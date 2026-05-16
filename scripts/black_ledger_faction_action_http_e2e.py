#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    parser.parse_args()
    result = subprocess.run(
        ["python3", "scripts/black_ledger_faction_action_runtime_e2e.py"],
        cwd="/docker/chummercomplete/chummer.run-services",
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
