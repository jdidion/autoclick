import json
import sys
from typing import Optional, Type

import click

from autoclick.utils import get_module, get_version, serialize_command


def version_option(
    version: Optional[str] = None,
    module: Optional[str] = None,
    *param_decls,
    prog_name: Optional[str] = None,
    message: str = "{prog}, version {ver}",
    option_class: Type[click.Option] = click.Option,
    **kwargs
) -> click.Option:
    """Adds a ``--version`` option that immediately ends the program
    printing out the version number.  This is implemented as an eager
    option that prints the version and exits the program in the callback.

    Args:
        version: the version number to show. If not provided, attempts an auto
            discovery via setuptools.
        module:
        prog_name: the name of the program (defaults to autodetection)
        message: custom message to show instead of the default
            (``"{prog}, version {ver}"``)
        option_class:
        kwargs: everything else is forwarded to :func:`option`.
    """
    def callback(ctx, param, value):
        if not value or ctx.resilient_parsing:
            return
        ver = version or get_version(module or get_module())
        prog = prog_name or ctx.find_root().info_name
        click.echo(message.format(prog, ver), color=ctx.color)
        ctx.exit()

    kwargs.setdefault("is_flag", True)
    kwargs.setdefault("expose_value", False)
    kwargs.setdefault("is_eager", True)
    kwargs.setdefault("help", "Show the version and exit.")
    kwargs["callback"] = callback

    return option_class(*(param_decls or ("--version",)), **kwargs)


def describe_option(
    *param_decls,
    option_class: Type[click.Option] = click.Option,
    **kwargs
) -> click.Option:
    """Adds a ``--describe`` option that immediately ends the program
    printing out the version number. This is implemented as an eager
    option that prints the version and exits the program in the callback.

    Args:
        option_class:
        kwargs: everything else is forwarded to :func:`option`.
    """
    def callback(ctx: click.Context, param, value):
        if value and not ctx.resilient_parsing:
            json.dump(
                serialize_command(ctx.command),
                sys.stdout
            )
            ctx.exit()

    kwargs.setdefault("is_flag", True)
    kwargs.setdefault("expose_value", False)
    kwargs.setdefault(
        "help", "Print the structured description of this command to stdout"
    )
    kwargs.setdefault("is_eager", True)
    kwargs["callback"] = callback

    return option_class(*(param_decls or (f"--describe",)), **kwargs)
