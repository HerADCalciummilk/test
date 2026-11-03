# multi_optimize_tp_24h 程序说明

24 小时降水频率匹配订正算法（0403 号版本）。

---

## 1. 概述

`multi_optimize_tp_24h` 针对数值模式输出的 **24 小时累积降水预报**，利用历史同期模式场与实况站点的统计关系，对当前预报进行 **空间结构订正** 与 **频率匹配订正**，生成订正后的站点（MICAPS3）和格点（MICAPS4/NC）产品。

核心思路：在历史样本中找到与当前模式场最相似的个例，借鉴其模式—实况偏差规律，结合光流位移和分位数频率匹配，改善模式降水的空间分布和量级分布。

---

## 2. 应用场景

| 场景 | 说明 |
|------|------|
| 中期降水订正 | 对 36～252 h 时效的 24 h 累积降水预报进行订正 |
| 多模式业务化 | 通过 plugin JSON 切换 ECMWF、CMA-MESO 等不同模式路径 |
| 实时/回算 | `rpt_list` 留空为实时；填写起报时间可批量回算 |
| 地方考核站部署 | 替换 `resource/sta.m3` 为地方站网模板 |

适用对象：已有模式 24 h 降水格点产品、站点 24 h 降水实况、以及足够长度历史样本的业务环境。

---

## 3. 算法原理

### 3.1 总体思路

对每个 **起报时间 + 预报时效** 组合，算法分三步：

1. **相似个例检索**：在历史模式场中，按 TS 类相似度指标找出与当前模式场空间分布最接近的样本。
2. **切片订正**（站点尺度）：将订正区域划分为若干子区域（切片），在每个切片内：
   - 用相似历史样本做 **频率匹配**，调整当前模式降水分布；
   - 时效 ≤ 60 h 时，进一步用 **光流法** 估计降水系统位移并做半拉格朗日平流订正。
3. **全域格点订正**：将各切片站点订正结果与模式背景场融合（克里金/格点插值），再对格点产品做 **频率匹配**，输出最终格点场。

### 3.2 相似度计算

模块：`src/cal_similarity.py`

- 在多个检验量级（默认 25 mm、50 mm）上，比较历史模式场与当前模式场的 TS 类得分；
- 各量级得分取平均，按得分降序排列历史样本索引；
- 累计相似度超过阈值（`sum_similar_threshold`）的样本用于后续订正。

### 3.3 光流订正

模块：`src/cal_optical_flow.py`、`src/cal_slice_tp.py`

- 取相似度最高的若干历史个例（最多 20 个）；
- 对每对历史模式—实况格点场估计光流矢量；
- 将光流叠加到当前模式场上，做半拉格朗日平流（仅 **dtime ≤ 60** 时启用）。

### 3.4 频率匹配

模块：`src/cal_frequency_match.py`

- 将模式与实况（或站点）降水按分位数等级（`fact_level` / `fact_level1`）建立映射；
- 对模式场各像素/站点做分段线性变换，使模式降水分布逼近实况分布；
- 切片阶段和最终格点阶段各执行一次频率匹配。

### 3.5 历史样本构造

- 以当前起报日期为基准，向前 **15 天**（`his_day`），并回溯 **3 年**（`his_year`）同期日历窗口；
- 逐日读取同时效的模式格点和对应时刻的站点实况；
- 模式与实况时间不一致时，按 `ipt_model` / `ipt_obs` 做 ±8 h 时区换算。

---

## 4. 算法实现流程

```
mainProcess(parafile)                         # src/correct_tp_24h.py
  └─ 按 rpt_list × [start_dtime, end_dtime] 多进程调度
       └─ correct_24H_TP(parafile, rpt, dtime)
            ├─ preLogical()          检查模式输入是否存在、输出是否覆盖
            ├─ read_his_ds()         加载历史模式格点 + 实况站点
            ├─ read_current_ds()     加载当前模式格点
            └─ mainProc()
                 ├─ cycle_correct_Slice()     逐切片：相似度 → 光流 → 频率匹配
                 ├─ _correct_current_TP_sta() 合并切片站点，写 MICAPS3
                 └─ _correct_current_TP_grd()  插值 + 频率匹配，写 MICAPS4/NC
```

### 4.1 主要源文件

| 文件 | 功能 |
|------|------|
| `src/correct_tp_24h.py` | **主程序**：流程、数据加载、切片循环、产品输出 |
| `src/cal_similarity.py` | **核心算法**：历史—当前模式相似度 |
| `src/cal_slice_tp.py` | **核心算法**：切片光流 + 频率匹配订正 |
| `src/cal_optical_flow.py` | **核心算法**：光流场 / 拉格朗日平流 |
| `src/cal_frequency_match.py` | **核心算法**：频率匹配（站点/格点） |
| `src/interpolation.py` | **核心算法**：Cressman / 双线性插值 |
| `src/utils/data_proc.py` | **工具**：格点/站点预处理、平滑、掩膜（`from utils.data_proc`） |
| `src/utils/data_save.py` | **工具**：MICAPS3/4/NC 写出 |
| `src/utils/config.py` | **工具**：算法内部常量参数 |
| `src/utils/verify.py` | **工具**：检验脚本（非主流水线） |
| `src/utils/logger.py` | **工具**：运行日志 |
| `src/utils/util_env.py` | **工具**：读取 `optimize_tp_24.ini`（`from utils.util_env`） |
| `00temp/utils/multipro_plugin.py` 等 | **共享**：并行 / 检验数据准备；根 `utils` 合并，无本地副本 |
| `cli/__main__.py` | 命令行入口 |

---

## 5. 关键参数说明

### 5.1 运行参数（`resource/optimize_tp_24.ini`）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `log_file` | `log/YYYYMMDD.txt` | 日志文件路径模板 |
| `station_info` | `resource/sta.m3` | 站点模板（MICAPS3） |
| `mask_nc` | `resource/mask010.nc` | 陆地掩码 |
| `default_plugin` | `resource/ecmwf.json` | 默认模式路径配置 |
| `rpt_list` | 空 | 起报时间：`空`=实时；`2025010100`=单个；`2025010100,2025010112`=范围 |
| `ipt_model` | `0` | 模式时间：`0` 国际时，`1` 北京时间 |
| `ipt_obs` | `1` | 实况时间：`0` 国际时，`1` 北京时间 |
| `ipt_type` | `m4` | 输入模式格式：`m4` 或 `nc` |
| `opt_type` | `m4` | 输出格点格式：`m4` 或 `nc` |
| `over_w` | `0` | 是否覆盖已有产品：`0` 跳过，`1` 覆盖 |
| `start_dtime` | `36` | 订正起始预报时效（h） |
| `end_dtime` | `252` | 订正结束预报时效（h，含） |
| `inter_dtime1` | `12` | ≤60 h 时效步长 |
| `inter_dtime2` | `12` | >60 h 时效步长 |
| `report_inter` | `12` | 起报时间间隔（h） |
| `res` | `0.1` | 输出分辨率（度） |
| `clip_coords` | `70,140,0,60` | 订正范围：起始/结束经度、纬度 |
| `pool_num` | `8` | 并行进程数 |

### 5.2 模式路径（plugin JSON，如 `resource/ecmwf.json`）

| 字段 | 说明 |
|------|------|
| `tp_model` | 模式 24 h 降水路径，占位符 `{rpt}`、`{dtime}` |
| `tp_obs` | 实况 24 h 降水路径（MICAPS3 站点） |
| `correct_tp_outpath` | 订正结果输出路径前缀（程序自动追加 `.m3` / `.m4`） |

路径示例（ECMWF）：

```json
{
  "tp_model": "/data/.../ecmwf/{rpt:%Y%m%d}/{rpt:%Y%m%d%H}.{dtime:03d}",
  "tp_obs": "/data/.../r24/sfc/{rpt:%y%m%d%H}.000",
  "correct_tp_outpath": "/data/.../output/ecmwf/{rpt:%Y%m%d%H}/{rpt:%Y%m%d%H}.{dtime:03d}"
}
```

起报 `2025010112`、时效 `036` 时，程序查找：

```text
{tp_model} → .../ecmwf/20250101/2025010112.036
{tp_obs}   → .../r24/sfc/25011212.000  （实况时间含 ipt 时区换算）
```

### 5.3 算法参数（`src/utils/config.py`，一般无需修改）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `expansion` | `1.0` | 切片外扩范围（度） |
| `inter_dis` | `5` | 背景场抽稀间隔（格点数） |
| `smooth_num` | `30` | 9 点平滑迭代次数 |
| `sum_similar_threshold` | `2.4` | 相似样本累计得分阈值 |
| `his_day` | `15` | 历史样本日历窗口（天） |
| `his_year` | `3` | 历史样本回溯年数 |
| `fact_level` | 0.1～500 mm 等级 | 切片频率匹配分级 |
| `fact_level1` | 0.01～250 mm 等级 | 格点频率匹配分级 |
| `similar_level` | `[25.0, 50.0]` | 相似度检验量级（mm） |

---

## 6. 输入与输出

### 6.1 输入

| 类型 | 格式 | 来源 |
|------|------|------|
| 模式 24 h 降水 | MICAPS4 / NC | `tp_model` 路径 |
| 站点 24 h 降水实况 | MICAPS3（`.000`） | `tp_obs` 路径 |
| 站点模板 | MICAPS3 | `resource/sta.m3` |
| 陆地掩码 | NC | `resource/mask010.nc` |

### 6.2 输出

每个起报时间、每个预报时效各生成：

| 产品 | 路径 | 格式 |
|------|------|------|
| 订正站点 | `{correct_tp_outpath}.m3` | MICAPS3 |
| 订正格点 | `{correct_tp_outpath}.{opt_type}` | MICAPS4 或 NC |

---

## 7. 调用方法

### 7.1 环境要求

- Python 3.8+
- 依赖：`meteva`、`numpy`、`pandas`、`xarray`、`scipy` 等（见 `requirements-cli.txt`）

### 7.2 部署步骤

1. 修改 `resource/optimize_tp_24.ini` 运行参数（起报时间、时效范围、时区等）。
2. 修改 `resource/*.json` 数据路径，确保与磁盘实际目录一致。
3. 确认 `resource/sta.m3`、`resource/mask010.nc` 存在。
4. 在项目根目录执行命令。

### 7.3 命令行

```bash
# 使用 ini 中 default_plugin（默认 ECMWF）
python -m cli

# 指定模式 plugin
python -m cli --plugin=resource/ecmwf.json

# 切换其他模式
python -m cli --plugin=resource/CMA_MESO.json
```

**起报时间** 不在命令行传入，在 `optimize_tp_24.ini` 的 `rpt_list` 中配置：

```ini
# 实时
rpt_list=

# 回算单个起报
rpt_list=2025010100

# 回算起报范围（从结束到开始，按 report_inter 递减）
rpt_list=2025010100,2025010112
```

### 7.4 运行逻辑摘要

1. 读取 ini 与 plugin，确定起报时次、时效列表、数据路径。
2. 对每个 `(起报, 时效)` 组合启动子进程。
3. 子进程检查模式输入文件是否存在；不存在则记录「当前数据缺失」并跳过。
4. 存在则执行订正，写出 `.m3` 和格点产品。

---

## 8. 常见问题

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 日志「当前数据缺失」 | `tp_model` 路径模板与磁盘不一致 | 核对实际文件路径，修正 plugin JSON |
| 日志「历史数据缺失」 | 历史样本不足 | 检查历史模式/实况是否齐全 |
| 日志「本地已存在降水订正产品」 | 输出已存在且 `over_w=0` | 设 `over_w=1` 或删除旧产品 |
| 全部任务跳过、无输出 | 输入路径错误或挂载未就绪 | `ls` 验证一个具体文件是否存在 |
| 订正区域异常 | `clip_coords` 或 `sta.m3` 不匹配 | 检查 ini 四至与站网范围 |

---

## 9. 目录结构

```
multi_optimize_tp_24h/
├── cli/          # 命令行入口 (python -m cli)
├── docs/         # 程序说明文档
├── nbs/          # Jupyter 说明笔记本（与 docs 内容一致）
├── resource/     # 配置文件、站点模板、掩码、plugin
├── src/          # 核心算法
├── test/         # 测试
└── utils/        # 配置读取、日志
```
