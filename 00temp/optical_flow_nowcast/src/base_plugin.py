"""光流外推插件基类。BasePlugin 来自 ``00temp/utils/base_plugin.py``。"""

import importlib.util
import sys
from pathlib import Path

_SHARED_BASE_PLUGIN = "nimm_shared_base_plugin"


def _load_shared_base_plugin():
    """加载 ``00temp/utils/base_plugin.py``，全进程共用同一个 BasePlugin。"""
    cached = sys.modules.get(_SHARED_BASE_PLUGIN)
    if cached is not None:
        return cached
    path = Path(__file__).resolve().parents[2] / "utils" / "base_plugin.py"
    spec = importlib.util.spec_from_file_location(_SHARED_BASE_PLUGIN, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_SHARED_BASE_PLUGIN] = module
    spec.loader.exec_module(module)
    return module


BasePlugin = _load_shared_base_plugin().BasePlugin


class PostProcessingPlugin(BasePlugin):
    """后处理插件。子类重写 process 作为入口。"""
