# 命令行（在本包目录执行，省略的数值参数读 resource/fusion.ini）：
# python -m cli --module gaussian --sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv --grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc --half-r 20

if __name__ == "__main__":
    import meteva_base as meb
    import numpy as np
    from datetime import datetime, timedelta
    from nimm.sta_grid_interp.interp_sg_delta_gaussian_plugin import InterpSgDeltaGaussian

    sta = meb.read_stadata_from_csv(r'/data/code/nimm/demo_data/input/sta_grid_interp/sta.csv')
    #print(sta)

    grid = meb.read_griddata_from_nc(r'/data/code/nimm/demo_data/input/sta_grid_interp/grid.nc')
    #print(grid)

    grid_info = meb.get_grid_of_data(grid)
    #print(grid_info)

    result = InterpSgDeltaGaussian().process(sta, grid)
    print(result)
