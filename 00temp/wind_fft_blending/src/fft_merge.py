# -*- coding: utf-8 -*-
"""兼容旧导入。算法类在 ``wind_fft_blending_plugin``。"""
try:
    from .wind_fft_blending_plugin import FFTMergePlugin
except ImportError:
    from wind_fft_blending_plugin import FFTMergePlugin

__all__ = ["FFTMergePlugin"]
