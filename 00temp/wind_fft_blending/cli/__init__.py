# -*- coding: utf-8 -*-
"""
FFT 特征匹配融合 CLI 包。

- 命令行：``python -m cli`` 或 ``python -m wind_fft_blending main_uv_path=... ass_uv_path=...``
- 未显式传入的参数先读 ``resource/conf.ini``，再没有则用代码预设
- 业务入口：``cli.wind_fft_blending_cli.process``；``from main import process`` 仍转到该入口
"""
