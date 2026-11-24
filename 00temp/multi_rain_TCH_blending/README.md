# pre_fcst_tch_realtime

读取多家数值模式的 24 小时累积降水，按误差协方差估计各模式不确定性，加权合成 TCH 集成预报，并写出格点场（m4）与站点场（m3）。北京时目录与检验平台 UTC 目录各一套。

无独立 runner。调度入口是 `src/pre_fcst_tch_realtime.py` 的 `process`。

## 目录

```
pre_fcst_tch_realtime/
├── cli/                 # python -m cli
├── resource/conf.ini    # 路径、模式列表、网格、时效
├── src/
│   ├── pre_fcst_tch_realtime.py
│   └── utils/util_env.py
├── test/
└── utils/               # 合并 00temp/utils 与 src/utils
```

## 启动

在本包目录执行：

```text
python -m cli --help
python cli/pre_fcst_tch_realtime_cli.py --help
python -m cli
python cli/pre_fcst_tch_realtime_cli.py
```

Python：

```python
from cli.pre_fcst_tch_realtime_cli import PreFcstTchRealtimeCli
PreFcstTchRealtimeCli.call()
```

或：

```python
from pre_fcst_tch_realtime import process
process()
```

未传入的参数先读 `resource/conf.ini`，再没有则用代码预设。`initial_time` 留空时按当前时间判定起报：北京时 12 时及以后取当日 08 时（UTC 00），否则取前一日 20 时（UTC 12）。传入 `YYYYMMDDHHMMSS` 时，用该时刻代替“现在”，时次判定规则不变。

完整运行依赖掩膜文件和模式降水目录，缺数据时无法写出预报。
