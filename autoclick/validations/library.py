from enum import Enum
import operator
import os
import pathlib
from typing import Callable, Sequence, Tuple, Union

from autoclick.types.library import (
    ReadablePath,
    ReadableFile,
    ReadableDir,
    WritablePath,
    WritableFile,
    WritableDir
)
from autoclick.validations import ValidationError, validation


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
    """
    Validate that some number of paramters are defined.

    Args:
        n: Number to compare against the number of defined parameters.
        cmp: Comparison.
    """
    def __init__(self, n: int = 1, cmp: Comparison = Comparison.GE):
        self.n = n
        self.cmp = cmp

    def __call__(self, **kwargs):
        defined = len(tuple(filter(None, kwargs.values())))
        if not self.cmp.fn(defined, self.n):
            raise ValidationError(
                f"Of the following parameters, the number defined must be " 
                f"{self.cmp.symbol} {self.n}: {', '.join(kwargs.keys())}"
            )


def defined_ge(n: int):
    return Defined(n, Comparison.GE)


class Mutex:
    def __init__(self, *groups: Union[int, Tuple[int, ...]], max_defined: int = 1):
        self.groups = groups
        self.max_defined = max_defined

    def __call__(self, **kwargs):
        args = list(kwargs.items())
        groups = self.groups or range(len(args))
        defined = []
        for group in groups:
            if isinstance(group, int):
                group = [group]
            for i in group:
                if args[i][1] is not None:
                    defined.append(group)
                    break
        if len(defined) > self.max_defined:
            group_str = ",".join(f"({','.join(str(i) for i in g)})" for g in defined)
            raise ValidationError(
                f"Values specified for > {self.max_defined} mutually exclusive groups: "
                f"{group_str}"
            )


class SequenceLength:
    """
    Validate that the length of a sequence is within certain bounds.

    Args:
        *lengths: either a single value, which specifies the exact length a sequence
            must have, or a min and max value.
    """
    def __init__(self, *lengths):
        if len(lengths) == 1:
            self.minlen = self.maxlen = lengths[0]
        else:
            self.minlen, self.maxlen = lengths
        if self.minlen > self.maxlen:
            raise ValueError("'minlen' must be <= 'maxlen'")

    def __call__(self, param_name: str, value: Sequence):
        if len(value) < self.minlen:
            raise ValidationError(
                f"Parameter {param_name} must have at least {self.minlen} elements."
            )
        if len(value) < self.maxlen:
            raise ValidationError(
                f"Parameter {param_name} can have at most {self.maxlen} elements."
            )


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
