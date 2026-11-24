# 坐标投影转换

## 算法功能

等经纬度网格与 Lambert 等距投影网格互转（iris Cube）。库内 `util_plugin` 另提供 meteva ↔ Cube、KDTree 数组投影等辅助，不作为 CLI 主入口。

## 算法原理

核心是：**在目标投影上构造规则网格，再把源场重采样到该网格**。投影变换只改格点的地理位置表述；场值由源网格插值得到，不改变物理量本身的定义。

### 1. 两类空间表示

- **等经纬度**：点用 \((\lambda,\varphi)\) 表示，格距为度。同一 \(\Delta\lambda\) 在不同纬度对应的地面距离不同，高纬格点更密。
- **Lambert 正形圆锥（等距网格）**：把椭球点投到平面直角坐标 \((x,y)\)（米）。在两条标准纬线（割线）附近长度变形小，适合中国区域模式与等距分析网格。本包用 `LambertConformal`：中央经/纬取目标经纬范围中心，割线默认 \(25^\circ\mathrm{N}\)、\(47^\circ\mathrm{N}\)。

互转方向：

- `lonlat-to-equal`：已知 lon/lat 场 → 在 Lambert 平面上按固定米制格距铺网并插值。
- `equal-to-lonlat`：已知 Lambert 场 → 在业务 lon/lat 范围上按固定角度格距铺网并插值。

### 2. 目标网格如何生成

**等距目标**（`make_equalarea_coords`）：

1. 由 `projection_extent=(lonmin,lonmax,latmin,latmax)` 与 `secant_latitudes` 建立 Lambert CRS。
2. 将范围四角（取西南、东北）从地理坐标变换到 Lambert，得到 \((x_\min,y_\min)\)、\((x_\max,y_\max)\)。
3. 在 \([x_\min,x_\max]\)、\([y_\min,y_\max]\) 上按 `grid_distance`（米）生成一维 \(x\)、\(y\) 轴，组成规则二维网格。

**等经纬度目标**（`make_lonlat_coords`）：

1. 在 `lonlat_extent` 内按 `grid_spacing`（度）生成 `longitude`、`latitude` 轴。
2. 坐标系统为地理 `GeogCS`。

目标 Cube 外壳复制源场非空间维与元数据，仅替换水平维坐标。

### 3. 重采样（投影变换 + 插值）

对每个目标格点 \(P_t\)：

1. **坐标变换**：用源、目标 CRS（cartopy / iris）把 \(P_t\) 变到源网格坐标系中的查询位置 \(P_s=(x_s,y_s)\) 或 \((\lambda_s,\varphi_s)\)。
2. **插值**：在源规则网格上取值。
   - `bilinear`：双线性（cartopy 侧为 `RegularGridInterpolator(..., method="linear")`；iris 侧为 `iris.analysis.Linear`）。
   - `nearest`：最近邻。
3. **域外**：`extrapolation_mode=nanmask` 时，落在源域外的点填 NaN，不外推。

因此「投影」负责几何对齐，「插值」负责场值；边界 NaN 反映源覆盖范围，而非投影公式本身的截断。

### 4. 两种实现的差异

| | cartopy 路径（默认） | iris 路径 |
|--|---------------------|-----------|
| 坐标 | `coord_system.as_cartopy_crs()` + `transform_points` | iris Cube `coord_system` + regridder |
| 插值 | `scipy.interpolate.RegularGridInterpolator` | `iris.analysis.Linear` / `Nearest` |
| 结果 | 同参数下数值应接近，细节因插值实现略有差别 |

二者原理相同：都是「目标格点 → 源 CRS → 规则网格插值」。

## 参数说明

取值优先级：**命令行显式参数** → `resource/conf.ini` → 代码预设。

### 运行参数（`conf.ini` `[cli]` / CLI）

| 参数 | 类型 | 含义 |
|------|------|------|
| `mode` | `str` | 互转方向：`lonlat-to-equal` / `equal-to-lonlat`；默认 `lonlat-to-equal` |
| `backend` | `str` | 重采样实现：`cartopy` / `iris`；默认 `cartopy` |
| `source_cube` | `path` | 输入 iris Cube 路径（`.nc` 等） |

### `mode=lonlat-to-equal`（`[lonlat_to_equal]`）

| 参数 | 类型 | 含义 |
|------|------|------|
| `projection_extent` | `list[float]` | 目标外包络 `lonmin,lonmax,latmin,latmax`（再投 Lambert 得米制范围）；默认 `83,138,12,53` |
| `secant_latitudes` | `list[float]` | Lambert 两条标准纬线（°N）；默认 `25,47` |
| `grid_distance` | `float` | 等距格距（米）；默认 `1000` |
| `regrid_mode` | `str` | `bilinear` / `nearest`；默认 `bilinear` |
| `extrapolation_mode` | `str` | 源域外填 NaN，不外推；默认 `nanmask` |

椭球：`GeogCS(6378137, 6356752.314140356)`；中央经/纬取 `projection_extent` 中心。

### `mode=equal-to-lonlat`（`[equal_to_lonlat]`）

| 参数 | 类型 | 含义 |
|------|------|------|
| `lonlat_extent` | `list[float]` | 目标等经纬度范围；默认 `83,138,12,53` |
| `grid_spacing` | `float` | 等经纬度格距（度）；默认 `0.1` |
| `regrid_mode` | `str` | `bilinear` / `nearest`；默认 `bilinear` |
| `extrapolation_mode` | `str` | 源域外填 NaN，不外推；默认 `nanmask` |

## 主要入口

- `src/cube_lonlat_to_equal_cartopy.py` / `cube_equal_to_lonlat_cartopy.py`：cartopy 实现（CLI 默认 `backend=cartopy`）
- `src/cube_lonlat_to_equal.py` / `cube_equal_to_lonlat.py`：iris regridder（`backend=iris`）
- `src/utils/cpt_utils.py`：公共工具（网格元数据、维坐标组装、目标网格构造、cartopy 重采样）
- `src/util_plugin.py`：meteva ↔ Cube、KDTree 数组投影等辅助
- `cli/coordinate_projection_transform_cli.py`：主入口（`backend=cartopy|iris`，默认 cartopy）
- `cli/coordinate_projection_transform_cartopy_cli.py`：兼容入口（等同 `backend=cartopy`）

## 源、目标投影与网格定义

CLI 只做两类网格互转（`backend` 仅换实现，不换投影类型）。可调数值见上文 **参数说明**。

| 网格 | 投影 / CRS | 维坐标 | 单位 |
|------|------------|--------|------|
| 等经纬度 | `GeogCS`（地理经纬度） | `longitude` / `latitude` | 度 |
| Lambert 等距 | `LambertConformal`（正形圆锥） | `projection_x_coordinate` / `projection_y_coordinate` | 米 |

源 Cube 的 x/y 轴须带 `coord_system`。`regrid_mode`：cartopy 侧为 `RegularGridInterpolator` 的 `linear`/`nearest`；iris 侧为 `Linear`/`Nearest` regridder。目标格点变换到源 CRS 后插值写回目标 Cube；`nanmask` 时域外为 NaN。

## 运行示例

### 区域模式场 → 业务网格

场景：区域模式为 Lambert 等距 Cube，落到业务等经纬度网格（约 83–138°E、12–53°N、0.1°）。用 `mode=equal-to-lonlat`。

```bash
# 本包目录
python -m cli mode=equal-to-lonlat \
  source_cube=resource/data/regional_lambert.nc \
  lonlat_extent=83,138,12,53 \
  grid_spacing=0.1 \
  regrid_mode=bilinear \
  extrapolation_mode=nanmask
```

```python
from cli.coordinate_projection_transform_cli import process

out = process(
    mode="equal-to-lonlat",
    backend="cartopy",
    source_cube="resource/data/regional_lambert.nc",
    lonlat_extent=[83.0, 138.0, 12.0, 53.0],
    grid_spacing=0.1,
    regrid_mode="bilinear",
    extrapolation_mode="nanmask",
)
```

等价配置可写在 `resource/conf.ini` 的 `[cli]` / `[equal_to_lonlat]`，未在命令行给出的项从中读取。

反向（等经纬度 → 区域等距）用 `mode=lonlat-to-equal`，并设置 `projection_extent`、`secant_latitudes`、`grid_distance`。

### 核对坐标与输出边界

1. **源**：`coord(axis="x/y")` 名称、单位、`coord_system` 与 mode 一致（等距为米制 projection；等经纬度为 lon/lat）。
2. **目标范围**：输出 lon/lat（或 projection xy）首末点落在 `lonlat_extent` / 等距外包络内；格距等于 `grid_spacing` 或 `grid_distance`。
3. **格点数**：等经纬度约 `(lonmax-lonmin)/spacing+1`；等距按米制 `arange` 结果复核。
4. **边界缺测**：`nanmask` 下源域外目标点应为 NaN；若边界无缺测，检查 extent 是否过大或源域是否覆盖。
5. **四角抽检**：目标四角反变换到源 CRS，确认落在源网格内外与预期一致。
6. **实现对照**（可选）：同参数下 `backend=cartopy` 与 `backend=iris` 差值应可接受；样例对比见下节。

### 其它 CLI 写法

在本包目录（默认 cartopy）：

```bash
python -m cli mode=lonlat-to-equal source_cube=path/to/lonlat.nc
```

```bash
python -m cli mode=equal-to-lonlat source_cube=path/to/equal.nc grid_spacing=0.1
```

改用 iris regridder：

```bash
python -m cli backend=iris mode=lonlat-to-equal source_cube=path/to/lonlat.nc
```

```python
from cli.coordinate_projection_transform_cli import process
process(mode="lonlat-to-equal", source_cube="path/to/lonlat.nc")  # cartopy
process(backend="iris", mode="lonlat-to-equal", source_cube="path/to/lonlat.nc")
```

或在 `00temp` 目录：`python -m coordinate_projection_transform ...`

未给出的参数读 `resource/conf.ini`，再没有用代码预设。

## iris / cartopy 对比（样例 m4）

```bash
python test/compare_iris_cartopy_m4.py
```

默认读包内 `resource/sample/2026052400.036.m4`（等经纬度 → 等距对比），图写到 `resource/compare_out/`。

## 目录说明

- `src/`：投影主算法（iris / cartopy 两套 Cube plugin）+ `util_plugin` + `utils/cpt_utils`
- `cli/`：主 CLI（`backend` 选实现）
- `resource/conf.ini`：运行参数；`resource/sample/`：对比用 m4 样例
- `test/` / `nbs/` / `docs/`
