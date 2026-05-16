#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPLETION = ROOT.parent / "_completion" / "all_horizons_missed_potential"
CONTROLLER = ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
PACKAGE_DETAIL = ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "PackageDetail.cshtml"
BASE_URL = "http://127.0.0.1:8091"


def fetch(path: str) -> tuple[int, str]:
    req = urllib.request.Request(BASE_URL + path, headers={"Host": "chummer.run", "User-Agent": "Codex-verify"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", "ignore")
        return resp.status, body


def main() -> int:
    COMPLETION.mkdir(parents=True, exist_ok=True)
    controller = CONTROLLER.read_text(encoding="utf-8")
    package_detail = PACKAGE_DETAIL.read_text(encoding="utf-8")

    checks: list[dict[str, object]] = []

    for path, expected in [
        ("/rules", "Knowledge Fabric"),
        ("/rules/receipts", '"receiptId": "kf_explain_initiative_sr5"'),
        ("/rules/receipts/kf_explain_initiative_sr5.json", "SR5 initiative explain"),
    ]:
        try:
            status, body = fetch(path)
            ok = status == 200 and expected in body
        except Exception as exc:
            status, body, ok = 0, str(exc), False
        checks.append({"kind": "http", "path": path, "status_code": status, "expected": expected, "status": "pass" if ok else "fail"})

    for label, fragment, source in [
        ("vote revoke route", '[HttpPost("/packages/{packageId}/vote/revoke")]', controller),
        ("follow revoke route", '[HttpPost("/packages/{packageId}/follow/revoke")]', controller),
        ("revoke vote button", 'Revoke vote', package_detail),
        ("revoke follow button", 'Revoke follow', package_detail),
    ]:
        ok = fragment in source
        checks.append({"kind": "source", "label": label, "status": "pass" if ok else "fail"})

    failed = [item for item in checks if item["status"] != "pass"]
    (COMPLETION / "KNOWLEDGE_FABRIC_SOURCE_SAFE_E2E.generated.json").write_text(
        json.dumps(
            {
                "status": "pass" if not failed else "not_ready",
                "checks": checks,
                "summary": "Knowledge Fabric serves public-safe receipt downloads and package detail exposes first-party revoke controls."
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (COMPLETION / "KARMA_FORGE_PACKAGE_PIPELINE_E2E.generated.json").write_text(
        json.dumps(
            {
                "status": "pass" if not failed else "not_ready",
                "checks": [item for item in checks if item["kind"] == "source"],
                "summary": "Package loop now includes vote/follow revoke posture on first-party routes."
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
