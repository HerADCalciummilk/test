# -*- coding: utf-8 -*-
"""Insert TCH into the algorithm list and the progress page."""
import json
import re
from pathlib import Path
import requests

mcp = json.loads(Path(r"C:\Users\38144\.cursor\mcp.json").read_text(encoding="utf-8"))
auth = mcp["mcpServers"]["showdoc"]["headers"]["Authorization"]
url = "https://www.showdoc.com.cn/mcp.php"
headers = {"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"}
PENDING = (
    '<span style="display:inline-block;margin:2px 0;padding:1px 6px;border-radius:3px;'
    'background:#e6f4ff;border:1px solid #91caff;color:#0958d9;font-weight:600;">算法完成<br>文档待完善</span>'
)
SYNTH = (
    '<span style="display:inline-block;margin:2px 0;padding:1px 6px;border-radius:3px;'
    'background:#fff1f0;border:1px solid #ffa39e;color:#cf1322;font-weight:700;">自建数据</span>'
)


def rpc(method, params, sid=None):
    h = dict(headers)
    if sid:
        h["Mcp-Session-Id"] = sid
    r = requests.post(url, headers=h, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=180)
    r.raise_for_status()
    return r.headers.get("Mcp-Session-Id"), r.json()


def tool(sid, name, arguments):
    _, data = rpc("tools/call", {"name": name, "arguments": arguments}, sid)
    if "error" in data:
        raise SystemExit(json.dumps(data["error"], ensure_ascii=False)[:1500])
    return json.loads(data["result"]["content"][0]["text"])


def bump(content, start, end):
    region = content[start:end]
    def repl(m):
        n = int(m.group(1))
        if n < 35:
            return m.group(0)
        return "<td>%d</td>" % (n + 1)
    return content[:start] + re.sub(r"<td>(\d+)</td>", repl, region) + content[end:]


def table_span(content, marker):
    i = content.find(marker)
    start = content.rfind("<table", 0, i)
    end = content.find("</table>", i) + len("</table>")
    return start, end


sid, _ = rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "cursor", "version": "1"}})

list_page = tool(sid, "get_page", {"page_id": "11559060627551917"})
content = list_page["page_content"]
ls, le = table_span(content, "optical_flow_nowcast")
print("LIST table", ls, le, "n35", len(re.findall(r"<td>(3[5-9]|[4-9]\d)</td>", content[ls:le])))
anchor = '<td rowspan="4"><strong>5多源融合</strong></td>'
if anchor not in content:
    raise SystemExit("list rowspan anchor missing")
content = content.replace(anchor, '<td rowspan="5"><strong>5多源融合</strong></td>', 1)
row = (
    '<tr><td>34</td><td><a href="https://www.showdoc.com.cn/2598854776811541/11559060627552479">'
    'multi_rain_mait24_blending</a></td><td><code>05blending</code></td>'
    '<td>分区 TS、beta 记忆与频率匹配的 24 小时多源降水融合</td></tr>'
)
insert = (
    row
    + '<tr><td>35</td><td><a href="https://www.showdoc.com.cn/2598854776811541/11559060627870675">'
    'multi_rain_TCH_blending</a></td><td><code>05blending</code></td>'
    '<td>按模式误差做 BTCH 加权的多模式降水融合</td></tr>'
)
if row not in content:
    raise SystemExit("list mait24 row missing")
# bump first so the new 35 is not incremented
content = bump(content, ls, le)
content = content.replace(row, insert, 1)
print("LIST", tool(sid, "update_page", {
    "page_id": "11559060627551917",
    "page_content": content,
    "expected_hash": list_page["content_hash"],
}).get("content_hash"))

prog = tool(sid, "get_page", {"page_id": "11559060627554830"})
p = prog["page_content"]
ps, pe = table_span(p, "optical_flow_nowcast")
print("PROG table", ps, pe, "n35", len(re.findall(r"<td>(3[5-9]|[4-9]\d)</td>", p[ps:pe])))
p_anchor = '<td rowspan="4"><strong>5多源融合</strong></td>'
if p_anchor not in p:
    raise SystemExit("progress rowspan missing")
p = p.replace(p_anchor, '<td rowspan="5"><strong>5多源融合</strong></td>', 1)
i = p.find("multi_rain_mait24_blending")
tr0 = p.rfind("<tr>", 0, i)
tr1 = p.find("</tr>", i) + 5
old_row = p[tr0:tr1]
new_row = old_row
new_row = new_row.replace(">34<", ">35<", 1)
new_row = new_row.replace("11559060627552479", "11559060627870675")
new_row = new_row.replace("multi_rain_mait24_blending", "multi_rain_TCH_blending")
new_row = new_row.replace("郭云谦、曹勇、陈荣", "待填")
new_row = new_row.replace(
    "分区 TS、beta 记忆与频率匹配的 24 小时多源降水融合",
    "按模式误差做 BTCH 加权的多模式降水融合",
)
new_row = re.sub(r"<span style=.*</span>", PENDING + "<br>" + SYNTH, new_row, count=1)
p = bump(p, ps, pe)
# old_row number 34 was not bumped; the stored slice still matches
if old_row not in p:
    raise SystemExit("progress row missing after bump")
p = p.replace(old_row, old_row + new_row, 1)
p = p.replace("核对（2026-11-23）：46 行与算法清单一致。", "核对（2026-11-24）：47 行与算法清单一致。新增 multi_rain_TCH_blending。", 1)
p = p.replace(
    "文档待完善仍为 `stormcast_predict`、`time_lagging`、`unet3d`",
    "文档待完善仍为 `stormcast_predict`、`time_lagging`、`unet3d`、`multi_rain_TCH_blending`",
    1,
)
print("PROG", tool(sid, "update_page", {
    "page_id": "11559060627554830",
    "page_content": p,
    "expected_hash": prog["content_hash"],
}).get("content_hash"))
print("TCH rows", p.count("multi_rain_TCH_blending"))
