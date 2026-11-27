# 资源目录

`db_trans.ini` 是命令行运行配置。

源码主模块 `db_trans_plugin.DbTransPlugin` 对应 `cli/db_trans_cli.py`。在 `00temp` 下执行 `python -m db_trans key=value`，或 `python -m utils.nimm_cli db_trans key=value`。没写的参数先读配置，没有再用代码预设。`method=summary` 只列出可用变换。
