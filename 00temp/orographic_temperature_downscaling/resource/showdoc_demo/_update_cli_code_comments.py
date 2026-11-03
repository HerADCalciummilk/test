# -*- coding: utf-8 -*-
"""为 CLI 页两处使用示例代码补充注释（路径注明分辨率）；批量调度不动。"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

MCP = Path(r"C:\Users\38144\.cursor\mcp.json")
PAGE_ID = "11559060627556703"
URL = "https://www.showdoc.com.cn/mcp.php"

LAPSE_CODE_OLD = '''```python
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

t_clevs = [0.1, 1.97, 3.85, 5.72, 7.59, 9.46, 11.34, 13.21, 15.08, 16.95, 18.83, 20.7]
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
```'''

LAPSE_CODE_NEW = '''```python
from pathlib import Path
import numpy as np
import meteva_base as meb
from meteva_base.tool.plot_tools import pcolormesh_2d_grid
from orographic_temperature_downscaling.cli.dsc_temp_lapse_rate import process

# 样例根目录：与插件页同域裁剪真场（103–108°E、28–33°N）
DEMO = Path("orographic_temperature_downscaling/resource/showdoc_demo")
# ---- 粗网格路径（EC，约 0.1°，51×51）----
t_path = str(DEMO / "t_coarse.nc")       # 气温（℃），EC 0.1°
z_path = str(DEMO / "z_coarse.nc")       # 源地形（m），EC 0.1°
m_path = str(DEMO / "landmask.nc")       # 海陆掩码，与 EC 同网格
g_path = str(DEMO / "demo_gamma.nc")     # 输出：粗网格 Γ（K m-1），EC 0.1°

# 读入后补 units，供插件内部换算（℃→K、m）
temperature = meb.read_griddata_from_nc(t_path)
orography = meb.read_griddata_from_nc(z_path)
temperature.attrs["units"] = "℃"
orography.attrs["units"] = "m"

# CLI：路径入参估 Γ（邻域参数与插件页示例一致）
gamma = process(
    t_path,
    orography_path=z_path,
    land_sea_mask_path=m_path,
    output_path=g_path,
    max_height_diff=1200.0,
    nbhood_radius=2,
)
print(gamma)

# 作图：气温 / 地形 / Γ；地形色标与细网格 DEM 共用
t_clevs = [0.1, 1.97, 3.85, 5.72, 7.59, 9.46, 11.34, 13.21, 15.08, 16.95, 18.83, 20.7]
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
```'''

APPLY_CODE_OLD = '''```python
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

t_clevs_f = [0.43, 2.27, 4.11, 5.95, 7.79, 9.62, 11.46, 13.3, 15.14, 16.98, 18.82, 20.66]
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
```'''

APPLY_CODE_NEW = '''```python
from interp_gg_linear.src.interp_gg_linear import InterpGGLinearPlugin
from orographic_temperature_downscaling.cli.anc_lapse_rate import process

# ---- 细网格路径（1 km；同域约 501×501；Apply 四场须同网格）----
dest_path = str(DEMO / "z_dest_fine.nc")     # 目标地形（m），1 km DEM
t_f_path = str(DEMO / "demo_t_fine.nc")      # 写盘：气温插到 1 km（℃）
g_f_path = str(DEMO / "demo_gamma_fine.nc")  # 写盘：Γ 插到 1 km（K m-1）
s_f_path = str(DEMO / "demo_z_src_fine.nc")  # 写盘：源地形插到 1 km（m）
corr_path = str(DEMO / "demo_t_corr.nc")     # 输出：订正气温（K），1 km

# 由 1 km DEM 坐标构造目标网格（Apply 本身不做重网格）
dest_orog = meb.read_griddata_from_nc(dest_path)
dest_orog.attrs["units"] = "m"
dlon = float(np.diff(dest_orog.lon.values[:2])[0])  # ≈0.01°
dlat = float(np.diff(dest_orog.lat.values[:2])[0])
g_f = meb.grid(
    [float(dest_orog.lon.min()), float(dest_orog.lon.max()), dlon],
    [float(dest_orog.lat.min()), float(dest_orog.lat.max()), dlat],
)

# 粗场（EC 0.1°）→ 细网格（1 km），再写盘供 CLI 读路径
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

# CLI：四路径 Apply（气温 / Γ / 源地形 / 目标 DEM，均为 1 km）
corrected = process(
    t_f_path, g_f_path, s_f_path, dest_path, output_path=corr_path,
)
print(corrected)

# 作图：地形与粗网格共用 z_clevs；订正前/后共用气温色标
t_clevs_f = [0.43, 2.27, 4.11, 5.95, 7.79, 9.62, 11.46, 13.3, 15.14, 16.98, 18.82, 20.66]
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
```'''


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
    page = mcp_call("get_page", {"page_id": PAGE_ID}, tok)
    md = page["page_content"]
    h = page["content_hash"]

    if "# 批量调度示例" not in md:
        raise SystemExit("batch section missing")

    for label, old, new in [
        ("lapse", LAPSE_CODE_OLD, LAPSE_CODE_NEW),
        ("apply", APPLY_CODE_OLD, APPLY_CODE_NEW),
    ]:
        if old not in md:
            raise SystemExit(f"{label} code block not found")
        md = md.replace(old, new, 1)
        print("ok", label)

    if "# 批量调度示例" not in md:
        raise SystemExit("batch section lost")

    result = mcp_call(
        "update_page",
        {"page_id": PAGE_ID, "page_content": md, "expected_hash": h},
        tok,
    )
    print(result)


if __name__ == "__main__":
    main()
