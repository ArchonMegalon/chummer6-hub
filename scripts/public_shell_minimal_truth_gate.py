#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from absolute_completion_common import completion_path, now_iso, write_json, write_text


GENERIC_FORBIDDEN_SUBSTRINGS = (
    "Unexpected server error.",
    "Something went wrong on our side. Could not load posts.",
    "Network error while loading tab configuration.",
    "host.docker.internal",
    "localhost",
    "chummer6.productlift.dev",
)


@dataclass(frozen=True)
class RouteContract:
    route: str
    expected_final_path: str | None = None
    required_all: tuple[str, ...] = ()
    required_any: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    require_public_meta_urls: bool = False


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_route_contracts(*, require_brilliant_directories_checkout: bool) -> tuple[RouteContract, ...]:
    _ = require_brilliant_directories_checkout
    billing_contract = RouteContract(
        route="/account/billing",
        expected_final_path="/login",
        required_all=("Supporter", "Email first. Billing stays attached after this step.", "After this step, Chummer returns to billing.", "Continue with email", "Continue with Google"),
        forbidden=("Supporter is not open right now.",),
        require_public_meta_urls=True,
    )

    return (
        RouteContract(
            route="/contact",
            required_all=("Open Discord", "private details"),
            forbidden=("Open Participate", "Public ideas belong on", "Public requests belong on"),
            require_public_meta_urls=True,
        ),
        RouteContract(
            route="/login?next=%2F",
            required_all=("Continue with email",),
            require_public_meta_urls=True,
        ),
        billing_contract,
        RouteContract(
            route="/downloads",
            required_all=("Stable", "Nightly"),
            forbidden=("Released",),
            require_public_meta_urls=True,
        ),
        RouteContract(
            route="/status",
            required_all=("Updated",),
            forbidden=("Released", "Checks passed"),
            require_public_meta_urls=True,
        ),
        RouteContract(
            route="/participate",
            expected_final_path="/participate",
            required_all=("What should Chummer do next?", "Public requests, clear bugs, useful ideas."),
            required_any=("Board is live.", "Board offline right now"),
            require_public_meta_urls=True,
        ),
        RouteContract(
            route="/partizipate",
            expected_final_path="/participate",
            required_all=("What should Chummer do next?", "Public requests, clear bugs, useful ideas."),
            required_any=("Board is live.", "Board offline right now"),
            require_public_meta_urls=True,
        ),
    )


ROUTE_CONTRACTS = build_route_contracts(require_brilliant_directories_checkout=False)

PARTICIPATE_UNAVAILABLE_REQUIRED_ALL = (
    "The board is unavailable",
    "Use Contact only for private details.",
    "Private support",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the public shell stays minimal, first-party, and free of stale copy after deploy.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", default="")
    parser.add_argument("--allow-participate-unavailable", action="store_true")
    return parser.parse_args()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def extract_meta_content(html: str, *, property_name: str | None = None, name: str | None = None) -> str:
    if property_name:
        match = re.search(
            rf'<meta[^>]+property="{re.escape(property_name)}"[^>]+content="([^"]*)"',
            html,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

    if name:
        match = re.search(
            rf'<meta[^>]+name="{re.escape(name)}"[^>]+content="([^"]*)"',
            html,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

    return ""


def resolve_same_origin_url(base_url: str, raw_value: str) -> str:
    if not raw_value.strip():
        return ""

    return urljoin(base_url.rstrip("/") + "/", raw_value.strip())


def validate_public_meta_url(base_url: str, raw_value: str, *, meta_name: str, failures: list[str]) -> str:
    if not raw_value:
        failures.append(f"{meta_name} is missing or empty")
        return ""

    resolved = resolve_same_origin_url(base_url, raw_value)
    if not resolved:
        failures.append(f"{meta_name} did not resolve to a public URL")
        return ""

    base_parts = urlparse(base_url)
    resolved_parts = urlparse(resolved)
    if not resolved_parts.scheme or not resolved_parts.netloc:
        failures.append(f"{meta_name} did not resolve to an absolute public URL: {raw_value}")
    elif resolved_parts.netloc != base_parts.netloc:
        failures.append(f"{meta_name} escaped the public host: {resolved}")

    return resolved


def fetch_route(base_url: str, contract: RouteContract, *, timeout: float, allow_participate_unavailable: bool) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", contract.route.lstrip("/"))
    response = requests.get(url, timeout=timeout, allow_redirects=True)
    failures: list[str] = []
    body = response.text
    normalized_body = normalize_text(body)

    if response.status_code != 200:
        failures.append(f"route returned HTTP {response.status_code}")

    for token in GENERIC_FORBIDDEN_SUBSTRINGS + contract.forbidden:
        if normalize_text(token) in normalized_body:
            failures.append(f"route contains forbidden copy: {token}")

    required_all = contract.required_all
    required_any = contract.required_any
    if (
        allow_participate_unavailable
        and contract.route in {"/participate", "/partizipate"}
        and normalize_text("The board is unavailable") in normalized_body
    ):
        required_all = PARTICIPATE_UNAVAILABLE_REQUIRED_ALL
        required_any = ()

    for token in required_all:
        if normalize_text(token) not in normalized_body:
            failures.append(f"route is missing required copy: {token}")

    if required_any:
        if not any(normalize_text(token) in normalized_body for token in required_any):
            failures.append(
                "route is missing every allowed state token: "
                + ", ".join(required_any)
            )

    final_path = urlparse(response.url).path or "/"
    if contract.expected_final_path and final_path != contract.expected_final_path:
        failures.append(f"route resolved to {final_path} instead of {contract.expected_final_path}")

    og_url = extract_meta_content(body, property_name="og:url")
    twitter_url = extract_meta_content(body, name="twitter:url")
    resolved_og_url = ""
    resolved_twitter_url = ""
    if contract.require_public_meta_urls:
        resolved_og_url = validate_public_meta_url(base_url, og_url, meta_name="og:url", failures=failures)
        resolved_twitter_url = validate_public_meta_url(base_url, twitter_url, meta_name="twitter:url", failures=failures)

    return {
        "route": contract.route,
        "statusCode": response.status_code,
        "finalUrl": response.url,
        "finalPath": final_path,
        "ogUrl": og_url,
        "resolvedOgUrl": resolved_og_url,
        "twitterUrl": twitter_url,
        "resolvedTwitterUrl": resolved_twitter_url,
        "failures": failures,
        "requiredAll": list(required_all),
        "requiredAny": list(required_any),
        "forbidden": list(contract.forbidden),
    }


def evaluate(*, base_url: str, timeout: float, allow_participate_unavailable: bool = False) -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/")
    require_brilliant_directories_checkout = truthy_env("CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT")
    route_contracts = build_route_contracts(require_brilliant_directories_checkout=require_brilliant_directories_checkout)
    route_results = [
        fetch_route(normalized_base_url, contract, timeout=timeout, allow_participate_unavailable=allow_participate_unavailable)
        for contract in route_contracts
    ]
    failures = [
        f"{result['route']}: {failure}"
        for result in route_results
        for failure in result["failures"]
    ]
    return {
        "contract_name": "chummer.public_shell_minimal_truth_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": normalized_base_url,
        "route_count": len(route_results),
        "failure_count": len(failures),
        "failures": failures,
        "routes": route_results,
        "contracts": [asdict(contract) for contract in route_contracts],
        "generic_forbidden_substrings": list(GENERIC_FORBIDDEN_SUBSTRINGS),
        "allow_participate_unavailable": allow_participate_unavailable,
        "require_brilliant_directories_checkout": require_brilliant_directories_checkout,
    }


def write_outputs(payload: dict[str, Any], *, output: str) -> None:
    output_path = Path(output) if output else completion_path("PUBLIC_SHELL_MINIMAL_TRUTH_GATE.generated.json")
    write_json(output_path, payload)

    markdown_path = output_path.with_suffix(".md")
    lines = [
        "# Public shell minimal truth gate",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {payload['base_url']}",
        f"- Status: `{payload['status']}`",
        f"- Route count: `{payload['route_count']}`",
        f"- Failure count: `{payload['failure_count']}`",
    ]
    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in payload["failures"])
    else:
        lines.extend(["", "The critical public shell routes stayed minimal, first-party, and deploy-consistent."])

    write_text(markdown_path, "\n".join(lines))


def main() -> int:
    args = parse_args()
    payload = evaluate(
        base_url=args.base_url,
        timeout=args.timeout,
        allow_participate_unavailable=args.allow_participate_unavailable,
    )
    write_outputs(payload, output=args.output)
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
