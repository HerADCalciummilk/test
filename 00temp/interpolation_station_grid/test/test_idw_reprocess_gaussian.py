# 原 idw_delta 的等价写法（idw 绝对值 / 偏差路径与高斯权重相互独立，需显式组合）：
# 命令行（在 00temp 目录执行）：
#   python -m interpolation_station_grid method=idw idw_gaussian=true reprocess=true background=...

if __name__ == "__main__":
    import meteva_base as meb
    from interp_sg_plugin import InterpSg

    sta = meb.read_stadata_from_csv(r"/data/code/nimm/demo_data/input/sta_grid_interp/sta.csv")
    grid = meb.read_griddata_from_nc(r"/data/code/nimm/demo_data/input/sta_grid_interp/grid.nc")
    grid_info = meb.get_grid_of_data(grid)

    result = InterpSg(
        method="idw", gaussian=True, reprocess=True, effectR=1000, nearNum=8, decrease=2
    ).process(sta, grid_info, background=grid)
    print(result)
