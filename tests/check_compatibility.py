#!/usr/bin/env python3
"""Regress official Bend syntax, captures, and incremental break/repair behavior."""
from __future__ import annotations

import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tree_sitter import Parser, Query

from check_highlights import ROOT, fetch_grammar
from check_recovery import captures, descendants, edit, load_language, shape


@dataclass(frozen=True)
class Case:
    title: str
    source: bytes
    damage_at: bytes
    damage_token: bytes
    check: Callable


def text(source, node):
    return source[node.start_byte:node.end_byte]


def one(tree, source, kind, spelling):
    nodes = [node for node in descendants(tree.root_node)
             if node.type == kind and text(source, node) == spelling]
    assert len(nodes) == 1, (kind, spelling, str(tree.root_node))
    return nodes[0]


def field(source, node, name, spelling):
    child = node.child_by_field_name(name)
    assert child is not None and text(source, child) == spelling, (node.type, name, spelling)
    return child


def captured(got, node, source, name):
    assert (name, node.start_byte, node.end_byte, text(source, node)) in got, (
        name, node.type, text(source, node))


def declaration(tree, source, kind, name):
    nodes = [node for node in tree.root_node.named_children if node.type == kind
             and (head := node.child_by_field_name("name")) is not None
             and text(source, head) == name]
    assert len(nodes) == 1 and not nodes[0].has_error, (kind, name, str(tree.root_node))
    return nodes[0]


def check_law(tree, source, got):
    law = declaration(tree, source, "law_declaration", b"twice")
    captured(got, field(source, law, "name", b"twice"), source, "function")
    clause = one(tree, source, "for_clause", b"for ~f: Nat -> Nat")
    field(source, clause, "quantifier", b"~")
    captured(got, field(source, clause, "name", b"f"), source, "variable.parameter")
    assert field(source, clause, "type", b"Nat -> Nat").type == "function_type"
    argument = one(tree, source, "template_argument", b"~(n => 1n+n)")
    assert argument.named_children[0].type == "parenthesized_expression"
    call = one(tree, source, "call", b"twice(~(n => 1n+n), 1n)")
    captured(got, field(source, call, "function", b"twice"), source, "function")
    for node in descendants(law):
        if node.type in ("law", "for"):
            captured(got, node, source, "keyword")
        elif node.type == "identifier" and text(source, node) == b"Nat":
            captured(got, node, source, "type.builtin")


def check_unsafe(tree, source, got):
    name = b"Laws.false_law" if b"Laws.false_law?" in source else b"spin"
    definition = declaration(tree, source, "function_definition", name)
    head = field(source, definition, "name", name)
    final_name = head.named_children[-1] if head.type == "scoped_identifier" else head
    captured(got, final_name, source, "function")
    marker = field(source, definition, "unsafe", b"?")
    assert marker.start_byte == head.end_byte, "unsafe marker must follow the whole name"
    captured(got, marker, source, "attribute")
    assert not any(node.type == "hole" for node in descendants(definition))
    call = one(tree, source, "call", name + b"()")
    function = field(source, call, "function", name)
    final_function = function.named_children[-1] if function.type == "scoped_identifier" else function
    captured(got, final_function, source, "function")


def check_field(tree, source, got):
    outer = declaration(tree, source, "type_declaration", b"Outer")
    captured(got, field(source, outer, "name", b"Outer"), source, "type")
    constructor = one(tree, source, "constructor_declaration", b"Outer{a: Inner, a.b: U32}")
    captured(got, field(source, constructor, "name", b"Outer"), source, "constructor")
    member = one(tree, source, "field_declaration", b"a.b: U32")
    name = field(source, member, "name", b"a.b")
    assert name.type == "scoped_identifier", "dotted field name must remain one declaration"
    captured(got, name.named_children[-1], source, "property")
    captured(got, field(source, member, "type", b"U32"), source, "type.builtin")


def check_let(tree, source, got):
    definition = declaration(tree, source, "function_definition", b"main")
    captured(got, field(source, definition, "name", b"main"), source, "function")
    if b"-n : Nat" in source:
        statement = one(tree, source, "let_statement", b"-n : Nat = 5n")
        pattern = field(source, statement, "pattern", b"-n")
        assert pattern.type == "quantified_pattern"
        field(source, pattern, "quantifier", b"-")
        captured(got, field(source, pattern, "name", b"n"), source, "variable")
        captured(got, field(source, statement, "type", b"Nat"), source, "type.builtin")
        assert field(source, statement, "value", b"5n").type == "natural"
    elif b"x : U32" in source:
        group = one(tree, source, "parenthesized_expression",
                    b"(x : U32 = 1; y : U32 = 2; x + y : U32)")
        statements = [node for node in group.named_children if node.type == "let_statement"]
        assert [text(source, node) for node in statements] == [b"x : U32 = 1", b"y : U32 = 2"]
        for statement, name, value in zip(statements, (b"x", b"y"), (b"1", b"2")):
            captured(got, field(source, statement, "pattern", name), source, "variable")
            captured(got, field(source, statement, "type", b"U32"), source, "type.builtin")
            assert field(source, statement, "value", value).type == "integer"
        captured(got, field(source, group, "type", b"U32"), source, "type.builtin")
        assert any(node.type == "binary_expression" for node in group.named_children)
    else:
        statement = one(tree, source, "let_statement", b"z : U32 = 30")
        captured(got, field(source, statement, "pattern", b"z"), source, "variable")
        captured(got, field(source, statement, "type", b"U32"), source, "type.builtin")
        assert field(source, statement, "value", b"30").type == "integer"


def check_short_fill(tree, source, got):
    # The compiler rejects this cross-declaration arity mismatch. A syntax
    # grammar cannot match names and count a different declaration's clauses.
    law = declaration(tree, source, "law_declaration", b"F")
    clauses = [node for node in descendants(law) if node.type == "for_clause"]
    assert len(clauses) == 2
    for clause, name in zip(clauses, (b"f", b"g")):
        field(source, clause, "quantifier", b"~")
        captured(got, field(source, clause, "name", name), source, "variable.parameter")
    definition = declaration(tree, source, "function_definition", b"F")
    parameters = field(source, definition, "parameters", b"(f)")
    assert [text(source, node) for node in parameters.named_children] == [b"f"]
    captured(got, field(source, definition, "name", b"F"), source, "function")
    one(tree, source, "template_argument", b"~(h => h(1n))")
    argument = one(tree, source, "template_argument", b"~inc")
    captured(got, argument.named_children[0], source, "variable")


# Minimized from the pinned official Bend reference's tests/comptime/law.bend,
# tests/import/unsafe-law/safe.bend and tests/import/unsafe_law_own.bend,
# tests/run/ctr_dotted_field.bend, tests/parse/typed_let_sugar.bend, and
# tests/comptime/err_fill_short.bend (syntax-only; compiler rejects fill arity).
CASES = (
    Case("law template clause and call argument",
         b"law twice:\n  for ~f: Nat -> Nat\n  for x: Nat\n  Nat\n"
         b"def twice(f, x):\n  f(f(x))\n"
         b"def main():\n  twice(~(n => 1n+n), 1n)\n",
         b"1n)\n", b")", check_law),
    Case("unsafe unqualified definition",
         b"def spin?() -> Empty:\n  spin()\n",
         b"spin()\n", b")", check_unsafe),
    Case("unsafe qualified definition",
         b"def Laws.false_law?():\n  Laws.false_law()\n",
         b"Laws.false_law()\n", b")", check_unsafe),
    Case("dotted constructor field declaration",
         b"type Inner is Data:\n  Inner{b: U32}\n"
         b"type Outer is Data:\n  Outer{a: Inner, a.b: U32}\n",
         b"a.b: U32}\n", b"}", check_field),
    Case("erased typed let",
         b"def main() -> U32:\n  -n : Nat = 5n\n  30\n",
         b"= 5n", b"=", check_let),
    Case("ordinary typed let",
         b"def main() -> U32:\n  z : U32 = 30\n  z\n",
         b"= 30", b"=", check_let),
    Case("grouped typed let sequence",
         b"def main() -> U32:\n  (x : U32 = 1; y : U32 = 2; x + y : U32)\n",
         b"x + y : U32)\n", b")", check_let),
    Case("compiler-only law fill arity boundary",
         b"law F:\n  for ~f: (Nat -> Nat) -> Nat\n  for ~g: Nat -> Nat\n  Nat\n"
         b"def F(f):\n  f\n"
         b"def main():\n  F(~(h => h(1n)), ~inc)\n",
         b"~inc)\n", b")", check_short_fill),
)
INVALID_CASES = (
    ("template clause after ordinary clause",
     b"law mixed:\n  for x: Nat\n  for ~f: Nat -> Nat\n  Nat\n"),
    ("whitespace before unsafe marker", b"def spin ?() -> Empty:\n  spin()\n"),
    ("whitespace before qualified unsafe marker",
     b"def Laws.false_law ?():\n  Laws.false_law()\n"),
)
FOLLOWING = b"def after(x: Nat) -> Nat:\n  consume(x)\n"


def run(grammar: Path, directory: Path) -> None:
    language = load_language(grammar, directory / "bend-compatibility.so")
    parser = Parser(language)
    highlight = Query(language, (ROOT / "languages/bend2/highlights.scm").read_text())
    cycles = 0
    for case in CASES:
        for newline in (b"\n", b"\r\n"):
            original = (case.source + FOLLOWING).replace(b"\n", newline)
            # Match snippets independent of the file's line-ending convention.
            needle = case.damage_at.replace(b"\n", newline)
            offset = original.index(needle) + needle.index(case.damage_token)
            tree = parser.parse(original)
            assert not tree.root_node.has_error, (case.title, str(tree.root_node))
            pristine = shape(tree.root_node)
            baseline = captures(highlight, tree, original)
            case.check(tree, original, baseline)
            for node in tree.root_node.named_children:
                for token in node.children:
                    if token.type in ("def", "type", "law"):
                        captured(baseline, token, original, "keyword")
            suffix_start = len(case.source.replace(b"\n", newline))
            source = original
            for _ in range(2):
                source, tree = edit(parser, tree, source, offset, case.damage_token, b"")
                assert tree.root_node.has_error, (case.title, "damage must report a syntax error")
                following = declaration(tree, source, "function_definition", b"after")
                got = captures(highlight, tree, source)
                captured(got, field(source, following, "name", b"after"), source, "function")
                retained = {(name, start - len(case.damage_token), end - len(case.damage_token), value)
                            for name, start, end, value in baseline if start >= suffix_start}
                assert retained <= got, (case.title, "intact following definition lost captures")
                source, tree = edit(parser, tree, source, offset, b"", case.damage_token)
                assert source == original and not tree.root_node.has_error, case.title
                assert shape(tree.root_node) == pristine, (case.title, "repair changed tree")
                assert captures(highlight, tree, source) == baseline, (case.title, "repair changed captures")
                case.check(tree, source, baseline)
                cycles += 1
    for title, fixture in INVALID_CASES:
        for newline in (b"\n", b"\r\n"):
            source = (fixture + FOLLOWING).replace(b"\n", newline)
            tree = parser.parse(source)
            assert tree.root_node.has_error, (title, "invalid syntax accepted")
            following = declaration(tree, source, "function_definition", b"after")
            captured(captures(highlight, tree, source),
                     field(source, following, "name", b"after"), source, "function")
    print(f"PASS: {len(CASES)} official-syntax regressions; {len(INVALID_CASES)} syntax boundaries; "
          f"{cycles} deterministic break/repair cycles; LF/CRLF; structure and captures")


def main() -> None:
    manifest = tomllib.loads((ROOT / "extension.toml").read_text())["grammars"]["bend"]
    with tempfile.TemporaryDirectory(prefix="bend-compatibility-") as name:
        directory = Path(name)
        grammar = fetch_grammar(manifest["repository"], manifest["rev"], directory)
        run(grammar, directory)


if __name__ == "__main__":
    main()
