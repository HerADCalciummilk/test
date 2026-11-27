# resource

气温个例，2026-10-10～24。`cli/crop_common_domain.py` 把 EC、实况和地形裁到公共域 71–139°E、16–59°N，写到 `data/common_domain/`。

| 目录 | 用途 |
| --- | --- |
| `data/ec_tmp2m/` | EC 2 m 温度原场，2026-10-10～24 各一个时次 |
| `data/hrcldas_tair/` | HRCLDAS 气温实况 |
| `data/ancil/` | 模式地形、1 km 地形和海陆掩膜 |
| `data/common_domain/` | 裁到公共域后的同一套输入，其中气温在 `ec_tmp2m/`。`output/` 是本机订正结果、递减率和图 |
| `sample/` | 调用尝试用的小样例，103–108°E、28–33°N |
| `cli_input/` | 官方 UKVX 冒烟输入，不是这套区域个例 |
| `cli_output/` | 冒烟命令写出的结果 |

`python -m cli` 的冒烟入口读 `cli_input/`，写出 `cli_output/`。
