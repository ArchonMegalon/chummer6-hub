#!/usr/bin/env python3
"""Fail-closed preflight for the private Build Ghost/Rook compose profile."""

from __future__ import annotations

import argparse
import re
import stat
from pathlib import Path


_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def validate(image: str, env_file: Path) -> list[str]:
    reasons: list[str] = []
    if not _DIGEST.search(image.strip()):
        reasons.append("image-must-be-sha256-digest-pinned")

    try:
        resolved = env_file.resolve(strict=True)
    except FileNotFoundError:
        reasons.append("env-file-missing")
        return reasons
    if not env_file.is_absolute():
        reasons.append("env-file-must-be-absolute")
    if resolved.is_symlink() or not resolved.is_file():
        reasons.append("env-file-must-be-regular-file")
    else:
        mode = stat.S_IMODE(resolved.stat().st_mode)
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            reasons.append("env-file-must-not-be-group-or-world-accessible")
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--env-file", required=True, type=Path)
    args = parser.parse_args()
    reasons = validate(args.image, args.env_file)
    if reasons:
        for reason in reasons:
            print(reason)
        return 1
    print("rook-private-deployment-preflight: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
