# 本地检查报告：`00temp/wind_composite`

## 一、总评

| 项目 | 内容 |
|------|------|
| 算法包 | `00temp/wind_composite` |
| 检查时间 | 2026-09-16 18:34:31 |
| 机器发现 | 阻断 **0** · 警告 **6** · 信息 **4** |
| 注释 | 共 **1** 处缺 docstring |
| 依赖 | 声明 **3** 个 · 未声明 **1** 个 |
| pytest | 通过（5.31s） |
| 模型 | `qwen3.7-flash-2026-07-15` |
| 风险等级 | `medium` |
| meb 格式 | 部分符合，1 处问题 |

算法核心逻辑正确，但 `ComputeWindDirection.process` 存在严重的格式合规性缺陷：它同时接受 meb 网格和裸 numpy 数组，且在接收裸数组时直接返回裸数组，导致输出不再是 meb 标准网格。这违反了 meb 数据格式的强制性要求，可能导致下游依赖该格式的程序崩溃或产生错误结果。此外，CLI 中缺少对 `netCDF4` 的依赖声明。

## 二、分项检查

### 目录结构

- 通过（无发现项）

### 语法

- 通过（无发现项）

### 插件形态

- 通过（无发现项）

### flake8

- **[警告]** `cli/run_wind_composite.py` — E266 too many leading '#' for block comment ×2（行 46、50）
- **[警告]** `cli/run_wind_composite.py` — E262 inline comment should start with '# '（行 54）
- **[警告]** `cli/run_wind_composite.py` — W293 blank line contains whitespace（行 35）

### 注释

共 **1** 处缺 docstring：

- **[警告]** `src/wind_composite.py:gust_factor:31` — 公开 function 缺少 docstring

### 依赖完整性

清单：`requirements.txt`、`pyproject.toml`　代码用到 **5** 个外部库　Python 版本要求：`>=3.10`

- **[警告]** `cli/run_wind_composite.py:10` — 运行时依赖 `netCDF4` 未在依赖清单中声明
- **[信息]** `requirements.txt:3` — 以下依赖在多处声明，建议各自只保留一处：`meteva_base`（pyproject.toml、requirements.txt:3）；`numpy`（pyproject.toml、requirements.txt:1）；`xarray`（pyproject.toml、requirements.txt:2）

### meb 数据格式

- **[信息]** `src` — 入参出参符合 meb 数据格式，看着是网格；依据：注解 ['DataArray']；接口 ['check_griddata', 'checkout_griddata', 'read_griddata_from_nc', 'rebuild_griddata']；导入 ['meb']；时空坐标 6/6；网格 attrs 6/6；源码根外证据来自 cli/run_wind_composite.py
- **[信息]** `src/wind_composite.py` — 入口同时接受裸数组等非 meb 类型（src/wind_composite.py:ComputeWindDirection.process）：并非强制 meb 数据格式，请确认是否符合规范

### pytest 运行

- **环境**：Python `3.13.9` · pytest `8.4.2` · `Windows-11-10.0.26200-SP0` · 继承本机库 · 已装 `requirements.txt` · 临时 venv（跑完已删除）
- **必需库**：pytest 已就绪 · numpy 已就绪 · meteva_base 已就绪
- **可用依赖**：matplotlib `3.10.6` · meteva_base `0.3.0.3` · netCDF4 `1.7.2` · numpy `2.3.5` · pandas `2.3.3` · scipy `1.16.3` · xarray `2025.10.1`

- **结果**：通过　**耗时**：`5.31s`
- **日志**：

```text
    _descriptor.FieldDescriptor(

..\..\..\..\anaconda3\Lib\site-packages\meteva_base\io\DataBlock_pb2.py:261
  D:\anaconda3\Lib\site-packages\meteva_base\io\DataBlock_pb2.py:261: DeprecationWarning: Call to deprecated create function Descriptor(). Note: Create unlinked descriptors is going to go away. Please use get/find descriptors from generated code or query the descriptor_pool.
    _MAPRESULT = _descriptor.Descriptor(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
6 passed, 31 warnings in 3.96s
```

### meb 数据格式（LLM 复核）

**结论**：部分符合

- **入参**：入参符合 meb 规范。`ComputeWindSpeed` 强制校验 meb 格式；`ComputeWindDirection` 虽允许传入非 meb 类型（如 np.ndarray），但在内部通过 isinstance 判断处理，且静态检查确认其有 meb 输入路径。
- **出参**：出参不符合 meb 规范。`ComputeWindSpeed` 正确返回 meb 网格；但 `ComputeWindDirection.process` 在接收到非 meb 输入（np.ndarray）时，直接返回计算后的 np.ndarray，未调用 `rebuild_griddata` 进行格式化，导致输出退化为裸数组。
- **依据**：src/wind_composite.py:68-82
- **问题**：
  - `ComputeWindDirection.process` 兼容裸数组输入并直接返回裸数组，破坏了 meb 输出格式的一致性。当输入为 np.ndarray 时，返回值也是 np.ndarray，缺失 member、level 等维度信息及 units 等属性。

### 语义审查要点

1. **输出格式不一致：部分路径返回裸数组而非 meb 网格**（high · semantics · `src/wind_composite.py:ComputeWindDirection.process`）
   根据 meb 规范，process 方法的返回值必须为标准 meb 网格数据（DataArray）。当前代码在 `ComputeWindDirection.process` 中，若检测到输入为 `xr.DataArray` 则正常处理并返回 meb 网格；但若输入为 `np.ndarray`（注释称兼容早期调用方），则直接返回 `wind_direction` 的计算结果（np.ndarray）。这导致同一接口的输出类型不固定，极易引发下游代码的类型错误或属性访问异常。
   - 依据：src/wind_composite.py:79-81: `return wind_direction(np.asarray(u), np.asarray(v))` 直接返回 ndarray

2. **运行时依赖 netCDF4 未在清单中声明**（medium · other · `cli/run_wind_composite.py`）
   CLI 脚本显式 import 了 `netCDF4` 模块用于打印版本信息，但该库未在 `requirements.txt` 或 `pyproject.toml` 中声明。虽然 pytest 环境可能因其他依赖间接安装了它，但这属于不规范做法，可能导致在新环境中运行 CLI 时报错。
   - 依据：cli/run_wind_composite.py:10: `import netCDF4`; dependencies section shows undeclared: ['netCDF4']

3. **公开函数缺少 docstring**（low · docs · `src/wind_composite.py:gust_factor`）
   静态检查指出 `gust_factor` 函数缺少文档字符串。虽然该函数目前看似未被主流程直接调用（仅作为辅助函数存在），但作为公开 API 的一部分，缺乏说明不利于维护。
   - 依据：static docstrings check finding

### 改进建议

### 1. 修复 `ComputeWindDirection` 的输出格式问题（关键）

**问题**：`ComputeWindDirection.process` 为了兼容旧代码，允许传入 `np.ndarray` 并直接返回 `np.ndarray`。这违背了 meb 插件接口契约。

**建议方案**：
- **方案 A（推荐）**：移除对裸数组的兼容，强制要求所有调用方传入 meb 网格。如果确实需要支持裸数组，应在入口处将其包装为 meb 网格（例如赋予默认坐标和属性），或者明确抛出 TypeError 提示用户升级调用方式。
- **方案 B**：如果必须保留兼容性，应确保无论输入何种格式，输出都必须是 meb 网格。对于裸数组输入，需构造一个临时的 meb 模板或使用 `rebuild_griddata` 的变体来生成带有基本属性的 DataArray，即使这些属性可能不完整，也不能直接返回裸数组。

### 2. 补充依赖声明

在 `requirements.txt` 或 `pyproject.toml` 中添加 `netCDF4`，以确保 CLI 环境的完整性。

### 3. 完善文档

为 `gust_factor` 函数添加 docstring，说明其用途及参数含义。
