#!/usr/bin/env python3
"""Run release verification; never hide upstream compatibility failures."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    failed = []
    for script in ("check_highlights.py", "check_recovery.py", "check_scanner.py", "check_upstream.py"):
        print(f"\n=== {script} ===", flush=True)
        result = subprocess.run([sys.executable, str(ROOT / "tests" / script)], cwd=ROOT)
        if result.returncode:
            failed.append(script)
    if failed:
        raise SystemExit("FAIL: " + ", ".join(failed))
    print("PASS: all pinned grammar verification gates")


if __name__ == "__main__":
    main()
