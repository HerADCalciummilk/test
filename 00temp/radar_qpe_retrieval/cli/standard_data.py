# -*- coding: utf-8 -*-
"""标准格式体积基数据轻量读取（CLI 附属，非独立 io 包）。

仅依赖标准库与 numpy，不依赖 cinrad / pyart。
入口::

    from radar_qpe_retrieval.cli.standard_data import load_standard_radar, StandardDataLite
"""
from __future__ import annotations

import bz2
import gzip
from typing import Any


class RadarDecodeError(Exception):
    """无法正确解码雷达基数据。"""


def prepare_file(file: Any) -> Any:
    """打开基数据路径或透传已打开的二进制流；按魔数自动识别 gzip/bz2。"""
    if hasattr(file, "read"):
        return file
    path = str(file)
    with open(path, "rb") as f:
        magic = f.read(3)
    if magic.startswith(b"\x1f\x8b"):
        return gzip.GzipFile(path, "rb")
    if magic.startswith(b"BZh"):
        return bz2.BZ2File(path, "rb")
    return open(path, "rb")


# ---- SDD binary layouts ----
import numpy as np

generic_header = [
    ("magic_number", "i4"),
    ("major_version", "i2"),
    ("minor_version", "i2"),
    ("generic_type", "i4"),
    ("product_type", "i4"),
    ("res1", "16c"),
]

generic_header_dtype = np.dtype(generic_header)

site_config = [
    ("site_code", "S8"),
    ("site_name", "S32"),
    ("Latitude", "f4"),
    ("Longitude", "f4"),
    ("antenna_height", "i4"),
    ("ground_height", "i4"),
    ("frequency", "f4"),
    ("beam_width_hori", "f4"),
    ("beam_width_vert", "f4"),
    ("RDA_version", "i4"),
    ("radar_type", "i2"),
    ("antenna_gain", "i2"),
    ("trans_loss", "i2"),
    ("recv_loss", "i2"),
    ("other_loss", "i2"),
    ("res2", "46c"),
]

site_config_dtype = np.dtype(site_config)

task_config = [
    ("task_name", "S32"),
    ("task_dsc", "S128"),
    ("polar_type", "i4"),
    ("scan_type", "i4"),
    ("pulse_width", "i4"),
    ("scan_start_time", "i4"),
    ("cut_number", "i4"),
    ("hori_noise", "f4"),
    ("vert_noise", "f4"),
    ("hori_cali", "f4"),
    ("vert_cali", "f4"),
    ("hori_tmp", "f4"),
    ("vert_tmp", "f4"),
    ("ZDR_cali", "f4"),
    ("PHIDP_cali", "f4"),
    ("LDR_cali", "f4"),
    ("res3", "40c"),
]

task_config_dtype = np.dtype(task_config)

cut_config = [
    ("process_mode", "i4"),
    ("wave_form", "i4"),
    ("PRF1", "f4"),
    ("PRF2", "f4"),
    ("dealias_mode", "i4"),
    ("azimuth", "f4"),
    ("elev", "f4"),
    ("start_angle", "f4"),
    ("end_angle", "f4"),
    ("angular_reso", "f4"),
    ("scan_spd", "f4"),
    ("log_reso", "i4"),
    ("dop_reso", "i4"),
    ("max_range1", "i4"),
    ("max_range2", "i4"),
    ("start_range", "i4"),
    ("sample1", "i4"),
    ("sample2", "i4"),
    ("phase_mode", "i4"),
    ("atmos_loss", "f4"),
    ("nyquist_spd", "f4"),
    ("moments_mask", "i8"),
    ("moments_size_mask", "i8"),
    ("misc_filter_mask", "i4"),
    ("SQI_thres", "f4"),
    ("SIG_thres", "f4"),
    ("CSR_thres", "f4"),
    ("LOG_thres", "f4"),
    ("CPA_thres", "f4"),
    ("PMI_thres", "f4"),
    ("DPLOG_thres", "f4"),
    ("res_thres", "4V"),
    ("dBT_mask", "i4"),
    ("dBZ_mask", "i4"),
    ("vel_mask", "i4"),
    ("sw_mask", "i4"),
    ("DP_mask", "i4"),
    ("res_mask", "12V"),
    ("scan_sync", "i4"),
    ("direction", "i4"),
    ("ground_clutter_classifier_type", "i2"),
    ("ground_clutter_filter_type", "i2"),
    ("ground_clutter_filter_notch_width", "i2"),
    ("ground_clutter_filter_window", "i2"),
    ("res4", "72V"),
]

cut_config_dtype = np.dtype(cut_config)

radial_header = [
    ("radial_state", "i4"),
    ("spot_blank", "i4"),
    ("seq_number", "i4"),
    ("radial_number", "i4"),
    ("elevation_number", "i4"),
    ("azimuth", "f4"),
    ("elevation", "f4"),
    ("seconds", "i4"),
    ("microseconds", "i4"),
    ("data_length", "i4"),
    ("moment_number", "i4"),
    ("res5", "i2"),
    ("hori_est_noise", "i2"),
    ("vert_est_noise", "i2"),
    ("zip_type", "c"),
    ("res6", "13c"),
]

radial_header_dtype = np.dtype(radial_header)

moment_header = [
    ("data_type", "i4"),
    ("scale", "i4"),
    ("offset", "i4"),
    ("bin_length", "i2"),
    ("flags", "i2"),
    ("block_length", "i4"),
    ("res", "12c"),
]

moment_header_dtype = np.dtype(moment_header)

product_header = [
    ("product_type", "i4"),
    ("product_name", "S32"),
    ("product_gentime", "i4"),
    ("scan_start_time", "i4"),
    ("data_start_time", "i4"),
    ("data_end_time", "i4"),
    ("proj_type", "i4"),
    ("dtype_1", "i4"),
    ("dtype_2", "i4"),
    ("res", "64c"),
]

product_header_dtype = np.dtype(product_header)

pa_site_config = [
    ("site_code", "S8"),
    ("site_name", "S32"),
    ("Latitude", "f4"),
    ("Longitude", "f4"),
    ("antenna_height", "i4"),
    ("ground_height", "i4"),
    ("frequency", "f4"),
    ("antenna_type", "i4"),
    ("tr_number", "i4"),
    ("RDA_version", "i4"),
    ("radar_type", "i2"),
    ("res2", "54c"),
]

pa_site_config_dtype = np.dtype(pa_site_config)

pa_task_config = [
    ("task_name", "S32"),
    ("task_dsc", "S128"),
    ("polar_type", "i4"),
    ("scan_type", "i4"),
    ("san_beam_number", "i4"),
    ("cut_number", "i4"),
    ("ray_order", "i4"),
    ("scan_start_time", "i8"),
    ("res3", "68c"),
]

pa_task_config_dtype = np.dtype(pa_task_config)

pa_beam = [
    ('beam_index', 'i4'),  
    ('beam_type', 'i4'),  
    ('sub_pulse_number', 'i4'),  
    ('tx_beam_direction', 'f4'),  
    ('tx_beam_width_h', 'f4'),  
    ('tx_beam_width_v', 'f4'),  
    ('tx_beam_gain', 'f4'),  
    ('reserved_00', '100c'),  
    ('sub_pulse_strategy', 'i4'),  
    ('sub_pulse_modulation', 'i4'),  
    ('sub_pulse_frequency', 'f4'),  
    ('sub_pulse_band_width', 'f4'),
    ('sub_pulse_width', 'i4'),  
    ('reserved_01', '492c'),
]

pa_beam_dtype = np.dtype(pa_beam)

pa_cut_config = [
    ('cut_index', 'i2'),  
    ('tx_beam_index', 'i2'),  
    ('elev', 'f4'),  
    ('tx_beam_gain', 'f4'),  
    ('rx_beam_width_h', 'f4'),  
    ('rx_beam_width_v', 'f4'),  
    ('rx_beam_gain', 'f4'),  
    ('process_mode', 'i4'),  
    ('wave_form', 'i4'),  
    ('n1_prf_1', 'f4'),  
    ('n1_prf_2', 'f4'),  
    ('n2_prf_1', 'f4'),  
    ('n2_prf_2', 'f4'),  
    ('unfold_mode', 'i4'),  
    ('azimuth', 'f4'),  
    ('start_angle', 'f4'),  
    ('end_angle', 'f4'),  
    ('angle_resolution', 'f4'),  
    ('scan_speed', 'f4'),  
    ('log_reso', 'f4'),  
    ('dop_reso', 'f4'),  
    ('max_range1', 'i4'),  
    ('max_range2', 'i4'),  
    ('start_range', 'i4'),  
    ('sample_1', 'i4'),  
    ('sample_2', 'i4'),  
    ('phase_mode', 'i4'),  
    ('atmospheric_loss', 'f4'),  
    ('nyquist_spd', 'f4'),  
    ('moments_mask', 'i8'),  
    ('moments_size_mask', 'i8'),  
    ('misc_filter_mask', 'i4'),  
    ('sqi_threshold', 'f4'),  
    ('sig_threshold', 'f4'),  
    ('csr_threshold', 'f4'),  
    ('log_threshold', 'f4'),  
    ('cpa_threshold', 'f4'),  
    ('pmi_threshold', 'f4'),  
    ('dplog_threshold', 'f4'),  
    ('thresholds_reserved', '4c'),  
    ('dbt_mask', 'i4'),  
    ('dbz_mask', 'i4'),  
    ('velocity', 'i4'),  
    ('spectrum_width_mask', 'i4'),  
    ('zdr_mask', 'i4'),  
    ('mask_reserved', '12c'),  
    ('scan_sync', '4c'),  
    ('direction', 'i4'),  
    ('ground_clutter_classifier_type', 'i2'),  
    ('ground_clutter_filter_type', 'i2'),  
    ('ground_clutter_filter_notch_width', 'i2'),  
    ('ground_clutter_filter_window', 'i2'),  
    ('reserved', '44c')
]

pa_cut_config_dtype = np.dtype(pa_cut_config)

pa_radial_header = [
    ("radial_state", "i4"),
    ("spot_blank", "i4"),
    ("seq_number", "i4"),
    ("radial_number", "i4"),
    ("elevation_number", "i4"),
    ("azimuth", "f4"),
    ("elevation", "f4"),
    ("seconds", "i8"),
    ("microseconds", "i4"),
    ("data_length", "i4"),
    ("moment_number", "i4"),
    ("scan_beam_index", "i2"),
    ("hori_est_noise", "i2"),
    ("vert_est_noise", "i2"),
    ("zip_type", "i4"), # acctualy it's ref flag,ziptype is reserved
    ("res6", "70c"),
]

pa_radial_header_dtype = np.dtype(pa_radial_header)

l3_radial_header = [
    ("dtype", "i4"),
    ("scale", "i4"),
    ("offset", "i4"),
    ("bin_length", "i2"),
    ("flags", "i2"),
    ("reso", "i4"),
    ("start_range", "i4"),
    ("max_range", "i4"),
    ("nradial", "i4"),
    ("max_val", "i4"),
    ("range_of_max", "i4"),
    ("az_of_max", "f4"),
    ("min_val", "i4"),
    ("range_of_min", "i4"),
    ("az_of_min", "f4"),
    ("res", "8c"),
]

l3_radial_header_dtype = np.dtype(l3_radial_header)

l3_radial_block = [
    ("start_az", "f4"),
    ("angular_reso", "f4"),
    ("nbins", "i4"),
    ("res", "20c"),
]

l3_radial_block_dtype = np.dtype(l3_radial_block)

l3_raster_header = [
    ("dtype", "i4"),
    ("scale", "i4"),
    ("offset", "i4"),
    ("bin_length", "i2"),
    ("flags", "i2"),
    ("row_reso", "i4"),
    ("col_reso", "i4"),
    ("row_side_length", "i4"),
    ("col_side_length", "i4"),
    ("max_val", "i4"),
    ("range_of_max", "i4"),
    ("az_of_max", "f4"),
    ("min_val", "i4"),
    ("range_of_min", "i4"),
    ("az_of_min", "f4"),
    ("res", "8c"),
]

l3_raster_header_dtype = np.dtype(l3_raster_header)

l3_hail_table = [
    ("hail_id", "i4"),
    ("hail_azimuth", "f4"),
    ("hail_range", "i4"),
    ("hail_possibility", "i4"),
    ("hail_severe_possibility", "i4"),
    ("hail_size", "f4"),
    ("rcm", "i4"),
]

l3_hail_table_dtype = np.dtype(l3_hail_table)

l3_meso_table = [
    ("feature_id", "i4"),
    ("storm_id", "i4"),
    ("meso_azimuth", "f4"),
    ("meso_range", "i4"),
    ("meso_elevation", "f4"),
    ("meso_avgshr", "f4"),
    ("meso_height", "i4"),
    ("meso_azdia", "i4"),
    ("meso_radius", "i4"),
    ("meso_avgrv", "f4"),
    ("meso_mxrv", "f4"),
    ("meso_top", "i4"),
    ("meso_base", "i4"),
    ("meso_baseazim", "f4"),
    ("meso_baserange", "i4"),
    ("meso_baseelevation", "f4"),
    ("meso_mxtanshr", "f4"),
]

l3_meso_table_dtype = np.dtype(l3_meso_table)

l3_feature_table = [
    ("feature_id", "i4"),
    ("storm_id", "i4"),
    ("feature_type", "i4"),
    ("feature_azimuth", "f4"),
    ("feature_range", "i4"),
    ("feature_elevation", "f4"),
    ("feature_avgshr", "f4"),
    ("feature_height", "i4"),
    ("feature_azdia", "i4"),
    ("feature_radius", "i4"),
    ("feature_avgrv", "f4"),
    ("feature_mxrv", "f4"),
    ("feature_top", "i4"),
    ("feature_base", "i4"),
    ("feature_baseazim", "f4"),
    ("feature_baserange", "i4"),
    ("feature_baseelevation", "f4"),
    ("feature_mxtanshr", "f4"),
]

l3_feature_table_dtype = np.dtype(l3_feature_table)

l3_tvs_table = [
    ("tvs_id", "i4"),
    ("tvs_stormtype", "i4"),
    ("tvs_azimuth", "f4"),
    ("tvs_range", "i4"),
    ("tvs_elevation", "f4"),
    ("tvs_lldv", "f4"),
    ("tvs_avgdv", "f4"),
    ("tvs_mxdv", "f4"),
    ("tvs_mxdvhgt", "i4"),
    ("tvs_depth", "i4"),
    ("tvs_base", "i4"),
    ("tvs_top", "i4"),
    ("tvs_mxshr", "f4"),
    ("tvs_mxshrhgt", "i4"),
]

l3_tvs_table_dtype = np.dtype(l3_tvs_table)

l3_sti_header = [
    ("num_of_storms", "i4"),
    ("num_of_continuous_storms", "i4"),
    ("num_of_components", "i4"),
    ("avg_speed", "f4"),
    ("avg_direction", "f4"),
]

l3_sti_header_dtype = np.dtype(l3_sti_header)

l3_sti_motion = [
    ("azimuth", "f4"),
    ("range", "i4"),
    ("speed", "f4"),
    ("direction", "f4"),
    ("forecast_error", "i4"),
    ("mean_forecast_error", "i4"),
]

l3_sti_motion_dtype = np.dtype(l3_sti_motion)

l3_sti_position = [
    ("azimuth", "f4"),
    ("range", "i4"),
    ("volume_time", "i4"),
]

l3_sti_position_dtype = np.dtype(l3_sti_position)

l3_sti_attribute = [
    ("id", "i4"),
    ("type", "i4"),
    ("num_of_volumes", "i4"),
    ("azimuth", "f4"),
    ("range", "i4"),
    ("height", "i4"),
    ("max_ref", "f4"),
    ("max_ref_height", "i4"),
    ("vil", "f4"),
    ("num_of_components", "i4"),
    ("index_of_first", "i4"),
    ("top_height", "i4"),
    ("index_of_top", "i4"),
    ("bottom_height", "i4"),
    ("index_of_bottom", "i4"),
]

l3_sti_attribute_dtype = np.dtype(l3_sti_attribute)

l3_sti_component = [
    ("height", "i4"),
    ("max_ref", "f4"),
    ("index_of_next", "i4"),
]

l3_sti_component_dtype = np.dtype(l3_sti_component)

l3_sti_adaptation = [
    ("def_dir", "i4"),
    ("def_spd", "f4"),
    ("max_vtime", "i4"),
    ("num_of_past_volume", "i4"),
    ("corr_speed", "f4"),
    ("min_speed", "f4"),
    ("allow_error", "i4"),
    ("frc_intvl", "i4"),
    ("num_frc_intvl", "i4"),
    ("err_intvl", "i4"),
]

l3_sti_adaptation_dtype = np.dtype(l3_sti_adaptation)

l3_vwp_header = [
    ("nyquist_velocity", "f4"),
    ("number_of_vols", "i4"),
    ("wind_speed_max", "f4"),
    ("wind_direction_max", "f4"),
    ("height_max", "f4"),
    ("res", "12c"),
]

l3_vwp_header_dtype = np.dtype(l3_vwp_header)

l3_vwp_table = [
    ("start_time", "i4"),
    ("height", "i4"),
    ("fitvalid", "i4"),
    ("wind_direction", "f4"),
    ("wind_speed", "f4"),
    ("rms_std", "f4"),
    ("res", "8c"),
]

l3_vwp_table_dtype = np.dtype(l3_vwp_table)

l3_swp = [
    ("range", "i4"),
    ("azimuth", "f4"),
    ("swp", "i4"),
]

l3_swp_dtype = np.dtype(l3_swp)

l3_uam = [
    ("range", "i4"),
    ("azimuth", "f4"),
    ("a", "i4"),
    ("b", "i4"),
    ("deg", "i4"),
    ("max1", "f4"),
    ("max2", "f4"),
    ("max3", "f4"),
    ("max4", "f4"),
    ("max5", "f4"),
    ("area", "f4"),
]

l3_uam_dtype = np.dtype(l3_uam)

l3_wer_header = [
    ("elevation", "f4"),
    ("scan_time", "i4"),
    ("center_height", "i4"),
    ("res", "20c"),
]

l3_wer_header_dtype = np.dtype(l3_wer_header)

# SDD 结构化 dtype 别名
SDD_header = generic_header_dtype
SDD_site = site_config_dtype
SDD_task = task_config_dtype
SDD_cut = cut_config_dtype
SDD_rad_header = radial_header_dtype
SDD_mom_header = moment_header_dtype


"""CINRAD 标准格式（SAD/FMT 等）体积基数据轻量读取。

解析站点与任务头、各仰角径向产品，提供 PPI 数组、距离轴、门经纬高等查询接口。
附属实现：供 ``cli/radar_grid_cli`` 读标准格式基数据；仅依赖标准库与 numpy。
"""

import numpy as np
import datetime
import warnings
from collections import defaultdict



EARTH_RADIUS_KM = 6371.0
K_EARTH = 4.0 / 3.0
RADAR_HEIGHT_SOURCE = "ground_height"


def epoch_seconds_to_utc(epoch_seconds: float):
    """将 Unix 纪元秒转为带 UTC 时区的 ``datetime``。

    标准格式任务块字段 ``scan_start_time`` 存的是自 1970-01-01 00:00:00 UTC
    起的秒数；解析后写入 ``StandardDataLite.scantime``，用于体扫起始时刻。

    参数:
        epoch_seconds: Unix 时间戳（秒，可为 float；解析时常用 ``int(...)``）。

    返回:
        ``datetime.datetime``，``tzinfo=datetime.timezone.utc``。
    """
    return datetime.datetime.fromtimestamp(
        epoch_seconds, tz=datetime.timezone.utc
    )


def beam_height_km(range_km, elev_deg, radar_height_km=0.0):
    """4/3 等效地球半径模型下的波束高度（相对平均海平面，千米）。

    参数:
        range_km: 斜距，形状 ``(..., ngate)``，单位 km。
        elev_deg: 仰角（度），形状可广播到 ``(..., 1)`` 或标量。
        radar_height_km: 雷达海拔高度，单位 km，默认 ``0.0``。

    返回:
        与广播后输入同形的 ``ndarray``，门高度，单位 km。
    """
    elev_rad = np.deg2rad(elev_deg)
    re = K_EARTH * EARTH_RADIUS_KM
    return radar_height_km + range_km * np.sin(elev_rad) + (range_km ** 2) / (2.0 * re)


def gate_longitude_latitude_km(range_km, azimuth_deg, elev_deg, centerlon, centerlat):
    """由斜距 / 方位 / 仰角估算各库的经纬度（平面近似）。

    参数:
        range_km: 距离轴，形状 ``(ngate,)``，单位 km。
        azimuth_deg: 方位角，形状 ``(naz,)``，单位度。
        elev_deg: 仰角，形状 ``(naz,)``，单位度。
        centerlon: 站点经度（度）。
        centerlat: 站点纬度（度）。

    返回:
        ``(lon, lat)``，均为形状 ``(naz, ngate)`` 的 ``ndarray``，单位度。
    """
    az_rad = np.deg2rad(azimuth_deg)
    elev_rad = np.deg2rad(elev_deg)

    north_km = (
        np.cos(az_rad)[:, np.newaxis]
        * range_km[np.newaxis, :]
        * np.cos(elev_rad)[:, np.newaxis]
    )
    east_km = (
        np.sin(az_rad)[:, np.newaxis]
        * range_km[np.newaxis, :]
        * np.cos(elev_rad)[:, np.newaxis]
    )

    lat = centerlat + north_km / 111.0
    lon = centerlon + east_km / (111.0 * np.cos(np.deg2rad(lat)))
    return lon, lat


class StandardDataLite:
    """标准格式体积雷达轻量对象：解析一次，按仰角/产品取数组与几何量。"""

    dtype_corr = {
        1: "TREF",
        2: "REF",
        3: "VEL",
        4: "SW",
        7: "ZDR",
        9: "RHO",
        10: "PHI",
        11: "KDP",
    }

    velocity_products = {"VEL", "SW", "VELSZ"}

    def __init__(self, file):
        """打开并解析标准格式体积。

        参数:
            file: 文件路径、文件对象或 ``BytesIO`` 等，由 ``prepare_file`` 统一处理。
        """
        with prepare_file(file) as self.f:
            self._parse()

    @staticmethod
    def _safe_first(struct_arr, *names, default=0.0):
        """从结构化数组中取第一个可用标量字段。

        参数:
            struct_arr: numpy 结构化数组。
            *names: 候选字段名，按顺序尝试。
            default: 均不可用时的默认值。

        返回:
            ``float``。
        """
        if struct_arr.size == 0:
            return float(default)
        dtype_names = struct_arr.dtype.names or ()
        for name in names:
            if name in dtype_names:
                try:
                    return float(struct_arr[name][0])
                except Exception:
                    pass
        return float(default)

    @staticmethod
    def _safe_text_first(struct_arr, *names, default=""):
        """从结构化数组中取第一个可用文本字段。

        参数:
            struct_arr: numpy 结构化数组。
            *names: 候选字段名。
            default: 默认空字符串。

        返回:
            ``str``（已去 ``\\x00`` 与首尾空白）。
        """
        if struct_arr.size == 0:
            return default
        dtype_names = struct_arr.dtype.names or ()
        for name in names:
            if name not in dtype_names:
                continue
            value = struct_arr[name][0]
            if isinstance(value, bytes):
                return value.decode("ascii", errors="ignore").replace("\x00", "").strip()
            try:
                return bytes(value).decode("ascii", errors="ignore").replace("\x00", "").strip()
            except Exception:
                return str(value).replace("\x00", "").strip()
        return default

    @staticmethod
    def _select_radar_height(antenna_height, ground_height):
        """按 ``RADAR_HEIGHT_SOURCE`` 选择用于波束高度的雷达海拔。

        参数:
            antenna_height: 天线高度（米），可能为 NaN。
            ground_height: 地面高度（米），可能为 NaN。

        返回:
            ``float``，单位米；均无效时返回 ``0.0``。
        """
        if RADAR_HEIGHT_SOURCE == "antenna_height" and np.isfinite(antenna_height):
            return float(antenna_height)
        if np.isfinite(ground_height):
            return float(ground_height)
        return 0.0

    def _parse(self):
        """解析文件头、站点/任务/仰角配置与全部径向产品块。

        副作用:
            设置站点属性、``scantime``（经 ``epoch_seconds_to_utc``）、
            ``data`` / ``aux`` / ``el`` 等。
        """
        header = np.frombuffer(self.f.read(32), SDD_header)
        if header.size == 0 or header["magic_number"][0] != 0x4D545352:
            raise RadarDecodeError("Invalid standard data")

        site_config = np.frombuffer(self.f.read(128), SDD_site)
        if site_config.size == 0:
            raise RadarDecodeError("Invalid site config")

        self.stationlat = float(site_config["Latitude"][0])
        self.stationlon = float(site_config["Longitude"][0])
        self.latitude = self.stationlat
        self.longitude = self.stationlon

        self.site_code = self._safe_text_first(site_config, "site_code")
        self.site_name = self._safe_text_first(site_config, "site_name")
        self.code = self.site_code
        self.name = self.site_name
        self.antenna_height = self._safe_first(site_config, "antenna_height", default=np.nan)
        self.ground_height = self._safe_first(site_config, "ground_height", default=np.nan)
        self.frequency = self._safe_first(site_config, "frequency", default=np.nan)
        self.beam_width_hori = self._safe_first(site_config, "beam_width_hori", default=np.nan)
        self.beam_width_vert = self._safe_first(site_config, "beam_width_vert", default=np.nan)
        self.radar_type = int(self._safe_first(site_config, "radar_type", default=-1))

        self.radarheight = self._select_radar_height(
            antenna_height=self.antenna_height,
            ground_height=self.ground_height,
        )
        self.altitude = self.radarheight
        self.radarheight_source = RADAR_HEIGHT_SOURCE
        self.wavelength = 3e8 / self.frequency / 10000.0 if self.frequency > 0 else np.nan

        task = np.frombuffer(self.f.read(256), SDD_task)
        if task.size == 0:
            raise RadarDecodeError("Invalid task config")

        self.scantime = epoch_seconds_to_utc(int(task["scan_start_time"][0]))
        self.cut_num = int(task["cut_number"][0])

        self.scan_config = np.frombuffer(
            self.f.read(256 * self.cut_num), SDD_cut
        )
        if self.scan_config.size == 0:
            raise RadarDecodeError("Invalid scan config")

        data = {}
        aux = {}

        while True:
            header_bytes = self.f.read(64)
            if not header_bytes:
                break
            if len(header_bytes) < 64:
                warnings.warn("Incomplete radial header encountered", RuntimeWarning)
                break

            radial_header = np.frombuffer(header_bytes, SDD_rad_header)
            if radial_header.size == 0:
                break

            elev_number = int(radial_header["elevation_number"][0])
            el_num = elev_number - 1  # 文件为 1 起；内部 tilt 为 0 起
            moment_number = int(radial_header["moment_number"][0])

            # 损坏头防御：elevation_number<=0 → el_num=-1；越界也不入库
            skip_radial = el_num < 0 or el_num >= self.cut_num
            if skip_radial:
                warnings.warn(
                    f"Skip radial with invalid elevation_number={elev_number} "
                    f"(tilt={el_num}, cut_num={self.cut_num})",
                    RuntimeWarning,
                )

            if not skip_radial:
                if el_num not in data:
                    data[el_num] = defaultdict(list)
                    aux[el_num] = defaultdict(list)

                aux[el_num]["azimuth"].append(float(radial_header["azimuth"][0]))
                aux[el_num]["elevation"].append(float(radial_header["elevation"][0]))

            for _ in range(moment_number):
                moment_header_bytes = self.f.read(32)
                if not moment_header_bytes or len(moment_header_bytes) < 32:
                    warnings.warn("Incomplete moment header encountered", RuntimeWarning)
                    self.data = data
                    self.aux = aux
                    self.el = [float(cfg["elev"]) for cfg in self.scan_config]
                    return

                moment_header = np.frombuffer(moment_header_bytes, SDD_mom_header)
                if moment_header.size == 0:
                    continue

                block_length = int(moment_header["block_length"][0])
                bin_length = int(moment_header["bin_length"][0])

                if block_length == 0:
                    continue

                # 无论是否入库，都要读完 body，避免文件指针错位
                if bin_length not in (1, 2, 4, 8):
                    self.f.read(block_length)
                    continue

                dtype_code = int(moment_header["data_type"][0])
                dtype = self.dtype_corr.get(dtype_code, None)

                body_bytes = self.f.read(block_length)
                if len(body_bytes) < block_length:
                    warnings.warn("Incomplete moment body encountered", RuntimeWarning)
                    self.data = data
                    self.aux = aux
                    self.el = [float(cfg["elev"]) for cfg in self.scan_config]
                    return

                if skip_radial or not dtype:
                    continue

                data_body = np.frombuffer(body_bytes, f"u{bin_length}")

                if dtype not in aux[el_num]:
                    scale = float(moment_header["scale"][0])
                    offset = float(moment_header["offset"][0])
                    aux[el_num][dtype] = (scale, offset)

                data[el_num][dtype].append(data_body)

        self.data = data
        self.aux = aux
        self.el = [float(cfg["elev"]) for cfg in self.scan_config]

    def available_tilt(self, dtype=None):
        """列出可用仰角序号。

        参数:
            dtype: 产品名如 ``"REF"``；``None`` 表示任意产品均计入。

        返回:
            升序 ``list[int]``。
        """
        if dtype is None:
            return sorted(self.data.keys())
        return sorted([tilt for tilt in self.data if dtype in self.data[tilt]])

    def get_azimuth(self, tilt):
        """取某仰角各径向方位角。

        参数:
            tilt: 仰角序号（从 0 起）。

        返回:
            ``ndarray[float]``，形状 ``(naz,)``，单位度。
        """
        if tilt not in self.aux:
            raise RadarDecodeError(f"Tilt {tilt} does not exist")
        return np.asarray(self.aux[tilt].get("azimuth", []), dtype=float)

    def get_elevation_array(self, tilt):
        """取某仰角各径向的仰角序列。

        参数:
            tilt: 仰角序号。

        返回:
            ``ndarray[float]``，形状 ``(naz,)``，单位度。
            若径向仰角缺失，则用该层固定仰角 ``get_elevation`` 填满。
        """
        if tilt not in self.aux:
            raise RadarDecodeError(f"Tilt {tilt} does not exist")
        arr = np.asarray(self.aux[tilt].get("elevation", []), dtype=float)
        if arr.size == 0:
            # Fall back to the fixed elevation angle when ray elevations are absent.
            nrays = len(self.get_azimuth(tilt))
            arr = np.full(nrays, float(self.get_elevation(tilt)), dtype=float)
        return arr

    def _get_reso(self, tilt, dtype):
        """读取扫描配置中的距离分辨率（千米）。

        速度类产品用 ``dop_reso``，其余用 ``log_reso``（文件内单位 0.001 km）。
        """
        try:
            cfg = self.scan_config[tilt]
        except Exception as exc:
            raise RadarDecodeError(f"Scan config for tilt {tilt} does not exist") from exc

        names = cfg.dtype.names or ()

        if dtype in self.velocity_products:
            if "dop_reso" not in names:
                raise RadarDecodeError(f"dop_reso not found for tilt {tilt}, dtype={dtype}")
            reso = float(cfg["dop_reso"]) / 1000.0
        else:
            if "log_reso" not in names:
                raise RadarDecodeError(f"log_reso not found for tilt {tilt}, dtype={dtype}")
            reso = float(cfg["log_reso"]) / 1000.0

        if reso <= 0:
            raise RadarDecodeError(f"Invalid resolution for tilt={tilt}, dtype={dtype}")

        return reso

    def get_reso(self, tilt, dtype):
        """公开接口：返回距离分辨率（千米）。

        参数:
            tilt: 仰角序号。
            dtype: 产品名。

        返回:
            ``float``，单位 km。
        """
        return self._get_reso(tilt, dtype)

    def get_range_axis(self, tilt, dtype="REF", drange=None):
        """构造门中心斜距轴。

        参数:
            tilt: 仰角序号。
            dtype: 产品名（决定分辨率字段）。
            drange: 最大距离（km）；``None`` 表示用数据全部库。

        返回:
            ``ndarray[float]``，形状 ``(ngate,)``，单位 km。
            与 cinrad 一致：第一门中心在 ``1 * reso``。
        """
        reso = self.get_reso(tilt, dtype)
        raw = np.asarray(self.data[tilt][dtype])

        if raw.ndim == 1:
            raw = raw[np.newaxis, :]

        total_gates = raw.shape[1]
        ngates = total_gates if drange is None else int(float(drange) // reso)
        # Match cinrad semantics: the first gate center is at 1 * reso.
        return (np.arange(ngates, dtype=float) + 1.0) * reso

    def get_gate_z(self, tilt, dtype="REF", drange=None, as_meters=False):
        """各库海拔高度（平均海平面以上）。

        参数:
            tilt: 仰角序号。
            dtype: 产品名。
            drange: 最大距离（km），``None`` 不截断。
            as_meters: ``False`` 返回 km；``True`` 返回米。

        返回:
            ``ndarray``，形状 ``(nrays, ngates)``。
        """
        range_km = self.get_range_axis(tilt, dtype=dtype, drange=drange)
        elev_deg = self.get_elevation_array(tilt)
        nrays = elev_deg.size

        if nrays == 0:
            out = np.empty((0, range_km.size), dtype=float)
            return out * 1000.0 if as_meters else out

        radar_height_km = float(self.radarheight) / 1000.0

        z_km = beam_height_km(
            range_km[np.newaxis, :],
            elev_deg[:, np.newaxis],
            radar_height_km=radar_height_km,
        )

        return z_km * 1000.0 if as_meters else z_km

    def get_gate_lon_lat(self, tilt, dtype="REF", drange=None):
        """各库经纬度。

        参数:
            tilt / dtype / drange: 同 ``get_range_axis``。

        返回:
            ``(lon, lat)``，形状均为 ``(naz, ngate)``，单位度。
        """
        range_km = self.get_range_axis(tilt, dtype=dtype, drange=drange)
        azimuth_deg = self.get_azimuth(tilt)
        elev_deg = self.get_elevation_array(tilt)
        return gate_longitude_latitude_km(
            range_km=range_km,
            azimuth_deg=azimuth_deg,
            elev_deg=elev_deg,
            centerlon=self.stationlon,
            centerlat=self.stationlat,
        )

    def get_site_info(self):
        """站点元信息字典（供 payload / 前端使用）。

        返回:
            含站点号、经纬、海拔、频率、波束宽度、雷达类型等字段的 ``dict``。
        """
        return {
            "site_code": self.site_code,
            "site_name": self.site_name,
            "longitude": self.stationlon,
            "latitude": self.stationlat,
            "altitude": self.altitude,
            "radarheight": self.radarheight,
            "radarheight_source": self.radarheight_source,
            "antenna_height": self.antenna_height,
            "ground_height": self.ground_height,
            "frequency": self.frequency,
            "wavelength": self.wavelength,
            "beam_width_hori": self.beam_width_hori,
            "beam_width_vert": self.beam_width_vert,
            "radar_type": self.radar_type,
        }

    def get_sweep(self, tilt, dtype="REF", drange=None, fill_value=np.nan):
        """组装单层 PPI 扫掠包（含数据、轴与门经纬）。

        参数:
            tilt: 仰角序号。
            dtype: 产品名，默认 ``"REF"``。
            drange: 最大距离（km），``None`` 不截断。
            fill_value: 无效值填充。

        返回:
            ``dict``，含 ``data`` / ``azimuth`` / ``range`` / ``gate_*`` / ``site_info`` 等。
        """
        gate_longitude, gate_latitude = self.get_gate_lon_lat(
            tilt, dtype=dtype, drange=drange
        )
        return {
            "data": self.get_array(
                tilt=tilt,
                drange=drange,
                dtype=dtype,
                fill_value=fill_value,
            ),
            "azimuth": self.get_azimuth(tilt),
            "elevation": self.get_elevation(tilt),
            "elevation_array": self.get_elevation_array(tilt),
            "range": self.get_range_axis(tilt, dtype=dtype, drange=drange),
            "reso": self.get_reso(tilt, dtype),
            "gate_z": self.get_gate_z(tilt, dtype=dtype, drange=drange, as_meters=False),
            "gate_altitude": self.get_gate_z(tilt, dtype=dtype, drange=drange, as_meters=True),
            "gate_longitude": gate_longitude,
            "gate_latitude": gate_latitude,
            "site_info": self.get_site_info(),
            "site_longitude": self.stationlon,
            "site_latitude": self.stationlat,
            "radarheight_m": self.radarheight,
            "altitude_m": self.altitude,
            "antenna_height_m": self.antenna_height,
            "ground_height_m": self.ground_height,
        }

    def get_raw(self, tilt, drange, dtype):
        """解码原始存储值为物理量（masked array）。

        参数:
            tilt: 仰角序号。
            drange: 最大距离（km）；``None`` 用全部库。
            dtype: 产品名。

        返回:
            普通产品：masked ``ndarray``，形状 ``(naz, ngate)``。
            速度类产品：``(data, rf)`` 二元组，``rf`` 为距离折叠标记掩膜。
        """
        if tilt not in self.data:
            raise RadarDecodeError(f"Tilt {tilt} does not exist")

        if dtype not in self.data[tilt]:
            raise RadarDecodeError(f"Product {dtype} does not exist in tilt {tilt}")

        if drange is not None and drange < 0:
            raise RadarDecodeError("drange must be None or a non-negative number")

        reso = self._get_reso(tilt, dtype)
        raw = np.asarray(self.data[tilt][dtype])

        if raw.size == 0:
            nrays = len(self.aux[tilt].get("azimuth", []))
            ngates = 0 if drange is None else int(float(drange) // reso)
            warnings.warn("Empty data", RuntimeWarning)
            empty = np.ma.masked_all((nrays, ngates), dtype=float)
            if dtype in self.velocity_products:
                return empty, np.ma.masked_all((nrays, ngates), dtype=float)
            return empty

        if raw.ndim == 1:
            raw = raw[np.newaxis, :]

        total_gates = raw.shape[1]
        ngates = total_gates if drange is None else int(float(drange) // reso)

        cut = raw[:, :ngates]
        shape_diff = ngates - cut.shape[1]
        cut_ma = np.ma.array(cut, copy=False)

        if shape_diff > 0:
            append = np.ma.masked_all((cut.shape[0], shape_diff))
            cut_ma = np.ma.hstack([cut_ma, append])

        cut_ma = np.ma.masked_less(cut_ma, 5)

        if dtype not in self.aux[tilt]:
            raise RadarDecodeError(
                f"Scale/offset metadata for product {dtype} not found in tilt {tilt}"
            )

        scale, offset = self.aux[tilt][dtype]
        if scale == 0:
            raise RadarDecodeError(
                f"Invalid scale=0 for product {dtype} in tilt {tilt}"
            )

        data = (cut_ma - offset) / scale

        if dtype in self.velocity_products:
            rf_src = raw[:, :ngates]
            rf = np.ma.masked_not_equal(rf_src, 1)

            if shape_diff > 0:
                rf_append = np.ma.masked_all((rf.shape[0], shape_diff))
                rf = np.ma.hstack([rf, rf_append])

            return data, rf

        return data

    def get_array(
        self,
        tilt=0,
        drange=None,
        dtype="REF",
        fill_value=None,
        out_dtype=None,
    ):
        """取二维产品场（可填充无效值、指定输出 dtype）。

        参数:
            tilt: 仰角序号，默认 ``0``。
            drange: 最大距离（km），``None`` 不截断。
            dtype: 产品名，默认 ``"REF"``。
            fill_value: 若给定则 ``masked.filled(fill_value)``；``None`` 保留掩膜数组。
            out_dtype: 如 ``np.float32``；``None`` 保持默认。

        返回:
            ``ndarray`` 或 masked array，形状 ``(naz, ngate)``。速度类只返回数据分量。
        """
        raw = self.get_raw(tilt=tilt, drange=drange, dtype=dtype)

        if isinstance(raw, tuple):
            data = raw[0]
        else:
            data = raw

        if fill_value is not None:
            filled = data.filled(fill_value)
            if out_dtype is not None:
                return np.ascontiguousarray(filled, dtype=out_dtype)
            return filled

        if out_dtype is not None:
            return np.ascontiguousarray(np.asarray(data, dtype=out_dtype))
        return data

    def get_elevation(self, tilt):
        """该层固定仰角（来自扫描配置）。

        参数:
            tilt: 仰角序号。

        返回:
            ``float``，单位度。
        """
        if tilt < 0 or tilt >= len(self.el):
            raise RadarDecodeError(f"Tilt {tilt} does not exist")
        return self.el[tilt]

    def get_all_arrays(
        self,
        drange=None,
        fill_value=None,
        dtypes=None,
        include_elevation_array=True,
        out_dtype=None,
    ):
        """导出全部（或筛选）仰角的产品数组，供 service payload 整理。

        参数:
            drange: 最大距离（km），``None`` 不截断。
            fill_value: 传给 ``get_array`` 的填充值。
            dtypes: ``None``=全部产品；如 ``("REF",)`` 只解需要的量。
            include_elevation_array: ``False`` 可省逐径向仰角数组。
            out_dtype: 如 ``np.float32``，避免默认 float64 大数组。

        返回:
            ``dict[tilt_int, info]``，``info`` 含 ``elevation`` / ``site_info`` /
            ``products`` / ``reso``（km），以及可选的 ``elevation_array``。
        """
        result = {}
        want = None if dtypes is None else {str(d).upper() for d in dtypes}
        site_info = self.get_site_info()

        for tilt in sorted(self.data.keys()):
            prod_names = sorted(self.data[tilt].keys())
            if want is not None:
                prod_names = [d for d in prod_names if d in want]
                if not prod_names:
                    continue

            tilt_data = {
                "elevation": self.get_elevation(tilt),
                "site_info": site_info,
                "products": {},
                "reso": {},
            }
            if include_elevation_array:
                tilt_data["elevation_array"] = self.get_elevation_array(tilt)

            for dtype in prod_names:
                tilt_data["products"][dtype] = self.get_array(
                    tilt=tilt,
                    drange=drange,
                    dtype=dtype,
                    fill_value=fill_value,
                    out_dtype=out_dtype,
                )
                tilt_data["reso"][dtype] = self._get_reso(tilt, dtype)

            result[tilt] = tilt_data

        return result


def load_standard_radar(file):
    """读取 CINRAD 标准格式体积基数据（路径自动识别 gzip/bz2）。"""
    return StandardDataLite(file)


__all__ = [
    "RadarDecodeError",
    "StandardDataLite",
    "load_standard_radar",
    "prepare_file",
]
