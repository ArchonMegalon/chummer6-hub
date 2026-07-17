from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_downloads_version_marker.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_downloads_version_marker", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def visible_version_for_release_posture(
    version: str,
    *,
    release_status: str = "published",
    release_channel: str = "public_stable",
    release_supportability_state: str = "gold_supported",
    release_rollout_state: str = "public_stable",
) -> str:
    normalized = version.removeprefix("Version ").strip()
    if normalized.lower().startswith("run-") and len(normalized) >= 12:
        stamp = normalized[4:12]
        if stamp.isdigit():
            normalized_status = release_status.strip().lower()
            status_allows_stable_release = not normalized_status or normalized_status == "published"
            is_stable_release = (
                status_allows_stable_release
                and release_supportability_state == "gold_supported"
                and (
                    release_channel in {"public_stable", "stable"}
                    or release_rollout_state == "public_stable"
                )
            )
            preview_suffix = "" if is_stable_release else " (Preview)"
            return f"Version {stamp[0:4]}.{stamp[4:6]}.{stamp[6:8]}{preview_suffix}"
    return version if version.startswith("Version ") else f"Version {version}"


class _DownloadsMarkerHandler(BaseHTTPRequestHandler):
    include_marker = True
    marker_value: str | None = None
    downloads_visible_version_text = visible_version_for_release_posture("run-20260630")
    status_visible_version_text: str | None = None
    status_heading = "Stable downloads"
    release_contract_name: str | None = "Chummer.Hub.Registry.Contracts"
    release_version = "run-20260630"
    release_status = "published"
    release_channel = "public_stable"
    release_supportability_state = "gold_supported"
    release_rollout_state = "public_stable"
    release_supportability_summary = ""
    release_known_issue_summary = ""
    release_fix_availability_summary = ""
    release_public_install_count: int | None = None
    release_published_at: str | None = None
    release_proof_freshness_status: str | None = None
    release_public_trust_supportability_state: str | None = None
    release_public_trust_rollout_state: str | None = None
    release_registry_supportability_state: str | None = None
    release_registry_rollout_state: str | None = None
    release_manifest_overrides: dict[str, Any] | None = None

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/downloads":
            resolved_marker_value = (
                f"Version {self.release_version}" if self.marker_value is None else self.marker_value
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            parts = ["<main>"]
            if self.downloads_visible_version_text:
                parts.append(f'<p class="downloads-version">{self.downloads_visible_version_text}</p>')
            if self.include_marker:
                parts.append(
                    f'<span data-downloads-release-version="{resolved_marker_value}" hidden>{resolved_marker_value}</span>'
                )
            parts.append("</main>")
            self.wfile.write("".join(parts).encode("utf-8"))
            return
        if self.path == "/status":
            resolved_marker_value = (
                f"Version {self.release_version}" if self.marker_value is None else self.marker_value
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            parts = [f"<main><h1>{self.status_heading}</h1>"]
            if self.status_visible_version_text:
                parts.append(f"<p>{self.status_visible_version_text}</p>")
            if self.include_marker:
                parts.append(
                    f'<span data-downloads-release-version="{resolved_marker_value}" hidden>{resolved_marker_value}</span>'
                )
            parts.append("</main>")
            self.wfile.write("".join(parts).encode("utf-8"))
            return
        if self.path == "/downloads/RELEASE_CHANNEL.generated.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            payload = {
                "status": self.release_status,
                "version": self.release_version,
                "channel": self.release_channel,
                "supportabilityState": self.release_supportability_state,
                "rolloutState": self.release_rollout_state,
                "supportabilitySummary": self.release_supportability_summary,
                "knownIssueSummary": self.release_known_issue_summary,
                "fixAvailabilitySummary": self.release_fix_availability_summary,
            }
            if self.release_contract_name is not None:
                payload["contractName"] = self.release_contract_name
            if self.release_published_at is not None:
                payload["publishedAt"] = self.release_published_at
            public_trust_metrics: dict[str, Any] = {}
            if self.release_proof_freshness_status is not None:
                public_trust_metrics["proofFreshness"] = {
                    "status": self.release_proof_freshness_status,
                }
            if (
                self.release_public_trust_supportability_state is not None
                or self.release_public_trust_rollout_state is not None
            ):
                public_trust_metrics["releaseChannel"] = {
                    "supportabilityState": self.release_public_trust_supportability_state,
                    "rolloutState": self.release_public_trust_rollout_state,
                }
            if self.release_public_install_count is not None:
                public_trust_metrics["adoptionHealth"] = {
                    "publicInstallCount": self.release_public_install_count,
                }
            if public_trust_metrics:
                payload["publicTrustMetrics"] = public_trust_metrics
            if (
                self.release_registry_supportability_state is not None
                or self.release_registry_rollout_state is not None
            ):
                payload["registryBoundaryCoverage"] = {
                    "releaseChannel": {
                        "supportabilityState": self.release_registry_supportability_state,
                        "rolloutState": self.release_registry_rollout_state,
                    }
                }
            if self.release_manifest_overrides:
                payload.update(self.release_manifest_overrides)
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def with_server(
    include_marker: bool,
    downloads_visible_version_text: str | None = None,
    status_visible_version_text: str | None = None,
    marker_value: str | None = None,
    status_heading: str = "Stable downloads",
    release_contract_name: str | None = "Chummer.Hub.Registry.Contracts",
    release_version: str = "run-20260630",
    release_status: str = "published",
    release_channel: str = "public_stable",
    release_supportability_state: str = "gold_supported",
    release_rollout_state: str = "public_stable",
    release_supportability_summary: str = "",
    release_known_issue_summary: str = "",
    release_fix_availability_summary: str = "",
    release_public_install_count: int | None = None,
    release_published_at: str | None = None,
    release_proof_freshness_status: str | None = None,
    release_public_trust_supportability_state: str | None = None,
    release_public_trust_rollout_state: str | None = None,
    release_registry_supportability_state: str | None = None,
    release_registry_rollout_state: str | None = None,
    release_manifest_overrides: dict[str, Any] | None = None,
):
    handler = type(
        "ConfiguredDownloadsMarkerHandler",
        (_DownloadsMarkerHandler,),
        {
            "include_marker": include_marker,
            "marker_value": marker_value,
            "downloads_visible_version_text": downloads_visible_version_text or visible_version_for_release_posture(
                release_version,
                release_status=release_status,
                release_channel=release_channel,
                release_supportability_state=release_supportability_state,
                release_rollout_state=release_rollout_state,
            ),
            "status_visible_version_text": status_visible_version_text,
            "status_heading": status_heading,
            "release_contract_name": release_contract_name,
            "release_version": release_version,
            "release_status": release_status,
            "release_channel": release_channel,
            "release_supportability_state": release_supportability_state,
            "release_rollout_state": release_rollout_state,
            "release_supportability_summary": release_supportability_summary,
            "release_known_issue_summary": release_known_issue_summary,
            "release_fix_availability_summary": release_fix_availability_summary,
            "release_public_install_count": release_public_install_count,
            "release_published_at": release_published_at,
            "release_proof_freshness_status": release_proof_freshness_status,
            "release_public_trust_supportability_state": release_public_trust_supportability_state,
            "release_public_trust_rollout_state": release_public_trust_rollout_state,
            "release_registry_supportability_state": release_registry_supportability_state,
            "release_registry_rollout_state": release_registry_rollout_state,
            "release_manifest_overrides": release_manifest_overrides,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def close_server(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def write_release_manifest(path: Path, **overrides: Any) -> None:
    payload = {
        "contractName": "Chummer.Hub.Registry.Contracts",
        "status": "published",
        "version": "run-20260630",
        "channel": "public_stable",
        "supportabilityState": "gold_supported",
        "rolloutState": "public_stable",
        "supportabilitySummary": "",
        "knownIssueSummary": "",
        "fixAvailabilitySummary": "",
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_bound_preview_manifest(
    path: Path,
    *,
    proof_freshness_status: str = "stale",
    published_at: str = "2026-07-13T11:34:17Z",
) -> str:
    payload = {
        "contractName": "Chummer.Hub.Registry.Contracts",
        "status": "published",
        "version": "run-20260713-123603",
        "publishedAt": published_at,
        "channel": "preview",
        "supportabilityState": "preview_supported",
        "rolloutState": "promoted_preview",
        "supportabilitySummary": "Preview support remains subject to review caveats.",
        "knownIssueSummary": "Preview caveats remain active while proof receipts are reviewed.",
        "fixAvailabilitySummary": "Use the preview shelf while review remains active.",
        "publicTrustMetrics": {
            "proofFreshness": {
                "status": proof_freshness_status,
            },
            "releaseChannel": {
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
            },
        },
        "registryBoundaryCoverage": {
            "releaseChannel": {
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
            },
        },
    }
    raw_payload = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw_payload)
    return hashlib.sha256(raw_payload).hexdigest()


def write_source_contract_fixture(module, root: Path, *, valued_marker: bool) -> None:
    marker = (
        '<span data-downloads-release-version="@ManifestVersionText(Model.Manifest)" hidden>@ManifestVersionText(Model.Manifest)</span>'
        if valued_marker
        else '<span data-downloads-release-version hidden>@ManifestVersionText(Model.Manifest)</span>'
    )
    downloads = "\n".join(
        [
            "static string ManifestVersionText(PublicReleaseManifestDto manifest)",
            "!string.IsNullOrWhiteSpace(manifest.Version)",
            marker,
            "downloads-version",
        ]
    )
    status = "\n".join(
        [
            "static string ManifestVersionText(PublicReleaseManifestDto manifest)",
            "!string.IsNullOrWhiteSpace(manifest.Version)",
            marker,
        ]
    )
    css = ".surface-downloads .downloads-version { overflow-wrap: anywhere; }"
    spec = (
        "downloads_version_text: downloadsVersionText\n"
        "status_redirect_version_text: statusVersionText\n"
        "status_redirect_heading: statusHeadingText\n"
        "status_redirect_heading_recognized: statusHeadingRecognized\n"
        "status_redirect_heading_expected: expectedStatusHeading\n"
        "status_redirect_heading_matches_release_channel: statusHeadingMatchesReleaseChannel\n"
        "status_redirect_heading_uses_generic_updated_copy: statusHeadingUsesGenericUpdatedCopy\n"
    )
    payloads = {
        module.SOURCE_FILES[0]: downloads,
        module.SOURCE_FILES[1]: status,
        module.SOURCE_FILES[2]: css,
        module.SOURCE_FILES[3]: spec,
    }
    for relative_path, text in payloads.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_source_contract_tracks_downloads_version_marker_and_artifact_fields() -> None:
    module = load_module()

    result, failures = module.verify_source(REPO_ROOT)

    assert failures == []
    assert result["marker_in_view"] is True
    assert result["manifest_version_marker_prefers_release_version"] is True
    assert result["status_uses_marker_contract"] is True
    assert result["styled_marker"] is True
    assert result["playwright_records_version_text"] is True
    assert result["playwright_records_status_heading"] is True


def test_source_contract_rejects_boolean_downloads_version_marker(tmp_path: Path) -> None:
    module = load_module()
    write_source_contract_fixture(module, tmp_path, valued_marker=False)

    result, failures = module.verify_source(tmp_path)

    assert result["marker_in_view"] is False
    assert result["status_marker_in_view"] is False
    assert "Downloads view must expose a valued data-downloads-release-version attribute" in failures
    assert "Status view must expose a valued data-downloads-release-version attribute" in failures


def test_live_contract_passes_when_downloads_and_status_have_marker() -> None:
    module = load_module()
    server, thread, base_url = with_server(include_marker=True)
    try:
        result, failures = module.verify_live(base_url, timeout=5)
    finally:
        close_server(server, thread)

    assert failures == []
    assert result["downloads_marker"] is True
    assert result["status_redirect_marker"] is True
    assert result["downloads_version_marker_value"] == "Version run-20260630"
    assert result["status_redirect_version_marker_value"] == "Version run-20260630"
    assert result["downloads_version_text"] == "Version 2026.06.30"
    assert result["status_redirect_version_text"] == "Version run-20260630"
    assert result["status_redirect_heading"] == "Stable downloads"
    assert result["status_redirect_heading_recognized"] is True
    assert result["status_redirect_heading_expected"] is None
    assert result["status_redirect_heading_matches_release_channel"] is None
    assert result["status_redirect_heading_uses_generic_updated_copy"] is False


def test_expected_status_heading_requires_full_stable_public_tuple() -> None:
    module = load_module()

    assert module.expected_status_heading(
        "published",
        "run-20260630",
        "preview",
        "gold_supported",
        "promoted_preview",
    ) == "Preview downloads"
    assert module.expected_status_heading(
        "published",
        "run-20260630",
        "stable",
        "gold_supported",
        "public_stable",
    ) == "Stable downloads"
    assert module.expected_status_heading(
        "published",
        "run-20260630",
        "docker",
        "gold_supported",
        "public_stable",
    ) == "Stable downloads"
    assert module.expected_status_heading(
        "published",
        "run-20260630",
        "stable",
        "review_required",
        "public_stable",
    ) == "Preview downloads"
    assert module.expected_status_heading(
        "",
        "run-20260630",
        "stable",
        "gold_supported",
        "public_stable",
    ) == "Stable downloads"


def test_release_channel_heading_uses_explicit_public_installer_availability() -> None:
    module = load_module()
    preview_manifest = {
        "status": "published",
        "version": "run-20260630",
        "channel": "preview",
        "supportabilityState": "preview_supported",
        "rolloutState": "promoted_preview",
    }
    stable_manifest = {
        "status": "published",
        "version": "run-20260630",
        "channel": "public_stable",
        "supportabilityState": "gold_supported",
        "rolloutState": "public_stable",
    }

    paused_expected, paused_failures = module.release_channel_expectations(
        {
            **preview_manifest,
            "publicTrustMetrics": {"adoptionHealth": {"publicInstallCount": 0}},
        }
    )
    preview_expected, preview_failures = module.release_channel_expectations(
        {
            **preview_manifest,
            "publicTrustMetrics": {"adoptionHealth": {"publicInstallCount": 1}},
        }
    )
    stable_expected, stable_failures = module.release_channel_expectations(
        {
            **stable_manifest,
            "publicTrustMetrics": {"adoptionHealth": {"publicInstallCount": 2}},
        }
    )
    legacy_expected, legacy_failures = module.release_channel_expectations(preview_manifest)

    assert paused_failures == []
    assert paused_expected["public_installer_available"] is False
    assert paused_expected["status_heading_expected"] == "Downloads paused"
    assert preview_failures == []
    assert preview_expected["public_installer_available"] is True
    assert preview_expected["status_heading_expected"] == "Preview downloads"
    assert stable_failures == []
    assert stable_expected["public_installer_available"] is True
    assert stable_expected["status_heading_expected"] == "Stable downloads"
    assert legacy_failures == []
    assert legacy_expected["public_installer_available"] is True
    assert legacy_expected["status_heading_expected"] == "Preview downloads"


def test_release_channel_expectations_rejects_unknown_channel_even_with_nonempty_posture() -> None:
    module = load_module()

    _expectations, failures = module.release_channel_expectations(
        {
            "status": "published",
            "version": "run-20260713-123603",
            "channel": "experimental",
            "supportabilityState": "gold_supported",
            "rolloutState": "public_stable",
        }
    )

    assert "release channel channel is unsupported: experimental" in failures


def test_release_channel_expectations_rejects_all_preserved_source_rollout_blockers() -> None:
    module = load_module()

    for rollout_state in ("blocked", "disabled", "unpublished"):
        _expectations, failures = module.release_channel_expectations(
            {
                "status": "published",
                "version": "run-20260713-123603",
                "channel": "public_stable",
                "supportabilityState": "gold_supported",
                "rolloutState": rollout_state,
            }
        )

        assert f"release channel rolloutState is blocking: {rollout_state}" in failures


def test_expected_visible_version_candidates_follow_release_posture() -> None:
    module = load_module()

    assert module.expected_visible_version_candidates_for_posture(
        "run-20260630",
        "published",
        "public_stable",
        "gold_supported",
        "public_stable",
    ) == ["Version 2026.06.30", "Version run-20260630"]
    assert module.expected_visible_version_candidates_for_posture(
        "run-20260630",
        "published",
        "docker",
        "gold_supported",
        "public_stable",
    ) == ["Version 2026.06.30", "Version run-20260630"]
    assert module.expected_visible_version_candidates_for_posture(
        "run-20260630",
        "published",
        "preview",
        "preview_supported",
        "promoted_preview",
    ) == ["Version 2026.06.30 (Preview)", "Version run-20260630"]
    assert module.expected_visible_version_candidates_for_posture(
        "run-20260630",
        "",
        "public_stable",
        "gold_supported",
        "public_stable",
    ) == ["Version 2026.06.30", "Version run-20260630"]


def test_summary_promotes_source_and_live_fields_for_handoff_receipts() -> None:
    module = load_module()
    server, thread, base_url = with_server(include_marker=True)
    try:
        live_result, failures = module.verify_live(
            base_url,
            timeout=5,
            expected_release_status="published",
            expected_release_version="run-20260630",
            expected_release_channel="public_stable",
            expected_supportability_state="gold_supported",
            expected_rollout_state="public_stable",
        )
    finally:
        close_server(server, thread)

    assert failures == []
    summary = module.summarize_checks(
        [
            {
                "mode": "source",
                "marker_in_view": True,
                "manifest_version_marker_prefers_release_version": True,
                "styled_marker": True,
                "playwright_records_version_text": True,
            },
            live_result,
        ]
    )

    assert summary["source_marker_in_view"] is True
    assert summary["source_manifest_version_marker_prefers_release_version"] is True
    assert summary["source_styled_marker"] is True
    assert summary["source_playwright_records_version_text"] is True
    assert summary["base_url"] == base_url
    assert summary["expected_release_status"] == "published"
    assert summary["expected_release_channel"] == "public_stable"
    assert summary["expected_release_version"] == "run-20260630"
    assert summary["visible_version_matches_release_channel"] is True
    assert summary["status_redirect_version_matches_release_channel"] is True
    assert summary["release_manifest_status"] == "published"
    assert summary["release_manifest_status_matches_release_channel"] is True
    assert summary["release_manifest_channel"] == "public_stable"
    assert summary["release_manifest_channel_matches_release_channel"] is True
    assert summary["release_manifest_version_matches_release_channel"] is True
    assert summary["release_manifest_supportability_matches_release_channel"] is True
    assert summary["release_manifest_rollout_matches_release_channel"] is True
    assert summary["downloads_has_marker"] is True
    assert summary["status_redirect_has_marker"] is True
    assert summary["downloads_version_marker_value"] == "Version run-20260630"
    assert summary["status_redirect_version_marker_value"] == "Version run-20260630"
    assert summary["downloads_version_marker_matches_release_channel"] is True
    assert summary["status_redirect_version_marker_matches_release_channel"] is True
    assert summary["status_redirect_heading"] == "Stable downloads"
    assert summary["status_redirect_heading_recognized"] is True
    assert summary["status_redirect_heading_expected"] == "Stable downloads"
    assert summary["status_redirect_heading_expectation_source"] == "live_release_manifest"
    assert summary["status_redirect_heading_matches_release_channel"] is True
    assert summary["release_manifest_public_installer_available"] is True
    assert summary["status_redirect_heading_uses_generic_updated_copy"] is False
    assert summary["visible_version"] == "Version 2026.06.30"
    assert summary["status_redirect_version"] == "Version run-20260630"


def test_downloads_version_marker_exposes_stable_receipt_contract() -> None:
    module = load_module()

    assert module.CONTRACT_NAME == "chummer.downloads_version_marker.v1"


def test_public_release_manifest_passes_when_it_matches_release_channel(tmp_path) -> None:
    module = load_module()
    public_manifest = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_manifest(public_manifest)
    expected, expectation_failures = module.release_channel_expectations(json.loads(public_manifest.read_text(encoding="utf-8")))

    result, failures = module.verify_public_release_manifest(public_manifest, expected)

    assert expectation_failures == []
    assert failures == []
    assert result["exists"] is True
    assert result["public_release_status"] == "published"
    assert result["public_release_status_matches_release_channel"] is True
    assert result["public_release_version"] == "run-20260630"
    assert result["public_release_version_matches_release_channel"] is True
    assert result["public_release_channel"] == "public_stable"
    assert result["public_release_channel_matches_release_channel"] is True
    assert result["public_release_supportability_matches_release_channel"] is True
    assert result["public_release_rollout_matches_release_channel"] is True


def test_public_release_manifest_fails_when_posture_drifts_from_release_channel(tmp_path) -> None:
    module = load_module()
    release_channel = {
        "status": "published",
        "version": "run-20260630",
        "channel": "public_stable",
        "supportabilityState": "gold_supported",
        "rolloutState": "public_stable",
    }
    expected, expectation_failures = module.release_channel_expectations(release_channel)
    public_manifest = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_manifest(
        public_manifest,
        supportabilityState="review_required",
        rolloutState="coverage_incomplete",
    )

    result, failures = module.verify_public_release_manifest(public_manifest, expected)

    assert expectation_failures == []
    assert result["public_release_supportability_state"] == "review_required"
    assert result["public_release_rollout_state"] == "coverage_incomplete"
    assert result["public_release_supportability_matches_release_channel"] is False
    assert result["public_release_rollout_matches_release_channel"] is False
    assert "public release manifest supportabilityState does not match release channel" in failures
    assert "public release manifest rolloutState does not match release channel" in failures


def test_public_release_manifest_rejects_green_copy_for_preview_supported_release(tmp_path) -> None:
    module = load_module()
    release_channel = {
        "status": "published",
        "version": "run-20260630",
        "channel": "preview",
        "supportabilityState": "preview_supported",
        "rolloutState": "promoted_preview",
    }
    expected, expectation_failures = module.release_channel_expectations(release_channel)
    public_manifest = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_manifest(
        public_manifest,
        channel="preview",
        supportabilityState="preview_supported",
        rolloutState="promoted_preview",
        knownIssueSummary="Current release checks are clear.",
    )

    result, failures = module.verify_public_release_manifest(public_manifest, expected)

    assert expectation_failures == []
    assert result["public_release_copy_safe"] is False
    assert result["public_release_unsafe_copy_markers"] == ["checks are clear"]
    assert "public release manifest uses green/gold copy while supportabilityState is preview_supported" in failures


def test_public_release_manifest_accepts_preview_copy_with_explicit_caveat(tmp_path) -> None:
    module = load_module()
    release_channel = {
        "status": "published",
        "version": "run-20260630",
        "channel": "preview",
        "supportabilityState": "preview_supported",
        "rolloutState": "promoted_preview",
    }
    expected, expectation_failures = module.release_channel_expectations(release_channel)
    public_manifest = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_manifest(
        public_manifest,
        channel="preview",
        supportabilityState="preview_supported",
        rolloutState="promoted_preview",
        knownIssueSummary="Preview caveats still apply, but the shelf has recent install coverage.",
    )

    result, failures = module.verify_public_release_manifest(public_manifest, expected)

    assert expectation_failures == []
    assert failures == []
    assert result["public_release_copy_safe"] is True
    assert result["public_release_has_preview_or_review_caveat"] is True


def test_live_contract_fails_when_downloads_marker_is_missing() -> None:
    module = load_module()
    server, thread, base_url = with_server(include_marker=False)
    try:
        result, failures = module.verify_live(base_url, timeout=5)
    finally:
        close_server(server, thread)

    assert result["downloads_marker"] is False
    assert result["status_redirect_marker"] is False
    assert "/downloads missing data-downloads-release-version" in failures
    assert "/status missing data-downloads-release-version" in failures


def test_live_contract_fails_when_status_heading_uses_stale_generic_copy() -> None:
    module = load_module()
    server, thread, base_url = with_server(include_marker=True, status_heading="Updated")
    try:
        result, failures = module.verify_live(
            base_url,
            timeout=5,
            expected_release_status="published",
            expected_release_version="run-20260630",
            expected_release_channel="public_stable",
            expected_supportability_state="gold_supported",
            expected_rollout_state="public_stable",
        )
    finally:
        close_server(server, thread)

    assert result["status_redirect_heading"] == "Updated"
    assert result["status_redirect_heading_recognized"] is False
    assert result["status_redirect_heading_expected"] == "Stable downloads"
    assert result["status_redirect_heading_matches_release_channel"] is False
    assert result["status_redirect_heading_uses_generic_updated_copy"] is True
    assert "/status still uses stale generic Updated heading" in failures
    assert "/status heading is not a recognized release-status decision heading" in failures
    assert "/status heading does not match served release posture (expected Stable downloads)" in failures


def test_live_contract_fails_when_downloads_marker_value_is_empty() -> None:
    module = load_module()
    server, thread, base_url = with_server(include_marker=True, marker_value="")
    try:
        result, failures = module.verify_live(base_url, timeout=5)
    finally:
        close_server(server, thread)

    assert result["downloads_marker"] is True
    assert result["status_redirect_marker"] is True
    assert result["downloads_version_marker_value"] == ""
    assert result["status_redirect_version_marker_value"] == ""
    assert result["downloads_version_text"] == "Version 2026.06.30"
    assert result["status_redirect_version_text"] is None
    assert "/downloads data-downloads-release-version is empty" in failures
    assert "/status data-downloads-release-version is empty" in failures
    assert "/downloads data-downloads-release-version is not a Version value" in failures
    assert "/status data-downloads-release-version is not a Version value" in failures


def test_live_contract_fails_when_downloads_marker_value_disagrees_with_visible_text() -> None:
    module = load_module()
    server, thread, base_url = with_server(include_marker=True, marker_value="Version run-old")
    try:
        result, failures = module.verify_live(base_url, timeout=5, expected_release_version="run-20260630")
    finally:
        close_server(server, thread)

    assert result["downloads_version_marker_value"] == "Version run-old"
    assert result["status_redirect_version_marker_value"] == "Version run-old"
    assert result["downloads_version_text"] == "Version 2026.06.30"
    assert result["status_redirect_version_text"] == "Version run-old"
    assert result["visible_version_matches_release_channel"] is False
    assert result["status_redirect_version_matches_release_channel"] is False
    assert result["downloads_version_marker_matches_release_channel"] is False
    assert result["status_redirect_version_marker_matches_release_channel"] is False
    assert "/downloads visible Version text does not match release channel" not in failures
    assert "/downloads data-downloads-release-version does not match release channel" in failures
    assert "/status data-downloads-release-version does not match release channel" in failures


def test_live_contract_fails_when_visible_version_mismatches_release_channel() -> None:
    module = load_module()
    server, thread, base_url = with_server(include_marker=True, downloads_visible_version_text="Version 0.0.0.1")
    try:
        result, failures = module.verify_live(base_url, timeout=5, expected_release_version="run-20260630")
    finally:
        close_server(server, thread)

    assert result["expected_release_version"] == "run-20260630"
    assert result["downloads_version_text"] == "Version 0.0.0.1"
    assert result["status_redirect_version_text"] == "Version run-20260630"
    assert result["visible_version_matches_release_channel"] is False
    assert result["status_redirect_version_matches_release_channel"] is True
    assert "/downloads visible Version text does not match release channel" in failures


def test_live_contract_fails_when_live_release_posture_mismatches_release_channel() -> None:
    module = load_module()
    server, thread, base_url = with_server(
        include_marker=True,
        release_supportability_state="review_required",
        release_rollout_state="coverage_incomplete",
    )
    try:
        result, failures = module.verify_live(
            base_url,
            timeout=5,
            expected_release_status="published",
            expected_release_version="run-20260630",
            expected_release_channel="public_stable",
            expected_supportability_state="gold_supported",
            expected_rollout_state="public_stable",
        )
    finally:
        close_server(server, thread)

    assert result["release_manifest_version_matches_release_channel"] is True
    assert result["release_manifest_supportability_state"] == "review_required"
    assert result["release_manifest_rollout_state"] == "coverage_incomplete"
    assert result["release_manifest_supportability_matches_release_channel"] is False
    assert result["release_manifest_rollout_matches_release_channel"] is False
    assert "/downloads RELEASE_CHANNEL supportabilityState does not match release channel" in failures
    assert "/downloads RELEASE_CHANNEL rolloutState does not match release channel" in failures


def test_live_contract_fails_when_live_preview_release_claims_checks_are_clear() -> None:
    module = load_module()
    server, thread, base_url = with_server(
        include_marker=True,
        status_heading="Preview downloads",
        release_channel="preview",
        release_supportability_state="preview_supported",
        release_rollout_state="promoted_preview",
        release_known_issue_summary="Current release checks are clear.",
    )
    try:
        result, failures = module.verify_live(
            base_url,
            timeout=5,
            expected_release_status="published",
            expected_release_version="run-20260630",
            expected_release_channel="preview",
            expected_supportability_state="preview_supported",
            expected_rollout_state="promoted_preview",
        )
    finally:
        close_server(server, thread)

    assert result["release_manifest_copy_safe"] is False
    assert result["release_manifest_unsafe_copy_markers"] == ["checks are clear"]
    assert "/downloads RELEASE_CHANNEL live release manifest uses green/gold copy while supportabilityState is preview_supported" in failures


def test_live_contract_fails_when_status_heading_mismatches_release_channel_posture() -> None:
    module = load_module()
    server, thread, base_url = with_server(
        include_marker=True,
        status_heading="Stable downloads",
        release_channel="preview",
        release_supportability_state="preview_supported",
        release_rollout_state="promoted_preview",
    )
    try:
        result, failures = module.verify_live(
            base_url,
            timeout=5,
            expected_release_status="published",
            expected_release_version="run-20260630",
            expected_release_channel="preview",
            expected_supportability_state="preview_supported",
            expected_rollout_state="promoted_preview",
        )
    finally:
        close_server(server, thread)

    assert result["status_redirect_heading"] == "Stable downloads"
    assert result["status_redirect_heading_recognized"] is True
    assert result["status_redirect_heading_expected"] == "Preview downloads"
    assert result["status_redirect_heading_matches_release_channel"] is False
    assert "/status heading does not match served release posture (expected Preview downloads)" in failures


def test_live_heading_follows_served_paused_manifest_without_masking_registry_drift() -> None:
    module = load_module()
    server, thread, base_url = with_server(
        include_marker=True,
        status_heading="Downloads paused",
        release_version="run-20260713-123603",
        release_channel="preview",
        release_supportability_state="review_required",
        release_rollout_state="coverage_incomplete",
        release_known_issue_summary="Preview review-required caveats remain while coverage is incomplete.",
        release_public_install_count=0,
    )
    try:
        result, failures = module.verify_live(
            base_url,
            timeout=5,
            expected_release_status="published",
            expected_release_version="run-20260712-174412",
            expected_release_channel="public_stable",
            expected_supportability_state="gold_supported",
            expected_rollout_state="public_stable",
            expected_public_installer_available=True,
        )
    finally:
        close_server(server, thread)

    assert result["status_redirect_heading"] == "Downloads paused"
    assert result["status_redirect_heading_expected"] == "Downloads paused"
    assert result["status_redirect_heading_expectation_source"] == "live_release_manifest"
    assert result["status_redirect_heading_matches_release_channel"] is True
    assert result["release_manifest_public_installer_available"] is False
    assert result["release_manifest_version_matches_release_channel"] is False
    assert result["release_manifest_channel_matches_release_channel"] is False
    assert result["release_manifest_supportability_matches_release_channel"] is False
    assert result["release_manifest_rollout_matches_release_channel"] is False
    assert "/downloads RELEASE_CHANNEL version does not match release channel" in failures
    assert "/downloads RELEASE_CHANNEL channel does not match release channel" in failures
    assert "/status heading does not match served release posture" not in "\n".join(failures)


def test_live_contract_fails_when_live_release_status_mismatches_release_channel() -> None:
    module = load_module()
    server, thread, base_url = with_server(
        include_marker=True,
        release_status="draft",
    )
    try:
        result, failures = module.verify_live(
            base_url,
            timeout=5,
            expected_release_status="published",
            expected_release_version="run-20260630",
            expected_release_channel="public_stable",
            expected_supportability_state="gold_supported",
            expected_rollout_state="public_stable",
        )
    finally:
        close_server(server, thread)

    assert result["release_manifest_status"] == "draft"
    assert result["release_manifest_status_matches_release_channel"] is False
    assert "/downloads RELEASE_CHANNEL status does not match release channel" in failures


def test_live_contract_fails_when_live_release_channel_mismatches_release_channel() -> None:
    module = load_module()
    server, thread, base_url = with_server(
        include_marker=True,
        release_channel="preview",
    )
    try:
        result, failures = module.verify_live(
            base_url,
            timeout=5,
            expected_release_status="published",
            expected_release_version="run-20260630",
            expected_release_channel="public_stable",
            expected_supportability_state="gold_supported",
            expected_rollout_state="public_stable",
        )
    finally:
        close_server(server, thread)

    assert result["release_manifest_channel"] == "preview"
    assert result["release_manifest_channel_matches_release_channel"] is False
    assert "/downloads RELEASE_CHANNEL channel does not match release channel" in failures


def test_main_fails_when_expected_release_channel_is_not_launch_gold(tmp_path) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_channel.write_text(
        json.dumps(
            {
                "status": "published",
                "version": "run-20260630",
                "channel": "public_stable",
                "supportabilityState": "review_required",
                "rolloutState": "coverage_incomplete",
            }
        ),
        encoding="utf-8",
    )
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    write_release_manifest(
        public_manifest,
        version="run-20260630",
        supportabilityState="review_required",
        rolloutState="coverage_incomplete",
    )
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    server, thread, base_url = with_server(
        include_marker=True,
        release_supportability_state="review_required",
        release_rollout_state="coverage_incomplete",
    )
    try:
        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--base-url",
                base_url,
                "--release-channel-receipt",
                str(release_channel),
                "--public-release-manifest",
                str(public_manifest),
                "--output",
                str(output),
            ]
        )
    finally:
        close_server(server, thread)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["status"] == "fail"
    assert payload["release_channel_status"] == "published"
    assert "release channel supportabilityState is not launch-supported" in payload["failures"]
    assert "release channel rolloutState is blocking: coverage_incomplete" in payload["failures"]


def test_main_allows_review_required_coverage_incomplete_when_launch_support_not_required(tmp_path) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_channel.write_text(
        json.dumps(
            {
                "status": "published",
                "version": "run-20260630",
                "channel": "public_stable",
                "supportabilityState": "review_required",
                "rolloutState": "coverage_incomplete",
            }
        ),
        encoding="utf-8",
    )
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    write_release_manifest(
        public_manifest,
        version="run-20260630",
        supportabilityState="review_required",
        rolloutState="coverage_incomplete",
        knownIssueSummary="Known issue: required desktop tuple coverage is incomplete.",
        supportabilitySummary="Treat the current release as review-required because required desktop tuple coverage is incomplete.",
        fixAvailabilitySummary="Do not send fixed notices until required desktop tuple coverage is complete for the promoted shelf.",
    )
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    server, thread, base_url = with_server(
        include_marker=True,
        status_heading="Preview downloads",
        release_supportability_state="review_required",
        release_rollout_state="coverage_incomplete",
        release_known_issue_summary="Known issue: required desktop tuple coverage is incomplete.",
        release_supportability_summary="Treat the current release as review-required because required desktop tuple coverage is incomplete.",
        release_fix_availability_summary="Do not send fixed notices until required desktop tuple coverage is complete for the promoted shelf.",
    )
    try:
        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--base-url",
                base_url,
                "--release-channel-receipt",
                str(release_channel),
                "--public-release-manifest",
                str(public_manifest),
                "--allow-non-launch-supported-release-channel",
                "--allow-unbound-release-channel",
                "--output",
                str(output),
            ]
        )
    finally:
        close_server(server, thread)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "pass"
    assert payload["expected_release_supportability_state"] == "review_required"
    assert payload["expected_release_rollout_state"] == "coverage_incomplete"
    assert "release channel supportabilityState is not launch-supported" not in payload["failures"]
    assert "release channel rolloutState is blocking: coverage_incomplete" not in payload["failures"]


def test_main_passes_for_preview_channel_with_preview_supported(tmp_path) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_channel.write_text(
        json.dumps(
            {
                "status": "published",
                "version": "run-20260630",
                "channel": "preview",
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
            }
        ),
        encoding="utf-8",
    )
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    write_release_manifest(
        public_manifest,
        version="run-20260630",
        channel="preview",
        supportabilityState="preview_supported",
        rolloutState="promoted_preview",
        knownIssueSummary="Preview caveats still apply, but the shelf has recent install coverage.",
    )
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    server, thread, base_url = with_server(
        include_marker=True,
        status_heading="Preview downloads",
        release_channel="preview",
        release_supportability_state="preview_supported",
        release_rollout_state="promoted_preview",
        release_known_issue_summary="Preview caveats still apply, but the shelf has recent install coverage.",
    )
    try:
        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--base-url",
                base_url,
                "--release-channel-receipt",
                str(release_channel),
                "--public-release-manifest",
                str(public_manifest),
                "--allow-unbound-release-channel",
                "--output",
                str(output),
            ]
        )
    finally:
        close_server(server, thread)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "pass"
    assert payload["expected_release_supportability_state"] == "preview_supported"
    assert payload["public_release_supportability_state"] == "preview_supported"
    assert payload["public_release_copy_safe"] is True
    assert payload["release_manifest_copy_safe"] is True


def test_main_records_paused_heading_expectation_for_zero_public_installers(tmp_path) -> None:
    module = load_module()
    release_payload = {
        "status": "published",
        "version": "run-20260630",
        "channel": "preview",
        "supportabilityState": "preview_supported",
        "rolloutState": "promoted_preview",
        "knownIssueSummary": "Preview caveats still apply while public downloads are paused.",
        "publicTrustMetrics": {"adoptionHealth": {"publicInstallCount": 0}},
    }
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_channel.write_text(json.dumps(release_payload), encoding="utf-8")
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    write_release_manifest(public_manifest, **release_payload)
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    server, thread, base_url = with_server(
        include_marker=True,
        status_heading="Downloads paused",
        release_channel="preview",
        release_supportability_state="preview_supported",
        release_rollout_state="promoted_preview",
        release_known_issue_summary="Preview caveats still apply while public downloads are paused.",
        release_public_install_count=0,
    )
    try:
        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--base-url",
                base_url,
                "--release-channel-receipt",
                str(release_channel),
                "--public-release-manifest",
                str(public_manifest),
                "--allow-unbound-release-channel",
                "--output",
                str(output),
            ]
        )
    finally:
        close_server(server, thread)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "pass"
    assert payload["release_channel_public_installer_available"] is False
    assert payload["release_channel_status_heading_expected"] == "Downloads paused"
    assert payload["expected_public_installer_available"] is False
    assert payload["release_manifest_public_installer_available"] is False
    assert payload["status_redirect_heading_expected"] == "Downloads paused"
    assert payload["status_redirect_heading_expectation_source"] == "live_release_manifest"


def test_main_allows_review_required_public_stable_channel_when_flag_enabled(tmp_path) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_channel.write_text(
        json.dumps(
            {
                "status": "published",
                "version": "run-20260704-170602",
                "channel": "public_stable",
                "supportabilityState": "review_required",
                "rolloutState": "public_release_review_required",
            }
        ),
        encoding="utf-8",
    )
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    write_release_manifest(
        public_manifest,
        version="run-20260704-170602",
        channel="public_stable",
        supportabilityState="review_required",
        rolloutState="public_release_review_required",
        knownIssueSummary="Known issue: review-required release posture is active until launch blockers clear.",
    )
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    server, thread, base_url = with_server(
        include_marker=True,
        status_heading="Preview downloads",
        release_version="run-20260704-170602",
        release_channel="public_stable",
        release_supportability_state="review_required",
        release_rollout_state="public_release_review_required",
        release_known_issue_summary="Known issue: review-required release posture is active until launch blockers clear.",
    )
    try:
        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--base-url",
                base_url,
                "--release-channel-receipt",
                str(release_channel),
                "--public-release-manifest",
                str(public_manifest),
                "--allow-non-launch-supported-release-channel",
                "--allow-unbound-release-channel",
                "--output",
                str(output),
            ]
        )
    finally:
        close_server(server, thread)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "pass"
    assert "release channel supportabilityState is not launch-supported" not in payload["failures"]


def test_main_writes_fail_receipt_when_live_probe_errors(tmp_path) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_channel.write_text(
        json.dumps(
            {
                "status": "published",
                "version": "run-20260630",
                "channel": "preview",
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
            }
        ),
        encoding="utf-8",
    )
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    write_release_manifest(
        public_manifest,
        version="run-20260630",
        channel="preview",
        supportabilityState="preview_supported",
        rolloutState="promoted_preview",
        knownIssueSummary="Preview caveats still apply, but the shelf has recent install coverage.",
    )
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    original_verify_live = module.verify_live

    def raising_verify_live(*_args, **_kwargs):
        raise RuntimeError("http://127.0.0.1:8091/downloads: timed out")

    module.verify_live = raising_verify_live
    try:
        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--base-url",
                "http://127.0.0.1:8091",
                "--release-channel-receipt",
                str(release_channel),
                "--public-release-manifest",
                str(public_manifest),
                "--output",
                str(output),
            ]
        )
    finally:
        module.verify_live = original_verify_live

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["status"] == "fail"
    assert (
        "live verification requires --release-channel-receipt-sha256 unless --allow-unbound-release-channel is explicit"
        in payload["failures"]
    )
    assert "live probe failed: http://127.0.0.1:8091/downloads: timed out" in payload["failures"]
    live_check = next(check for check in payload["checks"] if check.get("mode") == "live")
    assert live_check["base_url"] == "http://127.0.0.1:8091"
    assert live_check["probe_error"] == "http://127.0.0.1:8091/downloads: timed out"


def test_main_defaults_source_root_to_repo_root_when_invoked_elsewhere(tmp_path) -> None:
    module = load_module()
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        exit_code = module.main(
            [
                "--skip-release-version-match",
                "--output",
                str(output),
            ]
        )
    finally:
        os.chdir(previous_cwd)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "pass"
    assert payload["source_marker_in_view"] is True


def test_main_live_skip_release_match_still_requires_explicit_unbound_opt_in(tmp_path) -> None:
    module = load_module()
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    legacy_output = tmp_path / "DOWNLOADS_VERSION_MARKER.legacy.generated.json"
    server, thread, base_url = with_server(include_marker=True)
    try:
        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--base-url",
                base_url,
                "--skip-release-version-match",
                "--output",
                str(output),
            ]
        )
        legacy_exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--base-url",
                base_url,
                "--skip-release-version-match",
                "--allow-unbound-release-channel",
                "--output",
                str(legacy_output),
            ]
        )
    finally:
        close_server(server, thread)

    payload = json.loads(output.read_text(encoding="utf-8"))
    legacy_payload = json.loads(legacy_output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["status"] == "fail"
    assert (
        "live verification requires --release-channel-receipt-sha256 unless --allow-unbound-release-channel is explicit"
        in payload["failures"]
    )
    assert payload["release_channel_receipt_binding_status"] == "not_requested"
    assert legacy_exit_code == 0
    assert legacy_payload["status"] == "pass"
    assert legacy_payload["release_channel_receipt_binding_status"] == "not_requested"


def test_main_binds_explicit_release_channel_receipt_to_exact_raw_sha256(tmp_path) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    expected_sha256 = write_bound_preview_manifest(release_channel)
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    public_manifest.write_bytes(release_channel.read_bytes())
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"

    exit_code = module.main(
        [
            "--source-root",
            str(REPO_ROOT),
            "--release-channel-receipt",
            str(release_channel),
            "--release-channel-receipt-sha256",
            expected_sha256,
            "--invocation-id",
            "bound-verifier-test-invocation",
            "--public-release-manifest",
            str(public_manifest),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "pass"
    assert payload["release_channel_receipt_sha256_expected"] == expected_sha256
    assert payload["release_channel_receipt_sha256_actual"] == expected_sha256
    assert payload["release_channel_receipt_sha256_matches"] is True
    assert payload["release_channel_receipt_binding_status"] == "pass"
    assert payload["contractName"] == "chummer.downloads_version_marker.bound.v1"
    assert payload["invocation_id"] == "bound-verifier-test-invocation"
    assert payload["release_channel_version"] == "run-20260713-123603"
    assert payload["release_channel_published_at"] == "2026-07-13T11:34:17Z"
    assert payload["release_channel_proof_freshness_status"] == "stale"
    assert payload["public_release_published_at_matches_release_channel"] is True
    assert payload["public_release_proof_freshness_matches_release_channel"] is True


def test_sha_bound_release_authority_rejects_contract_timestamp_and_alias_drift(tmp_path) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_bound_preview_manifest(release_channel)
    baseline = json.loads(release_channel.read_text(encoding="utf-8"))
    cases = (
        (
            "missing-contract",
            lambda payload: payload.pop("contractName"),
            "release channel contractName is missing for SHA-256-bound verification",
        ),
        (
            "wrong-contract",
            lambda payload: payload.__setitem__("contractName", "Unrelated.Release.Contract"),
            "release channel contractName is unsupported for SHA-256-bound verification",
        ),
        (
            "invalid-timestamp",
            lambda payload: payload.__setitem__("publishedAt", "2026-07-13 12:38:14"),
            "release channel publishedAt must be a timezone-aware ISO-8601 timestamp for SHA-256-bound verification",
        ),
        (
            "channel-alias-drift",
            lambda payload: payload.__setitem__("channelId", "experimental"),
            "release channel channel aliases conflict for SHA-256-bound verification",
        ),
        (
            "nested-posture-alias-drift",
            lambda payload: payload["publicTrustMetrics"]["releaseChannel"].__setitem__(
                "supportability_state",
                "gold_supported",
            ),
            "release channel publicTrustMetrics release-channel supportabilityState aliases conflict for SHA-256-bound verification",
        ),
    )

    for _case_name, mutate, expected_failure in cases:
        payload = json.loads(json.dumps(baseline))
        mutate(payload)
        _expectations, failures = module.release_channel_expectations(
            payload,
            require_bound_contract=True,
            require_published_at=True,
        )
        assert expected_failure in failures


def test_main_sha_bound_receipt_fails_closed_for_absent_or_unknown_proof_freshness(
    tmp_path: Path,
) -> None:
    module = load_module()
    for proof_status in ("", "unknown"):
        case_root = tmp_path / (proof_status or "absent")
        case_root.mkdir()
        release_channel = case_root / "RELEASE_CHANNEL.generated.json"
        expected_sha256 = write_bound_preview_manifest(
            release_channel,
            proof_freshness_status=proof_status,
        )
        public_manifest = case_root / "public-RELEASE_CHANNEL.generated.json"
        public_manifest.write_bytes(release_channel.read_bytes())
        output = case_root / "DOWNLOADS_VERSION_MARKER.generated.json"

        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--release-channel-receipt",
                str(release_channel),
                "--release-channel-receipt-sha256",
                expected_sha256,
                "--public-release-manifest",
                str(public_manifest),
                "--output",
                str(output),
            ]
        )

        payload = json.loads(output.read_text(encoding="utf-8"))
        assert exit_code == 1
        assert payload["release_channel_receipt_sha256_matches"] is True
        assert (
            "release channel proofFreshness.status must be fresh, stale, or explicit missing for SHA-256-bound verification"
            in payload["failures"]
        )


def test_main_sha_bound_receipt_rejects_internally_inconsistent_nested_posture(
    tmp_path: Path,
) -> None:
    module = load_module()
    cases = (
        (
            "supportability",
            ("publicTrustMetrics", "releaseChannel", "supportabilityState"),
            "gold_supported",
            "release channel publicTrustMetrics release-channel supportabilityState contradicts the top-level SHA-256-bound posture",
        ),
        (
            "rollout",
            ("registryBoundaryCoverage", "releaseChannel", "rolloutState"),
            "coverage_incomplete",
            "release channel registryBoundaryCoverage release-channel rolloutState contradicts the top-level SHA-256-bound posture",
        ),
    )
    for case_name, path, replacement, expected_failure in cases:
        case_root = tmp_path / case_name
        case_root.mkdir()
        release_channel = case_root / "RELEASE_CHANNEL.generated.json"
        write_bound_preview_manifest(release_channel)
        release_payload = json.loads(release_channel.read_text(encoding="utf-8"))
        target = release_payload
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = replacement
        raw_payload = (json.dumps(release_payload, sort_keys=True) + "\n").encode("utf-8")
        release_channel.write_bytes(raw_payload)
        expected_sha256 = hashlib.sha256(raw_payload).hexdigest()
        public_manifest = case_root / "public-RELEASE_CHANNEL.generated.json"
        public_manifest.write_bytes(raw_payload)
        output = case_root / "DOWNLOADS_VERSION_MARKER.generated.json"

        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--release-channel-receipt",
                str(release_channel),
                "--release-channel-receipt-sha256",
                expected_sha256,
                "--public-release-manifest",
                str(public_manifest),
                "--output",
                str(output),
            ]
        )

        result = json.loads(output.read_text(encoding="utf-8"))
        assert exit_code == 1
        assert expected_failure in result["failures"]


def test_main_rejects_release_channel_receipt_sha256_mismatch(tmp_path) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    actual_sha256 = write_bound_preview_manifest(release_channel)
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    public_manifest.write_bytes(release_channel.read_bytes())
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    wrong_sha256 = "0" * 64 if actual_sha256 != "0" * 64 else "1" * 64

    exit_code = module.main(
        [
            "--source-root",
            str(REPO_ROOT),
            "--release-channel-receipt",
            str(release_channel),
            "--release-channel-receipt-sha256",
            wrong_sha256,
            "--public-release-manifest",
            str(public_manifest),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["status"] == "fail"
    assert payload["release_channel_receipt_sha256_expected"] == wrong_sha256
    assert payload["release_channel_receipt_sha256_actual"] == actual_sha256
    assert payload["release_channel_receipt_sha256_matches"] is False
    assert payload["release_channel_receipt_binding_status"] == "fail"
    assert "release channel receipt SHA-256 does not match the explicitly selected digest" in payload["failures"]


def test_main_accepts_consistent_conservative_served_review_floor_for_stale_or_missing_proof(tmp_path) -> None:
    module = load_module()
    for proof_status in ("stale", "missing"):
        case_root = tmp_path / proof_status
        case_root.mkdir()
        release_channel = case_root / "RELEASE_CHANNEL.generated.json"
        expected_sha256 = write_bound_preview_manifest(
            release_channel,
            proof_freshness_status=proof_status,
        )
        public_manifest = case_root / "public-RELEASE_CHANNEL.generated.json"
        public_manifest.write_bytes(release_channel.read_bytes())
        output = case_root / "DOWNLOADS_VERSION_MARKER.generated.json"
        server, thread, base_url = with_server(
            include_marker=True,
            status_heading="Preview downloads",
            release_version="run-20260713-123603",
            release_channel="preview",
            release_supportability_state="review_required",
            release_rollout_state="public_release_review_required",
            release_supportability_summary="Treat this preview as review-required while proof receipts are checked.",
            release_known_issue_summary="Known issue: preview proof receipts remain under review.",
            release_fix_availability_summary="Use the preview shelf while review remains active.",
            release_published_at="2026-07-13T11:34:17Z",
            release_proof_freshness_status=proof_status,
            release_public_trust_supportability_state="review_required",
            release_public_trust_rollout_state="public_release_review_required",
            release_registry_supportability_state="review_required",
            release_registry_rollout_state="public_release_review_required",
        )
        try:
            exit_code = module.main(
                [
                    "--source-root",
                    str(REPO_ROOT),
                    "--base-url",
                    base_url,
                    "--release-channel-receipt",
                    str(release_channel),
                    "--release-channel-receipt-sha256",
                    expected_sha256,
                    "--public-release-manifest",
                    str(public_manifest),
                    "--output",
                    str(output),
                ]
            )
        finally:
            close_server(server, thread)

        payload = json.loads(output.read_text(encoding="utf-8"))
        assert exit_code == 0
        assert payload["status"] == "pass"
        assert payload["release_manifest_supportability_matches_release_channel"] is False
        assert payload["release_manifest_rollout_matches_release_channel"] is False
        assert payload["release_manifest_supportability_compatible_with_release_channel"] is True
        assert payload["release_manifest_rollout_compatible_with_release_channel"] is True
        assert payload["release_manifest_conservative_review_floor_applied"] is True
        assert payload["release_manifest_internal_supportability_consistent"] is True
        assert payload["expected_release_published_at"] == "2026-07-13T11:34:17Z"
        assert payload["expected_release_proof_freshness_status"] == proof_status
        assert payload["release_manifest_published_at_matches_release_channel"] is True
        assert payload["release_manifest_proof_freshness_matches_release_channel"] is True


def test_main_rejects_review_floor_for_fresh_proof_or_mixed_nested_supportability(tmp_path) -> None:
    module = load_module()
    cases = (
        ("fresh", "review_required", True),
        ("stale", "preview_supported", False),
    )
    for proof_status, registry_supportability, internally_consistent in cases:
        case_root = tmp_path / f"{proof_status}-{registry_supportability}"
        case_root.mkdir()
        release_channel = case_root / "RELEASE_CHANNEL.generated.json"
        expected_sha256 = write_bound_preview_manifest(
            release_channel,
            proof_freshness_status=proof_status,
        )
        public_manifest = case_root / "public-RELEASE_CHANNEL.generated.json"
        public_manifest.write_bytes(release_channel.read_bytes())
        output = case_root / "DOWNLOADS_VERSION_MARKER.generated.json"
        server, thread, base_url = with_server(
            include_marker=True,
            status_heading="Preview downloads",
            release_version="run-20260713-123603",
            release_channel="preview",
            release_supportability_state="review_required",
            release_rollout_state="public_release_review_required",
            release_supportability_summary="Treat this preview as review-required while proof receipts are checked.",
            release_known_issue_summary="Known issue: preview proof receipts remain under review.",
            release_fix_availability_summary="Use the preview shelf while review remains active.",
            release_published_at="2026-07-13T11:34:17Z",
            release_proof_freshness_status=proof_status,
            release_public_trust_supportability_state="review_required",
            release_public_trust_rollout_state="public_release_review_required",
            release_registry_supportability_state=registry_supportability,
            release_registry_rollout_state="public_release_review_required",
        )
        try:
            exit_code = module.main(
                [
                    "--source-root",
                    str(REPO_ROOT),
                    "--base-url",
                    base_url,
                    "--release-channel-receipt",
                    str(release_channel),
                    "--release-channel-receipt-sha256",
                    expected_sha256,
                    "--public-release-manifest",
                    str(public_manifest),
                    "--output",
                    str(output),
                ]
            )
        finally:
            close_server(server, thread)

        payload = json.loads(output.read_text(encoding="utf-8"))
        assert exit_code == 1
        assert payload["status"] == "fail"
        assert payload["release_manifest_supportability_compatible_with_release_channel"] is False
        assert payload["release_manifest_rollout_compatible_with_release_channel"] is False
        assert payload["release_manifest_conservative_review_floor_applied"] is False
        assert payload["release_manifest_internal_supportability_consistent"] is internally_consistent


def test_main_rejects_live_published_at_drift_even_when_review_floor_is_conservative(tmp_path) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    expected_sha256 = write_bound_preview_manifest(release_channel)
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    public_manifest.write_bytes(release_channel.read_bytes())
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    server, thread, base_url = with_server(
        include_marker=True,
        status_heading="Preview downloads",
        release_version="run-20260713-123603",
        release_channel="preview",
        release_supportability_state="review_required",
        release_rollout_state="public_release_review_required",
        release_supportability_summary="Treat this preview as review-required while proof receipts are checked.",
        release_known_issue_summary="Known issue: preview proof receipts remain under review.",
        release_fix_availability_summary="Use the preview shelf while review remains active.",
        release_published_at="2026-07-13T11:35:17Z",
        release_proof_freshness_status="stale",
        release_public_trust_supportability_state="review_required",
        release_public_trust_rollout_state="public_release_review_required",
        release_registry_supportability_state="review_required",
        release_registry_rollout_state="public_release_review_required",
    )
    try:
        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--base-url",
                base_url,
                "--release-channel-receipt",
                str(release_channel),
                "--release-channel-receipt-sha256",
                expected_sha256,
                "--public-release-manifest",
                str(public_manifest),
                "--output",
                str(output),
            ]
        )
    finally:
        close_server(server, thread)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["release_manifest_published_at_matches_release_channel"] is False
    assert "/downloads RELEASE_CHANNEL publishedAt does not match release channel" in payload["failures"]


def test_main_keeps_legacy_no_sha_served_posture_comparison_strict(tmp_path) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_bound_preview_manifest(release_channel)
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    public_manifest.write_bytes(release_channel.read_bytes())
    output = tmp_path / "DOWNLOADS_VERSION_MARKER.generated.json"
    server, thread, base_url = with_server(
        include_marker=True,
        status_heading="Preview downloads",
        release_version="run-20260713-123603",
        release_channel="preview",
        release_supportability_state="review_required",
        release_rollout_state="public_release_review_required",
        release_supportability_summary="Treat this preview as review-required while proof receipts are checked.",
        release_known_issue_summary="Known issue: preview proof receipts remain under review.",
        release_fix_availability_summary="Use the preview shelf while review remains active.",
        release_published_at="2026-07-13T11:34:17Z",
        release_proof_freshness_status="stale",
        release_public_trust_supportability_state="review_required",
        release_public_trust_rollout_state="public_release_review_required",
        release_registry_supportability_state="review_required",
        release_registry_rollout_state="public_release_review_required",
    )
    try:
        exit_code = module.main(
            [
                "--source-root",
                str(REPO_ROOT),
                "--base-url",
                base_url,
                "--release-channel-receipt",
                str(release_channel),
                "--public-release-manifest",
                str(public_manifest),
                "--output",
                str(output),
            ]
        )
    finally:
        close_server(server, thread)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["release_channel_receipt_binding_status"] == "not_requested"
    assert payload["release_manifest_supportability_matches_release_channel"] is False
    assert payload["release_manifest_supportability_compatible_with_release_channel"] is False
    assert payload["release_manifest_conservative_review_floor_applied"] is False


def test_rollout_vocabulary_is_closed_and_preserves_every_recognized_blocker() -> None:
    module = load_module()

    assert module.RELEASE_CHANNEL_POSITIVE_ROLLOUT_STATES == {
        "promoted_preview",
        "public_stable",
    }
    assert module.RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES == (
        module.RELEASE_CHANNEL_POSITIVE_ROLLOUT_STATES
        | module.RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES
    )
    for rollout_state in module.RELEASE_CHANNEL_RECOGNIZED_ROLLOUT_STATES:
        _expectations, failures = module.release_channel_expectations(
            {
                "status": "published",
                "version": "run-20260713-123603",
                "channel": "preview",
                "supportabilityState": "preview_supported",
                "rolloutState": rollout_state,
            },
            require_launch_supported=False,
        )
        assert f"release channel rolloutState is unsupported: {rollout_state}" not in failures

    for rollout_state in module.RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES:
        assert module.conservative_rollout_floor(
            rollout_state,
            module.RELEASE_CHANNEL_REVIEW_ROLLOUT_STATE,
        ) == rollout_state

    unknown_rollout = "future_optimistic_projection"
    _expectations, failures = module.release_channel_expectations(
        {
            "status": "published",
            "version": "run-20260713-123603",
            "channel": "preview",
            "supportabilityState": "preview_supported",
            "rolloutState": unknown_rollout,
        },
        require_launch_supported=False,
    )
    assert f"release channel rolloutState is unsupported: {unknown_rollout}" in failures
    assert module.conservative_rollout_floor(
        unknown_rollout,
        module.RELEASE_CHANNEL_REVIEW_ROLLOUT_STATE,
    ) == ""


def test_conservative_review_floor_preserves_recognized_blockers_and_rejects_unknown() -> None:
    module = load_module()

    def served_manifest(rollout_state: str) -> dict[str, Any]:
        return {
            "supportabilityState": "review_required",
            "rolloutState": rollout_state,
            "publicTrustMetrics": {
                "proofFreshness": {"status": "stale"},
                "releaseChannel": {
                    "supportabilityState": "review_required",
                    "rolloutState": rollout_state,
                },
            },
            "registryBoundaryCoverage": {
                "releaseChannel": {
                    "supportabilityState": "review_required",
                    "rolloutState": rollout_state,
                },
            },
        }

    def expected_posture(rollout_state: str) -> dict[str, str]:
        return {
            "supportability_state": "preview_supported",
            "rollout_state": rollout_state,
            "proof_freshness_status": "stale",
            "public_trust_supportability_state": "preview_supported",
            "public_trust_rollout_state": rollout_state,
            "registry_supportability_state": "preview_supported",
            "registry_rollout_state": rollout_state,
        }

    for rollout_state in module.RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES:
        compatibility = module.served_posture_compatibility(
            served_manifest(rollout_state),
            expected_posture(rollout_state),
            release_channel_receipt_sha256_bound=True,
        )
        assert compatibility["conservative_review_floor_valid"] is True
        assert compatibility["effective_review_rollout_state"] == rollout_state

    unknown_rollout = "future_optimistic_projection"
    compatibility = module.served_posture_compatibility(
        served_manifest(unknown_rollout),
        expected_posture(unknown_rollout),
        release_channel_receipt_sha256_bound=True,
    )
    assert compatibility["conservative_review_floor_valid"] is False
    assert compatibility["supportability_compatible"] is False
    assert compatibility["effective_review_rollout_state"] == ""


def test_sha_bound_static_public_manifest_requires_authority_identity_and_consistent_aliases(
    tmp_path: Path,
) -> None:
    module = load_module()
    selected_manifest = tmp_path / "selected-RELEASE_CHANNEL.generated.json"
    write_bound_preview_manifest(selected_manifest)
    selected_payload = json.loads(selected_manifest.read_text(encoding="utf-8"))
    expected, expectation_failures = module.release_channel_expectations(
        selected_payload,
        require_bound_contract=True,
        require_published_at=True,
    )
    assert expectation_failures == []

    cases = (
        (
            "missing-contract",
            lambda payload: payload.pop("contractName"),
            "public release manifest contractName is missing for SHA-256-bound verification",
        ),
        (
            "wrong-contract",
            lambda payload: payload.__setitem__("contractName", "Unrelated.Release.Contract"),
            "public release manifest contractName is unsupported for SHA-256-bound verification",
        ),
        (
            "contract-alias-conflict",
            lambda payload: payload.__setitem__("contract_name", "Unrelated.Release.Contract"),
            "public release manifest contractName aliases conflict for SHA-256-bound verification",
        ),
        (
            "top-level-alias-conflict",
            lambda payload: payload.__setitem__("rollout_state", "public_stable"),
            "public release manifest rolloutState aliases conflict for SHA-256-bound verification",
        ),
        (
            "nested-alias-conflict",
            lambda payload: payload["publicTrustMetrics"]["releaseChannel"].__setitem__(
                "supportability_state",
                "gold_supported",
            ),
            "public release manifest publicTrustMetrics release-channel supportabilityState aliases conflict for SHA-256-bound verification",
        ),
    )
    for case_name, mutate, expected_failure in cases:
        public_manifest = tmp_path / f"{case_name}.json"
        public_payload = json.loads(json.dumps(selected_payload))
        mutate(public_payload)
        public_manifest.write_text(json.dumps(public_payload), encoding="utf-8")

        result, failures = module.verify_public_release_manifest(
            public_manifest,
            expected,
            release_channel_receipt_sha256_bound=True,
        )

        assert expected_failure in failures
        assert result["release_channel_receipt_sha256_bound"] is True
        if "alias-conflict" in case_name:
            assert result["public_release_aliases_consistent"] is False


def test_sha_bound_live_manifest_requires_authority_identity_and_consistent_aliases(
    tmp_path: Path,
) -> None:
    module = load_module()
    release_channel = tmp_path / "RELEASE_CHANNEL.generated.json"
    expected_sha256 = write_bound_preview_manifest(release_channel)
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    public_manifest.write_bytes(release_channel.read_bytes())

    cases = (
        (
            "missing-contract",
            {"release_contract_name": None},
            "/downloads RELEASE_CHANNEL contractName is missing for SHA-256-bound verification",
        ),
        (
            "wrong-contract",
            {"release_contract_name": "Unrelated.Release.Contract"},
            "/downloads RELEASE_CHANNEL contractName is unsupported for SHA-256-bound verification",
        ),
        (
            "contract-alias-conflict",
            {"release_manifest_overrides": {"contract_name": "Unrelated.Release.Contract"}},
            "/downloads RELEASE_CHANNEL contractName aliases conflict for SHA-256-bound verification",
        ),
        (
            "top-level-alias-conflict",
            {"release_manifest_overrides": {"rollout_state": "promoted_preview"}},
            "/downloads RELEASE_CHANNEL rolloutState aliases conflict for SHA-256-bound verification",
        ),
        (
            "nested-alias-conflict",
            {
                "release_manifest_overrides": {
                    "publicTrustMetrics": {
                        "proofFreshness": {"status": "stale"},
                        "releaseChannel": {
                            "supportabilityState": "review_required",
                            "supportability_state": "preview_supported",
                            "rolloutState": "public_release_review_required",
                        },
                    }
                }
            },
            "/downloads RELEASE_CHANNEL publicTrustMetrics release-channel supportabilityState aliases conflict for SHA-256-bound verification",
        ),
    )
    for case_name, server_overrides, expected_failure in cases:
        output = tmp_path / f"{case_name}.generated.json"
        server, thread, base_url = with_server(
            include_marker=True,
            status_heading="Preview downloads",
            release_version="run-20260713-123603",
            release_channel="preview",
            release_supportability_state="review_required",
            release_rollout_state="public_release_review_required",
            release_supportability_summary="Treat this preview as review-required while proof receipts are checked.",
            release_known_issue_summary="Known issue: preview proof receipts remain under review.",
            release_fix_availability_summary="Use the preview shelf while review remains active.",
            release_published_at="2026-07-13T11:34:17Z",
            release_proof_freshness_status="stale",
            release_public_trust_supportability_state="review_required",
            release_public_trust_rollout_state="public_release_review_required",
            release_registry_supportability_state="review_required",
            release_registry_rollout_state="public_release_review_required",
            **server_overrides,
        )
        try:
            exit_code = module.main(
                [
                    "--source-root",
                    str(REPO_ROOT),
                    "--base-url",
                    base_url,
                    "--release-channel-receipt",
                    str(release_channel),
                    "--release-channel-receipt-sha256",
                    expected_sha256,
                    "--public-release-manifest",
                    str(public_manifest),
                    "--output",
                    str(output),
                ]
            )
        finally:
            close_server(server, thread)

        payload = json.loads(output.read_text(encoding="utf-8"))
        assert exit_code == 1
        assert expected_failure in payload["failures"]
        assert payload["release_channel_receipt_sha256_matches"] is True
        if "alias-conflict" in case_name:
            assert payload["release_manifest_aliases_consistent"] is False


def test_static_and_live_manifest_rollout_vocabulary_rejects_unknown_tokens(
    tmp_path: Path,
) -> None:
    module = load_module()
    unknown_rollout = "future_optimistic_projection"
    public_manifest = tmp_path / "public-RELEASE_CHANNEL.generated.json"
    write_release_manifest(public_manifest, rolloutState=unknown_rollout)
    expected = {
        "status": "published",
        "version": "run-20260630",
        "channel": "public_stable",
        "supportability_state": "gold_supported",
        "rollout_state": unknown_rollout,
    }

    _result, public_failures = module.verify_public_release_manifest(
        public_manifest,
        expected,
    )
    assert (
        f"public release manifest rolloutState is unsupported: {unknown_rollout}"
        in public_failures
    )

    server, thread, base_url = with_server(
        include_marker=True,
        release_rollout_state=unknown_rollout,
    )
    try:
        _result, live_failures = module.verify_live(
            base_url,
            timeout=5,
            expected_release_status="published",
            expected_release_version="run-20260630",
            expected_release_channel="public_stable",
            expected_supportability_state="gold_supported",
            expected_rollout_state=unknown_rollout,
        )
    finally:
        close_server(server, thread)
    assert (
        f"/downloads RELEASE_CHANNEL rolloutState is unsupported: {unknown_rollout}"
        in live_failures
    )
