"""Plugin wrapper for fast refined interpolation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_THRESHOLD_KEYS = (
    "2t",
    "2rh",
    "10ws",
    "10u",
    "10v",
    "2t_max",
    "2t_min",
    "2rh_max",
    "2rh_min",
    "10ws_max",
)


@dataclass
class FastRefineInterpPlugin:
    """快速精细化插值插件。

    插件只负责接收显式参数并调用算法入口；具体的模式数据、地形数据、
    站点文件和业务配置仍按原算法的配置文件规则读取。
    """

    debug: int = 0
    update: int = 0
    operation: str = "i"
    begin_date: str | None = None
    resolution: str = "site"
    para_file: str = "Fast_refine_interp_site.ini"
    work_dir: str | Path | None = None
    model_region: str = "EC_12P5KM"
    root_path: str | Path | None = None
    s3_method: str = "g_interp"
    site_name: str = "Station1"
    # 键为 ``节.键``，例如 ``InstantInfo.dem_head``、``MaxMinInfo.update``、``threshold.2t``。
    # process() 的同名参数若不是 None，会盖过这里的值。
    ini_overrides: dict | None = None

    def process(
        self,
        config: str | None = None,
        dem_head=None,
        dem_format=None,
        recall=None,
        Interp_Time=None,
        validate=None,
        validate_area=None,
        del_no_eta=None,
        out_China=None,
        eta_cmn_out=None,
        VR_plot=None,
        rlt_plot=None,
        plot_format=None,
        MICAPS_out=None,
        PQ_shortname=None,
        Interp_Maxmin=None,
        maxmin_update=None,
        maxmin_validate=None,
        forecast_time=None,
        custom_path=None,
        FH_parallel=None,
        FH_max_pcount=None,
        FH_DI_timeout=None,
        FH_TI_timeout=None,
        BT_parallel=None,
        BT_max_pcount=None,
        BT_timeout=None,
        Para_parallel=None,
        Para_max_pcount=None,
        Para_timeout=None,
        **threshold,
    ):
        """Run fast refined interpolation with the configured parameters.

        ``config`` 给出时作为本次算法参数 ini（绝对路径传入 ``para_file``），
        返回前恢复默认 ini。省略时仍用 ``para_file``。

        其余参数对应 resource/conf.ini。``None`` 表示用 ini；ini 缺键时用 conf.ini 里的预设。
        ``validate`` 是 InstantInfo.validate，``maxmin_validate`` 是 MaxMinInfo.validate。
        ``maxmin_update`` 是 MaxMinInfo.update，与构造参数 ``update``（0/1 强制更新）不是同一项。
        阈值键 ``2t``、``2rh``、``10ws``、``10u``、``10v``、``2t_max``、``2t_min``、
        ``2rh_max``、``2rh_min``、``10ws_max`` 用关键字传入。
        """
        from .fast_refine_interp import run_fast_refine

        unknown = sorted(set(threshold) - _THRESHOLD_KEYS)
        if unknown:
            names = ", ".join(unknown)
            raise TypeError(f"未知参数: {names}")

        overrides = {}
        if self.ini_overrides:
            for key, value in self.ini_overrides.items():
                if value is not None:
                    overrides[key] = value
        named = {
            "InstantInfo.dem_head": dem_head,
            "InstantInfo.dem_format": dem_format,
            "InstantInfo.recall": recall,
            "InstantInfo.Interp_Time": Interp_Time,
            "InstantInfo.validate": validate,
            "InstantInfo.validate_area": validate_area,
            "InstantInfo.del_no_eta": del_no_eta,
            "InstantInfo.out_China": out_China,
            "InstantInfo.eta_cmn_out": eta_cmn_out,
            "InstantInfo.VR_plot": VR_plot,
            "InstantInfo.rlt_plot": rlt_plot,
            "InstantInfo.plot_format": plot_format,
            "InstantInfo.MICAPS_out": MICAPS_out,
            "InstantInfo.PQ_shortname": PQ_shortname,
            "MaxMinInfo.Interp_Maxmin": Interp_Maxmin,
            "MaxMinInfo.update": maxmin_update,
            "MaxMinInfo.validate": maxmin_validate,
            "MaxMinInfo.forecast_time": forecast_time,
            "SiteInfo.custom_path": custom_path,
            "PoolInfo.FH_parallel": FH_parallel,
            "PoolInfo.FH_max_pcount": FH_max_pcount,
            "PoolInfo.FH_DI_timeout": FH_DI_timeout,
            "PoolInfo.FH_TI_timeout": FH_TI_timeout,
            "PoolInfo.BT_parallel": BT_parallel,
            "PoolInfo.BT_max_pcount": BT_max_pcount,
            "PoolInfo.BT_timeout": BT_timeout,
            "PoolInfo.Para_parallel": Para_parallel,
            "PoolInfo.Para_max_pcount": Para_max_pcount,
            "PoolInfo.Para_timeout": Para_timeout,
        }
        for key, value in named.items():
            if value is not None:
                overrides[key] = value
        for key in _THRESHOLD_KEYS:
            value = threshold.get(key)
            if value is not None:
                overrides["threshold." + key] = value

        para_file = self.para_file
        if config:
            from utils.util_env import set_main_ini

            para_file = set_main_ini(config)
        try:
            return run_fast_refine(
                debug=self.debug,
                update=self.update,
                operation=self.operation,
                begin_date=self.begin_date,
                resolution=self.resolution,
                para_file=para_file,
                work_dir=str(self.work_dir) if self.work_dir is not None else None,
                model_region=self.model_region,
                root_path=str(self.root_path) if self.root_path is not None else None,
                s3_method=self.s3_method,
                site_name=self.site_name,
                overrides=overrides or None,
            )
        finally:
            if config:
                from utils.util_env import set_main_ini

                set_main_ini(None)
