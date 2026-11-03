"""Minimal plugin base classes used by the Kalman plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BasePlugin(ABC):
    """Base callable plugin interface."""

    def __call__(self, *args, **kwargs):
        """Delegate calls to ``process``."""
        return self.process(*args, **kwargs)

    @abstractmethod
    def process(self, *args, **kwargs):
        """Run the plugin."""


class PostProcessingPlugin(BasePlugin):
    """Post-processing plugin marker class."""
