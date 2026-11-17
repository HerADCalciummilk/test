# -*- coding: utf-8 -*-
"""Upload ShowDoc demo PNGs and print URL map."""
from __future__ import annotations

import base64
import json
from pathlib import Path

# This script only prepares base64; MCP upload is done by the agent.
OUT = Path(r"d:\workspace\test\00temp\interpolation_station_grid\resource\showdoc_demo")
names = [
    "sg_before_bg.png",
    "sg_idw_after.png",
    "sg_gauss_after.png",
    "sg_cress_after.png",
    "sg_idw_nobg.png",
    "sg_krig_nobg.png",
    "cli_before.png",
    "cli_after.png",
]
meta = {}
for n in names:
    p = OUT / n
    meta[n] = {
        "path": str(p),
        "size": p.stat().st_size,
        "b64_path": str(OUT / (n + ".b64")),
    }
    (OUT / (n + ".b64")).write_text(base64.b64encode(p.read_bytes()).decode("ascii"), encoding="ascii")
(OUT / "upload_manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print("prepared", len(names), "b64 files")
