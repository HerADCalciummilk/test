# 线性SCD多时效融合算法说明

## 算法概述

线性SCD多时效融合算法用于短临降水预报与模式降水产品的多时效融合。算法先将 `unet_qpf` 和 `mait_st` 拆分、插值到统一的 0.01 度、10 分钟网格，再按预报时效权重进行线性融合或显著性融合，最后可对融合结果进行前后时段补齐。

## 核心能力

- `QpfSplitPlugin`：读取 `unet_qpf` NetCDF 和 `mait_st` MICAPS4/NetCDF 产品，完成空间裁剪、线性插值和 10 分钟时段拆分。
- `ScdFusionPlugin`：按配置文件配对两个来源的 10 分钟产品，根据关键时效权重进行 SCD 双源融合。
- `linear_blending_forecast`：提供逐帧权重线性融合，并可叠加降水梯度显著性权重。
- `padding_workflow`：将融合结果向起报时刻前后补齐，前段使用实况文件，尾段使用 `mait_st` 文件。

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `src/` | 核心算法、拆分流程、融合流程和补齐流程 |
| `cli/` | 时间拆分、SCD 融合、结果补齐的命令行入口 |
| `resource/` | 默认配置模板 |
| `test/` | 线性融合最小单元测试 |
| `test_data/` | 测试数据说明 |
| `nbs/` | notebook 示例 |
| `docs/` | 算法说明文档 |
| `utils/` | 预留工具目录 |

## 使用入口

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

上述入口均支持 `--config` 指定外部配置文件。

## 注意事项

1. 导入包名已与目录名一致：`linear_scd_multi_time_fusion.src` 和 `linear_scd_multi_time_fusion.cli`。
2. `resource/` 中的默认配置保留生产环境路径，正式运行前需要按部署环境修改。
3. `scd_pair_fusion_config.ini` 中 `dry_run = false` 时会写出融合产品，测试时建议先改为 `true` 或使用隔离输出目录。
4. 原始目录未提供独立小样例输入数据，完整拆分、融合和补齐流程仍需业务数据环境验证。
