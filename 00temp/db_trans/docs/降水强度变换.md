# 降水强度变换

## 基本信息

- 算法名称：`db_trans`
- 来源：从 `optical_flow_nowcast/src/dB_trans.py` 拆出
- 算法类型：降水场预处理
- 原始作者标记：cheny

## 算法功能

把降水强度换成更适合光流和平流计算的数值刻度，也可以变回毫米/小时。变换本身不计算速度场，也不做外推。

- `dB_transform`：`10·log10(R)`。低于阈值的无降水格点写成固定零值。
- `boxcox_transform`：Box-Cox 变换。`Lambda=0` 时是对数变换。
- `NQ_transform`：正态分位数变换。无降水在正态空间记为 `0`，逆变换依赖正变换留下的插值函数。
- `sqrt_transform`：开平方，逆变换是平方。

## 主要入口

- `src/db_trans_plugin.py`：`DbTransPlugin(BasePlugin)`
  - 共用：`R`、`metadata`、`inverse`
  - `dB_transform` 特有：`threshold`、`zerovalue`
  - `boxcox_transform` 特有：`Lambda`、`threshold`、`zerovalue`
  - `NQ_transform` / `Q_transform` 特有：`a`（逆变换依赖正变换 `metadata["inqt"]`）
  - `sqrt_transform` 特有：无
  - `process(method=db|box|nq|sqrt, ...)` 统一调度

`optical_flow_nowcast` 的 Lucas-Kanade 插件在估平流前调用这里。对应关系是 `db`、`box`、`nq`、`sqrt`。

## 算法原理

1. **用途**：光流特征追踪对原始 mm/h 降水动态范围敏感；先变换到更平缓的刻度再估速，外推后再逆变换。本包只做标量变换，不算风场。
2. **`db`**：\(R \ge \mathrm{threshold}\) 时 \(10\log_{10}R\)；低于阈值格点写固定 `zerovalue`（默认约为阈值 dB 减 5）。逆变换为 \(10^{R/10}\)。
3. **`box`**：Box-Cox；`lam=0` 时对超过阈值部分做对数变换，无雨仍用 `zerovalue`。
4. **`nq`**：用 `scipy` 分位数将样本映到正态分位；无雨记为 `0`；逆变换依赖正变换写入 `metadata["inqt"]` 的插值函数。
5. **`sqrt`**：\(R^{1/2}\)，逆为平方；无额外阈值分支。
6. **调度**：`DbTransPlugin.process(method=db|box|nq|sqrt, inverse=...)` 统一入口；`metadata` 在正/逆变换间传递阈值与插值表。

## 参数说明

| 参数 | 类型 | 含义 |
|------|------|------|
| `method` | str | `db` / `box` / `nq` / `sqrt`；默认 `summary` |
| `values` | list | 逗号分隔试算数组（不读格点）；默认空 |
| `threshold` | float | 有雨判定（mm/h），用于 `db`、`box`；默认 `0.1` |
| `zerovalue` | float | 无雨格点在变换空间的取值；默认空则各方法内置 |
| `lam` | float | Box-Cox 的 \(\lambda\)；默认 `0` |
| `a` | float | 正态 Q-Q 变换绘图偏移；默认 `0` |
| `inverse` | bool | 是否做逆变换；默认 false |

插件 `process` 另有数组 `R`；光流侧通过 `transform_method` 选择同上四种方法。

## 目录说明

- `src/db_trans_plugin.py`：四种降水强度变换（类方法）。
- `cli/db_trans_cli.py`：在本包目录执行 `python -m cli`；或在 `00temp` 下 `python -m db_trans`。
- `resource/conf.ini` / `db_trans.ini`：命令行未显式传入的参数先读配置，再没有则用预设。
- `utils/util_env.py`：读取 ini。
- `test/`：变换数值和命令行缺省参数测试。
- `nbs/`：命令行调用示例 notebook。
- `docs/`：本说明。

## 运行示例

在本包目录下执行。没写的参数先读 `resource/db_trans.ini`，配置里也没有再用代码预设。`summary` 只列出变换名称。

```bash
python -m cli.dB_trans_cli
```

```bash
python -m cli.dB_trans_cli --method db --values 0,0.05,0.1,1,10,100
```

```bash
python -m cli.dB_trans_cli --method box --values 0.1,1,10 --lambda 0
```

```bash
python -m cli.dB_trans_cli --method sqrt --values 0,1,4,9
```

`db` 在阈值 `0.1` 下，上面第一组数变成 `-15,-15,-10,0,10,20`。低于 `0.1` 记为 `-15`，`1` 变成 `0`，`10` 变成 `10`，`100` 变成 `20`。

## 依赖与运行条件

依赖 `numpy`、`scipy`。不依赖 `iris`、`meteva` 或光流插件。

## 当前限制

- 命令行一次只变换一组逗号分隔的数，不读格点文件。
- `nq` 的逆变换需要正变换写进 `metadata` 的插值函数，命令行单次调用只做正变换。
- `db`、`box` 的无降水取值留空时，沿用函数内部默认，不在配置里写死一个数。
