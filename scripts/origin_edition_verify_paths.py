from __future__ import annotations

import os
from pathlib import Path

from origin_edition_context import OriginEditionContext


DEFAULT_EVIDENCE_ROOT = Path("/docker/chummercomplete/.tmp/origin-dossier-fresh-gold")


def evidence_root_from_env() -> Path:
    return Path(os.environ.get("CHUMMER_ORIGIN_EDITION_EVIDENCE_ROOT", str(DEFAULT_EVIDENCE_ROOT)))


def context_from_env() -> OriginEditionContext:
    return OriginEditionContext.from_env()


def branch_from_env() -> Path:
    return context_from_env().branch(evidence_root_from_env())


def deployed_browser_probe_from_env() -> Path:
    return branch_from_env() / "deployed-chummer-browser-probe.receipt.json"


def deployed_operator_handoff_from_env() -> Path:
    return branch_from_env() / "deployed-operator-handoff.receipt.json"


def gold_proof_chain_from_env() -> Path:
    return evidence_root_from_env() / "ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json"


def gold_requirement_coverage_from_env() -> Path:
    return evidence_root_from_env() / "ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json"


def gold_final_verdict_from_env() -> Path:
    return evidence_root_from_env() / "FINAL_ORIGIN_EDITION_GOLD_VERDICT.md"
