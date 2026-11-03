"""conf.ini 键可以覆盖算法参数读取，缺键时用预设，不启动预报。"""
import configparser
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fast_refine_interp_plugin import FastRefineInterpPlugin
from src.para_ini import _load_fast_refine_sections


class _Args:
    update = 0


def _sample_config():
    cfg = configparser.ConfigParser()
    cfg.read_dict(
        {
            "InstantInfo": {
                "dem_head": "DEM",
                "dem_format": "tif",
                "recall": "False",
                "Interp_Time": "False",
                "validate": "False",
                "validate_area": "NONE",
                "del_no_eta": "False",
                "out_China": "False",
                "eta_cmn_out": "False",
                "VR_plot": "False",
                "rlt_plot": "False",
                "plot_format": "png",
                "MICAPS_out": "False",
                "PQ_shortname": "2t",
            },
            "MaxMinInfo": {
                "Interp_Maxmin": "False",
                "update": "False",
                "validate": "False",
                "forecast_time": "012_036",
            },
            "SiteInfo": {"custom_path": "sample_minimal/Parameter/Station1"},
            "PoolInfo": {
                "FH_parallel": "False",
                "FH_max_pcount": "1",
                "FH_DI_timeout": "900",
                "FH_TI_timeout": "900",
                "BT_parallel": "False",
                "BT_max_pcount": "1",
                "BT_timeout": "900",
                "Para_parallel": "False",
                "Para_max_pcount": "1",
                "Para_timeout": "900",
            },
            "threshold": {
                "2t": "2.0",
                "2rh": "10.0",
                "10ws": "2.0",
                "10u": "2.0",
                "10v": "2.0",
                "2t_max": "2.0",
                "2t_min": "2.0",
                "2rh_max": "10.0",
                "2rh_min": "10.0",
                "10ws_max": "2.0",
            },
        }
    )
    return cfg


def test_complete_ini_without_overrides_matches_file():
    instant, maxmin, site, pool, threshold = _load_fast_refine_sections(_sample_config(), _Args(), None)
    assert instant["dem_head"] == "DEM"
    assert instant["validate"] is False
    assert instant["Prov_code"] is None
    assert instant["PQ_shortname"] == ["2t"]
    assert maxmin["update"] is False
    assert maxmin["forecast_time"] == ["012_036"]
    assert site["custom_path"] == "sample_minimal/Parameter/Station1"
    assert pool["FH_max_pcount"] == 1
    assert threshold["2t"] == 2.0
    assert threshold["2rh"] == 10.0


def test_override_replaces_ini_and_missing_key_uses_preset():
    cfg = _sample_config()
    cfg.remove_option("InstantInfo", "dem_format")
    cfg.remove_option("threshold", "10u")
    cfg.remove_option("MaxMinInfo", "update")
    instant, maxmin, _site, _pool, threshold = _load_fast_refine_sections(
        cfg,
        _Args(),
        {
            "InstantInfo.validate": True,
            "MaxMinInfo.validate": True,
            "threshold.2t": 3.5,
        },
    )
    assert instant["validate"] is True
    assert instant["dem_format"] == "tif"
    assert maxmin["validate"] is True
    assert maxmin["update"] is False
    assert threshold["2t"] == 3.5
    assert threshold["10u"] == 2.0


def test_plugin_accepts_ini_parameters():
    plugin = FastRefineInterpPlugin(work_dir="D:/tmp/EC_12P5KM", model_region="EC_12P5KM")
    assert plugin.ini_overrides is None
    assert "maxmin_update" in plugin.process.__code__.co_varnames
    assert "validate" in plugin.process.__code__.co_varnames
