# interp_gg_linear — 程序说明

格点 → 格点 **双线性** 插值：把源格点场按水平索引分数插到目标网格。目标超出源网格时，先在重叠区插值，再以 `outer_value` 外扩；源网格跨满 360° 时经度按周期取模。

$$
V=(1-dx)(1-dy)\,V_{j,i}+dx(1-dy)\,V_{j,i+1}+(1-dx)dy\,V_{j+1,i}+dx\,dy\,V_{j+1,i+1}
$$

其中 \(i=\lfloor x\rfloor,\;dx=x-i\)，\(x=(λ-λ_0)/Δλ\)（纬度同理）。当前仅支持水平 `used_coords="xy"`。

---

## 1. 算法原理

目标是把规则源网格上的场，连续地重采样到另一套水平网格（可加密、平移或裁剪）。

1. **源 / 目标网格**  
   源场 `grd` 提供数值与源网格 `grid0`；目标 `grid` 提供 `glon`/`glat`。时间、层次、成员维沿用源场。

2. **越界判定**  
   非全球场：目标经纬度范围超出源网格即越界。  
   全球循环场（`dlon×nlon≥360`）：只检查纬度是否越界。  
   越界且未给 `outer_value` 时返回 `None`。

3. **双线性加权**  
   将目标格点映射到源网格索引空间，取左下角整数下标 \((i,j)\) 与分数 \((dx,dy)\)，用四个角点加权。经度循环时 \(i,i+1\) 对 `icycle=360/dlon` 取模；纬度上界钳制到 `nlat-1`。

4. **外扩**  
   若越界：先对 `get_inner_grid` 重叠区插值，再 `expand_to_contain_another_grid(..., outer_value=...)` 填满目标网格。

---

## 2. 算法实现方式

| 层级 | 路径 | 说明 |
|------|------|------|
| 算法核 | `src/interp_gg_linear.py` | `interp_gg_linear`、`InterpGGLinearPlugin` |
| 调度 | `src/runner.py` | `process`：读源格点 → 插值 → 写 Micaps4 |
| 配置 | `src/utils/util_env.py` | 读 `resource/interp_gg_linear.ini` |
| CLI | `cli/__main__.py` | argparse → `process` |

**主流程（`interp_gg_linear`）**

1. `grd is None` 则返回 `None`；否则取 level/time/dtime/member 与 `get_grid_of_data`。  
2. 判断 `iscycle` 与 `is_out`；越界且无 `outer_value` 则打印提示并返回 `None`。  
3. 越界时目标先收成重叠网格，否则直接用目标 `glon/glat`（时间维等来自源）。  
4. 对每个 member/level/time/dtime 切片：算 `ig,jg,dx,dy`，拼 `c00…c11`，写回。  
5. 越界则 `expand_to_contain_another_grid`；`attrs` 深拷贝自源场。

**目标网格优先级（`runner._resolve_target_grid`）**

1. CLI/ini 显式 `glon`+`glat`，或 `domain=sou,nor,wst,est,dlon,dlat`  
2. `grid_template_path` 模板格点（仅取水平网格）

**调用形态**

- 函数：`interp_gg_linear(grd, grid, used_coords="xy", outer_value=...)`  
- 插件：`InterpGGLinearPlugin(...)(grd, grid)`  
- 产品入口：`from runner import process` / `python -m cli`

入参为 meteva 格点场与 `grid` 对象。仓库根另有共享 `utils/interp_gg_pulgin.py`，逻辑应与本包 `src/interp_gg_linear.py` 保持一致。

---

## 3. 算法参数说明

### 3.1 插值参数（算法核 / ini / CLI 共用）

| 参数 | ini 键 | CLI | 默认 | 含义 |
|------|--------|-----|------|------|
| `used_coords` | `used_coords` | `--used-coords` | `xy` | 插值坐标；当前仅支持水平 `xy` |
| `outer_value` | `outer_value` | `--outer-value` | `0` | 目标超出源网格时的填充值；ini 留空表示不设 |
| `glon` / `glat` | `glon` / `glat` | `--glon` / `--glat` | 空 | `slon,elon,dlon` / `slat,elat,dlat` |
| `domain` | `domain` | `--domain` | 空 | `sou,nor,wst,est,dlon,dlat`（与 glon/glat 二选一） |

目标超出源网格且未设 `outer_value` 时，函数返回 `None`，`process` 会报错退出。

### 3.2 路径与格式（ini）

| 键 | 默认 | 含义 |
|----|------|------|
| `grid_path` | 空 | 输入源格点 |
| `output_path` | `resource/output/gg_linear.m4` | 输出 Micaps4 |
| `grid_template_path` | 空 | 可选网格模板（仅取水平网格） |
| `grid_type` | `m4` | `m4` / `nc` |
| `grid_template_type` | `m4` | `m4` / `nc` |

未在 CLI 给出的项一律回落到 `resource/interp_gg_linear.ini`。

---

## 4. 算法使用说明

**环境**：项目根目录 `interp_gg_linear/`；依赖 `numpy` / `meteva` / `meteva_base`；共享 `utils.base_plugin`（仓库根 `utils/`）。无 `scripts/`。

**步骤**

1. 编辑 `resource/interp_gg_linear.ini`，填写 `grid_path`，并指定目标网格（`domain` / `glon`+`glat` / `grid_template_path` 之一）。  
2. 任选一种入口运行（见下节 CLI，或模块 / 直跑）。  
3. 查看输出 Micaps4；日志模板见 ini 中 `log_file`。

**模块调用**

```python
from runner import process
process(grid_path="a.m4", domain=[20, 50, 70, 140, 0.1, 0.1],
        outer_value=0, output_path="out.m4")

# 或直接调算法核（已有 meteva 对象时）
from interp_gg_linear import interp_gg_linear, InterpGGLinearPlugin
grd_out = interp_gg_linear(grd, grid, used_coords="xy", outer_value=0)
grd_out = InterpGGLinearPlugin(outer_value=0)(grd, grid)
```

**直跑**

```bash
python src/runner.py
```

（未传参时同样读 ini。）

---

## 5. CLI 调用说明

在仓库根执行：

```bash
python -m cli --help
python -m cli
python -m cli --grid=a.m4 --domain=20,50,70,140,0.1,0.1 --output=out.m4
python -m cli --grid=a.m4 --glon=70,140,0.1 --glat=15,55,0.1 --outer-value=0
python -m cli --grid=a.m4 --grid-template=b.m4 --output=out.m4
```

| 参数 | 说明 |
|------|------|
| `--grid` | 输入源格点 Micaps4/NC |
| `--output` | 输出格点 Micaps4 |
| `--grid-template` | 可选网格模板格点（仅取水平网格） |
| `--used-coords` | 插值坐标，当前仅 `xy` |
| `--outer-value` | 目标超出源网格时的填充值 |
| `--glon` / `--glat` | 目标经纬度定义 |
| `--domain` | `sou,nor,wst,est,dlon,dlat` |

省略的参数从 `resource/interp_gg_linear.ini` 读取。
