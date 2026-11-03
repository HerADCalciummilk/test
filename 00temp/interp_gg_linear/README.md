# interp_gg_linear

格点 → 格点 **双线性** 插值：按源网格索引分数重采样到目标网格；越界用 `outer_value` 外扩。由仓库根 `utils/interp_gg_pulgin.py` 分离为独立算法包。

$$
V=(1-dx)(1-dy)\,V_{j,i}+dx(1-dy)\,V_{j,i+1}+(1-dx)dy\,V_{j+1,i}+dx\,dy\,V_{j+1,i+1}
$$

## 目录结构

```
interp_gg_linear/
├── cli/              # python -m cli
├── docs/             # 程序说明
├── nbs/              # Jupyter 说明
├── resource/         # interp_gg_linear.ini 等
├── src/
│   ├── runner.py            # 主程序 process
│   ├── interp_gg_linear.py  # 算法核心
│   └── utils/util_env.py    # 读 ini
├── test/
├── 00log/ / 00temp/
└── utils/            # 仅 __init__：合并 ../../utils + src/utils
```

## 快速开始

1. 修改 `resource/interp_gg_linear.ini`：`grid_path`，以及目标网格（`domain` / `glon`+`glat` / `grid_template_path`）
2. 项目根执行：

```bash
python -m cli --help
python -m cli
python -m cli --grid=a.m4 --domain=20,50,70,140,0.1,0.1 --output=out.m4
python -m cli --grid=a.m4 --glon=70,140,0.1 --glat=15,55,0.1 --outer-value=0

# 模块
# from runner import process
# process(grid_path=..., domain=[...], outer_value=0)

# 直跑
python src/runner.py
```

依赖：`numpy`、`meteva`、`meteva_base`；共享 `utils.base_plugin`（仓库根 `utils/`）。

整理登记见 `NIMM_list.md`、`00log/`。  
说明（原理 / 实现 / 参数 / 使用 / CLI）见 [docs/interp_gg_linear_程序说明.md](docs/interp_gg_linear_程序说明.md)、[nbs/interp_gg_linear_说明.ipynb](nbs/interp_gg_linear_说明.ipynb)。
