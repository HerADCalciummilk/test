from pathlib import Path
from typing import List, Optional, Sequence, Union

import h5py
import numpy as np
import xarray as xr

from fy4agri.metadata import CHANNELS, attr_scalar, common_attrs, parse_channels
from fy4agri.projection import latlon_to_fy4_grid
from fy4agri.reader import read_calibrated_channel, sample_to_latlon


class FY4LatLonChannelPlugin:
    """FY-4B AGRI L1 HDF parser plugin.

    The plugin reads FY-4B AGRI L1 channel data, calibrates each channel with
    its HDF calibration table, resamples to a regular latitude/longitude grid,
    and writes one NetCDF file per channel.
    """

    def __init__(
        self,
        output_root: Optional[str] = None,
        resolution: float = 0.04,
        lat_min: float = -60.0,
        lat_max: float = 60.0,
        lon_half_width: float = 75.0,
        channels: Union[str, Sequence[int]] = "1-15",
        resampling: str = "bilinear",
    ):
        if resolution <= 0:
            raise ValueError("resolution must be greater than 0")
        if lat_min >= lat_max:
            raise ValueError("lat_min must be less than lat_max")
        if lon_half_width <= 0:
            raise ValueError("lon_half_width must be greater than 0")
        if resampling not in ("nearest", "bilinear"):
            raise ValueError("resampling must be 'nearest' or 'bilinear'")

        self.output_root = Path(output_root) if output_root else None
        self.resolution = float(resolution)
        self.lat_min = float(lat_min)
        self.lat_max = float(lat_max)
        self.lon_half_width = float(lon_half_width)
        self.channels = self._normalize_channels(channels)
        self.resampling = resampling

    @staticmethod
    def _normalize_channels(channels: Union[str, Sequence[int]]) -> List[int]:
        if isinstance(channels, str):
            return parse_channels(channels)
        return parse_channels(",".join(str(ch) for ch in channels))

    def _build_target_grid(self, lon0: float):
        lat = np.arange(
            self.lat_max,
            self.lat_min - self.resolution / 2.0,
            -self.resolution,
            dtype=np.float32,
        )
        lon = np.arange(
            lon0 - self.lon_half_width,
            lon0 + self.lon_half_width + self.resolution / 2.0,
            self.resolution,
            dtype=np.float32,
        )
        lon2d, lat2d = np.meshgrid(lon, lat)
        return lat, lon, lat2d, lon2d

    def _resolve_output_dir(self, input_hdf: Union[str, Path], output_dir: Optional[Union[str, Path]]) -> Path:
        if output_dir is not None:
            return Path(output_dir)
        if self.output_root is not None:
            return self.output_root / Path(input_hdf).stem
        raise ValueError("output_dir must be provided when output_root is not configured")

    def _write_channel_file(self, output_dir: Path, channel_number: int, values, lat, lon, attrs) -> Path:
        info = CHANNELS[channel_number]
        dataset = xr.Dataset(
            data_vars={
                "channel_value": (
                    ("lat", "lon"),
                    values,
                    {
                        "long_name": f"FY-4B AGRI L1 channel {channel_number:02d} calibrated value on regular lat/lon grid",
                        "wavelength": info.wavelength,
                        "units": info.unit,
                        "value_kind": info.value_kind,
                        "_FillValue": np.float32(np.nan),
                    },
                )
            },
            coords={
                "lat": lat,
                "lon": lon,
            },
            attrs={
                **attrs,
                "channel": channel_number,
                "channel_wavelength": info.wavelength,
                "channel_units": info.unit,
                "channel_value_kind": info.value_kind,
            },
        )

        output_path = output_dir / f"CH{channel_number:02d}_{info.safe_wavelength}.nc"
        dataset.to_netcdf(output_path, engine="scipy", format="NETCDF3_64BIT")
        return output_path

    def process(self, input_hdf: Union[str, Path], output_dir: Optional[Union[str, Path]] = None) -> List[str]:
        """Convert one FY-4B AGRI HDF file to split regular lat/lon channel files.

        Args:
            input_hdf: Source FY-4B AGRI L1 HDF file.
            output_dir: Destination folder for per-channel NetCDF files. If not
                provided, `output_root / input_hdf.stem` is used.

        Returns:
            List of generated NetCDF file paths.
        """
        input_hdf = Path(input_hdf)
        output_dir = self._resolve_output_dir(input_hdf, output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        generated_files = []
        with h5py.File(input_hdf, "r") as hdf:
            lon0 = float(attr_scalar(hdf.attrs, "NOMCenterLon"))
            lat, lon, lat2d, lon2d = self._build_target_grid(lon0)
            src_line, src_col, visible = latlon_to_fy4_grid(lat2d, lon2d, lon0, hdf.attrs)

            attrs = common_attrs(hdf, input_hdf)
            attrs.update(
                {
                    "title": "FY-4B AGRI L1 single-channel regular lat/lon grid",
                    "output_projection": f"regular latitude/longitude grid, {self.resampling} resampling from FY-4 geostationary fixed grid",
                    "resampling": self.resampling,
                    "source_grid": "FY-4 geostationary fixed grid",
                    "output_layout": "one NetCDF file per channel",
                }
            )

            for channel_number in self.channels:
                source = read_calibrated_channel(hdf, channel_number)
                values = sample_to_latlon(source, src_line, src_col, visible, self.resampling)
                output_path = self._write_channel_file(output_dir, channel_number, values, lat, lon, attrs)
                generated_files.append(str(output_path))
                print(output_path)

        return generated_files


FY4ChannelPlugin = FY4LatLonChannelPlugin


def process(input_hdf: Union[str, Path], output_dir: Union[str, Path], config=None, **kwargs) -> List[str]:
    """单文件解码入口。``config`` 为空时不改插件参数；给出时按该 ini 补齐未传入项。"""
    if not config:
        return FY4LatLonChannelPlugin(**kwargs).process(input_hdf, output_dir)
    from utils.util_env import resolve_single

    cfg = resolve_single(
        input_hdf=str(input_hdf),
        output_dir=str(output_dir),
        config=config,
        **kwargs,
    )
    plugin_keys = ("resolution", "lat_min", "lat_max", "lon_half_width", "channels", "resampling")
    plugin_kwargs = {key: cfg[key] for key in plugin_keys if key in cfg}
    return FY4LatLonChannelPlugin(**plugin_kwargs).process(cfg["input_hdf"], cfg["output_dir"])
