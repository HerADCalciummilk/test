from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _current_time(now: datetime | None, time_zone: str) -> datetime:
    """取得指定时间口径下的当前时间，并转为供文件命名使用的无时区时间。"""
    zone = timezone.utc if time_zone == "UTC" else ZoneInfo("Asia/Shanghai")
    if now is None:
        return datetime.now(zone).replace(tzinfo=None)
    if now.tzinfo is not None:
        return now.astimezone(zone).replace(tzinfo=None)
    return now


def determine_initial_time(
    now: datetime | None = None,
    time_zone: str = "CST",
) -> datetime:
    """按原程序发布时间规则，确定需要处理的模式起报时间。"""
    current = _current_time(now, time_zone)

    if time_zone == "UTC":
        if current.hour < 6:
            return current.replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1)
        if current.hour < 18:
            return current.replace(hour=0, minute=0, second=0, microsecond=0)
        return current.replace(hour=12, minute=0, second=0, microsecond=0)

    if 2 <= current.hour < 14:
        return current.replace(hour=20, minute=0, second=0, microsecond=0) - timedelta(days=1)
    if current.hour >= 14:
        return current.replace(hour=8, minute=0, second=0, microsecond=0)
    return current.replace(hour=8, minute=0, second=0, microsecond=0) - timedelta(days=1)


def validate_initial_time(
    value: datetime,
    time_zone: str = "CST",
) -> datetime:
    """校验直接指定的模式起报时间是否符合所选时间口径。"""
    normalized = _current_time(value, time_zone)
    valid_hours = (0, 12) if time_zone == "UTC" else (8, 20)
    if (
        normalized.hour not in valid_hours
        or normalized.minute
        or normalized.second
        or normalized.microsecond
    ):
        hours_text = "00:00 或 12:00" if time_zone == "UTC" else "08:00 或 20:00"
        raise ValueError(f"模式起报时间必须是整点的 {hours_text}")
    return normalized


def convert_initial_time(
    value: datetime,
    source_time_zone: str,
    target_time_zone: str,
) -> datetime:
    """把同一模式起报时刻在UTC和中国标准时间之间转换。"""
    source_zone = timezone.utc if source_time_zone == "UTC" else ZoneInfo("Asia/Shanghai")
    target_zone = timezone.utc if target_time_zone == "UTC" else ZoneInfo("Asia/Shanghai")
    source_time = value.replace(tzinfo=source_zone)
    return source_time.astimezone(target_zone).replace(tzinfo=None)
