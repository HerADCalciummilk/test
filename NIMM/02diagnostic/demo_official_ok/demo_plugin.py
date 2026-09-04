"""正式目录样例：合格插件。"""


class BasePlugin:
    def __init__(self) -> None:
        pass

    def process(self, data):
        raise NotImplementedError


class OfficialDemoPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__()

    def process(self, data):
        # Issue #32：#31 后更新管理再测（草稿→转正→再 push）
        return {"kind": "02diagnostic", "echo": data}
