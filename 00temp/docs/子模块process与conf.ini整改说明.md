# 子模块 `process` / `conf.ini` 整改说明

各子模块主入口统一为 `process`，默认配置统一为包内 `resource/conf.ini`，并可传 `config` 读取外部 ini。算法计算过程未改；默认配置内容与原默认 ini 一致时，不传 `config` 结果与改前相同。

## 总表

| 子模块 | 默认 `conf.ini` 来源 | 入口 `process` | `config` 外部配置 | 具体改动要点 |
|---|---|---|---|---|
| `00_blend` | 复制自 `blend.ini` | CLI 曾抽出，后撤回 | 已有 `set_main_ini` | 保留默认 ini 改指向 `conf.ini`；CLI 入口仍为 `run` |
| `00_forecast_time_split` | 复制自 `timesplit.ini` | CLI 曾抽出，后撤回 | 已有 | 三条命令默认 ini 改名；CLI 入口仍为 `run` |
| `coordinate_projection_transform` | 复制自 `projection.ini` | CLI 曾抽出，后撤回 | 已有 | 默认 ini 改名；CLI 入口仍为 `run` |
| `db_trans` | 复制自 `db_trans.ini` | CLI 曾抽出，后撤回 | 已有 | 默认 ini 改名；CLI 入口仍为 `run` |
| `frequency_matching_rain01` | 复制自 `qpf_fm.ini` | 原已有 | 原已有 | 仅默认路径改为 `conf.ini` |
| `frequency_matching_rain03` | 复制自 `qpf_fm.ini` | 原已有（含 `runner_bck`） | 主入口已有 | 主入口默认 ini 改名；`runner_bck` 未强改 |
| `frequency_matching_rain24` | 复制自 `optimize_tp_24.ini` | 原已有 + nowcast 补齐 | 主入口原有；nowcast 本次补齐 | 默认 ini 改名；`correct_tp_24h_nowcast.process` 增加 `config` |
| `fy4b_argi_l1_decoder` | 复制自 `fy4.ini` | src 入口保留；CLI 抽出撤回 | 已有 / src 补齐 | CLI 入口仍为 `run`；单文件/批量 src `process` 支持 `config` |
| `grid_stat_merge` | 复制自 `grid_stat_merge.ini` | 原已有 | 原已有 | 仅默认 ini 改名 |
| `gust_factor` | 复制自 `gust_factor.ini` | 原已有 | 原已有 | 仅默认 ini 改名 |
| `interp_gg_linear` | 复制自 `interp_gg_linear.ini` | 原已有 | 原已有 | 仅默认 ini 改名 |
| `interp_sg_cressman` | 复制自 `interp_sg_cressman.ini` | 原已有 | 原已有 | 仅默认 ini 改名 |
| `kalman_element_forecast_correction` | 复制自 `kalman.ini` | CLI 曾抽出，后撤回 | 已有 | 默认 ini 改名；CLI 入口仍为 `run`；`src/kalman_cli.process` 原样保留 |
| `multi_rain_mait01_blending` | 复制自 `mait_1.ini` | 原已有 | 原已有 | 仅默认 ini 改名 |
| `multi_rain_mait03_blending` | 复制自 `mait_3.ini` | 原已有 | 原已有 | 仅默认 ini 改名 |
| `multi_rain_mait24_blending` | 复制自 `mait_24.ini` | 原已有 | 原已有 | 仅默认 ini 改名 |
| `optical_flow_nowcast` | 复制自 `optical_flow.ini` | CLI 曾抽出，后撤回 | 已有 | 默认 ini 改名；CLI 入口仍为 `run`；插件类 `process` 原样保留 |
| `orographic_nwp_3d_downscaling` | 复制样例站点 ini | CLI 曾抽出，后撤回 | 已有 | 默认回落改为 `resource/conf.ini`；不传 `config` 时业务仍读工作目录 `para_file`；插件 `process` 原样保留 |
| `station_grid_fusion` | 复制自 `fusion.ini` | CLI 曾抽出，后撤回 | 已有 | 默认 ini 改名；CLI 入口仍为 `run` |
| `steps_multi_time_fusion` | 复制自 `steps.ini` | CLI 曾抽出，后撤回 | 已有 | 默认 ini 改名；CLI 入口仍为 `run` |
| `wind_fft_blending` | 复制自 `fft_merge.ini` | 原已有 | 原已有 | 仅默认 ini 改名 |
| `linear_scd_multi_time_fusion` | 复制自 `scd_pair_fusion_config.ini` | `pair`/`padding`/`split` 补 `process` | 本次补齐 | 融合/补齐默认读 `conf.ini`；拆分仍默认 `split_config.ini`，可用 `config` 覆盖 |
| `emos_probability_calibration` | 新建空 `[process]` | 原已有 | 本次补齐 | `process` 增加 `config`；空项不改算法默认 |
| `feels_like_temperature` | 新建空配置 | 原已有 | 本次补齐 | 同上 |
| `generate_ancillary` | 新建空配置 | 原已有（3 个 CLI） | 本次补齐 | 同上 |
| `generate_derived_solar_fields` | 新建空配置 | 原已有（2 个 CLI） | 本次补齐 | 同上 |
| `generate_orographic_smoothing_coefficients` | 新建空配置 | 原已有 | 本次补齐 | 同上 |
| `neighbourhood_probability_processing` | 新建空配置 | 原已有（3 个 CLI） | 本次补齐 | 同上 |
| `orographic_precipitation_downscaling` | 新建空配置 | 原已有 | 本次补齐 | 同上 |
| `orographic_temperature_downscaling` | 新建空配置 | 原已有（2 个 CLI） | 本次补齐 | 同上 |
| `orographic_wind_downscaling` | 新建空配置 | 原已有 | 本次补齐 | 同上 |
| `probability_reliability_correction` | 新建空配置 | 原已有（4 个 CLI） | 本次补齐 | 同上 |
| `radar_echo_classification` | 新建空配置 | 原已有（4 个 CLI） | 本次补齐 | 同上 |
| `radar_qpe_retrieval` | 新建空配置 | 原已有 | 本次补齐 | 同上 |
| `radar_wind_dealiasing` | 新建空配置 | 原已有（2 个 CLI） | 本次补齐 | 同上 |
| `regrid` | 新建空配置 | 原已有 | 本次补齐 | 同上 |
| `samos_probability_calibration` | 新建空配置 | 原已有 | 本次补齐 | 同上 |
| `simple_bias_correction` | 新建空配置 | 原已有（2 个 CLI） | 本次补齐 | 同上 |
| `station_height_difference_correction` | 新建空配置 | 原已有（2 个 CLI） | 本次补齐 | 同上 |
| `threshold_probability_conversion` | 新建空配置 | 原已有 | 本次补齐 | 同上 |
| `weather_phenom_grid_12h` | 新建空配置 | 原已有 | 原有占位，本次真正可填 | `process` 用 `conf.ini` 只补仍为 `None` 的项 |

## 读表说明

1. **复制自旧 ini**：内容与原默认文件一致，只是默认路径改为 `resource/conf.ini`；旧文件仍可显式传入。
2. **新建空配置**：`[process]` 键默认留空，不覆盖代码默认值，不改变算法结果。
3. **算法核心计算未改**；本次只动入口命名、默认配置路径，以及 `config` 解析能力。
4. **CLI 抽出撤回**：原先没有模块级 `process` 入口、仅从 CliBase.`run` 机械抽出的包，已把逻辑折回 `run`，避免与插件类 `process` 或算法入口混淆。这些包仍保留 `resource/conf.ini` 与 `--config`。

## 撤回范围（从 CLI 抽出的假入口）

以下包的 CLI 文件不再保留“从 `run` 复制出来的模块级 `process`”，业务仍由 `run` / 原有算法 `process` 承担：

- `00_blend`
- `00_forecast_time_split`
- `coordinate_projection_transform`
- `db_trans`
- `fy4b_argi_l1_decoder`（仅 CLI；`src` 原有 `process` 保留）
- `kalman_element_forecast_correction`（仅 CLI；`src/kalman_cli.process` 保留）
- `optical_flow_nowcast`（仅 CLI；插件类 `process` 保留）
- `orographic_nwp_3d_downscaling`（仅 CLI；插件 `process` 保留）
- `station_grid_fusion`
- `steps_multi_time_fusion`
