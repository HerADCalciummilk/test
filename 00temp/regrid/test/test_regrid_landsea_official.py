#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RegridLandSea 官方样例全量对照测试。

算法输入取自 ``python regrid/cli/preprocess_test_data.py`` 写出的 ``test_data/cli_input/``；
KGO / 原版 iris 仍对照 ``test_data/`` 下官方文件。
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import iris
import meteva_base as meb
import numpy as np
import pytest

from regrid import RegridLandSea
from regrid.test.helpers import to_compare_array

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
DATA_DIR = PACKAGE_ROOT / "test_data"
CLI_INPUT = DATA_DIR / "cli_input"
IMPROVER_ROOT = PROJECT_ROOT / "improver-1.18.7"

if IMPROVER_ROOT.exists() and str(IMPROVER_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPROVER_ROOT))


def _require_files(*paths: Path) -> None:
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        pytest.skip(
            f"测试数据缺失（请先运行 python regrid/cli/preprocess_test_data.py）: {missing}"
        )


# case_id, mode, cli_input, cli_target, cli_landmask, vicinity,
# official_input, official_target, official_landmask, kgo_rel, atol, extrapolation_mode
OFFICIAL_CASES = [
    (
        "single_bilinear",
        "bilinear",
        "global_cutout.nc",
        "ukvx_grid.nc",
        None,
        25000.0,
        "global_cutout.nc",
        "ukvx_grid.nc",
        None,
        "basic/kgo.nc",
        1e-4,
        "nanmask",
    ),
    (
        "single_bilinear-2",
        "bilinear-2",
        "global_cutout.nc",
        "ukvx_grid.nc",
        None,
        25000.0,
        "global_cutout.nc",
        "ukvx_grid.nc",
        None,
        "basic/kgo.nc",
        1e-4,
        "nanmask",
    ),
    (
        "single_nearest",
        "nearest",
        "global_cutout.nc",
        "ukvx_grid.nc",
        None,
        25000.0,
        "global_cutout.nc",
        "ukvx_grid.nc",
        None,
        "nearest/kgo.nc",
        1e-4,
        "nanmask",
    ),
    (
        "single_nearest_extrapolate",
        "nearest",
        "ukvx_grid.nc",
        "global_cutout.nc",
        None,
        25000.0,
        "ukvx_grid.nc",
        "global_cutout.nc",
        None,
        "extrapolate/kgo.nc",
        1e-4,
        "extrapolate",
    ),
    (
        "single_nearest-with-mask",
        "nearest-with-mask",
        "global_cutout.nc",
        "ukvx_landmask.nc",
        "glm_landmask.nc",
        100000.0,
        "global_cutout.nc",
        "landmask/ukvx_landmask.nc",
        "landmask/glm_landmask.nc",
        "landmask/kgo.nc",
        1e-4,
        "nanmask",
    ),
    (
        "multi_nearest-with-mask",
        "nearest-with-mask",
        "global_cutout_multi_realization.nc",
        "ukvx_landmask.nc",
        "engl_landmask.nc",
        100000.0,
        "landmask/global_cutout_multi_realization.nc",
        "landmask/ukvx_landmask.nc",
        "landmask/engl_landmask.nc",
        "landmask/kgo_multi_realization.nc",
        1e-4,
        "nanmask",
    ),
    (
        "multi_nearest-2",
        "nearest-2",
        "global_cutout_multi_realization.nc",
        "ukvx_landmask.nc",
        None,
        25000.0,
        "landmask/global_cutout_multi_realization.nc",
        "landmask/ukvx_landmask.nc",
        None,
        "nearest_2/kgo_multi_realization.nc",
        1e-4,
        "nanmask",
    ),
    (
        "multi_bilinear-2",
        "bilinear-2",
        "global_cutout_multi_realization.nc",
        "ukvx_landmask.nc",
        None,
        25000.0,
        "landmask/global_cutout_multi_realization.nc",
        "landmask/ukvx_landmask.nc",
        None,
        "bilinear_2/kgo_multi_realization.nc",
        1e-4,
        "nanmask",
    ),
    (
        "multi_nearest-with-mask-2",
        "nearest-with-mask-2",
        "global_cutout_multi_realization.nc",
        "ukvx_landmask.nc",
        "engl_landmask.nc",
        25000.0,
        "landmask/global_cutout_multi_realization.nc",
        "landmask/ukvx_landmask.nc",
        "landmask/engl_landmask.nc",
        "nearest_landmask_2/kgo_multi_realization.nc",
        1e-4,
        "nanmask",
    ),
    (
        "multi_bilinear-with-mask-2",
        "bilinear-with-mask-2",
        "global_cutout_multi_realization.nc",
        "ukvx_landmask.nc",
        "engl_landmask.nc",
        25000.0,
        "landmask/global_cutout_multi_realization.nc",
        "landmask/ukvx_landmask.nc",
        "landmask/engl_landmask.nc",
        "bilinear_landmask_2/kgo_multi_realization.nc",
        0.05,
        "nanmask",
    ),
]


def _run_original(
    mode: str,
    input_nc: Path,
    target_nc: Path,
    landmask_nc: Path | None = None,
    vicinity: float = 25000.0,
    extrapolation_mode: str = "nanmask",
):
    iris = pytest.importorskip("iris")
    from improver.regrid.landsea import RegridLandSea as OriginalRegridLandSea

    landmask = iris.load_cube(str(landmask_nc)) if landmask_nc is not None else None
    plugin = OriginalRegridLandSea(
        regrid_mode=mode,
        landmask=landmask,
        landmask_vicinity=vicinity,
        extrapolation_mode=extrapolation_mode,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return plugin(
            iris.load_cube(str(input_nc)),
            iris.load_cube(str(target_nc)),
            regridded_title="test",
        )


@pytest.mark.parametrize(
    "case_id,mode,cli_in,cli_tgt,cli_mask,vicinity,"
    "off_in,off_tgt,off_mask,kgo_rel,atol,extrapolation_mode",
    OFFICIAL_CASES,
    ids=[c[0] for c in OFFICIAL_CASES],
)
def test_regrid_landsea_against_kgo_and_original(
    case_id: str,
    mode: str,
    cli_in: str,
    cli_tgt: str,
    cli_mask: str | None,
    vicinity: float,
    off_in: str,
    off_tgt: str,
    off_mask: str | None,
    kgo_rel: str,
    atol: float,
    extrapolation_mode: str,
) -> None:
    """迁移版读 cli_input；对照官方 KGO 与原版 iris。"""
    src_path = CLI_INPUT / cli_in
    tgt_path = CLI_INPUT / cli_tgt
    mask_path = CLI_INPUT / cli_mask if cli_mask else None
    kgo_nc = DATA_DIR / kgo_rel
    off_in_nc = DATA_DIR / off_in
    off_tgt_nc = DATA_DIR / off_tgt
    off_mask_nc = DATA_DIR / off_mask if off_mask else None

    required = [src_path, tgt_path, kgo_nc, off_in_nc, off_tgt_nc]
    if mask_path is not None:
        required.append(mask_path)
    if off_mask_nc is not None:
        required.append(off_mask_nc)
    _require_files(*required)

    _unbounded = (-np.inf, np.inf, np.nan)
    src = meb.checkout_griddata(
        meb.read_griddata_from_nc(str(src_path)), valid_val=_unbounded
    )
    tgt = meb.checkout_griddata(
        meb.read_griddata_from_nc(str(tgt_path)), valid_val=_unbounded
    )
    landmask = (
        meb.checkout_griddata(
            meb.read_griddata_from_nc(str(mask_path)), valid_val=_unbounded
        )
        if mask_path is not None
        else None
    )
    # KGO / 原版只比数值：直接 iris.load_cube，不做六维转换
    kgo = iris.load_cube(str(kgo_nc))

    migrated = RegridLandSea(
        regrid_mode=mode,
        landmask=landmask,
        landmask_vicinity=vicinity,
        extrapolation_mode=extrapolation_mode,
    )(src, tgt, regridded_title="test")

    mig_arr = to_compare_array(migrated)
    kgo_arr = to_compare_array(kgo)
    assert mig_arr.shape == kgo_arr.shape, f"{case_id}: migrated vs KGO shape"
    np.testing.assert_allclose(
        mig_arr, kgo_arr, atol=atol, rtol=1e-4, equal_nan=True
    )

    original = _run_original(
        mode, off_in_nc, off_tgt_nc, off_mask_nc, vicinity, extrapolation_mode
    )
    orig_arr = to_compare_array(original)
    assert mig_arr.shape == orig_arr.shape, f"{case_id}: migrated vs original shape"
    np.testing.assert_allclose(
        mig_arr, orig_arr, atol=atol, rtol=1e-4, equal_nan=True
    )
    np.testing.assert_allclose(
        orig_arr, kgo_arr, atol=atol, rtol=1e-4, equal_nan=True
    )
