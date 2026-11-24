# CLI 组织说明

本文说明 `00temp` 各子模块如何组织命令行入口：目录职责、装饰器合参、CLI 调度与参数传递。



## 1. 目录怎么分

```text
{包名}/
  cli/
    {包名}_cli.py          # 主入口：@merge_params 装饰的 process
    __main__.py            # process()（已带装饰器，读 conf.ini）
  src/
    *_plugin.py            # 算法与可复用步骤
  resource/
    conf.ini               # 默认运行配置，与 process 形参对应
  __main__.py              # python -m {包名} → nimm_cli
```

| 位置 | 内容 |
|------|------|
| `cli/*_cli.py` | 定义 `process` 形参、合参后校验/展开任务、调 `src` |
| `src/` | 算法原理与可复用步骤；**不再读 conf** |
| `resource/conf.ini` | 默认配置；键名对应 `process` 形参 |

原则：

- `process` 是对外入口；有多条可并行任务时再用 `_process` + `SimpleParallelTool`，单次流水线把正文写在 `process` 即可。
- `src` 只吃已经合好的参数，不做 ini 二次读取。
- 有几条独立主程序，就写几个 `*_cli.py`；**禁止** CLI → CLI 互相转发。



## 2. 装饰器 `@merge_params`

定义在 `00temp/utils/merge_params.py`，用来装饰 CLI 的 **`process`**。  
真正的函数体执行前，装饰器先把「命令行 / Python 调用 / 配置文件 / 签名预设」收成一套完整参数，再调用函数体。

### 2.1 参数整合优先级（高 → 低，务必按此理解）

| 优先级 | 来源 | 说明 |
|--------|------|------|
| **1** | **显性参数** | 调用时传入且不为 `None` 的值：命令行 `key=value`、`process(key=...)`、Python 关键字参数 |
| **2** | **`config` / `ini_path` 指向的配置文件** | 调用方显式指定的「输入配置」；从该文件抽出非空项填补仍缺的形参 |
| **3** | **默认配置文件** | 子模块 `resource/conf.ini`（可由装饰器参数改路径）；文件中非空项 |
| **4** | **参数默认预设值** | `process` **函数签名上的默认值**（如 `pro_count: int = 1`） |

要点：

- **已传入的非 `None` 显性值不会被任何 ini 覆盖。**
- 形参仍为 `None`（或未传）时，才依次看：输入 ini → 默认 `conf.ini` → 签名预设。
- 算法正文（`process` 体 / `_process` / `src`）**不要再读 conf**；合参只发生在装饰器这一层。
- `config` / `ini_path` 这两个名字是「换配置文件」的开关，**不要写进 `conf.ini` 正文当业务键**，也不要塞进并行任务的 `fixed_params`。

两个容易混的名字：

| 名字 | 出现位置 | 含义 |
|------|----------|------|
| 装饰器参数 `ini_path=` / `default_ini=` | `@merge_params(ini_path=...)` | 指定本包**默认**配置相对路径，缺省 `resource/conf.ini` |
| 调用参数 `config=` 或 `ini_path=` | `process(config=...)` / 命令行 `config=...` | 指定**本次**要读的「输入配置」文件（优先级第 2 层）；`config` 优于同次传入的 `ini_path` |

相对路径一律按 **入口 `*_cli.py` 所在包的根目录** 解析。

### 2.2 装饰器内部在做什么

调用 `process(...)` 时，包装器大致顺序：

1. **收集显性参数**  
   用 `inspect.signature` 的 `bind_partial`，只收本次真正传入的参数（**不**先套签名默认值），形成 `external`。
2. **确定配置文件路径**  
   - 默认文件：包内 `resource/conf.ini`（或装饰器改过的路径）  
   - 输入文件：若 `external` 里有非空的 `config` / `ini_path`，则解析为绝对路径  
   - 若输入文件与默认文件是同一路径，只按「输入配置」读一次，避免重复
3. **读 ini 非空项**  
   支持：无节头扁平 `key=value`；单节 `section=`；多节 `sections=`（后节同名键覆盖先节）。空字符串当作「未配置」。
4. **按四级优先级拼出每个形参的最终值**  
   只整合目标函数声明过的形参（以及本次显式传入的键）；**不会**把 ini 里多余的键塞进调用。
5. **类型转换**  
   按函数注解把 ini / 命令行字符串转成 `int` / `float` / `bool` / `list` / `tuple` 等；列表类注解支持逗号分隔。
6. **调用真正的 `process` 函数体**  
   传入合好的关键字参数；若函数未声明 `config`，装饰器用完路径即丢，不传进函数体。

签名上的默认值被故意留到第 4 级：装饰器**不会**在合参前 `apply_defaults`，否则无法区分「调用方没传」和「调用方想用预设」。

### 2.3 怎么挂装饰器

```python
from utils.merge_params import merge_params

# 默认：优先读 [process] 节；无该节则合并全部节；也支持无节头扁平 ini
@merge_params()
def process(plugin=None, pro_count: int = 1, config=None):
    ...

# 指定单节
@merge_params(section="cli")
def process(module: str = "steps", pro_count: int = 1, config=None, **kwargs):
    ...

# 多节按顺序合并（后节同名键覆盖先节）
@merge_params(sections=["cli", "lonlat_to_equal", "equal_to_lonlat"])
def process(mode: str = "lonlat-to-equal", ..., config=None):
    ...
```

`process` 的每个具名运行参数都应能在 `resource/conf.ini` 里找到对应项（或接受签名预设）。不传参时应能靠 **默认 ini + 预设** 跑起来；合参后必填项仍为空时再在函数体里报错。

### 2.4 合参结果示例

假设签名为 `process(method: str = "db", threshold: float = 0.1, config=None)`，默认 `conf.ini` 有 `method=sqrt`，另有一份 `other.ini` 有 `threshold=0.5`：

| 调用 | 最终 method | 最终 threshold |
|------|-------------|----------------|
| `process()` | `sqrt`（默认 ini） | `0.1`（签名预设；ini 未写） |
| `process(method="nq")` | `nq`（显性） | `0.1`（预设） |
| `process(config="resource/other.ini")` | `sqrt`（默认 ini，因 other 未写 method） | `0.5`（输入 ini） |
| `process(config="resource/other.ini", threshold=0.9)` | `sqrt` | `0.9`（显性压过输入 ini） |



## 3. 用户如何调用（三种方式）

工作目录一般在 **`00temp`**（用 `python -m {包名}` / `nimm_cli` 时不要先 `cd` 进子包）。  
参数一律 `key=value`（也支持 `--key=value`）。三种方式共用同一套 `@merge_params`，优先级见 §2.1。

### 3.1 写一个 `.py`，引入 cli 的 `process` 执行

适合脚本、notebook、其它模块里直接调：

```python
# 例：run_rain24.py（先保证能 import 到该包子模块）
import sys
from pathlib import Path

_TEMP = Path(r"D:\Work\NIMM_pip_repos\00temp")
_PKG = _TEMP / "frequency_matching_rain24"
sys.path[:0] = [str(_PKG), str(_TEMP)]

from cli.frequency_matching_rain24_cli import process

process()  # 默认 conf.ini + 签名预设
process(match_mode="aligned", pro_count=4)  # 显性参数
process(config="resource/conf_aligned.ini", match_mode="aligned")  # 换输入 ini + 显性
```

要点：导入的是 **`cli/{包名}_cli.py` 里已装饰的 `process`**；相对路径按该包根解析。

### 3.2 包根 `__main__.py`：`python -m {包名}` + 参数

每个子模块包根有 `__main__.py`，内部把包名和 `sys.argv` 转给 `nimm_cli`，从而支持：

```text
cd D:\Work\NIMM_pip_repos\00temp

python -m frequency_matching_rain24
python -m frequency_matching_rain24 match_mode=original pro_count=4
python -m frequency_matching_rain24 config=resource/conf_aligned.ini match_mode=aligned
```

包根 `__main__.py` 典型写法：

```python
# {包名}/__main__.py
import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_TEMP = _ROOT.parent
sys.path.insert(0, str(_ROOT))
importlib.import_module("cli.%s_cli" % _ROOT.name)
if str(_TEMP) not in sys.path:
    sys.path.insert(1, str(_TEMP))

from utils.nimm_cli import nimm_cli

if __name__ == "__main__":
    raise SystemExit(nimm_cli([_ROOT.name, *sys.argv[1:]]))
```

另：已在**子模块包根**时，也可用 `python -m cli key=value ...`（走 `cli/__main__.py`，直接 `process()`）。

### 3.3 `nimm_cli`：接收模块名 + 参数

统一调度器，显式写模块名（与 §3.2 等价，可跑任意子模块，含同包次入口）：

```text
cd D:\Work\NIMM_pip_repos\00temp

python -m utils.nimm_cli frequency_matching_rain24
python -m utils.nimm_cli frequency_matching_rain24 match_mode=aligned pro_count=4
python -m utils.nimm_cli frequency_matching_rain24 config=resource/conf_aligned.ini

# 同包次入口（如 cartopy）
python -m utils.nimm_cli coordinate_projection_transform cli=cartopy mode=lonlat-to-equal source_cube=...
```

内部：定位 `cli/{包名}_cli.py`（或 `cli=` 指定的次入口）→ 取 `process` → `process(**kwargs)`。  
`nimm_cli` **不读 ini、不合参**；合参全由该 `process` 上的 `@merge_params` 完成。

### 3.4 三种方式对照

| 方式 | 怎么用 | 内部 |
|------|--------|------|
| **1. Python 引入** | 自写 `.py`：`from cli.{包名}_cli import process` → `process(...)` | 直接调装饰后的 `process` |
| **2. `python -m {包名}`** | 包根 `__main__.py` + 命令行 `key=value` | `__main__` → `nimm_cli([包名, ...])` |
| **3. `nimm_cli`** | `python -m utils.nimm_cli {包名} key=value ...` | 按模块名找 `*_cli.py` → `process(**kwargs)` |

`config=` / `ini_path=` 只用来指定**本次输入配置文件**；业务参数仍用各自的 `key=value` / 关键字参数。



## 4. 调用后参数如何组装与传递

整体链路：

```text
用户调用（命令行 key=value / process(**kwargs)）
    → 收成「显性参数」字典（字符串或 Python 值）
    → @merge_params 四级合参 + 类型转换
    → process 函数体拿到最终形参
    → 校验 / 规范化 → 组装 run（与任务列表）
    → _process(**run) 或直接调 src（只吃已解析好的值）
```

### 4.1 从用户输入到显性参数

1. 命令行：`parse_kv_argv` 把 `key=value` 收成 `{key: "字符串"}`；经 `nimm_cli` 时第一项无 `=` 的裸词是包名，不是业务参数。
2. `process(**kwargs)`：这些项全部进入装饰器的 **显性层（优先级 1）**。
3. 因此：**命令行 / 调用里写过的项一定压过任何 ini。**

### 4.2 装饰器如何拼出最终参数

对 `process` 的每一个形参，按 §2.1 取第一个非空来源：

1. 显性（非 `None`）→ 若是字符串且有类型注解，按注解转换  
2. 否则读 `config` / `ini_path` 指向的输入 ini 中该键的非空值并转换  
3. 否则读默认 `resource/conf.ini` 中该键的非空值并转换  
4. 否则用函数签名上的预设默认值  
5. 仍没有则为 `None`（函数体里再决定是否报错）

只整合**函数声明过的形参**；ini 里多出来的键不会塞进调用。  
`config` / `ini_path` 只用于选文件：函数若未声明 `config`，装饰器用完路径即丢，不传入函数体。

### 4.3 `process` 函数体：组装后再往下传

装饰器调用真正的 `process(...)` 时，形参已经是最终值。函数体典型步骤：

1. **校验**：合参后必填仍为空再 `raise`（不要在合参前因「没传参」就失败）。
2. **规范化**：相对路径改绝对路径、列表拆分、枚举别名等。
3. **组装传递结构**（两种常见写法）：

**单次流水线**（无并行）：合参结果直接作为关键字传给 `src` / plugin：

```python
@merge_params()
def process(method: str = "db", values=None, threshold: float = 0.1, config=None):
    # 此处 method / values / threshold 已是四级合参后的最终值
    return src_process(method=method, values=values, threshold=threshold)
```

**多任务**（可选并行）：把「本批共用」收进 `run`，把「每条变化」收进任务列表，再传给 `_process`：

```python
def _process(item, **run):
    # item：本条任务特有；run：合参后的共用参数
    Demo(**run).process(item)


@merge_params()
def process(input_path: str = None, output_path: str = None, pro_count: int = 1, config=None):
    if not input_path:
        raise ValueError("缺少参数: input_path")
    run = {"output_path": output_path}          # 共用：已是合参结果
    tasks = [{"input_path": input_path}]        # 或由 ini/显性展开出的多条
    count = int(pro_count or 1)
    if count > 1:
        SimpleParallelTool(
            target_func=_process,
            parallel_mode="async",
            with_return=True,
            num_process=count,
            fixed_params=run,                   # 每条子进程都带上共用参数
        ).process({"item": tasks})
    else:
        for item in tasks:
            _process(item, **run)
```

| 传递对象 | 内容 | 谁消费 |
|----------|------|--------|
| 装饰器 → `process` 形参 | 四级合参后的最终业务参数 | `process` 函数体 |
| `run` / 关键字参数 | 本批共用的最终值 | `_process` 或 `src` |
| 任务列表元素 | 每条任务变化的部分 | `_process(item, **run)` |
| `fixed_params=run` | 并行时每条子进程共享的副本 | `SimpleParallelTool` → `_process` |

约定：

- `_process` / `src` **禁止再读 conf**；只使用上游传下来的值。
- 仅当存在多条可并行任务时才上 `pro_count` + `SimpleParallelTool`；单次流水线不要空 `_process` 或 `task_key: [1]`。

