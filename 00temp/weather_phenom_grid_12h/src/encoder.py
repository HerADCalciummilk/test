# -*- coding: utf-8 -*-
"""
天气现象编码模块（第6章）
将 idx_final_A, idx_final_B, logic 编码为5位整型综合电码
格式：K * 10000 + AA * 100 + BB
  单一：K=0，AA=BB=现象电码 → KAAAA（如多云: 00101）
  双重：K=逻辑电码，AA=前，BB=后 → KAABB（如阴转小雨: 10207）

性能优化：接收 int8 索引，通过查找表一次性完成编码，无 Python 循环
"""
import numpy as np

from resource.weather_config import WEATHER_CODE_NAME, LOGIC_CODE_RELATION, WEATHER_INFLUENCE_LEVEL

# 构建索引→整数电码值查找表
_SORTED_CODES = sorted(WEATHER_INFLUENCE_LEVEL.keys(), key=lambda c: WEATHER_INFLUENCE_LEVEL[c])
_CODE_INT_LUT = np.array([int(c) for c in _SORTED_CODES], dtype=np.int32)


def encode(idx_final_A: np.ndarray, idx_final_B: np.ndarray,
           logic: np.ndarray) -> np.ndarray:
    """
    生成5位综合电码

    Args:
        idx_final_A : [lat, lon] int8 — 表述在前的天气现象索引
        idx_final_B : [lat, lon] int8 — 表述在后的天气现象索引（单一时 = idx_final_A）
        logic       : [lat, lon] int8 — 0/1/2/3

    Returns:
        result  : [lat, lon] int32 — 5位整型电码（如 10207, 00101）
    """
    # 通过查找表一次性将索引转为电码整数值（纯 numpy 索引，无循环）
    aa = _CODE_INT_LUT[idx_final_A.astype(np.intp)]
    bb = _CODE_INT_LUT[idx_final_B.astype(np.intp)]
    k  = logic.astype(np.int32)

    return (k * 10000 + aa * 100 + bb).astype(np.int32)


def decode(code_int: int) -> dict:
    """
    解析单个整型综合电码（用于调试/验证）

    Args:
        code_int : 如 10207

    Returns:
        dict 包含逻辑关系、天气现象名称、预报表述
    """
    s     = f"{int(code_int):05d}"
    k     = int(s[0])
    aa    = s[1:3]
    bb    = s[3:5]
    logic = LOGIC_CODE_RELATION.get(k, "未知")
    na    = WEATHER_CODE_NAME.get(aa, f"未知({aa})")
    nb    = WEATHER_CODE_NAME.get(bb, f"未知({bb})")
    desc  = na if k == 0 else f"{na}{logic}{nb}"
    return {
        "综合电码":   s,
        "逻辑关系电码": k,
        "逻辑关系":   logic,
        "天气现象A电码": aa,
        "天气现象A":  na,
        "天气现象B电码": bb,
        "天气现象B":  nb,
        "预报表述":   desc,
    }


# ──────────────────────────────────────────────────────────────
# 验证：运行标准示例（需要从项目根目录以模块方式运行）
# python -m src.encoder
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from resource.weather_config import STANDARD_EXAMPLES
    print("=== 编码/解码验证（标准示例）===")
    for ex in STANDARD_EXAMPLES:
        result = decode(int(ex["电码"]))
        ok = "✓" if result["预报表述"] == ex["表述"] else f"✗(得到:{result['预报表述']})"
        print(f"  {ex['电码']} → {result['预报表述']:12s}  {ok}")


# ══════════════════════════════════════════════════════════════
# 算法插件 (Plugin) — DIA 诊断类
# ══════════════════════════════════════════════════════════════

class DIA_WeatherPhenomEncoder:
    """
    天气现象综合电码编码算法插件 (DIA - Diagnostic)

    依据 QX/T 740-2024 第6章，将判识与选取结果编码为5位整型综合电码。

    编码格式：
      - 单一现象：K=0, AA=BB=现象电码 → KAAAA (如多云: 00101)
      - 双重现象：K=逻辑电码, AA=前, BB=后 → KAABB (如阴转小雨: 10207)

    设计规范：
      - 严禁文件 I/O；输入输出均为内存对象 (ndarray)
      - 向量化编码：通过查找表(LUT)一次性完成，无 Python 循环

    Args:
        config (dict | None): 可选配置字典，用于覆盖默认值。
            支持的键：WEATHER_CODE_NAME, LOGIC_CODE_RELATION, WEATHER_INFLUENCE_LEVEL
            None 表示使用 resource.weather_config 标准配置（推荐）。

    Example:
        >>> plugin = DIA_WeatherPhenomEncoder()
        >>> result = plugin.process(idx_final_A, idx_final_B, logic)
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config   # 预留：自定义编码配置注入钩子

    def process(self, idx_final_A: np.ndarray, idx_final_B: np.ndarray,
                logic: np.ndarray) -> np.ndarray:
        """
        生成5位综合电码网格。

        Args:
            idx_final_A (np.ndarray): [lat, lon] int8 — 表述在前的天气现象索引
            idx_final_B (np.ndarray): [lat, lon] int8 — 表述在后的天气现象索引
                                       （单一现象时 = idx_final_A）
            logic       (np.ndarray): [lat, lon] int8 — 逻辑关系编码 (0/1/2/3)

        Returns:
            np.ndarray: [lat, lon] int32 — 5位整型综合电码
                示例值: 0 → 晴(00000), 101 → 多云(00101), 10207 → 阴转小雨
        """
        return encode(idx_final_A, idx_final_B, logic)
