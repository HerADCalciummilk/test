# neighbourhood_probability_processing

## 算法概述

`neighbourhood_probability_processing` 用于集合/概率预报中的邻域处理和概率生成。原始算法迁移自 Met Office IMPROVER 的 `nbhood` 相关模块，并适配 `meteva_base` 的 `grid_data` 六维数据结构，同时支持 `numpy.ndarray` 输入。

本次整理的核心能力包括：

- 对二维空间场执行邻域平均或邻域求和，支持 `square` 和 `circular` 两类邻域。
- 在圆形邻域内生成百分位结果。
- 支持按时效配置可变邻域半径。
- 支持外部掩码、陆海分区、地形带分层掩码及权重折叠。
- 支持角度场复数化处理后再做邻域统计。

## 算法分类

- 分类：`07probability`
- 分类依据：算法主要用于集合/概率预报后处理，包括邻域概率、百分位生成和掩码分层概率处理。

## 主要文件

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/nbhood.py` | 邻域概率、邻域百分位、圆形核和基础邻域处理 |
| 核心源码 | `src/use_nbhood.py` | 按分层掩码迭代执行邻域处理，并支持权重折叠 |
| 辅助源码 | `src/utils/` | 可变半径、角度复数转换、halo 裁剪、网格与重网格等内部工具 |
| 辅助源码 | `utils/base_plugin.py` | 插件基类 |
| 辅助源码 | `utils/utils.py` | `meb.checkout_griddata` 与输出重组装 |
| CLI | `cli/ens_nbhood.py` | 普通邻域概率和百分位生成调度脚本 |
| CLI | `cli/ens_nbhood_iterate_with_mask.py` | 按分层掩码迭代邻域处理调度脚本 |
| CLI | `cli/ens_nbhood_land_and_sea.py` | 陆海/地形带分区邻域处理调度脚本 |
| CLI | `cli/preprocess_test_data.py` | 官方投影样例预处理（threshold → level） |
| 文档 | `docs/nbhood.md` | 邻域概率和百分位算法说明 |
| 文档 | `docs/use_nbhood.md` | 掩码分层邻域处理说明 |
| 测试 | `test/` | 核心邻域处理和掩码邻域处理测试 |
| 数据 | `test_data/` | 官方样例和对照 `nc` 数据 |

## 输入输出

### 普通邻域概率

输入：

- `data`：待处理概率或阈值场，最后两维为空间维。
- `radii`：邻域半径，单位通常为 `m`。
- `mask`：外部掩码，可选。
- `grid_spacing`：网格间距，`numpy` 输入时必填，`xarray` 输入通常自动推断。

输出：

- 邻域平均概率或邻域和，输出结构与输入保持一致。

### 邻域百分位

输入：

- `data`：待处理集合或概率场。
- `radii`：邻域半径。
- `percentiles`：目标百分位列表。

输出：

- 百分位结果。`numpy` 输入时首轴为百分位维；`xarray` 标准六维输入时会将百分位信息映射到 `member` 维并保留附加坐标。

### 分层掩码邻域处理

输入：

- `data`：主输入场。
- `mask`：包含分层维的掩码，例如 `topographic_zone`。
- `collapse_weights`：分层折叠权重，可选。

输出：

- 不提供权重时，输出包含分层结果；`xarray` 标准六维场景下分层维会与 `member` 联合映射。
- 提供权重时，沿分层维折叠回原空间结构。

## 当前整理状态

当前阶段为原始算法整理至中间目录，尚未补充到正式算法仓库目录。

已完成：

- 自 `D:\workspace\improver\nbhood` 增量同步 src/（含 src/utils/）、utils/、cli/、test/、docs/、nbs/（2026-08-24）。
- 导入路径已统一为中间目录模块名 `neighbourhood_probability_processing`。
- 核心与 CLI 改用 `meb.checkout_griddata()`；补齐 `cli/preprocess_test_data.py`；已删除原目录没有的 `cli/io.py` 与包内脚手架。
- 未同步 `test_data/`（约 10.89MB、84 文件）；CLI / 预处理缺样例时中文提示后退出。
- 原目录 pytest：53 passed；中间目录：42 passed / 11 skipped（缺 test_data 时官方对照 skip）。

待处理：

- 补充至 `NIMM/07probability/` 时需将导入路径调整为仓库正式包路径。
- `test_data` 体量较大，正式入库前建议筛选必要小样例。

