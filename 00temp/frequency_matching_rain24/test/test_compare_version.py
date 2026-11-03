import meteva_base as meb
import numpy as np
import matplotlib.pyplot as plt
import datetime


ecmwf_v2 = r'D:/Work/multi_optimize_tp_24h_250402/resource/output/rain24/ecmwf/YYYYMMDDHH/YYYYMMDDHH.TTT.m4'
ecmwf_nimm = r'D:/Work/multi_optimize_tp_24h/resource/output/rain24/ecmwf/YYYYMMDDHH/YYYYMMDDHH.TTT.m4'
png_dir = r'D:/Work/multi_optimize_tp_24h/resource/output/pngs/YYYYMMDD'
dtime = 36
ftime = '2025100100'

fo_time = datetime.datetime.strptime(ftime, '%Y%m%d%H')
ec_2_path = meb.get_path(ecmwf_v2, fo_time, dtime)
ec_1_path = meb.get_path(ecmwf_nimm, fo_time, dtime)
pg_path = meb.get_path(png_dir, fo_time)

ec1_grd = meb.read_griddata_from_micaps4(ec_2_path)
ec2_grd = meb.read_griddata_from_micaps4(ec_1_path)

map_extend = [70.0, 140.0, 0, 60.0]
axs = meb.creat_axs(2, map_extend, ncol=2, add_index=['ecmwf_v2', 'ecmwf_nimm'],
                    sup_title=f'{ftime}_{dtime:03d}时效降水', sup_fontsize=26, wspace=1, height=26, width=26)
clevs = np.array([0, 0.1, 10, 25, 50, 100])
meb.add_contourf(axs[0], ec1_grd, cmap='rainbow', clevs=clevs, add_colorbar=True)
meb.add_contourf(axs[1], ec2_grd, cmap='rainbow', clevs=clevs, add_colorbar=True)

# plt.savefig(f"{pg_path}/{ftime}_{dtime:03d}_1.png", bbox_inches='tight')


ecmwf_v2 = r'D:/Work/multi_optimize_tp_24h_250402/resource/output/rain24/ecmwf/YYYYMMDDHH/YYYYMMDDHH.TTT.m3'
ecmwf_nimm = r'D:/Work/multi_optimize_tp_24h/resource/output/rain24/ecmwf/YYYYMMDDHH/YYYYMMDDHH.TTT.m3'
dtime = 36
ec_2_path = meb.get_path(ecmwf_v2, fo_time, dtime)
ec_1_path = meb.get_path(ecmwf_nimm, fo_time, dtime)

ec1_sta = meb.read_stadata_from_micaps3(ec_2_path)
ec2_sta = meb.read_stadata_from_micaps3(ec_1_path)

axs = meb.creat_axs(2, map_extend, ncol=2, add_index=['ecmwf_v2', 'ecmwf_nimm'],
                    sup_title=f'{ftime}_{dtime:03d}时效降水', sup_fontsize=26, wspace=1, height=26, width=26)
meb.add_scatter(axs[0], ec1_sta, cmap=meb.cmaps.rain_24h, add_colorbar=True, alpha=1)
meb.add_scatter(axs[1], ec2_sta, cmap=meb.cmaps.rain_24h, add_colorbar=True, alpha=1)

# plt.savefig(f"{pg_path}/{ftime}_{dtime:03d}_2.png", bbox_inches='tight')