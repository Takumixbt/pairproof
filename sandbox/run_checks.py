"""Runs an untrusted code+test bundle through pytest, ruff, and bandit, and
emits a structured verification report as JSON.

Runs standalone (reads a bundle JSON from stdin, writes a report JSON to
stdout) so it can be the entrypoint of a locked-down Docker container with no
network access. Also importable directly (`run_checks`) for local unit tests
against known-good/known-bad samples without needing Docker.

Bundle format (stdin / `files` arg): {"files": {"<relative path>": "<content>"}}
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TIMEOUT_SECONDS = 30
MAX_LOG_CHARS = 4000


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
        log = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, log[:MAX_LOG_CHARS]
    except subprocess.TimeoutExpired:
        return -1, f"TIMEOUT after {TIMEOUT_SECONDS}s"
    except FileNotFoundError as e:
        return -2, f"tool not found: {e}"


def _pytest_summary(log: str) -> dict:
    m = re.search(r"(\d+) passed(?:, (\d+) failed)?", log)
    if not m:
        m = re.search(r"(\d+) failed", log)
        if m:
            return {"passed": 0, "failed": int(m.group(1))}
        return {"passed": None, "failed": None}
    return {"passed": int(m.group(1)), "failed": int(m.group(2) or 0)}


def _is_test_file(rel_path: str) -> bool:
    name = Path(rel_path).name
    return name.startswith("test_") or name.endswith("_test.py")


def run_checks(files: dict[str, str]) -> dict:
    if not files:
        raise ValueError("bundle has no files")

    bundle_hash = hashlib.sha256(
        json.dumps(files, sort_keys=True).encode("utf-8")
    ).hexdigest()

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        source_paths: list[str] = []
        for rel_path, content in files.items():
            dest = workdir / rel_path
            if workdir not in dest.resolve().parents:
                raise ValueError(f"path escapes workdir: {rel_path}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            if not _is_test_file(rel_path):
                source_paths.append(rel_path)

        pytest_code, pytest_log = _run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short"], workdir,
        )
        ruff_code, ruff_log = _run(
            [sys.executable, "-m", "ruff", "check", "."], workdir,
        )
        # Bandit only scans non-test source files: assert (B101) is normal
        # pytest practice in test files, not a security issue there.
        if source_paths:
            bandit_code, bandit_log = _run(
                [sys.executable, "-m", "bandit", "-q", *source_paths], workdir,
            )
        else:
            bandit_code, bandit_log = 0, "no non-test source files to scan"

    pytest_summary = _pytest_summary(pytest_log)
    overall_pass = pytest_code == 0 and bandit_code == 0

    report = {
        "bundle_hash": bundle_hash,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": {
            "pytest": {"exit_code": pytest_code, "summary": pytest_summary, "log": pytest_log},
            "ruff": {"exit_code": ruff_code, "log": ruff_log},
            "bandit": {"exit_code": bandit_code, "log": bandit_log},
        },
        "overall_pass": overall_pass,
    }
    return report


def main() -> None:
    payload = json.loads(sys.stdin.read())
    files = payload.get("files") or {}
    report = run_checks(files)
    sys.stdout.write(json.dumps(report))


if __name__ == "__main__":
    main()
