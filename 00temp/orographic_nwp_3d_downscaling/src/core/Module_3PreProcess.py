# -*- coding: utf-8 -*- 
# cython:language_level=3

import os
import sys
import re
import h5py
try:
  import pygrib
except ImportError:
  pass
  #print(__name__+':run in windows or no install pygrib')
import numpy  as np
import pandas as pd
from scipy import interpolate
from multiprocessing import Pool
import core.Module_MyFunction as MMyfun
import core.Module_Diagnosis as MDiag

class Class_3PreProcess(object):

  "初始化函数"
  def __init__(self, iDebug = 0):
    self.iDebug = iDebug
    self.RGrid_Default    = -32766.0
    self.iN_Frost_Time    = 0
    self.ltForecast_Time  = [0,24]
    self.cls_myfun        = MMyfun.Class_MyFunction(iDebug=0)

  #单个日期
  def dRead_PreProcess_ini(self,sIn_sub_path,sfile_name):
    try:
      with open(os.path.join(sIn_sub_path, sfile_name),'r') as fh:
       #预测时效段
       self.iN_FTime = int(fh.readline().strip('\n'))
       self.ltForecast_Time = []
       for line in fh.readlines():
         #去除空行
         if line.strip()=="":continue
         #找出需要的字符
         relt = re.split(r'\s*[;,\s]\s*', line)
         self.ltForecast_Time.extend(relt[:-1])
       #删除非数字的
       self.ltForecast_Time = [ x for x in self.ltForecast_Time if x.isdigit()][0:self.iN_FTime]
    except Exception as e:
       print(e)
  
  #日期段
  def dRead_PreProcess_P_ini(self,sIn_sub_path,sfile_name):
    try:
      with open(os.path.join(sIn_sub_path, sfile_name),'r') as fh:
       #预测时效段
       self.iN_FTime = int(fh.readline().strip('\n'))
       self.ltForecast_Time = []
       for line in fh.readlines():
         #去除空行
         if line.strip()=="":continue
         #找出需要的字符
         relt = re.split(r'\s*[;,\s]\s*', line)
         self.ltForecast_Time.append(relt[0:2])
       #删除非数字的
       self.ltForecast_Time = [ ltx for ltx in self.ltForecast_Time if ltx[0].isdigit()][0:self.iN_FTime]
    except Exception as e:
       print(e)
  
  def dmulti_S3_Interp_Sites(self,args):
    return self.dS3_Interp_Sites(*args)
  #插值Grib中1个变量到所有站点
  def dS3_Interp_Sites(self, grb, ndy_site_xy):
    inx = grb['Ni']                                        #东西方向格点数
    iny = grb['Nj']                                        #南北方向格点数
    fbegin_lat = grb['latitudeOfFirstGridPointInDegrees']  #开始纬度
    fend_lat   = grb['latitudeOfLastGridPointInDegrees']   #结束纬度
    fbegin_lon = grb['longitudeOfFirstGridPointInDegrees'] #开始经度
    fend_lon   = grb['longitudeOfLastGridPointInDegrees']  #结束经度
    if(fend_lon<0.0): fend_lon = fend_lon + 360.
    #原始网格数据
    ndy_x_lon = np.linspace(fbegin_lon, fend_lon, inx)  #西-东(小-大)
    ndy_y_lat = np.linspace(fend_lat, fbegin_lat, iny)  #南-北(小-大)
    #站点插值
    interp_rgi = interpolate.RegularGridInterpolator((ndy_y_lat, ndy_x_lon), np.flipud(grb['values'])) #南-北的数据
    rlt_interp = interp_rgi(ndy_site_xy)  
    return rlt_interp
  
  
  def dmulti_S3_Interp_RIW(self,args):
    return self.dS3_Interp_RIW(*args)
  #对1个Grib文件的读取/插值/保存
  def dS3_Interp_RIW(self, sIn_Abs_path, sOut_Abs_path, ltinterp_site_code, ndy_site_xy, cls_model, fGrid_Default=-32766.0):
    #保存的站点插值数据
    dict_site = {}
    dict_site=dict_site.fromkeys(ltinterp_site_code)
    ndy=np.zeros(cls_model.iN_elt_1t1s, dtype=np.float32)+fGrid_Default
    for key in dict_site:dict_site[key]=ndy.copy()
    #打开grib数据文件进行读取预测数据
    grbs = pygrib.open(sIn_Abs_path)
    for grb in grbs:
      idx = cls_model.find_index(grb.shortName, grb.level) #计算与EC_New_Info.ini整个数据中对应的位置
      if idx==-1:continue
      Interp_relt=self.dS3_Interp_Sites(grb, ndy_site_xy)
      #保存值
      for i,ssite_code in enumerate(ltinterp_site_code):
        dict_site[ssite_code][idx]=Interp_relt[i].copy()
    grbs.close()
    #保存数据
    temp_path = sOut_Abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_Abs_path):
      os.rename(sOut_Abs_path, temp_path)
    with h5py.File(temp_path,'a') as fh:
      ltexist_site=list(fh.keys())
      for scode in dict_site:
        if(scode in ltexist_site):
          #data = fh[scode]
          fh[scode][...] = dict_site[scode]
        else:
          fh.create_dataset(scode, data=dict_site[scode], compression="gzip", compression_opts=9)
    #重命名
    os.rename(temp_path, sOut_Abs_path)

  #多线程读S3中1个时效的数据
  def dmulti_read_S3_1t(self, args):
     return self.dread_S3_1t(*args)
  #读取S3中1个预报时次多个站点的多个物理量数据
  def dread_S3_1t(self, sIn_abs_path, ltgsite_code, iN_elt_1t1s, ndy_save_idx=[]):
    if ndy_save_idx==[]:
      ndy_save_idx = np.arange(iN_elt_1t1s)
    else:
      iN_elt_1t1s = len(ndy_save_idx)
    dy_data=dict.fromkeys(ltgsite_code)
    if os.path.exists(sIn_abs_path):
      with h5py.File(sIn_abs_path,'r') as fh:
        ltexist_site=list(fh.keys())
        for scode in ltgsite_code:
          if(scode in ltexist_site):
            dy_data[scode]=fh[scode][()][ndy_save_idx] #.value(ndy_save_idx)
          else:
            dy_data[scode]=np.zeros((iN_elt_1t1s,), dtype=np.float32)+np.nan
    else:
      for scode in ltgsite_code:
       dy_data[scode]=np.zeros((iN_elt_1t1s,), dtype=np.float32)+np.nan
    return pd.DataFrame(dy_data)
  
  
  #多线程读S3中1天N个时效的数据(获取多天的结果)
  def dmulti_read_S3_1D(self, args):
     return self.dread_S3_1D(*args)
  def dread_S3_1D(self, ltS3_Abs_path, ltmdl_sites, iN_elt_1t1s, iN_Process, ndy_save_idx=[]):
    # ltcycle=[]; pool_result=[]
    # for sIn_path in ltS3_Abs_path:
      # ltcycle.append([sIn_path,ltmdl_sites])
      # relt=self.dread_S3_1t(sIn_path,ltmdl_sites,iN_elt_1t1s)
      # pool_result.append(relt)
    if ndy_save_idx==[]:
      ltcycle=[[sIn_path,ltmdl_sites,iN_elt_1t1s] for sIn_path in ltS3_Abs_path]
    else:
      ltcycle=[[sIn_path,ltmdl_sites,iN_elt_1t1s,ndy_save_idx] for sIn_path in ltS3_Abs_path]
    pool = Pool(processes = iN_Process)
    pool_result = pool.map(self.dmulti_read_S3_1t, ltcycle)
    pool.close()
    pool.join()
    #数据合并(多个时效的读取合并到一个dataframe)(行:因子, 列:站点)
    return pd.concat(pool_result,ignore_index=True)

  #S3中格点数据变量名
  def dRS3_Grid_var_name(self, sS3_Method, sPQ_name, sPQ_type):
    #要素名
    sPQ_name_lower=sPQ_name.lower()
    if sPQ_name_lower=="temperature":
      ltPQ_name_short=["2T"]
    elif sPQ_name_lower=="relative_humidity":
      ltPQ_name_short=["2RH"]
    elif sPQ_name_lower=="visibility":
      ltPQ_name_short=["VIS"]
    elif sPQ_name_lower=="total_cloud":
      ltPQ_name_short=["TCC"]
    elif sPQ_name_lower=="wind":
      ltPQ_name_short=["10U","10V"]
    elif sPQ_name_lower=="gust":
      ltPQ_name_short=["10U","10V",'10FG3']
    #要素类型
    sPQ_type_lower=sPQ_type.lower()
    if "max" in sPQ_type_lower:
      sPQ_type_short="MAX"
    elif "min" in sPQ_type_lower:
      sPQ_type_short="MIN"
    else:
      sPQ_type_short=""
    #hdf5的要素名
    if(sS3_Method.lower()=="maxmin_24h"):
      ltrelt=[x+"_"+sPQ_type_short for x in ltPQ_name_short]
    elif(sS3_Method.lower() in ["interp_hourly"]):
      ltrelt=ltPQ_name_short
    elif(sS3_Method.lower() in ["interp_dem"]):
      ltrelt=[x.lower() for x in ltPQ_name_short]
    else:
      ltrelt=[]
    return ltrelt
  
  #S3中格点数据变量名
  def dRS3_Grid_Varname(self, sS3_Method, sPQ_name, sPQ_type):
    #要素名
    sPQ_name_lower=sPQ_name.lower()
    if sPQ_name_lower=="temperature":
      ltPQ_name_short=["2T"]
    elif sPQ_name_lower=="relativehumidity":
      ltPQ_name_short=["2RH"]
    elif sPQ_name_lower=="visibility":
      ltPQ_name_short=["VIS"]
    elif sPQ_name_lower=="totalcloud":
      ltPQ_name_short=["TCC"]
    elif sPQ_name_lower=="wind":
      ltPQ_name_short=["10U","10V"]
    elif sPQ_name_lower=="gust":
      ltPQ_name_short=["10U","10V",'10FG3']
    #要素类型
    sPQ_type_lower=sPQ_type.lower()
    if "max" in sPQ_type_lower:
      sPQ_type_short="MAX"
    elif "min" in sPQ_type_lower:
      sPQ_type_short="MIN"
    else:
      sPQ_type_short=""
    #hdf5的要素名
    if(sS3_Method.lower()=="maxmin_24h"):
      ltrelt=[x+"_"+sPQ_type_short for x in ltPQ_name_short]
    elif(sS3_Method.lower() in ["interp_hourly"]):
      ltrelt=ltPQ_name_short
    elif(sS3_Method.lower() in ["interp_dem"]):
      ltrelt=[x.lower() for x in ltPQ_name_short]
    else:
      ltrelt=[]
    return ltrelt

  #读取站点插值数据
  def dmulti_RS3_site(self, args):
     return self.dRS3_site(*args)
  #读取站点标量
  def dRS3_site(self, sIn_abs_path, sPhyQ_shortname, ltsites=None):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        with h5py.File(sIn_abs_path,'r') as fh:
          ltkeys = list(fh.keys())
          ndydata=fh[sPhyQ_shortname][()] #.value
          #有输入站点信息,说明需要区分站点和数据
          if ltsites is not None:
            skey_site="site"
            #有站点信息
            if skey_site in ltkeys:
              ndysites=fh[skey_site][()].astype("str") #获取站点信息
              if len(ltsites)!=ndysites.size:
                ndydata = np.array([ndydata[ndysites==ssites][0] if ssites in ndysites else np.nan for ssites in ltsites])
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        ndydata = np.array([])
    else:
      ndydata = np.array([])
    return ndydata
  
  #读取站点风场
  def dRS3_site_wind(self, sIn_abs_path, ltPhyQ_shortname=["10u","10v","10ws"], ltsites=None):
    #文件不存在
    dydata={sPhyQ_shortname:np.array([]) for sPhyQ_shortname in ltPhyQ_shortname}
    if os.path.exists(sIn_abs_path):
      try:
        with h5py.File(sIn_abs_path,'r') as fh:
          ltkeys = list(fh.keys())
          for sPhyQ_shortname in ltPhyQ_shortname:
            ndydata=fh[sPhyQ_shortname][()] #.value
            #有输入站点信息,说明需要区分站点和数据
            if ltsites is not None:
              skey_site="site"
              #有站点信息
              if skey_site in ltkeys:
                ndysites=fh[skey_site][()].astype("str") #获取站点信息
                if len(ltsites)!=ndysites.size:
                  ndydata = np.array([ndydata[ndysites==ssites][0] if ssites in ndysites else np.nan for ssites in ltsites])
            dydata[sPhyQ_shortname]=ndydata
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
    return dydata

  #读取格点S3数据
  def dmulti_RS3_Grid_scalar(self, args):
     return self.dRS3_Grid_scalar(*args)
  def dRS3_Grid_scalar(self, sIn_abs_path, sname, ltsites=None):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        with h5py.File(sIn_abs_path,'r') as fh:
          ltkeys = list(fh.keys())
          ndydata=fh[sname][()] #.value
          #有输入站点信息,说明需要区分站点和数据
          if ltsites is not None:
            skey_site="site"
            #有站点信息
            if skey_site in ltkeys:
              ndysites=fh[skey_site][()] #获取站点信息
              if len(ltsites)!=ndysites.size:
                ndydata = np.array([])
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        ndydata = np.array([])
    else:
      ndydata = np.array([])
    return ndydata
  
 #读取S3格点多个变量
  def dmulti_RS3_Grid_Mvar(self, args):
     return self.dRS3_Grid_Mvar(*args)
  def dRS3_Grid_Mvar(self, sIn_abs_path, ltkey):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        with h5py.File(sIn_abs_path,'r') as fh:
          ltkeys_exist = list(fh.keys())
          dydata={}
          for skey in ltkey:
            if skey in ltkeys_exist:
              dydata[skey] = fh[skey][()] #.value
            else:
              dydata[skey] = np.array([])
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        dydata = {skey:np.array([]) for skey in ltkey}
    else:
      dydata = {skey:np.array([]) for skey in ltkey}
    return dydata
    
  #读取格点实况
  def dmulti_RS3_Grid_Scalar_DYN(self, args):
     return self.dRS3_Grid_Scalar_DYN(*args)
  def dRS3_Grid_Scalar_DYN(self, sIn_abs_path, sname):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        with h5py.File(sIn_abs_path,'r') as fh:
          ndy_data=fh[sname][()] #.value
          ndy_10U=fh["10U"][()]
          ndy_10V=fh["10V"][()]
          ndy_10GMA=fh["10GMA"][()]
          ndy_SFW=fh["SFW"][()]
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        ndy_data  = np.array([])
        ndy_10U   = np.array([])
        ndy_10V   = np.array([])
        ndy_10GMA = np.array([])
        ndy_SFW   = np.array([])
    else:
      ndy_data  = np.array([])
      ndy_10U   = np.array([])
      ndy_10V   = np.array([])
      ndy_10GMA = np.array([])
      ndy_SFW   = np.array([])
    return [ndy_data,ndy_10U,ndy_10V,ndy_10GMA,ndy_SFW]

  #读取格点风实况
  def dmulti_RS3_Grid_wind(self,args):
     return self.dRS3_Grid_wind(*args)
  def dRS3_Grid_wind(self, sIn_abs_path, ltvar):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        with h5py.File(sIn_abs_path,'r') as fh:
          ndy_data1=fh[ltvar[0]][()]
          ndy_data2=fh[ltvar[1]][()]
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        ndy_data1 = np.array([])
        ndy_data2 = np.array([])
    else:
      ndy_data1 = np.array([])
      ndy_data2 = np.array([])
    return [ndy_data1,ndy_data2]
  
  #读取格点风实况
  def dmulti_RS3_Grid_Gust(self,args):
     return self.dRS3_Grid_Gust(*args)
  def dRS3_Grid_Gust(self, sIn_abs_path, ltvar):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        with h5py.File(sIn_abs_path,'r') as fh:
          ndy_data1=fh[ltvar[0]][()]  #"10U",
          ndy_data2=fh[ltvar[1]][()]  #"10V",
          ndy_data3=fh[ltvar[1]][()]  #"10FG3"
          #UV_to_Wind
          ndydir,ndyspd = self.cls_myfun.dUV_to_Wind(ndy_data1, ndy_data2)
          #再从Wind_to_UV
          ndy_data1,ndy_data2 = self.cls_myfun.dWind_to_UV(ndydir,ndy_data3)
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        ndy_data1 = np.array([])
        ndy_data2 = np.array([])
    else:
      ndy_data1 = np.array([])
      ndy_data2 = np.array([])
    return [ndy_data1,ndy_data2]
  
  #多天的插值
  def dmulti_Interp_S3_Grid(self, args):
    return self.dInterp_S3_Grid(*args)
  #插值
  def dInterp_S3_Grid(self, ndy_grid, ndy_x_lon, ndy_y_lat, ndy_site_xy):
    '''
      ndy_x_lon 西-东(小-大)
      ndy_y_lat 南-北(小-大)
    '''
    #原始网格数据
    #ndy_x_lon = np.linspace(fbegin_lon, fend_lon, inx)  #西-东(小-大)
    #ndy_y_lat = np.linspace(fbegin_lat, fend_lat, iny)  #南-北(小-大)
    #站点插值
    interp_rgi = interpolate.RegularGridInterpolator((ndy_y_lat, ndy_x_lon), ndy_grid) #南-北的数据
    ndy_interp = interp_rgi(ndy_site_xy)  
    return ndy_interp
    

  #输出插值结果文件(输出5*5细网格)
  def dOut_hdf5(self, sOut_Abs_path, ltelements, dyPhyQ, update=0):
    #判断文件夹存在
    (shdf5_path,shdf5_file_name)  = os.path.split(sOut_Abs_path)
    if not os.path.exists(shdf5_path): os.makedirs(shdf5_path)
    #清除临时文件
    stemp_path=sOut_Abs_path+".tmp"
    if os.path.exists(stemp_path): os.remove(stemp_path)
    with h5py.File(stemp_path,'a') as fh:
      ltexist_PQ=list(fh.keys())
      for skey in ltelements:
        skey_upper=skey.upper()
        if((skey_upper in ltexist_PQ) and update==1): #强制更新
          fh[skey_upper][...]=dyPhyQ[skey]
        else:
          fh.create_dataset(skey_upper, data=dyPhyQ[skey], compression="gzip", compression_opts=9)
    os.rename(stemp_path, sOut_Abs_path)
    return

  
  def dS3multi_accum_split_ec(self, args):
    return self.dS3_accum_split_ec(*args)
  #累积量分解 & 时间和空间插值 & 输出1h的5*5细网格
  def dS3_accum_split_ec(self, ltIn_Abs_path, sOut_Abs_path, ltelements, lt1d_lonlat_raw, ndy_points_xy, shape2d_interp, method='nearest'): 
    '''
      降水量拆分并插值到细网格
      method         :插值方案 'linear' 'nearest'
      ltelements     :简写物理量名列表
      lt1d_lonlat_ec :模式产品1d经纬度[经度,纬度]  #西-东(小-大) #南-北(小-大)
      ndy_points_xy  :插值点,[[纬度 经度]] [n,2]
      shape2d_interp :插值后1d变2d的reshape维度元祖
    '''
    # #输出grib 数据测试(调试使用)
    # skey="tp"
    # grbs = pygrib.open(ltIn_Abs_path[1])
    # grb=grbs.select(shortName=skey)[0]
    # ndyvalues=grb.values  #上-下=北-南
    # print(ndyvalues)
    # stemp_path="/data3/zxq/IGF_sys/GMOSRR/3PreProcess/Cumulant_Decompose/EC_New/"+"a.grb"
    # with open(stemp_path,'wb') as grbout:
      # grbout.write(grb.tostring())
    # grbs.close()
    # print("=====================================")
    # #输出hdf5
    # print(np.flipud(ndyvalues)) #上-下=南-北
    # stemp_path="/data3/zxq/IGF_sys/GMOSRR/3PreProcess/Cumulant_Decompose/EC_New/"+"b.h5"
    # with h5py.File(stemp_path, 'w') as fh:
      # fh.create_dataset(skey, data=np.flipud(ndyvalues) , compression="gzip", compression_opts=9)
    # print("over")
    # sys.exit()
    #读取grib
    #第1时物理量(前面时效累积量)
    dyPhyQ_t1={x:None for x in ltelements}
    grbs = pygrib.open(ltIn_Abs_path[0])
    for selem in ltelements:
      try:
        grb=grbs.select(shortName=selem)[0]
        dyPhyQ_t1[selem] = grb.values       #上-下 = 北-南  左-右 = 西-东  .shape(481 561)
      except ValueError:                    #南-北 = 60-0:0.125 = 481个点 西-东 = 70-140:0.125 = 561个点
        continue
    grbs.close()
    #==========================================================
    #第4时物理量
    dyPhyQ_t4={x:None for x in ltelements}
    grbs = pygrib.open(ltIn_Abs_path[1])
    for selem in ltelements:
      try:
        grb=grbs.select(shortName=selem)[0]
        dyPhyQ_t4[selem] = grb.values
      except ValueError:
        continue
    # #获取信息
    # fbegin_lon = grb['longitudeOfFirstGridPointInDegrees'] #西=70
    # fend_lon   = grb['longitudeOfLastGridPointInDegrees']  #东=140
    # fbegin_lat = grb['latitudeOfFirstGridPointInDegrees']  #北=60
    # fend_lat   = grb['latitudeOfLastGridPointInDegrees']   #南=0
    # in_lon_x   = grb['Ni'] #西-东格点数=561
    # in_lat_y   = grb['Nj'] #南-北格点数=481
    grbs.close()
    #==========================================================
    #累积量拆分
    dyPhyQ_t4_raw={x:None for x in ltelements}
    for selem in ltelements:
      if dyPhyQ_t4[selem] is not None and dyPhyQ_t1[selem] is not None:
        ndyPhyQ=dyPhyQ_t4[selem]-dyPhyQ_t1[selem]
        if selem in ['tp','cp','lsp']: ndyPhyQ=ndyPhyQ*1000 #降水m-mm
        ndyPhyQ[ndyPhyQ<0.1]=0.0
        dyPhyQ_t4_raw[selem] = ndyPhyQ
    #==========================================================
    # #原始网格数据
    # ndy_x_lon = np.linspace(fbegin_lon, fend_lon  , in_lon_x)  #西-东(左-右) 1d数组(70,...,140)
    # ndy_y_lat = np.linspace(fend_lat  , fbegin_lat, in_lat_y)  #南-北(上-下) 1d数组(60,...,0)
    #累积量空间插值
    dyPhyQ_t4_itp={x:None for x in ltelements}
    for selem in ltelements:  
      interp_rgi = interpolate.RegularGridInterpolator((lt1d_lonlat_raw[1], lt1d_lonlat_raw[0]), np.flipud(dyPhyQ_t4_raw[selem]), method=method) #北-南的数据
      #插值
      ndyinterp = interp_rgi(ndy_points_xy).reshape(shape2d_interp) #南-北(上-下)
      ndyinterp[ndyinterp<0.1]=0.0
      #ndyinterp = np.flipud(ndyinterp)  #北-南(上-下)
      dyPhyQ_t4_itp[selem] = ndyinterp
    #==========================================================
    #3h累积量输出到hdf5
    self.dOut_hdf5(sOut_Abs_path, ltelements,  dyPhyQ_t4_itp)
    #==========================================================
    #1h累积量
    #输出文件夹拆分
    sOut_Sub_path, sOut_file_name = os.path.split(sOut_Abs_path)
    #时间间隔
    ibegin_hour=int(sOut_file_name[0:3])
    ispan=int(sOut_file_name[4:7])-ibegin_hour
    #3h间隔
    if ispan==3:                             #t =ibegin_hour 例如:3,4,5,6
      dy1hPQ_t1={x:None for x in ltelements} #t1=ibegin_hour+1
      dy1hPQ_t2={x:None for x in ltelements} #t2=ibegin_hour+2
      dy1hPQ_t3={x:None for x in ltelements} #t3=ibegin_hour+3
      for selem in ltelements:  
        mask=np.where((0.1<=dyPhyQ_t4_itp[selem]) & (dyPhyQ_t4_itp[selem]<0.3))
        ndy1hPQ_t1=dyPhyQ_t4_itp[selem]/3. #1h的量 插值成3份
        ndy1hPQ_t1[ndy1hPQ_t1<0.1]=0.0     #1h和2h的量,
        ndy1hPQ_t3=ndy1hPQ_t1.copy()       #3h的量
        ndy1hPQ_t3[mask]=dyPhyQ_t4_itp[selem][mask] #因为拆分前总量<0.3的拆分后会<0.1,前面<0.1的=0了,把值放在最后一个
        dy1hPQ_t1[selem]=ndy1hPQ_t1
        dy1hPQ_t2[selem]=ndy1hPQ_t1
        dy1hPQ_t3[selem]=ndy1hPQ_t3
      #t+1
      sOut_file_name="%03d"%(ibegin_hour)+"_"+"%03d"%(ibegin_hour+1)+".h5"
      sOut_Abs_path  = os.path.join(sOut_Sub_path, sOut_file_name)
      self.dOut_hdf5(sOut_Abs_path, ltelements,  dy1hPQ_t1)
      #t+2
      sOut_file_name="%03d"%(ibegin_hour+1)+"_"+"%03d"%(ibegin_hour+2)+".h5"
      sOut_Abs_path  = os.path.join(sOut_Sub_path, sOut_file_name)
      self.dOut_hdf5(sOut_Abs_path, ltelements,  dy1hPQ_t2)
      #t+3
      sOut_file_name="%03d"%(ibegin_hour+2)+"_"+"%03d"%(ibegin_hour+3)+".h5"
      sOut_Abs_path  = os.path.join(sOut_Sub_path, sOut_file_name)
      self.dOut_hdf5(sOut_Abs_path, ltelements,  dy1hPQ_t3)
    elif ispan==6:
      dy1hPQ_t1={x:None for x in ltelements} #t1=ibegin_hour+3
      dy1hPQ_t2={x:None for x in ltelements} #t2=ibegin_hour+6
      for selem in ltelements:  
        mask=np.where((0.1<=dyPhyQ_t4_itp[selem]) & (dyPhyQ_t4_itp[selem]<0.2))
        # ndy1hPQ_t1=dyPhyQ_t4_itp[selem]/2. #1h的量 插值成2份
        # ndy1hPQ_t1[ndy1hPQ_t1<0.1]=0.0     #1h的量
        # ndy1hPQ_t2[mask]=dyPhyQ_t4_itp[selem][mask] #因为拆分前总量<0.3的拆分后会<0.1,前面<0.1的=0了,把值放在最后一个
        # dy1hPQ_t1[selem]=ndy1hPQ_t1
        # dy1hPQ_t2[selem]=ndy1hPQ_t2
      #t+1
      sOut_file_name="%03d"%(ibegin_hour)+"_"+"%03d"%(ibegin_hour+3)+".h5"
      sOut_Abs_path  = os.path.join(sOut_Sub_path, sOut_file_name)
      self.dOut_hdf5(sOut_Abs_path, ltelements,  dy1hPQ_t1)
      #t+2
      sOut_file_name="%03d"%(ibegin_hour+3)+"_"+"%03d"%(ibegin_hour+6)+".h5"
      sOut_Abs_path  = os.path.join(sOut_Sub_path, sOut_file_name)
      self.dOut_hdf5(sOut_Abs_path, ltelements,  dy1hPQ_t2)
    return
    

  #输出3km插值结果文件(输出5*5细网格)
  def dOut_hdf5_3km(self, sOut_Abs_path, dyPhyQ, update=0):
    #判断文件夹存在
    (shdf5_path,shdf5_file_name)  = os.path.split(sOut_Abs_path)
    if not os.path.exists(shdf5_path): os.makedirs(shdf5_path)
    #清除临时文件
    stemp_path=sOut_Abs_path+".tmp"
    if os.path.exists(stemp_path): os.remove(stemp_path)
    with h5py.File(stemp_path,'a') as fh:
      ltexist_PQ=list(fh.keys())
      for skey in dyPhyQ:
        skey_upper=skey.upper()
        if((skey_upper in ltexist_PQ) and update==1): #强制更新
          fh[skey_upper][...]=dyPhyQ[skey]
        else:
          fh.create_dataset(skey_upper, data=dyPhyQ[skey], compression="gzip", compression_opts=9)
    os.rename(stemp_path, sOut_Abs_path)
    return

  #3km降水累积量分解 & 时间和空间插值 & 输出1h的5*5细网格
  def dS3multi_accum_split_3km(self, args):
    return self.dS3_accum_split_3km(*args)
  def dS3_accum_split_3km(self, ltIn_Abs_path, sOut_Abs_path, dyelements, lt1d_lonlat_raw, ndy_points_xy, shape2d_interp, method='nearest'): 
    '''
      降水量拆分并插值到细网格
      method         :插值方案 'linear' 'nearest'
      dyelements     :简写物理量名字典
      lt1d_lonlat_ec :模式产品1d经纬度[经度,纬度]  #西-东(小-大) #南-北(小-大)
      ndy_points_xy  :插值点,[[纬度 经度]] [n,2]
      shape2d_interp :1d-2d的reshape维度元祖
    '''
    dyelements={"tp":[1,8]}
    #==========================================================
    #第1时物理量(前面时效累积量)
    dyPhyQ_t1={x:None for x in dyelements}
    grbs = pygrib.open(ltIn_Abs_path[0])
    for grb in grbs:
      ltparaCN=[grb["parameterCategory"],grb["parameterNumber"]]
      if ltparaCN==[1,8]: #总降水
        selem            = 'tp'        
        dyPhyQ_t1[selem] = grb.values  #上-下 = 北-南  左-右 = 西-东.shape(1159,1190)
    grbs.close()
    #==========================================================
    #第1时物理量(前面时效累积量)
    dyPhyQ_t2={x:None for x in dyelements}
    grbs = pygrib.open(ltIn_Abs_path[1])
    for grb in grbs:
      ltparaCN=[grb["parameterCategory"],grb["parameterNumber"]]
      if ltparaCN==[1,8]: #总降水
        selem            = 'tp'        #北-南 = 60.1-10.:0.03 = 1671个点 西-东 = 70.0-145:0.03 = 2501个点
        dyPhyQ_t2[selem] = grb.values  #上-下 = 北-南  左-右 = 西-东.shape(1159,1190)
        # #获取信息
        # fbegin_lon = grb['longitudeOfFirstGridPointInDegrees'] #西=70.0
        # fend_lon   = grb['longitudeOfLastGridPointInDegrees']  #东=145
        # fbegin_lat = grb['latitudeOfFirstGridPointInDegrees']  #北=60.1
        # fend_lat   = grb['latitudeOfLastGridPointInDegrees']   #南=10
        # in_lon_x   = grb['Ni'] #西-东格点数=561
        # in_lat_y   = grb['Nj'] #南-北格点数=481
    grbs.close()
    # print(ltIn_Abs_path[0])
    # print(ltIn_Abs_path[1])
    # print(fbegin_lon,fend_lon,in_lon_x)
    # print(fbegin_lat,fend_lat,in_lat_y)
    # sys.exit()
    #==========================================================
    #拆分量
    dyPhyQ_t3_raw={x:None for x in dyelements}
    for selem in dyelements:
      if dyPhyQ_t2[selem] is not None and dyPhyQ_t1[selem] is not None:
        ndyPhyQ=dyPhyQ_t2[selem]-dyPhyQ_t1[selem]
        if selem in ['tp','cp','lsp']: ndyPhyQ=ndyPhyQ*1000 #降水m-mm
        ndyPhyQ[ndyPhyQ<0.1]=0.0
        dyPhyQ_t3_raw[selem] = ndyPhyQ
    #==========================================================
    # #原始网格数据
    # ndy_x_lon = np.linspace(fbegin_lon, fend_lon  , in_lon_x)  #西-东(左-右) 1d数组(70,...,145)  2501
    # ndy_y_lat = np.linspace(fend_lat  , fbegin_lat, in_lat_y)  #南-北(上-下) 1d数组(10,...,60.1) 1671
    # print(dyPhyQ_t3_raw['tp'].shape)
    # print(ndy_x_lon)
    # print(ndy_y_lat)
    # sys.exit()
    #累积量空间插值
    dyPhyQ_t4_itp={x:None for x in dyelements}
    for selem in dyelements:  
      interp_rgi = interpolate.RegularGridInterpolator((lt1d_lonlat_raw[1], lt1d_lonlat_raw[0]), np.flipud(dyPhyQ_t3_raw[selem]), method=method) #北-南的数据
      #插值
      ndyinterp = interp_rgi(ndy_points_xy).reshape(shape2d_interp) #南-北(上-下)
      ndyinterp[ndyinterp<0.1]=0.0
      #ndyinterp = np.flipud(ndyinterp)  #北-南(上-下)
      dyPhyQ_t4_itp[selem] = ndyinterp
    #==========================================================
    #1h累积量输出到hdf5
    self.dOut_hdf5_3km(sOut_Abs_path,  dyPhyQ_t4_itp)
    #==========================================================
    return


  #输出ec插值结果文件(输出5*5细网格)
  def dOut_hdf5_mxmi_ec(self, sOut_Abs_path, dyPhyQ, update=0):
    #判断文件夹存在
    (shdf5_path,shdf5_file_name)  = os.path.split(sOut_Abs_path)
    if not os.path.exists(shdf5_path): os.makedirs(shdf5_path)
    #清除临时文件
    stemp_path=sOut_Abs_path+".tmp"
    if os.path.exists(stemp_path): os.remove(stemp_path)
    with h5py.File(stemp_path,'a') as fh:
      ltexist_PQ=list(fh.keys())
      for skey in dyPhyQ:
        skey_upper=skey.upper()
        if((skey_upper in ltexist_PQ) and update==1): #强制更新
          for x in dyPhyQ[skey]:
            if x is not None:
              fh[skey_upper][...]=x
        else:
          for x in dyPhyQ[skey]:
            if x is not None:
              fh.create_dataset(skey_upper, data=x, compression="gzip", compression_opts=9)
    os.rename(stemp_path, sOut_Abs_path)
    return

  #并行读取多个文件
  def dmulti_dget_1grib_ec(self,args):
    return self.dget_1grib_ec(*args)
  #读取1个文件多个要素
  def dget_1grib_ec(self, sIn_abs_path, ltshortName):
    '''
      ltshortName = [[grib中变量简写名, 输入变量名]]
    '''
    dyPQ={ltkey[1]:None for ltkey in ltshortName}
    if os.path.exists(sIn_abs_path):
      grbs = pygrib.open(sIn_abs_path)
      for ltkey in ltshortName:
        try:
          if ltkey[0]=="2rh": #相对湿度
            grb_2t=grbs.select(shortName="2t")[0] #2m温度
            grb_2d=grbs.select(shortName="2d")[0] #2m露点
            rlt=MDiag.relative_humidity(grb_2t.values,grb_2d.values) #计算相对湿度
            rlt=np.round(rlt,2)
          elif ltkey[0]=="10fg3": #风场
            grb_10u=grbs.select(shortName="10u")[0]     #10m_u风
            grb_10v=grbs.select(shortName="10v")[0]     #10m_v风
            grb_fg=grbs.select(shortName="10fg3")[0]    #10m_阵风
            rlt_10u=np.round(grb_10u.values,2)
            rlt_10v=np.round(grb_10v.values,2)
            rlt_fg =np.round(grb_fg.values,2)
          else: 
            grb=grbs.select(shortName=ltkey[0])[0]  #上-下 = 北-南  左-右 = 西-东  .shape(481 561)
            rlt=np.round(grb.values,2)              #北-南 = 60-0:0.125 = 481个点 西-东 = 70-140:0.125 = 561个点
        except ValueError:
          rlt     = None
          rlt_10u = None
          rlt_10v = None
          rlt_fg  = None
        if ltkey[0]=="10fg3":
          dyPQ["10U_MAX"]=rlt_10u
          dyPQ["10V_MAX"]=rlt_10v
          dyPQ[ltkey[1]]=rlt_fg
        else:
          dyPQ[ltkey[1]]=rlt
      grbs.close()
    return dyPQ

  #变量名称转变(输入的变量名转换)
  def dname_to_shortname(self, sIn_name):
    sIn_name_lower=sIn_name.lower()
    if sIn_name_lower=="2t_max":
      sOut_name="mx2t3"
    elif sIn_name_lower=="2t_min":
      sOut_name="mn2t3"
    elif sIn_name_lower=="10w_max":
      sOut_name="10fg3"
    elif sIn_name_lower=="vis_min":
      sOut_name="vis"
    elif sIn_name_lower=="2rh_max":
      sOut_name="2rh"
    elif sIn_name_lower=="2rh_min":
      sOut_name="2rh"
    else:
      sOut_name=None
    return sOut_name

  #日变最大最小求取
  def dS3_MaxMin_EC(self, ltIn_Abs_path, sOut_Abs_path, ltelements, lt1d_lonlat_ec, ndy_points_xy, shape2d_interp, method='linear'): 
    '''
      最大最小值求取并插值到细网格
      ltelements     :简写物理量名列表
      lt1d_lonlat_ec :模式产品1d经纬度[经度,纬度]  #西-东(小-大) #南-北(小-大)
      ndy_points_xy  :插值点,[[纬度 经度]] [n,2]
      shape2d_interp :1d-2d的reshape维度元祖
    '''
    ltelements  = [x.upper() for x in ltelements] #全部大写
    #ec模式产品的2d-shape
    ltec_shape=[len(lt1d_lonlat_ec[1]),len(lt1d_lonlat_ec[0])]
    #ec_grib中简写名
    ltshortName = [[self.dname_to_shortname(sele),sele] for sele in ltelements] #[[grib中变量简写名, 输入变量名]]
    ltshortName = [ltwork for ltwork in ltshortName if ltwork[0] is not None]   #删除无效的None
    if not ltshortName: #列表空
      print("Error:",ltelements)
      return
    #从多个时次文件中读取多个物理量
    ltcycle=[[x,ltshortName] for x in ltIn_Abs_path] 
    iN_Process = len(ltcycle)
    pool = Pool(processes = iN_Process)
    pool_result = pool.map(self.dmulti_dget_1grib_ec, ltcycle) #多个字典组成的列表[{},{}...] #每个字典为1个时次
    pool.close() #多个时次的结果
    pool.join()
    #多文件多变量[{},{}...]变为{skymax:[最大,最小]}的结构,插值到5km
    if "10W_MAX" in ltelements:
      dyPQ_mxmi={skey:[None,None] for skey in ltelements if skey!="10W_MAX"}
      dyPQ_mxmi["10U_MAX"]=[None,None]
      dyPQ_mxmi["10V_MAX"]=[None,None]
      dyPQ_mxmi["10WS_MAX"]=[None,None]
    else:  
      dyPQ_mxmi={skey:[None,None] for skey in ltelements}
    #要素循环
    for sIn_name in ltelements: 
      #矢量场
      if sIn_name in ["10W_MAX"]:
        #同1个要素多个时效的数组在1个列表中
        ltu=[dyPQ["10U_MAX"].flatten() for dyPQ in pool_result if dyPQ["10U_MAX"] is not None]
        ltv=[dyPQ["10V_MAX"].flatten() for dyPQ in pool_result if dyPQ["10V_MAX"] is not None]
        ltws=[dyPQ[sIn_name].flatten() for dyPQ in pool_result if dyPQ[sIn_name] is not None]
        if (not ltu) or (not ltv) or (not ltws): continue
        ndyPQ1d_uu=np.vstack(ltu)
        ndyPQ1d_vv=np.vstack(ltv)
        ndyPQ1d_wss=np.vstack(ltws)  #(8, 269841)
        # print(ndyPQ1d_wss)
        #每1列上求最大(上-下 = 北-南  左-右 = 西-东)
        ndyPQ1d_ws=np.nanmax(ndyPQ1d_wss,axis=0).reshape(ltec_shape) #(481, 561)
        ndyrow = np.nanargmax(ndyPQ1d_wss,axis=0) #时间上选出数组中最大值的行索引 1d
        ndycol = np.arange(ndyPQ1d_wss.shape[1])  #列索引 1d
        #最大值时间对应的u 和 v
        ndyPQ1d_u = ndyPQ1d_uu[ndyrow,ndycol].reshape(ltec_shape)
        ndyPQ1d_v = ndyPQ1d_vv[ndyrow,ndycol].reshape(ltec_shape)
        #UV_to_Wind
        ndydir,ndyspd = self.cls_myfun.dUV_to_Wind(ndyPQ1d_u, ndyPQ1d_v)
        #再从Wind_to_UV
        ndyU,ndyV = self.cls_myfun.dWind_to_UV(ndydir,ndyPQ1d_ws)
        ndyU=np.round(ndyU,2)
        ndyV=np.round(ndyV,2)
        #10U_MAX插值函数
        interp_rgi = interpolate.RegularGridInterpolator((lt1d_lonlat_ec[1], lt1d_lonlat_ec[0]), np.flipud(ndyU), method=method) #南-北的数据
        #插值
        ndyinterp = interp_rgi(ndy_points_xy).reshape(shape2d_interp) #南-北(上-下)
        ndyinterp=np.round(ndyinterp,2)
        #保存最小
        dyPQ_mxmi["10U_MAX"][1]=ndyinterp
        #10V_MAX插值函数
        interp_rgi = interpolate.RegularGridInterpolator((lt1d_lonlat_ec[1], lt1d_lonlat_ec[0]), np.flipud(ndyV), method=method) #南-北的数据
        #插值
        ndyinterp = interp_rgi(ndy_points_xy).reshape(shape2d_interp) #南-北(上-下)
        ndyinterp=np.round(ndyinterp,2)
        #保存最小
        dyPQ_mxmi["10V_MAX"][1]=ndyinterp
        #10WS_MAX插值函数
        interp_rgi = interpolate.RegularGridInterpolator((lt1d_lonlat_ec[1], lt1d_lonlat_ec[0]), np.flipud(ndyPQ1d_ws), method=method) #南-北的数据
        #插值
        ndyinterp = interp_rgi(ndy_points_xy).reshape(shape2d_interp) #南-北(上-下)
        ndyinterp=np.round(ndyinterp,2)
        #保存最小
        dyPQ_mxmi["10WS_MAX"][1]=ndyinterp
      #标量场
      else:
        ltwork=[dyPQ[sIn_name].flatten() for dyPQ in pool_result if dyPQ[sIn_name] is not None]
        if not ltwork: continue
        ndyPQ1d=np.vstack(ltwork) #1维数组(行:时间,列:格点号)
        if sIn_name in ["2T_MAX","2RH_MAX"]:
          #求最大(上-下 = 北-南  左-右 = 西-东)
          ndyPQ1d=np.nanmax(ndyPQ1d,axis=0).reshape(ltec_shape)  
          #插值函数
          interp_rgi = interpolate.RegularGridInterpolator((lt1d_lonlat_ec[1], lt1d_lonlat_ec[0]), np.flipud(ndyPQ1d), method=method) #南-北的数据
          #插值
          ndyinterp = interp_rgi(ndy_points_xy).reshape(shape2d_interp) #南-北(上-下)
          #保存最大
          dyPQ_mxmi[sIn_name][0]=ndyinterp
        elif sIn_name in ["2T_MIN","VIS_MIN","2RH_MIN"]:
          #求最小(上-下 = 北-南  左-右 = 西-东)
          ndyPQ1d=np.nanmin(ndyPQ1d,axis=0).reshape(ltec_shape)  
          #插值函数
          interp_rgi = interpolate.RegularGridInterpolator((lt1d_lonlat_ec[1], lt1d_lonlat_ec[0]), np.flipud(ndyPQ1d), method=method) #南-北的数据
          #插值
          ndyinterp = interp_rgi(ndy_points_xy).reshape(shape2d_interp) #南-北(上-下)
          #保存最小
          dyPQ_mxmi[sIn_name][1]=ndyinterp
    #保存
    self.dOut_hdf5_mxmi_ec(sOut_Abs_path, dyPQ_mxmi, update=0)
    return












