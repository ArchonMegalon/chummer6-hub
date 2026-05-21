#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests


ANSWERLY_BASE_URL = "https://api.answerly.io/"
DEFAULT_ENDPOINT = "https://chummer.run/api/v1/chat/completions"
DEFAULT_MODELS_URL = "https://chummer.run/api/v1/models"
DEFAULT_AGENT_ID = "e034e8d9-bfe0-4459-8032-a3892756b854"


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


def answer_text(payload: dict) -> str:
    return payload["choices"][0]["message"]["content"]


def post_answer(endpoint: str, token: str, model: str, prompt: str) -> dict:
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def answerly_post(session: str, path: str, payload: dict) -> dict:
    response = requests.post(
        ANSWERLY_BASE_URL + path,
        json={**payload, "session": session},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def unwrap_list(payload: dict) -> list[dict]:
    value = payload.get("output")
    if isinstance(value, list):
        return value
    value = payload.get("data")
    if isinstance(value, list):
        return value
    value = payload.get("result")
    if isinstance(value, list):
        return value
    return []


def verify_public_endpoint(endpoint: str, models_url: str, token: str) -> dict:
    unauth_models = requests.get(models_url, timeout=60)
    if unauth_models.status_code != 401:
        raise SystemExit(f"Unauthenticated models route returned {unauth_models.status_code}, expected 401.")

    models_response = requests.get(
        models_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    models_response.raise_for_status()
    models_payload = models_response.json()
    model_ids = [item["id"] for item in models_payload["data"]]
    if "sr-rulebot" not in model_ids:
        raise SystemExit("Public models route does not expose sr-rulebot.")

    support_payload = post_answer(endpoint, token, "answerly-support-assistant", "How do I install the Windows desktop build?")
    support_text = answer_text(support_payload)
    if "install" not in support_text.lower():
        raise SystemExit("Support answer did not look installation-oriented.")

    rules_payload = post_answer(endpoint, token, "sr-rulebot", "In SR6, how should I think about Edge during a firefight?")
    rules_text = answer_text(rules_payload)
    if "edge" not in rules_text.lower():
        raise SystemExit("Rule Ghost answer did not mention Edge.")
    if "page " in rules_text.lower() or "chapter " in rules_text.lower():
        raise SystemExit("Rule Ghost answer used page/chapter wording instead of a safe summary.")

    refusal_payload = post_answer(endpoint, token, "sr-rulebot", "Quote the full decking rules from the book.")
    refusal_text = answer_text(refusal_payload)
    if "will not" not in refusal_text.lower():
        raise SystemExit("Rule Ghost refusal path is not active.")

    stream_response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "model": "answerly-support-assistant",
            "stream": True,
            "messages": [{"role": "user", "content": "Say hello"}],
        },
        timeout=60,
    )
    if stream_response.status_code != 400:
        raise SystemExit(f"stream=true returned {stream_response.status_code}, expected 400.")
    stream_body = stream_response.text.lower()
    if "stream=true" not in stream_body and "not supported" not in stream_body:
        raise SystemExit("stream=true rejection did not explain the unsupported streaming posture.")

    return {
        "endpoint": endpoint,
        "models_url": models_url,
        "model_ids": model_ids,
        "unauthenticated_models_rejected": True,
        "streaming_rejected": True,
        "support_sample": support_text,
        "rule_sample": rules_text,
        "refusal_sample": refusal_text,
    }


def verify_live_oauth(base_url: str) -> dict:
    session = requests.Session()

    login_response = session.get(f"{base_url}/login?next=%2Fhome", timeout=60)
    login_response.raise_for_status()
    login_body = login_response.text
    if "Continue with Google" not in login_body:
        raise SystemExit("Login page does not advertise the Google handoff.")

    oauth_response = session.get(
        f"{base_url}/auth/google/start?next=%2Fhome",
        allow_redirects=False,
        timeout=60,
    )
    if oauth_response.status_code != 302:
        raise SystemExit(f"Google OAuth start returned {oauth_response.status_code}, expected 302.")

    redirect = oauth_response.headers.get("Location", "")
    if not redirect.startswith("https://accounts.google.com/o/oauth2/v2/auth"):
        raise SystemExit("Google OAuth start did not redirect to Google Accounts.")

    parsed = urlparse(redirect)
    query = parse_qs(parsed.query)
    redirect_uri = query.get("redirect_uri", [""])[0]
    if redirect_uri != f"{base_url}/auth/google/callback":
        raise SystemExit(f"Google OAuth redirect_uri mismatch: {redirect_uri!r}")

    required_fields = {
        "client_id": query.get("client_id", [""])[0],
        "response_type": query.get("response_type", [""])[0],
        "scope": query.get("scope", [""])[0],
        "state": query.get("state", [""])[0],
        "nonce": query.get("nonce", [""])[0],
        "code_challenge": query.get("code_challenge", [""])[0],
        "code_challenge_method": query.get("code_challenge_method", [""])[0],
    }
    missing = [key for key, value in required_fields.items() if not value]
    if missing:
        raise SystemExit(f"Google OAuth redirect is missing required fields: {', '.join(missing)}")
    if required_fields["response_type"] != "code":
        raise SystemExit("Google OAuth response_type is not code.")
    if required_fields["code_challenge_method"] != "S256":
        raise SystemExit("Google OAuth code_challenge_method is not S256.")

    return {
        "login_ok": True,
        "google_handoff_ok": True,
        "redirect_uri": redirect_uri,
        "oauth_redirect": redirect,
    }


def verify_answerly_workspace(env: dict[str, str], expected_endpoint: str) -> dict:
    email = require(env, "ANSWERLY_IO_USERNAME")
    password = require(env, "ANSWERLY_IO_PASSWORD")
    expected_agent_id = env.get("ANSWERLY_RULE_GHOST_AGENT_ID", DEFAULT_AGENT_ID)

    login = requests.post(
        ANSWERLY_BASE_URL + "user-login",
        json={"input": {"mode": "native", "email": email, "password": password}, "session": ""},
        timeout=60,
    ).json()
    session = login["output"]["session"]
    bootstrap = answerly_post(session, "user-login-data", {"input": {"id": "", "companyId": "", "workspaceId": ""}})["output"]
    company_id = bootstrap["user"]["companyId"]
    workspace_id = bootstrap["user"]["workspaceId"]

    agents = unwrap_list(answerly_post(session, "answerly-agent-list", {"input": {"companyId": company_id, "workspaceId": workspace_id}}))
    agent = next((item for item in agents if item.get("id") == expected_agent_id), None)
    if agent is None:
        raise SystemExit(f"Expected Answerly agent {expected_agent_id} was not found.")

    connection_id = agent.get("connectionId", "").strip()
    if not connection_id:
        raise SystemExit("Rule Ghost agent does not have an LLM connection configured.")

    connections = unwrap_list(answerly_post(session, "ai/connection/all", {"input": {"companyId": company_id, "workspaceId": workspace_id}}))
    connection = next((item for item in connections if item.get("id") == connection_id), None)
    if connection is None:
        raise SystemExit(f"Could not find configured connection {connection_id} in Answerly.")

    actual_endpoint = (connection.get("endpoint") or "").strip()
    if actual_endpoint != expected_endpoint:
        raise SystemExit(f"Answerly points at {actual_endpoint!r}, expected {expected_endpoint!r}.")

    return {
        "agent_id": agent.get("id"),
        "agent_name": agent.get("name"),
        "connection_id": connection.get("id"),
        "connection_platform": connection.get("platform"),
        "connection_endpoint": actual_endpoint,
        "workspace_id": workspace_id,
        "company_id": company_id,
    }


def main() -> int:
    env = load_env()
    endpoint = env.get("ANSWERLY_RULE_GHOST_ENDPOINT", DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT
    models_url = endpoint.rsplit("/", 2)[0] + "/models" if endpoint.endswith("/chat/completions") else DEFAULT_MODELS_URL
    token = require(env, "ANSWERLY_RULE_GHOST_API_TOKEN")
    base_url = endpoint.rsplit("/api/v1/chat/completions", 1)[0]

    public_check = verify_public_endpoint(endpoint, models_url, token)
    oauth_check = verify_live_oauth(base_url)
    workspace_check = verify_answerly_workspace(env, endpoint)

    print(
        json.dumps(
            {
                "verdict": "ANSWERLY_RULE_GHOST_LIVE_VERIFIED",
                "public": public_check,
                "oauth": oauth_check,
                "answerly_workspace": workspace_check,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
