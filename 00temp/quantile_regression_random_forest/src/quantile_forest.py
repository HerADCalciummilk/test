"""本地化后的分位数回归森林入口。

实现来自同目录的 quantile-forest 1.4.2 源码副本，不导入已安装的 quantile_forest 包。
"""

from quantile_regression_random_forest.src._quantile_forest import ExtraTreesQuantileRegressor, RandomForestQuantileRegressor

QuantileForestRegressor = RandomForestQuantileRegressor

__all__ = [
    "ExtraTreesQuantileRegressor",
    "QuantileForestRegressor",
    "RandomForestQuantileRegressor",
]
