# -*- coding: utf-8 -*-
"""所有示例图标题补分辨率，上传并更新模板页。"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

MCP = Path(r"C:\Users\38144\.cursor\mcp.json")
UPLOAD = Path(__file__).resolve().parent / "figs" / "upload"
PAGE_ID = "11559060627552402"
ITEM_ID = "2598854776811541"
URL = "https://www.showdoc.com.cn/mcp.php"
NAMES = [
    "t_coarse",
    "z_coarse",
    "gamma",
    "z_fine",
    "t_before",
    "t_after",
    "t_delta",
]


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
    return json.loads(json.loads(raw)["result"]["content"][0]["text"])


def main() -> None:
    tok = token()
    urls: dict[str, str] = {}
    for n in NAMES:
        info = mcp_call(
            "upload_attachment",
            {
                "item_id": ITEM_ID,
                "page_id": PAGE_ID,
                "file_name": f"{n}.jpg",
                "file_base64": (UPLOAD / f"{n}.b64.txt").read_text(encoding="ascii"),
            },
            tok,
        )
        urls[n] = info["url"]
        print("up", n, info["file_size"])
    (UPLOAD / "all_urls.json").write_text(
        json.dumps(urls, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    page = mcp_call("get_page", {"page_id": PAGE_ID}, tok)
    md = page["page_content"]
    h = page["content_hash"]

    replacements = [
        (
            'title="粗网格气温（℃，EC）"',
            'title="粗网格气温（℃，EC 0.1°）"',
        ),
        (
            'title="粗网格源地形（m，EC 0.1°）"',
            'title="粗网格源地形（m，EC 0.1°）"',
        ),  # already ok; keep for no-op safety
        (
            'title="粗网格 Γ（K/km）"',
            'title="粗网格 Γ（K/km，EC 0.1°）"',
        ),
        (
            'title="细网格目标地形（m，1 km DEM）"',
            'title="细网格目标地形（m，1 km DEM）"',
        ),
        (
            'title="插到细网格后的气温（订正前，℃）"',
            'title="插到细网格后的气温（订正前，℃，1 km）"',
        ),
        (
            'title="地形订正后气温（℃）"',
            'title="地形订正后气温（℃，1 km）"',
        ),
        (
            'title="订正增量（K）"',
            'title="订正增量（K，1 km）"',
        ),
        ("粗网格气温（℃）：", "粗网格气温（℃，EC 0.1°）："),
        (
            "粗网格源地形（m，EC 0.1°；与细地形同色标）：",
            "粗网格源地形（m，EC 0.1°；与细地形同色标）：",
        ),
        ("粗网格 Γ（K/km，固定色标）：", "粗网格 Γ（K/km，EC 0.1°；固定色标）："),
        (
            "细网格目标地形（m，1 km DEM；与粗地形同色标）：",
            "细网格目标地形（m，1 km DEM；与粗地形同色标）：",
        ),
        (
            "插到细网格后的气温（订正前，℃）：",
            "插到细网格后的气温（订正前，℃，1 km）：",
        ),
        ("地形订正后气温（℃）：", "地形订正后气温（℃，1 km）："),
        ("订正增量（K）= 订正后 − 插值场：", "订正增量（K，1 km）= 订正后 − 插值场："),
    ]

    # image URL replacements: match existing markdown image lines by alt text
    img_map = {
        "粗网格气温": urls["t_coarse"],
        "粗网格源地形": urls["z_coarse"],
        "粗网格Γ": urls["gamma"],
        "细网格目标地形": urls["z_fine"],
        "订正前细网格气温": urls["t_before"],
        "订正后气温": urls["t_after"],
        "订正增量": urls["t_delta"],
    }
    for alt, new_url in img_map.items():
        pat = re.compile(rf"!\[{re.escape(alt)}\]\([^)]+\)")
        md2, n = pat.subn(f"![{alt}]({new_url})", md, count=1)
        if n != 1:
            raise SystemExit(f"img replace failed for {alt}: n={n}")
        md = md2
        print("img", alt)

    for i, (old, new) in enumerate(replacements):
        if old == new:
            continue
        if old not in md:
            raise SystemExit(f"MISSING text #{i}: {old!r}")
        md = md.replace(old, new)
        print("txt", i)

    result = mcp_call(
        "update_page",
        {"page_id": PAGE_ID, "page_content": md, "expected_hash": h},
        tok,
    )
    print(result)


if __name__ == "__main__":
    main()
