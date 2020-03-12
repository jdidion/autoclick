from importlib import import_module
from pathlib import Path
import sys
from typing import Optional, Type

import click


def version_option(
    version: Optional[str] = None,
    module: Optional[str] = None,
    *param_decls,
    prog_name: Optional[str] = None,
    message: str = "{prog}, version {ver}",
    option_class: Type[click.Option] = click.Option,
    **kwargs
) -> click.Option:
    """Adds a ``--version`` option which immediately ends the program
    printing out the version number.  This is implemented as an eager
    option that prints the version and exits the program in the callback.

    Args:
        version: the version number to show. If not provided, attempts an auto
            discovery via setuptools.
        module: The name of the module from which the version should be detected if
            `version` is None.
        prog_name: the name of the program (defaults to autodetection)
        message: custom message to show instead of the default
            (``"{prog}, version {ver}"``)
        option_class:
        kwargs: everything else is forwarded to :func:`option`.
    """
    if not any((version, module)):
        raise ValueError("At least one of 'version' or 'module' is required")

    def callback(ctx, param, value):
        if not value or ctx.resilient_parsing:
            return

        ver = version or get_version(module)
        prog = prog_name or ctx.find_root().info_name
        click.echo(message.format(prog=prog, ver=ver), color=ctx.color)
        ctx.exit()

    kwargs.setdefault("is_flag", True)
    kwargs.setdefault("expose_value", False)
    kwargs.setdefault("is_eager", True)
    kwargs.setdefault("help", "Show the version and exit.")
    kwargs["callback"] = callback

    return option_class(param_decls or ("--version",), **kwargs)


def get_version(pkg):
    # Try pkg_resources
    try:
        import pkg_resources
    except ImportError:
        pass
    else:
        try:
            # Try get_distribution
            return pkg_resources.get_distribution(pkg).version
        except:
            # Fall back to looking for entry point
            for dist in pkg_resources.working_set:
                scripts = dist.get_entry_map().get("console_scripts") or {}

                for script_name, entry_point in scripts.items():
                    if entry_point.module_name == pkg:
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
                    return toml_mod.parse(inp.read())["tool"]["poetry"]["version"]
            else:
                path = path.parent

    # Try [_]version.py, which is used by versioneer and other tools
    for mod_name in ("version", "_version"):
        try:
            mod = import_module(mod_name, pkg)

            if hasattr(mod, "__version__"):
                return getattr(mod, "__version__")
        except ImportError:
            pass

    raise RuntimeError("Could not determine version")


def get_toml_parser():
    try:
        import tomlkit
        return tomlkit
    except ImportError:
        pass

    import toml
    return toml
