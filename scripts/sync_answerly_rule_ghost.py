#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

import requests


ANSWERLY_BASE_URL = "https://api.answerly.io/"
DEFAULT_AGENT_NAME = "SR Rulebot"
DEFAULT_AGENT_ID = "e034e8d9-bfe0-4459-8032-a3892756b854"
DEFAULT_CONNECTION_ID = "434b7017-5669-458a-845e-d3c67365a573"


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


def owned_rulebooks() -> list[str]:
    roots = [
        Path("/mnt/pcloud/personal/Roleplay/sr"),
        Path("/mnt/pcloud/personal/Roleplay/sr/German"),
    ]
    found: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for pdf in root.glob("*.pdf"):
            if pdf.name not in found:
                found.append(pdf.name)
    return sorted(found)


def build_instructions(books: list[str]) -> str:
    titles = "\n".join(f"- {title}" for title in books[:12])
    return textwrap.dedent(
        f"""
        You are Rule Ghost, a Shadowrun rules assistant for Tibor's owned library.

        Operating posture:
        1. Answer Shadowrun rules questions in plain language.
        2. Prefer concise summaries and short bullet points over dense prose.
        3. Ask the user to clarify the edition when SR5 and SR6 differ in important ways.
        4. Never reproduce book wording, long excerpts, tables, or page-by-page content.
        5. Never claim exact wording from a rulebook. Summarize the rule instead.
        6. If the user asks for private campaign advice, hidden GM information, or secret NPC state, refuse and explain the boundary briefly.
        7. If you are uncertain, say what is uncertain and ask one narrowing question.
        8. Treat the loaded library as owned reference material, but only answer with paraphrased summaries.
        9. When useful, cite only the book title and a high-level section hint, never long quotations.
        10. Keep the tone human, direct, and practical.

        Loaded owned titles:
        {titles if titles else "- Shadowrun Fifth Edition Core Rulebook\\n- Shadowrun 5D - Grundregelwerk\\n- Shadowrun Sixth World"}
        """
    ).strip()


def build_qa_seed() -> list[tuple[str, str]]:
    return [
        (
            "Which Shadowrun books are loaded into Rule Ghost?",
            "Rule Ghost is currently grounded on Tibor's owned Shadowrun books and should summarize them in its own words rather than reproduce them.",
        ),
        (
            "Can you quote rulebook text or reproduce tables?",
            "No. Rule Ghost should explain mechanics in plain language, but it should not reproduce book wording, long excerpts, structured tables, or page-by-page content.",
        ),
        (
            "How should I ask a Shadowrun rules question?",
            "Start with the edition, then name the exact mechanic or action, and finally describe the confusing situation. That gives the assistant enough context to summarize the right rule path without guessing.",
        ),
        (
            "What is Edge for in SR5?",
            "In SR5, Edge is a scarce luck reserve. Use it when the moment really matters: improving a key roll, pushing through a bad spot, or giving yourself a better chance on something critical.",
        ),
        (
            "What is Edge for in SR6?",
            "In SR6, Edge is a more active momentum currency. It moves in and out during play based on positioning, gear, and circumstance, so players are expected to think about it much more often than in SR5.",
        ),
        (
            "How should I think about initiative in Shadowrun?",
            "Treat initiative as the game's action-order system. In SR5 it leans harder on multiple passes and score reduction over the round, while SR6 uses a flatter, easier-to-read turn flow. If the edition is not clear, ask first.",
        ),
        (
            "What does a glitch mean in Shadowrun?",
            "A glitch means the attempt resolves with a complication. Keep the main outcome in view, then layer on a messy side effect, added cost, or unintended consequence instead of treating it like a totally separate rule path.",
        ),
        (
            "How should I think about Drain or Fade?",
            "Drain or Fade is the balancing cost after a magical or resonance-heavy action. Resolve the main effect, then handle the backlash with the edition's resistance process and apply whatever consequence remains.",
        ),
        (
            "How should I think about Matrix questions when the edition is unclear?",
            "Matrix procedures change enough between editions that the assistant should ask whether you mean SR5 or SR6 before it goes narrow. Once the edition is clear, it can summarize the action, resistance, and trace-pressure flow in plain language.",
        ),
        (
            "How should I think about damage and wound penalties?",
            "Damage matters twice: first when you resist the hit, then later when accumulated injury starts dragging down performance. Track the damage cleanly, and only then apply the edition's injury-pressure posture.",
        ),
    ]


def build_title_qas(books: list[str]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for title in books[:80]:
        label = title.replace("_", " ").replace(".pdf", "").strip()
        results.append(
            (
                f"Do you have {label} in the owned Shadowrun library?",
                f"Yes. {label} is in the owned Shadowrun library. I can use it as a private reference anchor, but I should still answer with paraphrased summaries instead of reproducing book text.",
            )
        )

    return results


def post(session: str, path: str, payload: dict) -> dict:
    response = requests.post(
        ANSWERLY_BASE_URL + path,
        json={**payload, "session": session},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def ensure_connection(
    session: str,
    company_id: str,
    workspace_id: str,
    connection_id: str,
    endpoint: str,
    api_token: str,
) -> tuple[str, dict]:
    listing = post(session, "ai/connection/all", {"input": {"companyId": company_id, "workspaceId": workspace_id}})
    existing = listing.get("output", []) or []
    current = next((item for item in existing if item.get("id") == connection_id), None)
    payload = {
        "id": connection_id if current is not None else "",
        "companyId": company_id,
        "workspaceId": workspace_id,
        "endpoint": endpoint,
        "platform": "Azure",
        "model": "sr-rulebot",
        "apiKey": api_token,
    }
    task = "ai/connection/edit" if current is not None else "ai/connection/new"
    result = post(session, task, {"aiConnection": payload})
    output = result.get("output") or result.get("data") or payload
    return output.get("id") or connection_id, output


def ensure_agent(
    session: str,
    company_id: str,
    workspace_id: str,
    agent_id: str,
    connection_id: str,
    instructions: str,
) -> tuple[str, dict]:
    agents = post(session, "answerly-agent-list", {"input": {"companyId": company_id, "workspaceId": workspace_id}})["output"]
    agent = next((item for item in agents if item.get("id") == agent_id), None)
    if agent is None:
        agent = next((item for item in agents if item.get("name") == DEFAULT_AGENT_NAME), None)

    if agent is None:
        payload = {
            "id": "",
            "companyId": company_id,
            "workspaceId": workspace_id,
            "name": DEFAULT_AGENT_NAME,
            "picture": "/icons/book.svg",
            "instructions": instructions,
            "connectionId": connection_id,
            "dailyTokenLimit": 0,
            "tokenLimiter": {"mode": "no-limit", "value": 0},
            "createUnknownQA": True,
            "transcripts": {"enabled": False, "emailAddresses": []},
            "answerlyV2": {"enabled": False},
        }
        result = post(session, "answerly-agent-create", {"input": payload})
        created = result.get("output") or payload
        return created.get("id", agent_id), created

    agent["name"] = DEFAULT_AGENT_NAME
    agent["connectionId"] = connection_id
    agent["instructions"] = instructions
    result = post(session, "answerly-agent-edit", {"input": agent})
    updated = result.get("output") or agent
    return updated.get("id", agent.get("id", agent_id)), updated


def main() -> int:
    env = load_env()
    email = require(env, "ANSWERLY_IO_USERNAME")
    password = require(env, "ANSWERLY_IO_PASSWORD")
    endpoint = require(env, "ANSWERLY_RULE_GHOST_ENDPOINT")
    api_token = require(env, "ANSWERLY_RULE_GHOST_API_TOKEN")
    requested_agent_id = env.get("ANSWERLY_RULE_GHOST_AGENT_ID", DEFAULT_AGENT_ID)
    connection_id = env.get("ANSWERLY_RULE_GHOST_CONNECTION_ID", DEFAULT_CONNECTION_ID)

    login = requests.post(
        ANSWERLY_BASE_URL + "user-login",
        json={"input": {"mode": "native", "email": email, "password": password}, "session": ""},
        timeout=60,
    ).json()
    session = login["output"]["session"]
    bootstrap = post(session, "user-login-data", {"input": {"id": "", "companyId": "", "workspaceId": ""}})["output"]
    company_id = bootstrap["user"]["companyId"]
    workspace_id = bootstrap["user"]["workspaceId"]

    books = owned_rulebooks()
    instructions = build_instructions(books)
    connection_id, connection_result = ensure_connection(
        session=session,
        company_id=company_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        endpoint=endpoint,
        api_token=api_token,
    )
    agent_id, agent_result = ensure_agent(
        session=session,
        company_id=company_id,
        workspace_id=workspace_id,
        agent_id=requested_agent_id,
        connection_id=connection_id,
        instructions=instructions,
    )

    existing = post(session, "answerly-qa-list", {"input": {"companyId": company_id, "workspaceId": workspace_id}})["output"]
    existing_by_question = {item.get("question"): item for item in existing}
    created = 0
    updated = 0
    for question, answer in [*build_qa_seed(), *build_title_qas(books)]:
        payload = existing_by_question.get(
            question,
            {
                "id": "",
                "companyId": company_id,
                "workspaceId": workspace_id,
                "vectorId": "",
                "agentId": agent_id,
                "question": question,
                "answer": answer,
                "ts": "0",
                "embeddingStatus": "initial",
                "stats": {"hits": 0, "likes": 0, "dislikes": 0},
            },
        )
        payload.update(
            {
                "companyId": company_id,
                "workspaceId": workspace_id,
                "agentId": agent_id,
                "question": question,
                "answer": answer,
            }
        )
        task = "answerly-qa-edit" if payload.get("id") else "answerly-qa-create"
        result = post(session, task, {"input": payload})
        if result.get("error"):
            raise SystemExit(f"{task} failed for {question!r}: {json.dumps(result)}")
        if task.endswith("edit"):
            updated += 1
        else:
            created += 1

    print(
        json.dumps(
            {
                "connection": connection_result,
                "agent_id": agent_id,
                "agent": {"id": agent_id, "name": DEFAULT_AGENT_NAME},
                "rulebooks_indexed": len(books),
                "qa_created": created,
                "qa_updated": updated,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
