from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = (
    ROOT
    / "Chummer.Run.Api"
    / "wwwroot"
    / "artifacts"
    / "mac-codex-release-pipeline"
    / "bootstrap.sh"
)


def run_bash(
    wrapper: Path,
    *,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("/bin/bash", str(wrapper)),
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("explicit_override", (False, True))
def test_bootstrap_preserves_portable_generator_lock_resolution(
    tmp_path: Path,
    explicit_override: bool,
) -> None:
    portable_tmp = tmp_path / "portable tmp"
    portable_tmp.mkdir()
    hub_alias = tmp_path / "hub-alias"
    hub_repo = tmp_path / "hub-repo"
    generator = hub_alias / "scripts" / "materialize_hub_local_release_proof.py"
    output_path = tmp_path / "generated-proof.json"
    observation_path = tmp_path / "generator-environment.txt"
    wrapper = tmp_path / "exercise-generator.sh"
    generator.parent.mkdir(parents=True)
    hub_repo.mkdir()
    generator.write_text(
        """\
from __future__ import annotations

import os
from pathlib import Path
import sys

Path(os.environ["CHUMMER_TEST_LOCK_OBSERVATION"]).write_text(
    os.environ.get("CHUMMER_HUB_LOCAL_PROOF_MUTATION_LOCK_PATH", ""),
    encoding="utf-8",
)
Path(sys.argv[1]).write_text("{}\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    wrapper.write_text(
        f"""\
#!/usr/bin/env bash
set -euo pipefail
source {shlex.quote(str(BOOTSTRAP))}
install_bootstrap_cleanup_traps
require_hub_projection_authority_handoffs() {{ :; }}
hub_local_release_proof_has_canonical_baseline() {{ [[ -f "$1" ]]; }}
RELEASE_PYTHON_BIN="$(command -v python3)"
generate_hub_local_release_proof \
  {shlex.quote(str(hub_alias))} \
  {shlex.quote(str(hub_repo))} \
  {shlex.quote(str(output_path))}
""",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["TMPDIR"] = str(portable_tmp)
    environment["CHUMMER_TEST_LOCK_OBSERVATION"] = str(observation_path)
    expected_override = tmp_path / "shared authority" / "public-edge-mutation.lock"
    if explicit_override:
        environment["CHUMMER_HUB_LOCAL_PROOF_MUTATION_LOCK_PATH"] = str(
            expected_override
        )
    else:
        environment.pop("CHUMMER_HUB_LOCAL_PROOF_MUTATION_LOCK_PATH", None)

    result = run_bash(wrapper, environment=environment)

    assert result.returncode == 0, (
        f"generator wrapper failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    observed = observation_path.read_text(encoding="utf-8")
    if explicit_override:
        assert observed == str(expected_override)
        assert list(portable_tmp.iterdir()) == []
    else:
        expected_default = (
            portable_tmp
            / f"chummer-public-edge-mutation-{os.getuid()}"
            / "public-edge-mutation.lock"
        )
        assert observed == str(expected_default)
        assert expected_default.parent.is_dir()
        assert expected_default.parent.stat().st_mode & 0o777 == 0o700
        assert not expected_default.exists()
    assert "/docker/" not in observed
    assert output_path.is_file()


def test_bootstrap_cleanup_is_idempotent_and_signal_safe(tmp_path: Path) -> None:
    portable_tmp = tmp_path / "bootstrap-tmp"
    portable_tmp.mkdir()
    observation_path = tmp_path / "temporary-paths.txt"
    wrapper = tmp_path / "exercise-signal-cleanup.sh"
    wrapper.write_text(
        f"""\
#!/usr/bin/env bash
set -euo pipefail
source {shlex.quote(str(BOOTSTRAP))}
install_bootstrap_cleanup_traps
temporary_file="$(mktemp "${{TMPDIR}}/bootstrap-file.XXXXXX")"
temporary_directory="$(mktemp -d "${{TMPDIR}}/bootstrap-directory.XXXXXX")"
bootstrap_tmp_paths+=("$temporary_file" "$temporary_directory")
printf '%s\\n%s\\n' "$temporary_file" "$temporary_directory" \
  > {shlex.quote(str(observation_path))}
kill -TERM "$$"
exit 92
""",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["TMPDIR"] = str(portable_tmp)

    result = run_bash(wrapper, environment=environment)

    assert result.returncode == 143, (
        f"expected signal exit 143, got {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    temporary_file, temporary_directory = (
        Path(value)
        for value in observation_path.read_text(encoding="utf-8").splitlines()
    )
    assert not temporary_file.exists()
    assert not temporary_directory.exists()
    assert list(portable_tmp.iterdir()) == []


def test_registry_validation_remains_fail_closed_after_portable_fallback(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "generated-proof.json"
    registry_validator = tmp_path / "registry_materializer.py"
    continued_path = tmp_path / "continued-after-registry-validation"
    wrapper = tmp_path / "exercise-registry-rejection.sh"
    registry_validator.write_text(
        """\
def load_release_proof(_path):
    raise RuntimeError("fixture Registry rejection")
""",
        encoding="utf-8",
    )
    wrapper.write_text(
        f"""\
#!/usr/bin/env bash
set -euo pipefail
source {shlex.quote(str(BOOTSTRAP))}
generate_hub_local_release_proof() {{
  printf '%s\\n' '{{"status":"pass"}}' > "$3"
}}
json_generated_at_health() {{
  printf '%s\\n' fresh
}}
generate_validated_hub_local_release_proof \
  ignored-alias \
  ignored-repo \
  {shlex.quote(str(output_path))} \
  86400 \
  300 \
  {shlex.quote(str(registry_validator))}
touch {shlex.quote(str(continued_path))}
""",
        encoding="utf-8",
    )

    result = run_bash(wrapper, environment=os.environ.copy())

    assert result.returncode != 0
    assert "Registry-incompatible receipt" in result.stderr
    assert "fixture Registry rejection" in result.stderr
    assert not continued_path.exists()
