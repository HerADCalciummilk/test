# 气温地形降尺度(三维插值)

## 基本信息

- 算法名称：`orographic_nwp_3d_downscaling`
- 原始工程名：`nimm_g_interp` / `g_interp_zxq`
- 算法类型：`00space_downscale`
- 贡献人：曾晓青、丰硕、赵如奇
- 原始路径：`D:\temp\202301_zhinengwangge\20230206_unitycode\NIMM_pip_repos\TEMP\260625\g_interp_zxq`

## 算法功能

该算法封装快速精细化插值流程，基于模式场、地形、站点或格点配置执行近地面气象要素的细网格或站点三维插值，并支持最优参数求解。当前包装入口将原始 `g_interp` 业务流程整理为 `FastRefineInterpPlugin.process()` 和命令行调用方式。

## 目录说明

- `src/`：核心算法源码，包含 `fast_refine_interp.py`、插件包装 `fast_refine_interp_plugin.py` 以及 `core/` 中的原始业务模块。
- `cli/`：命令行入口 `fast_refine_interp.py`。
- `resource/`：最小样例配置模板 `sample_minimal/`，其中路径为占位路径，运行前需替换为真实业务路径。
- `test/`：最小插件构造测试。
- `nbs/`：当前无 notebook，保留规范目录。
- `docs/`：原始说明文档及本整理说明。
- `utils/`：保留规范目录，当前仅包含初始化文件。

## 插件入口

公开插件类为：

```python
from nimm_g_interp.src.fast_refine_interp_plugin import FastRefineInterpPlugin
```

主要参数包括 `work_dir`、`root_path`、`model_region`、`operation`、`resolution`、`begin_date`、`para_file`、`s3_method` 和 `site_name`。

## CLI 示例

```powershell
python -m nimm_g_interp.cli.fast_refine_interp `
  --work-dir D:\sample\EC_12P5KM `
  --root-path D:\sample `
  --model-region EC_12P5KM `
  --resolution site `
  --operation i `
  --begin-date 2026062508
```

## 依赖与运行条件

完整业务运行依赖真实模式资料、实况资料、地形数据、站点文件、`Parameter` 配置目录以及原始工程的二进制扩展 `Module_Micaps_RW.so`。`resource/sample_minimal/` 仅提供最小配置模板，不能替代完整业务数据。

## 当前限制

- 导入路径仍使用原始 `nimm_g_interp` 包名；当前中间目录名为 `orographic_nwp_3d_downscaling`，正式入库时需统一包名和导入路径。
- 原始代码依赖业务目录结构和配置文件，未提供可完整运行的独立样例数据。
- `Module_Micaps_RW.so` 为二进制扩展，可能受 Python 版本、系统平台和编译环境限制。
- 当前仅做中间整理，尚未完成完整业务运行验证。
