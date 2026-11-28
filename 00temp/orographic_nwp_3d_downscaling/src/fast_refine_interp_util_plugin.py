# -*- coding: utf-8 -*-
"""地形三维插值的标量计算。插件和 `Class_Interp_dem` 都调用这里，公式只有这一份。"""
import numpy as np


def dem_interp_scalar(dyIntpP, dyGrid, lapse_rate_2d, eta=1.0, skey="2t", sout="less"):
    """把粗网格标量按地形订正后双线性插到目标点。

    参数：
        dyIntpP：目标点，含 lon、lat、alt。
        dyGrid：源格点，含起止经纬度、分辨率、格点数、二维经纬度、alt，以及 skey 对应的要素场。
            数组上下方向是南到北。
        lapse_rate_2d：垂直变率，形状与源格点相同。
        eta：地形订正系数。标量、源格点场或目标点场都可以。
        skey：要素短名，例如 2t、2rh、10ws、sp。
        sout：`less` 只返回插值结果；其他值再返回四角格点索引。

    返回：
        目标点上的要素场。风速小于 0 记为 0，相对湿度限制在 0 到 100，气压低于 200 记为 200。
    """
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
