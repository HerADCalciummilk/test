# 福建 OTS 降水订正

## 算法实现原理

OTS（Optimal Threshold Scheme，最优阈值方案）用历史站点实况和 EC 预报，为每个时效、每个降水等级搜索订正阈值，再用反距离权重把站点订正量插值到格点。

两条任务：

1. `threshold`：对应原 autofjyz。读历史样本，由 `OtsThresholdPlugin` 生成 20 个时效、10 个降水等级的阈值表。
2. `forecast`：对应原 autofcast。读 12 小时降水场和阈值表，由 `OtsForecastPlugin` 做插值订正，并合成 24 小时降水。

`task=both` 时，订正直接使用刚算出的阈值表。20 个时效为 12、24、…、240 小时。等级阈值为 0.1、1、5、10、25、35、50、75、100、150 毫米。搜索上下限和分段订正在 `ots_fzmos_rain_util_plugin`（实现文件 `_util_plugin.py`）。

`pro_count` 大于 1 时，并行在插件内部完成，不在命令行再套一层进程池。

## 算法参数说明

入口是 `cli/ots_fzmos_rain_cli.py` 的 `process`。常用参数：

| 参数 | 含义 |
| --- | --- |
| `task` | `threshold`、`forecast` 或 `both` |
| `pro_count` | 插件内部并行进程数，默认 1 |
| `initial_time` / `now` | 起报或当前时间 |
| `input_time_zone` / `output_time_zone` | 输入、输出时区，默认 `CST` |
| `input_rain12_dir` / `input_apcp_dir` | 12 小时降水和 APCP 目录 |
| `threshold_file` | 阈值表路径 |
| `output_rain12_m4_dir` / `output_rain24_m4_dir` | 12/24 小时 Micaps4 输出目录 |
| `output_rain12_nc_dir` / `output_rain24_nc_dir` | 12/24 小时 NetCDF 输出目录 |
| `obs_dir` / `ec_dir` / `station_file` | 阈值任务的实况、EC 和站点表 |
| `station_count` | 站点数量，默认 70 |
| `interpolation_radius` | 反距离插值半径，默认 0.7 度 |
| `config` / `ini_path` | 本次 ini，`config` 优先。省略则读 `resource/conf.ini` |

源网格和输出网格的起止经纬度、间隔、点数也是 `process` 的具名参数，与 `resource/conf.ini` 对应。显式参数优先于 ini，ini 空项再用函数预设。

## 算法调用示例

在 `00temp`：

```text
python -m ots_fzmos_rain task=forecast initial_time=2026090108
python -m utils.nimm_cli ots_fzmos_rain ini_path=resource/conf.ini pro_count=4
```

在本包目录：

```text
python -m cli task=threshold initial_time=2026090108
python cli/ots_fzmos_rain_cli.py
```

Python：

```python
from cli.ots_fzmos_rain_cli import process

process(task="forecast", initial_time="2026090108", pro_count=1)
```

`process` 先读历史样本或 12 小时场，再调用阈值插件和订正插件，最后把格点写成 m4 或 nc。
