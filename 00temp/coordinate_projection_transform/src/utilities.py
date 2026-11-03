# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2022， CMA National Meteorological Centre.
# All rights reserved.
#
# Distributed under the terms of the GPL v2 License.
#


"""General NIMM metadata utilities"""
import iris
import numpy as np
import xarray as xa
import meteva_base as meb
import datetime

import os
import cartopy.crs as ccrs
import scipy



def simple_pic_iris(cube):
    """
    plot a simple visualization of cube data
    """
    import matplotlib.pyplot as plt
    import iris.plot as iplt
    import iris.quickplot as qplt
    plt.figure(figsize=(16, 9))
    qplt.contourf(cube,25)
    ax = plt.gca()
    ax.coastlines()
    ax.gridlines()
    iplt.show()
    return None


def cal_validtime_from_meteva_griddata(xa_data, bounds=None):
    """
    提取二维(只有经纬度)xarray的时间维度相关(起报时间、预报时效)信息, 包括time, forecast_reference_time等.
    Args:
        xa_data (xarray.da): 
            xarray data read by METEVA.BASE.
        bounds: list（length=2）,Lower and upper point related to time. eg:past 1h percipitation bounds=[-1,0] 
    Return:
        time: valid time
        frt: forecast reference time
        time_bounds: Lower and upper bound on time point, if required. default None
    """

    try:
        dtime_type = xa_data.attrs['dtime_type']
    except:
        dtime_type = 'hour'

    ## frt
    xa_frt = meb.all_type_time_to_datetime(xa_data.time.values[0])
    ## time
    dtime = xa_data.dtime.values[0]#dtime, 单变量
    if dtime_type == 'hour':
        xa_valid_time = xa_frt + datetime.timedelta(hours=int(dtime))#小时间隔
    else:
        xa_valid_time = xa_frt + datetime.timedelta(minutes=int(dtime))#分钟级间隔
    
    ## time_bounds
    time_bounds = None
    if bounds is not None:
        if dtime_type == 'hour':#小时
            low = xa_valid_time + datetime.timedelta(hours=int(bounds[0]))#时间下限
            upper = xa_valid_time + datetime.timedelta(hours=int(bounds[1]))#时间上限
        else:#分钟
            low = xa_valid_time + datetime.timedelta(minutes=int(bounds[0]))#时间下限
            upper = xa_valid_time + datetime.timedelta(minutes=int(bounds[1]))#时间上限            
        time_bounds = [low, upper]
    return(xa_valid_time, xa_frt, time_bounds)




############ 基于NIMM的不同投影转换，生成numpy数组 ############
def _projdict_to_meteva_gridinfo(proj_dict,  times = [datetime.datetime(2022,2,1,0)],dtimes = [24],levels= [2],members = None):
    """
    将投影(等经纬度)信息字典proj_grid_dict 转为 meteva.grid类并输出
    信息字典proj_grid_dict={ 'dlon':10000, 'dlat':10000, #数据xy间隔(等经纬度单位°，等距单位m)
                'slon':70, 'slat':0, #起始点经纬度(ccrs.PlateCarree()中对应起始点坐标)
                'nlon':701,'nlat':601 #x/y方向格点数
                'spatial_grid':'latlon' # 转换为等经纬度投影('latlon')
                }"""
    if not isinstance(proj_dict, dict):
        raise IOError('Meteva.grid to proj_dict ERROR:  INPUT must be DICT')
    if proj_dict.get('spatial_grid')=='equalarea':
        raise IOError('proj_dict to Meteva.grid ERROR:  spatial_grid must be one of latlon')
    try:
        gridinfo = meb.grid(glon=[proj_dict['slon'],proj_dict['slon']+proj_dict['dlon']*(proj_dict['nlon']-1) ,proj_dict['dlon']], 
                                glat=[proj_dict['slat'],proj_dict['slat']+proj_dict['dlat']*(proj_dict['nlat']-1),proj_dict['dlat']],
                                gtime=times, dtime_list=dtimes,
                                level_list=levels, member_list=members)
        return(gridinfo)
    except Exception as err:
        print(err)
        return None

def _meteva_gridinfo_to_projdict(gridinfo):
    """
    将meteva.grid类 转为 投影(等经纬度)信息字典proj_grid_dict并输出
    return: 信息字典proj_grid_dict={ 'dlon':10000, 'dlat':10000, #数据xy间隔(等经纬度单位°，等距单位m)
                'slon':70, 'slat':0, #起始点经纬度(ccrs.PlateCarree()中对应起始点坐标)
                'nlon':701,'nlat':601 #x/y方向格点数
                'spatial_grid':'latlon' # 转换为等经纬度投影('latlon')
                }"""
    if not isinstance(gridinfo, meb.grid):
        raise IOError('Meteva.grid to proj_dict ERROR:  INPUT must be Meteva.grid class')
    proj_dict = {}
    proj_dict['dlon'] = gridinfo.dlon
    proj_dict['dlat'] = gridinfo.dlat
    proj_dict['slon'] = gridinfo.slon
    proj_dict['slat'] = gridinfo.slat
    proj_dict['elon'] = gridinfo.elon
    proj_dict['elat'] = gridinfo.elat
    proj_dict['nlon'] = gridinfo.nlon
    proj_dict['nlat'] = gridinfo.nlat
    proj_dict['spatial_grid'] = 'latlon'
    return(proj_dict)



## 不同网格转为等距，分别计算xy
def _cal_gridxy_lonlat(proj_i, proj_dict):
    ## 根据等经纬度网格信息，在等距投影上，生成等距xaxis和yaxis.
    ## Args: proj_dict  投影网格信息，可以是proj_dict投影网格字典 或者 meteva.grid网格信息类
    ## return(x, y)等经纬度网格

    row = proj_dict['nlat']
    col = proj_dict['nlon']
    lats = np.linspace(proj_dict['slat'], proj_dict['slat']+proj_dict['dlat']*(proj_dict['nlat']-1), num=row)
    lons = np.linspace(proj_dict['slon'], proj_dict['slon']+proj_dict['dlon']*(proj_dict['nlon']-1), num=col)
    lons,lats = np.meshgrid(lons,lats)#等经纬度meshgrid后lon/lat二维数组
    xy_lonlat = proj_i.transform_points(src_crs=ccrs.PlateCarree(), x=lons, y=lats)#投影至lambert,得到对应格点xy
    x = xy_lonlat[:,:,0]
    y = xy_lonlat[:,:,1]
    return(x,y)


def _cal_gridxy_lambert(proj_i, proj1_grid_dict):
    ## 根据等距网格信息，在等距投影上，生成等距xaxis和yaxis.
    ## return(x, y)等距网格
    lambert_slon = proj1_grid_dict['slon']
    lambert_slat = proj1_grid_dict['slat']
    distance_x = proj1_grid_dict['dlon']
    distance_y = proj1_grid_dict['dlat']
    start_x, start_y = proj_i.transform_point(lambert_slon, lambert_slat, src_crs=ccrs.PlateCarree()) #起始点相对xy距离,单点
    x = np.arange(0, 0+(proj1_grid_dict['nlon'])*distance_x, distance_x)+start_x
    y = np.arange(0, 0+(proj1_grid_dict['nlat'])*distance_y, distance_y)+start_y
    x,y = np.meshgrid(x, y)#meshgrid后二维xy方向相对距离数组
    return(x,y)

## kdtree邻近反距离插值，形成插值结果
def _xy_concat(x, y):
    #将meshgrid形式的x,y, 转化为散点数组形式
    return(np.concatenate([x.reshape(-1,1), y.reshape(-1,1)], axis=1))

def _near_value_kdtree(value, distance, near_distance=10000, def_val=np.NaN):
    #最邻近法,最大距离10000m
    dis_near = distance.copy()
    dis_near[dis_near>near_distance] = -1
    dis_near = dis_near[:,0]
    nearest = np.full(value.shape[0], fill_value=def_val, dtype=np.float32)
    nearest[dis_near>=0] = value[:,0][dis_near>=0]    
    return(nearest)

def _IDW_value_kdtree(value, distance, near_distance=20000, def_val=np.NaN):
    #反距离权重插值，最大距离20000m
    dis_idw = distance.copy()
    dis_idw[dis_idw>near_distance] = np.NaN
    weight = 1/np.square(dis_idw)
    total_weight = np.nansum(weight,axis=1)
    idw = np.nansum(value * weight,axis=1)/total_weight
    idw[distance[:,0]>near_distance] = def_val
    # print( idw[np.isnan(value).all(axis=1)].shape)
    idw[np.isnan(value).all(axis=1)] = def_val
    return(idw)


def interp_lambert2lonlat_kdtree(xy0, xy1, data0, def_val=np.NaN,
                                nearNum=3, nearDistance=20000):
    ##将data_lambert数据插值至lonlat网格点,kdtree寻找最邻近
    ##nearNum：每个点最邻近n个点； nearDistance：取邻近点时的最大距离
    raw_lambert_x = xy0[0]
    raw_lambert_y = xy0[1]
    x_lonlat = xy1[0]
    y_lonlat = xy1[1]
    data_lambert = data0
    # refTree
    ref_xyz = _xy_concat(raw_lambert_x, raw_lambert_y)
    tree = scipy.spatial.cKDTree(ref_xyz)
    # queryTree
    que_xyz = _xy_concat(x_lonlat, y_lonlat)
    distance, index = tree.query(que_xyz, k=nearNum)#最邻近n个点距离及索引数组
    # ref_values,最近n个点的值
    tempdata = data_lambert.flatten()
    ref_values = tempdata[index]
    ## a最邻近
    # new_arr = near_value_kdtree(ref_values, distance, def_val=def_val)
    # new_arr = new_arr.reshape(x_lonlat.shape)
    ## b反距离插值
    new_arr = _IDW_value_kdtree(ref_values, distance, near_distance=nearDistance, def_val=def_val)
    new_arr = new_arr.reshape(x_lonlat.shape)
    return(new_arr)



def proj_convert_kdtreeN(from_proj, from_grid_dict,
                        to_proj, to_grid_dict,
                        from_ndarray,
                        nearNum=3, nearDistance=20000,
                        ):
    """
    完成等经纬度与等距投影间的数据相互转换，输出转换后网格数据(数组)。
    from_proj/ to_proj: 待转换及转换到的投影坐标系， cartopy.ccrs类 https://scitools.org.uk/cartopy/docs/latest/reference/projections.html
    from_grid_dict/ to_grid_dict : 待转换及转换到的数据的网格信息，支持下列两者之一
                meteva网格信息类： meteva.grid class
                字典模板：grid_dict = { 'dlon':10000, 'dlat':10000, #数据xy间隔(等经纬度单位°，等距单位m)
                'slon':70, 'slat':0, #起始点经纬度(ccrs.PlateCarree()中对应起始点坐标)
                'nlon':701,'nlat':601 #x/y方向格点数
                'spatial_grid':'latlon' # 转换为等经纬度投影('latlon')或等距网格（'equalarea'）
                }#等距网格
    from_ndarray : 待转换的数组 np.ndarray
    nearNum/nearDistance: 插值参数，找目标格点最邻近nearNum个站点(最大距离nearDistance)
    return: 转换后的数据 np.ndarray
    """
    if isinstance(from_grid_dict, meb.grid):
        from_grid_dict = _meteva_gridinfo_to_projdict(from_grid_dict)
    if isinstance(to_grid_dict, meb.grid):
        to_grid_dict = _meteva_gridinfo_to_projdict(to_grid_dict)
    proj_list = ['latlon','equalarea']
    if from_grid_dict.get('spatial_grid')not in proj_list:
        raise IOError('INPUT proj_dict ERROR:  spatial_grid must be one of latlon/equalarea')
    if to_grid_dict.get('spatial_grid') not in proj_list:
        raise IOError('OUTPUT proj_dict ERROR:  spatial_grid must be one of latlon/equalarea')

    proj_standard = from_proj if from_grid_dict['spatial_grid']=='equalarea' else to_proj#选取等距网格为转换参考
    if from_grid_dict['spatial_grid']=='latlon':##由等经纬度转为等距 
        xy0 = _cal_gridxy_lonlat(proj_standard, from_grid_dict)#等经纬度xaxis/yaxis
        xy1 = _cal_gridxy_lambert(proj_standard, to_grid_dict)#等距xaxis/yaxis

    elif from_grid_dict['spatial_grid']=='equalarea': ##由等距转为等经纬度
        xy0 = _cal_gridxy_lambert(proj_standard, from_grid_dict)#等距xaxis/yaxis
        xy1 = _cal_gridxy_lonlat(proj_standard, to_grid_dict)#等经纬度xaxis/yaxis

    # print(from_grid_dict['spatial_grid']), print(to_grid_dict['spatial_grid'])
    ## 插值转换
    to_array = interp_lambert2lonlat_kdtree(xy0=xy0[0:2], xy1=xy1[0:2], data0=from_ndarray)
    return(to_array)


def _get_cube_coordname(cube):
    name_list=[]
    for coord in cube.coords():
        if isinstance(coord, iris.coords.DimCoord):
            name_list.append(coord.name())
    return(name_list)

def _get_cube_spatialgrid(cube):
    spatial_grid0 = 'latlon'
    try:
        if isinstance(cube.coord_system(), iris.coord_systems.GeogCS):
            spatial_grid0 = 'latlon'
        else:
            spatial_grid0 = 'equalarea'
        return spatial_grid0
    except Exception as err:
        print(err)
        return spatial_grid0


# from nimm.metadata.grid_info import GRID_COORD_ATTRIBUTES
def cube_dim_info_summary(cube):
    """
    返回CUBE对应的x/y维度网格信息(网格字典)
    """
    set_lat = {'lat','latitude','y','projection_y_coordinate'}
    set_lon = {'lon','longitude','x','projection_x_coordinate'}
    dim_set = set(_get_cube_coordname(cube))

    name_lon = dim_set.intersection(set_lon)
    if len(name_lon)<1 or len(name_lon)>2:
        raise ValueError('ERROR, longitude dim name in CUBE must be one of [lon, longitude, x, projection_x_coordinate]')
    else:
        name_lon = list(name_lon)[0]

    name_lat = dim_set.intersection(set_lat)
    if len(name_lat)<1 or len(name_lat)>2:
        raise ValueError('ERROR, latitude dim name in CUBE must be one of [lat,latitude,y,projection_y_coordinate]')
    else:
        name_lat = list(name_lat)[0]
    lons = cube.coord(name_lon).points
    lats = cube.coord(name_lat).points
    
    spatial_grid = _get_cube_spatialgrid(cube)
    try:
        dlon = round(lons[1] - lons[0], 3)
        dlat = round(lats[1] - lats[0], 3)
        nlon = len(lons)
        nlat = len(lats)

        if spatial_grid == 'equalarea':#slon/slat转为经纬度
            import cartopy.crs as ccrs
            coord_system = cube.coord(name_lat).coord_system
            PROJ_R = ccrs.PlateCarree()
            temp = PROJ_R.transform_point(src_crs=coord_system.as_cartopy_crs(), x=lons[0] , y=lats[0])
            slon = round(temp[0],3)
            slat = round(temp[1],3)
        elif spatial_grid == 'latlon':
            slon = lons[0]
            slat = lats[0]
        else:
            raise ValueError("spatial_grid should be one of latlon/equalarea")
        cube_info = {}
        cube_info['dlon'] = dlon
        cube_info['dlat'] = dlat
        cube_info['slon'] = slon
        cube_info['slat'] = slat
        cube_info['nlon'] = nlon
        cube_info['nlat'] = nlat
        cube_info['spatial_grid'] = spatial_grid
        return(cube_info)
    except Exception as err:
        print(err)
        return None







if __name__ == '__main__':
    # ### 01. cal_validtime_test
    # grd = meb.read_griddata_from_micaps4(r"\\10.20.90.107\sm_model\rain24\ecmwf\20230425\2023042500.036")
    # print(grd)
    # a = cal_validtime_from_meteva_griddata(grd, bounds=[-24, 0])
    # print(a)
    ### 02. proj_transform_test
    from nimm.metadata.grid_info import GRID_COORD_ATTRIBUTES
    proj0 = GRID_COORD_ATTRIBUTES['latlon']['coord_system'].as_cartopy_crs()
    proj1 = GRID_COORD_ATTRIBUTES['equalarea']['coord_system'].as_cartopy_crs()
    from_grid_dict  = { 'dlon':0.05, 'dlat':0.05, #数据xy间隔
                'slon':105, 'slat':20, #起始点经纬度定位
                'nlon':501,'nlat':301,
                'spatial_grid':'latlon' 
                }#等经纬度网格，距离单位°

    to_grid_dict = { 'dlon':5000, 'dlat':5000, #数据xy间隔
                'slon':105, 'slat':20, #起始点经纬度定位
                'nlon':501,'nlat':301,
                'spatial_grid':'equalarea' 
                }#等距网格，距离单位m，转换到的网格信息

    grid_info = meb.grid(glon=[105,130,0.05], glat=[20,35,0.05])##原始网格信息，略大于最终网格
    ## calculation
    file = r"\\10.10.31.84\qpe\QPE_10min\20230419\m10_202304190400.m4"#QPE
    grd = meb.read_griddata_from_micaps4(file,grid=grid_info)

    print(grd)
    grd.plot()
    data0 = proj_convert_kdtreeN(from_proj=proj0, from_grid_dict=grid_info,#grid_info/from_grid_dict
                                    to_proj=proj1, to_grid_dict=to_grid_dict, from_ndarray=grd.values.squeeze().astype(np.float32))
    print(data0, data0.shape)

    pass
