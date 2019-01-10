import typing

from autoclick.core import (
    SignatureError, ValidationError, ParameterCollisionError, TypeCollisionError,
    conversion, create_composite, composite_type, composite_factory, validation,
    command, group
)
from autoclick.types import *
from autoclick.validations import *


def set_global(name: str, value: typing.Any):
    """
    Configure global AutoClick settings:

    * "pass_context": (bool) whether to always/never pass the context to command
    functions, so that it is not required to specify pass_context=True to every
    command/group decorator.
    * "infer_short_names": (bool) whether to always/never infer paramter short names.

    Args:
        name: The global parameter name.
        value: The paramter value.
    """
    core.GLOBAL_CONFIG[name] = value
