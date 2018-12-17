from autoclick.core import ValidationError
from enum import Enum
import operator
from typing import Callable


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


def ge_defined(n: int): Defined(n, Comparison.GE)
