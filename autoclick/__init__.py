import logging
from pkg_resources import iter_entry_points
import typing

from autoclick.core import (
    SignatureError, ValidationError, ParameterCollisionError, TypeCollisionError,
    conversion, create_composite, composite_type, composite_factory, validation,
    command, group
)
from autoclick.types import *
from autoclick.validations import *


LOG = logging.getLogger("AutoClick")
T = typing.TypeVar("T")


def set_global(name: str, value: T) -> typing.Optional[T]:
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
    prev = core.GLOBAL_CONFIG.get(name, None)
    if prev != value:
        core.GLOBAL_CONFIG[name] = value
    return prev


# Load modules for validation and composite plugins
for entry_point in iter_entry_points(group='autoclick'):
    LOG.debug("Loading plugin entry-point %s", str(entry_point))
    entry_point.load()
