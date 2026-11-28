# 地形精细化插值规范副本

本目录独立复制自服务器回传版本，原版本不变。当前已验证产品为EC温度站点和5km格点；新NC输出通过独立转换测试，完整新流程需服务器复测。

## 目录

- `src/`：插件和核心算法，源码统一小写下划线命名。
- `cli/orographic_nwp_3d_downscaling_cli.py`：`process` 入口，参数来自调用、`resource/conf.ini` 和函数预设。
- `resource/config/`：当前生效的模式、路径、网格配置。
- `resource/Fast_refine_interp_5km.ini`：当前生效的运行开关和模式时效范围。
- `resource/terrain/`：原有真实地形与分区。
- `resource/maps/`：原有地图资源。
- `resource/legacy_pylib/`：原有编译库归档，保留供兼容核查，不保证跨系统可导入。
- `resource/sample*/`：历史配置样例，不是当前运行配置。
- `test/`：独立测试；`nbs/`：调用示例；`docs/`：说明与整理记录。

## 运行

在本目录执行，选择已有相应输入数据的业务时间：

```bash
python -m cli begin_date=2026111813 operation=i debug=1 update=1
```

在 `00temp` 下也可以：

```bash
python -m orographic_nwp_3d_downscaling begin_date=2026111813 operation=i debug=1 update=1
```

默认 EC、5km。省略的路径跟随本包位置。数据和输出配置仍保留服务器绝对路径，不会自动改为本机路径。部署前修改 `resource/config` 内的配置。运行开关见 `resource/conf.ini`，要素和时效见 `resource/Fast_refine_interp_5km.ini`。

验证：`python -m pytest test -q`。完整依赖和配置见 `docs/orographic_nwp_3d_downscaling_config.md`，整理过程见 `docs/本地整理记录.md`。
