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

GENERATION_ID = "release-20260705T040530Z-a1b2c3d4"


def json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.write_bytes(json_bytes(payload))


def make_releases_manifest() -> dict:
    return {
        "generationId": GENERATION_ID,
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
        "generationId": GENERATION_ID,
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


def make_upload_response(
    *,
    releases: dict | None = None,
    canonical: dict | None = None,
) -> dict:
    releases = releases if releases is not None else make_releases_manifest()
    canonical = canonical if canonical is not None else make_canonical_manifest()
    return {
        "version": "run-20260705-040324",
        "channel": "preview",
        "publishedAt": "2026-07-05T04:05:30Z",
        "promotedArtifactIds": [
            "avalonia-osx-arm64-installer",
            "blazor-desktop-osx-arm64-installer",
        ],
        "generationId": GENERATION_ID,
        "canonicalManifestSha256": MODULE.sha256_bytes(json_bytes(canonical)),
        "compatibilityManifestSha256": MODULE.sha256_bytes(json_bytes(releases)),
        "downloadsUrl": "https://chummer.run/downloads/",
    }


def evaluate_payloads(
    *,
    releases: dict | None = None,
    canonical: dict | None = None,
    response: dict | None = None,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="verify-release-upload-response-") as temp_root:
        root = Path(temp_root)
        local_manifest = root / "releases.json"
        local_canonical = root / "RELEASE_CHANNEL.generated.json"
        upload_response = root / "response.json"
        write_json(local_manifest, releases if releases is not None else make_releases_manifest())
        write_json(local_canonical, canonical if canonical is not None else make_canonical_manifest())
        write_json(
            upload_response,
            response if response is not None else make_upload_response(releases=releases, canonical=canonical),
        )
        return MODULE.evaluate(
            local_manifest_path=local_manifest,
            local_canonical_manifest_path=local_canonical,
            upload_response_path=upload_response,
        )


class VerifyReleaseUploadResponseTruthTests(unittest.TestCase):
    def test_passes_and_emits_only_safe_exact_publication_binding(self) -> None:
        receipt = evaluate_payloads()

        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(receipt["schemaVersion"], "chummer.release-upload-response-truth/v2")
        self.assertEqual(
            receipt["publicationBinding"],
            {
                "generationId": GENERATION_ID,
                "releaseVersion": "run-20260705-040324",
                "channel": "preview",
                "publishedAt": "2026-07-05T04:05:30Z",
                "artifactIds": [
                    "avalonia-osx-arm64-installer",
                    "blazor-desktop-osx-arm64-installer",
                ],
                "canonicalManifestSha256": receipt["candidateBinding"]["canonicalInputSha256"],
                "compatibilityManifestSha256": receipt["candidateBinding"]["compatibilityInputSha256"],
                "sanitizedUploadResponseSha256": receipt["publicationBinding"]["sanitizedUploadResponseSha256"],
                "candidateBindingSha256": receipt["publicationBinding"]["candidateBindingSha256"],
                "bindingSha256": receipt["publicationBinding"]["bindingSha256"],
            },
        )
        self.assertRegex(receipt["publicationBinding"]["bindingSha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(receipt["candidateBinding"]["canonicalInputSha256"], r"^sha256:[0-9a-f]{64}$")

    def test_fails_when_upload_response_version_does_not_match_local_manifest(self) -> None:
        response = make_upload_response()
        response["version"] = "run-20260704-170602"

        receipt = evaluate_payloads(response=response)

        self.assertEqual(receipt["status"], "fail")
        self.assertIsNone(receipt["publicationBinding"])
        self.assertIn(
            "upload response and local RELEASE_CHANNEL.generated.json differ for version",
            receipt["failures"],
        )

    def test_fails_when_local_manifest_identity_does_not_match_canonical_bytes(self) -> None:
        releases = make_releases_manifest()
        releases["channel"] = "stable"

        receipt = evaluate_payloads(releases=releases)

        self.assertEqual(receipt["status"], "fail")
        self.assertIn(
            "local releases.json and local RELEASE_CHANNEL.generated.json differ for channel",
            receipt["failures"],
        )

    def test_fails_on_missing_or_unsafe_generation_id(self) -> None:
        cases = [
            None,
            "",
            " generation-a",
            "../generation-a",
            "generation/child",
            "bad..generation",
            "generation:a",
            "x" * 129,
        ]
        for generation_id in cases:
            with self.subTest(generation_id=generation_id):
                response = make_upload_response()
                if generation_id is None:
                    response.pop("generationId")
                else:
                    response["generationId"] = generation_id

                receipt = evaluate_payloads(response=response)

                self.assertEqual(receipt["status"], "fail")
                self.assertIsNone(receipt["publicationBinding"])
                self.assertTrue(any("generationId" in failure for failure in receipt["failures"]))

    def test_fails_when_required_manifest_digest_is_missing(self) -> None:
        for key in ("canonicalManifestSha256", "compatibilityManifestSha256"):
            with self.subTest(key=key):
                response = make_upload_response()
                response.pop(key)

                receipt = evaluate_payloads(response=response)

                self.assertEqual(receipt["status"], "fail")
                self.assertIn(f"upload response {key} is missing or noncanonical", receipt["failures"])

    def test_fails_on_noncanonical_manifest_digests(self) -> None:
        invalid_digests = [
            "sha256:" + "A" * 64,
            "sha256:" + "a" * 63,
            "sha256:" + "g" * 64,
            "sha256:" + "a" * 64 + " ",
            123,
        ]
        for key in ("canonicalManifestSha256", "compatibilityManifestSha256"):
            for digest in invalid_digests:
                with self.subTest(key=key, digest=digest):
                    response = make_upload_response()
                    response[key] = digest

                    receipt = evaluate_payloads(response=response)

                    self.assertEqual(receipt["status"], "fail")
                    self.assertIn(f"upload response {key} is missing or noncanonical", receipt["failures"])

    def test_accepts_bare_lowercase_server_manifest_digests(self) -> None:
        response = make_upload_response()
        for key in ("canonicalManifestSha256", "compatibilityManifestSha256"):
            response[key] = response[key].removeprefix("sha256:")

        receipt = evaluate_payloads(response=response)

        self.assertEqual(receipt["status"], "pass", receipt["failures"])

    def test_fails_when_manifest_digest_bindings_collapse_to_one_value(self) -> None:
        response = make_upload_response()
        response["compatibilityManifestSha256"] = response["canonicalManifestSha256"]

        receipt = evaluate_payloads(response=response)

        self.assertEqual(receipt["status"], "fail")
        self.assertIn(
            "upload response canonical and compatibility manifest digests must identify distinct bytes",
            receipt["failures"],
        )

    def test_fails_when_valid_manifest_digest_does_not_match_exact_candidate_bytes(self) -> None:
        cases = [
            (
                "canonicalManifestSha256",
                "sha256:" + "c" * 64,
                "upload response canonicalManifestSha256 does not match exact local canonical manifest bytes",
            ),
            (
                "compatibilityManifestSha256",
                "sha256:" + "d" * 64,
                "upload response compatibilityManifestSha256 does not match exact local compatibility manifest bytes",
            ),
        ]
        for key, digest, failure in cases:
            with self.subTest(key=key):
                response = make_upload_response()
                response[key] = digest

                receipt = evaluate_payloads(response=response)

                self.assertEqual(receipt["status"], "fail")
                self.assertIn(failure, receipt["failures"])

    def test_fails_when_response_generation_does_not_match_candidate_manifests(self) -> None:
        response = make_upload_response()
        response["generationId"] = "release-20260705T040530Z-different"

        receipt = evaluate_payloads(response=response)

        self.assertEqual(receipt["status"], "fail")
        self.assertIn(
            "upload response generationId does not match the exact candidate generationId",
            receipt["failures"],
        )

    def test_fails_when_candidate_manifests_disagree_on_generation(self) -> None:
        canonical = make_canonical_manifest()
        canonical["generationId"] = "release-20260705T040530Z-different"

        receipt = evaluate_payloads(canonical=canonical)

        self.assertEqual(receipt["status"], "fail")
        self.assertIn("local release manifests disagree for generationId", receipt["failures"])

    def test_fails_when_response_artifact_ids_are_not_the_exact_candidate_inventory(self) -> None:
        cases = [
            ["unknown-artifact"],
            ["avalonia-osx-arm64-installer"],
            [
                "blazor-desktop-osx-arm64-installer",
                "avalonia-osx-arm64-installer",
            ],
            [
                "avalonia-osx-arm64-installer",
                "avalonia-osx-arm64-installer",
            ],
            "avalonia-osx-arm64-installer",
        ]
        for artifact_ids in cases:
            with self.subTest(artifact_ids=artifact_ids):
                response = make_upload_response()
                response["promotedArtifactIds"] = artifact_ids

                receipt = evaluate_payloads(response=response)

                self.assertEqual(receipt["status"], "fail")
                self.assertIsNone(receipt["publicationBinding"])

    def test_fails_when_local_manifest_artifact_ids_disagree(self) -> None:
        canonical = make_canonical_manifest()
        canonical["artifacts"][1]["artifactId"] = "different-artifact"

        receipt = evaluate_payloads(canonical=canonical)

        self.assertEqual(receipt["status"], "fail")
        self.assertIn("local release manifests disagree on the exact artifact ID inventory", receipt["failures"])

    def test_fails_on_conflicting_compatibility_artifact_id_aliases(self) -> None:
        releases = make_releases_manifest()
        releases["downloads"][0]["artifactId"] = "different-artifact"

        receipt = evaluate_payloads(releases=releases)

        self.assertEqual(receipt["status"], "fail")
        self.assertTrue(any("conflicting artifact ID aliases" in failure for failure in receipt["failures"]))

    def test_candidate_binding_hashes_exact_manifest_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="verify-release-upload-response-") as temp_root:
            root = Path(temp_root)
            local_manifest = root / "releases.json"
            local_canonical = root / "RELEASE_CHANNEL.generated.json"
            upload_response = root / "response.json"
            write_json(local_manifest, make_releases_manifest())
            canonical_bytes = json.dumps(make_canonical_manifest(), separators=(",", ":")).encode("utf-8")
            local_canonical.write_bytes(canonical_bytes)
            response = make_upload_response()
            response["canonicalManifestSha256"] = MODULE.sha256_bytes(canonical_bytes)
            write_json(upload_response, response)

            receipt = MODULE.evaluate(
                local_manifest_path=local_manifest,
                local_canonical_manifest_path=local_canonical,
                upload_response_path=upload_response,
            )

        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(
            receipt["candidateBinding"]["canonicalInputSha256"],
            MODULE.sha256_bytes(canonical_bytes),
        )

    def test_receipt_never_echoes_response_urls_or_claim_secrets(self) -> None:
        response = make_upload_response()
        response["downloadsUrl"] = "https://attacker.invalid/?ticket=secret-ticket"
        response["signedInInstallClaims"] = [
            {"artifactId": "avalonia-osx-arm64-installer", "claimCode": "secret-claim"}
        ]

        receipt = evaluate_payloads(response=response)
        encoded = json.dumps(receipt, sort_keys=True)

        self.assertEqual(receipt["status"], "pass")
        self.assertNotIn("attacker.invalid", encoded)
        self.assertNotIn("secret-ticket", encoded)
        self.assertNotIn("secret-claim", encoded)

    def test_fails_on_timezone_naive_publication_timestamp(self) -> None:
        response = make_upload_response()
        response["publishedAt"] = "2026-07-05T04:05:30"

        receipt = evaluate_payloads(response=response)

        self.assertEqual(receipt["status"], "fail")
        self.assertIn("upload response publishedAt must include a UTC offset", receipt["failures"])


if __name__ == "__main__":
    unittest.main()
