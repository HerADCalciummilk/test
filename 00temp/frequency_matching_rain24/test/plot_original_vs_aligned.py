# -*- coding: utf-8 -*-
"""用已跑出的产品场画 original(rain24_old) vs aligned 对比图。

aligned 部分 m4 头（时间行）损坏，本脚本用容错读法只取网格定义与数据。
输出：resource/output/pngs/original_vs_aligned/{rpt}/{rpt}.{dtime}.png
每张：原版 | aligned | aligned−原版。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT_ROOT = ROOT / "resource" / "output"
ORIG_ROOT = OUT_ROOT / "rain24_old" / "ecmwf"
ALIGN_ROOT = OUT_ROOT / "rain24_aligned" / "ecmwf"
PNG_ROOT = OUT_ROOT / "pngs" / "original_vs_aligned"

DEFAULT_DTIMES = (36, 72, 120, 168, 252)
DEFAULT_RPTS = ("2026081300", "2026081312")


def read_m4_robust(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """容错读 Micaps4：跳过损坏时间行，按网格定义行解析。"""
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    grid_i = None
    for i, ln in enumerate(lines[:10]):
        parts = ln.split()
        if len(parts) < 8:
            continue
        try:
            vals = [float(x) for x in parts[:8]]
        except ValueError:
            continue
        dlon, dlat, slon, elon, slat, elat, nlon, nlat = vals
        if nlon > 10 and nlat > 10 and abs(dlon) < 5 and abs(dlat) < 5:
            grid_i = i
            break
    if grid_i is None:
        raise ValueError("找不到网格定义行: %s" % path)
    parts = lines[grid_i].split()
    dlon, dlat, slon, elon, slat, elat = map(float, parts[:6])
    nlon, nlat = int(float(parts[6])), int(float(parts[7]))
    nums = []
    for ln in lines[grid_i + 1 :]:
        for tok in ln.split():
            try:
                nums.append(float(tok))
            except ValueError:
                pass
    need = nlon * nlat
    if len(nums) < need:
        raise ValueError("数据点数不足 %s: %d < %d" % (path, len(nums), need))
    arr = np.asarray(nums[:need], float).reshape(nlat, nlon)
    lon = np.linspace(slon, elon, nlon)
    lat = np.linspace(slat, elat, nlat)
    return lon, lat, arr


def _stats(a: np.ndarray, b: np.ndarray) -> dict:
    d = b - a
    mask = np.isfinite(d)
    if not np.any(mask):
        return {"rmse": np.nan, "mae": np.nan, "bias": np.nan, "maxabs": np.nan, "corr": np.nan}
    aa, bb, dd = a[mask], b[mask], d[mask]
    corr = float(np.corrcoef(aa, bb)[0, 1]) if aa.std() > 0 and bb.std() > 0 else np.nan
    return {
        "rmse": float(np.sqrt(np.mean(dd ** 2))),
        "mae": float(np.mean(np.abs(dd))),
        "bias": float(np.mean(dd)),
        "maxabs": float(np.max(np.abs(dd))),
        "corr": corr,
    }


def _plot_one(rpt: str, dtime: int) -> Optional[Path]:
    name = "%s.%03d.m4" % (rpt, dtime)
    p_old = ORIG_ROOT / rpt / name
    p_al = ALIGN_ROOT / rpt / name
    if not p_old.is_file() or not p_al.is_file():
        print("skip missing:", name)
        return None

    lon, lat, a = read_m4_robust(p_old)
    lon2, lat2, b = read_m4_robust(p_al)
    if a.shape != b.shape:
        print("skip shape mismatch %s: %s vs %s" % (name, a.shape, b.shape))
        return None
    st = _stats(a, b)
    d = b - a
    dmax = max(float(np.nanpercentile(np.abs(d), 99.5)), 1e-3)
    vmax = max(50.0, float(np.nanpercentile(np.concatenate([a.ravel(), b.ravel()]), 99)))

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), constrained_layout=True)
    panels = (
        (axes[0], a, "original (rain24_old)", "Blues", {"vmin": 0, "vmax": vmax}),
        (axes[1], b, "aligned (rain24_aligned)", "Blues", {"vmin": 0, "vmax": vmax}),
        (axes[2], d, "aligned - original", "RdBu_r", {"vmin": -dmax, "vmax": dmax}),
    )
    for ax, field, title, cmap, kw in panels:
        im = ax.pcolormesh(lon, lat, field, shading="auto", cmap=cmap, **kw)
        ax.set_title(title, fontsize=11)
        ax.set_xlim(float(lon.min()), float(lon.max()))
        ax.set_ylim(float(lat.min()), float(lat.max()))
        ax.set_aspect("equal")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)

    fig.suptitle(
        "%s dtime=%03dh  RMSE=%.3f  MAE=%.3f  bias=%+.3f  max|d|=%.3f  corr=%.4f"
        % (rpt, dtime, st["rmse"], st["mae"], st["bias"], st["maxabs"], st["corr"]),
        fontsize=12,
    )
    out_dir = PNG_ROOT / rpt
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ("%s.%03d.png" % (rpt, dtime))
    fig.savefig(str(out), dpi=140)
    plt.close(fig)
    print(
        "%s.%03d  RMSE=%.3f MAE=%.3f bias=%+.3f corr=%.4f  -> %s"
        % (rpt, dtime, st["rmse"], st["mae"], st["bias"], st["corr"], out)
    )
    return out


def main(rpts: Sequence[str] = DEFAULT_RPTS, dtimes: Sequence[int] = DEFAULT_DTIMES):
    paths = []
    for rpt in rpts:
        for dt in dtimes:
            p = _plot_one(rpt, int(dt))
            if p is not None:
                paths.append(p)
    # 汇总表
    print("--- summary (all common m4) ---")
    rows = []
    for rpt_dir in sorted(ORIG_ROOT.glob("*")):
        if not rpt_dir.is_dir():
            continue
        rpt = rpt_dir.name
        for p_old in sorted(rpt_dir.glob("*.m4")):
            p_al = ALIGN_ROOT / rpt / p_old.name
            if not p_al.is_file():
                continue
            try:
                _, _, a = read_m4_robust(p_old)
                _, _, b = read_m4_robust(p_al)
            except Exception as exc:
                print("read fail", p_old.name, exc)
                continue
            if a.shape != b.shape:
                continue
            st = _stats(a, b)
            dtime = int(p_old.stem.split(".")[-1])
            rows.append((rpt, dtime, st))
            print(
                "%s.%03d  RMSE=%.3f  MAE=%.3f  bias=%+.3f  corr=%.4f"
                % (rpt, dtime, st["rmse"], st["mae"], st["bias"], st["corr"])
            )
    if rows:
        rmses = [r[2]["rmse"] for r in rows]
        print(
            "n=%d  RMSE mean=%.3f median=%.3f  MAE mean=%.3f"
            % (len(rows), float(np.mean(rmses)), float(np.median(rmses)),
               float(np.mean([r[2]["mae"] for r in rows])))
        )
    print("figures: %d under %s" % (len(paths), PNG_ROOT))
    return paths


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv:
        rpt = argv[0]
        dts = [int(x) for x in argv[1:]] if len(argv) > 1 else list(DEFAULT_DTIMES)
        main(rpts=(rpt,), dtimes=dts)
    else:
        main()
