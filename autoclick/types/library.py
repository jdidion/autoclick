from abc import ABCMeta, abstractmethod
from enum import Enum, EnumMeta
import pathlib
import re
from typing import (
    Callable,
    Dict,
    Generic,
    Iterable,
    Match,
    NewType,
    Optional,
    Pattern,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast
)

import click

from autoclick.types import DEFAULT_METAVAR, autoconversion


T = TypeVar("T")

ReadablePath = NewType("ReadablePath", pathlib.Path)
ReadableFile = NewType("ReadableFile", pathlib.Path)
ReadableDir = NewType("ReadableDir", pathlib.Path)

WritablePath = NewType("WritablePath", pathlib.Path)
WritableFile = NewType("WritableFile", pathlib.Path)
WritableDir = NewType("WritableDir", pathlib.Path)


class BaseType(click.ParamType):
    def __init__(self, metavar: str = None):
        self.metavar = metavar

    def get_metavar(self, param):
        return self.metavar or DEFAULT_METAVAR


class Directory(BaseType):
    name = "dir"

    def __init__(
        self, *args, create: bool = False, metavar: str = "DIR", **kwargs
    ):
        super().__init__(metavar)
        kwargs.update(
            file_okay=False, dir_okay=True, readable=True, writable=True
        )
        self._path_type = click.types.Path(*args, **kwargs)
        self._create = create

    def convert(self, value, param, ctx) -> pathlib.Path:
        path = pathlib.Path(self._path_type(value, param, ctx))
        if self._create and not path.exists():
            path.mkdir(parents=True)
        return path


class OptionalTuple(click.types.Tuple):
    def __init__(self, types):
        super().__init__([])
        self.types = types

    def __call__(self, value, param=None, ctx=None):
        if value is None or all(v is None for v in value):
            return None
        return super().__call__(value, param, ctx)


class DelimitedList(BaseType):
    name = "list"

    def __init__(
        self, item_type: Callable[[str], T] = str, delimiter=",",
        strip_whitespace=True, choices: Optional[Iterable[T]] = None,
        metavar: str = "LIST"
    ):
        super().__init__(metavar)
        self.item_type = item_type
        self.delimiter = delimiter
        self.strip_whitespace = strip_whitespace
        self.choice = click.Choice(list(choices)) if choices else None

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


class RegExp(BaseType, metaclass=ABCMeta):
    name = "regexp"

    def __init__(
        self, pattern: Union[str, Pattern], exact: bool = True, metavar: str = "PATTERN"
    ):
        super().__init__(metavar)
        if isinstance(pattern, str):
            self.pattern = re.compile(pattern)
        else:
            self.pattern = cast(Pattern, pattern)
        self.exact = exact

    def convert(self, value, param, ctx):
        if self.exact:
            match = self.pattern.match(value)
        else:
            match = self.pattern.search(value)
        return self._handle_match(match, value, param, ctx)

    @abstractmethod
    def _handle_match(self, match: Match, value, param, ctx):
        pass


class Matches(RegExp):
    """Returns True if the regular expression matches the value.
    """
    def _handle_match(self, match: Match, value, param, ctx):
        return match is not None


class Parse(RegExp):
    """Uses regular expression to parse a value and returns the capture groups
    as a tuple.

    Raises:
        BadParameter if the regular expression does not match the value.
    """
    def _handle_match(self, match, value, param, ctx):
        if match is None:
            self.fail("Pattern {} does not match value {}".format(
                self.pattern, value), ctx=ctx, param=param)
        return match.groups()


E = TypeVar("E", bound=EnumMeta)


@autoconversion(lambda type_: issubclass(type_, Enum))
class EnumChoice(Generic[E], BaseType):
    """Translates string values into enum instances.

    Args:
        enum_class: Callable (typically a subclass of Enum) that returns enum
            instances.
        xform: How to transform string values before passing to callable;
            upper = convert to upper case; lower = convert to lower case;
            None = don"t convert. (default = upper)
    """
    name = "choice"

    def __init__(
        self, enum_class: Sequence[E], xform="upper", metavar: Optional[str] = None
    ):
        super().__init__(metavar)
        self.choice = click.Choice(list(e.name for e in list(enum_class)))
        self.metavar = metavar or self.choice.get_metavar(None)
        self.enum_class = enum_class
        if xform == "upper":
            self.xform = str.upper
        elif xform == "lower":
            self.xform = str.lower
        else:
            self.xform = lambda s: s

    def convert(self, value, param, ctx) -> E:
        return self.enum_class[self.choice.convert(self.xform(value), param, ctx)]

    def get_missing_message(self, param):
        return self.choice.get_missing_message(param)

    def __repr__(self):
        return str(self.choice)


K = TypeVar("K")
V = TypeVar("V")


@autoconversion(lambda type_: issubclass(type_, dict))
class Mapping(BaseType):
    """
    Todo: support conversion of key and value types. Need to expose core.CONVERSIONS.
    """
    name = "mapping"

    def __init__(
        self, key_type: Type[K], value_type: Type[V], metavar: Optional[str] = None
    ):
        super().__init__(metavar)

    def convert(self, value, param, ctx) -> Dict[K, V]:
        return dict(item.split("=") for item in value)
