# multi_rain_mait03_blending / mait_3h

**3 小时**多模式降水 TS 动态加权集成：历史 TS → beta 平滑权重 → 加权融合 → 频率匹配 → Cressman → Micaps3/4。

$$
w_n=(1-\alpha)\,s^{\mathrm{before}}_n+\alpha\,s^{\mathrm{now}}_n
$$

时效默认 **3–252 h，步长 3**。

## 目录结构

```
multi_rain_mait03_blending/
├── cli/                 # python -m cli
├── docs/                # 程序说明
├── nbs/                 # Jupyter 说明
├── resource/            # mait_3.ini、para_3*.ini、para_3_background*.ini、站点、掩膜
├── src/
│   ├── mait_3h.py              # 主程序 process
│   ├── mait_3_plugin.py        # TS / Cressman 插件
│   ├── mait_3_plugin_util.py   # 读数与写出
│   └── utils/util_env.py       # 读 ini
├── test/
├── 00log/ / 00temp/
└── utils/               # 仅 __init__：合并 ../../utils + src/utils
```

## 快速开始

1. 默认读 `resource/para_3.ini` / `para_3_background.ini`；本机 Windows 改 `mait_3.ini` 指向 `*_local.ini` 或用 `--para-path`  
2. 项目根执行：

```bash
python -m cli --help
python -m cli --time-inputs=202503092000
python -m cli --time-inputs=202503092000,202503100800 --is-multi=true --pro-count=4

# from mait_3h import process
# process(time_inputs=["202503092000"], is_multi=True, pro_count=4)

python src/mait_3h.py
```

依赖：`numpy`、`pandas`、`meteva`、`meteva_base`；共享 `utils.base_plugin`。

整理登记见 `NIMM_list.md`、`00log/`。  
说明（原理 / 实现 / 参数 / 使用 / CLI / 示例）见 [docs/MAIT_3H_程序说明.md](docs/MAIT_3H_程序说明.md)、[nbs/mait_3h_说明.ipynb](nbs/mait_3h_说明.ipynb)。
