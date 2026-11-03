#from nimm.nowcast.lk_plugin import LK
#from nimm.nowcast.sprog_plugin import Sprog
#from nimm.cli.nimm.now_steps_cli import process
#from nimm.nowcast.linda_plugin import Linda
#from nimm.nowcast.steps_plugin import Steps

import sys
import meteva_base as meb
sys.path.insert(0, '/home/nimm/nimm')
# from nimm.cli.nimm.now_lk_cli import process
from nimm.cli.nimm.now_sprog_cli import process
# from nimm.cli.nimm.now_extrapolation_cli import process
# from nimm.cli.nimm.now_linda_cli import process
# from nimm.cli.nimm.cal_fmm_kalman_cli import process


lk_para = {"size_opening": 3}
# xxx
lk_transform_para = {"threshold": 0.1, "Lambda": 0.3}

ex_transform_para = {"inverse": True,
                     "threshold": -5,
                     "Lambda": 0.3}

fcst_para = {"precip_thr": -5}


result = process(r'/home/nimm/nimm/demo_data/input/nowcast/YYYYMMDD/m10_YYYYMMDDHHTT.nc',
                 '202206271340',
                 output_path_format=r'./demo_data/output/nowcast/YYYYMMDD/YYYYMMDDHHTT.nc',
                 transform_method='box',
                 fcst_timesteps=3,
                 lk_transform_para=lk_transform_para,
                 ex_transform_para=ex_transform_para,
                 fcst_para=fcst_para)


print(result)
