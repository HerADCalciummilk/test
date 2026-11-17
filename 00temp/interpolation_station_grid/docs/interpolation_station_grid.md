# interpolation_station_grid 算法说明

将站点观测融合到规则格点场。面向 `meteva_base` 站点表与六维格点场。

四个插件接口统一为：

```text
process(sta, grid, background=None)
```

- `sta`：站点数据  
- `grid`：目标网格（`meb.grid` / `glon`·`glat` 等）  
- `background`：可选格点场；有则先对齐到目标网格再参与融合（IDW / Gaussian / Kriging 为偏差订正，Cressman 为初估场）

背景对齐依赖同级包 `interpolation_grid_grid.InterpGgLinear`（`outer_value` 控制越界填充）。结果 `attrs` 继承自输入站点。

---

## 1. 插件一览

| 插件 | 功能简介 |
| --- | --- |
| `InterpSgIdw` | 反距离权重（IDW）；可选高斯衰减与背景偏差订正 |
| `InterpSgGaussian` | 最近邻 × 高斯半径扩散；可选背景偏差订正 |
| `InterpSgKriging` | 局部普通克里金（OK）；可选背景偏差订正 |
| `InterpSgCressman` | Cressman 逐步订正；可选背景作初估场 |

---

## 2. 目录结构

| 路径 | 内容 |
| --- | --- |
| `src/` | 插件（`InterpSg*`） |
| `cli/` | `python -m cli` |
| `resource/conf.ini` | CLI 缺省参数 |
| `test/` | 配置与算法测试 |
| `nbs/` | Notebook |
| `docs/` | 本文档 |
| `utils/util_env.py` | 读取运行配置；并入 `00temp/utils` |

---

## 3. 共同约定

1. 按 `member` / `level` / `time` / `dtime` 切片分别插值后拼接。  
2. 站点经纬度转到球面笛卡尔坐标后用 KDTree 找近邻（距离为米量级）。  
3. 有 `background` 时：用 `InterpGgLinear` 对齐到目标网格；IDW / Gaussian / Kriging 插 `obs − bg_at_sta` 再叠回背景；Cressman 以对齐后的背景为初估场。  
4. 依赖：`meteva_base`、`numpy`、`scipy`、`interpolation_grid_grid.InterpGgLinear`、`utils.base_plugin`。

---

## 4. `InterpSgIdw`

### 原理

- 无背景：直接插站点值。  
- 有背景：插偏差再叠回背景。  
- `gaussian=False`（纯 IDW）：`w = 1 / d^decrease`；`effectR` 为硬截断——最近站距离超过该值时，无背景填 0，有背景则偏差置 0（保留背景）。  
- `gaussian=True`（IDW×高斯）：`w = (1 / d^decrease) * exp(-(d / effectR)^2)`，`effectR` 为高斯半径。

### 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `effectR` | `1000` | 纯 IDW：硬截断半径；高斯模式：高斯尺度（米量级） |
| `nearNum` | `8` | 每格点近邻站点数 |
| `decrease` | `2` | 距离衰减指数 |
| `gaussian` | `False` | 是否乘高斯核 |
| `outer_value` | `None` | 背景对齐越界填充，传给 `InterpGgLinear` |
| `sta` / `grid` / `background` | — | 见上文接口 |

### 示例

```python
from interp_sg_idw_plugin import InterpSgIdw
import meteva_base as meb

sta = meb.read_stadata_from_csv("sta.csv")  # 按实际读站方式
grid = meb.basicdata.grid([70, 140, 0.1], [15, 55, 0.1])

# 纯 IDW
result = InterpSgIdw(effectR=1000, nearNum=8, decrease=2).process(sta, grid)

# IDW × 高斯 + 背景偏差订正
bg = meb.read_griddata_from_nc("bg.nc")
result = InterpSgIdw(
    effectR=1000, nearNum=8, decrease=2, gaussian=True, outer_value=0.0
).process(sta, grid, background=bg)
```

---

## 5. `InterpSgGaussian`

### 原理

每格点只取最近 1 站，权重 `w = exp(-(d / halfR)^2)`；`d > halfR` 时权重为 0。有背景时同样先插偏差再叠回。

### 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `halfR` | `20` | 高斯半径（米量级），须 `> 0` |
| `outer_value` | `None` | 背景对齐越界填充 |
| `sta` / `grid` / `background` | — | 见上文接口 |

### 示例

```python
from interp_sg_gaussian_plugin import InterpSgGaussian

result = InterpSgGaussian(halfR=20).process(sta, grid)
result = InterpSgGaussian(halfR=20, outer_value=0.0).process(sta, grid, background=bg)
```

---

## 6. `InterpSgKriging`

### 原理

对每个目标格点取 `nearNum` 个近邻站，建立局部普通克里金方程组：

```text
γ(si, sj) λj + μ = γ(si, x0)
Σ λj = 1
```

估计值 = `Σ λj · zj`。矩阵奇异时该点退化为反距离加权。

变异函数可选 `spherical` / `exponential` / `gaussian`；`sill`、`range_` 为 `None` 时按当前切片站点样本自动估计。

### 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `model` | `"spherical"` | 变异函数：`spherical` / `exponential` / `gaussian` |
| `sill` | `None` | 基台；空则用站点方差 |
| `range_` | `None` | 变程（米量级）；空则近邻距离中位数粗估 |
| `nugget` | `0.0` | 块金，`>= 0` 且应小于基台 |
| `nearNum` | `20` | 每格点近邻站点数 |
| `outer_value` | `None` | 背景对齐越界填充 |
| `sta` / `grid` / `background` | — | 见上文接口 |

### 示例

```python
from interp_sg_kriging import InterpSgKriging

result = InterpSgKriging(model="spherical", nearNum=20).process(sta, grid)
result = InterpSgKriging(
    model="exponential", nearNum=20, nugget=0.0, outer_value=0.0
).process(sta, grid, background=bg)
```

---

## 7. `InterpSgCressman`

### 原理

经典逐步订正。初估场：无背景为 0；有背景则为对齐后的背景。对 `r_list` 中每个半径 R（通常由大到小）扫一遍：

```text
innov_i = obs_i − analysis_at_sta_i
analysis(x) ← analysis(x) + Σ w_i·innov_i / Σ w_i
w = (R² − d²) / (R² + d²)   （d ≥ R 时 w = 0）
```

下一扫在更新后的分析场上重新取站点值再算创新量。

### 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `r_list` | `(60000, 40000, 20000)` | 影响半径列表（米），须非空且各项 `> 0` |
| `nearNum` | `100` | 每格点近邻站点数上限，`>= 1` |
| `outer_value` | `None` | 背景对齐越界填充 |
| `sta` / `grid` / `background` | — | `background` 为初估场 |

### 示例

```python
from interp_sg_cressman_plugin import InterpSgCressman

result = InterpSgCressman(
    r_list=[60000, 40000, 20000], nearNum=100
).process(sta, grid)

result = InterpSgCressman(
    r_list=[60000, 40000, 20000], nearNum=100, outer_value=0.0
).process(sta, grid, background=bg)
```

---

## 8. CLI

在本包目录执行 `python -m cli`。未写参数先读 `resource/conf.ini`，再无则用预设；`sta`、`grid` 为空时报错。

| `--module` | 插件 |
| --- | --- |
| `idw` | `InterpSgIdw(gaussian=False)`；可用 `--background` |
| `idw_delta` | `InterpSgIdw(gaussian=True)`；`--grid` 同时作背景场（兼容旧入口） |
| `gaussian` | `InterpSgGaussian` |
| `kriging` | `InterpSgKriging` |
| `cressman` | `InterpSgCressman` |
| `total` | `idw` 旧别名 |

读写格式与格点→站点包对齐：

| 数据 | 支持格式 | 参数 |
| --- | --- | --- |
| 站点 | `csv` / `m3` | `--sta` / `--sta-type` |
| 格点 / 背景 | `nc` / `m4` | `--grid` / `--grid-type`，`--background` / `--background-type` |
| 输出格点 | `nc` / `m4` | `--output` / `--output-type`（可选；留空仅打印） |

```bash
python -m cli --module idw --sta sta.csv --grid grid.nc
python -m cli --module idw --sta sta.m3 --grid grid.m4 --output out.nc
python -m cli --module idw --sta sta.csv --grid grid.nc --background bg.nc
python -m cli --module idw_delta --sta sta.csv --grid bg.nc
python -m cli --module gaussian --sta sta.csv --grid grid.nc --half-r 20
python -m cli --module gaussian --sta sta.csv --grid grid.nc --background bg.nc --half-r 20
python -m cli --module kriging --sta sta.csv --grid grid.nc --kriging-model spherical --near-num 20
python -m cli --module cressman --sta sta.csv --grid grid.nc --r-list 60000,40000,20000
python -m cli --module cressman --sta sta.csv --grid grid.nc --background bg.nc
```

常用参数：`--effect-r` / `--near-num` / `--decrease`（IDW）、`--half-r`（Gaussian）、`--kriging-model` / `--kriging-sill` / `--kriging-range` / `--kriging-nugget`（Kriging）、`--r-list` / `--near-num`（Cressman）、`--output`、`--config`。

---

## 9. 选型提示

| 场景 | 建议 |
| --- | --- |
| 通用站点插值 | `InterpSgIdw` |
| 偏差订正且需平滑衰减 | `InterpSgIdw(gaussian=True)` 或 `InterpSgGaussian` |
| 需显式变异函数 / 局部 OK | `InterpSgKriging` |
| 多半径逐步订正（客观分析风格） | `InterpSgCressman` |
