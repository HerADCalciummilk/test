# -*- coding: utf-8 -*-
"""三段计算：空间插值、最高最低与时间插值、最优 eta。

只使用已经读好的 case。空间插值的中间 h5 仍由原插值过程写出。最优 eta 只返回结果。
"""
from utils.base_plugin import BasePlugin


class SpatialInterpPlugin(BasePlugin):
    """按预报时效做三维地形插值。

    参数 case：模式路径、地形、目标站点或格点、时效和订正参数。
    返回：写回 dyInterp_spc_nfh 的同一个 case。中间 h5 仍由原插值过程写出。
    """

    def process(self, case):
        """按预报时效做三维地形插值。h5 仍由原插值过程写出。"""
        if "Spath" in case:
            Spath = case["Spath"]
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
        if "cls_obsdb" in case:
            cls_obsdb = case["cls_obsdb"]
        if "dyInstantInfo" in case:
            dyInstantInfo = case["dyInstantInfo"]
        if "dyIntp_info" in case:
            dyIntp_info = case["dyIntp_info"]
        if "dyPara_ini_info" in case:
            dyPara_ini_info = case["dyPara_ini_info"]
        if "dyPool" in case:
            dyPool = case["dyPool"]
        if "dyglobalInfo" in case:
            dyglobalInfo = case["dyglobalInfo"]
        if "dymdl_Geog" in case:
            dymdl_Geog = case["dymdl_Geog"]
        if "dynowtime_vs_bhours" in case:
            dynowtime_vs_bhours = case["dynowtime_vs_bhours"]
        if "iForecast_hour" in case:
            iForecast_hour = case["iForecast_hour"]
        if "lDI_update" in case:
            lDI_update = case["lDI_update"]
        if "ltSlt_Site_Code" in case:
            ltSlt_Site_Code = case["ltSlt_Site_Code"]
        if "ltmdl_begin_hour" in case:
            ltmdl_begin_hour = case["ltmdl_begin_hour"]
        if "ndyforecast_hours" in case:
            ndyforecast_hours = case["ndyforecast_hours"]
        if "os" in case:
            os = case["os"]
        if "sForecast_hour" in case:
            sForecast_hour = case["sForecast_hour"]
        if "sInterp_YMDH" in case:
            sInterp_YMDH = case["sInterp_YMDH"]
        if "sModel_Region" in case:
            sModel_Region = case["sModel_Region"]
        if "sModel_Region_upper" in case:
            sModel_Region_upper = case["sModel_Region_upper"]
        if "sModel_name_lower" in case:
            sModel_name_lower = case["sModel_name_lower"]
        if "sOut_Abs_path" in case:
            sOut_Abs_path = case["sOut_Abs_path"]
        if "sOut_Sub_path" in case:
            sOut_Sub_path = case["sOut_Sub_path"]
        if "sOut_file_name" in case:
            sOut_file_name = case["sOut_file_name"]
        if "sPhyQ_shortname" in case:
            sPhyQ_shortname = case["sPhyQ_shortname"]
        if "sRegion_lower" in case:
            sRegion_lower = case["sRegion_lower"]
        if "sReso" in case:
            sReso = case["sReso"]
        if "sReso_dir" in case:
            sReso_dir = case["sReso_dir"]
        if "sS3_method" in case:
            sS3_method = case["sS3_method"]
        if "sYMDH_mdl_begin_BJ" in case:
            sYMDH_mdl_begin_BJ = case["sYMDH_mdl_begin_BJ"]
        if "sYMDH_mdl_begin_UTC" in case:
            sYMDH_mdl_begin_UTC = case["sYMDH_mdl_begin_UTC"]
        if "sYMD_mdl_begin" in case:
            sYMD_mdl_begin = case["sYMD_mdl_begin"]
        if "shour_mdl_begin" in case:
            shour_mdl_begin = case["shour_mdl_begin"]
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

        _here = locals()
        for _key in ("Nexist", "dyClass", "dyCommon_Para", "dyInterp_spc_nfh", "dyattr", "dyeta_file_name", "dymdl_rdata_nfh", "dynowtime_vs_bhours", "dypath_info", "dypath_mdl", "iForecast_hour", "iday_bj", "iday_utc", "ihour_bj", "ihour_utc", "imonth_bj", "imonth_utc", "iyear_bj", "iyear_utc", "lalive", "lexist_mdl", "ltfhours", "ltmdl_begin_hour", "ltout_info", "sForecast_hour", "sIn_1d_eta_abs_path", "sIn_cmn_eta_abs_path", "sIn_mdl_abs_path_dt", "sOut_Abs_path", "sOut_Sub_path", "sOut_file_name", "sPhyQ_shortname", "sYMDH_mdl_begin_BJ", "sYMDH_mdl_begin_UTC", "sYMD_mdl_begin", "shour_mdl_begin"):
            if _key in _here:
                case[_key] = _here[_key]
        return case


class MaxMinPlugin(BasePlugin):
    """由已插值的时效场求最高最低。

    参数 case：含 dyInterp_spc_nfh 和预报时段。
    返回：同一个 case。最高最低仍写入原 h5 结果。
    """

    def process(self, case):
        """由已插值的时效场求最高最低。"""
        if "Spath" in case:
            Spath = case["Spath"]
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
        if "cls_obsdb" in case:
            cls_obsdb = case["cls_obsdb"]
        if "dyClass" in case:
            dyClass = case["dyClass"]
        if "dyCommon_Para" in case:
            dyCommon_Para = case["dyCommon_Para"]
        if "dyInterp_spc_nfh" in case:
            dyInterp_spc_nfh = case["dyInterp_spc_nfh"]
        if "dyIntp_info" in case:
            dyIntp_info = case["dyIntp_info"]
        if "dyMaxMinInfo" in case:
            dyMaxMinInfo = case["dyMaxMinInfo"]
        if "dyPara_ini_info" in case:
            dyPara_ini_info = case["dyPara_ini_info"]
        if "dyglobalInfo" in case:
            dyglobalInfo = case["dyglobalInfo"]
        if "dymdl_Geog" in case:
            dymdl_Geog = case["dymdl_Geog"]
        if "dymdl_rdata_nfh" in case:
            dymdl_rdata_nfh = case["dymdl_rdata_nfh"]
        if "dypath_mdl" in case:
            dypath_mdl = case["dypath_mdl"]
        if "ih" in case:
            ih = case["ih"]
        if "ltSlt_Site_Code" in case:
            ltSlt_Site_Code = case["ltSlt_Site_Code"]
        if "sModel_Region" in case:
            sModel_Region = case["sModel_Region"]
        if "sReso" in case:
            sReso = case["sReso"]
        if "sReso_dir" in case:
            sReso_dir = case["sReso_dir"]
        if "sS3_method" in case:
            sS3_method = case["sS3_method"]
        if "sYMDH_mdl_begin_BJ" in case:
            sYMDH_mdl_begin_BJ = case["sYMDH_mdl_begin_BJ"]
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

        _here = locals()
        for _key in ("dyClass", "dyCommon_Para", "dyMaxMin_fhours", "ih", "ltbehour", "lthours", "sbehour"):
            if _key in _here:
                case[_key] = _here[_key]
        return case


class TimeInterpPlugin(BasePlugin):
    """在已有时效之间做时间插值。

    参数 case：含相邻时效的插值结果和要素名。
    返回：同一个 case。新时效仍写入原 h5 结果。
    """

    def process(self, case):
        """在已有时效之间做时间插值。"""
        if "args" in case:
            args = case["args"]
        if "cls_gv" in case:
            cls_gv = case["cls_gv"]
        if "cls_itp3d" in case:
            cls_itp3d = case["cls_itp3d"]
        if "cls_model" in case:
            cls_model = case["cls_model"]
        if "cls_obsdb" in case:
            cls_obsdb = case["cls_obsdb"]
        if "dyClass" in case:
            dyClass = case["dyClass"]
        if "dyCommon_Para" in case:
            dyCommon_Para = case["dyCommon_Para"]
        if "dyInterp_spc_nfh" in case:
            dyInterp_spc_nfh = case["dyInterp_spc_nfh"]
        if "dyPara_ini_info" in case:
            dyPara_ini_info = case["dyPara_ini_info"]
        if "dyglobalInfo" in case:
            dyglobalInfo = case["dyglobalInfo"]
        if "ihb" in case:
            ihb = case["ihb"]
        if "ndyforecast_hours" in case:
            ndyforecast_hours = case["ndyforecast_hours"]
        if "os" in case:
            os = case["os"]
        if "sModel_Region" in case:
            sModel_Region = case["sModel_Region"]
        if "sModel_Region_upper" in case:
            sModel_Region_upper = case["sModel_Region_upper"]
        if "sReso" in case:
            sReso = case["sReso"]
        if "sReso_dir" in case:
            sReso_dir = case["sReso_dir"]
        if "sS3_method" in case:
            sS3_method = case["sS3_method"]
        if "sYMDH_mdl_begin_BJ" in case:
            sYMDH_mdl_begin_BJ = case["sYMDH_mdl_begin_BJ"]
        if "sYMD_mdl_begin" in case:
            sYMD_mdl_begin = case["sYMD_mdl_begin"]
        if "shour_mdl_begin" in case:
            shour_mdl_begin = case["shour_mdl_begin"]
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

        _here = locals()
        for _key in ("dyClass", "dyCommon_Para", "ihb", "ihe", "ltInterp_fh_be", "sIn_sub_path"):
            if _key in _here:
                case[_key] = _here[_key]
        return case


class BestEtaPlugin(BasePlugin):
    """用实况在 0.1 到 1.0 上选取最优 eta。

    参数 case：含实况、模式路径、目标点和要素阈值。
    返回：同一个 case。格点或站点 eta 在 eta_products，由 process 写出 h5。
    """

    def process(self, case):
        """用实况在 0.1 到 1.0 上选取最优 eta。

        参数 case：含实况、模式路径、目标点和要素阈值。
        返回：同一个 case。eta_products 的每项含 hour、element、daily_dir、common_dir、data、keys、attrs。
        """
        if "Nexist" in case:
            Nexist = case["Nexist"]
        if "Spath" in case:
            Spath = case["Spath"]
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
        if "cls_obsdb" in case:
            cls_obsdb = case["cls_obsdb"]
        if "dyClass" in case:
            dyClass = case["dyClass"]
        if "dyCommon_Para" in case:
            dyCommon_Para = case["dyCommon_Para"]
        if "dyIntp_info" in case:
            dyIntp_info = case["dyIntp_info"]
        if "dyPara_ini_info" in case:
            dyPara_ini_info = case["dyPara_ini_info"]
        if "dyPool" in case:
            dyPool = case["dyPool"]
        if "dycut_obs" in case:
            dycut_obs = case["dycut_obs"]
        if "dyglobalInfo" in case:
            dyglobalInfo = case["dyglobalInfo"]
        if "dymdl_Geog" in case:
            dymdl_Geog = case["dymdl_Geog"]
        if "dymdl_ftime_info" in case:
            dymdl_ftime_info = case["dymdl_ftime_info"]
        if "dyobs_info" in case:
            dyobs_info = case["dyobs_info"]
        if "iForecast_hour" in case:
            iForecast_hour = case["iForecast_hour"]
        if "lexist_mdl" in case:
            lexist_mdl = case["lexist_mdl"]
        if "ltSlt_Site_Code" in case:
            ltSlt_Site_Code = case["ltSlt_Site_Code"]
        if "ltYMDH_mdl_begin" in case:
            ltYMDH_mdl_begin = case["ltYMDH_mdl_begin"]
        if "ndyforecast_hours" in case:
            ndyforecast_hours = case["ndyforecast_hours"]
        if "np" in case:
            np = case["np"]
        if "os" in case:
            os = case["os"]
        if "sForecast_hour" in case:
            sForecast_hour = case["sForecast_hour"]
        if "sIn_mdl_abs_path_dt" in case:
            sIn_mdl_abs_path_dt = case["sIn_mdl_abs_path_dt"]
        if "sInterp_YMDH" in case:
            sInterp_YMDH = case["sInterp_YMDH"]
        if "sModel_Region" in case:
            sModel_Region = case["sModel_Region"]
        if "sModel_Region_upper" in case:
            sModel_Region_upper = case["sModel_Region_upper"]
        if "sOut_Abs_path" in case:
            sOut_Abs_path = case["sOut_Abs_path"]
        if "sOut_Sub_path" in case:
            sOut_Sub_path = case["sOut_Sub_path"]
        if "sOut_file_name" in case:
            sOut_file_name = case["sOut_file_name"]
        if "sPhyQ_shortname" in case:
            sPhyQ_shortname = case["sPhyQ_shortname"]
        if "sReso" in case:
            sReso = case["sReso"]
        if "sReso_dir" in case:
            sReso_dir = case["sReso_dir"]
        if "sS3_method" in case:
            sS3_method = case["sS3_method"]
        if "sYMDH_mdl_begin_BJ" in case:
            sYMDH_mdl_begin_BJ = case["sYMDH_mdl_begin_BJ"]
        print("---------------best_eta-----------------------------")
        eta_products = []
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
                        eta_products.extend(cls_itp3d.dPool_best_eta_NBT_nPQ(ltYMDH_FH_mdl, dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para) or [])
                    #串行-起报
                    else:
                        print("BP_T_Serial") #最优参数-起报时间串行
                        eta_products.extend(cls_itp3d.dSerial_best_eta_NBT_nPQ(ltYMDH_FH_mdl, dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para) or [])
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
                        eta_products.extend(cls_itp3d.dPool_best_eta_NBT_nPQ(ltYMDH_FH_mdl, dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para) or [])
                    #串行-起报
                    else:
                        print("BP_T_Serial") #最优参数-起报时间串行
                        eta_products.extend(cls_itp3d.dSerial_best_eta_NBT_nPQ(ltYMDH_FH_mdl, dyGObs_PhyQ, dymdl_Geog, dyIntp_info, dyPara_ini_info, dyCommon_Para) or [])
            #1个起报时间
            if args.debug>=1:cls_myfun.dPrint_run_time()

        _here = locals()
        for _key in ("Nexist", "dfobs_site", "dyBP_Path", "dyClass", "dyCommon_Para", "dyGObs_PhyQ", "dyOut_Path", "eta_products", "iForecast_hour", "idy", "lalive_out", "lexist", "lexist_mdl", "lexist_obs", "lexist_out", "ltPara_Loss_cycle", "ltYMDH_FH_mdl", "ndyGObs_PhyQ", "ndyU", "ndyV", "ndyu", "ndyv", "sForecast_hour", "sIn_mdl_abs_path_dt", "sIn_obs_abs_path", "sIn_obs_abs_path_dt", "sIn_obs_sub_path", "sOut_Abs_path", "sOut_Abs_path1", "sOut_Sub_path", "sOut_Sub_path2", "sOut_file_name", "sPQ_name", "sPQ_type", "sPhyQ_shortname", "sYMDH_FH_mdl", "sYMDH_mdl_begin_BJ", "sYMDH_mdl_begin_UTC", "sobs_file_name"):
            if _key in _here:
                case[_key] = _here[_key]
        return case


