# -*- coding: utf-8 -*- 
# cython:language_level=3
import datetime
import os
import sys
import re
import h5py
import numpy  as np
import pandas as pd
from eccodes import *
from scipy import interpolate
from shutil import copyfile
import multiprocessing as mp
from multiprocessing.dummy import Pool as ThreadPool
from concurrent.futures import ThreadPoolExecutor
import meteva.base as meb
import netCDF4 as nc
import time

try:
  import pygrib
except ImportError:
  print(__name__+':no install pygrib')

#画图库
try:
  import seaborn as sns #sns.set()
  import matplotlib.pyplot as plt
  import matplotlib.ticker as mticker
  from matplotlib import colors, cm, rcParams, ticker
  from matplotlib.patheffects import Stroke
  from matplotlib.colors import LinearSegmentedColormap
  #cartopy
  import cartopy.crs as ccrs
  import cartopy.feature as cfeature
  from cartopy.feature import ShapelyFeature
  import cartopy.io.shapereader as shpreader
  from cartopy.mpl.gridliner import LATITUDE_FORMATTER, LONGITUDE_FORMATTER
except ImportError:
  print(__name__,ImportError)

try:
  import rasterio
  import rasterio.mask
except ImportError:
  print(__name__+':no install rasterio')

import Module_MyFunction      as MMyfun


class Class_Interp_dem(object):

  "初始化函数"
  def __init__(self, iDebug = 0):
    self.iDebug           = iDebug
    self.RGrid_Default    = -32766.0
    self.RCAbsZero        = 273.15
    self.fcalm_wd         = 999017.0   #静风
    self.seta_dir         = "eta"      #最优参数文件夹
    self.iN_Frost_Time    = 0
    self.ltForecast_Time  = [0,24]
    self.cls_myfun        = MMyfun.Class_MyFunction()
    self.dymdl_Geog       = None
    self.dyIntp_info      = None
    #检验要素名
    self.ltPQSN_vld       = ["2t", "2rh", "10ws"]
    #求参要素名
    self.ltPQSN_eta       = ['2t', '2rh', '10ws']    
    #插值要素名
    self.ltPQSN_Intp      = ['2t', '2rh', '10ws', '10u', '10v', 'sp', 'tcc']
    #垂直变率名
    self.ltgamma_name     = ['gamma_'+x for x in ['2t', '2rh', '10ws', '10u', '10v','sp']]
    #最大最小名
    self.ltPQSN_mxmn      = [] #['2t_max', '2t_min', '2rh_max', '2rh_min', '10ws_max']
    #瞬时要素短名==>实况文件夹名
    self.dyInstPQSN_to_obsdir = {"2t"    :["Temperature"     ,"H00_Inst"],\
                                 "2rh"   :["Relativehumidity","H00_Inst"],\
                                 "10ws"  :["Wind"            ,"H00_Inst"],\
                                 "10gust":["Wind"            ,"H01_Max" ],\
                                 "tcc"   :["Totalcloud"      ,"H00_Inst"],\
                                 "sp"    :["Surfacepressure" ,"H00_Inst"]}
    #日变要素短名==>实况文件    #(北京时间)
    self.dyPhyQ_24h  = {"2t_max"  :["Temperature"     ,"H24_Max"],\
                        "2t_min"  :["Temperature"     ,"H24_Min"],\
                        "2rh_max" :["Relativehumidity","H24_Max"],\
                        "2rh_min" :["Relativehumidity","H24_Min"],\
                        "10ws_max":["Wind"            ,"H24_Max"]}
    #要素输出保存有效位数
    self.dyPQ_round={"2t":1,"2rh":1,"10u":1,"10v":1,"10ws":1,"10gust":1,"mn2t3":1,"mx2t3":1,"tcc":2,\
                     "2t_max":1, "2t_min":1, "2rh_max":1, "2rh_min":1, "10ws_max":1, "sp":1,
                     'gamma_sp':4,'gamma_2t':4,'gamma_2rh':4,'gamma_10u':4,'gamma_10v':4,'gamma_10ws':4,
                     "lon_lat":3}
    #要素增量保存有效位数
    self.dyPQ_Inc_round={"2t":2,"2rh":2,"10u":2,"10v":2,"10ws":2,"10gust":2,"mn2t3":2,"mx2t3":2,"tcc":3,\
                         "2t_max":2, "2t_min":2, "2rh_max":2, "2rh_min":2, "10ws_max":2, "sp":2,
                         'gamma_sp':5,'gamma_2t':5,'gamma_2rh':5,'gamma_10u':5,'gamma_10v':5,'gamma_10ws':5}
    #质控
    self.dyPQ_QC={"2t":[-60,60],"2rh":[0,100],"10u":[-80,80],"10v":[-80,80],"10ws":[0,80],"10gust":[0,80],"mn2t3":[-60,60],"mx2t3":[-60,60],"tcc":[0,100],\
                  "2t_max":[-60,60], "2t_min":[-60,60], "2rh_max":[0,100], "2rh_min":[0,100], "10ws_max":[0,80], "sp":[200,1100]}

  #格点经纬度信息初始化
  def dGlonlat_init(self, ltGrid_info):
    dylonlat={}
    dylonlat["begin_lon"] = ltGrid_info[0]
    dylonlat["end_lon"]   = ltGrid_info[1]   #140.99对应dem1km.txt
    dylonlat["lon_res"]   = ltGrid_info[2]
    dylonlat["begin_lat"] = ltGrid_info[3]
    dylonlat["end_lat"]   = ltGrid_info[4]
    dylonlat["lat_res"]   = ltGrid_info[5]
    return dylonlat

  #根据起始经纬度范围信息计算相关矩阵信息
  def dlonlat_info(self, dylonlat, info_lev=2, around=2, idebug=0, slabel="1km"):
    '''
      dylonlat={}
      dylonlat["begin_lon"] = 70
      dylonlat["end_lon"]   = 140.0
      dylonlat["begin_lat"] = 0
      dylonlat["end_lat"]   = 60.0
      dylonlat["lon_res"]   = 0.05
      dylonlat["lat_res"]   = 0.05
      info_lev : 信息等级0 1 2 3
    '''
    iN_lon, iN_lat = self.dNum_lonlat(dylonlat)
    dylonlat["Nlon"]=iN_lon
    dylonlat["Nlat"]=iN_lat
    if idebug==1:
      print(slabel+":"+str(iN_lat)+"×"+str(iN_lon)+"="+str(iN_lon*iN_lat))
    dylonlat["tpshape_lonlat"]=(dylonlat["Nlat"],dylonlat["Nlon"])
    #信息1等级
    if info_lev>=1:
      #1维数组
      ndy1d_x_lon = np.arange(dylonlat["begin_lon"], dylonlat["end_lon"]+0.001, dylonlat["lon_res"])
      ndy1d_y_lat = np.arange(dylonlat["begin_lat"], dylonlat["end_lat"]+0.001, dylonlat["lat_res"])
      #保留小数位
      ndy1d_x_lon = np.around(ndy1d_x_lon,around)
      ndy1d_y_lat = np.around(ndy1d_y_lat,around)
      #保存信息
      dylonlat["ndy1d_x_lon"] = ndy1d_x_lon
      dylonlat["ndy1d_y_lat"] = ndy1d_y_lat
      #信息2等级
      if info_lev>=2:
        #2维数组
        ndy2d_x_lon, ndy2d_y_lat = np.meshgrid(ndy1d_x_lon, ndy1d_y_lat)  #上-下=南-北
        #保留小数位
        ndy2d_x_lon = np.around(ndy2d_x_lon,around)
        ndy2d_y_lat = np.around(ndy2d_y_lat,around) #上-下(南-北)
        #保存信息
        dylonlat["ndy2d_x_lon"] = ndy2d_x_lon
        dylonlat["ndy2d_y_lat"] = ndy2d_y_lat
        #信息2等级
        if info_lev>=2:
          #为后续在shape中找点用
          ndy2d_x_lon_flat = ndy2d_x_lon.flatten()  # 将坐标展成一维
          ndy2d_y_lat_flat = ndy2d_y_lat.flatten()
          ndy2d_xy = np.column_stack((ndy2d_y_lat_flat,ndy2d_x_lon_flat))
          dylonlat["ndy2d_xy"]    = ndy2d_xy
    return dylonlat

  #格点数
  def dNum_lonlat(self, dylonlat):
    iN_lon=round((dylonlat["end_lon"]-dylonlat["begin_lon"])/dylonlat["lon_res"])+1
    iN_lat=round((dylonlat["end_lat"]-dylonlat["begin_lat"])/dylonlat["lat_res"])+1
    return (iN_lon, iN_lat)
  
  #读分区文件-读取M4数据
  def dmulti_Read_d4_scalar(self, args):
     return self.dRead_d4_scalar(*args)  
  def dRead_d4_scalar(self, sIn_abs_path, skiprows=2, default=9999.0):
    if os.path.exists(sIn_abs_path):
      try:
        ndy_data=np.loadtxt(sIn_abs_path,skiprows=skiprows)
        ndy_data[np.isnan(ndy_data)]=default
        ndy_data[ndy_data>=default]=np.nan        
        with open(sIn_abs_path) as fh:
          lthead = [fh.readline()]
          shead = fh.readline()
          lthead.append(shead)
      except Exception as e:
        print("Error:"+sIn_abs_path)
        ndy_data = np.array([])
        lthead   = []
    else:
      ndy_data = np.array([])
      lthead   = []
    return ndy_data,lthead
  
  #读分区文件
  def dRead_Zoning(self, stif_abs_path):
    with rasterio.open(stif_abs_path) as dsr: #class 'rasterio.io.DatasetReader'
      #读取第一条数据
      ndyzoning = dsr.read(1) #返回一个numpy n-d数组 上-下(北-南) 左-右(西-东)
      #ndyzoning=ndyzoning.astype("float32") #left=70.0, bottom=0.0, right=140.050, top=60.05
      ndyzoning[ndyzoning>=60]=0
      ndyzoning=np.flipud(ndyzoning) #变为上-下(南-北) 左-右(西-东)
    #中国区域5km的mask
    mask_area=ndyzoning>0 #上-下(南-北)
    return ndyzoning, mask_area
  
  #读取中国地形文件
  def dRead_Terrain(self, stif_abs_path):
    with rasterio.open(stif_abs_path) as dsr: #class 'rasterio.io.DatasetReader'
      #读取第一条数据
      ndyterrain = dsr.read(1) #返回一个numpy n-d数组 上-下(北-南) 左-右(西-东)
      ndyterrain = np.round(ndyterrain.astype("float32"),1)
      ndyterrain[ndyterrain<=-1000.]=0
      ndyterrain[ndyterrain>=9000.]=0
      ndyterrain=np.flipud(ndyterrain) #变为上-下(南-北) 左-右(西-东)
    return ndyterrain

  #自选省份
  def dSelect_Provinces(self, ndyzoning_rlt, ltProv_code):
    mask_area=np.zeros_like(ndyzoning_rlt,dtype="float32")
    for iprov_code in ltProv_code:
      mask_area[ndyzoning_rlt==iprov_code]=iprov_code
    mask_area=mask_area>0
    return mask_area

  #粗网格根据地形插值到细网格
  def dDEM_3d_interp_scalar(self, dyIntpP, dyGrid, lapse_rate_2d, eta=1.0, skey="2t", sout="less"):
    '''
      dyIntpP:       插值点的经度,纬度,海拔字典
                     key: lon, lat, alt = 2d场
      dyGrid:        用于插值前格点的经度,纬度,海拔的字典  上-下=南-北数据 EC=(481, 561) 269841
                     key:begin_lon, lon_res, Nlon
                         begin_lat, lat_res, Nlat
                         ndy2d_x_lon, ndy2d_y_lat       
                         alt
      lapse_rate_2d：垂直变化率, 2维矩阵, 与dyGrid分辨率相同 EC=(481, 561)=269841
    '''
    #插值点对应四周格点号 dyGrid["ndy2d_x_lon"]是上-下=南-北数据
    ndyidx_left_W_lon  = np.floor((dyIntpP['lon']-dyGrid["begin_lon"])/dyGrid["lon_res"]).astype(int) #西:向下取整 
    ndyidx_right_E_lon = ndyidx_left_W_lon + 1 #东
    ndyidx_right_E_lon[ndyidx_right_E_lon>=dyGrid["Nlon"]]=dyGrid["Nlon"]-1
    #获得从0开始的插值点对应的左下角格点索引号
    ndyidx_up_S_lat    = np.floor((dyIntpP['lat']-dyGrid["begin_lat"])/dyGrid["lat_res"]).astype(int) #南=数组对应上方(南边纬度)
    ndyidx_down_N_lat  = ndyidx_up_S_lat + 1  #北=这里的up其实是实际中的南边,down是北边，因为矩阵是上-下=南-北数据
    ndyidx_down_N_lat[ndyidx_down_N_lat>=dyGrid["Nlat"]]=dyGrid["Nlat"]-1
    #左下右上经纬度  上-下=南-北数据
    ndyglon_left_WN  = dyGrid["ndy2d_x_lon"][ndyidx_down_N_lat,ndyidx_left_W_lon]   #西北角经度, 输入数组=左-右=西-东
    ndyglat_down_WN  = dyGrid["ndy2d_y_lat"][ndyidx_down_N_lat,ndyidx_left_W_lon]   #西北角纬度, x1 |----.  x2 y2 纬度小=南
    ndyglon_right_ES = dyGrid["ndy2d_x_lon"][ndyidx_up_S_lat  ,ndyidx_right_E_lon]  #东南角经度     |    |
    ndyglat_up_ES    = dyGrid["ndy2d_y_lat"][ndyidx_up_S_lat  ,ndyidx_right_E_lon]  #东南角纬度     .----|     y1 纬度大=北
    #权重参数
    x2_x=ndyglon_right_ES-dyIntpP['lon']  #右边(东) - 左点
    x_x1=dyIntpP['lon']-ndyglon_left_WN   #右点     - 左边(西)
    y_y1=dyIntpP['lat']-ndyglat_down_WN   #上点     - 下边(北)
    y2_y=ndyglat_up_ES -dyIntpP['lat']    #下点     - 上边(南)
    y2_y1_x2_x1 = -dyGrid["lat_res"]*dyGrid["lon_res"]
    #计算权重
    w1=y2_y*x2_x/y2_y1_x2_x1  #对应T11=左下
    w2=y2_y*x_x1/y2_y1_x2_x1  #对应T21=右下
    w3=y_y1*x2_x/y2_y1_x2_x1  #对应T12=左上
    w4=y_y1*x_x1/y2_y1_x2_x1  #对应T22=右上
    #4格点根据海拔高度进行物理量的偏差订正
    #print(f"size:eta-{np.size(eta)},====dyGrid['alt']{dyGrid['alt'].shape}== lr-{lapse_rate_2d.shape} alt-{np.size(dyIntpP['alt'])}")
    if np.size(eta)==1:
      ndyQ11_Bias_left_down_WN =(dyIntpP['alt']-dyGrid['alt'][ndyidx_down_N_lat, ndyidx_left_W_lon]) *lapse_rate_2d[ndyidx_down_N_lat,ndyidx_left_W_lon]*eta
      ndyQ21_Bias_right_down_EN=(dyIntpP['alt']-dyGrid['alt'][ndyidx_down_N_lat, ndyidx_right_E_lon])*lapse_rate_2d[ndyidx_down_N_lat,ndyidx_right_E_lon]*eta
      ndyQ12_Bias_left_up_WS   =(dyIntpP['alt']-dyGrid['alt'][ndyidx_up_S_lat,   ndyidx_left_W_lon]) *lapse_rate_2d[ndyidx_up_S_lat,  ndyidx_left_W_lon]*eta
      ndyQ22_Bias_right_up_ES  =(dyIntpP['alt']-dyGrid['alt'][ndyidx_up_S_lat,   ndyidx_right_E_lon])*lapse_rate_2d[ndyidx_up_S_lat,  ndyidx_right_E_lon]*eta
    elif np.size(eta)==np.size(lapse_rate_2d):
      #eta[ndyidx_down_N_lat,ndyidx_left_W_lon] #1d(1682601,)
      ndyQ11_Bias_left_down_WN =(dyIntpP['alt']-dyGrid['alt'][ndyidx_down_N_lat, ndyidx_left_W_lon]) *lapse_rate_2d[ndyidx_down_N_lat,ndyidx_left_W_lon]*eta[ndyidx_down_N_lat,ndyidx_left_W_lon]
      ndyQ21_Bias_right_down_EN=(dyIntpP['alt']-dyGrid['alt'][ndyidx_down_N_lat, ndyidx_right_E_lon])*lapse_rate_2d[ndyidx_down_N_lat,ndyidx_right_E_lon]*eta[ndyidx_down_N_lat,ndyidx_right_E_lon]
      ndyQ12_Bias_left_up_WS   =(dyIntpP['alt']-dyGrid['alt'][ndyidx_up_S_lat,   ndyidx_left_W_lon]) *lapse_rate_2d[ndyidx_up_S_lat,  ndyidx_left_W_lon]*eta[ndyidx_up_S_lat,  ndyidx_left_W_lon]
      ndyQ22_Bias_right_up_ES  =(dyIntpP['alt']-dyGrid['alt'][ndyidx_up_S_lat,   ndyidx_right_E_lon])*lapse_rate_2d[ndyidx_up_S_lat,  ndyidx_right_E_lon]*eta[ndyidx_up_S_lat,  ndyidx_right_E_lon]
    elif np.size(eta)==np.size(dyIntpP['alt']): #输入eta参数分辨率与插值后的分辨率一致
      if len(eta.shape)==2: eta=eta.flatten()
      ndyQ11_Bias_left_down_WN =(dyIntpP['alt']-dyGrid['alt'][ndyidx_down_N_lat, ndyidx_left_W_lon]) *lapse_rate_2d[ndyidx_down_N_lat,ndyidx_left_W_lon]*eta
      ndyQ21_Bias_right_down_EN=(dyIntpP['alt']-dyGrid['alt'][ndyidx_down_N_lat, ndyidx_right_E_lon])*lapse_rate_2d[ndyidx_down_N_lat,ndyidx_right_E_lon]*eta
      ndyQ12_Bias_left_up_WS   =(dyIntpP['alt']-dyGrid['alt'][ndyidx_up_S_lat,   ndyidx_left_W_lon]) *lapse_rate_2d[ndyidx_up_S_lat,  ndyidx_left_W_lon]*eta
      ndyQ22_Bias_right_up_ES  =(dyIntpP['alt']-dyGrid['alt'][ndyidx_up_S_lat,   ndyidx_right_E_lon])*lapse_rate_2d[ndyidx_up_S_lat,  ndyidx_right_E_lon]*eta
    #(插值点海拔-4个格点海拔)*垂直变化率=增量(高于插值点降低,低于插值点升高)  dyGrid=上-下:南-北(小-大)
    #4个格点的偏差订正值
    ndyQ11_WN = dyGrid[skey][ndyidx_down_N_lat,ndyidx_left_W_lon]  + ndyQ11_Bias_left_down_WN
    ndyQ21_EN = dyGrid[skey][ndyidx_down_N_lat,ndyidx_right_E_lon] + ndyQ21_Bias_right_down_EN
    ndyQ12_WS = dyGrid[skey][ndyidx_up_S_lat,  ndyidx_left_W_lon]  + ndyQ12_Bias_left_up_WS
    ndyQ22_ES = dyGrid[skey][ndyidx_up_S_lat,  ndyidx_right_E_lon] + ndyQ22_Bias_right_up_ES
    #偏差订正值双线性插值到插值点上
    ndyalt_interp_rlt = ndyQ11_WN*w1+ndyQ21_EN*w2+ndyQ12_WS*w3+ndyQ22_ES*w4
    #风速插值后会存在小于0的
    if skey in ["10ws","10fg3","10gust"]:
      ndyalt_interp_rlt[ndyalt_interp_rlt<=0.] = 0.
    elif skey in ["2rh"]:
      ndyalt_interp_rlt[ndyalt_interp_rlt<=0.]   = 0.
      ndyalt_interp_rlt[ndyalt_interp_rlt>=100.] = 100.
    elif skey in ["sp"]: #珠穆朗玛峰山顶气压最低
      ndyalt_interp_rlt[ndyalt_interp_rlt<=200] = 200
    #输出数据
    if sout=="less":
      return ndyalt_interp_rlt
    else:
      return ndyalt_interp_rlt, [ndyidx_down_N_lat,ndyidx_up_S_lat,ndyidx_left_W_lon,ndyidx_right_E_lon]
  
  #多层数据合并
  def dMulti_Level_merge(self, dyMLmodel, arnd=None):
    '''
      多层模式数据: dyMLmodel
    '''
    #层次从低层1000hpa到高层10hpa
    ltilevel = list(sorted([x for x in dyMLmodel.keys()], reverse=True))
    ndyMLdata = np.zeros((len(ltilevel), dyMLmodel[ltilevel[0]].size),dtype="float32")
    for irow,ilev in enumerate(ltilevel):
      ndyMLdata[irow,:] = dyMLmodel[ilev].flatten()
    #保留小数
    if arnd is not None:
      ndyMLdata = np.around(ndyMLdata,arnd)
    return ndyMLdata
  
  #网格标量双线性插值
  def dMesh_scalar_interp(self, dylonlat_SL_IG_12P5km, dylonlat_ML_IG_25km, vertical_rate_2d_surface, method='linear'):
    '''
      dylonlat_SL_IG_12P5km    : 插值结果的地理信息
      dylonlat_ML_IG_25km      : 插值前地理信息
      vertical_rate_2d_surface : 插值前物理量值=近地面垂直变率
    '''
    ndy12P5km_lon_x_1d = dylonlat_SL_IG_12P5km["ndy2d_x_lon"].flatten()
    ndy12P5km_lat_y_1d = dylonlat_SL_IG_12P5km["ndy2d_y_lat"].flatten()
    #需要插值的点:数组合并为[[纬度 经度]] [n,2]
    ndy12Pkm_xy =  np.vstack((ndy12P5km_lat_y_1d, ndy12P5km_lon_x_1d)).T
    #西-东=南-北=(左-右)(上-下)  #(摄氏度/米=-0.0065)
    interp_linear = interpolate.RegularGridInterpolator((dylonlat_ML_IG_25km["ndy1d_y_lat"], dylonlat_ML_IG_25km["ndy1d_x_lon"]), 
                                                         vertical_rate_2d_surface, method=method)      #输入南-北数据
    lapse_rate_2d_12P5km = interp_linear(ndy12Pkm_xy).reshape(dylonlat_SL_IG_12P5km["tpshape_lonlat"]) #输出南-北(上-下)
    return lapse_rate_2d_12P5km
  
  #插值矢量U/V/WS三个变量
  def dMesh_vector_interp(self, dylonlat_SL_IG_12P5km, dylonlat_ML_IG_25km, ndy2d_U, ndy2d_V, ndy2d_WS, method='linear'):
    '''
      dylonlat_SL_IG_12P5km : 地面层细网格经纬度信息
      dylonlat_ML_IG_25km   : 高空层粗网格经纬度信息
      ndy2d_U,ndy2d_V       : 要插值的粗2d矢量场
    '''
    ndy12P5km_lon_x_1d = dylonlat_SL_IG_12P5km["ndy2d_x_lon"].flatten()
    ndy12P5km_lat_y_1d = dylonlat_SL_IG_12P5km["ndy2d_y_lat"].flatten()
    #需要插值的点:数组合并为[[纬度 经度]] [n,2]
    ndy12Pkm_xy =  np.vstack((ndy12P5km_lat_y_1d, ndy12P5km_lon_x_1d)).T
    #西-东=南-北=(左-右)(上-下)  #(摄氏度/米=-0.0065)
    #U
    U_interp_linear = interpolate.RegularGridInterpolator((dylonlat_ML_IG_25km["ndy1d_y_lat"], dylonlat_ML_IG_25km["ndy1d_x_lon"]), 
                                                           ndy2d_U, method=method) #输入南-北数据
    ndy2d_U_12P5km = U_interp_linear(ndy12Pkm_xy).reshape(dylonlat_SL_IG_12P5km["tpshape_lonlat"]) #输出南-北(上-下)
    #V
    V_interp_linear = interpolate.RegularGridInterpolator((dylonlat_ML_IG_25km["ndy1d_y_lat"], dylonlat_ML_IG_25km["ndy1d_x_lon"]), 
                                                           ndy2d_V, method=method) #输入南-北数据
    ndy2d_V_12P5km = V_interp_linear(ndy12Pkm_xy).reshape(dylonlat_SL_IG_12P5km["tpshape_lonlat"]) #输出南-北(上-下)
    #WS
    WS_interp_linear = interpolate.RegularGridInterpolator((dylonlat_ML_IG_25km["ndy1d_y_lat"], dylonlat_ML_IG_25km["ndy1d_x_lon"]), 
                                                            ndy2d_WS, method=method) #输入南-北数据
    ndy2d_WS_12P5km = WS_interp_linear(ndy12Pkm_xy).reshape(dylonlat_SL_IG_12P5km["tpshape_lonlat"]) #输出南-北(上-下)
    return ndy2d_U_12P5km,ndy2d_V_12P5km,ndy2d_WS_12P5km
  
  
  #计算矢量数据的地面要素垂直变化率
  def dsurface_vector_vertical_rate(self, dymdl_rdata, ltMPQ=["u","v","ws"],  mask2d_common_SL_to_ML=None):
    '''
      dymdl_rdata             : ec原始数据:gh,t,sp
      ltMPQ                   : 多层变量
      mask2d_common_SL_to_ML  : 在原12.5km数据中,地表气压与25km数据公共部分点的布尔索引
    '''
    #判断是否需要的数据都在
    keys=dymdl_rdata.keys()
    if ("gh" not in keys) or ("sp" not in keys) or (ltMPQ[0] not in keys) or (ltMPQ[1] not in keys) or (ltMPQ[2] not in keys):
     return None
    #计算3d温度变化率
    #==================================================
    #多层数据合并为数组(层次从低1000-高10=从上到下)
    #位势高度的单位称作位势米，常用gpm（geopotential metre）
    ndyGH_ML = self.dMulti_Level_merge(dymdl_rdata['gh']    ,arnd=1)  #位势高度(位势米=gpm) 输入(19,67721)从上到下=低1000-高10
    ndyU_ML  = self.dMulti_Level_merge(dymdl_rdata[ltMPQ[0]],arnd=1)  #U风(m/s)
    ndyV_ML  = self.dMulti_Level_merge(dymdl_rdata[ltMPQ[1]],arnd=1)  #V风(m/s)
    ndyWS_ML = self.dMulti_Level_merge(dymdl_rdata[ltMPQ[2]],arnd=1)  #WS风(m/s)
    #垂直差
    ndy_ghdiff_z = ndyGH_ML[1:,]-ndyGH_ML[:-1,]   #z垂直高度差(上层-下层)
    ndy_Udiff_z  = ndyU_ML[1:,] -ndyU_ML[:-1,]    #z垂直U风差(少1层变为18层)
    ndy_Vdiff_z  = ndyV_ML[1:,] -ndyV_ML[:-1,]    #z垂直V风差(少1层变为18层)
    ndy_WSdiff_z = ndyWS_ML[1:,]-ndyWS_ML[:-1,]   #z垂直WS风差(少1层变为18层)
    #风垂直变化率(m/s/变化米 = ,平均)
    U_rate_ML_3d  = ndy_Udiff_z/ndy_ghdiff_z
    V_rate_ML_3d  = ndy_Vdiff_z/ndy_ghdiff_z
    WS_rate_ML_3d = ndy_WSdiff_z/ndy_ghdiff_z
    U_rate_ML_3d  = np.round(np.insert(U_rate_ML_3d,  0, U_rate_ML_3d[0],  axis=0),4) #增加1行到原数组首行(层19, 格点数67721)
    V_rate_ML_3d  = np.round(np.insert(V_rate_ML_3d,  0, V_rate_ML_3d[0],  axis=0),4)
    WS_rate_ML_3d = np.round(np.insert(WS_rate_ML_3d, 0, WS_rate_ML_3d[0], axis=0),4)
    #通过地面气压寻找每个格点的3D层次位置
    #==================================================
    #层次(从低1000-高10hpa)
    ndylevel_1d = np.sort(list(dymdl_rdata['gh'].keys()))[::-1] #从低(大)到高(小)层次(19层)
    MLshape     = dymdl_rdata['gh'][ndylevel_1d[0]].shape #多层变量的shape
    #构建一个所有格点的层次数组,根据地面气压寻找对应的位置的索引,然后对应到所求的 67721=(241, 281)
    if mask2d_common_SL_to_ML is not None:
      ndySP_1d_ML  = dymdl_rdata['sp'][mask2d_common_SL_to_ML] #智网区域25km分辨率的海平面气压(1维形式)
    else:
      ndySP_1d_ML  = dymdl_rdata['sp'].flatten()
    ndylevel_2d    = (ndylevel_1d.reshape(ndylevel_1d.shape[0], -1)).repeat(ndySP_1d_ML.size, axis=1) #上-下(低-高=1000-10)(层次19, 格点数67721) 
    #print(ndylevel_2d) #测试使用
    #根据地面气压寻找对应的位置的索引,然后对应到所求的变化率
    ndySP_diff     = ndylevel_2d-ndySP_1d_ML   #每一行每个元素都减去对应的ndySP数组每个元素#(层次19, 格点数67721)
    #行索引
    ndyrow_loc_idx = np.where(ndySP_diff>0, 1, 0).sum(axis=0) #1d,先找出每个格点标准气压>地面气压的位置=1(顶),否则为0 这就找出了1-0的区域(格点数67721,)=整数
    ndyrow_loc_idx = np.clip(ndyrow_loc_idx, 0, U_rate_ML_3d.shape[0]-1).astype("int32")
    #列索引 lapse_rate_3d_25km中每行中的列位置  ndyrow_loc_idx保存每列的行位置, 从lapse_rate_3d_25km 2维数据每列中选出对应行位置的数据
    ndycol_loc_idx = np.arange(ndyrow_loc_idx.size,dtype="int32")
    # #print(ndylevel_2d[ndyrow_loc_idx,ndycol_loc_idx]) #测试使用
    # #测试-lapse_rate_3d_25km中每列的行位置
    # #ndyrow_loc_idx_2d=ndyrow_loc_idx.reshape(MLshape) #结果1d变为2d 上-下=南-北数据 (89, 105)
    #计算地面到离地面最近的标准气压层之间的垂直变率
    #根据地面气压寻找对应的位置的索引,对应的地面之上的变化率 #(摄氏度/米=-0.0065)
    U_rate_2d_surface =U_rate_ML_3d[ndyrow_loc_idx,ndycol_loc_idx]
    V_rate_2d_surface =V_rate_ML_3d[ndyrow_loc_idx,ndycol_loc_idx]
    WS_rate_2d_surface=WS_rate_ML_3d[ndyrow_loc_idx,ndycol_loc_idx]
    #--------------------------------------------------------------
    U_rate_2d_surface =U_rate_2d_surface.reshape(MLshape) #结果变为#上-下=南-北数据
    V_rate_2d_surface =V_rate_2d_surface.reshape(MLshape) 
    WS_rate_2d_surface=WS_rate_2d_surface.reshape(MLshape) 
    #print(f"min:{np.min(U_rate_2d_surface):.4f},max:{np.max(U_rate_2d_surface):.4f}" ) #范围-0.0022,-0.0106
    return U_rate_2d_surface,V_rate_2d_surface,WS_rate_2d_surface #上-下=南-北数据
  
  
  #计算数据的地面要素垂直变化率
  def dsurface_scalar_vertical_rate(self, dymdl_rdata, sPQ="t", iround=4, mask2d_common_SL_to_ML=None):
    '''
      dymdl_rdata            : ec原始数据:gh,t,sp
      sPQ                    : 多层物理量名
      iround                 : 保存小数位数
      mask2d_common_SL_to_ML : 在原12.5km数据中,地表气压与25km数据公共部分点的布尔索引 
    '''
    #判断是否需要的数据都在
    keys=dymdl_rdata.keys()
    if ("gh" not in keys) or ("sp" not in keys) or (sPQ not in keys):
      if sPQ!="p":
        return None
      else: #说明是气压的地形插值
        dymdl_rdata[sPQ]={}
        for ilev in dymdl_rdata['gh']:
          dymdl_rdata[sPQ][ilev]= np.zeros_like(dymdl_rdata["gh"][ilev],dtype="float32")+ilev
    #计算3d垂直变化率
    #==================================================
    #多层数据合并为数组(层次从低1000-高10=从上到下)
    #位势高度的单位称作位势米，常用gpm(geopotential metre)
    ndyGH_ML = self.dMulti_Level_merge(dymdl_rdata['gh'],arnd=1)  #位势高度(位势米=gpm) 输入(19,67721)从上到下=低1000-高10
    ndyPQ_ML = self.dMulti_Level_merge(dymdl_rdata[sPQ] ,arnd=1)  #多层气温(摄氏度)
    #垂直差
    ndy_ghdiff_z=ndyGH_ML[1:,]-ndyGH_ML[:-1,]     #z垂直高度差(上层-下层)
    ndy_mtdiff_z=ndyPQ_ML[1:,]-ndyPQ_ML[:-1,]      #z垂直温度差(少1层变为18层)
    #温度垂直变化率(摄氏度/米 = -0.0065,平均)
    lapse_rate_ML_3d = ndy_mtdiff_z/ndy_ghdiff_z
    lapse_rate_ML_3d = np.round(np.insert(lapse_rate_ML_3d, 0, lapse_rate_ML_3d[0], axis=0),4) #增加1行到原数组首行(层19, 格点数67721)
    #通过地面气压寻找每个格点的3D层次位置
    #==================================================
    #层次(从低1000-高10hpa)
    ndylevel_1d = np.sort(list(dymdl_rdata['gh'].keys()))[::-1] #从低(大)到高(小)层次(19层)
    MLshape     = dymdl_rdata['gh'][ndylevel_1d[0]].shape #多层变量的shape
    #构建一个所有格点的层次数组,根据地面气压寻找对应的位置的索引,然后对应到所求的 67721=(241, 281)
    # print("===================", dymdl_rdata['sp'].shape, np.array(mask2d_common_SL_to_ML).shape)
    # print("gh============", ndyGH_ML.shape, "t=========", ndyPQ_ML.shape)
    if mask2d_common_SL_to_ML is not None:
      ndySP_1d_ML  = dymdl_rdata['sp'][mask2d_common_SL_to_ML] #智网区域25km分辨率的海平面气压(1维形式)
    else:
      ndySP_1d_ML  = dymdl_rdata['sp'].flatten()
    ndylevel_2d    = (ndylevel_1d.reshape(ndylevel_1d.shape[0], -1)).repeat(ndySP_1d_ML.size, axis=1) #上-下(低-高=1000-10)(层次19, 格点数67721) 
    # print(ndylevel_2d) #测试使用
    #根据地面气压寻找对应的位置的索引,然后对应到所求的变化率
    ndySP_diff     = ndylevel_2d-ndySP_1d_ML   #每一行每个元素都减去对应的ndySP数组每个元素#(层次19, 格点数67721)
    #行索引
    ndyrow_loc_idx = np.where(ndySP_diff>0, 1, 0).sum(axis=0) #1d,先找出每个格点标准气压>地面气压的位置=1(顶),否则为0 这就找出了1-0的区域(格点数67721,)=整数
    ndyrow_loc_idx = np.clip(ndyrow_loc_idx, 0, lapse_rate_ML_3d.shape[0]-1).astype("int32")
    #列索引 lapse_rate_3d_25km中每行中的列位置  ndyrow_loc_idx保存每列的行位置, 从lapse_rate_3d_25km 2维数据每列中选出对应行位置的数据
    ndycol_loc_idx = np.arange(ndyrow_loc_idx.size,dtype="int32")  #
    # #print(ndylevel_2d[ndyrow_loc_idx,ndycol_loc_idx]) #测试使用
    # #测试-lapse_rate_3d_25km中每列的行位置
    # #ndyrow_loc_idx_2d=ndyrow_loc_idx.reshape(MLshape) #结果1d变为2d 上-下=南-北数据 (89, 105)
    #计算地面到离地面最近的标准气压层之间的垂直变化率
    #根据地面气压寻找对应的位置的索引,对应的地面之上的变化率 #(摄氏度/米=-0.0065)
    lapse_rate_2d_surface = lapse_rate_ML_3d[ndyrow_loc_idx,ndycol_loc_idx] 
    lapse_rate_2d_surface = lapse_rate_2d_surface.reshape(MLshape) #结果变为#上-下=南-北数据
    #print(f"min:{np.min(lapse_rate_2d_surface):.4f},max:{np.max(lapse_rate_2d_surface):.4f}" ) #范围-0.0022,-0.0106
    lapse_rate_2d_surface = np.round(lapse_rate_2d_surface, iround)
    return lapse_rate_2d_surface #上-下=南-北数据
    
    
  #最优参数值保存, 应为eta值是在原始粗网格上，插值点是在细网格上
  #需要将细网格误差小的值对应的eta值的位置进行保存到粗网格分辨率上
  def dbest_eta_save(self, ndyeta, ltloc, ndy1d_idx, feta):
    """
      ndyeta : 保存的垂直率调节参数    eg,ec=2d(481, 561) ndyeta[ndyidx_down_N_lat,ndyidx_left_W_lon]=(1682601,)
      ltloc  : 插值的周围四点位置数组列表
    """
    ndyidx_down_N_lat  = ltloc[0]
    ndyidx_up_S_lat    = ltloc[1]
    ndyidx_left_W_lon  = ltloc[2]
    ndyidx_right_E_lon = ltloc[3]
    ndyidx=np.where(ndy1d_idx==True)
    ndyeta[ndyidx_down_N_lat[ndyidx],ndyidx_left_W_lon[ndyidx]]=feta
    ndyeta[ndyidx_down_N_lat[ndyidx],ndyidx_right_E_lon[ndyidx]]=feta
    ndyeta[ndyidx_up_S_lat[ndyidx],  ndyidx_left_W_lon[ndyidx]]=feta
    ndyeta[ndyidx_up_S_lat[ndyidx],  ndyidx_right_E_lon[ndyidx]]=feta
    return ndyeta
    
    
  #找出围绕插值点周围的4个格点
  def dfind_interp_4point(self, dyIntpP, dyGrid):
    '''
      dyIntpP:       插值点的经度,纬度,海拔字典
                     key: lon, lat, alt
      dyGrid:        用于插值的格点经度,纬度,海拔的字典  上-下=南-北数据
                     key:begin_lon, lon_res, Nlon
                         begin_lat, lat_res, Nlat
                         ndy2d_x_lon, ndy2d_y_lat
                         alt
    '''
    #插值点对应四周格点号 dyGrid["ndy2d_x_lon"]是上-下=南-北数据
    ndyidx_left_W_lon  = np.floor((dyIntpP['lon']-dyGrid["begin_lon"])/dyGrid["lon_res"]).astype(int) #西:向下取整 
    ndyidx_right_E_lon = ndyidx_left_W_lon + 1 #东
    ndyidx_right_E_lon[ndyidx_right_E_lon>=dyGrid["Nlon"]]=dyGrid["Nlon"]-1
    #获得从0开始的插值点对应的左下角格点索引号
    ndyidx_up_S_lat    = np.floor((dyIntpP['lat']-dyGrid["begin_lat"])/dyGrid["lat_res"]).astype(int) #南=数组对应上方(南边纬度)
    ndyidx_down_N_lat  = ndyidx_up_S_lat + 1  #北=这里的up其实是实际中的南边,down是北边，因为矩阵是上-下=南-北数据
    ndyidx_down_N_lat[ndyidx_down_N_lat>=dyGrid["Nlat"]]=dyGrid["Nlat"]-1
    #4格点与站点插值
    ndyleft_down_WN  =dyGrid['alt'][ndyidx_down_N_lat, ndyidx_left_W_lon]
    ndyright_down_EN =dyGrid['alt'][ndyidx_down_N_lat, ndyidx_right_E_lon]
    ndyleft_up_WS    =dyGrid['alt'][ndyidx_up_S_lat,   ndyidx_left_W_lon]
    ndyright_up_ES   =dyGrid['alt'][ndyidx_up_S_lat,   ndyidx_right_E_lon]
    #保存
    dfsite_4grid = pd.DataFrame({"site_code":dyIntpP['site_code'], "alt":dyIntpP['alt'],
                                 "LD_WN":ndyleft_down_WN,
                                 "RD_EN":ndyright_down_EN,
                                 "LU_WS":ndyleft_up_WS,
                                 "RU_ES":ndyright_up_ES,
                                 "diff_LD_WN":dyIntpP['alt']-ndyleft_down_WN,
                                 "diff_RD_EN":dyIntpP['alt']-ndyright_down_EN,
                                 "diff_LU_WS":dyIntpP['alt']-ndyleft_up_WS,
                                 "diff_RU_ES":dyIntpP['alt']-ndyright_up_ES})
    return dfsite_4grid
    
    
  #读取EC/CMA-MESO的grib文件变量进行三维插值
  def dRGrib_for_3Dinterp(self, sIn_abs_path, ltSPQ_shortname=["2t","2d","10u","10v","10fg3","mn2t3","mx2t3","tcc"], ltSL_bound=None, ltML_bound=None):
    '''
      sIn_abs_path   : 输入路径
      sSPQ_shortname : 单层变量输入 2d:2米露点温度,10fg3(gust):过去3h10米阵风 mn2t3:过去3h最小2米温度 mx2t3:过去3h最大2米温度
                                    tcc:总云量0-1,lcc:低云量 gfs: 2rh_max:[1,231] 最大相对湿度  2rh_min:[1,232] 最小相对湿度
      sSPQ           : 需要插值的地面变量
      ltSL_bound     : 单层裁剪区域 [纬度0,纬度1,经度0,经度1][iN_SL_bd_begin_y_lat,iN_SL_bd_end_y_lat,iN_SL_bd_begin_x_lon,iN_SL_bd_end_x_lon]
      ltML_bound     : 多层裁剪
      
      from eccodes import *
      with open(dypath_info[ifhour][0]) as fh:
        while 1:
          #加载第1条grib信息,获得第1条grib信息的编号
          igrib = codes_grib_new_from_file(fh)
          if igrib is not None:
            sshortName = codes_get(igrib,"shortName")
            if sshortName=="unknown":
              if codes_get(igrib,"parameterCategory")==6 and codes_get(igrib,"parameterNumber")==1:
                sshortName="tcc" #总云量
              elif codes_get(igrib,"parameterCategory")==1 and codes_get(igrib,"parameterNumber")==8:
                sshortName="tp"  #总降水
            
              print(sshortName, codes_get(igrib,"parameterName"))
              print(codes_get(igrib,"parameterCategory"),codes_get(igrib,"parameterNumber"))
            #释放内存
            codes_release(igrib)
          else:
            break
    '''
    if not os.path.exists(sIn_abs_path):
      return {}
    else:
      #多层变量
      ltMPQ_shortname = []
      if "2t" in ltSPQ_shortname:                      #单层: 2m气温
        ltMPQ_shortname = ltMPQ_shortname + ["t"]      #多层: 气压层气温
      if ("2d"  in ltSPQ_shortname) or \
         ("2r" in ltSPQ_shortname):                    #单层: 2m露点(EC需根据2d和2t计算2rh)/2m相对湿度(grapes直接有2r=2rh)
        ltMPQ_shortname = ltMPQ_shortname + ["r"]      #多层: 气压层相对湿度
      if ("10u" in ltSPQ_shortname) or \
         ("10v" in ltSPQ_shortname):                   #单层: 10m-u/v风
        ltMPQ_shortname = ltMPQ_shortname + ["u","v"]  #多层: 气压层风
      #打开文件
      with open(sIn_abs_path) as fh:
        dydata={} #;ltshortName=[]
        while 1:
          #加载第1条grib信息,获得第1条grib信息的编号
          igrib = codes_grib_new_from_file(fh)
          if igrib is not None:
            #日期
            #date = codes_get(igrib,"dataDate")
            sshortName = codes_get(igrib,"shortName")
            if sshortName=="unknown":
              if codes_get(igrib,"parameterCategory")==6 and codes_get(igrib,"parameterNumber")==1:
                sshortName="tcc" #总云量
              elif codes_get(igrib,"parameterCategory")==1 and codes_get(igrib,"parameterNumber")==8:
                sshortName="tp"  #总降水
              elif codes_get(igrib,"parameterCategory")==1 and codes_get(igrib,"parameterNumber")==231:
                sshortName="2rh_max"  #最大相对湿度
              elif codes_get(igrib,"parameterCategory")==1 and codes_get(igrib,"parameterNumber")==232:
                sshortName="2rh_min"
            # sshortName = codes_get(igrib,"name")
            # print(sshortName)
            # ltshortName.append(sshortName)
            #单层变量-地面/高空
            if sshortName in ["sp","orog"]+ltSPQ_shortname:
              Nj,Ni = codes_get(igrib,"Nj"),codes_get(igrib,"Ni")  #0.0 359.875 -90.0 90.0 =(1441, 2880)
              ndy2d = codes_get_values(igrib).reshape(Nj,Ni).astype("float32")  #上-下(北-南) Surface_pressure 地面气压
              if sshortName=="sp":
                ndy2d = np.around(ndy2d/100.,1) #Pa->hpa
              elif sshortName in ["2t","2d","mn2t3","mx2t3","tmax","tmin"]:  #气温类
                ndy2d = np.around(ndy2d-self.RCAbsZero,1)      #K->℃
              elif sshortName in ["10u","10v","10fg3","gust","10gust"]: #10m风和阵风:3km数据中是10gust,ec中是10fg3
                ndy2d = np.around(ndy2d,1)  #m/s
              elif sshortName in ["tcc"]:   #EC:总云量0-1, 3km: 0-100
                ndy2d = np.around(ndy2d,2)  #成
              elif sshortName in ["2rh_max","2rh_min"]: #CMA-GFS, 相对湿度
                ndy2d = np.around(ndy2d,0)
              #剪裁&上下翻转
              if ltSL_bound is not None: #变为上-下(南-北) 再截取
                ndy2d = np.flipud(ndy2d)[ltSL_bound[0]:ltSL_bound[1]+1,ltSL_bound[2]:ltSL_bound[3]+1]
              #不剪裁=原始
              else:
                ndy2d = np.flipud(ndy2d) #变为上-下(南-北)
              #输出shortname固定
              if sshortName=="2r":      #在grapes-3km里面2m相对湿度是2r,保存为2rh
                dydata["2rh"]= ndy2d
              elif sshortName in ["10fg3","gust","10gust"]: #在ec里面2m阵风是10fg3,输出保存为10gust名
                dydata["10gust"]= ndy2d
              elif sshortName=="sp":   #在ec里面2m阵风是sp,输出保存为sp名
                dydata["sp"]= ndy2d
              else:
                dydata[sshortName]= ndy2d
            #多层变量
            elif sshortName in ["gh"]+ltMPQ_shortname:
              ilevel = codes_get(igrib,"level")               #层次
              if ilevel<=200: #珠峰309到343百帕斯卡之间波动
                codes_release(igrib)
                continue
              Nj,Ni = codes_get(igrib,"Nj"),codes_get(igrib,"Ni")  #60.0 150.0 -10.0 60.0 =(281, 361)
              ndy2d = codes_get_values(igrib).reshape(Nj,Ni).astype("float32")  #上-下(北-南)
              #剪裁&上下翻转
              if ltSL_bound is not None: #变为上-下(南-北) 再截取
                ndy2d = np.flipud(ndy2d)[ltML_bound[0]:ltML_bound[1]+1,ltML_bound[2]:ltML_bound[3]+1]  
              #不剪裁=原始
              else:
                ndy2d = np.flipud(ndy2d) #上-下(南-北)
              #保留小数位
              if sshortName=="t":
                ndy2d = np.around(ndy2d-self.RCAbsZero,1)  #气温K->℃
              else:
                ndy2d = np.around(ndy2d,1) #风,相对湿度
              #已有≥2次
              if sshortName in dydata:
                dydata[sshortName][ilevel]=ndy2d
              #第1次
              else:
                dydata[sshortName]={ilevel:ndy2d}
            #释放内存
            codes_release(igrib)
          else:
            break
        # ltshortName=list(set(ltshortName))
        # print(ltshortName)
        # sys.exit()
        return dydata #上-下(南-北)

  # 读取EC/CMA-MESO的nc文件变量进行三维插值
  def dRNC_for_3Dinterp(self, sIn_abs_path_dt, ltSPQ_shortname=["2t","2d","10u","10v","10fg3","mn2t3","mx2t3","tcc"], ltSL_bound=None, ltML_bound=None):
    """
      sIn_abs_path   : 输入路径
      sSPQ_shortname : 单层变量输入 2d:2米露点温度,10fg3(gust):过去3h10米阵风 mn2t3:过去3h最小2米温度 mx2t3:过去3h最大2米温度
                                    tcc:总云量0-1,lcc:低云量 gfs: 2rh_max:[1,231] 最大相对湿度  2rh_min:[1,232] 最小相对湿度
      ltSL_bound     : 单层裁剪区域 [纬度0,纬度1,经度0,经度1][iN_SL_bd_begin_y_lat,iN_SL_bd_end_y_lat,iN_SL_bd_begin_x_lon,iN_SL_bd_end_x_lon]
      ltML_bound     : 多层裁剪
    """
    # 多层变量
    ltMPQ_shortname = []
    if "2t" in ltSPQ_shortname:  # 单层: 2m气温
      ltMPQ_shortname = ltMPQ_shortname + ["t"]  # 多层: 气压层气温
    if ("2d" in ltSPQ_shortname) or ("2r" in ltSPQ_shortname):  # 单层: 2m露点(EC需根据2d和2t计算2rh)/2m相对湿度(grapes直接有2r=2rh)
      ltMPQ_shortname = ltMPQ_shortname + ["r"]  # 多层: 气压层相对湿度
    if ("10u" in ltSPQ_shortname) or ("10v" in ltSPQ_shortname):  # 单层: 10m-u/v风
      ltMPQ_shortname = ltMPQ_shortname + ["u", "v"]  # 多层: 气压层风
    # 读取数据
    dydata = {}
    # 裁剪经纬度
    sel_lon = [dymdl_Geog["lonlat_SL_IG_mdl"]["begin_lon"], dymdl_Geog["lonlat_SL_IG_mdl"]["end_lon"]]
    sel_lat = [dymdl_Geog["lonlat_SL_IG_mdl"]["begin_lat"], dymdl_Geog["lonlat_SL_IG_mdl"]["end_lat"]]
    if dyCommon_Para["sModel_Region_upper"] in ["GRAPES_12P5KM"]:
      sel_lon = [dymdl_Geog["lonlat_SL_IG_mdl"]["begin_lon"], dymdl_Geog["lonlat_SL_IG_mdl"]["end_lon"]]
      sel_lat = [dymdl_Geog["lonlat_SL_IG_mdl"]["begin_lat"] - 0.25, dymdl_Geog["lonlat_SL_IG_mdl"]["end_lat"] + 0.25]
    for sshortName, sIn_abs_paths in sIn_abs_path_dt.items():
      # 单层变量-地面/高空
      if sshortName in ["sp", "orog"] + ltSPQ_shortname:
        # ndy6d = meb.read_griddata_from_nc(sIn_abs_paths, value_name=sshortName, level=None,
        #                                   member_dim=None, level_dim='isobaricInhPa', time_dim=None,
        #                                   dtime_dim='step', lat_dim='latitude', lon_dim='longitude') # 要素不存在时返回值为None
        # if ndy6d is None:
        #   # ndy2d = np.array([])
        #   print(sshortName + ' is not exist')
        #   continue
        # ndy2d = ndy6d.squeeze() # 压缩数据维度 6->2
        ndy2d, data_info = dyCommon_Para["Class"]["cls_obsdb"].dRObs_Nc(sIn_abs_paths, sshortName,
                                                                        select_lat=sel_lat, select_lon=sel_lon,
                                                                        is_data_info=True)
        if dyCommon_Para["sModel_Region_upper"] in ["GRAPES_12P5KM"]:
          ndy2d = self.dMesh_scalar_interp(dymdl_Geog["lonlat_SL_IG_mdl"], data_info, ndy2d)
        ndy2d = np.flipud(ndy2d)
        # 上-下(北-南)
        if sshortName == "sp":  # Surface_pressure 地面气压
          ndy2d = np.around(ndy2d / 100., 1)  # Pa->hpa
        elif sshortName in ["2t", "2d", "mn2t3", "mx2t3", "tmax", "tmin"]:  # 气温类
          ndy2d = np.around(ndy2d, 1)  # ℃
        elif sshortName in ["10u", "10v", "10fg3", "gust", "10gust"]:  # 10m风和阵风:3km数据中是10gust,ec中是10fg3
          ndy2d = np.around(ndy2d, 1)  # m/s
        elif sshortName in ["tcc"]:  # EC:总云量0-1, 3km: 0-100
          ndy2d = np.around(ndy2d, 2)  # 成
        elif sshortName in ["2rh_max", "2rh_min"]:  # CMA-GFS, 相对湿度
          ndy2d = np.around(ndy2d, 0)
        # 剪裁&上下翻转
        if ltSL_bound is not None:  # 变为上-下(南-北) 再截取
          ndy2d = np.flipud(ndy2d)[ltSL_bound[0]:ltSL_bound[1] + 1, ltSL_bound[2]:ltSL_bound[3] + 1]
        # 不剪裁=原始
        else:
          ndy2d = np.flipud(ndy2d)  # 变为上-下(南-北)
        # 输出shortname固定
        if sshortName == "2r":  # 在grapes-3km里面2m相对湿度是2r,保存为2rh
          dydata["2rh"] = ndy2d
        elif sshortName in ["10fg3", "gust", "10gust"]:  # 在ec里面2m阵风是10fg3,输出保存为10gust名
          dydata["10gust"] = ndy2d
        elif sshortName == "sp":  # 在ec里面2m阵风是sp,输出保存为sp名
          dydata["sp"] = ndy2d
        else:
          dydata[sshortName] = ndy2d
    # 多层变量
      elif sshortName in ["gh"]+ltMPQ_shortname:
        for slevel, sIn_abs_path in sIn_abs_paths.items():
          ndy2d, data_info = dyCommon_Para["Class"]["cls_obsdb"].dRObs_Nc(sIn_abs_path, sshortName,
                                                                          select_lat=sel_lat, select_lon=sel_lon,
                                                                          is_data_info=True)
          if dyCommon_Para["sModel_Region_upper"] in ["GRAPES_12P5KM"]:
            ndy2d = self.dMesh_scalar_interp(dymdl_Geog["lonlat_SL_IG_mdl"], data_info, ndy2d)
          ndy2d = np.flipud(ndy2d)
          # 高度int转换
          ilevel = int(re.findall('\d+', slevel)[0])
          if ilevel <= 200:  # 珠峰309到343百帕斯卡之间波动
            continue
          # 剪裁&上下翻转
          if ltSL_bound is not None:  # 变为上-下(南-北) 再截取
            ndy2d = np.flipud(ndy2d)[ltML_bound[0]:ltML_bound[1] + 1, ltML_bound[2]:ltML_bound[3] + 1]
          # 不剪裁=原始
          else:
            ndy2d = np.flipud(ndy2d)  # 上-下(南-北)
          # 保留小数位
          if sshortName == "t":
            ndy2d = np.around(ndy2d, 1)  # 气温℃
          else:
            ndy2d = np.around(ndy2d, 1)  # 风,相对湿度
          # 已有≥2次
          if sshortName in dydata:
            dydata[sshortName][ilevel] = ndy2d
          # 第1次
          else:
            dydata[sshortName] = {ilevel: ndy2d}
    # print(dydata)
    if "2rh_max" not in list(dydata.keys()) and "2rh_max" in self.ltPQSN_mxmn: self.ltPQSN_mxmn.remove("2rh_max")
    if "2rh_min" not in list(dydata.keys()) and "2rh_min" in self.ltPQSN_mxmn: self.ltPQSN_mxmn.remove("2rh_min")
    return dydata  # 上-下(南-北)

  #对原始grib数据进行扩充物理量和整理
  #扩充10m-ws,等压面层风速
  def dwind_expand(self, dymdl_rdata, ltSL=["10u","10v"], ltML=["u","v"] ):
    #uv风==>ws风速
    dymdl_rdata["10ws"] = np.sqrt(dymdl_rdata[ltSL[0]]**2+dymdl_rdata[ltSL[1]]**2) #扩充10m-ws
    dymdl_rdata["ws"]={ilevel:np.sqrt(dymdl_rdata[ltML[0]][ilevel]**2+dymdl_rdata[ltML[1]][ilevel]**2)  for ilevel in dymdl_rdata[ltML[0]]} #扩充等压面层风速
    return dymdl_rdata
  
  #2m相对湿度(物理量扩展)
  def drh_expand(self, dymdl_rdata):
    ndyrh=self.drelative_humidity(dymdl_rdata["2t"]+self.RCAbsZero,dymdl_rdata["2d"]+self.RCAbsZero)
    dymdl_rdata["2rh"]=np.around(ndyrh,1)
    return dymdl_rdata

  def drelative_humidity(self, temp_array, dewpoint_temp_array):
      """
      用温度、露点温度求相对湿度
      :param temp_array: 温度数组（单位： K）
      :param dewpoint_temp_array:露点温度数组（单位： K）
      :return:相对湿度数组
      """
      temp_svp = self.dsaturation_vapor_pressure(temp_array)
      dewpoint_temp_svp = self.dsaturation_vapor_pressure(dewpoint_temp_array)
      rrh_array = dewpoint_temp_svp / temp_svp * 100
      return rrh_array
  
  def dsaturation_vapor_pressure(self, temp_array):
      """
      通过温度计算饱和水汽压（单位：hpa）
      :param temp_array: 温度数组（单位：K）
      :return:饱和水汽压
      """
      #冰面
      temp_array[temp_array < self.RCAbsZero] = \
              (10**(3.56654 * np.log10(temp_array[temp_array < self.RCAbsZero]) -
               0.0032098 * temp_array[temp_array < self.RCAbsZero] -
              2484.956 / temp_array[temp_array < self.RCAbsZero] + 2.0702294))
      #水面
      temp_array[temp_array >= self.RCAbsZero] = \
          (10 ** (23.832241 - 2949.076 / temp_array[temp_array >= self.RCAbsZero] +
                    (-5.02808) * np.log10(temp_array[temp_array >= self.RCAbsZero]) +
                    (-1.3816E-7) * 10 ** (11.334 - 0.0303998 *
                          temp_array[temp_array >= self.RCAbsZero]) +
                    8.1328E-3 * 10 ** (3.49149 - 1302.8844 /
                      temp_array[temp_array >= self.RCAbsZero])))
      return temp_array


  #读取CLDAS网格实况产品数据
  def dRCLDAS_Vector_Grib(self, sIn_abs_path, ltbound=None, ltkey_name=["10u","10v"]):
    if not os.path.exists(sIn_abs_path):
      return {}
    else:
      #打开文件
      with open(sIn_abs_path) as fh:
        dydata={ltkey_name[0]:None,ltkey_name[1]:None}
        for skey_name in ltkey_name:
          igrib = codes_grib_new_from_file(fh)
          if igrib is not None:
            sshortName = codes_get(igrib,"shortName")
            #地面变量
            Nj,Ni = codes_get(igrib,"Nj"),codes_get(igrib,"Ni")  #0.0 359.875 -90.0 90.0 =(1201, 1401)
            ndy2d = codes_get_values(igrib).reshape(Nj,Ni)  #上-下(北-南)
            #保留小数位
            if sshortName in ["10u","10v"]:
              ndy2d = np.around(ndy2d,1)  #m/s
            #剪裁
            if ltbound is not None: #变为上-下(南-北) 再截取
              ndy2d = np.flipud(ndy2d)[ltbound[0]:ltbound[1]+1,ltbound[2]:ltbound[3]+1]  
            #不剪裁=原始
            else:
              ndy2d = np.flipud(ndy2d) #上-下(南-北)
            codes_release(igrib) #释放内存
            dydata[skey_name]=ndy2d
        return dydata[ltkey_name[0]], dydata[ltkey_name[1]]
    
    
  #读取CLDAS网格实况产品数据
  def dRCLDAS_Grib(self, sIn_abs_path, ltbound=None):
    if not os.path.exists(sIn_abs_path):
      return {}
    else:
      #打开文件
      with open(sIn_abs_path) as fh:
       igrib = codes_grib_new_from_file(fh)
       if igrib is not None:
         sshortName = codes_get(igrib,"shortName")
         #地面变量
         Nj,Ni = codes_get(igrib,"Nj"),codes_get(igrib,"Ni")  #0.0 359.875 -90.0 90.0 =(1201, 1401)
         ndy2d = codes_get_values(igrib).reshape(Nj,Ni)  #上-下(北-南)
         #保留小数位
         if sshortName in ["2t"]:
           ndy2d = np.around(ndy2d-self.RCAbsZero,1)  #K->℃
         #剪裁
         if ltbound is not None: #变为上-下(南-北) 再截取
           ndy2d = np.flipud(ndy2d)[ltbound[0]:ltbound[1]+1,ltbound[2]:ltbound[3]+1]  
         #不剪裁=原始
         else:
           ndy2d = np.flipud(ndy2d) #上-下(南-北)
         codes_release(igrib) #释放内存
         return ndy2d
    
  #输出空间插值数据
  def dmulti_WS3_Interp(self, args):
    return self.dWS3_Interp(*args)
  def dWS3_Interp(self, sout_abs_path, dyInterp, ltInterp_keys=None, dyattr=None):
    try:
      temp_path = sout_abs_path+".tmp"
      if os.path.exists(temp_path):os.remove(temp_path)
      if os.path.exists(sout_abs_path):os.remove(sout_abs_path)
      if ltInterp_keys is None:ltInterp_keys=dyInterp.keys()
      #print(temp_path)
      with h5py.File(temp_path,'w') as fh:
        #写属性
        if dyattr is not None:
          for skey in dyattr:
            if dyattr[skey] is None:
              fh.attrs[skey] = "None"
            else:
              fh.attrs[skey] = dyattr[skey]
        #写要素数据
        for skey in ltInterp_keys:
          if skey in dyInterp:
            #print('skey:', skey)
            #if skey.find('gamma') >= 0:
            #  continue
            fh.create_dataset(skey, data=dyInterp[skey], compression="gzip", compression_opts=6)
            #print(temp_path, ':', skey, ':start ', datetime.datetime.now())
            #if type(dyInterp[skey]) == np.ndarray:
            #  chunks_value = dyInterp[skey].shape
            #elif type(dyInterp[skey]) == list:
            #  chunks_value = (len(dyInterp[skey]),)
            #else:
            #  chunks_value = None
            #if chunks_value is None:
            #  fh.create_dataset(skey, data=dyInterp[skey], compression="gzip", compression_opts=6)
            #else:
            #  fh.create_dataset(skey, data=dyInterp[skey], compression="gzip", compression_opts=6, chunks=chunks_value)
            #print(temp_path, ':', skey, ':over ', datetime.datetime.now())

      #print(temp_path, ' rename start')
      time.sleep(3)
      os.rename(temp_path, sout_abs_path)
      #print(temp_path, ' rename over')
      return temp_path
    except Exception as err:
      print('except:', str(err))
      return None
  
  #输出空间插值数据
  def dCopy_rlt(self, ssrc_abs_path, sdst_abs_path):
    temp_path = sdst_abs_path+".tmp"
    if os.path.exists(temp_path):os.remove(temp_path)
    copyfile(ssrc_abs_path, temp_path)
    if os.path.exists(sdst_abs_path):os.remove(sdst_abs_path)
    time.sleep(3)
    os.rename(temp_path, sdst_abs_path)
    return
  
  #读算法eta参数
  def dRFRI_eta(self, sIn_abs_path):
    dydata={}
    with h5py.File(sIn_abs_path,'r') as fh:
      ndydata=np.round(fh[skey][...],1)
    return ndydata  
  
  #读空间插值数据
  def dRS3_Interp(self, sIn_abs_path, dyround=None):
    dydata={}
    with h5py.File(sIn_abs_path,'r') as fh:
      ltkeys = list(fh.keys())
      if dyround is None:
        dyround = {skey:2 if skey=="tcc" else 1 for skey in ltkeys}
      elif np.isscalar(dyround):
        dyround = {skey:dyround for skey in ltkeys}
      for skey in ltkeys:
        ndydata=fh[skey][...]
        if skey=="site":
          dydata[skey]= ndydata
        else:
          dydata[skey]= np.round(ndydata,dyround[skey])
    return dydata
  

  #不同时效不同要素的eta文件路径
  def deta_path(self, sResult_Main_Path, S3_dir, sS3_method, sModel_Region, sReso_dir, seta_dir, 
                sPhyQ_shortname, sYMD_mdl_begin, shour_mdl_begin, iForecast_hour, recall=False):
    sModel_Region_upper = sModel_Region.upper()
    #---参数路径--------------------------------------------------------------
    iday_ago=1
    #CMA_MESO-3km
    if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
      #20点和08点从第6个预报时效开始,其余起报点采用从第5个预报时效开始作为0场时间点
      if shour_mdl_begin in ["02","05","11","14","17"]:
        if 5<=iForecast_hour and iForecast_hour<=28:
          iday_ago=1
        elif 29<=iForecast_hour and iForecast_hour<=36:
          iday_ago=2
      elif shour_mdl_begin=="08":
        if 6<=iForecast_hour and iForecast_hour<=29:
          iday_ago=1
        elif 30<=iForecast_hour and iForecast_hour<=36:
          iday_ago=2
      elif shour_mdl_begin=="20":
        if 6<=iForecast_hour and iForecast_hour<=29:
          iday_ago=2
        elif 30<=iForecast_hour and iForecast_hour<=36:
          iday_ago=3
      elif shour_mdl_begin=="23":
        if 5<=iForecast_hour and iForecast_hour<=28:
          iday_ago=2
        elif 29<=iForecast_hour and iForecast_hour<=36:
          iday_ago=3
    #CMA_GFS-25km
    elif sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_25KM","GRAPES_GFS","CMA_GFS"]:
      #相对模式时间08:6-29时效用前1天参数,30-36时效用前2天参数;20:6-29时效用前2天参数,30-36时效用前3天参数
      if shour_mdl_begin in ["02","08","14"]:
        if 5<=iForecast_hour and iForecast_hour<=29:
          iday_ago=1
        elif 30<=iForecast_hour and iForecast_hour<=53:
          iday_ago=2
        elif 54<=iForecast_hour and iForecast_hour<=77:
          iday_ago=3
        elif 78<=iForecast_hour and iForecast_hour<=101:
          iday_ago=4
        elif 102<=iForecast_hour and iForecast_hour<=125:
          iday_ago=5
      elif shour_mdl_begin in ["20"]:
        if 6<=iForecast_hour and iForecast_hour<=29:
          iday_ago=2
        elif 30<=iForecast_hour and iForecast_hour<=53:
          iday_ago=3
        elif 54<=iForecast_hour and iForecast_hour<=77:
          iday_ago=4
        elif 78<=iForecast_hour and iForecast_hour<=101:
          iday_ago=5
        elif 102<=iForecast_hour and iForecast_hour<=125:
          iday_ago=6
    #EC-12.5km
    else:
      #相对模式时间08:6-29时效用前1天参数,30-36时效用前2天参数;20:6-29时效用前2天参数,30-36时效用前3天参数
      if shour_mdl_begin=="08":
        if 6<=iForecast_hour and iForecast_hour<=29:
          iday_ago=1
        elif 30<=iForecast_hour and iForecast_hour<=53:
          iday_ago=2
        elif 54<=iForecast_hour and iForecast_hour<=77:
          iday_ago=3
        elif 78<=iForecast_hour and iForecast_hour<=101:
          iday_ago=4
        elif 102<=iForecast_hour and iForecast_hour<=125:
          iday_ago=5
      elif shour_mdl_begin=="20":
        if 6<=iForecast_hour and iForecast_hour<=29:
          iday_ago=2
        elif 30<=iForecast_hour and iForecast_hour<=53:
          iday_ago=3
        elif 54<=iForecast_hour and iForecast_hour<=77:
          iday_ago=4
        elif 78<=iForecast_hour and iForecast_hour<=101:
          iday_ago=5
        elif 102<=iForecast_hour and iForecast_hour<=125:
          iday_ago=6
    sYMD_eta_begin = self.cls_myfun.dtimes_ago(sYMD_mdl_begin, iday_ago)
    #每天参数路径
    sIn_eta_file_name = "_".join([f"{iForecast_hour:03d}",sPhyQ_shortname,"eta"]) +".h5"
    sIn_sub1_path     = os.path.join(sResult_Main_Path,S3_dir, sS3_method, sModel_Region, sReso_dir, 
                                     sYMD_eta_begin[0:4], sYMD_eta_begin[0:8], shour_mdl_begin, seta_dir)
    sIn_1d_eta_abs_path = os.path.join(sIn_sub1_path, sIn_eta_file_name)
    #每日参数不存在
    #if not os.path.exists(sIn_1d_eta_abs_path):
    #恒定参数路径
    sIn_sub2_path      = os.path.join(sResult_Main_Path, S3_dir, sS3_method, sModel_Region, 
                                      sReso_dir, seta_dir, shour_mdl_begin)
    sIn_cmn_eta_abs_path   = os.path.join(sIn_sub2_path, sIn_eta_file_name)
    return sIn_1d_eta_abs_path, sIn_cmn_eta_abs_path


  def dS3YMDH_Interp_eta(self, sModel_Region_upper, smdl_YMDH_begin, iRFrst_hour):
    #如果是当天获得的模式结果,提前天数从1开始
    #如果是第二天获得的模式结果, 提前天数从2开始
    """
      iRFrst_hour : 模式的预报时效
    """
    iday_ago=1
    if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
      if smdl_YMDH_begin[8:] in ["02","05","08","11","14","17"]:
        if 5<=iRFrst_hour and iRFrst_hour<=29:
          iday_ago=1
        elif 30<=iRFrst_hour and iRFrst_hour<=53:
          iday_ago=2
      elif smdl_YMDH_begin[8:] in ["20","23"]:
        if 5<=iRFrst_hour and iRFrst_hour<=29:
          iday_ago=2
        elif 30<=iRFrst_hour and iRFrst_hour<=53:
          iday_ago=3
    elif sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_25KM","GRAPES_GFS","CMA_GFS"]:
      if smdl_YMDH_begin[8:] in ["02","08","14"]:
        if 5<=iRFrst_hour and iRFrst_hour<=29:
          iday_ago=1
        elif 30<=iRFrst_hour and iRFrst_hour<=53:
          iday_ago=2
        elif 54<=iRFrst_hour and iRFrst_hour<=77:
          iday_ago=3
      elif smdl_YMDH_begin[8:]=="20":
        if 5<=iRFrst_hour and iRFrst_hour<=29:
          iday_ago=2
        elif 30<=iRFrst_hour and iRFrst_hour<=53:
          iday_ago=3
        elif 54<=iRFrst_hour and iRFrst_hour<=77:
          iday_ago=4
    elif sModel_Region_upper in ["EC_12P5KM"]:
      if smdl_YMDH_begin[8:]=="08":
        if 6<=iRFrst_hour and iRFrst_hour<=29:
          iday_ago=1
        elif 30<=iRFrst_hour and iRFrst_hour<=53:
          iday_ago=2
        elif 54<=iRFrst_hour and iRFrst_hour<=77:
          iday_ago=3
      elif smdl_YMDH_begin[8:]=="20":
        if 6<=iRFrst_hour and iRFrst_hour<=29:
          iday_ago=2
        elif 30<=iRFrst_hour and iRFrst_hour<=53:
          iday_ago=3
        elif 54<=iRFrst_hour and iRFrst_hour<=77:
          iday_ago=4
    sYMDH_S3_eta = self.cls_myfun.dtimes_ago(smdl_YMDH_begin, iday_ago, sformat="%Y%m%d%H")
    return sYMDH_S3_eta

  #最优参数时的站点评分
  def dscore_site_best_eta(self, sPhyQ_shortname, dyIntp_info, dymdl_rdata, ndyVR_srf_2d, ndyobs_site, ndybest_eta, fthreshold):
    # dybest_eta["site"] = ltSlt_Site_Code
    #地形插值#上-下(南-北)
    ndyinterp_lr = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, ndyVR_srf_2d, eta=ndybest_eta, skey=sPhyQ_shortname)
    #智网误差#上-下(南-北)
    ndydiff_lr = ndyinterp_lr-ndyobs_site    #智网区
    ndyAE_lr   = np.abs(ndydiff_lr)          #智网区绝对误差AE
    fMAE_lr    = np.nanmean(ndyAE_lr)        #中国区平均绝对误差
    fMAE_lr    = np.round(fMAE_lr,3)
    fhit_lr    = (ndyAE_lr<=fthreshold).sum()/np.count_nonzero(~np.isnan(ndyAE_lr)) #中国区准确率
    fhit_lr    = np.round(fhit_lr,3)
    return {"MAE_lr":fMAE_lr,"HIT_lr":fhit_lr}
  
  #求解最优参数
  def dbest_eta_site(self, sPhyQ_shortname, dyIntp_info, dymdl_rdata, ndyobs_site, ndyVR_srf_2d, ltPara_Loss_cycle, fthreshold):
    #双线性插值
    #需要插值的点:数组合并为[[纬度 经度]] [n,2]
    ndyInterp_xy =  np.vstack((dyIntp_info['lat'], dyIntp_info['lon'])).T
    interp_linear = interpolate.RegularGridInterpolator((dymdl_rdata["ndy1d_y_lat"], dymdl_rdata["ndy1d_x_lon"]), 
                                                         dymdl_rdata[sPhyQ_shortname], method='linear')  #输入上-下(南-北)数据
    ndyinterp_bi = interp_linear(ndyInterp_xy)
    ndydiff_bi = ndyinterp_bi-ndyobs_site
    ndyAE_bi   = np.abs(ndydiff_bi)                                         #站点绝对误差AE
    fMAE_bi    = np.nanmean(ndyAE_bi)                                       #站点平均绝对误差
    fMAE_bi    = np.round(fMAE_bi,3)
    fhit_bi    = (ndyAE_bi<=fthreshold).sum()/np.count_nonzero(~np.isnan(ndyAE_bi)) #站点准确率
    fhit_bi    = np.round(fhit_bi,3)
    dyScore    = {"MAE_bi":fMAE_bi,"HIT_bi":fhit_bi}
    #------------------------------------------------
    #插值后保存站点最优参数
    ndybest_eta    = np.zeros(ndyobs_site.size,dtype="float32") 
    ndyAE_best_eta = ndyAE_bi.copy()  #GFS(1198,1401)=1678398
    #遍历损失参数
    for fpara_eta in ltPara_Loss_cycle[0:]:
      #地形插值#上-下(南-北)
      ndyinterp_lr = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, ndyVR_srf_2d, eta=fpara_eta, skey=sPhyQ_shortname)
      #智网误差#上-下(南-北)
      ndydiff_lr = ndyinterp_lr-ndyobs_site #智网区
      ndyAE_lr   = np.abs(ndydiff_lr)       #智网区绝对误差AE
      fMAE_lr    = np.nanmean(ndyAE_lr)     #中国区平均绝对误差
      fMAE_lr    = np.round(fMAE_lr,3)
      fhit_lr    = (ndyAE_lr<=fthreshold).sum()/np.count_nonzero(~np.isnan(ndyAE_lr)) #中国区准确率
      fhit_lr    = np.round(fhit_lr,3)
      #找出最小绝对误差对应的位置
      ndyidx_best_2d =ndyAE_lr<ndyAE_best_eta #找到最优二维索引
      ndyAE_best_eta[ndyidx_best_2d]=ndyAE_lr[ndyidx_best_2d]
      ndybest_eta[ndyidx_best_2d]=fpara_eta
      # if self.iDebug>=1: print(f"{sPhyQ_shortname}-{fpara_eta:.1f} : {fMAE_lr:.3f} {fMAE_bi:.3f} | "\
                                                                   # f"{fhit_lr:.3f} {fhit_bi:.3f}")
    ndybest_eta=np.round(ndybest_eta,1)
    return ndybest_eta, dyScore
  

  #双线插值模式结果和评分
  def dBI_Grid_score(self, dyIntp_info, dymdl_rdata, dyobs_grid, dyPara_ini_info, sPhyQ_shortname):
    #双线性插值
    #需要插值的点:数组合并为[[纬度 经度]] [n,2]
    ndyInterp_xy =  np.vstack((dyIntp_info['lat'], dyIntp_info['lon'])).T
    interp_linear = interpolate.RegularGridInterpolator((dymdl_rdata["ndy1d_y_lat"], dymdl_rdata["ndy1d_x_lon"]), 
                                                         dymdl_rdata[sPhyQ_shortname], method='linear')  #输入上-下(南-北)数据
    ndyinterp_bi = interp_linear(ndyInterp_xy)
    #双线性插值结果1d-2d
    ndyinterp_bi=ndyinterp_bi.reshape(dyIntp_info["2dshape"])
    #智网误差#上-下(南-北)
    ndydiff_bi     = ndyinterp_bi - dyobs_grid[sPhyQ_shortname]  #智网区误差
    ndyAE_bi       = np.abs(ndydiff_bi)                          #智网区绝对误差AE
    ndyAE_bi_China = ndyAE_bi[dyIntp_info["mask_area"]]          #中国区绝对误差AE
    fMAE_bi_China  = np.nanmean(ndyAE_bi_China)                  #中国区平均绝对误差
    fMAE_bi_China  = np.round(fMAE_bi_China,3)
    fhit_bi_China  = (ndyAE_bi_China<=dyPara_ini_info["threshold"][sPhyQ_shortname]).sum()/np.count_nonzero(~np.isnan(ndyAE_bi_China)) #中国区准确率
    fhit_bi_China  = np.round(fhit_bi_China,3)
    dyScore = {"AE_bi":ndyAE_bi,"MAE_bi_China":fMAE_bi_China,"HIT_bi_China":fhit_bi_China}
    if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
      ndyAE_bi_Proce = ndyAE_bi[dyIntp_info["mask_prov"]]
      fMAE_bi_Proce  = np.nanmean(ndyAE_bi_Proce)            #中国区平均绝对误差
      fMAE_bi_Proce  = np.round(fMAE_bi_Proce,3)
      fhit_bi_Proce  = (ndyAE_bi_Proce<=dyPara_ini_info["threshold"][sPhyQ_shortname]).sum()/np.count_nonzero(~np.isnan(ndyAE_bi_Proce)) #中国区准确率
      fhit_bi_Proce  = np.round(fhit_bi_Proce,3)
      dyScore.update({"MAE_bi_Proce":fMAE_bi_Proce,"HIT_bi_Proce":fhit_bi_Proce})
    return dyScore
  
  #格点最优参数求解
  def dbest_eta_grid(self, sPhyQ_shortname, dyIntp_info, dymdl_rdata, ndyobs_grid, ndyVR_srf_2d, ltPara_Loss_cycle, dyPara_ini_info):
    #双线性插值
    #需要插值的点:数组合并为[[纬度 经度]] [n,2]
    ndyInterp_xy  =  np.vstack((dyIntp_info['lat'], dyIntp_info['lon'])).T
    interp_linear = interpolate.RegularGridInterpolator((dymdl_rdata["ndy1d_y_lat"], dymdl_rdata["ndy1d_x_lon"]), 
                                                         dymdl_rdata[sPhyQ_shortname], method='linear')  #输入上-下(南-北)数据
    ndyinterp_bi = interp_linear(ndyInterp_xy)
    #双线性插值结果1d-2d
    ndyinterp_bi=ndyinterp_bi.reshape(dyIntp_info["2dshape"])
    #智网误差#上-下(南-北)
    ndydiff_bi     = ndyinterp_bi - ndyobs_grid            #智网区误差
    ndyAE_bi       = np.abs(ndydiff_bi)                    #智网区绝对误差AE
    ndyAE_bi_China = ndyAE_bi[dyIntp_info["mask_area"]]    #中国区绝对误差AE
    fMAE_bi_China  = np.nanmean(ndyAE_bi_China)            #中国区平均绝对误差
    fMAE_bi_China  = np.round(fMAE_bi_China,3)
    fhit_bi_China  = (ndyAE_bi_China<=dyPara_ini_info["threshold"][sPhyQ_shortname]).sum()/np.count_nonzero(~np.isnan(ndyAE_bi_China)) #中国区准确率
    fhit_bi_China  = np.round(fhit_bi_China,3)
    dyScore={"MAE_bi_China":fMAE_bi_China,"HIT_bi_China":fhit_bi_China}
    if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
      ndyAE_bi_Proce = ndyAE_bi[dyIntp_info["mask_prov"]]
      fMAE_bi_Proce  = np.nanmean(ndyAE_bi_Proce)            #中国区平均绝对误差
      fMAE_bi_Proce  = np.round(fMAE_bi_Proce,3)
      fhit_bi_Proce  = (ndyAE_bi_Proce<=dyPara_ini_info["threshold"][sPhyQ_shortname]).sum()/np.count_nonzero(~np.isnan(ndyAE_bi_Proce)) #中国区准确率
      fhit_bi_Proce  = np.round(fhit_bi_Proce,3)
      if self.iDebug>=2:print(f"{sPhyQ_shortname}-bi--China : {fMAE_bi_China:.3f} | {fhit_bi_China:.3f} "+\
                                                 f"| Proce : {fMAE_bi_Proce:.3f} | {fhit_bi_Proce:.3f}")
      dyScore.update({"MAE_bi_Proce":fMAE_bi_Proce,"HIT_bi_Proce":fhit_bi_Proce})
    else:
      if self.iDebug>=2:print(f"{sPhyQ_shortname}-bi--China : {fMAE_bi_China:.3f} | {fhit_bi_China:.3f}")
    ndybest_eta    = np.zeros(dyIntp_info["2dshape"],dtype="float32") 
    ndyAE_best_eta = ndyAE_bi.copy()  #GFS(1198,1401)=1678398
    #遍历损失参数
    for fpara_eta in ltPara_Loss_cycle[0:]:
      #地形插值#上-下(南-北)
      ndyinterp_lr = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, ndyVR_srf_2d, eta=fpara_eta, skey=sPhyQ_shortname)
      ndyinterp_lr = ndyinterp_lr.reshape(dyIntp_info["2dshape"]) #重新reshape
      #智网误差#上-下(南-北)
      ndydiff_lr   = ndyinterp_lr-ndyobs_grid  #智网区
      ndyAE_lr     = np.abs(ndydiff_lr)        #智网区绝对误差AE
      #找出最小绝对误差对应的位置
      ndyidx_best_2d =ndyAE_lr<ndyAE_best_eta  #找到最优二维索引
      ndyAE_best_eta[ndyidx_best_2d]=ndyAE_lr[ndyidx_best_2d]
      ndybest_eta[ndyidx_best_2d]=fpara_eta
      ndyAE_lr_China = ndyAE_lr[dyIntp_info["mask_area"]]                            #中国区绝对误差AE
      fMAE_lr_China  = np.nanmean(ndyAE_lr_China)                                             #中国区平均绝对误差
      fMAE_lr_China  = np.round(fMAE_lr_China,3)
      fhit_lr_China  = (ndyAE_lr_China<=dyPara_ini_info["threshold"][sPhyQ_shortname]).sum()/np.count_nonzero(~np.isnan(ndyAE_lr_China)) #中国区准确率
      fhit_lr_China  = np.round(fhit_lr_China,3)
      if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
        ndyAE_lr_Proce = ndyAE_lr[dyIntp_info["mask_prov"]]
        fMAE_lr_Proce  = np.nanmean(ndyAE_lr_Proce)            #中国区平均绝对误差
        fMAE_lr_Proce  = np.round(fMAE_lr_Proce,3)
        fhit_lr_Proce  = (ndyAE_lr_Proce<=dyPara_ini_info["threshold"][sPhyQ_shortname]).sum()/np.count_nonzero(~np.isnan(ndyAE_lr_Proce)) #中国区准确率
        fhit_lr_Proce  = np.round(fhit_lr_Proce,3)
        if self.iDebug>=2:print(f"{sPhyQ_shortname}-{fpara_eta:.1f}-China : {fMAE_lr_China:.3f} | {fhit_lr_China:.3f} "+\
                                                                f"| Proce : {fMAE_lr_Proce:.3f} | {fhit_lr_Proce:.3f}")
      else:
        if self.iDebug>=2:print(f"{sPhyQ_shortname}-{fpara_eta:.1f} : {fMAE_lr_China:.3f} | {fhit_lr_China:.3f}")
    return ndybest_eta,dyScore

  #最优参数时的格点评分
  def dscore_grid_best_eta(self, sPhyQ_shortname, dyIntp_info, dymdl_rdata, ndyVR_srf_2d, ndyobs_grid, ndybest_eta, dyPara_ini_info):
    #地形插值#上-下(南-北)
    ndyinterp_lr = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, ndyVR_srf_2d, eta=ndybest_eta, skey=sPhyQ_shortname)
    ndyinterp_lr = ndyinterp_lr.reshape(dyIntp_info["2dshape"]) #重新reshape
    #智网误差#上-下(南-北)
    ndydiff_lr     = ndyinterp_lr-ndyobs_grid             #智网区
    ndyAE_lr       = np.abs(ndydiff_lr)                   #智网区绝对误差AE
    ndyAE_lr_China = ndyAE_lr[dyIntp_info["mask_area"]]   #中国区绝对误差AE
    fMAE_lr_China  = np.nanmean(ndyAE_lr_China)           #中国区平均绝对误差
    fMAE_lr_China  = np.round(fMAE_lr_China,3)
    fhit_lr_China  = (ndyAE_lr_China<=dyPara_ini_info["threshold"][sPhyQ_shortname]).sum()/np.count_nonzero(~np.isnan(ndyAE_lr_China)) #中国区准确率
    fhit_lr_China  = np.round(fhit_lr_China,3)
    dyScore = {"MAE_lr_China":fMAE_lr_China,"HIT_lr_China":fhit_lr_China}
    if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
      ndyAE_lr_Proce = ndyAE_lr[dyIntp_info["mask_prov"]]
      fMAE_lr_Proce  = np.nanmean(ndyAE_lr_Proce)           #中国区平均绝对误差
      fMAE_lr_Proce  = np.round(fMAE_lr_Proce,3)
      fhit_lr_Proce  = (ndyAE_lr_Proce<=dyPara_ini_info["threshold"][sPhyQ_shortname]).sum()/np.count_nonzero(~np.isnan(ndyAE_lr_Proce)) #中国区准确率
      fhit_lr_Proce  = np.round(fhit_lr_Proce,3)
      dyScore.update({"MAE_lr_Proce":fMAE_lr_Proce,"HIT_lr_Proce":fhit_lr_Proce})
    return dyScore
  
  #初始化工作进程
  def init_si_process(self, _dyIntp_info, _dymdl_Geog, _dypath_info, _dyPara_ini_info, _dyCommon_Para):
    # 全局变量
    global dyIntp_info, dymdl_Geog, dypath_info, dyPara_ini_info, dyCommon_Para
    dyIntp_info     = _dyIntp_info
    dymdl_Geog      = _dymdl_Geog
    dypath_info     = _dypath_info
    dyPara_ini_info = _dyPara_ini_info
    dyCommon_Para   = _dyCommon_Para
    return
  #3d插值-串行(n个物理量-n个预报时效)
  def dSerial_mdl_3d_Interp_nPQ(self, ltfhours, dyIntp_info, dymdl_Geog, dypath_info, dyPara_ini_info, dyCommon_Para):
    self.init_si_process(dyIntp_info, dymdl_Geog, dypath_info, dyPara_ini_info, dyCommon_Para)
    dyInterp_rlt_nfh={};dymdl_rdata_nfh={}
    for ifhour in ltfhours:
      dyIntp_rlt, dymdl_rdata=self.dmdl_3d_Interp_nPQ(ifhour) 
      dyInterp_rlt_nfh[ifhour]=dyIntp_rlt
      dymdl_rdata_nfh[ifhour] =dymdl_rdata
    return dyInterp_rlt_nfh, dymdl_rdata_nfh
  #3d插值-并行(n个物理量-n个预报时效)
  def dPool_mdl_3d_Interp_nPQ(self, ltfhours, dyIntp_info, dymdl_Geog, dypath_info, dyPara_ini_info, dyCommon_Para):
    in_cpu_core = mp.cpu_count()
    iN_file_proces=np.min([len(ltfhours),in_cpu_core,dyPara_ini_info["Pool"]["FH_max_pcount"]])
    if self.iDebug>=1:print("FH_parallel:",iN_file_proces)
    pool = mp.Pool(processes = iN_file_proces, initializer=self.init_si_process, initargs=(dyIntp_info, dymdl_Geog, dypath_info, dyPara_ini_info, dyCommon_Para))
    pool_result = pool.map_async(self.dmdl_3d_Interp_nPQ, ltfhours)
    try:
      res = pool_result.get(timeout=dyPara_ini_info["Pool"]["FH_DI_timeout"])
    except mp.TimeoutError:
      pool.terminate()
      print("timeout:{}s".format(dyPara_ini_info["Pool"]["FH_DI_timeout"]))
      sys.exit()
    else:
      pool.close()
      pool.join()
    #保存数据
    dyInterp_rlt_nfh={};dymdl_rdata_nfh={}
    for ifhour, [dyIntp_rlt,dymdl_rdata] in zip(ltfhours,pool_result.get()):
      dyInterp_rlt_nfh[ifhour]=dyIntp_rlt
      dymdl_rdata_nfh[ifhour]=dymdl_rdata
    return dyInterp_rlt_nfh, dymdl_rdata_nfh
  #模式场三维插值(多要素)
  def dmdl_3d_Interp_nPQ(self, ifhour):
    print("Interp_t:",ifhour)
    if dypath_info[ifhour][1]==[]: return #说明不需要输出或升级
    sModel_Region_upper = dyCommon_Para["sModel_Region_upper"]
    #模式原瞬时插值文件路径循环-实时
    sfhour = "%03d"%ifhour
    #读取grib的地面和3D数据文件
    if sModel_Region_upper in ["EC_12P5KM"]:
      ltSPQ_shortname=[]
      if "2t" in self.ltPQSN_Intp:
        ltSPQ_shortname.append("2t")
      if "2rh" in self.ltPQSN_Intp:
        if "2t" in ltSPQ_shortname:
          ltSPQ_shortname = ltSPQ_shortname + ["2d"]
        else:
          ltSPQ_shortname = ltSPQ_shortname + ["2d","2t"]
      if "10ws" in self.ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["10u","10v"]
      if '2t_max' in self.ltPQSN_mxmn:
        ltSPQ_shortname.append("mx2t3")
      if '2t_min' in self.ltPQSN_mxmn:
        ltSPQ_shortname.append("mn2t3")
      if '10gust' in self.ltPQSN_Intp:
        ltSPQ_shortname.append("10fg3")
      if 'tcc' in self.ltPQSN_Intp:
        ltSPQ_shortname.append("tcc")
      # 修改数据读取
      dymdl_rdata = self.dRNC_for_3Dinterp(dypath_info[ifhour][0], ltSPQ_shortname=ltSPQ_shortname)
      #对原始grib数据进行扩充物理量和整理 #扩充10m-ws,等压面层风速,2m相对湿度
      if "10u" in dymdl_rdata and "10v" in dymdl_rdata:
        dymdl_rdata = self.dwind_expand(dymdl_rdata)
      if "2t" in dymdl_rdata and "2d" in dymdl_rdata:
        dymdl_rdata = self.drh_expand(dymdl_rdata)
      if "tcc" in self.ltPQSN_Intp:
        dymdl_rdata["tcc"] = np.around(dymdl_rdata["tcc"] *100) #总云量变从0-1变为0-100
    elif sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_25KM","GRAPES_GFS","CMA_GFS"]: #0.0625-60.0625, 
      ltSPQ_shortname=[]
      if "2t" in self.ltPQSN_Intp:
        ltSPQ_shortname.append("2t")
      if '2t_max' in self.ltPQSN_mxmn:
        ltSPQ_shortname.append("tmax")
      if '2t_min' in self.ltPQSN_mxmn:
        ltSPQ_shortname.append("tmin")
      if "2rh" in self.ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["2r"]
      if "2rh_max" in self.ltPQSN_mxmn:
        ltSPQ_shortname = ltSPQ_shortname + ["2rh_max"]
      if "2rh_min" in self.ltPQSN_mxmn:
        ltSPQ_shortname = ltSPQ_shortname + ["2rh_min"]
      if "10ws" in self.ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["10u","10v"]
      if '10gust' in self.ltPQSN_Intp:
        ltSPQ_shortname.append("gust")
      if 'tcc' in self.ltPQSN_Intp:
        ltSPQ_shortname.append("tcc")
      # 读取的函数修改
      dymdl_rdata = self.dRNC_for_3Dinterp(dypath_info[ifhour][0], ltSPQ_shortname=ltSPQ_shortname) # 上-下=南-北=(481, 561)
      if "10u" in dymdl_rdata and "10v" in dymdl_rdata:
        dymdl_rdata = self.dwind_expand(dymdl_rdata)   #产生地面和高空风速ws
      if "tcc" in self.ltPQSN_Intp:
        dymdl_rdata["tcc"] = np.around(dymdl_rdata["tcc"])  #3km的云0-100之间保存整数就行
    elif sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
      ltSPQ_shortname=[]
      if "2t" in self.ltPQSN_Intp:
        ltSPQ_shortname.append("2t")
      if "2rh" in self.ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["2r"]
      if "10ws" in self.ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["10u","10v"]
      if '10gust' in self.ltPQSN_Intp:
        ltSPQ_shortname.append("gust")
      if 'tcc' in self.ltPQSN_Intp:
        ltSPQ_shortname.append("tcc")

      # 读取NC数据的函数修改
      dymdl_rdata = self.dRNC_for_3Dinterp(dypath_info[ifhour][0], ltSPQ_shortname=ltSPQ_shortname)
      if "10u" in dymdl_rdata and "10v" in dymdl_rdata:
        dymdl_rdata = self.dwind_expand(dymdl_rdata)
      if "tcc" in self.ltPQSN_Intp:
        dymdl_rdata["tcc"] = np.around(dymdl_rdata["tcc"]) #3km的云0-100之间保存整数就行
    #升级模式地理信息
    dymdl_rdata.update(dymdl_Geog["lonlat_SL_IG_mdl"])
    #------------------------------------------------
    dyVR_srf_2d={}
    #2m气温-垂直变化率(C/m)
    if '2t' in self.ltPQSN_Intp: #gfs: 0.0625-60.0625 = 481x561
      dyVR_srf_2d["2t"]  = self.dsurface_scalar_vertical_rate(dymdl_rdata, sPQ="t", mask2d_common_SL_to_ML=dymdl_Geog["mask2d_common_12P5km_to_25km"]) #上-下=南-北数据 (241, 281)
    #2m相对湿度-垂直变化率(%/m)
    if '2rh' in self.ltPQSN_Intp:
      dyVR_srf_2d["2rh"] = self.dsurface_scalar_vertical_rate(dymdl_rdata, sPQ="r", mask2d_common_SL_to_ML=dymdl_Geog["mask2d_common_12P5km_to_25km"]) #上-下=南-北数据 (241, 281)
    #10m风-垂直变化率(m/s/m)
    if '10ws' in self.ltPQSN_Intp:
      dyVR_srf_2d["10u"],dyVR_srf_2d["10v"],dyVR_srf_2d["10ws"] = self.dsurface_vector_vertical_rate(dymdl_rdata, mask2d_common_SL_to_ML=dymdl_Geog["mask2d_common_12P5km_to_25km"]) #上-下=南-北数据 (241, 281)
    #地面气压-垂直变化率(hpa/m)
    if 'sp' in self.ltPQSN_Intp:
      dyVR_srf_2d["sp"]  = self.dsurface_scalar_vertical_rate(dymdl_rdata, sPQ="p", mask2d_common_SL_to_ML=dymdl_Geog["mask2d_common_12P5km_to_25km"])
    #粗网格地面要素垂直变化率插值到细网格
    if sModel_Region_upper in ["EC_12P5KM"]:
      #2m气温-垂直率空间插值
      if '2t' in self.ltPQSN_Intp:
        dyVR_srf_2d["2t"]  = self.dMesh_scalar_interp(dymdl_Geog["lonlat_SL_IG_mdl"], dymdl_Geog["lonlat_ML_IG_mdl"], dyVR_srf_2d["2t"]) #插值到12.5km 输出南-北(上-下)(481, 561)
      #2m湿度-垂直率空间插值
      if '2rh' in self.ltPQSN_Intp:
        dyVR_srf_2d["2rh"] = self.dMesh_scalar_interp(dymdl_Geog["lonlat_SL_IG_mdl"], dymdl_Geog["lonlat_ML_IG_mdl"], dyVR_srf_2d["2rh"])
      #10m风-垂直率空间插值
      if '10ws' in self.ltPQSN_Intp:
        dyVR_srf_2d["10u"],dyVR_srf_2d["10v"],dyVR_srf_2d["10ws"] = \
                          self.dMesh_vector_interp(dymdl_Geog["lonlat_SL_IG_mdl"], dymdl_Geog["lonlat_ML_IG_mdl"], dyVR_srf_2d["10u"],dyVR_srf_2d["10v"],dyVR_srf_2d["10ws"])
      #地面气压-垂直率空间插值
      if 'sp' in self.ltPQSN_Intp:
        dyVR_srf_2d["sp"]  = self.dMesh_scalar_interp(dymdl_Geog["lonlat_SL_IG_mdl"], dymdl_Geog["lonlat_ML_IG_mdl"], dyVR_srf_2d["sp"])
    #10m阵风
    if '10gust' in self.ltPQSN_Intp:
      dyVR_srf_2d["10gust"] = dyVR_srf_2d["10ws"]
    #------------------------------------------------
    ltPQSN_Intp_ready = [sphyq_sn for sphyq_sn in self.ltPQSN_Intp
                         if sphyq_sn not in ["tcc"] and sphyq_sn in dymdl_rdata and sphyq_sn in dyVR_srf_2d]
    if self.iDebug>=1:
      ltmiss = [sphyq_sn for sphyq_sn in self.ltPQSN_Intp
                if sphyq_sn not in ["tcc"] and sphyq_sn not in ltPQSN_Intp_ready]
      if len(ltmiss)>0:
        print("Skip interp missing data:", ltmiss)
    dyattr={}
    #读取eta参数
    dyeta={sphyq_sn:1.0 for sphyq_sn in ltPQSN_Intp_ready}
    for sphyq_sn in ltPQSN_Intp_ready: 
      if sphyq_sn in ["10u","10v","10gust","tcc","sp"]: continue #,
      sIn_eta_abs_path = dypath_info[ifhour][1][1][sphyq_sn]
      if not os.path.exists(sIn_eta_abs_path): 
        print("No:"+sIn_eta_abs_path)
        dyattr[sphyq_sn+"_eta_path"]=None
      else:
        #读取eta参数
        dydata = self.dRS3_Interp(sIn_eta_abs_path)
        #矢量
        if sphyq_sn == "10ws":
          for sPQ in ["10u","10v","10ws"]:
            dyeta[sPQ] = dydata[sPQ]
            dyattr[sPQ+"_eta_path"]=sIn_eta_abs_path
        #标量
        else:
          dyeta[sphyq_sn] = dydata[sphyq_sn]
          dyattr[sphyq_sn+"_eta_path"]=sIn_eta_abs_path
    #地面气压
    if 'sp' in ltPQSN_Intp_ready:
      dyeta["sp"]     = 1.0
    #10m阵风
    if '10gust' in ltPQSN_Intp_ready and '10ws' in dyeta:
      dyeta["10gust"] = dyeta["10ws"]
    #地形插值---------------------------------------------------------------------------------
    dyIntp_rlt = {sphyq_sn:self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, dyVR_srf_2d[sphyq_sn], eta=dyeta[sphyq_sn], skey=sphyq_sn) \
                  for sphyq_sn in ltPQSN_Intp_ready}
    
    if sModel_Region_upper in ["EC_12P5KM"]:
      #最高温度
      if '2t_max' in self.ltPQSN_mxmn:
        dyIntp_rlt['mx2t3'] = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, dyVR_srf_2d["2t"], eta=dyeta["2t"], skey="mx2t3")
      #最低温度
      if '2t_min' in self.ltPQSN_mxmn:
        dyIntp_rlt['mn2t3'] = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, dyVR_srf_2d["2t"], eta=dyeta["2t"], skey="mn2t3")
    if sModel_Region_upper in ["GRAPES_12P5KM"]:
      #最高温度
      if '2t_max' in self.ltPQSN_mxmn:
        dyIntp_rlt['2t_max'] = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, dyVR_srf_2d["2t"], eta=dyeta["2t"], skey="tmax")
      #最低温度
      if '2t_min' in self.ltPQSN_mxmn:
        dyIntp_rlt['2t_min'] = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, dyVR_srf_2d["2t"], eta=dyeta["2t"], skey="tmin")
      #最大相对湿度
      if "2rh_max" in self.ltPQSN_mxmn:
        dyIntp_rlt['2rh_max'] = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, dyVR_srf_2d["2rh"], eta=dyeta["2rh"], skey="2rh_max")
      #最小相对湿度
      if "2rh_min" in self.ltPQSN_mxmn:
        dyIntp_rlt['2rh_min'] = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, dyVR_srf_2d["2rh"], eta=dyeta["2rh"], skey="2rh_min")
    #总云量-双线性插值某要素--------------------------------------------------------------------------
    if "tcc" in self.ltPQSN_Intp:
      ndyInterp_xy =  np.vstack((dyIntp_info['lat'], dyIntp_info['lon'])).T #需要插值的点:数组合并为[[纬度 经度]] [n,2]
      interp_linear = interpolate.RegularGridInterpolator((dymdl_rdata["ndy1d_y_lat"], dymdl_rdata["ndy1d_x_lon"]), 
                                                           dymdl_rdata["tcc"], method='linear')  #输入上-下(南-北)数据
      dyIntp_rlt["tcc"]  = interp_linear(ndyInterp_xy)
    #--------------------------------------------------------------------------------
    #准备写数据
    ltInterp_keys=list(ltPQSN_Intp_ready)
    if sModel_Region_upper in ["EC_12P5KM"]:
      if '2t_max' in self.ltPQSN_mxmn:
        ltInterp_keys = ltInterp_keys + ['mx2t3']
      if '2t_min' in self.ltPQSN_mxmn:
        ltInterp_keys = ltInterp_keys + ['mn2t3']
    if sModel_Region_upper in ["GRAPES_12P5KM"]:
      if '2t_max' in self.ltPQSN_mxmn:
        ltInterp_keys = ltInterp_keys + ['2t_max']
      if '2t_min' in self.ltPQSN_mxmn:
        ltInterp_keys = ltInterp_keys + ['2t_min']
      if '2rh_max' in self.ltPQSN_mxmn:
        ltInterp_keys = ltInterp_keys + ['2rh_max']
      if '2rh_min' in self.ltPQSN_mxmn:
        ltInterp_keys = ltInterp_keys + ['2rh_min']
    #站点
    if dyCommon_Para["sReso"]=="Site":
      dyIntp_rlt["site"] = dyCommon_Para["Site_Code"]
      for sPhyQ in ltInterp_keys:
        #保存插值
        dyIntp_rlt[sPhyQ]  = np.round(dyIntp_rlt[sPhyQ],self.dyPQ_round[sPhyQ])
        #保存gamma
        if sPhyQ not in ['tcc','10gust','mx2t3', 'mn2t3']:
          #gamma插值到站点上
          ndyInterp_xy =  np.vstack((dyIntp_info['lat'], dyIntp_info['lon'])).T #需要插值的点:数组合并为[[纬度 经度]] [n,2]
          interp_linear = interpolate.RegularGridInterpolator((dymdl_rdata["ndy1d_y_lat"], dymdl_rdata["ndy1d_x_lon"]), 
                                                               dyVR_srf_2d[sPhyQ], method='linear')  #输入上-下(南-北)数据
          ndyVR_srf = interp_linear(ndyInterp_xy)
          dyIntp_rlt["gamma_"+sPhyQ] = np.round(ndyVR_srf,5)
      ltout_keys = ltInterp_keys + self.ltgamma_name + ["site"]
    #格点
    else:
      #格点结果截取
      for sPhyQ in ltInterp_keys:
        if sPhyQ in dyIntp_rlt:
          #1d==>2d
          data = np.round(dyIntp_rlt[sPhyQ].reshape(dyIntp_info["2dshape"]),1)
          #中国区域截取
          if dyPara_ini_info["InstantInfo"]["out_China"] and dyCommon_Para["sReso"]=="1km":
            data[~dyIntp_info["mask_area"]]=self.RGrid_Default
            #dyVR_srf_2d[sPhyQ][~dymdl_Geog["lonlat_SL_IG_mdl"]["mask_area"]]=self.RGrid_Default
          #保存插值
          dyIntp_rlt[sPhyQ] = data
          #保存gamma
          if sPhyQ not in ['tcc','10gust','mx2t3', 'mn2t3','2t_max','2t_min','2rh_max','2rh_min']:
            dyIntp_rlt["gamma_"+sPhyQ] = np.round(dyVR_srf_2d[sPhyQ],5)
      #保存网格经纬度信息
      dyIntp_rlt['lon_lat']  = [dyIntp_info['begin_lon'], dyIntp_info['end_lon'],
                                dyIntp_info['begin_lat'], dyIntp_info['end_lat'], 
                                dyIntp_info['lon_res']  , dyIntp_info['lat_res']]
      #保存key值
      ltout_keys = ltInterp_keys + self.ltgamma_name + ['lon_lat']
    #--------------------------------------------------------------------------------
    #写数据
    if self.iDebug>=1:print("out:"+dypath_info[ifhour][1][0])
    tmp_name = self.dWS3_Interp(dypath_info[ifhour][1][0], dyIntp_rlt, ltInterp_keys=ltout_keys, dyattr=dyattr)
    #if tmp_name is None:
    #  print('write error:', dypath_info[ifhour][1][0])
    #elif os.path.exists(tmp_name):
    #  print('rename:%s %s' % (tmp_name, dypath_info[ifhour][1][0]))
    #  os.rename(tmp_name, dypath_info[ifhour][1][0])
    #else:
    #  print('file not exist:', tmp_name)

    #是否进行瞬时检验===================================================================================
    if dyPara_ini_info["InstantInfo"]["validate"]:
      if dyCommon_Para["sReso"]=="Site":
        ltwork = [self.dvalidate_1PQ_site(ifhour, sphyq_sn, dyIntp_rlt, dymdl_rdata) for sphyq_sn in self.ltPQSN_vld]
      else:
        ltwork = [self.dvalidate_1PQ(ifhour, sphyq_sn, dyIntp_rlt, dymdl_rdata) for sphyq_sn in self.ltPQSN_vld]
    return [dyIntp_rlt,dymdl_rdata]

  #检验(1个物理量-1个预报时效)
  def dvalidate_1PQ(self, ifhour, sphyq_sn, dyIntp_rlt, dymdl_rdata):
    sReso = dyCommon_Para["sReso"]
    #逐时预报对应-观测时间
    sYMDH_Obs=self.cls_myfun.dBefAftDate2(dyCommon_Para["sYMDH_mdl_begin_BJ"], "hour", ifhour)
    #====格点实况要素路径====================================================
    sInterp_YMDH_dt = datetime.datetime.strptime(sYMDH_Obs, "%Y%m%d%H")
    sIn_obs_abs_path_dt, lexist = dyCommon_Para["Class"]["Spath"].obs_path(sInterp_YMDH_dt, "Grid"+sReso, sphyq_sn, sTime_range='000')

    if self.iDebug>=1:print("gv:",sYMDH_Obs,sIn_obs_abs_path_dt)
    if not lexist:
      print("No:" , sIn_obs_abs_path_dt)
      return
    #====读取格点实况数据====================================================
    #矢量-读取
    if sphyq_sn=='10ws':
      # 修改读取数据
      ndyu = dyCommon_Para["Class"]["cls_obsdb"].dRObs_Nc(sIn_obs_abs_path_dt['10u'], '10u')
      ndyv = dyCommon_Para["Class"]["cls_obsdb"].dRObs_Nc(sIn_obs_abs_path_dt['10v'], '10v')
      ndyu = np.flipud(ndyu)
      ndyv = np.flipud(ndyv)

      if ndyu.size!=0 and ndyv.size!=0:
        #剪裁插值地形和掩膜数据
        if dyCommon_Para["sModel_Region_upper"] in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
          if dyCommon_Para["Class"]["cls_model"].latlon_info.lat_start==10 and dyCommon_Para["Class"]["cls_model"].latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
            ndyu = ndyu[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
            ndyv = ndyv[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
        elif dyCommon_Para["sModel_Region_upper"] in ["GRAPES_25KM"]:
          if dyCommon_Para["Class"]["cls_model"].latlon_info.lat_start==0.125 and dyCommon_Para["Class"]["cls_model"].latlon_info.lat_end==60.125:
            ndyu = ndyu[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
            ndyv = ndyv[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
        elif dyCommon_Para["sModel_Region_upper"] in ["GRAPES_12P5KM","GRAPES_GFS","CMA_GFS"]:
          if dyCommon_Para["Class"]["cls_model"].latlon_info.lat_start==0.0625 and dyCommon_Para["Class"]["cls_model"].latlon_info.lat_end==60.0625:
            ndyu = ndyu[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
            ndyv = ndyv[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
      dyGObs_PhyQ = {"10u":ndyu,"10v":ndyv,"10ws":np.round(np.sqrt(np.square(ndyu)+np.square(ndyv)),1)}
      ltPhyQ_V=["10u","10v","10ws"]
    #标量-读取
    else:
      ndydata = dyCommon_Para["Class"]["cls_obsdb"].dRObs_Nc(sIn_obs_abs_path_dt[sphyq_sn], sphyq_sn) #上-下 南-北
      ndydata = np.flipud(ndydata) # #上-下 北-南
      # if sphyq_sn=="2t": ndydata=ndydata-self.RCAbsZero # 读取nc后单位为摄氏度
      if ndydata.size!=0:
        #剪裁插值地形和掩膜数据
        if dyCommon_Para["sModel_Region_upper"] in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
          if dyCommon_Para["Class"]["cls_model"].latlon_info.lat_start==10 and dyCommon_Para["Class"]["cls_model"].latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
            ndydata = ndydata[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
        elif dyCommon_Para["sModel_Region_upper"] in ["GRAPES_25KM"]:
          if dyCommon_Para["Class"]["cls_model"].latlon_info.lat_start==0.125 and dyCommon_Para["Class"]["cls_model"].latlon_info.lat_end==60.125:
            ndydata = ndydata[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
        elif dyCommon_Para["sModel_Region_upper"] in ["GRAPES_12P5KM","GRAPES_GFS","CMA_GFS"]:
          if dyCommon_Para["Class"]["cls_model"].latlon_info.lat_start==0.0625 and dyCommon_Para["Class"]["cls_model"].latlon_info.lat_end==60.0625:
            ndydata = ndydata[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
      dyGObs_PhyQ = {sphyq_sn:ndydata}
      ltPhyQ_V=[sphyq_sn]
    #检验===============================================================
    for sPhyQ_sn in ltPhyQ_V:
      if dyGObs_PhyQ[sPhyQ_sn] is None: #说明没有文件
        if self.iDebug>=1:print("gobs:",dyGObs_PhyQ[sPhyQ_sn])
        continue
      if dyGObs_PhyQ[sPhyQ_sn].size!=dyIntp_info['size']: #说明读取到文件,但是数据错误
        if self.iDebug>=1:print("Err:",dyGObs_PhyQ[sPhyQ_sn].size,dyIntp_info['size'])
        continue
      #双线性插值
      interp_linear = interpolate.RegularGridInterpolator((dymdl_rdata["ndy1d_y_lat"], dymdl_rdata["ndy1d_x_lon"]), 
                                                           dymdl_rdata[sPhyQ_sn], method='linear')  #输入上-下(南-北)数据
      ndyInterp_xy  = np.vstack((dyIntp_info['lat'], dyIntp_info['lon'])).T #需要插值的点:数组合并为[[纬度 经度]] [n,2]
      ndyinterp_bi  = interp_linear(ndyInterp_xy)
      #双线性插值结果1d-2d
      ndyinterp_bi  = ndyinterp_bi.reshape(dyIntp_info["2dshape"])
      #双线性误差#上-下(南-北)
      ndydiff_bi     = ndyinterp_bi - dyGObs_PhyQ[sPhyQ_sn]                                   #智网区误差
      ndyAE_bi       = np.abs(ndydiff_bi)                                                     #智网区绝对误差AE
      ndyAE_bi_China = ndyAE_bi[dyIntp_info["mask_area"]]                            #中国区绝对误差AE
      fMAE_bi_China  = np.nanmean(ndyAE_bi_China)                                             #中国区平均绝对误差
      fMAE_bi_China  = np.round(fMAE_bi_China,3)
      fhit_bi_China  = (ndyAE_bi_China<=dyPara_ini_info["threshold"][sPhyQ_sn]).sum()/np.count_nonzero(~np.isnan(ndyAE_bi_China)) #中国区准确率
      fhit_bi_China  = np.round(fhit_bi_China,3)
      #智网误差#上-下(南-北)
      ndydiff_lr     = dyIntp_rlt[sPhyQ_sn]-dyGObs_PhyQ[sPhyQ_sn]                     #智网区
      ndyAE_lr       = np.abs(ndydiff_lr)                                                     #智网区绝对误差AE
      ndyAE_lr_China = ndyAE_lr[dyIntp_info["mask_area"]]                            #中国区绝对误差AE
      fMAE_lr_China  = np.nanmean(ndyAE_lr_China)                                             #中国区平均绝对误差
      fMAE_lr_China  = np.round(fMAE_lr_China,3)
      fhit_lr_China  = (ndyAE_lr_China<=dyPara_ini_info["threshold"][sPhyQ_sn]).sum()/np.count_nonzero(~np.isnan(ndyAE_lr_China)) #中国区准确率
      fhit_lr_China  = np.round(fhit_lr_China,3)
      if self.iDebug>=1:print(f"{sPhyQ_sn}-{ifhour}h-{sReso}-China(lr,bi): {fMAE_lr_China:.3f} {fMAE_bi_China:.3f} | "\
                                                                         f"{fhit_lr_China:.3f} {fhit_bi_China:.3f}")
      if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
        ndyAE_bi_Proce = ndyAE_bi[dyIntp_info["mask_prov"]]
        fMAE_bi_Proce  = np.nanmean(ndyAE_bi_Proce)                                             #选省份平均绝对误差
        fMAE_bi_Proce  = np.round(fMAE_bi_Proce,3)
        fhit_bi_Proce  = (ndyAE_bi_Proce<=dyPara_ini_info["threshold"][sPhyQ_sn]).sum()/np.count_nonzero(~np.isnan(ndyAE_bi_Proce)) #选省准确率
        fhit_bi_Proce  = np.round(fhit_bi_Proce,3)
        ndyAE_lr_Proce = ndyAE_lr[dyIntp_info["mask_prov"]]
        fMAE_lr_Proce  = np.nanmean(ndyAE_lr_Proce)                                             #选省份平均绝对误差
        fMAE_lr_Proce  = np.round(fMAE_lr_Proce,3)
        fhit_lr_Proce  = (ndyAE_lr_Proce<=dyPara_ini_info["threshold"][sPhyQ_sn]).sum()/np.count_nonzero(~np.isnan(ndyAE_lr_Proce)) #选省准确率
        fhit_lr_Proce  = np.round(fhit_lr_Proce,3)
        if self.iDebug>=1:print(f"{sPhyQ_sn}-{ifhour}h-{sReso}-Proce(lr,bi): {fMAE_lr_Proce:.3f} {fMAE_bi_Proce:.3f} | "\
                                                                           f"{fhit_lr_Proce:.3f} {fhit_bi_Proce:.3f}")
      if self.iDebug>=1:print("-"*40)
    return
 

  #检验(1个物理量-1个预报时效-站点)
  def dvalidate_1PQ_site(self, ifhour, sphyq_sn, dyIntp_rlt, dymdl_rdata):
    #逐时预报对应-观测时间
    sYMDH_Obs=self.cls_myfun.dBefAftDate2(dyCommon_Para["sYMDH_mdl_begin_BJ"], "hour", ifhour)
    #====站点实况要素路径====================================================
    sPQ_name=self.dyInstPQSN_to_obsdir[sphyq_sn][0]
    sPQ_type=self.dyInstPQSN_to_obsdir[sphyq_sn][1]
    sIn_sub_path   = os.path.join(dyCommon_Para["Obs_Path"], sYMDH_Obs[0:4], sPQ_name, sPQ_type, sYMDH_Obs[0:8])
    sobs_file_name = sYMDH_Obs+"00"+".h5"
    sIn_obs_abs_path   = os.path.join(sIn_sub_path, sobs_file_name)
    if self.iDebug>=1:print("sv:",sYMDH_Obs,sIn_obs_abs_path)
    if not os.path.exists(sIn_obs_abs_path):
      print("No:"+sIn_obs_abs_path)
      return
    if sphyq_sn in ["2t",'2rh']:
      dfobs_site=dyCommon_Para["Class"]["cls_obsdb"].dRsite_obs(sIn_obs_abs_path, dyCommon_Para["Site_Code"], ltindex=[sphyq_sn])#(1行 多列站点) 缺损-32766.0
      dfobs_site[(dfobs_site[sphyq_sn]<=self.dyPQ_QC[sphyq_sn][0]) | (dfobs_site[sphyq_sn]>=self.dyPQ_QC[sphyq_sn][1])] = np.nan
      dfobs_site = dfobs_site.round(decimals=self.dyPQ_round[sphyq_sn])
      ltPhyQ_V=[sphyq_sn]
    else: #矢量
      dfobs_site=dyCommon_Para["Class"]["cls_obsdb"].dRsite_obs_wind(sIn_obs_abs_path, dyCommon_Para["Site_Code"], ltindex=["WD", sphyq_sn])
      dfobs_site[(dfobs_site[sphyq_sn]<=self.dyPQ_QC[sphyq_sn][0]) | (dfobs_site[sphyq_sn]>=self.dyPQ_QC[sphyq_sn][1])] = np.nan
      dfobs_site.loc[dfobs_site["WD"]==self.fcalm_wd,"WD"] = 0 #静风处理
      ndyU,ndyV = self.cls_myfun.dWind_to_UV(dfobs_site["WD"].values, dfobs_site[sphyq_sn].values) #风向风速转为uv风
      dfobs_site["10u"]  = np.around(ndyU, decimals=self.dyPQ_round["10u"])
      dfobs_site["10v"]  = np.around(ndyV, decimals=self.dyPQ_round["10v"])
      dfobs_site=dfobs_site.round(decimals=self.dyPQ_round[sphyq_sn])
      ltPhyQ_V=["10u","10v","10ws"]
    #检验===============================================================
    if not dfobs_site.isnull().all().all():
      for sPhyQ_sn in ltPhyQ_V:
        #双线性插值
        interp_linear = interpolate.RegularGridInterpolator((dymdl_rdata["ndy1d_y_lat"], dymdl_rdata["ndy1d_x_lon"]), 
                                                             dymdl_rdata[sPhyQ_sn], method='linear')  #输入上-下(南-北)数据
        ndyInterp_xy  = np.vstack((dyIntp_info['lat'], dyIntp_info['lon'])).T #需要插值的点:数组合并为[[纬度 经度]] [n,2]
        ndyinterp_bi  = interp_linear(ndyInterp_xy)
        #智网误差#上-下(南-北)
        ndydiff_bi = ndyinterp_bi - dfobs_site[sPhyQ_sn]                        #智网区误差
        ndyAE_bi   = np.abs(ndydiff_bi)                                         #智网区绝对误差AE
        fMAE_bi    = np.nanmean(ndyAE_bi)                                       #中国区平均绝对误差
        fMAE_bi    = np.round(fMAE_bi,3)
        fhit_bi    = (ndyAE_bi<=dyPara_ini_info["threshold"][sPhyQ_sn]).sum()/np.count_nonzero(~np.isnan(ndyAE_bi)) #中国区准确率
        fhit_bi    = np.round(fhit_bi,3)
        #智网误差#上-下(南-北)
        ndydiff_lr = dyIntp_rlt[sPhyQ_sn]-dfobs_site[sPhyQ_sn]  #智网区
        ndyAE_lr   = np.abs(ndydiff_lr)                                               #智网区绝对误差AE
        fMAE_lr    = np.nanmean(ndyAE_lr)                                             #中国区平均绝对误差
        fMAE_lr    = np.round(fMAE_lr,3)
        fhit_lr    = (ndyAE_lr<=dyPara_ini_info["threshold"][sPhyQ_sn]).sum()/np.count_nonzero(~np.isnan(ndyAE_lr))       #中国区准确率
        fhit_lr    = np.round(fhit_lr,3)
        if self.iDebug>=1:print(f"{sPhyQ_sn}-{ifhour}h-{dyCommon_Para['sReso']}-(lr,bi): {fMAE_lr:.3f} {fMAE_bi:.3f} | "\
                                                                                           f"{fhit_lr:.3f} {fhit_bi:.3f}")
        if self.iDebug>=1:print("-"*40)
    return



  #求最高最低-串行
  def dSerial_Max_Min_nPQ(self, dyInterp_spc_nfh, dyIntp_info, dymdl_rdata_nfh, dymdl_Geog, dypath_mdl, dyPara_ini_info, dyCommon_Para):
    self.init_mxmn_process( dyInterp_spc_nfh, dyIntp_info, dymdl_rdata_nfh, dymdl_Geog, dypath_mdl, dyPara_ini_info, dyCommon_Para)
    for skey_fhours in dyPara_ini_info["MaxMinInfo"]["forecast_time"]: #012_036
      self.dtime_MaxMin(skey_fhours)
  #初始化工作进程
  def init_mxmn_process(self, _dyInterp_spc_nfh, _dyIntp_info, _dymdl_rdata_nfh, _dymdl_Geog, _dypath_mdl, _dyPara_ini_info, _dyCommon_Para):
    # 全局变量
    global dyInterp_spc_nfh
    global dyIntp_info
    global dymdl_rdata_nfh
    global dymdl_Geog
    global dypath_mdl
    global dyPara_ini_info
    global dyCommon_Para
    dyInterp_spc_nfh = _dyInterp_spc_nfh
    dyIntp_info      = _dyIntp_info
    dymdl_rdata_nfh  = _dymdl_rdata_nfh
    dymdl_Geog       = _dymdl_Geog
    dypath_mdl       = _dypath_mdl
    dyPara_ini_info  = _dyPara_ini_info
    dyCommon_Para    = _dyCommon_Para
  #时间最大最小
  def dtime_MaxMin(self, skey_fhours):
    print("MaxMin_t:",skey_fhours)
    sModel_Region_upper = dyCommon_Para["sModel_Region"].upper()
    sReso = dyCommon_Para["sReso"]
    #==从逐3h文件中选取日最大值=========================================
    sIn_sub_path  = os.path.join(dyCommon_Para["rlt_Path"],dyCommon_Para["S3_dir"],dyCommon_Para["sS3_method"],
                                 dyCommon_Para["sModel_Region"], dyCommon_Para["sReso_dir"], \
                                 dyCommon_Para["sYMDH_mdl_begin_BJ"][0:4],dyCommon_Para["sYMDH_mdl_begin_BJ"][0:8], dyCommon_Para["sYMDH_mdl_begin_BJ"][8:10])
    #输出最高最低文件名
    sOut_file_name = skey_fhours + ".h5"
    sOut_abs_path   = os.path.join(sIn_sub_path, sOut_file_name)
    lexist = os.path.exists(sOut_abs_path)
    dyMaxMin_Intp={}
    #最高最低单独更新
    if lexist and dyPara_ini_info["MaxMinInfo"]["update"]==True:
      if self.iDebug>=1:print("remove:"+sOut_abs_path)
      os.remove(sOut_abs_path)
      lexist=False
    #输出插值文件=h5不存在 or h5存在&必须更新>1
    lalive = (not lexist) or (lexist and dyCommon_Para["update"]!=0 and dyInterp_spc_nfh!={})
    if not lalive: 
      print("No_update:"+sOut_abs_path)
      return
    else:
      ltSPQ_shortname = []
      if sModel_Region_upper in ["EC_12P5KM"]:
        #最高温度
        if '2t_max' in self.ltPQSN_mxmn:
          ltSPQ_shortname = ltSPQ_shortname + ['mx2t3']
        #最低温度
        if '2t_min' in self.ltPQSN_mxmn:
          ltSPQ_shortname = ltSPQ_shortname + ['mn2t3']
        #相对湿度
        if '2rh_min' in self.ltPQSN_mxmn or '2rh_max' in self.ltPQSN_mxmn:
          ltSPQ_shortname = ltSPQ_shortname + ['2t','2d']
        #最大风速
        if '10ws_max' in self.ltPQSN_mxmn:
          ltSPQ_shortname = ltSPQ_shortname + ["10gust"]
      elif sModel_Region_upper in ["GRAPES_12P5KM"]:
        #最高温度
        if '2t_max' in self.ltPQSN_mxmn:
          ltSPQ_shortname= ltSPQ_shortname +['tmax']
        #最低温度
        if '2t_min' in self.ltPQSN_mxmn:
          ltSPQ_shortname= ltSPQ_shortname +['tmin']
        #相对湿度
        if '2rh_max' in self.ltPQSN_mxmn:
          ltSPQ_shortname= ltSPQ_shortname +['2rh_max']
        if '2rh_min' in self.ltPQSN_mxmn:
          ltSPQ_shortname= ltSPQ_shortname +['2rh_min']
        #最大风速
        if '10ws_max' in self.ltPQSN_mxmn:
          ltSPQ_shortname= ltSPQ_shortname +['gust']
      #获取每个时效数据
      ndymax2t = np.zeros((len(dyCommon_Para["dyMaxMin_fhours"][skey_fhours]), dyIntp_info['size']),dtype="float32")+np.nan #最高温度
      ndymin2t = ndymax2t.copy() #最低温度
      if sModel_Region_upper in ["EC_12P5KM"]:  
        ndyIstrh = ndymax2t.copy() #瞬时相对湿度
      elif sModel_Region_upper in ["GRAPES_12P5KM"]:
        ndymax2rh = ndymax2t.copy()
        ndymin2rh = ndymax2t.copy()
      ndymaxfg = ndymax2t.copy() #最大风速
      #由于地形插值数据没有计算,需要从文件读取
      iexist_data = 0
      for idx, ifhour in enumerate(dyCommon_Para["dyMaxMin_fhours"][skey_fhours]):
        #从文件读取
        if ifhour not in dyInterp_spc_nfh:
          sfhour = "%03d"%ifhour
          sIn_file_name = sfhour+"_"+sfhour+".h5"
          sIn_abs_path  = os.path.join(sIn_sub_path, sIn_file_name)
          if os.path.exists(sIn_abs_path):
            iexist_data = iexist_data + 1
            #读取地形插值文件
            dydata = self.dRS3_Interp(sIn_abs_path, self.dyPQ_round)
            if sModel_Region_upper in ["EC_12P5KM"]:
              #最高温度
              if '2t_max' in self.ltPQSN_mxmn and 'mx2t3' in dydata:
                ndymax2t[idx,:] = dydata['mx2t3'].flatten()
              #最低温度
              if '2t_min' in self.ltPQSN_mxmn and 'mn2t3' in dydata:
                ndymin2t[idx,:] = dydata['mn2t3'].flatten()
              #相对湿度
              if ('2rh_min' in self.ltPQSN_mxmn or '2rh_max' in self.ltPQSN_mxmn) and ('2rh' in dydata):
                ndyIstrh[idx,:] = dydata['2rh'].flatten()
              #最大风速
              if '10ws_max' in self.ltPQSN_mxmn and "10gust" in dydata:
                ndymaxfg[idx,:] = dydata["10gust"].flatten()
            elif sModel_Region_upper in ["GRAPES_12P5KM"]:
              #最高温度
              if '2t_max' in self.ltPQSN_mxmn and '2t_max' in dydata:
                ndymax2t[idx,:] = dydata['2t_max'].flatten()
              #最低温度
              if '2t_min' in self.ltPQSN_mxmn and '2t_min' in dydata:
                ndymin2t[idx,:] = dydata['2t_min'].flatten()
              #相对湿度
              if '2rh_max' in self.ltPQSN_mxmn and '2rh_max' in dydata:
                ndymax2rh[idx,:] = dydata['2rh_max'].flatten()
              if '2rh_min' in self.ltPQSN_mxmn and '2rh_min' in dydata:
                ndymin2rh[idx,:] = dydata['2rh_min'].flatten()
              #最大风速
              if '10ws_max' in self.ltPQSN_mxmn:
                ndymaxfg[idx,:] = dydata["10gust"].flatten()
        #前面插值结果
        else:
          iexist_data = iexist_data + 1
          dydata = dyInterp_spc_nfh[ifhour] #地形插值后的计算数据
          if sModel_Region_upper in ["EC_12P5KM"]:
            #最高温度
            if '2t_max' in self.ltPQSN_mxmn:
              ndymax2t[idx,:] = dydata['mx2t3'].flatten()
            #最低温度
            if '2t_min' in self.ltPQSN_mxmn:
              ndymin2t[idx,:] = dydata['mn2t3'].flatten()
            #相对湿度
            if '2rh_min' in self.ltPQSN_mxmn or '2rh_max' in self.ltPQSN_mxmn:
              ndyIstrh[idx,:] = dydata['2rh'].flatten()
            #最大风速
            if '10ws_max' in self.ltPQSN_mxmn:
              ndymaxfg[idx,:] = dydata["10gust"].flatten()
          elif sModel_Region_upper in ["GRAPES_12P5KM"]:
            #最高温度
            if '2t_max' in self.ltPQSN_mxmn:
              ndymax2t[idx,:] = dydata['2t_max'].flatten()
            #最低温度
            if '2t_min' in self.ltPQSN_mxmn:
              ndymin2t[idx,:] = dydata['2t_min'].flatten()
            #相对湿度
            if '2rh_max' in self.ltPQSN_mxmn:
              ndymax2rh[idx,:] = dydata['2rh_max'].flatten()
            if '2rh_min' in self.ltPQSN_mxmn:
              ndymin2rh[idx,:] = dydata['2rh_min'].flatten()
            #最大风速
            if '10ws_max' in self.ltPQSN_mxmn:
              ndymaxfg[idx,:] = dydata["10gust"].flatten()
      #说明有缺损值,无法求日最高最低
      if iexist_data!=8:
        if dyCommon_Para["update"]>=1:print("Missing Interp_space:",iexist_data)
      else:
        #站点
        if sReso.lower()=="site":
          #最高温度
          if '2t_max' in self.ltPQSN_mxmn:
            dyMaxMin_Intp["2t_max"]   = np.nanmax(ndymax2t, axis=0) #每列最大值
          #最低温度
          if '2t_min' in self.ltPQSN_mxmn:
            dyMaxMin_Intp["2t_min"]   = np.nanmin(ndymin2t, axis=0)
          if sModel_Region_upper in ["EC_12P5KM"]:
            #最大相对湿度
            if '2rh_max' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_max"]  = np.nanmax(ndyIstrh, axis=0)
            #最小相对湿度
            if '2rh_min' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_min"]  = np.nanmin(ndyIstrh, axis=0)
          elif sModel_Region_upper in ["GRAPES_12P5KM"]:
            #最大相对湿度
            if '2rh_max' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_max"]  = np.nanmax(ndymax2rh, axis=0)
            #最小相对湿度
            if '2rh_min' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_min"]  = np.nanmin(ndymin2rh, axis=0)
          #最大风速
          if '10ws_max' in self.ltPQSN_mxmn:
            dyMaxMin_Intp["10ws_max"] = np.nanmax(ndymaxfg, axis=0)
          #站点信息
          dyMaxMin_Intp["site"]     = dyCommon_Para["Site_Code"]
        #格点
        else:
          #----------------------------------------------------------------
          #最高气温
          if '2t_max' in self.ltPQSN_mxmn:
            dyMaxMin_Intp["2t_max"]   = np.nanmax(ndymax2t, axis=0).reshape(dyIntp_info['2dshape']) #每列最大值=(8, 1682601)
          #最低温度
          if '2t_min' in self.ltPQSN_mxmn:
            dyMaxMin_Intp["2t_min"]   = np.nanmin(ndymin2t, axis=0).reshape(dyIntp_info['2dshape'])
          if sModel_Region_upper in ["EC_12P5KM"]:
            #最大相对湿度
            if '2rh_max' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_max"]  = np.nanmax(ndyIstrh, axis=0).reshape(dyIntp_info['2dshape'])
            #最小相对湿度
            if '2rh_min' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_min"]  = np.nanmin(ndyIstrh, axis=0).reshape(dyIntp_info['2dshape'])
          elif sModel_Region_upper in ["GRAPES_12P5KM"]:
            #最大相对湿度
            if '2rh_max' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_max"]  = np.nanmax(ndymax2rh, axis=0).reshape(dyIntp_info['2dshape'])
            #最小相对湿度
            if '2rh_min' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_min"]  = np.nanmin(ndymin2rh, axis=0).reshape(dyIntp_info['2dshape'])
          #最大风速
          if '10ws_max' in self.ltPQSN_mxmn:
            dyMaxMin_Intp["10ws_max"] = np.nanmax(ndymaxfg, axis=0).reshape(dyIntp_info['2dshape'])
          #----------------------------------------------------------------
          #极值对应的预报时效, EC是3h内的极值对应的结束预报时效
          if '2t_max' in self.ltPQSN_mxmn:
            dyMaxMin_Intp["2t_max_fh"]   = (dyCommon_Para["dyMaxMin_fhours"][skey_fhours][0]+np.argmax(ndymax2t, axis=0)*3).reshape(dyIntp_info['2dshape'])
          if '2t_min' in self.ltPQSN_mxmn:
            dyMaxMin_Intp["2t_min_fh"]   = (dyCommon_Para["dyMaxMin_fhours"][skey_fhours][0]+np.argmin(ndymin2t, axis=0)*3).reshape(dyIntp_info['2dshape'])
          if sModel_Region_upper in ["EC_12P5KM"]:
            if '2rh_max' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_max_fh"]  = (dyCommon_Para["dyMaxMin_fhours"][skey_fhours][0]+np.argmax(ndyIstrh, axis=0)*3).reshape(dyIntp_info['2dshape'])
            if '2rh_min' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_min_fh"]  = (dyCommon_Para["dyMaxMin_fhours"][skey_fhours][0]+np.argmin(ndyIstrh, axis=0)*3).reshape(dyIntp_info['2dshape'])
          elif sModel_Region_upper in ["GRAPES_12P5KM"]:
            if '2rh_max' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_max_fh"]  = (dyCommon_Para["dyMaxMin_fhours"][skey_fhours][0]+np.argmax(ndymax2rh, axis=0)*3).reshape(dyIntp_info['2dshape'])
            if '2rh_min' in self.ltPQSN_mxmn:
              dyMaxMin_Intp["2rh_min_fh"]  = (dyCommon_Para["dyMaxMin_fhours"][skey_fhours][0]+np.argmin(ndymin2rh, axis=0)*3).reshape(dyIntp_info['2dshape'])
          if '10ws_max' in self.ltPQSN_mxmn:
            dyMaxMin_Intp["10ws_max_fh"] = (dyCommon_Para["dyMaxMin_fhours"][skey_fhours][0]+np.argmax(ndymaxfg, axis=0)*3).reshape(dyIntp_info['2dshape'])
        #输出数据
        if self.iDebug>=1:print("out:"+sOut_abs_path)
        tmp_name = self.dWS3_Interp(sOut_abs_path, dyMaxMin_Intp)
        #if tmp_name is None:
        #  print('write error:', sOut_abs_path)
        #elif os.path.exists(tmp_name):
        #  print('rename:%s %s' % (tmp_name, sOut_abs_path))
        #  os.rename(tmp_name, sOut_abs_path)
        #else:
        #  print('file not exist:', tmp_name)

        ############################################################################################################
        #检验
        if dyPara_ini_info["MaxMinInfo"]["validate"]:
          #===================================================================================================================
          #模式原始产品的网格最高最低值(用于双线性插值)
          dyMaxMin_mdl={}
          ndymax2t = np.zeros((len(dyCommon_Para["dyMaxMin_fhours"][skey_fhours]), dymdl_Geog["lonlat_SL_IG_mdl"]["size"]),dtype="float32")+np.nan
          if '2t_min' in self.ltPQSN_mxmn:
            ndymin2t = ndymax2t.copy()
          if '2rh_min' in self.ltPQSN_mxmn:
            ndymin2rh = ndymax2t.copy()
          if '2rh_max' in self.ltPQSN_mxmn:
            ndymax2rh = ndymax2t.copy()
          if '10ws_max' in self.ltPQSN_mxmn:
            ndymaxfg = ndymax2t.copy()
          #从文件获取
          if dymdl_rdata_nfh=={}:
            for idx, ifhour in enumerate(dyCommon_Para["dyMaxMin_fhours"][skey_fhours]):
              sfhour = "%03d"%ifhour
              # 更换grib读取NC的地面和3D数据文件
              dymdl_rdata = self.dRNC_for_3Dinterp(dypath_mdl[ifhour], ltSPQ_shortname=ltSPQ_shortname)
              if sModel_Region_upper in ["EC_12P5KM"]:
                if "2t" in dymdl_rdata and "2d" in dymdl_rdata:
                  dymdl_rdata = self.drh_expand(dymdl_rdata)
                #最高温度
                if '2t_max' in self.ltPQSN_mxmn:
                  ndymax2t[idx,:] = dymdl_rdata['mx2t3'].flatten()
                #最低温度
                if '2t_min' in self.ltPQSN_mxmn:
                  ndymin2t[idx,:] = dymdl_rdata['mn2t3'].flatten()
                #最小相对湿度
                if '2rh_min' in self.ltPQSN_mxmn or '2rh_max' in self.ltPQSN_mxmn:
                  ndymin2rh[idx,:] = dymdl_rdata['2rh'].flatten()
              elif sModel_Region_upper in ["GRAPES_12P5KM"]:
                #最高温度
                if '2t_max' in self.ltPQSN_mxmn:
                  ndymax2t[idx,:] = dymdl_rdata['tmax'].flatten()
                #最低温度
                if '2t_min' in self.ltPQSN_mxmn:
                  ndymin2t[idx,:] = dymdl_rdata['tmin'].flatten()
                #最大相对湿度
                if '2rh_max' in self.ltPQSN_mxmn:
                  ndymax2rh[idx,:] = dymdl_rdata['2rh_max'].flatten()
                #最小相对湿度
                if '2rh_min' in self.ltPQSN_mxmn:
                  ndymin2rh[idx,:] = dymdl_rdata['2rh_min'].flatten()
              #最大风速
              if '10ws_max' in self.ltPQSN_mxmn:
                ndymaxfg[idx,:] = dymdl_rdata["10gust"].flatten()
          #从变量获取
          else:
            for idx, ifhour in enumerate(dyCommon_Para["dyMaxMin_fhours"][skey_fhours]):
              if sModel_Region_upper in ["EC_12P5KM"]:
                #最高温度
                if '2t_max' in self.ltPQSN_mxmn:
                  ndymax2t[idx,:] = dymdl_rdata_nfh[ifhour]['mx2t3'].flatten()
                #最低温度
                if '2t_min' in self.ltPQSN_mxmn:
                  ndymin2t[idx,:] = dymdl_rdata_nfh[ifhour]['mn2t3'].flatten()
                #相对湿度
                if '2rh_min' in self.ltPQSN_mxmn or '2rh_max' in self.ltPQSN_mxmn:
                  ndymin2rh[idx,:] = dymdl_rdata_nfh[ifhour]['2rh'].flatten()
              elif sModel_Region_upper in ["GRAPES_12P5KM"]:
                #最高温度
                if '2t_max' in self.ltPQSN_mxmn:
                  ndymax2t[idx,:] = dymdl_rdata_nfh[ifhour]['tmax'].flatten()
                #最低温度
                if '2t_min' in self.ltPQSN_mxmn:
                  ndymin2t[idx,:] = dymdl_rdata_nfh[ifhour]['tmin'].flatten()
                #最大相对湿度
                if '2rh_max' in self.ltPQSN_mxmn:
                  ndymax2rh[idx,:] = dymdl_rdata_nfh[ifhour]['2rh_max'].flatten()
                #最小相对湿度
                if '2rh_min' in self.ltPQSN_mxmn:
                  ndymin2rh[idx,:] = dymdl_rdata_nfh[ifhour]['2rh_min'].flatten() 
              #最大风速
              if '10ws_max' in self.ltPQSN_mxmn:
                ndymaxfg[idx,:] = dymdl_rdata_nfh[ifhour]["10gust"].flatten()
          #最高温度
          if '2t_max' in self.ltPQSN_mxmn:
            dyMaxMin_mdl["2t_max"]   = np.nanmax(ndymax2t, axis=0).reshape(dymdl_Geog["lonlat_SL_IG_mdl"]['tpshape_lonlat']) #每列最大值
          #最低温度
          if '2t_min' in self.ltPQSN_mxmn:
            dyMaxMin_mdl["2t_min"]   = np.nanmin(ndymin2t, axis=0).reshape(dymdl_Geog["lonlat_SL_IG_mdl"]['tpshape_lonlat'])
          if sModel_Region_upper in ["EC_12P5KM"]:
            #最大相对湿度
            if '2rh_max' in self.ltPQSN_mxmn:
              dyMaxMin_mdl["2rh_max"]  = np.nanmax(ndymin2rh, axis=0).reshape(dymdl_Geog["lonlat_SL_IG_mdl"]['tpshape_lonlat'])
            #最小相对湿度
            if '2rh_min' in self.ltPQSN_mxmn:
              dyMaxMin_mdl["2rh_min"]  = np.nanmin(ndymin2rh, axis=0).reshape(dymdl_Geog["lonlat_SL_IG_mdl"]['tpshape_lonlat'])
          elif sModel_Region_upper in ["GRAPES_12P5KM"]:
            #最大相对湿度
            if '2rh_max' in self.ltPQSN_mxmn:
              dyMaxMin_mdl["2rh_max"]  = np.nanmax(ndymax2rh, axis=0).reshape(dymdl_Geog["lonlat_SL_IG_mdl"]['tpshape_lonlat'])
              dyMaxMin_mdl["2rh_max"][dyMaxMin_mdl["2rh_max"]>100] = 100
            #最小相对湿度
            if '2rh_min' in self.ltPQSN_mxmn:
              dyMaxMin_mdl["2rh_min"]  = np.nanmin(ndymin2rh, axis=0).reshape(dymdl_Geog["lonlat_SL_IG_mdl"]['tpshape_lonlat'])
              dyMaxMin_mdl["2rh_min"][dyMaxMin_mdl["2rh_min"]<0] = 0
          #最大风速
          if '10ws_max' in self.ltPQSN_mxmn:
            dyMaxMin_mdl["10ws_max"] = np.nanmax(ndymaxfg, axis=0).reshape(dymdl_Geog["lonlat_SL_IG_mdl"]['tpshape_lonlat'])
          #===================================================================================================================
          #预报对应的日序-读实况
          sYMDH_day_Obs=self.cls_myfun.dBefAftDate2(dyCommon_Para["sYMDH_mdl_begin_BJ"], "hour", int(skey_fhours[-3:]))
          #格点-检验
          if sReso!="site":
            if self.iDebug>=1:print("Max-Min grid validate:")
            #格点实况路径
            if self.iDebug>=1:print("RGO:",sYMDH_day_Obs,dyCommon_Para["Obs_Path"])
            #=实况物理量循环==============================================
            for sPhyQ_shortname in self.ltPQSN_mxmn:
              #要素路径
              sInterp_YMDH_dt = datetime.datetime.strptime(sYMDH_day_Obs, "%Y%m%d%H")
              sIn_obs_abs_path_dt, lexist = dyCommon_Para["Class"]["Spath"].obs_path(sInterp_YMDH_dt, dyCommon_Para["sReso_dir"],
                                                                             sPhyQ_shortname, sTime_range='000')

              if not lexist:
                if self.iDebug>=1:print("No exist GObs:"+sIn_obs_abs_path_dt)
                continue
              else:
                #=读取格点实况数据===================================================
                #标量
                if sPhyQ_shortname in ["2t_max","2t_min","2rh_max","2rh_min"]:
                  # 修改读取
                  ndydata = dyCommon_Para["Class"]["cls_obsdb"].dRObs_Nc(sIn_obs_abs_path_dt[sPhyQ_shortname], sPhyQ_shortname)  # 上-下 南-北
                  ndydata = np.flipud(ndydata)  #上-下 北-南
                  if ndydata.size!=0:
                    #剪裁插值地形和掩膜数据
                    if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
                      if dyCommon_Para["Class"]["cls_model"].latlon_info.lat_start==10 and dyCommon_Para["Class"]["cls_model"].latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
                        ndydata = ndydata[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
                    elif sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_GFS","CMA_GFS"]:
                      if dyCommon_Para["Class"]["cls_model"].latlon_info.lat_start==0.0625 and dyCommon_Para["Class"]["cls_model"].latlon_info.lat_end==60.0625:
                        ndydata = ndydata[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
                  # if sPhyQ_shortname in ["2t_max","2t_min"]: ndydata=ndydata-self.RCAbsZero # 读取nc后单位为摄氏度
                  dyGObs_PhyQ={sPhyQ_shortname:ndydata}
                #矢量
                else:
                  # 修改读取
                  ndyu = dyCommon_Para["Class"]["cls_obsdb"].dRObs_Nc(sIn_obs_abs_path_dt['10u'], '10u')
                  ndyv = dyCommon_Para["Class"]["cls_obsdb"].dRObs_Nc(sIn_obs_abs_path_dt['10v'], '10v')
                  ndyu = np.flipud(ndyu)
                  ndyv = np.flipud(ndyv)
                  if ndyu.size!=0:
                    #剪裁插值地形和掩膜数据
                    if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
                      if dyCommon_Para["Class"]["cls_model"].latlon_info.lat_start==10 and dyCommon_Para["Class"]["cls_model"].latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
                        ndyu = ndyu[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
                        ndyv = ndyv[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
                    elif sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_GFS","CMA_GFS"]:
                      if dyCommon_Para["Class"]["cls_model"].latlon_info.lat_start==0.0625 and dyCommon_Para["Class"]["cls_model"].latlon_info.lat_end==60.0625:
                        ndyu = ndyu[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
                        ndyv = ndyv[dyIntp_info["cut_obs"][sReso][0]:dyIntp_info["cut_obs"][sReso][1]:dyIntp_info["cut_obs"][sReso][2],:]
                  ndyu[(ndyu<=self.dyPQ_QC[sPhyQ_shortname][0]) | (ndyu>=self.dyPQ_QC[sPhyQ_shortname][1])] = np.nan
                  ndyv[(ndyv<=self.dyPQ_QC[sPhyQ_shortname][0]) | (ndyv>=self.dyPQ_QC[sPhyQ_shortname][1])] = np.nan
                  dyGObs_PhyQ = {sPhyQ_shortname:np.round(np.sqrt(np.square(ndyu)+np.square(ndyv)),1)} #"10u":ndyu,"10v":ndyv,
                for sPhyQ_sn in dyGObs_PhyQ:
                  if dyGObs_PhyQ[sPhyQ_sn].size!=dyIntp_info['size']: #说明读取到文件,但是数据错误
                    if self.iDebug>=1:print("Err:",dyGObs_PhyQ[sPhyQ_sn].size,dyIntp_info['size'])
                    continue
                  #智网误差#上-下(南-北)
                  ndydiff_lr     = dyMaxMin_Intp[sPhyQ_sn]-dyGObs_PhyQ[sPhyQ_sn]       #智网区
                  ndyAE_lr       = np.abs(ndydiff_lr)                                              #智网区绝对误差AE
                  ndyAE_lr_China = ndyAE_lr[dyIntp_info["mask_area"]]                              #中国区绝对误差AE
                  fMAE_lr_China  = np.nanmean(ndyAE_lr_China)                                      #中国区平均绝对误差
                  fMAE_lr_China  = np.round(fMAE_lr_China,3)
                  fhit_lr_China  = (ndyAE_lr_China<=dyPara_ini_info["threshold"][sPhyQ_sn]).sum()/np.count_nonzero(~np.isnan(ndyAE_lr_China)) #中国区准确率
                  fhit_lr_China  = np.round(fhit_lr_China,3)
                  #原始文件双线性插值
                  if dyMaxMin_mdl!={}:
                    interp_linear = interpolate.RegularGridInterpolator((dymdl_Geog["lonlat_SL_IG_mdl"]["ndy1d_y_lat"], dymdl_Geog["lonlat_SL_IG_mdl"]["ndy1d_x_lon"]), 
                                                                         dyMaxMin_mdl[sPhyQ_sn], method='linear')  #输入上-下(南-北)数据
                    ndyInterp_xy  = np.vstack((dyIntp_info['lat'], dyIntp_info['lon'])).T #需要插值的点:数组合并为[[纬度 经度]] [n,2]
                    ndyinterp_bi  = interp_linear(ndyInterp_xy)
                    #双线性插值结果1d-2d
                    ndyinterp_bi  = ndyinterp_bi.reshape(dyIntp_info["2dshape"])
                    #智网误差#上-下(南-北)
                    ndydiff_bi     = ndyinterp_bi - dyGObs_PhyQ[sPhyQ_sn]                           #智网区误差
                    ndyAE_bi       = np.abs(ndydiff_bi)                                             #智网区绝对误差AE
                    ndyAE_bi_China = ndyAE_bi[dyIntp_info["mask_area"]]                             #中国区绝对误差AE
                    fMAE_bi_China  = np.nanmean(ndyAE_bi_China)                                     #中国区平均绝对误差
                    fMAE_bi_China  = np.round(fMAE_bi_China,3)
                    fhit_bi_China  = (ndyAE_bi_China<=dyPara_ini_info["threshold"][sPhyQ_sn]).sum()/np.count_nonzero(~np.isnan(ndyAE_bi_China)) #中国区准确率
                    fhit_bi_China  = np.round(fhit_bi_China,3)
                    if self.iDebug>=1:print(f"{sPhyQ_sn.ljust(5)}-{sReso}-best(lr,bi): {fMAE_lr_China:.3f} {fMAE_bi_China:.3f} | "\
                                                                                     f"{fhit_lr_China:.3f} {fhit_bi_China:.3f}")
                  else: 
                    if self.iDebug>=1:print(f"{sPhyQ_sn.ljust(5)}-{sReso}-best(lr): {fMAE_lr_China:.3f} {fhit_lr_China:.3f}")
          #站点-检验
          else:
            if self.iDebug>=1:print("Max-Min site validate:")
            #读站点实况主路径
            if self.iDebug>=1:print("RSO:",sYMDH_day_Obs)
            #物理量循环
            for sPhyQ_shortname in self.ltPQSN_mxmn:
              ltPhyQ_shortname =  sPhyQ_shortname.split("_")
              sPQ_name=self.dyPhyQ_24h[sPhyQ_shortname][0];sPQ_type=self.dyPhyQ_24h[sPhyQ_shortname][1]
              #站点实况文件名
              sIn_sub_path   = os.path.join(dyCommon_Para["Obs_Path"], sYMDH_day_Obs[0:4], sPQ_name, sPQ_type, sYMDH_day_Obs[0:8])
              sobs_site_name = sYMDH_day_Obs+"00"+".h5"
              sIn_abs_path  = os.path.join(sIn_sub_path, sobs_site_name)
              lexist = os.path.exists(sIn_abs_path)
              if not lexist:
                if self.iDebug>=1:print("No exist SObs:"+sIn_abs_path)
              else:
                #读取站点数据文件(标量)
                if sPhyQ_shortname in ["2t_max","2t_min","2rh_max","2rh_min"]:
                  dfobs_site=dyCommon_Para["Class"]["cls_obsdb"].dRsite_obs(sIn_abs_path, dyCommon_Para['ltSlt_Site_Code'], ltindex=[sPhyQ_shortname])#(1行 多列站点) 缺损-32766.0
                  dfobs_site[(dfobs_site[sPhyQ_shortname]<=self.dyPQ_QC[sPhyQ_shortname][0]) | (dfobs_site[sPhyQ_shortname]>=self.dyPQ_QC[sPhyQ_shortname][1])] = np.nan
                  dfobs_site = dfobs_site.round(decimals=self.dyPQ_round[sPhyQ_shortname])
                  ltPhyQ_V=[sPhyQ_shortname]
                else: #矢量
                  dfobs_site=dyCommon_Para["Class"]["cls_obsdb"].dRsite_obs_wind(sIn_abs_path, dyCommon_Para['ltSlt_Site_Code'], ltindex=["WD", sPhyQ_shortname])
                  dfobs_site[(dfobs_site[sPhyQ_shortname]<=self.dyPQ_QC[sPhyQ_shortname][0]) | (dfobs_site[sPhyQ_shortname]>=self.dyPQ_QC[sPhyQ_shortname][1])] = np.nan
                  dfobs_site.loc[dfobs_site["WD"]==fcalm_wd,"WD"] = 0 #静风处理
                  #ndyU,ndyV = cls_myfun.dWind_to_UV(dfobs_site["WD"].values, dfobs_site[sPhyQ_shortname].values) #风向风速转为uv风
                  #dfobs_site["10u"]  = np.around(ndyU, decimals=dyPQ_round["10u"])
                  #dfobs_site["10v"]  = np.around(ndyV, decimals=dyPQ_round["10v"])
                  dfobs_site=dfobs_site.round(decimals=self.dyPQ_round[sPhyQ_shortname])
                  ltPhyQ_V=[sPhyQ_shortname] #"10u","10v",
                #实况数据存在
                if not dfobs_site.isnull().all().all():
                  for sPhyQ_sn in ltPhyQ_V:
                    #智网误差#上-下(南-北)
                    ndydiff_lr = dyMaxMin_Intp[sPhyQ_sn]-dfobs_site[sPhyQ_sn]  #智网区
                    ndyAE_lr   = np.abs(ndydiff_lr)                                               #智网区绝对误差AE
                    fMAE_lr    = np.nanmean(ndyAE_lr)                                             #中国区平均绝对误差
                    fMAE_lr    = np.round(fMAE_lr,3)
                    fhit_lr    = (ndyAE_lr<=dyPara_ini_info["threshold"][sPhyQ_sn]).sum()/np.count_nonzero(~np.isnan(ndyAE_lr))       #中国区准确率
                    fhit_lr    = np.round(fhit_lr,3)
                    #原始文件双线性插值
                    if dyMaxMin_mdl!={}:
                      interp_linear = interpolate.RegularGridInterpolator((dyMaxMin_mdl["ndy1d_y_lat"], dyMaxMin_mdl["ndy1d_x_lon"]), 
                                                                           dyMaxMin_mdl[sPhyQ_sn], method='linear')  #输入上-下(南-北)数据
                      ndyInterp_xy  = np.vstack((dyIntp_info['lat'], dyIntp_info['lon'])).T #需要插值的点:数组合并为[[纬度 经度]] [n,2]
                      ndyinterp_bi  = interp_linear(ndyInterp_xy)
                      #智网误差#上-下(南-北)
                      ndydiff_bi = ndyinterp_bi - dfobs_site[sPhyQ_sn]                 #智网区误差
                      ndyAE_bi   = np.abs(ndydiff_bi)                                         #智网区绝对误差AE
                      fMAE_bi    = np.nanmean(ndyAE_bi)                                       #中国区平均绝对误差
                      fMAE_bi    = np.round(fMAE_bi,3)
                      fhit_bi    = (ndyAE_bi<=dyPara_ini_info["threshold"][sPhyQ_sn]).sum()/np.count_nonzero(~np.isnan(ndyAE_bi)) #中国区准确率
                      fhit_bi    = np.round(fhit_bi,3)
                      if self.iDebug>=1:print(f"{sPhyQ_sn.ljust(5)}-{sReso}-best(lr,bi): {fMAE_lr:.3f} {fMAE_bi:.3f} | "\
                                                                                       f"{fhit_lr:.3f} {fhit_bi:.3f}")
                    else: 
                      if self.iDebug>=1:print(f"{sPhyQ_sn.ljust(5)}-{sReso}-best(lr): {fMAE_lr:.3f} {fhit_lr:.3f}")
        print("-"*40)
      return


  #串行调用(n个物理量-n个预报时效)
  def dSerial_time_Interp_nPQ(self, ltInterp_fh_be, dyInterp_rlt_nfh, dyCommon_Para): #dyIntp_info, dymdl_Geog, dypath_info, dyPara_ini_info,
    self.init_ti_process(dyInterp_rlt_nfh, dyCommon_Para)
    for ltIfh_be in ltInterp_fh_be:
      self.dtime_Interp(ltIfh_be)
    return
  #并行调用(1个物理量-多个预报时效)
  def dPool_time_Interp_nPQ(self, ltInterp_fh_be, dyInterp_rlt_nfh, dyPara_ini_info, dyCommon_Para):
    in_cpu_core = mp.cpu_count()
    iN_file_proces=np.min([len(ltInterp_fh_be),in_cpu_core,dyPara_ini_info["Pool"]["FH_max_pcount"]])
    if self.iDebug>=1:print("FH_parallel:",iN_file_proces)
    pool = mp.Pool(processes = iN_file_proces, initializer=self.init_ti_process, initargs=(dyInterp_rlt_nfh, dyCommon_Para))
    pool_result = pool.map_async(self.dtime_Interp, ltInterp_fh_be)
    try:
      res = pool_result.get(timeout = dyPara_ini_info["Pool"]["FH_TI_timeout"])
    except mp.TimeoutError:
      pool.terminate()
      print("timeout:{}s".format(dyPara_ini_info["Pool"]["FH_TI_timeout"]))
      sys.exit()
    else:
      pool.close()
      pool.join()
    return
  #初始化工作进程
  def init_ti_process(self, _dyInterp_rlt_nfh, _dyCommon_Para):
    # 全局变量
    global dyInterp_rlt_nfh
    global dyCommon_Para
    dyInterp_rlt_nfh = _dyInterp_rlt_nfh
    dyCommon_Para    = _dyCommon_Para
  #时间插值
  def dtime_Interp(self, ltIfh_be):
    #输出数据
    fh1="%03d"%(ltIfh_be[0]+1)
    sOut_file_name1 = fh1+"_"+fh1+".h5"
    sOut_abs_path1  = os.path.join(dyCommon_Para["sIn_sub_path"],sOut_file_name1)
    fh2="%03d"%(ltIfh_be[0]+2)
    sOut_file_name2 = fh2+"_"+fh2+".h5"
    sOut_abs_path2  = os.path.join(dyCommon_Para["sIn_sub_path"],sOut_file_name2)
    lexist1=os.path.exists(sOut_abs_path1)
    lexist2=os.path.exists(sOut_abs_path2)
    #输出插值文件=h5存在 更新参数==0
    if lexist1 and lexist2 and dyCommon_Para["update"]==0: 
      print("No update:"+dyCommon_Para["sIn_sub_path"],sOut_file_name1,sOut_file_name2)
    else:
      print("Interp_t:",ltIfh_be)
      #找出时间插值开始结束时间和数据
      ih_span=ltIfh_be[1]-ltIfh_be[0]
      if ltIfh_be[0] not in dyInterp_rlt_nfh:
        sIfh_b        = "%03d"%ltIfh_be[0]
        sIn_file_name = sIfh_b+"_"+sIfh_b+".h5"
        sIn_abs_path  = os.path.join(dyCommon_Para["sIn_sub_path"],sIn_file_name)
        if not os.path.exists(sIn_abs_path):
          if self.iDebug>=1: print("No:"+sIn_abs_path)
          return
        dybegin_data  = self.dRS3_Interp(sIn_abs_path, self.dyPQ_round)
        #print("begin",sIn_abs_path)
      else:
        dybegin_data = dyInterp_rlt_nfh[ltIfh_be[0]]
      if ltIfh_be[1] not in dyInterp_rlt_nfh:
        sIfh_e        = "%03d"%ltIfh_be[1]
        sIn_file_name = sIfh_e+"_"+sIfh_e+".h5"
        sIn_abs_path  = os.path.join(dyCommon_Para["sIn_sub_path"],sIn_file_name)
        if not os.path.exists(sIn_abs_path):
          if self.iDebug>=1: print("No:"+sIn_abs_path)
          return        
        dyend_data = self.dRS3_Interp(sIn_abs_path, self.dyPQ_round)
      else:
        dyend_data = dyInterp_rlt_nfh[ltIfh_be[1]]
      #要素循环-插值
      dyInterp_time={iIfh:{sPhyQ:None for sPhyQ in dyCommon_Para["Interp_keys"]} for iIfh in range(ltIfh_be[0]+1,ltIfh_be[1])}
      for sPhyQ in dyCommon_Para["Interp_keys"]:
        if (dybegin_data[sPhyQ] is None) or (dyend_data[sPhyQ] is None): continue
        #1h的1增量计算
        ndyIncre = np.round((dyend_data[sPhyQ]-dybegin_data[sPhyQ])/float(ih_span),self.dyPQ_round[sPhyQ]+1)
        #插值时间循环
        for ih in range(1,ih_span):
          ifhour = ltIfh_be[0]+ih #时间插值计算
          dyInterp_time[ifhour][sPhyQ] = np.round(dybegin_data[sPhyQ] + ndyIncre*float(ih),self.dyPQ_round[sPhyQ])
      ltcycle=[]
      for iIfh in range(ltIfh_be[0]+1,ltIfh_be[1]):
        #输出数据
        sOut_file_name = "%03d"%iIfh + "_" + "%03d"%iIfh+".h5"
        sOut_abs_path  = os.path.join(dyCommon_Para["sIn_sub_path"],sOut_file_name)
        lalive = os.path.exists(sOut_abs_path)
        if (not lalive) or (lalive and dyCommon_Para["update"]!=0):
          if self.iDebug>=1:print("out:"+sOut_abs_path) #submit()不是阻塞的，而是立即返回。
          ltcycle.append([sOut_abs_path, dyInterp_time[iIfh], dyCommon_Para["Interp_keys"]])
      #并行输出结果
      pool = ThreadPool(processes=2)
      pool_result = pool.map_async(self.dmulti_WS3_Interp, ltcycle)
      pool.close()
      pool.join()

      #rsts = pool_result.get()
      #print(rsts)
      #for ltc_it, tmp_name in zip(ltcycle, rsts):
      #  if tmp_name is None:
      #    print('write error:', ltc_it[0])
      #  elif os.path.exists(tmp_name):
      #    print('rename:%s %s' % (tmp_name, ltc_it[0]))
      #    os.rename(tmp_name, ltc_it[0])
      #  else:
      #    print('file not exists:', tmp_name)
    return


  #串行调用(n个物理量-n个预报时效)
  def dSerial_best_eta_NBT_nPQ(self, ltYMDH_mdl_begin, dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para):
    self.init_bp_process(dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para)
    for sYMDH_FH_mdl in ltYMDH_mdl_begin:
      self.dbest_eta_1BT_nPQ(sYMDH_FH_mdl)
    return
  #并行调用(1个物理量-多个预报时效)
  def dPool_best_eta_NBT_nPQ(self, ltYMDH_mdl_begin, dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para):
    in_cpu_core = mp.cpu_count()
    iN_file_proces=np.min([len(ltYMDH_mdl_begin),in_cpu_core,dyPara_ini_info["Pool"]["BT_max_pcount"]])
    if self.iDebug>=1:print("BT_parallel:",iN_file_proces)
    pool = mp.Pool(processes = iN_file_proces, initializer=self.init_bp_process, initargs=(dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para))
    pool_result = pool.map_async(self.dbest_eta_1BT_nPQ, ltYMDH_mdl_begin)
    try:
      res = pool_result.get(timeout = dyPara_ini_info["Pool"]["BT_timeout"])
    except mp.TimeoutError:
      pool.terminate()
      print("timeout:{}s".format(dyPara_ini_info["Pool"]["BT_timeout"]))
      sys.exit()
    else:
      pool.close()
      pool.join()
    return
  #初始化工作进程
  def init_bp_process(self, _dyGObs_PhyQ, _dymdl_Geog, _dyIntp_info, _dyPara_ini_info, _dyCommon_Para):
    # 全局变量
    global dyGObs_PhyQ
    global dymdl_Geog
    global dyIntp_info
    global dyPara_ini_info
    global dyCommon_Para
    dyGObs_PhyQ     = _dyGObs_PhyQ
    dymdl_Geog      = _dymdl_Geog
    dyIntp_info     = _dyIntp_info
    dyPara_ini_info = _dyPara_ini_info
    dyCommon_Para   = _dyCommon_Para
  #1个起报时间的最优参数求解
  def dbest_eta_1BT_nPQ(self, sYMDH_FH_mdl):
    in_cpu_core = mp.cpu_count()
    dyattr      = {"YMDH":sYMDH_FH_mdl}
    print(" ".join([sYMDH_FH_mdl[0:8]+"_"+sYMDH_FH_mdl[8:],"=", dyCommon_Para["sInterp_YMDH"]]))
    ltPQSN_Intp =[x for x in dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl].keys() if x in self.ltPQSN_Intp]
    #读取grib的地面和3D数据文件
    if dyCommon_Para["sModel_Region_upper"] in ["EC_12P5KM"]:
      ltSPQ_shortname=[]
      if '2t' in ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["2t"]
      if '2rh' in ltPQSN_Intp:
        if "2t" not in ltSPQ_shortname:
          ltSPQ_shortname = ltSPQ_shortname + ["2t","2d"]
        else:
          ltSPQ_shortname = ltSPQ_shortname + ["2d"]
      if '10ws' in ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["10u","10v"]
      # if '2t_min' in ltPQSN_Intp:
        # ltSPQ_shortname.append("mn2t3")
      # if '2t_max' in ltPQSN_Intp:
        # ltSPQ_shortname.append("mx2t3")
      # if '10gust' in ltPQSN_Intp:
        # ltSPQ_shortname.append("10fg3")
      # if 'tcc' in ltPQSN_Intp:
        # ltSPQ_shortname.append("tcc")

      # 修改读取NC函数
      dymdl_rdata = self.dRNC_for_3Dinterp(dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl]["mdl"], ltSPQ_shortname=ltSPQ_shortname)
      #对原始grib数据进行扩充物理量和整理 #扩充10m-ws,等压面层风速,2m相对湿度
      if '10ws' in ltPQSN_Intp:
        dymdl_rdata = self.dwind_expand(dymdl_rdata)
      if '2rh' in ltPQSN_Intp:
        dymdl_rdata = self.drh_expand(dymdl_rdata)
      if "tcc" in ltPQSN_Intp:
        dymdl_rdata["tcc"] = np.around(dymdl_rdata["tcc"] *100) #总云量变从0-1变为0-100
    elif dyCommon_Para["sModel_Region_upper"] in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
      ltSPQ_shortname=[]
      if '2t' in ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["2t"]
      if '2rh' in ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["2r"]
      if '10ws' in ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["10u","10v"]
      if '10gust' in ltPQSN_Intp:
        ltSPQ_shortname.append("gust")
      if 'tcc' in ltPQSN_Intp:
        ltSPQ_shortname.append("tcc")
      # 修改读取NC函数
      dymdl_rdata = self.dRNC_for_3Dinterp(dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl]["mdl"], ltSPQ_shortname=ltSPQ_shortname)
      if '10ws' in ltPQSN_Intp:
        dymdl_rdata = self.dwind_expand(dymdl_rdata)
      if "tcc" in ltPQSN_Intp:
        dymdl_rdata["tcc"] = np.around(dymdl_rdata["tcc"]) #3km的云0-100之间保存整数就行
    elif dyCommon_Para["sModel_Region_upper"] in ["GRAPES_12P5KM","GRAPES_25KM","GRAPES_GFS","CMA_GFS"]:
      ltSPQ_shortname=[]
      if '2t' in ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["2t"]
      if '2rh' in ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["2r"]
      if '10ws' in ltPQSN_Intp:
        ltSPQ_shortname = ltSPQ_shortname + ["10u","10v"]
      if '10gust' in ltPQSN_Intp:
        ltSPQ_shortname.append("gust")
      if 'tcc' in ltPQSN_Intp:
        ltSPQ_shortname.append("tcc")
      # 修改读取NC函数
      dymdl_rdata = self.dRNC_for_3Dinterp(dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl]["mdl"], ltSPQ_shortname=ltSPQ_shortname)
      if '10ws' in ltPQSN_Intp:
        if "10u" in dymdl_rdata and "10v" in dymdl_rdata:
          dymdl_rdata = self.dwind_expand(dymdl_rdata)   #产生地面和高空风速ws
      if "tcc" in ltPQSN_Intp:
        dymdl_rdata["tcc"] = np.around(dymdl_rdata["tcc"])  #3km的云0-100之间保存整数就行
    #升级模式地理信息
    dymdl_rdata.update(dymdl_Geog["lonlat_SL_IG_mdl"])
    #------------------------------------------------
    dyVR_srf_2d={}
    #2m气温-垂直变化率(C/m)
    if '2t' in ltPQSN_Intp:
      dyVR_srf_2d["2t"]  = self.dsurface_scalar_vertical_rate(dymdl_rdata, sPQ="t", mask2d_common_SL_to_ML=dymdl_Geog["mask2d_common_12P5km_to_25km"]) #上-下=南-北数据 (241, 281)
    #2m相对湿度-垂直变化率(%/m)
    if "2rh" in ltPQSN_Intp:
      dyVR_srf_2d["2rh"] = self.dsurface_scalar_vertical_rate(dymdl_rdata, sPQ="r", mask2d_common_SL_to_ML=dymdl_Geog["mask2d_common_12P5km_to_25km"]) #上-下=南-北数据 (241, 281)
    #10m风-垂直变化率(m/s/m)
    if '10ws' in ltPQSN_Intp:
      dyVR_srf_2d["10u"],dyVR_srf_2d["10v"],dyVR_srf_2d["10ws"] = self.dsurface_vector_vertical_rate(dymdl_rdata, mask2d_common_SL_to_ML=dymdl_Geog["mask2d_common_12P5km_to_25km"]) #上-下=南-北数据 (241, 281)
    #地面气压-垂直变化率(hpa/m)
    if 'sp' in ltPQSN_Intp:
      dyVR_srf_2d["sp"]  = self.dsurface_scalar_vertical_rate(dymdl_rdata, sPQ="p", mask2d_common_SL_to_ML=dymdl_Geog["mask2d_common_12P5km_to_25km"])
    if dyCommon_Para["sModel_Region_upper"] in ["EC_12P5KM"]:
      #粗网格地面要素垂直变化率插值到细网格
      #2m气温-垂直率空间插值
      if '2t' in ltPQSN_Intp:
        dyVR_srf_2d["2t"]  = self.dMesh_scalar_interp(dymdl_Geog["lonlat_SL_IG_mdl"], dymdl_Geog["lonlat_ML_IG_mdl"], dyVR_srf_2d["2t"]) #插值到12.5km 输出南-北(上-下)(481, 561)
      #2m湿度-垂直率空间插值
      if "2rh" in ltPQSN_Intp:
        dyVR_srf_2d["2rh"] = self.dMesh_scalar_interp(dymdl_Geog["lonlat_SL_IG_mdl"], dymdl_Geog["lonlat_ML_IG_mdl"], dyVR_srf_2d["2rh"])
      #10m风-垂直率空间插值
      if '10ws' in ltPQSN_Intp:
        dyVR_srf_2d["10u"],dyVR_srf_2d["10v"],dyVR_srf_2d["10ws"] = \
                             self.dMesh_vector_interp(dymdl_Geog["lonlat_SL_IG_mdl"], dymdl_Geog["lonlat_ML_IG_mdl"], dyVR_srf_2d["10u"],dyVR_srf_2d["10v"],dyVR_srf_2d["10ws"])
      #地面气压-垂直率空间插值
      if 'sp' in ltPQSN_Intp:
        dyVR_srf_2d["sp"]  = self.dMesh_scalar_interp(dymdl_Geog["lonlat_SL_IG_mdl"], dymdl_Geog["lonlat_ML_IG_mdl"], dyVR_srf_2d["sp"])
    #要素-串-循环
    for sPhyQ_shortname in ltPQSN_Intp:
      #标量
      if sPhyQ_shortname in ["2t",'2rh']:
        #并行-参数-标量
        if dyPara_ini_info["Pool"]["Para_parallel"]:
          print("P-Parallel-"+sPhyQ_shortname)
          #双线插值模式结果和评分
          dybi_score = self.dBI_Grid_score(dyIntp_info, dymdl_rdata, dyGObs_PhyQ, dyPara_ini_info, sPhyQ_shortname)
          #if self.iDebug>=1:print(f"{sPhyQ_shortname}-{dyCommon_Para['sReso']}-bi : {fMAE_bi_China:.3f} | {fhit_bi_China:.3f}")
          #并行计算多个参数
          ltcycle=[[fpara_eta, sPhyQ_shortname] for fpara_eta in dyCommon_Para["ltPara_Loss_cycle"]]
          ltbest_eta     = self.dPool_GPara_AE(ltcycle, dyIntp_info, dymdl_rdata, dyVR_srf_2d, dyGObs_PhyQ, dyPara_ini_info)
          ndybest_eta    = np.zeros(dyIntp_info["2dshape"],dtype="float32") 
          ndyAE_best_eta = dybi_score["AE_bi"].copy()  #GFS(1198,1401)=1678398
          ndybest_eta    = self.dGPara_best(dyCommon_Para["ltPara_Loss_cycle"], ltbest_eta, ndyAE_best_eta, ndybest_eta)
          ndybest_eta    = np.round(ndybest_eta,1)
          #属性-评分
          dylr_score     = self.dscore_grid_best_eta(sPhyQ_shortname, dyIntp_info, dymdl_rdata, dyVR_srf_2d[sPhyQ_shortname], 
                                                     dyGObs_PhyQ[sPhyQ_shortname], ndybest_eta, dyPara_ini_info)
          #最优参数信息
          dyattr["MAE_HIT_China"] = f"MAE_lr:{dylr_score['MAE_lr_China']:.3f} MAE_bi:{dybi_score['MAE_bi_China']:.3f} "+\
                                    f"HIT_lr:{dylr_score['HIT_lr_China']:.3f} HIT_bi:{dybi_score['HIT_bi_China']:.3f}"
          if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
            dyattr["MAE_HIT_Proce"] = f"MAE_lr:{dylr_score['MAE_lr_Proce']:.3f} MAE_bi:{dybi_score['MAE_bi_Proce']:.3f} "+\
                                      f"HIT_lr:{dylr_score['HIT_lr_Proce']:.3f} HIT_bi:{dybi_score['HIT_bi_Proce']:.3f}"
          if self.iDebug>=1:
            print("-".join([sPhyQ_shortname,dyCommon_Para["sReso"],sYMDH_FH_mdl[8:],"best","China"]).ljust(12)+\
                                       f": {dylr_score['MAE_lr_China']:.3f} {dybi_score['MAE_bi_China']:.3f} "+\
                                       f"| {dylr_score['HIT_lr_China']:.3f} {dybi_score['HIT_bi_China']:.3f}")
            if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
              print("-".join([sPhyQ_shortname,dyCommon_Para["sReso"],sYMDH_FH_mdl[8:],"best","Proce"]).ljust(12)+\
                                         f": {dylr_score['MAE_lr_Proce']:.3f} {dybi_score['MAE_bi_Proce']:.3f} "+\
                                         f"| {dylr_score['HIT_lr_Proce']:.3f} {dybi_score['HIT_bi_Proce']:.3f}")
        #串行-标量
        else:
          print("P-Serial-"+sPhyQ_shortname)
          #格点
          if dyCommon_Para["sReso"]!="Site":
            #最优eta和双线性评分
            ndybest_eta, dybi_score = self.dbest_eta_grid(sPhyQ_shortname, dyIntp_info, dymdl_rdata, dyGObs_PhyQ[sPhyQ_shortname], 
                                                          dyVR_srf_2d[sPhyQ_shortname], dyCommon_Para["ltPara_Loss_cycle"], dyPara_ini_info)
            #FRI插值结果-评分分
            dylr_score = self.dscore_grid_best_eta(sPhyQ_shortname, dyIntp_info, dymdl_rdata, dyVR_srf_2d[sPhyQ_shortname], 
                                                   dyGObs_PhyQ[sPhyQ_shortname], ndybest_eta, dyPara_ini_info)
            if self.iDebug>=1:
              print("-".join([sPhyQ_shortname,dyCommon_Para["sReso"],sYMDH_FH_mdl[8:],"best","China"]).ljust(12)+\
                                             f": {dylr_score['MAE_lr_China']:.3f} {dybi_score['MAE_bi_China']:.3f} "+\
                                             f"| {dylr_score['HIT_lr_China']:.3f} {dybi_score['HIT_bi_China']:.3f}")
              if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
                print("-".join([sPhyQ_shortname,dyCommon_Para["sReso"],sYMDH_FH_mdl[8:],"best","Proce"]).ljust(12)+\
                                               f": {dylr_score['MAE_lr_Proce']:.3f} {dybi_score['MAE_bi_Proce']:.3f} "+\
                                               f"| {dylr_score['HIT_lr_Proce']:.3f} {dybi_score['HIT_bi_Proce']:.3f}")
            #最优参数信息
            dyattr["MAE_HIT_China"] = f"MAE_lr:{dylr_score['MAE_lr_China']:.3f} MAE_bi:{dybi_score['MAE_bi_China']:.3f} "+\
                                      f"HIT_lr:{dylr_score['HIT_lr_China']:.3f} HIT_bi:{dybi_score['HIT_bi_China']:.3f}"
            if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
              dyattr["MAE_HIT_Proce"] = f"MAE_lr:{dylr_score['MAE_lr_Proce']:.3f} MAE_bi:{dybi_score['MAE_bi_Proce']:.3f} "+\
                                        f"HIT_lr:{dylr_score['HIT_lr_Proce']:.3f} HIT_bi:{dybi_score['HIT_bi_Proce']:.3f}"
          #站点
          else:
            #最优eta和双线性评分
            ndybest_eta,dybi_score = self.dbest_eta_site(sPhyQ_shortname, dyIntp_info, dymdl_rdata, dyGObs_PhyQ[sPhyQ_shortname], 
                                                         dyVR_srf_2d[sPhyQ_shortname], dyCommon_Para["ltPara_Loss_cycle"], dyPara_ini_info["threshold"][sPhyQ_shortname])
            #FRI插值结果-评分
            dylr_score = self.dscore_site_best_eta(sPhyQ_shortname, dyIntp_info, dymdl_rdata, dyVR_srf_2d[sPhyQ_shortname], 
                                                   dyGObs_PhyQ[sPhyQ_shortname], ndybest_eta, dyPara_ini_info["threshold"][sPhyQ_shortname])
            if self.iDebug>=1:
              print("-".join([sPhyQ_shortname,dyCommon_Para["sReso"],sYMDH_FH_mdl[8:],"best"]).ljust(12)+\
                                         f": {dylr_score['MAE_lr']:.3f} {dybi_score['MAE_bi']:.3f} "+\
                                         f"| {dylr_score['HIT_lr']:.3f} {dybi_score['HIT_bi']:.3f}")
            #最优参数信息
            dyattr["MAE_HIT_Site"] = f"MAE_lr:{dylr_score['MAE_lr']:.3f} MAE_bi:{dybi_score['MAE_bi']:.3f} "+\
                                     f"HIT_lr:{dylr_score['HIT_lr']:.3f} HIT_bi:{dybi_score['HIT_bi']:.3f}"
        if dyPara_ini_info["InstantInfo"]["out_China"] and dyCommon_Para["sReso"]!="Site":
          ndybest_eta[~dyIntp_info["mask_area"]]=self.RGrid_Default
        dybest_eta={sPhyQ_shortname:ndybest_eta}
        ltInterp_keys=[sPhyQ_shortname]
        #站点信息
        if dyCommon_Para["sReso"]=="Site":
          dybest_eta["site"] = dyCommon_Para["Site_Code"]
          ltInterp_keys.append("site")
        #保存每日文件夹内最优参数----------------------------------------------------------------------------
        print("out:"+dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"])
        tmp_name = self.dWS3_Interp(dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"], dybest_eta, ltInterp_keys=ltInterp_keys, dyattr=dyattr)
        #if tmp_name is None:
        #  print('write error:', dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"])
        #elif os.path.exists(tmp_name):
        #  print('rename:%s %s' % (tmp_name, dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"]))
        #  #os.rename(tmp_name, dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"])
        #else:
        #  print('file not exist:', tmp_name)

        #保存恒定文件夹内最优参数(复制)
        if dyPara_ini_info["InstantInfo"]["eta_cmn_out"]:
          if self.iDebug>=1:print("out:"+dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out1"])
          self.dCopy_rlt(dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"], dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out1"])
        print("-"*20)
      #矢量-最优参数
      elif sPhyQ_shortname in ["10ws"]:
        ltPQ_name=["10u","10v","10ws"]
        dybest_eta={}
        #并行(风场)
        if dyPara_ini_info["Pool"]["Para_parallel"]:
          print("P-Parallel-"+sPhyQ_shortname)
          for sPhyQ_shortname in ltPQ_name:
            dybi_score = self.dBI_Grid_score(dyIntp_info, dymdl_rdata, dyGObs_PhyQ, dyPara_ini_info, sPhyQ_shortname)
            #if self.iDebug>=1:print(f"{sPhyQ_shortname}-{sReso}-bi : {fMAE_bi_China:.3f} | {fhit_bi_China:.3f}")
            #并行计算多个参数
            ltcycle=[[fpara_eta, sPhyQ_shortname] for fpara_eta in dyCommon_Para["ltPara_Loss_cycle"]]
            ltbest_eta     = self.dPool_GPara_AE(ltcycle, dyIntp_info, dymdl_rdata, dyVR_srf_2d, dyGObs_PhyQ, dyPara_ini_info)
            ndybest_eta    = np.zeros(dyIntp_info["2dshape"],dtype="float32") 
            ndyAE_best_eta = dybi_score["AE_bi"].copy()  #GFS(1198,1401)=1678398
            ndybest_eta    = self.dGPara_best(dyCommon_Para["ltPara_Loss_cycle"], ltbest_eta, ndyAE_best_eta, ndybest_eta)
            ndybest_eta=np.round(ndybest_eta,1)
            #保存每日文件夹内最优参数
            if dyPara_ini_info["InstantInfo"]["out_China"] and dyCommon_Para["sReso"]!="Site":
              ndybest_eta[~dyIntp_info["mask_area"]]=self.RGrid_Default
            dybest_eta[sPhyQ_shortname]=ndybest_eta
            #属性-评分
            dylr_score = self.dscore_grid_best_eta(sPhyQ_shortname, dyIntp_info, dymdl_rdata, dyVR_srf_2d[sPhyQ_shortname], 
                                                   dyGObs_PhyQ[sPhyQ_shortname], ndybest_eta, dyPara_ini_info)
            if self.iDebug>=1:
              print("-".join([sPhyQ_shortname,dyCommon_Para["sReso"],sYMDH_FH_mdl[8:],"best","China"]).ljust(12)+\
                              f": {dylr_score['MAE_lr_China']:.3f} {dybi_score['MAE_bi_China']:.3f} "+\
                              f"| {dylr_score['HIT_lr_China']:.3f} {dybi_score['HIT_bi_China']:.3f}")
              if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
                print("-".join([sPhyQ_shortname,dyCommon_Para["sReso"],sYMDH_FH_mdl[8:],"best","Proce"]).ljust(12)+\
                                               f": {dylr_score['MAE_lr_Proce']:.3f} {dybi_score['MAE_bi_Proce']:.3f} "+\
                                               f"| {dylr_score['HIT_lr_Proce']:.3f} {dybi_score['HIT_bi_Proce']:.3f}")
            dyattr[sPhyQ_shortname+"_MAE_HIT_China"] = f"MAE_lr:{dylr_score['MAE_lr_China']:.3f} MAE_bi:{dybi_score['MAE_bi_China']:.3f} "+\
                                                       f"HIT_lr:{dylr_score['HIT_lr_China']:.3f} HIT_bi:{dybi_score['HIT_bi_China']:.3f}"
            if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
              dyattr[sPhyQ_shortname+"_MAE_HIT_Proce"] = f"MAE_lr:{dylr_score['MAE_lr_Proce']:.3f} MAE_bi:{dybi_score['MAE_bi_Proce']:.3f} "+\
                                                         f"HIT_lr:{dylr_score['HIT_lr_Proce']:.3f} HIT_bi:{dybi_score['HIT_bi_Proce']:.3f}"
        
        #串行(风场)
        else:
          print("P-Serial-"+sPhyQ_shortname)
          #u/v/ws循环
          for sPhyQ_shortname in ltPQ_name: #求最优参数
            if dyCommon_Para["sReso"]!="Site":
              ndybest_eta,dybi_score = self.dbest_eta_grid(sPhyQ_shortname, dyIntp_info, dymdl_rdata, dyGObs_PhyQ[sPhyQ_shortname], 
                                                           dyVR_srf_2d[sPhyQ_shortname], dyCommon_Para["ltPara_Loss_cycle"], dyPara_ini_info)
            else:
              ndybest_eta,dybi_score = self.dbest_eta_site(sPhyQ_shortname, dyIntp_info, dymdl_rdata, dyGObs_PhyQ[sPhyQ_shortname], 
                                                           dyVR_srf_2d[sPhyQ_shortname], dyCommon_Para["ltPara_Loss_cycle"], dyPara_ini_info["threshold"][sPhyQ_shortname])
            #保存每日文件夹内最优参数
            if dyPara_ini_info["InstantInfo"]["out_China"] and dyCommon_Para["sReso"]!="Site":
              ndybest_eta[~dyIntp_info["mask_area"]]=self.RGrid_Default
            dybest_eta[sPhyQ_shortname]=ndybest_eta
            #格点-评分
            if dyCommon_Para["sReso"]!="Site":
              dylr_score = self.dscore_grid_best_eta(sPhyQ_shortname, dyIntp_info, dymdl_rdata, dyVR_srf_2d[sPhyQ_shortname], 
                                                     dyGObs_PhyQ[sPhyQ_shortname], ndybest_eta, dyPara_ini_info)
              dyattr[sPhyQ_shortname+"_MAE_HIT_China"] = f"MAE_lr:{dylr_score['MAE_lr_China']:.3f} MAE_bi:{dybi_score['MAE_bi_China']:.3f} "+\
                                                         f"HIT_lr:{dylr_score['HIT_lr_China']:.3f} HIT_bi:{dybi_score['HIT_bi_China']:.3f}"
              if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
                dyattr[sPhyQ_shortname+"_MAE_HIT_Proce"] = f"MAE_lr:{dylr_score['MAE_lr_Proce']:.3f} MAE_bi:{dybi_score['MAE_bi_Proce']:.3f} "+\
                                                         f"HIT_lr:{dylr_score['HIT_lr_Proce']:.3f} HIT_bi:{dybi_score['HIT_bi_Proce']:.3f}"
              if self.iDebug>=1:
                print("-".join([sPhyQ_shortname,dyCommon_Para["sReso"],sYMDH_FH_mdl[8:],"best","China"]).ljust(12)+\
                                f": {dylr_score['MAE_lr_China']:.3f} {dybi_score['MAE_bi_China']:.3f} "+\
                                f"| {dylr_score['HIT_lr_China']:.3f} {dybi_score['HIT_bi_China']:.3f}")
                if dyPara_ini_info["InstantInfo"]["Prov_code"] is not None:
                  print("-".join([sPhyQ_shortname,dyCommon_Para["sReso"],sYMDH_FH_mdl[8:],"best","Proce"]).ljust(12)+\
                                                 f": {dylr_score['MAE_lr_Proce']:.3f} {dybi_score['MAE_bi_Proce']:.3f} "+\
                                                 f"| {dylr_score['HIT_lr_Proce']:.3f} {dybi_score['HIT_bi_Proce']:.3f}")
            #站点-评分
            else:
              dylr_score = self.dscore_site_best_eta(sPhyQ_shortname, dyIntp_info, dymdl_rdata, dyVR_srf_2d[sPhyQ_shortname], 
                                                     dyGObs_PhyQ[sPhyQ_shortname], ndybest_eta, dyPara_ini_info["threshold"][sPhyQ_shortname])
              dyattr[sPhyQ_shortname+"_MAE_HIT_Site"] = f"MAE_lr:{dylr_score['MAE_lr']:.3f} MAE_bi:{dybi_score['MAE_bi']:.3f} "+\
                                                        f"HIT_lr:{dylr_score['HIT_lr']:.3f} HIT_bi:{dybi_score['HIT_bi']:.3f}"
              if self.iDebug>=1:
                print("-".join([sPhyQ_shortname,dyCommon_Para["sReso"],sYMDH_FH_mdl[8:],"best"]).ljust(12)+\
                                f": {dylr_score['MAE_lr']:.3f} {dybi_score['MAE_bi']:.3f} "+\
                                f"| {dylr_score['HIT_lr']:.3f} {dybi_score['HIT_bi']:.3f}")
        #保存每日文件夹内最优参数----------------------------------------------------------------------------
        if dyCommon_Para["sReso"]=="Site": #站点信息
          dybest_eta["site"] = dyCommon_Para["Site_Code"]
        ltInterp_keys=ltPQ_name+["site"]
        print("out:"+dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"])
        tmp_name = self.dWS3_Interp(dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"], dybest_eta, ltInterp_keys=ltInterp_keys, dyattr=dyattr)
        #if tmp_name is None:
        #  print('write error:', dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"])
        #elif os.path.exists(tmp_name):
        #  print('rename:%s %s' % (tmp_name, dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"]))
        #  os.rename(tmp_name, dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"])
        #else:
        #  print('file not exist:', tmp_name)

        #保存恒定文件夹内最优参数(复制)
        if dyPara_ini_info["InstantInfo"]["eta_cmn_out"]:
          if self.iDebug>=1:print("out:"+dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out1"])
          self.dCopy_rlt(dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out"], dyCommon_Para["dyBP_Path"][sYMDH_FH_mdl][sPhyQ_shortname]["out1"])
        return

  #串行
  def dSerial_GPara_AE(self, ltcycle, dyIntp_info, dymdl_rdata, dyVR_srf_2d, dyGObs_PhyQ):
    self.init_ae_process(dyIntp_info, dymdl_rdata, dyVR_srf_2d, dyGObs_PhyQ)
    ltbest_eta = [self.dGPara_AE(fpara_eta, sPhyQ_shortname) for fpara_eta, sPhyQ_shortname in ltcycle]
    return ltbest_eta
  #并发
  def dPool_GPara_AE(self, ltcycle, dyIntp_info, dymdl_rdata, dyVR_srf_2d, dyGObs_PhyQ, dyPara_ini_info):
    in_cpu_core = mp.cpu_count();objbest_eta=[]
    iN_file_proces=np.min([len(ltcycle),in_cpu_core,dyPara_ini_info["Pool"]["Para_max_pcount"]])
    if self.iDebug>=1:print("Para_parallel:",iN_file_proces)  
    pool = ThreadPool(processes = iN_file_proces, initializer=self.init_ae_process, initargs=(dyIntp_info, dymdl_rdata, dyVR_srf_2d, dyGObs_PhyQ))
    objbest_eta = pool.starmap_async(self.dGPara_AE, ltcycle)
    try:
      res = objbest_eta.get(timeout = dyPara_ini_info["Pool"]["Para_timeout"])
    except mp.TimeoutError:
      pool.terminate()
      print("timeout:{}s".format(dyPara_ini_info["Pool"]["Para_timeout"]))
      sys.exit()
    else:
      pool.close()
      pool.join()
    return objbest_eta.get()
  #初始化工作进程
  def init_ae_process(self, _dyIntp_info, _dymdl_rdata, _dyVR_srf_2d, _dyGObs_PhyQ):
    global dyIntp_info
    global dymdl_rdata
    global dyVR_srf_2d
    global dyGObs_PhyQ  #全局变量
    dyIntp_info = _dyIntp_info
    dymdl_rdata = _dymdl_rdata
    dyVR_srf_2d = _dyVR_srf_2d
    dyGObs_PhyQ = _dyGObs_PhyQ
  #按不同参数求取并行-求格点参数中间误差并行计算
  def dGPara_AE(self, fpara_eta, sPhyQ_shortname): #, dyIntp_info, dymdl_rdata, dyVR_srf_2d, dyGObs_PhyQ):
    #地形插值#上-下(南-北)
    #if self.iDebug>=1: print(fpara_eta, sPhyQ_shortname)
    ndyinterp_lr = self.dDEM_3d_interp_scalar(dyIntp_info, dymdl_rdata, dyVR_srf_2d[sPhyQ_shortname], eta=fpara_eta, skey=sPhyQ_shortname)
    ndyinterp_lr = ndyinterp_lr.reshape(dyIntp_info["2dshape"]) #重新reshape
    #智网绝对误差#上-下(南-北)
    ndyAE=np.round(np.abs(ndyinterp_lr-dyGObs_PhyQ[sPhyQ_shortname]),3)
    return ndyAE #智网区绝对误差AE
  #最优参数求解(串)
  def dGPara_best(self, ltPara_Loss_cycle, ltAE_lr, ndyAE_best_eta, ndybest_eta):
    for fpara_eta, ndyAE_lr in zip(ltPara_Loss_cycle,ltAE_lr):
      #找出最小绝对误差对应的位置
      ndyidx_best_2d =ndyAE_lr<ndyAE_best_eta #找到最优二维索引
      ndyAE_best_eta[ndyidx_best_2d]=ndyAE_lr[ndyidx_best_2d]
      ndybest_eta[ndyidx_best_2d]=fpara_eta
    return ndybest_eta
