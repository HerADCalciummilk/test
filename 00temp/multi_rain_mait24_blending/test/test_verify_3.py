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
ob_dir = r"/mnt/data1/DataPool/01CLDAS/02CMPAS/Daily/RT_5km/YYYY/YYYYMMDD/BJT_YYMMDDHH.000.nc"
ec_dir = r"/mnt/nimm_data/model_RT/globalECMWF_C1D/APCP24/YYYY/YYYYMMDD/NC/YYYYMMDDHH.TTT.nc"
mait_dir = r"/mnt/sm_qpf/v2021/rain24/mait/sfc/YYYYMMDD/YYYYMMDDHH.TTT.m4"
png_dir = r"/data/python_code/mait_24h/resource/data/pngs/YYYYMMDD"
dtimes = [36, 60, 84, 108, 132, 156, 180, 204, 228, 252]


def task(ftime):

    fo_time = datetime.datetime.strptime(ftime, "%Y%m%d%H")
    ob_time = fo_time + datetime.timedelta(hours=8)



    for dtime in dtimes:
        ob_path = meb.get_path(ob_dir, ob_time + datetime.timedelta(hours=dtime))
        ec_path = meb.get_path(ec_dir, fo_time, dtime)
        mt_path = meb.get_path(mait_dir, fo_time, dtime)
        pg_path = meb.get_path(png_dir, fo_time)
        # print("=----------------------------->>> ob_path : ", ob_path)
        # print("=----------------------------->>> ec_path : ", ec_path)
        # print("=----------------------------->>> mt_path : ", mait_path)
        if os.path.exists(mt_path) and os.path.exists(ec_path) and os.path.exists(ob_path):

            ob_grd = meb.read_griddata_from_nc(ob_path)
            ec_grd = meb.read_griddata_from_nc(ec_path)
            mt_grd = meb.read_griddata_from_micaps4(mt_path)

            print(f"--------------------->>> ob_grd : {ob_path}\n", ob_grd)
            print(f"--------------------->>> ec_grd : {ec_path}\n", ec_grd)
            print(f"--------------------->>> mt_grd : {mt_path}\n", mt_grd)

            map_extend = [113, 119.99, 36, 42.99]
            axs = meb.creat_axs(3, map_extend, ncol=3, add_index=["观测", "EC", "MAIT"], sup_title=f"{ftime}_{dtime:03d}时效降水", sup_fontsize=26, wspace=1, height=26, width=26)
            # axs = meb.creat_axs(3, map_extend, ncol=3, sup_title=f"{ftime}_{dtime:03d}时效降水", wspace=1, height=32, width=32)

            clevs = np.array([0, 0.1, 10, 25, 50, 100])
            meb.add_contourf(axs[0], ob_grd, cmap="rainbow", clevs=clevs, add_colorbar=True)
            meb.add_contourf(axs[1], ec_grd, cmap="rainbow", clevs=clevs, add_colorbar=True)
            meb.add_contourf(axs[2], mt_grd, cmap="rainbow", clevs=clevs, add_colorbar=True)

            # # 子图标题：总标题下方、子图外侧上方
            # titles = ["观测", "EC", "MAIT"]
            # for idx, ax in enumerate(axs):
            #     ax.set_title(titles[idx], y=1.04, pad=6, loc="center")

            if not os.path.exists(pg_path):
                os.makedirs(pg_path)

            plt.savefig(f"{pg_path}/{ftime}_{dtime:03d}.png", bbox_inches='tight')


def main(dates):
    for date in dates:
        for dtime in ["00", "12"]:
            task(date+dtime)


if __name__ == '__main__':
    dates = [
        "20250701", "20250702", "20250722", "20250723",
        # "20250801", "20250802", "20250803", "20250817",
        # "20250818", "20250821", "20250822",
        # "20250823", "20250825",
    ]
    main(dates)

    # task("2025070100")