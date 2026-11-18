# interpolation_grid_station 算法说明

将源格点场插值到站点位置。面向 `meteva_base` 六维场（`member, level, time, dtime, lat, lon`）。

算法对齐 `00temp/utils/interpolating.py` 中的 `interp_gs_*`，封装为 `PostProcessingPlugin`。

---

## 1. 插件一览

| 插件 | 功能简介 |
| --- | --- |
| `InterpGsNearest` | 格点→站点最近邻；索引四舍五入 |
| `InterpGsLinear` | 格点→站点双线性；`xy` / `xyz` / `xydt` |
| `InterpGsCubic` | 格点→站点双三次；三次卷积核加权 |

---

## 2. 目录结构

| 路径 | 内容 |
| --- | --- |
| `src/` | 插件与 `gs_helpers`（经度对齐） |
| `cli/` | `python -m cli` |
| `resource/conf.ini` | CLI 缺省 |
| `utils/` | `util_env`；并入共享 `00temp/utils`（`cli_base` / `base_plugin`） |
| `docs/` | 本文档 |
| `nbs/` | 说明与调用示例 Notebook |
| `test/` | 单元与示例 |

---

## 3. 接口约定

统一：`process(grd, sta)`。`grd` 为源六维场，`sta` 为目标站点表（至少含 `lon` / `lat`；`id` 等列保留）。

- 插值前三种方法均做经度预处理（`reset_lon_range`、`reset_global_griddata`）：对齐站/场经度约定，全球场补衔接列。
- 网格外站点由 `in_grid_xy` / `in_grid_xyz` 剔除；无有效站点时返回 `None`。
- `member` / `level` / `time` / `dtime` 展开为站点表行；数据列名为 `member` 坐标值。
- `attrs` 深拷贝自源场。

### 3.1 `InterpGsNearest`

对索引 `np.round` 取最近源格点赋值（固定水平）。

```python
from interp_gs_nearest_plugin import InterpGsNearest

result = InterpGsNearest().process(grd, sta)
```

### 3.2 `InterpGsLinear`

水平双线性四邻点加权。

| 参数 | 位置 | 默认 | 说明 |
| --- | --- | --- | --- |
| `used_coords` | 构造 | `"xy"` | `"xy"` / `"xyz"` / `"xydt"` |
| `grd` | `process` | — | 源格点场 |
| `sta` | `process` | — | 目标站点（`xydt` 须含有效 `dtime`） |

`"xydt"`：水平双线性后再对站点自身 `dtime` 线性插值（源场 `dtime` 维 ≥ 2）。已修复原 `interpolating.py` 中 `coords_g` 误用 `(ndtime, nlat, nlat)` 的缺陷，并改为与 `xyz` 同构的可分离线性，不再使用 `LinearNDInterpolator`。

```python
from interp_gs_linear_plugin import InterpGsLinear

result = InterpGsLinear().process(grd, sta)
result_dt = InterpGsLinear(used_coords="xydt").process(grd, sta)
```

### 3.3 `InterpGsCubic`

水平双三次，邻域 `p,q ∈ {-1,0,1,2}`，边界钳制（固定水平）。

```python
from interp_gs_cubic_plugin import InterpGsCubic

result = InterpGsCubic().process(grd, sta)
```

---

## 4. CLI

在本包目录执行：

```bash
python -m cli --module linear --grid resource/2026100900.024.nc --sta resource/2026100900.024_sta.csv
python -m cli --module nearest --grid resource/2026100900.024.nc --sta resource/2026100900.024_sta.csv --output out.csv
python -m cli --module cubic --grid resource/2026100900.024.nc --sta resource/2026100900.024_sta.csv --output out.m3
```

| 参数 | 说明 |
| --- | --- |
| `--module` | `linear` / `nearest` / `cubic` |
| `--grid` / `--sta` | 源格点、目标站点（必填，或写在 ini） |
| `--grid-type` / `--sta-type` | `nc`\|`m4`，`csv`\|`m3`；可按扩展名推断 |
| `--used-coords` | 仅 `linear`：`xy`/`xyz`/`xydt` |
| `--output` / `--output-type` | 可选写出站点；格式按扩展名或显式指定 |
| `--config` | 可选替换 `resource/conf.ini` |

取值优先级：命令行 > ini 非空项 > 预设。
