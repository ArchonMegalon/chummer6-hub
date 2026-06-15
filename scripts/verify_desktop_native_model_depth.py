#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
CHUMMER_UI_ROOT = Path(os.environ.get("CHUMMER_UI_ROOT", "/docker/chummercomplete/chummer-presentation"))
OUTPUT_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "DESKTOP_NATIVE_MODEL_DEPTH.generated.json"
REALITY_AUDIT_PATH = CHUMMER_UI_ROOT / ".codex-studio" / "published" / "CLASSIC_FORMPORT_REALITY_AUDIT.generated.json"
BRIDGE_PATH = CHUMMER_UI_ROOT / "Chummer.Avalonia" / "Controls" / "ClassicFormPorts" / "ClassicFormPortViewModelBridge.cs"
SECTION_HOST_PATH = CHUMMER_UI_ROOT / "Chummer.Avalonia" / "Controls" / "SectionHostControl.axaml.cs"
CLASSIC_HOST_PATH = CHUMMER_UI_ROOT / "Chummer.Avalonia" / "Controls" / "ClassicFormPortHostControl.axaml.cs"
SHELL_FRAME_PROJECTOR_PATH = CHUMMER_UI_ROOT / "Chummer.Avalonia" / "MainWindow.ShellFrameProjector.cs"
GEAR_PORT_PATH = CHUMMER_UI_ROOT / "Chummer.Avalonia" / "Controls" / "ClassicFormPorts" / "GearClassicPort.axaml.cs"

GENERIC_BLOCKERS = {
    "bridge_create_from_section_rows_signature": "CreateFromSectionRows(IReadOnlyList<SectionRowDisplayItem> sourceRows)",
    "bridge_parse_document_rows_signature": "ParseDocumentRows(IReadOnlyList<SectionRowDisplayItem> sourceRows)",
    "bridge_line_item_projection": "ClassicPortLineItem ToLineItem(",
    "bridge_bucket_projection": "SelectBucket(",
    "bridge_multi_bucket_projection": "SelectBuckets(",
    "section_host_row_record": "public sealed record SectionRowDisplayItem(string Path, string Value)",
    "classic_host_preview_document": "ClassicFormPortDocument.CreateFromPreview(",
    "classic_host_section_row_state": "IReadOnlyList<SectionRowDisplayItem> Rows,",
    "classic_host_gear_port_mount": "[\"gear\"] = new GearClassicPort()",
    "shell_frame_row_projection": "new SectionRowDisplayItem(row.Path, row.Value)",
    "gear_port_classic_type": "public partial class GearClassicPort",
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
    classic_host_text = read_text(CLASSIC_HOST_PATH)
    shell_frame_text = read_text(SHELL_FRAME_PROJECTOR_PATH)
    gear_port_text = read_text(GEAR_PORT_PATH)

    marker_hits = {
        name: marker in (
            bridge_text if name.startswith("bridge_")
            else section_host_text if name.startswith("section_host_")
            else classic_host_text if name.startswith("classic_host_")
            else shell_frame_text if name.startswith("shell_frame_")
            else gear_port_text
        )
        for name, marker in GENERIC_BLOCKERS.items()
    }
    classic_line_item_count = bridge_text.count("ClassicPortLineItem")
    bucket_call_count = bridge_text.count("SelectBucket(")
    multi_bucket_call_count = bridge_text.count("SelectBuckets(")
    reality_status = str(reality_payload.get("status") or "missing").strip().lower()

    failures: list[str] = []
    if marker_hits["bridge_create_from_section_rows_signature"]:
        failures.append("desktop flagship bridge still creates document state directly from SectionRowDisplayItem rows")
    if marker_hits["bridge_parse_document_rows_signature"]:
        failures.append("desktop flagship bridge still parses generic SectionRowDisplayItem rows into workflow state")
    if marker_hits["bridge_line_item_projection"] or classic_line_item_count >= 12:
        failures.append(f"desktop flagship bridge still projects ClassicPortLineItem wrappers across the desktop surface ({classic_line_item_count} references)")
    if marker_hits["bridge_bucket_projection"] or marker_hits["bridge_multi_bucket_projection"] or (bucket_call_count + multi_bucket_call_count) >= 3:
        failures.append("desktop flagship bridge still buckets generic row facts instead of typed workflow models")
    if marker_hits["classic_host_gear_port_mount"] or marker_hits["gear_port_classic_type"]:
        failures.append("desktop shell still mounts GearClassicPort as the gear compatibility surface")
    if marker_hits["classic_host_preview_document"]:
        failures.append("desktop classic host still derives gear workflow state from preview JSON instead of a typed gear surface model")
    if marker_hits["classic_host_section_row_state"] or marker_hits["shell_frame_row_projection"]:
        failures.append("desktop shell still projects SectionRowDisplayItem rows into the desktop gear compatibility surface")

    result = {
        "contract_name": "chummer.desktop_native_model_depth",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": "DESKTOP_NATIVE_MODEL_READY" if not failures else "DESKTOP_NATIVE_MODEL_REVIEW_REQUIRED",
        "inputs": {
            "classic_formport_reality_audit_path": str(REALITY_AUDIT_PATH),
            "bridge_path": str(BRIDGE_PATH),
            "section_host_path": str(SECTION_HOST_PATH),
            "classic_host_path": str(CLASSIC_HOST_PATH),
            "shell_frame_projector_path": str(SHELL_FRAME_PROJECTOR_PATH),
            "gear_port_path": str(GEAR_PORT_PATH),
        },
        "source_markers": {
            **marker_hits,
            "classic_port_line_item_list_count": classic_line_item_count,
            "bucket_call_count": bucket_call_count,
            "multi_bucket_call_count": multi_bucket_call_count,
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
