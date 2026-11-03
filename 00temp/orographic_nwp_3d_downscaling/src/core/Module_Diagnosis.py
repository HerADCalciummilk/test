# -*- coding: utf-8 -*- 
# cython:language_level=3

"""
通过温度、露点温度计算相对湿度
"""

import numpy as np

RCAbsZero = 273.15

def saturation_vapor_pressure(temp_array):
    """
    通过温度计算饱和水汽压（单位：hpa）
    :param temp_array: 温度数组（单位：K）
    :return:饱和水汽压
    """
    #冰面
    temp_array[temp_array < RCAbsZero] = \
            (10**(3.56654 * np.log10(temp_array[temp_array < RCAbsZero]) -
             0.0032098 * temp_array[temp_array < RCAbsZero] -
            2484.956 / temp_array[temp_array < RCAbsZero] + 2.0702294))
    #水面
    temp_array[temp_array >= RCAbsZero] = \
        (10 ** (23.832241 - 2949.076 / temp_array[temp_array >= RCAbsZero] +
                  (-5.02808) * np.log10(temp_array[temp_array >= RCAbsZero]) +
                  (-1.3816E-7) * 10 ** (11.334 - 0.0303998 *
                        temp_array[temp_array >= RCAbsZero]) +
                  8.1328E-3 * 10 ** (3.49149 - 1302.8844 /
                    temp_array[temp_array >= RCAbsZero])))
    return temp_array


def dsaturation_vapor_pressure2(ndyTemp):
    """
    通过温度计算饱和水汽压（单位：hpa）
    (Bolton, 1980)
     Bolton, D., The computation of equivalent potential temperature, 
     Monthly Weather Review, 108, 1046-1053, 1980..
    :param temp_array: 温度数组（单位：K）
    :return:饱和水汽压
    """
    
    return ndyTemp


def relative_humidity(temp_array,dewpoint_temp_array):
    """
    用温度、露点温度求相对湿度
    :param temp_array: 温度数组（单位： K）
    :param dewpoint_temp_array:露点温度数组（单位： K）
    :return:相对湿度数组
    """
    temp_svp = saturation_vapor_pressure(temp_array)
    dewpoint_temp_svp = saturation_vapor_pressure(dewpoint_temp_array)
    rrh_array = dewpoint_temp_svp / temp_svp * 100
    return rrh_array

#比湿求相对湿度
def dRelativeHumidity_from_SH(ndyTemp, ndySH):
    """
    用温度(℃)、比湿求相对湿度
    输入参数: ndyTemp    温度数组（单位： K）
    输入参数: ndySH      比湿数组（单位： K）
    :return:相对湿度数组
    """
    
    return


# 离地面气压最近层气压层的气温垂直递减率℃/m, 
# 先获取不同层次的变量信息,再循环(花费时间3s)
def dEC_near_surface_gma(grbs, t_shortName="t", gh_shortName="gh", sp_shortName="sp", idebug=0):
  try:
    ltt   = grbs.select(shortName=t_shortName)
    ltgh  = grbs.select(shortName=gh_shortName)
    #地面气压值(0.125×0.125)  #高空是0.25
    ndysp = grbs.select(shortName=sp_shortName)[0].values   
  except Exception as ex:
    print("shortName="+",".join([t_shortName, gh_shortName, sp_shortName]),ex)
    ndygamma=None
    return ndygamma
  #稀疏化
  x=np.arange(0,ndysp.shape[1],2)
  y=np.arange(0,ndysp.shape[0],2)
  ndysp=ndysp[np.ix_(y,x)]
  ndygamma=np.empty_like(ndysp)
  try:
    #层次
    ltt_lev =[grb.level*100 for grb in ltt]
    ltgh_lev=[grb.level*100 for grb in ltgh]
    ltlevel = sorted(ltt_lev, reverse=False)  #找出最小气压值列表中的索引(减少遍历次数)
    idx_min=(ltlevel>=ndysp.min()).sum()
    for bp,ep in zip(ltlevel[idx_min:],ltlevel[idx_min+1:]+[110000]):
      bhpa=bp/100; ehpa=ep/100
      if idebug>0: print(bhpa,ehpa)
      ndyidx=(bp<=ndysp) & (ndysp<=ep)   #找到符合这个气压范围的索引
      if ndyidx.size == 0: continue 
      if ep==110000: #最低一层没有下层信息,需要赋值上一层的结果
        ndydeltaz=(ndyabovegh[ndyidx]-ndybelowgh[ndyidx])  
        ndydeltat=ndyabovet[ndyidx]-ndybelowt[ndyidx]
        ndydeltat=ndyabovet[ndyidx]-ndybelowt[ndyidx]
      else:
        iidx_tbp=ltt_lev.index(bp)
        iidx_tep=ltt_lev.index(ep)
        iidx_ghbp=ltgh_lev.index(bp)
        iidx_ghep=ltgh_lev.index(ep)
        #位势高度(以"位势米"为单位的位势高度值(H)与以"米"为单位的几何高度值(Z)基本相同)
        ndyabovegh = ltgh[iidx_ghbp].values                 #上层位势高度
        ndybelowgh = ltgh[iidx_ghep].values                 #下层位势高度
        #温度
        ndyabovet = ltt[iidx_tbp].values                   #上层温度
        ndybelowt = ltt[iidx_tep].values                   #下层温度
        ndydeltaz=(ndyabovegh[ndyidx]-ndybelowgh[ndyidx])  #高度差
        ndydeltat=ndyabovet[ndyidx]-ndybelowt[ndyidx]      #温度差
      gamma=ndydeltat/ndydeltaz  #气温垂直递减率(℃/m)
      ndygamma[np.where(ndyidx==True)]=gamma
  except Exception as ex:
    print("dEC_near_surface_gma",ex)
    ndygamma=-0.006   #单位℃/m
  return ndygamma


# 离地面气压最近层气压层的变量
# 先获取不同层次的变量信息,再循环(花费时间3s)
def dEC_near_surface_elt(grbs, elt_shortName="w", sp_shortName="sp", idebug=0):
  try:
    ndysp = grbs.select(shortName=sp_shortName)[0].values   #地面气压值(0.125×0.125)  #高空是0.25
    ltw  = grbs.select(shortName=elt_shortName)  #垂直速度
  except Exception as ex:
    print("shortName="+",".join([elt_shortName, sp_shortName]),ex)
    ndyw=None
    return ndyw
  #稀疏化
  x=np.arange(0,ndysp.shape[1],2)
  y=np.arange(0,ndysp.shape[0],2)
  ndysp=ndysp[np.ix_(y,x)]
  ndyw=np.empty_like(ndysp)
  try:
    #层次
    ltw_lev = [grb.level*100 for grb in ltw]
    ltlevel = sorted(ltw_lev, reverse=False)  #找出最小气压值列表中的索引(减少遍历次数)
    idx_min=(ltlevel>=ndysp.min()).sum()
    for bp,ep in zip(ltlevel[idx_min:],ltlevel[idx_min+1:]+[110000]):
      bhpa=bp/100; ehpa=ep/100
      if idebug>0: print(bhpa,ehpa)
      ndyidx=(bp<=ndysp) & (ndysp<=ep)   #找到符合这个气压范围的索引
      if ndyidx.size == 0: continue 
      if ep==110000: #最低一层没有下层信息,需要赋值上一层的结果
        ndyw[np.where(ndyidx==True)]=ndyabovew[ndyidx]
      else:
        iidx_wbp=ltw_lev.index(bp)
        ndyabovew = ltw[iidx_wbp].values
        ndyw[np.where(ndyidx==True)]=ndyabovew[ndyidx]
  except Exception as ex:
    print("dEC_near_surface_elt",ex)
    ndyw=None
  return ndyw






if __name__ == '__main__':
    temp_list = [279.0,286]
    dewpoint_temp_list = [275,280.3]
    temp_array = np.array(temp_list)
    dewpoint_temp_array = np.array(dewpoint_temp_list)
    rrh_array = relative_humidity(temp_array,dewpoint_temp_array)
    print(rrh_array)