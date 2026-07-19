from __future__ import annotations

import json
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "scripts" / "release" / "verify_public_projection.sh"
MATERIALIZER_PATH = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"
DESKTOP_VERIFIER_PATH = REPO_ROOT / "scripts" / "verify_desktop_native_trust_receipts.py"
M120_VERIFIER_PATH = REPO_ROOT / "scripts" / "verify_next90_m120_hub_public_launch_health.py"
M125_VERIFIER_PATH = REPO_ROOT / "scripts" / "verify_next90_m125_hub_public_signal_packets.py"
M126_VERIFIER_PATH = REPO_ROOT / "scripts" / "verify_next90_m126_hub_hosted_proof_contracts.py"
M144_VERIFIER_PATH = REPO_ROOT / "scripts" / "verify_next90_m144_hub_release_truth_alignment.py"
LIVE_WINDOWS_VERIFIER_PATH = REPO_ROOT / "scripts" / "verify_live_public_windows_installer.py"
MATERIALIZER = "materialize_hub_local_release_proof.py"
VERIFIERS = [
    "verify_next90_m120_hub_public_launch_health.py",
    "verify_next90_m125_hub_public_signal_packets.py",
    "verify_next90_m126_hub_hosted_proof_contracts.py",
    "verify_desktop_native_trust_receipts.py",
    "verify_next90_m144_hub_release_truth_alignment.py",
    "verify_live_public_windows_installer.py",
]


def _write_stub_scripts(repo_root: Path, *, failing_verifier: str | None = None) -> Path:
    scripts = repo_root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    call_log = repo_root / "calls.jsonl"
    materializer = scripts / MATERIALIZER
    materializer.write_text(
        """from __future__ import annotations
import json
import os
import sys
from pathlib import Path

record = {"script": Path(__file__).name, "args": sys.argv[1:], "cwd": str(Path.cwd()), "release_channel": os.environ.get("CHUMMER_HUB_RELEASE_CHANNEL_PATH"), "m144_release_channel": os.environ.get("CHUMMER_NEXT90_M144_RELEASE_CHANNEL"), "flagship_readiness": os.environ.get("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"), "require_current": os.environ.get("CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS")}
with Path(os.environ["CALL_LOG"]).open("a", encoding="utf-8") as output:
    output.write(json.dumps(record, sort_keys=True) + "\\n")
out_path = Path(sys.argv[1])
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text("{}\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    for verifier in VERIFIERS:
        exit_code = 17 if verifier == failing_verifier else 0
        (scripts / verifier).write_text(
            f"""from __future__ import annotations
import json
import os
from pathlib import Path

record = {{"script": Path(__file__).name, "args": [], "cwd": str(Path.cwd()), "release_channel": os.environ.get("CHUMMER_HUB_RELEASE_CHANNEL_PATH"), "m144_release_channel": os.environ.get("CHUMMER_NEXT90_M144_RELEASE_CHANNEL"), "flagship_readiness": os.environ.get("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"), "require_current": os.environ.get("CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS")}}
with Path(os.environ["CALL_LOG"]).open("a", encoding="utf-8") as output:
    output.write(json.dumps(record, sort_keys=True) + "\\n")
raise SystemExit({exit_code})
""",
            encoding="utf-8",
        )
    return call_log


def _prepare_relocated_repo(tmp_path: Path, *, failing_verifier: str | None = None) -> tuple[Path, Path]:
    repo_root = tmp_path / "relocated workspace" / "hub checkout"
    release_dir = repo_root / "scripts" / "release"
    release_dir.mkdir(parents=True)
    shutil.copy2(WRAPPER, release_dir / WRAPPER.name)
    (repo_root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    return repo_root, _write_stub_scripts(repo_root, failing_verifier=failing_verifier)


def _run_wrapper(repo_root: Path, call_log: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "CALL_LOG": str(call_log),
            "CHUMMER_PUBLIC_BASE_URL": "https://proof.example.invalid",
        }
    )
    release_channel = repo_root / "release authority" / "RELEASE_CHANNEL.generated.json"
    release_channel.parent.mkdir(parents=True, exist_ok=True)
    release_channel.write_text("{}\n", encoding="utf-8")
    environment["CHUMMER_RELEASE_CHANNEL_PATH"] = str(release_channel)
    flagship_readiness = repo_root / "release authority" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    flagship_readiness.write_text("{}\n", encoding="utf-8")
    environment["CHUMMER_FLEET_FLAGSHIP_READINESS_PATH"] = str(flagship_readiness)
    return subprocess.run(
        ["bash", str(repo_root / "scripts" / "release" / WRAPPER.name)],
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )


def _read_calls(call_log: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in call_log.read_text(encoding="utf-8").splitlines()]


def test_wrapper_resolves_its_relocated_checkout_and_runs_the_full_gate(tmp_path: Path) -> None:
    repo_root, call_log = _prepare_relocated_repo(tmp_path)
    unrelated_cwd = tmp_path / "caller cwd"
    unrelated_cwd.mkdir()

    result = _run_wrapper(repo_root, call_log, unrelated_cwd)

    assert result.returncode == 0, result.stdout
    assert result.stdout == "public projection ok\n"
    calls = _read_calls(call_log)
    assert [call["script"] for call in calls] == [MATERIALIZER, *VERIFIERS]
    assert all(call["cwd"] == str(repo_root) for call in calls)
    release_channel = str(repo_root / "release authority" / "RELEASE_CHANNEL.generated.json")
    assert all(call["release_channel"] == release_channel for call in calls)
    assert all(call["m144_release_channel"] == release_channel for call in calls)
    flagship_readiness = str(
        repo_root / "release authority" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    )
    assert all(call["flagship_readiness"] == flagship_readiness for call in calls)
    assert all(call["require_current"] == "1" for call in calls)
    assert calls[0]["args"] == [
        ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
        "https://proof.example.invalid",
        "docker-compose.yml",
        "120",
        "true",
    ]
    assert (repo_root / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json").is_file()
    assert not (unrelated_cwd / ".codex-studio").exists()


def test_wrapper_fails_closed_and_does_not_run_later_gates(tmp_path: Path) -> None:
    failing_verifier = VERIFIERS[2]
    repo_root, call_log = _prepare_relocated_repo(
        tmp_path,
        failing_verifier=failing_verifier,
    )
    unrelated_cwd = tmp_path / "caller cwd"
    unrelated_cwd.mkdir()

    result = _run_wrapper(repo_root, call_log, unrelated_cwd)

    assert result.returncode == 17
    assert "public projection ok" not in result.stdout
    assert [call["script"] for call in _read_calls(call_log)] == [
        MATERIALIZER,
        *VERIFIERS[:3],
    ]


def test_wrapper_fails_before_generation_without_explicit_release_channel(tmp_path: Path) -> None:
    repo_root, call_log = _prepare_relocated_repo(tmp_path)
    unrelated_cwd = tmp_path / "caller cwd"
    unrelated_cwd.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "CALL_LOG": str(call_log),
            "CHUMMER_PUBLIC_BASE_URL": "https://proof.example.invalid",
        }
    )
    environment.pop("CHUMMER_HUB_RELEASE_CHANNEL_PATH", None)
    environment.pop("CHUMMER_RELEASE_CHANNEL_PATH", None)
    environment.pop("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH", None)
    environment.pop("CHUMMER_FLEET_FLAGSHIP_READINESS_PATH", None)

    result = subprocess.run(
        ["bash", str(repo_root / "scripts" / "release" / WRAPPER.name)],
        cwd=unrelated_cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )

    assert result.returncode == 2
    assert "explicit immutable release-channel handoff" in result.stdout
    assert not call_log.exists()


def test_wrapper_fails_before_generation_without_explicit_readiness(tmp_path: Path) -> None:
    repo_root, call_log = _prepare_relocated_repo(tmp_path)
    unrelated_cwd = tmp_path / "caller cwd"
    unrelated_cwd.mkdir()
    release_channel = repo_root / "release authority" / "RELEASE_CHANNEL.generated.json"
    release_channel.parent.mkdir(parents=True, exist_ok=True)
    release_channel.write_text("{}\n", encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            "CALL_LOG": str(call_log),
            "CHUMMER_PUBLIC_BASE_URL": "https://proof.example.invalid",
            "CHUMMER_RELEASE_CHANNEL_PATH": str(release_channel),
        }
    )
    environment.pop("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH", None)
    environment.pop("CHUMMER_FLEET_FLAGSHIP_READINESS_PATH", None)

    result = subprocess.run(
        ["bash", str(repo_root / "scripts" / "release" / WRAPPER.name)],
        cwd=unrelated_cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )

    assert result.returncode == 2
    assert "explicit flagship-readiness handoff" in result.stdout
    assert not call_log.exists()


def test_wrapper_contains_no_machine_local_checkout_path() -> None:
    source = WRAPPER.read_text(encoding="utf-8")
    assert "/docker/" not in source
    assert "/workspace/" not in source
    assert "/Users/" not in source
    assert "${BASH_SOURCE[0]}" in source


def _load_materializer_module():
    spec = importlib.util.spec_from_file_location(
        "hub_local_release_proof_portability_test",
        MATERIALIZER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_desktop_verifier_module():
    spec = importlib.util.spec_from_file_location(
        "desktop_native_trust_portability_test",
        DESKTOP_VERIFIER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_fallback_defaults_are_bound_to_the_checked_out_hub_repo(monkeypatch) -> None:
    for env_name in (
        "CHUMMER_FLEET_FLAGSHIP_READINESS_PATH",
        "CHUMMER_NEXT90_M120_QUEUE_STAGING",
        "CHUMMER_NEXT90_M120_DESIGN_QUEUE_STAGING",
        "CHUMMER_NEXT90_M120_SUCCESSOR_REGISTRY",
        "CHUMMER_NEXT90_M125_QUEUE_STAGING",
        "CHUMMER_NEXT90_M125_DESIGN_QUEUE_STAGING",
        "CHUMMER_NEXT90_M126_QUEUE_STAGING",
        "CHUMMER_NEXT90_M126_DESIGN_QUEUE_STAGING",
        "CHUMMER_NEXT90_M144_QUEUE_STAGING",
        "CHUMMER_NEXT90_M144_DESIGN_QUEUE_STAGING",
        "CHUMMER_NEXT90_M144_SUCCESSOR_REGISTRY",
        "CHUMMER_PRESENTATION_ROOT",
        "CHUMMER_WINDOWS_INSTALLER_PAYLOAD_VERIFY_SCRIPT",
    ):
        monkeypatch.delenv(env_name, raising=False)

    modules = {
        "m120": _load_module("portable_m120_verifier", M120_VERIFIER_PATH),
        "m125": _load_module("portable_m125_verifier", M125_VERIFIER_PATH),
        "m126": _load_module("portable_m126_verifier", M126_VERIFIER_PATH),
        "m144": _load_module("portable_m144_verifier", M144_VERIFIER_PATH),
        "desktop": _load_desktop_verifier_module(),
        "live_windows": _load_module("portable_live_windows_verifier", LIVE_WINDOWS_VERIFIER_PATH),
    }
    checkout_bound_paths = (
        modules["m120"].FLEET_QUEUE_STAGING_PATH,
        modules["m120"].DESIGN_QUEUE_STAGING_PATH,
        modules["m120"].SUCCESSOR_REGISTRY_PATH,
        modules["m125"].FLEET_QUEUE_STAGING_PATH,
        modules["m125"].DESIGN_QUEUE_STAGING_PATH,
        modules["m126"].FLEET_QUEUE_STAGING_PATH,
        modules["m126"].DESIGN_QUEUE_STAGING_PATH,
        modules["m144"].FLEET_QUEUE_STAGING_PATH,
        modules["m144"].DESIGN_QUEUE_STAGING_PATH,
        modules["m144"].SUCCESSOR_REGISTRY_PATH,
        modules["desktop"].DEFAULT_FLAGSHIP_READINESS_PATH,
        modules["desktop"].FALLBACK_FLAGSHIP_READINESS_PATH,
        modules["desktop"].DEFAULT_QUEUE_STAGING_PATH,
        modules["desktop"].DEFAULT_DESIGN_QUEUE_STAGING_PATH,
        modules["desktop"].DEFAULT_SUCCESSOR_REGISTRY_PATH,
        modules["live_windows"].DEFAULT_VERIFY_SCRIPT,
    )
    assert all(path.is_relative_to(REPO_ROOT) for path in checkout_bound_paths)
    assert modules["live_windows"].DEFAULT_VERIFY_SCRIPT == (
        REPO_ROOT / "scripts" / "verify-windows-installer-payloads.py"
    )


def test_materializer_maps_known_roots_and_rejects_unknown_machine_paths() -> None:
    module = _load_materializer_module()
    payload = {
        "hub": "/docker/chummercomplete/chummer6-hub/scripts/check.py",
        "legacyHub": "/docker/chummercomplete/chummer.run-services/tests/check.py",
        "ui": "/docker/chummercomplete/chummer6-ui/tests/check.py",
        "wholeProduct": "/docker/chummercomplete/RELEASE_BLOCKERS.generated.json",
        "fleet": ["/docker/fleet/.codex-studio/published/proof.json"],
        "route": "/home/work",
    }

    assert module._portable_public_value(payload) == {
        "hub": "repo://ArchonMegalon/chummer6-hub/scripts/check.py",
        "legacyHub": "repo://ArchonMegalon/chummer6-hub/tests/check.py",
        "ui": "repo://ArchonMegalon/chummer6-ui/tests/check.py",
        "wholeProduct": "evidence://whole-product/RELEASE_BLOCKERS.generated.json",
        "fleet": ["evidence://fleet/.codex-studio/published/proof.json"],
        "route": "/home/work",
    }
    for local_path in (
        "/tmp/proof.json",
        "/private/tmp/proof.json",
        "/private/var/folders/proof.json",
        "/var/folders/zz/proof.json",
        "/var/tmp/proof.json",
        "/workspace/repo/proof.json",
        "/Users/operator/repo/proof.json",
        "/home/operator/repo/proof.json",
        "/root/repo/proof.json",
        "/docker/unknown/proof.json",
        r"C:\Users\operator\proof.json",
        r"D:\Windows\Temp\proof.json",
    ):
        try:
            module._portable_public_value({"proof": local_path})
        except RuntimeError as error:
            assert "machine-local path" in str(error)
            assert "$.proof" in str(error)
        else:
            raise AssertionError(f"machine-local path was accepted: {local_path}")


def test_tracked_current_hub_proofs_are_portable() -> None:
    forbidden = ("/tmp/", "/var/tmp/", "/docker/", "/workspace/", "/Users/")
    proof_paths = (
        REPO_ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json",
        REPO_ROOT
        / "Chummer.Run.Api"
        / "wwwroot"
        / "proofs"
        / "mac-codex-release"
        / "HUB_LOCAL_RELEASE_PROOF.generated.json",
    )
    payloads = [path.read_text(encoding="utf-8") for path in proof_paths]
    assert payloads[0] == payloads[1]
    for path, payload in zip(proof_paths, payloads, strict=True):
        for prefix in forbidden:
            assert prefix not in payload, f"{path} contains {prefix}"


def test_desktop_verifier_compares_against_the_same_portable_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    readiness_path = tmp_path / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    readiness_path.write_text(
        json.dumps(
            {
                "contract_name": "fleet.flagship_product_readiness",
                "generated_at": "2026-07-19T00:00:00Z",
                "status": "fail",
                "scoped_status": "fail",
                "missing_keys": ["desktop_client"],
                "completion_audit": {
                    "status": "fail",
                    "reason": (
                        "blocked by /docker/chummercomplete/chummer6-hub/"
                        "RELEASE_BLOCKERS.generated.json"
                    ),
                },
                "flagship_readiness_audit": {
                    "reason": (
                        "blocked by /docker/chummercomplete/chummer6-hub/"
                        "RELEASE_BLOCKERS.generated.json"
                    ),
                    "missing_coverage_keys": ["desktop_client"],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH", str(readiness_path))
    module = _load_desktop_verifier_module()
    errors: list[str] = []

    snapshot = module._load_flagship_readiness_snapshot(errors)

    assert errors == []
    assert snapshot is not None
    assert snapshot["source_path"] == (
        "evidence://fleet/FLAGSHIP_PRODUCT_READINESS.generated.json"
    )
    assert "repo://ArchonMegalon/chummer6-hub/RELEASE_BLOCKERS.generated.json" in (
        snapshot["reason"]
    )
    assert "/docker/" not in json.dumps(snapshot)
