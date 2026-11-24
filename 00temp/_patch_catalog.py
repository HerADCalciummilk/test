# -*- coding: utf-8 -*-
import json
import re
from pathlib import Path
import requests

mcp = json.loads(Path(r"C:\Users\38144\.cursor\mcp.json").read_text(encoding="utf-8"))
auth = mcp["mcpServers"]["showdoc"]["headers"]["Authorization"]
url = "https://www.showdoc.com.cn/mcp.php"
headers = {"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"}


def rpc(method, params, sid=None):
    h = dict(headers)
    if sid:
        h["Mcp-Session-Id"] = sid
    r = requests.post(url, headers=h, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=180)
    r.raise_for_status()
    return r.headers.get("Mcp-Session-Id"), r.json()


def tool(sid, name, arguments):
    _, data = rpc("tools/call", {"name": name, "arguments": arguments}, sid)
    return json.loads(data["result"]["content"][0]["text"])


sid, _ = rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "cursor", "version": "1"}})

old = "Lucas-Kanade 光流估速，半拉格朗日多时效降水外推"
new = "Lucas-Kanade 与窗内 LSQR 估速，半拉格朗日外推；另有度制 Lagrangian 平流"
for pid, name in (("11559060627551917", "list"), ("11559060627554830", "progress")):
    page = tool(sid, "get_page", {"page_id": pid})
    content = page["page_content"]
    print("HASH", name, page.get("content_hash"), "hits", content.count(old))
    if name == "list":
        i = content.find("5多源")
        print(content[max(0, i - 120): i + 500])
        print("---ENDCAT---")
    else:
        print(content[:900])
        print("---ROW---")
        i = content.find("multi_rain_mait24_blending")
        tr0 = content.rfind("<tr>", 0, i)
        tr1 = content.find("</tr>", i)
        print(content[tr0:tr1 + 5])
        print("---COUNTS---")
        for m in re.findall(r".{0,40}(完善|待完善|未建).{0,40}", content[:2500]):
            pass
        print(content[:2500])
    patched = content.replace(old, new, 1)
    res = tool(sid, "update_page", {
        "page_id": pid,
        "page_content": patched,
        "expected_hash": page.get("content_hash"),
    })
    print("UPDATED", name, res.get("content_hash"))
