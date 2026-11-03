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


def main(ftime):
    pass
    sj =pd.read_hdf(ob_dir)



if __name__ == '__main__':
    h5_file = r"D:\data1\zhongzhuan\20260601\verify_data_20250401-20251001.h5"
    sta_all = pd.read_hdf(h5_file, key="sta_all")
    print(sta_all)
    # sta_all = sta_all[sta_all['time'].dt.date == pd.to_datetime('2025-07-01').date()]
    sta_all = sta_all[sta_all['time'] == pd.to_datetime('2025-07-01 08:00:00')]
    print(sta_all)
    sta_all = sta_all[sta_all['dtime'] == 36]
    print(sta_all)
    df_ob = sta_all[['level', 'time', 'dtime', 'id', 'lat', 'lon', 'ob']].copy()
    print(df_ob)

    df_ec = sta_all[['level', 'time', 'dtime', 'id', 'lat', 'lon', 'ec']].copy()
    print(df_ec)

    df_mait = sta_all[['level', 'time', 'dtime', 'id', 'lat', 'lon', 'mait']].copy()
    print(df_mait)

    map_extend = [113, 119.99, 36, 42.99]

    axs = meb.creat_axs(2, map_extend, ncol=2, sup_title="2022年5月27日降水观测", add_index=["a", "b"], sup_fontsize=8)
    meb.add_scatter_text(axs[0], df_ob, cmap=meb.cmaps.rain_24h, tag=0)
    meb.add_scatter(axs[1], df_ec, cmap=meb.cmaps.rain_24h, add_colorbar=True, alpha=1)
    meb.add_scatter(axs[1], df_mait, cmap=meb.cmaps.rain_24h, add_colorbar=True, alpha=1)

    plt.savefig(r"a.png", bbox_inches='tight')
