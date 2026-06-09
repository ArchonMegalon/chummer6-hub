#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
CORE_ENGINE_ROOT = Path(os.environ.get("CHUMMER_CORE_ENGINE_ROOT", "/docker/chummercomplete/chummer-core-engine"))
OUTPUT_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
DEFAULT_MIN_RULEFACTS = int(os.environ.get("CHUMMER_RULE_AUTHORITY_MIN_RULEFACTS", "100"))

def registry_paths() -> dict[str, Path]:
    return {
        "sr4": CORE_ENGINE_ROOT / ".codex-studio" / "published" / "SR4_RULEFACT_REGISTRY.generated.json",
        "sr5": CORE_ENGINE_ROOT / ".codex-studio" / "published" / "SR5_RULE_AUTHORITY_REGISTRY.generated.json",
        "sr6": CORE_ENGINE_ROOT / ".codex-studio" / "published" / "SR6_RULEFACT_REGISTRY.generated.json",
    }


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail closed when committed public ruleset registries are below minimum coverage.")
    parser.add_argument("--min-rulefacts", type=int, default=DEFAULT_MIN_RULEFACTS)
    args = parser.parse_args()

    rulesets: dict[str, Any] = {}
    failures: list[str] = []
    for ruleset, path in registry_paths().items():
        payload = load_json(path)
        count = int(payload.get("rulefact_count") or 0)
        verdict = str(payload.get("final_verdict") or "")
        status = "pass" if count >= args.min_rulefacts else "fail"
        if count < args.min_rulefacts:
            failures.append(f"{ruleset} rulefact_count {count} is below minimum {args.min_rulefacts}")
        if "READY" not in verdict:
            failures.append(f"{ruleset} final_verdict is not ready")
        rulesets[ruleset] = {
            "path": str(path),
            "rulefact_count": count,
            "final_verdict": verdict,
            "status": status,
        }

    result = {
        "contract_name": "chummer.rule_authority_minimum_coverage",
        "minimum_rulefacts_required": args.min_rulefacts,
        "status": "pass" if not failures else "fail",
        "rulesets": rulesets,
        "failures": failures,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit("rules authority minimum coverage failed")
    print("rule_authority_minimum_coverage:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
