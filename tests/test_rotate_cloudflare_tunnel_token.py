from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import threading
from typing import Any
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "rotate_cloudflare_tunnel_token.py"
SPEC = importlib.util.spec_from_file_location(
    "rotate_cloudflare_tunnel_token_test",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


ACCOUNT_ID = "a" * 32
TUNNEL_ID = "9e16dede-51cf-40fb-8bc1-2240650874fa"
OLD_SECRET = base64.b64encode(b"o" * 32).decode("ascii")
NEW_SECRET = base64.b64encode(b"n" * 32).decode("ascii")
OTHER_SECRET = base64.b64encode(b"x" * 32).decode("ascii")
GLOBAL_KEY = "global-api-key-that-must-never-leak"
EMAIL = "operator@example.com"


def make_token(secret: str) -> module.SecretText:
    payload = json.dumps(
        {"a": ACCOUNT_ID, "s": secret, "t": TUNNEL_ID},
        separators=(",", ":"),
    ).encode("utf-8")
    return module.SecretText(
        base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    )


OLD_TOKEN = make_token(OLD_SECRET)
NEW_TOKEN = make_token(NEW_SECRET)
OTHER_TOKEN = make_token(OTHER_SECRET)


def owner_only_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def owner_only_file(path: Path, content: str) -> Path:
    owner_only_directory(path.parent)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path


def credentials_file(root: Path) -> Path:
    return owner_only_file(
        root / "cloudflare.env",
        (
            f"CLOUDFLARE_EMAIL={EMAIL}\n"
            f"CLOUDFLARE_GLOBAL_API_KEY={GLOBAL_KEY}\n"
        ),
    )


def token_file(root: Path, token: module.SecretText = OLD_TOKEN) -> Path:
    return owner_only_file(root / "cloudflared.token", token.value + "\n")


def compose_env_file(root: Path, token_path: Path) -> Path:
    return owner_only_file(
        root / "compose.env",
        (
            f"CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE={token_path}\n"
            f"CHUMMER_CLOUDFLARED_RUNTIME_UID={os.geteuid()}\n"
            f"CHUMMER_CLOUDFLARED_RUNTIME_GID={os.getegid()}\n"
            "CHUMMER_RUN_TUNNEL_NETWORK=chummer5a_default\n"
        ),
    )


def connector(identifier: str) -> module.Connector:
    return module.Connector(
        connector_id=identifier,
        version="2026.7.0",
        active_edge_count=4,
        pending_edge_count=0,
    )


OLD_A = "11111111-1111-4111-8111-111111111111"
OLD_B = "22222222-2222-4222-8222-222222222222"
CANARY = "33333333-3333-4333-8333-333333333333"
PRIMARY = "44444444-4444-4444-8444-444444444444"
REPLICA = "55555555-5555-4555-8555-555555555555"
MIGRATION_B = "66666666-6666-4666-8666-666666666666"


def snapshot(*ids: str) -> module.ApiSnapshot:
    return module.ApiSnapshot(
        tunnel_id=TUNNEL_ID,
        tunnel_name="chummer-run",
        status="healthy",
        config_source="cloudflare",
        config_version=12,
        config_sha256="c" * 64,
        connectors=tuple(connector(identifier) for identifier in ids),
    )


class MemoryReceipt:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.forbidden: list[str] = []

    def add_forbidden(self, *values: str) -> None:
        self.forbidden.extend(values)

    def write(self, state: module.ReceiptState) -> None:
        serialized = json.dumps(state.payload(), sort_keys=True)
        assert all(secret not in serialized for secret in self.forbidden)
        self.payloads.append(json.loads(serialized))


class FakeApi:
    def __init__(self) -> None:
        self.phase = "baseline"
        self.current_token = OLD_TOKEN
        self.events: list[str] = []
        self.fail_rollback = False
        self.patch_error_after_apply: BaseException | None = None
        self.final_extra_connector: str | None = None

    def get_token(self) -> module.SecretText:
        return self.current_token

    def get_snapshot(self) -> module.ApiSnapshot:
        result = {
            "baseline": snapshot(OLD_A, OLD_B),
            "canary": snapshot(OLD_A, OLD_B, CANARY),
            "primary": snapshot(OLD_B, CANARY, PRIMARY),
            "replica": snapshot(CANARY, PRIMARY, REPLICA),
            "final": snapshot(PRIMARY, REPLICA),
        }[self.phase]
        if self.phase == "final" and self.final_extra_connector is not None:
            return snapshot(
                PRIMARY,
                REPLICA,
                self.final_extra_connector,
            )
        return result

    def rotate_secret(
        self,
        *,
        tunnel_name: str,
        tunnel_secret: module.SecretText,
    ) -> module.SecretText:
        assert tunnel_name == "chummer-run"
        if tunnel_secret.value == OLD_SECRET:
            self.events.append("patch-old")
            if self.fail_rollback:
                raise module.RotationError("simulated_rollback_failure")
            self.current_token = OLD_TOKEN
            self.phase = "baseline"
            return OLD_TOKEN
        self.events.append("patch-new")
        self.current_token = NEW_TOKEN
        if self.patch_error_after_apply is not None:
            raise self.patch_error_after_apply
        return NEW_TOKEN


class FakeRunner:
    def __init__(self) -> None:
        self.forbidden: list[str] = []

    def add_forbidden(self, *values: str) -> None:
        self.forbidden.extend(values)


class FakeDocker:
    def __init__(self, api: FakeApi) -> None:
        self.api = api
        self.runner = FakeRunner()
        self.events: list[str] = []
        self.fail_canary_join = False
        self.fail_primary_recreate = False

    def validate_host_and_compose(self) -> None:
        self.events.append("validate")

    def verify_connector_container(self, name: str) -> None:
        self.events.append(f"verify:{name}")

    def ensure_canary_absent(self) -> None:
        self.events.append("canary-absent")

    def start_canary(self, path: Path) -> None:
        assert path.read_text(encoding="utf-8").strip() == NEW_TOKEN.value
        self.events.append("start-canary")
        if not self.fail_canary_join:
            self.api.phase = "canary"

    def verify_canary_running(self) -> None:
        self.events.append("verify-canary")

    def recreate_service(self, name: str) -> None:
        self.events.append(f"recreate:{name}")
        if name == module.PRIMARY_SERVICE:
            if self.fail_primary_recreate:
                raise module.RotationError("simulated_primary_failure")
            self.api.phase = "primary"
        else:
            self.api.phase = "replica"

    def remove_canary(self) -> None:
        self.events.append("remove-canary")
        self.api.phase = (
            "final" if self.api.current_token.matches(NEW_TOKEN) else "baseline"
        )


class FakeMigrationApi:
    def __init__(self) -> None:
        self.phase = "legacy"
        self.current_token = OLD_TOKEN

    def get_token(self) -> module.SecretText:
        return self.current_token

    def get_snapshot(self) -> module.ApiSnapshot:
        return {
            "legacy": snapshot(OLD_A),
            "canary_a": snapshot(OLD_A, CANARY),
            "canary_b": snapshot(OLD_A, CANARY, MIGRATION_B),
            "replica": snapshot(OLD_A, CANARY, MIGRATION_B, REPLICA),
            "legacy_retired": snapshot(CANARY, MIGRATION_B, REPLICA),
            "primary": snapshot(CANARY, MIGRATION_B, REPLICA, PRIMARY),
            "after_a": snapshot(MIGRATION_B, REPLICA, PRIMARY),
            "final": snapshot(REPLICA, PRIMARY),
        }[self.phase]


class FakeMigrationDocker:
    def __init__(self, api: FakeMigrationApi) -> None:
        self.api = api
        self.runner = FakeRunner()
        self.events: list[str] = []
        self.fail_replica = False
        self.fail_primary = False

    def validate_host_and_compose(
        self,
        *,
        require_rendered: bool = True,
    ) -> None:
        self.events.append(f"validate:{require_rendered}")

    def ensure_connector_absent(self, name: str) -> None:
        assert name == module.REPLICA_SERVICE
        self.events.append(f"absent:{name}")

    def ensure_canary_absent(self) -> None:
        self.events.append("canaries-absent")

    def verify_legacy_container(self, token: module.SecretText) -> None:
        assert token.matches(OLD_TOKEN)
        self.events.append("verify-legacy")

    def start_migration_canary(self, name: str, path: Path) -> None:
        assert path.read_text(encoding="utf-8").strip() == OLD_TOKEN.value
        self.events.append(f"start:{name}")
        self.api.phase = (
            "canary_a"
            if name == module.MIGRATION_CANARY_CONTAINERS[0]
            else "canary_b"
        )

    def verify_migration_canary_running(self, name: str) -> None:
        self.events.append(f"verify:{name}")

    def recreate_service(self, name: str) -> None:
        self.events.append(f"recreate:{name}")
        if name == module.REPLICA_SERVICE:
            if self.fail_replica:
                raise module.RotationError("simulated_replica_failure")
            self.api.phase = "replica"
        else:
            if self.fail_primary:
                raise module.RotationError("simulated_primary_failure")
            self.api.phase = "primary"

    def verify_connector_container(self, name: str) -> None:
        self.events.append(f"verify:{name}")

    def retire_legacy_container(self, token: module.SecretText) -> None:
        assert token.matches(OLD_TOKEN)
        self.events.append("retire-legacy")
        self.api.phase = "legacy_retired"

    def remove_migration_canary(self, name: str) -> None:
        self.events.append(f"remove:{name}")
        if (
            self.api.phase == "canary_b"
            and name == module.MIGRATION_CANARY_CONTAINERS[1]
        ):
            self.api.phase = "canary_a"
        elif (
            self.api.phase == "canary_a"
            and name == module.MIGRATION_CANARY_CONTAINERS[0]
        ):
            self.api.phase = "legacy"
        elif name == module.MIGRATION_CANARY_CONTAINERS[0]:
            self.api.phase = "after_a"
        else:
            self.api.phase = "final"

    def remove_compose_service(self, name: str) -> None:
        self.events.append(f"rollback-remove:{name}")
        self.api.phase = "canary_b"


class FakeProber:
    specs = module.DEFAULT_PROBES

    def __init__(self) -> None:
        self.results = tuple(
            module.ProbeResult(
                spec.url,
                next(iter(spec.expected_statuses)),
                "d" * 64,
            )
            for spec in self.specs
        )
        self.verify_count = 0

    def probe(self) -> tuple[module.ProbeResult, ...]:
        return self.results

    def verify_stable(
        self,
        baseline: tuple[module.ProbeResult, ...],
    ) -> tuple[module.ProbeResult, ...]:
        assert baseline == self.results
        self.verify_count += 1
        return self.results


class FakeTiming:
    def __init__(self) -> None:
        self.events: list[tuple[str, int]] = []

    def wait_for(
        self,
        verifier: Any,
        *,
        timeout_seconds: int,
        failure_code: str,
    ) -> Any:
        self.events.append((f"wait:{failure_code}", timeout_seconds))
        return verifier()

    def dwell(self, verifier: Any) -> None:
        self.events.append(("dwell", module.MANDATORY_DWELL_SECONDS))
        verifier()

    def dwell_for(self, seconds: int, verifier: Any) -> None:
        self.events.append(("dwell_for", seconds))
        verifier()


def engine_fixture(tmp_path: Path) -> tuple[
    module.RotationEngine,
    FakeApi,
    FakeDocker,
    FakeTiming,
    module.ReceiptState,
    Path,
]:
    secret_root = owner_only_directory(tmp_path / "secrets")
    current_token = token_file(secret_root)
    inputs = module.RotationInputs(
        repository_root=ROOT,
        compose_file=ROOT / "docker-compose.public-edge.yml",
        compose_env_file=compose_env_file(secret_root, current_token),
        credentials_file=credentials_file(secret_root),
        token_file=current_token,
        receipt_file=secret_root / "receipt.json",
        tunnel_id=TUNNEL_ID,
        tunnel_name="chummer-run",
    )
    api = FakeApi()
    docker = FakeDocker(api)
    timing = FakeTiming()
    state = module.ReceiptState(run_id="test-run", mode="execute")
    receipt = MemoryReceipt()
    engine = module.RotationEngine(
        inputs=inputs,
        old_token=OLD_TOKEN,
        token_metadata=module.parse_tunnel_token(OLD_TOKEN),
        api=api,
        docker=docker,
        prober=FakeProber(),
        timing=timing,
        receipt=receipt,
        state=state,
        secret_factory=lambda: b"n" * 32,
    )
    return engine, api, docker, timing, state, current_token


def migration_fixture(tmp_path: Path) -> tuple[
    module.LegacyBootstrapEngine,
    FakeMigrationApi,
    FakeMigrationDocker,
    FakeTiming,
    module.ReceiptState,
    Path,
    Path,
    bytes,
]:
    secret_root = owner_only_directory(tmp_path / "secrets")
    current_token = secret_root / "cloudflared.token"
    compose_env = owner_only_file(
        secret_root / "compose.env",
        (
            "UNRELATED_SETTING=preserved\n"
            f"CHUMMER_RUN_CF_TUNNEL_TOKEN={OLD_TOKEN.value}\n"
            "CHUMMER_RUN_TUNNEL_NETWORK=chummer5a_default\n"
        ),
    )
    original = compose_env.read_bytes()
    inputs = module.RotationInputs(
        repository_root=ROOT,
        compose_file=ROOT / "docker-compose.public-edge.yml",
        compose_env_file=compose_env,
        credentials_file=credentials_file(secret_root),
        token_file=current_token,
        receipt_file=secret_root / "receipt.json",
        tunnel_id=TUNNEL_ID,
        tunnel_name="chummer-run",
    )
    migration = module.prepare_legacy_compose_migration(
        compose_env,
        token_file=current_token,
    )
    api = FakeMigrationApi()
    docker = FakeMigrationDocker(api)
    timing = FakeTiming()
    state = module.ReceiptState(run_id="migration-run", mode="execute")
    receipt = MemoryReceipt()
    receipt.add_forbidden(OLD_TOKEN.value, OLD_SECRET)
    engine = module.LegacyBootstrapEngine(
        inputs=inputs,
        migration=migration,
        token_metadata=module.parse_tunnel_token(OLD_TOKEN),
        api=api,
        docker=docker,
        prober=FakeProber(),
        timing=timing,
        receipt=receipt,
        state=state,
    )
    return (
        engine,
        api,
        docker,
        timing,
        state,
        compose_env,
        current_token,
        original,
    )


def test_secret_repr_and_str_are_redacted() -> None:
    assert OLD_TOKEN.value not in repr(OLD_TOKEN)
    assert OLD_TOKEN.value not in str(OLD_TOKEN)
    credentials = module.CloudflareCredentials(
        module.SecretText(EMAIL),
        module.SecretText(GLOBAL_KEY),
    )
    assert GLOBAL_KEY not in repr(credentials)
    assert EMAIL not in repr(credentials)


def test_token_parser_is_exact() -> None:
    metadata = module.parse_tunnel_token(OLD_TOKEN)
    assert metadata.account_id == ACCOUNT_ID
    assert metadata.tunnel_id == TUNNEL_ID
    assert metadata.tunnel_secret.value == OLD_SECRET
    extra = json.dumps(
        {"a": ACCOUNT_ID, "s": OLD_SECRET, "t": TUNNEL_ID, "x": "bad"}
    ).encode()
    with pytest.raises(module.RotationError, match="tunnel_token_invalid"):
        module.parse_tunnel_token(
            module.SecretText(base64.urlsafe_b64encode(extra).decode())
        )


def test_owner_only_reader_rejects_symlink_mode_hardlink_and_wrong_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = owner_only_directory(tmp_path / "safe")
    target = owner_only_file(root / "token", OLD_TOKEN.value)
    symlink = root / "symlink"
    symlink.symlink_to(target)
    with pytest.raises(module.RotationError):
        module.read_owner_only_file(symlink, limit=4096)

    target.chmod(0o640)
    with pytest.raises(module.RotationError, match="wrong_mode"):
        module.read_owner_only_file(target, limit=4096)
    target.chmod(0o600)

    hardlink = root / "hardlink"
    os.link(target, hardlink)
    with pytest.raises(module.RotationError, match="hardlinked"):
        module.read_owner_only_file(target, limit=4096)
    hardlink.unlink()

    actual_euid = os.geteuid()
    monkeypatch.setattr(module.os, "geteuid", lambda: actual_euid + 1)
    with pytest.raises(module.RotationError, match="wrong_owner"):
        module.read_owner_only_file(target, limit=4096)


def test_credentials_parser_selects_pair_from_owner_only_env(
    tmp_path: Path,
) -> None:
    root = owner_only_directory(tmp_path / "safe")
    parsed = module.parse_credentials_file(credentials_file(root))
    assert parsed.email.value == EMAIL
    assert parsed.global_api_key.value == GLOBAL_KEY
    extra = owner_only_file(
        root / "extra.env",
        (
            f"CLOUDFLARE_EMAIL={EMAIL}\n"
            f"CLOUDFLARE_GLOBAL_API_KEY={GLOBAL_KEY}\n"
            "EXTRA=forbidden\n"
        ),
    )
    assert module.parse_credentials_file(extra).global_api_key.value == GLOBAL_KEY
    duplicate = owner_only_file(
        root / "duplicate.env",
        (
            f"CLOUDFLARE_EMAIL={EMAIL}\n"
            f"CLOUDFLARE_EMAIL={EMAIL}\n"
            f"CLOUDFLARE_GLOBAL_API_KEY={GLOBAL_KEY}\n"
        ),
    )
    with pytest.raises(module.RotationError, match="invalid_shape"):
        module.parse_credentials_file(duplicate)


def test_compose_environment_rejects_legacy_token_and_identity_drift(
    tmp_path: Path,
) -> None:
    root = owner_only_directory(tmp_path / "safe")
    current = token_file(root)
    env_path = owner_only_file(
        root / "compose.env",
        (
            f"CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE={current}\n"
            f"CHUMMER_RUN_CF_TUNNEL_TOKEN={OLD_TOKEN.value}\n"
        ),
    )
    with pytest.raises(module.RotationError, match="legacy_tunnel_token"):
        module.parse_compose_environment(
            env_path,
            expected_token_file=current,
            token_stat=current.stat(),
        )
    env_path = owner_only_file(
        root / "compose.env",
        (
            f"CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE={current}\n"
            "CHUMMER_CLOUDFLARED_RUNTIME_UID=99999\n"
        ),
    )
    with pytest.raises(module.RotationError, match="identity_mismatch"):
        module.parse_compose_environment(
            env_path,
            expected_token_file=current,
            token_stat=current.stat(),
        )


def test_exact_live_legacy_state_migrates_through_two_temporary_connectors(
    tmp_path: Path,
) -> None:
    (
        engine,
        api,
        docker,
        timing,
        state,
        compose_env,
        current_token,
        _,
    ) = migration_fixture(tmp_path)

    engine.execute()

    assert api.phase == "final"
    assert state.migration_status == "passed"
    assert state.legacy_container_removed is True
    assert module.read_token_file(current_token).matches(OLD_TOKEN)
    rewritten = compose_env.read_text(encoding="utf-8")
    assert "CHUMMER_RUN_CF_TUNNEL_TOKEN=" not in rewritten
    assert OLD_TOKEN.value not in rewritten
    assert (
        f"CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE={current_token}"
        in rewritten
    )
    assert "UNRELATED_SETTING=preserved" in rewritten
    first_canary = f"start:{module.MIGRATION_CANARY_CONTAINERS[0]}"
    second_canary = f"start:{module.MIGRATION_CANARY_CONTAINERS[1]}"
    replica = f"recreate:{module.REPLICA_SERVICE}"
    primary = f"recreate:{module.PRIMARY_SERVICE}"
    assert docker.events.index(first_canary) < docker.events.index(second_canary)
    assert docker.events.index(second_canary) < docker.events.index(replica)
    assert docker.events.index(replica) < docker.events.index("retire-legacy")
    assert docker.events.index("retire-legacy") < docker.events.index(primary)
    assert [event for event in timing.events if event[0] == "dwell_for"] == [
        ("dwell_for", module.MIGRATION_DWELL_SECONDS),
        ("dwell_for", module.MIGRATION_DWELL_SECONDS),
        ("dwell_for", module.MIGRATION_DWELL_SECONDS),
    ]
    assert all(OLD_TOKEN.value not in event for event in docker.events)


def test_legacy_migration_precommit_failure_restores_exact_raw_state(
    tmp_path: Path,
) -> None:
    (
        engine,
        api,
        docker,
        _,
        state,
        compose_env,
        current_token,
        original,
    ) = migration_fixture(tmp_path)
    docker.fail_replica = True

    with pytest.raises(
        module.RotationError,
        match="simulated_replica_failure",
    ):
        engine.execute()

    assert api.phase == "legacy"
    assert compose_env.read_bytes() == original
    assert not current_token.exists()
    assert state.migration_status == "rolled_back"
    assert state.rollback_status == "passed"
    assert f"rollback-remove:{module.REPLICA_SERVICE}" in docker.events
    assert "retire-legacy" not in docker.events


def test_legacy_takeover_failure_preserves_two_canaries_and_replica(
    tmp_path: Path,
) -> None:
    (
        engine,
        api,
        docker,
        _,
        state,
        compose_env,
        current_token,
        _,
    ) = migration_fixture(tmp_path)
    docker.fail_primary = True

    with pytest.raises(
        module.RotationError,
        match="simulated_primary_failure",
    ):
        engine.execute()

    assert engine.commit_started is True
    assert state.legacy_container_removed is True
    assert api.phase == "legacy_retired"
    assert current_token.exists()
    assert OLD_TOKEN.value not in compose_env.read_text(encoding="utf-8")
    assert not any(
        event.startswith("remove:") for event in docker.events
    )
    assert f"rollback-remove:{module.REPLICA_SERVICE}" not in docker.events


def test_legacy_remote_token_drift_blocks_retirement_and_rolls_back(
    tmp_path: Path,
) -> None:
    (
        engine,
        api,
        docker,
        _,
        state,
        compose_env,
        current_token,
        original,
    ) = migration_fixture(tmp_path)

    class DriftAfterReplicaDwell(FakeTiming):
        def __init__(self) -> None:
            super().__init__()
            self.dwell_count = 0

        def dwell_for(self, seconds: int, verifier: Any) -> None:
            super().dwell_for(seconds, verifier)
            self.dwell_count += 1
            if self.dwell_count == 2:
                remote_reads = iter((OTHER_TOKEN, OLD_TOKEN))
                api.get_token = lambda: next(remote_reads, OLD_TOKEN)

    engine.timing = DriftAfterReplicaDwell()

    with pytest.raises(
        module.RotationError,
        match="migration_remote_token_changed",
    ):
        engine.execute()

    assert "retire-legacy" not in docker.events
    assert compose_env.read_bytes() == original
    assert not current_token.exists()
    assert state.migration_status == "rolled_back"
    assert state.rollback_status == "passed"


def test_receipt_writer_blocks_any_known_secret(tmp_path: Path) -> None:
    root = owner_only_directory(tmp_path / "safe")
    state = module.ReceiptState(run_id="run", mode="audit")
    state.events.append({"name": GLOBAL_KEY})
    writer = module.ReceiptWriter(root / "receipt.json", [GLOBAL_KEY])
    with pytest.raises(module.RotationError, match="secret_leak"):
        writer.write(state)
    assert not (root / "receipt.json").exists()


def test_safe_runner_blocks_secret_in_argv_and_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = module.SafeRunner([GLOBAL_KEY])
    with pytest.raises(module.RotationError, match="secret_leak"):
        runner.run(("example", GLOBAL_KEY))

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=GLOBAL_KEY,
            stderr="",
        ),
    )
    with pytest.raises(module.RotationError, match="output_secret_leak"):
        runner.run(("example",))


def test_docker_runtime_contract_binds_image_health_identity_and_mount(
    tmp_path: Path,
) -> None:
    root = owner_only_directory(tmp_path / "safe")
    current = token_file(root)
    inputs = module.RotationInputs(
        repository_root=ROOT,
        compose_file=ROOT / "docker-compose.public-edge.yml",
        compose_env_file=compose_env_file(root, current),
        credentials_file=credentials_file(root),
        token_file=current,
        receipt_file=root / "receipt.json",
        tunnel_id=TUNNEL_ID,
        tunnel_name="chummer-run",
    )
    image_id = "sha256:" + ("f" * 64)

    class ImageRunner(FakeRunner):
        def run(self, argv: Any, **kwargs: Any) -> Any:
            assert tuple(argv[:3]) == ("docker", "image", "inspect")
            return subprocess.CompletedProcess(argv, 0, image_id + "\n", "")

    client = module.DockerClient(
        runner=ImageRunner(),
        inputs=inputs,
        environment=module.ComposeEnvironment(
            token_file=current,
            runtime_uid=os.geteuid(),
            runtime_gid=os.getegid(),
            network="chummer5a_default",
        ),
        run_id="run",
    )
    payload: dict[str, Any] = {
        "Image": image_id,
        "Config": {
            "Image": module.PINNED_IMAGE,
            "Cmd": [
                "tunnel",
                "run",
                "--token-file",
                module.TOKEN_TARGET,
            ],
            "Env": ["PATH=/usr/bin"],
            "User": f"{os.geteuid()}:{os.getegid()}",
            "Healthcheck": {
                "Test": [
                    "CMD",
                    "cloudflared",
                    "tunnel",
                    "--metrics",
                    "127.0.0.1:2000",
                    "ready",
                ]
            },
            "Labels": {
                "com.docker.compose.service": module.PRIMARY_SERVICE,
                "com.docker.compose.project": module.COMPOSE_PROJECT_NAME,
                "com.docker.compose.project.working_dir": str(root),
                "com.docker.compose.project.config_files": str(
                    inputs.compose_file
                ),
            },
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "RestartPolicy": {"Name": "unless-stopped"},
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
        },
        "State": {"Health": {"Status": "healthy"}},
        "Mounts": [
            {
                "Type": "bind",
                "Source": str(current),
                "Destination": module.TOKEN_TARGET,
                "RW": False,
            }
        ],
        "NetworkSettings": {
            "Networks": {"chummer5a_default": {}}
        },
    }

    client._verify_token_file_container(
        payload,
        expected_source=current,
        expected_service=module.PRIMARY_SERVICE,
    )
    payload["Config"]["Labels"]["com.docker.compose.project"] = "wrong-project"
    with pytest.raises(
        module.RotationError,
        match="ownership_mismatch",
    ):
        client._verify_token_file_container(
            payload,
            expected_source=current,
            expected_service=module.PRIMARY_SERVICE,
        )
    payload["Config"]["Labels"][
        "com.docker.compose.project"
    ] = module.COMPOSE_PROJECT_NAME
    payload["HostConfig"]["CapDrop"] = []
    with pytest.raises(module.RotationError, match="capabilities_invalid"):
        client._verify_token_file_container(
            payload,
            expected_source=current,
            expected_service=module.PRIMARY_SERVICE,
        )
    payload["HostConfig"]["CapDrop"] = ["ALL"]
    payload["Config"].pop("Healthcheck")
    payload["State"] = {"Status": "running"}
    client._verify_token_file_container(
        payload,
        expected_source=current,
        require_compose_healthcheck=False,
    )
    payload["Config"]["Healthcheck"] = {
        "Test": [
            "CMD-SHELL",
            "cloudflared tunnel --metrics 127.0.0.1:2000 ready",
        ]
    }
    payload["State"]["Health"] = {"Status": "unhealthy"}
    with pytest.raises(
        module.RotationError,
        match="canary_healthcheck_forbidden",
    ):
        client._verify_token_file_container(
            payload,
            expected_source=current,
            require_compose_healthcheck=False,
        )


def test_distroless_canary_uses_shell_free_exec_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = owner_only_directory(tmp_path / "safe")
    current = token_file(root)
    inputs = module.RotationInputs(
        repository_root=ROOT,
        compose_file=ROOT / "docker-compose.public-edge.yml",
        compose_env_file=compose_env_file(root, current),
        credentials_file=credentials_file(root),
        token_file=current,
        receipt_file=root / "receipt.json",
        tunnel_id=TUNNEL_ID,
        tunnel_name="chummer-run",
    )

    class RecordingRunner(FakeRunner):
        def __init__(self) -> None:
            super().__init__()
            self.commands: list[tuple[str, ...]] = []

        def run(self, argv: Any, **kwargs: Any) -> Any:
            command = tuple(argv)
            self.commands.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

    runner = RecordingRunner()
    client = module.DockerClient(
        runner=runner,
        inputs=inputs,
        environment=module.ComposeEnvironment(
            token_file=current,
            runtime_uid=os.geteuid(),
            runtime_gid=os.getegid(),
            network="chummer5a_default",
        ),
        run_id="run",
    )
    canary = module.MIGRATION_CANARY_CONTAINERS[0]
    client.start_migration_canary(canary, current)
    start_command = runner.commands[-1]
    assert start_command[:3] == ("docker", "run", "--detach")
    assert not any(value.startswith("--health") for value in start_command)

    monkeypatch.setattr(
        client,
        "_inspect_raw",
        lambda *args, **kwargs: {
            "Config": {
                "Labels": {
                    "run.chummer.cloudflare-migration": "run",
                }
            },
            "State": {"Status": "running"},
        },
    )
    validation_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        client,
        "_verify_token_file_container",
        lambda *args, **kwargs: validation_calls.append(kwargs),
    )
    client.verify_migration_canary_running(canary)

    assert validation_calls == [
        {
            "expected_source": current,
            "require_compose_healthcheck": False,
        }
    ]
    assert runner.commands[-1] == (
        "docker",
        "exec",
        canary,
        *module.CLOUDFLARED_READY_COMMAND,
    )


def test_every_compose_command_uses_stable_project_and_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = owner_only_directory(tmp_path / "safe")
    current = token_file(root)
    inputs = module.RotationInputs(
        repository_root=ROOT,
        compose_file=ROOT / "docker-compose.public-edge.yml",
        compose_env_file=root / ".env",
        credentials_file=root / "credentials",
        token_file=current,
        receipt_file=root / "receipt.json",
        tunnel_id=TUNNEL_ID,
        tunnel_name="chummer-run",
    )

    class RecordingRunner(FakeRunner):
        def __init__(self) -> None:
            super().__init__()
            self.commands: list[tuple[str, ...]] = []

        def run(self, argv: Any, **kwargs: Any) -> Any:
            command = tuple(argv)
            self.commands.append(command)
            if command[:2] == ("docker", "info"):
                return subprocess.CompletedProcess(command, 0, "amd64\n", "")
            if "--format" in command and "json" in command:
                return subprocess.CompletedProcess(command, 0, "{}", "")
            return subprocess.CompletedProcess(command, 0, "", "")

    runner = RecordingRunner()
    client = module.DockerClient(
        runner=runner,
        inputs=inputs,
        environment=module.ComposeEnvironment(
            token_file=current,
            runtime_uid=os.geteuid(),
            runtime_gid=os.getegid(),
            network="chummer5a_default",
        ),
        run_id="run",
    )
    with pytest.raises(
        module.RotationError,
        match="compose_project_contract_mismatch",
    ):
        client.validate_host_and_compose()
    client.recreate_service(module.PRIMARY_SERVICE)

    inspections = iter(
        (
            {
                "Config": {
                    "Labels": {
                        "com.docker.compose.service": module.REPLICA_SERVICE,
                        "com.docker.compose.project": (
                            module.COMPOSE_PROJECT_NAME
                        ),
                        "com.docker.compose.project.working_dir": str(root),
                        "com.docker.compose.project.config_files": str(
                            inputs.compose_file
                        ),
                    }
                }
            },
            None,
        )
    )
    monkeypatch.setattr(
        client,
        "_inspect_raw",
        lambda *args, **kwargs: next(inspections),
    )
    client.remove_compose_service(module.REPLICA_SERVICE)

    compose_commands = [
        command
        for command in runner.commands
        if command[:2] == ("docker", "compose")
    ]
    assert len(compose_commands) == 4
    for command in compose_commands:
        assert command[2:6] == (
            "--project-name",
            module.COMPOSE_PROJECT_NAME,
            "--project-directory",
            str(root),
        )


def test_rotation_lock_is_canonical_across_token_choices_and_nonblocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = owner_only_directory(tmp_path / "safe")
    monkeypatch.setattr(module, "RUNTIME_LOCK_ROOT", root)
    compose_env = root / ".env"
    common = {
        "repository_root": ROOT,
        "compose_file": ROOT / "docker-compose.public-edge.yml",
        "compose_env_file": compose_env,
        "credentials_file": root / "credentials",
        "receipt_file": root / "receipt",
        "tunnel_id": TUNNEL_ID,
        "tunnel_name": "chummer-run",
    }
    first_inputs = module.RotationInputs(
        token_file=root / "first.token",
        **common,
    )
    second_inputs = module.RotationInputs(
        token_file=root / "second.token",
        **common,
    )
    lock_path = first_inputs.lock_file
    assert lock_path == second_inputs.lock_file
    assert lock_path == module.canonical_rotation_lock_path(
        compose_env,
        TUNNEL_ID,
    )
    with module.RotationLock(lock_path, "first"):
        with pytest.raises(module.RotationError, match="already_running"):
            with module.RotationLock(lock_path, "second"):
                pass
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600


def test_cli_rejects_caller_selected_lock_path() -> None:
    with pytest.raises(SystemExit):
        module.build_parser().parse_args(
            [
                "--credentials-file",
                "/credentials",
                "--token-file",
                "/token",
                "--compose-env-file",
                "/compose.env",
                "--receipt",
                "/receipt",
                "--tunnel-id",
                TUNNEL_ID,
                "--lock-file",
                "/alternate.lock",
            ]
        )


def test_cli_rejects_caller_selected_compose_file() -> None:
    with pytest.raises(SystemExit):
        module.build_parser().parse_args(
            [
                "--credentials-file",
                "/credentials",
                "--token-file",
                "/token",
                "--compose-env-file",
                "/compose.env",
                "--receipt",
                "/receipt",
                "--tunnel-id",
                TUNNEL_ID,
                "--compose-file",
                "/alternate.yml",
            ]
        )


def test_cloudflare_client_uses_get_and_patch_only_and_never_leaks_key() -> None:
    calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def transport(
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        calls.append((method, url, headers, body))
        if method == "PATCH":
            result: object = {"token": NEW_TOKEN.value}
        elif url.endswith("/token"):
            result = OLD_TOKEN.value
        elif url.endswith("/configurations"):
            result = {"version": 12, "config": {"ingress": []}}
        elif url.endswith("/connections"):
            result = [
                {
                    "id": OLD_A,
                    "version": "2026.7.0",
                    "conns": [
                        {"is_pending_reconnect": False}
                        for _ in range(4)
                    ],
                },
                {
                    "id": OLD_B,
                    "version": "2026.7.0",
                    "conns": [
                        {"is_pending_reconnect": False}
                        for _ in range(4)
                    ],
                },
            ]
        else:
            result = {
                "id": TUNNEL_ID,
                "name": "chummer-run",
                "status": "healthy",
                "config_src": "cloudflare",
            }
        return 200, json.dumps({"success": True, "result": result}).encode()

    client = module.CloudflareClient(
        account_id=ACCOUNT_ID,
        tunnel_id=TUNNEL_ID,
        credentials=module.CloudflareCredentials(
            module.SecretText(EMAIL),
            module.SecretText(GLOBAL_KEY),
        ),
        transport=transport,
    )
    assert client.get_token().matches(OLD_TOKEN)
    assert len(client.get_snapshot().active_connector_ids) == 2
    assert client.rotate_secret(
        tunnel_name="chummer-run",
        tunnel_secret=module.SecretText(NEW_SECRET),
    ).matches(NEW_TOKEN)
    assert {call[0] for call in calls} == {"GET", "PATCH"}
    assert all(call[0] != "DELETE" for call in calls)
    assert all(GLOBAL_KEY not in call[1] for call in calls)
    assert all(GLOBAL_KEY not in (call[3] or b"").decode() for call in calls)


def test_happy_path_has_three_mandatory_dwells_before_final_cleanup(
    tmp_path: Path,
) -> None:
    engine, api, docker, timing, state, current_token = engine_fixture(
        tmp_path
    )
    engine.execute()

    assert state.status == "passed"
    assert module.read_token_file(current_token).matches(NEW_TOKEN)
    assert api.events == ["patch-new"]
    assert docker.events.index("start-canary") < docker.events.index(
        f"recreate:{module.PRIMARY_SERVICE}"
    )
    assert docker.events.index(
        f"recreate:{module.PRIMARY_SERVICE}"
    ) < docker.events.index(f"recreate:{module.REPLICA_SERVICE}")
    assert docker.events.index("remove-canary") < docker.events.index(
        f"verify:{module.PRIMARY_SERVICE}",
        docker.events.index("remove-canary"),
    )
    assert [event for event in timing.events if event[0] == "dwell"] == [
        ("dwell", 600),
        ("dwell", 600),
        ("dwell", 600),
    ]
    assert state.final_connector_ids == sorted((PRIMARY, REPLICA))
    assert not engine.stage_file.exists()


def test_preflight_rejects_unknown_active_connector(
    tmp_path: Path,
) -> None:
    engine, api, _, _, _, _ = engine_fixture(tmp_path)
    api.get_snapshot = lambda: snapshot(OLD_A, OLD_B, CANARY)

    with pytest.raises(
        module.RotationError,
        match="unexpected_active_connector_topology",
    ):
        engine.audit()


def test_preflight_rejects_unpinned_active_connector_version(
    tmp_path: Path,
) -> None:
    engine, api, _, _, _, _ = engine_fixture(tmp_path)
    api.get_snapshot = lambda: module.ApiSnapshot(
        tunnel_id=TUNNEL_ID,
        tunnel_name="chummer-run",
        status="healthy",
        config_source="cloudflare",
        config_version=12,
        config_sha256="c" * 64,
        connectors=(
            module.Connector(OLD_A, "2025.1.0", 4, 0),
            connector(OLD_B),
        ),
    )

    with pytest.raises(
        module.RotationError,
        match="active_connector_version_mismatch",
    ):
        engine.audit()


def test_remote_token_drift_during_canary_dwell_rolls_back_precommit(
    tmp_path: Path,
) -> None:
    engine, api, docker, _, state, current_token = engine_fixture(tmp_path)

    class RemoteDriftTiming(FakeTiming):
        def dwell(self, verifier: Any) -> None:
            api.current_token = OTHER_TOKEN
            super().dwell(verifier)

    engine.timing = RemoteDriftTiming()

    with pytest.raises(
        module.RotationError,
        match="rotated_remote_token_mismatch",
    ):
        engine.execute()

    assert api.events == ["patch-new", "patch-old"]
    assert state.rollback_status == "passed"
    assert module.read_token_file(current_token).matches(OLD_TOKEN)
    assert not any(
        event.startswith("recreate:") for event in docker.events
    )


def test_final_verification_rejects_unknown_active_connector(
    tmp_path: Path,
) -> None:
    engine, api, docker, _, state, _ = engine_fixture(tmp_path)
    api.final_extra_connector = MIGRATION_B

    with pytest.raises(
        module.RotationError,
        match="unexpected_active_connector_topology",
    ):
        engine.execute()

    assert engine.commit_started is True
    assert state.rotation_commit_started is True
    assert "remove-canary" in docker.events
    assert api.events == ["patch-new"]


def test_accepted_but_timed_out_patch_is_reconciled_and_continues(
    tmp_path: Path,
) -> None:
    engine, api, _, _, state, current_token = engine_fixture(tmp_path)
    api.patch_error_after_apply = module.RotationError(
        "cloudflare_transport_failed"
    )

    engine.execute()

    assert state.status == "passed"
    assert api.events == ["patch-new"]
    assert module.read_token_file(current_token).matches(NEW_TOKEN)
    assert any(
        event["name"] == "cloudflare_patch_response_reconciled"
        for event in state.events
    )


def test_interrupt_after_accepted_patch_rolls_back_before_reraising(
    tmp_path: Path,
) -> None:
    engine, api, docker, _, state, current_token = engine_fixture(tmp_path)
    api.patch_error_after_apply = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        engine.execute()

    assert api.events == ["patch-new", "patch-old"]
    assert state.rollback_status == "passed"
    assert module.read_token_file(current_token).matches(OLD_TOKEN)
    assert not any(
        event.startswith("recreate:") for event in docker.events
    )


def test_filesystem_failure_after_patch_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, api, docker, _, state, current_token = engine_fixture(tmp_path)
    original_write = module.atomic_write_owner_only

    def fail_stage_write(
        path: Path,
        content: bytes,
        *,
        replace: bool,
    ) -> None:
        if path == engine.stage_file:
            raise OSError("simulated")
        original_write(path, content, replace=replace)

    monkeypatch.setattr(module, "atomic_write_owner_only", fail_stage_write)

    with pytest.raises(OSError, match="simulated"):
        engine.execute()

    assert api.events == ["patch-new", "patch-old"]
    assert state.rollback_status == "passed"
    assert module.read_token_file(current_token).matches(OLD_TOKEN)
    assert "start-canary" not in docker.events


def test_interrupt_during_mandatory_dwell_rolls_back(
    tmp_path: Path,
) -> None:
    engine, api, docker, _, state, current_token = engine_fixture(tmp_path)

    class InterruptTiming(FakeTiming):
        def dwell(self, verifier: Any) -> None:
            verifier()
            raise KeyboardInterrupt()

    engine.timing = InterruptTiming()

    with pytest.raises(KeyboardInterrupt):
        engine.execute()

    assert api.events == ["patch-new", "patch-old"]
    assert state.rollback_status == "passed"
    assert module.read_token_file(current_token).matches(OLD_TOKEN)
    assert "remove-canary" in docker.events


def test_canary_join_failure_rolls_back_before_any_incumbent_removal(
    tmp_path: Path,
) -> None:
    engine, api, docker, timing, state, current_token = engine_fixture(
        tmp_path
    )
    docker.fail_canary_join = True

    with pytest.raises(
        module.RotationError,
        match="new_connector_identity_ambiguous",
    ):
        engine.execute()

    assert api.events == ["patch-new", "patch-old"]
    assert state.rollback_status == "passed"
    assert module.read_token_file(current_token).matches(OLD_TOKEN)
    assert not any(
        event.startswith("recreate:") for event in docker.events
    )
    assert docker.events[-1] == "remove-canary"
    assert not engine.stage_file.exists()


def test_post_commit_primary_failure_preserves_canary_and_new_token(
    tmp_path: Path,
) -> None:
    engine, api, docker, timing, state, current_token = engine_fixture(
        tmp_path
    )
    docker.fail_primary_recreate = True

    with pytest.raises(module.RotationError, match="simulated_primary_failure"):
        engine.execute()

    assert api.events == ["patch-new"]
    assert engine.commit_started is True
    assert module.read_token_file(current_token).matches(NEW_TOKEN)
    assert "remove-canary" not in docker.events
    assert f"recreate:{module.REPLICA_SERVICE}" not in docker.events
    assert engine.stage_file.exists()


def test_rollback_failure_is_explicit_and_preserves_canary(
    tmp_path: Path,
) -> None:
    engine, api, docker, timing, state, current_token = engine_fixture(
        tmp_path
    )
    docker.fail_canary_join = True
    api.fail_rollback = True

    with pytest.raises(module.RotationError, match="rollback_failed"):
        engine.execute()

    assert state.rollback_status == "failed"
    assert "remove-canary" not in docker.events
    assert module.read_token_file(current_token).matches(OLD_TOKEN)
    assert engine.stage_file.exists()


def test_execute_requires_exact_confirmation_without_touching_files(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = module.run(
        [
            "--execute",
            "--confirm",
            "wrong",
            "--credentials-file",
            "/not/read",
            "--token-file",
            "/not/read",
            "--compose-env-file",
            "/not/read",
            "--receipt",
            "/not/write",
            "--tunnel-id",
            TUNNEL_ID,
        ]
    )
    assert result == 2
    captured = capsys.readouterr()
    assert module.CONFIRMATION in captured.err
    assert GLOBAL_KEY not in captured.err


def test_execute_requires_script_in_canonical_live_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    alternate_root = owner_only_directory(tmp_path / "alternate")
    result = module.run(
        [
            "--execute",
            "--bootstrap-legacy",
            "--confirm",
            module.CONFIRMATION,
            "--credentials-file",
            str(alternate_root / "credentials"),
            "--token-file",
            str(alternate_root / "token"),
            "--compose-env-file",
            str(alternate_root / ".env"),
            "--receipt",
            str(alternate_root / "receipt"),
            "--tunnel-id",
            TUNNEL_ID,
        ]
    )

    assert result == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["failureCode"] == "execute_requires_canonical_repository"
    assert payload["secretsExposed"] is False
    assert not (alternate_root / "receipt").exists()


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_code"),
    [
        (KeyboardInterrupt(), 130, "operator_interrupt"),
        (OSError("simulated"), 1, "unexpected_local_failure"),
    ],
)
def test_top_level_non_rotation_failures_keep_sanitized_json(
    failure: BaseException,
    expected_status: int,
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_validation(inputs: module.RotationInputs) -> Any:
        raise failure

    monkeypatch.setattr(module, "_validate_inputs", fail_validation)
    result = module.run(
        [
            "--credentials-file",
            "/not/read",
            "--token-file",
            "/not/read",
            "--compose-env-file",
            "/not/read",
            "--receipt",
            "/not/write",
            "--tunnel-id",
            TUNNEL_ID,
        ]
    )
    assert result == expected_status
    payload = json.loads(capsys.readouterr().err)
    assert payload["failureCode"] == expected_code
    assert payload["secretsExposed"] is False


def test_rotation_preflight_failure_after_bootstrap_is_action_required() -> None:
    state = module.ReceiptState(run_id="run", mode="execute")
    state.migration_status = "passed"
    state.migration_commit_started = True
    state.legacy_container_removed = True
    state.phase = "preflight"

    assert module.classify_failure_status(state) == "action_required"


def test_cli_has_no_dwell_bypass() -> None:
    with pytest.raises(SystemExit):
        module.build_parser().parse_args(
            [
                "--credentials-file",
                "/x",
                "--token-file",
                "/y",
                "--compose-env-file",
                "/z",
                "--receipt",
                "/r",
                "--tunnel-id",
                TUNNEL_ID,
                "--dwell-seconds",
                "0",
            ]
        )


def test_public_prober_ignores_ambient_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct_body = b"direct-public-proof"
    proxy_hits: list[str] = []

    class DirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(direct_body)

        def log_message(self, *args: object) -> None:
            return

    class ProxyHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            proxy_hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"spoofed-public-proof")

        def log_message(self, *args: object) -> None:
            return

    direct_server = ThreadingHTTPServer(("127.0.0.1", 0), DirectHandler)
    proxy_server = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
    direct_thread = threading.Thread(
        target=direct_server.serve_forever,
        daemon=True,
    )
    proxy_thread = threading.Thread(
        target=proxy_server.serve_forever,
        daemon=True,
    )
    direct_thread.start()
    proxy_thread.start()
    proxy_url = f"http://127.0.0.1:{proxy_server.server_port}"
    for name in (
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        monkeypatch.setenv(name, proxy_url)
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    real_getaddrinfo = socket.getaddrinfo

    def direct_test_dns(
        host: str,
        *args: object,
        **kwargs: object,
    ) -> Any:
        if host == "public-proof.invalid":
            host = "127.0.0.1"
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", direct_test_dns)
    try:
        spec = module.ProbeSpec(
            url=(
                "http://public-proof.invalid:"
                f"{direct_server.server_port}/health"
            ),
            expected_statuses=(200,),
            stable_body=True,
        )
        result = module.PublicProber((spec,)).probe()
    finally:
        direct_server.shutdown()
        proxy_server.shutdown()
        direct_server.server_close()
        proxy_server.server_close()
        direct_thread.join(timeout=5)
        proxy_thread.join(timeout=5)

    assert proxy_hits == []
    assert result[0].body_sha256 == hashlib.sha256(direct_body).hexdigest()


def test_cloudflare_transport_rejects_redirect_without_forwarding_headers() -> None:
    sink_headers: list[dict[str, str]] = []

    class SinkHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            sink_headers.append(dict(self.headers.items()))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            return

    sink_server = ThreadingHTTPServer(("127.0.0.1", 0), SinkHandler)
    sink_thread = threading.Thread(
        target=sink_server.serve_forever,
        daemon=True,
    )
    sink_thread.start()
    sink_url = f"http://127.0.0.1:{sink_server.server_port}/sink"

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", sink_url)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            return

    redirect_server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirect_thread = threading.Thread(
        target=redirect_server.serve_forever,
        daemon=True,
    )
    redirect_thread.start()
    try:
        with pytest.raises(
            module.RotationError,
            match="cloudflare_redirect_forbidden",
        ):
            module.urllib_transport(
                "GET",
                f"http://127.0.0.1:{redirect_server.server_port}/source",
                {
                    "X-Auth-Key": GLOBAL_KEY,
                    "X-Auth-Email": EMAIL,
                },
                None,
            )
    finally:
        redirect_server.shutdown()
        sink_server.shutdown()
        redirect_server.server_close()
        sink_server.server_close()
        redirect_thread.join(timeout=5)
        sink_thread.join(timeout=5)

    assert sink_headers == []


def test_source_has_no_connection_delete_api_or_secret_argv_path() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert 'method not in {"GET", "PATCH"}' in source
    assert '"DELETE"' not in source
    assert "/connections" in source
    assert "--token-file" in source
    assert '"--token",' not in source
    assert 'value.partition("=")[0].upper()' in source
