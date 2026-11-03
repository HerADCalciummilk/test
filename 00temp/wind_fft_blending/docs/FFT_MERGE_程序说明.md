# FFT 特征匹配融合 — 程序说明

## 1. 适用场景

| 场景 | 说明 |
|------|------|
| **多源气象场空间对齐** | 将主预报场中的空间特征（如台风、锋面）向辅助预报场对齐，实现特征匹配后的融合。 |
| **UV 风场融合** | 输入 `member` 维度长度为 2 时，按 u/v 矢量联合处理，位移场同时作用于两个分量。 |
| **标量场融合** | 输入 `member` 维度长度为 1 时，按标量场处理。 |
| **集合预报融合** | 支持多个辅助场列表，对各辅助场分别计算位移后取平均，再对主数据进行平流变换。 |
| **区域裁剪加速** | 对大尺度格点数据，可裁剪关注区域进行融合，再将结果贴回全图以提升效率。 |

---

## 2. 算法原理

本算法基于谱方法与迭代优化理论，核心思想是通过最小化两个场之间的差异，在频域迭代求解位移场，实现空间对齐与融合。

### 2.1 总体思路

给定主数据场 `main` 与辅助数据场 `ass`，算法估计从 `main` 到 `ass` 特征位置的二维位移场 `(dx, dy)`，再按 `move_percent` 控制移动幅度，对主数据进行平流变换得到融合结果。

### 2.2 特征匹配（Field Alignment 2D）

1. **重采样**：将输入二维场双线性插值至 `feature_border × feature_border` 的统一网格，降低计算量并统一尺度。
2. **归一化**：对参考场与目标场做 min-max 归一化，消除量纲差异。
3. **迭代优化**：在每次迭代中：
   - 根据当前位移场，用双三次插值（`_bicutest`）将参考场平移到当前位置；
   - 计算有效区域内的场差 `dq = loc × (arr1 - arr2)` 作为 forcing；
   - 由场差的梯度构造 forcing 分量 `t1`、`t2`；
   - 对 forcing 做二维 FFT，在频域求解位移增量 `ux`、`uy`；
   - 应用幂律型平滑滤波（`power_model`、`weight_value`）保证位移场物理合理；
   - 累加位移并检查收敛条件（误差中位数、瞬时位移极值、误差变化率）。
4. **收敛判据**：达到 `max_iterations`，或误差中位数 `errl ≤ 1e-4`，或瞬时位移 `errv ≤ 1e-5`，或误差变化 `derrl ≥ 1e+1` 时停止。
5. **尺度还原**：将低分辨率位移场插值回原始网格尺寸，并按宽高比例缩放位移量。

### 2.3 多辅助场融合

对 `ass_da_list` 中每个辅助场分别计算位移场，对 x/y 方向位移取算术平均；若 `move_percent < 1`，则对平均位移按比例缩放。

### 2.4 平流变换

根据最终位移场，对主数据（及 v 分量）进行平流：

1. 反射边界扩展（默认 25 像素）抑制边缘效应；
2. 构建反向映射坐标 `new_x = x - dx`，`new_y = y - dy`；
3. 双线性插值采样得到平流后的场；
4. 对插值产生的 NaN/Inf 位置，回填原始值。

### 2.5 关键技术

| 技术 | 作用 |
|------|------|
| 双线性插值重采样 | 适应不同分辨率，统一特征检测网格 |
| 反射边界扩展 | 避免 FFT 与平流过程中的边缘伪影 |
| 双三次插值 | 亚像素级精确位移计算 |
| 频域求解 | 高效计算整场的位移增量 |
| 约束权重与平滑滤波 | 抑制位移场振荡，保证结果稳定 |

---

## 3. 实现方法与主流程

### 3.1 调用链

```
python -m cli
    → cli 解析参数 → main.process(..., is_multi=..., pro_count=...)
python src/main.py
    → __main__ 中直接给 process 传参
    → main._run_one()（单任务；多任务时串行或 SimpleParallelTool）
    → fft_merge.FFTMergePlugin.__call__()
    → FFTMergePlugin.process()
    → _move_arr_with_several()
    → _calc_moved_arr() → _calc_moved_arr_with_2d_arr()
    → _advect()
```

### 3.2 `FFTMergePlugin.process` 流程

| 步骤 | 操作 |
|------|------|
| 1 | 校验 `move_percent ∈ (0, 1]` |
| 2 | 从 `main_da` 提取主分量数组；若 `member=2` 则同时提取 v 分量 |
| 3 | 从 `ass_da_list` 提取各辅助场数组 |
| 4 | 调用 `_move_arr_with_several` 计算融合后的 u/v 数组 |
| 5 | 通过 `meteva.base.grid_data` 封装为与原输入一致的 `xr.DataArray` 返回 |

### 3.3 数据流示意

```mermaid
flowchart TD
    A[读取 main_da 与 ass_da_list] --> B[提取 numpy 二维数组]
    B --> C[对每个 ass 计算位移场]
    C --> D[位移场加权平均 × move_percent]
    D --> E[对 main 及 v 分量平流 _advect]
    E --> F[封装为 xr.DataArray 输出]
```

### 3.4 输入数据格式

`main_da` 与 `ass_da_list` 中的每个 `xr.DataArray` 需包含以下维度（顺序固定）：

| 维度 | 要求 |
|------|------|
| `member` | 长度 1（标量）或 2（u/v 风） |
| `level` | 长度 1 |
| `time` | 长度 1 |
| `dtime` | 长度 1 |
| `lat` / `lon` | 空间格点维度，主辅场分辨率一致 |

### 3.5 类内部常量

下列量不作为 `process` / CLI 参数。`FFTMergePlugin` 启动时先读 `resource/fft_merge.ini`，缺项再用下表预设：

| 属性 | 预设 | 说明 |
|------|------|------|
| `weight_value` | 0.1 | 频域求解 Tikhonov 型约束权重 |
| `power_model` | 2 | 平滑滤波幂律指数（2 或 4） |
| `l_scale` | 1 | FFT 谱域尺度比率 |
| `reflect_pad` | 25 | 迭代与平流时的反射边界像素 |

---

## 4. 目录与核心文件

| 路径 | 作用 |
|------|------|
| `src/fft_merge.py` | 核心算法，`FFTMergePlugin` 类 |
| `src/main.py` | 可调度 `process`；未传参数先读 ini |
| `cli/__main__.py` | `python -m cli` 入口，转发至 `src/main.process` |
| `resource/fft_merge.ini` | 路径、可调参数与算法常量 |
| `src/utils/util_env.py` | 读 ini，并按「显式参数 > ini > 预设」补齐 |
| `NIMM_pip_testdata/multi_wind_fft_blending/test_data/sample_*_uv.m11` | 与仓库同级的 Micaps11 示例 UV 风场 |
| `docs/FFT_MERGE_程序说明.md` | 程序说明文档 |
| `nbs/fft_merge_说明.ipynb` | 算法说明 Notebook |
| `test/test_fft_merge.py` | 核心算法单元测试 |
| `test/test_main.py` | `src/main.process` 集成测试 |

---

## 5. 参数说明

### 5.1 `FFTMergePlugin.__call__` / `process` 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `main_da` | `xr.DataArray` | — | 主数据场，待融合调整的目标场 |
| `ass_da_list` | `list[xr.DataArray]` | — | 辅助数据列表，用于特征匹配参考 |
| `feature_border` | `int` | 192 | 内部重采样网格边长（像素）。值越小计算越快，但过小可能导致形变失真；128 约可提升 2/3 效率 |
| `max_iterations` | `int` | 1024 | 位移求解最大迭代次数。减少可加速，过少可能导致特征识别异常 |
| `move_percent` | `float` | 1.0 | 移动比例，取值 `(0, 1]`。1.0 表示完全移动到辅助场特征位置；0.5 表示移动到中间位置 |

### 5.2 CLI 参数

未在命令行给出的项先读 `resource/fft_merge.ini`，ini 无该项再用预设。`weight_value`、`power_model`、`l_scale`、`reflect_pad` 只在 ini 中配置。

| 选项 | 预设 | 说明 |
|------|------|------|
| `--main-uv` | ini `main_uv`（空则必须传入） | 主风场 Micaps11，可多个 |
| `--ass-uv` | ini `ass_uv`（空则必须传入） | 辅助风场 Micaps11 |
| `--output-dir` | `resource/output` | 输出目录 |
| `--output-prefix` | `fft_merge` | 输出文件名前缀 |
| `--feature-border` | 128 | 特征匹配网格边长 |
| `--max-iterations` | 1024 | 最大迭代次数 |
| `--move-percent` | 1.0 | 移动比例 `(0, 1]` |
| `--write-linear-compare` / `--no-write-linear-compare` | 开启 | 是否写出线性平均对比 |
| `--is-multi` / `--no-is-multi` | 关闭 | 多任务是否多进程 |
| `--pro-count` | 4 | 多进程并行数 |

命令行调用示例（在本包根目录执行）：

```bash
python -m cli --main-uv <主风场.m11> --ass-uv <辅助风场.m11> --output-dir resource/output --output-prefix sample_a
```

### 5.3 代码调用示例

```python
import fft_merge

plugin = fft_merge.FFTMergePlugin()
merged_da = plugin(main_da, [ass_da], feature_border=128)
merged_uv_da = plugin(main_uv_da, [ass_uv_da], feature_border=128, move_percent=0.8)
merged_ensemble = plugin(main_da, [ass1_da, ass2_da], feature_border=128, max_iterations=512)
```

### 5.4 使用建议

1. 陆海差异较大时，建议分区单独处理，避免互相干扰。
2. 对强特征（台风、锋面）效果较好；弱梯度场位移估计可能接近零。
3. 大区域数据建议裁剪后融合再贴回，可显著缩短耗时。

---

## 6. 运行方式

### 6.1 安装依赖

```bash
pip install -r requirements.txt
```

依赖：`numpy`、`scipy`、`meteva`、`xarray`。

### 6.2 命令行示例

在本包根目录执行。下面这条即可跑通单任务；没写上的 `--feature-border` 等先读 `resource/fft_merge.ini`，再没有则用预设。

```bash
python -m cli --main-uv <主风场.m11> --ass-uv <辅助风场.m11> --output-dir resource/output --output-prefix sample_a
```

样例数据位于与 `NIMM_pip_repos` **同级**目录：

`NIMM_pip_testdata/multi_wind_fft_blending/test_data/`

```bash
# 查看帮助（epilog 中会打印本机 test_data 绝对路径与多进程示例）
python -m cli --help

# 直接运行 main.py：在 src/main.py 的 __main__ 中改 process 传参
# python src/main.py

# 单任务（请将 TEST_DATA 换为本机绝对路径）
python -m cli \
  --main-uv %TEST_DATA%/sample_a1_uv.m11 \
  --ass-uv %TEST_DATA%/sample_a2_uv.m11 \
  --output-dir %TEST_DATA% \
  --output-prefix sample_a

# 多任务 + 多进程（路径列表 + --is-multi）
python -m cli \
  --main-uv %TEST_DATA%/sample_a1_uv.m11 %TEST_DATA%/sample_b1_uv.m11 \
  --ass-uv %TEST_DATA%/sample_a2_uv.m11 %TEST_DATA%/sample_b2_uv.m11 \
  --output-prefix sample_a sample_b \
  --output-dir %TEST_DATA% \
  --is-multi --pro-count 2
```

模块调度（``is_multi`` 控制是否多进程）::

```python
from main import process
process(
    main_uv_path=[".../a1.m11", ".../b1.m11"],
    ass_uv_path=[".../a2.m11", ".../b2.m11"],
    output_dir=".../test_data",
    output_prefix=["a", "b"],
    is_multi=True,
    pro_count=2,
)
```

### 6.3 示例输出

将 `--output-dir` 指向 `test_data`（或其它目录）时，可生成：

| 文件 | 内容 |
|------|------|
| `{prefix}_fft_uv.nc` | FFT 融合 UV 风 NetCDF |
| `{prefix}_fft_uv.m11` | FFT 融合 UV 风 Micaps11 |
| `{prefix}_line_uv.nc` | 线性平均 UV 风 NetCDF（对比用） |
| `{prefix}_line_uv.m11` | 线性平均 UV 风 Micaps11（对比用） |

输入数据：`test_data/sample_{a|b}1_uv.m11`（主数据）、`test_data/sample_{a|b}2_uv.m11`（辅助数据）。

### 6.4 运行测试

```bash
python -m pytest test/ -v
```

或单独运行：

```bash
python test/test_fft_merge.py
python test/test_main.py
```
