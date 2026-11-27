# resource

东南沿海降水个例，2026-07-27～29，域 105–122°E、18–31°N。`cli/preprocess_ec_oe_inputs.py` 把 `EC/` 插到离地约 1000 m，写到 `data/`。

| 目录 | 用途 |
| --- | --- |
| `EC/` | EC 原场：气压层与近地面温湿风，以及逐时降水 |
| `CMPAS_APCP/` | 逐时实况 |
| `ancil/` | 模式地形和 1 km 地形 |
| `data/` | 预处理后算法直接读的离地约 1000 m 温湿压风 |
| `data/output/` | 本机结果。`crop_101_123E_20_38N/` 是批量调度用的子域输入；其余是订正场、图和检验 |

调用尝试用的小样例在包根 `test_data/sample/`（101–110°E、28–38°N）。级联插件不读其中的 5 km 地形；分步重分配的 5 km 档用它。`test_data/orographic_enhancement_data/` 是 IMPROVER 官方对照样例，不是这套区域个例。
