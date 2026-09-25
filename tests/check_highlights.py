#!/usr/bin/env python3
"""Validate Zed highlight and bracket queries against the pinned Bend grammar corpus."""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TREE_SITTER = ["npx", "--yes", "--package=tree-sitter-cli@0.27.0", "tree-sitter"]
RANGE = re.compile(r"start: \((\d+), (\d+)\), end: \((\d+), (\d+)\)")
CAPTURE = re.compile(r"capture:\s*\d+\s+-\s+([a-z_.]+),")

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


def run_tree_sitter(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        [*TREE_SITTER, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "NO_COLOR": "1", "CLICOLOR": "0"},
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"tree-sitter {' '.join(args)} failed:\n{result.stderr}{result.stdout}"
        )
    return result.stdout


def fetch_grammar(repo: str, revision: str, destination: Path) -> Path:
    url = f"https://codeload.github.com/{repo}/tar.gz/{revision}"
    request = urllib.request.Request(url, headers={"User-Agent": "bend2-zed-corpus-test"})
    with urllib.request.urlopen(request, timeout=60) as response:
        archive_data = response.read()

    with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as archive:
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
    separator = re.compile(r"-{10,}")
    for corpus_file in sorted(corpus_dir.glob("*.txt")):
        lines = corpus_file.read_text(encoding="utf-8").splitlines()
        index = 0
        while index < len(lines):
            if not heading.fullmatch(lines[index]):
                index += 1
                continue
            title = lines[index + 1].strip()
            index += 3
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


def query_blocks(output: str, paths: list[Path]) -> dict[Path, list[str]]:
    by_name = {str(path.resolve()): path for path in paths}
    blocks = {path: [] for path in paths}
    active = None
    for line in output.splitlines():
        name = line.strip()
        if name in by_name:
            active = by_name[name]
        elif active is not None:
            blocks[active].append(line)
    return blocks


def assert_highlight_coverage(
    output: str,
    cases: list[tuple[str, str]],
    paths: list[Path],
) -> tuple[int, int, set[str]]:
    by_path = {
        str(path.resolve()): {
            "title": title,
            "data": source.encode("utf-8"),
            "line_starts": [0],
            "covered": bytearray(len(source.encode("utf-8"))),
        }
        for (title, source), path in zip(cases, paths, strict=True)
    }
    for item in by_path.values():
        item["line_starts"].extend(
            match.end() for match in re.finditer(b"\n", item["data"])
        )

    active = None
    captures = set()
    ranges = 0
    for line in output.splitlines():
        name = line.strip()
        if name in by_path:
            active = by_path[name]
            continue
        capture = CAPTURE.search(line)
        if capture:
            captures.add(capture.group(1))
        match = RANGE.search(line)
        if not match:
            continue
        if active is None:
            raise RuntimeError(
                f"Tree-sitter returned a capture before its file path: {line.strip()!r}; "
                f"output starts {output.splitlines()[:3]!r}; expected {list(by_path)[:1]!r}"
            )
        start_row, start_column, end_row, end_column = map(int, match.groups())
        starts = active["line_starts"]
        if end_row >= len(starts) or start_row >= len(starts):
            raise RuntimeError(f"invalid capture row in {active['title']}: {line.strip()}")
        start = starts[start_row] + start_column
        end = starts[end_row] + end_column
        if end < start or end > len(active["data"]):
            raise RuntimeError(f"invalid capture range in {active['title']}: {line.strip()}")
        active["covered"][start:end] = b"\x01" * (end - start)
        ranges += 1

    uncovered = []
    total_source_bytes = 0
    for item in by_path.values():
        for index, byte in enumerate(item["data"]):
            if byte in b" \t\r\n":
                continue
            total_source_bytes += 1
            if not item["covered"][index]:
                excerpt = item["data"][max(0, index - 8) : index + 12].decode(
                    "utf-8", errors="replace"
                )
                uncovered.append(f"{item['title']} near {excerpt!r}")
    if uncovered:
        raise RuntimeError(
            f"{len(uncovered)} non-whitespace source bytes have no highlight capture:\n"
            + "\n".join(uncovered[:12])
        )
    unsupported = captures - ZED_CAPTURES
    if unsupported:
        raise RuntimeError(f"captures unsupported by Zed themes: {', '.join(sorted(unsupported))}")
    if "variable.special" not in captures:
        raise RuntimeError("the wildcard `_` has no variable.special capture")
    return ranges, total_source_bytes, captures


def assert_brackets(
    blocks: dict[Path, list[str]],
    cases: list[tuple[str, str]],
    paths: list[Path],
) -> None:
    case_by_title = {
        title: (source, path) for (title, source), path in zip(cases, paths, strict=True)
    }
    braces_source, braces_path = case_by_title["Braces"]
    brace_lines = blocks[braces_path]
    match_open = [line for line in brace_lines if "- open," in line and "text: `\\{" in line]
    if len(match_open) != 3:
        raise RuntimeError(f"expected 3 match-expression opening delimiters, got {len(match_open)}")

    close_positions = set()
    for line in brace_lines:
        match = re.search(r"capture:\s*\d+\s+-\s+close,\s+start: \((\d+), (\d+)\)", line)
        if match and "text: `}`" in line:
            close_positions.add(tuple(map(int, match.groups())))
    source_lines = braces_source.splitlines()
    for line in match_open:
        match = re.search(r"start: \((\d+), (\d+)\)", line)
        row, column = map(int, match.groups())
        source_line = source_lines[row].encode("utf-8")
        if source_line[column : column + 2] != b"\\{":
            raise RuntimeError(f"match opener capture does not point to \\{{ on line {row + 1}")
        close_column = source_line.rfind(b"}")
        if close_column < 0 or (row, close_column) not in close_positions:
            raise RuntimeError(f"match expression on line {row + 1} has no matching close capture")

    reflexivity_row = next(i for i, line in enumerate(source_lines) if "{==}" in line)
    reflexivity_column = source_lines[reflexivity_row].index("{")
    if (reflexivity_row, reflexivity_column) in {
        tuple(map(int, match.groups()))
        for line in brace_lines
        if "- open," in line
        if (match := re.search(r"start: \((\d+), (\d+)\)", line))
    }:
        raise RuntimeError("reflexivity literal `{==}` is incorrectly treated as a bracket pair")

    for title in ("Types", "Datatype", "Do blocks"):
        _, path = case_by_title[title]
        lines = blocks[path]
        opens = [line for line in lines if "- open," in line and "text: `<`" in line]
        closes = [line for line in lines if "- close," in line and "text: `>`" in line]
        if not opens or len(opens) != len(closes):
            raise RuntimeError(
                f"unpaired generic angle delimiters in {title}: {len(opens)} opens/{len(closes)} closes"
            )


def main() -> None:
    if not shutil.which("npx"):
        raise RuntimeError("Node.js/npm is required to run the pinned tree-sitter CLI")

    manifest = tomllib.loads((ROOT / "extension.toml").read_text(encoding="utf-8"))
    grammar = manifest["grammars"]["bend"]
    repository = grammar["repository"].removeprefix("https://github.com/").removesuffix(".git")
    revision = grammar["rev"]

    with tempfile.TemporaryDirectory(prefix="bend2-highlight-test-") as temporary:
        temporary_dir = Path(temporary)
        grammar_dir = fetch_grammar(repository, revision, temporary_dir)
        parser_output = run_tree_sitter(["test"], cwd=grammar_dir)
        parser_summary = re.search(
            r"Total parses: (\d+); successful parses: (\d+); failed parses: (\d+)",
            parser_output,
        )
        if not parser_summary or parser_summary.group(1) != parser_summary.group(2) or parser_summary.group(3) != "0":
            raise RuntimeError(f"the pinned grammar corpus did not parse cleanly:\n{parser_output}")

        cases = extract_cases(grammar_dir / "test/corpus")
        if len(cases) != int(parser_summary.group(1)):
            raise RuntimeError(
                f"extracted {len(cases)} examples but the parser ran {parser_summary.group(1)} corpus tests"
            )
        inputs_dir = temporary_dir / "inputs"
        inputs_dir.mkdir()
        paths = []
        for index, (title, source) in enumerate(cases, start=1):
            path = inputs_dir / f"{index:03d}-{re.sub(r'[^A-Za-z0-9]+', '-', title)}.bend"
            path.write_text(source, encoding="utf-8")
            paths.append(path.resolve())

        highlights = ROOT / "languages/bend2/highlights.scm"
        brackets = ROOT / "languages/bend2/brackets.scm"
        cli_args = ["--grammar-path", str(grammar_dir)]
        query_output = run_tree_sitter(
            ["query", *cli_args, "--captures", str(highlights), *(str(path) for path in paths)],
            cwd=ROOT,
        )
        ranges, source_bytes, captures = assert_highlight_coverage(query_output, cases, paths)

        highlight_html = run_tree_sitter(
            [
                "highlight",
                *cli_args,
                "--query-paths",
                str(highlights),
                "--html",
                "--layout",
                "fragment",
                "--style",
                "minimal",
                *(str(path) for path in paths),
            ],
            cwd=ROOT,
        )
        if "class='variable'>M</span>" not in highlight_html or "class='variable'>P</span>" not in highlight_html:
            raise RuntimeError("module import aliases are not highlighted as variables")

        bracket_output = run_tree_sitter(
            ["query", *cli_args, "--captures", str(brackets), *(str(path) for path in paths)],
            cwd=ROOT,
        )
        assert_brackets(query_blocks(bracket_output, paths), cases, paths)

    print(
        f"PASS: {len(cases)} pinned parser corpus examples; {ranges} highlight captures; "
        f"{source_bytes} non-whitespace source bytes covered; "
        f"{len(captures)} Zed-supported capture types; bracket queries verified."
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, tarfile.TarError) as error:
        raise SystemExit(f"FAIL: {error}") from error
