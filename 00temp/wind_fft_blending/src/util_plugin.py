# -*- coding: utf-8 -*-
"""FFT 融合的纯计算步骤。公式与原先插件方法一致，只改成函数。"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import map_coordinates


def clean_arr(a_arr: np.ndarray, source_arr: np.ndarray) -> np.ndarray:
    """把平流结果里的无穷大换回源场。"""
    inf_mask = np.isinf(a_arr)
    a_arr[inf_mask] = source_arr[inf_mask]
    return a_arr


def myim_resize(in_arr: np.ndarray, size_new):
    """双线性插值到 size_new。"""
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


def expand_border(img_arr: np.ndarray, npix: int = 25):
    """按反射方式扩边，避免频域和平流碰到边界。"""
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


def bicutest(data_arr, x_arr, y_arr):
    """双三次插值取样。系数矩阵与原先一致。"""
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


def advect(input_arr, x_move_arr, y_move_arr, reflect_pad):
    """按位移场做反射边界上的线性平流。"""
    # 如果没有位移场，返回输入图像
    if x_move_arr.size == 0:
        return input_arr
    # 将 NaN 值替换为 0
    x_move_arr = np.nan_to_num(x_move_arr)
    y_move_arr = np.nan_to_num(y_move_arr)
    # 对输入图像进行边界填充
    pad = reflect_pad
    ex_arr = expand_border(input_arr, pad)
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
