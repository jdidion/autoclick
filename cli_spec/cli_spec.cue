extension :: {
  name: string
  alias?: string
  url?: string
}

if len(spec.extensions) > 0 {
  for ext in spec.extensions {
    "\( ext.name )"?: _
  }
}

base :: {
  tags: [ "string", ... ]
  properties: _
}

alias :: base & {
  name: string
  os?: [ string, ... ]
}

return_codes :: base & {
  success?: [ int, ... ]
  retry?: [ int, ... ]
}

parameter :: base & {
  name: string
  type: *"string" | "integer" | "float" | "boolean" | "file" | "directory"
  label?: string
  help?: string
  argname: string | *"\( strings.ToUpper(name) )"  // TODO: convert to uppercase
  nargs?: int
  delim: string | *" "
  hidden: bool | *true
  required?: bool
  default?: _
  range?: [ number, ... ]
  choices?: [ _, ... ]
  regexp?: string
  formats?: [ "string", ... ]
  channel: *"none" | "input" | "output" | "error"
  streamable: bool | *false
}

option :: parameter & {
  flag?: string
  required: bool | *false
  if type == "file" {
    channel: "none" | "input" | *"output" | "error"
  }
}

operand :: parameter & {
  index?: int
  required: bool | *true
  if type == "file" {
    channel: "none" | *"input" | "output" | "error"
  }
}

constraint :: {
  min_required?: int
  max_allowed?: int
}

group :: base & {
  title?: string
  help?: string
  constraints: [ constraint, ... ]
  options?: [ option, ... ]
  operands?: [ operand, ... ]
  groups?: [ group, ... ]
}

command :: base & {
  name: string
  help?: string
  aliases?: [ alias, ... ]
  url?: string
  return_codes?: return_codes
  options?: [ option, ... ]
  operands?: [ operand, ... ]
  groups?: [ group, ... ]
  subcommands?: [ command, ... ]
  syntax: *"gnu" | "posix" | "posix-strict"
  version?: string
  license?: string
}

spec :: {
  extensions: [ extension, ... ]
  commands: [ command, ... ]
}