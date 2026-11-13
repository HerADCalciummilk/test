# CLI

在本包目录执行 `python -m cli`。用 `--module` 选择 `idw`、`idw_delta`、`gaussian`、`kriging`、`cressman`（`total` 为 `idw` 旧别名）。
`idw` / `idw_delta` 均走 `InterpSgIdw`；`gaussian` 走 `InterpSgDeltaGaussian`；`kriging` 走 `InterpSgKriging`；`cressman` 走 `InterpSgCressman`。
`idw` / `gaussian` / `kriging` 的 `--background` 为偏差订正；`cressman` 的 `--background` 为初估场。
没写的参数先读 `resource/conf.ini`，再没有则用预设。`sta` 和 `grid` 为空时报错。

```bash
python -m cli --module idw --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc
```

```bash
python -m cli --module idw --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc --background /path/to/bg.nc
```

```bash
python -m cli --module idw_delta --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc
```

```bash
python -m cli --module kriging --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc --kriging-model spherical --near-num 20
```

```bash
python -m cli --module gaussian --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc --half-r 20
```

```bash
python -m cli --module cressman --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc --r-list 60000,40000,20000
```
