**基础信息**
- **所属包**: `orographic_temperature_downscaling`
- **插件页**: [orographic_temperature_downscaling](https://www.showdoc.com.cn/2598854776811541/11559060627552402)
- **调度脚本**: `cli/dsc_temp_lapse_rate.py`、`cli/anc_lapse_rate.py`

本页说明如何用 CLI 的 `process` 读文件估 Γ、做地形订正，以及批量调度。算法参数见插件页。使用示例读 `resource/showdoc_demo` 裁剪真场（与插件页同域：103–108°E、28–33°N）→ 路径传入 `process` → print / 画图。`main` 默认仍可读 `resource/cli_input` 样例，但不充当本文示例数据源。

**怎么跑**

```bash
python -m orographic_temperature_downscaling.cli
python -m orographic_temperature_downscaling.cli lapse-rate
python -m orographic_temperature_downscaling.cli apply-lapse
```

不带子命令时打印用法；带子命令时跑包内 `main`（默认 `resource/cli_input`）。业务数据请改路径，或按下面示例用 `showdoc_demo` 路径调用 `process`。

| 子命令 | 脚本 | 做什么 |
| --- | --- | --- |
| `lapse-rate` | `cli/dsc_temp_lapse_rate.py` | 估算层结递减率 Γ |
| `apply-lapse` | `cli/anc_lapse_rate.py` | 用 Γ 把气温从源地形订正到目标地形 |

---

# dsc_temp_lapse_rate.py

**调用插件**: `LapseRate`

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">process(<br>&nbsp;&nbsp;&nbsp;&nbsp;temperature_path,<br>&nbsp;&nbsp;&nbsp;&nbsp;orography_path=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;land_sea_mask_path=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output_path=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;max_height_diff=35.0,<br>&nbsp;&nbsp;&nbsp;&nbsp;nbhood_radius=7,<br>&nbsp;&nbsp;&nbsp;&nbsp;max_lapse_rate=-3*DALR,<br>&nbsp;&nbsp;&nbsp;&nbsp;min_lapse_rate=DALR,<br>&nbsp;&nbsp;&nbsp;&nbsp;dry_adiabatic=False,<br>)</div></div>

读气温（及可选地形、海陆掩码）nc，调用 `LapseRate` 估算层结递减率 Γ；`dry_adiabatic=True` 时直接返回 DALR 场。

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">temperature_path</span> | str。气温 nc 文件路径 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">orography_path</span> | str / None。地形高度 nc 路径；估算真实递减率时必填 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">land_sea_mask_path</span> | str / None。海陆掩码 nc 路径；估算真实递减率时必填 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">output_path</span> | str / None。输出 nc 路径；为 `None` 时不写文件 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">max_height_diff</span> | float。邻域最大高差（m） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">nbhood_radius</span> | int。邻域半径（格点） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">max_lapse_rate</span> | float。递减率上限；`DALR = -0.0098` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">min_lapse_rate</span> | float。递减率下限 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">dry_adiabatic</span> | bool。`True` 时直接返回 DALR 场 |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | 层结递减率 `DataArray`（`units='K m-1'`）；若给了 `output_path` 同时写出 nc |

**使用示例**

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
```

```
<xarray.DataArray 'air_temperature_lapse_rate' (member: 1, level: 1, time: 1,
                                                dtime: 1, lat: 51, lon: 51)> Size: 10kB
array([[[[[[-0.0060907 , -0.00372551, -0.00468451, ...,  0.0038845 ,
             0.00336316, -0.00046061],
           [-0.00697905, -0.00479418, -0.00502784, ...,  0.00324766,
             0.00135211, -0.00343593],
           [-0.00714306, -0.00515814, -0.00517604, ...,  0.00339385,
             0.00156866, -0.00224448],
           ...,
           [-0.00302311, -0.00363092, -0.00463387, ..., -0.00630611,
            -0.00649761, -0.00658015],
           [-0.00351569, -0.00423944, -0.00481306, ..., -0.00629828,
            -0.00612143, -0.00607667],
           [-0.00446332, -0.00506798, -0.00500175, ..., -0.00344553,
            -0.00364794, -0.00420304]]]]]],
      shape=(1, 1, 1, 1, 51, 51), dtype=float32)
Coordinates:
  * member   (member) <U5 20B 'data0'
  * level    (level) float32 4B 0.0
  * time     (time) datetime64[ns] 8B 2026-10-10
  * dtime    (dtime) int32 4B 0
  * lat      (lat) float64 408B 28.0 28.1 28.2 28.3 28.4 ... 32.7 32.8 32.9 33.0
  * lon      (lon) float64 408B 103.0 103.1 103.2 103.3 ... 107.8 107.9 108.0
Attributes:
    units:        K m-1
    model_var:    
    dtime_units:  hour
    level_type:   isobaric
    time_type:    UT
    time_bounds:  [0, 0]
```

粗网格气温（℃，EC 0.1°）：

![粗网格气温](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=aef29e8047ea805de6c7d92d48bad6f4&file=file.jpg)

粗网格源地形（m，EC 0.1°；与细地形同色标）：

![粗网格源地形](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=dbed0733d13861669a6be317a67ab2c8&file=file.jpg)

粗网格 Γ（K/km，EC 0.1°；固定色标）：

![粗网格Gamma](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=e1c4a84283f54bad7b5f1460190ed376&file=file.jpg)

---

# anc_lapse_rate.py

**调用插件**: `ApplyGriddedLapseRate`

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">process(<br>&nbsp;&nbsp;&nbsp;&nbsp;temperature_path,<br>&nbsp;&nbsp;&nbsp;&nbsp;lapse_rate_path,<br>&nbsp;&nbsp;&nbsp;&nbsp;source_orography_path,<br>&nbsp;&nbsp;&nbsp;&nbsp;target_orography_path,<br>&nbsp;&nbsp;&nbsp;&nbsp;output_path=None,<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">temperature_path</span> | str。气温 nc 文件路径 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">lapse_rate_path</span> | str。层结递减率 nc 文件路径 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">source_orography_path</span> | str。源地形高度 nc 文件路径 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">target_orography_path</span> | str。目标地形高度 nc 文件路径 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">output_path</span> | str / None。输出 nc 路径；为 `None` 时不写文件 |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | 订正后气温场（`DataArray`，`units='K'`）；若给了 `output_path` 同时写出 nc |

**使用示例**

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
```

```
<xarray.DataArray 'data0' (member: 1, level: 1, time: 1, dtime: 1, lat: 501,
                           lon: 501)> Size: 1MB
array([[[[[[285.03702, 285.97174, 286.27142, ..., 289.53   ,
            289.64   , 289.98926],
           [285.48993, 286.5551 , 286.54102, ..., 289.32434,
            289.623  , 289.75433],
           [286.20676, 286.9187 , 286.475  , ..., 289.00043,
            289.17468, 289.66092],
           ...,
           [272.99124, 273.02225, 273.026  , ..., 289.9307 ,
            289.6249 , 289.22803],
           [273.1374 , 273.1535 , 273.1627 , ..., 289.766  ,
            289.11465, 287.89688],
           [273.22763, 273.2661 , 273.284  , ..., 289.31073,
            287.8071 , 286.47717]]]]]],
      shape=(1, 1, 1, 1, 501, 501), dtype=float32)
Coordinates:
  * member   (member) <U5 20B 'data0'
  * level    (level) float32 4B 0.0
  * time     (time) datetime64[ns] 8B 2026-10-10
  * dtime    (dtime) int32 4B 0
  * lat      (lat) float64 4kB 28.0 28.01 28.02 28.03 ... 32.97 32.98 32.99 33.0
  * lon      (lon) float64 4kB 103.0 103.0 103.0 103.0 ... 108.0 108.0 108.0
Attributes:
    units:        K
    model_var:    
    dtime_units:  hour
    level_type:   isobaric
    time_type:    UT
    time_bounds:  [0, 0]
```

细网格目标地形（m，1 km DEM；与粗地形同色标）：

![细网格目标地形](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=848bbf98ab521154928e19d7df4ece34&file=file.jpg)

插到细网格后的气温（订正前，℃，1 km）：

![订正前](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=0d2bcd561020c2d0076ad67ecd8cd61a&file=file.jpg)

地形订正后气温（℃，1 km；与上图同色标）：

![订正后](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=f873df7f0d8ce1289179ed884db3e3ed&file=file.jpg)

订正增量（K，1 km）：

![订正增量](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=0ad28088e0b9272018be117ea317e730&file=file.jpg)

---

# 批量调度示例

在 `data/ec_t2m/` 下有待处理的 EC 气温数据；另备源地形、海陆掩码、目标 1 km 地形。下面用 `get_path_list_in_dir` 列出全部 nc，逐文件估 Γ → 插到 1 km → Apply。

```python
from pathlib import Path
import numpy as np
import meteva_base as meb
from orographic_temperature_downscaling.cli.dsc_temp_lapse_rate import process as est_gamma
from orographic_temperature_downscaling.cli.anc_lapse_rate import process as apply_gamma

OROG = "data/orog_src.nc"       # 源地形（与 EC 同网格）
MASK = "data/landmask.nc"       # 海陆掩码
DEST = "data/orog_1km.nc"       # 目标 1 km 地形

# 递归列出目录下全部文件，再只保留 nc
ec_list = meb.path_tools.get_path_list_in_dir("data/ec_t2m")
ec_list = [p for p in ec_list if p.endswith(".nc")]

# 源地形插到目标网格，全程复用
dest = meb.read_griddata_from_nc(DEST)
dest.attrs["units"] = "m"
grid1km = meb.get_grid_of_data(dest)
src1km = meb.interp_gg_linear(
    meb.read_griddata_from_nc(OROG), grid1km, outer_value=np.nan
)
src1km.attrs["units"] = "m"

for ec in ec_list:
    tag = Path(ec).stem                    # 如 2026101000.000
    lapse = f"output/lapse/{tag}.nc"

    # 1) 粗网格估 Γ
    est_gamma(ec, orography_path=OROG, land_sea_mask_path=MASK, output_path=lapse)

    # 2) 读气温 / Γ（DataArray 带 units；Apply 内会转到 K / K m-1）
    t = meb.read_griddata_from_nc(ec)
    g = meb.read_griddata_from_nc(lapse)

    # 3) 插到 1 km，时间维与气温对齐后 Apply
    t1 = meb.interp_gg_linear(t, grid1km, outer_value=np.nan)
    g1 = meb.interp_gg_linear(g, grid1km, outer_value=np.nan)
    # 插值结果继承坐标；补回 units 供 Apply 识别
    t1.attrs["units"] = t.attrs.get("units", "K")
    g1.attrs["units"] = g.attrs.get("units", "K m-1")
    kw = dict(
        time=t1.time.values, dtime=t1.dtime.values,
        member=t1.member.values, level=t1.level.values,
    )
    meb.write_griddata_to_nc(t1, "output/_tmp/t.nc", creat_dir=True)
    meb.write_griddata_to_nc(g1, "output/_tmp/g.nc", creat_dir=True)
    meb.write_griddata_to_nc(src1km.assign_coords(**kw), "output/_tmp/s.nc", creat_dir=True)
    meb.write_griddata_to_nc(dest.assign_coords(**kw), "output/_tmp/d.nc", creat_dir=True)

    apply_gamma(
        "output/_tmp/t.nc", "output/_tmp/g.nc",
        "output/_tmp/s.nc", "output/_tmp/d.nc",
        output_path=f"output/corr/{tag}.nc",
    )
```

EC 时间为**世界时**。实况若按**北京时**命名，检验时用 `有效世界时 + 8h`（本例 `00Z+.000` 对应实况 `…0800`）。

## 数据图展示

业务个例（EC / HRCLDAS）示意见历史附图，可与上文自建示例对照算法效果：

1 输入 EC（℃）

![输入 EC（℃）](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=84a6c6bf2a5a9f76a7205c262a2543c2&file=file.png)

2 层结递减率 Γ（K/m）

![层结递减率 Γ（K/m）](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=08f405eba8514cecd1cae000cad7da73&file=file.png)

3 订正结果（℃）

![订正结果（℃）](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=cd4d2988db52d6c4e3ef992d0e40f2d3&file=file.png)

4 实况 HRCLDAS（℃）

![实况 HRCLDAS（℃）](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=24c52ace1000aadb2ca368a47723e212&file=file.png)

## 检验结果

订正场（K）相对同时效 HRCLDAS，窗口 2026-10-10～24（15 天）：

| 项目 | 值 |
| --- | --- |
| mean_bias | **0.053 K** |
| mean_rmse | **1.786 K** |

| 起报.时效 | bias (K) | rmse (K) |
| --- | ---: | ---: |
| 2026101000.000 | -0.065 | 1.910 |
| 2026101100.000 | 0.039 | 1.918 |
| 2026101200.000 | -0.035 | 1.866 |
| 2026101300.000 | -0.013 | 1.756 |
| 2026101400.000 | 0.037 | 1.845 |
| 2026101500.000 | 0.022 | 1.787 |
| 2026101600.000 | 0.259 | 1.654 |
| 2026101700.000 | 0.234 | 1.715 |
| 2026101800.000 | -0.013 | 1.727 |
| 2026101900.000 | 0.064 | 1.745 |
| 2026102000.000 | 0.006 | 1.787 |
| 2026102100.000 | -0.030 | 1.793 |
| 2026102200.000 | 0.055 | 1.796 |
| 2026102300.000 | 0.116 | 1.742 |
| 2026102400.000 | 0.122 | 1.750 |
