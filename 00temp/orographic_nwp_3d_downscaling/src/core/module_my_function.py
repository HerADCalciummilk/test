# -*- coding: utf-8 -*- 
# cython:language_level=3


import os
import re
import sys
import pytz
import glob
import time
import math
import datetime
import calendar
import dateutil.relativedelta
from dateutil import tz
import itertools


try:
  from scipy.stats import truncnorm
except ImportError:
  print("no install scipy")
  linstall = None
  
#导入外库
try:
  import numpy as np
except ImportError:
  print("no install numpy")
  linstall = None


class Class_MyFunction(object):

  "初始化函数"
  def __init__(self, iDebug = 0):
    self.iDebug = iDebug  #0:调试, 1:业务
    #当前工作路径
    self.SCurrent_Path=os.getcwd()
    if(self.iDebug >= 1): print("now Path:",self.SCurrent_Path)
    #当前时间
    self.sTodayDate="".join(time.strftime('%Y%m%d',time.localtime(time.time())))
    if(self.iDebug >= 1): print("Today:",time.ctime())
    #开始运行时间
    self.dt_start_time = datetime.datetime.now()

  def str2bool(self, sIn_str):
    return sIn_str.lower() in ("yes", "true", "t", "1")
  
  #产生某个范围内的高斯分布
  def get_truncated_normal(self, mean=0, sd=1, low=0, upp=10):
    return truncnorm((low - mean) / sd, (upp - mean) / sd, loc=mean, scale=sd)
      
  '''获取文件的大小,结果保留两位小数,单位为MB'''
  def dGet_FileSize(self, filePath):
    filePath = filePath.encode('utf8')
    fsize = os.path.getsize(filePath)
    #M
    fsize = fsize/float(1024*1024)
    sunit="M"
    #G
    if fsize>=1024:
      fsize = fsize/float(1024)
      sunit="G"
    return round(fsize,2),sunit
        
  #uv风合成实际风
  def dmulti_run_UV2Wind(self, args):
    return self.dWind2UV(*args)
  def dUV2Wind(self,fU,fV):
    fspd=math.sqrt(fU**2+fV**2)
    tmp=270.0-math.atan2(fV,fU)*180.0/math.pi
    fdir=math.fmod(tmp,360.0)
    return fdir,fspd
  #数组版
  def dUV_to_Wind(self,ndyU,ndyV):
    ndyspd=np.sqrt(ndyU**2+ndyV**2)
    tmp=270.0-np.arctan2(ndyV,ndyU)*180.0/np.pi
    ndydir=np.fmod(tmp,360.0)
    return ndydir,ndyspd


  #实际风分解成uv风
  def dmulti_run_Wind2UV(self, args):
    return self.dWind2UV(*args)
  def dWind2UV(self, Rdir, Rspd):
    if Rspd<=0.0 or Rdir>360.0:
      fU = 0.0
      fV = 0.0
      return fU, fV
    else:
      tmp=(270-Rdir)*math.pi/180.0
      fV=Rspd*math.sin(tmp)
      fU=Rspd*math.cos(tmp)
      return fU, fV
  
  def dWind_to_UV(self, ndydir, ndyspd):
    ndytmp=(270-ndydir)*np.pi/180.0
    ndyV=ndyspd*np.sin(ndytmp)
    ndyU=ndyspd*np.cos(ndytmp)
    return ndyU,ndyV
    
    
  #找到某个类型的所有文件(通配符为*)
  def dfindfiles(self, dirname, pattern, key=os.path.getmtime, reverse=True):
    '''
    dirname 文件夹路径
    pattern 文件类型(带通配符)
    key     排序方式 os.path.getmtime
    reverse 是否倒序
    '''
    cwd = os.getcwd() #保存当前工作目录
    if dirname:
        os.chdir(dirname)
    result = []
    for filename in sorted(glob.iglob(pattern), key=key, reverse=reverse): #此处可以用glob.glob(pattern) 返回所有结果
        result.append(filename)
    #恢复工作目录
    os.chdir(cwd)
    return result
  
  
  #找到某个类型的所有文件(通配符为*)
  def dfind_files(self, path, exp):
    m = re.compile(exp)
    ltresult  = [f for f in os.listdir(path) if m.match(f)]
    #ltresult=[]
    #for filename in glob.iglob(spattern):
    #  ltresult.append(filename)
    return ltresult  
      
  #打印运行时间
  def dPrint_run_time(self):
    #程序运行结束时间
    dt_end_time = datetime.datetime.now()
    #时间差(分)
    tdiff = dateutil.relativedelta.relativedelta (dt_end_time, self.dt_start_time)
    print("%d hours, %d minutes %d seconds"%(tdiff.hours, tdiff.minutes, tdiff.seconds))
    
  #季节  
  def dSeason(self, imonth, lNorY):
    #按自然节气划分
    if lNorY==True:
      if imonth in [12,1,2]:
          return 4
      elif imonth in [3,4,5]:
          return 1
      elif imonth in [6,7,8]:
          return 2
      elif imonth in [9,10,11]:
          return 3
      else:
          return "error"
    #按年份划分
    else:
      if imonth in [1,2,3]:
          return 1
      elif imonth in [4,5,6]:
          return 2
      elif imonth in [7,8,9]:
          return 3
      elif imonth in [10,11,12]:
          return 4
      else:
          return "error"    
    
  #获取两个日期间所有月份
  def dget_month_range(self, start_day, end_day):
    months = (end_day.year - start_day.year)*12 + end_day.month - start_day.month
    month_range = ['%s-%s'%(start_day.year + mon//12,mon%12+1) 
                      for mon in range(start_day.month-1,start_day.month + months)]
    return month_range
    
  #找出每个月的开始结束日期
  def dmonths_BE_dates(self, sbegin_date, send_date, if_period=0):
    ltdate=self.ddates_between_two_date(sbegin_date, send_date, if_period)
    ltmonths_BE=[]; ltYM=[]
    for sdate in ltdate:
      if sdate[0:6] in ltYM: continue
      dtdate=datetime.datetime.strptime(sdate, "%Y%m%d")
      ltm_BE=[self.dfirst_day_of_month(dtdate),self.dlast_day_of_month(dtdate)]
      if ltm_BE not in ltmonths_BE:
        ltmonths_BE.append(ltm_BE) #时间段tuple列表
    ltmonths_BE[0][0]=sbegin_date
    ltmonths_BE[-1][-1]=send_date
    return ltmonths_BE

  #当前日期前的几个月是哪个月
  def dMonths_Ago(self, iN_Ago):
    iNow_Month = time.localtime()[1]-iN_Ago
    iNow_Year  = time.localtime()[0]  
    if(iNow_Month<=0):
      iNow_Month = iNow_Month + 12
      iNow_Year  = iNow_Year -1
    return str("%04d"%iNow_Year) + "-" + str("%02d"%iNow_Month)    
    
  #闰年
  def dis_leap_year(self,year):
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)    
  
  #获得日序
  def dYearday(self,sdate, sformat="%Y%m%d"):
    return datetime.datetime.strptime(sdate,sformat).timetuple().tm_yday
  
  # #两个时间间隔之间的所有时间(最小是小时)(输入10位日期)
  # def dDates_2Time(self, sStart_Date, sEnd_Date, finterval_h=1):
    # #分割日期
    # iStart_Year, iStart_Month, iStart_Day, iStart_Hour = self.dYMDH_split(sStart_Date)
    # iEnd_Year  , iEnd_Month  , iEnd_Day  , iEnd_Hour   = self.dYMDH_split(sEnd_Date)
    # #日期转换
    # dstart_date = datetime.datetime(iStart_Year, iStart_Month, iStart_Day, iStart_Hour)
    # dend_date = datetime.datetime(iEnd_Year , iEnd_Month , iEnd_Day)
  
    # dstart_date + datetime.timedelta(days = iday)

  #日序转换为日期
  def ddaynumber_to_date(self, iyear, idaynumber):
    return datetime.datetime(iyear, 1, 1) + datetime.timedelta(idaynumber-1)
  
  #两个日期之间的所有日期和天数
  def ddates_between_2date(self, sStart_Date, sEnd_Date):
    #分割日期
    iStart_Year, iStart_Month, iStart_Day, \
    iEnd_Year , iEnd_Month , iEnd_Day = self.ddate_split_2(sStart_Date, sEnd_Date)
    #日期转换
    dstart_date = datetime.datetime(iStart_Year, iStart_Month, iStart_Day)
    dend_date   = datetime.datetime(iEnd_Year  , iEnd_Month  , iEnd_Day)
    #间隔天数
    iN_days = (dend_date - dstart_date).days + 1 #inclusive 5 days
    #之间日期
    ltall_dates=[]
    for iday in range(iN_days):
      ltall_dates.append((dstart_date + datetime.timedelta(days = iday)).date().strftime("%Y%m%d"))
    return ltall_dates
  
  
  #两个日期之间的所有日期和天数(带有分段和不分段参数)
  def ddates_between_two_date(self, sStart_Date, sEnd_Date, if_period):
    """
    sStart_Date : 开始日期YMD
    sEnd_Date   : 结束日期YMD
    if_period   : 是否周期型(True/1:分段,False/0:连续)
    """
    #简单检查日期
    if sStart_Date>sEnd_Date: return []
    #分割日期
    iStart_Year, iStart_Month, iStart_Day, \
    iEnd_Year , iEnd_Month , iEnd_Day = self.ddate_split_2(sStart_Date, sEnd_Date)
    #月日和
    iStart_MD = iStart_Month*100+iStart_Day
    iEnd_MD   = iEnd_Month*100+iEnd_Day
    #分段(不连续)
    if (if_period==True):
      #结束月日>=开始月日
      if iEnd_MD>=iStart_MD:
        #年循环
        ltout_date = []
        for iy in range(iStart_Year, iEnd_Year+1):
          #非闰年出现2月29问题
          if not self.dis_leap_year(iy):
            iStart_MD_other = iStart_MD
            iEnd_MD_other   = iEnd_MD
            #月日出现
            if (iStart_Month==2 and iStart_Day>=29):
              iStart_MD_other=228
            if (iEnd_Month==2 and iEnd_Day>=29):
              iEnd_MD_other=228
          else:  
            iStart_MD_other = iStart_MD
            iEnd_MD_other   = iEnd_MD
          sin_start_date = str(iy) + str("%04d"%iStart_MD_other)
          sin_end_date   = str(iy) + str("%04d"%iEnd_MD_other)
          ltout_date = ltout_date + self.ddates_between_2date(sin_start_date, sin_end_date)
        return ltout_date
      #结束月日<开始月日
      else:
        #年循环
        ltout_date = []
        for iy in range(iStart_Year, iEnd_Year+1):
          #非闰年出现2月29问题
          if not self.dis_leap_year(iy):
            iStart_MD_other = iStart_MD
            iEnd_MD_other   = iEnd_MD          
            #月日出现
            if (iStart_Month==2 and iStart_Day>=29):
              iStart_MD_other=228
            if (iEnd_Month==2 and iEnd_Day>=29):
              iEnd_MD_other=228
          else:  
            iStart_MD_other = iStart_MD
            iEnd_MD_other   = iEnd_MD
          if iy==iStart_Year:
            sin_start_date = str(iy) + str("%04d"%iStart_MD_other)
            sin_end_date = str(iy) + "1231"
            ltout_date = ltout_date + self.ddates_between_2date(sin_start_date, sin_end_date)
            continue
          elif iy==iEnd_Year:
            sin_start_date = str(iy) + "0101"
            sin_end_date = str(iy) + str("%04d"%iEnd_MD_other)
            ltout_date = ltout_date + self.ddates_between_2date(sin_start_date, sin_end_date)
            continue
          else:
            sin_start_date = str(iy) + "0101"
            sin_end_date = str(iy) + str("%04d"%iEnd_MD_other)
            ltout_date = ltout_date + self.ddates_between_2date(sin_start_date, sin_end_date)          
            sin_start_date = str(iy) + str("%04d"%iStart_MD_other)
            sin_end_date = str(iy) + "1231"
            ltout_date = ltout_date + self.ddates_between_2date(sin_start_date, sin_end_date)
        return ltout_date
    #连续日期
    else:
      ltout_date = self.ddates_between_2date(sStart_Date, sEnd_Date)
      return ltout_date
  
  #两日期小时之间所有带小时的
  def ddateHours_in_2DH(self, sYMDH_begin, sYMDH_end, if_period=0, step_hour=1):
    """
    sYMDH_begin : YYYYMMDDHH 开始日期
    sYMDH_end   : YYYYMMDDHH 结束日期
    if_period   : 是否周期型(True/1:分段,False/0:连续)
    step_hour   : 分辨率步长(hour)
    """
    dtdate_hour_begin = datetime.datetime.strptime(sYMDH_begin, "%Y%m%d%H")
    dtdate_hour_end   = datetime.datetime.strptime(sYMDH_end  , "%Y%m%d%H")
    in_hours          = self.ddate_diff_hours(dtdate_hour_end ,dtdate_hour_begin)
    #月日和
    iStart_MDH = dtdate_hour_begin.month*10000+dtdate_hour_begin.day*100+dtdate_hour_begin.hour
    iEnd_MDH   = dtdate_hour_end.month*10000+dtdate_hour_end.day*100+dtdate_hour_end.hour
    ltdate_hours=[]
    for i in range(0,int(in_hours)+1,step_hour):
      dtdatehour=dtdate_hour_begin + datetime.timedelta(hours=i)
      #不连续(分段1/True)
      if (if_period==True or if_period>=1):
        ieach_MDH=dtdatehour.month*10000+dtdatehour.day*100+dtdatehour.hour
        #结束月日>=开始月日(同年)
        if iStart_MDH<=iEnd_MDH:
           if iStart_MDH<=ieach_MDH and ieach_MDH<=iEnd_MDH:
             sdate_hours=dtdatehour.strftime("%Y%m%d%H")
             ltdate_hours.append(sdate_hours)
             continue
        #结束月日<开始月日(跨年)
        else:
           if (iStart_MDH<=ieach_MDH and ieach_MDH<=1231) or (101<=ieach_MDH and ieach_MDH<=iEnd_MDH):
             sdate_hours=dtdatehour.strftime("%Y%m%d%H")
             ltdate_hours.append(sdate_hours)
             continue
      #连续日期(0/False))
      else:
        sdate_hours=dtdatehour.strftime("%Y%m%d%H")
        ltdate_hours.append(sdate_hours)
    return ltdate_hours
  
  
  #计算几天或几个时效的日期
  def dtimes_ago(self, sdate, iN_time_ago, day_hour="day", sformat="%Y%m%d", return_str=True):
    if day_hour=="day":
      dtdate_ago = datetime.datetime.strptime(sdate,sformat)-datetime.timedelta(days=iN_time_ago)
    else:
      dtdate_ago = datetime.datetime.strptime(sdate,sformat)-datetime.timedelta(hours=iN_time_ago)
    #返回字符串
    if return_str:
      sdate_ago=dtdate_ago.strftime(sformat)
      return sdate_ago
    else:
      return dtdate_ago


  #按照年成组 (返回的年序号从0开始)
  def ddates_Year_Group(self, ltdates, format="%Y%m%d"):
    #年数
    ibegin_year = int(ltdates[0][0:4])
    in_years    = int(ltdates[-1][0:4])-ibegin_year+1
    ltyears     = [str(ibegin_year+i) for i in range(in_years)]
    ltrlt_dates = [[] for i in range(in_years)]
    ltrlt_dayth = [[] for i in range(in_years)]
    for sdate in ltdates:
      idx = int(sdate[0:4])-ibegin_year
      ltrlt_dates[idx].append(sdate)
      ltrlt_dayth[idx].append(datetime.datetime.strptime(sdate,format).timetuple()[7]-1)
    return ltrlt_dates, ltrlt_dayth, ltyears
  
  #每个月最后1天
  def dlast_day_of_month(self, any_day, format="%Y%m%d"):
    """
    获取获得一个月中的最后一天
    :param any_day: 任意日期
    :return: string
    """
    next_month = any_day.replace(day=28) + datetime.timedelta(days=4)  # this will never fail
    return self.datetime_toString(next_month - datetime.timedelta(days=next_month.day), format)
  
  
  #每个月第1天
  def dfirst_day_of_month(self, any_day, format="%Y%m%d"):
    """
    获取获得一个月中的最后一天
    :param any_day: 任意日期
    :return: string
    """
    return self.datetime_toString(datetime.date(any_day.year, any_day.month, 1), format)
  
  #把datetime转成字符串
  def datetime_toString(self, dt, format="%Y%m%d %H:%M:%S"):
    return dt.strftime(format)

  #某年有多少天 = 1年天数
  def dyear_days(self, iyear):
    return 366 if calendar.isleap(iyear) else 365
  
  #某年某个月有多少天 = 1月天数
  def dmonth_days(self, iyear, imonth):
    return calendar.monthrange(iyear, imonth)[1]  
  
  
  #按照年成组
  def ddates_Year_Group2(self, ltdates):
    #年数
    ibegin_year = int(ltdates[0][0:4])
    in_years    = int(ltdates[-1][0:4])-ibegin_year+1
    ltyears     = [str(ibegin_year+i) for i in range(in_years)]
    ltrlt_dates = [[] for i in range(in_years)]
    for sdate in ltdates:
      idx = int(sdate[0:4])-ibegin_year
      ltrlt_dates[idx].append(sdate)
    return ltrlt_dates, ltyears  
  
  
  #将1个整数分解成两个整数相乘(int=行×列)
  def dint_decomposed(self, inum):
    irow=math.ceil(math.sqrt(inum))
    icol=math.ceil(inum/irow)
    return (irow,icol)
  
  
  #重组列表
  def dReform_List(self, ltRaw, iN=1):
    #检查参数
    if iN<=0:
      return [ltRaw]
    return [ltRaw[x:x+iN] for x in range(0, len(ltRaw), iN)]
  
  
  def split_seq(self, iterable, size):
      it = iter(iterable)
      item = list(itertools.islice(it, size))
      while item:
          yield item
          item = list(itertools.islice(it, size))

  def grouplen(self, sequence, chunk_size):
    return list(zip(*[iter(sequence)] * chunk_size))
          
  #列表分组
  def dGrouping(self, ltRaw, iN_g=1):
    #检查参数
    if iN_g<=1:
      return [ltRaw]
    iN_sample  = len(ltRaw) #样本数
    if(iN_g>=iN_sample):
      return [ltRaw[x:x+1] for x in range(0, iN_sample)]
    else:
      (iN_each_gp, remainder) = divmod(iN_sample,iN_g)
      if iN_each_gp>=2:  #每组2个以上的情况
        if remainder>iN_each_gp:
          return list(self.split_seq(ltRaw, iN_each_gp+1))
        else:
          return list(self.split_seq(ltRaw, iN_each_gp+remainder))
      else:
        #有remainder个剩余,等同于添加到头部remainder的每一个中
        return [ltRaw[x:x+2] for x in range(0,remainder*2,2)] + \
               [ltRaw[x:x+1] for x in range(remainder*2,iN_sample)]
        
  #判断是否是一个有效的日期字符串
  def dis_valid_date(self,str):
    try:
      time.strptime(str, "%Y-%m-%d")
      return True
    except:
      return False

  "1个10位日期分割"
  def dYMDH_split(self,sYMDH):
    iBegin_Year,iBegin_Month,iBegin_Day,iBegin_Hour = self.ddate_hour_split_1(sYMDH)
    return iBegin_Year, iBegin_Month, iBegin_Day, iBegin_Hour

      
  "2个8位日期分割"
  def ddate_split_2(self,sFrom_Date,sEnd_Date):
    #起始年月
    iFrom_Year,iFrom_Month,iFrom_Day = self.ddate_split_1(sFrom_Date)
    #结束年月
    iEnd_Year,iEnd_Month,iEnd_Day = self.ddate_split_1(sEnd_Date)
    return iFrom_Year, iFrom_Month, iFrom_Day, \
           iEnd_Year , iEnd_Month , iEnd_Day


  "1个8位日期分割"
  def ddate_split_1(self,sDate):
     #起始年月
    iYear=int(sDate[0:4])
    iMonth=int(sDate[4:6])
    iDay=int(sDate[6:8])
    return iYear, iMonth, iDay


  "1个10位日期分割"
  def ddate_hour_split_1(self,sDate):
     #起始年月
    iYear=int(sDate[0:4])
    iMonth=int(sDate[4:6])
    iDay=int(sDate[6:8])
    iHour = int(sDate[8:10])
    return iYear, iMonth, iDay, iHour

  #计算两个时间之间间隔多少个小时
  def dYMDH_diff_hours(self, sbegin_YMDH, send_YMDH, sformat="%Y%m%d%H"):
    dtbegin_YMDH = datetime.datetime.strptime(sbegin_YMDH, sformat)
    dtend_YMDH   = datetime.datetime.strptime(send_YMDH, sformat)
    ihours = int((dtend_YMDH-dtbegin_YMDH).total_seconds()/3600.0)
    return ihours

  #加上/减去n天(小时)后的日期
  def dBefAftDate2(self,sYYYYMMDDHH,sType,iNTime):
    iYear, iMonth, iDay, iHour = self.ddate_hour_split_1(sYYYYMMDDHH)
    return self.dBefAftDate(iYear,iMonth,iDay,iHour,sType,iNTime)

  #加上/减去n天(小时)后的日期
  def dBefAftDate(self,iYear,iMonth,iDay,iHour,sType,iNTime):
    if type(iNTime).__module__=='numpy':
      iN_Time=iNTime.item()
    else:
      iN_Time=iNTime
    #返回字符串
    sType = sType.lower() #都以大写
    odtFrom_Date = datetime.datetime(iYear,iMonth,iDay,iHour)
    if(sType=="day"):
      odtEndDate=odtFrom_Date+datetime.timedelta(days=iN_Time)           #前/后n天后的日期
      sodtEndDate=str(odtEndDate)[0:4]+str(odtEndDate)[5:7]+str(odtEndDate)[8:10]+str(odtEndDate)[11:13]
    elif(sType=="hour"):
      (iN_days, remainder) = divmod(iN_Time*3600,86400)
      odtEndDate=odtFrom_Date+datetime.timedelta(days=iN_days, seconds=remainder)   #np.asscalar前/后n小时后的日期 0 <= seconds < 3600*24
      sodtEndDate=str(odtEndDate)[0:4]+str(odtEndDate)[5:7]+str(odtEndDate)[8:10]+str(odtEndDate)[11:13]
    else:
      print(("错误时间类型:",sType))
      sodtEndDate=str(odtFrom_Date)[0:4]+str(odtFrom_Date)[5:7]+str(odtFrom_Date)[8:10]
    return sodtEndDate

  "更新输入文件中的参数"
  def dupdate_file_parameter(self,sfile_AbsPath, ltParameter_Row):
    #sfile_AbsPath : 文件的绝对路径
    #ltParameter_Row :[(所在行数,更新内容)]
    #读取原配置文件
    try:
      with open(sfile_AbsPath,'r') as fh:
        ltLines = fh.readlines()
    except IOError as error:
      print(error)
      return 0
    #修改数据
    ilen = len(ltLines)
    for irow, scontent in ltParameter_Row:
      if irow<=ilen:
        ltLines[irow-1] = scontent + "\n"
      else:
        ilen = len(ltLines)
        if irow>=ilen:
          ltLines.append(scontent + "\n")
    #重新写文件
    with open(sfile_AbsPath,'w') as fh:
      fh.writelines(ltLines)
    return 1

  
  "更新输入文件中的参数"
  def dupdate_Similar_list_file_parameter(self,sfile_AbsPath, ltParameter_Row):
    #sfile_AbsPath : 文件的绝对路径
    #ltParameter_Row :[起始所在行,列表个数,[列表]]
    #读取原配置文件
    try:
      with open(sfile_AbsPath,'r') as fh:
        ltLines = fh.readlines()
    except IOError as error:
      print(error)
      return 0
    #保存上半部分
    ltupper_part = ltLines[:ltParameter_Row[0]-1]
    #去除行数
    iN_delete = int(ltLines[ltParameter_Row[0]-1])
    #保存下半部分
    ltlower_part = ltLines[int(ltParameter_Row[0])+iN_delete:]
    ltwork = [sx+"\n" for sx in ltParameter_Row[2]]
    #新列表
    ltNew_Lines = ltupper_part + [str(ltParameter_Row[1])+"\n"] + ltwork + ltlower_part
    #重新写文件
    with open(sfile_AbsPath,'w') as fh:
      fh.writelines(ltNew_Lines)
    return 1
  

  "更新文件中的时间"
  def dupdate_file_today(self,sfile_AbsPath, ltDate_Row):
    #sfile_AbsPath : 文件的绝对路径
    #ltDate_Row :日期所在行数
    #读取原配置文件
    try:
      with open(sfile_AbsPath,'r') as fh:
        ltLines = fh.readlines()
    except IOError as error:
      print(error)
      return 0
    #修改数据
    for irow in ltDate_Row:
      ltLines[irow-1] = self.STodayDate + "\n"
    #重新写文件
    with open(sfile_AbsPath,'w') as fh:
      fh.writelines(ltLines)
    return 1

    
  #删除Fortran程序的注释
  def dDelte_Fortran_Annotation(self, sType, SInPut_Abs_Path , ltOut_File_Path_Name):
    if sType == ".f90" :
      sAnnotation_symbol = "!"
    elif sType == ".py" :
      sAnnotation_symbol = "#"
    else:
      return 0
    ltsource_lines = []
    #读取程序
    try:
      with open(SInPut_Abs_Path,'r') as fh:
        if sType == ".f90" or sType == ".py" :
          for seach_line in fh:
            ibeg = seach_line.find(sAnnotation_symbol)
            if ibeg == -1:
              ltsource_lines.append(seach_line)
            else:
              if (seach_line[0:ibeg].strip() != "" ):
                ltsource_lines.append(seach_line[0:ibeg]+"\n")
        elif sType == ".bat" :
          for seach_line in fh:
            ltsource_lines.append(seach_line)
    except IOError as error:
      print(error)
      return 0
    #输出程序
    if not os.path.exists(ltOut_File_Path_Name[0]):
      os.makedirs(ltOut_File_Path_Name[0])
    with open(os.path.join(ltOut_File_Path_Name[0],ltOut_File_Path_Name[1]),'w') as fh:
      for each in ltsource_lines:
        fh.write(each)
    return 1
  
  
  #aix判断当前用户中某个进程是否在运行
  def dIF_Program_Running(self,User_name,Program_name):
    #获得当前用户目前启动的进程
    scommands = "ps -ef|grep "+User_name.strip()+"|grep "+ Program_name.strip()+"|wc -l"
    fh = os.popen(scommands)
    iNum_lines = int(fh.readline())
    fh.close()
    if(self.iDebug >= 1):
      scommands = "ps -ef|grep "+User_name.strip()+"|grep "+ Program_name.strip()
      fh = os.popen(scommands)
      ltresult = fh.readlines()
      fh.close()
      if(len(ltresult)>1):
        for i,x in enumerate(ltresult):
          print((i,x))
    return iNum_lines
  
  
  '''读取参数文件'''
  def dRead_list_file_ini(self, SIn_Abs_path):
    try:
       with open(SIn_Abs_path,'r') as fh:
         iNum = int(fh.readline().split()[0])
         ltwork = []
         for i in range(iNum):
           ltwork.append( fh.readline().split("\n")[0])
    except IOError as error:
       print(("No "+SIn_Abs_path + ":",error))
       sys.exit()
    return iNum, ltwork
  
  
  # def dBJT_to_UTC(self, syear, smonth, sday, shour):
    # return time.strftime("%Y%m%d%H", time.gmtime(time.mktime(time.strptime(syear+smonth+sday+shour, "%Y%m%d%H"))))

  """北京时<-->世界时"""
  def dLocalT_cvt_UTC(self, sIn_YMDH, sformat="%Y%m%d%H", sdir="to"):
    dtIn_YMDH = datetime.datetime.strptime(sIn_YMDH, sformat)
    #北京时-->世界时
    if sdir=="to":
      dtYMDH_utc   = dtIn_YMDH.astimezone(pytz.UTC)
      sYMDH_utc    = dtYMDH_utc.strftime(sformat)
      return sYMDH_utc
    #世界时-->北京时
    else: 
      local_zone   = tz.tzlocal()
      dtYMDH_local = dtIn_YMDH.replace(tzinfo=tz.UTC).astimezone(local_zone)
      sYMDH_local  = dtYMDH_local.strftime(sformat)
      return sYMDH_local

  #UTC时间转本地时间 
  def utc_to_local(self, utc_st):
    """UTC时间转本地时间（+8:00）"""
    # usage:
    #     utc_time = datetime.datetime(2014, 9, 18, 10, 42, 16, 126000)
    #     local_time = utc_to_local(utc_time)
    #     print local_time.strftime("%Y-%m-%d %H:%M:%S")
    now_stamp = time.time()
    local_time = datetime.datetime.fromtimestamp(now_stamp)
    utc_time = datetime.datetime.utcfromtimestamp(now_stamp)
    offset = local_time - utc_time
    local_st = utc_st + offset
    return local_st

  #本地时间转UTC时间 
  def local_to_utc(self, local_st):
    """本地时间转UTC时间（-8:00）"""
    # usage:
    #    utc_tran = local_to_utc(local_time)
    #    print utc_tran.strftime("%Y-%m-%d %H:%M:%S")
    time_struct = time.mktime(local_st.timetuple())
    utc_st = datetime.datetime.utcfromtimestamp(time_struct)
    return utc_st

  
  '''读取任何文件内容'''
  '''无论有无行数'''
  def dRead_file_Contents(self, sIn_Abs_path):
    try:
      with open(sIn_Abs_path,'r') as fh:
        ltwork = fh.readlines()
    except IOError as error:
       print("No "+sIn_Abs_path)
       print(error)
       sys.exit()
    return ltwork
  
  '''写文件内容'''
  '''带有换行符\n'''
  def dWrite_file_Contents(self, sfile_AbsPath, ltNew_Lines):
    try:
      with open(sfile_AbsPath,'w') as fh:
        fh.writelines(ltNew_Lines)
    except IOError as error:
      print("No "+sfile_AbsPath)
      print(error)
      sys.exit()
    return
  
  #判断是否是nan
  def is_nan(self,x):
    return (x is np.nan or x != x or np.isnan(x))
  
  '''把时间戳转化为时间: 1479264792 to 2016-11-16 10:53:12'''
  def TimeStampToTime(self, timestamp):
    timestruct = time.localtime(timestamp)
    return time.strftime('%Y-%m-%d %H:%M:%S', timestruct)
  
  
  '''获取文件的大小,结果保留两位小数，单位为MB'''
  def get_FileSize(self, filePath):
    fsize = os.path.getsize(filePath)
    fsize = fsize/float(1024*1024)
    return round(fsize,2)
  
  
  '''获取文件的访问时间'''
  def get_FileAccessTime(self, filePath):
    t = os.path.getatime(filePath)
    return self.TimeStampToTime(t)
  
  
  '''获取文件的创建时间'''
  def get_FileCreateTime(self, filePath):
    t = os.path.getctime(filePath)
    return self.TimeStampToTime(t)
  
  
  '''获取文件的修改时间'''
  def get_FileModifyTime(self, filePath):
    t = os.path.getmtime(filePath)
    return self.TimeStampToTime(t)
  
  #获取整点时间
  def dWhole_time(self,dtdate_now=datetime.datetime.now(), ihour_ago=0):
    sformat="%Y-%m-%d %H"
    dtwhole_date=dtdate_now-datetime.timedelta(hours=ihour_ago)
    return datetime.datetime.strptime(dtwhole_date.strftime(sformat),sformat)
  
  #是否在前n小时之内
  def dWithin_nhours(self, in_time, ihour_ago=0):
    if isinstance(in_time,str):
      dtin_time = datetime.datetime.strptime(in_time, '%Y-%m-%d %H:%M:%S')
    else:
      dtin_time = in_time
    dtwhole_date_ago = self.dWhole_time(ihour_ago=ihour_ago)
    lwithin=False
    if dtin_time>=dtwhole_date_ago: lwithin=True
    return lwithin
  
  #两个日期之间相差几小时
  def ddate_diff_hours(self, dtend, dtbegin):
    td = dtend - dtbegin
    return td.days * 24 + td.seconds/3600


  # #获得目前函数名称
  # def get_current_function_name(self):
      # return inspect.stack()[1][3]
  
  #获得当前文件属性
  def get_attrs(self):  
      print('Module:', __name__)  
      print('File Path: ', __file__)  
      print('File Name: ', os.path.basename(__file__))  
      print('Line No.: ', sys._getframe().f_lineno)  
      print('Func: ', sys._getframe().f_code.co_name)
      #print('Func: ', get_current_function_name())  
  
    
  #根据列数获取excel类名
  def dexcel_column_name(self,n):
    """
    :type n: int
    :rtype: str
    """
    rStr = ""
    while n!=0:
        res = n%26
        if res == 0:
            res =26
            n -= 26
        rStr = chr(ord('A')+res-1) + rStr
        n = n//26
    return rStr
  
  #将数组中将偏差大的值进行替换,用ndydata2中的值替换ndydata1的错误值
  def darray_value_replace(self, ndydata1, ndydata2, fthreshold_offset, debug=3):
    #建模订正1的结果偏离平均误差订正结果的程度, 如果偏离程度过大说明建模订正有过拟合现象
    ndyerr_devia = np.abs(ndydata1-ndydata2)
    #如果订正误差偏离平均误差8摄氏度, 说明订正误差错误
    ndyidx=ndyerr_devia>=fthreshold_offset #找出偏差大的索引
    if np.any(ndyidx)==True and debug>=3:print(ndyerr_devia[ndyidx])
    ndydata1[ndyidx]=ndydata2[ndyidx] #替换
    return ndydata1,ndyidx
    
  #找出需要替换的数组
  def dfind_replace_index(self, ndydata1, ndydata2, fthreshold_offset, debug=3):
    #建模订正1的结果偏离平均误差订正结果的程度, 如果偏离程度过大说明建模订正有过拟合现象
    ndyerr_devia = np.abs(ndydata1-ndydata2)
    #如果订正误差偏离平均误差8摄氏度, 说明订正误差错误
    ndyidx=ndyerr_devia>=fthreshold_offset #找出偏差大的索引
    if np.any(ndyidx)==True and debug>=3:print(ndyerr_devia[ndyidx])
    return ndyidx
    
    
    
    
    
    
    
    
    
    
    
