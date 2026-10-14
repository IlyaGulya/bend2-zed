#!/usr/bin/env python3
"""Validate Zed highlight and bracket queries against the pinned Bend grammar corpus."""

from __future__ import annotations

import io
import os
import re
import subprocess
import tarfile
import tempfile
import tomllib
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

ZED_CAPTURES = frozenset(
    """
    attribute boolean comment comment.doc constant constant.builtin constructor embedded
    emphasis emphasis.strong enum function hint keyword label link_text link_uri number
    operator predictive preproc primary property punctuation punctuation.bracket
    punctuation.delimiter punctuation.list_marker punctuation.special string string.escape
    string.regex string.special string.special.symbol tag tag.doctype text.literal title
    type type.builtin variable variable.special variable.parameter variant
    """.split()
)


def fetch_grammar(repo: str, revision: str, destination: Path) -> Path:
    local_repo = ROOT / "tree-sitter-bend2-soulthym"
    archive_data = None
    archive_mode = "r:"
    if local_repo.is_dir():
        local_remote = subprocess.run(
            ["git", "-C", str(local_repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull},
        )
        def github_repository(url: str) -> str:
            return url.removeprefix("https://github.com/").removeprefix("git@github.com:").removesuffix(".git")

        if local_remote.returncode == 0 and github_repository(local_remote.stdout.strip()) == github_repository(repo):
            local_archive = subprocess.run(
                [
                    "git",
                    "-C",
                    str(local_repo),
                    "archive",
                    "--format=tar",
                    "--prefix=tree-sitter-bend2/",
                    revision,
                ],
                capture_output=True,
                check=False,
            )
            if local_archive.returncode == 0:
                archive_data = local_archive.stdout

    if archive_data is None:
        if repo.startswith("https://github.com/"):
            repository = repo.removeprefix("https://github.com/").removesuffix(".git")
        elif repo.startswith("git@github.com:"):
            repository = repo.removeprefix("git@github.com:").removesuffix(".git")
        else:
            raise RuntimeError(f"unsupported grammar repository URL: {repo}")
        url = f"https://codeload.github.com/{repository}/tar.gz/{revision}"
        request = urllib.request.Request(url, headers={"User-Agent": "bend2-zed-corpus-test"})
        with urllib.request.urlopen(request, timeout=60) as response:
            archive_data = response.read()
        archive_mode = "r:gz"

    with tarfile.open(fileobj=io.BytesIO(archive_data), mode=archive_mode) as archive:
        members = []
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                continue
            members.append(member)
        if not members:
            raise RuntimeError("the pinned grammar archive contains no safe files")
        archive.extractall(destination, members=members, filter="data")
        root_name = members[0].name.split("/", 1)[0]

    grammar_dir = destination / root_name
    if not (grammar_dir / "test/corpus").is_dir():
        raise RuntimeError("the pinned grammar archive has no test/corpus directory")
    return grammar_dir


def extract_cases(corpus_dir: Path) -> list[tuple[str, str]]:
    cases = []
    heading = re.compile(r"={10,}")
    separator = re.compile(r"-{3,}")
    for corpus_file in sorted(corpus_dir.glob("*.txt")):
        lines = corpus_file.read_text(encoding="utf-8").splitlines()
        index = 0
        while index < len(lines):
            if not heading.fullmatch(lines[index]):
                index += 1
                continue
            title = lines[index + 1].strip()
            index += 2
            while index < len(lines) and not heading.fullmatch(lines[index]):
                index += 1
            if index == len(lines):
                raise RuntimeError(f"missing closing corpus heading in {corpus_file}: {title}")
            index += 1
            while index < len(lines) and not lines[index].strip():
                index += 1
            start = index
            while index < len(lines) and not separator.fullmatch(lines[index]):
                index += 1
            if index == len(lines):
                raise RuntimeError(f"missing source/parse separator in {corpus_file}: {title}")
            source = "\n".join(lines[start:index]).rstrip("\n")
            cases.append((title, source))
    return cases


def run(grammar_dir: Path, directory: Path) -> None:
    from tree_sitter import Parser, Query, QueryCursor
    from check_recovery import captures, load_language

    language = load_language(grammar_dir, directory / "bend2-highlights.so")
    parser = Parser(language)
    highlight = Query(language, (ROOT / "languages/bend2/highlights.scm").read_text())
    brackets = Query(language, (ROOT / "languages/bend2/brackets.scm").read_text())
    outline = Query(language, (ROOT / "languages/bend2/outline.scm").read_text())

    def probe(source: bytes):
        tree = parser.parse(source)
        assert not tree.root_node.has_error, str(tree.root_node)
        got = captures(highlight, tree, source)
        assert {name for name, *_ in got} <= ZED_CAPTURES
        return tree, got

    def expect(source, got, spelling, role, occurrence=0):
        start = -1
        for _ in range(occurrence + 1):
            start = source.index(spelling, start + 1)
        assert (role, start, start + len(spelling), spelling) in got, (spelling, role, got)

    source = (
        b"import Base\nimport ./laws.bend as Laws\n"
        b"type Outer<A: Type> is Data:\n  Outer{a: A, a.b: U32}\n"
        b"law twice:\n  for ~f: Nat -> Nat\n  for x: Nat\n  Nat\n"
        b"@unsafe\n"
        b"def Laws.work?(x: Nat) -> U32:\n"
        b"  y = twice(~(n => 1n+n), x)\n"
        b"  z = Laws.launch!(y)\n"
        b"  match True{}:\n"
        b"    case True{}: Outer{y, z}\n"
        b"    case False{}: ?TODO\n"
        b"def literals():\n"
        b"  (_, \"a\\n\", '\\t', 1, 2n, 3.5, &1)\n"
        b"def foreign():\n  import \"effs/work.c\"\n"
    )
    tree, got = probe(source)
    expected = [
        (b"Base", "variable"), (b"./laws.bend", "string.special"),
        (b"Laws", "variable"), (b"Outer", "type"), (b"A", "variable.parameter"),
        (b"Type", "type.builtin"), (b"Data", "type.builtin"),
        (b"a.b", "property"), (b"U32", "type.builtin"),
        (b"twice", "function"), (b"Nat", "type.builtin"),
        (b"@unsafe", "attribute"), (b"Laws.work", "function"), (b"?", "attribute"),
        (b"Laws.launch", "function"), (b"!", "punctuation.special"),
        (b"True", "boolean"), (b"False", "boolean"),
        (b"TODO", "label"), (b"_", "variable.special"),
        (b'"a\\n"', "string"), (b"\\n", "string.escape"),
        (b"'\\t'", "string.special"), (b"3.5", "number"),
        (b"&1", "constant.builtin"), (b'"effs/work.c"', "string"),
        (b"match", "keyword"), (b"=>", "operator"),
    ]
    for spelling, role in expected:
        expect(source, got, spelling, role)
    expect(source, got, b"twice", "function", 1)
    expect(source, got, b"Outer", "constructor", 1)
    expect(source, got, b"Outer", "constructor", 2)
    for marker, spelling in ((b"~f:", b"f"), (b"n =>", b"n")):
        start = source.index(marker) + (1 if marker.startswith(b"~") else 0)
        assert ("variable.parameter", start, start + 1, spelling) in got
    matches = QueryCursor(highlight).matches(tree.root_node)
    for spelling, role in ((b"a.b", "property"), (b"Laws.work", "function"), (b"_", "variable.special")):
        start = source.index(spelling)
        roles = [(pattern, name) for pattern, match in matches for name, nodes in match.items()
                 for node in nodes if node.start_byte == start and node.end_byte == start + len(spelling)]
        assert max(roles)[1] == role, (spelling, roles)

    outline_matches = QueryCursor(outline).matches(tree.root_node)
    outlined = {(match["item"][0].type, source[match["name"][0].start_byte:match["name"][0].end_byte])
                for _, match in outline_matches}
    assert outlined == {
        ("type_definition", b"Outer"), ("constructor_definition", b"Outer"),
        ("law_definition", b"twice"), ("function_definition", b"Laws.work"),
        ("function_definition", b"literals"), ("function_definition", b"foreign"),
    }, outlined
    for _, match in outline_matches:
        item, name = match["item"][0], match["name"][0]
        assert item.start_byte <= name.start_byte < name.end_byte <= item.end_byte

    # Actual ranges matter: GPU '(' is a child of gpu_call, not arguments.
    bracket_sources = (
        b"type Box<A> is Data:\n  Box{value: A}\n"
        b"def f(x):\n  (Box<A>, Box{x}, [x], {x : A}, {x == x : A}, "
        b"\\{Box: x; x}, {==}, launch!(x))\n",
        b"def f():\n  do IO<A>:\n    return 1\n",
    )
    pairs = set()
    for source in bracket_sources:
        tree, _ = probe(source)
        for _, match in QueryCursor(brackets).matches(tree.root_node):
            opened, closed = match["open"][0], match["close"][0]
            left = source[opened.start_byte:opened.end_byte]
            right = source[closed.start_byte:closed.end_byte]
            assert (left, right) in {(b"(", b")"), (b"[", b"]"), (b"{", b"}"), (b"<", b">")}
            assert opened.end_byte <= closed.start_byte
            pairs.add((left, right))
        bracket_captures = captures(brackets, tree, source)
        if b"launch!" in source:
            start = source.index(b"launch!(") + len(b"launch!")
            assert ("open", start, start + 1, b"(") in bracket_captures
            assert not any(value == b"!" for _, _, _, value in bracket_captures)
            reflexivity = source.index(b"{==}")
            assert not any(a == reflexivity for _, a, _, _ in bracket_captures)
    assert pairs == {(b"(", b")"), (b"[", b"]"), (b"{", b"}"), (b"<", b">")}

    # Probe corpus captures, including intentional errors, without treating
    # permissively parsed malformed inputs as supported syntax.
    cases = extract_cases(grammar_dir / "test/corpus")
    total = 0
    for title, text in cases:
        source = text.encode()
        tree = parser.parse(source)
        got = captures(highlight, tree, source)
        assert {name for name, *_ in got} <= ZED_CAPTURES, title
        if not tree.root_node.has_error:
            covered = {i for _, start, end, _ in got for i in range(start, end)}
            missing = [i for i, byte in enumerate(source) if byte not in b" \t\r\n" and i not in covered]
            assert not missing, (title, missing[:12])
        total += len(got)
    print(f"PASS: input-driven highlight roles and precedence; actual bracket pairs and outline; "
          f"{len(cases)} corpus capture probes ({total} captures)")


def main() -> None:
    grammar = tomllib.loads((ROOT / "extension.toml").read_text())["grammars"]["bend2"]
    with tempfile.TemporaryDirectory(prefix="bend2-highlight-test-") as name:
        directory = Path(name)
        grammar_dir = fetch_grammar(grammar["repository"], grammar["rev"], directory)
        run(grammar_dir, directory)


if __name__ == "__main__":
    main()
