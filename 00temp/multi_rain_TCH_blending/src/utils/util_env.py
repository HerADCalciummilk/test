# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 TCH 实时集成的运行参数。

取值优先级由调用方保证：显式参数 > 本 ini 非空项 > ``PRESET``。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Union

_UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_UTIL_DIR))
_MAIN_INI_REL = os.path.join("resource", "conf.ini")
_RAW_INI_CACHE: Optional[Dict[str, str]] = None
_CONFIG_OVERRIDE: Optional[str] = None
_CONFIG_ENV = "NIMM_PRE_FCST_TCH_REALTIME_INI"

# 代码预设。与 resource/conf.ini 的当前取值一致。
PRESET: Dict[str, Any] = {
    "maskout_file": "E:/work/Data/by_type/maskout/maskout_cn_0.1_2.dat",
    "nx_mask": 701,
    "ny_mask": 601,
    "dir_model_data": "//10.20.90.107/sm_qpf/v2021/rain24/",
    "dir_tch_output": "//10.20.90.107/sm_qpf/v2021/rain24/tch/sfc/",
    # 模式降水输入格式：nc（默认）或 m4
    "ipt_type": "nc",
    "model_list": [
        "ecmwf",
        "german_gfs_hr",
        "ncep_gfs_hr",
        "grapes_3km",
        "beijing_mr",
        "guangzhou_mr",
        "shanghai_mr",
    ],
    "grid_lon": [70.0, 140.0, 0.10],
    "grid_lat": [0.0, 60.0, 0.10],
    "fcst_hours": [36, 60, 84],
    "station_level": 600,
    "bjt_offset_hours": 8,
    "initial_hour_threshold": 12,
    "initial_hour_late": 0,
    "initial_hour_early": 12,
    "initial_time": None,
}


def _abspath(p: str) -> str:
    return os.path.normpath(os.path.abspath(os.path.expanduser(p.strip())))


def _expand_path_maybe_relative_to_repo(p: str) -> str:
    s = (p or "").strip()
    if not s:
        return s
    exp = os.path.expanduser(s)
    if os.path.isabs(exp):
        return _abspath(exp)
    return _abspath(os.path.join(_REPO_ROOT, os.path.normpath(exp)))


def _default_ini_abs_path() -> str:
    return _abspath(os.path.join(_REPO_ROOT, os.path.normpath(_MAIN_INI_REL)))


def _main_ini_abs_path() -> str:
    if _CONFIG_OVERRIDE:
        return _CONFIG_OVERRIDE
    env_path = os.environ.get(_CONFIG_ENV, "").strip()
    if env_path:
        return env_path
    return _default_ini_abs_path()


def set_main_ini(path: Optional[str] = None) -> str:
    """切换运行配置 ini，并清空缓存。

    ``path`` 为空时回到 ``resource/conf.ini``。
    相对路径按本包根目录解析。文件不存在时抛出 FileNotFoundError。
    """
    global _CONFIG_OVERRIDE, _RAW_INI_CACHE
    if path is None or not str(path).strip():
        _CONFIG_OVERRIDE = None
        os.environ.pop(_CONFIG_ENV, None)
        chosen = _default_ini_abs_path()
    else:
        chosen = _expand_path_maybe_relative_to_repo(str(path))
        if not os.path.isfile(chosen):
            raise FileNotFoundError(f"配置文件不存在: {chosen}")
        _CONFIG_OVERRIDE = chosen
        os.environ[_CONFIG_ENV] = chosen
    _RAW_INI_CACHE = None
    return chosen


def _parse_kv_ini(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or s.startswith(";"):
                    continue
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k and v:
                    out[k] = v
    except OSError:
        return {}
    return out


def _get_raw_ini() -> Dict[str, str]:
    global _RAW_INI_CACHE
    if _RAW_INI_CACHE is None:
        _RAW_INI_CACHE = _parse_kv_ini(_main_ini_abs_path())
    return _RAW_INI_CACHE


def _ini_get(key: str) -> str:
    return _get_raw_ini().get(key, "")


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return True
    return False


def _as_str_list(value: Union[str, Sequence[str]]) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _as_float_list(value: Union[str, Sequence]) -> List[float]:
    return [float(item) for item in _as_str_list(value)]


def _as_int_list(value: Union[str, Sequence]) -> List[int]:
    return [int(float(item)) for item in _as_str_list(value)]


def _with_trailing_slash(path: str) -> str:
    if path.endswith(("/", "\\")):
        return path
    return path + "/"


def _pick_text(name: str, explicit: Any, preset: Any) -> str:
    if not _missing(explicit):
        return str(explicit).strip()
    raw = _ini_get(name)
    if raw:
        return raw
    return "" if preset is None else str(preset)


def _pick_int(name: str, explicit: Any, preset: int) -> int:
    if not _missing(explicit):
        return int(explicit)
    raw = _ini_get(name)
    if raw:
        return int(float(raw))
    return int(preset)


def _pick_path(name: str, explicit: Any, preset: str, *, slash: bool = False) -> str:
    chosen = _pick_text(name, explicit, preset)
    chosen = _expand_path_maybe_relative_to_repo(chosen)
    if slash:
        chosen = _with_trailing_slash(chosen)
    return chosen


def _pick_str_list(name: str, explicit: Any, preset: Sequence[str]) -> List[str]:
    if not _missing(explicit):
        return _as_str_list(explicit)
    raw = _ini_get(name)
    if raw:
        return _as_str_list(raw)
    return [str(item) for item in preset]


def _pick_float_list(name: str, explicit: Any, preset: Sequence[float], n: int) -> List[float]:
    if not _missing(explicit):
        vals = _as_float_list(explicit)
    else:
        raw = _ini_get(name)
        vals = _as_float_list(raw) if raw else [float(item) for item in preset]
    if len(vals) != n:
        raise ValueError(f"{name} 需要 {n} 个数，实际为 {vals}")
    return vals


def _pick_int_list(name: str, explicit: Any, preset: Sequence[int]) -> List[int]:
    if not _missing(explicit):
        vals = _as_int_list(explicit)
    else:
        raw = _ini_get(name)
        vals = _as_int_list(raw) if raw else [int(item) for item in preset]
    if not vals:
        raise ValueError(f"{name} 不能为空")
    return vals


def _normalize_ipt_type(value: Any) -> str:
    text = str(value or "nc").strip().lower()
    if text in ("nc", "netcdf", "netcdf4"):
        return "nc"
    if text in ("m4", "micaps4", "diamond4"):
        return "m4"
    raise ValueError("ipt_type 仅支持 nc / m4，收到: %r" % (value,))


def resolve_process_args(
    maskout_file: Optional[str] = None,
    nx_mask: Optional[int] = None,
    ny_mask: Optional[int] = None,
    dir_model_data: Optional[str] = None,
    dir_tch_output: Optional[str] = None,
    ipt_type: Optional[str] = None,
    model_list: Union[str, Sequence[str], None] = None,
    grid_lon: Union[str, Sequence, None] = None,
    grid_lat: Union[str, Sequence, None] = None,
    fcst_hours: Union[str, Sequence, None] = None,
    station_level: Optional[int] = None,
    bjt_offset_hours: Optional[int] = None,
    initial_hour_threshold: Optional[int] = None,
    initial_hour_late: Optional[int] = None,
    initial_hour_early: Optional[int] = None,
    initial_time: Optional[str] = None,
) -> Dict[str, Any]:
    """显式参数优先，否则用 ini 非空项，再否则用 ``PRESET``。"""
    initial = _pick_text("initial_time", initial_time, PRESET["initial_time"])
    ipt = _normalize_ipt_type(_pick_text("ipt_type", ipt_type, PRESET["ipt_type"]))
    return {
        "maskout_file": _pick_path("maskout_file", maskout_file, PRESET["maskout_file"]),
        "nx_mask": _pick_int("nx_mask", nx_mask, PRESET["nx_mask"]),
        "ny_mask": _pick_int("ny_mask", ny_mask, PRESET["ny_mask"]),
        "dir_model_data": _pick_path(
            "dir_model_data", dir_model_data, PRESET["dir_model_data"], slash=True
        ),
        "dir_tch_output": _pick_path(
            "dir_tch_output", dir_tch_output, PRESET["dir_tch_output"], slash=True
        ),
        "ipt_type": ipt,
        "model_list": _pick_str_list("model_list", model_list, PRESET["model_list"]),
        "grid_lon": _pick_float_list("grid_lon", grid_lon, PRESET["grid_lon"], 3),
        "grid_lat": _pick_float_list("grid_lat", grid_lat, PRESET["grid_lat"], 3),
        "fcst_hours": _pick_int_list("fcst_hours", fcst_hours, PRESET["fcst_hours"]),
        "station_level": _pick_int("station_level", station_level, PRESET["station_level"]),
        "bjt_offset_hours": _pick_int(
            "bjt_offset_hours", bjt_offset_hours, PRESET["bjt_offset_hours"]
        ),
        "initial_hour_threshold": _pick_int(
            "initial_hour_threshold",
            initial_hour_threshold,
            PRESET["initial_hour_threshold"],
        ),
        "initial_hour_late": _pick_int(
            "initial_hour_late", initial_hour_late, PRESET["initial_hour_late"]
        ),
        "initial_hour_early": _pick_int(
            "initial_hour_early", initial_hour_early, PRESET["initial_hour_early"]
        ),
        "initial_time": initial or None,
    }


def clear_ini_cache() -> None:
    """测试用：清空 ini 缓存。"""
    global _RAW_INI_CACHE
    _RAW_INI_CACHE = None
