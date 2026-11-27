from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


CST = timezone(timedelta(hours=8), name="CST")
UTC = timezone.utc


@dataclass(frozen=True)
class InitialTime:
    """输入数据采用的模式起报时间。"""

    year: int
    month: int
    day: int
    hour: int


@dataclass(frozen=True)
class TargetRun:
    """起报时间对应的 OTS 年份和 12 小时序号。"""

    initial_time: InitialTime
    business_initial_time: InitialTime
    input_time_zone: str
    this_year: int
    start_day: int


def is_leap_year(year: int) -> bool:
    """判断指定年份是否为闰年。"""
    if year % 4 != 0:
        return False
    if year % 100 != 0:
        return True
    return year % 400 == 0


def _to_datetime(value: InitialTime) -> datetime:
    """把自定义起报时间结构转换成 Python datetime。"""
    return datetime(value.year, value.month, value.day, value.hour)


def _from_datetime(value: datetime) -> InitialTime:
    """把 Python datetime 转换成自定义起报时间结构。"""
    return InitialTime(value.year, value.month, value.day, value.hour)


def add_hours(value: InitialTime, hours: int) -> InitialTime:
    """在起报时间上增减小时数。"""
    return _from_datetime(_to_datetime(value) + timedelta(hours=hours))


def _zone(time_zone: str) -> timezone:
    """返回配置名称对应的固定时区。"""
    return UTC if time_zone == "UTC" else CST


def _current_time(now: datetime | None, time_zone: str) -> datetime:
    """取得输入数据时区下的当前时间，并转为无时区时间。"""
    zone = _zone(time_zone)
    if now is None:
        return datetime.now(zone).replace(tzinfo=None)
    if now.tzinfo is not None:
        return now.astimezone(zone).replace(tzinfo=None)
    return now


def determine_initial_time(
    now: datetime | None = None,
    input_time_zone: str = "CST",
) -> InitialTime:
    """根据输入数据时区下的当前时间推导模式起报时间。"""
    current = _current_time(now, input_time_zone)
    initial = InitialTime(current.year, current.month, current.day, current.hour)

    if input_time_zone == "UTC":
        if initial.hour < 6:
            initial = InitialTime(initial.year, initial.month, initial.day, 12)
            return add_hours(initial, -24)
        if initial.hour < 18:
            return InitialTime(initial.year, initial.month, initial.day, 0)
        return InitialTime(initial.year, initial.month, initial.day, 12)

    if 2 <= initial.hour < 14:
        initial = InitialTime(initial.year, initial.month, initial.day, 20)
        return add_hours(initial, -24)
    if initial.hour >= 14:
        return InitialTime(initial.year, initial.month, initial.day, 8)

    initial = InitialTime(initial.year, initial.month, initial.day, 8)
    return add_hours(initial, -24)


def _from_exact_initial_time(value: datetime, input_time_zone: str) -> InitialTime:
    """校验并转换命令行直接指定的模式起报时间。"""
    if value.tzinfo is not None and value.utcoffset() is not None:
        raise ValueError("initial time must be a local datetime without a timezone offset")
    valid_hours = (0, 12) if input_time_zone == "UTC" else (8, 20)
    if value.hour not in valid_hours or value.minute != 0 or value.second != 0 or value.microsecond != 0:
        expected = "00:00 or 12:00" if input_time_zone == "UTC" else "08:00 or 20:00"
        raise ValueError(f"initial time must be exactly {expected} for {input_time_zone}")
    return InitialTime(value.year, value.month, value.day, value.hour)


def _convert_to_cst(value: InitialTime, input_time_zone: str) -> InitialTime:
    """把输入起报时间转换为原Fortran使用的CST业务时间。"""
    source = _to_datetime(value).replace(tzinfo=_zone(input_time_zone))
    return _from_datetime(source.astimezone(CST).replace(tzinfo=None))


def determine_target_run(
    now: datetime | None = None,
    *,
    initial_time: datetime | None = None,
    input_time_zone: str = "CST",
) -> TargetRun:
    """计算起报时间属于哪一年的第几个 12 小时时次。

    业务规则把上一年 12 月 31 日 20 时记为下一年序列的第 1 次起报。
    未指定 initial_time 时根据当前时间自动选时；指定后直接使用该起报时间。
    """
    if now is not None and initial_time is not None:
        raise ValueError("now and initial_time cannot be specified together")

    # 传入时间时等同于Fortran写死起报时间，不再执行自动选时。
    if initial_time is not None:
        initial = _from_exact_initial_time(initial_time, input_time_zone)
    else:
        # 未传时间时根据输入数据时区复现原Fortran的自动选时规则。
        initial = determine_initial_time(now, input_time_zone)

    business_initial = _convert_to_cst(initial, input_time_zone)

    if business_initial.month == 12 and business_initial.day == 31 and business_initial.hour == 20:
        return TargetRun(initial, business_initial, input_time_zone, business_initial.year + 1, 1)

    cursor = InitialTime(business_initial.year - 1, 12, 31, 20)
    for index in range(1, 735):
        if cursor == business_initial:
            return TargetRun(
                initial,
                business_initial,
                input_time_zone,
                business_initial.year,
                index,
            )
        cursor = add_hours(cursor, 12)

    raise ValueError(
        "could not map initial time "
        f"{initial.year:04d}-{initial.month:02d}-{initial.day:02d} {initial.hour:02d}:00 "
        "to a 12-hour sequence index"
    )


def half_days_in_year_for_renew(year: int) -> int:
    """返回一年包含的 12 小时时段数，业务规则中能被 4 整除即按闰年处理。"""
    return 732 if year % 4 == 0 else 730


def renew_day_730(year: int, day: int) -> tuple[int, int]:
    """把可能越界的半日序号归一化到正确年份和 1 起始序号。"""
    for _ in range(2):
        upper = half_days_in_year_for_renew(year)
        lower = half_days_in_year_for_renew(year - 1)
        if day > upper:
            year += 1
            day -= upper
        elif day <= 0:
            year -= 1
            day += lower
    return year, day
