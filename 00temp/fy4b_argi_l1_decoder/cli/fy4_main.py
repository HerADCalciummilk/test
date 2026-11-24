"""兼容旧模块名。参数在 ``fy4b_argi_l1_decoder_cli.process``。"""
from __future__ import annotations

from .fy4b_argi_l1_decoder_cli import process

main = process

__all__ = ["process", "main"]
