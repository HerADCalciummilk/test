# -*- coding: utf-8 -*-
"""
MAIT 1h 运行上下文（``src/utils/util_context.py``）。

主流程在 ``RunProcess._setup_context`` 中读完 ini/站点表后，调用 ``build_run_context``
将内存数据组装为 ``RunContext``，下游函数统一接收 ``ctx``：

- ``ctx.paths`` — 路径模板（local.ini / para_1.ini、para_1_background.ini、beta）
- ``ctx.models`` — 模式键名
- ``ctx.grid`` — 裁剪、分区、算法标量（``area_scale``、``predict_type``）
- ``ctx.session`` — 起报时刻、站点表、日志、实况时区标志

``build_run_context`` 不读文件，仅做参数装箱；**不改变**下游 TS/插值/写出各步的计算公式。
"""
import datetime
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class PathConfig:
    """数据路径模板（模式配置 ini、background ini、beta 目录）。"""

    beta_path_template: str
    fact_path: str
    output_sample_path: str
    model_path: Tuple[str, ...]
    background_templates: Mapping[str, str]


@dataclass(frozen=True)
class ModelConfig:
    """模式标识，键名与模式配置 ini（local.ini / para_1.ini）一致。"""

    model_name: Tuple[str, ...]


@dataclass(frozen=True)
class GridConfig:
    """格点划分、输出裁剪与权重算法标量。"""

    clip_coords: Tuple[float, ...]
    split_lat: int
    split_lon: int
    area_scale: float
    predict_type: int


@dataclass
class SessionContext:
    """单次运行的时次与站点上下文（含可变对象）。"""

    dt_now: datetime.datetime
    sd_sta_info: Any
    is_obs_bjt: bool
    simple_log: Any = None


@dataclass
class RunContext:
    """全流程运行上下文，按职责分层。"""

    paths: PathConfig
    models: ModelConfig
    grid: GridConfig
    session: SessionContext

    def dt_search_base(self) -> datetime.datetime:
        """模式检索与 Micaps 写出时间基准：is_obs_bjt 时为 dt_now 减 8 小时（业务约定，未改）。"""
        offset = 8 if self.session.is_obs_bjt else 0
        return self.session.dt_now - datetime.timedelta(hours=offset)


def build_run_context(
    *,
    beta_path_template: str,
    is_obs_bjt: bool,
    clip_coords: Sequence[float],
    split_lat: int,
    split_lon: int,
    dt_now: datetime.datetime,
    sd_sta_info: Any,
    model_name: Sequence[str],
    model_path: Sequence[str],
    fact_path: str,
    output_sample_path: str,
    background_templates: Mapping[str, str],
    simple_log: Any = None,
    area_scale: float = 0.5,
    predict_type: int = 1,
) -> RunContext:
    """将 ``_setup_context`` 已解析的参数组装为 ``RunContext``（无文件 IO）。"""
    return RunContext(
        paths=PathConfig(
            beta_path_template=beta_path_template,
            fact_path=fact_path,
            output_sample_path=output_sample_path,
            model_path=tuple(model_path),
            background_templates=dict(background_templates),
        ),
        models=ModelConfig(model_name=tuple(model_name)),
        grid=GridConfig(
            clip_coords=tuple(clip_coords),
            split_lat=split_lat,
            split_lon=split_lon,
            area_scale=area_scale,
            predict_type=predict_type,
        ),
        session=SessionContext(
            dt_now=dt_now,
            sd_sta_info=sd_sta_info,
            is_obs_bjt=is_obs_bjt,
            simple_log=simple_log,
        ),
    )
