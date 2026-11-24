# -*- coding: utf-8 -*-
"""对比 iris / cartopy 两套「等经纬度 → Lambert 等距」实现（不是等距→经纬度）。

方向固定：
    输入：MICAPS4 等经纬度格点（lon/lat Cube）
    输出：中国区 Lambert 等距格点（projection_x/y，米）
    对比：``CubeLonlatToEqual``（iris regridder）vs ``CubeLonlatToEqualCartopy``

默认样例（包内副本；可改 ``M4_PATH`` 或命令行第一个参数）::

    resource/sample/2026052400.036.m4

流程：读 m4 → 构造 lat/lon Cube → 两套 lonlat→equal → 差值统计 + 对比图。

运行（需 iris + cartopy；本机可用 py39）::

    python test/compare_iris_cartopy_m4.py
    python test/compare_iris_cartopy_m4.py path/to/file.m4
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
_OUT = _ROOT / "resource" / "compare_out"
for _p in (str(_SRC), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

M4_PATH = _ROOT / "resource" / "data" / "2026052400.036.m4"

PROJECTION_EXTENT = (83.0, 138.0, 12.0, 53.0)
SECANT_LATITUDES = (25.0, 47.0)
GRID_DISTANCE = 10000.0


def _read_micaps4(path: Path):
    """轻量读 MICAPS4 格点（不依赖 meteva），返回 lon, lat, data2d。

    头格式（业务常见）::

        diamond 4 <title>
        yy mm dd hh fhour level
        dx dy slon elon slat elat nx ny nContour ...
        <nx*ny 数据，按行 lat 递增>
    """
    tokens = path.read_text(encoding="utf-8", errors="ignore").split()
    if len(tokens) < 20 or tokens[0].lower() != "diamond":
        raise RuntimeError("非 MICAPS4: %s" % path)

    i = 2
    while i < len(tokens):
        try:
            float(tokens[i])
            break
        except ValueError:
            i += 1
    nums = []
    for tok in tokens[i:]:
        try:
            nums.append(float(tok))
        except ValueError:
            continue

    # nums: yy mm dd hh fhour level | dx dy slon elon slat elat nx ny ...
    if len(nums) < 14:
        raise RuntimeError("MICAPS4 头过短: %s" % path)
    dx, dy = nums[6], nums[7]
    slon, elon = nums[8], nums[9]
    slat, elat = nums[10], nums[11]
    nx, ny = int(round(nums[12])), int(round(nums[13]))
    if nx < 2 or ny < 2:
        raise RuntimeError("MICAPS4 格点数异常 nx=%s ny=%s" % (nx, ny))

    n_expect = nx * ny
    payload = None
    for skip in range(0, 64):
        start = 14 + skip
        chunk = nums[start : start + n_expect]
        if len(chunk) == n_expect:
            payload = chunk
            break
    if payload is None:
        raise RuntimeError("MICAPS4 数据长度不足: 期望 %d" % n_expect)

    lon = slon + dx * np.arange(nx, dtype=np.float64)
    lat = slat + dy * np.arange(ny, dtype=np.float64)
    if abs(lon[-1] - elon) > max(0.5, abs(dx) * 3):
        lon = np.linspace(slon, elon, nx)
    if abs(lat[-1] - elat) > max(0.5, abs(dy) * 3):
        lat = np.linspace(slat, elat, ny)
    data = np.asarray(payload, dtype=np.float64).reshape(ny, nx)
    return lon, lat, data


def _read_m4_via_meteva(path: Path):
    import meteva.base as meb

    grd = meb.read_griddata_from_micaps4(
        str(path), time=dt.datetime(2026, 5, 24, 0)
    )
    lon = np.asarray(grd.lon.values, dtype=np.float64)
    lat = np.asarray(grd.lat.values, dtype=np.float64)
    data = np.asarray(grd.values, dtype=np.float64).reshape(lat.size, lon.size)
    return lon, lat, data


def load_lonlat_cube(path: Path):
    """m4 → iris Cube（优先 meteva；否则轻量解析）。"""
    import iris
    from iris.coords import DimCoord
    from iris.cube import Cube

    try:
        lon, lat, data = _read_m4_via_meteva(path)
    except Exception:
        lon, lat, data = _read_micaps4(path)

    try:
        from utils.cpt_utils import GRID_COORD_ATTRIBUTES

        cs = GRID_COORD_ATTRIBUTES["latlon"]["coord_system"]
    except Exception:
        cs = iris.coord_systems.GeogCS(6371229.0)

    x_coord = DimCoord(
        lon,
        standard_name="longitude",
        units="degrees",
        coord_system=cs,
    )
    y_coord = DimCoord(
        lat,
        standard_name="latitude",
        units="degrees",
        coord_system=cs,
    )
    cube = Cube(
        data.astype(np.float32),
        long_name="precipitation",
        units="mm",
        dim_coords_and_dims=[(y_coord, 0), (x_coord, 1)],
    )
    return cube


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    """皮尔逊相关（纯 Python 累加，避开本机 BLAS ``corrcoef``/``dot`` 崩进程）。"""
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    n = a.size
    if n < 2:
        return float("nan")
    ma = float(a.sum() / n)
    mb = float(b.sum() / n)
    num = 0.0
    da2 = 0.0
    db2 = 0.0
    for i in range(n):
        xa = float(a[i]) - ma
        xb = float(b[i]) - mb
        num += xa * xb
        da2 += xa * xa
        db2 += xb * xb
    denom = (da2 * db2) ** 0.5
    if denom == 0.0:
        return 1.0 if abs(num) < 1e-12 else float("nan")
    return num / denom


def _stats(a: np.ndarray, b: np.ndarray) -> dict:
    mask = np.isfinite(a) & np.isfinite(b)
    n = int(mask.sum())
    if n < 2:
        return {
            "n": n,
            "mae": np.nan,
            "rmse": np.nan,
            "max_abs": np.nan,
            "corr": np.nan,
            "bias": np.nan,
        }
    da = np.asarray(a[mask], dtype=np.float64)
    db = np.asarray(b[mask], dtype=np.float64)
    diff = da - db
    mae = float(np.mean(np.abs(diff)))
    rmse = float(np.sqrt(np.mean(diff * diff)))
    max_abs = float(np.max(np.abs(diff)))
    bias = float(np.mean(diff))
    corr = 1.0 if mae == 0.0 and max_abs == 0.0 else _corr(da, db)
    return {
        "n": n,
        "mae": mae,
        "rmse": rmse,
        "max_abs": max_abs,
        "corr": corr,
        "bias": bias,
    }


def _align_xy(cube_a, cube_b):
    """裁到相同形状（若两端网格点数因浮点边界差 1）。"""
    ya = cube_a.coord(axis="y").points
    xa = cube_a.coord(axis="x").points
    yb = cube_b.coord(axis="y").points
    xb = cube_b.coord(axis="x").points
    ny = min(ya.size, yb.size)
    nx = min(xa.size, xb.size)
    da = np.asarray(cube_a.data, dtype=np.float64)[..., :ny, :nx]
    db = np.asarray(cube_b.data, dtype=np.float64)[..., :ny, :nx]
    return xa[:nx], ya[:ny], da, db


def _vmax99(arr: np.ndarray, floor: float = 1.0) -> float:
    vals = np.asarray(arr, dtype=np.float64).ravel()
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return floor
    vals.sort()
    idx = min(vals.size - 1, int(vals.size * 0.99))
    return float(max(vals[idx], floor))


def _to_rgb_blues(data: np.ndarray, vmax: float) -> np.ndarray:
    """简易 Blues 色标 → uint8 RGB。"""
    z = np.asarray(data, dtype=np.float64)
    t = np.clip(z / max(vmax, 1e-6), 0.0, 1.0)
    t = np.where(np.isfinite(z), t, 0.0)
    # 白 → 深蓝
    r = (255 * (1.0 - 0.85 * t)).astype(np.uint8)
    g = (255 * (1.0 - 0.55 * t)).astype(np.uint8)
    b = (255 * (1.0 - 0.10 * t)).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


def _to_rgb_rdbu(data: np.ndarray, dmax: float) -> np.ndarray:
    """简易 RdBu_r：负蓝、正红、零白。"""
    z = np.asarray(data, dtype=np.float64)
    t = np.clip(z / max(dmax, 1e-6), -1.0, 1.0)
    t = np.where(np.isfinite(z), t, 0.0)
    r = np.ones_like(t)
    g = np.ones_like(t)
    b = np.ones_like(t)
    pos = t > 0
    neg = t < 0
    r[pos] = 1.0
    g[pos] = 1.0 - t[pos]
    b[pos] = 1.0 - t[pos]
    r[neg] = 1.0 + t[neg]
    g[neg] = 1.0 + t[neg]
    b[neg] = 1.0
    rgb = np.stack(
        [
            (255 * r).astype(np.uint8),
            (255 * g).astype(np.uint8),
            (255 * b).astype(np.uint8),
        ],
        axis=-1,
    )
    return rgb


def _panel(rgb: np.ndarray, title: str, panel_w: int = 520, panel_h: int = 420):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.fromarray(np.flipud(rgb), mode="RGB")
    img = img.resize((panel_w, panel_h - 28), Image.BILINEAR)
    canvas = Image.new("RGB", (panel_w, panel_h), (255, 255, 255))
    canvas.paste(img, (0, 28))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((6, 6), title, fill=(20, 20, 20), font=font)
    return canvas


def make_compare_figure(cube_in, cube_iris, cube_cartopy, stats, out_png: Path):
    """用 PIL 拼 2×2 对比图（本机 matplotlib savefig 会崩进程）。"""
    from PIL import Image, ImageDraw, ImageFont

    finite_in = np.asarray(cube_in.data, dtype=np.float64)
    _, _, da, db = _align_xy(cube_iris, cube_cartopy)
    diff = da - db
    vmax = _vmax99(finite_in, 1.0)
    dmax = _vmax99(np.abs(diff), 0.1)
    if dmax < 1e-6:
        dmax = 0.1

    p0 = _panel(_to_rgb_blues(finite_in, vmax), "1 input: lon/lat (m4)")
    p1 = _panel(_to_rgb_blues(da, vmax), "2 iris: lonlat->equal (m)")
    p2 = _panel(_to_rgb_blues(db, vmax), "3 cartopy: lonlat->equal (m)")
    p3 = _panel(
        _to_rgb_rdbu(diff, dmax),
        "4 iris-cartopy  corr={corr:.6f} mae={mae:.4f} max={max_abs:.4f}".format(**stats),
    )

    gap = 8
    header = 36
    w = p0.width * 2 + gap * 3
    h = p0.height * 2 + gap * 3 + header
    canvas = Image.new("RGB", (w, h), (245, 245, 245))
    canvas.paste(p0, (gap, header + gap))
    canvas.paste(p1, (gap * 2 + p0.width, header + gap))
    canvas.paste(p2, (gap, header + gap * 2 + p0.height))
    canvas.paste(p3, (gap * 2 + p0.width, header + gap * 2 + p0.height))

    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    title = (
        "DIRECTION: lon/lat -> Lambert equal-distance (NOT equal->lonlat)  "
        "dx=%.0fm  extent=%s" % (GRID_DISTANCE, PROJECTION_EXTENT)
    )
    draw.text((gap, 10), title, fill=(10, 10, 10), font=font)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(out_png))
    return out_png


def run(m4_path: Path = M4_PATH) -> int:
    if not m4_path.is_file():
        print("找不到样例 m4: %s" % m4_path, file=sys.stderr)
        return 2

    from cube_lonlat_to_equal import CubeLonlatToEqual
    from cube_lonlat_to_equal_cartopy import CubeLonlatToEqualCartopy

    print("load:", m4_path)
    cube = load_lonlat_cube(m4_path)
    print("input cube:", cube)

    kw = dict(
        projection_extent=PROJECTION_EXTENT,
        secant_latitudes=SECANT_LATITUDES,
        grid_distance=GRID_DISTANCE,
        regrid_mode="bilinear",
        extrapolation_mode="nanmask",
    )
    t0 = dt.datetime.now()
    cube_iris = CubeLonlatToEqual(**kw).process(cube)
    t_iris = (dt.datetime.now() - t0).total_seconds()
    print("iris:", cube_iris, "  %.2fs" % t_iris)

    t0 = dt.datetime.now()
    cube_cartopy = CubeLonlatToEqualCartopy(**kw).process(cube)
    t_cartopy = (dt.datetime.now() - t0).total_seconds()
    print("cartopy:", cube_cartopy, "  %.2fs" % t_cartopy)

    _, _, da, db = _align_xy(cube_iris, cube_cartopy)
    stats = _stats(da, db)
    print(
        "compare n={n}  corr={corr:.8f}  mae={mae:.6f}  rmse={rmse:.6f}  "
        "max_abs={max_abs:.6f}  bias={bias:.6f}".format(**stats),
        flush=True,
    )

    out_png = _OUT / ("iris_vs_cartopy_%s.png" % m4_path.stem)
    make_compare_figure(cube, cube_iris, cube_cartopy, stats, out_png)
    print("figure:", out_png, flush=True)
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else M4_PATH
    raise SystemExit(run(path))
