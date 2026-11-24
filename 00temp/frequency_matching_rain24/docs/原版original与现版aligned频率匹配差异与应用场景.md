# 原版与现版频率匹配：差异与应用场景

两条流水线共用同一套频率匹配业务逻辑；差别在订正切片中的 **Cressman 类插值**与 **半拉格朗日平流外推** 实现。光流估 UV 两边仍用同一原版 `OpticalFlow`。产品对比图见同包 notebook：`nbs/原版与现版产品对比图.ipynb`。

---

## 1. 共同点

1. 分块相似检索，选历史相似个例；
2. 估 UV → 插值历史实况到格点 → **半拉格朗日平流外推**订正当前模式场；
3. `FrequencyMatch`：按实况频率结构匹配，出站点/格点产品。

相似判据、频率匹配阈值、分块与输出拼装两边相同。

| 环节 | 原版 | 现版 |
|------|------|------|
| 相似检索 / 频率匹配 | 相同 | 相同 |
| 光流估 UV | 原版 `OpticalFlow` | 相同 |
| 站点→格点插值 | 度制 `GressManInterpolation` | 项目 `interp_sg_cressman` + `cressman_project_innov` 再处理 |
| 降水场外推 | 度制 `Lagrangian.simple_semi_lagrangian_in_angle` | `LagrangianAligned` → 项目 `Extrapolation.forecast`（`n_iter=0`） |
| CLI | 同一入口 `cli/frequency_matching_rain24_cli.py`，`match_mode=original` | 同左，`match_mode=aligned`（默认） |
| 配套配置 | `resource/conf.ini`（plugin→`ecmwf.json`） | `resource/conf_aligned.ini`（plugin→`ecmwf_aligned.json`） |
| 代码路径 | 同一套 `*_plugin.py` + `*_plugin_util.py`；`match_mode` 只换 Cressman/外推 | 再处理在 `utils/cressman_extrap_reprocess.py` |

---

## 2. 差异分析

### 2.1 半拉格朗日平流外推

已知降水场与 UV，求风场作用下的降水分布，即沿光流轨迹的半拉格朗日平流外推。

| | 原版 | 现版 |
|--|------|------|
| 实现 | `Lagrangian`：经纬度网格上位移 = UV（度/步）×Δt，双线性回采 | `LagrangianAligned`：度制 UV 换像素速度，调用 `Extrapolation.forecast` |
| 风场用法 | 当地风、一步跳 | `n_iter=0`，当地风一步 |
| 边界 | 索引夹到域内再插值 | 出界夹边回填 |

差异在数值核：度制网格自写双线性 vs 项目像素系外推核及单位换算、边界处理。短时效雨核位移对 UV 与边界更敏感。

### 2.2 Cressman 类插值

订正链中插值用于历史实况铺格、最终格点合成等。两边均为多半径、由观测订正背景，核不同：

| | 原版（GressMan） | 现版（项目核再处理） |
|--|------------------|----------------------|
| 距离 | 度制圆 √(Δlon²+Δlat²)≤R° | 项目核为 km，再处理用度制圆裁剪/融合 |
| 权重 | 幂权重创新（观测−背景）累加回背景 | 项目公式 (R²−d²)/(R²+d²) 为主扫，再残差抛光、`degree_blend` 融合 |
| 目的 | 业务原版形态 | 不改 `interp_sg_cressman` 源码，封装使结果接近 GressMan |

差异在影响半径几何与权重、创新路径。强降水梯度区对半径与权重更敏感。

---

## 3. 应用场景

### 3.1 原版优点与适用

**优点**

- 与历史业务产品、既有检验基线口径一致；
- 度制 GressMan + 度制半拉格朗日外推链条完整、可复现；
- 作为对照基准时结果稳定，便于验证资料与匹配链路。

**适用**

- 业务发布、归档、基线检验；
- 需要与既往原版产品严格对齐的场景。

### 3.2 现版优点与适用

**优点**

- 插值与外推接到项目子模块（`interp_sg_cressman`、`Extrapolation`），便于工程化维护；
- 不改项目核源码即可做再处理标定（如 `degree_blend`、`r_km_scale`）；

**适用**

- 子模块接入与核替换试验；
- 在保持频率匹配主逻辑不变的前提下推进工程化落地。

### 3.3 选用建议（按优点）

| 更看重 | 建议 |
|--------|------|
| 业务口径一致、可复现归档 | 原版 |
| 项目子模块接入、工程化扩展 | 现版 |

运行入口为 `cli/frequency_matching_rain24_cli.py`，用 `match_mode` 选择路线：

**原版**（`match_mode=original`）

```bash
python -m cli
python -m cli match_mode=original config=resource/conf.ini
python -m frequency_matching_rain24 match_mode=original config=resource/conf.ini
```

**现版**（`match_mode=aligned`）

```bash
python -m cli match_mode=aligned config=resource/conf_aligned.ini
python -m frequency_matching_rain24 match_mode=aligned config=resource/conf_aligned.ini
```

- `conf.ini` → `resource/ecmwf.json`；`conf_aligned.ini` → `resource/ecmwf_aligned.json`
- CLI `_process` 三段：读入 → `OpticalFlowSliceCorrectPlugin` / `CressmanFreqMatchGridPlugin`.process → 写出；`match_mode` 只换 Cressman/外推
- 输出目录须分开，避免互相覆盖

## 产品对比图

左：原版；中：现版；右：现版−原版。完整加载与重绘见 `nbs/原版与现版产品对比图.ipynb`。

起报 `2026081300`，时效 036 / 072 / 120：

![2026081300.036](../resource/output/pngs/original_vs_aligned/2026081300/2026081300.036.png)

![2026081300.072](../resource/output/pngs/original_vs_aligned/2026081300/2026081300.072.png)

![2026081300.120](../resource/output/pngs/original_vs_aligned/2026081300/2026081300.120.png)
