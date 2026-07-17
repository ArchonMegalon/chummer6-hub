from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "restore_public_edge_portal_image.py"


def load_module():
    spec = importlib.util.spec_from_file_location("restore_public_edge_portal_image", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_restore_retages_and_recreates_when_container_or_tag_drift(monkeypatch, tmp_path) -> None:
    module = load_module()
    expected = "sha256:" + "1" * 64
    dirty = "sha256:" + "2" * 64
    commands: list[list[str]] = []

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        commands.append(command)
        if command == ["docker", "image", "inspect", "--format", "{{.Id}}", expected]:
            return module.CommandResult(command, 0, expected, "")
        if command == ["docker", "image", "inspect", "--format", "{{.Id}}", "chummer-run-api:local"]:
            return module.CommandResult(command, 0, dirty, "")
        if command == ["docker", "inspect", "portal"]:
            return module.CommandResult(
                command,
                0,
                json.dumps(
                    [
                        {
                            "Id": "prior-portal-container",
                            "Image": dirty,
                            "Config": {"Image": "chummer-run-api:local"},
                            "State": {"Status": "running", "Running": True, "ExitCode": 0},
                        }
                    ]
                ),
                "",
            )
        return module.CommandResult(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)

    result = module.restore_portal_image(
        expected,
        ["chummer-run-api:local"],
        tmp_path / "docker-compose.public-edge.yml",
        tmp_path / ".env",
        "chummer6-hub",
        "chummer-portal",
        "portal",
        False,
        False,
    )

    assert ["docker", "tag", expected, "chummer-run-api:local"] in commands
    stop_command = [
        "docker",
        "compose",
        "--env-file",
        str(tmp_path / ".env"),
        "-p",
        "chummer6-hub",
        "-f",
        str(tmp_path / "docker-compose.public-edge.yml"),
        "stop",
        "chummer-portal",
    ]
    assert stop_command in commands
    initializer_command = [
        "docker",
        "compose",
        "--env-file",
        str(tmp_path / ".env"),
        "-p",
        "chummer6-hub",
        "-f",
        str(tmp_path / "docker-compose.public-edge.yml"),
        "run",
        "--rm",
        "--no-deps",
        "chummer-portal-volume-init",
    ]
    assert initializer_command in commands
    portal_command = [
        "docker",
        "compose",
        "--env-file",
        str(tmp_path / ".env"),
        "-p",
        "chummer6-hub",
        "-f",
        str(tmp_path / "docker-compose.public-edge.yml"),
        "up",
        "-d",
        "--no-build",
        "--no-deps",
        "--force-recreate",
        "chummer-portal",
    ]
    assert [
        "docker",
        "compose",
        "--env-file",
        str(tmp_path / ".env"),
        "-p",
        "chummer6-hub",
        "-f",
        str(tmp_path / "docker-compose.public-edge.yml"),
        "up",
        "-d",
        "--no-build",
        "--no-deps",
        "--force-recreate",
        "chummer-portal",
    ] in commands
    assert commands.index(stop_command) < commands.index(initializer_command) < commands.index(portal_command)
    assert result["containerRecreated"] is True
    assert result["portalQuiesceCommand"] == stop_command
    assert result["volumeInitializerCommand"] == initializer_command
    assert result["imageTags"][0]["retagged"] is True


def test_restore_skips_recreate_when_container_and_tag_match(monkeypatch, tmp_path) -> None:
    module = load_module()
    expected = "sha256:" + "a" * 64
    commands: list[list[str]] = []

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        commands.append(command)
        if command[:4] == ["docker", "image", "inspect", "--format"]:
            return module.CommandResult(command, 0, expected, "")
        if command == ["docker", "inspect", "portal"]:
            return module.CommandResult(
                command,
                0,
                json.dumps(
                    [
                        {
                            "Image": expected,
                            "Config": {"Image": "chummer-run-api:local"},
                            "State": {"Status": "running", "Running": True, "ExitCode": 0},
                        }
                    ]
                ),
                "",
            )
        return module.CommandResult(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)

    result = module.restore_portal_image(
        expected,
        ["chummer-run-api:local"],
        tmp_path / "docker-compose.public-edge.yml",
        None,
        "chummer6-hub",
        "chummer-portal",
        "portal",
        False,
        False,
    )

    assert not any(command[:2] == ["docker", "tag"] for command in commands)
    assert not any(command[:2] == ["docker", "compose"] for command in commands)
    assert result["containerRecreated"] is False
    assert result["volumeInitializerCommand"] == []
    assert result["imageTags"][0]["retagged"] is False


def test_restore_recreates_when_container_matches_but_is_not_running(monkeypatch, tmp_path) -> None:
    module = load_module()
    expected = "sha256:" + "b" * 64
    commands: list[list[str]] = []

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        commands.append(command)
        if command[:4] == ["docker", "image", "inspect", "--format"]:
            return module.CommandResult(command, 0, expected, "")
        if command == ["docker", "inspect", "portal"]:
            return module.CommandResult(
                command,
                0,
                json.dumps(
                    [
                        {
                            "Image": expected,
                            "Config": {"Image": "chummer-run-api:local"},
                            "State": {
                                "Status": "exited",
                                "Running": False,
                                "ExitCode": 0,
                                "StartedAt": "2026-07-02T11:00:00Z",
                                "FinishedAt": "2026-07-02T11:01:00Z",
                            },
                        }
                    ]
                ),
                "",
            )
        if command == ["docker", "image", "inspect", expected]:
            return module.CommandResult(command, 0, json.dumps([{"Id": expected, "Config": {"Labels": {}}}]), "")
        return module.CommandResult(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)

    result = module.restore_portal_image(
        expected,
        ["chummer-run-api:local"],
        tmp_path / "docker-compose.public-edge.yml",
        None,
        "chummer6-hub",
        "chummer-portal",
        "portal",
        False,
        False,
    )

    compose_commands = [command for command in commands if command[:2] == ["docker", "compose"]]
    assert ["stop", "chummer-portal"] == compose_commands[0][-2:]
    assert compose_commands[1][-1] == "chummer-portal-volume-init"
    assert compose_commands[2][-1] == "chummer-portal"
    assert result["containerRecreated"] is True
    assert result["containerStatusBefore"] == "exited"
    assert result["containerRunningBefore"] is False


def test_initializer_failure_restarts_quiesced_prior_container(monkeypatch, tmp_path) -> None:
    module = load_module()
    expected = "sha256:" + "1" * 64
    dirty = "sha256:" + "2" * 64
    prior_container = "prior-portal-container"
    commands: list[list[str]] = []

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        commands.append(command)
        if command == ["docker", "image", "inspect", "--format", "{{.Id}}", expected]:
            return module.CommandResult(command, 0, expected, "")
        if command == ["docker", "image", "inspect", "--format", "{{.Id}}", "chummer-run-api:local"]:
            return module.CommandResult(command, 0, dirty, "")
        if command == ["docker", "inspect", "portal"]:
            return module.CommandResult(
                command,
                0,
                json.dumps(
                    [
                        {
                            "Id": prior_container,
                            "Image": dirty,
                            "Config": {"Image": "chummer-run-api:local"},
                            "State": {"Status": "running", "Running": True, "ExitCode": 0},
                        }
                    ]
                ),
                "",
            )
        if command[:2] == ["docker", "compose"] and command[-1] == "chummer-portal-volume-init":
            return module.CommandResult(command, 37, "", "initializer failed")
        return module.CommandResult(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)

    with pytest.raises(RuntimeError, match="initializer failed"):
        module.restore_portal_image(
            expected,
            ["chummer-run-api:local"],
            tmp_path / "docker-compose.public-edge.yml",
            None,
            "chummer6-hub",
            "chummer-portal",
            "portal",
            False,
            False,
        )

    stop_index = next(index for index, command in enumerate(commands) if command[-2:] == ["stop", "chummer-portal"])
    init_index = next(index for index, command in enumerate(commands) if command[-1] == "chummer-portal-volume-init")
    restart_index = commands.index(["docker", "start", prior_container])
    assert stop_index < init_index < restart_index
    assert not any(command[:2] == ["docker", "compose"] and "up" in command for command in commands)


def test_recreate_failure_falls_back_to_prior_image_when_prior_container_is_gone(monkeypatch, tmp_path) -> None:
    module = load_module()
    expected = "sha256:" + "3" * 64
    dirty = "sha256:" + "4" * 64
    prior_container = "prior-portal-container"
    commands: list[list[str]] = []
    portal_up_attempts = 0

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        nonlocal portal_up_attempts
        commands.append(command)
        if command == ["docker", "image", "inspect", "--format", "{{.Id}}", expected]:
            return module.CommandResult(command, 0, expected, "")
        if command == ["docker", "image", "inspect", "--format", "{{.Id}}", "chummer-run-api:local"]:
            return module.CommandResult(command, 0, dirty, "")
        if command == ["docker", "inspect", "portal"]:
            return module.CommandResult(
                command,
                0,
                json.dumps(
                    [
                        {
                            "Id": prior_container,
                            "Image": dirty,
                            "Config": {"Image": "chummer-run-api:local"},
                            "State": {"Status": "running", "Running": True, "ExitCode": 0},
                        }
                    ]
                ),
                "",
            )
        if command == ["docker", "start", prior_container]:
            return module.CommandResult(command, 1, "", "container was removed")
        if command[:2] == ["docker", "compose"] and "up" in command:
            portal_up_attempts += 1
            if portal_up_attempts == 1:
                return module.CommandResult(command, 41, "", "recreate failed")
        return module.CommandResult(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)

    with pytest.raises(RuntimeError, match="recreate failed"):
        module.restore_portal_image(
            expected,
            ["chummer-run-api:local"],
            tmp_path / "docker-compose.public-edge.yml",
            None,
            "chummer6-hub",
            "chummer-portal",
            "portal",
            False,
            False,
        )

    stop_index = next(index for index, command in enumerate(commands) if command[-2:] == ["stop", "chummer-portal"])
    init_index = next(index for index, command in enumerate(commands) if command[-1] == "chummer-portal-volume-init")
    up_indexes = [index for index, command in enumerate(commands) if command[:2] == ["docker", "compose"] and "up" in command]
    start_index = commands.index(["docker", "start", prior_container])
    rollback_tag_index = commands.index(["docker", "tag", dirty, "chummer-run-api:local"])
    assert stop_index < init_index < up_indexes[0] < start_index < rollback_tag_index < up_indexes[1]
    assert portal_up_attempts == 2


def test_restore_receipt_captures_drift_image_details(monkeypatch, tmp_path) -> None:
    module = load_module()
    expected = "sha256:" + "1" * 64
    dirty = "sha256:" + "2" * 64

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        if command == ["docker", "image", "inspect", "--format", "{{.Id}}", expected]:
            return module.CommandResult(command, 0, expected, "")
        if command == ["docker", "image", "inspect", "--format", "{{.Id}}", "chummer-run-api:local"]:
            return module.CommandResult(command, 0, dirty, "")
        if command == ["docker", "inspect", "portal"]:
            return module.CommandResult(
                command,
                0,
                json.dumps(
                    [
                        {
                            "Image": dirty,
                            "Config": {"Image": "chummer-run-api:local"},
                            "State": {"Status": "running", "Running": True, "ExitCode": 0},
                        }
                    ]
                ),
                "",
            )
        if command == ["docker", "image", "inspect", expected]:
            return module.CommandResult(
                command,
                0,
                json.dumps(
                    [
                        {
                            "Id": expected,
                            "Created": "2026-07-01T10:00:00Z",
                            "RepoTags": ["chummer-run-api:protected-clean"],
                            "RepoDigests": [],
                            "Config": {"Labels": {"source": "approved"}},
                        }
                    ]
                ),
                "",
            )
        if command == ["docker", "image", "inspect", dirty]:
            return module.CommandResult(
                command,
                0,
                json.dumps(
                    [
                        {
                            "Id": dirty,
                            "Created": "2026-07-01T11:00:00Z",
                            "RepoTags": ["chummer-run-api:local"],
                            "RepoDigests": [],
                            "Config": {"Labels": {"source": "dirty-build"}},
                        }
                    ]
                ),
                "",
            )
        return module.CommandResult(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)

    result = module.restore_portal_image(
        expected,
        ["chummer-run-api:local"],
        tmp_path / "docker-compose.public-edge.yml",
        None,
        "chummer6-hub",
        "chummer-portal",
        "portal",
        False,
        False,
    )

    assert result["sourceImageDetails"]["labels"] == {"source": "approved"}
    assert result["containerImageDetailsBefore"]["created"] == "2026-07-01T11:00:00Z"
    assert result["containerImageDetailsBefore"]["labels"] == {"source": "dirty-build"}
    assert result["imageTags"][0]["imageDetailsBefore"]["repoTags"] == ["chummer-run-api:local"]


def test_restore_rejects_non_digest_expected_image() -> None:
    module = load_module()

    try:
        module.require_sha256_image_id("chummer-run-api:local")
    except ValueError as error:
        assert "expected a sha256:<64 hex> image id" in str(error)
    else:
        raise AssertionError("non-digest image id was accepted")


def test_resolve_image_tags_includes_matching_public_edge_aliases(monkeypatch) -> None:
    module = load_module()

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        if command == ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"]:
            return module.CommandResult(
                command,
                0,
                "\n".join(
                    [
                        "chummer-run-api:local",
                        "chummer-run-api:pwa-direct-20260702-0925",
                        "chummer-run-api:pwa-direct-mobile-alias-cba57",
                        "chummer-run-api:current-source-mobile-alias-20260702",
                        "chummer-run-api:fixed-alias-07d1060-20260702",
                        "chummer-run-api:<none>",
                        "other-service:pwa-direct-ignore",
                    ]
                ),
                "",
            )
        return module.CommandResult(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)

    result = module.resolve_image_tags(
        ["chummer-run-api:local"],
        [
            r"^chummer-run-api:pwa-direct",
            r"^chummer-run-api:current-source",
            r"^chummer-run-api:fixed-alias",
        ],
        dry_run=False,
    )

    assert result == [
        "chummer-run-api:local",
        "chummer-run-api:pwa-direct-20260702-0925",
        "chummer-run-api:pwa-direct-mobile-alias-cba57",
        "chummer-run-api:current-source-mobile-alias-20260702",
        "chummer-run-api:fixed-alias-07d1060-20260702",
    ]


def test_resolve_image_tags_defaults_to_local_without_patterns(monkeypatch) -> None:
    module = load_module()
    calls: list[list[str]] = []

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        calls.append(command)
        return module.CommandResult(command, 0, "chummer-run-api:pwa-direct-dirty", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)

    assert module.resolve_image_tags([], [], dry_run=False) == ["chummer-run-api:local"]
    assert calls == []


def test_resolve_image_tags_discovers_runtime_aliases_for_dirty_container_image(monkeypatch) -> None:
    module = load_module()
    dirty = "sha256:" + "7" * 64

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        if command == ["docker", "image", "inspect", dirty]:
            return module.CommandResult(
                command,
                0,
                json.dumps(
                    [
                        {
                            "Id": dirty,
                            "Created": "2026-07-02T10:00:00Z",
                            "RepoTags": [
                                "chummer-run-api:local",
                                "chummer-run-api:zz-07d1060-mobile-alias-keep",
                                "other-service:ignore-me",
                            ],
                            "RepoDigests": [],
                            "Config": {"Labels": {}},
                        }
                    ]
                ),
                "",
            )
        if command == ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"]:
            return module.CommandResult(command, 0, "", "")
        return module.CommandResult(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)

    result = module.resolve_image_tags(
        ["chummer-run-api:local"],
        [],
        container_image_id=dirty,
        dry_run=False,
    )

    assert result == [
        "chummer-run-api:local",
        "chummer-run-api:zz-07d1060-mobile-alias-keep",
    ]


def test_postdeploy_gate_retries_until_runtime_is_warm(monkeypatch, tmp_path) -> None:
    module = load_module()
    expected = "sha256:" + "3" * 64
    output_path = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    calls: list[list[str]] = []

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        calls.append(command)
        if len(calls) == 1:
            output_path.write_text(
                json.dumps({"status": "fail", "portalRuntimeImageStatus": "pass"}),
                encoding="utf-8",
            )
            return module.CommandResult(command, 1, "", "warming")
        output_path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "portalRuntimeImageStatus": "pass",
                    "releaseManifestVersion": "run-test",
                }
            ),
            encoding="utf-8",
        )
        return module.CommandResult(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.run_postdeploy_gate(
        expected,
        "https://chummer.run",
        "public_stable",
        "portal",
        "chummer-run-api:local",
        output_path,
        2,
        0,
        [],
        420,
        None,
        False,
    )

    assert len(calls) == 2
    assert result["status"] == "pass"
    assert result["attempts"][0]["status"] == "fail"
    assert result["attempts"][1]["status"] == "pass"


def test_postdeploy_gate_forwards_browser_proof_requirements(monkeypatch, tmp_path) -> None:
    module = load_module()
    expected = "sha256:" + "6" * 64
    output_path = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    artifact_dir = tmp_path / "browser-artifacts"
    calls: list[list[str]] = []

    def fake_run_command(command, cwd=module.ROOT, dry_run=False):
        calls.append(command)
        output_path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "portalRuntimeImageStatus": "pass",
                    "browserPlaywrightStatus": "pass",
                    "browserPlaywrightRequiredProofs": [
                        "downloadsStatus",
                        "mobilePwaViewport",
                        "frontdoorNavigation",
                    ],
                }
            ),
            encoding="utf-8",
        )
        return module.CommandResult(command, 0, "", "")

    monkeypatch.setattr(module, "run_command", fake_run_command)

    result = module.run_postdeploy_gate(
        expected,
        "https://chummer.run",
        "preview",
        "portal",
        "chummer-run-api:local",
        output_path,
        1,
        0,
        ["downloadsStatus", "mobilePwaViewport", "frontdoorNavigation"],
        180,
        artifact_dir,
        False,
    )

    command = calls[0]
    assert command[command.index("--expected-release-channel") + 1] == "preview"
    assert "--require-downloads-status-playwright" in command
    assert "--require-mobile-pwa-viewport-playwright" in command
    assert "--require-frontdoor-navigation-playwright" in command
    assert command[command.index("--playwright-timeout-seconds") + 1] == "180"
    assert command[command.index("--playwright-artifact-dir") + 1] == str(artifact_dir)
    assert result["browserPlaywrightStatus"] == "pass"
    assert result["browserPlaywrightRequiredProofs"] == [
        "downloadsStatus",
        "mobilePwaViewport",
        "frontdoorNavigation",
    ]


def test_stability_watch_repairs_drift_before_postdeploy(monkeypatch, tmp_path) -> None:
    module = load_module()
    expected = "sha256:" + "4" * 64
    dirty = "sha256:" + "5" * 64
    states = [
        {
            "expectedImageId": expected,
            "containerImageId": expected,
            "imageTags": [{"tag": "chummer-run-api:local", "imageId": expected}],
            "drift": [],
        },
        {
            "expectedImageId": expected,
            "containerImageId": dirty,
            "imageTags": [{"tag": "chummer-run-api:local", "imageId": dirty}],
            "drift": [f"portal container points at {dirty}", f"portal image tag chummer-run-api:local points at {dirty}"],
        },
        {
            "expectedImageId": expected,
            "containerImageId": expected,
            "imageTags": [{"tag": "chummer-run-api:local", "imageId": expected}],
            "drift": [],
        },
    ]
    repairs: list[dict[str, object]] = []
    monotonic_values = iter([0.0, 0.1, 0.2, 2.0])

    def fake_inspect_runtime_state(*_args, **_kwargs):
        return states.pop(0) if states else {
            "expectedImageId": expected,
            "containerImageId": expected,
            "imageTags": [{"tag": "chummer-run-api:local", "imageId": expected}],
            "drift": [],
        }

    def fake_restore_portal_image(*_args, **_kwargs):
        repair = {"expectedImageId": expected, "containerRecreated": True}
        repairs.append(repair)
        return repair

    monkeypatch.setattr(module, "inspect_runtime_state", fake_inspect_runtime_state)
    monkeypatch.setattr(module, "restore_portal_image", fake_restore_portal_image)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))

    result = module.watch_runtime_stability(
        expected,
        ["chummer-run-api:local"],
        tmp_path / "docker-compose.public-edge.yml",
        None,
        "chummer6-hub",
        "chummer-portal",
        "portal",
        1.0,
        0.0,
        2,
        False,
    )

    assert result["status"] == "pass"
    assert result["skipped"] is False
    assert result["repairCount"] == 1
    assert len(result["driftEvents"]) == 1
    assert repairs == [{"expectedImageId": expected, "containerRecreated": True}]


def test_stability_watch_repairs_stopped_container_even_when_image_matches(monkeypatch, tmp_path) -> None:
    module = load_module()
    expected = "sha256:" + "8" * 64
    states = [
        {
            "expectedImageId": expected,
            "containerImageId": expected,
            "containerStatus": "running",
            "containerRunning": True,
            "imageTags": [{"tag": "chummer-run-api:local", "imageId": expected}],
            "drift": [],
        },
        {
            "expectedImageId": expected,
            "containerImageId": expected,
            "containerStatus": "exited",
            "containerRunning": False,
            "imageTags": [{"tag": "chummer-run-api:local", "imageId": expected}],
            "drift": ["portal container is not running (status exited)"],
        },
        {
            "expectedImageId": expected,
            "containerImageId": expected,
            "containerStatus": "running",
            "containerRunning": True,
            "imageTags": [{"tag": "chummer-run-api:local", "imageId": expected}],
            "drift": [],
        },
    ]
    repairs: list[dict[str, object]] = []
    monotonic_values = iter([0.0, 0.1, 0.2, 2.0])

    def fake_inspect_runtime_state(*_args, **_kwargs):
        return states.pop(0) if states else {
            "expectedImageId": expected,
            "containerImageId": expected,
            "containerStatus": "running",
            "containerRunning": True,
            "imageTags": [{"tag": "chummer-run-api:local", "imageId": expected}],
            "drift": [],
        }

    def fake_restore_portal_image(*_args, **_kwargs):
        repair = {"expectedImageId": expected, "containerRecreated": True}
        repairs.append(repair)
        return repair

    monkeypatch.setattr(module, "inspect_runtime_state", fake_inspect_runtime_state)
    monkeypatch.setattr(module, "restore_portal_image", fake_restore_portal_image)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))

    result = module.watch_runtime_stability(
        expected,
        ["chummer-run-api:local"],
        tmp_path / "docker-compose.public-edge.yml",
        None,
        "chummer6-hub",
        "chummer-portal",
        "portal",
        1.0,
        0.0,
        2,
        False,
    )

    assert result["status"] == "pass"
    assert result["repairCount"] == 1
    assert result["driftEvents"][0]["drift"] == ["portal container is not running (status exited)"]
    assert repairs == [{"expectedImageId": expected, "containerRecreated": True}]
