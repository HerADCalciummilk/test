# TCH 多模式 24h 降水集成 — 程序说明

**multi_rain_TCH_blending**（`pre_fcst_tch_realtime`）：读取多家数值模式 24 小时累积降水，估计各模式不确定度并得到 **BTCH** 权重，加权合成 **TCH** 集成场，写出 Micaps4 格点与可选站点场。调度入口：`src/pre_fcst_tch_realtime.py` 的 `process` 或 `python -m cli`。

---

## 算法原理

1. **读数与对齐**  
   按起报时次（北京时规则见 `conf.ini`）与 `fcst_hours` 查找各模式降水文件（默认 NetCDF，可回退 micaps4）；插值到统一 `grid_lon` / `grid_lat`，合并为 `member` 维格点。

2. **不确定度与 BTCH 权重**（`TchWeightPlugin`）  
   将各模式与参考场展平为矩阵，求预报减参考的样本协方差 $S$；约束优化得到各模式绝对/相对不确定度。  
   集成权重 $w_i \propto \prod_{j\neq i} \mathrm{err}_j^2$，再归一化——单模式误差越小权重越大。

3. **加权合成**（`TchBlendPlugin`）  
   $Q_{\mathrm{TCH}} = \sum_i w_i \, Q_i$（逐格点）；可选 `interp_gs_linear` 得站点场。

4. **掩膜与写出**  
   可读 `maskout_file` 约束有效区；输出目录分北京时与 UTC 两套（见业务配置）。

---

## 参数说明

### 运行参数（`resource/conf.ini` / CLI）

| 参数 | 类型 | 含义 |
|------|------|------|
| `maskout_file` | `path` | 全国 0.1° 掩膜路径；默认 `resource/maskout_cn_0.1_2.dat` |
| `nx_mask` / `ny_mask` | `int` | 掩膜网格尺寸；默认 701 / 601 |
| `dir_model_data` | `path` | 模式降水输入根目录；默认测试数据路径 |
| `dir_tch_output` | `path` | TCH 输出根目录；默认测试数据路径 |
| `ipt_type` | `str` | 输入格式 `nc` 或 `m4`；默认 `nc` |
| `model_list` | `list[str]` | 参与集成顺序（与权重维一致）；默认 ecmwf、ncep…等 7 模式 |
| `grid_lon` / `grid_lat` | `list[float]` | 统一插值网格起止与分辨率；默认 `70,140,0.1` / `0,60,0.1` |
| `fcst_hours` | `list[int]` | 预报时效（小时）；默认 `36,60,84` |
| `station_level` | `int` | 站点层次；默认 600 |
| `bjt_offset_hours` | `int` | 北京时与 UTC 差（小时）；默认 8 |
| `initial_hour_threshold` | `int` | 起报时次判定阈值；默认 12 |
| `initial_hour_late` / `initial_hour_early` | `int` | 起报时次判定（UTC 00 或 12）；默认 0 / 12 |
| `initial_time` | `str` | `YYYYMMDDHHMMSS` 代替“当前”做时次判定 |

未在 CLI 显式传入的项：显式参数 → `conf.ini` → 代码预设。

### 插件接口

| 类 | 主要输入 | 输出 |
|----|----------|------|
| `TchWeightPlugin` | 多模式+参考展平场 | 不确定度、`get_weight_mul` 权重 |
| `TchBlendPlugin` | `qpf_model`（含 `member`）、`weights`、可选 `station` | `qpf_combine`、`sta_combine` |

---

## 运行示例

```bash
python -m cli
python multi_rain_TCH_blending/cli/multi_rain_TCH_blending_cli.py
```

```python
from pre_fcst_tch_realtime import process
process()
```

完整运行依赖掩膜与各模式降水目录；缺文件时无法写出预报。