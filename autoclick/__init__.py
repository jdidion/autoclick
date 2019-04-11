import pkg_resources

from autoclick.utils import LOG, set_global
from autoclick.commands import command, group
from autoclick.core import SignatureError, ParameterCollisionError
from autoclick.composites import (
    TypeCollisionError,
    create_composite,
    composite_type,
    composite_factory
)
from autoclick.composites.library import *
from autoclick.types import conversion
from autoclick.types.library import *
from autoclick.validations import ValidationError, validation
from autoclick.validations.library import *


# Load modules for validation and composite plugins
for entry_point in pkg_resources.iter_entry_points(group='autoclick'):
    LOG.debug("Loading plugin entry-point %s", str(entry_point))
    entry_point.load()
