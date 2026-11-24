# -*- coding: utf-8 -*-
"""极坐标质控插件与网格化编排冒烟测试。"""
from __future__ import annotations

from pathlib import Path

import meteva_base as meb
import numpy as np
import pytest

from radar_qpe_retrieval.cli.cinrad_pyart_prep import load_cinrad_pyart_radar
from radar_qpe_retrieval.cli.radar_qc_cli import process as radar_qc_process
from radar_qpe_retrieval.src.polar_grid import pyart_field_to_meteva_volume
from radar_qpe_retrieval.src.radar_qc import (
    PolarQCResult,
    PolarRadarQCPlugin,
    compute_beam_blockage_mask,
    dem_grid_to_arrays,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = (
    ROOT
    / "resource"
    / "data"
    / "Z_RADR_I_Z9010_20250724192400_O_DOR_SAD_CAP_FMT.bin.bz2"
)
DEM = ROOT / "resource" / "HGT_M_1KM_CHINA.nc"
if not DEM.is_file():
    DEM = (
        ROOT.parent
        / "orographic_wind_downscaling"
        / "resource"
        / "data"
        / "HGT_M_1KM_CHINA.nc"
    )


@pytest.mark.skipif(not DATA.is_file(), reason="sample radar volume missing")
def test_polar_qc_plugin_masks_and_reduces_valid_gates():
    _, radar = load_cinrad_pyart_radar(str(DATA), radius=300)
    before = np.ma.getmaskarray(radar.fields["reflectivity"]["data"]).mean()
    plugin = PolarRadarQCPlugin(
        use_zdr=True,
        use_phidp_texture=True,
        use_kdp_texture=True,
        use_attenuation_correction=True,
        despeckle=True,
        despeckle_size=10,
    )
    radar, gatefilter = plugin.process(radar)
    after = np.ma.getmaskarray(radar.fields["reflectivity"]["data"]).mean()
    assert gatefilter.gate_excluded.any()
    assert after >= before
    assert "specific_differential_phase" in radar.fields
    assert np.ma.getmaskarray(radar.fields["specific_differential_phase"]["data"]).any()
    assert "_qc_phidp_texture" in radar.fields
    assert "_qc_kdp_texture" in radar.fields
    assert "specific_attenuation" in radar.fields
    assert "corrected_reflectivity" in radar.fields
    assert np.isfinite(np.ma.filled(radar.fields["specific_attenuation"]["data"], np.nan)).any()


@pytest.mark.skipif(not DATA.is_file(), reason="sample radar volume missing")
def test_radar_qc_process_shapes():
    out = radar_qc_process(
        input_path=str(DATA), radius=300, resolution=(1000, 1000), sweep=0
    )
    refl0, kdp0, att0 = out["refl"], out["kdp"], out["att"]
    radar, gatefilter = out["radar"], out["gatefilter"]
    assert refl0.ndim == 6
    assert kdp0.ndim == 6
    assert att0 is not None and att0.ndim == 6
    assert refl0.sizes["lat"] == 1000
    assert refl0.sizes["lon"] == 1000
    assert float(refl0.level.values[0]) == pytest.approx(
        float(radar.fixed_angle["data"][0]), abs=0.05
    )
    assert np.isfinite(np.asarray(refl0.values)).any()
    assert np.isfinite(np.asarray(att0.values)).any()
    assert gatefilter.gate_included.any()


@pytest.mark.skipif(not DATA.is_file(), reason="sample radar volume missing")
def test_pyart_field_to_meteva_volume_requires_cinrad_file():
    cinrad_file, radar = load_cinrad_pyart_radar(str(DATA), radius=300)
    radar, _ = PolarRadarQCPlugin(despeckle=False).process(radar)
    with pytest.raises(ValueError, match="cinrad_file"):
        pyart_field_to_meteva_volume(radar, "reflectivity", cinrad_file=None)
    vol = pyart_field_to_meteva_volume(
        radar, "reflectivity", resolution=(500, 500), cinrad_file=cinrad_file
    )
    assert int(vol.sizes["level"]) == int(radar.nsweeps)


@pytest.mark.skipif(
    not (DATA.is_file() and DEM.is_file()),
    reason="sample radar or DEM missing",
)
def test_beam_blockage_with_dem_excludes_gates():
    _, radar = load_cinrad_pyart_radar(str(DATA), radius=300)
    dem = meb.read_griddata_from_nc(str(DEM))
    hgt, lat, lon = dem_grid_to_arrays(dem)
    assert hgt.ndim == 2
    assert lat.size >= 2 and lon.size >= 2

    base = PolarRadarQCPlugin(
        use_phidp_texture=False,
        use_kdp_texture=False,
        use_zdr=False,
        despeckle=False,
    )
    radar_base, gf_base = base.process(radar)
    n_base = int(np.asarray(gf_base.gate_excluded).sum())

    _, radar2 = load_cinrad_pyart_radar(str(DATA), radius=300)
    with_bb = PolarRadarQCPlugin(
        use_phidp_texture=False,
        use_kdp_texture=False,
        use_zdr=False,
        despeckle=False,
    )
    _, gf_bb = with_bb.process(radar2, dem=dem)
    n_bb = int(np.asarray(gf_bb.gate_excluded).sum())
    assert n_bb >= n_base

    blocked = compute_beam_blockage_mask(radar_base, hgt, lat, lon)
    assert blocked.shape == np.asarray(radar_base.fields["reflectivity"]["data"]).shape
    assert blocked.dtype == bool
    # 近站盲区修复后，最低仰角不应被整层误判为遮挡
    s0 = int(radar_base.sweep_start_ray_index["data"][0])
    e0 = int(radar_base.sweep_end_ray_index["data"][0])
    assert blocked[s0 : e0 + 1].mean() < 0.95


@pytest.mark.skipif(not DATA.is_file(), reason="sample radar volume missing")
def test_plugin_process_with_cinrad_returns_qpe_grids():
    cinrad_file, radar = load_cinrad_pyart_radar(str(DATA), radius=300)
    result = PolarRadarQCPlugin(
        despeckle=False,
        resolution=(500, 500),
        sweep=0,
    ).process(radar, cinrad_file=cinrad_file)
    assert isinstance(result, PolarQCResult)
    assert result.refl is not None and result.refl.ndim == 6
    assert result.kdp is not None and result.kdp.ndim == 6
    assert result.att is not None and result.att.ndim == 6
    assert np.isfinite(np.asarray(result.refl.values)).any()
    assert int(result.volumes["reflectivity"].sizes["level"]) == int(result.radar.nsweeps)
