from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys


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
IDS = {
    "presentation": "1" * 64,
    "ai": "2" * 64,
    "edge": "3" * 64,
}
IMAGES = {
    "presentation": "sha256:" + "a" * 64,
    "ai": "sha256:" + "b" * 64,
    "edge": "sha256:" + "c" * 64,
}
PRIVATE_NETWORK = MODULE.PROJECT + "_build-ghost-private"
LOOPBACK_NETWORK = MODULE.PROJECT + "_build-ghost-loopback"


def labels(role: str, compose: Path) -> dict[str, str]:
    values = {
        "com.docker.compose.project": MODULE.PROJECT,
        "com.docker.compose.service": MODULE.SERVICES[role],
        "com.docker.compose.config-hash": f"config-{role}",
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
        return [
            *(f"{name}=false" for name in MODULE.PROVIDER_GATES),
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_TRANSPORT_MODE=provider-body-key-v2",
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_ENDPOINT=https://canary.chummer.run/api/v2/ai/build-ghost/tool",
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_AUTHORITY_ENDPOINT=https://presentation.canary.chummer.run/api/internal/build-ghost/tool/resolve",
            "CHUMMER_AI_INTERNAL_API_TOKEN=" + "internal-secret-token-should-never-appear-" + "x" * 32,
        ]
    if role == "presentation":
        return [
            "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_DEPLOYMENT_ENABLED=true",
            "CHUMMER_BUILD_GHOST_PACKET_ACCESS_STORE_ROOT=/app/state/build-ghost-packet-access",
        ]
    return []


def team_truth() -> dict[str, object]:
    binding = {
        "configured": True,
        "readback": True,
        "reference_match": True,
        "account_owner_match": True,
        "organization_owner_match": True,
    }
    return {
        "schema": "ea.tough_tongue.read_only_binding_receipt.v1",
        "provider_key": "tough_tongue",
        "generated_at": "2026-08-23T05:30:00Z",
        "probe_mode": "strict_read_only_get",
        "probe_ok": True,
        "ready": True,
        "status": "ready",
        "source": "live_provider_readback",
        "blockers": [],
        "raw_account_identifiers_exposed": False,
        "raw_candidate_identifiers_exposed": False,
        "raw_credentials_exposed": False,
        "provider_activation": {
            "agents_mutated": False,
            "functions_mutated": False,
            "grants_created": False,
            "provider_resources_mutated": False,
            "scenarios_mutated": False,
            "sessions_created": False,
            "voices_mutated": False,
        },
        "requests": {
            "attempted_count": 6,
            "methods": ["GET"],
            "mutation_request_count": 0,
            "response_bodies_persisted": False,
        },
        "accounts": {
            "configured_count": 6,
            "distinct_count": 6,
            "opaque_account_refs": ["sha256:" + "e" * 64],
            "preferred_account_ref_configured": True,
            "preferred_account_ref_valid": True,
            "preferred_match_count": 1,
            "preferred_ownership_verified": True,
        },
        "bindings": {
            "agent": dict(binding),
            "voice": dict(binding),
            "function": dict(binding),
            "scenario": dict(binding),
        },
        "entitlements": {"premium_verified": True, "live_avatar_verified": True},
        "ownership": {
            "account_verified": True,
            "organization_verified": True,
            "all_candidate_resources_verified": True,
        },
        "contract": {"configured": True, "verified": True, "methods": ["GET"]},
        "evidence_digest": "sha256:" + "d" * 64,
        "receipt_digest": "sha256:" + "f" * 64,
        "secretCanary": "must-not-flow-to-attestation",
    }


def canary_output() -> bytes:
    values = dict(MODULE.CANARY_EXPECTED)
    values.update(
        {
            "characters": "1200",
            "ttl_seconds": "299",
            "audit_records": "8",
            "revocation_markers": "2",
        }
    )
    return (" ".join(f"{key}={value}" for key, value in values.items()) + "\n").encode()


class FakeRunner:
    def __init__(self, compose: Path, caddy: Path):
        self.compose = compose
        self.caddy = caddy
        self.truth = team_truth()
        self.packet = {"authority": "v2", "pending": 0, "claims": 0, "audit": 8, "revocations": 2}
        self.host_ip = "127.0.0.1"
        self.remote_gate = "false"
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
        if role == "ai" and self.remote_gate != "false":
            env = [
                f"{MODULE.PROVIDER_GATES[0]}={self.remote_gate}" if row.startswith(MODULE.PROVIDER_GATES[0] + "=") else row
                for row in env
            ]
        role_labels = labels(role, self.compose)
        networks = {PRIVATE_NETWORK: {}}
        bindings: dict[str, object] = {}
        mounts: list[dict[str, object]] = []
        if role == "edge":
            networks[LOOPBACK_NETWORK] = {}
            bindings = {"443/tcp": [{"HostIp": self.host_ip, "HostPort": "8443"}]}
            mounts = [
                {
                    "Type": "bind",
                    "Source": str(self.caddy),
                    "Destination": "/etc/caddy/Caddyfile",
                    "RW": False,
                }
            ]
        started = "2026-08-23T04:00:00Z"
        if self.drift_after_canary and self.runtime_round > 1 and role == "ai":
            started = "2026-08-23T05:00:00Z"
        return {
            "Id": IDS[role],
            "Image": IMAGES[role],
            "State": {
                "Running": True,
                "Paused": False,
                "Restarting": False,
                "StartedAt": started,
                **({"Health": {"Status": "healthy"}} if role != "edge" else {}),
            },
            "Config": {"Labels": role_labels, "Env": env},
            "HostConfig": {"PortBindings": bindings},
            "NetworkSettings": {"Networks": networks},
            "Mounts": mounts,
        }

    def image(self, role: str) -> dict[str, object]:
        return {
            "Id": IMAGES[role],
            "RepoDigests": [],
            "RootFS": {"Layers": ["sha256:" + ("1" if role == "presentation" else "2" if role == "ai" else "3") * 64]},
            "Config": {"Labels": labels(role, self.compose)},
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
            return self.result(raw)
        if args[:2] == ["docker", "ps"]:
            self.runtime_round += 1
            return self.result(
                "\n".join(
                    f"{IDS[role]}\t{MODULE.SERVICES[role]}" for role in ("presentation", "ai", "edge")
                )
                + "\n"
            )
        if args[:4] == ["docker", "inspect", "--type", "container"]:
            role = next(role for role, value in IDS.items() if value == args[-1])
            return self.result(json.dumps([self.container(role)]))
        if args[:3] == ["docker", "image", "inspect"]:
            role = next(role for role, value in IMAGES.items() if value == args[-1])
            return self.result(json.dumps([self.image(role)]))
        if args[:3] == ["docker", "network", "inspect"]:
            if args[-1] == PRIVATE_NETWORK:
                payload = {"Id": "4" * 64, "Internal": True, "Containers": {value: {} for value in IDS.values()}}
            else:
                payload = {"Id": "5" * 64, "Internal": False, "Containers": {IDS["edge"]: {}}}
            return self.result(json.dumps([payload]))
        if args[:3] == ["docker", "exec", IDS["presentation"]] and args[3:5] == ["sh", "-c"]:
            return self.result(json.dumps(self.packet) + "\n")
        if args[:1] == ["bash"]:
            self.packet_canary_called = True
            return self.result(canary_output())
        if args[:4] == ["docker", "exec", "-i", IDS["ai"]]:
            self.fallback_canary_called = True
            request = json.loads(args[args.index("--data-binary") + 1])
            assert request["schema"] == "chummer.tough_tongue.build_ghost_request.v1"
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


def fixture(tmp_path: Path):
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
    output = tmp_path / "receipt.json"
    runner = FakeRunner(compose, caddy)
    return compose, canary, live_ops, output, runner


def invoke(tmp_path: Path, runner: FakeRunner):
    compose = runner.compose
    return MODULE.attest(
        repo_root=compose.parent,
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
    assert payload["toughTongueTeamAccountTruth"]["ready"] is True
    assert output.stat().st_mode & 0o777 == 0o600
    serialized = output.read_text(encoding="utf-8")
    assert "internal-secret-token" not in serialized
    assert "must-not-flow-to-attestation" not in serialized
    assert "opaque_account_refs" not in serialized


def test_one_non_false_provider_gate_blocks_and_skips_canaries(tmp_path: Path):
    fixture(tmp_path)
    runner = FakeRunner(tmp_path / "docker-compose.build-ghost-private-nonprod.yml", tmp_path / "ops/build-ghost-private-nonprod/Caddyfile")
    runner.remote_gate = "true"

    payload = invoke(tmp_path, runner)

    assert payload["status"] == "blocked"
    assert payload["claim"] is None
    assert any("remote_execution_enabled-not-literal-false" in reason for reason in payload["blockers"])
    assert "canaries-skipped-unsafe-runtime" in payload["blockers"]
    assert runner.packet_canary_called is False
    assert runner.fallback_canary_called is False


def test_nonempty_packet_store_blocks_before_any_canary(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    runner.packet["pending"] = 1

    payload = invoke(tmp_path, runner)

    assert "packet-store-before-pending-not-zero" in payload["blockers"]
    assert "canaries-skipped-unsafe-runtime" in payload["blockers"]
    assert runner.packet_canary_called is False


def test_non_loopback_edge_binding_blocks_deployment_claim(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    runner.host_ip = "0.0.0.0"

    payload = invoke(tmp_path, runner)

    assert payload["status"] == "blocked"
    assert "edge-published-binding-not-loopback-only" in payload["blockers"]
    assert runner.packet_canary_called is False


def test_live_team_truth_blockers_remain_explicit_and_redacted(tmp_path: Path):
    _, _, _, output, runner = fixture(tmp_path)
    runner.truth = copy.deepcopy(team_truth())
    runner.truth.update({"probe_ok": False, "ready": False, "status": "blocked"})
    runner.truth["blockers"] = ["tough_tongue_preferred_account_ref_missing"]
    runner.truth["accounts"]["preferred_account_ref_valid"] = False

    payload = invoke(tmp_path, runner)

    assert payload["status"] == "blocked"
    assert "tough-tongue:tough_tongue_preferred_account_ref_missing" in payload["blockers"]
    assert "tough-tongue-team-account-truth-not-ready" in payload["blockers"]
    assert runner.packet_canary_called is True
    assert "must-not-flow-to-attestation" not in output.read_text(encoding="utf-8")


def test_container_identity_drift_during_canaries_fails_closed(tmp_path: Path):
    _, _, _, _, runner = fixture(tmp_path)
    runner.drift_after_canary = True

    payload = invoke(tmp_path, runner)

    assert payload["status"] == "blocked"
    assert "runtime-identity-drift-during-attestation" in payload["blockers"]


def test_unavailable_live_probe_still_materializes_an_explicit_blocked_receipt(tmp_path: Path):
    _, _, _, output, runner = fixture(tmp_path)
    runner.raise_live_probe = True

    payload = invoke(tmp_path, runner)

    assert payload["status"] == "blocked"
    assert "tough-tongue-live-ops-probe-unavailable" in payload["blockers"]
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["claim"] is None


def test_operator_docs_make_the_generated_claim_and_provider_boundary_explicit():
    readme = (ROOT / "ops" / "build-ghost-private-nonprod" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "attest_build_ghost_private_nonprod_deployment.py" in readme
    assert "deployed-private-nonprod" in readme
    assert "remoteAttempted=false" in readme
    assert "probe-tough-tongue-bindings" in readme
    assert "strictly read-only" in readme
    assert "never changes a Compose service" in readme
