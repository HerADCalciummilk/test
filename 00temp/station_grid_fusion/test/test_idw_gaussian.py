# 命令行（在本包目录执行，省略的数值参数读 resource/conf.ini）：
# python -m cli --module gaussian --sta ... --grid ... --half-r 20
# 有背景：再加 --background ...

if __name__ == "__main__":
    import meteva_base as meb
    from interp_sg_delta_gaussian_plugin import InterpSgDeltaGaussian

    sta = meb.read_stadata_from_csv(r"/data/code/nimm/demo_data/input/sta_grid_interp/sta.csv")
    grid = meb.read_griddata_from_nc(r"/data/code/nimm/demo_data/input/sta_grid_interp/grid.nc")
    grid_info = meb.get_grid_of_data(grid)

    result = InterpSgDeltaGaussian(halfR=20).process(sta, grid_info, background=grid)
    print(result)
