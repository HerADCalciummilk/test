#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本模块定义了插件基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BasePlugin(ABC):
    """基础插件类。"""

    def __call__(self, *args, **kwargs):
        """使插件类实例可以直接调用。"""
        return self.process(*args, **kwargs)

    @abstractmethod
    def process(self, *args, **kwargs):
        """插件处理主函数。"""
        pass
