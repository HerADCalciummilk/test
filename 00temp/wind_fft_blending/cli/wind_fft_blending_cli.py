# -*- coding: utf-8 -*-
"""多风场 FFT 融合。

``process`` 只排任务。一个任务在 ``_process``：读入 → ``FFTMergePlugin.process`` → 写出。
``pro_count>1`` 时用 ``SimpleParallelTool``，否则串行。显式 ``is_multi=False`` 强制串行。

由 ``python -m wind_fft_blending`` 或 ``python -m utils.nimm_cli wind_fft_blending`` 启动。
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from datetime import datetime
from typing import List, Optional, Sequence, Union

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _p in (_SRC_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.merge_params import merge_params
from utils.multipro_plugin import SimpleParallelTool
from utils.util_env import PRESET


def _pkg_path(path: str) -> str:
    expanded = os.path.expanduser(str(path))
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(_ROOT_DIR, expanded))


def _as_str_list(value: Union[str, os.PathLike, Sequence]) -> List[str]:
    if isinstance(value, (str, os.PathLike)):
        text = os.fspath(value)
        if "," in text:
            return [_pkg_path(item.strip()) for item in text.split(",") if item.strip()]
        return [_pkg_path(text)]
    return [_pkg_path(os.fspath(item)) for item in value]


def _netcdf_encoding(da):
    name = da.name if da.name else "data0"
    return {name: {"dtype": "int32", "scale_factor": 0.001, "_FillValue": -9999, "zlib": True}}


def _del_dir_or_file(src_path):
    try:
        if not os.path.exists(src_path):
            return True
        if os.path.isdir(src_path):
            shutil.rmtree(src_path, ignore_errors=True)
        else:
            os.remove(src_path)
    except Exception:
        pass


def _prefix_list(value) -> List[str]:
    if isinstance(value, (str, os.PathLike)):
        text = os.fspath(value)
        if "," in text:
            return [item.strip() for item in text.split(",") if item.strip()]
        return [text]
    return [os.fspath(item) for item in value]


def _normalize_cases(main_uv_path, ass_uv_path, output_dir, output_prefix):
    """将入口参数规范为任务列表。"""
    mains = _as_str_list(main_uv_path)
    prefixes = _prefix_list(output_prefix)
    output_dir = _pkg_path(output_dir)

    if len(mains) == 1:
        if len(prefixes) != 1:
            raise ValueError("单主场时 output_prefix 只能有一个")
        if isinstance(ass_uv_path, (str, os.PathLike)):
            text = os.fspath(ass_uv_path)
            ass = [_pkg_path(item.strip()) for item in text.split(",") if item.strip()] if "," in text else [_pkg_path(text)]
        else:
            ass = [_pkg_path(os.fspath(item)) for item in ass_uv_path]
        if not ass:
            raise ValueError("ass_uv_path 不能为空")
        return [{
            "main_uv_path": mains[0],
            "ass_uv_path": ass,
            "output_dir": output_dir,
            "output_prefix": prefixes[0],
        }]

    if len(prefixes) != len(mains):
        raise ValueError("多主场时 output_prefix 数量须与 main_uv_path 一致")
    if isinstance(ass_uv_path, (str, os.PathLike)):
        raise ValueError("多主场时 ass_uv_path 须为与主场等长的列表")
    ass_list = list(ass_uv_path)
    if len(ass_list) != len(mains):
        raise ValueError("多主场时 ass_uv_path 数量须与 main_uv_path 一致")

    cases = []
    for main_p, ass_p, prefix in zip(mains, ass_list, prefixes):
        if isinstance(ass_p, (str, os.PathLike)):
            ass_one = _pkg_path(os.fspath(ass_p))
        else:
            ass_one = [_pkg_path(os.fspath(item)) for item in ass_p]
        cases.append({
            "main_uv_path": main_p,
            "ass_uv_path": ass_one,
            "output_dir": output_dir,
            "output_prefix": prefix,
        })
    return cases


def _filled(value, key):
    return PRESET[key] if value is None else value


def _process(
    main_uv_path: str,
    ass_uv_path,
    output_dir: str,
    output_prefix: str,
    feature_border: int = 128,
    max_iterations: int = 1024,
    move_percent: float = 1.0,
    write_linear_compare: bool = True,
    weight_value: float = 0.1,
    power_model: int = 2,
    l_scale: int = 1,
    reflect_pad: int = 25,
) -> bool:
    """一个融合任务：读入风场，插件做频域对齐，写出结果。"""
    if isinstance(ass_uv_path, (str, os.PathLike)):
        ass_uv_paths: List[str] = [os.fspath(ass_uv_path)]
    else:
        ass_uv_paths = [os.fspath(item) for item in ass_uv_path]
    if not ass_uv_paths:
        print("ass_uv_path 不能为空")
        return False
    if not os.path.isfile(main_uv_path):
        print(f"主风场不存在: {main_uv_path}")
        return False
    for path in ass_uv_paths:
        if not os.path.isfile(path):
            print(f"辅助风场不存在: {path}")
            return False
    if not (0.0 < float(move_percent) <= 1.0):
        print("move_percent 须满足 (0, 1]")
        return False

    from meteva import base as meb
    from wind_fft_blending_plugin import FFTMergePlugin

    os.makedirs(output_dir, exist_ok=True)
    prefix = str(output_prefix).strip() or "fft_merge"
    print(f"主风场: {main_uv_path}")
    print(f"辅助风场: {ass_uv_paths}")
    print(f"执行结果保存目录：{output_dir}")

    # 读入主场与辅助场
    print("******开始读取输入数据")
    uv1_da = meb.read_gridwind_from_micaps11(main_uv_path)
    print(f"读取完成：{main_uv_path}")
    uv2_da_list = []
    for path in ass_uv_paths:
        da = meb.read_gridwind_from_micaps11(path)
        uv2_da_list.append(da)
        print(f"读取完成：{path}")

    muv_path = os.path.join(output_dir, f"{prefix}_fft_uv.nc")
    muv_m11_path = os.path.join(output_dir, f"{prefix}_fft_uv.m11")
    _del_dir_or_file(muv_path)
    _del_dir_or_file(muv_m11_path)

    # 频域对齐融合
    print("******开始进行FFT融合")
    s_time = time.time()
    muv_da = FFTMergePlugin(
        weight_value=weight_value,
        power_model=power_model,
        l_scale=l_scale,
        reflect_pad=reflect_pad,
    ).process(
        uv1_da,
        uv2_da_list,
        feature_border=int(feature_border),
        max_iterations=int(max_iterations),
        move_percent=float(move_percent),
    )
    muv_da.to_netcdf(muv_path, encoding=_netcdf_encoding(muv_da))
    print(f"FFT融合结果保存成功: {muv_path}")
    print(f"FFT融合完成, 耗时：{round(time.time() - s_time, 4)}s")
    meb.write_griddata_to_micaps11(muv_da, muv_m11_path)
    print(f"FFT风速结果micaps11保存成功（为了方便对比结果）:{muv_m11_path}")

    # 可选：线性平均对比场
    if write_linear_compare:
        luv_path = os.path.join(output_dir, f"{prefix}_line_uv.nc")
        luv_m11_path = os.path.join(output_dir, f"{prefix}_line_uv.m11")
        _del_dir_or_file(luv_path)
        _del_dir_or_file(luv_m11_path)
        print("******开始进行线性插值")
        s_time = time.time()
        luv_da = uv1_da
        for da in uv2_da_list:
            luv_da = luv_da + da
        luv_da = luv_da / float(1 + len(uv2_da_list))
        luv_da.to_netcdf(luv_path, encoding=_netcdf_encoding(luv_da))
        print(f"线性插值结果保存成功: {luv_path}")
        print(f"线性插值执行完成, 耗时：{round(time.time() - s_time, 4)}s")
        meb.write_griddata_to_micaps11(luv_da, luv_m11_path)
        print(f"线性插值风速micaps11结果保存成功（为了方便对比结果）:{luv_m11_path}")

    print("执行完毕")
    return True


@merge_params(anchor=__file__)
def process(
    main_uv_path=None,
    ass_uv_path=None,
    output_dir: str = None,
    output_prefix=None,
    feature_border: int = None,
    max_iterations: int = None,
    move_percent: float = None,
    write_linear_compare: bool = None,
    is_multi: bool = None,
    pro_count: int = None,
    weight_value: float = None,
    power_model: int = None,
    l_scale: int = None,
    reflect_pad: int = None,
    config=None,
):
    """展开融合任务。``pro_count>1`` 时并行调用 ``_process``。"""
    _ = config
    if main_uv_path is None:
        raise ValueError("main_uv_path 未显式传入，且 resource/conf.ini 的 main_uv_path 为空")
    if ass_uv_path is None:
        raise ValueError("ass_uv_path 未显式传入，且 resource/conf.ini 的 ass_uv_path 为空")
    output_dir = _filled(output_dir, "output_dir")
    output_prefix = _filled(output_prefix, "output_prefix")
    common = dict(
        feature_border=int(_filled(feature_border, "feature_border")),
        max_iterations=int(_filled(max_iterations, "max_iterations")),
        move_percent=float(_filled(move_percent, "move_percent")),
        write_linear_compare=bool(_filled(write_linear_compare, "write_linear_compare")),
        weight_value=float(_filled(weight_value, "weight_value")),
        power_model=int(_filled(power_model, "power_model")),
        l_scale=int(_filled(l_scale, "l_scale")),
        reflect_pad=int(_filled(reflect_pad, "reflect_pad")),
    )
    cases = _normalize_cases(main_uv_path, ass_uv_path, output_dir, output_prefix)
    count = int(_filled(pro_count, "pro_count") or 1)
    # 旧调用仍可传 is_multi；真正的分支只看进程数
    if is_multi is False:
        count = 1
    elif is_multi is True and count <= 1:
        count = 2

    if count > 1 and len(cases) > 1:
        sw_all = datetime.now()
        results = SimpleParallelTool(
            target_func=_process,
            parallel_mode="async",
            with_return=True,
            num_process=count,
            fixed_params=common,
        ).process({
            "main_uv_path": [case["main_uv_path"] for case in cases],
            "ass_uv_path": [case["ass_uv_path"] for case in cases],
            "output_dir": [case["output_dir"] for case in cases],
            "output_prefix": [case["output_prefix"] for case in cases],
        })
        print(">>> Time elasped: " + str((datetime.now() - sw_all).total_seconds()))
        results = list(results) if results is not None else []
    else:
        results = [_process(**case, **common) for case in cases]
    if len(cases) == 1:
        return results[0]
    return results
