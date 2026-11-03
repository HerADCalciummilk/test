# -*- coding: utf-8 -*- 
# cython:language_level=3
import os
import re
import sys
import pandas as pd

class Class_Station_Info(object):

  "初始化函数"
  def __init__(self, iDebug = 0):
    self.iDebug              = iDebug  #>=1:调试, 0:业务
    self.iNSlt_Sites         = 0       #站点个数
    self.ltSlt_Site_Class    = []      #站点类别  
    self.ltSlt_Site_Code     = []      #站点代码(整型)
    self.ltSlt_Site_Prov_PY  = []      #站点所属省份的拼音
    self.ltSlt_Site_Lon      = []      #站点经度(度)
    self.ltSlt_Site_Lat      = []      #站点纬度(度)
    self.ltSlt_Site_Alt      = []      #站点海拔(m)
    self.ltSlt_Site_Name     = []      #站点中文名
    self.ltSlt_Site_Prov_Chi = []      #站点所属省份的中文
    return

  #读取所选站点信息
  def dRead_Station_Info(self,SIn_Abs_Path):
    with open(SIn_Abs_Path,'r', encoding='UTF-8') as fh:
      self.iNSlt_Sites = int(fh.readline().split()[0])  #站点个数
      dt_site={}
      for i in range(0,self.iNSlt_Sites):
        ltwork = re.split('[, \t]', fh.readline().strip())
        ltwork = list(filter(None, ltwork))
        self.ltSlt_Site_Code.append(ltwork[0])
        self.ltSlt_Site_Prov_PY.append(ltwork[1])
        self.ltSlt_Site_Lon.append(float(ltwork[2]))
        self.ltSlt_Site_Lat.append(float(ltwork[3]))
        self.ltSlt_Site_Alt.append(float(ltwork[4]))
        self.ltSlt_Site_Name.append(ltwork[5])
        self.ltSlt_Site_Prov_Chi.append(ltwork[6])
        dt_site[ltwork[0]] = [ltwork[1],
                              float(ltwork[2]),
                              float(ltwork[3]),
                              float(ltwork[4]),
                              ltwork[5],ltwork[6]]
    return dt_site

  #读取所选站点信息
  def dread_station(self, sabs_path, lthead_name=None, skiprows=1):
    dfsites = pd.read_csv(sabs_path, delim_whitespace=True, skiprows=skiprows, header=None, names=lthead_name)
    return dfsites


  #读取所选站点信息
  def dRead_Station_Info_5Column(self,SIn_Abs_Path):
    with open(SIn_Abs_Path,'r') as fh:
       self.iNSlt_Sites = int(fh.readline().split()[0])  #站点个数
       for i in range(0,self.iNSlt_Sites):
         ltwork = re.split('[, \t]', fh.readline().strip())
         ltwork = list(filter(None, ltwork))
         self.ltSlt_Site_Code.append(ltwork[0])
         self.ltSlt_Site_Lat.append(float(ltwork[1]))
         self.ltSlt_Site_Lon.append(float(ltwork[2]))
         self.ltSlt_Site_Alt.append(float(ltwork[3]))
         self.ltSlt_Site_Name.append(ltwork[4])
    return
    
    
  #读取MEOFIS所有站点信息
  def dRead_MEOFIS_Station_Info_6Column(self,SIn_Abs_Path):
    with open(SIn_Abs_Path,'r') as fh:
       self.iNSlt_Sites = int(fh.readline().split()[0])  #站点个数
       for i in range(0,self.iNSlt_Sites):
         ltwork = re.split('[, \t]', fh.readline().strip())
         ltwork = list(filter(None, ltwork))
         self.ltSlt_Site_Code.append(ltwork[0])          #站点代码
         self.ltSlt_Site_Name.append(ltwork[1])          #名称
         self.ltSlt_Site_Lat.append(float(ltwork[2]))    #纬度
         self.ltSlt_Site_Lon.append(float(ltwork[3]))    #经度
         self.ltSlt_Site_Alt.append(float(ltwork[4]))    #海拔
         self.ltSlt_Site_Prov_Chi.append(ltwork[5])      #所属
    return
    

  #读取带有分类的站点信息
  def dRead_Class_Station_Info(self, SIn_Abs_Path):
    with open(SIn_Abs_Path,'r') as fh:
       self.iNSlt_Sites = int(fh.readline().split()[0])  #站点个数
       for i in range(0,self.iNSlt_Sites):
         ltwork = re.split('[, \t]', fh.readline().strip())
         ltwork = list(filter(None, ltwork))
         self.ltSlt_Site_Class.append(int(ltwork[0]))
         self.ltSlt_Site_Code.append(ltwork[1])
         self.ltSlt_Site_Prov_PY.append(ltwork[2])
         self.ltSlt_Site_Lon.append(float(ltwork[3]))
         self.ltSlt_Site_Lat.append(float(ltwork[4]))
         self.ltSlt_Site_Alt.append(float(ltwork[5]))
         self.ltSlt_Site_Name.append(ltwork[6])
         self.ltSlt_Site_Prov_Chi.append(ltwork[7])
    return
    
    
    
    
    