import re
from typing import List, Sequence

from autoclick.types import *
from autoclick.utils import get_match_type


VALIDATIONS: Dict[Type, List[Callable]] = {}

UNDERSCORES = re.compile("_")
ALPHA_CHARS = set(chr(i) for i in tuple(range(97, 123)) + tuple(range(65, 91)))


class ValidationError(click.UsageError):
    """Raised by a validation function when an input violates a constraint.
    """


def register_validation(type_: Type, validation_fn: Callable):
    """

    Args:
        type_:
        validation_fn:
    """
    if type_ not in VALIDATIONS:
        VALIDATIONS[type_] = []
    VALIDATIONS[type_].append(validation_fn)


def has_validations(type_: Type) -> bool:
    """

    Args:
        type_:

    Returns:

    """
    return type_ in VALIDATIONS


def get_validations(type_: Type) -> Optional[Sequence[Callable]]:
    """

    Args:
        type_:

    Returns:

    """
    return VALIDATIONS.get(type_, None)


def validation(
    match_type: Optional[Type] = None,
    depends: Optional[Tuple[Callable, ...]] = None,
    decorated: Optional[Callable] = None
):
    """Annotates a single-parameter validation.

    Args:
        match_type: The type that will match this validation. If None, is inferred
            from the type of the first parameter in the signature of the annotated
            function.
        depends: Other validations that are pre-requisite for this one.
        decorated: The function to decorate.

    Returns:
        A decorator function.
    """
    def decorator(f: Callable) -> Callable:
        _match_type = match_type
        if _match_type is None:
            _match_type = get_match_type(f)

        if depends:
            def composite_validation(**kwargs):
                for dep in depends:
                    dep(**kwargs)
                f(**kwargs)
            target = composite_validation
        else:
            target = f

        # Annotated validation functions can only ever validate a single parameter
        # so we can explicitly specify the param name and value as kwargs to the
        # decorated function.
        def call_target(**kwargs):
            if len(kwargs) == 2 and set(kwargs.keys()) == {"param_name", "value"}:
                pass
            elif len(kwargs) != 1:
                print(kwargs)
                raise ValueError(
                    "A @validation decorator may only validate a single parameter."
                )
            else:
                kwargs = dict(zip(("param_name", "value"), list(kwargs.items())[0]))
            if kwargs["value"] is not None:
                target(**kwargs)

        register_validation(match_type, call_target)

        return call_target

    if decorated:
        return decorator(decorated)
    else:
        return decorator
