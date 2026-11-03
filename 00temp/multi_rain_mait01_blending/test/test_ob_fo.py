import os

import meteva
import pandas as pd
import numpy as np
import meteva_base as meb
import meteva.product as mpd

import meteva.method as mem
import meteva.product as mpd

import datetime

import meteva_base as meb
import numpy as np
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['SimHei']
plt.rcParams['axes.unicode_minus']=False
import pandas as pd

# ob_dir = r"/mnt/Observation/r24/sfc/YYMMDDHH.000"
# 10.28.16.234\data1\DataPool\01CLDAS\02CMPAS\Hourly\NRT_1km\APCP
ob_dir = r"/data234/DataPool/01CLDAS/02CMPAS/Hourly/NRT_1km/APCP/YYYY/YYYYMMDD/BJT_YYMMDDHH.000.nc"
cma3km_dir = r"/data/mnt/model_RT/mesoCMA_3KM/APCP/YYYY/YYYYMMDD/YYYYMMDDHH.TTT.nc"
mait_dir = r"/data100/st_qpf/rain01/mait_st/sfc/YYYY/YYYYMMDD/YYYYMMDDHH.TTT.nc"
png_dir = r"/data/code/mait_1h/resource/data/pngs/YYYYMMDD"
dtimes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]


def task(ftime):

    fo_time = datetime.datetime.strptime(ftime, "%Y%m%d%H")
    ob_time = fo_time + datetime.timedelta(hours=8)



    for dtime in dtimes:
        ob_path = meb.get_path(ob_dir, ob_time + datetime.timedelta(hours=dtime))
        cma3km_path = meb.get_path(cma3km_dir, fo_time, dtime)
        bef_cma3km_path = meb.get_path(cma3km_dir, fo_time, (dtime-1))
        mt_path = meb.get_path(mait_dir, fo_time, dtime)
        pg_path = meb.get_path(png_dir, fo_time)

        if os.path.exists(mt_path) and os.path.exists(cma3km_path) and os.path.exists(ob_path):
            ob_grd = meb.read_griddata_from_nc(ob_path)
            cma3km_grd = meb.read_griddata_from_nc(cma3km_path)
            bef_cma3km_grd = meb.read_griddata_from_nc(bef_cma3km_path)
            cma3km_grd.values = cma3km_grd.values - bef_cma3km_grd.values
            mt_grd = meb.read_griddata_from_nc(mt_path)

            print(f"--------------------->>> ob_grd : {ob_path}\n", ob_grd.shape)
            print(f"--------------------->>> cma3km_grd : {cma3km_path}\n", cma3km_grd.shape)
            print(f"--------------------->>> mt_grd : {mt_path}\n", mt_grd.shape)

            map_extend = [113, 119.99, 36, 42.99]
            axs = meb.creat_axs(3, map_extend, ncol=3, add_index=["OBS", "CMA_3KM", "MAIT"], sup_title=f"{ftime}_{dtime:03d}", sup_fontsize=26, wspace=1, height=26, width=26)


            clevs = np.array([0, 0.1, 10, 25, 50, 100])
            meb.add_contourf(axs[0], ob_grd, cmap="rainbow", clevs=clevs, add_colorbar=True)
            meb.add_contourf(axs[1], cma3km_grd, cmap="rainbow", clevs=clevs, add_colorbar=True)
            meb.add_contourf(axs[2], mt_grd, cmap="rainbow", clevs=clevs, add_colorbar=True)

            if not os.path.exists(pg_path):
                os.makedirs(pg_path)

            plt.savefig(f"{pg_path}/{ftime}_{dtime:03d}.png", bbox_inches='tight')


def main(dates):
    for date in dates:
        for dtime in [
            "00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11",
            "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23"
        ]:
            task(date+dtime)


if __name__ == '__main__':
    dates = [
        "20250701", "20250702", "20250722", "20250723",
        "20250801", "20250802", "20250803", "20250817",
        "20250818", "20250821", "20250822",
        "20250823", "20250825",
    ]
    main(dates)
    # task("2025070100")

