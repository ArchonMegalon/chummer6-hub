from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts" / "deploy_public_edge_portal.sh"
MIGRATION_LOOP = ROOT / "scripts" / "migration-loop.sh"
RESTORE = ROOT / "scripts" / "restore_public_edge_portal_image.py"
PUBLISHER = ROOT / "scripts" / "publish_public_edge_portal_overlay.py"
RUNBOOK = ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md"
PRIOR_PORTAL_IMAGE_ID = "sha256:" + "1" * 64
CANDIDATE_PORTAL_IMAGE_ID = "sha256:" + "2" * 64
MISMATCH_PORTAL_IMAGE_ID = "sha256:" + "3" * 64
PRIOR_TOOL_IMAGE_ID = "sha256:" + "4" * 64
PRIOR_TUNNEL_IMAGE_ID = "sha256:" + "5" * 64
CANDIDATE_TOOL_IMAGE_ID = "sha256:" + "6" * 64
PRIOR_TUNNEL_REPLICA_IMAGE_ID = "sha256:" + "7" * 64
PRIOR_PORTAL_CONTAINER_ID = "a" * 64
CANDIDATE_PORTAL_CONTAINER_ID = "b" * 64
PRIOR_TUNNEL_CONTAINER_ID = "c" * 64
PRIOR_TUNNEL_REPLICA_CONTAINER_ID = "f" * 64
POSTQUIESCE_PROOF_CONTAINER_ID = "d" * 64
ORPHAN_STATE_CONSUMER_CONTAINER_ID = "e" * 64
TOPOLOGY_B_GUARD_MESSAGE = (
    "canonical public edge mutation is blocked while topology-B downloads "
    "authority exists"
)


def write_public_projection_snapshot(root: Path, proof_bytes: bytes) -> Path:
    output_names = (
        "HUB_LOCAL_RELEASE_PROOF.generated.json",
        "HUB_SERVED_RELEASE_PROOF.generated.json",
        "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
        "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
        "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
        "RELEASE_CHANNEL.generated.json",
        "FLAGSHIP_PRODUCT_READINESS.generated.json",
    )
    payloads = {
        output_names[0]: proof_bytes,
        output_names[1]: proof_bytes,
        output_names[2]: b"m125\n",
        output_names[3]: b"m126\n",
        output_names[4]: b"windows\n",
        output_names[5]: b'{"status":"test"}\n',
        output_names[6]: b'{"status":"fail"}\n',
    }
    digests = {
        name: hashlib.sha256(payloads[name]).hexdigest() for name in output_names
    }
    aggregate = hashlib.sha256()
    for name in output_names:
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digests[name].encode("ascii"))
        aggregate.update(b"\n")
    snapshot_sha256 = aggregate.hexdigest()
    snapshot_id = f"public-projection-{snapshot_sha256}"
    snapshot = root / snapshot_id
    snapshot.mkdir(parents=True)
    for name, payload in payloads.items():
        (snapshot / name).write_bytes(payload)
    manifest_name = "PUBLIC_PROJECTION_SNAPSHOT.generated.json"
    release_gate_findings = [
        {
            "gate": "live public Windows installer",
            "status": "postdeploy_required",
            "reason": "live Windows installer proof must pass after code deployment",
        }
    ]
    manifest = {
        "contractName": "chummer.public_projection_snapshot/v1",
        "status": "review_required",
        "projectionStage": "code_deploy_review_required",
        "codeDeploymentAuthority": True,
        "releaseUploadAuthority": False,
        "candidateImportAuthority": False,
        "releaseGateFindings": release_gate_findings,
        "snapshotId": snapshot_id,
        "snapshotSha256": snapshot_sha256,
        "authorityInputs": {},
        "outputs": {
            name: {
                "relativePath": name,
                "sha256": digests[name],
                "sizeBytes": len(payloads[name]),
            }
            for name in output_names
        },
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    (snapshot / manifest_name).write_bytes(manifest_bytes)
    current = {
        "contractName": "chummer.public_projection_current/v1",
        "status": "review_required",
        "projectionStage": "code_deploy_review_required",
        "codeDeploymentAuthority": True,
        "releaseUploadAuthority": False,
        "candidateImportAuthority": False,
        "releaseGateFindings": release_gate_findings,
        "snapshotId": snapshot_id,
        "snapshotSha256": snapshot_sha256,
        "manifestRelativePath": f"{snapshot_id}/{manifest_name}",
        "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "outputs": {name: f"{snapshot_id}/{name}" for name in output_names},
    }
    (root / "CURRENT.json").write_text(
        json.dumps(current, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return snapshot / output_names[0]


@pytest.fixture(autouse=True)
def fake_rendered_compose_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for forbidden_name in (
        "BASH_ENV",
        "BASHOPTS",
        "BASH_XTRACEFD",
        "ENV",
        "PS4",
        "SHELLOPTS",
        "CDPATH",
        "GLOBIGNORE",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
        "PYTHONBREAKPOINT",
        "PYTHONWARNINGS",
        "PYTHONSAFEPATH",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "BUILDKIT_HOST",
        "BUILDX_BUILDER",
        "COMPOSE_FILE",
    ):
        monkeypatch.delenv(forbidden_name, raising=False)
    trusted_tools = tmp_path / "trusted-tools"
    trusted_tools.mkdir()
    trusted_python = trusted_tools / "python3"
    trusted_python.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ -n \"${FAKE_TRUSTED_PYTHON_LOG:-}\" ]; then printf '%s\\n' \"$*\" >> \"$FAKE_TRUSTED_PYTHON_LOG\"; fi\n"
        "arg_value() { key=\"$1\"; shift; while [ \"$#\" -gt 0 ]; do if [ \"$1\" = \"$key\" ]; then shift; [ \"$#\" -gt 0 ] || return 1; printf '%s' \"$1\"; return 0; fi; shift; done; return 1; }\n"
        "case \"$*\" in\n"
        "  *verify_public_edge_deploy_authority.py*) exit \"${FAKE_AUTHORITY_EXIT:-0}\";;\n"
        "  *verify_public_edge_deploy_source.py*) exit \"${FAKE_SOURCE_GATE_EXIT:-0}\";;\n"
        "  *deploy_public_download_only_cutover.py*) if [ -n \"${FAKE_PUBLIC_DOWNLOAD_CONTROLLER_PID:-}\" ]; then printf '%s\\n' \"$$\" > \"$FAKE_PUBLIC_DOWNLOAD_CONTROLLER_PID\"; fi; if [ -n \"${FAKE_PUBLIC_DOWNLOAD_CONTROLLER_READY:-}\" ]; then /usr/bin/touch \"$FAKE_PUBLIC_DOWNLOAD_CONTROLLER_READY\"; fi; case \"${FAKE_PUBLIC_DOWNLOAD_CONTROLLER_MODE:-exit}\" in block) trap '' HUP INT TERM; while :; do printf '%s\\n' alive >> \"$FAKE_PUBLIC_DOWNLOAD_CONTROLLER_HEARTBEAT\"; /usr/bin/sleep 0.05; done;; term) /usr/bin/kill -TERM \"$$\";; int) /usr/bin/kill -INT \"$$\";; exit) if [ -n \"${FAKE_PUBLIC_DOWNLOAD_CLEANUP_TAMPER_PATH:-}\" ]; then /usr/bin/chmod 0644 \"$FAKE_PUBLIC_DOWNLOAD_CLEANUP_TAMPER_PATH\"; fi; exit \"${FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT:-0}\";; *) exit 91;; esac;;\n"
        "  *verify_install_linking_cutover_boundary.py*\"--expected-phase public_acceptance_completed\"*) boundary=\"$(arg_value --boundary \"$@\")\"; expected=\"$(arg_value --expected-boundary-sha256 \"$@\")\"; actual=\"$(/usr/bin/sha256sum -- \"$boundary\" | /usr/bin/awk '{print $1}')\"; [ \"$actual\" = \"$expected\" ] || exit 81; /usr/bin/cat \"$FAKE_INSTALL_LINKING_FINAL_VERIFICATION_JSON\"; exit 0;;\n"
        "  *verify_install_linking_cutover_boundary.py*) boundary=\"$(arg_value --boundary \"$@\")\"; expected=\"$(arg_value --expected-boundary-sha256 \"$@\")\"; actual=\"$(/usr/bin/sha256sum -- \"$boundary\" | /usr/bin/awk '{print $1}')\"; [ \"$actual\" = \"$expected\" ] || exit 81; /usr/bin/cat \"$FAKE_INSTALL_LINKING_BOUNDARY_VERIFICATION_JSON\"; exit \"${FAKE_INSTALL_LINKING_BOUNDARY_VERIFY_EXIT:-0}\";;\n"
        "  *run_install_linking_postgres_cutover.py*\"--source-replay-preflight\"*) exit \"${FAKE_SOURCE_REPLAY_PREFLIGHT_EXIT:-0}\";;\n"
        "  *run_install_linking_postgres_cutover.py*\"--post-quiesce-reproof\"*) output=\"$(arg_value --output \"$@\")\"; attempt=\"$(arg_value --reproof-attempt-id \"$@\")\"; inventory=\"$(arg_value --volume-inventory-receipt \"$@\")\"; expected_inventory_sha256=\"$(arg_value --expected-volume-inventory-sha256 \"$@\")\"; actual_inventory_sha256=\"$(/usr/bin/sha256sum -- \"$inventory\" | /usr/bin/awk '{print $1}')\"; [ \"$actual_inventory_sha256\" = \"$expected_inventory_sha256\" ] || exit 84; reproof_exit=\"${FAKE_POSTQUIESCE_EXIT:-}\"; reproof_mode=\"${FAKE_POSTQUIESCE_MODE:-}\"; if [ -z \"$reproof_mode\" ]; then if [ -z \"$reproof_exit\" ] || [ \"$reproof_exit\" = 0 ]; then reproof_mode=pass; else reproof_mode=unknown; fi; fi; case \"$reproof_mode\" in sigkill) /usr/bin/kill -KILL \"$$\";; missing) exit \"${reproof_exit:-1}\";; malformed) printf '%s\\n' '{malformed' > \"$output\"; /usr/bin/chmod 0600 \"$output\"; exit \"${reproof_exit:-1}\";; safe_fail) reproof_status=fail; start_intent=false; start_may=false; reproof_exit=\"${reproof_exit:-1}\";; pass) reproof_status=pass; start_intent=true; start_may=true; reproof_exit=\"${reproof_exit:-0}\"; printf '%s\\n' \"$attempt\" > \"$FAKE_POSTQUIESCE_COMPLETED_STATE\";; oom) reproof_status=unknown; start_intent=true; start_may=true; reproof_exit=\"${reproof_exit:-137}\";; unknown) reproof_status=unknown; start_intent=true; start_may=true; reproof_exit=\"${reproof_exit:-70}\";; *) exit 85;; esac; printf '{\"containerStartMayHaveBeenInvoked\":%s,\"mode\":\"%s\",\"reason\":\"%s\",\"startIntentWritten\":%s,\"status\":\"%s\"}\\n' \"$start_may\" \"$reproof_mode\" \"${FAKE_POSTQUIESCE_REASON:-none}\" \"$start_intent\" \"$reproof_status\" > \"$output\"; /usr/bin/chmod 0600 \"$output\"; exit \"$reproof_exit\";;\n"
        "  *materialize_install_linking_cutover_boundary.py*\"--phase public_acceptance_completed\"*) /usr/bin/cp \"$FAKE_INSTALL_LINKING_FINAL_BOUNDARY\" \"$(arg_value --output \"$@\")\"; /usr/bin/chmod 0600 \"$(arg_value --output \"$@\")\"; exit \"${FAKE_INSTALL_LINKING_MATERIALIZER_EXIT:-0}\";;\n"
        "  *verify_public_projection.py*) if [ -n \"${FAKE_PUBLIC_DOWNLOAD_PROJECTION_RESOLUTION:-}\" ]; then /usr/bin/cat \"$FAKE_PUBLIC_DOWNLOAD_PROJECTION_RESOLUTION\"; exit 0; fi; exec /usr/bin/python3 \"$@\";;\n"
        "  *verify_public_edge_postdeploy_gate.py*) exec /usr/bin/python3 \"$@\";;\n"
        "  *chummer.public_projection_current/v1*) exec /usr/bin/python3 \"$@\";;\n"
        "  *validate_public_edge_compose_runtime.py*) /usr/bin/cat >/dev/null; exit 0;;\n"
        "  *\"Public-download pinned controller descriptor verifier\"*) if [ -n \"${FAKE_BOUND_CONTROLLER_DESCRIPTOR_PAUSE_READY:-}\" ]; then /usr/bin/touch \"$FAKE_BOUND_CONTROLLER_DESCRIPTOR_PAUSE_READY\"; /usr/bin/sleep 30; fi; exec /usr/bin/python3 \"$@\";;\n"
        "  *\"Retained pre-controller public-download post-lease verifier\"*) exec /usr/bin/python3 \"$@\";;\n"
        "  *secrets.token_hex*|*hmac.compare_digest*) exec /usr/bin/python3 \"$@\";;\n"
        "  *matches\\ =\\ \\[\\]*) exec /usr/bin/python3 \"$@\";;\n"
        "  *\"InstallLinking verified boundary binding parser\"*) exec /usr/bin/python3 \"$@\";;\n"
        "  *\"InstallLinking candidate build-source provenance parser\"*) printf '%s|%s|%s|%s|canonical-build-context|-|-|-|-|-|-|-|-|-|-' \"$FAKE_HUB_REGISTRY_HEAD\" \"$FAKE_DESIGN_PRODUCT_HEAD\" \"$FAKE_FLEET_MEDIA_FACTORY_HEAD\" \"$FAKE_BUILD_CONTEXT_DOCKERIGNORE_SHA256\"; exit 0;;\n"
        "  *\"InstallLinking state-volume consumer ID parser\"*) exec /usr/bin/python3 \"$@\";;\n"
        "  *\"InstallLinking state-volume consumer parser\"*) exec /usr/bin/python3 \"$@\";;\n"
        "  *\"InstallLinking state-volume inventory publisher\"*) exec /usr/bin/python3 \"$@\";;\n"
        "  *\"InstallLinking state-volume inventory transition verifier\"*) exec /usr/bin/python3 \"$@\";;\n"
        "  *\"InstallLinking live runtime authority readiness publisher\"*) exec /usr/bin/python3 \"$@\";;\n"
        "  *\"Public-edge private snapshot publisher\"*) exec /usr/bin/python3 \"$@\";;\n"
        "  *\"InstallLinking stable private receipt hasher\"*) if [ \"${FAKE_STABLE_HASH_FAIL_ONCE:-0}\" = 1 ] && [ ! -e \"$FAKE_STABLE_HASH_STATE\" ]; then /usr/bin/touch \"$FAKE_STABLE_HASH_STATE\"; exit 83; fi; exec /usr/bin/python3 \"$@\";;\n"
        "  *\"InstallLinking public acceptance evidence publisher\"*) exec /usr/bin/python3 \"$@\";;\n"
        "  *\"InstallLinking post-quiesce attempt receipt classifier\"*) receipt=\"$5\"; [ -f \"$receipt\" ] || exit 86; reproof_mode=\"${FAKE_POSTQUIESCE_MODE:-}\"; reproof_exit=\"${FAKE_POSTQUIESCE_EXIT:-}\"; if [ -z \"$reproof_mode\" ]; then if [ -z \"$reproof_exit\" ] || [ \"$reproof_exit\" = 0 ]; then reproof_mode=pass; else reproof_mode=unknown; fi; fi; [ \"$reproof_mode\" != malformed ] || exit 87; receipt_sha256=\"$(/usr/bin/sha256sum -- \"$receipt\" | /usr/bin/awk '{print $1}')\"; case \"$reproof_mode\" in pass) classification=pass;; safe_fail) classification=safe_fail;; oom|unknown) classification=unknown;; *) exit 88;; esac; printf '%s|%s' \"$classification\" \"$receipt_sha256\"; exit 0;;\n"
        "  *\"InstallLinking post-quiesce runtime authority identity parser\"*) printf '%s|%s' \"$FAKE_INSTALL_LINKING_AUTHORITY_IDENTITY_SHA256\" \"$FAKE_INSTALL_LINKING_RUNTIME_ROLE_SHA256\"; exit 0;;\n"
        "  *\"InstallLinking public acceptance evidence precommit verifier\"*) [ \"${FAKE_POSTDEPLOY_DIGEST_TAMPER:-0}\" != 1 ] || exit 82; shift 4; /usr/bin/sha256sum -- \"$1\" | /usr/bin/awk '{print $1}'; exit 0;;\n"
        "  *\"InstallLinking accepted boundary closure parser\"*) exec /usr/bin/python3 \"$@\";;\n"
        "  *runtimeProofBindSource*) printf '%s\\n' \"$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256\"; exit 0;;\n"
        "esac\n"
        "if [ \"${1:-}\" = -I ] && [ \"${2:-}\" = -c ]; then\n"
        "  case \"${3:-}\" in *\"Public-edge postdeploy code-deploy receipt scanner\"*) exec /usr/bin/python3 \"$@\";; esac\n"
        "  /usr/bin/cat >/dev/null\n"
        "  exit 0\n"
        "fi\n"
        "exec /usr/bin/env python3 \"$@\"\n",
        encoding="utf-8",
    )
    trusted_python.chmod(0o755)
    trusted_docker = trusted_tools / "docker"
    trusted_docker.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ \"${1:-}\" = --context ] && [ \"${2:-}\" = default ]; then shift 2; fi\n"
        "case \"$*\" in\n"
        "  \"context inspect default --format {{.Name}}|{{.Endpoints.docker.Host}}|{{.Endpoints.docker.SkipTLSVerify}}\")\n"
        "    if [ -n \"${FAKE_DOCKER_CONTEXT_PAUSE_READY:-}\" ]; then /usr/bin/touch \"$FAKE_DOCKER_CONTEXT_PAUSE_READY\"; /usr/bin/sleep 30; fi\n"
        "    printf '%s\\n' \"${FAKE_DOCKER_CONTEXT_IDENTITY:-default|unix:///var/run/docker.sock|false}\"; exit 0;;\n"
        "  \"buildx ls --format json\")\n"
        "    if [ -n \"${FAKE_BUILDER_JSON:-}\" ]; then printf '%s\\n' \"$FAKE_BUILDER_JSON\"; else printf '%s\\n' '{\"Current\":true,\"Driver\":\"docker\",\"Name\":\"default\",\"Nodes\":[{\"Endpoint\":\"default\",\"Name\":\"default\",\"Status\":\"running\"}]}'; fi; exit 0;;\n"
        "esac\n"
        "exec /usr/bin/env docker \"$@\"\n",
        encoding="utf-8",
    )
    trusted_docker.chmod(0o755)
    projection_snapshot_root = tmp_path / "public-projection"
    runtime_proof = write_public_projection_snapshot(
        projection_snapshot_root,
        b'{"status":"test"}\n',
    )
    release_channel_receipt = runtime_proof.parent / "RELEASE_CHANNEL.generated.json"
    fake_event_log = tmp_path / "fake-runtime-events.log"
    fake_auto_remove_state = tmp_path / "fake-candidate-auto-remove.state"
    fake_candidate_name_state = tmp_path / "fake-candidate-name.state"
    fake_prior_portal_running_state = tmp_path / "fake-prior-portal-running.state"
    fake_postquiesce_completed_state = tmp_path / "fake-postquiesce-completed.state"
    fake_auto_remove_state.write_text("false\n", encoding="utf-8")
    fake_prior_portal_running_state.write_text("true\n", encoding="utf-8")
    cutover_receipt_root = tmp_path / "install-linking-cutover"
    cutover_receipt_root.mkdir(mode=0o700)
    cutover_boundary = cutover_receipt_root / "INSTALL_LINKING_POSTGRES_CUTOVER_BOUNDARY.json"
    cutover_id = "test-cutover-0001"
    cutover_boundary.write_text(
        json.dumps(
            {
                "candidateImageId": CANDIDATE_PORTAL_IMAGE_ID,
                "candidateToolImageId": CANDIDATE_TOOL_IMAGE_ID,
                "cutoverId": cutover_id,
                "phase": "validate_completed",
                "status": "in_progress",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    cutover_boundary.chmod(0o600)
    active_build_info = cutover_receipt_root / "candidate-build-info.json"
    active_build_info.write_text("{}\n", encoding="utf-8")
    active_build_info.chmod(0o600)
    final_run_receipt = cutover_receipt_root / "cutover-run.json"
    final_run_receipt.write_text('{"status":"pass"}\n', encoding="utf-8")
    final_run_receipt.chmod(0o600)
    final_boundary = tmp_path / "accepted-install-linking-boundary.json"
    final_boundary.write_text(
        json.dumps(
            {
                "candidateImageId": CANDIDATE_PORTAL_IMAGE_ID,
                "candidateToolImageId": CANDIDATE_TOOL_IMAGE_ID,
                "cutoverId": cutover_id,
                "phase": "public_acceptance_completed",
                "status": "pass",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    cutover_boundary_sha256 = hashlib.sha256(cutover_boundary.read_bytes()).hexdigest()
    final_boundary_sha256 = hashlib.sha256(final_boundary.read_bytes()).hexdigest()
    verification_common = {
        "activeBuildInfoPath": str(active_build_info),
        "activeBuildInfoSha256": "7" * 64,
        "boundaryReceiptPath": str(cutover_boundary),
        "candidateImageId": CANDIDATE_PORTAL_IMAGE_ID,
        "candidatePortalTag": f"chummer-run-api:cutover-{'a' * 24}",
        "candidateToolImageId": CANDIDATE_TOOL_IMAGE_ID,
        "candidateToolTag": (
            f"chummer-install-linking-postgres-tool:cutover-{'a' * 24}"
        ),
        "canonicalPortalTagIdBeforeAndAfter": PRIOR_PORTAL_IMAGE_ID,
        "canonicalToolTagIdBeforeAndAfter": PRIOR_TOOL_IMAGE_ID,
        "composeSha256": "8" * 64,
        "contractName": (
            "chummer.install_linking_postgres_cutover_boundary_verification.v1"
        ),
        "cutoverId": cutover_id,
        "envSha256": "9" * 64,
        "finalRunReceiptPath": str(final_run_receipt),
        "finalRunReceiptSha256": "a" * 64,
        "finalRunReceiptStatus": "pass",
        "runnerSha256": "b" * 64,
        "sourceHead": "0" * 40,
        "status": "pass",
    }
    initial_verification = {
        **verification_common,
        "boundaryReceiptSha256": cutover_boundary_sha256,
        "phase": "validate_completed",
    }
    final_verification = {
        **verification_common,
        "boundaryReceiptSha256": final_boundary_sha256,
        "phase": "public_acceptance_completed",
    }
    initial_verification_path = tmp_path / "install-linking-boundary-verification.json"
    final_verification_path = tmp_path / "install-linking-final-verification.json"
    initial_verification_path.write_text(
        json.dumps(initial_verification, sort_keys=True),
        encoding="utf-8",
    )
    final_verification_path.write_text(
        json.dumps(final_verification, sort_keys=True),
        encoding="utf-8",
    )
    deploy_under_test = tmp_path / "deploy_public_edge_portal.sh"
    deploy_script = DEPLOY.read_text(encoding="utf-8")
    deploy_script = deploy_script.replace(
        'readonly TRUSTED_PYTHON="/usr/bin/python3"',
        f'readonly TRUSTED_PYTHON="{trusted_python}"',
    ).replace(
        'readonly TRUSTED_DOCKER="/usr/bin/docker"',
        f'readonly TRUSTED_DOCKER="{trusted_docker}"',
    ).replace(
        'ROOT_DIR="$("$TRUSTED_REALPATH" -e -- "$SCRIPT_DIR/..")"',
        f'ROOT_DIR="{ROOT}"',
    ).replace(
        'CANONICAL_DOCKER_CONFIG_ROOT="/docker/chummercomplete/.state/public-edge-docker-cli"',
        f'CANONICAL_DOCKER_CONFIG_ROOT="{tmp_path / "docker-config"}"',
    ).replace(
        'DEPLOY_LOCK_ROOT="/docker/chummercomplete/.state"',
        f'DEPLOY_LOCK_ROOT="{tmp_path / "lock-state"}"',
    ).replace(
        'CANONICAL_PUBLIC_PROJECTION_SNAPSHOT_ROOT="/docker/chummercomplete/chummer.run-services/.codex-studio/published"',
        f'CANONICAL_PUBLIC_PROJECTION_SNAPSHOT_ROOT="{projection_snapshot_root}"',
    ).replace("PATH=/usr/bin:/bin", 'PATH="$PATH"').replace(
        '"$TRUSTED_ENV" -i', '"$TRUSTED_ENV"'
    )
    deploy_under_test.write_text(deploy_script, encoding="utf-8")
    deploy_under_test.chmod(0o755)
    monkeypatch.setattr(sys.modules[__name__], "DEPLOY", deploy_under_test)
    monkeypatch.setenv("CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD", "0" * 40)
    monkeypatch.setenv(
        "CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY",
        str(cutover_boundary),
    )
    monkeypatch.setenv(
        "CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256",
        cutover_boundary_sha256,
    )
    monkeypatch.setenv(
        "CHUMMER_INSTALL_LINKING_CANDIDATE_IMAGE_ID",
        CANDIDATE_PORTAL_IMAGE_ID,
    )
    monkeypatch.setenv(
        "CHUMMER_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID",
        CANDIDATE_TOOL_IMAGE_ID,
    )
    monkeypatch.setenv(
        "FAKE_INSTALL_LINKING_BOUNDARY_VERIFICATION_JSON",
        str(initial_verification_path),
    )
    monkeypatch.setenv(
        "FAKE_INSTALL_LINKING_FINAL_VERIFICATION_JSON",
        str(final_verification_path),
    )
    monkeypatch.setenv(
        "FAKE_INSTALL_LINKING_FINAL_BOUNDARY",
        str(final_boundary),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF", "refs/remotes/origin/main"
    )
    monkeypatch.setenv("CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM", "1")
    monkeypatch.setenv("CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH", "1")
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256",
        hashlib.sha256(
            (ROOT / "scripts" / "verify_public_edge_deploy_authority.py").read_bytes()
        ).hexdigest(),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT",
        str(release_channel_receipt),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256",
        hashlib.sha256(release_channel_receipt.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT",
        str(projection_snapshot_root),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256",
        hashlib.sha256(runtime_proof.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv("FAKE_RUNTIME_PROOF_FILE", str(runtime_proof))
    monkeypatch.setenv("FAKE_EVENT_LOG", str(fake_event_log))
    monkeypatch.setenv("FAKE_AUTO_REMOVE_STATE", str(fake_auto_remove_state))
    monkeypatch.setenv("FAKE_CANDIDATE_NAME_STATE", str(fake_candidate_name_state))
    monkeypatch.setenv(
        "FAKE_POSTQUIESCE_COMPLETED_STATE",
        str(fake_postquiesce_completed_state),
    )
    monkeypatch.setenv(
        "FAKE_PRIOR_PORTAL_RUNNING_STATE", str(fake_prior_portal_running_state)
    )
    monkeypatch.setenv("FAKE_PRIOR_PORTAL_IMAGE_ID", PRIOR_PORTAL_IMAGE_ID)
    monkeypatch.setenv("FAKE_CANDIDATE_PORTAL_IMAGE_ID", CANDIDATE_PORTAL_IMAGE_ID)
    monkeypatch.setenv("FAKE_CANDIDATE_TOOL_IMAGE_ID", CANDIDATE_TOOL_IMAGE_ID)
    monkeypatch.setenv("FAKE_MISMATCH_PORTAL_IMAGE_ID", MISMATCH_PORTAL_IMAGE_ID)
    monkeypatch.setenv("FAKE_PRIOR_TOOL_IMAGE_ID", PRIOR_TOOL_IMAGE_ID)
    monkeypatch.setenv("FAKE_PRIOR_TUNNEL_IMAGE_ID", PRIOR_TUNNEL_IMAGE_ID)
    monkeypatch.setenv(
        "FAKE_PRIOR_TUNNEL_REPLICA_IMAGE_ID",
        PRIOR_TUNNEL_REPLICA_IMAGE_ID,
    )
    monkeypatch.setenv("FAKE_PRIOR_PORTAL_CONTAINER_ID", PRIOR_PORTAL_CONTAINER_ID)
    monkeypatch.setenv(
        "FAKE_CANDIDATE_PORTAL_CONTAINER_ID", CANDIDATE_PORTAL_CONTAINER_ID
    )
    monkeypatch.setenv("FAKE_PRIOR_TUNNEL_CONTAINER_ID", PRIOR_TUNNEL_CONTAINER_ID)
    monkeypatch.setenv(
        "FAKE_PRIOR_TUNNEL_REPLICA_CONTAINER_ID",
        PRIOR_TUNNEL_REPLICA_CONTAINER_ID,
    )
    monkeypatch.setenv(
        "FAKE_POSTQUIESCE_PROOF_CONTAINER_ID",
        POSTQUIESCE_PROOF_CONTAINER_ID,
    )
    monkeypatch.setenv(
        "FAKE_ORPHAN_STATE_CONSUMER_CONTAINER_ID",
        ORPHAN_STATE_CONSUMER_CONTAINER_ID,
    )
    monkeypatch.setenv(
        "FAKE_CUTOVER_NAME_SUFFIX",
        hashlib.sha256(cutover_id.encode("utf-8")).hexdigest()[:24],
    )
    monkeypatch.setenv("FAKE_HUB_REGISTRY_HEAD", "c" * 40)
    monkeypatch.setenv("FAKE_DESIGN_PRODUCT_HEAD", "d" * 40)
    monkeypatch.setenv("FAKE_FLEET_MEDIA_FACTORY_HEAD", "e" * 40)
    monkeypatch.setenv("FAKE_BUILD_CONTEXT_DOCKERIGNORE_SHA256", "f" * 64)
    monkeypatch.setenv(
        "FAKE_INSTALL_LINKING_AUTHORITY_IDENTITY_SHA256", "1" * 64
    )
    monkeypatch.setenv("FAKE_INSTALL_LINKING_RUNTIME_ROLE_SHA256", "2" * 64)

    build = {
        "context": "/docker/chummercomplete",
        "dockerfile": str(ROOT / "Chummer.Run.Api" / "Dockerfile"),
        "additional_contexts": {
            "run-services-source": str(ROOT),
            "fleet-media-factory-contracts": "/docker/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts",
            "design-product": "/docker/chummercomplete/chummer-design",
        },
    }
    tool_build = {**build, "target": "install-linking-postgres-tool-final"}
    rendered = {
        "name": "chummer6-hub",
        "services": {
            "chummer-portal-volume-init": {"image": "chummer-run-api:local"},
            "chummer-portal": {
                "image": "chummer-run-api:local",
                "build": build,
                "environment": {
                    "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": "false",
                    "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": "false",
                },
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app",
                        "target": "/app",
                        "read_only": True,
                    }
                ],
                "ports": [{"target": 8080, "published": "8091", "protocol": "tcp"}],
            },
            "chummer-install-linking-postgres-admin": {
                "image": "chummer-install-linking-postgres-tool:local",
                "build": tool_build,
            },
            "chummer-install-linking-postgres-import": {
                "image": "chummer-install-linking-postgres-tool:local",
                "build": tool_build,
            },
        },
    }
    path = tmp_path / "rendered-compose.json"
    path.write_text(json.dumps(rendered), encoding="utf-8")
    monkeypatch.setenv("FAKE_COMPOSE_CONFIG_JSON", str(path))
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_COMPOSE_ATTESTATION_OUTPUT",
        str(tmp_path / "compose-runtime-attestation.json"),
    )


def materialize_fake_public_download_journal(
    tmp_path: Path,
    operation_id: str,
    *,
    source_head: str = "0" * 40,
) -> tuple[Path, Path]:
    receipt_root = tmp_path / "lock-state" / "public-edge-deploy-receipts"
    receipt_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    receipt_root.chmod(0o700)
    operation_root = receipt_root / f"chummer-public-download-{operation_id}"
    operation_root.mkdir(mode=0o700, exist_ok=True)
    operation_root.chmod(0o700)
    operation_journal = receipt_root / f"{operation_root.name}.operation.json"
    operation_journal.write_text(
        json.dumps(
            {
                "operation": (
                    "initial-release-shelf-public-download-cutover"
                ),
                "operationRoot": str(operation_root),
                "projectName": operation_root.name,
                "schema": "chummer.public-download-only-operation/v1",
                "sourceHead": source_head,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    operation_journal.chmod(0o600)
    return operation_root, operation_journal


def configure_fake_public_download_retirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id = "retire-test-0001"
    materialize_fake_public_download_journal(tmp_path, operation_id)
    credentials = tmp_path / "cloudflare-credentials.json"
    credentials.write_text(
        '{"apiToken":"test-only-not-a-live-token"}\n',
        encoding="utf-8",
    )
    credentials.chmod(0o600)
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_OPERATION_ID",
        operation_id,
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_FILE",
        str(credentials),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_ACCOUNT_ID",
        "a" * 32,
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_TUNNEL_ID",
        "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF",
        "refs/remotes/origin/main",
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_CANONICAL_PUBLISHER_SHA256",
        "9" * 64,
    )


def configure_fake_public_download_cutover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    operation_id = "cutover-test-0001"
    projection_root = Path(
        os.environ["CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT"]
    )
    (projection_root / "CURRENT.json").chmod(0o644)
    snapshot_sha256 = "a" * 64
    snapshot_id = f"public-projection-{snapshot_sha256}"
    snapshot = projection_root / snapshot_id
    snapshot.mkdir(mode=0o755)
    runtime_proof = snapshot / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    release_channel = snapshot / "RELEASE_CHANNEL.generated.json"
    candidate_authority = (
        snapshot / "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"
    )
    runtime_proof.write_text('{"status":"test"}\n', encoding="utf-8")
    release_channel.write_text('{"status":"test"}\n', encoding="utf-8")
    candidate_authority.write_text(
        '{"candidateImportAuthority":true}\n',
        encoding="utf-8",
    )
    runtime_sha256 = hashlib.sha256(runtime_proof.read_bytes()).hexdigest()
    release_sha256 = hashlib.sha256(release_channel.read_bytes()).hexdigest()
    candidate_sha256 = hashlib.sha256(candidate_authority.read_bytes()).hexdigest()
    resolution = {
        "candidateImportAuthority": True,
        "codeDeploymentAuthority": False,
        "contractName": "chummer.public_projection_current/v1",
        "manifestSha256": "b" * 64,
        "outputs": {
            runtime_proof.name: {
                "name": runtime_proof.name,
                "path": str(runtime_proof),
                "sha256": runtime_sha256,
            },
            release_channel.name: {
                "name": release_channel.name,
                "path": str(release_channel),
                "sha256": release_sha256,
            },
            candidate_authority.name: {
                "name": candidate_authority.name,
                "path": str(candidate_authority),
                "sha256": candidate_sha256,
            },
        },
        "projectionStage": "candidate_import_ready",
        "releaseUploadAuthority": False,
        "snapshotId": snapshot_id,
        "snapshotSha256": snapshot_sha256,
        "status": "candidate_import_ready",
    }
    resolution_path = tmp_path / "candidate-projection-resolution.json"
    resolution_path.write_text(
        json.dumps(resolution, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    credentials = tmp_path / "cloudflare-credentials.json"
    credentials.write_text(
        '{"apiToken":"test-only-not-a-live-token"}\n',
        encoding="utf-8",
    )
    credentials.chmod(0o600)
    candidate_stage = tmp_path / "candidate-stage"
    release_candidate = candidate_stage / "bundle"
    release_candidate.mkdir(parents=True)
    direct_import = candidate_stage / "UNSIGNED_WINDOWS_PREVIEW_DIRECT_IMPORT.generated.json"
    direct_import.write_text('{"status":"pass"}\n', encoding="utf-8")
    migration_authority = tmp_path / "migration-authority.json"
    migration_authority.write_text('{"status":"pass"}\n', encoding="utf-8")
    restoration = tmp_path / "restoration.json"
    restoration.write_text('{"status":"pass"}\n', encoding="utf-8")
    final_gold = tmp_path / "final-gold.json"
    final_gold.write_text('{"status":"pass"}\n', encoding="utf-8")
    fleet = tmp_path / "fleet"
    fleet.mkdir()
    monkeypatch.setenv(
        "FAKE_PUBLIC_DOWNLOAD_PROJECTION_RESOLUTION",
        str(resolution_path),
    )
    monkeypatch.setenv("CHUMMER_PUBLIC_DOWNLOAD_OPERATION_ID", operation_id)
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_FILE",
        str(credentials),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_ACCOUNT_ID",
        "a" * 32,
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_TUNNEL_ID",
        "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY",
        str(migration_authority),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_MIGRATION_AUTHORITY_SHA256",
        hashlib.sha256(migration_authority.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_RELEASE_CANDIDATE_ROOT",
        str(release_candidate),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY",
        str(candidate_authority),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_CANDIDATE_IMPORT_AUTHORITY_SHA256",
        candidate_sha256,
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT",
        str(direct_import),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_DIRECT_IMPORT_RECEIPT_SHA256",
        hashlib.sha256(direct_import.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_MANIFEST_CLOSURE_RESTORATION_SPEC",
        str(restoration),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_MANIFEST_CLOSURE_RESTORATION_SPEC_SHA256",
        hashlib.sha256(restoration.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SOURCE",
        str(final_gold),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_FINAL_GOLD_SHA256",
        hashlib.sha256(final_gold.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv("CHUMMER_PUBLIC_DOWNLOAD_FLEET_SOURCE", str(fleet))
    monkeypatch.setenv("CHUMMER_PUBLIC_DOWNLOAD_FLEET_SHA256", "c" * 64)
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_TREE_SHA256",
        "d" * 64,
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256",
        runtime_sha256,
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT",
        str(release_channel),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256",
        release_sha256,
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_DELIVERY_PHASE",
        "windows-preview",
    )
    return operation_id


def retained_public_edge_lock_artifacts(tmp_path: Path) -> dict[str, Path]:
    lock_root = tmp_path / "lock-state"
    lock = lock_root / "public-edge-mutation.lock"
    token_path = lock / "owner-token"
    token = token_path.read_text(encoding="ascii").strip()
    token_digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    authority_root = lock_root / "public-edge-lock-recovery-receipts"
    return {
        "authorization": (
            authority_root / f"deploy-{token_digest}.owner-token"
        ),
        "binding": authority_root / f"deploy-{token_digest}.binding.json",
        "lease": authority_root / f"deploy-{token_digest}.lease",
        "lock": lock,
        "token": token_path,
    }


def retain_fake_public_download_retirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path]:
    configure_fake_public_download_retirement(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT", "143")
    retained = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover-retire",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert retained.returncode == 76, retained.stderr
    return retained_public_edge_lock_artifacts(tmp_path)


def retain_fake_public_download_precontroller_cutover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, dict[str, Path]]:
    operation_id = configure_fake_public_download_cutover(tmp_path, monkeypatch)
    ready = tmp_path / "bound-controller-descriptor-paused"
    monkeypatch.setenv(
        "FAKE_BOUND_CONTROLLER_DESCRIPTOR_PAUSE_READY",
        str(ready),
    )
    process = subprocess.Popen(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5
        while (
            not ready.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert ready.exists(), "cutover did not reach pinned controller preflight"
        artifacts = retained_public_edge_lock_artifacts(tmp_path)
        os.killpg(process.pid, signal.SIGKILL)
        assert process.wait(timeout=5) == -signal.SIGKILL
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        monkeypatch.delenv(
            "FAKE_BOUND_CONTROLLER_DESCRIPTOR_PAUSE_READY",
            raising=False,
        )
    return operation_id, artifacts


def make_fake_authority_source(
    tmp_path: Path,
    *,
    inject_postdeploy_child_secret_key: bool = False,
    inject_postdeploy_nested_secret_key: str | None = None,
    inject_postdeploy_nested_secret_value: str | None = None,
) -> Path:
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    (source / "Chummer.Run.Api").mkdir()
    (source / "docker-compose.public-edge.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    (source / "Chummer.Run.Api" / "Dockerfile").write_text(
        "FROM scratch\n", encoding="utf-8"
    )
    (source / "scripts" / "validate_public_edge_compose_runtime.py").write_text(
        "import sys\nsys.stdin.read()\n",
        encoding="utf-8",
    )
    for name in (
        "attest_initial_release_shelf_cutover.py",
        "attest_public_edge_compose_source.py",
        "run_install_linking_postgres_cutover.py",
        "materialize_install_linking_cutover_boundary.py",
    ):
        (source / "scripts" / name).write_text(
            "#!/usr/bin/env python3\nraise SystemExit(0)\n",
            encoding="utf-8",
        )
    (source / "scripts" / "verify_public_edge_postdeploy_gate.py").write_text(
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "pathlib.Path(os.environ['FAKE_POSTDEPLOY_LOG']).write_text("
        "json.dumps(args), encoding='utf-8')\n"
        "output = pathlib.Path(args[args.index('--output') + 1])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        "payload = {"
        "'contractName':'chummer.public_edge_postdeploy_gate.v1',"
        "'status':'pass','projectionPurpose':'code-deploy',"
        "'projectionStatus':'review_required',"
        "'projectionStage':'code_deploy_review_required',"
        "'codeDeploymentAuthority':True,'releaseUploadAuthority':False,"
        "'releaseReady':False,"
        "'codeDeployReviewRequiredAuthoritySatisfied':True,"
        "'childReceipts':{}"
        "}\n"
        f"if {inject_postdeploy_child_secret_key!r}:\n"
        "    payload['childReceipts'] = {"
        "'preflight':{'databasePassword':'hunter2'}}\n"
        f"if {inject_postdeploy_nested_secret_key is not None!r}:\n"
        "    payload['roleAliasRouteResults'] = ["
        f"{{{inject_postdeploy_nested_secret_key!r}:'hunter2'}}]\n"
        f"if {inject_postdeploy_nested_secret_value is not None!r}:\n"
        "    payload['roleAliasRouteResults'] = ["
        f"{{'detail':{inject_postdeploy_nested_secret_value!r}}}]\n"
        "output.write_text(json.dumps(payload), encoding='utf-8')\n"
        "raise SystemExit(int(os.environ.get('FAKE_POSTDEPLOY_EXIT', '0')))\n",
        encoding="utf-8",
    )
    projection_verifier = source / "scripts/release/verify_public_projection.py"
    projection_verifier.parent.mkdir()
    projection_verifier.write_bytes(
        (ROOT / "scripts/release/verify_public_projection.py").read_bytes()
    )
    return source


def write_fake_transaction_python(path: Path) -> None:
    path.write_text(
        r'''#!/bin/sh
set -eu
if [ -n "${FAKE_PYTHON_LOG:-}" ]; then printf '%s\n' "$*" >> "$FAKE_PYTHON_LOG"; fi

arg_value() {
  key="$1"
  shift
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "$key" ]; then
      shift
      [ "$#" -gt 0 ] || return 1
      printf '%s' "$1"
      return 0
    fi
    shift
  done
  return 1
}

case "$*" in
  *runtimeProofBindSource*)
    printf '%s\n' "$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256";;
  *"attest_public_edge_compose_source.py capture-environment"*)
    source="$(arg_value --source "$@")"
    receipt="$(arg_value --receipt "$@")"
    /usr/bin/sha256sum -- "$source" | /usr/bin/awk '{print $1}' > "$receipt"
    /usr/bin/chmod 0600 "$receipt";;
  *"attest_public_edge_compose_source.py verify-environment"*)
    source="$(arg_value --source "$@")"
    receipt="$(arg_value --receipt "$@")"
    expected="$(/usr/bin/cat "$receipt")"
    actual="$(/usr/bin/sha256sum -- "$source" | /usr/bin/awk '{print $1}')"
    [ "$actual" = "$expected" ];;
  *"attest_public_edge_compose_source.py capture"*)
    source="$(arg_value --source "$@")"
    snapshot="$(arg_value --snapshot "$@")"
    receipt="$(arg_value --receipt "$@")"
    /usr/bin/cp "$source" "$snapshot"
    /usr/bin/chmod 0600 "$snapshot"
    printf '%s\n' '{"status":"pass"}' > "$receipt"
    /usr/bin/chmod 0600 "$receipt";;
  *"attest_public_edge_compose_source.py verify"*)
    [ -f "$(arg_value --snapshot "$@")" ] || exit 90;;
  *"publish_public_edge_portal_overlay.py --activate"*)
    if [ "${FAKE_MUTATE_COMPOSE_ENV_AFTER_ATTESTATION:-0}" = 1 ]; then
      printf '%s\n' 'CHUMMER_PUBLIC_CANONICAL_ORIGIN=http://stale.invalid' \
        > "$FAKE_COMPOSE_ENV_MUTATION_TARGET"
      /usr/bin/chmod 0600 "$FAKE_COMPOSE_ENV_MUTATION_TARGET"
    fi;;
  *"public_edge_overlay_transaction.py snapshot"*)
    output="$(arg_value --output "$@")"
    printf '%s\n' '{"phase":"prepared"}' > "$output"
    /usr/bin/chmod 0600 "$output"
    printf '%s\n' 'journal:snapshot' >> "$FAKE_EVENT_LOG";;
  *"public_edge_overlay_transaction.py mark-phase"*)
    output="$(arg_value --output "$@")"
    phase="$(arg_value --phase "$@")"
    [ -f "$output" ] || exit 91
    printf '{"phase":"%s"}\n' "$phase" > "$output"
    /usr/bin/chmod 0600 "$output"
    printf 'journal:phase:%s\n' "$phase" >> "$FAKE_EVENT_LOG";;
  *"public_edge_overlay_transaction.py complete"*)
    output="$(arg_value --output "$@")"
    runtime_output="$(arg_value --runtime-authority-output "$@")"
    candidate_id="$(arg_value --candidate-portal-container-id "$@")"
    candidate_name="$(arg_value --candidate-portal-container-name "$@")"
    candidate_image="$(arg_value --candidate-portal-image-id "$@")"
    readiness="$(arg_value --install-linking-authority-readiness "$@")"
    readiness_sha256="$(arg_value --install-linking-authority-readiness-sha256 "$@")"
    [ -f "$output" ] || exit 92
    actual_readiness_sha256="$(/usr/bin/sha256sum -- "$readiness" | /usr/bin/awk '{print $1}')"
    [ "$actual_readiness_sha256" = "$readiness_sha256" ] || exit 93
    printf '{"contractName":"chummer.public-edge.active-runtime-authority/v1","generatedAtUtc":"2026-07-23T00:00:00+00:00","installLinkingAuthorityReadinessPath":"%s","installLinkingAuthorityReadinessSha256":"%s","portal":{"containerId":"%s","containerName":"%s","existed":true,"imageId":"%s","proofAuthorityMountSha256":"%s","proofPublicMountSha256":"%s","wasRunning":true},"status":"pass"}\n' "$readiness" "$readiness_sha256" "$candidate_id" "$candidate_name" "$candidate_image" "$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" "$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" > "$runtime_output"
    /usr/bin/chmod 0600 "$runtime_output"
    /usr/bin/rm -f -- "$output"
    printf '%s\n' 'journal:complete' >> "$FAKE_EVENT_LOG";;
  *public_edge_deploy_recovery.py*)
    snapshot="$(arg_value --snapshot "$@")"
    /usr/bin/rm -f -- "$snapshot"
    printf 'recovery:portal-tag:%s\n' "$FAKE_PRIOR_PORTAL_IMAGE_ID" >> "$FAKE_EVENT_LOG"
    printf 'recovery:tool-tag:%s\n' "$FAKE_PRIOR_TOOL_IMAGE_ID" >> "$FAKE_EVENT_LOG"
    printf '%s\n' 'journal:recovered' >> "$FAKE_EVENT_LOG";;
esac
exit 0
''',
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_fake_blue_green_docker(path: Path) -> None:
    path.write_text(
        r'''#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
printf 'docker:%s\n' "$*" >> "$FAKE_EVENT_LOG"
case "$*" in
  *" config --format json") cat "$FAKE_COMPOSE_CONFIG_JSON"; exit 0;;
  "container ls --all --quiet --no-trunc --filter volume=chummer6-hub_chummer-run-api-state")
    printf '%s\n' "$FAKE_PRIOR_PORTAL_CONTAINER_ID"
    if [ "${FAKE_STATE_VOLUME_CONSUMER_RACE:-}" = orphan_before ]; then
      printf '%s\n' "$FAKE_ORPHAN_STATE_CONSUMER_CONTAINER_ID"
    fi
    if [ -f "$FAKE_POSTQUIESCE_COMPLETED_STATE" ]; then
      printf '%s\n' "$FAKE_POSTQUIESCE_PROOF_CONTAINER_ID"
      if [ "${FAKE_STATE_VOLUME_CONSUMER_RACE:-}" = rw_after ]; then
        printf '%s\n' "$FAKE_ORPHAN_STATE_CONSUMER_CONTAINER_ID"
      fi
    fi
    ;;
  "container inspect --format {{json .Id}}"*" $FAKE_PRIOR_PORTAL_CONTAINER_ID")
    printf '"%s" "/chummer6-hub-chummer-portal-1" "%s" false {"com.docker.compose.oneoff":"False","com.docker.compose.project":"chummer6-hub","com.docker.compose.service":"chummer-portal"} [{"Destination":"/app/state","Name":"chummer6-hub_chummer-run-api-state","RW":true,"Type":"volume"}]\n' "$FAKE_PRIOR_PORTAL_CONTAINER_ID" "$FAKE_PRIOR_PORTAL_IMAGE_ID"
    ;;
  "container inspect --format {{json .Id}}"*" $FAKE_POSTQUIESCE_PROOF_CONTAINER_ID")
    attempt="$(/usr/bin/cat "$FAKE_POSTQUIESCE_COMPLETED_STATE")"
    job_name="postquiesce-${attempt}-prove-local-store-absent"
    job_hash="$(printf '%s' "$job_name" | /usr/bin/sha256sum | /usr/bin/awk '{print substr($1,1,12)}')"
    project_prefix="$(printf '%s' "$FAKE_CUTOVER_NAME_SUFFIX" | /usr/bin/cut -c1-16)"
    container_name="chummer-install-linking-cutover-${FAKE_CUTOVER_NAME_SUFFIX}-${job_name}"
    project="chummer6-ilpg-${project_prefix}-${job_hash}"
    printf '"%s" "/%s" "%s" false {"com.docker.compose.oneoff":"False","com.docker.compose.project":"%s","com.docker.compose.service":"chummer-install-linking-postgres-import-presence-proof"} [{"Destination":"/app/state","Name":"chummer6-hub_chummer-run-api-state","RW":false,"Type":"volume"}]\n' "$FAKE_POSTQUIESCE_PROOF_CONTAINER_ID" "$container_name" "$FAKE_CANDIDATE_TOOL_IMAGE_ID" "$project"
    ;;
  "container inspect --format {{json .Id}}"*" $FAKE_ORPHAN_STATE_CONSUMER_CONTAINER_ID")
    orphan_running=false
    orphan_rw=false
    if [ "${FAKE_STATE_VOLUME_CONSUMER_RACE:-}" = rw_after ]; then
      orphan_running=true
      orphan_rw=true
    fi
    printf '"%s" "/orphan-state-consumer" "%s" %s {"com.docker.compose.oneoff":"False","com.docker.compose.project":"attacker-project","com.docker.compose.service":"chummer-portal"} [{"Destination":"/app/state","Name":"chummer6-hub_chummer-run-api-state","RW":%s,"Type":"volume"}]\n' "$FAKE_ORPHAN_STATE_CONSUMER_CONTAINER_ID" "$FAKE_CANDIDATE_TOOL_IMAGE_ID" "$orphan_running" "$orphan_rw"
    ;;
  "image ls --quiet --no-trunc --filter reference=chummer-run-api:local")
    count="$(grep -c '^image ls --quiet --no-trunc --filter reference=chummer-run-api:local$' "$FAKE_DOCKER_LOG")"
    if [ "$count" -eq 1 ]; then
      printf '%s\n' "$FAKE_PRIOR_PORTAL_IMAGE_ID"
    else
      printf '%s\n' "$FAKE_CANDIDATE_PORTAL_IMAGE_ID"
    fi
    ;;
  "image ls --quiet --no-trunc --filter reference=chummer-install-linking-postgres-tool:local")
    printf '%s\n' "$FAKE_PRIOR_TOOL_IMAGE_ID";;
  "image inspect chummer-run-api:cutover-"*" --format {{.Id}}")
    printf '%s\n' "$FAKE_CANDIDATE_PORTAL_IMAGE_ID";;
  "image inspect chummer-install-linking-postgres-tool:cutover-"*" --format {{.Id}}")
    printf '%s\n' "$FAKE_CANDIDATE_TOOL_IMAGE_ID";;
  "image inspect chummer-run-api:local --format {{.Id}}")
    printf '%s\n' "$FAKE_CANDIDATE_PORTAL_IMAGE_ID";;
  "image inspect chummer-install-linking-postgres-tool:local --format {{.Id}}")
    printf '%s\n' "$FAKE_CANDIDATE_TOOL_IMAGE_ID";;
  "image tag "*)
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = image_promotion ]; then exit 44; fi;;
  *" ps --all -q chummer-portal")
    printf '%s\n' "$FAKE_PRIOR_PORTAL_CONTAINER_ID";;
  *" ps --all -q chummer-run-cloudflared")
    printf '%s\n' "$FAKE_PRIOR_TUNNEL_CONTAINER_ID";;
  *" ps --all -q chummer-run-cloudflared-replica")
    printf '%s\n' "$FAKE_PRIOR_TUNNEL_REPLICA_CONTAINER_ID";;
  "container inspect --format {{.Id}} $FAKE_PRIOR_PORTAL_CONTAINER_ID")
    printf '%s\n' "$FAKE_PRIOR_PORTAL_CONTAINER_ID";;
  "container inspect --format {{.Image}} $FAKE_PRIOR_PORTAL_CONTAINER_ID")
    printf '%s\n' "$FAKE_PRIOR_PORTAL_IMAGE_ID";;
  "container inspect --format {{.Name}} $FAKE_PRIOR_PORTAL_CONTAINER_ID")
    printf '%s\n' '/chummer6-hub-chummer-portal-1';;
  "container inspect --format {{.State.Running}} $FAKE_PRIOR_PORTAL_CONTAINER_ID")
    if [ -n "${FAKE_PRIOR_PORTAL_RUNNING:-}" ]; then
      printf '%s\n' "$FAKE_PRIOR_PORTAL_RUNNING"
    else
      /usr/bin/cat "$FAKE_PRIOR_PORTAL_RUNNING_STATE"
    fi;;
  "container exec $FAKE_PRIOR_PORTAL_CONTAINER_ID /usr/bin/sha256sum -- "*)
    printf '%s  %s\n' "$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" "${*##* }";;
  "container cp $FAKE_PRIOR_PORTAL_CONTAINER_ID:"*)
    for target in "$@"; do :; done
    /usr/bin/cp "$FAKE_RUNTIME_PROOF_FILE" "$target";;
  "container ls --all --quiet --no-trunc --filter name=^/chummer-public-edge-candidate-"*)
    ;;
  "container inspect --format {{.Id}} chummer-public-edge-candidate-"*)
    printf '%s\n' "$FAKE_CANDIDATE_PORTAL_CONTAINER_ID";;
  "container inspect --format {{.Id}} $FAKE_PRIOR_TUNNEL_CONTAINER_ID")
    printf '%s\n' "$FAKE_PRIOR_TUNNEL_CONTAINER_ID";;
  "container inspect --format {{.Image}} $FAKE_PRIOR_TUNNEL_CONTAINER_ID")
    printf '%s\n' "$FAKE_PRIOR_TUNNEL_IMAGE_ID";;
  "container inspect --format {{.State.Running}} $FAKE_PRIOR_TUNNEL_CONTAINER_ID")
    printf '%s\n' true;;
  "container inspect --format {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} $FAKE_PRIOR_TUNNEL_CONTAINER_ID")
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = tunnel_health ]; then
      printf '%s\n' unhealthy
    else
      printf '%s\n' healthy
    fi;;
  "container inspect --format {{.Id}} $FAKE_PRIOR_TUNNEL_REPLICA_CONTAINER_ID")
    printf '%s\n' "$FAKE_PRIOR_TUNNEL_REPLICA_CONTAINER_ID";;
  "container inspect --format {{.Image}} $FAKE_PRIOR_TUNNEL_REPLICA_CONTAINER_ID")
    printf '%s\n' "$FAKE_PRIOR_TUNNEL_REPLICA_IMAGE_ID";;
  "container inspect --format {{.State.Running}} $FAKE_PRIOR_TUNNEL_REPLICA_CONTAINER_ID")
    printf '%s\n' true;;
  "container inspect --format {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} $FAKE_PRIOR_TUNNEL_REPLICA_CONTAINER_ID")
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = tunnel_replica_health ]; then
      printf '%s\n' unhealthy
    else
      printf '%s\n' healthy
    fi;;
  "buildx build "*)
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = build ]; then exit 44; fi;;
  *" stop chummer-run-cloudflared")
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = tunnel_stop ]; then exit 43; fi;;
  *" stop chummer-run-cloudflared-replica")
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = tunnel_replica_stop ]; then exit 43; fi;;
  "container stop $FAKE_PRIOR_PORTAL_CONTAINER_ID")
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = portal_stop ]; then exit 43; fi
    printf '%s\n' false > "$FAKE_PRIOR_PORTAL_RUNNING_STATE";;
  *" run --rm --no-deps chummer-portal-volume-init")
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = initializer ]; then exit 37; fi;;
  *" run -T -d "*"chummer-public-edge-candidate-"*)
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = candidate_creation ]; then exit 41; fi
    case " $* " in
      *" --rm "*) printf '%s\n' true > "$FAKE_AUTO_REMOVE_STATE";;
      *) printf '%s\n' false > "$FAKE_AUTO_REMOVE_STATE";;
    esac
    previous=
    for argument in "$@"; do
      if [ "$previous" = --name ]; then
        printf '%s\n' "$argument" > "$FAKE_CANDIDATE_NAME_STATE"
        break
      fi
      previous="$argument"
    done
    printf '%s\n' "$FAKE_CANDIDATE_PORTAL_CONTAINER_ID";;
  "container inspect --format {{.Id}} $FAKE_CANDIDATE_PORTAL_CONTAINER_ID")
    printf '%s\n' "$FAKE_CANDIDATE_PORTAL_CONTAINER_ID";;
  "container inspect --format {{.Name}} $FAKE_CANDIDATE_PORTAL_CONTAINER_ID")
    printf '/%s\n' "$(/usr/bin/cat "$FAKE_CANDIDATE_NAME_STATE")";;
  "container inspect --format {{.State.Running}} $FAKE_CANDIDATE_PORTAL_CONTAINER_ID")
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = candidate_readiness ]; then printf '%s\n' false; else printf '%s\n' true; fi;;
  "container inspect --format {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} $FAKE_CANDIDATE_PORTAL_CONTAINER_ID")
    printf '%s\n' healthy;;
  "container exec $FAKE_CANDIDATE_PORTAL_CONTAINER_ID dotnet /app/loopback-probe/Chummer.Run.LoopbackProbe.dll /api/ready/install-linking-authority")
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = install_linking_authority_readiness ]; then exit 45; fi
    readiness_mode="${FAKE_INSTALL_LINKING_AUTHORITY_MODE:-pass}"
    readiness_authority="$FAKE_INSTALL_LINKING_AUTHORITY_IDENTITY_SHA256"
    readiness_extra=
    case "$readiness_mode" in
      pass) ;;
      hash_mismatch) readiness_authority="3333333333333333333333333333333333333333333333333333333333333333";;
      extra_field) readiness_extra=',"unexpected":true';;
      malformed) printf '%s' '{malformed'; exit 0;;
      http_503) printf '%s' '{"status":"fail"}'; exit 22;;
      *) exit 89;;
    esac
    printf '{"authorityIdentitySha256":"%s","checkedAtUtc":"%s","code":"runtime_role_least_privilege","contractName":"chummer.install_linking_postgres_runtime_authority_readiness.v1","currentRoleMatches":true,"leastPrivilegeValid":true,"ready":true,"runtimeRoleSha256":"%s","status":"pass"%s}' "$readiness_authority" "${FAKE_INSTALL_LINKING_AUTHORITY_CHECKED_AT:-2026-07-23T00:00:00+00:00}" "$FAKE_INSTALL_LINKING_RUNTIME_ROLE_SHA256" "$readiness_extra"
    ;;
  "container exec $FAKE_CANDIDATE_PORTAL_CONTAINER_ID dotnet /app/loopback-probe/Chummer.Run.LoopbackProbe.dll /api/ready/publication")
    if [ "${FAKE_DOCKER_FAILURE_PHASE:-}" = publication_readiness ]; then exit 45; fi
    printf '%s' '{"ready":true}';;
  "container exec $FAKE_CANDIDATE_PORTAL_CONTAINER_ID /usr/bin/sha256sum -- "*)
    printf '%s  %s\n' "$CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256" "${*##* }";;
  "container inspect --format {{.Image}} $FAKE_CANDIDATE_PORTAL_CONTAINER_ID")
    if [ "${FAKE_CANDIDATE_MISMATCH:-0}" = 1 ]; then
      printf '%s\n' "$FAKE_MISMATCH_PORTAL_IMAGE_ID"
    else
      printf '%s\n' "$FAKE_CANDIDATE_PORTAL_IMAGE_ID"
    fi;;
  "container inspect --format {{json .NetworkSettings.Networks}} $FAKE_CANDIDATE_PORTAL_CONTAINER_ID")
    printf '%s\n' '{"default":{"Aliases":["chummer-portal"]}}';;
  "container start $FAKE_PRIOR_TUNNEL_CONTAINER_ID") ;;
  "container start $FAKE_PRIOR_TUNNEL_REPLICA_CONTAINER_ID") ;;
  "container update --restart unless-stopped $FAKE_CANDIDATE_PORTAL_CONTAINER_ID")
    if [ "$(/usr/bin/cat "$FAKE_AUTO_REMOVE_STATE")" = true ]; then exit 64; fi
    printf '%s\n' 'candidate:restart-policy:unless-stopped' >> "$FAKE_EVENT_LOG";;
  "container rm $FAKE_PRIOR_PORTAL_CONTAINER_ID") ;;
esac
exit 0
''',
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_fake_daemon_rejects_restart_policy_for_auto_remove_candidate(
    tmp_path: Path,
) -> None:
    fake_docker = tmp_path / "docker"
    write_fake_blue_green_docker(fake_docker)
    env = os.environ.copy()
    env["FAKE_DOCKER_LOG"] = str(tmp_path / "docker.log")

    create = subprocess.run(
        [
            str(fake_docker),
            "compose",
            "run",
            "-T",
            "-d",
            "--rm",
            "--no-deps",
            "--service-ports",
            "--use-aliases",
            "--name",
            "chummer-public-edge-candidate-autoremove",
            "chummer-portal",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    promote = subprocess.run(
        [
            str(fake_docker),
            "container",
            "update",
            "--restart",
            "unless-stopped",
            CANDIDATE_PORTAL_CONTAINER_ID,
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert create.returncode == 0
    assert create.stdout.strip() == CANDIDATE_PORTAL_CONTAINER_ID
    assert Path(env["FAKE_AUTO_REMOVE_STATE"]).read_text(encoding="utf-8") == "true\n"
    assert promote.returncode == 64


def test_source_replay_preflight_failure_stops_before_quiesce(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    trusted_python_log = tmp_path / "trusted-python.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_TRUSTED_PYTHON_LOG": str(trusted_python_log),
            "FAKE_SOURCE_REPLAY_PREFLIGHT_EXIT": "1",
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert (
        "candidate build-source replay preflight failed"
        in result.stderr
    )
    trusted_commands = trusted_python_log.read_text(
        encoding="utf-8"
    ).splitlines()
    assert any("--source-replay-preflight" in command for command in trusted_commands)
    assert not any("--post-quiesce-reproof" in command for command in trusted_commands)
    docker_commands = (
        docker_log.read_text(encoding="utf-8").splitlines()
        if docker_log.exists()
        else []
    )
    assert not any("container stop" in command for command in docker_commands)
    assert not any(command.startswith("image tag ") for command in docker_commands)


@pytest.mark.parametrize(
    ("operation", "authority_kind"),
    [
        ("deploy", "file"),
        ("deploy", "broken_symlink"),
        ("initial-release-shelf-cutover", "file"),
        ("initial-release-shelf-cutover", "broken_symlink"),
    ],
)
def test_topology_b_authority_blocks_fresh_canonical_mutation_before_lock_or_quiesce(
    tmp_path: Path,
    operation: str,
    authority_kind: str,
) -> None:
    receipt_root = tmp_path / "lock-state" / "public-edge-deploy-receipts"
    receipt_root.mkdir(parents=True)
    authority = receipt_root / "public-download-active-runtime-authority.json"
    if authority_kind == "file":
        authority.write_text("{}\n", encoding="utf-8")
    else:
        authority.symlink_to(tmp_path / "missing-topology-b-authority.json")
    docker_log = tmp_path / "docker.log"
    trusted_python_log = tmp_path / "trusted-python.log"
    env = os.environ.copy()
    env.update(
        {
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_TRUSTED_PYTHON_LOG": str(trusted_python_log),
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY), operation],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert TOPOLOGY_B_GUARD_MESSAGE in result.stderr
    assert (
        "initial-release-shelf-public-download-cutover-retire"
        in result.stderr
    )
    assert not (tmp_path / "lock-state" / "public-edge-mutation.lock").exists()
    assert set(receipt_root.iterdir()) == {authority}
    assert not Path(env["FAKE_EVENT_LOG"]).exists()
    assert not docker_log.exists()
    trusted_commands = trusted_python_log.read_text(
        encoding="utf-8"
    ).splitlines()
    assert not any("--source-replay-preflight" in command for command in trusted_commands)
    assert not any("--post-quiesce-reproof" in command for command in trusted_commands)


@pytest.mark.parametrize(
    "operation",
    [
        "recover",
        "initial-release-shelf-cutover-recover",
        "initial-release-shelf-public-download-cutover",
        "initial-release-shelf-public-download-cutover-recover",
        "initial-release-shelf-public-download-cutover-retire",
    ],
)
def test_topology_b_guard_allows_supported_recovery_and_download_routes(
    tmp_path: Path,
    operation: str,
) -> None:
    receipt_root = tmp_path / "lock-state" / "public-edge-deploy-receipts"
    receipt_root.mkdir(parents=True)
    (
        receipt_root / "public-download-active-runtime-authority.json"
    ).write_text("{}\n", encoding="utf-8")
    env = os.environ.copy()
    env["CHUMMER_PUBLIC_EDGE_COMPOSE_FILE"] = str(
        tmp_path / "deliberately-missing-compose.yml"
    )

    result = subprocess.run(
        ["bash", str(DEPLOY), operation],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert TOPOLOGY_B_GUARD_MESSAGE not in result.stderr
    assert "requires the exact owner-controlled single-link Compose input" in result.stderr


@pytest.mark.parametrize(
    "operation",
    ["deploy", "initial-release-shelf-cutover"],
)
def test_topology_b_guard_allows_canonical_transaction_recovery(
    tmp_path: Path,
    operation: str,
) -> None:
    receipt_root = tmp_path / "lock-state" / "public-edge-deploy-receipts"
    receipt_root.mkdir(parents=True)
    (
        receipt_root / "public-download-active-runtime-authority.json"
    ).write_text("{}\n", encoding="utf-8")
    (
        receipt_root / "active-overlay-transaction.json"
    ).write_text("{}\n", encoding="utf-8")
    env = os.environ.copy()
    env["CHUMMER_PUBLIC_EDGE_COMPOSE_FILE"] = str(
        tmp_path / "deliberately-missing-compose.yml"
    )

    result = subprocess.run(
        ["bash", str(DEPLOY), operation],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert TOPOLOGY_B_GUARD_MESSAGE not in result.stderr
    assert "requires the exact owner-controlled single-link Compose input" in result.stderr


def test_guarded_deploy_happy_path_promotes_candidate_then_commits_and_cleans_up(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    trusted_python_log = tmp_path / "trusted-python.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_TRUSTED_PYTHON_LOG": str(trusted_python_log),
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"public_edge_portal_deployed {CANDIDATE_PORTAL_IMAGE_ID}"
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    candidate_create = next(
        command
        for command in commands
        if " run -T -d " in command
        and " --name chummer-public-edge-candidate-" in command
    )
    assert " --rm " not in f" {candidate_create} "
    assert candidate_create.endswith(" chummer-portal")
    assert (
        f"container update --restart unless-stopped {CANDIDATE_PORTAL_CONTAINER_ID}"
        in commands
    )
    assert not any("/usr/bin/curl" in command for command in commands)
    assert any(
        command.endswith("Chummer.Run.LoopbackProbe.dll /api/ready/publication")
        for command in commands
    )
    assert any(
        command.endswith(
            "Chummer.Run.LoopbackProbe.dll "
            "/api/ready/install-linking-authority"
        )
        for command in commands
    )
    assert Path(env["FAKE_AUTO_REMOVE_STATE"]).read_text(encoding="utf-8") == "false\n"
    cutover_root = Path(env["CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY"]).parent
    readiness_files = list(
        cutover_root.glob("install-linking-authority-readiness-*.json")
    )
    assert len(readiness_files) == 1
    readiness_path = readiness_files[0]
    readiness_bytes = readiness_path.read_bytes()
    readiness_sha256 = hashlib.sha256(readiness_bytes).hexdigest()
    readiness = json.loads(readiness_bytes)
    assert set(readiness) == {
        "authorityIdentitySha256",
        "checkedAtUtc",
        "code",
        "contractName",
        "currentRoleMatches",
        "leastPrivilegeValid",
        "ready",
        "runtimeRoleSha256",
        "status",
    }
    assert (
        readiness["authorityIdentitySha256"]
        == env["FAKE_INSTALL_LINKING_AUTHORITY_IDENTITY_SHA256"]
    )
    assert (
        readiness["runtimeRoleSha256"]
        == env["FAKE_INSTALL_LINKING_RUNTIME_ROLE_SHA256"]
    )
    assert readiness_path.stat().st_mode & 0o777 == 0o600
    private_active_runtime_files = list(cutover_root.glob("active-runtime-*.json"))
    assert len(private_active_runtime_files) == 1
    private_active_runtime = json.loads(
        private_active_runtime_files[0].read_text(encoding="utf-8")
    )
    assert (
        private_active_runtime["installLinkingAuthorityReadinessPath"]
        == str(readiness_path)
    )
    assert (
        private_active_runtime["installLinkingAuthorityReadinessSha256"]
        == readiness_sha256
    )
    complete_command = next(
        command
        for command in python_log.read_text(encoding="utf-8").splitlines()
        if "public_edge_overlay_transaction.py complete" in command
    )
    assert f"--install-linking-authority-readiness {readiness_path}" in complete_command
    assert (
        f"--install-linking-authority-readiness-sha256 {readiness_sha256}"
        in complete_command
    )

    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    journal_events = [event for event in events if event.startswith("journal:")]
    assert journal_events == [
        "journal:snapshot",
        "journal:phase:image_build_started",
        "journal:phase:image_built",
        "journal:phase:tunnel_drained",
        "journal:phase:portal_stopped",
        "journal:phase:overlay_activated",
        "journal:phase:portal_candidate_started",
        "journal:phase:tunnel_started",
        "journal:complete",
    ]
    complete_index = events.index("journal:complete")
    restart_policy_index = events.index("candidate:restart-policy:unless-stopped")
    final_prior_inspect_index = max(
        index
        for index, event in enumerate(events)
        if event
        == "docker:container inspect --format {{.State.Running}} "
        f"{PRIOR_PORTAL_CONTAINER_ID}"
    )
    cleanup_index = events.index(f"docker:container rm {PRIOR_PORTAL_CONTAINER_ID}")
    assert restart_policy_index < complete_index < final_prior_inspect_index < cleanup_index
    assert not (
        tmp_path
        / "lock-state"
        / "public-edge-deploy-receipts"
        / "active-overlay-transaction.json"
    ).exists()
    assert postdeploy_log.is_file()


def test_guarded_deploy_detects_env_drift_after_attestation_and_recovers_before_create(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    environment_file = tmp_path / "public-edge.env"
    environment_file.write_text(
        "CHUMMER_PUBLIC_CANONICAL_ORIGIN=https://chummer.run\n",
        encoding="utf-8",
    )
    environment_file.chmod(0o600)
    deploy_under_test = tmp_path / "deploy-env-binding.sh"
    original_environment_literal = (
        'CANONICAL_ENV_FILE="/docker/chummercomplete/chummer.run-services/.env"'
    )
    deploy_source = Path(DEPLOY).read_text(encoding="utf-8")
    assert original_environment_literal in deploy_source
    deploy_under_test.write_text(
        deploy_source.replace(
            original_environment_literal,
            f'CANONICAL_ENV_FILE="{environment_file}"',
        ),
        encoding="utf-8",
    )
    deploy_under_test.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_MUTATE_COMPOSE_ENV_AFTER_ATTESTATION": "1",
            "FAKE_COMPOSE_ENV_MUTATION_TARGET": str(environment_file),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": str(environment_file),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(deploy_under_test)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "source or environment changed before a guarded read" in result.stderr
    assert "volume initialization failed" in result.stderr
    commands = (
        docker_log.read_text(encoding="utf-8").splitlines()
        if docker_log.exists()
        else []
    )
    assert not any("chummer-portal-volume-init" in command for command in commands)
    python_commands = python_log.read_text(encoding="utf-8").splitlines()
    assert any(
        "publish_public_edge_portal_overlay.py --activate" in command
        for command in python_commands
    )
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:phase:overlay_activated" in events
    assert "journal:recovered" in events
    assert "journal:complete" not in events


@pytest.mark.parametrize(
    ("mode", "checked_at"),
    (
        ("hash_mismatch", None),
        ("extra_field", None),
        ("malformed", None),
        ("http_503", None),
        ("pass", "2026-07-23T01:00:00+01:00"),
    ),
)
def test_guarded_deploy_rejects_unbound_runtime_authority_readiness(
    tmp_path: Path,
    mode: str,
    checked_at: str | None,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_INSTALL_LINKING_AUTHORITY_MODE": mode,
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                ROOT / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )
    if checked_at is not None:
        env["FAKE_INSTALL_LINKING_AUTHORITY_CHECKED_AT"] = checked_at

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "InstallLinking runtime authority readiness failed" in result.stderr
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert any(
        command.endswith(
            "Chummer.Run.LoopbackProbe.dll "
            "/api/ready/install-linking-authority"
        )
        for command in commands
    )
    assert not any("/usr/bin/curl" in command for command in commands)
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:phase:portal_candidate_started" in events
    assert "journal:complete" not in events
    assert "journal:recovered" in events
    assert not (tmp_path / "lock-state" / "public-edge-mutation.lock").exists()
    cutover_root = Path(env["CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY"]).parent
    assert not list(
        cutover_root.glob("install-linking-authority-readiness-*.json")
    )
    assert "public_edge_overlay_transaction.py complete" not in python_log.read_text(
        encoding="utf-8"
    )


def test_guarded_deploy_reconciles_materializer_publish_then_nonzero_without_rollback(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    trusted_python_log = tmp_path / "trusted-python.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_TRUSTED_PYTHON_LOG": str(trusted_python_log),
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "FAKE_INSTALL_LINKING_MATERIALIZER_EXIT": "74",
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        f"public_edge_portal_deployed {CANDIDATE_PORTAL_IMAGE_ID}"
    )
    assert (
        "install_linking_public_acceptance_materializer_reconciled "
        "exit_status=74 boundary_sha256="
    ) in result.stderr
    boundary = json.loads(
        Path(env["CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY"]).read_text(
            encoding="utf-8"
        )
    )
    assert boundary["phase"] == "public_acceptance_completed"
    assert boundary["status"] == "pass"
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:complete" in events
    assert "journal:recovered" not in events
    trusted_commands = trusted_python_log.read_text(encoding="utf-8").splitlines()
    assert any(
        "materialize_install_linking_cutover_boundary.py" in command
        and "--phase public_acceptance_completed" in command
        for command in trusted_commands
    )
    assert any(
        "verify_install_linking_cutover_boundary.py" in command
        and "--expected-phase public_acceptance_completed" in command
        for command in trusted_commands
    )


def test_guarded_deploy_rolls_back_nonzero_materializer_with_mismatched_boundary(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    env = os.environ.copy()
    Path(env["FAKE_INSTALL_LINKING_FINAL_BOUNDARY"]).write_text(
        '{"phase":"public_acceptance_completed","status":"pass","tampered":true}\n',
        encoding="utf-8",
    )
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "FAKE_INSTALL_LINKING_MATERIALIZER_EXIT": "74",
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 70
    assert "materializer exact reconciliation failed" in result.stderr
    assert "materializer_reconciled" not in result.stderr
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:complete" in events
    assert "journal:recovered" in events
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert not any(command.startswith("image rm ") for command in commands)


def test_guarded_deploy_exit_trap_reconciles_accepted_boundary_before_rollback(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    stable_hash_state = tmp_path / "stable-hash-failed-once"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "FAKE_INSTALL_LINKING_MATERIALIZER_EXIT": "74",
            "FAKE_STABLE_HASH_FAIL_ONCE": "1",
            "FAKE_STABLE_HASH_STATE": str(stable_hash_state),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 70
    assert "materializer exact reconciliation failed" in result.stderr
    assert "install_linking_public_acceptance_exit_reconciled" in result.stderr
    assert stable_hash_state.is_file()
    boundary = json.loads(
        Path(env["CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY"]).read_text(
            encoding="utf-8"
        )
    )
    assert boundary["phase"] == "public_acceptance_completed"
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:complete" in events
    assert "journal:recovered" not in events
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert not any(command.startswith("image rm ") for command in commands)


@pytest.mark.parametrize("mutation", ("digest", "symlink"))
def test_guarded_deploy_rejects_boundary_path_or_digest_tamper_before_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    boundary = Path(os.environ["CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY"])
    env = os.environ.copy()
    if mutation == "digest":
        boundary.write_bytes(boundary.read_bytes() + b" ")
        expected_message = "boundary verification failed before Docker mutation"
    else:
        alias = tmp_path / "boundary-alias.json"
        alias.symlink_to(boundary)
        env["CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY"] = str(alias)
        expected_message = "exact existing non-aliased path"

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert expected_message in result.stderr


def test_guarded_deploy_rejects_unique_candidate_id_mismatch_before_tag_mutation(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_CANDIDATE_PORTAL_IMAGE_ID": MISMATCH_PORTAL_IMAGE_ID,
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                ROOT / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "differs from its independent pin" in result.stderr
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert any(
        command.startswith("image inspect chummer-run-api:cutover-")
        for command in commands
    )
    assert not any(command.startswith("image tag ") for command in commands)
    assert not any(command.endswith(" stop chummer-run-cloudflared") for command in commands)


def test_guarded_deploy_snapshots_a_t_promotes_b_u_and_retains_on_unknown_reproof(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_POSTQUIESCE_EXIT": "70",
            "FAKE_POSTQUIESCE_REASON": "remote_generation_changed",
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                ROOT / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 70
    snapshot_command = next(
        command
        for command in python_log.read_text(encoding="utf-8").splitlines()
        if "public_edge_overlay_transaction.py snapshot" in command
    )
    assert f"--prior-image-tag-id {PRIOR_PORTAL_IMAGE_ID}" in snapshot_command
    assert f"--prior-tool-image-tag-id {PRIOR_TOOL_IMAGE_ID}" in snapshot_command
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    portal_promotion = next(
        index
        for index, event in enumerate(events)
        if event.startswith("docker:image tag chummer-run-api:cutover-")
    )
    tool_promotion = next(
        index
        for index, event in enumerate(events)
        if event.startswith(
            "docker:image tag chummer-install-linking-postgres-tool:cutover-"
        )
    )
    assert events.index("journal:snapshot") < portal_promotion < tool_promotion
    assert "journal:phase:overlay_activated" not in events
    assert "journal:recovered" not in events
    lock_root = tmp_path / "lock-state"
    assert (lock_root / "public-edge-mutation.lock").is_dir()
    assert (
        lock_root
        / "public-edge-deploy-receipts"
        / "active-overlay-transaction.json"
    ).is_file()


@pytest.mark.parametrize(
    "reason",
    ("local_store_reappeared", "remote_generation_changed"),
)
def test_guarded_deploy_postquiesce_state_change_blocks_candidate_activation(
    tmp_path: Path,
    reason: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    trusted_python_log = tmp_path / "trusted-python.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_TRUSTED_PYTHON_LOG": str(trusted_python_log),
            "FAKE_POSTQUIESCE_EXIT": "1",
            "FAKE_POSTQUIESCE_REASON": reason,
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                ROOT / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 70
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:phase:portal_stopped" in events
    assert "journal:phase:overlay_activated" not in events
    assert "journal:recovered" not in events
    lock_root = tmp_path / "lock-state"
    assert (lock_root / "public-edge-mutation.lock").is_dir()
    assert (
        lock_root
        / "public-edge-deploy-receipts"
        / "active-overlay-transaction.json"
    ).is_file()
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert not any(" run -T -d " in command for command in commands)
    assert "materialize_install_linking_cutover_boundary.py" not in trusted_python_log.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "mode",
    ("sigkill", "oom", "missing", "malformed"),
)
def test_guarded_deploy_retains_authority_without_verified_postquiesce_outcome(
    tmp_path: Path,
    mode: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_POSTQUIESCE_MODE": mode,
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                ROOT / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 70
    assert "unknown_authority_retained" in result.stderr
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:phase:portal_stopped" in events
    assert "journal:phase:overlay_activated" not in events
    assert "journal:recovered" not in events
    lock_root = tmp_path / "lock-state"
    assert (lock_root / "public-edge-mutation.lock").is_dir()
    assert (
        lock_root
        / "public-edge-deploy-receipts"
        / "active-overlay-transaction.json"
    ).is_file()


def test_guarded_deploy_rolls_back_only_verified_postquiesce_safe_fail(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_POSTQUIESCE_MODE": "safe_fail",
            "FAKE_POSTQUIESCE_EXIT": "70",
            "FAKE_POSTQUIESCE_REASON": "pre_start_validation_failed",
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                ROOT / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "verified safe failure (runner exit 70)" in result.stderr
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:phase:portal_stopped" in events
    assert "journal:phase:overlay_activated" not in events
    assert "journal:recovered" in events
    assert not (tmp_path / "lock-state" / "public-edge-mutation.lock").exists()


def test_guarded_deploy_accepts_verified_postquiesce_pass_despite_runner_exit(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "FAKE_POSTQUIESCE_MODE": "pass",
            "FAKE_POSTQUIESCE_EXIT": "42",
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:phase:overlay_activated" in events
    assert "journal:complete" in events
    assert "journal:recovered" not in events


def test_guarded_deploy_rejects_orphan_state_volume_consumer_before_reproof(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    trusted_python_log = tmp_path / "trusted-python.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_TRUSTED_PYTHON_LOG": str(trusted_python_log),
            "FAKE_STATE_VOLUME_CONSUMER_RACE": "orphan_before",
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                ROOT / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "post-quiesce state-volume consumer inventory failed" in result.stderr
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:phase:portal_stopped" in events
    assert "journal:phase:overlay_activated" not in events
    assert "journal:recovered" in events
    trusted_commands = trusted_python_log.read_text(encoding="utf-8").splitlines()
    assert not any(
        "run_install_linking_postgres_cutover.py" in command
        and "--post-quiesce-reproof" in command
        for command in trusted_commands
    )


def test_guarded_deploy_retains_authority_on_postreproof_rw_volume_consumer_race(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_STATE_VOLUME_CONSUMER_RACE": "rw_after",
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                ROOT / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 70
    assert "pre-activation state-volume consumer inventory is unknown" in result.stderr
    assert "unknown_authority_retained" in result.stderr
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:phase:portal_stopped" in events
    assert "journal:phase:overlay_activated" not in events
    assert "journal:recovered" not in events
    lock_root = tmp_path / "lock-state"
    assert (lock_root / "public-edge-mutation.lock").is_dir()
    assert (
        lock_root
        / "public-edge-deploy-receipts"
        / "active-overlay-transaction.json"
    ).is_file()
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert any(
        command.endswith(f" {ORPHAN_STATE_CONSUMER_CONTAINER_ID}")
        and command.startswith("container inspect --format {{json .Id}}")
        for command in commands
    )


def test_guarded_deploy_fabricated_postdeploy_digest_cannot_finalize_acceptance(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    trusted_python_log = tmp_path / "trusted-python.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "FAKE_POSTDEPLOY_DIGEST_TAMPER": "1",
            "FAKE_TRUSTED_PYTHON_LOG": str(trusted_python_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "public acceptance evidence verification failed" in result.stderr
    trusted_commands = trusted_python_log.read_text(encoding="utf-8").splitlines()
    assert not any(
        "materialize_install_linking_cutover_boundary.py" in command
        for command in trusted_commands
    )
    boundary = json.loads(
        Path(env["CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY"]).read_text(
            encoding="utf-8"
        )
    )
    assert boundary["phase"] == "validate_completed"
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:complete" in events
    assert "journal:recovered" in events


@pytest.mark.parametrize(
    ("missing_name", "message"),
    (
        (
            "CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH",
            "requires /usr/bin/env -i",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD",
            "externally supplied as a full 40-hex commit",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF",
            "full refs/remotes/... authority",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256",
            "independently supplied full SHA-256",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256",
            "independently supplied as a lowercase SHA-256",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT",
            "must be externally supplied",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256",
            "externally supplied as a lowercase SHA-256",
        ),
        (
            "CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY",
            "must be an absolute private receipt path",
        ),
        (
            "CHUMMER_INSTALL_LINKING_CUTOVER_BOUNDARY_SHA256",
            "independently supplied lowercase SHA-256",
        ),
        (
            "CHUMMER_INSTALL_LINKING_CANDIDATE_IMAGE_ID",
            "independently supplied full image ID",
        ),
        (
            "CHUMMER_INSTALL_LINKING_CANDIDATE_TOOL_IMAGE_ID",
            "independently supplied full image ID",
        ),
    ),
)
def test_guarded_deploy_requires_external_clean_launch_and_source_authorities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
    message: str,
) -> None:
    docker_log = tmp_path / "docker.log"
    monkeypatch.delenv(missing_name, raising=False)
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert message in result.stderr
    assert not docker_log.exists()


def test_guarded_deploy_rejects_tampered_current_before_docker(
    tmp_path: Path,
) -> None:
    docker_log = tmp_path / "docker.log"
    projection_root = Path(
        os.environ["CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT"]
    )
    (projection_root / "CURRENT.json").write_text("{}\n", encoding="utf-8")
    env = os.environ.copy()
    env["FAKE_DOCKER_LOG"] = str(docker_log)

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "authenticated CURRENT public projection is unavailable" in result.stderr
    assert not docker_log.exists()


def test_guarded_recovery_uses_durable_journal_without_reading_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    journal = (
        tmp_path
        / "lock-state"
        / "public-edge-deploy-receipts"
        / "active-overlay-transaction.json"
    )
    journal.parent.mkdir(parents=True)
    journal.write_text('{"phase":"prepared"}\n', encoding="utf-8")
    projection_root = Path(
        os.environ["CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT"]
    )
    (projection_root / "CURRENT.json").write_text("{}\n", encoding="utf-8")
    advanced_current = (projection_root / "CURRENT.json").read_bytes()
    python_log = tmp_path / "python.log"
    trusted_python_log = tmp_path / "trusted-python.log"
    monkeypatch.delenv(
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256",
        raising=False,
    )
    monkeypatch.delenv(
        "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256",
        raising=False,
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(tmp_path / "docker.log"),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_TRUSTED_PYTHON_LOG": str(trusted_python_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
        }
    )

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY), "recover"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "public_edge_deploy_recovery_complete"
    assert not journal.exists()
    assert (projection_root / "CURRENT.json").read_bytes() == advanced_current
    trusted_calls = trusted_python_log.read_text(encoding="utf-8").splitlines()
    assert not any("verify_public_projection.py" in call for call in trusted_calls)
    recovery_call = next(
        call
        for call in python_log.read_text(encoding="utf-8").splitlines()
        if "public_edge_deploy_recovery.py" in call
    )
    assert "--runtime-proof-bind-source" not in recovery_call
    assert "--expected-runtime-proof-bind-source-sha256" not in recovery_call


@pytest.mark.parametrize(
    ("name", "value", "message"),
    (
        (
            "CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256",
            "0" * 64,
            "does not match its independent SHA-256 pin",
        ),
        (
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM",
            "0",
            "upstream authority is mandatory",
        ),
    ),
)
def test_guarded_deploy_rejects_authority_pin_mismatch_or_upstream_bypass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    monkeypatch.setenv(name, value)
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))
    monkeypatch.setenv("FAKE_TRUSTED_PYTHON_LOG", str(python_log))

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert message in result.stderr
    assert not docker_log.exists()
    assert not python_log.exists()


@pytest.mark.parametrize(
    "name",
    (
        "BASH_ENV",
        "ENV",
        "PYTHONPATH",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "BUILDKIT_HOST",
        "BUILDX_BUILDER",
        "COMPOSE_FILE",
    ),
)
def test_guarded_deploy_rejects_ambient_execution_routing_before_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    monkeypatch.setenv(name, "/dev/null")
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))
    monkeypatch.setenv("FAKE_TRUSTED_PYTHON_LOG", str(python_log))

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "rejects ambient execution routing" in result.stderr
    assert not docker_log.exists()
    assert not python_log.exists()


def test_guarded_deploy_rejects_inherited_xtrace_without_leaking_canary(
    tmp_path: Path,
) -> None:
    canary = "xtrace-secret-canary-6c4de7a2"
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    env = os.environ.copy()
    env.update(
        {
            "SHELLOPTS": "braceexpand:hashall:interactive-comments:xtrace",
            "BASHOPTS": "extglob",
            "BASH_XTRACEFD": "2",
            "PS4": f"trace-{canary}-",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_TRUSTED_PYTHON_LOG": str(python_log),
        }
    )

    result = subprocess.run(
        [str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "rejects ambient execution routing" in result.stderr
    assert canary not in result.stdout
    assert canary not in result.stderr
    assert not docker_log.exists()
    assert not python_log.exists()
    script = DEPLOY.read_text(encoding="utf-8")
    assert script.index("set +x") < script.index("ambient_routing_names=(")
    assert script.index("ambient_routing_names=(") < script.index("secrets.token_hex")


def test_guarded_deploy_authority_gate_precedes_selected_source_and_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))
    monkeypatch.setenv("FAKE_TRUSTED_PYTHON_LOG", str(python_log))
    monkeypatch.setenv("FAKE_AUTHORITY_EXIT", "19")

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 19
    python_calls = python_log.read_text(encoding="utf-8").splitlines()
    assert len(python_calls) == 1
    assert "verify_public_edge_deploy_authority.py" in python_calls[0]
    assert "check_public_edge_deploy_preflight.py" not in python_calls[0]
    assert not docker_log.exists()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    (
        (
            "FAKE_DOCKER_CONTEXT_IDENTITY",
            "remote|tcp://attacker.invalid:2375|false",
            "non-canonical Docker daemon context",
        ),
        (
            "FAKE_BUILDER_JSON",
            '{"Current":true,"Driver":"docker-container","Name":"default","Nodes":[]}',
            "non-canonical Buildx builder",
        ),
    ),
)
def test_guarded_deploy_attests_local_daemon_and_builder_before_compose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    docker_log = tmp_path / "docker.log"
    monkeypatch.setenv(name, value)
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(docker_log))

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert message in result.stderr
    assert not docker_log.exists()
    assert not (tmp_path / "lock-state" / "public-edge-mutation.lock").exists()
    assert not list(
        (
            tmp_path
            / "lock-state"
            / "public-edge-lock-recovery-receipts"
        ).glob("deploy-*.owner-token")
    )


def test_guarded_deploy_rejects_identical_duplicate_default_builders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = {
        "Current": True,
        "Driver": "docker",
        "Name": "default",
        "Nodes": [
            {
                "Endpoint": "default",
                "Name": "default",
                "Status": "running",
            }
        ],
    }
    monkeypatch.setenv(
        "FAKE_BUILDER_JSON",
        "\n".join((json.dumps(builder), json.dumps(builder, sort_keys=True))),
    )
    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "non-canonical Buildx builder" in result.stderr


def test_guarded_deploy_rejects_conflicting_duplicate_default_builders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = {
        "Current": True,
        "Driver": "docker",
        "Name": "default",
        "Nodes": [
            {
                "Endpoint": "default",
                "Name": "default",
                "Status": "running",
            }
        ],
    }
    conflicting = {
        **canonical,
        "Nodes": [{**canonical["Nodes"][0], "Status": "stopped"}],
    }
    monkeypatch.setenv(
        "FAKE_BUILDER_JSON",
        "\n".join((json.dumps(canonical), json.dumps(conflicting))),
    )

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "non-canonical Buildx builder" in result.stderr
    assert not (tmp_path / "lock-state" / "public-edge-mutation.lock").exists()


def test_guarded_deploy_sigkill_leaves_external_authenticated_recovery_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready = tmp_path / "docker-context-paused"
    monkeypatch.setenv("FAKE_DOCKER_CONTEXT_PAUSE_READY", str(ready))
    process = subprocess.Popen(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    deadline = time.monotonic() + 5
    while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.exists(), "deploy did not reach the paused canonical Docker attestation"

    lock_token = tmp_path / "lock-state" / "public-edge-mutation.lock" / "owner-token"
    external_tokens = list(
        (
            tmp_path
            / "lock-state"
            / "public-edge-lock-recovery-receipts"
        ).glob("deploy-*.owner-token")
    )
    assert len(external_tokens) == 1
    external_token = external_tokens[0]
    assert lock_token.stat().st_mode & 0o777 == 0o600
    assert external_token.stat().st_mode & 0o777 == 0o600
    assert lock_token.read_text(encoding="ascii") == external_token.read_text(
        encoding="ascii"
    )

    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)

    assert (tmp_path / "lock-state" / "public-edge-mutation.lock").is_dir()
    assert external_token.is_file()
    retained_artifacts = retained_public_edge_lock_artifacts(tmp_path)
    assert retained_artifacts["binding"].is_file()
    assert retained_artifacts["lease"].is_file()
    assert retained_artifacts["binding"].stat().st_mode & 0o777 == 0o600
    assert retained_artifacts["lease"].stat().st_mode & 0o777 == 0o600


def test_retirement_controller_failure_forces_status_76_and_retains_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_fake_public_download_retirement(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT", "143")

    result = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover-retire",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 76
    assert "authenticated mutation lock retained" in result.stderr
    assert (
        tmp_path / "lock-state" / "public-edge-mutation.lock"
    ).is_dir()


def test_cutover_recovery_adopts_exact_retained_lock_and_cleans_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id = configure_fake_public_download_cutover(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT", "76")

    cutover = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert cutover.returncode == 76, cutover.stderr
    lock_root = tmp_path / "lock-state"
    lock = lock_root / "public-edge-mutation.lock"
    token = (lock / "owner-token").read_text(encoding="ascii").strip()
    token_digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    authority_root = lock_root / "public-edge-lock-recovery-receipts"
    binding = authority_root / f"deploy-{token_digest}.binding.json"
    lease = authority_root / f"deploy-{token_digest}.lease"
    authorization = authority_root / f"deploy-{token_digest}.owner-token"
    binding_payload = json.loads(binding.read_text(encoding="utf-8"))
    assert token not in binding.read_text(encoding="utf-8")
    assert binding_payload["initialOperation"].endswith("-cutover")
    assert binding_payload["allowedResumeOperation"].endswith("-cutover-recover")
    assert binding.stat().st_mode & 0o777 == 0o600
    assert lease.stat().st_mode & 0o777 == 0o600
    assert authorization.stat().st_mode & 0o777 == 0o600

    materialize_fake_public_download_journal(tmp_path, operation_id)
    projection_current = (
        Path(os.environ["CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT"])
        / "CURRENT.json"
    )
    projection_current.write_text("{}\n", encoding="utf-8")
    projection_current.chmod(0o644)
    trusted_python_log = tmp_path / "recovery-trusted-python.log"
    monkeypatch.setenv(
        "FAKE_TRUSTED_PYTHON_LOG",
        str(trusted_python_log),
    )
    monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT", "0")
    recovery = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover-recover",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert recovery.returncode == 0, recovery.stderr
    assert not lock.exists()
    assert not binding.exists()
    assert not lease.exists()
    assert not authorization.exists()
    assert projection_current.read_text(encoding="utf-8") == "{}\n"
    assert not any(
        "verify_public_projection.py" in call
        for call in trusted_python_log.read_text(
            encoding="utf-8"
        ).splitlines()
    )


def test_precontroller_cutover_sigkill_retries_same_id_without_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id, artifacts = (
        retain_fake_public_download_precontroller_cutover(
            tmp_path,
            monkeypatch,
        )
    )
    binding_before = artifacts["binding"].read_bytes()
    journal = (
        tmp_path
        / "lock-state"
        / "public-edge-deploy-receipts"
        / f"chummer-public-download-{operation_id}.operation.json"
    )
    assert not journal.exists()

    wrong_route = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover-recover",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert wrong_route.returncode == 70
    assert artifacts["binding"].read_bytes() == binding_before

    retry = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert retry.returncode == 0, retry.stderr
    assert not artifacts["lock"].exists()
    assert not artifacts["authorization"].exists()
    assert not artifacts["lease"].exists()
    assert not artifacts["binding"].exists()


def test_precontroller_cutover_retry_reclaims_exact_empty_operation_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id, artifacts = (
        retain_fake_public_download_precontroller_cutover(
            tmp_path,
            monkeypatch,
        )
    )
    operation_root = (
        tmp_path
        / "lock-state"
        / "public-edge-deploy-receipts"
        / f"chummer-public-download-{operation_id}"
    )
    operation_root.mkdir(mode=0o700)
    operation_root.chmod(0o700)

    retry = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert retry.returncode == 0, retry.stderr
    assert not operation_root.exists()
    assert not artifacts["lock"].exists()
    assert not artifacts["authorization"].exists()
    assert not artifacts["lease"].exists()
    assert not artifacts["binding"].exists()


def test_precontroller_cutover_retry_rejects_journal_after_lease_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id, artifacts = (
        retain_fake_public_download_precontroller_cutover(
            tmp_path,
            monkeypatch,
        )
    )
    operation_root, journal = materialize_fake_public_download_journal(
        tmp_path,
        operation_id,
    )
    binding_before = artifacts["binding"].read_bytes()
    controller_ready = tmp_path / "journaled-prestart-controller-ready"
    monkeypatch.setenv(
        "FAKE_PUBLIC_DOWNLOAD_CONTROLLER_READY",
        str(controller_ready),
    )

    rejected = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert rejected.returncode == 70
    assert "changed after lease acquisition" in rejected.stderr
    assert not controller_ready.exists()
    assert operation_root.is_dir()
    assert journal.is_file()
    assert artifacts["binding"].read_bytes() == binding_before
    assert artifacts["lock"].is_dir()
    assert artifacts["authorization"].is_file()
    assert artifacts["lease"].is_file()


def test_retirement_retry_adopts_same_id_retained_lock_and_cleans_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_fake_public_download_retirement(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT", "143")
    first = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover-retire",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 76, first.stderr

    monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT", "0")
    retry = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover-retire",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert retry.returncode == 0, retry.stderr
    lock_root = tmp_path / "lock-state"
    assert not (lock_root / "public-edge-mutation.lock").exists()
    assert not list(
        (lock_root / "public-edge-lock-recovery-receipts").iterdir()
    )


@pytest.mark.parametrize(
    "mismatch",
    (
        "operation-id",
        "route",
        "journal",
        "source-head",
        "wrapper-digest",
        "controller-digest",
    ),
)
def test_retained_lock_adoption_rejects_bound_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    artifacts = retain_fake_public_download_retirement(tmp_path, monkeypatch)
    operation = "initial-release-shelf-public-download-cutover-retire"
    if mismatch == "operation-id":
        monkeypatch.setenv(
            "CHUMMER_PUBLIC_DOWNLOAD_OPERATION_ID",
            "retire-test-0002",
        )
    elif mismatch == "route":
        operation = "initial-release-shelf-public-download-cutover-recover"
    elif mismatch == "journal":
        operation_id = os.environ["CHUMMER_PUBLIC_DOWNLOAD_OPERATION_ID"]
        journal = (
            tmp_path
            / "lock-state"
            / "public-edge-deploy-receipts"
            / f"chummer-public-download-{operation_id}.operation.json"
        )
        payload = json.loads(journal.read_text(encoding="utf-8"))
        payload["projectName"] = "chummer-public-download-wrong"
        journal.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        journal.chmod(0o600)
    elif mismatch == "source-head":
        monkeypatch.setenv("CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD", "1" * 40)
    elif mismatch == "wrapper-digest":
        DEPLOY.write_text(
            DEPLOY.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        DEPLOY.chmod(0o755)
    elif mismatch == "controller-digest":
        binding = json.loads(
            artifacts["binding"].read_text(encoding="utf-8")
        )
        binding["controllerSha256"] = "f" * 64
        artifacts["binding"].write_text(
            json.dumps(binding, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifacts["binding"].chmod(0o600)
    controller_ready = tmp_path / "mismatched-adoption-controller-ready"
    monkeypatch.setenv(
        "FAKE_PUBLIC_DOWNLOAD_CONTROLLER_READY",
        str(controller_ready),
    )
    monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT", "0")

    rejected = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            operation,
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert rejected.returncode == 70
    assert "could not atomically establish" in rejected.stderr
    assert not controller_ready.exists()
    assert artifacts["lock"].is_dir()
    assert artifacts["token"].is_file()
    assert artifacts["authorization"].is_file()
    assert artifacts["lease"].is_file()
    assert artifacts["binding"].is_file()


def test_generic_recover_never_adopts_public_download_retirement_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = retain_fake_public_download_retirement(tmp_path, monkeypatch)
    binding_before = artifacts["binding"].read_bytes()

    rejected = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "recover",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert rejected.returncode == 75
    assert "another public-edge mutation owns" in rejected.stderr
    assert artifacts["lock"].is_dir()
    assert artifacts["token"].is_file()
    assert artifacts["binding"].read_bytes() == binding_before


def test_adopted_retirement_validation_failure_retains_exact_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = retain_fake_public_download_retirement(tmp_path, monkeypatch)
    before = {
        name: path.read_bytes()
        for name, path in artifacts.items()
        if name != "lock"
    }
    controller_ready = tmp_path / "validation-failure-controller-ready"
    monkeypatch.setenv(
        "FAKE_PUBLIC_DOWNLOAD_CONTROLLER_READY",
        str(controller_ready),
    )
    monkeypatch.setenv(
        "CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_FILE",
        str(tmp_path / "missing-cloudflare-credentials.json"),
    )

    failed = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover-retire",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert failed.returncode == 76
    assert "adopted public-download recovery did not complete" in failed.stderr
    assert not controller_ready.exists()
    assert artifacts["lock"].is_dir()
    for name, expected in before.items():
        assert artifacts[name].read_bytes() == expected


@pytest.mark.parametrize(
    "corruption",
    (
        "binding-symlink",
        "lease-hardlink",
        "authorization-mode",
        "binding-tamper",
        "authorization-tamper",
        "lease-tamper",
        "lock-extra-entry",
    ),
)
def test_retained_lock_adoption_rejects_unsafe_artifact_metadata_or_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    artifacts = retain_fake_public_download_retirement(tmp_path, monkeypatch)
    if corruption == "binding-symlink":
        decoy = tmp_path / "binding-decoy.json"
        decoy.write_text("{}\n", encoding="utf-8")
        decoy.chmod(0o600)
        artifacts["binding"].unlink()
        artifacts["binding"].symlink_to(decoy)
    elif corruption == "lease-hardlink":
        os.link(artifacts["lease"], tmp_path / "lease-hardlink")
    elif corruption == "authorization-mode":
        artifacts["authorization"].chmod(0o644)
    elif corruption == "binding-tamper":
        payload = json.loads(
            artifacts["binding"].read_text(encoding="utf-8")
        )
        payload["allowedResumeOperation"] = "recover"
        artifacts["binding"].write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifacts["binding"].chmod(0o600)
    elif corruption == "authorization-tamper":
        artifacts["authorization"].write_text(
            "f" * 64 + "\n",
            encoding="ascii",
        )
        artifacts["authorization"].chmod(0o600)
    elif corruption == "lease-tamper":
        artifacts["lease"].write_text("not-empty\n", encoding="ascii")
        artifacts["lease"].chmod(0o600)
    elif corruption == "lock-extra-entry":
        extra = artifacts["lock"] / "unexpected"
        extra.write_text("unexpected\n", encoding="utf-8")
        extra.chmod(0o600)
    controller_ready = tmp_path / "unsafe-adoption-controller-ready"
    monkeypatch.setenv(
        "FAKE_PUBLIC_DOWNLOAD_CONTROLLER_READY",
        str(controller_ready),
    )
    monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT", "0")

    rejected = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover-retire",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert rejected.returncode == 70
    assert not controller_ready.exists()
    assert artifacts["lock"].is_dir()


def test_retained_lock_cleanup_failure_keeps_all_authority_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = retain_fake_public_download_retirement(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT", "0")
    monkeypatch.setenv(
        "FAKE_PUBLIC_DOWNLOAD_CLEANUP_TAMPER_PATH",
        str(artifacts["binding"]),
    )

    result = subprocess.run(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover-retire",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 70
    assert "deployment lock release failed" in result.stderr
    assert artifacts["lock"].is_dir()
    assert artifacts["token"].is_file()
    assert artifacts["authorization"].is_file()
    assert artifacts["lease"].is_file()
    assert artifacts["binding"].is_file()


def test_lock_cleanup_durably_releases_canonical_name_before_artifact_gc() -> None:
    script = DEPLOY.read_text(encoding="utf-8")
    cleanup_start = script.index(
        'releasing_path = os.path.join(\n'
        '    lock_root,\n'
        '    f"public-edge-mutation.lock.releasing.'
    )
    cleanup_end = script.index(
        "' \"$DEPLOY_LOCK_DIR\" \"$deploy_lock_identity\"",
        cleanup_start,
    )
    cleanup = script[cleanup_start:cleanup_end]

    rename = cleanup.index(
        "renameat2(-100, lock_path, -100, releasing_path, 1)"
    )
    durable_release = cleanup.index("os.fsync(lock_root_descriptor)", rename)
    token_gc = cleanup.index("os.unlink(released_token_path)", durable_release)
    binding_gc = cleanup.index("os.unlink(binding_path)", token_gc)
    authorization_gc = cleanup.index("os.unlink(authorization_path)", binding_gc)
    lease_gc = cleanup.index("os.unlink(lease_path)", authorization_gc)
    tombstone_gc = cleanup.index("os.rmdir(releasing_path)", lease_gc)

    assert rename < durable_release < token_gc
    assert token_gc < binding_gc < authorization_gc < lease_gc < tombstone_gc


def test_retirement_wrapper_sigkill_keeps_durable_lock_while_child_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_fake_public_download_retirement(tmp_path, monkeypatch)
    ready = tmp_path / "retirement-controller-ready"
    child_pid_path = tmp_path / "retirement-controller.pid"
    heartbeat = tmp_path / "retirement-controller.heartbeat"
    monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_MODE", "block")
    monkeypatch.setenv(
        "FAKE_PUBLIC_DOWNLOAD_CONTROLLER_READY",
        str(ready),
    )
    monkeypatch.setenv(
        "FAKE_PUBLIC_DOWNLOAD_CONTROLLER_PID",
        str(child_pid_path),
    )
    monkeypatch.setenv(
        "FAKE_PUBLIC_DOWNLOAD_CONTROLLER_HEARTBEAT",
        str(heartbeat),
    )
    process = subprocess.Popen(
        [
            "/usr/bin/bash",
            "--noprofile",
            "--norc",
            str(DEPLOY),
            "initial-release-shelf-public-download-cutover-retire",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    child_pid: int | None = None
    try:
        deadline = time.monotonic() + 5
        while (
            (not ready.exists() or not child_pid_path.exists())
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert ready.exists(), "retirement controller did not start"
        child_pid = int(child_pid_path.read_text(encoding="ascii"))
        assert child_pid != process.pid
        lock = (
            tmp_path / "lock-state" / "public-edge-mutation.lock"
        )
        assert lock.is_dir()
        assert heartbeat.is_file()
        before = heartbeat.stat().st_size

        os.kill(process.pid, signal.SIGKILL)
        assert process.wait(timeout=5) == -signal.SIGKILL

        os.kill(child_pid, 0)
        deadline = time.monotonic() + 2
        while (
            heartbeat.stat().st_size <= before
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert heartbeat.stat().st_size > before
        assert lock.is_dir()
        assert (lock / "owner-token").is_file()
        assert list(
            (
                tmp_path
                / "lock-state"
                / "public-edge-lock-recovery-receipts"
            ).glob("deploy-*.owner-token")
        )

        live_adoption = subprocess.run(
            [
                "/usr/bin/bash",
                "--noprofile",
                "--norc",
                str(DEPLOY),
                "initial-release-shelf-public-download-cutover-retire",
            ],
            cwd=ROOT,
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            check=False,
        )
        assert live_adoption.returncode == 75
        assert "another public-edge mutation owns" in live_adoption.stderr
        assert lock.is_dir()

        os.kill(child_pid, signal.SIGKILL)
        monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_MODE", "exit")
        monkeypatch.setenv("FAKE_PUBLIC_DOWNLOAD_CONTROLLER_EXIT", "0")
        adopted: subprocess.CompletedProcess[str] | None = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            adopted = subprocess.run(
                [
                    "/usr/bin/bash",
                    "--noprofile",
                    "--norc",
                    str(DEPLOY),
                    "initial-release-shelf-public-download-cutover-retire",
                ],
                cwd=ROOT,
                env=os.environ.copy(),
                text=True,
                capture_output=True,
                check=False,
            )
            if adopted.returncode != 75:
                break
            time.sleep(0.02)
        assert adopted is not None
        assert adopted.returncode == 0, adopted.stderr
        assert not lock.exists()
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if process.poll() is None:
            process.wait(timeout=5)


def test_guarded_deploy_unique_auth_orphan_does_not_block_new_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_root = tmp_path / "lock-state"
    auth_root = lock_root / "public-edge-lock-recovery-receipts"
    auth_root.mkdir(parents=True, mode=0o700)
    auth_root.chmod(0o700)
    orphan_token = "a" * 64
    orphan_digest = hashlib.sha256(orphan_token.encode("ascii")).hexdigest()
    orphan = auth_root / f"deploy-{orphan_digest}.owner-token"
    orphan.write_text(orphan_token + "\n", encoding="ascii")
    orphan.chmod(0o600)
    monkeypatch.setenv(
        "FAKE_DOCKER_CONTEXT_IDENTITY",
        "remote|tcp://attacker.invalid:2375|false",
    )

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "non-canonical Docker daemon context" in result.stderr
    assert orphan.read_text(encoding="ascii") == orphan_token + "\n"
    assert not (lock_root / "public-edge-mutation.lock").exists()
    assert list(auth_root.glob("deploy-*.owner-token")) == [orphan]
    assert list(auth_root.iterdir()) == [orphan]


def test_guarded_deploy_never_removes_tokenless_existing_fixed_lock(
    tmp_path: Path,
) -> None:
    lock_root = tmp_path / "lock-state"
    lock_root.mkdir(mode=0o700)
    fixed_lock = lock_root / "public-edge-mutation.lock"
    fixed_lock.mkdir(mode=0o700)

    result = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", str(DEPLOY)],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 75
    assert "another public-edge mutation owns" in result.stderr
    assert fixed_lock.is_dir()
    assert list(fixed_lock.iterdir()) == []
    assert not list(lock_root.glob(".public-edge-mutation.lock.staging.*"))
    assert not list(
        (lock_root / "public-edge-lock-recovery-receipts").glob(
            "deploy-*.owner-token"
        )
    )
    assert not list(
        (lock_root / "public-edge-lock-recovery-receipts").iterdir()
    )


@pytest.mark.parametrize(
    "failure_phase",
    [
        "portal_stop",
        "initializer",
        "candidate_creation",
        "candidate_readiness",
        "publication_readiness",
        "tunnel_health",
        "tunnel_replica_health",
    ],
)
def test_guarded_deploy_uses_named_candidate_and_durable_recovery_on_failure(
    tmp_path: Path,
    failure_phase: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    fake_python = fake_bin / "python3"
    write_fake_transaction_python(fake_python)
    fake_docker = fake_bin / "docker"
    write_fake_blue_green_docker(fake_docker)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_DOCKER_FAILURE_PHASE": failure_phase,
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )
    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    python_commands = python_log.read_text(encoding="utf-8").splitlines()
    assert any("public_edge_deploy_recovery.py" in command for command in python_commands)
    assert not any("force-recreate" in command for command in commands)

    tunnel_stop_index = next(
        index
        for index, command in enumerate(commands)
        if command.endswith(" stop chummer-run-cloudflared")
    )
    portal_stop_index = commands.index(
        f"container stop {PRIOR_PORTAL_CONTAINER_ID}"
    )
    assert tunnel_stop_index < portal_stop_index
    if failure_phase == "portal_stop":
        assert not any("chummer-portal-volume-init" in command for command in commands)
        return

    init_index = next(
        index
        for index, command in enumerate(commands)
        if command.endswith(" run --rm --no-deps chummer-portal-volume-init")
    )
    assert portal_stop_index < init_index
    if failure_phase == "initializer":
        return

    candidate_index = next(
        index
        for index, command in enumerate(commands)
        if " run -T -d --no-deps --service-ports --use-aliases --name "
        "chummer-public-edge-candidate-" in command
    )
    assert init_index < candidate_index
    assert commands[candidate_index].endswith(" chummer-portal")
    if failure_phase == "candidate_creation":
        return

    candidate_running_index = commands.index(
        "container inspect --format {{.State.Running}} "
        f"{CANDIDATE_PORTAL_CONTAINER_ID}"
    )
    assert candidate_index < candidate_running_index
    if failure_phase == "candidate_readiness":
        return

    publication_index = next(
        index
        for index, command in enumerate(commands)
        if command.startswith(
            f"container exec {CANDIDATE_PORTAL_CONTAINER_ID} "
            "dotnet /app/loopback-probe/"
            "Chummer.Run.LoopbackProbe.dll "
        )
    )
    assert candidate_running_index < publication_index


def test_guarded_deploy_uses_orchestrated_postdeploy_closure_and_no_legacy_flags(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    fake_docker = fake_bin / "docker"
    write_fake_blue_green_docker(fake_docker)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "FAKE_POSTDEPLOY_EXIT": "47",
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 1
    args = json.loads(postdeploy_log.read_text(encoding="utf-8"))
    assert args == [
        "--base-url",
        "https://chummer.run",
        "--strict-preflight",
        "--release-channel-receipt",
        env["CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT"],
        "--release-channel-receipt-sha256",
        env["CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256"],
        "--public-projection-snapshot-root",
        env["CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT"],
        "--public-projection-purpose",
        "code-deploy",
        "--expect-code-deploy-review-required",
        "--runtime-proof-bind-source-sha256",
        env["CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256"],
        "--overlay-root",
        "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app",
        "--expected-build-info",
        "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app/.codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json",
        "--require-downloads-status-playwright",
        "--require-mobile-pwa-viewport-playwright",
        "--require-frontdoor-navigation-playwright",
        "--playwright-artifact-dir",
        str(source / ".codex-studio/published/public-edge-browser-proofs/downloads-status"),
        "--mobile-pwa-viewport-artifact-dir",
        str(source / ".codex-studio/published/public-edge-browser-proofs/mobile-pwa-viewport"),
        "--frontdoor-navigation-artifact-dir",
        str(source / ".codex-studio/published/public-edge-browser-proofs/frontdoor-navigation"),
        "--output",
        str(source / ".codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"),
    ]
    assert "--self-contained-direct" not in args
    assert "--expected-release-channel" not in args
    assert "--expected-portal-image-id" not in args
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert any(
        " run -T -d --no-deps --service-ports --use-aliases --name "
        "chummer-public-edge-candidate-" in command
        for command in commands
    )
    assert not any("force-recreate" in command for command in commands)
    assert any(
        "public_edge_deploy_recovery.py" in command
        for command in python_log.read_text(encoding="utf-8").splitlines()
    )


def test_guarded_deploy_rejects_secret_key_in_postdeploy_child_receipt(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(
        tmp_path,
        inject_postdeploy_child_secret_key=True,
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "postdeploy code-deploy authority failed" in result.stderr
    assert "hunter2" not in result.stdout
    assert "hunter2" not in result.stderr
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:complete" not in events
    assert "candidate:restart-policy:unless-stopped" not in events
    assert "journal:recovered" in events


@pytest.mark.parametrize(
    "secret_key",
    (
        "credentials",
        "databaseCredentials",
        "passwords",
        "tokens",
        "secrets",
        "connectionString",
        "connection_strings",
        "dsn",
    ),
)
def test_guarded_deploy_rejects_secret_alias_in_allowed_nested_postdeploy_field(
    tmp_path: Path,
    secret_key: str,
) -> None:
    source = make_fake_authority_source(
        tmp_path,
        inject_postdeploy_nested_secret_key=secret_key,
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "postdeploy code-deploy authority failed" in result.stderr
    assert "hunter2" not in result.stdout
    assert "hunter2" not in result.stderr
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:complete" not in events
    assert "candidate:restart-policy:unless-stopped" not in events
    assert "journal:recovered" in events


@pytest.mark.parametrize(
    "secret_value",
    (
        "credentials: hunter2",
        "https%3A%2F%2Fuser%3Ahunter2%40example.test%2F",
    ),
)
def test_guarded_deploy_rejects_secret_assignment_value_in_nested_postdeploy_field(
    tmp_path: Path,
    secret_value: str,
) -> None:
    source = make_fake_authority_source(
        tmp_path,
        inject_postdeploy_nested_secret_value=secret_value,
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    write_fake_blue_green_docker(fake_bin / "docker")
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    postdeploy_log = tmp_path / "postdeploy.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "postdeploy code-deploy authority failed" in result.stderr
    assert "hunter2" not in result.stdout
    assert "hunter2" not in result.stderr
    events = Path(env["FAKE_EVENT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert "journal:complete" not in events
    assert "candidate:restart-policy:unless-stopped" not in events
    assert "journal:recovered" in events


def test_guarded_deploy_rejects_candidate_image_mismatch_before_postdeploy(
    tmp_path: Path,
) -> None:
    source = make_fake_authority_source(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_transaction_python(fake_bin / "python3")
    postdeploy_log = tmp_path / "postdeploy.json"
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    trusted_python_log = tmp_path / "trusted-python.log"
    fake_docker = fake_bin / "docker"
    write_fake_blue_green_docker(fake_docker)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_TRUSTED_PYTHON_LOG": str(trusted_python_log),
            "FAKE_CANDIDATE_MISMATCH": "1",
            "FAKE_POSTDEPLOY_LOG": str(postdeploy_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(source),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(
                source / "docker-compose.public-edge.yml"
            ),
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 1
    assert "candidate image identity failed" in result.stderr
    assert not postdeploy_log.exists()
    assert any(
        "public_edge_deploy_recovery.py" in command
        for command in python_log.read_text(encoding="utf-8").splitlines()
    )
    assert not any(
        "materialize_install_linking_cutover_boundary.py" in command
        for command in trusted_python_log.read_text(encoding="utf-8").splitlines()
    )


def test_guarded_deploy_preflight_failure_prevents_every_docker_command(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python_log = tmp_path / "python.log"
    docker_log = tmp_path / "docker.log"
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_PYTHON_LOG\"\n"
        "case \"$*\" in *check_public_edge_deploy_preflight.py*) exit 23;; esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_DOCKER_LOG": str(docker_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 23
    assert "check_public_edge_deploy_preflight.py" in python_log.read_text(encoding="utf-8")
    assert not docker_log.exists()


def test_guarded_deploy_compose_config_failure_prevents_image_build(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_python = fake_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
        "case \"$*\" in *\" config --format json\") exit 31;; esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert len(commands) == 1
    assert commands[0].endswith(" config --format json")
    assert all("buildx build" not in command for command in commands)


def test_guarded_deploy_promotion_failure_journals_exact_prior_tags_for_recovery(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    fake_python = fake_bin / "python3"
    write_fake_transaction_python(fake_python)
    fake_docker = fake_bin / "docker"
    write_fake_blue_green_docker(fake_docker)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_DOCKER_FAILURE_PHASE": "image_promotion",
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    promotion_index = next(
        index
        for index, command in enumerate(commands)
        if command.startswith("image tag chummer-run-api:cutover-")
    )
    assert promotion_index >= 0
    assert all("buildx build" not in command for command in commands)
    assert all(not command.endswith(" stop chummer-portal") for command in commands)
    python_commands = python_log.read_text(encoding="utf-8").splitlines()
    snapshot_command = next(
        command
        for command in python_commands
        if "public_edge_overlay_transaction.py snapshot" in command
    )
    assert f"--prior-image-tag-id {PRIOR_PORTAL_IMAGE_ID}" in snapshot_command
    assert f"--prior-tool-image-tag-id {PRIOR_TOOL_IMAGE_ID}" in snapshot_command
    current = json.loads(
        (
            Path(env["CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT"])
            / "CURRENT.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        f"--public-projection-snapshot-id {current['snapshotId']}"
        in snapshot_command
    )
    assert (
        f"--public-projection-snapshot-sha256 {current['snapshotSha256']}"
        in snapshot_command
    )
    assert (
        f"--public-projection-manifest-sha256 {current['manifestSha256']}"
        in snapshot_command
    )
    assert any("public_edge_deploy_recovery.py" in command for command in python_commands)


def test_migration_loop_runs_default_preflight_before_build_mutation(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python_log = tmp_path / "python.log"
    docker_log = tmp_path / "docker.log"
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_PYTHON_LOG\"\n"
        "case \"$*\" in *check_public_edge_deploy_preflight.py*) exit 29;; esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.pop("CHUMMER_PUBLIC_EDGE_DEPLOY_PREFLIGHT_GATE", None)
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_DOCKER_LOG": str(docker_log),
            "CHUMMER_PUBLIC_EDGE_DEPLOY_REPO_ROOT": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_DEPLOY_SOURCE_GATE": "1",
            "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT": (
                "/docker/chummercomplete/chummer-hub-registry/.codex-studio/"
                "published/RELEASE_CHANNEL.generated.json"
            ),
            "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256": "d" * 64,
            "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256": "e" * 64,
            "CHUMMER_PORTAL_E2E": "0",
            "CHUMMER_HUB_E2E": "0",
        }
    )

    result = subprocess.run(
        ["bash", str(MIGRATION_LOOP), "1"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    python_commands = python_log.read_text(encoding="utf-8").splitlines()
    assert python_commands
    assert "check_public_edge_deploy_preflight.py" in python_commands[0]
    docker_commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert all(" up -d --build " not in command for command in docker_commands)


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS", "0"),
        ("CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS", "not-a-number"),
        ("CHUMMER_PUBLIC_EDGE_POSTDEPLOY_RETRY_DELAY_SECONDS", "-1"),
    ),
)
def test_guarded_deploy_rejects_postdeploy_bypass_before_docker(
    tmp_path: Path,
    name: str,
    value: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            name: value,
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 2
    assert not docker_log.exists()


def test_guarded_deploy_rejects_unreviewed_compose_override_before_docker(
    tmp_path: Path,
) -> None:
    unreviewed_compose = tmp_path / "docker-compose.public-edge.yml"
    unreviewed_compose.write_text("services: {}\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(unreviewed_compose),
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 2
    assert "exact owner-controlled single-link Compose input" in result.stderr
    assert not docker_log.exists()


@pytest.mark.parametrize(
    ("name", "value_kind", "message"),
    (
        ("CHUMMER_PUBLIC_EDGE_PROJECT_NAME", "literal", "non-canonical Compose project"),
        ("CHUMMER_PUBLIC_EDGE_PORTAL_IMAGE_TAG", "literal", "non-canonical portal image tag"),
        ("CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR", "literal", "non-canonical portal overlay root"),
        ("CHUMMER_PUBLIC_EDGE_BASE_URL", "literal", "non-canonical verification origin"),
        ("CHUMMER_PUBLIC_EDGE_PORT", "literal", "non-canonical public portal port"),
        ("CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT", "directory", "non-canonical build context"),
        ("CHUMMER_PUBLIC_EDGE_ENV_FILE", "file", "non-canonical Compose environment file"),
        (
            "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT",
            "file",
            "release-channel receipt override is not the authenticated CURRENT output",
        ),
    ),
)
def test_guarded_deploy_rejects_runtime_authority_override_before_docker(
    tmp_path: Path,
    name: str,
    value_kind: str,
    message: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    override = "noncanonical"
    if value_kind == "directory":
        override_path = tmp_path / "override"
        override_path.mkdir()
        override = str(override_path)
    elif value_kind == "file":
        override_path = tmp_path / "override"
        override_path.write_text("{}\n", encoding="utf-8")
        override = str(override_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            name: override,
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 2
    assert message in result.stderr
    assert not docker_log.exists()


@pytest.mark.parametrize("failure", ("compose_ps", "container_image", "container_state"))
def test_guarded_deploy_fails_closed_when_prior_runtime_capture_fails(
    tmp_path: Path,
    failure: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_python = fake_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        """#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
    case "$*" in *" config --format json") cat "$FAKE_COMPOSE_CONFIG_JSON"; exit 0;; esac
    case "$*" in
      "image inspect chummer-run-api:cutover-"*" --format {{.Id}}") printf '%s\n' "$FAKE_CANDIDATE_PORTAL_IMAGE_ID" ;;
      "image inspect chummer-install-linking-postgres-tool:cutover-"*" --format {{.Id}}") printf '%s\n' "$FAKE_CANDIDATE_TOOL_IMAGE_ID" ;;
      "image ls --quiet --no-trunc --filter reference=chummer-run-api:local") printf '%s\n' "$FAKE_PRIOR_PORTAL_IMAGE_ID" ;;
      "image ls --quiet --no-trunc --filter reference=chummer-install-linking-postgres-tool:local") printf '%s\n' "$FAKE_PRIOR_TOOL_IMAGE_ID" ;;
      "image inspect chummer-run-api:local --format {{.Id}}") printf '%s\n' "$FAKE_CANDIDATE_PORTAL_IMAGE_ID" ;;
      "image inspect chummer-install-linking-postgres-tool:local --format {{.Id}}") printf '%s\n' "$FAKE_CANDIDATE_TOOL_IMAGE_ID" ;;
  *" ps --all -q chummer-portal")
    if [ "$FAKE_CAPTURE_FAILURE" = compose_ps ]; then exit 58; fi
    printf '%s\n' prior-portal
    ;;
  "container inspect --format {{.Image}} prior-portal")
    if [ "$FAKE_CAPTURE_FAILURE" = container_image ]; then exit 59; fi
    printf '%s\n' sha256:prior-image
    ;;
  "container inspect --format {{.State.Running}} prior-portal")
    if [ "$FAKE_CAPTURE_FAILURE" = container_state ]; then exit 60; fi
    printf '%s\n' true
    ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_CAPTURE_FAILURE": failure,
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 3
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert not any(command.endswith(" stop chummer-portal") for command in commands)
    assert not any("chummer-portal-volume-init" in command for command in commands)


def test_all_public_edge_mutators_share_one_nonoverrideable_host_lock() -> None:
    lock_path = "/docker/chummercomplete/.state/public-edge-mutation.lock"
    deploy_text = (ROOT / "scripts" / "deploy_public_edge_portal.sh").read_text(
        encoding="utf-8"
    )
    restore_text = RESTORE.read_text(encoding="utf-8")
    shared_lock_text = (ROOT / "scripts" / "public_edge_mutation_lock.py").read_text(
        encoding="utf-8"
    )
    publisher_text = PUBLISHER.read_text(encoding="utf-8")
    runbook_text = RUNBOOK.read_text(encoding="utf-8")
    production_cutover = runbook_text[
        runbook_text.index("### Sole production application cutover") :
        runbook_text.index("### Authenticated manual stale-lock recovery")
    ]

    assert 'DEPLOY_LOCK_ROOT="/docker/chummercomplete/.state"' in deploy_text
    assert f'DEPLOY_LOCK_DIR="$DEPLOY_LOCK_ROOT/public-edge-mutation.lock"' in deploy_text
    assert "LOCK_PATH as PUBLIC_EDGE_MUTATION_LOCK" in restore_text
    assert 'LOCK_ROOT = Path("/docker/chummercomplete/.state")' in shared_lock_text
    assert 'LOCK_PATH = LOCK_ROOT / "public-edge-mutation.lock"' in shared_lock_text
    assert f'Path("{lock_path}")' in publisher_text
    assert "CHUMMER_PUBLIC_EDGE_DEPLOY_LOCK_ROOT" not in deploy_text
    assert 'DEPLOY_LOCK_ROOT="${' not in deploy_text
    assert 'DEPLOY_LOCK_DIR="${' not in deploy_text
    assert production_cutover.count("scripts/deploy_public_edge_portal.sh") == 2
    assert "scripts/deploy_public_edge_portal.sh recover" in production_cutover
    assert "Operators do not stop the portal" in production_cutover
    for retired_manual_lock in (
        "cutover_lock_dir=",
        "--shared-mutation-lock-token",
        "public_edge_mutation_lock.py acquire",
        "CHUMMER_PUBLIC_EDGE_DEPLOY_LOCK_ROOT",
        "DEPLOY_LOCK_ROOT=",
        "DEPLOY_LOCK_DIR=",
    ):
        assert retired_manual_lock not in runbook_text
    assert publisher_text.index("with public_edge_mutation_lock(") < publisher_text.index(
        "with overlay_publish_lock(",
        publisher_text.index("with public_edge_mutation_lock("),
    )


def test_migration_loop_routes_portal_through_guarded_transaction_wrapper() -> None:
    script = MIGRATION_LOOP.read_text(encoding="utf-8")

    assert 'bash "$PUBLIC_EDGE_DEPLOY_REPO_ROOT/scripts/deploy_public_edge_portal.sh"' in script
    assert "up -d --build chummer-run-identity" in script
    assert "up -d --build --remove-orphans chummer-run-identity chummer-portal" not in script
    assert 'export CHUMMER_RUN_SERVICES_CONTEXT_DIR="$PUBLIC_EDGE_DEPLOY_REPO_ROOT"' in script


def test_guarded_deploy_journals_previously_stopped_portal_for_recovery(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"
    fake_python = fake_bin / "python3"
    write_fake_transaction_python(fake_python)
    fake_docker = fake_bin / "docker"
    write_fake_blue_green_docker(fake_docker)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_PYTHON_LOG": str(python_log),
            "FAKE_PRIOR_PORTAL_RUNNING": "false",
            "FAKE_DOCKER_FAILURE_PHASE": "publication_readiness",
            "CHUMMER_RUN_SERVICES_SOURCE": str(ROOT),
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": "/docker/chummercomplete",
            "CHUMMER_PUBLIC_EDGE_COMPOSE_FILE": str(ROOT / "docker-compose.public-edge.yml"),
            "CHUMMER_PUBLIC_EDGE_ENV_FILE": "/docker/chummercomplete/chummer.run-services/.env",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "0" * 40,
            "CHUMMER_PUBLIC_EDGE_REQUIRE_UPSTREAM": "1",
            "CHUMMER_PUBLIC_EDGE_POSTDEPLOY_ATTEMPTS": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY)], cwd=ROOT, env=env, text=True, capture_output=True
    )

    assert result.returncode == 1
    commands = docker_log.read_text(encoding="utf-8").splitlines()
    assert f"container stop {PRIOR_PORTAL_CONTAINER_ID}" not in commands
    assert not any("force-recreate" in command for command in commands)
    python_commands = python_log.read_text(encoding="utf-8").splitlines()
    snapshot_command = next(
        command
        for command in python_commands
        if "public_edge_overlay_transaction.py snapshot" in command
    )
    assert "--prior-portal-existed 1" in snapshot_command
    assert "--prior-portal-was-running 0" in snapshot_command
    assert any("public_edge_deploy_recovery.py" in command for command in python_commands)
