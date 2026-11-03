# grid_stat_merge — 程序说明

格站融合：用站点相对格点的偏差，按高斯权重订正网格场。

$$
\text{融合格点} = \text{原格点} + \text{偏差场}
$$

---

## 1. 算法原理

目标是在保留格点场大尺度结构的同时，把站点观测信息订正进网格。

1. **站点偏差**  
   将格点场线性插值到站点，得到格点在站上的估计值，再与站点观测作差：

   $$
   \mathrm{bias}_i = V^{\mathrm{sta}}_i - V^{\mathrm{g\to s}}_i
   $$

2. **高斯空间传播**  
   每个站点的偏差按二维高斯核向周围格点扩散；影响水平尺度约 \(R\times 0.01^\circ\)，\(\sigma \approx 0.35\,R\)（\(R\) 为索引半径）。多站贡献按权重累加后归一，得到整场偏差场。

3. **可选约束**  
   - **地形掩膜**：若提供地形场，仅在相对站点高度差 \(|\Delta h|<100\,\mathrm{m}\) 的区域传播偏差，减轻跨山脉虚假订正。  
   - **热传导扩散**：对偏差场做固定站点值的迭代平滑，减弱孤立站造成的“牛眼”。

4. **写回**  

   $$
   V^{\mathrm{out}} = V^{\mathrm{grid}} + \mathrm{BiasField}
   $$

---

## 2. 算法实现方式

| 层级 | 路径 | 说明 |
|------|------|------|
| 算法核 | `src/grid_stat_merge.py` | `do_gs_merge`、`diffuse_values`、`GridStatMergePlugin` |
| 调度 | `src/runner.py` | `process`：读格点/站点 → 融合 → 写 Micaps4 |
| 配置 | `src/utils/util_env.py` | 读 `resource/grid_stat_merge.ini` |
| CLI | `cli/__main__.py` | argparse → `process` |

**主流程（`do_gs_merge`）**

1. 规范化站点列（值/经/纬），`domain` 缺省时从格点网格推断。  
2. `meb.interp_gs_linear` 得站上格点值，计算 `bias`。  
3. 预计算高斯核 `w_basic`，按站裁剪窗口累加 `bias*w` 与 `w`，再 `bias_mat /= w_mat`。  
4. 若开启热传导：`interp_sg_diffuse` → `diffuse_values`。  
5. `ifcst_g.values += bias_mat`，返回订正格点。

**调用形态**

- 函数：`do_gs_merge(grd, sta, R=..., domain=..., terr_mat=..., ...)`  
- 插件：`GridStatMergePlugin(...)(grd, sta)`  
- 产品入口：`from runner import process` / `python -m cli`

入参为 meteva 格点与站点 DataFrame，不硬绑业务对象。仓库根另有共享 `utils/grid_stat_merge_plugin.py`，逻辑应与本包 `src/grid_stat_merge.py` 保持一致。

---

## 3. 算法参数说明

### 3.1 融合参数（算法核 / ini / CLI 共用）

| 参数 | ini 键 | CLI | 默认 | 含义 |
|------|--------|-----|------|------|
| `R` | `R` | `--R` | 200 | 误差传播半径（索引单位）；水平约 \(R\times0.01^\circ\) |
| `domain` | `domain` | `--domain` | 空（从格点推断） | `sou,nor,wst,est,dlon,dlat` |
| `terr_mat` / 地形路径 | `terr_path` | `--terr` | 无 | 地形格点；有则启用 \(\|\Delta h\|<100\) 掩膜 |
| `b_use_heatflux_equation` | `use_heatflux` | `--use-heatflux` | false | 是否对偏差场做热传导 |
| `hf_eq_iter_nums` | `hf_eq_iter_nums` | `--hf-iters` | 20 | 热传导迭代次数（开启时有效） |
| `sta_val_col` 等 | `sta_val_col` / `sta_lon_col` / `sta_lat_col` | （仅 ini） | `data0` / `lon` / `lat` | 站点列名 |

### 3.2 路径与格式（ini）

| 键 | 默认 | 含义 |
|----|------|------|
| `grid_path` | 空 | 输入格点 |
| `sta_path` | 空 | 输入站点 |
| `output_path` | `resource/output/merge.m4` | 输出 Micaps4 |
| `terr_path` | 空 | 可选地形 |
| `grid_type` / `sta_type` | `m4` / `m3` | `m4`/`nc`；`m3`/`nc` |

未在 CLI 给出的项一律回落到 `resource/grid_stat_merge.ini`。

---

## 4. 算法使用说明

**环境**：项目根目录 `grid_stat_merge/`；依赖 `numpy` / `pandas` / `scipy` / `meteva`；共享 `utils.base_plugin`。

**步骤**

1. 编辑 `resource/grid_stat_merge.ini`，至少填写 `grid_path`、`sta_path`（及需要的 `output_path` / `R` 等）。  
2. 任选一种入口运行（见下节 CLI，或模块 / 直跑）。  
3. 查看输出 Micaps4；日志模板见 ini 中 `log_file`。

**模块调用**

```python
from runner import process
process(grid_path="a.m4", sta_path="b.m3", output_path="out.m4", R=200)

# 或直接调算法核（已有 meteva 对象时）
from grid_stat_merge import do_gs_merge, GridStatMergePlugin
grd_out = do_gs_merge(grd, sta_df, R=200)
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
python -m cli --grid=a.m4 --sta=b.m3 --output=out.m4
python -m cli --R=200 --use-heatflux false
python -m cli --domain=20,50,70,140,0.1,0.1 --terr=terr.m4 --hf-iters=20
```

| 参数 | 说明 |
|------|------|
| `--grid` | 输入格点 Micaps4/NC |
| `--sta` | 输入站点 Micaps3 |
| `--output` | 输出格点 Micaps4 |
| `--terr` | 可选地形格点 |
| `--R` | 误差传播半径 |
| `--domain` | `sou,nor,wst,est,dlon,dlat` |
| `--use-heatflux` | `true`/`false`，热传导开关 |
| `--hf-iters` | 热传导迭代次数 |

省略的参数从 `resource/grid_stat_merge.ini` 读取。
