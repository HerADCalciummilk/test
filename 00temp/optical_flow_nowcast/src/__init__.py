"""Public plugin classes for optical-flow nowcast algorithms."""

__all__ = ["Extrapolation", "LK", "LsqrOpticalFlow", "WindowLsqr", "Lagrangian"]


def __getattr__(name):
    if name == "Extrapolation":
        from optical_flow_nowcast.src.extrapolation_plugin import Extrapolation

        return Extrapolation
    if name == "LK":
        from optical_flow_nowcast.src.lk_plugin import LK

        return LK
    if name in ("WindowLsqr", "LsqrOpticalFlow"):
        from optical_flow_nowcast.src.lsqr_optical_flow_plugin import LsqrOpticalFlow

        return LsqrOpticalFlow
    if name == "Lagrangian":
        from optical_flow_nowcast.src.lagrangian_plugin import Lagrangian

        return Lagrangian
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
