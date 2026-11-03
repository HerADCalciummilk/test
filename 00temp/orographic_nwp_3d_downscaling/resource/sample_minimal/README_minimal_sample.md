# 最小样例配置说明

本目录保留原 `g_interp` 工程提供的最小 `site` 插值配置模板，目标是帮助业务侧先准备一套可运行目录。

推荐先使用如下配置组合：

```text
operation = i
resolution = site
PQ_shortname = 2t
Interp_Time = False
Interp_Maxmin = False
validate = False
```

## 已提供的模板文件

```text
sample_minimal/Fast_refine_interp_site.ini
sample_minimal/Parameter/Global_Info.ini
sample_minimal/Parameter/Obs_Info.ini
sample_minimal/Parameter/Mdl_Obs_Path_Info.ini
sample_minimal/Parameter/Station1
sample_minimal/Parameter/EC/EC_12P5KM_Info.ini
```

这些模板中的 `D:/sample/...` 都是占位路径，实际运行前需要替换为真实数据路径。

## 运行时需要的真实数据

1. 模式 NetCDF 数据。

   最小 `2t` 插值建议准备 `2t`、`t`、`gh`、`sp`。其中 `t`、`gh`、`sp` 用于垂直订正和近地面诊断。

2. 模式地形数据。

   需要在业务根目录的 `lib/terrain/<MODEL_REGION>/` 下提供 `Terrain_*.tif`；如有分区文件，还可提供 `Zoning_*.tif`。

3. 站点文件。

   模板中的 `Parameter/Station1` 可作为格式参考，站点经纬度需要落在模式范围内。

4. 实况数据。

   当 `operation=i` 且 `validate=False` 时，最小样例可以暂不准备实况。若执行求参、检验或格点实况订正，则需要配置真实实况路径。

## 新版调用方式

改造后不再要求当前目录名必须是 `EC_12P5KM`。可以通过 CLI 显式指定：

```text
python -m nimm_g_interp.cli.fast_refine_interp ^
  --work-dir D:/path/to/business/EC_12P5KM ^
  --root-path D:/path/to/business ^
  --model-region EC_12P5KM ^
  --para-file Fast_refine_interp_site.ini ^
  --resolution site ^
  --operation i ^
  --begin-date 2025010100
```

完整运行仍依赖真实业务数据和路径配置。
