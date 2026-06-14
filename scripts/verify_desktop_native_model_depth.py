#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
CHUMMER_UI_ROOT = Path(os.environ.get("CHUMMER_UI_ROOT", "/docker/chummercomplete/chummer6-ui"))
OUTPUT_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "DESKTOP_NATIVE_MODEL_DEPTH.generated.json"
REALITY_AUDIT_PATH = CHUMMER_UI_ROOT / ".codex-studio" / "published" / "CLASSIC_FORMPORT_REALITY_AUDIT.generated.json"
BRIDGE_PATH = CHUMMER_UI_ROOT / "Chummer.Avalonia" / "Controls" / "ClassicFormPorts" / "ClassicFormPortViewModelBridge.cs"
SECTION_HOST_PATH = CHUMMER_UI_ROOT / "Chummer.Avalonia" / "Controls" / "SectionHostControl.axaml.cs"

GENERIC_BLOCKERS = {
    "bridge_create_from_rows_signature": "CreateFromRows(IReadOnlyList<SectionRowDisplayItem> rows)",
    "bridge_from_rows_signature": "FromRows(IReadOnlyList<SectionRowDisplayItem> rows)",
    "section_host_row_record": "public sealed record SectionRowDisplayItem(string Path, string Value)",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    reality_payload = load_json(REALITY_AUDIT_PATH)
    bridge_text = read_text(BRIDGE_PATH)
    section_host_text = read_text(SECTION_HOST_PATH)

    marker_hits = {
        name: marker in (bridge_text if "bridge_" in name else section_host_text)
        for name, marker in GENERIC_BLOCKERS.items()
    }
    classic_line_item_count = bridge_text.count("IReadOnlyList<ClassicPortLineItem>")
    bucket_call_count = bridge_text.count("Bucket(")
    key_snapshot_count = bridge_text.count("Snapshot(")
    reality_status = str(reality_payload.get("status") or "missing").strip().lower()

    failures: list[str] = []
    if reality_status not in {"pass", "passed", "ready"}:
        failures.append("classic_formport_reality_audit is not passing")
    if marker_hits["bridge_create_from_rows_signature"]:
        failures.append("desktop flagship bridge still creates domain state directly from SectionRowDisplayItem rows")
    if marker_hits["bridge_from_rows_signature"]:
        failures.append("desktop flagship bridge still derives row facts from generic SectionRowDisplayItem rows")
    if classic_line_item_count >= 12:
        failures.append(f"desktop flagship bridge still exposes {classic_line_item_count} ClassicPortLineItem list surfaces")
    if bucket_call_count >= 3 and key_snapshot_count >= 1:
        failures.append("desktop flagship bridge still buckets generic row facts instead of typed workflow models")

    result = {
        "contract_name": "chummer.desktop_native_model_depth",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": "DESKTOP_NATIVE_MODEL_READY" if not failures else "DESKTOP_NATIVE_MODEL_REVIEW_REQUIRED",
        "inputs": {
            "classic_formport_reality_audit_path": str(REALITY_AUDIT_PATH),
            "bridge_path": str(BRIDGE_PATH),
            "section_host_path": str(SECTION_HOST_PATH),
        },
        "source_markers": {
            **marker_hits,
            "classic_port_line_item_list_count": classic_line_item_count,
            "bucket_call_count": bucket_call_count,
            "snapshot_call_count": key_snapshot_count,
        },
        "reality_audit_status": reality_status,
        "failures": failures,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(json.dumps(result, indent=2), file=sys.stderr)
        raise SystemExit("desktop native model depth failed")

    print("desktop_native_model_depth:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
