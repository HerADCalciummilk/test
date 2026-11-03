import numpy as np

from .metadata import attr_scalar


def latlon_to_fy4_grid(lat2d, lon2d, lon0, attrs):
    """Convert geodetic lat/lon to FY-4 AGRI nominal full-disk line/column."""
    req = float(attr_scalar(attrs, "Semimajor axis of ellipsoid"))
    rpol = float(attr_scalar(attrs, "Semiminor axis of ellipsoid"))
    h = float(attr_scalar(attrs, "NOMSatHeight"))
    step = float(attr_scalar(attrs, "dSamplingAngle")) * 1e-6
    n = int(float(attr_scalar(attrs, "RegWidth")))
    center = (n - 1) / 2.0

    lat = np.deg2rad(lat2d)
    lon = np.deg2rad(lon2d)
    sub_lon = np.deg2rad(lon0)
    dlon = lon - sub_lon
    dlon = (dlon + np.pi) % (2 * np.pi) - np.pi

    phi_c = np.arctan((rpol * rpol / (req * req)) * np.tan(lat))
    cos_phi_c = np.cos(phi_c)
    re = rpol / np.sqrt(1.0 - ((req * req - rpol * rpol) / (req * req)) * cos_phi_c * cos_phi_c)

    r1 = h - re * cos_phi_c * np.cos(dlon)
    r2 = -re * cos_phi_c * np.sin(dlon)
    r3 = re * np.sin(phi_c)
    rn = np.sqrt(r1 * r1 + r2 * r2 + r3 * r3)

    x = np.arctan2(-r2, r1)
    y = np.arcsin(-r3 / rn)

    col = center + x / step
    line = center + y / step

    visible = (h * (h - r1)) >= (req * req)
    visible &= line >= 0
    visible &= line <= n - 1
    visible &= col >= 0
    visible &= col <= n - 1
    return line, col, visible


def fy4_grid_to_latlon(attrs):
    """Convert FY-4 AGRI fixed-grid line/column centers to geodetic lat/lon."""
    req = float(attr_scalar(attrs, "Semimajor axis of ellipsoid"))
    rpol = float(attr_scalar(attrs, "Semiminor axis of ellipsoid"))
    h = float(attr_scalar(attrs, "NOMSatHeight"))
    lon0 = np.deg2rad(float(attr_scalar(attrs, "NOMCenterLon")))
    step = float(attr_scalar(attrs, "dSamplingAngle")) * 1e-6
    width = int(float(attr_scalar(attrs, "RegWidth")))
    height = int(float(attr_scalar(attrs, "RegLength")))
    center_col = (width - 1) / 2.0
    center_line = (height - 1) / 2.0

    lines = np.arange(height, dtype=np.float64)
    cols = np.arange(width, dtype=np.float64)
    x = (cols - center_col) * step
    y = (lines - center_line) * step
    x2d, y2d = np.meshgrid(x, y)

    cos_x = np.cos(x2d)
    sin_x = np.sin(x2d)
    cos_y = np.cos(y2d)
    sin_y = np.sin(y2d)
    a2_b2 = (req * req) / (rpol * rpol)

    sd_term = (h * cos_x * cos_y) ** 2 - (cos_y * cos_y + a2_b2 * sin_y * sin_y) * (h * h - req * req)
    visible = sd_term >= 0

    sd = np.sqrt(np.maximum(sd_term, 0.0))
    sn = (h * cos_x * cos_y - sd) / (cos_y * cos_y + a2_b2 * sin_y * sin_y)
    s1 = h - sn * cos_x * cos_y
    s2 = sn * sin_x * cos_y
    s3 = -sn * sin_y

    lon = lon0 + np.arctan2(s2, s1)
    lat = np.arctan(a2_b2 * s3 / np.sqrt(s1 * s1 + s2 * s2))
    lon = np.rad2deg(lon).astype(np.float32)
    lat = np.rad2deg(lat).astype(np.float32)
    lon[~visible] = np.nan
    lat[~visible] = np.nan
    return lat, lon, visible

