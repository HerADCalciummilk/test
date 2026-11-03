import numpy as np
from scipy import ndimage


def read_calibrated_channel(hdf, channel_number):
    suffix = f"{channel_number:02d}"
    dn = hdf[f"Data/NOMChannel{suffix}"][()]
    cal = hdf[f"Calibration/CALChannel{suffix}"][()]
    values = np.full(dn.shape, np.nan, dtype=np.float32)
    valid = dn <= 4095
    values[valid] = cal[dn[valid]]
    return values


def sample_to_latlon(source, src_line, src_col, visible, method):
    if method == "nearest":
        row = np.rint(src_line).astype(np.int32)
        col = np.rint(src_col).astype(np.int32)
        sampled = np.full(src_line.shape, np.nan, dtype=np.float32)
        sampled[visible] = source[row[visible], col[visible]]
        return sampled

    sampled = ndimage.map_coordinates(
        source,
        np.array([src_line, src_col], dtype=np.float64),
        order=1,
        mode="constant",
        cval=np.nan,
        prefilter=False,
    ).astype(np.float32)
    sampled[~visible] = np.nan
    return sampled
