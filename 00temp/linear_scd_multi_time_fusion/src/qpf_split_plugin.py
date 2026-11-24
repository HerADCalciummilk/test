"""QPF 10-minute split plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from utils.base_plugin import BasePlugin


class QpfSplitPlugin(BasePlugin):
    """Split unet_qpf and mait_st products to aligned 10-minute grids."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path else (
            Path(__file__).resolve().parents[1] / "resource" / "split_config.ini"
        )

    def __call__(self, history_range: Sequence[str] | None = None) -> None:
        return self.process(history_range=history_range)

    def process(
        self,
        history_range: Sequence[str] | None = None,
        config=None,
        daemon: bool = False,
        allowed_realtime_minutes=None,
        history_step_minutes=None,
        dry_run=None,
        max_files=None,
        source1_dir=None,
        source2_dir=None,
        truth_dir=None,
        output_dir=None,
        enabled=None,
        time_step_minutes=None,
        overwrite=None,
        blending_type=None,
        keyframe_weights=None,
        lon_min=None,
        lon_max=None,
        lat_min=None,
        lat_max=None,
        output_var=None,
        output_source=None,
    ) -> None:
        """按配置把两路产品拆成对齐的 10 分钟场。``None`` 不覆盖 ini。"""
        import linear_scd_multi_time_fusion.src.split_workflow as split_workflow

        # 显式参数写入本次配置后，走原拆分流程（含 daemon）
        split_workflow.process(
            history_range=history_range,
            config=Path(config) if config else self.config_path,
            daemon=daemon,
            allowed_realtime_minutes=allowed_realtime_minutes,
            history_step_minutes=history_step_minutes,
            dry_run=dry_run,
            max_files=max_files,
            source1_dir=source1_dir,
            source2_dir=source2_dir,
            truth_dir=truth_dir,
            output_dir=output_dir,
            enabled=enabled,
            time_step_minutes=time_step_minutes,
            overwrite=overwrite,
            blending_type=blending_type,
            keyframe_weights=keyframe_weights,
            lon_min=lon_min,
            lon_max=lon_max,
            lat_min=lat_min,
            lat_max=lat_max,
            output_var=output_var,
            output_source=output_source,
        )
