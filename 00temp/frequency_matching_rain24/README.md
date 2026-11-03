# multi_optimize_tp_24h

24 小时降水频率匹配订正算法，目录结构与 `mait_24h` 一致。

## 目录结构

```
multi_optimize_tp_24h/
├── cli/          # 命令行入口 (python -m cli)
├── docs/         # 程序说明文档
├── nbs/          # Jupyter 说明笔记本
├── resource/     # 配置文件、站点模板、掩码等
├── src/          # 核心算法与主程序
│   ├── correct_tp_24h.py / cal_*.py / interpolation.py
│   └── utils/    # 本算法工具：config / data_proc / data_save / verify / logger / util_env
├── test/         # 测试
└── utils/        # 仅 __init__：合并 00temp/utils 共享插件 + src/utils（无本地副本）
```

## 快速开始

1. 安装依赖：`pip install -r requirements-cli.txt`
2. 修改 `resource/optimize_tp_24.ini` 运行参数（含 `rpt_list` 起报）
3. 修改 `resource/*.json` 数据路径
4. 将 `mask010.nc` 放入 `resource/` 目录
5. 运行：

```bash
# 命令行（调度主程序 process；参数说明见 --help）
python -m cli --help
python -m cli --plugin=resource/ecmwf.json
python -m cli --rpt-list=2025100100,2025100112 --is-multi true --pro-count 8

# 模块调用
# from correct_tp_24h import process
# process(plugin="resource/ecmwf.json", is_multi=True, pro_count=8)

# 直跑（改 src/correct_tp_24h.py 的 __main__ 传参）
python src/correct_tp_24h.py
```

整理登记见 `NIMM_list.md`、`00log/`、`00temp/`。详细说明见 [docs/multi_optimize_tp_24h_程序说明.md](docs/multi_optimize_tp_24h_程序说明.md)。
