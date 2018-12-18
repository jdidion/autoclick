# AutoClick

AutoClick creates Click-based CLIs using type annotations.

The simplest use of AutoClick requires annotating your main method with `@autoclick.command`:

```python
# test.py
import autoclick

@autoclick.command("greet")
def main(greeting: str, name: str):
    print(f"{greeting} {name}")

if __name__ == "__main__":
    main()
```

```bash
$ python test.py --help
Usage: test.py [OPTIONS] [GREETING] [NAME]

Options:
  --help  Show this message and exit.
```

For additional customization, keyword arguments can be passed to the command annotation:

```python
@autoclick.command(
    short_names={
        "greeting": "G",
        "name": "n"
    },
    show_defaults=True
)
def main(greeting: str = "hello", name: str = "human"):
    print(f"{greeting} {name}")
```

```bash
$ python test.py --help
Usage: test.py [OPTIONS]

Options:
  -G, --greeting TEXT  [default: hello]
  -n, --name TEXT      [default: human]
  --help               Show this message and exit.
```

## Type conversion

In Click, type conversion can be done either in a callback or by using a callable type (such as a subclass of ParamType) as the type. In AutoClick, type conversions are performed automatically based on type annotations for callable types. However, for more complex type conversion, there are three additional methods:

1. Automatic conversion functions. A conversion function is decorated by `@conversion`. The conversion decorator by default infers the type being converted to from the return annotation. Otherwise, the destination type can be specified as an argument to the decorator. The decorator registers the function as the converter for the specified type. When that type is encountered as an annotation of a parameter to a command function, the converter function is used to convert the string argument to that type.

```python
class Bork:
    def __init__(self, n: str):
        self.n = n

    def __str__(self):
        print(",".join(["bork"] * self.n))

@autoclick.conversion()
def bork(n: str) -> Bork:
    return Bork(n)

@autoclick.command("bork")
def main(bork: Bork):
    print(bork)
```

In the case where there needs to be specialized handling of common types, new types can be created using `typing.NewType`:

```python
import typing

DoubleInt = typing.NewType("DoubleInt", int)

@autoclick.conversion(DoubleInt)
def double_int(i: str):
    return int(i) * 2

@autoclick.command("double")
def main(i1: int, i2: DoubleInt):
    print(i1, i2)
```

2. Conversion functions can also be specified explicitly in the command decorator:

```python
@autoclick.command(
    types={
        "a": double_int
    }
)
def main(a: int):
    print(a)
```

Note that any of the types in the `click.Types` package can also be used in this way.

3. For composite types, the `autoclick.composite_type` and `autoclick.composite_factory` functions can be used. An example of a composite type is a class that requires more than one parameter to its constructor. For composite types, the same annotation-based CLI creation is performed, and the parameters are injected into the CLI in place of the composite parameter.

```python
@autoclick.composite_type()
class Foo:
    def __init__(bar: str, baz: int):
        self.bar = bar
        self.baz = baz

@autoclick.command()
def main(foo: Foo):
    print(foo.bar, foo.baz)
```

In this case, the options to main would be `--foo-bar` and `--foo-baz`. Once the CLI is processed, the values of these options are used to construct the `Foo` instance, which is then passed to the call to `main`. The parameter name in the command function is prepended to the parameter names of the composite type, so that a composite type can be used multiple types in a command function signature.

A `autoclick.composite_factory` function returns a complex type. For example, the code below is equivalent to the code above:

```python
@autoclick.composite_factory(Foo)
def foo_factory(bar: str, baz: int):
    return Foo(bar, baz)
```

## Conditionals and Validations

Conditionals and Validations are similar - they are both decorators that take **kwargs parameter. The keywords are parameter names and values are parameter values. When the function takes multiple parameters, they should specify the order; ordering depends on python 3.5+ behavior that dictionaries are ordered implicitly.

A conditional function is used to modify the values of one or more parameters conditional on the value(s) of other parameters. A conditional function may return a dict with keys being parameter names that should be updated, and values being the new parameter values.

A validation function is intended to check that one or more parameter values conform to certain restrictions. The return value of a validation function is ignored.

Both conditional and validation functions can throw ValidationError.

These functions can be associated with parameters in two ways. First, using the 'conditionals' and 'validations' arguments of the command decorator. These are dicts with a parameter name or tuple of parameter names being the key and the function being the value. Second, validation functions can be associated with parameters when they are decorated with `@autoclick.validation` and the parameter type matches the type argument of the validation decorator. Multi-parameter validations can only be associated via the first method. Since conditionals are expected to be multi-valued, there is no `@autoclick.conditional` annotation, i.e. they must always be explicitly specified.

### Type matching

You can also use distinct types created by the `typing.NewType` function for type matching validations. For example, if you want to define a parameter that must be positive and even:

```python
PositiveEven = NewType('PositiveEven', int)

@autoclick.validation(PositiveEven)
def validate_positive_even(arg: int):
  if i < 0:
    raise ValidationError()
  if i % 2 != 0:
    raise ValidationError()
```

Note that the typing library does not currently provide an intersection type. Thus, Positive, Even, and PositiveEven must all be distinct validations. There are two ways to simplify:

1. Add the parameter to the validation dict of the command decorator with a tuple of mutliple functions as the value:

```python
@autoclick.command(
    validations={
        "a": (positive, even)
    }
)
```

2. Create a composite validation:

```python
@autoclick.validation(PositiveEven, (positive, even))
def validate_positive_even(arg: int):
  pass
```

or even

```python
autoclick.validation(PositiveEven, (positive, even))
```

### Docstring utilization

AutoClick uses the [docparse](https://github.com/jdidion/docparse) library to parse the docstrings of command functions and composites to extract help text. Note that currently docparse only supports Google-style docstrings.

```python
# test.py
@autoclick.command(show_defaults=True)
def main(x: str = "hello"):
    """Print a string

    Args:
        x: The string to print.
    """
    print(x)

if __name__ == "__main__":
    main()
```

```bash
$ python test.py --help
Usage: test.py [OPTIONS] [X]

  Print a string

Options:
  -x, --x TEXT  The string to print.  [default: hello]
  --help        Show this message and exit.
```

## Installation

```bash
$ pip intall autoclick
```

## Runtime Dependencies

* Python 3.6+
* docparse

## Build dependencies

* poetry 0.12+
* pytest (with pytest-cov plugin)

## Details

### Option attribute inference

The following sections describe details of how the arguments to click classes/functions are inferred from the type and docstring information:

#### All Parameters

* name (long): parameter name; underscores converted to dashes unless keep_underscores=True in the command decorator.
* name (short): starting from the left-most character of the parameter name, the first character that is not used by another parameter or by any built-in; can be overridden by specifying the 'parameter_names' dictionary in the command decorator.
* type: inferred from the type hint; if type hint is missing, inferred from the default value; if default value is missing, str.
* required: by default, true for positional arguments (Arguments) and false for keyword arguments (Options); if positionals_as_options=True in the command decorator, positional arguments are instead required Options. Required keyword arguments can be specified in the 'required' list in the command decorator.
* default: unset for positional arguments, keyword value for keyword arguments.
* nargs: 1 unless type is Tuple (in which case nargs is the number of arguments to the Tuple).

#### Option-only

* hide_input: False unless the command 'hidden' parameter is specified and includes the parameter name.
* is_flag: True for keyword arguments of type boolean; assumed to be the True option unless the name starts with 'no'; the other option will always be inferred by adding/removing 'no-'
* multiple: True for sequence types
* help: Parsed from docstring.

## Todo

* Look at incorporating features from contributed packages: https://github.com/click-contrib