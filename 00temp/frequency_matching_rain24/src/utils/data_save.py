# -- coding: utf-8 --
# @Time : 2025/3/6 17:05
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : dataSave.py
# @Software: PyCharm
import copy
import math, os
import traceback
import numpy as np
import pandas as pd
import datetime
import meteva.base as meb


def write_griddata(correct_current_model_grd, save_path, opt_type):
        if opt_type == 'm4':
            write_griddata_to_micaps4(correct_current_model_grd, save_path=save_path)
        elif opt_type == 'nc':
            meb.write_griddata_to_nc(correct_current_model_grd, save_path=save_path, effectiveNum=1)
        else:
            raise ('输出格点文件类型设置有误，当前仅支持m4和nc')

def write_griddata_to_micaps4(da, save_path="a.txt", creat_dir=True, effectiveNum=1, show=True, title=None, vmax=200, vmin=0):
    """
    输出micaps4格式文件
    :param da:xarray多维数据信息
    :param path:存储路径
    :param effectiveNum 有效数字 默认：6
    :return 最终按照需要保存的路径，将da数据保存为m4格式
    """
    try:
        dir = os.path.split(os.path.abspath(save_path))[0]
        if not os.path.isdir(dir):
            if not creat_dir:
                print("文件夹："+dir+"不存在")
                return False
            else:
                meb.tool.path_tools.creat_path(save_path)

        grid = meb.basicdata.get_grid_of_data(da)
        level = grid.levels[0]
        stime = grid.stime_str
        year = stime[0:4]
        month = stime[4:6]
        day = stime[6:8]
        hour = stime[8:10]
        hour_range = str(grid.dtimes[0])
        values = da.values
        grid_values = np.squeeze(values)

        dif = (vmax - vmin) / 10.0
        if dif ==0:
            inte = 1
        else:
            inte = math.pow(10, math.floor(math.log10(dif)))

        end = len(save_path)
        start = max(0, end - 17)

        if title is None:
            title = ("diamond 4 " + save_path[start:end] + "\n"
                     + year + " " + month + " " + day + " " + hour + " " + hour_range + " " + str(level) + "\n"
                     + "{:.6f}".format(grid.dlon) + " " + "{:.6f}".format(grid.dlat) + " " + "{:.6f}".format(grid.slon) + " " +"{:.6f}".format(grid.elon) + " "
                     + "{:.6f}".format(grid.slat) + " " + "{:.6f}".format(grid.elat) + " " + str(grid.nlon) + " " + str(grid.nlat) + " "
                     + str(inte) + " " + str(vmin) + " " + str(vmax) + " 1 0")
        else:

            title = ("diamond 4 "+ title +"\n"
                     + year + " " + month + " " + day + " " + hour + " " + hour_range + " " + str(level) + "\n"
                     + "{:.6f}".format(grid.dlon) + " " + "{:.6f}".format(grid.dlat) + " " + "{:.6f}".format(grid.slon) + " " + "{:.6f}".format(grid.elon) + " "
                     + "{:.6f}".format(grid.slat) + " " + "{:.6f}".format(grid.elat) + " " + str(grid.nlon) + " " + str(grid.nlat) + " "
                     + str(inte) + " " + str(vmin) + " " + str(vmax) + " 1 0")

        # 二维数组写入micaps文件
        format_str = "%." + str(effectiveNum) + "f "

        np.savetxt(save_path, grid_values, delimiter=' ',
                   fmt=format_str, header=title, comments='')
        if show:
            print('成功输出至'+ save_path)
        return True
    except:
        exstr = traceback.format_exc()
        print(exstr)
        return False


def write_stadata_to_micaps3(sta0,save_path = "a.txt",creat_dir = False, type = -1,effectiveNum = 4,show = False,title = None):
    """
    生成micaps3格式的文件
    :param sta0:站点数据信息
    :param save_path 需要保存的文件路径和名称
    :param type 类型：默认：1
    :param effectiveNum 有效数字 默认为：4
    :return:保存为micaps3格式的文件
    """
    try:
        sta = copy.deepcopy(sta0)
        dir = os.path.split(os.path.abspath(save_path))[0]
        if not os.path.isdir(dir):
            if not creat_dir:
                print("文件夹：" + dir + "不存在")
                return False
            else:
                meb.tool.path_tools.creat_path(save_path)

        br = open(save_path,'w')
        end = len(save_path)
        start = max(0, end-17)
        nsta =len(sta.index)
        time = sta['time'].iloc[0]
        if isinstance(time,np.datetime64) or isinstance(time, datetime.datetime):
            time_str = meb.tool.time_tools.time_to_str(time)
            time_str = time_str[0:4] + " " +time_str[4:6] + " " + time_str[6:8] + " " + time_str[8:10] + " "
        else:
            time_str = "2099 01 01 0 "

        if np.isnan(sta['level'].iloc[0]):
            level = 0
        else:
            level = int(sta['level'].iloc[0])
        if type<0 or level == np.NaN or level == pd.NaT:
            level = int(type)

        if title is None:
            str1=("diamond 3 " + save_path[start:end] + "\n"+ time_str + str(level) +" 0 0 0 0\n1 " + str(nsta) + "\n")
        else:
            str1 = ("diamond 3 " + title + "\n" + time_str + str(level) + " 0 0 0 0\n1 " + str(
                nsta) + "\n")
        br.write(str1)
        br.close()
        data_names = meb.basicdata.get_stadata_names(sta)
        if "alt" not in data_names:
            data_name = meb.basicdata.get_stadata_names(sta)[0]
            df = copy.deepcopy(sta[['id','lon','lat',data_name]])
            df['alt'] = 0
            df = df.reindex(columns=['id', 'lon', 'lat', 'alt', data_name])
        else:
            colums = ['id','lon','lat','alt']
            for name in data_names:
                if name != "alt":
                    colums.append(name)
                    break
            df = sta.loc[:,colums]
            if len(colums) == 4:
                df["data0"] = 0
        effectiveNum_str = "%." + '%d'% effectiveNum + "f"
        df.to_csv(save_path,mode='a',header=None,sep = "\t",float_format=effectiveNum_str,index = None)
        if show:
            print('成功输出至' + save_path)
        return True
    except:
        exstr = traceback.format_exc()
        print(exstr)
        return False