from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = (
    REPO_ROOT
    / "Chummer.Run.Api"
    / "wwwroot"
    / "artifacts"
    / "mac-codex-release-pipeline"
    / "bootstrap.sh"
)


def canonical_manifest(
    proof_status: str,
    *,
    top: str = "review_required",
    public: str = "review_required",
    registry: str = "review_required",
    public_posture: str = "blocked",
    registry_posture: str = "blocked",
) -> bytes:
    return json.dumps(
        {
            "supportabilityState": top,
            "publicTrustMetrics": {
                "releaseChannel": {
                    "supportabilityState": public,
                    "posture": public_posture,
                },
                "proofFreshness": {"status": proof_status},
            },
            "registryBoundaryCoverage": {
                "releaseChannel": {
                    "supportabilityState": registry,
                    "publicTrustPosture": registry_posture,
                },
            },
        }
    ).encode("utf-8")


@contextlib.contextmanager
def canonical_server(
    *,
    status: int = 200,
    body: bytes = b"{}",
) -> Iterator[tuple[str, list[str]]]:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            requests.append(self.command)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args: object) -> None:
            del args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/downloads/RELEASE_CHANNEL.generated.json", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_preflight(url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; verify_live_canonical_supportability_preflight "$2"',
            "live-canonical-preflight-test",
            str(BOOTSTRAP),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "CHUMMER_LIVE_CANONICAL_PREFLIGHT_TIMEOUT_SECONDS": "2",
        },
    )


def projection_manifest() -> dict[str, object]:
    return {
        "version": "run-20260714-163300",
        "publishedAt": "2026-07-14T16:35:12Z",
        "channel": "preview",
        "channelId": "preview",
        "status": "published",
        "rolloutState": "public_release_review_required",
        "rolloutReason": "Stale proof keeps the release review-required.",
        "supportabilityState": "review_required",
        "publicTrustMetrics": {
            "proofFreshness": {"status": "stale"},
            "releaseChannel": {
                "posture": "blocked",
                "rolloutState": "public_release_review_required",
                "supportabilityState": "review_required",
            },
        },
        "registryBoundaryCoverage": {
            "releaseChannel": {
                "publicTrustPosture": "blocked",
                "rolloutState": "public_release_review_required",
                "supportabilityState": "review_required",
            },
        },
        "artifacts": [],
    }


def run_projection_verifier(
    local_path: Path,
    compatibility_url: str,
    canonical_url: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; verify_live_release_projection "$2" "$3" "$4"',
            "live-canonical-projection-test",
            str(BOOTSTRAP),
            str(local_path),
            compatibility_url,
            canonical_url,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )


@pytest.mark.parametrize("proof_status", ["stale", "missing"])
def test_preflight_accepts_review_floor_at_all_three_paths(proof_status: str) -> None:
    with canonical_server(body=canonical_manifest(proof_status)) as (url, requests):
        result = run_preflight(url)

    assert result.returncode == 0, result.stderr
    assert "all supportability paths are review_required" in result.stdout
    assert "all public trust posture paths are blocked" in result.stdout
    assert requests == ["GET"]


def test_preflight_rejects_every_drifted_supportability_path_before_release_work() -> None:
    body = canonical_manifest(
        "stale",
        top="preview_supported",
        public="preview_supported",
        registry="preview_supported",
        public_posture="preview",
        registry_posture="preview",
    )
    with canonical_server(body=body) as (url, requests):
        result = run_preflight(url)

    assert result.returncode == 1
    assert "supportabilityState='review_required' at all three canonical supportability paths" in result.stderr
    assert "supportabilityState='preview_supported'" in result.stderr
    assert "publicTrustMetrics.releaseChannel.supportabilityState='preview_supported'" in result.stderr
    assert "registryBoundaryCoverage.releaseChannel.supportabilityState='preview_supported'" in result.stderr
    assert "publicTrustMetrics.releaseChannel.posture='preview'" in result.stderr
    assert "registryBoundaryCoverage.releaseChannel.publicTrustPosture='preview'" in result.stderr
    assert "No release build or upload was started" in result.stderr
    assert "deploy/activate the corrected canonicalization or live projection" in result.stderr
    assert requests == ["GET"]


def test_preflight_does_not_invent_review_floor_for_fresh_proof() -> None:
    body = canonical_manifest(
        "fresh",
        top="preview_supported",
        public="preview_supported",
        registry="preview_supported",
        public_posture="preview",
        registry_posture="preview",
    )
    with canonical_server(body=body) as (url, requests):
        result = run_preflight(url)

    assert result.returncode == 0, result.stderr
    assert "proofFreshness.status=fresh" in result.stdout
    assert requests == ["GET"]


@pytest.mark.parametrize(
    ("public_posture", "registry_posture", "expected_fragment"),
    [
        ("preview", "blocked", "publicTrustMetrics.releaseChannel.posture='preview'"),
        ("blocked", "preview", "registryBoundaryCoverage.releaseChannel.publicTrustPosture='preview'"),
        ("", "blocked", "publicTrustMetrics.releaseChannel.posture=''"),
    ],
)
def test_preflight_rejects_public_trust_posture_relaxation_for_stale_proof(
    public_posture: str,
    registry_posture: str,
    expected_fragment: str,
) -> None:
    body = canonical_manifest(
        "stale",
        public_posture=public_posture,
        registry_posture=registry_posture,
    )
    with canonical_server(body=body) as (url, requests):
        result = run_preflight(url)

    assert result.returncode == 1
    assert expected_fragment in result.stderr
    assert "No release build or upload was started" in result.stderr
    assert requests == ["GET"]


def test_final_projection_verifier_accepts_identical_release_truth(tmp_path: Path) -> None:
    local_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    local_path.write_text(json.dumps(projection_manifest()), encoding="utf-8")
    with canonical_server(body=json.dumps({"downloads": []}).encode("utf-8")) as (
        compatibility_url,
        compatibility_requests,
    ), canonical_server(body=local_path.read_bytes()) as (canonical_url, canonical_requests):
        result = run_projection_verifier(local_path, compatibility_url, canonical_url)

    assert result.returncode == 0, result.stderr
    assert compatibility_requests == ["GET"]
    assert canonical_requests == ["GET"]


@pytest.mark.parametrize(
    ("path", "replacement", "expected_field"),
    [
        (("supportabilityState",), "preview_supported", "supportabilityState"),
        (
            ("publicTrustMetrics", "releaseChannel", "posture"),
            "preview",
            "publicTrustMetrics.releaseChannel.posture",
        ),
        (
            ("registryBoundaryCoverage", "releaseChannel", "publicTrustPosture"),
            "preview",
            "registryBoundaryCoverage.releaseChannel.publicTrustPosture",
        ),
        (("rolloutReason",), "Optimistic publication narrative.", "rolloutReason"),
    ],
)
def test_final_projection_verifier_rejects_post_publish_truth_drift(
    tmp_path: Path,
    path: tuple[str, ...],
    replacement: str,
    expected_field: str,
) -> None:
    local_payload = projection_manifest()
    live_payload = json.loads(json.dumps(local_payload))
    target = live_payload
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = replacement

    local_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    local_path.write_text(json.dumps(local_payload), encoding="utf-8")
    with canonical_server(body=json.dumps({"downloads": []}).encode("utf-8")) as (
        compatibility_url,
        compatibility_requests,
    ), canonical_server(body=json.dumps(live_payload).encode("utf-8")) as (
        canonical_url,
        canonical_requests,
    ):
        result = run_projection_verifier(local_path, compatibility_url, canonical_url)

    assert result.returncode == 1
    assert "changed uploaded release truth after promotion" in result.stderr
    assert expected_field in result.stderr
    assert compatibility_requests == ["GET"]
    assert canonical_requests == ["GET"]


def test_preflight_fails_closed_on_unknown_proof_freshness_status() -> None:
    with canonical_server(body=canonical_manifest("future_status")) as (url, requests):
        result = run_preflight(url)

    assert result.returncode == 1
    assert (
        "unrecognized publicTrustMetrics.proofFreshness.status='future_status'"
        in result.stderr
    )
    assert "No release build or upload was started" in result.stderr
    assert "Operator/deployment handoff required" in result.stderr
    assert "fresh, stale, or missing" in result.stderr
    assert requests == ["GET"]


@pytest.mark.parametrize("status", [403, 503])
def test_preflight_fails_closed_on_unavailable_http_response(status: int) -> None:
    with canonical_server(status=status, body=b"access unavailable") as (url, requests):
        result = run_preflight(url)

    assert result.returncode == 1
    assert f"HTTP {status}" in result.stderr
    assert "No release build or upload was started" in result.stderr
    assert "Operator/deployment handoff required" in result.stderr
    assert requests == ["GET"]


def test_preflight_fails_closed_on_network_and_contract_failures() -> None:
    reserved_socket = socket.socket()
    reserved_socket.bind(("127.0.0.1", 0))
    unavailable_host, unavailable_port = reserved_socket.getsockname()
    try:
        network_result = run_preflight(f"http://{unavailable_host}:{unavailable_port}/manifest.json")
    finally:
        reserved_socket.close()
    assert network_result.returncode == 1
    assert "could not reach" in network_result.stderr
    assert "No release build or upload was started" in network_result.stderr
    assert "Operator/deployment handoff required" in network_result.stderr

    with canonical_server(body=b"not-json") as (malformed_url, malformed_requests):
        malformed_result = run_preflight(malformed_url)
    assert malformed_result.returncode == 1
    assert "could not parse" in malformed_result.stderr
    assert "Operator/deployment handoff required" in malformed_result.stderr
    assert malformed_requests == ["GET"]

    missing_proof = json.dumps({"supportabilityState": "review_required"}).encode("utf-8")
    with canonical_server(body=missing_proof) as (missing_url, missing_requests):
        missing_result = run_preflight(missing_url)
    assert missing_result.returncode == 1
    assert "could not determine publicTrustMetrics.proofFreshness.status" in missing_result.stderr
    assert "Operator/deployment handoff required" in missing_result.stderr
    assert missing_requests == ["GET"]


def test_preflight_runs_before_clone_restore_build_and_upload_but_final_verifier_remains() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

    call = 'verify_live_canonical_supportability_preflight "$canonical_verify_url"'
    preflight_index = bootstrap.index(call, bootstrap.index("main()"))
    clone_index = bootstrap.index('clone_or_update "https://github.com/ArchonMegalon/chummer6-ui.git"')
    restore_index = bootstrap.index('log "restoring $project for $rid"')
    build_index = bootstrap.index('log "publishing $project"')
    upload_index = bootstrap.index('log "uploading release bundle via staged HTTP session"')
    final_verify_index = bootstrap.index('log "verifying live canonical manifest at $canonical_verify_url"')

    assert preflight_index < clone_index < restore_index < build_index < upload_index < final_verify_index
    assert bootstrap.count(call) == 1
    assert bootstrap.count('bash scripts/verify-releases-manifest.sh "$canonical_verify_url"') == 1
    assert bootstrap.count(
        'verify_live_release_projection "$dist_dir/RELEASE_CHANNEL.generated.json" '
        '"$compatibility_verify_url" "$canonical_verify_url"'
    ) == 1
