from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_public_download_only_postdeploy.py"
SPEC = importlib.util.spec_from_file_location("public_download_postdeploy", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
postdeploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(postdeploy)


class Response:
    def __init__(
        self,
        status: int,
        payload: dict[str, object],
        *,
        private: bool = False,
        content_type: str = "application/json",
    ) -> None:
        self.status_code = status
        self._payload = payload
        self.headers = {"Content-Type": content_type}
        if private:
            self.headers = {
                "Content-Type": content_type,
                "Cache-Control": "private, no-store, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            }

    def json(self) -> dict[str, object]:
        return self._payload


class StreamResponse:
    def __init__(
        self,
        url: str,
        body: bytes,
        *,
        status: int = 200,
        generation: str = "generation-a",
        headers: dict[str, str] | None = None,
        request_headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status
        self.url = url
        self.body = body
        self.history: list[object] = []
        self.headers = {
            "Content-Length": str(len(body)),
            postdeploy.GENERATION_HEADER: generation,
        }
        self.headers.update(headers or {})
        self.request = SimpleNamespace(headers=request_headers or {})
        self.closed = False

    def iter_content(self, chunk_size: int) -> Any:
        step = max(1, min(chunk_size, 7))
        for offset in range(0, len(self.body), step):
            yield self.body[offset : offset + step]

    def close(self) -> None:
        self.closed = True


class DeliveryFixture:
    def __init__(
        self,
        tmp_path: Path,
        *,
        embed_metadata: bool = True,
        semantic_payload_route: bool = False,
    ) -> None:
        self.base_url = "https://chummer.run"
        self.generation = "generation-a"
        self.version = "run-test"
        self.artifact_id = "avalonia-win-x64-installer"
        self.installer_name = "chummer-avalonia-win-x64-installer.exe"
        self.payload_name = "chummer-avalonia-win-x64-payload.zip"
        self.installer_url = f"{self.base_url}/downloads/files/{self.installer_name}"
        self.payload_url = (
            f"{self.base_url}/downloads/files/{self.payload_name}"
        )
        self.manifest_payload_url = (
            f"{self.base_url}/downloads/g/{self.generation}/install/"
            f"{self.artifact_id}/payload"
            if semantic_payload_route
            else self.payload_url
        )
        self.sidecar_url = self.payload_url + ".json"
        self.canonical_url = (
            f"{self.base_url}/downloads/RELEASE_CHANNEL.generated.json"
        )
        self.compatibility_url = f"{self.base_url}/downloads/releases.json"
        self.payload_bytes = b"payload-body-v1"
        self.payload_sha256 = hashlib.sha256(self.payload_bytes).hexdigest()
        metadata = (
            b"payloadDownloadUrl\x00"
            + self.payload_url.encode()
            + b"\x00payloadSha256\x00"
            + self.payload_sha256.encode()
            + b"\x00payloadSizeBytes\x00"
            + str(len(self.payload_bytes)).encode()
        )
        if not embed_metadata:
            metadata = b"x" * len(metadata)
        self.installer_bytes = b"MZ\x00" + metadata
        self.sidecar: dict[str, object] = {
            "contractName": postdeploy.SIDECAR_CONTRACT,
            "downloadUrl": self.payload_url,
            "fileName": self.payload_name,
            "installerFileName": self.installer_name,
            "payloadAcquisitionMode": "download",
            "releaseVersion": self.version,
            "sha256": self.payload_sha256,
            "sizeBytes": len(self.payload_bytes),
        }
        self.artifact: dict[str, object] = {
            "artifactId": self.artifact_id,
            "id": self.artifact_id,
            "platform": "windows",
            "rid": "win-x64",
            "arch": "x64",
            "kind": "installer",
            "head": "avalonia",
            "channel": "preview",
            "channelId": "preview",
            "version": self.version,
            "releaseVersion": self.version,
            "artifactByteVisibility": "public",
            "installAccessClass": "open_public",
            "installerMode": "bootstrap",
            "payloadAcquisitionMode": "download",
            "previewPolicy": "preview_policy",
            "publicInstallRoute": None,
            "signature": {
                "policy": "preview_policy",
                "required": False,
                "status": "unsigned",
            },
            "fileName": self.installer_name,
            "downloadUrl": f"/downloads/files/{self.installer_name}",
            "sha256": hashlib.sha256(self.installer_bytes).hexdigest(),
            "sizeBytes": len(self.installer_bytes),
            "payloadFileName": self.payload_name,
            "payloadDownloadUrl": self.manifest_payload_url.removeprefix(
                self.base_url
            ),
            "payloadSha256": self.payload_sha256,
            "payloadSizeBytes": len(self.payload_bytes),
        }
        self.route: dict[str, object] = {
            "artifactId": self.artifact_id,
            "platform": "windows",
            "rid": "win-x64",
            "publicationState": "preview",
            "visibility": "public_artifact_only",
            "promotionState": "proof_required",
            "publicInstallRoute": None,
            "routeAuthority": False,
            "updateEligibility": "blocked_missing_proof",
        }
        self.canonical: dict[str, object] = {
            "generationId": self.generation,
            "version": self.version,
            "channelId": "preview",
            "rolloutState": "coverage_incomplete",
            "supportabilityState": "review_required",
            "status": "published",
            "registryCommit": "d" * 40,
            "desktopTupleCoverage": {"desktopRouteTruth": [self.route]},
            "artifacts": [self.artifact],
        }
        compatibility_row = {
            key: value
            for key, value in self.artifact.items()
            if key != "artifactByteVisibility"
        }
        compatibility_row["url"] = compatibility_row["downloadUrl"]
        self.compatibility: dict[str, object] = {
            "generationId": self.generation,
            "version": self.version,
            "channel": "preview",
            "rolloutState": "coverage_incomplete",
            "supportabilityState": "review_required",
            "status": "published",
            "downloads": [compatibility_row],
        }
        self.root = tmp_path / "bundle"
        self.files = self.root / "files"
        self.files.mkdir(parents=True)
        self.evidence_root = self.root / "release-evidence"
        self.evidence_root.mkdir()
        self.local_manifest = self.root / "releases.json"
        self.local_canonical = self.root / "RELEASE_CHANNEL.generated.json"
        self.responses: dict[str, StreamResponse] = {}
        self.rewrite()

    @staticmethod
    def json_bytes(payload: dict[str, object]) -> bytes:
        return json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"

    def rewrite(self) -> None:
        canonical_bytes = self.json_bytes(self.canonical)
        manifest_bytes = self.json_bytes(self.compatibility)
        sidecar_bytes = self.json_bytes(self.sidecar)
        release_scope_sha256 = "a" * 64
        evidence_registry_commit = "b" * 40
        artifact_handoff: dict[str, object] = {
            "contractName": "chummer.public-preview-byte-handoff/v1",
            "status": "approved_public_preview_bytes",
            "sourcePublicationState": "preview",
            "releaseScopeDecisionSha256": release_scope_sha256,
            "releaseVersion": self.version,
            "channel": "preview",
            "artifactId": self.artifact_id,
            "head": "avalonia",
            "platform": "windows",
            "rid": "win-x64",
            "arch": "x64",
            "sha256": hashlib.sha256(self.installer_bytes).hexdigest(),
            "sizeBytes": len(self.installer_bytes),
            "artifactAccessClass": "open_public",
            "signingRequirement": "preview_unsigned_allowed",
            "downloadUrl": f"/downloads/files/{self.installer_name}",
            "publicInstallRoute": (
                f"/downloads/install/{self.artifact_id}"
            ),
        }
        release_decision: dict[str, object] = {
            "artifactAccessClass": "open_public",
            "artifactHandoff": artifact_handoff,
            "channel": "preview",
            "contractName": "chummer.preview-release-decision/v2",
            "manifestSha256": hashlib.sha256(canonical_bytes).hexdigest(),
            "platforms": ["windows"],
            "primaryHeadByPlatform": {"windows": "avalonia"},
            "registryCommit": evidence_registry_commit,
            "releaseDecisionStatus": "review_required",
            "releaseScopeDecisionSha256": release_scope_sha256,
            "releaseVersion": self.version,
            "status": "review_required",
            "verdict": "PREVIEW_RELEASE_REVIEW_REQUIRED",
        }
        decision_bytes = self.json_bytes(release_decision)
        decision_sha256 = hashlib.sha256(decision_bytes).hexdigest()
        authority_snapshot: dict[str, object] = {
            "artifactCount": 1,
            "artifacts": [
                {
                    "arch": "x64",
                    "artifactId": self.artifact_id,
                    "downloadUrl": f"/downloads/files/{self.installer_name}",
                    "head": "avalonia",
                    "installAccessClass": "open_public",
                    "kind": "installer",
                    "platform": "windows",
                    "publicInstallRoute": (
                        f"/downloads/install/{self.artifact_id}"
                    ),
                    "rid": "win-x64",
                    "sha256": hashlib.sha256(
                        self.installer_bytes
                    ).hexdigest(),
                    "sizeBytes": len(self.installer_bytes),
                }
            ],
            "authorityContract": "chummer.release-authority-snapshot/v2",
            "availablePlatforms": ["windows"],
            "channel": "preview",
            "downloadAccessPosture": "open_public",
            "knownIssueSummary": (
                "Preview release remains review-required."
            ),
            "manifestSha256": hashlib.sha256(canonical_bytes).hexdigest(),
            "primaryHeadByPlatform": {"windows": "avalonia"},
            "registryCommit": evidence_registry_commit,
            "releaseDecisionSha256": decision_sha256,
            "releaseDecisionStatus": "review_required",
            "releaseVersion": self.version,
            "rolloutState": "public_release_review_required",
            "status": "published",
            "supportabilityState": "review_required",
        }
        snapshot_bytes = self.json_bytes(authority_snapshot)
        current: dict[str, object] = {
            "decisionSha256": decision_sha256,
            "releaseVersion": self.version,
            "snapshotSha256": hashlib.sha256(
                snapshot_bytes
            ).hexdigest(),
            "status": "review_required",
        }
        self.release_truth: dict[str, object] = {
            "contractName": "chummer.release-truth-projection/v1",
            "releaseVersion": self.version,
            "channel": "preview",
            "releaseStatus": "published",
            "rolloutState": "public_release_review_required",
            "supportabilityState": "review_required",
            "availablePlatforms": ["windows"],
            "primaryHeadByPlatform": {"windows": "avalonia"},
            "artifactCount": 1,
            "downloadAccessPosture": "open_public",
            "knownIssueSummary": "Preview release remains review-required.",
            "manifestSha256": hashlib.sha256(canonical_bytes).hexdigest(),
            "registryCommit": evidence_registry_commit,
            "releaseDecisionStatus": "review_required",
            "releaseDecisionSha256": decision_sha256,
            "releaseScopeDecisionSha256": release_scope_sha256,
            "artifactHandoff": artifact_handoff,
        }
        live_canonical = {**self.canonical, "releaseTruth": self.release_truth}
        live_compatibility = {
            **self.compatibility,
            "releaseTruth": self.release_truth,
        }
        live_canonical_bytes = self.json_bytes(live_canonical)
        live_manifest_bytes = self.json_bytes(live_compatibility)
        self.local_canonical.write_bytes(canonical_bytes)
        self.local_manifest.write_bytes(manifest_bytes)
        (self.files / f"{self.payload_name}.json").write_bytes(sidecar_bytes)
        (self.evidence_root / "CURRENT.json").write_bytes(
            self.json_bytes(current)
        )
        (self.evidence_root / "SNAPSHOT.json").write_bytes(snapshot_bytes)
        (self.evidence_root / "RELEASE_DECISION.json").write_bytes(
            decision_bytes
        )
        self.responses = {
            self.canonical_url: StreamResponse(
                self.canonical_url,
                live_canonical_bytes,
                generation=self.generation,
            ),
            self.compatibility_url: StreamResponse(
                self.compatibility_url,
                live_manifest_bytes,
                generation=self.generation,
            ),
            self.installer_url: StreamResponse(
                self.installer_url,
                self.installer_bytes,
                generation=self.generation,
            ),
            self.payload_url: StreamResponse(
                self.payload_url,
                self.payload_bytes,
                generation=self.generation,
            ),
            self.sidecar_url: StreamResponse(
                self.sidecar_url,
                sidecar_bytes,
                generation=self.generation,
            ),
        }

    def install(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, bool]]:
        calls: list[tuple[str, bool]] = []

        def fake_get(
            _session: object,
            url: str,
            timeout: float,
            *,
            stream: bool,
        ) -> StreamResponse:
            assert timeout == 1
            calls.append((url, stream))
            return self.responses[url]

        monkeypatch.setattr(postdeploy, "anonymous_get", fake_get)
        return calls

    def verify(self) -> dict[str, object]:
        with postdeploy.anonymous_session() as session:
            return postdeploy.verify_public_download_delivery(
                session=session,
                delivery_phase=postdeploy.DELIVERY_PHASE_WINDOWS_PREVIEW,
                base_url=self.base_url,
                local_manifest_path=self.local_manifest,
                local_canonical_manifest_path=self.local_canonical,
                timeout=1,
            )


def control_release_truth() -> dict[str, object]:
    release_scope_sha256 = "a" * 64
    return {
        "artifactCount": 1,
        "artifactHandoff": {
            "arch": "x64",
            "artifactAccessClass": "open_public",
            "artifactId": "avalonia-win-x64-installer",
            "channel": "preview",
            "contractName": "chummer.public-preview-byte-handoff/v1",
            "downloadUrl": (
                "/downloads/files/"
                "chummer-avalonia-win-x64-installer.exe"
            ),
            "head": "avalonia",
            "platform": "windows",
            "publicInstallRoute": (
                "/downloads/install/avalonia-win-x64-installer"
            ),
            "releaseScopeDecisionSha256": release_scope_sha256,
            "releaseVersion": "run-test",
            "rid": "win-x64",
            "sha256": "b" * 64,
            "signingRequirement": "preview_unsigned_allowed",
            "sizeBytes": 1,
            "sourcePublicationState": "preview",
            "status": "approved_public_preview_bytes",
        },
        "availablePlatforms": ["windows"],
        "channel": "preview",
        "contractName": "chummer.release-truth-projection/v1",
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": "Preview release remains review-required.",
        "manifestSha256": "c" * 64,
        "primaryHeadByPlatform": {"windows": "avalonia"},
        "registryCommit": "d" * 40,
        "releaseDecisionSha256": "e" * 64,
        "releaseDecisionStatus": "review_required",
        "releaseScopeDecisionSha256": release_scope_sha256,
        "releaseStatus": "published",
        "releaseVersion": "run-test",
        "rolloutState": "public_release_review_required",
        "supportabilityState": "review_required",
    }


def responses() -> dict[str, Response]:
    serving = {
        "contractName": postdeploy.READINESS_CONTRACT,
        "ready": True,
        "status": "pass",
        "servingReady": True,
        "overallReady": False,
        "overallStatus": "fail",
        "publicationReady": False,
        "checks": [],
        "releaseShelf": {"servingReady": True},
    }
    result = {
        "/api/ready/public-downloads": Response(200, serving),
        **{
            path: Response(503, {"status": "fail"})
            for path in postdeploy.UNAVAILABLE_READINESS_PATHS
        },
        **{
            path: Response(
                503,
                postdeploy.PROBLEM,
                private=True,
                content_type="application/problem+json; charset=utf-8",
            )
            for path in postdeploy.PRIVATE_PATHS
        },
        **{
            path: Response(
                409,
                {
                    "message": "Install handoff is withheld.",
                    "status": "review_required",
                    "releaseTruth": control_release_truth(),
                },
                private=True,
                content_type="application/json; charset=utf-8",
            )
            for path in postdeploy.INSTALL_ROUTE_DENIAL_PATHS
        },
    }
    return result


def test_control_plane_accepts_serving_only_and_private_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = responses()
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _session, _base, path, _timeout: fixture[path],
    )
    with postdeploy.anonymous_session() as session:
        result = postdeploy.verify_control_plane(
            session,
            "https://chummer.run",
            1,
        )
    assert result["privateBoundaryStatuses"] == {
        path: 503 for path in postdeploy.PRIVATE_PATHS
    }
    assert result["installRouteDenialStatuses"] == {
        path: 409 for path in postdeploy.INSTALL_ROUTE_DENIAL_PATHS
    }
    assert result["installRouteReleaseTruthSha256"] == (
        postdeploy._canonical_object_sha256(control_release_truth())
    )


def test_control_plane_rejects_global_readiness_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = responses()
    fixture["/api/ready"] = Response(200, {"status": "pass"})
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _session, _base, path, _timeout: fixture[path],
    )
    with postdeploy.anonymous_session() as session:
        with pytest.raises(ValueError, match="unexpectedly claimed readiness"):
            postdeploy.verify_control_plane(
                session,
                "https://chummer.run",
                1,
            )


def test_control_plane_rejects_install_route_without_review_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = responses()
    fixture["/downloads/install/public-download-only-probe"] = Response(
        503,
        postdeploy.PROBLEM,
        private=True,
        content_type="application/problem+json; charset=utf-8",
    )
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _session, _base, path, _timeout: fixture[path],
    )
    with postdeploy.anonymous_session() as session:
        with pytest.raises(ValueError, match="review-required install denial"):
            postdeploy.verify_control_plane(
                session,
                "https://chummer.run",
                1,
            )


def test_control_plane_rejects_optimistic_release_truth_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = responses()
    denial = fixture["/downloads/install/public-download-only-probe"]
    denial._payload["releaseTruth"]["stable"] = True
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _session, _base, path, _timeout: fixture[path],
    )

    with postdeploy.anonymous_session() as session:
        with pytest.raises(
            ValueError,
            match="review-required install denial",
        ):
            postdeploy.verify_control_plane(
                session,
                "https://chummer.run",
                1,
            )


def test_control_plane_rejects_private_problem_body_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = responses()
    fixture["/api/v1/install-linking/me"] = Response(
        503,
        {**postdeploy.PROBLEM, "detail": "different"},
        private=True,
        content_type="application/problem+json; charset=utf-8",
    )
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _session, _base, path, _timeout: fixture[path],
    )
    with postdeploy.anonymous_session() as session:
        with pytest.raises(ValueError, match="private 503 boundary"):
            postdeploy.verify_control_plane(
                session,
                "https://chummer.run",
                1,
            )


@pytest.mark.parametrize(
    ("path", "content_type", "message"),
    (
        (
            "/api/v1/install-linking/me",
            "application/problem+jsonx",
            "private 503 boundary",
        ),
        (
            "/downloads/install/public-download-only-probe",
            "application/jsonp",
            "review-required install denial",
        ),
    ),
)
def test_control_plane_rejects_mime_suffix_drift(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    content_type: str,
    message: str,
) -> None:
    fixture = responses()
    fixture[path].headers["Content-Type"] = content_type
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _session, _base, request_path, _timeout: fixture[request_path],
    )
    with postdeploy.anonymous_session() as session:
        with pytest.raises(ValueError, match=message):
            postdeploy.verify_control_plane(
                session,
                "https://chummer.run",
                1,
            )


def test_anonymous_get_is_redirect_free_and_carries_no_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sentinel = object()
    captured: dict[str, object] = {}
    netrc = tmp_path / "ambient.netrc"
    netrc.write_text(
        "machine chummer.run login ambient password credential\n",
        encoding="utf-8",
    )
    netrc.chmod(0o600)
    monkeypatch.setenv("NETRC", str(netrc))
    monkeypatch.setenv(
        "HTTPS_PROXY",
        "http://ambient:credential@proxy.invalid:8443",
    )
    monkeypatch.setenv(
        "REQUESTS_CA_BUNDLE",
        str(tmp_path / "ambient-ca.pem"),
    )

    def fake_send(request: object, **kwargs: object) -> object:
        captured["request"] = request
        captured.update(kwargs)
        return sentinel

    session = postdeploy.anonymous_session()
    assert session.trust_env is False
    monkeypatch.setattr(session, "send", fake_send)
    assert (
        postdeploy.anonymous_get(
            session,
            "https://chummer.run/downloads/a",
            2,
            stream=True,
        )
        is sentinel
    )
    assert captured["allow_redirects"] is False
    assert captured["stream"] is True
    assert captured["proxies"] == {}
    assert captured["verify"] is True
    request = captured["request"]
    headers = request.headers
    assert headers["Accept-Encoding"] == "identity"
    assert "Authorization" not in headers
    assert "Proxy-Authorization" not in headers
    assert "Cookie" not in headers
    session.close()


def _exact_incumbent_bootstrap(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, StreamResponse]]:
    incumbent_rows = [
        {
            "artifactId": "avalonia-osx-arm64-installer",
            "platform": "macos",
            "rid": "osx-arm64",
            "kind": "installer",
            "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
            "sha256": "e5d6f7feb0ae1297dfe7dceae1a3d49078134861f475099688eb8cc8979bb006",
            "sizeBytes": 53916415,
        },
        {
            "artifactId": "blazor-desktop-osx-arm64-installer",
            "platform": "macos",
            "rid": "osx-arm64",
            "kind": "installer",
            "fileName": "chummer-blazor-desktop-osx-arm64-installer.dmg",
            "sha256": "68dd1a5ba76c2b927f9eb56d43a9c3c855144158d29c48a34f8567624b781c9a",
            "sizeBytes": 51884585,
        },
        {
            "artifactId": "avalonia-osx-arm64-archive",
            "platform": "macos",
            "rid": "osx-arm64",
            "kind": "archive",
            "fileName": "chummer-avalonia-osx-arm64.tar.gz",
            "sha256": "ccd2c28045d1d4a57678f9ed24aafe9e39f3f5e5e82d6749c40fe1828d47e54a",
            "sizeBytes": 47387641,
        },
        {
            "artifactId": "blazor-desktop-osx-arm64-archive",
            "platform": "macos",
            "rid": "osx-arm64",
            "kind": "archive",
            "fileName": "chummer-blazor-desktop-osx-arm64.tar.gz",
            "sha256": "6b6ea64dbb05dfb8b99cb6c9ec859d98d7493a8d9a79e75d1ffd26e8e8004fdf",
            "sizeBytes": 45382391,
        },
    ]
    canonical = {
        "version": "run-20260715-140426",
        "artifacts": incumbent_rows,
    }
    compatibility = {
        "version": "run-20260715-140426",
        "downloads": [
            {
                **row,
                "id": row["artifactId"],
            }
            for row in incumbent_rows
        ],
    }
    canonical_bytes = DeliveryFixture.json_bytes(canonical)
    compatibility_bytes = DeliveryFixture.json_bytes(compatibility)
    assert canonical["version"] == "run-20260715-140426"
    assert compatibility["version"] == "run-20260715-140426"
    assert (
        postdeploy._windows_bootstrap_rows(
            canonical,
            key="artifacts",
            label="exact incumbent canonical manifest",
        )
        == []
    )
    assert (
        postdeploy._windows_bootstrap_rows(
            compatibility,
            key="downloads",
            label="exact incumbent compatibility manifest",
        )
        == []
    )
    bundle = tmp_path / "exact-incumbent"
    bundle.mkdir(parents=True)
    local_canonical = bundle / "RELEASE_CHANNEL.generated.json"
    local_manifest = bundle / "releases.json"
    local_canonical.write_bytes(canonical_bytes)
    local_manifest.write_bytes(compatibility_bytes)
    generation = "legacy-migration-generation"
    base = "https://chummer.run/downloads"
    return (
        local_manifest,
        local_canonical,
        {
            f"{base}/RELEASE_CHANNEL.generated.json": StreamResponse(
                f"{base}/RELEASE_CHANNEL.generated.json",
                canonical_bytes,
                generation=generation,
            ),
            f"{base}/releases.json": StreamResponse(
                f"{base}/releases.json",
                compatibility_bytes,
                generation=generation,
            ),
        },
    )


def test_bootstrap_phase_accepts_exact_no_windows_incumbent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_manifest, local_canonical, responses_by_url = (
        _exact_incumbent_bootstrap(tmp_path)
    )
    calls: list[str] = []

    def fake_get(
        _session: object,
        url: str,
        _timeout: float,
        *,
        stream: bool,
    ) -> StreamResponse:
        assert stream is True
        calls.append(url)
        return responses_by_url[url]

    monkeypatch.setattr(postdeploy, "anonymous_get", fake_get)
    with postdeploy.anonymous_session() as session:
        result = postdeploy.verify_public_download_delivery(
            session=session,
            delivery_phase=postdeploy.DELIVERY_PHASE_BOOTSTRAP,
            base_url="https://chummer.run",
            local_manifest_path=local_manifest,
            local_canonical_manifest_path=local_canonical,
            timeout=1,
        )

    assert result["deliveryPhase"] == "bootstrap"
    assert result["expectedWindowsState"] == "absent"
    assert result["windowsDeliveryClaimed"] is False
    assert result["artifacts"] == []
    assert result["canonicalManifest"]["generationId"] == (
        result["compatibilityManifest"]["generationId"]
    )
    assert calls == [
        "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json",
        "https://chummer.run/downloads/releases.json",
    ]


def test_delivery_phases_reject_manifest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = DeliveryFixture(tmp_path / "windows")
    windows.install(monkeypatch)
    with postdeploy.anonymous_session() as session:
        with pytest.raises(ValueError, match="requires zero Windows"):
            postdeploy.verify_public_download_delivery(
                session=session,
                delivery_phase=postdeploy.DELIVERY_PHASE_BOOTSTRAP,
                base_url=windows.base_url,
                local_manifest_path=windows.local_manifest,
                local_canonical_manifest_path=windows.local_canonical,
                timeout=1,
            )

    local_manifest, local_canonical, _responses = _exact_incumbent_bootstrap(
        tmp_path / "incumbent"
    )
    with postdeploy.anonymous_session() as session:
        with pytest.raises(
            ValueError,
            match="no Windows bootstrap installer",
        ):
            postdeploy.verify_public_download_delivery(
                session=session,
                delivery_phase=postdeploy.DELIVERY_PHASE_WINDOWS_PREVIEW,
                base_url="https://chummer.run",
                local_manifest_path=local_manifest,
                local_canonical_manifest_path=local_canonical,
                timeout=1,
            )


def test_cli_requires_explicit_delivery_phase(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        postdeploy.main(
            [
                "--base-url",
                "https://chummer.run",
                "--source-root",
                str(ROOT),
                "--local-manifest",
                str(tmp_path / "releases.json"),
                "--local-canonical-manifest",
                str(tmp_path / "canonical.json"),
                "--output",
                str(tmp_path / "receipt.json"),
            ]
        )
    assert raised.value.code == 2


def test_strict_delivery_accepts_exact_anonymous_gets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    calls = fixture.install(monkeypatch)

    result = fixture.verify()

    assert result["status"] == "pass"
    assert result["generationId"] == fixture.generation
    assert (
        fixture.canonical["registryCommit"]
        != fixture.release_truth["registryCommit"]
    )
    assert result["generationHeader"] == postdeploy.GENERATION_HEADER
    assert result["releaseTruthSha256"] == (
        postdeploy._canonical_object_sha256(fixture.release_truth)
    )
    assert [url for url, _ in calls] == [
        fixture.canonical_url,
        fixture.compatibility_url,
        fixture.installer_url,
        fixture.payload_url,
        fixture.sidecar_url,
    ]
    assert all(stream for _, stream in calls)
    artifact = result["artifacts"][0]
    assert artifact["policy"]["stable"] is False
    assert artifact["policy"]["update"] is False
    assert artifact["embeddedInstallerMetadataAgrees"] is True


def test_strict_delivery_accepts_sealed_legacy_rows_with_release_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    for key in ("artifactByteVisibility", "previewPolicy", "signature"):
        fixture.artifact.pop(key)
        fixture.compatibility["downloads"][0].pop(key, None)
    for key in ("routeAuthority", "publicationState", "visibility"):
        fixture.route.pop(key)
    fixture.route.update(
        {
            "promotionState": "promoted",
            "updateEligibility": "eligible",
            "publicInstallRoute": (
                f"/downloads/install/{fixture.artifact_id}"
            ),
        }
    )
    fixture.rewrite()
    fixture.install(monkeypatch)

    result = fixture.verify()

    assert result["status"] == "pass"
    assert result["artifacts"][0]["policy"]["stable"] is False
    assert result["artifacts"][0]["policy"]["update"] is False


def test_strict_delivery_rejects_legacy_install_route_for_other_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    for key in ("artifactByteVisibility", "previewPolicy", "signature"):
        fixture.artifact.pop(key)
        fixture.compatibility["downloads"][0].pop(key, None)
    for key in ("routeAuthority", "publicationState", "visibility"):
        fixture.route.pop(key)
    fixture.route.update(
        {
            "promotionState": "promoted",
            "updateEligibility": "eligible",
            "publicInstallRoute": "/downloads/install/unrelated-artifact",
        }
    )
    fixture.rewrite()
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="legacy route truth shape"):
        fixture.verify()


def test_strict_delivery_uses_sidecar_raw_url_for_semantic_manifest_payload_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path, semantic_payload_route=True)
    calls = fixture.install(monkeypatch)

    result = fixture.verify()

    requested_urls = [url for url, _stream in calls]
    assert result["status"] == "pass"
    assert fixture.manifest_payload_url != fixture.payload_url
    assert fixture.payload_url in requested_urls
    assert fixture.manifest_payload_url not in requested_urls


def test_www_delivery_accepts_canonical_apex_sidecar_url(
    tmp_path: Path,
) -> None:
    fixture = DeliveryFixture(
        tmp_path,
        semantic_payload_route=True,
    )

    _canonical, _generation, expectations = (
        postdeploy.derive_download_expectations(
            base_url="https://www.chummer.run",
            local_manifest_path=fixture.local_manifest,
            local_canonical_manifest_path=fixture.local_canonical,
        )
    )

    assert expectations[0].payload_url == fixture.payload_url
    assert expectations[0].payload_probe_url == (
        "https://www.chummer.run/downloads/files/"
        f"{fixture.payload_name}"
    )
    assert expectations[0].sidecar_probe_url == (
        "https://www.chummer.run/downloads/files/"
        f"{fixture.payload_name}.json"
    )


def test_strict_delivery_accepts_generation_scoped_sidecar_and_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(
        tmp_path,
        semantic_payload_route=True,
    )
    generation_root = (
        fixture.root / "generations" / fixture.generation
    )
    generation_files = generation_root / "files"
    generation_evidence = generation_root / "release-evidence"
    generation_files.mkdir(parents=True)
    generation_evidence.mkdir()
    (fixture.files / f"{fixture.payload_name}.json").replace(
        generation_files / f"{fixture.payload_name}.json"
    )
    for name in ("CURRENT.json", "SNAPSHOT.json", "RELEASE_DECISION.json"):
        (fixture.evidence_root / name).replace(
            generation_evidence / name
        )
    fixture.install(monkeypatch)

    assert fixture.verify()["status"] == "pass"


def test_strict_delivery_rejects_disagreeing_sidecar_copies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    generation_files = (
        fixture.root
        / "generations"
        / fixture.generation
        / "files"
    )
    generation_files.mkdir(parents=True)
    (
        generation_files / f"{fixture.payload_name}.json"
    ).write_bytes(b"{}\n")
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="sidecar copies disagree"):
        fixture.verify()


def test_strict_delivery_rejects_disagreeing_release_evidence_copies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    generation_evidence = (
        fixture.root
        / "generations"
        / fixture.generation
        / "release-evidence"
    )
    generation_evidence.mkdir(parents=True)
    for name in ("CURRENT.json", "SNAPSHOT.json", "RELEASE_DECISION.json"):
        (generation_evidence / name).write_bytes(
            (fixture.evidence_root / name).read_bytes()
        )
    with (generation_evidence / "CURRENT.json").open("ab") as handle:
        handle.write(b" ")
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="evidence copies disagree"):
        fixture.verify()


def test_strict_delivery_rejects_mutated_release_evidence_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    with (fixture.evidence_root / "RELEASE_DECISION.json").open(
        "ab"
    ) as handle:
        handle.write(b" ")
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="CURRENT.json is not closed"):
        fixture.verify()


@pytest.mark.parametrize(
    "field",
    (
        "registryCommit",
        "releaseDecisionSha256",
        "releaseScopeDecisionSha256",
    ),
)
def test_strict_delivery_rejects_release_truth_authority_not_in_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    replacement = "e" * (40 if field == "registryCommit" else 64)
    for url in (fixture.canonical_url, fixture.compatibility_url):
        payload = json.loads(fixture.responses[url].body.decode("utf-8"))
        payload["releaseTruth"][field] = replacement
        if field == "releaseScopeDecisionSha256":
            payload["releaseTruth"]["artifactHandoff"][field] = replacement
        fixture.responses[url] = StreamResponse(
            url,
            fixture.json_bytes(payload),
            generation=fixture.generation,
        )
    fixture.install(monkeypatch)

    with pytest.raises(
        ValueError,
        match="expected review-required authority",
    ):
        fixture.verify()


def test_strict_delivery_rejects_optimistic_release_truth_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    for url in (fixture.canonical_url, fixture.compatibility_url):
        payload = json.loads(fixture.responses[url].body.decode("utf-8"))
        payload["releaseTruth"]["stable"] = True
        fixture.responses[url] = StreamResponse(
            url,
            fixture.json_bytes(payload),
            generation=fixture.generation,
        )
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="unexpected authority schema"):
        fixture.verify()


def test_sidecar_lookup_rejects_unsafe_generation_segment(
    tmp_path: Path,
) -> None:
    fixture = DeliveryFixture(tmp_path)

    with pytest.raises(ValueError, match="safe path segment"):
        postdeploy._find_sidecar_bytes(
            fixture.local_manifest,
            fixture.local_canonical,
            f"{fixture.payload_name}.json",
            "../generation-a",
        )


def test_strict_delivery_rejects_cross_generation_semantic_payload_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path, semantic_payload_route=True)
    drifted = fixture.manifest_payload_url.replace(
        fixture.generation,
        "generation-b",
    )
    fixture.artifact["payloadDownloadUrl"] = drifted.removeprefix(
        fixture.base_url
    )
    fixture.compatibility["downloads"][0]["payloadDownloadUrl"] = (
        drifted.removeprefix(fixture.base_url)
    )
    fixture.rewrite()
    fixture.install(monkeypatch)

    with pytest.raises(
        ValueError,
        match="not filename- or generation-bound",
    ):
        fixture.verify()


def test_strict_delivery_rejects_release_truth_signing_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    payload = json.loads(
        fixture.responses[fixture.canonical_url].body.decode("utf-8")
    )
    payload["releaseTruth"]["artifactHandoff"]["signingRequirement"] = (
        "stable_signature_required"
    )
    fixture.responses[fixture.canonical_url] = StreamResponse(
        fixture.canonical_url,
        fixture.json_bytes(payload),
        generation=fixture.generation,
    )
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="artifact handoff disagrees"):
        fixture.verify()


def test_strict_delivery_rejects_redirect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    fixture.responses[fixture.installer_url] = StreamResponse(
        fixture.installer_url,
        b"",
        status=302,
        headers={"Location": "https://example.invalid/installer.exe"},
    )
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="expected HTTP 200, got 302"):
        fixture.verify()


@pytest.mark.parametrize(
    "artifact",
    ("installer", "payload", "sidecar"),
)
def test_strict_delivery_rejects_same_size_corruption_for_every_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact: str,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    target_url = {
        "installer": fixture.installer_url,
        "payload": fixture.payload_url,
        "sidecar": fixture.sidecar_url,
    }[artifact]
    original = fixture.responses[target_url].body
    corrupted = bytes([original[0] ^ 1]) + original[1:]
    fixture.responses[target_url] = StreamResponse(
        target_url,
        corrupted,
        generation=fixture.generation,
    )
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="streamed sha256"):
        fixture.verify()


@pytest.mark.parametrize("mode", ["absent", "mismatched"])
def test_strict_delivery_rejects_absent_or_mismatched_content_length(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    response = fixture.responses[fixture.payload_url]
    if mode == "absent":
        response.headers.pop("Content-Length")
        expected = "missing Content-Length"
    else:
        response.headers["Content-Length"] = str(len(fixture.payload_bytes) + 1)
        expected = "does not match expected"
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match=expected):
        fixture.verify()


@pytest.mark.parametrize(
    "header,value",
    [
        ("Set-Cookie", "session=secret"),
        ("Authorization", "Bearer leaked"),
        ("WWW-Authenticate", 'Bearer realm="private"'),
        ("Location", "https://example.invalid/elsewhere"),
    ],
)
@pytest.mark.parametrize(
    "artifact",
    ("installer", "payload", "sidecar"),
)
def test_strict_delivery_rejects_cookie_auth_or_location_headers_for_every_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    header: str,
    value: str,
    artifact: str,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    target_url = {
        "installer": fixture.installer_url,
        "payload": fixture.payload_url,
        "sidecar": fixture.sidecar_url,
    }[artifact]
    fixture.responses[target_url].headers[header] = value
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match=f"forbidden response header {header}"):
        fixture.verify()


@pytest.mark.parametrize(
    "header,value",
    [
        ("Authorization", "Bearer ambient"),
        ("Cookie", "session=ambient"),
        ("Proxy-Authorization", "Basic ambient"),
    ],
)
@pytest.mark.parametrize(
    "artifact",
    ("installer", "payload", "sidecar"),
)
def test_strict_delivery_rejects_request_credentials_for_every_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    header: str,
    value: str,
    artifact: str,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    target_url = {
        "installer": fixture.installer_url,
        "payload": fixture.payload_url,
        "sidecar": fixture.sidecar_url,
    }[artifact]
    fixture.responses[target_url].request.headers[header] = value
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match=f"request carried credential header {header}"):
        fixture.verify()


def test_strict_delivery_rejects_credential_bearing_manifest_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    fixture.artifact["payloadDownloadUrl"] = (
        f"/downloads/files/{fixture.payload_name}?token=secret"
    )
    fixture.rewrite()
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="credential-free"):
        fixture.verify()


def test_strict_delivery_rejects_sidecar_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    fixture.sidecar["releaseVersion"] = "run-evil"
    fixture.rewrite()
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="sidecar releaseVersion"):
        fixture.verify()


def test_strict_delivery_rejects_generation_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    fixture.responses[fixture.sidecar_url].headers[
        postdeploy.GENERATION_HEADER
    ] = "generation-b"
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="generation 'generation-b'"):
        fixture.verify()


def test_strict_delivery_rejects_compressed_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    fixture.responses[fixture.payload_url].headers["Content-Encoding"] = "gzip"
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="unexpected Content-Encoding"):
        fixture.verify()


def test_strict_delivery_rejects_embedded_installer_metadata_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path, embed_metadata=False)
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="missing embedded"):
        fixture.verify()


def test_strict_delivery_rejects_stable_route_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    fixture.route["routeAuthority"] = True
    fixture.rewrite()
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match="stable/install authority"):
        fixture.verify()
