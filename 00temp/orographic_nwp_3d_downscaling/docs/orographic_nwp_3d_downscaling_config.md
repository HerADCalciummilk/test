# 配置与运行说明

## 插件

```python
from cli.orographic_nwp_3d_downscaling_cli import process

process(
    root_path="/path/to/orographic_nwp_3d_downscaling",
    work_dir="/path/to/orographic_nwp_3d_downscaling/resource",
    para_file="Fast_refine_interp_5km.ini",
    model_region="EC_12P5KM", resolution="5km", operation="i",
    begin_date="2026111813", debug=1, update=1,
)
```

`process` 先读配置、地形和目标点，再调用 `SpatialInterpPlugin`，写出 NetCDF，需要时再调用 `MaxMinPlugin`、`TimeInterpPlugin`。`BestEtaPlugin` 只返回 eta，由 `process` 写成 `{时效}_{要素}_eta.h5`。

`root_path` 支持新项目根目录、新resource目录，也兼容旧Parameter/lib资源根目录。旧布局使用旧运行配置时仍需提供相应work_dir。

## 生效配置

| 文件 | 用途 |
|---|---|
| resource/config/Global_Info.ini | 输出根目录和缺测值 |
| resource/config/Mdl_Obs_Path_Info.ini | 模式根目录、变量目录、时区和气压层 |
| resource/config/EC/EC_12P5KM_Info.ini | 模式区域、输入声明、层次和可用时效 |
| resource/config/Obs_Info.ini | 目标网格定义；仅格点插值不要求观测数据存在 |
| resource/Fast_refine_interp_5km.ini | 输出要素、模式时效范围和功能开关 |

模式信息文件严格按固定行序解析，不要增加注释或空行。路径和层次须在两个模式配置中保持一致。新增多要素须核对输入依赖，尚未完成所有要素的业务验证。

`[ForecastHourRange] EC_12P5KM = 0,240` 表示包含两端，只计算模式时效列表与范围的交集；单时效测试设为 `6,6`。

## 输入输出

EC输入示例：`模式根/TMP_2M/2026/20261118/2026111800.006.nc`；高空示例：`模式根/TMP/900/2026/20261118/2026111800.006.nc`。

NetCDF输出启用时，正式结果为 `result/TMP_2M/2026/20261118/2026111800.006.nc`，要素目录复用输入映射，文件使用配置的时区（当前UTC）。`data0` 维度为member、level、time、dtime、lat、lon，近地面level标记为0。压力导出为Pa，温度为degC。

旧H5中间文件及gamma保留在 `result/.interp_cache`。当前只输出近地面产品，高空层是辅助输入，不会自动输出高空产品。NetCDF模式当前要求关闭时间插值和最大最小值功能。站点输出仍沿用旧流程。

## 时间与更新

begin_date是北京时间业务时间，不是结果有效时间。EC固定映射：01—12时取前一天20时，13—23时取当天08时，00时取前一天08时。不扫描最新完整文件、不自动回退。结果有效时间为所选起报加时效。

update=1重算；update=0复用已有H5并跳过已有NC。配置、算法或输入改变后应update=1或换输出目录，避免复用旧缓存。

## 环境与验证边界

实际业务模块依赖numpy、pandas、h5py、netCDF4、scipy、eccodes、meteva、rasterio等；部分绘图和旧功能还依赖其他包。推荐复用已跑通服务器的环境，并保存 `conda env export` 作为部署记录。不要在Windows加载Linux `.so`。

