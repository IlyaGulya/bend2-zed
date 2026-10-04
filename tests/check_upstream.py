#!/usr/bin/env python3
"""Sweep every .bend file in the pinned official release; never execute Bend code.

Default invocation is a release gate. --diagnostic emits the same review report
without treating syntax drift or incomplete review as success for release purposes.
No mode writes or updates the rejection baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import multiprocessing
import tarfile
import tempfile
import time
import tomllib
import urllib.request
from pathlib import Path, PurePosixPath

from check_highlights import ROOT, fetch_grammar

REFERENCE = ROOT / "tests/bend-reference.json"
BASELINE = ROOT / "tests/upstream-rejections.json"


def corpus_inventory(root: Path) -> tuple[list[Path], str]:
    files = sorted(root.rglob("*.bend"), key=lambda path: path.relative_to(root).as_posix())
    digest = hashlib.sha256()
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"not a regular corpus file: {path}")
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii") + b"\n")
    return files, digest.hexdigest()


def fetch_reference(reference: dict, destination: Path) -> Path:
    request = urllib.request.Request(reference["archive_url"], headers={"User-Agent": "bend2-zed-upstream-test"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != reference["archive_sha256"]:
        raise RuntimeError("official release archive checksum changed; explicit reference review required")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                raise RuntimeError(f"unsafe release archive member: {member.name}")
        roots = {PurePosixPath(member.name).parts[0] for member in members}
        if len(roots) != 1:
            raise RuntimeError("release archive must have exactly one root")
        archive.extractall(destination, members=members, filter="data")
    return destination / roots.pop()


def validate_reference(root: Path, reference: dict, baseline: dict) -> list[Path]:
    files, digest = corpus_inventory(root)
    if len(files) != reference["corpus"]["files"] or digest != reference["corpus"]["sha256"]:
        raise RuntimeError("reference .bend inventory/content differs from the pinned full release")
    for entry in reference["anchors"]:
        if hashlib.sha256((root / entry["file"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"reference anchor changed: {entry['file']}")
    if baseline["reference_commit"] != reference["commit"]:
        raise RuntimeError("rejection reviews refer to a different Bend release")
    names = {path.relative_to(root).as_posix(): path for path in files}
    seen = set()
    for review in baseline["reviews"]:
        name = review["file"]
        if name in seen or name not in names:
            raise RuntimeError(f"duplicate or missing reviewed fixture: {name}")
        seen.add(name)
        if review["classification"] not in {"malformed-syntax", "valid-source-grammar-gap"}:
            raise RuntimeError(f"invalid rejection classification: {name}")
        if not review["reason"].strip() or not review["evidence"]:
            raise RuntimeError(f"missing explicit review evidence: {name}")
        if hashlib.sha256(names[name].read_bytes()).hexdigest() != review["sha256"]:
            raise RuntimeError(f"reviewed fixture content changed: {name}")
    return files


def worker(connection, grammar: Path, library: Path) -> None:
    # Share the pinned-grammar ctypes loader with the incremental checks, not a
    # separately generated grammar. Imports stay here so metadata/report helpers
    # can be used without the optional tree-sitter Python dependency.
    try:
        from tree_sitter import Parser
        from check_recovery import load_language
        language = load_language(grammar, library)
        connection.send({"ready": True})
        while True:
            path = connection.recv()
            if path is None:
                return
            source = Path(path).read_bytes()
            started = time.monotonic()
            tree = Parser(language).parse(source)
            errors = []
            error_count = 0
            if tree.root_node.has_error:
                stack = [tree.root_node]
                while stack:
                    node = stack.pop()
                    if node.is_error or node.is_missing:
                        error_count += 1
                        if len(errors) < 32:
                            errors.append({
                                "type": node.type, "missing": node.is_missing,
                                "start_byte": node.start_byte, "end_byte": node.end_byte,
                                "start_point": list(node.start_point), "end_point": list(node.end_point),
                                "excerpt": source[node.start_byte:min(node.end_byte, node.start_byte + 200)].decode("utf-8", "replace"),
                            })
                    stack.extend(reversed(node.children))
            expected = [line[2:] for line in source.decode("utf-8").splitlines() if line.startswith("#|")]
            connection.send({
                "status": "rejected" if tree.root_node.has_error else "accepted",
                "seconds": time.monotonic() - started,
                "bytes": len(source), "sha256": hashlib.sha256(source).hexdigest(),
                "error_count": error_count, "errors": errors,
                "expects_diagnostic": any(line.startswith("Error:") or
                                          (line.startswith("exit ") and line[5:].isdigit() and int(line[5:]) > 0)
                                          for line in expected),
                "expected_output": expected,
            })
    except EOFError:
        pass
    except BaseException as error:
        connection.send({"worker_error": f"{type(error).__name__}: {error}"})
    finally:
        connection.close()


def stop_worker(process, connection) -> None:
    connection.close()
    process.terminate()
    process.join(timeout=2)
    if process.is_alive():
        process.kill()
        process.join()


def start_worker(context, grammar: Path, library: Path):
    connection, child = context.Pipe()
    process = context.Process(target=worker, args=(child, grammar, library))
    process.start()
    child.close()
    try:
        if not connection.poll(60):
            raise RuntimeError("parser worker failed to initialize within 60 seconds")
        message = connection.recv()
        if message != {"ready": True}:
            raise RuntimeError(f"parser worker initialization failed: {message}")
    except BaseException:
        stop_worker(process, connection)
        raise
    return process, connection


def sweep(files: list[Path], root: Path, grammar: Path, directory: Path, timeout: float) -> list[dict]:
    context = multiprocessing.get_context("spawn")
    process = connection = None
    results = []
    try:
        for path in files:
            if process is None:
                process, connection = start_worker(context, grammar, directory / "upstream-parser.so")
            started = time.monotonic()
            try:
                connection.send(str(path))
                if not connection.poll(timeout):
                    result = {"status": "timeout", "seconds": time.monotonic() - started}
                else:
                    result = connection.recv()
                    if "worker_error" in result:
                        result = {"status": "worker-error", "detail": result["worker_error"]}
            except (EOFError, BrokenPipeError, ConnectionResetError) as error:
                result = {"status": "worker-error", "detail": f"{type(error).__name__}: {error}"}
            result["file"] = path.relative_to(root).as_posix()
            results.append(result)
            if result["status"] not in {"accepted", "rejected"}:
                stop_worker(process, connection)
                process = connection = None
    finally:
        if process is not None:
            stop_worker(process, connection)
    return results


def review_results(results: list[dict], baseline: dict) -> dict:
    reviews = {entry["file"]: entry for entry in baseline["reviews"]}
    rejected = {entry["file"] for entry in results if entry["status"] == "rejected"}
    accepted = {entry["file"] for entry in results if entry["status"] == "accepted"}
    new = sorted(rejected - reviews.keys())
    formerly = sorted(accepted & reviews.keys())
    gaps = sorted(name for name in rejected & reviews.keys()
                  if reviews[name]["classification"] == "valid-source-grammar-gap")
    infrastructure = [entry["file"] for entry in results if entry["status"] not in {"accepted", "rejected"}]
    reasons = []
    if not baseline["review_complete"]:
        reasons.append(baseline["review_blocker"])
    if new:
        reasons.append(f"{len(new)} new/unreviewed rejections require individual syntax review")
    if formerly:
        reasons.append(f"{len(formerly)} formerly rejected fixtures now accepted; review required")
    if gaps:
        reasons.append(f"{len(gaps)} reviewed valid-source grammar gaps remain")
    if infrastructure:
        reasons.append(f"{len(infrastructure)} files timed out or failed in the parser worker")
    return {"passed": not reasons, "reasons": reasons,
            "new_rejections": new, "formerly_rejected_accepted": formerly,
            "valid_source_gaps": gaps, "infrastructure_failures": infrastructure}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dir", type=Path, help="offline release directory; full corpus checksums are mandatory")
    parser.add_argument("--report", type=Path, default=ROOT / "build/upstream-report.json")
    parser.add_argument("--timeout", type=float, default=10.0, help="hard wall-clock seconds per file (default: 10)")
    parser.add_argument("--diagnostic", action="store_true", help="collect report only; NEVER a release gate")
    args = parser.parse_args()
    if args.timeout <= 0 or not math.isfinite(args.timeout):
        parser.error("--timeout must be finite and greater than zero")
    report = {"mode": "diagnostic" if args.diagnostic else "release", "per_file_timeout_seconds": args.timeout}
    try:
        reference = json.loads(REFERENCE.read_text())
        baseline = json.loads(BASELINE.read_text())
        manifest = tomllib.loads((ROOT / "extension.toml").read_text())["grammars"]["bend"]
        report.update({"reference": reference, "grammar": manifest, "rejection_baseline": baseline,
                       "review_complete": baseline["review_complete"],
                       "diagnostic_note": "Expected semantic/runtime diagnostics are NOT a syntax oracle or exemption."})
        with tempfile.TemporaryDirectory(prefix="bend-upstream-") as name:
            directory = Path(name)
            root = args.reference_dir.resolve() if args.reference_dir else fetch_reference(reference, directory)
            files = validate_reference(root, reference, baseline)
            grammar = fetch_grammar(manifest["repository"], manifest["rev"], directory)
            results = sweep(files, root, grammar, directory, args.timeout)
        gate = review_results(results, baseline)
        report.update({"total": len(results), "accepted": sum(entry["status"] == "accepted" for entry in results),
                       "rejected": sum(entry["status"] == "rejected" for entry in results),
                       "release_gate": gate, "results": results})
        exit_code = int(bool(gate["infrastructure_failures"]) or (not args.diagnostic and not gate["passed"]))
    except Exception as error:
        report.update({"infrastructure_error": f"{type(error).__name__}: {error}",
                       "release_gate": {"passed": False, "reasons": [str(error)]}})
        exit_code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{'DIAGNOSTIC ONLY — NOT A RELEASE GATE' if args.diagnostic else 'RELEASE GATE'}: "
          f"{'PASS' if report['release_gate']['passed'] else 'FAIL'}")
    if "total" in report:
        print(f"{report['total']} files: {report['accepted']} accepted, {report['rejected']} rejected")
    for reason in report["release_gate"]["reasons"]:
        print(reason)
    for name in report["release_gate"].get("new_rejections", []):
        print(f"NEW/UNREVIEWED REJECTION: {name}")
    for name in report["release_gate"].get("formerly_rejected_accepted", []):
        print(f"FORMERLY REJECTED, NOW ACCEPTED: {name}")
    for name in report["release_gate"].get("valid_source_gaps", []):
        print(f"VALID-SOURCE GRAMMAR GAP: {name}")
    for name in report["release_gate"].get("infrastructure_failures", []):
        print(f"TIMEOUT/WORKER FAILURE: {name}")
    print(f"Per-file report: {args.report}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
