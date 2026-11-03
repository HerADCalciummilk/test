"""Kalman mean-error update plugin."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from kalman_element_forecast_correction.utils.base_plugin import PostProcessingPlugin


class KalmanME(PostProcessingPlugin):
    """Update a Kalman mean-error or mean-absolute-error field."""

    def __init__(
        self,
        model_id_attr: Optional[str] = None,
        alpha: Optional[float] = 0.1,
        is_mae: Optional[bool] = False,
        time_new: Optional[datetime] = None,
        dtime_new: Optional[int] = None,
    ) -> None:
        self.model_id_attr = model_id_attr
        self.alpha = alpha
        self.is_mae = is_mae
        self.time_new = time_new
        self.dtime_new = dtime_new

    def process(
        self,
        fcst_new,
        obs_new,
        me_before = None,
    ):
        """Update Kalman error using the latest forecast and observation grids."""
        from kalman_element_forecast_correction.utils.grid_utils import (
            check_for_meb_griddata,
            check_for_xy_coordinates,
            kalman_me,
        )

        try:
            fcst = check_for_meb_griddata(fcst_new)
            obs = check_for_meb_griddata(obs_new)
            if me_before is not None:
                me_bef = check_for_meb_griddata(me_before)
                data = [fcst, obs, me_bef]
            else:
                me_bef = None
                data = [fcst, obs]

            if not check_for_xy_coordinates(data):
                print("kalman_me ERROR: OBS and Fcst grid coordinates are not same")
            if not check_for_xy_coordinates([fcst, obs], is_time_match=True):
                print("kalman_me Warning: fcst and obs time/dtime not match")
            if me_bef is not None:
                if not self._compare_time_ge(fcst, me_bef):
                    print("kalman_me Warning: ME time > fcst time")
                if not self._compare_dtime_eq(fcst, me_bef):
                    print("kalman_me Warning: fcst and ME dtime not same")
        except Exception as err:
            print(err)
            return None

        return kalman_me(
            fcst,
            obs,
            me_bef,
            alpha=self.alpha,
            is_mae=self.is_mae,
            time_new=self.time_new,
            dtime_new=self.dtime_new,
        )

    @staticmethod
    def _compare_time_ge(grd0, grd1) -> bool:
        return (grd0.time.values >= grd1.time.values).all()

    @staticmethod
    def _compare_dtime_eq(grd0, grd1) -> bool:
        return (grd0.dtime.values == grd1.dtime.values).all()
