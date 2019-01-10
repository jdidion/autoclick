from enum import Enum
import operator
import os
from typing import Callable

from autoclick.core import ValidationError, validation
from autoclick.types import *


class Comparison(Enum):
    LT = ("<", operator.lt)
    LE = ("<=", operator.le)
    GT = (">", operator.gt)
    GE = (">=", operator.ge)
    EQ = ("=", operator.eq)
    NE = ("!=", operator.ne)

    def __init__(self, symbol: str, fn: Callable):
        self.symbol = symbol
        self.fn = fn


class Defined:
    def __init__(self, n: int, cmp: Comparison):
        self.n = n
        self.cmp = cmp

    def __call__(self, **kwargs):
        if not self.cmp.fn(self.n, len(kwargs)):
            raise ValidationError(
                f"Of the following parameters, the number defined must be " 
                f"{self.cmp.symbol} {self.n}: {','.join(kwargs.keys())}"
            )


def ge_defined(n: int):
    return Defined(n, Comparison.GE)


@validation(ReadablePath)
def readable_path(param_name: str, value: pathlib.Path):
    if not value.exists():
        raise ValidationError(
            f"Parameter {param_name} value {value} does not exist."
        )


@validation(ReadableFile, depends=(readable_path,))
def readable_file(param_name: str, value: pathlib.Path):
    if not value.is_file():
        raise ValidationError(
            f"Parameter {param_name} value {value} is not a file."
        )


@validation(ReadableDir, depends=(readable_path,))
def readable_dir(param_name: str, value: pathlib.Path):
    if not value.is_dir():
        raise ValidationError(
            f"Parameter {param_name} value {value} is not a directory."
        )


@validation(WritablePath)
def writable_path(param_name: str, value: pathlib.Path):
    existing = value
    while not existing.exists():
        if existing.parent:
            existing = existing.parent
        else:
            break
    if not os.access(existing, os.W_OK):
        raise ValidationError(
            f"Parameter {param_name} value {value} is not writable."
        )


@validation(WritableFile, depends=(writable_path,))
def writable_file(param_name: str, value: pathlib.Path):
    if value.exists() and not value.is_file():
        raise ValidationError(
            f"Parameter {param_name} value {value} exists and is not a file."
        )


@validation(WritableDir, depends=(writable_path,))
def writable_dir(param_name: str, value: pathlib.Path):
    if value.exists() and not value.is_dir():
        raise ValidationError(
            f"Parameter {param_name} value {value} exists and is not a directory."
        )
