#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Sequence


PASS = {"pass", "passed", "ready"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
CONTRACTS = {
    "desktop_visual": "chummer6-ui.desktop_visual_familiarity_exit_gate",
    "desktop_workflow": "chummer6-ui.desktop_workflow_execution_gate",
    "desktop_executable": "chummer6-ui.desktop_executable_exit_gate",
}


class ReceiptError(ValueError):
    pass


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize one candidate-bound Presentation receipt from passing source evidence."
    )
    parser.add_argument("--evidence-id", choices=sorted(CONTRACTS), required=True)
    parser.add_argument("--source-evidence", action="append", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--release-scope-decision", type=Path, required=True)
    parser.add_argument("--predecessor-snapshot", type=Path, required=True)
    parser.add_argument("--predecessor-decision", type=Path, required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _read(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    if not path.is_absolute():
        raise ReceiptError(f"{label} must be absolute")
    metadata = os.lstat(path)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
        or metadata.st_nlink != 1
        or not 1 <= metadata.st_size <= 8 * 1024 * 1024
    ):
        raise ReceiptError(f"{label} must be a stable caller-owned single-link file")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReceiptError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ReceiptError(f"{label} must be a JSON object")
    return raw, payload


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _contract(payload: dict[str, Any]) -> str:
    return str(payload.get("contractName") or payload.get("contract_name") or "").strip()


def _status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or payload.get("verdict") or "").strip().lower()


def _validate_sources(
    evidence_id: str,
    release_version: str,
    sources: Sequence[tuple[Path, bytes, dict[str, Any]]],
) -> None:
    if len({path.resolve() for path, _, _ in sources}) != len(sources):
        raise ReceiptError("source evidence paths must be distinct")
    for path, _, payload in sources:
        if _status(payload) not in PASS:
            raise ReceiptError(f"source evidence is not passing: {path}")
        for key in ("failures", "browserErrors", "collectionFailures"):
            if key in payload and payload[key] not in ([], None):
                raise ReceiptError(f"source evidence contains {key}: {path}")
        aliases = [
            payload[key]
            for key in ("releaseVersion", "release_version", "version")
            if key in payload and isinstance(payload[key], str)
        ]
        if aliases and any(value != release_version for value in aliases):
            raise ReceiptError(f"source evidence release version drifted: {path}")
    contracts = {_contract(payload) for _, _, payload in sources}
    if evidence_id == "desktop_visual":
        required = "chummer6-ui.desktop_visual_familiarity_exit_gate"
        if required not in contracts:
            raise ReceiptError("desktop visual source gate is missing")
    elif evidence_id == "desktop_workflow":
        if "chummer6-ui.clickable-surface-e2e" not in contracts:
            raise ReceiptError("desktop workflow requires the exhaustive clickable-surface receipt")
        click = next(payload for _, _, payload in sources if _contract(payload) == "chummer6-ui.clickable-surface-e2e")
        totals = click.get("totals")
        if not isinstance(totals, dict) or any(
            int(totals.get(key, 0)) != 0
            for key in ("failed", "failures", "skipped")
            if key in totals
        ):
            raise ReceiptError("clickable-surface totals are not clean")
    else:
        if "chummer6-ui.unsigned-preview-windows-installer-visual-proof" not in contracts:
            raise ReceiptError("desktop executable requires Windows installer visual proof")
        if not any(
            payload.get("platform") == "windows"
            and payload.get("rid") == "win-x64"
            and payload.get("releaseVersion") == release_version
            for _, _, payload in sources
        ):
            raise ReceiptError("desktop executable requires bound Windows startup evidence")


def main() -> int:
    args = _args()
    try:
        manifest_raw, manifest = _read(args.manifest, "candidate manifest")
        scope_raw, scope = _read(args.release_scope_decision, "approved release scope")
        snapshot_raw, snapshot = _read(args.predecessor_snapshot, "predecessor snapshot")
        decision_raw, decision = _read(args.predecessor_decision, "predecessor decision")
        sources = [
            (path, *_read(path, f"source evidence {index}"))
            for index, path in enumerate(args.source_evidence)
        ]
        release_version = str(manifest.get("version") or manifest.get("releaseVersion") or "")
        if not release_version or scope.get("releaseVersion") != release_version:
            raise ReceiptError("manifest and approved scope release versions disagree")
        manifest_sha = _sha(manifest_raw)
        decision_sha = _sha(decision_raw)
        snapshot_sha = _sha(snapshot_raw)
        if (
            scope.get("contractName") != "chummer.release-scope-decision/v1"
            or scope.get("status") != "approved"
            or snapshot.get("releaseVersion") != release_version
            or snapshot.get("status") != "published"
            or snapshot.get("releaseDecisionStatus") != "review_required"
            or snapshot.get("manifestSha256") != manifest_sha
            or snapshot.get("releaseDecisionSha256") != decision_sha
            or decision.get("status") != "review_required"
        ):
            raise ReceiptError("candidate authority envelope is inconsistent")
        registry_commit = str(snapshot.get("registryCommit") or "")
        if GIT_SHA.fullmatch(registry_commit) is None:
            raise ReceiptError("candidate Registry commit is invalid")
        platform = args.platform.strip().lower()
        rows = scope.get("platforms")
        row = next(
            (item for item in rows if isinstance(item, dict) and item.get("platform") == platform),
            None,
        ) if isinstance(rows, list) else None
        if row is None:
            raise ReceiptError("selected Presentation platform is outside approved scope")
        required_heads = [row.get("primaryHead"), *(row.get("fallbackHeads") or [])]
        artifacts = snapshot.get("artifacts")
        observed = {
            item.get("head")
            for item in artifacts
            if isinstance(item, dict)
            and item.get("platform") == platform
            and item.get("rid") == row.get("rid")
        } if isinstance(artifacts, list) else set()
        if observed != set(required_heads) or snapshot.get("primaryHeadByPlatform", {}).get(platform) != row.get("primaryHead"):
            raise ReceiptError("candidate snapshot does not cover the selected Presentation scope")
        _validate_sources(args.evidence_id, release_version, sources)
        payload = {
            "contract_name": CONTRACTS[args.evidence_id],
            "contract_version": 1,
            "status": "pass",
            "releaseVersion": release_version,
            "release_version": release_version,
            "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "evidence_id": args.evidence_id,
            "source_evidence": [
                {"fileName": path.name, "sha256": _sha(raw)}
                for path, raw, _ in sources
            ],
            "campaign_operability_candidate_binding": {
                "contract_name": "chummer6-ui.campaign_operability_candidate_binding",
                "contract_version": 1,
                "release_version": release_version,
                "release_scope_decision_sha256": _sha(scope_raw),
                "manifest_sha256": manifest_sha,
                "authority_snapshot_sha256": snapshot_sha,
                "release_decision_sha256": decision_sha,
                "registry_commit": registry_commit,
                "platform": platform,
                "rid": row.get("rid"),
                "primary_head": row.get("primaryHead"),
                "required_heads": required_heads,
            },
        }
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ReceiptError) as error:
        print(f"candidate Presentation receipt failed: {error}", file=os.sys.stderr)
        return 1
    print("candidate_presentation_receipt:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
