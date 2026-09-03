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
        # Issue #22：更新管理验证用占位说明，行为与原先一致
        return {"kind": "02diagnostic", "echo": data}
