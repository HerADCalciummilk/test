# -*- coding: utf-8 -*-
"""风速订正辅助计算。

``RoughnessCorrection`` 调用这里的工具类。数值公式与原实现一致。
"""
from typing import Optional, Tuple, Union

import numpy as np
import xarray as xr
from numpy import ndarray

import meteva_base as meb

from orographic_wind_downscaling.src.wind_downscaling import (
    ABSOLUTE_CORRECTION_TOL,
    DX_MAX_FACTOR,
    DX_MIN_FACTOR,
    FrictionVelocity,
    HREF_SCALE,
    RMDI,
    VONKARMAN,
    Z0M_SEA,
)

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
        *,
        absolute_correction_tol: float = ABSOLUTE_CORRECTION_TOL,
        href_scale: float = HREF_SCALE,
        dx_max_factor: float = DX_MAX_FACTOR,
        dx_min_factor: float = DX_MIN_FACTOR,
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
        absolute_correction_tol:
            扰动衰减阈值 ε，默认 0.04。主要影响粗糙度订正参考高度。
        href_scale:
            参考高度相对半峰谷高度的上限倍数，默认 2.0。减小可压低 RC 作用厚度。
        dx_max_factor:
            ``dx_max = dx_max_factor * modres``，默认 3.0。影响波数下限裁剪。
        dx_min_factor:
            ``dx_min = dx_min_factor * ppres``，默认 0.5。影响波数上限裁剪。
        """
        # 存储输入参数
        self.a_over_s = a_over_s  # 地形轮廓粗糙度
        self.z_0 = z_0  # 植被粗糙度长度
        self.pporo = pporo  # 后处理网格地形高度
        self.modoro = modoro  # 模式网格地形高度（已插值至后处理网格）
        self.absolute_correction_tol = float(absolute_correction_tol)
        self.href_scale = float(href_scale)
        self.dx_max_factor = float(dx_max_factor)
        self.dx_min_factor = float(dx_min_factor)
        if self.absolute_correction_tol <= 0.0 or self.absolute_correction_tol >= 1.0:
            raise ValueError("absolute_correction_tol 必须落在 (0, 1)。")
        if self.href_scale <= 0.0:
            raise ValueError("href_scale 必须为正。")
        if self.dx_max_factor <= 0.0 or self.dx_min_factor <= 0.0:
            raise ValueError("dx_max_factor 与 dx_min_factor 必须为正。")

        # 计算半峰谷高度（half peak to trough height）
        self.h_over_2 = self.sigma2hover2(sigma)
        
        # 生成高度订正（HC）和粗糙度订正（RC）的掩码
        self.hcmask, self.rcmask = self._setmask()
        
        # 处理植被粗糙度长度的无效值（设置为海面默认值）
        if self.z_0 is not None:
            self.z_0[z_0 <= 0] = Z0M_SEA
        
        # 计算最小和最大水平尺度
        self.dx_min = self.dx_min_factor * ppres
        self.dx_max = self.dx_max_factor * modres
        
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
        # 计算尺度参数 alpha（基于 absolute_correction_tol / ε）
        alpha = -np.log(self.absolute_correction_tol)
        
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
        
        # 限制参考高度不超过半峰谷高度的 href_scale 倍
        h_ref = np.minimum(h_ref, self.href_scale * self.h_over_2)
        
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
        hc_add = (
            expon
            * u_a[:, :, np.newaxis]
            * ml2[:, :, np.newaxis]
            * onemfrac
        )
        
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

    def do_rc_hc_all(
        self,
        hgrid: ndarray,
        uorig: ndarray,
    ) -> Tuple[ndarray, ndarray]:
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
        ``(订正风速, hc_add)``：
        - 订正风速：经 RC + HC 且非负截断后的三维场；
        - ``hc_add``：高度订正附加项（截断前），与风速同形。

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
        
        return result.astype(np.float32), hc_add.astype(np.float32)
