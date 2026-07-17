from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "launch_artifact_factory_source_pack_batch.py"


def release_media_request() -> dict[str, object]:
    return {
        "recipeId": "release-proof-shelf-bundle",
        "requiredReceiptRefs": [
            "release:run-20260415",
            "promotion:startup-smoke:avalonia-linux-x64",
            "public-shelf:/downloads/install/avalonia-linux-x64-installer",
        ],
        "publicProofShelfRefs": ["/artifacts/release-bundles/avalonia-linux-x64-installer"],
        "approvedSourcePacks": [
            {
                "sourcePackId": "release-pack-20260415",
                "sourcePackKind": "desktop_release",
                "provenanceRef": "release-channel:preview:run-20260415",
                "evidenceRefs": [
                    "release:run-20260415",
                    "promotion:startup-smoke:avalonia-linux-x64",
                    "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                ],
                "releaseArtifactId": "avalonia-linux-x64-installer",
            }
        ],
        "outputBindings": [
            {
                "format": "preview_card",
                "publicRef": "/artifacts/release-bundles/avalonia-linux-x64-installer/preview_card",
            }
        ],
    }


def support_media_request(include_release_pack: bool = False) -> dict[str, object]:
    approved_source_packs: list[dict[str, object]] = []
    if include_release_pack:
        approved_source_packs.append(
            {
                "sourcePackId": "release-pack-20260415",
                "sourcePackKind": "release",
                "provenanceRef": "release-channel:preview:run-20260415",
                "evidenceRefs": [
                    "release:run-20260415",
                    "promotion:startup-smoke:avalonia-linux-x64",
                    "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                ],
                "releaseArtifactId": "avalonia-linux-x64-installer",
            }
        )

    approved_source_packs.append(
        {
            "sourcePackId": "support-pack-11709",
            "sourcePackKind": "support_case",
            "provenanceRef": "support-case:11709",
            "evidenceRefs": [
                "support:11709",
                "privacy:redacted",
                "install:preview",
            ],
            "supportCaseId": "11709",
        }
    )

    return {
        "recipeId": "support-case-proof-packet",
        "requiredReceiptRefs": [
            "support:11709",
            "privacy:redacted",
            "install:preview",
        ],
        "publicProofShelfRefs": ["/account/support-packets/11709"],
        "approvedSourcePacks": approved_source_packs,
        "outputBindings": [
            {
                "format": "packet",
                "publicRef": "/account/support-packets/11709/packet",
            }
        ],
    }


def publication_media_request() -> dict[str, object]:
    return {
        "recipeId": "publication-proof-shelf-bundle",
        "requiredReceiptRefs": [
            "publication:redmond-brief:v3",
            "moderation:approved:redmond-brief",
            "public-shelf:/artifacts/publications/redmond-brief",
        ],
        "publicProofShelfRefs": ["/artifacts/publications/redmond-brief/bundles"],
        "approvedSourcePacks": [
            {
                "sourcePackId": "publication-pack-redmond-brief",
                "sourcePackKind": "publication",
                "provenanceRef": "publication:redmond-brief:v3",
                "evidenceRefs": [
                    "publication:redmond-brief:v3",
                    "moderation:approved:redmond-brief",
                    "public-shelf:/artifacts/publications/redmond-brief",
                ],
                "publicationId": "redmond-brief",
            }
        ],
        "outputBindings": [
            {
                "format": "caption",
                "publicRef": "/artifacts/publications/redmond-brief/bundles/caption",
            }
        ],
    }


def aggregate_media_request_refs(media_requests: list[dict[str, object]], field_name: str) -> list[str]:
    return sorted(
        {
            str(item).strip()
            for media_request in media_requests
            for item in media_request.get(field_name, [])
            if isinstance(item, str) and item.strip()
        }
    )


class _RecordingHandler(BaseHTTPRequestHandler):
    expected_methods_by_path = {
        "/api/internal/artifact-factory/recipes": "GET",
        "/api/internal/artifact-factory/source-pack-batches": "POST",
    }
    response_payloads_by_path = {
        "/api/internal/artifact-factory/recipes": {
            "contractName": "chummer.run.artifact_factory.recipe_job.v1",
            "recipeVersion": "2026-04-15",
            "recipes": [
                {
                    "family": "release",
                    "recipeId": "release-proof-shelf-bundle",
                    "allowedSourceKinds": ["release", "release_evidence", "desktop_release", "install_receipt"],
                    "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                    "requiredReceiptPrefixes": ["release", "promotion", "public-shelf"],
                },
                {
                    "family": "fix",
                    "recipeId": "fix-followthrough-bundle",
                    "allowedSourceKinds": ["fix_receipt", "support_case", "install_receipt", "release"],
                    "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                    "requiredReceiptPrefixes": ["fix", "install", "support"],
                },
                {
                    "family": "support",
                    "recipeId": "support-case-proof-packet",
                    "allowedSourceKinds": ["support_case", "crash_report", "install_receipt", "release"],
                    "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                    "requiredReceiptPrefixes": ["support", "privacy", "install"],
                },
                {
                    "family": "publication",
                    "recipeId": "publication-proof-shelf-bundle",
                    "allowedSourceKinds": ["publication", "creator_publication", "campaign_recap", "runtime_bundle"],
                    "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                    "requiredReceiptPrefixes": ["publication", "moderation", "public-shelf"],
                },
                {
                    "family": "campaign_cold_open",
                    "recipeId": "campaign-cold-open-bundle",
                    "allowedSourceKinds": ["campaign_primer", "campaign_pack", "campaign_cold_open_pack"],
                    "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                    "requiredReceiptPrefixes": ["campaign", "primer", "audience", "locale"],
                },
                {
                    "family": "mission_briefing",
                    "recipeId": "mission-briefing-reel",
                    "allowedSourceKinds": ["mission_pack", "mission_briefing", "mission_briefing_pack"],
                    "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                    "requiredReceiptPrefixes": ["mission", "briefing", "audience", "locale"],
                },
            ],
        },
        "/api/internal/artifact-factory/source-pack-batches": {
            "contractName": "chummer.run.artifact_factory.recipe_job.v1",
            "recipeVersion": "2026-04-15",
            "state": "queued",
            "jobCount": 1,
            "families": ["release"],
            "requiredFamilies": ["release"],
            "recipeIds": ["release-proof-shelf-bundle"],
            "jobIds": ["artifact-job-release-12345678"],
            "sourcePackIds": ["release-pack-20260415"],
            "requiredReceiptRefs": aggregate_media_request_refs([release_media_request()], "requiredReceiptRefs"),
            "publicProofShelfRefs": aggregate_media_request_refs([release_media_request()], "publicProofShelfRefs"),
            "jobs": [{"jobId": "artifact-job-release-12345678", "family": "release"}],
            "mediaFactoryRequests": [release_media_request()],
        },
    }
    response_status_by_path: dict[str, int] = {}
    requests: list[dict[str, object]] = []

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8") if length else ""
        parsed_body = json.loads(raw_body) if raw_body else None
        request_record = {
            "method": self.command,
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "host": self.headers.get("Host"),
            "forwarded_proto": self.headers.get("X-Forwarded-Proto"),
            "user_agent": self.headers.get("User-Agent"),
            "accept_language": self.headers.get("Accept-Language"),
            "content_type": self.headers.get("Content-Type"),
            "body": parsed_body,
        }
        type(self).requests.append(request_record)

        expected_method = type(self).expected_methods_by_path.get(self.path)
        if expected_method is None or self.command != expected_method:
            self.send_response(405)
            self.end_headers()
            return

        body = json.dumps(type(self).response_payloads_by_path[self.path]).encode("utf-8")
        self.send_response(type(self).response_status_by_path.get(self.path, 200))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ArtifactFactorySourcePackLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_fleet_internal_api_token = os.environ.get("FLEET_INTERNAL_API_TOKEN")
        os.environ["FLEET_INTERNAL_API_TOKEN"] = "expected-token"
        _RecordingHandler.expected_methods_by_path = {
            "/api/internal/artifact-factory/recipes": "GET",
            "/api/internal/artifact-factory/source-pack-batches": "POST",
        }
        _RecordingHandler.response_payloads_by_path = {
            "/api/internal/artifact-factory/recipes": {
                "contractName": "chummer.run.artifact_factory.recipe_job.v1",
                "recipeVersion": "2026-04-15",
                "recipes": [
                    {
                        "family": "release",
                        "recipeId": "release-proof-shelf-bundle",
                        "allowedSourceKinds": ["release", "release_evidence", "desktop_release", "install_receipt"],
                        "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                        "requiredReceiptPrefixes": ["release", "promotion", "public-shelf"],
                    },
                    {
                        "family": "fix",
                        "recipeId": "fix-followthrough-bundle",
                        "allowedSourceKinds": ["fix_receipt", "support_case", "install_receipt", "release"],
                        "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                        "requiredReceiptPrefixes": ["fix", "install", "support"],
                    },
                    {
                        "family": "support",
                        "recipeId": "support-case-proof-packet",
                        "allowedSourceKinds": ["support_case", "crash_report", "install_receipt", "release"],
                        "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                        "requiredReceiptPrefixes": ["support", "privacy", "install"],
                    },
                    {
                        "family": "publication",
                        "recipeId": "publication-proof-shelf-bundle",
                        "allowedSourceKinds": ["publication", "creator_publication", "campaign_recap", "runtime_bundle"],
                        "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                        "requiredReceiptPrefixes": ["publication", "moderation", "public-shelf"],
                    },
                    {
                        "family": "campaign_cold_open",
                        "recipeId": "campaign-cold-open-bundle",
                        "allowedSourceKinds": ["campaign_primer", "campaign_pack", "campaign_cold_open_pack"],
                        "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                        "requiredReceiptPrefixes": ["campaign", "primer", "audience", "locale"],
                    },
                    {
                        "family": "mission_briefing",
                        "recipeId": "mission-briefing-reel",
                        "allowedSourceKinds": ["mission_pack", "mission_briefing", "mission_briefing_pack"],
                        "allowedFormats": ["preview_card", "caption", "packet", "short_video", "audio"],
                        "requiredReceiptPrefixes": ["mission", "briefing", "audience", "locale"],
                    },
                ],
            },
            "/api/internal/artifact-factory/source-pack-batches": {
                "contractName": "chummer.run.artifact_factory.recipe_job.v1",
                "recipeVersion": "2026-04-15",
                "state": "queued",
                "jobCount": 1,
                "families": ["release"],
                "requiredFamilies": ["release"],
                "recipeIds": ["release-proof-shelf-bundle"],
                "jobIds": ["artifact-job-release-12345678"],
                "sourcePackIds": ["release-pack-20260415"],
                "requiredReceiptRefs": aggregate_media_request_refs([release_media_request()], "requiredReceiptRefs"),
                "publicProofShelfRefs": aggregate_media_request_refs([release_media_request()], "publicProofShelfRefs"),
                "jobs": [{"jobId": "artifact-job-release-12345678", "family": "release"}],
                "mediaFactoryRequests": [release_media_request()],
            },
        }
        _RecordingHandler.response_status_by_path = {}
        _RecordingHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.previous_fleet_internal_api_token is None:
            os.environ.pop("FLEET_INTERNAL_API_TOKEN", None)
        else:
            os.environ["FLEET_INTERNAL_API_TOKEN"] = self.previous_fleet_internal_api_token

    def test_launches_source_pack_batch_from_file(self) -> None:
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            json.dump(payload, handle)
            handle.flush()
            request_path = handle.name

        try:
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--base-url",
                    self.base_url,
                    "--public-host",
                    "chummer.run",
                    "--forwarded-proto",
                    "https",
                    "--request-file",
                    request_path,
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        finally:
            os.unlink(request_path)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            {
                "contractName": "chummer.run.artifact_factory.recipe_job.v1",
                "recipeVersion": "2026-04-15",
                "state": "queued",
                "jobCount": 1,
                "families": ["release"],
                "requiredFamilies": ["release"],
                "recipeIds": ["release-proof-shelf-bundle"],
                "jobIds": ["artifact-job-release-12345678"],
                "sourcePackIds": ["release-pack-20260415"],
                "requiredReceiptRefs": aggregate_media_request_refs([release_media_request()], "requiredReceiptRefs"),
                "publicProofShelfRefs": aggregate_media_request_refs([release_media_request()], "publicProofShelfRefs"),
                "jobs": [{"jobId": "artifact-job-release-12345678", "family": "release"}],
                "mediaFactoryRequests": [release_media_request()],
            },
            json.loads(result.stdout),
        )
        self.assertEqual(
            {
                "method": "GET",
                "path": "/api/internal/artifact-factory/recipes",
                "authorization": "Bearer expected-token",
                "host": "chummer.run",
                "forwarded_proto": "https",
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 ChummerArtifactFactoryLauncher/1.0",
                "accept_language": "en-US,en;q=0.9",
                "content_type": None,
                "body": None,
            },
            _RecordingHandler.requests[0],
        )
        self.assertEqual(
            {
                "method": "POST",
                "path": "/api/internal/artifact-factory/source-pack-batches",
                "authorization": "Bearer expected-token",
                "host": "chummer.run",
                "forwarded_proto": "https",
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 ChummerArtifactFactoryLauncher/1.0",
                "accept_language": "en-US,en;q=0.9",
                "content_type": "application/json",
                "body": payload,
            },
            _RecordingHandler.requests[1],
        )

    def test_lists_recipe_catalog(self) -> None:
        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--recipes",
            ],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual("GET", _RecordingHandler.requests[0]["method"])
        self.assertEqual("/api/internal/artifact-factory/recipes", _RecordingHandler.requests[0]["path"])
        self.assertIsNone(_RecordingHandler.requests[0]["body"])
        self.assertEqual(
            "release-proof-shelf-bundle",
            json.loads(result.stdout)["recipes"][0]["recipeId"],
        )

    def test_fails_when_recipe_catalog_contract_drifts(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/recipes"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/recipes"],
            "contractName": "chummer.run.artifact_factory.recipe_job.v2",
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--recipes",
            ],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contractName", result.stderr)
        self.assertIn("recipe_job.v1", result.stderr)

    def test_fails_when_batch_response_contract_drifts_from_recipe_catalog(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            "contractName": "chummer.run.artifact_factory.recipe_job.v2",
            "recipeVersion": "2026-04-15",
            "state": "queued",
            "jobCount": 1,
            "families": ["release"],
            "requiredFamilies": ["release"],
            "recipeIds": ["release-proof-shelf-bundle"],
            "jobIds": ["artifact-job-release-12345678"],
            "sourcePackIds": ["release-pack-20260415"],
            "jobs": [{"jobId": "artifact-job-release-12345678", "family": "release"}],
            "mediaFactoryRequests": [{"recipeId": "release-proof-shelf-bundle"}],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            json.dump(payload, handle)
            handle.flush()
            request_path = handle.name

        try:
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--base-url",
                    self.base_url,
                    "--public-host",
                    "chummer.run",
                    "--forwarded-proto",
                    "https",
                    "--request-file",
                    request_path,
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        finally:
            os.unlink(request_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contractName", result.stderr)
        self.assertIn("must match the recipe catalog", result.stderr)

    def test_fails_when_batch_response_required_families_drift_from_request(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "families": ["support"],
            "requiredFamilies": ["support"],
            "jobIds": ["artifact-job-support-12345678"],
            "jobs": [{"jobId": "artifact-job-support-12345678", "family": "support"}],
            "mediaFactoryRequests": [{"recipeId": "support-case-proof-packet"}],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requiredFamilies", result.stderr)
        self.assertIn("launch request requiredFamilies", result.stderr)

    def test_fails_when_batch_response_families_drift_from_request(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "families": ["support"],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("families", result.stderr)
        self.assertIn("launch request requiredFamilies", result.stderr)

    def test_fails_when_batch_response_source_pack_ids_drift_from_request(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "sourcePackIds": ["different-pack-20260415"],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sourcePackIds", result.stderr)
        self.assertIn("requested recipe families", result.stderr)

    def test_accepts_family_scoped_source_pack_ids_when_request_contains_extra_approved_packs(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "sourcePackIds": ["release-pack-20260415"],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                },
                {
                    "sourcePackId": "support-pack-11709",
                    "sourcePackKind": "support_case",
                    "approvalState": "approved",
                    "provenanceRef": "support-case:11709",
                    "evidenceRefs": [
                        "support:11709",
                        "privacy:redacted",
                        "install:preview",
                    ],
                    "supportCaseId": "11709",
                },
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(["release"], _RecordingHandler.requests[1]["body"]["requiredFamilies"])
        self.assertEqual(["release-pack-20260415"], json.loads(result.stdout)["sourcePackIds"])

    def test_fails_when_batch_response_recipe_ids_drift_from_required_families(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "recipeIds": ["support-case-proof-packet"],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("recipeIds", result.stderr)
        self.assertIn("launch request requiredFamilies", result.stderr)

    def test_fails_when_batch_response_job_count_drifts_from_required_families(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "jobCount": 2,
            "jobIds": [
                "artifact-job-release-12345678",
                "artifact-job-release-87654321",
            ],
            "jobs": [
                {"jobId": "artifact-job-release-12345678", "family": "release"},
                {"jobId": "artifact-job-release-87654321", "family": "release"},
            ],
            "mediaFactoryRequests": [
                {"recipeId": "release-proof-shelf-bundle"},
                {"recipeId": "release-proof-shelf-bundle"},
            ],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jobCount", result.stderr)
        self.assertIn("launch request requiredFamilies", result.stderr)

    def test_fails_when_batch_response_job_ids_length_drifts_from_job_count(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "jobCount": 2,
            "jobs": [
                {"jobId": "artifact-job-release-12345678", "family": "release"},
                {"jobId": "artifact-job-release-87654321", "family": "release"},
            ],
            "mediaFactoryRequests": [
                {"recipeId": "release-proof-shelf-bundle"},
                {"recipeId": "release-proof-shelf-bundle"},
            ],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jobIds length must match jobCount", result.stderr)

    def test_fails_when_batch_response_job_ids_drift_from_jobs(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "jobIds": ["artifact-job-release-different"],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jobs jobId values must match response jobIds", result.stderr)

    def test_fails_when_batch_response_job_families_drift_from_request(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "jobs": [{"jobId": "artifact-job-release-12345678", "family": "support"}],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jobs family values must match the launch request requiredFamilies", result.stderr)

    def test_fails_when_batch_response_media_factory_requests_length_drifts_from_job_count(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "jobCount": 2,
            "jobIds": [
                "artifact-job-release-12345678",
                "artifact-job-release-87654321",
            ],
            "jobs": [
                {"jobId": "artifact-job-release-12345678", "family": "release"},
                {"jobId": "artifact-job-release-87654321", "family": "release"},
            ],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mediaFactoryRequests length must match jobCount", result.stderr)

    def test_fails_when_batch_response_required_receipts_drift_from_media_requests(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "requiredReceiptRefs": ["release:run-20260415"],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requiredReceiptRefs", result.stderr)
        self.assertIn("mediaFactoryRequests receipt union", result.stderr)

    def test_fails_when_batch_response_public_shelf_refs_drift_from_media_requests(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "publicProofShelfRefs": ["/artifacts/release-bundles/different-installer"],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("publicProofShelfRefs", result.stderr)
        self.assertIn("mediaFactoryRequests proof shelf union", result.stderr)

    def test_fills_required_families_from_launchable_recipe_families_when_request_omits_them(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            **_RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"],
            "jobCount": 3,
            "families": ["publication", "release", "support"],
            "requiredFamilies": ["publication", "release", "support"],
            "recipeIds": [
                "publication-proof-shelf-bundle",
                "release-proof-shelf-bundle",
                "support-case-proof-packet",
            ],
            "jobIds": [
                "artifact-job-publication-12345678",
                "artifact-job-release-12345678",
                "artifact-job-support-12345678",
            ],
            "sourcePackIds": [
                "publication-pack-redmond-brief",
                "release-pack-20260415",
                "support-pack-11709",
            ],
            "requiredReceiptRefs": aggregate_media_request_refs(
                [publication_media_request(), release_media_request(), support_media_request(include_release_pack=True)],
                "requiredReceiptRefs",
            ),
            "publicProofShelfRefs": aggregate_media_request_refs(
                [publication_media_request(), release_media_request(), support_media_request(include_release_pack=True)],
                "publicProofShelfRefs",
            ),
            "jobs": [
                {"jobId": "artifact-job-publication-12345678", "family": "publication"},
                {"jobId": "artifact-job-release-12345678", "family": "release"},
                {"jobId": "artifact-job-support-12345678", "family": "support"},
            ],
            "mediaFactoryRequests": [
                publication_media_request(),
                release_media_request(),
                support_media_request(include_release_pack=True),
            ],
        }
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                },
                {
                    "sourcePackId": "support-pack-11709",
                    "sourcePackKind": "support_case",
                    "approvalState": "approved",
                    "provenanceRef": "support-case:11709",
                    "evidenceRefs": [
                        "support:11709",
                        "privacy:redacted",
                        "install:preview",
                    ],
                    "supportCaseId": "11709",
                },
                {
                    "sourcePackId": "publication-pack-redmond-brief",
                    "sourcePackKind": "publication",
                    "approvalState": "approved",
                    "provenanceRef": "publication:redmond-brief:v3",
                    "evidenceRefs": [
                        "publication:redmond-brief:v3",
                        "moderation:approved:redmond-brief",
                        "public-shelf:/artifacts/publications/redmond-brief",
                    ],
                    "publicationId": "redmond-brief",
                },
            ],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(["publication", "release", "support"], _RecordingHandler.requests[1]["body"]["requiredFamilies"])

    def test_fails_closed_when_request_omits_required_families_and_no_recipe_is_launchable(self) -> None:
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "unsupported-pack-20260415",
                    "sourcePackKind": "unsupported_kind",
                    "approvalState": "approved",
                    "provenanceRef": "unsupported:20260415",
                }
            ],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no approved source packs matching any supported recipe family", result.stderr)

    def test_fails_closed_when_requested_formats_target_family_outside_required_families(self) -> None:
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
            "requestedFormats": [{"family": "support", "formats": ["packet"]}],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside requiredFamilies", result.stderr)

    def test_fails_closed_when_required_family_lacks_recipe_anchor_or_receipts(self) -> None:
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(1, len(_RecordingHandler.requests))
        self.assertIn("no approved source packs for required recipe family/families: release", result.stderr)

    def test_fails_provider_specific_source_pack_refs_before_launch(self) -> None:
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "heygen:render-job-11709",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(1, len(_RecordingHandler.requests))
        self.assertIn("provider-specific provenanceRef", result.stderr)
        self.assertIn("one-off provider flows", result.stderr)

    def test_fails_external_public_shelf_evidence_before_launch(self) -> None:
        payload = {
            "batchId": "next90-m107-source-pack-wave",
            "requestedBy": "fleet.release",
            "sourcePacks": [
                {
                    "sourcePackId": "release-pack-20260415",
                    "sourcePackKind": "desktop_release",
                    "approvalState": "approved",
                    "provenanceRef": "release-channel:preview:run-20260415",
                    "evidenceRefs": [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:https://example.invalid/downloads/install/avalonia-linux-x64-installer",
                    ],
                    "releaseArtifactId": "avalonia-linux-x64-installer",
                }
            ],
            "requiredFamilies": ["release"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(1, len(_RecordingHandler.requests))
        self.assertIn("non-local public proof shelf evidenceRef", result.stderr)
        self.assertIn("Chummer public proof shelf", result.stderr)

    def test_launches_campaign_cold_open_and_mission_briefing_from_locale_matched_packs(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            "contractName": "chummer.run.artifact_factory.recipe_job.v1",
            "recipeVersion": "2026-04-15",
            "state": "queued",
            "jobCount": 2,
            "families": ["campaign_cold_open", "mission_briefing"],
            "requiredFamilies": ["campaign_cold_open", "mission_briefing"],
            "recipeIds": ["campaign-cold-open-bundle", "mission-briefing-reel"],
            "jobIds": ["artifact-job-campaign-cold-open-12345678", "artifact-job-mission-briefing-12345678"],
            "sourcePackIds": ["campaign-primer-redmond-01", "mission-pack-arcology-01"],
            "jobs": [
                {"jobId": "artifact-job-campaign-cold-open-12345678", "family": "campaign_cold_open"},
                {"jobId": "artifact-job-mission-briefing-12345678", "family": "mission_briefing"},
            ],
            "mediaFactoryRequests": [
                {
                    "recipeId": "campaign-cold-open-bundle",
                    "requiredReceiptRefs": [
                        "campaign:redmond-01",
                        "primer:approved:redmond-01",
                        "audience:players",
                        "locale:de-AT",
                    ],
                    "publicProofShelfRefs": ["/artifacts/campaigns/redmond-01/cold-open"],
                    "approvedSourcePacks": [
                        {
                            "sourcePackId": "campaign-primer-redmond-01",
                            "evidenceRefs": [
                                "campaign:redmond-01",
                                "primer:approved:redmond-01",
                                "audience:players",
                                "locale:de-AT",
                            ],
                            "campaignId": "redmond-01",
                            "audience": "players,gm",
                            "locale": "de-AT",
                        }
                    ],
                    "outputBindings": [
                        {
                            "format": "preview_card",
                            "publicRef": "/artifacts/campaigns/redmond-01/cold-open/preview_card",
                        }
                    ],
                },
                {
                    "recipeId": "mission-briefing-reel",
                    "requiredReceiptRefs": [
                        "mission:arcology-01",
                        "briefing:approved:arcology-01",
                        "audience:players",
                        "locale:de-AT",
                    ],
                    "publicProofShelfRefs": ["/artifacts/missions/arcology-01/briefing"],
                    "approvedSourcePacks": [
                        {
                            "sourcePackId": "mission-pack-arcology-01",
                            "evidenceRefs": [
                                "mission:arcology-01",
                                "briefing:approved:arcology-01",
                                "audience:players",
                                "locale:de-AT",
                            ],
                            "missionId": "arcology-01",
                            "audience": "players",
                            "locale": "de-AT",
                        }
                    ],
                    "outputBindings": [
                        {
                            "format": "preview_card",
                            "publicRef": "/artifacts/missions/arcology-01/briefing/preview_card",
                        }
                    ],
                },
            ],
        }
        media_requests = _RecordingHandler.response_payloads_by_path[
            "/api/internal/artifact-factory/source-pack-batches"
        ]["mediaFactoryRequests"]
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"][
            "requiredReceiptRefs"
        ] = aggregate_media_request_refs(media_requests, "requiredReceiptRefs")
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"][
            "publicProofShelfRefs"
        ] = aggregate_media_request_refs(media_requests, "publicProofShelfRefs")
        payload = {
            "batchId": "next90-m108-campaign-briefing-wave",
            "requestedBy": "campaign.ops",
            "audience": "players",
            "locale": "de-AT",
            "sourcePacks": [
                {
                    "sourcePackId": "campaign-primer-redmond-01",
                    "sourcePackKind": "campaign_primer",
                    "approvalState": "approved",
                    "provenanceRef": "campaign:redmond-01:primer:v2",
                    "evidenceRefs": [
                        "campaign:redmond-01",
                        "primer:approved:redmond-01",
                        "audience:players",
                        "locale:de-AT",
                    ],
                    "campaignId": "redmond-01",
                    "audience": "players,gm",
                    "locale": "de-AT",
                },
                {
                    "sourcePackId": "mission-pack-arcology-01",
                    "sourcePackKind": "mission_pack",
                    "approvalState": "approved",
                    "provenanceRef": "mission:arcology-01:briefing:v1",
                    "evidenceRefs": [
                        "mission:arcology-01",
                        "briefing:approved:arcology-01",
                        "audience:players",
                        "locale:de-AT",
                    ],
                    "missionId": "arcology-01",
                    "audience": "players",
                    "locale": "de-AT",
                },
            ],
            "requiredFamilies": ["campaign_cold_open", "mission_briefing"],
        }

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(["campaign_cold_open", "mission_briefing"], _RecordingHandler.requests[1]["body"]["requiredFamilies"])
        self.assertEqual("players", _RecordingHandler.requests[1]["body"]["audience"])
        self.assertEqual("de-AT", _RecordingHandler.requests[1]["body"]["locale"])
        self.assertEqual(["campaign-cold-open-bundle", "mission-briefing-reel"], json.loads(result.stdout)["recipeIds"])

    def test_fails_campaign_briefing_response_without_audience_locale_media_proof(self) -> None:
        _RecordingHandler.response_payloads_by_path["/api/internal/artifact-factory/source-pack-batches"] = {
            "contractName": "chummer.run.artifact_factory.recipe_job.v1",
            "recipeVersion": "2026-04-15",
            "state": "queued",
            "jobCount": 1,
            "families": ["campaign_cold_open"],
            "requiredFamilies": ["campaign_cold_open"],
            "recipeIds": ["campaign-cold-open-bundle"],
            "jobIds": ["artifact-job-campaign-cold-open-12345678"],
            "sourcePackIds": ["campaign-primer-redmond-01"],
            "jobs": [{"jobId": "artifact-job-campaign-cold-open-12345678", "family": "campaign_cold_open"}],
            "mediaFactoryRequests": [
                {
                    "recipeId": "campaign-cold-open-bundle",
                    "requiredReceiptRefs": ["campaign:redmond-01", "primer:approved:redmond-01"],
                    "approvedSourcePacks": [
                        {
                            "sourcePackId": "campaign-primer-redmond-01",
                            "evidenceRefs": ["campaign:redmond-01", "primer:approved:redmond-01"],
                            "campaignId": "redmond-01",
                            "audience": "players",
                            "locale": "de-AT",
                        }
                    ],
                    "publicProofShelfRefs": ["/artifacts/campaigns/redmond-01/cold-open"],
                    "outputBindings": [
                        {
                            "format": "preview_card",
                            "publicRef": "/artifacts/campaigns/redmond-01/cold-open/preview_card",
                        }
                    ],
                }
            ],
        }
        payload = {
            "batchId": "next90-m108-campaign-briefing-wave",
            "requestedBy": "campaign.ops",
            "audience": "players",
            "locale": "de-AT",
            "sourcePacks": [
                {
                    "sourcePackId": "campaign-primer-redmond-01",
                    "sourcePackKind": "campaign_primer",
                    "approvalState": "approved",
                    "provenanceRef": "campaign:redmond-01:primer:v2",
                    "evidenceRefs": [
                        "campaign:redmond-01",
                        "primer:approved:redmond-01",
                        "audience:players",
                        "locale:de-AT",
                    ],
                    "campaignId": "redmond-01",
                    "audience": "players",
                    "locale": "de-AT",
                }
            ],
            "requiredFamilies": ["campaign_cold_open"],
        }

        result = subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--request-file", "-"],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must include campaign proof anchor(s)", result.stderr)
        self.assertIn("audience:players", result.stderr)
        self.assertIn("locale:de-at", result.stderr)

    def test_fails_campaign_briefing_preflight_when_locale_drifts(self) -> None:
        payload = {
            "batchId": "next90-m108-campaign-briefing-wave",
            "requestedBy": "campaign.ops",
            "audience": "players",
            "locale": "fr-FR",
            "sourcePacks": [
                {
                    "sourcePackId": "campaign-primer-redmond-01",
                    "sourcePackKind": "campaign_primer",
                    "approvalState": "approved",
                    "provenanceRef": "campaign:redmond-01:primer:v2",
                    "evidenceRefs": ["campaign:redmond-01", "primer:approved:redmond-01", "audience:players", "locale:de-AT"],
                    "campaignId": "redmond-01",
                    "audience": "players",
                    "locale": "de-AT",
                }
            ],
            "requiredFamilies": ["campaign_cold_open"],
        }

        result = subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--request-file", "-"],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(1, len(_RecordingHandler.requests))
        self.assertIn("locale 'de-AT' does not match requested locale 'fr-FR'", result.stderr)

    def test_fails_campaign_briefing_preflight_when_audience_is_not_allowed(self) -> None:
        payload = {
            "batchId": "next90-m108-campaign-briefing-wave",
            "requestedBy": "campaign.ops",
            "audience": "players",
            "locale": "de-AT",
            "sourcePacks": [
                {
                    "sourcePackId": "mission-pack-arcology-01",
                    "sourcePackKind": "mission_pack",
                    "approvalState": "approved",
                    "provenanceRef": "mission:arcology-01:briefing:v1",
                    "evidenceRefs": ["mission:arcology-01", "briefing:approved:arcology-01", "audience:gm", "locale:de-AT"],
                    "missionId": "arcology-01",
                    "audience": "gm",
                    "locale": "de-AT",
                }
            ],
            "requiredFamilies": ["mission_briefing"],
        }

        result = subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--request-file", "-"],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(1, len(_RecordingHandler.requests))
        self.assertIn("audience does not allow requested audience 'players'", result.stderr)

    def test_fails_campaign_briefing_preflight_when_audience_anchor_drifts(self) -> None:
        payload = {
            "batchId": "next90-m108-campaign-briefing-wave",
            "requestedBy": "campaign.ops",
            "audience": "players",
            "locale": "de-AT",
            "sourcePacks": [
                {
                    "sourcePackId": "campaign-primer-redmond-01",
                    "sourcePackKind": "campaign_primer",
                    "approvalState": "approved",
                    "provenanceRef": "campaign:redmond-01:primer:v2",
                    "evidenceRefs": ["campaign:redmond-01", "primer:approved:redmond-01", "audience:gm", "locale:de-AT"],
                    "campaignId": "redmond-01",
                    "audience": "players",
                    "locale": "de-AT",
                }
            ],
            "requiredFamilies": ["campaign_cold_open"],
        }

        result = subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--request-file", "-"],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(1, len(_RecordingHandler.requests))
        self.assertIn("must include evidenceRef 'audience:players'", result.stderr)

    def test_fails_campaign_briefing_preflight_when_locale_anchor_drifts(self) -> None:
        payload = {
            "batchId": "next90-m108-campaign-briefing-wave",
            "requestedBy": "campaign.ops",
            "audience": "players",
            "locale": "de-AT",
            "sourcePacks": [
                {
                    "sourcePackId": "mission-pack-arcology-01",
                    "sourcePackKind": "mission_pack",
                    "approvalState": "approved",
                    "provenanceRef": "mission:arcology-01:briefing:v1",
                    "evidenceRefs": ["mission:arcology-01", "briefing:approved:arcology-01", "audience:players", "locale:fr-FR"],
                    "missionId": "arcology-01",
                    "audience": "players",
                    "locale": "de-AT",
                }
            ],
            "requiredFamilies": ["mission_briefing"],
        }

        result = subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--request-file", "-"],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(1, len(_RecordingHandler.requests))
        self.assertIn("must include evidenceRef 'locale:de-AT'", result.stderr)

    def test_fails_campaign_briefing_preflight_when_public_shelf_skips_surface(self) -> None:
        payload = {
            "batchId": "next90-m108-campaign-briefing-wave",
            "requestedBy": "campaign.ops",
            "audience": "players",
            "locale": "de-AT",
            "sourcePacks": [
                {
                    "sourcePackId": "campaign-primer-redmond-01",
                    "sourcePackKind": "campaign_primer",
                    "approvalState": "approved",
                    "provenanceRef": "campaign:redmond-01:primer:v2",
                    "evidenceRefs": ["campaign:redmond-01", "primer:approved:redmond-01", "audience:players", "locale:de-AT"],
                    "publicShelfRef": "/artifacts/campaigns/redmond-01",
                    "audience": "players",
                    "locale": "de-AT",
                }
            ],
            "requiredFamilies": ["campaign_cold_open"],
        }

        result = subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--request-file", "-"],
            cwd=REPO_ROOT,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(1, len(_RecordingHandler.requests))
        self.assertIn("/artifacts/campaigns/{id}/cold-open", result.stderr)

    def test_fails_closed_without_internal_token(self) -> None:
        env = os.environ.copy()
        env.pop("FLEET_INTERNAL_API_TOKEN", None)

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--request-file",
                "-",
            ],
            cwd=REPO_ROOT,
            env=env,
            input=json.dumps({"batchId": "missing-token"}),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("internal bearer token is required", result.stderr)

    def test_rejects_credential_cli_without_echoing_value(self) -> None:
        sentinel = "cli-token-must-not-be-echoed"
        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--base-url",
                self.base_url,
                "--token",
                sentinel,
                "--recipes",
            ],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential-bearing CLI arguments are not supported", result.stderr)
        self.assertNotIn(sentinel, result.stdout)
        self.assertNotIn(sentinel, result.stderr)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn('parser.add_argument(\n        "--token"', source)

    def test_http_error_body_is_suppressed_before_logging(self) -> None:
        hostile_secret = "must-not-leak-artifact-factory-bearer"
        _RecordingHandler.response_status_by_path = {
            "/api/internal/artifact-factory/recipes": 403,
        }
        _RecordingHandler.response_payloads_by_path[
            "/api/internal/artifact-factory/recipes"
        ] = {
            "message": f"Authorization: Bearer {hostile_secret}",
            "credential": hostile_secret,
            "traceId": "trace-safe-123",
        }

        env = os.environ.copy()
        env["FLEET_INTERNAL_API_TOKEN"] = "launcher-only-token"
        result = subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--recipes"],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("response detail suppressed", result.stderr)
        self.assertIn("traceId=trace-safe-123", result.stderr)
        self.assertNotIn(hostile_secret, result.stdout)
        self.assertNotIn(hostile_secret, result.stderr)
        self.assertNotIn("Authorization", result.stderr)


if __name__ == "__main__":
    unittest.main()
