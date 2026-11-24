# mait_3h — 程序说明

**3 小时**多模式降水 **TS 动态加权**集成（`multi_rain_mait03_blending`）：历史场算多阈值 TS → 与历史 beta 平滑得权重 → 加权融合当前场 → 频率匹配订正站点 → Cressman 上格点。输出 Micaps3 / Micaps4。

$$
w_n=(1-\alpha)\,s^{\mathrm{before}}_n+\alpha\,s^{\mathrm{now}}_n,\qquad
V^{\mathrm{sta}}=\mathrm{FM}\!\left(\sum_n w_n V^{\mathrm{now}}_n\right)
$$

默认 \(\alpha=0.1\)；权重按评分从大到小，第 6 名及以后置 0，再按当前场是否到齐归一。时效 **3–252 h，步长 3**。

**算法应用**：业务上用于国家级 / 省级短中期 **3 小时累积降水** 多模式集成（EC、CMA、区域模式等 Micaps3 站点预报 + 实况）。输出订正站点场（`.m3`）与格点场（`.m4`/`.nc`），供检验、下游订正或产品制作。历史 beta 使权重随近期技巧缓慢更新，避免单日评分抖动。

---

## 1. 算法原理

目标是在保留各模式相对技巧的同时，把多模式 3 小时降水合成一张站点场，再客观分析到网格。

1. **资料与可用性**  
   读历史模式站点、当前模式站点、实况站点、当前背景格点。`DataFlgProcess` 统计历史/当前到齐标记；历史全缺或当前全缺则该时效退出。

2. **分区 TS 动态权重**  
   全区分成子区（默认整域一块，训练窗外扩 `area_scale=0.5`）。对量级 \(0.1,10,25,50\,\mathrm{mm}\)（权重 \(0.05,0.1,0.35,0.5\)）：  
   - \(s^{\mathrm{now}}\propto \mathrm{TS}(\hat{V}^{\mathrm{his}},V^{\mathrm{obs}})/(\overline{\mathrm{TS}}_{\mathrm{cross}}+S)\)，\(S=10^5\)；  
   - 与历史 beta：\(s^{\mathrm{last}}=(1-\alpha)s^{\mathrm{before}}+\alpha s^{\mathrm{now}}\)。  
   再按 \(s^{\mathrm{last}}\) 排序，仅保留前 5 个模式，缺测模式权重为 0 后归一。

3. **频率匹配（站点）**  
   用保留模式的当前场与融合场建立分位映射（实况级 0.1–250 mm），分段线性订正融合站点；\(V<0.1\) 置 0。分位排序前有 \(U(0,10^{-3})\) 扰动（原算法即如此）。

4. **Cressman 上格点**  
   陆地区外每隔 5 点取背景格点当伪站，与订正站混合；影响半径 \(8,6,4,2\times\Delta\lambda\)，9 点平滑 10 次。再用站点↔格点做一次频率匹配。时效 \(\ge 108\,\mathrm{h}\) 乘 0.8，并钳制极值。

5. **写出**  
   站点 Micaps3；格点 Micaps4。可选 `is_interp` 再双线性裁到 `clip_coords`。

---

## 2. 算法实现方式

| 层级 | 路径 | 说明 |
|------|------|------|
| 调度 | `src/mait_3h.py` | `process` / `RunProcess`：读数 → TS → FM → Cressman → 写盘 |
| 算法插件 | `src/mait_3_plugin.py` | `AnalysisTsWeightProcess`、`StationDataInterp2GridDataProcess`、`DataFlgProcess` |
| 读数与写出 | `src/mait_3_plugin_util.py` | para/background/时间/beta/mask、Micaps3/4 |
| 数值核 | `src/utils/util_new.py` | `get_ts`、`MetevaFrequencyMatch`、`MetevaSpatialAnalisis` |
| 多进程 | `utils/multipro_plugin.py` | `SimpleParallelTool`（与 mait01/24 相同，按起报分发） |
| 配置 | `src/utils/util_env.py` | 读 `resource/mait_3.ini` |
| CLI | `cli/__main__.py` | argparse → `process` |

**主流程（`RunProcess._process_single`）**

1. `_prepare` 日志与站点表；`_analysis_para_ini` 解析模式/实况/输出路径。  
2. `_read_history_source_micaps3`、`_read_now_source_micaps3_micaps4` 读历史/当前/实况/背景。  
3. `DataFlgProcess`：历史或当前全缺则 return。  
4. 读历史 beta → `AnalysisTsWeightProcess` 得站点场与当期评分 → `write_beta`、写 Micaps3。  
5. `read_grid_mask` → `StationDataInterp2GridDataProcess` → 写 Micaps4。

多个起报由 `is_multi` + `SimpleParallelTool` 并行（每个 worker 串行跑该起报的全部时效）。`is_multi=false` 时按起报串行。

**调用形态**

- 产品：`from mait_3h import process` / `python -m cli` / `python src/mait_3h.py`  
- 插件：`AnalysisTsWeightProcess(...).process()`、`StationDataInterp2GridDataProcess(...).process()`

入参为起报时刻与路径配置；算法核操作 meteva 站点 DataFrame 与本包 `GridData` / `StationDataArray`。

---

## 3. 参数说明

### 3.1 运行参数（`mait_3.ini` / CLI 共用）

| 参数 | 类型 | 含义 |
|------|------|------|
| `time_inputs` | `list[str]` | UTC 起报列表，写 `YYYYMMDD0000` / `YYYYMMDD1200` 即出该 00/12Z；默认当前时刻 |
| `time_input` | `str` | 单个起报（兼容旧写法） |
| `predict_valid_list` | `list[int]` | 预报时效展开（小时）；显式传入则按列表；空则 **3–252，步长 3** |
| `para_path` | `path` | 模式/实况/输出路径；默认 `resource/para_3.ini` |
| `background_path` | `path` | 背景格点 Micaps4 路径；默认 `resource/para_3_background.ini` |
| `beta_path` | `str` | 历史/当期权重文件；默认 `beta_3h/YYYYMMDDHH/%02d_%02d_TTT.info` |
| `is_obs_bjt` | `bool` | 实况按北京时（+8 h）；默认 true |
| `is_interp` | `bool` | 写出前是否双线性裁剪；默认 false |
| `is_multi` | `bool` | 多个起报是否多进程；默认 false |
| `clip_coords` | `list[float]` | `lon0,lon1,lat0,lat1,dlon,dlat`；默认 `70,140,0,60,0.1,0.1` |
| `pro_count` | `int` | 起报并行进程数（仅 `is_multi`）；默认 3 |

### 3.2 算法内部常量（代码内，非 ini）

| 参数 | 类型 | 含义 |
|------|------|------|
| `area_scale` | `float` | 训练窗外扩（相对子区边长）；默认 0.5 |
| `predict_type` | `int` | 3 小时累积降水；默认 3 |
| `rain_limit` / 权重 | `list[float]` | TS 量级与合成权重；默认 0.1/10/25/50；0.05/0.1/0.35/0.5 |
| \(\alpha\) / \(S\) | `float` | beta 平滑；交叉 TS 平滑；默认 0.1 / \(10^5\) |
| 站点 FM 级 | `list[float]` | 站点频率匹配；默认 0.1–250 mm（18 级） |
| 格点 FM 级 | `list[float]` | 格点频率匹配；默认 0.01–250 mm（19 级） |
| Cressman 半径 | `list[float]` | 逐步订正；掩膜外每隔 5 点取背景作伪站；默认 \(8,6,4,2\times\Delta\lambda\) |
| 平滑 | `int` | Cressman 之后；默认 9 点 × 10 次 |
| 长时效衰减 | `float` | 格点后处理；\(\ge108\,\mathrm{h}\) 乘 0.8 |
| 写出 | `str` | 前缀 `staoutputPath`；`.m3` / `.m4`（可选 `.nc`）；`is_interp` 时可再裁到 `clip_coords` |

### 3.3 路径（`mait_3.ini`）

| 参数 | 类型 | 含义 |
|------|------|------|
| `log_file` | `str` | 日志模板；默认 `log/YYYYMMDD.txt` |
| `station_info` | `path` | 站点表；默认 `resource/station_info.txt` |
| `mask_dat` | `path` | 陆地掩膜（境外填背景伪站）；默认 `resource/mask010.dat` |

默认读 `para_3.ini` / `para_3_background.ini`（Linux 挂载路径）。Windows 本机用 UNC 时，把 `mait_3.ini` 改成 `para_3_local.ini` / `para_3_background_local.ini`，或 CLI `--para-path` / `--background-path`。  
`para_3*.ini`：`modelNum`、各模式 **站点** Micaps3、`fact`（R03 实况）、`staoutputPath`。默认模式键：`ecModel`、`ncepModel`、`grapesgfsModel`、`japanModel`、`shanghaiModel`、`grapes3kmModel`、`beijingModel`、`guangzhouModel`。  
`para_3_background*.ini`：与模式键同名的 **格点** Micaps4 背景模板；缺键时回退为同模式 Micaps3 改 `.m4`。站点表 / 陆地掩膜见上表 `station_info`、`mask_dat`。未在 CLI 给出的项回落 `resource/mait_3.ini` / `conf.ini`。

---

## 4. 运行示例

**环境**：项目根 `multi_rain_mait03_blending/`；依赖 `numpy` / `pandas` / `meteva` / `meteva_base`；共享 `utils.base_plugin`。无 `scripts/`。

**步骤**

1. 默认读 `resource/para_3.ini` 与 `para_3_background.ini`；本机 Windows 改 `mait_3.ini` 指向 `*_local.ini` 或用 `--para-path`。  
2. 确认 `resource/station_info.txt`、`resource/mask010.dat`；需要历史权重时对齐 `beta_3h/`。  
3. 任选 CLI / 模块 / 直跑。  
4. 查看 `staoutputPath` 下对应时效的 `.m3` / `.m4`。

**模块调用**

```python
from mait_3h import process
process(time_inputs=["202608200000"], is_multi=False)
process(time_inputs=["202608200000", "202608201200"], is_multi=True, pro_count=4)
process(time_input="202608200000", predict_valid_list=[3, 6, 9],
        para_path="resource/para_3.ini")
```

**直跑**

```bash
python src/mait_3h.py
```

（写 UTC 起报 `YYYYMMDD0000` / `YYYYMMDD1200`，内部再转作业时刻；未传项读 ini。）

---

### CLI

在本包根执行。每个起报内按时效串行；`pro_count>1` 时按起报并行。

区域逐 3 小时回算示例（核对产物：`staoutputPath` 下 `.m3` / `.m4`，范围与 `clip_coords` 一致）：

```bash
python -m cli time_inputs=2025070200,2025070212 \
  predict_valid_list=3,6,9,12,15,18,21,24 \
  para_path=resource/para_3.ini \
  background_path=resource/para_3_background.ini \
  clip_coords=70,140,0,60,0.1,0.1 \
  pro_count=2
```

其它常用写法：

```bash
python -m cli time_inputs=202608200000
python -m cli time_inputs=202608200000,202608201200 pro_count=4
python -m cli time_inputs=202608200000 predict_valid_list=3,6,9
python -m cli time_inputs=202608200000 is_interp=true clip_coords=70,140,0,60,0.1,0.1
```

| 参数 | 说明 |
|------|------|
| `time_inputs` | UTC 起报，如 `202608200000,202608201200` |
| `predict_valid_list` | 时效列表；省略则 3–252 步长 3 |
| `para_path` | 模式/实况 ini（站点） |
| `background_path` | 背景格点 Micaps4 ini |
| `beta_path` | beta 路径模板 |
| `is_obs_bjt` | 实况是否北京时 |
| `is_interp` | 是否按 clip 再插值 |
| `clip_coords` | 输出裁剪六元组 |
| `pro_count` | 起报并行进程数 |

省略项从 `resource/conf.ini` / `mait_3.ini` 读取。若日志出现历史或当前全缺，检查对应日目录与 `VVV` 时效文件名。

---

## 6. 示例：合成场上的 TS 与频率匹配

不依赖业务路径：构造「实况 / 历史模式 / 当前模式」站点列，演示 `get_ts` 与分位映射订正（对应 `src/utils/util_new.py`）。完整集成需 `process(...)` 与 `para_3*.ini` 中的 Micaps 路径。

```python
from utils.util_new import get_ts, MetevaFrequencyMatch, data0_str
# 合成列 → get_ts(his, obs, 0.1, 20.0)
#         → get_model_level / correct_model_data
```

Notebook 中同节可直接运行。
