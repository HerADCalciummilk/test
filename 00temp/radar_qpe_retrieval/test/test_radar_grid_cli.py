# -*- coding: utf-8 -*-
"""基数据 → 经纬网格附属 CLI 冒烟测试（轻量读入，无 cinrad）。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = (
    ROOT
    / "resource"
    / "data"
    / "Z_RADR_I_Z9010_20250724192400_O_DOR_SAD_CAP_FMT.bin.bz2"
)


@pytest.mark.skipif(not DATA.is_file(), reason="sample radar volume missing")
def test_load_standard_radar_via_cli_module():
    from radar_qpe_retrieval.cli.standard_data import (
        RadarDecodeError,
        load_standard_radar,
    )

    radar = load_standard_radar(DATA)
    assert radar.site_code
    refl = radar.get_array(tilt=0, drange=80, dtype="REF")
    assert refl.ndim == 2 and refl.shape[0] > 0

    bad = ROOT / "resource" / "data" / "__not_a_radar__.bin"
    # 仅测异常类型导入；垃圾文件用临时构造
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(b"X" * 64)
        bad_path = f.name
    try:
        with pytest.raises(RadarDecodeError):
            load_standard_radar(bad_path)
    finally:
        Path(bad_path).unlink(missing_ok=True)


@pytest.mark.skipif(not DATA.is_file(), reason="sample radar volume missing")
def test_process_grids_ref_to_netcdf(tmp_path):
    from radar_qpe_retrieval.cli.radar_grid_cli import process

    out_dir = tmp_path / "grid_out"
    result = process(
        input_path=str(DATA),
        output_dir=str(out_dir),
        fields="REF",
        radius=100,
        resolution=(200, 200),
        sweep=0,
    )
    assert "REF" in result["levels"]
    refl = result["levels"]["REF"]
    assert refl.ndim == 6
    assert int(refl.sizes["level"]) == 1
    assert np.isfinite(np.asarray(refl.values, dtype=np.float64)).any()
    assert (out_dir / "REF.nc").is_file()


@pytest.mark.skipif(not DATA.is_file(), reason="sample radar volume missing")
def test_process_volume_multi_field(tmp_path):
    from radar_qpe_retrieval.cli.radar_grid_cli import process

    out_dir = tmp_path / "vol_out"
    result = process(
        input_path=str(DATA),
        output_dir=str(out_dir),
        fields="REF,KDP",
        radius=80,
        resolution=(120, 120),
        volume=True,
    )
    assert "REF" in result["fields"]
    for name, vol in result["volumes"].items():
        assert int(vol.sizes["level"]) >= 1
        assert (out_dir / f"{name}.nc").is_file()
