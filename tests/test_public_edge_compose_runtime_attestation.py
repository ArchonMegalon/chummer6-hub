from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_public_edge_compose_runtime.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_public_edge_compose_runtime", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def rendered_compose(
    *, source_root: Path, build_context: Path, overlay_root: Path
) -> dict[str, object]:
    build = {
        "context": str(build_context),
        "dockerfile": str(source_root / "Chummer.Run.Api" / "Dockerfile"),
        "additional_contexts": {
            "run-services-source": str(source_root),
            "fleet-media-factory-contracts": "/docker/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts",
            "design-product": "/docker/chummercomplete/chummer-design",
        },
    }
    tool_build = {**build, "target": "install-linking-postgres-tool-final"}
    return {
        "name": "chummer6-hub",
        "services": {
            "chummer-portal-volume-init": {"image": "chummer-run-api:local"},
            "chummer-portal": {
                "image": "chummer-run-api:local",
                "build": build,
                "environment": {
                    "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": "false",
                    "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": "false",
                    "SECRET_NOT_ALLOWED_IN_RECEIPT": "do-not-copy",
                },
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(overlay_root),
                        "target": "/app",
                        "read_only": True,
                    }
                ],
                "ports": [{"target": 8080, "published": "8091", "protocol": "tcp"}],
            },
            "chummer-install-linking-postgres-admin": {
                "image": "chummer-install-linking-postgres-tool:local",
                "build": tool_build,
            },
            "chummer-install-linking-postgres-import": {
                "image": "chummer-install-linking-postgres-tool:local",
                "build": tool_build,
            },
        },
    }


def fixture_roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    source_root = tmp_path / "source"
    build_context = tmp_path / "workspace"
    overlay_root = tmp_path / "overlay" / "app"
    (source_root / "Chummer.Run.Api").mkdir(parents=True)
    build_context.mkdir()
    overlay_root.mkdir(parents=True)
    (source_root / "Chummer.Run.Api" / "Dockerfile").write_text(
        "FROM scratch\n", encoding="utf-8"
    )
    return source_root, build_context, overlay_root


def test_compose_attestation_accepts_only_canonical_runtime_and_omits_environment(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root, build_context, overlay_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
    )

    receipt = module.validate_runtime(
        payload,
        project_name="chummer6-hub",
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
        published_port=8091,
    )
    output = tmp_path / "receipt.json"
    module.atomic_write_json(output, receipt)

    assert receipt["status"] == "pass"
    assert receipt["proxyGates"] == {
        "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": "false",
        "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": "false",
    }
    assert "do-not-copy" not in output.read_text(encoding="utf-8")
    assert os.stat(output).st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update(name="other"), "project name"),
        (
            lambda payload: payload["services"]["chummer-portal"].update(image="other"),
            "portal image",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["volumes"][0].update(
                read_only=False
            ),
            "read-only overlay",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["ports"][0].update(
                published="8092"
            ),
            "port binding",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_PUBLIC_PLAY_PROXY_ENABLED="true"
            ),
            "literal string false",
        ),
        (
            lambda payload: payload["services"]["chummer-portal"]["environment"].update(
                CHUMMER_PUBLIC_PLAY_PROXY_URL="https://retired.invalid"
            ),
            "forbidden retired proxy key",
        ),
        (
            lambda payload: payload["services"]["chummer-install-linking-postgres-admin"][
                "build"
            ].update(target="other"),
            "build authority drifted",
        ),
    ],
)
def test_compose_attestation_rejects_runtime_authority_drift(
    tmp_path: Path, mutation, message: str
) -> None:
    module = load_module()
    source_root, build_context, overlay_root = fixture_roots(tmp_path)
    payload = copy.deepcopy(
        rendered_compose(
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
        )
    )
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        module.validate_runtime(
            payload,
            project_name="chummer6-hub",
            source_root=source_root,
            build_context=build_context,
            overlay_root=overlay_root,
            published_port=8091,
        )


def test_compose_attestation_runs_under_isolated_python(tmp_path: Path) -> None:
    source_root, build_context, overlay_root = fixture_roots(tmp_path)
    payload = rendered_compose(
        source_root=source_root,
        build_context=build_context,
        overlay_root=overlay_root,
    )
    output = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            str(SCRIPT),
            "--project-name",
            "chummer6-hub",
            "--source-root",
            str(source_root),
            "--build-context",
            str(build_context),
            "--overlay-root",
            str(overlay_root),
            "--published-port",
            "8091",
            "--output",
            str(output),
        ],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "pass"
