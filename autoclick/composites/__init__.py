from abc import ABCMeta, abstractmethod
import functools
import inspect
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
    cast
)

import click

from autoclick.core import (
    DEC,
    BaseDecorator,
    ParameterInfo,
    SignatureError,
    apply_to_parsed_args
)
from autoclick.utils import get_dest_type


class TypeCollisionError(Exception):
    """Raised when a decorator is defined for a type for which a decorator of the
    same kind has already been defined.
    """


class Composite(BaseDecorator[DEC], metaclass=ABCMeta):
    """
    Represents a complex type that requires values from multiple parameters. A
    composite parameter is defined by annotating a class using the `composite_type`
    decorator, or by annotating a function with the `composite_factory` decorator.
    The parameters of the composite type's construtor (exluding `self`) or of the
    composite factory function are added to the command prior to argument parsing,
    and then they are replaced by an instance of the annotated class after parsing.

    Note that composite parameters cannot be nested, i.e. a parameter cannot be a
    list of composite types, and a composite type cannot itself have composite type
    parameters - either of these will raise a :class:`SignatureError`.

    Args:
        parameters_as_args: Whether to treat all parameters as Arguments regardless
            of whether they are optional or required.
        force_create: Always create an instance of the composite type, even if all
            the parameter values are `None`.
        kwargs: Keyword arguments passed to :class:`BaseDecorator` constructor.

    Kwargs:
        to_wrap: The function/class to wrap.
        keep_underscores: Whether underscores should be retained in option names
            (True) or converted to hyphens (False).
        short_names: Dictionary mapping parameter names to short names. If
            not specified, usage of short names depends on `infer_short_names`.
            Set a value to `None` to disable short name usage for a paramter.
        infer_short_names: Whether to infer short names from parameter names.
            See Details on the algorithm used to select the short name. If a
            parameter has a short name specified in `short_names` it overrides
            the inferred short name.
        option_order: Specify an order of option processing that is different
            from the order in the signature of the annotated function.
        types: Dict mapping parameter names to functions that perform type
            conversion. By default, the type of a parameter is inferred from
            its annotation.
        positionals_as_options: Whether to treat positional arguments as required
            options.
        conditionals: Dict mapping paramter names or tuples of parameter names to
            conditional functions or lists of conditinal functions.
        validations: Dict mapping paramter names or tuples of parameter names to
            validation functions or lists of validation functions.
        required: Sequence of required options. If not specified, only paramters
            without default values are required.
        show_defaults: Whether to show defaults in the help text.
        hidden: Sequence of hidden options. These options are not displayed in the
            help text.
        param_help: Dict mapping parameters to help strings. By default, these are
            extracted from the function docstring.
    """
    def __init__(
        self,
        parameters_as_args: bool = False,
        force_create: bool = False,
        **kwargs
    ):
        self._parameters_as_args = parameters_as_args
        self.force_create = force_create
        self._parameters = None
        super().__init__(**kwargs)

    @property
    @abstractmethod
    def _match_type(self) -> Callable:
        """The
        """
        pass

    def _handle_parameter_info(self, param: ParameterInfo) -> bool:
        if param.extra_arguments or param.extra_kwargs:
            raise SignatureError(
                "CompositeType cannot have *args or **kwargs"
            )
        return super()._handle_parameter_info(param)

    def _create_decorator(self) -> DEC:
        self._parameters = self._get_parameter_info()
        if has_composite(self._match_type):
            raise TypeCollisionError(
                f"A composite for type {self._match_type} is already defined."
            )
        register_composite(self._match_type, self)
        return self._decorated

    def create_click_parameters(
        self,
        param: ParameterInfo,
        used_short_names: Set[str],
        add_prefixes: bool,
        hidden: bool,
        default_values: Dict[str, Any],
        help_text: str,
        option_class: Type[click.Option],
        argument_class: Type[click.Argument],
        force_positionals_as_options: bool = False
    ) -> Tuple[Sequence[click.Parameter], Callable[[dict], None]]:
        """
        Create the Click parameters for this composite's signature.

        Args:
            param:
            used_short_names:
            add_prefixes:
            hidden:
            default_values:
            help_text:
            option_class:
            argument_class:
            force_positionals_as_options:

        Returns:
             A tuple (click_parameters, callback), where click_parameters is a
             list of :class:`click.Option` or :class:`click.Argument` instances,
             and the callback is the function to be called with the actual parameter
             values after the command line is parsed. If `self.parameters_as_args` is
             True, a single :class:`click.Tuple` instance.
        """
        if self._parameters_as_args:
            param_decls = ["--{}".format(self._get_long_name(param.name))]

            short_name = self._get_short_name(param.name, used_short_names)
            if short_name:
                used_short_names.add(short_name)
                param_decls.append(f"-{short_name}")

            types = []
            default = []
            for param_name in self._option_order:
                composite_param = self._parameters[param_name]
                types.append(composite_param.click_type)
                default.append(default_values.get(param_name, composite_param.default))

            click_parameters = [
                option_class(
                    param_decls,
                    type=click.Tuple(types),
                    required=not param.optional,
                    default=default,
                    show_default=self._show_defaults,
                    nargs=len(types),
                    hidden=hidden,
                    is_flag=False,
                    multiple=False,
                    help=help_text
                )
            ]
        else:
            prefix = param.name if add_prefixes else None
            click_parameters = [
                self._create_click_parameter(
                    param=self._parameters[opt],
                    used_short_names=used_short_names,
                    option_class=option_class,
                    argument_class=argument_class,
                    long_name_prefix=prefix,
                    hidden=hidden,
                    default_values=default_values,
                    force_positionals_as_options=force_positionals_as_options
                )
                for opt in self._option_order
            ]

        callback = cast(
            Callable[[dict], None],
            functools.partial(self.handle_args, param=param, add_prefixes=add_prefixes)
        )

        return click_parameters, callback

    def handle_args(self, ctx: click.Context, param: ParameterInfo, add_prefixes: bool):
        if self._parameters_as_args:
            kwargs = dict(zip(self._option_order, ctx.params.pop(param.name, ())))
            apply_to_parsed_args(self._conditionals, kwargs, update=True)
            apply_to_parsed_args(self._validations, kwargs, update=False)
        else:
            kwargs = {}
            for composite_param_name in self._parameters.keys():
                if add_prefixes:
                    arg_name = f"{param.name}_{composite_param_name}"
                else:
                    arg_name = composite_param_name
                kwargs[composite_param_name] = ctx.params.pop(arg_name, None)

        if (
            self.force_create or
            not param.optional or
            tuple(filter(None, kwargs.values()))
        ):
            ctx.params[param.name] = self._decorated(**kwargs)
        else:
            ctx.params[param.name] = None


COMPOSITES: Dict[Type, Composite] = {}


def has_composite(type_: Type):
    return type_ in COMPOSITES


def register_composite(type_: Type, composite: Composite):
    # Todo: warn about overwriting existing composite
    COMPOSITES[type_] = composite


def get_composite(type_: Type) -> Optional[Composite]:
    return COMPOSITES.get(type_, None)


# noinspection PyPep8Naming
class composite_type(Composite[type]):
    """

    """
    @property
    def _match_type(self):
        return self._decorated


# noinspection PyPep8Naming
class composite_factory(Composite[Callable]):
    """
    Annotates a function that returns an instance of a composite type.

    Args:
        dest_type: The composite type, i.e. the type that will be recognized in the
            signature of the command function and matched with this factory function.
            If not specified, it is inferred from the return type.
        keep_underscores: Whether underscores should be retained in option names
            (True) or converted to hyphens (False).
        short_names: Dictionary mapping parameter names to short names. If
            not specified, usage of short names depends on `infer_short_names`.
            Set a value to `None` to disable short name usage for a paramter.
        infer_short_names: Whether to infer short names from parameter names.
            See Details on the algorithm used to select the short name. If a
            parameter has a short name specified in `short_names` it overrides
            the inferred short name.
        option_order: Specify an order of option processing that is different
            from the order in the signature of the annotated function.
        types: Dict mapping parameter names to functions that perform type
            conversion. By default, the type of a parameter is inferred from
            its annotation.
        positionals_as_options: Whether to treat positional arguments as required
            options.
        conditionals: Dict mapping paramter names or tuples of parameter names to
            conditional functions or lists of conditinal functions.
        validations: Dict mapping paramter names or tuples of parameter names to
            validation functions or lists of validation functions.
        required: Sequence of required options. If not specified, only paramters
            without default values are required.
        show_defaults: Whether to show defaults in the help text.
        hidden: Sequence of hidden options. These options are not displayed in the
            help text.
        param_help: Dict mapping parameters to help strings. By default, these are
            extracted from the function docstring.
    """
    def __init__(
        self,
        dest_type: Optional[Type] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._target = dest_type

    @property
    def _match_type(self):
        return self._target

    def _create_decorator(self) -> Callable:
        if self._target is None:
            self._target = get_dest_type(self._decorated)
        return super()._create_decorator()


def create_composite(to_wrap: Union[Callable, Type], **kwargs) -> Composite:
    """Creates a :class:`Composite` for use in the `composites` paramter to a
    `command` or `group` decorator.

    Kwargs:
        to_wrap: The function/class to wrap.
        keep_underscores: Whether underscores should be retained in option names
            (True) or converted to hyphens (False).
        short_names: Dictionary mapping parameter names to short names. If
            not specified, usage of short names depends on `infer_short_names`.
            Set a value to `None` to disable short name usage for a paramter.
        infer_short_names: Whether to infer short names from parameter names.
            See Details on the algorithm used to select the short name. If a
            parameter has a short name specified in `short_names` it overrides
            the inferred short name.
        option_order: Specify an order of option processing that is different
            from the order in the signature of the annotated function.
        types: Dict mapping parameter names to functions that perform type
            conversion. By default, the type of a parameter is inferred from
            its annotation.
        positionals_as_options: Whether to treat positional arguments as required
            options.
        conditionals: Dict mapping paramter names or tuples of parameter names to
            conditional functions or lists of conditinal functions.
        validations: Dict mapping paramter names or tuples of parameter names to
            validation functions or lists of validation functions.
        required: Sequence of required options. If not specified, only paramters
            without default values are required.
        show_defaults: Whether to show defaults in the help text.
        hidden: Sequence of hidden options. These options are not displayed in the
            help text.
        param_help: Dict mapping parameters to help strings. By default, these are
            extracted from the function docstring.
    """
    if inspect.isclass(to_wrap):
        comp = composite_type(**kwargs)
    else:
        comp = composite_factory(**kwargs)
    comp(to_wrap)
    return comp
