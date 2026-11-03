# CLI

在本包目录执行 `python -m cli`。用 `--module` 选择 `total`、`idw`、`idw_delta`、`gaussian`。没写的参数先读 `resource/fusion.ini`，再没有则用预设。`sta` 和 `grid` 为空时报错。

```bash
python -m cli --module total --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc
```

```bash
python -m cli --module idw --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc
```

```bash
python -m cli --module idw_delta --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc
```

```bash
python -m cli --module gaussian --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc --half-r 20
```
