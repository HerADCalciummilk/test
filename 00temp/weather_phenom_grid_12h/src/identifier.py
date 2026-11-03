# -*- coding: utf-8 -*-
"""
天气现象判识模块（附录A）
依据 QX/T 740-2024 中表A.1/A.2/A.3 的生成规则，对每个网格点判识31种天气现象是否"出现"
输出包含：12h整体出现情况 + 逐精细时步(3h)出现情况
"""
import numpy as np

from resource.weather_config import (
    RAIN_THRESHOLDS, SNOW_THRESHOLDS,
    THUNDER_RAIN_THRESH, HAIL_RAIN_THRESH, SLEET_THRESH, FRZRAIN_THRESH,
    FINE_PRECIP_THRESH,
    PTYPE_RAIN, PTYPE_SNOW, PTYPE_SLEET, PTYPE_FRZRAIN,
    THUNDER_OCCUR, HAIL_OCCUR,
    FOG_LEVEL_TO_CODE, HAZE_LEVEL_TO_CODE, SAND_LEVEL_TO_CODE,
    WEATHER_INFLUENCE_LEVEL,
)

# TCC云量单位自动识别阈值：若最大值 ≤ 1.1 视为分数(0~1)，需×100转为百分比
TCC_FRACTION_THRESHOLD = 1.1


def identify(data_dict: dict[str, np.ndarray | None]) -> dict[str, dict[str, np.ndarray]]:
    """
    判识各天气现象在12h内和各精细时步内的出现情况

    Args:
        data_dict: {变量名: ndarray[4, lat, lon]} — 来自 data_loader.load_segment()

    Returns:
        occur: {
            电码(str): {
                "12h":  ndarray[lat, lon]    bool  — 12h窗口内是否出现
                "fine": ndarray[4, lat, lon] bool  — 每个3h时步是否出现
            }
        }  共31个天气现象
    """
    R03     = data_dict.get("R03")
    PTYPE   = data_dict.get("PTYPE03")
    TCC     = data_dict.get("TCC")
    FOG     = data_dict.get("FOG")
    HAZE    = data_dict.get("HAZE")
    SAND    = data_dict.get("SAND")
    THUNDER = data_dict.get("THUNDER")
    HAIL    = data_dict.get("HAIL")

    # 获取参考形状
    ref = next((v for v in data_dict.values() if v is not None), None)
    if ref is None:
        return {}
    n_steps, nlat, nlon = ref.shape
    shape = (nlat, nlon)
    fine_shape = (n_steps, nlat, nlon)

    occur = {}

    # ══════════════════════════════════════════════════════════
    # 一、降水现象（表A.1）
    # ══════════════════════════════════════════════════════════
    if R03 is not None and PTYPE is not None:
        r03   = np.nan_to_num(R03,   nan=0.0)   # [4, lat, lon]
        ptype = np.nan_to_num(PTYPE, nan=0.0)   # [4, lat, lon]

        # 各相态逐步降水量
        rain_step  = np.where(ptype == PTYPE_RAIN,   r03, 0.0)   # [4, lat, lon]
        snow_step  = np.where(ptype == PTYPE_SNOW,   r03, 0.0)
        sleet_step = np.where(ptype == PTYPE_SLEET,  r03, 0.0)
        frz_step   = np.where(ptype == PTYPE_FRZRAIN, r03, 0.0)

        # 12h累积量
        rain_accum = rain_step.sum(axis=0)   # [lat, lon]
        snow_accum = snow_step.sum(axis=0)
        r_total    = r03.sum(axis=0)

        # 雷暴/冰雹辅助标志
        thunder_arr = np.nan_to_num(THUNDER, nan=0.0) if THUNDER is not None \
                      else np.zeros(fine_shape)
        hail_arr    = np.nan_to_num(HAIL,    nan=0.0) if HAIL    is not None \
                      else np.zeros(fine_shape)
        thunder_any = (thunder_arr >= THUNDER_OCCUR).any(axis=0)    # [lat, lon]
        hail_any    = (hail_arr    >= HAIL_OCCUR   ).any(axis=0)

        # ── 降雨量级（07~12）──────────────────────────────────
        # fine：该时步有雨（相态为雨 且 降水量>阈值）
        fine_rain = (r03 > FINE_PRECIP_THRESH) & (ptype == PTYPE_RAIN)
        for code, (lo, hi) in RAIN_THRESHOLDS.items():
            occur[code] = {
                "12h":  (rain_accum >= lo) & (rain_accum < hi),
                "fine": fine_rain,
            }

        # ── 降雪量级（14~17, 36, 37）──────────────────────────
        fine_snow = (r03 > FINE_PRECIP_THRESH) & (ptype == PTYPE_SNOW)
        for code, (lo, hi) in SNOW_THRESHOLDS.items():
            occur[code] = {
                "12h":  (snow_accum >= lo) & (snow_accum < hi),
                "fine": fine_snow,
            }

        # ── 雷阵雨（04）──────────────────────────────────────
        fine_thunder_rain = (r03 > FINE_PRECIP_THRESH) & (thunder_arr >= THUNDER_OCCUR)
        occur["04"] = {
            "12h":  (r_total >= THUNDER_RAIN_THRESH) & thunder_any,
            "fine": fine_thunder_rain,
        }

        # ── 雷阵雨并伴有冰雹（05）────────────────────────────
        # 12h条件：总降水≥阈值 且 降水时段内有冰雹
        hail_in_precip = ((r03 > FINE_PRECIP_THRESH) & (hail_arr >= HAIL_OCCUR)).any(axis=0)
        fine_hail_rain = (r03 > FINE_PRECIP_THRESH) & (hail_arr >= HAIL_OCCUR)
        occur["05"] = {
            "12h":  (r_total >= HAIL_RAIN_THRESH) & hail_in_precip,
            "fine": fine_hail_rain,
        }

        # ── 雨夹雪（06）──────────────────────────────────────
        fine_sleet = sleet_step > FINE_PRECIP_THRESH
        occur["06"] = {
            "12h":  (sleet_step > SLEET_THRESH).any(axis=0),
            "fine": fine_sleet,
        }

        # ── 冻雨（19）────────────────────────────────────────
        fine_frz = frz_step > FINE_PRECIP_THRESH
        occur["19"] = {
            "12h":  (r_total >= FRZRAIN_THRESH) & (frz_step > FRZRAIN_THRESH).any(axis=0),
            "fine": fine_frz,
        }

    # ══════════════════════════════════════════════════════════
    # 二、天空状况（表A.3）
    # ══════════════════════════════════════════════════════════
    if TCC is not None:
        tcc = np.nan_to_num(TCC, nan=50.0)   # 缺测默认多云
        # 自动识别单位：0~1 → 转为 0~100
        if np.nanmax(tcc) <= TCC_FRACTION_THRESHOLD:
            tcc = tcc * 100.0

        # 晴（00）：cl ≤ 30%
        fine_qing  = tcc <= 30.0
        occur["00"] = {"12h": fine_qing.any(axis=0),  "fine": fine_qing}

        # 多云（01）：30% < cl < 90%
        fine_duoyun = (tcc > 30.0) & (tcc < 90.0)
        occur["01"] = {"12h": fine_duoyun.any(axis=0), "fine": fine_duoyun}

        # 阴（02）：cl ≥ 90%
        fine_yin   = tcc >= 90.0
        occur["02"] = {"12h": fine_yin.any(axis=0),   "fine": fine_yin}

    # ══════════════════════════════════════════════════════════
    # 三、视程障碍 - 雾（表A.2）
    # ══════════════════════════════════════════════════════════
    if FOG is not None:
        fog = np.nan_to_num(FOG, nan=0.0).astype(np.int8)   # [4, lat, lon]
        for level, code in FOG_LEVEL_TO_CODE.items():
            fine_fog = (fog == level)
            occur[code] = {"12h": fine_fog.any(axis=0), "fine": fine_fog}

    # ══════════════════════════════════════════════════════════
    # 四、视程障碍 - 霾（表A.2）
    # ══════════════════════════════════════════════════════════
    if HAZE is not None:
        haze = np.nan_to_num(HAZE, nan=0.0).astype(np.int8)
        for level, code in HAZE_LEVEL_TO_CODE.items():
            fine_haze = (haze == level)
            occur[code] = {"12h": fine_haze.any(axis=0), "fine": fine_haze}

    # ══════════════════════════════════════════════════════════
    # 五、视程障碍 - 沙尘（表A.2）
    # ══════════════════════════════════════════════════════════
    if SAND is not None:
        sand = np.nan_to_num(SAND, nan=0.0).astype(np.int8)
        for level, code in SAND_LEVEL_TO_CODE.items():
            fine_sand = (sand == level)
            occur[code] = {"12h": fine_sand.any(axis=0), "fine": fine_sand}

    # ══════════════════════════════════════════════════════════
    # 补全：确保31种可选现象都有对应条目（缺失的填False）
    # ══════════════════════════════════════════════════════════
    for code in WEATHER_INFLUENCE_LEVEL:
        if code not in occur:
            occur[code] = {
                "12h":  np.zeros(shape,      dtype=bool),
                "fine": np.zeros(fine_shape, dtype=bool),
            }

    return occur


# ══════════════════════════════════════════════════════════════
# 算法插件 (Plugin) — DIA 诊断类
# ══════════════════════════════════════════════════════════════

class DIA_WeatherPhenomIdentifier:
    """
    天气现象判识算法插件 (DIA - Diagnostic)

    依据 QX/T 740-2024 附录A 表A.1/A.2/A.3，对每个网格点判识31种天气现象
    是否在12h时段内及各精细时步(3h)出现。

    设计规范：
      - 严禁文件 I/O；输入输出均为内存对象 (ndarray / dict)
      - 环境无关：阈值通过 __init__ 显式注入，无隐藏全局依赖
      - 向量化计算：全程 NumPy，严禁原生 Python for 循环处理网格数据

    Args:
        config (dict | None): 可选阈值配置字典，用于覆盖默认值。
            支持的键（均与 resource.weather_config 同名）：
              RAIN_THRESHOLDS, SNOW_THRESHOLDS, THUNDER_RAIN_THRESH,
              HAIL_RAIN_THRESH, SLEET_THRESH, FRZRAIN_THRESH,
              FINE_PRECIP_THRESH, PTYPE_RAIN, PTYPE_SNOW, PTYPE_SLEET,
              PTYPE_FRZRAIN, THUNDER_OCCUR, HAIL_OCCUR,
              FOG_LEVEL_TO_CODE, HAZE_LEVEL_TO_CODE, SAND_LEVEL_TO_CODE,
              WEATHER_INFLUENCE_LEVEL
            None 表示使用 resource.weather_config 标准配置（推荐）。

    Example:
        >>> plugin = DIA_WeatherPhenomIdentifier()
        >>> occur = plugin.process(data_dict)
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config   # 预留：自定义阈值注入钩子

    def process(self, data_dict: dict) -> dict:
        """
        判识各天气现象在12h内和各精细时步内的出现情况。

        Args:
            data_dict (dict): {变量名: ndarray[4, lat, lon] float32}
                来自 data_loader.load_segment() 的原始数据字典。
                必须包含: R03, PTYPE03, TCC, FOG, HAZE, SAND, THUNDER, HAIL

        Returns:
            dict: {
                电码(str): {
                    "12h":  ndarray[lat, lon]    bool — 12h窗口内是否出现,
                    "fine": ndarray[4, lat, lon] bool — 每个3h时步是否出现
                }
            }  共31个天气现象

        Raises:
            ValueError: 当 data_dict 为空或所有变量均为 None 时
        """
        return identify(data_dict)
