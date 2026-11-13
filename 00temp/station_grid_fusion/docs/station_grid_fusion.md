# 网格站点融合算法说明

## 算法概述

网格站点融合算法用于将站点观测信息融合到规则格点产品中。可用于要素精细化、观测订正或主客观一致协调处理。

## 核心能力

- `InterpSgIdw`：站点→格点 IDW。`background=None` 时直接插值；给出背景场时先算偏差再插值并叠加。`gaussian=False` 为纯 IDW（`effectR` 为硬截断半径：超距填 0）；`gaussian=True` 为 IDW×高斯（`effectR` 作高斯半径）。原 `InterpSgIdwDelta` / `InterpSgTotal` 已并入本类。
- `InterpSgKriging`：局部普通克里金（OK）。每个格点用 `nearNum` 个近邻站建方程组；变异函数可选 spherical / exponential / gaussian；`sill` / `range_` 可自动估计。同样支持可选 `background` 偏差订正。
- `InterpSgDeltaGaussian`：最近邻 × 高斯半径扩散。`process(sta, grid, background=None)` 与 IDW 对齐；有背景先算偏差再叠回，无背景直接插站点值。
- `InterpSgCressman`：按 `r_list` 逐步 Cressman 订正。`process(sta, grid, background=None)`；背景作初估场（对齐后改写半径内格点），与 IDW 的偏差订正语义不同。
- `interp_station_to_grid_renew.py`：保留旧函数式实现与批处理示例。

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `src/` | 插件类与旧函数式源码 |
| `cli/` | `python -m cli`，`--module` 选 idw / idw_delta / gaussian / kriging / cressman |
| `resource/conf.ini` | 命令行缺省参数 |
| `test/` | 配置解析测试与示例脚本 |
| `nbs/` | Jupyter notebook |
| `docs/` | 本说明 |
| `utils/util_env.py` | 读取运行配置；并入 `00temp/utils` |

## 主要入口

无背景场插值：

```python
from station_grid_fusion.src import InterpSgIdw

result = InterpSgIdw(effectR=1000, nearNum=8, decrease=2).process(sta, grid_info)
```

有背景场偏差订正：

```python
from station_grid_fusion.src import InterpSgIdw

result = InterpSgIdw(
    effectR=1000, nearNum=8, decrease=2, gaussian=True
).process(sta, grid_info, background=grid_background)
```

普通克里金：

```python
from station_grid_fusion.src import InterpSgKriging

result = InterpSgKriging(
    model="spherical", nearNum=20
).process(sta, grid_info, background=None)
```

## CLI 示例

在本包目录下执行。没写的参数先读 `resource/conf.ini`。`sta` 和 `grid` 两边都为空时会报错。

`--module idw_delta` 仍可用（`InterpSgIdw(gaussian=True)`，`--grid` 作背景场）。`--module total` 为 `idw` 旧别名。

```bash
python -m cli --module idw --sta <sta.csv> --grid <grid.nc>
python -m cli --module idw --sta <sta.csv> --grid <grid.nc> --background <bg.nc>
python -m cli --module idw_delta --sta <sta.csv> --grid <grid.nc>
python -m cli --module kriging --sta <sta.csv> --grid <grid.nc> --kriging-model spherical --near-num 20
python -m cli --module gaussian --sta <sta.csv> --grid <grid.nc> --half-r 20
python -m cli --module gaussian --sta <sta.csv> --grid <grid.nc> --background <bg.nc> --half-r 20
python -m cli --module cressman --sta <sta.csv> --grid <grid.nc> --r-list 60000,40000,20000
python -m cli --module cressman --sta <sta.csv> --grid <grid.nc> --background <bg.nc>
```

```python
from station_grid_fusion.src import InterpSgDeltaGaussian

result = InterpSgDeltaGaussian(halfR=20).process(sta, grid_info, background=bg)
```

```python
from station_grid_fusion.src import InterpSgCressman

result = InterpSgCressman(r_list=[60000, 40000, 20000], nearNum=100).process(
    sta, grid_info, background=bg
)
```


## 注意事项

1. 依赖 `meteva_base`、`numpy`、`scipy`，以及共享 `utils.base_plugin`。
2. 示例路径可能仍含旧绝对路径，正式测试前请替换。
3. 原始目录未提供独立测试数据；示例脚本在 `test/`，notebook 在 `nbs/`。
