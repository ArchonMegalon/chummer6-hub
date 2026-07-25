#!/usr/bin/env python3
"""Capture one provider-authenticated topology-B retirement proof bundle.

The workflow using this command is non-mutating. It snapshots the exact public
commit marker and its two content-addressed dependencies only after the Hub
retirement controller has written and read back all three byte streams.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Callable, Mapping

import cloudflare_public_download_transaction as cloudflare
import deploy_public_download_only_cutover as controller


ACTOR = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}[A-Za-z0-9])?$")
ROOT = Path(__file__).resolve().parents[1]


class ProofError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ProofError(message)


def validate_github_context(environment: Mapping[str, str]) -> str:
    source_sha = environment.get("GITHUB_SHA", "")
    actor = environment.get("GITHUB_ACTOR", "")
    triggering_actor = environment.get("GITHUB_TRIGGERING_ACTOR", "")
    if (
        environment.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or environment.get("GITHUB_REPOSITORY")
        != controller.TOPOLOGY_B_SOURCE_REPOSITORY
        or environment.get("GITHUB_REF") != controller.TOPOLOGY_B_SOURCE_REF
        or environment.get("GITHUB_RUN_ATTEMPT") != "1"
        or controller.COMMIT.fullmatch(source_sha) is None
        or ACTOR.fullmatch(actor) is None
        or triggering_actor != actor
    ):
        fail(
            "topology-B retirement proof requires a first-attempt, "
            "same-actor workflow_dispatch from protected Hub main"
        )
    return source_sha


def _preflight_binding(
    proof: Mapping[str, Any],
    field: str,
) -> str:
    value = proof.get(field)
    digest = value.get("sha256") if isinstance(value, dict) else None
    size = value.get("sizeBytes") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != {"sha256", "sizeBytes"}
        or not isinstance(digest, str)
        or controller.SHA256.fullmatch(digest) is None
        or type(size) is not int
        or size <= 0
        or size > 16 * 1024 * 1024
    ):
        fail(f"topology-B {field} binding is malformed")
    return digest


def require_protected_main_ancestry(
    terminal_source_sha: str,
    provider_source_sha: str,
) -> None:
    if (
        controller.COMMIT.fullmatch(terminal_source_sha) is None
        or controller.COMMIT.fullmatch(provider_source_sha) is None
    ):
        fail("Hub source ancestry contains a malformed commit")
    environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
    }
    try:
        observed_head = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(ROOT),
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
            ],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        ancestry = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(ROOT),
                "merge-base",
                "--is-ancestor",
                terminal_source_sha,
                provider_source_sha,
            ],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        fail(f"Hub protected-main ancestry could not be verified: {exc}")
    if observed_head != provider_source_sha or ancestry.returncode != 0:
        fail(
            "retirement source is not an ancestor of the exact "
            "provider-authenticated Hub main checkout"
        )


def capture_public_bundle(
    *,
    source_sha: str,
    output_dir: Path,
    ancestry_verifier: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    if controller.COMMIT.fullmatch(source_sha) is None:
        fail("Hub source SHA is invalid")
    if not output_dir.is_absolute() or output_dir.exists() or output_dir.is_symlink():
        fail("proof output directory must be a new absolute path")
    try:
        output_dir.mkdir(mode=0o700)
    except OSError as exc:
        fail("proof output directory could not be created")
    metadata = output_dir.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        fail("proof output directory metadata is unsafe")

    proof_url = (
        f"{controller.CANONICAL_DOWNLOADS_BASE_URL}/"
        f"{controller.TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME}"
    )
    try:
        proof_bytes = controller.strict_public_retirement_get(proof_url)
        proof = controller._strict_json_object_bytes(
            proof_bytes,
            label="public topology-B retirement proof",
        )
        proof_source = proof.get("source")
        terminal_source_sha = (
            proof_source.get("commit")
            if isinstance(proof_source, dict)
            else None
        )
        if (
            not isinstance(terminal_source_sha, str)
            or controller.COMMIT.fullmatch(terminal_source_sha) is None
        ):
            fail("topology-B terminal source SHA is malformed")
        (ancestry_verifier or require_protected_main_ancestry)(
            terminal_source_sha,
            source_sha,
        )
        committed_sha = _preflight_binding(
            proof,
            "committedBoundaryReceipt",
        )
        post_marker_sha = _preflight_binding(
            proof,
            "postMarkerConvergenceReceipt",
        )
        committed_url = (
            f"{controller.CANONICAL_DOWNLOADS_BASE_URL}/"
            f"{controller.TOPOLOGY_B_PUBLIC_RECEIPT_DIRECTORY}/"
            f"committed-boundary-{committed_sha}.json"
        )
        post_marker_url = (
            f"{controller.CANONICAL_DOWNLOADS_BASE_URL}/"
            f"{controller.TOPOLOGY_B_PUBLIC_RECEIPT_DIRECTORY}/"
            f"post-marker-convergence-{post_marker_sha}.json"
        )
        committed_bytes = controller.strict_public_retirement_get(
            committed_url
        )
        post_marker_bytes = controller.strict_public_retirement_get(
            post_marker_url
        )
        canonical = proof.get("canonicalAuthority")
        publisher_sha256 = (
            canonical.get("publisherSha256")
            if isinstance(canonical, dict)
            else None
        )
        if (
            not isinstance(publisher_sha256, str)
            or controller.SHA256.fullmatch(publisher_sha256) is None
        ):
            fail("canonical publisher SHA-256 is malformed")
        controller.validate_topology_b_public_retirement_bundle(
            proof_bytes=proof_bytes,
            committed_boundary_bytes=committed_bytes,
            post_marker_bytes=post_marker_bytes,
            expected_source_head=terminal_source_sha,
            expected_publisher_sha256=publisher_sha256,
            cloudflare=cloudflare,
        )
    except (controller.CutoverError, OSError, ValueError) as exc:
        fail(f"public topology-B retirement proof did not validate: {exc}")

    entries = {
        controller.TOPOLOGY_B_PUBLIC_RETIREMENT_FILENAME: proof_bytes,
        "committed-boundary-receipt.json": committed_bytes,
        "post-marker-convergence-receipt.json": post_marker_bytes,
    }
    for name, data in entries.items():
        path = output_dir / name
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o444)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
                os.fchmod(handle.fileno(), 0o444)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    descriptor = os.open(
        output_dir,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return {
        "contractName": (
            "chummer6-hub.topology-b-retirement-provider-snapshot.v1"
        ),
        "status": "passed",
        "sourceSha": terminal_source_sha,
        "providerSourceSha": source_sha,
        "entryCount": len(entries),
        "entries": {
            name: {
                "sha256": controller.sha256_bytes(data),
                "sizeBytes": len(data),
                "mode": "0444",
            }
            for name, data in sorted(entries.items())
        },
        "publisherSha256": publisher_sha256,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        context_sha = validate_github_context(os.environ)
        if args.source_sha != context_sha:
            fail("CLI source SHA differs from the GitHub run authority")
        result = capture_public_bundle(
            source_sha=context_sha,
            output_dir=args.output_dir,
        )
    except (ProofError, OSError, ValueError) as exc:
        print(
            f"topology_b_committed_retirement_proof: {exc}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
