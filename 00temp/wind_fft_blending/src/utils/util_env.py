# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取运行参数与算法常量。

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
_CONFIG_ENV = "NIMM_WIND_FFT_BLENDING_INI"

# 代码预设。ini 缺键或值为空时使用。
PRESET: Dict[str, Any] = {
    "output_dir": "resource/output",
    "output_prefix": "fft_merge",
    "feature_border": 128,
    "max_iterations": 1024,
    "move_percent": 1.0,
    "write_linear_compare": True,
    "is_multi": False,
    "pro_count": 4,
    "weight_value": 0.1,
    "power_model": 2,
    "l_scale": 1,
    "reflect_pad": 25,
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
    相对路径按项目根目录解析。文件不存在时抛出 FileNotFoundError。
    同时写入环境变量，供多进程子进程继承同一 ini。
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
    """简单 key=value ini（#/; 注释，忽略空行）。"""
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
                k = k.strip().lower()
                if k:
                    out[k] = v.strip()
    except OSError:
        return {}
    return out


def _get_raw_ini() -> Dict[str, str]:
    global _RAW_INI_CACHE
    if _RAW_INI_CACHE is None:
        _RAW_INI_CACHE = _parse_kv_ini(_main_ini_abs_path())
    return _RAW_INI_CACHE


def clear_ini_cache() -> None:
    """测试用：清空 ini 缓存。"""
    global _RAW_INI_CACHE
    _RAW_INI_CACHE = None


def get_repo_root() -> str:
    """本包根目录（``wind_fft_blending/``）。"""
    return _REPO_ROOT


def _raw(key: str) -> Optional[str]:
    """ini 中的原始字符串；缺键或空白返回 None。"""
    if key.lower() not in _get_raw_ini():
        return None
    v = _get_raw_ini()[key.lower()].strip()
    return v or None


def _opt_int(key: str, preset: int) -> int:
    v = _raw(key)
    return preset if v is None else int(v)


def _opt_float(key: str, preset: float) -> float:
    v = _raw(key)
    return preset if v is None else float(v)


def _opt_bool(key: str, preset: bool) -> bool:
    v = _raw(key)
    if v is None:
        return preset
    t = v.lower()
    if t in ("1", "true", "yes", "y", "on"):
        return True
    if t in ("0", "false", "no", "n", "off"):
        return False
    return preset


def _split_list(key: str) -> List[str]:
    v = _raw(key)
    if not v:
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


def _split_first(*keys: str) -> List[str]:
    for key in keys:
        items = _split_list(key)
        if items:
            return items
    return []


def get_algo_constants() -> Dict[str, Any]:
    """算法常量。ini 缺键时用 ``PRESET``。显式传参由 ``resolve_process_args`` 覆盖。"""
    return {
        "weight_value": _opt_float("weight_value", float(PRESET["weight_value"])),
        "power_model": _opt_int("power_model", int(PRESET["power_model"])),
        "l_scale": _opt_int("l_scale", int(PRESET["l_scale"])),
        "reflect_pad": _opt_int("reflect_pad", int(PRESET["reflect_pad"])),
    }


def get_run_defaults() -> Dict[str, Any]:
    """ini 覆盖后的运行默认值。路径已展开为绝对路径；空的输入路径保持空列表。"""
    prefixes = _split_list("output_prefix") or [str(PRESET["output_prefix"])]
    out_rel = _raw("output_dir") or str(PRESET["output_dir"])
    return {
        "main_uv": [
            _expand_path_maybe_relative_to_repo(p)
            for p in _split_first("main_uv_path", "main_uv")
        ],
        "ass_uv": [
            _expand_path_maybe_relative_to_repo(p)
            for p in _split_first("ass_uv_path", "ass_uv")
        ],
        "output_dir": _expand_path_maybe_relative_to_repo(out_rel),
        "output_prefix": prefixes,
        "feature_border": _opt_int("feature_border", int(PRESET["feature_border"])),
        "max_iterations": _opt_int("max_iterations", int(PRESET["max_iterations"])),
        "move_percent": _opt_float("move_percent", float(PRESET["move_percent"])),
        "write_linear_compare": _opt_bool(
            "write_linear_compare", bool(PRESET["write_linear_compare"])
        ),
        "is_multi": _opt_bool("is_multi", bool(PRESET["is_multi"])),
        "pro_count": _opt_int("pro_count", int(PRESET["pro_count"])),
    }


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return True
    return False


def _one_or_many(items: Sequence[str]) -> Union[str, List[str]]:
    vals = [str(x) for x in items]
    if len(vals) == 1:
        return vals[0]
    return vals


def resolve_process_args(
    main_uv_path: Union[str, Sequence[str], None] = None,
    ass_uv_path: Union[str, Sequence, None] = None,
    output_dir: Optional[str] = None,
    output_prefix: Union[str, Sequence[str], None] = None,
    feature_border: Optional[int] = None,
    max_iterations: Optional[int] = None,
    move_percent: Optional[float] = None,
    write_linear_compare: Optional[bool] = None,
    is_multi: Optional[bool] = None,
    pro_count: Optional[int] = None,
    weight_value: Optional[float] = None,
    power_model: Optional[int] = None,
    l_scale: Optional[int] = None,
    reflect_pad: Optional[int] = None,
) -> Dict[str, Any]:
    """显式参数优先，否则用 ini，再否则用 ``PRESET``。

    ``main_uv_path`` / ``ass_uv_path`` 在显式参数和 ini 都为空时抛出 ``ValueError``。
    """
    cfg = get_run_defaults()
    consts = get_algo_constants()
    if _missing(main_uv_path):
        if not cfg["main_uv"]:
            raise ValueError(
                "main_uv_path 未显式传入，且 resource/conf.ini 的 main_uv_path 为空"
            )
        main_uv_path = _one_or_many(cfg["main_uv"])
    if _missing(ass_uv_path):
        if not cfg["ass_uv"]:
            raise ValueError(
                "ass_uv_path 未显式传入，且 resource/conf.ini 的 ass_uv_path 为空"
            )
        ass_uv_path = _one_or_many(cfg["ass_uv"])
    if _missing(output_dir):
        output_dir = cfg["output_dir"]
    if _missing(output_prefix):
        output_prefix = _one_or_many(cfg["output_prefix"])
    return {
        "main_uv_path": main_uv_path,
        "ass_uv_path": ass_uv_path,
        "output_dir": output_dir,
        "output_prefix": output_prefix,
        "feature_border": int(cfg["feature_border"] if feature_border is None else feature_border),
        "max_iterations": int(cfg["max_iterations"] if max_iterations is None else max_iterations),
        "move_percent": float(cfg["move_percent"] if move_percent is None else move_percent),
        "write_linear_compare": (
            cfg["write_linear_compare"] if write_linear_compare is None else bool(write_linear_compare)
        ),
        "is_multi": cfg["is_multi"] if is_multi is None else bool(is_multi),
        "pro_count": int(cfg["pro_count"] if pro_count is None else pro_count),
        "weight_value": float(consts["weight_value"] if weight_value is None else weight_value),
        "power_model": int(consts["power_model"] if power_model is None else power_model),
        "l_scale": int(consts["l_scale"] if l_scale is None else l_scale),
        "reflect_pad": int(consts["reflect_pad"] if reflect_pad is None else reflect_pad),
    }
