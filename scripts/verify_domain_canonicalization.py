#!/usr/bin/env python3
from __future__ import annotations

import requests

from absolute_completion_common import RUN_SERVICES_ROOT, completion_path, now_iso, write_json, write_text


DOMAINS = [
    "https://chummer.run",
    "https://www.chummer.run",
    "https://chummer6.run",
    "https://www.chummer6.run",
]
PUBLIC_FILES = [
    RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_LANDING_MANIFEST.yaml",
    RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_FEATURE_REGISTRY.yaml",
    RUN_SERVICES_ROOT / "docs" / "PUBLIC_LANDING_SURFACE.md",
    RUN_SERVICES_ROOT.parent / "Chummer6" / "DOWNLOAD.md",
]


def probe(url: str) -> dict:
    try:
        response = requests.get(url, timeout=15, allow_redirects=False)
        return {
            "status_code": response.status_code,
            "location": response.headers.get("Location"),
            "state": "reachable",
        }
    except Exception as exc:
        return {
            "status_code": None,
            "location": None,
            "state": f"error:{exc.__class__.__name__}",
        }


def main() -> int:
    probes = {url: probe(url) for url in DOMAINS}
    public_references = []
    for path in PUBLIC_FILES:
        text = path.read_text(encoding="utf-8")
        if "chummer6.run" in text:
            public_references.append(str(path))

    alias_state = "not_used" if not public_references else "referenced_publicly"
    status = "pass" if alias_state == "not_used" else "fail"
    payload = {
        "contract_name": "chummer.domain_canonicalization",
        "status": status,
        "generated_at_utc": now_iso(),
        "canonical_public_domain": "chummer.run",
        "domain_status": {
            "chummer.run": probes["https://chummer.run"]["state"],
            "www.chummer.run": probes["https://www.chummer.run"]["state"],
            "chummer6.run": alias_state,
            "www.chummer6.run": probes["https://www.chummer6.run"]["state"],
        },
        "probes": probes,
        "public_references": public_references,
    }
    write_json(completion_path("DOMAIN_CANONICALIZATION.generated.json"), payload)
    write_text(
        completion_path("DOMAIN_CANONICALIZATION_REPORT.md"),
        "\n".join(
            [
                "# Domain canonicalization report",
                "",
                f"- Generated: {payload['generated_at_utc']}",
                "- Canonical public domain: `chummer.run`",
                f"- `chummer6.run` public references: {len(public_references)}",
                f"- Status: `{status}`",
            ]
        ),
    )
    if status == "pass":
        print("domain_canonicalization:ok")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
