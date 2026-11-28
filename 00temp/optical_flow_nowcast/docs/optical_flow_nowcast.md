# 临近光流法外推预报 — 程序说明

本包用连续降水场估计平流，再把最近一场降水往前推，得到临近预报。估速和外推可以分开调用，也可以直接用 S-PROG、LINDA、STEPS 这三套已经带平流的临近预报。

降水和平流都是 nc，多个降水文件用英文逗号隔开，按时间从早到晚。参数优先级是：调用时写上的值，高于 `resource/conf.ini` 里的非空项，高于代码预设。空着的配置项不覆盖上一层。`config` 用来换本次要读的 ini。

在 `00temp` 下用 `python -m optical_flow_nowcast module=<名字>`，或 `python -m utils.nimm_cli optical_flow_nowcast cli=<名字>`。`module` 默认 `steps`。`window_lsqr`、`window-lsqr` 都转到窗域最小二乘。命令行读完场就调用插件，不把结果场返回；要拿到场，用各节里的 Python 调用。

下面每个算法分开写原理、用途、参数和调用。表里的「必填」指命令行不给、配置里也是空时会报错。只在 Python 里用、不进 ini 的项写在该算法参数表后面。`module=` 走统一入口，`cli=` 走该算法自己的入口。Python 示例在本包目录下运行。

## Lucas–Kanade（`LK`）

**原理。** 在时间连续的降水场上检测特征点，用 Lucas–Kanade 估计特征点在相邻时次之间的位移，再将稀疏运动矢量插值为稠密的 u、v 场。估速前可对降水做强度变换，减弱强降水对光流估计的影响。特征检测默认 Shi–Tomasi，插值默认反距离权重。插值前可用形态学开运算滤除孤立回波，按标准差剔除离群矢量，并对空间邻近的矢量做抽稀。

**用途。** 由至少两张时间间隔一致的二维降水场估计平流速度，不生成外推降水。返回速度场（成员为 u、v）以及相邻时次的时间间隔，供后续外推使用。

**参数。** 命令 `python -m cli.lk_cli`，配置节 `[lk]`。

| 参数 | 必填 | 预设 | 含义 |
| --- | --- | --- | --- |
| `precip` | 是 | 无 | 降水 nc，逗号分隔，从早到晚 |
| `transform_method` | 否 | 不变换 | 估速前的强度变换：`db`、`box`、`NQ`、`sqrt` |
| `fd_method` | 否 | `shitomasi` | 特征检测，还可为 `blob`、`tstorm` |
| `interp_method` | 否 | `idwinterp2d` | 稀疏运动矢量插值，还可为 `rbfinterp2d` |
| `dense` | 否 | `true` | 为真时输出整场 u、v；为假时只留稀疏矢量 |
| `nr_std_outlier` | 否 | `3` | 离群剔除用的标准差倍数 |
| `k_outlier` | 否 | `30` | 局部离群检测看的近邻个数 |
| `size_opening` | 否 | `3` | 开运算核的像素大小，`0` 表示不做 |
| `decl_scale` | 否 | `20` | 抽稀尺度（像素），小于 2 时不抽稀 |
| `verbose` | 否 | `false` | 是否打印过程信息 |

只在插件构造时传入、不写进 ini 的有：`transform_para`（变换参数，例如 `box` 的 `threshold`、`Lambda`）、`lk_kwargs`、`fd_kwargs`、`interp_kwargs`。

**调用。** 在 `00temp`：

```bash
python -m optical_flow_nowcast module=lk precip=obs1.nc,obs2.nc transform_method=box
python -m utils.nimm_cli optical_flow_nowcast cli=lk precip=obs1.nc,obs2.nc transform_method=box
```

在本包目录用 Python 取回速度场和时间间隔：

```python
from src.lk_plugin import LK
from utils.cli_grid_io import load_precip_griddata_list

uv, delta = LK(
    transform_method="box",
    transform_para={"threshold": 0.01, "Lambda": 0.3},
).process(load_precip_griddata_list("obs1.nc,obs2.nc"))
```

## 窗域最小二乘（`LsqrOpticalFlow`）

**原理。** 在前一时次与后一时次降水场上设置滑动窗口。窗口内降水达到阈值、前后变差达到阈值且有效格点不少于下限时，用带阻尼的最小二乘估计该窗口的平流速度。窗口尺度以经纬度给出，可配置多组。稀疏速度再经 `interpolation_station_grid` 的 Cressman 插值到整场，得到 u、v。

**用途。** 由成对降水场估计平流速度，不依赖特征点追踪。类名也可写为 `OpticalFlow`、`WindowLsqr`。返回的速度场与 Lucas–Kanade 的输出形式一致，可直接用于后续外推。

**参数。** 命令 `python -m cli.lsqr_optical_flow_cli`，配置节 `[lsqr_optical_flow]`。

| 参数 | 必填 | 预设 | 含义 |
| --- | --- | --- | --- |
| `precip_before` | 是 | 无 | 前一场（源场，例如模式）nc |
| `precip_next` | 是 | 无 | 后一场（目标场，例如实况）nc |
| `min_window` | 否 | `5.0,5.0` | 窗的经度尺度和纬度尺度，单位度；多尺度用分号隔开 |
| `rain_limit` | 否 | `0.1` | 窗内当作有效降水的下限 |
| `delta_rain_limit` | 否 | `0.1` | 窗内前后场降水变差的下限 |
| `num_limit` | 否 | `100` | 窗口内最少有效格点数，不足则该窗口不参与估计 |
| `lsqr_damp` | 否 | `0.01` | 最小二乘阻尼 |
| `verbose` | 否 | `false` | 是否打印过程信息 |

**调用。** 在 `00temp`：

```bash
python -m optical_flow_nowcast module=lsqr_optical_flow precip_before=model.nc precip_next=obs.nc
python -m utils.nimm_cli optical_flow_nowcast cli=lsqr_optical_flow precip_before=model.nc precip_next=obs.nc
```

在本包目录用 Python 取回速度场。两场分开传；只传一个长度不少于 2 的列表时，按相邻时次配对：

```python
from src.lsqr_optical_flow_plugin import LsqrOpticalFlow
from utils.cli_grid_io import load_precip_griddata_list

uv, delta = LsqrOpticalFlow(min_window=[[5.0, 5.0]]).process(
    load_precip_griddata_list("model.nc"),
    load_precip_griddata_list("obs.nc"),
)
```

## 半拉格朗日外推（`Extrapolation`）

**原理。** 速度场给出每个格点在一个时间步内的位移。半拉格朗日外推沿该位移回溯上游位置，从最近一张降水场取值，并按 `timesteps` 逐步积分。默认外推方法为 `semilagrangian`。

**用途。** 在已有 u、v 速度场的条件下，生成确定性外推降水。速度可来自本包的光流估计，也可读取外部速度 nc。`timesteps` 为积分步数，`delta_min` 为每步的时间间隔（分钟）。

**参数。** 命令 `python -m cli.extrapolation_cli`，配置节 `[extrapolation]`。

| 参数 | 必填 | 预设 | 含义 |
| --- | --- | --- | --- |
| `precip` | 是 | 无 | 降水 nc；用序列里最新的一张做外推 |
| `velocity` | 是 | 无 | 速度 nc，两个分量 |
| `timesteps` | 是 | 无 | 向前推的步数 |
| `delta_min` | 否 | `10` | 一步的分钟数 |
| `extrap_method` | 否 | `semilagrangian` | 平流方案 |
| `measure_time` | 否 | `false` | 是否统计耗时 |

插件构造还可以传 `extrap_kwargs`，原样交给所选平流方案，不进 ini。

**调用。** 在 `00temp`：

```bash
python -m optical_flow_nowcast module=extrapolation precip=obs.nc velocity=uv.nc timesteps=6
python -m utils.nimm_cli optical_flow_nowcast cli=extrapolation precip=obs.nc velocity=uv.nc timesteps=6
```

在本包目录用 Python 取回外推场：

```python
from datetime import timedelta

from src.extrapolation_plugin import Extrapolation
from utils.cli_grid_io import load_precip_griddata_list, load_velocity_griddata

forecast = Extrapolation().process(
    load_precip_griddata_list("obs.nc"),
    load_velocity_griddata("uv.nc"),
    6,
    delta_t=timedelta(minutes=10),
)
```

## 半拉格朗日平流（`Lagrangian`）

**原理。** 由 u、v 和 `delta_time` 计算各格点上游的经纬度，再对原降水场做双线性插值，得到平流一个时间步后的降水场。u、v 与经纬度使用同一单位。

**用途。** 对单张降水场做一步平流。无命令行，仅 Python 调用。输入为 u、v 和降水场，输出为平流后的降水场。

**参数。**

| 参数 | 必填 | 预设 | 含义 |
| --- | --- | --- | --- |
| `u` | 是 | 无 | 经向风场 |
| `v` | 是 | 无 | 纬向风场 |
| `rain` | 是 | 无 | 要平流的降水场 |
| `delta_time` | 否 | `1.0` | 平流时间步长，与 u、v 的时间单位一致 |

**调用。** 没有命令行。在本包目录：

```python
from src.lagrangian_plugin import Lagrangian

out = Lagrangian().process(u, v, rain, delta_time=1.0)
```

## S-PROG（`Sprog`）

**原理。** 将降水场分解为若干空间尺度。各尺度用自回归分别演变后，再做半拉格朗日平流并叠加。随后用概率匹配，使预报降水的强度分布与最近时次实况一致。小尺度分量的可预报时效较短，随预报时效衰减。

**用途。** 在给定平流速度的条件下，生成一条尺度分解的确定性临近预报。自回归默认 2 阶，输入降水序列一般不少于 3 个时次。速度场对应相邻时次之间的位移。

**参数。** 命令 `python -m cli.sprog_cli`，配置节 `[sprog]`。

| 参数 | 必填 | 预设 | 含义 |
| --- | --- | --- | --- |
| `precip` | 是 | 无 | 降水 nc 序列，从早到晚 |
| `velocity` | 是 | 无 | 速度场 |
| `timesteps` | 是 | 无 | 外推步数 |
| `delta_min` | 否 | `10` | 一步的分钟数 |
| `precip_thr` | 否 | `-5` | 可辨降水阈值；只统计超过它的格点时会用到 |
| `n_cascade_levels` | 否 | `6` | 尺度层数 |
| `extrap_method` | 否 | `semilagrangian` | 平流方案 |
| `decomp_method` | 否 | `fft` | 尺度分解方法 |
| `bandpass_filter_method` | 否 | `gaussian` | 带通滤波，还可为 `uniform` |
| `ar_order` | 否 | `2` | 自回归阶数，至少为 1 |
| `conditional` | 否 | `false` | 为真时，统计只看超过 `precip_thr` 的格点 |
| `probmatching_method` | 否 | `cdf` | 概率匹配：`cdf` 对齐分布，`mean` 只对齐平均，空则不做 |
| `num_workers` | 否 | `1` | 并行 worker 数 |
| `fft_method` | 否 | `numpy` | 傅里叶变换实现 |
| `domain` | 否 | `spatial` | `spatial` 或 `spectral` |
| `measure_time` | 否 | `false` | 是否统计耗时 |

插件还可以传 `extrap_kwargs`、`filter_kwargs`，不进 ini。

**调用。** 在 `00temp`：

```bash
python -m optical_flow_nowcast module=sprog precip=obs1.nc,obs2.nc,obs3.nc velocity=uv.nc timesteps=6
python -m utils.nimm_cli optical_flow_nowcast cli=sprog precip=obs1.nc,obs2.nc,obs3.nc velocity=uv.nc timesteps=6
```

在本包目录用 Python 取回预报场：

```python
from datetime import timedelta

from src.sprog_plugin import Sprog
from utils.cli_grid_io import load_precip_griddata_list, load_velocity_griddata

forecast = Sprog(precip_thr=-5).process(
    load_precip_griddata_list("obs1.nc,obs2.nc,obs3.nc"),
    load_velocity_griddata("uv.nc"),
    6,
    delta_t=timedelta(minutes=10),
)
```

## LINDA（`Linda`）

**原理。** 在降水场上检测局地特征（默认 blob 检测），用拉格朗日积分–差分方程和自回归描述特征的平流与生消，再按速度场外推。`add_perturbations` 为真时，对特征和速度加入随机扰动，生成集合成员。

**用途。** 面向可分离的局地降水特征，给出确定性临近预报或集合预报。默认 `add_perturbations=false`，输出单一预报；为真时成员数由 `n_ens_members` 指定。

**参数。** 命令 `python -m cli.linda_cli`，配置节 `[linda]`。

| 参数 | 必填 | 预设 | 含义 |
| --- | --- | --- | --- |
| `precip` | 是 | 无 | 降水 nc 序列 |
| `velocity` | 是 | 无 | 速度场 |
| `timesteps` | 是 | 无 | 外推步数 |
| `delta_min` | 否 | `10` | 一步的分钟数 |
| `add_perturbations` | 否 | `false` | 是否加扰动得到集合 |
| `feature_method` | 否 | `blob` | 特征检测，还可为 `domain`、`shitomasi` |
| `max_num_features` | 否 | `25` | 最多保留的特征数 |
| `ari_order` | 否 | `1` | 积分差分自回归阶数 |
| `kernel_type` | 否 | `anisotropic` | 特征核类型 |
| `localization_window_radius` | 否 | 随场尺寸 | 定位窗半径 |
| `errdist_window_radius` | 否 | 随场尺寸 | 误差分布窗半径 |
| `acf_window_radius` | 否 | 随场尺寸 | 自相关窗半径 |
| `extrap_method` | 否 | `semilagrangian` | 平流方案 |
| `pert_thrs` | 否 | `0.5,1.0` | 估计扰动时用的两个阈值 |
| `n_ens_members` | 否 | `10` | 集合成员数 |
| `vel_pert_method` | 否 | `bps` | 平流扰动方法；留空表示不扰动速度 |
| `kmperpixel` | 否 | 无 | 空间分辨率，千米/像素；做速度扰动时需要 |
| `timestep` | 否 | 无 | 速度场对应的时间步，分钟；做速度扰动时需要 |
| `num_workers` | 否 | `1` | 并行 worker 数 |
| `seed` | 否 | 无 | 随机种子 |
| `use_multiprocessing` | 否 | `false` | 是否用多进程 |
| `measure_time` | 否 | `false` | 是否统计耗时 |
| `return_output` | 否 | `true` | 是否返回预报场 |

插件还可以传 `feature_kwargs`、`extrap_kwargs`、`vel_pert_kwargs` 和进度 `callback`，不进 ini。

**调用。** 在 `00temp`：

```bash
python -m optical_flow_nowcast module=linda precip=obs1.nc,obs2.nc,obs3.nc velocity=uv.nc timesteps=6
python -m utils.nimm_cli optical_flow_nowcast cli=linda precip=obs1.nc,obs2.nc,obs3.nc velocity=uv.nc timesteps=6
```

在本包目录用 Python 取回预报场。要集合时把 `add_perturbations` 设为真：

```python
from datetime import timedelta

from src.linda_plugin import Linda
from utils.cli_grid_io import load_precip_griddata_list, load_velocity_griddata

forecast = Linda(add_perturbations=False).process(
    load_precip_griddata_list("obs1.nc,obs2.nc,obs3.nc"),
    load_velocity_griddata("uv.nc"),
    6,
    delta_t=timedelta(minutes=10),
)
```

## STEPS（`Steps`）

**原理。** 将降水场分解为若干空间尺度，各尺度分别演变并做半拉格朗日平流。同时对降水加入随机噪声、对平流加入扰动，得到多个集合成员。成员差异来自这些扰动。概率匹配使预报降水的强度分布与最近时次实况一致。`mask_method` 用于处理无降水区域。

**用途。** 在给定平流速度的条件下生成短时集合预报，用于表示落区与强度的不确定性。默认 4 个成员。本入口不重新估计速度。

**参数。** 命令 `python -m cli.steps_cli`，配置节 `[steps]`。统一入口不写 `module` 时也是这一条。

| 参数 | 必填 | 预设 | 含义 |
| --- | --- | --- | --- |
| `precip` | 是 | 无 | 降水 nc 序列 |
| `velocity` | 是 | 无 | 速度场 |
| `timesteps` | 是 | 无 | 外推步数 |
| `delta_min` | 否 | `10` | 一步的分钟数 |
| `n_ens_members` | 否 | `4` | 集合成员数 |
| `n_cascade_levels` | 否 | `6` | 尺度层数 |
| `precip_thr` | 否 | 无 | 可辨降水阈值；做条件统计或掩膜时需要 |
| `kmperpixel` | 否 | 无 | 千米/像素；做速度扰动或 `incremental` 掩膜时需要 |
| `timestep` | 否 | 无 | 速度场时间步（分钟）；同上 |
| `extrap_method` | 否 | `semilagrangian` | 平流方案 |
| `decomp_method` | 否 | `fft` | 尺度分解 |
| `bandpass_filter_method` | 否 | `gaussian` | 带通滤波，还可为 `uniform` |
| `noise_method` | 否 | `nonparametric` | 降水噪声；留空表示不加 |
| `noise_stddev_adj` | 否 | 不做 | 噪声标准差订正：`auto` 或 `fixed` |
| `ar_order` | 否 | `2` | 自回归阶数 |
| `vel_pert_method` | 否 | 不扰动 | 平流扰动方法 |
| `conditional` | 否 | `false` | 为真时，统计只看超过阈值的格点 |
| `probmatching_method` | 否 | `cdf` | 概率匹配方式 |
| `mask_method` | 否 | 不掩膜 | 无降水掩膜：`obs`、`sprog`、`incremental` |
| `seed` | 否 | 无 | 随机种子 |
| `num_workers` | 否 | `1` | 并行 worker 数 |
| `fft_method` | 否 | `numpy` | 傅里叶变换实现 |
| `domain` | 否 | `spatial` | `spatial` 或 `spectral` |
| `measure_time` | 否 | `false` | 是否统计耗时 |
| `return_output` | 否 | `true` | 是否返回预报场 |

插件还可以传 `extrap_kwargs`、`filter_kwargs`、`noise_kwargs`、`vel_pert_kwargs`、`mask_kwargs` 和 `callback`，不进 ini。

**调用。** 在 `00temp`。不写 `module` 时统一入口就是 STEPS：

```bash
python -m optical_flow_nowcast precip=obs1.nc,obs2.nc,obs3.nc velocity=uv.nc timesteps=6
python -m optical_flow_nowcast module=steps precip=obs1.nc,obs2.nc,obs3.nc velocity=uv.nc timesteps=6 n_ens_members=4
python -m utils.nimm_cli optical_flow_nowcast cli=steps precip=obs1.nc,obs2.nc,obs3.nc velocity=uv.nc timesteps=6
```

在本包目录用 Python 取回集合成员：

```python
from datetime import timedelta

from src.steps_plugin import Steps
from utils.cli_grid_io import load_precip_griddata_list, load_velocity_griddata

forecast = Steps(n_ens_members=4).process(
    load_precip_griddata_list("obs1.nc,obs2.nc,obs3.nc"),
    load_velocity_griddata("uv.nc"),
    6,
    delta_t=timedelta(minutes=10),
)
```
