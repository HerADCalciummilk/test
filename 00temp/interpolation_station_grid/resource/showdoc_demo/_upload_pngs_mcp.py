# -*- coding: utf-8 -*-
"""Upload showdoc_demo PNGs via ShowDoc MCP upload_attachment."""
from __future__ import annotations

import base64
import json
import re
import urllib.request
from pathlib import Path

DEMO = Path(__file__).resolve().parent
MCP = Path(r"C:\Users\38144\.cursor\mcp.json")
URL = "https://www.showdoc.com.cn/mcp.php"
ITEM_ID = "2598854776811541"
PLUGIN_PAGE = "11559060627552458"
CLI_PAGE = "11559060627727594"

FILES = [
    ("sg_obs_sta.png", PLUGIN_PAGE),
    ("sg_before_bg.png", PLUGIN_PAGE),
    ("sg_idw_after.png", PLUGIN_PAGE),
    ("sg_gauss_after.png", PLUGIN_PAGE),
    ("sg_cress_after.png", PLUGIN_PAGE),
    ("sg_krig_after.png", PLUGIN_PAGE),
    ("cli_obs_sta.png", CLI_PAGE),
    ("cli_compare.png", CLI_PAGE),
]


def token() -> str:
    m = re.search(r"Bearer ([a-z0-9_]+)", MCP.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError("no bearer in mcp.json")
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
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read().decode()
    return json.loads(json.loads(raw)["result"]["content"][0]["text"])


def extract_url(info: dict) -> str:
    for k in ("url", "file_url"):
        if info.get(k):
            return str(info[k])
    if info.get("sign"):
        f = info.get("file") or "file.png"
        return f"https://www.showdoc.com.cn/server/api/attachment/visitFile?sign={info['sign']}&file={f}"
    raise KeyError(f"no url in response: {info!r}")


def main() -> None:
    tok = token()
    urls: dict[str, str] = {}
    for name, page_id in FILES:
        b64 = base64.b64encode((DEMO / name).read_bytes()).decode("ascii")
        info = mcp_call(
            "upload_attachment",
            {
                "item_id": ITEM_ID,
                "page_id": page_id,
                "file_name": name,
                "file_base64": b64,
            },
            tok,
        )
        urls[name] = extract_url(info)
        print(name, urls[name])
    out = DEMO / "upload_png_urls.json"
    out.write_text(json.dumps(urls, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()