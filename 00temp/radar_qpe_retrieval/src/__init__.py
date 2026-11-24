#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""核心算法子包。

- ``qpe``：``QPEPlugin`` 等，输入/输出为 meteva ``grid_data`` 网格。
- ``radar_qc``：``PolarRadarQCPlugin``，输入 Py-ART ``Radar``，
  质控后可输出 meb 六维网格供 ``QPEPlugin`` 直接使用。
"""

from .qpe import (
    QPEPlugin,
    ZtoR,
    EstimateRainRateA,
    EstimateRainRateHydro,
    EstimateRainRateKdp,
    EstimateRainRateZ,
    EstimateRainRateZA,
    EstimateRainRateZKdp,
    EstimateRainRateZPoly,
    EstimateZtoR,
    est_rain_rate_a,
    est_rain_rate_hydro,
    est_rain_rate_kdp,
    est_rain_rate_z,
    est_rain_rate_za,
    est_rain_rate_zkdp,
    est_rain_rate_zpoly,
)
from .radar_qc import (
    PolarQCResult,
    PolarRadarQCPlugin,
    apply_gatefilter_to_radar_fields,
    compute_beam_blockage_mask,
)

__all__ = [
    "QPEPlugin",
    "PolarQCResult",
    "PolarRadarQCPlugin",
    "apply_gatefilter_to_radar_fields",
    "compute_beam_blockage_mask",
    "EstimateRainRateZ",
    "EstimateRainRateZPoly",
    "EstimateRainRateKdp",
    "EstimateRainRateA",
    "EstimateRainRateZKdp",
    "EstimateRainRateZA",
    "EstimateRainRateHydro",
    "EstimateZtoR",
    "est_rain_rate_z",
    "est_rain_rate_zpoly",
    "est_rain_rate_kdp",
    "est_rain_rate_a",
    "est_rain_rate_zkdp",
    "est_rain_rate_za",
    "est_rain_rate_hydro",
    "ZtoR",
]
