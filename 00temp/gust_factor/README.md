# gust_factor

根据历史站点「10 m 平均风速预报 + 阵风观测」统计阵风系数，并用 U/V 格点订正阵风预报。

$$
\mathrm{param}=\frac{\sum(\mathrm{obs}\cdot\mathrm{fcst})}{\sum\mathrm{fcst}^{2}},\quad
\mathrm{gust}=\max\bigl(\mathrm{ws},\;\mathrm{clamp}(a\cdot\mathrm{ws}\cdot\mathrm{param}+b)\bigr)
$$

无独立 `runner`；调度入口为 `src/gust_factor.py` 的 `process`。

## 目录结构

```
gust_factor/
├── cli/              # python -m cli
├── docs/             # 程序说明
├── nbs/              # Jupyter 说明
├── resource/         # gust_factor.ini、样例 CSV/NC
├── src/
│   ├── gust_factor.py     # 算法核 + process
│   └── utils/util_env.py # 读 ini
├── test/
├── 00log/ / 00temp/
└── utils/            # 仅 __init__：合并 ../../utils + src/utils
```

## 快速开始

1. 按需修改 `resource/gust_factor.ini`
2. 项目根执行：

```bash
python -m cli --help
python -m cli
python -m cli --mode=calc
python -m cli --mode=correct --fore-hour=24

# 模块
# from gust_factor import process
# process(mode="all")

# 直跑
python src/gust_factor.py
```

依赖：`numpy`、`pandas`、`meteva_base`；可选 `matplotlib`（对比图）。

整理登记见 `NIMM_list.md`、`00log/`。  
说明见 [docs/gust_factor_程序说明.md](docs/gust_factor_程序说明.md)、[nbs/gust_factor_说明.ipynb](nbs/gust_factor_说明.ipynb)。
