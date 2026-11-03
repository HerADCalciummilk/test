# -*- coding: utf-8 -*- 
# cython:language_level=3

import os
import sys
import h5py
from shutil import copyfile
import numpy  as np
import pandas as pd
from multiprocessing import Pool, cpu_count
import core.Module_Global_Variable as MGV
import core.Module_MyFunction      as MMyfun

class Class_5Forecast(object):

  "初始化函数"
  def __init__(self, iDebug = 0):
    self.iDebug         = iDebug
    self.cls_gv         = MGV.Class_Global_Variable()
    self.cls_myfun      = MMyfun.Class_MyFunction()
    
  '''读取参数文件'''
  def dRead_Forecast_ini(self,SIn_Sub_Path):
    SFile_Name = "Forecast.ini"
    with open(os.path.join(SIn_Sub_Path, SFile_Name),'r') as fh:
      for i in range(0,3):
        fh.readline()
      iN_FTimes = int(fh.readline())
      ltForecast_Times = []
      for i in range(0,iN_FTimes):
        ltForecast_Times.append(fh.readline().split())    #季节
    return iN_FTimes,ltForecast_Times
  
  def dmulti_S5_Frst_NS_1day(self, args):
    return self.dS5_Frst_NS_1day(*args)
  #预报1天N个站的结果
  def dS5_Frst_NS_1day(self, dy_Pdr_mdl, ltS3_Nt_data, ltmdl_sites, ltPdr_FHours, fGrid_Default=-32766.0):
    """
    dy_Pdr_mdl    : 因子模型
    ltS3_Nt_data  : 1天n个时次的S3数据
    ltmdl_sites   : 站点代号
    """
    #站点循环
    ltfrst_relt=[]
    for ssite_code in ltmdl_sites:
      ndy_Pdr_ID=dy_Pdr_mdl[ssite_code]["ID"]
      #因子循环
      ltdata=[]
      for vd_pdr in ndy_Pdr_ID:
        ifile_idx = ltPdr_FHours.index(int(vd_pdr["Code"][6:9]))
        ltdata.append(ltS3_Nt_data[ifile_idx][ssite_code][vd_pdr["Index"]])
      ndy_Pdr_data=np.array(ltdata)
      if np.nan not in ndy_Pdr_data:
        #标准化
        if dy_Pdr_mdl[ssite_code]["PNORM_METHOD"]=="std":
          std_data=(ndy_Pdr_data-dy_Pdr_mdl[ssite_code]["PNORM"]["mean"])/dy_Pdr_mdl[ssite_code]["PNORM"]["std"]
        elif dy_Pdr_mdl[ssite_code]["PNORM_METHOD"]=="max_min":
          std_data=(ndy_Pdr_data-dy_Pdr_mdl[ssite_code]["PNORM"]["mean"])/dy_Pdr_mdl[ssite_code]["PNORM"]["max-min"]
        #回归预报
        result=np.dot(std_data, dy_Pdr_mdl[ssite_code]["RC"][1:])+dy_Pdr_mdl[ssite_code]["RC"][0]
      else:
        result=fGrid_Default
      ltfrst_relt.append(result)
    return ltfrst_relt
  
  
  #1CF固定因子
  def dmulti_S5_Frst_CF(self, args):
    return self.dS5_Frst_CF(*args)
  #预报1天N个站的结果
  def dS5_Frst_CF(self, dy_Pdr_mdl, ndy_factors, ltmdl_sites, fGrid_Default=-32766.0):  
    #站点循环
    ltfrst_relt=[]
    for idx, ssite_code in enumerate(ltmdl_sites):
      ndy_Pdr_data=np.array(ndy_factors[idx])
      if np.nan not in ndy_Pdr_data:
        #标准化
        if dy_Pdr_mdl[ssite_code]["PNORM_METHOD"]=="std":
          std_data=(ndy_Pdr_data-dy_Pdr_mdl[ssite_code]["PNORM"]["mean"])/dy_Pdr_mdl[ssite_code]["PNORM"]["std"]
        elif dy_Pdr_mdl[ssite_code]["PNORM_METHOD"]=="max_min":
          std_data=(ndy_Pdr_data-dy_Pdr_mdl[ssite_code]["PNORM"]["mean"])/dy_Pdr_mdl[ssite_code]["PNORM"]["max-min"]
        #回归预报
        result=np.dot(std_data, dy_Pdr_mdl[ssite_code]["RC"][1:])+dy_Pdr_mdl[ssite_code]["RC"][0]
      else:
        result=fGrid_Default
      ltfrst_relt.append(result)
    return ltfrst_relt
        
        
  #预报结果质量控制
  def dS5_Frst_QC(self,ndy_frst_relt, sPQ_name_lower):
    #转换为array
    if type(ndy_frst_relt).__module__ != np.__name__:
      ndy_frst_relt = np.array(ndy_frst_relt)
    if sPQ_name_lower=="temperature":                #温度
      mask=np.logical_or(ndy_frst_relt<=-60.0, ndy_frst_relt>=60.0)
      ndy_frst_relt[mask]=np.nan
    elif sPQ_name_lower=="relative_humidity":        #相对湿度
      mask=ndy_frst_relt<=0.0                        
      ndy_frst_relt[mask]=0.1                        
      mask=ndy_frst_relt>100.0                      
      ndy_frst_relt[mask]=100.0                      
    elif sPQ_name_lower=="total_cloud":              #总云量
      mask=ndy_frst_relt<=0.0                        
      ndy_frst_relt[mask]=0.0                        
      mask=ndy_frst_relt>1.0                       
      ndy_frst_relt[mask]=1.0                       
    elif sPQ_name_lower=="visibility":               #能见度
      mask=ndy_frst_relt<10.0
      ndy_frst_relt[mask]=10.0
      mask=ndy_frst_relt>=100000.0
      ndy_frst_relt[mask]=100000.0
    elif sPQ_name_lower=="ws":                       #风速
      mask=ndy_frst_relt<0.0
      ndy_frst_relt[mask]=0.0
      mask=ndy_frst_relt>=120.0
      ndy_frst_relt[mask]=np.nan
    elif sPQ_name_lower=="u" or sPQ_name_lower=="v": #uv风速
      mask=ndy_frst_relt<=-80.0
      ndy_frst_relt[mask]=np.nan
      mask=ndy_frst_relt>=80.0
      ndy_frst_relt[mask]=np.nan
    elif sPQ_name_lower=="precipitation":            #降水
      mask=ndy_frst_relt<0.0
      ndy_frst_relt[mask]=0.0
      mask=ndy_frst_relt>=2000.0
      ndy_frst_relt[mask]=np.nan
    return ndy_frst_relt
  
  
  #保存预报站点的结果
  def dWS5_Frst_sites(self, sOut_abs_path,ltfrst_site_code, ltfrst_relt, sMDL_Time, sFrst_Time):
    #保存数据
    temp_path = sOut_abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_abs_path):
      os.rename(sOut_abs_path, temp_path)
      with h5py.File(temp_path,'a') as fh:
        fh.attrs[self.cls_gv.S5_Frst_Time] = sFrst_Time
        fh.attrs[self.cls_gv.S4_MDL_Time] = sMDL_Time
        ltexist_site=list(fh["value"].value["sites"].astype('U7'))
        ltexist_value=list(fh["value"].value["forecast"])
        for scode,fvalue in zip(ltfrst_site_code,ltfrst_relt):
          if scode not in ltexist_site:
            ltexist_site.append(scode)
            ltexist_value.append(fvalue)
        dtype = np.dtype([("sites", 'S7'), ("forecast",np.float)])
        wdata = np.zeros((len(ltexist_site),), dtype=dtype)
        wdata["sites"]    = np.array(ltexist_site).astype("S7")
        wdata["forecast"] = ltexist_value
        fh["value"].resize(wdata.shape)
        fh["value"][...] = wdata
    else:
      dtype = np.dtype([("sites", 'S7'), ("forecast",np.float)])
      wdata = np.zeros((len(ltfrst_site_code),), dtype=dtype)
      wdata["sites"]    = np.array(ltfrst_site_code).astype("S7")
      wdata["forecast"] = ltfrst_relt
      with h5py.File(temp_path,'a') as fh:
        fh.attrs[self.cls_gv.S5_Frst_Time] = sFrst_Time
        fh.attrs[self.cls_gv.S4_MDL_Time] = sMDL_Time
        fh.create_dataset("value", data=wdata, maxshape=(None,), compression="gzip", compression_opts=9, chunks=True)
    if os.path.exists(temp_path):
      os.rename(temp_path,sOut_abs_path)

        
  #保存预报站点的结果
  def dWS5_Frst_sites_Wind(self, sOut_abs_path, ltfrst_site_code, ltfrst_relt_U, ltfrst_relt_V, ltfrst_relt_WS, sMDL_Time, sFrst_Time):
    #保存数据
    temp_path = sOut_abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_abs_path):
      os.rename(sOut_abs_path, temp_path)
      print(temp_path)
      with h5py.File(temp_path,'a') as fh:
        fh.attrs[self.cls_gv.S5_Frst_Time] = sFrst_Time
        fh.attrs[self.cls_gv.S4_MDL_Time]  = sMDL_Time
        ltexist_site=list(fh["value"].value["sites"].astype('U7'))
        ltexist_U=list(fh["value"].value["U"])
        ltexist_V=list(fh["value"].value["V"])
        ltexist_WS=list(fh["value"].value["WS"])
        for scode,fU,fV,fWS in zip(ltfrst_site_code,ltfrst_relt_U, ltfrst_relt_V, ltfrst_relt_WS):
          if scode not in ltexist_site:
            ltexist_site.append(scode)
            ltexist_U.append(fU)
            ltexist_V.append(fV)
            ltexist_WS.append(fWS)
        dtype = np.dtype([("sites", 'S7'), ("U",np.float), ("V",np.float), ("WS",np.float)])
        wdata = np.zeros((len(ltexist_site),), dtype=dtype)
        wdata["sites"]    = np.array(ltexist_site).astype("S7")
        wdata["U"]  = ltexist_U
        wdata["V"]  = ltexist_V
        wdata["WS"] = ltexist_WS
        fh["value"].resize(wdata.shape)
        fh["value"][...] = wdata
    else:
      dtype = np.dtype([("sites", 'S7'), ("U",np.float), ("V",np.float), ("WS",np.float)])
      wdata = np.zeros((len(ltfrst_site_code),), dtype=dtype)
      wdata["sites"]    = np.array(ltfrst_site_code).astype("S7")
      wdata["U"]  = ltfrst_relt_U
      wdata["V"]  = ltfrst_relt_V
      wdata["WS"] = ltfrst_relt_WS
      with h5py.File(temp_path,'a') as fh:
        fh.attrs[self.cls_gv.S5_Frst_Time] = sFrst_Time
        fh.attrs[self.cls_gv.S4_MDL_Time] = sMDL_Time
        fh.create_dataset("value", data=wdata, maxshape=(None,), compression="gzip", compression_opts=9, chunks=True)
    if os.path.exists(temp_path):
      os.rename(temp_path,sOut_abs_path)
    
  #写格点预报结果
  def dWS5_Frst_Grid(self, sOut_abs_path, ndy_frst_relt, sMDL_Time, sFrst_Time):
    temp_path = sOut_abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_abs_path):
      os.remove(sOut_abs_path)
    with h5py.File(temp_path,'a') as fh:
      fh.attrs[self.cls_gv.S5_Frst_Time] = sFrst_Time
      fh.attrs[self.cls_gv.S4_MDL_Time]  = sMDL_Time
      ltkeys=list(fh.keys())
      if ltkeys!=[]:
        fh[ltkeys[0]][...] = ndy_frst_relt
      else:
        fh.create_dataset("value", data=ndy_frst_relt, compression="gzip", compression_opts=9)
    if os.path.exists(temp_path):
      os.rename(temp_path,sOut_abs_path)
    
  #写格点预报结果
  def dmulti_WS5Frst_Grid(self, args):
     return self.dWS5Frst_Grid(*args)  
  def dWS5Frst_Grid(self, sOut_abs_path, ndy_frst_relt, sMDL_Time, sFrst_Time, sblend_method='1'):
    temp_path = sOut_abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_abs_path):
      os.remove(sOut_abs_path)
    with h5py.File(temp_path,'a') as fh:
      fh.attrs[self.cls_gv.S5_Frst_Time] = sFrst_Time
      fh.attrs[self.cls_gv.S4_MDL_Time]  = sMDL_Time
      fh.attrs['blend_method']           = sblend_method
      ltkeys=list(fh.keys())
      if ltkeys!=[]:
        fh[ltkeys[0]][...] = ndy_frst_relt
      else:
        fh.create_dataset("value", data=ndy_frst_relt, compression="gzip", compression_opts=9)
    if os.path.exists(temp_path):
      os.rename(temp_path,sOut_abs_path)
 
  #写格点预报结果
  def dWS5Frst_Grid2(self, sOut_abs_path, dyfrst_relt, sMDL_Time, sFrst_Time, sblend_method='1'):
    temp_path = sOut_abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_abs_path):
      os.remove(sOut_abs_path)
    with h5py.File(temp_path,'a') as fh:
      fh.attrs[self.cls_gv.S5_Frst_Time] = sFrst_Time
      fh.attrs[self.cls_gv.S4_MDL_Time]  = sMDL_Time
      fh.attrs['blend_method']           = sblend_method
      ltkeys=list(fh.keys())
      if ltkeys!=[]:
        for skeys in ltkeys:
          fh[skeys][...] = dyfrst_relt[skeys]
      else:
        for skeys in dyfrst_relt:
          fh.create_dataset(skeys, data=dyfrst_relt[skeys], compression="gzip", compression_opts=9)
    if os.path.exists(temp_path):
      os.rename(temp_path,sOut_abs_path)

  def dmulti_WS5_Frst_Grid_Wind(self, args):
     return self.dWS5_Frst_Grid_Wind(*args)
  def dWS5_Frst_Grid_Wind(self, sOut_abs_path, ndy_frst_U, ndy_frst_V, ndy_frst_WS, sMDL_Time, sFrst_Time):
    temp_path = sOut_abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_abs_path):
      os.remove(sOut_abs_path)
    with h5py.File(temp_path,'a') as fh:
      fh.attrs[self.cls_gv.S5_Frst_Time] = sFrst_Time
      fh.attrs[self.cls_gv.S4_MDL_Time]  = sMDL_Time
      ltkeys=list(fh.keys())
      #U
      if "U" in ltkeys:
        fh["U"][...] = ndy_frst_U
      else:
        fh.create_dataset("U", data=ndy_frst_U, compression="gzip", compression_opts=9) 
      #V
      if "V" in ltkeys:
        fh["V"][...] = ndy_frst_V
      else:
        fh.create_dataset("V", data=ndy_frst_V, compression="gzip", compression_opts=9) 
      #WS
      if "WS" in ltkeys:
        fh["WS"][...] = ndy_frst_WS
      else:
        fh.create_dataset("WS", data=ndy_frst_WS, compression="gzip", compression_opts=9)
    if os.path.exists(temp_path):
      os.rename(temp_path,sOut_abs_path)


  #读取标量格点预报
  def dmulti_RS5_Grid_scalar(self, args):
     return self.dRS5_Grid_scalar(*args)
  def dRS5_Grid_scalar(self, sIn_abs_path):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        with h5py.File(sIn_abs_path,'r') as fh:
          ndy_data=fh["value"][()]
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        ndy_data = np.array([])
    else:
      ndy_data = np.array([])
    return ndy_data

  #读取矢量格点预报
  def dmulti_RS5_Grid_Wind(self, args):
     return self.dRS5_Grid_Wind(*args)
  def dRS5_Grid_Wind(self, sIn_abs_path, ltkey=["U","V","WS"], ltround=[2,2,2]):
    #文件不存在
    if os.path.exists(sIn_abs_path):
      try:
        with h5py.File(sIn_abs_path,'r') as fh:
          ndy_U =np.round(fh[ltkey[0]][()],ltround[0])
          ndy_V =np.round(fh[ltkey[1]][()],ltround[1])
          ndy_WS=np.round(fh[ltkey[2]][()],ltround[2])
      except Exception as e:
        print("Error:"+sIn_abs_path)
        print(e)
        ndy_U  = np.array([])
        ndy_V  = np.array([])
        ndy_WS = np.array([])
    else:
        ndy_U  = np.array([])
        ndy_V  = np.array([])
        ndy_WS = np.array([])
    return [ndy_U, ndy_V, ndy_WS]
  
  #并行读取
  def dmulti_RS5_GM4_scalar(self, args):
     return self.dRMICAPS_d4_scalar(*args)
  #读取M4数据
  def dRMICAPS_d4_scalar(self, sIn_abs_path, skiprows=2, default=9999.0):
    if os.path.exists(sIn_abs_path):
      try:
        ndy_data=np.loadtxt(sIn_abs_path,skiprows=skiprows)
        ndy_data[np.isnan(ndy_data)]=default
        ndy_data[ndy_data>=default]=np.nan
      except Exception as e:
        print("Error:"+sIn_abs_path)
        ndy_data = np.array([])
    else:
      ndy_data = np.array([])
    return ndy_data
    
  #站点-标量-多个预报时效并行
  def dmulti_Frst_Site_Scalar_1REG_KLM(self, args):
    return self.dFrst_Site_Scalar_1REG_KLM(*args)
  #站点-标量-1个起报时间YMDHd的1REG_KLM训练
  def dFrst_Site_Scalar_1REG_KLM(self, iRFrst_Hours, dyattr, dyrun_info, dyPQ_QC, dyPQ_round, dythreshold, dyVar, dyClass):
    sRFrst_Hours = f"{iRFrst_Hours:03d}"
    print(sRFrst_Hours)
    sPQ_name_lower     = dyVar["sPQ_name"].lower()
    ltSlt_Site_Code    = dyVar["ltSlt_Site_Code"]
    sYMDH_mdl_begin_BJ = dyVar["sYMDH_mdl_begin_BJ"]
    sS4_method         = dyVar["sS4_method"]
    sModel_Region      = dyVar["sModel_Region"]
    imdl_sub_hour      = dyVar["imdl_sub_hour"]
    smdl_sub_hour      = f"{imdl_sub_hour:02d}"
    sS3_sub_path       = dyVar["sS3_sub_path"]
    sPhyQ_shortname    = dyVar["sPhyQ_shortname"]
    sPQ_name_type      = dyVar["sPQ_name_type"]
    sReso_dir          = dyVar["sReso_dir"]
    ndyFmethod         = dyVar["ndyFmethod"]
    ndyrdm_er_0t       = dyVar["ndyrdm_er_0t"]
    ltRE_Weight        = dyVar["ltRE_Weight"]
    dymdl_para_0t      = dyVar["dymdl_para_0t"]
    #输出文件路径
    sOut_file_name = sRFrst_Hours+"_"+sRFrst_Hours+".h5"
    sOut_abs_path  = os.path.join(dyVar["sOut_sub_path"], sOut_file_name)
    #预报时效对应的实况数据路径
    sObs_Y_YMDH      = self.cls_myfun.dBefAftDate2(dyVar["sInBJ_YMDH"], "hour", iRFrst_Hours)
    sObs_Y_file_name = sObs_Y_YMDH+"00"+dyVar["suffix_obs"]
    sObs_Y_sub_path  = os.path.join(dyVar["sobs_site_main_Path"], sObs_Y_YMDH[0:4], dyVar["sPQ_name"], dyVar["sPQ_type_Obs"], sObs_Y_YMDH[0:8])
    sObs_Y_abs_path  = os.path.join(sObs_Y_sub_path, sObs_Y_file_name)
    #print(sObs_Y_abs_path)
    #t时刻对应的S3数据,t场S3值=未来观测时间的预报值
    iS3_X_begin_fhour = imdl_sub_hour+iRFrst_Hours
    sS3_X_begin_fhour = f"{iS3_X_begin_fhour:03d}"
    sS3_X_file_name   = sS3_X_begin_fhour+"_"+sS3_X_begin_fhour+".h5"
    sS3_xt_abs_path   = os.path.join(sS3_sub_path, sS3_X_file_name)
    #print(sS3_xt_abs_path)
    print("S3_Y :"+sYMDH_mdl_begin_BJ+"_"+sS3_X_file_name)
    print("obs_Y:"+sObs_Y_file_name)
    ltvalid_score = [np.nan, np.nan, np.nan, np.nan]
    #无t时刻S3数据
    if not os.path.exists(sS3_xt_abs_path):
      print("No:"+sS3_xt_abs_path)
      return ltvalid_score
    else:
      #读取S3_X数据
      ndyS3_xt_frst= dyClass["cls_S3"].dRS3_site(sS3_xt_abs_path, sPhyQ_shortname, ltsites=ltSlt_Site_Code)
      if ndyS3_xt_frst.size==0:
        print("Error data:"+sS3_xt_abs_path,"Size=0")
        return ltvalid_score
      print("4:Read S3_X over")
      #输入训练模型-恒定参数路径
      sIn_sub_path = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S4_dir, sS4_method, sModel_Region,
                                   sPQ_name_type, sReso_dir, sYMDH_mdl_begin_BJ[8:])
      sIn_file_name = "_".join(["TS", sYMDH_mdl_begin_BJ[8:], sS3_X_begin_fhour, sS3_X_begin_fhour])+".h5"
      sIn_4mdl_xt_abs_path = os.path.join(sIn_sub_path, sIn_file_name)
      #没有xt时刻的训练模型
      if not os.path.exists(sIn_4mdl_xt_abs_path):
        if dyVar["debug"]>=1:print("No:"+sIn_4mdl_xt_abs_path)
        return ltvalid_score
      else:
        #读模型
        dymdl_para_xt={}
        with h5py.File(sIn_4mdl_xt_abs_path,'r') as fh:
          dymdl_para_xt["mdl_time_v"] = fh.attrs["mdl_time_v"]  #计算系统误差的样本时间
          #ndyCF   = fh["CF"][()]    #系数
          ndySE   = fh["SE"][()]    #系统平均误差
          ndysite = fh["site"][()].astype("str")  #站点
          #dymdl_para_xt["CF"] = np.array([ndyCF[ndysite==ssites][0] if ssites in ndysite else 0 for ssites in ltSlt_Site_Code])
          dymdl_para_xt["SE"] = np.array([ndySE[ndysite==ssites][0] if ssites in ndysite else 0 for ssites in ltSlt_Site_Code])
        print("sys_err_time:"+dymdl_para_xt["mdl_time_v"])
        print("5:Read mdl-xt over")
        print("mdl-xt:"+sIn_4mdl_xt_abs_path)
        #t时刻系统误差订正
        ndyCR_xt_frst = ndyS3_xt_frst + dymdl_para_xt["SE"]*ndyFmethod
        #t时刻随机误差订正
        ndyCR_xt_frst = ndyCR_xt_frst + ndyrdm_er_0t*ltRE_Weight[iRFrst_Hours]
        #检验
        if dyrun_info["if_validate"]:
          #读取Obs-xt数据
          if not os.path.exists(sObs_Y_abs_path):
            print("No:"+sObs_Y_abs_path)
          else:
            dfobs_site=dyClass["cls_obsdb"].dRsite_obs(sObs_Y_abs_path, ltSlt_Site_Code, ltindex=[sPhyQ_shortname])#(1行 多列站点) 缺损-32766.0
            dfobs_site[(dfobs_site[sPhyQ_shortname]<=dyPQ_QC[sPhyQ_shortname][0]) | (dfobs_site[sPhyQ_shortname]>=dyPQ_QC[sPhyQ_shortname][1])] = np.nan
            dfobs_site = dfobs_site.round(decimals=dyPQ_round[sPhyQ_shortname])
            ndyobs_Yt = dfobs_site[sPhyQ_shortname].values
            mask_obs=np.isnan(ndyobs_Yt)
            mask_recall=np.isnan(ndyCR_xt_frst)
            mask_S3=np.isnan(ndyS3_xt_frst)
            mask = mask_obs | mask_recall | mask_S3
            #绝对误差
            ndyAE_CR = np.abs(ndyCR_xt_frst[~mask] - ndyobs_Yt[~mask])
            ndyAE_S3 = np.abs(ndyS3_xt_frst[~mask] - ndyobs_Yt[~mask])
            #平均绝对误差
            fMAE_RC = np.round(np.nanmean(ndyAE_CR),3)
            fMAE_S3 = np.round(np.nanmean(ndyAE_S3),3)
            #准确率
            fHIT_RC = np.round(np.sum(ndyAE_CR<=dythreshold[sPhyQ_shortname])/ndyAE_CR.size,3)
            fHIT_S3 = np.round(np.sum(ndyAE_S3<=dythreshold[sPhyQ_shortname])/ndyAE_S3.size,3)
            sline = "HIT:RC"+":"+"%.3f"%fHIT_RC+" S3:"+"%.3f"%fHIT_S3 + " | " + "MAE:RC"+":"+"%.3f"%fMAE_RC+" S3:"+"%.3f"%fMAE_S3
            dyattr['HIT_MAE_xt']=sline
            if(dyVar["debug"]>=1):print(sline)
            print("6:check over")
            if dyrun_info["Out_vidx"]: ltvalid_score = [fHIT_RC, fHIT_S3, fMAE_RC, fMAE_S3]
        #============================================4保存结果================================================
        decimals=1
        ndyCR_xt_frst=self.dS5_Frst_QC(ndyCR_xt_frst, sPQ_name_lower)
        ndyCR_xt_frst=np.around(ndyCR_xt_frst, decimals=decimals)
        dyattr["force_out"]= dyVar["force_out"]
        if "mdl_time_v" in dymdl_para_0t:
          dyattr["mdl_0t_v"] =dymdl_para_0t["mdl_time_v"]
        if "mdl_time_v" in dymdl_para_xt:
          dyattr["mdl_xt_v"] =dymdl_para_xt["mdl_time_v"]
        dyattr["frst_time"]="_".join([sYMDH_mdl_begin_BJ[0:8], sYMDH_mdl_begin_BJ[8:],smdl_sub_hour, sRFrst_Hours])
        dyattr["obs_time"] =sObs_Y_YMDH
        self.dWS5_Site_Frlt(sOut_abs_path, ndyCR_xt_frst, ltsites=ltSlt_Site_Code, dyattr=dyattr)
        print("out:"+sOut_abs_path)
    print("-"*40)
    return ltvalid_score
  
  #写站点标量预报结果(1REG_KLM方法)
  def dWS5_Site_Frlt(self, sOut_abs_path, ndyfrst_relt, ltsites=None, dyattr=None):
    temp_path = sOut_abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_abs_path):
      os.remove(sOut_abs_path)
    with h5py.File(temp_path,'a') as fh:
      #属性
      if dyattr is not None:
        for skey in dyattr:
          fh.attrs[skey] = dyattr[skey]
      ltexist_keys=list(fh.keys())
      #站点
      if ltsites is not None:
        skey="site"
        fh.create_dataset(skey, data=ltsites, compression="gzip", compression_opts=9)
      #数据
      fh.create_dataset("value", data=ndyfrst_relt, compression="gzip", compression_opts=9)
    os.rename(temp_path,sOut_abs_path)
  
  #站点-风-多个预报时效并行
  def dmulti_Frst_Site_Wind_1REG_KLM(self, args):
    return self.dFrst_Site_Wind_1REG_KLM(*args)
  #站点-风-1个预报时间YMDHd的1REG_KLM训练
  def dFrst_Site_Wind_1REG_KLM(self, iRFrst_Hours, dyattr, dyrun_info, dyPQ_QC, dyPQ_round, dythreshold, dyVar, dyClass):
    sRFrst_Hours = f"{iRFrst_Hours:03d}"
    print(sRFrst_Hours)
    ltPhyQ_shortname   = dyVar["ltPhyQ_shortname"]
    sPhyQ_shortname    = ltPhyQ_shortname[-1]
    sPQ_name_type      = dyVar["sPQ_name_type"]
    sPQ_name_lower     = dyVar["sPQ_name"].lower()
    sReso_dir          = dyVar["sReso_dir"]
    ltSlt_Site_Code    = dyVar["ltSlt_Site_Code"]
    sS4_method         = dyVar["sS4_method"]
    sModel_Region      = dyVar["sModel_Region"]
    imdl_sub_hour      = dyVar["imdl_sub_hour"]
    smdl_sub_hour      = f"{imdl_sub_hour:02d}"
    sS3_sub_path       = dyVar["sS3_sub_path"]
    sYMDH_mdl_begin_BJ = dyVar["sYMDH_mdl_begin_BJ"]
    ltRE_Weight        = dyVar["ltRE_Weight"]
    dyFmethod          = dyVar["dyFmethod"]
    fcalm_wd           = dyVar["fcalm_wd"]
    dyrdm_er_0t        = dyVar["dyrdm_er_0t"]
    dymdl_para_0t      = dyVar["dymdl_para_0t"]
    if not os.path.exists(dyVar["sOut_sub_path"]): os.makedirs(dyVar["sOut_sub_path"])
    #输出文件路径
    sOut_file_name = sRFrst_Hours+"_"+sRFrst_Hours+".h5"
    sOut_abs_path  = os.path.join(dyVar["sOut_sub_path"], sOut_file_name)
    #预报时效对应的实况数据路径
    sObs_Y_YMDH      = self.cls_myfun.dBefAftDate2(dyVar["sInBJ_YMDH"], "hour", iRFrst_Hours)
    sObs_Y_file_name = sObs_Y_YMDH+"00"+dyVar["suffix_obs"]
    sObs_Y_sub_path  = os.path.join(dyVar["sobs_site_main_Path"], sObs_Y_YMDH[0:4], dyVar["sPQ_name"], dyVar["sPQ_type_Obs"], sObs_Y_YMDH[0:8])
    sObs_Y_abs_path  = os.path.join(sObs_Y_sub_path, sObs_Y_file_name)
    #print(sObs_Y_abs_path)
    #t时刻对应的S3数据,t场S3值=未来观测时间的预报值
    iS3_X_begin_fhour = imdl_sub_hour+iRFrst_Hours
    sS3_X_begin_fhour = f"{iS3_X_begin_fhour:03d}"
    sS3_X_file_name   = sS3_X_begin_fhour+"_"+sS3_X_begin_fhour+".h5"
    sS3_xt_abs_path   = os.path.join(sS3_sub_path, sS3_X_file_name)
    #print(sS3_xt_abs_path)
    print("S3_Y :"+sYMDH_mdl_begin_BJ+"_"+sS3_X_file_name)
    print("obs_Y:"+sObs_Y_file_name)
    dyvalid_score = {sPhyQ_sn:[np.nan, np.nan, np.nan, np.nan] for sPhyQ_sn in ltPhyQ_shortname}
    #无t时刻S3数据
    if not os.path.exists(sS3_xt_abs_path):
      print("No:"+sS3_xt_abs_path)
      return dyvalid_score
    else:
      #读取S3_X数据
      dyS3_xt_frst = dyClass["cls_S3"].dRS3_site_wind(sS3_xt_abs_path, ltPhyQ_shortname=ltPhyQ_shortname, ltsites=ltSlt_Site_Code)
      if dyS3_xt_frst[sPhyQ_shortname].size==0:
        print("Error data:"+sS3_xt_abs_path,"Size=0")
        return dyvalid_score
      print("4:Read S3_X over")
      #输入训练模型-恒定参数路径
      sIn_sub_path = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S4_dir, sS4_method, sModel_Region,
                                   sPQ_name_type, sReso_dir, sYMDH_mdl_begin_BJ[8:])
      sIn_file_name = "_".join(["TS", sYMDH_mdl_begin_BJ[8:], sS3_X_begin_fhour, sS3_X_begin_fhour])+".h5"
      sIn_4mdl_xt_abs_path = os.path.join(sIn_sub_path, sIn_file_name)
      #没有xt时刻的训练模型
      if not os.path.exists(sIn_4mdl_xt_abs_path):
        if dyVar["debug"]>=1:print("No:"+sIn_4mdl_xt_abs_path)
        return dyvalid_score
      else:
        #读模型
        dymdl_para_xt={"10u":{},"10v":{},sPhyQ_shortname:{}}
        with h5py.File(sIn_4mdl_xt_abs_path,'r') as fh:
          dymdl_para_xt["mdl_time_v"] = fh.attrs["mdl_time_v"]  #计算系统误差的样本时间
          ndysite = fh["site"][()].astype("str")  #站点
          for sPhyQ_sn in ltPhyQ_shortname:
            #ndyCF = fh[sPhyQ_sn]["CF"][()]   #系数
            ndySE = fh[sPhyQ_sn]["SE"][()]   #系统平均误差
            #dymdl_para_xt[sPhyQ_sn]["CF"] = np.array([ndyCF[ndysite==ssites][0] if ssites in ndysite else 0 for ssites in ltSlt_Site_Code])
            dymdl_para_xt[sPhyQ_sn]["SE"] = np.array([ndySE[ndysite==ssites][0] if ssites in ndysite else 0 for ssites in ltSlt_Site_Code])
        print("sys_err_time:"+dymdl_para_xt["mdl_time_v"])
        print("5:Read mdl-xt over")
        print("mdl:"+sIn_4mdl_xt_abs_path)
        dyCR_xt_frst={}
        for sPhyQ_sn in ltPhyQ_shortname:
          #t时刻系统误差订正
          dyCR_xt_frst[sPhyQ_sn] = dyS3_xt_frst[sPhyQ_sn] + dymdl_para_xt[sPhyQ_sn]["SE"]*dyFmethod[sPhyQ_sn] #dymdl_para_xt[sPhyQ_sn]["CF"]*
          #t时刻随机误差订正
          dyCR_xt_frst[sPhyQ_sn] = dyCR_xt_frst[sPhyQ_sn] + dyrdm_er_0t[sPhyQ_sn]*ltRE_Weight[iRFrst_Hours]
        #检验
        if dyrun_info["if_validate"]:
          #读取Obs-xt数据
          if not os.path.exists(sObs_Y_abs_path):
            print("No:"+sObs_Y_abs_path)
          else:
            #读取风站点
            dfobs_site=dyClass["cls_obsdb"].dRsite_obs_wind(sObs_Y_abs_path, ltSlt_Site_Code, ltindex=["WD", sPhyQ_shortname])
            dfobs_site[(dfobs_site[sPhyQ_shortname]<=dyPQ_QC[sPhyQ_shortname][0]) | (dfobs_site[sPhyQ_shortname]>=dyPQ_QC[sPhyQ_shortname][1])] = np.nan
            dfobs_site.loc[dfobs_site["WD"]==fcalm_wd,"WD"] = 0 #静风处理
            dfobs_site["10u"],dfobs_site["10v"] = self.cls_myfun.dWind_to_UV(dfobs_site["WD"].values, dfobs_site[sPhyQ_shortname].values) #风向风速转为uv风
            dfobs_site=dfobs_site.round(decimals=dyPQ_round[sPhyQ_shortname])
            for sPhyQ_sn in ltPhyQ_shortname:
              ndyobs_Yt = dfobs_site[sPhyQ_sn].values
              mask_obs=np.isnan(ndyobs_Yt)
              mask_recall=np.isnan(dyCR_xt_frst[sPhyQ_sn])
              mask_S3=np.isnan(dyS3_xt_frst[sPhyQ_sn])
              mask = mask_obs | mask_recall | mask_S3
              #绝对误差
              ndyAE_CR = np.abs(dyCR_xt_frst[sPhyQ_sn] - ndyobs_Yt)
              ndyAE_S3 = np.abs(dyS3_xt_frst[sPhyQ_sn] - ndyobs_Yt)
              #平均绝对误差
              fMAE_RC = np.round(np.nanmean(ndyAE_CR),3)
              fMAE_S3 = np.round(np.nanmean(ndyAE_S3),3)
              #准确率
              fHIT_RC = np.round(np.sum(ndyAE_CR[~mask]<=dythreshold[sPhyQ_shortname])/ndyAE_CR[~mask].size,3)
              fHIT_S3 = np.round(np.sum(ndyAE_S3[~mask]<=dythreshold[sPhyQ_shortname])/ndyAE_S3[~mask].size,3)
              if sPhyQ_sn==sPhyQ_shortname:
                sline = sPhyQ_sn+"-HIT-RC:"+"%.3f"%fHIT_RC+" S3:"+"%.3f"%fHIT_S3 + " |" +\
                                 " MAE-RC:"+"%.3f"%fMAE_RC+" S3:"+"%.3f"%fMAE_S3
              else:
                sline = sPhyQ_sn+"--HIT-RC:"+"%.3f"%fHIT_RC+" S3:"+"%.3f"%fHIT_S3 + " |" +\
                                  " MAE-RC:"+"%.3f"%fMAE_RC+" S3:"+"%.3f"%fMAE_S3
              dyattr[sPhyQ_sn+"_HIT_MAE_xt"]=sline
              if(dyVar["debug"]>=1):print(sline)
              if dyrun_info["Out_vidx"]:
                dyvalid_score[sPhyQ_sn]=[fHIT_RC, fHIT_S3, fMAE_RC, fMAE_S3]
          print("6:check over")
        #============================================4保存结果================================================
        decimals=1
        for sPhyQ_sn in ltPhyQ_shortname:
          dyCR_xt_frst[sPhyQ_sn]=self.dS5_Frst_QC(dyCR_xt_frst[sPhyQ_sn], sPhyQ_sn)
          dyCR_xt_frst[sPhyQ_sn]=np.around(dyCR_xt_frst[sPhyQ_sn], decimals=decimals)
        dyattr["force_out"]=dyVar["force_out"]
        if "mdl_time_v" in dymdl_para_0t:
          dyattr["mdl_0t_v"] =dymdl_para_0t["mdl_time_v"]
        if "mdl_time_v" in dymdl_para_xt:
          dyattr["mdl_xt_v"] =dymdl_para_xt["mdl_time_v"]
        dyattr["frst_time"]="_".join([sYMDH_mdl_begin_BJ[0:8], sYMDH_mdl_begin_BJ[8:],smdl_sub_hour,sRFrst_Hours])
        dyattr["obs_time"] =sObs_Y_YMDH
        self.dWS5_SWind_Frlt(sOut_abs_path, dyCR_xt_frst, ltsites=ltSlt_Site_Code, dyattr=dyattr)
        print("out:"+sOut_abs_path)
    print("-"*40)
    return dyvalid_score
    
  #写站点矢量预报结果(1REG_KLM方法)
  def dWS5_SWind_Frlt(self, sOut_abs_path, dyfrst_relt, ltsites=None, dyattr=None):
    temp_path = sOut_abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_abs_path):
      os.remove(sOut_abs_path)
    with h5py.File(temp_path,'a') as fh:
      #属性
      if dyattr is not None:
        for skey in dyattr:
          fh.attrs[skey] = dyattr[skey]
      ltexist_keys=list(fh.keys())
      #站点
      if ltsites is not None:
        skey="site"
        fh.create_dataset(skey, data=ltsites, compression="gzip", compression_opts=9)
      #数据
      for skey in dyfrst_relt:
        fh.create_dataset(skey, data=dyfrst_relt[skey], compression="gzip", compression_opts=9)
    os.rename(temp_path, sOut_abs_path)
      
  #格点-风-多个起报时效并行
  def dmulti_Frst_Grid_Wind_1REG_KLM(self, args):
    return self.dFrst_Grid_Wind_1REG_KLM(*args)
  #格点-风-1个起报时间YMDHd的1REG_KLM训练
  def dFrst_Grid_Wind_1REG_KLM(self, iRFrst_Hours, dyattr, dyrun_info, dyPQ_QC, dyPQ_round, dythreshold, dyVar, dyClass):
    sRFrst_Hours   = f"{iRFrst_Hours:03d}"
    print(sRFrst_Hours)
    fdefault           = dyVar["fdefault"]
    suffix_obs         = dyVar["suffix_obs"]
    sPQ_name           = dyVar["sPQ_name"]
    sPQ_name_lower     = dyVar["sPQ_name"].lower()
    sPQ_name_type      = dyVar["sPQ_name_type"]
    sPQ_type_Obs       = dyVar["sPQ_type_Obs"]    
    ltPhyQ_shortname   = dyVar["ltPhyQ_shortname"]
    sPhyQ_shortname    = ltPhyQ_shortname[-1]
    sReso              = dyVar["sReso"]
    sReso_dir          = dyVar["sReso_dir"]
    sYMDH_mdl_begin_BJ = dyVar["sYMDH_mdl_begin_BJ"]
    sInBJ_YMDH         = dyVar["sInBJ_YMDH"]
    sS4_method         = dyVar["sS4_method"]
    sModel_Region      = dyVar["sModel_Region"]
    sModel_Region_upper= sModel_Region.upper()
    imdl_sub_hour      = dyVar["imdl_sub_hour"]
    smdl_sub_hour      = f"{imdl_sub_hour:02d}"
    sS3_sub_path       = dyVar["sS3_sub_path"]
    sOut_sub_path      = dyVar["sOut_sub_path"]
    ltRE_Weight        = dyVar["ltRE_Weight"]
    dyFmethod          = dyVar["dyFmethod"]
    fcalm_wd           = dyVar["fcalm_wd"]
    dyrdm_er_0t        = dyVar["dyrdm_er_0t"]
    dymdl_para_0t      = dyVar["dymdl_para_0t"]
    #输出文件路径
    sOut_file_name = sRFrst_Hours+"_"+sRFrst_Hours+".h5"
    sOut_abs_path  = os.path.join(sOut_sub_path, sOut_file_name)
    #预报时效对应的实况数据路径
    sObs_Y_YMDH      = self.cls_myfun.dBefAftDate2(sInBJ_YMDH, "hour", iRFrst_Hours)
    sObs_Y_file_name = sObs_Y_YMDH+"00"+suffix_obs
    sObs_Y_sub_path  = os.path.join(dyClass["cls_obsdb"].sObs_Main_Path, sObs_Y_YMDH[0:4], sPQ_name, sPQ_type_Obs, sObs_Y_YMDH[0:8])
    sObs_Y_abs_path  = os.path.join(sObs_Y_sub_path, sObs_Y_file_name)
    #t时刻对应的S3数据,t场S3值=未来观测时间的预报值
    iS3_X_begin_fhour = imdl_sub_hour+iRFrst_Hours
    sS3_X_begin_fhour = f"{iS3_X_begin_fhour:03d}"
    sS3_X_file_name   = sS3_X_begin_fhour+"_"+sS3_X_begin_fhour+".h5"
    sS3_xt_abs_path   = os.path.join(sS3_sub_path, sS3_X_file_name)
    print("S3_Y :"+sYMDH_mdl_begin_BJ+"_"+sS3_X_file_name)
    print("obs_Y:"+sObs_Y_file_name)
    dyvalid_score = {sPhyQ_sn:[np.nan, np.nan, np.nan, np.nan] for sPhyQ_sn in ltPhyQ_shortname}
    #无t时刻S3数据
    if not os.path.exists(sS3_xt_abs_path):
      print("No:"+sS3_xt_abs_path)
      return dyvalid_score
    else:
      #矢量
      dyS3_xt_frst=dyClass["cls_S3"].dRS3_Grid_Mvar(sS3_xt_abs_path, ltPhyQ_shortname) #上-下=南-北
      if dyS3_xt_frst[sPhyQ_shortname].size==0: 
        print("Error data:"+sS3_xt_abs_path,"Size=0")
        return dyvalid_score
      print("4:Read S3 xt over")
      #输入训练模型-恒定参数路径
      sIn_sub_path = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S4_dir, sS4_method, sModel_Region,
                                   sPQ_name_type, sReso_dir, sYMDH_mdl_begin_BJ[8:])
      sIn_file_name = "_".join(["TG", sYMDH_mdl_begin_BJ[8:], sS3_X_begin_fhour, sS3_X_begin_fhour])+".h5"
      sIn_4mdl_xt_abs_path = os.path.join(sIn_sub_path, sIn_file_name)
      #没有xt时刻的训练模型
      if not os.path.exists(sIn_4mdl_xt_abs_path):
        if dyVar["debug"]>=1:print("No:"+sIn_4mdl_xt_abs_path)
        return dyvalid_score
      else:
        #矢量
        dymdl_para_xt={"10u":{},"10v":{},sPhyQ_shortname:{}}
        with h5py.File(sIn_4mdl_xt_abs_path,'r') as fh:
          dymdl_para_xt["mdl_time_v"] = fh.attrs["mdl_time_v"]  #计算系统误差的样本时间
          for sPhyQ_sn in ltPhyQ_shortname:               #
            dymdl_para_xt[sPhyQ_sn]["SE"] = fh[sPhyQ_sn]["SE"][()]
        print("sys_err_time:"+dymdl_para_xt["mdl_time_v"])
        print("5:Read mdl-xt over")
        print("mdl:..."+os.sep+os.sep.join(sIn_4mdl_xt_abs_path.split(os.sep)[-7:]))
        #订正
        dyCR_xt_frst={};dyrdm_er_xt={}
        for sPhyQ_sn in ltPhyQ_shortname:
          #t时刻系统误差订正
          dyCR_xt_frst[sPhyQ_sn] = dyS3_xt_frst[sPhyQ_sn] + dymdl_para_xt[sPhyQ_sn]["SE"]*dyFmethod[sPhyQ_sn]
          #t时刻随机误差订正
          dyCR_xt_frst[sPhyQ_sn] = dyCR_xt_frst[sPhyQ_sn] + dyrdm_er_0t[sPhyQ_sn]*ltRE_Weight[iRFrst_Hours]
        #检验
        if dyrun_info["if_validate"]:
          #读取Obs_0数据
          if not os.path.exists(sObs_Y_abs_path):
            print("No:"+sObs_Y_abs_path)
          else:
            ndyu,ndyv = dyClass["cls_obsdb"].dRObs_Grid_Wind(sObs_Y_abs_path) #获得uv数据
            #剪裁插值地形和掩膜数据
            if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
              if dyClass["cls_model"].latlon_info.lat_start==10 and dyClass["cls_model"].latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
                if sReso=="5km":
                  icut_3km_y_lat_num=[200, 1201, 1] #上-下=南-北,截取0-200行南边数据
                elif sReso=="1km":
                  icut_3km_y_lat_num=[1000, 7001, 1]
                ndyu = ndyu[icut_3km_y_lat_num[0]:icut_3km_y_lat_num[1]:icut_3km_y_lat_num[2],:]
                ndyv = ndyv[icut_3km_y_lat_num[0]:icut_3km_y_lat_num[1]:icut_3km_y_lat_num[2],:]
            ndyu[ndyu>=fdefault]=np.nan
            ndyv[ndyv>=fdefault]=np.nan
            dyobs_Yt = {"10u":ndyu,"10v":ndyv,sPhyQ_shortname:np.sqrt(ndyu**2+ndyv**2)}
            for sPhyQ_sn in ltPhyQ_shortname:
              #绝对误差
              ndyAE_CR = np.abs(dyCR_xt_frst[sPhyQ_sn] - dyobs_Yt[sPhyQ_sn])
              ndyAE_S3 = np.abs(dyS3_xt_frst[sPhyQ_sn] - dyobs_Yt[sPhyQ_sn])
              #平均绝对误差
              fMAE_RC = np.round(np.nanmean(ndyAE_CR),3)
              fMAE_S3 = np.round(np.nanmean(ndyAE_S3),3)
              #准确率
              fHIT_RC = np.round(np.sum(ndyAE_CR<=dythreshold[sPhyQ_shortname])/ndyAE_CR.size,3)
              fHIT_S3 = np.round(np.sum(ndyAE_S3<=dythreshold[sPhyQ_shortname])/ndyAE_S3.size,3)
              if sPhyQ_sn==sPhyQ_shortname:
                sline = sPhyQ_sn+"-HIT:RC"+":"+"%.3f"%fHIT_RC+" S3:"+"%.3f"%fHIT_S3+" | "+\
                                  "MAE:RC"+":"+"%.3f"%fMAE_RC+" S3:"+"%.3f"%fMAE_S3
              else:
                sline = sPhyQ_sn+"--HIT:RC"+":"+"%.3f"%fHIT_RC+" S3:"+"%.3f"%fHIT_S3+" | "+\
                                   "MAE:RC"+":"+"%.3f"%fMAE_RC+" S3:"+"%.3f"%fMAE_S3
              dyattr[sPhyQ_sn+"_HIT_MAE_xt"]=sline
              if(dyVar["debug"]>=1):print(sline)
              if dyrun_info["Out_vidx"]:
                dyvalid_score[sPhyQ_sn]=[fHIT_RC, fHIT_S3, fMAE_RC, fMAE_S3]
          print("6:check xt over")
        #============================================4保存结果================================================
        decimals=1
        for sPhyQ_sn in ltPhyQ_shortname:
          dyCR_xt_frst[sPhyQ_sn]=self.dS5_Frst_QC(dyCR_xt_frst[sPhyQ_sn], sPQ_name_lower)
          dyCR_xt_frst[sPhyQ_sn]=np.around(dyCR_xt_frst[sPhyQ_sn], decimals=decimals)
        dyattr["force_out"]=dyVar["force_out"]
        dyattr["mdl_0t_v"] =dymdl_para_0t["mdl_time_v"]
        dyattr["mdl_xt_v"] =dymdl_para_xt["mdl_time_v"]
        dyattr["frst_time"]="_".join([sYMDH_mdl_begin_BJ[0:8], sYMDH_mdl_begin_BJ[8:],smdl_sub_hour,sRFrst_Hours])
        dyattr["obs_time"] =sObs_Y_YMDH
        self.dWS5_WindG_Frlt(sOut_abs_path, dyCR_xt_frst, dyattr=dyattr)
        print("out:"+sOut_abs_path)
    print("-"*40)
    return dyvalid_score
    
    
  #写矢量格点预报结果(1REG_KLM方法)
  def dWS5_WindG_Frlt(self, sOut_abs_path, dyfrst_relt, dyattr=None):
    temp_path = sOut_abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_abs_path):
      os.remove(sOut_abs_path)
    with h5py.File(temp_path,'a') as fh:
      #属性
      if dyattr is not None:
        for skey in dyattr:
          fh.attrs[skey] = dyattr[skey]
      ltexist_keys=list(fh.keys())
      #数据
      if ltexist_keys!=[]:
        for skey in dyfrst_relt:
          fh[skey][...] = dyfrst_relt[skey]
      else:
        for skey in dyfrst_relt:
          fh.create_dataset(skey, data=dyfrst_relt[skey], compression="gzip", compression_opts=9)
    #重命名
    if os.path.exists(temp_path):
      os.rename(temp_path,sOut_abs_path)
    
  #格点-标量-多个起报时效并行
  def dmulti_Frst_Grid_Scalar_1REG_KLM(self, args):
    return self.dFrst_Grid_Scalar_1REG_KLM(*args)
  #格点-标量-1个起报时间YMDHd的1REG_KLM训练
  def dFrst_Grid_Scalar_1REG_KLM(self, iRFrst_Hours, dyattr, dyrun_info, dyPQ_QC, dyPQ_round, dythreshold, dyVar, dyClass):
    fabs_zero          = 273.15
    suffix_obs         = dyVar["suffix_obs"]
    sReso              = dyVar["sReso"]
    sReso_dir          = dyVar["sReso_dir"]
    sPQ_name           = dyVar["sPQ_name"]
    sPQ_name_lower     = dyVar["sPQ_name"].lower()
    sPQ_type_Obs       = dyVar["sPQ_type_Obs"]   
    sPQ_name_type      = dyVar["sPQ_name_type"]    
    sPhyQ_shortname    = dyVar["sPhyQ_shortname"]
    sYMDH_mdl_begin_BJ = dyVar["sYMDH_mdl_begin_BJ"]
    sInBJ_YMDH         = dyVar["sInBJ_YMDH"]
    sS4_method         = dyVar["sS4_method"]
    sModel_Region      = dyVar["sModel_Region"]
    sModel_Region_upper= sModel_Region.upper()
    imdl_sub_hour      = dyVar["imdl_sub_hour"]
    smdl_sub_hour      = f"{imdl_sub_hour:02d}"
    sS3_sub_path       = dyVar["sS3_sub_path"]
    sOut_sub_path      = dyVar["sOut_sub_path"]
    ndyFmethod         = dyVar["ndyFmethod"]
    ndyrdm_er_0t       = dyVar["ndyrdm_er_0t"]
    ltRE_Weight        = dyVar["ltRE_Weight"]
    dymdl_para_0t      = dyVar["dymdl_para_0t"]
    sRFrst_Hours       = f"{iRFrst_Hours:03d}"
    #输出文件路径
    sOut_file_name = sRFrst_Hours+"_"+sRFrst_Hours+".h5"
    sOut_abs_path  = os.path.join(sOut_sub_path, sOut_file_name)
    #预报时效对应的实况数据路径
    sObs_Y_YMDH      = self.cls_myfun.dBefAftDate2(sInBJ_YMDH, "hour", iRFrst_Hours)
    sObs_Y_file_name = sObs_Y_YMDH+"00"+suffix_obs
    sObs_Y_sub_path  = os.path.join(dyClass["cls_obsdb"].sObs_Main_Path, sObs_Y_YMDH[0:4], sPQ_name, sPQ_type_Obs, sObs_Y_YMDH[0:8])
    sObs_Y_abs_path  = os.path.join(sObs_Y_sub_path, sObs_Y_file_name)
    #t时刻对应的S3数据,t场S3值=未来观测时间的预报值
    iS3_X_begin_fhour = imdl_sub_hour+iRFrst_Hours
    sS3_X_begin_fhour = f"{iS3_X_begin_fhour:03d}"
    sS3_X_file_name   = sS3_X_begin_fhour+"_"+sS3_X_begin_fhour+".h5"
    sS3_xt_abs_path   = os.path.join(sS3_sub_path, sS3_X_file_name)
    print("S3_Y :"+sYMDH_mdl_begin_BJ+"_"+sS3_X_file_name)
    print("obs_Y:"+sObs_Y_file_name)
    ltvalid_score = [np.nan, np.nan, np.nan, np.nan]
    #无t时刻S3数据
    if not os.path.exists(sS3_xt_abs_path):
      print("No:"+sS3_xt_abs_path)
      return ltvalid_score
    else:
      ndyS3_xt_frst=dyClass["cls_S3"].dRS3_Grid_scalar(sS3_xt_abs_path, sPhyQ_shortname)
      if ndyS3_xt_frst.size==0: 
        print("Error data:"+sS3_xt_abs_path,"Size=0")
        return ltvalid_score
      print("4:Read S3 xt over")
      #输入训练模型-恒定参数路径
      sIn_sub_path = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S4_dir, sS4_method, sModel_Region,
                                  sPQ_name_type, sReso_dir, sYMDH_mdl_begin_BJ[8:])
      sIn_file_name = "_".join(["TG", sYMDH_mdl_begin_BJ[8:], sS3_X_begin_fhour, sS3_X_begin_fhour])+".h5"
      sIn_4mdl_xt_abs_path = os.path.join(sIn_sub_path, sIn_file_name)
      #没有xt时刻的训练模型
      if not os.path.exists(sIn_4mdl_xt_abs_path):
        if dyVar["debug"]>=1:print("No:"+sIn_4mdl_xt_abs_path)
        return ltvalid_score
      else:
        #读模型
        dymdl_para_xt={}
        with h5py.File(sIn_4mdl_xt_abs_path,'r') as fh:
          dymdl_para_xt["mdl_time_v"] = fh.attrs["mdl_time_v"]  #计算系统误差的样本时间
          #dymdl_para_xt["CF"] = fh["CF"][()]                #
          dymdl_para_xt["SE"] = fh["SE"][()]
        print("sys_err_time:"+dymdl_para_xt["mdl_time_v"])
        print("5:Read mdl xt over")
        print("mdl:..."+os.sep+os.sep.join(sIn_4mdl_xt_abs_path.split(os.sep)[-7:]))
        #t时刻系统误差订正
        ndyCR_xt_frst = ndyS3_xt_frst + dymdl_para_xt["SE"]*ndyFmethod
        #t时刻随机误差订正
        ndyCR_xt_frst = ndyCR_xt_frst + ndyrdm_er_0t*ltRE_Weight[iRFrst_Hours]
        #检验
        if dyrun_info["if_validate"]:
         #读取Obs_0数据
         if not os.path.exists(sObs_Y_abs_path):
           print("No:"+sObs_Y_abs_path)
         else:
           ndyobs_Yt=dyClass["cls_obsdb"].dRObs_Grid(sObs_Y_abs_path) #上-下=南-北
           #剪裁插值地形和掩膜数据
           if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
             if dyClass["cls_model"].latlon_info.lat_start==10 and dyClass["cls_model"].latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
               if sReso=="5km":
                 icut_3km_y_lat_num=[200, 1201, 1] #上-下=南-北,截取0-200行南边数据
               elif sReso=="1km":
                 icut_3km_y_lat_num=[1000, 7001, 1]
               ndyobs_Yt = ndyobs_Yt[icut_3km_y_lat_num[0]:icut_3km_y_lat_num[1]:icut_3km_y_lat_num[2],:]
           if(sPQ_name_lower=="temperature"): ndyobs_Yt = ndyobs_Yt - fabs_zero
           #绝对误差
           ndyAE_CR = np.abs(ndyCR_xt_frst - ndyobs_Yt)
           ndyAE_S3 = np.abs(ndyS3_xt_frst - ndyobs_Yt)
           #平均绝对误差
           fMAE_RC = np.round(np.nanmean(np.abs(ndyCR_xt_frst-ndyobs_Yt)),3)
           fMAE_S3 = np.round(np.nanmean(np.abs(ndyS3_xt_frst-ndyobs_Yt)),3)
           #准确率
           fHIT_RC = np.round(np.sum(ndyAE_CR<=dythreshold[sPhyQ_shortname])/ndyAE_CR.size,3)
           fHIT_S3 = np.round(np.sum(ndyAE_S3<=dythreshold[sPhyQ_shortname])/ndyAE_S3.size,3)
           sline = "HIT-RC"+":"+"%.3f"%fHIT_RC+" S3:"+"%.3f"%fHIT_S3 + " | " + \
                   "MAE-RC"+":"+"%.3f"%fMAE_RC+" S3:"+"%.3f"%fMAE_S3
           dyattr['HIT_MAE_xt']=sline
           if(dyVar["debug"]>=1):print(sline)
           print("4:check xt over")
           if dyrun_info["Out_vidx"]:ltvalid_score = [fHIT_RC, fHIT_S3, fMAE_RC, fMAE_S3]
        #============================================4保存结果================================================
        decimals=1
        ndyCR_xt_frst=self.dS5_Frst_QC(ndyCR_xt_frst, sPQ_name_lower)
        ndyCR_xt_frst=np.around(ndyCR_xt_frst, decimals=decimals)
        dyattr["force_out"]=dyVar["force_out"]
        if "mdl_time_v" in dymdl_para_0t:
          dyattr["mdl_0t_v"] =dymdl_para_0t["mdl_time_v"]
        if "mdl_time_v" in dymdl_para_xt:
          dyattr["mdl_xt_v"] =dymdl_para_xt["mdl_time_v"]
        dyattr["frst_time"]="_".join([sYMDH_mdl_begin_BJ[0:8], sYMDH_mdl_begin_BJ[8:],smdl_sub_hour,sRFrst_Hours])
        dyattr["obs_time"] =sObs_Y_YMDH
        self.dWS5_Grid_Frlt(sOut_abs_path, ndyCR_xt_frst, dyattr=dyattr)
        print("out:"+sOut_abs_path)
    print("-"*40)
    return ltvalid_score

  #格点-多个起报时效并行
  def dmulti_Frst_Grid_2REG_KLM(self, args):
    return self.dFrst_Grid_2REG_KLM(*args)
  #格点-1个起报时间YMDHd的1REG_KLM训练
  def dFrst_Grid_2REG_KLM(self, iRFrst_Hours, dyVar, dyClass):
    sRFrst_Hours       = f"{iRFrst_Hours:03d}"
    fabs_zero          = dyVar["fabs_zero"]
    fdefault           = dyVar["fdefault"]
    suffix_obs         = dyVar["suffix_obs"]
    sReso              = dyVar["sReso"]
    sReso_dir          = dyVar["sReso_dir"]
    sPQ_name           = dyVar["sPQ_name"]
    sPQ_name_lower     = dyVar["sPQ_name"].lower()
    sPQ_type_Obs       = dyVar["sPQ_type_Obs"]   
    sPQ_name_type      = dyVar["sPQ_name_type"]    
    sPhyQ_shortname    = dyVar["sPhyQ_shortname"]
    ltPhyQ_shortname   = dyVar["ltPhyQ_shortname"]
    sYMDH_mdl_begin_BJ = dyVar["sYMDH_mdl_begin_BJ"]
    sInBJ_YMDH         = dyVar["sInBJ_YMDH"]
    sS4_method         = dyVar["sS4_method"]
    sModel_Region      = dyVar["sModel_Region"]
    sModel_Region_upper= sModel_Region.upper()
    imdl_sub_hour      = dyVar["imdl_sub_hour"]
    smdl_sub_hour      = f"{imdl_sub_hour:02d}"
    sS3_sub_path       = dyVar["sS3_sub_path"]
    sOut_sub_path      = dyVar["sOut_sub_path"]
    ltRE_Weight        = dyVar["ltRE_Weight"]
    dythreshold        = dyVar["dythreshold"]
    dymdl_para_0t      = dyVar["dymdl_para_0t"]
    dyPQ_round         = dyVar["dyPQ_round"]
    dyPQ_QC            = dyVar["dyPQ_QC"]
    dyrun_info         = dyVar["dyrun_info"]
    dyattr             = dyVar["dyattr"]
    dyzone             = dyVar["dyzone"]
    dycut              = dyVar["dycut"]
    #--------------------------------------------------
    #输出文件路径
    sOut_file_name = sRFrst_Hours+"_"+sRFrst_Hours+".h5"
    sOut_abs_path  = os.path.join(sOut_sub_path, sOut_file_name)
    #预报时效对应的实况数据路径
    sObs_Y_YMDH      = self.cls_myfun.dBefAftDate2(sInBJ_YMDH, "hour", iRFrst_Hours)
    sObs_Y_file_name = sObs_Y_YMDH+"00"+suffix_obs
    sObs_Y_sub_path  = os.path.join(dyClass["cls_obsdb"].sObs_Main_Path, sObs_Y_YMDH[0:4], sPQ_name, sPQ_type_Obs, sObs_Y_YMDH[0:8])
    sObs_Y_abs_path  = os.path.join(sObs_Y_sub_path, sObs_Y_file_name)
    #t时刻对应的S3数据,t场S3值=未来观测时间的预报值
    iS3_X_begin_fhour = imdl_sub_hour+iRFrst_Hours
    sS3_X_begin_fhour = f"{iS3_X_begin_fhour:03d}"
    sS3_X_file_name   = sS3_X_begin_fhour+"_"+sS3_X_begin_fhour+".h5"
    sS3_xt_abs_path   = os.path.join(sS3_sub_path, sS3_X_file_name)
    print("S3_Y :"+sYMDH_mdl_begin_BJ+"_"+sS3_X_file_name)
    print("obs_Y:"+sObs_Y_file_name)
    if sPhyQ_shortname in ["10ws"]:
      dyvalid_score = {sPhyQ_sn:[np.nan, np.nan, np.nan, np.nan] for sPhyQ_sn in ltPhyQ_shortname}
    else:
      dyvalid_score = {sPhyQ_shortname:[np.nan, np.nan, np.nan, np.nan]}
    #无t时刻S3数据
    if not os.path.exists(sS3_xt_abs_path):
      print("No:"+sS3_xt_abs_path)
      return dyvalid_score
    else:
      #矢量
      if sPhyQ_shortname in ["10ws"]:
        dyS3_xt_frst=dyClass["cls_S3"].dRS3_Grid_Mvar(sS3_xt_abs_path, ltPhyQ_shortname) #上-下=南-北
        if dyS3_xt_frst[sPhyQ_shortname].size==0: 
          print("Error data:"+sS3_xt_abs_path,"Size=0")
          return dyvalid_score
      #标量
      else:
        ndyS3_xt_frst=dyClass["cls_S3"].dRS3_Grid_scalar(sS3_xt_abs_path, sPhyQ_shortname)
        if ndyS3_xt_frst.size==0: 
          print("Error data:"+sS3_xt_abs_path,"Size=0")
          return dyvalid_score
        print("4:Read S3 xt over")
      if dyVar["debug"]>=1:print("S3_xt:"+sS3_xt_abs_path)
      #xt-训练模型-每日参数路径
      sYMDH_mdl_xt_BJ  = self.dPara_YMDH(sYMDH_mdl_begin_BJ, iRFrst_Hours)
      sIn_sub_path  = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S4_dir, sS4_method, sModel_Region,
                                   sPQ_name_type, sReso_dir, sYMDH_mdl_xt_BJ[0:4], sYMDH_mdl_xt_BJ[0:8], sYMDH_mdl_xt_BJ[8:])
      sIn_file_name = "_".join(["TG", sYMDH_mdl_xt_BJ[8:], sS3_X_begin_fhour, sS3_X_begin_fhour])+".h5"
      sIn_4mdl_xt_abs_path = os.path.join(sIn_sub_path, sIn_file_name)
      #不是回算&每日参数不存在=找恒定参数路径
      if (not os.path.exists(sIn_4mdl_xt_abs_path)) and (not dyrun_info["recall"]):
        sIn_sub_path = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S4_dir, sS4_method, sModel_Region,
                                    sPQ_name_type, sReso_dir, sYMDH_mdl_begin_BJ[8:])
        sIn_4mdl_xt_abs_path = os.path.join(sIn_sub_path, sIn_file_name)
      dyattr["mdl_xt"]=sIn_4mdl_xt_abs_path
      #没有xt时刻的训练模型
      if not os.path.exists(sIn_4mdl_xt_abs_path):
        if dyVar["debug"]>=1:print("No:"+sIn_4mdl_xt_abs_path)
        return dyvalid_score
      else:
        if sPhyQ_shortname in ["10ws"]:
          dymdl_para_xt={sPhyQ_sn:{"SE":None,"CF":None} for sPhyQ_sn in ltPhyQ_shortname}
          with h5py.File(sIn_4mdl_xt_abs_path,'r') as fh:
            dymdl_para_xt["mdl_time_v"] = fh.attrs["mdl_time_v"]  #计算系统误差的样本时间
            for sPhyQ_sn in ltPhyQ_shortname:
              dymdl_para_xt[sPhyQ_sn]["SE"] = fh[sPhyQ_sn]["SE"][()]
              dymdl_para_xt[sPhyQ_sn]["CF"] = fh[sPhyQ_sn]["CF"][()]
          print("sys_err_time:"+dymdl_para_xt["mdl_time_v"])
          print("mdl:..."+os.sep+os.sep.join(sIn_4mdl_xt_abs_path.split(os.sep)[-7:]))
          #----------------------随机误差权重公共路径----------------------------------------------------------
          #随机场权重路径
          sYMDH_mdl_xt_BJ  = self.dPara_YMDH(sYMDH_mdl_begin_BJ, iRFrst_Hours)
          sIn_rdm_sub_path = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S5_dir, sS4_method, sModel_Region,
                                          sPQ_name_type, sReso_dir, sYMDH_mdl_xt_BJ[0:4],  sYMDH_mdl_xt_BJ[0:8], 
                                          sYMDH_mdl_xt_BJ[8:], smdl_sub_hour, "alpha")
          sIn_file_name = sRFrst_Hours+".h5"
          sIn_rdm_abs_path  = os.path.join(sIn_rdm_sub_path, sIn_file_name)
          if (not os.path.exists(sIn_rdm_abs_path)) and (not dyrun_info["recall"]):
            sIn_rdm_sub_path  = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S5_dir, sS4_method, sModel_Region,
                                             sPQ_name_type, sReso_dir, "alpha", sYMDH_mdl_begin_BJ[8:],smdl_sub_hour)
            sIn_rdm_abs_path  = os.path.join(sIn_rdm_sub_path, sIn_file_name)
            print("RdmPara:"+os.sep.join(["alpha", sYMDH_mdl_begin_BJ[8:],smdl_sub_hour,sIn_file_name]))
          else: #业务运行
            print("RdmPara:"+os.sep.join(["....", sYMDH_mdl_xt_BJ[0:4], sYMDH_mdl_xt_BJ[0:8], sYMDH_mdl_xt_BJ[8:], \
                                                  smdl_sub_hour, "alpha", sIn_file_name]),os.path.exists(sIn_rdm_abs_path))
          #读取随机场权重信息
          if os.path.exists(sIn_rdm_abs_path):
            RW_U, RW_V, RW_WS =self.dRS5_Grid_Wind(sIn_rdm_abs_path, ltkey=ltPhyQ_shortname)
            dyrdm_Weight={ltPhyQ_shortname[0]:RW_U,ltPhyQ_shortname[1]:RW_V,ltPhyQ_shortname[2]:RW_WS}
            dyattr["rdm_xt"]=sIn_rdm_abs_path
          else:
            dyattr["rdm_xt"]="None"
            dyrdm_Weight={ltPhyQ_shortname[0]:ltRE_Weight[iRFrst_Hours],
                          ltPhyQ_shortname[1]:ltRE_Weight[iRFrst_Hours],
                          ltPhyQ_shortname[2]:ltRE_Weight[iRFrst_Hours]}
          #订正
          dySC_xt_frst={};dyRC_xt_frst={}
          for sPhyQ_sn in ltPhyQ_shortname:
            #t时刻系统误差订正
            dySC_xt_frst[sPhyQ_sn] = dyS3_xt_frst[sPhyQ_sn] + dymdl_para_xt[sPhyQ_sn]["SE"]*dymdl_para_xt[sPhyQ_sn]["CF"]
            #t时刻随机误差订正
            dyRC_xt_frst[sPhyQ_sn] = dySC_xt_frst[sPhyQ_sn] + dyVar["rdm_er_0t"][sPhyQ_sn]*dyrdm_Weight[sPhyQ_sn]
          #---------------------------------------------------------------------------------------------------------
          #检验
          if dyrun_info["if_validate"]:
            #读取t场Obs数据
            if not os.path.exists(sObs_Y_abs_path):
              print("No:"+sObs_Y_abs_path)
            else:
              ndyu,ndyv = dyClass["cls_obsdb"].dRObs_Grid_Wind(sObs_Y_abs_path) #获得uv数据
              #剪裁
              if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
                if dyClass["cls_model"].latlon_info.lat_start==10 and dyClass["cls_model"].latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
                  ndyu = ndyu[dycut[sReso][0]:dycut[sReso][1]:dycut[sReso][2],:]
                  ndyv = ndyv[dycut[sReso][0]:dycut[sReso][1]:dycut[sReso][2],:]
              ndyu[ndyu>=fdefault]=np.nan
              ndyv[ndyv>=fdefault]=np.nan
              dyobs_Yt = {"10u":ndyu,"10v":ndyv,sPhyQ_shortname:np.sqrt(ndyu**2+ndyv**2)}
              for sPhyQ_sn in ltPhyQ_shortname:
                #绝对误差
                ndyAE_S3 = np.abs(dyS3_xt_frst[sPhyQ_sn] - dyobs_Yt[sPhyQ_sn])
                ndyAE_SC = np.abs(dySC_xt_frst[sPhyQ_sn] - dyobs_Yt[sPhyQ_sn])
                ndyAE_RC = np.abs(dyRC_xt_frst[sPhyQ_sn] - dyobs_Yt[sPhyQ_sn])
                #中国区域
                ndyAE_S3_China = ndyAE_S3[dyzone[sReso]["mask_area"]]
                ndyAE_SC_China = ndyAE_SC[dyzone[sReso]["mask_area"]]
                ndyAE_RC_China = ndyAE_RC[dyzone[sReso]["mask_area"]]
                #平均绝对误差
                fMAE_S3_China = np.round(np.nanmean(ndyAE_S3_China),3)
                fMAE_SC_China = np.round(np.nanmean(ndyAE_SC_China),3)
                fMAE_RC_China = np.round(np.nanmean(ndyAE_RC_China),3)
                #准确率
                fHIT_S3_China = np.round(np.sum(ndyAE_S3_China<=dythreshold[sPhyQ_shortname])/ndyAE_S3_China.size,3)
                fHIT_SC_China = np.round(np.sum(ndyAE_SC_China<=dythreshold[sPhyQ_shortname])/ndyAE_SC_China.size,3)
                fHIT_RC_China = np.round(np.sum(ndyAE_RC_China<=dythreshold[sPhyQ_shortname])/ndyAE_RC_China.size,3)
                sline = "HIT-RC:"+"%.3f"%fHIT_RC_China+" SC:%.3f"%fHIT_SC_China+" S3:%.3f"%fHIT_S3_China + " | " +\
                        "MAE-RC:"+"%.3f"%fMAE_RC_China+" SC:%.3f"%fMAE_SC_China+" S3:%.3f"%fMAE_S3_China
                dyattr[sPhyQ_sn+"_HIT_MAE_xt"]=sline
                if(dyVar["debug"]>=1):print("-".join([sRFrst_Hours,sPhyQ_sn,sline]))
                if dyrun_info["Out_vidx"]: dyvalid_score[sPhyQ_sn] = [fHIT_RC_China, fHIT_S3_China, fMAE_RC_China, fMAE_S3_China]
              print("-"*40)
          #============================================4保存结果================================================
          decimals=1
          for sPhyQ_sn in ltPhyQ_shortname:
            dyRC_xt_frst[sPhyQ_sn]=self.dS5_Frst_QC(dyRC_xt_frst[sPhyQ_sn], sPQ_name_lower)
            dyRC_xt_frst[sPhyQ_sn]=np.around(dyRC_xt_frst[sPhyQ_sn], decimals=decimals)
          dyattr["force_out"]=dyVar["force_out"]
          dyattr["mdl_0t_v"] =dymdl_para_0t["mdl_time_v"]
          dyattr["mdl_xt_v"] =dymdl_para_xt["mdl_time_v"]
          dyattr["frst_time"]="_".join([sYMDH_mdl_begin_BJ[0:8], sYMDH_mdl_begin_BJ[8:],smdl_sub_hour,sRFrst_Hours])
          dyattr["obs_time"] =sObs_Y_YMDH
          self.dWS5_WindG_Frlt(sOut_abs_path, dyRC_xt_frst, dyattr=dyattr)
          print("out:"+sOut_abs_path)
          return dyvalid_score
        #标量
        else:
          #读模型
          dymdl_para_xt={}
          with h5py.File(sIn_4mdl_xt_abs_path,'r') as fh:
            dymdl_para_xt["mdl_time_v"] = fh.attrs["mdl_time_v"]  #计算系统误差的样本时间
            dymdl_para_xt["CF"] = fh["CF"][()]                #
            dymdl_para_xt["SE"] = fh["SE"][()]
          print("sys_err_time:"+dymdl_para_xt["mdl_time_v"])
          print("mdl:..."+os.sep+os.sep.join(sIn_4mdl_xt_abs_path.split(os.sep)[-7:]))
          #----------------------随机误差权重公共路径----------------------------------------------------------
          #随机场权重路径
          sYMDH_mdl_xt_BJ  = self.dPara_YMDH(sYMDH_mdl_begin_BJ, iRFrst_Hours)
          sIn_rdm_sub_path = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S5_dir, sS4_method, sModel_Region,
                                          sPQ_name_type, sReso_dir, sYMDH_mdl_xt_BJ[0:4],  sYMDH_mdl_xt_BJ[0:8], 
                                          sYMDH_mdl_xt_BJ[8:], smdl_sub_hour, "alpha")
          sIn_file_name = sRFrst_Hours+".h5"
          sIn_rdm_abs_path  = os.path.join(sIn_rdm_sub_path, sIn_file_name)
          if (not os.path.exists(sIn_rdm_abs_path)) and (not dyrun_info["recall"]):
            sIn_rdm_sub_path  = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S5_dir, sS4_method, sModel_Region,
                                             sPQ_name_type, sReso_dir, "alpha", sYMDH_mdl_begin_BJ[8:],smdl_sub_hour)
            sIn_rdm_abs_path  = os.path.join(sIn_rdm_sub_path, sIn_file_name)
            print("RdmPara:"+os.sep.join(["alpha", sYMDH_mdl_begin_BJ[8:],smdl_sub_hour,sIn_file_name]))
          else: #业务运行
            print("RdmPara:"+os.sep.join(["....", sYMDH_mdl_xt_BJ[0:4], sYMDH_mdl_xt_BJ[0:8], sYMDH_mdl_xt_BJ[8:], \
                                                  smdl_sub_hour, "alpha", sIn_file_name]),os.path.exists(sIn_rdm_abs_path))
          #读取随机场权重信息
          if os.path.exists(sIn_rdm_abs_path):
            rdm_Weight=self.dRS5_Grid_scalar(sIn_rdm_abs_path)
            dyattr["rdm_xt"]=sIn_rdm_abs_path
          else:
            rdm_Weight=ltRE_Weight[iRFrst_Hours]
            dyattr["rdm_xt"]="None"
          #t时刻系统误差订正
          ndySC_xt_frst = ndyS3_xt_frst + dymdl_para_xt["SE"]*dymdl_para_xt["CF"]
          #t时刻随机误差订正
          ndyRC_xt_frst = ndySC_xt_frst + dyVar["rdm_er_0t"]*rdm_Weight
          #检验
          if dyrun_info["if_validate"]:
            #读取Obs_0数据
            if not os.path.exists(sObs_Y_abs_path):
              print("No:"+sObs_Y_abs_path)
            else:
              ndyobs_Yt=dyClass["cls_obsdb"].dRObs_Grid(sObs_Y_abs_path) #上-下=南-北
              #剪裁插值地形和掩膜数据
              if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
                if dyClass["cls_model"].latlon_info.lat_start==10 and dyClass["cls_model"].latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
                  ndyobs_Yt = ndyobs_Yt[dycut[sReso][0]:dycut[sReso][1]:dycut[sReso][2],:]
              if(sPQ_name_lower=="temperature"): ndyobs_Yt = ndyobs_Yt - fabs_zero
              #绝对误差
              ndyAE_S3 = np.abs(ndyS3_xt_frst - ndyobs_Yt)
              ndyAE_SC = np.abs(ndySC_xt_frst - ndyobs_Yt)
              ndyAE_RC = np.abs(ndyRC_xt_frst - ndyobs_Yt)
              ndyAE_S3_China = ndyAE_S3[dyzone[sReso]["mask_area"]]
              ndyAE_SC_China = ndyAE_SC[dyzone[sReso]["mask_area"]]
              ndyAE_RC_China = ndyAE_RC[dyzone[sReso]["mask_area"]]
              #平均绝对误差
              fMAE_S3_China = np.round(np.nanmean(ndyAE_S3_China),3)
              fMAE_SC_China = np.round(np.nanmean(ndyAE_SC_China),3)
              fMAE_RC_China = np.round(np.nanmean(ndyAE_RC_China),3)
              #准确率
              fHIT_S3_China = np.round(np.sum(ndyAE_S3_China<=dythreshold[sPhyQ_shortname])/ndyAE_S3_China.size,3)
              fHIT_SC_China = np.round(np.sum(ndyAE_SC_China<=dythreshold[sPhyQ_shortname])/ndyAE_SC_China.size,3)
              fHIT_RC_China = np.round(np.sum(ndyAE_RC_China<=dythreshold[sPhyQ_shortname])/ndyAE_RC_China.size,3)
              sline = "HIT-RC:"+"%.3f"%fHIT_RC_China+" SC:%.3f"%fHIT_SC_China+" S3:%.3f"%fHIT_S3_China + " | " +\
                      "MAE-RC:"+"%.3f"%fMAE_RC_China+" SC:%.3f"%fMAE_SC_China+" S3:%.3f"%fMAE_S3_China
              dyattr['HIT_MAE_xt']=sline
              if(dyVar["debug"]>=1):print("-".join([sRFrst_Hours,sPhyQ_shortname,sline]))
              print("4:check xt over")
              if dyrun_info["Out_vidx"]:dyvalid_score = {sPhyQ_shortname:[fHIT_RC_China, fHIT_S3_China, fMAE_RC_China, fMAE_S3_China]}
            print("-"*40)
          #============================================4保存结果================================================
          decimals=1
          ndyRC_xt_frst=self.dS5_Frst_QC(ndyRC_xt_frst, sPQ_name_lower)
          ndyRC_xt_frst=np.around(ndyRC_xt_frst, decimals=decimals)
          dyattr["force_out"]=dyVar["force_out"]
          if "mdl_time_v" in dymdl_para_0t:
            dyattr["mdl_0t_v"] =dymdl_para_0t["mdl_time_v"]
          if "mdl_time_v" in dymdl_para_xt:
            dyattr["mdl_xt_v"] =dymdl_para_xt["mdl_time_v"]
          dyattr["frst_time"]="_".join([sYMDH_mdl_begin_BJ[0:8], sYMDH_mdl_begin_BJ[8:],smdl_sub_hour,sRFrst_Hours])
          dyattr["obs_time"] =sObs_Y_YMDH
          self.dWS5_Grid_Frlt(sOut_abs_path, ndyRC_xt_frst, dyattr=dyattr)
          print("out:"+sOut_abs_path)
          return dyvalid_score
  
  #并行参数
  def dmulti_S5_2REG_KLM_RPara(self, args):
    return self.dS5_2REG_KLM_RPara(*args)
  #1个预报时次的参数
  def dS5_2REG_KLM_RPara(self, iRFrst_Hours, dyVar, dyClass):
    idebug              = dyVar['debug']
    iupdate             = dyVar['update']
    fdefault            = dyVar['fdefault']
    fabs_zero           = dyVar['fabs_zero']
    suffix_obs          = dyVar['suffix_obs']
    sInBJ_YMDH_ago      = dyVar['sInBJ_YMDH_ago']
    sPQ_name            = dyVar['sPQ_name']
    sPQ_name_lower      = sPQ_name.lower()
    sPQ_type_Obs        = dyVar['sPQ_type_Obs']
    sPQ_name_type       = dyVar['sPQ_name_type']
    sReso               = dyVar['sReso']
    sReso_dir           = dyVar['sReso_dir']
    dynowtime_vs_bhours = dyVar['dynowtime_vs_bhours']
    sS4_method          = dyVar['sS4_method']
    sModel_Region       = dyVar['sModel_Region']
    sModel_Region_upper = sModel_Region.upper()
    sPhyQ_shortname     = dyVar['sPhyQ_shortname']
    ltPhyQ_shortname    = dyVar['ltPhyQ_shortname']
    dyrun_info          = dyVar['dyrun_info']
    dycut               = dyVar['dycut']
    dyzone              = dyVar['dyzone']
    dythreshold         = dyVar["dythreshold"]
    iRC_method          = dyVar['iRC_method']
    if sPhyQ_shortname in ["10ws"]:
      dyobs_xt          = dyVar['dyobs_xt']
    else:
      ndyobs_xt         = dyVar['ndyobs_xt']
    #---------------------------------------------
    sRFrst_Hours        = f"{iRFrst_Hours:03d}"
    print(sRFrst_Hours+"-Para")
    #历史滚动起报时间对应的obs时间和路径
    sObs_0t_YMDH      = self.cls_myfun.dBefAftDate2(sInBJ_YMDH_ago, "hour", -iRFrst_Hours)
    sObs_0t_file_name = sObs_0t_YMDH+"00"+suffix_obs
    sObs_0t_sub_path  = os.path.join(dyClass["cls_obsdb"].sObs_Main_Path, sObs_0t_YMDH[0:4], sPQ_name, sPQ_type_Obs, sObs_0t_YMDH[0:8])
    sObs_0t_abs_path  = os.path.join(sObs_0t_sub_path, sObs_0t_file_name)
    #模式起报时间
    ltmdl_begin_hour    = dynowtime_vs_bhours[int(sObs_0t_YMDH[8:])]                   #多往前1天,因为预报时效有超过24小时
    shour_mdl_begin     = "%02d"%ltmdl_begin_hour[0]                                   #模式起报时
    sYMD_mdl_begin      = self.cls_myfun.dtimes_ago(sObs_0t_YMDH[0:8], ltmdl_begin_hour[1]) #模式起报日期YMD
    sYMDH_mdl_begin_BJ  = sYMD_mdl_begin+shour_mdl_begin  #(北京时间)                  #模式起报日期YMDH
    #模式起报时间与起报时间
    imdl_sub_hour = self.cls_myfun.dYMDH_diff_hours(sYMDH_mdl_begin_BJ, sObs_0t_YMDH)
    smdl_sub_hour = f"{imdl_sub_hour:02d}"
    #0场的S3值=当前观测时间的预报值
    iS3_0_begin_fhour = imdl_sub_hour  #起报时刻对应的
    sS3_0_begin_fhour = f"{iS3_0_begin_fhour:03d}"
    sS3_0_file_name   = sS3_0_begin_fhour+"_"+sS3_0_begin_fhour+".h5"
    sS3_sub_path  = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S3_dir, dyrun_info["s3_method"], sModel_Region, sReso_dir,
                                 sYMDH_mdl_begin_BJ[0:4], sYMDH_mdl_begin_BJ[0:8], sYMDH_mdl_begin_BJ[8:])
    sS3_0t_abs_path   = os.path.join(sS3_sub_path, sS3_0_file_name)
    print("S3-0t :"+sYMDH_mdl_begin_BJ+"_"+sS3_0_file_name)
    #0时刻训练模型-每天参数路径
    sYMDH_mdl_BJ  = self.dPara_YMDH(sYMDH_mdl_begin_BJ, iRFrst_Hours) #if dyrun_info["recall"]:
    sIn_sub_path  = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S4_dir, sS4_method, sModel_Region,
                                 sPQ_name_type, sReso_dir, sYMDH_mdl_BJ[0:4], sYMDH_mdl_BJ[0:8], sYMDH_mdl_BJ[8:])
    sIn_file_name = "_".join(["TG", sYMDH_mdl_BJ[8:], sS3_0_begin_fhour, sS3_0_begin_fhour])+".h5"
    sIn_4mdl_0t_abs_path = os.path.join(sIn_sub_path, sIn_file_name)
    print("mdl_0t:"+os.sep.join([sYMDH_mdl_BJ[0:8], sYMDH_mdl_BJ[8:],sIn_file_name]))
    #t时刻对应的S3数据,t场S3值=未来观测时间的预报值
    iS3_X_begin_fhour = imdl_sub_hour+iRFrst_Hours
    sS3_X_begin_fhour = f"{iS3_X_begin_fhour:03d}"
    sS3_X_file_name   = sS3_X_begin_fhour+"_"+sS3_X_begin_fhour+".h5"
    sS3_xt_abs_path   = os.path.join(sS3_sub_path, sS3_X_file_name)
    print("S3_xt :"+sYMDH_mdl_begin_BJ+"_"+sS3_X_file_name)
    #t时刻训练模型-每天参数路径
    sIn_file_name = "_".join(["TG", sYMDH_mdl_BJ[8:], sS3_X_begin_fhour, sS3_X_begin_fhour])+".h5"
    sIn_4mdl_xt_abs_path = os.path.join(sIn_sub_path, sIn_file_name)
    print("mdl_xt:"+os.sep.join([sYMDH_mdl_BJ[0:8], sYMDH_mdl_BJ[8:],sIn_file_name]))
    #--------------------------参数输出文件路径----------------------------------------------------------
    #1个起报时效的参数路径
    sOut_1d_sub_path  = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S5_dir, sS4_method, sModel_Region,
                                  sPQ_name_type, sReso_dir, sYMDH_mdl_begin_BJ[0:4], sYMDH_mdl_begin_BJ[0:8], 
                                  sYMDH_mdl_begin_BJ[8:],smdl_sub_hour,"alpha")
    if not os.path.exists(sOut_1d_sub_path): os.makedirs(sOut_1d_sub_path)
    sOut_file_name = sRFrst_Hours+".h5"
    sOut_1d_abs_path  = os.path.join(sOut_1d_sub_path, sOut_file_name) #输出文件路径
    #公共起报时效的参数路径
    sOut_cmn_sub_path  = os.path.join(dyClass["cls_gp"].sResult_Main_Path, dyClass["cls_gv"].S5_dir, sS4_method, sModel_Region,
                                      sPQ_name_type, sReso_dir, "alpha", sYMDH_mdl_begin_BJ[8:],smdl_sub_hour)
    sOut_cmn_abs_path  = os.path.join(sOut_cmn_sub_path, sOut_file_name)
    if not os.path.exists(sOut_cmn_sub_path): os.makedirs(sOut_cmn_sub_path)
    #不需要更新
    if os.path.exists(sOut_1d_abs_path) and iupdate==0:         
      print("No_update:"+sOut_1d_abs_path)
      return
    else:
      #---------------------------------------------------------------
      #无0t-obs &无0t-xt场S3数据 & 没有0t-xt训练模型
      if not (os.path.exists(sObs_0t_abs_path) and \
              os.path.exists(sS3_0t_abs_path) and os.path.exists(sS3_xt_abs_path) and \
              os.path.exists(sIn_4mdl_0t_abs_path) and os.path.exists(sIn_4mdl_xt_abs_path)):
        if not (os.path.exists(sObs_0t_abs_path)):
          print("No:"+sObs_0t_abs_path)
        elif not (os.path.exists(sS3_0t_abs_path)):
          print("No:"+sS3_0t_abs_path)
        elif not (os.path.exists(sS3_xt_abs_path)):
          print("No:"+sS3_xt_abs_path)
        elif not (os.path.exists(sIn_4mdl_0t_abs_path)):
          print("No:"+sIn_4mdl_0t_abs_path)
        elif not (os.path.exists(sIn_4mdl_xt_abs_path)):
          print("No:"+sIn_4mdl_xt_abs_path)
        return
      else:
        dyattr={"mdl_YMDH_HH_HHH":"_".join([sYMDH_mdl_BJ,smdl_sub_hour,sRFrst_Hours])}
        print("mdl_YMDH_HH_HHH:"+"_".join([sYMDH_mdl_BJ,smdl_sub_hour,sRFrst_Hours]))
        #-------------------------读取0t-实况数据---------------------------
        #矢量
        if sPhyQ_shortname in ["10ws"]:
          ndyu,ndyv = dyClass['cls_obsdb'].dRObs_Grid_Wind(sObs_0t_abs_path) #获得uv数据
          #剪裁观测数据
          if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
            if dyClass['cls_model'].latlon_info.lat_start==10 and dyClass['cls_model'].latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
              ndyu = ndyu[dycut['cut'][0]:dycut['cut'][1]:dycut['cut'][2],:]
              ndyv = ndyv[dycut['cut'][0]:dycut['cut'][1]:dycut['cut'][2],:]
          ndyu[ndyu>=fdefault]=np.nan
          ndyv[ndyv>=fdefault]=np.nan
          dyobs_0t = {"10u":ndyu,"10v":ndyv,sPhyQ_shortname:np.sqrt(ndyu**2+ndyv**2)}
        #标量
        else:
          ndyobs_0t=dyClass['cls_obsdb'].dRObs_Grid(sObs_0t_abs_path) #上-下=南-北
          #剪裁观测数据
          if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
            if dyClass['cls_model'].latlon_info.lat_start==10 and dyClass['cls_model'].latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
              ndyobs_0t = ndyobs_0t[dycut['cut'][0]:dycut['cut'][1]:dycut['cut'][2],:]
          if(sPQ_name_lower=="temperature"): ndyobs_0t = ndyobs_0t - fabs_zero
        if idebug>=1:print("Obs_0t:"+sObs_0t_abs_path)
        #矢量
        if sPhyQ_shortname in ["10ws"]:
          #---------------------------读0t场S3-------------------------------------
          dyS3_0t_frst=dyClass["cls_S3"].dRS3_Grid_Mvar(sS3_0t_abs_path, ltPhyQ_shortname) #上-下=南-北
          if dyS3_0t_frst[sPhyQ_shortname].size==0: 
            print("Error data:"+sS3_0t_abs_path,"Size=0")
            return
          if idebug>=1:print("S3_0t:"+sS3_0t_abs_path)
          #---------------------------读xt场S3-------------------------------------
          dyS3_xt_frst=dyClass["cls_S3"].dRS3_Grid_Mvar(sS3_xt_abs_path, ltPhyQ_shortname) #上-下=南-北
          if dyS3_xt_frst[sPhyQ_shortname].size==0: 
            print("Error data:"+sS3_xt_abs_path,"Size=0")
            return
          if idebug>=1:print("S3_xt:"+sS3_xt_abs_path)
          #---------------------------读0t场模型-----------------------------------
          dymdl_para_0t={"10u":{},"10v":{},sPhyQ_shortname:{}}
          with h5py.File(sIn_4mdl_0t_abs_path,'r') as fh:
            dymdl_para_0t["mdl_time_v"] = fh.attrs["mdl_time_v"]  #计算系统误差的样本时间
            for sPhyQ_sn in ltPhyQ_shortname:
              dymdl_para_0t[sPhyQ_sn]["SE"] = fh[sPhyQ_sn]["SE"][()]
              dymdl_para_0t[sPhyQ_sn]["CF"] = fh[sPhyQ_sn]["CF"][()]
            dyattr["mdl_0t"]=sIn_4mdl_0t_abs_path
            dyattr["mdl_0t_vtime"]=dymdl_para_0t["mdl_time_v"]
          print("mdl_0t:"+sIn_4mdl_0t_abs_path)
          #---------------------------读xt场模型-----------------------------------
          dymdl_para_xt={"10u":{},"10v":{},sPhyQ_shortname:{}}
          with h5py.File(sIn_4mdl_xt_abs_path,'r') as fh:
            dymdl_para_xt["mdl_time_v"] = fh.attrs["mdl_time_v"]  #计算系统误差的样本时间
            for sPhyQ_sn in ltPhyQ_shortname:
              dymdl_para_xt[sPhyQ_sn]["SE"] = fh[sPhyQ_sn]["SE"][()]
              dymdl_para_xt[sPhyQ_sn]["CF"] = fh[sPhyQ_sn]["CF"][()]
            dyattr["mdl_xt"]=sIn_4mdl_xt_abs_path
            dyattr["mdl_xt_vtime"]=dymdl_para_xt["mdl_time_v"]
          print("mdl_xt:"+sIn_4mdl_xt_abs_path)
          #要素循环
          dyRdCof={}
          for sPhyQ_sn in ltPhyQ_shortname:
            #0t-系统误差修订场
            ndySC_0t_frst = dyS3_0t_frst[sPhyQ_sn] + dymdl_para_0t[sPhyQ_sn]["SE"]*dymdl_para_0t[sPhyQ_sn]["CF"]
            #0t-随机误差
            ndyEr_0t = dyobs_0t[sPhyQ_sn] - ndySC_0t_frst
            #xt-系统误差修订场
            ndySC_xt_frst = dyS3_xt_frst[sPhyQ_sn] + dymdl_para_xt[sPhyQ_sn]["SE"]*dymdl_para_xt[sPhyQ_sn]["CF"]
            #xt-剩余绝对误差(系数=0)
            ndyAE_SC_xt = np.abs(dyobs_xt[sPhyQ_sn] - ndySC_xt_frst)
            if iRC_method==1:
              #--------------------------方案1--------------------------------
              #中国区域AE
              ndyAE_SC_xt_China = ndyAE_SC_xt[dyzone[sReso]["mask_area"]] #变1d
              #中国区域MAE
              fMAE_SC_xt_China = np.round(np.nanmean(ndyAE_SC_xt_China),3)
              #参数遍历
              fRdCof=0
              for fcof in dyVar["ndyRPara"]:
                ndyRC_xt_frst = ndySC_xt_frst + ndyEr_0t*fcof  #0场随机误差修正后
                #xt-剩余绝对误差
                ndyAE_RC_xt = np.abs(dyobs_xt[sPhyQ_sn] - ndyRC_xt_frst)
                #中国区域AE
                ndyAE_RC_xt_China = ndyAE_RC_xt[dyzone[sReso]["mask_area"]]
                #中国区域MAE
                fMAE_RC_xt_China = np.round(np.nanmean(ndyAE_RC_xt_China),3)
                if fMAE_RC_xt_China<fMAE_SC_xt_China:
                  fRdCof=fcof
                  fMAE_SC_xt_China=fMAE_RC_xt_China
              #随机误差参数
              ndyRdCof = np.zeros_like(ndySC_xt_frst)
              dyRdCof[sPhyQ_sn] = np.round(ndyRdCof+fRdCof,2)
            else:
              #--------------------------方案2--------------------------------
              ndyRdCof = np.zeros_like(ndySC_xt_frst)
              for fcof in dyVar["ndyRPara"]:
                ndyRC_xt_frst = ndySC_xt_frst + ndyEr_0t*fcof  #0场随机误差修正后
                #xt-剩余绝对误差
                ndyAE_RC_xt = np.abs(dyobs_xt[sPhyQ_sn] - ndyRC_xt_frst)
                mask=ndyAE_RC_xt<ndyAE_SC_xt
                ndyRdCof[mask]=fcof
                ndyAE_SC_xt[mask]=ndyAE_RC_xt[mask]
              dyRdCof[sPhyQ_sn] = np.round(ndyRdCof,2)
            #---------------------------------------------------------------
            #检验
            if dyrun_info["if_validate"]:
              ndyRC_xt_frst = dyS3_xt_frst[sPhyQ_sn] + dymdl_para_xt[sPhyQ_sn]["SE"]*dymdl_para_xt[sPhyQ_sn]["CF"] + ndyEr_0t*dyRdCof[sPhyQ_sn]
              #绝对误差
              ndyAE_S3 = np.abs(dyS3_xt_frst[sPhyQ_sn] - dyobs_xt[sPhyQ_sn])
              ndyAE_SC = np.abs(ndySC_xt_frst - dyobs_xt[sPhyQ_sn])
              ndyAE_RC = np.abs(ndyRC_xt_frst - dyobs_xt[sPhyQ_sn])
              ndyAE_S3_China = ndyAE_S3[dyzone[sReso]["mask_area"]]
              ndyAE_SC_China = ndyAE_SC[dyzone[sReso]["mask_area"]]
              ndyAE_RC_China = ndyAE_RC[dyzone[sReso]["mask_area"]]
              #平均绝对误差
              fMAE_S3_China = np.round(np.nanmean(ndyAE_S3_China),3)
              fMAE_SC_China = np.round(np.nanmean(ndyAE_SC_China),3)
              fMAE_RC_China = np.round(np.nanmean(ndyAE_RC_China),3)
              #准确率
              fHIT_S3_China = np.round(np.sum(ndyAE_S3_China<=dythreshold[sPhyQ_sn])/ndyAE_S3_China.size,3)
              fHIT_SC_China = np.round(np.sum(ndyAE_SC_China<=dythreshold[sPhyQ_sn])/ndyAE_SC_China.size,3)
              fHIT_RC_China = np.round(np.sum(ndyAE_RC_China<=dythreshold[sPhyQ_sn])/ndyAE_RC_China.size,3)
              sline = "HIT-RC:"+"%.3f"%fHIT_RC_China+" SC:%.3f"%fHIT_SC_China+" S3:%.3f"%fHIT_S3_China + " | " +\
                      "MAE:RC:"+"%.3f"%fMAE_RC_China+" SC:%.3f"%fMAE_SC_China+" S3:%.3f"%fMAE_S3_China
              dyattr[sPhyQ_sn+"_HIT_MAE"]=sline
              if iRC_method==1:
                if(idebug>=1):print("-".join([sRFrst_Hours,sPhyQ_sn,"%.2f"%fRdCof,sline]))
              else:
               if(idebug>=1):print("-".join([sRFrst_Hours,sPhyQ_sn,sline]))
          #输出参数
          self.dWS5_WindG_Frlt(sOut_1d_abs_path, dyRdCof, dyattr=dyattr)
          if(idebug>=1):print("out-1t:"+sOut_1d_abs_path)
          #保存恒定文件夹内最优参数(复制)
          if dyrun_info["para_cmn_out"]: 
            self.dCopy_rlt(sOut_1d_abs_path, sOut_cmn_abs_path)
            if idebug>=1:print("out-cp:"+sOut_cmn_abs_path)
          print("-"*40)
          return
        #标量
        else:
          #---------------------------读0t场S3-------------------------------------
          ndyS3_0t_frst=dyClass["cls_S3"].dRS3_Grid_scalar(sS3_0t_abs_path, sPhyQ_shortname)
          if ndyS3_0t_frst.size==0: 
            print("Error data:"+sS3_0t_abs_path,"Size=0")
            return
          if idebug>=1:print("S3_0t:"+sS3_0t_abs_path)
          #---------------------------读xt场S3-------------------------------------
          ndyS3_xt_frst=dyClass["cls_S3"].dRS3_Grid_scalar(sS3_xt_abs_path, sPhyQ_shortname)
          if ndyS3_xt_frst.size==0: 
            print("Error data:"+sS3_xt_abs_path,"Size=0")
            return
          if idebug>=1:print("S3_xt:"+sS3_xt_abs_path)
          #---------------------------读0t场模型-----------------------------------
          dymdl_para_0t={}
          with h5py.File(sIn_4mdl_0t_abs_path,'r') as fh:
            dymdl_para_0t["mdl_time_v"] = fh.attrs["mdl_time_v"]  #计算系统误差的样本时间
            dymdl_para_0t["SE"] = fh["SE"][()]
            dymdl_para_0t["CF"] = fh["CF"][()]
            if(idebug>=1):print("mdl_time_0t:"+dymdl_para_0t["mdl_time_v"])
            dyattr["mdl_0t"]=sIn_4mdl_0t_abs_path
            dyattr["mdl_0t_vtime"]=dymdl_para_0t["mdl_time_v"]
          print("mdl_0t:"+sIn_4mdl_0t_abs_path)
          #---------------------------读xt场模型-----------------------------------
          dymdl_para_xt={}
          with h5py.File(sIn_4mdl_xt_abs_path,'r') as fh:
            dymdl_para_xt["mdl_time_v"] = fh.attrs["mdl_time_v"]  #计算系统误差的样本时间
            dymdl_para_xt["SE"] = fh["SE"][()]
            dymdl_para_xt["CF"] = fh["CF"][()]
            dyattr["mdl_xt"]=sIn_4mdl_xt_abs_path
            dyattr["mdl_xt_vtime"]=dymdl_para_xt["mdl_time_v"]
            if(idebug>=1):print("mdl_time_xt:"+dymdl_para_xt["mdl_time_v"])
          print("mdl_xt:"+sIn_4mdl_xt_abs_path)
          #0t-系统误差修订场
          ndySC_0t_frst = ndyS3_0t_frst + dymdl_para_0t["SE"]*dymdl_para_0t["CF"]
          #0t-随机误差
          ndyEr_0t = ndyobs_0t - ndySC_0t_frst
          #xt-系统误差修订场
          ndySC_xt_frst = ndyS3_xt_frst + dymdl_para_xt["SE"]*dymdl_para_xt["CF"]
          #xt-随机误差
          ndyEr_SC_xt = ndyobs_xt - ndySC_xt_frst
          #xt-剩余绝对误差(系数=0)
          ndyAE_SC_xt = np.abs(ndyEr_SC_xt)
          if iRC_method==1:
            #--------------------------方案1--------------------------------
            #中国区域AE
            ndyAE_SC_xt_China = ndyAE_SC_xt[dyzone[sReso]["mask_area"]] #变->1d
            #中国区域MAE
            fMAE_SC_xt_China = np.round(np.nanmean(ndyAE_SC_xt_China),3)
            #参数遍历
            ndyRdCof=np.zeros_like(ndySC_xt_frst)
            fRdCof=0
            for fcof in dyVar["ndyRPara"]:
              ndyRC_xt_frst = ndySC_xt_frst + ndyEr_0t*fcof  #0场随机误差修正后
              #xt-剩余绝对误差
              ndyAE_RC_xt = np.abs(ndyobs_xt - ndyRC_xt_frst)
              #中国区域AE
              ndyAE_RC_xt_China = ndyAE_RC_xt[dyzone[sReso]["mask_area"]] #变->1d
              #中国区域MAE
              fMAE_RC_xt_China = np.round(np.nanmean(ndyAE_RC_xt_China),3)
              if fMAE_RC_xt_China<fMAE_SC_xt_China:
                fRdCof=fcof
                fMAE_SC_xt_China=fMAE_RC_xt_China
            #随机误差参数
            ndyRdCof = np.round(ndyRdCof+fRdCof,2)
          else:
            #--------------------------方案2--------------------------------
            #参数遍历
            ndyRdCof=np.zeros_like(ndySC_xt_frst)
            for fcof in dyVar["ndyRPara"]:
              ndyRC_xt_frst = ndySC_xt_frst + ndyEr_0t*fcof  #0场随机误差修正后
              #xt-剩余绝对误差
              ndyAE_RC_xt = np.abs(ndyobs_xt - ndyRC_xt_frst)
              mask=ndyAE_RC_xt<ndyAE_SC_xt
              ndyRdCof[mask]=fcof
              ndyAE_SC_xt[mask]=ndyAE_RC_xt[mask]
            #随机误差参数-初始化
            ndyRdCof = np.round(ndyRdCof,2)
          #----------------------------------------------------------------
          #检验
          if dyrun_info["if_validate"]:
            ndyRC_xt_frst = ndyS3_xt_frst + dymdl_para_xt["SE"]*dymdl_para_xt["CF"] + ndyEr_0t*ndyRdCof
            #绝对误差
            ndyAE_S3 = np.abs(ndyS3_xt_frst - ndyobs_xt)
            ndyAE_SC = np.abs(ndySC_xt_frst - ndyobs_xt)
            ndyAE_RC = np.abs(ndyRC_xt_frst - ndyobs_xt)
            ndyAE_S3_China = ndyAE_S3[dyzone[sReso]["mask_area"]]
            ndyAE_SC_China = ndyAE_SC[dyzone[sReso]["mask_area"]]
            ndyAE_RC_China = ndyAE_RC[dyzone[sReso]["mask_area"]]
            #平均绝对误差
            fMAE_S3_China = np.round(np.nanmean(ndyAE_S3_China),3)
            fMAE_SC_China = np.round(np.nanmean(ndyAE_SC_China),3)
            fMAE_RC_China = np.round(np.nanmean(ndyAE_RC_China),3)
            #准确率
            fHIT_S3_China = np.round(np.sum(ndyAE_S3_China<=dythreshold[sPhyQ_shortname])/ndyAE_S3_China.size,3)
            fHIT_SC_China = np.round(np.sum(ndyAE_SC_China<=dythreshold[sPhyQ_shortname])/ndyAE_SC_China.size,3)
            fHIT_RC_China = np.round(np.sum(ndyAE_RC_China<=dythreshold[sPhyQ_shortname])/ndyAE_RC_China.size,3)
            sline = "HIT-RC:"+"%.3f"%fHIT_RC_China+" SC:%.3f"%fHIT_SC_China+" S3:%.3f"%fHIT_S3_China + " | " +\
                    "MAE:RC:"+"%.3f"%fMAE_RC_China+" SC:%.3f"%fMAE_SC_China+" S3:%.3f"%fMAE_S3_China
            dyattr[sPhyQ_shortname+"_HIT_MAE"]=sline
            if iRC_method==1:
              if(idebug>=1):print("-".join([sRFrst_Hours,sPhyQ_shortname,"%.2f"%fRdCof,sline]))
            else:
              if(idebug>=1):print("-".join([sRFrst_Hours,sPhyQ_shortname,sline]))
          #输出参数
          self.dWS5_Grid_Frlt(sOut_1d_abs_path, ndyRdCof, dyattr=dyattr)
          if(idebug>=1):print("out-1t:"+sOut_1d_abs_path)
          #保存恒定文件夹内最优参数(复制)
          if dyrun_info["para_cmn_out"]: 
            self.dCopy_rlt(sOut_1d_abs_path, sOut_cmn_abs_path)
            if idebug>=1:print("out-cp:"+sOut_cmn_abs_path)
          print("-"*40)
          return
  

    
  #写标量格点预报结果(1REG_KLM方法)
  def dWS5_Grid_Frlt(self, sOut_abs_path, ndy_frst_relt, dyattr=None):
    temp_path = sOut_abs_path+".tmp"
    if os.path.exists(temp_path):
      os.remove(temp_path)
    if os.path.exists(sOut_abs_path):
      os.remove(sOut_abs_path)
    with h5py.File(temp_path,'a') as fh:
      #属性
      if dyattr is not None:
        for skey in dyattr:
          fh.attrs[skey] = dyattr[skey]
      ltexist_keys=list(fh.keys())
      #数据
      if ltexist_keys!=[]:
        fh[ltexist_keys[0]][...] = ndy_frst_relt
      else:
        fh.create_dataset("value", data=ndy_frst_relt, compression="gzip", compression_opts=9)
    if os.path.exists(temp_path):
      os.rename(temp_path,sOut_abs_path)

  #输出空间插值数据
  def dCopy_rlt(self, ssrc_abs_path, sdst_abs_path):
    temp_path = sdst_abs_path+".tmp"
    #删除存在的tmp文件
    if os.path.exists(temp_path):os.remove(temp_path)
    #复制
    copyfile(ssrc_abs_path, temp_path)
    #移除旧文件
    if os.path.exists(sdst_abs_path):os.remove(sdst_abs_path)
    #重命名
    os.rename(temp_path, sdst_abs_path)
    return

  #---历史参数日期文件夹--------------------------------------------------------------
  #回算读取建模和预报系统误差和随机误差参数
  def dPara_YMDH(self, smdl_YMDH_begin, iRFrst_hour):
    fquo,frem=divmod(iRFrst_hour, 24) #商数,余数
    sYMDH_Para = self.cls_myfun.dtimes_ago(smdl_YMDH_begin, int(fquo)+1, sformat="%Y%m%d%H")
    return sYMDH_Para




