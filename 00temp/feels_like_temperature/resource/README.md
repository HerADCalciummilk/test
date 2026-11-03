# resource（最小运行资源）

本目录随包上传，供容器内直接试跑 CLI。

| 路径 | 说明 |
|------|------|
| `cli_input/*.nc` | **经纬坐标** meb 六维样例（气温/风速/相对湿度/气压），来自 `test_data/.../latlon/cli_input` |
| `cli_output/` | `main()` 默认写出目录 |

业务约定：输入为 meb 六维网格，空间维为 `lat`/`lon`（非投影米制坐标）。

默认命令（包根目录；在 `cli/der_feel_like_temp.py` 的 `main()` 中改路径）::

    python -m cli
