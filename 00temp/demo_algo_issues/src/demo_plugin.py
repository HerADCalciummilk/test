"""故意含问题的示例：函数式入口，无继承基类的具体插件。"""

DATA_ROOT = "/home/nimm/data/demo"


def process(data):
    with open(DATA_ROOT + "/input.txt", encoding="utf-8") as handle:
        return handle.read()
