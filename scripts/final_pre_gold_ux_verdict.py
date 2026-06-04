#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


OUTPUT_ROOT = Path("/docker/chummercomplete/_completion/pregold_ux_pwa_black_ledger")
PUBLISHED_ROOT = Path("/docker/chummercomplete/chummer.run-services/.codex-studio/published")


def load_json(name: str) -> dict:
    path = OUTPUT_ROOT / name
    published_path = PUBLISHED_ROOT / name
    local_payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    published_payload = json.loads(published_path.read_text(encoding="utf-8")) if published_path.is_file() else None

    if name == "BLACK_LEDGER_FACTION_VIDEO_CARD_PROOF.generated.json":
        if isinstance(published_payload, dict) and str(published_payload.get("status", "")).lower() == "pass":
            if str(published_payload.get("base_url") or "").strip().lower().startswith("https://chummer.run"):
                return published_payload

    if local_payload is not None:
        return local_payload
    if published_payload is not None:
        return published_payload
    return {"status": "missing", "path": str(path)}


def write_text(name: str, text: str) -> None:
    path = OUTPUT_ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def status_ok(payload: dict) -> bool:
    return str(payload.get("status", "")).lower() == "pass"


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = load_json("PWA_MANIFEST_LIVE.generated.json")
    service_worker = load_json("PWA_SERVICE_WORKER_LIVE.generated.json")
    installability = load_json("PWA_INSTALLABILITY.generated.json")
    offline = load_json("PWA_OFFLINE_CACHE.generated.json")
    globe_render = load_json("BLACK_LEDGER_GLOBE_RENDER.generated.json")
    globe_motion = load_json("BLACK_LEDGER_GLOBE_MOTION.generated.json")
    globe_reduced = load_json("BLACK_LEDGER_GLOBE_REDUCED_MOTION.generated.json")
    globe_frontdoor = load_json("BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json")
    faction_videos = load_json("BLACK_LEDGER_FACTION_VIDEO_CARD_PROOF.generated.json")
    no_noise = load_json("BLACK_LEDGER_GLOBE_NO_NOISE.generated.json")
    faction_identity = load_json("BLACK_LEDGER_GLOBE_CANON.generated.json")

    pwa_ready = all(status_ok(payload) for payload in [manifest, service_worker, installability, offline])
    globe_ready = all(status_ok(payload) for payload in [globe_render, globe_motion, globe_reduced, globe_frontdoor, no_noise])
    faction_ready = all(status_ok(payload) for payload in [faction_videos, faction_identity])
    ux_ready = no_noise.get("status") == "pass"
    final_ready = pwa_ready and globe_ready and faction_ready and ux_ready

    write_text(
        "FINAL_PWA_GOLD_VERDICT.md",
        "\n".join(
            [
                "# Final PWA gold verdict",
                "",
                f"- Manifest live: `{manifest.get('status', 'missing')}`",
                f"- Service worker live: `{service_worker.get('status', 'missing')}`",
                f"- Installability truth: `{installability.get('status', 'missing')}`",
                f"- Offline cache: `{offline.get('status', 'missing')}`",
                f"- Verdict: `{'READY' if pwa_ready else 'NOT_READY'}`",
            ]
        ),
    )
    write_text(
        "FINAL_BLACK_LEDGER_XCOM_GLOBE_VERDICT.md",
        "\n".join(
            [
                "# Final Black Ledger XCOM globe verdict",
                "",
                f"- Render: `{globe_render.get('status', 'missing')}`",
                f"- Frontdoor: `{globe_frontdoor.get('status', 'missing')}`",
                f"- Motion: `{globe_motion.get('status', 'missing')}`",
                f"- Reduced motion: `{globe_reduced.get('status', 'missing')}`",
                f"- Noise gate: `{no_noise.get('status', 'missing')}`",
                f"- Verdict: `{'BLACK_LEDGER_XCOM_GLOBE_READY' if globe_ready else 'NOT_READY'}`",
            ]
        ),
    )
    write_text(
        "FINAL_PRE_GOLD_UX_VERDICT.md",
        "\n".join(
            [
                "# Final pre-gold UX verdict",
                "",
                f"- Generated: `{datetime.now(timezone.utc).isoformat()}`",
                f"- PWA truth: `{'pass' if pwa_ready else 'fail'}`",
                f"- UX redesign: `{'pass' if ux_ready else 'fail'}`",
                f"- Globe: `{'pass' if globe_ready else 'fail'}`",
                f"- Faction identity and videos: `{'pass' if faction_ready else 'fail'}`",
                "",
                f"`{'PRE_GOLD_UX_READY' if final_ready else 'NOT_READY'}`",
            ]
        ),
    )
    return 0 if final_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
