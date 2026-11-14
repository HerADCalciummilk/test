# CLI

在本包目录执行 `python -m cli`。用 `--module` 选择 `linear`、`nearest`、`cubic`。
分别走 `InterpGgLinear` / `InterpGgNearest` / `InterpGgCubic`。
目标网格须提供 `--glon`+`--glat`，或 `--domain`，或 `--grid-template`。
没写的参数先读 `resource/conf.ini`，再没有则用预设。`grid` 为空时报错。

```bash
python -m cli --module linear --grid a.nc --domain 20,50,70,140,0.1,0.1 --outer-value 0
```

```bash
python -m cli --module nearest --grid a.nc --domain 20,50,70,140,0.1,0.1 --outer-value 0
```

```bash
python -m cli --module cubic --grid a.m4 --glon 70,140,0.1 --glat 15,55,0.1 --output out.m4
```
