# -*- coding: utf-8 -*-
"""
阵风系数计算与阵风预报订正（``gust_factor``）。

算法概要
--------
1. **系数计算**：用历史站点「10 m 平均风速预报 + 阵风观测」，按预报时效估计
   阵风系数 ``param``，再对分位数做一元线性匹配得到 ``a, b``。
2. **实时订正**：由 U/V 得平均风速，再
   ``gust = max(ws, clamp(ws * param * a + b))``。

入口
----
- 模块：``from gust_factor import process``
- CLI：``python -m cli``
- 直跑：``python src/gust_factor.py``

数据读写优先使用 ``meteva_base``（格点 NC 读/写）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
import meteva_base as meb


def _bootstrap_paths() -> None:
    """保证包根与 ``src`` 在 ``sys.path`` 最前，便于 ``from utils...`` / 本模块直跑。"""
    _src = Path(__file__).resolve().parent
    _root = _src.parent
    for p in (str(_root), str(_src)):
        while p in sys.path:
            sys.path.remove(p)
    for p in reversed((str(_root), str(_src))):
        sys.path.insert(0, p)


_bootstrap_paths()

from utils.util_env import get_repo_root, get_resolved_paths, get_run_params  # noqa: E402


# ---------------------------------------------------------------------------
# 算法核：阵风系数计算
# ---------------------------------------------------------------------------


class GustFactorCalculatorPlugin(object):
    """根据历史站点预报/观测统计阵风系数与分位数匹配参数。

    对每个预报时效 ``h``：

    1. 最小二乘（过原点）估计 ``param``，使 ``obs ≈ param * fcst``：
       ``param = Σ(obs·fcst) / Σ(fcst²)``。
    2. 用 ``fcst * param`` 与 ``obs`` 在固定百分位上取值，再拟合
       ``y = a·x + b``，得到分位数匹配斜截距。

    结果形如 ``{"24": {"param": ..., "a": ..., "b": ...}, ...}``。
    """

    def __init__(self):
        # 分位数匹配所用百分位序列（%）；覆盖中高分位以约束强风端
        self.per_list = [
            10, 15, 20, 25, 30, 35, 40, 45, 50,
            55, 60, 65, 70, 75, 80, 85, 90, 95, 99,
        ]
        self.gust_factor: Dict[str, Dict[str, float]] = {}

    def __call__(
        self,
        station_data_set: pd.DataFrame,
        fore_hours: Sequence[int] = (24, 48, 72),
        save_path: str = "",
    ) -> Dict[str, Dict[str, float]]:
        """可调用接口，等价于 :meth:`process`。"""
        return self.process(station_data_set, fore_hours, save_path)

    def process(
        self,
        station_data_set: pd.DataFrame,
        fore_hours: Sequence[int] = (24, 48, 72),
        save_path: str = "",
    ) -> Dict[str, Dict[str, float]]:
        """计算各时效阵风系数并可选写入 JSON。

        Parameters
        ----------
        station_data_set :
            须含列 ``level, time, dtime, id, lon, lat, fcst_wind, obs_gust``；
            有效样本量建议 ≥ 100。
        fore_hours :
            需要统计的预报时效（小时）。
        save_path :
            非空则 ``json.dump`` 写出系数文件。

        Returns
        -------
        dict
            键为时效字符串，值为 ``param/a/b``。
        """
        required_cols = [
            "level", "time", "dtime", "id", "lon", "lat", "fcst_wind", "obs_gust",
        ]
        existing_cols = list(station_data_set.columns)
        for col in required_cols:
            if col not in existing_cols:
                raise Exception("站点数据缺少必要的列: %s" % col)

        # 去掉关键字段缺失行，避免污染回归
        before_count = station_data_set.shape[0]
        station_data_set = station_data_set.dropna(
            subset=["dtime", "fcst_wind", "obs_gust"]
        ).copy()
        after_count = station_data_set.shape[0]
        if before_count > after_count:
            print("数据中存在nan值，已去除%d条数据" % (before_count - after_count))
        if after_count < 100:
            raise Exception("数据量不足100条，无法计算阵风系数")

        station_data_set = station_data_set.astype(
            {"dtime": int, "fcst_wind": float, "obs_gust": float}
        )
        for eve_hour in fore_hours:
            t_pd = station_data_set[station_data_set["dtime"] == int(eve_hour)]
            self._calc_some_hour_param(t_pd, int(eve_hour))

        self._save_gust_factor(save_path)
        return self.gust_factor

    def _calc_some_hour_param(self, data_pd: pd.DataFrame, fore_hour: int) -> bool:
        """对单一时效估计 ``param`` 与分位数匹配 ``a,b``。"""
        print("**********start calculate gust factor in fcst hour[%d]" % fore_hour)
        obs_arr = np.asarray(data_pd["obs_gust"], dtype=float)
        fore_arr = np.asarray(data_pd["fcst_wind"], dtype=float)

        # 过原点最小二乘：param = Σ(obs·fcst) / Σ(fcst²)
        t_par = float(np.sum(obs_arr * fore_arr) / np.sum(fore_arr * fore_arr))

        # 分位数匹配：线性订正后的预报分位 ↔ 观测分位
        new_arr = fore_arr * t_par
        new_per_arr = self._calc_percent_value(new_arr)
        obs_per_arr = self._calc_percent_value(obs_arr)
        a, b = self._least_squares_method(new_per_arr, obs_per_arr)

        par_dic = {"param": t_par, "a": float(a), "b": float(b)}
        self.gust_factor[str(fore_hour)] = par_dic
        print("per list: %s" % self.per_list)
        print("fore per: %s" % list(np.round(new_per_arr, 2)))
        print("obs per: %s" % list(np.round(obs_per_arr, 2)))
        print("gust factor for [%dh] is: %s" % (fore_hour, par_dic))
        return True

    def _calc_percent_value(self, data_arr) -> List[float]:
        """按 ``self.per_list`` 计算百分位值（自动忽略 NaN）。"""
        data_arr = np.asarray(data_arr, dtype=float)
        filtered_arr = data_arr[~np.isnan(data_arr)]
        return [float(np.percentile(filtered_arr, p_v)) for p_v in self.per_list]

    def _least_squares_method(self, x, y) -> Tuple[float, float]:
        """一元线性最小二乘 ``y = a·x + b``。"""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        mean_x = np.mean(x)
        mean_y = np.mean(y)
        denominator = np.sum((x - mean_x) ** 2)
        # 退化情形：分位几乎常数，退回单位斜率
        if denominator == 0:
            return 1.0, float(mean_y - mean_x)
        a = float(np.sum((x - mean_x) * (y - mean_y)) / denominator)
        b = float(mean_y - a * mean_x)
        return a, b

    def _save_gust_factor(self, save_path: str) -> bool:
        """写出 JSON；``save_path`` 为空则跳过。"""
        try:
            if not save_path:
                return True
            parent = os.path.dirname(os.path.abspath(save_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as fso:
                json.dump(self.gust_factor, fso, indent=4, ensure_ascii=False)
            print("阵风系数保存完成：%s" % save_path)
            return True
        except Exception as e:
            print("阵风系数保存失败：%s" % e)
            return False


# ---------------------------------------------------------------------------
# 算法核：用阵风系数订正格点预报
# ---------------------------------------------------------------------------


class GustCorrectWithFactorPlugin(object):
    """读取阵风系数 JSON，由 10 m U/V 生成订正后的阵风格点场。

    步骤：``ws = sqrt(u²+v²)`` → ``g0 = ws * param`` →
    ``g1 = a·g0 + b`` → 负值/过大回退 ``g0`` → 且不低于平均风速 ``ws``。
    """

    def __init__(self):
        self.gust_factor: Dict[str, Dict[str, float]] = {}

    def __call__(self, u_da, v_da, fore_hour: int, factor_path: str):
        """可调用接口，等价于 :meth:`process`。"""
        return self.process(u_da, v_da, fore_hour, factor_path)

    def process(self, u_da, v_da, fore_hour: int, factor_path: str):
        """对单时效格点 U/V 做阵风订正。

        Parameters
        ----------
        u_da, v_da :
            meteva_base 格点场，维序 ``member, level, time, dtime, lat, lon``；
            前四维长度通常为 1。
        fore_hour :
            预报时效（小时），须在系数文件中存在。
        factor_path :
            阵风系数 JSON 路径。

        Returns
        -------
        xarray.DataArray
            订正后阵风格点（meteva_base ``grid_data``）。
        """
        self._load_gust_factor(factor_path)

        # 取水平二维切片（与示范数据 member/level/time/dtime=1 一致）
        u_arr = np.asarray(u_da.values)[0, 0, 0, 0]
        v_arr = np.asarray(v_da.values)[0, 0, 0, 0]
        s_arr = np.sqrt(u_arr ** 2 + v_arr ** 2)

        main_grd = meb.get_grid_of_data(u_da)
        param_dic = self.gust_factor.get(str(fore_hour), None)
        if param_dic is None:
            raise Exception("预报时效[%s]的阵风系数不存在" % fore_hour)

        gust_arr = s_arr * float(param_dic["param"])
        new_g_arr = gust_arr * float(param_dic["a"]) + float(param_dic["b"])
        # 物理约束：负值或异常大值回退到未匹配的 gust_arr
        new_g_arr = np.where(new_g_arr < 0, gust_arr, new_g_arr)
        new_g_arr = np.where(new_g_arr > 100, gust_arr, new_g_arr)
        # 阵风不应低于同时次平均风速
        min_mask = new_g_arr < s_arr
        new_g_arr = new_g_arr.copy()
        new_g_arr[min_mask] = s_arr[min_mask]

        n_grd = meb.grid(main_grd.glon, main_grd.glat)
        return meb.grid_data(n_grd, new_g_arr)

    def _load_gust_factor(self, json_path: str) -> bool:
        """从 JSON 加载 ``{时效: {param,a,b}}``。"""
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as fso:
                self.gust_factor = json.load(fso)
        else:
            raise Exception("阵风系数文件不存在：%s" % json_path)
        return True


# ---------------------------------------------------------------------------
# I/O 与辅助
# ---------------------------------------------------------------------------


def load_station_csv_dir(csv_dir: str) -> pd.DataFrame:
    """合并目录下全部 CSV 为训练用站点表。"""
    if not csv_dir or not os.path.isdir(csv_dir):
        raise FileNotFoundError("站点 CSV 目录不存在: %s" % csv_dir)
    frames = []
    for name in sorted(os.listdir(csv_dir)):
        if not name.lower().endswith(".csv"):
            continue
        frames.append(pd.read_csv(os.path.join(csv_dir, name)))
    if not frames:
        raise FileNotFoundError("目录中无 CSV: %s" % csv_dir)
    return pd.concat(frames, axis=0, ignore_index=True)


def read_grid_nc(path: str):
    """用 ``meteva_base`` 读取格点 NC。"""
    if not path or not os.path.exists(path):
        raise FileNotFoundError("格点文件不存在: %s" % path)
    return meb.read_griddata_from_nc(path)


def write_grid_nc(grd, path: str) -> None:
    """用 ``meteva_base`` 写出格点 NC。"""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    meb.write_griddata_to_nc(grd, path, creat_dir=True)


def make_compare_png(ws_arr, gust_arr, png_path: str, show_png) -> bool:
    """平均风速与订正阵风并排伪彩图（可选依赖 matplotlib）。"""
    try:
        import matplotlib.pyplot as plt
        from matplotlib import colors
    except ImportError:
        print("未安装 matplotlib，跳过出图: %s" % png_path)
        return False

    colev = [
        "#99DBEA", "#52A5D1", "#3753AD", "#80C505", "#52C10D",
        "#35972A", "#FAE33B", "#EAB81E", "#F78C2C", "#E2331F",
        "#992B27", "#471713", "#BC5CC2", "#975CC0",
    ]
    cmap = colors.ListedColormap(colev)
    fig = plt.figure(figsize=(12, 7))
    plt.subplots_adjust(wspace=0.05, hspace=0.05)
    ax1 = fig.add_subplot(1, 2, 1)
    im = ax1.imshow(ws_arr, cmap=cmap, vmin=0, vmax=50, interpolation="nearest")
    ax1.set_axis_off()
    ax1.set_title("WS10")
    ax2 = fig.add_subplot(1, 2, 2)
    ax2.imshow(gust_arr, cmap=cmap, vmin=0, vmax=50, interpolation="nearest")
    ax2.set_axis_off()
    ax2.set_title("Gust")
    cbar_ax = fig.add_axes([0.92, 0.15, 0.02, 0.7])
    fig.colorbar(im, cax=cbar_ax)
    parent = os.path.dirname(os.path.abspath(png_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    fig.savefig(png_path, dpi=100, bbox_inches="tight")
    if show_png:
        plt.show()
    plt.close(fig)
    print("对比图片已保存至：%s" % png_path)
    return True


def _parse_fore_hours(value) -> Tuple[int, ...]:
    if value is None:
        return (24, 48, 72)
    if isinstance(value, (list, tuple)):
        return tuple(int(x) for x in value)
    s = str(value).strip()
    if not s:
        return (24, 48, 72)
    return tuple(int(x.strip()) for x in s.split(",") if x.strip())


# ---------------------------------------------------------------------------
# 可调度入口（无独立 runner）
# ---------------------------------------------------------------------------


def process(
    mode: Optional[str] = None,
    station_csv_dir: Optional[str] = None,
    fore_hours: Optional[Union[Sequence[int], str]] = None,
    factor_path: Optional[str] = None,
    u_path: Optional[str] = None,
    v_path: Optional[str] = None,
    fore_hour: Optional[int] = None,
    output_path: Optional[str] = None,
    make_png: Optional[bool] = None,
    show_png: Optional[bool] = None,
    ws_path: Optional[str] = None,
    png_path: Optional[str] = None,
) -> Dict:
    """阵风系数 / 订正可调度入口。

    未传参数从 ``resource/gust_factor.ini`` 读取。

    Parameters
    ----------
    mode :
        ``calc`` / ``correct`` / ``all``。
    station_csv_dir :
        历史站点 CSV 目录（``calc`` / ``all``）。
    fore_hours :
        系数统计时效列表。
    factor_path :
        系数 JSON 路径（写出或读入）。
    u_path, v_path :
        10 m U/V 格点 NC（``correct`` / ``all``）。
    fore_hour :
        订正时效。
    output_path :
        订正阵风 NC 输出路径。
    make_png / ws_path / png_path :
        可选对比图。

    Returns
    -------
    dict
        含 ``mode``、``gust_factor``（若计算）、``output_path``（若订正）等。
    """
    paths = get_resolved_paths()
    params = get_run_params()

    mode = (mode or params["mode"] or "all").strip().lower()
    station_csv_dir = station_csv_dir or paths["station_csv_dir"]
    factor_path = factor_path or paths["factor_path"]
    u_path = u_path or paths["u_path"]
    v_path = v_path or paths["v_path"]
    output_path = output_path or paths["output_path"]
    ws_path = ws_path if ws_path is not None else paths.get("ws_path", "")
    png_path = png_path or paths["png_path"]
    fore_hours_t = _parse_fore_hours(
        fore_hours if fore_hours is not None else params["fore_hours"]
    )
    fore_hour = int(params["fore_hour"] if fore_hour is None else fore_hour)
    if make_png is None:
        make_png = bool(params["make_png"])
    if show_png is None:
        show_png = bool(params["show_png"])

    result: Dict = {"mode": mode, "repo_root": get_repo_root()}

    if mode in ("calc", "all"):
        print("#" * 60)
        print("start calculate gust factor")
        print("#" * 60)
        train_pd = load_station_csv_dir(station_csv_dir)
        g_factor = GustFactorCalculatorPlugin().process(
            train_pd, fore_hours=fore_hours_t, save_path=factor_path
        )
        result["gust_factor"] = g_factor
        result["factor_path"] = factor_path

    if mode in ("correct", "all"):
        print("#" * 60)
        print("start use gust factor to correct gust forecast")
        print("#" * 60)
        u_da = read_grid_nc(u_path)
        v_da = read_grid_nc(v_path)
        g_da = GustCorrectWithFactorPlugin().process(
            u_da, v_da, fore_hour, factor_path
        )
        write_grid_nc(g_da, output_path)
        print("阵风预报结果已保存至：%s" % output_path)
        result["output_path"] = output_path
        result["fore_hour"] = fore_hour

        if make_png and ws_path:
            ws_da = read_grid_nc(ws_path)
            ws_arr = np.asarray(ws_da.values)[0, 0, 0, 0]
            gust_arr = np.asarray(g_da.values)[0, 0, 0, 0]
            make_compare_png(ws_arr, gust_arr, png_path, show_png)
            result["png_path"] = png_path

    if mode not in ("calc", "correct", "all"):
        raise ValueError("未知 mode=%r，期望 calc/correct/all" % mode)

    return result


if __name__ == "__main__":
    process()
