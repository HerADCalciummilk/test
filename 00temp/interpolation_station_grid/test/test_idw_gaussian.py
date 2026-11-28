# 命令行（在 00temp 目录执行，省略的参数读 resource/conf.ini）：
# python -m interpolation_station_grid method=gaussian sta=... grid=... gaussian_half_r=20
# 有背景：再加 background=...

if __name__ == "__main__":
    import meteva_base as meb
    from interp_sg_gaussian_plugin import InterpSgGaussian

    sta = meb.read_stadata_from_csv(r"/data/code/nimm/demo_data/input/sta_grid_interp/sta.csv")
    grid = meb.read_griddata_from_nc(r"/data/code/nimm/demo_data/input/sta_grid_interp/grid.nc")
    grid_info = meb.get_grid_of_data(grid)

    result = InterpSgGaussian(halfR=20).process(sta, grid_info, background=grid)
    print(result)
