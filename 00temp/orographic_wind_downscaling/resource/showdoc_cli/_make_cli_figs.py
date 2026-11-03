from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import xarray as xr
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name
from meteva_base.tool.plot_tools import pcolormesh_2d_grid

from orographic_wind_downscaling.cli.dsc_wind_downscaling import process

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

pkg = Path(__file__).resolve().parents[2]
root = pkg / "resource" / "data"
crop = root / "example_crop"
out_dir = Path(__file__).resolve().parent
out_dir.mkdir(parents=True, exist_ok=True)
(root / "cli_output").mkdir(parents=True, exist_ok=True)

with xr.open_dataset(crop / "wind_speed.nc") as ds:
    wind = ds[next(iter(ds.data_vars))].load()

result = process(
    str(crop / "wind_speed.nc"),
    str(crop / "sigma.nc"),
    str(crop / "target_orography.nc"),
    str(crop / "standard_orography.nc"),
    str(crop / "silhouette_roughness.nc"),
    20000.0,
    vegetative_roughness_path=str(crop / "vegetative_roughness.nc"),
    output_path=str(root / "cli_output" / "wind_2026083100_10m.nc"),
    output_height_level=10.0,
)
print(result)

before = wind.isel(level=0) if "level" in wind.dims else wind
after = result
cmap, clevs = get_cmap_and_clevs_by_element_name("wind_speed")
kw = dict(cmap=cmap, clevs=list(clevs), add_county_line=False, add_worldmap=False, show=False)
pcolormesh_2d_grid(before, save_path=str(out_dir / "cli_wind_10m_before.png"), title="10 m 风速-订正前", **kw)
pcolormesh_2d_grid(after, save_path=str(out_dir / "cli_wind_10m_after.png"), title="10 m 风速-订正后", **kw)
print("wrote", out_dir / "cli_wind_10m_before.png")
print("wrote", out_dir / "cli_wind_10m_after.png")
