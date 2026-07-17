#!/usr/bin/env python3
from __future__ import annotations

import ast
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, quote_plus, urlsplit

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_google_oauth_linking_proof import verify as verify_google_oauth_linking_proof_receipt
from verify_windows_installer_visual_audit_intake_request import (
    verify as verify_windows_visual_intake_request_receipt,
)
from public_edge_postdeploy_contract import (
    PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME,
    PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS,
    normalize_public_edge_postdeploy_payload,
    public_edge_v2_artifact_contract_failures,
    public_edge_v2_offline_failures,
    public_edge_v2_private_identity_failures,
)
from verify_public_edge_observability_release import (
    DEFAULT_RUNTIME_SOURCES as PUBLIC_EDGE_OBSERVABILITY_RUNTIME_SOURCES,
    GATE_CONTRACT as PUBLIC_EDGE_OBSERVABILITY_GATE_CONTRACT_NAME,
    build_receipt as build_public_edge_observability_release_receipt,
    read_regular_file_bytes as read_stable_regular_file_bytes,
    release_candidate_binding as public_edge_observability_release_candidate_binding,
)
from writable_temp_root import configure_process_tmpdir, subprocess_env


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
ROOT = RUN_SERVICES_ROOT.parent
CHUMMER_PLAY_ROOT = ROOT / "chummer-play"
TRUSTED_BASH = Path("/usr/bin/bash").resolve()
TRUSTED_PYTHON = Path("/usr/bin/python3").resolve()
TRUSTED_NODE = Path("/usr/bin/node").resolve()
TRUSTED_GIT = Path("/usr/bin/git").resolve()
TRUSTED_PATH = "/usr/bin:/bin"
ISOLATED_PYTHON_RUNNER = (
    "import runpy,sys;"
    "script=sys.argv[1];"
    "sys.path.insert(0,str(__import__('pathlib').Path(script).resolve().parent));"
    "sys.argv=sys.argv[1:];"
    "runpy.run_path(script,run_name='__main__')"
)
TRUSTED_PYTHON_ISOLATED_PREFIX = (
    str(TRUSTED_PYTHON),
    "-I",
    "-c",
    ISOLATED_PYTHON_RUNNER,
)
AUTHORITATIVE_CONTROLLER_SCOPE = "authoritative_controller_runtime"
DIAGNOSTIC_AUTHORITY_SCOPE = "diagnostic_non_authoritative"
EXTERNAL_WRITE_AUTHORIZATION_FLAG = "--authorize-external-release-writes"
REDACTED_GLOBAL_VERIFIER_OUTPUT_PATH = "<redacted-local-verifier-transcript>"
AUTHORITATIVE_RELEASE_LAUNCHER_SHEBANG = b"#!/usr/bin/python3 -I\n"
LINUX_PR_SET_CHILD_SUBREAPER = 36
LINUX_PR_GET_CHILD_SUBREAPER = 37
PROCESS_CONTAINMENT_MODE = "linux_subreaper_procfs_v1"
PROCESS_POLL_INTERVAL_SECONDS = 0.05
PROJECTION_STEP_TIMEOUT_SECONDS = 300
CONTROLLER_OUTPUT_MAX_BYTES = 1024 * 1024
GOVERNED_CODE_SUFFIXES = frozenset(
    {
        ".bash",
        ".c",
        ".cjs",
        ".cpp",
        ".cs",
        ".csproj",
        ".css",
        ".dll",
        ".dockerfile",
        ".exe",
        ".fs",
        ".fsproj",
        ".go",
        ".h",
        ".hpp",
        ".html",
        ".js",
        ".json",
        ".jsx",
        ".mjs",
        ".node",
        ".props",
        ".ps1",
        ".py",
        ".pyi",
        ".rs",
        ".sh",
        ".sln",
        ".so",
        ".sql",
        ".targets",
        ".toml",
        ".ts",
        ".tsx",
        ".xml",
        ".yaml",
        ".yml",
    }
)
GOVERNED_CODE_BASENAMES = frozenset(
    {
        "Dockerfile",
        "Gemfile",
        "Makefile",
        "Pipfile",
        "go.mod",
        "go.sum",
        "gradlew",
        "package-lock.json",
        "pnpm-lock.yaml",
        "requirements.txt",
        "yarn.lock",
    }
)
# These are output/state roots, not executable authority.  Their exact list is
# itself bound into each governed snapshot.  Gate-owned outputs that can carry
# launch truth are bound separately by RELEASE_VERIFIER_GATE_RECEIPTS.
GOVERNED_CODE_EXCLUDED_OUTPUTS = (
    (".codex-studio/", "gate-generated receipts; launch-critical receipts are bound separately"),
    (".state/", "runtime watcher/import state, never an executable entrypoint"),
    (".tmp/", "ephemeral workspace scratch output"),
    ("TestResults/", "test result output"),
    ("_completion/", "operator completion/delivery output"),
    ("artifacts/", "build artifact output"),
    ("bin/", "compiler output; source inputs remain governed"),
    ("coverage/", "coverage report output"),
    ("dist/", "packaged distribution output"),
    ("obj/", "compiler intermediate output"),
    ("Chummer.Portal/downloads/", "published download shelf bound by release receipts"),
)
GOVERNED_CODE_EXCLUDED_OUTPUT_PREFIXES = tuple(
    prefix for prefix, _reason in GOVERNED_CODE_EXCLUDED_OUTPUTS
)
GOVERNED_RESTORED_DEPENDENCY_PREFIXES = (
    "node_modules/",
)
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH = PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_REFRESH_COMMAND = [
    *TRUSTED_PYTHON_ISOLATED_PREFIX,
    "scripts/verify_flagship_product_readiness_gate.py",
    "--summary-output",
    str(DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH),
]
TELEGRAM_TEXT_DELIVERY_ROOT = ROOT / "_completion" / "telegram_text_delivery"
REGISTRY_PUBLISHED_ROOT = ROOT / "chummer-hub-registry" / ".codex-studio" / "published"
REGISTRY_RELEASE_CHANNEL = REGISTRY_PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json"
PUBLIC_RELEASE_SNAPSHOT = ROOT / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT.generated.json"
PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT = ROOT / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"
RELEASE_BLOCKERS_JSON = ROOT / "RELEASE_BLOCKERS.generated.json"
CURRENT_AUXILIARY_RELEASE_RECEIPTS: tuple[tuple[str, Path], ...] = (
    (
        "supply_chain_evidence",
        ROOT / ".codex-studio" / "published" / "SUPPLY_CHAIN_RELEASE_GATE.generated.json",
    ),
    (
        "public_edge_observability_release",
        PUBLISHED_ROOT / "PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json",
    ),
)
SUPPLY_CHAIN_VERIFIER_SCRIPT = ROOT / "scripts" / "release" / "verify_supply_chain_evidence.py"
WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES = (
    ROOT / "chummer.run-services" / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
    ROOT / "chummer-presentation" / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
    ROOT / "chummer6-ui" / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json",
    ROOT / "chummer-presentation" / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json",
    ROOT / "chummer6-ui" / ".codex-studio" / "published" / "portal" / "RELEASE_CHANNEL.generated.json",
)
LIVE_DOWNLOADS_SHELF_DIR = RUN_SERVICES_ROOT / "Chummer.Portal" / "downloads"
PORTAL_RELEASE_CHANNEL = LIVE_DOWNLOADS_SHELF_DIR / "RELEASE_CHANNEL.generated.json"
STABLE_PUBLISH_SCRIPT = ROOT / "chummer6-ui" / "scripts" / "publish-download-bundle.sh"
DEFAULT_OUTPUT_PATH = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "RELEASE_READY.generated.json"
OUTPUT_PATH = DEFAULT_OUTPUT_PATH
VERIFY_SCRIPT = ROOT / "scripts" / "release" / "verify_chummer6_release_ready.sh"
RELEASE_TRUTH_SYNC_SCRIPT = ROOT / "scripts" / "release" / "_release_gate_common.py"
TIMEOUT_SECONDS = int(os.environ.get("CHUMMER_RELEASE_READY_TIMEOUT_SECONDS", "3600"))
TERMINATION_GRACE_SECONDS = int(os.environ.get("CHUMMER_RELEASE_READY_TERMINATION_GRACE_SECONDS", "10"))
PROJECTION_RETRY_MAX_AGE = timedelta(hours=6)
PROJECTION_RETRY_MINIMUM_COMPLETED_GATES = 38
PUBLIC_EDGE_OBSERVABILITY_GATE_MAX_AGE = timedelta(hours=24)
PUBLIC_EDGE_OBSERVABILITY_GATE_FUTURE_SKEW = timedelta(minutes=5)
PUBLIC_EDGE_OBSERVABILITY_READY_VERDICT = "OBSERVABILITY_RELEASE_READY"
RELEASE_VERIFIER_REPLAY_BINDING_CONTRACT = "chummer.release_verifier_replay_binding.v2"
RELEASE_VERIFIER_REPLAY_BINDING_PREFIX = "RELEASE_VERIFIER_BINDING "
RELEASE_VERIFIER_START_BINDING_PREFIX = "RELEASE_VERIFIER_START_BINDING "
RELEASE_VERIFIER_GATE_RECEIPT_BINDING_PREFIX = "RELEASE_GATE_RECEIPT_BINDING "
RELEASE_EXECUTION_PLAN_PREFIX = "RELEASE_EXECUTION_PLAN "
RELEASE_GATE_EXECUTION_BINDING_PREFIX = "RELEASE_GATE_EXECUTION_BINDING "
RELEASE_VERIFIER_REPLAY_MAX_AGE = timedelta(minutes=30)
RELEASE_VERIFIER_REPLAY_FUTURE_SKEW = timedelta(minutes=5)
RELEASE_VERIFIER_DIRECT_RECEIPT_MAX_AGE = timedelta(hours=24)
RELEASE_EXECUTION_PLAN_CONTRACT = "chummer.release_execution_plan.v3"
RELEASE_GATE_EXECUTION_PREBINDING_CONTRACT = "chummer.release_gate_execution_prebinding.v1"
RELEASE_GATE_EXECUTION_BINDING_CONTRACT = "chummer.release_gate_execution_binding.v1"
RELEASE_EXECUTION_PLAN_MAX_AGE = timedelta(hours=6)
RELEASE_EXECUTION_ENV_KEYS = (
    "CHUMMER_PUBLIC_BASE_URL",
    "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD",
    "CHUMMER_RUN_SERVICES_ROOT",
    "CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E",
    "CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E",
    "CHUMMER_RELEASE_READY_SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH",
    "CHUMMER_RELEASE_READY_SKIP_WINDOWS_RUNTIME_REFRESH",
    "CHUMMER_RELEASE_READY_GATE_TIMEOUT_SECONDS",
    "CHUMMER_RELEASE_READY_GUIDE_GATE_TIMEOUT_SECONDS",
    "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS",
    "CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_REUSE_MAX_AGE_HOURS",
    "CHUMMER_PUBLIC_EDGE_TIMEOUT_SECONDS",
    "PATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONNOUSERSITE",
    "BASH_ENV",
    "ENV",
    "CDPATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "NODE_PATH",
    "NODE_OPTIONS",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
)
RELEASE_EXECUTION_FORBIDDEN_ENV_KEYS = (
    "BASH_ENV",
    "ENV",
    "CDPATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "NODE_PATH",
    "NODE_OPTIONS",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
)
# This is deliberately a finite, code-owned list.  Values may be supplied to
# gate children, but authority artifacts contain only their SHA-256 digests.
# Unknown ambient variables are never inherited by the controller.
RELEASE_CONTROLLER_ENV_ALLOWLIST = frozenset(
    {
        *RELEASE_EXECUTION_ENV_KEYS,
        "HOME",
        "LANG",
        "LC_ALL",
        "TZ",
        "TMPDIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE",
        "CHUMMER_SKIP_CODEX_HANDOFF_MATERIALIZER",
        "CHUMMER_SKIP_RELEASE_WRAPPER_REFRESH",
        "CHUMMER_SKIP_PUBLIC_GUIDE_VERIFICATION",
        "CHUMMER_RELEASE_READY_MATERIALIZER_ACTIVE",
        "TEABLE_ACCESS_TOKEN",
        "TEABLE_API_TOKEN",
        "TEABLE_BASE_URL",
        "TEABLE_SPACE_ID",
        "TEABLE_DATABASE_ID",
        "TEABLE_TABLE_ID",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REDIRECT_URI",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "CF_API_TOKEN",
        "CF_ACCOUNT_ID",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_REGION",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_OPTIONAL_LOCKS",
    }
)
RELEASE_PROVIDER_ENV_KEYS = frozenset(
    {
        "TEABLE_ACCESS_TOKEN",
        "TEABLE_API_TOKEN",
        "TEABLE_BASE_URL",
        "TEABLE_SPACE_ID",
        "TEABLE_DATABASE_ID",
        "TEABLE_TABLE_ID",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REDIRECT_URI",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "CF_API_TOKEN",
        "CF_ACCOUNT_ID",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_REGION",
    }
)
RELEASE_SECRET_ENV_KEYS = frozenset(
    {
        "TEABLE_ACCESS_TOKEN",
        "TEABLE_API_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "CLOUDFLARE_API_TOKEN",
        "CF_API_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    }
)
RELEASE_GATE_PROVIDER_ENV_KEYS: dict[str, frozenset[str]] = {
    "verify_supply_chain_evidence": frozenset(
        {
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_REGION",
        }
    ),
    "verify_external_distribution_mirror_proof": frozenset(
        {
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_REGION",
        }
    ),
    "verify_google_oauth_linking_operator_evidence_request": frozenset(
        {
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_OAUTH_REDIRECT_URI",
        }
    ),
    "verify_google_oauth_linking_proof": frozenset(
        {
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_OAUTH_REDIRECT_URI",
        }
    ),
    "verify_account_handoff_runtime_config": frozenset(
        {
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_OAUTH_REDIRECT_URI",
        }
    ),
    "verify_ea_operator_readiness": frozenset(
        {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"}
    ),
    "verify_operator_release_dashboard": frozenset(
        {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"}
    ),
    "verify_public_edge_compose_operability": frozenset(
        {
            "CLOUDFLARE_API_TOKEN",
            "CLOUDFLARE_ACCOUNT_ID",
            "CF_API_TOKEN",
            "CF_ACCOUNT_ID",
        }
    ),
    "verify_public_edge_observability_release": frozenset(
        {
            "CLOUDFLARE_API_TOKEN",
            "CLOUDFLARE_ACCOUNT_ID",
            "CF_API_TOKEN",
            "CF_ACCOUNT_ID",
        }
    ),
    "verify_public_edge_postdeploy_gate": frozenset(
        {
            "CLOUDFLARE_API_TOKEN",
            "CLOUDFLARE_ACCOUNT_ID",
            "CF_API_TOKEN",
            "CF_ACCOUNT_ID",
        }
    ),
    "verify_teable_important_work_sync": frozenset(
        {
            "TEABLE_ACCESS_TOKEN",
            "TEABLE_API_TOKEN",
            "TEABLE_BASE_URL",
            "TEABLE_SPACE_ID",
            "TEABLE_DATABASE_ID",
            "TEABLE_TABLE_ID",
        }
    ),
}
CODE_ENTRYPOINT_SUFFIXES = (".sh", ".py", ".cjs", ".js")
REQUIRED_RELEASE_VERIFIER_GATES = (
    "verify_chummer6_desktop_gold",
    "verify_chummer6_blazor_gold",
    "verify_design_release_policy",
    "verify_package_boundaries",
    "verify_supply_chain_evidence",
    "verify_core_release_receipts",
    "verify_run_services_restore_drill",
    "verify_release_bundle_transaction",
    "verify_release_channel",
    "verify_public_projection",
    "verify_public_edge_compose_operability",
    "verify_public_edge_observability_release",
    "verify_hub_release_truth_alignment",
    "verify_public_ui_frame_integrity",
    "verify_public_release_snapshot_truth",
    "verify_public_copy_leak_gate",
    "verify_live_surface_parity",
    "verify_public_route_proof",
    "verify_live_public_windows_installer",
    "verify_external_distribution_mirror_proof",
    "verify_windows_installer_visual_audit_intake_request",
    "verify_ruleset_readiness",
    "verify_flagship_product_readiness",
    "verify_public_edge_postdeploy_gate",
    "verify_public_portal_e2e",
    "verify_partizipate_runtime_fallback",
    "verify_participate_billing_honesty",
    "verify_account_handoff_runtime_config",
    "verify_google_oauth_linking_operator_evidence_request",
    "verify_google_oauth_linking_proof",
    "verify_ea_operator_readiness",
    "verify_mymedia_public_surface",
    "verify_design_quality_gate",
    "verify_mobile_release_proof",
    "verify_ui_kit_package_release",
    "verify_media_claims",
    "verify_cross_repo_receipt_consistency",
    "verify_proof_freshness",
    "verify_no_public_internal_dependencies",
    "verify_public_truth_convergence",
    "verify_guide_convergence",
    "verify_repo_release_posture",
    "verify_platform_matrix",
    "crawl_public_release_surfaces",
    "verify_teable_important_work_sync",
    "verify_operator_release_dashboard",
)


def isolated_python_argv(
    script: str | Path,
    *arguments: object,
) -> list[str]:
    """Run a governed script after isolated Python startup has completed."""

    return [
        *TRUSTED_PYTHON_ISOLATED_PREFIX,
        str(script),
        *(str(argument) for argument in arguments),
    ]


def isolated_python_command(
    script: str | Path,
    *arguments: object,
) -> str:
    return shlex.join(isolated_python_argv(script, *arguments))


def supported_release_controller_command(
    *,
    force_global_verifier: bool = False,
    external_write_authorized: bool = False,
    global_verifier_output: bool = False,
    global_verifier_output_sha256: str = "",
    retry_release_truth_projection: bool = False,
    skip_windows_runtime_refresh: bool = False,
    skip_google_oauth_runtime_refresh: bool = False,
) -> str:
    """Return the executable launcher invocation recorded in release receipts."""

    effective_arguments: list[str] = []
    if force_global_verifier:
        effective_arguments.append("--force-global-verifier")
    if external_write_authorized:
        effective_arguments.append(EXTERNAL_WRITE_AUTHORIZATION_FLAG)
    if global_verifier_output:
        effective_arguments.extend(
            [
                "--global-verifier-output",
                REDACTED_GLOBAL_VERIFIER_OUTPUT_PATH,
                "--global-verifier-output-sha256",
                global_verifier_output_sha256,
            ]
        )
    if retry_release_truth_projection:
        effective_arguments.append("--retry-release-truth-projection")
    if skip_windows_runtime_refresh:
        effective_arguments.append("--skip-windows-runtime-refresh")
    if skip_google_oauth_runtime_refresh:
        effective_arguments.append("--skip-google-oauth-runtime-refresh")
    invocation = shlex.join(
        [str(VERIFY_SCRIPT), *effective_arguments]
    )
    return (
        f"CHUMMER_RUN_SERVICES_ROOT={shlex.quote(str(RUN_SERVICES_ROOT))} "
        f"{invocation}"
    )


def _module_assignment(tree: ast.Module, name: str) -> ast.expr | None:
    assignments: list[ast.expr] = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        ):
            assignments.append(statement.value)
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == name
            and statement.value is not None
        ):
            assignments.append(statement.value)
    return assignments[0] if len(assignments) == 1 else None


def _is_environment_selected_run_services_root(value: ast.expr) -> bool:
    if not (
        isinstance(value, ast.Call)
        and not value.args
        and not value.keywords
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "resolve"
    ):
        return False
    path_call = value.func.value
    if not (
        isinstance(path_call, ast.Call)
        and len(path_call.args) == 1
        and not path_call.keywords
        and isinstance(path_call.func, ast.Name)
        and path_call.func.id == "Path"
    ):
        return False
    lookup = path_call.args[0]
    return (
        isinstance(lookup, ast.Subscript)
        and isinstance(lookup.value, ast.Attribute)
        and lookup.value.attr == "environ"
        and isinstance(lookup.value.value, ast.Name)
        and lookup.value.value.id == "os"
        and isinstance(lookup.slice, ast.Constant)
        and lookup.slice.value == "CHUMMER_RUN_SERVICES_ROOT"
    )


def _materializer_path_parts(value: ast.expr) -> tuple[str, ...] | None:
    if isinstance(value, ast.Name):
        return (value.id,)
    if (
        isinstance(value, ast.BinOp)
        and isinstance(value.op, ast.Div)
        and isinstance(value.right, ast.Constant)
        and isinstance(value.right.value, str)
    ):
        left = _materializer_path_parts(value.left)
        if left is not None:
            return (*left, value.right.value)
    return None


def _protected_name_binding_count(tree: ast.AST, name: str) -> int:
    stored_names = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Store)
        and node.id == name
    )
    arguments = sum(
        1 for node in ast.walk(tree) if isinstance(node, ast.arg) and node.arg == name
    )
    return stored_names + arguments


def _is_name(value: ast.expr, name: str) -> bool:
    return isinstance(value, ast.Name) and value.id == name


def _is_str_of_name(value: ast.expr, name: str) -> bool:
    return (
        isinstance(value, ast.Call)
        and len(value.args) == 1
        and not value.keywords
        and _is_name(value.func, "str")
        and _is_name(value.args[0], name)
    )


def _is_forwarded_argv(value: ast.expr) -> bool:
    if not isinstance(value, ast.Starred) or not isinstance(value.value, ast.Subscript):
        return False
    subscript = value.value
    argv = subscript.value
    slice_value = subscript.slice
    return (
        isinstance(argv, ast.Attribute)
        and argv.attr == "argv"
        and _is_name(argv.value, "sys")
        and isinstance(slice_value, ast.Slice)
        and isinstance(slice_value.lower, ast.Constant)
        and slice_value.lower.value == 1
        and slice_value.upper is None
        and slice_value.step is None
    )


AUTHORITATIVE_RELEASE_LAUNCHER_SOURCE = '''#!/usr/bin/python3 -I
__python_launcher__ = ("chummer-release-controller",)

import os
import sys
from pathlib import Path


if sys.flags.isolated != 1:
    raise RuntimeError("NOT RELEASE READY: release launcher requires isolated Python startup")


RUN_SERVICES_ROOT = Path(os.environ["CHUMMER_RUN_SERVICES_ROOT"]).resolve()
MATERIALIZER = RUN_SERVICES_ROOT / "scripts" / "materialize_release_ready_receipt.py"
TRUSTED_PYTHON = "/usr/bin/python3"
TRUSTED_PATH = "/usr/bin:/bin"
FORBIDDEN_CODE_LOADING_ENV = (
    "BASH_ENV",
    "ENV",
    "CDPATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "NODE_PATH",
    "NODE_OPTIONS",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
)


def controller_environment() -> dict[str, str]:
    ambient = dict(os.environ)
    inherited_functions = sorted(
        name for name in ambient if name.startswith("BASH_FUNC_")
    )
    if inherited_functions:
        raise RuntimeError(
            "NOT RELEASE READY: inherited Bash functions are forbidden: "
            + ", ".join(inherited_functions)
        )
    inherited_hooks = sorted(
        name for name in FORBIDDEN_CODE_LOADING_ENV if ambient.get(name)
    )
    if inherited_hooks:
        raise RuntimeError(
            "NOT RELEASE READY: inherited code-loading hooks are forbidden: "
            + ", ".join(inherited_hooks)
        )
    for name in FORBIDDEN_CODE_LOADING_ENV:
        ambient.pop(name, None)
    ambient["PATH"] = TRUSTED_PATH
    ambient["PYTHONDONTWRITEBYTECODE"] = "1"
    ambient["PYTHONNOUSERSITE"] = "1"
    return ambient


def launch() -> None:
    environment = controller_environment()
    os.chdir(RUN_SERVICES_ROOT)
    os.execve(
        TRUSTED_PYTHON,
        [
            TRUSTED_PYTHON,
            "-I",
            str(MATERIALIZER),
            "--run-authoritative-controller",
            *sys.argv[1:],
        ],
        environment,
    )


launch()
'''


def _matches_authoritative_release_launcher_template(tree: ast.Module) -> bool:
    """Compare executable syntax while allowing comments and formatting changes."""

    expected = ast.parse(AUTHORITATIVE_RELEASE_LAUNCHER_SOURCE)
    return ast.dump(tree, include_attributes=False) == ast.dump(
        expected,
        include_attributes=False,
    )


def _read_authoritative_release_launcher(
    path: Path,
) -> tuple[bytes | None, str | None]:
    """Bind bytes, inode, ownership, and mode without following the final path."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None, "missing"
    except OSError:
        return None, "not a readable regular nonsymlink file"
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            return None, "not a regular nonsymlink file"
        if before.st_uid != os.geteuid():
            return None, "not owned by the current caller"
        if not before.st_mode & stat.S_IXUSR:
            return None, "not executable by its owner"
        if before.st_size > CONTROLLER_OUTPUT_MAX_BYTES:
            return None, "too_large"

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(
                fd,
                min(65536, CONTROLLER_OUTPUT_MAX_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > CONTROLLER_OUTPUT_MAX_BYTES:
                return None, "too_large"

        after = os.fstat(fd)
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(before, field) != getattr(after, field)
            for field in stable_fields
        ):
            return None, "changed during identity-bound read"
        return b"".join(chunks), None
    except OSError:
        return None, "unreadable"
    finally:
        os.close(fd)


def source_binding_failures(launcher_path: Path | None = None) -> list[str]:
    """Prove the shared launcher dispatches this checkout's materializer."""

    path = launcher_path or VERIFY_SCRIPT
    raw, error = _read_authoritative_release_launcher(path)
    if error is not None or raw is None:
        return [f"shared release launcher is {error or 'unreadable'}: {path}"]
    first_line = raw.partition(b"\n")[0] + (b"\n" if b"\n" in raw else b"")
    shebang_failure = first_line != AUTHORITATIVE_RELEASE_LAUNCHER_SHEBANG
    failures: list[str] = []
    if shebang_failure:
        failures.append(
            "shared release launcher shebang must be exactly #!/usr/bin/python3 -I "
            "with an LF terminator and no byte prefix"
        )
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return [*failures, f"shared release launcher is not valid UTF-8 Python: {exc}"]

    if not _matches_authoritative_release_launcher_template(tree):
        failures.append(
            "shared release launcher executable syntax must match the governed "
            "authoritative launcher template exactly (comments and formatting may differ)"
        )
    run_services_root = _module_assignment(tree, "RUN_SERVICES_ROOT")
    if run_services_root is None:
        failures.append("shared release launcher must assign RUN_SERVICES_ROOT exactly once")
    elif not _is_environment_selected_run_services_root(run_services_root):
        failures.append(
            "shared release launcher RUN_SERVICES_ROOT must exactly resolve "
            "Path(os.environ['CHUMMER_RUN_SERVICES_ROOT'])"
        )
    if _protected_name_binding_count(tree, "RUN_SERVICES_ROOT") != 1:
        failures.append(
            "shared release launcher RUN_SERVICES_ROOT must not be shadowed or reassigned"
        )

    materializer = _module_assignment(tree, "MATERIALIZER")
    if materializer is None:
        failures.append("shared release launcher must assign MATERIALIZER exactly once")
    else:
        path_parts = _materializer_path_parts(materializer)
        if path_parts not in {
            ("RUN_SERVICES_ROOT", "scripts", "materialize_release_ready_receipt.py"),
            ("RUN_SERVICES_ROOT", "scripts/materialize_release_ready_receipt.py"),
        }:
            failures.append(
                "shared release launcher MATERIALIZER must exactly target "
                "RUN_SERVICES_ROOT/scripts/materialize_release_ready_receipt.py"
            )
        if any(
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "chummer.run-services" in node.value
            for node in ast.walk(materializer)
        ):
            failures.append("shared release launcher MATERIALIZER is legacy-checkout-bound")
    if _protected_name_binding_count(tree, "MATERIALIZER") != 1:
        failures.append(
            "shared release launcher MATERIALIZER must not be shadowed or reassigned"
        )

    trusted_python = _module_assignment(tree, "TRUSTED_PYTHON")
    if not (
        isinstance(trusted_python, ast.Constant)
        and trusted_python.value == "/usr/bin/python3"
    ):
        failures.append(
            "shared release launcher TRUSTED_PYTHON must be exactly /usr/bin/python3"
        )
    if _protected_name_binding_count(tree, "TRUSTED_PYTHON") != 1:
        failures.append(
            "shared release launcher TRUSTED_PYTHON must not be shadowed or reassigned"
        )

    controller_environment_functions = [
        statement
        for statement in tree.body
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
        and statement.name == "controller_environment"
    ]
    if len(controller_environment_functions) != 1:
        failures.append(
            "shared release launcher must define controller_environment exactly once"
        )

    launch_functions = [
        statement
        for statement in tree.body
        if isinstance(statement, ast.FunctionDef) and statement.name == "launch"
    ]
    launch = launch_functions[0] if len(launch_functions) == 1 else None
    if launch is None:
        failures.append("shared release launcher must define launch exactly once")

    exec_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execve"
        and _is_name(node.func.value, "os")
    ]
    exec_call = exec_calls[0] if len(exec_calls) == 1 else None
    if exec_call is None:
        failures.append("shared release launcher must contain exactly one os.execve dispatch")

    if launch is not None and exec_call is not None:
        direct_dispatch = (
            bool(launch.body)
            and isinstance(launch.body[-1], ast.Expr)
            and launch.body[-1].value is exec_call
        )
        if not direct_dispatch:
            failures.append(
                "shared release launcher os.execve must be the final direct launch statement"
            )
        legacy_dispatch_literals = sorted(
            {
                node.value
                for node in ast.walk(launch)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "chummer.run-services" in node.value
            }
        )
        if legacy_dispatch_literals:
            failures.append("shared release launcher executable dispatch is legacy-checkout-bound")

        if len(exec_call.args) != 3 or exec_call.keywords:
            failures.append(
                "shared release launcher os.execve must have executable, argv, and environment"
            )
        else:
            executable, argv, environment = exec_call.args
            if not _is_name(executable, "TRUSTED_PYTHON"):
                failures.append(
                    "shared release launcher os.execve must execute TRUSTED_PYTHON"
                )
            expected_argv = (
                isinstance(argv, ast.List)
                and len(argv.elts) == 5
                and _is_name(argv.elts[0], "TRUSTED_PYTHON")
                and isinstance(argv.elts[1], ast.Constant)
                and argv.elts[1].value == "-I"
                and _is_str_of_name(argv.elts[2], "MATERIALIZER")
                and isinstance(argv.elts[3], ast.Constant)
                and argv.elts[3].value == "--run-authoritative-controller"
                and _is_forwarded_argv(argv.elts[4])
            )
            if not expected_argv:
                failures.append(
                    "shared release launcher os.execve argv must use isolated trusted Python, "
                    "str(MATERIALIZER), --run-authoritative-controller, and forwarded argv"
                )
            if not _is_name(environment, "environment"):
                failures.append(
                    "shared release launcher os.execve must use the sanitized environment"
                )
            environment_assignments = [
                node
                for node in ast.walk(launch)
                if isinstance(node, (ast.Assign, ast.AnnAssign))
                and (
                    (
                        isinstance(node, ast.Assign)
                        and any(
                            isinstance(target, ast.Name)
                            and target.id == "environment"
                            for target in node.targets
                        )
                    )
                    or (
                        isinstance(node, ast.AnnAssign)
                        and isinstance(node.target, ast.Name)
                        and node.target.id == "environment"
                    )
                )
            ]
            environment_value = (
                environment_assignments[0].value
                if len(environment_assignments) == 1
                else None
            )
            if not (
                isinstance(environment_value, ast.Call)
                and _is_name(environment_value.func, "controller_environment")
                and not environment_value.args
                and not environment_value.keywords
                and environment_assignments[0].lineno < exec_call.lineno
            ):
                failures.append(
                    "shared release launcher environment must come directly from "
                    "controller_environment()"
                )

    top_level_launch_calls = [
        statement
        for statement in tree.body
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and _is_name(statement.value.func, "launch")
        and not statement.value.args
        and not statement.value.keywords
    ]
    if (
        len(top_level_launch_calls) != 1
        or not tree.body
        or tree.body[-1] is not top_level_launch_calls[0]
    ):
        failures.append(
            "shared release launcher must invoke launch() exactly once as its final statement"
        )
    return failures


def current_git_head() -> str:
    completed = subprocess.run(
        [
            str(TRUSTED_GIT),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-C",
            str(RUN_SERVICES_ROOT),
            "rev-parse",
            "--verify",
            "HEAD",
        ],
        cwd=RUN_SERVICES_ROOT,
        env={
            "PATH": TRUSTED_PATH,
            "HOME": "/nonexistent",
            "LC_ALL": "C",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        },
        capture_output=True,
        check=False,
        timeout=30,
    )
    value = coerce_output(completed.stdout).strip()
    if completed.returncode != 0 or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
        detail = coerce_output(completed.stderr).strip()
        raise ValueError(
            "current run-services Git HEAD is unavailable"
            + (f": {detail}" if detail else "")
        )
    return value


def isolated_python_script(command: list[str]) -> Path:
    prefix_length = len(TRUSTED_PYTHON_ISOLATED_PREFIX)
    if (
        len(command) <= prefix_length
        or tuple(command[:prefix_length]) != TRUSTED_PYTHON_ISOLATED_PREFIX
    ):
        raise ValueError("release command lacks the isolated trusted Python launcher")
    return Path(command[prefix_length])


def canonical_release_gate_specs(
    environment: dict[str, str],
) -> tuple[dict[str, object], ...]:
    """Return the immutable, controller-owned 46-gate launch plan.

    This is the inspection API for integration tests.  It deliberately accepts
    only the already-sanitized controller environment; callers cannot inject
    commands, entrypoints, interpreters, or external-write classifications.
    """

    public_base = shlex.quote(environment["CHUMMER_PUBLIC_BASE_URL"])
    gate_timeout = int(environment["CHUMMER_RELEASE_READY_GATE_TIMEOUT_SECONDS"])
    guide_timeout = int(environment["CHUMMER_RELEASE_READY_GUIDE_GATE_TIMEOUT_SECONDS"])
    public_edge_timeout = int(environment["CHUMMER_PUBLIC_EDGE_TIMEOUT_SECONDS"])
    public_edge_reuse = int(environment["CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_REUSE_MAX_AGE_HOURS"])
    skip_google = environment["CHUMMER_RELEASE_READY_SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH"] == "1"
    skip_windows = environment["CHUMMER_RELEASE_READY_SKIP_WINDOWS_RUNTIME_REFRESH"] == "1"
    require_blazor_local_e2e = environment["CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E"] == "1"
    require_blazor_self_host_e2e = (
        environment["CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E"] == "1"
    )
    bash = str(TRUSTED_BASH)
    python = shlex.join(TRUSTED_PYTHON_ISOLATED_PREFIX)
    node = str(TRUSTED_NODE)
    root = str(ROOT)
    services = str(RUN_SERVICES_ROOT)
    published_browser_root = services + "/.codex-studio/published/public-edge-browser-proofs"

    def spec(
        name: str,
        command: str,
        *entrypoints: str | Path,
        timeout_seconds: int | None = None,
        external_write: bool = False,
    ) -> dict[str, object]:
        return {
            "name": name,
            "command": command,
            "cwd": root,
            "timeout_seconds": timeout_seconds or gate_timeout,
            "entrypoints": tuple(str(Path(value)) for value in entrypoints),
            "external_write": external_write,
        }

    windows_entrypoints: tuple[str, ...]
    if skip_windows:
        windows_command = (
            f"cd {services} && {python} {services}/scripts/"
            "verify_windows_installer_visual_audit_intake_request.py --require-pass"
        )
        windows_entrypoints = (
            f"{services}/scripts/verify_windows_installer_visual_audit_intake_request.py",
        )
    else:
        windows_command = (
            f"cd {services} && {python} {services}/scripts/"
            "materialize_windows_installer_visual_audit_intake_request.py "
            f"--release-channel {REGISTRY_RELEASE_CHANNEL} "
            f"--portal-release-channel {PORTAL_RELEASE_CHANNEL} "
            "--output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json "
            f"&& {python} {services}/scripts/verify_windows_installer_visual_audit_intake_request.py "
            f"&& {python} {services}/scripts/auto_import_windows_installer_gold_proof.py "
            "--intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json "
            "--output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json "
            "--wait-seconds 0"
        )
        windows_entrypoints = (
            f"{services}/scripts/materialize_windows_installer_visual_audit_intake_request.py",
            f"{services}/scripts/verify_windows_installer_visual_audit_intake_request.py",
            f"{services}/scripts/auto_import_windows_installer_gold_proof.py",
        )

    if skip_google:
        google_request_command = (
            f"cd {services} && {python} {services}/scripts/"
            "verify_google_oauth_linking_operator_evidence_request.py --require-pass"
        )
        google_request_entrypoints = (
            f"{services}/scripts/verify_google_oauth_linking_operator_evidence_request.py",
        )
        google_proof_command = (
            f"cd {services} && {python} {services}/scripts/"
            "verify_google_oauth_linking_proof.py --require-pass"
        )
        google_proof_entrypoints = (
            f"{services}/scripts/verify_google_oauth_linking_proof.py",
        )
    else:
        google_request_command = (
            f"cd {services} && {python} {services}/scripts/"
            f"materialize_google_oauth_linking_operator_evidence_request.py --base-url {public_base} "
            f"&& {python} {services}/scripts/verify_google_oauth_linking_operator_evidence_request.py "
            f"&& {python} {services}/scripts/auto_import_google_oauth_linking_operator_evidence.py "
            "--intake-request .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json "
            "--output .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json "
            "--wait-seconds 0"
        )
        google_request_entrypoints = (
            f"{services}/scripts/materialize_google_oauth_linking_operator_evidence_request.py",
            f"{services}/scripts/verify_google_oauth_linking_operator_evidence_request.py",
            f"{services}/scripts/auto_import_google_oauth_linking_operator_evidence.py",
        )
        google_proof_command = (
            f"cd {services} && {python} {services}/scripts/"
            f"materialize_google_oauth_linking_proof.py --base-url {public_base} "
            f"&& {python} {services}/scripts/verify_google_oauth_linking_proof.py"
        )
        google_proof_entrypoints = (
            f"{services}/scripts/materialize_google_oauth_linking_proof.py",
            f"{services}/scripts/verify_google_oauth_linking_proof.py",
        )

    ea_once = (
        f"{python} {services}/scripts/materialize_ea_operator_readiness.py && "
        f"{python} {services}/scripts/verify_ea_operator_readiness.py"
    )
    public_edge_preflight = " --skip-preflight" if environment["CHUMMER_PUBLIC_BASE_URL"].rstrip("/") == "https://chummer.run" else ""
    desktop_gold_entrypoints = (
        f"{root}/scripts/release/verify_desktop_gold_policy.sh",
        f"{root}/scripts/release/verify_package_boundaries.sh",
        f"{root}/chummer-hub-registry/scripts/release/verify_release_channel.sh",
        f"{services}/scripts/materialize_hub_local_release_proof.py",
        f"{services}/scripts/verify_desktop_native_trust_receipts.py",
        f"{root}/scripts/release/verify_platform_matrix.sh",
        f"{root}/chummer-presentation/scripts/verify_desktop_artifact_size_budget.py",
        f"{root}/chummer-presentation/scripts/release/verify_desktop_release_matrix.sh",
        f"{root}/chummer-presentation/scripts/release/verify_desktop_first_minute.sh",
        f"{root}/chummer-presentation/scripts/release/verify_desktop_gold_workflows.sh",
        f"{root}/chummer-presentation/scripts/release/verify_desktop_visual_proof.sh",
        f"{root}/chummer-presentation/scripts/release/verify_desktop_update_rollback_revoke.sh",
        f"{root}/chummer-presentation/scripts/release/verify_desktop_support_crash_feedback.sh",
        f"{root}/scripts/release/verify_proof_freshness.sh",
        f"{root}/scripts/release/verify_public_truth_convergence.sh",
        f"{root}/scripts/release/verify_no_public_internal_dependencies.sh",
        f"{root}/scripts/release/verify_repo_release_posture.sh",
    )
    desktop_gold_command = " && ".join(
        (
            f"{bash} {desktop_gold_entrypoints[0]}",
            f"{bash} {desktop_gold_entrypoints[1]}",
            f"{bash} {desktop_gold_entrypoints[2]}",
            (
                f"cd {services} && {python} {desktop_gold_entrypoints[3]} "
                f".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json "
                f"{public_base} docker-compose.yml 120 true >/dev/null && "
                f"{python} {desktop_gold_entrypoints[4]}"
            ),
            f"{bash} {desktop_gold_entrypoints[5]}",
            f"{python} {desktop_gold_entrypoints[6]}",
            *(f"{bash} {entrypoint}" for entrypoint in desktop_gold_entrypoints[7:]),
        )
    )
    blazor_gates: list[tuple[str, str, str]] = [
        (
            "verify_blazor_component_shell",
            f"{root}/chummer-presentation/scripts/test-blazor-components.sh",
            (
                f"cd {root}/chummer-presentation && {bash} "
                f"{root}/chummer-presentation/scripts/test-blazor-components.sh"
            ),
        ),
        (
            "verify_browser_surface_proxy_timeout_posture",
            f"{root}/scripts/release/verify_browser_surface_proxy_timeout_posture.sh",
            f"{bash} {root}/scripts/release/verify_browser_surface_proxy_timeout_posture.sh",
        ),
        (
            "verify_blazor_public_edge_workbench_proof",
            f"{root}/chummer-presentation/scripts/ai/milestones/blazor-public-edge-workbench-proof-check.sh",
            (
                f"{bash} {root}/chummer-presentation/scripts/ai/milestones/"
                "blazor-public-edge-workbench-proof-check.sh"
            ),
        ),
        (
            "verify_blazor_public_edge_execution_proof",
            f"{root}/chummer-presentation/scripts/ai/milestones/blazor-public-edge-execution-proof-check.sh",
            (
                f"{bash} {root}/chummer-presentation/scripts/ai/milestones/"
                "blazor-public-edge-execution-proof-check.sh"
            ),
        ),
        (
            "verify_blazor_play_surface_horizon",
            f"{root}/chummer-presentation/scripts/ai/milestones/blazor-play-surface-horizon-check.sh",
            (
                f"{bash} {root}/chummer-presentation/scripts/ai/milestones/"
                "blazor-play-surface-horizon-check.sh"
            ),
        ),
        (
            "verify_blazor_execution_horizon_bridge",
            f"{services}/scripts/verify_blazor_execution_horizon_bridge.py",
            f"cd {services} && {python} {services}/scripts/verify_blazor_execution_horizon_bridge.py",
        ),
        (
            "verify_blazor_public_edge_freshness",
            f"{root}/chummer-presentation/scripts/release/verify_blazor_public_edge_freshness.sh",
            (
                f"{bash} {root}/chummer-presentation/scripts/release/"
                "verify_blazor_public_edge_freshness.sh"
            ),
        ),
    ]
    if require_blazor_local_e2e:
        blazor_gates.append(
            (
                "verify_blazor_local_ui_e2e",
                f"{services}/scripts/e2e-ui.sh",
                f"cd {services} && {bash} {services}/scripts/e2e-ui.sh",
            )
        )
    if require_blazor_self_host_e2e:
        blazor_gates.extend(
            [
                (
                    "verify_blazor_self_host_workbench_e2e",
                    f"{root}/chummer-presentation/scripts/e2e-portal.sh",
                    (
                        f"cd {root}/chummer-presentation && {bash} "
                        f"{root}/chummer-presentation/scripts/e2e-portal.sh"
                    ),
                ),
                (
                    "verify_blazor_self_host_workbench_freshness",
                    (
                        f"{root}/chummer-presentation/scripts/release/"
                        "verify_blazor_self_host_workbench_freshness.sh"
                    ),
                    (
                        f"{bash} {root}/chummer-presentation/scripts/release/"
                        "verify_blazor_self_host_workbench_freshness.sh"
                    ),
                ),
            ]
        )
    blazor_gold_entrypoints = tuple(entrypoint for _name, entrypoint, _command in blazor_gates)
    blazor_command_parts = ["failures=()"]
    for gate_name, _entrypoint, gate_command in blazor_gates:
        blazor_command_parts.append(
            f"if ( {gate_command} ); then printf '%s\\n' {shlex.quote(f'PASS {gate_name}')}; "
            f"else failures+=({shlex.quote(gate_name)}); "
            f"printf '%s\\n' {shlex.quote(f'FAIL {gate_name}')}; fi"
        )
    blazor_command_parts.extend(
        [
            (
                "if (( ${#failures[@]} )); then printf '%s\\n' 'BLAZOR NOT GOLD'; "
                "printf '%s\\n' \"${failures[@]}\"; exit 1; fi"
            ),
            "printf '%s\\n' 'BLAZOR GOLD'",
        ]
    )
    blazor_gold_command = "; ".join(blazor_command_parts)
    values = (
        spec(
            "verify_chummer6_desktop_gold",
            desktop_gold_command,
            *desktop_gold_entrypoints,
        ),
        spec(
            "verify_chummer6_blazor_gold",
            blazor_gold_command,
            *blazor_gold_entrypoints,
        ),
        spec("verify_design_release_policy", f"{bash} {root}/scripts/release/verify_design_release_policy.sh", f"{root}/scripts/release/verify_design_release_policy.sh"),
        spec("verify_package_boundaries", f"{bash} {root}/scripts/release/verify_package_boundaries.sh", f"{root}/scripts/release/verify_package_boundaries.sh"),
        spec("verify_supply_chain_evidence", f"collector_status=0; {python} {root}/scripts/release/collect_build_provenance.py --workspace-root {root} || collector_status=$?; verifier_status=0; {python} {root}/scripts/release/verify_supply_chain_evidence.py --workspace-root {root} || verifier_status=$?; if (( collector_status != 0 )); then exit $collector_status; fi; exit $verifier_status", f"{root}/scripts/release/collect_build_provenance.py", f"{root}/scripts/release/verify_supply_chain_evidence.py"),
        spec("verify_core_release_receipts", f"{bash} {root}/chummer-core-engine/scripts/release/verify_core_release_receipts.sh", f"{root}/chummer-core-engine/scripts/release/verify_core_release_receipts.sh"),
        spec("verify_run_services_restore_drill", f"cd {services} && {bash} {services}/scripts/ai/run_services_restore_drill.sh", f"{services}/scripts/ai/run_services_restore_drill.sh"),
        spec(
            "verify_release_bundle_transaction",
            f"cd {services} && CHUMMER_RELEASE_BUNDLE_TRANSACTION_TRX_VERIFIER={services}/scripts/verify_release_bundle_transaction_trx.py {bash} {services}/scripts/verify_release_bundle_transaction_gate.sh",
            f"{services}/scripts/verify_release_bundle_transaction_gate.sh",
            f"{services}/scripts/verify_release_bundle_transaction_trx.py",
        ),
        spec("verify_release_channel", f"{bash} {root}/chummer-hub-registry/scripts/release/verify_release_channel.sh", f"{root}/chummer-hub-registry/scripts/release/verify_release_channel.sh"),
        spec("verify_public_projection", f"{bash} {services}/scripts/release/verify_public_projection.sh", f"{services}/scripts/release/verify_public_projection.sh"),
        spec("verify_public_edge_compose_operability", f"cd {services} && {python} {services}/scripts/verify_public_edge_compose_operability.py", f"{services}/scripts/verify_public_edge_compose_operability.py"),
        spec("verify_public_edge_observability_release", f"cd {services} && {python} {services}/scripts/verify_public_edge_observability_release.py", f"{services}/scripts/verify_public_edge_observability_release.py"),
        spec("verify_hub_release_truth_alignment", f"cd {services} && {python} {services}/scripts/verify_next90_m144_hub_release_truth_alignment.py", f"{services}/scripts/verify_next90_m144_hub_release_truth_alignment.py"),
        spec("verify_public_ui_frame_integrity", f"{bash} {root}/scripts/release/verify_public_ui_frame_integrity.sh", f"{root}/scripts/release/verify_public_ui_frame_integrity.sh"),
        spec("verify_public_release_snapshot_truth", f"{bash} {root}/scripts/release/verify_public_release_snapshot_truth.sh", f"{root}/scripts/release/verify_public_release_snapshot_truth.sh"),
        spec("verify_public_copy_leak_gate", f"cd {services} && {python} {services}/scripts/verify_public_copy_leak_gate.py --base-url {public_base}", f"{services}/scripts/verify_public_copy_leak_gate.py"),
        spec("verify_live_surface_parity", f"cd {services} && {python} {services}/scripts/verify_live_surface_parity.py --base-url {public_base}", f"{services}/scripts/verify_live_surface_parity.py"),
        spec("verify_public_route_proof", f"cd {services} && {python} {services}/scripts/verify_public_routes_from_manifest.py --base-url {public_base} --strict-positive --output .codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json", f"{services}/scripts/verify_public_routes_from_manifest.py"),
        spec("verify_live_public_windows_installer", f"cd {services} && {python} {services}/scripts/verify_live_public_windows_installer.py --base-url {public_base}", f"{services}/scripts/verify_live_public_windows_installer.py"),
        spec("verify_external_distribution_mirror_proof", f"cd {services} && {python} {services}/scripts/materialize_external_distribution_mirror_proof.py --base-url {public_base} --output .codex-studio/published/EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json", f"{services}/scripts/materialize_external_distribution_mirror_proof.py"),
        spec("verify_windows_installer_visual_audit_intake_request", windows_command, *windows_entrypoints),
        spec("verify_ruleset_readiness", f"cd {services} && {python} {services}/scripts/classify_ruleset_readiness.py --output .codex-studio/published/RULESET_READINESS.generated.json", f"{services}/scripts/classify_ruleset_readiness.py"),
        spec("verify_flagship_product_readiness", f"cd {services} && {python} {services}/scripts/verify_flagship_product_readiness_gate.py", f"{services}/scripts/verify_flagship_product_readiness_gate.py"),
        spec("verify_public_edge_postdeploy_gate", f"cd {services} && {python} {services}/scripts/verify_public_edge_postdeploy_gate.py --base-url {public_base} --timeout-seconds {public_edge_timeout}{public_edge_preflight} --require-downloads-status-playwright --require-mobile-pwa-viewport-playwright --require-pwa-offline-cache-playwright --require-blazor-new-runner-menu-playwright --require-frontdoor-navigation-playwright --reuse-existing-playwright-artifacts --reuse-artifact-max-age-hours {public_edge_reuse} --playwright-artifact-dir {published_browser_root}/downloads-status --mobile-pwa-viewport-artifact-dir {published_browser_root}/mobile-viewport --pwa-offline-cache-artifact-dir {published_browser_root}/offline-cache --blazor-new-runner-menu-artifact-dir {published_browser_root}/blazor-new-runner-menu --frontdoor-navigation-artifact-dir {published_browser_root}/frontdoor-navigation --output .codex-studio/published/PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json", f"{services}/scripts/verify_public_edge_postdeploy_gate.py"),
        spec("verify_public_portal_e2e", f"cd {services} && CHUMMER_PORTAL_BASE_URL={public_base} CHUMMER_PORTAL_PUBLIC_HOST= CHUMMER_PORTAL_FORWARDED_PROTO= CHUMMER_PORTAL_REQUIRE_BLAZOR=1 {node} {services}/scripts/e2e-portal.cjs", f"{services}/scripts/e2e-portal.cjs"),
        spec("verify_partizipate_runtime_fallback", f"cd {services} && {node} {services}/scripts/verify_partizipate_runtime_fallback.cjs --base-url {public_base}", f"{services}/scripts/verify_partizipate_runtime_fallback.cjs"),
        spec("verify_participate_billing_honesty", f"cd {services} && {python} {services}/scripts/materialize_participate_billing_honesty.py --completion-dir .codex-studio/published && {python} {services}/scripts/verify_participate_billing_honesty.py --completion-dir .codex-studio/published", f"{services}/scripts/materialize_participate_billing_honesty.py", f"{services}/scripts/verify_participate_billing_honesty.py"),
        spec("verify_account_handoff_runtime_config", f"cd {services} && {python} {services}/scripts/verify_account_handoff_runtime_config.py", f"{services}/scripts/verify_account_handoff_runtime_config.py"),
        spec("verify_google_oauth_linking_operator_evidence_request", google_request_command, *google_request_entrypoints),
        spec("verify_google_oauth_linking_proof", google_proof_command, *google_proof_entrypoints),
        spec("verify_ea_operator_readiness", f"cd {services} && ( ({ea_once}) || (sleep 5 && {ea_once}) || (sleep 15 && {ea_once}) )", f"{services}/scripts/materialize_ea_operator_readiness.py", f"{services}/scripts/verify_ea_operator_readiness.py"),
        spec("verify_mymedia_public_surface", f"cd {services} && {python} {services}/scripts/materialize_mymedia_public_surface.py && {python} {services}/scripts/verify_mymedia_public_surface.py", f"{services}/scripts/materialize_mymedia_public_surface.py", f"{services}/scripts/verify_mymedia_public_surface.py"),
        spec("verify_design_quality_gate", f"cd {services} && {python} {services}/scripts/materialize_design_quality_gate.py", f"{services}/scripts/materialize_design_quality_gate.py"),
        spec("verify_mobile_release_proof", f"{bash} {root}/chummer-play/scripts/release/verify_mobile_release_proof.sh", f"{root}/chummer-play/scripts/release/verify_mobile_release_proof.sh"),
        spec("verify_ui_kit_package_release", f"{bash} {root}/chummer-ui-kit/scripts/release/verify_ui_kit_package_release.sh", f"{root}/chummer-ui-kit/scripts/release/verify_ui_kit_package_release.sh"),
        spec("verify_media_claims", f"{bash} /docker/fleet/repos/chummer-media-factory/scripts/release/verify_media_claims.sh", "/docker/fleet/repos/chummer-media-factory/scripts/release/verify_media_claims.sh"),
        spec("verify_cross_repo_receipt_consistency", f"{bash} {root}/scripts/release/verify_cross_repo_receipt_consistency.sh", f"{root}/scripts/release/verify_cross_repo_receipt_consistency.sh"),
        spec("verify_proof_freshness", f"{bash} {root}/scripts/release/verify_proof_freshness.sh", f"{root}/scripts/release/verify_proof_freshness.sh"),
        spec("verify_no_public_internal_dependencies", f"{bash} {root}/scripts/release/verify_no_public_internal_dependencies.sh", f"{root}/scripts/release/verify_no_public_internal_dependencies.sh"),
        spec("verify_public_truth_convergence", f"{bash} {root}/scripts/release/verify_public_truth_convergence.sh", f"{root}/scripts/release/verify_public_truth_convergence.sh"),
        spec("verify_guide_convergence", f"{bash} {root}/Chummer6/scripts/release/verify_guide_convergence.sh", f"{root}/Chummer6/scripts/release/verify_guide_convergence.sh", timeout_seconds=guide_timeout),
        spec("verify_repo_release_posture", f"{bash} {root}/scripts/release/verify_repo_release_posture.sh", f"{root}/scripts/release/verify_repo_release_posture.sh"),
        spec("verify_platform_matrix", f"{bash} {root}/scripts/release/verify_platform_matrix.sh", f"{root}/scripts/release/verify_platform_matrix.sh"),
        spec("crawl_public_release_surfaces", f"{bash} {root}/scripts/release/crawl_public_release_surfaces.sh", f"{root}/scripts/release/crawl_public_release_surfaces.sh"),
        spec("verify_teable_important_work_sync", f"cd {services} && {python} {services}/scripts/sync_important_work_to_teable.py --sync", f"{services}/scripts/sync_important_work_to_teable.py", external_write=True),
        spec("verify_operator_release_dashboard", f"cd {services} && {python} {services}/scripts/materialize_operator_release_dashboard.py --release-ready-self-check", f"{services}/scripts/materialize_operator_release_dashboard.py"),
    )
    if tuple(str(item["name"]) for item in values) != REQUIRED_RELEASE_VERIFIER_GATES:
        raise RuntimeError("canonical release gate declaration drifted")
    return values
RELEASE_VERIFIER_BOUND_PROGRAMS = (
    ("release_ready_materializer", Path(__file__).resolve()),
    ("supply_chain_verifier", SUPPLY_CHAIN_VERIFIER_SCRIPT),
    ("public_edge_postdeploy_verifier", RUN_SERVICES_ROOT / "scripts" / "verify_public_edge_postdeploy_gate.py"),
    ("downloads_version_marker_verifier", RUN_SERVICES_ROOT / "scripts" / "verify_downloads_version_marker.py"),
    ("google_oauth_linking_verifier", RUN_SERVICES_ROOT / "scripts" / "verify_google_oauth_linking_proof.py"),
    ("google_oauth_linking_materializer", RUN_SERVICES_ROOT / "scripts" / "materialize_google_oauth_linking_proof.py"),
    ("google_oauth_request_verifier", RUN_SERVICES_ROOT / "scripts" / "verify_google_oauth_linking_operator_evidence_request.py"),
    ("google_oauth_request_materializer", RUN_SERVICES_ROOT / "scripts" / "materialize_google_oauth_linking_operator_evidence_request.py"),
    ("public_edge_observability_verifier", RUN_SERVICES_ROOT / "scripts" / "verify_public_edge_observability_release.py"),
    ("windows_visual_audit_verifier", RUN_SERVICES_ROOT / "scripts" / "verify_windows_installer_visual_audit_intake_request.py"),
    ("windows_visual_audit_intake_materializer", RUN_SERVICES_ROOT / "scripts" / "materialize_windows_installer_visual_audit_intake_request.py"),
    ("windows_visual_audit_proof_verifier", RUN_SERVICES_ROOT / "scripts" / "verify_windows_installer_visual_audit.py"),
    ("release_channel_verifier", ROOT / "chummer-hub-registry" / "scripts" / "release" / "verify_release_channel.sh"),
)
RELEASE_VERIFIER_GATE_RECEIPTS = (
    (
        "verify_supply_chain_evidence",
        "supply_chain_evidence",
        ROOT / ".codex-studio" / "published" / "SUPPLY_CHAIN_RELEASE_GATE.generated.json",
        "chummer6.supply_chain_release_gate.v1",
        (),
        (),
    ),
    (
        "verify_public_edge_observability_release",
        "public_edge_observability_release",
        PUBLISHED_ROOT / "PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json",
        PUBLIC_EDGE_OBSERVABILITY_GATE_CONTRACT_NAME,
        ("release_candidate", "version"),
        ("release_candidate", "channel"),
    ),
    (
        "verify_windows_installer_visual_audit_intake_request",
        "windows_installer_visual_audit",
        PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
        "chummer.windows_installer_visual_audit",
        ("release", "version"),
        ("release", "channel"),
    ),
    (
        "verify_flagship_product_readiness",
        "flagship_product_readiness",
        PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json",
        "chummer.flagship_product_readiness_gate.v1",
        (),
        (),
    ),
    (
        "verify_public_edge_postdeploy_gate",
        "public_edge_postdeploy_gate",
        PUBLISHED_ROOT / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json",
        PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME,
        ("expectedReleaseVersion",),
        ("expectedReleaseChannel",),
    ),
    (
        "verify_google_oauth_linking_proof",
        "google_oauth_linking_proof",
        PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
        "chummer.run.google_oauth_linking_proof",
        (),
        (),
    ),
)
RELEASE_READY_MATERIALIZER_ACTIVE_ENV = "CHUMMER_RELEASE_READY_MATERIALIZER_ACTIVE"
SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH_ENV = "CHUMMER_RELEASE_READY_SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH"
SKIP_WINDOWS_RUNTIME_REFRESH_ENV = "CHUMMER_RELEASE_READY_SKIP_WINDOWS_RUNTIME_REFRESH"
READY_MARKER = "RELEASE READY"
NOT_READY_MARKER = "NOT RELEASE READY"
WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST_NAME = "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT_NAME = "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
DEFAULT_WINDOWS_WATCHER_STATE = RUN_SERVICES_ROOT / ".state" / "windows_installer_gold_proof_watcher.generated.json"
GOLD_SUPPORTABILITY_STATE = "gold_supported"
FLAGSHIP_STABLE_CHANNELS = {"public_stable", "stable", "docker"}
FLAGSHIP_PUBLIC_STABLE_ROLLOUT_STATE = "public_stable"
PASS_STATES = {"pass", "passed", "ready"}
FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME = "chummer.flagship_product_readiness_gate.v1"
FLAGSHIP_PRODUCT_READY_VERDICT = "FLAGSHIP_PRODUCT_READY"
FLAGSHIP_PRODUCT_NOT_READY_VERDICT = "NOT_FLAGSHIP_PRODUCT_READY"
FLAGSHIP_PRODUCT_READINESS_RECOVERABLE_LAUNCH_BLOCKERS = {
    "final gold janitor state is 'fail'",
    "final gold janitor verdict is 'NOT_GOLD'",
    "live-backed gold claim is not allowed",
}
BLOCKING_ROLLOUT_STATES = {
    "coverage_incomplete",
    "release_review_required",
    "public_release_review_required",
    "desktop_polish_needed",
    "revoked",
}
INACTIVE_OPERATOR_REQUEST_ACTION_FIELDS = (
    "operator_ask_send_command",
    "preferred_drop_path",
    "preferred_drop_path_exists",
    "preferred_zip_name",
    "required_zip_filename",
    "discover_command",
    "import_command",
    "auto_import_command",
    "auto_import_watch_command",
    "post_import_verify_command",
    "post_import_verify_note",
    "post_import_commands",
    "expected_artifact_patterns",
    "drop_roots_checked",
)

configure_process_tmpdir(workspace_root=ROOT)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def terminate_process_group(
    process: subprocess.Popen[bytes],
    *,
    grace_seconds: int = TERMINATION_GRACE_SECONDS,
) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def process_identity(pid: int) -> dict[str, object] | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    closing = raw.rfind(")")
    if closing < 0:
        return None
    fields = raw[closing + 2 :].split()
    if len(fields) < 20:
        return None
    try:
        return {
            "pid": pid,
            "state": fields[0],
            "parent_pid": int(fields[1]),
            "process_group_id": int(fields[2]),
            "session_id": int(fields[3]),
            "start_time_ticks": int(fields[19]),
        }
    except ValueError:
        return None


def process_identity_is_live(identity: dict[str, object]) -> bool:
    current = process_identity(int(identity["pid"]))
    return bool(
        current is not None
        and current.get("start_time_ticks") == identity.get("start_time_ticks")
        and current.get("state") != "Z"
    )


def direct_process_children(pid: int) -> set[int]:
    values: set[int] = set()
    task_root = Path(f"/proc/{pid}/task")
    try:
        task_directories = list(task_root.iterdir())
    except (FileNotFoundError, PermissionError, OSError):
        return values
    for task in task_directories:
        try:
            text = (task / "children").read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError, OSError):
            continue
        for value in text.split():
            if value.isdigit():
                values.add(int(value))
    return values


def descendant_processes(roots: set[int]) -> dict[int, dict[str, object]]:
    values: dict[int, dict[str, object]] = {}
    pending = list(roots)
    while pending:
        parent = pending.pop()
        for child in direct_process_children(parent):
            if child in values:
                continue
            identity = process_identity(child)
            if identity is None:
                continue
            values[child] = identity
            pending.append(child)
    return values


def process_group_members(process_group_id: int) -> dict[int, dict[str, object]]:
    values: dict[int, dict[str, object]] = {}
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return values
    for entry in entries:
        if not entry.name.isdigit():
            continue
        identity = process_identity(int(entry.name))
        if identity is not None and identity.get("process_group_id") == process_group_id:
            values[int(entry.name)] = identity
    return values


def live_process_group_members(process_group_id: int) -> dict[int, dict[str, object]]:
    return {
        pid: identity
        for pid, identity in process_group_members(process_group_id).items()
        if identity.get("state") != "Z" and process_identity_is_live(identity)
    }


def ensure_authoritative_process_containment() -> dict[str, object]:
    if not sys.platform.startswith("linux") or not Path("/proc/self/task").is_dir():
        raise ValueError("authoritative process containment requires Linux procfs")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(LINUX_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise ValueError(f"failed to enable child subreaper containment: errno={error}")
    enabled = ctypes.c_int(0)
    if libc.prctl(
        LINUX_PR_GET_CHILD_SUBREAPER,
        ctypes.byref(enabled),
        0,
        0,
        0,
    ) != 0 or enabled.value != 1:
        error = ctypes.get_errno()
        raise ValueError(f"child subreaper containment verification failed: errno={error}")
    existing_children = direct_process_children(os.getpid())
    if existing_children:
        raise ValueError(
            "authoritative controller started with unowned child processes: "
            + ", ".join(str(value) for value in sorted(existing_children))
        )
    return {
        "mode": PROCESS_CONTAINMENT_MODE,
        "authoritative": True,
        "subreaper": True,
        "procfs": "/proc",
    }


def reap_adopted_processes(pids: set[int]) -> None:
    for pid in sorted(pids):
        while True:
            try:
                waited, _status = os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, ProcessLookupError):
                break
            if waited == 0 or waited == pid:
                break


def reap_all_adopted_processes() -> None:
    """Reap every exited child adopted by the subreaper without blocking."""

    while True:
        try:
            waited, _status = os.waitpid(-1, os.WNOHANG)
        except (ChildProcessError, ProcessLookupError):
            return
        if waited <= 0:
            return


def gate_lingering_processes(
    leader_pid: int,
    process_group_id: int,
    baseline_controller_children: set[int],
) -> dict[int, dict[str, object]]:
    controller_children = direct_process_children(os.getpid()) - baseline_controller_children
    values = descendant_processes({leader_pid, *controller_children})
    for pid in controller_children:
        identity = process_identity(pid)
        if identity is not None:
            values[pid] = identity
    values.update(live_process_group_members(process_group_id))
    values.pop(leader_pid, None)
    values.pop(os.getpid(), None)
    reap_adopted_processes(set(values))
    return {
        pid: identity
        for pid, identity in values.items()
        if process_identity_is_live(identity)
    }


def signal_process_identity(identity: dict[str, object], signum: int) -> None:
    if not process_identity_is_live(identity):
        return
    try:
        os.kill(int(identity["pid"]), signum)
    except ProcessLookupError:
        pass


def extinguish_gate_processes(
    leader_pid: int,
    process_group_id: int,
    baseline_controller_children: set[int],
    initial: dict[int, dict[str, object]],
    *,
    grace_seconds: int,
    force_group: bool,
) -> list[dict[str, object]]:
    known = dict(initial)

    def discover() -> dict[int, dict[str, object]]:
        current = gate_lingering_processes(
            leader_pid,
            process_group_id,
            baseline_controller_children,
        )
        known.update(current)
        return {
            pid: identity
            for pid, identity in known.items()
            if process_identity_is_live(identity)
        }

    if force_group or live_process_group_members(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for identity in discover().values():
        signal_process_identity(identity, signal.SIGTERM)
    deadline = time.monotonic() + max(0, grace_seconds)
    while time.monotonic() < deadline:
        live = discover()
        if not live and not live_process_group_members(process_group_id):
            reap_all_adopted_processes()
            return []
        reap_adopted_processes(set(known))
        time.sleep(PROCESS_POLL_INTERVAL_SECONDS)

    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
    for identity in discover().values():
        signal_process_identity(identity, signal.SIGKILL)
    kill_deadline = time.monotonic() + max(1.0, PROCESS_POLL_INTERVAL_SECONDS * 4)
    while time.monotonic() < kill_deadline:
        reap_adopted_processes(set(known))
        live = discover()
        if not live and not live_process_group_members(process_group_id):
            reap_all_adopted_processes()
            return []
        time.sleep(PROCESS_POLL_INTERVAL_SECONDS)
    remaining = list(discover().values())
    reap_all_adopted_processes()
    return remaining


def read_output_file(handle: object) -> str:
    """Read a bounded tail only after the gate process tree is quiescent."""

    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    truncated = size > CONTROLLER_OUTPUT_MAX_BYTES
    handle.seek(max(0, size - CONTROLLER_OUTPUT_MAX_BYTES))
    text = coerce_output(handle.read()).strip()
    if truncated:
        return f"[controller output truncated to final {CONTROLLER_OUTPUT_MAX_BYTES} bytes]\n{text}"
    return text


def interrupted_release_verifier_signal_exception(signum: int) -> BaseException:
    if signum == signal.SIGINT:
        return KeyboardInterrupt()
    return SystemExit(128 + signum)


def extract_failed_gates(failure_lines: list[str]) -> list[str]:
    failed_gates: list[str] = []
    seen: set[str] = set()
    for line in failure_lines:
        text = line.strip()
        if text.startswith("FAIL "):
            gate = text.removeprefix("FAIL ").strip().split(maxsplit=1)[0]
        else:
            gate = text.split(maxsplit=1)[0]
        gate = gate.rstrip(":")
        if not gate or gate in seen:
            continue
        seen.add(gate)
        failed_gates.append(gate)
    return failed_gates


def load_json_with_status(path: Path) -> tuple[dict[str, object], str]:
    if not path.is_file():
        return {}, "missing"
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "invalid"
    if not isinstance(parsed, dict):
        return {}, "invalid"
    return parsed, "loaded"


def load_json(path: Path) -> dict[str, object]:
    parsed, _ = load_json_with_status(path)
    return parsed


def supply_chain_receipt_validation_failures(
    payload: dict[str, object],
    *,
    current_time: datetime | None = None,
) -> list[str]:
    try:
        spec = importlib.util.spec_from_file_location(
            "chummer_release_ready_supply_chain_verifier",
            SUPPLY_CHAIN_VERIFIER_SCRIPT,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("supply chain verifier import spec is unavailable")
        verifier = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = verifier
        spec.loader.exec_module(verifier)
        failures = verifier.supply_chain_report_validation_failures(
            payload,
            ROOT,
            current_time=current_time,
            recheck_runtime_inputs=True,
        )
    except Exception as exc:
        return [f"supply chain receipt revalidation failed: {type(exc).__name__}: {exc}"]
    return [str(item).strip() for item in failures if str(item).strip()]


def google_oauth_receipt_validation_failures(path: Path) -> list[str]:
    try:
        ok, result = verify_google_oauth_linking_proof_receipt(path, require_pass=True)
    except Exception as exc:
        return [f"google OAuth receipt revalidation failed: {type(exc).__name__}: {exc}"]
    issues = normalized_string_list(result.get("issues")) if isinstance(result, dict) else []
    if not ok or not isinstance(result, dict) or result.get("status") != "pass":
        return issues or ["google OAuth receipt failed the current verifier"]
    if result.get("operator_evidence_pass") is not True:
        issues.append("google OAuth current verifier did not prove operator evidence")
    return list(dict.fromkeys(issues))


def direct_receipt_semantic_validation_failures(
    gate_name: str,
    payload: dict[str, object],
    receipt_path: Path,
    *,
    observed_at: datetime,
) -> list[str]:
    """Apply each direct receipt's available contract-specific verifier."""

    if gate_name == "verify_supply_chain_evidence":
        failures = supply_chain_receipt_validation_failures(
            payload,
            current_time=observed_at,
        )
    elif gate_name == "verify_public_edge_observability_release":
        failures = public_edge_observability_release_blocking_reasons(
            payload,
            receipt_path=receipt_path,
            release_channel_path=REGISTRY_RELEASE_CHANNEL,
            now=observed_at,
        )
    elif gate_name == "verify_windows_installer_visual_audit_intake_request":
        failures = windows_visual_audit_release_blocking_reasons(payload)
    elif gate_name == "verify_flagship_product_readiness":
        failures = flagship_product_readiness_gate_semantic_failures(payload)
    elif gate_name == "verify_public_edge_postdeploy_gate":
        failures = public_edge_postdeploy_release_blocking_reasons(payload)
    elif gate_name == "verify_google_oauth_linking_proof":
        failures = google_oauth_receipt_validation_failures(receipt_path)
    else:
        failures = []
    return list(dict.fromkeys(str(item).strip() for item in failures if str(item).strip()))


def refresh_flagship_product_readiness_gate(path: Path) -> None:
    if path != DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH:
        return
    verify_script = RUN_SERVICES_ROOT / "scripts" / "verify_flagship_product_readiness_gate.py"
    if not verify_script.is_file():
        return
    try:
        subprocess.run(
            DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_REFRESH_COMMAND,
            cwd=RUN_SERVICES_ROOT,
            env=subprocess_env(workspace_root=ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass


def receipt_load_failure(label: str, path: Path, load_status: str) -> str | None:
    if load_status == "missing":
        return f"{label} receipt is missing: {path}"
    if load_status == "invalid":
        return f"{label} receipt is malformed: {path}"
    return None


def receipt_status_fields(
    path: Path,
    payload: dict[str, object],
    load_status: str,
) -> dict[str, object]:
    source_status = str(payload.get("status") or "").strip()
    reported_source_status = source_status or ("invalid" if load_status == "invalid" else "missing")
    effective_status = reported_source_status
    normalized_source_status = normalized_token(source_status)
    failures = normalized_string_list(payload.get("failures"))
    failed_gates = normalized_string_list(payload.get("failed_gates"))
    if normalized_source_status in PASS_STATES and (failures or failed_gates):
        effective_status = "fail"
    contract_name = str(payload.get("contract_name") or payload.get("contractName") or "").strip()
    if (
        contract_name == FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME
        and normalized_source_status in PASS_STATES
        and flagship_product_readiness_gate_semantic_failures(payload)
    ):
        effective_status = "fail"
    result: dict[str, object] = {"status": effective_status}
    if reported_source_status != effective_status:
        result["raw_status"] = reported_source_status
    return result


def receipt_state(path: Path, payload: dict[str, object], load_status: str) -> dict[str, object]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "path": str(path),
        "exists": path.is_file(),
        "load_status": load_status,
        **receipt_status_fields(path, payload, load_status),
        "verdict": str(payload.get("verdict") or "").strip(),
        "contract_name": str(payload.get("contract_name") or payload.get("contractName") or "").strip(),
        "generated_at_utc": str(
            payload.get("generated_at_utc")
            or payload.get("generatedAtUtc")
            or payload.get("generatedAt")
            or payload.get("generated_at")
            or ""
        ).strip(),
        "summary_readiness_load_status": str(summary.get("readiness_load_status") or "").strip(),
    }


def normalized_token(value: object) -> str:
    return str(value or "").strip().lower()


def normalized_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalized_root_blocker_entries(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        blocker_id = str(entry.get("id") or entry.get("blocker_id") or "").strip()
        if not blocker_id:
            continue
        entry["id"] = blocker_id
        entry["blocker_id"] = str(entry.get("blocker_id") or blocker_id).strip()
        result.append(entry)
    return result


def path_exists(path_value: object) -> bool:
    text = str(path_value or "").strip()
    if not text:
        return False
    try:
        return Path(text).is_file()
    except OSError:
        return False


def text_sha256(path_value: object) -> str:
    text = str(path_value or "").strip()
    if not text:
        return ""
    try:
        path = Path(text)
        if not path.is_file():
            return ""
        return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest().lower()
    except (OSError, UnicodeDecodeError):
        return ""


def watcher_state_details(path_value: object) -> dict[str, object]:
    text = str(path_value or "").strip()
    path = Path(text) if text else DEFAULT_WINDOWS_WATCHER_STATE
    payload, load_status = load_json_with_status(path)
    matching_process_pids = (
        list(payload.get("matching_process_pids"))
        if isinstance(payload.get("matching_process_pids"), list)
        else []
    )
    duplicate_process_pids = (
        list(payload.get("duplicate_process_pids"))
        if isinstance(payload.get("duplicate_process_pids"), list)
        else []
    )
    status = str(payload.get("status") or "").strip()
    duplicate_count = int(payload.get("duplicate_process_count") or len(duplicate_process_pids))
    return {
        "watcher_state_receipt_path": str(path),
        "watcher_state_receipt_exists": path.is_file(),
        "watcher_state_receipt_load_status": load_status,
        "watcher_state_receipt_generated_at_utc": str(payload.get("generated_at_utc") or "").strip(),
        "watcher_status": status,
        "watcher_pid": payload.get("pid"),
        "watcher_process_alive": bool(payload.get("process_alive")),
        "watcher_matching_process_pids": matching_process_pids,
        "watcher_matching_process_count": int(payload.get("matching_process_count") or len(matching_process_pids)),
        "watcher_duplicate_process_pids": duplicate_process_pids,
        "watcher_duplicate_process_count": duplicate_count,
        "watcher_note": str(payload.get("note") or "").strip(),
        "watcher_attention_required": status != "running" or duplicate_count > 0,
    }


def refresh_watcher_state(watcher_status_command: str, watcher_path: Path) -> dict[str, object]:
    command_text = str(watcher_status_command or "").strip()
    if command_text:
        try:
            subprocess.run(
                shlex.split(command_text),
                cwd=RUN_SERVICES_ROOT,
                env=subprocess_env(workspace_root=ROOT),
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (FileNotFoundError, TypeError, ValueError, subprocess.TimeoutExpired):
            pass
    return watcher_state_details(watcher_path)


def refresh_auto_import_state(auto_import_command: str, auto_import_path: Path) -> tuple[dict[str, object], str]:
    command_text = str(auto_import_command or "").strip()
    if command_text:
        try:
            subprocess.run(
                shlex.split(command_text),
                cwd=RUN_SERVICES_ROOT,
                env=subprocess_env(workspace_root=ROOT),
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (FileNotFoundError, TypeError, ValueError, subprocess.TimeoutExpired):
            pass
    return load_json_with_status(auto_import_path)


def google_oauth_release_truth_effective_pass(payload: dict[str, object]) -> bool:
    if not isinstance(payload, dict):
        return False

    failures = normalized_string_list(payload.get("failures"))
    failed_gates = normalized_string_list(payload.get("failed_gates"))
    if normalized_token(payload.get("status")) in PASS_STATES and not failures and not failed_gates:
        return True

    operator_evidence = (
        payload.get("operator_end_to_end_evidence")
        if isinstance(payload.get("operator_end_to_end_evidence"), dict)
        else {}
    )
    operator_request_artifacts = (
        payload.get("operator_request_artifacts")
        if isinstance(payload.get("operator_request_artifacts"), dict)
        else {}
    )
    quick_probe = (
        payload.get("quick_handoff_probe")
        if isinstance(payload.get("quick_handoff_probe"), dict)
        else {}
    )
    signed_in_probe = (
        payload.get("signed_in_link_handoff")
        if isinstance(payload.get("signed_in_link_handoff"), dict)
        else {}
    )
    request_status = normalized_token(
        operator_request_artifacts.get("request_effective_status")
        or operator_request_artifacts.get("request_status")
    )
    signed_in_status = normalized_token(signed_in_probe.get("status"))
    only_signed_in_failures = bool(failures) and all(
        item.startswith("signed_in_link_handoff:") for item in failures
    )
    only_paused_auth_failures = bool(failures) and all(
        item.startswith("auth_signin_automation_paused:") for item in failures
    )

    if (
        request_status == "not_required"
        and operator_request_artifacts.get("operator_action_still_required") is False
        and not failed_gates
        and only_paused_auth_failures
    ):
        return True

    return (
        operator_evidence.get("pass") is True
        and request_status == "not_required"
        and quick_probe.get("pass") is True
        and signed_in_status == "fail"
        and only_signed_in_failures
    )


def telegram_delivery_receipt_details(receipt_name: object) -> dict[str, object]:
    normalized_receipt_name = str(receipt_name or "").strip()
    receipt_path = TELEGRAM_TEXT_DELIVERY_ROOT / normalized_receipt_name if normalized_receipt_name else None
    receipt_exists = bool(receipt_path and receipt_path.is_file())
    payload = load_json(receipt_path) if receipt_exists and receipt_path is not None else {}
    return {
        "operator_ask_delivery_receipt_path": str(receipt_path) if receipt_path is not None else "",
        "operator_ask_delivery_receipt_exists": receipt_exists,
        "operator_ask_delivery_status": str(payload.get("status") or "").strip(),
        "operator_ask_delivery_generated_at_utc": str(payload.get("generated_at_utc") or "").strip(),
        "operator_ask_delivery_message_ids": list(payload.get("message_ids")) if isinstance(payload.get("message_ids"), list) else [],
        "operator_ask_delivery_text_sha256": str(payload.get("text_sha256") or "").strip(),
        "operator_ask_delivery_text_preview": str(payload.get("text_preview") or "").strip(),
    }


def suppress_inactive_operator_request_actions(artifacts: dict[str, object]) -> dict[str, object]:
    historical = (
        dict(artifacts.get("operator_action_historical_artifacts"))
        if isinstance(artifacts.get("operator_action_historical_artifacts"), dict)
        else {}
    )
    for field in INACTIVE_OPERATOR_REQUEST_ACTION_FIELDS:
        if field not in artifacts:
            continue
        value = artifacts.get(field)
        if isinstance(value, list):
            if value:
                historical[field] = list(value)
            artifacts[field] = []
            continue
        if isinstance(value, bool):
            if value:
                historical[field] = value
            artifacts[field] = False
            continue
        text = str(value or "").strip()
        if text:
            historical[field] = text
        artifacts[field] = ""
    artifacts["operator_action_historical_only"] = bool(historical)
    if historical:
        artifacts["operator_action_historical_artifacts"] = historical
    return artifacts


def restore_inactive_operator_request_actions(artifacts: dict[str, object]) -> dict[str, object]:
    historical = (
        dict(artifacts.get("operator_action_historical_artifacts"))
        if isinstance(artifacts.get("operator_action_historical_artifacts"), dict)
        else {}
    )
    for field in INACTIVE_OPERATOR_REQUEST_ACTION_FIELDS:
        if field not in historical:
            continue
        value = historical.pop(field)
        current = artifacts.get(field)
        if isinstance(value, list):
            if not current:
                artifacts[field] = list(value)
            continue
        if isinstance(value, bool):
            if not current:
                artifacts[field] = value
            continue
        if not str(current or "").strip():
            artifacts[field] = value
    if not str(artifacts.get("operator_ask_delivery_text_preview") or "").strip():
        historical_preview = str(artifacts.get("operator_ask_delivery_historical_text_preview") or "").strip()
        if historical_preview:
            artifacts["operator_ask_delivery_text_preview"] = historical_preview
    artifacts["operator_action_historical_artifacts"] = historical
    artifacts["operator_action_historical_only"] = bool(historical)
    return artifacts


def enrich_operator_ask_delivery_state(artifacts: dict[str, object]) -> dict[str, object]:
    delivery_receipt_path = str(artifacts.get("operator_ask_delivery_receipt_path") or "").strip()
    operator_ask_receipt_name = str(artifacts.get("operator_ask_receipt_name") or "").strip()
    if not delivery_receipt_path and operator_ask_receipt_name:
        artifacts.update(telegram_delivery_receipt_details(operator_ask_receipt_name))

    operator_ask_message_sha256 = str(artifacts.get("operator_ask_message_sha256") or "").strip()
    if not operator_ask_message_sha256:
        operator_ask_message_sha256 = text_sha256(artifacts.get("operator_ask_text_path"))
        if operator_ask_message_sha256:
            artifacts["operator_ask_message_sha256"] = operator_ask_message_sha256

    delivery_text_sha256 = str(artifacts.get("operator_ask_delivery_text_sha256") or "").strip()
    comparable = bool(operator_ask_message_sha256 and delivery_text_sha256)
    matches_current = bool(comparable and operator_ask_message_sha256 == delivery_text_sha256)
    request_status = str(artifacts.get("request_status") or "").strip()
    effective_request_status = str(
        artifacts.get("request_effective_status")
        or request_status
        or ""
    ).strip()
    needs_resend = bool(
        comparable
        and not matches_current
        and effective_request_status != "not_required"
    )
    if effective_request_status == "not_required":
        historical_preview = str(artifacts.get("operator_ask_delivery_text_preview") or "").strip()
        if historical_preview:
            artifacts["operator_ask_delivery_historical_text_preview"] = historical_preview
            artifacts["operator_ask_delivery_text_preview"] = ""
        suppress_inactive_operator_request_actions(artifacts)
        artifacts["operator_ask_delivery_historical_only"] = True
        comparable = False
        matches_current = False
        needs_resend = False
    else:
        restore_inactive_operator_request_actions(artifacts)
        artifacts["operator_ask_delivery_historical_only"] = False
    send_command = str(artifacts.get("operator_ask_send_command") or "").strip()
    artifacts["operator_ask_delivery_current_text_comparable"] = comparable
    artifacts["operator_ask_delivery_matches_current_text"] = matches_current
    artifacts["operator_ask_delivery_needs_resend"] = needs_resend
    artifacts["operator_ask_resend_command"] = send_command if needs_resend else ""
    return artifacts


def release_channel_identity(payload: dict[str, object]) -> dict[str, str]:
    return {
        "status": normalized_token(payload.get("status")),
        "channel": normalized_token(payload.get("channelId") or payload.get("channel")),
        "version": str(payload.get("version") or payload.get("releaseVersion") or "").strip(),
        "supportability_state": normalized_token(payload.get("supportabilityState")),
        "rollout_state": normalized_token(payload.get("rolloutState")),
    }


def release_channel_identity_text(identity: dict[str, str]) -> str:
    return (
        f"channel={identity.get('channel') or 'missing'}, "
        f"version={identity.get('version') or 'missing'}, "
        f"supportability={identity.get('supportability_state') or 'missing'}, "
        f"rollout={identity.get('rollout_state') or 'missing'}"
    )


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def workspace_portal_release_channel_drift_failures(
    authoritative_payload: dict[str, object],
) -> list[str]:
    authoritative_identity = release_channel_identity(authoritative_payload)
    failures: list[str] = []
    seen_paths: set[Path] = set()
    for candidate in WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES:
        path = Path(candidate)
        if not path.is_file():
            continue
        resolved_path = path.resolve()
        if resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)
        local_payload = load_json(resolved_path)
        local_identity = release_channel_identity(local_payload)
        if local_identity == authoritative_identity:
            continue
        failures.append(
            "workspace portal release channel artifact "
            f"{display_path(resolved_path)} disagrees with authoritative registry receipt "
            f"(local {release_channel_identity_text(local_identity)}; "
            f"authoritative {release_channel_identity_text(authoritative_identity)})"
        )
    return failures


def current_release_truth_root_context() -> dict[str, object]:
    blockers_payload, load_status = load_json_with_status(RELEASE_BLOCKERS_JSON)
    if load_status != "loaded":
        return {
            "root_blocker_ids": [],
            "root_blockers": [],
            "root_blockers_generated_at": "",
            "stable_promotion_command": "",
            "post_promotion_verify_command": "",
            "root_release_truth_source": str(RELEASE_BLOCKERS_JSON),
        }

    root_blockers = normalized_root_blocker_entries(blockers_payload.get("root_blockers"))
    if not root_blockers:
        root_blockers = normalized_root_blocker_entries(blockers_payload.get("blockers"))
    root_blocker_ids = normalized_string_list([entry.get("id") for entry in root_blockers])
    posture = next(
        (
            entry
            for entry in root_blockers
            if isinstance(entry, dict) and str(entry.get("id") or "").strip() == "release_posture:non_flagship_channel"
        ),
        {},
    )
    return {
        "root_blocker_ids": root_blocker_ids,
        "root_blockers": root_blockers,
        "root_blockers_generated_at": str(blockers_payload.get("generated_at") or "").strip(),
        "stable_promotion_command": str(posture.get("stable_promotion_command") or "").strip(),
        "post_promotion_verify_command": str(posture.get("post_promotion_verify_command") or "").strip(),
        "root_release_truth_source": str(RELEASE_BLOCKERS_JSON),
    }


def int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def auto_import_failure_fields(auto_import_payload: dict[str, object]) -> dict[str, object]:
    failure = auto_import_payload.get("import_failure")
    failure = dict(failure) if isinstance(failure, dict) else {}
    return {
        "auto_import_import_failure": failure,
        "auto_import_import_failure_type": str(failure.get("type") or "").strip(),
        "auto_import_import_failure_message": str(failure.get("message") or "").strip(),
        "auto_import_import_failure_code": failure.get("code") if failure else None,
        "auto_import_import_failure_summary": str(auto_import_payload.get("summary") or "").strip(),
    }


def flagship_product_readiness_expected_gate_verdict(status: object) -> str:
    return (
        FLAGSHIP_PRODUCT_READY_VERDICT
        if normalized_token(status) in PASS_STATES
        else FLAGSHIP_PRODUCT_NOT_READY_VERDICT
    )


def flagship_product_readiness_gate_semantic_failures(payload: dict[str, object]) -> list[str]:
    if str(payload.get("contract_name") or "").strip() != FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME:
        return []
    expected_verdict = flagship_product_readiness_expected_gate_verdict(payload.get("status"))
    actual_verdict = str(payload.get("verdict") or "").strip()
    if actual_verdict == expected_verdict:
        return []
    return [f"flagship_product_readiness gate has unexpected verdict (expected {expected_verdict})"]


def flagship_product_readiness_gate_structural_green(summary: dict[str, object]) -> bool:
    if str(summary.get("contract_name") or "").strip() != "fleet.flagship_product_readiness":
        return False
    if normalized_token(summary.get("status")) != "fail" or summary.get("pass") is not False:
        return False
    if int_value(summary.get("missing_count")) != 0:
        return False
    if int_value(summary.get("scoped_missing_count")) != 0:
        return False
    if normalized_string_list(summary.get("coverage_gap_keys")):
        return False
    if normalized_string_list(summary.get("scoped_coverage_gap_keys")):
        return False
    if flagship_product_readiness_gate_semantic_failures(
        {
            "contract_name": FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME,
            "status": summary.get("status"),
            "verdict": summary.get("verdict"),
        }
    ):
        return False

    completion_status = normalized_token(summary.get("completion_audit_status"))
    readiness_status = normalized_token(summary.get("flagship_readiness_audit_status"))
    return completion_status in PASS_STATES and readiness_status in PASS_STATES


def flagship_product_readiness_recoverable(payload: dict[str, object]) -> bool:
    if str(payload.get("contract_name") or "").strip() != FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME:
        return False
    if normalized_token(payload.get("status")) != "fail" or payload.get("pass") is not False:
        return False
    if flagship_product_readiness_gate_semantic_failures(payload):
        return False
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return False
    blockers = normalized_string_list(summary.get("launch_critical_nested_blockers"))
    if not blockers or any(
        not is_recoverable_flagship_product_readiness_blocker(blocker)
        for blocker in blockers
    ):
        return False
    summary = dict(summary)
    nested_status = normalized_token(summary.get("status"))
    if nested_status and nested_status != normalized_token(payload.get("status")):
        return False
    nested_verdict = str(summary.get("verdict") or "").strip()
    if nested_verdict and nested_verdict != str(payload.get("verdict") or "").strip():
        return False
    summary["status"] = payload.get("status")
    summary["verdict"] = payload.get("verdict")
    return flagship_product_readiness_gate_structural_green(summary)


def is_recoverable_flagship_product_readiness_blocker(blocker: str) -> bool:
    candidate = str(blocker or "").strip()
    return candidate in FLAGSHIP_PRODUCT_READINESS_RECOVERABLE_LAUNCH_BLOCKERS


def current_release_channel_failures(payload: dict[str, object]) -> list[str]:
    failures: list[str] = []
    status = normalized_token(payload.get("status"))
    version = str(payload.get("version") or payload.get("releaseVersion") or "").strip()
    channel = str(payload.get("channel") or payload.get("channelId") or "").strip()
    normalized_channel = channel.lower()
    supportability_state = normalized_token(payload.get("supportabilityState"))
    rollout_state = normalized_token(payload.get("rolloutState"))
    if status != "published":
        failures.append("release channel status is not published")
    if not version:
        failures.append("release channel version is missing")
    if not channel:
        failures.append("release channel channel is missing")
    elif normalized_channel not in FLAGSHIP_STABLE_CHANNELS:
        failures.append(f"release channel channel is {normalized_channel}, not a flagship stable lane")
    if supportability_state != GOLD_SUPPORTABILITY_STATE:
        failures.append("release channel supportability is not gold_supported")
    if rollout_state in BLOCKING_ROLLOUT_STATES:
        failures.append(f"release channel rollout is blocking: {rollout_state}")
    elif rollout_state and rollout_state != FLAGSHIP_PUBLIC_STABLE_ROLLOUT_STATE:
        failures.append(f"release channel rollout is {rollout_state}, not public_stable")
    return failures


def stable_release_publish_command(
    release_channel_payload: dict[str, object],
    windows_artifact: dict[str, object] | None = None,
) -> str:
    release_version = str(
        release_channel_payload.get("version")
        or release_channel_payload.get("releaseVersion")
        or ""
    ).strip()
    release_published_at = str(
        release_channel_payload.get("publishedAt")
        or release_channel_payload.get("generatedAt")
        or release_channel_payload.get("generated_at")
        or ""
    ).strip()

    bundle_dir = LIVE_DOWNLOADS_SHELF_DIR
    if isinstance(windows_artifact, dict):
        for key in ("stage_release_build_handoff_path", "stage_windows_visual_proof_handoff_path"):
            raw_path = str(windows_artifact.get(key) or "").strip()
            if raw_path:
                bundle_dir = Path(raw_path).parent
                break

    env_parts = ["RELEASE_CHANNEL=public_stable"]
    if release_version:
        env_parts.append(f"RELEASE_VERSION={shlex.quote(release_version)}")
    if release_published_at:
        env_parts.append(f"RELEASE_PUBLISHED_AT={shlex.quote(release_published_at)}")

    quoted_script = shlex.quote(str(STABLE_PUBLISH_SCRIPT))
    quoted_bundle_dir = shlex.quote(str(bundle_dir))
    return " ".join(
        [
            *env_parts,
            "bash",
            quoted_script,
            quoted_bundle_dir,
            quoted_bundle_dir,
        ]
    )


def stable_release_post_publish_verify_command() -> str:
    return " && ".join(
        [
            "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier",
            "python3 scripts/materialize_operator_release_dashboard.py",
            "python3 scripts/final_gold_janitor.py",
            "python3 ../scripts/release/_release_gate_common.py",
            "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\"",
        ]
    )


def flagship_product_readiness_coverage_gap_reasons(
    payload: dict[str, object],
) -> list[str]:
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    if (
        str(payload.get("contract_name") or "").strip()
        != FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME
        and str(summary.get("contract_name") or "").strip()
        != "fleet.flagship_product_readiness"
    ):
        return []

    reasons: list[str] = []
    seen: set[str] = set()
    for source in (payload, summary):
        for field in ("coverage_gap_keys", "scoped_coverage_gap_keys"):
            for gap_key in normalized_string_list(source.get(field)):
                if gap_key in seen:
                    continue
                seen.add(gap_key)
                reasons.append(f"flagship readiness coverage gap remains: {gap_key}")
    return reasons


def receipt_failure_reasons(payload: dict[str, object], fallback: str) -> list[str]:
    coverage_gap_reasons = flagship_product_readiness_coverage_gap_reasons(payload)

    def with_coverage_gaps(reasons: list[str]) -> list[str]:
        combined: list[str] = []
        seen: set[str] = set()
        for reason in [*reasons, *coverage_gap_reasons]:
            if reason in seen:
                continue
            seen.add(reason)
            combined.append(reason)
        return combined

    failures = payload.get("failures")
    if isinstance(failures, list):
        cleaned = [str(item).strip() for item in failures if str(item).strip()]
        if cleaned:
            return with_coverage_gaps(cleaned)
    blockers = payload.get("blockers")
    if isinstance(blockers, list):
        cleaned = [str(item).strip() for item in blockers if str(item).strip()]
        if cleaned:
            return with_coverage_gaps(cleaned)
    failed_gates = payload.get("failed_gates")
    if isinstance(failed_gates, list):
        cleaned = [str(item).strip() for item in failed_gates if str(item).strip()]
        if cleaned:
            return with_coverage_gaps(cleaned)
    next_actions = payload.get("nextActions") or payload.get("next_actions")
    if isinstance(next_actions, list):
        cleaned = [str(item).strip() for item in next_actions if str(item).strip()]
        if cleaned:
            return with_coverage_gaps(cleaned)
    summary = payload.get("summary")
    if isinstance(summary, dict):
        nested = summary.get("launch_critical_nested_blockers")
        if isinstance(nested, list):
            cleaned = [str(item).strip() for item in nested if str(item).strip()]
            if cleaned:
                return with_coverage_gaps(cleaned)
        reason = str(summary.get("reason") or "").strip()
        if reason:
            return with_coverage_gaps([reason])
    if coverage_gap_reasons:
        return coverage_gap_reasons
    return [fallback]


def normalized_sha(value: object) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def windows_visual_audit_intake_request_path(published_root: Path | None = None) -> Path:
    return (published_root or PUBLISHED_ROOT) / WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST_NAME


def windows_visual_audit_auto_import_path(published_root: Path | None = None) -> Path:
    return (published_root or PUBLISHED_ROOT) / WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT_NAME


def portal_downloads_root(run_services_root: Path | None = None) -> Path:
    return (run_services_root or RUN_SERVICES_ROOT) / "Chummer.Portal" / "downloads"


def current_windows_stage_handoff_artifacts() -> dict[str, object]:
    downloads_root = portal_downloads_root()
    release_build_handoff_path = downloads_root / "RELEASE_BUILD_HANDOFF.generated.json"
    visual_proof_handoff_path = downloads_root / "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"

    artifacts: dict[str, object] = {
        "stage_release_build_handoff_path": str(release_build_handoff_path),
        "stage_release_build_handoff_exists": release_build_handoff_path.is_file(),
        "stage_windows_visual_proof_handoff_path": str(visual_proof_handoff_path),
        "stage_windows_visual_proof_handoff_exists": visual_proof_handoff_path.is_file(),
    }

    if release_build_handoff_path.is_file():
        payload = load_json(release_build_handoff_path)
        artifacts["stage_release_build_handoff_status"] = "pass" if bool(payload.get("stage_proof_complete")) else "fail"
        artifacts["stage_release_build_handoff_generated_at"] = str(payload.get("generated_at") or "").strip()
        artifacts["stage_release_build_handoff_stage_dir"] = str(payload.get("stage_dir") or "").strip()
        artifacts["stage_release_build_handoff_blockers"] = normalized_string_list(payload.get("blockers"))
        windows_exit_gate_refresh = (
            payload.get("windows_exit_gate_refresh")
            if isinstance(payload.get("windows_exit_gate_refresh"), dict)
            else {}
        )
        artifacts["stage_windows_exit_gate_refresh_status"] = str(
            windows_exit_gate_refresh.get("status") or ""
        ).strip()
        artifacts["stage_windows_exit_gate_refresh_path"] = str(
            windows_exit_gate_refresh.get("json_path") or ""
        ).strip()
        artifacts["stage_windows_exit_gate_refresh_blocking_mode"] = str(
            windows_exit_gate_refresh.get("blocking_mode") or ""
        ).strip()

    if visual_proof_handoff_path.is_file():
        payload = load_json(visual_proof_handoff_path)
        artifacts["stage_windows_visual_proof_handoff_status"] = str(payload.get("status") or "").strip()
        artifacts["stage_windows_visual_proof_handoff_summary"] = str(payload.get("summary") or "").strip()
        artifacts["stage_windows_visual_proof_handoff_visual_proof_path"] = str(
            payload.get("visual_proof_path") or ""
        ).strip()
        artifacts["stage_windows_visual_proof_handoff_next_actions"] = normalized_string_list(
            payload.get("next_actions")
        )
        artifact_intake = (
            payload.get("operator_artifact_intake")
            if isinstance(payload.get("operator_artifact_intake"), dict)
            else {}
        )
        artifacts["stage_windows_visual_proof_preferred_drop_root"] = str(
            artifact_intake.get("preferred_drop_root") or ""
        ).strip()
        artifacts["stage_windows_visual_proof_preferred_receipt_path"] = str(
            artifact_intake.get("preferred_visual_proof_receipt_path") or ""
        ).strip()
        artifacts["stage_windows_visual_proof_preferred_screenshot_dir"] = str(
            artifact_intake.get("preferred_screenshot_dir") or ""
        ).strip()
        artifacts["stage_windows_visual_proof_post_copy_verify_command"] = str(
            artifact_intake.get("post_copy_verify_command") or ""
        ).strip()

    return artifacts


def current_blocking_gate_artifacts(*, refresh_windows_runtime_receipts: bool = True) -> dict[str, dict[str, object]]:
    artifacts: dict[str, dict[str, object]] = {}
    root_context = current_release_truth_root_context()
    artifacts["release_truth_root"] = root_context
    public_edge_root_blocker = next(
        (
            entry
            for entry in root_context.get("root_blockers", [])
            if isinstance(entry, dict)
            and str(entry.get("id") or entry.get("blocker_id") or "").strip()
            == "release_truth:public_edge_postdeploy_gate"
        ),
        {},
    )
    if (
        isinstance(public_edge_root_blocker, dict)
        and str(public_edge_root_blocker.get("blocker_class") or "").strip()
        == "deployment_activation_proof_required"
    ):
        artifacts["public_edge_postdeploy_gate"] = {
            "status": "fail",
            "pass": False,
            "blocker_class": "deployment_activation_proof_required",
            "local_surface_regression": False,
            "deployment_activation_proof_required": True,
            "activation_authority_required": bool(
                public_edge_root_blocker.get("activation_authority_required")
            ),
            "post_activation_proof_required": bool(
                public_edge_root_blocker.get("post_activation_proof_required")
            ),
            "active_root": str(public_edge_root_blocker.get("runtime_overlay_root") or "").strip(),
            "staging_root": str(public_edge_root_blocker.get("staged_overlay_root") or "").strip(),
            "staged_overlay_receipt_path": str(
                public_edge_root_blocker.get("staged_overlay_receipt_path") or ""
            ).strip(),
            "staged_overlay_status": str(public_edge_root_blocker.get("staged_overlay_status") or "").strip(),
            "activation_transaction_journal_path": str(
                public_edge_root_blocker.get("activation_transaction_journal_path") or ""
            ).strip(),
            "activation_transaction_journal_exists": public_edge_root_blocker.get(
                "activation_transaction_journal_exists"
            ),
            "external_prerequisite": str(
                public_edge_root_blocker.get("external_prerequisite") or ""
            ).strip(),
            "verify_command": str(public_edge_root_blocker.get("verify_command") or "").strip(),
        }
    for gate, path in CURRENT_AUXILIARY_RELEASE_RECEIPTS:
        payload, load_status = load_json_with_status(path)
        artifacts[gate] = {
            **receipt_state(path, payload, load_status),
            "failures": normalized_string_list(payload.get("failures")),
            "blockers": normalized_string_list(payload.get("blockers")),
            "next_actions": normalized_string_list(
                payload.get("next_actions") or payload.get("nextActions")
            ),
            "operator_dependencies": normalized_string_list(
                payload.get("operator_dependencies")
            ),
        }

    snapshot_audit_payload, snapshot_audit_load_status = load_json_with_status(
        PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT
    )
    if snapshot_audit_load_status == "loaded":
        snapshot_audit_status = receipt_status_fields(
            PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT,
            snapshot_audit_payload,
            snapshot_audit_load_status,
        )
        artifacts["public_release_snapshot_readonly_audit"] = {
            "path": str(PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT),
            "exists": PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.is_file(),
            "load_status": snapshot_audit_load_status,
            **snapshot_audit_status,
            "verdict": str(snapshot_audit_payload.get("verdict") or "").strip(),
            "generated_at_utc": str(
                snapshot_audit_payload.get("generated_at_utc")
                or snapshot_audit_payload.get("generatedAtUtc")
                or snapshot_audit_payload.get("generatedAt")
                or snapshot_audit_payload.get("generated_at")
                or ""
            ).strip(),
            "pass": normalized_token(snapshot_audit_status.get("status")) in PASS_STATES,
            "summary": str(snapshot_audit_payload.get("summary") or "").strip(),
            "expected_top_level_blocker_ids": normalized_string_list(
                snapshot_audit_payload.get("expected_top_level_blocker_ids")
            ),
            "expected_release_truth_blockers": normalized_string_list(
                snapshot_audit_payload.get("expected_release_truth_blockers")
            ),
        }

    google_proof_path = PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
    google_payload = load_json(google_proof_path)
    google_request_artifacts = (
        google_payload.get("operator_request_artifacts")
        if isinstance(google_payload.get("operator_request_artifacts"), dict)
        else {}
    )
    if google_request_artifacts:
        artifacts["google_oauth_linking_proof"] = enrich_operator_ask_delivery_state(dict(google_request_artifacts))
        artifacts["google_oauth_linking_proof"]["next_actions"] = normalized_string_list(
            google_payload.get("nextActions") or google_payload.get("next_actions")
        )
        try:
            _ok, verifier = verify_google_oauth_linking_proof_receipt(google_proof_path, require_pass=False)
            verifier = dict(verifier) if isinstance(verifier, dict) else {}
        except Exception as exc:
            verifier = {
                "status": "fail",
                "issues": [f"google_oauth_linking_proof_verifier_failed:{type(exc).__name__}"],
                "path": str(google_proof_path),
                "require_pass": False,
            }
        request_artifacts_pass = bool(artifacts["google_oauth_linking_proof"].get("pass"))
        request_status = str(artifacts["google_oauth_linking_proof"].get("request_status") or "").strip()
        request_effective_status = str(
            artifacts["google_oauth_linking_proof"].get("request_effective_status")
            or request_status
            or ""
        ).strip()
        operator_evidence_pass = bool(verifier.get("operator_evidence_pass"))
        if not request_effective_status:
            request_effective_status = "not_required" if operator_evidence_pass else "operator_action_required"
        operator_action_still_required = request_effective_status == "operator_action_required"
        artifacts["google_oauth_linking_proof"]["proof_verifier_status"] = str(verifier.get("status") or "").strip()
        artifacts["google_oauth_linking_proof"]["proof_verifier_issues"] = normalized_string_list(verifier.get("issues"))
        artifacts["google_oauth_linking_proof"]["proof_operator_request_artifacts_pass"] = bool(
            verifier.get("operator_request_artifacts_pass")
        )
        artifacts["google_oauth_linking_proof"]["request_artifacts_pass"] = request_artifacts_pass
        artifacts["google_oauth_linking_proof"]["proof_operator_request_effective_status"] = request_effective_status
        artifacts["google_oauth_linking_proof"]["proof_operator_action_still_required"] = operator_action_still_required
        artifacts["google_oauth_linking_proof"]["proof_operator_evidence_pass"] = operator_evidence_pass
        artifacts["google_oauth_linking_proof"]["release_truth_effective_pass"] = google_oauth_release_truth_effective_pass(
            google_payload
        )
        artifacts["google_oauth_linking_proof"]["pass"] = (
            request_artifacts_pass
            and not operator_action_still_required
            and operator_evidence_pass
            and artifacts["google_oauth_linking_proof"]["proof_verifier_status"] == "pass"
        )
        failures = normalized_string_list(artifacts["google_oauth_linking_proof"].get("failures"))
        required_operator_evidence_path = str(
            artifacts["google_oauth_linking_proof"].get("required_operator_evidence_path") or ""
        ).strip()
        if operator_action_still_required:
            failure = (
                f"operator action still required until Google OAuth operator evidence exists: {required_operator_evidence_path}"
                if required_operator_evidence_path
                else "operator action still required until Google OAuth operator evidence exists"
            )
            if failure not in failures:
                failures.append(failure)
        if not operator_evidence_pass:
            failure = (
                f"google oauth operator evidence is not pass: {required_operator_evidence_path}"
                if required_operator_evidence_path
                else "google oauth operator evidence is not pass"
            )
            if failure not in failures:
                failures.append(failure)
        verifier_status = artifacts["google_oauth_linking_proof"]["proof_verifier_status"]
        if verifier_status != "pass":
            failure = f"google oauth proof verifier status is {verifier_status or 'missing'}"
            if failure not in failures:
                failures.append(failure)
        artifacts["google_oauth_linking_proof"]["failures"] = failures

    windows_request_path = windows_visual_audit_intake_request_path()
    windows_request_payload = load_json(windows_request_path)
    windows_visual_audit_payload = load_json(PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json")
    if windows_request_path.is_file() and windows_request_payload:
        operator_draft = (
            windows_request_payload.get("operator_telegram_draft")
            if isinstance(windows_request_payload.get("operator_telegram_draft"), dict)
            else {}
        )
        artifact_intake = (
            windows_request_payload.get("artifact_intake")
            if isinstance(windows_request_payload.get("artifact_intake"), dict)
            else {}
        )
        watcher_launch_mode = str(artifact_intake.get("watcher_launch_mode") or "").strip()
        watcher_state_path = str(artifact_intake.get("watcher_state_path") or "").strip()
        watcher_pid_file = str(artifact_intake.get("watcher_pid_file") or "").strip()
        watcher_log_path = str(artifact_intake.get("watcher_log_path") or "").strip()
        watcher_start_command = str(artifact_intake.get("watcher_start_command") or "").strip()
        watcher_status_command = str(artifact_intake.get("watcher_status_command") or "").strip()
        watcher_stop_command = str(artifact_intake.get("watcher_stop_command") or "").strip()
        watcher_path = Path(watcher_state_path) if watcher_state_path else DEFAULT_WINDOWS_WATCHER_STATE
        auto_import_path = windows_visual_audit_auto_import_path(windows_request_path.parent)
        if refresh_windows_runtime_receipts:
            auto_import_payload, auto_import_load_status = refresh_auto_import_state(
                str(artifact_intake.get("auto_import_command") or "").strip(),
                auto_import_path,
            )
            watcher_state = refresh_watcher_state(watcher_status_command, watcher_path)
        else:
            auto_import_payload, auto_import_load_status = load_json_with_status(auto_import_path)
            watcher_state = watcher_state_details(watcher_path)
        operator_ask_receipt_name = str(operator_draft.get("receipt_name") or "").strip()
        delivery_receipt = telegram_delivery_receipt_details(operator_ask_receipt_name)
        artifacts["windows_installer_visual_audit"] = enrich_operator_ask_delivery_state({
            "request_receipt_path": str(windows_request_path),
            "request_receipt_exists": windows_request_path.is_file(),
            "operator_ask_text_path": str(
                operator_draft.get("current_message_path")
                or operator_draft.get("message_path")
                or ""
            ).strip(),
            "operator_ask_text_exists": path_exists(
                operator_draft.get("current_message_path")
                or operator_draft.get("message_path")
                or ""
            ),
            "operator_ask_metadata_path": str(
                operator_draft.get("current_metadata_path")
                or operator_draft.get("metadata_path")
                or ""
            ).strip(),
            "operator_ask_metadata_exists": path_exists(
                operator_draft.get("current_metadata_path")
                or operator_draft.get("metadata_path")
                or ""
            ),
            "operator_ask_send_command": str(operator_draft.get("send_command") or "").strip(),
            "operator_ask_receipt_name": operator_ask_receipt_name,
            "operator_ask_message_preview": str(operator_draft.get("message_preview") or "").strip(),
            "operator_ask_message_sha256": text_sha256(
                operator_draft.get("current_message_path")
                or operator_draft.get("message_path")
                or ""
            ),
            "preferred_drop_path": str(
                windows_request_payload.get("preferred_drop_path")
                or operator_draft.get("preferred_drop_path")
                or ""
            ).strip(),
            "preferred_drop_path_exists": path_exists(
                windows_request_payload.get("preferred_drop_path")
                or operator_draft.get("preferred_drop_path")
                or ""
            ),
            "preferred_zip_name": str(
                windows_request_payload.get("preferred_zip_name")
                or operator_draft.get("preferred_zip_name")
                or ""
            ).strip(),
            "required_zip_filename": str(
                windows_request_payload.get("required_zip_filename")
                or operator_draft.get("required_zip_filename")
                or ""
            ).strip(),
            "preferred_extracted_visual_dir": str(
                windows_request_payload.get("preferred_extracted_visual_dir")
                or artifact_intake.get("preferred_extracted_visual_dir")
                or operator_draft.get("preferred_extracted_visual_dir")
                or ""
            ).strip(),
            "preferred_extracted_visual_dir_exists": path_exists(
                windows_request_payload.get("preferred_extracted_visual_dir")
                or artifact_intake.get("preferred_extracted_visual_dir")
                or operator_draft.get("preferred_extracted_visual_dir")
                or ""
            ),
            "discover_command": str(artifact_intake.get("discover_command") or "").strip(),
            "discover_visual_source_command": str(
                artifact_intake.get("discover_visual_source_command")
                or operator_draft.get("discover_visual_source_command")
                or ""
            ).strip(),
            "import_command": str(artifact_intake.get("import_command") or "").strip(),
            "auto_import_command": str(artifact_intake.get("auto_import_command") or "").strip(),
            "auto_import_watch_command": str(artifact_intake.get("auto_import_watch_command") or "").strip(),
            "watcher_launch_mode": watcher_launch_mode,
            "watcher_state_path": watcher_state_path,
            "watcher_pid_file": watcher_pid_file,
            "watcher_log_path": watcher_log_path,
            "watcher_start_command": watcher_start_command,
            "watcher_status_command": watcher_status_command,
            "watcher_stop_command": watcher_stop_command,
            **watcher_state,
            "post_import_verify_command": str(artifact_intake.get("post_import_verify_command") or "").strip(),
            "post_import_verify_note": str(artifact_intake.get("post_import_verify_note") or "").strip(),
            "expected_artifact_patterns": list(windows_request_payload.get("expected_artifact_patterns"))
            if isinstance(windows_request_payload.get("expected_artifact_patterns"), list)
            else [],
            "drop_roots_checked": list(windows_request_payload.get("drop_roots_checked"))
            if isinstance(windows_request_payload.get("drop_roots_checked"), list)
            else [],
            "promoted_installer_sha256": str(
                windows_request_payload.get("promoted_installer_sha256")
                or operator_draft.get("promoted_installer_sha256")
                or ""
            ).strip(),
            "auto_import_receipt_path": str(auto_import_path),
            **delivery_receipt,
        })
        artifacts["windows_installer_visual_audit"].update(
            {
                "auto_import_receipt_exists": auto_import_path.is_file(),
                "auto_import_receipt_load_status": auto_import_load_status,
                "auto_import_receipt_status": str(auto_import_payload.get("status") or "").strip(),
                "auto_import_receipt_generated_at_utc": str(auto_import_payload.get("generated_at_utc") or "").strip(),
                "auto_import_artifact": str(auto_import_payload.get("artifact") or "").strip(),
                **auto_import_failure_fields(auto_import_payload),
                "auto_import_actionable_candidate_count": int_value(auto_import_payload.get("actionable_candidate_count")),
                "auto_import_matching_promoted_directory_candidate_count": int_value(
                    auto_import_payload.get("matching_promoted_directory_candidate_count")
                ),
                "auto_import_matching_promoted_zip_candidate_count": int_value(
                    auto_import_payload.get("matching_promoted_zip_candidate_count")
                ),
                "auto_import_stale_directory_candidate_count": int_value(
                    auto_import_payload.get("stale_directory_candidate_count")
                ),
                "auto_import_stage_like_stale_directory_candidate_count": int_value(
                    auto_import_payload.get("stage_like_stale_directory_candidate_count")
                ),
                "auto_import_stage_visual_proof_receipt_count": int_value(
                    auto_import_payload.get("stage_visual_proof_receipt_count")
                ),
                "auto_import_matching_promoted_stage_visual_proof_receipt_count": int_value(
                    auto_import_payload.get("matching_promoted_stage_visual_proof_receipt_count")
                ),
                "auto_import_stale_stage_visual_proof_receipt_count": int_value(
                    auto_import_payload.get("stale_stage_visual_proof_receipt_count")
                ),
                "auto_import_suppressed_stale_stage_visual_proof_receipt_count": int_value(
                    auto_import_payload.get("suppressed_stale_stage_visual_proof_receipt_count")
                ),
                "auto_import_stage_startup_smoke_receipt_count": int_value(
                    auto_import_payload.get("stage_startup_smoke_receipt_count")
                ),
                "auto_import_matching_promoted_stage_startup_smoke_receipt_count": int_value(
                    auto_import_payload.get("matching_promoted_stage_startup_smoke_receipt_count")
                ),
                "auto_import_stale_stage_startup_smoke_receipt_count": int_value(
                    auto_import_payload.get("stale_stage_startup_smoke_receipt_count")
                ),
                "auto_import_suppressed_stale_stage_startup_smoke_receipt_count": int_value(
                    auto_import_payload.get("suppressed_stale_stage_startup_smoke_receipt_count")
                ),
                "auto_import_stale_directory_digest_summary": list(
                    auto_import_payload.get("stale_directory_digest_summary")
                ) if isinstance(auto_import_payload.get("stale_directory_digest_summary"), list) else [],
                "auto_import_matching_promoted_stage_visual_proof_receipts": list(
                    auto_import_payload.get("matching_promoted_stage_visual_proof_receipts")
                ) if isinstance(auto_import_payload.get("matching_promoted_stage_visual_proof_receipts"), list) else [],
                "auto_import_stale_stage_visual_proof_receipts": list(
                    auto_import_payload.get("stale_stage_visual_proof_receipts")
                ) if isinstance(auto_import_payload.get("stale_stage_visual_proof_receipts"), list) else [],
                "auto_import_matching_promoted_stage_startup_smoke_receipts": list(
                    auto_import_payload.get("matching_promoted_stage_startup_smoke_receipts")
                ) if isinstance(auto_import_payload.get("matching_promoted_stage_startup_smoke_receipts"), list) else [],
                "auto_import_stale_stage_startup_smoke_receipts": list(
                    auto_import_payload.get("stale_stage_startup_smoke_receipts")
                ) if isinstance(auto_import_payload.get("stale_stage_startup_smoke_receipts"), list) else [],
                "auto_import_stage_visual_proof_receipt_note": str(
                    auto_import_payload.get("stage_visual_proof_receipt_note") or ""
                ).strip(),
                "auto_import_stage_startup_smoke_receipt_note": str(
                    auto_import_payload.get("stage_startup_smoke_receipt_note") or ""
                ).strip(),
                "auto_import_directory_candidate_note": str(
                    auto_import_payload.get("directory_candidate_note") or ""
                ).strip(),
            }
        )
        try:
            _ok, verifier = verify_windows_visual_intake_request_receipt(windows_request_path, require_pass=False)
            verifier = dict(verifier) if isinstance(verifier, dict) else {}
        except Exception as exc:
            verifier = {
                "status": "fail",
                "issues": [f"windows_visual_audit_intake_request_verifier_failed:{type(exc).__name__}"],
                "path": str(windows_request_path),
                "require_pass": False,
                "operator_action_still_required": False,
                "recovery_pack_pass": False,
            }
        artifacts["windows_installer_visual_audit"]["request_verifier_status"] = str(
            verifier.get("status") or ""
        ).strip()
        artifacts["windows_installer_visual_audit"]["request_verifier_issues"] = normalized_string_list(
            verifier.get("issues")
        )
        artifacts["windows_installer_visual_audit"]["request_recovery_pack_pass"] = bool(
            verifier.get("recovery_pack_pass")
        )
        artifacts["windows_installer_visual_audit"]["request_operator_action_still_required"] = bool(
            verifier.get("operator_action_still_required")
        )
        artifacts["windows_installer_visual_audit"]["next_actions"] = normalized_string_list(
            windows_visual_audit_payload.get("nextActions") or windows_visual_audit_payload.get("next_actions")
        )
        windows_failures = normalized_string_list(artifacts["windows_installer_visual_audit"].get("failures"))
        artifacts["windows_installer_visual_audit"]["failures"] = windows_failures
        artifacts["windows_installer_visual_audit"].update(current_windows_stage_handoff_artifacts())

    return {key: value for key, value in artifacts.items() if value}


def append_unique_action(target: list[str], seen: set[str], action: object) -> None:
    text = str(action or "").strip()
    if not text or text in seen:
        return
    seen.add(text)
    target.append(text)


def apply_release_ready_actions(payload: dict[str, object], actions: list[str]) -> None:
    normalized_actions = normalized_string_list(actions)
    if str(payload.get("status") or "").strip().lower() == "pass":
        payload["nextActions"] = []
        payload["advisoryActions"] = normalized_actions
        return
    payload["nextActions"] = normalized_actions
    payload["advisoryActions"] = []


def windows_stage_visual_proof_hint_paths(artifact: dict[str, object], *, limit: int = 2) -> list[str]:
    sample_paths: list[str] = []
    for key in (
        "auto_import_matching_promoted_stage_visual_proof_receipts",
        "auto_import_stale_stage_visual_proof_receipts",
        "auto_import_matching_promoted_stage_startup_smoke_receipts",
        "auto_import_stale_stage_startup_smoke_receipts",
    ):
        rows = artifact.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            path_text = str(row.get("path") or "").strip()
            if path_text and path_text not in sample_paths:
                sample_paths.append(path_text)
            if len(sample_paths) >= limit:
                return sample_paths
    return sample_paths


def windows_stage_visual_proof_hint_action(artifact: dict[str, object]) -> str | None:
    if not artifact or not bool(artifact.get("request_operator_action_still_required")):
        return None
    receipt_count = int_value(artifact.get("auto_import_stage_visual_proof_receipt_count"))
    note = str(artifact.get("auto_import_stage_visual_proof_receipt_note") or "").strip()
    startup_receipt_count = int_value(artifact.get("auto_import_stage_startup_smoke_receipt_count"))
    startup_note = str(artifact.get("auto_import_stage_startup_smoke_receipt_note") or "").strip()
    if receipt_count <= 0 and startup_receipt_count <= 0 and not note and not startup_note:
        return None

    receipt_path = str(artifact.get("auto_import_receipt_path") or "").strip()
    location = receipt_path or "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
    visual_summary = f"visual-proof receipts={receipt_count}"
    startup_summary = f"startup-smoke receipts={startup_receipt_count}"
    summary = (
        f"Review surfaced Windows stage/nightly proof hints in {location}; "
        f"{visual_summary}, {startup_summary}. "
        "Use them only to locate old capture output for recapture or bundle packaging."
    )
    if note:
        summary = f"{summary} {note}"
    if startup_note:
        summary = f"{summary} {startup_note}"
    return summary


def release_ready_next_actions(
    blocking_gate_artifacts: dict[str, dict[str, object]],
    release_channel_payload: dict[str, object] | None = None,
    root_context: dict[str, object] | None = None,
) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()

    google = blocking_gate_artifacts.get("google_oauth_linking_proof")
    google = google if isinstance(google, dict) else {}
    google_effective_pass = bool(google.get("release_truth_effective_pass"))
    google_requires_followup = bool(
        google
        and not google_effective_pass
        and (
            google.get("proof_operator_action_still_required")
            or not google.get("pass", False)
        )
    )
    google_nested_actions = normalized_string_list(google.get("next_actions"))
    google_resend = str(google.get("operator_ask_resend_command") or "").strip()
    google_resend_already_listed = bool(
        google_resend and any(google_resend in action for action in google_nested_actions)
    )
    if (
        google_requires_followup
        and google.get("operator_ask_delivery_needs_resend")
        and google_resend
        and not google_resend_already_listed
    ):
        append_unique_action(actions, seen, f"Resend the current Google OAuth operator ask: {google_resend}")
    google_import = str(google.get("import_command") or "").strip()
    if google_requires_followup and google_import:
        append_unique_action(actions, seen, f"When the Google OAuth evidence bundle is ready, import it: {google_import}")
        append_unique_action(
            actions,
            seen,
            "That --verify import reruns the full intake-request post-import gate chain, not just the first verifier.",
        )
    google_evidence_path = str(google.get("required_operator_evidence_path") or "").strip()
    if google_requires_followup and google_evidence_path:
        append_unique_action(actions, seen, f"Required Google OAuth operator evidence receipt: {google_evidence_path}")
    if google_requires_followup:
        for action in google_nested_actions:
            append_unique_action(actions, seen, action)

    windows = blocking_gate_artifacts.get("windows_installer_visual_audit")
    windows = windows if isinstance(windows, dict) else {}
    windows_requires_followup = bool(
        windows
        and (
            windows.get("request_operator_action_still_required")
            or not windows.get("pass", False)
        )
    )
    windows_nested_actions = normalized_string_list(windows.get("next_actions"))
    windows_resend = str(windows.get("operator_ask_resend_command") or "").strip()
    windows_resend_already_listed = bool(
        windows_resend and any(windows_resend in action for action in windows_nested_actions)
    )
    windows_send = str(windows.get("operator_ask_send_command") or "").strip()
    windows_send_already_listed = bool(
        windows_send and any(windows_send in action for action in windows_nested_actions)
    )
    windows_import = str(windows.get("import_command") or "").strip()
    windows_import_already_listed = bool(
        windows_import and any(windows_import in action for action in windows_nested_actions)
    )
    windows_stage_hint_already_listed = any(
        action.startswith("Review surfaced Windows stage/nightly proof hints in ")
        for action in windows_nested_actions
    )
    windows_stage_hint_paths_already_listed = any(
        action.startswith("Sample stale Windows proof hint paths: ")
        for action in windows_nested_actions
    )
    if (
        windows_requires_followup
        and windows.get("operator_ask_delivery_receipt_exists") is False
        and windows_send
        and not windows_send_already_listed
    ):
        append_unique_action(
            actions,
            seen,
            f"Send the prepared current Windows proof operator ask: {windows_send}",
        )
    if (
        windows_requires_followup
        and windows.get("operator_ask_delivery_needs_resend")
        and windows_resend
        and not windows_resend_already_listed
    ):
        append_unique_action(actions, seen, f"Resend the current Windows proof operator ask: {windows_resend}")
    if windows_requires_followup and windows_import and not windows_import_already_listed:
        append_unique_action(actions, seen, f"When the Windows gold proof bundle is ready, import it: {windows_import}")
        append_unique_action(
            actions,
            seen,
            "That --verify import reruns the full intake-request post-import gate chain, not just the first verifier.",
        )
    windows_stage_hint_action = windows_stage_visual_proof_hint_action(windows)
    if windows_requires_followup and windows_stage_hint_action and not windows_stage_hint_already_listed:
        append_unique_action(actions, seen, windows_stage_hint_action)
    windows_stage_hint_paths = windows_stage_visual_proof_hint_paths(windows)
    if windows_requires_followup and windows_stage_hint_paths and not windows_stage_hint_paths_already_listed:
        append_unique_action(
            actions,
            seen,
            "Sample stale Windows proof hint paths: " + "; ".join(windows_stage_hint_paths),
        )
    if windows_requires_followup:
        windows_stage_handoff_actions = normalized_string_list(
            windows.get("stage_windows_visual_proof_handoff_next_actions")
        )
        if not windows_nested_actions:
            for action in windows_stage_handoff_actions:
                append_unique_action(actions, seen, action)
        for action in windows_nested_actions:
            append_unique_action(actions, seen, action)

    for gate in ("supply_chain_evidence", "public_edge_observability_release"):
        artifact = blocking_gate_artifacts.get(gate)
        artifact = artifact if isinstance(artifact, dict) else {}
        if normalized_token(artifact.get("status")) in PASS_STATES:
            continue
        for field in ("next_actions", "operator_dependencies"):
            for action in normalized_string_list(artifact.get(field)):
                append_unique_action(actions, seen, action)

    public_edge = blocking_gate_artifacts.get("public_edge_postdeploy_gate")
    public_edge = public_edge if isinstance(public_edge, dict) else {}
    if str(public_edge.get("blocker_class") or "").strip() == "deployment_activation_proof_required":
        append_unique_action(
            actions,
            seen,
            (
                "Obtain explicit public-edge activation authority, perform the governed atomic activation, "
                "then capture a clean mounted-overlay preflight and new live postdeploy proof; do not restamp "
                "the legacy active build receipt."
            ),
        )

    release_channel_payload = release_channel_payload if isinstance(release_channel_payload, dict) else {}
    root_context = root_context if isinstance(root_context, dict) else {}
    normalized_root_blocker_ids = {
        item.casefold()
        for item in normalized_string_list(root_context.get("root_blocker_ids"))
    }
    root_stable_promotion_command = str(root_context.get("stable_promotion_command") or "").strip()
    root_post_promotion_verify_command = str(root_context.get("post_promotion_verify_command") or "").strip()
    needs_release_posture_promotion = bool(current_release_channel_failures(release_channel_payload)) or (
        "release_posture:non_flagship_channel" in normalized_root_blocker_ids
    ) or bool(root_stable_promotion_command)
    if needs_release_posture_promotion:
        append_unique_action(
            actions,
            seen,
            "After the missing operator proofs are green, promote the live release channel to a public stable lane with gold_supported supportability.",
        )
        stable_publish = stable_release_publish_command(release_channel_payload, windows) or root_stable_promotion_command
        if stable_publish:
            append_unique_action(
                actions,
                seen,
                f"Stable promotion command: {stable_publish}",
            )
        if root_stable_promotion_command and root_stable_promotion_command != stable_publish:
            append_unique_action(
                actions,
                seen,
                f"Stable promotion wrapper command: {root_stable_promotion_command}",
            )
        append_unique_action(
            actions,
            seen,
            "After stable promotion, rerun the release blocker chain: "
            + (root_post_promotion_verify_command or stable_release_post_publish_verify_command()),
        )

    return actions


def windows_visual_audit_missing_artifact_failure(
    artifact: dict[str, object],
) -> str | None:
    if not artifact or not bool(artifact.get("request_operator_action_still_required")):
        return None

    preferred_drop_path = str(artifact.get("preferred_drop_path") or "").strip()
    if preferred_drop_path and not path_exists(preferred_drop_path):
        return f"windows installer gold proof artifact is still missing: {preferred_drop_path}"

    preferred_zip_name = str(
        artifact.get("preferred_zip_name")
        or artifact.get("required_zip_filename")
        or ""
    ).strip()
    if preferred_zip_name:
        return f"windows installer gold proof artifact is still missing: {preferred_zip_name}"
    return None


def windows_visual_audit_release_blocking_reasons(payload: dict[str, object]) -> list[str]:
    fallback = "windows_installer_visual_audit receipt is not pass"
    reasons = receipt_failure_reasons(payload, fallback)
    if normalized_token(payload.get("status")) in PASS_STATES and reasons == [fallback]:
        reasons = []
    artifact = payload.get("artifact")
    artifact = artifact if isinstance(artifact, dict) else {}
    visual = payload.get("visualAuditSource")
    visual = visual if isinstance(visual, dict) else {}

    promoted_digest = normalized_sha(artifact.get("sha256"))
    visual_digest = normalized_sha(visual.get("artifactSha256"))
    if (
        promoted_digest
        and len(promoted_digest) == 64
        and visual_digest
        and len(visual_digest) == 64
        and promoted_digest != visual_digest
    ):
        source_path = str(visual.get("path") or "").strip()
        detail = (
            "windows installer visual audit source still targets "
            f"{visual_digest} instead of promoted digest {promoted_digest}"
        )
        if source_path:
            detail = f"{detail}: {source_path}"
        if detail not in reasons:
            reasons.append(detail)
    return reasons


def public_edge_postdeploy_release_blocking_reasons(payload: dict[str, object]) -> list[str]:
    payload = normalize_public_edge_postdeploy_payload(payload)
    reasons = receipt_failure_reasons(payload, "public_edge_postdeploy_gate receipt is not pass")
    if normalized_token(payload.get("status")) in PASS_STATES and reasons == ["public_edge_postdeploy_gate receipt is not pass"]:
        reasons = []
    contract_name = str(payload.get("contractName") or payload.get("contract_name") or "").strip()
    status_is_pass = normalized_token(payload.get("status")) in PASS_STATES
    if status_is_pass and contract_name != PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME:
        reasons.append(
            "public_edge_postdeploy_gate receipt contract is not " + PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME
        )
    if status_is_pass and contract_name == PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME:
        missing_fields = sorted(
            field
            for field in PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS
            if field not in payload
        )
        if missing_fields:
            reasons.append("public_edge_postdeploy_gate receipt missing current fields: " + ", ".join(missing_fields))
        reasons.extend(public_edge_v2_artifact_contract_failures(payload))
        reasons.extend(public_edge_v2_offline_failures(payload))
        reasons.extend(public_edge_v2_private_identity_failures(payload))
    non_preflight = [
        reason
        for reason in reasons
        if reason.startswith("public_edge_postdeploy_gate receipt missing current fields:")
        or "preflight" not in reason.lower()
    ]
    if non_preflight:
        return non_preflight
    if int_value(payload.get("preflightBlockingLockCount")) != 0 or normalized_token(payload.get("preflightStatus")) == "fail":
        return []
    return reasons


def public_edge_observability_release_blocking_reasons(
    payload: dict[str, object],
    *,
    receipt_path: Path,
    release_channel_path: Path,
    now: datetime | None = None,
) -> list[str]:
    """Rebind a pass-shaped observability receipt to current local truth."""

    if normalized_token(payload.get("status")) not in PASS_STATES:
        return receipt_failure_reasons(
            payload,
            "public_edge_observability_release receipt is not pass",
        )

    reasons: list[str] = []
    if str(payload.get("contract_name") or "").strip() != PUBLIC_EDGE_OBSERVABILITY_GATE_CONTRACT_NAME:
        reasons.append(
            "public_edge_observability_release contract_name is not the current release-gate contract"
        )
    if str(payload.get("verdict") or "").strip() != PUBLIC_EDGE_OBSERVABILITY_READY_VERDICT:
        reasons.append(
            "public_edge_observability_release verdict is not OBSERVABILITY_RELEASE_READY"
        )
    if normalized_string_list(payload.get("failures")):
        reasons.append("public_edge_observability_release pass receipt records failures")
    if int_value(payload.get("failure_count")) != 0:
        reasons.append("public_edge_observability_release pass receipt has a nonzero failure_count")

    generated_at = parse_receipt_timestamp(payload.get("generated_at_utc"))
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    if generated_at is None:
        reasons.append(
            "public_edge_observability_release generated_at_utc is missing or is not offset-aware"
        )
    else:
        if generated_at > observed_at + PUBLIC_EDGE_OBSERVABILITY_GATE_FUTURE_SKEW:
            reasons.append("public_edge_observability_release generated_at_utc is in the future")
        if observed_at - generated_at > PUBLIC_EDGE_OBSERVABILITY_GATE_MAX_AGE:
            reasons.append("public_edge_observability_release receipt is stale")

    expected_release, _, _, release_failures = public_edge_observability_release_candidate_binding(
        release_channel_path
    )
    if release_failures:
        reasons.extend(
            f"current observability release candidate is invalid: {failure}"
            for failure in release_failures
        )
    recorded_release = payload.get("release_candidate")
    recorded_release = recorded_release if isinstance(recorded_release, dict) else {}
    for key in ("sha256", "version", "channel"):
        recorded = str(recorded_release.get(key) or "").strip()
        expected = str(expected_release.get(key) or "").strip()
        if not recorded or recorded != expected:
            reasons.append(
                f"public_edge_observability_release release_candidate.{key} does not match current release bytes"
            )

    required_check_ids = {
        "runtime:program",
        "runtime:readiness",
        "runtime:instruments",
        "runtime:middleware",
        "runtime:compose",
        "release_candidate",
        "policy",
        "operator_proof",
    }
    checks = payload.get("checks")
    recorded_checks: dict[str, str] = {}
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            check_id = str(check.get("id") or "").strip()
            if check_id:
                recorded_checks[check_id] = normalized_token(check.get("status"))
    if set(recorded_checks) != required_check_ids or any(
        recorded_checks.get(check_id) not in PASS_STATES for check_id in required_check_ids
    ):
        reasons.append(
            "public_edge_observability_release does not contain the complete passing check matrix"
        )

    if reasons:
        return list(dict.fromkeys(reasons))

    current_receipt = build_public_edge_observability_release_receipt(
        policy_path=RUN_SERVICES_ROOT / "ops" / "public-edge-observability-policy.json",
        operator_proof_path=(
            receipt_path.parent / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF.generated.json"
        ),
        release_channel_path=release_channel_path,
        runtime_sources=PUBLIC_EDGE_OBSERVABILITY_RUNTIME_SOURCES,
        now=observed_at,
    )
    if normalized_token(current_receipt.get("status")) not in PASS_STATES:
        current_failures = normalized_string_list(current_receipt.get("failures"))
        if current_failures:
            reasons.extend(
                f"current observability verification failed: {failure}"
                for failure in current_failures
            )
        else:
            reasons.append("current observability verification is not pass")
        return list(dict.fromkeys(reasons))

    comparisons = (
        ("policy.sha256", payload.get("policy"), current_receipt.get("policy"), "sha256"),
        (
            "runtime_source_binding.aggregate_sha256",
            payload.get("runtime_source_binding"),
            current_receipt.get("runtime_source_binding"),
            "aggregate_sha256",
        ),
        (
            "operator_proof.path",
            payload.get("operator_proof"),
            current_receipt.get("operator_proof"),
            "path",
        ),
        (
            "operator_proof.sha256",
            payload.get("operator_proof"),
            current_receipt.get("operator_proof"),
            "sha256",
        ),
        (
            "operator_proof.status",
            payload.get("operator_proof"),
            current_receipt.get("operator_proof"),
            "status",
        ),
        (
            "operator_proof.generated_at_utc",
            payload.get("operator_proof"),
            current_receipt.get("operator_proof"),
            "generated_at_utc",
        ),
    )
    for label, recorded_parent, current_parent, key in comparisons:
        recorded_parent = recorded_parent if isinstance(recorded_parent, dict) else {}
        current_parent = current_parent if isinstance(current_parent, dict) else {}
        if str(recorded_parent.get(key) or "").strip() != str(current_parent.get(key) or "").strip():
            reasons.append(
                f"public_edge_observability_release {label} does not match current verified bytes"
            )

    recorded_runtime = payload.get("runtime_source_binding")
    recorded_runtime = recorded_runtime if isinstance(recorded_runtime, dict) else {}
    current_runtime = current_receipt.get("runtime_source_binding")
    current_runtime = current_runtime if isinstance(current_runtime, dict) else {}
    if recorded_runtime.get("sources") != current_runtime.get("sources"):
        reasons.append(
            "public_edge_observability_release runtime source rows do not match current verified bytes"
        )
    return list(dict.fromkeys(reasons))


def public_edge_release_truth_runtime_override_reasons(
    snapshot_payload: dict[str, object],
    receipt_path: Path,
) -> list[str]:
    release_truth = snapshot_payload.get("release_truth")
    if not isinstance(release_truth, dict):
        return []
    state = release_truth.get("public_edge_postdeploy_gate")
    if not isinstance(state, dict) or state.get("runtime_override_applied") is not True:
        return []
    state_path = str(state.get("path") or "").strip()
    if state_path and Path(state_path).resolve() != receipt_path.resolve():
        return []

    runtime_observation = state.get("runtime_observation")
    runtime_observation = runtime_observation if isinstance(runtime_observation, dict) else {}
    reasons: list[str] = []
    verdict = str(state.get("verdict") or "").strip()
    if verdict:
        reasons.append(f"public_edge_postdeploy_gate release truth verdict is {verdict}")
    override_reason = str(
        state.get("runtime_override_reason")
        or runtime_observation.get("summary")
        or ""
    ).strip()
    if override_reason:
        reasons.append(override_reason)
    reasons.extend(normalized_string_list(runtime_observation.get("blocking_findings")))

    deduped: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        deduped.append(reason)
    return deduped


def collect_current_blocking_failures(*, refresh_windows_runtime_receipts: bool = True) -> list[str]:
    blockers: list[str] = []
    blocking_gate_artifacts = current_blocking_gate_artifacts(
        refresh_windows_runtime_receipts=refresh_windows_runtime_receipts
    )
    release_channel_path = REGISTRY_PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json"
    release_channel, release_channel_load_status = load_json_with_status(release_channel_path)
    public_release_snapshot = load_json(PUBLIC_RELEASE_SNAPSHOT)
    release_channel_load_failure = receipt_load_failure("release channel", release_channel_path, release_channel_load_status)
    if release_channel_load_failure:
        blockers.append(f"FAIL release_channel: {release_channel_load_failure}")
    else:
        release_channel_failures = current_release_channel_failures(release_channel)
        blockers.extend(f"FAIL release_channel: {failure}" for failure in release_channel_failures)
        workspace_portal_drift_failures = workspace_portal_release_channel_drift_failures(release_channel)
        blockers.extend(f"FAIL release_channel: {failure}" for failure in workspace_portal_drift_failures)

    current_receipts = {
        "flagship_product_readiness": PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json",
        "google_oauth_linking_proof": PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
        "public_edge_postdeploy_gate": PUBLISHED_ROOT / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json",
        "windows_installer_visual_audit": PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
    }
    current_receipts.update(dict(CURRENT_AUXILIARY_RELEASE_RECEIPTS))
    refresh_flagship_product_readiness_gate(current_receipts["flagship_product_readiness"])
    deferred_recoverable_flagship_blockers: list[str] = []
    for gate, path in current_receipts.items():
        payload, load_status = load_json_with_status(path)
        public_edge_runtime_override_reasons = (
            public_edge_release_truth_runtime_override_reasons(public_release_snapshot, path)
            if gate == "public_edge_postdeploy_gate"
            else []
        )
        public_edge_observability_reasons = (
            public_edge_observability_release_blocking_reasons(
                payload,
                receipt_path=path,
                release_channel_path=release_channel_path,
            )
            if gate == "public_edge_observability_release" and load_status == "loaded"
            else []
        )
        receipt_load_issue = receipt_load_failure(gate, path, load_status)
        if receipt_load_issue:
            reasons = [receipt_load_issue]
        else:
            google_oauth_reasons = (
                google_oauth_receipt_validation_failures(path)
                if gate == "google_oauth_linking_proof"
                else []
            )
            if (
                gate == "google_oauth_linking_proof"
                and not google_oauth_reasons
                and google_oauth_release_truth_effective_pass(payload)
            ):
                continue
            status = normalized_token(payload.get("status"))
            supply_chain_reasons = (
                supply_chain_receipt_validation_failures(payload)
                if gate == "supply_chain_evidence" and status in PASS_STATES
                else []
            )
            payload_failures = payload.get("failures")
            payload_failed_gates = payload.get("failed_gates")
            flagship_semantic_failures = (
                flagship_product_readiness_gate_semantic_failures(payload)
                if gate == "flagship_product_readiness"
                else []
            )
            has_failures = (
                (isinstance(payload_failures, list) and bool(payload_failures))
                or (isinstance(payload_failed_gates, list) and bool(payload_failed_gates))
                or bool(flagship_semantic_failures)
            )
            public_edge_receipt_reasons = (
                public_edge_postdeploy_release_blocking_reasons(payload)
                if gate == "public_edge_postdeploy_gate"
                else []
            )
            if not (
                public_edge_runtime_override_reasons
                or public_edge_observability_reasons
                or supply_chain_reasons
                or google_oauth_reasons
                or (gate == "public_edge_postdeploy_gate" and public_edge_receipt_reasons)
                or status not in {"pass", "passed", "ready"}
                or has_failures
            ):
                continue
            reasons = (
                public_edge_runtime_override_reasons
                or public_edge_receipt_reasons
                if gate == "public_edge_postdeploy_gate"
                else public_edge_observability_reasons
                if gate == "public_edge_observability_release"
                else supply_chain_reasons
                or receipt_failure_reasons(payload, f"{gate} receipt is not pass")
                if gate == "supply_chain_evidence"
                else google_oauth_reasons
                or receipt_failure_reasons(payload, f"{gate} receipt is not pass")
                if gate == "google_oauth_linking_proof"
                else windows_visual_audit_release_blocking_reasons(payload)
                if gate == "windows_installer_visual_audit"
                else [
                    *flagship_semantic_failures,
                    *[
                        reason
                        for reason in receipt_failure_reasons(payload, "")
                        if reason not in flagship_semantic_failures
                        and reason
                    ],
                ]
                if gate == "flagship_product_readiness" and flagship_semantic_failures
                else receipt_failure_reasons(payload, f"{gate} receipt is not pass")
            )
        if reasons:
            if gate == "windows_installer_visual_audit":
                missing_artifact_failure = windows_visual_audit_missing_artifact_failure(
                    blocking_gate_artifacts.get("windows_installer_visual_audit", {})
                )
                if missing_artifact_failure and missing_artifact_failure not in reasons:
                    reasons.append(missing_artifact_failure)
            gate_blockers = [f"FAIL {gate}: {reason}" for reason in reasons]
            if (
                gate == "flagship_product_readiness"
                and load_status == "loaded"
                and flagship_product_readiness_recoverable(payload)
            ):
                deferred_recoverable_flagship_blockers = gate_blockers
            elif gate_blockers:
                blockers.extend(gate_blockers)
    return blockers


def current_receipt_states() -> dict[str, dict[str, object]]:
    release_channel_path = REGISTRY_PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json"
    release_channel, release_channel_load_status = load_json_with_status(release_channel_path)
    receipt_paths = {
        "release_channel": release_channel_path,
        "flagship_product_readiness": PUBLISHED_ROOT / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json",
        "google_oauth_linking_proof": PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
        "public_edge_postdeploy_gate": PUBLISHED_ROOT / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json",
        "windows_installer_visual_audit": PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
    }
    receipt_paths.update(dict(CURRENT_AUXILIARY_RELEASE_RECEIPTS))
    refresh_flagship_product_readiness_gate(receipt_paths["flagship_product_readiness"])
    states = {
        "release_channel": receipt_state(release_channel_path, release_channel, release_channel_load_status),
    }
    for key, path in receipt_paths.items():
        if key == "release_channel":
            continue
        payload, load_status = load_json_with_status(path)
        state = receipt_state(path, payload, load_status)
        if key == "google_oauth_linking_proof" and load_status == "loaded":
            semantic_failures = google_oauth_receipt_validation_failures(path)
            if semantic_failures:
                state["raw_status"] = state["status"]
                state["status"] = "fail"
                state["semantic_failures"] = semantic_failures
        if (
            key == "supply_chain_evidence"
            and load_status == "loaded"
            and normalized_token(state.get("status")) in PASS_STATES
        ):
            semantic_failures = supply_chain_receipt_validation_failures(payload)
            if semantic_failures:
                state["raw_status"] = state["status"]
                state["status"] = "fail"
                state["semantic_failures"] = semantic_failures
        if key == "public_edge_observability_release" and load_status == "loaded":
            semantic_failures = public_edge_observability_release_blocking_reasons(
                payload,
                receipt_path=path,
                release_channel_path=release_channel_path,
            )
            if normalized_token(state.get("status")) in PASS_STATES and semantic_failures:
                state["raw_status"] = state["status"]
                state["status"] = "fail"
                state["semantic_failures"] = semantic_failures
        states[key] = state
    return states


def normalize_verdict_line(line: str) -> str:
    return " ".join(re.findall(r"[A-Za-z0-9]+", line.upper())).strip()


def verdict_markers(stdout: str, stderr: str) -> tuple[bool, list[str]]:
    saw_ready = False
    negative_lines: list[str] = []
    for line in [*stdout.splitlines(), *stderr.splitlines()]:
        normalized = normalize_verdict_line(line)
        if normalized == READY_MARKER:
            saw_ready = True
        if normalized == NOT_READY_MARKER:
            negative_lines.append(line.strip())
    return saw_ready, negative_lines


def gate_progress_markers(stdout: str, stderr: str) -> dict[str, object]:
    started_gates: list[str] = []
    completed_gates: list[str] = []
    for line in [*stdout.splitlines(), *stderr.splitlines()]:
        text = line.strip()
        if text.startswith("START "):
            gate = text.removeprefix("START ").strip().split(maxsplit=1)[0]
            if gate:
                started_gates.append(gate)
        elif text.startswith("PASS "):
            gate = text.removeprefix("PASS ").strip().split(maxsplit=1)[0]
            if gate:
                completed_gates.append(gate)
    return {
        "started_gates": started_gates,
        "completed_gates": completed_gates,
        "last_started_gate": started_gates[-1] if started_gates else "",
        "last_completed_gate": completed_gates[-1] if completed_gates else "",
    }


def canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """Publish JSON through a mode-0600 sibling and one atomic rename."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(json.dumps(payload, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def release_ready_materialization_failure_payload(
    *,
    phase: str,
    reason: str,
    returncode: int | None,
    timed_out: bool = False,
    proof_refresh_policy: dict[str, str] | None = None,
    command: str | None = None,
) -> dict[str, object]:
    """Build a current, explicitly non-authoritative receipt for producer failure.

    A receipt producer failure is itself release truth.  Publishing this small
    fail-closed receipt avoids an ambiguous missing artifact without allowing a
    failed producer to assert launch authority.
    """

    sanitized_reason = redact_release_output(str(reason), dict(os.environ)).strip()
    if not sanitized_reason:
        sanitized_reason = "release-ready receipt producer failed without a diagnostic"
    failure = f"FAIL release_ready_receipt_materializer: {sanitized_reason}"
    return {
        "contract_name": "chummer.release_ready",
        "generated_at_utc": now_iso(),
        "status": "fail",
        "verdict": "NOT_RELEASE_READY",
        "command": command or supported_release_controller_command(),
        "returncode": returncode,
        "timed_out": bool(timed_out),
        "timeout_seconds": TIMEOUT_SECONDS,
        "saw_release_ready_marker": False,
        "not_release_ready_markers": ["release-ready receipt producer failed"],
        "failures": [failure],
        "failed_gates": ["release_ready_receipt_materializer"],
        "blocking_gate_artifacts": {},
        "current_receipt_states": {},
        "stdout_tail": [],
        "stderr_tail": [],
        "global_verifier_skipped_due_current_blockers": False,
        "proof_refresh_policy": dict(proof_refresh_policy or {}),
        "authority_scope": DIAGNOSTIC_AUTHORITY_SCOPE,
        "authoritative": False,
        "diagnostic": True,
        "test_only": False,
        "external_release_writes_authorized": False,
        "materialization_error": {
            "phase": str(phase or "unknown"),
            "reason": sanitized_reason,
            "returncode": returncode,
            "timed_out": bool(timed_out),
        },
        "nextActions": [
            "Repair the release-ready receipt producer, then rerun the canonical release gate."
        ],
        "advisoryActions": [],
    }


def publish_release_ready_materialization_failure(
    *,
    phase: str,
    reason: str,
    returncode: int | None,
    timed_out: bool = False,
    proof_refresh_policy: dict[str, str] | None = None,
    command: str | None = None,
) -> dict[str, object]:
    payload = release_ready_materialization_failure_payload(
        phase=phase,
        reason=reason,
        returncode=returncode,
        timed_out=timed_out,
        proof_refresh_policy=proof_refresh_policy,
        command=command,
    )
    atomic_write_json(OUTPUT_PATH, payload)
    return payload


def projection_staging_path() -> Path:
    return OUTPUT_PATH.with_name(f".{OUTPUT_PATH.name}.projection-in-progress")


def durable_unlink(path: Path) -> None:
    """Remove stale authority and fsync its directory before continuing."""

    try:
        path.unlink()
    except FileNotFoundError:
        return
    directory_descriptor = os.open(
        path.parent,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def controller_environment_value_digests(environment: dict[str, str]) -> dict[str, str]:
    """Bind controller values without serializing provider credentials."""

    return {
        key: hashlib.sha256(value.encode("utf-8")).hexdigest()
        for key, value in sorted(environment.items())
    }


def controller_gate_environment(
    gate_name: str,
    environment: dict[str, str],
) -> dict[str, str]:
    """Return the least-privilege environment bound to one canonical gate."""

    if gate_name not in REQUIRED_RELEASE_VERIFIER_GATES:
        raise ValueError(f"release controller gate environment is not canonical: {gate_name}")
    provider_keys = RELEASE_GATE_PROVIDER_ENV_KEYS.get(gate_name, frozenset())
    return dict(
        sorted(
            (key, value)
            for key, value in environment.items()
            if key not in RELEASE_PROVIDER_ENV_KEYS or key in provider_keys
        )
    )


def url_encoded_secret_pattern(value: str) -> str:
    """Match percent-escape hex case without folding credential characters."""

    parts: list[str] = []
    index = 0
    while index < len(value):
        if (
            value[index] == "%"
            and index + 2 < len(value)
            and re.fullmatch(r"[0-9A-Fa-f]{2}", value[index + 1 : index + 3])
        ):
            parts.append("%")
            for digit in value[index + 1 : index + 3]:
                lowered = digit.lower()
                parts.append(
                    f"[{lowered}{lowered.upper()}]"
                    if lowered in "abcdef"
                    else re.escape(digit)
                )
            index += 3
            continue
        parts.append(re.escape(value[index]))
        index += 1
    return "".join(parts)


def redact_release_output(text: str, environment: dict[str, str]) -> str:
    """Redact credential values plus common assignment/header representations."""

    redacted = str(text)
    values = sorted(
        {
            str(environment.get(key) or "")
            for key in RELEASE_SECRET_ENV_KEYS
            if str(environment.get(key) or "")
        },
        key=len,
        reverse=True,
    )
    for value in values:
        redacted = redacted.replace(value, "[REDACTED]")
        encoded_values = {
            quote(value, safe=""),
            quote_plus(value, safe=""),
        }
        for encoded_value in sorted(encoded_values, key=len, reverse=True):
            if encoded_value and encoded_value != value:
                redacted = re.sub(
                    url_encoded_secret_pattern(encoded_value),
                    "[REDACTED]",
                    redacted,
                )
    credential_names = "|".join(
        re.escape(key) for key in sorted(RELEASE_SECRET_ENV_KEYS, key=len, reverse=True)
    )
    redacted = re.sub(
        rf"(?i)\b({credential_names})\b(\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;\r\n]+)",
        r"\1\2[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(authorization\s*:\s*)(?:bearer|basic)\s+[^\s,;\r\n]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(x-api-key|api[-_]?key|access[-_]?token|secret|token)(\s*[:=]\s*)"
        r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;\r\n]+)",
        r"\1\2[REDACTED]",
        redacted,
    )
    return redacted


def authoritative_controller_environment(
    source: dict[str, str] | os._Environ[str] | None = None,
    *,
    skip_google_oauth_runtime_refresh: bool = False,
    skip_windows_runtime_refresh: bool = False,
) -> dict[str, str]:
    ambient = dict(os.environ if source is None else source)
    inherited_functions = sorted(key for key in ambient if key.startswith("BASH_FUNC_"))
    if inherited_functions:
        raise ValueError(
            "release controller rejects inherited Bash functions: "
            + ", ".join(inherited_functions)
        )
    for key in RELEASE_EXECUTION_FORBIDDEN_ENV_KEYS:
        if ambient.get(key):
            raise ValueError(f"release controller environment {key} must be unset")
    incoming_path = str(ambient.get("PATH") or "")
    if incoming_path != TRUSTED_PATH:
        raise ValueError(
            "release controller rejects inherited or user-writable PATH; "
            f"expected exactly {TRUSTED_PATH}"
        )
    binding_failures = source_binding_failures()
    if binding_failures:
        raise ValueError(
            "release controller source binding failed: "
            + "; ".join(binding_failures)
        )

    controlled_defaults = {
        "CHUMMER_PUBLIC_BASE_URL": "https://chummer.run",
        "CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E": "0",
        "CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E": "0",
        "CHUMMER_RELEASE_READY_SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH": "0",
        "CHUMMER_RELEASE_READY_SKIP_WINDOWS_RUNTIME_REFRESH": "0",
        "CHUMMER_RELEASE_READY_GATE_TIMEOUT_SECONDS": "900",
        "CHUMMER_RELEASE_READY_GUIDE_GATE_TIMEOUT_SECONDS": "1800",
        "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "30",
        "CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_REUSE_MAX_AGE_HOURS": "24",
        "CHUMMER_PUBLIC_EDGE_TIMEOUT_SECONDS": "60",
        "PATH": TRUSTED_PATH,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    sanitized = {
        key: str(value)
        for key, value in ambient.items()
        if key in RELEASE_CONTROLLER_ENV_ALLOWLIST and value is not None and str(value)
    }
    sanitized.update(
        {
            key: str(ambient.get(key) or default)
            for key, default in controlled_defaults.items()
        }
    )
    for key in RELEASE_EXECUTION_FORBIDDEN_ENV_KEYS:
        sanitized.pop(key, None)
    sanitized["PATH"] = TRUSTED_PATH
    sanitized["PYTHONDONTWRITEBYTECODE"] = "1"
    sanitized["PYTHONNOUSERSITE"] = "1"
    sanitized[RELEASE_READY_MATERIALIZER_ACTIVE_ENV] = "1"
    sanitized["CHUMMER_SKIP_CODEX_HANDOFF_MATERIALIZER"] = "1"
    sanitized["CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE"] = "1"
    sanitized["GIT_CONFIG_GLOBAL"] = "/dev/null"
    sanitized["GIT_CONFIG_NOSYSTEM"] = "1"
    sanitized["GIT_OPTIONAL_LOCKS"] = "0"
    sanitized["CHUMMER_RUN_SERVICES_ROOT"] = str(RUN_SERVICES_ROOT)
    sanitized["CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD"] = current_git_head()
    if skip_google_oauth_runtime_refresh:
        sanitized[SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH_ENV] = "1"
    if skip_windows_runtime_refresh:
        sanitized[SKIP_WINDOWS_RUNTIME_REFRESH_ENV] = "1"
    normalized_control = validate_release_execution_environment(
        {key: sanitized.get(key, "") for key in RELEASE_EXECUTION_ENV_KEYS}
    )
    sanitized.update(normalized_control)
    return dict(sorted(sanitized.items()))


def current_release_execution_environment(
    environment: dict[str, str] | None = None,
) -> dict[str, str]:
    source = os.environ if environment is None else environment
    return {key: str(source.get(key) or "") for key in RELEASE_EXECUTION_ENV_KEYS}


def inherited_environment_sha256(environment: dict[str, str] | None = None) -> str:
    source = dict(os.environ if environment is None else environment)
    return canonical_json_sha256(controller_environment_value_digests(source))


def validate_release_execution_environment(environment: dict[str, object]) -> dict[str, str]:
    if set(environment) != set(RELEASE_EXECUTION_ENV_KEYS):
        raise ValueError("release execution environment fields are incomplete or unexpected")
    normalized = {key: str(environment.get(key) or "") for key in RELEASE_EXECUTION_ENV_KEYS}
    if normalized["PYTHONDONTWRITEBYTECODE"] != "1":
        raise ValueError("release execution requires PYTHONDONTWRITEBYTECODE=1")
    if normalized["PYTHONNOUSERSITE"] != "1":
        raise ValueError("release execution requires PYTHONNOUSERSITE=1")
    for key in RELEASE_EXECUTION_FORBIDDEN_ENV_KEYS:
        if normalized[key]:
            raise ValueError(f"release execution environment {key} must be unset")
    if normalized["CHUMMER_RUN_SERVICES_ROOT"] != str(RUN_SERVICES_ROOT):
        raise ValueError(
            "release execution CHUMMER_RUN_SERVICES_ROOT must equal the current checkout"
        )
    if re.fullmatch(
        r"(?:[0-9a-f]{40}|[0-9a-f]{64})",
        normalized["CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD"],
    ) is None:
        raise ValueError(
            "release execution CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD must be a full Git commit"
        )
    parsed_url = urlsplit(normalized["CHUMMER_PUBLIC_BASE_URL"])
    try:
        parsed_port = parsed_url.port
    except ValueError as exc:
        raise ValueError("release execution public base URL has an invalid port") from exc
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.hostname
        or not re.fullmatch(r"(?:[A-Za-z0-9.-]+|[0-9A-Fa-f:]+)", parsed_url.hostname)
        or parsed_url.username
        or parsed_url.password
        or parsed_url.query
        or parsed_url.fragment
        or parsed_url.path not in {"", "/"}
        or (parsed_port is not None and not 1 <= parsed_port <= 65535)
        or any(ord(character) < 33 or ord(character) > 126 for character in normalized["CHUMMER_PUBLIC_BASE_URL"])
    ):
        raise ValueError("release execution public base URL is not a clean HTTP(S) origin")
    if normalized["PATH"] != TRUSTED_PATH:
        raise ValueError(f"release execution PATH must equal trusted PATH {TRUSTED_PATH}")
    for key in (
        "CHUMMER_RELEASE_READY_GATE_TIMEOUT_SECONDS",
        "CHUMMER_RELEASE_READY_GUIDE_GATE_TIMEOUT_SECONDS",
        "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS",
        "CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_REUSE_MAX_AGE_HOURS",
        "CHUMMER_PUBLIC_EDGE_TIMEOUT_SECONDS",
    ):
        try:
            parsed = int(normalized[key])
        except ValueError as exc:
            raise ValueError(f"release execution environment {key} is not an integer") from exc
        if parsed <= 0 or parsed > 86400:
            raise ValueError(f"release execution environment {key} is out of range")
    for key in (
        "CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E",
        "CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E",
        "CHUMMER_RELEASE_READY_SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH",
        "CHUMMER_RELEASE_READY_SKIP_WINDOWS_RUNTIME_REFRESH",
    ):
        if normalized[key] not in {"0", "1"}:
            raise ValueError(f"release execution environment {key} is not 0 or 1")
    return normalized


def absolute_nonsymlink_path(path: Path, *, require_directory: bool = False) -> Path:
    normalized = Path(os.path.abspath(path))
    if not normalized.is_absolute():
        raise ValueError(f"release execution path is not absolute: {path}")
    current = Path(normalized.anchor)
    for component in normalized.parts[1:]:
        current /= component
        try:
            entry_stat = os.lstat(current)
        except OSError as exc:
            raise ValueError(f"release execution path is unavailable: {normalized}: {exc}") from exc
        if stat.S_ISLNK(entry_stat.st_mode):
            raise ValueError(f"release execution path has a symlink component: {current}")
    final_stat = os.lstat(normalized)
    expected_type = stat.S_ISDIR if require_directory else stat.S_ISREG
    if not expected_type(final_stat.st_mode):
        kind = "directory" if require_directory else "regular file"
        raise ValueError(f"release execution path is not a {kind}: {normalized}")
    return normalized


def directory_identity(path: Path) -> dict[str, object]:
    normalized = absolute_nonsymlink_path(path, require_directory=True)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(normalized, flags)
    try:
        value = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    return {
        "path": str(normalized),
        "device": value.st_dev,
        "inode": value.st_ino,
        "mode": value.st_mode,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
    }


def directory_ancestor_identities(path: Path) -> list[dict[str, object]]:
    """Capture every directory from *path* through the filesystem root."""

    normalized = Path(os.path.abspath(path))
    values: list[dict[str, object]] = []
    current = normalized
    while True:
        values.append(directory_identity(current))
        if current.parent == current:
            break
        current = current.parent
    return values


def directory_execution_identity(path: Path) -> dict[str, object]:
    identity = directory_identity(path)
    return {
        **identity,
        "ancestors": directory_ancestor_identities(Path(str(identity["path"])).parent),
    }


def regular_file_execution_identity(path: Path) -> dict[str, object]:
    normalized = absolute_nonsymlink_path(path)
    parent = normalized.parent
    ancestors_before = directory_ancestor_identities(parent)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(normalized, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"release execution input is not regular: {normalized}")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    leaf_after = os.lstat(normalized)
    ancestors_after = directory_ancestor_identities(parent)
    stable_fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise ValueError(f"release execution input changed while hashing: {normalized}")
    if any(getattr(after, field) != getattr(leaf_after, field) for field in stable_fields):
        raise ValueError(f"release execution input path changed while hashing: {normalized}")
    if ancestors_before != ancestors_after:
        raise ValueError(f"release execution input ancestor changed while hashing: {parent}")
    return {
        "path": str(normalized),
        "sha256": digest.hexdigest(),
        "device": after.st_dev,
        "inode": after.st_ino,
        "mode": after.st_mode,
        "size_bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
        "parent": ancestors_after[0],
        "ancestors": ancestors_after,
    }


def governed_code_path(relative_path: str) -> bool:
    normalized = relative_path.replace(os.sep, "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    if not normalized or any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in GOVERNED_CODE_EXCLUDED_OUTPUT_PREFIXES
    ):
        return False
    path = Path(normalized)
    return (
        path.name in GOVERNED_CODE_BASENAMES
        or path.suffix.lower() in GOVERNED_CODE_SUFFIXES
        or "scripts" in path.parts
    )


def governed_restored_dependency_path(relative_path: str) -> bool:
    normalized = relative_path.replace(os.sep, "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in GOVERNED_RESTORED_DEPENDENCY_PREFIXES
    )


def governed_repository_root(path: Path) -> Path:
    current = Path(os.path.abspath(path))
    if current.is_file():
        current = current.parent
    while True:
        marker = current / ".git"
        if marker.exists():
            if stat.S_ISLNK(os.lstat(marker).st_mode):
                raise ValueError(f"governed repository .git marker is a symlink: {marker}")
            return absolute_nonsymlink_path(current, require_directory=True)
        if current.parent == current:
            raise ValueError(f"governed code path is outside a Git repository: {path}")
        current = current.parent


def governed_repository_roots(paths: list[Path] | tuple[Path, ...]) -> tuple[Path, ...]:
    values: list[Path] = []
    for path in paths:
        root = governed_repository_root(path)
        if root not in values:
            values.append(root)
    return tuple(values)


def run_governed_git(
    repository: Path,
    arguments: list[str],
    environment: dict[str, str],
) -> bytes:
    git_environment = {
        "PATH": TRUSTED_PATH,
        "HOME": environment.get("HOME", "/nonexistent"),
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    completed = subprocess.run(
        [
            str(TRUSTED_GIT),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-C",
            str(repository),
            *arguments,
        ],
        cwd=repository,
        env=git_environment,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        detail = coerce_output(completed.stderr).strip()
        raise ValueError(
            f"governed repository Git command failed at {repository}: "
            f"{detail or completed.returncode}"
        )
    return bytes(completed.stdout)


def null_delimited_paths(value: bytes) -> list[str]:
    try:
        return [item.decode("utf-8") for item in value.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise ValueError("governed repository contains a non-UTF-8 path") from exc


def governed_code_file_identity(repository: Path, relative_path: str) -> dict[str, object]:
    path = repository / relative_path
    normalized = absolute_nonsymlink_path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(normalized, flags)
    try:
        before = os.fstat(descriptor)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    stable_fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise ValueError(f"governed code changed while snapshotting: {normalized}")
    return {
        "path": relative_path.replace(os.sep, "/"),
        "sha256": digest.hexdigest(),
        "device": after.st_dev,
        "inode": after.st_ino,
        "mode": after.st_mode,
        "size_bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
    }


def governed_code_directory_identities(
    repository: Path,
    relative_paths: list[str],
) -> list[dict[str, object]]:
    directories: set[Path] = {repository}
    for relative_path in relative_paths:
        current = (repository / relative_path).parent
        while True:
            directories.add(current)
            if current == repository:
                break
            if repository not in current.parents:
                raise ValueError(
                    f"governed code path escaped repository while binding directories: {relative_path}"
                )
            current = current.parent
    return [
        directory_identity(path)
        for path in sorted(directories, key=lambda value: str(value))
    ]


def current_governed_code_snapshot(
    repositories: list[Path] | tuple[Path, ...],
    environment: dict[str, str],
) -> dict[str, object]:
    repository_snapshots: list[dict[str, object]] = []
    for repository in repositories:
        root = absolute_nonsymlink_path(repository, require_directory=True)
        try:
            head = run_governed_git(
                root,
                ["rev-parse", "--verify", "HEAD"],
                environment,
            ).decode().strip()
        except ValueError as exc:
            raise ValueError(
                f"governed repository has no enrolled Git HEAD at {root}; "
                "commit the external workspace release authority into a governed "
                "repository before running the authoritative controller (live untracked "
                "digest fallback is not accepted)"
            ) from exc
        tree = run_governed_git(root, ["rev-parse", "--verify", "HEAD^{tree}"], environment).decode().strip()
        dirty_values: list[str] = []
        for arguments in (
            ["diff", "--name-only", "-z", "--no-ext-diff"],
            ["diff", "--cached", "--name-only", "-z", "--no-ext-diff"],
            ["ls-files", "--others", "--exclude-standard", "-z"],
            ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        ):
            dirty_values.extend(null_delimited_paths(run_governed_git(root, arguments, environment)))
        dirty_code_paths = sorted(
            set(
                value
                for value in dirty_values
                if governed_code_path(value)
                and not governed_restored_dependency_path(value)
            )
        )
        if dirty_code_paths:
            raise ValueError(
                f"governed repository has uncommitted code at {root}: "
                + ", ".join(dirty_code_paths[:20])
            )
        tracked = null_delimited_paths(
            run_governed_git(root, ["ls-files", "--cached", "-z"], environment)
        )
        restored_dependency_files = {
            value
            for value in dirty_values
            if governed_code_path(value) and governed_restored_dependency_path(value)
        }
        governed_files = sorted(
            {value for value in tracked if governed_code_path(value)}
            | restored_dependency_files
        )
        directories_before = governed_code_directory_identities(root, governed_files)
        identities = [
            governed_code_file_identity(root, relative_path)
            for relative_path in governed_files
        ]
        directories_after = governed_code_directory_identities(root, governed_files)
        if directories_before != directories_after:
            raise ValueError(
                f"governed code directory tree changed while snapshotting: {root}"
            )
        repository_snapshots.append(
            {
                "root": directory_execution_identity(root),
                "head_commit": head,
                "head_tree": tree,
                "governed_file_count": len(identities),
                "governed_files_sha256": canonical_json_sha256(identities),
                "governed_directory_count": len(directories_after),
                "governed_directories_sha256": canonical_json_sha256(
                    directories_after
                ),
                "restored_dependency_prefixes": list(
                    GOVERNED_RESTORED_DEPENDENCY_PREFIXES
                ),
                "restored_dependency_file_count": len(restored_dependency_files),
            }
        )
    body: dict[str, object] = {
        "excluded_outputs": [
            {"prefix": prefix, "reason": reason}
            for prefix, reason in GOVERNED_CODE_EXCLUDED_OUTPUTS
        ],
        "repositories": repository_snapshots,
    }
    return {**body, "snapshot_sha256": canonical_json_sha256(body)}


def validate_governed_code_snapshot(
    recorded: dict[str, object],
    repositories: list[Path] | tuple[Path, ...],
    environment: dict[str, str],
) -> dict[str, object]:
    current = current_governed_code_snapshot(repositories, environment)
    if current != recorded:
        raise ValueError("release governed code snapshot drifted")
    return current


def path_is_within_declared_root(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def literal_code_paths(command: str) -> list[str]:
    suffixes = "|".join(re.escape(value.removeprefix(".")) for value in CODE_ENTRYPOINT_SUFFIXES)
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_./-])(/[A-Za-z0-9_./+-]+\.(?:{suffixes}))(?=$|[\s;&|()])"
    )
    return list(dict.fromkeys(match.group(1) for match in pattern.finditer(command)))


def shell_command_tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def build_release_execution_plan(
    gate_specs: list[list[str] | tuple[str, ...]],
    interpreter_specs: list[list[str] | tuple[str, ...]],
    code_root_values: list[str | Path],
    *,
    environment: dict[str, object] | None = None,
    controller_environment: dict[str, str] | None = None,
    external_write_gates: tuple[str, ...] | list[str] = (),
    external_write_authorized: bool = False,
    governed_repositories: tuple[Path, ...] | list[Path] = (),
    require_governed_code_snapshot: bool = False,
    process_containment: dict[str, object] | None = None,
    run_nonce: str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    normalized_environment = validate_release_execution_environment(
        dict(environment or current_release_execution_environment())
    )
    bound_controller_environment = dict(
        controller_environment
        or {key: value for key, value in normalized_environment.items() if value}
    )
    unknown_controller_keys = set(bound_controller_environment) - RELEASE_CONTROLLER_ENV_ALLOWLIST
    if unknown_controller_keys:
        raise ValueError(
            "release controller environment contains non-allowlisted keys: "
            + ", ".join(sorted(unknown_controller_keys))
        )
    if current_release_execution_environment(bound_controller_environment) != normalized_environment:
        raise ValueError("release controller environment does not match execution controls")
    nonce = str(run_nonce or secrets.token_hex(32)).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", nonce):
        raise ValueError("release execution run nonce is not a 64-character lowercase hex value")
    if tuple(str(spec[0]) for spec in gate_specs if len(spec) == 5) != REQUIRED_RELEASE_VERIFIER_GATES:
        raise ValueError("release execution gate specs are not the canonical complete matrix")
    if any(len(spec) != 5 for spec in gate_specs):
        raise ValueError("release execution gate spec must have five fields")

    code_roots = [absolute_nonsymlink_path(Path(value), require_directory=True) for value in code_root_values]
    if not code_roots:
        raise ValueError("release execution has no declared code roots")
    code_root_identities = [directory_execution_identity(path) for path in code_roots]

    interpreters: list[dict[str, object]] = []
    interpreter_names: set[str] = set()
    for spec in interpreter_specs:
        if len(spec) != 2:
            raise ValueError("release execution interpreter spec must have two fields")
        name, raw_path = (str(spec[0]), str(spec[1]))
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in interpreter_names:
            raise ValueError(f"release execution interpreter name is invalid or duplicate: {name}")
        interpreter_names.add(name)
        interpreters.append({"name": name, "identity": regular_file_execution_identity(Path(raw_path))})
    runner_name = (
        "bash_noprofile_norc"
        if "bash_noprofile_norc" in interpreter_names
        else "bash_lc" if "bash_lc" in interpreter_names else ""
    )
    if not runner_name:
        raise ValueError("release execution interpreters must include bash_noprofile_norc")
    interpreter_by_name = {str(item["name"]): item for item in interpreters}

    gates: list[dict[str, object]] = []
    for index, spec in enumerate(gate_specs):
        name, command, raw_cwd, raw_timeout, raw_entrypoints = (str(value) for value in spec)
        cwd = absolute_nonsymlink_path(Path(raw_cwd), require_directory=True)
        try:
            timeout_seconds = int(raw_timeout)
        except ValueError as exc:
            raise ValueError(f"release execution gate timeout is invalid: {name}") from exc
        if timeout_seconds <= 0 or timeout_seconds > 86400:
            raise ValueError(f"release execution gate timeout is out of range: {name}")
        entrypoint_paths = [
            absolute_nonsymlink_path(Path(value))
            for value in raw_entrypoints.split("|")
            if value
        ]
        if not entrypoint_paths or len(set(entrypoint_paths)) != len(entrypoint_paths):
            raise ValueError(f"release execution gate entrypoints are missing or duplicate: {name}")
        if any(not path_is_within_declared_root(path, code_roots) for path in entrypoint_paths):
            raise ValueError(f"release execution gate entrypoint is outside declared code roots: {name}")
        literal_paths = [Path(value) for value in literal_code_paths(command)]
        if set(literal_paths) != set(entrypoint_paths):
            raise ValueError(f"release execution gate literal code paths are not exactly covered: {name}")
        tokens = set(shell_command_tokens(command))
        used_interpreters = [
            interpreter_name
            for interpreter_name, item in interpreter_by_name.items()
            if str(item["identity"]["path"]) in tokens
        ]
        if not used_interpreters:
            raise ValueError(f"release execution gate command has no bound interpreter: {name}")
        gate_interpreters = list(dict.fromkeys([runner_name, *used_interpreters]))
        gate_environment = controller_gate_environment(name, bound_controller_environment)
        gates.append(
            {
                "index": index,
                "name": name,
                "command": command,
                "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                "cwd": str(cwd),
                "timeout_seconds": timeout_seconds,
                "interpreter_names": gate_interpreters,
                "entrypoints": [regular_file_execution_identity(path) for path in entrypoint_paths],
                "environment_keys": sorted(gate_environment),
                "environment_value_sha256": controller_environment_value_digests(
                    gate_environment
                ),
            }
        )

    authority_paths: list[Path] = []
    for value in (VERIFY_SCRIPT, Path(__file__).resolve(), *(path for _name, path in RELEASE_VERIFIER_BOUND_PROGRAMS)):
        normalized = Path(os.path.abspath(value))
        if normalized not in authority_paths:
            authority_paths.append(normalized)

    normalized_external_write_gates = tuple(str(value) for value in external_write_gates)
    if any(value not in REQUIRED_RELEASE_VERIFIER_GATES for value in normalized_external_write_gates):
        raise ValueError("release execution external-write gate declaration is invalid")
    normalized_governed_repositories = tuple(
        absolute_nonsymlink_path(Path(value), require_directory=True)
        for value in governed_repositories
    )
    if require_governed_code_snapshot and not normalized_governed_repositories:
        raise ValueError("authoritative release execution has no governed code repositories")
    governed_snapshot = (
        current_governed_code_snapshot(
            normalized_governed_repositories,
            bound_controller_environment,
        )
        if require_governed_code_snapshot
        else {}
    )
    normalized_process_containment = dict(
        process_containment
        or {
            "mode": "diagnostic_unenforced",
            "authoritative": False,
            "subreaper": False,
            "procfs": "",
        }
    )
    if set(normalized_process_containment) != {
        "mode",
        "authoritative",
        "subreaper",
        "procfs",
    }:
        raise ValueError("release execution process containment binding is invalid")
    if require_governed_code_snapshot and normalized_process_containment != {
        "mode": PROCESS_CONTAINMENT_MODE,
        "authoritative": True,
        "subreaper": True,
        "procfs": "/proc",
    }:
        raise ValueError("authoritative release execution lacks enforced process containment")
    body: dict[str, object] = {
        "contract_name": RELEASE_EXECUTION_PLAN_CONTRACT,
        "run_nonce": nonce,
        "wrapper_cwd": str(absolute_nonsymlink_path(Path.cwd(), require_directory=True)),
        "environment": normalized_environment,
        "inherited_environment_sha256": inherited_environment_sha256(
            bound_controller_environment
        ),
        "controller_environment_keys": sorted(bound_controller_environment),
        "controller_environment_value_sha256": controller_environment_value_digests(
            bound_controller_environment
        ),
        "external_write_gates": list(normalized_external_write_gates),
        "external_write_authorized": bool(external_write_authorized),
        "governed_code_snapshot_required": bool(require_governed_code_snapshot),
        "governed_code_snapshot": governed_snapshot,
        "process_containment": normalized_process_containment,
        "code_roots": code_root_identities,
        "interpreters": interpreters,
        "authority_inputs": [
            regular_file_execution_identity(path) for path in authority_paths
        ],
        "gates": gates,
        "gate_count": len(gates),
    }
    return {
        **body,
        "generated_at_utc": observed_at.isoformat().replace("+00:00", "Z"),
        "plan_sha256": canonical_json_sha256(body),
    }


def validate_release_execution_plan(
    plan: dict[str, object],
    *,
    now: datetime | None = None,
    enforce_max_age: bool = True,
    enforce_current_environment: bool = True,
    recheck_inputs: bool = True,
    controller_environment: dict[str, str] | None = None,
) -> dict[str, object]:
    expected_fields = {
        "contract_name",
        "run_nonce",
        "wrapper_cwd",
        "environment",
        "inherited_environment_sha256",
        "controller_environment_keys",
        "controller_environment_value_sha256",
        "external_write_gates",
        "external_write_authorized",
        "governed_code_snapshot_required",
        "governed_code_snapshot",
        "process_containment",
        "code_roots",
        "interpreters",
        "authority_inputs",
        "gates",
        "gate_count",
        "generated_at_utc",
        "plan_sha256",
    }
    if set(plan) != expected_fields or plan.get("contract_name") != RELEASE_EXECUTION_PLAN_CONTRACT:
        raise ValueError("release execution plan fields or contract are invalid")
    body = {key: value for key, value in plan.items() if key not in {"generated_at_utc", "plan_sha256"}}
    if plan.get("plan_sha256") != canonical_json_sha256(body):
        raise ValueError("release execution plan digest is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(plan.get("run_nonce") or "")):
        raise ValueError("release execution plan run nonce is invalid")
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    generated_at = parse_receipt_timestamp(plan.get("generated_at_utc"))
    if generated_at is None or generated_at > observed_at + RELEASE_VERIFIER_REPLAY_FUTURE_SKEW:
        raise ValueError("release execution plan timestamp is invalid")
    if enforce_max_age and observed_at - generated_at > RELEASE_EXECUTION_PLAN_MAX_AGE:
        raise ValueError("release execution plan is stale")
    environment = plan.get("environment")
    if not isinstance(environment, dict):
        raise ValueError("release execution plan environment is invalid")
    normalized_environment = validate_release_execution_environment(environment)
    current_environment = current_release_execution_environment(
        controller_environment
    ) if controller_environment is not None else current_release_execution_environment()
    if enforce_current_environment and normalized_environment != current_environment:
        raise ValueError("release execution environment drifted")
    if controller_environment is not None:
        expected_keys = sorted(controller_environment)
        expected_digests = controller_environment_value_digests(controller_environment)
        if plan.get("controller_environment_keys") != expected_keys:
            raise ValueError("release controller environment key set drifted")
        if plan.get("controller_environment_value_sha256") != expected_digests:
            raise ValueError("release controller environment values drifted")
        if plan.get("inherited_environment_sha256") != inherited_environment_sha256(
            controller_environment
        ):
            raise ValueError("release controller environment digest drifted")
    elif (
        not isinstance(plan.get("controller_environment_keys"), list)
        or not isinstance(plan.get("controller_environment_value_sha256"), dict)
    ):
        raise ValueError("release controller environment digest binding is invalid")
    external_write_gates = normalized_string_list(plan.get("external_write_gates"))
    if any(value not in REQUIRED_RELEASE_VERIFIER_GATES for value in external_write_gates):
        raise ValueError("release execution external-write gate binding is invalid")
    if not isinstance(plan.get("external_write_authorized"), bool):
        raise ValueError("release execution external-write authorization is invalid")
    if not isinstance(plan.get("governed_code_snapshot_required"), bool):
        raise ValueError("release governed code snapshot requirement is invalid")
    governed_snapshot = plan.get("governed_code_snapshot")
    if not isinstance(governed_snapshot, dict):
        raise ValueError("release governed code snapshot is invalid")
    if plan.get("governed_code_snapshot_required") is True:
        snapshot_body = {
            key: value
            for key, value in governed_snapshot.items()
            if key != "snapshot_sha256"
        }
        if (
            set(governed_snapshot)
            != {"excluded_outputs", "repositories", "snapshot_sha256"}
            or governed_snapshot.get("snapshot_sha256")
            != canonical_json_sha256(snapshot_body)
            or governed_snapshot.get("excluded_outputs")
            != [
                {"prefix": prefix, "reason": reason}
                for prefix, reason in GOVERNED_CODE_EXCLUDED_OUTPUTS
            ]
        ):
            raise ValueError("release governed code snapshot binding is invalid")
        repositories = governed_snapshot.get("repositories")
        if not isinstance(repositories, list) or not repositories:
            raise ValueError("release governed code repositories are missing")
        repository_roots = [
            Path(str(item.get("root", {}).get("path") or ""))
            for item in repositories
            if isinstance(item, dict) and isinstance(item.get("root"), dict)
        ]
        if len(repository_roots) != len(repositories):
            raise ValueError("release governed code repository identities are invalid")
        if controller_environment is not None:
            current_snapshot = validate_governed_code_snapshot(
                governed_snapshot,
                repository_roots,
                controller_environment,
            )
    elif governed_snapshot:
        raise ValueError("diagnostic release plan has an unexpected governed code snapshot")
    process_containment = plan.get("process_containment")
    if not isinstance(process_containment, dict) or set(process_containment) != {
        "mode",
        "authoritative",
        "subreaper",
        "procfs",
    }:
        raise ValueError("release execution process containment binding is invalid")
    if plan.get("governed_code_snapshot_required") is True and process_containment != {
        "mode": PROCESS_CONTAINMENT_MODE,
        "authoritative": True,
        "subreaper": True,
        "procfs": "/proc",
    }:
        raise ValueError("authoritative release execution process containment is unenforced")
    gates = plan.get("gates")
    if not isinstance(gates, list) or tuple(
        str(item.get("name") or "") for item in gates if isinstance(item, dict)
    ) != REQUIRED_RELEASE_VERIFIER_GATES:
        raise ValueError("release execution plan gate matrix is not canonical")
    if plan.get("gate_count") != len(REQUIRED_RELEASE_VERIFIER_GATES):
        raise ValueError("release execution plan gate count is not canonical")
    if not recheck_inputs:
        return dict(plan)

    code_roots = plan.get("code_roots")
    interpreters = plan.get("interpreters")
    authority_inputs = plan.get("authority_inputs")
    if (
        not isinstance(code_roots, list)
        or not isinstance(interpreters, list)
        or not isinstance(authority_inputs, list)
    ):
        raise ValueError("release execution plan roots or interpreters are invalid")
    for recorded in code_roots:
        if not isinstance(recorded, dict):
            raise ValueError("release execution code root identity is invalid")
        if directory_execution_identity(Path(str(recorded.get("path") or ""))) != recorded:
            raise ValueError("release execution code root identity drifted")
    interpreter_map: dict[str, dict[str, object]] = {}
    for item in interpreters:
        if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
            raise ValueError("release execution interpreter identity is invalid")
        name = str(item.get("name") or "")
        identity = dict(item["identity"])
        if regular_file_execution_identity(Path(str(identity.get("path") or ""))) != identity:
            raise ValueError(f"release execution interpreter identity drifted: {name}")
        interpreter_map[name] = identity
    if not ({"bash_noprofile_norc", "bash_lc"} & set(interpreter_map)):
        raise ValueError("release execution plan runner interpreters are missing")
    for recorded_value in authority_inputs:
        if not isinstance(recorded_value, dict):
            raise ValueError("release execution authority input identity is invalid")
        recorded = dict(recorded_value)
        if regular_file_execution_identity(Path(str(recorded.get("path") or ""))) != recorded:
            raise ValueError("release execution authority input identity drifted")
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict) or gate.get("index") != index:
            raise ValueError("release execution plan gate index is invalid")
        if gate.get("command_sha256") != hashlib.sha256(
            str(gate.get("command") or "").encode("utf-8")
        ).hexdigest():
            raise ValueError(f"release execution gate command digest is invalid: {gate.get('name')}")
        absolute_nonsymlink_path(Path(str(gate.get("cwd") or "")), require_directory=True)
        names = gate.get("interpreter_names")
        entrypoints = gate.get("entrypoints")
        gate_environment = controller_gate_environment(
            str(gate.get("name") or ""),
            controller_environment or {},
        ) if controller_environment is not None else None
        if not isinstance(names, list) or any(str(name) not in interpreter_map for name in names):
            raise ValueError(f"release execution gate interpreter coverage is invalid: {gate.get('name')}")
        if not isinstance(entrypoints, list) or not entrypoints:
            raise ValueError(f"release execution gate entrypoints are invalid: {gate.get('name')}")
        if (
            not isinstance(gate.get("environment_keys"), list)
            or not isinstance(gate.get("environment_value_sha256"), dict)
            or (
                gate_environment is not None
                and (
                    gate.get("environment_keys") != sorted(gate_environment)
                    or gate.get("environment_value_sha256")
                    != controller_environment_value_digests(gate_environment)
                )
            )
        ):
            raise ValueError(
                f"release execution gate environment binding drifted: {gate.get('name')}"
            )
        recorded_paths: list[Path] = []
        for identity in entrypoints:
            if not isinstance(identity, dict):
                raise ValueError("release execution gate entrypoint identity is invalid")
            recorded = dict(identity)
            recorded_path = Path(str(recorded.get("path") or ""))
            recorded_paths.append(recorded_path)
            if regular_file_execution_identity(recorded_path) != recorded:
                raise ValueError(f"release execution gate entrypoint identity drifted: {gate.get('name')}")
        if set(recorded_paths) != set(Path(value) for value in literal_code_paths(str(gate.get("command") or ""))):
            raise ValueError(f"release execution gate literal entrypoint coverage drifted: {gate.get('name')}")
    return dict(plan)


def release_execution_gate(plan: dict[str, object], gate_name: str) -> dict[str, object]:
    gates = plan.get("gates")
    if not isinstance(gates, list):
        raise ValueError("release execution plan gates are invalid")
    gate = next(
        (dict(item) for item in gates if isinstance(item, dict) and item.get("name") == gate_name),
        None,
    )
    if gate is None:
        raise ValueError(f"release execution gate is not canonical: {gate_name}")
    return gate


def current_gate_execution_inputs(
    plan: dict[str, object],
    gate_name: str,
) -> list[dict[str, object]]:
    gate = release_execution_gate(plan, gate_name)
    interpreters = plan.get("interpreters")
    if not isinstance(interpreters, list):
        raise ValueError("release execution plan interpreters are invalid")
    interpreter_map = {
        str(item.get("name") or ""): dict(item.get("identity") or {})
        for item in interpreters
        if isinstance(item, dict)
    }
    inputs: list[dict[str, object]] = []
    for name in gate.get("interpreter_names") or []:
        recorded = interpreter_map.get(str(name))
        if not recorded:
            raise ValueError(f"release execution gate interpreter is missing: {gate_name}:{name}")
        current = regular_file_execution_identity(Path(str(recorded.get("path") or "")))
        if current != recorded:
            raise ValueError(f"release execution gate interpreter drifted: {gate_name}:{name}")
        inputs.append({"role": f"interpreter:{name}", "identity": current})
    entrypoints = gate.get("entrypoints")
    if not isinstance(entrypoints, list):
        raise ValueError(f"release execution gate entrypoints are invalid: {gate_name}")
    for index, recorded_value in enumerate(entrypoints):
        if not isinstance(recorded_value, dict):
            raise ValueError(f"release execution gate entrypoint is invalid: {gate_name}")
        recorded = dict(recorded_value)
        current = regular_file_execution_identity(Path(str(recorded.get("path") or "")))
        if current != recorded:
            raise ValueError(f"release execution gate entrypoint drifted: {gate_name}:{index}")
        inputs.append({"role": f"entrypoint:{index + 1}", "identity": current})
    return inputs


def current_gate_execution_prebinding(
    plan: dict[str, object],
    gate_name: str,
    start_binding: dict[str, object],
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    validate_release_execution_plan(plan, now=observed_at, recheck_inputs=False)
    gate = release_execution_gate(plan, gate_name)
    if (
        start_binding.get("run_nonce") != plan.get("run_nonce")
        or start_binding.get("execution_plan_sha256") != plan.get("plan_sha256")
    ):
        raise ValueError("release execution prebinding is not tied to the verifier start binding")
    inputs = current_gate_execution_inputs(plan, gate_name)
    body: dict[str, object] = {
        "contract_name": RELEASE_GATE_EXECUTION_PREBINDING_CONTRACT,
        "run_nonce": plan["run_nonce"],
        "execution_plan_sha256": plan["plan_sha256"],
        "start_authority_sha256": str(start_binding.get("authority_sha256") or ""),
        "gate": gate_name,
        "gate_index": gate["index"],
        "command_sha256": gate["command_sha256"],
        "cwd": gate["cwd"],
        "timeout_seconds": gate["timeout_seconds"],
        "execution_inputs": inputs,
        "execution_inputs_sha256": canonical_json_sha256(inputs),
    }
    signed_body = {
        **body,
        "captured_before_at_utc": observed_at.isoformat().replace("+00:00", "Z"),
    }
    return {**signed_body, "prebinding_sha256": canonical_json_sha256(signed_body)}


def complete_gate_execution_binding(
    plan: dict[str, object],
    prebinding: dict[str, object],
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    validate_release_execution_plan(plan, now=observed_at, recheck_inputs=False)
    gate_name = str(prebinding.get("gate") or "")
    gate = release_execution_gate(plan, gate_name)
    expected_pre_fields = {
        "contract_name",
        "run_nonce",
        "execution_plan_sha256",
        "start_authority_sha256",
        "gate",
        "gate_index",
        "command_sha256",
        "cwd",
        "timeout_seconds",
        "execution_inputs",
        "execution_inputs_sha256",
        "captured_before_at_utc",
        "prebinding_sha256",
    }
    if set(prebinding) != expected_pre_fields or prebinding.get("contract_name") != RELEASE_GATE_EXECUTION_PREBINDING_CONTRACT:
        raise ValueError("release gate execution prebinding fields or contract are invalid")
    pre_body = {
        key: value
        for key, value in prebinding.items()
        if key != "prebinding_sha256"
    }
    if prebinding.get("prebinding_sha256") != canonical_json_sha256(pre_body):
        raise ValueError("release gate execution prebinding digest is invalid")
    if (
        prebinding.get("run_nonce") != plan.get("run_nonce")
        or prebinding.get("execution_plan_sha256") != plan.get("plan_sha256")
        or prebinding.get("gate_index") != gate.get("index")
        or prebinding.get("command_sha256") != gate.get("command_sha256")
        or prebinding.get("cwd") != gate.get("cwd")
        or prebinding.get("timeout_seconds") != gate.get("timeout_seconds")
    ):
        raise ValueError("release gate execution prebinding does not match the current plan")
    captured_before = parse_receipt_timestamp(prebinding.get("captured_before_at_utc"))
    if captured_before is None or captured_before > observed_at + RELEASE_VERIFIER_REPLAY_FUTURE_SKEW:
        raise ValueError("release gate execution prebinding timestamp is invalid")
    current_inputs = current_gate_execution_inputs(plan, gate_name)
    if prebinding.get("execution_inputs") != current_inputs:
        raise ValueError(f"release gate execution inputs changed during gate: {gate_name}")
    body: dict[str, object] = {
        "contract_name": RELEASE_GATE_EXECUTION_BINDING_CONTRACT,
        "status": "pass",
        "run_nonce": plan["run_nonce"],
        "execution_plan_sha256": plan["plan_sha256"],
        "start_authority_sha256": prebinding["start_authority_sha256"],
        "gate": gate_name,
        "gate_index": gate["index"],
        "command_sha256": gate["command_sha256"],
        "cwd": gate["cwd"],
        "timeout_seconds": gate["timeout_seconds"],
        "execution_inputs": current_inputs,
        "execution_inputs_sha256": canonical_json_sha256(current_inputs),
        "captured_before_at_utc": prebinding["captured_before_at_utc"],
        "prebinding_sha256": prebinding["prebinding_sha256"],
    }
    signed_body = {
        **body,
        "captured_after_at_utc": observed_at.isoformat().replace("+00:00", "Z"),
    }
    return {**signed_body, "binding_sha256": canonical_json_sha256(signed_body)}


def validate_gate_execution_bindings(
    plan: dict[str, object],
    bindings: list[dict[str, object]],
    *,
    start_binding: dict[str, object] | None = None,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    validate_release_execution_plan(plan, now=observed_at, enforce_current_environment=False)
    if tuple(str(item.get("gate") or "") for item in bindings) != REQUIRED_RELEASE_VERIFIER_GATES:
        raise ValueError("release gate execution bindings are incomplete or out of order")
    validated: list[dict[str, object]] = []
    for index, binding in enumerate(bindings):
        gate_name = REQUIRED_RELEASE_VERIFIER_GATES[index]
        gate = release_execution_gate(plan, gate_name)
        expected_fields = {
            "contract_name",
            "status",
            "run_nonce",
            "execution_plan_sha256",
            "start_authority_sha256",
            "gate",
            "gate_index",
            "command_sha256",
            "cwd",
            "timeout_seconds",
            "execution_inputs",
            "execution_inputs_sha256",
            "captured_before_at_utc",
            "prebinding_sha256",
            "captured_after_at_utc",
            "binding_sha256",
        }
        if set(binding) != expected_fields or binding.get("contract_name") != RELEASE_GATE_EXECUTION_BINDING_CONTRACT:
            raise ValueError(f"release gate execution binding fields or contract are invalid: {gate_name}")
        body = {
            key: value
            for key, value in binding.items()
            if key != "binding_sha256"
        }
        if binding.get("binding_sha256") != canonical_json_sha256(body):
            raise ValueError(f"release gate execution binding digest is invalid: {gate_name}")
        if (
            binding.get("status") != "pass"
            or binding.get("run_nonce") != plan.get("run_nonce")
            or binding.get("execution_plan_sha256") != plan.get("plan_sha256")
            or binding.get("gate_index") != index
            or binding.get("command_sha256") != gate.get("command_sha256")
            or binding.get("cwd") != gate.get("cwd")
            or binding.get("timeout_seconds") != gate.get("timeout_seconds")
        ):
            raise ValueError(f"release gate execution binding does not match plan: {gate_name}")
        if start_binding is not None and binding.get("start_authority_sha256") != start_binding.get("authority_sha256"):
            raise ValueError(f"release gate execution binding is not tied to start authority: {gate_name}")
        before = parse_receipt_timestamp(binding.get("captured_before_at_utc"))
        after = parse_receipt_timestamp(binding.get("captured_after_at_utc"))
        if before is None or after is None or before > after or after > observed_at + RELEASE_VERIFIER_REPLAY_FUTURE_SKEW:
            raise ValueError(f"release gate execution binding chronology is invalid: {gate_name}")
        current_inputs = current_gate_execution_inputs(plan, gate_name)
        if binding.get("execution_inputs") != current_inputs:
            raise ValueError(f"release gate execution binding inputs drifted: {gate_name}")
        if binding.get("execution_inputs_sha256") != canonical_json_sha256(current_inputs):
            raise ValueError(f"release gate execution binding input digest is invalid: {gate_name}")
        validated.append(dict(binding))
    return validated


def current_release_verifier_replay_binding(
    *,
    now: datetime | None = None,
    gate_names: list[str] | tuple[str, ...] | None = None,
    execution_plan: dict[str, object] | None = None,
    binding_phase: str = "standalone",
    execution_bindings: list[dict[str, object]] | None = None,
    direct_receipt_bindings: list[dict[str, object]] | None = None,
    enforce_current_environment: bool = True,
) -> dict[str, object]:
    selected_gates = tuple(gate_names or REQUIRED_RELEASE_VERIFIER_GATES)
    if selected_gates != REQUIRED_RELEASE_VERIFIER_GATES:
        raise ValueError("release verifier gate plan does not match the canonical ordered matrix")
    release_channel_path = REGISTRY_PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json"
    manifest_bytes, manifest_error = read_stable_regular_file_bytes(release_channel_path)
    if manifest_error is not None or manifest_bytes is None:
        raise ValueError(f"current release channel is {manifest_error or 'unreadable'}")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("current release channel is invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("current release channel is not a JSON object")

    version = str(manifest.get("releaseVersion") or manifest.get("version") or "").strip()
    channel = str(manifest.get("channel") or manifest.get("channelId") or "").strip()
    status = str(manifest.get("status") or "").strip()
    supportability = str(manifest.get("supportabilityState") or "").strip()
    rollout = str(manifest.get("rolloutState") or "").strip()
    published_at = str(manifest.get("publishedAt") or manifest.get("published_at") or "").strip()
    if not version or not channel or status != "published":
        raise ValueError("current release channel lacks a published version/channel binding")

    verifier_bytes, verifier_error = read_stable_regular_file_bytes(VERIFY_SCRIPT)
    if verifier_error is not None or verifier_bytes is None:
        raise ValueError(f"release verifier script is {verifier_error or 'unreadable'}")
    programs: list[dict[str, object]] = []
    for name, path in RELEASE_VERIFIER_BOUND_PROGRAMS:
        program_bytes, program_error = read_stable_regular_file_bytes(path)
        if program_error is not None or program_bytes is None:
            raise ValueError(f"bound release verifier program {name} is {program_error or 'unreadable'}")
        programs.append(
            {
                "name": name,
                "path": str(path.resolve()),
                "sha256": hashlib.sha256(program_bytes).hexdigest(),
                "size_bytes": len(program_bytes),
            }
        )
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    release_published_at = parse_receipt_timestamp(published_at)
    if release_published_at is None:
        raise ValueError("current release channel publishedAt is missing or invalid")
    if release_published_at > observed_at + RELEASE_VERIFIER_REPLAY_FUTURE_SKEW:
        raise ValueError("current release channel publishedAt is in the future")
    if binding_phase not in {"standalone", "start", "final"}:
        raise ValueError("release verifier binding phase is invalid")
    if execution_plan is not None:
        validate_release_execution_plan(
            execution_plan,
            now=observed_at,
            enforce_current_environment=enforce_current_environment,
        )
        execution_plan_sha256 = str(execution_plan.get("plan_sha256") or "")
        run_nonce = str(execution_plan.get("run_nonce") or "")
    else:
        execution_plan_sha256 = ""
        run_nonce = ""
    execution_result_digests = [
        str(item.get("binding_sha256") or "")
        for item in (execution_bindings or [])
    ]
    direct_receipt_result_digests = [
        str(item.get("binding_sha256") or "")
        for item in (direct_receipt_bindings or [])
    ]
    if binding_phase == "start" and (execution_result_digests or direct_receipt_result_digests):
        raise ValueError("release verifier start binding cannot contain gate results")
    if binding_phase == "final" and execution_plan is None:
        raise ValueError("release verifier final binding requires an execution plan")
    authority: dict[str, object] = {
        "contract_name": RELEASE_VERIFIER_REPLAY_BINDING_CONTRACT,
        "binding_phase": binding_phase,
        "execution_plan_sha256": execution_plan_sha256,
        "run_nonce": run_nonce,
        "execution_results_sha256": canonical_json_sha256(execution_result_digests),
        "direct_receipt_results_sha256": canonical_json_sha256(direct_receipt_result_digests),
        "release_channel_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "release_version": version,
        "release_published_at_utc": published_at,
        "channel": channel,
        "status": status,
        "supportability_state": supportability,
        "rollout_state": rollout,
        "verifier_script_sha256": hashlib.sha256(verifier_bytes).hexdigest(),
        "gate_names": list(selected_gates),
        "gate_count": len(selected_gates),
        "bound_programs": programs,
    }
    return {
        **authority,
        "generated_at_utc": observed_at.isoformat().replace("+00:00", "Z"),
        "authority_sha256": hashlib.sha256(
            json.dumps(authority, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _binding_lines(stdout: str, prefix: str) -> list[dict[str, object]]:
    encoded = [
        line[len(prefix) :].strip()
        for line in stdout.splitlines()
        if line.startswith(prefix)
    ]
    bindings: list[dict[str, object]] = []
    for value in encoded:
        try:
            binding = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"release verifier binding after {prefix.strip()} is invalid JSON") from exc
        if not isinstance(binding, dict):
            raise ValueError(f"release verifier binding after {prefix.strip()} is not a JSON object")
        bindings.append(binding)
    return bindings


def validate_release_verifier_binding_payload(
    binding: dict[str, object],
    *,
    now: datetime | None = None,
    enforce_max_age: bool = True,
    execution_plan: dict[str, object] | None = None,
    expected_phase: str | None = None,
    execution_bindings: list[dict[str, object]] | None = None,
    direct_receipt_bindings: list[dict[str, object]] | None = None,
    enforce_current_environment: bool = False,
) -> dict[str, object]:
    expected_fields = {
        "contract_name",
        "binding_phase",
        "execution_plan_sha256",
        "run_nonce",
        "execution_results_sha256",
        "direct_receipt_results_sha256",
        "generated_at_utc",
        "authority_sha256",
        "release_channel_sha256",
        "release_version",
        "release_published_at_utc",
        "channel",
        "status",
        "supportability_state",
        "rollout_state",
        "verifier_script_sha256",
        "gate_names",
        "gate_count",
        "bound_programs",
    }
    if set(binding) != expected_fields:
        raise ValueError("release verifier binding fields are incomplete or unexpected")
    if binding.get("contract_name") != RELEASE_VERIFIER_REPLAY_BINDING_CONTRACT:
        raise ValueError("release verifier binding contract is invalid")
    if expected_phase is not None and binding.get("binding_phase") != expected_phase:
        raise ValueError("release verifier binding phase is invalid")
    if tuple(normalized_string_list(binding.get("gate_names"))) != REQUIRED_RELEASE_VERIFIER_GATES:
        raise ValueError("release verifier binding gate matrix is not canonical")
    if binding.get("gate_count") != len(REQUIRED_RELEASE_VERIFIER_GATES):
        raise ValueError("release verifier binding gate count is not canonical")

    authority = {
        key: value
        for key, value in binding.items()
        if key not in {"generated_at_utc", "authority_sha256"}
    }
    authority_sha256 = hashlib.sha256(
        json.dumps(authority, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if binding.get("authority_sha256") != authority_sha256:
        raise ValueError("release verifier binding authority digest is invalid")

    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    generated_at = parse_receipt_timestamp(binding.get("generated_at_utc"))
    if generated_at is None:
        raise ValueError("release verifier binding timestamp is invalid")
    if generated_at > observed_at + RELEASE_VERIFIER_REPLAY_FUTURE_SKEW:
        raise ValueError("release verifier binding timestamp is in the future")
    if enforce_max_age and observed_at - generated_at > RELEASE_VERIFIER_REPLAY_MAX_AGE:
        raise ValueError("release verifier binding is stale")

    if execution_plan is not None:
        validate_release_execution_plan(
            execution_plan,
            now=observed_at,
            enforce_current_environment=enforce_current_environment,
        )
        if (
            binding.get("execution_plan_sha256") != execution_plan.get("plan_sha256")
            or binding.get("run_nonce") != execution_plan.get("run_nonce")
        ):
            raise ValueError("release verifier binding execution plan does not match current truth")
    elif binding.get("execution_plan_sha256") or binding.get("run_nonce"):
        raise ValueError("release verifier binding execution plan is unavailable")
    current = current_release_verifier_replay_binding(
        now=observed_at,
        execution_plan=execution_plan,
        binding_phase=str(binding.get("binding_phase") or "standalone"),
        execution_bindings=execution_bindings,
        direct_receipt_bindings=direct_receipt_bindings,
        enforce_current_environment=enforce_current_environment,
    )
    for key in expected_fields - {"generated_at_utc"}:
        if binding.get(key) != current.get(key):
            raise ValueError(f"release verifier binding {key} does not match current truth")
    return dict(binding)


RELEASE_VERIFIER_STABLE_AUTHORITY_FIELDS = (
    "contract_name",
    "execution_plan_sha256",
    "run_nonce",
    "release_channel_sha256",
    "release_version",
    "release_published_at_utc",
    "channel",
    "status",
    "supportability_state",
    "rollout_state",
    "verifier_script_sha256",
    "gate_names",
    "gate_count",
    "bound_programs",
)


def validate_start_final_release_authority(
    start_binding: dict[str, object],
    final_binding: dict[str, object],
    *,
    execution_plan: dict[str, object],
) -> None:
    """Require one immutable release authority from controller start to emit."""

    if start_binding.get("binding_phase") != "start":
        raise ValueError("release verifier start authority phase is invalid")
    if final_binding.get("binding_phase") != "final":
        raise ValueError("release verifier final authority phase is invalid")
    if any(
        start_binding.get(field) != final_binding.get(field)
        for field in RELEASE_VERIFIER_STABLE_AUTHORITY_FIELDS
    ):
        raise ValueError("release verifier authority drifted between start and final binding")
    if (
        start_binding.get("execution_plan_sha256") != execution_plan.get("plan_sha256")
        or final_binding.get("execution_plan_sha256") != execution_plan.get("plan_sha256")
        or start_binding.get("run_nonce") != execution_plan.get("run_nonce")
        or final_binding.get("run_nonce") != execution_plan.get("run_nonce")
    ):
        raise ValueError("release verifier authority is not bound to the active execution plan")
    start_at = parse_receipt_timestamp(start_binding.get("generated_at_utc"))
    final_at = parse_receipt_timestamp(final_binding.get("generated_at_utc"))
    plan_at = parse_receipt_timestamp(execution_plan.get("generated_at_utc"))
    if plan_at is None or start_at is None or final_at is None or plan_at > start_at or start_at > final_at:
        raise ValueError("release verifier plan/start/final binding timestamps are inconsistent")


def _nested_receipt_text(payload: dict[str, object], path: tuple[str, ...]) -> str:
    value: object = payload
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "").strip()


def current_release_gate_receipt_binding(
    gate_name: str,
    *,
    now: datetime | None = None,
    execution_binding: dict[str, object] | None = None,
    execution_plan: dict[str, object] | None = None,
) -> dict[str, object] | None:
    spec = next((item for item in RELEASE_VERIFIER_GATE_RECEIPTS if item[0] == gate_name), None)
    if spec is None:
        return None
    _, receipt_name, receipt_path, expected_contract, version_path, channel_path = spec
    receipt_bytes, receipt_error = read_stable_regular_file_bytes(receipt_path)
    if receipt_error is not None or receipt_bytes is None:
        raise ValueError(f"{receipt_name} direct receipt is {receipt_error or 'unreadable'}")
    try:
        payload = json.loads(receipt_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{receipt_name} direct receipt is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{receipt_name} direct receipt is not a JSON object")
    contract = str(payload.get("contract_name") or payload.get("contractName") or "").strip()
    status = normalized_token(payload.get("status"))
    if contract != expected_contract:
        raise ValueError(f"{receipt_name} direct receipt contract is not current")
    if status not in PASS_STATES:
        raise ValueError(f"{receipt_name} direct receipt is not pass")
    if normalized_string_list(payload.get("failures")) or normalized_string_list(payload.get("failed_gates")):
        raise ValueError(f"{receipt_name} direct receipt records failures")

    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    generated_text = str(
        payload.get("generated_at_utc")
        or payload.get("generatedAtUtc")
        or payload.get("generatedAt")
        or payload.get("generated_at")
        or ""
    ).strip()
    generated_at = parse_receipt_timestamp(generated_text)
    if generated_at is None:
        raise ValueError(f"{receipt_name} direct receipt timestamp is invalid")
    if generated_at > observed_at + RELEASE_VERIFIER_REPLAY_FUTURE_SKEW:
        raise ValueError(f"{receipt_name} direct receipt timestamp is in the future")
    if observed_at - generated_at > RELEASE_VERIFIER_DIRECT_RECEIPT_MAX_AGE:
        raise ValueError(f"{receipt_name} direct receipt is stale")

    release_binding = current_release_verifier_replay_binding(now=observed_at)
    release_published_at = parse_receipt_timestamp(release_binding.get("release_published_at_utc"))
    if release_published_at is not None and generated_at < release_published_at:
        raise ValueError(f"{receipt_name} direct receipt predates the current release")
    receipt_version = _nested_receipt_text(payload, version_path) if version_path else ""
    receipt_channel = _nested_receipt_text(payload, channel_path) if channel_path else ""
    if version_path and receipt_version != release_binding["release_version"]:
        raise ValueError(f"{receipt_name} direct receipt version does not match current release")
    if channel_path and receipt_channel != release_binding["channel"]:
        raise ValueError(f"{receipt_name} direct receipt channel does not match current release")
    semantic_failures = direct_receipt_semantic_validation_failures(
        gate_name,
        payload,
        receipt_path,
        observed_at=observed_at,
    )
    if semantic_failures:
        raise ValueError("; ".join(semantic_failures))
    authority_inputs: list[dict[str, object]] = []
    if gate_name == "verify_google_oauth_linking_proof":
        operator_evidence = (
            payload.get("operator_end_to_end_evidence")
            if isinstance(payload.get("operator_end_to_end_evidence"), dict)
            else {}
        )
        request_artifacts = (
            payload.get("operator_request_artifacts")
            if isinstance(payload.get("operator_request_artifacts"), dict)
            else {}
        )
        if (
            str(request_artifacts.get("release_version") or "").strip()
            != release_binding["release_version"]
            or str(request_artifacts.get("release_channel") or "").strip()
            != release_binding["channel"]
        ):
            raise ValueError("google OAuth operator request is bound to another release")
        evidence_path = Path(str(operator_evidence.get("path") or ""))
        request_path = Path(str(request_artifacts.get("request_receipt_path") or ""))
        expected_evidence_path = PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
        expected_request_path = PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
        if evidence_path.resolve() != expected_evidence_path.resolve():
            raise ValueError("google OAuth operator evidence path is not authoritative")
        if request_path.resolve() != expected_request_path.resolve():
            raise ValueError("google OAuth operator request path is not authoritative")
        evidence_observed_at = parse_receipt_timestamp(operator_evidence.get("observed_at_utc"))
        if evidence_observed_at is None or (
            release_published_at is not None and evidence_observed_at < release_published_at
        ):
            raise ValueError("google OAuth operator evidence predates the current release")
        bound_google_paths = [
            ("google_oauth_operator_evidence", evidence_path),
            ("google_oauth_operator_request", request_path),
        ]
        screenshot_paths = operator_evidence.get("screenshot_paths")
        if not isinstance(screenshot_paths, list) or len(screenshot_paths) < 2:
            raise ValueError("google OAuth operator evidence has too few screenshots")
        imported_root = (RUN_SERVICES_ROOT / ".state" / "google_oauth_linking_operator_evidence" / "imported").resolve()
        for index, value in enumerate(screenshot_paths):
            screenshot = Path(str(value or ""))
            resolved_screenshot = screenshot.resolve()
            if imported_root not in resolved_screenshot.parents:
                raise ValueError("google OAuth screenshot path is outside the governed import root")
            bound_google_paths.append((f"google_oauth_screenshot_{index + 1}", screenshot))
        for name, path in bound_google_paths:
            bound_bytes, bound_error = read_stable_regular_file_bytes(path)
            if bound_error is not None or bound_bytes is None:
                raise ValueError(f"{name} is {bound_error or 'unreadable'}")
            if name.startswith("google_oauth_screenshot_") and (
                len(bound_bytes) < 64 or not bound_bytes.startswith(b"\x89PNG\r\n\x1a\n")
            ):
                raise ValueError(f"{name} is not a substantive PNG proof")
            authority_inputs.append(
                {
                    "name": name,
                    "path": str(path.resolve()),
                    "sha256": hashlib.sha256(bound_bytes).hexdigest(),
                    "size_bytes": len(bound_bytes),
                }
            )
    if gate_name == "verify_windows_installer_visual_audit_intake_request":
        intake_path = PUBLISHED_ROOT / WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST_NAME
        try:
            intake_ok, intake_result = verify_windows_visual_intake_request_receipt(
                intake_path,
                require_pass=True,
            )
        except Exception as exc:
            raise ValueError(
                f"windows visual intake request current verifier failed: {type(exc).__name__}: {exc}"
            ) from exc
        expected_verifier_sha = normalized_sha(
            intake_result.get("visual_audit_verifier_sha256_expected")
        )
        actual_verifier_sha = normalized_sha(
            intake_result.get("visual_audit_verifier_sha256_actual")
        )
        if (
            not intake_ok
            or intake_result.get("status") != "pass"
            or not re.fullmatch(r"[0-9a-f]{64}", expected_verifier_sha)
            or expected_verifier_sha != actual_verifier_sha
            or intake_result.get("visual_audit_verifier_sha256_matches_current") is not True
        ):
            raise ValueError(
                "windows visual intake request lacks an exact current expected verifier SHA binding"
            )
        intake_bytes, intake_error = read_stable_regular_file_bytes(intake_path)
        if intake_error is not None or intake_bytes is None:
            raise ValueError(f"windows visual intake request is {intake_error or 'unreadable'}")
        authority_inputs.append(
            {
                "name": "windows_visual_audit_intake_request",
                "path": str(intake_path.resolve()),
                "sha256": hashlib.sha256(intake_bytes).hexdigest(),
                "size_bytes": len(intake_bytes),
                "expected_verifier_sha256": expected_verifier_sha,
            }
        )
    if execution_binding is not None:
        if (
            execution_binding.get("contract_name") != RELEASE_GATE_EXECUTION_BINDING_CONTRACT
            or execution_binding.get("status") != "pass"
            or execution_binding.get("gate") != gate_name
            or not re.fullmatch(
                r"[0-9a-f]{64}",
                str(execution_binding.get("binding_sha256") or ""),
            )
        ):
            raise ValueError(f"{receipt_name} gate execution binding is invalid")
        if execution_plan is None or (
            execution_binding.get("execution_plan_sha256") != execution_plan.get("plan_sha256")
            or execution_binding.get("run_nonce") != execution_plan.get("run_nonce")
        ):
            raise ValueError(f"{receipt_name} gate execution binding is not tied to the current plan")
        gate_execution_binding_sha256 = str(execution_binding["binding_sha256"])
        execution_plan_sha256 = str(execution_plan["plan_sha256"])
        run_nonce = str(execution_plan["run_nonce"])
    else:
        gate_execution_binding_sha256 = ""
        execution_plan_sha256 = ""
        run_nonce = ""
    body: dict[str, object] = {
        "contract_name": "chummer.release_gate_receipt_binding.v1",
        "gate": gate_name,
        "gate_execution_binding_sha256": gate_execution_binding_sha256,
        "execution_plan_sha256": execution_plan_sha256,
        "run_nonce": run_nonce,
        "receipt_name": receipt_name,
        "path": str(receipt_path.resolve()),
        "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "size_bytes": len(receipt_bytes),
        "receipt_contract": contract,
        "receipt_status": status,
        "receipt_verdict": str(payload.get("verdict") or "").strip(),
        "receipt_generated_at_utc": generated_text,
        "release_channel_sha256": release_binding["release_channel_sha256"],
        "release_version": release_binding["release_version"],
        "channel": release_binding["channel"],
        "authority_inputs": authority_inputs,
    }
    signed_body = {
        **body,
        "captured_at_utc": observed_at.isoformat().replace("+00:00", "Z"),
    }
    return {**signed_body, "binding_sha256": canonical_json_sha256(signed_body)}


def validate_release_gate_receipt_bindings(
    bindings: list[dict[str, object]],
    *,
    now: datetime | None = None,
    execution_plan: dict[str, object] | None = None,
    execution_bindings: list[dict[str, object]] | None = None,
    require_execution_binding: bool = False,
) -> list[dict[str, object]]:
    expected_gates = tuple(item[0] for item in RELEASE_VERIFIER_GATE_RECEIPTS)
    observed_gates = tuple(str(item.get("gate") or "") for item in bindings)
    if observed_gates != expected_gates:
        raise ValueError("release verifier direct receipt bindings are incomplete or out of order")
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    execution_by_gate = {
        str(item.get("gate") or ""): item
        for item in (execution_bindings or [])
    }
    for binding in bindings:
        gate_name = str(binding.get("gate") or "")
        execution_binding = execution_by_gate.get(gate_name)
        if require_execution_binding and execution_binding is None:
            raise ValueError(f"release verifier direct receipt execution binding is missing: {gate_name}")
        current = current_release_gate_receipt_binding(
            gate_name,
            now=observed_at,
            execution_binding=execution_binding,
            execution_plan=execution_plan,
        )
        if current is None:
            raise ValueError(f"release verifier direct receipt binding gate is unknown: {gate_name}")
        signed_body = {key: value for key, value in binding.items() if key != "binding_sha256"}
        if binding.get("binding_sha256") != canonical_json_sha256(signed_body):
            raise ValueError(f"release verifier direct receipt binding digest is invalid: {gate_name}")
        stable_fields = set(current) - {"captured_at_utc", "binding_sha256"}
        if set(binding) != set(current):
            raise ValueError(f"release verifier direct receipt binding fields changed: {gate_name}")
        for field in stable_fields:
            if binding.get(field) != current.get(field):
                raise ValueError(f"release verifier direct receipt binding drifted: {gate_name}:{field}")
        captured_at = parse_receipt_timestamp(binding.get("captured_at_utc"))
        if captured_at is None or captured_at > observed_at + RELEASE_VERIFIER_REPLAY_FUTURE_SKEW:
            raise ValueError(f"release verifier direct receipt capture timestamp is invalid: {gate_name}")
    return [dict(item) for item in bindings]


def validate_release_verifier_replay_binding(
    stdout: str,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    def parse_event_json(line: str, prefix: str) -> dict[str, object]:
        if not line.startswith(prefix):
            raise ValueError(f"global verifier replay expected {prefix.strip()}")
        try:
            parsed = json.loads(line[len(prefix) :].strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"global verifier replay {prefix.strip()} is invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"global verifier replay {prefix.strip()} is not a JSON object")
        return parsed

    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    authority_prefixes = (
        RELEASE_EXECUTION_PLAN_PREFIX,
        RELEASE_VERIFIER_START_BINDING_PREFIX,
        RELEASE_GATE_EXECUTION_BINDING_PREFIX,
        RELEASE_VERIFIER_GATE_RECEIPT_BINDING_PREFIX,
        RELEASE_VERIFIER_REPLAY_BINDING_PREFIX,
        "START ",
        "PASS ",
        READY_MARKER,
        NOT_READY_MARKER,
    )
    cursor = 0
    while cursor < len(lines) and not any(lines[cursor].startswith(prefix) for prefix in authority_prefixes):
        cursor += 1
    if cursor >= len(lines) or not lines[cursor].startswith(RELEASE_EXECUTION_PLAN_PREFIX):
        raise ValueError("global verifier replay execution plan must be the first authority event")
    execution_plan = parse_event_json(lines[cursor], RELEASE_EXECUTION_PLAN_PREFIX)
    cursor += 1
    if cursor >= len(lines):
        raise ValueError("global verifier replay start binding is missing")
    start_binding_value = parse_event_json(lines[cursor], RELEASE_VERIFIER_START_BINDING_PREFIX)
    cursor += 1
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    validate_release_execution_plan(
        execution_plan,
        now=observed_at,
        enforce_current_environment=False,
    )
    start_binding = validate_release_verifier_binding_payload(
        start_binding_value,
        now=observed_at,
        enforce_max_age=False,
        execution_plan=execution_plan,
        expected_phase="start",
        execution_bindings=[],
        direct_receipt_bindings=[],
        enforce_current_environment=False,
    )
    execution_bindings: list[dict[str, object]] = []
    receipt_bindings: list[dict[str, object]] = []
    direct_gate_names = {item[0] for item in RELEASE_VERIFIER_GATE_RECEIPTS}
    plan_gates = execution_plan.get("gates")
    if not isinstance(plan_gates, list):
        raise ValueError("global verifier replay execution plan gates are invalid")
    for index, gate_name in enumerate(REQUIRED_RELEASE_VERIFIER_GATES):
        gate = plan_gates[index]
        if not isinstance(gate, dict):
            raise ValueError(f"global verifier replay gate plan is invalid: {gate_name}")
        expected_start = f"START {gate_name} timeout={gate.get('timeout_seconds')}s"
        if cursor >= len(lines) or lines[cursor] != expected_start:
            raise ValueError(f"global verifier replay expected exact START event: {gate_name}")
        cursor += 1
        if cursor >= len(lines):
            raise ValueError(f"global verifier replay execution binding is missing: {gate_name}")
        execution_binding = parse_event_json(lines[cursor], RELEASE_GATE_EXECUTION_BINDING_PREFIX)
        if execution_binding.get("gate") != gate_name:
            raise ValueError(f"global verifier replay execution binding moved: {gate_name}")
        execution_bindings.append(execution_binding)
        cursor += 1
        if gate_name in direct_gate_names:
            if cursor >= len(lines):
                raise ValueError(f"global verifier replay direct receipt binding is missing: {gate_name}")
            direct_binding = parse_event_json(
                lines[cursor],
                RELEASE_VERIFIER_GATE_RECEIPT_BINDING_PREFIX,
            )
            if direct_binding.get("gate") != gate_name:
                raise ValueError(f"global verifier replay direct receipt binding moved: {gate_name}")
            receipt_bindings.append(direct_binding)
            cursor += 1
        expected_pass = (
            f"PASS {gate_name} execution_binding_sha256="
            f"{execution_binding.get('binding_sha256')}"
        )
        if cursor >= len(lines) or lines[cursor] != expected_pass:
            raise ValueError(f"global verifier replay expected exact PASS event: {gate_name}")
        cursor += 1
    if cursor >= len(lines):
        raise ValueError("global verifier replay final binding is missing")
    final_binding_value = parse_event_json(lines[cursor], RELEASE_VERIFIER_REPLAY_BINDING_PREFIX)
    cursor += 1
    if cursor >= len(lines) or lines[cursor] != READY_MARKER:
        raise ValueError("global verifier replay RELEASE READY must follow the final binding")
    cursor += 1
    if cursor != len(lines):
        raise ValueError("global verifier replay contains trailing events after RELEASE READY")

    execution_bindings = validate_gate_execution_bindings(
        execution_plan,
        execution_bindings,
        start_binding=start_binding,
        now=observed_at,
    )
    receipt_bindings = validate_release_gate_receipt_bindings(
        receipt_bindings,
        now=observed_at,
        execution_plan=execution_plan,
        execution_bindings=execution_bindings,
        require_execution_binding=True,
    )
    final_binding = validate_release_verifier_binding_payload(
        final_binding_value,
        now=observed_at,
        enforce_max_age=True,
        execution_plan=execution_plan,
        expected_phase="final",
        execution_bindings=execution_bindings,
        direct_receipt_bindings=receipt_bindings,
        enforce_current_environment=False,
    )
    validate_start_final_release_authority(
        start_binding,
        final_binding,
        execution_plan=execution_plan,
    )
    start_at = parse_receipt_timestamp(start_binding.get("generated_at_utc"))
    final_at = parse_receipt_timestamp(final_binding.get("generated_at_utc"))
    if start_at is None or final_at is None:
        raise ValueError("global verifier start/final binding timestamps are invalid")
    previous_at = start_at
    direct_by_gate = {str(item.get("gate") or ""): item for item in receipt_bindings}
    for execution_binding in execution_bindings:
        gate_name = str(execution_binding.get("gate") or "")
        before = parse_receipt_timestamp(execution_binding.get("captured_before_at_utc"))
        after = parse_receipt_timestamp(execution_binding.get("captured_after_at_utc"))
        if before is None or after is None or before < previous_at or after < before:
            raise ValueError(f"global verifier gate binding timestamps are out of order: {gate_name}")
        previous_at = after
        direct = direct_by_gate.get(gate_name)
        if direct is not None:
            direct_at = parse_receipt_timestamp(direct.get("captured_at_utc"))
            if direct_at is None or direct_at < previous_at:
                raise ValueError(f"global verifier direct receipt timestamp is out of order: {gate_name}")
            previous_at = direct_at
    if final_at < previous_at:
        raise ValueError("global verifier final binding predates gate completion")
    return {
        **final_binding,
        "authority_scope": DIAGNOSTIC_AUTHORITY_SCOPE,
        "authoritative": False,
        "diagnostic": True,
        "test_only": True,
        "run_start_generated_at_utc": start_binding["generated_at_utc"],
        "gate_receipt_bindings": receipt_bindings,
        "gate_execution_bindings": execution_bindings,
        "execution_plan": execution_plan,
    }


def load_replayed_release_verifier_output(path: Path, expected_sha256: str) -> tuple[str, dict[str, object]]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"global verifier output is not a file: {resolved}")
    if resolved.stat().st_mode & 0o077:
        raise ValueError("global verifier output must have mode 0600 or stricter")
    raw = resolved.read_bytes()
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or actual_sha256 != expected_sha256:
        raise ValueError("global verifier output SHA-256 mismatch")
    try:
        stdout = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("global verifier output is not valid UTF-8") from exc

    replay_binding = validate_release_verifier_replay_binding(stdout)

    progress = gate_progress_markers(stdout, "")
    started = normalized_string_list(progress.get("started_gates"))
    completed = normalized_string_list(progress.get("completed_gates"))
    saw_ready_marker, not_ready_lines = verdict_markers(stdout, "")
    failure_lines = [line.strip() for line in stdout.splitlines() if line.strip().startswith("FAIL ")]
    nonempty_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(started) < PROJECTION_RETRY_MINIMUM_COMPLETED_GATES:
        raise ValueError(
            f"global verifier replay has only {len(started)} started gates; "
            f"requires at least {PROJECTION_RETRY_MINIMUM_COMPLETED_GATES}"
        )
    if started != completed:
        raise ValueError("global verifier replay START/PASS gate order is incomplete or mismatched")
    if len(started) != len(set(started)):
        raise ValueError("global verifier replay contains duplicate gate executions")
    if failure_lines or not_ready_lines or not saw_ready_marker:
        raise ValueError("global verifier replay does not prove an unambiguous ready verdict")
    if not nonempty_lines or normalize_verdict_line(nonempty_lines[-1]) != READY_MARKER:
        raise ValueError("global verifier replay does not end with RELEASE READY")
    # Structural replay remains useful for diagnostics, but a transcript is
    # self-asserted data.  It cannot become launch authority until a protected,
    # detached execution-attestation trust root is deliberately enrolled.
    raise ValueError(
        "global verifier replay is diagnostic-only; detached signed execution-attestation "
        "trust is not enrolled"
    )


def diagnostic_artifact(kind: str, artifact: object) -> dict[str, object]:
    return {
        "authority_scope": DIAGNOSTIC_AUTHORITY_SCOPE,
        "authoritative": False,
        "diagnostic": True,
        "test_only": True,
        "kind": kind,
        "artifact": artifact,
    }


def authoritative_release_execution_plan(
    environment: dict[str, str],
    *,
    external_write_authorized: bool,
    process_containment: dict[str, object],
) -> dict[str, object]:
    specs = canonical_release_gate_specs(environment)
    gate_specs = [
        [
            str(item["name"]),
            str(item["command"]),
            str(item["cwd"]),
            str(item["timeout_seconds"]),
            "|".join(str(value) for value in item["entrypoints"]),
        ]
        for item in specs
    ]
    external_write_gates = tuple(
        str(item["name"]) for item in specs if item["external_write"] is True
    )
    governed_paths = tuple(
        [VERIFY_SCRIPT, Path(__file__).resolve()]
        + [
            Path(str(entrypoint))
            for item in specs
            for entrypoint in item["entrypoints"]
        ]
    )
    repository_roots = governed_repository_roots(governed_paths)
    for path in governed_paths:
        repository = governed_repository_root(path)
        relative_path = str(Path(os.path.abspath(path)).relative_to(repository))
        if not governed_code_path(relative_path):
            raise ValueError(
                f"canonical release entrypoint falls inside an excluded output root: {path}"
            )
    return build_release_execution_plan(
        gate_specs,
        [
            ["bash_noprofile_norc", str(TRUSTED_BASH)],
            ["python3", str(TRUSTED_PYTHON)],
            ["node", str(TRUSTED_NODE)],
            ["git", str(TRUSTED_GIT)],
        ],
        [str(ROOT), "/docker/fleet/repos/chummer-media-factory"],
        environment=current_release_execution_environment(environment),
        controller_environment=environment,
        external_write_gates=external_write_gates,
        external_write_authorized=external_write_authorized,
        governed_repositories=repository_roots,
        require_governed_code_snapshot=True,
        process_containment=process_containment,
    )


def controller_external_write_blockers(
    plan: dict[str, object],
) -> list[str]:
    gates = normalized_string_list(plan.get("external_write_gates"))
    if not gates or plan.get("external_write_authorized") is True:
        return []
    return [
        "external release writes are not authorized; rerun with the explicit "
        f"{EXTERNAL_WRITE_AUTHORIZATION_FLAG} CLI flag before executing: "
        + ", ".join(gates)
    ]


def run_controller_gate_command(
    gate: dict[str, object],
    environment: dict[str, str],
) -> dict[str, object]:
    """Spawn one gate without login/profile hooks and own its process group."""

    containment = ensure_authoritative_process_containment()
    baseline_controller_children = direct_process_children(os.getpid())
    stdout_file = tempfile.TemporaryFile()
    stderr_file = tempfile.TemporaryFile()
    argv = [
        str(TRUSTED_BASH),
        "--noprofile",
        "--norc",
        "-c",
        str(gate["command"]),
    ]
    process = subprocess.Popen(
        argv,
        cwd=Path(str(gate["cwd"])),
        env=environment,
        stdout=stdout_file,
        stderr=stderr_file,
        start_new_session=True,
    )
    process_group_id = process.pid
    tracked_descendants: dict[int, dict[str, object]] = {}
    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def cleanup_and_reraise(signum: int, _frame: object) -> None:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        lingering = gate_lingering_processes(
            process.pid,
            process_group_id,
            baseline_controller_children,
        )
        lingering.update(
            {
                pid: identity
                for pid, identity in tracked_descendants.items()
                if process_identity_is_live(identity)
            }
        )
        extinguish_gate_processes(
            process.pid,
            process_group_id,
            baseline_controller_children,
            lingering,
            grace_seconds=int(
                environment["CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS"]
            ),
            force_group=process.poll() is None,
        )
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        raise interrupted_release_verifier_signal_exception(signum)

    signal.signal(signal.SIGINT, cleanup_and_reraise)
    signal.signal(signal.SIGTERM, cleanup_and_reraise)
    timed_out = False
    lingering_at_completion: dict[int, dict[str, object]] = {}
    containment_remaining: list[dict[str, object]] = []
    try:
        deadline = time.monotonic() + int(gate["timeout_seconds"])
        while process.poll() is None:
            tracked_descendants.update(
                gate_lingering_processes(
                    process.pid,
                    process_group_id,
                    baseline_controller_children,
                )
            )
            if time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(PROCESS_POLL_INTERVAL_SECONDS)
        lingering_at_completion = gate_lingering_processes(
            process.pid,
            process_group_id,
            baseline_controller_children,
        )
        lingering_at_completion.update(
            {
                pid: identity
                for pid, identity in tracked_descendants.items()
                if process_identity_is_live(identity)
            }
        )
        containment_remaining = extinguish_gate_processes(
            process.pid,
            process_group_id,
            baseline_controller_children,
            lingering_at_completion,
            grace_seconds=int(
                environment["CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS"]
            ),
            force_group=timed_out or process.poll() is None or bool(lingering_at_completion),
        )
        if process.poll() is None:
            try:
                process.wait(
                    timeout=max(
                        1,
                        int(environment["CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS"]),
                    )
                )
            except subprocess.TimeoutExpired:
                containment_remaining.append(
                    process_identity(process.pid)
                    or {"pid": process.pid, "state": "unknown"}
                )
        final_lingering = gate_lingering_processes(
            process.pid,
            process_group_id,
            baseline_controller_children,
        )
        final_lingering.update(
            {
                pid: identity
                for pid, identity in tracked_descendants.items()
                if process_identity_is_live(identity)
            }
        )
        containment_remaining.extend(
            identity
            for pid, identity in final_lingering.items()
            if pid not in {
                int(item.get("pid") or 0) for item in containment_remaining
            }
        )
        containment_violation = bool(lingering_at_completion or containment_remaining)
        stdout = redact_release_output(read_output_file(stdout_file), environment)
        stderr = redact_release_output(read_output_file(stderr_file), environment)
        if containment_violation:
            detail = (
                "gate left descendant processes after leader completion; "
                f"observed={sorted(lingering_at_completion)} "
                f"remaining={sorted(int(item.get('pid') or 0) for item in containment_remaining)}"
            )
            stderr = f"{stderr.rstrip()}\n{detail}\n" if stderr else detail + "\n"
        returncode = 124 if timed_out else int(process.returncode or 0)
        if containment_violation and returncode == 0:
            returncode = 125
        return {
            "argv": argv,
            "returncode": returncode,
            "timed_out": timed_out,
            "stdout": stdout,
            "stderr": stderr,
            "process_containment": containment,
            "lingering_descendant_pids": sorted(lingering_at_completion),
            "containment_remaining_pids": sorted(
                int(item.get("pid") or 0) for item in containment_remaining
            ),
            "containment_violation": containment_violation,
            "tracked_descendant_pids": sorted(tracked_descendants),
        }
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        stdout_file.close()
        stderr_file.close()


def run_authoritative_release_controller(
    environment: dict[str, str],
    *,
    external_write_authorized: bool = False,
) -> dict[str, object]:
    """Own plan, process launch, waits, identity checks, and final authority."""

    environment = authoritative_controller_environment(environment)
    transcript: list[str] = []
    stderr_lines: list[str] = []
    try:
        process_containment = ensure_authoritative_process_containment()
        plan = authoritative_release_execution_plan(
            environment,
            external_write_authorized=external_write_authorized,
            process_containment=process_containment,
        )
        transcript.append(
            RELEASE_EXECUTION_PLAN_PREFIX
            + json.dumps(plan, sort_keys=True, separators=(",", ":"))
        )
        validate_release_execution_plan(
            plan,
            controller_environment=environment,
        )
        start_binding = current_release_verifier_replay_binding(
            execution_plan=plan,
            binding_phase="start",
        )
        transcript.append(
            RELEASE_VERIFIER_START_BINDING_PREFIX
            + json.dumps(start_binding, sort_keys=True, separators=(",", ":"))
        )
        blockers = controller_external_write_blockers(plan)
        if blockers:
            stderr_lines.extend(blockers)
            transcript.extend([f"BLOCKED {value}" for value in blockers])
            transcript.append(NOT_READY_MARKER)
            return {
                "authority_scope": AUTHORITATIVE_CONTROLLER_SCOPE,
                "authoritative": True,
                "diagnostic": False,
                "test_only": False,
                "returncode": 77,
                "timed_out": False,
                "stdout": "\n".join(transcript) + "\n",
                "stderr": "\n".join(stderr_lines) + "\n",
                "validated_release_binding": {},
                "external_write_authorized": False,
            }

        execution_bindings: list[dict[str, object]] = []
        receipt_bindings: list[dict[str, object]] = []
        for gate_name in REQUIRED_RELEASE_VERIFIER_GATES:
            # Every checkpoint reopens and rehashes roots, every ancestor,
            # interpreters, authority programs, and this gate's entrypoints.
            validate_release_execution_plan(
                plan,
                controller_environment=environment,
            )
            gate = release_execution_gate(plan, gate_name)
            prebinding = current_gate_execution_prebinding(
                plan,
                gate_name,
                start_binding,
            )
            transcript.append(
                f"START {gate_name} timeout={gate['timeout_seconds']}s"
            )
            gate_result = run_controller_gate_command(
                gate,
                controller_gate_environment(gate_name, environment),
            )
            validate_release_execution_plan(
                plan,
                controller_environment=environment,
            )
            if gate_result["returncode"] != 0:
                failure = (
                    f"FAIL {gate_name}: timed out after {gate['timeout_seconds']}s"
                    if gate_result["timed_out"]
                    else f"FAIL {gate_name}"
                )
                transcript.append(failure)
                if gate_result["stdout"]:
                    transcript.append(str(gate_result["stdout"]).rstrip("\n"))
                if gate_result["stderr"]:
                    stderr_lines.append(str(gate_result["stderr"]).rstrip("\n"))
                transcript.append(NOT_READY_MARKER)
                return {
                    "authority_scope": AUTHORITATIVE_CONTROLLER_SCOPE,
                    "authoritative": True,
                    "diagnostic": False,
                    "test_only": False,
                    "returncode": int(gate_result["returncode"]),
                    "timed_out": bool(gate_result["timed_out"]),
                    "stdout": "\n".join(transcript) + "\n",
                    "stderr": "\n".join(stderr_lines) + ("\n" if stderr_lines else ""),
                    "validated_release_binding": {},
                    "external_write_authorized": external_write_authorized,
                }
            execution_binding = complete_gate_execution_binding(plan, prebinding)
            execution_bindings.append(execution_binding)
            transcript.append(
                RELEASE_GATE_EXECUTION_BINDING_PREFIX
                + json.dumps(execution_binding, sort_keys=True, separators=(",", ":"))
            )
            receipt_binding = current_release_gate_receipt_binding(
                gate_name,
                execution_binding=execution_binding,
                execution_plan=plan,
            )
            if receipt_binding is not None:
                receipt_bindings.append(receipt_binding)
                transcript.append(
                    RELEASE_VERIFIER_GATE_RECEIPT_BINDING_PREFIX
                    + json.dumps(receipt_binding, sort_keys=True, separators=(",", ":"))
                )
            transcript.append(
                f"PASS {gate_name} execution_binding_sha256="
                f"{execution_binding['binding_sha256']}"
            )

        # Final checkpoint is independent of the after-wait checkpoint for the
        # last gate and catches any higher-ancestor swap/restore before emit.
        validate_release_execution_plan(
            plan,
            controller_environment=environment,
        )
        execution_bindings = validate_gate_execution_bindings(
            plan,
            execution_bindings,
            start_binding=start_binding,
        )
        receipt_bindings = validate_release_gate_receipt_bindings(
            receipt_bindings,
            execution_plan=plan,
            execution_bindings=execution_bindings,
            require_execution_binding=True,
        )
        final_binding = current_release_verifier_replay_binding(
            execution_plan=plan,
            binding_phase="final",
            execution_bindings=execution_bindings,
            direct_receipt_bindings=receipt_bindings,
        )
        validate_start_final_release_authority(
            start_binding,
            final_binding,
            execution_plan=plan,
        )
        validate_release_verifier_binding_payload(
            final_binding,
            execution_plan=plan,
            expected_phase="final",
            execution_bindings=execution_bindings,
            direct_receipt_bindings=receipt_bindings,
            enforce_current_environment=True,
        )
        transcript.append(
            RELEASE_VERIFIER_REPLAY_BINDING_PREFIX
            + json.dumps(final_binding, sort_keys=True, separators=(",", ":"))
        )
        transcript.append(READY_MARKER)
        validated = {
            **final_binding,
            "start_binding": start_binding,
            "run_start_generated_at_utc": start_binding["generated_at_utc"],
            "gate_receipt_bindings": receipt_bindings,
            "gate_execution_bindings": execution_bindings,
            "execution_plan": plan,
        }
        return {
            "authority_scope": AUTHORITATIVE_CONTROLLER_SCOPE,
            "authoritative": True,
            "diagnostic": False,
            "test_only": False,
            "returncode": 0,
            "timed_out": False,
            "stdout": "\n".join(transcript) + "\n",
            "stderr": "",
            "validated_release_binding": validated,
            "external_write_authorized": external_write_authorized,
        }
    except (OSError, ValueError) as exc:
        stderr_lines.append(
            redact_release_output(
                f"release controller rejected execution: {exc}",
                environment,
            )
        )
        transcript.append(NOT_READY_MARKER)
        return {
            "authority_scope": AUTHORITATIVE_CONTROLLER_SCOPE,
            "authoritative": True,
            "diagnostic": False,
            "test_only": False,
            "returncode": 1,
            "timed_out": False,
            "stdout": "\n".join(transcript) + "\n",
            "stderr": "\n".join(stderr_lines) + "\n",
            "validated_release_binding": {},
            "external_write_authorized": external_write_authorized,
        }


def revalidate_authoritative_release_result(
    validated_release_binding: dict[str, object],
    environment: dict[str, str],
) -> None:
    """Recheck every live authority input immediately before atomic publish."""

    execution_plan = validated_release_binding.get("execution_plan")
    start_binding = validated_release_binding.get("start_binding")
    execution_bindings = validated_release_binding.get("gate_execution_bindings")
    receipt_bindings = validated_release_binding.get("gate_receipt_bindings")
    final_binding = {
        key: value
        for key, value in validated_release_binding.items()
        if key
        not in {
            "start_binding",
            "run_start_generated_at_utc",
            "gate_receipt_bindings",
            "gate_execution_bindings",
            "execution_plan",
        }
    }
    if (
        not isinstance(execution_plan, dict)
        or not isinstance(start_binding, dict)
        or not isinstance(execution_bindings, list)
        or not isinstance(receipt_bindings, list)
    ):
        raise ValueError("authoritative release result is missing bound controller evidence")
    validate_release_execution_plan(
        execution_plan,
        controller_environment=environment,
    )
    validated_execution_bindings = validate_gate_execution_bindings(
        execution_plan,
        [dict(item) for item in execution_bindings if isinstance(item, dict)],
        start_binding=start_binding,
    )
    validated_receipt_bindings = validate_release_gate_receipt_bindings(
        [dict(item) for item in receipt_bindings if isinstance(item, dict)],
        execution_plan=execution_plan,
        execution_bindings=validated_execution_bindings,
        require_execution_binding=True,
    )
    validate_release_verifier_binding_payload(
        start_binding,
        enforce_max_age=True,
        execution_plan=execution_plan,
        expected_phase="start",
        execution_bindings=[],
        direct_receipt_bindings=[],
        enforce_current_environment=True,
    )
    validate_release_verifier_binding_payload(
        final_binding,
        execution_plan=execution_plan,
        expected_phase="final",
        execution_bindings=validated_execution_bindings,
        direct_receipt_bindings=validated_receipt_bindings,
        enforce_current_environment=True,
    )
    validate_start_final_release_authority(
        start_binding,
        final_binding,
        execution_plan=execution_plan,
    )


def run_release_verifier(env: dict[str, str]) -> tuple[int, bool, str, str]:
    result = run_authoritative_release_controller(env)
    return (
        int(result["returncode"]),
        bool(result["timed_out"]),
        str(result["stdout"]),
        str(result["stderr"]),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize the release-ready receipt from the global release verifier.",
    )
    parser.add_argument(
        "--force-global-verifier",
        action="store_true",
        help="Run the hour-scale global release verifier even when current receipts already prove blockers.",
    )
    parser.add_argument(
        "--run-authoritative-controller",
        action="store_true",
        help="Run the controller-owned canonical gate plan and emit its live result.",
    )
    parser.add_argument(
        EXTERNAL_WRITE_AUTHORIZATION_FLAG,
        action="store_true",
        help=(
            "Explicitly authorize canonical gates classified as external writes for this "
            "controller invocation; this choice is bound into the execution plan and receipt."
        ),
    )
    parser.add_argument(
        "--global-verifier-output",
        type=Path,
        help=(
            "Parse a verifier transcript for diagnostics only. Launch authority remains disabled "
            "until detached signed execution-attestation trust is enrolled."
        ),
    )
    parser.add_argument(
        "--global-verifier-output-sha256",
        default="",
        help="Required SHA-256 binding for --global-verifier-output.",
    )
    parser.add_argument(
        "--retry-release-truth-projection",
        action="store_true",
        help=(
            "Retry only derived release-truth convergence from a fresh receipt that proves the global "
            "verifier passed every gate and failed solely during projection."
        ),
    )
    parser.add_argument(
        "--skip-windows-runtime-refresh",
        action="store_true",
        help=(
            "Reuse the current Windows auto-import and watcher receipts instead of refreshing them "
            "while materializing the release-ready receipt."
        ),
    )
    parser.add_argument(
        "--skip-google-oauth-runtime-refresh",
        action="store_true",
        help=(
            "Reuse and verify the current Google OAuth request/proof receipts instead of "
            "probing or refreshing the live sign-in flow."
        ),
    )
    parser.add_argument(
        "--emit-release-verifier-binding",
        action="store_true",
        help="Print a pure local authority binding for the aggregate verifier and exit.",
    )
    parser.add_argument(
        "--release-verifier-binding-phase",
        choices=("standalone", "start", "final"),
        default="standalone",
        help="Authority-binding phase for --emit-release-verifier-binding.",
    )
    parser.add_argument(
        "--emit-release-execution-plan",
        action="store_true",
        help="Print the complete nonce-bound aggregate execution plan and exit.",
    )
    parser.add_argument(
        "--release-gate-spec",
        action="append",
        nargs=5,
        default=[],
        metavar=("NAME", "COMMAND", "CWD", "TIMEOUT", "ENTRYPOINTS"),
        help="Canonical gate specification with pipe-separated explicit code entrypoints.",
    )
    parser.add_argument(
        "--release-interpreter",
        action="append",
        nargs=2,
        default=[],
        metavar=("NAME", "PATH"),
        help="Absolute no-symlink interpreter or runner binary used by the gate plan.",
    )
    parser.add_argument(
        "--release-code-root",
        action="append",
        default=[],
        metavar="PATH",
        help="Absolute declared code-owned root for explicit gate entrypoints.",
    )
    parser.add_argument(
        "--release-execution-plan-json",
        default="",
        metavar="JSON",
        help="Nonce-bound execution plan used by a pure binding operation.",
    )
    parser.add_argument(
        "--emit-release-gate-execution-prebinding",
        default="",
        metavar="GATE",
        help="Capture the current execution identities immediately before a gate.",
    )
    parser.add_argument(
        "--complete-release-gate-execution-prebinding-json",
        default="",
        metavar="JSON",
        help="Complete and verify a gate prebinding immediately after successful execution.",
    )
    parser.add_argument(
        "--release-verifier-start-binding-json",
        default="",
        metavar="JSON",
        help="Start authority binding used by a gate execution prebinding.",
    )
    parser.add_argument(
        "--validate-release-gate-execution-bindings",
        action="store_true",
        help="Validate the complete canonical gate execution binding sequence and exit.",
    )
    parser.add_argument(
        "--release-gate-execution-binding-json",
        action="append",
        default=[],
        metavar="JSON",
        help="Gate execution binding; repeat in canonical order.",
    )
    parser.add_argument(
        "--release-gate-receipt-binding-json",
        action="append",
        default=[],
        metavar="JSON",
        help="Direct receipt binding; repeat in canonical direct-receipt order.",
    )
    parser.add_argument(
        "--validate-release-verifier-binding-json",
        default="",
        help="Validate a previously captured aggregate verifier authority binding and exit.",
    )
    parser.add_argument(
        "--emit-release-gate-receipt-binding",
        default="",
        metavar="GATE",
        help="Print the current direct-receipt binding for a gate, when that gate owns one.",
    )
    parser.add_argument(
        "--validate-release-gate-receipt-binding-json",
        action="append",
        default=[],
        metavar="JSON",
        help=(
            "Validate a captured direct-receipt binding against current bytes; repeat in "
            "canonical direct-receipt gate order."
        ),
    )
    parser.add_argument(
        "--release-verifier-gate",
        action="append",
        default=[],
        help="Ordered aggregate gate name; repeat to bind and validate the complete matrix.",
    )
    args = parser.parse_args(argv)
    selected_verifier_modes = sum(
        bool(value)
        for value in (
            args.force_global_verifier,
            args.run_authoritative_controller,
            args.retry_release_truth_projection,
            args.global_verifier_output,
        )
    )
    if selected_verifier_modes > 1:
        parser.error(
            "--force-global-verifier, --run-authoritative-controller, "
            "--retry-release-truth-projection, and --global-verifier-output are mutually exclusive"
        )
    if bool(args.global_verifier_output) != bool(args.global_verifier_output_sha256):
        parser.error(
            "--global-verifier-output and --global-verifier-output-sha256 must be supplied together"
        )
    pure_binding_modes = sum(
        bool(value)
        for value in (
            args.emit_release_verifier_binding,
            args.emit_release_execution_plan,
            args.validate_release_verifier_binding_json,
            args.emit_release_gate_execution_prebinding,
            args.complete_release_gate_execution_prebinding_json,
            args.validate_release_gate_execution_bindings,
            args.emit_release_gate_receipt_binding,
            args.validate_release_gate_receipt_binding_json,
        )
    )
    if pure_binding_modes > 1 or (pure_binding_modes and selected_verifier_modes):
        parser.error("release verifier binding modes are mutually exclusive with execution modes")
    if args.release_verifier_gate and not args.emit_release_verifier_binding:
        parser.error("--release-verifier-gate requires --emit-release-verifier-binding")
    if args.release_gate_spec and not args.emit_release_execution_plan:
        parser.error("--release-gate-spec requires --emit-release-execution-plan")
    if (args.release_interpreter or args.release_code_root) and not args.emit_release_execution_plan:
        parser.error("--release-interpreter and --release-code-root require --emit-release-execution-plan")
    if args.authorize_external_release_writes and (
        pure_binding_modes
        or args.retry_release_truth_projection
        or args.global_verifier_output
    ):
        parser.error(
            f"{EXTERNAL_WRITE_AUTHORIZATION_FLAG} is accepted only by a live controller run"
        )
    return args


def current_blocker_precheck_enabled(args: argparse.Namespace) -> bool:
    return (
        not args.force_global_verifier
        and OUTPUT_PATH == DEFAULT_OUTPUT_PATH
    )


def should_refresh_release_truth_projection(release_ready: bool) -> bool:
    return release_ready and OUTPUT_PATH == DEFAULT_OUTPUT_PATH


def parse_receipt_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def projection_retry_validation_failures(
    payload: dict[str, object],
    proof_refresh_policy: dict[str, str],
    *,
    current_time: datetime | None = None,
    controller_environment: dict[str, str] | None = None,
) -> list[str]:
    failures: list[str] = [
        "projection retry is offline replay and remains disabled until protected detached "
        "controller execution-attestation trust is enrolled"
    ]
    if OUTPUT_PATH != DEFAULT_OUTPUT_PATH:
        failures.append("projection retry is allowed only for the authoritative release-ready receipt")
    if payload.get("contract_name") != "chummer.release_ready":
        failures.append("receipt contract_name is not chummer.release_ready")
    if payload.get("status") != "fail" or payload.get("verdict") != "NOT_RELEASE_READY":
        failures.append("receipt is not a failed release-ready result")
    returncode = payload.get("returncode")
    if not isinstance(returncode, int) or isinstance(returncode, bool) or returncode != 0:
        failures.append("global verifier returncode is not zero")
    if payload.get("timed_out") is not False:
        failures.append("global verifier timed_out is not false")
    if payload.get("saw_release_ready_marker") is not True:
        failures.append("global verifier RELEASE READY marker is missing")
    if normalized_string_list(payload.get("not_release_ready_markers")):
        failures.append("global verifier emitted NOT RELEASE READY markers")
    if payload.get("global_verifier_skipped_due_current_blockers") is not False:
        failures.append("global verifier was skipped")
    if (
        payload.get("authority_scope") != AUTHORITATIVE_CONTROLLER_SCOPE
        or payload.get("authoritative") is not True
        or payload.get("diagnostic") is not False
        or payload.get("test_only") is not False
    ):
        failures.append("receipt is not authoritative live-controller output")

    started_gates = normalized_string_list(payload.get("started_gates"))
    completed_gates = normalized_string_list(payload.get("completed_gates"))
    if tuple(started_gates) != REQUIRED_RELEASE_VERIFIER_GATES:
        failures.append("started global gate list is not the canonical complete matrix")
    if tuple(completed_gates) != REQUIRED_RELEASE_VERIFIER_GATES:
        failures.append("completed global gate list is not the canonical complete matrix")
    if completed_gates and payload.get("last_completed_gate") != completed_gates[-1]:
        failures.append("last_completed_gate does not match the completed gate list")

    receipt_failures = normalized_string_list(payload.get("failures"))
    if not receipt_failures or any(
        not failure.startswith("FAIL release_truth_projection_refresh:")
        for failure in receipt_failures
    ):
        failures.append("receipt contains a failure outside release-truth projection")
    if normalized_string_list(payload.get("failed_gates")) != ["release_truth_projection_refresh"]:
        failures.append("failed_gates is not projection-only")
    projection = payload.get("release_truth_projection_refresh")
    if not isinstance(projection, dict) or projection.get("status") != "fail":
        failures.append("failed release-truth projection receipt is missing")
    if payload.get("proof_refresh_policy") != proof_refresh_policy:
        failures.append("requested proof refresh policy does not match the verified run")

    binding = payload.get("release_verifier_binding")
    execution_plan = payload.get("release_execution_plan")
    execution_bindings = payload.get("release_verifier_gate_execution_bindings")
    direct_bindings = payload.get("release_verifier_gate_receipt_bindings")
    validated_execution_bindings: list[dict[str, object]] = []
    validated_direct_bindings: list[dict[str, object]] = []
    if not isinstance(execution_plan, dict):
        failures.append("release execution plan is missing")
    else:
        try:
            validate_release_execution_plan(
                execution_plan,
                now=current_time,
                enforce_current_environment=False,
                controller_environment=(
                    controller_environment
                    if execution_plan.get("governed_code_snapshot_required") is True
                    else None
                ),
            )
        except ValueError as exc:
            failures.append(f"release execution plan is invalid: {exc}")
    if not isinstance(execution_bindings, list):
        failures.append("release verifier gate execution bindings are missing")
    elif isinstance(execution_plan, dict):
        try:
            validated_execution_bindings = validate_gate_execution_bindings(
                execution_plan,
                [dict(item) for item in execution_bindings if isinstance(item, dict)],
                now=current_time,
            )
        except ValueError as exc:
            failures.append(f"release verifier gate execution bindings are invalid: {exc}")
    if not isinstance(direct_bindings, list):
        failures.append("release verifier direct receipt bindings are missing")
    elif isinstance(execution_plan, dict):
        try:
            validated_direct_bindings = validate_release_gate_receipt_bindings(
                [dict(item) for item in direct_bindings if isinstance(item, dict)],
                now=current_time,
                execution_plan=execution_plan,
                execution_bindings=validated_execution_bindings,
                require_execution_binding=True,
            )
        except ValueError as exc:
            failures.append(f"release verifier direct receipt bindings are invalid: {exc}")
    if not isinstance(binding, dict):
        failures.append("release verifier authority binding is missing")
    else:
        try:
            validate_release_verifier_binding_payload(
                binding,
                now=current_time,
                execution_plan=execution_plan if isinstance(execution_plan, dict) else None,
                expected_phase="final",
                execution_bindings=validated_execution_bindings,
                direct_receipt_bindings=validated_direct_bindings,
                enforce_current_environment=False,
            )
        except ValueError as exc:
            failures.append(f"release verifier authority binding is invalid: {exc}")

    generated_at = parse_receipt_timestamp(payload.get("generated_at_utc"))
    now = (current_time or datetime.now(UTC)).astimezone(UTC)
    if generated_at is None:
        failures.append("generated_at_utc is missing or invalid")
    else:
        age = now - generated_at
        if age < timedelta(minutes=-5) or age > PROJECTION_RETRY_MAX_AGE:
            failures.append("projection-only failure receipt is not fresh enough to retry")
    return failures


def projection_step_environment(environment: dict[str, str]) -> dict[str, str]:
    """Projection is local-only and receives no provider credential family."""

    return dict(
        sorted(
            (key, value)
            for key, value in environment.items()
            if key not in RELEASE_PROVIDER_ENV_KEYS
        )
    )


def projection_step_prebinding(
    name: str,
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    execution_plan: dict[str, object],
) -> dict[str, object]:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError("release projection step name is invalid")
    try:
        entrypoint = isolated_python_script(command)
    except ValueError as exc:
        raise ValueError(
            f"release projection step lacks the isolated trusted Python interpreter: {name}"
        ) from exc
    normalized_cwd = absolute_nonsymlink_path(cwd, require_directory=True)
    if not entrypoint.is_absolute():
        entrypoint = normalized_cwd / entrypoint
    entrypoint = absolute_nonsymlink_path(entrypoint)
    repository = governed_repository_root(entrypoint)
    relative = str(entrypoint.relative_to(repository))
    if not governed_code_path(relative):
        raise ValueError(f"release projection entrypoint is outside governed code: {name}")
    governed_snapshot = execution_plan.get("governed_code_snapshot")
    snapshot_repositories = (
        governed_snapshot.get("repositories")
        if isinstance(governed_snapshot, dict)
        else None
    )
    bound_repository_roots = {
        Path(str(item.get("root", {}).get("path") or ""))
        for item in (snapshot_repositories or [])
        if isinstance(item, dict) and isinstance(item.get("root"), dict)
    }
    if repository not in bound_repository_roots:
        raise ValueError(f"release projection entrypoint repository is not plan-governed: {name}")
    command_text = shlex.join(command)
    body: dict[str, object] = {
        "contract_name": "chummer.release_projection_step_prebinding.v1",
        "name": name,
        "run_nonce": execution_plan["run_nonce"],
        "execution_plan_sha256": execution_plan["plan_sha256"],
        "command": command_text,
        "command_sha256": hashlib.sha256(command_text.encode("utf-8")).hexdigest(),
        "cwd": directory_execution_identity(normalized_cwd),
        "interpreter": regular_file_execution_identity(TRUSTED_PYTHON),
        "entrypoint": regular_file_execution_identity(entrypoint),
        "timeout_seconds": PROJECTION_STEP_TIMEOUT_SECONDS,
        "environment_keys": sorted(environment),
        "environment_value_sha256": controller_environment_value_digests(environment),
        "external_write": False,
        "external_write_authorized": bool(execution_plan.get("external_write_authorized")),
        "outputs": {
            "authoritative_receipt": str(OUTPUT_PATH),
            "non_authoritative_staging_receipt": str(projection_staging_path()),
        },
    }
    captured = {**body, "captured_before_at_utc": now_iso()}
    return {**captured, "prebinding_sha256": canonical_json_sha256(captured)}


def refresh_release_truth_projection(
    env: dict[str, str],
    execution_plan: dict[str, object] | None = None,
) -> dict[str, object]:
    return run_release_truth_projection_step(
        "release_truth_root",
        isolated_python_argv(RELEASE_TRUTH_SYNC_SCRIPT),
        ROOT,
        env,
        execution_plan=execution_plan,
    )


def run_release_truth_projection_step(
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    *,
    allow_failure: bool = False,
    execution_plan: dict[str, object] | None = None,
) -> dict[str, object]:
    refresh_env = projection_step_environment(env)
    refresh_env.setdefault("PATH", TRUSTED_PATH)
    refresh_env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    refresh_env.setdefault("PYTHONNOUSERSITE", "1")
    refresh_env.setdefault("CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS", "30")
    refresh_env["CHUMMER_SKIP_RELEASE_WRAPPER_REFRESH"] = "1"
    refresh_env["CHUMMER_SKIP_CODEX_HANDOFF_MATERIALIZER"] = "1"
    refresh_env["CHUMMER_SKIP_PUBLIC_GUIDE_VERIFICATION"] = "1"
    prebinding: dict[str, object] = {}
    try:
        if execution_plan is not None:
            validate_release_execution_plan(
                execution_plan,
                controller_environment=env,
            )
            prebinding = projection_step_prebinding(
                name,
                command,
                cwd,
                refresh_env,
                execution_plan,
            )
        completed = run_controller_gate_command(
            {
                "command": shlex.join(command),
                "cwd": str(cwd),
                "timeout_seconds": PROJECTION_STEP_TIMEOUT_SECONDS,
            },
            refresh_env,
        )
        if (
            execution_plan is not None
            and completed.get("process_containment")
            != execution_plan.get("process_containment")
        ):
            raise ValueError(f"release projection process containment drifted: {name}")
        if execution_plan is not None:
            validate_release_execution_plan(
                execution_plan,
                controller_environment=env,
            )
            current = projection_step_prebinding(
                name,
                command,
                cwd,
                refresh_env,
                execution_plan,
            )
            stable_fields = set(prebinding) - {"captured_before_at_utc", "prebinding_sha256"}
            if any(prebinding.get(field) != current.get(field) for field in stable_fields):
                raise ValueError(f"release projection step authority drifted: {name}")
    except (FileNotFoundError, OSError, ValueError) as exc:
        return {
            "name": name,
            "command": shlex.join(command),
            "returncode": None,
            "status": "fail",
            "allow_failure": allow_failure,
            "error": redact_release_output(str(exc), refresh_env),
            "stdout_tail": [],
            "stderr_tail": [],
        }
    return {
        "name": name,
        "command": shlex.join(command),
        "returncode": completed["returncode"],
        "status": (
            "pass"
            if completed["returncode"] == 0
            else "allowed_failure" if allow_failure else "fail"
        ),
        "allow_failure": allow_failure,
        "error": "",
        "stdout_tail": str(completed["stdout"]).splitlines()[-20:],
        "stderr_tail": str(completed["stderr"]).splitlines()[-20:],
        "process_containment": completed.get("process_containment", {}),
        "containment_violation": bool(completed.get("containment_violation")),
        "prebinding": prebinding,
        "completed_at_utc": now_iso(),
    }


def converge_release_truth_dependents(
    env: dict[str, str],
    *,
    final_pass: bool,
    execution_plan: dict[str, object] | None = None,
) -> dict[str, object]:
    refresh_env = dict(env)
    refresh_env["CHUMMER_SKIP_RELEASE_WRAPPER_REFRESH"] = "1"
    refresh_env["CHUMMER_SKIP_CODEX_HANDOFF_MATERIALIZER"] = "1"
    refresh_env["CHUMMER_SKIP_PUBLIC_GUIDE_VERIFICATION"] = "1"
    steps: list[tuple[str, list[str], Path, bool]] = []
    if final_pass:
        steps.extend(
            [
                (
                    "mobile_cross_surface_readiness",
                    isolated_python_argv(
                        "scripts/materialize_mobile_cross_surface_readiness.py"
                    ),
                    CHUMMER_PLAY_ROOT,
                    False,
                ),
                (
                    "mobile_release_boundary",
                    isolated_python_argv("scripts/materialize_mobile_release_boundary.py"),
                    CHUMMER_PLAY_ROOT,
                    False,
                ),
                (
                    "mobile_local_release_proof",
                    isolated_python_argv("scripts/materialize_mobile_local_release_proof.py"),
                    CHUMMER_PLAY_ROOT,
                    False,
                ),
            ]
        )
    steps.extend(
        [
            (
                "operator_release_dashboard",
                isolated_python_argv(
                    "scripts/materialize_operator_release_dashboard.py",
                    "--skip-windows-runtime-refresh",
                ),
                RUN_SERVICES_ROOT,
                not final_pass,
            ),
            (
                "final_gold_janitor",
                isolated_python_argv(
                    "scripts/final_gold_janitor.py",
                    "--skip-materializers",
                    "--skip-windows-runtime-refresh",
                ),
                RUN_SERVICES_ROOT,
                False,
            ),
            (
                "flagship_product_readiness",
                isolated_python_argv(
                    "scripts/verify_flagship_product_readiness_gate.py",
                    "--summary-output",
                    ".codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json",
                ),
                RUN_SERVICES_ROOT,
                False,
            ),
            (
                "release_truth_projection",
                isolated_python_argv(RELEASE_TRUTH_SYNC_SCRIPT),
                ROOT,
                False,
            ),
        ]
    )
    results: list[dict[str, object]] = []
    for name, command, cwd, allow_failure in steps:
        result = run_release_truth_projection_step(
            name,
            command,
            cwd,
            refresh_env,
            allow_failure=allow_failure,
            execution_plan=execution_plan,
        )
        results.append(result)
        if result["status"] == "fail":
            break
    return {
        "status": "pass" if all(result["status"] != "fail" for result in results) else "fail",
        "phase": "final" if final_pass else "wrapper_cycle",
        "steps": results,
    }


def current_projection_blocker_failures(
    blocking_gate_artifacts: dict[str, dict[str, object]],
    receipt_states: dict[str, dict[str, object]],
    root_context: dict[str, object],
) -> list[str]:
    """Return current truth that is incompatible with a ready projection."""

    failures = [
        f"FAIL current_release_truth: root blocker remains: {blocker_id}"
        for blocker_id in normalized_string_list(root_context.get("root_blocker_ids"))
    ]
    blocking_statuses = {"blocked", "fail", "failed", "invalid", "missing", "not_ready"}
    for name, artifact in sorted(blocking_gate_artifacts.items()):
        if name == "release_truth_root" or not isinstance(artifact, dict):
            continue
        status = normalized_token(artifact.get("status"))
        if status in blocking_statuses or artifact.get("pass") is False:
            failures.append(
                f"FAIL current_release_truth: blocking gate artifact is not pass: {name}"
            )
    allowed_receipt_statuses = {*PASS_STATES, "not_required", "published"}
    for name, state in sorted(receipt_states.items()):
        if not isinstance(state, dict):
            continue
        status = normalized_token(state.get("status"))
        load_status = normalized_token(state.get("load_status"))
        if load_status in {"invalid", "missing"} or status not in allowed_receipt_statuses:
            failures.append(
                f"FAIL current_release_truth: current receipt is not pass: {name}"
            )
    return list(dict.fromkeys(failures))


def apply_current_release_truth_projection(
    payload: dict[str, object],
    release_channel: dict[str, object],
    *,
    enforce_status_consistency: bool = True,
) -> list[str]:
    blocking_gate_artifacts = current_blocking_gate_artifacts(
        refresh_windows_runtime_receipts=False
    )
    root_context = current_release_truth_root_context()
    receipt_states = current_receipt_states()
    payload.update(
        {
            "generated_at_utc": now_iso(),
            "blocking_gate_artifacts": blocking_gate_artifacts,
            "current_receipt_states": receipt_states,
            "root_blocker_ids": root_context["root_blocker_ids"],
            "root_blockers": root_context["root_blockers"],
            "root_blockers_generated_at": root_context["root_blockers_generated_at"],
            "stable_promotion_command": root_context["stable_promotion_command"],
            "post_promotion_verify_command": root_context["post_promotion_verify_command"],
            "root_release_truth_source": root_context["root_release_truth_source"],
        }
    )
    if not enforce_status_consistency:
        actions = release_ready_next_actions(
            blocking_gate_artifacts,
            release_channel,
            root_context,
        )
        apply_release_ready_actions(payload, actions)
        return []
    consistency_failures = current_projection_blocker_failures(
        blocking_gate_artifacts,
        receipt_states,
        root_context,
    )
    if consistency_failures:
        failures = normalized_string_list(payload.get("failures"))
        failures.extend(
            failure for failure in consistency_failures if failure not in failures
        )
        payload.update(
            {
                "status": "fail",
                "verdict": "NOT_RELEASE_READY",
                "failures": failures,
                "failed_gates": extract_failed_gates(failures),
            }
        )
    actions = release_ready_next_actions(
        blocking_gate_artifacts,
        release_channel,
        root_context,
    )
    if consistency_failures:
        if not actions:
            blocker_summary = "; ".join(
                failure.removeprefix("FAIL current_release_truth: ")
                for failure in consistency_failures
            )
            actions = [
                "Resolve the current release-truth blockers "
                f"({blocker_summary}), then rerun: {supported_release_controller_command()}"
            ]
    apply_release_ready_actions(payload, actions)
    return consistency_failures


def converge_release_truth_projection(
    payload: dict[str, object],
    release_channel: dict[str, object],
    env: dict[str, str],
    *,
    execution_plan: dict[str, object] | None = None,
) -> dict[str, object]:
    if OUTPUT_PATH == DEFAULT_OUTPUT_PATH and execution_plan is None:
        raise ValueError("authoritative release projection requires the controller execution plan")
    durable_unlink(OUTPUT_PATH)

    def write_staging(phase: str) -> None:
        staged = json.loads(json.dumps(payload))
        release_binding = payload.get("release_verifier_binding")
        if not isinstance(release_binding, dict):
            release_binding = {}
        staged.update(
            {
                "status": "in_progress",
                "verdict": "NOT_RELEASE_READY",
                "authority_scope": DIAGNOSTIC_AUTHORITY_SCOPE,
                "authoritative": False,
                "diagnostic": True,
                "test_only": False,
                "projection_staging": {
                    "status": "in_progress",
                    "phase": phase,
                    "run_nonce": str((execution_plan or {}).get("run_nonce") or ""),
                    "execution_plan_sha256": str(
                        (execution_plan or {}).get("plan_sha256") or ""
                    ),
                    "release_channel_sha256": str(
                        release_binding.get("release_channel_sha256") or ""
                    ),
                    "release_version": str(release_binding.get("release_version") or ""),
                    "authoritative_output": str(OUTPUT_PATH),
                },
            }
        )
        atomic_write_json(projection_staging_path(), staged)

    write_staging("root")
    root_refresh = refresh_release_truth_projection(env, execution_plan)
    root_refresh["phase"] = "root"
    projection_phases: list[dict[str, object]] = [root_refresh]
    if root_refresh.get("status") == "pass":
        apply_current_release_truth_projection(
            payload,
            release_channel,
            enforce_status_consistency=False,
        )
        write_staging("wrapper_cycle")
        wrapper_cycle = converge_release_truth_dependents(
            env,
            final_pass=False,
            execution_plan=execution_plan,
        )
        projection_phases.append(wrapper_cycle)
        if wrapper_cycle.get("status") == "pass":
            apply_current_release_truth_projection(
                payload,
                release_channel,
                enforce_status_consistency=False,
            )
            write_staging("final")
            projection_phases.append(
                converge_release_truth_dependents(
                    env,
                    final_pass=True,
                    execution_plan=execution_plan,
                )
            )

    projection_refresh = {
        "status": (
            "pass"
            if projection_phases and all(phase.get("status") == "pass" for phase in projection_phases)
            else "fail"
        ),
        "phases": projection_phases,
    }
    payload["release_truth_projection_refresh"] = projection_refresh
    if projection_refresh["status"] != "pass":
        failed_phase = next(
            (phase for phase in projection_phases if phase.get("status") != "pass"),
            {},
        )
        projection_error = str(failed_phase.get("error") or "").strip()
        if not projection_error:
            projection_error = f"phase={failed_phase.get('phase') or 'unknown'}"
        failure_lines = normalized_string_list(payload.get("failures"))
        projection_failure = f"FAIL release_truth_projection_refresh: {projection_error}"
        if projection_failure not in failure_lines:
            failure_lines.append(projection_failure)
        payload["status"] = "fail"
        payload["verdict"] = "NOT_RELEASE_READY"
        payload["failures"] = failure_lines
        payload["failed_gates"] = extract_failed_gates(failure_lines)
    consistency_failures = apply_current_release_truth_projection(
        payload,
        release_channel,
    )
    if consistency_failures:
        projection_refresh.update(
            {
                "status": "fail",
                "current_truth_consistency": "fail",
                "current_blocker_failures": consistency_failures,
            }
        )
    write_staging("complete_pending_authority_revalidation")
    return projection_refresh


def main(argv: list[str] | None = None) -> int:
    args = parse_args([] if argv is None else argv)
    receipt_command = supported_release_controller_command(
        force_global_verifier=args.force_global_verifier,
        external_write_authorized=args.authorize_external_release_writes,
        global_verifier_output=bool(args.global_verifier_output),
        global_verifier_output_sha256=args.global_verifier_output_sha256,
        retry_release_truth_projection=args.retry_release_truth_projection,
        skip_windows_runtime_refresh=args.skip_windows_runtime_refresh,
        skip_google_oauth_runtime_refresh=args.skip_google_oauth_runtime_refresh,
    )

    def parsed_json_object(value: str, label: str) -> dict[str, object]:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} is invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{label} is not a JSON object")
        return parsed

    def parsed_json_objects(values: list[str], label: str) -> list[dict[str, object]]:
        return [parsed_json_object(value, label) for value in values]

    if args.run_authoritative_controller:
        durable_unlink(OUTPUT_PATH)
        durable_unlink(projection_staging_path())
        try:
            controller_environment = authoritative_controller_environment(
                skip_google_oauth_runtime_refresh=args.skip_google_oauth_runtime_refresh,
                skip_windows_runtime_refresh=args.skip_windows_runtime_refresh,
            )
        except ValueError as exc:
            print(NOT_READY_MARKER)
            print(f"release controller environment rejected: {exc}", file=sys.stderr)
            return 78
        result = run_authoritative_release_controller(
            controller_environment,
            external_write_authorized=args.authorize_external_release_writes,
        )
        sys.stdout.write(str(result["stdout"]))
        sys.stderr.write(str(result["stderr"]))
        return int(result["returncode"])

    if args.emit_release_execution_plan:
        try:
            plan = build_release_execution_plan(
                args.release_gate_spec,
                args.release_interpreter,
                args.release_code_root,
            )
        except ValueError as exc:
            print(f"release execution plan rejected: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                diagnostic_artifact("release_execution_plan", plan),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if args.emit_release_verifier_binding:
        try:
            execution_plan = (
                parsed_json_object(args.release_execution_plan_json, "release execution plan")
                if args.release_execution_plan_json
                else None
            )
            execution_bindings = parsed_json_objects(
                args.release_gate_execution_binding_json,
                "release gate execution binding",
            )
            receipt_bindings = parsed_json_objects(
                args.release_gate_receipt_binding_json,
                "release gate receipt binding",
            )
            if args.release_verifier_binding_phase in {"start", "final"} and execution_plan is None:
                raise ValueError("start/final release verifier binding requires an execution plan")
            if args.release_verifier_binding_phase == "final":
                execution_bindings = validate_gate_execution_bindings(
                    execution_plan or {},
                    execution_bindings,
                )
                receipt_bindings = validate_release_gate_receipt_bindings(
                    receipt_bindings,
                    execution_plan=execution_plan,
                    execution_bindings=execution_bindings,
                    require_execution_binding=True,
                )
            binding = current_release_verifier_replay_binding(
                gate_names=args.release_verifier_gate or None,
                execution_plan=execution_plan,
                binding_phase=args.release_verifier_binding_phase,
                execution_bindings=execution_bindings,
                direct_receipt_bindings=receipt_bindings,
            )
        except ValueError as exc:
            print(f"release verifier binding rejected: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                diagnostic_artifact("release_verifier_binding", binding),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if args.validate_release_verifier_binding_json:
        try:
            parsed_binding = parsed_json_object(
                args.validate_release_verifier_binding_json,
                "release verifier binding",
            )
            execution_plan = (
                parsed_json_object(args.release_execution_plan_json, "release execution plan")
                if args.release_execution_plan_json
                else None
            )
            execution_bindings = parsed_json_objects(
                args.release_gate_execution_binding_json,
                "release gate execution binding",
            )
            receipt_bindings = parsed_json_objects(
                args.release_gate_receipt_binding_json,
                "release gate receipt binding",
            )
            validate_release_verifier_binding_payload(
                parsed_binding,
                enforce_max_age=False,
                execution_plan=execution_plan,
                expected_phase=str(parsed_binding.get("binding_phase") or ""),
                execution_bindings=execution_bindings,
                direct_receipt_bindings=receipt_bindings,
                enforce_current_environment=True,
            )
        except ValueError as exc:
            print(f"release verifier binding rejected: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                diagnostic_artifact(
                    "release_verifier_binding_validation",
                    {"status": "structurally_valid"},
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if args.emit_release_gate_execution_prebinding:
        try:
            execution_plan = parsed_json_object(
                args.release_execution_plan_json,
                "release execution plan",
            )
            start_binding = parsed_json_object(
                args.release_verifier_start_binding_json,
                "release verifier start binding",
            )
            binding = current_gate_execution_prebinding(
                execution_plan,
                args.emit_release_gate_execution_prebinding,
                start_binding,
            )
        except ValueError as exc:
            print(f"release gate execution prebinding rejected: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                diagnostic_artifact("release_gate_execution_prebinding", binding),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if args.complete_release_gate_execution_prebinding_json:
        try:
            execution_plan = parsed_json_object(
                args.release_execution_plan_json,
                "release execution plan",
            )
            prebinding = parsed_json_object(
                args.complete_release_gate_execution_prebinding_json,
                "release gate execution prebinding",
            )
            binding = complete_gate_execution_binding(execution_plan, prebinding)
        except ValueError as exc:
            print(f"release gate execution binding rejected: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                diagnostic_artifact("release_gate_execution_binding", binding),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if args.validate_release_gate_execution_bindings:
        try:
            execution_plan = parsed_json_object(
                args.release_execution_plan_json,
                "release execution plan",
            )
            execution_bindings = parsed_json_objects(
                args.release_gate_execution_binding_json,
                "release gate execution binding",
            )
            validate_gate_execution_bindings(execution_plan, execution_bindings)
        except ValueError as exc:
            print(f"release gate execution bindings rejected: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                diagnostic_artifact(
                    "release_gate_execution_binding_validation",
                    {"status": "structurally_valid"},
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if args.emit_release_gate_receipt_binding:
        try:
            execution_plan = parsed_json_object(
                args.release_execution_plan_json,
                "release execution plan",
            )
            execution_bindings = parsed_json_objects(
                args.release_gate_execution_binding_json,
                "release gate execution binding",
            )
            execution_binding = next(
                (
                    item
                    for item in execution_bindings
                    if item.get("gate") == args.emit_release_gate_receipt_binding
                ),
                None,
            )
            binding = current_release_gate_receipt_binding(
                args.emit_release_gate_receipt_binding,
                execution_binding=execution_binding,
                execution_plan=execution_plan,
            )
        except ValueError as exc:
            print(f"release gate receipt binding rejected: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                diagnostic_artifact("release_gate_receipt_binding", binding),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if args.validate_release_gate_receipt_binding_json:
        try:
            parsed_bindings = parsed_json_objects(
                args.validate_release_gate_receipt_binding_json,
                "release gate receipt binding",
            )
            execution_plan = parsed_json_object(
                args.release_execution_plan_json,
                "release execution plan",
            )
            execution_bindings = parsed_json_objects(
                args.release_gate_execution_binding_json,
                "release gate execution binding",
            )
            validate_release_gate_receipt_bindings(
                parsed_bindings,
                execution_plan=execution_plan,
                execution_bindings=execution_bindings,
                require_execution_binding=True,
            )
        except ValueError as exc:
            print(f"release gate receipt binding rejected: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                diagnostic_artifact(
                    "release_gate_receipt_binding_validation",
                    {"status": "structurally_valid"},
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if not args.retry_release_truth_projection and not args.global_verifier_output:
        durable_unlink(OUTPUT_PATH)
        durable_unlink(projection_staging_path())
    try:
        env = authoritative_controller_environment(
            skip_google_oauth_runtime_refresh=args.skip_google_oauth_runtime_refresh,
            skip_windows_runtime_refresh=args.skip_windows_runtime_refresh,
        )
    except ValueError as exc:
        publish_release_ready_materialization_failure(
            phase="controller_environment",
            reason=str(exc),
            returncode=78,
            proof_refresh_policy={
                "google_oauth": (
                    "verify_existing_receipts"
                    if args.skip_google_oauth_runtime_refresh
                    else "refresh_live_proof"
                ),
                "windows_installer": (
                    "verify_existing_receipts"
                    if args.skip_windows_runtime_refresh
                    else "refresh_runtime_receipts"
                ),
            },
            command=receipt_command,
        )
        print(f"release controller environment rejected: {exc}", file=sys.stderr)
        return 78
    proof_refresh_policy = {
        "google_oauth": (
            "verify_existing_receipts"
            if args.skip_google_oauth_runtime_refresh
            else "refresh_live_proof"
        ),
        "windows_installer": (
            "verify_existing_receipts"
            if args.skip_windows_runtime_refresh
            else "refresh_runtime_receipts"
        ),
    }
    refresh_windows_runtime_receipts = not args.skip_windows_runtime_refresh
    if args.retry_release_truth_projection:
        payload, load_status = load_json_with_status(OUTPUT_PATH)
        retry_failures = (
            [f"authoritative release-ready receipt is {load_status}"]
            if load_status != "loaded"
            else projection_retry_validation_failures(
                payload,
                proof_refresh_policy,
                controller_environment=env,
            )
        )
        if retry_failures:
            print(
                json.dumps(
                    {
                        "status": "rejected",
                        "operation": "retry_release_truth_projection",
                        "failures": retry_failures,
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1

        source_generated_at = str(payload.get("generated_at_utc") or "").strip()
        source_failures = normalized_string_list(payload.get("failures"))
        retry_actions = normalized_string_list(payload.get("nextActions"))
        if not retry_actions:
            retry_actions = normalized_string_list(payload.get("advisoryActions"))
        payload.pop("release_truth_projection_refresh", None)
        payload.update(
            {
                "generated_at_utc": now_iso(),
                "status": "pass",
                "verdict": "RELEASE_READY",
                "failures": [],
                "failed_gates": [],
                "projection_retry": {
                    "status": "in_progress",
                    "retried_at_utc": now_iso(),
                    "source_generated_at_utc": source_generated_at,
                    "source_failures": source_failures,
                    "global_gate_count": len(normalized_string_list(payload.get("completed_gates"))),
                },
            }
        )
        apply_release_ready_actions(payload, retry_actions)
        release_channel = load_json(REGISTRY_PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json")
        projection_refresh = converge_release_truth_projection(payload, release_channel, env)
        projection_retry = payload.get("projection_retry")
        if isinstance(projection_retry, dict):
            projection_retry["status"] = projection_refresh["status"]
            projection_retry["completed_at_utc"] = now_iso()
        atomic_write_json(OUTPUT_PATH, payload)
        print(f"release_ready_receipt:{payload['status']}")
        return 0

    current_blocking_failures = (
        collect_current_blocking_failures(
            refresh_windows_runtime_receipts=refresh_windows_runtime_receipts
        )
        if current_blocker_precheck_enabled(args)
        else []
    )
    if current_blocking_failures:
        failures = list(current_blocking_failures)
        failed_gates = extract_failed_gates(failures)
        blocking_gate_artifacts = current_blocking_gate_artifacts(
            refresh_windows_runtime_receipts=refresh_windows_runtime_receipts
        )
        root_context = current_release_truth_root_context()
        release_channel = load_json(REGISTRY_PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json")
        payload = {
            "contract_name": "chummer.release_ready",
            "generated_at_utc": now_iso(),
            "status": "fail",
            "verdict": "NOT_RELEASE_READY",
            "command": receipt_command,
            "returncode": None,
            "timed_out": False,
            "timeout_seconds": TIMEOUT_SECONDS,
            "saw_release_ready_marker": False,
            "not_release_ready_markers": ["current receipt precheck found launch blockers"],
            "failures": failures,
            "failed_gates": failed_gates,
            "blocking_gate_artifacts": blocking_gate_artifacts,
            "current_receipt_states": current_receipt_states(),
            "global_verifier_skipped_due_current_blockers": True,
            "global_verifier_skip_reason": "current receipts already prove launch blockers",
            "stdout_tail": [],
            "stderr_tail": [],
            "root_blocker_ids": root_context["root_blocker_ids"],
            "root_blockers": root_context["root_blockers"],
            "root_blockers_generated_at": root_context["root_blockers_generated_at"],
            "stable_promotion_command": root_context["stable_promotion_command"],
            "post_promotion_verify_command": root_context["post_promotion_verify_command"],
            "root_release_truth_source": root_context["root_release_truth_source"],
            "proof_refresh_policy": proof_refresh_policy,
        }
        apply_release_ready_actions(
            payload,
            release_ready_next_actions(blocking_gate_artifacts, release_channel, root_context),
        )
        atomic_write_json(OUTPUT_PATH, payload)
        print(f"release_ready_receipt:{payload['status']}")
        return 0
    replay_metadata: dict[str, object] | None = None
    controller_result: dict[str, object] | None = None
    if args.global_verifier_output:
        try:
            stdout, replay_metadata = load_replayed_release_verifier_output(
                args.global_verifier_output,
                args.global_verifier_output_sha256,
            )
        except ValueError as exc:
            print(f"global verifier replay rejected: {exc}", file=sys.stderr)
            return 1
        returncode, timed_out, stderr = 0, False, ""
    else:
        controller_result = run_authoritative_release_controller(
            env,
            external_write_authorized=args.authorize_external_release_writes,
        )
        returncode = int(controller_result["returncode"])
        timed_out = bool(controller_result["timed_out"])
        stdout = str(controller_result["stdout"])
        stderr = str(controller_result["stderr"])
    progress = gate_progress_markers(stdout, stderr)

    failure_lines = [
        line.strip()
        for line in [*stdout.splitlines(), *stderr.splitlines()]
        if line.strip().startswith("FAIL ") or line.strip().startswith("verify_")
    ]
    if timed_out:
        failure_lines.append(f"verify_release_ready timed out after {TIMEOUT_SECONDS}s")
        if progress["last_started_gate"]:
            failure_lines.append(
                f"verify_release_ready last started gate: {progress['last_started_gate']}"
            )
    release_channel = load_json(REGISTRY_PUBLISHED_ROOT / "RELEASE_CHANNEL.generated.json")
    failure_lines.extend(
        f"FAIL release_channel: {failure}"
        for failure in workspace_portal_release_channel_drift_failures(release_channel)
    )
    failed_gates = extract_failed_gates(failure_lines)
    saw_ready_marker, not_ready_lines = verdict_markers(stdout, stderr)
    if not_ready_lines:
        failure_lines.append("verify_release_ready printed NOT_RELEASE_READY marker")
    if not saw_ready_marker:
        failure_lines.append("verify_release_ready did not print RELEASE_READY marker")
    validated_release_binding: dict[str, object] = {}
    if returncode == 0 and saw_ready_marker and not not_ready_lines:
        if (
            controller_result is None
            or controller_result.get("authority_scope") != AUTHORITATIVE_CONTROLLER_SCOPE
            or controller_result.get("authoritative") is not True
            or controller_result.get("diagnostic") is not False
            or controller_result.get("test_only") is not False
            or not isinstance(controller_result.get("validated_release_binding"), dict)
            or not controller_result["validated_release_binding"]
        ):
            failure_lines.append(
                "FAIL release_verifier_binding: result did not originate from the live controller"
            )
        else:
            validated_release_binding = dict(
                controller_result["validated_release_binding"]
            )
    failed_gates = extract_failed_gates(failure_lines)
    release_ready = returncode == 0 and saw_ready_marker and not not_ready_lines and not failure_lines and not failed_gates
    blocking_gate_artifacts = current_blocking_gate_artifacts(
        refresh_windows_runtime_receipts=refresh_windows_runtime_receipts
    )
    root_context = current_release_truth_root_context()
    payload = {
        "contract_name": "chummer.release_ready",
        "generated_at_utc": now_iso(),
        "status": "pass" if release_ready else "fail",
        "verdict": "RELEASE_READY" if release_ready else "NOT_RELEASE_READY",
        "command": receipt_command,
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_seconds": TIMEOUT_SECONDS,
        "saw_release_ready_marker": saw_ready_marker,
        "not_release_ready_markers": not_ready_lines,
        "failures": failure_lines,
        "failed_gates": failed_gates,
        "blocking_gate_artifacts": blocking_gate_artifacts,
        "current_receipt_states": current_receipt_states(),
        "stdout_tail": stdout.splitlines()[-80:],
        "stderr_tail": stderr.splitlines()[-80:],
        "started_gates": progress["started_gates"],
        "completed_gates": progress["completed_gates"],
        "last_started_gate": progress["last_started_gate"],
        "last_completed_gate": progress["last_completed_gate"],
        "global_verifier_skipped_due_current_blockers": False,
        "root_blocker_ids": root_context["root_blocker_ids"],
        "root_blockers": root_context["root_blockers"],
        "root_blockers_generated_at": root_context["root_blockers_generated_at"],
        "stable_promotion_command": root_context["stable_promotion_command"],
        "post_promotion_verify_command": root_context["post_promotion_verify_command"],
        "root_release_truth_source": root_context["root_release_truth_source"],
        "proof_refresh_policy": proof_refresh_policy,
        "authority_scope": (
            str(controller_result.get("authority_scope") or DIAGNOSTIC_AUTHORITY_SCOPE)
            if controller_result is not None
            else DIAGNOSTIC_AUTHORITY_SCOPE
        ),
        "authoritative": bool(
            controller_result is not None
            and controller_result.get("authoritative") is True
        ),
        "diagnostic": bool(
            controller_result is None
            or controller_result.get("diagnostic") is not False
        ),
        "test_only": bool(
            controller_result is None
            or controller_result.get("test_only") is not False
        ),
        "external_release_writes_authorized": bool(
            controller_result is not None
            and controller_result.get("external_write_authorized") is True
        ),
        "release_verifier_binding": {
            key: value
            for key, value in validated_release_binding.items()
            if key
            not in {
                "run_start_generated_at_utc",
                "start_binding",
                "gate_receipt_bindings",
                "gate_execution_bindings",
                "execution_plan",
            }
        },
        "release_execution_plan": (
            validated_release_binding.get("execution_plan")
            if isinstance(validated_release_binding.get("execution_plan"), dict)
            else {}
        ),
        "release_verifier_start_generated_at_utc": str(
            validated_release_binding.get("run_start_generated_at_utc") or ""
        ),
        "release_verifier_start_binding": (
            validated_release_binding.get("start_binding")
            if isinstance(validated_release_binding.get("start_binding"), dict)
            else {}
        ),
        "release_verifier_gate_receipt_bindings": (
            validated_release_binding.get("gate_receipt_bindings")
            if isinstance(validated_release_binding.get("gate_receipt_bindings"), list)
            else []
        ),
        "release_verifier_gate_execution_bindings": (
            validated_release_binding.get("gate_execution_bindings")
            if isinstance(validated_release_binding.get("gate_execution_bindings"), list)
            else []
        ),
    }
    if replay_metadata is not None:
        payload["global_verifier_output_replay"] = {
            "status": "accepted",
            **replay_metadata,
        }
    apply_release_ready_actions(
        payload,
        release_ready_next_actions(blocking_gate_artifacts, release_channel, root_context),
    )
    if should_refresh_release_truth_projection(release_ready):
        converge_release_truth_projection(
            payload,
            release_channel,
            env,
            execution_plan=(
                validated_release_binding.get("execution_plan")
                if isinstance(validated_release_binding.get("execution_plan"), dict)
                else None
            ),
        )
    if payload.get("status") == "pass" and OUTPUT_PATH == DEFAULT_OUTPUT_PATH:
        try:
            revalidate_authoritative_release_result(validated_release_binding, env)
        except ValueError as exc:
            failure = f"FAIL release_authority_final_revalidation: {exc}"
            failures = normalized_string_list(payload.get("failures"))
            failures.append(failure)
            payload.update(
                {
                    "status": "fail",
                    "verdict": "NOT_RELEASE_READY",
                    "failures": failures,
                    "failed_gates": extract_failed_gates(failures),
                }
            )
    atomic_write_json(OUTPUT_PATH, payload)
    durable_unlink(projection_staging_path())
    print(f"release_ready_receipt:{payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
