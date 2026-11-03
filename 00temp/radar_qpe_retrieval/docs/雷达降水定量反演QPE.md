# 雷达降水定量反演QPE

## 基本信息

- 算法名称：`radar_qpe_retrieval`
- 原始路径：`D:\workspace\pyart_nimm\qpe`
- 算法类型：`01obs_adustment`
- 贡献人：郭云谦、王亭波

## 算法功能

该算法从 Py-ART 的定量降水估算逻辑迁移而来，面向雷达网格数据执行 QPE 降水率反演。算法以 `meteva_base.grid_data` 风格的 `xarray.DataArray` 为输入输出，支持反射率、KDP、比衰减和水凝物分类等多种雷达变量，输出降水率网格，通常单位为 `mm/h`。

## 主要方法

- `est_rain_rate_z`：基于反射率和幂律 Z-R 关系估算降水率。
- `est_rain_rate_zpoly`：基于反射率多项式经验关系估算降水率。
- `est_rain_rate_kdp`：基于 KDP 估算降水率。
- `est_rain_rate_a`：基于比衰减估算降水率。
- `est_rain_rate_zkdp`：融合反射率和 KDP 估算降水率。
- `est_rain_rate_za`：融合反射率和比衰减估算降水率。
- `est_rain_rate_hydro`：结合水凝物分类、反射率和比衰减估算降水率。
- `ZtoR`：使用经典 `Z = aR^b` 关系反算降水率。

## 目录说明

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/qpe.py` | QPE 插件与算法函数 |
| 内部工具 | `src/utils/_freq.py`、`src/utils/_grid.py` | 频率系数与网格重组装 |
| 模块工具 | `utils/grid_gate_filter.py` | 门控过滤 |
| 插件基类 | `utils/base_plugin.py` | PostProcessingPlugin |
| CLI | `cli/qpe.py` | QPE 统一入口 |
| CLI 辅助 | `cli/cinrad_meb.py`、`cli/cinrad_pyart_prep.py` | CINRAD 读数与预处理 |
| 测试 | `test/` | 单元测试、插件、CLI、门控过滤 |
| 文档 | `docs/qpe.md` | 原始算法说明 |
| notebook | `nbs/qpe.ipynb` | 示例 |
| 资源 | `resource/` | 仅说明；样例在独立 testdata / 原目录 |

## 插件入口

统一插件类 `QPEPlugin`（`src/qpe.py`），通过 `method` 参数选择 `z`、`zpoly`、`kdp`、`a`、`zkdp`、`za`、`hydro`、`ztor` 等方法。

## 当前整理状态

当前阶段为原始算法整理至中间目录，尚未补充至正式算法仓库目录。

已完成：

- 自 `D:\workspace\pyart_nimm\qpe` 同步 src/、utils/、cli/、test/、docs/、nbs/（2026-07-13）。
- 导入路径已统一为中间目录模块名 `radar_qpe_retrieval`。
- 移除旧中间目录中 echo_class 等无关文件。
- 建立算法内 00log/、00temp/、NIMM_list.md、.gitignore。

待处理：

- 补充至 NIMM/01obs_adustment/ 时需将导入路径调整为仓库正式包路径。
- test_data 体量较大，正式入库前建议筛选必要小样例。
- resource/ 当前为空，正式补充时确认是否保留。
