#!/usr/bin/python
# -*- coding: utf-8 -*-
import configparser
import datetime
import os
import sys


class Class_Get_Sorce_Path(object):

  "初始化函数"
  def __init__(self, iDebug = 0):
    self.iDebug = iDebug
    self.dydirpathInfo = {}
    self.ltSPQ_shortname = ['sp'] # 地面单层要素
    self.ltMPQ_shortname = ['gh'] # 高空多层要素
    self.ltObs_shortname = ['2t', '2rh', '10ws', '10u', '10v'] # 实况要素

    # 路径配置信息
  def dRead_Mdl_Obs_path_ini(self, sIn_sub_path, subpath="Parameter", sfile_name="Mdl_Obs_Path_Info.ini", shortname=None):
    sdir_path = os.path.join(sIn_sub_path, subpath, sfile_name)
    if os.path.exists(sdir_path):
      self.dydirpathInfo = {"ModelPathInfo": {}, "ObsPathInfo": {}, "ElementDirGround": {}, "ElementDirHigh": {}, "levels":{}}
      config = configparser.ConfigParser()
      config.read(sdir_path, encoding='UTF-8')
      # 读取模式路径信息
      self.dydirpathInfo["ModelPathInfo"]["basepath"]      = config.get('ModelPathInfo', "basepath")
      self.dydirpathInfo["ModelPathInfo"]["GRAPES_12P5KM"] = config.get('ModelPathInfo', "GRAPES_12P5KM")
      self.dydirpathInfo["ModelPathInfo"]["GRAPES_25KM"]   = config.get('ModelPathInfo', "GRAPES_25KM")
      self.dydirpathInfo["ModelPathInfo"]["GRAPES_3KM"]    = config.get('ModelPathInfo', "GRAPES_3KM")
      self.dydirpathInfo["ModelPathInfo"]["GRAPES_MESO"]   = config.get('ModelPathInfo', "GRAPES_MESO")
      self.dydirpathInfo["ModelPathInfo"]["GRAPES_GFS"]    = config.get('ModelPathInfo', "GRAPES_GFS")
      self.dydirpathInfo["ModelPathInfo"]["CMA_MESO"]      = config.get('ModelPathInfo', "CMA_MESO")
      self.dydirpathInfo["ModelPathInfo"]["CMA_GFS"]       = config.get('ModelPathInfo', "CMA_GFS")
      self.dydirpathInfo["ModelPathInfo"]["EC_12P5KM"]     = config.get('ModelPathInfo', "EC_12P5KM")
      self.dydirpathInfo["ModelPathInfo"]["timezone"]      = config.get('ModelPathInfo', "timezone")  # 文件存储路径时区
      self.dydirpathInfo["ModelPathInfo"]["file_timezone"] = config.get('ModelPathInfo', "file_timezone")  # 文件存储路径时区
      # 读取实况路径信息
      self.dydirpathInfo["ObsPathInfo"]["basepath"]      = config.get('ObsPathInfo', "basepath")
      self.dydirpathInfo["ObsPathInfo"]["Grid_5km"]      = config.get('ObsPathInfo', "Grid_5km")
      self.dydirpathInfo["ObsPathInfo"]["Grid_1km"]      = config.get('ObsPathInfo', "Grid_1km")
      self.dydirpathInfo["ObsPathInfo"]["timezone"]      = config.get('ObsPathInfo', "timezone")
      self.dydirpathInfo["ObsPathInfo"]["file_timezone"] = config.get('ObsPathInfo', "file_timezone")
      # 实况传入了需要的固定要素
      # if shortname:
      #   if shortname in ['10u', '10v']:
      #     self.dydirpathInfo["ElementDirGround"]['10u'] = config.get('ElementDirGround', '10u')
      #     self.dydirpathInfo["ElementDirGround"]['10v'] = config.get('ElementDirGround', '10v')
      #     self.Obs_shortname = ['10u', '10v']
      #   else:
      #     self.dydirpathInfo["ElementDirGround"][shortname] = config.get('ElementDirGround', shortname)
      #     self.Obs_shortname = [shortname]
      # else:
      ltSPQ_shortname_copy = self.ltSPQ_shortname.copy()
      if ['10ws'] in self.ltSPQ_shortname:
        ltSPQ_shortname_copy = ltSPQ_shortname_copy + ['10u', '10v']
      print(f"eles:{self.ltSPQ_shortname}, {self.ltMPQ_shortname}, {self.ltObs_shortname}")
      if self.ltSPQ_shortname:
        for sPQ in ltSPQ_shortname_copy:
          try:
            self.dydirpathInfo["ElementDirGround"][sPQ] = config.get('ElementDirGround', sPQ)
          except Exception as e:
            # 删除未配置路径的地面要素
            self.ltSPQ_shortname.remove(sPQ)
            print(f'{sfile_name}:', e)
            continue
      ltMPQ_shortname_copy = self.ltMPQ_shortname.copy()
      if self.ltMPQ_shortname:
        for sPQ in ltMPQ_shortname_copy:
          try:
            self.dydirpathInfo["ElementDirHigh"][sPQ] = config.get('ElementDirHigh', sPQ)
          except Exception as e:
            # 删除未配置路径的高空要素
            self.ltMPQ_shortname.remove(sPQ)
            print(f'{sfile_name}:', e)
            continue
      ltObs_shortname_copy = self.ltObs_shortname.copy()
      if self.ltObs_shortname:
        for sPQ in ltObs_shortname_copy:
          try:
            self.dydirpathInfo["ElementDirGround"][sPQ] = config.get('ElementDirGround', sPQ)
          except Exception as e:
            # 删除未配置路径的实况要素
            self.ltObs_shortname.remove(sPQ)
            print(f'{sfile_name}:', e)
            continue
      # self.dydirpathInfo["ElementDirGround"]["timezone"] = config.get('ElementDirGround', "timezone")
      # self.dydirpathInfo["ElementDirHigh"]["timezone"]   = config.get('ElementDirHigh', "timezone")
      # 模式预报高度层层数
      self.dydirpathInfo["levels"]["EC_12P5KM"]     = config.get('levels', "EC_12P5KM").split(',')
      self.dydirpathInfo["levels"]["GRAPES_12P5KM"] = config.get('levels', "GRAPES_12P5KM").split(',')

      self.dydirpathInfo["debug_info"] = config.get('debug_info', "info")

    else:
      print("No:" + sdir_path)
      sys.exit()

  # 添加高低空要素名
  def get_ltsPQ_ltMPQ_shortname(self, ltPQSN_Intp, ltPQSN_mxmn, sModel_Region_upper):
    # 读取grib的地面和3D数据文件
    if sModel_Region_upper in ["EC_12P5KM"]:
      if "2t" in ltPQSN_Intp:
        self.ltSPQ_shortname.append("2t")
      if "2rh" in ltPQSN_Intp:
        if "2t" in self.ltSPQ_shortname:
          self.ltSPQ_shortname = self.ltSPQ_shortname + ["2d"]
        else:
          self.ltSPQ_shortname = self.ltSPQ_shortname + ["2d", "2t"]
      if "10ws" in ltPQSN_Intp:
        self.ltSPQ_shortname = self.ltSPQ_shortname + ["10u", "10v"]
      if '2t_max' in ltPQSN_mxmn:
        self.ltSPQ_shortname.append("mx2t3")
      if '2t_min' in ltPQSN_mxmn:
        self.ltSPQ_shortname.append("mn2t3")
      if '10gust' in ltPQSN_Intp:
        self.ltSPQ_shortname.append("10fg3")
      if 'tcc' in ltPQSN_Intp:
        self.ltSPQ_shortname.append("tcc")
    elif sModel_Region_upper in ["GRAPES_12P5KM", "GRAPES_25KM", "GRAPES_GFS", "CMA_GFS"]:  # 0.0625-60.0625,
      if "2t" in ltPQSN_Intp:
        self.ltSPQ_shortname.append("2t")
      if '2t_max' in ltPQSN_mxmn:
        self.ltSPQ_shortname.append("tmax")
      if '2t_min' in ltPQSN_mxmn:
        self.ltSPQ_shortname.append("tmin")
      if "2rh" in ltPQSN_Intp:
        self.ltSPQ_shortname = self.ltSPQ_shortname + ["2r"]
      if "2rh_max" in ltPQSN_mxmn:
        self.ltSPQ_shortname = self.ltSPQ_shortname + ["2rh_max"]
      if "2rh_min" in ltPQSN_mxmn:
        self.ltSPQ_shortname = self.ltSPQ_shortname + ["2rh_min"]
      if "10ws" in ltPQSN_Intp:
        self.ltSPQ_shortname = self.ltSPQ_shortname + ["10u", "10v"]
      if '10gust' in ltPQSN_Intp:
        self.ltSPQ_shortname.append("gust")
      if 'tcc' in ltPQSN_Intp:
        self.ltSPQ_shortname.append("tcc")
    elif sModel_Region_upper in ["GRAPES_3KM", "GRAPES_MESO", "CMA_MESO"]:
      if "2t" in ltPQSN_Intp:
        self.ltSPQ_shortname.append("2t")
      if "2rh" in ltPQSN_Intp:
        self.ltSPQ_shortname = self.ltSPQ_shortname + ["2r"]
      if "10ws" in ltPQSN_Intp:
        self.ltSPQ_shortname = self.ltSPQ_shortname + ["10u", "10v"]
      if '10gust' in ltPQSN_Intp:
        self.ltSPQ_shortname.append("gust")
      if 'tcc' in ltPQSN_Intp:
        self.ltSPQ_shortname.append("tcc")

    # 添加高空要素
    if "2t" in self.ltSPQ_shortname:  # 单层: 2m气温
      self.ltMPQ_shortname = self.ltMPQ_shortname + ["t"]  # 多层: 气压层气温
    if ("2d" in self.ltSPQ_shortname) or ("2r" in self.ltSPQ_shortname):  # 单层: 2m露点(EC需根据2d和2t计算2rh)/2m相对湿度(grapes直接有2r=2rh)
      self.ltMPQ_shortname = self.ltMPQ_shortname + ["r"]  # 多层: 气压层相对湿度
    if ("10u" in self.ltSPQ_shortname) or ("10v" in self.ltSPQ_shortname):  # 单层: 10m-u/v风
      self.ltMPQ_shortname = self.ltMPQ_shortname + ["u", "v"]  # 多层: 气压层风

  # 实况文件路径拼接
  def obs_path(self, sInterp_YMDH_dt, sReso_dir, shortname, sTime_range='000'):
    """
    :param sInterp_YMDH_dt: 文件时间YYYYMMDDHH 10位，北京时
    :param sReso_dir: 实况模式名
    :param shortname: 要素简写
    :param sTime_range:时效
    ruturn 数据文件路径字典，文件是否存在
    """
    # logging.info("开始拼接实况文件路径")
    sInterp_YMDH_dt = self.to_datetime_type(sInterp_YMDH_dt)
    sIn_obs_abs_paths = {}
    if self.dydirpathInfo["ObsPathInfo"]["timezone"] in ["UTC"]:
      sInterp_YMDH_dt_utc = sInterp_YMDH_dt - datetime.timedelta(hours=8)
    else:
      sInterp_YMDH_dt_utc = sInterp_YMDH_dt
    # for shortname in self.ltObs_shortname:
    # 输入格点实况nc数据文件名
    if 'max' in shortname or 'min' in shortname:
      step = 'Daily'
    else:
      step = 'Hourly'
    if self.dydirpathInfo["ObsPathInfo"]["file_timezone"] in ["UTC"]:
      sobs_file_name = sInterp_YMDH_dt_utc.strftime('UTC_%Y%m%d%H') + f".{sTime_range}" + ".nc"
    else:
      sobs_file_name = sInterp_YMDH_dt.strftime('BJT_%Y%m%d%H') + f".{sTime_range}" + ".nc"
    # 矢量数据。
    if shortname in ['10ws']:
      for st in ['10u', '10v']:
        sIn_obs_sub_path = os.path.join(self.dydirpathInfo["ObsPathInfo"]["basepath"],
                                        self.dydirpathInfo["ObsPathInfo"][sReso_dir],
                                        step,
                                        self.dydirpathInfo["ElementDirGround"][st],
                                        sInterp_YMDH_dt_utc.strftime('%Y'),
                                        sInterp_YMDH_dt_utc.strftime('%Y%m%d'))
        sIn_obs_abs_path = os.path.join(sIn_obs_sub_path, sobs_file_name)
        sIn_obs_abs_paths[st] = sIn_obs_abs_path
        lexist = os.path.exists(sIn_obs_abs_path)
    else:
      sIn_obs_sub_path = os.path.join(self.dydirpathInfo["ObsPathInfo"]["basepath"],
                                      self.dydirpathInfo["ObsPathInfo"][sReso_dir],
                                      step,
                                      self.dydirpathInfo["ElementDirGround"][shortname],
                                      sInterp_YMDH_dt_utc.strftime('%Y'),
                                      sInterp_YMDH_dt_utc.strftime('%Y%m%d'))
      sIn_obs_abs_path = os.path.join(sIn_obs_sub_path, sobs_file_name)
      sIn_obs_abs_paths[shortname] = sIn_obs_abs_path
      lexist = os.path.exists(sIn_obs_abs_path)
    if not lexist:
      if self.iDebug >= 1: print(f"File_obs not Exist:{sIn_obs_abs_path}")

    return sIn_obs_abs_paths, lexist

  # 模式nc文件路径拼接
  def mdl_path(self, sInterp_YMDH_dt, sModel_Region_upper, sTime_range='000'):
    """
    :param sInterp_YMDH_dt: 文件时间YYYYMMDDHH 10位，北京时
    :param sModel_Region_upper: 模式名，
    :param sTime_range:时效
    return 数据文件路径字典，不存在的数据文件列表
    """
    # logging.info("开始拼接模式文件路径")
    sInterp_YMDH_dt = self.to_datetime_type(sInterp_YMDH_dt)
    # 要素路径字典
    mdl_paths = {}
    # 要素文件不存在的
    Nexist = []
    # 文件路径时间确认
    if self.dydirpathInfo["ModelPathInfo"]["timezone"] in ["UTC"]:
      sInterp_YMDH_dt_utc = sInterp_YMDH_dt - datetime.timedelta(hours=8)
    else:
      sInterp_YMDH_dt_utc = sInterp_YMDH_dt
    # 地面要素路径
    for shortname in self.ltSPQ_shortname:
      if self.dydirpathInfo["ModelPathInfo"]["file_timezone"] in ["UTC"]:
        if sModel_Region_upper in ['EC_12P5KM', 'GRAPES_12P5KM']:
          sIn_mdl_sub_path = os.path.join(self.dydirpathInfo["ModelPathInfo"]["basepath"],
                                          self.dydirpathInfo["ModelPathInfo"][sModel_Region_upper],
                                          self.dydirpathInfo["ElementDirGround"][shortname],
                                          sInterp_YMDH_dt_utc.strftime('%Y'),
                                          sInterp_YMDH_dt_utc.strftime('%Y%m%d'))
          smdl_file_name = sInterp_YMDH_dt_utc.strftime('%Y%m%d%H') + f".{sTime_range}" + ".nc"
        else:  # 其他模式路径，后续按需改变
          sIn_mdl_sub_path = os.path.join(self.dydirpathInfo["ModelPathInfo"]["basepath"],
                                          self.dydirpathInfo["ModelPathInfo"][sModel_Region_upper],
                                          self.dydirpathInfo["ElementDirGround"][shortname],
                                          sInterp_YMDH_dt_utc.strftime('%Y'),
                                          sInterp_YMDH_dt_utc.strftime('%Y%m%d'))
          smdl_file_name = sInterp_YMDH_dt_utc.strftime('%Y%m%d%H') + f".{sTime_range}" + ".nc"
      else: # 北京时
        if sModel_Region_upper in ['EC_12P5KM', 'GRAPES_12P5KM']:
          sIn_mdl_sub_path = os.path.join(self.dydirpathInfo["ModelPathInfo"]["basepath"],
                                          self.dydirpathInfo["ModelPathInfo"][sModel_Region_upper],
                                          self.dydirpathInfo["ElementDirGround"][shortname],
                                          sInterp_YMDH_dt_utc.strftime('%Y'),
                                          sInterp_YMDH_dt_utc.strftime('%Y%m%d'))
          smdl_file_name = sInterp_YMDH_dt.strftime('%Y%m%d%H') + f".{sTime_range}" + ".nc"
        else:  # 其他模式路径，后续按需改变
          sIn_mdl_sub_path = os.path.join(self.dydirpathInfo["ModelPathInfo"]["basepath"],
                                          self.dydirpathInfo["ModelPathInfo"][sModel_Region_upper],
                                          self.dydirpathInfo["ElementDirGround"][shortname],
                                          sInterp_YMDH_dt_utc.strftime('%Y'),
                                          sInterp_YMDH_dt_utc.strftime('%Y%m%d'))
          smdl_file_name = sInterp_YMDH_dt.strftime('%Y%m%d%H') + f".{sTime_range}" + ".nc"

      sIn_mdl_abs_path = os.path.join(sIn_mdl_sub_path, smdl_file_name)
      if not os.path.exists(sIn_mdl_abs_path):
        Nexist.append(sIn_mdl_abs_path)
      else:
        mdl_paths[shortname] = sIn_mdl_abs_path


    # 高空要素路径
    for shortname in self.ltMPQ_shortname:
      levels = self.dydirpathInfo["levels"][sModel_Region_upper]
      # 高空层次循环
      for level in levels:
        # 输入格点实况nc数据文件名
        if self.dydirpathInfo["ModelPathInfo"]["file_timezone"] in ["UTC"]:
          if sModel_Region_upper in ['EC_12P5KM', 'GRAPES_12P5KM']:
            sIn_mdl_sub_path = os.path.join(self.dydirpathInfo["ModelPathInfo"]["basepath"],
                                            self.dydirpathInfo["ModelPathInfo"][sModel_Region_upper],
                                            self.dydirpathInfo["ElementDirHigh"][shortname],
                                            level,
                                            sInterp_YMDH_dt_utc.strftime('%Y'),
                                            sInterp_YMDH_dt_utc.strftime('%Y%m%d'))
            smdl_file_name = sInterp_YMDH_dt_utc.strftime('%Y%m%d%H') + f".{sTime_range}" + ".nc"
          else: # 其他模式路径，后续按需改变
            sIn_mdl_sub_path = os.path.join(self.dydirpathInfo["ModelPathInfo"]["basepath"],
                                            self.dydirpathInfo["ModelPathInfo"][sModel_Region_upper],
                                            self.dydirpathInfo["ElementDirHigh"][shortname],
                                            level,
                                            sInterp_YMDH_dt_utc.strftime('%Y'),
                                            sInterp_YMDH_dt_utc.strftime('%Y%m%d'))
            smdl_file_name = sInterp_YMDH_dt_utc.strftime('%Y%m%d%H') + f".{sTime_range}" + ".nc"
        else: # 北京时
          if sModel_Region_upper in ['EC_12P5KM', 'GRAPES_12P5KM']:
            sIn_mdl_sub_path = os.path.join(self.dydirpathInfo["ModelPathInfo"]["basepath"],
                                            self.dydirpathInfo["ModelPathInfo"][sModel_Region_upper],
                                            self.dydirpathInfo["ElementDirHigh"][shortname],
                                            level,
                                            sInterp_YMDH_dt_utc.strftime('%Y'),
                                            sInterp_YMDH_dt_utc.strftime('%Y%m%d'))
            smdl_file_name = sInterp_YMDH_dt.strftime('%Y%m%d%H') + f".{sTime_range}" + ".nc"
          else: # 其他模式路径，后续按需改变
            sIn_mdl_sub_path = os.path.join(self.dydirpathInfo["ModelPathInfo"]["basepath"],
                                            self.dydirpathInfo["ModelPathInfo"][sModel_Region_upper],
                                            self.dydirpathInfo["ElementDirHigh"][shortname],
                                            level,
                                            sInterp_YMDH_dt_utc.strftime('%Y'),
                                            sInterp_YMDH_dt_utc.strftime('%Y%m%d'))
            smdl_file_name = sInterp_YMDH_dt.strftime('%Y%m%d%H') + f".{sTime_range}" + ".nc"
        sIn_mdl_abs_path = os.path.join(sIn_mdl_sub_path, smdl_file_name)
        # 要素文件不存在的
        if not os.path.exists(sIn_mdl_abs_path):
          Nexist.append(sIn_mdl_abs_path)
        else:
          # 多层后
          if shortname in mdl_paths:
            mdl_paths[shortname][level] = sIn_mdl_abs_path
          # 第1层
          else:
            mdl_paths[shortname] = {level: sIn_mdl_abs_path}
    if Nexist:
      if self.iDebug >= 1: print(f"File_mdl not Exist:{Nexist}")

    return mdl_paths, Nexist

  def to_datetime_type(self, YMDH):
    if type(YMDH) is datetime.datetime:
      return YMDH
    else:
      if len(YMDH) != 10:
        raise ValueError(F'{YMDH} Format is not YYYYMMDDHH')
      return datetime.datetime.strptime(str(YMDH), "%Y%m%d%H")


if __name__ == '__main__':
  class_path = Class_Get_Sorce_Path()
  class_path.ltSPQ_shortname = ['2t','2rh','t']
  class_path.dRead_Mdl_Obs_path_ini('../../')
