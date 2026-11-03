"""QPF 10-minute split plugin."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


class QpfSplitPlugin:
    """Split unet_qpf and mait_st products to aligned 10-minute grids."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path else (
            Path(__file__).resolve().parents[1] / "resource" / "split_config.ini"
        )

    def __call__(self, history_range: Sequence[str] | None = None) -> None:
        return self.process(history_range=history_range)

    def process(self, history_range: Sequence[str] | None = None, config=None) -> None:
        """Run realtime mode or a two-value UTC history range.

        ``config`` 给出时本次改读该 ini。省略时仍用构造时的拆分配置。
        """
        import linear_scd_multi_time_fusion.src.split_workflow as split_workflow

        config_path = Path(config) if config else self.config_path
        args = argparse.Namespace(
            history_range=list(history_range or []),
            config=config_path,
            daemon=False,
        )
        cfg = split_workflow.load_config(config_path)
        split_workflow.run_once(cfg, args)
