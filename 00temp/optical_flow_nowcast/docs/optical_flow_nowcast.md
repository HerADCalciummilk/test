# 临近光流法外推预报 — 程序说明

基于光流与半拉格朗日平流的临近外推预报。包含 Lucas-Kanade（`LK`）、窗域 LSQR（`LsqrOpticalFlow`）、半拉格朗日外推（`Extrapolation` / `Lagrangian`），以及 LINDA、S-PROG、STEPS 等扩展临近预报能力。

## 算法原理

1. **降水预处理**：估平流前可选用 `db_trans` 的 `db` / `box` / `nq` / `sqrt` 变换，减弱强降水对光流的牵拉。
2. **`LK`**：对连续降水场做特征检测（默认 Shi-Tomasi）、Lucas–Kanade 追踪得稀疏位移；可选形态学开运算、离群剔除；稀疏 UV 经 IDW 等插值铺密（`dense=true`）。
3. **`LsqrOpticalFlow`**：窗域 LSQR 在相邻降水场差分上求风，配合度制 Cressman 铺密 UV（与 `LK` 并列，不改原 `LK` 接口）。
4. **`Extrapolation` / `Lagrangian`**：用半拉格朗日平流（默认 `semilagrangian`）把最近观测降水场按 UV 外推 `timesteps` 步；步长与 `velocity` 携带的 `delta_min` 一致。
5. **`sprog` / `linda` / `steps`**：在光流外推基础上叠加谱级联、随机扰动或集合技巧，生成概率临近预报或集合。

## 参数说明

配置见 `resource/conf.ini`（同名 `key=value` CLI 优先）。子模块由 `module` 或独立子入口 `python -m cli.<模块>_cli` 选择。

### 公用与子模块（`conf.ini`）

| 参数 | 类型 | 含义 |
|------|------|------|
| `module` | `str` | `lk` / `lsqr_optical_flow` / `extrapolation` / `sprog` / `linda` / `steps` |
| `precip` | `path` | 降水序列路径（逗号分隔 nc，`lk`/`sprog` 等） |
| `transform_method` | `str` | 估速前 `db_trans` 方法；默认空 |
| `fd_method` | `str` | 特征检测；默认 shitomasi |
| `interp_method` | `str` | 稀疏→稠密插值；默认 idwinterp2d |
| `dense` | `bool` | 是否输出稠密速度场；默认 true |
| `nr_std_outlier` | `int` | 离群剔除标准差倍数；默认 3 |
| `k_outlier` | `int` | 局部离群近邻数；默认 30 |
| `size_opening` | `int` | 形态学开运算核，0 表示不做；默认 3 |
| `decl_scale` | `int` | 稀疏矢量抽稀尺度（像素）；默认 20 |
| `precip_before` | `path` | LSQR 源场（模式） |
| `precip_next` | `path` | LSQR 目标场（实况） |
| `min_window` | `list[float]` | 窗尺度 lon,lat（度）；默认 5.0,5.0 |
| `rain_limit` | `float` | 窗内有效降水阈值；默认 0.1 |
| `velocity` | `path` | 平流速度场路径 |
| `timesteps` | `int` | 外推时次数 |
| `delta_min` | `int` | 时间步长（分钟）；默认 10 |
| `extrap_method` | `str` | 平流方案；默认 semilagrangian |
| `n_cascade_levels` | `int` | 级联层数（`sprog`/`steps`）；默认 6 |
| `n_ens_members` | `int` | 集合成员数；默认 4–10（见各 `conf.ini` 节） |

更多 `sprog` / `linda` / `steps` 键见 `resource/conf.ini` 对应节；未在表中列出的项与同节注释一致。

### 插件参数（仅 Python，非 ini）

| 参数 | 类型 | 含义 |
|------|------|------|
| `lk_kwargs` | `dict` | 传给 `LK.process` 的额外字典；默认插件内置 |
| `extrap_kwargs` | `dict` | 传给外推 `process` 的额外字典；默认插件内置 |
| `callback` | `callable` | 进度回调，仅插件调用 |

### 公开插件

```python
from optical_flow_nowcast.src import Extrapolation, LK, LsqrOpticalFlow, Lagrangian
```

`LK.process` / `LsqrOpticalFlow.process` 输出平流速度场；`Extrapolation.process` 对外推场多时效外推。

| 目录 | 内容 |
| --- | --- |
| `src/` | 光流、外推与临近预报核心 |
| `cli/` | `python -m cli.<模块>_cli` 或统一 `python -m cli` |
| `resource/conf.ini` | 运行配置 |

## 运行示例

在本包目录执行。没写的参数先读 `resource/conf.ini`，再没有则用代码预设。降水场、平流场路径和外推时次未设置时会报错。子 CLI 仅打印解析参数时不读取格点。

```bash
python -m cli.lk_cli precip=obs1.nc,obs2.nc
python -m cli.lsqr_optical_flow_cli precip_before=model.nc precip_next=obs.nc
python -m cli.extrapolation_cli precip=obs.nc velocity=uv.nc timesteps=6
python -m cli.sprog_cli precip=obs1.nc,obs2.nc,obs3.nc velocity=uv.nc timesteps=6
python -m cli.linda_cli precip=obs1.nc,obs2.nc,obs3.nc velocity=uv.nc timesteps=6
python -m cli.steps_cli precip=obs1.nc,obs2.nc,obs3.nc velocity=uv.nc timesteps=6
```

直接执行 `python -m cli` 可列出上述子命令。

归档说明：降水强度变换拆至同级 `db_trans`；稀疏 UV 度制铺密见 `interp_sg_cressman`。rain24 抽出的 `lsqr_optical_flow_plugin.py`、`lagrangian_plugin.py` 为新增文件，不改原 `LK`/`Extrapolation` 接口。