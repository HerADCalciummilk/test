# -*- coding: utf-8 -*-
"""读取快速精细化插值 ini。显式覆盖优先于 ini，缺键时用 resource/conf.ini 的预设。"""


def _coerce_override(kind, raw):
    """把显式参数或缺失键的预设转成与 ini 读取相同的类型。"""
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, int) and raw in (0, 1):
            return bool(raw)
        text = str(raw).strip().lower()
        if text in ("1", "true", "yes", "y", "on"):
            return True
        if text in ("0", "false", "no", "n", "off"):
            return False
        raise ValueError("无法解析布尔值: %r" % (raw,))
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    if kind == "csv":
        if isinstance(raw, (list, tuple)):
            return [str(item) for item in raw]
        return str(raw).split(",")
    if kind == "csv_strip":
        if isinstance(raw, (list, tuple)):
            return [str(item).strip() for item in raw]
        return [item.strip() for item in str(raw).split(",")]
    if kind == "forecast":
        if isinstance(raw, (list, tuple)):
            return [str(item).strip() for item in raw]
        return [item.strip() for item in str(raw).replace("\n", "").split(",")]
    return raw if isinstance(raw, str) else str(raw)


def _ini_value(config, section, option, kind):
    if kind == "bool":
        return config.getboolean(section, option)
    if kind == "int":
        return config.getint(section, option)
    if kind == "float":
        return config.getfloat(section, option)
    if kind == "csv":
        return config.get(section, option).split(",")
    if kind == "csv_strip":
        return [item.strip() for item in config.get(section, option).split(",")]
    if kind == "forecast":
        return [item.strip() for item in config.get(section, option).replace("\n", "").split(",")]
    return config.get(section, option)


def _option_value(config, overrides, section, option, kind, preset):
    """显式覆盖 > ini > 与 resource/conf.ini 相同的预设。"""
    token = "%s.%s" % (section, option)
    if overrides and token in overrides and overrides[token] is not None:
        return _coerce_override(kind, overrides[token])
    if config.has_option(section, option):
        return _ini_value(config, section, option, kind)
    return _coerce_override(kind, preset)


_INSTANT_SPEC = (
    ("dem_head", "str", "DEM"),
    ("dem_format", "str", "tif"),
    ("recall", "bool", False),
    ("Interp_Time", "bool", False),
    ("validate", "bool", False),
    ("del_no_eta", "bool", False),
    ("out_China", "bool", False),
    ("eta_cmn_out", "bool", False),
    ("VR_plot", "bool", False),
    ("rlt_plot", "bool", False),
    ("plot_format", "csv", "png"),
    ("MICAPS_out", "bool", False),
    ("PQ_shortname", "csv_strip", "2t"),
)
_POOL_SPEC = (
    ("FH_parallel", "bool", False),
    ("FH_max_pcount", "int", 1),
    ("FH_DI_timeout", "int", 900),
    ("FH_TI_timeout", "int", 900),
    ("BT_parallel", "bool", False),
    ("BT_max_pcount", "int", 1),
    ("BT_timeout", "int", 900),
    ("Para_parallel", "bool", False),
    ("Para_max_pcount", "int", 1),
    ("Para_timeout", "int", 900),
)
_THRESHOLD_PRESET = (
    ("2t", 2.0),
    ("2rh", 10.0),
    ("10ws", 2.0),
    ("10u", 2.0),
    ("10v", 2.0),
    ("2t_max", 2.0),
    ("2t_min", 2.0),
    ("2rh_max", 10.0),
    ("2rh_min", 10.0),
    ("10ws_max", 2.0),
)


def _load_fast_refine_sections(config, args, overrides):
    """读取算法 ini。覆盖字典的键是 ``节.键``，例如 ``InstantInfo.validate``。"""
    overrides = overrides or {}
    instant = {}
    for option, kind, preset in _INSTANT_SPEC:
        instant[option] = _option_value(config, overrides, "InstantInfo", option, kind, preset)
    swork = _option_value(config, overrides, "InstantInfo", "validate_area", "str", "NONE")
    if str(swork).upper() != "NONE":
        instant["Prov_code"] = [int(x) for x in str(swork).split(",")]
    else:
        instant["Prov_code"] = None

    maxmin = {
        "Interp_Maxmin": _option_value(config, overrides, "MaxMinInfo", "Interp_Maxmin", "bool", False),
    }
    update_token = "MaxMinInfo.update"
    if update_token in overrides and overrides[update_token] is not None:
        maxmin["update"] = _coerce_override("bool", overrides[update_token])
    elif config.has_option("MaxMinInfo", "update"):
        maxmin["update"] = config.getboolean("MaxMinInfo", "update")
    else:
        maxmin["update"] = args.update >= 1
    maxmin["validate"] = _option_value(config, overrides, "MaxMinInfo", "validate", "bool", False)
    maxmin["forecast_time"] = _option_value(
        config, overrides, "MaxMinInfo", "forecast_time", "forecast", "012_036"
    )
    site = {
        "custom_path": _option_value(
            config, overrides, "SiteInfo", "custom_path", "str", "sample_minimal/Parameter/Station1"
        ),
    }
    pool = {}
    for option, kind, preset in _POOL_SPEC:
        pool[option] = _option_value(config, overrides, "PoolInfo", option, kind, preset)
    threshold = {}
    for option, preset in _THRESHOLD_PRESET:
        threshold[option] = _option_value(config, overrides, "threshold", option, "float", preset)
    return instant, maxmin, site, pool, threshold
