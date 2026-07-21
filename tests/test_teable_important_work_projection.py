from __future__ import annotations

import csv
import fcntl
import importlib.util
import json
import os
import stat
import sys
import threading
from pathlib import Path

import pytest


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


def make_item(module, item_id: str):
    return module.ImportantWorkItem(
        item_id,
        f"Title {item_id}",
        "Operations",
        "P0",
        "active",
        "daily",
        "test",
        "why",
        "next",
        "gate",
    )


def governed_lock_path(module, root: Path) -> Path:
    return root / module.SYNC_LOCK_DIRECTORY_NAME / module.SYNC_LOCK_FILENAME


def synthetic_credentialed_https_url(
    username: str,
    password: str,
    location: str,
    query_token: str,
) -> str:
    return "{}://{}@{}?token={}".format(
        "https",
        ":".join((username, password)),
        location,
        query_token,
    )


@pytest.fixture(autouse=True)
def isolate_teable_sync_lock(tmp_path, monkeypatch):
    isolated_path = (
        tmp_path
        / f"chummer-teable-important-work-sync-{os.geteuid()}"
        / "teable-important-work-sync.lock"
    )
    monkeypatch.setenv("CHUMMER_TEABLE_IMPORTANT_WORK_LOCK_PATH", str(isolated_path))


def assert_counter_invariants(result: dict):
    assert result["total_count"] == (
        result["synced_count"] + result["failed_count"] + result["unattempted_count"]
    )
    assert result["row_attempted_count"] == result["synced_count"] + result["failed_count"]
    assert result["synced_count"] == result["created_count"] + result["updated_count"]
    assert result["counter_invariants"]["all_pass"] is True


def test_projection_contains_unique_important_work_rows():
    module = load_module()

    rows = module.important_work_items()
    item_ids = [row.item_id for row in rows]

    assert len(rows) == 40
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


def test_windows_installer_rows_reflect_promoted_native_gold_proof():
    module = load_module()
    rows = {row.item_id: row for row in module.important_work_items()}
    digest = "80655fd79a096cd7714910d7b38f7741eea01f82ada96dc6a2a097951997d91"

    for item_id in ("windows-installer-premium", "windows-installer-current-shelf-proof"):
        row = rows[item_id]
        serialized = json.dumps(row.__dict__, sort_keys=True)
        assert row.status == "promoted-gold-proof-passed"
        assert row.cadence == "after every Windows promotion"
        assert "2026-07-12" in row.source
        assert digest in row.acceptance_gate
        assert "rerun native gold proof" in row.next_action.lower()
        assert "blocked-until-next-publish" not in serialized
        assert "27878634601" not in serialized
        assert "27878949995" not in serialized
        assert "4c5f62eb" not in serialized


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


@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
@pytest.mark.parametrize(
    "redirect_url",
    [
        "https://chummer.run/api/internal/community/important-work-moved",
        "https://other.example/secret-target",
    ],
    ids=["same-origin", "cross-origin"],
)
def test_hub_seed_post_redirect_is_blocked_closed_and_never_replayed(
    monkeypatch,
    status_code,
    redirect_url,
):
    module = load_module()
    token = "hub-secret-token"
    item = make_item(module, "item-1")
    opened_requests = []

    class CloseTrackingResponse:
        def __init__(self):
            self.close_count = 0
            self.read_count = 0

        def close(self):
            self.close_count += 1

        def read(self, *args, **kwargs):
            self.read_count += 1
            raise AssertionError("blocked Hub redirect response must not be read")

    response = CloseTrackingResponse()

    def fake_build_opener(handler):
        class FakeOpener:
            def open(self, request, timeout):
                opened_requests.append(request)
                return handler.redirect_request(
                    request,
                    response,
                    status_code,
                    "Redirect",
                    {},
                    redirect_url,
                )

        return FakeOpener()

    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module.urllib.request, "build_opener", fake_build_opener)

    result = module.seed_hub_store(
        hub_base_url="https://chummer.run",
        hub_token=token,
    )

    serialized = json.dumps(result, sort_keys=True)
    assert result["state"] == "failed"
    assert result["recorded_count"] == 0
    assert result["failed_count"] == 1
    assert result["errors"] == ["item-1:hub_redirect_blocked"]
    assert len(opened_requests) == 1
    assert opened_requests[0].get_method() == "POST"
    assert opened_requests[0].get_header("Authorization") == f"Bearer {token}"
    assert response.close_count == 1
    assert response.read_count == 0
    assert token not in serialized
    assert redirect_url not in serialized


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

    monkeypatch.setattr(module, "open_teable_url", fake_urlopen)

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

    monkeypatch.setattr(module, "open_teable_url", lambda request, timeout: FakeResponse())

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


def test_env_assignments_parses_supported_dotenv_syntax(tmp_path):
    module = load_module()
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                "# ignored",
                "TEABLE_API_KEY=plain-token",
                'CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID="base-quoted"',
                "export CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID='tbl-exported'",
                "INVALID LINE",
                "1INVALID=value",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert module.env_assignments(dotenv_path) == {
        "TEABLE_API_KEY": "plain-token",
        "CHUMMER_TEABLE_IMPORTANT_WORK_BASE_ID": "base-quoted",
        "CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID": "tbl-exported",
    }


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

    assert args.request_timeout_seconds == "9"
    assert args.sync_deadline_seconds == "45"


def test_process_environment_precedes_local_env_assignments(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "env_assignments",
        lambda path: {"TEABLE_API_KEY": "dotenv-token"},
    )
    clear_local_env_cache(module)
    monkeypatch.setenv("TEABLE_API_KEY", "process-token")

    args = module.parse_args([])

    assert args.api_key == "process-token"


def test_unsafe_dotenv_deadline_reaches_strict_validation(tmp_path, monkeypatch):
    module = load_module()
    output = tmp_path / "receipt.json"
    monkeypatch.setattr(
        module,
        "env_assignments",
        lambda path: {
            "TEABLE_API_KEY": "dotenv-token",
            "CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID": "tbl-dotenv",
            "CHUMMER_TEABLE_IMPORTANT_WORK_SYNC_DEADLINE_SECONDS": "181",
        },
    )
    clear_local_env_cache(module)
    monkeypatch.delenv("TEABLE_API_KEY", raising=False)
    monkeypatch.delenv("CHUMMER_TEABLE_IMPORTANT_WORK_API_KEY", raising=False)
    monkeypatch.delenv("CHUMMER_TEABLE_IMPORTANT_WORK_TABLE_ID", raising=False)
    monkeypatch.delenv(
        "CHUMMER_TEABLE_IMPORTANT_WORK_SYNC_DEADLINE_SECONDS",
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "send_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("invalid dotenv policy must not reach network")
        ),
    )

    exit_code = module.main(["--sync", "--output", str(output)])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert payload["sync"]["sync_deadline_seconds"] == 181.0
    assert payload["sync"]["errors"] == [
        "teable_configuration:teable_config_sync_deadline_invalid"
    ]


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
    assert result["failed_count"] == 0
    assert result["unattempted_count"] == len(module.important_work_items())
    assert result["errors"] == ["teable_setup:teable_http_403"]
    assert "demo-token" not in json.dumps(result)
    assert "teable_http_403:blocked" not in json.dumps(result)
    assert_counter_invariants(result)


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
    assert result["errors"] == [
        "item-1:teable_sync_deadline_exceeded",
        "item-2:teable_sync_deadline_exceeded",
    ]


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
    assert result["errors"] == ["item-1:teable_http_400"]


def test_sync_to_teable_reconciles_ambiguous_create_without_reposting(monkeypatch):
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
    create_batches: list[list[str]] = []

    monkeypatch.setattr(module, "important_work_items", lambda repo_root=module.RUN_SERVICES_ROOT: items)
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module,
        "existing_record_ids_by_item_id",
        lambda *args, **kwargs: {},
    )

    def reconcile(*args, expected_fields=None, **kwargs):
        assert expected_fields is not None
        return "rec-1" if args[3] == "item-1" else None

    monkeypatch.setattr(module, "find_existing_record", reconcile)

    def flaky_create_batch(*args, **kwargs):
        batch = args[3]
        create_batches.append([item.item_id for item in batch])
        raise RuntimeError("teable_timeout_after_15s")

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

    assert result["state"] == "failed"
    assert create_batches == [["item-1", "item-2"]]
    assert result["created_count"] == 1
    assert result["reconciled_create_count"] == 1
    assert result["retry_count"] == 0
    assert result["errors"] == ["item-2:teable_create_reconciliation_absent"]


def test_sync_to_teable_never_blindly_retries_create_when_reconciliation_fails(monkeypatch):
    module = load_module()
    item = module.ImportantWorkItem(
        "item-1", "Item 1", "Ops", "P0", "active", "daily", "test", "why", "next", "gate"
    )
    create_attempts = 0

    monkeypatch.setattr(module, "important_work_items", lambda repo_root=module.RUN_SERVICES_ROOT: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)

    def failed_reconciliation(*args, **kwargs):
        raise RuntimeError("teable_timeout_after_15s")

    def ambiguous_create(*args, **kwargs):
        nonlocal create_attempts
        create_attempts += 1
        raise RuntimeError("teable_timeout_after_15s")

    monkeypatch.setattr(module, "existing_record_ids_by_item_id", lambda *args, **kwargs: {})
    monkeypatch.setattr(module, "find_existing_record", failed_reconciliation)
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
    assert result["errors"] == ["item-1:teable_timeout"]


def test_sync_upserts_to_configured_table(monkeypatch):
    module = load_module()
    requests: list[tuple[str, str, dict | None]] = []

    def fake_send_json(
        method: str,
        url: str,
        api_key: str,
        payload: dict | None = None,
        timeout: float = 60,
        **kwargs,
    ):
        requests.append((method, url, payload))
        assert api_key == "demo-token"
        if method == "GET" and "/field?" in url:
            return [{"name": field["name"]} for field in module.REQUIRED_FIELDS]
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
    first_item = module.important_work_items()[0]
    monkeypatch.setattr(
        module,
        "existing_record_ids_by_item_id",
        lambda *args, **kwargs: {first_item.item_id: "rec-existing"},
    )

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
    create_request_sizes = [
        len(payload["records"])
        for method, url, payload in requests
        if method == "POST" and url.endswith("/record") and payload is not None
    ]
    assert create_request_sizes == [10, 10, 10, len(module.important_work_items()) - 31]
    assert_counter_invariants(result)


def test_request_timeout_is_capped_by_exact_remaining_deadline_without_one_second_floor(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module.time, "monotonic", lambda: 9.75)

    assert module.bounded_timeout_seconds(15, deadline_monotonic=10.0) == pytest.approx(0.25)


def test_record_lookup_uses_take_two_and_escapes_exact_item_id(monkeypatch):
    module = load_module()
    captured: dict[str, str] = {}
    item_id = "key'\\part"

    def fake_send_json(method, url, api_key, payload=None, timeout=60, **kwargs):
        captured["url"] = url
        return {"records": [{"id": "rec-1", "fields": {"Item Id": item_id}}]}

    monkeypatch.setattr(module, "send_json", fake_send_json)

    assert module.find_existing_record("https://teable.test/api", "token", "tbl", item_id) == "rec-1"
    decoded_url = module.urllib.parse.unquote(captured["url"])
    assert "take=2" in decoded_url
    assert "{Item Id} = 'key\\'\\\\part'" in decoded_url


def test_record_lookup_rejects_duplicate_item_id_rows(monkeypatch):
    module = load_module()

    monkeypatch.setattr(
        module,
        "send_json",
        lambda *args, **kwargs: {
            "records": [
                {"id": "rec-1", "fields": {"Item Id": "item-1"}},
                {"id": "rec-2", "fields": {"Item Id": "item-1"}},
            ]
        },
    )

    with pytest.raises(RuntimeError, match="teable_duplicate_item_id"):
        module.find_existing_record("https://teable.test/api", "token", "tbl", "item-1")


def test_exact_lookup_preflight_rejects_duplicate_source_id_even_when_absent(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="teable_source_duplicate_item_id"):
        module.existing_record_ids_by_item_id(
            "https://teable.test/api",
            "token",
            "tbl",
            ["item-1", "item-1"],
        )


@pytest.mark.parametrize("malformed_lane", ["field", "record"])
def test_malformed_setup_or_record_read_fails_before_record_create(monkeypatch, malformed_lane):
    module = load_module()
    item = make_item(module, "item-1")
    record_post_count = 0

    monkeypatch.setattr(module, "important_work_items", lambda: [item])

    def fake_send_json(method, url, api_key, payload=None, timeout=60, **kwargs):
        nonlocal record_post_count
        if method == "GET" and "/field?" in url:
            if malformed_lane == "field":
                return {"not": "a-list"}
            return [{"name": field["name"]} for field in module.REQUIRED_FIELDS]
        if method == "GET" and "/record?" in url:
            return {"not": "records"} if malformed_lane == "record" else {"records": []}
        if method == "POST" and url.endswith("/record"):
            record_post_count += 1
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setattr(module, "send_json", fake_send_json)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://teable.test/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        transient_retry_limit=0,
    )

    assert result["state"] == "failed"
    assert result["synced_count"] == 0
    assert result["unattempted_count"] == 1
    assert record_post_count == 0


def test_malformed_table_list_fails_before_table_create(monkeypatch):
    module = load_module()
    post_count = 0

    def fake_send_json(method, url, api_key, payload=None, timeout=60, **kwargs):
        nonlocal post_count
        if method == "GET":
            return {"not": "tables"}
        post_count += 1
        return {}

    monkeypatch.setattr(module, "send_json", fake_send_json)

    with pytest.raises(RuntimeError, match="teable_table_list_invalid_response"):
        module.resolve_or_create_table("https://teable.test/api", "token", "base", "Work")
    assert post_count == 0


def test_updates_are_split_into_ten_ten_remainder_batches(monkeypatch):
    module = load_module()
    items = [make_item(module, f"item-{index:02d}") for index in range(25)]
    batch_sizes: list[int] = []

    monkeypatch.setattr(module, "important_work_items", lambda: items)
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: f"rec-{args[3]}")

    def fake_update(*args, **kwargs):
        batch_sizes.append(len(args[3]))
        return len(args[3])

    monkeypatch.setattr(module, "update_record_batch", fake_update)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://teable.test/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        batch_size=99,
    )

    assert result["state"] == "passed"
    assert batch_sizes == [10, 10, 5]
    assert result["batch_size"] == 10
    assert result["batch_count"] == 3
    assert result["completed_batch_count"] == 3
    assert result["updated_count"] == 25


def test_transient_update_is_retried_but_permanent_update_is_not(monkeypatch):
    module = load_module()
    item = make_item(module, "item-1")
    attempts = 0

    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: "rec-1")

    def transient_then_pass(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("teable_http_503:provider-body-must-not-leak")
        return 1

    monkeypatch.setattr(module, "update_record_batch", transient_then_pass)
    transient_result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://teable.test/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        retry_backoff_seconds=0,
    )

    assert transient_result["state"] == "passed"
    assert attempts == 2
    assert transient_result["retry_count"] == 1
    assert "provider-body" not in json.dumps(transient_result)

    attempts = 0

    def permanent_failure(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("teable_http_400:secret-provider-body")

    monkeypatch.setattr(module, "update_record_batch", permanent_failure)
    permanent_result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://teable.test/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        retry_backoff_seconds=0,
    )

    assert permanent_result["state"] == "failed"
    assert attempts == 1
    assert permanent_result["retry_count"] == 0
    assert permanent_result["errors"] == ["item-1:teable_http_400"]
    assert "secret-provider-body" not in json.dumps(permanent_result)


@pytest.mark.parametrize(
    ("confirmed", "expected_synced", "expected_failed"),
    [
        ({"item-1", "item-2"}, 2, 0),
        (set(), 0, 2),
        ({"item-1"}, 1, 1),
    ],
)
def test_ambiguous_create_is_never_reposted_and_requires_exact_reconciliation(
    monkeypatch,
    confirmed,
    expected_synced,
    expected_failed,
):
    module = load_module()
    items = [make_item(module, "item-1"), make_item(module, "item-2")]
    create_attempts = 0

    monkeypatch.setattr(module, "important_work_items", lambda: items)
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)

    def lookup(*args, expected_fields=None, **kwargs):
        item_id = args[3]
        if expected_fields is None:
            return None
        return f"rec-{item_id}" if item_id in confirmed else None

    def ambiguous_create(*args, **kwargs):
        nonlocal create_attempts
        create_attempts += 1
        raise RuntimeError("teable_timeout:provider-body")

    monkeypatch.setattr(module, "find_existing_record", lookup)
    monkeypatch.setattr(module, "create_record_batch", ambiguous_create)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://teable.test/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        retry_backoff_seconds=0,
    )

    assert create_attempts == 1
    assert result["synced_count"] == expected_synced
    assert result["created_count"] == expected_synced
    assert result["failed_count"] == expected_failed
    assert result["ambiguous_create_count"] == 2
    assert result["reconciled_create_count"] == expected_synced
    assert result["retry_count"] == 0
    assert result["state"] == ("passed" if expected_failed == 0 else "failed")
    assert_counter_invariants(result)


def test_stale_reconciliation_row_remains_failed(monkeypatch):
    module = load_module()
    item = make_item(module, "item-1")

    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)

    def lookup(*args, expected_fields=None, **kwargs):
        if expected_fields is None:
            return None
        raise RuntimeError("teable_record_reconciliation_stale")

    monkeypatch.setattr(module, "find_existing_record", lookup)
    monkeypatch.setattr(module, "create_record_batch", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("teable_invalid_json_response")))

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://teable.test/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
    )

    assert result["state"] == "failed"
    assert result["failed_count"] == 1
    assert result["reconciled_create_count"] == 0
    assert result["errors"] == ["item-1:teable_record_reconciliation_stale"]


def test_deadline_failure_leaves_later_batches_truthfully_unattempted(monkeypatch):
    module = load_module()
    items = [make_item(module, f"item-{index:02d}") for index in range(11)]

    monkeypatch.setattr(module, "important_work_items", lambda: items)
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: f"rec-{args[3]}")
    monkeypatch.setattr(
        module,
        "update_record_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("teable_sync_deadline_exceeded")),
    )

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://teable.test/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
    )

    assert result["state"] == "failed"
    assert result["batch_count"] == 2
    assert result["attempted_batch_count"] == 1
    assert result["failed_count"] == 10
    assert result["unattempted_count"] == 1
    assert result["deadline_exceeded"] is True
    assert result["row_attempted_count"] == 10
    assert_counter_invariants(result)


def test_batch_mutation_responses_validate_counts_and_ids(monkeypatch):
    module = load_module()
    items = [make_item(module, "item-1"), make_item(module, "item-2")]

    monkeypatch.setattr(module, "send_json", lambda *args, **kwargs: [{"id": "wrong-1"}, {"id": "wrong-2"}])
    with pytest.raises(RuntimeError, match="teable_update_response_id_mismatch"):
        module.update_record_batch(
            "https://teable.test/api",
            "token",
            "tbl",
            [(items[0], "rec-1"), (items[1], "rec-2")],
            "2026-07-12T00:00:00Z",
        )

    monkeypatch.setattr(
        module,
        "send_json",
        lambda *args, **kwargs: {
            "records": [
                {"id": "same", "fields": module.teable_fields_for_row(items[0], "2026-07-12T00:00:00Z")},
                {"id": "same", "fields": module.teable_fields_for_row(items[1], "2026-07-12T00:00:00Z")},
            ]
        },
    )
    with pytest.raises(RuntimeError, match="teable_create_response_id_mismatch"):
        module.create_record_batch(
            "https://teable.test/api",
            "token",
            "tbl",
            items,
            "2026-07-12T00:00:00Z",
        )


def test_table_and_field_create_ambiguity_reconciles_without_post_retry(monkeypatch):
    module = load_module()
    table_gets = 0
    table_posts = 0

    def table_send(method, url, api_key, payload=None, timeout=60, **kwargs):
        nonlocal table_gets, table_posts
        if method == "GET":
            table_gets += 1
            return [] if table_gets == 1 else [
                {"id": "tbl-1", "name": "Work", "dbTableName": module.DEFAULT_DB_TABLE_NAME}
            ]
        table_posts += 1
        raise RuntimeError("teable_timeout")

    monkeypatch.setattr(module, "send_json", table_send)

    assert module.resolve_or_create_table("https://teable.test/api", "token", "base", "Work") == "tbl-1"
    assert table_posts == 1

    field_gets = 0
    field_posts = 0
    required_names = [str(field["name"]) for field in module.REQUIRED_FIELDS]

    def field_send(method, url, api_key, payload=None, timeout=60, **kwargs):
        nonlocal field_gets, field_posts
        if method == "GET":
            field_gets += 1
            names = required_names[:-1] if field_gets == 1 else required_names
            return [{"name": name} for name in names]
        field_posts += 1
        raise RuntimeError("teable_timeout")

    monkeypatch.setattr(module, "send_json", field_send)

    module.ensure_fields("https://teable.test/api", "token", "tbl-1")
    assert field_posts == 1


def test_transient_get_retry_is_bounded_and_counted(monkeypatch):
    module = load_module()
    attempts = 0
    retry_state = {"retry_count": 0}

    def flaky_get(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("teable_http_503:body")
        return {"records": [{"id": "rec-1", "fields": {"Item Id": "item-1"}}]}

    monkeypatch.setattr(module, "send_json", flaky_get)

    assert module.find_existing_record(
        "https://teable.test/api",
        "token",
        "tbl",
        "item-1",
        retry_backoff_seconds=0,
        retry_state=retry_state,
    ) == "rec-1"
    assert attempts == 2
    assert retry_state == {"retry_count": 1}


def test_one_deadline_value_is_propagated_through_setup_lookup_write_and_reconciliation(monkeypatch):
    module = load_module()
    item = make_item(module, "item-1")
    observed_deadlines: list[float | None] = []

    monkeypatch.setattr(module, "important_work_items", lambda: [item])

    def ensure(*args, deadline_monotonic=None, **kwargs):
        observed_deadlines.append(deadline_monotonic)

    def lookup(*args, deadline_monotonic=None, expected_fields=None, **kwargs):
        observed_deadlines.append(deadline_monotonic)
        return "rec-1" if expected_fields is not None else None

    def create(*args, deadline_monotonic=None, **kwargs):
        observed_deadlines.append(deadline_monotonic)
        raise RuntimeError("teable_invalid_json_response")

    monkeypatch.setattr(module, "ensure_fields", ensure)
    monkeypatch.setattr(module, "find_existing_record", lookup)
    monkeypatch.setattr(module, "create_record_batch", create)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://teable.test/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_deadline_seconds=30,
    )

    assert result["state"] == "passed"
    assert len(observed_deadlines) == 4
    assert observed_deadlines[0] is not None
    assert len(set(observed_deadlines)) == 1


def test_sync_result_shape_is_uniform_when_not_requested_or_blocked():
    module = load_module()

    not_requested = module.build_projection()["sync"]
    blocked = module.sync_to_teable(
        api_key=None,
        api_base_url="https://teable.test/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
    )

    assert set(not_requested) == set(blocked)


@pytest.mark.parametrize(
    ("argument", "value", "error_code"),
    [
        ("request_timeout_seconds", 15.01, "teable_config_request_timeout_invalid"),
        ("request_timeout_seconds", 0, "teable_config_request_timeout_invalid"),
        ("request_timeout_seconds", "inf", "teable_config_request_timeout_invalid"),
        ("sync_deadline_seconds", 180.01, "teable_config_sync_deadline_invalid"),
        ("sync_deadline_seconds", "nan", "teable_config_sync_deadline_invalid"),
        ("transient_retry_limit", 4, "teable_config_retry_limit_invalid"),
        ("transient_retry_limit", 1.5, "teable_config_retry_limit_invalid"),
        ("retry_backoff_seconds", 5.01, "teable_config_retry_backoff_invalid"),
        ("retry_backoff_seconds", -0.1, "teable_config_retry_backoff_invalid"),
    ],
)
def test_unsafe_numeric_configuration_fails_before_network(
    tmp_path,
    monkeypatch,
    argument,
    value,
    error_code,
):
    module = load_module()
    item = make_item(module, "item-1")
    network_calls = 0
    monkeypatch.setattr(module, "important_work_items", lambda: [item])

    def unexpected_network(*args, **kwargs):
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("configuration failure must precede network")

    monkeypatch.setattr(module, "send_json", unexpected_network)
    kwargs = {
        "api_key": "token",
        "api_base_url": "https://relay.example/api",
        "base_id": None,
        "table_id": "tbl",
        "table_name": "Work",
        "sync_lock_path": tmp_path / "sync.lock",
        argument: value,
    }

    result = module.sync_to_teable(**kwargs)

    assert result["state"] == "failed"
    assert result["errors"] == [f"teable_configuration:{error_code}"]
    assert result["row_attempted_count"] == 0
    assert network_calls == 0
    assert_counter_invariants(result)


def test_smaller_timeout_and_deadline_values_remain_supported(tmp_path, monkeypatch):
    module = load_module()
    item = make_item(module, "item-1")
    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: "rec-1")
    monkeypatch.setattr(module, "update_record_batch", lambda *args, **kwargs: 1)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/governed/teable/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        request_timeout_seconds=0.25,
        sync_deadline_seconds=1.0,
        transient_retry_limit=0,
        retry_backoff_seconds=0,
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    assert result["state"] == "passed"
    assert result["request_timeout_seconds"] == 0.25
    assert result["sync_deadline_seconds"] == 1.0
    assert_counter_invariants(result)


def test_invalid_cli_numeric_value_writes_truthful_receipt_and_exits_nonzero(tmp_path, monkeypatch):
    module = load_module()
    output = tmp_path / "receipt.json"
    network_calls = 0

    def unexpected_network(*args, **kwargs):
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("invalid CLI policy must not reach network")

    monkeypatch.setattr(module, "send_json", unexpected_network)

    exit_code = module.main(
        [
            "--sync",
            "--api-key",
            "token",
            "--request-timeout-seconds",
            "inf",
            "--sync-lock-path",
            str(governed_lock_path(module, tmp_path)),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert payload["sync"]["state"] == "failed"
    assert payload["sync"]["request_timeout_seconds"] is None
    assert payload["sync"]["errors"] == [
        "teable_configuration:teable_config_request_timeout_invalid"
    ]
    assert network_calls == 0


def test_unsafe_env_deadline_is_not_silently_replaced_by_default(tmp_path, monkeypatch):
    module = load_module()
    output = tmp_path / "receipt.json"
    monkeypatch.setenv("CHUMMER_TEABLE_IMPORTANT_WORK_SYNC_DEADLINE_SECONDS", "181")
    monkeypatch.setattr(
        module,
        "send_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call network")),
    )

    exit_code = module.main(
        [
            "--sync",
            "--api-key",
            "token",
            "--sync-lock-path",
            str(governed_lock_path(module, tmp_path)),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert payload["sync"]["sync_deadline_seconds"] == 181.0
    assert payload["sync"]["errors"] == [
        "teable_configuration:teable_config_sync_deadline_invalid"
    ]


@pytest.mark.parametrize(
    "api_base_url",
    [
        "http://relay.example/api",
        "https://relay.example/api?token=secret",
        "https://relay.example/api#fragment",
        "ftp://relay.example/api",
    ],
)
def test_unsafe_api_base_url_fails_before_network(tmp_path, monkeypatch, api_base_url):
    module = load_module()
    network_calls = 0
    monkeypatch.setattr(module, "important_work_items", lambda: [make_item(module, "item-1")])

    def unexpected_network(*args, **kwargs):
        nonlocal network_calls
        network_calls += 1

    monkeypatch.setattr(module, "send_json", unexpected_network)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url=api_base_url,
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    assert result["state"] == "failed"
    assert result["errors"] == ["teable_configuration:teable_config_api_base_url_invalid"]
    assert network_calls == 0


def test_api_url_credentials_and_query_are_removed_from_failed_receipt(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "important_work_items", lambda: [make_item(module, "item-1")])
    raw_url = synthetic_credentialed_https_url(
        "operator",
        "super-secret",
        "relay.example/governed/api",
        "query-secret",
    )

    result = module.sync_to_teable(
        api_key=None,
        api_base_url=raw_url,
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    rendered = json.dumps(result)
    assert result["state"] == "failed"
    assert result["api_base_url"] == "https://relay.example/governed/api"
    assert "super-secret" not in rendered
    assert "query-secret" not in rendered
    assert "operator" not in rendered


def test_api_base_accepts_custom_https_and_explicit_loopback_http():
    module = load_module()

    assert module.validated_api_base_url("https://governed-relay.example/custom/api") == (
        "https://governed-relay.example/custom/api"
    )
    assert module.validated_api_base_url("http://127.0.0.1:8080/api") == "http://127.0.0.1:8080/api"
    assert module.validated_api_base_url("http://[::1]:8080/api") == "http://[::1]:8080/api"


def test_sync_lock_default_is_shared_across_sibling_worktrees_and_env_can_override(tmp_path, monkeypatch):
    module = load_module()

    assert module.DEFAULT_SYNC_LOCK_PATH == (
        Path("/tmp") / module.SYNC_LOCK_DIRECTORY_NAME / module.SYNC_LOCK_FILENAME
    )
    assert "cross_host" in module.build_projection()["sync"]["sync_lock_scope"]
    override = governed_lock_path(module, tmp_path)
    monkeypatch.setenv("CHUMMER_TEABLE_IMPORTANT_WORK_LOCK_PATH", str(override))
    assert module.parse_args([]).sync_lock_path == str(override)


def test_sync_tests_resolve_isolated_lock_at_call_time_without_touching_live_default(monkeypatch):
    module = load_module()
    item = make_item(module, "item-1")
    default_path = module.DEFAULT_SYNC_LOCK_PATH
    default_snapshot = (
        (default_path.stat().st_mode, default_path.read_bytes())
        if default_path.exists()
        else None
    )
    isolated_path = Path(os.environ["CHUMMER_TEABLE_IMPORTANT_WORK_LOCK_PATH"])
    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: "rec-1")
    monkeypatch.setattr(module, "update_record_batch", lambda *args, **kwargs: 1)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
    )

    assert result["state"] == "passed"
    assert isolated_path.read_bytes() == module.SYNC_LOCK_SIGNATURE
    assert result["sync_lock_path"] == str(isolated_path)
    if default_snapshot is None:
        assert not default_path.exists()
    else:
        assert (default_path.stat().st_mode, default_path.read_bytes()) == default_snapshot


@pytest.mark.parametrize(
    ("mode", "content"),
    [
        (0o644, b"unrelated content\n"),
        (0o600, b"not the Chummer lock signature\n"),
    ],
)
def test_unrecognized_existing_lock_file_is_unchanged_and_not_acquired(
    tmp_path,
    monkeypatch,
    mode,
    content,
):
    module = load_module()
    item = make_item(module, "item-1")
    lock_path = governed_lock_path(module, tmp_path)
    lock_path.parent.mkdir(mode=0o700)
    lock_path.write_bytes(content)
    lock_path.chmod(mode)
    before_mode = stat.S_IMODE(lock_path.stat().st_mode)
    network_calls = 0
    monkeypatch.setattr(module, "important_work_items", lambda: [item])

    def unexpected_network(*args, **kwargs):
        nonlocal network_calls
        network_calls += 1

    monkeypatch.setattr(module, "send_json", unexpected_network)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=lock_path,
    )

    assert result["state"] == "failed"
    assert result["errors"] == ["teable_lock:teable_sync_lock_unrecognized"]
    assert stat.S_IMODE(lock_path.stat().st_mode) == before_mode
    assert lock_path.read_bytes() == content
    assert network_calls == 0
    fd = os.open(lock_path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)


def test_arbitrary_existing_file_override_is_rejected_without_metadata_or_content_change(tmp_path):
    module = load_module()
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("keep me", encoding="utf-8")
    unrelated.chmod(0o644)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=unrelated,
    )

    assert result["errors"] == [
        "teable_configuration:teable_config_sync_lock_path_invalid"
    ]
    assert stat.S_IMODE(unrelated.stat().st_mode) == 0o644
    assert unrelated.read_text(encoding="utf-8") == "keep me"


def test_group_writable_nonsticky_lock_container_is_rejected(tmp_path, monkeypatch):
    module = load_module()
    unsafe_container = tmp_path / "unsafe-container"
    unsafe_container.mkdir()
    unsafe_container.chmod(0o777)
    lock_path = governed_lock_path(module, unsafe_container)
    network_calls = 0
    monkeypatch.setattr(module, "important_work_items", lambda: [make_item(module, "item-1")])

    def unexpected_network(*args, **kwargs):
        nonlocal network_calls
        network_calls += 1

    monkeypatch.setattr(module, "send_json", unexpected_network)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=lock_path,
    )

    assert result["errors"] == ["teable_lock:teable_sync_lock_unrecognized"]
    assert not lock_path.exists()
    assert network_calls == 0


def test_multilink_lock_inode_is_rejected(tmp_path, monkeypatch):
    module = load_module()
    lock_path = governed_lock_path(module, tmp_path)
    lock_path.parent.mkdir(mode=0o700)
    lock_path.write_bytes(module.SYNC_LOCK_SIGNATURE)
    lock_path.chmod(0o600)
    os.link(lock_path, lock_path.parent / "unexpected-hardlink")
    monkeypatch.setattr(module, "important_work_items", lambda: [make_item(module, "item-1")])

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=lock_path,
    )

    assert result["errors"] == ["teable_lock:teable_sync_lock_unrecognized"]
    assert lock_path.stat().st_nlink == 2
    assert lock_path.read_bytes() == module.SYNC_LOCK_SIGNATURE


def test_unexpected_exception_with_retained_traceback_releases_sync_lock(tmp_path, monkeypatch):
    module = load_module()
    item = make_item(module, "item-1")
    lock_path = governed_lock_path(module, tmp_path)
    original_chunked = module.chunked
    retained_exception: list[BaseException] = []
    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: "rec-1")

    def unexpected_after_acquire(*args, **kwargs):
        raise ValueError("unexpected_after_lock_acquire")

    monkeypatch.setattr(module, "chunked", unexpected_after_acquire)
    try:
        module.sync_to_teable(
            api_key="token",
            api_base_url="https://relay.example/api",
            base_id=None,
            table_id="tbl",
            table_name="Work",
            sync_lock_path=lock_path,
        )
    except ValueError as exc:
        retained_exception.append(exc)
    else:
        raise AssertionError("unexpected exception should propagate")

    monkeypatch.setattr(module, "chunked", original_chunked)
    monkeypatch.setattr(module, "update_record_batch", lambda *args, **kwargs: 1)
    second = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=lock_path,
    )

    assert retained_exception and retained_exception[0].__traceback__ is not None
    assert second["state"] == "passed"


def test_teable_redirect_handler_blocks_cross_origin_and_https_downgrade():
    module = load_module()
    handler = module.SafeTeableRedirectHandler()
    request = module.urllib.request.Request(
        "https://relay.example/api/table",
        headers={"Authorization": "Bearer secret"},
    )

    with pytest.raises(module.urllib.error.HTTPError) as cross_origin:
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://other.example/api/table",
        )
    assert cross_origin.value.code == 470

    with pytest.raises(module.urllib.error.HTTPError) as downgrade:
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "http://relay.example/api/table",
        )
    assert downgrade.value.code == 470

    same_origin = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://relay.example/api/next",
    )
    assert same_origin is not None
    assert same_origin.get_header("Authorization") == "Bearer secret"


@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
def test_teable_redirect_handler_rejects_all_non_read_redirects(status_code):
    module = load_module()
    handler = module.SafeTeableRedirectHandler()
    request = module.urllib.request.Request(
        "https://relay.example/api/table",
        data=b"{}",
        headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
        method="POST",
    )

    with pytest.raises(module.TeableRequestPhaseError) as blocked:
        handler.redirect_request(
            request,
            None,
            status_code,
            "Redirect",
            {},
            "https://relay.example/api/other",
        )

    assert str(blocked.value) == "teable_mutation_redirect_blocked"
    assert blocked.value.request_method == "POST"
    assert blocked.value.request_io_started is True
    assert blocked.value.response_received is True
    assert module.is_ambiguous_create_error(blocked.value) is True


@pytest.mark.parametrize(
    "error_code",
    ["teable_mutation_redirect_blocked", "teable_sync_deadline_exceeded"],
)
def test_phase_error_is_create_ambiguous_only_for_post(error_code):
    module = load_module()
    post_error = module.TeableRequestPhaseError(
        error_code,
        request_method="post",
        request_io_started=True,
        response_received=True,
    )
    patch_error = module.TeableRequestPhaseError(
        error_code,
        request_method="patch",
        request_io_started=True,
        response_received=True,
    )

    assert post_error.request_method == "POST"
    assert patch_error.request_method == "PATCH"
    assert module.is_ambiguous_create_error(post_error) is True
    assert module.is_ambiguous_create_error(patch_error) is False


def test_same_origin_head_redirect_fails_closed_without_method_rewrite_or_header_loss():
    module = load_module()
    handler = module.SafeTeableRedirectHandler()
    request = module.urllib.request.Request(
        "https://relay.example/api/table",
        headers={"Authorization": "Bearer secret"},
        method="HEAD",
    )

    class CloseTrackingResponse:
        def __init__(self):
            self.close_count = 0

        def close(self):
            self.close_count += 1

    response = CloseTrackingResponse()
    with pytest.raises(module.urllib.error.HTTPError) as blocked:
        handler.redirect_request(
            request,
            response,
            302,
            "Found",
            {},
            "https://relay.example/api/next",
        )

    assert blocked.value.code == 470
    assert request.get_method() == "HEAD"
    assert request.get_header("Authorization") == "Bearer secret"
    assert response.close_count == 1


@pytest.mark.parametrize(
    ("request_method", "redirect_url"),
    [
        ("POST", "https://relay.example/api/next"),
        ("PATCH", "https://relay.example/api/next"),
        ("HEAD", "https://relay.example/api/next"),
        ("GET", "https://other.example/api/next"),
        ("GET", "http://relay.example/api/next"),
    ],
)
def test_every_rejected_redirect_closes_response_without_reading_body(
    request_method,
    redirect_url,
):
    module = load_module()
    handler = module.SafeTeableRedirectHandler()
    request = module.urllib.request.Request(
        "https://relay.example/api/table",
        data=b"{}" if request_method in {"POST", "PATCH"} else None,
        headers={"Authorization": "Bearer secret"},
        method=request_method,
    )

    class CloseTrackingResponse:
        def __init__(self):
            self.close_count = 0
            self.read_count = 0

        def close(self):
            self.close_count += 1

        def read(self, *args, **kwargs):
            self.read_count += 1
            raise AssertionError("redirect rejection must not read provider body")

    response = CloseTrackingResponse()
    with pytest.raises((module.urllib.error.HTTPError, module.TeableRequestPhaseError)):
        handler.redirect_request(
            request,
            response,
            302,
            "Found",
            {},
            redirect_url,
        )

    assert response.close_count == 1
    assert response.read_count == 0


def test_rejected_redirect_preserves_policy_error_when_response_is_already_closed():
    module = load_module()
    handler = module.SafeTeableRedirectHandler()
    request = module.urllib.request.Request(
        "https://relay.example/api/table",
        data=b"{}",
        method="POST",
    )

    class AlreadyClosedResponse:
        def close(self):
            raise ValueError("already closed")

    with pytest.raises(module.TeableRequestPhaseError) as blocked:
        handler.redirect_request(
            request,
            AlreadyClosedResponse(),
            302,
            "Found",
            {},
            "https://relay.example/api/next",
        )

    assert str(blocked.value) == "teable_mutation_redirect_blocked"


@pytest.mark.parametrize("status_code", [301, 302, 303])
@pytest.mark.parametrize("reconciliation_confirmed", [True, False])
def test_post_redirect_is_reconciled_once_without_retry_or_secret_leak(
    tmp_path,
    monkeypatch,
    status_code,
    reconciliation_confirmed,
):
    module = load_module()
    handler = module.SafeTeableRedirectHandler()
    item = make_item(module, "item-1")
    post_count = 0
    redirect_url = synthetic_credentialed_https_url(
        "redirect-user",
        "redirect-secret",
        "other.example/next",
        "redirect-query",
    )
    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)

    def lookup(*args, expected_fields=None, **kwargs):
        if expected_fields is None:
            return None
        return "rec-1" if reconciliation_confirmed else None

    def redirect_after_post(request, timeout):
        nonlocal post_count
        assert request.get_method() == "POST"
        post_count += 1
        return handler.redirect_request(
            request,
            None,
            status_code,
            "Redirect",
            {},
            redirect_url,
        )

    monkeypatch.setattr(module, "find_existing_record", lookup)
    monkeypatch.setattr(module, "open_teable_url", redirect_after_post)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    rendered = json.dumps(result)
    assert post_count == 1
    assert result["retry_count"] == 0
    assert result["ambiguous_create_count"] == 1
    assert result["reconciled_create_count"] == (1 if reconciliation_confirmed else 0)
    assert result["state"] == ("passed" if reconciliation_confirmed else "failed")
    assert "redirect-user" not in rendered
    assert "redirect-secret" not in rendered
    assert "redirect-query" not in rendered


def test_get_cross_origin_redirect_remains_non_mutating_setup_failure_without_url_leak(monkeypatch):
    module = load_module()
    handler = module.SafeTeableRedirectHandler()
    open_count = 0
    redirect_url = synthetic_credentialed_https_url(
        "redirect-user",
        "redirect-secret",
        "other.example/next",
        "redirect-query",
    )

    def redirect_after_get(request, timeout):
        nonlocal open_count
        assert request.get_method() == "GET"
        open_count += 1
        return handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            redirect_url,
        )

    monkeypatch.setattr(module, "open_teable_url", redirect_after_get)

    with pytest.raises(RuntimeError) as failure:
        module.send_json("GET", "https://relay.example/api/base/access/all", "token")

    assert open_count == 1
    assert str(failure.value) == "teable_http_470"
    assert module.is_ambiguous_create_error(failure.value) is False
    assert "redirect" not in str(failure.value)


def test_patch_redirect_is_not_retried_and_is_not_counted_as_create_ambiguity(tmp_path, monkeypatch):
    module = load_module()
    handler = module.SafeTeableRedirectHandler()
    item = make_item(module, "item-1")
    patch_count = 0
    redirect_url = synthetic_credentialed_https_url(
        "redirect-user",
        "redirect-secret",
        "other.example/next",
        "redirect-query",
    )
    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: "rec-1")

    def redirect_after_patch(request, timeout):
        nonlocal patch_count
        assert request.get_method() == "PATCH"
        patch_count += 1
        return handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            redirect_url,
        )

    monkeypatch.setattr(module, "open_teable_url", redirect_after_patch)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        retry_backoff_seconds=0,
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    rendered = json.dumps(result)
    assert result["state"] == "failed"
    assert patch_count == 1
    assert result["retry_count"] == 0
    assert result["ambiguous_create_count"] == 0
    assert result["errors"] == ["item-1:teable_mutation_redirect_blocked"]
    assert "redirect-user" not in rendered
    assert "redirect-secret" not in rendered
    assert "redirect-query" not in rendered


def test_provider_path_ids_are_validated_before_network_and_quote_uses_no_safe_slash(tmp_path, monkeypatch):
    module = load_module()
    network_calls = 0
    monkeypatch.setattr(module, "important_work_items", lambda: [make_item(module, "item-1")])

    def unexpected_network(*args, **kwargs):
        nonlocal network_calls
        network_calls += 1

    monkeypatch.setattr(module, "send_json", unexpected_network)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl/escape",
        table_name="Work",
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    assert result["errors"] == ["teable_configuration:teable_table_id_invalid"]
    assert network_calls == 0
    monkeypatch.setattr(module, "validated_provider_id", lambda value, kind: "tbl/escape")
    assert module.quoted_provider_id("ignored", kind="table") == "tbl%2Fescape"


def test_table_and_field_success_bodies_require_exact_names_then_reconcile(monkeypatch):
    module = load_module()
    table_gets = 0
    table_posts = 0

    def table_send(method, url, api_key, payload=None, **kwargs):
        nonlocal table_gets, table_posts
        if method == "GET":
            table_gets += 1
            return [] if table_gets == 1 else [
                {
                    "id": "tbl-1",
                    "name": "Work",
                    "dbTableName": module.DEFAULT_DB_TABLE_NAME,
                }
            ]
        table_posts += 1
        return {"id": "tbl-1"}

    monkeypatch.setattr(module, "send_json", table_send)
    assert module.resolve_or_create_table("https://relay.example/api", "token", "base", "Work") == "tbl-1"
    assert table_posts == 1

    field_gets = 0
    field_posts = 0
    names = [str(field["name"]) for field in module.REQUIRED_FIELDS]

    def field_send(method, url, api_key, payload=None, **kwargs):
        nonlocal field_gets, field_posts
        if method == "GET":
            field_gets += 1
            visible = names[:-1] if field_gets == 1 else names
            return [{"name": name} for name in visible]
        field_posts += 1
        return {"id": "fld-1"}

    monkeypatch.setattr(module, "send_json", field_send)
    module.ensure_fields("https://relay.example/api", "token", "tbl-1")
    assert field_posts == 1


@pytest.mark.parametrize("malformation", ["missing_fields", "wrong_title"])
def test_malformed_create_success_is_ambiguous_and_exactly_reconciled(
    tmp_path,
    monkeypatch,
    malformation,
):
    module = load_module()
    item = make_item(module, "item-1")
    post_count = 0
    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)

    def lookup(*args, expected_fields=None, **kwargs):
        return "rec-1" if expected_fields is not None else None

    def create_response(method, url, api_key, payload=None, **kwargs):
        nonlocal post_count
        post_count += 1
        if malformation == "missing_fields":
            return {"records": [{"id": "rec-1"}]}
        fields = module.teable_fields_for_row(item, payload["records"][0]["fields"]["Last Synced At UTC"])
        fields["Title"] = "Wrong title"
        return {"records": [{"id": "rec-1", "fields": fields}]}

    monkeypatch.setattr(module, "find_existing_record", lookup)
    monkeypatch.setattr(module, "send_json", create_response)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    assert result["state"] == "passed"
    assert post_count == 1
    assert result["ambiguous_create_count"] == 1
    assert result["reconciled_create_count"] == 1
    assert_counter_invariants(result)


@pytest.mark.parametrize("malformation", ["missing_fields", "wrong_title"])
def test_malformed_update_success_uses_only_bounded_idempotent_retry(
    tmp_path,
    monkeypatch,
    malformation,
):
    module = load_module()
    item = make_item(module, "item-1")
    attempts = 0
    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: "rec-1")

    def update_response(method, url, api_key, payload=None, **kwargs):
        nonlocal attempts
        attempts += 1
        expected_fields = dict(payload["records"][0]["fields"])
        if attempts == 1:
            if malformation == "missing_fields":
                return [{"id": "rec-1"}]
            expected_fields["Title"] = "Wrong title"
        return [{"id": "rec-1", "fields": expected_fields}]

    monkeypatch.setattr(module, "send_json", update_response)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        retry_backoff_seconds=0,
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    assert result["state"] == "passed"
    assert attempts == 2
    assert result["retry_count"] == 1


def test_duplicate_source_item_ids_fail_before_outcomes_map_lock_or_network(tmp_path, monkeypatch):
    module = load_module()
    duplicate_items = [make_item(module, "duplicate"), make_item(module, "duplicate")]
    network_calls = 0
    monkeypatch.setattr(module, "important_work_items", lambda: duplicate_items)

    def unexpected_network(*args, **kwargs):
        nonlocal network_calls
        network_calls += 1

    monkeypatch.setattr(module, "send_json", unexpected_network)

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    assert result["state"] == "failed"
    assert result["errors"] == ["teable_source:teable_source_duplicate_item_id"]
    assert len(result["item_outcomes"]) == 2
    assert result["row_attempted_count"] == 0
    assert network_calls == 0
    assert not (tmp_path / "sync.lock").exists()
    assert_counter_invariants(result)


def test_duplicate_batch_item_ids_are_rejected_before_mutation(monkeypatch):
    module = load_module()
    item = make_item(module, "duplicate")
    network_calls = 0

    def unexpected_network(*args, **kwargs):
        nonlocal network_calls
        network_calls += 1

    monkeypatch.setattr(module, "send_json", unexpected_network)
    with pytest.raises(RuntimeError, match="teable_create_batch_duplicate_item_id"):
        module.create_record_batch(
            "https://relay.example/api",
            "token",
            "tbl",
            [item, item],
            "2026-07-12T00:00:00Z",
        )
    with pytest.raises(RuntimeError, match="teable_update_batch_duplicate_item_id"):
        module.update_record_batch(
            "https://relay.example/api",
            "token",
            "tbl",
            [(item, "rec-1"), (item, "rec-2")],
            "2026-07-12T00:00:00Z",
        )
    assert network_calls == 0


def test_post_response_deadline_crossing_is_ambiguous_and_reconciled(tmp_path, monkeypatch):
    module = load_module()
    item = make_item(module, "item-1")
    post_count = 0
    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)

    def lookup(*args, expected_fields=None, **kwargs):
        return "rec-1" if expected_fields is not None else None

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"{}"

    def sent_then_deadline(*args, **kwargs):
        nonlocal post_count
        post_count += 1
        return FakeResponse()

    monkeypatch.setattr(module, "find_existing_record", lookup)
    monkeypatch.setattr(module, "open_teable_url", sent_then_deadline)
    monotonic_values = iter([0.0, 0.0, 0.0, 181.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    assert post_count == 1
    assert result["state"] == "failed"
    assert result["ambiguous_create_count"] == 1
    assert result["reconciled_create_count"] == 1
    assert result["deadline_exceeded"] is True


def test_pre_request_deadline_expiry_is_not_create_ambiguous(tmp_path, monkeypatch):
    module = load_module()
    item = make_item(module, "item-1")
    open_calls = 0
    monkeypatch.setattr(module, "important_work_items", lambda: [item])
    monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: None)

    def should_not_open(*args, **kwargs):
        nonlocal open_calls
        open_calls += 1
        raise AssertionError("deadline expired before request I/O")

    monkeypatch.setattr(module, "open_teable_url", should_not_open)
    monotonic_values = iter([0.0, 0.0, 181.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))

    result = module.sync_to_teable(
        api_key="token",
        api_base_url="https://relay.example/api",
        base_id=None,
        table_id="tbl",
        table_name="Work",
        sync_lock_path=governed_lock_path(module, tmp_path),
    )

    assert open_calls == 0
    assert result["state"] == "failed"
    assert result["failed_count"] == 1
    assert result["ambiguous_create_count"] == 0
    assert result["reconciled_create_count"] == 0
    assert result["deadline_exceeded"] is True


@pytest.mark.parametrize("blocked_lane", ["table", "field"])
def test_single_writer_lock_covers_table_and_field_setup_races(
    tmp_path,
    monkeypatch,
    blocked_lane,
):
    module = load_module()
    item = make_item(module, "item-1")
    entered = threading.Event()
    release = threading.Event()
    first_results: list[dict] = []
    setup_calls = 0
    lock_path = governed_lock_path(module, tmp_path)
    monkeypatch.setattr(module, "important_work_items", lambda: [item])

    def blocking_table(*args, **kwargs):
        nonlocal setup_calls
        setup_calls += 1
        entered.set()
        assert release.wait(5)
        return "tbl"

    def blocking_fields(*args, **kwargs):
        nonlocal setup_calls
        setup_calls += 1
        entered.set()
        assert release.wait(5)

    if blocked_lane == "table":
        monkeypatch.setattr(module, "resolve_or_create_table", blocking_table)
        monkeypatch.setattr(module, "ensure_fields", lambda *args, **kwargs: None)
        table_id = None
        base_id = "base"
    else:
        monkeypatch.setattr(module, "ensure_fields", blocking_fields)
        table_id = "tbl"
        base_id = None
    monkeypatch.setattr(module, "find_existing_record", lambda *args, **kwargs: "rec-1")
    monkeypatch.setattr(module, "update_record_batch", lambda *args, **kwargs: 1)

    kwargs = {
        "api_key": "token",
        "api_base_url": "https://relay.example/api",
        "base_id": base_id,
        "table_id": table_id,
        "table_name": "Work",
        "sync_lock_path": lock_path,
    }
    first = threading.Thread(target=lambda: first_results.append(module.sync_to_teable(**kwargs)))
    first.start()
    assert entered.wait(5)

    second_result = module.sync_to_teable(**kwargs)
    release.set()
    first.join(5)

    assert not first.is_alive()
    assert first_results[0]["state"] == "passed"
    assert second_result["state"] == "failed"
    assert second_result["errors"] == ["teable_lock:teable_sync_busy"]
    assert second_result["row_attempted_count"] == 0
    assert setup_calls == 1
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600


def test_main_empty_argv_does_not_fall_back_to_process_argv(tmp_path, monkeypatch):
    module = load_module()
    output = tmp_path / "receipt.json"
    csv_output = tmp_path / "receipt.csv"
    monkeypatch.setattr(module, "DEFAULT_OUTPUT", output)
    monkeypatch.setattr(module, "DEFAULT_CSV_OUTPUT", csv_output)
    monkeypatch.setattr(module.sys, "argv", ["prog", "--definitely-invalid"])

    assert module.main([]) == 0
    assert output.is_file()
    assert csv_output.is_file()


def test_requested_missing_credentials_exits_nonzero(tmp_path):
    module = load_module()
    output = tmp_path / "receipt.json"

    exit_code = module.main(["--sync", "--api-key", "", "--output", str(output)])

    assert exit_code == 2
    assert json.loads(output.read_text(encoding="utf-8"))["sync"]["state"] == "blocked"


def test_hub_failure_plus_teable_success_still_exits_nonzero(tmp_path, monkeypatch):
    module = load_module()
    output = tmp_path / "receipt.json"

    monkeypatch.setattr(
        module,
        "seed_hub_store",
        lambda **kwargs: {"state": "failed", "attempted": True, "errors": ["hub_http_503"]},
    )
    monkeypatch.setattr(
        module,
        "sync_to_teable",
        lambda **kwargs: {"state": "passed", "attempted": True, "errors": []},
    )

    exit_code = module.main(
        [
            "--seed-hub",
            "--hub-token",
            "hub-token",
            "--sync",
            "--api-key",
            "teable-token",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["hub_seed"]["state"] == "failed"
    assert payload["sync"]["state"] == "passed"
