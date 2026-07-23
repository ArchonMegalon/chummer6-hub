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
    ) -> None:
        self.status_code = status
        self._payload = payload
        self.headers = {"Content-Type": "application/json"}
        if private:
            self.headers = {
                "Content-Type": "application/problem+json; charset=utf-8",
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
    def __init__(self, tmp_path: Path, *, embed_metadata: bool = True) -> None:
        self.base_url = "https://chummer.run"
        self.generation = "generation-a"
        self.version = "run-test"
        self.artifact_id = "avalonia-win-x64-installer"
        self.installer_name = "chummer-avalonia-win-x64-installer.exe"
        self.payload_name = "chummer-avalonia-win-x64-payload.zip"
        self.installer_url = f"{self.base_url}/downloads/files/{self.installer_name}"
        self.payload_url = f"{self.base_url}/downloads/files/{self.payload_name}"
        self.sidecar_url = self.payload_url + ".json"
        self.canonical_url = (
            f"{self.base_url}/downloads/RELEASE_CHANNEL.generated.json"
        )
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
            "payloadDownloadUrl": f"/downloads/files/{self.payload_name}",
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
        self.local_canonical.write_bytes(canonical_bytes)
        self.local_manifest.write_bytes(manifest_bytes)
        (self.files / f"{self.payload_name}.json").write_bytes(sidecar_bytes)
        self.responses = {
            self.canonical_url: StreamResponse(
                self.canonical_url,
                canonical_bytes,
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

        def fake_get(url: str, timeout: float, *, stream: bool) -> StreamResponse:
            assert timeout == 1
            calls.append((url, stream))
            return self.responses[url]

        monkeypatch.setattr(postdeploy, "anonymous_get", fake_get)
        return calls

    def verify(self) -> dict[str, object]:
        return postdeploy.verify_public_download_delivery(
            base_url=self.base_url,
            local_manifest_path=self.local_manifest,
            local_canonical_manifest_path=self.local_canonical,
            timeout=1,
        )


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
            path: Response(503, postdeploy.PROBLEM, private=True)
            for path in postdeploy.PRIVATE_PATHS
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
        lambda _base, path, _timeout: fixture[path],
    )
    result = postdeploy.verify_control_plane("https://chummer.run", 1)
    assert result["privateBoundaryStatuses"] == {
        path: 503 for path in postdeploy.PRIVATE_PATHS
    }


def test_control_plane_rejects_global_readiness_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = responses()
    fixture["/api/ready"] = Response(200, {"status": "pass"})
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _base, path, _timeout: fixture[path],
    )
    with pytest.raises(ValueError, match="unexpectedly claimed readiness"):
        postdeploy.verify_control_plane("https://chummer.run", 1)


def test_control_plane_rejects_private_problem_body_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = responses()
    fixture["/api/v1/install-linking/me"] = Response(
        503,
        {**postdeploy.PROBLEM, "detail": "different"},
        private=True,
    )
    monkeypatch.setattr(
        postdeploy,
        "get",
        lambda _base, path, _timeout: fixture[path],
    )
    with pytest.raises(ValueError, match="private 503 boundary"):
        postdeploy.verify_control_plane("https://chummer.run", 1)


def test_anonymous_get_is_redirect_free_and_carries_no_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    captured: dict[str, object] = {}

    def fake_requests_get(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(postdeploy.requests, "get", fake_requests_get)
    assert postdeploy.anonymous_get("https://chummer.run/downloads/a", 2, stream=True) is sentinel
    assert captured["allow_redirects"] is False
    assert captured["stream"] is True
    assert captured["cookies"] == {}
    assert isinstance(captured["auth"], postdeploy.AnonymousAuth)
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Accept-Encoding"] == "identity"
    assert "Authorization" not in headers
    assert "Cookie" not in headers


def test_strict_delivery_accepts_exact_anonymous_gets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    calls = fixture.install(monkeypatch)

    result = fixture.verify()

    assert result["status"] == "pass"
    assert result["generationId"] == fixture.generation
    assert result["generationHeader"] == postdeploy.GENERATION_HEADER
    assert [url for url, _ in calls] == [
        fixture.canonical_url,
        fixture.installer_url,
        fixture.payload_url,
        fixture.sidecar_url,
    ]
    assert all(stream for _, stream in calls)
    artifact = result["artifacts"][0]
    assert artifact["policy"]["stable"] is False
    assert artifact["policy"]["update"] is False
    assert artifact["embeddedInstallerMetadataAgrees"] is True


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


def test_strict_delivery_rejects_same_size_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    corrupted = bytes([fixture.payload_bytes[0] ^ 1]) + fixture.payload_bytes[1:]
    fixture.responses[fixture.payload_url] = StreamResponse(
        fixture.payload_url,
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
def test_strict_delivery_rejects_cookie_auth_or_location_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    header: str,
    value: str,
) -> None:
    fixture = DeliveryFixture(tmp_path)
    fixture.responses[fixture.installer_url].headers[header] = value
    fixture.install(monkeypatch)

    with pytest.raises(ValueError, match=f"forbidden response header {header}"):
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
