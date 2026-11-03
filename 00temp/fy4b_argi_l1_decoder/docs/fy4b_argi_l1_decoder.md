# fy4b_argi_l1_decoder

## 算法概述

`fy4b_argi_l1_decoder` 用于 FY-4B 卫星 AGRI L1 HDF 数据解码、通道定标和规则经纬度网格重采样。原始算法读取 FY-4B AGRI L1 HDF 文件中的 `Data/NOMChannelXX` 与 `Calibration/CALChannelXX`，将 DN 值定标为反射率或亮温，并按指定分辨率输出逐通道 NetCDF 文件。

说明：用户给定中文名为“FY4卫星ARGI的L1数据解码”。原始代码、README 和文件名均使用 `AGRI`，本次按用户要求将算法目录命名为 `argi`，但源码包名保留原始 `fy4agri`，以避免改变原始导入逻辑。

## 算法分类

- 分类：`basic_data`
- 分类依据：算法主要进行 FY-4B 卫星 L1 数据读取、定标、投影转换和 NetCDF 预处理输出，属于基础数据读写预处理类。

## 主要能力

- 读取 FY-4B AGRI L1 HDF 文件。
- 按通道读取 `NOMChannelXX` 和 `CALChannelXX`。
- 支持 `1-15` 通道选择。
- 将 FY-4 静止卫星固定网格反算至规则经纬度目标网格。
- 支持 `nearest` 和 `bilinear` 重采样。
- 单文件模式：一个 HDF 文件输出多个通道 NetCDF。
- 批处理模式：扫描指定时段 HDF 文件并按 `CHxx/YYYYMMDD/YYYYMMDDHH.nc` 输出。

## 主要文件

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/fy4agri/metadata.py` | 通道元数据、HDF 属性解析、通道选择解析 |
| 核心源码 | `src/fy4agri/projection.py` | FY-4 静止卫星投影与经纬度网格转换 |
| 核心源码 | `src/fy4agri/reader.py` | 通道定标和重采样 |
| 插件源码 | `src/fy4_latlon_channel_plugin.py` | 单文件 HDF 解码插件 |
| 插件源码 | `src/fy4_batch_latlon_channel_plugin.py` | 批处理 HDF 解码插件 |
| CLI | `cli/` | 在本包目录执行 `python -m cli`，用 `--module batch` 或 `--module single` |
| 运行配置 | `resource/fy4.ini` | 命令行未显式传入的参数先读此文件，再没有则用预设 |
| 旧示例 | `cli/run_fy4_batch.py` | 写死路径的批处理脚本，仍可直接运行 |
| 文档 | `docs/README.md` | 原始 README |
| 测试 | `test/test_fy4b_argi_l1_decoder.py` | 最小参数和元数据解析测试 |

## 输入输出

输入：

- FY-4B AGRI L1 HDF 文件。
- 通道选择，例如 `1-15`、`1,3,7`。
- 目标经纬度网格配置：分辨率、纬度范围、中心经度半宽。

输出：

- 单文件模式：`CHxx_wavelength.nc`。
- 批处理模式：`output_root/CHxx/YYYYMMDD/YYYYMMDDHH.nc`。
- 每个 NetCDF 包含 `channel_value(lat, lon)`、`lat`、`lon`。

## CLI 示例

在本包目录下执行。没写的参数先读 `resource/fy4.ini`，配置里也没有再用代码预设。输入目录、输出目录和时间在两边都为空时会报错，不会猜测路径。网格预设为分辨率 `0.04`、纬度 `-60` 到 `60`、经度半宽 `75`、通道 `1-15`、重采样 `bilinear`。

```bash
python -m cli --module batch --input-root /mnt/data_229/SatelliteData/fy4b_l1 --output-root /mnt/data_229/SatelliteData/fy4b_channel_latlon --start-time 2023010406 --end-time 2023010423
```

```bash
python -m cli --module single --input-hdf D:/testdata/FY4/input.HDF --output-dir D:/testdata/FY4/channel_data/case_name
```

## 当前整理状态

当前阶段为原始算法整理至中间目录，尚未补充到正式算法仓库目录。

已完成：

- 原始核心源码复制到 `00temp/fy4b_argi_l1_decoder/src/`。
- 原始批处理示例复制到 `00temp/fy4b_argi_l1_decoder/cli/`。
- 原始 README 复制到 `docs/README.md`。
- 新增整理说明和最小测试。
- 新建 `resource/`、`test_data/`、`nbs/`、`utils/` 说明文件。

待处理：

- 原始目录未提供真实 FY-4B AGRI HDF 样例，因此当前测试无法验证真实解码数值结果。
- 正式补充到 `NIMM/basic_data/` 时需要统一导入路径。
- 需要确认算法名称中 `ARGI` 与原始代码 `AGRI` 的命名差异是否仅为业务命名要求。

