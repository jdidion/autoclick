from abc import ABCMeta, abstractmethod
import inspect
import re
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast
)

import click
import docparse

from autoclick.types import get_conversion
from autoclick.types.library import OptionalTuple
from autoclick.utils import EMPTY, EMPTY_OR_NONE, LOG, get_global
from autoclick.validations import get_validations


UNDERSCORES = re.compile("_")
ALPHA_CHARS = set(chr(i) for i in tuple(range(97, 123)) + tuple(range(65, 91)))
DEC = TypeVar("DEC")


class ParameterCollisionError(Exception):
    """Raised when a composite paramter has the same name as one in the parent
    function.
    """


class SignatureError(Exception):
    """Raised when the signature of the decorated method is not supported.
    """


class ParameterInfo:
    """Extracts and contains the necessary information from a
    :class:`inspect.Parameter`.

    Args:
        name: The parameter name.
        param: A :class:`inspect.Parameter`.
        click_type: The conversion function, if specified explicitly.
        required: Whether this is explicitly specified to be a required parameter.
    """

    def __init__(
        self, name: str, param: inspect.Parameter, click_type: Optional[type] = None,
        required: bool = False
    ):
        self.name = name
        self.anno_type = param.annotation
        self.click_type = click_type
        self.optional = not (required or param.default is EMPTY)
        self.default = None if param.default is EMPTY else param.default
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
                self.default = None
            else:
                raise SignatureError(
                    f"Union type not supported for parameter {name}"
                )

        self.match_type = self.anno_type

        def resolve_new_type(t):
            return t.__supertype__ if (
                inspect.isfunction(t) and hasattr(t, "__supertype__")
            ) else t

        self.anno_type = resolve_new_type(self.anno_type)

        # Resolve meta-types
        if hasattr(self.anno_type, "__origin__"):
            origin = self.anno_type.__origin__

            if hasattr(self.anno_type, "__args__"):
                if origin == Tuple:
                    # Resolve Tuples with specified arguments
                    if self.click_type is None:
                        self.click_type = click.Tuple([
                            resolve_new_type(a) for a in self.anno_type.__args__
                        ])
                elif len(self.anno_type.__args__) == 1:
                    self.match_type = self.anno_type.__args__[0]

            self.anno_type = origin

        # Unwrap complex types
        while hasattr(self.anno_type, "__extra__"):
            self.anno_type = self.anno_type.__extra__

        # Set nargs when type is a click.Tuple
        if isinstance(self.click_type, click.Tuple):
            self.nargs = len(cast(click.Tuple, self.click_type).types)
            if self.default is None:
                # Substitute a subclass of click.Tuple that will convert a sequence
                # of all None's to a None
                self.default = (None,) * self.nargs
                self.click_type = OptionalTuple(self.click_type.types)
            elif not isinstance(self.default, Sequence):
                raise SignatureError(
                    f"Default value of paramter {self.name} of type Tuple must be a "
                    f"sequence."
                )
            else:
                arrity = len(tuple(self.default))
                if arrity != self.nargs:
                    raise SignatureError(
                        f"Default value of paramter {self.name} of type Tuple must be "
                        f"a collection having the same arrity; {arrity} != {self.nargs}"
                    )

        # Collection types are treated as parameters that can be specified
        # multiple times
        if (
            self.nargs == 1 and
            self.anno_type != str and
            issubclass(self.anno_type, Collection)
        ):
            self.multiple = True

        if self.match_type is None:
            self.match_type = self.anno_type

        if self.click_type is None:
            self.click_type = get_conversion(self.match_type, self.anno_type)

        self.is_flag = (
            self.click_type == bool or
            isinstance(self.click_type, click.types.BoolParamType)
        )


class BaseDecorator(Generic[DEC], metaclass=ABCMeta):
    """
    Base class for decorators of groups, commands, and composites.
    """

    def __init__(
        self,
        keep_underscores: bool = False,
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
        param_help: Optional[Dict[str, str]] = None,
        decorated: Optional[Callable] = None
    ):
        self._keep_underscores = get_global("keep_underscores", keep_underscores)
        self._short_names = short_names or {}
        self._infer_short_names = get_global("infer_short_names", infer_short_names)
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
                        [v] if v and not isinstance(v, list) else v
                    )
                    for k, v in d.items()
                )

        self._conditionals = _as_many_to_many(conditionals)
        self._validations = _as_many_to_many(validations)

        if decorated:
            self(decorated=decorated)

    def __call__(self, decorated: Callable) -> DEC:
        self._decorated = decorated
        # TODO: support other docstring styles
        self._docs = docparse.parse_docs(decorated, docparse.DocStyle.GOOGLE)
        return self._create_decorator()

    @abstractmethod
    def _create_decorator(self) -> DEC:
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
        """
        Register parameter. Subclasses can override this method to filter out
        some paramters.

        Args:
            param: A :class:`ParameterInfo`.

        Returns:
            True if this parameter should be added to the parser.
        """

        if param.name not in self._option_order:
            self._option_order.append(param.name)

        vals = get_validations(param.match_type)
        if vals:
            if param.name not in self._validations:
                self._validations[(param.name,)] = []
            self._validations[(param.name,)].extend(vals)
        return True

    def _create_click_parameter(
        self,
        param: ParameterInfo,
        used_short_names: Set[str],
        default_values: Dict[str, Any],
        option_class: Type[click.Option],
        argument_class: Type[click.Argument],
        long_name_prefix: Optional[str] = None,
        hidden: bool = False,
        force_positionals_as_options: bool = False
    ) -> click.Parameter:
        """Create a click.Parameter instance (either Option or Argument).

        Args:
            param: A :class:`ParameterInfo`.
            used_short_names: A set of short names that have been used by other
                parameters and thus should not be re-used.
            default_values:
            option_class: Class to instantiate for option parameters.
            argument_class: Class to instantiate for argument parameters.
            long_name_prefix: Prefix to add to long option names.
            hidden: Whether to not show the parameter in help text.
            force_positionals_as_options: Whether to force positional arguments to be
                treated as options.

        Returns:
            A :class:`click.Parameter`.
        """

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
                type=None if param.is_flag else param.click_type,
                required=not param.optional,
                default=default_values.get(param_name, param.default),
                show_default=self._show_defaults,
                nargs=param.nargs,
                hidden=hidden or param_name in self._hidden,
                multiple=param.multiple,
                help=self._get_help(param_name)
            )
        else:
            # TODO: where to show argument help?
            return argument_class(
                [long_name],
                type=param.click_type,
                default=default_values.get(param_name, param.default),
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


def apply_to_parsed_args(d, values: dict, update=False):
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
