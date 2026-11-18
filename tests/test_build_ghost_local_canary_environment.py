"""Execute canary preflight with fake Docker; never contact a daemon/provider."""

import subprocess
from pathlib import Path

import pytest

from test_build_ghost_first_provider_disabled_rollout import (
    ROOT,
    docker_calls,
    patch_state,
    rollback_fixture,
)


CANARY = ROOT / "ops/build-ghost-private-nonprod/run-local-canary.sh"
GATES = (
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED",
    "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_REMOTE_EXECUTION_ENABLED",
)


def run_preflight(fixture):
    # These tests stop before cp and must not depend on an installed ripgrep
    # or allow an accidental real HTTP call. Advertise the later-phase tools
    # for require_command/type -P, but fail loudly if either is ever executed.
    # This is not proof that the deployment host has those runtime tools.
    binary_root = Path(fixture["env"]["PATH"].split(":", 1)[0])
    for name in ("rg", "curl"):
        executable = binary_root / name
        executable.write_text("#!/bin/sh\nprintf 'unexpected-canary-auxiliary-execution\\n' >&2\nexit 88\n")
        executable.chmod(0o700)
    result = subprocess.run(
        ["bash", str(CANARY)],
        env=fixture["env"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert "unexpected-canary-auxiliary-execution" not in result.stdout + result.stderr
    return result


@pytest.mark.parametrize("gate", GATES)
@pytest.mark.parametrize("values", ([], ["true"], [""], ["FALSE"], ["false", "false"], ["false", "true"], ["true", "false"]))
def test_canary_rejects_each_unsafe_gate_before_any_runtime_request(tmp_path, gate, values):
    fixture = rollback_fixture(tmp_path)
    patch_state(fixture, gate_values_by_name={gate: [gate + "=" + value for value in values]})
    result = run_preflight(fixture)
    assert result.returncode != 0
    assert f"positive_canary=failed stage=provider-gates gate={gate}" in result.stdout
    calls = docker_calls(fixture)
    assert calls and all(call[0] in ("ps", "inspect") for call in calls)
    assert "synthetic-do-not-print" not in result.stdout + result.stderr


def test_canary_admits_exact_false_assignments_without_disclosing_other_environment(tmp_path):
    fixture = rollback_fixture(tmp_path)
    patch_state(fixture, gate_values_by_name={
        gate: [gate + "=false", gate + "_OTHER=true", "SECRET=synthetic-do-not-print"]
        for gate in GATES
    })
    result = run_preflight(fixture)
    # Fake Docker deliberately stops at the first cp: no certificate, HTTP,
    # grant, workspace or provider operation is performed in this test.
    assert result.returncode == 87
    calls = docker_calls(fixture)
    assert calls[-1][0] == "cp"
    env_calls = [call for call in calls if call[0] == "inspect"]
    assert len(env_calls) == len(GATES)
    for gate, call in zip(GATES, env_calls, strict=True):
        assert f'"{gate}="' in call[-1]
        assert '}}entry{{if eq . ' in call[-1]
        assert '{{println .}}' not in call[-1]
    assert "synthetic-do-not-print" not in result.stdout + result.stderr + fixture["log"].read_text()


def test_canary_rejects_inspect_failure_even_if_partial_output_matches(tmp_path):
    fixture = rollback_fixture(tmp_path)
    patch_state(fixture, environment_inspect_exit=42)
    result = run_preflight(fixture)
    assert result.returncode != 0
    assert f"positive_canary=failed stage=provider-gates gate={GATES[0]}" in result.stdout
    assert all(call[0] in ("ps", "inspect") for call in docker_calls(fixture))
    assert "synthetic-do-not-print" not in result.stdout + result.stderr


def test_canary_rechecks_gates_after_lifecycle_proof_and_never_dumps_environment():
    source = CANARY.read_text(encoding="utf-8")
    call = 'canary_provider_gates_false "$ai_id"'
    assert source.count(call) == 2
    first, last = source.index(call), source.rindex(call)
    assert source.index('ai_id="$(container_id chummer-build-ghost-ai)"') < first
    assert first < source.index('docker cp "$edge_id:') < source.index('support_response=')
    assert source.index('positive_canary=failed stage=secret-or-lifecycle-cleanliness') < last
    assert last < source.index('closed_status=')
    assert '{{println .}}' not in source
    assert '{{json .Config.Env}}' not in source
    assert '2>/dev/null)' in source
