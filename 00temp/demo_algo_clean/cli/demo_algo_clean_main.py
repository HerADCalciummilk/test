"""cli：读取输入、调用插件 process、写回结果。"""

import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PKG / "src"))

from demo_plugin import DemoCleanPlugin  # noqa: E402


def load_input(path: Path) -> object:
    text = path.read_text(encoding="utf-8").strip()
    return text or {}


def save_output(path: Path, payload: object) -> None:
    path.write_text(str(payload), encoding="utf-8")


def main() -> None:
    in_path = _PKG / "resource" / "sample_input.txt"
    out_path = _PKG / "resource" / "sample_output.txt"
    data = load_input(in_path) if in_path.is_file() else {"sample": 1}
    plugin = DemoCleanPlugin()
    result = plugin.process(data)
    save_output(out_path, result)
    print(result)


if __name__ == "__main__":
    main()
