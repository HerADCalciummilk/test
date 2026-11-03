# resource (minimal runtime samples)

| path | note |
|------|------|
| `cli_input/input_landmask_meb.nc` | lat/lon meb6d landmask (`python -m cli landmask`) |
| `cli_input/input_orog_meb.nc` | lat/lon meb6d orography (`bands` / `weights`) |
| `cli_input/input_land_meb.nc` | lat/lon meb6d landmask for topography CLIs |
| `cli_input/bounds_topography_bands.json` | thresholds for `bands` |
| `cli_input/bounds_topographic_zone_weights.json` | thresholds for `weights` |
| `cli_output/` | default outputs of each `main()` |

Entry (package root)::

    python -m cli              # list subcommands
    python -m cli landmask
    python -m cli bands
    python -m cli weights
