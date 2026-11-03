"""FY-4B AGRI L1 解码命令行。参数定义在 ``fy4b_argi_l1_decoder_cli``。"""
from __future__ import annotations

from .fy4b_argi_l1_decoder_cli import build_parser, fy4b_argi_l1_decoder_cli as main

__all__ = ["build_parser", "main"]
