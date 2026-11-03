# -*- coding: utf-8 -*-
"""更新模板页：粗/细地形同色标 + 粗地形标题含分辨率。"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

MCP = Path(r"C:\Users\38144\.cursor\mcp.json")
UPLOAD = Path(__file__).resolve().parent / "figs" / "upload"
PAGE_ID = "11559060627552402"
URL = "https://www.showdoc.com.cn/mcp.php"


def token() -> str:
    m = re.search(r"Bearer ([a-z0-9_]+)", MCP.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError("no bearer token")
    return m.group(1)


def mcp_call(name: str, arguments: dict, tok: str) -> dict:
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=body,
        headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode()
    text = json.loads(raw)["result"]["content"][0]["text"]
    return json.loads(text)


def main() -> None:
    tok = token()
    urls = json.loads((UPLOAD / "terrain_urls.json").read_text(encoding="utf-8"))
    page = mcp_call("get_page", {"page_id": PAGE_ID}, tok)
    md = page["page_content"]
    h = page["content_hash"]

    replacements = [
        (
            "temperature.attrs[\"units\"] = \"℃\"\norography.attrs[\"units\"] = \"m\"\n\nprint(temperature)\nt_clevs =",
            "temperature.attrs[\"units\"] = \"℃\"\norography.attrs[\"units\"] = \"m\"\nz_clevs = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]\n\nprint(temperature)\nt_clevs =",
        ),
        (
            "orography, save_path=\"z_coarse.png\", title=\"粗网格源地形（m，EC）\",\n    cmap=\"terrain\", show=False,",
            "orography, save_path=\"z_coarse.png\", title=\"粗网格源地形（m，EC 0.1°）\",\n    clevs=z_clevs, cmap=\"terrain\", show=False,",
        ),
        (
            "dest_orog, save_path=\"z_fine.png\", title=\"细网格目标地形（m，1 km DEM）\",\n    cmap=\"terrain\", show=False,",
            "dest_orog, save_path=\"z_fine.png\", title=\"细网格目标地形（m，1 km DEM）\",\n    clevs=z_clevs, cmap=\"terrain\", show=False,",
        ),
        (
            "![粗网格源地形](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=3ad0bdabb638da81ee937384c280991c&file=file.jpg)",
            f"![粗网格源地形]({urls['z_coarse']})",
        ),
        (
            "![细网格目标地形](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=2da32776d113e8e6bf319501ffe23d3c&file=file.jpg)",
            f"![细网格目标地形]({urls['z_fine']})",
        ),
        (
            "粗网格源地形（m）：",
            "粗网格源地形（m，EC 0.1°；与细地形同色标）：",
        ),
        (
            "细网格目标地形（m）：",
            "细网格目标地形（m，1 km DEM；与粗地形同色标）：",
        ),
    ]
    for i, (old, new) in enumerate(replacements):
        if old not in md:
            raise SystemExit(f"MISSING #{i}: {old[:80]!r}")
        md = md.replace(old, new)
        print("OK", i)

    result = mcp_call(
        "update_page",
        {"page_id": PAGE_ID, "page_content": md, "expected_hash": h},
        tok,
    )
    print(result)


if __name__ == "__main__":
    main()
