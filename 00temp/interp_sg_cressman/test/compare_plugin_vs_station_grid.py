# -*- coding: utf-8 -*-
"""三方对比：场对场（参考）+ 留出站对实况 RMSE（主结论）。

数据（本包 ``resource/sample``）::

    resource/sample/2026052400.036.m4   # 格点背景
    resource/sample/26052520.000        # 站点实况

对比对象：

1. 本包 ``InterpSgCressman(reprocess=False)``：km 核绝对值 + ``background``
2. 本包 ``InterpSgCressman(reprocess=True)``：差值累加再处理
3. ``interpolation_station_grid.InterpSgCressman``：现封装逐步创新量订正

评价：

- **主结论**：留出约 20% 站，用训练站插值，在留出站上对实况算 RMSE（多 seed 平均）；
  同时报背景场基线与 ΔRMSE。
- **参考**：全站插值后的场对场 corr/mae/rmse + 四联图（锐度观感，不定优劣）。

运行::

    python test/compare_plugin_vs_station_grid.py
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
_SG_SRC = _TEMP / "interpolation_station_grid" / "src"
_SG_ROOT = _TEMP / "interpolation_station_grid"
_GG_ROOT = _TEMP / "interpolation_grid_grid"
_GG_SRC = _GG_ROOT / "src"
_PATH_PREFIX = [
    str(_SRC),
    str(_ROOT),
    str(_SG_SRC),
    str(_SG_ROOT),
    str(_GG_ROOT),
    str(_GG_SRC),
]
sys.path[:0] = [p for p in _PATH_PREFIX if p not in sys.path]

import meteva.base as meb
import meteva_base

import importlib.util

from interp_sg_cressman_plugin import DEFAULT_R_LIST_DEG, InterpSgCressman

# station_grid 现封装与本包同名，按文件路径单独加载
_sg_path = _SG_SRC / "interp_sg_cressman_plugin.py"
_spec = importlib.util.spec_from_file_location("sg_interp_sg_cressman_plugin", _sg_path)
_sg_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_sg_mod)
InterpSgCressmanStationGrid = _sg_mod.InterpSgCressman

_DEFAULT_M4 = _SAMPLE / "2026052400.036.m4"
_DEFAULT_STA = _SAMPLE / "26052520.000"

_CLIP = (100.0, 125.0, 20.0, 45.0)
_R_DEG = list(DEFAULT_R_LIST_DEG)
_KM_PER_DEG = float(getattr(meteva_base.basicdata.const, "ER", 6371.229)) * math.pi / 180.0
_NEAR = 100
_UNDEF = 9999.0
_HOLD_FRAC = 0.2
_HOLD_SEEDS = (7, 17, 27)


def _arr(g) -> np.ndarray:
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def _stats(a: np.ndarray, b: np.ndarray) -> dict:
    mask = np.isfinite(a) & np.isfinite(b)
    n = int(mask.sum())
    if n < 2:
        return {"n": n, "mae": np.nan, "rmse": np.nan, "max_abs": np.nan, "corr": np.nan}
    da, db = a[mask], b[mask]
    diff = da - db
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


def _print_pair(name: str, st: dict) -> None:
    print(
        "{name}: n={n} corr={corr:.6f} mae={mae:.6f} rmse={rmse:.6f} max_abs={max_abs:.6f}".format(
            name=name, **st
        )
    )


def _clip_grd(grd, clip):
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
    return out.reset_index(drop=True)


def _r_km_from_deg(r_deg):
    return [float(r) * _KM_PER_DEG * 1000.0 for r in r_deg]


def _get_grid(bg):
    if hasattr(meb, "get_grid_of_data"):
        return meb.get_grid_of_data(bg)
    return meteva_base.basicdata.get_grid_of_data(bg)


def _interp_at_sta(grd, sta):
    try:
        s = meb.interp_gs_linear(grd, sta)
    except Exception:
        s = meteva_base.interp_gs_linear(grd, sta)
    return np.asarray(s.iloc[:, -1], dtype=float)


def _run_orig(sta, grid, bg, r_km):
    return InterpSgCressman(
        r_list=r_km, nearNum=_NEAR, reprocess=False
    ).process(sta, grid=grid, background=bg)


def _run_plugin(sta, bg, r_deg):
    return InterpSgCressman(
        r_list=list(r_deg),
        nearNum=_NEAR,
        reprocess=True,
        rain_limit=0.01,
    ).process(sta, background=bg)


def _run_sg(sta, grid, bg, r_km):
    return InterpSgCressmanStationGrid(
        r_list=r_km, nearNum=_NEAR, outer_value=0.0
    ).process(sta, grid, background=bg)


def _to_rgb_blues(data, vmax):
    z = np.asarray(data, dtype=float)
    t = np.clip(np.where(np.isfinite(z), z / max(vmax, 1e-6), 0.0), 0.0, 1.0)
    r = (255 * (1.0 - 0.85 * t)).astype(np.uint8)
    g = (255 * (1.0 - 0.55 * t)).astype(np.uint8)
    b = (255 * (1.0 - 0.10 * t)).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def _panel(rgb, title, w=400, h=340):
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


def _save_figure(bg, orig, plugin, sg, out_png: Path):
    from PIL import Image, ImageDraw, ImageFont

    fields = [_arr(bg), orig, plugin, sg]
    vmax = 1.0
    for f in fields:
        v = f[np.isfinite(f)]
        if v.size:
            vmax = max(vmax, float(np.percentile(v, 99)))

    panels = [
        _panel(_to_rgb_blues(fields[0], vmax), "background (m4)"),
        _panel(_to_rgb_blues(fields[1], vmax), "reprocess=False (km)"),
        _panel(_to_rgb_blues(fields[2], vmax), "plugin reprocess=True"),
        _panel(_to_rgb_blues(fields[3], vmax), "InterpSgCressman (station_grid)"),
    ]
    gap, header = 8, 44
    pw, ph = panels[0].size
    W = gap * 5 + pw * 4
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
        "False | True | station_grid | clip=%s | r_deg=%s" % (_CLIP, _R_DEG),
        fill=(10, 10, 10),
        font=font,
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(out_png))
    return out_png


def _holdout_once(sta, bg, grid, r_deg, r_km, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = len(sta)
    n_hold = max(1, int(round(n * _HOLD_FRAC)))
    idx = np.arange(n)
    rng.shuffle(idx)
    hold_idx = np.sort(idx[:n_hold])
    train_idx = np.sort(idx[n_hold:])
    train = sta.iloc[train_idx].reset_index(drop=True)
    hold = sta.iloc[hold_idx].reset_index(drop=True)
    obs = np.asarray(hold["data0"], float)

    out_o = _run_orig(train, grid, bg, r_km)
    out_p = _run_plugin(train, bg, r_deg)
    out_s = _run_sg(train, grid, bg, r_km)

    return {
        "seed": seed,
        "n_hold": len(hold),
        "bg": _stats(_interp_at_sta(bg, hold), obs),
        "orig": _stats(_interp_at_sta(out_o, hold), obs),
        "plugin": _stats(_interp_at_sta(out_p, hold), obs),
        "sg": _stats(_interp_at_sta(out_s, hold), obs),
    }


def run(m4_path: Path = _DEFAULT_M4, sta_path: Path = _DEFAULT_STA) -> int:
    if not m4_path.is_file():
        print("缺少格点: %s" % m4_path, file=sys.stderr)
        return 2
    if not sta_path.is_file():
        print("缺少站点: %s" % sta_path, file=sys.stderr)
        return 2
    if not _SG_SRC.is_dir():
        print("找不到 interpolation_station_grid/src: %s" % _SG_SRC, file=sys.stderr)
        return 2

    print("grid:", m4_path)
    print("sta :", sta_path)
    bg = meb.read_griddata_from_micaps4(str(m4_path))
    bg = _clip_grd(bg, _CLIP)
    sta = meb.read_stadata_from_micaps3(str(sta_path))
    sta = _clean_sta(sta, _CLIP)
    print("after clip: grid", _arr(bg).shape, "sta", len(sta))
    if len(sta) < 20:
        print("裁剪后站点数过少", file=sys.stderr)
        return 1

    grid = _get_grid(bg)
    r_km = _r_km_from_deg(_R_DEG)
    print("r_deg=%s" % _R_DEG)
    print("r_km =%s" % [round(x, 1) for x in r_km])

    # ---- A) 全站：场对场 + 出图（参考）----
    print("\n=== A) 全站训练：场对场（参考，不定优劣）===", flush=True)
    print("1) InterpSgCressman reprocess=False ...", flush=True)
    out_orig = _run_orig(sta, grid, bg, r_km)
    a = _arr(out_orig)

    print("2) InterpSgCressman reprocess=True ...", flush=True)
    out_p1 = _run_plugin(sta, bg, _R_DEG)
    b = _arr(out_p1)

    print("3) InterpSgCressman (station_grid) ...", flush=True)
    out_sg = _run_sg(sta, grid, bg, r_km)
    c = _arr(out_sg)

    _print_pair("False vs True", _stats(a, b))
    _print_pair("False vs station_grid", _stats(a, c))
    _print_pair("True vs station_grid", _stats(b, c))

    out_png = _OUT / ("three_way_%s.png" % m4_path.stem)
    _save_figure(bg, a, b, c, out_png)
    print("figure:", out_png)

    # ---- B) 留出：对实况 RMSE（主结论）----
    print(
        "\n=== B) 留出检验（主结论：%.0f%% hold-out, seeds=%s）==="
        % (_HOLD_FRAC * 100, _HOLD_SEEDS),
        flush=True,
    )
    rows = []
    for seed in _HOLD_SEEDS:
        print("seed=%s ..." % seed, flush=True)
        row = _holdout_once(sta, bg, grid, _R_DEG, r_km, seed)
        rows.append(row)
        print(
            "  hold n=%s | bg=%.4f | False=%.4f | True=%.4f | sg=%.4f"
            % (
                row["n_hold"],
                row["bg"]["rmse"],
                row["orig"]["rmse"],
                row["plugin"]["rmse"],
                row["sg"]["rmse"],
            )
        )

    def _mean_rmse(key: str) -> float:
        return float(np.nanmean([r[key]["rmse"] for r in rows]))

    mean_bg = _mean_rmse("bg")
    mean_o = _mean_rmse("orig")
    mean_p = _mean_rmse("plugin")
    mean_s = _mean_rmse("sg")

    print("\n--- 主结论：留出站平均 RMSE（越小越好）---")
    print("background                 rmse=%.4f" % mean_bg)
    print(
        "reprocess=False (km)       rmse=%.4f  (Δ vs bg: %+.4f)"
        % (mean_o, mean_o - mean_bg)
    )
    print(
        "reprocess=True             rmse=%.4f  (Δ vs bg: %+.4f)"
        % (mean_p, mean_p - mean_bg)
    )
    print(
        "station_grid               rmse=%.4f  (Δ vs bg: %+.4f)"
        % (mean_s, mean_s - mean_bg)
    )

    scores = {
        "reprocess=False": mean_o,
        "reprocess=True": mean_p,
        "station_grid": mean_s,
    }
    winner = min(scores, key=scores.get)
    print("→ winner (hold-out RMSE):", winner)
    return 0


if __name__ == "__main__":
    m4 = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_M4
    sta = Path(sys.argv[2]) if len(sys.argv) > 2 else _DEFAULT_STA
    raise SystemExit(run(m4, sta))
