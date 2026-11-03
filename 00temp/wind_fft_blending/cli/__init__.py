# -*- coding: utf-8 -*-
"""
FFT 特征匹配融合 CLI 包。

- 命令行：``python -m cli --main-uv <主风场.m11> --ass-uv <辅助风场.m11> --output-dir resource/output --output-prefix sample_a``
- 未显式传入的参数先读 ``resource/conf.ini``，再没有则用代码预设
- 业务主程序：``from main import process``；或 ``python src/main.py``（改 ``__main__`` 传参）
"""
