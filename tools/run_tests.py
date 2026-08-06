#!/usr/bin/env python3
"""Run the pipeline unit-test suite (stdlib unittest, no deps).

    python3 tools/run_tests.py

Discovers tools/tests/test_*.py and reports a pass/fail summary. Exits
non-zero if any test fails, so it can gate CI / pre-commit.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))


def main():
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(HERE, "tests"), pattern="test_*.py",
                            top_level_dir=HERE)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
