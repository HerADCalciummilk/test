# resource (minimal runtime samples)

| path | note |
|------|------|
| `cli_input/input_surface_altitude_meb.nc` | lat/lon meb6d；clearsky 作海拔/目标网格，solar-time 作目标网格（共用） |
| `cli_input/input_linke_turbidity_meb.nc` | lat/lon meb6d Linke turbidity（clearsky） |
| `cli_output/` | default outputs of each `main()` |

Entry (package root)::

    python -m cli              # list subcommands
    python -m cli clearsky
    python -m cli solar-time
