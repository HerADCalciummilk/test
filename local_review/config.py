"""本地检查可调常量与 meb API 名单。"""

from __future__ import annotations

# 包必要子目录（中间布局）
REQUIRED_MID_DIRS = ("src", "cli", "test", "docs", "nbs", "resource")
OFFICIAL_COMPANION_TOPS = ("cli", "test", "docs", "nbs", "resource")
PLUGIN_BASE_NAMES = frozenset({"BasePlugin", "PostProcessingPlugin"})
SKIP_DIR_NAMES = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache",
})
PLACEHOLDER_FILE_NAMES = frozenset({".gitkeep"})
DOC_SUFFIXES = frozenset({".md", ".txt", ".rst"})
CODE_SUFFIXES = frozenset({".py"})

MAX_TEXT_FILE_BYTES = 1_500_000
MAX_FILE_CHARS = 12_000
MAX_TOTAL_CHARS = 60_000

# 逐条列出缺 docstring 的上限，超出部分只计数（避免报告刷屏）
DOCSTRING_MISSING_LIST_LIMIT = 40

# 跑 pytest 前必须在 venv 里可用的库：导入名 -> pip 需求串。
# 继承本机库只是加速手段，缺了这里的库脚本会主动 pip 安装，避免
# 「本机没装」变成算法包的测试失败。
REQUIRED_RUNTIME_LIBS: dict[str, str] = {
    "pytest": "pytest",
    "numpy": "numpy",
    "meteva_base": "meteva_base",
}
# 同一个库的其它导入写法（代码里常见 `import meteva_base as meb`）
RUNTIME_LIB_ALIASES: dict[str, tuple[str, ...]] = {
    "meteva_base": ("meb", "meteva"),
}
# 需要私有源或本地 wheel 时不在此处配置：pip 自己的 PIP_INDEX_URL /
# PIP_EXTRA_INDEX_URL / PIP_FIND_LINKS 环境变量与 pip.ini 会被子进程直接继承。

# 依赖完整性：pip 包名与 import 名不一致的常见情况（左边为归一化后的包名）
DIST_TO_IMPORT_NAMES: dict[str, tuple[str, ...]] = {
    "pyyaml": ("yaml",),
    "pillow": ("PIL",),
    "opencv_python": ("cv2",),
    "opencv_python_headless": ("cv2",),
    "scikit_learn": ("sklearn",),
    "scikit_image": ("skimage",),
    "python_dateutil": ("dateutil",),
    "protobuf": ("google",),
    "beautifulsoup4": ("bs4",),
    "attrs": ("attr", "attrs"),
    "gdal": ("osgeo",),
    "netcdf4": ("netCDF4",),
    "basemap": ("mpl_toolkits",),
    "meteva_base": ("meteva_base", "meb"),
    "tables": ("tables",),
    "msgpack_python": ("msgpack",),
}
# conda 包名与 import 名的差异（environment.yml 用得上）
CONDA_TO_IMPORT_NAMES: dict[str, tuple[str, ...]] = {
    "pytorch": ("torch",),
    "opencv": ("cv2",),
    "py_opencv": ("cv2",),
    "netcdf4": ("netCDF4",),
    "pytables": ("tables",),
    "python_graphviz": ("graphviz",),
}
# 测试专用工具：只在 test/ 里出现时不要求写进 requirements.txt
TEST_ONLY_IMPORTS = frozenset({"pytest", "mock", "hypothesis", "pytest_cov"})
# 逐条列出未声明依赖的上限
DEP_LIST_LIMIT = 20
# 依赖总数超过该值提示关注
DEP_TOTAL_WARN_THRESHOLD = 30
# 已停止维护 / 不建议再用的包：包名 -> 原因（归一化后的包名）
DEPRECATED_DISTS: dict[str, str] = {
    "basemap": "已停止维护，建议改用 cartopy",
    "nose": "已停止维护，建议改用 pytest",
    "pycrypto": "已停止维护且有安全问题，建议改用 pycryptodome",
    "sklearn": "是占位包，应声明 scikit-learn",
    "distribute": "早已废弃，由 setuptools 取代",
    "imp": "标准库 imp 已移除，应改用 importlib",
}
# 重量级依赖：静态只做标记，必要性交由 LLM 结合代码规模判断
HEAVY_DISTS = frozenset({
    "tensorflow", "tensorflow_gpu", "torch", "pytorch", "keras", "jax",
    "jaxlib", "transformers", "mxnet", "paddlepaddle", "detectron2",
})

# 报告里额外探测并列出版本的常见依赖
PROBE_EXTRA_LIBS = (
    "pandas", "xarray", "scipy", "matplotlib", "netCDF4",
)

# meb 网格：用于启发式匹配的 import 名与常见 API（可随库演进增补）
# `meb` 是 meteva_base 的惯用简写：`import meteva_base as meb`
MEB_MODULE_NAMES = frozenset({"meb", "meteva_base"})
MEB_API_NAMES = frozenset({
    "checkout_griddata",
    "check_for_meb_griddata",
    "griddata",
    "read_griddata",
    "write_griddata",
    "contourf",
    "contourf_2d_grid",
    "pcolormesh_2d_grid",
    "barbs_grid_wind",
})
# 参数/变量名中出现这些视为网格 I/O 正向信号
MEB_NAME_HINTS = frozenset({
    "griddata", "grid_data", "meb_grid", "grd", "stda",
})
# meb.* 调用只要名字含这些片段就算 meb 数据操作，省得逐个枚举 API
MEB_API_SUBSTRINGS = ("griddata", "stadata", "grid_data", "sta_data")

# 类型注解 / isinstance 里出现这些即视为对应格式的候选证据。
# meb 网格底层是 xr.DataArray（六维），站点数据是 pandas.DataFrame（前六列固定）
MEB_GRID_ANNOTATIONS = frozenset({"DataArray"})
MEB_STATION_ANNOTATIONS = frozenset({"DataFrame"})
# 六维网格的维名与站点表的前六列：成组出现才算指纹，单个词太常见
MEB_GRID_DIM_NAMES = ("member", "level", "time", "dtime", "lat", "lon")
MEB_STATION_COLUMNS = ("level", "time", "dtime", "id", "lat", "lon")
# 成组指纹的命中阈值：六个里出现这么多个才算
MEB_FINGERPRINT_MIN_HITS = 5
# meb 网格必备的六项 attrs。dtime_units/level_type/time_bounds 这类名字辨识度高，
# 撞上其他库的概率极低，所以阈值比维名低
# 网格必备的六项属性，每项给出可接受的写法：
# meb 实际写入的是 model_var，而规范文档里写作 model，两者算同一槽位
MEB_GRID_ATTR_NAMES = (
    ("units",),
    ("model_var", "model"),
    ("dtime_units",),
    ("level_type",),
    ("time_type",),
    ("time_bounds",),
)
MEB_GRID_ATTR_MIN_HITS = 3
