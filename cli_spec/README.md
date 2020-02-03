# CLI Spec

## Scope

This document specifies a schema for encoding the metadata related to a command-line interface in a syntax-independent manner. The goal is to provide an interchange format by which CLIs may be self-documenting (i.e. a command line tool can generate a metadata file describing all of its sub-commands, arguments, and options), and from which tool wrappers may be generated (e.g. CWL tools and WDL tasks).

## Assumptions

This schema is designed to capture all of the metadata necessary to generate a valid command for a POSIX-compliant command-line tool. While it may be possible to describe non-POSIX CLIs using this schema, there is no guarantee that this schema captures the necessary metadata to support all of the many syntaxes that are in use across operating systems and shells. However, the schema does allow for arbitrary key-value pairs to enable syntax-specific extensions.

## Schema

A CLI Spec describes one or more commands. A valid CLI Spec JSON document has a single required top-level member with key "commands" and an array value. Each element in the array specifies a different command. A CLI Spec may also have a top-level "extensions" member whose value is a list of extension definitions.

### Example

```json
{
  "extensions": [
    {
      "namespace": "com.foo.bar",
      "alias": "gui",
      "url": "https://bar.foo.com/cli-extensions.json"
    }
  ],
  "commands": [
    {
      "name": "say",
      "help": "Say something to the user",
      "aliases": [
        {
          "name": "hi",
          "os": ["vms"]
        }
      ],
      "syntax": "gnu",
      "version": ">=1.0.1",
      "subcommands": [
        {
          "name": "hello",
          "help": "Say hello",
          "options": [
            {
              "name": "age",
              "flag": "a",
              "label": "Age",
              "help": "The user’s age",
              "type": "int",
              "range": [0, 150],
              "properties": {
                "gui:hints": "slider"
              }
            }
          ],
          "operands": [
            {
              "name": "username",
              "label": "Username",
              "help": "The user to greet (defaults to current user)",
              "type": "string",
              "required": false
            }
          ]
        }
      ]
    }
  ]
}
```

### Command

A *command* object describes a command-line interface, including any sub-commands, optional parameters ("options"), and required parameters ("operands").

#### name

The (most common) name of the executable. This is the only required member.

#### help

Optional description of the command. Typically this is copied from the output of calling a command with it’s *--help* (or equivalent) option, including usage examples, but not including any parameter details.

#### aliases

If a command has different names in different environments, or is commonly aliased, those aliases can be listed in the *aliases* array. Each element of the array is an object with a required "name" member whose value is the alias name. An alias may also specify a "os" member whose value is an array of names of operating systems where the alias is used.

#### syntax

By default, commands are assumed to conform to all POSIX requirements (*"syntax": "posix"*). If a command also conforms to the optional (but recommended) POSIX guidelines, the syntax can be set to "posix-strict". If a command supports the GNU extensions (long option names, availability of *--version* and *--help* options), set the syntax to "gnu".

#### version

Indicates a version of the command to which the specification applies. By default, a version of "*" is assumed, meaning that all versions of the command are allowed. The combination of *name* and *version* must be unique within a CLI Spec.

A version may be any valid character string; however, if the tool follows the rules of [semantic versioning](https://semver.org/), then it is also allowed to specify version constraints using the grammar defined by [poetry](https://python-poetry.org/docs/dependency-specification/).

When version constraints are used, then the consumer of the spec may validate the version, and there may be multiple entries for a command as long it is not ambiguious which command applies to any given version of the tool. If there is a *command* with no version (or with version "*"), that command is used as the default version if no other version/range matches.

#### license

The name of the software license under which the command is made available. Optional.

#### url

A URL for the tool, e.g. a GitHub page or documentation site. Optional.

#### return_codes

An object that specifies the meanings of different return codes. The default value is *{"success": [0]}*. The allowed keys are: "success" and "retry", and each value is an integer array of return code values. Any return code that is not in either the "success" or "return" array is interpreted as a failure code. A "retry" code is one that indicates temporary failure and for which the caller may want to retry the command at a later time.

#### options and operands

The user-definable parameters to a command are specified by the *options* and *operands* members. The difference between an option and an operand is that an option consists of a flag (e.g. *-f* in POSIX syntax or *--long-name* in GNU syntax) followed by zero or more option values, whereas an operand is a single value. Operands are also sometimes called "arguments" or "positional arguments". Typically, options are not required (i.e. "optional") while operands are, but this is not always the case. In POSIX syntax, any options must be specified first, followed by any operands; GNU allows for the mixing of options and operands. See the "Parameter" section below for details on the members of these elements.

#### groups

Parameters may be grouped to indicate a relationship between them. By default, a group is only for the purpose of enabling more readable documentation (e.g. when there are many parameters). However, the relationship can also be made explicit by including a *constraints* member. The most common type of constraint is mutual exclusivity.

The *groups* member has an array value, and each element is a group object. See the "Group" section below.

#### subcommands

If a command has multiple sub-commands (e.g. git), the *subcommands* element is a list whose members are subcommand objects. A subcommand can have the same members as *command*; any missing members are inherited from the parent command. Subcommands can be nested to any level of depth.

### Group

#### title

The group title. Optional.

#### help

Help text for the group. Optional.

#### constraints

An object with one or more of the following members:

* min_required: Integer; minimum number of the options in the group that must have a value specified (either on the command line or via their *default* member).

* max_allowed: Integer; maximum number of the options in the group that may have a value specified. For example, *max_allowed: 1* indicates mutual exclusivity of the parameters in the group.

#### options, operands, and groups

These are exactly the same as in the *command* block (see above). Groups may be nested to any level.

### Parameter

#### name

The parameter name. Required. If the syntax is "gnu", and *flag* is not specified, then this must be the long-name of the option (without the "--" prefix).

#### flag

The flag character (sometimes called the option’s "short name"), without the "-" prefix. Required for options unless *name* can be used as the option’s long-name. **Not allowed for operands.**

#### index

A zero-based integer specifying the ordering of operands. Required for operands when the command has more than one operand parameter. **Not allowed for options.** If two operands have the same index, the order in which they will be listed in the command line will be arbitrary.

#### label

A more human-readable label. Optional; defaults to the value of *name*. May be used (for example) when creating a GUI wrapper for a CLI.

#### help

An optional description of the parameter. Typically, this is the same help text as is displayed next to the option when calling the command with the *--help* option (or perhaps from the *man* page).

#### argname

The name to use for the option argument(s) when referring to them in generated documentation. Defaults to the value of *name* converted to CAPITAL_SNAKE_CASE.

#### hidden

The parameter cannot be defined by the user. Boolean; default is *false*. Hidden parameters are *required* and typically must define a *default* (but see "channel" for exceptions).

#### required

Whether the parameter is required. Optional; defaults to *false *for options and *true* for operands and hidden parameters. Cannot be set to *false* for hidden parameters.

#### nargs

The number of arguments allowed in the option value. Optional; defaults to 1 unless *type* is "bool", in which case the option is assumed to be a switch with no (0) arguments. May be a single integer, a range specified as *[min, max]*, or a string with a value of "*" (meaning zero or more) or "+" (meaning one or more). If more than one argument is allowed, the delimiter between arguments may be specified by the *delim* member.

#### delim

The delimiter between arguments in the option value when more than one argument is allowed. Optional; defaults to " " (space). 

#### type

The data type of the option value. The the option allows multiple arguments, all arguments must be the same type. Optional; defaults to "string".

* string: a string of one or more characters; by default, all characters are allowed, but this may be restricted by *regexp* or *choices.*

* integer: by default, any integer in the range allowed by POSIX ([-2147483647, 2147483647]), but this may be restricted by *range* or *choices.*

* float: by default, any floating point number in the range allowed by the operating system, but this may be restricted by *range* or *choices.*

* boolean: no option value is accepted; presence of the flag indicates a *true* value and absence indicates *false*, but this can be inverted using *"default": true.*

* file: a file path. Represented as a string, but with the additional implication that the consumer of the spec may validate that the file exists (if *channel* is "input") or that the path is writable (if *channel* is "output"). When *nargs* is greater than 1, the use of a "glob" expression should be supported to select multiple files that match a given pattern.

* directory: a directory path. Represented as a string, but with the additional implication that the consumer of the spec may validate that the directory exists (if *channel* is "input") or that the directory is creatable/writable (if *channel* is "output"). 

#### default

The default value of the parameter. Optional, except for hidden parameters; but see "channel" for exceptions. If specified, the value must be of the type specified by the *type* member. If multiple option arguments are allowed, *default* must be an array (unless *type* is "file", in which case a string glob expression is allowed). The *null* value is not allowed.

#### range

When the data type is "integer" or "float", *range* can be used to limit the allowed values to a specific range. The range is specified as an array *[min, max[, step]]*, where *min*/*max* is an integer, a float (if *type* is "float"), or the string "*" meaning the smallest/largest allowed value. If *min* and *max* are both integers, then a third integer array element is allowed indicating the step. If *default *is specified, the value must be within *range*.

#### choices

The allowed option values. Optional. If specified, must be an array whose elements must be of the type specified by the *type *member. If *default *is specified, the value must be among those specified by *choices*.

#### regexp

A regular expression that may be used to validate the option arguments. May be specified regardless of the *type*, but typically this is used with "string" values. If *default* is specified, the value must match *regexp*.

#### formats

For options of type "file", specifies an array allowed file formats. A format may be specified using "glob" syntax, meaning that the file name should be checked against the pattern, or it may be an [International Resource Identifier](https://tools.ietf.org/html/rfc3987). Optional; defaults to ["*"]. If *default* is specified, it must match at least one of the formats.

#### channel

The channel of an input or output parameter. Optional; allowed values are "none", "input", "output", and "error". When *type* is "file" or "directory", the default value is "input" for operands and "output" for options; otherwise the default value is "none".

When *hidden* is *true*, the value of *channel* may take on additional implications, depending on the values of *type* and *default*. It is an error for any command to have more than one hidden parameter each with *channel* values of "input", "output", and "error".

* When *channel* is "input"

    * If *default* is defined, the value is passed to the command via standard input

        * If *type* is "file", the contents of the file are sent to standard input (e.g. using an input redirect or by *cat*ing the file and piping it to the command)

        * Otherwise the value itself is sent to standard input (e.g. using *echo*)

    * Otherwise, the system standard input is redirected to the command.

* When *channel* is "output" or "error"

    * If *default *is defined, then *type* must be "file" and the contents of standard output/error are redirected to the file defined by *default*.

    * Otherwise, the contents of standard output/error should be recorded and made available to the caller (e.g. by assigning it to a variable *name* or by writing it to a temporary file or another output device). If *type* is anything other than "string", the caller may first validate (or perform type conversion) on the contents of standard output/error.

#### streamable

Whether the program requires that this input/output file is a regular file, or if it may be a named pipe. Boolean; default is *false*. Only valid for parameters of type "file".

### Tags and Properties

Any object value in the spec may include arbitrary metadata in the form of *tags* and/or *properties*.

Tags and property keys may contain any valid characters *except* that the colon (':') is reserved as a separator between an extension name/alias (the "namespace") and the tag/key; i.e. if a tag/key contains a colon, everything before the first colon is assumed to be the namespace.

#### tags

An array of string tags.

#### properties

A property is an object with arbitrary keys and values. Property keys are subject to the same restrictions as tags; property values may be any valid JSON.

### Extensions

A consumer of a spec may define abitrary extensions for use by spec producers. For example, a program that generates a GUI interface to a command-line tool may add extensions to enable the spec producer to add hints for what types of UI component should be used for each argument.

There is an optional top-level *extensions* member whose value is a list of extension objects. An extension must be defined at the top level before it may be used elsewhere in the spec. The allowed fields for an extension object are below.

Once extensions are defined, then any object-type member of the schema may use the extension name (or alias) as a prefix to any *tag* or *property*.

#### name

The extension name. String; required. Reverse-domain-name notation should be used when possible, to avoid collisions.

#### alias

A short alias for the extension.

#### url

A URL for the extension. If the URL resolves, the consumer of the spec may try to use the contents to validate the usages of the extension. String; optional.

## References

* POSIX (i.e. IEEE Std 1003.1-2017): [https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap12.html](https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap12.html)

* GNU standards for command line interfaces: [https://www.gnu.org/prep/standards/standards.html](https://www.gnu.org/prep/standards/standards.html)

* CTK/Slicer

    * [http://www.commontk.org/index.php/Documentation/Command_Line_Interface](http://www.commontk.org/index.php/Documentation/Command_Line_Interface)

    * [https://www.slicer.org/wiki/Documentation/Nightly/Developers/SlicerExecutionModel#XML_Schema](https://www.slicer.org/wiki/Documentation/Nightly/Developers/SlicerExecutionModel#XML_Schema)

    * [https://www.slicer.org/wiki/Slicer3:Execution_Model_Discussion#Initial_JSON_output_from_sample_registration_package](https://www.slicer.org/wiki/Slicer3:Execution_Model_Discussion#Initial_JSON_output_from_sample_registration_package)

* CWL: [https://www.commonwl.org/v1.1/CommandLineTool.html#CommandLineBinding](https://www.commonwl.org/v1.1/CommandLineTool.html#CommandLineBinding)

* WDL: [https://github.com/openwdl/wdl/blob/master/versions/1.0/SPEC.md](https://github.com/openwdl/wdl/blob/master/versions/1.0/SPEC.md)

