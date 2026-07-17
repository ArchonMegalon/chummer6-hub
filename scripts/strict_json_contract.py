#!/usr/bin/env python3
"""Fail-closed JSON decoder for security and deployment contracts."""

from __future__ import annotations

import json
from typing import Any


class StrictJsonContractError(ValueError):
    """Raised when a contract is not an unambiguous UTF-8 JSON object."""


def strict_json_object(payload: bytes, *, label: str) -> dict[str, Any]:
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
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StrictJsonContractError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise StrictJsonContractError(f"{label} must contain a JSON object")
    return parsed
