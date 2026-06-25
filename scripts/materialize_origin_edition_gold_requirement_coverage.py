#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")
CONTRACT_NAME = "chummer.origin_edition.gold_requirement_coverage.v1"

REQUIREMENTS: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "approved_sample_runner_canon_only",
        "Approved fictional sample runner canon packet, consent, and Chummer canon authority",
        ("chummer_canon_authority_verified", "source_packet_integrity_and_consent_verified"),
        ("approved_sources_only", "source_packet_integrity_and_consent_verified"),
    ),
    (
        "provider_story_and_humanizer_pipeline",
        "Story/manuscript generation and Undetectable Humanizer post-step are proved",
        ("story_generation_receipt", "provider_manuscript_file", "undetectable_humanizer_receipt", "humanizer_quality_receipt"),
        (),
    ),
    (
        "canon_privacy_audit",
        "Canon/privacy audit passed with no hard conflicts or privacy findings",
        ("canon_privacy_audit", "chummer_canon_authority_verified"),
        (),
    ),
    (
        "cover_consistency_all_surfaces",
        "Same rendered story-scene cover is used across Chummer, ebook, PDF, M4B, Audiobookshelf, and movie",
        ("cover_generation_receipt", "cover_consistency_receipt", "cover_consistency_required_surfaces"),
        ("same_cover_sha_bound",),
    ),
    (
        "ebook_pdf_dossier_packaging",
        "Ebook/PDF dossier package is hash-bound and imported under the Origin dossier branch",
        ("ebook_import_receipt", "ebook_artifact_file", "ebook_artifact_namespace", "dossier_ebook_pdf_packaging_verified"),
        ("dossier_ebook_pdf_packaging_verified",),
    ),
    (
        "m4b_premium_audiobook_packaging",
        "M4B audiobook uses verified Inkfluence or Unmixr premium narration, no fallback audio, and the approved cover/manuscript",
        ("m4b_provider_receipt", "m4b_artifact_file", "m4b_artifact_namespace", "m4b_premium_narration_import_verified"),
        ("m4b_premium_narration_import_verified", "no_fallback_audio"),
    ),
    (
        "audiobookshelf_dossier_and_audiobook_share",
        "Audiobookshelf hosts and shares both ebook dossier and M4B audiobook",
        ("audiobookshelf_import_receipt", "audiobookshelf_import_receipt_namespace", "audiobookshelf_dossier_and_audiobook_share_verified"),
        ("audiobookshelf_dossier_and_audiobook_shared",),
    ),
    (
        "movie_story_scene_playback",
        "Chummer media hosts a real story-scene movie with selected-face cover and approved premium narration audio",
        ("movie_generation_receipt", "movie_artifact_file", "movie_artifact_namespace", "chummer_movie_story_scene_playback_verified"),
        ("chummer_movie_story_scene_playback_verified",),
    ),
    (
        "local_authenticated_chummer_route",
        "Local authenticated Chummer page exposes Read, Listen, Watch, Canon Audit, cover, and book routes",
        ("local_authenticated_chummer_route", "local_authenticated_route_tabs_verified"),
        ("local_authenticated_route_tabs_verified",),
    ),
    (
        "runsite_handoff_constraints",
        "RunSite handoff constraints, newest LTD/env inspection, Rybbit env-only wiring, and no-deploy posture are proved",
        ("runsite_integration_proof", "runsite_handoff_constraints_verified"),
        ("runsite_handoff_constraints_verified",),
    ),
    (
        "telegram_origin_links",
        "EA Telegram sent read, listen, watch, and open-in-Chummer links",
        ("telegram_delivery_receipt", "telegram_origin_links_verified"),
        (),
    ),
    (
        "no_fallback_no_sentinel_no_direct_publish_no_secrets",
        "No fallback/sentinel media, no direct provider publishing, and no committed/generated secrets are proved",
        ("final_no_fallback_no_sentinel_audit", "final_bundle_no_fallback_no_sentinel_verified", "secret_hygiene_verified", "provider_publish_boundary_verified"),
        ("no_provider_direct_publish", "no_committed_or_receipt_secrets_claimed"),
    ),
    (
        "deployed_owner_read_listen_watch_canon",
        "Deployed owner can log into Chummer, see cover, read, listen, watch, and verify Canon Audit",
        ("deployed_user_login_read_listen_watch",),
        ("gold_audit_completion_claim_allowed",),
    ),
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_statuses(matrix: dict[str, Any]) -> dict[str, str]:
    rows = matrix.get("rows") if isinstance(matrix.get("rows"), list) else []
    return {
        str(row.get("id")): str(row.get("status") or "")
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }


def materialize(evidence_root: Path, output: Path) -> dict[str, Any]:
    evidence_root = evidence_root.resolve()
    matrix_path = evidence_root / "ORIGIN_EDITION_GOLD_COMPLETION_MATRIX.generated.json"
    proof_chain_path = evidence_root / "ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json"
    matrix = read_json(matrix_path)
    proof_chain = read_json(proof_chain_path)
    rows = row_statuses(matrix)
    hard_gates = matrix.get("hardGates") if isinstance(matrix.get("hardGates"), dict) else {}

    requirement_results: list[dict[str, Any]] = []
    for requirement_id, label, row_ids, hard_gate_ids in REQUIREMENTS:
        missing_rows = [row_id for row_id in row_ids if row_id not in rows]
        blocked_rows = [row_id for row_id in row_ids if rows.get(row_id) != "proved"]
        missing_hard_gates = [gate for gate in hard_gate_ids if gate not in hard_gates]
        blocked_hard_gates = [gate for gate in hard_gate_ids if hard_gates.get(gate) is not True]
        status = "proved" if not missing_rows and not blocked_rows and not missing_hard_gates and not blocked_hard_gates else "blocked"
        requirement_results.append(
            {
                "id": requirement_id,
                "label": label,
                "status": status,
                "rowIds": list(row_ids),
                "hardGateIds": list(hard_gate_ids),
                "missingRows": missing_rows,
                "blockedRows": blocked_rows,
                "missingHardGates": missing_hard_gates,
                "blockedHardGates": blocked_hard_gates,
            }
        )

    blocked = [item["id"] for item in requirement_results if item["status"] != "proved"]
    passed = not blocked
    next_action = (
        "Gold requirement coverage is complete. Keep the artifacts archived outside providers."
        if passed
        else str(proof_chain.get("next_action") or "Resolve blocked requirements and rerun the strict Gold verifier.").strip()
    )
    blocking_reason = "" if passed else ",".join(f"requirement:{item}" for item in blocked)
    progress = {
        "provedRequirements": len(requirement_results) - len(blocked),
        "totalRequirements": len(requirement_results),
        "blockedRequirements": blocked,
    }
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "updated_at": now_iso(),
        "status": "pass" if passed else "blocked",
        "goalCompletionClaimAllowed": passed and proof_chain.get("goalCompletionClaimAllowed") is True,
        "next_action": next_action,
        "blocking_reason": blocking_reason,
        "progress": progress,
        "matrixPath": matrix_path.as_posix(),
        "matrixSha256": sha256_file(matrix_path),
        "proofChainPath": proof_chain_path.as_posix(),
        "proofChainSha256": sha256_file(proof_chain_path),
        "blockedRequirements": blocked,
        "requirements": requirement_results,
        "privacy": {
            "rawCredentialExposed": False,
            "rawSessionTokenExposed": False,
            "envValuesExposed": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Origin Edition Gold requirement coverage.")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output or args.evidence_root / "ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json"
    payload = materialize(args.evidence_root, output)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
