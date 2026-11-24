# -*- coding: utf-8 -*-
"""快速精细化插值。

``@merge_params`` 合 resource/conf.ini。``config`` 只换这份配置，不改算法 para 文件。
阈值要素形参为 ``_2t`` 等（不能以数字开头），传入插件后写回 ``threshold.2t``。
"""
import os
import sys

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_PARENT = os.path.dirname(_ROOT_DIR)
for _p in (_PARENT, _ROOT_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _ROOT_DIR)
if _PARENT not in sys.path:
    sys.path.insert(1, _PARENT)

from utils.merge_params import merge_params


def _plugin_cls():
    try:
        from nimm_g_interp.src.fast_refine_interp_plugin import FastRefineInterpPlugin
    except ModuleNotFoundError:
        from src.fast_refine_interp_plugin import FastRefineInterpPlugin
    return FastRefineInterpPlugin


@merge_params()
def process(
    work_dir: str = None,
    root_path: str = None,
    model_region: str = "EC_12P5KM",
    s3_method: str = "g_interp",
    para_file: str = "Fast_refine_interp_site.ini",
    resolution: str = "site",
    operation: str = "i",
    begin_date: str = None,
    site_name: str = "Station1",
    debug: int = 0,
    update: int = 0,
    config=None,
    dem_head: str = None,
    dem_format: str = None,
    recall: bool = None,
    interp_time: bool = None,
    validate: bool = None,
    validate_area: str = None,
    del_no_eta: bool = None,
    out_china: bool = None,
    eta_cmn_out: bool = None,
    vr_plot: bool = None,
    rlt_plot: bool = None,
    plot_format: str = None,
    micaps_out: bool = None,
    pq_shortname: str = None,
    interp_maxmin: bool = None,
    maxmin_update: bool = None,
    maxmin_validate: bool = None,
    forecast_time: str = None,
    custom_path: str = None,
    fh_parallel: bool = None,
    fh_max_pcount: int = None,
    fh_di_timeout: int = None,
    fh_ti_timeout: int = None,
    bt_parallel: bool = None,
    bt_max_pcount: int = None,
    bt_timeout: int = None,
    para_parallel: bool = None,
    para_max_pcount: int = None,
    para_timeout: int = None,
    _2t: float = None,
    _2rh: float = None,
    _10ws: float = None,
    _10u: float = None,
    _10v: float = None,
    _2t_max: float = None,
    _2t_min: float = None,
    _2rh_max: float = None,
    _2rh_min: float = None,
    _10ws_max: float = None,
):
    """调度快速精细化插值。``config`` 已由装饰器读入，不再传给算法 para 文件。"""
    _ = config
    if work_dir is None or not str(work_dir).strip():
        raise ValueError("缺少参数: work_dir")
    plugin = _plugin_cls()(
        debug=int(debug or 0),
        update=int(update or 0),
        operation=operation or "i",
        begin_date=begin_date,
        resolution=resolution or "site",
        para_file=para_file or "Fast_refine_interp_site.ini",
        work_dir=work_dir,
        model_region=model_region or "EC_12P5KM",
        root_path=root_path,
        s3_method=s3_method or "g_interp",
        site_name=site_name or "Station1",
    )
    return plugin.process(
        dem_head=dem_head,
        dem_format=dem_format,
        recall=recall,
        Interp_Time=interp_time,
        validate=validate,
        validate_area=validate_area,
        del_no_eta=del_no_eta,
        out_China=out_china,
        eta_cmn_out=eta_cmn_out,
        VR_plot=vr_plot,
        rlt_plot=rlt_plot,
        plot_format=plot_format,
        MICAPS_out=micaps_out,
        PQ_shortname=pq_shortname,
        Interp_Maxmin=interp_maxmin,
        maxmin_update=maxmin_update,
        maxmin_validate=maxmin_validate,
        forecast_time=forecast_time,
        custom_path=custom_path,
        FH_parallel=fh_parallel,
        FH_max_pcount=fh_max_pcount,
        FH_DI_timeout=fh_di_timeout,
        FH_TI_timeout=fh_ti_timeout,
        BT_parallel=bt_parallel,
        BT_max_pcount=bt_max_pcount,
        BT_timeout=bt_timeout,
        Para_parallel=para_parallel,
        Para_max_pcount=para_max_pcount,
        Para_timeout=para_timeout,
        _2t=_2t,
        _2rh=_2rh,
        _10ws=_10ws,
        _10u=_10u,
        _10v=_10v,
        _2t_max=_2t_max,
        _2t_min=_2t_min,
        _2rh_max=_2rh_max,
        _2rh_min=_2rh_min,
        _10ws_max=_10ws_max,
    )
