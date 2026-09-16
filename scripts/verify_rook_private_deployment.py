#!/usr/bin/env python3
"""Fail-closed preflight for the private Build Ghost/Rook compose profile."""

from __future__ import annotations

import argparse
import re
import stat
from pathlib import Path


_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_REQUIRED_ENV = {
    "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_ENDPOINT",
    "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_AUTH_AUDIENCE",
    "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_AUTHORITY_ENDPOINT",
    "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN",
}


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
        values: dict[str, str] = {}
        for line in resolved.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
        for key in sorted(_REQUIRED_ENV):
            if not values.get(key):
                reasons.append(f"env-missing-{key.lower()}")
        if len(values.get("CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN", "")) < 32:
            reasons.append("env-private-tool-service-token-too-short")
        if not values.get("CHUMMER_AI_INTERNAL_API_TOKEN") and not values.get("FLEET_INTERNAL_API_TOKEN"):
            reasons.append("env-internal-api-token-missing")
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
