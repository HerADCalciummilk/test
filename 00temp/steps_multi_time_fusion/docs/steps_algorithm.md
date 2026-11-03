# NIMM STEPS 降水融合算法说明

## 1. 现有代码验证结论

原始 `STEPS` 目录包含三类核心能力：

- `noise/`：非参数滤波器训练和 AR(2) 噪声生成。
- `climatological_skill/`：按 cascade level 计算气候态 skill。
- `Blending/`：基于 STEPS cascade 的 nowcast/NWP/noise 融合。

验证结果：

- 原始代码语法编译通过。
- 核心数值函数可以运行。
- `pytorch` conda 环境中 `numpy/scipy/netCDF4/meteva.base/cartopy/matplotlib` 均可用。
- 默认 Python 环境缺少 `netCDF4/meteva/cartopy`，不能运行完整文件 I/O 型业务脚本。
- 原始 CLI 中硬编码了 `D:\code\...` 示例路径，当前机器缺少这些数据，直接运行完整融合 CLI 会因文件不存在失败。
- 原始日志中含有部分特殊符号，在 Windows GBK 控制台下可能触发 `UnicodeEncodeError`。

因此，本次改造保留算法核心，修正导入方式、命名和 CLI 参数化问题。

## 2. 公开插件

| 插件类 | 功能 | 路径 |
| --- | --- | --- |
| `StepsNoisePlugin` | 训练非参数滤波器并生成 AR(2) 噪声场。 | `src/noise_plugin.py` |
| `ClimatologicalSkillPlugin` | 计算日 skill 和 climatological skill。 | `src/climatological_skill_plugin.py` |
| `StepsBlendingPlugin` | 对 nowcast 与 NWP 二维降水场进行 STEPS cascade 融合。 | `src/steps_blending_plugin.py` |

导入方式：

```python
from steps_multi_time_fusion.src import StepsNoisePlugin, ClimatologicalSkillPlugin, StepsBlendingPlugin
```

## 3. 目录结构

| 路径 | 作用 |
| --- | --- |
| `src/noise.py` | 非参数滤波器和 AR(2) 噪声核心算法。 |
| `src/climatological_skill.py` | cascade skill 和气候态 skill 核心算法。 |
| `src/steps_blending.py` | STEPS cascade 融合核心算法。 |
| `src/*_plugin.py` | 对外公开插件类。 |
| `cli/` | 参数化命令行入口。 |
| `test/` | 最小单元测试。 |
| `docs/` | 中文说明文档。 |

## 4. 命令行入口

生成 AR(2) 噪声：

```bash
python -m steps_multi_time_fusion.cli.noise generate --output-dir output_noise --issue-time 202508191600
```

汇总 climatological skill：

```bash
python -m steps_multi_time_fusion.cli.climatological_skill --input-dir clim_skill_data --output clim_skill_data/climatological_skill.npy
```

对两个二维 `.npy` 文件进行 STEPS 融合：

```bash
python -m steps_multi_time_fusion.cli.blending --nowcast nowcast.npy --nwp nwp.npy --output blended.npy
```

## 5. 注意事项

- 完整业务数据读写仍需要 `pytorch` 环境中的 `meteva.base`、`netCDF4` 等依赖。
- 新 CLI 不再硬编码 `D:\code\...` 路径。
- 新代码避免使用可能导致 Windows 控制台编码错误的特殊日志符号。
- 原始目录中的论文、PPT、展开的 docx 文件和 notebook 未迁移到新包。
