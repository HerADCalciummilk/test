# 测试说明

`test_cli_config.py` 检查命令行参数是否先读 `resource/conf.ini`。

`test_interp_sg_facade.py` 测统一入口 `InterpSg(method=...)` 的分派与 IDW 结果一致性。

`test_interp.py`、`test_idw_delta.py`、`test_gaussian.py`、`test_cressman.py` 是原来放在 `nbs/` 的示例脚本，依赖外部站点 csv 和格点 nc，直接运行脚本才会执行。
