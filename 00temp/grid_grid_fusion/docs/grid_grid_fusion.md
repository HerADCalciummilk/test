# 格点→格点融合算法说明

## 算法概述

将源格点场重采样到目标水平网格。提供最近邻、双线性、双三次三种水平插值。

## 核心能力

- `InterpGgNearest`：最近邻。目标点取源场四舍五入最近格点。
- `InterpGgLinear`：双线性。算法对齐独立包 `interp_gg_linear`。
- `InterpGgCubic`：双三次。核函数与 `interpolating.cubic_f` 一致。

三者共同点：

- 接口均为 `process(grd, grid)`；`used_coords` 当前仅支持 `xy`。
- **全球循环场仍检查纬度越界**，超出须给 `outer_value`（异于库内不查纬度的行为）。
- 依赖 `meteva_base` 数据结构与工具，**不**直接调用库内 `interp_gg_*`。
- 结果 `attrs` 继承自源场。

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `src/` | 插件类 |
| `cli/` | `python -m cli`，`--module` 选 linear / nearest / cubic |
| `resource/conf.ini` | 命令行缺省参数 |
| `test/` | 配置解析与示例 |
| `docs/` | 本说明 |
| `utils/util_env.py` | 读取运行配置；并入 `00temp/utils` |

## 主要入口

```python
from grid_grid_fusion.src import InterpGgLinear, InterpGgNearest, InterpGgCubic
import meteva_base as meb

grd = meb.read_griddata_from_nc("source.nc")
grid = meb.basicdata.grid([70, 140, 0.1], [15, 55, 0.1])
result = InterpGgLinear(outer_value=0.0).process(grd, grid)
```

## CLI 示例

```bash
python -m cli --module linear --grid <grid.nc> --domain 20,50,70,140,0.1,0.1 --outer-value 0
python -m cli --module nearest --grid <grid.nc> --domain 20,50,70,140,0.1,0.1 --outer-value 0
python -m cli --module cubic --grid <grid.m4> --glon 70,140,0.1 --glat 15,55,0.1 --output out.m4
```

## 注意事项

1. 依赖 `meteva_base`、`numpy`，以及共享 `utils.base_plugin`。
2. 目标超出源网格且未设 `outer_value` 时，插件返回 `None`；CLI 会报错退出。
