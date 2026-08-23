from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "attest_build_ghost_private_nonprod_deployment.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_ghost_private_attester", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_module()
NOW = dt.datetime(2026, 8, 23, 5, 30, 0, tzinfo=dt.timezone.utc)
IDS = {"presentation": "1" * 64, "ai": "2" * 64, "edge": "3" * 64}
IMAGES = {
    "presentation": "sha256:" + "a" * 64,
    "ai": "sha256:" + "b" * 64,
    "edge": "sha256:" + "c" * 64,
}
ACCOUNT_REFS = ["sha256:" + f"{number:x}" * 64 for number in range(1, 7)]
PREFERRED_ACCOUNT_REF = ACCOUNT_REFS[2]
CANDIDATE_REFS = {
    "agent": "agent-review-1",
    "voice": "voice-review-1",
    "function": "function-review-1",
    "scenario": "scenario-review-1",
    "live_avatar": "live-avatar-review-1",
}
CANDIDATE_DIGESTS = {
    kind: MODULE._candidate_ref_digest(value) for kind, value in CANDIDATE_REFS.items()
}
CONTRACT_DIGEST = "sha256:" + "7" * 64
PRIVATE_NETWORK = MODULE.PROJECT + "_build-ghost-private"
LOOPBACK_NETWORK = MODULE.PROJECT + "_build-ghost-loopback"


def labels(role: str, compose: Path) -> dict[str, str]:
    values = {
        "com.docker.compose.project": MODULE.PROJECT,
        "com.docker.compose.service": MODULE.SERVICES[role],
        "com.docker.compose.config-hash": (
            "d" * 64 if role == "presentation" else "e" * 64 if role == "ai" else "f" * 64
        ),
        "com.docker.compose.project.config_files": str(compose),
        "run.chummer.build-ghost.profile": "private-nonprod",
    }
    if role == "presentation":
        values.update(
            {
                "run.chummer.build-ghost.hub-revision": "4" * 40,
                "org.opencontainers.image.revision": "5" * 40,
                "run.chummer.build-ghost.core-revision": "6" * 40,
                "run.chummer.build-ghost.hub-registry-revision": "7" * 40,
                "run.chummer.build-ghost.ui-kit-revision": "8" * 40,
                "run.chummer.build-ghost.media-factory-revision": "9" * 40,
                "run.chummer.build-ghost.packet-store-schema": "v2",
            }
        )
    elif role == "ai":
        values.update(
            {
                "org.opencontainers.image.revision": "4" * 40,
                "run.chummer.build-ghost.core-revision": "6" * 40,
                "run.chummer.build-ghost.hub-registry-revision": "7" * 40,
                "run.chummer.build-ghost.media-factory-revision": "9" * 40,
            }
        )
    return values


def environment(role: str) -> list[str]:
    if role == "ai":
        rows = [
            *(f"{name}=false" for name in MODULE.PROVIDER_GATES),
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_TRANSPORT_MODE=provider-body-key-v2",
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_ENDPOINT=https://canary.chummer.run/api/v2/ai/build-ghost/tool",
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_AUTHORITY_ENDPOINT=https://presentation.canary.chummer.run/api/internal/build-ghost/tool/resolve",
            "CHUMMER_AI_INTERNAL_API_TOKEN=" + "internal-secret-token-should-never-appear-" + "x" * 32,
            "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS="
            + ";".join(f"secret-slot-{number}-must-not-persist" for number in range(6)),
            "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS=" + ";".join(ACCOUNT_REFS),
            "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF=" + PREFERRED_ACCOUNT_REF,
            f"{MODULE.TOUGH_TONGUE_CONTRACT_DIGEST_ENV}={CONTRACT_DIGEST}",
        ]
        rows.extend(
            f"{MODULE.TOUGH_TONGUE_CANDIDATE_ENV[kind]}={value}"
            for kind, value in CANDIDATE_REFS.items()
        )
        return rows
    if role == "presentation":
        return [
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_DEPLOYMENT_ENABLED=true",
            "CHUMMER_BUILD_GHOST_PACKET_ACCESS_STORE_ROOT=/app/state/build-ghost-packet-access",
        ]
    return []


def expectation_digest(candidate_digests: dict[str, str] | None = None) -> str:
    return MODULE._upstream_digest(
        {
            "preferred_account_ref": PREFERRED_ACCOUNT_REF,
            "candidate_refs": dict(sorted((candidate_digests or CANDIDATE_DIGESTS).items())),
        }
    )


def seal_truth(payload: dict[str, object]) -> dict[str, object]:
    payload.pop("receipt_digest", None)
    payload.pop("evidence_digest", None)
    evidence = {
        "contract": payload.get("contract"),
        "expectation_digest": payload.get("expectation_digest"),
        "accounts": payload.get("accounts"),
        "entitlements": payload.get("entitlements"),
        "bindings": payload.get("bindings"),
        "ownership": payload.get("ownership"),
        "requests": payload.get("requests"),
        "provider_activation": payload.get("provider_activation"),
    }
    payload["evidence_digest"] = MODULE._upstream_digest(evidence)
    payload["receipt_digest"] = MODULE._upstream_digest(payload)
    return payload


def team_truth() -> dict[str, object]:
    binding = {
        "configured": True,
        "ref_sha256": "",
        "readback": True,
        "reference_match": True,
        "account_owner_match": True,
        "organization_owner_match": True,
    }
    bindings: dict[str, dict[str, object]] = {}
    for kind in ("agent", "voice", "function", "scenario"):
        bindings[kind] = {**binding, "ref_sha256": CANDIDATE_DIGESTS[kind]}
    bindings["scenario"].update(
        {
            "live_avatar_match": True,
            "live_avatar_provider_allowed": True,
            "voice_match": True,
            "function_match": True,
            "observed_live_avatar_provider_ref_sha256": "sha256:" + "9" * 64,
        }
    )
    payload: dict[str, object] = {
        "schema": "ea.tough_tongue.read_only_binding_receipt.v1",
        "generated_at": "2026-08-23T05:30:00Z",
        "provider_key": "tough_tongue",
        "probe_mode": "strict_read_only_get",
        "status": "verified",
        "ready": True,
        "probe_ok": True,
        "reason": "",
        "blockers": [],
        "next_action": "",
        "source": "tough_tongue_public_api:digest_bound_verified_get_contract",
        "expectation_digest": expectation_digest(),
        "contract": {
            "schema": "ea.tough_tongue.read_only_binding_contract.v1",
            "configured": True,
            "verified": True,
            "digest": CONTRACT_DIGEST,
            "source_type": "captured_read_only_api",
            "source_ref_sha256": "sha256:" + "8" * 64,
            "verified_at": "2026-08-22T12:00:00Z",
            "methods": ["GET"],
        },
        "accounts": {
            "configured_count": len(ACCOUNT_REFS),
            "distinct_count": len(ACCOUNT_REFS),
            "opaque_account_refs": sorted(ACCOUNT_REFS),
            "preferred_account_ref": PREFERRED_ACCOUNT_REF,
            "preferred_account_ref_configured": True,
            "preferred_account_ref_valid": True,
            "preferred_match_count": 1,
            "preferred_ownership_verified": True,
        },
        "entitlements": {
            "plan_readback": True,
            "premium_verified": True,
            "live_avatar_verified": True,
            "observed_plan_ref_sha256": "sha256:" + "a" * 64,
        },
        "bindings": bindings,
        "ownership": {
            "account_verified": True,
            "organization_verified": True,
            "all_candidate_resources_verified": True,
        },
        "requests": {
            "attempted_count": 5,
            "methods": ["GET"],
            "mutation_request_count": 0,
            "response_bodies_persisted": False,
        },
        "provider_activation": {
            "sessions_created": False,
            "grants_created": False,
            "agents_mutated": False,
            "voices_mutated": False,
            "functions_mutated": False,
            "scenarios_mutated": False,
            "provider_resources_mutated": False,
        },
        "raw_credentials_exposed": False,
        "raw_account_identifiers_exposed": False,
        "raw_candidate_identifiers_exposed": False,
    }
    return seal_truth(payload)


def canary_output() -> bytes:
    values = dict(MODULE.CANARY_EXPECTED)
    values.update(
        {"characters": "1200", "ttl_seconds": "299", "audit_records": "8", "revocation_markers": "2"}
    )
    return (" ".join(f"{key}={value}" for key, value in values.items()) + "\n").encode()


class FakeRunner:
    def __init__(self, compose: Path, caddy: Path):
        self.compose = compose
        self.compose_by_role = {role: compose for role in MODULE.SERVICES}
        self.caddy = caddy
        self.truth = team_truth()
        self.packet = {"authority": "v2", "pending": 0, "claims": 0, "audit": 8, "revocations": 2}
        self.host_ip = "127.0.0.1"
        self.remote_gate = "false"
        self.candidate_overrides: dict[str, str] = {}
        self.runtime_round = 0
        self.drift_after_canary = False
        self.raise_live_probe = False
        self.packet_canary_called = False
        self.fallback_canary_called = False

    def result(self, stdout: bytes | str = b"", returncode: int = 0, stderr: bytes = b""):
        if isinstance(stdout, str):
            stdout = stdout.encode()
        return MODULE.CommandResult(returncode, stdout, stderr)

    def container(self, role: str) -> dict[str, object]:
        env = environment(role)
        if role == "ai" and self.candidate_overrides:
            replacements = {
                MODULE.TOUGH_TONGUE_CANDIDATE_ENV[kind]: value
                for kind, value in self.candidate_overrides.items()
            }
            env = [
                f"{name}={replacements[name]}"
                if (name := row.partition("=")[0]) in replacements else row
                for row in env
            ]
        if role == "ai" and self.remote_gate != "false":
            env = [
                f"{MODULE.PROVIDER_GATES[0]}={self.remote_gate}"
                if row.startswith(MODULE.PROVIDER_GATES[0] + "=") else row
                for row in env
            ]
        role_labels = labels(role, self.compose_by_role[role])
        networks = {PRIVATE_NETWORK: {}}
        bindings: dict[str, object] = {}
        mounts: list[dict[str, object]] = []
        if role == "edge":
            networks[LOOPBACK_NETWORK] = {}
            bindings = {"443/tcp": [{"HostIp": self.host_ip, "HostPort": "8443"}]}
            mounts = [{
                "Type": "bind", "Source": str(self.caddy),
                "Destination": "/etc/caddy/Caddyfile", "RW": False,
            }]
        started = "2026-08-23T04:00:00Z"
        if self.drift_after_canary and self.runtime_round > 1 and role == "ai":
            started = "2026-08-23T05:00:00Z"
        return {
            "Id": IDS[role], "Image": IMAGES[role],
            "State": {
                "Running": True, "Paused": False, "Restarting": False,
                "StartedAt": started,
                **({"Health": {"Status": "healthy"}} if role != "edge" else {}),
            },
            "Config": {"Labels": role_labels, "Env": env},
            "HostConfig": {"PortBindings": bindings},
            "NetworkSettings": {"Networks": networks},
            "Mounts": mounts,
        }

    def image(self, role: str) -> dict[str, object]:
        layer = "1" if role == "presentation" else "2" if role == "ai" else "3"
        return {
            "Id": IMAGES[role], "RepoDigests": [],
            "RootFS": {"Layers": ["sha256:" + layer * 64]},
            "Config": {"Labels": labels(role, self.compose_by_role[role])},
        }

    def run(self, args, *, timeout, input_bytes=None):
        args = list(args)
        if args[:4] == ["git", "-C", str(self.compose.parent), "rev-parse"]:
            if args[-1] == "--show-toplevel":
                return self.result(str(self.compose.parent) + "\n")
            if args[-1] == "HEAD":
                return self.result("a" * 40 + "\n")
            if args[-1] == "HEAD^{tree}":
                return self.result("b" * 40 + "\n")
        if args[:4] == ["git", "-C", str(self.compose.parent), "status"]:
            return self.result()
        if "probe-tough-tongue-bindings" in args:
            if self.raise_live_probe:
                raise MODULE.AttestationError("simulated bounded probe failure")
            receipt = Path(args[args.index("--receipt-path") + 1])
            raw = json.dumps(self.truth, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            receipt.write_bytes(raw)
            os.chmod(receipt, 0o600)
            return self.result(raw, returncode=0 if self.truth.get("ready") is True else 1)
        if args[:2] == ["docker", "ps"]:
            self.runtime_round += 1
            return self.result("\n".join(
                f"{IDS[role]}\t{MODULE.SERVICES[role]}"
                for role in ("presentation", "ai", "edge")
            ) + "\n")
        if args[:4] == ["docker", "inspect", "--type", "container"]:
            role = next(role for role, value in IDS.items() if value == args[-1])
            return self.result(json.dumps([self.container(role)]))
        if args[:3] == ["docker", "image", "inspect"]:
            role = next(role for role, value in IMAGES.items() if value == args[-1])
            return self.result(json.dumps([self.image(role)]))
        if args[:3] == ["docker", "network", "inspect"]:
            payload = (
                {"Id": "4" * 64, "Internal": True, "Containers": {value: {} for value in IDS.values()}}
                if args[-1] == PRIVATE_NETWORK
                else {"Id": "5" * 64, "Internal": False, "Containers": {IDS["edge"]: {}}}
            )
            return self.result(json.dumps([payload]))
        if args[:3] == ["docker", "exec", IDS["presentation"]] and args[3:5] == ["sh", "-c"]:
            return self.result(json.dumps(self.packet) + "\n")
        if args[:1] == ["bash"]:
            self.packet_canary_called = True
            return self.result(canary_output())
        if args[:4] == ["docker", "exec", "-i", IDS["ai"]]:
            self.fallback_canary_called = True
            request = json.loads(args[args.index("--data-binary") + 1])
            response = {
                "usedDeterministicFallback": True,
                "safeText": MODULE.FALLBACK_TEXT,
                "providerAnswer": None,
                "receipt": {
                    "requestId": request["requestId"],
                    "packetDigest": request["packetDigest"],
                    "remoteExecutionEnabled": False,
                    "remoteAttempted": False,
                    "fallbackReason": "remote-disabled",
                    "validationReasons": ["remote-execution-disabled-by-default"],
                },
            }
            return self.result(json.dumps(response, separators=(",", ":")) + "\n200")
        raise AssertionError(f"unexpected command: {args}")


def fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, FakeRunner]:
    os.chmod(tmp_path, 0o700)
    compose = tmp_path / "docker-compose.build-ghost-private-nonprod.yml"
    caddy_dir = tmp_path / "ops" / "build-ghost-private-nonprod"
    caddy_dir.mkdir(parents=True)
    caddy = caddy_dir / "Caddyfile"
    canary = tmp_path / "run-local-canary.sh"
    live_ops = tmp_path / "ea_live_ops.py"
    compose.write_text("name: chummer-build-ghost-private-nonprod\n", encoding="utf-8")
    caddy.write_text("https://canary.chummer.run { respond 404 }\n", encoding="utf-8")
    canary.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    live_ops.write_text("raise SystemExit(99)\n", encoding="utf-8")
    for path in (compose, caddy, canary, live_ops):
        os.chmod(path, 0o700 if path in (canary, live_ops) else 0o600)
    return compose, canary, live_ops, tmp_path / "receipt.json", FakeRunner(compose, caddy)


def invoke(tmp_path: Path, runner: FakeRunner):
    return MODULE._attest(
        repo_root=runner.compose.parent,
        output=tmp_path / "receipt.json",
        canary=tmp_path / "run-local-canary.sh",
        live_ops=tmp_path / "ea_live_ops.py",
        runner=runner,
        clock=lambda: NOW,
    )


def test_all_evidence_emits_only_digest_bound_private_nonprod_claim(tmp_path: Path):
    _, _, _, output, runner = fixture(tmp_path)
    payload = invoke(tmp_path, runner)
    assert payload["status"] == "deployed-private-nonprod"
    assert payload["claim"] == "deployed-private-nonprod"
    assert payload["blockers"] == []
    assert payload["runtime"]["providerGates"]["allLiteralFalse"] is True
    assert payload["runtime"]["confinement"]["loopbackOnly"] is True
    assert payload["packetStore"]["before"]["pending"] == 0
    assert payload["packetStore"]["after"]["claims"] == 0
    assert payload["canaries"]["deterministicNoProviderFallback"]["remoteAttempted"] is False
    assert payload["toughTongueTeamAccountTruth"]["bindingMatchesDeployedConfiguration"] is True
    assert output.stat().st_mode & 0o777 == 0o600
    serialized = output.read_text(encoding="utf-8")
    assert "internal-secret-token" not in serialized
    assert "secret-slot-" not in serialized
    assert all(value not in serialized for value in CANDIDATE_REFS.values())


@pytest.mark.parametrize("role", ["presentation", "ai", "edge"])
def test_every_runtime_compose_source_mismatch_blocks(role: str, tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    alternate = tmp_path / f"stale-{role}.yml"
    alternate.write_text("name: stale\n", encoding="utf-8")
    os.chmod(alternate, 0o600)
    runner.compose_by_role[role] = alternate
    payload = invoke(tmp_path, runner)
    assert f"{role}-runtime-compose-source-drift" in payload["blockers"]
    assert payload["claim"] is None
    assert runner.packet_canary_called is False


@pytest.mark.parametrize("option", ["--repo-root", "--canary", "--ea-live-ops", "--project"])
def test_production_cli_rejects_authority_override_options(option: str, tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(tmp_path / "receipt.json"), option, "attacker"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 2
    assert b"unrecognized arguments" in result.stderr
    assert not (tmp_path / "receipt.json").exists()


def test_deployed_account_count_and_set_mismatch_blocks(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    accounts = runner.truth["accounts"]
    assert isinstance(accounts, dict)
    accounts["opaque_account_refs"] = ACCOUNT_REFS[:-1]
    accounts["configured_count"] = 5
    accounts["distinct_count"] = 5
    seal_truth(runner.truth)
    payload = invoke(tmp_path, runner)
    assert "tough-tongue-deployed-account-set-mismatch" in payload["blockers"]
    assert payload["claim"] is None


def test_deployed_preferred_account_mismatch_blocks(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    accounts = runner.truth["accounts"]
    assert isinstance(accounts, dict)
    accounts["preferred_account_ref"] = ACCOUNT_REFS[1]
    seal_truth(runner.truth)
    payload = invoke(tmp_path, runner)
    assert "tough-tongue-deployed-preferred-account-mismatch" in payload["blockers"]


@pytest.mark.parametrize("kind", ["agent", "voice", "function", "scenario"])
def test_deployed_candidate_binding_mismatch_blocks(kind: str, tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    bindings = runner.truth["bindings"]
    assert isinstance(bindings, dict) and isinstance(bindings[kind], dict)
    bindings[kind]["ref_sha256"] = "sha256:" + "0" * 64
    seal_truth(runner.truth)
    payload = invoke(tmp_path, runner)
    assert "tough-tongue-deployed-candidate-binding-mismatch" in payload["blockers"]


def test_deployed_live_avatar_expectation_mismatch_blocks(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    altered = dict(CANDIDATE_DIGESTS)
    altered["live_avatar"] = "sha256:" + "0" * 64
    runner.truth["expectation_digest"] = expectation_digest(altered)
    seal_truth(runner.truth)
    payload = invoke(tmp_path, runner)
    assert "tough-tongue-deployed-expectation-digest-mismatch" in payload["blockers"]


@pytest.mark.parametrize("kind", ["agent", "voice", "function", "scenario", "live_avatar"])
def test_precomputed_live_candidate_digest_in_container_is_rejected(
    kind: str, tmp_path: Path
):
    _, _, _, _, runner = fixture(tmp_path)
    runner.candidate_overrides[kind] = CANDIDATE_DIGESTS[kind]

    payload = invoke(tmp_path, runner)

    label = kind.replace("_", "-")
    assert f"deployed-tough-tongue-{label}-ref-invalid" in payload["blockers"]
    assert "tough-tongue-deployed-candidate-binding-mismatch" in payload["blockers"]
    assert "canaries-skipped-unsafe-runtime" in payload["blockers"]
    assert payload["status"] == "blocked"
    assert payload["claim"] is None
    assert runner.packet_canary_called is False
    assert runner.fallback_canary_called is False


def test_deployed_readback_contract_digest_mismatch_blocks(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    contract = runner.truth["contract"]
    assert isinstance(contract, dict)
    contract["digest"] = "sha256:" + "0" * 64
    seal_truth(runner.truth)
    payload = invoke(tmp_path, runner)
    assert "tough-tongue-deployed-readback-contract-digest-mismatch" in payload["blockers"]


@pytest.mark.parametrize("mutation", ["missing", "extra", "true"])
def test_provider_activation_requires_exact_all_false_schema(mutation: str, tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    activation = runner.truth["provider_activation"]
    assert isinstance(activation, dict)
    if mutation == "missing":
        activation.pop("sessions_created")
    elif mutation == "extra":
        activation["unreviewed_mutation"] = False
    else:
        activation["sessions_created"] = True
    seal_truth(runner.truth)
    payload = invoke(tmp_path, runner)
    assert "tough-tongue-live-ops-provider-activation-observed" in payload["blockers"]
    assert payload["toughTongueTeamAccountTruth"]["providerMutationObserved"] is True
    assert payload["claim"] is None


@pytest.mark.parametrize("field", ["source", "evidence_digest", "receipt_digest", "blocker"])
def test_untrusted_upstream_sentinel_cannot_persist_or_mint_claim(field: str, tmp_path: Path):
    _, _, _, output, runner = fixture(tmp_path)
    sentinel = f"sentinel-{field}-must-not-persist"
    if field == "source":
        runner.truth["source"] = sentinel
        seal_truth(runner.truth)
    elif field == "blocker":
        runner.truth["blockers"] = [sentinel]
        seal_truth(runner.truth)
    elif field == "evidence_digest":
        runner.truth["evidence_digest"] = sentinel
        runner.truth.pop("receipt_digest", None)
        runner.truth["receipt_digest"] = MODULE._upstream_digest(runner.truth)
    else:
        runner.truth["receipt_digest"] = sentinel
    payload = invoke(tmp_path, runner)
    serialized = output.read_text(encoding="utf-8")
    assert payload["claim"] is None
    assert "tough-tongue-live-ops-receipt-schema-invalid" in payload["blockers"]
    assert sentinel not in serialized


def test_one_non_false_provider_gate_blocks_and_skips_canaries(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    runner.remote_gate = "true"
    payload = invoke(tmp_path, runner)
    assert payload["status"] == "blocked"
    assert any("remote_execution_enabled-not-literal-false" in reason for reason in payload["blockers"])
    assert "canaries-skipped-unsafe-runtime" in payload["blockers"]
    assert runner.packet_canary_called is False


def test_nonempty_packet_store_blocks_before_any_canary(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    runner.packet["pending"] = 1
    payload = invoke(tmp_path, runner)
    assert "packet-store-before-pending-not-zero" in payload["blockers"]
    assert runner.packet_canary_called is False


def test_non_loopback_edge_binding_blocks_deployment_claim(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    runner.host_ip = "0.0.0.0"
    payload = invoke(tmp_path, runner)
    assert "edge-published-binding-not-loopback-only" in payload["blockers"]
    assert runner.packet_canary_called is False


def test_live_team_truth_blockers_remain_explicit_and_redacted(tmp_path: Path):
    _, _, _, output, runner = fixture(tmp_path)
    runner.truth.update({
        "probe_ok": True, "ready": False, "status": "unverified",
        "reason": "tough_tongue_binding_evidence_mismatch",
        "blockers": ["tough_tongue_binding_evidence_mismatch"],
        "next_action": "review_tough_tongue_binding_readback_mismatch",
    })
    seal_truth(runner.truth)
    payload = invoke(tmp_path, runner)
    assert "tough-tongue:tough_tongue_binding_evidence_mismatch" in payload["blockers"]
    assert "tough-tongue-team-account-truth-not-ready" in payload["blockers"]
    assert "secret-slot-" not in output.read_text(encoding="utf-8")


def test_container_identity_drift_during_canaries_fails_closed(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    runner.drift_after_canary = True
    payload = invoke(tmp_path, runner)
    assert "runtime-identity-drift-during-attestation" in payload["blockers"]


def test_unavailable_live_probe_materializes_an_explicit_blocked_receipt(tmp_path: Path):
    _, _, _, output, runner = fixture(tmp_path)
    runner.raise_live_probe = True
    payload = invoke(tmp_path, runner)
    assert "tough-tongue-live-ops-probe-unavailable" in payload["blockers"]
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["claim"] is None


def test_operator_docs_make_authority_and_digest_binding_explicit():
    readme = (ROOT / "ops" / "build-ghost-private-nonprod" / "README.md").read_text(encoding="utf-8")
    assert "attest_build_ghost_private_nonprod_deployment.py" in readme
    assert "deployed-private-nonprod" in readme
    assert "remoteAttempted=false" in readme
    assert "strictly read-only" in readme
    assert "no repository, Compose project, canary, or live-ops" in readme
    assert "EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST" in readme
