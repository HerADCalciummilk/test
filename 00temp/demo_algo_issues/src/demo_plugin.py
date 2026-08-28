"""故意含问题的示例算法，用于验证 L1 机器审核。"""

DATA_ROOT = "/home/nimm/data/demo"


def process(data):
    with open(DATA_ROOT + "/input.txt", encoding="utf-8") as handle:
        return handle.read()
