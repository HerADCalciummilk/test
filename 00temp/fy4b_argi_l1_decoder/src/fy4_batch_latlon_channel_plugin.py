import re
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import List, Optional, Sequence, Union

import h5py
import numpy as np
import xarray as xr

from fy4agri.metadata import CHANNELS, attr_scalar, common_attrs, parse_channels
from fy4agri.projection import latlon_to_fy4_grid
from fy4agri.reader import read_calibrated_channel, sample_to_latlon


FY4_FILENAME_RE = re.compile(
    r"^FY4B-_AGRI--_N_DISK_(?P<center>\d{4}E)_L1-_FDI-_MULT_NOM_"
    r"(?P<start>\d{14})_(?P<end>\d{14})_4000M_V(?P<version>\d+)\.HDF$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FY4FileInfo:
    path: Path
    center: str
    start_time: datetime
    end_time: datetime
    version: str

    @property
    def ymd(self) -> str:
        return self.start_time.strftime("%Y%m%d")

    @property
    def ymdh(self) -> str:
        return self.start_time.strftime("%Y%m%d%H")


def parse_time(value: Union[str, datetime], is_end: bool = False) -> datetime:
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    formats = {
        8: "%Y%m%d",
        10: "%Y%m%d%H",
        12: "%Y%m%d%H%M",
        14: "%Y%m%d%H%M%S",
    }
    if len(text) not in formats:
        raise ValueError("time must use YYYYMMDD, YYYYMMDDHH, YYYYMMDDHHMM, or YYYYMMDDHHMMSS")

    parsed = datetime.strptime(text, formats[len(text)])
    if is_end and len(text) == 8:
        return datetime.combine(parsed.date(), time(23, 59, 59))
    if is_end and len(text) == 10:
        return parsed.replace(minute=59, second=59)
    if is_end and len(text) == 12:
        return parsed.replace(second=59)
    return parsed


def parse_fy4_filename(path: Union[str, Path]) -> Optional[FY4FileInfo]:
    path = Path(path)
    match = FY4_FILENAME_RE.match(path.name)
    if not match:
        return None
    return FY4FileInfo(
        path=path,
        center=match.group("center").upper(),
        start_time=datetime.strptime(match.group("start"), "%Y%m%d%H%M%S"),
        end_time=datetime.strptime(match.group("end"), "%Y%m%d%H%M%S"),
        version=match.group("version"),
    )


class FY4BatchLatLonChannelPlugin:
    """Batch FY-4B AGRI L1 HDF parser plugin.

    It scans a base directory for 1050E/1330E FY-4B HDF files in a time range,
    converts each file to a regular latitude/longitude grid, and writes one
    NetCDF file per channel using:

        output_root/CHxx/YYYYMMDD/YYYYMMDDHH.nc
    """

    def __init__(
        self,
        input_root: str,
        output_root: str,
        start_time: Union[str, datetime],
        end_time: Union[str, datetime],
        resolution: float = 0.04,
        lat_min: float = -60.0,
        lat_max: float = 60.0,
        lon_half_width: float = 75.0,
        channels: Union[str, Sequence[int]] = "1-15",
        resampling: str = "bilinear",
        centers: Sequence[str] = ("1050E", "1330E"),
        overwrite: bool = False,
        recursive: bool = False,
    ):
        if resolution <= 0:
            raise ValueError("resolution must be greater than 0")
        if lat_min >= lat_max:
            raise ValueError("lat_min must be less than lat_max")
        if lon_half_width <= 0:
            raise ValueError("lon_half_width must be greater than 0")
        if resampling not in ("nearest", "bilinear"):
            raise ValueError("resampling must be 'nearest' or 'bilinear'")

        self.input_root = Path(input_root)
        self.output_root = Path(output_root)
        self.start_time = parse_time(start_time)
        self.end_time = parse_time(end_time, is_end=True)
        if self.start_time > self.end_time:
            raise ValueError("start_time must be earlier than or equal to end_time")

        self.resolution = float(resolution)
        self.lat_min = float(lat_min)
        self.lat_max = float(lat_max)
        self.lon_half_width = float(lon_half_width)
        self.channels = self._normalize_channels(channels)
        self.resampling = resampling
        self.centers = {center.upper() for center in centers}
        self.overwrite = bool(overwrite)
        self.recursive = bool(recursive)

    @staticmethod
    def _normalize_channels(channels: Union[str, Sequence[int]]) -> List[int]:
        if isinstance(channels, str):
            return parse_channels(channels)
        return parse_channels(",".join(str(ch) for ch in channels))

    def _iter_hdf_files(self) -> List[FY4FileInfo]:
        pattern = "**/*.HDF" if self.recursive else "*.HDF"
        matched = []
        for path in self.input_root.glob(pattern):
            info = parse_fy4_filename(path)
            if info is None:
                continue
            if info.center not in self.centers:
                continue
            if self.start_time <= info.start_time <= self.end_time:
                matched.append(info)
        return sorted(matched, key=lambda item: (item.start_time, item.center, item.path.name))

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

    def _channel_output_path(self, channel_number: int, file_info: FY4FileInfo) -> Path:
        return self.output_root / f"CH{channel_number:02d}" / file_info.ymd / f"{file_info.ymdh}.nc"

    def _write_channel_file(self, path: Path, channel_number: int, values, lat, lon, attrs) -> Optional[str]:
        if path.exists() and not self.overwrite:
            print(f"skip existing: {path}")
            return None

        info = CHANNELS[channel_number]
        path.parent.mkdir(parents=True, exist_ok=True)
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
            coords={"lat": lat, "lon": lon},
            attrs={
                **attrs,
                "channel": channel_number,
                "channel_wavelength": info.wavelength,
                "channel_units": info.unit,
                "channel_value_kind": info.value_kind,
            },
        )
        dataset.to_netcdf(path, engine="scipy", format="NETCDF3_64BIT")
        print(path)
        return str(path)

    def _process_one_file(self, file_info: FY4FileInfo) -> List[str]:
        generated = []
        with h5py.File(file_info.path, "r") as hdf:
            lon0 = float(attr_scalar(hdf.attrs, "NOMCenterLon"))
            lat, lon, lat2d, lon2d = self._build_target_grid(lon0)
            src_line, src_col, visible = latlon_to_fy4_grid(lat2d, lon2d, lon0, hdf.attrs)

            attrs = common_attrs(hdf, file_info.path)
            attrs.update(
                {
                    "title": "FY-4B AGRI L1 single-channel regular lat/lon grid",
                    "output_projection": f"regular latitude/longitude grid, {self.resampling} resampling from FY-4 geostationary fixed grid",
                    "resampling": self.resampling,
                    "source_grid": "FY-4 geostationary fixed grid",
                    "output_layout": "output_root/CHxx/YYYYMMDD/YYYYMMDDHH.nc",
                    "satellite_center": file_info.center,
                    "source_start_time": file_info.start_time.strftime("%Y%m%d%H%M%S"),
                    "source_end_time": file_info.end_time.strftime("%Y%m%d%H%M%S"),
                }
            )

            for channel_number in self.channels:
                output_path = self._channel_output_path(channel_number, file_info)
                source = read_calibrated_channel(hdf, channel_number)
                values = sample_to_latlon(source, src_line, src_col, visible, self.resampling)
                written = self._write_channel_file(output_path, channel_number, values, lat, lon, attrs)
                if written is not None:
                    generated.append(written)
        return generated

    def process(self) -> List[str]:
        files = self._iter_hdf_files()
        if not files:
            print("No FY4B HDF files matched the requested time range.")
            return []

        generated = []
        for file_info in files:
            print(f"processing {file_info.center} {file_info.start_time:%Y-%m-%d %H:%M:%S}: {file_info.path}")
            generated.extend(self._process_one_file(file_info))
        return generated


FY4BatchPlugin = FY4BatchLatLonChannelPlugin


def process(
    input_root: str,
    output_root: str,
    start_time: Union[str, datetime],
    end_time: Union[str, datetime],
    config=None,
    **kwargs,
) -> List[str]:
    """批量解码入口。``config`` 为空时不改插件参数；给出时按该 ini 补齐未传入项。"""
    if not config:
        return FY4BatchLatLonChannelPlugin(
            input_root=input_root,
            output_root=output_root,
            start_time=start_time,
            end_time=end_time,
            **kwargs,
        ).process()
    from utils.util_env import resolve_batch

    cfg = resolve_batch(
        input_root=input_root,
        output_root=output_root,
        start_time=start_time if isinstance(start_time, str) else start_time.strftime("%Y%m%d%H%M%S"),
        end_time=end_time if isinstance(end_time, str) else end_time.strftime("%Y%m%d%H%M%S"),
        config=config,
        **kwargs,
    )
    plugin_keys = ("resolution", "lat_min", "lat_max", "lon_half_width", "channels", "resampling")
    plugin_kwargs = {key: cfg[key] for key in plugin_keys if key in cfg}
    centers = cfg.get("centers")
    if isinstance(centers, str):
        centers = [item.strip() for item in centers.split(",") if item.strip()]
    return FY4BatchLatLonChannelPlugin(
        input_root=cfg["input_root"],
        output_root=cfg["output_root"],
        start_time=cfg["start_time"],
        end_time=cfg["end_time"],
        centers=centers,
        overwrite=cfg.get("overwrite"),
        recursive=cfg.get("recursive"),
        **plugin_kwargs,
    ).process()
