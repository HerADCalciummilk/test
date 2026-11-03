# -*- coding: utf-8 -*- 
# cython:language_level=3
import os
import sys
import datetime
import h5py
import numpy  as np
import pandas as pd
try:
  import netCDF4 as nc
except ImportError:
  nc = None
try:
  import pygrib
except ImportError:
  pass
  #print(__name__+':run in windows or no install pygrib')
import Module_MyFunction as MMyfun
import collections
from configparser import ConfigParser

class LatlonInfo:
  """
  经纬度信息类
  """
  def __init__(self):
    self.lon_precision = ''
    self.lat_precision = ''
    self.lon_start     = ''
    self.lon_end       = ''
    self.lat_start     = ''
    self.lat_end       = ''
    self.N_lons        = ''
    self.N_lats        = ''

class Class_Obs_DataBase(object):

  "初始化函数"
  def __init__(self, iDebug = 0):
    self.iDebug         = iDebug                #>=1:调试, 0:业务
    #self.sObs_Main_Path = ""
    #self.latlon_info    = ""
    self.obs_info       = {}
    self.cls_myfun      = MMyfun.Class_MyFunction(iDebug=0)
    return

  #Obs_Info.ini
  def dRObs_Info_ini(self,sRoot_Path, sfile_name="Obs_Info.ini", smid_folder="Parameter", encoding="utf8"):
    """
    按行解析ini配置文件并存到数据结构
    :param file_path: ini文件路径
    :return:
    """
    if sRoot_Path=="." or sRoot_Path=="":
      sIn_abs_path=sfile_name
    else:
      sIn_abs_path=os.path.join(sRoot_Path, smid_folder, sfile_name)
    if not os.path.exists(sIn_abs_path):
      print("No:"+sIn_abs_path)
      sys.exit()

    try:
      cfg = ConfigParser()
      cfg.read(sIn_abs_path, encoding=encoding)

      '''
      sections = cfg.sections()
      for section in sections:
        self.obs_info[section] = {}

        sec_items = cfg.items(section)
        for sec_item in sec_items:
          self.obs_info[section][sec_item[0]] = sec_item[1]
        '''
      #Site
      section_name = 'Site'
      self.obs_info[section_name] = {}
      self.obs_info[section_name]['path'] = cfg.get(section_name, 'path')
      self.obs_info[section_name]['site_name'] = cfg.get(section_name, 'site_name')
      #Grid_5km
      section_name = 'Grid_5km'
      self.obs_info[section_name] = {}
      self.obs_info[section_name]['path'] = cfg.get(section_name, 'path')
      self.obs_info[section_name]['lat_north'] = float(cfg.get(section_name, 'lat_north'))
      self.obs_info[section_name]['lat_south'] = float(cfg.get(section_name, 'lat_south'))
      self.obs_info[section_name]['lon_west'] = float(cfg.get(section_name, 'lon_west'))
      self.obs_info[section_name]['lon_east'] = float(cfg.get(section_name, 'lon_east'))
      self.obs_info[section_name]['reso_lat'] = float(cfg.get(section_name, 'reso_lat'))
      self.obs_info[section_name]['reso_lon'] = float(cfg.get(section_name, 'reso_lon'))
      #Grid_5km
      section_name = 'Grid_1km'
      self.obs_info[section_name] = {}
      self.obs_info[section_name]['path'] = cfg.get(section_name, 'path')
      self.obs_info[section_name]['lat_north'] = float(cfg.get(section_name, 'lat_north'))
      self.obs_info[section_name]['lat_south'] = float(cfg.get(section_name, 'lat_south'))
      self.obs_info[section_name]['lon_west'] = float(cfg.get(section_name, 'lon_west'))
      self.obs_info[section_name]['lon_east'] = float(cfg.get(section_name, 'lon_east'))
      self.obs_info[section_name]['reso_lat'] = float(cfg.get(section_name, 'reso_lat'))
      self.obs_info[section_name]['reso_lon'] = float(cfg.get(section_name, 'reso_lon'))
    except Exception as err:
      print('read obs infos except:%s' % str(err))
      sys.exit()

  #多线程读实况数据

  # ?????NetCDF?????data0(member, level, time, dtime, lat, lon)
  def dRObs_Nc(self, sIn_abs_path, sVar_name=None, select_lat=None, select_lon=None, is_data_info=False):
    if nc is None:
      raise ImportError("netCDF4 is required to read nc data")
    if not os.path.exists(sIn_abs_path):
      if self.iDebug >= 1: print("No:" + sIn_abs_path)
      empty = np.array([])
      return (empty, {}) if is_data_info else empty
    try:
      with nc.Dataset(sIn_abs_path) as ds:
        lat_name = "lat" if "lat" in ds.variables else "latitude"
        lon_name = "lon" if "lon" in ds.variables else "longitude"
        lat = np.array(ds.variables[lat_name][:], dtype="float32")
        lon = np.array(ds.variables[lon_name][:], dtype="float32")
        var_name = sVar_name if sVar_name in ds.variables else "data0"
        if var_name not in ds.variables:
          data_vars = [k for k, v in ds.variables.items() if len(getattr(v, "dimensions", ())) >= 2]
          if not data_vars:
            raise KeyError("No 2D data variable found in " + sIn_abs_path)
          var_name = data_vars[-1]
        data = np.array(ds.variables[var_name][...], dtype="float32").squeeze()
        while data.ndim > 2:
          data = data[0]
        if data.ndim != 2:
          raise ValueError(f"{sIn_abs_path}: expected 2D data after squeeze, got shape {data.shape}")
        lat_idx = np.arange(lat.size)
        lon_idx = np.arange(lon.size)
        if select_lat is not None:
          lat_min, lat_max = min(select_lat), max(select_lat)
          lat_idx = np.where((lat >= lat_min - 1e-6) & (lat <= lat_max + 1e-6))[0]
        if select_lon is not None:
          lon_min, lon_max = min(select_lon), max(select_lon)
          lon_idx = np.where((lon >= lon_min - 1e-6) & (lon <= lon_max + 1e-6))[0]
        data = data[np.ix_(lat_idx, lon_idx)]
        lat_sel = lat[lat_idx]
        lon_sel = lon[lon_idx]
        data_info = {
          "begin_lon": float(lon_sel[0]), "end_lon": float(lon_sel[-1]),
          "begin_lat": float(lat_sel[0]), "end_lat": float(lat_sel[-1]),
          "lon_res": float(abs(lon_sel[1] - lon_sel[0])) if lon_sel.size > 1 else 0.0,
          "lat_res": float(abs(lat_sel[1] - lat_sel[0])) if lat_sel.size > 1 else 0.0,
          "Nlon": int(lon_sel.size), "Nlat": int(lat_sel.size),
          "ndy1d_x_lon": lon_sel, "ndy1d_y_lat": lat_sel,
          "tpshape_lonlat": data.shape,
        }
      return (data, data_info) if is_data_info else data
    except Exception as e:
      print("Error:" + sIn_abs_path)
      print(e)
      empty = np.array([])
      return (empty, {}) if is_data_info else empty

  def dmulti_read_site_obs(self,args):
     return self.dread_site_obs(*args)
  #读取1个要素1年中的多个站点和日期的实况数据
  def dread_site_obs(self, sIn_abs_path, ltgsite_code, ltYG_dayth, lttime_index=None):
    '''
      ltYG_dayth: 年日的序号-1，对于h5文件内部需要在真实日序上-1
    '''
    in_sites=len(ltgsite_code)
    in_days =len(ltYG_dayth)
    df_relt=pd.DataFrame(np.zeros((in_days,in_sites), dtype=np.float32)+np.nan, columns=ltgsite_code)
    #观测文件存在
    if os.path.exists(sIn_abs_path):
      with h5py.File(sIn_abs_path,'r') as fh:
        ltexist_site=list(fh.keys())
        for scode in ltgsite_code:
          if(scode in ltexist_site):
            df_relt[scode] = fh[scode][()][ltYG_dayth] #
    if lttime_index is not None:
      df_relt.index = lttime_index
    return df_relt
  
  
  #多线程读实况数据
  def dmulti_read_site_wind(self,args):
     return self.dread_site_wind(*args)
  #读取1个要素1年中的多个站点和日期的风数据
  def dread_site_wind(self, sIn_abs_path, ltgsite_code, ltYG_dayth, lttime_index=None):
    in_sites=len(ltgsite_code)
    in_days =len(ltYG_dayth)
    df_WD=pd.DataFrame(np.zeros((in_days,in_sites), dtype=np.float32)+np.nan, columns=ltgsite_code)
    df_WS=pd.DataFrame(np.zeros((in_days,in_sites), dtype=np.float32)+np.nan, columns=ltgsite_code)
    #观测文件存在
    if os.path.exists(sIn_abs_path):
      with h5py.File(sIn_abs_path,'r') as fh:
        ltexist_site=list(fh.keys())
        for scode in ltgsite_code:
          if(scode in ltexist_site):
            df_WD[scode] = fh[scode][()][ltYG_dayth][:,0]
            df_WS[scode] = fh[scode][()][ltYG_dayth][:,1]
    if lttime_index is not None:
      df_WD.index = lttime_index
      df_WS.index = lttime_index
    return [df_WD,df_WS]
    
  #读1个时效所有站点一个文件的实况站点标量观测数据
  def dRsite_obs(self, sIn_abs_path, ltgsite_code, ltindex=['val']):
    in_sites=len(ltgsite_code)
    dfrelt=pd.DataFrame(np.zeros((1,in_sites), dtype=np.float32)+np.nan, index=ltindex, columns=ltgsite_code)
    if os.path.exists(sIn_abs_path):
      #观测文件存在
      with h5py.File(sIn_abs_path,'r') as fh:
        ltexist_site=list(fh.keys())
        data=np.array([fh[scode][()] if(scode in ltexist_site) else np.nan for scode in ltgsite_code])
        dfrelt.loc[ltindex[0],ltgsite_code] = data
    return dfrelt.T
  
  #并行读取标量实况文件
  def dmulti_RObs_site_scalar(self,args):
     return self.dRObs_site_scalar(*args)
  def dRObs_site_scalar(self, sYMDH, dyVar, dyPQ_QC, dyPQ_round):
    sPQ_short_name=dyVar["sPQ_short_name"]
    #站点实况文件名
    sIn_sub_path   = os.path.join(dyVar["sobs_site_main_Path"], sYMDH[0:4], dyVar["sPQ_name"], dyVar["sPQ_type_Obs"], sYMDH[0:8])
    sobs_file_name = sYMDH+"00"+dyVar["suffix"]
    sIn_abs_path   = os.path.join(sIn_sub_path, sobs_file_name)
    #存在
    if(dyVar["debug"]>=2):print("sobs:"+sIn_abs_path)
    dfobs_site=self.dRsite_obs(sIn_abs_path, dyVar["ltSlt_Site_Code"], ltindex=[sPQ_short_name]) #(1行 多列站点) 缺损-32766.0
    if os.path.exists(sIn_abs_path):
      dfobs_site[sPQ_short_name] = dfobs_site[sPQ_short_name].round(decimals=dyPQ_round[sPQ_short_name])
      dfobs_site[(dfobs_site[sPQ_short_name]<=dyPQ_QC[sPQ_short_name][0]) | (dfobs_site[sPQ_short_name]>=dyPQ_QC[sPQ_short_name][1])] = np.nan
    return dfobs_site

  #读1个时效所有站点一个文件的实况站点标量观测数据
  def dRsite_obs_wind(self, sIn_abs_path, ltgsite_code, ltindex=["WD","WS"]):
    in_sites=len(ltgsite_code)
    dfrelt=pd.DataFrame(np.zeros((2,in_sites), dtype=np.float32)+np.nan, index=ltindex, columns=ltgsite_code)
    if os.path.exists(sIn_abs_path):
      #观测文件存在
      with h5py.File(sIn_abs_path,'r') as fh:
        ltexist_site=list(fh.keys())
        data=np.array([[fh[scode][()][0],fh[scode][()][1]] if(scode in ltexist_site) else [np.nan,np.nan] for scode in ltgsite_code])
        dfrelt.loc[ltindex[0],ltgsite_code]=data[:,0]
        dfrelt.loc[ltindex[1],ltgsite_code]=data[:,1]
    return dfrelt.T

  #并行读取矢量实况文件
  def dmulti_RObs_site_wind(self,args):
     return self.dRObs_site_wind(*args)
  def dRObs_site_wind(self, sYMDH, dyVar, dyPQ_QC, dyPQ_round):
    sPQ_short_name=dyVar["sPQ_short_name"]
    #站点实况文件名
    sIn_sub_path   = os.path.join(dyVar["sobs_site_main_Path"], sYMDH[0:4], dyVar["sPQ_name"], dyVar["sPQ_type_Obs"], sYMDH[0:8])
    sobs_file_name = sYMDH+"00"+dyVar["suffix"]
    sIn_abs_path = os.path.join(sIn_sub_path, sobs_file_name)
    if(dyVar["debug"]>=2):print("sobs:"+sIn_abs_path)
    dfobs_site=self.dRsite_obs_wind(sIn_abs_path, dyVar["ltSlt_Site_Code"], ltindex=["WD", sPQ_short_name])
    #存在
    if os.path.exists(sIn_abs_path):
      dfobs_site[(dfobs_site[sPQ_short_name]<=dyPQ_QC[sPQ_short_name][0]) | (dfobs_site[sPQ_short_name]>=dyPQ_QC[sPQ_short_name][1])] = np.nan
      dfobs_site.loc[dfobs_site["WD"]==dyVar["fcalm_wd"],"WD"] = 0 #静风处理
      ndyU,ndyV = self.cls_myfun.dWind_to_UV(dfobs_site["WD"].values, dfobs_site[sPQ_short_name].values) #风向风速转为uv风
      dfobs_site["10u"]  = np.around(ndyU, decimals=dyPQ_round["10u"])
      dfobs_site["10v"]  = np.around(ndyV, decimals=dyPQ_round["10v"])
      dfobs_site=dfobs_site.round(decimals=dyPQ_round[sPQ_short_name])
    return dfobs_site


  #S3预报时间转换为观测时间(目前只有日变的)
  def dS3date_to_Obs(self, sPQ_type, ltdtS3_dates, ibegin_hour, ibegin_fhour, iend_fhour, suffix=".h5"):
    if(sPQ_type.lower()[0:3]=="day"):
      ihour_diff = iend_fhour - ibegin_fhour
      ltobsdate=[(dtS3_dates + datetime.timedelta(hours=ibegin_hour) + datetime.timedelta(hours=iend_fhour)).strftime('%Y%m%d') \
                 for dtS3_dates in ltdtS3_dates]
      sobs_begin_date=(ltdtS3_dates[0] + datetime.timedelta(hours=ibegin_hour) + datetime.timedelta(hours=ibegin_fhour)).strftime('%Y%m%d%H')
      sobs_end_date=(ltdtS3_dates[0] + datetime.timedelta(hours=ibegin_hour) + datetime.timedelta(hours=iend_fhour)).strftime('%Y%m%d%H')
      #实况文件名
      sobs_file_name=f"{ihour_diff:02d}_{sobs_begin_date[-2:]}_{sobs_end_date[-2:]}"+suffix
    else:
      pass
    return ltobsdate, sobs_file_name
  
  
  #获取实况的文件名和日期
  def dObs_date_file(self, sPQ_type, sbegin_date, send_date, ibegin_hour, ibegin_fhour, iend_fhour, if_period, 
                           hour_offset=0, day_offset=0, suffix=".h5"):
    #读实况数据的日期计算
    iBegin_Year, iBegin_Month, iBegin_Day, \
    iEnd_Year  , iEnd_Month  , iEnd_Day = self.cls_myfun.ddate_split_2(sbegin_date, send_date)
    #每个建模实况样本的开始结束日期/文件名
    #逐日
    if(sPQ_type.lower()[0:3]=="day"):
      #检查日变解释时效
      idiff_hour = iend_fhour-ibegin_fhour
      if(idiff_hour!=24):
        print("forecast hour error:",ibegin_fhour,iend_fhour)
        print("Module_Obs_DataBase:dObs_date_file")
        sys.exit()
      #预报未来几天的预报, 业务运行的话 需要推迟12h
      ifrst_day,rema = divmod(iend_fhour,24)     
      if(rema!=0):# 如果是12-36,36-60,60-84,84-108,108-132,132-156,156-180,180-204,204-228,228-252
        itype=2
        ifrst_day,rema = divmod(iend_fhour-12,24)
        if(rema==0):
          ibegin_hour = ibegin_hour + 12
          if ibegin_hour>24: #20点
            ibegin_hour=ibegin_hour-24
            ifrst_day=ifrst_day+1
        else:
          print("forecast hour error:",iend_fhour)
          print("Module_Obs_DataBase:dObs_date_file")
          sys.exit()
      else:
        itype=1
      ifrst_day = ifrst_day + day_offset
      sBegin_mdate_obs = self.cls_myfun.dBefAftDate(iBegin_Year, iBegin_Month, iBegin_Day,0,"Day", ifrst_day)
      sEnd_mdate_obs   = self.cls_myfun.dBefAftDate(iEnd_Year  , iEnd_Month  , iEnd_Day  ,0,"Day", ifrst_day)
      sobs_file_name   = self.dobs_file_name(ibegin_hour, ibegin_fhour, iend_fhour, sday_hour="day", suffix=suffix)
    #逐时
    else:
      ibegin_fhour     = ibegin_fhour+hour_offset
      iend_fhour       = iend_fhour+hour_offset
      sBegin_mdate_obs = self.cls_myfun.dBefAftDate(iBegin_Year, iBegin_Month, iBegin_Day, ibegin_hour,"hour",iend_fhour)
      sEnd_mdate_obs   = self.cls_myfun.dBefAftDate(iEnd_Year  , iEnd_Month  , iEnd_Day  ,ibegin_hour,"hour",iend_fhour)
      sobs_file_name   = self.dobs_file_name(ibegin_hour, ibegin_fhour, iend_fhour, sday_hour="hour", suffix=suffix)     #实况文件名
    #每个建模样本实况日期
    ltdates_obs = self.cls_myfun.ddates_between_two_date(sBegin_mdate_obs, sEnd_mdate_obs, if_period)
    return  ltdates_obs, sobs_file_name

  #实况文件名
  def dobs_file_name(self, iBegin_hour, iBegin_fhour, iEnd_fhour, sday_hour="day", suffix=".h5"):
    """
    iBegin_hour  : 开始时间
    iBegin_fhour : 预报开始时效
    iEnd_fhour   : 预报结束时效
    """
    #逐日
    if sday_hour.lower()=="day":
      sobs_fname = "_".join(["%02d"%(iEnd_fhour-iBegin_fhour),"%02d"%iBegin_hour,"%02d"%iBegin_hour])+suffix
    #时间段
    elif sday_hour.lower()=="span":
      sobs_fname = "_".join(["%02d"%(iEnd_fhour-iBegin_fhour),"%02d"%iBegin_fhour,"%02d"%iEnd_fhour])+suffix
    #逐时
    else:
      #实况文件名(时效)
      ifrst_day,iobs_fname_begin_hour = divmod(iBegin_hour+iBegin_fhour,24)
      sobs_fname_begin_hour="%02d"%iobs_fname_begin_hour
      ifrst_day,iobs_fname_end_hour   = divmod(iBegin_hour+iEnd_fhour,24)
      sobs_fname_end_hour="%02d"%iobs_fname_end_hour
      if iobs_fname_begin_hour==23 and iobs_fname_end_hour==0:
        sobs_fname_end_hour="24"
      #文件名中的插值
      diff=iEnd_fhour-iBegin_fhour
      if diff<0:  #跨天区间(03_23_02.h5)
        diff=24+diff
      sobs_fname_diff_hour="%02d"%diff
      #实况文件名
      sobs_fname="_".join([sobs_fname_diff_hour,sobs_fname_begin_hour,sobs_fname_end_hour])+suffix
    return sobs_fname
    
  #模式预报时间对应的实况时间（多个时间）
  def dmdl_vs_Obs_YMDHs(self, sbegin_YMD, send_YMD, sbegin_HH, sbegin_fHH):
    ltdates_obs = self.cls_myfun.ddates_between_two_date(sbegin_YMD, send_YMD, 0)
    return [self.dmdl_vs_Obs_YMDH(sYMD, sbegin_HH, sbegin_fHH) for sYMD in ltdates_obs]
  
  #模式预报时间对应的实况时间（1个时间）
  def dmdl_vs_Obs_YMDH(self, sbegin_YMD, sbegin_HH, sbegin_fHH):
    sbegin_YMDH = sbegin_YMD + sbegin_HH
    return self.cls_myfun.dBefAftDate2(sbegin_YMDH,"hour",int(sbegin_fHH))
  
  #逐时时刻日期
  def dPrecip_mdl_date(self, ltS3_Date, ibegin_hour, ltPdr_1S_FHours, suffix=".h5"):
    """
    ltS3_Date         : S3步的预报开始日期列表
    ibegin_hour       : 预报时效
    ltPdr_1S_FHours   : 预报时效区间[[0,3],[3,6]]
    """
    ltdate_mdl = []
    for sS3_dates in ltS3_Date:
      iBegin_Year  = int(sS3_dates[0:4])
      iBegin_Month = int(sS3_dates[4:6])
      iBegin_Day   = int(sS3_dates[6:])
      for ltfh in ltPdr_1S_FHours:
        smdate_obs_begin = self.cls_myfun.dBefAftDate(iBegin_Year, iBegin_Month, iBegin_Day, ibegin_hour,"hour",ltfh[0])
        smdate_obs_end   = self.cls_myfun.dBefAftDate(iBegin_Year, iBegin_Month, iBegin_Day, ibegin_hour,"hour",ltfh[1])
        idayth=datetime.datetime.strptime(smdate_obs_end,"%Y%m%d%H").timetuple()[7]-1  #hdf5文件格式
        diff=ltfh[1]-ltfh[0]
        if diff<0: diff=24+diff  #跨天区间(03_23_02.h5)
        sobs_fname_diff_hour="%02d"%diff
        sS3_Fdates="_".join([sS3_dates,f"{ibegin_hour:02d}",f"{ltfh[0]:03d}",f"{ltfh[1]:03d}"])
        #实况文件名
        sobs_fname="_".join([sobs_fname_diff_hour,smdate_obs_begin[8:],smdate_obs_end[8:]])+suffix
        ltdate_mdl.append([smdate_obs_begin, smdate_obs_end, sobs_fname, idayth, sS3_Fdates])
    return ltdate_mdl
    

  #逐时时刻日期
  def dOPrecip_date2(self, begin_date, end_date, begin_hour, begin_fhour, end_fhour, if_period=0, step_hour=1):
    #读实况数据的日期计算
    iBegin_Year, iBegin_Month, iBegin_Day, \
    iEnd_Year  , iEnd_Month  , iEnd_Day = self.cls_myfun.ddate_split_2(begin_date, end_date)
    ibegin_fhour = begin_fhour
    iend_fhour   = end_fhour
    sBegin_mdate_obs = self.cls_myfun.dBefAftDate(iBegin_Year, iBegin_Month, iBegin_Day, begin_hour,"hour",ibegin_fhour)
    sEnd_mdate_obs   = self.cls_myfun.dBefAftDate(iEnd_Year  , iEnd_Month  , iEnd_Day  ,begin_hour,"hour",iend_fhour)
    #两个日期之间的所有时间
    ltdates_obs=self.cls_myfun.ddateHours_in_2DH(sBegin_mdate_obs, sEnd_mdate_obs, if_period=if_period, step_hour=step_hour)
    return ltdates_obs
    
  #读取格点实况
  def dmulti_RObs_Grid(self,args):
     return self.dRObs_Grid(*args)
  def dRObs_Grid(self, sIn_abs_path):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        grbs = pygrib.open(sIn_abs_path)
        data=np.round(np.ma.getdata(grbs[1].values),2)
        grbs.close()
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        data= np.array([])
    else:
      data= np.array([])
    return data
    
  #读取格点实况
  def dmulti_RObs_Grid_Wind(self,args):
     return self.dRObs_Grid_Wind(*args)
  def dRObs_Grid_Wind(self, sIn_abs_path):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        grbs = pygrib.open(sIn_abs_path)
        if grbs[1].shortName=="10u":
          data1 = np.round(np.ma.getdata(grbs[1].values) ,1)
        if grbs[2].shortName=="10v":
          data2 = np.round(np.ma.getdata(grbs[2].values) ,1)
        grbs.close()
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        data1 = np.array([])
        data2 = np.array([])
    else:
      data1 = np.array([])
      data2 = np.array([])
    return [data1,data2]
  
  #根据parameterNumber获取数据
  def dRObs_Grid_Wind2(self, sIn_abs_path):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        grbs = pygrib.open(sIn_abs_path)
        if grbs[1].parameterNumber==102: #u
          data1 = np.round(np.ma.getdata(grbs[1].values),1)
        if grbs[2].parameterNumber==103: #v
          data2 = np.round(np.ma.getdata(grbs[2].values),1)
        grbs.close()
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        data1 = np.array([])
        data2 = np.array([])
    else:
      data1 = np.array([])
      data2 = np.array([])
    return [data1,data2]

  #读取风场返回字典
  def dRObs_Grid_UV(self, sIn_abs_path):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        grbs = pygrib.open(sIn_abs_path)
        if grbs[1].parameterNumber==102: #u
          data1 = np.round(np.ma.getdata(grbs[1].values),1)
        if grbs[2].parameterNumber==103: #v
          data2 = np.round(np.ma.getdata(grbs[2].values),1)
        grbs.close()
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        data1 = np.array([])
        data2 = np.array([])
    else:
      data1 = np.array([])
      data2 = np.array([])
    return {"10u":data1,"10v":data2}



  def dObs_Grid_Extract(self, sIn_Abs_Path, sOut_Abs_Path, ltArea, ldel_raw=False, changeDecimalPrecision=None):
    """
      sIn_Abs_Path     输入路径
      sOut_Abs_Path    输出路径
      ltArea           截取区域 
      ldel_raw=False   是否删除原始
    """
    #输入文件存在
    if os.path.exists(sIn_Abs_Path):
      #打开grib数据文件进行读取预测数据
      temp_path = sOut_Abs_Path+".tmp"
      if os.path.exists(temp_path):
        os.remove(temp_path)
      try:
        grbout = open(temp_path,'wb')
        grbs = pygrib.open(sIn_Abs_Path)
        for grb in grbs:
          subdata, lats, lons = grb.data(lat1=ltArea[0]-0.001,lat2=ltArea[1]+0.001, \
                                         lon1=ltArea[2]-0.001,lon2=ltArea[3]+0.001)
          #修改经度
          grb['longitudeOfFirstGridPointInDegrees'] = lons[0,0]
          grb['longitudeOfLastGridPointInDegrees']  = lons[-1,-1]
          #修改纬度
          grb['latitudeOfFirstGridPointInDegrees']  = lats[0,0]
          grb['latitudeOfLastGridPointInDegrees']   = lats[-1,-1]
          #修改格点数
          grb['Nj']                                 = lons.shape[0]
          grb['Ni']                                 = lons.shape[1]
          #改变精度
          if changeDecimalPrecision!=None:
            grb["changeDecimalPrecision"]           = changeDecimalPrecision
          #修改数值
          grb['values']                             = subdata
          #写入新文件
          grbout.write(grb.tostring())
        grbs.close()
        grbout.close()
        fsize = os.path.getsize(temp_path)  #获取新数据大小(bytes)
        #删除错误文件
        if fsize==0.0:
          os.remove(temp_path)
        else:
          #重命名
          os.rename(temp_path, sOut_Abs_Path)
      except:
        print("error:grib",sIn_Abs_Path)
        sys.exit()
      # #删除原始数据
      # if ldel_raw==True:
        # try:
          # os.remove(sIn_Abs_Path)
        # except OSError as e: # name the Exception `e`
          # print("Failed with:", e.strerror) # look what it says
          # print("Error code:", e.code)
    else:
      print("No:"+sIn_Abs_Path)
    return
  
  #读取观测数据
  def dread_obs_grid(self, sIn_Abs_Path):
    grbs = pygrib.open(sIn_Abs_Path)
    data=grbs[1]['values']
    grbs.close()
    return data
    
  #观测降水累加
  def dObs_Rain_Accu(self, ltfiles_path, sOut_Abs_Path, sYMDH, default=9999.0):

    #输出临时文件存在
    temp_path = sOut_Abs_Path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    ndysum=0
    for i,sin_abs_path in enumerate(ltfiles_path):
      ndy_data=self.dread_obs_grid(sin_abs_path)
      ndy_data[ndy_data>=default]=np.nan
      ndysum=ndysum+ndy_data
    ndysum[np.isnan(ndysum)]=default
    ndysum=np.float32(ndysum)
    #写入新的grib
    try:    
      grbs = pygrib.open(ltfiles_path[0])
      grb=grbs[1]
      grbs.close()
      #修改日期
      grb.year=int(sYMDH[0:4])
      grb.month=int(sYMDH[4:6])
      grb.day=int(sYMDH[6:8])
      grb.hour=int(sYMDH[8:10])
      #修改值
      grb['values']=ndysum
      #写入
      grbout = open(temp_path,'wb')
      grbout.write(grb.tostring())
      grbout.close()
      fsize = os.path.getsize(temp_path)  #获取新数据大小(bytes)
      #删除错误文件
      if fsize==0.0:
        os.remove(temp_path)
      else:
        os.rename(temp_path, sOut_Abs_Path)  #重命名
    except:
      print("error:grib",sOut_Abs_Path)
    return
  
  
