# grid_stat_merge

格站融合：用站点相对格点的偏差，按高斯权重订正网格场。

$$
\text{融合格点} = \text{原格点} + \text{偏差场}
$$

偏差：`bias = 站 − 格点插到站`；可选地形掩膜与热传导去牛眼。

## 目录结构

```
grid_stat_merge/
├── cli/              # python -m cli
├── docs/             # 程序说明
├── nbs/              # Jupyter 说明
├── resource/         # grid_stat_merge.ini 等
├── src/
│   ├── runner.py           # 主程序 process
│   ├── grid_stat_merge.py  # 算法核心
│   └── utils/util_env.py   # 读 ini
├── test/
├── 00log/ / 00temp/
└── utils/            # 仅 __init__：合并 ../../utils + src/utils
```

## 快速开始

1. 修改 `resource/grid_stat_merge.ini` 中 `grid_path` / `sta_path` / `output_path`
2. 项目根执行：

```bash
python -m cli --help
python -m cli
python -m cli --grid=a.m4 --sta=b.m3 --output=out.m4 --R=200

# 模块
# from runner import process
# process(grid_path=..., sta_path=..., output_path=...)

# 直跑
python src/runner.py
```

依赖：`numpy`、`pandas`、`scipy`、`meteva`；共享 `utils.base_plugin`（仓库根 `utils/`）。

整理登记见 `NIMM_list.md`、`00log/`。  
说明（原理 / 实现 / 参数 / 使用 / CLI）见 [docs/grid_stat_merge_程序说明.md](docs/grid_stat_merge_程序说明.md)、[nbs/grid_stat_merge_说明.ipynb](nbs/grid_stat_merge_说明.ipynb)。
