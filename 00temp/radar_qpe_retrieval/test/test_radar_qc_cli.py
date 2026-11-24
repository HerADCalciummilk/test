# -*- coding: utf-8 -*-
"""质控 CLI（radar_qc_cli）冒烟测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT.parent
for p in (TEMP, ROOT):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from radar_qpe_retrieval.cli.radar_qc_cli import RadarQcCli, process  # noqa: E402

DATA = (
    ROOT
    / "resource"
    / "data"
    / "Z_RADR_I_Z9010_20250724192400_O_DOR_SAD_CAP_FMT.bin.bz2"
)


def test_radar_qc_cli_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        RadarQcCli().main(["--help"])
    assert exc.value.code in (0, None)


@pytest.mark.skipif(not DATA.is_file(), reason="sample radar volume missing")
def test_process_writes_refl_kdp(tmp_path):
    refl_out = tmp_path / "refl_qc.nc"
    kdp_out = tmp_path / "kdp_qc.nc"
    att_out = tmp_path / "att_qc.nc"
    result = process(
        input_path=str(DATA),
        radius=300,
        resolution=(500, 500),
        sweep=0,
        use_attenuation_correction=True,
        despeckle=False,
        use_phidp_texture=False,
        use_kdp_texture=False,
        use_zdr=False,
        refl_output_path=str(refl_out),
        kdp_output_path=str(kdp_out),
        att_output_path=str(att_out),
    )
    assert refl_out.is_file()
    assert kdp_out.is_file()
    assert result["refl"] is not None
    assert result["kdp"] is not None
    if result["att"] is not None:
        assert att_out.is_file()
