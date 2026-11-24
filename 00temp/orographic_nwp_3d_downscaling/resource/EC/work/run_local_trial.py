#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local EC trial runner for resource/EC prepared data."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fast_refine_interp_plugin import FastRefineInterpPlugin

EC_ROOT = Path(__file__).resolve().parents[1]
WORK_DIR = Path(__file__).resolve().parent

CONFIG = {
    "debug": 1,
    "update": 1,
    "operation": "i",
    # 业务时刻→EC 北京时 08 起报；文件为 UTC 命名 2026072800.006.nc
    "begin_date": "2026072814",
    "resolution": "site",
    "para_file": "Fast_refine_interp_site.ini",
    "model_region": "EC_12P5KM",
    "s3_method": "g_interp",
    "work_dir": str(WORK_DIR),
    "root_path": str(EC_ROOT),
    "site_name": "Station1",
}


def main() -> None:
    plugin = FastRefineInterpPlugin(**CONFIG)
    plugin.process()
    print("\nAll done.")


if __name__ == "__main__":
    main()
