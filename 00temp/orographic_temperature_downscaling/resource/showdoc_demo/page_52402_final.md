**基础信息**
- **所属包**: `orographic_temperature_downscaling`
- **预报类型**: 时空映射(降尺度)
- **算法类别**: `00space_downscale`
- **正式目录规划**: `NIMM/00space_downscale/orographic_temperature_downscaling/`
- **对外入口**: `LapseRate`、`ApplyGriddedLapseRate`
- **CLI 页**: [orographic_temperature_downscaling](https://www.showdoc.com.cn/2598854776811541/11559060627556703)
- **应用场景**: [地形精细化格点](https://www.showdoc.com.cn/2598854776811541/11559060627551913)

按层结递减率 $$\Gamma$$ 与源/目标地形高差，把气温从源地形订正到目标地形。常用两步：`LapseRate` 估 $$\Gamma$$ → 重网格到目标分辨率 → `ApplyGriddedLapseRate` 订正。两个 Process **不能**在粗/细网格未对齐时直接串联（见下方算法流程与 `ApplyGriddedLapseRate`）。

入参为带 `units` 的 `DataArray` 时，内部自动转到 K / K m⁻¹ / m；纯 `ndarray` 按已是目标单位处理。读文件、批量调度与业务检验见 [CLI 页](https://www.showdoc.com.cn/2598854776811541/11559060627556703)。

**算法功能与流程**

```mermaid
flowchart LR
    A[粗网格：气温 / 源地形 / 掩码] --> B[LapseRate<br/>估计 Γ]
    B --> R[重网格到目标分辨率]
    R --> C[ApplyGriddedLapseRate]
    D[目标细地形] --> C
    C --> E[订正气温]
```

1. **源网格**（如 EC）：气温 + 源地形 + 海陆掩码 → `LapseRate` 得 Γ（K/m）。
2. **订正前**：气温、Γ、源地形重网格到目标分辨率；目标地形用真实细地形（如 1 km DEM）。
3. **同一细网格**上：`ApplyGriddedLapseRate(气温, Γ, 源地形映到细网格, 目标细地形)` → 订正气温。
4. `|Δz| ≤ 50 m` 用局地 Γ；超出部分改用 ELR = −0.0065 K/m。

也可先插细网格再估 Γ，但邻域回归用的是插值后的场，一般仍推荐「先估 Γ 再插」。

# LapseRate

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">LapseRate(<br>&nbsp;&nbsp;&nbsp;&nbsp;max_height_diff=35.0,<br>&nbsp;&nbsp;&nbsp;&nbsp;nbhood_radius=7,<br>&nbsp;&nbsp;&nbsp;&nbsp;max_lapse_rate=-3*DALR,<br>&nbsp;&nbsp;&nbsp;&nbsp;min_lapse_rate=DALR,<br>).process(temperature, orography, land_sea_mask)</div></div>

以格点为中心取邻域（边长 `2·nbhood_radius+1`），丢掉相对中心高差超过 `max_height_diff` 的邻居，拟合 `Γ = cov(T, z) / var(z)`，再裁到 `[min_lapse_rate, max_lapse_rate]`。默认 DALR = −0.0098 K/m，Γ_min = DALR，Γ_max = −3·DALR。海洋点或样本不足回退 DALR。最后两维为空间维。

**构造参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">max_height_diff</span> | float。邻域样本相对中心允许的最大高差（m） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">nbhood_radius</span> | int。邻域半径，窗口边长为 `2 * nbhood_radius + 1` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">max_lapse_rate</span> | float。层结递减率上限（K/m）；`DALR = -0.0098` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">min_lapse_rate</span> | float。层结递减率下限（K/m） |

**process 参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">temperature</span> | DataArray / ndarray。气温场；`DataArray` 须带 `units`（如 `K`、`℃`），内部转 K；`ndarray` 按已是 K |
| <span style="color:#1677ff;font-weight:600;font-size:16px">orography</span> | DataArray / ndarray。地形高度；`DataArray` 须带 `units`（如 `m`），内部转 m；`ndarray` 按已是 m |
| <span style="color:#1677ff;font-weight:600;font-size:16px">land_sea_mask</span> | DataArray / ndarray。海陆掩码；陆为 True（或 1）、海为 False（或 0） |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | 层结递减率场（`units='K m-1'`，`float32`）；类型随输入为六维 `DataArray` 或 `ndarray` |

**使用示例**

读裁剪样例（`resource/showdoc_demo`：EC 气温 / 源地形 / 掩码，103–108°E、28–33°N，约 0.1°、51×51），调用 `LapseRate` 估计 Γ；后续降尺度与细目标地形见下一节。

```python
from pathlib import Path
import numpy as np
import meteva_base as meb
from meteva_base.tool.plot_tools import pcolormesh_2d_grid
from interp_gg_linear.src.interp_gg_linear import InterpGGLinearPlugin
from orographic_temperature_downscaling.src.lapse_rate import LapseRate, ApplyGriddedLapseRate

DEMO = Path("orographic_temperature_downscaling/resource/showdoc_demo")
temperature = meb.read_griddata_from_nc(str(DEMO / "t_coarse.nc"))
orography = meb.read_griddata_from_nc(str(DEMO / "z_coarse.nc"))
land_sea_mask = meb.read_griddata_from_nc(str(DEMO / "landmask.nc")).astype(bool)
temperature.attrs["units"] = "℃"
orography.attrs["units"] = "m"

print(temperature)
t_clevs = [0.1, 1.97, 3.85, 5.72, 7.59, 9.46, 11.34, 13.21, 15.08, 16.95, 18.83, 20.7]
pcolormesh_2d_grid(
    temperature, save_path="t_coarse.png", title="粗网格气温（℃，EC）",
    clevs=t_clevs, cmap="RdYlBu_r", show=False,
)
pcolormesh_2d_grid(
    orography, save_path="z_coarse.png", title="粗网格源地形（m，EC）",
    cmap="terrain", show=False,
)
```

```
<xarray.DataArray 'air_temperature' (member: 1, level: 1, time: 1, dtime: 1,
                                     lat: 51, lon: 51)> Size: 10kB
array([[[[[[11.9, 11.1,  9.9, ..., 15.4, 15.5, 16.6],
           [13.2, 12.9, 11.6, ..., 15.9, 15.6, 16.4],
           [12.7, 11.5,  9.2, ..., 15.6, 15.1, 15.7],
           ...,
           [-1.1, -0.6,  0.1, ..., 14.8, 14.3, 14.4],
           [-0.9, -0.6, -0.5, ..., 16.3, 15.8, 15.9],
           [ 0. , -0.2, -0.7, ..., 16.4, 16.4, 16.1]]]]]],
      shape=(1, 1, 1, 1, 51, 51), dtype=float32)
Coordinates:
  * member   (member) <U5 20B 'data0'
  * level    (level) float32 4B 0.0
  * time     (time) datetime64[ns] 8B 2026-10-10
  * dtime    (dtime) int32 4B 0
  * lat      (lat) float64 408B 28.0 28.1 28.2 28.3 28.4 ... 32.7 32.8 32.9 33.0
  * lon      (lon) float64 408B 103.0 103.1 103.2 103.3 ... 107.8 107.9 108.0
Attributes:
    units:        ℃
    model_var:    
    dtime_units:  hour
    level_type:   isobaric
    time_type:    UT
    time_bounds:  [0, 0]
```

粗网格气温（℃）：

![粗网格气温](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=eaed2c6a53a793e02baeb9114391e3f5&file=file.jpg)

粗网格源地形（m）：

![粗网格源地形](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=3ad0bdabb638da81ee937384c280991c&file=file.jpg)

```python
gamma = LapseRate(max_height_diff=1200.0, nbhood_radius=2).process(
    temperature, orography, land_sea_mask
)
print(gamma)
# 算法场单位为 K/m；作图×1000 成 K/km，固定色标
g_clevs = [-10.0, -9.0, -8.0, -7.5, -7.0, -6.5, -6.0, -5.5, -5.0, -4.0, -3.0]
pcolormesh_2d_grid(
    gamma * 1000.0, save_path="gamma.png", title="粗网格 Γ（K/km）",
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

粗网格 Γ（K/km，固定色标）：

![粗网格Γ](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=21bde88cb168cf790135a64a0de8ed64&file=file.jpg)

# ApplyGriddedLapseRate

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">ApplyGriddedLapseRate().process(temperature, lapse_rate, source_orog, dest_orog)</div></div>

应用已有层结递减率。`Δz = z_dest − z_src`。`|Δz| ≤ z_max`（默认 50 m）时 `ΔT = Γ·Δz`；超出部分改用 ELR。`T' = T + ΔT`。内部在 Kelvin 与 K/m 下计算，输出单位为 **K**。四输入须同网格；Apply **不会**自动重网格。

**构造参数**

| 参数 | 说明 |
| --- | --- |
| 无 | 无额外构造参数 |

**process 参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">temperature</span> | DataArray / ndarray。待订正气温；`DataArray` 带 `units` 时内部转 K |
| <span style="color:#1677ff;font-weight:600;font-size:16px">lapse_rate</span> | DataArray / ndarray。预计算 Γ；`DataArray` 带 `units` 时内部转 K m⁻¹ |
| <span style="color:#1677ff;font-weight:600;font-size:16px">source_orog</span> | DataArray / ndarray。源地形；`DataArray` 带 `units` 时内部转 m |
| <span style="color:#1677ff;font-weight:600;font-size:16px">dest_orog</span> | DataArray / ndarray。目标地形；`DataArray` 带 `units` 时内部转 m |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | 订正后气温（`units='K'`，`float32`），形状与输入气温一致 |

**使用示例**

承接上一节粗网格 Γ。将气温 / Γ / 源地形插到 **1 km DEM** 网格（同域约 501×501），再 `Apply`：订正量由细网格上 Δz = 目标 DEM − 源地形插值场决定，增量应贴合地形起伏。

```python
dest_orog = meb.read_griddata_from_nc(str(DEMO / "z_dest_fine.nc"))
dest_orog.attrs["units"] = "m"
dlon = float(np.diff(dest_orog.lon.values[:2])[0])
dlat = float(np.diff(dest_orog.lat.values[:2])[0])
g_f = meb.grid(
    [float(dest_orog.lon.min()), float(dest_orog.lon.max()), dlon],
    [float(dest_orog.lat.min()), float(dest_orog.lat.max()), dlat],
)

# 粗场 → 细网格（Apply 本身不做重网格）
interp = InterpGGLinearPlugin(used_coords="xy", outer_value=0.0)
t_fine = interp.process(temperature, g_f)
g_fine = interp.process(gamma, g_f)
src_fine = interp.process(orography, g_f)
t_fine.attrs["units"] = "℃"
g_fine.attrs["units"] = "K m-1"
src_fine.attrs["units"] = "m"

t_corr = ApplyGriddedLapseRate().process(t_fine, g_fine, src_fine, dest_orog)
print(t_corr)

t_clevs_f = [0.43, 2.27, 4.11, 5.95, 7.79, 9.62, 11.46, 13.3, 15.14, 16.98, 18.82, 20.66]
pcolormesh_2d_grid(
    dest_orog, save_path="z_fine.png", title="细网格目标地形（m，1 km DEM）",
    cmap="terrain", show=False,
)
pcolormesh_2d_grid(
    t_fine, save_path="t_before.png", title="插到细网格后的气温（订正前，℃）",
    clevs=t_clevs_f, cmap="RdYlBu_r", show=False,
)
pcolormesh_2d_grid(
    t_corr - 273.15, save_path="t_after.png", title="地形订正后气温（℃）",
    clevs=t_clevs_f, cmap="RdYlBu_r", show=False,
)
# 订正增量 = 订正后(K) − 插值场(转 K)
pcolormesh_2d_grid(
    t_corr - (t_fine + 273.15), save_path="t_delta.png", title="订正增量（K）",
    cmap="bwr", show=False,
)
```

```
<xarray.DataArray 'data0' (member: 1, level: 1, time: 1, dtime: 1, lat: 501,
                           lon: 501)> Size: 1MB
array([[[[[[285.03683, 285.96445, 286.2523 , ..., 289.5258 ,
            289.6431 , 290.0123 ],
           [285.4989 , 286.55237, 286.52652, ..., 289.32565,
            289.605  , 289.74844],
           [286.22018, 286.92047, 286.46512, ..., 288.98782,
            289.192  , 289.6582 ],
           ...,
           [272.9927 , 273.0275 , 273.0336 , ..., 289.95523,
            289.60162, 289.22653],
           [273.14453, 273.1652 , 273.17902, ..., 289.78055,
            289.1026 , 287.87735],
           [273.23663, 273.25314, 273.26953, ..., 289.31073,
            287.7997 , 286.467  ]]]]]],
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

订正增量贴合 1 km 地形起伏（约 −12～+9 K），高原/山脊偏冷、盆地/谷地偏暖。

细网格目标地形（m）：

![细网格目标地形](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=2da32776d113e8e6bf319501ffe23d3c&file=file.jpg)

插到细网格后的气温（订正前，℃）：

![订正前细网格气温](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=5af459078d34d3ec1b42d64c8b3e3ca1&file=file.jpg)

地形订正后气温（℃）：

![订正后气温](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=db86a898d5a11380a7312bfc9f7119df&file=file.jpg)

订正增量（K）= 订正后 − 插值场：

![订正增量](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=b6803a14160f1dc8b79658a32d5fda94&file=file.jpg)

---

算法 CLI 使用说明请见 [orographic_temperature_downscaling](https://www.showdoc.com.cn/2598854776811541/11559060627556703)。
