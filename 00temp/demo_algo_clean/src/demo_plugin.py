"""结构完整、内容干净的示例算法，用于验证 L1 可通过。"""

from abc import ABC


class BasePlugin(ABC):
    """底基座（演示用本地拷贝；正式环境应使用统一公共基类）。"""

    def process(self, *args, **kwargs):
        raise NotImplementedError


class DemoAlgoPlugin(BasePlugin):
    """具体插件：class + __init__ + 非空 process。"""

    def __init__(self):
        pass

    def process(self, field):
        """纯计算：不做文件读写。"""
        return field + 1
