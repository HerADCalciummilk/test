from nimm import PostProcessingPlugin
from typing import Optional, Tuple
import meteva_base as meb
import os
import sys
sys.path.append('/data/code/nimm/nimm/sta_grid_interp')
from nimm.sta_grid_interp.interp_station_to_grid_renew import interp_sg_idw


class InterpSgTotal(PostProcessingPlugin):
    def __init__(self, 
                 model_id_attr: Optional[str] = None):
        """
        Initialise the class

        Args:
            model_id_attr:
                Name of the attribute used to identify the source model for
                blending.
        """
        self.model_id_attr = model_id_attr
    def process(self,sta, to_grid, grid_background=None, **args):
        ## sta0  站点数据
        ## to_grid:  格点信息类
        ## grid_background: 背景场，默认为0
        ## 其他参数： effectR=1000, nearNum=8,decrease = 2
        ## 无背景场时， 直接反距离插值；   有背景场时，使用站点格点误差扩散及反距离插值
        delta_effect_r = args.pop("delta_effectR", 400)
        delta_near_num = args.pop("delta_nearNum", 10)
        delta_decrease = args.pop("delta_decrease", 2)
        if grid_background is None:
            grid = interp_sg_idw(sta, to_grid, **args)
        else:
            print(to_grid)
            grid_background = meb.interp_gg_linear(grid_background, grid=to_grid)
            grid = interp_sg_idw_delta(
                sta,
                grid0=grid_background,
                effectR=delta_effect_r,
                nearNum=delta_near_num,
                decrease=delta_decrease,
            )
        return(grid)
    
if __name__=="__main__":
    sta=meb.read_stadata_from_csv(r'/data/code/nimm/demo_data/input/sta_grid_interp/sta.csv')
    grid=meb.read_griddata_from_nc(r'/data/code/nimm/demo_data/input/sta_grid_interp/grid.nc')
    grid_info=meb.get_grid_of_data(grid)
    #Interp_sg_total().process(sta,grid_info)
    InterpSgTotal().process(sta,grid_info)