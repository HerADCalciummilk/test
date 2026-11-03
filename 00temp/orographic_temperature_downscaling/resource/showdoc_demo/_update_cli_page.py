# -*- coding: utf-8 -*-
"""仅替换 CLI 模板页两处「使用示例」+ 页首示例说明；批量调度段不动。"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

DEMO = Path(__file__).resolve().parent
MCP = Path(r"C:\Users\38144\.cursor\mcp.json")
PAGE_ID = "11559060627556703"
URL = "https://www.showdoc.com.cn/mcp.php"


def token() -> str:
    m = re.search(r"Bearer ([a-z0-9_]+)", MCP.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError("no bearer")
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
    urls = json.loads(
        (DEMO / "figs" / "cli" / "upload" / "urls.json").read_text(encoding="utf-8")
    )
    clevs = json.loads((DEMO / "cli_clevs.json").read_text(encoding="utf-8"))
    stdout_g = (DEMO / "cli_stdout_gamma.txt").read_text(encoding="utf-8").rstrip()
    stdout_c = (DEMO / "cli_stdout_t_corr.txt").read_text(encoding="utf-8").rstrip()
    t_clevs = clevs["t_clevs"]
    t_clevs_f = clevs["t_clevs_f"]

    page = mcp_call("get_page", {"page_id": PAGE_ID}, tok)
    md = page["page_content"]
    h = page["content_hash"]

    intro_old = (
        "本页说明如何用 CLI 的 `process` 读文件估 Γ、做地形订正，以及批量调度。"
        "算法参数见插件页。使用示例**固定自建数据**：构造场写盘 → 路径传入 `process` → "
        "print / 画图（与插件页同一合成域）。`main` 默认仍可读 `resource/cli_input` 样例，"
        "但不充当本文示例数据源。"
    )
    intro_new = (
        "本页说明如何用 CLI 的 `process` 读文件估 Γ、做地形订正，以及批量调度。"
        "算法参数见插件页。使用示例读 `resource/showdoc_demo` 裁剪真场（与插件页同域："
        "103–108°E、28–33°N）→ 路径传入 `process` → print / 画图。"
        "`main` 默认仍可读 `resource/cli_input` 样例，但不充当本文示例数据源。"
    )
    if intro_old not in md:
        raise SystemExit("intro not found")
    md = md.replace(intro_old, intro_new)

    how_old = "业务数据请改路径或按下面示例自建后调用 `process`。"
    how_new = "业务数据请改路径，或按下面示例用 `showdoc_demo` 路径调用 `process`。"
    if how_old not in md:
        raise SystemExit("how-run sentence not found")
    md = md.replace(how_old, how_new)

    lapse_ex = f"""**使用示例**

读裁剪样例（`resource/showdoc_demo`：EC 气温 / 源地形 / 掩码，约 0.1°、51×51），路径传入 CLI `process` 估 Γ。

```python
from pathlib import Path
import numpy as np
import meteva_base as meb
from meteva_base.tool.plot_tools import pcolormesh_2d_grid
from orographic_temperature_downscaling.cli.dsc_temp_lapse_rate import process

DEMO = Path("orographic_temperature_downscaling/resource/showdoc_demo")
t_path = str(DEMO / "t_coarse.nc")
z_path = str(DEMO / "z_coarse.nc")
m_path = str(DEMO / "landmask.nc")
g_path = str(DEMO / "demo_gamma.nc")

temperature = meb.read_griddata_from_nc(t_path)
orography = meb.read_griddata_from_nc(z_path)
temperature.attrs["units"] = "℃"
orography.attrs["units"] = "m"

gamma = process(
    t_path,
    orography_path=z_path,
    land_sea_mask_path=m_path,
    output_path=g_path,
    max_height_diff=1200.0,
    nbhood_radius=2,
)
print(gamma)

t_clevs = {t_clevs}
z_clevs = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
g_clevs = [-10.0, -9.0, -8.0, -7.5, -7.0, -6.5, -6.0, -5.5, -5.0, -4.0, -3.0]
pcolormesh_2d_grid(
    temperature, save_path="cli_t_coarse.png", title="粗网格气温（℃，EC 0.1°）",
    clevs=t_clevs, cmap="RdYlBu_r", show=False,
)
pcolormesh_2d_grid(
    orography, save_path="cli_z_coarse.png", title="粗网格源地形（m，EC 0.1°）",
    clevs=z_clevs, cmap="terrain", show=False,
)
pcolormesh_2d_grid(
    gamma * 1000.0, save_path="cli_gamma.png", title="粗网格 Γ（K/km，EC 0.1°）",
    clevs=g_clevs, cmap="coolwarm", show=False,
)
```

```
{stdout_g}
```

粗网格气温（℃，EC 0.1°）：

![粗网格气温]({urls['cli_t_coarse']})

粗网格源地形（m，EC 0.1°；与细地形同色标）：

![粗网格源地形]({urls['cli_z_coarse']})

粗网格 Γ（K/km，EC 0.1°；固定色标）：

![粗网格Gamma]({urls['cli_gamma']})
"""

    apply_ex = f"""**使用示例**

承接上一节粗网格 Γ。将气温 / Γ / 源地形插到 **1 km DEM** 网格并写盘，四路径传入 Apply CLI；目标地形用同域 `z_dest_fine.nc`。

```python
from interp_gg_linear.src.interp_gg_linear import InterpGGLinearPlugin
from orographic_temperature_downscaling.cli.anc_lapse_rate import process

dest_path = str(DEMO / "z_dest_fine.nc")
t_f_path = str(DEMO / "demo_t_fine.nc")
g_f_path = str(DEMO / "demo_gamma_fine.nc")
s_f_path = str(DEMO / "demo_z_src_fine.nc")
corr_path = str(DEMO / "demo_t_corr.nc")

dest_orog = meb.read_griddata_from_nc(dest_path)
dest_orog.attrs["units"] = "m"
dlon = float(np.diff(dest_orog.lon.values[:2])[0])
dlat = float(np.diff(dest_orog.lat.values[:2])[0])
g_f = meb.grid(
    [float(dest_orog.lon.min()), float(dest_orog.lon.max()), dlon],
    [float(dest_orog.lat.min()), float(dest_orog.lat.max()), dlat],
)

interp = InterpGGLinearPlugin(used_coords="xy", outer_value=0.0)
t_fine = interp.process(temperature, g_f)
g_fine = interp.process(gamma, g_f)
src_fine = interp.process(orography, g_f)
t_fine.attrs["units"] = "℃"
g_fine.attrs["units"] = "K m-1"
src_fine.attrs["units"] = "m"
meb.write_griddata_to_nc(t_fine, t_f_path, creat_dir=True)
meb.write_griddata_to_nc(g_fine, g_f_path, creat_dir=True)
meb.write_griddata_to_nc(src_fine, s_f_path, creat_dir=True)

corrected = process(
    t_f_path, g_f_path, s_f_path, dest_path, output_path=corr_path,
)
print(corrected)

t_clevs_f = {t_clevs_f}
pcolormesh_2d_grid(
    dest_orog, save_path="cli_z_fine.png", title="细网格目标地形（m，1 km DEM）",
    clevs=z_clevs, cmap="terrain", show=False,
)
pcolormesh_2d_grid(
    t_fine, save_path="cli_t_before.png", title="插到细网格后的气温（订正前，℃，1 km）",
    clevs=t_clevs_f, cmap="RdYlBu_r", show=False,
)
pcolormesh_2d_grid(
    corrected - 273.15, save_path="cli_t_after.png", title="地形订正后气温（℃，1 km）",
    clevs=t_clevs_f, cmap="RdYlBu_r", show=False,
)
pcolormesh_2d_grid(
    corrected - (t_fine + 273.15), save_path="cli_t_delta.png", title="订正增量（K，1 km）",
    cmap="bwr", show=False,
)
```

```
{stdout_c}
```

细网格目标地形（m，1 km DEM；与粗地形同色标）：

![细网格目标地形]({urls['cli_z_fine']})

插到细网格后的气温（订正前，℃，1 km）：

![订正前]({urls['cli_t_before']})

地形订正后气温（℃，1 km；与上图同色标）：

![订正后]({urls['cli_t_after']})

订正增量（K，1 km）：

![订正增量]({urls['cli_t_delta']})
"""

    # replace first 使用示例 (lapse) — from heading to --- before # anc
    m1 = re.search(
        r"\*\*使用示例\*\*\n\n合成场仅演示[\s\S]*?(?=\n---\n\n# anc_lapse_rate\.py)",
        md,
    )
    if not m1:
        raise SystemExit("lapse 使用示例 block not found")
    md = md[: m1.start()] + lapse_ex.rstrip() + "\n" + md[m1.end() :]

    m2 = re.search(
        r"\*\*使用示例\*\*\n\n承接上一节：气温[\s\S]*?(?=\n---\n\n# 批量调度示例)",
        md,
    )
    if not m2:
        raise SystemExit("apply 使用示例 block not found")
    md = md[: m2.start()] + apply_ex.rstrip() + "\n" + md[m2.end() :]

    if "# 批量调度示例" not in md:
        raise SystemExit("batch section missing after replace")

    result = mcp_call(
        "update_page",
        {"page_id": PAGE_ID, "page_content": md, "expected_hash": h},
        tok,
    )
    print(result)
    (DEMO / "cli_page_preview_tail.md").write_text(
        md[md.find("# 批量调度示例") : md.find("# 批量调度示例") + 200],
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
