# 本地算法包检查

一条命令把交来的算法包过一遍，输出一份 Markdown 审核报告。

整个 `local_review/` 目录可以随时拆走单独使用。

```text
静态检查 → 实跑（venv + pytest）→ LLM 复核与总结 → Markdown + JSON
```

任何一步发现问题都**不会中断后续步骤**，始终跑完再写报告；问题严重程度体现在退出码上。

## 快速开始

```bash
# 1. 装工具自身的依赖
pip install -r local_review/requirements.txt

# 2. 配 LLM（环境变量或配置文件，详见「LLM 配置」）
set OPENAI_API_KEY=sk-...

# 3. 跑
python -m local_review --path 00temp/<pkg> --out local-review-report.md
```

产物两份：`local-review-report.md`（给人看）和 `local-review-report.json`
（给程序看，含规则 ID 与全部指标）。

上面第 1 步装的是**本工具自身**的依赖，装到你当前的 Python 里。跑 pytest 时另有一个
给**被审算法包**用的虚拟环境，默认每次运行都新建、跑完即删，所以每次都要花一点时间装依赖
（详见「实跑（pytest）」）；反复审同一个包时用 `--venv <路径>` 复用可以省下这部分。

## 输入：算法包布局

包只要是**六树结构**就行，放在哪个上级目录都可以——不必先归入 `00temp`：

```text
<任意目录>/<pkg>/{src,cli,test,docs,nbs,resource}/
```

`--path` 指向包根（含 `src/` 的那一层），`--root` 给仓库根（默认当前目录）。
相对路径按 `--root` 解析，绝对路径直接用；包不在 `--root` 之下也认，
只是报告里的位置会退化成绝对路径，所以**能给 `--root` 就给**。

```bash
python -m local_review --path demo                     # 直接放在仓库根下
python -m local_review --path incoming/2026-09/demo    # 任意层级
python -m local_review --path 00temp/demo              # 已归入中间目录
python -m local_review --path NIMM/02diagnostic/demo   # 正式布局
```

两个前缀有额外含义：`00temp/<pkg>` 允许传更深的路径（`00temp/demo/src/algo.py` 也会
归到 `00temp/demo`）；`NIMM/<kind>/<pkg>` 走正式布局，配套目录在
`cli|test|docs|nbs|resource/<kind>/<pkg>/`。其余情况必须正好指向包根。

认不出来时会打印提示并以退出码 2 结束——条件是既不在 `--root` 下、目录里又没有 `src/`。

### 可选：包内 `review_run.toml`

**没有这个文件也能正常跑**，它只用来覆盖三项默认行为。要用就在包根建 `review_run.toml`：

```toml
# 关掉 meb 数据格式检查（确实不处理气象网格/站点数据的包）
meb_grid_required = false
# pytest 超时秒数，默认 300
timeout_sec = 600
# 指定依赖清单文件名，默认自动找 requirements.txt / requirements-dev.txt
requirements = "requirements-test.txt"
```

三项都可以只写需要的那一项，格式是简单的 `键 = 值`，`#` 开头为注释。

## 输出：报告结构

Markdown 分「总评」和「分项检查」两层：

- **一、总评**：一张表给出包名、检查时间、机器发现的阻断/警告/信息条数、缺 docstring 数、
  依赖声明与未声明数、pytest 结果、模型、风险等级、meb 格式判定；表下是 LLM 写的中文总评。
- **二、分项检查**：按检查项分节列出机器发现（`[阻断]/[警告]/[信息]` + 文件:行 + 说明），
  然后是 LLM 的 meb 复核、语义审查要点和改进建议。

报告里**不出现规则 ID**（如 `DEP_UNDECLARED`）——判定说明比 ID 更好读。需要按规则 ID
做程序化处理时读 JSON。

## 检查范围

| 检查项 | 方式 | 判定依据 |
|--------|------|----------|
| 目录结构 | 静态 | 六树目录齐不齐、有没有空目录 |
| Python 语法 | 静态 | 每个 `.py` 能否 `ast.parse` |
| 插件形态 | 静态 | 有没有继承 `BasePlugin`/`PostProcessingPlugin` 的具体插件类，`__init__`/`process` 是否齐备且非空 |
| 代码风格 | 静态 | `flake8` |
| 注释是否写全 | 静态 | 公开 API（模块/类/函数）缺 docstring 逐条列出 |
| 依赖完整性 | 静态 | 清单与代码 import 比对、版本冲突、Python 版本声明等 |
| meb 数据格式 | 静态 + LLM | 入参出参是否为 meb 数据格式 |
| 能否跑通 | 实跑 | 建 venv、装依赖、`pytest test/` |
| 语义与逻辑 | LLM | 空壳实现、逻辑问题、硬编码与隐蔽 I/O、不安全执行、重量级依赖必要性 |
| 行内注释 | LLM | 注释与代码矛盾或过时、关键逻辑段落完全无注释 |

阻断级（会让退出码变 1）的判定有：缺必要目录、Python 语法错误、缺具体插件类、插件缺
`__init__`/`process` 或 `process` 为空、依赖版本冲突、缺 `test/` 或无测试文件、
建 venv 或装依赖失败、pytest 未全部通过、必需库缺失且本包用到。
目录存在但是空的只算警告。

### 注释

静态层只看**有没有**，不算覆盖率。公开 API（不以 `_` 开头的模块、类、函数、方法）缺
docstring 即逐条列出，超过 `DOCSTRING_MISSING_LIST_LIMIT`（40）条的部分并成一句只报总数。
总评里的「共 N 处缺 docstring」是这一项的汇总。

行内注释的质量静态判不了，交 LLM，并且**只报两类有实际风险的**：注释与代码矛盾或明显
过时（要指出哪一行对不上）、关键逻辑段落完全无注释（公式、魔数、分支阈值等看不懂就没法
维护之处）。「建议补充注释说明参数含义」这类泛泛的建议不写——否则会把真正的问题挤下去。

### 依赖完整性

包根下的依赖清单**全部解析并合并**，不是只取第一个命中的——否则「同一个包在两个文件里
版本要求矛盾」会被漏掉。

| 来源 | 解析内容 |
|------|----------|
| `requirements.txt` / `requirements-dev.txt` | 包名 + 版本约束，跟随 `-r` 引用 |
| `pyproject.toml` | `[project]` 的 `dependencies`、`optional-dependencies`、`requires-python`，以及 poetry 段 |
| `environment.yml` | `dependencies` 块（含嵌套 `- pip:`）、`python=` |
| `setup.py` | `install_requires`、`python_requires`；只读 AST 字面量，**不执行**脚本 |
| `.python-version` / `runtime.txt` | 仅 Python 版本（`3.12.10` 或 `python-3.11.9`）。**不算依赖清单** |

| 规则 | 级别 | 判定 |
|------|------|------|
| `DEP_NO_MANIFEST` | 警告 | 一个清单都没有 |
| `DEP_VERSION_CONFLICT` | **阻断** | 同一包版本要求矛盾（两个不同 `==`、下界高于上界、钉版本超出范围），跨文件也算 |
| `DEP_NO_PYTHON_VERSION` | 警告 / 信息 | 没有任何 Python 版本声明。只交 `requirements.txt`（无处可写）时降为信息 |
| `DEP_UNDECLARED` | 警告（测试目录内为信息） | 代码 import 了但清单没声明。**换机器直接 `ModuleNotFoundError`，是这一节最该先看的** |
| `DEP_DEPRECATED` | 警告 | 命中停维护名单（`basemap`、`nose`、`pycrypto` 等） |
| `DEP_HEAVY` | 信息 | 命中重量级名单（`tensorflow`、`torch` 等），必要性交 LLM 结合代码规模判断 |
| `DEP_DUPLICATE_DECLARED` | 信息 | 同一包多处声明但不矛盾 |
| `DEP_NON_PYPI_SOURCE` | 信息 | 指向 `git+` / URL / 本地路径，换机器可能装不上 |
| `DEP_REPO_INTERNAL` | 信息 | import 指向仓库内其他包，不需写进清单，但本包无法脱离仓库单独交付 |
| `DEP_UNUSED_DECLARED` | 信息 | 声明了却没 import，只是多装无用的包，不影响跑通 |
| `DEP_MANIFEST_UNPARSED` | 信息 | 清单读不动或写的是非字面量。命中时本包的 `DEP_UNDECLARED` 全部降为信息并注明「可能实为已声明」 |

**输出粒度**：只有 `DEP_UNDECLARED` 逐条列出（带 `文件:行`，需要逐个跳过去确认），
其余同类结论合并成一条，包名超过 `DEP_LIST_LIMIT`（20）个只报总数。
依赖总数（超 30 个在总评标「偏多」）和「全部依赖都没写版本约束」只进汇总，不占条目。

包名与 import 名不一致的情况靠两张映射表兜住：`DIST_TO_IMPORT_NAMES`（pip，如
`PyYAML`→`yaml`、`Pillow`→`PIL`）和 `CONDA_TO_IMPORT_NAMES`（conda，如 `pytorch`→`torch`）。
环境标记（`; python_version<"3.10"`）会用 `packaging.markers` 求值，
只有存在某个环境让两条声明同时生效才判真冲突，避免误报。

### meb 数据格式

只答一个问题：**入参出参是不是 meb 数据格式**。网格还是站点只作附注，不影响判定。

静态分析拿不到运行时真实类型（`def process(self, data)` 里 `data` 是什么取决于调用方），
所以采的是可复核的静态证据：

| 证据 | 例子 | 强度 |
|------|------|------|
| 类型注解 | `def process(self, t: xr.DataArray) -> xr.DataArray` | 强 |
| `isinstance` 守卫 | `isinstance(data, xr.DataArray)` | 强 |
| meb 接口调用 | `meb.*` 中名字含 `griddata`/`stadata` 的调用（含包内同名 helper） | 强 |
| 时空坐标 | 网格维名 `member/level/time/dtime/lat/lon` 或站点列 `level/time/dtime/id/lat/lon` 命中 ≥5 且 `dtime` 在场 | 中 |
| 网格 attrs | `units`/`model`/`dtime_units`/`level_type`/`time_type`/`time_bounds` 命中 ≥3 | 补充（算法代码直接读写这些属性的地方本就不多） |
| 参数命名 | `griddata`、`grd`、`stda` | 弱 |

| 规则 | 级别 | 判定 |
|------|------|------|
| `MEB_GRID_NOT_USED` | 警告 | 全无信号 |
| `MEB_GRID_PROCESS_UNCLEAR` | 警告 | 有包级信号，但某个 `process` 自身看不出格式 |
| `MEB_GRID_OPTIONAL_INPUT` | 信息 | 注解形如 `Union[xr.DataArray, np.ndarray]`，即未强制 meb 格式 |
| `MEB_GRID_SIGNAL_OK` | 信息 | 判定结果与依据清单 |

扫描范围上，`process` 逐个判定只看源码根；网格的构造与还原常写在包内 `utils`、`cli` 里，
这些文件只贡献格式证据。`test/` 排除在外——测试夹具造网格不代表算法本身按 meb 走。
只有具体插件（有基类的类）的 `process` 算入口，基类里 `return data` 那种桩方法不参与判定。

**「实际逻辑是否真按规范走」由 LLM 判断**：提示词里写明了六维维名顺序、六项 attrs 与
站点前六列，模型据此核对入参是否按规范消费、返回是否仍是该格式、有没有中途退化成裸
`ndarray` 后未还原。这项结论在 LLM 输出里是必填字段 `meb_verdict`
（`verdict` 取 `yes`/`partial`/`no`/`unclear`，另有 `input`、`output`、`issues`、`basis`），
报告中单独成节并在总评占一行；字段缺失会显式写「LLM 未给出判定」，不静默跳过。

### 实跑（pytest）

用来证明能跑通。**通过不等于业务正确**——测试的质量与覆盖范围本身没有保障，
所以报告里只作为一项事实呈现，不夸大成结论。

流程：建 venv → 有 `requirements.txt` 就 `pip install -r` → 补齐必需库 → `pytest test/`。
缺 `test/` 目录或目录下没有 `test_*.py` / `*_test.py` 都算阻断，因为无从证明能跑通。

venv 默认建在**系统临时目录**（`local-review-venv-*`）并在跑完删除，
不会在算法包里留下需要 gitignore 的目录。默认**继承当前解释器已装的库**
（`system_site_packages=True`）只是加速手段：算法包普遍依赖 numpy / xarray / `meteva_base`，
全隔离时只要包里没写 `requirements.txt`，pytest 就会因缺依赖收集失败，把环境问题
误报成算法问题。

但继承**不能依赖本机恰好装了什么**。`config.py` 的 `REQUIRED_RUNTIME_LIBS`
列出跑测试前必须可用的库（默认 `pytest`、`numpy`、`meteva_base`）：探测不到就自动
`pip install`；装完仍缺则记 `EXEC_MISSING_REQUIRED_LIB`——若本包代码 import 了该库
（或缺的是 pytest）算**阻断**并说明「测试结果不可信」，本包没用到则只是警告，不冤枉算法。
`meteva_base` 写成 `import meteva_base as meb` 也算已具备。

报告的 pytest 一节会记录实际运行环境（Python / pytest 版本、平台、是否继承本机库、
依赖来源）和探测到的常见依赖版本，方便判断用例失败是环境问题还是代码问题。

装依赖走本机 pip 的默认配置。**需要私有源或本地 wheel 时不用给工具传参**——pip 子进程
直接继承本机环境，用 pip 自己的机制即可：临时设 `PIP_INDEX_URL` / `PIP_EXTRA_INDEX_URL` /
`PIP_FIND_LINKS` 环境变量，长期需求写用户级 `pip.ini`（Windows 在 `%APPDATA%\pip\pip.ini`）。

### LLM 复核

**必选环节**，跑在所有机器检查之后，一次调用完成。它拿到的是完整的检查结果 JSON
加包内代码与文档摘录（按 `docs → src → cli` 顺序采集 `.md/.txt/.rst/.py`）。

分工是按「机器能不能判定」切的。机器负责可判定的部分（结构、语法、flake8、缺 docstring、
依赖比对、meb 静态证据、pytest 实跑），LLM 负责判不了的部分：代码语义与逻辑、
meb 实际逻辑是否合规、重量级依赖的必要性，以及总评与风险等级。
LLM **不能运行代码**，也不会改判机器结论——两者在报告里并存。

有三处需要留意：摘录有上限（单文件 12,000 字符、合计 60,000 字符、检查 JSON 20,000 字符），
**大包会被截断**；`test/` 目录不在摘录范围内；notebook（`.ipynb`）也不采集。

调用返回的 JSON 若解析失败，会自动纠正重试一次（并优先使用端点的 JSON 模式）。
仍失败则报告照常写出、只是缺语义部分，退出码为 1。

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--path PATH` | **必填**，算法包路径 |
| `--root ROOT` | 仓库根目录，默认当前目录 |
| `--out PATH` | Markdown 报告路径，默认 `local-review-report.md` |
| `--json PATH` | JSON 报告路径，默认 `local-review-report.json` |
| `--llm-config PATH` | 指定 LLM 配置文件 |
| `--fail-on-warning` | 有警告也让退出码为 1 |
| `--venv PATH` | 用指定目录做 venv 并复用（不删除），反复跑同一个包能省下装依赖的时间 |
| `--keep-venv` | 保留默认创建的临时 venv（调试用，报告里会打印路径） |
| `--isolated-venv` | 不继承本机库，完全隔离（依赖需由 `requirements.txt` 提供） |
| `--skip-run` | 跳过实跑（调试用） |
| `--allow-skip-llm` | 跳过 LLM（仅本地调试，正式流程不应使用） |
| `--dry-run` | 只跑静态检查 |

退出码：`0` 正常；`1` 有阻断项、或 LLM 未成功、或指定了 `--fail-on-warning` 且有警告；
`2` 路径识别不出算法包。**退出码非 0 也已经写好报告**——判断成败看退出码，拿结论读报告。

## LLM 配置

支持环境变量或配置文件，**环境变量优先**。

| 项 | 环境变量 | 配置文件字段 |
|----|----------|--------------|
| API Key | `OPENAI_API_KEY` | `api_key`（或 `openai_api_key`） |
| 网关 | `OPENAI_BASE_URL` | `base_url`（或 `openai_base_url`） |
| 模型 | `OPENAI_MODEL` | `model`（或 `openai_model`） |

用配置文件的话，内容是这样（三项都可省，省了就用环境变量或默认值）：

```toml
api_key = "sk-..."
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
```

文件名取 `local_review.llm.toml` 或 `.local_review.llm.toml`，**放在 `local_review/`
目录下**（和工具放在一起，不用往仓库根塞东西）。自动查找只看这个目录，放别处需要用
`--llm-config` 指定，相对路径按 `--root` 解析。

```bash
# 放在 local_review/ 下，自动读取
python -m local_review --path 00temp/demo

# 放在别处，显式指定
python -m local_review --path 00temp/demo --llm-config D:\secrets\my-llm.toml
```

**该文件含密钥，不要提交。** `.gitignore` 里写的是 `**/local_review.llm.toml`
通配，所以放仓库任何位置都会被忽略。

接口按 OpenAI 兼容的 `/chat/completions` 调用，所以自建网关或国内模型服务
只要兼容这个协议都能用。

## 模块文件

| 文件 | 作用 |
|------|------|
| `cli.py` | 一键入口：参数解析、编排「静态 → 实跑 → LLM → 写报告」、退出码 |
| `config.py` | 可调常量与名单（目录名、插件基类名、必需库、包名映射、停维护/重量级依赖、meb 判据阈值等） |
| `package.py` | 算法包路径解析、目录定位、文本读取、`review_run.toml` 读取 |
| `models.py` | 报告数据结构：`Finding` / `SectionResult` / `ReviewReport` |
| `static_checks.py` | 目录结构、Python 语法、插件形态、flake8 |
| `docstring_check.py` | 公开 API 缺 docstring 的逐条列举与计数 |
| `dependency_check.py` | 依赖清单解析与比对；其 import 扫描也被实跑复用 |
| `meb_check.py` | 按类型注解、时空坐标与 meb 接口判断入参出参是否为 meb 数据格式 |
| `run_check.py` | 建临时 venv、装依赖、备齐必需库、跑 pytest、清理 venv |
| `llm_config.py` | 解析 LLM 配置（本目录下的 `local_review.llm.toml` 与环境变量） |
| `llm_review.py` | 采集包内上下文、调用 LLM、解析并纠错重试 |
| `report.py` | 写「总评 + 分项」的 Markdown 与 JSON |
| `test_local_review.py` | 自测（不依赖外网 LLM；pip 失败时部分实跑用例会跳过） |
| `requirements.txt` | 本工具自身的依赖 |

自测：`python -m unittest local_review.test_local_review`

## 已知局限

- **判不了真实类型**。meb 数据格式靠静态证据加 LLM 推理，不执行代码，
  注解与实参不一致时会有误差。
- **`setup.py` 里动态拼接的依赖读不到**（不执行脚本），此时会记 `DEP_MANIFEST_UNPARSED`
  并把未声明依赖的结论整体降级。
- **标准库判定跟着当前解释器**（`sys.stdlib_module_names`）。若被审包面向更低版本的
  Python，个别新标准库模块可能被误算成第三方。
- **大包的 LLM 摘录会截断**，且不含 `test/` 与 notebook。
- **pytest 通过不代表算法正确**，只代表现有测试在当前环境下能跑过。
