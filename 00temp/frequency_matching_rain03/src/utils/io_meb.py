# -*- coding: utf-8 -*-
"""路径展开与 Micaps I/O：直接用 ``meteva_base``。

写出约定（与 mait 等包一致）：
- ``.m3``：组 ``sta_data``，交给 ``meb.write_stadata_to_micaps3``
- ``.m4`` / ``.nc``：组 ``grid_data``，交给对应 write

读 ``.m4``：先 ``meb.read_griddata_from_micaps4``，再与原版手写拆词对齐。
业务文件 ``lat 60→0, dlat=-0.1`` 上 meb+reset 可能相对原版南北颠倒
（``max|orig-nimm[::-1]|≈0``），``align_meb_grid_to_original`` 负责翻回。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable, Optional, Sequence, Tuple

import numpy as np

try:
    import meteva_base as meb
except ImportError as exc:
    raise ImportError("未安装 meteva_base，请先执行: pip install meteva_base") from exc


GRID_SUFFIXES = (".m4", ".nc")
STA_SUFFIXES = (".m3",)


def expand_data_path(template: str, dt_input: datetime, i_valid: int = 0) -> str:
    """``VVV`` 换成 ``TTT`` 后 ``meb.get_path``。"""
    tpl = str(template).replace("VVV", "TTT").replace("VV", "TT")
    return meb.get_path(tpl, dt_input, i_valid)


def resolve_existing_path(
    path: str,
    suffixes: Sequence[str] = GRID_SUFFIXES + STA_SUFFIXES,
) -> Optional[str]:
    """已存在则返回：原路径 → 追加后缀 → 去掉已有后缀。"""
    if not path:
        return None
    if os.path.isfile(path):
        return path
    for suffix in suffixes:
        candidate = path + suffix
        if os.path.isfile(candidate):
            return candidate
    root, ext = os.path.splitext(path)
    if ext and os.path.isfile(root):
        return root
    return None


def find_grid_file(template: str, dt_input: datetime, i_valid: int = 0) -> Tuple[str, Optional[str]]:
    raw = expand_data_path(template, dt_input, i_valid)
    return raw, resolve_existing_path(raw, GRID_SUFFIXES)


def find_sta_file(template: str, dt_input: datetime, i_valid: int = 0) -> Tuple[str, Optional[str]]:
    raw = expand_data_path(template, dt_input, i_valid)
    return raw, resolve_existing_path(raw, STA_SUFFIXES)


def norm_sta_id(value) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        try:
            return str(int(float(text)))
        except Exception:
            pass
    return text


def read_stadata_rows(path: str) -> list:
    sta = meb.read_stadata_from_micaps3(path)
    if sta is None:
        raise RuntimeError(f"meb.read_stadata_from_micaps3 失败: {path}")
    data_col = sta.columns[-1]
    rows = []
    for _, row in sta.iterrows():
        rows.append((
            norm_sta_id(row["id"]),
            float(row["lon"]),
            float(row["lat"]),
            float(row[data_col]),
        ))
    return rows


def _micaps4_tokens(path: str):
    try:
        encoding, text = meb.io.get_encoding_of_file(path)
    except Exception:
        encoding, text = None, None
    if encoding is None or text is None:
        raw = open(path, "rb").read()
        text = None
        for enc in ("gb2312", "gbk", "utf-8", "gb18030"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            return None
    if isinstance(text, list):
        text = " ".join(text)
    return str(text).replace(",", "").split()


def parse_micaps4_like_original(path: str) -> Optional[dict]:
    """与原版 ``GridData._read_val_from_micaps4`` 相同的拆词与南北处理。"""
    tokens = _micaps4_tokens(path)
    if not tokens or len(tokens) < 23:
        return None
    try:
        dlon = abs(float(tokens[9]))
        dlat = abs(float(tokens[10]))
        slon, elon = float(tokens[11]), float(tokens[12])
        slat, elat = float(tokens[13]), float(tokens[14])
        xn = int(float(tokens[15]))
        yn = int(float(tokens[16]))
    except (TypeError, ValueError, IndexError):
        return None
    if xn <= 0 or yn <= 0 or len(tokens) - 22 < xn * yn:
        return None
    lon0 = slon if slon < elon else elon
    lat0 = slat if slat < elat else elat
    data = np.array(tokens[22:22 + xn * yn], dtype=np.float64).reshape((yn, xn))
    if slat >= elat:
        data = data[::-1].copy()
    return {
        "dlon": dlon,
        "dlat": dlat,
        "lon0": lon0,
        "lat0": lat0,
        "xn": xn,
        "yn": yn,
        "val": data,
    }


def read_griddata_from_micaps4(path: str):
    """``meb.read_griddata_from_micaps4``；失败返回 ``None``。"""
    return meb.read_griddata_from_micaps4(path)


def align_meb_grid_to_original(val: np.ndarray, path: str) -> np.ndarray:
    """若 meb 场相对原版只是南北颠倒，则翻行；否则必要时改用原版场。"""
    parsed = parse_micaps4_like_original(path)
    if parsed is None or val.shape != parsed["val"].shape:
        return val
    orig = parsed["val"]
    diff = float(np.max(np.abs(val - orig)))
    if diff <= 1e-4:
        return val
    flipped = val[::-1]
    diff_flip = float(np.max(np.abs(flipped - orig)))
    if diff_flip < diff and diff_flip <= 1e-3:
        return flipped.copy()
    return orig.copy()


def write_stadata_m3(
    ids: Iterable,
    lons: Iterable,
    lats: Iterable,
    vals: Iterable,
    path: str,
    dt_input: Optional[datetime] = None,
    i_valid: int = 0,
    title: Optional[str] = None,
) -> None:
    """组 ``sta_data`` 后 ``meb.write_stadata_to_micaps3``。"""
    import pandas as pd
    id_list = []
    for item in ids:
        try:
            id_list.append(int(item))
        except Exception:
            id_list.append(item)
    sta = meb.sta_data(pd.DataFrame({
        "id": id_list,
        "lon": list(lons),
        "lat": list(lats),
        "data0": list(vals),
    }))
    if dt_input is not None:
        meb.set_stadata_coords(sta, time=dt_input, dtime=int(i_valid))
    kwargs = {"save_path": path, "effectiveNum": 2, "creat_dir": True}
    if title:
        kwargs["title"] = title
    meb.write_stadata_to_micaps3(sta, **kwargs)
