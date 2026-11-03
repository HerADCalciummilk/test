# samos算法改写

## 算法概述

基于 `xarray` 的集合预报 **SAMOS**（Standardized Anomaly Model Output Statistics）概率订正实现。算法思路源自 Met Office IMPROVER：先用 **GAM** 估计预报/实况气候均值与标准差，将变量变换为标准化异常，再在异常空间上训练 **EMOS**，订正后再用实况气候态还原到原始单位。

主流程不依赖 `iris`，统一以六维数据结构支持**格点**与**站点**两类输入。

本次整理的核心能力包括：

- `train_gams`：对历史集合预报与实况分别拟合气候均值/标准差 GAM。
- `train_samos`：在标准化异常上调用 `emos_calibration.train_emos` 得到 α、β、γ、δ。
- `apply_samos`：GAM 气候态 → 异常 → EMOS 参数 → 实况气候还原 → 集合/概率/分位数输出。
- GAM 特征可为坐标（`lat`/`lon`）及静态场（站点 `altitude`/`slope`，格点 `orography`/`land_fraction` 等）。
- 静态因子进入 GAM（`gam_additional_fields` / `features`）；异常 EMOS 默认不再附带 static，系数按站一维。
- API 仍可选 `emos_additional_fields`（与 IMPROVER 兼容），业务默认不要用。

对外 API：`gam_calibration.train_gams`、`samos_calibration.train_samos` / `apply_samos`；概率模板复用 `emos_calibration.create_prob_template`。

## 算法分类

- 分类：`07probability`
- 分类依据：算法面向集合预报概率订正和概率/分位数输出，属于集合及概率预报相关算法。

## 主要文件

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| SAMOS API | `src/samos_calibration.py` | `train_samos` / `apply_samos` |
| GAM API | `src/gam_calibration.py` | `train_gams` |
| GAM 适配 | `src/gam_grid.py` | 气候统计、异常变换、静态因子并入 |
| GAM 模型 | `src/gam_models.py` | pyGAM 拟合/预测 |
| EMOS 依赖 | 兄弟包 `emos_probability_calibration/src/emos_*.py` | `train_emos` / `apply_emos` / `create_prob_template` |
| CLI | `cli/run_samos.py` | `process`：读入 → GAM+EMOS → 可选写出 |
| 示例 Notebook | `nbs/samos.ipynb` | 站点 SAMOS：0/1/2 static 对比 |
| 结果演示 | `tests/samos_probability_calibration_main.py` | 打印输入/输出结构 |
| 测试数据 | `test_data/spot/`、`test_data/grid/` | 站点 CSV / 格点 NetCDF 样例 |

## 数据约定

### 统一六维

预报与实况均使用维度 `(member, level, time, dtime, lat, lon)`：

| 字段       | 预报           | 实况       |
| -------- | ------------ | -------- |
| `time`   | 起报时间         | 有效时间     |
| `dtime`  | 预报时效（如 12 h） | 0        |
| `member` | 集合成员编号       | 恒为 0（占位） |

### 格点 / 站点输入

与 EMOS 相同：格点为完整 `lat × lon` 六维 xarray；站点为六列 DataFrame 或稀疏六维 xarray。

### 静态协变量与 GAM 特征

推荐分工（本仓库 Notebook / 对照脚本默认）：

- **静态因子只进 GAM**：`train_gams(..., additional_fields=static)`，并在 `features` 中写上变量名（如 `altitude`、`slope`）。
- **异常空间 EMOS 不再附带 static**：`emos_additional_fields=None`。此时 α、γ、δ 及 β（仅 anomaly 集合均值一项）均为**与站点对齐的一维系数**（`emos_n_stations` 与有效站一致；存储上可能散射到稀疏 `lat×lon`，有效点外为 NaN）。
- API 仍保留可选的 `emos_additional_fields`（与 IMPROVER 一致），但业务默认不要把海拔/坡度再当地形预测因子塞进异常 EMOS。

站点样例三种配置：

| static 个数 | GAM `features` | 静态文件 | 异常 EMOS β |
| --- | --- | --- | --- |
| 0 | `lat, lon` | 无 | 1 项（anomaly mean） |
| 1 | `lat, lon, altitude` | `static_altitude.csv` | 同上 |
| 2 | `lat, lon, altitude, slope` | + `static_slope.csv` | 同上 |

### 当前站点样例数据规模

路径：`test_data/spot/`

| 文件                    | 行数  | 含义                      |
| --------------------- | --- | ----------------------- |
| `hf.csv`              | 90  | 3 member × 5 起报时次 × 6 站 |
| `truth.csv`           | 30  | 5 有效时刻 × 6 站            |
| `static_altitude.csv` | 6   | 6 站海拔                   |
| `static_slope.csv`    | 6   | 6 站坡度                   |

样例时次较短，Notebook / 对照脚本使用 `window_length=3`（奇数窗；完整业务序列常用更大窗口如 11）。

## 输入输出

### GAM 训练 — `train_gams`

输入：

- `input_field`：历史预报或实况。
- `features`：GAM 预测因子名列表。
- `model_specification`：pyGAM 项规格（如对各特征使用 `linear` / `spline`）。
- `additional_fields`：可选静态场。
- `window_length`：气候滚动窗长度（奇数）。

输出：长度为 2 的模型列表 `[mean_gam, std_gam]`；若有效时次不足以做滚动窗则返回 `None`。

### 系数训练 — `train_samos`

输入：

- `historic_forecasts` / `truths`：历史集合与实况。
- `forecast_gams` / `truth_gams`：`train_gams` 结果。
- `gam_features` / `gam_additional_fields`：须与训练 GAM 时一致（静态因子在这里）。
- `emos_additional_fields`：默认 `None`；异常 EMOS 按站一维。仅在需要额外地形预测因子时再传入。
- 常用 EMOS 参数：`distribution='norm'`, `predictor='mean'`, `point_by_point=True`。

输出：与 `train_emos` 相同的系数 `xr.Dataset`（`emos_coefficient_alpha/beta/gamma/delta`），定义在**标准化异常空间**；默认 β 的 `predictor_index` 长度为 1。

### 应用订正 — `apply_samos`

输入：

- `forecast`：待订正集合、分位数或（配合模板）集合预报。
- `forecast_gams` / `truth_gams` / `emos_coefficients`。
- `gam_features` 与两侧 `*_additional_fields`。
- `prob_template`：可选，由 `emos_calibration.create_prob_template` 生成。
- `percentiles` / `realizations_count`：分位数订正时使用。

输出（`xr.Dataset`，原始物理单位）：

- 集合：`air_temperature(member, …)`
- 概率：`probability_of_air_temperature_below_threshold(threshold, …)`
- 分位数：`air_temperature(percentile, …)`（默认可输出 10/50/90）

## 示例 Notebook 说明

`nbs/samos.ipynb` 使用站点样例数据，在 **0 / 1 / 2 个 GAM static** 三种配置下完成完整 SAMOS 流程并出图：

1. **§1** 读取数据；`train_gams`（含 static）→ `train_samos`（`emos_additional_fields=None`）→ `apply_samos`。
2. **§2** 按站一维对比 α、β、γ、δ（四种配置下 β 均为单 predictor；差异来自 GAM 气候异常不同）。
3. **§3** 各站订正后集合均值 vs 未订正集合均值。
4. **§4** 低于阈值（285/288/292 K）概率对比。
5. **§5** 分位值订正对比（订正输出 10/50/90；未订正输入为 0/50/100）。

运行方式：在 Jupyter 中打开 `nbs/samos.ipynb`，自第一个代码单元起 **Run All**。建议内核使用已安装 `pygam`、且 NumPy/SciPy 与之兼容的环境（如 `improver_samos`）。

最小调用示例：

```python
from emos_calibration import create_prob_template
from gam_calibration import train_gams
from samos_calibration import train_samos, apply_samos

features = ["lat", "lon", "altitude"]
model_spec = [["linear", [i], {}] for i in range(len(features))]
static = [altitude_df]  # 可选

forecast_gams = train_gams(hf, features, model_spec, additional_fields=static, window_length=3, max_iter=30)
truth_gams = train_gams(truth, features, model_spec, additional_fields=static, window_length=3, max_iter=30)

coeffs = train_samos(
    hf, truth, forecast_gams, truth_gams, features,
    gam_additional_fields=static,
    emos_additional_fields=None,  # 静态因子已由 GAM 消化
    distribution="norm",
    predictor="mean",
    point_by_point=True,
)

ensemble = apply_samos(
    forecast=apply_fc,
    forecast_gams=forecast_gams,
    truth_gams=truth_gams,
    emos_coefficients=coeffs,
    gam_features=features,
    gam_additional_fields=static,
    emos_additional_fields=None,
)
prob_tpl = create_prob_template(apply_fc, thresholds=[285.0, 288.0, 292.0], thresholds_operator="below")
probability = apply_samos(
    forecast=apply_fc,
    forecast_gams=forecast_gams,
    truth_gams=truth_gams,
    emos_coefficients=coeffs,
    gam_features=features,
    gam_additional_fields=static,
    emos_additional_fields=None,
    prob_template=prob_tpl,
)
```

## 运行方式

在包根目录 `samos_probability_calibration/` 下（需同级存在 `emos_probability_calibration/`）：

```bash
# 包根目录子命令
python -m cli samos

# 或直接运行 CLI 脚本
python cli/run_samos.py

# 查看输入/输出结构（spot/grid，0/1/2 static）
python tests/samos_probability_calibration_main.py
python tests/samos_probability_calibration_main.py --domain spot --static 1
```

## 当前整理状态

本目录为独立的 `samos_probability_calibration` 包，主流程不依赖 `iris`，运行时依赖兄弟包 `emos_probability_calibration`。

已完成：

- 六维格点/站点统一 SAMOS API（`src/samos_*.py` + `src/gam_*.py`）。
- `cli/`、`docs/`、`nbs/`、`test_data/`、结果演示脚本。
