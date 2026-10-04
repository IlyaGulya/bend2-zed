#!/usr/bin/env python3
"""Exercise pinned grammar with real incremental edits and Zed queries."""
from __future__ import annotations

import ctypes
import subprocess
import random
import tempfile
import tomllib
from pathlib import Path

from tree_sitter import Language, Parser, Query, QueryCursor
from check_highlights import ROOT, extract_cases, fetch_grammar


def load_language(grammar: Path, output: Path) -> Language:
    subprocess.run([
        "cc", "-std=c11", "-shared", "-fPIC", "-O2", "-I", str(grammar / "src"),
        str(grammar / "src/parser.c"), str(grammar / "src/scanner.c"), "-o", str(output),
    ], check=True)
    library = ctypes.CDLL(str(output))
    function = library.tree_sitter_bend
    function.restype = ctypes.c_void_p
    # Language retains the grammar's static data; keep its library loaded.
    capsule_new = ctypes.pythonapi.PyCapsule_New
    capsule_new.restype = ctypes.py_object
    capsule_new.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    language = Language(capsule_new(function(), b"tree_sitter.Language", None))
    LIBRARIES.append(library)
    return language


LIBRARIES: list[ctypes.CDLL] = []


def shape(node):
    return (
        node.type, node.start_byte, node.end_byte, node.start_point, node.end_point,
        node.is_named, node.is_missing, node.is_error,
        tuple((node.field_name_for_child(i), shape(child)) for i, child in enumerate(node.children)),
    )


def point(source: bytes, offset: int) -> tuple[int, int]:
    prefix = source[:offset]
    return prefix.count(b"\n"), len(prefix.rsplit(b"\n", 1)[-1])


def edit(parser: Parser, tree, source: bytes, offset: int, old: bytes, new: bytes):
    assert source[offset:offset + len(old)] == old
    updated = source[:offset] + new + source[offset + len(old):]
    tree.edit(
        start_byte=offset, old_end_byte=offset + len(old), new_end_byte=offset + len(new),
        start_point=point(source, offset), old_end_point=point(source, offset + len(old)),
        new_end_point=point(updated, offset + len(new)),
    )
    incremental = parser.parse(updated, tree)
    fresh = parser.parse(updated)
    assert shape(incremental.root_node) == shape(fresh.root_node), "incremental tree differs from fresh parse"
    return updated, incremental


def captures(query: Query, tree, source: bytes):
    return {(name, node.start_byte, node.end_byte, source[node.start_byte:node.end_byte])
            for name, nodes in QueryCursor(query).captures(tree.root_node).items() for node in nodes}


def descendants(node):
    yield node
    for child in node.children:
        yield from descendants(child)


def run(grammar: Path, directory: Path) -> None:
    language = load_language(grammar, directory / "bend.so")
    parser = Parser(language)
    query_paths = sorted((ROOT / "languages/bend2").glob("*.scm"))
    queries = {path.name: Query(language, path.read_text()) for path in query_paths}
    highlight = queries["highlights.scm"]
    prefix = b"def before():\n  True{}\n"
    suffixes = [
        (b"def after(x: Nat) -> Nat:\n  consume(x)\n", "function_definition", b"after", "function"),
        (b"type After is Data:\n  Done{}\n", "type_declaration", b"After", "type"),
        (b"law After:\n  Type\n", "law_declaration", b"After", "function"),
    ]
    count = 0
    for suffix, kind, name, capture in suffixes:
        for newline in (b"\n", b"\r\n"):
            original = (prefix + b"def broken():\n  consume(1)\n" + suffix).replace(b"\n", newline)
            tree = parser.parse(original)
            assert not tree.root_node.has_error, (kind, str(tree.root_node))
            pristine = shape(tree.root_node)
            baseline = {key: captures(query, tree, original) for key, query in queries.items()}
            offset = original.index(b"consume(1)") + len(b"consume(1")
            source = original
            for _ in range(2):
                source, tree = edit(parser, tree, source, offset, b")", b"")
                assert tree.root_node.has_error, "damaged input must report a syntax error"
                nodes = [node for node in descendants(tree.root_node) if node.type == kind
                         and (head := node.child_by_field_name("name")) is not None
                         and source[head.start_byte:head.end_byte] == name]
                assert len(nodes) == 1 and not nodes[0].has_error, "intact following declaration lost"
                got = captures(highlight, tree, source)
                assert any(c == capture and text == name for c, _, _, text in got), "following name lost highlight"
                # Compare all unaffected captures in every Zed query, translating offsets.
                suffix_start = original.index(suffix.split(b"\n")[0])
                for key, expected in baseline.items():
                    retained = {(c, start - 1, end - 1, text) for c, start, end, text in expected if start >= suffix_start}
                    assert retained <= captures(queries[key], tree, source), (key, "suffix captures lost")
                    untouched_prefix = {entry for entry in expected if entry[2] <= len(prefix.replace(b"\n", newline))}
                    assert untouched_prefix <= captures(queries[key], tree, source), (key, "prefix captures lost")
                source, tree = edit(parser, tree, source, offset, b"", b")")
                assert source == original and shape(tree.root_node) == pristine, "repair did not restore original tree"
                for key, expected in baseline.items():
                    assert captures(queries[key], tree, source) == expected, "repair changed captures"
                count += 1
    # Damaged nested matches have weaker guarantees: keyword colors + repair,
    # not preservation of later case-clause structure.
    original = b'def broken():\n  match x:\n    case True{}:\n      row = String.append("a", String.append("b", String.append("c", String.append("d", "e"))))\n    case False{}: 0n\ndef after():\n  match x:\n    case True{}: 1n\n    case False{}: 0n\n'
    tree = parser.parse(original)
    assert not tree.root_node.has_error
    pristine = shape(tree.root_node)
    offset = original.index(b'"e"))))') + len(b'"e"))')
    source = original
    for _ in range(2):
        source, tree = edit(parser, tree, source, offset, b"))", b"")
        assert tree.root_node.has_error
        got = captures(highlight, tree, source)
        expected_cases = {i for i in range(len(source)) if source.startswith(b"case ", i)}
        assert {start for c, start, _, text in got if c == "keyword" and text == b"case"} == expected_cases
        assert any(c == "function" and text == b"after" for c, _, _, text in got)
        source, tree = edit(parser, tree, source, offset, b"", b"))")
        assert shape(tree.root_node) == pristine
        count += 1
    # Consistency alone is not a guarantee of error locality or useful captures.
    rng = random.Random(20261004)
    edits = 0
    for title, text in extract_cases(grammar / "test/corpus"):
        original = text.encode()
        tree = parser.parse(original)
        pristine = shape(tree.root_node)
        candidates = [i for i, byte in enumerate(original) if 32 <= byte < 127]
        if not candidates:
            continue
        for _ in range(3):
            offset = rng.choice(candidates)
            old = original[offset:offset + 1]
            replacement = rng.choice([b"", b"?", b" "])
            source, tree = edit(parser, tree, original, offset, old, replacement)
            fresh = parser.parse(source)
            for key, query in queries.items():
                assert captures(query, tree, source) == captures(query, fresh, source), (title, key)
            source, tree = edit(parser, tree, source, offset, replacement, old)
            assert source == original and shape(tree.root_node) == pristine, title
            edits += 2
    print(f"PASS: {count} targeted break/repair cycles; {edits} seeded corpus edits; LF/CRLF; incremental/fresh trees and all Zed queries")


def main():
    manifest = tomllib.loads((ROOT / "extension.toml").read_text())["grammars"]["bend"]
    with tempfile.TemporaryDirectory(prefix="bend-recovery-") as name:
        directory = Path(name)
        grammar = fetch_grammar(manifest["repository"], manifest["rev"], directory)
        run(grammar, directory)


if __name__ == "__main__":
    main()
