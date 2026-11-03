# (C) Crown Copyright, Met Office. All rights reserved.
#
# This file is part of 'IMPROVER' and is released under the BSD 3-Clause license.
# See LICENSE in the root of the repository for full licensing details.
"""
模块包含适用于meteva数据结构的风速降尺度插件。

本模块实现了基于地形粗糙度和高度的风速订正算法，
用于提高风速预报的空间分辨率和准确性。
"""

# 导入必要的库
import json
from typing import Optional, Tuple, Union

import numpy as np
import xarray as xr
from numpy import ndarray

import meteva_base as meb

from orographic_wind_downscaling.utils.base_plugin import BasePlugin, PostProcessingPlugin
from orographic_wind_downscaling.utils.utils import rebuild_to_meb_griddata

# 真实缺测数据指示符
RMDI = -32767.0

# 用于确定参考高度的尺度参数（扰动衰减阈值）
ABSOLUTE_CORRECTION_TOL = 0.04

# 用于确定参考高度的缩放参数
HREF_SCALE = 2.0

# 冯·卡门常数
VONKARMAN = 0.4

# 经纬网格间距换算为米时使用的地球半径（与常见气象近似一致）
EARTH_RADIUS_M = 6371000.0

# 海面点的默认粗糙度长度（米）
Z0M_SEA = 0.0001


class FrictionVelocity(BasePlugin):
    """
    摩擦速度计算类
    该类用于计算大气边界层中的摩擦速度 u*，这是表征近地面大气湍流强度的特征速度尺度。
    摩擦速度反映了地表对大气运动的摩擦拖拽作用，是连接地表和大气的关键参数。
    计算原理基于对数风速廓线方程，适用于中性大气条件下的边界层风速分布。
    所需参数包括：
    - 参考高度 h_ref
    - 参考高度处的风速 u_href
    - 表面粗糙度 z_0
    - 计算掩码 mask
    """

    def __init__(
            self, u_href: ndarray, h_ref: ndarray, z_0: ndarray, mask: ndarray
    ) -> None:
        """
        初始化摩擦速度计算类
        参数
        ----------
        u_href:
            二维浮点型数组（float32）—— 参考高度 h_ref 处的风速
        h_ref:
            二维浮点型数组（float32）—— 参考高度
        z_0:
            二维浮点型数组（float32）—— 植被粗糙度长度，反映地表粗糙程度
        mask:
            二维布尔型数组（bool）—— True 表示对应格点需计算摩擦速度 u*
        注意事项：
            * z_0 与 h_ref 必须使用相同的单位（通常为米）。
            * 计算得到的摩擦速度的单位与输入风速 u_href 的单位一致。
            * 所有输入数组必须具有相同的尺寸。
        """
        self.u_href = u_href
        self.h_ref = h_ref
        self.z_0 = z_0
        self.mask = mask
        # 检查输入数组是否具有相同的大小
        array_sizes = [np.size(u_href), np.size(h_ref), np.size(z_0), np.size(mask)]
        if not all(x == array_sizes[0] for x in array_sizes):
            raise ValueError("输入数组 u_href, h_ref, z_0, mask 的大小不一致")

    def process(self) -> ndarray:
        """
        核心计算方法：计算摩擦速度场
        计算公式：
        u* = K * (u_href / ln(h_ref / z_0))
        其中：
        - u* 为摩擦速度
        - K 为冯·卡门常数（Von Karman's constant），通常取 0.4
        - u_href 为参考高度处的风速
        - h_ref 为参考高度
        - z_0 为植被粗糙度长度
        计算步骤：
        1. 初始化结果数组为 RMDI（Real Missing Data Indicator）
        2. 提取掩码为 True 的区域的风速值作为分子
        3. 计算掩码区域的对数项作为分母
        4. 应用公式计算摩擦速度
        5. 将计算结果赋值回结果数组的对应位置
        返回值：
            二维浮点型数组（float32）—— 摩擦速度场，未计算的格点值为 RMDI
        """
        # 初始化结果数组，默认为 RMDI
        ustar = np.full(self.u_href.shape, RMDI, dtype=np.float32)

        # 提取需要计算的区域的风速值
        numerator = self.u_href[self.mask]

        # 计算对数项，忽略可能的无效计算（如除零）
        with np.errstate(invalid="ignore"):
            denominator = np.log(self.h_ref[self.mask] / self.z_0[self.mask])

        # 应用摩擦速度计算公式
        ustar[self.mask] = VONKARMAN * (numerator / denominator)

        return ustar


class RoughnessCorrectionUtilities:
    """
    用于计算风速高度订正与粗糙度订正的类。

    本类封装了基于辅助文件（ancil files）计算粗糙度订正和高度订正的相关函数，
    所需辅助文件/数据包括：

     * 网格单元内的高度标准差 sigma（模式网格插值至后处理网格）
     * 地形轮廓粗糙度 a_over_s（模式网格插值至后处理网格）
     * 植被粗糙度长度 z_0（模式网格插值至后处理网格）
     * 后处理网格地形高度 pporo
     * 插值至后处理网格的模式网格地形高度 modoro
     * 高度层三维/一维网格
     * 高度层三维网格上的风速三维场（来源于上述高度层网格）。
    """

    def __init__(
        self,
        a_over_s: ndarray,
        sigma: ndarray,
        z_0: ndarray,
        pporo: ndarray,
        modoro: ndarray,
        ppres: float,
        modres: float,
    ) -> None:
        """
        初始化粗糙度订正与高度订正的参数。

        参数
        ----------
        a_over_s:
            二维浮点型数组（float32）—— 地形轮廓粗糙度场（无量纲），属于辅助数据，
            计算方法参考 Robinson, D. (2008)《UM 辅助文件制作》（统一模式文档 73 号）。
        sigma:
            二维浮点型数组（float32）—— 网格单元内的高度标准差场，单位为长度单位。
        z_0:
            二维浮点型数组（float32）—— 植被粗糙度长度场，单位为长度单位。
        pporo:
            二维浮点型数组（float32）—— 后处理网格地形高度场。
        modoro:
            二维浮点型数组（float32）—— 插值至后处理网格的模式地形高度场。
        ppres:
            浮点型（Float）—— 后处理网格的网格单元边长。
        modres:
            浮点型（Float）—— 模式网格的网格单元边长。
        """
        # 存储输入参数
        self.a_over_s = a_over_s  # 地形轮廓粗糙度
        self.z_0 = z_0  # 植被粗糙度长度
        self.pporo = pporo  # 后处理网格地形高度
        self.modoro = modoro  # 模式网格地形高度（已插值至后处理网格）
        
        # 计算半峰谷高度（half peak to trough height）
        self.h_over_2 = self.sigma2hover2(sigma)
        
        # 生成高度订正（HC）和粗糙度订正（RC）的掩码
        self.hcmask, self.rcmask = self._setmask()
        
        # 处理植被粗糙度长度的无效值（设置为海面默认值）
        if self.z_0 is not None:
            self.z_0[z_0 <= 0] = Z0M_SEA
        
        # 计算最小和最大水平尺度
        self.dx_min = ppres / 2.0  # 后处理网格无法解析的更小尺度
        self.dx_max = 3.0 * modres  # 模式网格已解析的更大尺度
        
        # 计算地形波数（k = 2*pi / L）
        self.wavenum = self._calc_wav()
        
        # 计算粗糙度订正的参考高度
        self.h_ref = self._calc_h_ref()
        
        # 根据缺失地形数据更新高度订正掩码
        self._refinemask()
        
        # 计算后处理网格与模式网格的地形高度差
        self.h_at0 = self._delta_height()


    def _refinemask(self) -> None:
        """
        基于缺测值 RMDI 和无效地形高度（NaN）重新掩码。

        高度订正（HC）所用的掩码需在以下区域设为 False：
        模式地形或后处理地形中任意一个包含无效数值的格点。
        该步骤无法提前执行，原因是该掩码会被用于波数计算——
        而波数需要且应当在所有半峰谷高度 h_over_2 和轮廓粗糙度 a_over_s 为有效数值的格点上计算。
        """
        self.hcmask[self.pporo == RMDI] = False
        self.hcmask[self.modoro == RMDI] = False
        self.hcmask[np.isnan(self.pporo)] = False
        self.hcmask[np.isnan(self.modoro)] = False

    def _setmask(self) -> Tuple[ndarray, ndarray]:
        """
        生成近似的陆海掩码。

        生成本质上为陆海掩码的掩码数组：
        海上区域的高度标准差和轮廓粗糙度均为 0；
        高度标准差为 0 时，半峰谷高度 h_over_2 会被赋值为缺测值 RMDI。

        返回值：
            - 二维布尔型数组 —— 陆点为 True，海点为 False（用于高度订正 HC）
            - 二维布尔型数组 —— 除海点外，植被粗糙度长度 z_0 无效的格点也为 False（用于粗糙度订正 RC）
        """
        hcmask = np.full(self.h_over_2.shape, True, dtype=bool)
        hcmask[self.h_over_2 <= 0] = False
        hcmask[self.a_over_s <= 0] = False
        hcmask[np.isnan(self.h_over_2)] = False
        hcmask[np.isnan(self.a_over_s)] = False
        rcmask = np.copy(hcmask)
        if self.z_0 is not None:
            rcmask[self.z_0 <= 0] = False
            rcmask[np.isnan(self.z_0)] = False
        return hcmask, rcmask

    @staticmethod
    def sigma2hover2(sigma: ndarray) -> ndarray:
        """
        计算半峰谷高度。

        用于估算峰谷高度的辅助数据包含网格单元内的高度标准差。
        对于正弦波而言，该标准差与波振幅的关系为：

        振幅 = sigma * sqrt(2)

        此处的振幅对应半峰谷高度（h_o_2）。

        参数
        ----------
        sigma:
            二维浮点型数组（float32）—— 网格单元内的高度标准差。

        返回值
        ----------
        二维浮点型数组（float32）—— 半峰谷高度。

        说明：
            sigma = 0 的格点（即海点）会被赋值为 RMDI（缺测值）。
        """
        h_o_2 = np.full(sigma.shape, RMDI, dtype=np.float32)
        h_o_2[sigma > 0] = sigma[sigma > 0] * np.sqrt(2.0)
        return h_o_2

    def _calc_wav(self) -> ndarray:
        """
        计算典型地形长度尺度对应的波数 k。

        本函数用于计算典型地形长度尺度 L 对应的波数 k，公式如下：

        .. math::
          :label:

            k = 2 * \\pi / L

        长度尺度 L 由半峰谷高度 h_over_2 和轮廓粗糙度 a_over_s
        （网格单元内多个横截面的单位长度上坡坡度平均值）近似求得，公式为：

        .. math::
          :label:

            L = 2 * \\rm{h\\_over\\_2} / \\rm{a\\_over\\_s}

        a_over_s 为无量纲量，因其是上坡坡度的总和（坡度的测量单位与计算长度单位一致）。

        半峰谷高度 h_over_2 由网格单元内的高度标准差 sigma 计算得出，公式为：

        .. math::
          :label:

            \\rm{h\\_over\\_2} = \\sqrt{2} * \\rm{sigma}

        该公式基于正弦波假设推导（详见 sigma2hover2 函数/说明）。

        由公式 (1) 和 (2) 可推导出：

        .. math::
          :label:

            k = 2*\\pi / (2 * \\rm{h\\_over\\_2} / \\rm{a\\_over\\_s)}
              = \\rm{a\\_over\\_s} * \\pi / \\rm{h\\_over\\_2}

        返回值：
            二维浮点型数组（float32）—— 波数（单位为输入参数 h_over_2 单位的倒数）。
        """

        # 初始化波数数组，默认值为缺测值
        wavn = np.full(self.a_over_s.shape, RMDI, dtype=np.float32)
        
        # 在有效陆地区域计算波数：k = a_over_s * pi / h_over_2
        wavn[self.hcmask] = (self.a_over_s[self.hcmask] * np.pi) / self.h_over_2[
            self.hcmask
        ]
        
        # 限制波数上限（对应最小水平尺度）
        wavn[wavn > np.pi / self.dx_min] = np.pi / self.dx_min
        
        # 海点设置为缺测值
        wavn[self.h_over_2 == 0] = RMDI
        
        # 限制波数下限（对应最大水平尺度）
        wavn[abs(wavn) < np.pi / self.dx_max] = np.pi / self.dx_max
        
        return wavn

    def _calc_h_ref(self) -> ndarray:
        """
        计算粗糙度订正的参考高度。

        气流与植被粗糙度达到平衡的参考高度与 1/波数（1/wavenum）成正比
        （Howard & Clark, 2007）。

        Vosper (2009) 和 Clark (2009) 认为，在参考高度处，扰动应衰减至某一比例
        系数 ε（即 ABSOLUTE_CORRECTION_TOL 常量）。系数 α 对应 Clark (2009)
        《UK Climatology - Wind Screening Tool》（英国气候学——风筛选工具）中
        的公式 1.3；相关理论依据亦可参考 Vosper (2009)。
        公开可获取的外部参考文献见英国皇冠地产官网（www.thecrownestate.co.uk）
        发布的《Virtual Met Mast Version 1 Methodology and Verification》
        （虚拟气象塔1.0版方法学与验证）报告。

        α 是用于确定参考高度的尺度参数的对数值，当前取值为 0.04（该值对应
        Vosper 和 Clark 文献中均提及的 ε 系数）

        返回值：
            二维浮点型数组（float32）—— 粗糙度订正的参考高度
        """
        # 计算尺度参数 alpha（基于 ABSOLUTE_CORRECTION_TOL）
        alpha = -np.log(ABSOLUTE_CORRECTION_TOL)
        
        # 初始化可调参数和参考高度数组，默认值为缺测值
        tunable_param = np.full(self.wavenum.shape, RMDI, dtype=np.float32)
        h_ref = np.full(self.wavenum.shape, RMDI, dtype=np.float32)
        
        # 在有效陆地区域计算可调参数
        tunable_param[self.hcmask] = alpha + np.log(
            self.wavenum[self.hcmask] * self.h_over_2[self.hcmask]
        )
        
        # 限制可调参数的范围在 [0, 1] 之间
        tunable_param[tunable_param > 1.0] = 1.0
        tunable_param[tunable_param < 0.0] = 0.0
        
        # 计算参考高度：h_ref = tunable_param / wavenum
        h_ref[self.hcmask] = tunable_param[self.hcmask] / self.wavenum[self.hcmask]
        
        # 确保参考高度不低于 1.0 米
        h_ref[h_ref < 1.0] = 1.0
        
        # 限制参考高度不超过半峰谷高度的 HREF_SCALE 倍
        h_ref = np.minimum(h_ref, HREF_SCALE * self.h_over_2)
        
        # 再次确保参考高度不低于 1.0 米
        h_ref[h_ref < 1.0] = 1.0
        
        # 非陆地区域参考高度设置为 0
        h_ref[~self.hcmask] = 0.0
        
        return h_ref

    def calc_roughness_correction(
        self, hgrid: ndarray, uold: ndarray, mask: ndarray
    ) -> ndarray:
        """
        用于执行粗糙度订正的函数。

        参数
        ----------
        hgrid:
            三维或一维浮点型数组（float32）—— 地形以上高度
        uold:
            三维浮点型数组（float32）—— hgrid 高度处的原始风速值
        mask:
            二维布尔型数组（bool）—— 陆点为 True，海点为 False，
            植被粗糙度长度 z_0 无效的格点也为 False

        返回值
        ----------
        三维浮点型数组（float32）—— hgrid 高度处经粗糙度订正后的风速值。
        在参考高度 href 以上，订正后风速与原始风速 uold 相等。

        说明：
            将参考高度以下的风速廓线替换为随高度对数增长的廓线，该廓线的边界条件为：
            参考高度 h_ref 处的风速为原始参考风速 uhref，植被粗糙度长度 z_0 处的风速为 0
        """
        # 计算参考高度处的风速 uhref
        uhref = self._calc_u_at_h(uold, hgrid, self.h_ref, mask)
        
        # 如果高度网格是一维的，扩展为三维以匹配风速数组维度
        if hgrid.ndim == 1:
            hgrid = hgrid[np.newaxis, np.newaxis, :]
        
        # 计算摩擦速度 ustar
        fv = FrictionVelocity(uhref, self.h_ref, self.z_0, mask)
        ustar = fv()
        
        # 创建风速副本以进行订正
        unew = np.copy(uold)
        
        # 标记非掩码区域的参考高度为缺测值
        mhref = self.h_ref
        mhref[~mask] = RMDI
        
        # 确定需要进行粗糙度订正的高度条件（低于参考高度）
        cond = hgrid < self.h_ref[:, :, np.newaxis]

        # 创建全 1 数组用于广播操作
        arr_ones = np.ones(unew.shape, dtype=np.float32)

        # 计算对数风速廓线的各项
        first_arg = (ustar[:, :, np.newaxis] * arr_ones)[cond]
        sec_arg = np.log(
            hgrid / (np.reshape(self.z_0, self.z_0.shape + (1,)) * arr_ones)
        )[cond]

        # 应用对数风速廓线公式：u = (ustar * ln(z/z0)) / k
        unew[cond] = (first_arg * sec_arg) / VONKARMAN

        return unew

    def _calc_u_at_h(
        self,
        u_in: ndarray,
        h_in: ndarray,
        hhere: ndarray,
        mask: ndarray,
        dolog: bool = False,
    ) -> ndarray:
        """
        将 h_in 高度层上的风速 u_in 插值到 hhere 高度的函数。

        参数
        ----------
        u_in:
            三维浮点型数组（float32）—— h_in 高度层上的风速值，最后一维为高度维度
        h_in:
            三维或一维浮点型数组（float32）—— 高度层数组
        hhere:
            二维浮点型数组（float32）—— 待插值的目标高度网格
        mask:
            二维布尔型数组（bool）—— 对插值结果 uath 进行掩码处理
        dolog:
            布尔值，若为 True 则使用对数插值，默认值为 False（线性插值）

        返回值
        ----------
        二维浮点型数组（float32）—— 插值到目标高度 h 处的风速值
        """
        # 掩码处理：将小于 0 的值视为无效
        u_in = np.ma.masked_less(u_in, 0.0)
        h_in = np.ma.masked_less(h_in, 0.0)
        
        # 掩码处理目标高度
        hhere = np.ma.masked_less(hhere, 0.0)
        
        # 找到目标高度所在的上层高度索引
        upidx = np.argmax(h_in > hhere[:, :, np.newaxis], axis=2)
        
        # 找到目标高度所在的下层高度索引
        loidx = np.argmin(
            np.ma.masked_less(hhere[:, :, np.newaxis] - h_in, 0.0), axis=2
        )

        # 根据高度网格的维度获取上层和下层高度值
        if h_in.ndim == 3:
            # 对于三维高度网格，使用 take 方法获取对应索引的高度值
            hup = h_in.take(
                upidx.flatten()
                + np.arange(0, upidx.size * h_in.shape[2], h_in.shape[2])
            )
            hlow = h_in.take(
                loidx.flatten()
                + np.arange(0, loidx.size * h_in.shape[2], h_in.shape[2])
            )
        elif h_in.ndim == 1:
            # 对于一维高度网格，直接通过索引获取高度值
            hup = h_in[upidx].flatten()
            hlow = h_in[loidx].flatten()
        
        # 获取对应高度索引的风速值
        uup = u_in.take(
            upidx.flatten() + np.arange(0, upidx.size * u_in.shape[2], u_in.shape[2])
        )
        ulow = u_in.take(
            loidx.flatten() + np.arange(0, loidx.size * u_in.shape[2], u_in.shape[2])
        )
        
        # 展平掩码数组
        mask = mask.flatten()
        
        # 初始化插值结果数组，默认值为缺测值
        uath = np.full(mask.shape, RMDI, dtype=np.float32)
        
        # 根据需要选择对数插值或线性插值
        if dolog:
            uath[mask] = self._interpolate_log(
                hup[mask], hlow[mask], hhere.flatten()[mask], uup[mask], ulow[mask]
            )
        else:
            uath[mask] = self._interpolate_1d(
                hup[mask], hlow[mask], hhere.flatten()[mask], uup[mask], ulow[mask]
            )
        
        # 重塑插值结果为原始的二维形状
        uath = np.reshape(uath, hhere.shape)
        
        return uath

    @staticmethod
    def _interpolate_1d(
        xup: ndarray, xlow: ndarray, at_x: ndarray, yup: ndarray, ylow: ndarray
    ) -> ndarray:
        """
        适用于二维网格输入层的简易一维线性插值函数。

        参数
        ----------
        xup:
            二维浮点型数组（float32）—— 上层 x 区间边界
        xlow:
            二维浮点型数组（float32）—— 下层 x 区间边界
        at_x:
            二维浮点型数组（float32）—— 待插值的 x 取值（需计算对应 y 值）
        yup:
            二维浮点型数组（float32）—— xup 对应的 y 值（y(xup)）
        ylow:
            二维浮点型数组（float32）—— xlow 对应的 y 值（y(xlow)）

        返回值
        ----------
        二维浮点型数组（float32）—— 基于 xlow 与 xup 间的线性函数关系，
        插值得到的 at_x 对应的 y 值（y(at_x)）
        """
        interp = np.full(xup.shape, RMDI, dtype=np.float32)
        diffs = xup - xlow
        interp[diffs != 0] = ylow[diffs != 0] + (
            (at_x[diffs != 0] - xlow[diffs != 0])
            / diffs[diffs != 0]
            * (yup[diffs != 0] - ylow[diffs != 0])
        )
        interp[diffs == 0] = at_x[diffs == 0] / xup[diffs == 0] * (yup[diffs == 0])
        return interp

    @staticmethod
    def _interpolate_log(
        xup: ndarray, xlow: ndarray, at_x: ndarray, yup: ndarray, ylow: ndarray
    ) -> ndarray:
        """
        简易一维对数插值函数 y(x)，但最低层为地面层时除外。

        参数
        ----------
        xup:
            二维浮点型数组（float32）—— 上层 x 区间边界
        xlow:
            二维浮点型数组（float32）—— 下层 x 区间边界
        at_x:
            二维浮点型数组（float32）—— 待插值的 x 取值（需计算对应 y 值）
        yup:
            二维浮点型数组（float32）—— xup 对应的 y 值（y(xup)）
        ylow:
            二维浮点型数组（float32）—— xlow 对应的 y 值（y(xlow)）

        返回值
        ----------
        二维浮点型数组（float32）—— 基于 xlow 与 xup 间的对数函数关系，
        插值得到的 at_x 对应的 y 值（y(at_x)）
        """
        ain = np.full(xup.shape, RMDI, dtype=np.float32)
        loginterp = np.full(xup.shape, RMDI, dtype=np.float32)
        mfrac = xup / xlow
        mtest = (xup / xlow != 1) & (at_x != xup)
        ain[mtest] = (yup[mtest] - ylow[mtest]) / np.log(mfrac[mtest])
        loginterp[mtest] = ain[mtest] * np.log(at_x[mtest] / xup[mtest]) + yup[mtest]
        mtest = xup / xlow == 1  # below lowest layer, make lin interp
        loginterp[mtest] = at_x[mtest] / xup[mtest] * (yup[mtest])
        mtest = at_x == xup  # just use yup
        loginterp[mtest] = yup[mtest]
        return loginterp

    def _calc_height_corr(
        self,
        u_a: ndarray,
        heightg: ndarray,
        mask: ndarray,
        onemfrac: Union[float, ndarray],
    ) -> ndarray:
        """
        用于计算高度订正附加项

        参数
        ----------
        u_a:
            二维浮点型数组（float32）—— 外部风速（例如：参考高度 h_ref_orig 处的风速）
        heightg:
            一维或三维浮点型数组（float32）—— 地形以上高度
        mask:
            三维布尔型数组（bool）—— 对高度订正附加项（hc_add）结果进行掩码处理
        onemfrac:
            当前为标量值 1，但也可以是位置和高度的函数（例如：三维浮点型数组 float32）

        返回值
        ----------
        三维浮点型数组（float32）—— 风速的高度订正附加项

        说明：
            高度订正是气流的扰动项，该扰动项随高度呈指数衰减。
            垂直偏移量 h_at0 越大（未解析的地形越高），扰动程度越显著。

            扰动越平缓（扰动的水平尺度越大），高度订正量越小
            （因此，波数越大，扰动程度越显著）。
            计算公式：hc_add = exp(-height*wavenumber)*u(href)*h_at_0*wavenumber

            贝塞尔函数项默认取最终系数 1，因此在公式中省略。
        """
        # 获取外部风速的空间维度
        (xdim, ydim) = u_a.shape
        
        # 处理高度网格维度，确保为三维
        if heightg.ndim == 1:
            # 一维高度网格：扩展为三维以匹配风速数组维度
            zdim = heightg.shape[0]
            heightg = heightg[np.newaxis, np.newaxis, :]
        elif heightg.ndim == 3:
            # 三维高度网格：直接使用
            zdim = heightg.shape[2]
        
        # 计算地形高度差与波数的乘积
        ml2 = self.h_at0 * self.wavenum
        
        # 初始化指数衰减因子数组
        expon = np.ones([xdim, ydim, zdim], dtype=np.float32)
        
        # 计算高度与波数的乘积
        mult = self.wavenum[:, :, np.newaxis] * heightg
        
        # 计算指数衰减因子：exp(-height * wavenumber)
        expon[mult > 0.0001] = np.exp(-mult[mult > 0.0001])
        
        # 计算高度订正附加项：hc_add = exp(-z*k) * u(href) * (h_at0*k) * onemfrac
        hc_add = expon * u_a[:, :, np.newaxis] * ml2[:, :, np.newaxis] * onemfrac
        
        # 对非掩码区域的高度订正附加项设为 0
        hc_add[~mask, :] = 0
        
        return hc_add

    def _delta_height(self) -> ndarray:
        """
        用于计算后处理网格（pp-grid）与模式网格高度差值。

        计算后处理网格高度与模式网格高度的差值。

        返回值：
            二维浮点型数组（float32）—— 高度差值（后处理网格值 - 模式网格值）
        """
        delt_z = np.full(self.pporo.shape, RMDI, dtype=np.float32)
        delt_z[self.hcmask] = self.pporo[self.hcmask] - self.modoro[self.hcmask]
        return delt_z

    def do_rc_hc_all(self, hgrid: ndarray, uorig: ndarray) -> ndarray:
        """
        用于调用高度订正（HC）和粗糙度订正（RC）的函数。

        参数
        ----------
        hgrid:
            一维或三维浮点型数组（float32）—— 输入风速对应的高度网格
        uorig:
            三维浮点型数组（float32）—— 各高度层的风速值

        返回值
        ----------
        三维浮点型数组（float32）—— 经粗糙度订正（RC）和高度订正（HC）后的风速值

        参考文献：
        Friedrich, M. M., 2016
        Wind Downscaling Program (Internal Met Office Report)
        """
        # 处理三维高度网格的无效值
        if hgrid.ndim == 3:
            # 标记含有缺测值的高度层
            condition1 = (hgrid == RMDI).any(axis=2)
            # 对含有缺测值的格点禁用高度订正和粗糙度订正
            self.hcmask[condition1] = False
            self.rcmask[condition1] = False
        
        # 创建粗糙度订正的掩码副本，并禁用含有缺测值的风速格点
        mask_rc = np.copy(self.rcmask)
        mask_rc[(uorig == RMDI).any(axis=2)] = False
        
        # 创建高度订正的掩码副本，并禁用含有缺测值的风速格点
        mask_hc = np.copy(self.hcmask)
        mask_hc[(uorig == RMDI).any(axis=2)] = False
        
        # 执行粗糙度订正（如果提供了植被粗糙度长度）
        if self.z_0 is not None:
            unew = self.calc_roughness_correction(hgrid, uorig, mask_rc)
        else:
            # 无植被粗糙度长度时，直接使用原始风速
            unew = uorig
        
        # 计算高度订正参考高度（1/wavenum）处的风速
        uhref_orig = self._calc_u_at_h(uorig, hgrid, 1.0 / self.wavenum, mask_hc)
        
        # 禁用风速小于等于 0 的格点的高度订正
        mask_hc[uhref_orig <= 0] = False
        
        # 设置贝塞尔函数项为 1（参考 Friedrich, 2016）
        # 若贝塞尔函数项不为 1，示例用法：
        # onemfrac = 1.0 - BfuncFrac(nx,ny,nz,heightvec,z_0,waveno, Ustar, UI)
        onemfrac = 1.0
        
        # 计算高度订正附加项
        hc_add = self._calc_height_corr(uhref_orig, hgrid, mask_hc, onemfrac)
        
        # 合并粗糙度订正和高度订正结果
        result = unew + hc_add
        
        # 确保风速非负（高度订正在后处理网格地形低于模式网格时可能为负）
        result[result < 0.0] = 0
        
        return result.astype(np.float32)


class RoughnessCorrection(PostProcessingPlugin):
    """
    风速降尺度主插件：对输入风速执行粗糙度订正（RC）与高度订正（HC）。

    该类是 `RoughnessCorrectionUtilities` 的上层封装，负责完成以下工作：
    1. 统一输入数据结构（`numpy.ndarray` / `xarray.DataArray`）。
    2. 校验辅助场与风速场的空间一致性。
    3. 按“批次维 + (level, lat, lon)”切片循环调用核心订正计算。
    4. 重组输出结构：
       - `numpy.ndarray` 输入返回 `numpy.ndarray`；
       - `xarray.DataArray` 输入返回按 meteva_base 约定维度重组后的 `xarray.DataArray`。

    维度约定：
    - 算法内部计算阶段按 `(level, lat, lon)` 组织三维风速切片。
    - 对于高维输入，除上述三维外的其余维度都作为批次维度独立处理。
    - 对于 `xarray.DataArray` 输入，会先调用 `meb.checkout_griddata` 归一化为
      `member, level, time, dtime, lat, lon` 顺序，再参与计算。

    参数
    ----------
    a_over_s : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
        地形轮廓粗糙度（无量纲）。
    sigma : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
        网格单元内的高度标准差（米）。
    pporo : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
        后处理网格地形高度（米）。
        当传入 xr.DataArray 且未提供 ppres 时，会自动根据坐标估算分辨率（米）。
        投影米制坐标直接取间距；真经纬坐标将度间距换算为米后再取平均。
    modoro : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
        插值至后处理网格的模式地形高度（米）。
    modres : float
        模式原始平均分辨率（米）。
    ppres : float, 可选
        后处理网格分辨率（网格单元平均边长，米）。
        当 pporo 为 np.ndarray 时必须显式提供；当 pporo 为 xr.DataArray 时可省略。
    z0 : np.ndarray 或 xr.DataArray, 形状 (lat, lon)，可选
        植被粗糙度长度（米）。若为None，则跳过粗糙度订正步骤。
    """

    def __init__(
        self,
        a_over_s: Union[np.ndarray, xr.DataArray],
        sigma: Union[np.ndarray, xr.DataArray],
        pporo: Union[np.ndarray, xr.DataArray],
        modoro: Union[np.ndarray, xr.DataArray],
        modres: float,
        ppres: Optional[float] = None,
        z0: Optional[Union[np.ndarray, xr.DataArray]] = None,
    ) -> None:
        """
        初始化 RoughnessCorrection 类。
        
        参数
        ----------
        a_over_s : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
            地形轮廓粗糙度（无量纲）。
        sigma : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
            网格单元内的高度标准差（米）。
        pporo : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
            后处理网格地形高度（米）。
            若传入 DataArray 且 `ppres` 为空，将自动基于坐标推断网格分辨率（米）；
            真经纬网格会将度间距换算为米。
        modoro : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
            插值至后处理网格的模式地形高度（米）。
        modres : float
            模式原始平均分辨率（米）。
        ppres : float, optional
            后处理网格分辨率（网格单元平均边长，米）。
            当 `pporo` 为 DataArray 时可不传；当 `pporo` 为 ndarray 时必须显式传入。
        z0 : np.ndarray 或 xr.DataArray, 形状 (lat, lon)，可选
            植被粗糙度长度（米）。若为None，则跳过粗糙度订正步骤。
        """
        # 存储输入参数
        self.a_over_s = self._to_lat_lon_array(a_over_s, "a_over_s")
        self.sigma = self._to_lat_lon_array(sigma, "sigma")
        # 后处理网格地形高度与分辨率：
        # - DataArray 输入时，可从投影米制或真经纬坐标推断 ppres（始终为米）；
        # - ndarray 输入时，要求外部显式提供 ppres。
        if isinstance(pporo, xr.DataArray):
            pporo = meb.checkout_griddata(pporo)
            if ppres is None:
                ppres = self.infer_grid_resolution_from_coords(pporo)
            self.pporo = np.asarray(pporo.values, dtype=np.float32).squeeze()
            if self.pporo.ndim != 2:
                raise ValueError("pporo 在压缩后必须为二维地形场 (lat, lon)。")
        else:
            self.pporo = np.asarray(pporo, dtype=np.float32)
            if ppres is None:
                raise ValueError("当 pporo 为 ndarray 时，ppres 必须显式传入。")
            if self.pporo.ndim != 2:
                raise ValueError("pporo 必须是二维地形场 (lat, lon)。")

        self.modoro = self._to_lat_lon_array(modoro, "modoro")
        self.z0 = None if z0 is None else self._to_lat_lon_array(z0, "z0")
        self.modres = modres  # 模式原始平均分辨率
        self.ppres = float(ppres)  # 后处理网格分辨率

    @staticmethod
    def _to_lat_lon_array(
        field: Union[np.ndarray, xr.DataArray],
        name: str,
    ) -> np.ndarray:
        """将辅助场统一为二维 `(lat, lon)` 数组。"""
        if isinstance(field, xr.DataArray):
            normalized = meb.checkout_griddata(field, is_single=True)
            values = np.asarray(normalized.values.squeeze(), dtype=np.float32)
        else:
            values = np.asarray(field, dtype=np.float32)

        if values.ndim != 2:
            raise ValueError(
                f"{name} 必须是二维单场 `(lat, lon)`，当前维度为 {values.ndim}。"
            )
        return values

    @staticmethod
    def _coord_units_token(coord: xr.DataArray) -> str:
        """归一化坐标 units 字符串，便于判断米制/角度。"""
        return str(coord.attrs.get("units", "")).strip().lower()

    @classmethod
    def _coords_are_geographic_degrees(
        cls,
        data: xr.DataArray,
        y_coord: xr.DataArray,
        x_coord: xr.DataArray,
    ) -> bool:
        """判断空间坐标是否为真经纬（度）。

        判定顺序：

        1. 坐标 ``units``：明确为米 → 否；含 ``degree`` → 是。
        2. ``grid_mapping_attrs``：``latitude_longitude`` 等 → 是；投影类 → 否。
        3. **两侧均无 ``units``**：meb 网格一般默认为经纬，常不写空间坐标单位，
           此时视为经纬。例外：数值远超地理经纬度合理范围时，仍判为投影米制
           （例如官方样例仅把 ``projection_*`` 重命名为 ``lat/lon``、未改数值与单位）。
        """
        y_units = cls._coord_units_token(y_coord)
        x_units = cls._coord_units_token(x_coord)
        meter_tokens = ("m", "metre", "meter", "metres", "meters")
        if y_units in meter_tokens or x_units in meter_tokens:
            return False
        if "degree" in y_units or "degree" in x_units:
            return True

        mapping_raw = data.attrs.get("grid_mapping_attrs")
        if isinstance(mapping_raw, str) and mapping_raw.strip():
            try:
                mapping = json.loads(mapping_raw)
            except json.JSONDecodeError:
                mapping = {}
            if isinstance(mapping, dict):
                name = str(mapping.get("grid_mapping_name", "")).lower()
                if name in ("latitude_longitude", "latlon", "geographic"):
                    return True
                if "lambert" in name or "projected" in name or "azimuthal" in name:
                    return False

        y = np.asarray(y_coord.values, dtype=np.float64)
        x = np.asarray(x_coord.values, dtype=np.float64)
        y = y[np.isfinite(y)]
        x = x[np.isfinite(x)]

        # 无单位：meb 默认经纬；空坐标或数值落在经纬范围内 → True
        # 数值像投影米制（|y|≫90 或 |x|≫360）→ False，避免维名重命名误判
        units_missing = (not y_units) and (not x_units)
        if y.size == 0 or x.size == 0:
            return bool(units_missing)

        in_geo_range = bool(
            np.nanmax(np.abs(y)) <= 90.0 + 1e-6
            and np.nanmax(np.abs(x)) <= 360.0 + 1e-6
        )
        if units_missing:
            return in_geo_range
        # 仅一侧有未识别单位时，仍用范围启发
        return in_geo_range


    @staticmethod
    def infer_grid_resolution_from_coords(
        data: xr.DataArray,
        y_name: Optional[str] = None,
        x_name: Optional[str] = None,
    ) -> float:
        """基于二维空间坐标估算网格分辨率（米）。

        - 投影米制坐标：直接取 ``bounds``/``points`` 差分（米）。
        - 真经纬坐标：将纬度/经度差分换算为米后再平均；
          东西向间距按代表纬度 ``cos(lat)`` 缩放。

        参数
        ----------
        data : xr.DataArray
            包含空间坐标的输入场（通常传入目标网格地形场）。
        y_name : str, optional
            y 方向坐标名。未提供时会尝试自动识别。
        x_name : str, optional
            x 方向坐标名。未提供时会尝试自动识别。

        返回
        -------
        float
            估算的网格分辨率（米），定义为 y/x 分辨率的平均值。
            计算时优先使用坐标 `bounds`，若不存在则退回 `points` 差分。

        异常
        -------
        ValueError
            当无法识别空间坐标或坐标点数不足时抛出。
        """
        if not isinstance(data, xr.DataArray):
            raise TypeError("data 必须是 xarray.DataArray。")

        dims = list(data.dims)

        def _pick_dim(candidates, fallback_index):
            for name in candidates:
                if name in dims:
                    return name
            return dims[fallback_index] if len(dims) >= abs(fallback_index) else None

        y_name = y_name or _pick_dim(("lat", "projection_y_coordinate", "y"), -2)
        x_name = x_name or _pick_dim(("lon", "projection_x_coordinate", "x"), -1)

        if y_name is None or x_name is None:
            raise ValueError("无法从输入中识别空间维度名称。")
        if y_name not in data.coords or x_name not in data.coords:
            raise ValueError(f"输入缺少坐标 {y_name}/{x_name}，无法推断网格分辨率。")

        y_coord = data.coords[y_name]
        x_coord = data.coords[x_name]

        def _resolution_from_coord(coord: xr.DataArray) -> float:
            # CF 坐标若存在 bounds，优先用 bounds 计算分辨率。
            bound_name = coord.attrs.get("bounds")
            if bound_name and bound_name in data.coords:
                bounds = np.asarray(data.coords[bound_name].values, dtype=np.float64)
                if bounds.ndim == 2 and bounds.shape[0] >= 1 and bounds.shape[1] >= 2:
                    widths = np.abs(bounds[:, 1] - bounds[:, 0])
                    widths = widths[np.isfinite(widths)]
                    if widths.size > 0:
                        return float(np.median(widths))

            # 无 bounds 时使用 points 的相邻差分。
            points = np.asarray(coord.values, dtype=np.float64)
            if points.size < 2:
                raise ValueError("坐标点数不足，无法推断网格分辨率。")
            diffs = np.abs(np.diff(points))
            diffs = diffs[np.isfinite(diffs)]
            if diffs.size == 0:
                raise ValueError("坐标差分无有效值，无法推断网格分辨率。")
            return float(np.median(diffs))

        dy = _resolution_from_coord(y_coord)
        dx = _resolution_from_coord(x_coord)

        # 真经纬：度间距 → 米；投影米制（含维名重命名）保持原间距。
        if RoughnessCorrection._coords_are_geographic_degrees(data, y_coord, x_coord):
            lat_points = np.asarray(y_coord.values, dtype=np.float64)
            lat_points = lat_points[np.isfinite(lat_points)]
            lat0 = float(np.median(lat_points)) if lat_points.size else 0.0
            dy_m = np.deg2rad(dy) * EARTH_RADIUS_M
            dx_m = np.deg2rad(dx) * EARTH_RADIUS_M * np.cos(np.deg2rad(lat0))
            return float(np.mean([abs(dy_m), abs(dx_m)]))

        return float(np.mean([dy, dx]))

    def process(
        self,
        wind_speed: Union[np.ndarray, xr.DataArray],
        height_grid: Optional[np.ndarray] = None,
    ) -> Union[np.ndarray, xr.DataArray]:
        """
        对风速进行地形粗糙度订正和高度订正。

        参数
        ----------
        wind_speed : np.ndarray or xr.DataArray
            输入风速场。
            - 若为 `np.ndarray`，默认最后三个维度为 `(level, lat, lon)`；
              前导维度全部作为批次维处理。
            - 若为 `xr.DataArray`，先按 meteva_base 维度规范化后再计算。

        height_grid : np.ndarray or None
            风速层对应的高度网格，一维数组或三维数组：
            - 一维数组：表示所有点位共用的固定高度值
            - 三维数组：表示随空间变化的高度值
            当 `wind_speed` 为 `xr.DataArray` 且未显式提供该参数时，
            默认使用输入中的 `level` 坐标。
            当 `wind_speed` 为 `np.ndarray` 时，必须显式传入。

        返回值
        ----------
        np.ndarray 或 xr.DataArray
            经修正后的风速结果。
            - 输入为 np.ndarray 时返回 np.ndarray；
            - 输入为 xr.DataArray 时返回按 meteva_base 维度重组的 xr.DataArray。
        """
        template_da: Optional[xr.DataArray] = None

        # 处理输入数据类型
        if isinstance(wind_speed, xr.DataArray):
            template_da = meb.checkout_griddata(wind_speed)

            # 从DataArray中获取高度网格（如果未提供）
            if height_grid is None:
                height_grid = template_da.level.values.astype(np.float32)
            # DataArray 分支保持标准六维，不做 squeeze，避免 level 轴语义丢失
            wind_speed = np.asarray(template_da.values, dtype=np.float32)
            ndim = wind_speed.ndim
            axes = list(range(ndim))
            level_axis, lat_axis, lon_axis = 1, 4, 5
            n_levels = wind_speed.shape[level_axis]
            n_lat = wind_speed.shape[lat_axis]
            n_lon = wind_speed.shape[lon_axis]
        else:
            # 处理NumPy数组输入
            ndim = wind_speed.ndim
            if ndim == 2:
                wind_speed = np.asarray([wind_speed])
                ndim = wind_speed.ndim

            axes = list(range(ndim))
            level_axis = axes[-3]
            lat_axis = axes[-2]
            lon_axis = axes[-1]
            n_levels = wind_speed.shape[level_axis]
            n_lat = wind_speed.shape[lat_axis]
            n_lon = wind_speed.shape[lon_axis]

        if height_grid is None:
            raise ValueError("height_grid 不能为空：NumPy输入必须显式传入高度网格。")

        height_grid = np.asarray(height_grid, dtype=np.float32)

        # 检查辅助数据的空间维度是否匹配
        expected_spatial = (n_lat, n_lon)
        if self.a_over_s.shape != expected_spatial:
            raise ValueError(f"a_over_s 形状 {self.a_over_s.shape} 与预期 {expected_spatial} 不匹配")
        if self.sigma.shape != expected_spatial:
            raise ValueError(f"sigma 形状 {self.sigma.shape} 与预期 {expected_spatial} 不匹配")
        if self.pporo.shape != expected_spatial:
            raise ValueError(f"pporo 形状 {self.pporo.shape} 与预期 {expected_spatial} 不匹配")
        if self.modoro.shape != expected_spatial:
            raise ValueError(f"modoro 形状 {self.modoro.shape} 与预期 {expected_spatial} 不匹配")
        if self.z0 is not None and self.z0.shape != expected_spatial:
            raise ValueError(f"z0 形状 {self.z0.shape} 与预期 {expected_spatial} 不匹配")

        # 准备高度网格用于核心订正例程
        if height_grid.ndim == 1:
            # 检查一维高度网格长度是否与高度层数匹配
            if height_grid.shape[0] != n_levels:
                raise ValueError(f"一维高度网格长度 {height_grid.shape[0]} 与高度层数 {n_levels} 不匹配")
            hgrid_for_rc = height_grid  # 保持一维，后续会自动广播
        elif height_grid.ndim == 3:
            # 检查三维高度网格形状是否匹配
            if height_grid.shape != (n_levels, n_lat, n_lon):
                raise ValueError(f"三维高度网格形状 {height_grid.shape} 与预期 ({n_levels}, {n_lat}, {n_lon}) 不匹配")
            # 转置为 (lat, lon, levels) 格式，以适应核心订正例程
            hgrid_for_rc = np.transpose(height_grid, (1, 2, 0))
        else:
            # 高度网格必须是一维或三维
            raise ValueError(f"height_grid 必须是一维或三维，当前维度为 {height_grid.ndim}")

        # 识别批量维度并重新排序为 (batch..., levels, lat, lon)
        batch_axes = [i for i in axes if i not in (level_axis, lat_axis, lon_axis)]
        new_order = batch_axes + [level_axis, lat_axis, lon_axis]
        wind_t = np.transpose(wind_speed, new_order)

        # 展平批量维度
        batch_shape = [wind_t.shape[i] for i in range(len(batch_axes))]
        total_batch = int(np.prod(batch_shape))
        wind_2d = wind_t.reshape((total_batch, n_levels, n_lat, n_lon))

        # 创建粗糙度订正工具实例
        rc_utils = RoughnessCorrectionUtilities(
            self.a_over_s, self.sigma, self.z0,
            self.pporo, self.modoro,
            self.ppres, self.modres
        )

        # 初始化输出数组
        out_2d = np.zeros_like(wind_2d, dtype=np.float32)

        # 处理每个批量元素
        for i in range(total_batch):
            u_slice = wind_2d[i]  # (levels, lat, lon)
            # 转置为 (lat, lon, levels) 格式，以适应核心订正例程
            u_3d = np.transpose(u_slice, (1, 2, 0))
            # 执行粗糙度订正和高度订正
            result_3d = rc_utils.do_rc_hc_all(hgrid_for_rc, u_3d)
            # 转回 (levels, lat, lon) 格式
            result_slice = np.transpose(result_3d, (2, 0, 1))
            # 存储结果
            out_2d[i] = result_slice

        # 恢复批量维度的原始形状
        out_t = out_2d.reshape(wind_t.shape)

        # 反转转置，恢复原始维度顺序
        inv_order = [new_order.index(i) for i in axes]
        output = np.transpose(out_t, inv_order)

        if template_da is not None:
            result_da = rebuild_to_meb_griddata(
                output,
                template_da,
                name=template_da.name,
                units=template_da.attrs.get("units"),
            )
            # 保留 standard_name=wind_speed 的语义，同时补充处理后变量的可读描述。
            result_da.attrs["long_name"] = "downscaled wind speed"
            return result_da

        return output
