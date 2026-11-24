# 本地检查报告：`00temp/review_bad_sample`

## 一、总评

| 项目 | 内容 |
|------|------|
| 算法包 | `00temp/review_bad_sample` |
| 检查时间 | 2026-10-19 18:19:00 |
| 机器发现 | 阻断 **4** · 警告 **8** · 信息 **0** |
| 注释 | 共 **5** 处缺 docstring |
| 依赖 | 声明 **0** 个 · import 已全部声明 |
| pytest | 失败（exit=1） |
| 模型 | `qwen3.7-flash-2026-07-15` |
| 风险等级 | `high` |
| meb 格式 | 不符合，2 处问题 |

该算法包为故意构造的异常测试样本，存在多处严重缺陷。代码层面：CLI入口存在语法错误导致无法运行；核心插件`BrokenDemoPlugin.process`为空实现（仅pass），且未遵循MEB数据格式规范（无输入校验、无输出返回）；缺少必要的依赖清单和文档字符串。测试层面：包含故意失败的测试用例。整体质量极低，不具备任何实际业务价值或可维护性。

## 二、分项检查

### 目录结构

- **[阻断]** `nbs` — 缺少必要目录: nbs

### 语法

- **[阻断]** `cli/broken_cli.py:1` — invalid syntax

### 插件形态

- **[阻断]** `src/bad_plugin.py:BrokenDemoPlugin:10` — process 为空实现

### flake8

- **[警告]** `cli/broken_cli.py` — E999 SyntaxError: invalid syntax（行 1）

### 注释

共 **5** 处缺 docstring：

- **[警告]** `src/bad_plugin.py:1` — 公开 module 缺少 docstring
- **[警告]** `src/bad_plugin.py:BrokenDemoPlugin:6` — 公开 class 缺少 docstring
- **[警告]** `src/bad_plugin.py:BrokenDemoPlugin.process:10` — 公开 method 缺少 docstring
- **[警告]** `src/bad_plugin.py:PostProcessingPlugin:1` — 公开 class 缺少 docstring
- **[警告]** `src/bad_plugin.py:PostProcessingPlugin.process:2` — 公开 method 缺少 docstring

### 依赖完整性

清单：无依赖清单　代码用到 **0** 个外部库　Python 版本要求：未声明

- **[警告]** `整包` — 未找到任何依赖清单（requirements.txt / pyproject.toml / environment.yml / setup.py），换机器无法复现环境

### meb 数据格式

- **[警告]** `src` — 未检测到 meb 数据格式的任何信号（无 meb 导入/接口调用，注解中无 xr.DataArray / pandas.DataFrame，也未见 meb 时空坐标）；算法入参出参应采用 meb 数据格式

### pytest 运行

- **环境**：Python `3.11.5` · pytest `9.1.1` · `Windows-10-10.0.26200-SP0` · 继承本机库 · 包内无 requirements.txt · 临时 venv（跑完已删除）
- **必需库**：numpy 已就绪 · pytest 本轮安装 · meteva_base 本轮安装
- **可用依赖**：matplotlib `3.10.8` · meteva_base `0.3.1.1` · netCDF4 `1.7.2` · numpy `2.3.5` · pandas `2.3.3` · scipy `1.17.1` · xarray `2025.12.0`

- **结果**：失败（exit=1）　**耗时**：`0.88s`
- **日志**：

```text
_____________________________ test_known_failure ______________________________
test\test_known_fail.py:2: in test_known_failure
    assert False, "异常样例：故意失败"
E   AssertionError: 异常样例：故意失败
E   assert False
=========================== short test summary info ===========================
FAILED test/test_known_fail.py::test_known_failure - AssertionError: 异常样例...
1 failed in 0.16s
```

### meb 数据格式（LLM 复核）

**结论**：不符合

- **入参**：入参未采用MEB数据格式。代码中process方法使用*args, **kwargs接收任意参数，未对输入的xarray.DataArray或pandas.DataFrame进行类型检查或维度/列名校验，不符合MEB规范。
- **出参**：出参未采用MEB数据格式。PostProcessingPlugin返回None，BrokenDemoPlugin.process直接pass（隐式返回None），未返回符合MEB规范的网格DataArray或站点DataFrame。
- **依据**：src/bad_plugin.py:10
- **问题**：
  - process方法完全空实现，未处理任何逻辑，也未返回MEB数据格式结果。
  - 入参未做MEB格式校验，直接接受任意参数，存在运行时风险。

### 语义审查要点

1. **CLI入口语法错误**（high · execution · `cli/broken_cli.py`）
   main函数定义存在语法错误（def main(:），导致模块无法导入或执行。
   - 依据：cli/broken_cli.py:1

2. **核心插件process为空实现**（high · semantics · `src/bad_plugin.py`）
   BrokenDemoPlugin.process方法仅包含pass语句，无任何业务逻辑，且未返回有效结果。
   - 依据：src/bad_plugin.py:10-11

3. **关键类与方法缺失文档字符串**（medium · docs · `src/bad_plugin.py`）
   PostProcessingPlugin、BrokenDemoPlugin及其process方法均缺少docstring，不利于维护和理解。
   - 依据：src/bad_plugin.py:1-12

4. **缺少依赖清单文件**（medium · other · `整包`）
   未找到requirements.txt等依赖声明文件，环境复现困难。
   - 依据：static check

5. **测试用例故意失败**（low · execution · `test`）
   test_known_fail.py中包含assert False，导致pytest运行失败。
   - 依据：test/test_known_fail.py:2

### 改进建议

1. **修复语法错误**：立即修正`cli/broken_cli.py`中的`def main(:`语法错误。
2. **实现核心逻辑**：在`BrokenDemoPlugin.process`中实现具体的数据处理逻辑，确保输入符合MEB格式，并返回正确的MEB格式结果。
3. **补充文档**：为所有公开类和公共方法添加详细的docstring，说明参数、返回值及业务逻辑。
4. **添加依赖管理**：创建`requirements.txt`或`pyproject.toml`，明确声明项目依赖。
5. **清理测试**：移除故意失败的测试用例，或将其标记为expected failure（如果确实是测试框架的一部分）。
