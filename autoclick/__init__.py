from abc import ABCMeta, abstractmethod
import collections
import copy
import inspect
import logging
import re
import typing
from typing import (
    Callable, Dict, List, Optional, Sequence, Set, Tuple, Type, Union, cast
)

import click
import docparse


LOG = logging.getLogger("AutoClick")
UNDERSCORES = re.compile("_")
ALPHA_CHARS = set(chr(i) for i in tuple(range(97, 123)) + tuple(range(65, 91)))


class SignatureError(Exception):
    """Raised when the signature of the decorated method is not supported."""
    pass


class ValidationError(Exception):
    """Raised by a validation function when an input violates a constraint."""
    pass


class ParameterCollisionError(Exception):
    """Raised when a composite paramter has the same name as one in the parent
    function.
    """
    pass


class CommandMixin:
    def __init__(
        self,
        *args,
        conditionals: Dict[Sequence[str], Sequence[Callable]],
        validations: Dict[Sequence[str], Sequence[Callable]],
        composites: Dict[str, "CompositeBuilder"],
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.conditionals = conditionals
        self.validations = validations
        self.composites = composites

    def parse_args(self, ctx, args):
        args = cast(click.Command, super()).parse_args(ctx, args)

        def _apply(l, update=False):
            if l:
                for params, fns in l.items():
                    fn_kwargs = dict(
                        (_param, ctx.params.get(_param, None))
                        for _param in params
                    )
                    for fn in fns:
                        result = fn(**fn_kwargs)
                        if result and update:
                            for _param, value in result.items():
                                ctx.params[_param] = value

        _apply(self.conditionals, update=True)
        _apply(self.validations, update=False)

        if self.composites:
            for handler in self.composites.values():
                handler.handle_args(ctx)

        return args


class CompositeParameter:
    """
    Represents a complex type that requires values from multiple parameters. A
    composite parameter is defined by annotating a class using the `composite`
    decorator. The parameters of the class' construtor (exluding `self`) are
    added to the CommandBuilder, prior to parsing, and then they are replaced by
    an instance of the annotated class after parsing.

    Note that composite parameters cannot be nested, i.e. a parameter cannot be a
    list of composite types, and a composite type cannot itself have composite type
    parameters - either of these will cause a `SignatureError` to be raised.

    Args:
        cls_or_fn: The class being decorated.
        command_kwargs: Keyword arguments to CommandBuilder.
    """
    def __init__(self, cls_or_fn: Callable, command_kwargs: dict):
        self._cls_or_fn = cls_or_fn
        self._command_kwargs = command_kwargs

    def __call__(
        self, param_name: str, click_command: CommandMixin,
        exclude_short_names:  Set[str]
    ):
        kwargs = copy.copy(self._command_kwargs)
        if "exclude_short_names" in kwargs:
            exclude_short_names.update(kwargs["exclude_short_names"])
        kwargs["exclude_short_names"] = exclude_short_names
        return CompositeBuilder(self._cls_or_fn, param_name, click_command, **kwargs)


class AutoClickCommand(CommandMixin, click.Command):
    pass


class AutoClickGroup(CommandMixin, click.Group):
    def command(self, arg, **kwargs):
        """A shortcut decorator for declaring and attaching a command to
        the group.  This takes the same arguments as :func:`command` but
        immediately registers the created command with this instance by
        calling into :meth:`add_command`.
        """
        if callable(arg):
            cmd = CommandBuilder(arg, **kwargs).command
            self.add_command(cmd)
            return cmd
        else:
            def decorator(f):
                _cmd = CommandBuilder(f, arg, **kwargs).command
                self.add_command(_cmd)
                return _cmd
            return decorator

    def group(self, arg, **kwargs):
        """A shortcut decorator for declaring and attaching a group to
        the group.  This takes the same arguments as :func:`group` but
        immediately registers the created command with this instance by
        calling into :meth:`add_command`.
        """
        if callable(arg):
            cmd = GroupBuilder(arg, **kwargs).command
            self.add_command(cmd)
            return cmd
        else:
            def decorator(f):
                _cmd = GroupBuilder(f, arg, **kwargs).command
                self.add_command(_cmd)
                return _cmd
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


class WrapperType(click.ParamType):
    def __init__(self, name, fn):
        self.name = name
        self.fn = fn

    def convert(self, value, param, ctx):
        return self.fn(value, param, ctx)


CONVERSIONS: Dict[Type, click.ParamType] = {}
VALIDATIONS: Dict[Type, List[Callable]] = {}
COMPOSITES: Dict[Type, CompositeParameter] = {}


def conversion(arg: Optional[Union[Type, Callable]] = None):
    """Annotates a conversion function.

    If called as a function, takes a single argument, the destination type.
    Otherwise, the destination type is inferred from the function's return
    type.

    Args:
        arg: Function or type
    """
    if inspect.isfunction(arg):
        _dest_type = _get_dest_type(arg)
        CONVERSIONS[_dest_type] = WrapperType(_dest_type.__name__, arg)
        return arg
    else:
        def decorator(f: Callable) -> Callable:
            dest_type = arg
            if dest_type is None:
                dest_type = _get_dest_type(f)
            click_type = WrapperType(dest_type.__name__, f)
            CONVERSIONS[dest_type] = click_type
            return f

        return decorator


def composite_type(*args, **kwargs):
    if args:
        dest_type = args[0]
        COMPOSITES[dest_type] = CompositeParameter(dest_type, kwargs)
        return dest_type
    else:
        def decorator(cls):
            COMPOSITES[cls] = CompositeParameter(cls, kwargs)
            return cls

        return decorator


def composite_factory(arg: Union[Type, Callable], **kwargs):
    if inspect.isfunction(arg):
        _dest_type = _get_dest_type(arg)
        COMPOSITES[_dest_type] = CompositeParameter(_dest_type, kwargs)
        return arg
    else:
        def decorator(f):
            dest_type = arg
            if dest_type is None:
                dest_type = _get_dest_type(f)
            COMPOSITES[dest_type] = CompositeParameter(f, kwargs)
            return f

        return decorator


def validation(
    arg: Union[Type, Callable],
    depends: Optional[Tuple[Callable, ...]] = None
):
    if inspect.isfunction(arg):
        _match_type = _get_dest_type(arg)
        if _match_type not in VALIDATIONS:
            VALIDATIONS[_match_type] = []
        VALIDATIONS[_match_type].append(arg)
        return arg
    else:
        def decorator(f: Callable) -> Callable:
            match_type = arg
            if match_type is None:
                match_type = _get_match_type(f)

            if depends:
                def composite_validation(*args, **kwargs):
                    for dep in depends:
                        dep(*args, **kwargs)
                    f(*args, **kwargs)
                target = composite_validation
            else:
                target = f

            if match_type not in VALIDATIONS:
                VALIDATIONS[match_type] = []
            VALIDATIONS[match_type].append(target)
            return target

        return decorator


def _get_dest_type(f):
    dest_type = inspect.signature(f).return_annotation
    if not dest_type:
        raise ValueError(f"Function {f} must have a non-None return annotation")
    return dest_type


def _get_match_type(f):
    params = inspect.signature(f).parameters
    if len(params) != 1:
        raise ValueError(f"Function {f} must have exactly one parameter")
    return list(params.values())[0].annotation


def command(
    arg: Optional[Union[Callable, str]] = None,
    **kwargs
):
    """Creates a new :class:`Command` and uses the decorated function as
    callback. Uses type arguments of decorated function to automatically
    create:func:`option`s and :func:`argument`s. The name of the command
    defaults to the name of the function.

    Args:
        arg: Either the function being annotated or an optional name. If name is
            not specified, it is taken from the function name.
        kwargs: Additional keyword args to pass to CommandBuilder.
    """
    if callable(arg):
        return CommandBuilder(arg, **kwargs).command
    else:
        return lambda f: CommandBuilder(f, arg, **kwargs).command


def group(
    arg: Optional[Union[Callable, str]] = None,
    **kwargs
):
    """Creates a new :class:`Group` and uses the decorated function as
    callback. Uses type arguments of decorated function to automatically
    create:func:`option`s and :func:`argument`s. The name of the group
    defaults to the name of the function.

    Args:
        arg: Either the function being annotated or an optional name. If name is
            not specified, it is taken from the function name.
        kwargs: Additional keyword args to pass to GroupBuilder.
    """
    if callable(arg):
        return GroupBuilder(arg, **kwargs).command
    else:
        return lambda f: GroupBuilder(f, arg, **kwargs).command


class ParamBuilder(metaclass=ABCMeta):
    def __init__(
        self,
        to_wrap: Callable,
        func_params: Optional[Dict[str, inspect.Parameter]] = None,
        option_order: Optional[Sequence[str]] = None,
        exclude_short_names: Optional[Set[str]] = None,
        required: Optional[Sequence[str]] = None,
        conditionals: Dict[
            Union[str, Tuple[str, ...]], Union[Callable, List[Callable]]] = None,
        validations: Dict[
            Union[str, Tuple[str, ...]], Union[Callable, List[Callable]]] = None,
        **kwargs
    ):
        self._wrapped = to_wrap
        self._wrapped_name = to_wrap.__name__
        if func_params is None:
            func_params = inspect.signature(to_wrap).parameters
        self._func_params = func_params
        self._docs = docparse.parse_docs(to_wrap, docparse.DocStyle.GOOGLE)
        self._has_order = option_order is not None
        self.option_order = option_order or []
        if exclude_short_names is None:
            exclude_short_names = set()
        self._exclude_short_names = exclude_short_names

        self.required = set()
        if required:
            self.required.update(required)

        if conditionals is None:
            self.conditionals = {}
        else:
            self.conditionals = dict(
                (
                    k if isinstance(k, tuple) else (k,),
                    list(v) if v and not isinstance(v, list) else v
                )
                for k, v in conditionals.items()
            )

        if validations is None:
            self.validations = {}
        else:
            self.validations = dict(
                (
                    k if isinstance(k, tuple) else (k,),
                    list(v) if v and not isinstance(v, list) else v
                )
                for k, v in validations.items()
            )

        self.params = {}
        self.handle_params(**kwargs)

    @property
    @abstractmethod
    def command(self) -> CommandMixin:
        pass

    def handle_composite(self, param_name, param_type) -> bool:
        return False

    def _get_long_name(self, param_name: str, keep_underscores: bool) -> str:
        if keep_underscores:
            return param_name
        else:
            return UNDERSCORES.sub("-", param_name)

    def handle_params(
        self,
        short_names: Optional[Dict[str, str]] = None,
        types: Optional[Dict[str, Callable]] = None,
        hidden: Optional[Sequence[str]] = None,
        keep_underscores: bool = True,
        positionals_as_options: bool = False,
        infer_short_names: bool = True,
        show_defaults: bool = False,
        option_class: Type[click.Option] = click.Option,
        argument_class: Type[click.Argument] = click.Argument,
    ):
        if short_names:
            for short_name in short_names.keys():
                if short_name in self._exclude_short_names:
                    raise ParameterCollisionError(
                        f"Short name {short_name} defined for two different parameters"
                    )
                self._exclude_short_names.add(short_name)

        param_help = {}
        if self._docs:
            param_help = dict(
                (p.name, str(p.description))
                for p in self._docs.parameters.values()
            )

        for param_name, param in self._func_params.items():
            if param.kind is inspect.Parameter.VAR_POSITIONAL:
                self.command.allow_extra_arguments = True
                continue
            elif param.kind is inspect.Parameter.VAR_KEYWORD:
                self.command.ignore_unknown_options = False
                continue

            param_long_name = self._get_long_name(param_name, keep_underscores)
            param_type = param.annotation
            param_default = param.default
            has_default = param.default not in {inspect.Parameter.empty, None}
            param_optional = has_default

            if param_type is None:
                if has_default:
                    param_type = type(param_default)
                else:
                    param_type = str

            if not self._has_order:
                self.option_order.append(param_name)

            if self.handle_composite(param_name, param_type):
                continue

            param_nargs = 1
            param_multiple = False

            if types and param_name in types:
                click_type = types[param_name]
                is_flag = (
                    click_type == bool or
                    isinstance(click_type, click.types.BoolParamType)
                )
                if isinstance(click_type, click.Tuple):
                    param_nargs = len(cast(click.Tuple, click_type).types)

            else:
                click_type = None
                match_type = None

                if param_type is inspect.Parameter.empty:
                    if not has_default:
                        LOG.debug(
                            f"No type annotation or default value for paramter "
                            f"{param_name}; using <str>"
                        )
                        param_type = str
                    else:
                        param_type = type(param_default)
                        LOG.debug(
                            f"Inferring type {param_type} from paramter {param_name} "
                            f"default value {param_default}"
                        )
                elif isinstance(param_type, str):
                    if param_type in globals():
                        param_type = globals()[param_type]
                    else:
                        raise SignatureError(
                            f"Could not resolve type {param_type} of paramter "
                            f"{param_name} in function {self._wrapped_name}"
                        )

                # Resolve Union attributes
                # The only time a Union type is allowed is when it has two args and
                # one is None (i.e. an Optional)
                if (
                    hasattr(param_type, "__origin__") and
                    param_type.__origin__ is Union
                ):
                    filtered_args = set(param_type.__args__)
                    if type(None) in filtered_args:
                        filtered_args.remove(type(None))
                    if len(filtered_args) == 1:
                        param_type = filtered_args.pop()
                        param_optional = True
                    else:
                        raise SignatureError(
                            f"Union type not supported for parameter {param_name} "
                            f"in function {self._wrapped_name}"
                        )

                # Resolve NewType
                if (
                    inspect.isfunction(param_type) and
                    hasattr(param_type, "__supertype__")
                ):
                    # It's a NewType
                    match_type = param_type
                    # TODO: this won't work for nested type hierarchies
                    param_type = param_type.__supertype__

                # Resolve Tuples with specified arguments
                if (
                    isinstance(param_type, typing.TupleMeta) and
                    param_type.__args__
                ):
                    param_nargs = len(param_type.__args__)
                    click_type = click.Tuple(param_type.__args__)

                # Unwrap complex types
                while (
                    isinstance(param_type, typing.TypingMeta) and
                    hasattr(param_type, '__extra__')
                ):
                    param_type = param_type.__extra__

                # Now param_type should be primitive or an instantiable type

                # Allow multiple values when type is a non-string collection
                if (
                    param_nargs == 1 and
                    param_type != str and
                    issubclass(param_type, collections.Collection)
                ):
                    param_multiple = True

                is_flag = param_type == bool

                if click_type is None:
                    # Find type conversion
                    if match_type is None:
                        match_type = param_type
                    if match_type in CONVERSIONS:
                        click_type = CONVERSIONS[match_type]
                    else:
                        click_type = param_type

                # Find validations
                if param_type in VALIDATIONS:
                    if param_name not in self.validations:
                        self.validations[(param_name,)] = []
                        self.validations[(param_name,)].extend(VALIDATIONS[match_type])

            is_option = param_optional or positionals_as_options

            if is_option:
                short_name = None
                if short_names and param_name in short_names:
                    short_name = short_names[param_name]
                elif infer_short_names:
                    for char in param_name:
                        if char.isalpha():
                            if char.lower() not in self._exclude_short_names:
                                short_name = char.lower()
                            elif char.upper() not in self._exclude_short_names:
                                short_name = char.upper()
                            else:
                                continue
                            break
                    else:
                        # try to select one randomly
                        remaining = ALPHA_CHARS - self._exclude_short_names
                        if len(remaining) == 0:
                            raise click.BadParameter(
                                f"Could not infer short name for parameter {param_name}"
                            )
                        # TODO: this may not be deterministic
                        short_name = remaining.pop()

                    self._exclude_short_names.add(short_name)

                if not is_flag:
                    long_name_str = f"--{param_long_name}"
                elif param_long_name.startswith("no-"):
                    long_name_str = f"--{param_long_name[3:]}/--{param_long_name}"
                else:
                    long_name_str = f"--{param_long_name}/--no-{param_long_name}"
                param_decls = [long_name_str]
                if short_name:
                    param_decls.append(f"-{short_name}")

                param = option_class(
                    param_decls,
                    type=click_type,
                    required=not param_optional,
                    default=param_default,
                    show_default=show_defaults,
                    nargs=param_nargs,
                    hide_input=hidden and param_name in hidden,
                    is_flag=is_flag,
                    multiple=param_multiple,
                    help=param_help.get(param_name, None)
                )
            else:
                param = argument_class(
                    [param_long_name],
                    type=click_type,
                    default=param_default,
                    nargs=-1 if param_nargs == 1 and param_multiple else param_nargs
                )
                # TODO: where to show parameter help?
                # help = param_help.get(param_name, None)

            self.params[param_name] = param


class CompositeBuilder(ParamBuilder):
    def __init__(
        self,
        to_wrap: Callable,
        param_name: str,
        click_command: CommandMixin,
        **kwargs
    ):
        self.param_name = param_name
        self._click_command = click_command
        func_params = None
        if inspect.isclass(to_wrap):
            func_params = dict(
                inspect.signature(cast(type, to_wrap).__init__).parameters
            )
            func_params.pop("self")
        super().__init__(to_wrap, func_params, **kwargs)

    @property
    def command(self) -> CommandMixin:
        return self._click_command

    def _get_long_name(self, param_name: str, keep_underscores: bool) -> str:
        return super()._get_long_name(
            f"{self.param_name}_{param_name}",
            keep_underscores
        )

    def handle_args(self, ctx):
        """
        Pop the args added by the composite and replace them with the composite type.

        Args:
            ctx:
        """
        kwargs = {}
        for composite_param_name in self.params.keys():
            arg_name = self._get_long_name(composite_param_name, True)
            kwargs[composite_param_name] = ctx.params.pop(arg_name, None)
        ctx.params[self.param_name] = self._wrapped(**kwargs)


class BaseCommandBuilder(ParamBuilder):
    def __init__(
        self,
        to_wrap: Callable,
        command_class: Type[CommandMixin],
        name: Optional[str] = None,
        composite_types: Optional[Dict[str, CompositeParameter]] = None,
        extra_click_kwargs: Optional[dict] = None,
        **kwargs
    ):
        self._name = name
        self._command_class = command_class
        self._click_command = None
        self.composites = {}
        self._composite_types = composite_types or {}
        self._extra_click_kwargs = extra_click_kwargs or {}
        super().__init__(to_wrap, **kwargs)

    @property
    def name(self) -> str:
        return self._name or self._wrapped_name.lower().replace('_', '-')

    @property
    def command(self) -> CommandMixin:
        return self._click_command

    def handle_composite(self, param_name, param_type) -> bool:
        if param_name in self._composite_types:
            composite_param = self._composite_types[param_name]
        elif param_type in COMPOSITES:
            composite_param = COMPOSITES[param_type]
        else:
            return False
        builder = composite_param(
            param_name, self.command, self._exclude_short_names
        )
        self.composites[param_name] = builder
        return True

    def handle_params(self, **kwargs):
        desc = None
        if self._docs and self._docs.description:
            desc = str(self._docs.description)
        self._click_command = self._command_class(
            self.name,
            help=desc,
            callback=self._wrapped,
            conditionals=self.conditionals,
            validations=self.validations,
            composites=self.composites,
            **self._extra_click_kwargs
        )
        super().handle_params(**kwargs)
        params = cast(click.Command, self.command).params
        for param_name in self.option_order:
            if param_name in self.composites:
                builder = self.composites[param_name]
                for composite_param_name in builder.option_order:
                    params.append(builder.params[composite_param_name])
            else:
                params.append(self.params[param_name])


class CommandBuilder(BaseCommandBuilder):
    def __init__(
        self,
        to_wrap: Callable,
        name: Optional[str] = None,
        command_class: Type[AutoClickCommand] = AutoClickCommand,
        **kwargs
    ):
        super().__init__(to_wrap, command_class, name, **kwargs)


class GroupBuilder(BaseCommandBuilder):
    def __init__(
        self,
        to_wrap: Callable,
        name: Optional[str] = None,
        command_class: Type[AutoClickGroup] = AutoClickGroup,
        commands: Optional[Dict[str, click.Command]] = None,
        **kwargs
    ):
        super().__init__(to_wrap, command_class, name, **kwargs)
        self._extra_click_kwargs["commands"] = commands or {}
