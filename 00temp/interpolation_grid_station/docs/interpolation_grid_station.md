# interpolation_grid_station 算法说明

将源格点场插值到站点位置。面向 `meteva_base` 六维场（`member, level, time, dtime, lat, lon`）。

水平 `xy` 与 `meteva_base.interp_gs_nearest` / `interp_gs_linear` / `interp_gs_cubic` 对齐，封装为 `PostProcessingPlugin`。对外推荐统一入口 `InterpGs(method=...)`。

---

## 1. 插件一览

| 插件 | 功能简介 |
| --- | --- |
| `InterpGs` | 格点→站点插值**统一入口**：`method=linear|nearest|cubic` |
| `InterpGsNearest` | 格点→站点最近邻；索引四舍五入 |
| `InterpGsLinear` | 格点→站点双线性；`xy` / `xyz` / `xydt` |
| `InterpGsCubic` | 格点→站点双三次；三次卷积核加权 |

---

## 2. 目录结构

| 路径 | 内容 |
| --- | --- |
| `src/` | 插件与 `gs_helpers`（经度对齐） |
| `cli/` | `interpolation_grid_station_cli.py`（`@merge_params` `process`）；`python -m interpolation_grid_station` / `python -m cli` |
| `resource/conf.ini` | CLI 缺省 |
| `utils/` | 包内工具；并入共享 `00temp/utils`（`merge_params` / `base_plugin`） |
| `docs/` | 本文档 |
| `nbs/` | 说明与调用示例 Notebook |
| `test/` | 单元与示例（含与 `meb.interp_gs_*` 的 `xy` 对照） |

---

## 3. 接口约定

统一：`process(grd, sta)`。`grd` 为源六维场，`sta` 为目标站点表（至少含 `lon` / `lat`；`id` 等列保留）。

- 插值前三种方法均做经度预处理（`reset_lon_range`、`reset_global_griddata`）：对齐站/场经度约定，全球场补衔接列。
- 网格外站点由 `in_grid_xy` / `in_grid_xyz` 剔除；无有效站点时返回 `None`。
- `member` / `level` / `time` / `dtime` 展开为站点表行；数据列名为 `member` 坐标值。
- `attrs` 深拷贝自源场。
- 水平 `xy`：与 `meb.interp_gs_*` 数值一致（见 `test/test_gs_plugins.py` 的 `test_match_meb_xy`）。

### 3.1 `InterpGs`（统一入口）

对外推荐经本入口调用；按 `method` 分派到 Linear / Nearest / Cubic。未用于当前 `method` 的参数忽略。CLI 的 `method=` 亦经本入口。

| 参数 | 位置 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `method` | 构造 | 是 | `linear` | `linear` / `nearest` / `cubic` |
| `used_coords` | 构造 | 否 | `"xy"` | 仅 `linear`：`xy` / `xyz` / `xydt` |
| `grd` | `process` | 是 | — | 源格点场 |
| `sta` | `process` | 是 | — | 目标站点 |

```python
from interp_gs_plugin import InterpGs
import meteva_base as meb

grd = meb.read_griddata_from_nc("source.nc")
sta = meb.read_stadata_from_csv("stations.csv")
result = InterpGs(method="linear", used_coords="xy").process(grd, sta)
# nearest / cubic：
# InterpGs(method="nearest").process(grd, sta)
# InterpGs(method="cubic").process(grd, sta)
```

各算法插件仍可单独使用（见下）。

### 3.2 `InterpGsNearest`

对索引 `np.round` 取最近源格点赋值（固定水平）。对齐 `meb.interp_gs_nearest`。

```python
from interp_gs_nearest_plugin import InterpGsNearest

result = InterpGsNearest().process(grd, sta)
# 等价：InterpGs(method="nearest").process(grd, sta)
```

### 3.3 `InterpGsLinear`

水平双线性四邻点加权。`used_coords="xy"` 时对齐 `meb.interp_gs_linear`。

| 参数 | 位置 | 默认 | 说明 |
| --- | --- | --- | --- |
| `used_coords` | 构造 | `"xy"` | `"xy"` / `"xyz"` / `"xydt"` |
| `grd` | `process` | — | 源格点场 |
| `sta` | `process` | — | 目标站点（`xydt` 须含有效 `dtime`） |

- `"xy"`：仅水平双线性。
- `"xyz"`：再叠一层高度线性（站点须含高度信息，并由 `in_grid_xyz` 筛选）。
- `"xydt"`：水平双线性后再对站点自身 `dtime` 线性插值（源场 `dtime` 维 ≥ 2）；本包实现为与 `xyz` 同构的可分离线性。

```python
from interp_gs_linear_plugin import InterpGsLinear

result = InterpGsLinear().process(grd, sta)
result_dt = InterpGsLinear(used_coords="xydt").process(grd, sta)
# 等价：InterpGs(method="linear", used_coords="xydt").process(grd, sta)
```

### 3.4 `InterpGsCubic`

水平双三次，邻域 `p,q ∈ {-1,0,1,2}`，边界钳制（固定水平）。对齐 `meb.interp_gs_cubic`。

```python
from interp_gs_cubic_plugin import InterpGsCubic

result = InterpGsCubic().process(grd, sta)
# 等价：InterpGs(method="cubic").process(grd, sta)
```

---

## 4. CLI

`process` 挂 `@merge_params()`，参数优先级：显式 `key=value` / `process(...)` > `config=` 指定的输入 ini > `resource/conf.ini` 非空项 > 签名预设。`resource/conf.ini` 键名与 `process` 形参一一对应。

`method` 选 `linear` / `nearest` / `cubic`（不用 `module`，避免与 `nimm_cli` 占用键冲突）。`grid` / `sta` 必填；包内相对路径按包根解析。`used_coords` 仅 `linear` 生效（其它 method 忽略）。

```bash
# 在 00temp 目录执行（包根入口）
python -m interpolation_grid_station method=linear grid=resource/2026100900.024.nc sta=resource/2026100900.024_sta.csv
python -m interpolation_grid_station method=nearest grid=resource/2026100900.024.nc sta=resource/2026100900.024_sta.csv output=out.csv
python -m interpolation_grid_station method=cubic grid=resource/2026100900.024.nc sta=resource/2026100900.024_sta.csv output=out.m3
python -m interpolation_grid_station method=linear grid=a.nc sta=sta.csv used_coords=xydt

# 在本包目录也可用 python -m cli key=value ...
python -m cli method=linear grid=resource/2026100900.024.nc sta=resource/2026100900.024_sta.csv
```

| 参数 | 说明 |
| --- | --- |
| `method` | `linear` / `nearest` / `cubic` |
| `grid` / `sta` | 源格点、目标站点（必填，或写在 ini） |
| `grid_type` / `sta_type` | `nc`\|`m4`，`csv`\|`m3`；可按扩展名推断 |
| `used_coords` | 仅 `linear`：`xy`/`xyz`/`xydt`（其它 method 忽略） |
| `output` / `output_type` | 可选写出站点；格式按扩展名或显式指定 |
| `config` | 可选替换 `resource/conf.ini` |

---

## 5. 选型与注意

1. **等距经纬格点→站点**：优先 `InterpGs(method="linear"|"nearest"|"cubic")`。
2. **含高度 / 时效维**：`method="linear"` 且 `used_coords="xyz"` / `"xydt"`。
3. 网格外站点会被剔除；无有效站点时返回 `None`。
4. 水平 `xy` 与 `meb.interp_gs_*` 对照一致；独立插件与 `InterpGs(method=...)` 等价。
5. 依赖：`meteva_base`、`numpy`、`pandas`、包内 / 共享 `utils.base_plugin`。

说明 Notebook：`nbs/interpolation_grid_station_说明.ipynb`。
