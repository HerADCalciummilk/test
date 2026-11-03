# -*- coding: utf-8 -*-
"""调用 ``src/main.process`` 的集成测试。"""
import shutil
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
_OUT = _REPO / "test" / "_main_out"
_TEST_DATA = (
    _REPO.parents[1].parent
    / "NIMM_pip_testdata"
    / "multi_wind_fft_blending"
    / "test_data"
)

for _p in (str(_REPO), str(_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from main import process  # noqa: E402


def _require_sample(sample: str = "a"):
    main_uv = _TEST_DATA / f"sample_{sample}1_uv.m11"
    ass_uv = _TEST_DATA / f"sample_{sample}2_uv.m11"
    if not (main_uv.is_file() and ass_uv.is_file()):
        pytest.skip(f"缺少示例数据: {main_uv} / {ass_uv}")
    return str(main_uv), str(ass_uv)


def setup_module():
    if _OUT.is_dir():
        shutil.rmtree(_OUT, ignore_errors=True)
    _OUT.mkdir(parents=True, exist_ok=True)


def teardown_module():
    if _OUT.is_dir():
        shutil.rmtree(_OUT, ignore_errors=True)


def test_process_sample_a():
    main_uv, ass_uv = _require_sample("a")
    prefix = "test_sample_a"
    ok = process(
        main_uv_path=main_uv,
        ass_uv_path=ass_uv,
        output_dir=str(_OUT),
        output_prefix=prefix,
        feature_border=128,
        max_iterations=1024,
        move_percent=1.0,
        write_linear_compare=True,
        is_multi=False,
    )
    assert ok is True
    assert (_OUT / f"{prefix}_fft_uv.nc").is_file()
    assert (_OUT / f"{prefix}_fft_uv.m11").is_file()
    assert (_OUT / f"{prefix}_line_uv.nc").is_file()
    assert (_OUT / f"{prefix}_line_uv.m11").is_file()


def test_process_missing_input_returns_false():
    ok = process(
        main_uv_path=str(_TEST_DATA / "not_exist_main.m11"),
        ass_uv_path=str(_TEST_DATA / "not_exist_ass.m11"),
        output_dir=str(_OUT),
        output_prefix="missing_case",
    )
    assert ok is False


def test_process_invalid_move_percent_returns_false():
    main_uv, ass_uv = _require_sample("a")
    ok = process(
        main_uv_path=main_uv,
        ass_uv_path=ass_uv,
        output_dir=str(_OUT),
        output_prefix="bad_move",
        move_percent=0.0,
        write_linear_compare=False,
    )
    assert ok is False


def test_process_multi_serial():
    main_a, ass_a = _require_sample("a")
    main_b, ass_b = _require_sample("b")
    results = process(
        main_uv_path=[main_a, main_b],
        ass_uv_path=[ass_a, ass_b],
        output_dir=str(_OUT),
        output_prefix=["serial_a", "serial_b"],
        feature_border=64,
        max_iterations=16,
        write_linear_compare=False,
        is_multi=False,
    )
    assert results == [True, True]
    assert (_OUT / "serial_a_fft_uv.m11").is_file()
    assert (_OUT / "serial_b_fft_uv.m11").is_file()


def test_process_multi_parallel():
    main_a, ass_a = _require_sample("a")
    main_b, ass_b = _require_sample("b")
    results = process(
        main_uv_path=[main_a, main_b],
        ass_uv_path=[ass_a, ass_b],
        output_dir=str(_OUT),
        output_prefix=["mp_a", "mp_b"],
        feature_border=64,
        max_iterations=16,
        write_linear_compare=False,
        is_multi=True,
        pro_count=2,
    )
    assert results == [True, True]
    assert (_OUT / "mp_a_fft_uv.m11").is_file()
    assert (_OUT / "mp_b_fft_uv.m11").is_file()


if __name__ == "__main__":
    setup_module()
    try:
        test_process_missing_input_returns_false()
        test_process_invalid_move_percent_returns_false()
        test_process_multi_serial()
        test_process_multi_parallel()
        test_process_sample_a()
        print("all tests passed")
    finally:
        teardown_module()
