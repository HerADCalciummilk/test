from __future__ import annotations

import argparse
import configparser
import datetime as dt
import re
import shutil
from pathlib import Path
from typing import Iterable


UTC = dt.timezone.utc
BJT = dt.timezone(dt.timedelta(hours=8))

try:
    from .conf_overrides import CONF_KEYS, apply_conf_overrides
except ImportError:
    from conf_overrides import CONF_KEYS, apply_conf_overrides


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对 SCD 融合结果进行前后时段补齐。")
    parser.add_argument("history_range", nargs="*", help="可选历史范围：START_UTC END_UTC，格式 YYYYMMDDHHMM。")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "resource" / "conf.ini",
        help="SCD 融合配置文件路径。",
    )
    args = parser.parse_args()
    if len(args.history_range) not in (0, 2):
        parser.error("history range must be omitted or contain exactly START_UTC END_UTC.")
    return args


def read_config(path: Path) -> configparser.ConfigParser:
    config = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    read_files = config.read(path, encoding="utf-8")
    if not read_files:
        raise FileNotFoundError(f"Cannot read config: {path}")
    return config


def parse_utc_minute(text: str) -> dt.datetime:
    if not re.fullmatch(r"\d{12}", text):
        raise ValueError(f"UTC time must use YYYYMMDDHHMM: {text}")
    return dt.datetime.strptime(text, "%Y%m%d%H%M").replace(tzinfo=UTC)


def ymd(value: dt.datetime) -> str:
    return value.strftime("%Y%m%d")


def ymdhm(value: dt.datetime) -> str:
    return value.strftime("%Y%m%d%H%M")


def lead_text(minutes: int) -> str:
    return f"n{abs(minutes):02d}" if minutes < 0 else f"{minutes:03d}"


def parse_cycle_and_lead(path: Path) -> tuple[str, int] | None:
    match = re.fullmatch(r"(\d{12})\.(\d{3}|n\d{2,3})\.nc", path.name)
    if not match:
        return None
    lead = match.group(2)
    lead_minutes = -int(lead[1:]) if lead.startswith("n") else int(lead)
    return match.group(1), lead_minutes


def iter_history_cycles(start_text: str, end_text: str, step_minutes: int) -> list[str]:
    start = parse_utc_minute(start_text)
    end = parse_utc_minute(end_text)
    if end < start:
        raise ValueError(f"history end is before start: {start_text} > {end_text}")
    cycles: list[str] = []
    current = start
    while current <= end:
        cycles.append(ymdhm(current))
        current += dt.timedelta(minutes=step_minutes)
    return cycles


def latest_output_cycle(output_dir: Path) -> str:
    cycles: set[str] = set()
    for path in output_dir.glob("*/*/*.nc"):
        parsed = parse_cycle_and_lead(path)
        if parsed is not None:
            cycles.add(parsed[0])
    if not cycles:
        raise FileNotFoundError(f"No fusion output files found under {output_dir}")
    return max(cycles)


def cycle_output_dir(config: configparser.ConfigParser, cycle: str) -> Path:
    output_dir = Path(config.get("paths", "output_dir"))
    return output_dir / cycle[:8] / cycle


def truth_path(config: configparser.ConfigParser, valid_time: dt.datetime) -> Path:
    truth_dir = Path(config.get("paths", "truth_dir"))
    valid_time_bjt = valid_time.astimezone(BJT)
    return truth_dir / f"{valid_time_bjt:%Y}" / ymd(valid_time_bjt) / f"BJT_{ymdhm(valid_time_bjt)}.000.nc"


def mait_path(config: configparser.ConfigParser, cycle: str, lead_minutes: int) -> Path:
    source2_dir = Path(config.get("paths", "source2_dir"))
    return source2_dir / cycle[:8] / f"{cycle}.{lead_minutes:03d}.nc"


def output_path(config: configparser.ConfigParser, cycle: str, lead_minutes: int) -> Path:
    return cycle_output_dir(config, cycle) / f"{cycle}.{lead_text(lead_minutes)}.nc"


def copy_nc(src: Path, dst: Path, overwrite: bool) -> bool:
    if not src.exists():
        print(f"[missing] {src}")
        return False
    if dst.exists() and not overwrite:
        print(f"[exists] {dst}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"[wrote] {dst} <- {src}")
    return True


def existing_positive_leads(config: configparser.ConfigParser, cycle: str) -> list[int]:
    folder = cycle_output_dir(config, cycle)
    leads: list[int] = []
    for path in folder.glob(f"{cycle}.*.nc"):
        parsed = parse_cycle_and_lead(path)
        if parsed is None:
            continue
        _, lead = parsed
        if lead >= 0:
            leads.append(lead)
    return sorted(set(leads))


def next_hour(value: dt.datetime) -> dt.datetime:
    base = value.replace(minute=0, second=0, microsecond=0)
    if value == base:
        return value
    return base + dt.timedelta(hours=1)


def pad_before_cycle(config: configparser.ConfigParser, cycle: str, step_minutes: int, overwrite: bool) -> None:
    cycle_time = parse_utc_minute(cycle)
    hour_start = cycle_time.replace(minute=0, second=0, microsecond=0)
    offset = int((cycle_time - hour_start).total_seconds() // 60)
    for back_minutes in range(offset, -1, -step_minutes):
        valid_time = cycle_time - dt.timedelta(minutes=back_minutes)
        lead = -back_minutes
        copy_nc(truth_path(config, valid_time), output_path(config, cycle, lead), overwrite)


def pad_after_cycle(config: configparser.ConfigParser, cycle: str, step_minutes: int, overwrite: bool) -> None:
    leads = existing_positive_leads(config, cycle)
    if not leads:
        print(f"[skip] no existing positive fusion leads for {cycle}")
        return
    last_lead = max(leads)
    cycle_time = parse_utc_minute(cycle)
    last_time = cycle_time + dt.timedelta(minutes=last_lead)
    target_end = next_hour(last_time)
    target_lead = int((target_end - cycle_time).total_seconds() // 60)
    for lead in range(last_lead + step_minutes, target_lead + 1, step_minutes):
        copy_nc(mait_path(config, cycle, lead), output_path(config, cycle, lead), overwrite)


def cycle_list(config: configparser.ConfigParser, args: argparse.Namespace, step_minutes: int) -> Iterable[str]:
    if len(args.history_range) == 2:
        return iter_history_cycles(args.history_range[0], args.history_range[1], step_minutes)
    return [latest_output_cycle(Path(config.get("paths", "output_dir")))]


def process(
    history_range=None,
    config=None,
    allowed_realtime_minutes=None,
    history_step_minutes=None,
    dry_run=None,
    max_files=None,
    source1_dir=None,
    source2_dir=None,
    truth_dir=None,
    output_dir=None,
    enabled=None,
    time_step_minutes=None,
    overwrite=None,
    blending_type=None,
    keyframe_weights=None,
    lon_min=None,
    lon_max=None,
    lat_min=None,
    lat_max=None,
    output_var=None,
    output_source=None,
) -> None:
    """融合结果补齐入口。``config`` 为空时读 ``resource/conf.ini``。

    其余参数对应 conf.ini。``None`` 不覆盖；空字符串会写入空值。
    """
    passed = locals()
    conf_options = {key: passed[key] for key in CONF_KEYS}
    config_path = Path(config) if config else Path(__file__).resolve().parents[1] / "resource" / "conf.ini"
    args = argparse.Namespace(history_range=list(history_range or []), config=config_path)
    loaded = read_config(config_path)
    apply_conf_overrides(loaded, **conf_options)
    if not loaded.getboolean("padding", "enabled", fallback=True):
        print("[skip] padding.enabled is false")
        return
    step_minutes = loaded.getint("padding", "time_step_minutes", fallback=10)
    overwrite = loaded.getboolean("padding", "overwrite", fallback=False)
    for cycle in cycle_list(loaded, args, step_minutes):
        print(f"[cycle] {cycle}")
        pad_before_cycle(loaded, cycle, step_minutes, overwrite)
        pad_after_cycle(loaded, cycle, step_minutes, overwrite)


def main() -> None:
    args = parse_args()
    process(history_range=args.history_range, config=args.config)


if __name__ == "__main__":
    main()
