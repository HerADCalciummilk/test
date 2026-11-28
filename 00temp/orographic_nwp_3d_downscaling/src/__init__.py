"""Public plugin exports for orographic_nwp_3d_downscaling."""

__all__ = ["BestEtaPlugin", "MaxMinPlugin", "SpatialInterpPlugin", "TimeInterpPlugin"]


def __getattr__(name):
    if name in __all__:
        from . import fast_refine_interp_plugin

        return getattr(fast_refine_interp_plugin, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
