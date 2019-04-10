import inspect
import logging
from typing import Callable, Optional, Type, TypeVar


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
