"""Kalman algorithm plugins and workflow code."""

__all__ = ["KalmanFix", "KalmanME"]


def __getattr__(name):
    if name == "KalmanFix":
        from kalman_element_forecast_correction.src.kalman_fix_plugin import KalmanFix

        return KalmanFix
    if name == "KalmanME":
        from kalman_element_forecast_correction.src.kalman_me_plugin import KalmanME

        return KalmanME
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
