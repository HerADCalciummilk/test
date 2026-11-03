"""Compatibility base class for archived NIMM plugins."""


class PostProcessingPlugin:
    """Minimal stand-in for the original NIMM PostProcessingPlugin."""

    def process(self, *args, **kwargs):
        raise NotImplementedError

