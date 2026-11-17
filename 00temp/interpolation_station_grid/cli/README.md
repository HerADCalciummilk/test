# CLI

详细说明与示例见 [`docs/interpolation_station_grid.md`](../docs/interpolation_station_grid.md) 第 8 节。

在本包目录执行：

```bash
python -m cli --module idw --sta sta.csv --grid grid.nc
python -m cli --module idw --sta sta.m3 --grid grid.m4 --output out.nc
python -m cli --module cressman --sta sta.csv --grid grid.nc --r-list 60000,40000,20000
```

站点：`csv` / `m3`；格点与输出：`nc` / `m4`（可用 `--sta-type` / `--grid-type` / `--output-type` 显式指定）。
