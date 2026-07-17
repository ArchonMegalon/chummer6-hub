from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest import mock

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_google_oauth_linking_operator_evidence_artifact.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "import_google_oauth_linking_operator_evidence_artifact",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_rejects_missing_or_legacy_intake_before_any_write(tmp_path: Path) -> None:
    module = load_module()
    artifact = tmp_path / "proof.zip"
    artifact.write_bytes(b"not-a-zip")
    evidence_path = tmp_path / "published" / "evidence.json"
    with pytest.raises(SystemExit, match="intake request not found"):
        module.import_artifact(
            artifact,
            evidence_path=evidence_path,
            imported_screenshot_root=tmp_path / "imported",
            intake_request=tmp_path / "missing-request.json",
        )
    legacy = tmp_path / "legacy-request.json"
    legacy.write_text(json.dumps({"base_url": "https://chummer.run"}) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not current/actionable"):
        module.import_artifact(
            artifact,
            evidence_path=evidence_path,
            imported_screenshot_root=tmp_path / "imported",
            intake_request=legacy,
        )
    assert not evidence_path.exists()


def test_import_rejects_pytest_provenance_before_unpack_or_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    artifact = tmp_path / "proof.zip"
    artifact.write_bytes(b"not-a-zip")
    evidence_path = tmp_path / "published" / "evidence.json"
    monkeypatch.setattr(
        module,
        "load_intake_payload_for_import",
        lambda *args, **kwargs: {"status": "operator_action_required"},
    )
    with pytest.raises(SystemExit, match="pytest/test-fixture artifact provenance"):
        module.import_artifact(
            artifact,
            evidence_path=evidence_path,
            imported_screenshot_root=tmp_path / "imported",
            intake_request=tmp_path / "request.json",
        )
    assert not evidence_path.exists()


def test_post_import_plan_ignores_injected_request_commands(tmp_path: Path) -> None:
    module = load_module()
    marker = tmp_path / "command-injection-marker"
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "artifact_intake": {
                    "post_import_commands": [f"touch {marker}"],
                    "post_import_verify_command": f"touch {marker}",
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    plan = module.post_import_commands(request, module.DEFAULT_BASE_URL)
    assert plan == module.evidence_v2.fixed_post_import_argv_plan(
        base_url=module.DEFAULT_BASE_URL,
        request_path=request,
        evidence_path=module.DEFAULT_OPERATOR_EVIDENCE_PATH,
    )
    assert all(isinstance(argv, list) for argv in plan)
    assert not any(str(marker) in argument for argv in plan for argument in argv)
    assert not marker.exists()


def test_run_post_import_chain_uses_fixed_argv_without_shell(tmp_path: Path) -> None:
    module = load_module()
    request = tmp_path / "request.json"
    request.write_text("{}\n", encoding="utf-8")
    observed: list[list[str]] = []

    def fake_run(argv: list[str], cwd: Path) -> dict[str, object]:
        observed.append(argv)
        return {
            "argv": argv,
            "returncode": 1 if any(item.endswith("verify_google_oauth_linking_operator_evidence_request.py") for item in argv) else 0,
            "stdout_tail": [],
            "stderr_tail": [],
        }

    with mock.patch.object(module, "run_command", side_effect=fake_run):
        returncode, results = module.run_post_import_chain(request, module.DEFAULT_BASE_URL)
    assert returncode == 1
    assert observed == module.post_import_argv_plan(request, module.DEFAULT_BASE_URL)
    assert len(results) == 4


def test_run_command_passes_argv_with_shell_disabled(tmp_path: Path) -> None:
    module = load_module()
    completed = mock.Mock(returncode=0, stdout="", stderr="")
    with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
        result = module.run_command(["python3", "-c", "print('ok')"], tmp_path)
    assert result["returncode"] == 0
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.args[0] == ["python3", "-c", "print('ok')"]
