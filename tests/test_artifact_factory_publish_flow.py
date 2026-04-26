from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO_ROOT / "scripts" / "materialize_artifact_factory_source_pack_batch.py"
PUBLISH_HTTP = REPO_ROOT / "scripts" / "publish-download-bundle-http.sh"


class ArtifactFactoryPublishFlowTests(unittest.TestCase):
    def test_materializer_builds_release_source_pack_batch_from_promoted_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-publish-flow-") as temp_root:
            temp_root_path = Path(temp_root)
            manifest_path = temp_root_path / "releases.json"
            promotion_result_path = temp_root_path / "promotion-result.json"
            output_path = temp_root_path / "artifact-factory-source-pack-batch.json"

            manifest_path.write_text(
                json.dumps(
                    {
                        "channel": "preview",
                        "version": "run-20260423-181724",
                        "downloads": [
                            {"id": "avalonia-linux-x64-installer", "kind": "desktop_release"},
                            {"id": "avalonia-win-x64-installer", "kind": "desktop_release"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            promotion_result_path.write_text(
                json.dumps({"promotedArtifactIds": ["avalonia-linux-x64-installer"]}),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--release-manifest",
                    str(manifest_path),
                    "--promotion-result",
                    str(promotion_result_path),
                    "--requested-by",
                    "fleet.release",
                    "--output",
                    str(output_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(["release"], payload["requiredFamilies"])
            self.assertEqual("fleet.release", payload["requestedBy"])
            self.assertEqual(1, len(payload["sourcePacks"]))
            release_pack = payload["sourcePacks"][0]
            self.assertEqual("release-pack-avalonia-linux-x64-installer", release_pack["sourcePackId"])
            self.assertEqual("desktop_release", release_pack["sourcePackKind"])
            self.assertEqual("approved", release_pack["approvalState"])
            self.assertEqual("avalonia-linux-x64-installer", release_pack["releaseArtifactId"])
            self.assertEqual("/downloads/install/avalonia-linux-x64-installer", release_pack["publicShelfRef"])
            self.assertIn("release:run-20260423-181724", release_pack["evidenceRefs"])
            self.assertIn("promotion:preview:avalonia-linux-x64-installer", release_pack["evidenceRefs"])
            self.assertIn(
                "public-shelf:/downloads/install/avalonia-linux-x64-installer",
                release_pack["evidenceRefs"],
            )

    def test_materializer_merges_sidecar_source_packs_and_family_overrides(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-sidecar-flow-") as temp_root:
            temp_root_path = Path(temp_root)
            manifest_path = temp_root_path / "releases.json"
            sidecar_path = temp_root_path / "source-packs.json"
            output_path = temp_root_path / "artifact-factory-source-pack-batch.json"

            manifest_path.write_text(
                json.dumps(
                    {
                        "channel": "preview",
                        "version": "run-20260423-181724",
                        "downloads": [{"id": "avalonia-linux-x64-installer", "kind": "desktop_release"}],
                    }
                ),
                encoding="utf-8",
            )
            sidecar_path.write_text(
                json.dumps(
                    {
                        "requiredFamilies": ["support", "publication"],
                        "requestedFormats": [{"family": "publication", "formats": ["caption", "packet"]}],
                        "sourcePacks": [
                            {
                                "sourcePackId": "support-pack-11709",
                                "sourcePackKind": "support_case",
                                "approvalState": "approved",
                                "provenanceRef": "support-case:11709",
                                "evidenceRefs": ["support:11709", "privacy:redacted", "install:preview"],
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
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--release-manifest",
                    str(manifest_path),
                    "--source-pack-file",
                    str(sidecar_path),
                    "--required-family",
                    "release",
                    "--output",
                    str(output_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(["publication", "release", "support"], payload["requiredFamilies"])
            self.assertEqual(
                [{"family": "publication", "formats": ["caption", "packet"]}],
                payload["requestedFormats"],
            )
            self.assertEqual(3, len(payload["sourcePacks"]))
            self.assertTrue(
                any(source_pack.get("sourcePackId") == "support-pack-11709" for source_pack in payload["sourcePacks"])
            )

    def test_publish_http_script_wires_artifact_factory_autolaunch(self) -> None:
        script_text = PUBLISH_HTTP.read_text(encoding="utf-8")
        self.assertIn("CHUMMER_ARTIFACT_FACTORY_AUTOLAUNCH", script_text)
        self.assertIn("materialize_artifact_factory_source_pack_batch.py", script_text)
        self.assertIn("launch_artifact_factory_source_pack_batch.py", script_text)
        self.assertIn("Artifact-factory batch launched via", script_text)

    def test_publish_http_script_auto_resolves_release_proof_candidates(self) -> None:
        script_text = PUBLISH_HTTP.read_text(encoding="utf-8")
        self.assertIn("resolve_release_proof_path()", script_text)
        self.assertIn('bundle_root / "proof" / "HUB_LOCAL_RELEASE_PROOF.generated.json"', script_text)
        self.assertIn('repo_root / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"', script_text)
        self.assertIn(
            'repo_root / "Chummer.Run.Api" / "wwwroot" / "proofs" / "mac-codex-release" / "HUB_LOCAL_RELEASE_PROOF.generated.json"',
            script_text,
        )
        self.assertIn('RELEASE_PROOF_PATH_RESOLVED="$(resolve_release_proof_path', script_text)
        self.assertIn('materializer_args+=("--release-proof" "$RELEASE_PROOF_PATH_RESOLVED")', script_text)

    def test_publish_http_script_prefers_resolved_release_proof_over_raw_env_check(self) -> None:
        script_text = PUBLISH_HTTP.read_text(encoding="utf-8")
        self.assertNotIn('materializer_args+=("--release-proof" "$RELEASE_PROOF_PATH")', script_text)
        self.assertNotIn('if [[ -n "${RELEASE_PROOF_PATH:-}" && -f "${RELEASE_PROOF_PATH:-}" ]]; then', script_text)

    def test_publish_http_script_leaves_required_families_empty_for_inference(self) -> None:
        script_text = PUBLISH_HTTP.read_text(encoding="utf-8")
        self.assertIn('ARTIFACT_FACTORY_REQUIRED_FAMILIES="${CHUMMER_ARTIFACT_FACTORY_REQUIRED_FAMILIES:-}"', script_text)
        self.assertNotIn('ARTIFACT_FACTORY_REQUIRED_FAMILIES="${CHUMMER_ARTIFACT_FACTORY_REQUIRED_FAMILIES:-release}"', script_text)

    def test_publish_http_script_passes_artifact_factory_audience_and_locale(self) -> None:
        script_text = PUBLISH_HTTP.read_text(encoding="utf-8")
        self.assertIn('ARTIFACT_FACTORY_AUDIENCE="${CHUMMER_ARTIFACT_FACTORY_AUDIENCE:-}"', script_text)
        self.assertIn('ARTIFACT_FACTORY_LOCALE="${CHUMMER_ARTIFACT_FACTORY_LOCALE:-}"', script_text)
        self.assertIn('materializer_args+=("--audience" "$ARTIFACT_FACTORY_AUDIENCE")', script_text)
        self.assertIn('materializer_args+=("--locale" "$ARTIFACT_FACTORY_LOCALE")', script_text)

    def test_materializer_infers_campaign_bundle_families_and_metadata_from_sidecar_packs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-campaign-sidecar-flow-") as temp_root:
            temp_root_path = Path(temp_root)
            manifest_path = temp_root_path / "releases.json"
            sidecar_path = temp_root_path / "campaign-source-packs.json"
            output_path = temp_root_path / "artifact-factory-source-pack-batch.json"

            manifest_path.write_text(
                json.dumps(
                    {
                        "channel": "preview",
                        "version": "run-20260423-181724",
                        "downloads": [{"id": "avalonia-linux-x64-installer", "kind": "desktop_release"}],
                    }
                ),
                encoding="utf-8",
            )
            sidecar_path.write_text(
                json.dumps(
                    {
                        "audience": "gm,table",
                        "locale": "de-DE",
                        "sourcePacks": [
                            {
                                "sourcePackId": "campaign-pack-redmond-arc",
                                "sourcePackKind": "campaign_pack",
                                "approvalState": "approved",
                                "provenanceRef": "campaign:redmond-arc:v1",
                                "evidenceRefs": [
                                    "campaign:redmond-arc",
                                    "primer:redmond-arc",
                                    "audience:gm",
                                    "audience:table",
                                    "locale:de-DE",
                                ],
                                "campaignId": "redmond-arc",
                                "publicShelfRef": "/artifacts/campaigns/redmond-arc/cold-open",
                                "audience": "gm,table",
                                "locale": "de-DE",
                            },
                            {
                                "sourcePackId": "mission-pack-silver-run",
                                "sourcePackKind": "mission_pack",
                                "approvalState": "approved",
                                "provenanceRef": "mission:silver-run:v2",
                                "evidenceRefs": [
                                    "mission:silver-run",
                                    "briefing:silver-run",
                                    "audience:gm",
                                    "audience:table",
                                    "locale:de-DE",
                                ],
                                "missionId": "silver-run",
                                "publicShelfRef": "/artifacts/missions/silver-run/briefing",
                                "audience": "gm,table",
                                "locale": "de-DE",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--release-manifest",
                    str(manifest_path),
                    "--source-pack-file",
                    str(sidecar_path),
                    "--output",
                    str(output_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(
                ["campaign_cold_open", "mission_briefing", "release"],
                payload["requiredFamilies"],
            )
            self.assertEqual("gm,table", payload["audience"])
            self.assertEqual("de-DE", payload["locale"])

    def test_materializer_infers_campaign_metadata_from_approved_pack_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-campaign-pack-metadata-") as temp_root:
            temp_root_path = Path(temp_root)
            manifest_path = temp_root_path / "releases.json"
            sidecar_path = temp_root_path / "campaign-source-packs.json"
            output_path = temp_root_path / "artifact-factory-source-pack-batch.json"

            manifest_path.write_text(
                json.dumps(
                    {
                        "channel": "preview",
                        "version": "run-20260423-181724",
                        "downloads": [{"id": "avalonia-linux-x64-installer", "kind": "desktop_release"}],
                    }
                ),
                encoding="utf-8",
            )
            sidecar_path.write_text(
                json.dumps(
                    {
                        "sourcePacks": [
                            {
                                "sourcePackId": "campaign-pack-redmond-arc",
                                "sourcePackKind": "campaign_pack",
                                "approvalState": "approved",
                                "provenanceRef": "campaign:redmond-arc:v1",
                                "evidenceRefs": [
                                    "campaign:redmond-arc",
                                    "primer:redmond-arc",
                                    "audience:gm",
                                    "audience:table",
                                    "locale:de-DE",
                                ],
                                "campaignId": "redmond-arc",
                                "publicShelfRef": "/artifacts/campaigns/redmond-arc/cold-open",
                                "audience": "gm,table",
                                "locale": "de-DE",
                            },
                            {
                                "sourcePackId": "mission-pack-silver-run",
                                "sourcePackKind": "mission_pack",
                                "approvalState": "approved",
                                "provenanceRef": "mission:silver-run:v2",
                                "evidenceRefs": [
                                    "mission:silver-run",
                                    "briefing:silver-run",
                                    "audience:gm",
                                    "audience:table",
                                    "locale:de-DE",
                                ],
                                "missionId": "silver-run",
                                "publicShelfRef": "/artifacts/missions/silver-run/briefing",
                                "audience": "gm,table",
                                "locale": "de-DE",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--release-manifest",
                    str(manifest_path),
                    "--source-pack-file",
                    str(sidecar_path),
                    "--output",
                    str(output_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(
                ["campaign_cold_open", "mission_briefing", "release"],
                payload["requiredFamilies"],
            )
            self.assertEqual("gm,table", payload["audience"])
            self.assertEqual("de-DE", payload["locale"])

    def test_materializer_rejects_campaign_pack_metadata_inference_when_packs_disagree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-campaign-pack-metadata-drift-") as temp_root:
            temp_root_path = Path(temp_root)
            manifest_path = temp_root_path / "releases.json"
            sidecar_path = temp_root_path / "campaign-source-packs.json"

            manifest_path.write_text(
                json.dumps(
                    {
                        "channel": "preview",
                        "version": "run-20260423-181724",
                        "downloads": [{"id": "avalonia-linux-x64-installer", "kind": "desktop_release"}],
                    }
                ),
                encoding="utf-8",
            )
            sidecar_path.write_text(
                json.dumps(
                    {
                        "sourcePacks": [
                            {
                                "sourcePackId": "campaign-pack-redmond-arc",
                                "sourcePackKind": "campaign_pack",
                                "approvalState": "approved",
                                "provenanceRef": "campaign:redmond-arc:v1",
                                "evidenceRefs": [
                                    "campaign:redmond-arc",
                                    "primer:redmond-arc",
                                    "audience:gm",
                                    "locale:de-DE",
                                ],
                                "campaignId": "redmond-arc",
                                "audience": "gm",
                                "locale": "de-DE",
                            },
                            {
                                "sourcePackId": "mission-pack-silver-run",
                                "sourcePackKind": "mission_pack",
                                "approvalState": "approved",
                                "provenanceRef": "mission:silver-run:v2",
                                "evidenceRefs": [
                                    "mission:silver-run",
                                    "briefing:silver-run",
                                    "audience:table",
                                    "locale:fr-FR",
                                ],
                                "missionId": "silver-run",
                                "audience": "table",
                                "locale": "fr-FR",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--release-manifest",
                    str(manifest_path),
                    "--source-pack-file",
                    str(sidecar_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("require --audience or sidecar audience when approved packs disagree", completed.stderr)

    def test_materializer_rejects_unapproved_sidecar_source_packs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-unapproved-sidecar-") as temp_root:
            temp_root_path = Path(temp_root)
            manifest_path = temp_root_path / "releases.json"
            sidecar_path = temp_root_path / "source-packs.json"

            manifest_path.write_text(
                json.dumps(
                    {
                        "channel": "preview",
                        "version": "run-20260423-181724",
                        "downloads": [{"id": "avalonia-linux-x64-installer", "kind": "desktop_release"}],
                    }
                ),
                encoding="utf-8",
            )
            sidecar_path.write_text(
                json.dumps(
                    {
                        "requiredFamilies": ["support"],
                        "sourcePacks": [
                            {
                                "sourcePackId": "support-pack-11709",
                                "sourcePackKind": "support_case",
                                "approvalState": "pending",
                                "provenanceRef": "support-case:11709",
                                "evidenceRefs": ["support:11709", "privacy:redacted", "install:preview"],
                                "supportCaseId": "11709",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--release-manifest",
                    str(manifest_path),
                    "--source-pack-file",
                    str(sidecar_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("must already be approved", completed.stderr)

    def test_materializer_rejects_requested_formats_for_unrequired_family(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-format-family-scope-") as temp_root:
            temp_root_path = Path(temp_root)
            manifest_path = temp_root_path / "releases.json"

            manifest_path.write_text(
                json.dumps(
                    {
                        "channel": "preview",
                        "version": "run-20260423-181724",
                        "downloads": [{"id": "avalonia-linux-x64-installer", "kind": "desktop_release"}],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--release-manifest",
                    str(manifest_path),
                    "--required-family",
                    "release",
                    "--requested-format",
                    "publication=caption,packet",
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("requested formats for family 'publication' without requiring that family", completed.stderr)

    def test_materializer_rejects_required_family_without_matching_approved_source_pack(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-missing-family-pack-") as temp_root:
            temp_root_path = Path(temp_root)
            manifest_path = temp_root_path / "releases.json"

            manifest_path.write_text(
                json.dumps(
                    {
                        "channel": "preview",
                        "version": "run-20260423-181724",
                        "downloads": [{"id": "avalonia-linux-x64-installer", "kind": "desktop_release"}],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--release-manifest",
                    str(manifest_path),
                    "--required-family",
                    "support",
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("has no approved source packs for required family 'support'", completed.stderr)

    def test_materializer_supports_sidecar_only_support_and_publication_batches(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-sidecar-only-batch-") as temp_root:
            temp_root_path = Path(temp_root)
            sidecar_path = temp_root_path / "source-packs.json"
            output_path = temp_root_path / "artifact-factory-source-pack-batch.json"

            sidecar_path.write_text(
                json.dumps(
                    {
                        "requiredFamilies": ["support", "publication"],
                        "sourcePacks": [
                            {
                                "sourcePackId": "support-pack-11709",
                                "sourcePackKind": "support_case",
                                "approvalState": "approved",
                                "provenanceRef": "support-case:11709",
                                "evidenceRefs": ["support:11709", "privacy:redacted", "install:preview"],
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
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--source-pack-file",
                    str(sidecar_path),
                    "--requested-by",
                    "fleet.support",
                    "--output",
                    str(output_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(["publication", "support"], payload["requiredFamilies"])
            self.assertEqual("fleet.support", payload["requestedBy"])
            self.assertEqual("artifact-factory-publication-pack-redmond-brief-support-pack-11709", payload["batchId"])
            self.assertEqual(2, len(payload["sourcePacks"]))

    def test_materializer_rejects_provider_specific_sidecar_provenance_before_launch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-provider-sidecar-") as temp_root:
            temp_root_path = Path(temp_root)
            sidecar_path = temp_root_path / "source-packs.json"

            sidecar_path.write_text(
                json.dumps(
                    {
                        "sourcePacks": [
                            {
                                "sourcePackId": "publication-pack-redmond-brief",
                                "sourcePackKind": "publication",
                                "approvalState": "approved",
                                "provenanceRef": "heygen:redmond-brief:v3",
                                "evidenceRefs": [
                                    "publication:redmond-brief:v3",
                                    "moderation:approved:redmond-brief",
                                    "public-shelf:/artifacts/publications/redmond-brief",
                                ],
                                "publicationId": "redmond-brief",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--source-pack-file",
                    str(sidecar_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("provider-specific provenanceRef", completed.stderr)
            self.assertIn("one-off provider flows", completed.stderr)

    def test_materializer_rejects_non_local_public_shelf_evidence_before_launch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-nonlocal-sidecar-") as temp_root:
            temp_root_path = Path(temp_root)
            sidecar_path = temp_root_path / "source-packs.json"

            sidecar_path.write_text(
                json.dumps(
                    {
                        "sourcePacks": [
                            {
                                "sourcePackId": "support-pack-11709",
                                "sourcePackKind": "support_case",
                                "approvalState": "approved",
                                "provenanceRef": "support-case:11709",
                                "evidenceRefs": [
                                    "support:11709",
                                    "privacy:redacted",
                                    "public-shelf:https://cdn.example.test/support/11709",
                                ],
                                "supportCaseId": "11709",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--source-pack-file",
                    str(sidecar_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("non-local public proof shelf evidenceRef", completed.stderr)

    def test_materializer_requires_manifest_or_sidecar_source_packs(self) -> None:
        completed = subprocess.run(
            [
                "python3",
                str(MATERIALIZER),
            ],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("requires --release-manifest or at least one --source-pack-file", completed.stderr)

    def test_materializer_fails_closed_when_campaign_bundle_metadata_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-campaign-sidecar-metadata-") as temp_root:
            temp_root_path = Path(temp_root)
            manifest_path = temp_root_path / "releases.json"
            sidecar_path = temp_root_path / "campaign-source-packs.json"

            manifest_path.write_text(
                json.dumps(
                    {
                        "channel": "preview",
                        "version": "run-20260423-181724",
                        "downloads": [{"id": "avalonia-linux-x64-installer", "kind": "desktop_release"}],
                    }
                ),
                encoding="utf-8",
            )
            sidecar_path.write_text(
                json.dumps(
                    {
                        "sourcePacks": [
                            {
                                "sourcePackId": "campaign-pack-redmond-arc",
                                "sourcePackKind": "campaign_pack",
                                "approvalState": "approved",
                                "provenanceRef": "campaign:redmond-arc:v1",
                                "evidenceRefs": ["campaign:redmond-arc", "primer:redmond-arc"],
                                "campaignId": "redmond-arc",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    "--release-manifest",
                    str(manifest_path),
                    "--source-pack-file",
                    str(sidecar_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("require --audience or sidecar audience", completed.stderr)


if __name__ == "__main__":
    unittest.main()
