# 命令行（在本包目录执行）：
# python -m cli --module nearest --grid ... --domain 20,50,70,140,0.1,0.1 --outer-value 0
# python -m cli --module cubic --grid ... --domain 20,50,70,140,0.1,0.1 --outer-value 0

if __name__ == "__main__":
    import meteva_base as meb
    from interp_gg_cubic_plugin import InterpGgCubic
    from interp_gg_nearest_plugin import InterpGgNearest

    grd = meb.read_griddata_from_nc(r"/data/code/nimm/demo_data/input/sta_grid_interp/grid.nc")
    grid = meb.basicdata.grid([70, 140, 0.25], [15, 55, 0.25])
    print(InterpGgNearest(outer_value=0.0).process(grd, grid))
    print(InterpGgCubic(outer_value=0.0).process(grd, grid))
