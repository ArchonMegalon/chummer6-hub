#!/usr/bin/env python3
"""Fail closed unless a release bundle carries exact governed Mac provenance."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_root", type=Path)
    args = parser.parse_args()
    support_path = Path(__file__).resolve().with_name("build_provenance_support.py")
    spec = importlib.util.spec_from_file_location("chummer_release_bundle_provenance_support", support_path)
    if spec is None or spec.loader is None:
        print(f"build provenance support is unavailable: {support_path}", file=sys.stderr)
        return 1
    support = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = support
    spec.loader.exec_module(support)
    failures = support.validate_release_bundle_build_provenance(args.bundle_root)
    for failure in failures:
        print(f"build_provenance_bundle_failure={failure}", file=sys.stderr)
    if failures:
        return 1
    print("build_provenance_bundle=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
