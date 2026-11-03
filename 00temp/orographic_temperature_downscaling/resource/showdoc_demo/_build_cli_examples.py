# -*- coding: utf-8 -*-
"""跑 CLI process + 出图（对齐插件页 showdoc_demo），供更新 CLI 模板页使用示例。"""
from __future__ import annotations

import base64
import io
import json
import re
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import meteva_base as meb
from meteva_base.tool.plot_tools import pcolormesh_2d_grid
from PIL import Image

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from interp_gg_linear.src.interp_gg_linear import InterpGGLinearPlugin
from orographic_temperature_downscaling.cli.anc_lapse_rate import (
    process as apply_process,
)
from orographic_temperature_downscaling.cli.dsc_temp_lapse_rate import (
    process as lapse_process,
)

DEMO = Path(__file__).resolve().parent
FIG = DEMO / "figs" / "cli"
UPLOAD = FIG / "upload"
FIG.mkdir(parents=True, exist_ok=True)
UPLOAD.mkdir(parents=True, exist_ok=True)

MCP = Path(r"C:\Users\38144\.cursor\mcp.json")
PAGE_ID = "11559060627556703"
ITEM_ID = "2598854776811541"
URL = "https://www.showdoc.com.cn/mcp.php"

Z_CLEVS = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
G_CLEVS = [-10.0, -9.0, -8.0, -7.5, -7.0, -6.5, -6.0, -5.5, -5.0, -4.0, -3.0]


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


def save_jpg(png: Path, stem: str) -> None:
    im = Image.open(png).convert("RGB")
    w, h = im.size
    nw = 560
    im = im.resize((nw, int(h * nw / w)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=48, optimize=True)
    raw = buf.getvalue()
    (UPLOAD / f"{stem}.jpg").write_bytes(raw)
    (UPLOAD / f"{stem}.b64.txt").write_text(
        base64.b64encode(raw).decode("ascii"), encoding="ascii"
    )


def clean_stdout(da) -> str:
    return str(da).replace("np.int64(0)", "0")


def main() -> None:
    # paths relative style for page; absolute for local run
    t_path = DEMO / "t_coarse.nc"
    z_path = DEMO / "z_coarse.nc"
    m_path = DEMO / "landmask.nc"
    g_path = DEMO / "demo_gamma.nc"
    dest_path = DEMO / "z_dest_fine.nc"
    t_f_path = DEMO / "demo_t_fine.nc"
    g_f_path = DEMO / "demo_gamma_fine.nc"
    s_f_path = DEMO / "demo_z_src_fine.nc"
    corr_path = DEMO / "demo_t_corr.nc"

    temperature = meb.read_griddata_from_nc(str(t_path))
    orography = meb.read_griddata_from_nc(str(z_path))
    temperature.attrs["units"] = "℃"
    orography.attrs["units"] = "m"

    gamma = lapse_process(
        str(t_path),
        orography_path=str(z_path),
        land_sea_mask_path=str(m_path),
        output_path=str(g_path),
        max_height_diff=1200.0,
        nbhood_radius=2,
    )
    (DEMO / "cli_stdout_gamma.txt").write_text(clean_stdout(gamma), encoding="utf-8")

    t_clevs = list(
        np.linspace(
            float(np.nanpercentile(temperature.values, 2)),
            float(np.nanpercentile(temperature.values, 98)),
            12,
        )
    )
    pcolormesh_2d_grid(
        temperature,
        save_path=str(FIG / "cli_t_coarse.png"),
        title="粗网格气温（℃，EC 0.1°）",
        clevs=t_clevs,
        cmap="RdYlBu_r",
        show=False,
    )
    pcolormesh_2d_grid(
        orography,
        save_path=str(FIG / "cli_z_coarse.png"),
        title="粗网格源地形（m，EC 0.1°）",
        clevs=Z_CLEVS,
        cmap="terrain",
        show=False,
    )
    pcolormesh_2d_grid(
        gamma * 1000.0,
        save_path=str(FIG / "cli_gamma.png"),
        title="粗网格 Γ（K/km，EC 0.1°）",
        clevs=G_CLEVS,
        cmap="coolwarm",
        show=False,
    )

    dest_orog = meb.read_griddata_from_nc(str(dest_path))
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
    meb.write_griddata_to_nc(t_fine, str(t_f_path), creat_dir=True)
    meb.write_griddata_to_nc(g_fine, str(g_f_path), creat_dir=True)
    meb.write_griddata_to_nc(src_fine, str(s_f_path), creat_dir=True)

    corrected = apply_process(
        str(t_f_path),
        str(g_f_path),
        str(s_f_path),
        str(dest_path),
        output_path=str(corr_path),
    )
    (DEMO / "cli_stdout_t_corr.txt").write_text(
        clean_stdout(corrected), encoding="utf-8"
    )

    t_clevs_f = list(
        np.linspace(
            float(np.nanpercentile(t_fine.values, 2)),
            float(np.nanpercentile(t_fine.values, 98)),
            12,
        )
    )
    pcolormesh_2d_grid(
        dest_orog,
        save_path=str(FIG / "cli_z_fine.png"),
        title="细网格目标地形（m，1 km DEM）",
        clevs=Z_CLEVS,
        cmap="terrain",
        show=False,
    )
    pcolormesh_2d_grid(
        t_fine,
        save_path=str(FIG / "cli_t_before.png"),
        title="插到细网格后的气温（订正前，℃，1 km）",
        clevs=t_clevs_f,
        cmap="RdYlBu_r",
        show=False,
    )
    pcolormesh_2d_grid(
        corrected - 273.15,
        save_path=str(FIG / "cli_t_after.png"),
        title="地形订正后气温（℃，1 km）",
        clevs=t_clevs_f,
        cmap="RdYlBu_r",
        show=False,
    )
    pcolormesh_2d_grid(
        corrected - (t_fine + 273.15),
        save_path=str(FIG / "cli_t_delta.png"),
        title="订正增量（K，1 km）",
        cmap="bwr",
        show=False,
    )

    meta = {
        "t_clevs": [round(float(x), 2) for x in t_clevs],
        "t_clevs_f": [round(float(x), 2) for x in t_clevs_f],
    }
    (DEMO / "cli_clevs.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    stems = [
        "cli_t_coarse",
        "cli_z_coarse",
        "cli_gamma",
        "cli_z_fine",
        "cli_t_before",
        "cli_t_after",
        "cli_t_delta",
    ]
    for s in stems:
        save_jpg(FIG / f"{s}.png", s)
        print("fig", s)

    # upload
    tok = token()
    urls = {}
    for s in stems:
        info = mcp_call(
            "upload_attachment",
            {
                "item_id": ITEM_ID,
                "page_id": PAGE_ID,
                "file_name": f"{s}.jpg",
                "file_base64": (UPLOAD / f"{s}.b64.txt").read_text(encoding="ascii"),
            },
            tok,
        )
        urls[s] = info["url"]
        print("up", s, info["file_size"])
    (UPLOAD / "urls.json").write_text(
        json.dumps(urls, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("done")


if __name__ == "__main__":
    main()
