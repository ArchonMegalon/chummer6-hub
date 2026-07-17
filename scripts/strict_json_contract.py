#!/usr/bin/env python3
"""Fail-closed JSON decoder for security and deployment contracts."""

from __future__ import annotations

import json
import math
from typing import Any


class StrictJsonContractError(ValueError):
    """Raised when a contract is not an unambiguous UTF-8 JSON object."""


DEFAULT_STRICT_JSON_MAX_DEPTH = 128


def _validate_json_value(
    value: Any,
    *,
    label: str,
    max_depth: int,
) -> None:
    if max_depth < 1:
        raise ValueError("strict JSON max_depth must be positive")

    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if depth > max_depth:
            raise StrictJsonContractError(
                f"{label} exceeds the maximum JSON nesting depth"
            )
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise StrictJsonContractError(
                f"{label} contains a non-finite JSON number"
            )


def strict_json_object(
    payload: bytes,
    *,
    label: str,
    max_depth: int = DEFAULT_STRICT_JSON_MAX_DEPTH,
) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for key, value in pairs:
            if key in parsed:
                raise StrictJsonContractError(
                    f"{label} contains a duplicate JSON field"
                )
            parsed[key] = value
        return parsed

    def reject_nonfinite(_value: str) -> None:
        raise StrictJsonContractError(
            f"{label} contains a non-finite JSON number"
        )

    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_nonfinite,
        )
    except StrictJsonContractError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        OverflowError,
        RecursionError,
    ) as exc:
        raise StrictJsonContractError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise StrictJsonContractError(f"{label} must contain a JSON object")
    _validate_json_value(parsed, label=label, max_depth=max_depth)
    return parsed


def canonical_json_bytes(
    payload: dict[str, Any],
    *,
    label: str,
    max_depth: int = DEFAULT_STRICT_JSON_MAX_DEPTH,
) -> bytes:
    """Render one deterministic, depth-bounded JSON object with a trailing newline."""

    _validate_json_value(payload, label=label, max_depth=max_depth)
    try:
        return (
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise StrictJsonContractError(
            f"{label} cannot be rendered as canonical JSON"
        ) from exc
