from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_FIRSTBOOK_FORBIDDEN_MATERIAL = {
    "sourcebook copied prose",
    "private runner data",
    "GM-only campaign secrets",
    "unproven release claims",
}


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean value, got {value!r}")


def parse_iso_utc(value: str) -> str:
    text = value.strip()
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    content = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    if path is None:
        print(content, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_mapping(items: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in items:
        key, separator, value = item.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"expected KEY=VALUE mapping, got {item!r}")
        mapping[key.strip()] = value.strip()
    return mapping


def parse_sources(items: list[str]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for item in items:
        path_text, authority, classification = [part.strip() for part in item.split("|", 2)]
        source_path = Path(path_text)
        if not source_path.is_file():
            raise FileNotFoundError(f"source file not found: {source_path}")
        if not authority:
            raise ValueError(f"source authority is required: {item!r}")
        if classification not in {"public", "campaign_safe", "private"}:
            raise ValueError(f"unsupported source classification: {classification!r}")
        sources.append(
            {
                "path": str(source_path),
                "authority": authority,
                "sha256": sha256_file(source_path),
                "classification": classification,
            }
        )
    if not sources:
        raise ValueError("at least one source is required")
    return sources


def normalize_claims(items: list[str]) -> list[str]:
    claims = [item.strip() for item in items if item.strip()]
    if not claims:
        raise ValueError("at least one claim is required")
    return claims


def approval_block(
    *,
    human_review_required: bool,
    gm_approval_required: bool,
    player_approval_required: bool,
    publication_allowed: bool,
) -> dict[str, bool]:
    return {
        "human_review_required": human_review_required,
        "gm_approval_required": gm_approval_required,
        "player_approval_required": player_approval_required,
        "publication_allowed": publication_allowed,
    }


def private_data_block(
    *,
    contains_private_runner: bool,
    contains_gm_secret: bool,
    contains_sourcebook_prose: bool,
) -> dict[str, bool]:
    return {
        "contains_private_runner": contains_private_runner,
        "contains_gm_secret": contains_gm_secret,
        "contains_sourcebook_prose": contains_sourcebook_prose,
    }


def packet_private_data_is_safe(packet: dict[str, Any]) -> bool:
    private_data = packet.get("private_data") or {}
    return not any(bool(private_data.get(key)) for key in private_data)


def detect_missing_required_claims(script_text: str, allowed_claims: list[str]) -> list[str]:
    lowered = script_text.lower()
    return [claim for claim in allowed_claims if claim.lower() not in lowered]


def detect_forbidden_claims(script_text: str, forbidden_claims: list[str]) -> list[str]:
    lowered = script_text.lower()
    return [claim for claim in forbidden_claims if claim.lower() in lowered]


def validate_firstbook_forbidden_material(items: list[str]) -> list[str]:
    normalized = [item.strip() for item in items if item.strip()]
    missing = [
        required
        for required in sorted(REQUIRED_FIRSTBOOK_FORBIDDEN_MATERIAL)
        if required not in normalized
    ]
    if missing:
        raise ValueError(
            "firstbook forbidden material is missing required entries: "
            + ", ".join(missing)
        )
    return normalized


def require_existing_file(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_file():
        raise FileNotFoundError(f"file not found: {path}")
    return path


def parse_chapter_specs(items: list[str]) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for item in items:
        number_text, title, path_text, review_status = [part.strip() for part in item.split("|", 3)]
        path = require_existing_file(path_text)
        chapter_number = int(number_text)
        chapters.append(
            {
                "chapter": chapter_number,
                "title": title,
                "markdown_path": str(path),
                "markdown_sha256": sha256_file(path),
                "review_status": review_status,
            }
        )
    if not chapters:
        raise ValueError("at least one chapter is required")
    return sorted(chapters, key=lambda item: int(item["chapter"]))


def parse_export_specs(items: list[str]) -> dict[str, dict[str, str]]:
    exports: dict[str, dict[str, str]] = {}
    for item in items:
        export_format, path_text = [part.strip() for part in item.split("|", 1)]
        path = require_existing_file(path_text)
        exports[export_format] = {
            "path": str(path),
            "sha256": sha256_file(path),
        }
    return exports
