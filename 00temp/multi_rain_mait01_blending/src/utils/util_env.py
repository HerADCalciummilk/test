# -*- coding: utf-8 -*-
"""
MAIT 1H 运行参数（``src/utils/util_env.py``）

**统一从仓库内** ``resource/mait_1.ini`` **读取**路径与默认运行项（对齐 mait_24h 的 ``mait_24.ini``，不再按操作系统加载 ``envs/*.env``）。

``mait_1.ini`` 常用键（``key=value``，每行一条，``#`` / ``;`` 开头为注释）：

- ``log_file`` — 日志路径模板（如 ``log/YYYYMMDD.txt``）
- ``para_ini`` — ``local.ini``（本地开发默认；生产可用 ``para_1.ini``）
- ``background_ini`` — ``local_background.ini``（本地开发默认；生产可用 ``para_1_background.ini``）
- ``beta_path_template`` / ``bate_file`` — beta 目录模板
- ``station_info``、``mask_dat``（亦接受 ``mask_nc`` 键名，值仍指向 .dat 掩膜）
- ``clip_coords`` — 六个浮点逗号分隔
- ``predict_valid_list`` — 预报时效（小时）逗号分隔
- ``is_obs_bj`` — 实况是否北京时间（兼容 ``is_obs_bjt``）
- ``is_multi``、``pro_count``、``split_lat``
- ``split_lon`` — 亦可写 ``split_lin``

若 ``resource/mait_1.ini`` 不存在或某键缺失，则使用该键在代码内的硬编码默认值。

``get_resolved_paths`` / 各 ``get_default_*`` 在首次调用时读取并缓存 ini；修改 ini 后需重新启动进程生效。
"""
import os
from typing import Any, Dict, List, Optional

_UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_UTIL_DIR))

_MAIN_INI_REL = os.path.join("resource", "mait_1.ini")

_DEFAULT_CLIP_COORDS = (70.0, 140.0, 0.0, 60.0, 0.1, 0.1)
_DEFAULT_PREDICT_VALID = tuple(range(1, 48 + 1, 1))

_RAW_INI_CACHE: Optional[Dict[str, str]] = None


def _abspath(p: str) -> str:
    return os.path.normpath(os.path.abspath(os.path.expanduser(p.strip())))


def _expand_path_maybe_relative_to_repo(p: str) -> str:
    """绝对路径照旧；否则视为相对仓库根的相对路径。"""
    s = p.strip()
    if not s:
        return s
    exp = os.path.expanduser(s)
    if os.path.isabs(exp):
        return _abspath(exp)
    return _abspath(os.path.join(_REPO_ROOT, os.path.normpath(exp)))


def _main_ini_abs_path() -> str:
    return _abspath(os.path.join(_REPO_ROOT, os.path.normpath(_MAIN_INI_REL)))


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
                k = k.strip().lower()
                if k:
                    out[k] = v.strip()
    except OSError:
        return {}
    return out


def _get_raw_ini() -> Dict[str, str]:
    global _RAW_INI_CACHE
    if _RAW_INI_CACHE is not None:
        return _RAW_INI_CACHE
    path = _main_ini_abs_path()
    if os.path.isfile(path):
        _RAW_INI_CACHE = _parse_kv_ini(path)
    else:
        _RAW_INI_CACHE = {}
    return _RAW_INI_CACHE


def _defaults_paths_resolved() -> Dict[str, str]:
    """与示例 ``resource/mait_1.ini`` 一致的默认路径（均为绝对路径）。"""
    return {
        "log_file_template": _expand_path_maybe_relative_to_repo("log/YYYYMMDD.txt"),
        "para_ini": _expand_path_maybe_relative_to_repo("resource/local.ini"),
        "background_ini": _expand_path_maybe_relative_to_repo("resource/local_background.ini"),
        "beta_path_template": _expand_path_maybe_relative_to_repo("beta_1h/YYYYMMDDHH"),
        "station_info": _expand_path_maybe_relative_to_repo("resource/sta.info"),
        "mask_dat": _expand_path_maybe_relative_to_repo("resource/mask010.dat"),
    }


def _raw_path(key: str) -> Optional[str]:
    raw = _get_raw_ini()
    v = raw.get(key.lower())
    if v is None or not str(v).strip():
        return None
    return str(v).strip()


def _parse_bool(s: Optional[str], *, default: bool) -> bool:
    if s is None:
        return default
    t = s.strip().lower()
    if t in ("1", "true", "yes", "y", "on"):
        return True
    if t in ("0", "false", "no", "n", "off"):
        return False
    return default


def _parse_int_opt(s: Optional[str], *, default: int) -> int:
    if s is None:
        return default
    try:
        return int(str(s).strip())
    except ValueError:
        return default


def get_resolved_paths() -> Dict[str, Any]:
    """
    路径字典（绝对路径）。

    键：``log_file_template``、``para_ini``、``background_ini``、``beta_path_template``、
    ``station_info``、``mask_dat``。
    """
    base = _defaults_paths_resolved().copy()

    lf = _raw_path("log_file")
    if lf:
        base["log_file_template"] = _expand_path_maybe_relative_to_repo(lf)

    pi = _raw_path("para_ini")
    if pi:
        base["para_ini"] = _expand_path_maybe_relative_to_repo(pi)

    bg = _raw_path("background_ini")
    if bg:
        base["background_ini"] = _expand_path_maybe_relative_to_repo(bg)

    beta = _raw_path("beta_path_template") or _raw_path("bate_file") or _raw_path("beta_file")
    if beta:
        base["beta_path_template"] = _expand_path_maybe_relative_to_repo(beta)

    st = _raw_path("station_info")
    if st:
        base["station_info"] = _expand_path_maybe_relative_to_repo(st)

    mk = _raw_path("mask_dat") or _raw_path("mask_nc")
    if mk:
        base["mask_dat"] = _expand_path_maybe_relative_to_repo(mk)

    return base


def get_default_clip_coords() -> List[float]:
    """``clip_coords``；缺省或无效时六个常量。"""
    raw = _get_raw_ini().get("clip_coords")
    if not raw:
        return list(_DEFAULT_CLIP_COORDS)
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    if len(parts) != 6:
        return list(_DEFAULT_CLIP_COORDS)
    try:
        return [float(x) for x in parts]
    except ValueError:
        return list(_DEFAULT_CLIP_COORDS)


def get_default_predict_valid_list() -> List[int]:
    raw = _get_raw_ini().get("predict_valid_list")
    if not raw:
        return list(_DEFAULT_PREDICT_VALID)
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    try:
        return [int(x) for x in parts]
    except ValueError:
        return list(_DEFAULT_PREDICT_VALID)


def get_default_is_obs_bjt() -> bool:
    raw = _get_raw_ini().get("is_obs_bjt") or _get_raw_ini().get("is_obs_bj")
    return _parse_bool(raw, default=True)


def get_default_is_multi() -> bool:
    return _parse_bool(_get_raw_ini().get("is_multi"), default=False)


def get_default_pro_count() -> int:
    return _parse_int_opt(_get_raw_ini().get("pro_count"), default=4)


def get_default_split_lat() -> int:
    return _parse_int_opt(_get_raw_ini().get("split_lat"), default=1)


def get_default_split_lon() -> int:
    raw = _get_raw_ini()
    return _parse_int_opt(raw.get("split_lon") or raw.get("split_lin"), default=1)
