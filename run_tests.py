#!/usr/bin/env python
"""Run all tests for the qtrading package."""
import sys
import subprocess


def run_tests():
    result = subprocess.run([
        sys.executable, "-m", "pytest",
        "qtrading/tests/",
        "-v",
        "--tb=short",
    ], capture_output=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())