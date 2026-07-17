from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "publish-download-bundle-http.sh"
UPLOAD_ATTEMPT_RECEIPT_HELPER = REPO_ROOT / "scripts" / "release" / "release_upload_attempt_receipt.py"
SESSION_ID = "0123456789abcdef0123456789abcdef"


def write_bundle(root: Path) -> Path:
    files_dir = root / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "channel": "preview",
        "version": "run-test",
        "status": "published",
        "supportabilitySummary": (
            "Treat the current release as review-required because stale or incomplete proof receipts "
            "still block launch-readiness claims: fixture bundle still needs current proof receipts."
        ),
        "knownIssueSummary": (
            "Known issue: stale or incomplete proof receipts still block launch-readiness claims: "
            "fixture bundle still needs current proof receipts."
        ),
        "artifacts": [],
        "desktopTupleCoverage": {
            "externalProofRequests": [{"marker": "stale-proof"}],
            "desktopRouteTruth": [{"marker": "stale-route"}],
        },
        "installAwareArtifactRegistry": [{"marker": "stale-install"}],
        "desktopSurfaceRefs": [{"marker": "stale-surface"}],
        "artifactIdentityRegistry": [{"marker": "stale-identity"}],
        "artifactPublicationBindings": [{"marker": "stale-binding"}],
        "publicTrustMetrics": {
            "marker": "stale-trust",
            "releaseChannel": {"supportabilityState": "launch_supported"},
        },
        "registryBoundaryCoverage": {"marker": "stale-boundary"},
    }
    (root / "releases.json").write_text(json.dumps(payload), encoding="utf-8")
    (root / "RELEASE_CHANNEL.generated.json").write_text(json.dumps(payload), encoding="utf-8")
    (files_dir / "notes.txt").write_text("release lane proof\n", encoding="utf-8")
    return root


def write_registry(root: Path) -> Path:
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    verifier = scripts_dir / "verify_public_release_channel.py"
    verifier.write_text(
        """
from __future__ import annotations


def expected_external_proof_request_rows(payload):
    return [{"marker": "canonical-proof"}]


def expected_desktop_route_truth_rows(payload):
    return [{"marker": "canonical-route"}]


def expected_install_aware_artifact_registry_rows(payload):
    return [{"marker": "canonical-install"}]


def expected_desktop_surface_ref_rows(payload):
    return [{"marker": "canonical-surface"}]


def expected_artifact_identity_registry_rows(payload):
    return [{"marker": "canonical-identity"}]


def expected_artifact_publication_binding_rows(payload):
    return [{"marker": "canonical-binding"}]


def expected_public_trust_metrics(payload):
    return {
        "marker": "canonical-trust",
        "releaseChannel": {"supportabilityState": "review_required"},
    }


def expected_registry_boundary_coverage(payload):
    return {"marker": "canonical-boundary"}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return root


def write_script_fixture(
    root: Path,
    *,
    include_materializer: bool = True,
    include_launcher: bool = True,
    include_shelf_truth_gate: bool = True,
    include_public_shell_gate: bool = True,
) -> Path:
    script_dir = root / "scripts"
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / "publish-download-bundle-http.sh"
    script_path.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")

    for helper_name, stdout_text in (
        ("verify-windows-installer-payloads.py", "windows_installer_payload_gate:ok no_windows_installers"),
        ("verify-windows-installer-visual-proof.py", "windows_visual_proof_gate:ok no_windows_installers"),
        (
            "verify-windows-installer-visual-proof-handoff.py",
            "windows_installer_visual_proof_handoff_gate:ok posture=proof_only",
        ),
    ):
        (script_dir / helper_name).write_text(
            (
                "#!/usr/bin/env python3\n"
                "print(" + repr(stdout_text) + ")\n"
            ),
            encoding="utf-8",
        )

    if include_shelf_truth_gate:
        (script_dir / "public_download_shelf_truth_gate.py").write_text(
            """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", required=True)
parser.add_argument("--local-manifest", required=True)
parser.add_argument("--local-canonical-manifest", required=True)
args = parser.parse_args()

payload = {
    "baseUrl": args.base_url,
    "localManifest": args.local_manifest,
    "localCanonicalManifest": args.local_canonical_manifest,
}
log_path = os.environ.get("SHELF_TRUTH_LOG")
if log_path:
    Path(log_path).write_text(json.dumps(payload), encoding="utf-8")
""",
            encoding="utf-8",
        )

    if include_public_shell_gate:
        (script_dir / "public_shell_minimal_truth_gate.py").write_text(
            """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", required=True)
args = parser.parse_args()

payload = {"baseUrl": args.base_url}
log_path = os.environ.get("PUBLIC_SHELL_TRUTH_LOG")
if log_path:
    Path(log_path).write_text(json.dumps(payload), encoding="utf-8")
""",
            encoding="utf-8",
        )

    if include_materializer:
        (script_dir / "materialize_artifact_factory_source_pack_batch.py").write_text(
            """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--release-manifest", required=True)
parser.add_argument("--promotion-result", required=True)
parser.add_argument("--requested-by", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--release-proof")
parser.add_argument("--required-family", action="append", default=[])
parser.add_argument("--requested-format", action="append", default=[])
parser.add_argument("--audience")
parser.add_argument("--locale")
parser.add_argument("--source-pack-file", action="append", default=[])
args = parser.parse_args()

payload = {
    "requestedBy": args.requested_by,
    "requiredFamilies": args.required_family,
    "requestedFormats": args.requested_format,
    "audience": args.audience,
    "locale": args.locale,
    "sourcePackFiles": args.source_pack_file,
    "credentialEnvironment": {
        key: os.environ[key]
        for key in (
            "TOKEN",
            "ARTIFACT_FACTORY_TOKEN",
            "FLEET_INTERNAL_API_TOKEN",
            "CHUMMER_RELEASE_UPLOAD_TOKEN",
            "CHUMMER_RELEASE_UPLOAD_TOKEN_FILE",
            "CHUMMER_RELEASE_UPLOAD_TOKEN_PATH",
            "CHUMMER_RELEASE_UPLOAD_TICKET",
        )
        if key in os.environ
    },
    "credentialFileContents": {
        key: Path(os.environ[key]).read_text(encoding="utf-8")
        for key in ("CHUMMER_RELEASE_UPLOAD_TOKEN_FILE", "CHUMMER_RELEASE_UPLOAD_TOKEN_PATH")
        if key in os.environ and Path(os.environ[key]).is_file()
    },
    "promotionResult": json.loads(Path(args.promotion_result).read_text(encoding="utf-8")),
}
Path(args.output).write_text(json.dumps(payload), encoding="utf-8")

log_path = os.environ.get("ARTIFACT_FACTORY_MATERIALIZER_LOG")
if log_path:
    Path(log_path).write_text(json.dumps(payload), encoding="utf-8")
""",
            encoding="utf-8",
        )

    if include_launcher:
        (script_dir / "launch_artifact_factory_source_pack_batch.py").write_text(
            """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", required=True)
parser.add_argument("--request-file", required=True)
args = parser.parse_args()
token = os.environ.get("FLEET_INTERNAL_API_TOKEN", "")
if not token:
    raise SystemExit("missing artifact-factory token")

request_payload = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
log_path = os.environ.get("ARTIFACT_FACTORY_LAUNCHER_LOG")
if log_path:
    Path(log_path).write_text(
        json.dumps(
            {
                "baseUrl": args.base_url,
                "token": token,
                "argv": os.sys.argv[1:],
                "requestPayload": request_payload,
            }
        ),
        encoding="utf-8",
    )

print(json.dumps({"status": "accepted", "requestPayload": request_payload}))
""",
            encoding="utf-8",
        )

    return script_path


@dataclass
class UploadRecorder:
    session_posts: int = 0
    file_posts: int = 0
    complete_posts: int = 0
    paths: list[str] = field(default_factory=list)
    file_request_bodies: list[bytes] = field(default_factory=list)
    session_payload_overrides: dict[str, object] = field(default_factory=dict)
    completion_response_body: bytes | None = None
    completion_status: int = 200
    completion_response_headers: dict[str, str] = field(default_factory=dict)


@contextlib.contextmanager
def serve_upload_api(recorder: UploadRecorder):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            recorder.paths.append(self.path)
            body_length = int(self.headers.get("Content-Length", "0") or "0")
            request_body = self.rfile.read(body_length) if body_length > 0 else b""

            if self.path == "/api/internal/releases/upload-sessions":
                recorder.session_posts += 1
                payload = {
                    "sessionId": SESSION_ID,
                    "expiresAtUtc": "2026-07-16T00:00:00Z",
                    "filesUrl": f"/api/internal/releases/upload-sessions/{SESSION_ID}/files",
                    "completeUrl": f"/api/internal/releases/upload-sessions/{SESSION_ID}/complete",
                }
                payload.update(recorder.session_payload_overrides)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))
                return

            if self.path.endswith("/files"):
                recorder.file_posts += 1
                recorder.file_request_bodies.append(request_body)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")
                return

            if self.path.endswith("/complete"):
                recorder.complete_posts += 1
                self.send_response(recorder.completion_status)
                self.send_header("Content-Type", "application/json")
                for name, value in recorder.completion_response_headers.items():
                    self.send_header(name, value)
                self.end_headers()
                response_body = recorder.completion_response_body
                if response_body is None:
                    response_body = json.dumps(
                        {
                            "status": "accepted",
                            "signedInInstallClaims": [
                                {
                                    "artifactId": "proof-artifact",
                                    "claimCode": "proof-secret-claim-code",
                                    "installDispatchUrl": (
                                        "https://example.invalid/downloads/install/proof-artifact"
                                        "?claimCode=proof-secret-url-claim"
                                    ),
                                    "signedUrl": "https://example.invalid/install?token=proof-secret-query-token",
                                }
                            ],
                            "credential": "proof-future-credential",
                            "apiKey": "proof-future-api-key",
                            "handoffCode": "proof-future-handoff-code",
                            "value": "eyJhbGciOiJIUzI1NiJ9.proof-future-jwt.signature",
                        }
                    ).encode("utf-8")
                self.wfile.write(response_body)
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            thread.join(timeout=5)


def run_publish(bundle_root: Path, base_url: str, registry_root: Path) -> subprocess.CompletedProcess[str]:
    return run_publish_with_script(SCRIPT, bundle_root, base_url, registry_root)


def run_publish_with_script(
    script_path: Path,
    bundle_root: Path,
    base_url: str,
    registry_root: Path,
    *,
    extra_env: dict[str, str | None] | None = None,
    shell_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("CHUMMER_RELEASE_UPLOAD_URL", None)
    env.pop("CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK", None)
    env.pop("CHUMMER_RELEASE_UPLOAD_TOKEN_FILE", None)
    env.pop("CHUMMER_RELEASE_UPLOAD_TOKEN_PATH", None)
    env.pop("CHUMMER_ARTIFACT_FACTORY_TOKEN", None)
    env.pop("CHUMMER_RELEASE_UPLOAD_ALLOW_PROOF_ONLY_VISUAL_HANDOFF", None)
    env.pop("CHUMMER_FORCE_NIGHTLY_PUBLISH", None)
    env.pop("CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF_PATH", None)
    env.pop("CHUMMER_UI_WINDOWS_DESKTOP_EXIT_GATE_PATH", None)
    env.update(
        {
            "CHUMMER_HUB_REGISTRY_ROOT": str(registry_root),
            "CHUMMER_RELEASE_UPLOAD_SESSIONS_URL": f"{base_url}/api/internal/releases/upload-sessions",
            "CHUMMER_RELEASE_UPLOAD_TOKEN": "test-token",
            "CHUMMER_RELEASE_UPLOAD_ATTEMPT_RECEIPT_HELPER": str(UPLOAD_ATTEMPT_RECEIPT_HELPER),
            "CHUMMER_RELEASE_UPLOAD_NON_INTERACTIVE": "1",
            "CHUMMER_RELEASE_UPLOAD_VERIFY_MANIFEST": "0",
            "CHUMMER_RELEASE_UPLOAD_VERIFY_ROUTES": "0",
            "CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH": "0",
            "CHUMMER_RELEASE_UPLOAD_VERIFY_PUBLIC_SHELL_TRUTH": "0",
            "CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH": "0",
        }
    )
    if extra_env:
        for key, value in extra_env.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
    return subprocess.run(
        ["bash", *(shell_args or []), str(script_path), str(bundle_root)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_publish_download_bundle_http_rejects_legacy_direct_upload_configuration(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            SCRIPT,
            bundle_root,
            base_url,
            registry_root,
            extra_env={
                "CHUMMER_RELEASE_UPLOAD_URL": f"{base_url}/api/internal/releases/bundles",
            },
        )

    assert result.returncode != 0
    assert "CHUMMER_RELEASE_UPLOAD_URL is retired" in result.stderr
    assert recorder.paths == []


def test_publish_download_bundle_http_rejects_direct_fallback_opt_in(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            SCRIPT,
            bundle_root,
            base_url,
            registry_root,
            extra_env={"CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK": "true"},
        )

    assert result.returncode != 0
    assert "Direct release upload fallback is permanently disabled" in result.stderr
    assert recorder.paths == []


def test_publish_download_bundle_http_requires_nightly_force_for_proof_only_visual_handoff(
    tmp_path: Path,
) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            SCRIPT,
            bundle_root,
            base_url,
            registry_root,
            extra_env={
                "CHUMMER_RELEASE_UPLOAD_ALLOW_PROOF_ONLY_VISUAL_HANDOFF": "1",
                "CHUMMER_FORCE_NIGHTLY_PUBLISH": "0",
            },
        )

    assert result.returncode != 0
    assert "also requires CHUMMER_FORCE_NIGHTLY_PUBLISH=1" in result.stderr
    assert recorder.paths == []


def test_publish_download_bundle_http_passes_explicit_handoff_paths_only_under_double_opt_in(
    tmp_path: Path,
) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture")
    handoff_path = bundle_root / "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"
    gate_path = bundle_root / "UI_WINDOWS_DESKTOP_EXIT_GATE.generated.json"
    handoff_log = tmp_path / "handoff-args.json"
    helper_path = script_path.parent / "verify-windows-installer-visual-proof-handoff.py"
    helper_path.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from pathlib import Path
Path(os.environ["HANDOFF_ARGS_LOG"]).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
print("windows_installer_visual_proof_handoff_gate:ok posture=proof_only")
""",
        encoding="utf-8",
    )
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            script_path,
            bundle_root,
            base_url,
            registry_root,
            extra_env={
                "CHUMMER_RELEASE_UPLOAD_ALLOW_PROOF_ONLY_VISUAL_HANDOFF": "1",
                "CHUMMER_FORCE_NIGHTLY_PUBLISH": "1",
                "CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF_PATH": str(handoff_path),
                "CHUMMER_UI_WINDOWS_DESKTOP_EXIT_GATE_PATH": str(gate_path),
                "HANDOFF_ARGS_LOG": str(handoff_log),
            },
        )

    assert result.returncode == 0, result.stdout + result.stderr
    args = json.loads(handoff_log.read_text(encoding="utf-8"))
    assert args == [
        "--files-dir",
        str(bundle_root / "files"),
        "--manifest",
        str(bundle_root / "releases.json"),
        "--manifest",
        str(bundle_root / "RELEASE_CHANNEL.generated.json"),
        "--handoff",
        str(handoff_path),
        "--windows-gate",
        str(gate_path),
    ]


def test_publish_download_bundle_http_uploads_same_shelf_signing_receipts(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    signing_path = bundle_root / "signing" / "signing-avalonia-win-x64.receipt.json"
    signing_path.parent.mkdir(parents=True)
    signing_path.write_text(
        '{"contractName":"chummer6-ui.desktop_artifact_signing","signingStatus":"pass"}\n',
        encoding="utf-8",
    )
    registry_root = write_registry(tmp_path / "registry")
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish(bundle_root, base_url, registry_root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert recorder.file_posts == 4
    assert any(
        b'signing/signing-avalonia-win-x64.receipt.json' in body
        for body in recorder.file_request_bodies
    )


def test_publish_download_bundle_http_rejects_cross_origin_session_endpoints(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    recorder = UploadRecorder(
        session_payload_overrides={"filesUrl": "https://attacker.invalid/upload"},
    )

    with serve_upload_api(recorder) as base_url:
        result = run_publish(bundle_root, base_url, registry_root)

    assert result.returncode != 0
    assert recorder.session_posts == 1
    assert recorder.file_posts == 0
    assert recorder.complete_posts == 0


def test_publish_download_bundle_http_rejects_unsafe_session_identity(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    recorder = UploadRecorder(session_payload_overrides={"sessionId": "../foreign"})

    with serve_upload_api(recorder) as base_url:
        result = run_publish(bundle_root, base_url, registry_root)

    assert result.returncode != 0
    assert "unsafe sessionId" in result.stderr
    assert recorder.session_posts == 1
    assert recorder.file_posts == 0


def test_publish_download_bundle_http_canonicalizes_release_truth_before_upload(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish(bundle_root, base_url, registry_root)

    assert result.returncode == 0, result.stderr or result.stdout
    assert recorder.session_posts == 1
    assert recorder.file_posts == 3
    assert recorder.complete_posts == 1
    assert "proof-secret-claim-code" not in result.stdout
    assert "proof-secret-url-claim" not in result.stdout
    assert "proof-secret-query-token" not in result.stdout
    assert "proof-secret-claim-code" not in result.stderr
    assert "proof-secret-url-claim" not in result.stderr
    assert "proof-secret-query-token" not in result.stderr
    assert "proof-future-credential" not in result.stdout
    assert "proof-future-api-key" not in result.stdout
    assert "proof-future-handoff-code" not in result.stdout
    assert "proof-future-jwt" not in result.stdout
    assert "signedInInstallClaimsCount" not in result.stdout
    assert "claimCode" not in result.stdout
    assert "installDispatchUrl" not in result.stdout
    assert "signedUrl" not in result.stdout

    receipt_path = bundle_root / "release-upload-handoff.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt_path.stat().st_mode & 0o777 == 0o600
    assert receipt["schemaVersion"] == "chummer.release-upload-handoff/v1"
    assert receipt["apiOrigin"] == base_url
    assert receipt["sessionId"] == SESSION_ID
    assert receipt["expiresAtUtc"] == "2026-07-16T00:00:00Z"
    assert receipt["candidate"]["version"] == "run-test"
    assert len(receipt["candidate"]["canonicalManifestSha256"]) == 64
    assert len(receipt["candidate"]["inventorySha256"]) == 64
    assert len(receipt["candidate"]["bundleIdentitySha256"]) == 64
    assert receipt["completion"]["state"] == "completed"
    assert [row["state"] for row in receipt["stateHistory"]] == [
        "created",
        "uploaded",
        "request_started",
        "completed",
    ]
    receipt_text = receipt_path.read_text(encoding="utf-8")
    assert "test-token" not in receipt_text
    assert "proof-secret" not in receipt_text

    for manifest_name in ("releases.json", "RELEASE_CHANNEL.generated.json"):
        payload = json.loads((bundle_root / manifest_name).read_text(encoding="utf-8"))
        assert payload["desktopTupleCoverage"]["externalProofRequests"] == [{"marker": "canonical-proof"}]
        assert payload["desktopTupleCoverage"]["desktopRouteTruth"] == [{"marker": "canonical-route"}]
        assert payload["installAwareArtifactRegistry"] == [{"marker": "canonical-install"}]
        assert payload["desktopSurfaceRefs"] == [{"marker": "canonical-surface"}]
        assert payload["artifactIdentityRegistry"] == [{"marker": "canonical-identity"}]
        assert payload["artifactPublicationBindings"] == [{"marker": "canonical-binding"}]
        assert payload["publicTrustMetrics"] == {
            "marker": "canonical-trust",
            "releaseChannel": {"supportabilityState": "review_required"},
        }
        assert payload["registryBoundaryCoverage"] == {"marker": "canonical-boundary"}
        assert payload["supportabilityState"] == "review_required"
        assert "review-required" in payload["supportabilitySummary"]
        assert "stale or incomplete proof receipts" in payload["supportabilitySummary"]
        assert "stale or incomplete proof receipts" in payload["knownIssueSummary"]


def test_publish_download_bundle_http_does_not_fail_after_publish_on_deep_response(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    recorder = UploadRecorder(completion_response_body=(b"[" * 1200) + b"0" + (b"]" * 1200))

    with serve_upload_api(recorder) as base_url:
        result = run_publish(bundle_root, base_url, registry_root)

    assert recorder.complete_posts == 1
    assert result.returncode == 0, result.stderr or result.stdout
    assert '"itemCount": 1' in result.stdout
    assert ("[" * 100) not in result.stdout


def test_publish_download_bundle_http_bounds_success_response_display(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    recorder = UploadRecorder(completion_response_body=b'"' + (b"x" * (1024 * 1024)) + b'"')

    with serve_upload_api(recorder) as base_url:
        result = run_publish(bundle_root, base_url, registry_root)

    assert recorder.complete_posts == 1
    assert result.returncode != 0
    assert "completion outcome is unknown" in result.stderr
    receipt = json.loads((bundle_root / "release-upload-handoff.json").read_text(encoding="utf-8"))
    assert receipt["completion"]["state"] == "request_started"


def test_publish_download_bundle_http_retains_ambiguous_completion_handoff(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    recorder = UploadRecorder(
        completion_status=503,
        completion_response_body=b'{"type":"publication-outcome-unknown","token":"must-not-leak"}',
    )

    with serve_upload_api(recorder) as base_url:
        result = run_publish(bundle_root, base_url, registry_root)

    assert recorder.complete_posts == 1
    assert result.returncode != 0
    assert "completion outcome is unknown" in result.stderr
    assert "Do not create another session" in result.stderr
    assert "must-not-leak" not in result.stdout
    assert "must-not-leak" not in result.stderr
    receipt = json.loads((bundle_root / "release-upload-handoff.json").read_text(encoding="utf-8"))
    assert receipt["sessionId"] == SESSION_ID
    assert receipt["completion"]["state"] == "request_started"
    assert receipt["completion"]["requestStartedAtUtc"]


def test_publish_download_bundle_http_never_persists_hostile_response_headers(
    tmp_path: Path,
) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    controlled_tmp = tmp_path / "controlled-tmp"
    controlled_tmp.mkdir()
    secret = "hostile-response-header-must-never-touch-disk"
    recorder = UploadRecorder(
        completion_status=503,
        completion_response_body=b'{"status":"publication-outcome-unknown"}',
        completion_response_headers={
            "Set-Cookie": f"release_session={secret}; HttpOnly; Secure",
            "Location": f"https://attacker.invalid/handoff?credential={secret}",
            "WWW-Authenticate": f'Bearer error_description="{secret}"',
        },
    )

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            SCRIPT,
            bundle_root,
            base_url,
            registry_root,
            extra_env={"TMPDIR": str(controlled_tmp)},
        )

    assert recorder.complete_posts == 1
    assert result.returncode != 0
    assert secret not in result.stdout
    assert secret not in result.stderr
    for root in (controlled_tmp, bundle_root):
        for path in root.rglob("*"):
            if path.is_file():
                assert secret.encode("utf-8") not in path.read_bytes(), path


def test_publish_download_bundle_http_never_dumps_raw_response_headers() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "-D " not in script
    assert "--dump-header" not in script
    assert "headers_file" not in script
    assert "headers_path" not in script
    assert "response-headers" not in script


def test_publish_download_bundle_http_warns_not_to_retry_after_post_completion_failure(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture")
    verifier = script_path.parent / "verify-releases-manifest.sh"
    verifier.write_text("#!/usr/bin/env bash\nexit 91\n", encoding="utf-8")
    verifier.chmod(0o755)
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            script_path,
            bundle_root,
            base_url,
            registry_root,
            extra_env={"CHUMMER_RELEASE_UPLOAD_VERIFY_MANIFEST": "1"},
        )

    assert recorder.complete_posts == 1
    assert result.returncode == 91
    assert "may already be public" in result.stderr
    assert "Do not create or publish another session" in result.stderr
    receipt = json.loads((bundle_root / "release-upload-handoff.json").read_text(encoding="utf-8"))
    assert receipt["completion"]["state"] == "completed"


def test_publish_download_bundle_http_launches_artifact_factory_batch_when_helpers_exist(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture")
    materializer_log = tmp_path / "materializer-log.json"
    launcher_log = tmp_path / "launcher-log.json"
    ambient_token_file = tmp_path / "ambient-token-file"
    ambient_token_file.write_text("ambient-file-secret\n", encoding="utf-8")
    ambient_token_file.chmod(0o600)
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            script_path,
            bundle_root,
            base_url,
            registry_root,
            extra_env={
                "CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH": "1",
                "CHUMMER_ARTIFACT_FACTORY_TOKEN": "factory-only-token",
                "TOKEN": "ambient-generic-token",
                "ARTIFACT_FACTORY_TOKEN": "ambient-generic-factory-token",
                "FLEET_INTERNAL_API_TOKEN": "ambient-fleet-token",
                "CHUMMER_RELEASE_UPLOAD_TICKET": "ambient-release-ticket",
                "CHUMMER_RELEASE_UPLOAD_TOKEN_FILE": str(ambient_token_file),
                "CHUMMER_RELEASE_UPLOAD_TOKEN_PATH": str(ambient_token_file),
                "CHUMMER_ARTIFACT_FACTORY_REQUIRED_FAMILIES": "release,publication",
                "CHUMMER_ARTIFACT_FACTORY_REQUESTED_FORMATS": "caption,packet",
                "CHUMMER_ARTIFACT_FACTORY_AUDIENCE": "gm",
                "CHUMMER_ARTIFACT_FACTORY_LOCALE": "de-DE",
                "ARTIFACT_FACTORY_MATERIALIZER_LOG": str(materializer_log),
                "ARTIFACT_FACTORY_LAUNCHER_LOG": str(launcher_log),
            },
        )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Artifact-factory batch launched via" in result.stdout
    materializer_payload = json.loads(materializer_log.read_text(encoding="utf-8"))
    launcher_payload = json.loads(launcher_log.read_text(encoding="utf-8"))
    assert materializer_payload["requestedBy"] == "fleet.release"
    assert materializer_payload["requiredFamilies"] == ["release", "publication"]
    assert materializer_payload["requestedFormats"] == ["caption", "packet"]
    assert materializer_payload["audience"] == "gm"
    assert materializer_payload["locale"] == "de-DE"
    assert materializer_payload["credentialEnvironment"] == {}
    assert materializer_payload["credentialFileContents"] == {}
    assert materializer_payload["promotionResult"]["responseSanitized"] is True
    assert materializer_payload["promotionResult"]["status"] == "accepted"
    assert "signedInInstallClaims" not in materializer_payload["promotionResult"]
    assert "credential" not in materializer_payload["promotionResult"]
    assert "apiKey" not in materializer_payload["promotionResult"]
    assert launcher_payload["baseUrl"] == base_url
    assert launcher_payload["token"] == "factory-only-token"
    assert "factory-only-token" not in launcher_payload["argv"]
    assert "test-token" not in launcher_payload["argv"]
    assert launcher_payload["requestPayload"]["requiredFamilies"] == ["release", "publication"]


def test_publish_download_bundle_http_never_reuses_release_token_for_artifact_factory(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture")
    launcher_log = tmp_path / "launcher-log.json"
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            script_path,
            bundle_root,
            base_url,
            registry_root,
            extra_env={
                "CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH": "1",
                "CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH_REQUIRED": "1",
                "ARTIFACT_FACTORY_LAUNCHER_LOG": str(launcher_log),
            },
        )

    assert recorder.complete_posts == 1
    assert result.returncode != 0
    assert "requires its own CHUMMER_ARTIFACT_FACTORY_TOKEN" in result.stderr
    assert "test-token" not in result.stdout
    assert "test-token" not in result.stderr
    assert not launcher_log.exists()


def test_publish_download_bundle_http_rejects_insecure_upload_token_files(tmp_path: Path) -> None:
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture")
    secure_target = tmp_path / "secure-token"
    secure_target.write_text("file-only-secret\n", encoding="utf-8")
    secure_target.chmod(0o600)
    insecure_file = tmp_path / "world-readable-token"
    insecure_file.write_text("file-only-secret\n", encoding="utf-8")
    insecure_file.chmod(0o644)
    symlink_file = tmp_path / "token-link"
    symlink_file.symlink_to(secure_target)

    recorder = UploadRecorder()
    with serve_upload_api(recorder) as base_url:
        for index, token_path in enumerate((insecure_file, symlink_file)):
            bundle_root = write_bundle(tmp_path / f"bundle-{index}")
            result = run_publish_with_script(
                script_path,
                bundle_root,
                base_url,
                registry_root,
                extra_env={
                    "CHUMMER_RELEASE_UPLOAD_TOKEN": None,
                    "CHUMMER_RELEASE_UPLOAD_TOKEN_FILE": str(token_path),
                },
            )
            assert result.returncode != 0
            assert "current-owner, non-symlink regular file with mode 0600" in result.stderr
            assert "file-only-secret" not in result.stdout
            assert "file-only-secret" not in result.stderr

    assert recorder.session_posts == 0


def test_publish_download_bundle_http_accepts_owner_mode_0600_upload_token_file(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture")
    token_path = tmp_path / "upload-token"
    token_path.write_text("file-only-secret\n", encoding="utf-8")
    token_path.chmod(0o600)
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            script_path,
            bundle_root,
            base_url,
            registry_root,
            extra_env={
                "CHUMMER_RELEASE_UPLOAD_TOKEN": None,
                "CHUMMER_RELEASE_UPLOAD_TOKEN_FILE": str(token_path),
            },
        )

    assert result.returncode == 0, result.stderr or result.stdout
    assert recorder.complete_posts == 1
    assert "file-only-secret" not in result.stdout
    assert "file-only-secret" not in result.stderr


def test_publish_download_bundle_http_disables_hostile_ambient_curlrc(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture")
    home = tmp_path / "home"
    home.mkdir()
    trace_path = tmp_path / "curl-trace.log"
    (home / ".curlrc").write_text(
        f'trace-ascii = "{trace_path}"\ntrace-time\n',
        encoding="utf-8",
    )
    upload_secret = "curlrc-must-not-capture-this-secret"
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            script_path,
            bundle_root,
            base_url,
            registry_root,
            extra_env={
                "HOME": str(home),
                "CHUMMER_RELEASE_UPLOAD_TOKEN": upload_secret,
            },
        )

    assert result.returncode == 0, result.stderr or result.stdout
    assert recorder.complete_posts == 1
    assert not trace_path.exists()
    assert upload_secret not in result.stdout
    assert upload_secret not in result.stderr
    assert "upload-auth.curl" not in SCRIPT.read_text(encoding="utf-8")


def test_publish_download_bundle_http_disables_inherited_xtrace_before_secret_capture(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture")
    upload_secret = "xtrace-must-not-print-this-upload-secret"
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            script_path,
            bundle_root,
            base_url,
            registry_root,
            extra_env={"CHUMMER_RELEASE_UPLOAD_TOKEN": upload_secret},
            shell_args=["-x"],
        )

    assert result.returncode == 0, result.stderr or result.stdout
    assert recorder.complete_posts == 1
    assert upload_secret not in result.stdout
    assert upload_secret not in result.stderr


def test_publish_download_bundle_http_fails_closed_when_artifact_factory_required_helper_is_missing(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture", include_materializer=False)
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            script_path,
            bundle_root,
            base_url,
            registry_root,
            extra_env={
                "CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH": "1",
                "CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH_REQUIRED": "1",
            },
        )

    assert result.returncode != 0
    assert "Artifact-factory request materializer missing:" in result.stderr


def test_publish_download_bundle_http_runs_shelf_and_public_shell_truth_gates(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture")
    shelf_log = tmp_path / "shelf-truth-log.json"
    public_shell_log = tmp_path / "public-shell-truth-log.json"
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            script_path,
            bundle_root,
            base_url,
            registry_root,
            extra_env={
                "CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH": "1",
                "CHUMMER_RELEASE_UPLOAD_VERIFY_PUBLIC_SHELL_TRUTH": "1",
                "CHUMMER_PUBLIC_BASE_URL": base_url,
                "SHELF_TRUTH_LOG": str(shelf_log),
                "PUBLIC_SHELL_TRUTH_LOG": str(public_shell_log),
            },
        )

    assert result.returncode == 0, result.stderr or result.stdout
    shelf_payload = json.loads(shelf_log.read_text(encoding="utf-8"))
    public_shell_payload = json.loads(public_shell_log.read_text(encoding="utf-8"))
    assert shelf_payload == {
        "baseUrl": base_url,
        "localManifest": str(bundle_root / "releases.json"),
        "localCanonicalManifest": str(bundle_root / "RELEASE_CHANNEL.generated.json"),
    }
    assert public_shell_payload == {"baseUrl": base_url}


def test_publish_download_bundle_http_fails_when_required_shelf_truth_gate_script_is_missing(tmp_path: Path) -> None:
    bundle_root = write_bundle(tmp_path / "bundle")
    registry_root = write_registry(tmp_path / "registry")
    script_path = write_script_fixture(tmp_path / "fixture", include_shelf_truth_gate=False)
    recorder = UploadRecorder()

    with serve_upload_api(recorder) as base_url:
        result = run_publish_with_script(
            script_path,
            bundle_root,
            base_url,
            registry_root,
            extra_env={
                "CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH": "1",
                "CHUMMER_PUBLIC_BASE_URL": base_url,
            },
        )

    assert result.returncode != 0
    assert "public_download_shelf_truth_gate.py" in result.stderr
