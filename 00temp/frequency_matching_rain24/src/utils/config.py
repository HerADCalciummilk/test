##################################算法参数##################################
from utils.util_env import get_runtime_config

_runtime = get_runtime_config()
res = _runtime["res"]

# 切片网格
expansion = 1.0

inter_dis = 5  # 数据抽稀间隔
smooth_num = 30  # 9点平滑次数
sum_similar_threshold = 2.4  # 相似度和阈值

# 历史资料
his_day = 15
his_year = 3

fact_level = [0.1, 0.5, 1.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0, 500.0]
fact_level1 = [0.01, 0.1, 0.5, 1.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0]
similar_level = [25.0, 50.0]
