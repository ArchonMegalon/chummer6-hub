#!/usr/bin/env python3
"""Validate retained attestation-v1 inputs; never recover container credentials.

The two stdout hashes are ephemeral in-process drift fences, not receipts or
historical evidence. Historical authority comes from the operator-pinned prior
attestation and its immutable Git source objects. Run with Python isolated mode.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

import yaml


PROJECT = "chummer-build-ghost-private-nonprod"
SERVICES = {"presentation": "chummer-build-ghost-presentation",
            "ai": "chummer-build-ghost-ai", "edge": "build-ghost-private-edge"}
IMAGES = {"presentation": "chummer-build-ghost-presentation:private-nonprod",
          "ai": "chummer-build-ghost-ai:private-nonprod", "edge": "caddy:2.10.2-alpine"}
COMPOSE = "docker-compose.build-ghost-private-nonprod.yml"
CADDY = "ops/build-ghost-private-nonprod/Caddyfile"
CONTRACT = "ops/build-ghost-private-nonprod/tough-tongue-read-only-binding-contract.unconfigured.json"
SECRET = "build-ghost-tough-tongue-read-only-binding-contract"
HEX = re.compile(r"[0-9a-f]{64}\Z")
LABEL = "com.docker.compose."


def require(condition):
    if not condition:
        raise ValueError("prior authority unavailable or changed")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def parse_json(data):
    return json.loads(data, object_pairs_hook=unique_pairs)


def owned_path(value, directory=False):
    path = Path(value)
    require(path.is_absolute() and str(path) == value and ".." not in path.parts)
    for part in [*reversed(path.parents), path]:
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode))
    info = path.stat()
    require(info.st_uid == os.getuid() and not info.st_mode & 0o022)
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
    return path


def stable_bytes(path):
    owned_path(str(path))
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 2 * 1024 * 1024)
        data = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
        require(len(data) == before.st_size)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns))
        require(path.stat() == after)
    return data


def command(args, env=None):
    # Do not propagate Compose's diagnostics: interpolation errors may contain
    # operator values. Only the allowlisted, nonsecret outputs below are used.
    limit = 2 * 1024 * 1024
    output = bytearray()
    counts = {"stdout": 0, "stderr": 0}
    with subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          start_new_session=True) as process:
        deadline = time.monotonic() + 30
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, "stdout")
                selector.register(process.stderr, selectors.EVENT_READ, "stderr")
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    require(remaining > 0)
                    for key, _ in selector.select(remaining):
                        chunk = os.read(key.fd, min(65536, limit - counts[key.data] + 1))
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        counts[key.data] += len(chunk)
                        require(counts[key.data] <= limit)
                        if key.data == "stdout":
                            output.extend(chunk)
                        # stderr is counted and discarded, never retained/logged.
                require(process.wait(timeout=max(0.001, deadline - time.monotonic())) == 0)
        finally:
            # Kill the entire command group on failure, including a Compose
            # plugin child retaining a pipe after the Docker parent exits.
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
    return bytes(output)


def file_binding(binding, path, data, with_path=False):
    require(isinstance(binding, dict) and type(binding.get("sizeBytes")) is int)
    require(binding["sizeBytes"] == len(data) and binding.get("sha256") == "sha256:" + digest(data))
    if with_path:
        require(binding.get("pathSha256") == "sha256:" + digest(str(path).encode()))
        require(binding.get("matchesAttesterSource") is True)


class ClosedLoader(yaml.SafeLoader):
    pass


def yaml_mapping(loader, node):
    return unique_pairs(loader.construct_pairs(node, deep=True))


ClosedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, yaml_mapping)


def validate_recipe(data, root):
    # Reject additional input files BEFORE Compose can evaluate any env_file,
    # include, extends, config, or secret. No home-grown YAML interpretation.
    for token in yaml.scan(data):
        require(not isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken, yaml.tokens.TagToken)))
    model = yaml.load(data, Loader=ClosedLoader)
    require(isinstance(model, dict) and set(model) <= {"name", "services", "volumes", "networks", "secrets"})
    require(model.get("name") == PROJECT and isinstance(model.get("services"), dict))
    require(set(SERVICES.values()) <= set(model["services"]) <= set(SERVICES.values()) | {
        "build-ghost-private-trust-export", "build-ghost-live-support-store-init", "build-ghost-cloudflare-access-edge"})
    allowed = {"image", "build", "restart", "environment", "volumes", "healthcheck", "networks", "depends_on",
               "secrets", "ports", "entrypoint", "command", "network_mode", "user", "read_only", "cap_drop",
               "cap_add", "security_opt", "profiles"}
    for name, service in model["services"].items():
        require(isinstance(service, dict) and set(service) <= allowed)
        # No other host files may enter rollback through bind mounts.
        for mount in service.get("volumes", []):
            require(isinstance(mount, str))
            pieces = mount.split(":")
            require(len(pieces) in (2, 3))
            source = pieces[0]
            if "/" in source or "$" in source or source.startswith("."):
                require(name == SERVICES["edge"] and mount == "./" + CADDY + ":/etc/caddy/Caddyfile:ro")
        for secret in service.get("secrets", []):
            require(name == SERVICES["ai"] and isinstance(secret, dict)
                    and set(secret) <= {"source", "target", "mode"}
                    and secret.get("source") == SECRET
                    and secret.get("target") == "tough-tongue-read-only-binding-contract.json")
    for role, name in SERVICES.items():
        require(model["services"][name].get("image") == IMAGES[role])
    secrets = model.get("secrets", {})
    require(isinstance(secrets, dict) and set(secrets) <= {SECRET})
    if secrets:
        require(secrets[SECRET] == {"file": "${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE:-./" + CONTRACT + "}"})
    # Named volumes only: driver_opts can hide a host-file bind.
    for volume in (model.get("volumes") or {}).values():
        require(volume is None or volume == {})
    return model


def inspect(container, field):
    return command(["docker", "inspect", container, "--format", field]).decode().strip()


def validate(mode, expected_inputs, expected_runtime):
    receipt_path = owned_path(os.environ["CHUMMER_BUILD_GHOST_ROLLBACK_ATTESTATION_FILE"])
    pin = os.environ["CHUMMER_BUILD_GHOST_ROLLBACK_ATTESTATION_SHA256"]
    require(HEX.fullmatch(pin))
    receipt_bytes = stable_bytes(receipt_path)
    require(digest(receipt_bytes) == pin)
    receipt = parse_json(receipt_bytes)
    require(receipt.get("schema") == "chummer.build_ghost.private_nonprod_deployment_attestation.v1")
    require(receipt.get("project") == PROJECT and receipt.get("runtime", {}).get("project") == PROJECT)
    require(receipt.get("evidenceDigestContract") == "sha256-canonical-json-without-evidenceDigest")
    require(receipt.get("evidenceDigest") == "sha256:" + digest(canonical({k: v for k, v in receipt.items() if k != "evidenceDigest"})))
    require(receipt.get("status") == "deployed-private-nonprod" and receipt.get("claim") == "deployed-private-nonprod")
    require(receipt.get("blockers") == [] and receipt.get("runtimeStableDuringAttestation") is True)
    require(receipt.get("providerActivationAuthorized") is False and receipt.get("externalMutationPerformed") is False)
    runtime = receipt["runtime"]
    require(runtime.get("providerGates", {}).get("allLiteralFalse") is True)
    require(runtime.get("confinement", {}).get("loopbackOnly") is True)
    rows = runtime["containers"]
    require(set(rows) == set(SERVICES))
    root = owned_path(os.environ["CHUMMER_BUILD_GHOST_ROLLBACK_PROJECT_DIRECTORY"], directory=True)
    recipe = owned_path(os.environ["CHUMMER_BUILD_GHOST_ROLLBACK_COMPOSE_FILE"])
    require(recipe == root / COMPOSE)
    public_files = {relative: stable_bytes(root / relative) for relative in (COMPOSE, CADDY, CONTRACT)}
    sources = receipt["sources"]
    source_git = sources["git"]
    require(source_git.get("clean") is True)
    head, tree = source_git["head"], source_git["tree"]
    require(re.fullmatch(r"[0-9a-f]{40}", head) and re.fullmatch(r"[0-9a-f]{40}", tree))
    git = ["git", "--no-replace-objects", "-C", str(root)]
    git_environment = dict(os.environ, GIT_NO_LAZY_FETCH="1")
    require(command([*git, "rev-parse", "--show-toplevel"], git_environment).decode().strip() == str(root))
    require(command([*git, "rev-parse", head + "^{tree}"], git_environment).decode().strip() == tree)
    for relative, data in public_files.items():
        require(command([*git, "show", head + ":" + relative], git_environment) == data)
    file_binding(sources["compose"], recipe, public_files[COMPOSE])
    file_binding(sources["caddy"], root / CADDY, public_files[CADDY])
    file_binding(runtime["confinement"]["caddySource"], root / CADDY, public_files[CADDY], True)
    require(parse_json(public_files[CONTRACT]) == {
        "schema": "chummer.build_ghost.tough_tongue.read_only_binding_contract.unconfigured.v2", "status": "blocked"})
    validate_recipe(public_files[COMPOSE], root)
    version = command(["docker", "compose", "version", "--short"]).decode().strip()
    require(re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version))
    environment = dict(os.environ)
    for key in ("COMPOSE_FILE", "COMPOSE_ENV_FILES"):
        environment.pop(key, None)
    environment.update(COMPOSE_PROFILES="", COMPOSE_DISABLE_ENV_FILE="true",
                       CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE=str(root / CONTRACT))
    compose = ["docker", "compose", "--env-file", "/dev/null", "--project-name", PROJECT,
               "--project-directory", str(root), "--file", str(recipe)]
    observed = {}
    for role, service in SERVICES.items():
        row = rows[role]
        require(HEX.fullmatch(row["composeConfigHash"]))
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", row["containerId"]))
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", row["image"]["imageId"]))
        file_binding(row["composeSource"], recipe, public_files[COMPOSE], True)
        output = command([*compose, "config", "--hash", service], environment).decode().strip()
        require(output == service + " " + row["composeConfigHash"])
        if mode == "inputs":
            continue
        ids = command(["docker", "ps", "--no-trunc", "--filter", "label=" + LABEL + "project=" + PROJECT,
                       "--filter", "label=" + LABEL + "service=" + service, "--filter", "status=running", "--format", "{{.ID}}"])
        container = ids.decode().strip()
        require(HEX.fullmatch(container))
        if mode == "prior":
            require("sha256:" + container == row["containerId"])
        require(inspect(container, "{{.Image}}") == row["image"]["imageId"])
        labels = parse_json(inspect(container, "{{json .Config.Labels}}"))
        wanted = {LABEL + "project": PROJECT, LABEL + "service": service,
                  LABEL + "project.config_files": str(recipe), LABEL + "project.working_dir": str(root),
                  LABEL + "config-hash": row["composeConfigHash"], LABEL + "version": version}
        require(all(labels.get(k) == value for k, value in wanted.items()))
        mounts = parse_json(inspect(container, "{{json .Mounts}}"))
        require(isinstance(mounts, list))
        normalized = []
        for mount in mounts:
            require(mount.get("Type") in {"volume", "bind"} and type(mount.get("RW")) is bool)
            if mount["Type"] == "bind":
                expected = {"edge": (str(root / CADDY), "/etc/caddy/Caddyfile"),
                            "ai": (str(root / CONTRACT), "/run/secrets/tough-tongue-read-only-binding-contract.json")}
                require(role in expected and (mount.get("Source"), mount.get("Destination")) == expected[role] and mount["RW"] is False)
            normalized.append({key: mount.get(key) for key in ("Type", "Destination", "Name", "Source", "RW")})
        require(len({m["Destination"] for m in normalized}) == len(normalized))
        ports = parse_json(inspect(container, "{{json .HostConfig.PortBindings}}"))
        require(ports == {"443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8443"}]} if role == "edge" else ports in ({}, None))
        observed[role] = {"labels": wanted, "image": row["image"]["imageId"],
                          "mounts": sorted(normalized, key=lambda m: m["Destination"]), "ports": ports}
    for relative, data in public_files.items():
        require(stable_bytes(root / relative) == data)
    require(stable_bytes(receipt_path) == receipt_bytes)
    inputs = digest(canonical({"attestation": pin, "root": str(root), "recipe": str(recipe), "version": version,
                               "publicFiles": {p: digest(data) for p, data in public_files.items()}}))
    runtime_hash = digest(canonical(observed)) if observed else expected_runtime
    if expected_inputs:
        require(inputs == expected_inputs)
    if mode == "restored" or expected_runtime and mode == "prior":
        require(expected_runtime and runtime_hash == expected_runtime)
    return inputs, runtime_hash


if __name__ == "__main__":
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--mode", choices=("prior", "inputs", "restored"), required=True)
    parser.add_argument("--expected-inputs", default="")
    parser.add_argument("--expected-runtime", default="")
    args = parser.parse_args()
    try:
        require(args.mode == "prior" or HEX.fullmatch(args.expected_inputs))
        print(*validate(args.mode, args.expected_inputs, args.expected_runtime))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, yaml.YAMLError):
        print("rook_prior_authority=invalid", file=sys.stderr)
        sys.exit(1)
