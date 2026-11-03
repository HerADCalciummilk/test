# utils

`util_env.py` 读取 `resource/blend.ini`，缺项再用代码预设。融合计算在 `src/weight_blending.py`。

本目录和 NIMM 环境里的 `utils.cube_checker` 不是同一个包。在本目录执行融合类时，需要让外部 `utils.cube_checker` 仍能被导入。
