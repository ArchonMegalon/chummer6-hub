#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


RUN_SERVICES_ROOT = Path("/docker/chummercomplete/chummer.run-services")
WORKSPACE_ROOT = Path("/docker/chummercomplete")
COMPLETION_ROOT = WORKSPACE_ROOT / "_completion" / "chummer6_absolute_completion"
INPUT_ROOT = COMPLETION_ROOT / "_inputs" / "chummer_qwen35_execution_plan_20260508"
OVERWATCH_OUT_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "out" / "absolute-audit-codexliz-overwatch"
CURRENT_RUN_DIR = OVERWATCH_OUT_ROOT / "current"
GIT_BASELINE_PATH = CURRENT_RUN_DIR / "estate-git-baseline.json"
STRICT_GATE = RUN_SERVICES_ROOT / "scripts" / "check_absolute_audit_substance.py"
RUN_LEDGER_METRICS: dict[str, tuple[int, int, int, bool]] | None = None
PASS_STATUSES = {"pass", "passed", "ready", "ok", "green"}
EXPECTED_REPO_PATHS = [
    "/docker/chummercomplete/Chummer6",
    "/docker/EA",
    "/docker/fleet",
    "/docker/chummercomplete/chummer.run-services",
    "/docker/chummercomplete/chummer-core-engine",
    "/docker/chummercomplete/chummer-presentation",
    "/docker/chummercomplete/chummer-design",
    "/docker/chummercomplete/chummer-hub-registry",
    "/docker/chummercomplete/chummer-play",
    "/docker/chummercomplete/chummer-ui-kit",
    "/docker/fleet/repos/chummer-media-factory",
]
OPTIONAL_ORACLE_PATHS = [
    "/docker/chummer5a",
    "/docker/fleet/repos/chummer4",
]
UNAVAILABLE_REQUIRED_REPOS: list[str] = []
EXPECTED_ROLE_BY_PATH = {
    "/docker/chummercomplete/Chummer6": "product",
    "/docker/EA": "executive-assistant",
    "/docker/fleet": "fleet",
    "/docker/chummercomplete/chummer.run-services": "hub",
    "/docker/chummercomplete/chummer-core-engine": "core",
    "/docker/chummercomplete/chummer-presentation": "ui",
    "/docker/chummercomplete/chummer-design": "design",
    "/docker/chummercomplete/chummer-hub-registry": "hub-registry",
    "/docker/chummercomplete/chummer-play": "mobile",
    "/docker/chummercomplete/chummer-ui-kit": "ui-kit",
    "/docker/fleet/repos/chummer-media-factory": "media-factory",
    "/docker/chummer5a": "chummer5a-oracle",
    "/docker/fleet/repos/chummer4": "chummer4-oracle",
}
REQUIRED_GATE_IDS = [
    "gate-public-no-overclaim",
    "gate-auth-account-install",
    "gate-feedback-loop",
    "gate-karma-forge",
    "gate-package-management",
    "gate-chummer5a-human-parity",
    "gate-rulesets",
    "gate-mobile-pwa",
    "gate-ltd-adapters",
]


def pass_value_to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None
PASS0_ARTIFACTS = [
    "REPO_INVENTORY.yaml",
    "CANON_TRUTH_MAP.md",
    "OWNERSHIP_TRUTH_MAP.yaml",
    "FALSE_COMPLETE_REGISTER.yaml",
    "BUG_AND_GAP_REGISTER.yaml",
    "ABSOLUTE_COMPLETION_VERDICT.md",
]
FALSE_COMPLETE_SEED_TOKENS = [
    "ui-as-engine",
    "route-as-auth",
    "screenshot-as-behavior",
    "vote-as-priority",
    "merged-code-as-release",
    "ltd-as-truth",
]
FALSE_CLAIM_SEED_TOKENS = [
    "full chummer5a parity",
    "sr4 ready",
    "sr6 ready",
    "flagship release",
    "fixed",
    "package supported",
    "votes decide roadmap",
    "public feedback is support",
    "oauth works",
    "mobile pwa works",
]
EXPECTED_COMPLETION_BRANCH = "completion/absolute-product-finish"
ROUTE_ALLOWED_STATES = {
    "implemented",
    "proven",
    "preview_bounded",
    "blocked",
    "blocked_external",
    "not_mounted",
}
PRODUCT_DOC_PATHS = [
    "/docker/chummercomplete/Chummer6/DOWNLOAD.md",
    "/docker/chummercomplete/Chummer6/STATUS.md",
]
PRODUCT_DOC_RISK_TOKENS = [
    "github.com",
    "/releases",
    "full parity",
    "sr4 ready",
    "sr6 ready",
    "flagship",
]
FALSE_CLAIM_SECTION_MARKERS = [
    "owner:",
    "current status:",
    "blocked public wording:",
    "allowed public wording:",
    "required proof:",
]
PRODUCT_DOC_GUIDE_MARKERS = [
    "current claim:",
    "target claim:",
    "owner:",
    "proof:",
]
PRODUCT_DOC_TRUTH_MARKERS = [
    "source repo:",
    "current truth:",
    "allowed public posture:",
]
VERIFICATION_COMMAND_MARKERS = [
    "owner repo:",
    "command:",
    "evidence:",
]
HORIZON_SECTION_MARKERS = [
    "status:",
    "owner:",
    "next_action:",
]
HORIZON_REQUIRED_TOKENS = [
    "horizon",
    "creator",
    "community",
    "black ledger",
    "ghostwire",
    "runsite",
    "jackpoint",
]
CANON_TRUTH_MARKERS = [
    "owner repo:",
    "implementation repo:",
    "proof:",
    "public posture:",
]
VERDICT_MARKERS = [
    "readiness:",
    "claim posture:",
    "top blockers:",
    "next slice:",
]
REQUIRED_E2E_JOURNEY_TOKENS = {
    "gate-auth-account-install": ["google auth", "email auth", "install claim", "account support history"],
    "gate-feedback-loop": ["feedback submission", "support case", "product governor", "fleet workpackage", "release proof before notify"],
    "gate-karma-forge": ["karma forge submit", "rules impact audit", "package candidate", "rollback"],
    "gate-package-management": ["package browser", "vote/follow", "install/update/revoke", "package impact"],
    "gate-mobile-pwa": ["pwa install", "offline/reconnect", "auth", "session resume", "tap target/accessibility"],
}
MARKDOWN_SEMANTIC_RULES = {
    "ABSOLUTE_GAP_AUDIT.md": ["p0:", "p1:", "owner:", "next_action:"],
    "MISSED_POTENTIAL_AUDIT.md": ["missed potential:", "owner:", "impact:", "next_action:"],
    "USER_WISH_DESIGN_EXPANSION.md": ["user wish:", "design expansion:", "owner:", "verification:"],
    "LTD_COMPLETION_MAP.md": ["status:", "adapter owner:", "required receipt:", "risk:"],
    "ABSOLUTE_PRODUCT_COMPLETION_PLAN.md": ["workstream:", "owner:", "verification:", "next_action:"],
    "FEEDBACK_TO_IMPLEMENTATION_LOOP.md": ["intake:", "ea audit:", "fleet workpackage:", "release proof:"],
    "KARMA_FORGE_PRODUCT_AND_IMPLEMENTATION_LOOP.md": ["submission:", "rules impact audit:", "package candidate:", "rollback:"],
    "PACKAGE_MANAGEMENT_AND_PUBLIC_PACKAGE_BROWSER.md": ["package model:", "public routes:", "admin routes:", "verification:"],
    "MOBILE_PWA_PRODUCT_SPEC.md": ["entry points:", "offline/reconnect:", "auth:", "verification:"],
    "E2E_TEST_PLAN.md": ["gate:", "journey:", "owner repo:", "evidence:"],
    "VERIFICATION_COMMANDS.md": ["owner repo:", "command:", "evidence:"],
    "DEV_CHANGE_GUIDE.md": ["repo:", "files:", "change:", "verification:"],
    "FALSE_CLAIM_RISK.md": ["owner:", "blocked public wording:", "allowed public wording:", "required proof:"],
    "PUBLIC_COPY_CHANGE_GUIDE.md": ["current claim:", "target claim:", "owner:", "proof:"],
    "LTD_ADAPTER_IMPLEMENTATION_GUIDE.md": ["verification:", "fallback:", "off-switch:", "required receipt:"],
    "RELEASE_RUNBOOK.md": ["preflight:", "deploy:", "verification:", "rollback:"],
    "PREMIUM_FLAGSHIP_POLISH_REPORT.md": ["polish lane:", "owner:", "verification:", "remaining gap:"],
}
RUN_LEDGER_REQUIRED_KEYS = ("run_id", "pass", "phase", "action", "status")

REQUIRED_ARTIFACTS = [
    "RUN_LEDGER.jsonl",
    "REPO_INVENTORY.yaml",
    "CANON_TRUTH_MAP.md",
    "OWNERSHIP_TRUTH_MAP.yaml",
    "ABSOLUTE_GAP_AUDIT.md",
    "MISSED_POTENTIAL_AUDIT.md",
    "USER_WISH_DESIGN_EXPANSION.md",
    "LTD_COMPLETION_MAP.md",
    "FALSE_COMPLETE_REGISTER.yaml",
    "ABSOLUTE_PRODUCT_COMPLETION_PLAN.md",
    "FEEDBACK_TO_IMPLEMENTATION_LOOP.md",
    "KARMA_FORGE_PRODUCT_AND_IMPLEMENTATION_LOOP.md",
    "PACKAGE_MANAGEMENT_AND_PUBLIC_PACKAGE_BROWSER.md",
    "MOBILE_PWA_PRODUCT_SPEC.md",
    "HORIZON_MVP_COMPLETION_MAP.yaml",
    "ABSOLUTE_RELEASE_GATES.yaml",
    "COMPLETION_BACKLOG.yaml",
    "E2E_TEST_PLAN.md",
    "E2E_RESULTS.generated.json",
    "VERIFICATION_COMMANDS.md",
    "VERIFICATION_RESULTS.generated.json",
    "BUG_AND_GAP_REGISTER.yaml",
    "DEV_CHANGE_GUIDE.md",
    "FALSE_CLAIM_RISK.md",
    "PUBLIC_COPY_CHANGE_GUIDE.md",
    "LTD_ADAPTER_IMPLEMENTATION_GUIDE.md",
    "RELEASE_RUNBOOK.md",
    "PREMIUM_FLAGSHIP_POLISH_REPORT.md",
    "ABSOLUTE_COMPLETION_VERDICT.md",
    "FINAL_NEXT_ACTIONS.yaml",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_json(command: list[str], *, cwd: Path) -> dict[str, Any]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if not result.stdout.strip():
        raise RuntimeError(f"{' '.join(command)} produced no stdout")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{' '.join(command)} did not produce a JSON object")
    return payload


def run_text(command: list[str], *, cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def build_check(*, key: str, label: str, path: Path, ok: bool, detail: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "path": str(path),
        "ok": ok,
        "detail": detail,
    }


def walk_objects(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_objects(child)


def mounted_expected_paths() -> list[Path]:
    paths = [Path(item) for item in EXPECTED_REPO_PATHS if Path(item).exists()]
    paths.extend(Path(item) for item in OPTIONAL_ORACLE_PATHS if Path(item).exists())
    return paths


def looks_like_sha(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    token = value.strip()
    if len(token) < 7 or len(token) > 40:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in token)


def repo_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("repos", "repositories"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    entries: list[dict[str, Any]] = []
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        entry = dict(value)
        entry.setdefault("name", str(key))
        entries.append(entry)
    return entries


def record_has_gate_id(payload: Any, gate_id: str) -> bool:
    if isinstance(payload, dict):
        keys = {
            str(payload.get("id") or ""),
            str(payload.get("gate_id") or ""),
            str(payload.get("key") or ""),
            str(payload.get("name") or ""),
            str(payload.get("slug") or ""),
        }
        if gate_id in keys:
            return True
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return gate_id in text


def record_is_passing(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("ok") is True or payload.get("passed") is True or payload.get("success") is True:
        return True
    status = str(payload.get("status") or payload.get("result") or payload.get("state") or payload.get("outcome") or "").strip().lower()
    return status in PASS_STATUSES


def gate_presence_in_payload(payload: Any, gate_ids: list[str], *, require_pass: bool) -> tuple[list[str], list[str]]:
    present: set[str] = set()
    passing: set[str] = set()
    for obj in walk_objects(payload):
        for gate_id in gate_ids:
            if not record_has_gate_id(obj, gate_id):
                continue
            present.add(gate_id)
            if not require_pass or record_is_passing(obj):
                passing.add(gate_id)
    missing = [gate_id for gate_id in gate_ids if gate_id not in passing]
    return sorted(present), missing


def target_public_route_paths() -> list[str]:
    path = INPUT_ROOT / "TARGET_PUBLIC_ROUTES.yaml"
    if not path.is_file():
        return []
    payload = load_yaml(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("routes"), list):
        return []
    paths: list[str] = []
    for item in payload["routes"]:
        if not isinstance(item, dict):
            continue
        route = item.get("path")
        if isinstance(route, str) and route.strip():
            paths.append(route.strip())
    return paths


def ltd_seed_entries() -> list[dict[str, Any]]:
    path = INPUT_ROOT / "LTD_COMPLETION_MAP_SEED.yaml"
    if not path.is_file():
        return []
    payload = load_yaml(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("classification"), list):
        return []
    return [item for item in payload["classification"] if isinstance(item, dict)]


def mounted_git_repo_paths() -> list[Path]:
    repos: list[Path] = []
    for path in mounted_expected_paths():
        code, stdout, _stderr = run_text(["git", "rev-parse", "--is-inside-work-tree"], cwd=path)
        if code == 0 and stdout == "true":
            repos.append(path)
    return repos


def current_git_state_map() -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for path in mounted_git_repo_paths():
        dirty_code, dirty_stdout, _dirty_stderr = run_text(["git", "status", "--porcelain"], cwd=path)
        branch_code, branch_stdout, _branch_stderr = run_text(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
        sha_code, sha_stdout, _sha_stderr = run_text(["git", "rev-parse", "HEAD"], cwd=path)
        upstream_code, upstream_stdout, _upstream_stderr = run_text(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd=path)
        ahead = behind = None
        if upstream_code == 0 and upstream_stdout:
            count_code, counts, _count_err = run_text(["git", "rev-list", "--left-right", "--count", f"HEAD...{upstream_stdout}"], cwd=path)
            if count_code == 0 and counts:
                parts = counts.split()
                if len(parts) == 2:
                    ahead, behind = parts
        results[str(path)] = {
            "dirty": dirty_code == 0 and bool(dirty_stdout),
            "branch": branch_stdout if branch_code == 0 else None,
            "head_sha": sha_stdout if sha_code == 0 else None,
            "upstream": upstream_stdout if upstream_code == 0 else None,
            "ahead": ahead,
            "behind": behind,
        }
    return results


def git_baseline_map() -> dict[str, dict[str, Any]] | None:
    baseline_path = git_baseline_path()
    if not baseline_path.is_file():
        return None
    payload = load_json(baseline_path)
    if isinstance(payload, dict) and isinstance(payload.get("repos"), list):
        items = payload["repos"]
    elif isinstance(payload, list):
        items = payload
    else:
        return None
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").rstrip("/")
        if path:
            result[path] = item
    return result or None


def current_run_started_at() -> datetime | None:
    run_id = current_run_id()
    if run_id and re.fullmatch(r"\d{8}T\d{6}Z", run_id):
        try:
            return datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            pass

    proof_root = COMPLETION_ROOT / "proofs" / str(run_id)
    if proof_root.is_dir():
        timestamps = [path.stat().st_mtime for path in proof_root.rglob("*.json")]
        if timestamps:
            return datetime.fromtimestamp(max(timestamps), tz=timezone.utc)

    baseline = git_baseline_path()
    if baseline.is_file():
        payload = load_json(baseline)
        if isinstance(payload, dict):
            started = parse_iso_datetime(str(payload.get("generated_at") or ""))
            if started is not None:
                return started
    return None


def run_ledger_metrics_by_run_id() -> dict[str, tuple[int, int, int, bool]]:
    global RUN_LEDGER_METRICS
    if RUN_LEDGER_METRICS is not None:
        return RUN_LEDGER_METRICS

    metrics: dict[str, list[int]] = {}
    ledger_path = COMPLETION_ROOT / "RUN_LEDGER.jsonl"
    if not ledger_path.is_file():
        RUN_LEDGER_METRICS = {}
        return RUN_LEDGER_METRICS
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if not isinstance(item, dict):
            continue
        run_id = str(item.get("run_id") or "").strip()
        if not re.fullmatch(r"\d{8}T\d{6}Z", run_id):
            continue
        values = metrics.setdefault(run_id, [0, 0, 0, False])
        values[0] += 1
        if (
            all(key in item for key in RUN_LEDGER_REQUIRED_KEYS)
            and pass_value_to_int(item.get("pass")) in {0, 1, 2}
            and str(item.get("phase") or "").strip()
            and str(item.get("action") or "").strip()
            and str(item.get("status") or "").strip()
        ):
            values[1] += 1
        if any(item.get(key) for key in ("repo", "repo_path", "artifacts", "proof_paths", "evidence_paths")):
            values[2] += 1
        if pass_value_to_int(item.get("pass")) == 0:
            values[3] = True
    RUN_LEDGER_METRICS = {run_id: tuple(values) for run_id, values in metrics.items()}
    return RUN_LEDGER_METRICS


def has_sufficient_run_ledger_activity(run_id: str | None) -> bool:
    if not run_id:
        return False
    parsed, structured, evidence, pass0_seen = run_ledger_metrics_by_run_id().get(run_id, (0, 0, 0, False))
    return parsed >= 1 and structured >= 1 and evidence >= 1 and pass0_seen


def current_run_id() -> str | None:
    try:
        explicit_run_dir = CURRENT_RUN_DIR.resolve().name
    except Exception:
        explicit_run_dir = ""
    candidates: list[str] = []
    if re.fullmatch(r"\d{8}T\d{6}Z", explicit_run_dir or ""):
        candidates.append(explicit_run_dir)

    completion_run_ids = []
    release_gates_path = COMPLETION_ROOT / "ABSOLUTE_RELEASE_GATES.yaml"
    if release_gates_path.is_file():
        try:
            payload = load_yaml(release_gates_path)
            configured_run_id = str(payload.get("run_id") or "").strip()
            if re.fullmatch(r"\d{8}T\d{6}Z", configured_run_id):
                completion_run_ids.append(configured_run_id)
        except Exception:
            pass

    proof_root = COMPLETION_ROOT / "proofs"
    if proof_root.is_dir():
        completion_run_ids.extend(
            path.name
            for path in proof_root.iterdir()
            if path.is_dir() and re.fullmatch(r"\d{8}T\d{6}Z", path.name)
        )
    candidates.extend(sorted(set(completion_run_ids), reverse=True))

    if not candidates:
        return explicit_run_dir or None

    for run_id in candidates:
        if has_sufficient_run_ledger_activity(run_id):
            return run_id
    return candidates[0]


def git_baseline_path() -> Path:
    run_id = current_run_id()
    if run_id:
        return OVERWATCH_OUT_ROOT / str(run_id) / "estate-git-baseline.json"
    return GIT_BASELINE_PATH


def repo_inventory_map() -> dict[str, dict[str, Any]]:
    path = COMPLETION_ROOT / "REPO_INVENTORY.yaml"
    if not path.is_file():
        return {}
    return {
        repo_path: repo
        for repo in repo_entries(load_yaml(path))
        for repo_path in [
            next(
                (
                    str(value).rstrip("/")
                    for value in (
                        repo.get("path"),
                        repo.get("mount_path"),
                        repo.get("root"),
                        repo.get("repo_path"),
                    )
                    if isinstance(value, str) and str(value).strip()
                ),
                "",
            )
        ]
        if repo_path
    }


def inventory_sha(entry: dict[str, Any]) -> str:
    return str(
        entry.get("head_sha")
        or entry.get("sha")
        or entry.get("commit")
        or entry.get("commit_sha")
        or entry.get("git_sha")
        or ""
    ).strip()


def inventory_branch(entry: dict[str, Any]) -> str:
    return str(entry.get("branch") or entry.get("git_branch") or entry.get("head_branch") or "").strip()


def inventory_dirty_state(entry: dict[str, Any]) -> bool | None:
    for key in ("dirty", "git_dirty"):
        if key not in entry:
            continue
        value = entry.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1", "dirty"}:
                return True
            if lowered in {"false", "no", "0", "clean"}:
                return False
    if "clean" in entry:
        value = entry.get("clean")
        if isinstance(value, bool):
            return not value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1", "clean"}:
                return False
            if lowered in {"false", "no", "0", "dirty"}:
                return True
    return None


def inventory_bool(entry: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key not in entry:
            continue
        value = entry.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0"}:
                return False
    return None


def window_has_markers(text: str, anchor: str, markers: list[str], *, window: int = 2200) -> bool:
    index = text.find(anchor.lower())
    if index == -1:
        return False
    segment = text[index:index + window]
    return all(marker in segment for marker in markers)


def object_matches_seed_token(obj: dict[str, Any], token: str, *, keys: tuple[str, ...]) -> bool:
    lowered = token.lower()
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and lowered in value.lower():
            return True
    return False


def text_mentions_run_id(path: Path, run_id: str) -> bool:
    if run_id in path.name or run_id in str(path.parent):
        return True
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            chunk = handle.read(131072).lower()
    except Exception:
        return False
    return run_id.lower() in chunk


def resolve_evidence_path(value: str) -> Path | None:
    candidate = Path(value)
    candidates: list[Path]
    if candidate.is_absolute():
        candidates = [candidate]
    else:
        candidates = [
            COMPLETION_ROOT / candidate,
            WORKSPACE_ROOT / candidate,
            RUN_SERVICES_ROOT / candidate,
            Path("/docker") / candidate,
        ]
    for path in candidates:
        if path.exists():
            return path
    return None


def evidence_value_to_paths(value: Any) -> list[Path]:
    results: list[Path] = []
    if isinstance(value, str):
        resolved = resolve_evidence_path(value.strip())
        if resolved is not None:
            results.append(resolved)
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, str):
                continue
            resolved = resolve_evidence_path(item.strip())
            if resolved is not None:
                results.append(resolved)
    return results


def verification_matrix_gates() -> list[dict[str, Any]]:
    path = INPUT_ROOT / "VERIFICATION_MATRIX.yaml"
    if not path.is_file():
        return []
    payload = load_yaml(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("gates"), list):
        return []
    return [item for item in payload["gates"] if isinstance(item, dict)]


def verification_matrix_commands_map() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for gate in verification_matrix_gates():
        gate_id = str(gate.get("id") or "").strip()
        commands = gate.get("commands")
        if not gate_id or not isinstance(commands, list):
            continue
        result[gate_id] = [str(item).strip() for item in commands if str(item).strip()]
    return result


def find_entry_by_key(value: Any, key_name: str, key_value: str) -> dict[str, Any] | None:
    for obj in walk_objects(value):
        if not isinstance(obj, dict):
            continue
        candidate = str(obj.get(key_name) or "").strip()
        if candidate == key_value:
            return obj
    return None


def find_gate_entry(value: Any, gate_id: str) -> dict[str, Any] | None:
    for key_name in ("gate_id", "id", "key", "name", "slug"):
        entry = find_entry_by_key(value, key_name, gate_id)
        if entry is not None:
            return entry
    return None


def extract_entry_list(entry: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        value = entry.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def command_receipt_ok(entry: dict[str, Any]) -> bool:
    if entry.get("ok") is True or entry.get("passed") is True or entry.get("success") is True:
        return True
    status = str(entry.get("status") or entry.get("result") or entry.get("state") or entry.get("outcome") or "").strip().lower()
    return status in PASS_STATUSES


def command_receipt_detail(entry: dict[str, Any]) -> bool:
    if "exit_code" in entry and entry.get("exit_code") not in (0, "0"):
        return False
    evidence = entry.get("evidence_paths") or entry.get("proof_paths") or entry.get("artifacts") or entry.get("receipts")
    evidence_paths = evidence_value_to_paths(evidence)
    return bool(evidence_paths)


def command_receipt_binding(entry: dict[str, Any], inventory: dict[str, dict[str, Any]], live_state: dict[str, dict[str, Any]]) -> bool:
    repo_path = str(entry.get("repo_path") or entry.get("path") or "").rstrip("/")
    commit_sha = str(entry.get("commit_sha") or entry.get("head_sha") or entry.get("repo_sha") or "").strip()
    generated_at = parse_iso_datetime(str(entry.get("generated_at") or entry.get("verified_at") or ""))
    evidence = entry.get("evidence_paths") or entry.get("proof_paths") or entry.get("artifacts") or entry.get("receipts")
    evidence_paths = evidence_value_to_paths(evidence)
    run_id = str(entry.get("run_id") or "").strip()
    if not repo_path or not commit_sha or generated_at is None or not evidence_paths:
        return False
    active_run_id = current_run_id()
    if not run_id or not active_run_id or run_id != active_run_id:
        return False
    run_started_at = current_run_started_at()
    if run_started_at is not None and generated_at < run_started_at:
        return False
    inventory_entry = inventory.get(repo_path)
    if inventory_entry is None:
        return False
    live_entry = live_state.get(repo_path)
    if live_entry is None:
        return False
    inventory_sha_value = inventory_sha(inventory_entry)
    if inventory_sha_value and inventory_sha_value != commit_sha:
        return False
    inventory_branch_value = inventory_branch(inventory_entry)
    live_branch_value = str(live_entry.get("branch") or "").strip()
    if inventory_branch_value and live_branch_value and inventory_branch_value != live_branch_value:
        return False
    inventory_dirty_value = inventory_dirty_state(inventory_entry)
    live_dirty_value = live_entry.get("dirty")
    if inventory_dirty_value is not None and inventory_dirty_value != live_dirty_value:
        return False
    live_sha = str(live_entry.get("head_sha") or "").strip()
    if live_sha and live_sha != commit_sha:
        return False
    freshness_floor = generated_at
    if run_started_at is not None and run_started_at > freshness_floor:
        freshness_floor = run_started_at
    if any(not text_mentions_run_id(path, active_run_id) for path in evidence_paths):
        return False
    return True


def count_high_priority_items(value: Any) -> int:
    count = 0
    for obj in walk_objects(value):
        priority = str(obj.get("priority") or obj.get("severity") or "").strip().upper()
        if priority not in {"P0", "P1"}:
            continue
        status = str(obj.get("status") or obj.get("state") or "").strip().lower()
        if status in {"done", "closed", "complete", "completed", "resolved", "retired", "not_applicable"}:
            continue
        count += 1
    return count


def artifact_exists_check() -> dict[str, Any]:
    missing = [name for name in REQUIRED_ARTIFACTS if not (COMPLETION_ROOT / name).is_file()]
    return build_check(
        key="required_artifacts",
        label="Required completion artifacts",
        path=COMPLETION_ROOT,
        ok=not missing,
        detail="all artifacts present" if not missing else f"missing {len(missing)} artifacts: {', '.join(missing)}",
    )


def pass0_control_plane_check() -> dict[str, Any]:
    missing = [name for name in PASS0_ARTIFACTS if not (COMPLETION_ROOT / name).is_file()]
    return build_check(
        key="pass0_control_plane",
        label="Pass 0 control-plane artifacts",
        path=COMPLETION_ROOT,
        ok=not missing,
        detail="all pass0 artifacts present" if not missing else f"missing {len(missing)} artifacts: {', '.join(missing)}",
    )


def run_ledger_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "RUN_LEDGER.jsonl"
    if not path.is_file():
        return build_check(key="run_ledger", label="Run ledger", path=path, ok=False, detail="missing")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    parsed = 0
    current_run_lines = 0
    structured = 0
    active_run_id = current_run_id()
    pass0_seen = False
    evidence_rows = 0
    for line in lines:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            parsed += 1
            is_current_run = bool(active_run_id) and str(item.get("run_id") or "").strip() == active_run_id
            if is_current_run:
                current_run_lines += 1
                if int(item.get("pass", -1)) == 0:
                    pass0_seen = True
                if any(item.get(key) for key in ("repo", "repo_path", "artifacts", "proof_paths", "evidence_paths")):
                    evidence_rows += 1
            timestamp = item.get("timestamp") or item.get("ts") or item.get("generated_at")
            if (
                is_current_run
                and all(key in item for key in RUN_LEDGER_REQUIRED_KEYS)
                and parse_iso_datetime(str(timestamp or "")) is not None
                and str(item.get("phase") or "").strip()
                and str(item.get("action") or "").strip()
                and str(item.get("status") or "").strip()
            ):
                structured += 1
    ok = structured >= 5 and pass0_seen and evidence_rows >= 2
    return build_check(
        key="run_ledger",
        label="Run ledger",
        path=path,
        ok=ok,
        detail=(
            f"parsed_lines={parsed} current_run_lines={current_run_lines} "
            f"structured_lines={structured} pass0_seen={pass0_seen} "
            f"evidence_rows={evidence_rows} total_lines={len(lines)}"
        ),
    )


def repo_inventory_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "REPO_INVENTORY.yaml"
    if not path.is_file():
        return build_check(key="repo_inventory", label="Repo inventory", path=path, ok=False, detail="missing")
    payload = load_yaml(path)
    repos = repo_entries(payload)
    count = len(repos)
    mounted_paths = mounted_expected_paths()
    covered_paths: set[str] = set()
    sha_count = 0
    branch_count = 0
    dirty_count = 0
    role_count = 0
    for repo in repos:
        values = [repo.get("path"), repo.get("mount_path"), repo.get("root"), repo.get("repo_path")]
        for value in values:
            if isinstance(value, str):
                normalized = value.rstrip("/")
                if normalized:
                    covered_paths.add(normalized)
        if any(looks_like_sha(repo.get(key)) for key in ("head_sha", "sha", "commit", "commit_sha", "git_sha")):
            sha_count += 1
        if any(isinstance(repo.get(key), str) and str(repo.get(key)).strip() for key in ("branch", "git_branch", "head_branch")):
            branch_count += 1
        if any(key in repo for key in ("dirty", "git_dirty", "clean")):
            dirty_count += 1
        repo_path = next(
            (
                str(value).rstrip("/")
                for value in values
                if isinstance(value, str) and str(value).strip()
            ),
            "",
        )
        expected_role = EXPECTED_ROLE_BY_PATH.get(repo_path)
        actual_role = str(repo.get("role") or repo.get("repo_role") or repo.get("estate_role") or "").strip()
        if expected_role and actual_role == expected_role:
            role_count += 1
    missing_paths = [str(item) for item in mounted_paths if str(item) not in covered_paths]
    expected_role_count = sum(1 for item in mounted_paths if str(item) in EXPECTED_ROLE_BY_PATH)
    ok = (
        count >= len(mounted_paths)
        and not missing_paths
        and sha_count >= len(mounted_paths)
        and branch_count >= len(mounted_paths)
        and dirty_count >= len(mounted_paths)
        and role_count >= expected_role_count
    )
    return build_check(
        key="repo_inventory",
        label="Repo inventory",
        path=path,
        ok=ok,
        detail=f"repo_count={count} expected_mounted={len(mounted_paths)} missing_paths={len(missing_paths)} sha_entries={sha_count} branch_entries={branch_count} dirty_state_entries={dirty_count} semantic_role_entries={role_count}/{expected_role_count}",
    )


def repo_inventory_live_reconciliation_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "REPO_INVENTORY.yaml"
    if not path.is_file():
        return build_check(key="repo_inventory_live_reconciliation", label="Repo inventory live reconciliation", path=path, ok=False, detail="missing")
    inventory = repo_inventory_map()
    current = current_git_state_map()
    mismatches: list[str] = []
    for repo_path, state in current.items():
        entry = inventory.get(repo_path)
        if entry is None:
            mismatches.append(f"{repo_path}:missing_inventory_entry")
            continue
        entry_branch = inventory_branch(entry)
        live_branch = str(state.get("branch") or "").strip()
        if entry_branch != live_branch:
            mismatches.append(f"{repo_path}:branch={entry_branch or 'missing'}!=live={live_branch or 'missing'}")
        entry_sha = inventory_sha(entry)
        live_sha = str(state.get("head_sha") or "").strip()
        if entry_sha != live_sha:
            mismatches.append(f"{repo_path}:sha={entry_sha or 'missing'}!=live={live_sha or 'missing'}")
        entry_dirty = inventory_dirty_state(entry)
        live_dirty = state.get("dirty")
        if entry_dirty is None or entry_dirty != live_dirty:
            mismatches.append(f"{repo_path}:dirty={entry_dirty!r}!=live={live_dirty!r}")
    ok = not mismatches
    return build_check(
        key="repo_inventory_live_reconciliation",
        label="Repo inventory live reconciliation",
        path=path,
        ok=ok,
        detail=f"mismatches={', '.join(mismatches) if mismatches else 'none'}",
    )


def branch_policy_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "REPO_INVENTORY.yaml"
    if not path.is_file():
        return build_check(key="branch_policy_alignment", label="Branch policy alignment", path=path, ok=False, detail="missing")
    repos = repo_entries(load_yaml(path))
    mounted_paths = {str(item) for item in mounted_expected_paths()}
    current = current_git_state_map()
    mismatches: list[str] = []
    for repo in repos:
        values = [repo.get("path"), repo.get("mount_path"), repo.get("root"), repo.get("repo_path")]
        repo_path = next((str(value).rstrip("/") for value in values if isinstance(value, str) and str(value).strip()), "")
        if repo_path not in mounted_paths:
            continue
        branch = inventory_branch(repo)
        live_branch = str(current.get(repo_path, {}).get("branch") or "").strip()
        managed = inventory_bool(repo, "completion_managed", "managed_by_completion", "touched_by_completion")
        baseline_note = str(repo.get("baseline_state_note") or repo.get("inherited_git_state_note") or "").strip()
        baseline_owner = str(repo.get("baseline_owner") or repo.get("inherited_state_owner") or "").strip()
        if managed is True:
            if branch != EXPECTED_COMPLETION_BRANCH:
                mismatches.append(f"{repo_path}:inventory={branch or 'missing'}")
            if live_branch != EXPECTED_COMPLETION_BRANCH:
                mismatches.append(f"{repo_path}:live={live_branch or 'missing'}")
        elif not branch:
            mismatches.append(f"{repo_path}:inventory={branch or 'missing'}")
        if not live_branch:
            mismatches.append(f"{repo_path}:live={live_branch or 'missing'}")
        if branch and live_branch and branch != live_branch:
            mismatches.append(f"{repo_path}:inventory_live_mismatch={branch}->{live_branch}")
        if managed is not True and (not baseline_note or not baseline_owner):
            mismatches.append(f"{repo_path}:missing_inherited_branch_note")
    ok = not mismatches
    return build_check(
        key="branch_policy_alignment",
        label="Branch policy alignment",
        path=path,
        ok=ok,
        detail=f"mismatches={', '.join(mismatches) if mismatches else 'none'}",
    )


def estate_git_state_check() -> dict[str, Any]:
    mismatches: list[str] = []
    current = current_git_state_map()
    baseline = git_baseline_map() or {}
    inventory = repo_inventory_map()
    for path, state in current.items():
        before = baseline.get(path, {})
        entry = inventory.get(path)
        managed = inventory_bool(entry or {}, "completion_managed", "managed_by_completion", "touched_by_completion")
        inherited_dirty = bool(before.get("dirty"))
        inherited_upstream = str(before.get("upstream") or "")
        inherited_ahead = str(before.get("ahead") or "")
        inherited_behind = str(before.get("behind") or "")
        inherited_nonclean = inherited_dirty or not inherited_upstream or inherited_ahead not in {"", "0"} or inherited_behind not in {"", "0"}
        note = str((entry or {}).get("baseline_state_note") or (entry or {}).get("inherited_git_state_note") or "").strip()
        baseline_owner = str((entry or {}).get("baseline_owner") or (entry or {}).get("inherited_state_owner") or "").strip()
        if state.get("dirty"):
            if managed is True or not inherited_dirty:
                mismatches.append(f"{path}:dirty")
                continue
            if managed is not False or not note or not baseline_owner:
                mismatches.append(f"{path}:dirty_without_inherited_note")
            continue
        upstream = str(state.get("upstream") or "")
        if not upstream:
            if managed is True or not inherited_nonclean:
                mismatches.append(f"{path}:no_upstream")
            elif managed is not False or not note or not baseline_owner:
                mismatches.append(f"{path}:no_upstream_without_inherited_note")
            continue
        ahead = str(state.get("ahead") or "")
        behind = str(state.get("behind") or "")
        if ahead != "0" or behind != "0":
            if managed is True or not inherited_nonclean:
                mismatches.append(f"{path}:ahead={ahead or '?'}:behind={behind or '?'}")
            elif managed is not False or not note or not baseline_owner:
                mismatches.append(f"{path}:ahead={ahead or '?'}:behind={behind or '?'}_without_inherited_note")
    ok = not mismatches
    return build_check(
        key="estate_git_state",
        label="Estate git state",
        path=WORKSPACE_ROOT,
        ok=ok,
        detail=f"mismatches={', '.join(mismatches) if mismatches else 'none'}",
    )


def estate_git_drift_from_baseline_check() -> dict[str, Any]:
    baseline = git_baseline_map()
    if baseline is None:
        return build_check(
            key="estate_git_drift_from_baseline",
            label="Estate git drift from baseline",
            path=git_baseline_path(),
            ok=False,
            detail="missing baseline",
        )
    current = current_git_state_map()
    drifts: list[str] = []
    for path, state in current.items():
        before = baseline.get(path)
        if before is None:
            drifts.append(f"{path}:missing_in_baseline")
            continue
        before_dirty = bool(before.get("dirty"))
        after_dirty = bool(state.get("dirty"))
        if after_dirty and not before_dirty:
            drifts.append(f"{path}:new_dirty")
        before_branch = str(before.get("branch") or "")
        after_branch = str(state.get("branch") or "")
        if before_branch and after_branch and before_branch != after_branch:
            drifts.append(f"{path}:branch_changed={before_branch}->{after_branch}")
    ok = not drifts
    return build_check(
        key="estate_git_drift_from_baseline",
        label="Estate git drift from baseline",
        path=git_baseline_path(),
        ok=ok,
        detail=f"drifts={', '.join(drifts) if drifts else 'none'}",
    )


def unavailable_repo_documentation_check() -> dict[str, Any]:
    inventory = COMPLETION_ROOT / "REPO_INVENTORY.yaml"
    gaps = COMPLETION_ROOT / "BUG_AND_GAP_REGISTER.yaml"
    actions = COMPLETION_ROOT / "FINAL_NEXT_ACTIONS.yaml"
    missing_docs: list[str] = []
    inventory_payload = load_yaml(inventory) if inventory.is_file() else None
    gap_text = gaps.read_text(encoding="utf-8").lower() if gaps.is_file() else ""
    action_text = actions.read_text(encoding="utf-8").lower() if actions.is_file() else ""
    for repo_name in UNAVAILABLE_REQUIRED_REPOS:
        entry = find_entry_by_key(inventory_payload, "name", repo_name) if inventory_payload is not None else None
        if entry is None:
            entry = find_entry_by_key(inventory_payload, "repo", repo_name) if inventory_payload is not None else None
        if entry is None:
            missing_docs.append(repo_name)
            continue
        status = str(entry.get("status") or entry.get("availability") or "").strip().lower()
        reason = str(entry.get("reason") or entry.get("unavailable_reason") or "").strip()
        next_action = str(entry.get("next_action") or "").strip()
        required_for = entry.get("required_for_gates") or entry.get("blocked_gates")
        if status not in {"unavailable", "not_mounted", "missing"} or not reason or not next_action or not isinstance(required_for, list) or not required_for:
            missing_docs.append(repo_name)
            continue
        token = repo_name.lower()
        if token not in gap_text or token not in action_text:
            missing_docs.append(repo_name)
    ok = not missing_docs
    return build_check(
        key="unavailable_repo_documentation",
        label="Unavailable repo documentation",
        path=COMPLETION_ROOT,
        ok=ok,
        detail=f"missing={', '.join(missing_docs) if missing_docs else 'none'}",
    )


def structured_yaml_check(filename: str, *, minimum_objects: int = 1) -> dict[str, Any]:
    path = COMPLETION_ROOT / filename
    if not path.is_file():
        return build_check(key=filename, label=filename, path=path, ok=False, detail="missing")
    payload = load_yaml(path)
    object_count = sum(1 for _ in walk_objects(payload))
    ok = object_count >= minimum_objects
    return build_check(
        key=filename,
        label=filename,
        path=path,
        ok=ok,
        detail=f"object_count={object_count}",
    )


def ownership_truth_map_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "OWNERSHIP_TRUTH_MAP.yaml"
    if not path.is_file():
        return build_check(key="ownership_truth_map_semantics", label="Ownership truth map semantics", path=path, ok=False, detail="missing")
    payload = load_yaml(path)
    missing: list[str] = []
    for repo_path in [str(item) for item in mounted_expected_paths() if str(item) in EXPECTED_ROLE_BY_PATH]:
        expected_role = EXPECTED_ROLE_BY_PATH[repo_path]
        matched = False
        for obj in walk_objects(payload):
            if not isinstance(obj, dict):
                continue
            role = str(obj.get("role") or obj.get("repo_role") or obj.get("estate_role") or "").strip()
            path_value = str(obj.get("repo_path") or obj.get("path") or obj.get("root") or obj.get("mount_path") or "").rstrip("/")
            canon = str(obj.get("canon_source") or obj.get("canon_repo") or obj.get("design_source") or "").strip()
            implementation = str(obj.get("implementation_source") or obj.get("owner_repo") or obj.get("implementation_repo") or "").strip()
            gates = obj.get("verification_gates") or obj.get("gates")
            if role == expected_role and path_value == repo_path and canon and implementation and isinstance(gates, list) and gates:
                matched = True
                break
        if not matched:
            missing.append(expected_role)
    ok = not missing
    return build_check(
        key="ownership_truth_map_semantics",
        label="Ownership truth map semantics",
        path=path,
        ok=ok,
        detail=f"missing_roles={', '.join(missing) if missing else 'none'}",
    )


def canon_truth_map_semantics_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "CANON_TRUTH_MAP.md"
    if not path.is_file():
        return build_check(key="canon_truth_map_semantics", label="Canon truth map semantics", path=path, ok=False, detail="missing")
    text = path.read_text(encoding="utf-8").lower()
    missing = []
    roles = [EXPECTED_ROLE_BY_PATH[str(item)] for item in mounted_expected_paths() if str(item) in EXPECTED_ROLE_BY_PATH]
    for role in roles:
        if not window_has_markers(text, role, CANON_TRUTH_MARKERS):
            missing.append(role)
    ok = not missing
    return build_check(
        key="canon_truth_map_semantics",
        label="Canon truth map semantics",
        path=path,
        ok=ok,
        detail=f"missing_roles={', '.join(missing) if missing else 'none'}",
    )


def structured_json_check(filename: str) -> dict[str, Any]:
    path = COMPLETION_ROOT / filename
    if not path.is_file():
        return build_check(key=filename, label=filename, path=path, ok=False, detail="missing")
    payload = load_json(path)
    status = str(payload.get("status") or payload.get("result") or "").strip().lower() if isinstance(payload, dict) else ""
    object_count = sum(1 for _ in walk_objects(payload))
    ok = isinstance(payload, dict) and object_count >= 3
    return build_check(
        key=filename,
        label=filename,
        path=path,
        ok=ok,
        detail=f"status={status or 'missing'} object_count={object_count}",
    )


def markdown_check(filename: str, *, minimum_chars: int = 400) -> dict[str, Any]:
    path = COMPLETION_ROOT / filename
    if not path.is_file():
        return build_check(key=filename, label=filename, path=path, ok=False, detail="missing")
    text = path.read_text(encoding="utf-8")
    ok = len(text.strip()) >= minimum_chars
    return build_check(
        key=filename,
        label=filename,
        path=path,
        ok=ok,
        detail=f"char_count={len(text.strip())}",
    )


def completion_backlog_clear_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "COMPLETION_BACKLOG.yaml"
    if not path.is_file():
        return build_check(key="completion_backlog_clear", label="Completion backlog clear", path=path, ok=False, detail="missing")
    payload = load_yaml(path)
    high_priority_count = count_high_priority_items(payload)
    ok = high_priority_count == 0
    return build_check(
        key="completion_backlog_clear",
        label="Completion backlog clear",
        path=path,
        ok=ok,
        detail=f"open_p0_p1={high_priority_count}",
    )


def backlog_clear_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "FINAL_NEXT_ACTIONS.yaml"
    if not path.is_file():
        return build_check(key="final_next_actions", label="Final next actions", path=path, ok=False, detail="missing")
    payload = load_yaml(path)
    high_priority_count = count_high_priority_items(payload)
    ok = high_priority_count == 0
    return build_check(
        key="final_next_actions",
        label="Final next actions",
        path=path,
        ok=ok,
        detail=f"open_p0_p1={high_priority_count}",
    )


def bug_register_clear_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "BUG_AND_GAP_REGISTER.yaml"
    if not path.is_file():
        return build_check(key="bug_register", label="Bug and gap register", path=path, ok=False, detail="missing")
    payload = load_yaml(path)
    high_priority_count = count_high_priority_items(payload)
    ok = high_priority_count == 0
    return build_check(
        key="bug_register",
        label="Bug and gap register",
        path=path,
        ok=ok,
        detail=f"open_p0_p1={high_priority_count}",
    )


def bug_register_semantics_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "BUG_AND_GAP_REGISTER.yaml"
    if not path.is_file():
        return build_check(key="bug_register_semantics", label="Bug register semantics", path=path, ok=False, detail="missing")
    payload = load_yaml(path)
    structured = 0
    missing = 0
    for obj in walk_objects(payload):
        if not isinstance(obj, dict):
            continue
        priority = str(obj.get("priority") or obj.get("severity") or "").strip().upper()
        if priority not in {"P0", "P1", "P2"}:
            continue
        structured += 1
        owner = str(obj.get("owner") or "").strip()
        title = str(obj.get("title") or obj.get("summary") or obj.get("name") or "").strip()
        next_action = str(obj.get("next_action") or "").strip()
        repo_path = str(obj.get("repo_path") or obj.get("owner_repo") or obj.get("implementation_repo") or "").strip()
        gates = obj.get("blocked_gates") or obj.get("required_for_gates") or obj.get("gates")
        if not owner or not title or not next_action or not repo_path or not isinstance(gates, list) or not gates:
            missing += 1
    ok = structured > 0 and missing == 0
    return build_check(
        key="bug_register_semantics",
        label="Bug register semantics",
        path=path,
        ok=ok,
        detail=f"structured_entries={structured} malformed_entries={missing}",
    )


def horizon_mvp_completion_map_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "HORIZON_MVP_COMPLETION_MAP.yaml"
    if not path.is_file():
        return build_check(key="horizon_mvp_semantics", label="Horizon MVP completion map semantics", path=path, ok=False, detail="missing")
    text = path.read_text(encoding="utf-8").lower()
    missing = [token for token in HORIZON_REQUIRED_TOKENS if not window_has_markers(text, token, HORIZON_SECTION_MARKERS)]
    ok = not missing
    return build_check(
        key="horizon_mvp_semantics",
        label="Horizon MVP completion map semantics",
        path=path,
        ok=ok,
        detail=f"missing={', '.join(missing) if missing else 'none'}",
    )


def verdict_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "ABSOLUTE_COMPLETION_VERDICT.md"
    if not path.is_file():
        return build_check(key="completion_verdict", label="Completion verdict", path=path, ok=False, detail="missing")
    text = path.read_text(encoding="utf-8")
    ok = any(token in text for token in ["PREVIEW_READY", "FLAGSHIP_READY", "RELEASE_READY"])
    return build_check(
        key="completion_verdict",
        label="Completion verdict",
        path=path,
        ok=ok,
        detail="readiness token present" if ok else "missing readiness token",
    )


def completion_verdict_semantics_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "ABSOLUTE_COMPLETION_VERDICT.md"
    if not path.is_file():
        return build_check(key="completion_verdict_semantics", label="Completion verdict semantics", path=path, ok=False, detail="missing")
    text = path.read_text(encoding="utf-8").lower()
    ok = all(marker in text for marker in VERDICT_MARKERS) and any(token.lower() in text for token in ["PREVIEW_READY", "FLAGSHIP_READY", "RELEASE_READY"])
    return build_check(
        key="completion_verdict_semantics",
        label="Completion verdict semantics",
        path=path,
        ok=ok,
        detail="required verdict sections present" if ok else "missing required verdict sections",
    )


def release_gates_coverage_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "ABSOLUTE_RELEASE_GATES.yaml"
    if not path.is_file():
        return build_check(key="release_gates_coverage", label="Release gates coverage", path=path, ok=False, detail="missing")
    payload = load_yaml(path)
    inventory = repo_inventory_map()
    live_state = current_git_state_map()
    present, missing = gate_presence_in_payload(payload, REQUIRED_GATE_IDS, require_pass=False)
    structured_missing: list[str] = []
    for gate_id in REQUIRED_GATE_IDS:
        entry = find_gate_entry(payload, gate_id)
        if entry is None:
            structured_missing.append(gate_id)
            continue
        owner = str(entry.get("owner") or "").strip()
        status = str(entry.get("status") or entry.get("state") or "").strip().lower()
        proof = entry.get("proof_path") or entry.get("proof_paths") or entry.get("evidence_paths") or entry.get("blocker")
        if not owner or status not in PASS_STATUSES.union({"blocked", "blocked_external", "not_mounted"}) or not proof:
            structured_missing.append(gate_id)
            continue
        if status in PASS_STATUSES:
            if not command_receipt_binding(entry, inventory, live_state):
                structured_missing.append(gate_id)
                continue
        else:
            next_action = str(entry.get("next_action") or "").strip()
            repo_path = str(entry.get("repo_path") or "").strip()
            blocker = str(entry.get("blocker") or "").strip()
            if not next_action or not repo_path or not blocker:
                structured_missing.append(gate_id)
    ok = not missing and not structured_missing
    return build_check(
        key="release_gates_coverage",
        label="Release gates coverage",
        path=path,
        ok=ok,
        detail=f"present={len(present)} missing={', '.join(sorted(set(missing + structured_missing))) if (missing or structured_missing) else 'none'}",
    )


def verification_commands_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "VERIFICATION_COMMANDS.md"
    if not path.is_file():
        return build_check(key="verification_commands_coverage", label="Verification commands coverage", path=path, ok=False, detail="missing")
    text = path.read_text(encoding="utf-8")
    matrix = verification_matrix_commands_map()
    gate_markers = ("Owner repo:", "Command:", "Evidence:", "Expected proof:")

    def gate_window(gate_id: str) -> str:
        anchor = text.find(gate_id)
        if anchor < 0:
            return ""
        next_anchor = len(text)
        for other_gate_id in REQUIRED_GATE_IDS:
            if other_gate_id == gate_id:
                continue
            position = text.find(other_gate_id, anchor + len(gate_id))
            if position != -1 and position < next_anchor:
                next_anchor = position
        next_anchor = min(next_anchor, anchor + 4000)
        return text[anchor:next_anchor]

    missing: list[str] = []
    for gate_id in REQUIRED_GATE_IDS:
        section = gate_window(gate_id)
        if not section:
            missing.append(gate_id)
            continue
        if any(marker not in section for marker in gate_markers):
            missing.append(gate_id)
            continue
        commands = matrix.get(gate_id, [])
        if not commands:
            missing.append(gate_id)
            continue
        if any(command not in section for command in commands):
            missing.append(gate_id)
    ok = not missing
    return build_check(
        key="verification_commands_coverage",
        label="Verification commands coverage",
        path=path,
        ok=ok,
        detail=f"missing={', '.join(missing) if missing else 'none'}",
    )


def verification_results_gate_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "VERIFICATION_RESULTS.generated.json"
    if not path.is_file():
        return build_check(key="verification_results_gates", label="Verification results gates", path=path, ok=False, detail="missing")
    payload = load_json(path)
    inventory = repo_inventory_map()
    live_state = current_git_state_map()
    matrix = verification_matrix_commands_map()
    missing: list[str] = []
    for gate_id in REQUIRED_GATE_IDS:
        entry = find_gate_entry(payload, gate_id)
        if entry is None or not record_is_passing(entry):
            missing.append(gate_id)
            continue
        command_entries = extract_entry_list(entry, ("commands", "command_receipts", "receipts", "checks"))
        expected = matrix.get(gate_id, [])
        if not expected:
            missing.append(gate_id)
            continue
        command_map = {
            str(item.get("command") or item.get("cmd") or "").strip(): item
            for item in command_entries
            if isinstance(item, dict)
        }
        if any(
            command not in command_map
            or not command_receipt_ok(command_map[command])
            or not command_receipt_detail(command_map[command])
            or not command_receipt_binding(command_map[command], inventory, live_state)
            for command in expected
        ):
            missing.append(gate_id)
    ok = not missing
    return build_check(
        key="verification_results_gates",
        label="Verification results gates",
        path=path,
        ok=ok,
        detail=f"gate_count={len(REQUIRED_GATE_IDS)} missing={', '.join(missing) if missing else 'none'}",
    )


def e2e_results_coverage_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "E2E_RESULTS.generated.json"
    if not path.is_file():
        return build_check(key="e2e_results_coverage", label="E2E results coverage", path=path, ok=False, detail="missing")
    payload = load_json(path)
    inventory = repo_inventory_map()
    live_state = current_git_state_map()
    required = [
        "gate-auth-account-install",
        "gate-feedback-loop",
        "gate-karma-forge",
        "gate-package-management",
        "gate-mobile-pwa",
    ]
    missing: list[str] = []
    for gate_id in required:
        entry = find_gate_entry(payload, gate_id)
        if entry is None or not record_is_passing(entry):
            missing.append(gate_id)
            continue
        journeys = entry.get("journeys") or entry.get("cases") or entry.get("scenarios")
        evidence = entry.get("evidence_paths") or entry.get("proof_paths") or entry.get("artifacts")
        if (
            not isinstance(journeys, list)
            or not journeys
            or not evidence_value_to_paths(evidence)
            or not command_receipt_binding(entry, inventory, live_state)
        ):
            missing.append(gate_id)
            continue
        bad_journeys = False
        for journey in journeys:
            if not isinstance(journey, dict):
                bad_journeys = True
                break
            name = str(journey.get("name") or journey.get("id") or journey.get("slug") or "").strip()
            if not name or not record_is_passing(journey) or not command_receipt_binding(journey, inventory, live_state):
                bad_journeys = True
                break
        if bad_journeys:
            missing.append(gate_id)
            continue
        covered = " ".join(
            str(journey.get("name") or journey.get("id") or journey.get("slug") or "")
            for journey in journeys
            if isinstance(journey, dict)
        ).lower()
        required_tokens = REQUIRED_E2E_JOURNEY_TOKENS.get(gate_id, [])
        if any(token not in covered for token in required_tokens):
            missing.append(gate_id)
    ok = not missing
    return build_check(
        key="e2e_results_coverage",
        label="E2E results coverage",
        path=path,
        ok=ok,
        detail=f"required={len(required)} missing={', '.join(missing) if missing else 'none'}",
    )


def target_public_routes_coverage_check() -> dict[str, Any]:
    routes = target_public_route_paths()
    if not routes:
        return build_check(
            key="target_public_routes_coverage",
            label="Target public routes coverage",
            path=INPUT_ROOT / "TARGET_PUBLIC_ROUTES.yaml",
            ok=False,
            detail="no target routes loaded",
        )

    release_gates_path = COMPLETION_ROOT / "ABSOLUTE_RELEASE_GATES.yaml"
    if not release_gates_path.is_file():
        return build_check(
            key="target_public_routes_coverage",
            label="Target public routes coverage",
            path=release_gates_path,
            ok=False,
            detail="ABSOLUTE_RELEASE_GATES.yaml missing",
        )
    payload = load_yaml(release_gates_path)
    inventory = repo_inventory_map()
    live_state = current_git_state_map()
    active_run_id = current_run_id()
    public_routes = []
    if isinstance(payload, dict) and isinstance(payload.get("public_routes"), list):
        public_routes = [item for item in payload["public_routes"] if isinstance(item, dict)]
    route_map = {str(item.get("path") or "").strip(): item for item in public_routes if str(item.get("path") or "").strip()}
    missing: list[str] = []
    for route in routes:
        entry = route_map.get(route)
        if entry is None:
            missing.append(route)
            continue
        state = str(entry.get("state") or entry.get("status") or "").strip().lower()
        owner = str(entry.get("owner") or "").strip()
        proof = entry.get("proof_path") or entry.get("proof_paths") or entry.get("evidence_paths")
        blocker = entry.get("blocker") or entry.get("next_action")
        if state not in ROUTE_ALLOWED_STATES or not owner:
            missing.append(route)
            continue
        if state in {"implemented", "proven", "preview_bounded"}:
            route_repo_path = str(entry.get("repo_path") or "").rstrip("/")
            route_commit = str(entry.get("commit_sha") or "").strip()
            route_generated_at = parse_iso_datetime(str(entry.get("generated_at") or entry.get("verified_at") or ""))
            inventory_entry = inventory.get(route_repo_path)
            live_entry = live_state.get(route_repo_path)
            inventory_sha_value = inventory_sha(inventory_entry) if inventory_entry else ""
            live_sha = str(live_entry.get("head_sha") or "").strip() if live_entry else ""
            proof_paths = evidence_value_to_paths(proof)
            if (
                not active_run_id
                or
                not route_repo_path
                or not route_commit
                or route_generated_at is None
                or not proof_paths
                or not inventory_entry
                or not live_entry
                or str(entry.get("run_id") or "").strip() != active_run_id
                or (inventory_sha_value and inventory_sha_value != route_commit)
                or (live_sha and live_sha != route_commit)
                or any(not text_mentions_run_id(path, active_run_id) for path in proof_paths)
            ):
                missing.append(route)
        else:
            repo_path = str(entry.get("repo_path") or "").strip()
            route_commit = str(entry.get("commit_sha") or "").strip()
            next_action = str(entry.get("next_action") or "").strip()
            blocker_text = str(blocker or "").strip()
            blocked_generated_at = parse_iso_datetime(str(entry.get("blocked_at") or entry.get("generated_at") or entry.get("verified_at") or ""))
            inventory_entry = inventory.get(repo_path) if repo_path else None
            live_entry = live_state.get(repo_path) if repo_path else None
            inventory_sha_value = inventory_sha(inventory_entry) if inventory_entry else ""
            live_sha = str(live_entry.get("head_sha") or "").strip() if live_entry else ""
            if (
                not active_run_id
                or str(entry.get("run_id") or "").strip() != active_run_id
                or not repo_path
                or not next_action
                or not blocker_text
                or blocked_generated_at is None
            ):
                missing.append(route)
                continue
            if inventory_entry and (not route_commit or (inventory_sha_value and inventory_sha_value != route_commit)):
                missing.append(route)
                continue
            if live_entry and (not route_commit or (live_sha and live_sha != route_commit)):
                missing.append(route)
        if state in {"blocked", "blocked_external", "not_mounted"} and not str(entry.get("repo_path") or "").strip():
            missing.append(route)
    ok = not missing
    return build_check(
        key="target_public_routes_coverage",
        label="Target public routes coverage",
        path=release_gates_path,
        ok=ok,
        detail=f"route_count={len(routes)} missing={', '.join(missing) if missing else 'none'}",
    )


def false_complete_seed_coverage_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "FALSE_COMPLETE_REGISTER.yaml"
    if not path.is_file():
        return build_check(key="false_complete_seed_coverage", label="False-complete seed coverage", path=path, ok=False, detail="missing")
    payload = load_yaml(path)
    missing: list[str] = []
    for token in FALSE_COMPLETE_SEED_TOKENS:
        matched = False
        for obj in walk_objects(payload):
            if not isinstance(obj, dict):
                continue
            if not object_matches_seed_token(obj, token, keys=("risk", "id", "token", "name", "slug", "claim", "title")):
                continue
            owner = str(obj.get("owner") or obj.get("adapter_owner") or "").strip()
            status = str(obj.get("status") or obj.get("state") or "").strip()
            next_action = str(obj.get("next_action") or obj.get("mitigation") or "").strip()
            proof = obj.get("proof_path") or obj.get("proof_paths") or obj.get("evidence_paths") or obj.get("proof_or_blocker") or obj.get("blocker")
            gates = obj.get("required_for_gates") or obj.get("blocked_gates") or obj.get("gates")
            if owner and status and next_action and proof and isinstance(gates, list) and gates:
                matched = True
                break
        if not matched:
            missing.append(token)
    ok = not missing
    return build_check(
        key="false_complete_seed_coverage",
        label="False-complete seed coverage",
        path=path,
        ok=ok,
        detail=f"missing={', '.join(missing) if missing else 'none'}",
    )


def false_claim_seed_coverage_check() -> dict[str, Any]:
    path = COMPLETION_ROOT / "FALSE_CLAIM_RISK.md"
    if not path.is_file():
        return build_check(key="false_claim_seed_coverage", label="False-claim seed coverage", path=path, ok=False, detail="missing")
    text = path.read_text(encoding="utf-8").lower()
    missing = [token for token in FALSE_CLAIM_SEED_TOKENS if not window_has_markers(text, token, FALSE_CLAIM_SECTION_MARKERS)]
    ok = not missing
    return build_check(
        key="false_claim_seed_coverage",
        label="False-claim seed coverage",
        path=path,
        ok=ok,
        detail=f"missing={', '.join(missing) if missing else 'none'}",
    )


def product_doc_truth_coverage_check() -> dict[str, Any]:
    guide_path = COMPLETION_ROOT / "PUBLIC_COPY_CHANGE_GUIDE.md"
    truth_path = COMPLETION_ROOT / "CANON_TRUTH_MAP.md"
    gaps_path = COMPLETION_ROOT / "BUG_AND_GAP_REGISTER.yaml"
    missing: list[str] = []
    guide_text = guide_path.read_text(encoding="utf-8").lower() if guide_path.is_file() else ""
    truth_text = truth_path.read_text(encoding="utf-8").lower() if truth_path.is_file() else ""
    gap_text = gaps_path.read_text(encoding="utf-8").lower() if gaps_path.is_file() else ""
    for raw_path in PRODUCT_DOC_PATHS:
        path = Path(raw_path)
        if not path.is_file():
            missing.append(f"{raw_path}:missing_file")
            continue
        token = path.name.lower()
        if not window_has_markers(guide_text, token, PRODUCT_DOC_GUIDE_MARKERS):
            missing.append(f"{raw_path}:guide_section_incomplete")
            continue
        if not window_has_markers(truth_text, token, PRODUCT_DOC_TRUTH_MARKERS):
            missing.append(f"{raw_path}:truth_section_incomplete")
            continue
        doc_text = path.read_text(encoding="utf-8").lower()
        doc_risks = [risk for risk in PRODUCT_DOC_RISK_TOKENS if risk in doc_text]
        if doc_risks:
            if raw_path.lower() not in gap_text and token not in gap_text:
                missing.append(f"{raw_path}:risk_not_registered")
                continue
            if any(risk not in gap_text for risk in doc_risks):
                missing.append(f"{raw_path}:risk_tokens_unmapped")
    ok = not missing
    return build_check(
        key="product_doc_truth_coverage",
        label="Product doc truth coverage",
        path=Path(PRODUCT_DOC_PATHS[0]).parent,
        ok=ok,
        detail=f"missing={', '.join(missing) if missing else 'none'}",
    )


def markdown_semantic_check(filename: str, markers: list[str]) -> dict[str, Any]:
    path = COMPLETION_ROOT / filename
    if not path.is_file():
        return build_check(key=f"{filename}.semantic", label=f"{filename} semantic coverage", path=path, ok=False, detail="missing")
    text = path.read_text(encoding="utf-8").lower()
    missing = [marker for marker in markers if marker not in text]
    ok = not missing
    return build_check(
        key=f"{filename}.semantic",
        label=f"{filename} semantic coverage",
        path=path,
        ok=ok,
        detail=f"missing={', '.join(missing) if missing else 'none'}",
    )


def ltd_seed_coverage_check() -> dict[str, Any]:
    map_path = COMPLETION_ROOT / "LTD_COMPLETION_MAP.md"
    guide_path = COMPLETION_ROOT / "LTD_ADAPTER_IMPLEMENTATION_GUIDE.md"
    if not map_path.is_file() or not guide_path.is_file():
        missing = []
        if not map_path.is_file():
            missing.append(map_path.name)
        if not guide_path.is_file():
            missing.append(guide_path.name)
        return build_check(key="ltd_seed_coverage", label="LTD seed coverage", path=COMPLETION_ROOT, ok=False, detail=f"missing={', '.join(missing)}")

    entries = ltd_seed_entries()
    map_text = map_path.read_text(encoding="utf-8").lower()
    guide_text = guide_path.read_text(encoding="utf-8").lower()
    missing_map: list[str] = []
    missing_guide: list[str] = []
    for entry in entries:
        name = str(entry.get("ltd") or "").strip()
        status = str(entry.get("status") or "").strip().lower()
        owner = str(entry.get("adapter_owner") or "").strip().lower()
        receipt = str(entry.get("required_receipt") or "").strip().lower()
        if not name:
            continue
        if not window_has_markers(
            map_text,
            name.lower(),
            [
                f"status: {status}",
                f"adapter owner: {owner}",
                f"required receipt: {receipt}",
                "risk:",
            ],
        ):
            missing_map.append(name)
        if status in {"use_now", "pilot"} and not window_has_markers(
            guide_text,
            name.lower(),
            [
                "verification:",
                "fallback:",
                "off-switch:",
                f"required receipt: {receipt}",
            ],
        ):
            missing_guide.append(name)
    ok = not missing_map and not missing_guide
    detail_parts = [
        f"missing_map={', '.join(missing_map) if missing_map else 'none'}",
        f"missing_guide={', '.join(missing_guide) if missing_guide else 'none'}",
    ]
    return build_check(
        key="ltd_seed_coverage",
        label="LTD seed coverage",
        path=COMPLETION_ROOT,
        ok=ok,
        detail=" ".join(detail_parts),
    )


def strict_gate_check() -> dict[str, Any]:
    payload = run_json(["python3", str(STRICT_GATE)], cwd=RUN_SERVICES_ROOT)
    ok = bool(payload.get("closure_done"))
    pending = payload.get("pending_check_keys") or []
    return build_check(
        key="strict_hub_substance",
        label="Strict hub substance gate",
        path=STRICT_GATE,
        ok=ok,
        detail="closure_done=true" if ok else f"pending={', '.join(str(item) for item in pending)}",
    )


def main() -> int:
    checks = [
        strict_gate_check(),
        artifact_exists_check(),
        pass0_control_plane_check(),
        run_ledger_check(),
        repo_inventory_check(),
        repo_inventory_live_reconciliation_check(),
        branch_policy_check(),
        estate_git_state_check(),
        estate_git_drift_from_baseline_check(),
        unavailable_repo_documentation_check(),
        ownership_truth_map_check(),
        canon_truth_map_semantics_check(),
        structured_yaml_check("OWNERSHIP_TRUTH_MAP.yaml"),
        structured_yaml_check("FALSE_COMPLETE_REGISTER.yaml"),
        structured_yaml_check("BUG_AND_GAP_REGISTER.yaml"),
        structured_yaml_check("COMPLETION_BACKLOG.yaml"),
        structured_yaml_check("ABSOLUTE_RELEASE_GATES.yaml"),
        structured_yaml_check("HORIZON_MVP_COMPLETION_MAP.yaml"),
        horizon_mvp_completion_map_check(),
        structured_json_check("E2E_RESULTS.generated.json"),
        structured_json_check("VERIFICATION_RESULTS.generated.json"),
        release_gates_coverage_check(),
        verification_commands_check(),
        verification_results_gate_check(),
        e2e_results_coverage_check(),
        target_public_routes_coverage_check(),
        false_complete_seed_coverage_check(),
        false_claim_seed_coverage_check(),
        ltd_seed_coverage_check(),
        product_doc_truth_coverage_check(),
        bug_register_semantics_check(),
        markdown_check("CANON_TRUTH_MAP.md"),
        markdown_check("ABSOLUTE_GAP_AUDIT.md"),
        markdown_check("MISSED_POTENTIAL_AUDIT.md"),
        markdown_check("USER_WISH_DESIGN_EXPANSION.md"),
        markdown_check("LTD_COMPLETION_MAP.md"),
        markdown_check("ABSOLUTE_PRODUCT_COMPLETION_PLAN.md"),
        markdown_check("FEEDBACK_TO_IMPLEMENTATION_LOOP.md"),
        markdown_check("KARMA_FORGE_PRODUCT_AND_IMPLEMENTATION_LOOP.md"),
        markdown_check("PACKAGE_MANAGEMENT_AND_PUBLIC_PACKAGE_BROWSER.md"),
        markdown_check("MOBILE_PWA_PRODUCT_SPEC.md"),
        markdown_check("E2E_TEST_PLAN.md"),
        markdown_check("VERIFICATION_COMMANDS.md"),
        markdown_check("DEV_CHANGE_GUIDE.md"),
        markdown_check("FALSE_CLAIM_RISK.md"),
        markdown_check("PUBLIC_COPY_CHANGE_GUIDE.md"),
        markdown_check("LTD_ADAPTER_IMPLEMENTATION_GUIDE.md"),
        markdown_check("RELEASE_RUNBOOK.md"),
        markdown_check("PREMIUM_FLAGSHIP_POLISH_REPORT.md"),
        verdict_check(),
        completion_verdict_semantics_check(),
        *[markdown_semantic_check(filename, markers) for filename, markers in MARKDOWN_SEMANTIC_RULES.items()],
        completion_backlog_clear_check(),
        backlog_clear_check(),
        bug_register_clear_check(),
    ]

    pending_checks = [check for check in checks if not check["ok"]]
    pending_abs_ids = [check["key"] for check in pending_checks]
    payload = {
        "generated_at": now_iso(),
        "closure_done": not pending_checks,
        "pending_abs_ids": pending_abs_ids,
        "pending_check_keys": pending_abs_ids,
        "checks": checks,
        "summary": "QWEN35 estate completion gate is green." if not pending_checks else "QWEN35 estate completion gate is still open.",
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if not pending_checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
