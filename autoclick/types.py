import pathlib
from typing import Callable, Iterable, NewType, Optional, Tuple, TypeVar, cast

import click


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
