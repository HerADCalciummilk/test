# 命令行（在本包目录执行，省略的数值参数读 resource/fusion.ini）：
# python -m cli --module idw_delta --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc

if __name__ == "__main__":
    import meteva_base as meb
    import numpy as np
    from datetime import datetime, timedelta
    from nimm.sta_grid_interp.interp_sg_idw_delta_plugin import InterpSgIdwDelta

    sta = meb.read_stadata_from_csv(r'/data/code/nimm/demo_data/input/sta_grid_interp/sta.csv')
    #print(sta)

    grid = meb.read_griddata_from_nc(r'/data/code/nimm/demo_data/input/sta_grid_interp/grid.nc')
    #print(grid)

    grid_info = meb.get_grid_of_data(grid)
    #print(grid_info)

    result = InterpSgIdwDelta().process(sta, grid)
    print(result)
