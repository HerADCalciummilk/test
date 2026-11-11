# 风速降尺度模块分析文档

## 1. 模块概述

本包风速降尺度分两步：

1. **粗糙度计算**（`src/roughness.py`）：由高分辨率 DEM 与模式网格地形统计 `sigma`、`a_over_s`。
2. **风速订正**（`src/wind_downscaling.py`）：用辅料对风速做粗糙度订正（RC）与高度订正（HC）。

衔接：

```text
细网格 DEM + 模式网格地形
        → RoughnessCalculation → sigma, a_over_s（细网格）
        → RoughnessCorrection(a_over_s, sigma, pporo, modoro, ...)
        → (订正风速, hc_add)
```

`wind_downscaling.py` 主要类：

- `FrictionVelocity`：计算大气边界层中的摩擦速度
- `RoughnessCorrectionUtilities`：提供粗糙度订正和高度订正的核心功能
- `RoughnessCorrection`：高级接口；固定返回 `(订正风速, hc_add)`

## 2. RoughnessCalculation 与 AncRoughnessCli

### 2.1 功能描述

`RoughnessCalculation` 由**高分辨率 DEM**与**模式网格地形**统计订正辅料：

- `sigma`：模式格点中心窗口内高度总体标准差（米）
- `a_over_s`（轮廓粗糙度）：窗口内东西 / 南北截面上升段高度增量除以截面长度后的平均（无量纲）

输出与高分辨率 DEM **同网格**，供 `RoughnessCorrection` 使用。命令行见 `cli/roughness_cli.py`（`AncRoughnessCli`）。

**约束**：`model_orography` 必须仍是模式分辨率网格（只用其 `lat`/`lon` 定义格点），不能是已插到细网格的场。

对每个模式格点：

1. 在细网格上取以其为中心、边长 ≈ 模式格距 / 细网格格距的窗口（如 0.2° / 0.01° → 20）。
2. 窗口须完整落在细网格内且高度全部有效，否则该模式格点记为缺测。
3. 完整窗口上计算 `sigma` 与轮廓粗糙度。
4. 缺测模式格点先在模式网格上由周围有效点线性填补（凸包外最近邻），再插回细网格。

### 2.2 输入参数

| 参数名 | 类型 | 是否必填 | 说明 | 单位 |
| --- | --- | --- | --- | --- |
| `orography` | `xr.DataArray` | 是 | 高分辨率地形高度，须带一维递增 `lat`/`lon` | `m` |
| `model_orography` | `xr.DataArray` | 是 | 模式网格地形；只用经纬网格，不用高度值做统计 | `m` |

### 2.3 输出

| 返回值 | 类型 | 说明 | 单位 |
| --- | --- | --- | --- |
| `sigma` | `xr.DataArray` | 与细网格同形；`name='standard_deviation_of_height_in_grid_cell'` | `m` |
| `a_over_s` | `xr.DataArray` | 与细网格同形；`name='silhouette_roughness'` | 无量纲（`1`） |

`process` **固定**返回 `(sigma, a_over_s)`。

### 2.4 主要方法

| 方法 | 作用 |
| --- | --- |
| `window_size` | 由模式/细网格格距比得到中心窗口边长（格点数） |
| `cell_height_std` | 模式格点窗口高度总体标准差 → 填补 → 插到细网格 |
| `cell_silhouette` | 模式格点窗口轮廓粗糙度 → 填补 → 插到细网格 |
| `window_silhouette` | 单窗口：东西、南北上坡增量 / 截面长度后平均 |
| `fill_model_field` | 模式网格缺测线性填补（凸包外最近邻） |
| `to_fine_grid` | 模式场线性插到细网格（范围外取最近模式格点） |

### 2.5 算法要点

**窗口边长**

```text
nlat ≈ round(Δlat_model / Δlat_fine)
nlon ≈ round(Δlon_model / Δlon_fine)
```

**sigma**：完整窗口内高度的总体标准差。

**轮廓粗糙度（单窗口）**：

- 东西向：上坡高度增量之和 / 东西向截面长度（米，含 `cos(lat)`）
- 南北向：上坡高度增量之和 / 南北向截面长度（米）
- `a/s = mean(有效方向的比值)`

长度换算使用 `METRES_PER_DEGREE ≈ 111195`（1° 对应弧长近似）。

`pporo` 一般为细网格目标地形；`modoro` 为插到细网格的模式地形高度（与本步「模式网格地形」不同：后者只提供模式 lat/lon 网格）。

### 2.6 使用方法

```python
from pathlib import Path
import meteva_base as meb
from orographic_wind_downscaling.src.roughness import RoughnessCalculation

CROP = Path("orographic_wind_downscaling/resource/data/example_crop")
orography = meb.read_griddata_from_nc(str(CROP / "fine_orography.nc"))
model_orography = meb.read_griddata_from_nc(str(CROP / "model_orography_grid.nc"))

sigma, a_over_s = RoughnessCalculation().process(orography, model_orography)
# 或 RoughnessCalculation()(orography, model_orography)
print(sigma.name, a_over_s.name)
```

### 2.7 CLI：`AncRoughnessCli`

脚本：`cli/roughness_cli.py`

```bash
python cli/roughness_cli.py \
  --orography-path PATH \
  --model-orography-path MODEL.nc \
  [--sigma-output-path SIGMA.nc] \
  [--silhouette-output-path AOS.nc]
```

```python
from cli.roughness_cli import AncRoughnessCli

AncRoughnessCli.call(
    orography_path="PATH",
    model_orography_path="MODEL.nc",
    sigma_output_path="SIGMA.nc",
    silhouette_output_path="AOS.nc",
)
```

`AncRoughnessCli.call` 返回退出码 `0`；需要场对象时读输出 nc，或调用模块内 `process(...)`（返回 `(sigma, silhouette)`）。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `orography_path` | 是 | 高分辨率地形 nc（米） |
| `model_orography_path` | 是 | 模式网格地形 nc |
| `sigma_output_path` | 否 | 高度标准差输出路径；省略不写 |
| `silhouette_output_path` | 否 | 轮廓粗糙度输出路径；省略不写 |

## 3. 风速订正核心类分析

### 3.1 FrictionVelocity 类

#### FrictionVelocity 功能描述

计算大气边界层中的摩擦速度 u*，这是表征近地面大气湍流强度的特征速度尺度。

#### FrictionVelocity 输入参数

| 参数名 | 类型 | 描述 | 单位 |
| --- | --- | --- | --- |
| `u_href` | 二维浮点型数组（float32） | 参考高度 h_ref 处的风速 | 与输入风速单位一致（通常为 m/s） |
| `h_ref` | 二维浮点型数组（float32） | 参考高度 | 长度单位（通常为米） |
| `z_0` | 二维浮点型数组（float32） | 植被粗糙度长度，反映地表粗糙程度 | 长度单位（通常为米） |
| `mask` | 二维布尔型数组（bool） | True 表示对应格点需计算摩擦速度 u* | 无 |

#### FrictionVelocity 输出参数

| 返回值 | 类型 | 描述 | 单位 |
| --- | --- | --- | --- |
| `process()` | 二维浮点型数组（float32） | 摩擦速度场，未计算的格点值为 RMDI | 与输入风速单位一致（通常为 m/s） |

#### FrictionVelocity 算法原理

基于对数风速廓线方程，计算公式为：

```math
u* = K \times \frac{u_{href}}{\ln(\frac{h_{ref}}{z_0})}
```

其中：

- `u*` 为摩擦速度
- `K` 为冯·卡门常数（Von Karman's constant），通常取 0.4
- `u_{href}` 为参考高度处的风速
- `h_{ref}` 为参考高度
- `z_0` 为植被粗糙度长度

#### FrictionVelocity 使用方法

```python
from src.wind_downscaling import FrictionVelocity

# 初始化实例
fv = FrictionVelocity(u_href, h_ref, z_0, mask)

# 计算摩擦速度
ustar = fv()  # 或 fv.process()
```

#### 输入输出示例（FrictionVelocity）

```python
import numpy as np
from orographic_wind_downscaling.src.wind_downscaling import FrictionVelocity

# 构造二维输入场 (lat, lon)
u_href = (np.random.rand(101, 101) * 20.0).astype(np.float32)      # m s-1
h_ref = np.full((101, 101), 10.0, dtype=np.float32)                # m
z_0 = (np.random.rand(101, 101) * 0.5 + 0.01).astype(np.float32)   # m
mask = np.ones((101, 101), dtype=bool)                              # True 表示参与计算

fv = FrictionVelocity(u_href=u_href, h_ref=h_ref, z_0=z_0, mask=mask)
ustar = fv.process()

print(type(ustar))      # <class 'numpy.ndarray'>
print(ustar.shape)      # (101, 101)
print(ustar.dtype)      # float32
```

### 3.2 RoughnessCorrectionUtilities 类

#### RoughnessCorrectionUtilities 功能描述

提供粗糙度订正和高度订正的核心功能，基于辅助文件计算风速订正。

#### RoughnessCorrectionUtilities 输入参数

| 参数名 | 类型 | 描述 | 单位 |
| --- | --- | --- | --- |
| `a_over_s` | 二维浮点型数组（float32） | 地形轮廓粗糙度场（无量纲） | 无 |
| `sigma` | 二维浮点型数组（float32） | 网格单元内的高度标准差场 | 长度单位 |
| `z_0` | 二维浮点型数组（float32） | 植被粗糙度长度场 | 长度单位 |
| `pporo` | 二维浮点型数组（float32） | 后处理网格地形高度场 | 长度单位 |
| `modoro` | 二维浮点型数组（float32） | 插值至后处理网格的模式地形高度场 | 长度单位 |
| `ppres` | 浮点型（float） | 后处理网格的网格单元边长 | 长度单位 |
| `modres` | 浮点型（float） | 模式网格的网格单元边长 | 长度单位 |

#### 主要方法及输出

| 方法名 | 输入参数 | 输出参数 | 描述 |
| --- | --- | --- | --- |
| `sigma2hover2` | sigma: 二维浮点型数组 | 二维浮点型数组 | 计算半峰谷高度 |
| `calc_roughness_correction` | hgrid: 三维或一维浮点型数组 uold: 三维浮点型数组 mask: 二维布尔型数组 | 三维浮点型数组 | 执行粗糙度订正 |
| `do_rc_hc_all` | hgrid: 一维或三维浮点型数组 uorig: 三维浮点型数组 | `(订正风速, hc_add)` 二元组 | 同时执行粗糙度订正和高度订正；`hc_add` 为截断前高度订正附加项 |

#### RoughnessCorrectionUtilities 算法原理

1. **半峰谷高度计算**：

  ```math
   h_{over2} = \sqrt{2} \times \sigma
  ```

1. **波数计算**：

  ```math
   k = \frac{a_{over_s} \times \pi}{h_{over2}}
  ```

1. **参考高度计算**：

  ```math
   h_{ref} = \frac{tunable\_param}{wavenum}
  ```

1. **粗糙度订正**：将参考高度以下的风速廓线替换为随高度对数增长的廓线。
2. **高度订正**：考虑地形高度差对风速的影响，随高度呈指数衰减：

  ```math
   hc\_add = \exp(-height \times wavenumber) \times u(href) \times h\_at\_0 \times wavenumber
  ```

#### RoughnessCorrectionUtilities 使用方法

```python
from src.wind_downscaling import RoughnessCorrectionUtilities

# 初始化实例
rc_utils = RoughnessCorrectionUtilities(
    a_over_s=a_over_s,
    sigma=sigma,
    z_0=z_0,
    pporo=pporo,
    modoro=modoro,
    ppres=ppres,
    modres=modres
)

# 执行粗糙度和高度订正
final_wind, hc_add = rc_utils.do_rc_hc_all(height_grid, wind_speed)
```

### 3.3 RoughnessCorrection 类

#### RoughnessCorrection 功能描述

`RoughnessCorrection` 是风速降尺度流程的主插件，用于组织输入数据并调度
`RoughnessCorrectionUtilities` 执行粗糙度订正（RC）与高度订正（HC）。

相较于底层工具类，本插件重点负责：

- 输入结构统一（`np.ndarray` / `xr.DataArray`）。
- 高维批次维拆分与逐片处理。
- 输出结构重组（尤其是 DataArray 场景下的 meteva_base 维度对齐）。

#### RoughnessCorrection 输入参数

| 参数名 | 类型 | 是否必填 | 说明 | 单位 |
| --- | --- | --- | --- | --- |
| `a_over_s` | `np.ndarray` 或 `xr.DataArray` | 是 | 地形轮廓粗糙度单场；若为 `xr.DataArray`，会先做网格校验并压缩为二维 `(lat, lon)` | 无量纲（`1`） |
| `sigma` | `np.ndarray` 或 `xr.DataArray` | 是 | 网格内地形高度标准差单场；`xr.DataArray` 输入会先校验并压缩 | `m` |
| `pporo` | `np.ndarray` 或 `xr.DataArray` | 是 | 目标网格地形高度单场；若为 `xr.DataArray` 且未传 `ppres`，自动由坐标推断 `ppres` | `m` |
| `modoro` | `np.ndarray` 或 `xr.DataArray` | 是 | 标准网格（模式）地形高度单场；`xr.DataArray` 输入会先校验并压缩 | `m` |
| `modres` | `float` | 是 | 模式原始分辨率 | `m` |
| `ppres` | `float` | 条件必填 | 后处理网格分辨率；当 `pporo` 为 `np.ndarray` 时必须显式传入 | `m` |
| `z0` | `np.ndarray` 或 `xr.DataArray` | 否 | 植被粗糙度长度单场；不传则跳过植被粗糙度订正分支 | `m` |

#### 方法及输出

| 方法名 | 输入参数 | 输出结果 | 描述 |
| --- | --- | --- | --- |
| `process` | wind_speed: np.ndarray 或 xr.DataArray；height_grid: np.ndarray，可选 | `(订正风速, hc_add)` | 对风速做 RC + HC；`hc_add` 为高度订正附加项（截断前） |
| `infer_grid_resolution_from_coords` | `data: xr.DataArray` | `float` | 从坐标估算网格分辨率（米）：投影米制直接取间距；真经纬将度间距换算为米 |

合成式：`u_out = max(u_RC + hc_add, 0)`。粗糙度订正替换近地廓线；高度订正为加性项；最后非负截断。

#### 输出表（当前版本）

| 输入类型 | 输出 | 维度约定 |
| --- | --- | --- |
| `wind_speed` 为 `np.ndarray` | `(ndarray, ndarray)` | 二者与输入风速同结构（批次维 + `level, lat, lon`） |
| `wind_speed` 为 `xr.DataArray` | `(DataArray, DataArray)` | 二者均为 meteva_base 六维；`hc_add.name='height_correction'` |

#### RoughnessCorrection 算法原理

1. 识别输入类型并规范风速数据结构。
    - 数组输入默认最后三维为 `(level, lat, lon)`；
    - DataArray 输入会先规范为 meteva_base 约定维度顺序。
2. 校验辅助场 `a_over_s / sigma / pporo / modoro / z0` 与风速场空间形状一致。
3. 若 `pporo` 为 DataArray 且未显式提供 `ppres`，自动按坐标估算后处理网格分辨率（米）；真经纬输入会将度间距换算为米（东西向按代表纬度 `cos(lat)` 缩放）。
4. 组织高度网格（支持一维公共高度层或三维空间变化高度层）。
5. 将输入整理为“批次维 + (level, lat, lon)”并逐批次调用核心订正。
6. 还原为输入对应结构，并固定返回 `(订正风速, hc_add)`；若输入为 DataArray，则二者均按标准维度重组。

#### RoughnessCorrection 使用方法

```python
from orographic_wind_downscaling.src.wind_downscaling import RoughnessCorrection

# 初始化实例
plugin = RoughnessCorrection(
    a_over_s=a_over_s,
    sigma=sigma,
    pporo=pporo,
    modoro=modoro,
    modres=modres,
    z0=z0
)

# 执行风速订正：固定返回订正风速与高度订正量
corrected_wind, hc_add = plugin.process(wind_speed, height_levels)
```

## 4. 核心算法原理

### 4.1 摩擦速度计算

摩擦速度是表征近地面大气湍流强度的特征速度尺度，反映了地表对大气运动的摩擦拖拽作用。计算基于对数风速廓线方程，适用于中性大气条件下的边界层风速分布。

### 4.2 粗糙度订正

粗糙度订正是将参考高度以下的风速廓线替换为随高度对数增长的廓线，边界条件为：

- 参考高度 h_ref 处的风速为原始参考风速 uhref
- 植被粗糙度长度 z_0 处的风速为 0

### 4.3 高度订正

高度订正是考虑地形高度差对风速的影响，扰动项随高度呈指数衰减。垂直偏移量 h_at0 越大（未解析的地形越高），扰动程度越显著。扰动越平缓（扰动的水平尺度越大），高度订正量越小。

### 4.4 波数计算

波数是表征地形特征尺度的重要参数，由半峰谷高度和地形轮廓粗糙度计算得出，用于确定参考高度和高度订正的衰减率。

## 5. 数据流程

1. **输入数据准备**：收集地形轮廓粗糙度、高度标准差、植被粗糙度长度等辅助数据（`sigma` / `a_over_s` 可由第 2 节 `RoughnessCalculation` 从 DEM 与模式网格地形生成）
2. **参数计算**：计算半峰谷高度、波数、参考高度等中间参数
3. **掩码生成**：生成高度订正和粗糙度订正的掩码
4. **风速订正**：执行粗糙度订正和高度订正，得到 `u_RC` 与 `hc_add`
5. **结果处理**：`u_out = max(u_RC + hc_add, 0)`，并与 `hc_add` 一并返回

## 6. 代码优化建议

1. **错误处理增强**：添加更多的输入参数验证，提高代码的健壮性
2. **性能优化**：对于大规模数据，可以考虑使用 NumPy 的向量化操作替代循环
3. **文档完善**：添加更多的内联注释，特别是对于复杂的数学公式
4. **单元测试**：增加更多的单元测试，覆盖边界情况
5. **模块化**：将一些重复的代码提取为单独的函数，提高代码的可维护性

## 7. 参考文献

1. Robinson, D. (2008). *UM 辅助文件制作*（统一模式文档 73 号）
2. Howard, T. & Clark, P. (2007). 地形对风速影响的研究
3. Vosper, S. B. (2009). 地形粗糙度对边界层的影响
4. Clark, P. (2009). *UK Climatology - Wind Screening Tool*（英国气候学——风筛选工具）
5. Friedrich, M. M. (2016). *Wind Downscaling Program* (Internal Met Office Report)
6. 英国皇冠地产官网发布的《Virtual Met Mast Version 1 Methodology and Verification》（虚拟气象塔1.0版方法学与验证）报告

## 8. 输入输出示例

### 示例1：`numpy.ndarray` 输入与输出

```python
import numpy as np
from orographic_wind_downscaling.src.wind_downscaling import RoughnessCorrection

# 假设风速是 (level, lat, lon)
wind_speed = np.random.rand(9, 101, 101).astype(np.float32) * 20.0

# 辅助场必须是二维 (lat, lon)
a_over_s = np.random.rand(101, 101).astype(np.float32)
sigma = (np.random.rand(101, 101) * 100.0).astype(np.float32)
pporo = (np.random.rand(101, 101) * 500.0).astype(np.float32)
modoro = (np.random.rand(101, 101) * 500.0).astype(np.float32)
z0 = (np.random.rand(101, 101) * 0.5 + 0.01).astype(np.float32)

# 每层高度（与 level 数一致）
height_levels = np.array([10, 20, 30, 50, 70, 100, 150, 200, 300], dtype=np.float32)

plugin = RoughnessCorrection(
    a_over_s=a_over_s,
    sigma=sigma,
    pporo=pporo,
    modoro=modoro,
    modres=1500.0,
    ppres=2000.0,
    z0=z0,
)

corrected_wind, hc_add = plugin.process(wind_speed=wind_speed, height_grid=height_levels)
print(type(corrected_wind), type(hc_add))  # ndarray, ndarray
print(corrected_wind.shape, hc_add.shape)  # (9, 101, 101), (9, 101, 101)
```

### 示例2：`xarray.DataArray` 输入与输出（meteva_base 六维）

```python
import numpy as np
import xarray as xr
from orographic_wind_downscaling.src.wind_downscaling import RoughnessCorrection

# 构造标准六维风速场: (member, level, time, dtime, lat, lon)
wind_speed_da = xr.DataArray(
    np.random.rand(1, 9, 1, 1, 101, 101).astype(np.float32) * 20.0,
    dims=("member", "level", "time", "dtime", "lat", "lon"),
    coords={
        "member": ["data0"],
        "level": np.array([10, 20, 30, 50, 70, 100, 150, 200, 300], dtype=np.float32),
        "time": [np.datetime64("2023-01-01T00:00:00")],
        "dtime": [0],
        "lat": np.linspace(20.0, 60.0, 101, dtype=np.float32),
        "lon": np.linspace(70.0, 140.0, 101, dtype=np.float32),
    },
    name="wind_speed",
    attrs={"units": "m s-1"},
)

# 辅助场也可直接传 DataArray（可为六维单场，算法会校验并压缩）
aux_6d = xr.DataArray(
    np.random.rand(1, 1, 1, 1, 101, 101).astype(np.float32),
    dims=("member", "level", "time", "dtime", "lat", "lon"),
    coords={
        "member": ["data0"],
        "level": [0.0],
        "time": [np.datetime64("2023-01-01T00:00:00")],
        "dtime": [0],
        "lat": wind_speed_da.coords["lat"],
        "lon": wind_speed_da.coords["lon"],
    },
)

plugin = RoughnessCorrection(
    a_over_s=aux_6d,
    sigma=aux_6d * 100.0,
    pporo=aux_6d * 500.0,
    modoro=aux_6d * 500.0,
    modres=1500.0,
    z0=aux_6d * 0.5 + 0.01,
)

corrected_da, hc_da = plugin.process(wind_speed=wind_speed_da)
print(corrected_da.dims, hc_da.name)  # 六维；height_correction
print(corrected_da.shape, hc_da.shape)  # (1, 9, 1, 1, 101, 101)
```

### 输出约定

- `process` **固定**返回 `(订正风速, hc_add)`。
- 当 `wind_speed` 为 `numpy.ndarray` 时，二者均为同结构 `ndarray`。
- 当 `wind_speed` 为 `xarray.DataArray` 时，二者均为 meteva_base 六维 `DataArray`；`hc_add.name='height_correction'`。
- 辅助场 `a_over_s / sigma / pporo / modoro / z0` 均支持 `numpy.ndarray` 与 `xarray.DataArray`；其中 `xarray` 输入会先进行网格格式校验。
- CLI `dsc_wind_downscaling` 写盘时仅使用订正风速，忽略 `hc_add`。

## 9. CLI 应用

粗糙度辅料 CLI 见第 2.7 节 `AncRoughnessCli`。风速订正示例脚本：`orographic_wind_downscaling/cli/dsc_wind_downscaling.py`。

### 9.1 运行方式

PowerShell 示例：

```powershell
python -m orographic_wind_downscaling.cli.dsc_wind_downscaling
```

在代码中调用：

```python
from orographic_wind_downscaling.cli.dsc_wind_downscaling import process

result = process(
    wind_speed_path="orographic_wind_downscaling/test_data/wind_calculations_data/cli_input/input.nc",
    sigma_path="orographic_wind_downscaling/test_data/wind_calculations_data/cli_input/sigma.nc",
    target_orography_path="orographic_wind_downscaling/test_data/wind_calculations_data/cli_input/highres_orog.nc",
    standard_orography_path="orographic_wind_downscaling/test_data/wind_calculations_data/cli_input/standard_orog.nc",
    silhouette_roughness_path="orographic_wind_downscaling/test_data/wind_calculations_data/cli_input/a_over_s.nc",
    model_resolution=1500.0,
    vegetative_roughness_path="orographic_wind_downscaling/test_data/wind_calculations_data/cli_input/veg.nc",
    output_path="orographic_wind_downscaling/test_data/wind_calculations_data/cli_output/cli_result.nc",
    output_height_level=None,
    output_height_level_units="m",
)
```

内置测试数据目录：`orographic_wind_downscaling/test_data/wind_calculations_data/`。

| 路径 | 说明 |
| --- | --- |
| `cli_input/` | 方案一输入（投影维重命名；由 `cli/preprocess_test_data.py` 写出） |
| `cli_input/latlon/` | 方案二输入与对照场（经纬重网格；含 `kgo.nc`、`original_algorithm_result.nc`） |
| `cli_output/` | CLI 示例输出目录 |
| `kgo.nc` | 官方 KGO（投影坐标，位于数据根目录） |
| `original_algorithm_result.nc` | 原 IMPROVER 算法结果（投影坐标，位于数据根目录） |
| `input.nc`、`a_over_s.nc` 等 | 原始官方投影样例（预处理源文件） |

官方样例预处理（一次生成方案一 `cli_input/` 与方案二 `cli_input/latlon/`）：

```powershell
python orographic_wind_downscaling/cli/preprocess_test_data.py
```

官方回归测试：

```powershell
pytest orographic_wind_downscaling/test/test_official_wind_downscaling.py
```

测试从 `cli_input/` 读入六维输入，与根目录 `kgo.nc`、`original_algorithm_result.nc` 对照。若 `cli_input/` 缺失，先运行上述预处理脚本生成。

验证 Notebook：`nbs/wind_calculations.ipynb`（仅读取预处理结果并做方法调用与对照；预处理请先运行上述脚本）

- **方案一**：投影维重命名路径（低误差对照）
- **方案二**：真经纬重网格路径（`ppres` 度→米推断；对照场亦由预处理写出）

原 Iris 插件不能在纯经纬网格上直接重跑。

### 9.2 `process()` 参数说明

| 参数 | 是否必填 | 说明 | 单位/格式 |
| --- | --- | --- | --- |
| `wind_speed_path` | 是 | 待订正风速场 nc 路径 | NC 文件 |
| `sigma_path` | 是 | 网格内地形高度标准差 nc 路径 | `m` |
| `target_orography_path` | 是 | 目标网格地形高度 nc 路径 | `m` |
| `standard_orography_path` | 是 | 标准网格地形高度 nc 路径 | `m` |
| `silhouette_roughness_path` | 是 | 地形轮廓粗糙度 nc 路径 | 无量纲（`1`） |
| `model_resolution` | 是 | 模式原始分辨率 | `m` |
| `vegetative_roughness_path` | 否 | 植被粗糙度长度 nc 路径 | `m` |
| `output_path` | 否 | 输出 nc 路径 | NC 文件 |
| `output_height_level` | 否 | 提取指定高度层 | 数值 |
| `output_height_level_units` | 否 | 高度层单位，默认 `m` | 如 `m`、`km` |

### 使用注意

1. 本 CLI 当前仅支持 meteva_base 网格数据格式输入：`member, level, time, dtime, lat, lon`。
2. 若输入不是 meteva_base 网格数据格式，请先运行 `python orographic_wind_downscaling/cli/preprocess_test_data.py`（写出方案一 `cli_input/` 与方案二 `cli_input/latlon/`）。
3. `--output-height-level` 与 `--output-height-level-units` 建议配套使用；只给单位不指定高度时，单位参数不会生效。

## 10. 总结

先用 `RoughnessCalculation` / `AncRoughnessCli` 从细网格 DEM 与模式网格地形得到 `sigma`、`a_over_s`；再用 `RoughnessCorrection` 做风速订正：RC 替换近地廓线，HC 叠加 `hc_add`，再非负截断，固定返回 `(订正风速, hc_add)`。
