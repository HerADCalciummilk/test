# -*- coding: utf-8 -*-
"""入口参数整合：外部非 None，其次输入配置，再次默认 ``resource/conf.ini``，最后方法预设。

只给入口函数补「仍为 None」的参数。已经传入的值保持不变，
因此默认空配置不会改算法结果。

支持：

- 无节头的 key=value 扁平 ini（如 frequency_matching_rain24）
- 指定单节（如 ``[process]``、``[noise]``）
- 指定多节按顺序合并（后节同名键覆盖先节）
- 目标节不存在时，合并文件中全部节的非空键（便于 ``[transform]`` 等无 ``[process]`` 的包）
- 装饰器 ``merge_params``：调用前按
  「外部 > 输入配置文件 > 默认 resource/conf.ini > 方法预设」整合参数
"""
from __future__ import annotations

import configparser
import functools
import inspect
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Union, get_args, get_origin, get_type_hints

Caster = Union[str, Callable[[str], Any], None]


def conf_path(anchor_file: str, config: Optional[str] = None) -> Optional[Path]:
    """定位本次要读的 ini。

    ``config`` 为空时使用锚点文件所在包的 ``resource/conf.ini``。
    该文件不存在则返回 None。传入的路径不存在则抛出 FileNotFoundError。
    相对路径按包目录解析。
    """
    pkg = Path(anchor_file).resolve().parents[1]
    if config is None or not str(config).strip():
        default = pkg / "resource" / "conf.ini"
        return default if default.is_file() else None
    raw = Path(str(config).strip()).expanduser()
    chosen = raw if raw.is_absolute() else (pkg / raw)
    chosen = chosen.resolve()
    if not chosen.is_file():
        raise FileNotFoundError(f"配置文件不存在: {chosen}")
    return chosen


def _parse_flat_ini(text: str) -> Dict[str, str]:
    """解析无节头的 key=value 文本。空值跳过。"""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or raw.startswith(";"):
            continue
        if "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        key = key.strip()
        value = value.strip()
        if key and value:
            out[key] = value
    return out


def _section_items(parser: configparser.ConfigParser, section: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not parser.has_section(section):
        return out
    for key, value in parser.items(section):
        text_value = value.strip()
        if text_value:
            out[key] = text_value
    return out


def _merge_sections(
    parser: configparser.ConfigParser,
    sections: Sequence[str],
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for section in sections:
        out.update(_section_items(parser, section))
    return out


def _all_section_names(parser: configparser.ConfigParser) -> Sequence[str]:
    # 保持文件中的出现顺序；跳过 DEFAULT
    return tuple(parser.sections())


def load_ini_values(
    anchor_file: str,
    config: Optional[str] = None,
    section: str = "process",
    sections: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """读取 ini 中的非空项。

    - ``sections`` 非空：按给定顺序合并这些节（后覆盖先）
    - 否则若存在 ``section``：只取该节
    - 无节头扁平文件：取全部非空键
    - 有节但目标节不存在：合并全部节的非空键
    """
    path = conf_path(anchor_file, config)
    if path is None:
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        parser = configparser.ConfigParser()
        parser.read_string(text)
    except configparser.MissingSectionHeaderError:
        return _parse_flat_ini(text)

    if sections:
        return _merge_sections(parser, sections)
    if parser.has_section(section):
        return _section_items(parser, section)
    return _merge_sections(parser, _all_section_names(parser))


def load_process_ini(
    anchor_file: str,
    config: Optional[str] = None,
    section: str = "process",
    sections: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """读取运行配置中的非空项（兼容扁平 ini、单节与多节回退）。"""
    return load_ini_values(anchor_file, config, section=section, sections=sections)


def _cast(raw: str, caster: Caster) -> Any:
    if caster is None or caster == "str":
        return raw
    if callable(caster):
        return caster(raw)
    if caster == "int":
        return int(raw)
    if caster == "float":
        return float(raw)
    if caster == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "y", "on")
    if caster == "float_list":
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        if len(parts) == 1:
            return float(parts[0])
        return [float(item) for item in parts]
    if caster == "str_list":
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        if len(parts) == 1:
            return parts[0]
        return parts
    if caster == "int_list":
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        if len(parts) == 1:
            return int(parts[0])
        return [int(item) for item in parts]
    if caster == "int_tuple":
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        return tuple(int(item) for item in parts)
    if caster == "float_tuple":
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        return tuple(float(item) for item in parts)
    if caster == "list_keep":
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def overlay_none(
    anchor_file: str,
    config: Optional[str],
    values: Dict[str, Any],
    *,
    section: str = "process",
    sections: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """用 ini 填补仍为 None 的参数。

    ``values`` 的值可以是当前参数，或 ``(当前值, 转换名)``。
    当前值不是 None 时保持原样。
    """
    ini = load_process_ini(anchor_file, config, section=section, sections=sections)
    out: Dict[str, Any] = {}
    for key, spec in values.items():
        if isinstance(spec, tuple):
            current, caster = spec
        else:
            current, caster = spec, None
        if current is None and key in ini:
            out[key] = _cast(ini[key], caster)
        else:
            out[key] = current
    return out


def _annotation_caster(annotation: Any) -> Caster:
    """由函数注解推断 ini 字符串转换器。"""
    if annotation is inspect.Parameter.empty or annotation is None:
        return None
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Union and type(None) in args:
        non_none = [item for item in args if item is not type(None)]
        if len(non_none) == 1:
            return _annotation_caster(non_none[0])
    if annotation is bool:
        return "bool"
    if annotation is int:
        return "int"
    if annotation is float:
        return "float"
    if annotation is str:
        return "str"
    if annotation is list or origin is list:
        if args and args[0] is int:
            return "int_list"
        if args and args[0] is float:
            return "float_list"
        return "list_keep"
    if annotation is tuple or origin is tuple:
        if args and args[0] is int:
            return "int_tuple"
        return "float_tuple"
    return None


DEFAULT_INI_REL = "resource/conf.ini"


def _load_ini_file(
    path: Optional[Path],
    *,
    section: str = "process",
    sections: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """从已解析的 ini 路径读取非空项。"""
    if path is None or not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        parser = configparser.ConfigParser()
        parser.read_string(text)
    except configparser.MissingSectionHeaderError:
        return _parse_flat_ini(text)
    if sections:
        return _merge_sections(parser, sections)
    if parser.has_section(section):
        return _section_items(parser, section)
    return _merge_sections(parser, _all_section_names(parser))


def _resolve_ini_path(
    anchor_file: Optional[str],
    relative_or_abs: Optional[str],
) -> Optional[Path]:
    """解析 ini 路径。默认 ``resource/conf.ini`` 可以不存在。"""
    if anchor_file:
        try:
            return conf_path(anchor_file, relative_or_abs)
        except FileNotFoundError:
            if relative_or_abs in (None, "", DEFAULT_INI_REL):
                return None
            raise
    if relative_or_abs is None or not str(relative_or_abs).strip():
        return None
    raw = Path(str(relative_or_abs).strip()).expanduser()
    if not raw.is_file():
        raise FileNotFoundError(f"配置文件不存在: {raw}")
    return raw.resolve()


def collect_merged_params(
    external: Mapping[str, Any],
    *,
    ini_path: Optional[str] = DEFAULT_INI_REL,
    default_ini: str = DEFAULT_INI_REL,
    anchor_file: Optional[str] = None,
    section: str = "process",
    sections: Optional[Sequence[str]] = None,
    casters: Optional[Mapping[str, Caster]] = None,
    annotations: Optional[Mapping[str, Any]] = None,
    presets: Optional[Mapping[str, Any]] = None,
    param_names: Optional[Sequence[str]] = None,
    config_keys: Sequence[str] = ("config", "ini_path"),
) -> Dict[str, Any]:
    """按优先级整合参数。

    优先级（高 → 低）::

        1. 外部输入（``external`` 中非 None）
        2. 输入配置文件（调用方 ``config`` / ``ini_path`` 指向的文件）
        3. 默认配置文件（子模块 ``resource/conf.ini``，可由 ``default_ini`` 指定）
        4. 方法预设默认值（``presets``，一般为函数签名默认值）

    ``ini_path`` 为装饰器侧默认配置相对路径，缺省 ``resource/conf.ini``，
    相对路径按 ``anchor_file`` 所在包根解析。
    """
    presets = dict(presets or {})
    caster_map = dict(casters or {})

    def _caster_for(key: str) -> Caster:
        if key in caster_map:
            return caster_map[key]
        if annotations:
            return _annotation_caster(annotations.get(key, inspect.Parameter.empty))
        return None

    def _from_ini(raw: str, key: str) -> Any:
        return _cast(raw, _caster_for(key))

    # --- 定位默认配置与输入配置 ---
    default_rel = default_ini or DEFAULT_INI_REL
    if ini_path is not None and str(ini_path).strip():
        # 装饰器未另指定 default_ini 时，ini_path 即默认配置路径名
        if default_ini == DEFAULT_INI_REL and ini_path != DEFAULT_INI_REL:
            default_rel = str(ini_path).strip()

    default_path = _resolve_ini_path(anchor_file, default_rel if anchor_file else None)
    if default_path is None and anchor_file:
        default_path = _resolve_ini_path(anchor_file, None)

    input_rel: Optional[str] = None
    for key in config_keys:
        value = external.get(key)
        if value is not None and str(value).strip():
            input_rel = str(value).strip()
            break

    input_path: Optional[Path] = None
    if input_rel:
        input_path = _resolve_ini_path(anchor_file, input_rel)

    same_file = (
        input_path is not None
        and default_path is not None
        and input_path.resolve() == default_path.resolve()
    )
    input_ini = _load_ini_file(
        None if same_file else input_path,
        section=section,
        sections=sections,
    )
    default_ini_vals = _load_ini_file(
        default_path,
        section=section,
        sections=sections,
    )
    if same_file and input_path is not None:
        # 显式传入的就是默认文件：只作为「输入配置」层读一次，避免重复
        input_ini = _load_ini_file(input_path, section=section, sections=sections)
        default_ini_vals = {}

    # 只整合目标函数形参，以及调用时显式传入的其它键。不把 ini 里多余键塞进调用。
    if param_names is not None:
        keys = set(param_names)
        keys.update(key for key, value in external.items() if value is not None)
    else:
        keys = set(external.keys()) | set(presets.keys())
        keys |= set(input_ini.keys()) | set(default_ini_vals.keys())

    out: Dict[str, Any] = {}
    for key in keys:
        if key in config_keys:
            continue
        if key in external and external[key] is not None:
            value = external[key]
            if isinstance(value, str):
                caster = _caster_for(key)
                if caster not in (None, "str"):
                    value = _cast(value, caster)
            out[key] = value
        elif key in input_ini:
            out[key] = _from_ini(input_ini[key], key)
        elif key in default_ini_vals:
            out[key] = _from_ini(default_ini_vals[key], key)
        elif key in presets:
            out[key] = presets[key]
        elif key in external:
            out[key] = external[key]
        else:
            out[key] = None

    # 配置路径只写回函数真正声明了的形参。未声明的 config / ini_path 只用来选文件。
    declared = set(param_names) if param_names is not None else None
    active = input_path or default_path
    if active is not None and (declared is None or "config" in declared) and (
        "config" in keys
        or "config" in external
        or declared is None
    ):
        if external.get("config") is not None and str(external.get("config")).strip():
            out["config"] = str(input_path or active)
        else:
            out["config"] = str(active)
    for key in config_keys:
        if key == "config":
            continue
        if declared is not None and key not in declared:
            continue
        if key in keys and key in external and external[key] is not None:
            out[key] = external[key]

    return out


def _submodule_name(anchor_file: Optional[str]) -> Optional[str]:
    """由入口文件定位子模块目录名。``cli`` / ``src`` 下的文件取上一级目录名。"""
    if not anchor_file:
        return None
    path = Path(anchor_file).resolve()
    if path.parent.name in {"cli", "src", "test", "nbs"}:
        return path.parents[1].name
    return path.parent.name


def merge_params(
    ini_path: Optional[str] = DEFAULT_INI_REL,
    *,
    submodule: Optional[str] = None,
    default_ini: str = DEFAULT_INI_REL,
    anchor: Optional[str] = None,
    section: str = "process",
    sections: Optional[Sequence[str]] = None,
    casters: Optional[Mapping[str, Caster]] = None,
):
    """装饰器：调用前按四级优先级整合参数，再传给被装饰函数。

    优先级（高 → 低）::

        1. 外部输入参数
        2. 输入配置文件（调用时的 ``config`` / ``ini_path``）
        3. 默认配置文件（子模块下 ``resource/conf.ini``）
        4. 方法签名上的预设默认值

    不传参数时，子模块名由函数所在文件推断，配置文件默认 ``resource/conf.ini``。
    调用方可额外传入 ``config`` 或 ``ini_path`` 指定这次要读的配置文件。
    函数没有这两个形参时，装饰器用完即丢，不会传进函数体。
    相对路径按入口文件所在包的根目录解析。``config`` 优先于 ``ini_path``。
    列表、元组注解会把配置里的逗号分隔字符串转成对应类型。

    用法::

        @merge_params()
        def process(cls, plugin=None, rpt_times: list = None, pro_count: int = 1):
            ...
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(fn)
        try:
            annotations = get_type_hints(fn)
        except Exception:
            annotations = {
                name: param.annotation
                for name, param in sig.parameters.items()
                if name not in ("self", "cls")
            }
        annotations.pop("return", None)
        presets = {
            name: param.default
            for name, param in sig.parameters.items()
            if name not in ("self", "cls")
            and param.kind
            not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
            and param.default is not inspect.Parameter.empty
        }
        param_names = [
            name
            for name, param in sig.parameters.items()
            if name not in ("self", "cls")
            and param.kind
            not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
        ]

        declared = set(param_names)
        has_var_keyword = any(
            param.kind is inspect.Parameter.VAR_KEYWORD
            for param in sig.parameters.values()
        )
        config_keys = ("config", "ini_path")

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 未声明的配置路径：无 **kwargs 时由本装饰器读取；有 **kwargs 时原样转给下游。
            carried: Dict[str, Any] = {}
            forward: Dict[str, Any] = {}
            for key in config_keys:
                if key in declared or key not in kwargs:
                    continue
                if has_var_keyword:
                    forward[key] = kwargs.pop(key)
                else:
                    carried[key] = kwargs.pop(key)

            # 不 apply_defaults：把签名默认值留给第 4 级「方法预设」
            bound = sig.bind_partial(*args, **kwargs)

            external: Dict[str, Any] = {}
            self_or_cls = None
            self_name = None
            for name, value in bound.arguments.items():
                if name in ("self", "cls") and self_or_cls is None:
                    self_or_cls = value
                    self_name = name
                    continue
                param = sig.parameters[name]
                if param.kind is inspect.Parameter.VAR_KEYWORD:
                    external.update(value)
                elif param.kind is inspect.Parameter.VAR_POSITIONAL:
                    continue
                else:
                    external[name] = value
            external.update(carried)

            anchor_file = anchor
            if not anchor_file:
                mod = sys.modules.get(fn.__module__)
                anchor_file = getattr(mod, "__file__", None) if mod is not None else None

            merged = collect_merged_params(
                external,
                ini_path=ini_path,
                default_ini=default_ini,
                anchor_file=anchor_file,
                section=section,
                sections=sections,
                casters=casters,
                annotations=annotations,
                presets=presets,
                param_names=param_names,
            )

            call_kwargs = dict(merged)
            call_kwargs.update(forward)
            if self_name is not None:
                return fn(self_or_cls, **call_kwargs)
            return fn(**call_kwargs)

        mod = sys.modules.get(fn.__module__)
        detected = getattr(mod, "__file__", None) if mod is not None else None
        wrapper.__nimm_merge_params__ = True  # type: ignore[attr-defined]
        wrapper.__nimm_submodule__ = submodule or _submodule_name(anchor or detected)  # type: ignore[attr-defined]
        wrapper.__nimm_ini__ = ini_path or default_ini or DEFAULT_INI_REL  # type: ignore[attr-defined]
        return wrapper

    return decorator


def parse_kv_argv(
    argv: Optional[Sequence[str]] = None,
    *,
    bare_as_module: bool = False,
) -> Dict[str, str]:
    """把命令行 ``key=value``（或 ``--key=value``）收成字典。

    ``bare_as_module=True`` 时，第一项若不含 ``=`` 则记为 ``module``
    （供 ``utils.nimm_cli`` 使用）。
    """
    items = list(sys.argv[1:] if argv is None else argv)
    out: Dict[str, str] = {}
    if bare_as_module and items and "=" not in items[0] and not str(items[0]).startswith("-"):
        out["module"] = items.pop(0)
    for token in items:
        body = token[2:] if str(token).startswith("--") else str(token)
        if "=" not in body:
            raise ValueError("无法识别的参数: %s。请写成 key=value" % token)
        key, value = body.split("=", 1)
        out[key.replace("-", "_")] = value
    return out


def from_argv(process: Callable[..., Any], argv: Optional[Sequence[str]] = None) -> Callable[..., Any]:
    """装饰已挂 ``@merge_params`` 的 ``process``：把命令行 ``key=value`` 注入后再调用。

    ``cli/__main__.py`` 用法::

        from utils.merge_params import from_argv
        from .xxx_cli import process

        from_argv(process)()

    显式传入的关键字优先于 argv；argv 未写的项仍由 ``@merge_params`` 读 ini / 预设。
    """

    @functools.wraps(process)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        cli_args = list(sys.argv[1:] if argv is None else argv)
        if cli_args[:1] in (["-h"], ["--help"]):
            print("用法: python -m cli [key=value ...]")
            print("参数由 process 的 @merge_params 与 resource/conf.ini 合并。")
            return 0
        parsed = parse_kv_argv(cli_args, bare_as_module=False)
        merged = dict(parsed)
        merged.update(kwargs)
        return process(*args, **merged)

    return wrapper


def run_process(process: Callable[..., Any], argv: Optional[Sequence[str]] = None) -> int:
    """兼容旧写法；等价于 ``from_argv(process)()``。"""
    try:
        result = from_argv(process, argv=argv)()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if isinstance(result, int):
        return result
    return 0
