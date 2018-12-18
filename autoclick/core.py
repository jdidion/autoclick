from abc import ABCMeta, abstractmethod
import collections
import functools
import inspect
import logging
import re
import typing
from typing import (
    Callable, Dict, Generic, List, Optional, Sequence, Set, Tuple, Type, TypeVar,
    Union, cast
)

import click
import docparse

import pkg_resources
pkg_resources.get_distribution("autoclick")

LOG = logging.getLogger("AutoClick")
UNDERSCORES = re.compile("_")
ALPHA_CHARS = set(chr(i) for i in tuple(range(97, 123)) + tuple(range(65, 91)))
EMPTY = inspect.Signature.empty
EMPTY_OR_NONE = {EMPTY, None}

CONVERSIONS: Dict[Type, click.ParamType] = {}
VALIDATIONS: Dict[Type, List[Callable]] = {}
COMPOSITES: Dict[Type, "Composite"] = {}

COMMON_OPTIONS = """
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

COMMAND_OPTIONS = """
name: The command name. If not specified, it is taken from the name
    of the annotated function.
composite_types: Dict mapping parameter names to :class:`CompositeParameter`
    objects.
add_composite_prefixes: By default, the parameter name is added as a prefix
    when deriving the option names for composite parameters. If set to false,
    each composite type may only be used for at most one parameter, and the
    user must ensure that no composite parameter names conflict with each
    other or with other parameter names in the annotated function.
command_help: Command description. By default, this is extracted from the
    funciton docstring.
option_class: Class to use when creating :class:`click.Option`s.
argument_class: Class to use when creating :class:`click.Argument`s.
extra_click_kwargs: Dict of extra arguments to pass to the
    :class:`click.Command` constructor.
"""


class SignatureError(Exception):
    """Raised when the signature of the decorated method is not supported.
    """


class ValidationError(Exception):
    """Raised by a validation function when an input violates a constraint.
    """


class ParameterCollisionError(Exception):
    """Raised when a composite paramter has the same name as one in the parent
    function.
    """


class TypeCollisionError(Exception):
    """Raised when a decorator is defined for a type for which a decorator of the
    same kind has already been defined.
    """


class ParameterInfo:
    """Extracts and contains the necessary information from a
    :class:`inspect.Parameter`.

    Args:
        name: The parameter name
        param: A :class:`inspect.Parameter`
        click_type: The conversion function, if specified explicitly
        required: Whether this is explicitly specified to be a required parameter
    """
    def __init__(
        self, name: str, param: inspect.Parameter, click_type: Optional[type] = None,
        required: bool = False
    ):
        self.name = name
        self.anno_type = param.annotation
        self.click_type = click_type
        self.match_type = None
        self.optional = not (required or param.default is EMPTY)
        self.default = param.default
        self.nargs = 1
        self.multiple = False
        self.extra_arguments = (param.kind is inspect.Parameter.VAR_POSITIONAL)
        self.extra_kwargs = (param.kind is inspect.Parameter.VAR_KEYWORD)

        if self.anno_type in EMPTY_OR_NONE:
            if not self.optional:
                LOG.debug(
                    f"No type annotation or default value for parameter "
                    f"{name}; using <str>"
                )
                self.anno_type = str
            else:
                self.anno_type = type(self.default)
                LOG.debug(
                    f"Inferring type {self.anno_type} from paramter {name} "
                    f"default value {self.default}"
                )
        elif isinstance(self.anno_type, str):
            if self.anno_type in globals():
                self.anno_type = globals()[self.anno_type]
            else:
                raise SignatureError(
                    f"Could not resolve type {self.anno_type} of paramter {name}"
                )

        # Resolve Union attributes
        # The only time a Union type is allowed is when it has two args and
        # one is None (i.e. an Optional)
        if (
            hasattr(self.anno_type, "__origin__") and
            self.anno_type.__origin__ is Union
        ):
            filtered_args = set(self.anno_type.__args__)
            if type(None) in filtered_args:
                filtered_args.remove(type(None))
            if len(filtered_args) == 1:
                self.anno_type = filtered_args.pop()
                self.optional = True
            else:
                raise SignatureError(
                    f"Union type not supported for parameter {name}"
                )

        # Resolve NewType
        if (
            inspect.isfunction(self.anno_type) and
            hasattr(self.anno_type, "__supertype__")
        ):
            self.match_type = self.anno_type
            # TODO: this won't work for nested type hierarchies
            self.anno_type = self.anno_type.__supertype__

        # Resolve meta-types
        if hasattr(self.anno_type, "__origin__"):
            origin = self.anno_type.__origin__

            # Resolve Tuples with specified arguments
            if (
                self.click_type is None and
                origin == typing.Tuple and
                self.anno_type.__args__
            ):
                self.click_type = click.Tuple(self.anno_type.__args__)

            self.anno_type = origin

        # Unwrap complex types
        while hasattr(self.anno_type, "__extra__"):
            self.anno_type = self.anno_type.__extra__

        # Allow multiple values when type is a non-string collection
        if isinstance(self.click_type, click.Tuple):
            self.nargs = len(cast(click.Tuple, self.click_type).types)

        # Collection types are treated as parameters that can be specified
        # multiple times
        if (
            self.nargs == 1 and
            self.anno_type != str and
            issubclass(self.anno_type, collections.Collection)
        ):
            self.multiple = True

        if self.match_type is None:
            self.match_type = self.anno_type

        if self.click_type is None:
            if self.match_type in CONVERSIONS:
                self.click_type = CONVERSIONS[self.match_type]
            else:
                self.click_type = self.anno_type

        self.is_flag = (
            self.click_type == bool or
            isinstance(self.click_type, click.types.BoolParamType)
        )


D = TypeVar("D")


class BaseDecorator(Generic[D], metaclass=ABCMeta):
    """
    Base class for decorators that create Click parameters.
    """
    def __init__(
        self,
        keep_underscores: bool = True,
        short_names: Optional[Dict[str, str]] = None,
        infer_short_names: bool = True,
        option_order: Optional[Sequence[str]] = None,
        types: Optional[Dict[str, Callable]] = None,
        positionals_as_options: bool = False,
        conditionals: Dict[
            Union[str, Tuple[str, ...]], Union[Callable, List[Callable]]] = None,
        validations: Dict[
            Union[str, Tuple[str, ...]], Union[Callable, List[Callable]]] = None,
        required: Optional[Sequence[str]] = None,
        hidden: Optional[Sequence[str]] = None,
        show_defaults: bool = False,
        param_help: Optional[Dict[str, str]] = None
    ):
        self._keep_underscores = keep_underscores
        self._short_names = short_names or {}
        self._infer_short_names = infer_short_names
        self._option_order = option_order or []
        self._positionals_as_options = positionals_as_options
        self._types = types or {}
        self._required = required or set()
        self._hidden = hidden or set()
        self._show_defaults = show_defaults
        self._param_help = param_help or {}
        self._decorated = None
        self._docs = None

        def _as_many_to_many(d):
            if d is None:
                return {}
            else:
                return dict(
                    (
                        k if isinstance(k, tuple) else (k,),
                        list(v) if v and not isinstance(v, list) else v
                    )
                    for k, v in d.items()
                )

        self._conditionals = _as_many_to_many(conditionals)
        self._validations = _as_many_to_many(validations)

    def __call__(self, decorated: Callable) -> D:
        self._decorated = decorated
        self._docs = docparse.parse_docs(decorated, docparse.DocStyle.GOOGLE)
        return self._create_decorator()

    @abstractmethod
    def _create_decorator(self) -> D:
        pass

    def _get_parameter_info(self) -> Dict[str, ParameterInfo]:
        if inspect.isclass(self._decorated):
            signature_parameters = dict(
                inspect.signature(cast(type, self._decorated).__init__).parameters
            )
            signature_parameters.pop("self")
        else:
            signature_parameters = dict(
                inspect.signature(cast(Callable, self._decorated)).parameters
            )

        parameter_infos = {}

        for name, sig_param in signature_parameters.items():
            param = ParameterInfo(
                name, sig_param, self._types.get(name, None), name in self._required
            )
            if self._handle_parameter_info(param):
                parameter_infos[name] = param

        return parameter_infos

    def _handle_parameter_info(self, param: ParameterInfo) -> bool:
        if param.name not in self._option_order:
            self._option_order.append(param.name)
        if param.match_type in VALIDATIONS:
            if param.name not in self._validations:
                self._validations[(param.name,)] = []
            self._validations[(param.name,)].extend(
                VALIDATIONS[param.match_type]
            )
        return True

    def _create_click_parameter(
        self,
        param: ParameterInfo,
        used_short_names: Set[str],
        option_class: Type[click.Option],
        argument_class: Type[click.Argument],
        long_name_prefix: Optional[str] = None,
        hidden: bool = False,
        force_positionals_as_options: bool = False
    ) -> click.Parameter:
        param_name = param.name
        long_name = self._get_long_name(param_name, long_name_prefix)

        if (
            param.optional or
            force_positionals_as_options or
            self._positionals_as_options
        ):
            if not param.is_flag:
                long_name_decl = f"--{long_name}"
            elif long_name.startswith("no-"):
                long_name_decl = f"--{long_name[3:]}/--{long_name}"
            else:
                long_name_decl = f"--{long_name}/--no-{long_name}"

            param_decls = [long_name_decl]

            short_name = self._get_short_name(param_name, used_short_names)
            if short_name:
                used_short_names.add(short_name)
                param_decls.append(f"-{short_name}")

            return option_class(
                param_decls,
                type=param.click_type,
                required=not param.optional,
                default=param.default,
                show_default=self._show_defaults,
                nargs=param.nargs,
                hidden=hidden or param_name in self._hidden,
                is_flag=param.is_flag,
                multiple=param.multiple,
                help=self._get_help(param_name)
            )
        else:
            # TODO: where to show argument help?
            return argument_class(
                [long_name],
                type=param.click_type,
                default=param.default,
                nargs=-1 if param.nargs == 1 and param.multiple else param.nargs
            )

    def _get_short_name(self, name: str, used_short_names: Set[str]):
        short_name = self._short_names.get(name, None)

        if short_name and short_name in used_short_names:
            raise ParameterCollisionError(
                f"Short name {short_name} defined for two different parameters"
            )
        elif not short_name and self._infer_short_names:
            for char in name:
                if char.isalpha():
                    if char.lower() not in used_short_names:
                        short_name = char.lower()
                    elif char.upper() not in used_short_names:
                        short_name = char.upper()
                    else:
                        continue
                    break
            else:
                # try to select one randomly
                remaining = ALPHA_CHARS - used_short_names
                if len(remaining) == 0:
                    raise click.BadParameter(
                        f"Could not infer short name for parameter {name}"
                    )
                # TODO: this may not be deterministic
                short_name = remaining.pop()

        return short_name

    def _get_long_name(self, name: str, prefix: Optional[str] = None):
        long_name = name
        if prefix:
            long_name = f"{prefix}_{long_name}"
        if not self._keep_underscores:
            long_name = UNDERSCORES.sub("-", long_name)
        return long_name

    def _get_help(self, name: str):
        if name in self._param_help:
            return self._param_help[name]
        elif self._docs and self._docs.parameters and name in self._docs.parameters:
            return str(self._docs.parameters[name].description)


class Composite(BaseDecorator[D], metaclass=ABCMeta):
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
    """
    def __init__(
        self,
        parameters_as_args: bool = False,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._parameters_as_args = parameters_as_args
        self._parameters = None

    @property
    @abstractmethod
    def _match_type(self) -> D:
        pass

    def _handle_parameter_info(self, param: ParameterInfo) -> bool:
        if param.extra_arguments or param.extra_kwargs:
            raise SignatureError(
                "CompositeType cannot have *args or **kwargs"
            )
        return super()._handle_parameter_info(param)

    def _create_decorator(self) -> D:
        self._parameters = self._get_parameter_info()
        if self._match_type in COMPOSITES:
            raise TypeCollisionError(
                f"A composite for type {self._match_type} is already defined."
            )
        COMPOSITES[self._match_type] = self
        return self._decorated

    def create_click_parameters(
        self,
        param: ParameterInfo,
        used_short_names: Set[str],
        add_prefixes: bool,
        hidden: bool,
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
                param = self._parameters[param_name]
                types.append(param.click_type)
                default.append(param.default)

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
            values = dict(zip(self._option_order, ctx.params.pop(param.name, ())))
            _apply_to_parsed_args(self._conditionals, values, update=True)
            _apply_to_parsed_args(self._validations, values, update=False)
            ctx.params[param.name] = self._decorated(**values)
        else:
            prefix = param.name if add_prefixes else None
            kwargs = {}
            for composite_param_name in self._parameters.keys():
                arg_name = self._get_long_name(composite_param_name, prefix)
                kwargs[composite_param_name] = ctx.params.pop(arg_name, None)
                ctx.params[param.name] = self._decorated(**kwargs)


# noinspection PyPep8Naming
class composite_type(Composite[type]):
    @property
    def _match_type(self) -> D:
        return self._decorated


composite_type.__doc__ = f"""
Annotates a class that will be regitered as a composite type.

Args:
    {COMMON_OPTIONS}
"""


# noinspection PyPep8Naming
class composite_factory(Composite[Callable]):
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
            self._target = _get_dest_type(self._decorated)
        return super()._create_decorator()


composite_factory.__doc__ = f"""
Annotates a function that returns an instance of a composite type.

Args:
    dest_type: The composite type, i.e. the type that will be recognized in the
        signature of the command function and matched with this factory function.
        If not specified, it is inferred from the return type.
    {COMMON_OPTIONS}
"""


def create_composite(to_wrap: Union[Callable, Type], **kwargs) -> Composite:
    """Creates a :class:`Composite` for use in the `composites` paramter to a
    `command` or `group` decorator.
    """
    if inspect.isclass(to_wrap):
        comp = composite_type(**kwargs)
    else:
        comp = composite_factory(**kwargs)
    comp(to_wrap)
    return comp


create_composite.__doc__ = f"""
Create a composite for a function or class.

Args:
    to_wrap: The function/class to wrap.
    {COMMON_OPTIONS}
"""


class CommandMixin:
    """
    Mixin class that overrides :func:`parse_args` to apply validations and conditionals,
    and to resolve composite types.
    """
    def __init__(
        self,
        *args,
        conditionals: Dict[Sequence[str], Sequence[Callable]],
        validations: Dict[Sequence[str], Sequence[Callable]],
        composite_callbacks: Sequence[Callable[[dict], None]],
        used_short_names: Set[str],
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self._conditionals = conditionals or {}
        self._validations = validations or {}
        self._composite_callbacks = composite_callbacks or {}
        self._used_short_names = used_short_names or {}

    def parse_args(self, ctx, args):
        args = cast(click.Command, super()).parse_args(ctx, args)
        _apply_to_parsed_args(self._conditionals, ctx.params, update=True)
        _apply_to_parsed_args(self._validations, ctx.params, update=False)
        for callback in self._composite_callbacks:
            callback(ctx)
        return args


class AutoClickCommand(CommandMixin, click.Command):
    """
    Subclass of :class:`click.Command` that also inherits :class:`CommandMixin`.
    """
    pass


class AutoClickGroup(CommandMixin, click.Group):
    """
    Subclass of :class:`click.Group` that also inherits :class:`CommandMixin`.
    """
    def command(self, name: str = None, **kwargs):
        """A shortcut decorator for declaring and attaching a command to
        the group.  This takes the same arguments as :func:`command` but
        immediately registers the created command with this instance by
        calling into :meth:`add_command`.
        """
        def decorator(f):
            cmd = command(
                name=name,
                used_short_names=self._used_short_names,
                **kwargs
            )
            click_command = cmd(f)
            self.add_command(click_command)
            return click_command
        return decorator

    def group(self, name: str = None, **kwargs):
        """A shortcut decorator for declaring and attaching a group to
        the group.  This takes the same arguments as :func:`group` but
        immediately registers the created command with this instance by
        calling into :meth:`add_command`.
        """
        def decorator(f):
            grp = group(
                name=name,
                used_short_names=self._used_short_names,
                **kwargs
            )
            click_group = grp(f)
            self.add_command(click_group)
            return click_group
        return decorator

    def parse_args(self, ctx, args):
        if not args and self.no_args_is_help and not ctx.resilient_parsing:
            click.echo(ctx.get_help(), color=ctx.color)
            ctx.exit()

        rest = CommandMixin.parse_args(self, ctx, args)
        if self.chain:
            ctx.protected_args = rest
            ctx.args = []
        elif rest:
            ctx.protected_args, ctx.args = rest[:1], rest[1:]

        return ctx.args


class BaseCommandDecorator(BaseDecorator[D], metaclass=ABCMeta):
    """
    Base class for decorators that wrap command functions.
    """
    def __init__(
        self,
        name: Optional[str] = None,
        composite_types: Optional[Dict[str, Composite]] = None,
        add_composite_prefixes: bool = False,
        command_help: Optional[str] = None,
        option_class: Type[click.Option] = click.Option,
        argument_class: Type[click.Argument] = click.Argument,
        extra_click_kwargs: Optional[dict] = None,
        used_short_names: Optional[Set[str]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._name = name
        self._composite_types = composite_types or {}
        self._add_composite_prefixes = add_composite_prefixes
        self._command_help = command_help
        self._option_class = option_class
        self._argument_class = argument_class
        self._extra_click_kwargs = extra_click_kwargs or {}
        self._used_short_names = set()
        if used_short_names:
            self._used_short_names.update(used_short_names)
        self._allow_extra_arguments = False
        self._allow_extra_kwargs = False

    @property
    def name(self) -> str:
        """The command name."""
        return self._name or self._decorated.__name__.lower().replace('_', '-')

    def _handle_parameter_info(self, param: ParameterInfo) -> bool:
        if param.extra_arguments:
            self._allow_extra_arguments = True
            return False
        elif param.extra_kwargs:
            self._allow_extra_kwargs = True
            return False
        return super()._handle_parameter_info(param)

    def _create_decorator(self) -> D:
        parameter_infos = self._get_parameter_info()
        command_params = []
        composite_callbacks = []

        for param_name in self._option_order:
            param = parameter_infos[param_name]

            composite = None
            if param_name in self._composite_types:
                composite = self._composite_types[param_name]
            elif param.match_type in COMPOSITES:
                composite = COMPOSITES[param.match_type]

            if composite:
                click_parameters, callback = composite.create_click_parameters(
                    param=param,
                    used_short_names=self._used_short_names,
                    add_prefixes=self._add_composite_prefixes,
                    hidden=param.name in self._hidden,
                    option_class=self._option_class,
                    argument_class=self._argument_class,
                    help_text=self._get_help(param.name),
                    force_positionals_as_options=self._positionals_as_options
                )
                command_params.extend(click_parameters)
                composite_callbacks.append(callback)
            else:
                command_params.append(self._create_click_parameter(
                    param=param,
                    used_short_names=self._used_short_names,
                    option_class=self._option_class,
                    argument_class=self._argument_class
                ))

        desc = None
        if self._docs and self._docs.description:
            desc = str(self._docs.description)

        click_command = self._create_click_command(
            name=self.name,
            callback=self._decorated,
            help=desc,
            conditionals=self._conditionals,
            validations=self._validations,
            composite_callbacks=composite_callbacks,
            **self._extra_click_kwargs
        )
        click_command.params = command_params
        if self._allow_extra_arguments:
            click_command.allow_extra_arguments = True
        if self._allow_extra_kwargs:
            click_command.ignore_unknown_options = False

        return click_command

    @abstractmethod
    def _create_click_command(self, **kwargs) -> D:
        pass


# noinspection PyPep8Naming
class command(BaseCommandDecorator[click.Command]):
    def __init__(
        self,
        name: str = None,
        command_class: Type[CommandMixin] = AutoClickCommand,
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self._command_class = command_class

    def _create_click_command(self, **kwargs) -> click.Command:
        return cast(click.Command, self._command_class(
            used_short_names=self._used_short_names,
            **kwargs
        ))


command.__doc__ = f"""
Decorator that creates a click.Command based on type annotations of the
annotated function.

Args:
    command_class: Class to use when creating the :class:`click.Command`. This must
        inherit from :class:`CommandMixin`.
    {COMMAND_OPTIONS}
    {COMMON_OPTIONS}
"""


# noinspection PyPep8Naming
class group(BaseCommandDecorator[click.Group]):
    def __init__(
        self,
        name: str = None,
        group_class: Type[CommandMixin] = AutoClickGroup,
        commands: Optional[Dict[str, click.Command]] = None,
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self._group_class = group_class
        self._extra_click_kwargs["commands"] = commands or {}

    def _create_click_command(self, **kwargs) -> click.Group:
        return cast(click.Group, self._group_class(
            used_short_names=self._used_short_names,
            **kwargs
        ))


group.__doc__ = f"""
Decorator that creates a :class:`click.Group` based on type annotations of the
annotated function.

Args:
    group_class: Class to use when creating the :class:`click.Group`. This must
        inherit from :class:`CommandMixin`.
    {COMMAND_OPTIONS}
    {COMMON_OPTIONS}
"""


class ParamTypeAdapter(click.ParamType):
    """
    Adapts a conversion function to a :class:`click.ParamType`.
    """
    def __init__(self, name, fn):
        self.name = name
        self.fn = fn

    def convert(self, value, param, ctx):
        return self.fn(value, param, ctx)


def conversion(
    dest_type: Optional[Type] = None,
    depends: Optional[Tuple[Callable, ...]] = None
):
    """Annotates a conversion function.

    Args:
        dest_type: Destination type for this conversion. If None, it is
            inferred from the return type of the annotated function.
        depends: Functions on which this conversion depends. They are called in
            order, with the output from each function being passed as the input
            to the next. The type of the parameter to the conversion function
            must be the return type of the last dependency.

    Returns:
        A decorator function.
    """
    def decorator(f: Callable) -> Callable:
        _dest_type = dest_type
        if _dest_type is None:
            _dest_type = _get_dest_type(f)

        if depends:
            def composite_conversion(value):
                for dep in depends:
                    value = dep(value)
                return f(value)

            target = composite_conversion
        else:
            target = f

        click_type = ParamTypeAdapter(_dest_type.__name__, target)
        CONVERSIONS[_dest_type] = click_type
        return target

    return decorator


def validation(
    match_type: Optional[Type] = None,
    depends: Optional[Tuple[Callable, ...]] = None
):
    """Annotates a single-parameter validation.

    Args:
        match_type: The type that will match this validation. If None, is inferred
            from the type of the first parameter in the signature of the annotated
            function.
        depends: Other validations that are pre-requisite for this one.

    Returns:
        A decorator function.
    """
    def decorator(f: Callable) -> Callable:
        _match_type = match_type
        if _match_type is None:
            _match_type = _get_match_type(f)

        if depends:
            def composite_validation(*args, **kwargs):
                for dep in depends:
                    dep(*args, **kwargs)
                f(*args, **kwargs)
            target = composite_validation
        else:
            target = f

        if match_type not in VALIDATIONS:
            VALIDATIONS[_match_type] = []
        VALIDATIONS[_match_type].append(target)
        return target

    return decorator


def _apply_to_parsed_args(d, values: dict, update=False):
    for params, fns in d.items():
        fn_kwargs = dict(
            (param, values.get(param, None))
            for param in params
        )
        for fn in fns:
            result = fn(**fn_kwargs)
            if result and update:
                for param, value in result.items():
                    values[param] = value


def _get_match_type(f):
    params = inspect.signature(f).parameters
    if len(params) == 0:
        raise ValueError(f"Function {f} must have at least one parameter")
    params = list(params.values())
    if len(params) > 1:
        for p in params[1:]:
            if p.default == EMPTY:
                raise ValueError(
                    f"All but the first parameter must have default values in "
                    f"the signature of function {f}."
                )
    return params[0].annotation


def _get_dest_type(f):
    dest_type = inspect.signature(f).return_annotation
    if dest_type in EMPTY_OR_NONE:
        raise ValueError(f"Function {f} must have a non-None return annotation")
    return dest_type
