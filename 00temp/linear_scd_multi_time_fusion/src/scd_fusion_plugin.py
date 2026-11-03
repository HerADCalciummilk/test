"""SCD pair fusion plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


class ScdFusionPlugin:
    """Fuse split unet_qpf and mait_st files using configured SCD weights."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path else (
            Path(__file__).resolve().parents[1] / "resource" / "scd_pair_fusion_config.ini"
        )

    def __call__(self, history_range: Sequence[str] | None = None) -> None:
        return self.process(history_range=history_range)

    def process(self, history_range: Sequence[str] | None = None) -> None:
        """Run realtime mode or a two-value UTC history range."""
        import linear_scd_multi_time_fusion.src.pair_fusion_workflow as pair_fusion_workflow

        history = list(history_range or [])
        config = pair_fusion_workflow.read_config(self.config_path)
        positional_history = len(history) == 2
        mode = "history" if positional_history else "realtime"
        history_start_utc = history[0] if positional_history else None
        history_end_utc = history[1] if positional_history else None

        dry_run = pair_fusion_workflow.parse_bool(config.get("run", "dry_run", fallback="true"))
        keyframes = pair_fusion_workflow.parse_keyframe_weights(config.get("fusion", "keyframe_weights"))
        pairs = pair_fusion_workflow.build_pairs(config, mode, history_start_utc, history_end_utc)

        if dry_run:
            print("当前为 dry_run，仅检查配对关系；如需写出文件，请将配置 dry_run 改为 false。")
            return

        for index, pair in enumerate(pairs, start=1):
            print(f"[{index}/{len(pairs)}] 融合 {pair.source1_path.name} -> {pair.output_path}")
            pair_fusion_workflow.fuse_one_pair(pair, config, keyframes)
