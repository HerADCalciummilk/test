# 资源目录

`conf.ini` 是命令行运行配置（等经纬度 ↔ 等距）。

在本包目录执行 `python -m cli`。没写的参数先读这里，配置里也没有再用代码预设。

- `mode=lonlat-to-equal`：等经纬度 → 等距
- `mode=equal-to-lonlat`：等距 → 等经纬度
- `backend=cartopy`（默认）/ `iris`：选实现

`sample/2026052400.036.m4`：iris vs cartopy 对比用等经纬度样例（供 `test/compare_iris_cartopy_m4.py`）。
