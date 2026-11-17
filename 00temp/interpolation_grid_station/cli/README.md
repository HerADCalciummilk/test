# CLI

在本包目录执行：

```bash
python -m cli --module linear --grid resource/2026100900.024.nc --sta resource/2026100900.024_sta.csv
python -m cli --module nearest --grid resource/2026100900.024.nc --sta resource/2026100900.024_sta.csv --output out.csv
python -m cli --module cubic --grid resource/2026100900.024.nc --sta resource/2026100900.024_sta.csv --output out.m3
```

未给出的项读 `resource/conf.ini`，再没有则用预设。`grid` / `sta` 在 ini 中留空时必须由命令行传入。
