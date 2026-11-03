import meteva_base as meb
#import meteva

import datetime
import pandas as pd
import os

import numpy as np
import os
import datetime
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
import copy



###### 全局变量




###### 功能函数
######### 网格站点融合技术  #########
## 简单版
def interp_sg_delta_gaussian(sta0, grid0,  halfR=20):
    import meteva
    from scipy.spatial import cKDTree
    ## sta0:  站点数据
    ## grid0:  格点数据，有背景场
    ## halfR: 高斯半径(站点偏差影响附近网格的范围)
    sta = meteva.base.sele_by_para(sta0,drop_IV=True)
    grid2 = meteva.base.get_grid_of_data(grid0)##格点信息
    sta.iloc[:,-1] = sta.iloc[:,-1]-meb.interp_gs_linear(grid0, sta).iloc[:,-1]##站点与对应网格偏差
#     meb.plot_tools.scatter_sta(sta)
    # 偏差扩散至周围网格
    data_name = meteva.base.get_stadata_names(sta)
    xyz_sta = meteva.base.tool.math_tools.lon_lat_to_cartesian(sta['lon'].values,
                                                                                sta['lat'].values,
                                                                                R=meteva.base.basicdata.const.ER)##站点
    lon = np.arange(grid2.nlon) * grid2.dlon + grid2.slon
    lat = np.arange(grid2.nlat) * grid2.dlat + grid2.slat
    grid_lon, grid_lat = np.meshgrid(lon, lat)
    xyz_grid = meteva.base.tool.math_tools.lon_lat_to_cartesian(grid_lon.flatten(),
                                                                                 grid_lat.flatten(),
                                                                                 R=meteva.base.basicdata.const.ER)##网格点
    tree = cKDTree(xyz_sta)##站点索引树，找离站点最近的格点
    # d,inds 分别是站点到格点的距离和id
    d, inds = tree.query(xyz_grid, k=1)##返回每个格点最近的nearNum个站点
    ## 格站偏差向周围高斯扩散
    input_dat = sta.iloc[:,-1].values
    w2 = np.exp(-(d/halfR)**2)
    dat = w2 * input_dat[inds]
    dat[d>halfR]=0
#     print(input_dat.shape, inds.shape, d.shape)
    dat = dat.astype(np.float32)
    grd_delta = meteva.base.basicdata.grid_data(grid2, dat)#网格偏差
#     meb.plot_tools.contourf_2d_grid(grd_delta)
    grd_final = grid0.copy()
    grd_final.values = grd_final.values + grd_delta.values
    grd_final.name = "data0"
    return grd_final


## 多站点插值版，无背景场
def interp_sg_idw(sta0, grid, effectR=1000, nearNum=8,decrease = 2):
    ## sta0:  站点数据
    ## grid:  格点信息类，无背景场
    ## effectR: 反距离权重最大距离范围

    sta1 = meb.sele_by_para(sta0,drop_IV=True)
    sta_list = meb.split(sta1,["member","level","time","dtime"])
    grd_list = []
    for sta in sta_list:
        data_name = meb.get_stadata_names(sta)
        index0 = sta.index[0]
        dtime = sta.loc[index0, 'dtime'].astype(int)
        level = sta.loc[index0, 'level'].astype(int)
        grid2 = meb.basicdata.grid(grid.glon, grid.glat, [sta.loc[index0, 'time']],
                                                           [dtime],
                                                           [level], data_name)
        xyz_sta = meb.tool.math_tools.lon_lat_to_cartesian(sta['lon'].values,
                                                                                    sta['lat'].values,
                                                                                    R=meb.basicdata.const.ER)
        lon = np.arange(grid2.nlon) * grid2.dlon + grid2.slon
        lat = np.arange(grid2.nlat) * grid2.dlat + grid2.slat
        grid_lon, grid_lat = np.meshgrid(lon, lat)
        xyz_grid = meb.tool.math_tools.lon_lat_to_cartesian(grid_lon.flatten(),
                                                                                     grid_lat.flatten(),
                                                                                     R=meb.basicdata.const.ER)
        tree = cKDTree(xyz_sta)
        # d,inds 分别是站点到格点的距离和id
        if nearNum > len(sta.index):
            nearNum = len(sta.index)
        d, inds = tree.query(xyz_grid, k=nearNum)
        if nearNum >1:
            d += 1e-6
            w = 1.0 / d ** decrease
            input_dat = sta.values[:,-1]
            dat = np.sum(w * input_dat[inds], axis=1) / np.sum(w, axis=1)
            bg = meb.basicdata.grid_data(grid2)
            bg_dat = bg.values.flatten()
            dat = np.where(d[:, 0] > effectR, bg_dat, dat)
        else:
            input_dat = sta.iloc[:,-1].values
            dat = input_dat[inds]
            bg = meb.basicdata.grid_data(grid2)
            bg_dat = bg.values.flatten()
            dat = np.where(d[:] > effectR, bg_dat, dat)
        dat = dat.astype(np.float32)
        grd = meb.basicdata.grid_data(grid2, dat)
        grd.name = data_name[0]
        grd_list.append(grd)

    grd_all = meb.concat(grd_list)
    return grd_all

## 多站点插值版,有背景场，格站融合
def interp_sg_idw_delta(sta0, grid0, effectR =1000, nearNum=8,decrease = 2):
    import meteva
    from scipy.spatial import cKDTree
    ## sta0:  站点数据
    ## grid0:  格点数据，有背景场
    ## effectR: 高斯半径(站点偏差影响附近网格的范围)
    sta = meteva.base.sele_by_para(sta0,drop_IV=True)
    grid2 = meteva.base.get_grid_of_data(grid0)##格点信息
    sta.iloc[:,-1] = sta.iloc[:,-1]-meb.interp_gs_linear(grid0, sta).iloc[:,-1]##站点与对应网格偏差    
    # 偏差扩散至周围网格    
    data_name = meteva.base.get_stadata_names(sta)
    index0 = sta.index[0]
    xyz_sta = meteva.base.tool.math_tools.lon_lat_to_cartesian(sta['lon'].values,
                                                                                sta['lat'].values,
                                                                                R=meteva.base.basicdata.const.ER)##站点
    lon = np.arange(grid2.nlon) * grid2.dlon + grid2.slon
    lat = np.arange(grid2.nlat) * grid2.dlat + grid2.slat
    grid_lon, grid_lat = np.meshgrid(lon, lat)
    xyz_grid = meteva.base.tool.math_tools.lon_lat_to_cartesian(grid_lon.flatten(),
                                                                                 grid_lat.flatten(),
                                                                                 R=meteva.base.basicdata.const.ER)##网格点
    tree = cKDTree(xyz_sta)##站点索引树，找离站点最近的格点
    # d,inds 分别是站点到格点的距离和id
    if nearNum > len(sta.index):
        nearNum = len(sta.index)
    d, inds = tree.query(xyz_grid, k=nearNum)##返回每个格点最近的nearNum个站点
    if nearNum >1:
        d += 1e-6
        w1 = 1.0 / d ** decrease
        w2 = np.exp(-(d/effectR)**2)
        input_dat = sta.values[:,-1]
        dat = np.sum(w1 * w2 * input_dat[inds], axis=1) / np.sum(w1, axis=1)
    else:
        input_dat = sta.iloc[:,-1].values
        w2 = np.exp(-(d/effectR)**2)
        dat = w2 * input_dat[inds]
        dat[d>effectR]=0
    dat = dat.astype(np.float32)
    grd_delta = meteva.base.basicdata.grid_data(grid2, dat)#网格偏差
    grd_final = grid0.copy()
    grd_final.values = grd_final.values + grd_delta.values
    grd_final.name = "data0"
    return grd_final


## 综合站点到格点插值
def interp_sg_total(sta, to_grid, grid_background=None, **args):
    ## sta0  站点数据
    ## to_grid:  格点信息类
    ## grid_background: 背景场，默认为0
    ## 其他参数： effectR=1000, nearNum=8,decrease = 2
    ## 无背景场时， 直接反距离插值；   有背景场时，使用站点格点误差扩散及反距离插值
    if grid_background is None:
        grid = interp_sg_idw(sta, to_grid, **args)
    else:
        grid_background = meb.interp_gg_linear(grid_background, grid=to_grid)
        grid = interp_sg_idw_delta(sta, grid0=grid_background, effectR =1000, nearNum=8,decrease = 2)
    return(grid)


def get_stadata_from_df(filename, var_name='TEM_Avg'):
    ## 常规要素读取，返回meteva.stadata数据
    """
    要素列表['PRS_Avg', 'PRS_Sea_Avg', 'WIN_S_Inst_Max', 'WIN_S_2mi_Avg',
       'TEM_Avg', 'TEM_Max', 'TEM_Min', 'RHU_Avg', 'RHU_Min',
       'PRE_Time_2020', 'PRE_Time_0808']
    """
    sta_all = pd.read_hdf(filename, 'df')
    sta_temp = sta_all.loc[:, ['Lon','Lat','Datetime','Station_Id_d',var_name]]
    sta = meb.sta_data(sta_temp, columns=['lon','lat','time','id','data0'])
    sta.level = 0
    sta.dtime = 0
    sta = sta.dropna(axis=0, subset=['data0'])
    return sta

### 流程搭建
def interp_gs_process0(sta_fmt, to_fmt, time, var_name='TEM_Avg',show=False):
    ### 从逐日站点数据DataFrame中，生成格点插值流程
    ### 网格化，经纬度范围
    glon = [85, 105, 0.05]
    glat = [20, 40, 0.05]
    grid_file = meb.get_path(to_fmt, time=time+datetime.timedelta(hours=8), dt=0)
    
    if os.path.exists(grid_file):
        return None
    sta_file = meb.get_path(sta_fmt, time=time, dt=0)
    if not os.path.exists(sta_file):
        print("sta_file not existed: {0}".format(sta_file))
        return None
    if show: print(sta_file)
    sta = get_stadata_from_df(sta_file, var_name=var_name)
    to_grid = meb.grid(glon=glon, glat=glat)
    grid = interp_sg_total(sta, to_grid)

    grid_file = meb.get_path(to_fmt, time=time+datetime.timedelta(hours=8), dt=0)
    meb.write_griddata_to_nc(grid, grid_file, effectiveNum=3, creat_dir=True)
    if show:
        # meb.plot_tools.scatter_sta(meb.sele_by_para(sta,lon=glon[0:2], lat=glat[0:2]))
        # meb.plot_tools.contourf_2d_grid(grid)
        print('File output:{}'.format(time))
    return None

def interp_gs_process1(sta_fmt, to_fmt, time, show=False):
    ### 从micaps3站点，生成格点插值流程
    ### 网格化，经纬度范围
    glon = [85, 105, 0.05]
    glat = [20, 40, 0.05]
    grid_file = meb.get_path(to_fmt, time=time, dt=0)
    
    if os.path.exists(grid_file):
        return None
    sta_file = meb.get_path(sta_fmt, time=time, dt=0)
    if not os.path.exists(sta_file):
        print("sta_file not existed: {0}".format(sta_file))
        return None
    if show: print(sta_file)
    sta = meb.read_stadata_from_micaps3(sta_file)

    to_grid = meb.grid(glon=glon, glat=glat)

    grid = interp_sg_total(sta, to_grid)
    grid_file = meb.get_path(to_fmt, time=time, dt=0)
    meb.write_griddata_to_nc(grid, grid_file, effectiveNum=3, creat_dir=True)
    if show:
        meb.plot_tools.scatter_sta(meb.sele_by_para(sta,lon=glon[0:2], lat=glat[0:2]))
        meb.plot_tools.contourf_2d_grid(grid)
        
    return None

def add_all_sta(sta_fmt, time, sumnum=24):
    sumlist = np.arange(sumnum)
    sta_sum = None
    for fh in sumlist:
        sta_file = meb.get_path(sta_fmt, time=time-datetime.timedelta(hours=int(fh)), dt=0)
        if not os.path.exists(sta_file):
            print("sta_file not existed: {0}".format(sta_file))
            continue
        if sta_sum is None:
            sta_sum = meb.read_stadata_from_micaps3(sta_file)
        else:
            sta_temp = meb.read_stadata_from_micaps3(sta_file)
            meb.set_stadata_coords(sta_temp, time=time)
            sta_sum = meb.add_on_level_time_dtime_id(sta_sum, sta_temp, how='outer',default=0)
    return sta_sum

def interp_gs_process_sum(sta_fmt, to_fmt, time, sumnum=24, show=False):
    ## sumnum: 过去累加的小时数
    ### 从micaps3站点，先累加，再生成格点插值流程
    grid_file = meb.get_path(to_fmt, time=time, dt=0)
    if os.path.exists(grid_file):
        return None

    ## 站点读取
    if show: print(time, meb.get_path(sta_fmt, time=time, dt=0))
    sta_sum = add_all_sta(sta_fmt, time, sumnum=24)

    ### 网格化
    glon = [85, 105, 0.05]
    glat = [20, 40, 0.05]
    to_grid = meb.grid(glon=glon, glat=glat)

    grid = interp_sg_total(sta_sum, to_grid)
    grid_file = meb.get_path(to_fmt, time=time, dt=0)
    meb.write_griddata_to_nc(grid, grid_file, effectiveNum=3, creat_dir=True)
    if show:
#         meb.plot_tools.scatter_sta(meb.sele_by_para(sta_sum,lon=glon[0:2], lat=glat[0:2]))
        meb.plot_tools.scatter_sta(meb.sele_by_para(sta_sum))
        meb.plot_tools.contourf_2d_grid(grid)
    return None


#####################工具类函数 #############
#### 时间相关操作函数
def get_date_from_str(input,get_datetime64=False):
    '''
    输入str/datetime64/datetime时，输出datetime或np.datetime（通过get_datetime64参数控制）
    '''
    if isinstance(input, int):##输入为数字时
        input = ''.join([x for x in input if x.isdigit()])
    if type(input) == str:## 输入为字符串
        num = ''.join([x for x in input if x.isdigit()])
        # 用户输入2019041910十位字符，后面补全加0000，为14位统一处理
        if len(num) == 4:
            num += "0101000000"
        elif len(num) == 6:
            num +="01000000"
        elif len(num) == 8:
            num +="000000"
        elif len(num) == 10:
            num +="0000"
        elif len(num) == 12:
            num +="00"
        else:
            print("输入日期有误，请检查！")
        # 统一将日期变为datetime类型
        stime = datetime.datetime.strptime(num, '%Y%m%d%H%M%S')#返回datetime
        if get_datetime64 :
            stime = np.datetime64(stime)#返回datetime64                
    elif isinstance(input,np.datetime64):## 输入为datetime64
        if get_datetime64:
            stime = input
        else:
            stime = input.astype(datetime.datetime)
            print("here",stime)
            if isinstance(stime, int):
                stime = datetime.datetime.utcfromtimestamp(stime / 1000000000)                
    elif isinstance(input, datetime.datetime):## 输入为datetime.datetime
        if get_datetime64:
            stime = np.datetime64(input)#返回datetime64
        else:
            stime = input
    return(stime)

def get_date_list_pd(gtime=['2020060700', '2020060712', 12], delta='H'):
    ## 获取多时间列表
    """
    gtime参数（start_date_str, end_date_str, hour_intervals）
    """
    num1 =[]
    if type(gtime[0]) == str:
        for i in range (0,2):
            num = ''.join([x for x in gtime[i] if x.isdigit()])
            num1.append(get_date_from_str(num))
        stime = np.datetime64(num1[0])
        etime = np.datetime64(num1[1])
    else:
        stime = gtime[0]
        etime = gtime[1]
    times = pd.date_range(stime, etime, freq=str(gtime[2])+delta)
    return(times.to_pydatetime())#返回datetime类型数组

#### 并行计算函数
def split_list_equal(list0, n):
    ## list0等分，每份n个
    for i in range(0, len(list0),n):
        yield list0[i:i+n]

def split_list_nlist(list0, n):
    ## list0等分为n组
    if len(list0)%n == 0:
        cnt = len(list0)//n
    else:
        cnt = len(list0)//n+1
    for i in range(0,n):
        yield list0[i*cnt : (i+1)*cnt]

def multi_pool_cal(operation, input, pro_count):
    ## operation为待并行函数，参数为列表(list)
    ## input为某参数列表， pro_count为进程数
    ## 根据pro_count自动将input切分为等长的n份，作为并行参数
    from multiprocessing import Pool
    processes_pool = Pool(pro_count)
    input = split_list_nlist(input, pro_count)
    input_list = []
    for i in input:
        input_list.append(list(i))
    #print(input_list)
    # 开始并行
    processes_pool.map(operation, input_list)
    return None


def multi_model_process(model, datelist, n_pools = 6):
    ## 有数据返回的并行调度
    from multiprocessing import Pool
    results=[]
    datelist_mpi = list(split_list_nlist(datelist, n_pools))#大list平分为若干小list
    mp = Pool(n_pools)
    for dtlist in datelist_mpi:
        dtlist = dtlist
        print(dtlist)
        res = mp.apply_async(model.process, args=(dtlist,))
        results.append(res)
    mp.close()
    mp.join()
    a = []
    # 数据整理,apply_async()组织数据
    a = [i.get() for i in results]
    results = pd.concat(a, axis=0)
    return(results)


class interp_sg(object):
    def __init__(self, times, sta_fmt, to_fmt, var_dict=None, show=False):
        self.times = times
        self.sta_fmt = sta_fmt
        self.to_fmt = to_fmt
        self.var_dict = var_dict
        self.show = show

    def process(self, var_names):
        times = self.times
        sta_fmt = self.sta_fmt##读取文件fmt
        for var_name in var_names:
            to_var_name = self.var_dict.get(var_name)
            to_fmt = self.to_fmt.format(to_var_name)##输出文件fmt
            if to_var_name is None:
                continue
            for i,time in enumerate(times):
                if i%500==0: show=True
                interp_gs_process0(sta_fmt, to_fmt, time, var_name=var_name, show=self.show )##执行interp_SG
        return None





if __name__ == "__main__":

    # ## 01 Read micaps3 data and interpolating（station->grid）
    # times = get_date_list_pd(gtime=['2019010108','2023030108',24],delta='H')
    # sta_fmt = r"\\10.28.16.234\data2\temp\230224_guizhou\obs\00_daily_spe\ssh0\YYYY\YYYYMMDDHH.TTT"
    # to_fmt = r"\\10.28.16.234\data2\temp\230224_guizhou\obs\01_grid_daily\1_ssh\YYYY\YYYYMMDDHH.000.nc"
    # for i,time in enumerate(times):
    #     show = False
    #     interp_gs_process1(sta_fmt, to_fmt, time, show=show)

    # ## 02 Read DataFrame Daily data and interpolating（station->grid）
    times = get_date_list_pd(gtime=['2014010100','2023030100',24],delta='H')

    var_dict = {
        'TEM_Max':'0_2tmax',
        'TEM_Avg':'0_2tmean',
        'TEM_Min':'0_2tmin',
        'PRS_Sea_Avg':'0_mslp',
        'RHU_Avg':'0_rh',
        'PRE_Time_0808':'0_tp',
        'WIN_S_2mi_Avg':'0_winds',
        'WIN_S_Inst_Max':'0_gust',
    }#    
    """
    要素列表['PRS_Avg', 'PRS_Sea_Avg', 'WIN_S_Inst_Max', 'WIN_S_2mi_Avg',
       'TEM_Avg', 'TEM_Max', 'TEM_Min', 'RHU_Avg', 'RHU_Min',
       'PRE_Time_2020', 'PRE_Time_0808']
    """


    var_names = list(var_dict.keys())# all VARS
    # var_names = ['TEM_Max','TEM_Avg','TEM_Min']

    INTERP_SG = interp_sg(times=times, 
                    sta_fmt=r"\\10.28.16.234\data2\temp\230224_guizhou\obs\00_daily\YYYYMMDDHH.h5", 
                    to_fmt=r"\\10.28.16.234\data2\temp\230224_guizhou\obs\01_grid_daily\{0}\YYYY\YYYYMMDDHH.000.nc", 
                    var_dict=var_dict, show=True,
                    )## Interp class


    par_num = 8 #multiprocess Num
    if len(var_names)>=3 and par_num>1:
        ## 并行计算
        print("MULTIPROCESSING:  ProcessNUM = {0}".format(par_num))
        multi_pool_cal(INTERP_SG.process, var_names, par_num)
    else:
        ## 单进程计算
        print("SINGLEPROCESSING:")
        INTERP_SG.process(var_names=var_names)
        
    pass




