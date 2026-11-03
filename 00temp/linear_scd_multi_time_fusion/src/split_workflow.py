from __future__ import annotations

import argparse
import configparser
import datetime as dt
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import h5py
import numpy as np


UTC = dt.timezone.utc


@dataclass(frozen=True)
class Source1File:
    path: Path
    cycle_utc: dt.datetime
    forecast_minutes: int


@dataclass(frozen=True)
class GridFrame:
    data: np.ndarray
    lat: np.ndarray
    lon: np.ndarray


@dataclass(frozen=True)
class M4Header:
    year: int
    month: int
    day: int
    hour: int
    lead_hour: int
    dlon: float
    dlat: float
    lon_start: float
    lon_end: float
    lat_start: float
    lat_end: float
    nlon: int
    nlat: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="实时拆分 unet_qpf 和 mait_st 为 0.01 度、10 分钟文件。")
    parser.add_argument("history_range", nargs="*", help="可选历史范围：START_UTC END_UTC，格式 YYYYMMDDHHMM。")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "resource" / "split_config.ini",
        help="时间拆分配置文件路径。",
    )
    parser.add_argument("--daemon", action="store_true", help="按配置中的 [schedule] 持续运行。")
    args = parser.parse_args()
    if len(args.history_range) not in (0, 2):
        parser.error("history range must be omitted or contain exactly START_UTC END_UTC.")
    return args


def load_config(path: Path) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    read = cfg.read(path, encoding="utf-8")
    if not read:
        raise FileNotFoundError(f"Cannot read config: {path}")
    return cfg


def parse_utc_minute(text: str) -> dt.datetime:
    if not re.fullmatch(r"\d{12}", text):
        raise ValueError(f"UTC time must use YYYYMMDDHHMM: {text}")
    return dt.datetime.strptime(text, "%Y%m%d%H%M").replace(tzinfo=UTC)


def ymd(value: dt.datetime) -> str:
    return value.strftime("%Y%m%d")


def ymdhm(value: dt.datetime) -> str:
    return value.strftime("%Y%m%d%H%M")


def bool_cfg(cfg: configparser.ConfigParser, section: str, key: str, default: bool) -> bool:
    if cfg.has_option(section, key):
        return cfg.getboolean(section, key)
    return default


def float_cfg(cfg: configparser.ConfigParser, section: str, key: str, default: float) -> float:
    return cfg.getfloat(section, key) if cfg.has_option(section, key) else default


def int_cfg(cfg: configparser.ConfigParser, section: str, key: str, default: int) -> int:
    return cfg.getint(section, key) if cfg.has_option(section, key) else default


def minute_list_cfg(cfg: configparser.ConfigParser, section: str, key: str, default: str) -> set[int]:
    text = cfg.get(section, key, fallback=default).strip()
    minutes = {int(item.strip()) for item in text.split(",") if item.strip()}
    invalid = sorted(item for item in minutes if item < 0 or item > 59)
    if invalid:
        raise ValueError(f"[{section}] {key} contains invalid minute values: {invalid}")
    return minutes


def iter_utc_minutes(start: dt.datetime, end: dt.datetime, step_minutes: int) -> list[dt.datetime]:
    if end < start:
        raise ValueError(f"history end is before start: {ymdhm(start)} > {ymdhm(end)}")
    if step_minutes <= 0:
        raise ValueError("history step must be positive")
    times: list[dt.datetime] = []
    current = start
    while current <= end:
        times.append(current)
        current += dt.timedelta(minutes=step_minutes)
    return times


def source1_pattern(suffix: str) -> re.Pattern[str]:
    return re.compile(rf"^(\d{{12}})\.(\d{{3}}){re.escape(suffix)}$")


def source2_pattern(suffix: str) -> re.Pattern[str]:
    return re.compile(rf"^(\d{{10}})\.(\d{{3}}){re.escape(suffix)}$")


def list_source1_files(cfg: configparser.ConfigParser) -> list[Source1File]:
    base_dir = Path(cfg.get("source_unet_qpf", "base_dir"))
    suffix = cfg.get("source_unet_qpf", "file_suffix", fallback=f".{cfg.get('source_unet_qpf', 'format')}")
    pattern = source1_pattern(suffix)
    files: list[Source1File] = []
    for path in base_dir.rglob(f"*{suffix}"):
        match = pattern.match(path.name)
        if not match:
            continue
        cycle = parse_utc_minute(match.group(1))
        files.append(Source1File(path=path, cycle_utc=cycle, forecast_minutes=int(match.group(2))))
    files.sort(key=lambda item: item.cycle_utc)
    return files


def latest_source1_file(cfg: configparser.ConfigParser) -> Source1File | None:
    files = list_source1_files(cfg)
    minutes = minute_list_cfg(cfg, "runtime", "allowed_realtime_minutes", "0,30")
    files = [item for item in files if item.cycle_utc.minute in minutes]
    return files[-1] if files else None


def history_source1_files(cfg: configparser.ConfigParser, start_text: str, end_text: str) -> list[Source1File]:
    start = parse_utc_minute(start_text)
    end = parse_utc_minute(end_text)
    step_minutes = int_cfg(cfg, "grid", "time_step_minutes", 10)
    wanted_cycles = set(iter_utc_minutes(start, end, step_minutes))
    by_cycle = {item.cycle_utc: item for item in list_source1_files(cfg)}
    missing = [cycle for cycle in sorted(wanted_cycles) if cycle not in by_cycle]
    if missing:
        print("[history] missing source_unet_qpf cycles:")
        for cycle in missing[:20]:
            print(f"  {ymdhm(cycle)}")
        if len(missing) > 20:
            print("  ...")
    return [by_cycle[cycle] for cycle in sorted(wanted_cycles) if cycle in by_cycle]


def nc_scale(handle: h5py.File) -> float:
    raw = handle["data0"].attrs.get("scale_factor", [1.0])
    return float(np.asarray(raw).ravel()[0])


def read_unet_file(path: Path) -> tuple[dict[int, GridFrame], tuple[float, float, float, float]]:
    frames: dict[int, GridFrame] = {}
    with h5py.File(path, "r") as handle:
        lat = np.asarray(handle["lat"][()], dtype=np.float64)
        lon = np.asarray(handle["lon"][()], dtype=np.float64)
        dtime = np.asarray(handle["dtime"][()], dtype=np.int32).ravel()
        scale = nc_scale(handle)
        for index, lead in enumerate(dtime):
            raw = handle["data0"][0, 0, 0, index, :, :].astype(np.float32)
            frames[int(lead)] = GridFrame(data=raw * scale, lat=lat, lon=lon)
    extent = (float(lon[0]), float(lon[-1]), float(lat[0]), float(lat[-1]))
    return frames, extent


def parse_m4_header(line: str) -> M4Header:
    parts = line.split()
    if len(parts) < 18 or parts[0].lower() != "diamond" or parts[1] != "4":
        raise ValueError(f"Unsupported MICAPS4 header: {line[:120]}")
    return M4Header(
        year=int(parts[3]),
        month=int(parts[4]),
        day=int(parts[5]),
        hour=int(parts[6]),
        lead_hour=int(parts[7]),
        dlon=float(parts[9]),
        dlat=float(parts[10]),
        lon_start=float(parts[11]),
        lon_end=float(parts[12]),
        lat_start=float(parts[13]),
        lat_end=float(parts[14]),
        nlon=int(parts[15]),
        nlat=int(parts[16]),
    )


def read_m4_file(path: Path) -> GridFrame:
    raw = path.read_bytes()
    first_newline = raw.find(b"\n")
    if first_newline < 0:
        raise ValueError(f"MICAPS4 file has no data body: {path}")
    header_line = raw[:first_newline].decode("utf-8", errors="ignore")
    header = parse_m4_header(header_line)
    values = np.fromstring(raw[first_newline + 1 :].decode("ascii", errors="ignore"), sep=" ", dtype=np.float32)
    expected = header.nlat * header.nlon
    if values.size < expected:
        raise ValueError(f"MICAPS4 data is incomplete: {path}, expected {expected}, got {values.size}")
    data = values[:expected].reshape(header.nlat, header.nlon)
    lat = np.round(header.lat_start + np.arange(header.nlat, dtype=np.float64) * header.dlat, 8)
    lon = np.round(header.lon_start + np.arange(header.nlon, dtype=np.float64) * header.dlon, 8)
    return GridFrame(data=data, lat=lat, lon=lon)


def read_nc_single_frame(path: Path) -> GridFrame:
    with h5py.File(path, "r") as handle:
        lat = np.asarray(handle["lat"][()], dtype=np.float64)
        lon = np.asarray(handle["lon"][()], dtype=np.float64)
        scale = nc_scale(handle)
        data = handle["data0"][0, 0, 0, 0, :, :].astype(np.float32) * scale
    return GridFrame(data=data, lat=lat, lon=lon)


def read_source2_frame(path: Path, fmt: str) -> GridFrame:
    fmt = fmt.lower()
    if fmt == "m4":
        return read_m4_file(path)
    if fmt == "nc":
        return read_nc_single_frame(path)
    raise ValueError(f"Unsupported source_mait_st format: {fmt}")


def source2_path(cfg: configparser.ConfigParser, cycle_utc: dt.datetime, lead_hour: int) -> Path:
    base_dir = Path(cfg.get("source_mait_st", "base_dir"))
    suffix = cfg.get("source_mait_st", "file_suffix", fallback=f".{cfg.get('source_mait_st', 'format')}")
    date_dir = bool_cfg(cfg, "source_mait_st", "date_dir", True)
    name = f"{cycle_utc:%Y%m%d%H}.{lead_hour:03d}{suffix}"
    return base_dir / ymd(cycle_utc) / name if date_dir else base_dir / name


def source2_alignment(source1_cycle_utc: dt.datetime, forecast_minutes: int) -> tuple[dt.datetime, list[int]]:
    source2_cycle = source1_cycle_utc.replace(minute=0, second=0, microsecond=0) - dt.timedelta(hours=1)
    end_time = source1_cycle_utc + dt.timedelta(minutes=forecast_minutes)
    hours_needed = math.ceil((end_time - source2_cycle).total_seconds() / 3600.0)
    return source2_cycle, list(range(1, hours_needed + 1))


def axis_overlap(extent1: tuple[float, float, float, float], extent2: tuple[float, float, float, float], step: float) -> tuple[np.ndarray, np.ndarray]:
    lon_start = max(extent1[0], extent2[0])
    lon_end = min(extent1[1], extent2[1])
    lat_start = max(extent1[2], extent2[2])
    lat_end = min(extent1[3], extent2[3])
    if lon_start >= lon_end or lat_start >= lat_end:
        raise ValueError(f"No spatial overlap: source1={extent1}, source2={extent2}")
    lon0 = math.ceil((lon_start - 1e-9) / step) * step
    lon1 = math.floor((lon_end + 1e-9) / step) * step
    lat0 = math.ceil((lat_start - 1e-9) / step) * step
    lat1 = math.floor((lat_end + 1e-9) / step) * step
    lon = np.round(np.arange(lon0, lon1 + step / 2.0, step, dtype=np.float64), 6)
    lat = np.round(np.arange(lat0, lat1 + step / 2.0, step, dtype=np.float64), 6)
    return lat, lon


def crop_slice(axis: np.ndarray, start: float, end: float) -> slice:
    left = max(int(np.searchsorted(axis, start, side="left")) - 1, 0)
    right = min(int(np.searchsorted(axis, end, side="right")), len(axis) - 1)
    return slice(left, right + 1)


def interp2d_linear(frame: GridFrame, dst_lat: np.ndarray, dst_lon: np.ndarray) -> np.ndarray:
    lat_slice = crop_slice(frame.lat, float(dst_lat[0]), float(dst_lat[-1]))
    lon_slice = crop_slice(frame.lon, float(dst_lon[0]), float(dst_lon[-1]))
    src_lat = frame.lat[lat_slice]
    src_lon = frame.lon[lon_slice]
    values = frame.data[lat_slice, lon_slice].astype(np.float32, copy=False)

    lon_interp = np.empty((values.shape[0], dst_lon.size), dtype=np.float32)
    for iy in range(values.shape[0]):
        lon_interp[iy, :] = np.interp(dst_lon, src_lon, values[iy, :]).astype(np.float32)

    out = np.empty((dst_lat.size, dst_lon.size), dtype=np.float32)
    for ix in range(dst_lon.size):
        out[:, ix] = np.interp(dst_lat, src_lat, lon_interp[:, ix]).astype(np.float32)
    return out


def frame_extent(frame: GridFrame) -> tuple[float, float, float, float]:
    return float(frame.lon[0]), float(frame.lon[-1]), float(frame.lat[0]), float(frame.lat[-1])


def load_source2_hourly(
    cfg: configparser.ConfigParser,
    source1_cycle_utc: dt.datetime,
    forecast_minutes: int,
) -> tuple[dt.datetime, dict[int, GridFrame], tuple[float, float, float, float]]:
    fmt = cfg.get("source_mait_st", "format").lower()
    strict = bool_cfg(cfg, "behavior", "strict_missing_mait", True)
    delete_broken = bool_cfg(cfg, "behavior", "delete_broken_inputs", False)
    source2_cycle, leads = source2_alignment(source1_cycle_utc, forecast_minutes)
    frames: dict[int, GridFrame] = {}
    extent: tuple[float, float, float, float] | None = None
    missing: list[Path] = []
    for lead in leads:
        path = source2_path(cfg, source2_cycle, lead)
        if not path.exists():
            missing.append(path)
            continue
        try:
            frame = read_source2_frame(path, fmt)
        except Exception:
            if delete_broken:
                path.unlink(missing_ok=True)
            raise
        frames[lead] = frame
        if extent is None:
            extent = frame_extent(frame)
    if missing and strict:
        raise FileNotFoundError("Missing mait_st files:\n" + "\n".join(str(path) for path in missing))
    if not frames or extent is None:
        raise FileNotFoundError("No mait_st frames were loaded.")
    return source2_cycle, frames, extent


def cumulative_source2_at(
    spatial_frames: dict[int, np.ndarray],
    source2_cycle_utc: dt.datetime,
    target_time_utc: dt.datetime,
) -> np.ndarray:
    offset_hours = (target_time_utc - source2_cycle_utc).total_seconds() / 3600.0
    if offset_hours < -1e-9:
        raise ValueError(f"mait_st target time is before source cycle: {target_time_utc}")

    if not spatial_frames:
        raise ValueError("No mait_st spatial frames are available.")

    sample = next(iter(spatial_frames.values()))
    if offset_hours <= 1e-9:
        return np.zeros_like(sample, dtype=np.float32)

    left = int(math.floor(offset_hours))
    right = int(math.ceil(offset_hours))

    cumulative = np.zeros_like(sample, dtype=np.float32)
    for lead in range(1, left + 1):
        if lead not in spatial_frames:
            raise KeyError(f"Cannot accumulate mait_st at {target_time_utc}: missing lead {lead}")
        cumulative += spatial_frames[lead]

    if left == right:
        return cumulative

    if right not in spatial_frames:
        raise KeyError(f"Cannot interpolate cumulative mait_st at {target_time_utc}: need lead {right}")
    fraction = np.float32(offset_hours - left)
    return cumulative + spatial_frames[right] * fraction


def source2_period_from_cumulative(
    spatial_frames: dict[int, np.ndarray],
    source2_cycle_utc: dt.datetime,
    period_start_utc: dt.datetime,
    period_end_utc: dt.datetime,
) -> np.ndarray:
    if period_end_utc < period_start_utc:
        raise ValueError(f"mait_st period end is before start: {period_start_utc} -> {period_end_utc}")
    start_cumulative = cumulative_source2_at(spatial_frames, source2_cycle_utc, period_start_utc)
    end_cumulative = cumulative_source2_at(spatial_frames, source2_cycle_utc, period_end_utc)
    return end_cumulative - start_cumulative


def output_path(cfg: configparser.ConfigParser, source_name: str, cycle_utc: dt.datetime, lead_minutes: int) -> Path:
    base_dir = Path(cfg.get("output", "base_dir"))
    return base_dir / source_name / ymd(cycle_utc) / f"{ymdhm(cycle_utc)}.{lead_minutes:03d}.nc"


def write_source_output_file(
    path: Path,
    source_name: str,
    cycle_utc: dt.datetime,
    lead_minutes: int,
    lat: np.ndarray,
    lon: np.ndarray,
    data: np.ndarray,
    cfg: configparser.ConfigParser,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    compression_level = int_cfg(cfg, "output", "compression_level", 4)
    valid_time = cycle_utc + dt.timedelta(minutes=lead_minutes)
    with h5py.File(path, "w") as handle:
        handle.attrs["source"] = source_name
        handle.attrs["cycle_time_utc"] = cycle_utc.strftime("%Y-%m-%d %H:%M:%S")
        handle.attrs["valid_time_utc"] = valid_time.strftime("%Y-%m-%d %H:%M:%S")
        handle.attrs["lead_minutes"] = lead_minutes
        handle.attrs["spatial_resolution_degree"] = float_cfg(cfg, "grid", "resolution_degree", 0.01)
        handle.attrs["time_resolution_minutes"] = int_cfg(cfg, "grid", "time_step_minutes", 10)
        handle.attrs["interpolation"] = (
            "linear spatial interpolation; mait_st uses cumulative temporal interpolation "
            "followed by period differencing"
        )

        member = handle.create_dataset("member", data=np.array([b"data0"]))
        level = handle.create_dataset("level", data=np.array([0], dtype=np.int32))
        time_ds = handle.create_dataset("time", data=np.array([0], dtype=np.int64))
        dtime = handle.create_dataset("dtime", data=np.array([lead_minutes], dtype=np.int32))
        lat_ds = handle.create_dataset("lat", data=lat)
        lon_ds = handle.create_dataset("lon", data=lon)

        member.attrs["NAME"] = "member"
        level.attrs["NAME"] = "level"
        time_ds.attrs["NAME"] = "time"
        time_ds.attrs["units"] = f"days since {cycle_utc:%Y-%m-%d %H:%M:%S}"
        time_ds.attrs["calendar"] = "proleptic_gregorian"
        time_ds.attrs["valid_time_utc"] = valid_time.strftime("%Y-%m-%d %H:%M:%S")
        dtime.attrs["NAME"] = "dtime"
        dtime.attrs["units"] = "minutes"
        lat_ds.attrs["NAME"] = "lat"
        lat_ds.attrs["units"] = "degrees_north"
        lon_ds.attrs["NAME"] = "lon"
        lon_ds.attrs["units"] = "degrees_east"

        data6d = data.astype(np.float32).reshape(1, 1, 1, 1, lat.size, lon.size)
        dataset = handle.create_dataset(
            "data0",
            data=data6d,
            dtype="float32",
            chunks=(1, 1, 1, 1, min(256, lat.size), min(256, lon.size)),
            compression="gzip",
            compression_opts=compression_level,
            shuffle=True,
            fillvalue=np.nan,
        )
        dataset.attrs["units"] = "mm"
        dataset.attrs["name"] = "data0"
        dataset.attrs["dimensions"] = "member,level,time,dtime,lat,lon"
        for axis_name, axis_ds in (
            ("member", member),
            ("level", level),
            ("time", time_ds),
            ("dtime", dtime),
            ("lat", lat_ds),
            ("lon", lon_ds),
        ):
            axis_ds.make_scale(axis_name)
        for dim_index, axis_ds in enumerate((member, level, time_ds, dtime, lat_ds, lon_ds)):
            dataset.dims[dim_index].attach_scale(axis_ds)


def process_cycle(cfg: configparser.ConfigParser, source1: Source1File) -> None:
    step_minutes = int_cfg(cfg, "grid", "time_step_minutes", 10)
    step_degree = float_cfg(cfg, "grid", "resolution_degree", 0.01)
    include_zero = bool_cfg(cfg, "grid", "include_zero_lead", True)
    zero_policy = cfg.get("grid", "unet_zero_lead", fallback="nan").lower()
    overwrite = bool_cfg(cfg, "output", "overwrite", False)
    mait_extra_minutes = int_cfg(cfg, "grid", "mait_extra_minutes", 0)
    mait_forecast_minutes = source1.forecast_minutes + mait_extra_minutes

    print(f"[cycle] source1={source1.path} cycle_utc={ymdhm(source1.cycle_utc)} forecast={source1.forecast_minutes}min")
    unet_frames, unet_extent = read_unet_file(source1.path)
    source2_cycle, source2_frames, source2_extent = load_source2_hourly(cfg, source1.cycle_utc, mait_forecast_minutes)
    dst_lat, dst_lon = axis_overlap(unet_extent, source2_extent, step_degree)
    print(f"[grid] lat {dst_lat[0]:.2f}-{dst_lat[-1]:.2f} n={dst_lat.size}; lon {dst_lon[0]:.2f}-{dst_lon[-1]:.2f} n={dst_lon.size}")

    source2_spatial: dict[int, np.ndarray] = {
        lead: interp2d_linear(frame, dst_lat, dst_lon) for lead, frame in source2_frames.items()
    }
    leads = list(range(0 if include_zero else step_minutes, mait_forecast_minutes + 1, step_minutes))
    for lead in leads:
        unet_path = output_path(cfg, "unet_qpf", source1.cycle_utc, lead)
        mait_path = output_path(cfg, "mait_st", source1.cycle_utc, lead)
        need_unet = lead <= source1.forecast_minutes
        if (not need_unet or unet_path.exists()) and mait_path.exists() and not overwrite:
            if need_unet:
                print(f"[exists] {unet_path}")
            print(f"[exists] {mait_path}")
            continue
        period_end = source1.cycle_utc + dt.timedelta(minutes=lead)
        period_start = period_end - dt.timedelta(minutes=step_minutes) if lead > 0 else period_end
        mait_data = source2_period_from_cumulative(source2_spatial, source2_cycle, period_start, period_end)
        if need_unet:
            if lead in unet_frames:
                unet_data = interp2d_linear(unet_frames[lead], dst_lat, dst_lon)
            elif lead == 0 and zero_policy == "first" and unet_frames:
                unet_data = interp2d_linear(unet_frames[min(unet_frames)], dst_lat, dst_lon)
            elif lead == 0 and zero_policy == "nan":
                unet_data = np.full_like(mait_data, np.nan, dtype=np.float32)
            else:
                raise KeyError(f"unet_qpf lead {lead} is not available in {source1.path}")
        if need_unet and (not unet_path.exists() or overwrite):
            write_source_output_file(unet_path, "unet_qpf", source1.cycle_utc, lead, dst_lat, dst_lon, unet_data, cfg)
            print(f"[wrote] {unet_path}")
        if not mait_path.exists() or overwrite:
            write_source_output_file(mait_path, "mait_st", source1.cycle_utc, lead, dst_lat, dst_lon, mait_data, cfg)
            print(f"[wrote] {mait_path}")


def run_once(cfg: configparser.ConfigParser, args: argparse.Namespace) -> None:
    positional_history = len(args.history_range) == 2
    mode = "history" if positional_history else "realtime"
    if mode == "realtime":
        source1 = latest_source1_file(cfg)
        if source1 is None:
            print("[skip] no source_unet_qpf files found")
            return
        allowed_minutes = sorted(minute_list_cfg(cfg, "runtime", "allowed_realtime_minutes", "0,30"))
        print(f"[realtime] allowed cycle minutes={allowed_minutes}; selected={ymdhm(source1.cycle_utc)}")
        process_cycle(cfg, source1)
        return
    if mode == "history":
        start_text, end_text = args.history_range
        files = history_source1_files(cfg, start_text, end_text)
        print(f"[history] files={len(files)} start={start_text} end={end_text}")
        for source1 in files:
            process_cycle(cfg, source1)
        return
    raise ValueError(f"Unsupported runtime mode: {mode}")


def seconds_until_next_daily(now: dt.datetime, daily_times: str) -> float:
    targets: list[dt.datetime] = []
    for item in daily_times.split(","):
        item = item.strip()
        if not item:
            continue
        hour, minute = [int(part) for part in item.split(":", 1)]
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += dt.timedelta(days=1)
        targets.append(candidate)
    if not targets:
        raise ValueError("[schedule] daily_times is empty")
    return max(1.0, (min(targets) - now).total_seconds())


def daemon_loop(cfg: configparser.ConfigParser, args: argparse.Namespace) -> None:
    tz = ZoneInfo(cfg.get("schedule", "timezone", fallback="Asia/Shanghai"))
    schedule_mode = cfg.get("schedule", "mode", fallback="interval").lower()
    while True:
        now = dt.datetime.now(tz)
        print(f"[daemon] run at local={now:%Y-%m-%d %H:%M:%S %Z}")
        run_once(cfg, args)
        if schedule_mode == "interval":
            sleep_seconds = int_cfg(cfg, "schedule", "interval_minutes", 30) * 60
        elif schedule_mode == "daily_times":
            sleep_seconds = seconds_until_next_daily(dt.datetime.now(tz), cfg.get("schedule", "daily_times"))
        else:
            raise ValueError(f"Unsupported schedule mode: {schedule_mode}")
        print(f"[daemon] sleep {sleep_seconds:.0f}s")
        time.sleep(sleep_seconds)


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    if args.daemon:
        daemon_loop(cfg, args)
    else:
        run_once(cfg, args)


if __name__ == "__main__":
    main()
