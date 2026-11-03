import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from fy4agri.metadata import CHANNELS, parse_channels
from fy4_batch_latlon_channel_plugin import parse_fy4_filename, parse_time
from fy4_latlon_channel_plugin import FY4LatLonChannelPlugin


def test_parse_channels_range_and_list():
    assert parse_channels("1-3,5") == [1, 2, 3, 5]
    assert CHANNELS[13].unit == "K"


def test_parse_channels_rejects_invalid_channel():
    with pytest.raises(ValueError):
        parse_channels("1,99")


def test_parse_time_supports_hour_precision():
    assert parse_time("2023010406").strftime("%Y%m%d%H%M%S") == "20230104060000"


def test_parse_fy4_filename():
    info = parse_fy4_filename(
        "FY4B-_AGRI--_N_DISK_1050E_L1-_FDI-_MULT_NOM_"
        "20230104060000_20230104061459_4000M_V0001.HDF"
    )
    assert info is not None
    assert info.center == "1050E"
    assert info.ymdh == "2023010406"


def test_plugin_parameter_validation():
    with pytest.raises(ValueError):
        FY4LatLonChannelPlugin(resolution=0)

