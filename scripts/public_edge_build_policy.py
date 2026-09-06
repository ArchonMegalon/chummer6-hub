#!/usr/bin/env python3
"""Shared fail-closed public-edge build-source policy."""

from __future__ import annotations

import ast
import hashlib
import re
from typing import Any, Iterable, Mapping, Sequence


PUBLIC_EDGE_BUILD_SERVICE_TARGETS = {
    "chummer-portal": "",
    "chummer-install-linking-postgres-admin": (
        "install-linking-postgres-tool-final"
    ),
    "chummer-install-linking-postgres-runtime-proof": (
        "install-linking-postgres-tool-final"
    ),
    "chummer-install-linking-postgres-import-presence-proof": (
        "install-linking-postgres-tool-final"
    ),
    "chummer-install-linking-postgres-import": (
        "install-linking-postgres-tool-final"
    ),
}
PUBLIC_EDGE_NAMED_CONTEXT_NAMES = (
    "core-runtime-bundle",
    "design-product",
    "fleet-media-factory-contracts",
    "hub-registry-source",
    "hub-package-feed-input",
    "run-services-source",
)
PUBLIC_EDGE_BUILD_ARG_NAMES = (
    "CHUMMER_BUILD_CONCURRENCY",
    "CHUMMER_RUNTIME_GID",
    "CHUMMER_RUNTIME_UID",
)
PUBLIC_EDGE_BUILD_KEYS_BY_SERVICE = {
    service_name: frozenset(
        {
            "additional_contexts",
            "args",
            "context",
            "dockerfile",
            *({"target"} if target else set()),
        }
    )
    for service_name, target in PUBLIC_EDGE_BUILD_SERVICE_TARGETS.items()
}
PUBLIC_EDGE_COMPOSE_TOP_LEVEL_KEYS = frozenset(
    {
        "name",
        "networks",
        "services",
        "volumes",
    }
)
PUBLIC_EDGE_COMPOSE_PROJECT_NAME = "chummer6-hub"
PUBLIC_EDGE_RAW_SERVICE_KEYS_BY_SERVICE = {
    "chummer-portal": frozenset(
        {
            "build",
            "cap_drop",
            "cpu_shares",
            "cpus",
            "depends_on",
            "env_file",
            "environment",
            "extra_hosts",
            "healthcheck",
            "image",
            "mem_limit",
            "networks",
            "ports",
            "restart",
            "security_opt",
            "ulimits",
            "user",
            "volumes",
        }
    ),
    "chummer-install-linking-postgres-admin": frozenset(
        {
            "build",
            "cap_drop",
            "command",
            "environment",
            "extra_hosts",
            "image",
            "networks",
            "profiles",
            "read_only",
            "restart",
            "security_opt",
            "tmpfs",
            "ulimits",
            "user",
            "volumes",
        }
    ),
    "chummer-install-linking-postgres-runtime-proof": frozenset(
        {
            "build",
            "cap_drop",
            "command",
            "environment",
            "extra_hosts",
            "image",
            "networks",
            "profiles",
            "read_only",
            "restart",
            "security_opt",
            "tmpfs",
            "ulimits",
            "user",
            "volumes",
        }
    ),
    "chummer-install-linking-postgres-import-presence-proof": frozenset(
        {
            "build",
            "cap_drop",
            "command",
            "environment",
            "image",
            "network_mode",
            "profiles",
            "read_only",
            "restart",
            "security_opt",
            "tmpfs",
            "ulimits",
            "user",
            "volumes",
        }
    ),
    "chummer-install-linking-postgres-import": frozenset(
        {
            "build",
            "cap_drop",
            "command",
            "environment",
            "extra_hosts",
            "image",
            "networks",
            "profiles",
            "read_only",
            "restart",
            "security_opt",
            "tmpfs",
            "ulimits",
            "user",
            "volumes",
        }
    ),
}
PUBLIC_EDGE_RAW_SERVICE_IMAGES = {
    "chummer-portal": "chummer-run-api:local",
    "chummer-install-linking-postgres-admin": (
        "chummer-install-linking-postgres-tool:local"
    ),
    "chummer-install-linking-postgres-runtime-proof": (
        "chummer-install-linking-postgres-tool:local"
    ),
    "chummer-install-linking-postgres-import-presence-proof": (
        "chummer-install-linking-postgres-tool:local"
    ),
    "chummer-install-linking-postgres-import": (
        "chummer-install-linking-postgres-tool:local"
    ),
}
PUBLIC_EDGE_SERVICE_PROFILES_BY_SERVICE = {
    "chummer-portal": (),
    "chummer-install-linking-postgres-admin": (
        "install-linking-postgres-admin",
    ),
    "chummer-install-linking-postgres-runtime-proof": (
        "install-linking-postgres-admin",
    ),
    "chummer-install-linking-postgres-import-presence-proof": (
        "install-linking-postgres-admin",
    ),
    "chummer-install-linking-postgres-import": (
        "install-linking-postgres-admin",
    ),
}
PUBLIC_EDGE_RENDERED_BUILD_SERVICE_NAMES = frozenset(
    {
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-import",
        "chummer-install-linking-postgres-import-presence-proof",
        "chummer-install-linking-postgres-runtime-proof",
        "chummer-play-web",
        "chummer-portal",
        "chummer-presentation-api",
        "chummer-public-blazor",
        "chummer-run-identity",
    }
)
PUBLIC_EDGE_RENDERED_SERVICE_KEYS_BY_SERVICE = {
    "chummer-portal": frozenset(
        {
            "build",
            "cap_drop",
            "command",
            "cpu_shares",
            "cpus",
            "depends_on",
            "entrypoint",
            "environment",
            "extra_hosts",
            "healthcheck",
            "image",
            "mem_limit",
            "networks",
            "ports",
            "restart",
            "security_opt",
            "ulimits",
            "user",
            "volumes",
        }
    ),
    "chummer-install-linking-postgres-admin": frozenset(
        {
            "build",
            "cap_drop",
            "command",
            "entrypoint",
            "environment",
            "extra_hosts",
            "image",
            "networks",
            "profiles",
            "read_only",
            "restart",
            "security_opt",
            "tmpfs",
            "ulimits",
            "user",
            "volumes",
        }
    ),
    "chummer-install-linking-postgres-runtime-proof": frozenset(
        {
            "build",
            "cap_drop",
            "command",
            "entrypoint",
            "environment",
            "extra_hosts",
            "image",
            "networks",
            "profiles",
            "read_only",
            "restart",
            "security_opt",
            "tmpfs",
            "ulimits",
            "user",
            "volumes",
        }
    ),
    "chummer-install-linking-postgres-import-presence-proof": frozenset(
        {
            "build",
            "cap_drop",
            "command",
            "entrypoint",
            "environment",
            "image",
            "network_mode",
            "profiles",
            "read_only",
            "restart",
            "security_opt",
            "tmpfs",
            "ulimits",
            "user",
            "volumes",
        }
    ),
    "chummer-install-linking-postgres-import": frozenset(
        {
            "build",
            "cap_drop",
            "command",
            "entrypoint",
            "environment",
            "extra_hosts",
            "image",
            "networks",
            "profiles",
            "read_only",
            "restart",
            "security_opt",
            "tmpfs",
            "ulimits",
            "user",
            "volumes",
        }
    ),
}
PUBLIC_EDGE_DOCKER_STAGE_ORDER = (
    "public-pwa-proof",
    "hub-package-feed",
    "build",
    "install-linking-postgres-tool-final",
    "final",
)
PUBLIC_EDGE_DOCKER_BUILD_STAGE_INSTRUCTION_COUNT = 44
PUBLIC_EDGE_DOCKER_BUILD_STAGE_SHA256 = (
    "32e5233a0e849a1ca0532704feed4feef353d50d31fdeefa84b9cb043d7bed8c"
)
PUBLIC_EDGE_DOCKER_NAMED_CONTEXTS_BY_STAGE = {
    "public-pwa-proof": frozenset({"run-services-source"}),
    "hub-package-feed": frozenset(
        {
            "core-runtime-bundle",
            "hub-package-feed-input",
            "run-services-source",
        }
    ),
    "build": frozenset(
        {
            "fleet-media-factory-contracts",
            "hub-registry-source",
            "run-services-source",
        }
    ),
    "install-linking-postgres-tool-final": frozenset(),
    "final": frozenset({"design-product", "run-services-source"}),
}
PUBLIC_EDGE_DOCKER_COPY_STAGE_REFERENCES_BY_STAGE = {
    "public-pwa-proof": frozenset(),
    "hub-package-feed": frozenset({"public-pwa-proof"}),
    "build": frozenset({"hub-package-feed", "public-pwa-proof"}),
    "install-linking-postgres-tool-final": frozenset({"build"}),
    "final": frozenset({"build"}),
}
PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE = {
    "public-pwa-proof": frozenset(
        {
            "COPY --from=run-services-source scripts/validate_public_pwa_proof_authority.py scripts/validate_public_pwa_proof_authority.py",
            "COPY --from=run-services-source scripts/verify_public_pwa_static_assets.py scripts/verify_public_pwa_static_assets.py",
            "COPY --from=run-services-source scripts/generate_public_play_worker_projection.py scripts/generate_public_play_worker_projection.py",
            "COPY --from=run-services-source Chummer.Run.Api/public-pwa-proof-authority.json Chummer.Run.Api/public-pwa-proof-authority.json",
            "COPY --from=run-services-source Chummer.Run.Api/play-pwa-required-inventory.json Chummer.Run.Api/play-pwa-required-inventory.json",
            "COPY --from=run-services-source Chummer.Run.Api/play-pwa-mirrors.json Chummer.Run.Api/play-pwa-mirrors.json",
            "COPY --from=run-services-source Chummer.Run.Api/play-worker-projection.json Chummer.Run.Api/play-worker-projection.json",
            "COPY --from=run-services-source Chummer.Run.Api/service-worker.public-edge.template.js Chummer.Run.Api/service-worker.public-edge.template.js",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/mobile-install-shell.js Chummer.Run.Api/wwwroot/mobile-install-shell.js",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/mobile.css Chummer.Run.Api/wwwroot/mobile.css",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/manifest.play.webmanifest Chummer.Run.Api/wwwroot/manifest.play.webmanifest",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/manifest.player.webmanifest Chummer.Run.Api/wwwroot/manifest.player.webmanifest",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/manifest.gm.webmanifest Chummer.Run.Api/wwwroot/manifest.gm.webmanifest",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/manifest.observer.webmanifest Chummer.Run.Api/wwwroot/manifest.observer.webmanifest",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/icons/icon-192.png Chummer.Run.Api/wwwroot/icons/icon-192.png",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/icons/icon-512.png Chummer.Run.Api/wwwroot/icons/icon-512.png",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/icons/icon-192.svg Chummer.Run.Api/wwwroot/icons/icon-192.svg",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/icons/icon-512.svg Chummer.Run.Api/wwwroot/icons/icon-512.svg",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/mobile/service-worker.js Chummer.Run.Api/wwwroot/mobile/service-worker.js",
            "COPY --from=run-services-source Chummer.Run.Api/wwwroot/service-worker.js Chummer.Run.Api/wwwroot/service-worker.js",
        }
    ),
    "hub-package-feed": frozenset(
        {
            "COPY --from=run-services-source global.json global.json",
            "COPY --from=run-services-source scripts/ai/bootstrap-hub-package-feed.py scripts/ai/bootstrap-hub-package-feed.py",
            "COPY --from=run-services-source eng/package-plane.lock.json eng/package-plane.lock.json",
            "COPY --from=run-services-source eng/core-main-runtime-artifact-authority.json eng/core-main-runtime-artifact-authority.json",
            "COPY --from=run-services-source eng/core-runtime-bundle/core-runtime-bundle-input.json eng/core-runtime-bundle/core-runtime-bundle-input.json",
            "COPY --from=core-runtime-bundle chummer-core-runtime-package-plane-c06f22c185c7b733637fdb76b3cf333f31716781.zip eng/core-runtime-bundle/chummer-core-runtime-package-plane-c06f22c185c7b733637fdb76b3cf333f31716781.zip",
            "COPY --from=hub-package-feed-input . /opt/chummer-package-feed",
        }
    ),
    "build": frozenset(
        {
            "COPY --from=run-services-source Directory.Build.props chummer.run-services/",
            "COPY --from=run-services-source eng/NuGet.Container.Config /tmp/chummer-package-feed.NuGet.Config",
            "COPY --from=run-services-source Chummer.Run.Api/Chummer.Run.Api.csproj chummer.run-services/Chummer.Run.Api/",
            "COPY --from=run-services-source Chummer.Run.Api/packages.lock.json chummer.run-services/Chummer.Run.Api/",
            "COPY --from=run-services-source Chummer.InstallLinking.Postgres.Tool/Chummer.InstallLinking.Postgres.Tool.csproj chummer.run-services/Chummer.InstallLinking.Postgres.Tool/",
            "COPY --from=run-services-source Chummer.Run.LoopbackProbe/Chummer.Run.LoopbackProbe.csproj chummer.run-services/Chummer.Run.LoopbackProbe/",
            "COPY --from=run-services-source Chummer.Run.LoopbackProbe/packages.lock.json chummer.run-services/Chummer.Run.LoopbackProbe/",
            "COPY --from=run-services-source Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj chummer.run-services/Chummer.Campaign.Contracts/",
            "COPY --from=run-services-source Chummer.Campaign.Contracts/packages.lock.json chummer.run-services/Chummer.Campaign.Contracts/",
            "COPY --from=run-services-source Chummer.Control.Contracts/Chummer.Control.Contracts.csproj chummer.run-services/Chummer.Control.Contracts/",
            "COPY --from=run-services-source Chummer.Control.Contracts/packages.lock.json chummer.run-services/Chummer.Control.Contracts/",
            "COPY --from=run-services-source Chummer.Run.Contracts/Chummer.Run.Contracts.csproj chummer.run-services/Chummer.Run.Contracts/",
            "COPY --from=run-services-source Chummer.Run.Contracts/packages.lock.json chummer.run-services/Chummer.Run.Contracts/",
            "COPY --from=run-services-source Chummer.Play.Contracts/Chummer.Play.Contracts.csproj chummer.run-services/Chummer.Play.Contracts/",
            "COPY --from=run-services-source Chummer.Play.Contracts/packages.lock.json chummer.run-services/Chummer.Play.Contracts/",
            "COPY --from=run-services-source Chummer.World.Contracts/Chummer.World.Contracts.csproj chummer.run-services/Chummer.World.Contracts/",
            "COPY --from=run-services-source Chummer.World.Contracts/packages.lock.json chummer.run-services/Chummer.World.Contracts/",
            "COPY --from=run-services-source Chummer.Run.Api/ chummer.run-services/Chummer.Run.Api/",
            "COPY --from=run-services-source Chummer.InstallLinking.Postgres.Tool/ chummer.run-services/Chummer.InstallLinking.Postgres.Tool/",
            "COPY --from=run-services-source Chummer.Run.LoopbackProbe/ chummer.run-services/Chummer.Run.LoopbackProbe/",
            "COPY --from=run-services-source Chummer.Campaign.Contracts/ chummer.run-services/Chummer.Campaign.Contracts/",
            "COPY --from=run-services-source Chummer.Control.Contracts/ chummer.run-services/Chummer.Control.Contracts/",
            "COPY --from=run-services-source Chummer.Run.Contracts/ chummer.run-services/Chummer.Run.Contracts/",
            "COPY --from=run-services-source .codex-design/ chummer.run-services/.codex-design/",
            "COPY --from=run-services-source Chummer.Play.Contracts/ chummer.run-services/Chummer.Play.Contracts/",
            "COPY --from=run-services-source Chummer.World.Contracts/ chummer.run-services/Chummer.World.Contracts/",
            "COPY --from=hub-registry-source black-ledger/ chummer-hub-registry/black-ledger/",
            "COPY --from=fleet-media-factory-contracts . fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/",
        }
    ),
    "install-linking-postgres-tool-final": frozenset(),
    "final": frozenset(
        {
            "COPY --from=run-services-source --chmod=0555 scripts/initialize-public-edge-volumes.sh /usr/local/libexec/chummer/initialize-public-edge-volumes.sh",
            "COPY --from=design-product products/chummer/ /app/.codex-design/product/",
        }
    ),
}

_DOCKER_MOUNT_OPTION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])--mount(?:(?:=|\s)|$)",
    flags=re.IGNORECASE,
)
_DOCKER_PARSER_DIRECTIVE_PATTERN = re.compile(
    r"\s*#\s*(?:syntax|escape|check)\s*=.*",
    flags=re.IGNORECASE,
)
_PLAIN_COMPOSE_KEY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")


def docker_instruction_uses_mount(instruction: str) -> bool:
    """Return true for every Dockerfile --mount option spelling."""

    return _DOCKER_MOUNT_OPTION_PATTERN.search(instruction) is not None


def dockerfile_parser_directive_findings(
    text: str,
    *,
    expected_syntax_directive: str,
) -> tuple[bool, tuple[int, ...]]:
    """Require one exact first-line syntax directive and no later directives."""

    lines = text.splitlines()
    exact_syntax = bool(lines) and lines[0] == expected_syntax_directive
    late_directive_lines = tuple(
        line_number
        for line_number, line in enumerate(lines[1:], start=2)
        if _DOCKER_PARSER_DIRECTIVE_PATTERN.fullmatch(line)
    )
    return exact_syntax, late_directive_lines


def docker_logical_instruction_records(
    text: str,
    *,
    first_line_number: int = 1,
) -> tuple[tuple[tuple[int, str, bool], ...], tuple[int, ...]]:
    """Return exact logical instructions and malformed continuation origins."""

    records: list[tuple[int, str, bool]] = []
    malformed_continuations: list[int] = []
    pending_parts: list[str] = []
    pending_line_number = 0
    used_continuation = False
    for line_number, raw_line in enumerate(
        text.splitlines(),
        start=first_line_number,
    ):
        stripped = raw_line.strip()
        if not pending_parts and (not stripped or stripped.startswith("#")):
            continue
        if pending_parts and (not stripped or stripped.startswith("#")):
            malformed_continuations.append(pending_line_number)
            pending_parts = []
            pending_line_number = 0
            used_continuation = False
            continue
        continued = raw_line.rstrip().endswith("\\")
        segment = raw_line.rstrip()
        if continued:
            segment = segment[:-1]
        if not pending_parts:
            pending_line_number = line_number
        pending_parts.append(segment)
        if continued:
            used_continuation = True
            continue
        records.append(
            (
                pending_line_number,
                "".join(pending_parts).strip(),
                used_continuation,
            )
        )
        pending_parts = []
        pending_line_number = 0
        used_continuation = False
    if pending_parts:
        malformed_continuations.append(pending_line_number)
    return tuple(records), tuple(malformed_continuations)


def docker_logical_instructions(text: str) -> tuple[str, ...]:
    """Return logical instructions only when continuation syntax is complete."""

    records, malformed_continuations = docker_logical_instruction_records(text)
    if malformed_continuations:
        raise ValueError("Dockerfile has a malformed or dangling continuation")
    return tuple(instruction for _line, instruction, _continued in records)


def docker_stage_instruction_contract_matches(
    text: str,
    *,
    stage: str,
    expected_count: int,
    expected_sha256: str,
) -> bool:
    """Bind every instruction in one exact Docker stage, including later RUNs."""

    try:
        instructions = docker_logical_instructions(text)
    except ValueError:
        return False
    from_indexes = [
        index
        for index, instruction in enumerate(instructions)
        if re.fullmatch(
            rf"FROM\s+\S+\s+AS\s+{re.escape(stage)}",
            instruction,
            flags=re.IGNORECASE,
        )
    ]
    if len(from_indexes) != 1:
        return False
    start = from_indexes[0]
    end = next(
        (
            index
            for index in range(start + 1, len(instructions))
            if re.match(
                r"FROM(?:\s|$)", instructions[index], flags=re.IGNORECASE
            )
        ),
        len(instructions),
    )
    stage_instructions = instructions[start:end]
    digest = hashlib.sha256(
        ("\n".join(stage_instructions) + "\n").encode("utf-8")
    ).hexdigest()
    return (
        len(stage_instructions) == expected_count
        and digest == expected_sha256
    )


def docker_copy_from_reference(
    instruction: str,
) -> tuple[str | None, bool]:
    """Extract one literal COPY/ADD --from reference."""

    match = re.match(
        r"(?:COPY|ADD)\s+(.+)",
        instruction,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None, False
    tokens = match.group(1).split()
    from_references: list[str] = []
    option_count = 0
    for token in tokens:
        if not token.startswith("--"):
            break
        option_count += 1
        lower_token = token.lower()
        if lower_token.startswith("--from="):
            reference = token.split("=", 1)[1]
            if not reference:
                return None, True
            from_references.append(reference)
        elif lower_token == "--from":
            return None, True
    positional_tokens = tokens[option_count:]
    if any("--from" in token.lower() for token in positional_tokens):
        return None, True
    if len(from_references) > 1:
        return None, True
    return (from_references[0] if from_references else None), False


def docker_context_policy_findings(
    records: Sequence[tuple[int, str, bool]],
) -> dict[str, Any]:
    """Classify every context-selecting Docker logical instruction."""

    context_pattern = re.compile(
        r"(?<![A-Za-z0-9_.-])(?:"
        + "|".join(
            re.escape(name)
            for name in PUBLIC_EDGE_NAMED_CONTEXT_NAMES
        )
        + r")(?![A-Za-z0-9_.-])",
        flags=re.IGNORECASE,
    )
    noncopy_from_pattern = re.compile(
        r"--from(?:=|\s+)",
        flags=re.IGNORECASE,
    )
    current_stage = ""
    reviewed_copies_by_stage: dict[str, list[str]] = {}
    findings: dict[str, list[int]] = {
        "continuationUses": [],
        "forbiddenContextUses": [],
        "heredocUses": [],
        "invalidCopyFromUses": [],
        "invalidStageCopyFromUses": [],
        "mountFromUses": [],
        "noncopyFromUses": [],
        "onbuildUses": [],
    }
    seen_stage_aliases: set[str] = set()
    for line_number, instruction, used_continuation in records:
        is_copy_or_add = bool(
            re.match(
                r"(?:COPY|ADD)(?:\s|$)",
                instruction,
                flags=re.IGNORECASE,
            )
        )
        is_onbuild = bool(
            re.match(
                r"ONBUILD(?:\s|$)",
                instruction,
                flags=re.IGNORECASE,
            )
        )
        named_contexts = {
            match.group(0).lower()
            for match in context_pattern.finditer(instruction)
        }
        expected_stage_copies = (
            PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE.get(
                current_stage,
                frozenset(),
            )
        )
        uses_mount = docker_instruction_uses_mount(instruction)
        is_reviewed_copy = (
            is_copy_or_add
            and instruction in expected_stage_copies
        )
        if is_onbuild:
            findings["onbuildUses"].append(line_number)
        if named_contexts:
            if is_reviewed_copy:
                reviewed_copies_by_stage.setdefault(
                    current_stage,
                    [],
                ).append(instruction)
            else:
                findings["forbiddenContextUses"].append(line_number)
        if (
            used_continuation
            and (
                named_contexts
                or noncopy_from_pattern.search(instruction)
                or uses_mount
            )
        ):
            findings["continuationUses"].append(line_number)
        if uses_mount:
            findings["mountFromUses"].append(line_number)
        if (
            not is_copy_or_add
            and noncopy_from_pattern.search(instruction)
        ):
            findings["noncopyFromUses"].append(line_number)
        if is_copy_or_add:
            copy_from, malformed_copy_from = docker_copy_from_reference(
                instruction
            )
            if malformed_copy_from:
                findings["invalidCopyFromUses"].append(line_number)
            elif copy_from is not None:
                normalized_copy_from = copy_from.lower()
                invalid_reference = (
                    re.fullmatch(
                        r"[A-Za-z0-9_.-]+",
                        copy_from,
                    )
                    is None
                )
                if normalized_copy_from in PUBLIC_EDGE_NAMED_CONTEXT_NAMES:
                    invalid_reference = (
                        invalid_reference or not is_reviewed_copy
                    )
                else:
                    invalid_stage_reference = (
                        normalized_copy_from not in seen_stage_aliases
                        or normalized_copy_from == current_stage
                        or normalized_copy_from
                        not in PUBLIC_EDGE_DOCKER_COPY_STAGE_REFERENCES_BY_STAGE.get(
                            current_stage,
                            frozenset(),
                        )
                    )
                    if invalid_stage_reference:
                        findings["invalidStageCopyFromUses"].append(
                            line_number
                        )
                    invalid_reference = (
                        invalid_reference or invalid_stage_reference
                    )
                if invalid_reference:
                    findings["invalidCopyFromUses"].append(line_number)
        if "<<" in instruction:
            findings["heredocUses"].append(line_number)
        from_match = re.fullmatch(
            r"FROM\s+\S+(?:\s+AS\s+([A-Za-z0-9_.-]+))?",
            instruction,
            flags=re.IGNORECASE,
        )
        if from_match is not None:
            current_stage = (from_match.group(1) or "").lower()
            if current_stage:
                seen_stage_aliases.add(current_stage)

    exact_reviewed_copy_set = True
    for stage, expected in (
        PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE.items()
    ):
        actual = reviewed_copies_by_stage.get(stage, [])
        if set(actual) != set(expected) or len(actual) != len(expected):
            exact_reviewed_copy_set = False
            break
    return {
        **findings,
        "exactReviewedCopySet": exact_reviewed_copy_set,
        "reviewedCopiesByStage": reviewed_copies_by_stage,
    }


def _indentation(raw_line: str) -> int:
    return len(raw_line) - len(raw_line.lstrip(" "))


def _mapping_entry(
    raw_line: str,
    *,
    indent: int,
) -> tuple[str, str, bool] | None:
    if _indentation(raw_line) != indent or "\t" in raw_line[:indent]:
        return None
    if raw_line[indent : indent + 1] in {" ", "\t"}:
        return None
    text = raw_line[indent:].rstrip()
    if not text or text.startswith(("#", "-", "?", ":")):
        return None
    if text[0] in {"'", '"'}:
        quote = text[0]
        escaped = False
        closing_index = -1
        for index, character in enumerate(text[1:], start=1):
            if quote == '"' and character == "\\" and not escaped:
                escaped = True
                continue
            if character == quote and not escaped:
                closing_index = index
                break
            escaped = False
        if closing_index < 0:
            return None
        key_token = text[: closing_index + 1]
        remainder = text[closing_index + 1 :]
        if not remainder.startswith(":"):
            return None
        try:
            key = ast.literal_eval(key_token)
        except (SyntaxError, ValueError):
            return None
        if not isinstance(key, str):
            return None
        raw_value = remainder[1:].strip()
        return key, raw_value, False

    if ":" not in text:
        return None
    raw_key, remainder = text.split(":", 1)
    if raw_key != raw_key.strip():
        return None
    key = raw_key
    if (
        _PLAIN_COMPOSE_KEY_PATTERN.fullmatch(key) is None
        or (remainder and remainder[0] != " ")
    ):
        return None
    return key, remainder.strip(), True


def _uses_yaml_indirection(value: str) -> bool:
    return value.startswith(("&", "*", "!"))


def _unique_failures(failures: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(failures))


def public_edge_compose_build_syntax_failures(
    text: str,
    *,
    service_name: str | None = None,
) -> list[str]:
    """Validate raw Compose syntax before YAML can normalize alternate forms."""

    if service_name is not None and service_name not in PUBLIC_EDGE_BUILD_SERVICE_TARGETS:
        return [f"unknown governed Compose build service: {service_name}"]

    lines = text.splitlines()
    global_failures: list[str] = []
    service_failures = {
        name: [] for name in PUBLIC_EDGE_BUILD_SERVICE_TARGETS
    }

    top_level_entries: dict[str, list[tuple[int, str, bool]]] = {}
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _indentation(raw_line) != 0:
            continue
        entry = _mapping_entry(raw_line, indent=0)
        if entry is None:
            global_failures.append(
                "Compose contains an unparsed top-level token at "
                f"line {index + 1}"
            )
            continue
        key, value, plain_key = entry
        top_level_entries.setdefault(key, []).append(
            (index, value, plain_key)
        )
        if not plain_key:
            global_failures.append(
                f"Compose top-level key must be an unquoted literal: {key}"
            )
        if key == "name":
            if (
                value != PUBLIC_EDGE_COMPOSE_PROJECT_NAME
                or _uses_yaml_indirection(value)
            ):
                global_failures.append(
                    "Compose top-level name must use the exact canonical "
                    f"literal: {PUBLIC_EDGE_COMPOSE_PROJECT_NAME}"
                )
        elif value or _uses_yaml_indirection(value):
            global_failures.append(
                f"Compose top-level key must use a direct mapping: {key}"
            )

    for key, entries in top_level_entries.items():
        if len(entries) > 1:
            global_failures.append(
                f"Compose top-level key is duplicated semantically: {key}"
            )
    actual_top_level_keys = set(top_level_entries)
    if actual_top_level_keys != set(PUBLIC_EDGE_COMPOSE_TOP_LEVEL_KEYS):
        global_failures.append(
            "Compose top-level keys drifted from the closed allowlist"
        )
    if "include" in actual_top_level_keys:
        global_failures.append(
            "Compose include and external semantic composition are forbidden"
        )

    top_level_services = top_level_entries.get("services", [])
    if len(top_level_services) != 1:
        global_failures.append(
            "Compose must declare one exact plain services mapping"
        )
        services_start = -1
    else:
        services_start, services_value, services_plain_key = top_level_services[0]
        if not services_plain_key or services_value:
            global_failures.append(
                "Compose services must use the exact plain mapping form"
            )

    if services_start < 0:
        selected = (
            PUBLIC_EDGE_BUILD_SERVICE_TARGETS
            if service_name is None
            else (service_name,)
        )
        failures = list(global_failures)
        failures.extend(
            f"Compose must declare {name} exactly once" for name in selected
        )
        return _unique_failures(failures)

    services_end = len(lines)
    for index in range(services_start + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _indentation(lines[index]) == 0:
            services_end = index
            break

    declarations: dict[str, list[int]] = {}
    declaration_indexes: list[int] = []
    declaration_names_by_index: dict[int, str] = {}
    for index in range(services_start + 1, services_end):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indentation = _indentation(raw_line)
        if indentation > 2:
            continue
        if indentation != 2:
            global_failures.append(
                f"Compose services mapping contains an invalid token at line {index + 1}"
            )
            continue
        entry = _mapping_entry(raw_line, indent=2)
        if entry is None:
            global_failures.append(
                f"Compose services mapping contains a non-literal token at line {index + 1}"
            )
            continue
        key, value, plain_key = entry
        declaration_indexes.append(index)
        declaration_names_by_index[index] = key
        declarations.setdefault(key, []).append(index)
        target_failures = service_failures.get(key, global_failures)
        if not plain_key:
            target_failures.append(
                f"Compose service {key} must use an unquoted literal key"
            )
        if value or _uses_yaml_indirection(value):
            target_failures.append(
                f"Compose service {key} must use a direct mapping without YAML indirection"
            )

    for name, indexes in declarations.items():
        if len(indexes) > 1:
            service_failures.get(name, global_failures).append(
                f"Compose service key is duplicated semantically: {name}"
            )

    sorted_declaration_indexes = sorted(declaration_indexes)
    raw_build_service_names: set[str] = set()
    for declaration_offset, service_start in enumerate(
        sorted_declaration_indexes
    ):
        declared_service_name = declaration_names_by_index[service_start]
        service_end = (
            sorted_declaration_indexes[declaration_offset + 1]
            if declaration_offset + 1 < len(sorted_declaration_indexes)
            else services_end
        )
        for index in range(service_start + 1, service_end):
            raw_line = lines[index]
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indentation = _indentation(raw_line)
            if indentation > 4:
                continue
            if indentation != 4:
                global_failures.append(
                    f"Compose service {declared_service_name} contains "
                    f"an invalid direct token at line {index + 1}"
                )
                continue
            entry = _mapping_entry(raw_line, indent=4)
            if entry is None:
                global_failures.append(
                    f"Compose service {declared_service_name} contains "
                    f"an unparsed direct token at line {index + 1}"
                )
                continue
            key, _value, plain_key = entry
            if key == "build":
                raw_build_service_names.add(declared_service_name)
                if not plain_key:
                    global_failures.append(
                        f"Compose service {declared_service_name} build "
                        "must use an unquoted literal key"
                    )
    if raw_build_service_names != set(
        PUBLIC_EDGE_RENDERED_BUILD_SERVICE_NAMES
    ):
        global_failures.append(
            "Compose raw build-bearing service set drifted from "
            "the closed allowlist"
        )

    for governed_name in PUBLIC_EDGE_BUILD_SERVICE_TARGETS:
        indexes = declarations.get(governed_name, [])
        failures = service_failures[governed_name]
        if len(indexes) != 1:
            failures.append(
                f"Compose must declare {governed_name} exactly once"
            )
        if not indexes:
            continue
        service_start = indexes[0]
        service_end = services_end
        for candidate in sorted_declaration_indexes:
            if candidate > service_start:
                service_end = candidate
                break

        service_entries: dict[str, list[tuple[int, str]]] = {}
        for index in range(service_start + 1, service_end):
            raw_line = lines[index]
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indentation = _indentation(raw_line)
            if indentation > 4:
                continue
            if indentation != 4:
                failures.append(
                    f"Compose {governed_name} contains an invalid service token "
                    f"at line {index + 1}"
                )
                continue
            entry = _mapping_entry(raw_line, indent=4)
            if entry is None:
                failures.append(
                    f"Compose {governed_name} contains a non-literal service token "
                    f"at line {index + 1}"
                )
                continue
            key, value, plain_key = entry
            service_entries.setdefault(key, []).append((index, value))
            if not plain_key:
                failures.append(
                    f"Compose {governed_name} service keys must be unquoted literals"
                )
            if _uses_yaml_indirection(value):
                failures.append(
                    f"Compose {governed_name} service mapping forbids YAML indirection"
                )

        for key, entries in service_entries.items():
            if len(entries) > 1:
                failures.append(
                    f"Compose {governed_name} service key is duplicated semantically: {key}"
                )
        actual_service_keys = set(service_entries)
        expected_service_keys = set(
            PUBLIC_EDGE_RAW_SERVICE_KEYS_BY_SERVICE[governed_name]
        )
        if (
            actual_service_keys != expected_service_keys
            or any(
                len(entries) != 1
                for entries in service_entries.values()
            )
        ):
            failures.append(
                f"Compose {governed_name} service keys drifted from "
                "the closed allowlist"
            )

        image_entries = service_entries.get("image", [])
        if (
            len(image_entries) != 1
            or image_entries[0][1]
            != PUBLIC_EDGE_RAW_SERVICE_IMAGES[governed_name]
        ):
            failures.append(
                f"Compose {governed_name} image drifted from the "
                "canonical build identity"
            )
        expected_profiles = PUBLIC_EDGE_SERVICE_PROFILES_BY_SERVICE[
            governed_name
        ]
        profile_entries = service_entries.get("profiles", [])
        if expected_profiles:
            expected_profile_value = (
                '["' + '", "'.join(expected_profiles) + '"]'
            )
            if (
                len(profile_entries) != 1
                or profile_entries[0][1] != expected_profile_value
            ):
                failures.append(
                    f"Compose {governed_name} profiles drifted from "
                    "the canonical build selectors"
                )
        elif profile_entries:
            failures.append(
                f"Compose {governed_name} must not declare profiles"
            )

        build_entries = service_entries.get("build", [])
        if len(build_entries) != 1:
            failures.append(
                f"Compose {governed_name} must declare build exactly once"
            )
        if not build_entries:
            continue
        build_start, build_value = build_entries[0]
        if build_value:
            failures.append(
                f"Compose {governed_name} build must use a direct mapping"
            )
        build_end = service_end
        for entries in service_entries.values():
            for candidate, _value in entries:
                if build_start < candidate < build_end:
                    build_end = candidate

        direct_build_entries: dict[str, list[tuple[int, str]]] = {}
        for index in range(build_start + 1, build_end):
            raw_line = lines[index]
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indentation = _indentation(raw_line)
            if indentation > 6:
                continue
            if indentation != 6:
                failures.append(
                    f"Compose {governed_name} build contains an invalid token "
                    f"at line {index + 1}"
                )
                continue
            entry = _mapping_entry(raw_line, indent=6)
            if entry is None:
                failures.append(
                    f"Compose {governed_name} build contains a non-literal token "
                    f"at line {index + 1}"
                )
                continue
            key, value, plain_key = entry
            direct_build_entries.setdefault(key, []).append((index, value))
            if not plain_key:
                failures.append(
                    f"Compose {governed_name} build keys must be unquoted literals"
                )
            if _uses_yaml_indirection(value):
                failures.append(
                    f"Compose {governed_name} build forbids YAML indirection"
                )

        for key, entries in direct_build_entries.items():
            if len(entries) > 1:
                failures.append(
                    f"Compose {governed_name} build key is duplicated semantically: {key}"
                )
        actual_build_keys = set(direct_build_entries)
        expected_build_keys = set(
            PUBLIC_EDGE_BUILD_KEYS_BY_SERVICE[governed_name]
        )
        if (
            actual_build_keys != expected_build_keys
            or any(
                len(entries) != 1
                for entries in direct_build_entries.values()
            )
        ):
            failures.append(
                f"Compose {governed_name} build keys drifted from the closed allowlist"
            )

        nested_expectations = {
            "additional_contexts": set(PUBLIC_EDGE_NAMED_CONTEXT_NAMES),
            "args": set(PUBLIC_EDGE_BUILD_ARG_NAMES),
        }
        allowed_nested_token_indexes: set[int] = set()
        direct_indexes = sorted(
            index
            for entries in direct_build_entries.values()
            for index, _value in entries
        )
        for nested_key, expected_names in nested_expectations.items():
            entries = direct_build_entries.get(nested_key, [])
            if len(entries) != 1:
                failures.append(
                    f"Compose {governed_name} {nested_key} must be one direct mapping"
                )
                continue
            nested_start, nested_value = entries[0]
            if nested_value:
                failures.append(
                    f"Compose {governed_name} {nested_key} must be one direct mapping"
                )
                continue
            nested_end = build_end
            for candidate in direct_indexes:
                if candidate > nested_start:
                    nested_end = candidate
                    break
            nested_entries: dict[str, list[str]] = {}
            for index in range(nested_start + 1, nested_end):
                raw_line = lines[index]
                stripped = raw_line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                allowed_nested_token_indexes.add(index)
                if _indentation(raw_line) != 8:
                    failures.append(
                        f"Compose {governed_name} {nested_key} contains an invalid "
                        f"token at line {index + 1}"
                    )
                    continue
                entry = _mapping_entry(raw_line, indent=8)
                if entry is None:
                    failures.append(
                        f"Compose {governed_name} {nested_key} contains a non-literal "
                        f"token at line {index + 1}"
                    )
                    continue
                key, value, plain_key = entry
                nested_entries.setdefault(key, []).append(value)
                if not plain_key:
                    failures.append(
                        f"Compose {governed_name} {nested_key} keys must be "
                        "unquoted literals"
                    )
                if _uses_yaml_indirection(value):
                    failures.append(
                        f"Compose {governed_name} {nested_key} forbids YAML indirection"
                    )
            if (
                set(nested_entries) != expected_names
                or any(len(values) != 1 for values in nested_entries.values())
            ):
                failures.append(
                    f"Compose {governed_name} {nested_key} keys drifted from "
                    "the closed allowlist"
                )

        for index in range(build_start + 1, build_end):
            raw_line = lines[index]
            stripped = raw_line.strip()
            if (
                not stripped
                or stripped.startswith("#")
                or _indentation(raw_line) <= 6
                or index in allowed_nested_token_indexes
            ):
                continue
            failures.append(
                f"Compose {governed_name} build contains an unbound nested token "
                f"at line {index + 1}"
            )

    selected_names = (
        tuple(PUBLIC_EDGE_BUILD_SERVICE_TARGETS)
        if service_name is None
        else (service_name,)
    )
    selected_failures = list(global_failures)
    for name in selected_names:
        selected_failures.extend(service_failures[name])
    return _unique_failures(selected_failures)


def rendered_build_contract_matches(
    build: Any,
    *,
    service_name: str,
    build_context: str,
    dockerfile: str,
    additional_contexts: Mapping[str, str],
) -> bool:
    """Match one governed rendered build mapping exactly."""

    if not isinstance(build, dict):
        return False
    expected_build_keys = PUBLIC_EDGE_BUILD_KEYS_BY_SERVICE.get(service_name)
    if expected_build_keys is None:
        return False
    target = PUBLIC_EDGE_BUILD_SERVICE_TARGETS[service_name]
    expected_target = target or None
    build_args = build.get("args")
    if (
        set(build) != expected_build_keys
        or not isinstance(build_args, dict)
        or set(build_args) != set(PUBLIC_EDGE_BUILD_ARG_NAMES)
        or build_args.get("CHUMMER_BUILD_CONCURRENCY") != "1"
        or not isinstance(
            build_args.get("CHUMMER_RUNTIME_UID"),
            str,
        )
        or re.fullmatch(
            r"[1-9][0-9]{0,9}",
            build_args["CHUMMER_RUNTIME_UID"],
        )
        is None
        or not isinstance(
            build_args.get("CHUMMER_RUNTIME_GID"),
            str,
        )
        or re.fullmatch(
            r"[1-9][0-9]{0,9}",
            build_args["CHUMMER_RUNTIME_GID"],
        )
        is None
    ):
        return False
    return (
        build.get("context") == build_context
        and build.get("dockerfile") == dockerfile
        and build.get("additional_contexts") == dict(additional_contexts)
        and build.get("target") == expected_target
    )


def public_edge_rendered_compose_failures(
    payload: Any,
    *,
    expected_images: Mapping[str, str],
    build_context: str,
    dockerfile: str,
    additional_contexts: Mapping[str, str],
    transient_service_keys: Mapping[str, Iterable[str]] | None = None,
) -> list[str]:
    """Validate the effective rendered build authority exactly."""

    if not isinstance(payload, dict):
        return ["rendered Compose payload must be one mapping"]
    services = payload.get("services")
    if not isinstance(services, dict):
        return ["rendered Compose payload must contain one services mapping"]

    failures: list[str] = []
    build_service_names = {
        name
        for name, service in services.items()
        if isinstance(service, dict) and "build" in service
    }
    if build_service_names != set(PUBLIC_EDGE_RENDERED_BUILD_SERVICE_NAMES):
        failures.append(
            "rendered Compose build-bearing service set drifted from "
            "the closed allowlist"
        )

    transient_keys = transient_service_keys or {}
    if set(transient_keys) - set(PUBLIC_EDGE_BUILD_SERVICE_TARGETS):
        failures.append(
            "rendered Compose transient service-key authority named "
            "an unknown governed service"
        )
    if set(expected_images) != set(PUBLIC_EDGE_BUILD_SERVICE_TARGETS):
        failures.append(
            "rendered Compose expected image authority is incomplete"
        )
        return _unique_failures(failures)

    for service_name in PUBLIC_EDGE_BUILD_SERVICE_TARGETS:
        service = services.get(service_name)
        if not isinstance(service, dict):
            failures.append(
                f"rendered Compose omitted governed service {service_name}"
            )
            continue
        expected_keys = set(
            PUBLIC_EDGE_RENDERED_SERVICE_KEYS_BY_SERVICE[service_name]
        )
        expected_keys.update(transient_keys.get(service_name, ()))
        if set(service) != expected_keys:
            failures.append(
                f"rendered Compose {service_name} service keys drifted "
                "from the closed allowlist"
            )
        expected_profiles = PUBLIC_EDGE_SERVICE_PROFILES_BY_SERVICE[
            service_name
        ]
        if expected_profiles:
            profiles = service.get("profiles")
            if (
                not isinstance(profiles, list)
                or tuple(profiles) != expected_profiles
            ):
                failures.append(
                    f"rendered Compose {service_name} profiles drifted"
                )
        elif "profiles" in service:
            failures.append(
                f"rendered Compose {service_name} must not declare profiles"
            )
        if service.get("image") != expected_images[service_name]:
            failures.append(
                f"rendered Compose {service_name} image drifted"
            )
        if not rendered_build_contract_matches(
            service.get("build"),
            service_name=service_name,
            build_context=build_context,
            dockerfile=dockerfile,
            additional_contexts=additional_contexts,
        ):
            failures.append(
                f"rendered Compose {service_name} build mapping drifted"
            )
    return _unique_failures(failures)
