# -*- coding: utf-8 -*-
"""
逐 1 小时降水频率匹配订正 — 主程序（``src/runner.py``）。

流水线概要
----------
``process`` → 起报 ``cycles``（``is_multi`` 时 ``SimpleParallelTool`` 多进程）
→ ``_process_cycle`` → 时效 1–48h ``_process_one_valid``
→ 空间分块 ``_process_block``（相似筛选 → 光流 → 平流 → 频率匹配）
→ 合并站点写 Micaps3 → Cressman + 二次频率匹配写 Micaps4。

调用方式
--------
- 模块调用：``from runner import process`` → ``process(data_key=..., run_times=...)``
- 直接运行：``python src/runner.py``（在 ``__main__`` 中改传参）
- 命令行：``python -m cli [data_key] [起报时刻...]``（项目根目录）
"""
from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    """项目根优先（加载 ``utils`` 合并 ``src/utils``），再 ``src``（``proc`` / 本模块）。"""
    _src = Path(__file__).resolve().parent
    _root = _src.parent
    ordered = (str(_root), str(_src))
    for p in ordered:
        while p in sys.path:
            sys.path.remove(p)
    for p in reversed(ordered):
        sys.path.insert(0, p)


_bootstrap_paths()

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Sequence, Union
import json
import multiprocessing as mp
import os
import sys, time
import numpy as np
from utils.types import FileFlag, GridData, LineData, PointData, ScatterData
from proc import (
    Ensemble,
    FrequencyMatch,
    OpticalFlow,
    RainExtrapolation,
    SpatialAnalysis,
)
from utils.log import Log
from utils.multipro_plugin import SimpleParallelTool
from utils.string_process import date_replace
from utils.util_env import get_resolved_paths
from utils.util_paths import repo_root

# 分块内频率匹配用的实况等级表（mm）
FACT_LEVEL = [
    0.1,
    0.5,
    1.0,
    3.0,
    5.0,
    7.5,
    10.0,
    15.0,
    20.0,
    25.0,
    30.0,
    40.0,
    50.0,
    75.0,
    100.0,
]
# 相似个例多量级检验阈值（mm）
SIMILAR_LEVEL = [0.1, 0.5, 1.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0]
# Micaps4 二次频率匹配等级表（含更细小雨与更大极值）
FINAL_FACT_LEVEL = [
    0.01,
    0.1,
    0.5,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
    15.0,
    20.0,
    25.0,
    30.0,
    40.0,
    50.0,
    75.0,
    100.0,
    150.0,
    200.0,
    250.0,
]


@dataclass
class ParaConfig:
    """单一模式键的路径模板（来自 ``resource/path.json``）。"""

    name: str
    model_template: str
    fact_template: str
    output_template: str


@dataclass
class GridConfig:
    """目标网格、短/长时效分块边界与掩膜定义（来自 ``resource/config.json``）。"""

    lon_start: float
    lon_end: float
    lat_start: float
    lat_end: float
    dlon: float
    dlat: float
    short_lon_edges: list[float]  # 短时效（≤60h）经向分块边界
    short_lat_edges: list[float]
    long_lon_edges: list[float]  # 长时效整域边界
    long_lat_edges: list[float]
    expand: float  # 样本区相对订正区外扩（度）
    background_stride: int  # 写 M4 时背景稀疏采样步长
    mask_file: str
    mask_source_lon_start: float
    mask_source_lon_end: float
    mask_source_lat_start: float
    mask_source_lat_end: float
    mask_source_dlon: float
    mask_source_dlat: float


@dataclass(frozen=True)
class RunEnvPaths:
    """由 ``qpf_fm.ini`` 解析后的运行路径。"""

    log_file_template: Path
    config_json: Path
    path_json: Path
    station_info: Path
    mask_resource_dir: Path


def get_env_paths() -> RunEnvPaths:
    """读取 ini 并组装 ``RunEnvPaths``。"""
    raw = get_resolved_paths()
    mask_file: Path = raw["mask_file"]
    return RunEnvPaths(
        log_file_template=raw["log_file_template"],
        config_json=raw["config_json"],
        path_json=raw["path_json"],
        station_info=raw["station_info"],
        mask_resource_dir=mask_file.parent,
    )


def _get_env_int(name: str, default: int, lower: int = 1, upper: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            value = default
    value = max(lower, value)
    if upper is not None:
        value = min(upper, value)
    return value


def _get_optional_env_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _is_nc_template(path_template: str) -> bool:
    return Path(path_template).suffix.lower() == ".nc"


def _is_datetime_token(token: str) -> bool:
    return len(token) == 12 and token.isdigit()


def _default_grid_config() -> GridConfig:
    return GridConfig(
        lon_start=70.0,
        lon_end=140.0,
        lat_start=0.0,
        lat_end=60.0,
        dlon=0.1,
        dlat=0.1,
        short_lon_edges=[70.0, 75.0, 85.0, 95.0, 105.0, 115.0, 125.0, 135.0, 140.0],
        short_lat_edges=[0.0, 5.0, 15.0, 25.0, 35.0, 45.0, 55.0, 60.0],
        long_lon_edges=[70.0, 140.0],
        long_lat_edges=[0.0, 60.0],
        expand=1.0,
        background_stride=5,
        mask_file="mask010.dat",
        mask_source_lon_start=70.0,
        mask_source_lon_end=140.0,
        mask_source_lat_start=0.0,
        mask_source_lat_end=60.0,
        mask_source_dlon=0.1,
        mask_source_dlat=0.1,
    )


def _scaled_edges(
    start: float, end: float, base_offsets: list[float], base_span: float
) -> list[float]:
    span = end - start
    if span <= 0:
        return [start, end]
    return [start + span * (off / base_span) for off in base_offsets]


def _as_sorted_edges(value: object, fallback: list[float]) -> list[float]:
    if not isinstance(value, list):
        return fallback
    try:
        arr = [float(v) for v in value]
    except Exception:
        return fallback
    if len(arr) < 2:
        return fallback
    if any(arr[i] >= arr[i + 1] for i in range(len(arr) - 1)):
        return fallback
    return arr


def _edges_cover_domain(
    edges: list[float], start: float, end: float, eps: float = 1e-6
) -> bool:
    return (
        len(edges) >= 2 and abs(edges[0] - start) <= eps and abs(edges[-1] - end) <= eps
    )


def _load_grid_config(base: Path | None, log: Log) -> GridConfig:
    _ = base
    cfg = _default_grid_config()
    config_path = get_env_paths().config_json
    if not config_path.exists():
        return cfg
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.write_error("Config Json Content Is Not Right!", 1)
        raise RuntimeError("Config Json Content Is Not Right!") from exc
    if not isinstance(raw, dict):
        log.write_error("Config Json Content Is Not Right!", 1)
        raise RuntimeError("Config Json Content Is Not Right!")
    grid = raw.get("grid", raw)
    if not isinstance(grid, dict):
        grid = {}
    cfg.lon_start = float(grid.get("lon_start", cfg.lon_start))
    cfg.lon_end = float(grid.get("lon_end", cfg.lon_end))
    cfg.lat_start = float(grid.get("lat_start", cfg.lat_start))
    cfg.lat_end = float(grid.get("lat_end", cfg.lat_end))
    cfg.dlon = float(grid.get("dlon", cfg.dlon))
    cfg.dlat = float(grid.get("dlat", cfg.dlat))
    cfg.expand = float(grid.get("expand", cfg.expand))
    cfg.background_stride = max(
        1, int(grid.get("background_stride", cfg.background_stride))
    )
    cfg.mask_file = str(grid.get("mask_file", cfg.mask_file))
    cfg.mask_source_lon_start = float(
        grid.get("mask_source_lon_start", cfg.mask_source_lon_start)
    )
    cfg.mask_source_lon_end = float(
        grid.get("mask_source_lon_end", cfg.mask_source_lon_end)
    )
    cfg.mask_source_lat_start = float(
        grid.get("mask_source_lat_start", cfg.mask_source_lat_start)
    )
    cfg.mask_source_lat_end = float(
        grid.get("mask_source_lat_end", cfg.mask_source_lat_end)
    )
    cfg.mask_source_dlon = float(grid.get("mask_source_dlon", cfg.mask_source_dlon))
    cfg.mask_source_dlat = float(grid.get("mask_source_dlat", cfg.mask_source_dlat))

    short_lon_fallback = _scaled_edges(
        cfg.lon_start,
        cfg.lon_end,
        [0.0, 5.0, 15.0, 25.0, 35.0, 45.0, 55.0, 65.0, 70.0],
        70.0,
    )
    short_lat_fallback = _scaled_edges(
        cfg.lat_start,
        cfg.lat_end,
        [0.0, 5.0, 15.0, 25.0, 35.0, 45.0, 55.0, 60.0],
        60.0,
    )
    cfg.short_lon_edges = _as_sorted_edges(
        grid.get("short_lon_edges"), short_lon_fallback
    )
    cfg.short_lat_edges = _as_sorted_edges(
        grid.get("short_lat_edges"), short_lat_fallback
    )
    cfg.long_lon_edges = _as_sorted_edges(
        grid.get("long_lon_edges"), [cfg.lon_start, cfg.lon_end]
    )
    cfg.long_lat_edges = _as_sorted_edges(
        grid.get("long_lat_edges"), [cfg.lat_start, cfg.lat_end]
    )
    if not _edges_cover_domain(cfg.short_lon_edges, cfg.lon_start, cfg.lon_end):
        cfg.short_lon_edges = short_lon_fallback
    if not _edges_cover_domain(cfg.short_lat_edges, cfg.lat_start, cfg.lat_end):
        cfg.short_lat_edges = short_lat_fallback
    if not _edges_cover_domain(cfg.long_lon_edges, cfg.lon_start, cfg.lon_end):
        cfg.long_lon_edges = [cfg.lon_start, cfg.lon_end]
    if not _edges_cover_domain(cfg.long_lat_edges, cfg.lat_start, cfg.lat_end):
        cfg.long_lat_edges = [cfg.lat_start, cfg.lat_end]
    return cfg


def _load_path_configs(
    base: Path | None, log: Log
) -> tuple[dict[str, ParaConfig], str | None]:
    _ = base
    path_json = get_env_paths().path_json
    if not path_json.exists():
        log.write_error("Path Json File Is Not Exist!", 1)
        raise RuntimeError("Path Json File Is Not Exist!")
    try:
        payload = json.loads(path_json.read_text(encoding="utf-8"))
    except Exception as exc:
        log.write_error("Path Json Content Is Not Right!", 1)
        raise RuntimeError("Path Json Content Is Not Right!") from exc
    default_key: str | None = None
    raw_configs: dict[str, object]
    if isinstance(payload, dict) and isinstance(payload.get("configs"), dict):
        raw_configs = payload["configs"]
        if isinstance(payload.get("default"), str):
            default_key = payload["default"]
    elif isinstance(payload, dict):
        raw_configs = payload
    else:
        log.write_error("Path Json Content Is Not Right!", 1)
        raise RuntimeError("Path Json Content Is Not Right!")
    configs: dict[str, ParaConfig] = {}
    for key, cfg in raw_configs.items():
        if not isinstance(cfg, dict):
            continue
        model_template = cfg.get("model_template")
        fact_template = cfg.get("fact_template")
        output_template = cfg.get("output_template")
        if all(
            isinstance(v, str) and v.strip()
            for v in [model_template, fact_template, output_template]
        ):
            configs[str(key)] = ParaConfig(
                str(key),
                model_template.strip(),
                fact_template.strip(),
                output_template.strip(),
            )
    if not configs:
        log.write_error("Path Json Content Is Not Right!", 1)
        raise RuntimeError("Path Json Content Is Not Right!")
    return configs, default_key


def _select_para_and_runtime(
    args: list[str], configs: dict[str, ParaConfig], default_key: str | None, log: Log
) -> tuple[ParaConfig, list[datetime]]:
    data_key: str | None = None
    date_args: list[str] = []
    for token in args:
        if token.startswith("--data="):
            data_key = token.split("=", 1)[1].strip()
        elif token.startswith("--path="):
            data_key = token.split("=", 1)[1].strip()
        elif _is_datetime_token(token):
            date_args.append(token)
        elif data_key is None:
            data_key = token.strip()
        else:
            log.write_error("Args Is Not Right!", 1)
            raise RuntimeError("Args Is Not Right!")
    if data_key is None or not data_key:
        if default_key and default_key in configs:
            data_key = default_key
        elif len(configs) == 1:
            data_key = next(iter(configs.keys()))
        else:
            log.write_error("Data Key Is Not Specified!", 1)
            raise RuntimeError("Data Key Is Not Specified!")
    para = configs.get(data_key)
    if para is None:
        log.write_error(f"Data Key Is Not Exist! key={data_key}", 1)
        raise RuntimeError(f"Data Key Is Not Exist! key={data_key}")
    run_dts = _parse_runtime(date_args, log)
    return para, run_dts


def _parse_runtime(args: list[str], log: Log) -> list[datetime]:
    if not args:
        return [datetime.now()]
    if len(args) == 1 and len(args[0]) == 12:
        try:
            return [datetime.strptime(args[0], "%Y%m%d%H%M")]
        except ValueError as exc:
            log.write_error("Date Args Content Is Not Right!", 1)
            raise RuntimeError("Date Args Content Is Not Right!") from exc
    if len(args) == 2 and len(args[0]) == 12 and len(args[1]) == 12:
        try:
            start_dt = datetime.strptime(args[0], "%Y%m%d%H%M")
            end_dt = datetime.strptime(args[1], "%Y%m%d%H%M")
        except ValueError as exc:
            log.write_error("Date Args Content Is Not Right!", 1)
            raise RuntimeError("Date Args Content Is Not Right!") from exc
        if start_dt > end_dt:
            log.write_error("Date Args Range Is Not Right!", 1)
            raise RuntimeError("Date Args Range Is Not Right!")
        runtimes: list[datetime] = []
        current = start_dt
        while current <= end_dt:
            runtimes.append(current)
            current += timedelta(hours=1)
        return runtimes
    log.write_error("Date Args Number Is Not Right!", 1)
    raise RuntimeError("Date Args Number Is Not Right!")


def _task_seed(base_seed: int, dt_input1: datetime, i_valid: int) -> int:
    dt_key = int(dt_input1.strftime("%Y%m%d%H"))
    return int((base_seed * 1000003 + dt_key * 101 + i_valid) % (2**32 - 1))


def _load_mask_grid(env_paths: RunEnvPaths, grid_cfg: GridConfig) -> GridData:
    mask_path = env_paths.mask_resource_dir / grid_cfg.mask_file
    src_mask = GridData(
        grid_cfg.mask_source_lon_start,
        grid_cfg.mask_source_lon_end,
        grid_cfg.mask_source_lat_start,
        grid_cfg.mask_source_lat_end,
        grid_cfg.mask_source_dlon,
        grid_cfg.mask_source_dlat,
    )
    src_mask.read_float_val_from_bin(mask_path)
    return src_mask.mesh_val(
        grid_cfg.lon_start,
        grid_cfg.lon_end,
        grid_cfg.lat_start,
        grid_cfg.lat_end,
        grid_cfg.dlon,
        grid_cfg.dlat,
    )


def _domain(i_valid: int, grid_cfg: GridConfig):
    """
    按时效选择分块边界。

    Returns
    -------
    cll, clr, clb, clt :
        订正区（站点写出）四边列表。
    lll, llr, llb, llt :
        样本区（订正区外扩 ``expand``）四边列表。
    """
    if i_valid <= 60:
        lon_edges = grid_cfg.short_lon_edges
        lat_edges = grid_cfg.short_lat_edges
    else:
        lon_edges = grid_cfg.long_lon_edges
        lat_edges = grid_cfg.long_lat_edges
    a = lon_edges[:-1]
    b = lon_edges[1:]
    c = lat_edges[:-1]
    d = lat_edges[1:]
    expand = grid_cfg.expand
    return (
        a,
        b,
        c,
        d,
        [x - expand for x in a],
        [x + expand for x in b],
        [x - expand for x in c],
        [x + expand for x in d],
    )


def _rect(sd: ScatterData, l: float, r: float, b: float, t: float) -> ScatterData:
    """用矩形框裁剪站点子集。"""
    return sd.frame_by_line(LineData([l, r, r, l], [b, b, t, t]))


def _load_history_sample(
    model_path: Path, fact_path: Path, sta: ScatterData, grid_cfg: GridConfig
):
    """读取一对历史模式格点 + 实况站点；失败返回 ``None``。"""
    try:
        gm = GridData(model_path).mesh_val(
            grid_cfg.lon_start,
            grid_cfg.lon_end,
            grid_cfg.lat_start,
            grid_cfg.lat_end,
            grid_cfg.dlon,
            grid_cfg.dlat,
        )
        sf = sta.copy_scatter_data()
        sf.read_val_from_micaps3(fact_path)
        sf.clear_to_num_greater_than(0.0, 500.0)  # 剔除异常大值
        sf.clear_to_num_less_than(0.0, 0.0)
        return gm, sf
    except Exception:
        return None


def _process_block(
    ix: int,
    jy: int,
    sta: ScatterData,
    mask: GridData,
    train: list[GridData],
    train_s: list[GridData],
    fact_raw: list[ScatterData],
    cur_s: GridData,
    gd_cur: GridData,
    dy: int,
    fact_level: list[float],
    similar_level: list[float],
    cll: list[float],
    clr: list[float],
    clb: list[float],
    clt: list[float],
    lll: list[float],
    llr: list[float],
    llb: list[float],
    llt: list[float],
    grid_cfg: GridConfig,
):
    """
    单空间块订正：相似筛选 →（可选）光流 → 平流 + 频率匹配 → 块内站点场。

    Parameters
    ----------
    train / train_s :
        历史模式场原分辨率 / 平滑后场。
    cur_s / gd_cur :
        当前模式平滑场 / 原场。
    dy :
        有效历史样本数。
    cl* / ll* :
        订正区与样本区边界列表；``ix,jy`` 为块索引。
    """
    # 订正区站点；无站则跳过
    box = _rect(sta, cll[ix], clr[ix], clb[jy], clt[jy])
    if box.length <= 0:
        return None

    train_sta = _rect(sta, lll[ix], llr[ix], llb[jy], llt[jy])
    # 默认零位移；样本足够好时由光流覆盖
    uv = [
        GridData(lll[ix], llr[ix], llb[jy], llt[jy], grid_cfg.dlon, grid_cfg.dlat),
        GridData(lll[ix], llr[ix], llb[jy], llt[jy], grid_cfg.dlon, grid_cfg.dlat),
    ]

    # —— 1) 粗分辨率上做相似评分（掩膜外置 0，再抽稀到 10× 格距）——
    gms = []
    for src in train_s:
        tmp = src.copy_grid_data()
        tmp.mask_val(mask, 0.0)
        gms.append(
            tmp.mesh_val(
                lll[ix],
                llr[ix],
                llb[jy],
                llt[jy],
                10.0 * grid_cfg.dlon,
                10.0 * grid_cfg.dlat,
            )
        )

    gf = cur_s.copy_grid_data()
    gf.mask_val(mask, 0.0)
    gf = gf.mesh_val(
        lll[ix],
        llr[ix],
        llb[jy],
        llt[jy],
        10.0 * grid_cfg.dlon,
        10.0 * grid_cfg.dlat,
    )

    idx, score = Ensemble.get_similarity_index_by_ts_and_bias(
        gms, gf, dy, similar_level
    )

    # —— 2) 高相似样本≥20 时估计光流（历史模式→实况插值场）——
    if int((score >= 0.3).sum()) >= 20:
        befores: list[GridData] = []
        nexts: list[GridData] = []
        for n in range(20):
            bef = train[int(idx[n])].copy_grid_data()
            sd = fact_raw[int(idx[n])].copy_scatter_data()
            # 站点实况 → 格点“目标场”
            nxt = SpatialAnalysis.gressman_interpolation_for_rain(
                sd, bef, [1.0, 0.5, 0.25, 0.1]
            )
            SpatialAnalysis.grid_data_fix_by_scatter(sd, nxt)

            bef.smooth9(20)
            nxt.smooth9(20)

            bef = bef.mesh_val(
                lll[ix], llr[ix], llb[jy], llt[jy], grid_cfg.dlon, grid_cfg.dlat
            )
            nxt = nxt.mesh_val(
                lll[ix], llr[ix], llb[jy], llt[jy], grid_cfg.dlon, grid_cfg.dlat
            )

            # 光流前对历史模式做一次频率匹配，减小强度型偏差干扰位移估计
            ml, fu = FrequencyMatch.get_used_model_level_and_extend(
                [bef], [nxt], fact_level
            )
            if len(ml) >= 2:
                bef = FrequencyMatch.correct_model_data(bef, fu, ml)

            befores.append(
                bef.mesh_val(
                    lll[ix],
                    llr[ix],
                    llb[jy],
                    llt[jy],
                    5.0 * grid_cfg.dlon,
                    5.0 * grid_cfg.dlat,
                )
            )
            nexts.append(
                nxt.mesh_val(
                    lll[ix],
                    llr[ix],
                    llb[jy],
                    llt[jy],
                    5.0 * grid_cfg.dlon,
                    5.0 * grid_cfg.dlat,
                )
            )

        uv = [befores[0].copy_grid_data(), befores[0].copy_grid_data()]
        uv[0].clear_to_num(0.0)
        uv[1].clear_to_num(0.0)

        OpticalFlow.get_wind_from_optical_flow(
            befores, nexts, [[5.0, 5.0]], uv, num_limit=50
        )

        uv[0] = uv[0].mesh_val(
            lll[ix], llr[ix], llb[jy], llt[jy], grid_cfg.dlon, grid_cfg.dlat
        )
        uv[1] = uv[1].mesh_val(
            lll[ix], llr[ix], llb[jy], llt[jy], grid_cfg.dlon, grid_cfg.dlat
        )

    # —— 3) 取前 50% 相似样本：历史场平流后与实况建频率映射 ——
    top_n = int(0.5 * dy)
    ms: list[ScatterData] = []
    fs: list[ScatterData] = []
    for n in range(top_n):
        gm = train_s[int(idx[n])].mesh_val(
            lll[ix], llr[ix], llb[jy], llt[jy], grid_cfg.dlon, grid_cfg.dlat
        )
        gm = RainExtrapolation.simple_semi_lagrangian_in_angle(uv[0], uv[1], gm, 1.0)

        sm = train_sta.copy_scatter_data()
        sm.bilinear_interpolation_from_grid_data(gm)

        sf = train_sta.copy_scatter_data()
        sf.read_from_scatter_data(fact_raw[int(idx[n])])

        ms.append(sm)
        fs.append(sf)

    ml, fu = FrequencyMatch.get_used_model_level_and_extend(
        ms, fs, fact_level, fact_level_limit=20
    )

    # —— 4) 当前场：先平流，再按映射订正强度；映射不足则退回原模式 ——
    rain = cur_s.mesh_val(
        lll[ix], llr[ix], llb[jy], llt[jy], grid_cfg.dlon, grid_cfg.dlat
    )
    moved = RainExtrapolation.simple_semi_lagrangian_in_angle(uv[0], uv[1], rain, 1.0)

    out_grid = (
        gd_cur.mesh_val(
            lll[ix], llr[ix], llb[jy], llt[jy], grid_cfg.dlon, grid_cfg.dlat
        )
        if len(ml) < 2
        else FrequencyMatch.correct_model_data(moved, fu, ml)
    )

    out_sd = box.copy_scatter_data()
    out_sd.bilinear_interpolation_from_grid_data(out_grid)
    out_sd.clear_to_num_less_than(0.0, 0.01)

    return ix, jy, out_sd


def _process_one_valid(
    env_paths: RunEnvPaths,
    para: ParaConfig,
    dt_input1: datetime,
    i_valid: int,
    fact_level: list[float],
    similar_level: list[float],
    final_fact_level: list[float],
    sample_workers_cap: int,
    block_workers_cap: int,
    grid_cfg: GridConfig,
    fixed_seed: int | None = None,
) -> str | None:
    """
    处理单个起报 ``dt_input1`` 的单个时效 ``i_valid``（小时）。

    成功写出 Micaps3/4 返回 ``None``；读模式失败返回错误字符串；缺输入/已齐备则跳过。
    """
    if fixed_seed is not None:
        np.random.seed(_task_seed(fixed_seed, dt_input1, i_valid))
    p3 = Path(date_replace(para.output_template + ".m3", dt_input1, i_valid))
    p4 = Path(date_replace(para.output_template + ".m4", dt_input1, i_valid))
    cur = Path(date_replace(para.model_template, dt_input1, i_valid))
    # 仅当模式存在且至少缺一种输出时才计算
    if not (((not p3.exists()) or (not p4.exists())) and cur.exists()):
        return None
    print(f"Use data key: {para.name}")
    sta = ScatterData(env_paths.station_info, FileFlag.STAINFO)
    mask = _load_mask_grid(env_paths, grid_cfg)
    print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print(date_replace("Process Model Time Is: YYYYMMDDHH_VVV", dt_input1, i_valid))
    print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print("Read the Currect ModelData...")
    print(f"Current Model Data: {cur}")
    try:
        gd_cur = GridData(cur).mesh_val(
            grid_cfg.lon_start,
            grid_cfg.lon_end,
            grid_cfg.lat_start,
            grid_cfg.lat_end,
            grid_cfg.dlon,
            grid_cfg.dlat,
        )
    except Exception as exc:
        return str(exc)

    # 回溯最多 4 个日历年、起报日 ±15 天窗口内的模式–实况配对
    sample_jobs: list[tuple[Path, Path]] = []
    for y in range(4):
        d0 = dt_input1.replace(year=dt_input1.year - y)
        t1 = d0 - timedelta(days=15)
        t2 = d0 - timedelta(days=1) if y == 0 else d0 + timedelta(days=15)
        d = t1
        while d <= t2:
            m = Path(date_replace(para.model_template, d, i_valid))
            f = Path(date_replace(para.fact_template, d + timedelta(hours=i_valid), 0))
            if m.exists() and f.exists():
                sample_jobs.append((m, f))
            d += timedelta(days=1)
    model_raw: list[GridData] = []
    fact_raw: list[ScatterData] = []
    if sample_jobs:
        ordered_results: list[tuple[GridData, ScatterData] | None] = [None] * len(
            sample_jobs
        )
        sample_workers = (
            1
            if cur.suffix.lower() == ".nc"
            else min(sample_workers_cap, len(sample_jobs))
        )
        with ThreadPoolExecutor(max_workers=sample_workers) as executor:
            futures = {
                executor.submit(_load_history_sample, m, f, sta, grid_cfg): idx
                for idx, (m, f) in enumerate(sample_jobs)
            }
            for future in as_completed(futures):
                ordered_results[futures[future]] = future.result()
        for result in ordered_results:
            if result is not None:
                gm, sf = result
                model_raw.append(gm)
                fact_raw.append(sf)
    dy = len(model_raw)
    print(f"dyused: {dy}")
    if dy == 0:
        return None

    train = [g.copy_grid_data() for g in model_raw]
    train_s = [g.copy_grid_data() for g in model_raw]
    for g in train_s:
        g.smooth9(20)
    cur_s = gd_cur.copy_grid_data()
    cur_s.smooth9(20)

    # 分块并行订正
    cll, clr, clb, clt, lll, llr, llb, llt = _domain(i_valid, grid_cfg)
    block_jobs = [(ix, jy) for jy in range(len(clb)) for ix in range(len(cll))]
    correct: dict[tuple[int, int], ScatterData] = {}
    max_workers = min(block_workers_cap, len(block_jobs))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_block,
                ix,
                jy,
                sta,
                mask,
                train,
                train_s,
                fact_raw,
                cur_s,
                gd_cur,
                dy,
                fact_level,
                similar_level,
                cll,
                clr,
                clb,
                clt,
                lll,
                llr,
                llb,
                llt,
                grid_cfg,
            ): (ix, jy)
            for ix, jy in block_jobs
        }
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                ix, jy, out_sd = result
                correct[(ix, jy)] = out_sd

    # 合并各块站点 → Micaps3
    merged = _rect(sta, cll[0], clr[-1], clb[0], clt[-1])
    for key in sorted(correct.keys(), key=lambda x: (x[1], x[0])):
        merged.read_from_scatter_data(correct[key])
    sd2 = merged.copy_scatter_data()
    head3 = date_replace(
        "diamond 3 YYYY年MM月DD日HH时VVV时效001小时降水预报场 00 01 04 08  -1 0 1 0 0",
        dt_input1,
        i_valid,
    )
    sd2.clear_to_num_less_than(0.0, 0.01)
    sd2.writer_to_micaps3(p3, head3)

    # 稀疏背景点 + 订正站 → Cressman → 二次频率匹配 → Micaps4
    pts: list[PointData] = []
    for j in range(0, mask.yn, grid_cfg.background_stride):
        for i in range(0, mask.xn, grid_cfg.background_stride):
            if mask.val[j, i] < 0.0:
                pts.append(
                    PointData(
                        f"bg_{i}_{j}",
                        float(gd_cur.lon[i]),
                        float(gd_cur.lat[j]),
                        float(gd_cur.val[j, i]),
                    )
                )
    pts.extend(PointData(p.id, p.lon, p.lat, p.val) for p in sd2.sta_data)
    g1 = SpatialAnalysis.gressman_interpolation_for_rain(
        ScatterData(pts), gd_cur.copy_grid_data(), [0.6, 0.4, 0.2, 0.1]
    )
    g1.smooth9(10)
    sd4 = sta.copy_scatter_data()
    sd4.clear_to_num(0.0)
    sd4.bilinear_interpolation_from_grid_data(g1)
    ml, fu = FrequencyMatch.get_used_model_level(
        [sd4], [sd2], final_fact_level, fact_level_limit=20
    )
    g2 = FrequencyMatch.correct_model_data(g1, fu, ml)
    g2.clear_to_num_less_than(0.0, 0.01)
    out = Path(date_replace(para.output_template, dt_input1, i_valid))
    g2.write_val_to_micaps4(str(out) + ".m4", dt_input=dt_input1, i_valid=i_valid)
    return None


def _process_cycle(
    env_paths: RunEnvPaths,
    para: ParaConfig,
    dt_input1: datetime,
    fact_level: list[float],
    similar_level: list[float],
    final_fact_level: list[float],
    sample_workers_cap: int,
    block_workers_cap: int,
    grid_cfg: GridConfig,
    fixed_seed: int | None = None,
    valid_workers: int | None = None,
) -> list[str]:
    """
    对单个起报循环时效 1–48 h；时效维可多进程，失败时回退串行。

    ``valid_workers`` 为 ``None`` 时读环境变量 ``QPF_VALID_PROCESS_WORKERS``；
    起报层 ``is_multi`` 开启时建议传 ``1``，避免嵌套进程池。
    """
    errors: list[str] = []
    valid_jobs = list(range(1, 49))
    if valid_workers is None:
        valid_workers_default = min(max(1, (os.cpu_count() or 1) // 2), 8)
        valid_workers = _get_env_int(
            "QPF_VALID_PROCESS_WORKERS",
            valid_workers_default,
            lower=1,
            upper=max(1, os.cpu_count() or 1),
        )
        if _is_nc_template(para.model_template):
            valid_workers = 1
    else:
        valid_workers = max(1, int(valid_workers))
        if _is_nc_template(para.model_template):
            valid_workers = 1
    if valid_workers <= 1:
        for i_valid in valid_jobs:
            try:
                err = _process_one_valid(
                    env_paths,
                    para,
                    dt_input1,
                    i_valid,
                    fact_level,
                    similar_level,
                    final_fact_level,
                    sample_workers_cap,
                    block_workers_cap,
                    grid_cfg,
                    fixed_seed,
                )
                if err:
                    errors.append(err)
            except Exception as exc:
                errors.append(str(exc))
        return errors
    workers = min(valid_workers, len(valid_jobs))
    try:
        spawn_ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=spawn_ctx) as executor:
            futures = {
                executor.submit(
                    _process_one_valid,
                    env_paths,
                    para,
                    dt_input1,
                    i_valid,
                    fact_level,
                    similar_level,
                    final_fact_level,
                    sample_workers_cap,
                    block_workers_cap,
                    grid_cfg,
                    fixed_seed,
                ): i_valid
                for i_valid in valid_jobs
            }
            for future in as_completed(futures):
                try:
                    err = future.result()
                    if err:
                        errors.append(err)
                except Exception as exc:
                    errors.append(str(exc))
    except BrokenProcessPool as exc:
        errors.append(
            f"ProcessPool broken at cycle {dt_input1:%Y%m%d%H}, fallback to serial: {exc}"
        )
        for i_valid in valid_jobs:
            try:
                err = _process_one_valid(
                    env_paths,
                    para,
                    dt_input1,
                    i_valid,
                    fact_level,
                    similar_level,
                    final_fact_level,
                    sample_workers_cap,
                    block_workers_cap,
                    grid_cfg,
                    fixed_seed,
                )
                if err:
                    errors.append(err)
            except Exception as serial_exc:
                errors.append(str(serial_exc))
    return errors


def _process_cycle_worker(
    env_paths: RunEnvPaths,
    para: ParaConfig,
    fact_level: list[float],
    similar_level: list[float],
    final_fact_level: list[float],
    sample_workers_cap: int,
    block_workers_cap: int,
    grid_cfg: GridConfig,
    fixed_seed: Optional[int] = None,
    valid_workers: Optional[int] = None,
    **params,
) -> list[str]:
    """多进程 worker：处理一个起报 ``dt_input1``（``params['param']``）。"""
    case = params["param"]
    dt_input1 = case["dt_input1"]
    if isinstance(dt_input1, str):
        dt_input1 = datetime.strptime(dt_input1, "%Y%m%d%H%M")
    return _process_cycle(
        env_paths,
        para,
        dt_input1,
        fact_level,
        similar_level,
        final_fact_level,
        sample_workers_cap,
        block_workers_cap,
        grid_cfg,
        fixed_seed,
        valid_workers,
    )


def _process_multi_cycles(
    cases: list[dict],
    pro_count: int,
    fixed_params: dict,
) -> list[list[str]]:
    """多进程批量处理多个起报时刻（参考 mait24 ``SimpleParallelTool`` 用法）。"""
    sw_all = datetime.now()
    parallel_tool = SimpleParallelTool(
        target_func=_process_cycle_worker,
        parallel_mode="async",
        with_return=True,
        num_process=pro_count,
        fixed_params=fixed_params,
    )
    raw = parallel_tool.process({"param": cases})
    print(">>> Time elasped: " + str((datetime.now() - sw_all).total_seconds()))
    if raw is None:
        return []
    return [item if isinstance(item, list) else [] for item in raw]


def _resolve_para(
    data_key: Optional[str],
    configs: dict[str, ParaConfig],
    default_key: Optional[str],
    log: Log,
) -> ParaConfig:
    key = (data_key or "").strip() or None
    if key is None:
        if default_key and default_key in configs:
            key = default_key
        elif len(configs) == 1:
            key = next(iter(configs.keys()))
        else:
            log.write_error("Data Key Is Not Specified!", 1)
            raise RuntimeError("Data Key Is Not Specified!")
    para = configs.get(key)
    if para is None:
        log.write_error(f"Data Key Is Not Exist! key={key}", 1)
        raise RuntimeError(f"Data Key Is Not Exist! key={key}")
    return para


def _normalize_run_times(
    run_times: Optional[Sequence[Union[str, datetime]]], log: Log
) -> list[datetime]:
    if run_times is None:
        return [datetime.now()]
    tokens: list[str] = []
    dts: list[datetime] = []
    for item in run_times:
        if isinstance(item, datetime):
            dts.append(item)
        else:
            tokens.append(str(item).strip())
    if dts and tokens:
        log.write_error("Date Args Content Is Not Right!", 1)
        raise RuntimeError("Date Args Content Is Not Right!")
    if dts:
        return sorted(dts)
    return _parse_runtime(tokens, log)


def process(
    *,
    data_key: Optional[str] = None,
    run_times: Optional[Sequence[Union[str, datetime]]] = None,
    sample_workers: Optional[int] = None,
    block_workers: Optional[int] = None,
    fixed_seed: Optional[int] = None,
    is_multi: bool = False,
    pro_count: int = 4,
) -> int:
    """
    逐 1 小时降水频率匹配订正主入口（供模块调度）。

    Parameters
    ----------
    data_key :
        ``resource/path.json`` 中的模式键（如 ``ecmwf``）；``None`` 时用 json 的 default。
    run_times :
        运行时刻列表。元素为 ``datetime`` 或 ``YYYYMMDDHHMM`` 字符串；
        传两个时刻表示闭区间、步长 1h；``None`` 表示当前时刻。
    sample_workers / block_workers :
        历史样本读数 / 分块订正**线程**上限；``None`` 时读环境变量或默认值。
    fixed_seed :
        固定随机种子；``None`` 时读 ``QPF_FIXED_RANDOM_SEED``。
    is_multi :
        多起报（展开后的 ``cycles``）是否用进程池并行；仅当 cycle 数 > 1 时生效。
        开启时起报内时效维强制串行（``valid_workers=1``），避免嵌套进程池。
    pro_count :
        起报层多进程并行数（``is_multi=True`` 时使用）。

    Notes
    -----
    并行层次（由外到内）：
    1. ``is_multi``：多起报 ``cycles`` — ``SimpleParallelTool`` 进程池
    2. 单起报内时效 1–48h — 环境变量 ``QPF_VALID_PROCESS_WORKERS``（起报多进程时关闭）
    3. 样本读数 / 空间分块 — 线程池（``sample_workers`` / ``block_workers``）
    """
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print("+++++  Rain Forecast V2021                   +++++++++")
    print("+++++  Create By CaoYong 2021.02.23          +++++++++")
    print("+++++  QQ:403637605                          +++++++++")
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    t0 = time.perf_counter()
    base = repo_root()
    os.chdir(base)
    env_paths = get_env_paths()
    log = Log(date_replace(str(env_paths.log_file_template), datetime.now(), 0))
    configs, default_key = _load_path_configs(base, log)
    para = _resolve_para(data_key, configs, default_key, log)
    run_dts = _normalize_run_times(run_times, log)
    grid_cfg = _load_grid_config(base, log)
    print(para, run_dts, grid_cfg)
    print(f"Selected data key: {para.name}")
    fact_level = FACT_LEVEL
    similar_level = SIMILAR_LEVEL
    final_fact_level = FINAL_FACT_LEVEL
    sample_workers_cap = (
        sample_workers
        if sample_workers is not None
        else _get_env_int("QPF_SAMPLE_THREADS", 4, lower=1, upper=8)
    )
    block_workers_cap = (
        block_workers
        if block_workers is not None
        else _get_env_int("QPF_BLOCK_THREADS", 1, lower=1, upper=8)
    )
    if fixed_seed is None:
        fixed_seed = _get_optional_env_int("QPF_FIXED_RANDOM_SEED")
    # 业务约定：每个 run_dt 展开为过去 25 个整点（含时区 -8h）作为订正起报循环
    cycles = list(
        dict.fromkeys(
            run_dt - timedelta(hours=h + 8) for run_dt in run_dts for h in range(25)
        )
    )
    print(f"cycles={len(cycles)} is_multi={is_multi} pro_count={pro_count}")

    # 起报层多进程时关闭时效维进程池，避免进程数爆炸
    cycle_valid_workers = 1 if (is_multi and len(cycles) > 1) else None
    common = dict(
        env_paths=env_paths,
        para=para,
        fact_level=fact_level,
        similar_level=similar_level,
        final_fact_level=final_fact_level,
        sample_workers_cap=sample_workers_cap,
        block_workers_cap=block_workers_cap,
        grid_cfg=grid_cfg,
        fixed_seed=fixed_seed,
        valid_workers=cycle_valid_workers,
    )

    if len(cycles) == 1 or not is_multi:
        for dt_input1 in cycles:
            for err in _process_cycle(
                env_paths,
                para,
                dt_input1,
                fact_level,
                similar_level,
                final_fact_level,
                sample_workers_cap,
                block_workers_cap,
                grid_cfg,
                fixed_seed,
                cycle_valid_workers,
            ):
                log.write_error(err, 1)
    else:
        cases = [{"dt_input1": dt} for dt in cycles]
        for errs in _process_multi_cycles(cases, pro_count=pro_count, fixed_params=common):
            for err in errs:
                log.write_error(err, 1)

    log.write_info(f"Time elasped: {time.perf_counter()-t0:.3f}s", 1)
    print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """兼容旧调用：解析位置参数后转 ``process``。推荐使用 ``python -m cli``。"""
    args = list(sys.argv[1:] if argv is None else argv)
    base = repo_root()
    os.chdir(base)
    env_paths = get_env_paths()
    log = Log(date_replace(str(env_paths.log_file_template), datetime.now(), 0))
    configs, default_key = _load_path_configs(base, log)
    para, run_dts = _select_para_and_runtime(args, configs, default_key, log)
    return process(data_key=para.name, run_times=run_dts)


if __name__ == "__main__":
    # 直接运行：在此修改 process 传参即可；命令行请用 python -m cli ...
    raise SystemExit(
        process(
            data_key="ecmwf",
            run_times=None,
            sample_workers=None,
            block_workers=None,
            fixed_seed=None,
            is_multi=False,
            pro_count=4,
        )
    )
