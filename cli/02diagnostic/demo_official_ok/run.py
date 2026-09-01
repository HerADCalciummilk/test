"""正式包 cli：实例化插件并调用 process。"""

from pathlib import Path
import sys

# 测试仓内相对导入：把 NIMM 包路径加入 sys.path
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "NIMM" / "02diagnostic" / "demo_official_ok"))

from demo_plugin import OfficialDemoPlugin  # noqa: E402


def main() -> None:
    plugin = OfficialDemoPlugin()
    result = plugin.process({"sample": 1})
    print(result)


if __name__ == "__main__":
    main()
