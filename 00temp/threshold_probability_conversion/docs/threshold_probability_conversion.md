# threshold_probability_conversion

## 算法概述

`threshold_probability_conversion` 将诊断场（如气温、降水）转为「相对某个阈值是否成立」的 0～1 场。硬阈值时每个格点为 0 或 1；fuzzy 时在阈值附近做线性过渡。原始算法迁移自 Met Office IMPROVER 的 `improver.threshold.Threshold`，并适配 `meteva_base` 六维网格（阈值写入 `level`），同时支持 `numpy.ndarray` 输入。

核心能力包括：

- 硬阈值与 fuzzy 线性隶属（多阈值沿 `level` 堆叠）。
- 可选阈值单位换算、`fill_masked` 比较前填充。
- 可选 `collapse_coord` 对 `member` / `time` 求平均得到集合或时段概率。
- 可选 `vicinity` 方形邻域最大值（可与海陆掩码联用；多半径返回 Dataset）。

## 算法分类

- 分类：`07probability`
- 分类依据：算法用于集合/概率预报前的阈值化与概率场生成。

## 主要文件

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/threshold.py` | `Threshold` 主插件 |
| 辅助源码 | `src/utils/` | 比较符、线性重标定、格距与 vicinity |
| 辅助源码 | `utils/base_plugin.py` | 插件基类 |
| CLI | `cli/prb_threshold.py` | 阈值概率转换调度脚本 |
| CLI | `cli/preprocess_test_data.py` | 官方样例预处理（Iris/投影 → meb） |
| 文档 | `docs/threshold.md` | 算法与 CLI 参数说明 |
| 测试 | `test/` | 合成单测与官方 KGO 对照 |
| 数据 | `test_data/` | 官方样例和对照 `nc` 数据 |

## 输入输出

输入：

- `xarray.DataArray`：meb 六维诊断场，`level` 长度为 1。
- `numpy.ndarray`：任意形状；可选 `MaskedArray`。

输出：

- meb 输入：六维概率场，`level` 为阈值（原场单位），`units="1"`；多半径 `vicinity` 时为 `xr.Dataset`。
- ndarray 输入：形状 `(n_threshold, *input_shape)`。

## 当前整理状态

当前阶段为原始算法整理至中间目录，尚未补充到正式算法仓库目录。

已完成：

- 自 `D:\workspace\improver\threshold` 同步 `src/`、`utils/`、`cli/`、`test/`、`docs/`、`nbs/`（2026-08-24）。
- 导入路径已统一为中间目录模块名 `threshold_probability_conversion`。
- 未同步 `test_data/`（约 5.88MB、32 文件）；CLI / 预处理缺样例时中文提示后退出。
- 原目录 pytest：41 passed；中间目录：27 passed / 14 skipped（缺 test_data 时官方对照 skip）。
- 包根目录可用子命令入口：`python -m cli threshold`（无参列出用法）。

待处理：

- 补充至 `NIMM/07probability/` 时需将导入路径调整为仓库正式包路径。
- `test_data` 正式入库前建议筛选必要小样例。
