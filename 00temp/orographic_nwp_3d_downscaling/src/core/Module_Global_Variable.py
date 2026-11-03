# -*- coding: utf-8 -*- 
# cython:language_level=3

import os
import sys
import configparser
import numpy as np

# cls_gv.sMDL_TIME_lbl
# cls_gv.sObs_Grid_file
# cls_gv.sys_Para_dir
"4Modeling"

class Class_Global_Variable(object):

  "初始化函数"
  def __init__(self, iDebug = 0):
    self.iDebug         = iDebug
    #读文件的数据缺损信息
    self.RGrid_Default  = -32766.0
    self.RObs_Default   = -32766.0
    self.RScore_Default = -9.999
    #固定信息
    self.Sys_Para_dir   = "Parameter"
    self.sObs_Site_file = "Obs_Site.ini"
    self.sObs_Grid_file = "Obs_Grid.ini"
    self.Sys_MInfo_tail = "Info.ini"
    self.S1_dir         = "1DownLoad_Data"
    self.S3_dir         = "3PreProcess"
    self.S4_dir         = "4Modeling"
    self.S5_dir         = "5Forecast"
    self.S6_dir         = "6Validate"
    self.S4_fix_pdate   = "00000000_00000000"
    self.S4_TMDL_head   = "Tri"
    self.S4_PMDL_head   = "Pdr"
    self.S4_MDL_S3MD    = "S3_METHOD"
    self.S4_MDL_Time    = "MDL_TIME"  #建模结果h5属性中模型日期标签
    self.S5_Frst_Time   = "FORECAST_TIME"
    self.S5_Blend_dir   = "Blending"
    self.imax_run_fhour = 36
    self.lth5_dset      = ["CC", "FIT", "ID", "PMODEL", "PNORM", "RC", "SCORE"]
    self.ltnorm_method  = ["std","max_min"]
    #滚动订正的阈值
    self.dymhour_thd    = {8:[[14,23],[0,1]],20:[2,13]}
    self.bsh_range      = [6,17] #滚动订正亚起报时间(预报时效,eg.20/08模式起报点6h后开始预报)
    self.dt8_oprn       = [8,20] #建模日变[08-20)点启动20点模式预报场的时间 & 监控格点max/min时间
    self.fd20_oprn      = [2,14] #预报日变[2-14)点启动20点模式预报场时间
    #质控
    self.dyPQ_QC        = {"2t":[-60,60],"2rh":[0,100],"10u":[-80,80],"10v":[-80,80],"10ws":[0,80],"10gust":[0,80],"mn2t3":[-60,60],"mx2t3":[-60,60],"tcc":[0,100],\
                           "2t_max":[-60,60], "2t_min":[-60,60], "2rh_max":[0,100], "2rh_min":[0,100], "10ws_max":[0,80], "sp":[200,1100]}
    
  "读Global_Variable.ini" 
  def dRead_Global_Variable_ini(self, sIn_sub_path, sModel_Name):
    sfile_name = "Global_Variable.ini"
    sabs_path  = os.path.join(sIn_sub_path, "Parameter", sModel_Name, sfile_name)
    with open(sabs_path,'r') as fh:
      self.RGrid_Default  = float(fh.readline())   #数值预报数据缺测值
      self.RObs_Default   = float(fh.readline())   #Obs缺测值
      self.RScore_Default = float(fh.readline())   #评分缺测值
  
  #读Global_Info.ini
  def dGlobal_Info(self, sIn_sub_path, sfile_name="Global_Info.ini"):
    spara_abs_path  = os.path.join(sIn_sub_path, self.Sys_Para_dir, sfile_name)
    if os.path.exists(spara_abs_path):
      dyglobalInfo={"Path":{},"Default":{}}
      config = configparser.ConfigParser()
      config.read(spara_abs_path)
      dyglobalInfo["Path"]["result"]    = config.get('Path', "result")              #结果保存信息
      dyglobalInfo["Default"]["obs_site"] = config.getfloat('Default', "obs_site")
      dyglobalInfo["Default"]["mdl_grid"] = config.getfloat('Default', "mdl_grid")
      return dyglobalInfo
    else:
      print("No:"+spara_abs_path)
      sys.exit()

  #当前时间对应的模式起报时间
  def dnowtime_vs_bhours(self,sModel_name_lower,sRegion_lower, Num_BFH=8):
    '''
      sModel_name_lower = 模式名
      sRegion_lower     = 模式类型
      Num_BFH           = 起报次数
    '''
    if sModel_name_lower=="grapes" and sRegion_lower=="meso":
      dynowtime_vs_bhours = {2:[23,1],  3:[23,1],  4:[23,1],
                             5:[2 ,0],  6:[2 ,0],  7:[2 ,0],
                             8:[5 ,0],  9:[5 ,0], 10:[5 ,0],
                            11:[8 ,0], 12:[8 ,0], 13:[8 ,0],
                            14:[11,0], 15:[11,0], 16:[11,0],
                            17:[14,0], 18:[14,0], 19:[14,0],
                            20:[17,0], 21:[17,0], 22:[17,0],
                            23:[20,0],  0:[20,1],  1:[20,1]}
    #Grapes-3km
    elif sModel_name_lower=="grapes" and sRegion_lower=="3km":
      if Num_BFH==4:
        dynowtime_vs_bhours = {1:[20,1],  2:[20,1],  3:[20,1],  4:[20,1],  5:[20,1],  6:[20,1],
                               7:[2 ,0],  8:[2 ,0],  9:[2 ,0], 10:[2 ,0], 11:[2 ,0], 12:[2 ,0],
                              13:[8 ,0], 14:[8 ,0], 15:[8 ,0], 16:[8 ,0], 17:[8 ,0], 18:[8 ,0],
                              19:[14,0], 20:[14,0], 21:[14,0], 22:[14,0], 23:[14,0],  0:[14,1]}
      else:
        #8次起报
        dynowtime_vs_bhours = {2:[20,1],  3:[20,1],  
                               4:[23,1],  5:[23,1],  6:[23,1],
                               7:[2 ,0],  8:[2 ,0],  9:[2 ,0], 
                              10:[5 ,0], 11:[5 ,0], 12:[5 ,0],
                              13:[8 ,0], 14:[8 ,0], 15:[8 ,0], 
                              16:[11,0], 17:[11,0], 18:[11,0],
                              19:[14,0], 20:[14,0], 21:[14,0], 
                              22:[17,0], 23:[17,0],  0:[17,1], 1:[17,1]}
    #EC细网格
    elif sModel_name_lower=="ec" and (sRegion_lower=="new" or sRegion_lower=="12p5km"):
      dynowtime_vs_bhours = {2:[20,1],  3:[20,1],   4:[20,1],  5:[20,1],  6:[20,1],  7:[20,1],
                             8:[20,1],  9:[20,1],  10:[20,1], 11:[20,1], 12:[20,1], 13:[20,1],
                            14:[8 ,0], 15:[8 ,0],  16:[8 ,0], 17:[8 ,0], 18:[8 ,0], 19:[8 ,0], 
                            20:[8 ,0], 21:[8 ,0],  22:[8 ,0], 23:[8 ,0],  0:[8 ,1],  1:[8 ,1]}
    return dynowtime_vs_bhours


  #当前时间对应的模式起报时间
  def dS3_nowtime_vs_beginhour(self,sModel_name_lower, sRegion_lower, Num_BFH=8):
    '''
      sModel_name_lower = 模式名
      sRegion_lower     = 模式类型
      Num_BFH           = 起报次数
    '''
    #Grapes-3km
    if sModel_name_lower=="grapes" and sRegion_lower=="3km":
      if Num_BFH==4:
        dynowtime_vs_bhours = {1:[20,1],  2:[20,1],  3:[20,1],  4:[20,1],  5:[20,1],  6:[20,1],
                               7:[2 ,0],  8:[2 ,0],  9:[2 ,0], 10:[2 ,0], 11:[2 ,0], 12:[2 ,0],
                              13:[8 ,0], 14:[8 ,0], 15:[8 ,0], 16:[8 ,0], 17:[8 ,0], 18:[8 ,0],
                              19:[14,0], 20:[14,0], 21:[14,0], 22:[14,0], 23:[14,0],  0:[14,1]}
      else:
        #8次起报(13改为0)
        dynowtime_vs_bhours = {0:[20,1],  1:[20,1],  2:[20,1], 
                               3:[23,1],  4:[23,1],  5:[23,1], 
                               6:[2, 0],  7:[2 ,0],  8:[2 ,0], 
                               9:[5 ,0], 10:[5 ,0], 11:[5 ,0], 
                              12:[5 ,0], 13:[8 ,0], 14:[8 ,0], 
                              15:[11,0], 16:[11,0], 17:[11,0], 
                              18:[14,0], 19:[14,0], 20:[14,0], 
                              21:[17,0], 22:[17,0], 23:[17,0]}
    #EC细网格
    elif sModel_name_lower=="ec" and sRegion_lower=="12p5km":
      dynowtime_vs_bhours = {1:[20,1],  2:[20,1],  3:[20,1],   4:[20,1],  5:[20,1],  6:[20,1],  
                             7:[20,1],  8:[20,1],  9:[20,1],  10:[20,1], 11:[20,1], 12:[20,1], 
                            13:[8 ,0], 14:[8 ,0], 15:[8 ,0],  16:[8 ,0], 17:[8 ,0], 18:[8 ,0], 
                            19:[8 ,0], 20:[8 ,0], 21:[8 ,0],  22:[8 ,0], 23:[8 ,0],  0:[8 ,1]}
    else:
      #8次起报(13改为0)
      dynowtime_vs_bhours = {0:[17,1],  1:[20,1],  2:[20,1], 
                             3:[23,1],  4:[23,1],  5:[23,1], 
                             6:[2, 0],  7:[2 ,0],  8:[2 ,0], 
                             9:[5 ,0], 10:[5 ,0], 11:[5 ,0], 
                            12:[5 ,0], 13:[8 ,0], 14:[8 ,0], 
                            15:[11,0], 16:[11,0], 17:[11,0], 
                            18:[14,0], 19:[14,0], 20:[14,0], 
                            21:[17,0], 22:[17,0], 23:[17,0]}
    return dynowtime_vs_bhours

  #当前时间对应的模式起报时间
  def dnowtime_vs_beginhour(self,sModel_name_lower,sRegion_lower, Num_BFH=8):
    '''
      sModel_name_lower = 模式名
      sRegion_lower     = 模式类型
      Num_BFH           = 起报次数
    '''
    #Grapes-3km
    if sModel_name_lower=="grapes" and sRegion_lower=="3km":
      if Num_BFH==4:
        dynowtime_vs_bhours = {1:[20,1],  2:[20,1],  3:[20,1],  4:[20,1],  5:[20,1],  6:[20,1],
                               7:[2 ,0],  8:[2 ,0],  9:[2 ,0], 10:[2 ,0], 11:[2 ,0], 12:[2 ,0],
                              13:[8 ,0], 14:[8 ,0], 15:[8 ,0], 16:[8 ,0], 17:[8 ,0], 18:[8 ,0],
                              19:[14,0], 20:[14,0], 21:[14,0], 22:[14,0], 23:[14,0],  0:[14,1]}
      else:
        #8次起报(13改为)
        dynowtime_vs_bhours = {2:[20,1],  3:[20,1],  
                               4:[23,1],  5:[23,1],  6:[23,1],
                               7:[2 ,0],  8:[2 ,0],  9:[2 ,0], 
                              10:[5 ,0], 11:[5 ,0], 12:[5 ,0], 13:[5 ,0],
                              14:[8 ,0], 15:[8 ,0], 
                              16:[11,0], 17:[11,0], 18:[11,0],
                              19:[14,0], 20:[14,0], 21:[14,0], 
                              22:[17,0], 23:[17,0],  0:[17,1], 1:[17,1]}
    #EC细网格
    elif sModel_name_lower=="ec" and sRegion_lower=="12p5km":
      dynowtime_vs_bhours = {2:[20,1],  3:[20,1],   4:[20,1],  5:[20,1],  6:[20,1],  7:[20,1],
                             8:[20,1],  9:[20,1],  10:[20,1], 11:[20,1], 12:[20,1], 13:[20,1],
                            14:[8 ,0], 15:[8 ,0],  16:[8 ,0], 17:[8 ,0], 18:[8 ,0], 19:[8 ,0], 
                            20:[8 ,0], 21:[8 ,0],  22:[8 ,0], 23:[8 ,0],  0:[8 ,1],  1:[8 ,1]}
    else:
      #8次起报(13改为)
      dynowtime_vs_bhours = {2:[20,1],  3:[20,1],  4:[23,1],  5:[23,1],  6:[23,1],
                             7:[2 ,0],  8:[2 ,0],  9:[2 ,0], 
                            10:[5 ,0], 11:[5 ,0], 12:[5 ,0], 13:[5 ,0],
                            14:[8 ,0], 15:[8 ,0], 
                            16:[11,0], 17:[11,0], 18:[11,0],
                            19:[14,0], 20:[14,0], 21:[14,0], 
                            22:[17,0], 23:[17,0],  0:[17,1], 1:[17,1]}
    return dynowtime_vs_bhours

  #当前时间对应的模式起报时间
  def dnowtime_vs_bhours2(self,sModel_name_lower,sRegion_lower, Num_BFH=8):
    '''
      sModel_name_lower = 模式名
      sRegion_lower     = 模式类型
      Num_BFH           = 起报次数
    '''
    #Grapes-3km
    if sModel_name_lower=="grapes" and sRegion_lower=="3km":
      if Num_BFH==4:
        dynowtime_vs_bhours = {1:[20,1],  2:[20,1],  3:[20,1],  4:[20,1],  5:[20,1],  6:[20,1],
                               7:[2 ,0],  8:[2 ,0],  9:[2 ,0], 10:[2 ,0], 11:[2 ,0], 12:[2 ,0],
                              13:[8 ,0], 14:[8 ,0], 15:[8 ,0], 16:[8 ,0], 17:[8 ,0], 18:[8 ,0],
                              19:[14,0], 20:[14,0], 21:[14,0], 22:[14,0], 23:[14,0],  0:[14,1]}
      else:
        #8次起报(13改为)
        dynowtime_vs_bhours = {2:[20,1],  3:[20,1],  
                               4:[23,1],  5:[23,1],  6:[23,1],
                               7:[2 ,0],  8:[2 ,0],  9:[2 ,0], 
                              10:[5 ,0], 11:[5 ,0], 12:[5 ,0], 13:[5 ,0],
                              14:[8 ,0], 15:[8 ,0], 
                              16:[11,0], 17:[11,0], 18:[11,0],
                              19:[14,0], 20:[14,0], 21:[14,0], 
                              22:[17,0], 23:[17,0],  0:[17,1], 1:[17,1]}
    #EC细网格
    elif sModel_name_lower=="ec" and (sRegion_lower=="new" or sRegion_lower=="12p5km"):
      dynowtime_vs_bhours = {2:[20,1],  3:[20,1],   4:[20,1],  5:[20,1],  6:[20,1],  7:[20,1],
                             8:[20,1],  9:[20,1],  10:[20,1], 11:[20,1], 12:[20,1], 13:[20,1],
                            14:[8 ,0], 15:[8 ,0],  16:[8 ,0], 17:[8 ,0], 18:[8 ,0], 19:[8 ,0], 
                            20:[8 ,0], 21:[8 ,0],  22:[8 ,0], 23:[8 ,0],  0:[8 ,1],  1:[8 ,1]}
    else:
      #8次起报(13改为)
      dynowtime_vs_bhours = {2:[20,1],  3:[20,1],  4:[23,1],  5:[23,1],  6:[23,1],
                             7:[2 ,0],  8:[2 ,0],  9:[2 ,0], 
                            10:[5 ,0], 11:[5 ,0], 12:[5 ,0], 13:[5 ,0],
                            14:[8 ,0], 15:[8 ,0], 
                            16:[11,0], 17:[11,0], 18:[11,0],
                            19:[14,0], 20:[14,0], 21:[14,0], 
                            22:[17,0], 23:[17,0],  0:[17,1], 1:[17,1]}
    return dynowtime_vs_bhours

  #当前时间
  def dnowtime_vs_maxminhour(self,sModel_name_lower,sRegion_lower, Num_BFH=8):
    dynowtime_vs_maxminhour = {20:[20,0], 21:[20,0], 22:[20,0], 23:[20,0],  0:[20,1],  1:[20,1],\
                                2:[20,1],  3:[20,1],  4:[20,1],  5:[20,1],  6:[20,1],  7:[20,1],\
                                8:[8 ,0],  9:[8 ,0], 10:[8 ,0], 11:[8 ,0], 12:[8 ,0], 13:[8 ,0],\
                               14:[8 ,0], 15:[8 ,0], 16:[8 ,0], 17:[8 ,0], 18:[8 ,0], 19:[8 ,0]}
    return dynowtime_vs_maxminhour


  #读季节
  def dRead_Season_ini(self, sIn_sub_path):
    sfile_name = "Season.ini"
    sabs_path  = os.path.join(os.path.abspath(sIn_sub_path), "Parameter", sfile_name)
    if os.path.exists(sabs_path):
      dyconfig_season={}
      config = configparser.ConfigParser()
      config.read(sabs_path)
      dyconfig_season["NYears_ago"] = config.getint('predictor_season', "NYears_ago")
      dyconfig_season["begin_MD"]   = config.get('predictor_season', "begin_MD").split(",")
      dyconfig_season["end_MD"]     = config.get('predictor_season', "end_MD").split(",")
      return dyconfig_season
    else:
      print("No:"+sabs_path)
      sys.exit()
      return None

  #分省的格点代码(每个区域代码,检验使用)
  def dread_province_code(self,sIn_Sub_Path):
    """
    解析地区编码配置
    :param cfg_file:地区编码配置文件
    :return:{province:code}
    """
    sfile_name = "Province_Code"
    cfg_file = os.path.join(sIn_Sub_Path, "Parameter", sfile_name)    
    province_code = {}
    with open(cfg_file,'r') as f_r:
        for line in f_r.readlines():
            code = int(line.split(' ')[0])
            province = line.split(' ')[1]
            province_code[province] = code
    return province_code
  
  #读取分省mask数据
  def dread_mask(self,sIn_Sub_Path, resolution="005"):
    sfile_name = "mask_"+resolution+".dat"
    mask_path = os.path.join(sIn_Sub_Path, "Parameter", sfile_name)    
    array_mask = np.loadtxt(mask_path,skiprows=2)
    return array_mask
    # #获取mask文件起始经纬度
    # with open(mask_path,'r') as f_mask:
        # lines = f_mask.readlines()
        # lon_precision_mask = float(lines[1].split(' ')[7])
        # lat_precision_mask = float(lines[1].split(' ')[8])
        # lon_start_mask = float(lines[1].split(' ')[9])
        # lon_end_mask = float(lines[1].split(' ')[10])
        # lat_start_mask = float(lines[1].split(' ')[11])
        # lat_end_mask = float(lines[1].split(' ')[12])
    # lat_start_index = int((lat_start - lat_start_mask) / lat_precision_mask)
    # lat_end_index = int((lat_end - lat_start_mask) / lat_precision_mask) + 1
    # lon_start_index = int((lon_start - lon_start_mask) / lon_precision_mask)
    # lon_end_index = int((lon_end - lon_start_mask) / lon_precision_mask) + 1
    # #array_mask_sub = array_mask[lat_start_index:lat_end_index,lon_start_index:lon_end_index]



