#!/usr/bin/env python3
"""Invoke the owner-only Hub generation rollback API.

This client never edits the downloads shelf or current.json. It submits one
fully compare-and-swap-bound rollback request and writes only an immutable
operator receipt.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
from typing import Any, Optional, Sequence
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import quote, urlsplit


PUBLIC_ORIGIN = "https://chummer.run"
RECEIPT_CONTRACT = "chummer.release-shelf.rollback-operator-receipt/v1"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION_ID = re.compile(r"^auth-[0-9a-f]{64}$")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
MAX_SECRET_BYTES = 8192
MAX_RESPONSE_BYTES = 1024 * 1024


class RollbackClientError(RuntimeError):
    pass


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urlerror.HTTPError(req.full_url, code, msg, headers, fp)


def _arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare-and-swap the public Hub shelf to one retained generation. "
            "The owner token is read only from a caller-owned mode-0600 file."
        )
    )
    parser.add_argument("--target-generation", required=True)
    parser.add_argument("--expected-current-generation", required=True)
    parser.add_argument("--expected-current-snapshot-sha256", required=True)
    parser.add_argument("--expected-current-revision-id", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--base-url", default=PUBLIC_ORIGIN)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _safe_id(value: str, label: str) -> str:
    if SAFE_ID.fullmatch(value) is None or ".." in value:
        raise RollbackClientError(f"{label} must be a traversal-safe identifier")
    return value


def _request_payload(args: argparse.Namespace) -> dict[str, str]:
    target = _safe_id(args.target_generation, "target generation")
    current = _safe_id(
        args.expected_current_generation,
        "expected current generation",
    )
    if target == current:
        raise RollbackClientError(
            "target generation must differ from expected current generation"
        )
    if LOWER_SHA256.fullmatch(args.expected_current_snapshot_sha256) is None:
        raise RollbackClientError(
            "expected current snapshot digest must be lowercase SHA-256"
        )
    if REVISION_ID.fullmatch(args.expected_current_revision_id) is None:
        raise RollbackClientError("expected current revision ID is invalid")
    if IDEMPOTENCY_KEY.fullmatch(args.idempotency_key) is None:
        raise RollbackClientError(
            "idempotency key must be an 8-128 character portable token"
        )
    return {
        "targetGenerationId": target,
        "expectedCurrentGenerationId": current,
        "expectedCurrentSnapshotSha256": args.expected_current_snapshot_sha256,
        "expectedCurrentRevisionId": args.expected_current_revision_id,
        "idempotencyKey": args.idempotency_key,
    }


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _endpoint(base_url: str, generation_id: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "chummer.run"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise RollbackClientError(
            f"base URL must be the canonical owner endpoint {PUBLIC_ORIGIN}"
        )
    return (
        f"{PUBLIC_ORIGIN}/api/internal/releases/generations/"
        f"{quote(generation_id, safe='')}/rollback"
    )


def _read_owner_token(path: Optional[Path]) -> str:
    if path is None:
        raise RollbackClientError("--token-file is required unless --dry-run is used")
    if not path.is_absolute():
        raise RollbackClientError("owner token file path must be absolute")
    try:
        initial = os.lstat(path)
        if stat.S_ISLNK(initial.st_mode):
            raise RollbackClientError("owner token file must not be a symlink")
        parent = path.parent.resolve(strict=True)
        resolved = parent / path.name
        resolved_initial = os.lstat(resolved)
    except OSError as error:
        raise RollbackClientError("owner token file is unavailable") from error
    if (initial.st_dev, initial.st_ino) != (
        resolved_initial.st_dev,
        resolved_initial.st_ino,
    ):
        raise RollbackClientError("owner token path changed during resolution")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as error:
        raise RollbackClientError("owner token file could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if (
            (before.st_dev, before.st_ino)
            != (resolved_initial.st_dev, resolved_initial.st_ino)
            or
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or not 1 <= before.st_size <= MAX_SECRET_BYTES
        ):
            raise RollbackClientError(
                "owner token file must be caller-owned, single-link, regular, "
                "mode 0600, and bounded"
            )
        raw = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        item.st_mode,
        item.st_nlink,
    )
    if identity(before) != identity(after) or len(raw) != before.st_size:
        raise RollbackClientError("owner token file changed during stable read")
    try:
        final = os.lstat(resolved)
    except OSError as error:
        raise RollbackClientError("owner token file changed during stable read") from error
    if (final.st_dev, final.st_ino) != (after.st_dev, after.st_ino):
        raise RollbackClientError("owner token file changed during stable read")
    try:
        token = raw.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise RollbackClientError("owner token file must contain UTF-8") from error
    if not token or any(character.isspace() for character in token):
        raise RollbackClientError(
            "owner token must be one nonempty token without whitespace"
        )
    return token


def _strict_response(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        folded: set[str] = set()
        for key, value in pairs:
            normalized = key.casefold()
            if normalized in folded:
                raise RollbackClientError(
                    f"{label} contains duplicate or case-shadowed fields"
                )
            folded.add(normalized)
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RollbackClientError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise RollbackClientError(f"{label} must be a JSON object")
    return value


def _invoke(endpoint: str, body: bytes, token: str, timeout: int) -> dict[str, Any]:
    if timeout < 1 or timeout > 300:
        raise RollbackClientError("timeout must be between 1 and 300 seconds")
    request = urlrequest.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    opener = urlrequest.build_opener(
        _NoRedirect(),
        urlrequest.HTTPSHandler(context=ssl.create_default_context()),
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
    except urlerror.HTTPError as error:
        raw = error.read(MAX_RESPONSE_BYTES + 1)
        detail: Any
        try:
            detail = _strict_response(raw, "Hub rollback error response")
        except RollbackClientError:
            detail = {"status": error.code}
        raise RollbackClientError(
            f"Hub rollback rejected with HTTP {error.code}: "
            f"{json.dumps(detail, sort_keys=True, separators=(',', ':'))}"
        ) from error
    except (urlerror.URLError, TimeoutError, OSError) as error:
        raise RollbackClientError(
            "Hub rollback response is unknown; retry only with the same idempotency key"
        ) from error
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RollbackClientError("Hub rollback response exceeded its byte limit")
    if status != 200:
        raise RollbackClientError(f"Hub rollback returned unexpected HTTP {status}")
    return _strict_response(raw, "Hub rollback response")


def _receipt(
    endpoint: str,
    body: bytes,
    request: dict[str, str],
    response: Optional[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "contractName": RECEIPT_CONTRACT,
        "status": "dry_run" if dry_run else "submitted",
        "endpoint": endpoint,
        "requestSha256": hashlib.sha256(body).hexdigest(),
        "request": request,
        "response": response,
        "recordedAtUtc": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def _write_receipt(path: Optional[Path], receipt: dict[str, Any]) -> None:
    raw = _canonical_json(receipt) + b"\n"
    if path is None:
        sys.stdout.buffer.write(raw)
        return
    if not path.is_absolute():
        raise RollbackClientError("receipt output path must be absolute")
    if path.name.casefold() == "current.json":
        raise RollbackClientError("receipt output must not be named current.json")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise RollbackClientError("receipt output parent is unavailable") from error
    output = parent / path.name
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(output, flags, 0o600)
        try:
            os.write(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise RollbackClientError(
            "receipt output must be a new writable regular file"
        ) from error


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _arguments(argv)
    request = _request_payload(args)
    endpoint = _endpoint(args.base_url, request["targetGenerationId"])
    body = _canonical_json(request)
    if args.dry_run:
        response = None
    else:
        if args.output is None:
            raise RollbackClientError("--output is required for a live rollback")
        token = _read_owner_token(args.token_file)
        response = _invoke(endpoint, body, token, args.timeout)
    _write_receipt(
        args.output,
        _receipt(endpoint, body, request, response, args.dry_run),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RollbackClientError as error:
        print(f"rollback_release_generation.py: {error}", file=sys.stderr)
        raise SystemExit(2)
