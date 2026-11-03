"""Kalman forecast correction plugin."""

from __future__ import annotations

from typing import Optional

from kalman_element_forecast_correction.utils.base_plugin import PostProcessingPlugin


class KalmanFix(PostProcessingPlugin):
    """Apply a Kalman mean-error field to a forecast field."""

    def __init__(self, model_id_attr: Optional[str] = None) -> None:
        self.model_id_attr = model_id_attr

    def process(
        self,
        fcst_new,
        me_before = None,
    ):
        """Return the corrected forecast."""
        from kalman_element_forecast_correction.utils.grid_utils import (
            check_for_meb_griddata,
            check_for_xy_coordinates,
            kalman_fix,
        )

        try:
            fcst = check_for_meb_griddata(fcst_new)
            if me_before is not None:
                me_bef = check_for_meb_griddata(me_before)
                if not check_for_xy_coordinates([fcst, me_bef]):
                    raise ValueError("kalman_fix input grid coordinates are not same")
                if not self._compare_time_ge(fcst, me_bef):
                    print("kalman_fix Warning: ME time > fcst time")
                if not self._compare_dtime_eq(fcst, me_bef):
                    print("kalman_fix Warning: fcst and ME dtime not same")
            else:
                me_bef = None
        except Exception as err:
            print(err)
            return None
        return kalman_fix(fcst, me_before=me_bef)

    @staticmethod
    def _compare_time_ge(grd0, grd1) -> bool:
        return (grd0.time.values >= grd1.time.values).all()

    @staticmethod
    def _compare_dtime_eq(grd0, grd1) -> bool:
        return (grd0.dtime.values == grd1.dtime.values).all()
