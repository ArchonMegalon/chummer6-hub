#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RUN_SERVICES_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from absolute_completion_common import LocalHubApp, StaticHtmlStub, TokenIdentityStub, ensure_completion_root
from verify_participate_billing_honesty import build_payload, write_outputs


BOARD_SENTINEL = "board sentinel"
BOARD_HTML = """<!doctype html><html><head><title>Board</title></head><body><header><a href="/">ProductLift</a><a href="https://app.productlift.dev/login">Log in</a><a href="https://app.productlift.dev/signup">Sign up</a></header><main>board sentinel <a href="/roadmap">roadmap</a></main></body></html>"""
DEFAULT_REUSE_RECEIPT_MAX_AGE_HOURS = float(
    os.environ.get("CHUMMER_PARTICIPATE_BILLING_REUSE_MAX_AGE_HOURS", "24")
)
MATERIALIZER_SOURCE_FILES = (
    SCRIPT_DIR / "materialize_participate_billing_honesty.py",
    SCRIPT_DIR / "verify_participate_billing_honesty.py",
    SCRIPT_DIR / "absolute_completion_common.py",
    RUN_SERVICES_ROOT / "tests" / "public" / "participate-billing-auth.spec.ts",
    RUN_SERVICES_ROOT / "tests" / "public" / "participate-billing-unavailable.spec.ts",
)
CHILD_RECEIPT_NAMES = (
    "PARTICIPATE_BILLING_AUTH_E2E.generated.json",
    "PARTICIPATE_BILLING_UNAVAILABLE_E2E.generated.json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize runtime proof that Participate only exposes supporter UI when billing is available.")
    parser.add_argument("--completion-dir", default=str(ensure_completion_root()))
    parser.add_argument("--node-runner", default="npx")
    parser.add_argument("--reuse-existing-receipts", action="store_true")
    parser.add_argument("--reuse-receipt-max-age-hours", type=float, default=DEFAULT_REUSE_RECEIPT_MAX_AGE_HOURS)
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compute_materializer_source_digest() -> str:
    digest = hashlib.sha256()
    for path in MATERIALIZER_SOURCE_FILES:
        resolved = path.resolve()
        digest.update(str(resolved.relative_to(RUN_SERVICES_ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(resolved.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def artifact_generated_at_text(payload: dict) -> str:
    return str(
        payload.get("generated_at_utc")
        or payload.get("generatedAtUtc")
        or payload.get("generated_at")
        or payload.get("generatedAt")
        or ""
    ).strip()


def generated_at_is_fresh(value: str, max_age_hours: float) -> bool:
    if not value:
        return False
    try:
        generated_at = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return False
    return generated_at >= datetime.now(UTC) - timedelta(hours=max_age_hours)


def maybe_reuse_existing_receipts(
    completion_dir: Path,
    *,
    reuse_receipt_max_age_hours: float,
    materializer_source_digest: str,
) -> dict | None:
    honesty_path = completion_dir / "PARTICIPATE_BILLING_HONESTY.generated.json"
    if not honesty_path.is_file():
        return None

    payload = read_json(honesty_path)
    if str(payload.get("status") or "").strip().lower() != "pass":
        return None
    if str(payload.get("materializer_source_digest") or "").strip() != materializer_source_digest:
        return None
    if not generated_at_is_fresh(artifact_generated_at_text(payload), reuse_receipt_max_age_hours):
        return None

    for receipt_name in CHILD_RECEIPT_NAMES:
        receipt_path = completion_dir / receipt_name
        if not receipt_path.is_file():
            return None
        receipt_payload = read_json(receipt_path)
        if str(receipt_payload.get("status") or "").strip().lower() != "pass":
            return None
        if not generated_at_is_fresh(artifact_generated_at_text(receipt_payload), reuse_receipt_max_age_hours):
            return None

    return payload


def run_playwright(node_runner: str, spec_path: str, env: dict[str, str]) -> None:
    command = [node_runner]
    if Path(node_runner).name == "npx":
        command.append("--no-install")
    command.extend(["playwright", "test", spec_path])
    subprocess.run(
        command,
        check=True,
        env=env,
    )


def materialize(
    completion_dir: Path,
    node_runner: str,
    *,
    reuse_existing_receipts: bool = False,
    reuse_receipt_max_age_hours: float = DEFAULT_REUSE_RECEIPT_MAX_AGE_HOURS,
) -> dict:
    completion_dir.mkdir(parents=True, exist_ok=True)
    materializer_source_digest = compute_materializer_source_digest()
    if reuse_existing_receipts:
        reused = maybe_reuse_existing_receipts(
            completion_dir,
            reuse_receipt_max_age_hours=reuse_receipt_max_age_hours,
            materializer_source_digest=materializer_source_digest,
        )
        if reused is not None:
            return reused

    base_env = os.environ.copy()
    base_env["CHUMMER_COMPLETION_DIR"] = str(completion_dir)

    identity = TokenIdentityStub(
        access_token="test-token",
        subject_id="user-test",
        display_name="Casey Runner",
        email="runner@example.com",
    )
    board = StaticHtmlStub(html=BOARD_HTML)

    with identity, board:
        configured_env = {
            "CHUMMER_PRODUCTLIFT_FEEDBACK_URL": board.base_url,
            "BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL": "https://billing.example.test/supporter",
            "BRILLIANT_DIRECTORIES_FREE_PLAN_URL": "https://billing.example.test/free",
            "BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL": "https://billing.example.test/manage",
            "BRILLIANT_DIRECTORIES_SYNC_SECRET": "local-secret",
            "BRILLIANT_DIRECTORIES_CHECKOUT_USER_ID_PARAMETER": "external_user",
            "BRILLIANT_DIRECTORIES_CHECKOUT_PLAN_PARAMETER": "membership_plan",
        }
        with LocalHubApp(identity_base_url=identity.base_url, extra_env=configured_env, no_build=True) as app:
            env = dict(base_env)
            env.update(
                {
                    "BASE_URL": app.base_url,
                    "CHUMMER_E2E_IDENTITY_TOKEN": identity.access_token,
                    "CHUMMER_E2E_BOARD_BASE_URL": board.base_url,
                    "CHUMMER_E2E_BOARD_SENTINEL": BOARD_SENTINEL,
                }
            )
            run_playwright(node_runner, "tests/public/participate-billing-auth.spec.ts", env)

        unavailable_env = {
            "CHUMMER_PRODUCTLIFT_FEEDBACK_URL": board.base_url,
        }
        with LocalHubApp(identity_base_url=identity.base_url, extra_env=unavailable_env, no_build=True) as app:
            env = dict(base_env)
            env.update(
                {
                    "BASE_URL": app.base_url,
                    "CHUMMER_E2E_IDENTITY_TOKEN": identity.access_token,
                    "CHUMMER_E2E_BOARD_SENTINEL": BOARD_SENTINEL,
                }
            )
            run_playwright(node_runner, "tests/public/participate-billing-unavailable.spec.ts", env)

    payload = build_payload(completion_dir)
    payload["materializer_source_digest"] = materializer_source_digest
    payload["materializer_source_files"] = [
        str(path.resolve().relative_to(RUN_SERVICES_ROOT))
        for path in MATERIALIZER_SOURCE_FILES
    ]
    payload["reuse_receipt_max_age_hours"] = reuse_receipt_max_age_hours
    write_outputs(completion_dir, payload)
    return payload


def main() -> int:
    args = parse_args()
    completion_dir = Path(args.completion_dir).resolve()
    payload = materialize(
        completion_dir,
        args.node_runner,
        reuse_existing_receipts=args.reuse_existing_receipts,
        reuse_receipt_max_age_hours=args.reuse_receipt_max_age_hours,
    )
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
