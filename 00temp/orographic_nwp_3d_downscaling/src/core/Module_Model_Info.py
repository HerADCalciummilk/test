# -*- coding: utf-8 -*- 
# cython:language_level=3

"""
解析ini配置文件并存到指定数据结构
"""

import os
import re
import sys
import datetime
import pdb



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
      

class ModelInfo:
    """
    ModelInfo配置文件信息存储类
    """
    def __init__(self):
        #模式名
        self.model_name       = ''
        #模式标记             
        self.smodel_flag      = ''
        #经纬度信息           
        self.latlon_info      = []
        #指定日期数据存储位置 
        self.data_location    = {}
        #起报时间             
        self.report_times     = []
        #多层要素             
        self.iN_mlt_elt       = 0
        self.mlt_elts         = []
        self.mlt_short_name   = []
        #单层要素             
        self.iN_sgl_elt       = 0    
        self.sgl_elts         = []
        self.sgl_short_name   = []
        #etn层要素            
        self.iN_eta_elt       = 0
        self.eta_elts         = []
        self.eta_short_name   = []
        #日值要素
        self.iN_day_elt       = 0
        self.day_elts         = []
        self.day_short_name   = []
        #瞬时要素
        self.iN_hour_elt      = 0
        self.hour_elts        = []
        self.hour_short_name  = []
        #气压层               
        self.iN_Plevs         = 0
        self.pressure_levels  = []
        #单层标记             
        self.single_level     = ''
        #etn层                
        self.iN_Elevs         = 0
        self.eta_level        = ''
        #时间点
        self.iN_Fhours        = 0
        self.ltforecast_hours = []
        #非文件中的变量
        self.iN_elt_1t1s      = 0   #1个时次1个站点的要素个数
        self.P1t_code         = []  #1个时次的因子代码列表(与第3步数据对应)
        self.P1t_Name         = []  #1个时次的因子名称列表(与第3步数据对应)
        self.P1t_RInfo        = []  #1个时次的因子信息
        self.Pday_code        = []
        self.Pday_Name        = []
        self.Pday_RInfo       = []
        
        
    def ParseIni(self,file_path,encoding="utf-8"):
        """
        按行解析ini配置文件并存到数据结构
        :param file_path: ini文件路径
        :return:
        """
        with open(file_path,'r',encoding=encoding) as fh:
          #模式信息
          model_info  = fh.readline()
          self.model_name = model_info.split(' ')[0].strip()
          smodel_flag = model_info.split(' ')[1].strip()
          self.smodel_flag = str('%0.2d'%(int(smodel_flag)))
          #经纬度信息
          latlon_info = LatlonInfo()
          #纬度
          lat_line = fh.readline()
          lat_vars = lat_line.split()
          latlon_info.lat_start     = float(lat_vars[0])
          latlon_info.lat_end       = float(lat_vars[1])
          latlon_info.lat_precision = float(lat_vars[2])
          # 经度
          lon_line = fh.readline()
          lon_vars = lon_line.split()
          latlon_info.lon_start     = float(lon_vars[0])
          latlon_info.lon_end       = float(lon_vars[1])
          latlon_info.lon_precision = float(lon_vars[2])
          latlon_info.N_lons=round((latlon_info.lon_end-latlon_info.lon_start)/latlon_info.lon_precision)+1
          latlon_info.N_lats=round((latlon_info.lat_end-latlon_info.lat_start)/latlon_info.lat_precision)+1
          self.latlon_info=latlon_info
          #日期对应硬盘位置信息
          disk_num = fh.readline()
          #{'20120101_20131231':'/vdisk2/zxq/DataBase'}
          for i in range(int(disk_num)):
              disk_line = fh.readline()
              disk_vars = disk_line.split(' ')
              start_date = disk_vars[0].strip()
              end_date = disk_vars[1].strip()
              disk = disk_vars[2].strip()
              key = start_date + '_' + end_date
              self.data_location[key] = disk
          #开始时间
          start_time_num = fh.readline()
          report_time_line = fh.readline()
          report_times = report_time_line.split()
          for report_time in report_times:
              self.report_times.append(report_time.strip())
          #等压值变量
          self.iN_multi_elt = int(fh.readline())
          for i in range(self.iN_multi_elt):
              pressure_elt_line = fh.readline()
              pressure_elt_vars = pressure_elt_line.split()
              tmp_vars = []
              for pressure_elt_var in pressure_elt_vars:
                  if len(pressure_elt_var) == 0:
                      continue
                  tmp_vars.append(pressure_elt_var)
              elt_short_name = tmp_vars[0].strip()
              elt_full_name = tmp_vars[1].strip()
              elt_ch_name = tmp_vars[2].strip()
              self.mlt_short_name.append(elt_short_name)
              elt_tuple = (elt_short_name,elt_full_name,elt_ch_name)
              self.mlt_elts.append(elt_tuple)
          #单层变量
          self.iN_sgl_elt = int(fh.readline())
          for i in range(self.iN_sgl_elt):
              single_elt_line = fh.readline()
              single_elt_vars = single_elt_line.split()
              tmp_vars = []
              for single_elt_var in single_elt_vars:
                  if len(single_elt_var) == 0:
                      continue
                  tmp_vars.append(single_elt_var)
              elt_short_name = tmp_vars[0].strip()
              elt_full_name = tmp_vars[1].strip()
              elt_ch_name = tmp_vars[2].strip()
              self.sgl_short_name.append(elt_short_name)
              elt_tuple = (elt_short_name, elt_full_name, elt_ch_name)
              self.sgl_elts.append(elt_tuple)
          #eta变量
          self.iN_eta_elt = int(fh.readline())
          for i in range(self.iN_eta_elt):
              etn_elt_line = fh.readline()
              etn_elt_vars = etn_elt_line.split()
              tmp_vars = []
              for etn_elt_var in etn_elt_vars:
                  if len(etn_elt_var) == 0:
                      continue
                  tmp_vars.append(etn_elt_var)
              elt_short_name = tmp_vars[0].strip()
              elt_full_name = tmp_vars[1].strip()
              elt_ch_name = tmp_vars[2].strip()
              self.eta_short_name.append(elt_short_name)
              elt_tuple = (elt_short_name, elt_full_name, elt_ch_name)
              self.eta_elts.append(elt_tuple)
          #日变要素
          self.iN_day_elt = int(fh.readline())
          for i in range(self.iN_day_elt):
              day_elt_line = fh.readline()
              day_elt_vars = day_elt_line.split()
              tmp_vars = []
              for day_elt_var in day_elt_vars:
                  if len(day_elt_var) == 0:
                      continue
                  tmp_vars.append(day_elt_var)
              elt_short_name = tmp_vars[0].strip()
              elt_full_name = tmp_vars[1].strip()
              elt_ch_name = tmp_vars[2].strip()
              elt_rely = tmp_vars[3].strip()
              elt_func = tmp_vars[4].strip()
              self.day_short_name.append(elt_short_name)
              day_tuple = (elt_short_name, elt_full_name, elt_ch_name, elt_rely, elt_func)
              self.day_elts.append(day_tuple)
          #瞬时要素
          self.iN_hour_elt = int(fh.readline())
          for i in range(self.iN_hour_elt):
              hour_elt_line = fh.readline()
              hour_elt_vars = hour_elt_line.split()
              tmp_vars = []
              for hour_elt_var in hour_elt_vars:
                  if len(hour_elt_var) == 0:
                      continue
                  tmp_vars.append(hour_elt_var)
              elt_short_name = tmp_vars[0].strip()
              elt_full_name = tmp_vars[1].strip()
              elt_ch_name = tmp_vars[2].strip()
              elt_rely = tmp_vars[3].strip()
              elt_func = tmp_vars[4].strip()
              self.hour_short_name.append(elt_short_name)
              hour_tuple = (elt_short_name, elt_full_name, elt_ch_name, elt_rely, elt_func)
              self.hour_elts.append(hour_tuple)
          #气压层数
          self.iN_Plevs = int(fh.readline())
          #大气压层
          pressure_level_line = fh.readline()
          pressure_levels = re.split('[, ]',pressure_level_line.strip())
          for pressure_level in pressure_levels:
              self.pressure_levels.append(int(pressure_level.strip()))
          #单层标记
          self.single_level = fh.readline().strip()
          #etn层
          self.iN_Elevs  = int(fh.readline().strip())
          #预报时效
          self.iN_Fhours = int(fh.readline())
          time_lines     = fh.readlines()
          for sline in time_lines:
            ltforecast_hours = re.split('[, ]',sline.strip())
            self.ltforecast_hours.extend([int(time) for time in ltforecast_hours if len(time.strip())!=0])
          #非文件中变量
          self.iN_elt_1t1s = self.iN_multi_elt*self.iN_Plevs + self.iN_sgl_elt + self.iN_eta_elt*self.iN_Elevs
          #1个时次的因子代码列表(与第3步数据对应)
          #多层数据
          for i in range(self.iN_multi_elt): #要素
            for ilev in self.pressure_levels:  #层次
              self.P1t_code.append("_".join(["I"+"%03d"%(i+1),"%04d"%ilev]))
              self.P1t_Name.append("/".join([("%04d"%ilev)+"hpa"]+list(self.mlt_elts[i])))
              self.P1t_RInfo.append([ilev]+list(self.mlt_elts[i]))
          #单层数据
          for i in range(self.iN_sgl_elt): #要素
            self.P1t_code.append("_".join(["S"+"%03d"%(i+1),self.single_level]))
            self.P1t_Name.append("/".join(list(self.sgl_elts[i])))
            self.P1t_RInfo.append([int(self.single_level)]+list(self.sgl_elts[i]))
          #eta数据
          for i in range(self.iN_eta_elt):   #要素
            for ilev in range(self.iN_Elevs):  #层次
              self.P1t_code.append("_".join(["E"+"%03d"%(i+1),"%04d"%ilev]))
              self.P1t_Name.append("/".join(["%04d"%ilev]+list(self.eta_elts[i])))
              self.P1t_RInfo.append([ilev]+list(self.eta_elts[i]))
          #日变数据
          for i in range(self.iN_day_elt):
            self.Pday_code.append("_".join(["D"+"%03d"%(i+1),self.single_level]))
            self.Pday_Name.append("/".join(list(self.day_elts[i])))
            self.Pday_RInfo.append([int(self.single_level)]+list(self.day_elts[i]))
            
            
          
    def WRF_ParseIni(self,file_path,encoding="utf-8"):
        """
        按行解析ini配置文件并存到数据结构
        :param file_path: ini文件路径
        :return:
        """
        with open(file_path,'r',encoding=encoding) as fh:
            #模式信息
            model_info = fh.readline()
            self.model_name = model_info.split(' ')[0].strip()
            smodel_flag = model_info.split(' ')[1].strip()
            self.smodel_flag = str('%0.2d'%(int(smodel_flag)))
            #日期对应硬盘位置信息
            #{'20120101_20131231':'/vdisk2/zxq/DataBase'}
            disk_num = fh.readline()
            for i in range(int(disk_num)):
                disk_line = fh.readline()
                disk_vars = disk_line.split(' ')
                start_date = disk_vars[0].strip()
                end_date = disk_vars[1].strip()
                disk = disk_vars[2].strip()
                key = start_date + '_' + end_date
                self.data_location[key] = disk
            #开始时间
            start_time_num = fh.readline()
            report_time_line = fh.readline()
            report_times = report_time_line.split(' ')
            for report_time in report_times:
                self.report_times.append(report_time.strip())
            #多层变量
            iN_multi_elt = fh.readline()
            for i in range(int(iN_multi_elt)):
                pressure_elt_line = fh.readline()
                pressure_elt_vars = pressure_elt_line.split(' ')
                tmp_vars = []
                for pressure_elt_var in pressure_elt_vars:
                    if len(pressure_elt_var) == 0:
                        continue
                    tmp_vars.append(pressure_elt_var)
                elt_short_name = tmp_vars[0].strip()
                elt_full_name = tmp_vars[1].strip()
                elt_ch_name = tmp_vars[2].strip()
                elt_tuple = (elt_short_name,elt_full_name,elt_ch_name)
                self.mlt_elts.append(elt_tuple)
            #单层变量
            single_elt_num = fh.readline()
            for i in range(int(single_elt_num)):
                single_elt_line = fh.readline()
                single_elt_vars = single_elt_line.split(' ')
                tmp_vars = []
                for single_elt_var in single_elt_vars:
                    if len(single_elt_var) == 0:
                        continue
                    tmp_vars.append(single_elt_var)
                elt_short_name = tmp_vars[0].strip()
                elt_full_name = tmp_vars[1].strip()
                elt_ch_name = tmp_vars[2].strip()
                elt_tuple = (elt_short_name, elt_full_name, elt_ch_name)
                self.sgl_elts.append(elt_tuple)
            #单层标记
            self.single_level = fh.readline().strip()
            #etn层
            self.eta_level = fh.readline().strip()
            #预测时效
            iN_Fhours = int(fh.readline())
            time_lines = fh.readlines()
            for time_line in time_lines:
                ltforecast_hours = time_line.split(',')
                for time in ltforecast_hours:
                    if len(time.strip()) != 0:
                        self.ltforecast_hours.append(time.strip())


    def find_index(self, selt_name, ilevel=-1):
      """
      找出层次要素的位置
      """
      #在等压层
      if(selt_name in self.mlt_short_name):
        if ilevel in self.pressure_levels:
          ielt_idx = self.mlt_short_name.index(selt_name) #要素所在位置
          ilev_idx = self.pressure_levels.index(ilevel)   #层次所在位置
          iout_idx = ielt_idx*self.iN_Plevs+ilev_idx
        else:
          return -1
      #在单层
      elif(selt_name in self.sgl_short_name):
        ielt_idx = self.sgl_short_name.index(selt_name)
        iout_idx = self.iN_multi_elt*self.iN_Plevs+ielt_idx
      #在eta层
      elif(selt_name in self.eta_short_name):
        ielt_idx = self.eta_short_name.index(selt_name)
        iout_idx = self.iN_multi_elt*self.iN_Plevs + self.iN_sgl_elt + ielt_idx*self.iN_Elevs+ilevel-1
      #在日要素层
      elif(selt_name in self.day_short_name):
        iout_idx = self.day_short_name.index(selt_name)
      #在瞬时要素
      elif(selt_name in self.hour_short_name):
        ielt_idx = self.hour_short_name.index(selt_name)
        iout_idx = self.iN_day_elt + ielt_idx - 1
      else:
        return -1
      return iout_idx
    
    #预备因子的所有时效
    def dPredictor_Forecast_Hours(self, ltFrst_Hours, fend_limit=264): 
      """
      预测因子时效
      """
      #检查开始/结束预报时效是否在范围内
      if(ltFrst_Hours[0]<0):
        print("begin forecast hour:",ltFrst_Hours[0])
        print("Module_Model_Info:dPredictor_Forecast_Hours")
        sys.exit()
      if(ltFrst_Hours[1]>=fend_limit):
        print("end forecast hour:",ltFrst_Hours[1])
        print("Module_Model_Info:dPredictor_Forecast_Hours")
        sys.exit()
      #开始/结束时效内的预报时间
      lthours = [x for x in self.ltforecast_hours if ltFrst_Hours[0]<=x and x<=ltFrst_Hours[1]]
      #如果有存在的预报时效
      if lthours!=[]:
        idx_begin = self.ltforecast_hours.index(lthours[0])
        idx_end   = self.ltforecast_hours.index(lthours[-1])
        if(idx_begin>0):
          ltH=[self.ltforecast_hours[idx_begin-1]]
        else:
          ltH=[]
        if(idx_end<self.iN_Fhours-1):
          ltE=[self.ltforecast_hours[idx_end+1]]
        else:
          ltE=[]
        ltPhours=ltH+lthours+ltE
      #如果没有存在的,说明开始-结束时效的分辨率小于模式预报时效的分辨率 或者超出最大值
      else:
        #超出最大值 只用最后一个
        if ltFrst_Hours[0]>self.ltforecast_hours[-1]:
          ltPhours=[self.ltforecast_hours[-1]]
        else:
          for tpx in zip(self.ltforecast_hours,self.ltforecast_hours[1:]):
            if tpx[0]<=ltFrst_Hours[0] and ltFrst_Hours[0]<=tpx[1]:
              fbegin=tpx[0]
            if tpx[0]<=ltFrst_Hours[1] and ltFrst_Hours[1]<=tpx[1]:
              fend=tpx[1]
          ltPhours=[x for x in self.ltforecast_hours if fbegin<=x and x<=fend]
      return ltPhours
      
    #找出1个时次中某个因子的所在位置的index
    def dfind_1tPdr_index(self,ltfind_Pdr):
      ltlevel, ltshort_name, ltlong_name, ltChi_name=zip(*self.P1t_RInfo)
      lteach_idx=[]
      for ltPdr in ltfind_Pdr:  #[0层次,1要素名,2要素名类型(3种)]
        #要素的index
        if ltPdr[2]==1:
          ltelt_idx=[i for i,val in enumerate(ltshort_name) if val==ltPdr[1]]
        elif ltPdr[2]==2:
          ltelt_idx=[i for i,val in enumerate(ltlong_name) if val==ltPdr[1]]
        elif ltPdr[2]==3:
          ltelt_idx=[i for i,val in enumerate(ltChi_name) if val==ltPdr[1]]
        #层次的index
        ltlev_idx=[i for i,val in enumerate(ltlevel) if val==ltPdr[0]]
        #要素和层次
        if ltlev_idx!=[] and ltelt_idx!=[]: #intersection()方法用于返回两个或更多集合中都包含的元素，即交集
          isame_idx=list(set(ltelt_idx).intersection(set(ltlev_idx)))[0]
        else:
          isame_idx=float('nan')
        lteach_idx.append(isame_idx)
      return lteach_idx
    
    #找到日变化因子的序号
    def dfind_dayPdr_index(self,stype):
      idx=-1
      if stype=="max":
        idx=self.day_short_name.index("mx2t24")
      elif stype=="min":
        idx=self.day_short_name.index("mn2t24")
      return idx
    

    #所有时效的预备因子ID号(时效, 要素, 格点 从外到内循环)
    def dPredictor_ID_nhours(self,sBegin_mhour,ltPdr_FHours, ltGrid):
      """
        sBegin_mhour : str
        ltPdr_FHours : int list
        ltGrid       : int list
      """                   #模式          起报点         预报时效     要素  层次  格点
      return ["_".join([self.smodel_flag, sBegin_mhour, "%03d"%ifhour, scode, "%02d"%igrid]) \
              for ifhour in ltPdr_FHours for scode in self.P1t_code for igrid in ltGrid]
    
    
    def dPredictor_ID_day(self,sBegin_mhour,ltPdr_FHours, ltGrid):
      """
        sBegin_mhour : str
        ltPdr_FHours : int list
        ltGrid       : int list
      """                   #模式          起报点         预报时效     要素  层次  格点
      return ["_".join([self.smodel_flag, sBegin_mhour, "%03d"%ifhour, scode, "%02d"%igrid]) \
              for ifhour in ltPdr_FHours for scode in self.Pday_code for igrid in ltGrid]
    
    
    #找出因子的中文名
    def dfind_Pdr_Chinese_name(self,ltPdr_code):
      ltChinese_name=[]
      for scode in ltPdr_code:
        x=scode.decode('utf-8')
        stype=x[10:11]
        if stype=="I":
          schi_name= "_".join([self.model_name, x[3:5]+"t", str(int(x[6:9]))+"h", str(int(x[15:19]))+"hpa", self.mlt_elts[int(x[11:14])-1][1]])
        elif stype=="S":
          schi_name= "_".join([self.model_name, x[3:5]+"t", str(int(x[6:9]))+"h", self.sgl_elts[int(x[11:14])-1][1]])
        elif stype=="E":
          schi_name= "_".join([self.model_name, x[3:5]+"t", str(int(x[6:9]))+"h", str(int(x[15:19]))+"eta", self.eta_elts[int(x[11:14])-1][1]])
        elif stype=="D":
          schi_name= "_".join([self.model_name, x[3:5]+"t", str(int(x[6:9])-24)+"-"+str(int(x[6:9]))+"h", 
                              self.day_elts[int(x[11:14])-1][1]])
        ltChinese_name.append(schi_name.encode('utf-8'))
      return ltChinese_name
  
    def PrintInfo(self):
        """
        print类所有属性
        :return:
        """
        for key in self.__dict__:
            print (key,':',self.__dict__[key])

    def DateRange(self,begain_date,end_date):
        """
        获取date list
        :param begain_date: 开始日期
        :param end_date: 结束日期
        :return:date list
        """
        dates = []
        dt = datetime.datetime.strptime(begain_date, '%Y%m%d')
        date = begain_date
        while date <= end_date:
            dates.append(date)
            dt = dt + datetime.timedelta(1)
            date = dt.strftime('%Y%m%d')
        return dates

    def GetDisk(self,date):
        """
        传入一个日期，返回日期数据存储硬盘
        :param date: 日期
        :return:对应日期数据存储硬盘
        """
        disk = 'null'
        min_date = ''
        max_date = ''
        for key in self.data_location:
            start_date = key.split('_')[0]
            end_date = key.split('_')[1]
            if min_date == '' or min_date > start_date:
                min_date = start_date
                min_key = key
            if max_date == '' or max_date < end_date:
                max_date = end_date
                max_key = key
            dates = self.DateRange(start_date,end_date)
            if date in dates:
                disk = self.data_location[key]
        if disk == 'null':
            if date < min_date:
                disk = self.data_location[min_key]
            elif date > max_date:
                disk = self.data_location[max_key]
                
        return disk

    #读裁剪格点区域信息
    def dGridini(self,file_path):
      """
      按行解析ini配置文件并存到数据结构
      :param file_path: ini文件路径
      :return:
      """
      if os.path.exists(file_path):
        with open(file_path,'r',encoding='gbk') as fh:
          #经纬度信息
          latlon_info = LatlonInfo()
          # 纬度
          lat_line = fh.readline()
          lat_vars = lat_line.split()
          latlon_info.lat_start     = float(lat_vars[0])
          latlon_info.lat_end       = float(lat_vars[1])
          latlon_info.lat_precision = float(lat_vars[2])
          # 经度
          lon_line = fh.readline()
          lon_vars = lon_line.split()
          latlon_info.lon_start     = float(lon_vars[0])
          latlon_info.lon_end       = float(lon_vars[1])
          latlon_info.lon_precision = float(lon_vars[2])
          latlon_info.N_lons=round((latlon_info.lon_end-latlon_info.lon_start)/latlon_info.lon_precision)+1
          latlon_info.N_lats=round((latlon_info.lat_end-latlon_info.lat_start)/latlon_info.lat_precision)+1
          return latlon_info
      else:
        print("No:"+file_path)
        sys.exit()

if __name__ == '__main__':
    file_path = '/data3/zxq/IGF_sys/GMOSRR/Parameter/EC/EC_New_Info.ini'
    ec_new_info = ModelInfo()
    ec_new_info.ParseIni(file_path)
    ec_new_info.find_index('2t_max')