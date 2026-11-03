# -*- coding: utf-8 -*- 
# cython:language_level=3

import sys
import math
import datetime
import argparse

class Class_Arguments(object):

  "初始化函数"
  def __init__(self,step="S4"):
    self.step       = step.upper()
    self.dtNow      = datetime.datetime.now()
    self.inow_Year  = self.dtNow.year
    self.inow_Month = self.dtNow.month
    self.inow_Day   = self.dtNow.day
    self.inow_hour  = self.dtNow.hour
    self.inow_ymd   = int(self.dtNow.strftime('%Y%m%d'))
    self.inow_ymdh  = int(self.dtNow.strftime('%Y%m%d%H'))
    self.snow_ymd   = self.dtNow.strftime('%Y%m%d')
    #默认日期
    if self.step=="S4" or self.step=="S4_P":
      #默认因子日期
      dtbegin_date  = self.dtNow + datetime.timedelta(days=-365*2)
      sPbegin_year  = dtbegin_date.strftime('%Y')
      sPend_year    = self.dtNow.strftime('%Y')
      snowMD=self.dtNow.strftime('%Y%m%d')[4:]
      if("0501"<=snowMD and snowMD<="1031"):
        sPbegin_date  = sPbegin_year+"0501"
        sPend_date    = sPend_year+"1031"
      else:
        sPbegin_date  = sPbegin_year+"1101"
        sPend_date    = sPend_year+"0430"
      self.Pdr_date = sPbegin_date+"_"+sPend_date

  #参数
  def dArgs(self, sGrid_Site="Station", sPQ_type="day_max", dspt="GMOSRR system"):
    if sGrid_Site=="Station":
      s3_method="4Interpto1"
    elif sGrid_Site=="Grid":
      sPQ_type_lower=sPQ_type.lower()
      if sPQ_type_lower=="day_max" or sPQ_type_lower=="day_min":
        s3_method="MaxMin_24h"
      elif sPQ_type_lower=="hour_max" or sPQ_type_lower=="hour_min":
        s3_method="MaxMin_hourly"
      elif sPQ_type_lower=="hour_inst":
        s3_method="Interp_hourly"
    #输入参数
    parser = argparse.ArgumentParser(description=dspt)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-v"    , "--verbose"      , default=False, action="store_true") #不输入就是False, 输入就是True
    group.add_argument("-q"    , "--quiet"        , default=False, action="store_true")
    parser.add_argument("-m"   , "--model_name"   , default="EC"              , help="model name")
    parser.add_argument("-r"   , "--region"       , default="New"             , help="region name")
    parser.add_argument("-d"   , "--debug"        , default=1 , type=int      , help="debug")
    parser.add_argument("-u"   , "--update"       , default=0 , type=int      , help="update(0,1,2)")
    parser.add_argument("-p"   , "--if_period"    , default=False, action="store_true", help="date period(False)")
    parser.add_argument("-g"   , "--group"        , default=3 , type=int      , help="Grouping")
    parser.add_argument("-nf"  , "--no_fix_date"  , default=True, action="store_false", help="if fix date(00000000_00000000)")
    parser.add_argument("-opr" , "--operation"                                , help="Operation(p,t,f,o)")
    parser.add_argument("-bt"  , "--begin_time"                               , help="BJ begin time (10)") #输入程序启动时间
    parser.add_argument("-bd"  , "--begin_date"                               , help="Begin date(8)")
    parser.add_argument("-ed"  , "--end_date"                                 , help="End date(8)")
    parser.add_argument("-bh"  , "--begin_hour"               , type=int      , help="Begin hour(2)")
    parser.add_argument("-eh"  , "--end_hour"                 , type=int      , help="End hour(2)")
    parser.add_argument("-bsh" , "--begin_sub_hour"           , type=int      , help="Begin sub hour update")
    parser.add_argument("-sh"  , "--step_hour"                , type=int      , help="Step hour(2)")
    parser.add_argument("-bfh" , "--begin_fhour"              , type=int      , help="Begin forecast hour(3)")
    parser.add_argument("-efh" , "--end_fhour"                , type=int      , help="End forecast hour(3)")
    parser.add_argument("-sfh" , "--step_fhour"               , type=int      , help="Step forecast hour(2)")
    parser.add_argument("-fbd" , "--fbegin_date"                              , help="Forecast Begin date(8)")
    parser.add_argument("-roh" , "--rain_ohour"               , type=int      , help="Precipitation Observation hour(24)")
    parser.add_argument("-s3m" , "--s3_method"    , default=s3_method         , help="S3 method name")
    parser.add_argument("-s4m" , "--s4_method"    , default=None              , help="S4 method name")
    parser.add_argument("-s4p" , "--s4_pdate"                                 , help="S4 predictor date")
    parser.add_argument("-s5b" , "--s5_blend"     , default=None, type=int    , help="S5 blending class")
    parser.add_argument("-sn"  , "--site_name"    , default="Station1"        , help="Station file name")
    parser.add_argument("-gn"  , "--grid_name"                                , help="Grid file name")
    parser.add_argument("-syx" , "--sv_yx"        , default=False, action="store_true", help="Save YX")
    parser.add_argument("-iph" , "--in_path"                                  , help="Input path")
    parser.add_argument("-oph" , "--out_path"                                 , help="Output path")
    parser.add_argument("-obn" , "--obs_name"                                 , help="Obs name(Temperature...)")
    parser.add_argument("-obt" , "--obs_type"                                 , help="Obs type(Day_Max Hour_Inst...)")
    parser.add_argument("-pnt" , "--pq_name_type"                             , help="Obs name type(Temperature_Day_Max Temperature_Hour_Inst...)")
    parser.add_argument("-dmd" , "--delete_model" , default=False, action="store_true" , help="delete model")
    parser.add_argument("-ndel", "--no_delete"    , default=False, action="store_true" , help="no delete file")
    parser.add_argument("-prf" , "--para_file"                                         , help="parameter file")
    parser.add_argument("-cg"  , "--cpu_gpu"      , default=None, type=int             , help="CPU(0),GPU(1,2,3,...)")
    parser.add_argument("-thr" , "--threads"      , type=int                           , help="number of threads")
    parser.add_argument("-fo"  , "--force_out"    , default=0   , type=int             , help="force_out(0,1)")     #强制数据输出(其他=0,无最新实况时输出=1)    
    args = parser.parse_args()
    if args.operation==None:
      args.operation="o"
    #调试信息
    if args.verbose==True:
      args.debug=2
    elif args.quiet==True:
      args.debug=0
    else:
      if args.debug is None:
        args.debug=1
    #cpu_gpu
    if args.cpu_gpu is not None:
      if args.cpu_gpu<0:args.cpu_gpu=-1
    #起报时间
    if args.begin_hour is None:
      if self.step=="S2_OBS":
        args.begin_hour=self.inow_hour
      else:
        if self.inow_hour<=12:
          args.begin_hour=20
        else:
          args.begin_hour=8
    args.sbegin_hour  = "%02d"%args.begin_hour
    #结束时间
    if args.end_hour is None:
      args.end_hour = args.begin_hour
    args.send_hour = "%02d"%args.end_hour
    #起报时间步长
    if args.step_hour is not None:
      args.sstep_hour   = "%02d"%args.step_hour
    #开始预报时效
    if args.begin_fhour is None:
      args.begin_fhour = 0
    args.sbegin_fhour = "%03d"%args.begin_fhour
    #结束预报时效
    if args.end_fhour is None:
      args.end_fhour = 240
    args.send_fhour   = "%03d"%args.end_fhour
    #预报时效步长
    if args.step_fhour is None:
      args.step_fhour = 1
    args.sstep_fhour = "%03d"%args.step_fhour
    #滚动订正的预报开始
    if args.begin_sub_hour is None:
      ibegin_sub_hour=self.inow_hour-args.begin_hour
      if ibegin_sub_hour<0: ibegin_sub_hour=ibegin_sub_hour+24
      args.begin_sub_hour = ibegin_sub_hour
    args.sbegin_sub_hour  = "%02d"%args.begin_sub_hour
    #日期默认设定
    if args.begin_date is None:
      if self.step=="S2_OBS":
        args.begin_date=self.dtNow.strftime('%Y%m%d')
        args.end_date  = args.begin_date
      elif self.step=="S4":
        iday=math.ceil(args.end_fhour/24)
        dtbegin_date    = self.dtNow - datetime.timedelta(days=30+iday) 
        dtend_date      = self.dtNow - datetime.timedelta(days=iday)
        args.begin_date = dtbegin_date.strftime('%Y%m%d')
        args.end_date   = dtend_date.strftime('%Y%m%d')
      elif self.step=="S4_P":
        ltPdr_date=self.Pdr_date.split("_")
        args.begin_date = ltPdr_date[0]
        args.end_date   = ltPdr_date[1]
      else:
        if args.begin_hour==20:
          dtend_date = self.dtNow + datetime.timedelta(days=-1)
          args.begin_date=dtend_date.strftime('%Y%m%d')
          args.end_date  = args.begin_date
        else:
          args.begin_date=self.dtNow.strftime('%Y%m%d')
          args.end_date  = args.begin_date
    args.sbegin_date=str(args.begin_date)
    args.send_date=str(args.end_date)
    if args.rain_ohour is None:
      args.rain_ohour=24
    args.srain_ohour="%02d"%args.rain_ohour
    #第2步使用
    #实况名
    ltPQname=["Temperature","Relative_Humidity","Wind","Precipitation","Total_Cloud","Visibility"]
    if args.obs_name is None:
      args.obs_name = ltPQname
    else:
      args.obs_name = [args.obs_name]
    #实况类型
    ltPQ_type=["Day_Max", "Day_Min", "Hour_Inst", "Hour_Min", "Hour_01Accu"]
    if args.obs_type is None:
      args.obs_type = ltPQ_type
    else:
      args.obs_type = [args.obs_type]
    #实况信息汇总
    dtObs_info={}
    for sname in args.obs_name:
      for stype in args.obs_type:
        if ((stype in ["Day_Max","Day_Min","Hour_Inst"]) and (sname in ["Temperature","Relative_Humidity","Wind"])) or \
           ((stype in ["Hour_Inst"]) and (sname in ["Total_Cloud"])) or \
           ((stype in ["Hour_01Accu"]) and (sname in ["Precipitation"])) or \
           ((stype in ["Hour_Min"]) and (sname in ["Visibility"])) :
          if sname in dtObs_info:
            dtObs_info[sname].append(stype)
          else:
            dtObs_info[sname]=[stype]
    args.obs_info = dtObs_info
    return args
    
    
  #参数
  def dArgs_model(self, time_type="hour", dspt="GMOSRR system", gs_type="grid"):
    time_type = time_type.lower()
    #输入参数
    parser = argparse.ArgumentParser(description=dspt)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-v"    , "--verbose"      , action="store_true") #不输入就是False, 输入就是True
    group.add_argument("-q"    , "--quiet"        , action="store_true")
    parser.add_argument("-d"   , "--debug"        , default=1, type=int , help="debug")
    parser.add_argument("-u"   , "--update"       , default=0, type=int , help="update data")
    parser.add_argument("-p"   , "--if_period"    , default=False, action="store_true", help="date period(False)")
    parser.add_argument("-g"   , "--group"        , default=3, type=int , help="Grouping")
    parser.add_argument("-m"   , "--model_name"   , default="EC"        , help="model_name")
    parser.add_argument("-r"   , "--region"       , default="New"       , help="region name")
    parser.add_argument("-nf"  , "--no_fix_date"  , default=True, action="store_false", help="if fix date(00000000_00000000)")
    parser.add_argument("-syx" , "--sv_yx"        , default=False, action="store_true", help="Save YX")
    parser.add_argument("-mdl" , "--model"                              , help="run modeling(p,t,o)")
    parser.add_argument("-frt", "--frst"                                , help="run modeling(f,o)")
    parser.add_argument("-psn" , "--pseason"        , type=int          , help="Predictor season")
    parser.add_argument("-pbd" , "--pbegin_date"                        , help="Predictor Begin date(8)")
    parser.add_argument("-ped" , "--pend_date"                          , help="Predictor End date(8)")
    parser.add_argument("-tbd" , "--tbegin_date"                        , help="Train Begin date(8)")
    parser.add_argument("-ted" , "--tend_date"                          , help="Train End date(8)")
    parser.add_argument("-fbd" , "--fbegin_date"                        , help="Forecast Begin date(8)")
    parser.add_argument("-fed" , "--fend_date"                          , help="Forecast End date(8)")    
    parser.add_argument("-bh"  , "--begin_hour"     , type=int          , help="Begin hour(2)")
    parser.add_argument("-bsh" , "--begin_sub_hour" , type=int          , help="Begin hour hourly update")    
    parser.add_argument("-bfh" , "--begin_fhour"    , type=int          , help="Begin forecast hour(3)")
    parser.add_argument("-efh" , "--end_fhour"      , type=int          , help="End forecast hour(3)")
    parser.add_argument("-fhs" , "--fhour_span"     , type=int          , help="forecast hour span(3)")
    parser.add_argument("-s3m" , "--s3_method"                          , help="S3 method name")
    parser.add_argument("-s4p" , "--s4_pdate"                           , help="S4 Predictor date")
    parser.add_argument("-s5b" , "--s5_blend", default=None, type=int   , help="S5 blending class")
    parser.add_argument("-sn"  , "--site_name"                          , help="Station file name")
    parser.add_argument("-gn"  , "--grid_name"                          , help="Grid file name")
    parser.add_argument("-del" , "--delete"       , default=True , action="store_false", help="Delete file")
    parser.add_argument("-dmd" , "--delete_model" , default=False, action="store_true" , help="delete model")
    parser.add_argument("-rh"  , "--run_hour"     , default=12   ,type=int, help="run hour threshold(20:t<(12)<=t:08)")
    parser.add_argument("-eh1h", "--end_hour_1h"                         , help="1 hourly end forecast hour")
    parser.add_argument("-eh3h", "--end_hour_3h"                         , help="3 hourly end forecast hour")
    parser.add_argument("-eh6h", "--end_hour_6h"                         , help="6 hourly end forecast hour")
    parser.add_argument("-mtdays", "--mtrain_days" , type=int            , help="Moving Train days")
    parser.add_argument("-thr"   , "--threads"     , type=int            , help="number of threads")
    parser.add_argument("-udagr" , "--def_agrs"                          , help="user define argumet")
    parser.add_argument("-cg"    , "--cpu_gpu"     , default=None, type=int , help="CPU(0),GPU(1,2,3,...)")
    args = parser.parse_args()
    #调试信息
    if args.verbose==True:
      args.debug=2
    elif args.quiet==True:
      args.debug=0
    #cpu_gpu
    if args.cpu_gpu is not None:
      if args.cpu_gpu<0:args.cpu_gpu=-1
    #运行类型
    if args.model is None:
      if gs_type.lower()=="station":
        args.model=["p","t"]
      else:
        args.model=["t"]
    else:
      args.model = [args.model]
    if "o" in args.model : 
      if args.debug is None: args.debug=0
    #开始预报时效
    if args.begin_fhour is None:
      if time_type=="day":
        args.begin_fhour=12
      elif time_type=="moving_day":
        args.begin_fhour=12
      elif time_type=="hour": #不滚动
        args.begin_fhour=12
      elif time_type=="moving_hour":
        args.begin_fhour=1
    #结束预报时效
    if args.end_fhour is None:
      if time_type=="day":
        args.end_fhour=252
      elif time_type=="moving_day":
        args.end_fhour=36
      elif time_type=="hour": #不滚动
        args.end_fhour=252
      elif time_type=="moving_hour":
        args.end_fhour=24
    #站点名
    if args.site_name is None:
      args.site_name="Station1"
    #1h/3h/6h结束时效
    if args.end_hour_1h is None:
      args.end_hour_1h=36          #1h间隔预报结束时效
    if args.end_hour_3h is None:
      args.end_hour_3h=252         #3h间隔预报结束时效
    if args.end_hour_6h is None:
      if args.end_hour_3h==252:    #6h间隔预报结束时效
        args.end_hour_6h=360
      else:
        args.end_hour_6h=252
    if args.end_hour_3h==args.end_hour_6h:
      args.end_hour_6h = args.end_hour_3h+24
    #滑动训练日期
    if args.mtrain_days is None:
      args.mtrain_days=30
    if args.def_agrs is None:
      args.def_agrs=""
    return args

  #参数
  def dArgs_S1_DL(self, pyfile_name=None, dspt="MOSRR system", sModel_info=None):
    if pyfile_name==None:
      spara_file_name="Download_XXZX.ini"
    else:
      spara_file_name=pyfile_name.rsplit('.', 1)[0]+".ini"
    #grapes_meso的起报时效
    ltMESO_hours=[2,5,8,11,14,17,20,23]
    iN_meso_hour=len(ltMESO_hours)
    #输入参数
    parser = argparse.ArgumentParser(description=dspt)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-v"    , "--verbose"      , default=False, action="store_true") #不输入就是False, 输入就是True
    group.add_argument("-q"    , "--quiet"        , default=False, action="store_true")
    parser.add_argument("-d"   , "--debug"        , default=1, type=int , help="debug")
    parser.add_argument("-p"   , "--if_period"    , default=False, action="store_true" ,  help="date period(False)")
    parser.add_argument("-dl"  , "--download"     , default=True  , action="store_false",  help="download(True)")
    parser.add_argument("-cp"  , "--copy"         , default=False , action="store_true" ,  help="copy(True)")
    parser.add_argument("-dp"  , "--decomp"       , default=False, action="store_true" ,  help="decompression(False)")
    parser.add_argument("-rn"  , "--rename"       , default=False, action="store_true" ,  help="rename(False)")
    parser.add_argument("-ol"  , "--out_log"      , default=False, action="store_true" ,  help="output log(False)")
    parser.add_argument("-ndel", "--no_delete"    , default=True , action="store_false",  help="no delete raw file(True)")
    parser.add_argument("-thd" , "--thread"       , default=3    , type=int            ,  help="thread(3)")
    parser.add_argument("-s1dir", "--has_s1_dir"  , default=True , action="store_false",  help="if mkdir 1down_load dir(True)")
    parser.add_argument("-bd"  , "--begin_date"                               , help="Begin date(8)")
    parser.add_argument("-ed"  , "--end_date"                                 , help="End date(8)")
    parser.add_argument("-bh"  , "--begin_hour"   , type=int                  , help="Begin hour(2)")
    parser.add_argument("-eh"  , "--end_hour"     , type=int                  , help="End hour(2)")
    parser.add_argument("-bfh" , "--begin_fhour"  , default=0   , type=int    , help="Begin forecast hour(3)")
    parser.add_argument("-efh" , "--end_fhour"    , default=240 , type=int    , help="End forecast hour(3)")
    parser.add_argument("-fn"  , "--file_name"    , default=spara_file_name   , help="parameter file name")
    parser.add_argument("-rh"  , "--run_hour"     , default=12  , type=int    , help="run hour threshold(20:t<(12)<=t:08)")
    args = parser.parse_args()
    #inow_try=11
    #调试信息
    if args.verbose==True:
      args.debug=2
    elif args.quiet==True:
      args.debug=0
    else:
      if args.debug is None:
        args.debug=1
    #模式信息
    if sModel_info!=None:
      sModel_info=sModel_info.lower()
    #不同模式参数不一样
    if sModel_info=="grapes_gfs":
      pass
    else:
      #开始时效
      if args.begin_hour is None:
        #1天两次的开始时效
        if self.inow_hour<args.run_hour:
          args.begin_hour=20
        else:
          args.begin_hour=8
        if args.end_hour is None:
          args.end_hour=args.begin_hour
          args.send_hour = "%02d"%args.end_hour
      args.sbegin_hour = "%02d"%args.begin_hour
      #预报开始/结束时效
      if args.begin_fhour is not None:
        args.sbegin_fhour = "%03d"%args.begin_fhour
      if args.end_fhour  is not None:
        args.send_fhour   = "%03d"%args.end_fhour
      #日期默认设定
      if args.begin_date is None:
        #1天两次预报
        if args.begin_hour==20:
          dtend_date = self.dtNow + datetime.timedelta(days=-1)
          args.begin_date=dtend_date.strftime('%Y%m%d')
          args.end_date  = args.begin_date
        else:
          args.begin_date=self.dtNow.strftime('%Y%m%d')
          args.end_date  = args.begin_date
    return args
    



    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    