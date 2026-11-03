import os
from time import sleep

from utils.multipro_plugin import SimpleParallelTool


def square(n):
    sleep(0.3)
    return {"n": n, "square": n * n, "pid": os.getpid()}


if __name__ == "__main__":
    tool = SimpleParallelTool(
        target_func=square,
        num_process=2,
        parallel_mode="sync",
        with_return=True,
    )
    print("num_process:", tool.default_max_processes)
    result = tool.process({"n": [1, 2, 3, 4]})
    print(result)
    pids = sorted({item["pid"] for item in result})
    print("pids:", pids, "count:", len(pids))
