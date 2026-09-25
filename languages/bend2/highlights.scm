; Names and types
(identifier) @variable
((identifier) @variable @variable.special
  (#eq? @variable.special "_"))

((identifier) @type
  (#match? @type "^[A-Z][A-Za-z0-9_]*$"))

((identifier) @type.builtin
  (#any-of? @type.builtin
    "Empty" "Unit" "Bool" "Cmp" "Either" "Sigma" "Pair" "Nat" "U32" "F32" "Char" "String"
    "Maybe" "Result" "List" "Word" "Array" "Map" "Set" "Equal" "IO" "Chan" "File" "Socket"
    "Listener" "Window" "Audio" "Image" "Event" "App"))

(scoped_identifier
  (identifier) @property
  .
  (identifier))

; Declarations
(function_definition
  name: [
    (identifier) @function
    (scoped_identifier
      (identifier) @function .)
  ])

(law_declaration
  name: [
    (identifier) @function
    (scoped_identifier
      (identifier) @function .)
  ])

(type_declaration
  name: [
    (identifier) @type
    (scoped_identifier
      (identifier) @type .)
  ])

(constructor_declaration
  name: [
    (identifier) @constructor
    (scoped_identifier
      (identifier) @constructor .)
  ])

(field_declaration
  name: (identifier) @property)

(parameter
  name: (identifier) @variable.parameter)

(for_clause
  name: (identifier) @variable.parameter)

(exists_clause
  name: (identifier) @variable.parameter)

(lambda
  parameter: (identifier) @variable.parameter)

(dependent_function_type
  name: (identifier) @variable.parameter)

(exists_type
  name: (identifier) @variable.parameter)

(decorator) @attribute

; Imports and types
(import_declaration
  path: (import_path) @string.special)

(import_declaration
  alias: (identifier) @variable
)

(type_application
  name: [
    (identifier) @type
    (scoped_identifier
      (identifier) @type .)
  ])

(kind) @type.builtin

(do_block
  monad: [
    (identifier) @type
    (scoped_identifier
      (identifier) @type .)
  ])

(quantity) @constant.builtin

; Constructors and booleans
(constructor
  name: [
    (identifier) @constructor
    (scoped_identifier
      (identifier) @constructor .)
  ])

(constructor_pattern
  name: [
    (identifier) @constructor
    (scoped_identifier
      (identifier) @constructor .)
  ])

(match_arm
  name: [
    (identifier) @constructor
    (scoped_identifier
      (identifier) @constructor .)
  ])

((constructor
  name: (identifier) @boolean)
  (#any-of? @boolean "True" "False"))

((constructor_pattern
  name: (identifier) @boolean)
  (#any-of? @boolean "True" "False"))

; Function calls and holes
(call
  function: [
    (identifier) @function
    (scoped_identifier
      (identifier) @function .)
  ])

(call
  function: (type_application
    name: [
      (identifier) @function
      (scoped_identifier
        (identifier) @function .)
    ]))

(call
  "!" @punctuation.special)

(hole
  "?" @punctuation.special
  name: (identifier) @label)

; Literals and comments
(string) @string
(escape_sequence) @string.escape
(char) @string.special
(integer) @number
(natural) @number
(float) @number
(comment) @comment

; Keywords
[
  "def"
  "law"
  "type"
  "match"
  "case"
  "do"
  "return"
  "import"
  "as"
  "for"
  "exs"
  "where"
  "is"
] @keyword

; Operators
[
  "&"
  "|"
  "||"
  "&&"
  "<"
  "<="
  ">"
  ">="
  "<>"
  "++"
  "<&>"
  ".|."
  ".^."
  ".&."
  "<<"
  ">>"
  "+"
  "-"
  "*"
  "/"
  "%"
  "^"
  "=="
  "!="
  "="
  "<-"
  "->"
  "=>"
  "@"
  "~"
] @operator

; Delimiter pairs and separators
[
  "("
  ")"
  "["
  "]"
  "{"
  "}"
  "\\{"
] @punctuation.bracket

(type_application
  ["<" ">"] @punctuation.bracket)

(type_parameters
  ["<" ">"] @punctuation.bracket)

(do_block
  ["<" ">"] @punctuation.bracket)

[
  ","
  ":"
  ";"
] @punctuation.delimiter

(scoped_identifier
  "." @punctuation.delimiter)
