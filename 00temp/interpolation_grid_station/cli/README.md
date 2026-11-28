# CLI

在本包目录执行：

```bash
python -m cli method=linear grid=resource/2026100900.024.nc sta=resource/2026100900.024_sta.csv
python -m cli method=nearest grid=resource/2026100900.024.nc sta=resource/2026100900.024_sta.csv output=out.csv
python -m cli method=cubic grid=resource/2026100900.024.nc sta=resource/2026100900.024_sta.csv output=out.m3
```

在 `00temp` 目录亦可用：`python -m interpolation_grid_station method=linear grid=... sta=...`。

未给出的项读 `resource/conf.ini`，再没有则用签名预设。`grid` / `sta` 在 ini 中留空时必须由命令行传入。经统一入口 `InterpGs(method=...)` 调用。
