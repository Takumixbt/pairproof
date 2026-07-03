import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sandbox"))

from run_checks import run_checks  # noqa: E402

GOOD_CODE = "def add(a, b):\n    return a + b\n"
GOOD_TEST = "from solution import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"

BAD_CODE = "def add(a, b):\n    return a - b\n"  # wrong logic -> pytest fails
BAD_TEST = GOOD_TEST

INSECURE_CODE = "import subprocess\n\ndef run(cmd):\n    return subprocess.call(cmd, shell=True)\n"
INSECURE_TEST = "from solution import run\n\ndef test_run():\n    assert run(['echo', 'hi']) == 0\n"


def test_good_bundle_passes():
    report = run_checks({"solution.py": GOOD_CODE, "test_solution.py": GOOD_TEST})
    assert report["overall_pass"] is True
    assert report["checks"]["pytest"]["exit_code"] == 0
    assert report["checks"]["pytest"]["summary"]["failed"] == 0


def test_bad_logic_fails_pytest():
    report = run_checks({"solution.py": BAD_CODE, "test_solution.py": BAD_TEST})
    assert report["overall_pass"] is False
    assert report["checks"]["pytest"]["exit_code"] != 0


def test_insecure_code_fails_bandit():
    report = run_checks({"solution.py": INSECURE_CODE, "test_solution.py": INSECURE_TEST})
    assert report["checks"]["bandit"]["exit_code"] != 0
    assert report["overall_pass"] is False


def test_bundle_hash_is_stable_and_content_sensitive():
    r1 = run_checks({"solution.py": GOOD_CODE, "test_solution.py": GOOD_TEST})
    r2 = run_checks({"solution.py": GOOD_CODE, "test_solution.py": GOOD_TEST})
    r3 = run_checks({"solution.py": BAD_CODE, "test_solution.py": BAD_TEST})
    assert r1["bundle_hash"] == r2["bundle_hash"]
    assert r1["bundle_hash"] != r3["bundle_hash"]
