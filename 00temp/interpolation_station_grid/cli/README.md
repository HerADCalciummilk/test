# CLI

详细说明与示例见 [`docs/interpolation_station_grid.md`](../docs/interpolation_station_grid.md) 第 8 节。

在 `00temp` 目录执行（包根入口，解析命令行 `key=value`）：

```bash
python -m interpolation_station_grid method=idw sta=resource/obs_gust_d24.csv grid=resource/target_grid.nc
python -m interpolation_station_grid method=idw sta=resource/obs_gust_d24.csv grid=resource/target_grid.nc output=resource/out_idw.nc
python -m interpolation_station_grid method=cressman sta=resource/obs_gust_d24.csv grid=resource/target_grid.nc cressman_r_list=60,40,20
# Cressman 度制路径（须 background）；degree_blend=1.0 + rain_limit=0.01 即 rain24 original 形态
python -m interpolation_station_grid method=cressman sta=resource/obs_gust_d24.csv background=resource/bg_fcst_idw.nc reprocess=true cressman_degree_blend=1.0 cressman_rain_limit=0.01
```

- `idw_effect_r`、`gaussian_half_r` 单位为千米，可写小数。
- `cressman_*` 高级参数（`rain_limit`、`degree_blend`、`num_limit` 等）只在 `method=cressman reprocess=true` 时生效，键名与预设见 `resource/conf.ini`。

- 算法实现与 `process` 形参在 `interpolation_station_grid_cli.py`；默认值在 `resource/conf.ini`。
- `cli/__main__.py` 也支持在本包目录执行 `python -m cli key=value ...`（无参数时读 `conf.ini` 与签名预设）。

站点：`csv` / `m3`；格点与输出：`nc` / `m4`（可用 `sta_type` / `grid_type` / `output_type` 显式指定）。
