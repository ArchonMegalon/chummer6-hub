#!/usr/bin/env python3
"""Reject authoritative release updates that silently remove desktop tuples."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


INSTALL_MEDIA_KINDS = {"installer", "dmg", "pkg", "msix"}
PLATFORM_ALIASES = {
    "linux": "linux",
    "windows": "windows",
    "win": "windows",
    "mac": "macos",
    "macos": "macos",
    "osx": "macos",
}
SAFE_SCOPE_TOKEN = re.compile(r"^[a-z0-9._+\-]{1,64}$")


class ReplacementVerificationError(ValueError):
    """Raised when replacement truth is unavailable, malformed, or shrinking."""


def normalize_token(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_platform(value: Any) -> str:
    token = normalize_token(value)
    return PLATFORM_ALIASES.get(token, token)


def canonical_manifest_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    path = parsed.path.rstrip("/")
    if path.lower().endswith(".json"):
        return value
    if not path:
        path = "/downloads/RELEASE_CHANNEL.generated.json"
    elif path.lower().endswith("/downloads"):
        path += "/RELEASE_CHANNEL.generated.json"
    else:
        path += "/RELEASE_CHANNEL.generated.json"
    return urllib.parse.urlunparse(parsed._replace(path=path, query="", fragment=""))


def load_manifest(source: str, *, allow_missing: bool) -> dict[str, Any] | None:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in {"http", "https"}:
        url = canonical_manifest_url(source)
        request = urllib.request.Request(url, headers={"User-Agent": "chummer-release-shelf-preflight/1"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8-sig")
        except urllib.error.HTTPError as error:
            if error.code == 404 and allow_missing:
                return None
            raise ReplacementVerificationError(
                f"could not read existing canonical release manifest {url}: HTTP {error.code}"
            ) from error
        except (OSError, UnicodeError) as error:
            raise ReplacementVerificationError(
                f"could not read existing canonical release manifest {url}: {error}"
            ) from error
    else:
        path = Path(source)
        if not path.is_file():
            if allow_missing:
                return None
            raise ReplacementVerificationError(f"canonical release manifest does not exist: {path}")
        try:
            raw = path.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise ReplacementVerificationError(f"could not read canonical release manifest {path}: {error}") from error

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ReplacementVerificationError(f"canonical release manifest is not valid JSON: {source}: {error}") from error
    if not isinstance(payload, dict):
        raise ReplacementVerificationError(f"canonical release manifest must contain a JSON object: {source}")
    artifacts = payload.get("artifacts")
    if artifacts is not None and not isinstance(artifacts, list):
        raise ReplacementVerificationError(f"canonical release manifest artifacts must be a list: {source}")
    return payload


def artifact_file_name(artifact: dict[str, Any]) -> str:
    direct = Path(str(artifact.get("fileName") or "").strip()).name
    if direct:
        return direct
    return Path(str(artifact.get("downloadUrl") or "").strip()).name


def desktop_install_tuples(
    payload: dict[str, Any],
    *,
    selected_file_names: set[str] | None = None,
) -> set[str]:
    artifacts = payload.get("artifacts") or []
    tuples: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ReplacementVerificationError(f"canonical artifact row {index} must be a JSON object")
        kind = normalize_token(artifact.get("kind"))
        if kind not in INSTALL_MEDIA_KINDS:
            continue
        file_name = artifact_file_name(artifact)
        if selected_file_names is not None and file_name not in selected_file_names:
            continue
        head = normalize_token(artifact.get("head"))
        platform = normalize_platform(artifact.get("platform"))
        rid = normalize_token(artifact.get("rid") or artifact.get("runtimeIdentifier"))
        if not head or not platform or not rid or not file_name:
            raise ReplacementVerificationError(
                f"canonical install artifact row {index} is missing head/platform/rid/fileName"
            )
        tuples.add(f"{head}:{platform}:{rid}")
    return tuples


def normalize_exact_incoming_tuples(values: list[str] | None) -> set[str] | None:
    if values is None:
        return None
    if not values:
        raise ReplacementVerificationError("exact incoming scope must declare at least one desktop tuple")
    if len(values) > 32 or len(",".join(str(value) for value in values)) > 4096:
        raise ReplacementVerificationError(
            "exact incoming scope exceeds the 32-tuple or 4096-character limit"
        )

    normalized: set[str] = set()
    for raw_value in values:
        parts = [normalize_token(part) for part in str(raw_value).split(":")]
        if len(parts) != 3 or not all(parts):
            raise ReplacementVerificationError(
                "exact incoming desktop tuple must use head:platform:rid: " + str(raw_value)
            )
        head, platform, rid = parts
        platform = normalize_platform(platform)
        if not all(SAFE_SCOPE_TOKEN.fullmatch(token) for token in (head, platform, rid)):
            raise ReplacementVerificationError(
                "exact incoming desktop tuple contains an invalid token: " + str(raw_value)
            )
        canonical = f"{head}:{platform}:{rid}"
        if canonical in normalized:
            raise ReplacementVerificationError(
                "exact incoming desktop tuple was declared more than once: " + canonical
            )
        normalized.add(canonical)
    return normalized


def verify_replacement(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any],
    *,
    selected_file_names: set[str] | None = None,
    exact_incoming_tuples: set[str] | None = None,
) -> tuple[set[str], set[str]]:
    existing_tuples = desktop_install_tuples(existing or {})
    incoming_tuples = desktop_install_tuples(incoming, selected_file_names=selected_file_names)
    if exact_incoming_tuples is not None:
        if not exact_incoming_tuples:
            raise ReplacementVerificationError(
                "exact incoming scope must declare at least one desktop tuple"
            )
        missing_from_incoming = exact_incoming_tuples - incoming_tuples
        undeclared_incoming = incoming_tuples - exact_incoming_tuples
        if missing_from_incoming or undeclared_incoming:
            details: list[str] = []
            if missing_from_incoming:
                details.append("missing " + ", ".join(sorted(missing_from_incoming)))
            if undeclared_incoming:
                details.append("undeclared " + ", ".join(sorted(undeclared_incoming)))
            raise ReplacementVerificationError(
                "incoming desktop install tuples do not match the explicitly declared exact scope: "
                + "; ".join(details)
            )
        return existing_tuples, incoming_tuples

    missing = existing_tuples - incoming_tuples
    if missing:
        raise ReplacementVerificationError(
            "incoming authoritative release bundle would drop existing desktop install tuple(s): "
            + ", ".join(sorted(missing))
            + ". Scoped updates and explicit removals are not supported yet; publish a complete shelf."
        )
    return existing_tuples, incoming_tuples


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", required=True, help="Existing canonical manifest path or URL.")
    parser.add_argument("--incoming", required=True, help="Incoming canonical manifest path.")
    parser.add_argument(
        "--selected-files-dir",
        type=Path,
        help="Optional filtered files directory; incoming tuples without selected bytes do not count.",
    )
    parser.add_argument(
        "--allow-missing-existing",
        action="store_true",
        help="Allow an absent local manifest or HTTP 404 as a first-shelf publication.",
    )
    exact_scope = parser.add_mutually_exclusive_group()
    exact_scope.add_argument(
        "--exact-incoming-tuple",
        action="append",
        help=(
            "Declare the complete incoming desktop scope as head:platform:rid. Repeat once per tuple. "
            "When present, intentionally retired existing tuples are allowed only if incoming truth "
            "matches this exact non-empty scope."
        ),
    )
    exact_scope.add_argument(
        "--exact-incoming-scope",
        help=(
            "Comma-separated transport form of the complete head:platform:rid scope. "
            "This is intended for governed shell publishers; empty, malformed, and duplicate "
            "tuples fail closed."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        existing = load_manifest(args.existing, allow_missing=args.allow_missing_existing)
        incoming = load_manifest(args.incoming, allow_missing=False)
        assert incoming is not None
        selected_file_names: set[str] | None = None
        if args.selected_files_dir is not None:
            if not args.selected_files_dir.is_dir():
                raise ReplacementVerificationError(
                    f"selected files directory does not exist: {args.selected_files_dir}"
                )
            selected_file_names = {
                path.name for path in args.selected_files_dir.iterdir() if path.is_file()
            }
        exact_incoming_values = args.exact_incoming_tuple
        if args.exact_incoming_scope is not None:
            exact_incoming_values = args.exact_incoming_scope.split(",")
        existing_tuples, incoming_tuples = verify_replacement(
            existing,
            incoming,
            selected_file_names=selected_file_names,
            exact_incoming_tuples=normalize_exact_incoming_tuples(exact_incoming_values),
        )
    except ReplacementVerificationError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(
        "release shelf replacement preflight passed "
        f"(existing tuples={len(existing_tuples)}, incoming tuples={len(incoming_tuples)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
