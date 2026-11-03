# !/usr/bin/python
# -*-coding:utf-8 -*-
"""
运行依赖：
numpy>=1.26.1
scipy>=1.11.3
meteva>=1.9.1.4
"""
from __future__ import annotations

import numpy as np
import xarray as xr
from typing import List
from scipy.ndimage import map_coordinates
from scipy.fft import fft2, fftshift
from scipy.interpolate import RegularGridInterpolator
import meteva.base as meb
import warnings

warnings.filterwarnings('ignore')


class FFTMergePlugin(object):
    """
    该算法源于复旦大学，基于谱方法和迭代优化理论,采用迭代优化策略,核心思想是通过最小化两个字段的差异，迭代求解频域下的位移场，实现空间对齐
    - 利用双线性插值进行数据重采样以适应不同分辨率需求
    - 使用反射边界扩展技术避免边缘效应
    - 应用双三次插值进行精确的亚像素级位移计算
    - 通过频域求解方法高效计算位移场
    - 结合约束权重和平滑滤波保证位移场的物理合理性
    可能的应用场景：
    - 台风圈的调整移动
    - 集合预报多组数据的融合
    """

    def __init__(self, weight_value=None, power_model=None, l_scale=None, reflect_pad=None):
        # 显式参数优先，否则读 resource/conf.ini，再没有用预设。
        consts = {
            "weight_value": 0.1,
            "power_model": 2,
            "l_scale": 1,
            "reflect_pad": 25,
        }
        try:
            from utils.util_env import get_algo_constants
            consts.update(get_algo_constants())
        except ImportError:
            pass
        if weight_value is not None:
            consts["weight_value"] = weight_value
        if power_model is not None:
            consts["power_model"] = power_model
        if l_scale is not None:
            consts["l_scale"] = l_scale
        if reflect_pad is not None:
            consts["reflect_pad"] = reflect_pad
        self.weight_value = float(consts["weight_value"])
        self.power_model = int(consts["power_model"])
        self.l_scale = int(consts["l_scale"])
        self.reflect_pad = int(consts["reflect_pad"])

    def __call__(self, main_da: xr.DataArray, ass_da_list: List[xr.DataArray],
                 feature_border: int = 192, max_iterations: int = 1024, move_percent: float = 1.0) -> xr.DataArray:
        """
        该函数实现了基于傅里叶变换的特征匹配与数据融合算法，主要流程如下：
        1. 参数验证：检查移动比例是否在有效范围内(0, 1]
        2. 数据提取：从输入的xarray数据集中提取numpy数组格式的核心数据
        3. 特征匹配：利用傅里叶变换识别主数据与辅助数据间的特征位移关系
        4. 位移计算：对每个辅助数据集计算位移场，然后进行加权平均
        5. 数据融合：根据计算得到的位移场对原始数据进行平流变换，生成融合结果

        Parameters
        ----------
        main_da : xr.DataArray
            主数据，待处理的主要气象场，依次包含member，level，time，dtime，lat，lon共6个维度的信息;
            - member维度的length是2，则按照uv矢量处理，如果为1则按照标量处理
            - level， time， dtime这三个维度的length为1
            - lat, lon是数据的正常维度信息
        ass_da_list : list[xr.DataArray]
            辅助数据列表，用于与主数据集进行特征匹配和融合,每个辅助数据集应具有与主数据集相同的维度结构和空间分辨率
        feature_border : int, default 192
            特征参数量，默认值为192（常规尺寸192*192）。调整此参数可以提高运行效率：
            简单测试显示，调整到128可提升2/3的效率；但参数值过小可能导致数据出现较大形变，进而引发数据失真，
            建议根据自身数据特征进行试验调整，选取最优参数。
            此参数决定了内部重采样过程中的网格分辨率，影响特征检测的精度和计算效率
        max_iterations : int, default 1024
            最大迭代次数。减少迭代次数可提升运行效率；但迭代次数过少可能导致特征识别异常，进而引发数据失真，
            建议根据自身数据情况进行试验调整，选取最优参数。
            算法会在达到最大迭代次数或满足收敛条件时停止
        move_percent : float, default 1.0
            移动百分比，默认为1.0，取值范围为(0, 1]。
            说明：1 - 移动到ass_arr的目标位置；0.5 - 移动到主数据与ass_arr的中间位置。
            此参数控制融合过程中主数据向辅助数据特征位置移动的程度

        Returns
        -------
        xr.DataArray
            返回融合后的数据，数据结构与main_da一致

        Notes
        -----
        1. 算法基于傅里叶变换的频域分析，特别适合处理具有明显空间特征的气象数据
        2. 陆地与海上气象数据偏差较大的情况下，建议分开单独处理，避免互相干扰导致融合效果下降
        3. 为了提升效率，如果数据量较大，建议将需要调整的部分裁剪出来进行融合处理，处理完成后再贴回原数据集，此方法可显著提升运行效率
        4. 该算法对强特征（如台风、锋面等）有较好的追踪和匹配能力
        5. 可用于集合预报数据的融合处理，提高预报精度

        Examples
        --------
        >>> # 普通数据合并
        >>> ftt_merge = FttMergePlugin()
        >>> merged_da = ftt_merge(main_da, [ass_da], feature_border=128)
        >>> # uv风数据合并
        >>> ftt_merge = FttMergePlugin()
        >>> merged_uv_da = ftt_merge(main_uv_da, [ass_uv_da], feature_border=128)
        >>> # 集合预报数据合并
        >>> ftt_merge = FttMergePlugin()
        >>> merged_ensemble_da = ftt_merge(main_da, [ensemble1_da, ensemble2_da...], feature_border=128)
        """
        return self.process(main_da, ass_da_list, feature_border, max_iterations, move_percent)

    def process(self, main_da: xr.DataArray, ass_da_list: List[xr.DataArray],
                feature_border: int = 192, max_iterations: int = 1024, move_percent: float = 1.0) -> xr.DataArray:
        """
        该函数实现了基于傅里叶变换的特征匹配与数据融合算法，主要流程如下：
        1. 参数验证：检查移动比例是否在有效范围内(0, 1]
        2. 数据提取：从输入的xarray数据集中提取numpy数组格式的核心数据
        3. 特征匹配：利用傅里叶变换识别主数据与辅助数据间的特征位移关系
        4. 位移计算：对每个辅助数据集计算位移场，然后进行加权平均
        5. 数据融合：根据计算得到的位移场对原始数据进行平流变换，生成融合结果

        Parameters
        ----------
        main_da : xr.DataArray
            主数据，待处理的主要气象场，依次包含member，level，time，dtime，lat，lon共6个维度的信息;
            - member维度的length是2，则按照uv矢量处理，如果为1则按照标量处理
            - level， time， dtime这三个维度的length为1
            - lat, lon是数据的正常维度信息
        ass_da_list : list[xr.DataArray]
            辅助数据列表，用于与主数据集进行特征匹配和融合,每个辅助数据集应具有与主数据集相同的维度结构和空间分辨率
        feature_border : int, default 192
            特征参数量，默认值为192（常规尺寸192*192）。调整此参数可以提高运行效率：
            简单测试显示，调整到128可提升2/3的效率；但参数值过小可能导致数据出现较大形变，进而引发数据失真，
            建议根据自身数据特征进行试验调整，选取最优参数。
            此参数决定了内部重采样过程中的网格分辨率，影响特征检测的精度和计算效率
        max_iterations : int, default 1024
            最大迭代次数。减少迭代次数可提升运行效率；但迭代次数过少可能导致特征识别异常，进而引发数据失真，
            建议根据自身数据情况进行试验调整，选取最优参数。
            算法会在达到最大迭代次数或满足收敛条件时停止
        move_percent : float, default 1.0
            移动百分比，默认为1.0，取值范围为(0, 1]。
            说明：1 - 移动到ass_arr的目标位置；0.5 - 移动到主数据与ass_arr的中间位置。
            此参数控制融合过程中主数据向辅助数据特征位置移动的程度

        Returns
        -------
        xr.DataArray
            返回融合后的数据，数据结构与main_da一致

        Notes
        -----
        1. 算法基于傅里叶变换的频域分析，特别适合处理具有明显空间特征的气象数据
        2. 陆地与海上气象数据偏差较大的情况下，建议分开单独处理，避免互相干扰导致融合效果下降
        3. 为了提升效率，如果数据量较大，建议将需要调整的部分裁剪出来进行融合处理，处理完成后再贴回原数据集，此方法可显著提升运行效率
        4. 该算法对强特征（如台风、锋面等）有较好的追踪和匹配能力
        5. 可用于集合预报数据的融合处理，提高预报精度

        Examples
        --------
        >>> # 普通数据合并
        >>> ftt_merge = FttMergePlugin()
        >>> merged_da = ftt_merge(main_da, [ass_da], feature_border=128)
        >>> # uv风数据合并
        >>> ftt_merge = FttMergePlugin()
        >>> merged_uv_da = ftt_merge(main_uv_da, [ass_uv_da], feature_border=128)
        >>> # 集合预报数据合并
        >>> ftt_merge = FttMergePlugin()
        >>> merged_ensemble_da = ftt_merge(main_da, [ensemble1_da, ensemble2_da...], feature_border=128)
        """
        # 参数检查
        if move_percent <= 0 or move_percent > 1:
            raise ValueError("move_percent must be in (0, 1]")
        # 读取数据
        main_da_arr = main_da.values
        main_arr = main_da_arr[0][0][0][0]
        main_grd = meb.get_grid_of_data(main_da)
        member_arr = main_da.coords["member"]
        if member_arr.shape[0] == 2:
            other_arr = main_da_arr[1][0][0][0]
        else:
            other_arr = None
        ass_arr_list = []
        for eve in ass_da_list:
            eve_arr = eve.values
            eve_arr = eve_arr[0][0][0][0]
            ass_arr_list.append(eve_arr)
        # 合并数据
        mu_arr, mv_arr = self._move_arr_with_several(main_arr, ass_arr_list, other_arr,
                                                     feature_border, max_iterations, move_percent)
        # 格式化返回数据
        if mv_arr is None:
            n_grd = meb.grid(main_grd.glon, main_grd.glat)
            uv_da = meb.grid_data(n_grd, mu_arr)
        else:
            n_grd = meb.grid(main_grd.glon, main_grd.glat, member_list=["u", "v"])
            uv_da = meb.grid_data(n_grd, np.array([mu_arr, mv_arr]))
        return uv_da

    def _move_arr_with_several(self, main_arr: np.ndarray, ass_u_arrs: list | tuple, other_arr: np.ndarray | None,
                               feature_border: int = 192, max_iterations: int = 1024,
                               move_percent: float = 1.0) -> tuple:
        """
        对ass_arrs的每一组数据进行特征值计算偏移量，进行加权平均，将main_arr中的对应特征移动到加权平均的位置

        :param main_arr: np.ndarray，2D
        :param ass_u_arrs: [np.ndarray]，3D，多个[ass_u_arr, ass_u_arr, ...]
        :param other_arr: np.ndarray，2D
        :param feature_border: 特征参数量，192*192，默认为192，调整此参数可以提高效率；
            简单测试显示，调整到128，提升2/3的效率；
            但是如果数量太少，相关的数据可能出现较大的形变导致失真，可根据自身的数据特征进行试验调整，选取最优参数
        :param max_iterations: 最大迭代次数；减少迭代次数也可提升效率；但是也可能导致迭代次数过少，特征识别异常，
            导致数据失真，可根据自身数据情况进行试验调整，选取最优参数
        :param move_percent: 移动百分比，默认为1, (0, 1]
            1 - 是指移动到ass_arr的位置
            0.5 - 是指移动到一半的位置

        :return: (u_arr, v_arr) - (np.ndarray, np.ndarray), 2D
        """
        total_x_arr = None
        total_y_arr = None
        arr_count = 0
        for eve_arr in ass_u_arrs:
            t_x_move_arr, t_y_move_arr = self._calc_moved_arr(main_arr, eve_arr, feature_border, max_iterations)
            if total_x_arr is None:
                total_x_arr = t_x_move_arr
                total_y_arr = t_y_move_arr
            else:
                total_x_arr += t_x_move_arr
                total_y_arr += t_y_move_arr
            arr_count += 1
        x_move_arr = total_x_arr / arr_count
        y_move_arr = total_y_arr / arr_count
        if move_percent < 1.0:
            x_move_arr = x_move_arr * move_percent
            y_move_arr = y_move_arr * move_percent
        moved_main_arr = self._advect(main_arr, x_move_arr, y_move_arr)
        moved_main_arr = self._clean_arr(moved_main_arr, main_arr)
        if other_arr is not None:
            moved_other_arr = self._advect(other_arr, x_move_arr, y_move_arr)
            moved_other_arr = self._clean_arr(moved_other_arr, main_arr)
        else:
            moved_other_arr = None
        return moved_main_arr, moved_other_arr

    def _clean_arr(self, a_arr: np.ndarray, source_arr: np.ndarray) -> np.ndarray:
        """
        对数据进行清除，将数据中非0值设置为0
        """
        inf_mask = np.isinf(a_arr)
        a_arr[inf_mask] = source_arr[inf_mask]
        return a_arr

    def _myim_resize(self, in_arr: np.ndarray, size_new):
        """
        ==myimresize
        对数据进行双线性插值，获取其他形状大小size_new
        """
        size_in = in_arr.shape
        x_off = (size_in[1] - 1) / size_new[1]
        y_off = (size_in[0] - 1) / size_new[0]
        # 定义新的网格
        x_new = np.linspace(x_off / 2, size_in[1] - 1 - x_off / 2, size_new[1])  # 新的网格点数
        y_new = np.linspace(y_off / 2, size_in[0] - 1 - y_off / 2, size_new[0])
        # 创建坐标网格
        X, Y = np.meshgrid(x_new, y_new)
        # 进行双线性插值
        coords = np.array([Y.flatten(), X.flatten()])
        new_arr = map_coordinates(in_arr, coords, order=1)
        new_arr = new_arr.reshape(size_new[0], size_new[1])
        return new_arr

    def _expand_border(self, img_arr: np.ndarray, npix: int = 25):
        """
        添加反射边框
        核心逻辑：
            创建一个比原图像大 2 * npix 的新图像 newimage。
            将原图像放在新图像的中心。
            使用反射填充边框区域：
            左、右、上、下边框分别通过镜像原图像的边缘来填充。
            四个角区域也通过镜像填充。
        :param img_arr: 输入数组，2D
        :param npix: 扩大的像素数
        :return: 按照镜像原理扩充后的二维ndarray
        """
        # Get the size of the input image
        sz = img_arr.shape
        # Create a new image with the border
        newimage = np.zeros((sz[0] + 2 * npix, sz[1] + 2 * npix), dtype=img_arr.dtype)
        # Place the original image in the center
        newimage[npix:npix + sz[0], npix:npix + sz[1]] = img_arr
        # Add reflective borders
        # Left border
        newimage[npix:npix + sz[0], :npix] = img_arr[:, npix - 1::-1]
        # Right border
        newimage[npix:npix + sz[0], npix + sz[1]:] = img_arr[:, sz[1] - 1:sz[1] - npix - 1:-1]
        # Top border
        newimage[:npix, npix:npix + sz[1]] = img_arr[npix - 1::-1, :]
        # Bottom border
        newimage[npix + sz[0]:, npix:npix + sz[1]] = img_arr[sz[0] - 1:sz[0] - npix - 1:-1, :]
        # Top-left corner
        newimage[:npix, :npix] = img_arr[npix - 1::-1, npix - 1::-1]
        # Bottom-right corner
        newimage[npix + sz[0]:, npix + sz[1]:] = img_arr[sz[0] - 1:sz[0] - npix - 1:-1, sz[1] - 1:sz[1] - npix - 1:-1]
        # Bottom-left corner
        newimage[npix + sz[0]:, npix - 1::-1] = img_arr[sz[0] - 1:sz[0] - npix - 1:-1, :npix]
        # Top-right corner
        newimage[npix - 1::-1, npix + sz[1]:] = img_arr[:npix, sz[1] - 1:sz[1] - npix - 1:-1]
        return newimage

    def _bicutest(self, data_arr, x_arr, y_arr):
        """
        矩阵 iA：使用 numpy 的 array 来定义矩阵 iA。
        梯度计算：使用 numpy.gradient 来计算梯度。
        循环结构：Python 的 for 循环从 0 开始，因此 kx 和 ky 的范围是 range(4)。
        数组索引：Python 的数组索引从 0 开始，因此 left、right、top、bot 的计算方式与 MATLAB 一致。
        矩阵乘法：使用 np.dot 进行矩阵乘法。
        注意事项：
            确保输入的 X, Y, Z, XI, YI 是 numpy 数组。
            np.gradient 的计算结果与 MATLAB 的 gradient 函数结果一致，但需要注意边界条件的处理。
        """
        std_arr = np.array([
            [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [-3, 3, 0, 0, -2, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [2, -2, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, -3, 3, 0, 0, -2, -1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 2, -2, 0, 0, 1, 1, 0, 0],
            [-3, 0, 3, 0, 0, 0, 0, 0, -2, 0, -1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, -3, 0, 3, 0, 0, 0, 0, 0, -2, 0, -1, 0],
            [9, -9, -9, 9, 6, 3, -6, -3, 6, -6, 3, -3, 4, 2, 2, 1],
            [-6, 6, 6, -6, -3, -3, 3, 3, -4, 4, -2, 2, -2, -2, -1, -1],
            [2, 0, -2, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 2, 0, -2, 0, 0, 0, 0, 0, 1, 0, 1, 0],
            [-6, 6, 6, -6, -4, -2, 4, 2, -3, 3, -3, 3, -2, -1, -2, -1],
            [4, -4, -4, 4, 2, 2, -2, -2, 2, -2, 2, -2, 1, 1, 1, 1]
        ])

        grad_y, grad_x = np.gradient(data_arr)  # 等同matlab：[dZx,dZy]=gradient(Z);
        grad_x_y, grad_x_y = np.gradient(grad_x)
        left_arr = np.floor(x_arr).astype(int).flatten()
        right_arr = np.ceil(x_arr).astype(int).flatten()
        top_arr = np.floor(y_arr).astype(int).flatten()
        bot_arr = np.ceil(y_arr).astype(int).flatten()
        v = np.array([
            data_arr[top_arr, left_arr], data_arr[top_arr, right_arr], data_arr[bot_arr, left_arr],
            data_arr[bot_arr, right_arr],
            grad_x[top_arr, left_arr], grad_x[top_arr, right_arr], grad_x[bot_arr, left_arr],
            grad_x[bot_arr, right_arr],
            grad_y[top_arr, left_arr], grad_y[top_arr, right_arr], grad_y[bot_arr, left_arr],
            grad_y[bot_arr, right_arr],
            grad_x_y[top_arr, left_arr], grad_x_y[top_arr, right_arr], grad_x_y[bot_arr, left_arr],
            grad_x_y[bot_arr, right_arr]
        ])
        alph = np.dot(std_arr, v)
        # XI_flat = XI.flatten()
        dx_arr = x_arr.flatten() - left_arr
        dy_arr = y_arr.flatten() - top_arr
        r_arr = []
        for kx, ky in [[0, 0], [1, 0], [2, 0], [3, 0], [0, 1], [1, 1], [2, 1], [3, 1], [0, 2], [1, 2], [2, 2], [3, 2],
                       [0, 3], [1, 3], [2, 3], [3, 3]]:
            t_arr = (dx_arr ** kx) * (dy_arr ** ky)
            r_arr.append(t_arr)
        r_arr = np.array(r_arr)

        v_arr = alph * r_arr
        v_arr = np.sum(v_arr, axis=0)
        v_arr = v_arr.reshape(x_arr.shape)
        return v_arr

    def _calc_moved_arr(self, arr1, arr2, feature_border=192, iterations=1024):
        """
        字段对齐2D版本
        :param arr1: 归一化的三个字段。
        :param arr2: 归一化的三个字段。
        :param feature_border: 特征参数量，192*192，默认为192，调整此参数可以提高效率，调整到128，提升2/3的效率；
            但是如果数量太少，相关的数据可能出现较大的形变导致失真，可根据自身的数据特征进行试验调整，选取最优参数
        :param iterations: 最大迭代次数。
        :return x_move_arr, y_move_arr: 返回x和y方向的位移场
        """
        new_arr1 = self._myim_resize(arr1, [feature_border, feature_border])
        new_arr2 = self._myim_resize(arr2, [feature_border, feature_border])
        loc_arr = np.ones((feature_border, feature_border))
        qtx, qty, qq, errl = self._calc_moved_arr_with_2d_arr(new_arr1, new_arr2, loc_arr, 1,
                                                              iterations)
        x_move_arr = self._myim_resize(qtx, arr1.shape) * arr1.shape[1] / feature_border
        y_move_arr = self._myim_resize(qty, arr1.shape) * arr1.shape[0] / feature_border

        return x_move_arr, y_move_arr

    def _calc_moved_arr_with_2d_arr(self, arr1, arr2, loc_arr, msk, iterations):
        """
        二维字段对齐（Field Alignment 2D）V2版本核心函数
        基于谱方法（频域求解）和迭代优化，计算位移场实现两个二维字段的空间对齐，
        核心逻辑：通过最小化两个字段的差异，迭代求解频域下的位移场（ux/uy），最终输出累计位移和对齐后的字段。

        :param arr1: np.ndarray (二维)，归一化的参考字段（待对齐的基准字段）
        :param arr2: np.ndarray (二维)，归一化的目标字段（需要对齐到arr1的字段）
        :param loc_arr: np.ndarray (二维)，与输入字段同尺寸的掩码数组，标记有效观测位置（>0为有效区域，0为无效/忽略区域）
        :param msk: np.ndarray (二维)，位移场约束掩码，用于限制位移场的有效计算区域（0为禁用位移，1为允许位移）
        :param iterations: int，最大迭代次数，迭代终止的核心条件之一
        :return:
            qtx: np.ndarray (二维)，x方向累计位移场（所有迭代的位移累加）
            qty: np.ndarray (二维)，y方向累计位移场（所有迭代的位移累加）
            qq: np.ndarray (二维)，对齐后的arr1字段（最终匹配到arr2的结果）
            errl: float，最后一次迭代的字段差异中位数，表征对齐误差
        """
        szx = arr1.shape
        nx = szx[0]  # 假设它是正方形
        pblmr = np.arange(nx)
        loc_arr[(arr1 == np.inf)] = 0
        loc_arr[(arr2 == np.inf)] = 0
        loc_arr[(arr1 == -999999)] = 0
        loc_arr[(arr2 == -999999)] = 0
        arr1[(arr1 == np.inf)] = 0
        arr2[(arr2 == np.inf)] = 0
        arr1[(arr1 == -999999)] = 0
        arr2[(arr2 == -999999)] = 0

        # Normalize Xb and Y -- not always necessary.
        mxb = np.min(arr1)
        dxb = np.max(arr1) - mxb
        arr1 = (arr1 - mxb) / dxb
        arr2 = (arr2 - mxb) / dxb
        # We will solve spectrally.
        l_scale = round((self.l_scale * nx + nx) / 2) * 2
        m, n = np.meshgrid(np.arange(-l_scale // 2, l_scale // 2), np.arange(-l_scale // 2, l_scale // 2))

        ux = np.zeros((nx, nx))
        uy = np.zeros((nx, nx))
        qtx = np.zeros((nx, nx))
        qty = np.zeros((nx, nx))
        qq = arr1 * dxb + mxb

        w1 = 1
        w2 = w1 / 3  # A "Newtonian Fluid."
        loop_times = 0
        err = []
        errl = np.inf
        errv = np.inf
        derrl = -np.inf

        while (loop_times < iterations) and (errl > 1e-4) and (errv > 1e-5) and (derrl < 1e+1):
            # Clamp the displacement so it does not go wild.
            ssx = np.minimum(ux, nx / 2)
            ssy = np.minimum(uy, nx / 2)
            # Yank problem region displacement, but make consistent with NCEP
            # implementation on Halo placement...to do 5/15/12 Sai
            ssx = msk * ssx[pblmr[:, None], pblmr]
            ssy = msk * ssy[pblmr[:, None], pblmr]
            aa, bb = np.meshgrid(np.arange(len(ssx)), np.arange(len(ssx)))
            # p - q, interpolate.
            qx = aa - ssx
            qy = bb - ssy
            qtx += ssx
            qty += ssy
            t1 = np.zeros(szx[:2])
            t2 = np.zeros(szx[:2])
            dqe = 0
            # 这里传入的都是二维数组，因此对应的szx[2],手动修改为1
            # for i in range(szx[2]):
            # XXb1 = Xb1[pblmr, :][:, pblmr]  # make sure interp does not tank at edge.
            bd = min(self.reflect_pad, arr1.shape[0])
            arr1 = self._expand_border(arr1, bd)
            # bdx, bdy = np.meshgrid(np.arange(1, arr1.shape[1] + 1), np.arange(1, arr1.shape[0] + 1))
            arr1 = self._bicutest(arr1, bd + qx, bd + qy)
            qq = arr1 * dxb + mxb

            # Calc forcing here
            dq = loc_arr * (arr1 - arr2)
            dq[0, :] = 0
            dq[-1, :] = 0
            dq[:, 0] = 0
            dq[:, -1] = 0
            dXby, dXbx = np.gradient(arr1)
            t1 -= dXbx * dq
            t2 -= dXby * dq
            dqe = np.median(np.append(dqe, np.abs(dq[loc_arr > 0])), axis=0)

            # String along the residual (forcing) here.
            err.append(dqe)

            # Solve system at current iteration. Spectral solution.
            # Mode = even, 2 or 4 is all that is needed in most problems.
            # Note: Tikhonov is no longer necessary, superseeded by Yang and
            # Ravela 2009, SCA method.
            # 在当前迭代中求解系统。光谱解决方案。在大多数问题中，只需要模式=偶数、2或4。
            # 注：Tikhonov不再是必需的，取而代之的是Yang和Ravela 2009的SCA方法。
            # Moving over to Fourier domain
            fFx = fftshift(fft2(t1, s=(l_scale, l_scale)))
            fFy = fftshift(fft2(t2, s=(l_scale, l_scale)))
            # Avoid singularity
            fFx[l_scale // 2, l_scale // 2] = 0
            fFy[l_scale // 2, l_scale // 2] = 0

            # Apply deformation filters
            fac1 = w2 * n ** 2 + w1 * (n ** self.power_model + m ** self.power_model)
            fac2 = w2 * m * n
            fac4 = w2 * m ** 2 + w1 * (m ** self.power_model + n ** self.power_model)
            xpy = fac1 - fac2
            ypx = fac4 - fac2
            zz = (fac1 * fac4 - fac2 ** 2) * self.weight_value / l_scale
            fux = (-fFx * xpy + fac2 * fFy) / zz
            # ux = np.real(ifft2(ifftshift(fux)))
            ux0 = np.fft.ifftshift(fux)
            # 将 nan + nanj 替换为 0 + 0j
            ux0[np.isnan(ux0.real) & np.isnan(ux0.imag)] = 0 + 0j
            ux1 = np.fft.ifft2(ux0)
            ux = np.real(ux1)
            fuy = (fFx * fac2 - ypx * fFy) / zz
            # uy = np.real(ifft2(ifftshift(fuy)))
            uy0 = np.fft.ifftshift(fuy)
            uy0[np.isnan(uy0.real) & np.isnan(uy0.imag)] = 0 + 0j
            uy1 = np.fft.ifft2(uy0)
            uy = np.real(uy1)
            # We expect convergence on ux, instantaneous deformation -> to zero. This
            # of course is an assumption and only valid for appropriately formulated
            # local optimization. Nevertheless, we'll track it and use it as a
            # criterion.
            # 我们期望在ux上收敛，瞬时变形->为零。这当然是一个假设，仅适用于适当制定的局部优化。尽管如此，我们仍将跟踪它并将其用作标准。
            errv = np.max(np.abs(ux)) + np.max(np.abs(uy))
            if loop_times > 2:
                errl = err[-1]
                derrl = errl - err[-2]
            loop_times += 1
            # print(f"iter:{iter}, errl:{errl}, errv:{errv}, derrl:{derrl}")
        return qtx, qty, qq, errl

    def _advect(self, input_arr, x_move_arr, y_move_arr):
        """
        对图像进行位移平流处理
        :param input_arr: 输入图像 (2D numpy 数组)
        :param x_move_arr: x 方向的位移场 (2D numpy 数组)
        :param y_move_arr: y 方向的位移场 (2D numpy 数组)
        :return out_arr: 平流处理后的图像 (2D numpy 数组)
        """
        # 如果没有位移场，返回输入图像
        if x_move_arr.size == 0:
            return input_arr
        # 将 NaN 值替换为 0
        x_move_arr = np.nan_to_num(x_move_arr)
        y_move_arr = np.nan_to_num(y_move_arr)
        # 对输入图像进行边界填充
        pad = self.reflect_pad
        ex_arr = self._expand_border(input_arr, pad)
        # 创建网格
        xx, yy = np.meshgrid(np.arange(input_arr.shape[1]), np.arange(input_arr.shape[0]))
        # 计算插值坐标
        new_xx = pad + xx - x_move_arr
        new_yy = pad + yy - y_move_arr
        # 使用双线性插值计算平流后的图像
        x = np.arange(ex_arr.shape[1])
        y = np.arange(ex_arr.shape[0])
        interp_func = RegularGridInterpolator((y, x), ex_arr, method='linear', bounds_error=False, fill_value=np.nan)
        out_arr = interp_func((new_yy, new_xx))
        nan_mask = np.isnan(out_arr)
        out_arr[nan_mask] = input_arr[nan_mask]
        return out_arr
