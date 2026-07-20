from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "scripts" / "run-mac-release-bootstrap.sh"
BOOTSTRAP = (
    REPO_ROOT
    / "Chummer.Run.Api"
    / "wwwroot"
    / "artifacts"
    / "mac-codex-release-pipeline"
    / "bootstrap.sh"
)
RUNBOOK = (
    REPO_ROOT
    / "Chummer.Run.Api"
    / "wwwroot"
    / "artifacts"
    / "mac-codex-release-pipeline"
    / "readme.md"
)
EXPECTED_COMMIT_SETTINGS = (
    "CHUMMER_UI_EXPECTED_COMMIT",
    "CHUMMER_CORE_EXPECTED_COMMIT",
    "CHUMMER_HUB_EXPECTED_COMMIT",
    "CHUMMER_UI_KIT_EXPECTED_COMMIT",
    "CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT",
    "CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT",
    "CHUMMER_LEGACY_EXPECTED_COMMIT",
)


def test_release_generation_id_is_safe_and_operator_override_is_exact() -> None:
    generated = run_sourced('resolve_release_generation_id "run-20260720 nightly" ""')
    exact = run_sourced(
        'resolve_release_generation_id "ignored" "gen-reviewed-abcdef0123456789"'
    )
    unsafe = run_sourced('resolve_release_generation_id "ignored" "../escape"')

    assert generated.returncode == 0, generated.stderr
    assert re.fullmatch(
        r"gen-run-20260720-nightly-[0-9a-f]{16}", generated.stdout.strip()
    )
    assert exact.returncode == 0, exact.stderr
    assert exact.stdout.strip() == "gen-reviewed-abcdef0123456789"
    assert unsafe.returncode != 0


def test_live_convergence_origin_is_derived_from_canonical_https_manifest() -> None:
    valid = run_sourced(
        'resolve_https_release_origin "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json"'
    )
    unsafe = run_sourced(
        'resolve_https_release_origin "https://operator:secret@chummer.run/downloads/RELEASE_CHANNEL.generated.json"'
    )

    assert valid.returncode == 0, valid.stderr
    assert valid.stdout.strip() == "https://chummer.run"
    assert unsafe.returncode != 0


def test_hosted_bootstrap_http_publication_is_session_only() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "https://chummer.run/api/internal/releases/upload-sessions" in bootstrap
    assert "CHUMMER_RELEASE_UPLOAD_URL is retired" in bootstrap
    assert "direct release upload fallback is permanently disabled" in bootstrap
    assert "upload_release_bundle_direct" not in bootstrap
    assert "https://chummer.run/api/internal/releases/bundles" not in bootstrap
    assert "resolved_authority != base_authority" in bootstrap
    assert "upload session response endpoints do not match the created session" in bootstrap
    assert "allowed_scalars = (" in bootstrap
    assert 'summary["suppressedFieldCount"]' in bootstrap
    assert "validate_release_response_probe_url" in bootstrap
    assert "candidate_authority != canonical_authority" in bootstrap
    assert "release upload response contained an unsafe direct-file URL" in bootstrap
    assert '--max-filesize "$max_response_bytes"' in bootstrap
    assert '"$complete_url" \\\n      --no-retry' in bootstrap
    assert "https://chummer.run/api/internal/releases/upload-sessions" in runbook
    assert "https://chummer.run/api/internal/releases/bundles" not in runbook


def test_release_response_probe_url_validator_matches_real_completion_routes() -> None:
    canonical_url = "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json"
    accepted = (
        ("https://chummer.run/downloads/install/avalonia-osx-arm64-installer", "install"),
        (
            "https://chummer.run/downloads/g/run-20260715-140426/install/avalonia-osx-arm64-installer",
            "install",
        ),
        ("https://chummer.run/downloads/files/chummer-avalonia-osx-arm64-installer.dmg", "direct"),
        (
            "https://chummer.run/downloads/g/run-20260715-140426/files/"
            "chummer-avalonia-osx-arm64-installer.dmg",
            "direct",
        ),
        (
            "https://chummer.run/downloads/g/run-20260715-140426/install/avalonia-osx-arm64-installer",
            "direct",
        ),
        (
            "https://chummer.run/downloads/g/run-20260715-140426/install/"
            "avalonia-osx-arm64-installer/payload",
            "direct",
        ),
        (
            "https://chummer.run/downloads/g/run-20260715-140426/install/"
            "avalonia-osx-arm64-installer/metadata",
            "direct",
        ),
    )

    for route_url, role in accepted:
        result = run_sourced(
            'validate_release_response_probe_url "$2" "$3" "$4"',
            route_url,
            canonical_url,
            role,
        )
        assert result.returncode == 0, (route_url, result.stderr)
        assert result.stdout.strip() == route_url

    rejected = (
        ("https://attacker.invalid/downloads/install/artifact", "install"),
        ("https://chummer.run/downloads/install/artifact?claimCode=secret", "install"),
        (
            "https://chummer.run/downloads/g/run-20260715-140426/install/artifact/primary",
            "direct",
        ),
        ("https://chummer.run/downloads/g/run-20260715-140426/files/%2e%2e", "direct"),
        ("https://chummer.run/account/access", "direct"),
    )
    for route_url, role in rejected:
        result = run_sourced(
            'validate_release_response_probe_url "$2" "$3" "$4"',
            route_url,
            canonical_url,
            role,
        )
        assert result.returncode != 0, route_url


def clean_release_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in (
        "CHUMMER_MAC_RELEASE_STAGE_ONLY",
        "CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR",
        "CHUMMER_RELEASE_UPLOAD_TOKEN",
        "CHUMMER_RELEASE_UPLOAD_TOKEN_FILE",
        "CHUMMER_RELEASE_UPLOAD_TOKEN_PATH",
        "CHUMMER_RELEASE_UPLOAD_TICKET",
        "CHUMMER_RELEASE_UPLOAD_TICKET_FILE",
        "CHUMMER_RELEASE_UPLOAD_TICKET_PATH",
        "FLEET_INTERNAL_API_TOKEN",
        "CHUMMER_RELEASE_PUBLISH_MODE",
        "CHUMMER_RELEASE_UPLOAD_URL",
        "CHUMMER_RELEASE_UPLOAD_SESSIONS_URL",
        "CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK",
        "CHUMMER_RELEASE_UPLOAD_MAX_ATTEMPTS",
        "CHUMMER_RELEASE_UPLOAD_RETRY_SLEEP_SECONDS",
        "CHUMMER_RELEASE_UPLOAD_DIRECT_LIMIT_BYTES",
        "CHUMMER_RELEASE_UPLOAD_CHUNK_BYTES",
        "CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE",
        "CHUMMER_RELEASE_PRINT_SIGNED_INSTALL_CLAIMS",
        "CHUMMER_RELEASE_VERIFY_REQUIRE_COMPATIBILITY_PROJECTION",
        "CHUMMER_RELEASE_SKIP_STRICT_MANIFEST_VERIFY",
        "CHUMMER_RELEASE_EXACT_INCOMING_TUPLES",
        "CHUMMER_RELEASE_SSH_TARGET",
        "CHUMMER_REMOTE_STAGING_DIR",
        "CHUMMER_REMOTE_UI_REPO_DIR",
        "CHUMMER_PORTAL_DOWNLOADS_DEPLOY_DIR",
        "CHUMMER_PORTAL_DOWNLOADS_S3_URI",
        "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL",
        "CHUMMER_APP_SIGN_IDENTITY",
        "CHUMMER_NOTARY_PROFILE",
        "CHUMMER_BOOTSTRAP_FORCE_LOCAL",
        "CHUMMER_HUB_REF",
        *EXPECTED_COMMIT_SETTINGS,
        "CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS",
        "CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL",
        "CHUMMER_HUB_LOCAL_RELEASE_PROOF_EXPECTED_SHA256",
        "CHUMMER_UI_LOCALIZATION_RELEASE_GATE_URL",
        "CHUMMER_UI_LOCALIZATION_RELEASE_GATE_EXPECTED_SHA256",
        "CHUMMER_RELEASE_PYTHON",
        "CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS",
        "CHUMMER_HUB_RELEASE_CHANNEL_PATH",
        "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256",
        "CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY",
        "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT",
        "CHUMMER_FLEET_QUEUE_STAGING_PATH",
        "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256",
        "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY",
        "CHUMMER_DESIGN_QUEUE_STAGING_PATH",
        "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256",
        "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY",
        "CHUMMER_HUB_LOCAL_PROOF_MUTATION_LOCK_PATH",
        "CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_ROOT",
        "CHUMMER_PUBLIC_PROJECTION_WINDOWS_OUTPUT",
    ):
        environment.pop(name, None)
    return environment


def reviewed_pin_environment() -> dict[str, str]:
    environment = clean_release_environment()
    environment.update(
        {
            setting: f"{index:040x}"
            for index, setting in enumerate(EXPECTED_COMMIT_SETTINGS, start=1)
        }
    )
    return environment


def hub_projection_authority_environment(tmp_path: Path) -> dict[str, str]:
    environment = clean_release_environment()
    environment.update(
        {
            "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT": "1" * 40,
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT": "2" * 40,
        }
    )
    handoffs = (
        (
            "CHUMMER_HUB_RELEASE_CHANNEL_PATH",
            "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256",
            "CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY",
            "registry://release/run-test",
        ),
        (
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH",
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256",
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY",
            "fleet://readiness/run-test",
        ),
        (
            "CHUMMER_FLEET_QUEUE_STAGING_PATH",
            "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256",
            "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY",
            "fleet://queue/run-test",
        ),
        (
            "CHUMMER_DESIGN_QUEUE_STAGING_PATH",
            "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256",
            "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY",
            "repo://design/run-test/queue",
        ),
        (
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH",
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256",
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY",
            "repo://design/run-test/registry",
        ),
    )
    for index, (path_name, digest_name, authority_name, authority) in enumerate(handoffs):
        path = tmp_path / f"authority-{index}.json"
        payload = (json.dumps({"authority": index}, sort_keys=True) + "\n").encode("utf-8")
        path.write_bytes(payload)
        environment[path_name] = str(path)
        environment[digest_name] = hashlib.sha256(payload).hexdigest()
        environment[authority_name] = authority
    return environment


def make_wrapper_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "fixture"
    wrapper = root / "scripts" / WRAPPER.name
    bootstrap = (
        root
        / "Chummer.Run.Api"
        / "wwwroot"
        / "artifacts"
        / "mac-codex-release-pipeline"
        / "bootstrap.sh"
    )
    capture = tmp_path / "capture.txt"
    wrapper.parent.mkdir(parents=True)
    bootstrap.parent.mkdir(parents=True)
    wrapper.write_bytes(WRAPPER.read_bytes())
    bootstrap.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        "printf 'stage=%s\\noutput=%s\\ntoken=%s\\nhub_ref=%s\\nhub_expected_commit=%s\\n' "
        '"${CHUMMER_MAC_RELEASE_STAGE_ONLY:-}" '
        '"${CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR:-}" '
        '"${CHUMMER_RELEASE_UPLOAD_TOKEN:-}" '
        '"${CHUMMER_HUB_REF:-}" '
        '"${CHUMMER_HUB_EXPECTED_COMMIT:-}" >"$CAPTURE_PATH"\n'
        "printf 'arg=%s\\n' \"$@\" >>\"$CAPTURE_PATH\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    bootstrap.chmod(0o755)
    return wrapper, bootstrap, capture


def test_wrapper_stage_only_uses_local_bootstrap_without_auth_or_download(tmp_path: Path) -> None:
    wrapper, _bootstrap, capture = make_wrapper_fixture(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl_marker = tmp_path / "curl-was-called"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        '#!/usr/bin/env bash\nprintf called >"$CURL_MARKER"\nexit 97\n',
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    output = tmp_path / "candidate"
    environment = clean_release_environment()
    environment.update(
        {
            "CAPTURE_PATH": str(capture),
            "CURL_MARKER": str(curl_marker),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "CHUMMER_HUB_REF": "refs/heads/reviewed-mac-release",
            "CHUMMER_HUB_EXPECTED_COMMIT": "1774cc1030a25b3889ff2a9bdaf0671ade42bd73",
        }
    )

    result = subprocess.run(
        [str(wrapper), "--stage-only", "--stage-output-dir", str(output)],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    captured = capture.read_text(encoding="utf-8")
    assert "stage=1" in captured
    assert f"output={output}" in captured
    assert "token=" in captured
    assert "hub_ref=refs/heads/reviewed-mac-release" in captured
    assert "hub_expected_commit=1774cc1030a25b3889ff2a9bdaf0671ade42bd73" in captured
    assert "arg=--stage-only" in captured
    assert not curl_marker.exists()


def test_wrapper_keeps_normal_local_authenticated_mode_and_rejects_stage_conflicts(tmp_path: Path) -> None:
    wrapper, _bootstrap, capture = make_wrapper_fixture(tmp_path)
    environment = clean_release_environment()
    environment.update(
        {
            "CAPTURE_PATH": str(capture),
            "CHUMMER_BOOTSTRAP_FORCE_LOCAL": "1",
            "CHUMMER_RELEASE_UPLOAD_TOKEN": "normal-mode-token",
        }
    )
    normal = subprocess.run(
        [str(wrapper), "--normal-mode-argument"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert normal.returncode == 0, normal.stderr
    captured = capture.read_text(encoding="utf-8")
    assert "stage=" in captured
    assert "token=normal-mode-token" in captured
    assert "arg=--normal-mode-argument" in captured

    capture.unlink()
    rejected = subprocess.run(
        [str(wrapper), "--stage-only", "--stage-output-dir", str(tmp_path / "candidate")],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert rejected.returncode == 1
    assert "stage-only mode rejects CHUMMER_RELEASE_UPLOAD_TOKEN" in rejected.stderr
    assert not capture.exists()


def test_wrapper_never_places_release_auth_in_url_or_child_arguments(tmp_path: Path) -> None:
    wrapper, _bootstrap, capture = make_wrapper_fixture(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl_marker = tmp_path / "curl-was-called"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text('#!/usr/bin/env bash\nprintf called >"$CURL_MARKER"\nexit 97\n', encoding="utf-8")
    fake_curl.chmod(0o755)
    synthetic = "synthetic-token-with-query-characters?ticket=never"
    environment = clean_release_environment()
    environment.update(
        {
            "CAPTURE_PATH": str(capture),
            "CURL_MARKER": str(curl_marker),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "CHUMMER_RELEASE_UPLOAD_TOKEN": synthetic,
        }
    )

    result = subprocess.run(
        [str(wrapper), "--normal-mode-argument"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert not curl_marker.exists()
    captured = capture.read_text(encoding="utf-8")
    assert f"token={synthetic}" in captured
    assert "arg=--normal-mode-argument" in captured
    assert f"arg={synthetic}" not in captured
    assert synthetic not in result.stdout
    assert synthetic not in result.stderr

    source = WRAPPER.read_text(encoding="utf-8")
    assert "?apiToken=" not in source
    assert "?ticket=" not in source
    assert "url_encode" not in source
    assert "curl -fsSL" not in source


def test_wrapper_disables_inherited_xtrace_before_secret_capture(tmp_path: Path) -> None:
    wrapper, _bootstrap, capture = make_wrapper_fixture(tmp_path)
    synthetic = "wrapper-xtrace-must-not-print-this-secret"
    environment = clean_release_environment()
    environment.update(
        {
            "CAPTURE_PATH": str(capture),
            "CHUMMER_RELEASE_UPLOAD_TOKEN": synthetic,
        }
    )

    result = subprocess.run(
        ["bash", "-x", str(wrapper), "--normal-mode-argument"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert f"token={synthetic}" in capture.read_text(encoding="utf-8")
    assert synthetic not in result.stdout
    assert synthetic not in result.stderr


def test_wrapper_accepts_only_owner_mode_0600_non_symlink_auth_files(tmp_path: Path) -> None:
    wrapper, _bootstrap, capture = make_wrapper_fixture(tmp_path)
    secret = "synthetic-owner-only-token"
    token_file = tmp_path / "token.txt"
    token_file.write_text(secret + "\n", encoding="utf-8")

    def invoke(path: Path) -> subprocess.CompletedProcess[str]:
        environment = clean_release_environment()
        environment.update(
            {
                "CAPTURE_PATH": str(capture),
                "CHUMMER_RELEASE_UPLOAD_TOKEN_FILE": str(path),
            }
        )
        return subprocess.run(
            [str(wrapper)],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

    token_file.chmod(0o644)
    rejected_mode = invoke(token_file)
    assert rejected_mode.returncode != 0
    assert not capture.exists()
    assert secret not in rejected_mode.stdout
    assert secret not in rejected_mode.stderr

    token_file.chmod(0o600)
    token_link = tmp_path / "token-link.txt"
    token_link.symlink_to(token_file)
    rejected_link = invoke(token_link)
    assert rejected_link.returncode != 0
    assert not capture.exists()
    assert secret not in rejected_link.stdout
    assert secret not in rejected_link.stderr

    accepted = invoke(token_file)
    assert accepted.returncode == 0, accepted.stderr
    assert f"token={secret}" in capture.read_text(encoding="utf-8")


def run_sourced(command: str, *arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "$1"; {command}', "stage-only-test", str(BOOTSTRAP), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=env or clean_release_environment(),
    )


def make_remote_proof_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    proof = tmp_path / "remote-proof.json"
    proof.write_text(
        json.dumps({"contract_name": "chummer6-hub.local_release_proof"}) + "\n",
        encoding="utf-8",
    )
    marker = tmp_path / "curl-called"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        "output=\n"
        "while (( $# > 0 )); do\n"
        "  case \"$1\" in\n"
        "    -o) output=\"$2\"; shift 2 ;;\n"
        "    *) shift ;;\n"
        "  esac\n"
        "done\n"
        "test -n \"$output\"\n"
        "printf called >\"$REMOTE_CURL_MARKER\"\n"
        "cp \"$REMOTE_PROOF_SOURCE\" \"$output\"\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    return proof, marker, fake_bin


def test_bootstrap_preserves_reviewed_hub_ref_and_exact_commit_pin() -> None:
    expected_commit = "1774cc1030a25b3889ff2a9bdaf0671ade42bd73"
    environment = clean_release_environment()
    environment.update(
        {
            "CHUMMER_HUB_REF": "refs/heads/reviewed-mac-release",
            "CHUMMER_HUB_EXPECTED_COMMIT": expected_commit,
        }
    )

    explicit = run_sourced(
        'printf "%s|%s\\n" "$CHUMMER_HUB_REF" "$CHUMMER_HUB_EXPECTED_COMMIT"',
        env=environment,
    )
    defaulted = run_sourced(
        'printf "%s|%s\\n" "$CHUMMER_HUB_REF" "${CHUMMER_HUB_EXPECTED_COMMIT:-}"'
    )

    assert explicit.returncode == 0, explicit.stderr
    assert explicit.stdout == f"refs/heads/reviewed-mac-release|{expected_commit}\n"
    assert defaulted.returncode == 0, defaulted.stderr
    assert defaulted.stdout == "main|\n"


def test_bootstrap_requires_all_seven_reviewed_commit_pins_in_every_mode() -> None:
    for missing_setting in EXPECTED_COMMIT_SETTINGS:
        environment = reviewed_pin_environment()
        environment.pop(missing_setting)

        normal = run_sourced("require_all_reviewed_commit_pins", env=environment)
        stage_only = run_sourced(
            "MAC_RELEASE_STAGE_ONLY=1; require_all_reviewed_commit_pins",
            env=environment,
        )

        for result in (normal, stage_only):
            assert result.returncode == 1
            assert missing_setting in result.stderr
            assert "reviewed full 40-character hexadecimal commit SHA" in result.stderr


def test_bootstrap_rejects_malformed_commit_pins_and_normalizes_uppercase() -> None:
    for malformed in ("", "a" * 39, "g" * 40, "a" * 41):
        environment = reviewed_pin_environment()
        environment["CHUMMER_UI_EXPECTED_COMMIT"] = malformed

        rejected = run_sourced("require_all_reviewed_commit_pins", env=environment)

        assert rejected.returncode == 1
        assert "CHUMMER_UI_EXPECTED_COMMIT" in rejected.stderr

    environment = reviewed_pin_environment()
    environment["CHUMMER_UI_EXPECTED_COMMIT"] = "ABCDEF" * 6 + "ABCD"
    accepted = run_sourced(
        'require_all_reviewed_commit_pins; printf "%s\\n" "$CHUMMER_UI_EXPECTED_COMMIT"',
        env=environment,
    )

    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout == ("abcdef" * 6 + "abcd" + "\n")


def test_commit_pin_preflight_runs_before_stage_output_or_repo_clone() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    main_index = bootstrap.index("main() {")
    parse_index = bootstrap.index('parse_mac_release_stage_only_args "$@"', main_index)
    pin_gate_index = bootstrap.index("require_all_reviewed_commit_pins", parse_index)
    stage_output_index = bootstrap.index("local stage_output_path", pin_gate_index)
    work_root_index = bootstrap.index("local work_root=", stage_output_index)
    first_clone_index = bootstrap.index("clone_or_update", work_root_index)

    assert parse_index < pin_gate_index < stage_output_index < work_root_index < first_clone_index


def test_release_upload_curl_config_is_streamed_without_persistent_file(tmp_path: Path) -> None:
    config_path = tmp_path / "release-upload.curl"
    stream_marker = tmp_path / "stream-marker"
    environment = clean_release_environment()
    environment.update(
        {
            "CHUMMER_RELEASE_UPLOAD_TOKEN": "synthetic-test-token-not-a-real-credential",
            "CREDENTIAL_CONFIG_PATH": str(config_path),
            "STREAM_MARKER": str(stream_marker),
        }
    )
    result = run_sourced(
        r'''
release_upload_auth_value="$CHUMMER_RELEASE_UPLOAD_TOKEN"
export -n release_upload_auth_value
unset CHUMMER_RELEASE_UPLOAD_TOKEN
write_release_upload_curl_config "$release_upload_auth_value" |
  python3 -c 'import os, pathlib, sys; data = sys.stdin.read(); assert data.startswith("header = \"Authorization: Bearer "); assert data.endswith("\"\n"); pathlib.Path(os.environ["STREAM_MARKER"]).write_text("streamed", encoding="utf-8")'
exit 73
''',
        env=environment,
    )

    assert result.returncode == 73
    assert not config_path.exists()
    assert stream_marker.read_text(encoding="utf-8") == "streamed"
    assert "synthetic-test-token" not in result.stdout
    assert "synthetic-test-token" not in result.stderr


def test_hub_http_publisher_also_streams_auth_config_without_a_temp_file() -> None:
    publisher = (REPO_ROOT / "scripts" / "publish-download-bundle-http.sh").read_text(
        encoding="utf-8"
    )

    assert 'write_auth_curl_config "$UPLOAD_AUTH_VALUE" \\' in publisher
    assert '| curl -q --config - "$@"' in publisher
    assert "release_upload_curl_config=\"$(mktemp" not in publisher
    assert "Authorization: Bearer" in publisher


def test_release_python_selection_requires_311_and_honors_reviewed_interpreter() -> None:
    environment = clean_release_environment()
    environment["CHUMMER_RELEASE_PYTHON"] = sys.executable
    accepted = run_sourced("resolve_release_python", env=environment)

    assert accepted.returncode == 0, accepted.stderr
    assert Path(accepted.stdout.strip()).resolve() == Path(sys.executable).resolve()

    environment["CHUMMER_RELEASE_PYTHON"] = "/bin/false"
    rejected = run_sourced("resolve_release_python", env=environment)
    assert rejected.returncode != 0

    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    generator_start = bootstrap.index("generate_hub_local_release_proof() {")
    generator_end = bootstrap.index("\ngenerate_validated_hub_local_release_proof() {", generator_start)
    generator = bootstrap[generator_start:generator_end]
    assert '"$python_bin" "$generator_path"' in generator
    assert "CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS=1" in generator
    assert ">/dev/null 2>&1" not in generator


def test_hub_generator_failure_keeps_only_bounded_sanitized_diagnostics(tmp_path: Path) -> None:
    hub_alias = tmp_path / "hub-alias"
    generator = hub_alias / "scripts" / "materialize_hub_local_release_proof.py"
    generator.parent.mkdir(parents=True)
    generator.write_text(
        "import sys\n"
        "print('Authorization: Bearer leaked-ticket', file=sys.stderr)\n"
        "print('token=plain-secret', file=sys.stderr)\n"
        "print('eyJ1bmxhYmVsZWQ.abcdefghijklmnop.qrstuvwxyz12345', file=sys.stderr)\n"
        "print('/Users/operator/work/proof.json failed', file=sys.stderr)\n"
        "raise SystemExit(9)\n",
        encoding="utf-8",
    )
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    environment = hub_projection_authority_environment(tmp_path)
    environment.update(
        {
            "CHUMMER_RELEASE_PYTHON": sys.executable,
            "TMPDIR": str(temp_root),
        }
    )
    output = tmp_path / "proof.json"

    result = run_sourced(
        'trap cleanup_bootstrap_tmp_paths EXIT; '
        'generate_hub_local_release_proof "$2" "$3" "$4"',
        str(hub_alias),
        str(tmp_path / "hub-repo"),
        str(output),
        env=environment,
    )

    assert result.returncode != 0
    assert "leaked-ticket" not in result.stdout + result.stderr
    assert "plain-secret" not in result.stdout + result.stderr
    assert "eyJ1bmxhYmVsZWQ" not in result.stdout + result.stderr
    assert "/Users/operator" not in result.stdout + result.stderr
    assert "<redacted>" in result.stderr
    assert "<local-path>" in result.stderr
    assert list(temp_root.iterdir()) == []


def test_hub_generator_recovery_uses_python_312_and_all_immutable_handoffs(tmp_path: Path) -> None:
    hub_alias = tmp_path / "hub-alias"
    generator = hub_alias / "scripts" / "materialize_hub_local_release_proof.py"
    generator.parent.mkdir(parents=True)
    required_names = (
        "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT",
        "CHUMMER_HUB_RELEASE_CHANNEL_PATH",
        "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256",
        "CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY",
        "CHUMMER_FLEET_QUEUE_STAGING_PATH",
        "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256",
        "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY",
        "CHUMMER_DESIGN_QUEUE_STAGING_PATH",
        "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256",
        "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY",
    )
    generator.write_text(
        "import json, os, pathlib, sys\n"
        f"required = {required_names!r}\n"
        "assert all(os.environ.get(name) for name in required)\n"
        "assert os.environ.get('CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS') == '1'\n"
        "payload = {\n"
        "  'status': 'pass',\n"
        "  'journeysPassed': [\n"
        "    'install_claim_restore_continue', 'build_explain_publish',\n"
        "    'campaign_session_recover_recap', 'report_cluster_release_notify',\n"
        "    'organize_community_and_close_loop'],\n"
        "  'proofRoutes': [\n"
        "    '/downloads/install/avalonia-linux-x64-installer', '/home/access',\n"
        "    '/home/work', '/account/access', '/account/work', '/account/support',\n"
        "    '/contact', '/downloads', '/downloads/install/avalonia-osx-arm64-installer',\n"
        "    '/downloads/install/avalonia-win-x64-installer']}\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps(payload) + '\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    selection_marker = tmp_path / "python-312-selected"
    fake_python3 = fake_bin / "python3"
    fake_python312 = fake_bin / "python3.12"
    fake_python3.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"${1:-}\" == '-c' ]]; then exit 1; fi\n"
        "exec \"$REAL_PYTHON\" \"$@\"\n",
        encoding="utf-8",
    )
    fake_python312.write_text(
        "#!/usr/bin/env bash\n"
        "printf selected >\"$PYTHON_312_MARKER\"\n"
        "exec \"$REAL_PYTHON\" \"$@\"\n",
        encoding="utf-8",
    )
    fake_python3.chmod(0o755)
    fake_python312.chmod(0o755)
    environment = hub_projection_authority_environment(tmp_path)
    environment.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "REAL_PYTHON": sys.executable,
            "PYTHON_312_MARKER": str(selection_marker),
            "TMPDIR": str(tmp_path),
        }
    )
    output = tmp_path / "proof.json"

    result = run_sourced(
        'trap cleanup_bootstrap_tmp_paths EXIT; '
        'generate_hub_local_release_proof "$2" "$3" "$4"',
        str(hub_alias),
        str(tmp_path / "hub-repo"),
        str(output),
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert selection_marker.read_text(encoding="utf-8") == "selected"
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "pass"


def test_hub_generator_rejects_missing_authority_before_execution(tmp_path: Path) -> None:
    hub_alias = tmp_path / "hub-alias"
    generator = hub_alias / "scripts" / "materialize_hub_local_release_proof.py"
    generator.parent.mkdir(parents=True)
    marker = tmp_path / "generator-ran"
    generator.write_text(
        "import os, pathlib\n"
        "pathlib.Path(os.environ['GENERATOR_MARKER']).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    environment = hub_projection_authority_environment(tmp_path)
    environment.update(
        {
            "CHUMMER_RELEASE_PYTHON": sys.executable,
            "GENERATOR_MARKER": str(marker),
        }
    )
    environment.pop("CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256")

    result = run_sourced(
        'generate_hub_local_release_proof "$2" "$3" "$4"',
        str(hub_alias),
        str(tmp_path / "hub-repo"),
        str(tmp_path / "proof.json"),
        env=environment,
    )

    assert result.returncode != 0
    assert "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256" in result.stderr
    assert not marker.exists()


def test_post_completion_exit_trap_forbids_blind_retry(tmp_path: Path) -> None:
    receipt_path = tmp_path / "release-upload-handoff.json"
    result = run_sourced(
        'BOOTSTRAP_RELEASE_UPLOAD_ACCEPTED=1; '
        'BOOTSTRAP_RELEASE_UPLOAD_ATTEMPT_RECEIPT_PATH="$2"; '
        'trap cleanup_bootstrap_tmp_paths EXIT; '
        'exit 73',
        str(receipt_path),
    )

    assert result.returncode == 73
    assert "Release completion was accepted" in result.stderr
    assert "may already be public" in result.stderr
    assert "Do not create or publish another session" in result.stderr
    assert str(receipt_path) in result.stderr


def test_hosted_upload_persists_recovery_state_around_completion() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    upload_start = bootstrap.index("upload_release_bundle_http() {")
    upload_end = bootstrap.index("\nstage_local_release_bundle() {", upload_start)
    upload = bootstrap[upload_start:upload_end]

    created = upload.index("record_upload_attempt_state created")
    endpoint_validation = upload.index("upload session response endpoints do not match the created session")
    uploaded = upload.index("record_upload_attempt_state uploaded")
    request_started = upload.index("record_upload_attempt_state request_started")
    completion = upload.index('"complete staged upload"')
    accepted = upload.index("BOOTSTRAP_RELEASE_UPLOAD_ACCEPTED=1")
    response_fsync = upload.index('fsync-file --path "$response_path"')
    completed = upload.index("record_upload_attempt_state completed")

    assert created < endpoint_validation < uploaded < request_started < completion
    assert completion < accepted < response_fsync < completed
    assert '--max-filesize "$max_response_bytes"' in upload
    assert '"$complete_url" \\\n      --no-retry' in upload

    main_call = bootstrap.index('"$hub_alias/scripts/release/release_upload_attempt_receipt.py"', upload_end)
    response_argument = bootstrap.rindex('"$response_path" \\', upload_end, main_call)
    assert response_argument < main_call


def test_hosted_upload_has_no_empty_common_array_expansion_under_bash3_nounset() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    upload_start = bootstrap.index("upload_release_bundle_http() {")
    upload_end = bootstrap.index("\nstage_local_release_bundle() {", upload_start)
    upload = bootstrap[upload_start:upload_end]

    # Bash 3 (the native macOS shell) treats an empty array expansion as an
    # unbound variable under `set -u`, unlike newer Bash releases.
    assert "request_common" not in upload


def test_hosted_upload_retains_request_started_on_ambiguous_completion(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    files = bundle / "files"
    files.mkdir(parents=True)
    manifest = {"version": "run-proof", "artifacts": []}
    (bundle / "releases.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    (bundle / "RELEASE_CHANNEL.generated.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    (files / "proof.bin").write_bytes(b"proof")
    response_path = tmp_path / "release-upload-response.json"
    receipt_path = tmp_path / "release-upload-handoff.json"
    upload_auth = "synthetic-upload-auth"
    completion_marker = tmp_path / "completion-count"

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        """#!/usr/bin/env bash
set -eu
test "${1:-}" = "-q"
url="${!#}"
while (( $# > 0 )); do
  case "$1" in
    --write-out) shift 2 ;;
    *) shift ;;
  esac
done
cat >/dev/null
case "$url" in
  */upload-sessions)
    printf '%s' '{"sessionId":"0123456789abcdef0123456789abcdef","expiresAtUtc":"2026-07-16T00:00:00Z","filesUrl":"/api/internal/releases/upload-sessions/0123456789abcdef0123456789abcdef/files","chunksUrl":"/api/internal/releases/upload-sessions/0123456789abcdef0123456789abcdef/chunks","completeUrl":"/api/internal/releases/upload-sessions/0123456789abcdef0123456789abcdef/complete"}'
    printf '\nCHUMMER_HTTP_STATUS:200'
    ;;
  */complete)
    count=0
    test -f "$COMPLETION_MARKER" && count="$(cat "$COMPLETION_MARKER")"
    printf '%s' "$((count + 1))" >"$COMPLETION_MARKER"
    head -c 2048 /dev/zero | tr '\0' x
    printf '\nCHUMMER_HTTP_STATUS:200'
    exit 63
    ;;
  *) printf '{}\nCHUMMER_HTTP_STATUS:200' ;;
esac
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    environment = clean_release_environment()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "COMPLETION_MARKER": str(completion_marker),
            "CHUMMER_RELEASE_UPLOAD_ATTEMPT_RECEIPT_PATH": str(receipt_path),
            "CHUMMER_RELEASE_UPLOAD_MAX_RESPONSE_BYTES": "1024",
        }
    )
    helper = REPO_ROOT / "scripts" / "release" / "release_upload_attempt_receipt.py"
    result = run_sourced(
        'upload_release_bundle_http "$2" "$3" "$4" "$5" "$6"',
        str(bundle),
        "https://chummer.run/api/internal/releases/upload-sessions",
        upload_auth,
        str(response_path),
        str(helper),
        env=environment,
    )

    assert result.returncode != 0
    assert completion_marker.exists(), result.stderr or result.stdout
    assert completion_marker.read_text(encoding="utf-8") == "1"
    assert "completion outcome is unknown" in result.stderr
    assert "Do not create another session" in result.stderr
    assert str(receipt_path) in result.stderr
    assert upload_auth not in result.stdout
    assert upload_auth not in result.stderr
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["sessionId"] == "0123456789abcdef0123456789abcdef"
    assert receipt["completion"]["state"] == "request_started"


def test_hosted_upload_uses_stdin_config_without_credential_file() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    main_index = bootstrap.index("main() {")
    cleanup_init_index = bootstrap.index("bootstrap_tmp_paths=()", main_index)
    cleanup_trap_index = bootstrap.index("trap cleanup_bootstrap_tmp_paths EXIT", cleanup_init_index)

    assert cleanup_init_index < cleanup_trap_index
    assert 'release_upload_curl_config="$(mktemp)"' not in bootstrap
    assert (
        'write_release_upload_curl_config "$release_upload_auth_value" \\\n'
        '      | curl -q --config - "$@"'
    ) in bootstrap
    assert "local -a bootstrap_tmp_paths=()" not in bootstrap
    assert "-D " not in bootstrap
    assert "--dump-header" not in bootstrap
    assert "headers_file" not in bootstrap
    assert "headers_path" not in bootstrap
    assert "response-headers" not in bootstrap


def test_hosted_upload_sanitizes_response_before_persistence(tmp_path: Path) -> None:
    raw_response = tmp_path / "raw-response.json"
    sanitized_response = tmp_path / "sanitized-response.json"
    secret = "signed-claim-must-not-persist"
    raw_response.write_text(
        json.dumps(
            {
                "status": "accepted",
                "generationId": "gen-run-20260720-abcdef0123456789",
                "activationReceiptId": "activation-abcdef0123456789",
                "canonicalManifestSha256": "sha256:" + "a" * 64,
                "compatibilityManifestSha256": "sha256:" + "b" * 64,
                "installDispatchUrls": [
                    "https://chummer.run/downloads/install/proof-artifact",
                    f"https://chummer.run/downloads/install/proof-artifact?claim={secret}",
                ],
                "directFileUrls": ["https://chummer.run/downloads/files/proof.dmg"],
                "promotedArtifactIds": ["proof-artifact"],
                "signedInInstallClaims": [{"claimCode": secret}],
                "credential": secret,
                "errors": [{"message": secret}],
            }
        ) + "\nCHUMMER_HTTP_STATUS:200",
        encoding="utf-8",
    )

    result = run_sourced(
        'sanitize_release_upload_response_stream "$3" 8192 <"$2"',
        str(raw_response),
        str(sanitized_response),
    )

    assert result.returncode == 0, result.stderr
    sanitized = json.loads(sanitized_response.read_text(encoding="utf-8"))
    assert sanitized["responseSanitized"] is True
    assert sanitized["status"] == "accepted"
    assert sanitized["generationId"] == "gen-run-20260720-abcdef0123456789"
    assert sanitized["activationReceiptId"] == "activation-abcdef0123456789"
    assert sanitized["canonicalManifestSha256"] == "sha256:" + "a" * 64
    assert sanitized["compatibilityManifestSha256"] == "sha256:" + "b" * 64
    assert sanitized["installDispatchUrls"] == [
        "https://chummer.run/downloads/install/proof-artifact"
    ]
    assert sanitized["directFileUrls"] == [
        "https://chummer.run/downloads/files/proof.dmg"
    ]
    assert sanitized["promotedArtifactIds"] == ["proof-artifact"]
    assert "signedInInstallClaims" not in sanitized
    assert "credential" not in sanitized
    assert "errors" not in sanitized
    assert secret not in sanitized_response.read_text(encoding="utf-8")
    assert sanitized_response.stat().st_mode & 0o777 == 0o600


def test_capture_release_upload_auth_scrubs_child_environment(tmp_path: Path) -> None:
    environment_log = tmp_path / "child-environment.json"
    secret_values = (
        "release-token-sentinel",
        "release-ticket-sentinel",
        "fleet-token-sentinel",
    )
    environment = clean_release_environment()
    environment.update(
        {
            "CHUMMER_RELEASE_UPLOAD_TOKEN": secret_values[0],
            "CHUMMER_RELEASE_UPLOAD_TICKET": secret_values[1],
            "FLEET_INTERNAL_API_TOKEN": secret_values[2],
            "ENVIRONMENT_LOG": str(environment_log),
        }
    )
    result = run_sourced(
        r'''
release_upload_auth_value=""
release_upload_auth_source=""
capture_release_upload_auth_value release_upload_auth_value release_upload_auth_source
python3 -c 'import json, os, pathlib; names = ["CHUMMER_RELEASE_UPLOAD_TOKEN", "CHUMMER_RELEASE_UPLOAD_TICKET", "FLEET_INTERNAL_API_TOKEN", "release_upload_auth_value"]; pathlib.Path(os.environ["ENVIRONMENT_LOG"]).write_text(json.dumps({name: os.environ[name] for name in names if name in os.environ}), encoding="utf-8")'
printf "%s|%s\n" "${#release_upload_auth_value}" "$release_upload_auth_source"
''',
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{len(secret_values[0])}|CHUMMER_RELEASE_UPLOAD_TOKEN\n"
    assert json.loads(environment_log.read_text(encoding="utf-8")) == {}
    for secret_value in secret_values:
        assert secret_value not in result.stdout
        assert secret_value not in result.stderr


def test_hosted_bootstrap_disables_inherited_xtrace_before_auth_capture(tmp_path: Path) -> None:
    synthetic = "hosted-xtrace-must-not-print-this-ticket"
    output_path = tmp_path / "candidate"
    environment = clean_release_environment()
    environment.update(
        {
            "CHUMMER_RELEASE_UPLOAD_TICKET": synthetic,
            "CHUMMER_MAC_RELEASE_STAGE_ONLY": "1",
            "CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR": str(output_path),
        }
    )

    result = subprocess.run(
        ["bash", "-x", str(BOOTSTRAP)],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode != 0
    assert "stage-only mode rejects publish-only setting CHUMMER_RELEASE_UPLOAD_TICKET" in result.stderr
    assert synthetic not in result.stdout
    assert synthetic not in result.stderr


def test_remote_release_proof_inputs_remain_disabled_by_default(tmp_path: Path) -> None:
    proof, marker, fake_bin = make_remote_proof_fixture(tmp_path)
    environment = clean_release_environment()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "REMOTE_CURL_MARKER": str(marker),
            "REMOTE_PROOF_SOURCE": str(proof),
        }
    )

    result = run_sourced('resolve_hub_local_release_proof_path "$2"', "https://proof.invalid/proof.json", env=environment)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "\n"
    assert not marker.exists()


def test_remote_release_proof_requires_explicit_sha256_before_download(tmp_path: Path) -> None:
    proof, marker, fake_bin = make_remote_proof_fixture(tmp_path)
    environment = clean_release_environment()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "REMOTE_CURL_MARKER": str(marker),
            "REMOTE_PROOF_SOURCE": str(proof),
            "CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS": "1",
        }
    )

    result = run_sourced('resolve_hub_local_release_proof_path "$2"', "https://proof.invalid/proof.json", env=environment)

    assert result.returncode != 0
    assert "CHUMMER_HUB_LOCAL_RELEASE_PROOF_EXPECTED_SHA256 must be set" in result.stderr
    assert not marker.exists()


def test_remote_release_proof_rejects_digest_mismatch(tmp_path: Path) -> None:
    proof, marker, fake_bin = make_remote_proof_fixture(tmp_path)
    environment = clean_release_environment()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "REMOTE_CURL_MARKER": str(marker),
            "REMOTE_PROOF_SOURCE": str(proof),
            "CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS": "1",
            "CHUMMER_HUB_LOCAL_RELEASE_PROOF_EXPECTED_SHA256": "0" * 64,
        }
    )

    result = run_sourced('resolve_hub_local_release_proof_path "$2"', "https://proof.invalid/proof.json", env=environment)

    assert result.returncode != 0
    assert "downloaded remote proof SHA-256 does not match" in result.stderr
    assert marker.is_file()


def test_remote_release_proof_accepts_only_digest_bound_bytes(tmp_path: Path) -> None:
    proof, marker, fake_bin = make_remote_proof_fixture(tmp_path)
    expected_sha256 = hashlib.sha256(proof.read_bytes()).hexdigest()
    environment = clean_release_environment()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "REMOTE_CURL_MARKER": str(marker),
            "REMOTE_PROOF_SOURCE": str(proof),
            "CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS": "1",
            "CHUMMER_HUB_LOCAL_RELEASE_PROOF_EXPECTED_SHA256": expected_sha256.upper(),
        }
    )
    command = (
        'resolved="$(resolve_hub_local_release_proof_path "$2")"; '
        'test -f "$resolved"; '
        'cat "$resolved"; '
        'rm -f "$resolved"'
    )

    result = run_sourced(command, "https://proof.invalid/proof.json", env=environment)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["contract_name"] == "chummer6-hub.local_release_proof"
    assert marker.is_file()


def test_producer_stage_configuration_is_explicit_and_fail_closed(tmp_path: Path) -> None:
    normal = run_sourced('parse_mac_release_stage_only_args; printf "%s|%s\\n" "$MAC_RELEASE_STAGE_ONLY" "$MAC_RELEASE_STAGE_OUTPUT_DIR"')
    assert normal.returncode == 0, normal.stderr
    assert normal.stdout == "0|\n"

    output = tmp_path / "candidate"
    for setting in ("CHUMMER_RELEASE_UPLOAD_TICKET", "CHUMMER_RELEASE_SKIP_STRICT_MANIFEST_VERIFY"):
        stage_environment = clean_release_environment()
        stage_environment.update(
            {
                "CHUMMER_MAC_RELEASE_STAGE_ONLY": "1",
                "CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR": str(output),
                setting: "must-not-be-used",
            }
        )
        conflict = run_sourced("parse_mac_release_stage_only_args", env=stage_environment)
        assert conflict.returncode == 1
        assert f"rejects publish-only setting {setting}" in conflict.stderr


def test_exact_incoming_scope_transport_is_canonical_and_fail_closed() -> None:
    accepted = run_sourced(
        'normalize_release_exact_incoming_scope_transport python3 "$2"',
        "AVALONIA:WIN:WIN-X64, avalonia:linux:linux-x64",
    )
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout == "avalonia:linux:linux-x64,avalonia:windows:win-x64\n"

    for invalid in (
        "",
        "avalonia:linux",
        "avalonia::linux-x64",
        "avalonia:linux:linux-x64,AVALONIA:LINUX:LINUX-X64",
        "avalonia:linux:../../escape",
    ):
        rejected = run_sourced(
            'normalize_release_exact_incoming_scope_transport python3 "$2"',
            invalid,
        )
        assert rejected.returncode != 0, invalid


def test_bootstrap_binds_exact_scope_across_every_publication_transport() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

    assert "X-Chummer-Release-Exact-Incoming-Scope: $exact_incoming_scope" in bootstrap
    assert ".exactIncomingDesktopTuples | join(\",\")" in bootstrap
    assert "upload session response did not bind the authenticated exact incoming desktop scope" in bootstrap
    assert (
        "CHUMMER_RELEASE_EXACT_INCOMING_TUPLES='$exact_incoming_scope' "
        "bash scripts/publish-download-bundle.sh"
    ) in bootstrap
    assert 'CHUMMER_RELEASE_EXACT_INCOMING_TUPLES="$exact_incoming_scope" \\\n' in bootstrap


def test_stage_only_rejects_exact_scope_even_when_declared_empty(tmp_path: Path) -> None:
    environment = clean_release_environment()
    environment.update(
        {
            "CHUMMER_MAC_RELEASE_STAGE_ONLY": "1",
            "CHUMMER_MAC_RELEASE_STAGE_OUTPUT_DIR": str(tmp_path / "candidate"),
            "CHUMMER_RELEASE_EXACT_INCOMING_TUPLES": "",
        }
    )

    result = run_sourced("parse_mac_release_stage_only_args; main", env=environment)

    assert result.returncode != 0
    assert "stage-only mode rejects publish-only setting CHUMMER_RELEASE_EXACT_INCOMING_TUPLES" in result.stderr


def test_stage_output_path_rejects_relative_existing_and_symlink_targets(tmp_path: Path) -> None:
    relative = run_sourced('resolve_mac_release_stage_output_path "$2"', "relative-output")
    assert relative.returncode != 0
    assert "must be absolute" in relative.stderr

    existing = tmp_path / "existing"
    existing.mkdir()
    existing_result = run_sourced('resolve_mac_release_stage_output_path "$2"', str(existing))
    assert existing_result.returncode != 0
    assert "must not already exist or be a symlink" in existing_result.stderr

    symlink = tmp_path / "candidate-link"
    symlink.symlink_to(tmp_path / "missing-target")
    symlink_result = run_sourced('resolve_mac_release_stage_output_path "$2"', str(symlink))
    assert symlink_result.returncode != 0
    assert "must not already exist or be a symlink" in symlink_result.stderr

    accepted = tmp_path / "new-candidate"
    accepted_result = run_sourced('resolve_mac_release_stage_output_path "$2"', str(accepted))
    assert accepted_result.returncode == 0, accepted_result.stderr
    assert Path(accepted_result.stdout.strip()) == accepted


def test_staged_copy_is_revalidated_and_atomically_placed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "proof" / "build-provenance" / "v1").mkdir(parents=True)
    (source / "startup-smoke").mkdir()
    (source / "proof" / "build-provenance" / "v1" / "receipt.json").write_text("{}\n", encoding="utf-8")
    (source / "startup-smoke" / "startup-smoke-test.receipt.json").write_text("{}\n", encoding="utf-8")
    verifier = tmp_path / "verify.py"
    verifier.write_text(
        "import os, pathlib, sys\n"
        "root = pathlib.Path(sys.argv[1])\n"
        "assert (root / 'proof/build-provenance/v1/receipt.json').is_file()\n"
        "assert (root / 'startup-smoke/startup-smoke-test.receipt.json').is_file()\n"
        "pathlib.Path(os.environ['VERIFIER_MARKER']).write_text(str(root), encoding='utf-8')\n",
        encoding="utf-8",
    )
    output = tmp_path / "candidate"
    verifier_marker = tmp_path / "verified.txt"
    environment = clean_release_environment()
    environment["VERIFIER_MARKER"] = str(verifier_marker)
    command = (
        'validate_bundle_directory_integrity() { test -f "$1/release-evidence/mac-stage-only.json"; }; '
        'stage_local_release_bundle "$2" "$3" "$4" run-test preview osx-arm64 avalonia'
    )
    result = run_sourced(command, str(source), str(output), str(verifier), env=environment)

    assert result.returncode == 0, result.stderr
    assert f"release_stage_only_path={output}" in result.stdout
    assert output.is_dir()
    assert verifier_marker.is_file()
    receipt = json.loads((output / "release-evidence" / "mac-stage-only.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "pass"
    assert receipt["uploadAttempted"] is False
    assert receipt["publicationAttempted"] is False
    assert receipt["countsAsPublicationEvidence"] is False
    assert list(tmp_path.glob(".candidate.stage.*")) == []


def test_stage_only_returns_before_every_publish_and_live_verification_path() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    main_index = bootstrap.index("main() {")
    stage_branch = bootstrap.index("if (( MAC_RELEASE_STAGE_ONLY == 1 )); then", bootstrap.index("create_minimal_promotion_bundle", main_index))
    stage_call = bootstrap.index("stage_local_release_bundle \\", stage_branch)
    stage_return = bootstrap.index("return 0", stage_call)
    publish_switch = bootstrap.index('case "$publish_mode" in', stage_return)
    live_verify = bootstrap.index('log "verifying live canonical manifest at $canonical_verify_url"', publish_switch)

    assert stage_branch < stage_call < stage_return < publish_switch < live_verify
    assert 'if (( MAC_RELEASE_STAGE_ONLY == 0 )); then\n    validate_publish_mode' in bootstrap
    assert 'verify_live_canonical_supportability_preflight "$canonical_verify_url"' in bootstrap
    assert "upload/publication/live verification were not attempted" in bootstrap


def test_served_runbook_documents_governed_stage_only_handoff() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    for required_fragment in (
        "## Governed local Mac candidate (stage only)",
        "start from a clean `chummer.run-services` checkout pinned to a reviewed commit",
        'CHUMMER_RELEASE_CHANNEL="preview"',
        'CHUMMER_RELEASE_VERSION="$release_version"',
        "CHUMMER_UI_EXPECTED_COMMIT",
        "CHUMMER_CORE_EXPECTED_COMMIT",
        "CHUMMER_HUB_EXPECTED_COMMIT",
        "CHUMMER_HUB_LOCAL_RELEASE_PROOF_EXPECTED_SHA256",
        "CHUMMER_UI_LOCALIZATION_RELEASE_GATE_EXPECTED_SHA256",
        "CHUMMER_UI_KIT_EXPECTED_COMMIT",
        "CHUMMER_HUB_REGISTRY_EXPECTED_COMMIT",
        "CHUMMER_MEDIA_FACTORY_EXPECTED_COMMIT",
        "CHUMMER_LEGACY_EXPECTED_COMMIT",
        '--stage-only',
        '--stage-output-dir "$output"',
        "absolute path whose parent exists and whose final directory does not exist",
        "This produces an unsigned preview candidate.",
        "proof/build-provenance/v1/invocations/",
        "proof/build-provenance/v1/sbom/",
        "countsAsPublicationEvidence=false",
        "It must fail the canonical publisher's Linux/Windows/macOS platform floor if supplied by itself.",
        "governed Linux and Windows outputs carrying the same fresh version",
        "CHUMMER_RELEASE_CANDIDATE_STAGE_ONLY=1",
        'CHUMMER_RELEASE_CANDIDATE_OUTPUT_DIR="$validated_candidate"',
        '"$full_candidate"',
        "Promotion or activation is a later, separately authorized operation.",
    ):
        assert required_fragment in runbook
