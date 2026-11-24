# -*- coding: utf-8 -*-
"""用 ``resource/sample`` 对比 ``InterpSgCressman`` 两条路径。

默认数据::

    resource/sample/2026052400.036.m4   # 格点背景
    resource/sample/26052520.000        # 站点实况

1. ``reprocess=False``：km 核绝对值 + ``background``
2. ``reprocess=True``：差值累加再处理

运行::

    python test/compare_plugin_vs_interp_sg.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
_SAMPLE = _ROOT / "resource" / "sample"
_OUT = _ROOT / "resource" / "compare_out"
_TEMP = _ROOT.parent
_GG_ROOT = _TEMP / "interpolation_grid_grid"
_GG_SRC = _GG_ROOT / "src"
_PATH_PREFIX = [str(_SRC), str(_ROOT), str(_GG_ROOT), str(_GG_SRC)]
sys.path[:0] = [p for p in _PATH_PREFIX if p not in sys.path]

import meteva.base as meb
import meteva_base

from interp_sg_cressman_plugin import DEFAULT_R_LIST_DEG, InterpSgCressman

_DEFAULT_M4 = _SAMPLE / "2026052400.036.m4"
_DEFAULT_STA = _SAMPLE / "26052520.000"

# 裁一块加速（全国 0.1° 太慢）；可按需要改
_CLIP = (100.0, 125.0, 20.0, 45.0)  # lonmin, lonmax, latmin, latmax
_R_DEG = list(DEFAULT_R_LIST_DEG)  # 0.8,0.6,0.4,0.2 一类
_KM_PER_DEG = float(getattr(meteva_base.basicdata.const, "ER", 6371.229)) * math.pi / 180.0
_NEAR = 100
_UNDEF = 9999.0


def _arr(g) -> np.ndarray:
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def _stats(a: np.ndarray, b: np.ndarray) -> dict:
    mask = np.isfinite(a) & np.isfinite(b)
    n = int(mask.sum())
    if n < 2:
        return {"n": n, "mae": np.nan, "rmse": np.nan, "max_abs": np.nan, "corr": np.nan}
    da, db = a[mask], b[mask]
    diff = da - db
    # 手工相关，避开个别环境 corrcoef 崩进程
    da0, db0 = da - da.mean(), db - db.mean()
    denom = float(np.sqrt(np.dot(da0, da0) * np.dot(db0, db0)))
    corr = float(np.dot(da0, db0) / denom) if denom > 0 else float("nan")
    return {
        "n": n,
        "mae": float(np.mean(np.abs(diff))),
        "rmse": float(np.sqrt(np.mean(diff * diff))),
        "max_abs": float(np.max(np.abs(diff))),
        "corr": corr,
    }


def _clip_grd(grd, clip):
    """按经纬度范围裁格点（不用 sele_by_para，避免 DataArray 布尔索引坑）。"""
    lon0, lon1, lat0, lat1 = clip
    lon = np.asarray(grd.lon.values, float)
    lat = np.asarray(grd.lat.values, float)
    ix = np.where((lon >= lon0) & (lon <= lon1))[0]
    iy = np.where((lat >= lat0) & (lat <= lat1))[0]
    if ix.size < 2 or iy.size < 2:
        raise ValueError("裁剪后格点过少: lon=%s lat=%s" % (ix.size, iy.size))
    slon, elon = float(lon[ix[0]]), float(lon[ix[-1]])
    slat, elat = float(lat[iy[0]]), float(lat[iy[-1]])
    dlon = float(lon[1] - lon[0]) if lon.size > 1 else 0.1
    dlat = float(lat[1] - lat[0]) if lat.size > 1 else 0.1
    grid = meb.grid([slon, elon, dlon], [slat, elat, dlat])
    dat = _arr(grd)[iy[0] : iy[-1] + 1, ix[0] : ix[-1] + 1]
    out = meb.grid_data(grid)
    out.data = [[[[dat]]]]
    return out


def _clean_sta(sta, clip):
    lon0, lon1, lat0, lat1 = clip
    out = sta.copy()
    val = np.asarray(out["data0"], float)
    out = out.loc[(val < _UNDEF * 0.5) & np.isfinite(val)].copy()
    out = out.loc[
        (out["lon"] >= lon0)
        & (out["lon"] <= lon1)
        & (out["lat"] >= lat0)
        & (out["lat"] <= lat1)
    ].copy()
    out = out.reset_index(drop=True)
    return out


def _r_km_from_deg(r_deg):
    return [float(r) * _KM_PER_DEG * 1000.0 for r in r_deg]


def _to_rgb_blues(data, vmax):
    z = np.asarray(data, dtype=float)
    t = np.clip(np.where(np.isfinite(z), z / max(vmax, 1e-6), 0.0), 0.0, 1.0)
    r = (255 * (1.0 - 0.85 * t)).astype(np.uint8)
    g = (255 * (1.0 - 0.55 * t)).astype(np.uint8)
    b = (255 * (1.0 - 0.10 * t)).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def _to_rgb_rdbu(data, dmax):
    z = np.asarray(data, dtype=float)
    t = np.clip(np.where(np.isfinite(z), z / max(dmax, 1e-6), 0.0), -1.0, 1.0)
    r = np.ones_like(t)
    g = np.ones_like(t)
    b = np.ones_like(t)
    pos, neg = t > 0, t < 0
    g[pos] = 1.0 - t[pos]
    b[pos] = 1.0 - t[pos]
    r[neg] = 1.0 + t[neg]
    g[neg] = 1.0 + t[neg]
    return np.stack(
        [(255 * r).astype(np.uint8), (255 * g).astype(np.uint8), (255 * b).astype(np.uint8)],
        axis=-1,
    )


def _panel(rgb, title, w=480, h=400):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.fromarray(np.flipud(rgb), mode="RGB").resize((w, h - 28), Image.BILINEAR)
    canvas = Image.new("RGB", (w, h), (255, 255, 255))
    canvas.paste(img, (0, 28))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((6, 6), title, fill=(20, 20, 20), font=font)
    return canvas


def _save_pair_figure(bg, a_interp, c_plugin, out_png: Path):
    """三张：背景 | interp_sg | plugin(reprocess=True)。"""
    from PIL import Image, ImageDraw, ImageFont

    fields = [_arr(bg), a_interp, c_plugin]
    vmax = 1.0
    for f in fields:
        v = f[np.isfinite(f)]
        if v.size:
            vmax = max(vmax, float(np.percentile(v, 99)))

    panels = [
        _panel(_to_rgb_blues(fields[0], vmax), "background (m4)"),
        _panel(_to_rgb_blues(a_interp, vmax), "interp_sg_cressman (+bg absolute)"),
        _panel(_to_rgb_blues(c_plugin, vmax), "InterpSgCressman reprocess=True"),
    ]
    gap, header = 8, 44
    pw, ph = panels[0].size
    W = gap * 4 + pw * 3
    H = header + gap * 2 + ph
    canvas = Image.new("RGB", (W, H), (245, 245, 245))
    for i, p in enumerate(panels):
        canvas.paste(p, (gap + i * (pw + gap), header + gap))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text(
        (gap, 12),
        "background | interp_sg | plugin(reprocess=True) | resource/sample | clip=%s"
        % (_CLIP,),
        fill=(10, 10, 10),
        font=font,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(out_png))
    return out_png


def run(m4_path: Path = _DEFAULT_M4, sta_path: Path = _DEFAULT_STA) -> int:
    if not m4_path.is_file():
        print("缺少格点: %s" % m4_path, file=sys.stderr)
        return 2
    if not sta_path.is_file():
        print("缺少站点: %s" % sta_path, file=sys.stderr)
        return 2

    print("grid:", m4_path)
    print("sta :", sta_path)
    bg = meb.read_griddata_from_micaps4(str(m4_path))
    bg = _clip_grd(bg, _CLIP)
    sta = meb.read_stadata_from_micaps3(str(sta_path))
    sta = _clean_sta(sta, _CLIP)
    print("after clip: grid", _arr(bg).shape, "sta", len(sta))
    if len(sta) < 5:
        print("裁剪后站点数过少", file=sys.stderr)
        return 1

    grid = meb.get_grid_of_data(bg) if hasattr(meb, "get_grid_of_data") else meteva_base.basicdata.get_grid_of_data(bg)
    r_km = _r_km_from_deg(_R_DEG)
    print("r_deg=%s" % _R_DEG)
    print("r_km =%s" % [round(x, 1) for x in r_km])

    print("1) InterpSgCressman reprocess=False ...", flush=True)
    out_p0 = InterpSgCressman(
        r_list=r_km, nearNum=_NEAR, reprocess=False
    ).process(sta, grid=grid, background=bg)
    a = _arr(out_p0)

    print("2) InterpSgCressman reprocess=True (差值累加) ...", flush=True)
    out_p1 = InterpSgCressman(
        r_list=_R_DEG,
        nearNum=_NEAR,
        reprocess=True,
        rain_limit=0.01,
    ).process(sta, background=bg)
    c = _arr(out_p1)

    st02 = _stats(a, c)
    print(
        "False vs True: "
        "n={n} corr={corr:.6f} mae={mae:.6f} rmse={rmse:.6f} max_abs={max_abs:.6f}".format(**st02)
    )

    out_png = _OUT / ("interp_sg_vs_plugin_%s.png" % m4_path.stem)
    _save_pair_figure(bg, a, c, out_png)
    print("figure:", out_png)
    return 0


if __name__ == "__main__":
    m4 = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_M4
    sta = Path(sys.argv[2]) if len(sys.argv) > 2 else _DEFAULT_STA
    raise SystemExit(run(m4, sta))
