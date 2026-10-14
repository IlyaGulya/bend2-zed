; General names first; structural roles below take precedence.
(identifier) @variable
((identifier) @variable @variable.special
  (#eq? @variable.special "_"))
((identifier) @type
  (#match? @type "^[A-Z]"))
((identifier) @type.builtin
  (#any-of? @type.builtin
    "Empty" "Unit" "Bool" "Cmp" "Either" "Sigma" "Pair" "Nat" "U32" "F32" "Char" "String"
    "Maybe" "Result" "List" "Word" "Array" "Map" "Set" "Equal" "IO" "Chan" "File" "Socket"
    "Listener" "Window" "Audio" "Image" "Event" "App"))

; Dotted names are single identifiers, so capture their whole supported role.
(function_definition name: (identifier) @function)
(law_definition name: (identifier) @function)
(type_definition name: (identifier) @type)
(constructor_definition name: (identifier) @constructor)
(constructor_expression name: (identifier) @constructor)
(eliminator_arm name: (identifier) @constructor)
(type_application name: (identifier) @type)
(call_expression function: (identifier) @function)
(call_expression function: (type_application name: (identifier) @function))
(do_expression monad: (identifier) @type)

(parameter name: (identifier) @variable.parameter)
(type_parameter name: (identifier) @variable.parameter)
(constructor_definition (type_parameter name: (identifier) @property))
(law_clause name: (identifier) @variable.parameter)
(dependent_type name: (identifier) @variable.parameter)
(lambda_expression parameter: (identifier) @variable.parameter)
(lambda_expression parameter: (reusable_expression (identifier) @variable.parameter))

(import_statement path: (import_path) @string.special)
(import_statement alias: (module_alias) @variable)
"Base" @variable
(builtin_type) @type.builtin
"Kind" @type.builtin
(quantity) @constant.builtin
(decorator) @attribute
(function_definition "?" @attribute)
(gpu_call "!" @punctuation.special)

((constructor_expression name: (identifier) @boolean)
  (#any-of? @boolean "True" "False"))
(hole "?" @punctuation.special name: (identifier) @label)

(string) @string
(escape_sequence) @string.escape
(character) @string.special
(integer) @number
(natural) @number
(float) @number
(comment) @comment

["def" "law" "type" "match" "case" "do" "return" "import" "as"
 "for" "exs" "where" "is"] @keyword
; Recovered identifiers can retain keyword colors without coloring ERROR nodes.
((ERROR (identifier) @keyword)
  (#any-of? @keyword
    "def" "law" "type" "match" "case" "do" "return" "import" "as"
    "for" "exs" "where" "is"))

["&" "|" "||" "&&" "<" "<=" ">" ">=" "<>" "++" "<&>"
 ".|." ".^." ".&." "<<" ">>" "+" "-" "*" "/" "%" "^"
 "==" "!=" "=" "<-" "->" "=>" "@" "~" "\\"] @operator
["(" ")" "[" "]" "{" "}"] @punctuation.bracket
(type_application ["<" ">"] @punctuation.bracket)
(type_parameters ["<" ">"] @punctuation.bracket)
(do_expression ["<" ">"] @punctuation.bracket)
["," ":" ";"] @punctuation.delimiter
