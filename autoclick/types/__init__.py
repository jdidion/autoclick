from abc import ABCMeta, abstractmethod
from typing import Callable, Collection, Dict, List, Optional, Tuple, Type, Union, cast

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


class AggregateTypeMixin(metaclass=ABCMeta):
    @abstractmethod
    def aggregate(self, values):
        pass


class Aggregate:
    def __init__(self, param_name: str, param_type: AggregateTypeMixin):
        self.param_name = param_name
        self.param_type = param_type

    def __call__(self, ctx: click.Context):
        if self.param_name in ctx.params:
            agg_value = self.param_type.aggregate(ctx.params.pop(self.param_name))
            ctx.params[self.param_name] = agg_value


def conversion(
    dest_type: Optional[Type] = None,
    depends: Optional[Tuple[Callable, ...]] = None,
    decorated: Optional[Callable] = None,
    name: Optional[str] = None
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
        name: Type name; defaults to the `name` attribute of `dest_type`.

    Returns:
        A decorator function.
    """
    def decorator(f: Callable) -> Callable:
        _name = name
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

        if _name is None:
            if hasattr(_dest_type, "__name__"):
                _name = _dest_type.__name__
            elif hasattr(_dest_type, "_name"):
                _name = _dest_type._name
            else:
                raise ValueError(
                    f"Name cannot be determined from {_dest_type}; the 'name' "
                    f"argument must be provided."
                )

        click_type = ParamTypeAdapter(_name, target)
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


def get_conversion(
    match_type: Type, true_type: Optional[Type] = None,
    type_args: Optional[List[Type]] = None
) -> Callable:
    """
    Gets a conversion function for the given type, if one is available.

    Args:
        match_type: Type to match against.
        true_type: Type to auto-convert, if `match_type` does not match any
            registered conversions.
        type_args: If the original type was generic, this is the list of type arguments.

    Returns:
        A Callable - generally either a click.ParamType (if a conversion was found) or
        `true_type`.
    """
    if match_type in CONVERSIONS:
        return CONVERSIONS[match_type]

    if true_type is None:
        true_type = match_type

    for filter_fn, conversion_fn, pass_type in AUTOCONVERSIONS:
        if filter_fn(true_type):
            args = []
            if pass_type:
                args.append(true_type)
            if type_args:
                args.append(type_args)
            return conversion_fn(*args)

    if issubclass(true_type, Collection):
        return match_type

    return true_type


def register_autoconversion(
    filter_fn: Union[Type, Callable[[Type], bool]],
    conversion_fn: Callable[[Type, Optional[List[Type]]], click.ParamType],
    pass_type: bool = True
):
    if isinstance(filter_fn, type):
        filter_type = cast(type, filter_fn)
        filter_fn = lambda type_: issubclass(type_, filter_type)
    AUTOCONVERSIONS.append((filter_fn, conversion_fn, pass_type))


def autoconversion(
    filter_fn: Union[Type, Callable[[Type], bool]],
    conversion_fn: Optional[Callable[[Type], click.ParamType]] = None,
    pass_type: bool = True
):
    """
    Decorator that registers an automatic conversion for a (usually built-in) type.

    Args:
        filter_fn: Function that returns a boolean indicating whether or not
            the autoconversion applies to a given type.
        conversion_fn: Function that returns a `click.ParamType` for a given type.
        pass_type: Whether to pass the type being converted as the first argument
            to the conversion function (defaults to True).

    Returns:
        An object that is a subclass of `click.ParamType`.
    """
    def decorator(fn: Callable[[Type], click.ParamType]):
        register_autoconversion(filter_fn, conversion_fn or fn, pass_type)
        return fn
    return decorator
