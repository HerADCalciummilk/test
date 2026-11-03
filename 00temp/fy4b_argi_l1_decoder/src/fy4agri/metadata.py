from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChannelInfo:
    number: int
    wavelength: str
    unit: str
    value_kind: str

    @property
    def hdf_suffix(self):
        return f"{self.number:02d}"

    @property
    def safe_wavelength(self):
        return self.wavelength.replace(".", "p")


CHANNELS = {
    1: ChannelInfo(1, "0.47um", "1", "reflectance"),
    2: ChannelInfo(2, "0.65um", "1", "reflectance"),
    3: ChannelInfo(3, "0.825um", "1", "reflectance"),
    4: ChannelInfo(4, "1.379um", "1", "reflectance"),
    5: ChannelInfo(5, "1.61um", "1", "reflectance"),
    6: ChannelInfo(6, "2.225um", "1", "reflectance"),
    7: ChannelInfo(7, "3.75um_high", "K", "brightness_temperature"),
    8: ChannelInfo(8, "3.75um_low", "K", "brightness_temperature"),
    9: ChannelInfo(9, "6.25um", "K", "brightness_temperature"),
    10: ChannelInfo(10, "6.95um", "K", "brightness_temperature"),
    11: ChannelInfo(11, "7.42um", "K", "brightness_temperature"),
    12: ChannelInfo(12, "8.55um", "K", "brightness_temperature"),
    13: ChannelInfo(13, "10.8um", "K", "brightness_temperature"),
    14: ChannelInfo(14, "12.0um", "K", "brightness_temperature"),
    15: ChannelInfo(15, "13.3um", "K", "brightness_temperature"),
}


def attr_scalar(attrs, name):
    value = attrs[name]
    if isinstance(value, np.ndarray):
        value = value.reshape(-1)[0].item()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def parse_channels(spec):
    selected = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            selected.extend(range(int(start), int(end) + 1))
        else:
            selected.append(int(part))

    unique = sorted(set(selected))
    invalid = [ch for ch in unique if ch not in CHANNELS]
    if invalid:
        raise ValueError(f"Unsupported channel numbers: {invalid}")
    return unique


def channel_wavelengths(channel_numbers):
    return ",".join(CHANNELS[ch].wavelength for ch in channel_numbers)


def channel_units(channel_numbers):
    return ",".join(CHANNELS[ch].unit for ch in channel_numbers)


def common_attrs(hdf, source_file):
    return {
        "source_file": str(source_file),
        "satellite": str(attr_scalar(hdf.attrs, "Satellite Name")),
        "sensor": str(attr_scalar(hdf.attrs, "Sensor Name")),
        "nominal_center_longitude": float(attr_scalar(hdf.attrs, "NOMCenterLon")),
        "observing_beginning_date": str(attr_scalar(hdf.attrs, "Observing Beginning Date")),
        "observing_beginning_time": str(attr_scalar(hdf.attrs, "Observing Beginning Time")),
        "observing_ending_date": str(attr_scalar(hdf.attrs, "Observing Ending Date")),
        "observing_ending_time": str(attr_scalar(hdf.attrs, "Observing Ending Time")),
    }

