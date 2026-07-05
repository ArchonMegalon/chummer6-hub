from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "public_download_shelf_truth_gate.py"
SPEC = importlib.util.spec_from_file_location("public_download_shelf_truth_gate", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        status_code: int = 200,
        text: str = "",
        json_payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.text = text
        self._json_payload = json_payload
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        if self._json_payload is None:
            raise ValueError("missing json payload")
        return self._json_payload

    def close(self) -> None:
        return None


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def make_releases_manifest() -> dict:
    return {
        "version": "run-20260627-101500",
        "publicVersion": "0.0.0.1",
        "channel": "public_stable",
        "rolloutState": "public_stable",
        "supportabilityState": "gold_supported",
        "publishedAt": "2026-06-27T10:15:00+00:00",
        "status": "published",
        "downloads": [
            {
                "id": "avalonia-linux-x64-installer",
                "artifactId": "avalonia-linux-x64-installer",
                "fileName": "chummer-avalonia-linux-x64-installer.deb",
                "url": "https://chummer.run/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                "sha256": "a" * 64,
                "sizeBytes": 1234,
                "head": "avalonia",
                "platformId": "linux",
                "arch": "x64",
                "channel": "public_stable",
                "channelId": "public_stable",
                "installAccessClass": "open_public",
                "installerMode": "embedded",
                "kind": "installer",
            }
        ],
    }


def make_canonical_manifest() -> dict:
    return {
        "version": "run-20260627-101500",
        "publicVersion": "0.0.0.1",
        "channel": "public_stable",
        "channelId": "public_stable",
        "rolloutState": "public_stable",
        "supportabilityState": "gold_supported",
        "publishedAt": "2026-06-27T10:15:00Z",
        "status": "published",
        "artifacts": [
            {
                "id": "avalonia-linux-x64-installer",
                "artifactId": "avalonia-linux-x64-installer",
                "fileName": "chummer-avalonia-linux-x64-installer.deb",
                "downloadUrl": "https://chummer.run/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                "sha256": "a" * 64,
                "sizeBytes": 1234,
                "head": "avalonia",
                "rid": "linux-x64",
                "channel": "public_stable",
                "channelId": "public_stable",
                "installAccessClass": "open_public",
                "installerMode": "embedded",
                "kind": "installer",
            }
        ],
    }


def clone_payload(payload: dict) -> dict:
    return json.loads(json.dumps(payload))


def add_windows_bootstrap_artifact(
    *,
    releases_payload: dict,
    canonical_payload: dict,
) -> tuple[dict, dict]:
    releases_payload = json.loads(json.dumps(releases_payload))
    canonical_payload = json.loads(json.dumps(canonical_payload))
    releases_payload["downloads"].append(
        {
            "id": "avalonia-win-x64-installer",
            "artifactId": "avalonia-win-x64-installer",
            "fileName": "chummer-avalonia-win-x64-installer.exe",
            "url": "https://chummer.run/downloads/files/chummer-avalonia-win-x64-installer.exe",
            "sha256": "b" * 64,
            "sizeBytes": 5678,
            "head": "avalonia",
            "platformId": "windows",
            "arch": "x64",
            "channel": "public_stable",
            "channelId": "public_stable",
            "installAccessClass": "open_public",
            "installerMode": "bootstrap",
            "kind": "installer",
            "payloadFileName": "chummer-avalonia-win-x64-payload.zip",
            "payloadDownloadUrl": "https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip",
            "payloadSha256": "c" * 64,
            "payloadSizeBytes": 87654,
        }
    )
    canonical_payload["artifacts"].append(
        {
            "id": "avalonia-win-x64-installer",
            "artifactId": "avalonia-win-x64-installer",
            "fileName": "chummer-avalonia-win-x64-installer.exe",
            "downloadUrl": "https://chummer.run/downloads/files/chummer-avalonia-win-x64-installer.exe",
            "sha256": "b" * 64,
            "sizeBytes": 5678,
            "head": "avalonia",
            "rid": "win-x64",
            "channel": "public_stable",
            "channelId": "public_stable",
            "installAccessClass": "open_public",
            "installerMode": "bootstrap",
            "kind": "installer",
            "payloadFileName": "chummer-avalonia-win-x64-payload.zip",
            "payloadDownloadUrl": "https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip",
            "payloadSha256": "c" * 64,
            "payloadSizeBytes": 87654,
        }
    )
    return releases_payload, canonical_payload


class PublicDownloadShelfTruthGateTests(unittest.TestCase):
    def test_rid_from_row_derives_windows_and_linux_runtime_ids(self) -> None:
        self.assertEqual(
            MODULE.rid_from_row({"platformId": "windows", "arch": "x64"}),
            "win-x64",
        )
        self.assertEqual(
            MODULE.rid_from_row({"platformId": "windows-x64"}),
            "win-x64",
        )
        self.assertEqual(
            MODULE.rid_from_row({"platformId": "linux", "arch": "arm64"}),
            "linux-arm64",
        )
        self.assertEqual(
            MODULE.rid_from_row({"platformId": "macos-arm64"}),
            "osx-arm64",
        )
        self.assertEqual(
            MODULE.rid_from_row({"platformId": "macos", "arch": "x64"}),
            "osx-x64",
        )

    def test_matching_local_and_live_bundle_truth_passes(self) -> None:
        releases_payload = make_releases_manifest()
        canonical_payload = make_canonical_manifest()

        with tempfile.TemporaryDirectory(prefix="download-shelf-truth-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            write_json(local_manifest, releases_payload)
            write_json(local_canonical, canonical_payload)

            def fake_get(url: str, *args, **kwargs) -> FakeResponse:
                if url == "https://chummer.run/downloads":
                    return FakeResponse(
                        url=url,
                        text='<a data-download-artifact="avalonia-linux-x64-installer" href="/downloads/get/avalonia-linux-x64-installer">Download</a>',
                    )
                if url == "https://chummer.run/downloads/releases.json":
                    return FakeResponse(url=url, json_payload=releases_payload)
                if url == "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json":
                    return FakeResponse(url=url, json_payload=canonical_payload)
                raise AssertionError(f"unexpected GET {url}")

            def fake_head(url: str, *args, **kwargs) -> FakeResponse:
                self.assertEqual(
                    url,
                    "https://chummer.run/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                )
                return FakeResponse(
                    url=url,
                    status_code=200,
                    headers={"Content-Length": "1234"},
                )

            with mock.patch.object(MODULE.requests, "get", side_effect=fake_get), mock.patch.object(
                MODULE.requests,
                "head",
                side_effect=fake_head,
            ):
                receipt = MODULE.evaluate(
                    base_url="https://chummer.run",
                    local_manifest_path=local_manifest,
                    local_canonical_manifest_path=local_canonical,
                    timeout=5.0,
                    artifact_probes_enabled=True,
                )

        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(receipt["live"]["pageArtifactIds"], ["avalonia-linux-x64-installer"])
        self.assertEqual(len(receipt["live"]["artifactProbes"]), 1)

    def test_matching_local_and_live_bundle_truth_passes_for_linux_and_windows_public_installers(self) -> None:
        releases_payload, canonical_payload = add_windows_bootstrap_artifact(
            releases_payload=make_releases_manifest(),
            canonical_payload=make_canonical_manifest(),
        )

        with tempfile.TemporaryDirectory(prefix="download-shelf-truth-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            write_json(local_manifest, releases_payload)
            write_json(local_canonical, canonical_payload)

            def fake_get(url: str, *args, **kwargs) -> FakeResponse:
                if url == "https://chummer.run/downloads":
                    return FakeResponse(
                        url=url,
                        text=(
                            '<a data-download-artifact="avalonia-win-x64-installer" href="/downloads/get/avalonia-win-x64-installer">Windows</a>'
                            '<a data-download-artifact="avalonia-linux-x64-installer" href="/downloads/get/avalonia-linux-x64-installer">Linux</a>'
                        ),
                    )
                if url == "https://chummer.run/downloads/releases.json":
                    return FakeResponse(url=url, json_payload=releases_payload)
                if url == "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json":
                    return FakeResponse(url=url, json_payload=canonical_payload)
                raise AssertionError(f"unexpected GET {url}")

            def fake_head(url: str, *args, **kwargs) -> FakeResponse:
                expected_sizes = {
                    "https://chummer.run/downloads/files/chummer-avalonia-linux-x64-installer.deb": "1234",
                    "https://chummer.run/downloads/files/chummer-avalonia-win-x64-installer.exe": "5678",
                    "https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip": "87654",
                }
                self.assertIn(url, expected_sizes)
                return FakeResponse(
                    url=url,
                    status_code=200,
                    headers={"Content-Length": expected_sizes[url]},
                )

            with mock.patch.object(MODULE.requests, "get", side_effect=fake_get), mock.patch.object(
                MODULE.requests,
                "head",
                side_effect=fake_head,
            ):
                receipt = MODULE.evaluate(
                    base_url="https://chummer.run",
                    local_manifest_path=local_manifest,
                    local_canonical_manifest_path=local_canonical,
                    timeout=5.0,
                    artifact_probes_enabled=True,
                )

        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(
            receipt["live"]["pageArtifactIds"],
            ["avalonia-win-x64-installer", "avalonia-linux-x64-installer"],
        )
        self.assertEqual(
            receipt["live"]["publicArtifactIds"],
            ["avalonia-linux-x64-installer", "avalonia-win-x64-installer"],
        )
        self.assertEqual(len(receipt["live"]["artifactProbes"]), 3)
        self.assertTrue(receipt["alignment"]["artifactProbesPassed"])

    def test_transient_downloads_502_retries_and_passes(self) -> None:
        releases_payload = make_releases_manifest()
        canonical_payload = make_canonical_manifest()

        with tempfile.TemporaryDirectory(prefix="download-shelf-truth-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            write_json(local_manifest, releases_payload)
            write_json(local_canonical, canonical_payload)
            call_count = {"downloads": 0}

            def fake_get(url: str, *args, **kwargs) -> FakeResponse:
                if url == "https://chummer.run/downloads":
                    call_count["downloads"] += 1
                    if call_count["downloads"] == 1:
                        return FakeResponse(url=url, status_code=502)
                    return FakeResponse(
                        url=url,
                        text='<a data-download-artifact="avalonia-linux-x64-installer" href="/downloads/get/avalonia-linux-x64-installer">Download</a>',
                    )
                if url == "https://chummer.run/downloads/releases.json":
                    return FakeResponse(url=url, json_payload=releases_payload)
                if url == "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json":
                    return FakeResponse(url=url, json_payload=canonical_payload)
                raise AssertionError(f"unexpected GET {url}")

            with mock.patch.object(MODULE.requests, "get", side_effect=fake_get), mock.patch.object(
                MODULE.time,
                "sleep",
                return_value=None,
            ):
                receipt = MODULE.evaluate(
                    base_url="https://chummer.run",
                    local_manifest_path=local_manifest,
                    local_canonical_manifest_path=local_canonical,
                    timeout=5.0,
                    artifact_probes_enabled=False,
                )

        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(call_count["downloads"], 2)

    def test_live_confirmation_requires_consecutive_matching_samples(self) -> None:
        releases_payload = make_releases_manifest()
        canonical_payload = make_canonical_manifest()
        old_releases_payload = clone_payload(releases_payload)
        old_canonical_payload = clone_payload(canonical_payload)
        old_releases_payload["version"] = "run-20260704-170602"
        old_releases_payload["publishedAt"] = "2026-07-04T17:48:20+00:00"
        old_canonical_payload["version"] = "run-20260704-170602"
        old_canonical_payload["publishedAt"] = "2026-07-04T17:48:20Z"

        with tempfile.TemporaryDirectory(prefix="download-shelf-truth-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            write_json(local_manifest, releases_payload)
            write_json(local_canonical, canonical_payload)
            live_call_counts = {"releases": 0, "canonical": 0}

            def fake_get(url: str, *args, **kwargs) -> FakeResponse:
                normalized_url = url.split("?", 1)[0]
                if normalized_url == "https://chummer.run/downloads":
                    return FakeResponse(
                        url=url,
                        text='<a data-download-artifact="avalonia-linux-x64-installer" href="/downloads/get/avalonia-linux-x64-installer">Download</a>',
                    )
                if normalized_url == "https://chummer.run/downloads/releases.json":
                    live_call_counts["releases"] += 1
                    payload = old_releases_payload if live_call_counts["releases"] == 1 else releases_payload
                    return FakeResponse(url=url, json_payload=payload)
                if normalized_url == "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json":
                    live_call_counts["canonical"] += 1
                    payload = old_canonical_payload if live_call_counts["canonical"] == 1 else canonical_payload
                    return FakeResponse(url=url, json_payload=payload)
                raise AssertionError(f"unexpected GET {url}")

            with mock.patch.object(MODULE.requests, "get", side_effect=fake_get):
                receipt = MODULE.evaluate(
                    base_url="https://chummer.run",
                    local_manifest_path=local_manifest,
                    local_canonical_manifest_path=local_canonical,
                    timeout=5.0,
                    artifact_probes_enabled=False,
                    live_confirmation_count=2,
                    live_confirmation_delay_seconds=0.0,
                    live_max_samples=3,
                )

        self.assertEqual(receipt["status"], "pass")
        self.assertTrue(receipt["live"]["confirmation"]["stabilized"])
        self.assertEqual(receipt["live"]["confirmation"]["samplesObserved"], 3)
        self.assertEqual(receipt["live"]["confirmation"]["requiredConsecutiveMatches"], 2)

    def test_live_confirmation_fails_when_public_truth_never_catches_up(self) -> None:
        releases_payload = make_releases_manifest()
        canonical_payload = make_canonical_manifest()
        old_releases_payload = clone_payload(releases_payload)
        old_canonical_payload = clone_payload(canonical_payload)
        old_releases_payload["version"] = "run-20260704-170602"
        old_releases_payload["publishedAt"] = "2026-07-04T17:48:20+00:00"
        old_canonical_payload["version"] = "run-20260704-170602"
        old_canonical_payload["publishedAt"] = "2026-07-04T17:48:20Z"

        with tempfile.TemporaryDirectory(prefix="download-shelf-truth-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            write_json(local_manifest, releases_payload)
            write_json(local_canonical, canonical_payload)

            def fake_get(url: str, *args, **kwargs) -> FakeResponse:
                normalized_url = url.split("?", 1)[0]
                if normalized_url == "https://chummer.run/downloads":
                    return FakeResponse(
                        url=url,
                        text='<a data-download-artifact="avalonia-linux-x64-installer" href="/downloads/get/avalonia-linux-x64-installer">Download</a>',
                    )
                if normalized_url == "https://chummer.run/downloads/releases.json":
                    return FakeResponse(url=url, json_payload=old_releases_payload)
                if normalized_url == "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json":
                    return FakeResponse(url=url, json_payload=old_canonical_payload)
                raise AssertionError(f"unexpected GET {url}")

            with mock.patch.object(MODULE.requests, "get", side_effect=fake_get):
                receipt = MODULE.evaluate(
                    base_url="https://chummer.run",
                    local_manifest_path=local_manifest,
                    local_canonical_manifest_path=local_canonical,
                    timeout=5.0,
                    artifact_probes_enabled=False,
                    live_confirmation_count=2,
                    live_confirmation_delay_seconds=0.0,
                    live_max_samples=3,
                )

        self.assertEqual(receipt["status"], "fail")
        self.assertFalse(receipt["live"]["confirmation"]["stabilized"])
        self.assertTrue(
            any(
                "live shelf never matched local manifests for 2 consecutive sample(s) within 3 sample(s)" in failure
                for failure in receipt["failures"]
            )
        )

    def test_live_page_unknown_artifact_id_fails(self) -> None:
        releases_payload = make_releases_manifest()
        canonical_payload = make_canonical_manifest()

        with tempfile.TemporaryDirectory(prefix="download-shelf-truth-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            write_json(local_manifest, releases_payload)
            write_json(local_canonical, canonical_payload)

            def fake_get(url: str, *args, **kwargs) -> FakeResponse:
                if url == "https://chummer.run/downloads":
                    return FakeResponse(
                        url=url,
                        text='<a data-download-artifact="blazor-win-x64-installer" href="/downloads/get/blazor-win-x64-installer">Download</a>',
                    )
                if url == "https://chummer.run/downloads/releases.json":
                    return FakeResponse(url=url, json_payload=releases_payload)
                if url == "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json":
                    return FakeResponse(url=url, json_payload=canonical_payload)
                raise AssertionError(f"unexpected GET {url}")

            with mock.patch.object(MODULE.requests, "get", side_effect=fake_get):
                receipt = MODULE.evaluate(
                    base_url="https://chummer.run",
                    local_manifest_path=local_manifest,
                    local_canonical_manifest_path=local_canonical,
                    timeout=5.0,
                    artifact_probes_enabled=False,
                )

        self.assertEqual(receipt["status"], "fail")
        self.assertTrue(
            any("downloads page exposes artifact ids missing from live releases.json" in failure for failure in receipt["failures"])
        )

    def test_manifest_drift_fails(self) -> None:
        releases_payload = make_releases_manifest()
        canonical_payload = make_canonical_manifest()
        canonical_payload["artifacts"][0]["sha256"] = "b" * 64

        with tempfile.TemporaryDirectory(prefix="download-shelf-truth-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            write_json(local_manifest, releases_payload)
            write_json(local_canonical, canonical_payload)

            def fake_get(url: str, *args, **kwargs) -> FakeResponse:
                if url == "https://chummer.run/downloads":
                    return FakeResponse(
                        url=url,
                        text='<a data-download-artifact="avalonia-linux-x64-installer" href="/downloads/get/avalonia-linux-x64-installer">Download</a>',
                    )
                if url == "https://chummer.run/downloads/releases.json":
                    return FakeResponse(url=url, json_payload=releases_payload)
                if url == "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json":
                    return FakeResponse(url=url, json_payload=canonical_payload)
                raise AssertionError(f"unexpected GET {url}")

            with mock.patch.object(MODULE.requests, "get", side_effect=fake_get):
                receipt = MODULE.evaluate(
                    base_url="https://chummer.run",
                    local_manifest_path=local_manifest,
                    local_canonical_manifest_path=local_canonical,
                    timeout=5.0,
                    artifact_probes_enabled=False,
                )

        self.assertEqual(receipt["status"], "fail")
        self.assertTrue(
            any("differ for artifact avalonia-linux-x64-installer" in failure for failure in receipt["failures"])
        )

    def test_publish_and_verify_lanes_call_public_download_shelf_truth_gate(self) -> None:
        publish_script = (ROOT / "scripts" / "publish-download-bundle-http.sh").read_text(encoding="utf-8")
        verify_script = (ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")

        self.assertIn('python3 "$SCRIPT_DIR/verify_release_upload_response_truth.py"', publish_script)
        self.assertIn('--upload-response "$response_json"', publish_script)
        self.assertIn("CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH", publish_script)
        self.assertIn("CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_COUNT", publish_script)
        self.assertIn("CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_DELAY_SECONDS", publish_script)
        self.assertIn("CHUMMER_RELEASE_UPLOAD_VERIFY_SHELF_TRUTH_LIVE_MAX_SAMPLES", publish_script)
        self.assertIn('python3 "$SCRIPT_DIR/public_download_shelf_truth_gate.py"', publish_script)
        self.assertIn('--live-confirmation-count "$VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_COUNT"', publish_script)
        self.assertIn('--live-confirmation-delay-seconds "$VERIFY_SHELF_TRUTH_LIVE_CONFIRMATION_DELAY_SECONDS"', publish_script)
        self.assertIn('--live-max-samples "$VERIFY_SHELF_TRUTH_LIVE_MAX_SAMPLES"', publish_script)
        self.assertIn("test_public_download_shelf_truth_gate.py", verify_script)
        self.assertIn('python3 "$ROOT_DIR/scripts/public_download_shelf_truth_gate.py"', verify_script)


if __name__ == "__main__":
    unittest.main()
