import sys
import pytest


from typing import Optional
import autoclick


RESULT = None


@autoclick.composite_type(
    required=["a"]
)
class Foo:
    """
    A Foo.

    Args:
        a: blah
        b: blorf
    """
    def __init__(self, a: int, b: str = "foo"):
        self.a = a
        self.b = b

    def __eq__(self, other):
        return self.a == other.a and self.b == other.b

    def __str__(self):
        return "{} {}".format(self.a, self.b)


@autoclick.command()
def simple(foo: Foo, *args, bar: int = 1, baz: Optional[float] = None, **kwargs):
    """Process some metasyntactic variables.

    Args:
        foo: A Foo
        *args: Extra args
        bar: A bar
        baz: A baz
        **kwargs: Extra kwargs
    """
    global RESULT
    RESULT = dict(
        foo=foo,
        args=args,
        bar=bar,
        baz=baz,
        kwargs=kwargs
    )


@autoclick.group()
def grp():
    pass


@grp.command("test")
def simple2(foo: Foo, *args, bar: int = 1, baz: Optional[float] = None, **kwargs):
    """Process some metasyntactic variables.

    Args:
        foo: A Foo
        *args: Extra args
        bar: A bar
        baz: A baz
        **kwargs: Extra kwargs
    """
    global RESULT
    RESULT = dict(
        foo=foo,
        args=args,
        bar=bar,
        baz=baz,
        kwargs=kwargs
    )


class CliTest:
    def __init__(self, args, fn, expected):
        self.args = args
        self.fn = fn
        self.expected = expected


TEST_CASES = [
    CliTest(
        args=["1"],
        fn=simple,
        expected=dict(
            foo=Foo(1),
            args=(),
            bar=1,
            baz=None,
            kwargs={}
        )
    ),
    CliTest(
        args=["test", "1"],
        fn=simple2,
        expected=dict(
            foo=Foo(1),
            args=(),
            bar=1,
            baz=None,
            kwargs={}
        )
    )
]


# TODO: tests cannot be parallelized
@pytest.mark.parametrize("test_case", TEST_CASES)
def test_cli(test_case):
    sys.argv = ["main"] + test_case.args
    try:
        test_case.fn()
    except SystemExit:
        pass
    assert RESULT == test_case.expected
