# 命令行（在本包目录执行，省略的数值参数读 resource/conf.ini）：
# python -m cli --module idw_delta --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc

if __name__ == "__main__":
    import meteva_base as meb
    from interp_sg_idw_plugin import InterpSgIdw

    sta = meb.read_stadata_from_csv(r"/data/code/nimm/demo_data/input/sta_grid_interp/sta.csv")
    grid = meb.read_griddata_from_nc(r"/data/code/nimm/demo_data/input/sta_grid_interp/grid.nc")
    grid_info = meb.get_grid_of_data(grid)

    result = InterpSgIdw(gaussian=True).process(sta, grid_info, background=grid)
    print(result)
