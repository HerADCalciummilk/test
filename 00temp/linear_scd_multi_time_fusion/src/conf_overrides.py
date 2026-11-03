"""把 process / CLI 的显式参数写进已加载的 configparser。

``None`` 表示调用方没传，不改 ini。空字符串是显式空值。
布尔写成 ``true`` / ``false``，列表用逗号拼接。
"""
from __future__ import annotations

CONF_KEY_SECTION = {
    "allowed_realtime_minutes": "run",
    "history_step_minutes": "run",
    "dry_run": "run",
    "max_files": "run",
    "source1_dir": "paths",
    "source2_dir": "paths",
    "truth_dir": "paths",
    "output_dir": "paths",
    "enabled": "padding",
    "time_step_minutes": "padding",
    "overwrite": "padding",
    "blending_type": "fusion",
    "keyframe_weights": "fusion",
    "lon_min": "fusion",
    "lon_max": "fusion",
    "lat_min": "fusion",
    "lat_max": "fusion",
    "output_var": "fusion",
    "output_source": "fusion",
}

CONF_KEYS = tuple(CONF_KEY_SECTION)
BOOL_KEYS = ("dry_run", "enabled", "overwrite")
STRING_KEYS = tuple(key for key in CONF_KEYS if key not in BOOL_KEYS)


def _stringify(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    return str(value)


def apply_conf_overrides(cfg, **options) -> None:
    """把非 ``None`` 的参数写入配置。节不存在则创建。"""
    for key, section in CONF_KEY_SECTION.items():
        if key not in options or options[key] is None:
            continue
        if not cfg.has_section(section):
            cfg.add_section(section)
        cfg.set(section, key, _stringify(options[key]))


def add_conf_arguments(parser, add_optional_bool) -> None:
    """给命令行补上全部 conf.ini 键。省略时 dest 为 ``None``。"""
    for name in STRING_KEYS:
        parser.add_argument(
            "--" + name.replace("_", "-"),
            dest=name,
            default=None,
            metavar="VALUE",
            help=f"覆盖配置项 {name}。省略则用 ini；空字符串是显式空值。",
        )
    for name in BOOL_KEYS:
        add_optional_bool(
            parser,
            "--" + name.replace("_", "-"),
            dest=name,
            help_true=f"将 {name} 设为 true，覆盖 ini。",
            help_false=f"将 {name} 设为 false，覆盖 ini。",
        )
