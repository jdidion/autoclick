import inspect
import logging
from pathlib import Path
import sys
from typing import Callable, Optional, Type, TypeVar

import click


LOG = logging.getLogger("AutoClick")
EMPTY = inspect.Signature.empty
EMPTY_OR_NONE = {EMPTY, None}
GLOBAL_CONFIG = {}
T = TypeVar("T")


def set_global(name: str, value: T) -> Optional[T]:
    """
    Configure global AutoClick settings:

    * "infer_short_names": (bool) whether to always/never infer paramter short names.
         (defaut=True)
    * "keep_underscores": (bool) whether to retain underscores in paramter long names
        or covert them to dashes. (defaut=False)
    * "pass_context": (bool) whether to always/never pass the context to command
        functions, so that it is not required to specify pass_context=True to every
        command/group decorator. (defaut=False)

    Args:
        name: The global parameter name.
        value: The paramter value.

    Returns:
        The previous value of the setting.
    """
    prev = GLOBAL_CONFIG.get(name, None)
    if prev != value:
        GLOBAL_CONFIG[name] = value
    return prev


def get_global(name: str, default: T) -> T:
    return GLOBAL_CONFIG.get(name, default)


def get_match_type(f: Callable) -> Type:
    params = inspect.signature(f).parameters
    if len(params) == 0:
        raise ValueError(f"Function {f} must have at least one parameter")
    params = list(params.values())
    if len(params) > 1:
        for p in params[1:]:
            if p.default == EMPTY:
                raise ValueError(
                    f"All but the first parameter must have default values in "
                    f"the signature of function {f}."
                )
    return params[0].annotation


def get_dest_type(f: Callable) -> Type:
    dest_type = inspect.signature(f).return_annotation
    if dest_type in EMPTY_OR_NONE:
        raise ValueError(f"Function {f} must have a non-None return annotation")
    return dest_type


def get_module():
    if hasattr(sys, "_getframe"):
        return sys._getframe(1).f_globals.get("__name__")
    else:
        raise RuntimeError("Could not determine module")


def get_version(module) -> str:
    # Try pkg_resources
    try:
        import pkg_resources
    except ImportError:
        pass
    else:
        try:
            # Try get_distribution
            return pkg_resources.get_distribution(module).version
        except:
            # Fall back to looking for entry point
            for dist in pkg_resources.working_set:
                scripts = dist.get_entry_map().get("console_scripts") or {}
                for script_name, entry_point in scripts.items():
                    if entry_point.module_name == module:
                        return dist.version

    # Try pyproject.toml
    try:
        toml_mod = get_toml_parser()
    except ImportError:
        pass
    else:
        path = Path.cwd()
        while path:
            pyproj = path / "pyproject.toml"
            if pyproj.exists():
                with open(pyproj, "rt") as inp:
                    toml = toml_mod.parse(inp.read())
                    return toml["tool"]["poetry"]["version"].as_string()
            else:
                path = path.parent

    raise RuntimeError("Could not determine version")


def get_toml_parser():
    try:
        import tomlkit
        return tomlkit
    except ImportError:
        pass

    import toml
    return toml


def serialize_command(command: click.Command) -> dict:
    desc = {

    }

    return desc
