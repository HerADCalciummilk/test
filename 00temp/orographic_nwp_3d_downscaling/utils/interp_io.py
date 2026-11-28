# -*- coding: utf-8 -*-
"""读入和写出。数值插值不在这里。"""
def read_environment(case):
    """读运行目录、参数文件、模式和实况配置。"""
    if "begin_date" in case:
        begin_date = case["begin_date"]
    if "debug" in case:
        debug = case["debug"]
    if "model_region" in case:
        model_region = case["model_region"]
    if "operation" in case:
        operation = case["operation"]
    if "para_file" in case:
        para_file = case["para_file"]
    if "resolution" in case:
        resolution = case["resolution"]
    if "root_path" in case:
        root_path = case["root_path"]
    if "s3_method" in case:
        s3_method = case["s3_method"]
    if "site_name" in case:
        site_name = case["site_name"]
    if "update" in case:
        update = case["update"]
    if "work_dir" in case:
        work_dir = case["work_dir"]
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
    # 本文件在包的 utils 下，core 在 src/core。
    MODULE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    core_path = os.path.join(MODULE_DIR, "core")
    if MODULE_DIR not in sys.path:
        sys.path.insert(0, MODULE_DIR)
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    # =====================================================================================================

    import core.module_my_function      as MMyfun
    import core.module_arguments       as MArg
    import core.module_global_variable as MGV
    import core.module_station         as MSite
    import core.module_obs_data_base    as MObsDB
    import core.module_model_info      as MModel
    import core.module_3_preprocess     as M3PrePro
    import core.module_interp_dem5     as MInterp3d
    import core.module_diagnosis       as MDiag
    #import core.Module_Micaps_RW       as MMICPS
    import core.mdl_obs_path           as Mmop
    from core.forecast_config import forecast_hour_range
    from core.grid_netcdf import export_grid_file
    from core.resource_paths import resolve_resources


    # =============================================================================
    # 新增：纯函数入口（无任何parser，完全通过参数调用）
    # =============================================================================
    def _infer_root_path(work_dir):
        """从工作目录向上找含 Parameter、config 或 resource/config 的项目根。"""
        cur = os.path.abspath(work_dir)
        for _ in range(10):
            if any(os.path.isdir(os.path.join(cur, name)) for name in ("Parameter", "config", "resource/config")):
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
        pylib_path = os.path.join(root_path, "legacy_pylib")
        if not os.path.isdir(pylib_path):
            pylib_path = os.path.join(root_path, "lib", "pylib")
        if os.path.isdir(pylib_path) and pylib_path not in sys.path:
            sys.path.append(pylib_path)


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
    resource_root, parameter_dir, terrain_root = resolve_resources(sRoot_Path)
    sRoot_Path = str(resource_root)
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
    cls_gv.Sys_Para_dir = parameter_dir
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
    cls_obsdb.dRObs_Info_ini(sRoot_Path, smid_folder=parameter_dir)

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
        dyInstantInfo={};dyMaxMinInfo={};dySiteInfo={};dyPool={};dythreshold={}
        config = configparser.ConfigParser()
        config.read(spara_abs_path)
        netcdf_output_root = None
        if args.resolution.lower() != "site" and config.getboolean("NetCDFOutput", "enabled", fallback=False):
            netcdf_output_root = dyglobalInfo["Path"]["result"]
            dyglobalInfo["Path"]["result"] = os.path.join(netcdf_output_root, ".interp_cache")
        #瞬时
        dyInstantInfo["dem_head"]    = config.get('InstantInfo', "dem_head")                                     
        dyInstantInfo["dem_format"]  = config.get('InstantInfo', "dem_format")                                   
        dyInstantInfo["recall"]      = config.getboolean('InstantInfo', "recall")                                
        dyInstantInfo["Interp_Time"] = config.getboolean('InstantInfo', "Interp_Time")                           
        dyInstantInfo["validate"]    = config.getboolean('InstantInfo', "validate")                              
        swork                        = config.get('InstantInfo', "validate_area")
        if swork.upper()!="NONE":
            dyInstantInfo["Prov_code"] = [int(x) for x in swork.split(",")]
        else:
            dyInstantInfo["Prov_code"] = None
        dyInstantInfo["del_no_eta"]  = config.getboolean('InstantInfo', "del_no_eta")                            
        dyInstantInfo["out_China"]   = config.getboolean('InstantInfo', "out_China")                             
        dyInstantInfo["eta_cmn_out"] = config.getboolean('InstantInfo', "eta_cmn_out")                           
        dyInstantInfo["VR_plot"]     = config.getboolean('InstantInfo', "VR_plot")                               
        dyInstantInfo["rlt_plot"]    = config.getboolean('InstantInfo', "rlt_plot")                              
        dyInstantInfo["plot_format"] = config.get('InstantInfo', "plot_format").split(",")                       
        dyInstantInfo["MICAPS_out"]  = config.getboolean('InstantInfo', "MICAPS_out")                            
        dyInstantInfo["plot_format"] = config.get('InstantInfo', "plot_format").split(",")
        dyInstantInfo["PQ_shortname"]= [x.strip() for x in config.get('InstantInfo', "PQ_shortname").split(",")] 
        #=====================================
        #最高最低值
        dyMaxMinInfo["Interp_Maxmin"] = config.getboolean('MaxMinInfo', "Interp_Maxmin")                         
        if config.has_option('MaxMinInfo', "update"):
            dyMaxMinInfo["update"]      = config.getboolean('MaxMinInfo', "update")                                
        else:
            if args.update>=1:
                dyMaxMinInfo["update"]    = True
            else:
                dyMaxMinInfo["update"]    = False
        dyMaxMinInfo["validate"]      = config.getboolean('MaxMinInfo', "validate")                             
        dyMaxMinInfo["forecast_time"] = [x.strip() for x in config.get('MaxMinInfo', "forecast_time").replace('\n','').split(",")]   
        #=====================================
        #站点文件信息
        dySiteInfo["custom_path"]     = config.get('SiteInfo', "custom_path")
        #=====================================
        #并行信息
        dyPool["FH_parallel"]         = config.getboolean('PoolInfo', "FH_parallel")                            
        dyPool["FH_max_pcount"]       = config.getint('PoolInfo', "FH_max_pcount")                              
        dyPool["FH_DI_timeout"]       = config.getint('PoolInfo', "FH_DI_timeout")                              
        dyPool["FH_TI_timeout"]       = config.getint('PoolInfo', "FH_TI_timeout")                              
        #--------------------------
        dyPool["BT_parallel"]         = config.getboolean('PoolInfo', "BT_parallel")                            
        dyPool["BT_max_pcount"]       = config.getint('PoolInfo', "BT_max_pcount")                              
        dyPool["BT_timeout"]          = config.getint('PoolInfo', "BT_timeout")                                 
        #--------------------------
        dyPool["Para_parallel"]       = config.getboolean('PoolInfo', "Para_parallel")                          
        dyPool["Para_max_pcount"]     = config.getint('PoolInfo', "Para_max_pcount")                            
        dyPool["Para_timeout"]        = config.getint('PoolInfo', "Para_timeout")                               
        #检验命中率标准误差阈值
        ltwork=["2t","2rh","10ws","10u","10v","2t_max","2t_min","2rh_max","2rh_min","10ws_max"]
        for sPQ in ltwork:
            dythreshold[sPQ]            = config.getfloat('threshold', sPQ)

        if netcdf_output_root is not None and (dyInstantInfo["Interp_Time"] or dyMaxMinInfo["Interp_Maxmin"]):
            raise ValueError("NetCDFOutput currently requires Interp_Time=False and Interp_Maxmin=False")
        #打印并行参数信息
        print([skey+":"+str(dyPool[skey]) for skey in dyPool])
        dyPara_ini_info = {"InstantInfo":dyInstantInfo, "MaxMinInfo":dyMaxMinInfo, "Pool":dyPool, "threshold":dythreshold}
    else:
        print("No:"+spara_abs_path)
        sys.exit()

    _here = locals()
    for _key in ("M3PrePro", "MArg", "MDiag", "MGV", "MInterp3d", "MModel", "MMyfun", "MODULE_DIR", "MObsDB", "MSite", "Mmop", "SimpleArgs", "Spath", "_", "_append_optional_pylib", "_infer_root_path", "_split_model_region", "args", "cls_S3", "cls_gv", "cls_itp3d", "cls_model", "cls_myfun", "cls_obsdb", "cls_site", "config", "configparser", "core_path", "cpu_count", "cur", "datetime", "dyInstantInfo", "dyMaxMinInfo", "dyPara_ini_info", "dyPool", "dySiteInfo", "dyglobalInfo", "dythreshold", "export_grid_file", "forecast_hour_range", "h5py", "in_cpu_core", "ltwork", "name", "netcdf_output_root", "np", "os", "parameter_dir", "parent", "parts", "pd", "pylib_path", "resolve_resources", "resource_root", "sIn_mdl_Para_abs_path", "sInterp_YMDH", "sModel_Region", "sModel_Region_upper", "sModel_name", "sModel_name_lower", "sPQ", "sRegion", "sRegion_lower", "sRoot_Path", "sS3_method", "scurrent_path", "sfile_name", "skey", "spara_abs_path", "swork", "sys", "terrain_root", "time", "x"):
        if _key in _here:
            case[_key] = _here[_key]
    return case

def select_forecast_hours(case):
    """按业务时间确定起报时刻、预报时效和要素。"""
    if "args" in case:
        args = case["args"]
    if "cls_gv" in case:
        cls_gv = case["cls_gv"]
    if "cls_itp3d" in case:
        cls_itp3d = case["cls_itp3d"]
    if "cls_model" in case:
        cls_model = case["cls_model"]
    if "cls_myfun" in case:
        cls_myfun = case["cls_myfun"]
    if "config" in case:
        config = case["config"]
    if "dyInstantInfo" in case:
        dyInstantInfo = case["dyInstantInfo"]
    if "dyMaxMinInfo" in case:
        dyMaxMinInfo = case["dyMaxMinInfo"]
    if "dyglobalInfo" in case:
        dyglobalInfo = case["dyglobalInfo"]
    if "forecast_hour_range" in case:
        forecast_hour_range = case["forecast_hour_range"]
    if "np" in case:
        np = case["np"]
    if "sInterp_YMDH" in case:
        sInterp_YMDH = case["sInterp_YMDH"]
    if "sModel_Region_upper" in case:
        sModel_Region_upper = case["sModel_Region_upper"]
    if "sModel_name_lower" in case:
        sModel_name_lower = case["sModel_name_lower"]
    if "sRegion_lower" in case:
        sRegion_lower = case["sRegion_lower"]
    if "x" in case:
        x = case["x"]
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
        #4次起报
        else:
            lthour_mdl_begin = ["02","08","14","20"]
    #EC
    elif sModel_Region_upper=="EC_12P5KM":
        lthour_mdl_begin = ["08","20"]
    elif sModel_Region_upper in ["GRAPES_3KM","GRAPES_MESO","CMA_MESO"]:
        lthour_mdl_begin = [f"{ih:02d}" for ih in range(2,24,3)]
    else:
        lthour_mdl_begin = cls_model.report_times
    ibegin_fhour, iend_fhour = forecast_hour_range(
        config, sModel_Region_upper, cls_model.ltforecast_hours
    )
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

    _here = locals()
    for _key in ("dynowtime_vs_bhours", "iNum_BFH", "ibegin_fhour", "iend_fhour", "ih", "lthour_mdl_begin", "ltmdl_begin_hour", "mask", "ndyforecast_hours", "ndyfrst_hours", "sReso", "sReso_dir", "sYMD_mdl_begin", "shour_mdl_begin", "x"):
        if _key in _here:
            case[_key] = _here[_key]
    return case

def read_element_paths(case):
    """读要素短名和模式、实况路径配置。"""
    if "Spath" in case:
        Spath = case["Spath"]
    if "cls_itp3d" in case:
        cls_itp3d = case["cls_itp3d"]
    if "parameter_dir" in case:
        parameter_dir = case["parameter_dir"]
    if "sModel_Region_upper" in case:
        sModel_Region_upper = case["sModel_Region_upper"]
    if "sRoot_Path" in case:
        sRoot_Path = case["sRoot_Path"]
    # 获得所需的要素信息
    Spath.get_ltsPQ_ltMPQ_shortname(cls_itp3d.ltPQSN_Intp, cls_itp3d.ltPQSN_mxmn, sModel_Region_upper)
    # 读取路径配置文件 Mdl_Obs_Path_Info.ini
    Spath.dRead_Mdl_Obs_path_ini(sRoot_Path, subpath=parameter_dir)

    return case

def check_output_files(case):
    """检查已有 h5。全部已存在且不更新时按原逻辑退出。"""
    if "args" in case:
        args = case["args"]
    if "cls_gv" in case:
        cls_gv = case["cls_gv"]
    if "cls_itp3d" in case:
        cls_itp3d = case["cls_itp3d"]
    if "cls_myfun" in case:
        cls_myfun = case["cls_myfun"]
    if "dyInstantInfo" in case:
        dyInstantInfo = case["dyInstantInfo"]
    if "dyglobalInfo" in case:
        dyglobalInfo = case["dyglobalInfo"]
    if "h5py" in case:
        h5py = case["h5py"]
    if "ibegin_fhour" in case:
        ibegin_fhour = case["ibegin_fhour"]
    if "iend_fhour" in case:
        iend_fhour = case["iend_fhour"]
    if "lthour_mdl_begin" in case:
        lthour_mdl_begin = case["lthour_mdl_begin"]
    if "ndyforecast_hours" in case:
        ndyforecast_hours = case["ndyforecast_hours"]
    if "os" in case:
        os = case["os"]
    if "sInterp_YMDH" in case:
        sInterp_YMDH = case["sInterp_YMDH"]
    if "sModel_Region" in case:
        sModel_Region = case["sModel_Region"]
    if "sReso_dir" in case:
        sReso_dir = case["sReso_dir"]
    if "sS3_method" in case:
        sS3_method = case["sS3_method"]
    if "sYMD_mdl_begin" in case:
        sYMD_mdl_begin = case["sYMD_mdl_begin"]
    if "shour_mdl_begin" in case:
        shour_mdl_begin = case["shour_mdl_begin"]
    if "sys" in case:
        sys = case["sys"]
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

    _here = locals()
    for _key in ("dymdl_ftime_info", "fh", "iForecast_hour", "iThour", "idy", "ihb", "inum_eta_attrs", "lDI_update", "lDintep_exist_out", "lTI_update", "lTintep_exist_out", "leta_alive_out", "leta_exist_out", "leta_update", "lintep_alive_out", "lintep_exist_out", "ltTInterp_hour", "ltYMDH_mdl_begin", "lteta_exist_out", "ltprint_info", "obj_attrs", "sForecast_hour", "sIfh_b", "sOut_Abs_path", "sOut_Sub_path", "sOut_abs_path", "sOut_file_name", "sOut_sub_path", "sPhyQ_shortname", "sYMDH_mdl_begin_BJ", "sYMDH_mdl_begin_UTC"):
        if _key in _here:
            case[_key] = _here[_key]
    return case

def read_model_terrain(case):
    """读模式地形、分区和经纬度。"""
    if "args" in case:
        args = case["args"]
    if "cls_itp3d" in case:
        cls_itp3d = case["cls_itp3d"]
    if "cls_model" in case:
        cls_model = case["cls_model"]
    if "dyInstantInfo" in case:
        dyInstantInfo = case["dyInstantInfo"]
    if "np" in case:
        np = case["np"]
    if "os" in case:
        os = case["os"]
    if "sModel_Region" in case:
        sModel_Region = case["sModel_Region"]
    if "sModel_Region_upper" in case:
        sModel_Region_upper = case["sModel_Region_upper"]
    if "sys" in case:
        sys = case["sys"]
    if "terrain_root" in case:
        terrain_root = case["terrain_root"]
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
        sm4_abs_path  = os.path.join(terrain_root,sModel_Region_upper,"Terrain_"+sReso_mdl+"."+dyInstantInfo["dem_format"])
        if not os.path.exists(sm4_abs_path):
            print("No:"+sm4_abs_path)
            sys.exit()
        else:
            ndyterrain_mdl, lthead = cls_itp3d.dRead_d4_scalar(sm4_abs_path) #上-下(北-南) 左-右(西-东)
            ndyterrain_mdl[ndyterrain_mdl<=-1000.]=0
            ndyterrain_mdl[ndyterrain_mdl>=9000.]=9000
            ndyterrain_mdl=np.flipud(ndyterrain_mdl) #变为上-下(南-北) 左-右(西-东)=(1671,2501)=4179171=3km范围
        #分区
        sm4_abs_path = os.path.join(terrain_root,sModel_Region_upper,"Zoning_"+sReso_mdl+"."+dyInstantInfo["dem_format"])
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
        stif_abs_path = os.path.join(terrain_root,sModel_Region_upper,"Terrain_"+sReso_mdl+"."+dyInstantInfo["dem_format"])  #坐标60-0 70-140= 1201,1401 缺损-2147483647
        if not os.path.exists(stif_abs_path):
            print("No:"+stif_abs_path)
            sys.exit()
        else:
            ndyterrain_mdl = cls_itp3d.dRead_Terrain(stif_abs_path) #返回一个numpy n-d数组 上-下(北-南) 左-右(西-东)
        #分区
        stif_abs_path = os.path.join(terrain_root,sModel_Region_upper,"Zoning_"+sReso_mdl+"."+dyInstantInfo["dem_format"])
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
                            # 与当前 EC 高空实况一致：近地面 0.1°、高空 0.2°（原业务多为 0.125°/0.25°）
                            "lon_res"  :0.2, "lat_res"  :0.2} # 60–140 / 0–60 → 301×401
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

    _here = locals()
    for _key in ("dylonlat_ML_IG_mdl", "dylonlat_SL_IG_mdl", "dymdl_Geog", "iround", "lthead", "mask2d_common_12P5km_to_25km", "mask2d_x_lon_12P5km_to_25km", "mask2d_y_lat_12P5km_to_25km", "mask_area_mdl", "ndyterrain_mdl", "ndyzoning_mdl", "sReso_mdl", "sm4_abs_path", "stif_abs_path"):
        if _key in _here:
            case[_key] = _here[_key]
    return case

def read_interp_targets(case):
    """读站点或细网格目标点。"""
    if "args" in case:
        args = case["args"]
    if "cls_itp3d" in case:
        cls_itp3d = case["cls_itp3d"]
    if "cls_model" in case:
        cls_model = case["cls_model"]
    if "cls_myfun" in case:
        cls_myfun = case["cls_myfun"]
    if "cls_obsdb" in case:
        cls_obsdb = case["cls_obsdb"]
    if "cls_site" in case:
        cls_site = case["cls_site"]
    if "dyInstantInfo" in case:
        dyInstantInfo = case["dyInstantInfo"]
    if "dySiteInfo" in case:
        dySiteInfo = case["dySiteInfo"]
    if "np" in case:
        np = case["np"]
    if "os" in case:
        os = case["os"]
    if "parameter_dir" in case:
        parameter_dir = case["parameter_dir"]
    if "pd" in case:
        pd = case["pd"]
    if "sModel_Region_upper" in case:
        sModel_Region_upper = case["sModel_Region_upper"]
    if "sReso" in case:
        sReso = case["sReso"]
    if "sReso_dir" in case:
        sReso_dir = case["sReso_dir"]
    if "sRoot_Path" in case:
        sRoot_Path = case["sRoot_Path"]
    if "stif_abs_path" in case:
        stif_abs_path = case["stif_abs_path"]
    if "terrain_root" in case:
        terrain_root = case["terrain_root"]
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
            sIn_Abs_path = os.path.join(sRoot_Path, parameter_dir, args.site_name)
            if not os.path.exists(sIn_Abs_path):
                sIn_Abs_path = os.path.join(sRoot_Path, parameter_dir, args.site_name)
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
        stif_abs_path = os.path.join(terrain_root, dyInstantInfo["dem_head"]+"_"+sReso,"Zoning_"+sReso+".tif")  #坐标60-0 70-140 = 1201, 1401
        ndyzoning_rlt, mask_area_rlt = cls_itp3d.dRead_Zoning(stif_abs_path)#返回一个numpy 2-d数组 上-下(南-北) 左-右(西-东) 
        #检验指定省份
        if dyInstantInfo["Prov_code"] is not None:
            mask_selt_prov = cls_itp3d.dSelect_Provinces(ndyzoning_rlt, dyInstantInfo["Prov_code"]) #指定哪些省份= 5km=(1201, 1401)
        #读取中国sReso地形文件-插值结果分辨率
        stif_abs_path  = os.path.join(terrain_root,dyInstantInfo["dem_head"]+"_"+sReso,"Terrain_"+sReso+".tif")  #坐标60-0 70-140= 1201,1401 缺损-2147483647
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
        if dyInstantInfo["Prov_code"] is None:
            mask_selt_prov = mask_area_rlt
        dyIntp_info["mask_prov"] = mask_selt_prov #所选省
        if dyIntp_info["lat"].size != dyIntp_info["alt"].size:
            print("Err Intp lat alt",dyIntp_info["lat"].size, " /=",dyIntp_info["alt"].size)
    if args.debug>=1:cls_myfun.dPrint_run_time()
    #===============================================================================================================

    _here = locals()
    for _key in ("dfsite", "dtsite", "dyIntp_info", "dycut_obs", "dylonlat_rlt", "dyobs_info", "flat_start", "icut_3km_y_lat_num", "icut_y_lat_num", "ltSlt_Site_Alt", "ltSlt_Site_Code", "ltSlt_Site_Lat", "ltSlt_Site_Lon", "ltall_sites", "ltcols_name", "mask_area_rlt", "mask_selt_prov", "ndy2d_x_lon", "ndy2d_y_lat", "ndyterrain_obs", "ndyzoning_rlt", "sIn_Abs_path", "scode", "ssite_code_name", "stif_abs_path"):
        if _key in _here:
            case[_key] = _here[_key]
    return case

def write_netcdf(case):
    """把 h5 缓存写成 NetCDF 产品。"""
    if "args" in case:
        args = case["args"]
    if "cls_gv" in case:
        cls_gv = case["cls_gv"]
    if "cls_itp3d" in case:
        cls_itp3d = case["cls_itp3d"]
    if "configparser" in case:
        configparser = case["configparser"]
    if "dyglobalInfo" in case:
        dyglobalInfo = case["dyglobalInfo"]
    if "export_grid_file" in case:
        export_grid_file = case["export_grid_file"]
    if "ndyforecast_hours" in case:
        ndyforecast_hours = case["ndyforecast_hours"]
    if "netcdf_output_root" in case:
        netcdf_output_root = case["netcdf_output_root"]
    if "os" in case:
        os = case["os"]
    if "parameter_dir" in case:
        parameter_dir = case["parameter_dir"]
    if "sModel_Region" in case:
        sModel_Region = case["sModel_Region"]
    if "sReso_dir" in case:
        sReso_dir = case["sReso_dir"]
    if "sRoot_Path" in case:
        sRoot_Path = case["sRoot_Path"]
    if "sS3_method" in case:
        sS3_method = case["sS3_method"]
    if "sYMDH_mdl_begin_BJ" in case:
        sYMDH_mdl_begin_BJ = case["sYMDH_mdl_begin_BJ"]
    if "sYMD_mdl_begin" in case:
        sYMD_mdl_begin = case["sYMD_mdl_begin"]
    if "shour_mdl_begin" in case:
        shour_mdl_begin = case["shour_mdl_begin"]
    if netcdf_output_root is not None:
        output_mapping = configparser.ConfigParser()
        output_mapping.read(os.path.join(sRoot_Path, parameter_dir, "Mdl_Obs_Path_Info.ini"), encoding="utf-8")
        for output_hour in ndyforecast_hours:
            cache_path = os.path.join(
                dyglobalInfo["Path"]["result"], cls_gv.S3_dir, sS3_method,
                sModel_Region, sReso_dir, sYMD_mdl_begin[:4], sYMD_mdl_begin,
                shour_mdl_begin, f"{output_hour:03d}_{output_hour:03d}.h5"
            )
            if os.path.isfile(cache_path):
                for product in export_grid_file(
                    cache_path, netcdf_output_root, sYMDH_mdl_begin_BJ, output_hour,
                    dict(output_mapping.items("ElementDirGround")),
                    output_mapping.get("ModelPathInfo", "file_timezone"),
                    update=args.update != 0, fill_value=cls_itp3d.RGrid_Default
                ):
                    print("nc_out:" + product)

    _here = locals()
    for _key in ("cache_path", "output_hour", "output_mapping", "product"):
        if _key in _here:
            case[_key] = _here[_key]
    return case

