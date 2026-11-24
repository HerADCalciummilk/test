"""兼容导入。融合算法在 ``util_plugin``。"""
from linear_scd_multi_time_fusion.src.util_plugin import (
    compute_saliency_map,
    linear_blending_forecast,
)

__all__ = ["compute_saliency_map", "linear_blending_forecast"]
