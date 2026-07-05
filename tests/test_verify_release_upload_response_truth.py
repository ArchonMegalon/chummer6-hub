from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_upload_response_truth.py"
SPEC = importlib.util.spec_from_file_location("verify_release_upload_response_truth", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def make_releases_manifest() -> dict:
    return {
        "version": "run-20260705-040324",
        "channel": "preview",
        "publishedAt": "2026-07-05T04:05:30+00:00",
        "status": "published",
        "downloads": [
            {
                "id": "avalonia-osx-arm64-installer",
                "artifactId": "avalonia-osx-arm64-installer",
            },
            {
                "id": "blazor-desktop-osx-arm64-installer",
                "artifactId": "blazor-desktop-osx-arm64-installer",
            },
        ],
    }


def make_canonical_manifest() -> dict:
    return {
        "version": "run-20260705-040324",
        "channelId": "preview",
        "publishedAt": "2026-07-05T04:05:30Z",
        "status": "published",
        "artifacts": [
            {
                "artifactId": "avalonia-osx-arm64-installer",
            },
            {
                "artifactId": "blazor-desktop-osx-arm64-installer",
            },
        ],
    }


def make_upload_response() -> dict:
    return {
        "version": "run-20260705-040324",
        "channel": "preview",
        "publishedAt": "2026-07-05T04:05:30Z",
        "promotedArtifactIds": [
            "avalonia-osx-arm64-installer",
            "blazor-desktop-osx-arm64-installer",
        ],
        "downloadsUrl": "https://chummer.run/downloads/",
    }


class VerifyReleaseUploadResponseTruthTests(unittest.TestCase):
    def test_passes_when_upload_response_matches_local_manifests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="verify-release-upload-response-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            upload_response = root / "response.json"
            write_json(local_manifest, make_releases_manifest())
            write_json(local_canonical, make_canonical_manifest())
            write_json(upload_response, make_upload_response())

            receipt = MODULE.evaluate(
                local_manifest_path=local_manifest,
                local_canonical_manifest_path=local_canonical,
                upload_response_path=upload_response,
            )

        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(receipt["uploadResponse"]["view"]["version"], "run-20260705-040324")

    def test_fails_when_upload_response_version_does_not_match_local_manifest(self) -> None:
        response_payload = make_upload_response()
        response_payload["version"] = "run-20260704-170602"

        with tempfile.TemporaryDirectory(prefix="verify-release-upload-response-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            upload_response = root / "response.json"
            write_json(local_manifest, make_releases_manifest())
            write_json(local_canonical, make_canonical_manifest())
            write_json(upload_response, response_payload)

            receipt = MODULE.evaluate(
                local_manifest_path=local_manifest,
                local_canonical_manifest_path=local_canonical,
                upload_response_path=upload_response,
            )

        self.assertEqual(receipt["status"], "fail")
        self.assertTrue(
            any(
                "upload response and local RELEASE_CHANNEL.generated.json differ for version" in failure
                for failure in receipt["failures"]
            )
        )

    def test_fails_when_upload_response_promotes_unknown_artifact_ids(self) -> None:
        response_payload = make_upload_response()
        response_payload["promotedArtifactIds"] = ["unknown-artifact"]

        with tempfile.TemporaryDirectory(prefix="verify-release-upload-response-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            upload_response = root / "response.json"
            write_json(local_manifest, make_releases_manifest())
            write_json(local_canonical, make_canonical_manifest())
            write_json(upload_response, response_payload)

            receipt = MODULE.evaluate(
                local_manifest_path=local_manifest,
                local_canonical_manifest_path=local_canonical,
                upload_response_path=upload_response,
            )

        self.assertEqual(receipt["status"], "fail")
        self.assertTrue(
            any("promotedArtifactIds are missing from local manifests" in failure for failure in receipt["failures"])
        )


if __name__ == "__main__":
    unittest.main()
