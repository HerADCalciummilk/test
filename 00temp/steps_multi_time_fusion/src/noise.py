"""Non-parametric filter training and AR(2) noise generation for STEPS."""

from __future__ import annotations

from pathlib import Path

import numpy as np


class AR2NoiseGenerator:
    """Generate cascade-level AR(2) stochastic noise fields."""

    def __init__(self, filter_path: str | Path, phi1: float, phi2: float, n_levels: int):
        self.filters = np.load(filter_path)
        self.m_size, self.n_size = self.filters.shape[1:]
        self.phi1 = phi1
        self.phi2 = phi2
        self.n_levels = n_levels
        self.state_prev = np.zeros((n_levels, self.m_size, self.n_size))
        self.state = np.zeros((n_levels, self.m_size, self.n_size))

    def generate_one_step(self) -> np.ndarray:
        """Generate one AR(2) noise step with shape ``(n_levels, y, x)``."""
        noise_levels = []
        for level in range(self.n_levels):
            white = np.random.normal(0, 1, (self.m_size, self.n_size))
            fft_white = np.fft.fft2(white)
            fft_noise = fft_white * self.filters[level]
            noise = np.fft.ifft2(fft_noise).real
            noise = np.clip(noise, -15, None)
            new_state = self.phi1 * self.state[level] + self.phi2 * self.state_prev[level] + noise
            self.state_prev[level] = self.state[level].copy()
            self.state[level] = new_state.copy()
            noise_levels.append(new_state)
        return np.stack(noise_levels, axis=0)


def to_db(precip: np.ndarray) -> np.ndarray:
    """Convert precipitation to dB units with a 0.1 mm/h floor."""
    precip = np.where(precip < 0.1, 0.1, precip)
    db_values = 10 * np.log10(precip)
    db_values[~np.isfinite(db_values)] = -15.0
    return db_values


def decompose_cascade(field_db: np.ndarray, n_levels: int) -> list[np.ndarray]:
    """Decompose a dB precipitation field into simple FFT cascade levels."""
    cascades = []
    fft_field = np.fft.fft2(field_db)
    m_size, n_size = field_db.shape
    for level in range(n_levels):
        sigma = 2 ** (level + 1)
        fy, fx = np.ogrid[-m_size // 2 : m_size // 2, -n_size // 2 : n_size // 2]
        freq2 = (fx**2 + fy**2) / (sigma**2)
        kernel = np.exp(-freq2 / 2)
        cascades.append(np.fft.ifft2(fft_field * kernel).real)
    return cascades


def train_noise_filter(
    fields_db_list: list[np.ndarray],
    *,
    output_dir: str | Path,
    issue_time: str,
    n_levels: int,
) -> Path | None:
    """Train non-parametric filters from historical dB precipitation fields."""
    if not fields_db_list:
        print("没有有效历史数据，无法训练滤波器。")
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    total_frames = len(fields_db_list)
    m_size, n_size = fields_db_list[0].shape
    psd_sum = [np.zeros((m_size, n_size)) for _ in range(n_levels)]

    print(f"共收到 {total_frames} 帧历史数据，开始计算非参数滤波器。")
    for field_db in fields_db_list:
        for level, cascade in enumerate(decompose_cascade(field_db, n_levels)):
            fft_cascade = np.fft.fft2(cascade)
            psd_sum[level] += np.fft.fftshift(np.abs(fft_cascade) ** 2 / (m_size * n_size))

    filter_array = np.zeros((n_levels, m_size, n_size))
    y_grid, x_grid = np.ogrid[-m_size // 2 : m_size // 2, -n_size // 2 : n_size // 2]
    freq = np.sqrt(x_grid**2 + y_grid**2)
    freq[freq == 0] = 1e-8

    for level in range(n_levels):
        mean_psd = np.fft.ifftshift(psd_sum[level] / total_frames)
        filter_array[level] = np.sqrt(mean_psd) / (freq ** (-1.0) + 1e-8)

    filter_path = output_dir / f"nonparam_filters_{issue_time}.npy"
    np.save(filter_path, filter_array)
    print(f"非参数滤波器已保存：{filter_path}，形状 {filter_array.shape}")
    return filter_path


def generate_ar2_noise(
    *,
    filter_path: str | Path,
    output_dir: str | Path,
    issue_time: str,
    phi1: float,
    phi2: float,
    n_levels: int,
    n_ens_members: int,
    timesteps: int,
) -> Path:
    """Generate AR(2) noise members using a trained filter file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generator = AR2NoiseGenerator(filter_path, phi1, phi2, n_levels)
    noise_array = np.zeros((n_ens_members, timesteps, n_levels, generator.m_size, generator.n_size))

    for member in range(n_ens_members):
        print(f"生成噪声成员 {member + 1}/{n_ens_members}")
        generator.state_prev = np.zeros((n_levels, generator.m_size, generator.n_size))
        generator.state = np.zeros((n_levels, generator.m_size, generator.n_size))
        for step in range(timesteps):
            noise_array[member, step] = generator.generate_one_step()

    noise_path = output_dir / f"ar_noise_{issue_time}.npy"
    np.save(noise_path, noise_array)
    print(f"AR(2) 噪声场已保存：{noise_path}，形状 {noise_array.shape}")
    return noise_path
