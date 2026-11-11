# utils

`util_env.py` 读取 `resource/conf.ini`（及兼容的 timesplit.ini），缺项再用代码预设。

本包 `src/` 现有插件：`TimeSplit`。  
多时效读拼在上一级共用目录 `00temp/utils/grid_combine.py`（经本目录并入后以 `utils.grid_combine` 导入）：

- `read_multi_griddata`：同一起报，沿 `dtime`（`TimeSplit` CLI 读数）
- `concat_griddata`：通用拼接
