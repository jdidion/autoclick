from autoclick.core import (
    SignatureError, ValidationError, ParameterCollisionError, TypeCollisionError,
    conversion, create_composite, composite_type, composite_factory, validation,
    command, group
)
from autoclick.types import *
from autoclick.validations import *


def always_pass_context():
    """
    Configure AutoClick to always pass the context to command functions,
    so that it is not required to specify pass_context=True to every
    command/group decorator.
    """
    core.PASS_CONTEXT = True
