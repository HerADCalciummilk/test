"""中间目录样例：可过 L1 的具体插件（含故意 warning 点）。"""


class BasePlugin:
    def __init__(self) -> None:
        pass

    def process(self, data):
        raise NotImplementedError


class DemoCleanPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__()
        # 故意：硬编码业务路径 → L1 HARDCODED_BIZ_PATH warning
        self.data_root = "/home/nimm/data/demo_clean"

    def process(self, data):
        # 故意：源码内文件 I/O → L1 PLUGIN_FILE_IO warning
        path = self.data_root + "/input.txt"
        try:
            with open(path, encoding="utf-8") as handle:
                _ = handle.read(1)
        except OSError:
            pass
        return {"ok": True, "value": data}
