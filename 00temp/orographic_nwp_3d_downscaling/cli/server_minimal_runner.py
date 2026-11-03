#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal server-style runner for the EC_12P5KM site sample."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from nimm_g_interp.src.fast_refine_interp_plugin import FastRefineInterpPlugin
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.fast_refine_interp_plugin import FastRefineInterpPlugin


CONFIG = {
    "debug": 1,
    "update": 1,
    "operation": "i",
    "begin_date": "2026032213",
    "resolution": "site",
    "para_file": "Fast_refine_interp_site.ini",
    "model_region": "EC_12P5KM",
    "s3_method": "g_interp",
    "work_dir": "/home/nimm/test_g_interp_work/EC_12P5KM",
    "root_path": "/home/nimm/test_g_interp_root",
    "site_name": "Station1",
}


def main() -> None:
    plugin = FastRefineInterpPlugin(**CONFIG)
    plugin.process()
    print("\nAll done.")


if __name__ == "__main__":
    main()