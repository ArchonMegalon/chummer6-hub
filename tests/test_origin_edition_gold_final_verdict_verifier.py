from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_origin_edition_gold_final_verdict.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_gold_final_verdict_verifier", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seed(root: Path, *, ready: bool) -> tuple[Path, Path, Path]:
    blocked = [] if ready else ["deployed_owner_read_listen_watch_canon"]
    proof_chain = root / "ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json"
    coverage = root / "ORIGIN_EDITION_GOLD_REQUIREMENT_COVERAGE.generated.json"
    verdict = root / "FINAL_ORIGIN_EDITION_GOLD_VERDICT.md"
    write_json(
        proof_chain,
        {
            "status": "pass" if ready else "blocked",
            "goalCompletionClaimAllowed": ready,
            "namespace": "origin.chummer.run/Case/Ari/Ghost",
            "projectId": "case-ari-ghost",
            "next_action": "Gold proof chain is ready for release handoff. Keep the artifacts archived outside providers."
            if ready
            else "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe.",
            "blocking_reason": "" if ready else "stage:deployed_browser_probe,requirement:deployed_owner_read_listen_watch_canon",
            "privacy": {
                "deploymentPerformed": False,
                "envValuesExposed": False,
                "rawCredentialExposed": False,
                "rawSessionTokenExposed": False,
            },
        },
    )
    write_json(
        coverage,
        {
            "status": "pass" if ready else "blocked",
            "goalCompletionClaimAllowed": ready,
            "blockedRequirements": blocked,
        },
    )
    verdict.write_text(
        "\n".join(
            [
                "# Origin Edition Gold Verdict",
                "Namespace: `origin.chummer.run/Case/Ari/Ghost`",
                "Project ID: `case-ari-ghost`",
                f"Verdict: `{'ORIGIN_EDITION_GOLD_READY' if ready else 'ORIGIN_EDITION_GOLD_BLOCKED'}`",
                f"Goal completion claim allowed: `{'true' if ready else 'false'}`",
                "## Blocked Requirements",
                "- None." if ready else "- `deployed_owner_read_listen_watch_canon`",
                "## Required Next Action",
                "Gold proof chain is ready for release handoff. Keep the artifacts archived outside providers."
                if ready
                else "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe.",
                "## Proof Progress",
                "- Blocking reason: ``" if ready else "- Blocking reason: `stage:deployed_browser_probe,requirement:deployed_owner_read_listen_watch_canon`",
                "## Privacy And Release Boundary",
                "- `rawCredentialExposed`: `false`",
                "- `rawSessionTokenExposed`: `false`",
                "- `envValuesExposed`: `false`",
                "- `deploymentPerformed`: `false`",
                "## Source Artifacts",
                f"- Proof chain: `{proof_chain.as_posix()}`",
                f"- Proof chain SHA-256: `{sha256_file(proof_chain)}`",
                f"- Requirement coverage: `{coverage.as_posix()}`",
                f"- Requirement coverage SHA-256: `{sha256_file(coverage)}`",
            ]
        ),
        encoding="utf-8",
    )
    return verdict, proof_chain, coverage


def test_verifier_accepts_blocked_verdict_matching_blocked_proof(tmp_path: Path) -> None:
    module = load_module()
    verdict, proof_chain, coverage = seed(tmp_path, ready=False)

    ok, issues = module.verify(verdict, proof_chain, coverage)

    assert ok is True
    assert issues == []


def test_verifier_accepts_ready_verdict_matching_ready_proof(tmp_path: Path) -> None:
    module = load_module()
    verdict, proof_chain, coverage = seed(tmp_path, ready=True)

    ok, issues = module.verify(verdict, proof_chain, coverage)

    assert ok is True
    assert issues == []


def test_verifier_rejects_ready_text_for_blocked_proof(tmp_path: Path) -> None:
    module = load_module()
    verdict, proof_chain, coverage = seed(tmp_path, ready=False)
    text = verdict.read_text(encoding="utf-8").replace("ORIGIN_EDITION_GOLD_BLOCKED", "ORIGIN_EDITION_GOLD_READY")
    verdict.write_text(text, encoding="utf-8")

    ok, issues = module.verify(verdict, proof_chain, coverage)

    assert ok is False
    assert "verdict_text_mismatch:ORIGIN_EDITION_GOLD_BLOCKED" in issues
    assert "contradictory_verdict_present:ORIGIN_EDITION_GOLD_READY" in issues


def test_verifier_rejects_verdict_from_different_origin_context(tmp_path: Path) -> None:
    module = load_module()
    verdict, proof_chain, coverage = seed(tmp_path, ready=True)
    text = verdict.read_text(encoding="utf-8")
    text = text.replace("Namespace: `origin.chummer.run/Case/Ari/Ghost`", "Namespace: `origin.chummer.run/Varga/Mira/Kestrel`")
    text = text.replace("Project ID: `case-ari-ghost`", "Project ID: `varga-mira-kestrel`")
    verdict.write_text(text, encoding="utf-8")

    ok, issues = module.verify(verdict, proof_chain, coverage)

    assert ok is False
    assert "proof_namespace_missing_or_mismatched" in issues
    assert "proof_project_id_missing_or_mismatched" in issues


def test_verifier_rejects_ready_text_when_proof_chain_has_stale_blocked_rollups(tmp_path: Path) -> None:
    module = load_module()
    verdict, proof_chain, coverage = seed(tmp_path, ready=True)
    proof = json.loads(proof_chain.read_text(encoding="utf-8"))
    proof["blockedStages"] = ["requirement_coverage"]
    proof["blockedRequirements"] = ["deployed_owner_read_listen_watch_canon"]
    write_json(proof_chain, proof)
    lines = verdict.read_text(encoding="utf-8").splitlines()
    lines = [
        f"- Proof chain SHA-256: `{sha256_file(proof_chain)}`"
        if line.startswith("- Proof chain SHA-256:")
        else line
        for line in lines
    ]
    verdict.write_text("\n".join(lines), encoding="utf-8")

    ok, issues = module.verify(verdict, proof_chain, coverage)

    assert ok is False
    assert "verdict_text_mismatch:ORIGIN_EDITION_GOLD_BLOCKED" in issues
    assert "contradictory_verdict_present:ORIGIN_EDITION_GOLD_READY" in issues
    assert "blocked_requirement_missing:deployed_owner_read_listen_watch_canon" in issues


def test_verifier_rejects_secret_marker_in_verdict(tmp_path: Path) -> None:
    module = load_module()
    verdict, proof_chain, coverage = seed(tmp_path, ready=False)
    verdict.write_text(
        verdict.read_text(encoding="utf-8")
        + "\nBearer leaked\napi.telegram.org/bot123\nsecret-session\nUNMIXR_API_KEY=leaked\n",
        encoding="utf-8",
    )

    ok, issues = module.verify(verdict, proof_chain, coverage)

    assert ok is False
    assert "forbidden_secret_marker:Bearer " in issues
    assert "forbidden_secret_marker:api.telegram.org/bot" in issues
    assert "forbidden_secret_marker:secret-session" in issues
    assert "forbidden_secret_marker:UNMIXR_API_KEY=" in issues


def test_verifier_rejects_missing_next_action_from_verdict(tmp_path: Path) -> None:
    module = load_module()
    verdict, proof_chain, coverage = seed(tmp_path, ready=False)
    text = verdict.read_text(encoding="utf-8").replace(
        "Provide CHUMMER_DEPLOYED_E2E_IDENTITY_TOKEN for a real deployed owner session and rerun this probe.",
        "",
    )
    verdict.write_text(text, encoding="utf-8")

    ok, issues = module.verify(verdict, proof_chain, coverage)

    assert ok is False
    assert "next_action_missing" in issues


def test_verifier_rejects_stale_source_artifact_hashes(tmp_path: Path) -> None:
    module = load_module()
    verdict, proof_chain, coverage = seed(tmp_path, ready=False)
    text = verdict.read_text(encoding="utf-8")
    text = text.replace(f"Proof chain SHA-256: `{sha256_file(proof_chain)}`", "Proof chain SHA-256: `" + "0" * 64 + "`")
    text = text.replace(f"Requirement coverage SHA-256: `{sha256_file(coverage)}`", "Requirement coverage SHA-256: `" + "1" * 64 + "`")
    verdict.write_text(text, encoding="utf-8")

    ok, issues = module.verify(verdict, proof_chain, coverage)

    assert ok is False
    assert "proof_chain_sha_missing_or_stale" in issues
    assert "requirement_coverage_sha_missing_or_stale" in issues
