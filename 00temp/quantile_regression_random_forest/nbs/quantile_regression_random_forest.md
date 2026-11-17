# Quantile Regression Random Forest（分位数回归随机森林）

## 算法概述

`quantile_regression_random_forest` 改写自 IMPROVER 的 `improver.calibration.quantile_regression_random_forest`。它用历史集合预报和对应实况训练分位数回归森林，再对一份新的集合预报输出指定分位数。目标环境不使用 iris，输入和输出都是 meteva 的格点或站点数据。

集合的条件分布来自 Meinshausen 的分位数回归森林。`src/_quantile_forest.py` 是 quantile-forest 1.4.2 的源码副本，原来的 Cython 扩展改写在 `src/_quantile_forest_fast.py` 和 `src/_utils.py`。运行时不再导入已安装的 `quantile-forest` 包，也不依赖 IMPROVER 和 iris。

## 数据对应关系

meteva 格点由 `meteva_base.read_griddata_from_nc` 读成六维 `DataArray`，维度顺序是 `member, level, time, dtime, lat, lon`。

| meteva | 含义 | IMPROVER 中的对应量 |
| --- | --- | --- |
| member | 集合成员 | realization |
| level | 层次 | height / pressure |
| time | 起报时间 | forecast_reference_time |
| dtime | 预报时效 | forecast_period |
| lat, lon | 纬度和经度 | latitude, longitude |
| time + dtime | 有效时间 | time |

`dtime` 的单位看数据属性 `dtime_units`，取值为 `hour` 或 `minute`，规则与 `meteva_base.set_griddata_attrs` 一致。

站点表由 `meteva_base.read_stadata_from_csv` 读取。固定列是 `level, time, dtime, id, lon, lat`，其后是要素列。集合预报增加数值型 `member` 列。实况用 `ob_value`，并且 `dtime` 为 0 时，`time` 就是观测有效时间。

格点订正时，每个经纬度格点被当作一个站点，默认站点键是 `lat, lon`。站点订正默认使用 `id`。不同层次不会混在同一次统计里。

## 特征

特征配置是一个字典。键是预报列名，值是该列要计算的特征：

- `mean`、`std`、`min`、`max`：沿集合成员统计
- `percentile_50`：沿成员取百分位
- `members_below_273.15`、`members_above_0`：统计过阈值的成员数
- `static`：原列直接作为特征，例如海拔
- `day_of_year`、`day_of_year_sin`、`day_of_year_cos`
- `hour_of_day`、`hour_of_day_sin`、`hour_of_day_cos`

日期和小时由有效时间 `time + dtime` 计算。`log`、`log10`、`sqrt`、`cbrt` 会先作用于目标列，预测出的分位数再反变换。

## 输出

订正结果仍是 meteva 格点或站点表。原来的集合成员被替换为分位数：格点的 `member` 坐标写成 `0.1` 这样的字符串，站点的 `member` 列写成 `0.1` 这样的数值。起报时间、时效、层次和位置保持为输入预报的值。

## 运行

在本仓库根目录执行。默认读取 `quantile_regression_random_forest/testdata` 里的站点示例：

```text
python -m quantile_regression_random_forest train --output quantile_regression_random_forest_model.pkl
python -m quantile_regression_random_forest apply --model quantile_regression_random_forest_model.pkl --quantiles 0.1,0.5,0.9 --output quantile_regression_random_forest_calibrated.csv
```

格点示例：

```text
python -m quantile_regression_random_forest train --forecast quantile_regression_random_forest/testdata/forecast_grid.nc --truth quantile_regression_random_forest/testdata/truth_grid.nc --feature-config quantile_regression_random_forest/testdata/feature_config_grid.json --output quantile_regression_random_forest_grid_model.pkl
python -m quantile_regression_random_forest apply --forecast quantile_regression_random_forest/testdata/forecast_grid.nc --model quantile_regression_random_forest_grid_model.pkl --output quantile_regression_random_forest_calibrated.nc
```

`python -m quantile_regression_random_forest.cli` 与 `python -m quantile_regression_random_forest` 使用同一入口。
