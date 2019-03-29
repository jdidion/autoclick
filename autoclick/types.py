import pathlib
from typing import NewType

import click


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
