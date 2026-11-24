#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regional 1km fine-grid trial (90–108E / 25–38N)."""

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
    "begin_date": "2026072814",
    "resolution": "1km",
    "para_file": "Fast_refine_interp_1km.ini",
    "model_region": "EC_12P5KM",
    "s3_method": "g_interp",
    "work_dir": str(WORK_DIR),
    "root_path": str(EC_ROOT),
    "site_name": "Station1",
}


def main() -> None:
    plugin = FastRefineInterpPlugin(**CONFIG)
    plugin.process(PQ_shortname="2t", Interp_Time=False, validate=False, Interp_Maxmin=False)
    print("\nAll done (1km regional).")


if __name__ == "__main__":
    main()
