# -*- coding: utf-8 -*-
"""CLI 合参约定：签名预设 / conf.ini 键名 / 输入 config 覆盖 / 校验报错。"""
from __future__ import annotations

import configparser
import inspect
import typing
from pathlib import Path

import pytest

import cli.interpolation_station_grid_cli as cli_mod
from utils.merge_params import collect_merged_params

PKG = Path(cli_mod.__file__).resolve().parents[1]
CLI_FILE = cli_mod.__file__
process = cli_mod.process
RAW = process.__wrapped__


def _merged(external=None, config=None):
    sig = inspect.signature(RAW)
    presets = {n: p.default for n, p in sig.parameters.items() if p.default is not p.empty}
    ann = typing.get_type_hints(RAW)
    ext = dict(external or {})
    if config is not None:
        ext["config"] = config
    return collect_merged_params(
        ext,
        anchor_file=CLI_FILE,
        presets=presets,
        annotations=ann,
        param_names=list(sig.parameters),
    )


def test_ini_keys_match_process_params_and_are_unique() -> None:
    parser = configparser.ConfigParser()
    parser.read(PKG / "resource" / "conf.ini", encoding="utf-8")
    params = set(inspect.signature(RAW).parameters) - {"config"}
    keys = [k for s in parser.sections() for k in parser[s]]
    assert len(keys) == len(set(keys)), "conf.ini 中键名重复"
    assert set(keys) <= params, "conf.ini 中有不属于 process 形参的键: %s" % (set(keys) - params)


def test_defaults_from_ini_and_signature() -> None:
    got = _merged()
    assert got["method"] == "idw"
    assert got["reprocess"] is False
    assert got["outer_value"] is None
    assert got["idw_effect_r"] == 1000
    assert got["idw_near_num"] == 8
    assert got["idw_gaussian"] is False
    assert got["kriging_near_num"] == 20
    assert got["cressman_r_list"] is None
    assert got["cressman_near_num"] == 100
    assert got["sta"] is None


def test_explicit_string_values_are_cast() -> None:
    got = _merged({"reprocess": "true", "idw_effect_r": "500", "idw_gaussian": "true"})
    assert got["reprocess"] is True
    assert got["idw_effect_r"] == 500
    assert got["idw_gaussian"] is True


def test_input_config_overrides_default_ini(tmp_path: Path) -> None:
    alt = tmp_path / "alt.ini"
    alt.write_text("[idw]\nidw_gaussian=true\nidw_near_num=5\n", encoding="utf-8")
    got = _merged(config=str(alt))
    assert got["idw_gaussian"] is True
    assert got["idw_near_num"] == 5
    # 显式传入压过输入配置
    over = _merged({"idw_near_num": "3"}, config=str(alt))
    assert over["idw_near_num"] == 3


def test_invalid_methods_rejected() -> None:
    for bad in ("idw_delta", "total", "unknown"):
        with pytest.raises(ValueError, match="method"):
            process(method=bad, sta="resource/obs_gust_d24.csv", background="resource/bg_fcst_idw.nc")


def test_missing_sta_and_grid_background() -> None:
    with pytest.raises(ValueError, match="sta"):
        process(grid="resource/target_grid.nc")
    with pytest.raises(ValueError, match="grid 或 background"):
        process(sta="resource/obs_gust_d24.csv")


def test_reprocess_requires_background() -> None:
    with pytest.raises(ValueError, match="background"):
        process(sta="resource/obs_gust_d24.csv", grid="resource/target_grid.nc", reprocess=True)


def test_process_writes_output(tmp_path: Path) -> None:
    out = tmp_path / "out.nc"
    result = process(
        method="idw",
        sta="resource/obs_gust_d24.csv",
        grid="resource/target_grid.nc",
        output=str(out),
    )
    assert result is not None
    assert out.is_file()


# ---------------------------------------------------------------------------
# 完整性：半径小数、Cressman 高级参数、默认值与插件一致、ini 与形参一一对应
# ---------------------------------------------------------------------------
_CRESSMAN_ADV = (
    "rain_limit",
    "num_limit",
    "smooth",
    "power_param",
    "r_km_scale",
    "innov_gain",
    "residual_passes",
    "residual_degree_polish",
    "residual_polish_rounds",
    "degree_blend",
    "station_anchor_radius",
    "station_anchor_strength",
)


def test_every_process_param_has_ini_key() -> None:
    """形参 ↔ conf.ini 键名双向一一对应（config 例外）。"""
    parser = configparser.ConfigParser()
    parser.read(PKG / "resource" / "conf.ini", encoding="utf-8")
    keys = {k for s in parser.sections() for k in parser[s]}
    params = set(inspect.signature(RAW).parameters) - {"config"}
    assert params <= keys, "conf.ini 缺少键: %s" % sorted(params - keys)


def test_radius_params_accept_decimal_strings() -> None:
    got = _merged({"gaussian_half_r": "12.5", "idw_effect_r": "300.5"})
    assert got["gaussian_half_r"] == 12.5
    assert got["idw_effect_r"] == 300.5


def test_cressman_advanced_defaults_match_plugin() -> None:
    """CLI 里 cressman_* 的预设值必须与 InterpSgCressman 构造默认值一致，避免漂移。"""
    from interp_sg_cressman_plugin import InterpSgCressman

    cli_params = inspect.signature(RAW).parameters
    plugin_params = inspect.signature(InterpSgCressman.__init__).parameters
    for name in _CRESSMAN_ADV:
        assert cli_params["cressman_" + name].default == plugin_params[name].default, name
    assert cli_params["cressman_near_num"].default == plugin_params["nearNum"].default


def test_cressman_advanced_params_are_cast_from_strings() -> None:
    got = _merged(
        {
            "cressman_degree_blend": "1.0",
            "cressman_rain_limit": "0.01",
            "cressman_residual_passes": "2",
            "cressman_residual_degree_polish": "false",
        }
    )
    assert got["cressman_degree_blend"] == 1.0
    assert got["cressman_rain_limit"] == 0.01
    assert got["cressman_residual_passes"] == 2
    assert got["cressman_residual_degree_polish"] is False


def test_cressman_advanced_params_forwarded_to_interp_sg(monkeypatch) -> None:
    """CLI 把全部 cressman_* 原样转给 InterpSg（不真正插值，只截获构造参数）。"""
    import interp_sg_plugin

    seen = {}

    class _Spy:
        def __init__(self, **kw):
            seen.update(kw)

        def process(self, sta, grid=None, background=None):
            return "result"

    monkeypatch.setattr(interp_sg_plugin, "InterpSg", _Spy)
    process(
        method="cressman",
        sta="resource/obs_gust_d24.csv",
        background="resource/bg_fcst_idw.nc",
        reprocess=True,
        cressman_r_list="1.0,0.8,0.6,0.4",
        cressman_near_num=50,
        cressman_rain_limit=0.01,
        cressman_num_limit=2.0,
        cressman_smooth=0.002,
        cressman_power_param=1.5,
        cressman_r_km_scale=1.2,
        cressman_innov_gain=0.9,
        cressman_residual_passes=1,
        cressman_residual_degree_polish=False,
        cressman_residual_polish_rounds=2,
        cressman_degree_blend=1.0,
        cressman_station_anchor_radius=0.5,
        cressman_station_anchor_strength=0.3,
    )
    assert seen["method"] == "cressman"
    assert seen["reprocess"] is True
    assert seen["r_list"] == [1.0, 0.8, 0.6, 0.4]
    assert seen["nearNum"] == 50
    expected = {
        "rain_limit": 0.01,
        "num_limit": 2.0,
        "smooth": 0.002,
        "power_param": 1.5,
        "r_km_scale": 1.2,
        "innov_gain": 0.9,
        "residual_passes": 1,
        "residual_degree_polish": False,
        "residual_polish_rounds": 2,
        "degree_blend": 1.0,
        "station_anchor_radius": 0.5,
        "station_anchor_strength": 0.3,
    }
    for key, value in expected.items():
        assert seen[key] == value, key


def test_decimal_radius_forwarded_without_truncation(monkeypatch) -> None:
    import interp_sg_plugin

    seen = {}

    class _Spy:
        def __init__(self, **kw):
            seen.update(kw)

        def process(self, sta, grid=None, background=None):
            return "result"

    monkeypatch.setattr(interp_sg_plugin, "InterpSg", _Spy)
    process(
        method="gaussian",
        sta="resource/obs_gust_d24.csv",
        grid="resource/target_grid.nc",
        gaussian_half_r=12.5,
    )
    assert seen["halfR"] == 12.5


@pytest.mark.parametrize(
    "key, value, match",
    [
        ("cressman_degree_blend", 1.5, "cressman_degree_blend"),
        ("cressman_degree_blend", -0.1, "cressman_degree_blend"),
        ("cressman_power_param", 0.0, "cressman_power_param"),
        ("cressman_r_km_scale", 0.0, "cressman_r_km_scale"),
        ("cressman_station_anchor_radius", 0.0, "cressman_station_anchor_radius"),
        ("cressman_smooth", -1.0, "cressman_smooth"),
        ("cressman_residual_passes", -1, "cressman_residual_passes"),
    ],
)
def test_cressman_advanced_values_validated(key, value, match) -> None:
    with pytest.raises(ValueError, match=match):
        process(
            method="cressman",
            sta="resource/obs_gust_d24.csv",
            background="resource/bg_fcst_idw.nc",
            reprocess=True,
            **{key: value},
        )