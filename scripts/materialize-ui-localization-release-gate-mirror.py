#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any


def canonical_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(candidate)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base URL must be an absolute credential-free HTTPS origin")
    return urllib.parse.urlunsplit(("https", parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def materialize_payload(source: Path, base_url: str) -> dict[str, Any]:
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("UI localization release gate must be a JSON object")
    status = str(payload.get("status") or "").strip().lower()
    if status not in {"pass", "passed", "ready"}:
        raise ValueError("UI localization release gate must have passing status")
    generated_at = payload.get("generatedAt") or payload.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        raise ValueError("UI localization release gate must include generatedAt/generated_at")

    for key in ("localReleaseProof", "local_release_proof"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested["baseUrl"] = base_url
            nested["base_url"] = base_url
    return payload


def atomic_write_if_changed(path: Path, content: bytes) -> bool:
    if path.is_file() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="https://chummer.run")
    args = parser.parse_args()

    base_url = canonical_base_url(args.base_url)
    payload = materialize_payload(args.source, base_url)
    content = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    changed = atomic_write_if_changed(args.output, content)
    print(f"ui_localization_release_gate_mirror:{'updated' if changed else 'unchanged'}:{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
