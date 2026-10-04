#!/usr/bin/env python3
"""Exercise the pinned external scanner's state transitions and snapshot boundaries.

Requires a C compiler with AddressSanitizer and UndefinedBehaviorSanitizer support.
No installed Tree-sitter runtime or edited grammar checkout is used.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from check_highlights import ROOT, fetch_grammar


def main() -> None:
    manifest = tomllib.loads((ROOT / "extension.toml").read_text(encoding="utf-8"))
    pin = manifest["grammars"]["bend"]
    compiler = shlex.split(os.environ.get("CC", "cc"))
    if not compiler or shutil.which(compiler[0]) is None:
        raise RuntimeError("scanner checks require a C compiler; install one or set CC")

    with tempfile.TemporaryDirectory(prefix="bend2-scanner-") as temporary:
        workspace = Path(temporary)
        grammar = fetch_grammar(pin["repository"], pin["rev"], workspace)
        executable = workspace / "scanner-checks"
        command = [
            *compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-g",
            "-O1",
            "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer",
            "-I",
            str(grammar / "src"),
            str(ROOT / "tests" / "test_scanner.c"),
            "-o",
            str(executable),
        ]
        print(f"Scanner grammar: {pin['repository']} @ {pin['rev']}", flush=True)
        subprocess.run(command, check=True)
        # Memory/bounds problems and UB must fail the gate, never become a
        # compiler-dependent warning or a silently unsanitized fallback.
        subprocess.run(
            [str(executable)],
            check=True,
            env={
                **os.environ,
                "ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1",
                "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1",
            },
        )


if __name__ == "__main__":
    main()
