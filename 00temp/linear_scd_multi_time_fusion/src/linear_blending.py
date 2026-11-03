# linear_blending.py (完整更新版：支持 weights_now_list + 保留原有注释)

import numpy as np
import scipy.ndimage as ndimage
from typing import Dict, Any, List
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def compute_saliency_map(field: np.ndarray, sigma_gauss: float = 1.0) -> np.ndarray:
    """
    计算单帧降水场的显著性图（saliency map），用于 salient blending。

    Args:
        field (np.ndarray): 单帧降水场，shape 为 (height, width)，数据类型通常为 float
        sigma_gauss (float, optional): 高斯滤波标准差，控制梯度平滑程度，默认 1.0

    Returns:
        np.ndarray: 显著性图，shape 与输入相同，值越大表示降水特征越显著
    """
    grad_x = ndimage.sobel(field, axis=1)  # x方向梯度（水平）
    grad_y = ndimage.sobel(field, axis=0)  # y方向梯度（垂直）
    grad = np.hypot(grad_x, grad_y)        # 梯度幅度
    sal = ndimage.gaussian_filter(grad, sigma=sigma_gauss)  # 高斯平滑
    return sal

def linear_blending_forecast(
    precomputed_nowcast: np.ndarray,
    precip_model: np.ndarray,
    saliency: bool = False,
    start_frame: int = 1,          # 1-based
    end_frame: int = 29,           # 1-based
    start_weight_now: float = 1.0,
    end_weight_now: float = 0.0,
    weights_now_list: List[float] = None,
    saliency_floor: float = 0.05,
    saliency_strength: float = 0.35,
) -> np.ndarray:
    """
    对两组降水预报序列进行线性或显著性加权融合。

    Args:
        precomputed_nowcast (np.ndarray): 当前预报（通常是高分辨率 nowcast），shape 为 (timesteps, height, width)
        precip_model (np.ndarray): 数值模式预报（通常是低分辨率），shape 为 (timesteps, height, width)，若长度不足会自动补0
        saliency (bool, optional): 是否使用显著性加权融合，默认为 False（普通线性融合）
        start_frame (int, optional): 权重开始线性变化的帧号（1-based），默认为 1
        end_frame (int, optional): 权重结束线性变化的帧号（1-based），默认为 19
        start_weight_now (float, optional): 当前预报在 start_frame 时的权重，默认为 1.0
        end_weight_now (float, optional): 当前预报在 end_frame 及之后时的权重，默认为 0.0
        weights_now_list (List[float], optional): 逐帧当前预报权重列表，长度必须等于 timesteps，若提供则优先使用此参数

    Returns:
        np.ndarray: 融合后的降水场序列，shape 与 precomputed_nowcast 相同
    """
    if precomputed_nowcast is None:
        raise ValueError("Precomputed nowcast is required.")

    # 自动推断 timesteps
    timesteps = precomputed_nowcast.shape[0]

    # 确保 precip_model 长度一致（若不一致，优先以 nowcast 长度为准）
    if precip_model.shape[0] != timesteps:
        logging.warning(f"precip_model timesteps {precip_model.shape[0]} != nowcast {timesteps}, adjusting")
        if precip_model.shape[0] > timesteps:
            precip_model = precip_model[:timesteps]
        else:
            pad = np.zeros((timesteps - precip_model.shape[0],) + precip_model.shape[1:], 
                          dtype=precip_model.dtype)
            precip_model = np.concatenate((precip_model, pad), axis=0)

    precip_nowcast = precomputed_nowcast

    blended = np.zeros_like(precip_nowcast, dtype=np.float32)

    # 新增：判断是否使用逐帧权重
    use_per_frame_weight = weights_now_list is not None
    if use_per_frame_weight:
        if len(weights_now_list) != timesteps:
            raise ValueError(f"weights_now_list 长度 {len(weights_now_list)} 与 timesteps {timesteps} 不匹配")

    for t in range(timesteps):
        frame = t + 1  # 转为 1-based 帧号

        # 权重计算
        if use_per_frame_weight:
            weight_now = weights_now_list[t]
        else:
            # 基础线性权重计算（原有逻辑）
            if frame < start_frame:
                weight_now = start_weight_now
            elif frame >= end_frame:
                weight_now = end_weight_now
            else:
                denom = end_frame - start_frame
                fraction = (frame - start_frame) / denom if denom > 0 else 0.0
                weight_now = start_weight_now + fraction * (end_weight_now - start_weight_now)

        weight_model = 1.0 - weight_now

        if saliency:
            linear_base = weight_now * precip_nowcast[t] + weight_model * precip_model[t]
            sal_now = compute_saliency_map(precip_nowcast[t])
            sal_model = compute_saliency_map(precip_model[t])
            
            sal_now_max = np.max(sal_now)
            sal_model_max = np.max(sal_model)
            sal_now = sal_now / sal_now_max if sal_now_max > 0 else sal_now
            sal_model = sal_model / sal_model_max if sal_model_max > 0 else sal_model

            sal_now = sal_now + np.float32(saliency_floor)
            sal_model = sal_model + np.float32(saliency_floor)
            
            sal_weight_now = weight_now * sal_now
            sal_weight_model = weight_model * sal_model
            denom_sal = sal_weight_now + sal_weight_model
            low_saliency = denom_sal <= 1e-12

            w_now = np.empty_like(denom_sal, dtype=np.float32)
            w_model = np.empty_like(denom_sal, dtype=np.float32)
            w_now[~low_saliency] = sal_weight_now[~low_saliency] / denom_sal[~low_saliency]
            w_model[~low_saliency] = sal_weight_model[~low_saliency] / denom_sal[~low_saliency]
            w_now[low_saliency] = weight_now
            w_model[low_saliency] = weight_model

            salient_blended = w_now * precip_nowcast[t] + w_model * precip_model[t]
            strength = np.float32(np.clip(saliency_strength, 0.0, 1.0))
            blended[t] = linear_base * (np.float32(1.0) - strength) + salient_blended * strength
        else:
            blended[t] = weight_now * precip_nowcast[t] + weight_model * precip_model[t]

    return blended
