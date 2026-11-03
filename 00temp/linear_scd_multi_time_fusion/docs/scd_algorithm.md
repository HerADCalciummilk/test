# NIMM SCD 短临降水拆分与融合算法说明

## 1. 改造范围

本次只整理用户指定的核心链路：

- 时间拆分：原 `split_code/realtime_split_qpf.py`
- SCD 融合：原 `scd/fuse_code/run_scd_pair_fusion_from_config.py`
- 融合结果补齐：原 `scd/fuse_code/pad_fusion_output_from_config.py`

旧目录中的日志文件、可视化脚本、历史 notebook、无关 CLI 和 IDE 配置未纳入新包。

## 2. 对外公开插件

| 插件类 | 功能 | 路径 |
| --- | --- | --- |
| `QpfSplitPlugin` | 将 `unet_qpf` 与 `mait_st` 拆分并插值到统一的 0.01 度、10 分钟网格文件。 | `src/qpf_split_plugin.py` |
| `ScdFusionPlugin` | 按配置对拆分后的 `unet_qpf` 和 `mait_st` 进行 SCD 双源融合。 | `src/scd_fusion_plugin.py` |

包级公开方式：

```python
from linear_scd_multi_time_fusion.src import QpfSplitPlugin, ScdFusionPlugin
```

## 3. 目录结构

| 路径 | 作用 |
| --- | --- |
| `src/split_workflow.py` | 时间拆分主流程，来自原 `realtime_split_qpf.py`。 |
| `src/pair_fusion_workflow.py` | SCD 双源配对融合主流程。 |
| `src/padding_workflow.py` | 融合结果前后时段补齐流程。 |
| `src/linear_blending.py` | 线性融合和显著性融合核心数值算法。 |
| `src/qpf_split_plugin.py` | 时间拆分插件类。 |
| `src/scd_fusion_plugin.py` | SCD 融合插件类。 |
| `cli/` | 命令行入口。 |
| `resource/` | 默认配置模板。 |
| `test/` | 最小单元测试。 |
| `docs/` | 中文说明文档。 |

## 4. 命令行入口

时间拆分：

```bash
python -m linear_scd_multi_time_fusion.cli.split_qpf
python -m linear_scd_multi_time_fusion.cli.split_qpf 202608080810 202608080840
```

SCD 融合：

```bash
python -m linear_scd_multi_time_fusion.cli.run_scd_fusion
python -m linear_scd_multi_time_fusion.cli.run_scd_fusion 202608080810 202608080840
```

融合结果补齐：

```bash
python -m linear_scd_multi_time_fusion.cli.pad_fusion_output
python -m linear_scd_multi_time_fusion.cli.pad_fusion_output 202608080810 202608080840
```

三个入口均支持 `--config` 指定配置文件。

## 5. 配置文件

| 配置文件 | 来源 | 用途 |
| --- | --- | --- |
| `resource/split_config.ini` | 原 `split_code/config.ini` | 时间拆分配置。 |
| `resource/scd_pair_fusion_config.ini` | 原 `scd/fuse_code/scd_pair_fusion_config.ini` | 融合和补齐配置。 |

默认配置保留原生产路径。实际部署时可直接修改 `resource/` 中的配置，或通过 `--config` 指向外部配置。

## 6. 算法流程

时间拆分流程：

1. 查找实时或历史范围内的 `unet_qpf` 源文件。
2. 读取 `unet_qpf` 的 NetCDF 多时效数据。
3. 按 `unet_qpf` 起报时间对齐对应的 `mait_st` 小时产品。
4. 对两个来源做空间重叠区域裁剪与 0.01 度插值。
5. 将 `mait_st` 小时累计量拆分到 10 分钟时段。
6. 分别写出 `unet_qpf` 和 `mait_st` 的 10 分钟 NetCDF 文件。

SCD 融合流程：

1. 从配置中的 `source1_dir` 和 `source2_dir` 按相对路径配对文件。
2. 读取两个来源的 `data0` 六维网格数据。
3. 根据 `keyframe_weights` 对不同预报时效计算 source1 权重。
4. 调用 `linear_blending_forecast` 进行线性融合或显著性融合。
5. 写出融合后的 NetCDF 产品。

补齐流程：

1. 在起报时刻之前，用实况文件补齐负时效或零时效。
2. 在融合时效之后，用 `mait_st` 文件补齐到下一个整点。

## 7. 注意事项

- 插件类用于对外集成；文件扫描、读写和配置解析保留在工作流层。
- `QpfSplitPlugin` 和 `ScdFusionPlugin` 默认使用 `resource/` 下的配置文件。
- 融合配置中的 `dry_run = true` 时只检查配对关系，不写出融合结果。
- 旧目录的大型 `.log` 文件没有迁移。
