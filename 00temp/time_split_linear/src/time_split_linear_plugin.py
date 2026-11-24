# -*- coding: utf-8 -*-
"""时间线性拆分插件。插值公式在 ``TimeSplit``。"""
from cal_griddata_TimeSplit_plugin import TimeSplit


class TimeSplitLinearPlugin(TimeSplit):
    """沿预报时效或起报时间把粗时间场插成细时间场。"""
