import pathlib
from typing import NewType
import click

from autoclick.core import ValidationError, conversion, validation


ReadablePath = NewType("ReadablePath", pathlib.Path)


@validation(ReadablePath)
def readable_file(path: pathlib.Path):
    if not path.exists():
        raise ValidationError(f"Path {path} does not exist")
    if not path.is_file():
        raise ValidationError(f"Path {path} is not a file")
