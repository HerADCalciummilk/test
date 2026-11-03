# STEPS多时效融合

## 算法概述

本算法基于 STEPS cascade 思路，对临近预报、NWP 预报和随机噪声进行多时效降水融合。归档副本保留原始算法的三个核心能力：

- `StepsNoisePlugin`：训练非参数滤波器并生成 AR(2) 噪声场。
- `ClimatologicalSkillPlugin`：按 cascade level 计算日 skill 和 climatological skill。
- `StepsBlendingPlugin`：对 nowcast 与 NWP 二维降水场执行 STEPS cascade 融合。

## 目录说明

| 目录 | 内容 |
| --- | --- |
| `src/` | STEPS 核心算法与插件类 |
| `cli/` | 基于 `.npy` 文件的命令行验证入口 |
| `test/` | 最小核心单元测试 |
| `nbs/` | Notebook 使用示例 |
| `docs/` | 算法说明文档 |
| `resource/steps.ini` | 统一 CLI 的运行配置。`--module` 选择模块；未显式传入的参数先读此文件，再没有则用预设 |
| `utils/util_env.py` | 按「显式参数 > ini > 预设」补齐 CLI 参数 |

## 命令行调用示例

在本包目录下执行。用 `--module` 选择模块；没写的参数先读 `resource/steps.ini`，配置里也没有再用代码预设。输入路径在 ini 里留空时必须在命令行传入。

```bash
python -m cli --module noise --output-dir output_noise --issue-time 202508191600
```

```bash
python -m cli --module climatological_skill --input-dir clim_skill_data --output clim_skill.npy
```

```bash
python -m cli --module blending --nowcast nowcast.npy --nwp nwp.npy --output blended.npy
```

## 使用示例

```python
from steps_multi_time_fusion.src import (
    ClimatologicalSkillPlugin,
    StepsBlendingPlugin,
    StepsNoisePlugin,
)
```

## 整理说明

原始算法包名为 `nimm_steps`。归档到 `00temp/steps_multi_time_fusion/` 后，已将归档副本内的导入路径统一调整为 `steps_multi_time_fusion`，核心数值算法逻辑未改动。
