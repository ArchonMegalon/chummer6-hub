from __future__ import annotations

import ast
import copy
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
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


def unseal_test_repository(repository: Path) -> None:
    for directory, _directory_names, file_names in os.walk(repository):
        Path(directory).chmod(0o755)
        for file_name in file_names:
            (Path(directory) / file_name).chmod(0o644)


def seal_test_repository(repository: Path) -> None:
    for directory, _directory_names, file_names in os.walk(
        repository,
        topdown=False,
    ):
        for file_name in file_names:
            (Path(directory) / file_name).chmod(0o444)
        Path(directory).chmod(0o555)


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


def make_pinned_final_bind_runner(module, tmp_path: Path):
    commands = FakeCommands(lambda *_args: module.CommandResult(0, b"", b""))
    base = make_runner(module, tmp_path, commands)
    source = base.inputs.source_root
    scripts = source / "scripts"
    scripts.mkdir()
    shutil.copyfile(
        ROOT / "docker-compose.public-edge.yml",
        base.inputs.compose_file,
    )
    shutil.copyfile(SCRIPT, scripts / SCRIPT.name)
    base.inputs.env_file.write_text(
        "FINAL_BIND_AUTHORITY=canonical\n",
        encoding="utf-8",
    )
    base.inputs.env_file.chmod(0o600)
    inputs = replace(
        base.inputs,
        compose_sha256=module.hash_regular_file(
            base.inputs.compose_file,
            owner_only=False,
        ),
        env_sha256=module.hash_regular_file(
            base.inputs.env_file,
            owner_only=True,
        ),
        runner_sha256=module.hash_regular_file(
            scripts / SCRIPT.name,
            owner_only=False,
        ),
    )

    class Harness(module.GovernedCutoverRunner):
        def _validate_build_workspace_paths(self):
            return None

        def _validate_source(self):
            self._bind_pinned_source_inputs()

        def _validate_rendered_compose(self, **_kwargs):
            return None

    runner = Harness(inputs, command_runner=commands)
    runner._write_build_override()
    return runner, commands


def test_hub_registry_dockerignore_requires_exact_reviewed_bytes(
    tmp_path: Path,
) -> None:
    module = load_module()
    commands = FakeCommands(lambda *_args: module.CommandResult(0, b"", b""))
    runner = make_runner(module, tmp_path, commands)
    dockerignore = tmp_path / ".dockerignore"
    dockerignore.write_bytes(module.REVIEWED_HUB_REGISTRY_DOCKERIGNORE)

    digest = runner._require_exact_dockerignore(
        dockerignore,
        label="hub registry",
        expected=module.REVIEWED_HUB_REGISTRY_DOCKERIGNORE,
    )

    assert digest == module.sha256_bytes(
        module.REVIEWED_HUB_REGISTRY_DOCKERIGNORE
    )

    dockerignore.write_bytes(
        module.REVIEWED_HUB_REGISTRY_DOCKERIGNORE + b"unreviewed-output\n"
    )
    with pytest.raises(module.CutoverError, match="reviewed contract"):
        runner._require_exact_dockerignore(
            dockerignore,
            label="hub registry",
            expected=module.REVIEWED_HUB_REGISTRY_DOCKERIGNORE,
        )


def test_public_edge_compose_build_syntax_accepts_canonical_project_name() -> None:
    module = load_module()
    compose = (ROOT / "docker-compose.public-edge.yml").read_text(
        encoding="utf-8"
    )

    module.require_public_edge_compose_build_syntax(compose)


def test_public_edge_compose_build_syntax_rejects_project_name_drift() -> None:
    module = load_module()
    compose = (ROOT / "docker-compose.public-edge.yml").read_text(
        encoding="utf-8"
    ).replace(
        "name: chummer6-hub",
        "name: chummer6-hub-shadow",
        1,
    )

    with pytest.raises(
        module.CutoverError,
        match="top-level name must use the exact canonical literal",
    ):
        module.require_public_edge_compose_build_syntax(compose)


def make_synthetic_runner(module, tmp_path: Path, commands: FakeCommands):
    base = make_runner(module, tmp_path, commands)
    workspace = tmp_path / "synthetic"
    source = workspace / "run-services"
    build_context = source
    hub_registry = workspace / "hub-registry"
    design_product = workspace / "design-product"
    fleet_media_factory = workspace / "fleet-media-factory"
    for path in (
        source,
        hub_registry,
        design_product,
        fleet_media_factory,
    ):
        path.mkdir(parents=True)
        (path / ".git").mkdir()
        (path / "fixture.txt").write_text("sealed fixture\n", encoding="utf-8")
        seal_test_repository(path)
    workspace.chmod(0o700)
    inputs = replace(
        base.inputs,
        source_root=source,
        compose_file=source / "docker-compose.public-edge.yml",
        synthetic_workspace_root=workspace,
        build_context_root=build_context,
        hub_registry_root=hub_registry,
        design_product_root=design_product,
        fleet_media_factory_root=fleet_media_factory,
        expected_run_services_content_sha256="9" * 64,
        expected_hub_registry_content_sha256="a" * 64,
        expected_design_product_content_sha256="b" * 64,
        expected_fleet_media_factory_content_sha256="c" * 64,
    )
    return module.GovernedCutoverRunner(
        inputs,
        command_runner=commands,
    )


def git_provenance_callback(
    module,
    repository: Path,
    *,
    expected_head: str,
    observed_head: str | None = None,
    dirty: bytes = b"",
    replace_refs: bytes = b"",
    shallow: bytes = b"false\n",
    promisor_configuration: bytes = b"",
):
    def callback(arguments, _timeout, _check):
        command = arguments[3:]
        if command == ["rev-parse", "--show-toplevel"]:
            output = f"{repository}\n".encode()
        elif command == ["rev-parse", "HEAD"]:
            output = f"{observed_head or expected_head}\n".encode()
        elif command == ["rev-parse", "refs/remotes/origin/main"]:
            output = f"{expected_head}\n".encode()
        elif command == ["remote", "get-url", "origin"]:
            output = (
                b"https://github.com/ArchonMegalon/"
                b"chummer6-hub-registry.git\n"
            )
        elif command[:3] == [
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ]:
            return module.CommandResult(0, dirty, b"")
        elif command[:4] == [
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
        ]:
            output = b""
        elif command[:2] == ["ls-files", "-z"]:
            output = b"black-ledger/source.txt\0"
        elif command == [
            "for-each-ref",
            "--format=%(refname)",
            "refs/replace",
        ]:
            output = replace_refs
        elif command == ["rev-parse", "--is-shallow-repository"]:
            output = shallow
        elif command[:3] == ["config", "--local", "--get-regexp"]:
            return module.CommandResult(
                0 if promisor_configuration else 1,
                promisor_configuration,
                b"",
            )
        elif command == [
            "fsck",
            "--strict",
            "--full",
            "--no-dangling",
            "--no-progress",
        ]:
            output = b""
        else:
            raise AssertionError(command)
        return module.CommandResult(0, output, b"")

    return callback


def prepare_hub_provenance_fixture(module, runner) -> tuple[Path, Path, str]:
    repository = runner.inputs.hub_registry_root
    unseal_test_repository(repository)
    consumed = repository / "black-ledger"
    consumed.mkdir(exist_ok=True)
    (consumed / "source.txt").write_text("exact\n", encoding="utf-8")
    seal_test_repository(repository)
    content_sha256, _count, _file_set = module.source_content_sha256(
        repository,
        ["black-ledger/source.txt"],
    )
    return repository, consumed, content_sha256


def test_default_workspace_contract_preserves_canonical_dependencies(
    tmp_path: Path,
) -> None:
    module = load_module()
    runner = make_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )

    runner._validate_build_workspace_paths()

    assert runner.inputs.synthetic_workspace_root is None
    assert runner.inputs.build_context_root == module.CANONICAL_BUILD_CONTEXT
    assert runner.inputs.hub_registry_root == module.CANONICAL_HUB_REGISTRY
    assert runner.inputs.design_product_root == module.CANONICAL_DESIGN_PRODUCT
    assert (
        runner.inputs.fleet_media_factory_root
        == module.CANONICAL_FLEET_MEDIA_REPOSITORY
    )


def test_synthetic_workspace_rejects_symlinked_dependency(
    tmp_path: Path,
) -> None:
    module = load_module()
    commands = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    runner = make_synthetic_runner(module, tmp_path, commands)
    linked = runner.inputs.synthetic_workspace_root / "hub-linked"
    linked.symlink_to(runner.inputs.hub_registry_root, target_is_directory=True)
    runner = module.GovernedCutoverRunner(
        replace(runner.inputs, hub_registry_root=linked),
        command_runner=commands,
    )

    with pytest.raises(module.CutoverError, match="non-symlinked"):
        runner._validate_build_workspace_paths()


def test_synthetic_workspace_requires_exact_private_root_mode(
    tmp_path: Path,
) -> None:
    module = load_module()
    runner = make_synthetic_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )
    runner.inputs.synthetic_workspace_root.chmod(0o750)

    with pytest.raises(module.CutoverError, match="exact mode 0700"):
        runner._validate_build_workspace_paths()


def test_synthetic_workspace_rejects_writable_source_tree(
    tmp_path: Path,
) -> None:
    module = load_module()
    runner = make_synthetic_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )
    runner.inputs.hub_registry_root.chmod(0o755)

    with pytest.raises(module.CutoverError, match="operator-owned and sealed"):
        runner._validate_build_workspace_paths()


def test_synthetic_workspace_rejects_nonoperator_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    runner = make_synthetic_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )
    actual_uid = os.getuid()
    monkeypatch.setattr(module.os, "getuid", lambda: actual_uid + 1)

    with pytest.raises(module.CutoverError, match="owned by the operator UID"):
        runner._validate_build_workspace_paths()


def test_synthetic_workspace_rejects_linked_worktree_git_file(
    tmp_path: Path,
) -> None:
    module = load_module()
    runner = make_synthetic_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )
    repository = runner.inputs.hub_registry_root
    unseal_test_repository(repository)
    (repository / ".git").rmdir()
    (repository / ".git").write_text(
        "gitdir: /shared/repository/.git/worktrees/hub\n",
        encoding="utf-8",
    )
    seal_test_repository(repository)

    with pytest.raises(module.CutoverError, match="real local .git directory"):
        runner._validate_build_workspace_paths()


@pytest.mark.parametrize(
    "relative_path",
    (
        ".git/commondir",
        ".git/shallow",
        ".git/info/grafts",
        ".git/objects/info/alternates",
        ".git/objects/info/http-alternates",
        ".git/objects/pack/pack-test.promisor",
    ),
)
def test_synthetic_workspace_rejects_shared_or_incomplete_git_storage(
    tmp_path: Path,
    relative_path: str,
) -> None:
    module = load_module()
    runner = make_synthetic_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )
    repository = runner.inputs.hub_registry_root
    unseal_test_repository(repository)
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("forbidden\n", encoding="utf-8")
    seal_test_repository(repository)

    with pytest.raises(
        module.CutoverError,
        match="forbidden|partial/promisor",
    ):
        runner._validate_build_workspace_paths()


def test_synthetic_workspace_rejects_dependency_outside_approved_root(
    tmp_path: Path,
) -> None:
    module = load_module()
    commands = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    runner = make_synthetic_runner(module, tmp_path, commands)
    outside = tmp_path / "outside-design"
    outside.mkdir()
    runner = module.GovernedCutoverRunner(
        replace(runner.inputs, design_product_root=outside),
        command_runner=commands,
    )

    with pytest.raises(module.CutoverError, match="outside"):
        runner._validate_build_workspace_paths()


def test_synthetic_workspace_rejects_canonical_dependency_fallback(
    tmp_path: Path,
) -> None:
    module = load_module()
    commands = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    runner = make_synthetic_runner(module, tmp_path, commands)
    runner = module.GovernedCutoverRunner(
        replace(
            runner.inputs,
            hub_registry_root=module.CANONICAL_HUB_REGISTRY,
        ),
        command_runner=commands,
    )

    with pytest.raises(module.CutoverError, match="cannot fall back"):
        runner._validate_build_workspace_paths()


def test_synthetic_routing_environment_closes_every_build_source(
    tmp_path: Path,
) -> None:
    module = load_module()
    runner = make_synthetic_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )

    environment = module.build_routing_environment(runner.inputs)

    assert environment["CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT"] == str(
        runner.inputs.build_context_root
    )
    assert environment["CHUMMER_RUN_SERVICES_SOURCE"] == str(
        runner.inputs.source_root
    )
    assert environment["CHUMMER_HUB_REGISTRY_SOURCE"] == str(
        runner.inputs.hub_registry_root
    )
    assert environment["CHUMMER_DESIGN_PRODUCT_SOURCE"] == str(
        runner.inputs.design_product_root
    )
    assert environment[
        "CHUMMER_FLEET_MEDIA_FACTORY_CONTRACTS_SOURCE"
    ] == str(
        runner.inputs.fleet_media_factory_root
        / "src"
        / "Chummer.Media.Contracts"
    )


@pytest.mark.parametrize(
    ("dirty", "observed_head"),
    (
        (b" M black-ledger/source.txt\n", None),
        (b"", "8" * 40),
    ),
)
def test_synthetic_git_dependency_rejects_dirty_or_mismatched_ref(
    tmp_path: Path,
    dirty: bytes,
    observed_head: str | None,
) -> None:
    module = load_module()
    placeholder = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    runner = make_synthetic_runner(module, tmp_path, placeholder)
    repository = runner.inputs.hub_registry_root
    unseal_test_repository(repository)
    consumed = repository / "black-ledger"
    consumed.mkdir()
    (consumed / "source.txt").write_text("exact\n", encoding="utf-8")
    seal_test_repository(repository)
    content_sha256, _count, _file_set = module.source_content_sha256(
        repository,
        ["black-ledger/source.txt"],
    )
    expected_head = runner.inputs.expected_hub_registry_head
    commands = FakeCommands(
        git_provenance_callback(
            module,
            repository,
            expected_head=expected_head,
            observed_head=observed_head,
            dirty=dirty,
        )
    )
    runner = module.GovernedCutoverRunner(
        runner.inputs,
        command_runner=commands,
    )

    with pytest.raises(module.CutoverError, match="clean, exact"):
        runner._git_source_provenance(
            name="hub-registry",
            repository=repository,
            consumed_path=consumed,
            expected_head=expected_head,
            expected_content_sha256=content_sha256,
            allow_docker_excluded_ignored=False,
        )


def test_synthetic_git_dependency_rejects_content_pin_mismatch(
    tmp_path: Path,
) -> None:
    module = load_module()
    placeholder = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    runner = make_synthetic_runner(module, tmp_path, placeholder)
    repository = runner.inputs.hub_registry_root
    unseal_test_repository(repository)
    consumed = repository / "black-ledger"
    consumed.mkdir()
    (consumed / "source.txt").write_text("exact\n", encoding="utf-8")
    seal_test_repository(repository)
    expected_head = runner.inputs.expected_hub_registry_head
    commands = FakeCommands(
        git_provenance_callback(
            module,
            repository,
            expected_head=expected_head,
        )
    )
    runner = module.GovernedCutoverRunner(
        runner.inputs,
        command_runner=commands,
    )

    with pytest.raises(module.CutoverError, match="content digest"):
        runner._git_source_provenance(
            name="hub-registry",
            repository=repository,
            consumed_path=consumed,
            expected_head=expected_head,
            expected_content_sha256="f" * 64,
            allow_docker_excluded_ignored=False,
        )


@pytest.mark.parametrize(
    "hostile_state",
    ("replace", "shallow", "promisor"),
)
def test_synthetic_git_dependency_rejects_hostile_repository_state(
    tmp_path: Path,
    hostile_state: str,
) -> None:
    module = load_module()
    placeholder = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    base = make_synthetic_runner(module, tmp_path, placeholder)
    repository, consumed, content_sha256 = prepare_hub_provenance_fixture(
        module,
        base,
    )
    commands = FakeCommands(
        git_provenance_callback(
            module,
            repository,
            expected_head=base.inputs.expected_hub_registry_head,
            replace_refs=(
                b"refs/replace/1111111111111111111111111111111111111111\n"
                if hostile_state == "replace"
                else b""
            ),
            shallow=(
                b"true\n" if hostile_state == "shallow" else b"false\n"
            ),
            promisor_configuration=(
                b"remote.origin.promisor true\n"
                if hostile_state == "promisor"
                else b""
            ),
        )
    )
    runner = module.GovernedCutoverRunner(
        base.inputs,
        command_runner=commands,
    )

    with pytest.raises(
        module.CutoverError,
        match="replace, shallow, or promisor",
    ):
        runner._git_source_provenance(
            name="hub-registry",
            repository=repository,
            consumed_path=consumed,
            expected_head=runner.inputs.expected_hub_registry_head,
            expected_content_sha256=content_sha256,
            allow_docker_excluded_ignored=False,
        )


def test_synthetic_git_dependency_requires_strict_full_object_verification(
    tmp_path: Path,
) -> None:
    module = load_module()
    placeholder = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    base = make_synthetic_runner(module, tmp_path, placeholder)
    repository, consumed, content_sha256 = prepare_hub_provenance_fixture(
        module,
        base,
    )
    commands = FakeCommands(
        git_provenance_callback(
            module,
            repository,
            expected_head=base.inputs.expected_hub_registry_head,
        )
    )
    runner = module.GovernedCutoverRunner(
        base.inputs,
        command_runner=commands,
    )

    provenance = runner._git_source_provenance(
        name="hub-registry",
        repository=repository,
        consumed_path=consumed,
        expected_head=runner.inputs.expected_hub_registry_head,
        expected_content_sha256=content_sha256,
        allow_docker_excluded_ignored=False,
    )

    assert provenance["sourceKind"] == module.SYNTHETIC_SOURCE_KIND
    fsck_calls = [
        call
        for call in commands.calls
        if call[0][-5:]
        == ["fsck", "--strict", "--full", "--no-dangling", "--no-progress"]
    ]
    assert len(fsck_calls) == 1
    assert fsck_calls[0][1] == module.SYNTHETIC_GIT_FSCK_TIMEOUT_SECONDS
    assert all(
        call[1] == module.COMMAND_TIMEOUT_SECONDS
        for call in commands.calls
        if call not in fsck_calls
    )


def test_synthetic_git_dependency_fsck_timeout_fails_closed(
    tmp_path: Path,
) -> None:
    module = load_module()
    placeholder = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    base = make_synthetic_runner(module, tmp_path, placeholder)
    repository, consumed, content_sha256 = prepare_hub_provenance_fixture(
        module,
        base,
    )
    provenance_callback = git_provenance_callback(
        module,
        repository,
        expected_head=base.inputs.expected_hub_registry_head,
    )

    def callback(arguments, timeout, check):
        if arguments[-5:] == [
            "fsck",
            "--strict",
            "--full",
            "--no-dangling",
            "--no-progress",
        ]:
            raise module.CommandDeadlineExceeded(
                "bounded operator command timed out"
            )
        return provenance_callback(arguments, timeout, check)

    commands = FakeCommands(callback)
    runner = module.GovernedCutoverRunner(
        base.inputs,
        command_runner=commands,
    )

    with pytest.raises(
        module.CommandDeadlineExceeded,
        match="bounded operator command timed out",
    ):
        runner._git_source_provenance(
            name="hub-registry",
            repository=repository,
            consumed_path=consumed,
            expected_head=runner.inputs.expected_hub_registry_head,
            expected_content_sha256=content_sha256,
            allow_docker_excluded_ignored=False,
        )

    fsck_calls = [
        call
        for call in commands.calls
        if call[0][-5:]
        == ["fsck", "--strict", "--full", "--no-dangling", "--no-progress"]
    ]
    assert len(fsck_calls) == 1
    assert fsck_calls[0][1] == module.SYNTHETIC_GIT_FSCK_TIMEOUT_SECONDS


def test_real_sealed_standalone_git_repository_passes_strict_provenance(
    tmp_path: Path,
) -> None:
    module = load_module()
    base = make_synthetic_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )
    repository = base.inputs.hub_registry_root
    unseal_test_repository(repository)
    shutil.rmtree(repository / ".git")
    (repository / "fixture.txt").unlink()
    subprocess.run(
        ["/usr/bin/git", "init", "--initial-branch=main", str(repository)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "config", "user.name", "Test"],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "config",
            "user.email",
            "test@example.invalid",
        ],
        check=True,
    )
    consumed = repository / "black-ledger"
    consumed.mkdir()
    (consumed / "source.txt").write_text("exact\n", encoding="utf-8")
    subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "add", "--all"],
        check=True,
    )
    subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "commit", "-m", "fixture"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "remote",
            "add",
            "origin",
            module.CANONICAL_ORIGIN_URLS["hub-registry"],
        ],
        check=True,
    )
    head = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "update-ref",
            "refs/remotes/origin/main",
            head,
        ],
        check=True,
    )
    seal_test_repository(repository)
    content_sha256, _count, _file_set = module.source_content_sha256(
        repository,
        ["black-ledger/source.txt"],
    )
    runner = module.GovernedCutoverRunner(
        replace(
            base.inputs,
            expected_hub_registry_head=head,
            expected_hub_registry_content_sha256=content_sha256,
        ),
        command_runner=module.CommandRunner(
            docker_config_root=tmp_path / "docker-config",
        ),
    )

    provenance = runner._git_source_provenance(
        name="hub-registry",
        repository=repository,
        consumed_path=consumed,
        expected_head=head,
        expected_content_sha256=content_sha256,
        allow_docker_excluded_ignored=False,
    )

    assert provenance["head"] == head
    assert provenance["originMain"] == head
    assert provenance["contentSha256"] == content_sha256


def test_synthetic_git_dependency_rejects_content_drift_after_pin(
    tmp_path: Path,
) -> None:
    module = load_module()
    placeholder = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    base = make_synthetic_runner(module, tmp_path, placeholder)
    repository, consumed, content_sha256 = prepare_hub_provenance_fixture(
        module,
        base,
    )
    unseal_test_repository(repository)
    (consumed / "source.txt").write_text("drifted\n", encoding="utf-8")
    seal_test_repository(repository)
    commands = FakeCommands(
        git_provenance_callback(
            module,
            repository,
            expected_head=base.inputs.expected_hub_registry_head,
        )
    )
    runner = module.GovernedCutoverRunner(
        base.inputs,
        command_runner=commands,
    )

    with pytest.raises(module.CutoverError, match="content digest"):
        runner._git_source_provenance(
            name="hub-registry",
            repository=repository,
            consumed_path=consumed,
            expected_head=runner.inputs.expected_hub_registry_head,
            expected_content_sha256=content_sha256,
            allow_docker_excluded_ignored=False,
        )


def test_source_replay_preflight_rejects_content_pin_mismatch_before_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    runner = make_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )
    active_build_info = tmp_path / "candidate-build-info.json"
    active_build_info.write_text("{}\n", encoding="utf-8")
    active_build_info.chmod(0o600)
    expected_digest = module.sha256_bytes(active_build_info.read_bytes())
    observed = {
        "synthetic-build-context": {
            "dockerignoreSha256": "1" * 64,
        },
        "hub-registry": {
            "contentSha256": "2" * 64,
        },
    }
    recorded = copy.deepcopy(observed)
    recorded["hub-registry"]["contentSha256"] = "3" * 64
    runner._validate_source = lambda: None
    runner._capture_build_source_provenance = lambda: copy.deepcopy(
        observed
    )
    runner._run_job = lambda **_kwargs: pytest.fail(
        "source replay preflight dispatched an operator job"
    )
    monkeypatch.setattr(
        module,
        "bind_active_build_info",
        lambda *_args, **_kwargs: (
            active_build_info,
            expected_digest,
            {"buildSourceProvenance": recorded},
        ),
    )

    with pytest.raises(
        module.CutoverError,
        match="build-source replay binding drifted",
    ):
        runner.verify_source_replay(
            active_build_info=active_build_info,
            expected_active_build_info_sha256=expected_digest,
            expected_candidate_image_id=IMAGE,
            expected_candidate_tool_image_id=TOOL_IMAGE,
        )


def test_archive_source_mode_is_not_exposed() -> None:
    module = load_module()

    assert not hasattr(module, "SOURCE_ARCHIVE_AUTHORITY_CONTRACT")
    assert not hasattr(module.GovernedCutoverRunner, "_archive_source_provenance")


def test_compose_exposes_all_cutover_build_sources_with_canonical_defaults() -> None:
    compose = (ROOT / "docker-compose.public-edge.yml").read_text(
        encoding="utf-8"
    )
    dockerfile = (ROOT / "Chummer.Run.Api" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert compose.count(
        "${CHUMMER_HUB_REGISTRY_SOURCE:-"
        "/docker/chummercomplete/chummer-hub-registry}"
    ) == 5
    assert compose.count(
        "${CHUMMER_DESIGN_PRODUCT_SOURCE:-"
        "/docker/chummercomplete/chummer-design}"
    ) == 5
    assert compose.count(
        "${CHUMMER_FLEET_MEDIA_FACTORY_CONTRACTS_SOURCE:-"
        "/docker/fleet/repos/chummer-media-factory/src/"
        "Chummer.Media.Contracts}"
    ) >= 6
    assert (
        "COPY --from=hub-registry-source black-ledger/ "
        "chummer-hub-registry/black-ledger/"
    ) in dockerfile
    assert "COPY chummer-hub-registry/black-ledger/" not in dockerfile


def test_install_linking_tool_bundles_pinned_gss_runtime_without_package_install() -> None:
    dockerfile = (ROOT / "Chummer.Run.Api" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    tool_stage = dockerfile.split(
        " AS install-linking-postgres-tool-final\n",
        1,
    )[1].split("\nFROM ", 1)[0]

    for library in (
        "libgssapi_krb5.so.2",
        "libgssapi_krb5.so.2.2",
        "libk5crypto.so.3",
        "libk5crypto.so.3.1",
        "libkeyutils.so.1",
        "libkeyutils.so.1.10",
        "libkrb5.so.3",
        "libkrb5.so.3.3",
        "libkrb5support.so.0",
        "libkrb5support.so.0.1",
    ):
        assert f"/usr/lib/x86_64-linux-gnu/{library}" in tool_stage
    assert "COPY --from=build" in tool_stage
    assert not any(
        package_manager in tool_stage
        for package_manager in ("apt-get", "apt ", "apk ", "dnf ", "yum ")
    )


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
                "chummer5a_default": {"NetworkID": ""},
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

        def _final_bind_compose_inputs(self, **_kwargs):
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


def test_stopped_container_rejects_nonempty_network_id_drift(
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
    payload["NetworkSettings"]["Networks"]["chummer5a_default"][
        "NetworkID"
    ] = "f" * 64
    payload_holder["payload"] = payload

    with pytest.raises(module.CutoverError, match="network identity drifted"):
        runner._inspect_container(
            container_name=payload["Name"][1:],
            service="chummer-install-linking-postgres-admin",
            project=runner._job_project("prepare"),
            command=["prepare"],
        )


@pytest.mark.parametrize(
    "mutation",
    ("network-id", "network-mode", "state", "extra-network"),
)
def test_started_container_requires_exact_network_identity(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    payload = {
        "HostConfig": {"NetworkMode": "chummer5a_default"},
        "Id": CONTAINER_ID,
        "NetworkSettings": {
            "Networks": {
                "chummer5a_default": {"NetworkID": NETWORK_ID},
            },
        },
        "State": {"Status": "exited"},
    }
    if mutation == "network-id":
        payload["NetworkSettings"]["Networks"]["chummer5a_default"][
            "NetworkID"
        ] = "f" * 64
    elif mutation == "network-mode":
        payload["HostConfig"]["NetworkMode"] = "replacement"
    elif mutation == "state":
        payload["State"]["Status"] = "created"
    elif mutation == "extra-network":
        payload["NetworkSettings"]["Networks"]["replacement"] = {
            "NetworkID": "f" * 64,
        }

    def callback(_arguments, _timeout, _check):
        return module.CommandResult(
            0,
            json.dumps([payload]).encode(),
            b"",
        )

    runner = make_runner(module, tmp_path, FakeCommands(callback))
    with pytest.raises(
        module.CutoverError,
        match="started operator network identity drifted",
    ):
        runner._require_observed_network_identity(
            container_id=CONTAINER_ID,
            service="chummer-install-linking-postgres-admin",
        )


def test_started_container_accepts_exact_network_identity(
    tmp_path: Path,
) -> None:
    module = load_module()
    payload = {
        "HostConfig": {"NetworkMode": "chummer5a_default"},
        "Id": CONTAINER_ID,
        "NetworkSettings": {
            "Networks": {
                "chummer5a_default": {"NetworkID": NETWORK_ID},
            },
        },
        "State": {"Status": "exited"},
    }

    def callback(_arguments, _timeout, _check):
        return module.CommandResult(
            0,
            json.dumps([payload]).encode(),
            b"",
        )

    runner = make_runner(module, tmp_path, FakeCommands(callback))
    runner._require_observed_network_identity(
        container_id=CONTAINER_ID,
        service="chummer-install-linking-postgres-admin",
    )


def test_local_store_proof_rejects_decoy_and_accepts_compose_none_network(
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

    payload_holder["payload"]["Config"]["Env"][1] = (
        f"CHUMMER_INSTALL_LINKING_STORE_PATH={canonical_store}"
    )
    payload_holder["payload"]["NetworkSettings"]["Networks"] = {
        "none": {}
    }
    container_id, topology = runner._inspect_container(
        container_name=str(payload_holder["payload"]["Name"])[1:],
        service=service,
        project=project,
        command=["prove-local-store-absent"],
    )

    assert container_id == CONTAINER_ID
    assert topology["networkId"] == ""
    assert topology["networkMode"] == "none"

    payload_holder["payload"]["NetworkSettings"]["Networks"] = {
        "bridge": {"NetworkID": "a" * 64}
    }
    with pytest.raises(
        module.CutoverError,
        match="stopped operator container contract drifted",
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
                "postquiesce-attempt01-prove-authority-ready",
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

        def _final_bind_compose_inputs(self, **_kwargs):
            return None

    commands = FakeCommands(callback)
    base = make_runner(module, tmp_path, commands)
    runner = Harness(base.inputs, command_runner=commands)
    runner.candidate_image_id = IMAGE
    runner.candidate_tool_image_id = TOOL_IMAGE

    with pytest.raises(module.AmbiguousCutoverError):
        runner._run_job(
            job_name="postquiesce-attempt01-prove-authority-ready",
            service="chummer-install-linking-postgres-runtime-proof",
            command=("prove-authority-ready",),
            proof_contract=(
                "chummer.install_linking_postgres_authority_readiness_proof.v1"
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


def docker_context_policy_for_text(module, text: str) -> dict[str, object]:
    records, malformed_continuations = (
        module._docker_logical_instruction_records(text)
    )
    assert not malformed_continuations
    return module.docker_context_policy_findings(records)


def test_runtime_docker_context_policy_accepts_only_the_reviewed_copy_set() -> None:
    module = load_module()
    dockerfile_text = (ROOT / "Chummer.Run.Api" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    findings = docker_context_policy_for_text(module, dockerfile_text)

    assert findings["exactReviewedCopySet"] is True
    for key in (
        "forbiddenContextUses",
        "heredocUses",
        "mountFromUses",
        "noncopyFromUses",
        "invalidCopyFromUses",
        "continuationUses",
    ):
        assert findings[key] == []


@pytest.mark.parametrize(
    ("mutation", "finding_key"),
    (
        ("literal_run_mount", "mountFromUses"),
        ("variable_run_mount", "mountFromUses"),
        ("onbuild_mount", "mountFromUses"),
        ("onbuild_copy", "forbiddenContextUses"),
        ("context_from", "forbiddenContextUses"),
        ("stage_alias_collision", "forbiddenContextUses"),
        ("arg_context_literal", "forbiddenContextUses"),
        ("copy_from_variable", "invalidCopyFromUses"),
        ("noncopy_from_option", "noncopyFromUses"),
        ("case_variant", "forbiddenContextUses"),
        ("continuation_variant", "continuationUses"),
        ("heredoc", "heredocUses"),
    ),
)
def test_runtime_docker_context_policy_rejects_every_other_selection_form(
    mutation: str,
    finding_key: str,
) -> None:
    module = load_module()
    original = (ROOT / "Chummer.Run.Api" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    final_from = (
        "FROM "
        + module.DOCKER_BASE_IMAGE_REFERENCES["final"]
        + " AS final"
    )
    reviewed_copy = next(
        instruction
        for instruction in (
            module.EXPECTED_NAMED_CONTEXT_COPY_INSTRUCTIONS_BY_STAGE[
                "public-pwa-proof"
            ]
        )
        if "validate_public_pwa_proof_authority.py" in instruction
    )
    injected_instructions = {
        "literal_run_mount": (
            "RUN --mount=type=bind,from=run-services-source,"
            "source=.,target=/mnt true"
        ),
        "variable_run_mount": (
            "RUN --mount=type=bind,from=${SOURCE},source=.,target=/mnt true"
        ),
        "onbuild_mount": (
            "ONBUILD RUN --mount=type=bind,from=${SOURCE},"
            "source=.,target=/mnt true"
        ),
        "onbuild_copy": (
            "ONBUILD COPY --from=hub-registry-source "
            "black-ledger/ /tmp/black-ledger/"
        ),
        "context_from": "FROM run-services-source AS bypass",
        "arg_context_literal": "ARG SOURCE=design-product",
        "copy_from_variable": (
            "COPY --from=${SOURCE} README.md /tmp/unreviewed"
        ),
        "noncopy_from_option": "RUN echo --from=run-services-source",
        "heredoc": "RUN <<EOF\ntrue\nEOF",
    }
    if mutation in injected_instructions:
        mutated = original.replace(
            final_from + "\n",
            final_from + "\n" + injected_instructions[mutation] + "\n",
            1,
        )
    elif mutation == "stage_alias_collision":
        mutated = original.replace(
            final_from,
            final_from.rsplit(" AS ", 1)[0] + " AS design-product",
            1,
        )
    elif mutation == "case_variant":
        mutated = original.replace(
            reviewed_copy,
            reviewed_copy.replace(
                "run-services-source",
                "RUN-SERVICES-SOURCE",
            ),
            1,
        )
    elif mutation == "continuation_variant":
        mutated = original.replace(
            reviewed_copy,
            reviewed_copy.replace(
                "run-services-source",
                "run-services-\\\nsource",
            ),
            1,
        )
    else:  # pragma: no cover - the parameter list is closed above.
        raise AssertionError(f"Unhandled Docker context mutation: {mutation}")
    assert mutated != original

    findings = docker_context_policy_for_text(module, mutated)

    assert findings[finding_key]


@pytest.mark.parametrize(
    "instruction",
    (
        (
            "RUN --mount=type=bind,"
            "source=chummer-hub-registry/black-ledger,"
            "target=/mnt,ro cp -a /mnt /tmp/unreviewed-ledger"
        ),
        "RUN --mount=type=cache,target=/root/.cache true",
        "RUN --mount=type=secret,id=release-key,target=/run/key true",
        "RUN --mount=type=ssh,id=default true",
        (
            "RUN --mount=target=/mnt,"
            "source=chummer-hub-registry/black-ledger,"
            "type=bind,ro cp -a /mnt /tmp/unreviewed-ledger"
        ),
        "RUN --network=none --mount=type=cache,target=/root/.cache true",
        "rUn --MoUnT=TyPe=CaChE,TaRgEt=/root/.cache true",
        "RUN\t--mount=type=cache,target=/root/.cache true",
        "RUN --mount\t=\ttype=ssh,id=default true",
        "RUN --mount=type=cache,\\\n    target=/root/.cache true",
        "RUN \\\n    --mount=type=ssh,id=default true",
        "RUN --mou\\\nnt=type=cache,target=/root/.cache true",
    ),
)
def test_runtime_docker_context_policy_rejects_every_run_mount_form(
    instruction: str,
) -> None:
    module = load_module()
    original = (ROOT / "Chummer.Run.Api" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    insertion_point = (
        "COPY --from=public-pwa-proof "
        "/proof/public-pwa-proof-authority.receipt.json "
        "/tmp/public-pwa-proof-authority.receipt.json\n"
    )
    mutated = original.replace(
        insertion_point,
        insertion_point + instruction + "\n",
        1,
    )

    findings = docker_context_policy_for_text(module, mutated)

    assert findings["mountFromUses"]
    if "\\\n" in instruction:
        assert findings["continuationUses"]


@pytest.mark.parametrize(
    "instruction",
    (
        "ONBUILD",
        "ONBUILD RUN true",
        (
            "ONBUILD COPY --from=run-services-source "
            "Chummer.Run.Api/ /tmp/unreviewed/"
        ),
        "ONBUILD ADD https://example.invalid/payload /tmp/payload",
        "ONBUILD RUN --mount=type=cache,target=/root/.cache true",
        "oNbUiLd\tRuN true",
        "ONBUILD " + "\\\n" + "    RUN true",
        "ONBU" + "\\\n" + "ILD RUN true",
    ),
)
def test_runtime_docker_policy_rejects_every_onbuild_form(
    instruction: str,
) -> None:
    module = load_module()
    original = (ROOT / "Chummer.Run.Api" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    insertion_point = (
        "COPY --from=public-pwa-proof "
        "/proof/public-pwa-proof-authority.receipt.json "
        "/tmp/public-pwa-proof-authority.receipt.json\n"
    )
    mutated = original.replace(
        insertion_point,
        insertion_point + instruction + "\n",
        1,
    )

    findings = docker_context_policy_for_text(module, mutated)

    assert findings["onbuildUses"]


@pytest.mark.parametrize(
    "mutation",
    (
        "unreviewed_frontend",
        "late_syntax",
        "escape_backtick",
        "mixed_whitespace_escape",
    ),
)
def test_runtime_dockerfile_parser_policy_rejects_syntax_switches(
    mutation: str,
) -> None:
    module = load_module()
    original = (ROOT / "Chummer.Run.Api" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    exact_syntax = f"# syntax={module.DOCKERFILE_FRONTEND_REFERENCE}"
    if mutation == "unreviewed_frontend":
        mutated = original.replace(
            exact_syntax,
            "# syntax=docker/dockerfile:1.7",
            1,
        )
    elif mutation == "late_syntax":
        mutated = original.replace(
            exact_syntax + "\n",
            exact_syntax + "\n# syntax=docker/dockerfile:1.7\n",
            1,
        )
    elif mutation in {"escape_backtick", "mixed_whitespace_escape"}:
        escape_directive = (
            "# escape=`"
            if mutation == "escape_backtick"
            else "\t#\tescape \t= `"
        )
        mutated = original.replace(
            exact_syntax + "\n",
            exact_syntax + "\n" + escape_directive + "\n",
            1,
        )
        insertion_point = (
            "COPY --from=public-pwa-proof "
            "/proof/public-pwa-proof-authority.receipt.json "
            "/tmp/public-pwa-proof-authority.receipt.json\n"
        )
        mutated = mutated.replace(
            insertion_point,
            insertion_point
            + "RUN --mou`\n"
            + "nt=type=bind,source=chummer-hub-registry/black-ledger,"
            + "target=/mnt cp -a /mnt /tmp/unreviewed-ledger\n",
            1,
        )
    else:  # pragma: no cover - the parameter list is closed above.
        raise AssertionError(f"Unhandled parser directive mutation: {mutation}")

    with pytest.raises(
        module.CutoverError,
        match="parser directive contract drifted",
    ):
        module.require_candidate_dockerfile_parser_policy(mutated)


def reviewed_rendered_build(
    *,
    service_name: str,
) -> tuple[dict[str, object], dict[str, str]]:
    additional_contexts = {
        "design-product": "/synthetic/design-product",
        "fleet-media-factory-contracts": (
            "/synthetic/fleet-media-factory/src/Chummer.Media.Contracts"
        ),
        "hub-registry-source": "/synthetic/hub-registry",
        "run-services-source": "/synthetic/run-services",
    }
    build: dict[str, object] = {
        "additional_contexts": additional_contexts,
        "args": {
            "CHUMMER_BUILD_CONCURRENCY": "1",
            "CHUMMER_RUNTIME_GID": "1654",
            "CHUMMER_RUNTIME_UID": "1654",
        },
        "context": "/synthetic/run-services",
        "dockerfile": (
            "/synthetic/run-services/Chummer.Run.Api/Dockerfile"
        ),
    }
    if service_name != "chummer-portal":
        build["target"] = "install-linking-postgres-tool-final"
    return build, additional_contexts


def test_runtime_rendered_build_contract_accepts_all_cutover_services() -> None:
    module = load_module()
    services = (
        "chummer-portal",
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-runtime-proof",
        "chummer-install-linking-postgres-import-presence-proof",
        "chummer-install-linking-postgres-import",
    )

    for service_name in services:
        build, additional_contexts = reviewed_rendered_build(
            service_name=service_name
        )
        assert module.rendered_build_contract_matches(
            build,
            service_name=service_name,
            build_context="/synthetic/run-services",
            dockerfile=(
                "/synthetic/run-services/Chummer.Run.Api/Dockerfile"
            ),
            additional_contexts=additional_contexts,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "dockerfile_inline",
        "pull",
        "alternate_dockerfile",
        "context_selector_arg",
        "context_selector_value",
        "alternate_target",
    ),
)
def test_runtime_rendered_build_contract_rejects_alternate_authority(
    mutation: str,
) -> None:
    module = load_module()
    service_name = "chummer-install-linking-postgres-admin"
    build, additional_contexts = reviewed_rendered_build(
        service_name=service_name
    )
    if mutation == "dockerfile_inline":
        build["dockerfile_inline"] = "FROM scratch"
    elif mutation == "pull":
        build["pull"] = True
    elif mutation == "alternate_dockerfile":
        build["dockerfile"] = "/tmp/unreviewed.Dockerfile"
    elif mutation == "context_selector_arg":
        build_args = build["args"]
        assert isinstance(build_args, dict)
        build_args["SOURCE_CONTEXT"] = "run-services-source"
    elif mutation == "context_selector_value":
        build_args = build["args"]
        assert isinstance(build_args, dict)
        build_args["CHUMMER_RUNTIME_UID"] = "run-services-source"
    elif mutation == "alternate_target":
        build["target"] = "final"
    else:  # pragma: no cover - the parameter list is closed above.
        raise AssertionError(f"Unhandled rendered build mutation: {mutation}")

    assert not module.rendered_build_contract_matches(
        build,
        service_name=service_name,
        build_context="/synthetic/run-services",
        dockerfile="/synthetic/run-services/Chummer.Run.Api/Dockerfile",
        additional_contexts=additional_contexts,
    )


def reviewed_rendered_compose(
    module,
) -> tuple[dict[str, object], dict[str, str], dict[str, str]]:
    expected_images = dict(module.PUBLIC_EDGE_RAW_SERVICE_IMAGES)
    services: dict[str, dict[str, object]] = {
        service_name: {"build": {}}
        for service_name in module.PUBLIC_EDGE_RENDERED_BUILD_SERVICE_NAMES
        if service_name not in module.PUBLIC_EDGE_BUILD_SERVICE_TARGETS
    }
    additional_contexts: dict[str, str] = {}
    for service_name in module.PUBLIC_EDGE_BUILD_SERVICE_TARGETS:
        build, service_contexts = reviewed_rendered_build(
            service_name=service_name
        )
        additional_contexts = service_contexts
        service = {
            key: None
            for key in module.PUBLIC_EDGE_RENDERED_SERVICE_KEYS_BY_SERVICE[
                service_name
            ]
        }
        service["build"] = build
        service["image"] = expected_images[service_name]
        expected_profiles = module.PUBLIC_EDGE_SERVICE_PROFILES_BY_SERVICE[
            service_name
        ]
        if expected_profiles:
            service["profiles"] = list(expected_profiles)
        services[service_name] = service
    return {"services": services}, expected_images, additional_contexts


def test_runtime_rendered_compose_accepts_only_the_exact_build_authority() -> None:
    module = load_module()
    payload, expected_images, additional_contexts = (
        reviewed_rendered_compose(module)
    )

    failures = module.public_edge_rendered_compose_failures(
        payload,
        expected_images=expected_images,
        build_context="/synthetic/run-services",
        dockerfile="/synthetic/run-services/Chummer.Run.Api/Dockerfile",
        additional_contexts=additional_contexts,
    )

    assert failures == []


@pytest.mark.parametrize(
    "mutation",
    (
        "included_build_service",
        "build_pull",
        "pull_policy",
        "platform",
        "profiles",
        "develop",
        "provider",
        "models",
        "image",
        "tool_profiles",
    ),
)
def test_runtime_rendered_compose_rejects_every_unreviewed_build_selector(
    mutation: str,
) -> None:
    module = load_module()
    payload, expected_images, additional_contexts = (
        reviewed_rendered_compose(module)
    )
    services = payload["services"]
    assert isinstance(services, dict)
    portal = services["chummer-portal"]
    assert isinstance(portal, dict)
    if mutation == "included_build_service":
        services["included-sixth-build"] = {
            "build": {"context": "/unreviewed"}
        }
    elif mutation == "build_pull":
        build = portal["build"]
        assert isinstance(build, dict)
        build["pull"] = True
    elif mutation in {
        "pull_policy",
        "platform",
        "profiles",
        "develop",
        "provider",
        "models",
    }:
        values: dict[str, object] = {
            "pull_policy": "always",
            "platform": "linux/amd64",
            "profiles": ["unreviewed-build"],
            "develop": {},
            "provider": {"type": "unreviewed"},
            "models": {},
        }
        portal[mutation] = values[mutation]
    elif mutation == "image":
        portal["image"] = "unreviewed.invalid/portal:latest"
    elif mutation == "tool_profiles":
        tool = services["chummer-install-linking-postgres-admin"]
        assert isinstance(tool, dict)
        tool["profiles"] = ["unreviewed-build"]
    else:  # pragma: no cover - the parameter list is closed above.
        raise AssertionError(f"Unhandled rendered mutation: {mutation}")

    failures = module.public_edge_rendered_compose_failures(
        payload,
        expected_images=expected_images,
        build_context="/synthetic/run-services",
        dockerfile="/synthetic/run-services/Chummer.Run.Api/Dockerfile",
        additional_contexts=additional_contexts,
    )

    assert failures


def test_compose_input_final_bind_covers_every_effective_file(
    tmp_path: Path,
) -> None:
    module = load_module()
    events: list[object] = []

    class Harness(module.GovernedCutoverRunner):
        def _validate_source(self):
            events.append("source")

        def _bind_existing_build_override(self):
            events.append("build-override")

        def _bind_job_override(self, path, **kwargs):
            events.append(("job-override", path, kwargs))

        def _validate_rendered_compose(self, **kwargs):
            events.append(("rendered", kwargs))

        def _bind_pinned_source_inputs(self):
            events.append("pinned-source-inputs")

    base = make_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )
    runner = Harness(base.inputs, command_runner=base.commands)
    override = tmp_path / "job.override.json"
    command = ("prove-authority-ready",)

    runner._final_bind_compose_inputs(
        job_override=override,
        job_service="chummer-install-linking-postgres-runtime-proof",
        job_command=command,
        container_name="cutover-job",
        project="chummer6-ilpg-test",
    )

    assert [event if isinstance(event, str) else event[0] for event in events] == [
        "source",
        "build-override",
        "job-override",
        "rendered",
        "source",
        "pinned-source-inputs",
        "build-override",
        "job-override",
    ]
    rendered = events[3]
    assert isinstance(rendered, tuple)
    assert rendered[1] == {
        "overrides": (override,),
        "project": "chummer6-ilpg-test",
        "transient_service_keys": {
            "chummer-install-linking-postgres-runtime-proof": (
                "container_name",
            )
        },
    }


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        ("base-compose", "independently pinned cutover input digest drifted"),
        ("canonical-env", "independently pinned cutover input digest drifted"),
        ("build-override", "retained cutover image override identity drifted"),
        ("job-override", "generated job Compose override identity drifted"),
    ),
)
def test_final_bind_rejects_base_env_or_override_mutated_during_provenance(
    tmp_path: Path,
    mutation: str,
    expected_error: str,
) -> None:
    module = load_module()
    runner, commands = make_pinned_final_bind_runner(module, tmp_path)
    service = "chummer-install-linking-postgres-runtime-proof"
    command = ("prove-authority-ready",)
    override, container_name, project = runner._job_override(
        job_name="final-bind-proof",
        service=service,
        command=command,
    )
    bind_arguments = {
        "job_override": override,
        "job_service": service,
        "job_command": command,
        "container_name": container_name,
        "project": project,
    }
    runner._final_bind_compose_inputs(**bind_arguments)
    provenance_events: list[str] = []

    def capture_with_mutation():
        provenance_events.append("source-provenance")
        if mutation == "base-compose":
            runner.inputs.compose_file.write_bytes(
                runner.inputs.compose_file.read_bytes()
                + b"\n# changed during provenance\n"
            )
        elif mutation == "canonical-env":
            runner.inputs.env_file.write_text(
                "FINAL_BIND_AUTHORITY=changed-during-provenance\n",
                encoding="utf-8",
            )
        elif mutation == "build-override":
            payload = runner._build_override_payload()
            portal = payload["services"]["chummer-portal"]
            assert isinstance(portal, dict)
            portal["pull_policy"] = "always"
            module.write_private_json(
                runner.build_override,
                payload,
                replace=True,
            )
        elif mutation == "job-override":
            payload = runner._job_override_payload(
                service=service,
                command=command,
                container_name=container_name,
            )
            job = payload["services"][service]
            assert isinstance(job, dict)
            job["pull_policy"] = "always"
            module.write_private_json(
                override,
                payload,
                replace=True,
            )
        else:  # pragma: no cover - the parameter set above is closed.
            raise AssertionError(f"unhandled mutation: {mutation}")
        return {}

    runner._capture_build_source_provenance = capture_with_mutation
    runner._capture_build_source_provenance()

    with pytest.raises(module.CutoverError, match=expected_error):
        runner._final_bind_compose_inputs(**bind_arguments)

    assert provenance_events == ["source-provenance"]
    assert commands.calls == []


def test_generated_job_override_is_exactly_sealed_before_create(
    tmp_path: Path,
) -> None:
    module = load_module()
    commands = FakeCommands(
        lambda *_args: module.CommandResult(0, b"", b"")
    )
    runner = make_runner(module, tmp_path, commands)
    command = ("prove-authority-ready",)
    override, container_name, _project = runner._job_override(
        job_name="prove-authority-ready",
        service="chummer-install-linking-postgres-runtime-proof",
        command=command,
    )
    runner._bind_job_override(
        override,
        service="chummer-install-linking-postgres-runtime-proof",
        command=command,
        container_name=container_name,
    )
    tampered = runner._job_override_payload(
        service="chummer-install-linking-postgres-runtime-proof",
        command=command,
        container_name=container_name,
    )
    service = tampered["services"][
        "chummer-install-linking-postgres-runtime-proof"
    ]
    assert isinstance(service, dict)
    service["pull_policy"] = "always"
    module.write_private_json(override, tampered, replace=True)

    with pytest.raises(
        module.CutoverError,
        match="job Compose override identity drifted",
    ):
        runner._bind_job_override(
            override,
            service="chummer-install-linking-postgres-runtime-proof",
            command=command,
            container_name=container_name,
        )


def test_build_and_create_dispatches_are_immediately_preceded_by_final_bind(
    tmp_path: Path,
) -> None:
    module = load_module()

    class StopAtCompose(RuntimeError):
        pass

    build_events: list[str] = []

    class BuildHarness(module.GovernedCutoverRunner):
        def _require_candidate_tags_absent(self):
            return None

        def _resolve_image(self, _tag, *, allow_absent=False):
            return ""

        def _final_bind_compose_inputs(self, **_kwargs):
            build_events.append("final-bind")

        def _capture_build_source_provenance(self):
            build_events.append("source-provenance")
            return {}

        def _compose(self, *arguments, **kwargs):
            build_events.append("compose-command")
            return super()._compose(*arguments, **kwargs)

    def build_callback(_arguments, _timeout, _check):
        build_events.append("compose-build")
        raise StopAtCompose

    build_commands = FakeCommands(build_callback)
    build_root = tmp_path / "build"
    build_root.mkdir()
    base = make_runner(module, build_root, build_commands)
    build_runner = BuildHarness(
        base.inputs,
        command_runner=build_commands,
    )

    with pytest.raises(StopAtCompose):
        build_runner._build_candidates()
    assert build_events == [
        "source-provenance",
        "compose-command",
        "final-bind",
        "compose-build",
    ]

    create_events: list[str] = []
    observed_create_commands: list[tuple[str, ...]] = []
    command_count = 0

    def create_callback(arguments, _timeout, _check):
        nonlocal command_count
        command_count += 1
        if command_count == 1:
            return module.CommandResult(1, b"", b"")
        observed_create_commands.append(tuple(arguments))
        create_events.append("compose-create")
        raise StopAtCompose

    class CreateHarness(module.GovernedCutoverRunner):
        def _job_override(self, **_kwargs):
            return (
                self.inputs.receipt_root / "override.json",
                "cutover-job",
                "chummer6-ilpg-test",
            )

        def _final_bind_compose_inputs(self, **_kwargs):
            create_events.append("final-bind")

        def _compose(self, *arguments, **kwargs):
            create_events.append("compose-command")
            return super()._compose(*arguments, **kwargs)

    create_commands = FakeCommands(create_callback)
    create_root = tmp_path / "create"
    create_root.mkdir()
    base = make_runner(module, create_root, create_commands)
    create_runner = CreateHarness(
        base.inputs,
        command_runner=create_commands,
    )

    with pytest.raises(StopAtCompose):
        create_runner._run_job(
            job_name="prove-authority-ready",
            service="chummer-install-linking-postgres-runtime-proof",
            command=("prove-authority-ready",),
            proof_contract=(
                "chummer.install_linking_postgres_authority_readiness_proof.v1"
            ),
        )
    assert create_events == [
        "compose-command",
        "final-bind",
        "compose-create",
    ]
    assert len(observed_create_commands) == 1
    assert "--no-deps" not in observed_create_commands[0]
    assert observed_create_commands[0][-4:] == (
        "create",
        "--no-build",
        "--no-recreate",
        "chummer-install-linking-postgres-runtime-proof",
    )
    source_tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    runner_class = next(
        node
        for node in source_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "GovernedCutoverRunner"
    )
    for method_name, command_name in (
        ("_build_candidates", "build_command"),
        ("_run_job", "create_command"),
    ):
        method = next(
            node
            for node in runner_class.body
            if isinstance(node, ast.FunctionDef)
            and node.name == method_name
        )
        final_bind_index = next(
            index
            for index, statement in enumerate(method.body)
            if isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and statement.value.func.attr == "_final_bind_compose_inputs"
        )
        dispatch = method.body[final_bind_index + 1]
        assert isinstance(dispatch, ast.Expr)
        assert isinstance(dispatch.value, ast.Call)
        assert isinstance(dispatch.value.func, ast.Attribute)
        assert dispatch.value.func.attr == "run"
        assert dispatch.value.args
        assert isinstance(dispatch.value.args[0], ast.Name)
        assert dispatch.value.args[0].id == command_name


def test_compose_explicit_canonical_env_file_ignores_synthetic_root_dotenv(
    tmp_path: Path,
) -> None:
    module = load_module()
    base = make_runner(
        module,
        tmp_path,
        FakeCommands(lambda *_args: module.CommandResult(0, b"", b"")),
    )
    source = base.inputs.source_root
    base.inputs.compose_file.write_text(
        "services:\n"
        "  probe:\n"
        '    image: "alpine:${FINAL_BIND_ENV_AUTHORITY:'
        '?canonical env required}"\n',
        encoding="utf-8",
    )
    (source / ".env").write_text(
        "FINAL_BIND_ENV_AUTHORITY=hostile-synthetic-root\n",
        encoding="utf-8",
    )
    base.inputs.env_file.write_text(
        "FINAL_BIND_ENV_AUTHORITY=canonical-pinned\n",
        encoding="utf-8",
    )
    base.inputs.env_file.chmod(0o600)
    command_runner = module.CommandRunner(
        docker_config_root=tmp_path / "docker-client",
    )
    runner = module.GovernedCutoverRunner(
        base.inputs,
        command_runner=command_runner,
    )
    module.write_private_json(runner.build_override, {})
    command = runner._compose(
        "config",
        "--format",
        "json",
        project="env-authority-probe",
    )
    assert command[command.index("--env-file") + 1] == str(
        base.inputs.env_file
    )
    assert command[command.index("--project-directory") + 1] == str(source)

    rendered = subprocess.run(
        command,
        cwd=source,
        env=command_runner.environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    assert rendered.returncode == 0, rendered.stderr
    payload = json.loads(rendered.stdout)
    assert payload["services"]["probe"]["image"] == "alpine:canonical-pinned"

    base.inputs.env_file.write_text(
        "UNRELATED_PIN=present\n",
        encoding="utf-8",
    )
    missing = subprocess.run(
        command,
        cwd=source,
        env=command_runner.environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    assert missing.returncode != 0
    assert b"canonical env required" in missing.stderr
    assert b"hostile-synthetic-root" not in missing.stdout + missing.stderr


def test_rendered_compose_policy_expands_every_profile(
    tmp_path: Path,
) -> None:
    module = load_module()
    captured: list[list[str]] = []

    def callback(arguments, _timeout, _check):
        captured.append(arguments)
        return module.CommandResult(0, b"{}", b"")

    commands = FakeCommands(callback)
    runner = make_runner(module, tmp_path, commands)

    with pytest.raises(
        module.CutoverError,
        match="omitted services or networks",
    ):
        runner._validate_rendered_compose()

    assert len(captured) == 1
    command = captured[0]
    profile_index = command.index("--profile")
    assert command[profile_index : profile_index + 5] == [
        "--profile",
        "*",
        "config",
        "--format",
        "json",
    ]
