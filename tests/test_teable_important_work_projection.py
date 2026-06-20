from __future__ import annotations

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


def test_projection_contains_unique_important_work_rows():
    module = load_module()

    rows = module.important_work_items()
    item_ids = [row.item_id for row in rows]

    assert len(rows) >= 25
    assert len(item_ids) == len(set(item_ids))
    assert "desktop-premium-ui-polish" in item_ids
    assert "origin-dossier-first-story" in item_ids
    assert "desktop-updater-install-link" in item_ids
    assert "public-website-minimal-redesign" in item_ids
    assert "character-builder-core-usability" in item_ids
    assert "release-policy-daily-08" in item_ids
    assert "teable-important-work-sync" in item_ids


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


def test_main_writes_dry_run_artifact_without_teable_credentials(tmp_path, monkeypatch):
    module = load_module()
    output = tmp_path / "TEABLE_IMPORTANT_WORK.generated.json"
    monkeypatch.delenv("TEABLE_API_KEY", raising=False)
    monkeypatch.delenv("CHUMMER_TEABLE_IMPORTANT_WORK_API_KEY", raising=False)

    exit_code = module.main(["--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["sync"]["state"] == "not_requested"
    assert payload["sync"]["attempted"] is False


def test_sync_without_credentials_fails_closed_without_token_text():
    module = load_module()

    result = module.sync_to_teable(
        api_key=None,
        api_base_url="https://app.teable.ai/api",
        base_id="base-demo",
        table_id="tbl-demo",
        table_name="Chummer Important Work",
    )

    assert result["state"] == "blocked"
    assert result["errors"] == ["teable_api_key_missing"]
    assert "Bearer" not in json.dumps(result)


def test_sync_upserts_to_configured_table(monkeypatch):
    module = load_module()
    requests: list[tuple[str, str, dict | None]] = []

    def fake_send_json(method: str, url: str, api_key: str, payload: dict | None = None, timeout: int = 60):
        requests.append((method, url, payload))
        assert api_key == "demo-token"
        if method == "GET" and "/field?" in url:
            return [{"name": field["name"]} for field in module.REQUIRED_FIELDS]
        if method == "GET" and "/record?" in url:
            return {"records": []}
        if method == "POST" and url.endswith("/record"):
            return {"records": [{"id": "rec-created"}]}
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setattr(module, "send_json", fake_send_json)

    result = module.sync_to_teable(
        api_key="demo-token",
        api_base_url="https://app.teable.ai/api",
        base_id=None,
        table_id="tbl-work",
        table_name="Chummer Important Work",
    )

    assert result["state"] == "passed"
    assert result["table_id"] == "tbl-work"
    assert result["synced_count"] == len(module.important_work_items())
    assert any(method == "GET" and "/field?" in url for method, url, _ in requests)
    assert sum(1 for method, url, _ in requests if method == "POST" and url.endswith("/record")) == len(module.important_work_items())
