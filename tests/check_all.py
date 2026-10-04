#!/usr/bin/env python3
"""Run release verification; never hide upstream compatibility failures."""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dir", type=Path, help="offline Bend reference; full content hashes still checked")
    args = parser.parse_args()
    failed = []
    for script in ("check_highlights.py", "check_recovery.py", "check_compatibility.py", "check_scanner.py", "check_upstream_gate.py", "check_upstream.py"):
        print(f"\n=== {script} ===", flush=True)
        command = [sys.executable, str(ROOT / "tests" / script)]
        if script == "check_upstream.py" and args.reference_dir is not None:
            command += ["--reference-dir", str(args.reference_dir.resolve())]
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            failed.append(script)
    if failed:
        raise SystemExit("FAIL: " + ", ".join(failed))
    print("PASS: all pinned grammar verification gates")


if __name__ == "__main__":
    main()
