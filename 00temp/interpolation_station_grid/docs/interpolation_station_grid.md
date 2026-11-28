# interpolation_station_grid 算法说明

将站点观测融合到规则格点场。面向 `meteva_base` 站点表与六维格点场。

**推荐对外入口**：`InterpSg(method=...)`，由 `method` 分派到各算法插件。各 `InterpSg*` 仍可单独使用。接口统一为：

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
| `InterpSg` | **统一入口**：`method` 选算法，再转调下列插件 |
| `InterpSgIdw` | 反距离权重（IDW）；默认绝对值+远点回退背景；`reprocess=True` 为偏差订正 |
| `InterpSgGaussian` | 最近邻 × 高斯；默认绝对值+`d>halfR` 回退背景；`reprocess=True` 为偏差订正 |
| `InterpSgKriging` | 局部普通克里金（OK）；`reprocess=False` 绝对值（背景可只取网格）；`True` 偏差订正（无远点填背景） |
| `InterpSgCressman` | Cressman：默认 km 绝对值加权；可选 `reprocess` 差值累加 |

### 1.1 `InterpSg`（统一入口）

构造参数全部显式列出；按 `method` 选用子集，其余忽略。CLI 的 `method=` 与之同值域，内部已走本入口。

| `method` | 子插件 | 说明 |
| --- | --- | --- |
| `idw` | `InterpSgIdw` | 纯 IDW；`reprocess` 与 `gaussian` 相互独立 |
| `gaussian` | `InterpSgGaussian` | |
| `kriging` | `InterpSgKriging` | |
| `cressman` | `InterpSgCressman` | |

| 参数 | 默认 | 适用 `method` | 说明 |
| --- | --- | --- | --- |
| `method` | `idw` | 全部 | 见上表 |
| `reprocess` | `False` | 全部 | 绝对值 / 偏差路径，与 `gaussian` 独立 |
| `outer_value` | `None` | 全部 | 背景对齐越界填充 |
| `effectR` | `1000` | `idw` | 硬截断或高斯尺度（千米） |
| `nearNum` | `None` | `idw` / `kriging` / `cressman` | `None`→子插件默认 8/20/100 |
| `decrease` | `2` | `idw` | 距离衰减指数 |
| `gaussian` | `False` | `idw` | 是否乘高斯核；不随 `reprocess` 自动开启 |
| `halfR` | `20` | `gaussian` | 高斯半径（千米） |
| `model` | `spherical` | `kriging` | 变异函数：`spherical` / `exponential` / `gaussian` |
| `sill` | `None` | `kriging` | 基台；`None` 时用站点方差 |
| `range_` | `None` | `kriging` | 变程（千米） |
| `nugget` | `0.0` | `kriging` | 块金 |
| `r_list` | `None` | `cressman` | 影响半径列表；`None` 时：`reprocess=False` 默认 `(60.0, 40.0, 20.0)`（千米），`reprocess=True` 默认 `(1.0, 0.8, 0.6, 0.4)`（度） |
| `rain_limit` | `None` | `cressman`（仅 `reprocess=True`） | 降水回退阈值：格点值 ≤ 阈值时回退（步内回退到该步之前的场值，结束时回退到背景场）；`None` 不回退；`reprocess=False` 忽略此参数 |
| `num_limit` | `1.0` | 同上 | |
| `smooth` | `0.001` | 同上 | |
| `power_param` | `2.0` | 同上 | |
| `r_km_scale` | `1.35` | 同上 | |
| `innov_gain` | `1.0` | 同上 | |
| `residual_passes` | `0` | 同上 | |
| `residual_degree_polish` | `True` | 同上 | |
| `residual_polish_rounds` | `1` | 同上 | |
| `degree_blend` | `0.85` | 同上 | |
| `station_anchor_radius` | `0.35` | 同上 | |
| `station_anchor_strength` | `0.0` | 同上 | |
| `sta` / `grid` / `background` | — | `process` | 同各 `InterpSg*` |

```python
from interp_sg_plugin import InterpSg

result = InterpSg(
    method="idw", effectR=1000, nearNum=8, decrease=2, reprocess=False
).process(sta, grid, background=bg)

# 偏差订正（纯 IDW 权重）
result = InterpSg(method="idw", reprocess=True, effectR=1000, nearNum=8).process(
    sta, background=bg
)
# 偏差订正 + 高斯权重（原 idw_delta 的写法，需显式 gaussian=True）
result = InterpSg(
    method="idw", reprocess=True, gaussian=True, effectR=1000, nearNum=8
).process(sta, background=bg)

result = InterpSg(method="gaussian", halfR=20).process(sta, grid)
result = InterpSg(
    method="kriging", model="spherical", nearNum=20, reprocess=True
).process(sta, background=bg)
result = InterpSg(
    method="cressman", r_list=[60, 40, 20], nearNum=100
).process(sta, grid)
```

---

## 2. 目录结构

| 路径 | 内容 |
| --- | --- |
| `src/` | 插件（`InterpSg*`） |
| `cli/` | `*_cli.py` 中的 `process`（`@merge_params`）；`python -m interpolation_station_grid` 为命令行入口 |
| `resource/conf.ini` | CLI 缺省参数 |
| `test/` | 配置与算法测试 |
| `nbs/` | Notebook |
| `docs/` | 本文档 |
| `utils/` | 无业务代码；合参由 `00temp/utils/merge_params.py` 提供 |

---

## 3. 共同约定

1. 按 `member` / `level` / `time` / `dtime` 切片分别插值后拼接。  
2. 站点经纬度转到球面笛卡尔坐标后用 KDTree 找近邻（距离为千米，与 `lon_lat_to_cartesian` 的 `R=ER` 输出一致）。  
3. 有 `background` 时：用 `InterpGgLinear` 对齐到目标网格（Cressman `reprocess=True` 直接在背景场上运算）。IDW / Gaussian / Cressman / Kriging 均支持 `reprocess`；Kriging 无远点硬截断，`False`/`True` 均可从背景取网格，但 `False` 不用背景场值。  
4. 依赖：`meteva_base`、`numpy`、`scipy`、`interpolation_grid_grid.InterpGgLinear`、`utils.base_plugin`。

---

## 4. `InterpSgIdw`

### 原理

- `reprocess=False`（默认）：插站点**绝对值**；`d > effectR` 用背景填（无背景填 0）。`grid` 与 `background` 至少其一。  
- `reprocess=True`：须 `background`；插 `obs−bg` 再叠回。`grid` 可省略（从背景取网格）。  
- `gaussian=False`：`w = 1 / d^decrease`，`effectR` 硬截断。
- `gaussian=True`：`w = (1 / d^decrease) * exp(-(d / effectR)^2)`，`effectR` 为高斯半径。
- `reprocess` 与 `gaussian` 独立：前者只决定绝对值 / 偏差路径，后者只决定权重形状。

### 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `effectR` | `1000` | 纯 IDW：硬截断半径；高斯模式：高斯尺度（千米） |
| `nearNum` | `8` | 每格点近邻站点数 |
| `decrease` | `2` | 距离衰减指数 |
| `gaussian` | `False` | 是否乘高斯核（与 `reprocess` 独立） |
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
| `halfR` | `20` | 高斯半径（千米），须 `> 0` |
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
| `range_` | `None` | 变程（千米）；空则近邻距离中位数粗估 |
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
| `r_list` | False：`(60,40,20)`；True：`(1.0,0.8,0.6,0.4)` | False 为千米，True 为度 |
| `nearNum` | `100` | 近邻站点数上限，`>= 1` |
| `outer_value` | `None` | False 路径背景对齐越界填充 |
| `reprocess` | `False` | 是否走差值累加 |
| `sta` / `grid` / `background` | — | False 须 `grid`（或由背景取网格）；True 须 `background` |

### 示例

```python
from interp_sg_cressman_plugin import InterpSgCressman

result = InterpSgCressman(
    r_list=[60, 40, 20], nearNum=100
).process(sta, grid)

result = InterpSgCressman(
    r_list=[60, 40, 20], nearNum=100, outer_value=0.0
).process(sta, grid, background=bg)

result = InterpSgCressman(
    r_list=[1.0, 0.8, 0.6, 0.4], reprocess=True, rain_limit=0.01
).process(sta, background=bg)
```

---

## 8. CLI

CLI 结构遵循 `CLI组织说明.md`：`process` 定义在 `cli/interpolation_station_grid_cli.py` 并挂 `@merge_params()`；`key` 与 `process` 形参名相同，`resource/conf.ini` 的键与之一一对应。

参数优先级：命令行 / Python 显式传入 > `config=` 指定的输入 ini > `resource/conf.ini` 非空项 > 签名预设。`sta` 必填；`grid` 与 `background` 至少其一；`reprocess=true` 须 `background`。

调用方式（工作目录为 `00temp`）：

```bash
python -m interpolation_station_grid method=idw sta=resource/obs_gust_d24.csv grid=resource/target_grid.nc
```

- 包根 `__main__.py` 经 `utils/nimm_cli.py` 调用 `process`；`method` 为算法选择键（不用 `module`，因为 `nimm_cli` 占用了 `module`）。
- 包内相对路径一律按包根（`interpolation_station_grid/`）解析。
- Python 调用：`from cli.interpolation_station_grid_cli import process` 后 `process(method="idw", ...)`。
- `cli/__main__.py` 也支持在本包目录执行 `python -m cli key=value ...`（无参数时读 `conf.ini` 与签名预设）。

| `method` | `InterpSg(method=...)` |
| --- | --- |
| `idw` | `method="idw"`；`idw_gaussian` 默认 false，需显式开启高斯权重；`reprocess` 与之独立 |
| `gaussian` | `method="gaussian"`（`gaussian_half_r`） |
| `kriging` | `method="kriging"` |
| `cressman` | `method="cressman"` |

| 数据 / 开关 | 支持格式 | 参数 |
| --- | --- | --- |
| 站点 | `csv` / `m3` | `sta` / `sta_type` |
| 格点 / 背景 | `nc` / `m4` | `grid` / `grid_type`，`background` / `background_type` |
| 路径开关 | — | `reprocess=true\|false`（默认 false；true 须 background） |
| 输出格点 | `nc` / `m4` | `output` / `output_type`（可选；留空仅打印） |

```bash
# 在 00temp 目录执行
python -m interpolation_station_grid method=idw sta=resource/obs_gust_d24.csv grid=resource/target_grid.nc output=resource/out_idw.nc
python -m interpolation_station_grid method=idw sta=resource/obs_gust_d24.csv background=resource/bg_fcst_idw.nc
python -m interpolation_station_grid method=idw sta=resource/obs_gust_d24.csv background=resource/bg_fcst_idw.nc reprocess=true
python -m interpolation_station_grid method=idw sta=resource/obs_gust_d24.csv background=resource/bg_fcst_idw.nc reprocess=true idw_gaussian=true
python -m interpolation_station_grid method=idw sta=sta.m3 grid=grid.m4 output=out.m4
python -m interpolation_station_grid method=gaussian sta=sta.csv grid=grid.nc gaussian_half_r=20
python -m interpolation_station_grid method=kriging sta=sta.csv background=bg.nc reprocess=true
python -m interpolation_station_grid method=cressman sta=sta.csv grid=grid.nc cressman_r_list=60,40,20
python -m interpolation_station_grid method=cressman sta=sta.csv background=bg.nc reprocess=true cressman_r_list=1.0,0.8,0.6,0.4
```

常用参数（键名即 `process` 形参名，与 `conf.ini` 对应）：`reprocess`、`outer_value`（默认留空）、`idw_gaussian`（仅 idw，默认 false）、`idw_effect_r` / `idw_near_num` / `idw_decrease`（IDW）、`gaussian_half_r`（Gaussian）、`kriging_model` / `kriging_near_num` / `kriging_sill` / `kriging_range` / `kriging_nugget`（Kriging）、`cressman_r_list`（默认留空：`reprocess=false` 为 `60,40,20` 千米，`true` 为 `1.0,0.8,0.6,0.4` 度） / `cressman_near_num`（Cressman）、`output`、`config`。

`idw_effect_r`、`gaussian_half_r` 的单位是千米，可写小数（如 `gaussian_half_r=12.5`）。

Cressman 度制路径（`method=cressman` 且 `reprocess=true`）的高级参数，键名为 `cressman_` 加插件形参名，预设值与 `InterpSgCressman` 一致，只在该路径生效，其它情况被忽略：

| CLI 键 | 预设 | 含义 |
|--------|------|------|
| `cressman_rain_limit` | 留空 | 降水回退阈值，结果 ≤ 阈值的格点回退；留空不回退 |
| `cressman_num_limit` | `1.0` | 格点影响圈内至少几个站才更新 |
| `cressman_smooth` / `cressman_power_param` | `0.001` / `2.0` | 度制幂权重 `1/(d+smooth)^power_param` |
| `cressman_r_km_scale` | `1.35` | 度制半径换千米半径的缩放（仅千米核创新量扫） |
| `cressman_innov_gain` | `1.0` | 创新量增益（仅千米核创新量扫） |
| `cressman_residual_passes` | `0` | 追加创新量再扫次数 |
| `cressman_residual_degree_polish` / `cressman_residual_polish_rounds` | `true` / `1` | 创新量扫之后的度制抛光及其轮数 |
| `cressman_degree_blend` | `0.85` | 创新量扫结果与纯度制结果的融合权重 `[0,1]`；`1.0` 为纯度制，此时千米核相关参数不起作用 |
| `cressman_station_anchor_radius` / `cressman_station_anchor_strength` | `0.35` / `0.0` | 站点锚定半径（度）与强度 `[0,1]`，强度 0 即不锚定 |

复现 rain24 两种形态：original 用 `cressman_degree_blend=1.0 cressman_rain_limit=0.01`，aligned 用默认 `cressman_degree_blend=0.85`。

```bash
python -m interpolation_station_grid method=cressman sta=sta.csv background=bg.nc reprocess=true cressman_r_list=1.0,0.8,0.6,0.4 cressman_degree_blend=1.0 cressman_rain_limit=0.01
```

---

## 9. 选型提示

业务侧优先 `InterpSg(method=...)`；下表为算法选择：

| 场景 | 建议 |
| --- | --- |
| 通用站点插值 | `method="idw"`（或直接 `InterpSgIdw`） |
| 偏差订正且需平滑衰减 | `method="idw", reprocess=True, gaussian=True`，或 `method="gaussian"` |
| 需显式变异函数 / 局部 OK | `method="kriging"` |
| 多半径 Cressman（km 绝对值 / 可选差值累加） | `method="cressman"` |
