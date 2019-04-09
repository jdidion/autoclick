from enum import Enum, EnumMeta
import pathlib
from typing import (
    Callable,
    Generic,
    Iterable,
    NewType,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    cast
)

import click


AUTOCONVERSIONS = []


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


def autoconvert(type_: Type) -> Optional[click.ParamType]:
    """Try to automatically determine a conversion for a given type.

    Returns:
        Type object, if one is found; otherwise None.

    Todo:
        Enable plugins to register their own auto-conversion functions.
    """
    for filter_fn, conversion_fn in AUTOCONVERSIONS:
        if filter_fn(type_):
            return conversion_fn(type_)


T = TypeVar("T")


ReadablePath = NewType("ReadablePath", pathlib.Path)
ReadableFile = NewType("ReadableFile", pathlib.Path)
ReadableDir = NewType("ReadableDir", pathlib.Path)

WritablePath = NewType("WritablePath", pathlib.Path)
WritableFile = NewType("WritableFile", pathlib.Path)
WritableDir = NewType("WritableDir", pathlib.Path)


class OptionalTuple(click.types.Tuple):
    def __init__(self, types):
        super().__init__([])
        self.types = types

    def __call__(self, value, param=None, ctx=None):
        if value is None or all(v is None for v in value):
            return None
        return super().__call__(value, param, ctx)


class DelimitedList(click.ParamType):
    name = 'list'

    def __init__(
        self, item_type: Callable[[str], T] = str, delimiter=',',
        strip_whitespace=True, choices: Optional[Iterable[T]] = None,
        metavar: str = 'LIST'
    ):
        self.item_type = item_type
        self.delimiter = delimiter
        self.strip_whitespace = strip_whitespace
        self.choice = click.Choice(list(choices)) if choices else None
        self.metavar = metavar

    def convert(self, value, param, ctx) -> Tuple[T]:
        if not value:
            return cast(Tuple[T], ())
        items = value.split(self.delimiter)
        if self.strip_whitespace:
            items = (item.strip() for item in items)
        items = tuple(self.item_type(item) for item in items)
        if self.choice:
            items = tuple(self.choice.convert(i, param, ctx) for i in items)
        return items

    def get_metavar(self, param):
        return self.metavar


E = TypeVar('E', bound=EnumMeta)


@autoconversion(lambda type_: issubclass(type_, Enum))
class EnumChoice(Generic[E], click.ParamType):
    """Translates string values into enum instances.

    Args:
        enum_class: Callable (typically a subclass of Enum) that returns enum
            instances.
        xform: How to transform string values before passing to callable;
            upper = convert to upper case; lower = convert to lower case;
            None = don't convert. (default = upper)
    """
    name = 'choice'

    def __init__(
        self, enum_class: Sequence[E], xform='upper',
        metavar: Optional[str] = None
    ):
        self.choice = click.Choice(list(e.name for e in list(enum_class)))
        self.metavar = metavar or self.choice.get_metavar(None)
        self.enum_class = enum_class
        if xform == 'upper':
            self.xform = str.upper
        elif xform == 'lower':
            self.xform = str.lower
        else:
            self.xform = lambda s: s

    def convert(self, value, param, ctx) -> E:
        return self.enum_class[self.choice.convert(self.xform(value), param, ctx)]

    def get_missing_message(self, param):
        return self.choice.get_missing_message(param)

    def __repr__(self):
        return str(self.choice)

    def get_metavar(self, param):
        return self.metavar
