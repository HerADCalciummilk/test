**基础信息**
- **所属包**: `interpolation_station_grid`
- **插件页**: [interpolation_station_grid](https://www.showdoc.com.cn/2598854776811541/11559060627552458)
- **调度脚本**: `cli/interpolation_station_grid_cli.py`

本页是 CLI 使用说明；算法参数见插件页。样例为包内阵风站点 + `bg_fcst_idw` 背景（约 0.1°）。本包以单次 `method=...` 调用为主，无批量调度节。

**参数优先级**（由高到低）：**显式传入**（命令行 `key=value` / `process(key=...)`）**>** **输入配置文件**（`config=` 指定的 ini 非空项）**>** **默认配置** `resource/conf.ini` 非空项 **>** 签名预设。空 ini 项不覆盖上层已给出的值。

**怎么跑**

（发版环境：本包已可导入。）

```bash
# 在 00temp 目录执行（包根入口，解析 key=value）
# key 与 process 形参名相同；无 [] 的为必填，[] 内为可选
# grid 与 background 至少其一；reprocess=true 时须 background
python -m interpolation_station_grid method={idw|gaussian|kriging|cressman} sta=PATH [grid=PATH] [background=PATH] \
  [reprocess=true|false] [idw_gaussian=true|false] [output=PATH] \
  [idw_effect_r=N] [idw_near_num=N] [idw_decrease=N] \
  [gaussian_half_r=N] \
  [kriging_model=spherical|exponential|gaussian] [kriging_near_num=N] \
  [kriging_sill=N] [kriging_range=N] [kriging_nugget=N] \
  [cressman_r_list=R1,R2,...] [cressman_near_num=N] \
  [cressman_rain_limit=X] [cressman_degree_blend=0~1] [cressman_num_limit=N] [cressman_smooth=X] [cressman_power_param=X] \
  [cressman_r_km_scale=X] [cressman_innov_gain=X] [cressman_residual_passes=N] \
  [cressman_residual_degree_polish=true|false] [cressman_residual_polish_rounds=N] \
  [cressman_station_anchor_radius=X] [cressman_station_anchor_strength=X] \
  [sta_type=csv|m3] [grid_type=nc|m4] [background_type=nc|m4] [output_type=nc|m4] [config=PATH]

# 示例
python -m interpolation_station_grid method=idw sta=resource/obs_gust_d24.csv background=resource/bg_fcst_idw.nc reprocess=true output=resource/out.nc
```

`method` 省略则读 ini，预设 `idw`（仅支持 `idw` / `gaussian` / `kriging` / `cressman`）。`sta` 必填；`grid` / `background` 至少其一。有 `output` 则写格点 nc/m4；否则只 `print` 结果。包内相对路径按包根解析。`process` 返回插值结果格点场 `xarray.DataArray`。

在本包目录也可用 `python -m cli key=value ...`（无参数时读 `conf.ini` 与签名预设）。

| 子命令 | 脚本 | 说明 |
| --- | --- | --- |
| 包根 `python -m interpolation_station_grid` | `cli/interpolation_station_grid_cli.py` | `method=idw` / `gaussian` / `kriging` / `cressman` |

# interpolation_station_grid_cli

**调用插件**: `InterpSg`（由 `method=` 选择 `idw` / `gaussian` / `kriging` / `cressman`）

Python 入口为 `process`（关键字与命令行 `key` 同名）。未传入的可选项为 `None`，按参数优先级回落。

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">process(<br>&nbsp;&nbsp;&nbsp;&nbsp;method="idw",<br>&nbsp;&nbsp;&nbsp;&nbsp;reprocess=False,<br>&nbsp;&nbsp;&nbsp;&nbsp;outer&#95;value=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;sta=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;grid=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;background=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;sta&#95;type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;grid&#95;type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;background&#95;type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output&#95;type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;idw&#95;effect&#95;r=1000,<br>&nbsp;&nbsp;&nbsp;&nbsp;idw&#95;near&#95;num=8,<br>&nbsp;&nbsp;&nbsp;&nbsp;idw&#95;decrease=2,<br>&nbsp;&nbsp;&nbsp;&nbsp;idw&#95;gaussian=False,<br>&nbsp;&nbsp;&nbsp;&nbsp;gaussian&#95;half&#95;r=20,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging&#95;model="spherical",<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging&#95;near&#95;num=20,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging&#95;sill=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging&#95;range=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging&#95;nugget=0.0,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;r&#95;list=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;near&#95;num=100,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;rain&#95;limit=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;num&#95;limit=1.0,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;smooth=0.001,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;power&#95;param=2.0,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;r&#95;km&#95;scale=1.35,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;innov&#95;gain=1.0,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;residual&#95;passes=0,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;residual&#95;degree&#95;polish=True,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;residual&#95;polish&#95;rounds=1,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;degree&#95;blend=0.85,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;station&#95;anchor&#95;radius=0.35,<br>&nbsp;&nbsp;&nbsp;&nbsp;cressman&#95;station&#95;anchor&#95;strength=0.0,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">method</span> | 选择插值算法，仅支持 `idw` / `gaussian` / `kriging` / `cressman`。省略读 ini，预设 `idw` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">sta</span> | 输入**站点场**路径（csv/m3）。读入后交给插件作观测源；必填（或由 ini 提供） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">grid</span> | 输入格点文件路径（nc/m4）。CLI **只取网格信息**传给插件，场值不参与插值。可与 `background` 二选一以提供网格；两者都缺则报错 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">background</span> | 输入**背景格点场**路径（nc/m4）。`reprocess=true` 时必需。`false` 时：IDW/Gaussian/Cressman 作远点填充或初场，Kriging 仅在缺 `grid` 时取网格。无 `grid` 时也可单独提供网格 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">reprocess</span> | `false`：绝对值插值（背景可作远点填充）；`true`：偏差再插值。与 `gaussian` 相互独立 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">idw_gaussian</span> | 仅 `idw`：是否乘高斯核，默认 `false`；不随 `reprocess` 自动开启 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">outer_value</span> | 背景对齐越界填充值，默认 `None`（ini 留空） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">output</span> | 可选输出格点路径；给出则写 nc/m4；省略则仅 `print` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">idw_effect_r</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">idw_near_num</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">idw_decrease</span> | 仅 `idw`：影响半径（千米）、近邻数、距离衰减指数 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">gaussian_half_r</span> | 仅 `gaussian`：高斯半径（千米） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">cressman_r_list</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">cressman_near_num</span> | 仅 `cressman`：影响半径列表（逗号分隔；默认留空，由插件按 `reprocess` 选默认：`false` 为 `60,40,20` 千米，`true` 为 `1.0,0.8,0.6,0.4` 度）；近邻数 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">cressman_rain_limit</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">cressman_degree_blend</span> 等 | 仅 `cressman` 且 `reprocess=true`：降水回退阈值（留空不回退）、创新量扫与纯度制结果的融合权重 `[0,1]`（`1.0` 为纯度制）；另有 `cressman_num_limit`、`cressman_smooth`、`cressman_power_param`、`cressman_r_km_scale`、`cressman_innov_gain`、`cressman_residual_passes`、`cressman_residual_degree_polish`、`cressman_residual_polish_rounds`、`cressman_station_anchor_radius`、`cressman_station_anchor_strength`，预设与 `InterpSgCressman` 一致；rain24 original 形态用 `cressman_degree_blend=1.0 cressman_rain_limit=0.01` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">kriging_model</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">kriging_near_num</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">kriging_sill</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">kriging_range</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">kriging_nugget</span> | 仅 `kriging`：变异函数、近邻数、基台、变程、块金 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">sta_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">grid_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">background_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">output_type</span> | 格式；省略按扩展名 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">config</span> | 输入配置 ini（优先级高于默认 `conf.ini`，低于显式参数） |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | 插值结果格点场 `xarray.DataArray`（若给定 `output` 同时写盘） |

说明：`idw` 是否偏差订正由 `reprocess` 控制，是否乘高斯核由 `idw_gaussian` 控制，二者独立。

**使用示例**

包内真实样例：站点 `resource/obs_gust_d24.csv`、目标网格 `resource/target_grid.nc`、背景 `resource/bg_fcst_idw.nc`。`process` 直接返回插值结果格点场并写盘；展示输入站点与 **订正前/订正后** 对照（共用 `wind_speed` 色标）。

```python
from pathlib import Path
import matplotlib.pyplot as plt
import meteva_base as meb
import numpy as np
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name
from cli.interpolation_station_grid_cli import process

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 在 00temp 目录运行；resolve() 为绝对路径，避免被 CLI 按包根再解析一次
PKG = Path("interpolation_station_grid/resource").resolve()
DEMO = PKG / "showdoc_demo"
sta_path = str(PKG / "obs_gust_d24.csv")
grid_path = str(PKG / "target_grid.nc")
bg_path = str(PKG / "bg_fcst_idw.nc")
out_path = str(DEMO / "cli_idw_bg_out.nc")

# 写盘并返回结果格点场：IDW 偏差订正
grd = process(
    method="idw",
    sta=sta_path,
    grid=grid_path,
    background=bg_path,
    reprocess="true",
    output=out_path,
    idw_effect_r=150,
    idw_near_num=8,
    idw_decrease=2,
    sta_type="csv",
    grid_type="nc",
    background_type="nc",
    output_type="nc",
)
print(grd)
```

```
<xarray.DataArray 'data0' (member: 1, level: 1, time: 1, dtime: 1, lat: 71,
                           lon: 210)> Size: 60kB
array([[[[[[14.653, 13.959, 13.871, ..., 12.191, 12.223, 12.262],
           [14.89 , 14.231, 14.153, ..., 12.085, 12.125, 12.173],
           [15.166, 15.117, 14.501, ..., 11.965, 12.015, 12.073],
           ...,
           [14.582, 14.639, 14.711, ..., 15.565, 15.692, 15.815],
           [14.636, 15.338, 15.363, ..., 15.811, 15.893, 15.981],
           [15.458, 15.474, 15.503, ..., 16.033, 16.084, 16.142]]]]]],
      shape=(1, 1, 1, 1, 71, 210), dtype=float32)
Coordinates:
  * member   (member) <U5 20B 'data0'
  * level    (level) float32 4B 0.0
  * time     (time) datetime64[ns] 8B 2026-06-02
  * dtime    (dtime) int32 4B 24
  * lat      (lat) float64 568B 31.54 31.64 31.74 31.84 ... 38.34 38.44 38.54
  * lon      (lon) float64 2kB 99.6 99.7 99.8 99.9 ... 120.2 120.3 120.4 120.5
Attributes:
    units:               
    model_var:           
    dtime_units:         hour
    level_type:          isobaric
    time_type:           UT
    time_bounds:         [np.int64(0), np.int64(0)]
    data_start_columns:  6
```

```python
bg = meb.read_griddata_from_nc(bg_path)
obs = meb.read_stadata_from_csv(sta_path)
cmap, clevs = get_cmap_and_clevs_by_element_name("wind_speed")
clevs = np.asarray(clevs, dtype=float)
map_extend = [float(bg.lon.min()), float(bg.lon.max()), float(bg.lat.min()), float(bg.lat.max())]

# 输入站点
axs = meb.creat_axs(1, map_extend, ncol=1, height=6.5, width=12, dpi=120,
                    title_list=["输入-站点阵风 obs_gust"])
meb.add_scatter(axs[0], obs, cmap=cmap, clevs=clevs, point_size=28, add_colorbar=True,
                title="输入-站点阵风 obs_gust", title_fontsize=12)
plt.savefig("cli_obs_sta.png", dpi=120, bbox_inches="tight"); plt.close("all")

# 订正前 / 订正后对照（同一色标）
axs = meb.creat_axs(
    2, map_extend, ncol=2, add_index=True, add_worldmap=False,
    title_list=["订正前-背景场", "订正后-CLI InterpSgIdw"],
)
meb.add_contourf(axs[0], bg, cmap=cmap, clevs=clevs, cut_colorbar=False, add_colorbar=True)
meb.add_contourf(axs[1], grd, cmap=cmap, clevs=clevs, cut_colorbar=False, add_colorbar=True)
axs[0].set_title("订正前-背景场")
axs[1].set_title("订正后-CLI InterpSgIdw")
plt.savefig("cli_compare.png", dpi=120, bbox_inches="tight"); plt.close("all")
```

![输入-站点阵风](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=3954ae98c0bf50869a8984a7c4f959bf&file=file.png)

![订正前-背景场 / 订正后-CLI](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=4f54fdcf926fc824bc596f12565411cf&file=file.png)

---

插件说明请见 [interpolation_station_grid](https://www.showdoc.com.cn/2598854776811541/11559060627552458)。
