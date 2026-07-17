from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "sync_important_work_to_teable.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sync_important_work_to_teable", MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def clear_local_env_cache(module) -> None:
    module.local_env_assignments.cache_clear()


def seed_shared_render_lane(
    root: Path,
    *,
    include_propertyquarry_bridge: bool = True,
    include_internal_controller: bool = True,
    include_signed_in_route: bool = True,
) -> None:
    (root / "Chummer.Run.Api/Services/Community").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api/Services").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api/Controllers").mkdir(parents=True, exist_ok=True)
    (root / "Chummer.Run.Api/Services/Community/HorizonGovernedRenderRequestComposerService.cs").write_text(
        "\n".join(
            [
                'public const string OrchestrationLane = "ea_governed_render";',
                'public const string ContractName = "chummer6-hub.horizon_governed_render_request.v1";',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "Chummer.Run.Api/Services/RunsiteOrientationArtifactRequestBridgeService.cs").write_text(
        "\n".join(
            [
                'private const string DefaultPreferredProvider = "magicai";',
                'ArtifactKindOrCapabilityId: "runsite-scene-render"',
                "GovernedRenderRequest: new HorizonGovernedRenderRequestCreateRequest(",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if include_propertyquarry_bridge:
        (root / "Chummer.Run.Api/Services/PropertyquarryApartmentVideoArtifactRequestBridgeService.cs").write_text(
            "\n".join(
                [
                    'private const string DefaultPreferredProvider = "magicai";',
                    'ArtifactKindOrCapabilityId: "propertyquarry-apartment-video"',
                    "GovernedRenderRequest: new HorizonGovernedRenderRequestCreateRequest(",
                    "propertyquarry:property-packet",
                    "propertyquarry:property-continuity",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    if include_internal_controller:
        (root / "Chummer.Run.Api/Controllers/InternalPropertyquarryApartmentVideoController.cs").write_text(
            "\n".join(
                [
                    '[HttpPost("/api/internal/propertyquarry/apartment-videos/requests")]',
                    '[HttpPost("/api/internal/propertyquarry/apartment-videos/artifact-requests")]',
                    "PropertyquarryApartmentVideoArtifactRequestBridgeResult",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    if include_signed_in_route:
        (root / "Chummer.Run.Api/Controllers/CampaignSpineController.cs").write_text(
            "\n".join(
                [
                    '[HttpPost("me/property-workspaces/{propertyId}/apartment-video")]',
                    "PropertyquarryApartmentVideoRequest",
                    "BuildPropertyquarryApartmentVideoLane(property)",
                    "apartmentVideoRequestApiHrefTemplate",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def test_projection_contains_unique_important_work_rows():
    module = load_module()

    rows = module.important_work_items()
    item_ids = [row.item_id for row in rows]

    assert len(rows) >= 38
    assert len(item_ids) == len(set(item_ids))
    assert "desktop-premium-ui-polish" in item_ids
    assert "origin-dossier-first-story" in item_ids
    assert "origin-dossier-humanizer-loop" in item_ids
    assert "desktop-updater-install-link" in item_ids
    assert "public-website-minimal-redesign" in item_ids
    assert "public-proof-language-removal" in item_ids
    assert "public-help-accessibility-polish" in item_ids
    assert "character-builder-core-usability" in item_ids
    assert "release-policy-daily-08" in item_ids
    assert "reproducible-gold-proof-chain" in item_ids
    assert "shadowrun-data-files-completeness" in item_ids
    assert "table-pulse-remote-loop" in item_ids
    assert "minimal-seo-optimization" in item_ids
    assert "joggai-consented-avatar-video-lane" in item_ids
    assert "sendr-black-ledger-outreach-lane" in item_ids
    assert "code-quality-specialization-pass" in item_ids
    assert "teable-important-work-sync" in item_ids
    assert "teable-maintenance-not-horizon" in item_ids
    sendr = next(row for row in rows if row.item_id == "sendr-black-ledger-outreach-lane")
    assert "provider-lane contract" in sendr.next_action
    assert "provider-lane metadata" in sendr.acceptance_gate
    origin_story = next(row for row in rows if row.item_id == "origin-dossier-first-story")
    assert "ebook with fitting cover art first" in origin_story.next_action
    assert "exactly three story-fit portraits" in origin_story.next_action
    assert "voice-choice audiobook" in origin_story.acceptance_gate
    assert "ebook with fitting cover art first" in origin_story.acceptance_gate
    assert "character-visible render" in origin_story.acceptance_gate
    origin_humanizer = next(row for row in rows if row.item_id == "origin-dossier-humanizer-loop")
    assert "Subscribr-authored full story" in origin_humanizer.acceptance_gate
    assert "three story-fit portraits" in origin_humanizer.acceptance_gate


def test_windows_installer_rows_track_visual_audit_digest_mismatch(tmp_path):
    module = load_module()
    promoted_sha = "d9d25b2c93dbd4887590b52b03431c4aba3c5614dbc4b18ec2f282222067466c"
    stale_sha = "c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b"
    published = tmp_path / ".codex-studio" / "published"
    published.mkdir(parents=True)
    (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
        json.dumps(
            {
                "status": "fail",
                "artifact": {"sha256": promoted_sha, "actualSha256": promoted_sha},
                "visualAuditSource": {
                    "artifactSha256": stale_sha,
                    "artifactDigestMatchesPromoted": False,
                    "requiresRecapture": True,
                },
                "failures": [
                    "Windows installer visual audit source digest does not match promoted installer",
                ],
            }
        ),
        encoding="utf-8",
    )

    rows = module.important_work_items(tmp_path)
    premium = next(row for row in rows if row.item_id == "windows-installer-premium")
    current = next(row for row in rows if row.item_id == "windows-installer-current-shelf-proof")

    for row in (premium, current):
        assert row.status == "native-visual-recapture-needed"
        assert row.cadence == "now; before release-ready"
        assert promoted_sha in row.next_action
        assert (
            "import_windows_installer_gold_proof_artifact.py --intake-request "
            ".codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --verify"
            in row.next_action
        )
        assert "full post-import gate chain" in row.next_action
        assert promoted_sha in row.acceptance_gate
        assert "final-gold no longer fails" in row.acceptance_gate
        assert "next scheduled" not in row.next_action.lower()


def test_windows_installer_rows_track_passing_visual_audit(tmp_path):
    module = load_module()
    published = tmp_path / ".codex-studio" / "published"
    published.mkdir(parents=True)
    (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "artifact": {"sha256": "a" * 64, "actualSha256": "a" * 64},
                "source_digest_matches_promoted": True,
                "startupReceipt": {
                    "status": "pass",
                    "artifactDigestMatchesPromoted": True,
                },
                "visualAuditSource": {
                    "status": "pass",
                    "artifactSha256": "a" * 64,
                    "artifactDigestMatchesPromoted": True,
                    "requiresRecapture": False,
                },
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    rows = module.important_work_items(tmp_path)
    premium = next(row for row in rows if row.item_id == "windows-installer-premium")
    current = next(row for row in rows if row.item_id == "windows-installer-current-shelf-proof")

    assert premium.status == "current-shelf-visual-proof-pass"
    assert current.status == "current-shelf-visual-proof-pass"
    assert "Keep the native Windows visual audit refreshed" in current.next_action


def test_windows_installer_rows_reject_pass_shaped_visual_audit_with_nested_digest_mismatch(tmp_path):
    module = load_module()
    promoted_sha = "a" * 64
    stale_sha = "b" * 64
    published = tmp_path / ".codex-studio" / "published"
    published.mkdir(parents=True)
    (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "artifact": {"sha256": promoted_sha, "actualSha256": promoted_sha},
                "source_digest_matches_promoted": False,
                "startupReceipt": {
                    "status": "pass",
                    "artifactDigestMatchesPromoted": True,
                },
                "visualAuditSource": {
                    "status": "pass",
                    "artifactSha256": stale_sha,
                    "artifactDigestMatchesPromoted": False,
                    "requiresRecapture": True,
                },
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    rows = module.important_work_items(tmp_path)
    premium = next(row for row in rows if row.item_id == "windows-installer-premium")
    current = next(row for row in rows if row.item_id == "windows-installer-current-shelf-proof")

    for row in (premium, current):
        assert row.status == "native-visual-recapture-needed"
        assert promoted_sha in row.next_action
        assert "current-shelf-visual-proof-pass" not in row.status
        assert promoted_sha in row.acceptance_gate


def test_projection_rows_have_teable_ready_fields():
    module = load_module()

    payload = module.build_projection()

    assert payload["contract_name"] == "chummer.teable_important_work.v1"
    assert payload["status"] == "ready"
    assert payload["row_count"] == len(payload["rows"])
    assert payload["summary"]["priority_counts"]["P0"] >= 10
    for row in payload["rows"]:
        assert row["item_id"]
        assert row["title"]
        assert row["area"]
        assert row["priority"] in {"P0", "P1", "P2"}
        assert row["why_it_matters"]
        assert row["next_action"]
        assert row["acceptance_gate"]


def test_origin_visuals_magicai_row_tracks_login_only_pool_until_api_keys_exist(tmp_path):
    module = load_module()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MAGICAI_ACCOUNT_01_EMAIL=one@example.test",
                "MAGICAI_ACCOUNT_01_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_02_EMAIL=two@example.test",
                "MAGICAI_ACCOUNT_02_PASSWORD=shared-password",
                "",
            ]
        ),
        encoding="utf-8",
    )
    seed_shared_render_lane(tmp_path)

    runtime = module.origin_visuals_magicai_runtime(tmp_path)
    rows = module.important_work_items(tmp_path)
    item = next(row for row in rows if row.item_id == "origin-visuals-magicfit-runsite-magicai")

    assert runtime["status"] == "live-gold-pass-api-keys-pending"
    assert "2 of 2 declared login-ready pool slots" in runtime["next_action"]
    assert item.status == "live-gold-pass-api-keys-pending"
    assert "2 of 2 declared login-ready pool slots" in item.next_action


def test_origin_visuals_magicai_row_tracks_ready_pool_when_api_keys_exist(tmp_path):
    module = load_module()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MAGICAI_ACCOUNT_01_EMAIL=one@example.test",
                "MAGICAI_ACCOUNT_01_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_01_API_KEY=api-key-one",
                "",
            ]
        ),
        encoding="utf-8",
    )
    seed_shared_render_lane(tmp_path)

    runtime = module.origin_visuals_magicai_runtime(tmp_path)

    assert runtime["status"] == "live-gold-pass-render-lane-ready"
    assert "remaining MagicAI/omagic API keys for 0 of 1 declared login-ready pool slots" in runtime["next_action"]
    assert "Runsite and Propertyquarry via internal EA skills" in runtime["next_action"]


def test_origin_visuals_magicai_row_uses_live_platform_audit_when_present(tmp_path):
    module = load_module()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MAGICAI_ACCOUNT_02_EMAIL=two@example.test",
                "MAGICAI_ACCOUNT_02_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_03_EMAIL=three@example.test",
                "MAGICAI_ACCOUNT_03_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_04_EMAIL=four@example.test",
                "MAGICAI_ACCOUNT_04_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_05_EMAIL=five@example.test",
                "MAGICAI_ACCOUNT_05_PASSWORD=shared-password",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / ".codex-studio/published").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".codex-studio/published/MAGICAI_PLATFORM_ACCESS.generated.json").write_text(
        json.dumps(
            {
                "checked_at_utc": "2026-06-30T18:42:00Z",
                "slots": [
                    {"slot": "02", "keys_status": "forbidden", "logged_in": True},
                    {"slot": "03", "keys_status": "ok", "logged_in": True},
                    {"slot": "04", "keys_status": "login_failed", "logged_in": False},
                    {"slot": "05", "keys_status": "unverified", "logged_in": True},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    seed_shared_render_lane(tmp_path)

    audit = module.magicai_platform_audit(tmp_path)
    runtime = module.origin_visuals_magicai_runtime(tmp_path)

    assert audit["attempted"] is True
    assert audit["pending_mintable_aliases"] == ["03"]
    assert audit["pending_blocked_aliases"] == ["02"]
    assert audit["pending_login_failed_aliases"] == ["04"]
    assert audit["pending_unverified_aliases"] == ["05"]
    assert runtime["status"] == "live-gold-pass-api-keys-pending"
    assert "remaining MagicAI/omagic API keys for 1 mintable slot" in runtime["next_action"]
    assert "1 slot is currently API-forbidden" in runtime["next_action"]
    assert "1 slot currently fails platform login" in runtime["next_action"]
    assert "1 slot still needs a fresh live probe" in runtime["next_action"]


def test_origin_visuals_magicai_row_blocks_when_live_audit_has_no_mintable_slots(tmp_path):
    module = load_module()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MAGICAI_ACCOUNT_02_EMAIL=two@example.test",
                "MAGICAI_ACCOUNT_02_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_09_EMAIL=nine@example.test",
                "MAGICAI_ACCOUNT_09_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_03_EMAIL=three@example.test",
                "MAGICAI_ACCOUNT_03_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_03_API_KEY=api-key-three",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / ".codex-studio/published").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".codex-studio/published/MAGICAI_PLATFORM_ACCESS.generated.json").write_text(
        json.dumps(
            {
                "checked_at_utc": "2026-06-30T18:42:00Z",
                "slots": [
                    {"slot": "02", "keys_status": "forbidden", "logged_in": True},
                    {"slot": "03", "keys_status": "ok", "logged_in": True},
                    {"slot": "09", "keys_status": "login_failed", "logged_in": False},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    seed_shared_render_lane(tmp_path)

    audit = module.magicai_platform_audit(tmp_path)
    runtime = module.origin_visuals_magicai_runtime(tmp_path)

    assert audit["pending_mintable_aliases"] == []
    assert audit["pending_blocked_aliases"] == ["02"]
    assert audit["pending_login_failed_aliases"] == ["09"]
    assert runtime["status"] == "live-gold-pass-api-key-path-blocked"
    assert "clear the remaining MagicAI/omagic API key path blockers" in runtime["next_action"]
    assert "1 slot is currently API-forbidden" in runtime["next_action"]
    assert "1 slot currently fails platform login" in runtime["next_action"]


def test_origin_visuals_magicai_row_surfaces_origin_gold_ready_with_remaining_account_blockers(tmp_path):
    module = load_module()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MAGICAI_ACCOUNT_02_EMAIL=two@example.test",
                "MAGICAI_ACCOUNT_02_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_09_EMAIL=nine@example.test",
                "MAGICAI_ACCOUNT_09_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_03_EMAIL=three@example.test",
                "MAGICAI_ACCOUNT_03_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_03_API_KEY=api-key-three",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / ".codex-studio/published").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".codex-studio/published/MAGICAI_PLATFORM_ACCESS.generated.json").write_text(
        json.dumps(
            {
                "checked_at_utc": "2026-06-30T18:42:00Z",
                "slots": [
                    {"slot": "02", "keys_status": "forbidden", "logged_in": True},
                    {"slot": "03", "keys_status": "ok", "logged_in": True},
                    {"slot": "09", "keys_status": "login_failed", "logged_in": False},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    proof_root = tmp_path / ".tmp/origin-dossier-fresh-gold"
    proof_root.mkdir(parents=True)
    (proof_root / "ORIGIN_EDITION_GOLD_PROOF_CHAIN.generated.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "finalVerdict": "ORIGIN_EDITION_GOLD_READY",
                "goalCompletionClaimAllowed": True,
                "progress": {"passedStages": 10, "totalStages": 10},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    seed_shared_render_lane(tmp_path)

    runtime = module.origin_visuals_magicai_runtime(tmp_path)

    assert runtime["status"] == "origin-gold-ready-api-key-path-blocked"
    assert "Origin Dossier Gold is ready (10/10 proof stages)" in runtime["next_action"]
    assert "clear the remaining MagicAI/omagic API key path blockers" in runtime["next_action"]


def test_origin_visuals_magicai_row_keeps_render_lane_pending_until_propertyquarry_bridge_exists(tmp_path):
    module = load_module()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MAGICAI_ACCOUNT_01_EMAIL=one@example.test",
                "MAGICAI_ACCOUNT_01_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_01_API_KEY=api-key-one",
                "",
            ]
        ),
        encoding="utf-8",
    )
    seed_shared_render_lane(tmp_path, include_propertyquarry_bridge=False, include_internal_controller=False, include_signed_in_route=False)

    runtime = module.origin_visuals_magicai_runtime(tmp_path)

    assert runtime["status"] == "live-gold-pass-render-lane-pending"
    assert "shared EA render lane is still being wired" in runtime["next_action"]


def test_render_lane_readiness_requires_propertyquarry_request_surfaces(tmp_path):
    module = load_module()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MAGICAI_ACCOUNT_01_EMAIL=one@example.test",
                "MAGICAI_ACCOUNT_01_PASSWORD=shared-password",
                "MAGICAI_ACCOUNT_01_API_KEY=api-key-one",
                "",
            ]
        ),
        encoding="utf-8",
    )
    seed_shared_render_lane(tmp_path, include_internal_controller=False, include_signed_in_route=False)

    readiness = module.render_lane_readiness(tmp_path)
    runtime = module.origin_visuals_magicai_runtime(tmp_path)

    assert readiness["governed_render_contract"] is True
    assert readiness["runsite_bridge"] is True
    assert readiness["propertyquarry_bridge"] is True
    assert readiness["propertyquarry_internal_controller"] is False
    assert readiness["propertyquarry_signed_in_route"] is False
    assert runtime["status"] == "live-gold-pass-render-lane-pending"


def test_teable_field_definition_omits_unsupported_validation_flags():
    module = load_module()

    field = module.teable_field_definition({"name": "Item Id", "type": "singleLineText", "unique": True, "notNull": True})

    assert field == {"name": "Item Id", "type": "singleLineText", "description": ""}


def test_main_writes_dry_run_artifact_without_teable_credentials(tmp_path, monkeypatch):
    module = load_module()
    output = tmp_path / "TEABLE_IMPORTANT_WORK.generated.json"
    csv_output = output.with_suffix(".csv")
    monkeypatch.delenv("TEABLE_API_KEY", raising=False)
    monkeypatch.delenv("CHUMMER_TEABLE_IMPORTANT_WORK_API_KEY", raising=False)

    exit_code = module.main(["--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["sync"]["state"] == "not_requested"
    assert payload["sync"]["attempted"] is False
    rows = list(csv.DictReader(csv_output.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == payload["row_count"]
    assert rows[0]["Item Id"]
    assert rows[0]["Title"]
    assert rows[0]["Acceptance Gate"]


def test_sync_without_credentials_fails_closed_without_token_text():
    module = load_module()

    result = module.sync_to_teable(
        api_key=None,
        api_base_url="https://app.teable.ai/api",
        base_id="base-demo",
        table_id="tbl-demo",
        table_name="Chummer Important Work",
        request_timeout_seconds=module.DEFAULT_HTTP_TIMEOUT_SECONDS,
        sync_deadline_seconds=module.DEFAULT_SYNC_DEADLINE_SECONDS,
    )

    assert result["state"] == "blocked"
    assert result["errors"] == ["teable_api_key_missing"]
    assert "Bearer" not in json.dumps(result)


def test_seed_hub_without_internal_token_fails_closed_without_token_text():
    module = load_module()

    result = module.seed_hub_store(
        hub_base_url="https://chummer.run",
        hub_token=None,
        request_timeout_seconds=module.DEFAULT_HTTP_TIMEOUT_SECONDS,
    )

    assert result["state"] == "blocked"
    assert result["errors"] == ["hub_internal_token_missing"]
    assert "Bearer" not in json.dumps(result)


def test_seed_hub_posts_every_important_work_item(monkeypatch):
    module = load_module()
    requests: list[tuple[str, str, str, dict | None]] = []

    def fake_send_hub_json(method: str, url: str, token: str, payload: dict | None = None, timeout: float | None = None, **kwargs):
        requests.append((method, url, token, payload))
        return {"itemId": payload["itemId"]}

    monkeypatch.setattr(module, "send_hub_json", fake_send_hub_json)

    result = module.seed_hub_store(
        hub_base_url="https://chummer.run/",
        hub_token="internal-token",
        request_timeout_seconds=module.DEFAULT_HTTP_TIMEOUT_SECONDS,
    )

    assert result["state"] == "passed"
    assert result["recorded_count"] == len(module.important_work_items())
    assert result["failed_count"] == 0
    assert len(requests) == len(module.important_work_items())
    method, url, token, payload = requests[0]
    assert method == "POST"
    assert url == "https://chummer.run/api/internal/community/important-work"
    assert token == "internal-token"
    assert payload["scope"] == "chummer.run"
    assert payload["summary"]
    assert "Acceptance gate:" in payload["detail"]


def test_send_json_uses_teable_compatible_headers(monkeypatch):
    module = load_module()
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    module.send_json("GET", "https://app.teable.ai/api/base/base-demo/table", "demo-token")

    request = captured["request"]
    assert request.get_header("Authorization") == "Bearer demo-token"
    assert request.get_header("Accept") == "application/json, text/plain, */*"
    assert request.get_header("Origin") == "https://app.teable.ai"
    assert request.get_header("Referer") == "https://app.teable.ai/"
    assert request.get_header("User-agent") == "Mozilla/5.0"
    assert captured["timeout"] == module.DEFAULT_HTTP_TIMEOUT_SECONDS


def test_send_json_classifies_malformed_provider_response_as_ambiguous(monkeypatch):
    module = load_module()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"not-json"

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda request, timeout: FakeResponse())

    try:
        module.send_json("POST", "https://app.teable.ai/api/table/tbl/record", "demo-token", {})
    except RuntimeError as exc:
        assert str(exc) == "teable_invalid_json_response"
        assert module.is_transient_teable_error(exc) is True
    else:
        raise AssertionError("malformed Teable response should fail closed")


def test_transient_teable_error_classification_is_fail_closed():
    module = load_module()

    assert module.is_transient_teable_error(RuntimeError("The read operation timed out")) is True
    assert module.is_transient_teable_error(RuntimeError("teable_http_503:busy")) is True
    assert module.is_transient_teable_error(RuntimeError("teable_batch_create_count_mismatch:10")) is True
    assert module.is_transient_teable_error(RuntimeError("teable_http_400:invalid")) is False
    assert module.is_transient_teable_error(RuntimeError("teable_sync_deadline_exceeded")) is False


def test_resolve_api_base_url_accepts_teable_base_url(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "env_assignments", lambda path: {})
    clear_local_env_cache(module)
    monkeypatch.delenv("CHUMMER_TEABLE_IMPORTANT_WORK_API_BASE_URL", raising=False)
    monkeypatch.delenv("TEABLE_API_BASE_URL", raising=False)
    monkeypatch.setenv("TEABLE_BASE_URL", "https://app.teable.ai")

    assert module.resolve_api_base_url() == "https://app.teable.ai/api"


def test_parse_args_ignores_ea_teable_base_fallback(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "env_assignments", lambda path: {})
    clear_local_env_cache(module)
    monkeypatch.delenv("CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID", raising=False)
    monkeypatch.setenv("EA_ENV_TEABLE_BASE_ID", "base-ea")

    args = module.parse_args([])

    assert args.base_id is None


def test_parse_args_falls_back_to_local_env_assignments(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "env_assignments",
        lambda path: {
            "TEABLE_API_KEY": "dotenv-token",
            "CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID": "base-dotenv",
            "CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID": "tbl-dotenv",
            "CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_NAME": "Dotenv Important Work",
            "TEABLE_BASE_URL": "https://teable.example.test",
        },
    )
    clear_local_env_cache(module)
    monkeypatch.delenv("TEABLE_API_KEY", raising=False)
    monkeypatch.delenv("CHUMMER_TEABLE_IMPORTANT_WORK_API_KEY", raising=False)
    monkeypatch.delenv("CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID", raising=False)
    monkeypatch.delenv("CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID", raising=False)
    monkeypatch.delenv("CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_NAME", raising=False)
    monkeypatch.delenv("TEABLE_BASE_URL", raising=False)

    args = module.parse_args([])

    assert args.api_key == "dotenv-token"
    assert args.base_id == "base-dotenv"
    assert args.table_id == "tbl-dotenv"
    assert args.table_name == "Dotenv Important Work"
    assert args.api_base_url == "https://teable.example.test/api"


def test_parse_args_uses_teable_timeout_defaults(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "env_assignments", lambda path: {})
    clear_local_env_cache(module)
    monkeypatch.setenv("CHUMMER_TEABLE_HTTP_TIMEOUT_SECONDS", "9")
    monkeypatch.setenv("CHUMMER_TEABLE_IMPORTANT_WORK_SYNC_DEADLINE_SECONDS", "45")

    args = module.parse_args([])

    assert args.request_timeout_seconds == 9
    assert args.sync_deadline_seconds == 45


def test_sync_setup_failure_writes_failed_state_without_token(monkeypatch):
    module = load_module()

    def fail_setup(*args, **kwargs):
        raise RuntimeError("teable_http_403:blocked")

    monkeypatch.setattr(module, "resolve_or_create_table", fail_setup)

    result = module.sync_to_teable(
        api_key="demo-token",
        api_base_url="https://app.teable.ai/api",
        base_id="base-demo",
        table_id=None,
        table_name="Chummer Important Work",
        request_timeout_seconds=module.DEFAULT_HTTP_TIMEOUT_SECONDS,
        sync_deadline_seconds=module.DEFAULT_SYNC_DEADLINE_SECONDS,
    )

    assert result["state"] == "failed"
    assert result["failed_count"] == len(module.important_work_items())
    assert result["errors"] == ["teable_setup:teable_http_403:blocked"]
    assert "demo-token" not in json.dumps(result)


def test_sync_to_teable_stops_after_deadline(monkeypatch):
    module = load_module()
    items = [
        module.ImportantWorkItem("item-1", "Item 1", "Ops", "P0", "active", "daily", "test", "why", "next", "gate"),
        module.ImportantWorkItem("item-2", "Item 2", "Ops", "P0", "active", "daily", "test", "why", "next", "gate"),
    ]
    monotonic_values = iter([0.0, 0.0, 2.0])

    monkeypatch.setattr(module, "important_work_items", lambda repo_root=module.RUN_SERVICES_ROOT: items)
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module,
        "existing_record_ids_by_item_id",
        lambda *args, **kwargs: {"item-1": "rec-1", "item-2": "rec-2"},
    )
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))

    result = module.sync_to_teable(
        api_key="demo-token",
        api_base_url="https://app.teable.ai/api",
        base_id=None,
        table_id="tbl-work",
        table_name="Chummer Important Work",
        request_timeout_seconds=15,
        sync_deadline_seconds=1,
    )

    assert result["state"] == "failed"
    assert result["deadline_exceeded"] is True
    assert result["synced_count"] == 0
    assert result["created_count"] == 0
    assert result["updated_count"] == 0
    assert result["failed_count"] == 2
    assert result["last_item_id"] == "item-2"
    assert result["errors"] == ["update:item-1..item-2:teable_sync_deadline_exceeded"]


def test_sync_to_teable_splits_large_update_sets_into_bounded_batches(monkeypatch):
    module = load_module()
    items = [
        module.ImportantWorkItem(
            f"item-{index:02d}",
            f"Item {index:02d}",
            "Ops",
            "P0",
            "active",
            "daily",
            "test",
            "why",
            "next",
            "gate",
        )
        for index in range(25)
    ]
    batch_item_ids: list[list[str]] = []

    monkeypatch.setattr(module, "important_work_items", lambda repo_root=module.RUN_SERVICES_ROOT: items)
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module,
        "existing_record_ids_by_item_id",
        lambda *args, **kwargs: {item.item_id: f"rec-{item.item_id}" for item in items},
    )

    def fake_update_batch(*args, **kwargs):
        batch = args[3]
        batch_item_ids.append([item.item_id for item, _ in batch])
        return len(batch)

    monkeypatch.setattr(module, "update_record_batch", fake_update_batch)

    result = module.sync_to_teable(
        api_key="demo-token",
        api_base_url="https://app.teable.ai/api",
        base_id=None,
        table_id="tbl-work",
        table_name="Chummer Important Work",
        request_timeout_seconds=module.DEFAULT_HTTP_TIMEOUT_SECONDS,
        sync_deadline_seconds=module.DEFAULT_SYNC_DEADLINE_SECONDS,
        batch_size=10,
    )

    assert result["state"] == "passed"
    assert [len(batch) for batch in batch_item_ids] == [10, 10, 5]
    assert result["batch_count"] == 3
    assert result["completed_batch_count"] == 3
    assert result["retry_count"] == 0


def test_sync_to_teable_retries_transient_update_timeout(monkeypatch):
    module = load_module()
    item = module.ImportantWorkItem(
        "item-1", "Item 1", "Ops", "P0", "active", "daily", "test", "why", "next", "gate"
    )
    attempts = 0

    monkeypatch.setattr(module, "important_work_items", lambda repo_root=module.RUN_SERVICES_ROOT: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module,
        "existing_record_ids_by_item_id",
        lambda *args, **kwargs: {item.item_id: "rec-1"},
    )

    def flaky_update_batch(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("The read operation timed out")
        return len(args[3])

    monkeypatch.setattr(module, "update_record_batch", flaky_update_batch)

    result = module.sync_to_teable(
        api_key="demo-token",
        api_base_url="https://app.teable.ai/api",
        base_id=None,
        table_id="tbl-work",
        table_name="Chummer Important Work",
        request_timeout_seconds=15,
        sync_deadline_seconds=90,
        retry_backoff_seconds=0,
    )

    assert result["state"] == "passed"
    assert attempts == 2
    assert result["retry_count"] == 1
    assert result["updated_count"] == 1
    assert result["errors"] == []


def test_sync_to_teable_does_not_retry_permanent_update_failure(monkeypatch):
    module = load_module()
    item = module.ImportantWorkItem(
        "item-1", "Item 1", "Ops", "P0", "active", "daily", "test", "why", "next", "gate"
    )
    attempts = 0

    monkeypatch.setattr(module, "important_work_items", lambda repo_root=module.RUN_SERVICES_ROOT: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module,
        "existing_record_ids_by_item_id",
        lambda *args, **kwargs: {item.item_id: "rec-1"},
    )

    def rejected_update_batch(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("teable_http_400:invalid field")

    monkeypatch.setattr(module, "update_record_batch", rejected_update_batch)

    result = module.sync_to_teable(
        api_key="demo-token",
        api_base_url="https://app.teable.ai/api",
        base_id=None,
        table_id="tbl-work",
        table_name="Chummer Important Work",
        request_timeout_seconds=15,
        sync_deadline_seconds=90,
        retry_backoff_seconds=0,
    )

    assert result["state"] == "failed"
    assert attempts == 1
    assert result["retry_count"] == 0
    assert result["failed_count"] == 1
    assert result["errors"] == ["update:item-1..item-1:teable_http_400:invalid field"]


def test_sync_to_teable_reconciles_ambiguous_create_before_retry(monkeypatch):
    module = load_module()
    items = [
        module.ImportantWorkItem(
            f"item-{index}",
            f"Item {index}",
            "Ops",
            "P0",
            "active",
            "daily",
            "test",
            "why",
            "next",
            "gate",
        )
        for index in (1, 2)
    ]
    record_snapshots = iter([{}, {"item-1": "rec-1"}])
    create_batches: list[list[str]] = []

    monkeypatch.setattr(module, "important_work_items", lambda repo_root=module.RUN_SERVICES_ROOT: items)
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module,
        "existing_record_ids_by_item_id",
        lambda *args, **kwargs: next(record_snapshots),
    )

    def flaky_create_batch(*args, **kwargs):
        batch = args[3]
        create_batches.append([item.item_id for item in batch])
        if len(create_batches) == 1:
            raise RuntimeError("teable_timeout_after_15s")
        return len(batch)

    monkeypatch.setattr(module, "create_record_batch", flaky_create_batch)

    result = module.sync_to_teable(
        api_key="demo-token",
        api_base_url="https://app.teable.ai/api",
        base_id=None,
        table_id="tbl-work",
        table_name="Chummer Important Work",
        request_timeout_seconds=15,
        sync_deadline_seconds=90,
        retry_backoff_seconds=0,
    )

    assert result["state"] == "passed"
    assert create_batches == [["item-1", "item-2"], ["item-2"]]
    assert result["created_count"] == 2
    assert result["reconciled_create_count"] == 1
    assert result["retry_count"] == 1
    assert result["errors"] == []


def test_sync_to_teable_never_blindly_retries_create_when_reconciliation_fails(monkeypatch):
    module = load_module()
    item = module.ImportantWorkItem(
        "item-1", "Item 1", "Ops", "P0", "active", "daily", "test", "why", "next", "gate"
    )
    record_lookup_count = 0
    create_attempts = 0

    monkeypatch.setattr(module, "important_work_items", lambda repo_root=module.RUN_SERVICES_ROOT: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)

    def record_ids(*args, **kwargs):
        nonlocal record_lookup_count
        record_lookup_count += 1
        if record_lookup_count == 1:
            return {}
        raise RuntimeError("teable_timeout_after_15s")

    def ambiguous_create(*args, **kwargs):
        nonlocal create_attempts
        create_attempts += 1
        raise RuntimeError("teable_timeout_after_15s")

    monkeypatch.setattr(module, "existing_record_ids_by_item_id", record_ids)
    monkeypatch.setattr(module, "create_record_batch", ambiguous_create)

    result = module.sync_to_teable(
        api_key="demo-token",
        api_base_url="https://app.teable.ai/api",
        base_id=None,
        table_id="tbl-work",
        table_name="Chummer Important Work",
        request_timeout_seconds=15,
        sync_deadline_seconds=90,
        retry_backoff_seconds=0,
    )

    assert result["state"] == "failed"
    assert create_attempts == 1
    assert result["retry_count"] == 0
    assert result["failed_count"] == 1
    assert result["errors"] == [
        "create:item-1..item-1:ambiguous_create_reconciliation_failed:teable_timeout_after_15s"
    ]


def test_sync_upserts_to_configured_table(monkeypatch):
    module = load_module()
    requests: list[tuple[str, str, dict | None]] = []

    def fake_send_json(method: str, url: str, api_key: str, payload: dict | None = None, timeout: float | None = None, **kwargs):
        requests.append((method, url, payload))
        assert api_key == "demo-token"
        if method == "GET" and "/field?" in url:
            return [{"name": field["name"]} for field in module.REQUIRED_FIELDS]
        if method == "GET" and "/record?fieldKeyType=name&take=1000" in url:
            first_item = module.important_work_items()[0]
            return {
                "records": [
                    {
                        "id": "rec-existing",
                        "fields": {"Item Id": first_item.item_id},
                    }
                ]
            }
        if method == "PATCH" and url.endswith("/record"):
            assert payload is not None
            return [
                {"id": record["id"], "fields": record["fields"]}
                for record in payload["records"]
            ]
        if method == "POST" and url.endswith("/record"):
            assert payload is not None
            return {
                "records": [
                    {"id": f"rec-created-{index}", "fields": record["fields"]}
                    for index, record in enumerate(payload["records"])
                ]
            }
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setattr(module, "send_json", fake_send_json)

    result = module.sync_to_teable(
        api_key="demo-token",
        api_base_url="https://app.teable.ai/api",
        base_id=None,
        table_id="tbl-work",
        table_name="Chummer Important Work",
        request_timeout_seconds=module.DEFAULT_HTTP_TIMEOUT_SECONDS,
        sync_deadline_seconds=module.DEFAULT_SYNC_DEADLINE_SECONDS,
    )

    assert result["state"] == "passed"
    assert result["table_id"] == "tbl-work"
    assert result["synced_count"] == len(module.important_work_items())
    assert result["updated_count"] == 1
    assert result["created_count"] == len(module.important_work_items()) - 1
    assert any(method == "GET" and "/field?" in url for method, url, _ in requests)
    assert sum(1 for method, url, _ in requests if method == "GET" and "/record?" in url) == 1
    assert sum(1 for method, url, _ in requests if method == "PATCH" and url.endswith("/record")) == 1
    create_request_sizes = [
        len(payload["records"])
        for method, url, payload in requests
        if method == "POST" and url.endswith("/record") and payload is not None
    ]
    expected_create_count = len(module.important_work_items()) - 1
    expected_create_batch_count = (
        expected_create_count + module.DEFAULT_BATCH_SIZE - 1
    ) // module.DEFAULT_BATCH_SIZE
    assert len(create_request_sizes) == expected_create_batch_count
    assert sum(create_request_sizes) == expected_create_count
    assert max(create_request_sizes) <= module.DEFAULT_BATCH_SIZE
