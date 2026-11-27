# utils

`util_env.py` 是旧的 ini 读取实现（默认读 `resource/conf.ini`，缺项再用代码预设），目前只有 `test/test_db_trans.py` 引用，CLI 不使用它。

CLI 的参数合并由共享的 `utils.merge_params` 完成，优先级为：显性参数 > `config=` 指向的输入 ini > `resource/conf.ini` > `process` 签名默认值。

降水强度变换的实现在 `src/db_trans_plugin.py`（`DbTransPlugin`）。
