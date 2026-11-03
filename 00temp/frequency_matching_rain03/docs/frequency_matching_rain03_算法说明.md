# frequency_matching_rain03 — 程序说明

**逐 3 小时**单模式降水 **频率匹配**订正（`frequency_matching_rain03`）：由历史同期场按 TS+Bias 选相似个例 → 建分位映射订正当前预报 →（仅时效 \(\le 0\) 时）光流反演风场并半拉格朗日平流 → Cressman 上格点后再做一次格点频率匹配。输出 Micaps3 / Micaps4 / NC。由 `QPFFrequencyMatch_Rain03` 迁入 NIMM 布局。

$$
V' = f_k + \frac{f_{k+1}-f_k}{m_{k+1}-m_k}\,(V-m_k),\qquad
s=\mathrm{TS}\Bigl(1+\frac{0.2}{|9(\mathrm{Bias}-1)|+1}\Bigr)
$$

其中 \((m_k,f_k)\) 为模式/实况同频级对；\(\mathrm{TS}=H/(H+M+F+0.001)\)，\(\mathrm{Bias}=(H+F+0.001)/(H+M+0.001)\)。时效 **3–252 h，步长 3**；实况为 R03 / 3 小时累积。分位排序前有 \(U(0,10^{-3})\) 扰动（原算法即如此）。

**算法应用**：业务上用于单模式（如 ECMWF、GRAPES 3 km）**3 小时累积降水**统计订正。输入模式格点 Micaps4 与国家站 R03 实况 Micaps3，输出订正站点场（`.m3`）与格点场（`.m4`/`.nc`），供检验、短中期产品和下游融合。历史窗覆盖近年同期，使订正随气候与模式偏差缓慢更新。

---

## 1. 算法原理

目标是用「与当前预报最像」的历史模式–实况对，把当前场的量级分布拉到与实况同频，再客观分析到网格。

1. **资料与任务展开**  
   读 `path.json` 模式/实况/输出模板、`config.json` 网格、`sta.info` 站点、陆地掩膜。对每个起报时刻回溯 0–24 h（再减 8 h，对齐北京时），时效 3–252 h、步长 3。路径用 `meb.get_path` 展开；无后缀则试 `.m4`/`.nc`。读写格点/站点走 `meteva_base`。输出 `.m3`+`.m4` 已存在或模式输入缺失则跳过。

2. **历史相似个例**  
   回溯 4 年：当年取 \([t-15\,\mathrm{d},\,t-1\,\mathrm{d}]\)，往年取 \([t-365j-15\,\mathrm{d},\,t-365j+15\,\mathrm{d}]\)。历史模式 9 点平滑 30 次，掩膜后粗网格（\(5\Delta\lambda\)）上算多阈值 TS+Bias（默认 25、50 mm）。\(H+M+F\le 10\) 时该阈值记为无效。按评分从高到低累加，超过 \(2.4\) 后截断；频率匹配至少用 \(\max(\lfloor N/2\rfloor,\,n_{\mathrm{cut}})\) 个个例。

3. **频率匹配（站点/格点）**  
   相似个例的模式插值到训练区站点，与对应实况建分位映射（级 0.1–500 mm，可丢两端各 5 个样本）。对当前平滑场分段线性订正；级对不足 2 个则退回当前原始场。\(V<0.01\) 置 0。

4. **光流平流（仅时效 \(\le 0\)）**  
   当前默认时效均 \(\ge 3\)，此支不执行。短时效时：相似个例实况 Cressman 上格点后再 FM，用 5° 窗光流反演 \(u,v\)，按订正场强度缩放，半拉格朗日平流 1 步。

5. **Cressman 上格点**  
   订正站 + 掩膜外每 5 点抽的背景伪站；半径 \(8,6,4,2\times\Delta\lambda\)，9 点平滑 10 次。格点回插到站后再做一次频率匹配（级 0.01–250 mm）。写出 `.m3` / `.m4` / `.nc`。

---

## 2. 算法实现方式

| 层级 | 路径 | 说明 |
|------|------|------|
| 调度 | `src/runner.py` | `process` / `main`：读数 → 相似 → FM →（可选 OF）→ Cressman → 写盘 |
| 频率匹配 | `src/proc/frequency_match.py` | `FrequencyMatch`：分位映射与分段订正 |
| 相似 | `src/proc/ensemble.py` | `Ensemble`：相关 / RMSE / TS+Bias |
| 光流 / 平流 | `src/proc/optical_flow.py`、`rain_extrapolation.py` | 短时效风场与半拉格朗日 |
| Cressman | `src/proc/spatial_analysis.py` | `SpatialAnalisis.gress_man_interpolation_for_rain` |
| 数值替代 | `src/proc/alglib.py` | Pearson、稀疏 LSQR（光流） |
| 配置 | `src/utils/util_env.py` | 读 `resource/qpf_fm.ini` |
| 路径 / I/O | `src/utils/io_meb.py` | `meb.get_path`、后缀回退、Micaps 读写适配 |
| CLI | `cli/__main__.py` | argparse → `process` |

**主流程（`main` 单时效）**

1. `_load_path_configs` / `_load_grid_config`；读站点与掩膜。  
2. 未设 `QPF_DISABLE_LEADTIME_MP` 时，按时效切子进程并行（`QPF_LEADTIME_WORKERS`，默认最多 8）。  
3. 用 `meb.get_path` 展开模式路径（无后缀则试 `.m4`/`.nc`），`meb.read_griddata_from_micaps4` 读入后裁到大区网格。  
4. 扫历史窗，成对读模式格点与实况站点（`.m3`）；平滑后 `get_similarity_index_by_ts_and_bias`。  
5. `get_used_model_level_and_extend` + `correct_model_data` 订正当前场；插到站点写 `.m3`。  
6. 伪站 + Cressman + 格点 FM → `.m4` / `.nc`。

**调用形态**

- 产品：`from runner import process` / `python -m cli` / `python src/runner.py`  
- 算法核：`FrequencyMatch.correct_model_data(...)`、`Ensemble.get_similarity_index_by_ts_and_bias(...)`

入参为模式键与起报时刻；核操作本包 `GridData` / `ScatterData`。路径与 Micaps 读写走 `meteva_base`（未安装则报错提示 `pip install meteva_base`）。

---

## 3. 算法参数说明

### 3.1 运行参数（CLI / `process`）

| 参数 | CLI | 默认 | 含义 |
|------|-----|------|------|
| `data_key` | 位置参数 / `--data-key` | `path.json` 的 `default` | 模式键（如 `ecmwf`） |
| `run_times` | 1 或 2 个 `YYYYMMDDHH` / `YYYYMMDDHHMM` / `--start` `--end` | 当前时刻 | 单时次，或闭区间按小时展开；10 位按整点 |

### 3.2 算法内部常量（代码内，非 ini）

| 量 | 取值 | 含义 |
|----|------|------|
| 时效 | 3–252，步长 3 | 预报时效（小时） |
| 回溯循环 | 0–24 h，再 \(-8\) h | 起报对齐北京时 |
| 历史窗 | 4 年 × ±15 天 | 当年不含当日 |
| 平滑 | 9 点 × 30（历史）；×10（Cressman 后） | 削弱噪声 |
| `similar_level` | 25、50 mm | TS+Bias 阈值 |
| 相似截断 | 累加评分 \(>2.4\) | 再 \(\min(20,n)\) / \(\max(N/2,n)\) |
| 站点 FM 级 | 0.1–500 mm（19 级），两端可丢 5 | 相似个例映射 |
| 格点 FM 级 | 0.01–250 mm（19 级） | Cressman 后再订正 |
| Cressman 半径 | \(8,6,4,2\times\Delta\lambda\) | 逐步订正 |
| 光流窗 | \(5^\circ\times 5^\circ\) | 仅 `predict_valid<=0` |

### 3.3 路径（`qpf_fm.ini` / JSON）

| 键 / 文件 | 默认 | 含义 |
|-----------|------|------|
| `log_file` | `log/YYYYMMDD.txt` | 日志模板 |
| `config_json` | `resource/config.json` | 网格：`lon/lat` 起止、`dlon/dlat`、`expand` |
| `path_json` | `resource/path.json` | 各模式 `model_template` / `fact_template` / `output_template` |
| `station_info` | `resource/sta.info` | 站点表 |
| `mask_file` | `resource/mask010.dat` | 陆地掩膜；`dlon` 为 0.01/0.05 时改用 `mask001`/`mask005` |

路径占位符：`YYYY`/`MM`/`DD`/`HH`/`VVV`（三位时效）。展开时先把 `VVV` 换成 `TTT`，再 `meb.get_path(tpl, time, dtime)`。无后缀模板会依次尝试 `.m4` / `.nc` / `.m3`。格点用 `read_griddata_from_micaps4` / `read_griddata_from_nc` 与对应写出；站点用 `read_stadata_from_micaps3` / `write_stadata_to_micaps3`。`sta.info` 仍按本包站点表格式读取。未在 CLI 给出的项回落 ini / `path.json`。未安装 `meteva_base` 时直接报错。

环境变量：`QPF_LEADTIME_WORKERS`（时效子进程数）；`QPF_DISABLE_LEADTIME_MP=1` 关闭并行（子进程内部自动设置）。

---

## 4. 算法使用说明

**环境**：项目根 `frequency_matching_rain03/`；依赖 `numpy` / `scipy` / `meteva_base`。无 `scripts/`。

**步骤**

1. 在 `resource/path.json` 填写模式、实况、输出模板。  
2. 按需要改 `resource/config.json` 网格；确认 `sta.info` 与 `mask*.dat`。  
3. 任选 CLI / 模块 / 直跑。  
4. 查看 `output_template` 展开路径下的 `.m3` / `.m4` / `.nc`。

**模块调用**

```python
from runner import process
process(data_key="ecmwf", run_times=["202605220800"])
process(data_key="ecmwf", run_times=["202605220000", "202605221200"])
```

**直跑**

```bash
python src/runner.py ecmwf 202605220800
```

（无参则用 `path.json` 的 `default` 与当前时刻。）

---

## 5. CLI 调用说明

在仓库根执行：

```bash
python -m cli --help
python -m cli ecmwf 202605220800
python -m cli ecmwf 202605220000 202605221200
python -m cli --data-key ecmwf --start 202605220800
python -m cli --data-key ecmwf --start 202605220000 --end 202605221200
```

| 参数 | 说明 |
|------|------|
| 位置 `ARG` | 兼容旧写法：模式键 + 起报 `YYYYMMDDHH` 或 `YYYYMMDDHHMM` |
| `--data-key` | 模式键，对应 `path.json` 的 `configs` |
| `--start` | 起报起始；与 `--end` 组成闭区间（步长 1 小时） |
| `--end` | 结束时刻（需同时给 `--start`） |

省略模式键时用 `path.json` 的 `default`；省略时刻用当前系统时间。

---

## 6. 示例：合成场上的相似评分与频率匹配

不依赖业务路径：构造两场降水，演示 `Ensemble.similarity_score_by_ts_and_bias` 与 `FrequencyMatch` 分位订正（对应 `src/proc/`）。完整订正需 `process(...)` 与 `path.json` 中的 Micaps 路径。

```python
from proc.ensemble import Ensemble
from proc.frequency_match import FrequencyMatch
# 合成 GridData → similarity_score_by_ts_and_bias
# 合成列 → get_model_level / correct_model_data
```

Notebook 中同节可直接运行。
