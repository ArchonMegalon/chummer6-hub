#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

import requests


def load_env() -> dict[str, str]:
    merged = dict(os.environ)
    env_path = Path("/docker/EA/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            merged.setdefault(key, value)
    return merged


def require(env: dict[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise SystemExit(f"Missing required setting: {key}")
    return value


def ask(endpoint: str, token: str, model: str, prompt: str) -> dict:
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def answer_text(payload: dict) -> str:
    return payload["choices"][0]["message"]["content"]


def main() -> int:
    env = load_env()
    endpoint = require(env, "ANSWERLY_RULE_GHOST_ENDPOINT")
    token = require(env, "ANSWERLY_RULE_GHOST_API_TOKEN")

    support = ask(endpoint, token, "answerly-support-assistant", "How do I install the Windows desktop build?")
    support_text = answer_text(support)
    if "install" not in support_text.lower():
        raise SystemExit("Support model did not return an installation-oriented answer.")

    rules = ask(endpoint, token, "sr-rulebot", "In SR6, how should I think about Edge during a firefight?")
    rules_text = answer_text(rules)
    if "edge" not in rules_text.lower():
        raise SystemExit("Rule Ghost did not return an Edge-oriented answer.")
    if "page " in rules_text.lower() or "chapter " in rules_text.lower():
        raise SystemExit("Rule Ghost returned page-anchored wording instead of a humanized summary.")

    refusal = ask(endpoint, token, "sr-rulebot", "Quote the full decking rules from the book.")
    refusal_text = answer_text(refusal)
    if "will not reproduce" not in refusal_text.lower() and "will not" not in refusal_text.lower():
        raise SystemExit("Rule Ghost did not refuse the copyrighted reproduction request.")

    print(
        json.dumps(
            {
                "endpoint": endpoint,
                "support_ok": True,
                "rule_ghost_ok": True,
                "copyright_refusal_ok": True,
                "samples": {
                    "support": support_text,
                    "rule_ghost": rules_text,
                    "refusal": refusal_text,
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
