# -*- coding: utf-8 -*-
"""meteva / Cube 辅助与 KDTree 投影工具（由 utilities + cube_base 合并）。

对外：
- ``process(method="meteva_to_cube"|"cube_to_meteva", ...)``
- ``proj_convert_kdtreeN``、``read_cube_from_meteva_griddata``、
  ``read_meteva_griddata_from_cube``、``set_up_var_cube`` 等函数仍可直接调用。
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

import cartopy.crs as ccrs
import iris
import meteva_base as meb
import numpy as np
import pandas as pd
import scipy
import xarray as xr
from cf_units import date2num
from iris.coords import Coord, DimCoord
from iris.cube import Cube
from numpy import ndarray

_PKG_ROOT = str(Path(__file__).resolve().parents[1])
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from utils.cpt_utils import (
    GRID_COORD_ATTRIBUTES,
    TIME_COORDS,
    check_mandatory_standards,
    construct_dimension_coords,
)

METHODS = ("meteva_to_cube", "cube_to_meteva")



# --- projection / grid helpers (ex-utilities) ---

def simple_pic_iris(cube):
    """简单画出 iris Cube（调试用；惰性导入 matplotlib）。"""
    import iris.plot as iplt
    import iris.quickplot as qplt
    import matplotlib.pyplot as plt

    plt.figure(figsize=(16, 9))
    qplt.contourf(cube, 25)
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

# --- cube setup & meteva bridge (ex-cube_base) ---

def set_up_var_cube(
    data: ndarray,
    name: str = "air_temperature",
    units: str = "K",
    spatial_grid: str = "latlon",
    time: datetime.datetime = datetime.datetime(2017, 11, 10, 0, 0),
    validtime: datetime.datetime = datetime.datetime(2017, 11, 10, 4, 0),
    time_bounds: Optional[Tuple[datetime.datetime, datetime.datetime]] = None,
    realizations: Optional[Union[List[float], ndarray]] = None,
    include_scalar_coords: Optional[List[Coord]] = None,
    attributes: Optional[Dict[str, str]] = None,
    grid_spacing: Optional[float] = None,
    domain_corner: Optional[Tuple[float, float]] = None,
    height_levels: Optional[Union[List[float], ndarray]] = None,
    pressure: bool = False,
) -> Cube:
    """
    Set up a cube containing a single variable field with:
    - x/y spatial dimensions (equal area or lat / lon)
    - optional leading "realization" dimension
    - optional "height" dimension
    - "time", "forecast_reference_time" and "forecast_period" scalar coords
    - option to specify additional scalar coordinates
    - configurable attributes

    Args:
        data:
            2D (y-x ordered) or 3D (realization-y-x ordered) array of data
            to put into the cube.
        name:
            Variable name (standard / long)
        units:
            Variable units
        spatial_grid:
            What type of x/y coordinate values to use.  Permitted values are
            "latlon" or "equalarea".
        time:
            Single cube forecast reference time
        validtime:
            Single cube validity time
        time_bounds:
            Lower and upper bound on time point, if required，如var = past 1h percipitation，则bounds=[-1,0] 
        realizations:
            List of forecast realizations.  If not present, taken from the
            leading dimension of the input data array (if 3D).
        include_scalar_coords:
            List of iris.coords.DimCoord or AuxCoord instances of length 1.
        attributes:
            Optional cube attributes.
        grid_spacing:
            Grid resolution (degrees for latlon or metres for equalarea).
        domain_corner:
            Bottom left corner of grid domain (y,x) (degrees for latlon or metres for equalarea).
        height_levels:
            List of height levels in metres or pressure levels in Pa.
        pressure:
            Flag to indicate whether the height levels are specified as pressure, in Pa.
            If False, use height in metres.

    Returns:
        Cube containing a single variable field
    """
    # construct spatial dimension coordimates
    ypoints = data.shape[-2]
    xpoints = data.shape[-1]
    y_coord, x_coord = construct_yx_coords(
        ypoints,
        xpoints,
        spatial_grid,
        grid_spacing=grid_spacing,
        domain_corner=domain_corner,
    )

    dim_coords = construct_dimension_coords(
        data, y_coord, x_coord, realizations, height_levels, pressure
    )

    # construct list of aux_coords_and_dims
    scalar_coords = construct_scalar_time_coords(validtime, time_bounds, time)
    if include_scalar_coords is not None:
        for coord in include_scalar_coords:
            scalar_coords.append((coord, None))

    # set up attributes
    cube_attrs = {}
    if attributes is not None:
        cube_attrs.update(attributes)

    # create data cube
    cube = iris.cube.Cube(
        data,
        units=units,
        attributes=cube_attrs,
        dim_coords_and_dims=dim_coords,
        aux_coords_and_dims=scalar_coords,
    )
    cube.rename(name)

    # don't allow unit tests to set up invalid cubes
    check_mandatory_standards(cube)
    return cube


def _set_domain_corner(
    ypoints: int, xpoints: int, grid_spacing: float
) -> Tuple[float, float]:
    """
    Set domain corner to create a grid around 0,0.

    Args:
        ypoints
        xpoints
        grid_spacing

    Returns:
        (y,x) values of the bottom left corner of the domain
    """
    y_start = 0 - ((ypoints - 1) * grid_spacing) / 2
    x_start = 0 - ((xpoints - 1) * grid_spacing) / 2

    return y_start, x_start

def _create_yx_arrays(
    ypoints: int, xpoints: int, domain_corner: Tuple[float, float], grid_spacing: float,
) -> Tuple[ndarray, ndarray]:
    """
    Creates arrays for constructing y and x DimCoords.

    Args:
        ypoints
        xpoints
        domain_corner
        grid_spacing

    Returns:
        Tuple containing arrays of y and x coordinate values
    """
    y_stop = domain_corner[0] + (grid_spacing * (ypoints - 1))
    x_stop = domain_corner[1] + (grid_spacing * (xpoints - 1))

    y_array = np.linspace(domain_corner[0], y_stop, ypoints, dtype=np.float32)
    x_array = np.linspace(domain_corner[1], x_stop, xpoints, dtype=np.float32)

    return y_array, x_array


def construct_yx_coords(
    ypoints: int,
    xpoints: int,
    spatial_grid: str,
    grid_spacing: Optional[float] = None,
    domain_corner: Optional[Tuple[float, float]] = None,
) -> Tuple[DimCoord, DimCoord]:
    """
    Construct y/x spatial dimension coordinates

    Args:
        ypoints:
            Number of grid points required along the y-axis
        xpoints:
            Number of grid points required along the x-axis
        spatial_grid:
            Specifier to produce either a "latlon" or "equalarea" grid
        grid_spacing:
            Grid resolution (degrees for latlon or metres for equalarea). If not provided,
            defaults to 10 degrees for "latlon" grid or 2000 metres for "equalarea" grid
        domain_corner:
            Bottom left corner of grid domain (y,x) (degrees for latlon or metres for equalarea).
            If not provided, a grid is created centred around (0,0).

    Returns:
        Tuple containing y and x iris.coords.DimCoords
    """
    if spatial_grid not in GRID_COORD_ATTRIBUTES.keys():
        raise ValueError("Grid type {} not recognised".format(spatial_grid))

    if grid_spacing is None:
        grid_spacing = GRID_COORD_ATTRIBUTES[spatial_grid]["default_grid_spacing"]

    if domain_corner is None:
        domain_corner = _set_domain_corner(ypoints, xpoints, grid_spacing)
    y_array, x_array = _create_yx_arrays(ypoints, xpoints, domain_corner, grid_spacing)

    y_coord = DimCoord(
        y_array,
        GRID_COORD_ATTRIBUTES[spatial_grid]["yname"],
        units=GRID_COORD_ATTRIBUTES[spatial_grid]["units"],
        coord_system=GRID_COORD_ATTRIBUTES[spatial_grid]["coord_system"],
    )
    x_coord = DimCoord(
        x_array,
        GRID_COORD_ATTRIBUTES[spatial_grid]["xname"],
        units=GRID_COORD_ATTRIBUTES[spatial_grid]["units"],
        coord_system=GRID_COORD_ATTRIBUTES[spatial_grid]["coord_system"],
    )

    # add bounds on spatial coordinates
    if ypoints > 1:
        y_coord.guess_bounds()
    if xpoints > 1:
        x_coord.guess_bounds()

    return y_coord, x_coord


def _create_time_point(time: datetime.datetime) -> int:
    """Returns a coordinate point with appropriate units and datatype
    from a datetime.datetime instance.

    Args:
        time

    Returns:
        Returns coordinate point as datatype specified in TIME_COORDS["time"]
    """
    coord_spec = TIME_COORDS["time"]
    point = date2num(time, coord_spec.units, coord_spec.calendar)
    return np.around(point).astype(coord_spec.dtype)


def construct_scalar_time_coords(
    time: datetime.datetime, 
    time_bounds: Optional[List[datetime.datetime]], 
    frt: datetime.datetime,
) -> List[Tuple[DimCoord, bool]]:
    """
    Construct scalar time coordinates as aux_coord list

    Args:
        time:
            Single time point
        time_bounds:
            Lower and upper bound on time point, if required
        frt:
            Single forecast reference time point

    Returns:
        List of iris.coords.DimCoord instances with the associated "None"
        dimension (format required by iris.cube.Cube initialisation).
    """
    # generate time coordinate points
    time_point_seconds = _create_time_point(time)
    frt_point_seconds = _create_time_point(frt)

    fp_coord_spec = TIME_COORDS["forecast_period"]
    if time_point_seconds < frt_point_seconds:
        raise ValueError("Cannot set up cube with negative forecast period")
    fp_point_seconds = (time_point_seconds - frt_point_seconds).astype(
        fp_coord_spec.dtype
    )

    # parse bounds if required
    if time_bounds is not None:
        lower_bound = _create_time_point(time_bounds[0])
        upper_bound = _create_time_point(time_bounds[1])
        bounds = (min(lower_bound, upper_bound), max(lower_bound, upper_bound))
        if time_point_seconds < bounds[0] or time_point_seconds > bounds[1]:
            raise ValueError(
                "Time point {} not within bounds {}-{}".format(
                    time, time_bounds[0], time_bounds[1]
                )
            )
        fp_bounds = np.array(
            [[bounds[0] - frt_point_seconds, bounds[1] - frt_point_seconds]]
        ).astype(fp_coord_spec.dtype)
    else:
        bounds = None
        fp_bounds = None

    # create coordinates
    time_coord = DimCoord(
        time_point_seconds, "time", bounds=bounds, units=TIME_COORDS["time"].units
    )
    frt_coord = DimCoord(
        frt_point_seconds,
        "forecast_reference_time",
        units=TIME_COORDS["forecast_reference_time"].units,
    )
    fp_coord = DimCoord(
        fp_point_seconds, "forecast_period", bounds=fp_bounds, units=TIME_COORDS["forecast_period"].units
    )

    coord_dims = [(time_coord, None), (frt_coord, None), (fp_coord, None)]
    return coord_dims






###### DATA TRANSTORM: meteva.griddata_to_cube 
def read_cube_from_meteva_griddata(xa_data, spatial_grid = 'latlon', to_grid_info=None, 
                    bounds = None ):
    """
    将meteva格点(xarray)转为cube格式(标准投影插值转换流程,包括等经纬度及等距投影)
    Args:
        xa_data (xarray.da): 
            Meteva_base griddata (xarray data read by meteva_base python lib).
        spatial_grid: 'latlon' # 转换为等经纬度投影('latlon')或等距网格（'equalarea'）,默认为latlon
        to_grid_info: 转换到数据的网格信息，有两种模式构建：
                01. meteva_base.grid网格信息类(https://www.showdoc.com.cn/metevabase/10266280656401547)
                同时完成插值和转换，只支持转为等经纬度CUBE
                02. 转换至CUBE网格信息字典grid_dict
                持转换为等经纬度与等距两种投影形式CUBE。模板如下
                grid_dict = { 'dlon':10000, 'dlat':10000, #数据xy间隔(等经纬度单位°，等距单位m)
                'slon':70, 'slat':0, #起始点经纬度(ccrs.PlateCarree()中对应起始点坐标)
                'nlon':701,'nlat':601 #x/y方向格点数
                }
        bounds: 预报要素的time point范围，如var = past 1h percipitation，则bounds=[-1,0] 
    Return:
        cube: Iris.Cube, 等经纬度或等距投影的CUBE网格数据
    """
    is_pressure = False #True为等压层，False为高度层
    ## 数据
    xa_data_np = xa_data.values.squeeze().astype(np.float32)
    if len(xa_data_np.shape)>2 :
        print("Only support 2D griddata(lat, lon)! please split RAWdata to singleVariable.")
        return(None)

    ## name
    xa_data_name = xa_data.name

    ## 单位
    try:
        xa_data_unit = xa_data.attrs['units']
    except KeyError:
        xa_data_unit = None

    ## time, frt, time_bounds
    xa_data_ft, xa_data_frt, time_bounds = cal_validtime_from_meteva_griddata(xa_data, bounds=bounds)
    # print(xa_data_frt,xa_data_ft)
    ## attributes
    try:
        xa_data_attrs = {'dtime_type':xa_data.attrs['dtime_type']}
    except KeyError:
        xa_data_attrs = None

    ## level
    xa_data_level = meb.get_grid_of_data(xa_data).levels[0]
    ## pressure_bool
    xa_data_is_pressure = is_pressure#等压层或等高层

    ## 转换到数据的网格信息
    if to_grid_info is None:# 默认latlon
        grid_info = meb.get_grid_of_data(xa_data)
        from_data = xa_data_np
        spatial_grid = 'latlon'
    elif isinstance(to_grid_info, meb.grid):# meb.grid信息数据，插值至等经纬度网格
        grid_info = to_grid_info
        xa_interp = meb.interp_gg_linear(xa_data, grid=grid_info)#插值
        from_data = xa_interp.values.squeeze().astype(np.float32)
        spatial_grid = 'latlon'
        
    elif isinstance(to_grid_info, dict):#字典型信息数据，根据设置判断等经纬度或等距
        if spatial_grid == 'latlon':#等经纬度网格
            try:
                grid_info = _projdict_to_meteva_gridinfo(to_grid_info)
            except Exception as err:
                print("to_grid_info format ERROR, please check")
                raise ValueError(err)
            xa_interp = meb.interp_gg_linear(xa_data, grid=grid_info)#插值
            from_data = xa_interp.values.squeeze().astype(np.float32)

    ## 投影类型转换,生成CUBE
    ## 等经纬度
    if spatial_grid=='latlon':
        ## grid_spacing
        xa_data_dlon = grid_info.dlon
        ## domain_corner
        xa_data_corner = [grid_info.slat, grid_info.slon]
        xa_data_0 = from_data
        
    ## 等距
    elif spatial_grid=='equalarea':
        ##投影转换，生成numpy.ndarry
        proj0 = GRID_COORD_ATTRIBUTES['latlon']['coord_system'].as_cartopy_crs()##等经纬度
        proj1 = GRID_COORD_ATTRIBUTES['equalarea']['coord_system'].as_cartopy_crs()##等距网格
        proj0_dict = meb.get_grid_of_data(xa_data)
        proj1_dict = to_grid_info.copy()
        proj1_dict['spatial_grid'] = spatial_grid
        xa_data_0 = proj_convert_kdtreeN(from_proj=proj0, from_grid_dict=proj0_dict,
                                    to_proj=proj1, to_grid_dict=proj1_dict, from_ndarray=xa_data_np
                                    ).astype(np.float32)
        ## grid_spacing
        xa_data_dlon = proj1_dict['dlon']
        ## domain_corner
        conrner_x,conrner_y = proj1.transform_point(x=proj1_dict['slon'], y=proj1_dict['slat'], src_crs=ccrs.PlateCarree())
        xa_data_corner = [conrner_y, conrner_x]
    else:
        raise ValueError('spatial_grid ATTRIBUTE in grid_dict must be one of [latlon, equalarea]')
        
    #cube最多支持3维数据：[预报时间，lat, lon]
    cube = set_up_var_cube(data=xa_data_0,
                            name=xa_data_name,
                            units=xa_data_unit,
                            spatial_grid=spatial_grid,##'latlon or equalarea'
                            time = xa_data_frt,
                            validtime = xa_data_ft,
                            time_bounds = time_bounds,
                            attributes=xa_data_attrs,
                            grid_spacing=xa_data_dlon,
                            domain_corner=xa_data_corner,
                            height_levels=xa_data_level,
                            pressure=xa_data_is_pressure,
                           )
    return(cube)



###### DATA TRANSTORM: cube_to_meteva.griddata
def _cube_latlon_to_meteva(cube):#等经纬度cube转meteva.griddata
    xa0 = xr.DataArray.from_iris(cube)
    try:
        temp = len(xa0.time.values)
        dtlist = xa0.time.values
    except TypeError:
        dtlist = [xa0.time.values]
    ## dims info
    dtimelist = [int((i - xa0.forecast_reference_time.values).astype('timedelta64[h]')/np.timedelta64(1,'h')) for i in dtlist]
    glons = xa0.longitude.values
    glon = [glons[0], glons[-1], round(glons[1]-glons[0], 4)]
    glats = xa0.latitude.values
    glat = [glats[0], glats[-1], round(glats[1]-glats[0], 4)]
    ## generate meteva.griddata
    grid_info = meb.grid(glon=glon,  glat=glat,
                    gtime=[xa0.forecast_reference_time.values], dtime_list=dtimelist)
    grd = meb.grid_data(grid=grid_info, data=xa0.values.squeeze())
    return(grd)

def _cube_equalarea_to_meteva(cube, proj_dict_cube, proj_dict_xa):#等距cube转meteva.griddata
    ## proj_dict 支持 meteva.grid网格信息类，也支持投影网格字典
    cube_proj = GRID_COORD_ATTRIBUTES['equalarea']['coord_system'].as_cartopy_crs()##等距网格
    # cube_proj = cube.coord_system().as_cartopy_crs()#等距网格
    xa_proj = GRID_COORD_ATTRIBUTES['latlon']['coord_system'].as_cartopy_crs()##等经纬度

    #######
    ## 数据转换
    if isinstance(cube.data.data,np.ndarray):
        data = cube.data.data
        print("mask array!")
    else:
        data = cube.data      
    new_data = proj_convert_kdtreeN(from_proj=cube_proj, from_grid_dict=proj_dict_cube,
                                        to_proj=xa_proj, to_grid_dict=proj_dict_xa,
                                        from_ndarray=data)
    ##  构建等经纬度xa数据
    dtlist = pd.to_datetime(cube.coord('time').points.copy(), unit='s',origin='unix').to_pydatetime()
    gtime = pd.to_datetime(cube.coord('forecast_reference_time').points[0],
                           unit='s', origin='unix').to_pydatetime()
    try:
        temp = len(dtlist)
    except TypeError:
        dtlist = [dtlist]
    dtimelist = [int((i - gtime).total_seconds()/3600) for i in dtlist]

    if isinstance(proj_dict_xa, meb.grid):#网格信息类
        grid_info = proj_dict_xa.copy()
        grid_info.gtime = [gtime, gtime, '1h']
        grid_info.dtimes = dtimelist
        grid_info.levels = [0]
        grid_info.members = ['data0']
    else:#投影网格字典
        grid_info = _projdict_to_meteva_gridinfo(proj_dict_xa, times = [gtime],dtimes = dtimelist, levels= [0],members = ['data0'])
    # print(grid_info, grid_info.gtime)
    grd = meb.grid_data(grid=grid_info, data=new_data)
    return(grd)



def read_meteva_griddata_from_cube(cube, 
                        # spatial_grid = 'latlon', 
                        grid_info=None):
    """
    将cube格式转为meteva格点(xarray)(标准投影插值转换流程,包括等经纬度及等距投影)
    Args:
        cube: Cube griddata
        # spatial_grid: 'latlon' # 转换为等经纬度投影('latlon')或等距网格（'equalarea'）,默认为latlon
        cube_info/grid_info: 转换到数据的网格信息，有两种模式构建：
            01. meteva_base.grid网格信息类(https://www.showdoc.com.cn/metevabase/10266280656401547)
                同时完成插值和转换，只支持转为等经纬度CUBE
            02. 转换至CUBE网格信息字典grid_dict
                持转换为等经纬度与等距两种投影形式CUBE。模板如下
                grid_dict = { 'dlon':10000, 'dlat':10000, #数据xy间隔(等经纬度单位°，等距单位m)
                'slon':70, 'slat':0, #起始点经纬度(ccrs.PlateCarree()中对应起始点坐标)
                'nlon':701,'nlat':601 #x/y方向格点数
    """
    if isinstance(grid_info, dict):
        if 'spatial_grid' not in grid_info.keys():
            grid_info['spatial_grid'] = 'latlon'

    spatial_grid = _get_cube_spatialgrid(cube) #latlon/equalarea

    if spatial_grid == 'latlon':
        grd = _cube_latlon_to_meteva(cube)
        if grid_info is not None:
            if isinstance(grid_info, dict):
                grid_info0 = _projdict_to_meteva_gridinfo(grid_info)
            else:
                grid_info0 = grid_info
            try:
                grd = meb.interp_gg_linear(grd, grid=grid_info0)
            except Exception as err:
                raise ValueError(err)
    elif spatial_grid == 'equalarea':
        if grid_info is None:
            raise ValueError('ERROR: grid_info must be set IF spatial_grid is equalarea')
        cube_info = cube_dim_info_summary(cube)
        # print(cube_info)
        if 'spatial_grid' not in cube_info.keys():
            cube_info['spatial_grid'] = spatial_grid
        grd = _cube_equalarea_to_meteva(cube, cube_info, grid_info) #网格信息可以为两种类型
    else:
        raise IOError('Parameter spatial_grid ERROR:  spatial_grid must be one of latlon/equalarea')
    return(grd)


def process(
    method: str = "meteva_to_cube",
    darray: Optional[xr.DataArray] = None,
    cube: Optional[Cube] = None,
    spatial_grid: str = "latlon",
    to_grid_info=None,
    bounds=None,
    grid_info=None,
    show: bool = False,
    **kwargs: Any,
):
    """按 ``method`` 做 meteva ↔ Cube 转换。

    - ``meteva_to_cube``：需要 ``darray``；可选 ``spatial_grid`` / ``to_grid_info`` / ``bounds``
    - ``cube_to_meteva``：需要 ``cube``；可选 ``grid_info`` / ``to_grid_info``
    """
    _ = kwargs
    name = (method or "meteva_to_cube").strip().lower().replace("-", "_")
    if name not in METHODS:
        raise ValueError("method 无效。可选: %s" % (", ".join(METHODS),))
    if name == "meteva_to_cube":
        if darray is None:
            raise ValueError("meteva_to_cube 需要 darray")
        if show:
            print("util_plugin.process method=meteva_to_cube spatial_grid=%s" % spatial_grid)
        return read_cube_from_meteva_griddata(
            xa_data=darray,
            spatial_grid=spatial_grid,
            to_grid_info=to_grid_info,
            bounds=bounds,
        )
    if cube is None:
        raise ValueError("cube_to_meteva 需要 cube")
    info = grid_info if grid_info is not None else to_grid_info
    if show:
        print("util_plugin.process method=cube_to_meteva")
    return read_meteva_griddata_from_cube(cube=cube, grid_info=info)


class TransMetevaToCube:
    """兼容旧类名；内部转调 ``process(method='meteva_to_cube')``。"""

    def __init__(self, darray, spatial_grid="latlon", to_grid_info=None, bounds=None):
        self.darray = darray
        self.spatial_grid = spatial_grid
        self.to_grid_info = to_grid_info
        self.bounds = bounds

    def process(self, show=True):
        return process(
            method="meteva_to_cube",
            darray=self.darray,
            spatial_grid=self.spatial_grid,
            to_grid_info=self.to_grid_info,
            bounds=self.bounds,
            show=show,
        )


class TransCubeToMeteva:
    """兼容旧类名；内部转调 ``process(method='cube_to_meteva')``。"""

    def __init__(self, cube, to_grid_info=None):
        self.cube = cube
        self.to_grid_info = to_grid_info

    def process(self, show=True):
        return process(
            method="cube_to_meteva",
            cube=self.cube,
            to_grid_info=self.to_grid_info,
            show=show,
        )
