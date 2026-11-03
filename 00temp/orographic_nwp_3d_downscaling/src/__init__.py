"""Public plugin exports for nimm_g_interp."""

__all__ = ["FastRefineInterpPlugin"]


def __getattr__(name):
    if name == "FastRefineInterpPlugin":
        from .fast_refine_interp_plugin import FastRefineInterpPlugin

        return FastRefineInterpPlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
