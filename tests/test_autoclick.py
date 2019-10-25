import sys
import pytest


from typing import Dict, Optional
import autoclick


RESULT = None


@autoclick.composite_type(
    required=["a"]
)
class Foo:
    """
    A Foo.

    Args:
        num: blah
        name: blorf
    """
    def __init__(self, num: int, name: str = "foo"):
        self.num = num
        self.name = name

    def __eq__(self, other):
        return self.num == other.num and self.name == other.name

    def __repr__(self):
        return "{} {}".format(self.num, self.name)


@autoclick.command()
def simple(foo: Foo, bar: int = 1, baz: Optional[float] = None):
    """Process some metasyntactic variables.

    Args:
        foo: A Foo
        bar: A bar
        baz: A baz
    """
    global RESULT
    RESULT = dict(
        foo=foo,
        bar=bar,
        baz=baz
    )


@autoclick.group()
def grp():
    pass


@grp.command("test")
def simple2(
    foo: Foo, bar: int = 1, baz: Optional[float] = None,
    extra_args: Optional[Dict[str, str]] = None
):
    """Process some metasyntactic variables.

    Args:
        foo: A Foo
        bar: A bar
        baz: A baz
        extra_args:
    """
    global RESULT
    RESULT = dict(
        foo=foo,
        bar=bar,
        baz=baz,
        extra_args=extra_args
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
            bar=1,
            baz=None
        )
    ),
    CliTest(
        args=["test", "1"],
        fn=simple2,
        expected=dict(
            foo=Foo(1),
            bar=1,
            baz=None
        )
    ),
    CliTest(
        args=["test", "1", "-q", "foo=bar"],
        fn=simple2,
        expected=dict(
            foo=Foo(1),
            bar=1,
            baz=None,
            extra_kwargs={"foo": "bar"}
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
