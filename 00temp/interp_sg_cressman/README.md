# interp_sg_cressman

站点 → 格点 **Cressman** 插值：按 `r_list` 多半径逐级订正；可选背景场经双线性对齐到目标网格。

$$
w(d,R)=\frac{R^{2}-d^{2}}{R^{2}+d^{2}}\quad(d<R)
$$

有邻站的格点写为站点加权平均；无邻站的格点保留背景（或 0）。

## 目录结构

```
interp_sg_cressman/
├── cli/              # python -m cli
├── docs/             # 程序说明
├── nbs/              # Jupyter 说明
├── resource/         # interp_sg_cressman.ini 等
├── src/
│   ├── runner.py              # 主程序 process
│   ├── interp_sg_cressman.py  # 算法核心
│   └── utils/util_env.py      # 读 ini
├── test/
├── 00log/ / 00temp/
└── utils/            # 仅 __init__：合并 ../../utils + src/utils
```

## 快速开始

1. 修改 `resource/interp_sg_cressman.ini`：`sta_path`，以及目标网格（`domain` / `glon`+`glat` / `background_path` / `grid_template_path`）
2. 项目根执行：

```bash
python -m cli --help
python -m cli
python -m cli --sta=a.m3 --background=b.m4 --output=out.m4
python -m cli --sta=a.m3 --domain=20,50,70,140,0.1,0.1 --r-list=60000,40000,20000

# 模块
# from runner import process
# process(sta_path=..., domain=[...], r_list=[60000, 40000, 20000])

# 直跑
python src/runner.py
```

依赖：`numpy`、`scipy`、`meteva`、`meteva_base`；共享 `utils.base_plugin`、`utils.interp_gg_pulgin`（仓库根 `utils/`）。

整理登记见 `NIMM_list.md`、`00log/`。  
说明（原理 / 实现 / 参数 / 使用 / CLI）见 [docs/interp_sg_cressman_程序说明.md](docs/interp_sg_cressman_程序说明.md)、[nbs/interp_sg_cressman_说明.ipynb](nbs/interp_sg_cressman_说明.ipynb)。
