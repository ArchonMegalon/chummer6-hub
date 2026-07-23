from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_install_linking_postgres_cutover.py"
IMAGE = "sha256:" + "a" * 64
TOOL_IMAGE = "sha256:" + "b" * 64
CONTAINER_ID = "c" * 64
NETWORK_ID = "d" * 64


def load_module():
    name = "run_install_linking_postgres_cutover"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeCommands:
    def __init__(self, callback):
        self.callback = callback
        self.calls: list[tuple[list[str], int, bool]] = []

    def run(self, arguments, *, timeout=30, check=True):
        call = (list(arguments), timeout, check)
        self.calls.append(call)
        return self.callback(*call)


def make_runner(module, tmp_path: Path, commands: FakeCommands):
    tmp_path.chmod(0o700)
    source = tmp_path / "source"
    source.mkdir()
    inputs = module.CutoverInputs(
        source_root=source,
        compose_file=source / "docker-compose.public-edge.yml",
        env_file=tmp_path / ".env",
        receipt_root=tmp_path,
        boundary_output=tmp_path / "boundary.json",
        expected_head="1" * 40,
        compose_sha256="2" * 64,
        env_sha256="3" * 64,
        runner_sha256="4" * 64,
        expected_hub_registry_head="5" * 40,
        expected_design_product_head="6" * 40,
        expected_fleet_media_factory_head="7" * 40,
        expected_build_context_dockerignore_sha256="8" * 64,
        cutover_id="cutover-test",
    )
    runner = module.GovernedCutoverRunner(inputs, command_runner=commands)
    runner.candidate_image_id = IMAGE
    runner.candidate_tool_image_id = TOOL_IMAGE
    runner.public_network_name = "chummer5a_default"
    runner.public_network_id = NETWORK_ID
    return runner


@pytest.mark.parametrize(
    "path",
    (
        "Chummer.Run.Api/.env",
        "products/chummer/.env.production",
        "src/project/bin/Release/app.dll",
        "src/project/obj/project.assets.json",
        "src/project/node_modules/package/index.js",
        "src/project/Docker/Secrets/runtime.key",
        "src/project/server.pem",
        "src/project/credentials.prod.json",
        "src/project/secrets.yaml",
        "../outside",
    ),
)
def test_context_provenance_rejects_sensitive_or_output_paths(path: str) -> None:
    module = load_module()

    assert module.GovernedCutoverRunner._tracked_context_entry_is_sensitive_or_output(
        path
    )


@pytest.mark.parametrize(
    "path",
    (
        ".env.example",
        "Chummer.Run.Api/Program.cs",
        "products/chummer/public-guide/README.md",
        "src/Chummer.Media.Contracts/Assets/MediaAssetCatalogEntry.cs",
    ),
)
def test_context_provenance_accepts_reviewable_source_paths(path: str) -> None:
    module = load_module()

    assert not (
        module.GovernedCutoverRunner
        ._tracked_context_entry_is_sensitive_or_output(path)
    )


def admin_inspection(module, runner) -> dict:
    mounts = [
        {
            "Destination": (
                "/run/chummer-secrets/"
                "install-linking-postgres-migrator.connection-string"
            ),
            "RW": False,
            "Source": "/private/migrator.connection-string",
            "Type": "bind",
        },
        {
            "Destination": (
                "/run/chummer-secrets/install-linking-postgres-server-ca.pem"
            ),
            "RW": False,
            "Source": "/private/postgres-ca.pem",
            "Type": "bind",
        },
    ]
    runner.expected_mount_source_sha256[
        "chummer-install-linking-postgres-admin"
    ] = {
        item["Destination"]: module.sha256_bytes(item["Source"].encode())
        for item in mounts
    }
    critical_environment = {
        "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE": (
            "/run/chummer-secrets/"
            "install-linking-postgres-migrator.connection-string"
        ),
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_DATABASE": (
            "chummer_install_linking"
        ),
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST": (
            "db.example.net"
        ),
        "CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_PORT": "5432",
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE": "runtime_role",
    }
    runner.expected_critical_environment_sha256[
        "chummer-install-linking-postgres-admin"
    ] = module.critical_environment_sha256(
        "chummer-install-linking-postgres-admin",
        critical_environment,
    )
    project = runner._job_project("prepare")
    name = (
        f"chummer-install-linking-cutover-{runner.name_suffix}-prepare"
    )
    return {
        "Config": {
            "Cmd": ["prepare"],
            "Env": [
                f"CHUMMER_CUTOVER_SECRET_CANARY={runner.secret_canary}",
                *[
                    f"{key}={value}"
                    for key, value in critical_environment.items()
                ],
            ],
            "Labels": {
                "com.docker.compose.config-hash": "e" * 64,
                "com.docker.compose.oneoff": "False",
                "com.docker.compose.project": project,
                "com.docker.compose.service": (
                    "chummer-install-linking-postgres-admin"
                ),
            },
            "User": "1654:1654",
        },
        "HostConfig": {
            "CapDrop": ["ALL"],
            "ExtraHosts": ["postgres.example:192.0.2.1"],
            "NetworkMode": "chummer5a_default",
            "ReadonlyRootfs": True,
            "SecurityOpt": ["no-new-privileges:true"],
            "Tmpfs": {
                "/tmp": "rw,noexec,nosuid,nodev,mode=1777",
            },
        },
        "Id": CONTAINER_ID,
        "Image": TOOL_IMAGE,
        "Mounts": mounts,
        "Name": f"/{name}",
        "NetworkSettings": {
            "Networks": {
                "chummer5a_default": {"NetworkID": NETWORK_ID},
            },
        },
        "State": {"Running": False, "Status": "created"},
    }


def test_unique_job_projects_retain_independent_compose_containers(
    tmp_path: Path,
) -> None:
    module = load_module()
    commands = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    runner = make_runner(module, tmp_path, commands)

    first_path, first_name, first_project = runner._job_override(
        job_name="prepare",
        service="chummer-install-linking-postgres-admin",
        command=["prepare"],
    )
    second_path, second_name, second_project = runner._job_override(
        job_name="validate",
        service="chummer-install-linking-postgres-admin",
        command=["validate"],
    )

    assert first_project != second_project
    assert first_name != second_name
    assert runner._compose("create", project=first_project)[
        runner._compose("create", project=first_project).index("-p") + 1
    ] == first_project
    for path in (first_path, second_path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["volumes"]["chummer-run-api-state"] == {
            "external": True,
            "name": "chummer6-hub_chummer-run-api-state",
        }


@pytest.mark.parametrize("preexisting", ("portal", "tool"))
def test_preexisting_candidate_tag_aborts_before_build(
    tmp_path: Path,
    preexisting: str,
) -> None:
    module = load_module()

    def callback(arguments, _timeout, _check):
        rendered = " ".join(arguments)
        if " image ls " in f" {rendered} ":
            selected = (
                "chummer-run-api:cutover-" in rendered
                if preexisting == "portal"
                else "chummer-install-linking-postgres-tool:cutover-"
                in rendered
            )
            return module.CommandResult(
                0,
                (IMAGE + "\n").encode() if selected else b"",
                b"",
            )
        raise AssertionError("candidate build ran before freshness was proven")

    commands = FakeCommands(callback)
    runner = make_runner(module, tmp_path, commands)

    with pytest.raises(module.CutoverError, match="already exists"):
        runner._build_candidates()

    assert not any(" build " in f" {' '.join(call[0])} " for call in commands.calls)


def test_candidate_build_rejects_external_source_drift_during_build(
    tmp_path: Path,
) -> None:
    module = load_module()

    class Harness(module.GovernedCutoverRunner):
        captures = 0

        def _capture_build_source_provenance(self):
            self.captures += 1
            return {
                "design-product": {
                    "head": (
                        "1" * 40 if self.captures == 1 else "2" * 40
                    )
                }
            }

        def _require_candidate_tags_absent(self):
            return None

        def _resolve_image(self, tag, *, allow_absent=False):
            if tag == self.portal_tag:
                return IMAGE
            if tag == self.tool_tag:
                return TOOL_IMAGE
            return ""

        def _validate_source(self):
            return None

        def _validate_rendered_compose(self):
            return None

    commands = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    base = make_runner(module, tmp_path, commands)
    runner = Harness(base.inputs, command_runner=commands)

    with pytest.raises(module.CutoverError, match="source changed"):
        runner._build_candidates()

    assert not runner.candidate_build_info_path.exists()


def test_untracked_ignored_file_in_unfiltered_additional_context_is_rejected(
    tmp_path: Path,
) -> None:
    module = load_module()
    repository = tmp_path / "fleet"
    consumed = repository / "src" / "Chummer.Media.Contracts"
    consumed.mkdir(parents=True)
    expected_head = "7" * 40

    def callback(arguments, _timeout, _check):
        command = arguments[3:]
        if command == ["rev-parse", "--show-toplevel"]:
            output = f"{repository}\n"
        elif command == ["rev-parse", "HEAD"]:
            output = f"{expected_head}\n"
        elif command == ["rev-parse", "refs/remotes/origin/main"]:
            output = f"{expected_head}\n"
        elif command == ["remote", "get-url", "origin"]:
            output = (
                "https://github.com/ArchonMegalon/"
                "chummer6-media-factory.git\n"
            )
        elif command[:3] == ["status", "--porcelain=v1", "--untracked-files=all"]:
            output = ""
        elif command[:4] == [
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
        ]:
            output = (
                "src/Chummer.Media.Contracts/bin/Release/"
                "unreviewed.dll\n"
            )
        elif command[:2] == ["ls-files", "-z"]:
            output = (
                "src/Chummer.Media.Contracts/"
                "Chummer.Media.Contracts.csproj\0"
            )
        else:
            raise AssertionError(command)
        return module.CommandResult(0, output.encode(), b"")

    runner = make_runner(module, tmp_path, FakeCommands(callback))

    with pytest.raises(module.CutoverError, match="canonical origin/main"):
        runner._git_source_provenance(
            name="fleet-media-factory-contracts",
            repository=repository,
            consumed_path=consumed,
            expected_head=expected_head,
            allow_docker_excluded_ignored=False,
        )


def test_postquiesce_reproof_reopens_exact_retained_build_override(
    tmp_path: Path,
) -> None:
    module = load_module()
    runner = make_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )
    runner._write_build_override()
    original = runner.build_override.read_bytes()

    runner._bind_existing_build_override()

    assert runner.build_override.read_bytes() == original
    assert runner.build_override.stat().st_mode & 0o777 == 0o600
    payload = json.loads(original)
    payload["services"]["chummer-portal"]["image"] = (
        "chummer-run-api:cutover-wrong"
    )
    runner.build_override.write_bytes(
        module.canonical_json_bytes(payload, label="override")
    )
    with pytest.raises(module.CutoverError, match="identity drifted"):
        runner._bind_existing_build_override()


@pytest.mark.parametrize("mutation", ["wrong_source", "wrong_service"])
def test_stopped_container_inspection_rejects_topology_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    payload_holder: dict[str, object] = {}

    def callback(_arguments, _timeout, _check):
        return module.CommandResult(
            0,
            json.dumps([payload_holder["payload"]]).encode(),
            b"",
        )

    runner = make_runner(module, tmp_path, FakeCommands(callback))
    payload = admin_inspection(module, runner)
    if mutation == "wrong_source":
        payload["Mounts"][0]["Source"] = "/private/wrong.connection-string"
    else:
        payload["Config"]["Labels"][
            "com.docker.compose.service"
        ] = "chummer-install-linking-postgres-runtime-proof"
    payload_holder["payload"] = payload

    with pytest.raises(module.CutoverError, match="contract drifted"):
        runner._inspect_container(
            container_name=payload["Name"][1:],
            service="chummer-install-linking-postgres-admin",
            project=runner._job_project("prepare"),
            command=["prepare"],
        )


def test_valid_inspection_emits_closed_non_secret_source_and_network_identity(
    tmp_path: Path,
) -> None:
    module = load_module()
    payload_holder: dict[str, object] = {}

    def callback(_arguments, _timeout, _check):
        return module.CommandResult(
            0,
            json.dumps([payload_holder["payload"]]).encode(),
            b"",
        )

    runner = make_runner(module, tmp_path, FakeCommands(callback))
    payload = admin_inspection(module, runner)
    payload_holder["payload"] = payload
    container_id, topology = runner._inspect_container(
        container_name=payload["Name"][1:],
        service="chummer-install-linking-postgres-admin",
        project=runner._job_project("prepare"),
        command=["prepare"],
    )

    assert container_id == CONTAINER_ID
    assert topology["networkId"] == NETWORK_ID
    assert topology["command"] == ["prepare"]
    serialized = json.dumps(topology)
    assert "/private/" not in serialized
    assert all(
        len(item["sourceIdentitySha256"]) == 64
        for item in topology["mounts"]
    )


def test_local_store_proof_rejects_decoy_store_path(
    tmp_path: Path,
) -> None:
    module = load_module()
    payload_holder: dict[str, object] = {}

    def callback(_arguments, _timeout, _check):
        return module.CommandResult(
            0,
            json.dumps([payload_holder["payload"]]).encode(),
            b"",
        )

    runner = make_runner(module, tmp_path, FakeCommands(callback))
    service = "chummer-install-linking-postgres-import-presence-proof"
    job_name = "prove-local-store-absent"
    project = runner._job_project(job_name)
    canonical_store = "/app/state/install-linking/install-linking-store.json"
    runner.expected_mount_source_sha256[service] = {
        "/app/state": module.sha256_bytes(
            b"chummer6-hub_chummer-run-api-state"
        )
    }
    runner.expected_critical_environment_sha256[service] = (
        module.critical_environment_sha256(
            service,
            {"CHUMMER_INSTALL_LINKING_STORE_PATH": canonical_store},
        )
    )
    payload_holder["payload"] = {
        "Config": {
            "Cmd": ["prove-local-store-absent"],
            "Env": [
                f"CHUMMER_CUTOVER_SECRET_CANARY={runner.secret_canary}",
                (
                    "CHUMMER_INSTALL_LINKING_STORE_PATH="
                    "/app/state/decoy/install-linking-store.json"
                ),
            ],
            "Labels": {
                "com.docker.compose.config-hash": "e" * 64,
                "com.docker.compose.oneoff": "False",
                "com.docker.compose.project": project,
                "com.docker.compose.service": service,
            },
            "User": "1654:1654",
        },
        "HostConfig": {
            "CapDrop": ["ALL"],
            "ExtraHosts": [],
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "SecurityOpt": ["no-new-privileges:true"],
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,mode=1777"},
        },
        "Id": CONTAINER_ID,
        "Image": TOOL_IMAGE,
        "Mounts": [
            {
                "Destination": "/app/state",
                "RW": False,
                "Name": "chummer6-hub_chummer-run-api-state",
                "Type": "volume",
            }
        ],
        "Name": (
            "/chummer-install-linking-cutover-"
            f"{runner.name_suffix}-{job_name}"
        ),
        "NetworkSettings": {"Networks": {}},
        "State": {"Running": False, "Status": "created"},
    }

    with pytest.raises(
        module.CutoverError,
        match="critical environment drifted",
    ):
        runner._inspect_container(
            container_name=str(payload_holder["payload"]["Name"])[1:],
            service=service,
            project=project,
            command=["prove-local-store-absent"],
        )


def test_nonzero_docker_logs_result_is_not_accepted_as_captured(
    tmp_path: Path,
) -> None:
    module = load_module()
    commands = FakeCommands(
        lambda *_args: module.CommandResult(
            1,
            b'{"contractName":"forged","status":"pass"}\n',
            b"partial",
        )
    )
    runner = make_runner(module, tmp_path, commands)

    _stdout, _stdout_sha, _stderr, _stderr_sha, captured = (
        runner._capture_logs(CONTAINER_ID, "prepare")
    )

    assert captured is False


def test_termination_sequence_uses_pinned_container_id(
    tmp_path: Path,
) -> None:
    module = load_module()
    commands = FakeCommands(
        lambda *_args: module.CommandResult(0, b"0\n", b"")
    )
    runner = make_runner(module, tmp_path, commands)

    runner._terminate_active_container(CONTAINER_ID)

    assert [call[0][-5:] for call in commands.calls] == [
        ["container", "stop", "--time", "5", CONTAINER_ID],
        ["container", "kill", "--signal", "KILL", CONTAINER_ID],
        ["--context", "default", "container", "wait", CONTAINER_ID],
    ]


def test_start_intent_is_durable_and_binds_exact_container_id(
    tmp_path: Path,
) -> None:
    module = load_module()
    runner = make_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )

    path, digest, _created = runner._write_start_intent(
        job_name="prepare",
        service="chummer-install-linking-postgres-admin",
        project=runner._job_project("prepare"),
        container_name="chummer-install-linking-cutover-test-prepare",
        container_id=CONTAINER_ID,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["containerId"] == CONTAINER_ID
    assert runner.active_container_id == CONTAINER_ID
    assert runner.start_intent_written is True
    assert len(digest) == 64
    assert path.stat().st_mode & 0o777 == 0o600


def test_wait_timeout_is_durable_unknown_not_a_synthetic_exit(
    tmp_path: Path,
) -> None:
    module = load_module()

    def callback(_arguments, _timeout, _check):
        raise module.CommandDeadlineExceeded("timeout")

    runner = make_runner(module, tmp_path, FakeCommands(callback))
    with pytest.raises(module.JobWaitAmbiguity) as error:
        runner._wait_for_job(
            CONTAINER_ID,
            deadline=module.time.monotonic() + module.JOB_TIMEOUT_SECONDS,
        )
    assert error.value.timed_out is True


def test_start_latency_consumes_the_single_monotonic_job_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    observed: dict[str, object] = {}
    primary_wait_seen = False

    def callback(arguments, timeout, _check):
        nonlocal primary_wait_seen
        if arguments[-3:-1] == ["container", "inspect"]:
            return module.CommandResult(1, b"", b"")
        if arguments[-3:-1] == ["container", "start"]:
            observed["start_timeout"] = timeout
            clock[0] += 30.0
            return module.CommandResult(0, b"", b"")
        if (
            arguments[-3:-1] == ["container", "wait"]
            and not primary_wait_seen
        ):
            primary_wait_seen = True
            observed["wait_timeout"] = timeout
            raise module.CommandDeadlineExceeded("deadline")
        return module.CommandResult(0, b"", b"")

    class Harness(module.GovernedCutoverRunner):
        def _job_override(self, **_kwargs):
            return (
                self.inputs.receipt_root / "override.json",
                "postquiesce-attempt01-prove-empty-authority",
                "chummer6-ilpg-test",
            )

        def _inspect_container(self, **_kwargs):
            return CONTAINER_ID, {}

        def _resolve_image(self, _tag, *, allow_absent=False):
            return TOOL_IMAGE

        def _inspect_observed_state(self, _container_id):
            return "exited", None

        def _write_job_receipt(self, **kwargs):
            observed["timed_out"] = kwargs["timed_out"]
            path = self.inputs.receipt_root / "job-receipt.json"
            return path, "f" * 64

    commands = FakeCommands(callback)
    base = make_runner(module, tmp_path, commands)
    runner = Harness(base.inputs, command_runner=commands)
    runner.candidate_image_id = IMAGE
    runner.candidate_tool_image_id = TOOL_IMAGE

    with pytest.raises(module.AmbiguousCutoverError):
        runner._run_job(
            job_name="postquiesce-attempt01-prove-empty-authority",
            service="chummer-install-linking-postgres-runtime-proof",
            command=("prove-empty-authority",),
            proof_contract=(
                "chummer.install_linking_postgres_empty_authority_proof.v1"
            ),
        )

    assert observed["start_timeout"] == pytest.approx(180.0)
    assert observed["wait_timeout"] == pytest.approx(150.0)
    assert observed["timed_out"] is True


def test_success_receipt_is_written_only_after_durable_lease_release(
    tmp_path: Path,
) -> None:
    module = load_module()
    events: list[str] = []

    class Harness(module.GovernedCutoverRunner):
        def _validate_source(self):
            events.append("validate-source")

        def _write_build_override(self):
            events.append("override")

        def _acquire_lease(self):
            events.append("lease")

        def _validate_rendered_compose(self):
            events.append("compose")

        def _build_candidates(self):
            self.candidate_image_id = IMAGE
            self.candidate_tool_image_id = TOOL_IMAGE
            events.append("build")

        def _materialize(self, phase, **_kwargs):
            events.append(phase)

        def _run_job(self, **kwargs):
            events.append(kwargs["job_name"])

        def _write_phase_evidence(self, phase):
            events.append(f"evidence:{phase}")
            return self.inputs.receipt_root / f"{phase}.json"

        def _release_lease(self):
            events.append("release")

        def _write_final_receipt(self, *, status, reason, replace=False):
            events.append(f"final:{status}")
            return self.inputs.receipt_root / "final.json"

    commands = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    base = make_runner(module, tmp_path, commands)
    runner = Harness(base.inputs, command_runner=commands)

    runner.run()

    assert events.index("release") < events.index("final:pass")


def test_lease_release_failure_cannot_leave_a_false_passing_receipt(
    tmp_path: Path,
) -> None:
    module = load_module()
    statuses: list[str] = []

    class Harness(module.GovernedCutoverRunner):
        def _validate_source(self):
            return None

        def _write_build_override(self):
            return None

        def _acquire_lease(self):
            return None

        def _validate_rendered_compose(self):
            return None

        def _build_candidates(self):
            self.candidate_image_id = IMAGE
            self.candidate_tool_image_id = TOOL_IMAGE
            self.start_intent_written = True

        def _materialize(self, _phase, **_kwargs):
            return None

        def _run_job(self, **_kwargs):
            return None

        def _write_phase_evidence(self, phase):
            return self.inputs.receipt_root / f"{phase}.json"

        def _release_lease(self):
            raise module.CutoverError("release receipt failed")

        def _write_final_receipt(self, *, status, reason, replace=False):
            statuses.append(status)
            return self.inputs.receipt_root / "final.json"

    commands = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    base = make_runner(module, tmp_path, commands)
    runner = Harness(base.inputs, command_runner=commands)

    with pytest.raises(module.AmbiguousCutoverError):
        runner.run()
    assert statuses == ["unknown"]
