# NIMM Kalman 土壤温湿度订正算法说明

## 1. 改造范围

本算法包只保留原始目录中两个脚本实际使用到的流程：

- `kalman_data.sh`：运行 `SWVL` 土壤湿度和 `STL` 土壤温度的 Kalman 订正。
- `trans_data.sh`：将原始 `SWVL`、`STL` 的 NetCDF 文件复制到 Kalman 处理目录。

旧目录中的 `improver`、历史 notebook、demo、备份脚本和其他无关算法未纳入本次改造。

## 2. 目录结构

| 路径 | 作用 |
| --- | --- |
| `src/kalman_cli.py` | Kalman 误差更新和预报订正的通用主流程。 |
| `src/kalman_me_plugin.py` | `KalmanME` 插件，用于更新平均误差或平均绝对误差。 |
| `src/kalman_fix_plugin.py` | `KalmanFix` 插件，用于基于误差场订正预报场。 |
| `src/data_transfer.py` | `SWVL/STL` 源数据复制流程。 |
| `utils/grid_utils.py` | `meteva_base` 网格数据校验、坐标匹配和 Kalman 数值计算工具。 |
| `cli/kalman_data.py` | 替代原 `kalman_data.sh` 的 Python CLI 入口。 |
| `cli/trans_data.py` | 替代原 `trans_data.sh` 的 Python CLI 入口。 |
| `test/` | 非文件 I/O 部分的最小单元测试。 |
| `docs/` | 算法说明文档。 |
| `resource/` | 资源文件目录，目前无必须内置资源。 |
| `nbs/` | notebook 示例目录，目前仅保留目录说明。 |

## 3. 算法插件清单

| 算法插件 | 功能 | 路径 |
| --- | --- | --- |
| `KalmanME` | 根据最新预报和实况网格更新 Kalman 平均误差场或平均绝对误差场。 | `src/kalman_me_plugin.py` |
| `KalmanFix` | 使用最新 Kalman 平均误差场对模式预报网格进行订正。 | `src/kalman_fix_plugin.py` |

## 4. 输入输出

插件层输入输出均为内存对象，不直接读写文件。主要数据类型为符合 `meteva_base` 六维网格格式的 `xarray.DataArray`：

```text
member, level, time, dtime, lat, lon
```

文件读取、插值、路径拼接和结果写出均放在 CLI 流程中处理。

默认输出路径模板保持原脚本逻辑：

```text
{base_dir}/kal_me/{variable}/{level}/YYYY/YYYYMMDD/YYMMDDHH.TTT.nc
{base_dir}/output/{variable}/{level}/YYYY/YYYYMMDD/YYMMDDHH.TTT.nc
```

## 5. 运行方式

运行前一天的 Kalman 订正：

```bash
python -m kalman_element_forecast_correction.cli.kalman_data
```

运行指定日期范围：

```bash
python -m kalman_element_forecast_correction.cli.kalman_data 20260401 20260405
```

只运行某一个变量：

```bash
python -m kalman_element_forecast_correction.cli.kalman_data 20260401 20260401 --variables SWVL
python -m kalman_element_forecast_correction.cli.kalman_data 20260401 20260401 --variables STL
```

复制前一天源数据：

```bash
python -m kalman_element_forecast_correction.cli.trans_data
```

复制指定日期源数据：

```bash
python -m kalman_element_forecast_correction.cli.trans_data 20260401
```

也可以继续使用包装脚本：

```bash
bash kalman_data.sh
bash trans_data.sh
```

## 6. 默认路径

默认路径保留原脚本的生产路径，可通过 CLI 参数覆盖。

| 配置项 | 默认值 |
| --- | --- |
| Kalman 根目录 | `/data234/GUO_data/Kalman_data` |
| 实况根目录 | `/data234/DataPool/01CLDAS/00HRCLDAS/Hourly` |
| SWVL 源数据目录 | `/data/mnt/model_RT/globalECMWF_D1D/SWVL` |
| STL 源数据目录 | `/data/mnt/model_RT/globalECMWF_D1D/STL` |

示例：

```bash
python -m kalman_element_forecast_correction.cli.kalman_data --base-dir /data234/GUO_data/Kalman_data
python -m kalman_element_forecast_correction.cli.trans_data --target-base /data234/GUO_data/Kalman_data/process_data
```

## 7. 主要处理逻辑

`kalman_data` 流程：

1. 根据日期生成每日 `00`、`12` 两个起报时次。
2. 按变量 `SWVL/STL` 和层级 `5/10/40` 循环处理。
3. 对每个预报时效读取模式预报、实况和已有 Kalman 误差场。
4. 若已有最新误差场则直接读取，否则向前回溯并更新误差场。
5. 使用 `KalmanFix` 生成订正结果。
6. 写出 `kal_me` 和最终订正产品。

`trans_data` 流程：

1. 默认取系统日期的前一天，也可通过参数指定日期。
2. 遍历 `SWVL` 和 `STL`。
3. 将旧层级 `0-7/7-28/28-100/100-MISSING` 映射为 `5/10/40/100`。
4. 复制源目录下的 `.nc` 文件到 `process_data` 目录，保留原文件名。

## 8. 注意事项

- 生产运行依赖 `meteva_base`、`numpy`、`xarray` 等科学计算库。
- 当前本机 `pytorch` conda 环境中已确认存在 `meteva_base`。
- `kalman_data` 默认不限制最新可用观测时间；若实时业务需要避免使用晚于某一时刻的实况，可通过 `--obs-end-time YYYYMMDDHH` 显式指定。
- 预报场有效值中位数大于 `150` 时，会按开尔文自动转换为摄氏度。
- 默认处理变量为 `SWVL` 和 `STL`。
- 默认订正层级为 `5`、`10`、`40`，与原生产脚本保持一致。
