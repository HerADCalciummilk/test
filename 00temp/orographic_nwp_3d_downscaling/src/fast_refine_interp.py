# -*- coding: utf-8 -*- 
# cython:language_level=3
import os
import sys
import h5py
import time
import datetime
import configparser
import numpy as np
import pandas as pd
from multiprocessing  import cpu_count

# ====================== 关键修复：让 Python 能找到 core/ 目录下的所有 Module ======================
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
core_path = os.path.join(MODULE_DIR, "core")
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)
if core_path not in sys.path:
    sys.path.insert(0, core_path)
try:
    from .para_ini import _load_fast_refine_sections
except ImportError:
    from para_ini import _load_fast_refine_sections
# =====================================================================================================

import core.Module_MyFunction      as MMyfun
import core.Module_Arguments       as MArg
import core.Module_Global_Variable as MGV
import core.Module_Station         as MSite
import core.Module_Obs_DataBase    as MObsDB
import core.Module_Model_Info      as MModel
import core.Module_3PreProcess     as M3PrePro
import core.Module_Interp_dem5     as MInterp3d
import core.Module_Diagnosis       as MDiag
#import core.Module_Micaps_RW       as MMICPS
import core.mdl_obs_path           as Mmop


# =============================================================================
# 新增：纯函数入口（无任何parser，完全通过参数调用）
# =============================================================================
def _infer_root_path(work_dir):
    """????????????? Parameter ???????"""
    cur = os.path.abspath(work_dir)
    for _ in range(10):
        if os.path.isdir(os.path.join(cur, "Parameter")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.abspath(os.path.dirname(work_dir))


def _split_model_region(model_region):
    parts = model_region.split("_", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"model_region must look like EC_12P5KM, got {model_region!r}")
    return parts[0], parts[1]


def _append_optional_pylib(root_path):
    pylib_path = os.path.join(root_path, "lib", "pylib")
    if os.path.isdir(pylib_path) and pylib_path not in sys.path:
        sys.path.append(pylib_path)


def run_fast_refine(debug=0, update=0, operation="i", begin_date=None,
                    resolution="1km", para_file="Fast_refine_interp_1km.ini",
                    work_dir=None, model_region=None, root_path=None,
                    s3_method=None, site_name="Station1", overrides=None):
    """
    纯Python调用入口（供 runner 使用）

    ``overrides`` 的键是 ``节.键``（如 ``InstantInfo.validate``、``MaxMinInfo.update``、
    ``threshold.2t``）。值为 ``None`` 的项忽略。不传且 ini 齐全时行为与原来一致。
    """
    class SimpleArgs:
        pass
    args = SimpleArgs()
    args.debug = debug
    args.update = update
    args.operation = operation.lower()
    args.begin_date = begin_date
    args.resolution = resolution
    args.para_file = para_file
    args.site_name = site_name

    # ====================== 下面是原来主程序的全部逻辑（完整展开） ======================
    # 当前路径
    scurrent_path = os.path.abspath(work_dir or os.getcwd())
    sRoot_Path = os.path.abspath(root_path or _infer_root_path(scurrent_path))
    _append_optional_pylib(sRoot_Path)
    
    #cpu核数
    in_cpu_core = cpu_count()
    
    #pid
    print("py_pid:",os.getpid())
    
    #根据文件夹确定参数
    ltwork=scurrent_path.split(os.sep)
    #模式名 区域
    sModel_Region = model_region or ltwork[-1]
    sModel_name,sRegion = _split_model_region(sModel_Region)
    sModel_name_lower,sRegion_lower = sModel_name.lower(),sRegion.lower()
    sModel_Region_upper=sModel_Region.upper()
    if args.debug>=1:print("model:"+sModel_Region_upper)
    #第3步方法名
    sS3_method = s3_method or (ltwork[-2] if len(ltwork) >= 2 else "g_interp")
 
    #插值时间
    if args.begin_date is None or len(args.begin_date)<10: #没有输入或者输入不正确
        sInterp_YMDH = datetime.datetime.now().strftime('%Y%m%d%H')  # 当前系统时间
    else:
        sInterp_YMDH = args.begin_date
    if args.debug>=1:print("YMDH_BJ:"+sInterp_YMDH)
    
    #实例化
    cls_myfun = MMyfun.Class_MyFunction(iDebug=0)
    cls_gv    = MGV.Class_Global_Variable(iDebug=0)
    cls_site  = MSite.Class_Station_Info(iDebug=0)
    cls_obsdb = MObsDB.Class_Obs_DataBase(iDebug=0)
    cls_model = MModel.ModelInfo()
    cls_S3    = M3PrePro.Class_3PreProcess(iDebug=0)
    cls_itp3d = MInterp3d.Class_Interp_dem(iDebug=args.debug)
#    cls_micps = MMICPS.Class_Micaps_rw_data()
    # 路径拼接的配置添加
    Spath = Mmop.Class_Get_Sorce_Path(iDebug=args.debug)

    #全局变量
    dyglobalInfo = cls_gv.dGlobal_Info(sRoot_Path)

    #实况信息
    cls_obsdb.dRObs_Info_ini(sRoot_Path)

    #模式信息
    sIn_mdl_Para_abs_path = os.path.join(sRoot_Path, cls_gv.Sys_Para_dir, sModel_name, "_".join([sModel_Region, cls_gv.Sys_MInfo_tail]))
    cls_model.ParseIni(sIn_mdl_Para_abs_path)

    #------------------------------------------------------------------------------------------------------------------------
    #参数文件(CumulantDecompose.ini)
    if args.para_file is None:
        sfile_name = os.path.basename(sys.argv[0]).split(".")[0]+".ini"
    else:
        sfile_name = args.para_file
    spara_abs_path = os.path.join(scurrent_path,sfile_name)
    if os.path.exists(spara_abs_path):
        config = configparser.ConfigParser()
        config.read(spara_abs_path)
        dyInstantInfo, dyMaxMinInfo, dySiteInfo, dyPool, dythreshold = _load_fast_refine_sections(
            config, args, overrides
        )

        #打印并行参数信息
        print([skey+":"+str(dyPool[skey]) for skey in dyPool])
        dyPara_ini_info = {"InstantInfo":dyInstantInfo, "MaxMinInfo":dyMaxMinInfo, "Pool":dyPool, "threshold":dythreshold}
    else:
        print("No:"+spara_abs_path)
        sys.exit()

    #------------------------------------------------------------------------------------------------------------------------
  
    #-------------------------------------------------------------------------
    iNum_BFH=2 #几次起报
    dynowtime_vs_bhours = cls_gv.dS3_nowtime_vs_beginhour(sModel_name_lower, sRegion_lower, Num_BFH=iNum_BFH)
    ltmdl_begin_hour    = dynowtime_vs_bhours[int(sInterp_YMDH[8:])] #多往前1天,因为预报时效有超过24小时
    shour_mdl_begin     = "%02d"%ltmdl_begin_hour[0]
    sYMD_mdl_begin      = cls_myfun.dtimes_ago(sInterp_YMDH[0:8], ltmdl_begin_hour[1])
    #不同模式的起报时效
    #GRAPES_12P5KM
    if sModel_Region_upper in ["GRAPES_12P5KM", "GRAPES_25KM"]:
        #2次起报
        if iNum_BFH==2:
            lthour_mdl_begin = ["08","20"]
            iend_fhour=48
        #4次起报
        else:
            lthour_mdl_begin = ["02","08","14","20"]
            iend_fhour=42
        ibegin_fhour=3
    #EC
    elif sModel_Region_upper=="EC_12P5KM":
        lthour_mdl_begin = ["08","20"]
        ibegin_fhour=6
        iend_fhour=57 #54 #48  #为什么是36个时效,从2/14点开始起报(0h), 3点/15点是1h, 到8:00和20:00(30h)
    elif sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
        lthour_mdl_begin = [f"{ih:02d}" for ih in range(2,24,3)]
        ibegin_fhour=5
        iend_fhour=36  
    ndyfrst_hours=np.array(cls_model.ltforecast_hours,dtype="int32") #模式预报时效
    mask=np.logical_and(ibegin_fhour<=ndyfrst_hours,ndyfrst_hours<=iend_fhour) #限定
    ndyforecast_hours=ndyfrst_hours[mask]
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    #公共参数设定
    cls_itp3d.RGrid_Default   = dyglobalInfo["Default"]["mdl_grid"]  
    cls_itp3d.ltPQSN_vld      = ["2t", "2rh", "10ws"] #检验要素
    #需要插值的要素
    if dyInstantInfo["PQ_shortname"] is not None:
        cls_itp3d.ltPQSN_Obs    = dyInstantInfo["PQ_shortname"]  #实况要素,包括2t, 2rh, 10ws, 10gust, sp, tcc
        #参数名
        cls_itp3d.ltPQSN_eta    = [x for x in dyInstantInfo["PQ_shortname"] if x in cls_itp3d.ltPQSN_vld]   #输出eta的要素名
        #插值结果
        cls_itp3d.ltPQSN_Intp   = dyInstantInfo["PQ_shortname"] + ['10u', '10v']
        #gamma
        cls_itp3d.ltgamma_name  = ['gamma_'+x for x in cls_itp3d.ltPQSN_Intp if x not in ["tcc","10gust"]]
    #最高最低要素
    if dyMaxMinInfo["Interp_Maxmin"]:
        cls_itp3d.ltPQSN_mxmn   = []
        if "2t" in dyInstantInfo["PQ_shortname"]:
            cls_itp3d.ltPQSN_mxmn = cls_itp3d.ltPQSN_mxmn + ['2t_min','2t_max']
        if "2rh" in dyInstantInfo["PQ_shortname"]:
            cls_itp3d.ltPQSN_mxmn = cls_itp3d.ltPQSN_mxmn + ['2rh_min','2rh_max']
        if "10gust" in dyInstantInfo["PQ_shortname"]:
            cls_itp3d.ltPQSN_mxmn = cls_itp3d.ltPQSN_mxmn + ['10ws_max']
    #分辨率和输出文件夹名
    if args.resolution.lower()=="site":
        #读取插值站点的经纬度信息
        sReso      = "Site"
        sReso_dir  = sReso
    else:
        sReso      = args.resolution
        sReso_dir  = "Grid_"+sReso
    print("resolution:"+sReso)
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    # 获得所需的要素信息
    Spath.get_ltsPQ_ltMPQ_shortname(cls_itp3d.ltPQSN_Intp, cls_itp3d.ltPQSN_mxmn, sModel_Region_upper)
    # 读取路径配置文件 Mdl_Obs_Path_Info.ini
    Spath.dRead_Mdl_Obs_path_ini(sRoot_Path)
    #--------------------------------------------------------------------------

    #===============================================================================================================
    #空间插值输出结果检查
    #判断输出是否存在,是否需要继续运行
    lDI_update=False;lDintep_exist_out=[]
    if "i" in args.operation:
        sYMDH_mdl_begin_BJ  = sYMD_mdl_begin+shour_mdl_begin #(北京时间)
        #输出主路径
        sOut_Sub_path       = os.path.join(dyglobalInfo["Path"]["result"], cls_gv.S3_dir, sS3_method,\
                                           sModel_Region, sReso_dir, sYMDH_mdl_begin_BJ[0:4], sYMD_mdl_begin, shour_mdl_begin)
        for iForecast_hour in ndyforecast_hours:
            sForecast_hour = "%03d"%iForecast_hour
            sOut_file_name = sForecast_hour + "_" + sForecast_hour + ".h5"
            sOut_Abs_path  = os.path.join(sOut_Sub_path, sOut_file_name)
            #需要删除无使用eta的数据
            if dyInstantInfo["del_no_eta"] and os.path.exists(sOut_Abs_path):
                inum_eta_attrs = 0
                with h5py.File(sOut_Abs_path,'r') as fh:
                    obj_attrs = fh.attrs.keys()
                    inum_eta_attrs = len(obj_attrs)
                if inum_eta_attrs==0: #说明没有用eta
                    if args.debug>=1:print("del:"+sOut_Abs_path)
                    os.remove(sOut_Abs_path)
            else:
                lDintep_exist_out.append(os.path.exists(sOut_Abs_path))
        lintep_exist_out = all(lDintep_exist_out)
        lintep_alive_out = (not lintep_exist_out) or (lintep_exist_out and args.update!=0)
        #i参数&所有文件都存在
        if not lintep_alive_out and "i" in args.operation:
            print("DI_No_update:"+sOut_Sub_path)
            lDI_update=True
    #===============================================================================================================
  
    #===============================================================================================================
    #时间插值输出结果检查
    lTI_update=False;lTintep_exist_out=[]
    if "i" in args.operation and dyInstantInfo["Interp_Time"]:
        #如果要时间插值,哪些预报时效需要插值
        ltTInterp_hour=[]
        for ihb in ndyforecast_hours[0:-1]:
            ltTInterp_hour = ltTInterp_hour + [ihb+1,ihb+2]
        sOut_sub_path  = os.path.join(dyglobalInfo["Path"]["result"], cls_gv.S3_dir, sS3_method, sModel_Region, sReso_dir,\
                                      sYMDH_mdl_begin_BJ[0:4], sYMD_mdl_begin, shour_mdl_begin)
        for iThour in ltTInterp_hour:
            sIfh_b         = "%03d"%iThour
            sOut_file_name = sIfh_b+"_"+sIfh_b+".h5"
            sOut_abs_path  = os.path.join(sOut_sub_path, sOut_file_name)
            if not os.path.exists(sOut_abs_path):
                lTintep_exist_out.append(os.path.exists(sOut_abs_path))  
        lintep_exist_out = all(lTintep_exist_out)
        lintep_alive_out = (not lintep_exist_out) or (lintep_exist_out and args.update!=0)
        #i参数&所有文件都存在
        if not lintep_alive_out:
            print("TI_No_update:"+sOut_Sub_path)
            lTI_update=True
    #===============================================================================================================
       
    #===============================================================================================================
    #求参输出结果检查
    leta_update=False;lteta_exist_out=[]
    if "p" in args.operation:
        #根据输入的BJ时间计算需要参数择优的模式起报+预报时间=输入实况时间
        dymdl_ftime_info = {}; ltYMDH_mdl_begin=[]; 
        for iForecast_hour in range(ibegin_fhour,iend_fhour+1):
            sForecast_hour = "%03d"%iForecast_hour
            sYMDH_mdl_begin_BJ = cls_myfun.dBefAftDate2(sInterp_YMDH,"hour",-iForecast_hour)
            if sYMDH_mdl_begin_BJ[8:] not in lthour_mdl_begin: continue
            sYMDH_mdl_begin_UTC = cls_myfun.dLocalT_cvt_UTC(sYMDH_mdl_begin_BJ) #(世界时间)
            dymdl_ftime_info[sYMDH_mdl_begin_BJ] = [sYMDH_mdl_begin_UTC, iForecast_hour, sForecast_hour, sInterp_YMDH]
            ltYMDH_mdl_begin.append(sYMDH_mdl_begin_BJ) #计算最优参数时的模式开始YMDH时间
        if len(ltYMDH_mdl_begin)==0 and args.operation=="p":sys.exit()
        #每天参数输出子路径
        ltprint_info=[]
        for idy, sYMDH_mdl_begin_BJ in enumerate(ltYMDH_mdl_begin[0:]):
            iForecast_hour      = dymdl_ftime_info[sYMDH_mdl_begin_BJ][1]
            sForecast_hour      = dymdl_ftime_info[sYMDH_mdl_begin_BJ][2]
            if iForecast_hour not in ndyforecast_hours: continue #ec不在3h点上的时效=跳过
            ltprint_info.append(sYMDH_mdl_begin_BJ+"_"+sForecast_hour)
            sOut_Sub_path  = os.path.join(dyglobalInfo["Path"]["result"], cls_gv.S3_dir, sS3_method, sModel_Region, sReso_dir,
                                        sYMDH_mdl_begin_BJ[0:4], sYMDH_mdl_begin_BJ[0:8], sYMDH_mdl_begin_BJ[8:], cls_itp3d.seta_dir)
            for sPhyQ_shortname in cls_itp3d.ltPQSN_eta:
                #输出绝对路径
                sOut_file_name = "_".join([sForecast_hour, sPhyQ_shortname, "eta"]) +".h5" #最优参数文件名
                sOut_Abs_path  = os.path.join(sOut_Sub_path,  sOut_file_name)
                lteta_exist_out.append(os.path.exists(sOut_Abs_path))
        leta_exist_out= all(lteta_exist_out) #输出插值文件不存在=h5不存在 or h5存在&必须更新>1
        leta_alive_out = (not leta_exist_out) or (leta_exist_out and args.update!=0)
        #只有p参数&所有存在
        if not leta_alive_out:
            if ltprint_info!=[]: print("eta_No_update:",ltprint_info, "=", sInterp_YMDH)
            if "p"==args.operation: sys.exit()
            leta_update=True
            print("="*40)
    #===============================================================================================================
    if lDI_update and lTI_update and leta_update: sys.exit()

    #===============================================================================================================
    #模式空间信息
    if sModel_Region_upper in ["EC_12P5KM"]:
        sReso_mdl = "12P5km" #地面层
        iround    = 3        #保留经纬度信息
    elif sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_GFS","CMA_GFS"]:
        sReso_mdl = "12P5km"
        iround    = 4
    elif sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
        sReso_mdl = "3km"
        iround    = 2
    #读取模式分辨率的真实地形文件
    #M4格式
    if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]: #地形文件已经配套好,不用剪裁
        #地形
        sm4_abs_path  = os.path.join(sRoot_Path,"lib","terrain",sModel_Region_upper,"Terrain_"+sReso_mdl+"."+dyInstantInfo["dem_format"])
        if not os.path.exists(sm4_abs_path):
            print("No:"+sm4_abs_path)
            sys.exit()
        else:
            ndyterrain_mdl, lthead = cls_itp3d.dRead_d4_scalar(sm4_abs_path) #上-下(北-南) 左-右(西-东)
            ndyterrain_mdl[ndyterrain_mdl<=-1000.]=0
            ndyterrain_mdl[ndyterrain_mdl>=9000.]=9000
            ndyterrain_mdl=np.flipud(ndyterrain_mdl) #变为上-下(南-北) 左-右(西-东)=(1671,2501)=4179171=3km范围
        #分区
        sm4_abs_path = os.path.join(sRoot_Path,"lib","terrain",sModel_Region_upper,"Zoning_"+sReso_mdl+"."+dyInstantInfo["dem_format"])
        if not os.path.exists(sm4_abs_path):
            print("No:"+sm4_abs_path)
            mask_area_mdl=ndyterrain_mdl>0
        else:
            ndyzoning_mdl, lthead = cls_itp3d.dRead_d4_scalar(sm4_abs_path) #上-下(北-南) 左-右(西-东)
            ndyzoning_mdl[ndyzoning_mdl>=60]=0
            ndyzoning_mdl=np.flipud(ndyzoning_mdl) #变为上-下(南-北) 左-右(西-东)
            #中国区域5km的mask
            mask_area_mdl=ndyzoning_mdl>0 #上-下(南-北)
    #tif格式(智网全区域)
    else:
        #地形
        stif_abs_path = os.path.join(sRoot_Path,"lib","terrain",sModel_Region_upper,"Terrain_"+sReso_mdl+"."+dyInstantInfo["dem_format"])  #坐标60-0 70-140= 1201,1401 缺损-2147483647
        if not os.path.exists(stif_abs_path):
            print("No:"+stif_abs_path)
            sys.exit()
        else:
            ndyterrain_mdl = cls_itp3d.dRead_Terrain(stif_abs_path) #返回一个numpy n-d数组 上-下(北-南) 左-右(西-东)
        #分区
        stif_abs_path = os.path.join(sRoot_Path,"lib","terrain",sModel_Region_upper,"Zoning_"+sReso_mdl+"."+dyInstantInfo["dem_format"])
        if not os.path.exists(stif_abs_path):
            print("No:"+stif_abs_path)
            mask_area_mdl=ndyterrain_mdl>0
        else:
            ndyzoning_mdl, mask_area_mdl = cls_itp3d.dRead_Zoning(stif_abs_path)#返回一个numpy n-d数组 上-下(北-南) 左-右(西-东)
    #-------------------------------------------------------------------------------------------------------------------------
    #模式近地面层经纬度信息(左-右:西-东 上-下:南-北)
    dylonlat_SL_IG_mdl={"begin_lon":cls_model.latlon_info.lon_start,
                        "end_lon"  :cls_model.latlon_info.lon_end,
                        "begin_lat":cls_model.latlon_info.lat_start,
                        "end_lat"  :cls_model.latlon_info.lat_end,
                        "lon_res"  :cls_model.latlon_info.lon_precision,
                        "lat_res"  :cls_model.latlon_info.lat_precision}
    dylonlat_SL_IG_mdl=cls_itp3d.dlonlat_info(dylonlat_SL_IG_mdl, around=iround, idebug=args.debug, slabel=sModel_Region)
    #EC多层智网范围的25k地理信息
    if sModel_Region_upper=="EC_12P5KM":
        dylonlat_ML_IG_mdl={"begin_lon":cls_model.latlon_info.lon_start,
                            "end_lon"  :cls_model.latlon_info.lon_end,
                            "begin_lat":cls_model.latlon_info.lat_start,
                            "end_lat"  :cls_model.latlon_info.lat_end,
                            "lon_res"  :0.25, "lat_res"  :0.25} #=481×561
        #(EC多层: 左-右:西-东 上-下:南-北)
        dylonlat_ML_IG_mdl=cls_itp3d.dlonlat_info(dylonlat_ML_IG_mdl, around=2,idebug=args.debug,slabel="EC_ML_IG")
        #找出在12.5km数据中的25km公共索引(1维数组)
        mask2d_x_lon_12P5km_to_25km=np.in1d(dylonlat_SL_IG_mdl["ndy2d_x_lon"].flatten(),dylonlat_ML_IG_mdl["ndy1d_x_lon"].flatten()) #返回一个与ar1长度相同的布尔数组,ar1的元素在ar2中=True
        #返回一个与ar1长度相同的布尔数组,ar1的元素在ar2中=True
        mask2d_y_lat_12P5km_to_25km=np.in1d(dylonlat_SL_IG_mdl["ndy2d_y_lat"].flatten(),dylonlat_ML_IG_mdl["ndy1d_y_lat"].flatten()) #42607100个点=1维
        #在原12.5km数据中,与25km数据公共部分点的布尔索引  
        mask2d_common_12P5km_to_25km = (mask2d_y_lat_12P5km_to_25km * mask2d_x_lon_12P5km_to_25km).reshape(dylonlat_SL_IG_mdl["tpshape_lonlat"]) #与1km保持一致,6001*7100=42607100个点 True/False
    else:
        dylonlat_ML_IG_mdl           = None
        mask2d_common_12P5km_to_25km = None
    #模式近地面地理信息总汇
    dylonlat_SL_IG_mdl["alt"]                  = ndyterrain_mdl       #上-下(南-北)
    dylonlat_SL_IG_mdl["size"]                 = dylonlat_SL_IG_mdl["ndy2d_x_lon"].size
    dylonlat_SL_IG_mdl["mask_area"]            = mask_area_mdl
    dymdl_Geog                                 = {}
    dymdl_Geog["lonlat_SL_IG_mdl"]             = dylonlat_SL_IG_mdl   #EC:0-60.0  CMA-GFS:0.12-60.125 和 0.0625-60.0625
    dymdl_Geog["lonlat_ML_IG_mdl"]             = dylonlat_ML_IG_mdl
    dymdl_Geog["mask2d_common_12P5km_to_25km"] = mask2d_common_12P5km_to_25km
    #===============================================================================================================


    #===============================================================================================================
    #目标插值结果空间信息
    #站点
    if args.resolution.lower()=="site":
        #读取插值站点的经纬度信息
        dyobs_info = {"Obs_Path":cls_obsdb.obs_info[sReso_dir]["path"]}
        #读站点实况主路径
        if args.debug>=2:print("site_path:",cls_obsdb.obs_info['Site']["path"])
        #自定义站点路径
        if os.path.exists(dySiteInfo["custom_path"]):
            sIn_Abs_path = dySiteInfo["custom_path"]
        else:
            if args.site_name is None:
                args.site_name=cls_obsdb.obs_info["Site"]["site_name"]
            sIn_Abs_path = os.path.join(sRoot_Path, "Parameter", args.site_name)
            if not os.path.exists(sIn_Abs_path):
                sIn_Abs_path = os.path.join(sRoot_Path, "Parameter", args.site_name)
        if args.debug>=2:print("site_path:"+sIn_Abs_path)
        #读取站点信息
        dtsite = cls_site.dRead_Station_Info(sIn_Abs_path)
        ltall_sites=sorted(list(dtsite.keys()))
        ssite_code_name="site_code"
        #转为dataframe
        ltcols_name=["Province_py","Lon","Lat","Alt","Site_name","Province_ch"]
        dfsite=pd.DataFrame.from_dict(dtsite, orient='index')
        dfsite.columns=ltcols_name
        dfsite.index.name=ssite_code_name
        dfsite.reset_index(level=0, inplace=True) 
        if args.debug>=2:print("site Num.:",len(ltall_sites))
        #排除模式数据区域外站点
        ltSlt_Site_Code=[];ltSlt_Site_Lon=[];ltSlt_Site_Lat=[];ltSlt_Site_Alt=[]
        for scode in cls_site.ltSlt_Site_Code:
            if cls_model.latlon_info.lon_start<=dtsite[scode][1] and \
                dtsite[scode][1]<=cls_model.latlon_info.lon_end and \
                cls_model.latlon_info.lat_start<=dtsite[scode][2] and \
                dtsite[scode][2]<=cls_model.latlon_info.lat_end:
                ltSlt_Site_Code.append(scode)
                ltSlt_Site_Lon.append(dtsite[scode][1])
                ltSlt_Site_Lat.append(dtsite[scode][2])
                ltSlt_Site_Alt.append(dtsite[scode][3])
        #插值经纬度海拔信息
        dyIntp_info={"lon" :np.array(ltSlt_Site_Lon),
                    "lat" :np.array(ltSlt_Site_Lat),
                    "alt" :np.array(ltSlt_Site_Alt),
                    "size":len(ltSlt_Site_Code)}
    #格点
    else:
        #读取插值范围和分辨率信息
        dyIntp_info     = {} #插值点信息
        dycut_obs       = {}
        dyobs_info      = {"Obs_Path":cls_obsdb.obs_info[sReso_dir]["path"]} #读取插值5km/1km格点经纬度信息(5×5km,1×1km) 顺序是先5km后1km
        #插值地理信息初始化
        dylonlat_rlt = cls_itp3d.dGlonlat_init([cls_obsdb.obs_info[sReso_dir]["lon_west"],  cls_obsdb.obs_info[sReso_dir]["lon_east"],  cls_obsdb.obs_info[sReso_dir]["reso_lon"],\
                                                cls_obsdb.obs_info[sReso_dir]["lat_south"], cls_obsdb.obs_info[sReso_dir]["lat_north"], cls_obsdb.obs_info[sReso_dir]["reso_lat"]])
        #插值场地理信息矩阵信息
        dylonlat_rlt = cls_itp3d.dlonlat_info(dylonlat_rlt,slabel="rlt_"+sReso, idebug=args.debug) #字典中2d数组=上-下(南-北) 左-右(西-东)
        #读取中国sReso各省编码Mask文件-插值结果分辨率
        stif_abs_path = os.path.join(sRoot_Path,"lib","terrain", dyInstantInfo["dem_head"]+"_"+sReso,"Zoning_"+sReso+".tif")  #坐标60-0 70-140 = 1201, 1401
        ndyzoning_rlt, mask_area_rlt = cls_itp3d.dRead_Zoning(stif_abs_path)#返回一个numpy 2-d数组 上-下(南-北) 左-右(西-东) 
        #检验指定省份
        if dyInstantInfo["Prov_code"] is not None:
            mask_selt_prov = cls_itp3d.dSelect_Provinces(ndyzoning_rlt, dyInstantInfo["Prov_code"]) #指定哪些省份= 5km=(1201, 1401)
        #读取中国sReso地形文件-插值结果分辨率
        stif_abs_path  = os.path.join(sRoot_Path,"lib","terrain",dyInstantInfo["dem_head"]+"_"+sReso,"Terrain_"+sReso+".tif")  #坐标60-0 70-140= 1201,1401 缺损-2147483647
        ndyterrain_obs = cls_itp3d.dRead_Terrain(stif_abs_path) #返回一个numpy n-d数组 上-下(南-北) 左-右(西-东) 5km数据在渤海湾海面有点问题
        #剪裁插值地形和掩膜数据和实况
        if sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_GFS","CMA_GFS"]:
            if cls_model.latlon_info.lat_start==0.0625 and cls_model.latlon_info.lat_end==60.0625: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
                if sReso=="5km":
                    icut_y_lat_num=[2, 1201, 1] #南-北=左-右,截取0-1行南边数据,从0.1度开始-60度
                    flat_start=0.1
                elif sReso=="1km":
                    icut_y_lat_num=[7, 7001, 1]
                    flat_start=0.07
                dycut_obs[sReso]   = icut_y_lat_num
                mask_area_rlt  = mask_area_rlt[icut_y_lat_num[0]:icut_y_lat_num[1]:icut_y_lat_num[2],:]
                ndyzoning_rlt  = ndyzoning_rlt[icut_y_lat_num[0]:icut_y_lat_num[1]:icut_y_lat_num[2],:]
                ndyterrain_obs = ndyterrain_obs[icut_y_lat_num[0]:icut_y_lat_num[1]:icut_y_lat_num[2],:] #截断南边
                if dyInstantInfo["Prov_code"] is not None:
                    mask_selt_prov = mask_selt_prov[icut_y_lat_num[0]:icut_y_lat_num[1]:icut_y_lat_num[2],:]
                #插值地理信息重新初始化——配套截取的
                dylonlat_rlt = cls_itp3d.dGlonlat_init([cls_obsdb.obs_info[sReso_dir]["lon_west"], cls_obsdb.obs_info[sReso_dir]["lon_east"] , cls_obsdb.obs_info[sReso_dir]["reso_lon"],\
                                                        flat_start                          , cls_obsdb.obs_info[sReso_dir]["lat_north"], cls_obsdb.obs_info[sReso_dir]["reso_lat"]])
                #插值场地理信息矩阵信息
                dylonlat_rlt = cls_itp3d.dlonlat_info(dylonlat_rlt,slabel="rlt_"+sReso, around=3, idebug=args.debug) #字典中2d数组=上-下(南-北) 左-右(西-东)
        elif sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
            if cls_model.latlon_info.lat_start==10 and cls_model.latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
                if sReso=="5km":
                    icut_3km_y_lat_num=[200, 1201, 1] #南-北=左-右,截取0-200行南边数据
                elif sReso=="1km":
                    icut_3km_y_lat_num=[1000, 7001, 1]
                dycut_obs[sReso]= icut_3km_y_lat_num
                mask_area_rlt   = mask_area_rlt[icut_3km_y_lat_num[0]:icut_3km_y_lat_num[1]:icut_3km_y_lat_num[2],:]
                ndyzoning_rlt   = ndyzoning_rlt[icut_3km_y_lat_num[0]:icut_3km_y_lat_num[1]:icut_3km_y_lat_num[2],:]
                ndyterrain_obs  = ndyterrain_obs[icut_3km_y_lat_num[0]:icut_3km_y_lat_num[1]:icut_3km_y_lat_num[2],:] #截断南边
                if dyInstantInfo["Prov_code"] is not None:
                    mask_selt_prov = mask_selt_prov[icut_3km_y_lat_num[0]:icut_3km_y_lat_num[1]:icut_3km_y_lat_num[2],:]        
                #插值地理信息重新初始化——配套截取的
                dylonlat_rlt = cls_itp3d.dGlonlat_init([cls_obsdb.obs_info[sReso_dir]["lon_west"], cls_obsdb.obs_info[sReso_dir]["lon_east"],  cls_obsdb.obs_info[sReso_dir]["reso_lon"],\
                                                        cls_model.latlon_info.lat_start          , cls_obsdb.obs_info[sReso_dir]["lat_north"], cls_obsdb.obs_info[sReso_dir]["reso_lat"]])
                #插值场地理信息矩阵信息
                dylonlat_rlt = cls_itp3d.dlonlat_info(dylonlat_rlt,slabel="rlt_"+sReso, idebug=args.debug) #字典中2d数组=上-下(南-北) 左-右(西-东)
        #插值场经纬度海拔信息
        dyIntp_info              = dylonlat_rlt
        dyIntp_info["cut_obs"]   = dycut_obs
        ndy2d_x_lon              = dylonlat_rlt["ndy2d_x_lon"].copy()
        ndy2d_x_lon[:,-1]        = ndy2d_x_lon[:,-1]-0.001  #插值右=东边界处理
        ndy2d_y_lat              = dylonlat_rlt["ndy2d_y_lat"].copy()
        ndy2d_y_lat[-1,:]        = ndy2d_y_lat[-1,:]-0.001  #插值下=北边界处理
        dyIntp_info["lon"]       = ndy2d_x_lon.flatten().astype("float32")
        dyIntp_info["lat"]       = ndy2d_y_lat.flatten().astype("float32")
        dyIntp_info["2dshape"]   = dylonlat_rlt["tpshape_lonlat"]
        dyIntp_info["size"]      = dylonlat_rlt["ndy2d_y_lat"].size
        dyIntp_info["alt"]       = ndyterrain_obs.flatten()
        dyIntp_info["zoning"]    = ndyzoning_rlt
        dyIntp_info["mask_area"] = mask_area_rlt  #全国2d:上-下(南-北)
        dyIntp_info["mask_prov"] = mask_selt_prov #所选省
        if dyIntp_info["lat"].size != dyIntp_info["alt"].size:
            print("Err Intp lat alt",dyIntp_info["lat"].size, " /=",dyIntp_info["alt"].size)
    if args.debug>=1:cls_myfun.dPrint_run_time()
    #===============================================================================================================

    #===============================================================================================================
    #最新模式数据插值
    dyInterp_spc_nfh={}; dymdl_rdata_nfh={}
    if "i" in args.operation:
        print("-------------Spatial Interp----------------------------")
        dynowtime_vs_bhours = cls_gv.dS3_nowtime_vs_beginhour(sModel_name_lower,sRegion_lower)
        ltmdl_begin_hour    = dynowtime_vs_bhours[int(sInterp_YMDH[8:])] #多往前1天,因为预报时效有超过24小时
        shour_mdl_begin     = "%02d"%ltmdl_begin_hour[0]
        sYMD_mdl_begin      = cls_myfun.dtimes_ago(sInterp_YMDH[0:8], ltmdl_begin_hour[1])
        #(北京时间)
        sYMDH_mdl_begin_BJ  = sYMD_mdl_begin+shour_mdl_begin
        #(世界时间)
        sYMDH_mdl_begin_UTC = cls_myfun.dLocalT_cvt_UTC(sYMDH_mdl_begin_BJ)
        #拆分
        iyear_bj,  imonth_bj,  iday_bj, ihour_bj   = cls_myfun.ddate_hour_split_1(sYMDH_mdl_begin_BJ)
        iyear_utc, imonth_utc, iday_utc, ihour_utc = cls_myfun.ddate_hour_split_1(sYMDH_mdl_begin_UTC)
        print("YMDH_mdl:"+sYMDH_mdl_begin_BJ,ndyforecast_hours[0],"-",ndyforecast_hours[-1], '('+str(ndyforecast_hours.size)+')')
        #------------------------------------------------------------------------------------------------------------------
        #瞬时预报时效循环
        ltfhours=[]; dypath_info={}; dypath_mdl={}
        for iForecast_hour in ndyforecast_hours:
            sForecast_hour = "%03d"%iForecast_hour

            # 拼接NC数据全要素路径
            sIn_mdl_abs_path_dt, Nexist = Spath.mdl_path(sYMDH_mdl_begin_BJ, sModel_Region_upper, sTime_range=sForecast_hour)
            lexist_mdl = False if Nexist else True

            dypath_mdl[iForecast_hour]=sIn_mdl_abs_path_dt
            #输入-当天6-48h的EC原始文件存在=可以插值
            if lexist_mdl:
                #输出插值文件
                ltout_info=[];dyattr={"eta_path":None}
                sOut_file_name = sForecast_hour + "_" + sForecast_hour + ".h5"
                #输出主路径
                sOut_Sub_path  = os.path.join(dyglobalInfo["Path"]["result"], cls_gv.S3_dir, sS3_method,\
                                            sModel_Region, sReso_dir, sYMDH_mdl_begin_BJ[0:4],sYMD_mdl_begin, shour_mdl_begin)
                if not os.path.exists(sOut_Sub_path): 
                    try:
                        os.makedirs(sOut_Sub_path) #可能会出现错误
                    except OSError:
                        pass
                sOut_Abs_path  = os.path.join(sOut_Sub_path, sOut_file_name)
                lalive = os.path.exists(sOut_Abs_path)
                #输出插值文件不存在=h5不存在 or h5存在&必须更新>1
                if (not lalive) or (lalive and args.update!=0):
                    dyeta_file_name={}
                    for sPhyQ_shortname in cls_itp3d.ltPQSN_eta:
                        sIn_1d_eta_abs_path, sIn_cmn_eta_abs_path = cls_itp3d.deta_path(dyglobalInfo["Path"]["result"], cls_gv.S3_dir, sS3_method, \
                                                                                        sModel_Region, sReso_dir, cls_itp3d.seta_dir, sPhyQ_shortname, \
                                                                                        sYMD_mdl_begin, shour_mdl_begin, iForecast_hour)
                        dyeta_file_name[sPhyQ_shortname]=sIn_1d_eta_abs_path
                        #找eta公共路径=找不到每天路径时找公共路径
                        if (not dyInstantInfo["recall"]) and (not os.path.exists(sIn_1d_eta_abs_path)):
                            dyeta_file_name[sPhyQ_shortname]=sIn_cmn_eta_abs_path
                    #预报时效在外层保存输出路径和参数路径，
                    ltout_info=[sOut_Abs_path, dyeta_file_name] #必须要插值的路径
                else:
                    print("No_update:"+sOut_Abs_path)
                #保存不同预报时效路径信息，不同时效下哪些分辨率需要被计算
                if ltout_info!=[]:
                    ltfhours.append(iForecast_hour)  #必须要插值的时效
                    dypath_info[iForecast_hour] = [sIn_mdl_abs_path_dt, ltout_info]
            else:
                print("NO:", Nexist)
        #------------------------------------------------------------------------------------------------------------------
        #空间插值
        if not lDI_update:
            dyClass       = {"cls_obsdb":cls_obsdb,"cls_model":cls_model, "Spath":Spath}
            dyCommon_Para = {"sModel_Region_upper":sModel_Region_upper, "sReso":sReso, "sYMDH_mdl_begin_BJ":sYMDH_mdl_begin_BJ,
                            "Obs_Path":cls_obsdb.obs_info[sReso_dir]["path"],"Class":dyClass}
            if sReso=="Site":
                dyCommon_Para["Site_Code"]=ltSlt_Site_Code
            #并行-预报时效-3d空间插值, dyIntp_info
            if dyPool["FH_parallel"]:
                if len(ltfhours)>=1: #等于0表明无需更新
                    print("FH_Parallel")
                    dyInterp_spc_nfh, dymdl_rdata_nfh = cls_itp3d.dPool_mdl_3d_Interp_nPQ(ltfhours[0:], dyIntp_info, dymdl_Geog, dypath_info, dyPara_ini_info, dyCommon_Para)
            #串行-预报时效-3d空间插值
            else:
                print("FH_Serial")
                dyInterp_spc_nfh, dymdl_rdata_nfh = cls_itp3d.dSerial_mdl_3d_Interp_nPQ(ltfhours[0:], dyIntp_info, dymdl_Geog, dypath_info, dyPara_ini_info, dyCommon_Para)
            if args.debug>=1:cls_myfun.dPrint_run_time()
        #===============================================================================================================

        #===============================================================================================================
        #12-36日最高最低求取
        if dyMaxMinInfo["Interp_Maxmin"]:
            print("-------------Maxmin Interp----------------------------")
            #最高最低值求时间
            dyMaxMin_fhours={}
            if dyMaxMinInfo["Interp_Maxmin"]:
                for sbehour in dyMaxMinInfo["forecast_time"]:
                    ltbehour = sbehour.split("_")
                    lthours  = [ih for ih in range(int(ltbehour[0])+3,int(ltbehour[1])+1,3)]
                    dyMaxMin_fhours[sbehour]=lthours
            dyClass       = {"cls_obsdb":cls_obsdb,"cls_model":cls_model, "Spath": Spath}
            dyCommon_Para = {"update":args.update, "sModel_Region":sModel_Region, "sReso":sReso, "sReso_dir":sReso_dir, "S3_dir":cls_gv.S3_dir, "sS3_method":sS3_method, 
                            "sYMDH_mdl_begin_BJ":sYMDH_mdl_begin_BJ, "dyMaxMin_fhours":dyMaxMin_fhours,
                            "rlt_Path":dyglobalInfo["Path"]["result"], "Obs_Path":cls_obsdb.obs_info[sReso_dir]["path"], "Class":dyClass}
            if sReso=="Site":
                dyCommon_Para["Site_Code"]=ltSlt_Site_Code    
            #日最高最低值求取-分辨率循环
            cls_itp3d.dSerial_Max_Min_nPQ(dyInterp_spc_nfh, dyIntp_info, dymdl_rdata_nfh, dymdl_Geog, dypath_mdl, dyPara_ini_info, dyCommon_Para)
            if args.debug>=1:cls_myfun.dPrint_run_time()
        #===============================================================================================================
  
    #===============================================================================================================
    #时间插值
    if "i" in args.operation and dyInstantInfo["Interp_Time"] and (not lTI_update):
        print("-------------FH_Time Interp----------------------------")
        #如果要时间插值,哪些预报时效需要插值
        ltInterp_fh_be=[[ihb,ihe] for ihb,ihe in zip(ndyforecast_hours[0:-1],ndyforecast_hours[1:])]
        sIn_sub_path  = os.path.join(dyglobalInfo["Path"]["result"],cls_gv.S3_dir,sS3_method,sModel_Region,sReso_dir,\
                                    sYMDH_mdl_begin_BJ[0:4],sYMD_mdl_begin, shour_mdl_begin)
        dyClass       = {"cls_obsdb":cls_obsdb,"cls_model":cls_model}
        dyCommon_Para = {"sModel_Region_upper":sModel_Region_upper, "sReso":sReso, "sYMDH_mdl_begin_BJ":sYMDH_mdl_begin_BJ,
                        "Obs_Path":cls_obsdb.obs_info[sReso_dir]["path"],"Class":dyClass}
        dyCommon_Para["Interp_keys"]  = cls_itp3d.ltPQSN_Intp+cls_itp3d.ltgamma_name 
        dyCommon_Para["sIn_sub_path"] = sIn_sub_path
        dyCommon_Para["update"]       = args.update
        if len(ltInterp_fh_be)>=1: #等于0表明无需更新
            cls_itp3d.dPool_time_Interp_nPQ(ltInterp_fh_be[0:], dyInterp_spc_nfh, dyPara_ini_info, dyCommon_Para)
    if args.debug>=1:cls_myfun.dPrint_run_time()
    #===============================================================================================================
  

    ################################################################################################################################
    #最优参数求解
    if "p" in args.operation:
        print("---------------best_eta-----------------------------")
        if sReso=="1km":
            pass
        elif sReso=="Site":
            dyPool["BT_parallel"]   = True   
            dyPool["Para_parallel"] = False  
        #变量简写名
        ltPara_Loss_cycle = np.round(np.arange(0.1,1.1,0.1),1,).astype("float32")
        #----------------------------------------------------------------------------
        #模式起报和预报时间循环
        dyBP_Path={}; ltYMDH_FH_mdl=[]
        for idy, sYMDH_mdl_begin_BJ in enumerate(ltYMDH_mdl_begin[0:]): 
            sYMDH_mdl_begin_UTC = dymdl_ftime_info[sYMDH_mdl_begin_BJ][0]
            iForecast_hour      = dymdl_ftime_info[sYMDH_mdl_begin_BJ][1]
            sForecast_hour      = dymdl_ftime_info[sYMDH_mdl_begin_BJ][2]
            if iForecast_hour not in ndyforecast_hours: continue #ec不在3h点上的时效=跳过
            #模式预报路径---------------------------------------------------------------------------------------------
            sIn_mdl_abs_path_dt, Nexist = Spath.mdl_path(sYMDH_mdl_begin_BJ, sModel_Region_upper, sTime_range=sForecast_hour)
            lexist_mdl = False if Nexist else True

            #每天参数输出子路径---------------------------------------------------------------------------------------
            sOut_Sub_path  = os.path.join(dyglobalInfo["Path"]["result"], cls_gv.S3_dir, sS3_method, sModel_Region, sReso_dir,
                                        sYMDH_mdl_begin_BJ[0:4], sYMDH_mdl_begin_BJ[0:8], sYMDH_mdl_begin_BJ[8:], cls_itp3d.seta_dir)
            #恒定参数路径
            sOut_Sub_path2 = os.path.join(dyglobalInfo["Path"]["result"],cls_gv.S3_dir,sS3_method,sModel_Region, sReso_dir,\
                                        cls_itp3d.seta_dir, sYMDH_mdl_begin_BJ[8:])
            #要素循环
            dyOut_Path={}
            for sPhyQ_shortname in cls_itp3d.ltPQSN_eta:
                #实况

                #站点实况路径
                if sReso=="Site":
                    sPQ_name = cls_itp3d.dyInstPQSN_to_obsdir[sPhyQ_shortname][0]
                    sPQ_type = cls_itp3d.dyInstPQSN_to_obsdir[sPhyQ_shortname][1]
                    sIn_obs_sub_path = os.path.join(dyobs_info["Obs_Path"], sInterp_YMDH[0:4], sPQ_name, sPQ_type,
                                                    sInterp_YMDH[0:8])
                    sobs_file_name = sInterp_YMDH+"00"+".h5"
                    sIn_obs_abs_path = os.path.join(sIn_obs_sub_path, sobs_file_name)
                    lexist_obs = os.path.exists(sIn_obs_abs_path)
                #格点实况路径
                else:
                    sIn_obs_abs_path_dt, lexist_obs = Spath.obs_path(sYMDH_mdl_begin_BJ, sReso_dir, sPhyQ_shortname)
                    sIn_obs_abs_path = sIn_obs_abs_path_dt

                #输出绝对路径------------------------------------------------------------------------------------------
                sOut_file_name = "_".join([sForecast_hour, sPhyQ_shortname, "eta"]) +".h5" #最优参数文件名
                sOut_Abs_path  = os.path.join(sOut_Sub_path,  sOut_file_name)
                sOut_Abs_path1 = os.path.join(sOut_Sub_path2, sOut_file_name)
                lexist_out     = os.path.exists(sOut_Abs_path)
                #输出插值文件不存在=h5不存在 or h5存在&必须更新>1
                lalive_out = (not lexist_out) or (lexist_out and args.update!=0)
                if not lalive_out: 
                    print("No_update:"+sOut_Abs_path)
                else:
                    #实况和模式数据存在=可以运算
                    if lexist_obs and lexist_mdl:
                        #保存
                        dyOut_Path[sPhyQ_shortname] = {"out":sOut_Abs_path, "out1":sOut_Abs_path1}
                        #建立文件夹
                        if not os.path.exists(sOut_Sub_path):
                            try:
                                os.makedirs(sOut_Sub_path) #并会出现错误
                            except OSError:
                                pass
                        if not os.path.exists(sOut_Sub_path2): 
                            try:
                                os.makedirs(sOut_Sub_path2) #并会出现错误
                            except OSError:
                                pass
                    #缺一个文件
                    else:
                        if not lexist_obs:
                            print("No:", sIn_obs_abs_path)
                        if not lexist_mdl:
                            print("NO:", Nexist)
            if dyOut_Path!={}:
                sYMDH_FH_mdl = sYMDH_mdl_begin_BJ + "_" + sForecast_hour
                ltYMDH_FH_mdl.append(sYMDH_FH_mdl)
                dyOut_Path.update({"mdl":sIn_mdl_abs_path_dt})
                dyBP_Path[sYMDH_FH_mdl] = dyOut_Path
        #需要更新输出
        if len(dyBP_Path)!=0:
            #格点
            if sReso!="Site":
                #要素循环
                dyGObs_PhyQ={}
                for sPhyQ_shortname in cls_itp3d.ltPQSN_eta:
                    #格点实况路径
                    sIn_obs_abs_path_dt, lexist = Spath.obs_path(sYMDH_mdl_begin_BJ, sReso_dir, sPhyQ_shortname, sTime_range='000')
                    if args.debug>=1:print("GO:", sIn_obs_abs_path_dt)
                    #-----------------------------------------------
                    #标量 
                    if sPhyQ_shortname in ["2t",'2rh']:
                        #上-下 南-北 5km=(1201,1401)=1682601
                        # 修改 读取数据函数
                        ndyGObs_PhyQ = cls_obsdb.dRObs_Nc(sIn_obs_abs_path_dt[sPhyQ_shortname], sPhyQ_shortname)
                        ndyGObs_PhyQ = np.flipud(ndyGObs_PhyQ) # 数据回正

                        ndyGObs_PhyQ=ndyGObs_PhyQ.astype("float32")
                        #剪裁插值地形和掩膜数据
                        if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
                            if cls_model.latlon_info.lat_start==10 and cls_model.latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
                                ndyGObs_PhyQ = ndyGObs_PhyQ[dycut_obs[sReso][0]:dycut_obs[sReso][1]:dycut_obs[sReso][2],:]
                        elif sModel_Region_upper in ["GRAPES_25KM"]:
                            if cls_model.latlon_info.lat_start==0.125 and cls_model.latlon_info.lat_end==60.125:
                                ndyGObs_PhyQ = ndyGObs_PhyQ[dycut_obs[sReso][0]:dycut_obs[sReso][1]:dycut_obs[sReso][2],:]
                        elif sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_GFS","CMA_GFS"]:
                            if cls_model.latlon_info.lat_start==0.0625 and cls_model.latlon_info.lat_end==60.0625:
                                ndyGObs_PhyQ = ndyGObs_PhyQ[dycut_obs[sReso][0]:dycut_obs[sReso][1]:dycut_obs[sReso][2],:]
                        if ndyGObs_PhyQ.size!=dyIntp_info['size']: #说明读取到实况文件,但是数据错误,数据大小与插值点不一致
                            if args.debug>=1:print("Err:",ndyGObs_PhyQ.size,ndyGObs_PhyQ.size)
                            continue
                        dyGObs_PhyQ[sPhyQ_shortname]=ndyGObs_PhyQ
                    #矢量
                    else:
                        # 读取数据函数
                        ndyu = cls_obsdb.dRObs_Nc(sIn_obs_abs_path_dt['10u'], '10u')
                        ndyv = cls_obsdb.dRObs_Nc(sIn_obs_abs_path_dt['10v'], '10v')
                        ndyu = np.flipud(ndyu)
                        ndyv = np.flipud(ndyv)

                        ndyu = ndyu.astype("float32")
                        ndyv = ndyv.astype("float32")
                        #剪裁插值地形和掩膜数据
                        if sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
                            if cls_model.latlon_info.lat_start==10 and cls_model.latlon_info.lat_end==60.1: #只有原始模式数据是全区域插值时才需要进行地形和实况剪裁
                                ndyu = ndyu[dycut_obs[sReso][0]:dycut_obs[sReso][1]:dycut_obs[sReso][2],:]
                                ndyv = ndyv[dycut_obs[sReso][0]:dycut_obs[sReso][1]:dycut_obs[sReso][2],:]
                        elif sModel_Region_upper in ["GRAPES_25KM"]:
                            if cls_model.latlon_info.lat_start==0.125 and cls_model.latlon_info.lat_end==60.125:
                                ndyu = ndyu[dycut_obs[sReso][0]:dycut_obs[sReso][1]:dycut_obs[sReso][2],:]
                                ndyv = ndyv[dycut_obs[sReso][0]:dycut_obs[sReso][1]:dycut_obs[sReso][2],:]
                        elif sModel_Region_upper in ["GRAPES_12P5KM","GRAPES_GFS","CMA_GFS"]:
                            if cls_model.latlon_info.lat_start==0.0625 and cls_model.latlon_info.lat_end==60.0625:
                                ndyu = ndyu[dycut_obs[sReso][0]:dycut_obs[sReso][1]:dycut_obs[sReso][2],:]
                                ndyv = ndyv[dycut_obs[sReso][0]:dycut_obs[sReso][1]:dycut_obs[sReso][2],:]
                        if ndyu.size!=dyIntp_info['size']: #说明读取到实况文件,但是数据错误
                            if args.debug>=1:print("Err:",ndyu.size,ndyv.size)
                            continue
                        dyGObs_PhyQ["10u"] =np.round(ndyu,1)
                        dyGObs_PhyQ["10v"] =np.round(ndyv,1)
                        dyGObs_PhyQ["10ws"]=np.round(np.sqrt(np.square(ndyu)+np.square(ndyv)),1)
                #实况存在
                if dyGObs_PhyQ!={}:
                    dyClass = {"cls_obsdb": cls_obsdb, "cls_model": cls_model}
                    dyCommon_Para = {"update":args.update, "sReso":sReso, "sInterp_YMDH":sInterp_YMDH, "dyBP_Path":dyBP_Path,
                                    "sModel_Region_upper":sModel_Region_upper,"ltPara_Loss_cycle":ltPara_Loss_cycle, "timeout":900,
                                    "Class":dyClass}
                    #并行-起报时间
                    if dyPool["BT_parallel"]:
                        print("BP_T_parallel")
                        cls_itp3d.dPool_best_eta_NBT_nPQ(ltYMDH_FH_mdl, dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para)
                    #串行-起报
                    else:
                        print("BP_T_Serial") #最优参数-起报时间串行
                        cls_itp3d.dSerial_best_eta_NBT_nPQ(ltYMDH_FH_mdl, dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para)
            #站点
            else:
                dyGObs_PhyQ={}
                #要素循环
                for sPhyQ_shortname in cls_itp3d.ltPQSN_eta:
                    sPQ_name = cls_itp3d.dyInstPQSN_to_obsdir[sPhyQ_shortname][0]
                    sPQ_type = cls_itp3d.dyInstPQSN_to_obsdir[sPhyQ_shortname][1]
                    sIn_obs_sub_path = os.path.join(dyobs_info["Obs_Path"], sInterp_YMDH[0:4], sPQ_name, sPQ_type, sInterp_YMDH[0:8])
                    sobs_file_name   = sInterp_YMDH+"00"+".h5"
                    sIn_obs_abs_path = os.path.join(sIn_obs_sub_path, sobs_file_name)
                    if args.debug>=1:print("SO:"+sIn_obs_abs_path)
                    if sPhyQ_shortname in ["2t",'2rh']:
                        dfobs_site=cls_obsdb.dRsite_obs(sIn_obs_abs_path, ltSlt_Site_Code, ltindex=[sPhyQ_shortname])#(1行 多列站点) 缺损-32766.0
                        dfobs_site[(dfobs_site[sPhyQ_shortname]<=cls_itp3d.dyPQ_QC[sPhyQ_shortname][0]) | (dfobs_site[sPhyQ_shortname]>=cls_itp3d.dyPQ_QC[sPhyQ_shortname][1])] = np.nan
                        dfobs_site = dfobs_site.round(decimals=cls_itp3d.dyPQ_round[sPhyQ_shortname])
                        dyGObs_PhyQ[sPhyQ_shortname]=dfobs_site[sPhyQ_shortname].values
                    else: #矢量
                        dfobs_site=cls_obsdb.dRsite_obs_wind(sIn_obs_abs_path, ltSlt_Site_Code, ltindex=["WD", sPhyQ_shortname])
                        dfobs_site[(dfobs_site[sPhyQ_shortname]<=cls_itp3d.dyPQ_QC[sPhyQ_shortname][0]) | (dfobs_site[sPhyQ_shortname]>=cls_itp3d.dyPQ_QC[sPhyQ_shortname][1])] = np.nan
                        dfobs_site.loc[dfobs_site["WD"]==cls_itp3d.fcalm_wd,"WD"] = 0 #静风处理
                        ndyU,ndyV = cls_myfun.dWind_to_UV(dfobs_site["WD"].values, dfobs_site[sPhyQ_shortname].values) #风向风速转为uv风
                        dyGObs_PhyQ["10u"]  = np.around(ndyU, decimals=cls_itp3d.dyPQ_round["10u"])
                        dyGObs_PhyQ["10v"]  = np.around(ndyV, decimals=cls_itp3d.dyPQ_round["10v"])
                        dyGObs_PhyQ[sPhyQ_shortname] = np.around(dfobs_site[sPhyQ_shortname].values, decimals=cls_itp3d.dyPQ_round["10u"])
                #实况存在
                if dyGObs_PhyQ!={}:
                    dyCommon_Para = {"update":args.update, "sReso":sReso, "sInterp_YMDH":sInterp_YMDH, "dyBP_Path":dyBP_Path,
                                    "sModel_Region_upper":sModel_Region_upper,"ltPara_Loss_cycle":ltPara_Loss_cycle}
                    if sReso=="Site":
                        dyCommon_Para["Site_Code"]=ltSlt_Site_Code
                    dyPara_ini_info["Pool"]["Para_parallel"] = False #站点不需要参数并行
                    #并行-起报时间
                    if dyPool["BT_parallel"]:
                        print("BP_T_parallel")
                        cls_itp3d.dPool_best_eta_NBT_nPQ(ltYMDH_FH_mdl, dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para)
                    #串行-起报
                    else:
                        print("BP_T_Serial") #最优参数-起报时间串行
                        cls_itp3d.dSerial_best_eta_NBT_nPQ(ltYMDH_FH_mdl, dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para)
            #1个起报时间
            if args.debug>=1:cls_myfun.dPrint_run_time()
    #程序运行结束时间
    if args.debug>=1:cls_myfun.dPrint_run_time()



# 原有直接运行入口（兼容老用法）
if __name__ == '__main__':
    run_fast_refine()
