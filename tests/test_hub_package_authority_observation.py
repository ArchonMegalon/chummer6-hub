"""Observation may propose hashes; it must never admit them as release authority."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/package-authority-observation.yml"


def parse_workflow(path: Path):
    # The repository's lightweight yaml.py folds block scalars and cannot
    # validate runnable workflow scripts. Use the same isolated system PyYAML
    # interpreter that the hosted workflow explicitly installs and checks.
    result = subprocess.run(
        ["/usr/bin/python3", "-I", "-c",
         "import json, sys, yaml; "
         "assert hasattr(yaml, '__version__'); "
         "value = yaml.safe_load(sys.stdin.read()); "
         "value['on'] = value.pop(True) if True in value else value['on']; "
         "print(json.dumps(value))"],
        input=path.read_text(encoding="utf-8"), text=True,
        capture_output=True, check=True, timeout=10,
    )
    return json.loads(result.stdout)


@lru_cache(maxsize=1)
def workflow():
    return parse_workflow(WORKFLOW)


def test_observer_has_only_read_permission_and_no_protected_environment():
    value = workflow()
    assert value["permissions"] == {"contents": "read"}
    triggers = value.get("on", value.get(True))
    assert set(triggers) == {"workflow_dispatch", "pull_request"}
    assert set(value["jobs"]) == {"observe"}
    job = value["jobs"]["observe"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == 20
    assert "environment" not in job
    assert "secrets" not in WORKFLOW.read_text(encoding="utf-8").lower()
    assert value["concurrency"]["cancel-in-progress"] is False


def test_observer_actions_are_immutable_and_checkout_does_not_retain_credentials():
    steps = workflow()["jobs"]["observe"]["steps"]
    actions = [step for step in steps if "uses" in step]
    assert len(actions) == 2
    assert all(re.fullmatch(r"actions/(checkout|upload-artifact)@[0-9a-f]{40}", step["uses"]) for step in actions)
    assert actions[0]["with"]["persist-credentials"] is False
    scripts = "\n".join(step.get("run", "") for step in steps)
    assert 'test "$(git rev-parse HEAD)" = "${GITHUB_SHA}"' in scripts
    assert scripts.count('git status --porcelain --untracked-files=all') == 2


def test_observer_uses_the_exact_selected_core_bundle_and_recipe_validator():
    lock = json.loads((ROOT / "eng/package-plane.lock.json").read_text(encoding="utf-8"))
    steps = workflow()["jobs"]["observe"]["steps"]
    scripts = "\n".join(step.get("run", "") for step in steps)
    assert lock["core_runtime"]["bundle"]["url"] in scripts
    assert lock["core_runtime"]["bundle"]["sha256"] in scripts
    assert lock["dotnet_install"]["sha256"] in scripts
    assert f'--version {lock["dotnet_sdk"]}' in scripts
    assert "--max-filesize 16777216" in scripts
    assert "--proto-redir '=https'" in scripts
    assert "module.validate_build_recipe(root, lock)" in scripts
    assert "module.materialize_core_runtime_feed(" in scripts


def test_observed_bytes_cannot_be_labeled_a_locked_feed_or_publish_result():
    steps = workflow()["jobs"]["observe"]["steps"]
    scripts = "\n".join(step.get("run", "") for step in steps)
    assert scripts.count("--observe-package-authority") == 1
    assert 'test ! -e "${RUNNER_TEMP}/hub-observer-feed/chummer-hub-packages.inventory.json"' in scripts
    assert "--prebuilt-hub-feed-input" not in scripts
    assert "--validate-only" not in scripts
    for forbidden in ("git push", "gh release", "nuget push", "docker push", "continue-on-error"):
        assert forbidden not in WORKFLOW.read_text(encoding="utf-8")
    artifact = steps[-1]["with"]
    assert artifact["name"].startswith("hub-package-observation-")
    assert artifact["if-no-files-found"] == "error"
    assert artifact["overwrite"] is False
    assert artifact["include-hidden-files"] is False
    assert artifact["retention-days"] == 30
    assert "eng/package-plane.lock.json" in artifact["path"]
    assert "eng/core-main-runtime-artifact-authority.json" in artifact["path"]


def test_required_consumer_remains_independent_and_strict():
    text = (ROOT / ".github/workflows/package-plane.yml").read_text(encoding="utf-8")
    value = parse_workflow(ROOT / ".github/workflows/package-plane.yml")
    assert "no-siblings" in value["jobs"]
    assert "needs" not in value["jobs"]["no-siblings"]
    assert "--observe-package-authority" not in text
    assert "continue-on-error" not in text
    assert "verify-hub-package-plane.py" in text


def test_every_observer_shell_script_parses_as_a_real_multiline_block():
    scripts = [step["run"] for step in workflow()["jobs"]["observe"]["steps"] if "run" in step]
    assert len(scripts) == 3
    for script in scripts:
        assert script.startswith("set -euo pipefail\n")
        subprocess.run(["bash", "-n"], input=script, text=True,
                       capture_output=True, check=True, timeout=10)
    embedded = scripts[1].split("python3 -I - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    compile(embedded, str(WORKFLOW), "exec")
