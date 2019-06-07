from abc import ABCMeta, abstractmethod
from typing import Any, Callable, Dict, Optional, Sequence, Set, Type, Union, cast

import click

from autoclick.composites import Composite, get_composite
from autoclick.core import DEC, BaseDecorator, ParameterInfo, apply_to_parsed_args
from autoclick.utils import EMPTY, LOG, get_global


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
        click.Command.parse_args(cast(click.Command, self), ctx, args)
        apply_to_parsed_args(self._conditionals, ctx.params, update=True)
        apply_to_parsed_args(self._validations, ctx.params, update=False)
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

    Args:
        match_prefix: Whether to look for a command that starts with the specified
            name if the command name cannot be matched exactly.
    """

    def __init__(self, *args, match_prefix: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._match_prefix = match_prefix

    def command(
        self,
        name: Optional[str] = None,
        decorated: Optional[Callable] = None,
        **kwargs
    ):
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

        if decorated:
            return decorator(decorated)
        else:
            return decorator

    def group(
        self,
        name: Optional[str] = None,
        decorated: Optional[Callable] = None,
        **kwargs
    ):
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

        if decorated:
            return decorator(decorated)
        else:
            return decorator

    def get_command(self, ctx, cmd_name):
        cmd = click.Group.get_command(self, ctx, cmd_name)
        if cmd is not None:
            return cmd

        matches = [x for x in self.list_commands(ctx) if x.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        else:
            ctx.fail(f"Too many matches: {', '.join(sorted(matches))}")

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


class DefaultAutoClickGroup(AutoClickGroup):
    """

    """
    def __init__(
        self,
        *args,
        invoke_without_command: bool = None,
        no_args_is_help: bool = None,
        default: Optional[str] = None,
        default_if_no_args: bool = False,
        **kwargs
    ):
        if default_if_no_args:
            if invoke_without_command is False or no_args_is_help is True:
                raise ValueError(
                    "One one of 'no_args_is_help', 'default_if_no_args' may be True."
                )
            invoke_without_command = True
            no_args_is_help = False

        super().__init__(
            *args, invoke_without_command=invoke_without_command,
            no_args_is_help=no_args_is_help, **kwargs
        )
        self._default_cmd_name = default
        self._default_if_no_args = default_if_no_args

    def set_default_command(self, cmd):
        """Sets a command function as the default command.
        """
        self._default_cmd_name = cmd.name
        self.add_command(cmd)

    def parse_args(self, ctx, args):
        if not args and self._default_if_no_args:
            args.insert(0, self._default_cmd_name)
        return super().parse_args(ctx, args)

    def get_command(self, ctx, cmd_name):
        if cmd_name not in self.commands:
            # No command name matched.
            ctx.arg0 = cmd_name
            cmd_name = self._default_cmd_name
        return super().get_command(ctx, cmd_name)

    def resolve_command(self, ctx, args):
        base = super()
        cmd_name, cmd, args = base.resolve_command(ctx, args)
        if hasattr(ctx, 'arg0'):
            args.insert(0, ctx.arg0)
        return cmd_name, cmd, args

    def format_commands(self, ctx, formatter):
        formatter = DefaultCommandFormatter(self, formatter, mark='*')
        return super().format_commands(ctx, formatter)


class DefaultCommandFormatter:
    """Wraps a formatter to mark a default command.
    """

    def __init__(self, group_, formatter, mark='*'):
        self._group = group_
        self._formatter = formatter
        self._mark = mark

    def __getattr__(self, attr):
        return getattr(self.formatter, attr)

    def write_dl(self, rows, *args, **kwargs):
        rows_ = []
        for cmd_name, help_str in rows:
            if cmd_name == self._group.default_cmd_name:
                rows_.insert(0, (cmd_name + self._mark, help_str))
            else:
                rows_.append((cmd_name, help))
        return self._formatter.write_dl(rows_, *args, **kwargs)


class BaseCommandDecorator(BaseDecorator[DEC], metaclass=ABCMeta):
    """
    Base class for decorators that wrap command functions.
    """
    def __init__(
        self,
        name: Optional[str] = None,
        composite_types: Optional[Dict[str, Composite]] = None,
        add_composite_prefixes: bool = True,
        command_help: Optional[str] = None,
        option_class: Type[click.Option] = click.Option,
        argument_class: Type[click.Argument] = click.Argument,
        extra_click_kwargs: Optional[dict] = None,
        used_short_names: Optional[Set[str]] = None,
        default_values: Optional[Dict[str, Any]] = None,
        version: Optional[Union[str, bool]] = None,
        pass_context: Optional[bool] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._name = name
        self._composite_types: Dict[str, Composite] = composite_types or {}
        self._add_composite_prefixes = get_global(
            "add_composite_prefixes", add_composite_prefixes
        )
        self._command_help = command_help
        self._option_class = option_class
        self._argument_class = argument_class
        self._extra_click_kwargs = extra_click_kwargs or {}
        self._used_short_names = set()
        if used_short_names:
            self._used_short_names.update(used_short_names)
        self._default_values = default_values or {}
        self._pass_context = get_global("pass_context", pass_context)
        self._allow_extra_arguments = False
        self._allow_extra_kwargs = False
        self._add_version_option = version

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

    def _create_decorator(self) -> DEC:
        parameter_infos = self._get_parameter_info()
        command_params = []
        composite_callbacks = []

        # TODO
        # if self._add_version_option:
        #     command_params.append()

        if self._pass_context:
            ctx_param = list(parameter_infos.keys())[0]
            if parameter_infos[ctx_param].anno_type in {click.Context, EMPTY, None}:
                parameter_infos.pop(ctx_param)
                if ctx_param in self._option_order:
                    self._option_order.remove(ctx_param)
            else:
                LOG.warning(
                    "pass_context set to True, but first parameter of function %s "
                    "does not appear to be of type click.Context",
                    self.name
                )

        for param_name in self._option_order:
            param = parameter_infos[param_name]

            composite: Composite = (
                self._composite_types[param_name]
                if param_name in self._composite_types
                else get_composite(param.match_type)
            )

            if composite:
                click_parameters, callback = composite.create_click_parameters(
                    param=param,
                    used_short_names=self._used_short_names,
                    default_values=self._default_values,
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
                    default_values=self._default_values,
                    option_class=self._option_class,
                    argument_class=self._argument_class
                ))

        desc = None
        if self._docs and self._docs.description:
            desc = str(self._docs.description)

        callback = self._decorated
        if self._pass_context:
            callback = click.pass_context(callback)

        # TODO: pass `no_args_is_help=True` unless there are no required parameters
        click_command = self._create_click_command(
            name=self.name,
            callback=callback,
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
    def _create_click_command(self, **kwargs) -> DEC:
        pass


# noinspection PyPep8Naming
class command(BaseCommandDecorator[click.Command]):
    """
    Decorator that creates a click.Command based on type annotations of the
    annotated function.

    Args:
        command_class: Class to use when creating the :class:`click.Command`. This must
            inherit from :class:`CommandMixin`.
        name: The command name. If not specified, it is taken from the name
            of the annotated function.
        composite_types: Dict mapping parameter names to :class:`CompositeParameter`
            objects.
        add_composite_prefixes: By default, the parameter name is added as a prefix
            when deriving the option names for composite parameters. If set to false,
            each composite type may only be used for at most one parameter, and the
            user must ensure that no composite parameter names conflict with each
            other or with other parameter names in the annotated function.
        default_values: Specify default values for parameters. The primary usage is
            to specify default values for hidden parameters of composite types.
            Otherwise, it is better to specify default values in the signature of the
            command function.
        command_help: Command description. By default, this is extracted from the
            funciton docstring.
        option_class: Class to use when creating :class:`click.Option`s.
        argument_class: Class to use when creating :class:`click.Argument`s.
        extra_click_kwargs: Dict of extra arguments to pass to the
            :class:`click.Command` constructor.
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
        pass_context: Whether to pass in the click.Context as the first argument
            to the function.
    """
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


# noinspection PyPep8Naming
class group(BaseCommandDecorator[click.Group]):
    """
    Decorator that creates a :class:`click.Group` based on type annotations of the
    annotated function.

    Args:
        group_class: Class to use when creating the :class:`click.Group`. This must
            inherit from :class:`CommandMixin`.
        name: The command name. If not specified, it is taken from the name
            of the annotated function.
        composite_types: Dict mapping parameter names to :class:`CompositeParameter`
            objects.
        add_composite_prefixes: By default, the parameter name is added as a prefix
            when deriving the option names for composite parameters. If set to false,
            each composite type may only be used for at most one parameter, and the
            user must ensure that no composite parameter names conflict with each
            other or with other parameter names in the annotated function.
        default_values: Specify default values for parameters. The primary usage is
            to specify default values for hidden parameters of composite types.
            Otherwise, it is better to specify default values in the signature of the
            command function.
        command_help: Command description. By default, this is extracted from the
            funciton docstring.
        option_class: Class to use when creating :class:`click.Option`s.
        argument_class: Class to use when creating :class:`click.Argument`s.
        extra_click_kwargs: Dict of extra arguments to pass to the
            :class:`click.Command` constructor.
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
        pass_context: Whether to pass in the click.Context as the first argument
            to the function.
    """
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
