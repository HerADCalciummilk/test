# 本地算法包检查

一条命令把交来的算法包过一遍，输出一份 Markdown 审核报告。

整个 `local_review/` 目录可以拆走单独使用，不依赖本仓库的其它目录或 GitHub 审核脚本。

```text
静态检查 → 实跑（venv + pytest）→ LLM 复核与总结 → Markdown + JSON
```

任一步发现问题都**不会中断后续步骤**，始终跑完再写报告；问题严重程度体现在退出码上。

---

## 快速开始

### 1. 准备目录

解压后请保持文件夹名为 `local_review`。在其**上一级**放被审算法包，并在上一级执行命令：

```text
D:\review\
  local_review\          ← 本工具（解压出来的目录）
  feels_like_temperature\ ← 被审算法包（示例名，换成你的包即可）
```

要求：本机已装 **Python 3.10+**，并能执行 `pip` / `python`。

### 2. 安装工具依赖

在 `local_review` 的**上一级**目录打开终端：

```powershell
# Windows PowerShell
cd D:\review
pip install -r local_review\requirements.txt
```

```bash
# Linux / macOS / Git Bash
cd /path/to/review
pip install -r local_review/requirements.txt
```

这里装的是**检查工具自身**的依赖（flake8、openai、packaging 等），装到你当前使用的 Python 里。  
被审算法包的依赖会在后面跑 pytest 时另建临时虚拟环境安装，不必手动先装齐。

### 3. 配置 LLM（必做）

LLM 复核是正式流程的必选环节。需要三项信息：


| 含义       | 环境变量              | 配置文件字段     |
| -------- | ----------------- | ---------- |
| API Key  | `OPENAI_API_KEY`  | `api_key`  |
| 接口地址（网关） | `OPENAI_BASE_URL` | `base_url` |
| 模型名      | `OPENAI_MODEL`    | `model`    |


任选下面两种方式之一即可；**环境变量优先于配置文件**。  
接口需兼容 OpenAI 的 `/chat/completions`（自建网关、通义等兼容模式一般都可以）。

#### 方式 A：配置文件（推荐）

在 `local_review/` 下新建 `llm.toml`（也可用 `.llm.toml`），内容示例：

```toml
api_key = "sk-你的密钥"
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
```

把三项换成你们实际使用的密钥、网关和模型名。字段也支持别名：`openai_api_key`、`openai_base_url`、`openai_model`。

**该文件含密钥，不要提交到 git。**

#### 方式 B：环境变量（适合临时跑一次）

Windows PowerShell（**仅当前窗口有效**，关窗口后失效）：

```powershell
$env:OPENAI_API_KEY = "sk-你的密钥"
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
$env:OPENAI_MODEL = "gpt-4o-mini"
```

Windows CMD：

```bat
set OPENAI_API_KEY=sk-你的密钥
set OPENAI_BASE_URL=https://api.openai.com/v1
set OPENAI_MODEL=gpt-4o-mini
```

Linux / macOS：

```bash
export OPENAI_API_KEY="sk-你的密钥"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4o-mini"
```

配置文件放在别处时，运行时加 `--llm-config 路径`；相对路径按 `--root` 解析。

### 4. 运行检查

```powershell
# 被审包与 local_review 同级时
python -m local_review --path feels_like_temperature --out local-review-report.md

# 包在子目录里时，写相对路径即可
python -m local_review --path incoming\demo --out local-review-report.md

# 也可以给绝对路径
python -m local_review --path D:\packages\demo --root D:\packages --out D:\packages\report.md
```

首次完整跑会为算法包建临时虚拟环境并装依赖，通常需要几分钟；跑完默认删除该环境。  
反复审同一个包时可用 `--venv D:\review\.cache-venv` 复用，省下重复装库的时间。

### 5. 看结果

每次会写出两份产物（可用 `--out` / `--json` 改路径）：


| 文件                         | 用途                 |
| -------------------------- | ------------------ |
| `local-review-report.md`   | 给人看的审核报告           |
| `local-review-report.json` | 给程序看（含规则 ID 与全部指标） |


退出码：`0` 正常；`1` 有阻断项、或 LLM 未成功、或指定了 `--fail-on-warning`；`2` 路径识别不出算法包。  
**退出码非 0 时报告也已经写好**——判断成败看退出码，拿结论读 Markdown。

调试时可用：`--dry-run`（只跑静态）、`--skip-run`（跳过 pytest）、`--allow-skip-llm`（跳过 LLM，正式审核不要用）。

---



## 输入：算法包布局

包只要是**六树结构**即可，放在哪个上级目录都可以：

```text
<任意目录>/<pkg>/{src,cli,test,docs,nbs,resource}/
```

`--path` 指向包根（含 `src/` 的那一层），`--root` 为工作根目录（默认当前目录）。  
相对路径按 `--root` 解析；包不在 `--root` 之下也能审，只是报告里的位置可能变成绝对路径，所以**能给** `--root` **就给**。

```bash
python -m local_review --path demo                     # 与 local_review 同级
python -m local_review --path incoming/2026-09/demo    # 任意层级
python -m local_review --path 00temp/demo              # 中间目录布局
python -m local_review --path NIMM/02diagnostic/demo   # 正式布局
```

两个前缀有额外含义：`00temp/<pkg>` 允许传更深路径（`00temp/demo/src/algo.py` 也会归到包根）；  
`NIMM/<kind>/<pkg>` 走正式布局，配套目录在 `cli|test|docs|nbs|resource/<kind>/<pkg>/`。  
其余情况必须正好指向包根。认不出来时打印提示并以退出码 2 结束。

### 可选：包内 `review_run.toml`

**没有这个文件也能正常跑**，只在需要时覆盖默认行为。在包根创建即可：

```toml
# 关掉 meb 数据格式检查（确实不处理气象网格/站点数据的包）
meb_grid_required = false
# pytest 超时秒数，默认 300
timeout_sec = 600
# 指定依赖清单文件名，默认自动找 requirements.txt / requirements-dev.txt
requirements = "requirements-test.txt"
```

三项可只写需要的；`#` 开头为注释。

## 输出：报告结构

Markdown 分「总评」和「分项检查」两层：

- **一、总评**：包名、检查时间、机器发现条数、缺 docstring 数、依赖声明/未声明数、pytest 结果、模型、风险等级、meb 格式判定；表下是 LLM 中文总评。
- **二、分项检查**：按检查项列出机器发现（`[阻断]` / `[警告]` / `[信息]` + 文件:行 + 说明），以及 LLM 的 meb 复核、语义要点和改进建议。

报告里**不出现规则 ID**（如 `DEP_UNDECLARED`）。需要程序化处理时读 JSON。

## 检查范围


| 检查项       | 方式       | 判定依据                                                                              |
| --------- | -------- | --------------------------------------------------------------------------------- |
| 目录结构      | 静态       | 六树目录齐不齐、有没有空目录                                                                    |
| Python 语法 | 静态       | 每个 `.py` 能否 `ast.parse`                                                           |
| 插件形态      | 静态       | 有没有继承 `BasePlugin` / `PostProcessingPlugin` 的具体插件类，`__init__` / `process` 是否齐备且非空 |
| 代码风格      | 静态       | `flake8`                                                                          |
| 注释是否写全    | 静态       | 公开 API（模块/类/函数）缺 docstring 逐条列出                                                   |
| 依赖完整性     | 静态       | 清单与代码 import 比对、版本冲突、Python 版本声明等                                                 |
| meb 数据格式  | 静态 + LLM | 入参出参是否为 meb 数据格式                                                                  |
| 能否跑通      | 实跑       | 建 venv、装依赖、`pytest test/`                                                         |
| 语义与逻辑     | LLM      | 空壳实现、逻辑问题、硬编码与隐蔽 I/O、不安全执行、重量级依赖必要性                                               |
| 行内注释      | LLM      | 注释与代码矛盾或过时、关键逻辑段落完全无注释                                                            |


常见**阻断**（退出码 1）：缺必要目录、语法错误、缺具体插件类、插件缺 `__init__` / `process` 或 `process` 为空、依赖版本冲突、缺测试、建 venv / 装依赖失败、pytest 未全部通过、必需库缺失且本包用到。目录存在但为空只算警告。

### 注释

静态层只看**有没有** docstring，不算覆盖率。公开 API（不以 `_` 开头）缺失即逐条列出；超过 40 条的部分合并报总数。总评里的「共 N 处缺 docstring」是汇总。

行内注释质量交 LLM，且**只报有实际风险的两类**：注释与代码矛盾或明显过时；关键逻辑段落完全无注释（公式、魔数、分支阈值等）。泛泛的「建议多写注释」不写。

### 依赖完整性

包根下的依赖清单**全部解析并合并**（不是只取第一个），以便发现跨文件版本矛盾。


| 来源                                          | 解析内容                                                                         |
| ------------------------------------------- | ---------------------------------------------------------------------------- |
| `requirements.txt` / `requirements-dev.txt` | 包名 + 版本约束，跟随 `-r` 引用                                                         |
| `pyproject.toml`                            | `[project]` 的 dependencies、optional-dependencies、requires-python，以及 poetry 段 |
| `environment.yml`                           | dependencies（含嵌套 `- pip:`）、`python=`                                         |
| `setup.py`                                  | `install_requires`、`python_requires`；只读 AST 字面量，**不执行**脚本                    |
| `.python-version` / `runtime.txt`           | 仅 Python 版本。**不算依赖清单**                                                       |



| 规则                       | 级别           | 判定                                      |
| ------------------------ | ------------ | --------------------------------------- |
| `DEP_NO_MANIFEST`        | 警告           | 一个清单都没有                                 |
| `DEP_VERSION_CONFLICT`   | **阻断**       | 同一包版本要求矛盾（跨文件也算）                        |
| `DEP_NO_PYTHON_VERSION`  | 警告 / 信息      | 无 Python 版本声明；只交 requirements.txt 时降为信息 |
| `DEP_UNDECLARED`         | 警告（测试目录内为信息） | 代码 import 了但清单没声明——换机器最容易挂的一项           |
| `DEP_DEPRECATED`         | 警告           | 停维护包（如 `basemap`）                       |
| `DEP_HEAVY`              | 信息           | 重量级依赖（如 `tensorflow`、`torch`），必要性交 LLM  |
| `DEP_DUPLICATE_DECLARED` | 信息           | 多处声明但不矛盾                                |
| `DEP_NON_PYPI_SOURCE`    | 信息           | `git+` / URL / 本地路径                     |
| `DEP_REPO_INTERNAL`      | 信息           | import 仓库内其他包                           |
| `DEP_UNUSED_DECLARED`    | 信息           | 声明了却没 import                            |
| `DEP_MANIFEST_UNPARSED`  | 信息           | 清单读不动；此时未声明依赖结论会降级                      |


**输出粒度**：仅 `DEP_UNDECLARED` 逐条列出（带文件:行）；其余同类合并。依赖总数偏多、全部无版本约束等只进汇总。

### meb 数据格式

核心问题：**入参出参是不是 meb 数据格式**。网格 / 站点只作附注。

静态分析采可复核证据（注解、`isinstance`、meb 接口、时空坐标指纹、网格 attrs、参数命名）；  
「实际逻辑是否合规」由 LLM 在必填字段 `meb_verdict` 中给出，报告单独成节。

包内 `utils`、`cli` 可贡献格式证据；`test/` 不计入。只有具体插件（有基类）的 `process` 算入口。

### 实跑（pytest）

证明现有测试在当前环境下能跑通；**通过不等于业务正确**。

流程：建临时 venv → 有清单则 `pip install -r` → 补齐必需库（`pytest` / `numpy` / `meteva_base`）→ `pytest test/`。  
缺 `test/` 或没有测试文件算阻断。venv 默认建在系统临时目录，跑完删除；默认继承本机已装库以加速，必需库仍会主动探测并补装。

装依赖走本机 pip 配置。需要镜像或本地 wheel 时，设 `PIP_INDEX_URL` / `PIP_EXTRA_INDEX_URL` / `PIP_FIND_LINKS`，或写用户级 `pip.ini`（Windows：`%APPDATA%\pip\pip.ini`），无需给本工具额外传参。

### LLM 复核

跑在所有机器检查之后，一次调用完成。机器结论与 LLM 结论并存：LLM **不改判**机器结果，也**不能运行代码**。

摘录有上限（单文件 12,000 / 合计 60,000 / 检查 JSON 20,000 字符），大包可能被截断；不含 `test/` 与 `.ipynb`。  
返回 JSON 解析失败会自动纠正重试一次；仍失败则报告照写但缺语义部分，退出码为 1。

更细的字段说明见上文「快速开始 → 配置 LLM」。配置文件自动查找只看 `local_review/` 目录。

## 命令行参数


| 参数                  | 说明                                        |
| ------------------- | ----------------------------------------- |
| `--path PATH`       | **必填**，算法包路径                              |
| `--root ROOT`       | 工作根目录，默认当前目录                              |
| `--out PATH`        | Markdown 报告路径，默认 `local-review-report.md` |
| `--json PATH`       | JSON 报告路径，默认 `local-review-report.json`   |
| `--llm-config PATH` | 指定 LLM 配置文件（默认 `local_review/llm.toml`）   |
| `--fail-on-warning` | 有警告也让退出码为 1                               |
| `--venv PATH`       | 指定并复用 venv（不删除）                           |
| `--keep-venv`       | 保留本次临时 venv（调试用）                          |
| `--isolated-venv`   | 不继承本机库，完全隔离                               |
| `--skip-run`        | 跳过实跑（调试用）                                 |
| `--allow-skip-llm`  | 跳过 LLM（仅调试，正式流程不要用）                       |
| `--dry-run`         | 只跑静态检查                                    |




## 模块文件


| 文件                     | 作用                      |
| ---------------------- | ----------------------- |
| `cli.py`               | 一键入口与流程编排               |
| `config.py`            | 可调常量与名单                 |
| `package.py`           | 包路径解析、`review_run.toml` |
| `models.py`            | 报告数据结构                  |
| `static_checks.py`     | 目录 / 语法 / 插件 / flake8   |
| `docstring_check.py`   | 缺 docstring 列举          |
| `dependency_check.py`  | 依赖完整性                   |
| `meb_check.py`         | meb 数据格式静态证据            |
| `run_check.py`         | 临时 venv + pytest        |
| `llm_config.py`        | 读取 `llm.toml` 与环境变量     |
| `llm_review.py`        | 调用 LLM 并解析结果            |
| `report.py`            | 写 Markdown / JSON       |
| `test_local_review.py` | 自测（不依赖外网 LLM）           |
| `requirements.txt`     | 本工具依赖                   |


自测：`python -m unittest local_review.test_local_review`

## 已知局限

- meb 格式靠静态证据 + LLM 推理，不执行代码，注解与实参不一致时可能有误差。
- `setup.py` 里动态拼接的依赖读不到，会记未解析并把相关未声明结论降级。
- 标准库判定跟随当前解释器；被审包面向更低 Python 版本时，个别新标准库可能被误算成第三方。
- 大包的 LLM 摘录会截断，且不含 `test/` 与 notebook。
- pytest 通过只代表现有测试能跑过，不代表算法业务正确。

