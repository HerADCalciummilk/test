# multi_wind_fft_blending

## 算法概述

`multi_wind_fft_blending` 用于多风场特征匹配融合。算法基于 FFT 谱方法与迭代优化理论，估计主风场与一个或多个辅助风场之间的二维位移场，再按位移场对主风场进行平流调整，实现空间特征对齐后的融合。

该算法适用于：

- 多源风场空间特征对齐。
- UV 矢量风融合。
- 集合预报中多个辅助风场的特征匹配融合。
- 台风、锋面等强空间特征的位移调整。

## 算法分类

- 分类：`05blending`
- 分类依据：算法面向多个风场或多个预报成员的融合处理，通过频域特征匹配和位移平流生成融合结果。

## 主要文件

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/fft_merge.py` | `FFTMergePlugin` 核心算法 |
| 执行入口 | `src/main.py` | `process(..., is_multi=..., pro_count=...)`；命令行可直接运行 |
| CLI入口 | `cli/__main__.py` | `python -m cli` → `src/main.py` |
| 运行配置 | `resource/fft_merge.ini` | 未显式传入的参数先读此文件，再没有则用代码预设 |
| 共享多进程 | `../../utils/multipro_plugin.py` | `SimpleParallelTool` |
| 文档 | `docs/FFT_MERGE_程序说明.md` | 原始程序说明 |
| 测试 | `test/test_fft_merge.py` | 核心算法测试 |
| 测试 | `test/test_main.py` | 调用 `src/main.process` 的集成测试 |
| 样例数据 | `NIMM_pip_testdata/multi_wind_fft_blending/test_data/` | 与 `NIMM_pip_repos` 同级；Micaps11 样例输入 |
| 整理清单 | `NIMM_list.md` | 算法目录与待办 |
| 整理日志 | `00log/fft_merge_整理_20260722.log` | 一次整理对应一份日志 |
| 中间数据 | `00temp/fft_merge/` | 整理过程临时数据 |

> **已废弃**：`cli/fft_merge_cli.py`。命令行用 `python -m cli`；直跑用 `python src/main.py`（在 `__main__` 中改 `process` 传参）。  
> **数据位置**：样例仍从同级 `NIMM_pip_testdata/.../test_data` 读取。`resource/` 只放 `fft_merge.ini`。

## 命令行调用示例

在本包根目录执行。命令行没写的参数先读 `resource/fft_merge.ini`，ini 里也没有再用代码预设。

```bash
python -m cli --help

python -m cli --main-uv <主风场.m11> --ass-uv <辅助风场.m11> --output-dir resource/output --output-prefix sample_a
```

## 输入输出

输入：

- `main_da`：主风场，`xarray.DataArray`，标准六维结构为 `member, level, time, dtime, lat, lon`。
- `ass_da_list`：辅助风场列表，每个元素与主风场结构和空间分辨率一致。
- `feature_border`：内部特征匹配重采样网格边长。
- `max_iterations`：最大迭代次数。
- `move_percent`：主场向辅助场特征位置移动的比例，取值范围 `(0, 1]`。

输出：

- 融合后的 `xarray.DataArray`。当 `member` 长度为 2 时按 `u/v` 矢量风处理；当 `member` 长度为 1 时按标量场处理。

## 当前整理状态

当前阶段为原始算法整理至中间目录，尚未补充到正式算法仓库目录。

已完成：

- 将原始根目录源码 `fft_merge.py` 整理到 `src/`。
- `src/main.py`：可调度 `process`；`__main__` 直接传参运行。
- `cli/__main__.py`：命令行 argparse → `main.process`。
- `process` / CLI 支持 `is_multi`、`pro_count`。
- 废弃并删除 `cli/fft_merge_cli.py`。
- 补齐算法包内 `00temp/`、`00log/`、`NIMM_list.md`（见 `00log/fft_merge_整理_20260723.log`）。

待处理：

- 向 `NIMM_pip_testdata/multi_wind_fft_blending/test_data/` 补齐样例后跑通完整测试。
- 样例数据补齐后，用文档中的 `python -m cli` 示例做一次完整试跑。
- 正式补充到 `NIMM/05blending/` 时统一包路径。
- 评估是否继承仓库 `BasePlugin`。

