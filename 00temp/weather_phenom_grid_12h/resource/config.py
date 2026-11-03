# -*- coding: utf-8 -*-
"""
运行环境配置（部署环境相关）
包含：数据根目录、NC文件路径模板、路径生成辅助函数

算法结构常量（变量分组、时效上限等与环境无关的参数）
请见 resource/data_schema.py。

环境变量优先级（高 → 低）：
  1. 命令行 --data-root 参数（src/main.py 写入 SCMOC_DATA_ROOT）
  2. 系统环境变量 SCMOC_DATA_ROOT
  3. 本文件中的默认值（仅作开发参考）
"""
import os
from datetime import datetime

# 从 data_schema 导入算法结构常量（保持向后兼容的 * 导出）
from resource.data_schema import (
    VARS_240H, VARS_72H, ALL_VARS,
    FORECAST_INTERVAL,
    MAX_FORECAST_HOUR_240, MAX_FORECAST_HOUR_72,
    INIT_HOURS,
    get_max_forecast_hour, get_forecast_hours,
)

# ==============================================================================
# 运行环境配置
# ==============================================================================

# 数据根目录：优先读取环境变量，未设置时使用默认值（仅作开发参考）
# 生产部署：set SCMOC_DATA_ROOT=\\your_server\your_share\SCMOC
DATA_ROOT: str = os.environ.get(
    "SCMOC_DATA_ROOT",
    r"\\10.28.16.251\pool_public\SCMOC"
)

# ==============================================================================
# NC 文件路径模板（兼容旧接口，不依赖 meteva）
# ==============================================================================
NC_FILE_TEMPLATE  = "{root}/{var}/{init_time}/{init_time}.{fh:03d}.nc"
VAR_DIR_TEMPLATE  = "{root}/{var}"
INIT_DIR_TEMPLATE = "{root}/{var}/{init_time}"


# ==============================================================================
# 路径生成辅助函数
# ==============================================================================

def get_nc_path_fmt(var: str) -> str:
    """
    返回 meteva get_path 所需的路径格式字符串
    占位符规则（来自 meteva/base/tool/path_tools.py）：
      YYYYMMDDHH → 起报时次
      TTT         → 3位预报时效小时数（如 003, 012, 240）
    用法：get_path(fmt, init_dt, dt=fh_int)
    """
    return rf"{DATA_ROOT}\{var}\YYYYMMDDHH\YYYYMMDDHH.TTT.nc"


def str_to_datetime(init_time: str) -> datetime:
    """将起报时次字符串转为 datetime 对象，格式 YYYYMMDDHH"""
    return datetime.strptime(init_time, "%Y%m%d%H")


def get_var_dir(var: str) -> str:
    """获取变量目录路径"""
    return VAR_DIR_TEMPLATE.format(root=DATA_ROOT, var=var)


def get_init_dir(var: str, init_time: str) -> str:
    """获取时次目录路径"""
    return INIT_DIR_TEMPLATE.format(root=DATA_ROOT, var=var, init_time=init_time)


def get_nc_path(var: str, init_time: str, forecast_hour: int) -> str:
    """获取 NC 文件完整路径（兼容旧接口，不依赖 meteva）"""
    return NC_FILE_TEMPLATE.format(
        root=DATA_ROOT, var=var, init_time=init_time, fh=forecast_hour
    )


def get_all_nc_paths(var: str, init_time: str) -> list[str]:
    """获取某个变量某个时次的所有 NC 文件路径"""
    return [get_nc_path(var, init_time, fh) for fh in get_forecast_hours(var)]


# ==============================================================================
# 使用示例
# ==============================================================================
if __name__ == "__main__":
    var, init_time = "R03", "2026030100"
    print(f"DATA_ROOT      : {DATA_ROOT}")
    print(f"变量目录       : {get_var_dir(var)}")
    print(f"时次目录       : {get_init_dir(var, init_time)}")
    print(f"前5个NC文件路径:")
    for path in get_all_nc_paths(var, init_time)[:5]:
        print(f"  {path}")
    print(f"\n--- FOG变量 (72h) ---")
    for path in get_all_nc_paths("FOG", init_time)[:3]:
        print(f"  {path}")
