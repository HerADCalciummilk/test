"""
Run SCD pair fusion from an INI config.

This adapter is designed for the current realtime-style data layout:

    source_dir/YYYYMMDD/YYYYMMDDHHMM.LLL.nc

where LLL is lead minutes, and each NetCDF file contains:

    data0(member, level, time, dtime, lat, lon)

The script processes files one by one, so it can handle large 0.01-degree
national grids without stacking all lead times in memory.
"""

from configparser import ConfigParser
from dataclasses import dataclass
import argparse
import datetime as dt
from pathlib import Path
import re
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import xarray as xr


from linear_scd_multi_time_fusion.src.linear_blending import linear_blending_forecast


UTC = dt.timezone.utc


@dataclass(frozen=True)
class PairFile:
    cycle: str
    lead_minutes: int
    source1_path: Path
    source2_path: Path
    output_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按配置运行 SCD 双源配对融合。")
    parser.add_argument("history_range", nargs="*", help="可选历史范围：START_UTC END_UTC，格式 YYYYMMDDHHMM。")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "resource" / "scd_pair_fusion_config.ini",
        help="SCD 融合配置文件路径。",
    )
    args = parser.parse_args()
    if len(args.history_range) not in (0, 2):
        parser.error("history range must be omitted or contain exactly START_UTC END_UTC.")
    return args


def read_config(config_path: Path) -> ConfigParser:
    parser = ConfigParser(inline_comment_prefixes=("#", ";"))
    read_files = parser.read(config_path, encoding="utf-8")
    if not read_files:
        raise FileNotFoundError(f"Cannot read config: {config_path}")
    return parser


def get_optional(config: ConfigParser, section: str, key: str) -> Optional[str]:
    value = config.get(section, key, fallback="").strip()
    return value or None


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_utc_minute(text: str) -> dt.datetime:
    if not re.fullmatch(r"\d{12}", text):
        raise ValueError(f"UTC time must use YYYYMMDDHHMM: {text}")
    return dt.datetime.strptime(text, "%Y%m%d%H%M").replace(tzinfo=UTC)


def ymdhm(value: dt.datetime) -> str:
    return value.strftime("%Y%m%d%H%M")


def minute_list_config(config: ConfigParser) -> set[int]:
    text = config.get("run", "allowed_realtime_minutes", fallback="0,30").strip()
    minutes = {int(item.strip()) for item in text.split(",") if item.strip()}
    invalid = sorted(item for item in minutes if item < 0 or item > 59)
    if invalid:
        raise ValueError(f"[run] allowed_realtime_minutes contains invalid minute values: {invalid}")
    return minutes


def iter_history_cycles(start_text: str, end_text: str, step_minutes: int) -> List[str]:
    start = parse_utc_minute(start_text)
    end = parse_utc_minute(end_text)
    if end < start:
        raise ValueError(f"history end is before start: {start_text} > {end_text}")
    cycles: List[str] = []
    current = start
    while current <= end:
        cycles.append(ymdhm(current))
        current += dt.timedelta(minutes=step_minutes)
    return cycles


def parse_cycle_and_lead(path: Path) -> Tuple[str, int]:
    parts = path.name.split(".")
    if len(parts) < 3:
        raise ValueError(f"Filename must look like YYYYMMDDHHMM.LLL.nc: {path.name}")
    cycle = parts[0]
    lead = int(parts[1])
    return cycle, lead


def discover_nc_files(source_dir: Path) -> List[Path]:
    files = sorted(source_dir.glob("*/*.nc"))
    if not files:
        files = sorted(source_dir.glob("*.nc"))
    return files


def select_source1_files(
    config: ConfigParser,
    mode: str,
    history_start_utc: Optional[str],
    history_end_utc: Optional[str],
) -> List[Path]:
    source1_dir = Path(config.get("paths", "source1_dir")).resolve()
    files = discover_nc_files(source1_dir)
    if not files:
        raise FileNotFoundError(f"No .nc files found under source1_dir: {source1_dir}")

    cycles = [(parse_cycle_and_lead(path)[0], path) for path in files]

    if mode == "realtime":
        minutes = minute_list_config(config)
        allowed_cycles = [(cycle, path) for cycle, path in cycles if int(cycle[-2:]) in minutes]
        if not allowed_cycles:
            raise FileNotFoundError(f"No source1 files match realtime allowed minutes: {sorted(minutes)}")
        latest_cycle = max(cycle for cycle, _ in allowed_cycles)
        selected = [path for cycle, path in cycles if cycle == latest_cycle]
    elif mode == "history":
        if not history_start_utc or not history_end_utc:
            raise ValueError("history mode requires history_start_utc and history_end_utc")
        step_minutes = config.getint("run", "history_step_minutes", fallback=10)
        wanted_cycles = set(iter_history_cycles(history_start_utc, history_end_utc, step_minutes))
        by_cycle: Dict[str, List[Path]] = {}
        for cycle, path in cycles:
            by_cycle.setdefault(cycle, []).append(path)
        missing = [cycle for cycle in sorted(wanted_cycles) if cycle not in by_cycle]
        if missing:
            print("Missing source1 cycles:")
            for cycle in missing[:20]:
                print(f"  {cycle}")
            if len(missing) > 20:
                print("  ...")
        selected = [path for cycle in sorted(wanted_cycles) for path in by_cycle.get(cycle, [])]
    else:
        raise ValueError("mode must be realtime or history")

    selected = sorted(selected, key=lambda path: parse_cycle_and_lead(path))
    max_files = get_optional(config, "run", "max_files")
    if max_files is not None:
        selected = selected[: int(max_files)]
    return selected


def build_pairs(
    config: ConfigParser,
    mode: str,
    history_start_utc: Optional[str],
    history_end_utc: Optional[str],
) -> List[PairFile]:
    source1_dir = Path(config.get("paths", "source1_dir")).resolve()
    source2_dir = Path(config.get("paths", "source2_dir")).resolve()
    output_dir = Path(config.get("paths", "output_dir")).resolve()

    source1_files = select_source1_files(config, mode, history_start_utc, history_end_utc)
    pairs: List[PairFile] = []
    missing: List[Path] = []

    for source1_path in source1_files:
        rel = source1_path.relative_to(source1_dir)
        source2_path = source2_dir / rel
        cycle, lead = parse_cycle_and_lead(source1_path)
        cycle_day = cycle[:8]
        output_path = output_dir / cycle_day / cycle / source1_path.name
        if source2_path.exists():
            pairs.append(PairFile(cycle, lead, source1_path, source2_path, output_path))
        else:
            missing.append(source2_path)

    print(f"Selected source1 files: {len(source1_files)}")
    print(f"Matched pairs: {len(pairs)}")
    if missing:
        print(f"Missing source2 files: {len(missing)}")
        for path in missing[:10]:
            print(f"  missing: {path}")
        if len(missing) > 10:
            print("  ...")
    if not pairs:
        raise FileNotFoundError("No matched source1/source2 file pairs found")
    return pairs


def parse_keyframe_weights(text: str) -> Dict[int, float]:
    weights: Dict[int, float] = {}
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        lead_text, weight_text = item.split(":", 1)
        weights[int(lead_text.strip())] = float(weight_text.strip())
    if not weights:
        raise ValueError("keyframe_weights cannot be empty")
    return dict(sorted(weights.items()))


def interpolate_weight(lead_minutes: int, keyframes: Dict[int, float]) -> float:
    items = sorted(keyframes.items())
    if lead_minutes <= items[0][0]:
        return items[0][1]
    if lead_minutes >= items[-1][0]:
        return items[-1][1]

    for (lead_a, weight_a), (lead_b, weight_b) in zip(items[:-1], items[1:]):
        if lead_a <= lead_minutes <= lead_b:
            fraction = (lead_minutes - lead_a) / (lead_b - lead_a)
            return weight_a + fraction * (weight_b - weight_a)
    raise RuntimeError("Failed to interpolate weight")


def get_crop_slices(ds: xr.Dataset, config: ConfigParser) -> Tuple[slice, slice]:
    lon_min = get_optional(config, "fusion", "lon_min")
    lon_max = get_optional(config, "fusion", "lon_max")
    lat_min = get_optional(config, "fusion", "lat_min")
    lat_max = get_optional(config, "fusion", "lat_max")
    if not any([lon_min, lon_max, lat_min, lat_max]):
        return slice(None), slice(None)
    if not all([lon_min, lon_max, lat_min, lat_max]):
        raise ValueError("lon_min/lon_max/lat_min/lat_max must either all be set or all be empty")

    lon = ds["lon"].values
    lat = ds["lat"].values
    lon_mask = (lon >= float(lon_min)) & (lon <= float(lon_max))
    lat_mask = (lat >= float(lat_min)) & (lat <= float(lat_max))
    lon_idx = np.where(lon_mask)[0]
    lat_idx = np.where(lat_mask)[0]
    if len(lon_idx) == 0 or len(lat_idx) == 0:
        raise ValueError("Crop range does not overlap the input grid")
    return slice(int(lat_idx[0]), int(lat_idx[-1]) + 1), slice(int(lon_idx[0]), int(lon_idx[-1]) + 1)


def assert_compatible(a: xr.Dataset, b: xr.Dataset, source1_path: Path, source2_path: Path) -> None:
    for coord in ["member", "level", "time", "dtime", "lat", "lon"]:
        if coord not in a or coord not in b:
            raise ValueError(f"Missing coordinate {coord} in {source1_path} or {source2_path}")
    if a["data0"].dims != b["data0"].dims:
        raise ValueError(f"data0 dims differ: {source1_path} vs {source2_path}")
    for coord in ["member", "level", "time", "dtime", "lat", "lon"]:
        if not np.array_equal(a[coord].values, b[coord].values):
            raise ValueError(f"Coordinate {coord} differs: {source1_path} vs {source2_path}")


def fuse_one_pair(pair: PairFile, config: ConfigParser, keyframes: Dict[int, float]) -> None:
    blending_type = config.get("fusion", "blending_type", fallback="linear").strip().lower()
    if blending_type not in {"linear", "salient"}:
        raise ValueError("blending_type must be linear or salient")

    output_var = config.get("fusion", "output_var", fallback="data0").strip()
    output_source = config.get("fusion", "output_source", fallback="scd_fused").strip()
    weight_source1 = interpolate_weight(pair.lead_minutes, keyframes)

    ds1 = xr.open_dataset(pair.source1_path)
    ds2 = xr.open_dataset(pair.source2_path)
    try:
        assert_compatible(ds1, ds2, pair.source1_path, pair.source2_path)
        lat_slice, lon_slice = get_crop_slices(ds1, config)

        source1 = ds1["data0"].values[0, 0, 0, 0, lat_slice, lon_slice].astype("float32")
        source2 = ds2["data0"].values[0, 0, 0, 0, lat_slice, lon_slice].astype("float32")
        source1 = np.nan_to_num(source1, nan=0.0)
        source2 = np.nan_to_num(source2, nan=0.0)
        source1[source1 < 0] = 0.0
        source2[source2 < 0] = 0.0

        fused = linear_blending_forecast(
            precomputed_nowcast=source1[np.newaxis, :, :],
            precip_model=source2[np.newaxis, :, :],
            saliency=(blending_type == "salient"),
            weights_now_list=[weight_source1],
        )[0].astype("float32")

        fused_6d = fused[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
        out = xr.Dataset(
            data_vars={
                output_var: (("member", "level", "time", "dtime", "lat", "lon"), fused_6d),
            },
            coords={
                "member": ds1["member"].values,
                "level": ds1["level"].values,
                "time": ds1["time"].values,
                "dtime": ds1["dtime"].values,
                "lat": ds1["lat"].values[lat_slice],
                "lon": ds1["lon"].values[lon_slice],
            },
            attrs={
                **dict(ds1.attrs),
                "source": output_source,
                "source1_file": str(pair.source1_path),
                "source2_file": str(pair.source2_path),
                "blending_type": blending_type,
                "source1_weight": str(weight_source1),
                "source2_weight": str(1.0 - weight_source1),
            },
        )

        pair.output_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_netcdf(pair.output_path)
        out.close()
    finally:
        ds1.close()
        ds2.close()


def main() -> None:
    args = parse_args()
    config_path = args.config
    config = read_config(config_path)
    positional_history = len(args.history_range) == 2
    mode = "history" if positional_history else "realtime"
    if positional_history:
        history_start_utc, history_end_utc = args.history_range
    else:
        history_start_utc = None
        history_end_utc = None
    dry_run = parse_bool(config.get("run", "dry_run", fallback="true"))
    keyframes = parse_keyframe_weights(config.get("fusion", "keyframe_weights"))
    pairs = build_pairs(config, mode, history_start_utc, history_end_utc)

    print("Config:", config_path)
    print("Mode:", mode)
    if mode == "realtime":
        print("Allowed realtime minutes:", sorted(minute_list_config(config)))
    else:
        print("History:", history_start_utc, "->", history_end_utc)
    print("Blending:", config.get("fusion", "blending_type", fallback="linear"))
    print("Keyframes:", keyframes)
    print("Dry run:", dry_run)
    print("\nFirst pairs:")
    for pair in pairs[:5]:
        weight = interpolate_weight(pair.lead_minutes, keyframes)
        print(
            f"  {pair.source1_path.name} lead={pair.lead_minutes:03d} "
            f"source1_weight={weight:.3f} -> {pair.output_path}"
        )

    if dry_run:
        print("\nDry run only. Set dry_run = false in config to write fused NetCDF files.")
        return

    for i, pair in enumerate(pairs, start=1):
        print(f"[{i}/{len(pairs)}] Fusing {pair.source1_path.name} -> {pair.output_path}")
        fuse_one_pair(pair, config, keyframes)

    print("Fusion completed.")


if __name__ == "__main__":
    main()
