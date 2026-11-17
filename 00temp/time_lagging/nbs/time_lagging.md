# Time Lagging（时间滞后集合）

## 算法概述

`time_lagging` 改写自 IMPROVER 的 `improver.utilities.time_lagging.GenerateTimeLaggedEnsemble`。它把不同起报时次、但有效时间一致的集合成员拼成一个时间滞后集合。集合变大之后，可以继续用来估计概率；这一步本身不做阈值概率转换。

IMPROVER 用 iris 的 realization、forecast reference time 和 forecast period。这里改成 meteva 数据，不再依赖 iris。

## 数据对应关系

格点是 `member, level, time, dtime, lat, lon` 六维数据，读取函数是 `meteva_base.read_griddata_from_nc`。

| meteva | 含义 |
| --- | --- |
| member | 集合成员 |
| level | 层次 |
| time | 起报时间 |
| dtime | 预报时效 |
| lat, lon | 纬度和经度 |

有效时间是 `time + dtime`。`dtime_units` 为 `hour` 或 `minute`，由 `meteva_base.set_griddata_attrs` 的同一属性决定。

站点表的固定列是 `level, time, dtime, id, lon, lat`。有集合成员时增加 `member` 列，要素放在后续列。读取函数是 `meteva_base.read_stadata_from_csv`。

不同起报时次要分成不同文件或不同数据对象。六维格点的 `time` 和 `dtime` 是两个独立维度，一份格点不能同时表达“00 时起报、时效 12 小时”和“06 时起报、时效 6 小时”。

## 处理步骤

1. 检查每份输入的有效时间集合是否相同。不一致就停止。
2. 找到最新的起报时间，把所有输入的 `time` 改成这个时次。
3. 重算 `dtime`，使有效时间保持不变。例如 00 时起报的 12 小时时效，在统一到 06 时之后变成 6 小时时效。
4. 若不同输入使用了相同的 member 编号，按输入顺序从 0 重新编号。
5. 沿 member 拼接。层次、经纬度和时效坐标必须能够对齐。

只有一个起报时次时算法给出警告，并原样返回。

## 运行

在本仓库根目录执行。默认使用 `time_lagging/testdata` 中 00 时和 06 时两份格点，二者的有效时间都是当日 12 时：

```text
python -m time_lagging --output time_lagging_ensemble.nc
```

站点示例：

```text
python -m time_lagging --inputs time_lagging/testdata/cycle_00.csv time_lagging/testdata/cycle_06.csv --output time_lagging_ensemble.csv
```

`python -m time_lagging.cli` 与 `python -m time_lagging` 使用同一入口。
