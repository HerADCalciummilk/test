"""Public plugin classes for optical-flow nowcast algorithms."""

__all__ = ["Extrapolation", "LK"]


def __getattr__(name):
    if name == "Extrapolation":
        from optical_flow_nowcast.src.extrapolation_plugin import Extrapolation

        return Extrapolation
    if name == "LK":
        from optical_flow_nowcast.src.lk_plugin import LK

        return LK
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
