#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from absolute_completion_common import LocalHubApp, StaticHtmlStub, TokenIdentityStub, ensure_completion_root
from verify_participate_billing_honesty import build_payload, write_outputs


BOARD_SENTINEL = "board sentinel"
BOARD_HTML = """<!doctype html><html><head><title>Board</title></head><body><header><a href="/">ProductLift</a><a href="https://app.productlift.dev/login">Log in</a><a href="https://app.productlift.dev/signup">Sign up</a></header><main>board sentinel <a href="/roadmap">roadmap</a></main></body></html>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize runtime proof that Participate only exposes supporter UI when billing is available.")
    parser.add_argument("--completion-dir", default=str(ensure_completion_root()))
    parser.add_argument("--node-runner", default="npx")
    return parser.parse_args()


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


def materialize(completion_dir: Path, node_runner: str) -> dict:
    completion_dir.mkdir(parents=True, exist_ok=True)
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
    write_outputs(completion_dir, payload)
    return payload


def main() -> int:
    args = parse_args()
    completion_dir = Path(args.completion_dir).resolve()
    payload = materialize(completion_dir, args.node_runner)
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
