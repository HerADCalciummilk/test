"""中间目录样例：可过 L1 的具体插件（无硬编码路径、无 process 内文件 I/O）。"""


class BasePlugin:
    def __init__(self) -> None:
        pass

    def process(self, data):
        raise NotImplementedError


class DemoCleanPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__()

    def process(self, data):
        # 仅处理内存中的数据；文件读写由 cli 负责
        return {"ok": True, "value": data}
