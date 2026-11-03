import meteva
import pandas as pd
import numpy as np
import meteva_base as meb
import meteva.product as mpd

import meteva.method as mem
import meteva.product as mpd

import datetime

ob_dir = r"/mnt/Observation/r24/sfc/YYMMDDHH.000"
ec_dir = r"/mnt/nimm_data/model_RT/globalECMWF_C1D/APCP24/YYYY/YYYYMMDD/NC/YYYYMMDDHH.TTT.nc"
mait_dir = r"/mnt/sm_qpf/v2021/rain24/mait/sfc/YYYYMMDD/YYYYMMDDHH.TTT.m3"

sta_info = r"../resource/sta_20260601.info"


time = datetime.datetime(2025, 8, 26, 0, 0, 0)
dtime = 36

ob_path = meb.get_path(ob_dir, time + datetime.timedelta(hours=8 + dtime))
ec_path = meb.get_path(ec_dir, time, dtime)
mait_path = meb.get_path(mait_dir, time, dtime)


station = meteva.base.io.read_stadata_from_micaps3(sta_info)

print("=----------------->>>> : ", ob_path)
ob_sta = meteva.base.io.read_stadata_from_micaps3(ob_path)
ob_dat = meb.put_stadata_on_station(ob_sta, station)
print(ob_dat)

print("=----------------->>>> : ", ec_path)
ec_grd = meteva.base.io.read_griddata_from_nc(ec_path)
ec_dat = meteva.base.interp_gs_nearest(ec_grd, station)
print(ec_dat)

print("=----------------->>>> : ", mait_path)
mait_grd = meteva.base.io.read_stadata_from_micaps3(mait_path)
mait_dat = meb.put_stadata_on_station(mait_grd, station)
print(mait_dat)
