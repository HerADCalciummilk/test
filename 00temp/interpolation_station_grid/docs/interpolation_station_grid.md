# interpolation_station_grid 算法说明

将站点观测融合到规则格点场。面向 `meteva_base` 站点表与六维格点场。

四个插件接口统一为：

```text
process(sta, grid=None, background=None)
```

- `sta`：站点数据  
- `grid`：目标网格信息（`meb.grid` / `glon`·`glat` 等）；缺省时均可从 `background` 取  
- `background`：格点场。`reprocess=True` 时 IDW / Gaussian / Cressman / Kriging 均必需；`False` 时可选（IDW/Gaussian/Cressman 作远点/初值；Kriging 仅取网格）

背景对齐依赖同级包 `interpolation_grid_grid.InterpGgLinear`（`outer_value` 控制越界填充）。结果 `attrs` 继承自输入站点。

---

## 1. 插件一览

| 插件 | 功能简介 |
| --- | --- |
| `InterpSgIdw` | 反距离权重（IDW）；默认绝对值+远点回退背景；`reprocess=True` 为偏差订正 |
| `InterpSgGaussian` | 最近邻 × 高斯；默认绝对值+`d>halfR` 回退背景；`reprocess=True` 为偏差订正 |
| `InterpSgKriging` | 局部普通克里金（OK）；`reprocess=False` 绝对值（背景可只取网格）；`True` 偏差订正（无远点填背景） |
| `InterpSgCressman` | Cressman：默认 km 绝对值加权；可选 `reprocess` 差值累加 |

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
3. 有 `background` 时：用 `InterpGgLinear` 对齐到目标网格（Cressman `reprocess=True` 直接在背景场上运算）。IDW / Gaussian / Cressman / Kriging 均支持 `reprocess`；Kriging 无远点硬截断，`False`/`True` 均可从背景取网格，但 `False` 不用背景场值。  
4. 依赖：`meteva_base`、`numpy`、`scipy`、`interpolation_grid_grid.InterpGgLinear`、`utils.base_plugin`。

---

## 4. `InterpSgIdw`

### 原理

- `reprocess=False`（默认）：插站点**绝对值**；`d > effectR` 用背景填（无背景填 0）。`grid` 与 `background` 至少其一。  
- `reprocess=True`：须 `background`；插 `obs−bg` 再叠回。`grid` 可省略（从背景取网格）。  
- `gaussian=False`：`w = 1 / d^decrease`，`effectR` 硬截断。  
- `gaussian=True`：`w = (1 / d^decrease) * exp(-(d / effectR)^2)`，`effectR` 为高斯半径。

### 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `effectR` | `1000` | 纯 IDW：硬截断半径；高斯模式：高斯尺度（米量级） |
| `nearNum` | `8` | 每格点近邻站点数 |
| `decrease` | `2` | 距离衰减指数 |
| `gaussian` | `False` | 是否乘高斯核 |
| `outer_value` | `None` | 背景对齐越界填充，传给 `InterpGgLinear` |
| `reprocess` | `False` | `False` 绝对值+远点回退背景；`True` 偏差订正 |
| `sta` / `grid` / `background` | — | 见上文接口；均可只传 `background`（True 时 `background` 必需） |

### 示例

```python
from interp_sg_idw_plugin import InterpSgIdw
import meteva_base as meb

sta = meb.read_stadata_from_csv("sta.csv")  # 按实际读站方式
grid = meb.basicdata.grid([70, 140, 0.1], [15, 55, 0.1])
bg = meb.read_griddata_from_nc("bg.nc")

# 绝对值 IDW，超距回退背景（默认 reprocess=False）
result = InterpSgIdw(effectR=1000, nearNum=8, decrease=2).process(
    sta, grid, background=bg
)
# 也可只传背景（从中取网格）
result = InterpSgIdw(effectR=1000, nearNum=8, decrease=2).process(
    sta, background=bg
)

# 偏差订正 + 高斯权重（可只传 background）
result = InterpSgIdw(
    effectR=1000, nearNum=8, decrease=2, gaussian=True, reprocess=True, outer_value=0.0
).process(sta, background=bg)
```

---

## 5. `InterpSgGaussian`

### 原理

每格点只取最近 1 站，权重 `w = exp(-(d / halfR)^2)`。

- `reprocess=False`（默认）：插绝对值；`d > halfR` 用背景填（无背景填 0）。
- `reprocess=True`：须背景；插 `obs−bg` 再叠回（超距偏差为 0 → 保留背景）。

### 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `halfR` | `20` | 高斯半径（米量级），须 `> 0` |
| `outer_value` | `None` | 背景对齐越界填充 |
| `reprocess` | `False` | `False` 绝对值+远点回退背景；`True` 偏差订正 |
| `sta` / `grid` / `background` | — | 见上文接口；均可只传 `background` |

### 示例

```python
from interp_sg_gaussian_plugin import InterpSgGaussian

result = InterpSgGaussian(halfR=20).process(sta, grid)
result = InterpSgGaussian(halfR=20, outer_value=0.0, reprocess=False).process(
    sta, grid, background=bg
)
result = InterpSgGaussian(halfR=20, outer_value=0.0, reprocess=True).process(
    sta, background=bg
)
```

---

## 6. `InterpSgKriging`

### 原理

对每个目标格点取 `nearNum` 个近邻站，建立局部普通克里金方程组：

```text
γ(si, sj) λj + μ = γ(si, x0)
Σ λj = 1
```

估计值 = `Σ λj · zj`。矩阵奇异时该点退化为反距离加权。**无距离硬截断**（不做远点填背景）。

- `reprocess=False`（默认）：插绝对值；`grid` 与 `background` 至少其一（有背景时**只取网格**，不用场值）。
- `reprocess=True`：须 `background`；插 `obs−bg` 再叠回；`grid` 可省略（从背景取）。

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
| `reprocess` | `False` | `False` 绝对值（背景可只作网格源）；`True` 偏差订正 |
| `sta` / `grid` / `background` | — | 均可只传 `background`（True 时 `background` 必需） |

### 示例

```python
from interp_sg_kriging import InterpSgKriging

result = InterpSgKriging(model="spherical", nearNum=20).process(sta, grid)
# 绝对值：只传背景场取网格（不用场值）
result = InterpSgKriging(model="spherical", nearNum=20, reprocess=False).process(
    sta, background=bg
)
result = InterpSgKriging(
    model="exponential", nearNum=20, nugget=0.0, outer_value=0.0, reprocess=True
).process(sta, background=bg)  # 偏差订正
```

---

## 7. `InterpSgCressman`

### 原理

- `reprocess=False`（默认）：公里半径 Cressman **绝对值加权替换**；有背景时先双线性对齐作初值，有邻站的格点写为站点加权平均。
- `reprocess=True`：度制半径下对背景做 **差值累加再处理**（须 `background`）；`r_list` 单位为度。

权重（km 核）：

```text
w = (R² − d²) / (R² + d²)   （d ≥ R 时 w = 0）
```

### 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `r_list` | False：`(60000,40000,20000)`；True：`(1.0,0.8,0.6,0.4)` | False 为米，True 为度 |
| `nearNum` | `100` | 近邻站点数上限，`>= 1` |
| `outer_value` | `None` | False 路径背景对齐越界填充 |
| `reprocess` | `False` | 是否走差值累加 |
| `sta` / `grid` / `background` | — | False 须 `grid`（或由背景取网格）；True 须 `background` |

### 示例

```python
from interp_sg_cressman_plugin import InterpSgCressman

result = InterpSgCressman(
    r_list=[60000, 40000, 20000], nearNum=100
).process(sta, grid)

result = InterpSgCressman(
    r_list=[60000, 40000, 20000], nearNum=100, outer_value=0.0
).process(sta, grid, background=bg)

result = InterpSgCressman(
    r_list=[1.0, 0.8, 0.6, 0.4], reprocess=True, rain_limit=0.01
).process(sta, background=bg)
```

---

## 8. CLI

在本包目录执行 `python -m cli`。未写参数先读 `resource/conf.ini`，再无则用预设。`sta` 必填；`--grid` 与 `--background` 至少其一。

| `--module` | 插件 |
| --- | --- |
| `idw` | `InterpSgIdw(gaussian=False)` |
| `idw_delta` | `InterpSgIdw(gaussian=True, reprocess=True)`；须 `--background` |
| `gaussian` | `InterpSgGaussian` |
| `kriging` | `InterpSgKriging` |
| `cressman` | `InterpSgCressman` |
| `total` | `idw` 旧别名 |

| 数据 / 开关 | 支持格式 | 参数 |
| --- | --- | --- |
| 站点 | `csv` / `m3` | `--sta` / `--sta-type` |
| 格点 / 背景 | `nc` / `m4` | `--grid` / `--grid-type`，`--background` / `--background-type` |
| 路径开关 | — | `--reprocess true\|false`（默认 false；true 须 background） |
| 输出格点 | `nc` / `m4` | `--output` / `--output-type`（可选；留空仅打印） |

```bash
python -m cli --module idw --sta sta.csv --grid grid.nc
python -m cli --module idw --sta sta.csv --background bg.nc
python -m cli --module idw --sta sta.csv --background bg.nc --reprocess true
python -m cli --module idw --sta sta.m3 --grid grid.m4 --output out.nc
python -m cli --module idw_delta --sta sta.csv --background bg.nc
python -m cli --module idw_delta --sta sta.csv --grid grid.nc --background bg.nc
python -m cli --module gaussian --sta sta.csv --grid grid.nc --half-r 20
python -m cli --module kriging --sta sta.csv --background bg.nc --reprocess true
python -m cli --module cressman --sta sta.csv --grid grid.nc --r-list 60000,40000,20000
python -m cli --module cressman --sta sta.csv --background bg.nc --reprocess true --r-list 1.0,0.8,0.6,0.4
```

常用参数：`--reprocess`、`--effect-r` / `--near-num` / `--decrease`（IDW）、`--half-r`（Gaussian）、`--kriging-model` / `--kriging-sill` / `--kriging-range` / `--kriging-nugget`（Kriging）、`--r-list` / `--near-num`（Cressman）、`--output`、`--config`。

---

## 9. 选型提示

| 场景 | 建议 |
| --- | --- |
| 通用站点插值 | `InterpSgIdw` |
| 偏差订正且需平滑衰减 | `InterpSgIdw(gaussian=True)` 或 `InterpSgGaussian` |
| 需显式变异函数 / 局部 OK | `InterpSgKriging` |
| 多半径 Cressman（km 绝对值 / 可选差值累加） | `InterpSgCressman` |
