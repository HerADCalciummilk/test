# sklearn_code 算法仓库整理清单

以表格形式记录已整理入本仓库的算法，便于检索、维护与后续补充。

---

## 已整理算法列表


| 算法种类     | 算法代号            | 算法功能                                                     | 更新时间   | 源码与配置位置                                               | CLI 入口                                                  |
| ------------ | ------------------- | ------------------------------------------------------------ | ---------- | ------------------------------------------------------------ | --------------------------------------------------------- |
| 机器学习算法 | **linear**          | 线性回归（`LinearRegression`）：普通最小二乘、无正则项；超参数经 `model_kwargs` 配置 | 2026-08-26 | `src/sklearn_plugin.py`（`AVAILABLE_MODELS["linear"]`） | `cli/sklearn_code_cli.py`（`model=linear`）               |
| 机器学习算法 | **random_forest**   | 随机森林回归（`RandomForestRegressor`）：Bagging 树集成；树结构 / 正则超参数（`n_estimators`、`max_depth` 等）经 `model_kwargs` 配置 | 2026-08-26 | `src/sklearn_plugin.py`（`AVAILABLE_MODELS["random_forest"]`） | `cli/sklearn_code_cli.py`（配置 `model="random_forest"`）        |
| 机器学习算法 | **bayesian**        | 贝叶斯岭回归（`BayesianRidge`）：自动估计正则强度；先验超参数（`alpha_*` / `lambda_*` 等）经 `model_kwargs` 配置 | 2026-08-26 | `src/sklearn_plugin.py`（`AVAILABLE_MODELS["bayesian"]`） | `cli/sklearn_code_cli.py`（配置 `model="bayesian"`）             |
| 机器学习算法 | **logistic**        | 逻辑回归分类（`LogisticRegression`）：线性分类器；`C`、`solver`、`class_weight` 等经 `model_kwargs` 配置 | 2026-11-09 | `src/sklearn_plugin.py`（`AVAILABLE_MODELS["logistic"]`） | `cli/sklearn_code_cli.py`（配置 `model="logistic"`，分类自动判定） |
| 机器学习算法 | **random_forest_classifier** | 随机森林分类（`RandomForestClassifier`）：Bagging 树分类集成；`n_estimators`、`max_depth`、`class_weight` 等经 `model_kwargs` 配置 | 2026-11-09 | `src/sklearn_plugin.py`（`AVAILABLE_MODELS["random_forest_classifier"]`） | `cli/sklearn_code_cli.py`（配置 `model="random_forest_classifier"`） |
| 机器学习算法 | **svc**             | 支持向量分类（`SVC`）：默认 RBF 核；`C`、`kernel`、`gamma`、`class_weight` 等经 `model_kwargs` 配置 | 2026-11-09 | `src/sklearn_plugin.py`（`AVAILABLE_MODELS["svc"]`） | `cli/sklearn_code_cli.py`（配置 `model="svc"`，分类自动判定） |
| 特征工程算法 | **pca**             | 主成分分析（`PCA`）：单站特征时间序列降维（EOF）；降维参数经 `feat_kwargs` 配置，与模型配对为 sklearn `Pipeline` | 2026-08-26 | `src/sklearn_plugin.py`（`AVAILABLE_FEATURES["pca"]`） | `cli/sklearn_code_cli.py`（配置 `feat_model="pca"`）             |
| 特征工程算法 | **standard_scaler** | 标准化（`StandardScaler`）：逐特征去均值、单位方差缩放；参数经 `feat_kwargs` 配置，与模型配对为 sklearn `Pipeline` | 2026-08-26 | `src/sklearn_plugin.py`（`AVAILABLE_FEATURES["standard_scaler"]`） | `cli/sklearn_code_cli.py`（配置 `feat_model="standard_scaler"`） |

> 框架统一数据格式：训练 / 预测数据均为 meteva 站点 `pd.DataFrame`，列为 `level, time, dtime, id, lon, lat` + 数据列。`SklearnCal` 以 `__init__` 配置算法与超参数（回归 / 分类由估计器类型自动判定），以统一的
> `process(df, feature_cols=..., mode=...)` 调度：`mode="train"` 用**单表**（特征列 + 目标列，须传 `target_col`）拟合**单个全局估计器**（不做逐站建模）并由返回值接收；
> `mode="predict"` 输出维度列 + 预测列（`data_name`，默认 `"prediction"`，不含特征列），回归为 float32 连续值、分类为类别标签，模型可由训练实例缓存或 `SklearnCal(estimator=...)` 传入。

---

## sklearn_code 目录明细


| 类别     | 路径                                      | 作用                                                                                                                                                                              |
| -------- | ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 核心算法 | `src/sklearn_plugin.py`            | `SklearnCal`：统一训练 / 推理插件（`__init__` 配置模型与参数，`process(mode="train"\|"predict")` 调度，回归 / 分类自动判定）；内置算法名映射表 `AVAILABLE_MODELS` / `AVAILABLE_FEATURES` |
| CLI      | `cli/sklearn_code_cli.py` | 函数级 `process` / `_process` + `@merge_params`；读 `resource/conf.ini`；模型存在则加载预测，否则或 `retrain=true` 时先训练再预测 |
| 文档     | `docs/算法参数清单.md`                    | 框架内置算法参数清单（feat_kwargs／model_kwargs），含 sklearn 1.5 官方文档链接与英文参数表 |
| notebook | `nbs/算法参数和性能介绍.ipynb` | 算法参数与性能介绍：3 个回归 + 3 个分类 + 2 个特征工程的关键参数速查；气温回归与“未来 1 小时是否降水 / 24 小时降水量级”分类的精度 / 耗时 / 体积基准；PCA 主成分数与随机森林树数/深度实验 |
| 测试     | `test/`                                   | 单元测试：`test_SklearnCal.py`（fixture 内联，含回归 / 分类用例，共 30 用例；`python -m pytest test -q`） |
