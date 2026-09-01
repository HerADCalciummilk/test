"""正式包 cli：实例化插件并调用 process。"""

import sys
from pathlib import Path

# 测试仓未做成可安装包：把同算法的 NIMM 源码根加入 path
_REPO = Path(__file__).resolve().parents[3]
_SRC = _REPO / "NIMM" / "02diagnostic" / "demo_official_ok"
sys.path.insert(0, str(_SRC))

from demo_plugin import OfficialDemoPlugin  # noqa: E402


def main() -> None:
    plugin = OfficialDemoPlugin()
    result = plugin.process({"sample": 1})
    print(result)


if __name__ == "__main__":
    main()
