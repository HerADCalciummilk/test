#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""从 Py-ART ``retrieve.echo_class`` 迁移来的回波分类算法。
包括：
- Steiner 层状-对流分类
- 特征识别
- 水凝物分类
- 小波层状-对流分类
对上述算法进行了插件类的封装。
插件类的主要功能是：
- 接收meteva_base的网格数据作为输入
- 调用对应的算法函数进行处理
- 返回处理结果
"""

from __future__ import annotations

from warnings import warn

import meteva_base as meb
import numpy as np
import xarray as xr

from radar_echo_classification.src.utils._echo_class import _feature_detection, steiner_class_buff
from radar_echo_classification.src.utils._echo_class_wt import calc_scale_break, wavelet_reclass
from radar_echo_classification.src.utils._grid_utils import (
    _build_full_result,
    _build_level_result,
    _check_single_context,
    _flatten_to_scan,
    _get_dx_dy,
    get_xy_in_meters,
)
from radar_echo_classification.src.utils._hydro_utils import (
    _assign_to_class,
    _assign_to_class_scan,
    _compute_coeff_transform,
    _get_mass_centers,
    _mass_centers_table,
    _standardize,
)
from radar_echo_classification.utils.base_plugin import BasePlugin


class SteinerConvStratPlugin(BasePlugin):
    """Steiner 层状-对流分类插件。

    封装 ``steiner_conv_strat``，使用 Steiner 方法将回波划分为层状和对流。

    流程
    ----
    1. 校验反射率六维网格上下文，并从经纬度估算水平坐标与分辨率。
    2. 提取 ``member/time/dtime`` 唯一切片上的三维反射率体
       ``(level, lat, lon)``，调用 ``steiner_class_buff`` 做 Steiner 分类。
    3. 选取与 ``work_level`` 最接近的垂直层，将二维分类结果封装为
       ``meteva_base`` 单层网格。

    输出类别：0=未定义，1=层状，2=对流。
    """

    def __init__(
        self,
        dx=None,
        dy=None,
        intense: float = 42.0,
        work_level: float = 3000.0,
        peak_relation: str = "default",
        area_relation: str = "medium",
        bkg_rad: float = 11000.0,
        use_intense: bool = True,
    ) -> None:
        """初始化 Steiner 层状-对流分类插件。

        参数
        ----
        dx, dy : float, optional
            水平分辨率，单位米。未给定时根据经纬度坐标近似估算。
        intense : float, optional
            强对流回波阈值，单位 dBZ。
        work_level : float, optional
            分类使用的工作高度，单位米。
        peak_relation : str, optional
            峰值关系类型。
        area_relation : str, optional
            对流核心影响半径关系类型。
        bkg_rad : float, optional
            计算背景回波时使用的半径，单位米。
        use_intense : bool, optional
            是否直接使用强回波阈值识别对流核心。
        """
        self.kwargs = {
            "dx": dx,
            "dy": dy,
            "intense": intense,
            "work_level": work_level,
            "peak_relation": peak_relation,
            "area_relation": area_relation,
            "bkg_rad": bkg_rad,
            "use_intense": use_intense,
        }

    def process(self, refl: xr.DataArray) -> xr.DataArray:
        """运行 Steiner 层状-对流分类。

        参数
        ----
        refl : xr.DataArray
            meteva_base 反射率网格数据，需包含 level 维。

        返回
        ----
        xr.DataArray
            单层回波分类网格；类别 0=未定义，1=层状，2=对流。
        """
        return steiner_conv_strat(refl, **self.kwargs)


class FeatureDetectionPlugin(BasePlugin):
    """自适应阈值回波特征识别插件。

    封装 ``feature_detection``，使用自适应阈值方法进行回波特征识别。

    流程
    ----
    1. 校验输入网格，估算 ``dx/dy``，按 ``level_m`` 选取目标高度层。
    2. 对二维 CAPPI 截面估计背景场，依据阈值关系识别核心、特征、
       背景、弱回波及无地面回波等区域。
    3. 若 ``estimate_flag=True``，对原场加减 ``estimate_offset``（或
       使用显式 ``overest_field`` / ``underest_field``）再各运行一次，
       输出高估与低估敏感性结果。

    输出字典至少含 ``feature_detection``；``estimate_flag=True`` 时还含
    ``feature_under``、``feature_over``。
    """

    def __init__(
        self,
        dx=None,
        dy=None,
        level_m=None,
        always_core_thres: float = 42,
        bkg_rad_km: float = 11,
        use_cosine: bool = True,
        max_diff: float = 5,
        zero_diff_cos_val: float = 55,
        scalar_diff: float = 1.5,
        use_addition: bool = True,
        calc_thres: float = 0.75,
        weak_echo_thres: float = 5.0,
        min_val_used: float = 5.0,
        dB_averaging: bool = True,
        remove_small_objects: bool = True,
        min_km2_size: float = 10,
        binary_close: bool = False,
        val_for_max_rad: float = 30,
        max_rad_km: float = 5.0,
        core_val: int = 3,
        nosfcecho: int = 0,
        weakecho: int = 3,
        bkgd_val: int = 1,
        feat_val: int = 2,
        estimate_flag: bool = True,
        estimate_offset: float = 5,
    ) -> None:
        """初始化自适应阈值回波特征识别插件。

        参数
        ----
        dx, dy : float, optional
            水平分辨率，单位米。未给定时根据经纬度坐标近似估算。
        level_m : float, optional
            参与分类的高度，单位米。未给定时使用第一层。
        always_core_thres : float, optional
            始终判为核心回波的阈值。
        bkg_rad_km : float, optional
            计算背景场时使用的平均半径，单位千米。
        use_cosine : bool, optional
            是否使用余弦型阈值关系。
        max_diff : float, optional
            与背景场比较时允许的最大差值。
        zero_diff_cos_val : float, optional
            余弦阈值关系中差值为 0 时对应的场值。
        scalar_diff : float, optional
            固定差值关系中的增量。
        use_addition : bool, optional
            是否使用加法形式构造特征判据。
        calc_thres : float, optional
            参与分类计算的最小阈值。
        weak_echo_thres : float, optional
            弱回波阈值。
        min_val_used : float, optional
            参与背景与特征识别的最小场值。
        dB_averaging : bool, optional
            是否在 dB 空间进行背景平均。
        remove_small_objects : bool, optional
            是否移除面积过小的对象。
        min_km2_size : float, optional
            保留对象的最小面积，单位平方千米。
        binary_close : bool, optional
            是否在识别后执行二值闭运算。
        val_for_max_rad : float, optional
            对应最大影响半径的场值。
        max_rad_km : float, optional
            特征识别时允许的最大影响半径，单位千米。
        core_val : int, optional
            输出结果中核心回波的类别编号。
        nosfcecho : int, optional
            输出结果中无地面回波或未定义区域的类别编号。
        weakecho : int, optional
            输出结果中弱回波的类别编号。
        bkgd_val : int, optional
            输出结果中背景回波的类别编号。
        feat_val : int, optional
            输出结果中特征回波的类别编号。
        estimate_flag : bool, optional
            是否计算高估和低估结果。
        estimate_offset : float, optional
            构造高估和低估场时对原场增减的偏移量。
        """
        self.kwargs = {
            "dx": dx,
            "dy": dy,
            "level_m": level_m,
            "always_core_thres": always_core_thres,
            "bkg_rad_km": bkg_rad_km,
            "use_cosine": use_cosine,
            "max_diff": max_diff,
            "zero_diff_cos_val": zero_diff_cos_val,
            "scalar_diff": scalar_diff,
            "use_addition": use_addition,
            "calc_thres": calc_thres,
            "weak_echo_thres": weak_echo_thres,
            "min_val_used": min_val_used,
            "dB_averaging": dB_averaging,
            "remove_small_objects": remove_small_objects,
            "min_km2_size": min_km2_size,
            "binary_close": binary_close,
            "val_for_max_rad": val_for_max_rad,
            "max_rad_km": max_rad_km,
            "core_val": core_val,
            "nosfcecho": nosfcecho,
            "weakecho": weakecho,
            "bkgd_val": bkgd_val,
            "feat_val": feat_val,
            "estimate_flag": estimate_flag,
            "estimate_offset": estimate_offset,
        }

    def process(
        self,
        field_data: xr.DataArray,
        overest_field: xr.DataArray | None = None,
        underest_field: xr.DataArray | None = None,
    ) -> dict[str, xr.DataArray]:
        """运行自适应阈值回波特征识别。

        参数
        ----
        field_data : xr.DataArray
            meteva_base 网格数据，可为反射率或其他待识别场。
        overest_field, underest_field : xr.DataArray, optional
            显式提供高估和低估输入场。未给定时使用原场加减
            ``estimate_offset``。

        返回
        ----
        dict[str, xr.DataArray]
            回波特征分类结果字典，键与原始 Py-ART 接口保持一致。
            至少包含 ``feature_detection``；``estimate_flag=True`` 时还包含
            ``feature_under``、``feature_over``。
        """
        return feature_detection(
            field_data,
            overest_field=overest_field,
            underest_field=underest_field,
            **self.kwargs,
        )


class HydroclassSemisupervisedPlugin(BasePlugin):
    """半监督水凝物分类插件。

    封装 ``hydroclass_semisupervised``，使用半监督方法进行水凝物分类。

    流程
    ----
    1. 按 ``var_names`` 校验并读取偏振量（及温度/零度层高度）网格，
       预检仅剔除明显填充值，物理极值由 ``_standardize`` 饱和到 ±1。
    2. 未提供 ``mass_centers`` 时，优先从输入 ``attrs['frequency']`` 选择
       频段质心，否则使用 ``radar_freq``，再否则回退 C 波段默认质心。
    3. 将六维网格展平为扫描面，对各变量标准化后与质心做加权距离比较，
       得到最近类别；可选计算熵与各类别比例场。

    主输出 ``hydro`` 类别编号：0=未分类，1=聚集物，2=冰晶，3=小雨，
    4=冰缘颗粒，5=雨水，6=垂直定向冰，7=湿雪，8=冰雹融化，
    9=干雹或高密度雨滴。``compute_entropy=True`` 时另含 ``entropy``；
    ``output_distances=True`` 时另含 ``proportion_*``。
    """

    def __init__(
        self,
        hydro_names=("AG", "CR", "LR", "RP", "RN", "VI", "WS", "MH", "IH/HDG"),
        var_names=("Zh", "ZDR", "KDP", "RhoHV", "relH"),
        mass_centers=None,
        weights=np.array([1.0, 1.0, 1.0, 0.75, 0.5]),
        value: float = 50.0,
        lapse_rate: float = -6.5,
        radar_freq=None,
        temp_ref: str = "temperature",
        compute_entropy: bool = False,
        output_distances: bool = False,
        vectorize: bool = False,
    ) -> None:
        """初始化半监督水凝物分类插件。

        参数
        ----
        hydro_names : sequence of str, optional
            各水凝物类别的名称列表。
        var_names : sequence of str, optional
            参与分类的变量名称顺序。
        mass_centers : ndarray, optional
            各类别的质心矩阵。未给定时按频段选择默认质心。
        weights : ndarray, optional
            各变量在距离计算中的权重。
        value : float, optional
            将距离转换为比例时使用的衰减控制参数。
        lapse_rate : float, optional
            温度转换为相对零度层高度时使用的温度垂直递减率。
        radar_freq : float, optional
            雷达频率，单位 Hz，用于选择质心。
        temp_ref : str, optional
            温度相关输入的解释方式，可选 ``temperature`` 或
            ``height_over_iso0``。
        compute_entropy : bool, optional
            是否计算分类熵。
        output_distances : bool, optional
            是否输出各类别比例场。
        vectorize : bool, optional
            是否使用向量化距离分类计算。
        """
        self.kwargs = {
            "hydro_names": hydro_names,
            "var_names": var_names,
            "mass_centers": mass_centers,
            "weights": weights,
            "value": value,
            "lapse_rate": lapse_rate,
            "radar_freq": radar_freq,
            "temp_ref": temp_ref,
            "compute_entropy": compute_entropy,
            "output_distances": output_distances,
            "vectorize": vectorize,
        }

    def process(
        self,
        refl: xr.DataArray | None = None,
        zdr: xr.DataArray | None = None,
        rhv: xr.DataArray | None = None,
        kdp: xr.DataArray | None = None,
        temp: xr.DataArray | None = None,
        iso0: xr.DataArray | None = None,
    ) -> dict[str, xr.DataArray]:
        """运行半监督水凝物分类。

        参数
        ----
        refl, zdr, rhv, kdp : xr.DataArray, optional
            meteva_base 偏振量网格数据；需与 ``var_names`` 中声明的变量对应。
        temp, iso0 : xr.DataArray, optional
            温度场或相对零度层高度场；``var_names`` 含 ``relH`` 时按
            ``temp_ref`` 二选一。

        返回
        ----
        dict[str, xr.DataArray]
            水凝物分类及附加结果字典。至少含 ``hydro``；
            ``compute_entropy=True`` 时另含 ``entropy``；
            ``output_distances=True`` 时另含各类别比例场 ``proportion_*``。
        """
        return hydroclass_semisupervised(
            refl=refl,
            zdr=zdr,
            rhv=rhv,
            kdp=kdp,
            temp=temp,
            iso0=iso0,
            **self.kwargs,
        )


class ConvStratRautPlugin(BasePlugin):
    """小波层状-对流分类插件。

    封装 ``conv_strat_raut``，使用小波多分辨率方法进行层状-对流分类。

    流程
    ----
    1. 校验反射率网格，从经纬度自动估算水平分辨率 ``dx/dy``。
    2. 按 ``cappi_level``（高度值或层索引）选取目标 CAPPI 层。
    3. 依据 ``conv_scale_km`` 与网格分辨率计算小波尺度分割点，
       对反射率场做小波分解并按阈值重标记为层状、混合或对流核心。

    输出类别：0=未分类，1=层状，2=混合，3=对流核心。
    水平分辨率由网格坐标自动估算，不对外暴露 dx/dy 参数。
    """

    def __init__(
        self,
        cappi_level: float | int = 0,
        zr_a: float = 200,
        zr_b: float = 1.6,
        core_wt_threshold: float = 5,
        conv_wt_threshold: float = 1.5,
        conv_scale_km: float = 25,
        min_reflectivity: float = 5,
        conv_min_refl: float = 25,
        conv_core_threshold: float = 42,
        override_checks: bool = False,
    ) -> None:
        """初始化小波层状-对流分类插件。

        参数
        ----
        cappi_level : float or int, optional
            分类层，可传高度值或层索引。
        zr_a, zr_b : float, optional
            Z-R 关系式系数。
        core_wt_threshold : float, optional
            对流核心与混合回波之间的小波阈值。
        conv_wt_threshold : float, optional
            对流与层状回波之间的小波阈值。
        conv_scale_km : float, optional
            对流尺度与层状尺度的分割尺度，单位千米。
        min_reflectivity : float, optional
            参与分类的最小反射率阈值。
        conv_min_refl : float, optional
            始终视为非对流的反射率上限。
        conv_core_threshold : float, optional
            判定对流核心的反射率阈值。
        override_checks : bool, optional
            是否跳过参数取值范围检查。
        """
        self.kwargs = {
            "cappi_level": cappi_level,
            "zr_a": zr_a,
            "zr_b": zr_b,
            "core_wt_threshold": core_wt_threshold,
            "conv_wt_threshold": conv_wt_threshold,
            "conv_scale_km": conv_scale_km,
            "min_reflectivity": min_reflectivity,
            "conv_min_refl": conv_min_refl,
            "conv_core_threshold": conv_core_threshold,
            "override_checks": override_checks,
        }

    def process(self, refl: xr.DataArray) -> xr.DataArray:
        """运行小波层状-对流分类。

        参数
        ----
        refl : xr.DataArray
            meteva_base 反射率网格数据。

        返回
        ----
        xr.DataArray
            单层小波分类结果；类别 0=未分类，1=层状，2=混合，3=对流核心。
        """
        return conv_strat_raut(refl, **self.kwargs)


def steiner_conv_strat(
    refl: xr.DataArray,
    dx=None,
    dy=None,
    intense: float = 42.0,
    work_level: float = 3000.0,
    peak_relation: str = "default",
    area_relation: str = "medium",
    bkg_rad: float = 11000.0,
    use_intense: bool = True,
) -> xr.DataArray:
    """
    使用 Steiner 方法将回波划分为层状和对流。

    参数
    ----
    refl : xr.DataArray
        meteva_base 反射率网格数据，需包含 level 维。
    dx, dy : float, optional
        水平分辨率，单位米。未给定时根据经纬度坐标近似估算。
    intense : float, optional
        强对流回波阈值，单位 dBZ。
    work_level : float, optional
        分类使用的工作高度，单位米。
    peak_relation : str, optional
        峰值关系类型。
    area_relation : str, optional
        对流核心影响半径关系类型。
    bkg_rad : float, optional
        计算背景回波时使用的半径，单位米。
    use_intense : bool, optional
        是否直接使用强回波阈值识别对流核心。

    返回
    ----
    xr.DataArray
        单层回波分类网格。
    """
    refl_grid = _check_single_context(refl, valid_val=(-200.0, 200.0, np.nan))
    x_m, y_m = get_xy_in_meters(refl_grid)
    dx, dy = _get_dx_dy(refl_grid, dx=dx, dy=dy)
    x = x_m.astype(np.float32)
    y = y_m.astype(np.float32)
    z = np.asarray(refl_grid.level.values, dtype=np.float32)
    ze = np.asarray(refl_grid.values[0, :, 0, 0, :, :], dtype=np.float32)

    # =====================================
    # Steiner 分类入口
    #
    # 这里先从 meteva_base 六维网格中取出
    # member/time/dtime 唯一的三维切片，
    # 再组织成分类需要的三维反射率数据。
    # =====================================
    eclass = steiner_class_buff(
        ze,
        x,
        y,
        z,
        dx=dx,
        dy=dy,
        bkg_rad=bkg_rad,
        work_level=work_level,
        intense=intense,
        peak_relation=peak_relation,
        area_relation=area_relation,
        use_intense=use_intense,
    )

    # 选择与工作高度最接近的垂直层；未指定时默认首层。
    if work_level is None:
        level_index = 0
    else:
        level_index = int(np.argmin(np.abs(z - work_level)))
    template = refl_grid.isel(member=[0], level=[level_index], time=[0], dtime=[0])

    return _build_level_result(
        template,
        eclass.astype(np.int32),
        name="echo_classification",
        standard_name="echo_classification",
        long_name="Steiner echo classification",
        valid_min=0,
        valid_max=2,
        extra_attrs={
            "comment_1": (
                "Convective-stratiform echo classification based on Steiner et al. (1995)"
            ),
            "comment_2": "0 = Undefined, 1 = Stratiform, 2 = Convective",
        },
    )


def feature_detection(
    field_data: xr.DataArray,
    dx=None,
    dy=None,
    level_m=None,
    always_core_thres: float = 42,
    bkg_rad_km: float = 11,
    use_cosine: bool = True,
    max_diff: float = 5,
    zero_diff_cos_val: float = 55,
    scalar_diff: float = 1.5,
    use_addition: bool = True,
    calc_thres: float = 0.75,
    weak_echo_thres: float = 5.0,
    min_val_used: float = 5.0,
    dB_averaging: bool = True,
    remove_small_objects: bool = True,
    min_km2_size: float = 10,
    binary_close: bool = False,
    val_for_max_rad: float = 30,
    max_rad_km: float = 5.0,
    core_val: int = 3,
    nosfcecho: int = 0,
    weakecho: int = 3,
    bkgd_val: int = 1,
    feat_val: int = 2,
    estimate_flag: bool = True,
    estimate_offset: float = 5,
    overest_field: xr.DataArray | None = None,
    underest_field: xr.DataArray | None = None,
) -> dict[str, xr.DataArray]:
    """
    使用自适应阈值方法进行回波特征识别。

    参数
    ----
    field_data : xr.DataArray
        meteva_base 网格数据，可为反射率或其他待识别场。
    dx, dy : float, optional
        水平分辨率，单位米。未给定时根据经纬度坐标近似估算。
    level_m : float, optional
        参与分类的高度，单位米。未给定时使用第一层。
    always_core_thres : float, optional
        始终判为核心回波的阈值。
    bkg_rad_km : float, optional
        计算背景场时使用的平均半径，单位千米。
    use_cosine : bool, optional
        是否使用余弦型阈值关系。
    max_diff : float, optional
        与背景场比较时允许的最大差值。
    zero_diff_cos_val : float, optional
        余弦阈值关系中差值为 0 时对应的场值。
    scalar_diff : float, optional
        固定差值关系中的增量。
    use_addition : bool, optional
        是否使用加法形式构造特征判据。
    calc_thres : float, optional
        参与分类计算的最小阈值。
    weak_echo_thres : float, optional
        弱回波阈值。
    min_val_used : float, optional
        参与背景与特征识别的最小场值。
    dB_averaging : bool, optional
        是否在 dB 空间进行背景平均。
    remove_small_objects : bool, optional
        是否移除面积过小的对象。
    min_km2_size : float, optional
        保留对象的最小面积，单位平方千米。
    binary_close : bool, optional
        是否在识别后执行二值闭运算。
    val_for_max_rad : float, optional
        对应最大影响半径的场值。
    max_rad_km : float, optional
        特征识别时允许的最大影响半径，单位千米。
    core_val : int, optional
        输出结果中核心回波的类别编号。
    nosfcecho : int, optional
        输出结果中无地面回波或未定义区域的类别编号。
    weakecho : int, optional
        输出结果中弱回波的类别编号。
    bkgd_val : int, optional
        输出结果中背景回波的类别编号。
    feat_val : int, optional
        输出结果中特征回波的类别编号。
    estimate_flag : bool, optional
        是否计算高估和低估结果。
    estimate_offset : float, optional
        构造高估和低估场时对原场增减的偏移量。
    overest_field, underest_field : xr.DataArray, optional
        显式提供高估和低估输入场。未给定时使用原场加减偏移量。

    返回
    ----
    dict[str, xr.DataArray]
        回波特征分类结果字典，键与原始 Py-ART 接口保持一致。
    """
    if max_rad_km > 5:
        raise ValueError("max_rad_km must be less than or equal to 5")

    grid = _check_single_context(field_data)
    dx, dy = _get_dx_dy(grid, dx=dx, dy=dy)

    if bkg_rad_km * 1000 < 2 * dx or bkg_rad_km * 1000 < 2 * dy:
        raise ValueError("background radius for averaging must be at least 2 times dx and dy")

    levels = np.asarray(grid.level.values, dtype=np.float32)
    # feature_detection 仅在单层上运行；这里选取目标高度最近层。
    if level_m is None:
        level_index = 0
    else:
        level_index = int(np.argmin(np.abs(levels - level_m)))
    template = grid.isel(member=[0], level=[level_index], time=[0], dtime=[0])
    field_2d = np.asarray(template.values[0, 0, 0, 0, :, :], dtype=np.float32)

    # feature_detection 实际只处理一个二维 CAPPI 截面，
    # 因此这里先选定目标层。
    _, _, feature_best = _feature_detection(
        field_2d,
        dx,
        dy,
        always_core_thres=always_core_thres,
        bkg_rad_km=bkg_rad_km,
        use_cosine=use_cosine,
        max_diff=max_diff,
        zero_diff_cos_val=zero_diff_cos_val,
        scalar_diff=scalar_diff,
        use_addition=use_addition,
        calc_thres=calc_thres,
        weak_echo_thres=weak_echo_thres,
        min_val_used=min_val_used,
        dB_averaging=dB_averaging,
        remove_small_objects=remove_small_objects,
        min_km2_size=min_km2_size,
        binary_close=binary_close,
        val_for_max_rad=val_for_max_rad,
        max_rad_km=max_rad_km,
        core_val=core_val,
        nosfcecho=nosfcecho,
        weakecho=weakecho,
        bkgd_val=bkgd_val,
        feat_val=feat_val,
    )

    comment = (
        f"{nosfcecho} = No surface echo/Undefined, "
        f"{bkgd_val} = Background echo, "
        f"{feat_val} = Features, "
        f"{weakecho} = weak echo"
    )
    results = {
        "feature_detection": _build_level_result(
            template,
            feature_best,
            name="feature_detection",
            standard_name="feature_detection",
            long_name="Feature Detection",
            valid_min=0,
            valid_max=3,
            extra_attrs={"comment_1": comment},
        )
    }

    if not estimate_flag:
        return results

    # =====================================
    # 高估/低估敏感性试验
    #
    # 若用户没有显式提供 over/under 场，
    # 这里对同一二维场加减 estimate_offset，
    # 再分别运行一次识别算法。
    # =====================================
    if underest_field is None:
        under_field_2d = field_2d - estimate_offset
    else:
        under_grid = _check_single_context(underest_field)
        under_template = under_grid.isel(member=[0], level=[level_index], time=[0], dtime=[0])
        under_field_2d = np.asarray(under_template.values[0, 0, 0, 0, :, :], dtype=np.float32)

    if overest_field is None:
        over_field_2d = field_2d + estimate_offset
    else:
        over_grid = _check_single_context(overest_field)
        over_template = over_grid.isel(member=[0], level=[level_index], time=[0], dtime=[0])
        over_field_2d = np.asarray(over_template.values[0, 0, 0, 0, :, :], dtype=np.float32)

    _, _, feature_under = _feature_detection(
        under_field_2d,
        dx,
        dy,
        always_core_thres=always_core_thres,
        bkg_rad_km=bkg_rad_km,
        use_cosine=use_cosine,
        max_diff=max_diff,
        zero_diff_cos_val=zero_diff_cos_val,
        scalar_diff=scalar_diff,
        use_addition=use_addition,
        calc_thres=calc_thres,
        weak_echo_thres=weak_echo_thres,
        min_val_used=min_val_used,
        dB_averaging=dB_averaging,
        remove_small_objects=remove_small_objects,
        min_km2_size=min_km2_size,
        binary_close=binary_close,
        val_for_max_rad=val_for_max_rad,
        max_rad_km=max_rad_km,
        core_val=core_val,
        nosfcecho=nosfcecho,
        weakecho=weakecho,
        bkgd_val=bkgd_val,
        feat_val=feat_val,
    )

    _, _, feature_over = _feature_detection(
        over_field_2d,
        dx,
        dy,
        always_core_thres=always_core_thres,
        bkg_rad_km=bkg_rad_km,
        use_cosine=use_cosine,
        max_diff=max_diff,
        zero_diff_cos_val=zero_diff_cos_val,
        scalar_diff=scalar_diff,
        use_addition=use_addition,
        calc_thres=calc_thres,
        weak_echo_thres=weak_echo_thres,
        min_val_used=min_val_used,
        dB_averaging=dB_averaging,
        remove_small_objects=remove_small_objects,
        min_km2_size=min_km2_size,
        binary_close=binary_close,
        val_for_max_rad=val_for_max_rad,
        max_rad_km=max_rad_km,
        core_val=core_val,
        nosfcecho=nosfcecho,
        weakecho=weakecho,
        bkgd_val=bkgd_val,
        feat_val=feat_val,
    )

    results["feature_under"] = _build_level_result(
        template,
        feature_under,
        name="feature_under",
        standard_name="feature_detection_under",
        long_name="Feature Detection Underestimate",
        valid_min=0,
        valid_max=3,
        extra_attrs={"comment_1": comment},
    )
    results["feature_over"] = _build_level_result(
        template,
        feature_over,
        name="feature_over",
        standard_name="feature_detection_over",
        long_name="Feature Detection Overestimate",
        valid_min=0,
        valid_max=3,
        extra_attrs={"comment_1": comment},
    )

    return results


def hydroclass_semisupervised(
    refl: xr.DataArray | None = None,
    zdr: xr.DataArray | None = None,
    rhv: xr.DataArray | None = None,
    kdp: xr.DataArray | None = None,
    temp: xr.DataArray | None = None,
    iso0: xr.DataArray | None = None,
    hydro_names=("AG", "CR", "LR", "RP", "RN", "VI", "WS", "MH", "IH/HDG"),
    var_names=("Zh", "ZDR", "KDP", "RhoHV", "relH"),
    mass_centers=None,
    weights=np.array([1.0, 1.0, 1.0, 0.75, 0.5]),
    value: float = 50.0,
    lapse_rate: float = -6.5,
    radar_freq=None,
    temp_ref: str = "temperature",
    compute_entropy: bool = False,
    output_distances: bool = False,
    vectorize: bool = False,
) -> dict[str, xr.DataArray]:
    """
    使用半监督方法进行水凝物分类。

    参数
    ----
    refl, zdr, rhv, kdp : xr.DataArray
        meteva_base 偏振量网格数据。
    temp, iso0 : xr.DataArray, optional
        温度场或相对零度层高度场。
    hydro_names : sequence of str, optional
        各水凝物类别的名称列表。
    var_names : sequence of str, optional
        参与分类的变量名称顺序。
    mass_centers : ndarray, optional
        各类别的质心矩阵。未给定时按频段选择默认质心。
    weights : ndarray, optional
        各变量在距离计算中的权重。
    value : float, optional
        将距离转换为比例时使用的衰减控制参数。
    lapse_rate : float, optional
        温度转换为相对零度层高度时使用的温度垂直递减率。
    radar_freq : float, optional
        雷达频率，单位 Hz，用于选择质心。
    temp_ref : str, optional
        温度相关输入的解释方式，可选 temperature 或 height_over_iso0。
    compute_entropy : bool, optional
        是否计算分类熵。
    output_distances : bool, optional
        是否输出各类别比例场。
    vectorize : bool, optional
        是否使用向量化距离分类计算。

    返回
    ----
    dict[str, xr.DataArray]
        水凝物分类及附加结果字典。

    输出字典field_dict包含以下键:

    hydro:字典
        水文气象分类。
            - 0:未分类
            - 1:聚集物
            - 2:冰晶
            - 3:小雨
            - 4:冰缘颗粒
            - 5:雨水
            - 6:垂直定向冰
            - 7:湿雪
            - 8:冰雹融化
            - 9:干雹或高密度雨滴

    如果 compute_entropy为真:
    熵:字典
        水文气象物态解混的香农熵

    如果 output_distances 为 True:
    propX:字典
        给定水文气象类别的极化分解中雷达体积的比例
    """
    # 预检范围只剔除明显填充/异常值；物理极值由 _standardize 饱和到 ±1，
    # 与官方 Py-ART 一致，避免把真实高 KDP/ZDR 等直接置为 NaN。
    input_grids = {}
    grids = []
    for var_name in var_names:
        if var_name == "Zh":
            if refl is None:
                raise ValueError("refl must be provided when 'Zh' is in var_names")
            input_grids[var_name] = _check_single_context(
                refl, valid_val=(-200.0, 200.0, np.nan)
            )
        elif var_name == "ZDR":
            if zdr is None:
                raise ValueError("zdr must be provided when 'ZDR' is in var_names")
            input_grids[var_name] = _check_single_context(
                zdr, valid_val=(-50.0, 50.0, np.nan)
            )
        elif var_name == "KDP":
            if kdp is None:
                raise ValueError("kdp must be provided when 'KDP' is in var_names")
            input_grids[var_name] = _check_single_context(
                kdp, valid_val=(-100.0, 100.0, np.nan)
            )
        elif var_name == "RhoHV":
            if rhv is None:
                raise ValueError("rhv must be provided when 'RhoHV' is in var_names")
            input_grids[var_name] = _check_single_context(
                rhv, valid_val=(-0.5, 1.5, np.nan)
            )
        elif var_name == "relH":
            if temp_ref == "temperature":
                if temp is None:
                    raise ValueError("temp must be provided when 'relH' is in var_names")
                input_grids[var_name] = _check_single_context(
                    temp, valid_val=(-200.0, 100.0, np.nan)
                )
            else:
                if iso0 is None:
                    raise ValueError("iso0 must be provided when 'relH' is in var_names")
                input_grids[var_name] = _check_single_context(
                    iso0, valid_val=(-10000.0, 10000.0, np.nan)
                )
        else:
            raise ValueError(
                "Valid variable names for hydrometeor classification are: relH, Zh, ZDR, KDP and RhoHV"
            )
        grids.append(input_grids[var_name])

    template_grid = grids[0]

    #检查多个输入网格的水平和时间坐标是否一致。
    if not meb.checkout_griddata_same_coords(grids, is_time_match=True):
        raise ValueError("input grid coordinates must be same")

    if mass_centers is None:
        # 先尝试从输入数据属性读取频率；读取不到再使用显式参数 radar_freq。
        frequency = None
        for grid_item in grids:
            freq_attr = grid_item.attrs.get("frequency")
            if freq_attr is None:
                continue
            try:
                frequency = float(np.asarray(freq_attr).squeeze())
                break
            except Exception:
                continue

        if frequency is None:
            frequency = radar_freq

        if frequency is not None:
            mass_centers = _get_mass_centers(frequency)
        else:
            warn(
                "Radar frequency is unknown. Default coefficients for C band will be applied."
            )
            mass_centers = _mass_centers_table()["C"]

    # =====================================
    # 六维网格转算法扫描面
    #
    # 分类函数按 (nrays, nbins) 形式处理二维扫描数据。
    # 这里把 meteva_base 的六维网格统一展平，
    # 待分类结束后再恢复原形状。
    # =====================================
    fields_dict = {}
    original_shape = template_grid.values.shape
    for var_name in var_names:
        scan = _flatten_to_scan(input_grids[var_name])
        if var_name == "relH" and temp_ref == "temperature":
            scan = scan * (1000.0 / lapse_rate)
        fields_dict[var_name] = scan

    # =====================================
    # 标准化与距离分类
    #
    # 每个变量都要先标准化到 [-1, 1]，
    # 再与对应频段的质心做距离比较，
    # 从而得到最终分类结果。
    # =====================================
    mc_std = np.empty(np.shape(mass_centers), dtype=np.float32)
    for i, var_name in enumerate(var_names):
        mc_std[:, i] = _standardize(mass_centers[:, i].copy(), var_name)
        fields_dict[var_name] = _standardize(fields_dict[var_name].copy(), var_name)

    t_vals = None
    if compute_entropy:
        t_vals = _compute_coeff_transform(mc_std, weights=weights, value=value)

    if vectorize:
        hydroclass_data, entropy_data, prop_data = _assign_to_class_scan(
            fields_dict, mc_std, var_names=var_names, weights=weights, t_vals=t_vals
        )
    else:
        hydroclass_data, entropy_data, prop_data = _assign_to_class(
            fields_dict, mc_std, var_names=var_names, weights=weights, t_vals=t_vals
        )

    # 分类结果先恢复为完整六维网格，
    # 再统一封装为 meteva_base.grid_data。
    results = {
        "hydro": _build_full_result(
            template_grid,
            hydroclass_data,
            original_shape,
            name="radar_echo_classification",
            long_name="Hydrometeor classification",
            extra_attrs={
                "labels": ["NC", *hydro_names],
                "ticks": list(range(0, len(hydro_names) + 1)),
                "boundaries": [i - 0.5 for i in range(0, len(hydro_names) + 2)],
            },
        )
    }

    if compute_entropy:
        results["entropy"] = _build_full_result(
            template_grid,
            entropy_data,
            original_shape,
            name="hydroclass_entropy",
            long_name="Shannon entropy of the hydrometeor demixing",
        )

        if output_distances and prop_data is not None:
            for i, hydro_name in enumerate(hydro_names):
                field_name = "proportion_" + hydro_name
                results[field_name] = _build_full_result(
                    template_grid,
                    prop_data[:, :, i],
                    original_shape,
                    name=field_name,
                    long_name=field_name,
                )

    return results


def conv_strat_raut(
    refl: xr.DataArray,
    cappi_level: float | int = 0,
    zr_a: float = 200,
    zr_b: float = 1.6,
    core_wt_threshold: float = 5,
    conv_wt_threshold: float = 1.5,
    conv_scale_km: float = 25,
    min_reflectivity: float = 5,
    conv_min_refl: float = 25,
    conv_core_threshold: float = 42,
    override_checks: bool = False,
) -> xr.DataArray:
    """
    使用小波多分辨率方法进行层状-对流分类。

    参数
    ----
    refl : xr.DataArray
        meteva_base 反射率网格数据。
    cappi_level : float or int, optional
        分类层，可传高度值或层索引。
    zr_a, zr_b : float, optional
        Z-R 关系式系数。
    core_wt_threshold : float, optional
        对流核心与混合回波之间的小波阈值。
    conv_wt_threshold : float, optional
        对流与层状回波之间的小波阈值。
    conv_scale_km : float, optional
        对流尺度与层状尺度的分割尺度，单位千米。
    min_reflectivity : float, optional
        参与分类的最小反射率阈值。
    conv_min_refl : float, optional
        始终视为非对流的反射率上限。
    conv_core_threshold : float, optional
        判定对流核心的反射率阈值。
    override_checks : bool, optional
        是否跳过参数取值范围检查。

    返回
    ----
    xr.DataArray
        单层小波分类结果。

    说明
    ----
    水平分辨率由网格坐标自动估算（对齐原版从 Grid.x/y 读取 dx/dy），
    不对外暴露 dx/dy 参数。
    """
    refl_grid = _check_single_context(refl, valid_val=(-200.0, 200.0, np.nan))
    dx, dy = _get_dx_dy(refl_grid)
    if not np.isclose(dx, dy):
        warn(
            "Grid resolution dx and dy should be comparable for correct results.",
            UserWarning,
        )

    levels = np.asarray(refl_grid.level.values, dtype=np.float32)
    if isinstance(cappi_level, (int, np.integer)) and 0 <= int(cappi_level) < levels.size:
        level_index = int(cappi_level)
    else:
        # 当传入高度值而非索引时，选取最接近该高度的层。
        level_index = int(np.argmin(np.abs(levels - float(cappi_level))))

    scale_break = calc_scale_break(res_meters=dx, conv_scale_km=conv_scale_km)
    scale_break_km = (2 ** (scale_break - 1)) * dx / 1000

    if not override_checks:
        conv_core_threshold = max(40, conv_core_threshold)
        core_wt_threshold = max(4, min(core_wt_threshold, 6))
        conv_wt_threshold = max(1, min(conv_wt_threshold, 2))
        conv_scale_km = max(16, min(conv_scale_km, 32))
        min_reflectivity = max(0, min_reflectivity)
        conv_min_refl = max(25, min(conv_min_refl, 30))

    template = refl_grid.isel(member=[0], level=[level_index], time=[0], dtime=[0])
    # 保留缺测掩码，避免缺测点被当作有效值参与小波分类。
    dbz_data = np.ma.masked_invalid(
        np.asanyarray(template.values[0, 0, 0, 0, :, :], dtype=np.float32)
    )

    # =====================================
    # 小波分类主流程
    #
    # 先计算给定尺度分割下的小波和场，
    # 再依据波谱强度与反射率阈值将格点重新标记为
    # 层状、混合或对流。
    # =====================================
    reclass = wavelet_reclass(
        dbz_data=dbz_data,
        zr_a=zr_a,
        zr_b=zr_b,
        core_wt_threshold=core_wt_threshold,
        conv_wt_threshold=conv_wt_threshold,
        scale_break=scale_break,
        min_reflectivity=min_reflectivity,
        conv_min_refl=conv_min_refl,
        conv_core_threshold=conv_core_threshold,
    )

    return _build_level_result(
        template,
        np.ma.asarray(reclass).astype(np.float32).filled(np.nan),
        name="wt_reclass",
        standard_name="wavelet_echo_class",
        long_name="Wavelet-based multiresolution radar echo classification",
        valid_min=0,
        valid_max=3,
        extra_attrs={
            "classification_description": (
                "0: Unclassified, 1: Stratiform, 2: Mixed-Intermediate, 3: Convective Cores"
            ),
            "parameters": {
                "cappi_level": int(level_index),
                "zr_a": zr_a,
                "zr_b": zr_b,
                "core_wt_threshold": core_wt_threshold,
                "conv_wt_threshold": conv_wt_threshold,
                "conv_scale_km": conv_scale_km,
                "scale_break_used": int(scale_break_km),
                "min_reflectivity": min_reflectivity,
                "conv_min_refl": conv_min_refl,
                "conv_core_threshold": conv_core_threshold,
            },
        },
    )


__all__ = [
    "SteinerConvStratPlugin",
    "FeatureDetectionPlugin",
    "HydroclassSemisupervisedPlugin",
    "ConvStratRautPlugin",
    "steiner_conv_strat",
    "feature_detection",
    "hydroclass_semisupervised",
    "conv_strat_raut",
]
