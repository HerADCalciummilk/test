# frequency_matching_rain03

逐 **3 小时**单模式降水频率匹配订正：历史相似个例 → 分位订正 →（短时效可选光流平流）→ Cressman → Micaps3/4/NC。  
由 `QPFFrequencyMatch_Rain03` 按 NIMM 布局整理。时效默认 **3–252 h，步长 3**。

$$
V' = f_k + \frac{f_{k+1}-f_k}{m_{k+1}-m_k}\,(V-m_k)
$$

## 目录结构

```
frequency_matching_rain03/
├── cli/                 # python -m cli
├── docs/                # 程序说明
├── nbs/                 # Jupyter 说明
├── resource/            # qpf_fm.ini、path.json、config.json、站点、掩膜
├── src/
│   ├── runner.py        # 主程序 process / main
│   ├── proc/            # FM / 相似 / 光流 / 平流 / Cressman
│   └── utils/           # 类型、日志、ini
├── test/
├── 00log/ / 00temp/
└── utils/               # 仅 __init__：合并 ../../utils + src/utils
```

## 快速开始

1. 修改 `resource/path.json` 中模式 / 实况 / 输出路径  
2. 项目根执行：

```bash
python -m cli --help
python -m cli ecmwf 202605220800
python -m cli ecmwf 202605220000 202605221200

# from runner import process
# process(data_key="ecmwf", run_times=["202605220800"])

python src/runner.py ecmwf 202605220800
```

依赖：`numpy`、`scipy`、`meteva_base`（未安装会报错：`pip install meteva_base`）。路径用 `meb.get_path`，Micaps 读写走 meteva_base。并行：`QPF_LEADTIME_WORKERS`、`QPF_DISABLE_LEADTIME_MP=1`。

整理登记见 `NIMM_list.md`、`00log/`。  
说明（原理 / 实现 / 参数 / 使用 / CLI / 示例）见 [docs/frequency_matching_rain03_算法说明.md](docs/frequency_matching_rain03_算法说明.md)、[nbs/frequency_matching_rain03_说明.ipynb](nbs/frequency_matching_rain03_说明.ipynb)。
