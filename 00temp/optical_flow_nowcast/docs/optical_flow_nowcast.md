# 临近光流法外推预报

## 算法概述

本算法用于基于光流和半拉格朗日平流的临近外推预报。原始目录包含 Lucas-Kanade 光流平流估计、外推预报，以及 LINDA、S-PROG、STEPS 等相关临近预报方法。

本次归档重点对应用户提供的“临近光流法外推预报”：

- `LK`：基于 Lucas-Kanade 特征追踪计算二维平流速度场。
- `Extrapolation`：基于输入降水场和平流速度场进行半拉格朗日外推。
- `linda`、`sprog`、`steps`：同一原始目录内的相关临近预报算法，作为上下游或扩展能力一并保留。

## 目录说明

| 目录 | 内容 |
| --- | --- |
| `src/` | 光流、外推和相关临近预报核心源码 |
| `nbs/` | 原始 notebook 示例 |
| `test_data/` | 原始输出样例数据 |
| `cli/` | 每个功能模块一个入口，在本包目录执行 `python -m cli.<模块名>_cli` |
| `docs/` | 归档说明文档 |
| `resource/` | 资源说明 |
| `test/` | 最小测试脚本 |
| `utils/` | 工具说明目录 |

## 公开插件

```python
from optical_flow_nowcast.src import Extrapolation, LK
```

`LK.process(...)` 输出平流速度场和时间间隔，`Extrapolation.process(...)` 使用平流速度场对最近一次降水场进行多时效外推。

## 命令行

在本包目录执行。没写的参数先读 `resource/optical_flow.ini`，再没有则用代码预设。降水场、平流场路径和外推时次在命令行和 ini 里都为空时会报错。命令行只打印解析后的参数，不读取降水场，也不运行外推。`lk_kwargs`、`extrap_kwargs` 这类字典参数和 `callback` 仍用插件代码里的默认值。

```bash
python -m cli.lk_plugin_cli --precip obs1.nc,obs2.nc
```

```bash
python -m cli.extrapolation_plugin_cli --precip obs.nc --velocity uv.nc --timesteps 6
```

```bash
python -m cli.sprog_plugin_cli --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6
```

```bash
python -m cli.linda_plugin_cli --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6
```

```bash
python -m cli.steps_plugin_cli --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6
```

直接执行 `python -m cli` 会列出以上命令。

## 整理说明

原始代码依赖 NIMM 业务环境中的 `nimm.PostProcessingPlugin` 和 `nimm.nowcast.*` 包路径。归档副本已提供轻量 `PostProcessingPlugin` 兼容基类。降水强度变换已拆到同级子模块 `db_trans`，Lucas-Kanade 在估平流前调用 `db_trans.src.dB_trans`。同名的算法和插件已写在同一个文件里：`lk_plugin.py`、`extrapolation_plugin.py`、`linda_plugin.py`、`sprog_plugin.py`、`steps_plugin.py`。插件类直接调用本文件中的 `forecast`。

