from typing import Callable, Collection, Dict, Optional, Tuple, Type

import click

from autoclick.utils import get_dest_type


CONVERSIONS: Dict[Type, click.ParamType] = {}
AUTOCONVERSIONS = []
DEFAULT_METAVAR = "ARG"


class ParamTypeAdapter(click.ParamType):
    """
    Adapts a conversion function to a :class:`click.ParamType`.

    Args:
        name:
        fn:
    """
    def __init__(self, name, fn):
        self.name = name
        self.fn = fn

    def convert(self, value, param, ctx):
        return self.fn(value, param, ctx)


def conversion(
    dest_type: Optional[Type] = None,
    depends: Optional[Tuple[Callable, ...]] = None,
    decorated: Optional[Callable] = None
) -> Callable:
    """Annotates a conversion function.

    Args:
        dest_type: Destination type for this conversion. If None, it is
            inferred from the return type of the annotated function.
        depends: Functions on which this conversion depends. They are called in
            order, with the output from each function being passed as the input
            to the next. The type of the parameter to the conversion function
            must be the return type of the last dependency.
        decorated: The function to decorate.

    Returns:
        A decorator function.
    """
    def decorator(f: Callable) -> Callable:
        _dest_type = dest_type
        if _dest_type is None:
            _dest_type = get_dest_type(f)

        if depends:
            def composite_conversion(value):
                for dep in depends:
                    value = dep(value)
                return f(value)

            target = composite_conversion
        else:
            target = f

        click_type = ParamTypeAdapter(_dest_type.__name__, target)
        register_conversion(_dest_type, click_type)
        return target

    if decorated:
        return decorator(decorated)
    else:
        return decorator


def register_conversion(type_: Type, click_type: click.ParamType):
    """

    Args:
        type_:
        click_type:
    """
    CONVERSIONS[type_] = click_type


def has_conversion(type_: Type) -> bool:
    """

    Args:
        type_:

    Returns:

    """
    return type_ in CONVERSIONS


def get_conversion(match_type: Type, true_type: Optional[Type] = None) -> Callable:
    """
    Gets a conversion function for the given type, if one is available.

    Args:
        match_type: Type to match against.
        true_type: Type to auto-convert, if `match_type` does not match any
            registered conversions.

    Returns:
        A Callable - generally either a click.ParamType (if a conversion was found) or
        `true_type`.
    """
    if match_type in CONVERSIONS:
        return CONVERSIONS[match_type]

    if true_type is None:
        true_type = match_type

    for filter_fn, conversion_fn in AUTOCONVERSIONS:
        if filter_fn(true_type):
            return conversion_fn(true_type)

    if issubclass(true_type, Collection):
        return match_type

    return true_type


def autoconversion(
    filter_fn: Callable[[Type], bool],
    conversion_fn: Optional[Callable[[Type], click.ParamType]] = None
):
    """
    Decorator

    Args:
        filter_fn: Function that returns a boolean indicating whether or not
            the autoconversion applies to a given type.
        conversion_fn: Function that returns a `click.ParamType` for a given type.

    Returns:
        An object that is a subclass of `click.ParamType`.
    """
    def decorator(fn):
        AUTOCONVERSIONS.append((filter_fn, conversion_fn or fn))
        return fn
    return decorator
