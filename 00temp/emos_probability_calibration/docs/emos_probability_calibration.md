# emos算法改写

## 算法概述

`基于 `xarray` 的集合预报 EMOS（Ensemble Model Output Statistics）概率订正实现。算法思路源自 Met Office IMPROVER 的 EMOS calibration，主流程已去除对 `iris` 的强依赖，统一以六维数据结构支持**格点**与**站点**两类输入。

本次整理的核心能力包括：

- 基于历史集合预报和实况训练 EMOS 系数（`α`、`β`、`γ`、`δ`）。
- 支持正态分布 `norm` 和截断正态分布 `truncnorm` 的 CRPS 最小化。
- 根据训练系数生成订正分布的位置参数和尺度参数。
- 将 EMOS 结果输出为集合成员、阈值概率或分位数预报。
- 支持附加静态预测因子（`additional_fields`），如海拔 `altitude`、坡度 `slope` 等。
- 站点训练时自动匹配有效站点，并在订正阶段校验预报与系数空间一致性。

对外统一 API 为 `src/emos_calibration.py` 中的 `train_emos`、`apply_emos`、`create_prob_template`；`level` 维循环在该模块完成，内部逐层调用 `src/grid.py` 适配器与 `src/emos.py` 核心算法。

## 算法分类

- 分类：`07probability`
- 分类依据：算法面向集合预报概率订正和概率/分位数输出，属于集合及概率预报相关算法。

## 主要文件

| 类型          | 文件                              | 说明                                                        |
| ----------- | ------------------------------- | --------------------------------------------------------- |
| 对外 API      | `src/emos_calibration.py`       | `train_emos` / `apply_emos` / `create_prob_template` 统一入口 |
| 格点/站点适配     | `src/grid.py`                   | 六维输入规范化、站点压缩、系数散射、逐层 train/apply                          |
| 核心算法        | `src/emos.py`                   | EMOS 系数估计（CRPS 最小化）、ApplyEMOS、分位数/概率转换                    |
| 工具          | `src/xr_utils.py`               | xarray 坐标识别、分位数插值、预报类型判断等                                 |
| 示例 Notebook | `nbs/emos.ipynb`                | 站点测试：0/1/2 个 static 协变量下的训练、订正与可视化对比                      |
| 测试脚本        | `test_data/run_emos.py`         | 命令行查看输入/输出结构（不依赖 IMPROVER）                                |
| 对照脚本        | `test_data/compare_improver.py` | 可选：与 IMPROVER/Iris 结果对照（需安装 `improver`、`iris`）            |
| 测试数据        | `test_data/data/xarray/spot/`   | 站点 CSV 样例数据                                               |
| 测试数据        | `test_data/data/xarray/grid/`   | 格点六维 NetCDF 样例（如有）                                        |

## 数据约定

### 统一六维

预报与实况均使用维度 `(member, level, time, dtime, lat, lon)`：

| 字段       | 预报           | 实况       |
| -------- | ------------ | -------- |
| `time`   | 起报时间         | 有效时间     |
| `dtime`  | 预报时效（如 12 h） | 0        |
| `member` | 集合成员编号       | 恒为 0（占位） |

### 格点输入

- 格式：六维 `xarray.DataArray` / `Dataset`（NetCDF）。
- 空间维为完整 `lat × lon` 网格。

### 站点输入

- 格式：六列长表 `pandas.DataFrame`，或等价六维 `xarray`（稀疏 lat/lon，有效点外为 NaN）。
- 列：`member, level, time, dtime, lat, lon` + 数值列（如 `air_temperature`）。
- 相同 `(lat, lon)` 视为同一站点；内部可压缩为 `spot_index` 维进行训练/订正。

### 静态协变量（additional_fields）

- 每个 static 场在 `member/time/dtime` 上为单例，仅随 `(lat, lon)` 或站点变化。
- 训练时按文件名排序依次加入：`static_altitude.csv`、`static_slope.csv` …
- `predictor='mean'` 时，`emos_coefficient_beta` 的 `predictor_index` 维长度 = **1（集合均值）+ static 个数**：
  - 0 static → 1 个 β（`air_temperature`）
  - 1 static → 2 个 β（`air_temperature`, `altitude`）
  - 2 static → 3 个 β（`air_temperature`, `altitude`, `slope`）

### 当前站点样例数据规模

路径：`test_data/data/xarray/spot/`

| 文件                    | 行数  | 含义                      |
| --------------------- | --- | ----------------------- |
| `hf.csv`              | 90  | 3 member × 5 起报时次 × 6 站 |
| `truth.csv`           | 30  | 5 有效时刻 × 6 站            |
| `static_altitude.csv` | 6   | 6 站海拔                   |
| `static_slope.csv`    | 6   | 6 站坡度                   |

## 输入输出

### 系数训练 — `train_emos`

输入：

- `historic_forecasts`：历史集合预报（六维 xarray 或六列 DataFrame）。
- `truths`：对应实况。
- `additional_fields`：可选静态预测因子列表。
- 常用训练参数：`distribution='norm'`, `predictor='mean'`, `point_by_point=True`, `use_default_initial_guess=True`。

输出（`xr.Dataset`）：

- `emos_coefficient_alpha`：位置截距。
- `emos_coefficient_beta`：位置斜率，含 `predictor_index` 维及 `predictor_name` 坐标。
- `emos_coefficient_gamma`：尺度截距。
- `emos_coefficient_delta`：尺度斜率。
- 属性：`emos_n_stations`、`emos_valid_lat/lon`、`emos_training_dtime` 等（站点场景）。

### 应用订正 — `apply_emos`

输入：

- `forecast`：待订正集合、分位数或（配合模板）集合预报。
- `coefficients`：`train_emos` 输出的系数 Dataset。
- `additional_fields`：与训练阶段一致的 static 场。
- `prob_template`：可选，由 `create_prob_template` 生成，用于输出阈值概率。
- `percentiles` / `realizations_count`：分位数订正时使用。

输出（`xr.Dataset`）：

- 集合订正：`air_temperature(member, …)`。
- 概率订正：`probability_of_air_temperature_below_threshold(threshold, …)` 等。
- 分位数订正：`air_temperature(percentile, …)`，默认输出 10/50/90 分位。

### 概率模板 — `create_prob_template`

根据待订正集合预报生成与 IMPROVER 语义一致的概率模板：将 `member` 维替换为 `threshold` 维，供 `apply_emos(..., prob_template=...)` 使用。

## 示例 Notebook 说明

`nbs/emos.ipynb` 使用站点样例数据，在 **0 / 1 / 2 个 static** 三种配置下完成完整流程，并生成对比图：

1. **§1** 读取数据，分别训练并订正三种 static 场景。
2. **§2** 对比 α、γ、δ 系数；β 按 static 配置分图展示全部 predictor。
3. **§3** 各站订正后集合均值 vs 未订正集合均值。
4. **§4** 低于阈值（285/288/292 K）概率对比。
5. **§5** 分位值订正对比（订正输出 10/50/90；未订正输入为 0/50/100）。

运行方式：在 Jupyter 中打开 `nbs/emos.ipynb`，自第一个代码单元起 **Run All**。

最小调用示例：

```python
from src.emos_calibration import train_emos, apply_emos, create_prob_template

coeffs = train_emos(hf, truth, additional_fields=static_fields, distribution="norm", predictor="mean", point_by_point=True)
ensemble = apply_emos(forecast=apply_fc, coefficients=coeffs, additional_fields=static_fields)
prob_tpl = create_prob_template(apply_fc, thresholds=[285.0, 288.0, 292.0], thresholds_operator="below")
probability = apply_emos(forecast=apply_fc, coefficients=coeffs, prob_template=prob_tpl, additional_fields=static_fields)
```

## 测试脚本

```bash
# 包根目录子命令
python -m cli emos

# 查看输入/输出结构（spot，0/1/2 static；若仍保留旧脚本）
python test_data/run_emos.py
python test_data/run_emos.py --domain spot --static 1

# 可选：与 IMPROVER 对照（需 improver + iris）
python test_data/compare_improver.py
```

## 当前整理状态

当前仓库为 xarray 版 EMOS 独立整理目录，主流程不依赖 `iris`。

已完成：

- 六维格点/站点统一 API（`emos_calibration.py` + `grid.py`）。
- 站点稀疏匹配、系数 `predictor_name` 保留、订正阶段站点校验。
- 站点测试数据（CSV）与 Notebook 可视化（`nbs/emos.ipynb`）。
- 结构查看脚本 `test_data/run_emos.py`；可选 IMPROVER 对照脚本 `test_data/compare_improver.py`。

待处理 / 说明：

- 格点 NetCDF 测试数据目录 `test_data/data/xarray/grid/` 可按需补充；Notebook 当前以站点 CSV 为主。
- 正式入库时需确认包路径（当前为 `src.xxx` 相对导入）及 CLI 封装方式。
