#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.request
from pathlib import Path


BASE_URL = "http://127.0.0.1:8091"
ROOT = Path(__file__).resolve().parents[1]
COMPLETION = ROOT.parent / "_completion" / "all_horizons_missed_potential"

CHECKS = [
    ("/ready", "html", "Ready for Tonight"),
    ("/ready/packet/player.md", "text", "# Player packet"),
    ("/ready/packet/player.json", "json", '"roleId": "player"'),
    ("/ready/packet/gm.md", "text", "# GM packet"),
    ("/ready/packet/organizer.json", "json", '"roleId": "organizer"'),
    ("/ready/loadout/mage.json", "json", '"kitId": "mage"'),
    ("/ready/handoff/mobile.json", "json", '"mode": "ready_for_tonight"'),
]


def fetch(path: str) -> tuple[int, str]:
    request = urllib.request.Request(BASE_URL + path, headers={"Host": "chummer.run", "User-Agent": "Codex-verify"})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8")
        return response.status, body


def main() -> int:
    COMPLETION.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    failures: list[str] = []
    for path, kind, expected in CHECKS:
        try:
            status, body = fetch(path)
            passed = status == 200 and expected in body
        except Exception as exc:  # pragma: no cover - runtime probe
            status = 0
            body = str(exc)
            passed = False

        if not passed:
            failures.append(path)
        results.append(
            {
                "path": path,
                "kind": kind,
                "status_code": status,
                "expected_fragment": expected,
                "status": "pass" if passed else "fail",
            }
        )

    payload = {
        "status": "pass" if not failures else "not_ready",
        "checks": results,
        "summary": "Ready for Tonight shipped MVP exposes role verdict HTML, packet downloads, starter loadout JSON, and mobile handoff JSON."
    }
    (COMPLETION / "READY_FOR_TONIGHT_E2E.generated.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
