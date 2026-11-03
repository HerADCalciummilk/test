# multi_qpf_fm_rain01

逐 1 小时降水频率匹配订正（单模式 QPF 统计订正）。目录布局对齐 `mait_24h`。

## src 结构

| 路径 | 角色 |
|------|------|
| `src/runner.py` | **主程序**：`process` 调度流水线；`__main__` 直接传参 |
| `src/proc/` | 算法核心：相似评分、光流、平流、频率匹配、Cressman |
| `src/utils/` | 本算法工具：`types` / `verify` / `log` / `util_env` 等（`from utils.xxx`） |
| 根 `utils/__init__.py` | 合并 `00temp/utils` 共享插件 + `src/utils`；无本地副本 |

## 快速开始

```bash
# 命令行
python -m cli --help
python -m cli ecmwf 202604081130
python -m cli ecmwf 202604081130 202604081800 --is-multi --pro-count 4

# 模块调用
# from runner import process
# process(data_key="ecmwf", run_times=["202604081130"], is_multi=True, pro_count=4)

# 直接运行（改 src/runner.py 的 __main__ 传参）
python src/runner.py
```

并行层次：`--is-multi` 调度多起报进程；单起报内时效可用环境变量 `QPF_VALID_PROCESS_WORKERS`；样本/分块为线程池。

配置：`resource/qpf_fm.ini`、`path.json`、`config.json`、`sta.info`、`mask010.dat`。  
说明见 [docs/multi_qpf_fm_rain01_算法说明.md](docs/multi_qpf_fm_rain01_算法说明.md)。
