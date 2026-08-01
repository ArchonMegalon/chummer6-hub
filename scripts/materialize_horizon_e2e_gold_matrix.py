#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / ".codex-design" / "product" / "HORIZON_REGISTRY.yaml"
DEFAULT_SPEC = ROOT / "tests" / "public" / "horizon-e2e-gold.spec.ts"
DEFAULT_CONFIG = ROOT / "playwright.config.ts"
DEFAULT_PLAYWRIGHT_CLI = ROOT / "node_modules" / "playwright" / "cli.js"
DEFAULT_OUTPUT = ROOT / ".codex-studio" / "published" / "HORIZON_E2E_GOLD_MATRIX.generated.json"
DEFAULT_EVIDENCE_DIR = ROOT / ".codex-studio" / "published" / "horizon-e2e-gold"
EXPECTED_HORIZON_IDS = (
    "alice",
    "origin-dossier",
    "karma-forge",
    "knowledge-fabric",
    "jackpoint",
    "black-ledger",
    "runsite",
    "runbook-press",
    "table-pulse",
)
CONTRACT_NAME = "chummer.horizon_e2e_gold_matrix/v1"
RECEIPT_CONTRACT_NAME = "chummer.horizon_e2e_gold/v1"
PASS_VERDICT = "HORIZON_PORTFOLIO_GOLD"
CLAIM_SCOPE = "registered_shipped_mvp_public_journey"
MAX_FUTURE_SKEW = timedelta(minutes=5)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def load_registry(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    failures: list[str] = []
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [], [f"registry is missing or invalid: {exc}"]

    raw_horizons = payload.get("horizons")
    if not isinstance(raw_horizons, list):
        return [], ["registry horizons must be a list"]

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_horizons):
        if not isinstance(raw, dict):
            failures.append(f"registry horizon {index} must be an object")
            continue
        horizon_id = str(raw.get("id") or "").strip()
        if not horizon_id:
            failures.append(f"registry horizon {index} is missing id")
            continue
        if horizon_id in seen:
            failures.append(f"registry contains duplicate horizon {horizon_id}")
            continue
        seen.add(horizon_id)
        if str(raw.get("status") or "").strip() != "shipped_mvp":
            failures.append(f"{horizon_id} is not shipped_mvp")
        e2e = raw.get("e2e_gold")
        if not isinstance(e2e, dict):
            failures.append(f"{horizon_id} is missing e2e_gold contract")
            e2e = {}
        route = str(e2e.get("route") or "").strip()
        receipt_route = str(e2e.get("receipt_route") or "").strip()
        claim_scope = str(e2e.get("claim_scope") or "").strip()
        if not route.startswith("/"):
            failures.append(f"{horizon_id} e2e route must be absolute")
        if not receipt_route.startswith("/"):
            failures.append(f"{horizon_id} receipt route must be absolute")
        if claim_scope != CLAIM_SCOPE:
            failures.append(f"{horizon_id} has unexpected claim scope")
        rows.append(
            {
                "id": horizon_id,
                "title": str(raw.get("title") or horizon_id).strip(),
                "status": str(raw.get("status") or "").strip(),
                "route": route,
                "receipt_route": receipt_route,
                "claim_scope": claim_scope,
                "owning_repos": [
                    str(item).strip()
                    for item in raw.get("owning_repos") or []
                    if str(item).strip()
                ],
            }
        )

    actual_ids = tuple(row["id"] for row in rows)
    if actual_ids != EXPECTED_HORIZON_IDS:
        failures.append(
            "registry horizon order/coverage drifted: "
            f"expected {list(EXPECTED_HORIZON_IDS)}, got {list(actual_ids)}"
        )
    return rows, failures


def parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def artifact_failures(
    artifact: dict[str, Any],
    registry_row: dict[str, Any],
    *,
    run_started_at: datetime,
    run_finished_at: datetime,
    expected_base_url: str,
) -> list[str]:
    horizon_id = registry_row["id"]
    failures: list[str] = []
    if not artifact:
        return [f"{horizon_id} browser receipt is missing or invalid"]
    if artifact.get("contract_name") != RECEIPT_CONTRACT_NAME:
        failures.append(f"{horizon_id} browser receipt has unexpected contract")
    if artifact.get("status") != "pass" or artifact.get("verdict") != "GOLD":
        failures.append(f"{horizon_id} browser receipt is not GOLD/pass")
    for key in ("horizon_id", "route", "receipt_route", "claim_scope"):
        expected = registry_row["id" if key == "horizon_id" else key]
        if artifact.get(key) != expected:
            failures.append(f"{horizon_id} browser receipt {key} drifted")
    if str(artifact.get("base_url") or "").rstrip("/") != expected_base_url.rstrip("/"):
        failures.append(f"{horizon_id} browser receipt base_url drifted")
    generated_at = parse_timestamp(artifact.get("generated_at_utc"))
    if generated_at is None:
        failures.append(f"{horizon_id} browser receipt timestamp is invalid")
    elif generated_at < run_started_at - timedelta(seconds=2):
        failures.append(f"{horizon_id} browser receipt predates this execution")
    elif generated_at > run_finished_at + MAX_FUTURE_SKEW:
        failures.append(f"{horizon_id} browser receipt timestamp is in the future")
    if int(artifact.get("assertion_count") or 0) < 8:
        failures.append(f"{horizon_id} browser receipt has insufficient assertions")
    if len(artifact.get("journey_steps") or []) < 4:
        failures.append(f"{horizon_id} browser receipt has insufficient journey depth")
    if len(artifact.get("boundaries_verified") or []) < 4:
        failures.append(f"{horizon_id} browser receipt has insufficient boundary proof")
    if not isinstance(artifact.get("evidence"), dict) or not artifact.get("evidence"):
        failures.append(f"{horizon_id} browser receipt has no evidence map")
    return failures


def parse_playwright_stats(stdout: str) -> tuple[dict[str, int], str]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {}, f"Playwright JSON reporter output is invalid: {exc}"
    raw = payload.get("stats") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return {}, "Playwright JSON reporter is missing stats"
    stats = {
        "expected": int(raw.get("expected") or 0),
        "unexpected": int(raw.get("unexpected") or 0),
        "flaky": int(raw.get("flaky") or 0),
        "skipped": int(raw.get("skipped") or 0),
        "duration_ms": int(raw.get("duration") or 0),
    }
    return stats, ""


def build_matrix(
    *,
    registry_rows: list[dict[str, Any]],
    registry_failures: list[str],
    artifacts_dir: Path,
    evidence_dir: Path,
    base_url: str,
    run_started_at: datetime,
    run_finished_at: datetime,
    runner: dict[str, Any],
    source_inputs: dict[str, dict[str, str]],
) -> dict[str, Any]:
    failures = list(registry_failures)
    stats = runner.get("stats") if isinstance(runner.get("stats"), dict) else {}
    if runner.get("returncode") != 0:
        failures.append(f"Playwright exited with {runner.get('returncode')}")
    if runner.get("timed_out") is True:
        failures.append("Playwright timed out")
    if stats.get("expected") != len(EXPECTED_HORIZON_IDS):
        failures.append(
            f"Playwright expected-test count is {stats.get('expected')}, expected {len(EXPECTED_HORIZON_IDS)}"
        )
    if int(stats.get("unexpected") or 0) != 0:
        failures.append(f"Playwright reported {stats.get('unexpected')} unexpected test result(s)")
    if int(stats.get("skipped") or 0) != 0:
        failures.append(f"Playwright skipped {stats.get('skipped')} horizon test(s)")
    if runner.get("parse_failure"):
        failures.append(str(runner["parse_failure"]))

    evidence_dir.mkdir(parents=True, exist_ok=True)
    horizon_rows: list[dict[str, Any]] = []
    for registry_row in registry_rows:
        horizon_id = registry_row["id"]
        artifact_path = artifacts_dir / f"HORIZON_E2E_GOLD.{horizon_id}.generated.json"
        artifact = load_json(artifact_path)
        row_failures = artifact_failures(
            artifact,
            registry_row,
            run_started_at=run_started_at,
            run_finished_at=run_finished_at,
            expected_base_url=base_url,
        )
        failures.extend(row_failures)
        published_path = evidence_dir / f"{horizon_id}.generated.json"
        digest = ""
        if artifact:
            rendered = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
            published_path.write_text(rendered, encoding="utf-8")
            digest = sha256_bytes(rendered.encode("utf-8"))
        horizon_rows.append(
            {
                **registry_row,
                "status": "pass" if not row_failures else "fail",
                "verdict": "GOLD" if not row_failures else "NOT_GOLD",
                "assertion_count": int(artifact.get("assertion_count") or 0),
                "journey_steps": list(artifact.get("journey_steps") or []),
                "boundaries_verified": list(artifact.get("boundaries_verified") or []),
                "evidence_path": str(published_path),
                "evidence_sha256": digest,
                "failures": row_failures,
            }
        )

    passed_count = sum(row["status"] == "pass" for row in horizon_rows)
    failed_count = len(horizon_rows) - passed_count
    passed = (
        not failures
        and len(horizon_rows) == len(EXPECTED_HORIZON_IDS)
        and failed_count == 0
    )
    return {
        "contract_name": CONTRACT_NAME,
        "generated_at_utc": iso_utc(run_finished_at),
        "status": "pass" if passed else "fail",
        "verdict": PASS_VERDICT if passed else "NOT_HORIZON_PORTFOLIO_GOLD",
        "claim_scope": CLAIM_SCOPE,
        "all_horizons_gold": passed,
        "base_url": base_url,
        "registry_path": str(DEFAULT_REGISTRY),
        "source_inputs": source_inputs,
        "runner": runner,
        "summary": {
            "horizon_count": len(horizon_rows),
            "gold_count": passed_count,
            "failed_count": failed_count,
            "expected_count": len(EXPECTED_HORIZON_IDS),
            "assertion_count": sum(row["assertion_count"] for row in horizon_rows),
        },
        "required_horizon_ids": list(EXPECTED_HORIZON_IDS),
        "horizons": horizon_rows,
        "failures": list(dict.fromkeys(failures)),
        "proof_boundaries": {
            "proves": [
                "fresh rendered-browser execution for every registered shipped-MVP public journey",
                "first-party receipt and artifact routes used by those journeys",
                "identity, authority, privacy, and non-claim boundaries asserted by each journey",
            ],
            "does_not_prove_without_separate_receipts": [
                "future roadmap capabilities outside registered shipped-MVP scope",
                "authenticated owner flows when no governed test identity is available",
                "native desktop behavior on operating systems not executing this browser lane",
                "external provider generation or delivery beyond the verified handoff boundary",
            ],
        },
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def source_input(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": sha256_file(path) if path.is_file() else "",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute and materialize the fail-closed nine-horizon E2E gold matrix.")
    parser.add_argument("--base-url", default=os.environ.get("CHUMMER_PUBLIC_BASE_URL", "https://chummer.run"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--playwright-cli", type=Path, default=DEFAULT_PLAYWRIGHT_CLI)
    parser.add_argument("--node", type=Path, default=Path("/usr/bin/node"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    return parser.parse_args()


def playwright_command(args: argparse.Namespace, artifacts_dir: Path) -> list[str]:
    """Keep Playwright scratch state inside the disposable evidence directory."""
    return [
        str(args.node.resolve()),
        str(args.playwright_cli.resolve()),
        "test",
        "--config",
        str(args.config.resolve()),
        str(args.spec.resolve()),
        "--reporter=json",
        "--output",
        str((artifacts_dir / "playwright-test-results").resolve()),
    ]


def main() -> int:
    args = parse_args()
    base_url = str(args.base_url).strip().rstrip("/")
    if not base_url.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
        raise SystemExit("base URL must use HTTPS or an explicit loopback host")
    required_paths = (args.registry, args.spec, args.config, args.playwright_cli, args.node)
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        payload = {
            "contract_name": CONTRACT_NAME,
            "generated_at_utc": iso_utc(utc_now()),
            "status": "fail",
            "verdict": "NOT_HORIZON_PORTFOLIO_GOLD",
            "failures": [f"required executable input is missing: {path}" for path in missing],
        }
        write_json_atomic(args.output, payload)
        print("horizon_e2e_gold_matrix:fail")
        return 1

    registry_rows, registry_failures = load_registry(args.registry)
    run_started_at = utc_now()
    environment = dict(os.environ)
    environment.pop("FORCE_COLOR", None)
    environment["NO_COLOR"] = "1"
    environment["BASE_URL"] = base_url
    timed_out = False
    stdout = ""
    stderr = ""
    returncode = 1
    with tempfile.TemporaryDirectory(prefix="chummer-horizon-e2e-gold-") as temporary:
        artifacts_dir = Path(temporary)
        command = playwright_command(args, artifacts_dir)
        environment["CHUMMER_COMPLETION_DIR"] = str(artifacts_dir)
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=max(args.timeout_seconds, 1),
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = str(exc.stdout or "")
            stderr = str(exc.stderr or "")
            returncode = 124
        run_finished_at = utc_now()
        stats, parse_failure = parse_playwright_stats(stdout)
        runner = {
            "command": [
                "/usr/bin/node",
                "node_modules/playwright/cli.js",
                "test",
                "--config",
                "playwright.config.ts",
                "tests/public/horizon-e2e-gold.spec.ts",
                "--reporter=json",
                "--output",
                "$CHUMMER_COMPLETION_DIR/playwright-test-results",
            ],
            "returncode": returncode,
            "timed_out": timed_out,
            "stats": stats,
            "parse_failure": parse_failure,
            "stdout_sha256": sha256_bytes(stdout.encode("utf-8")),
            "stderr_sha256": sha256_bytes(stderr.encode("utf-8")),
            "stderr_tail": stderr[-4000:],
            "started_at_utc": iso_utc(run_started_at),
            "finished_at_utc": iso_utc(run_finished_at),
        }
        source_inputs = {
            "registry": source_input(args.registry),
            "browser_spec": source_input(args.spec),
            "playwright_config": source_input(args.config),
            "materializer": source_input(Path(__file__).resolve()),
        }
        payload = build_matrix(
            registry_rows=registry_rows,
            registry_failures=registry_failures,
            artifacts_dir=artifacts_dir,
            evidence_dir=args.evidence_dir,
            base_url=base_url,
            run_started_at=run_started_at,
            run_finished_at=run_finished_at,
            runner=runner,
            source_inputs=source_inputs,
        )
    payload["registry_path"] = str(args.registry.resolve())
    write_json_atomic(args.output, payload)
    print(f"horizon_e2e_gold_matrix:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
