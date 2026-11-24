# -*- coding: utf-8 -*-
"""Append Lagrangian and TCH examples to the Word appendix."""
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from lxml import etree
from PIL import Image as PILImage

DOC = Path(r"d:\workspace\test\NIMM算法附录.docx")
LAG_PNG = Path(r"d:\workspace\test\00temp\optical_flow_nowcast\resource\showdoc_demo\figs\lagrangian_1x2.png")
TCH_PNG = Path(r"d:\workspace\test\00temp\multi_rain_TCH_blending\resource\showdoc_demo\figs\tch_1x2.png")
CX = 4895999

LAG_CALL = """import numpy as np
import meteva_base as meb
from optical_flow_nowcast.src import Lagrangian

def grid_of(arr, member):
    ny, nx = arr.shape
    grid = meb.grid(
        [110.0, 110.0 + 0.05 * (nx - 1), 0.05],
        [30.0, 30.0 + 0.05 * (ny - 1), 0.05],
        gtime=["2024061208"], dtime_list=[0], level_list=[0], member_list=[member],
    )
    return meb.grid_data(grid=grid, data=arr.astype(np.float32))

ny, nx = 40, 40
yy, xx = np.mgrid[0:ny, 0:nx]
rain_arr = 18 * np.exp(-((yy - 20) ** 2 + (xx - 12) ** 2) / 32.0)
rain = grid_of(rain_arr, "rain")
u = grid_of(np.full((ny, nx), 0.8, np.float32), "u")
v = grid_of(np.zeros((ny, nx), np.float32), "v")
after = Lagrangian().process(u, v, rain, delta_time=1.0)
with np.printoptions(edgeitems=2, linewidth=120):
    print(after)""".splitlines()

LAG_OUT = """<xarray.DataArray 'data0' (member: 1, level: 1, time: 1, dtime: 1, lat: 40,
                           lon: 40)> Size: 13kB
array([[[[[[-1.17962413e-05, -1.10124019e-05, ...,  2.94727931e-06,  1.52902851e-06],
           [-3.99061686e-05, -3.72544743e-05, ...,  9.97051768e-06,  5.17263675e-06],
           ...,
           [-1.26821552e-04, -1.18394484e-04, ...,  3.16862413e-05,  1.64386056e-05],
           [-3.99061686e-05, -3.72544743e-05, ...,  9.97051768e-06,  5.17263675e-06]]]]]], shape=(1, 1, 1, 1, 40, 40))
Coordinates:
  * member   (member) <U4 16B 'rain'
  * level    (level) float32 4B 0.0
  * time     (time) datetime64[ns] 8B 2024-06-12T08:00:00
  * dtime    (dtime) int32 4B 0
  * lat      (lat) float64 320B 30.0 30.05 30.1 30.15 ... 31.8 31.85 31.9 31.95
  * lon      (lon) float64 320B 110.0 110.0 110.1 110.2 ... 111.8 111.9 112.0""".splitlines()

LAG_PLOT = """import matplotlib.pyplot as plt
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

cmap, _ = get_cmap_and_clevs_by_element_name("rain_1h")
clevs = [0, 0.1, 1, 2, 4, 8, 16, 32]
map_extend = [110.0, 110.0 + 0.05 * 39, 30.0, 30.0 + 0.05 * 39]
axs = meb.creat_axs(
    2, map_extend, ncol=2, width=11.2,
    add_worldmap=False, add_index=True, wspace=1.15, grid=False,
)
meb.add_contourf(axs[0], rain, cmap=cmap, clevs=clevs, cut_colorbar=False, add_colorbar=True)
meb.add_contourf(axs[1], after, cmap=cmap, clevs=clevs, cut_colorbar=False, add_colorbar=True)
axs[0].set_title("外推前降水（mm）", fontsize=10)
axs[1].set_title("Lagrangian 外推后（mm）", fontsize=10)""".splitlines()

TCH_CALL = """import numpy as np
import xarray as xr
import meteva_base as meb
from multi_rain_TCH_blending.src.tch_weight_plugin import TchWeightPlugin
from multi_rain_TCH_blending.src.tch_blend_plugin import TchBlendPlugin

def grid_of(arr, lon0, lat0, dx, member, dtime=24):
    ny, nx = arr.shape
    grid = meb.grid(
        [lon0, lon0 + dx * (nx - 1), dx],
        [lat0, lat0 + dx * (ny - 1), dx],
        gtime=["2024061208"], dtime_list=[dtime], level_list=[0], member_list=[member],
    )
    return meb.grid_data(grid=grid, data=arr.astype(np.float32))

ny, nx = 30, 30
yy, xx = np.mgrid[0:ny, 0:nx]
base = 14 * np.exp(-((yy - 18) ** 2 + (xx - 16) ** 2) / 22.0)
members = [base * 1.45, base * 0.72, base * 1.05]
err = np.array([4.0, 1.2, 2.5])
weights = TchWeightPlugin().get_weight_mul(err)
print("weights", np.round(weights, 4), "err", err)
names = ["ecmwf", "ncep", "grapes"]
parts = [grid_of(arr, 106.0, 28.0, 0.1, name) for name, arr in zip(names, members)]
qpf = xr.concat(parts, dim="member")
blended = TchBlendPlugin().process(qpf, weights)
after = blended["qpf_combine"]
with np.printoptions(edgeitems=2, linewidth=120):
    print(after)""".splitlines()

TCH_OUT = """weights [0.0682 0.7573 0.1745] err [4.  1.2 2.5]
<xarray.DataArray 'data0' (member: 1, level: 1, time: 1, dtime: 1, lat: 30, lon: 30)> Size: 7kB
array([[[[[[4.11367881e-11, 1.68341334e-10, ..., 6.68627300e-09, 2.14618738e-09],
           [2.01907943e-10, 8.26254436e-10, ..., 3.28176244e-08, 1.05339359e-08],
           ...,
           [1.08677045e-06, 4.44731838e-06, ..., 1.76641013e-04, 5.66989587e-05],
           [4.18392614e-07, 1.71216024e-06, ..., 6.80045095e-05, 2.18283678e-05]]]]]], shape=(1, 1, 1, 1, 30, 30))
Coordinates:
  * member   (member) <U3 12B 'tch'
  * level    (level) float32 4B 0.0
  * time     (time) datetime64[ns] 8B 2024-06-12T08:00:00
  * dtime    (dtime) int32 4B 24
  * lat      (lat) float64 240B 28.0 28.1 28.2 28.3 28.4 ... 30.6 30.7 30.8 30.9
  * lon      (lon) float64 240B 106.0 106.1 106.2 106.3 ... 108.7 108.8 108.9""".splitlines()

TCH_PLOT = """import matplotlib.pyplot as plt
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

cmap, _ = get_cmap_and_clevs_by_element_name("rain_1h")
clevs = [0, 0.1, 1, 2, 4, 8, 16, 32]
map_extend = [106.0, 106.0 + 0.1 * 29, 28.0, 28.0 + 0.1 * 29]
axs = meb.creat_axs(
    2, map_extend, ncol=2, width=11.2,
    add_worldmap=False, add_index=True, wspace=1.15, grid=False,
)
meb.add_contourf(axs[0], parts[0], cmap=cmap, clevs=clevs, cut_colorbar=False, add_colorbar=True)
meb.add_contourf(axs[1], after, cmap=cmap, clevs=clevs, cut_colorbar=False, add_colorbar=True)
axs[0].set_title("单模式 ecmwf（mm）", fontsize=10)
axs[1].set_title("TCH 加权结果（mm）", fontsize=10)""".splitlines()


def set_plain(paragraph, text):
    p = paragraph._p
    runs = p.findall(qn("w:r"))
    first = runs[0]
    for extra in runs[1:]:
        p.remove(extra)
    texts = first.findall(qn("w:t"))
    texts[0].text = text
    for extra in texts[1:]:
        first.remove(extra)


def set_lines(paragraph, lines):
    p = paragraph._p
    runs = p.findall(qn("w:r"))
    first = runs[0]
    for extra in runs[1:]:
        p.remove(extra)
    template = deepcopy(first)
    p.remove(first)
    for i, line in enumerate(lines):
        run = deepcopy(template)
        for child in list(run):
            if child.tag != qn("w:rPr"):
                run.remove(child)
        if i:
            etree.SubElement(run, qn("w:br"))
        node = etree.SubElement(run, qn("w:t"))
        if line[:1].isspace() or line[-1:].isspace() or line == "":
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        node.text = line
        p.append(run)


def set_caption(paragraph, number, description):
    texts = paragraph._p.findall(".//" + qn("w:t"))
    texts[1].text = " %s  " % number
    texts[2].text = description
    for extra in texts[3:]:
        extra.text = ""


def set_image(paragraph, png_path):
    from docx.image.image import Image as DocxImage

    image = DocxImage.from_file(str(png_path))
    rId, _ = paragraph.part.get_or_add_image(image)
    blip = paragraph._p.find(".//" + qn("a:blip"))
    blip.set(qn("r:embed"), rId)
    with PILImage.open(png_path) as im:
        w, h = im.size
    cy = int(CX * h / w)
    for tag in ("wp:extent", "a:ext"):
        for el in paragraph._p.findall(".//" + qn(tag)):
            el.set("cx", str(CX))
            el.set("cy", str(cy))


def clone(paragraph):
    return deepcopy(paragraph._p)


doc = Document(str(DOC))
intro = doc.paragraphs[117]
intro.runs[0].text = intro.runs[0].text.replace("三份", "五份")
zh = deepcopy(intro.runs[0]._r)
en = deepcopy(intro.runs[2]._r)
last = intro.runs[-1]._r
pieces = [
    ("；光流外推列出", zh),
    (" Lagrangian", en),
    ("；多源融合列出", zh),
    (" TchWeightPlugin", en),
    (" 与 ", zh),
    ("TchBlendPlugin", en),
]
for text, sample in pieces:
    run = deepcopy(sample)
    nodes = run.findall(qn("w:t"))
    nodes[0].text = text
    if text[:1].isspace() or text[-1:].isspace():
        nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for extra in nodes[1:]:
        run.remove(extra)
    last.addprevious(run)

h2 = doc.paragraphs[247]
h3 = doc.paragraphs[321]
lead = doc.paragraphs[327]
code = doc.paragraphs[328]
image = doc.paragraphs[338]
caption = doc.paragraphs[339]

blocks = []

def add_h2(text):
    el = clone(h2)
    blocks.append(el)
    set_plain_el(el, text)

def add_h3(text):
    el = clone(h3)
    blocks.append(el)
    set_plain_el(el, text)

def add_lead(text):
    el = clone(lead)
    blocks.append(el)
    set_plain_el(el, text)

def add_code(lines):
    el = clone(code)
    blocks.append(el)
    # set_lines expects a paragraph; operate on the element directly
    fake = type("P", (), {"_p": el})()
    set_lines(fake, lines)

def add_fig(png, number, description):
    img = clone(image)
    cap = clone(caption)
    blocks.append(img)
    blocks.append(cap)
    fake = type("P", (), {"_p": img, "part": image.part})()
    set_image(fake, png)
    set_caption(type("P", (), {"_p": cap})(), number, description)

def set_plain_el(el, text):
    set_plain(type("P", (), {"_p": el})(), text)

add_h2("4.4 光流外推")
add_lead("度制半拉格朗日平流。合成 0.05° 雨团，仅演示。均匀东风每步 0.8°，雨团中心往东移。LsqrOpticalFlow 把速度装回网格时会因时间轴不完整失败，这里不附图。")
add_h3("4.4.1 Lagrangian")
add_lead("无构造参数。u、v 与降水同网格，单位是每步的经度、纬度位移。")
add_code(LAG_CALL)
add_code(LAG_OUT)
add_code(LAG_PLOT)
add_fig(LAG_PNG, "4-20", "外推前降水与 Lagrangian 外推后（1×2）")

add_h2("4.5 TCH 加权融合")
add_lead("多模式降水按误差做 BTCH 加权。合成 0.1° 雨团，仅演示。TchWeightPlugin.process 在当前 SciPy 的 COBYLA 约束上会报维度错误，示例改用 get_weight_mul。")
add_h3("4.5.1 TchBlendPlugin")
add_lead("三个成员分别是底场的 1.45、0.72、1.05 倍，误差 4.0、1.2、2.5。误差最小的 ncep 权重最大，加权结果应靠近较小的那一档。")
add_code(TCH_CALL)
add_code(TCH_OUT)
add_code(TCH_PLOT)
add_fig(TCH_PNG, "4-21", "单模式 ecmwf 与 TCH 加权结果（1×2）")

anchor = doc.paragraphs[-1]._p
cursor = anchor
for el in blocks:
    cursor.addnext(el)
    cursor = el

doc.save(str(DOC))
print("saved", len(blocks), "blocks")
