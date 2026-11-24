"""验证 ``SimpleParallelTool`` 多进程并行是否可用。

用法（在仓库根目录）::

    python run_multipro_demo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from time import sleep

# SimpleParallelTool 位于 00temp/utils/
_ROOT = Path(__file__).resolve().parent
_TEMP = _ROOT / "00temp"
if str(_TEMP) not in sys.path:
    sys.path.insert(0, str(_TEMP))

from utils.multipro_plugin import SimpleParallelTool  # noqa: E402


def process_one_task(param: int, scale: int = 1) -> dict:
    """并行 worker：处理单个并行项。

    ``SimpleParallelTool`` 会把聚合字典拆成任务，再以关键字参数调用本函数：
    - ``param``：并行参数（每个进程拿到列表中的一项）
    - ``scale``：固定参数（所有任务共享，来自 ``fixed_params``）
    """
    sleep(0.2)
    value = int(param) * int(scale)
    return {
        "param": param,
        "scale": scale,
        "value": value,
        "pid": os.getpid(),
    }


def main() -> None:
    tasks = [1, 2, 3, 4]
    tool = SimpleParallelTool(
        target_func=process_one_task,
        num_process=2,
        parallel_mode="sync",
        with_return=True,
        fixed_params={"scale": 10},
    )
    print("num_process:", tool.default_max_processes)
    print("parent_pid:", os.getpid())

    # 聚合字典：键名须与 worker 形参一致；列表长度 = 任务数
    result = tool.process({"param": tasks})
    print("result:", result)

    pids = sorted({item["pid"] for item in result})
    print("worker_pids:", pids, "count:", len(pids))

    values = sorted(item["value"] for item in result)
    assert values == [10, 20, 30, 40], values
    if len(pids) >= 2:
        print("OK: SimpleParallelTool 使用了多个进程")
    else:
        print("WARN: 仅观察到 1 个 worker pid，请检查 num_process / 运行环境")


if __name__ == "__main__":
    main()
