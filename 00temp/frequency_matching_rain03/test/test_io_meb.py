# -*- coding: utf-8 -*-
from datetime import datetime

from utils.io_meb import expand_data_path, resolve_existing_path


def test_expand_data_path_10_digit_hour_and_lead():
    tpl = "/data/rain03/YYYYMMDD/YYYYMMDDHH.VVV"
    dt = datetime(2026, 8, 20, 0, 0)
    path = expand_data_path(tpl, dt, 3)
    assert "20260820" in path
    assert path.endswith(".003")
    assert "2026082000" in path


def test_expand_data_path_12_digit_same_as_10():
    tpl = "/obs/YYYYMMDD/h03_YYYYMMDDHH00.m3"
    dt = datetime(2026, 8, 20, 8, 0)
    path = expand_data_path(tpl, dt, 0)
    assert path.endswith("h03_202608200800.m3")
    assert "/20260820/" in path.replace("\\", "/")


def test_resolve_existing_path_appends_m4(tmp_path):
    base = tmp_path / "2026082000.003"
    (tmp_path / "2026082000.003.m4").write_text("diamond 4", encoding="utf-8")
    found = resolve_existing_path(str(base), (".m4", ".nc"))
    assert found is not None
    assert found.endswith(".m4")


def test_resolve_existing_path_prefers_exact(tmp_path):
    exact = tmp_path / "file.m4"
    exact.write_text("x", encoding="utf-8")
    found = resolve_existing_path(str(exact), (".m4", ".nc"))
    assert found == str(exact)


def test_resolve_existing_path_missing_returns_none(tmp_path):
    assert resolve_existing_path(str(tmp_path / "no_such"), (".m4", ".nc")) is None


def test_describe_task_io_finds_m4_suffix(tmp_path):
    from runner import _describe_task_io

    dt = datetime(2026, 8, 20, 0, 0)
    model_dir = tmp_path / "20260820"
    model_dir.mkdir()
    (model_dir / "2026082000.003.m4").write_text("x", encoding="utf-8")
    model_tpl = str(tmp_path / "YYYYMMDD" / "YYYYMMDDHH.VVV")
    out_tpl = str(tmp_path / "out" / "YYYYMMDDHH.VVV")
    info = _describe_task_io(model_tpl, out_tpl, dt, 3)
    assert info["model_missing"] is False
    assert info["model_path"].endswith(".m4")
    assert info["output_exists"] is False


def test_grid_data_reads_path_without_m4_suffix(tmp_path):
    from utils.grid_data import GridData

    tokens = (
        "diamond 4 test 2026 08 20 00 00 003 "
        "1.0 1.0 110.0 111.0 30.0 31.0 2 2 a b c d e "
        "1.0 2.0 3.0 4.0"
    )
    (tmp_path / "field.m4").write_text(tokens + "\n", encoding="utf-8")
    gd = GridData(str(tmp_path / "field"))
    assert gd.xn == 2 and gd.yn == 2
    assert abs(float(gd.val[0, 0]) - 1.0) < 1e-6


def test_align_meb_grid_flips_when_inverted_vs_original(tmp_path):
    """meb 相对原版南北颠倒时，align 应翻回。"""
    import numpy as np
    from utils.io_meb import align_meb_grid_to_original, parse_micaps4_like_original

    p = tmp_path / "ns.m4"
    p.write_text(
        "diamond 4 t 2026 08 20 00 00 003 1.0 -1.0 110.0 111.0 31.0 30.0 2 2 "
        "2.0 0.0 20.0 1 00\n0.06 0.08\n0.28 0.32\n",
        encoding="gb2312",
    )
    orig = parse_micaps4_like_original(str(p))["val"]
    inverted = orig[::-1].copy()
    fixed = align_meb_grid_to_original(inverted, str(p))
    assert float(np.max(np.abs(fixed - orig))) < 1e-6


def test_write_stadata_m3_via_meb(tmp_path):
    """站点写出：sta_data → meb.write_stadata_to_micaps3，再用 meb 读回。"""
    from utils.io_meb import write_stadata_m3
    import meteva_base as meb

    out = tmp_path / "out.m3"
    write_stadata_m3(
        ["50136", "54511"],
        [122.52, 116.28],
        [52.97, 39.93],
        [12.5, 0.3],
        str(out),
        dt_input=datetime(2026, 8, 21, 0, 0),
        i_valid=3,
    )
    assert out.is_file()
    sta = meb.read_stadata_from_micaps3(str(out))
    assert sta is not None
    assert len(sta) == 2
    vals = {str(int(i)): float(v) for i, v in zip(sta["id"], sta["data0"])}
    assert abs(vals["50136"] - 12.5) < 1e-6
    assert abs(vals["54511"] - 0.3) < 1e-6


def test_write_griddata_m4_via_meb(tmp_path):
    """格点写出：grid_data → meb.write_griddata_to_micaps4，网格信息来自 grd。"""
    from utils.grid_data import GridData
    import meteva_base as meb

    gd = GridData(2, 2, 110.0, 30.0, 1.0, 1.0)
    gd.val[0, 0] = 1.0
    gd.val[0, 1] = 2.0
    gd.val[1, 0] = 3.0
    gd.val[1, 1] = 4.0
    out = tmp_path / "out.m4"
    gd.write_val_to_micaps4(
        str(out), title="qpf_fm_test",
        dt_input=datetime(2026, 8, 21, 0, 0), i_valid=3)
    assert out.is_file()
    text = out.read_text(encoding="utf-8", errors="ignore")
    assert text.startswith("diamond 4")
    assert "qpf_fm_test" in text.splitlines()[0]
    # 网格行由 meb 从 grd 写出，不应再塞原版整行头
    grd = meb.read_griddata_from_micaps4(str(out))
    assert grd is not None
    assert grd.values.size >= 4
