# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2022， CMA National Meteorological Centre.
# All rights reserved.
#
# Distributed under the terms of the GPL v2 License.
#

"""
Functions to set up cube variable
translate meteva.griddata to cube,  and cube to meteva.griddata
include latlon to equalarea

"""
# from datetime import datetime
import datetime
import xarray as xr
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import iris
import numpy as np
from cf_units import Unit, date2num
from iris.coords import Coord, DimCoord
from iris.cube import Cube
from iris.exceptions import CoordinateNotFoundError
from numpy import ndarray
import cartopy.crs as ccrs
import meteva_base as meb


# from improver.synthetic_data.set_up_test_cubes import (
    # _construct_dimension_coords,
    # construct_scalar_time_coords,
# )

# from improver.metadata.check_datatypes import check_mandatory_standards

from nimm.utils.set_up_cubes import(
    construct_dimension_coords,
    check_mandatory_standards,
)
from nimm.metadata.time_info  import TIME_COORDS
from nimm.metadata.grid_info import GRID_COORD_ATTRIBUTES
from nimm.base.utilities import *
import nimm


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
                grid_info = nimm.base.utilities._projdict_to_meteva_gridinfo(to_grid_info)
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
        from nimm.metadata.grid_info import GRID_COORD_ATTRIBUTES
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
    import xarray as xr
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
    import pandas as pd
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
        grid_info = nimm.base.utilities._projdict_to_meteva_gridinfo(proj_dict_xa, times = [gtime],dtimes = dtimelist, levels= [0],members = ['data0'])
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

    spatial_grid = nimm.base.utilities._get_cube_spatialgrid(cube) #latlon/equalarea

    if spatial_grid == 'latlon':
        grd = _cube_latlon_to_meteva(cube)
        if grid_info is not None:
            if isinstance(grid_info, dict):
                grid_info0 = nimm.base.utilities._projdict_to_meteva_gridinfo(grid_info)
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
    



##### PLUGINS, grid_data_Transform
from nimm import PostProcessingPlugin

class TransMetevaToCube(PostProcessingPlugin):
    """
    插件类：将meteva格点(xarray.DataArray)转为cube格式(标准投影插值转换流程,包括等经纬度及等距投影)
    """
    def __init__(self,
        darray: xr.DataArray,
        spatial_grid: str = 'latlon', 
        to_grid_info: Optional[dict] = None,
        bounds = None
                ) -> Cube:
        """
        Args:
            darray (xarray.da): 
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
                    默认为等经纬度原始数据网格范围和分辨率
            bounds: 预报要素的time point范围，如var = past 1h percipitation，则bounds=[-1,0] 
        Return:
            cube: Iris.Cube, 等经纬度或等距投影的CUBE网格数据
        """
        self.grd = darray
        self.spatial_grid = spatial_grid
        self.to_grid_info = to_grid_info
        self.bounds = bounds
        return None
    
    def __repr__(self):
        """Represent the plugin instance as a string."""
        from nimm.base.utilities import _meteva_gridinfo_to_projdict
        result = (
            "### READING PARAMETERS ###: \n"
            "<From_Grid_Info : {},\n"
            "To_Grid_Info    : {},\n"
            "To_Grid_PROJ    : {},\n"
            "TO_Spatial_grid : {}>\n"
            "### "
            )
        from_grid_info_str = _meteva_gridinfo_to_projdict(meb.get_grid_of_data(self.grd))
        try:
            to_grid_proj = GRID_COORD_ATTRIBUTES[self.spatial_grid]["coord_system"]
            if not isinstance(self.to_grid_info, dict):
                to_grid_info_str = _meteva_gridinfo_to_projdict(self.to_grid_info)#meb.grid转为字典
            else:
                to_grid_info_str = self.to_grid_info
        except Exception as err:
            print(err)
            to_grid_proj = None
            to_grid_info_str = None

        return result.format(
            from_grid_info_str, 
            to_grid_info_str,
            to_grid_proj,
            self.spatial_grid) 

    def process(self, show=True)->Cube:
        if show: print(self)
        cube = read_cube_from_meteva_griddata(xa_data=self.grd, spatial_grid=self.spatial_grid,
        to_grid_info=self.to_grid_info, bounds = self.bounds )
        return cube



class TransCubeToMeteva(PostProcessingPlugin):
    """
    插件类： 将cube格式转为meteva格点(xarray)(标准投影插值转换流程,包括等经纬度及等距投影)
    """
    
    def __init__(self, 
        cube: Cube,
        # spatial_grid: str = 'latlon',
        to_grid_info: Optional[dict] = None
        ) -> xr.DataArray:
        """
        Args:
            cube: Cube griddata
            # spatial_grid: 'latlon' # 转换前的CUBE为等经纬度投影('latlon')或等距网格（'equalarea'）,默认为latlon, 现改为根据cube信息自动确定
            cube_info/grid_info: 转换数据的网格信息，有两种模式构建：
                01. meteva_base.grid网格信息类(https://www.showdoc.com.cn/metevabase/10266280656401547)
                    同时完成插值和转换，只支持转为等经纬度CUBE
                02. 转换至CUBE网格信息字典grid_dict
                    持转换为等经纬度与等距两种投影形式CUBE。模板如下
                    grid_dict = { 'dlon':10000, 'dlat':10000, #数据xy间隔(等经纬度单位°，等距单位m)
                    'slon':70, 'slat':0, #起始点经纬度(ccrs.PlateCarree()中对应起始点坐标)
                    'nlon':701,'nlat':601 #x/y方向格点数
        """
        self.cube = cube
        # self.spatial_grid = nimm.base.utilities._get_cube_spatialgrid(self.cube)
        self.to_grid_info = to_grid_info
        return None
    

    def __repr__(self):
        """Represent the plugin instance as a string."""
        from nimm.base.utilities import cube_dim_info_summary,_meteva_gridinfo_to_projdict
        result = (
            "### READING PARAMETERS ###: \n"
            "<From_Grid_Info : {},\n"
            "From_Grid_PROJ  : {},\n"
            "To_Grid_Info    : {}>\n"
            "### "
            )
        from_grid_info_str = cube_dim_info_summary(self.cube)
        from_grid_proj = self.cube.coord_system()
        try:
            if self.to_grid_info is None:
                to_grid_info_str = from_grid_info_str
            elif not isinstance(self.to_grid_info, dict):
                to_grid_info_str = _meteva_gridinfo_to_projdict(self.to_grid_info)#meb.grid转为字典
            else:
                to_grid_info_str = self.to_grid_info
        except Exception as err:
            print(err)
            to_grid_info_str = None
        return result.format(
            from_grid_info_str, 
            from_grid_proj,
            to_grid_info_str,) 


    def process(self, show=True)->xr.DataArray:
        import iris
        # spatial_grid0 = nimm.base.utilities._get_cube_spatialgrid(self.cube)
        # self.spatial_grid = spatial_grid0
        if show: print(self)
        grd = read_meteva_griddata_from_cube(cube=self.cube, 
                        # spatial_grid = self.spatial_grid, 
                        grid_info=self.to_grid_info)
        return grd



if __name__ == '__main__':
    file = r"\\10.10.31.84\qpe\QPE_10min\20230419\m10_202304190400.m4"#QPE
    grid_info = meb.grid(glon=[105,130,0.05], glat=[20,35,0.05])##原始网格信息
    to_grid_dict = { 'dlon':5000, 'dlat':5000, #数据xy间隔
                'slon':105, 'slat':20, #起始点经纬度定位
                'nlon':501,'nlat':301,
                'spatial_grid':'equalarea' 
                }#等距网格，距离单位m，转换到的网格信息
    ## 01 meteva to cube
    grd = meb.read_griddata_from_micaps4(file,grid=grid_info)
    cube0 = read_cube_from_meteva_griddata(grd)#等经纬度
    cube1 = read_cube_from_meteva_griddata(grd, spatial_grid = 'equalarea', to_grid_info=to_grid_dict)#等距
    simple_pic_iris(cube0), simple_pic_iris(cube1)
    print(cube0),print(cube1)

    ## 02 cube to meteva
    grd1 = _cube_latlon_to_meteva(cube0)
    print(grd1)

    pass