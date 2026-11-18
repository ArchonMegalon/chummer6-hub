#!/usr/bin/python3 -I
"""Observe an operator-admitted partial stack; never deploy or attest readiness.

Invoke with /usr/bin/python3 -I. The installed /usr/bin/docker and local Docker
daemon are trusted operator tooling, not authenticated by this helper. No
Compose evaluation, credential inspection, provider requests or Docker writes
are supported. Secret format validation does not establish runtime compatibility.
"""

import argparse
import base64
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


PROJECT = "chummer-build-ghost-private-nonprod"
PRESENTATION = "chummer-build-ghost-presentation"
NETWORK = PROJECT + "_build-ghost-private"
PACKET = PROJECT + "_build-ghost-packet-access"
JOURNAL = PROJECT + "_build-ghost-live-support"
CADDY = ("caddy-data", "caddy-config", "caddy-trust")
REVISIONS = {"hub", "core", "hubRegistry", "mediaFactory"}
SECRETS = ("CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN",
           "CHUMMER_AI_INTERNAL_API_TOKEN",
           "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")

CONTAINER_FORMAT = '{"id":{{json .Id}},"image":{{json .Image}},"status":{{json .State.Status}},"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}},"mounts":{{json .Mounts}},"networks":{{json .NetworkSettings.Networks}},"networkMode":{{json .HostConfig.NetworkMode}},"ports":{{json .HostConfig.PortBindings}}}'
NETWORK_FORMAT = '{"id":{{json .Id}},"name":{{json .Name}},"driver":{{json .Driver}},"scope":{{json .Scope}},"internal":{{json .Internal}},"ingress":{{json .Ingress}},"options":{{json .Options}},"containers":{{json .Containers}},"project":{{json (index .Labels "com.docker.compose.project")}},"role":{{json (index .Labels "com.docker.compose.network")}}}'
VOLUME_FORMAT = '{"name":{{json .Name}},"driver":{{json .Driver}},"scope":{{json .Scope}},"options":{{json .Options}},"mountpoint":{{json .Mountpoint}},"createdAt":{{json .CreatedAt}},"project":{{json (index .Labels "com.docker.compose.project")}},"role":{{json (index .Labels "com.docker.compose.volume")}}}'
IMAGE_FORMAT = '{"id":{{json .Id}},"digests":{{json .RepoDigests}},"hub":{{json (index .Config.Labels "org.opencontainers.image.revision")}},"core":{{json (index .Config.Labels "run.chummer.build-ghost.core-revision")}},"hubRegistry":{{json (index .Config.Labels "run.chummer.build-ghost.hub-registry-revision")}},"mediaFactory":{{json (index .Config.Labels "run.chummer.build-ghost.media-factory-revision")}},"profile":{{json (index .Config.Labels "run.chummer.build-ghost.profile")}}}'


def require(condition):
    if not condition:
        raise ValueError("preflight requirement not satisfied")


def exact_keys(value, expected):
    require(type(value) is dict and set(value) == set(expected))


def matches(pattern, value):
    return type(value) is str and pattern.fullmatch(value) is not None


def unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value)
        value[key] = item
    return value


def parse_json(data):
    def invalid_constant(_):
        raise ValueError("non-JSON constant")
    return json.loads(data, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)


def stable_admission(path_value):
    path = Path(path_value)
    require(path.is_absolute() and str(path) == path_value and ".." not in path.parts)
    for part in [*reversed(path.parents), path]:
        require(not stat.S_ISLNK(part.lstat().st_mode))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid())
        require(not before.st_mode & 0o022 and 0 < before.st_size <= 32768)
        data = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
        signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        require(len(data) == before.st_size and signature(before) == signature(after))
        require(signature(path.stat()) == signature(after))
    return data


def timestamp(value):
    # A public exact identity pin, not a clock-based freshness claim.
    return type(value) is str and re.fullmatch(r"[0-9T:.+Z-]{10,64}", value) is not None


def validate_admission(value):
    exact_keys(value, {"schema", "project", "presentation", "privateNetwork", "caddyVolumes", "images"})
    require(value["schema"] == "chummer.build_ghost.partial_bootstrap_admission.v1")
    require(value["project"] == PROJECT)
    presentation = value["presentation"]
    exact_keys(presentation, {"containerId", "imageId", "packetVolume", "packetVolumeCreatedAt"})
    require(matches(HEX64, presentation["containerId"]) and matches(IMAGE_ID, presentation["imageId"]))
    require(presentation["packetVolume"] == PACKET and timestamp(presentation["packetVolumeCreatedAt"]))
    network = value["privateNetwork"]
    exact_keys(network, {"id", "name"})
    require(matches(HEX64, network["id"]) and network["name"] == NETWORK)
    exact_keys(value["caddyVolumes"], CADDY)
    for role, pin in value["caddyVolumes"].items():
        if pin is not None:
            exact_keys(pin, {"name", "createdAt"})
            require(pin["name"] == PROJECT + "_" + role and timestamp(pin["createdAt"]))
    exact_keys(value["images"], {"ai", "edge"})
    ai, edge = value["images"]["ai"], value["images"]["edge"]
    exact_keys(ai, {"id", "sourceRevisions"})
    exact_keys(edge, {"id", "repoDigest"})
    require(matches(IMAGE_ID, ai["id"]) and matches(IMAGE_ID, edge["id"]))
    require(len({ai["id"], edge["id"], presentation["imageId"]}) == 3)
    exact_keys(ai["sourceRevisions"], REVISIONS)
    require(all(matches(REVISION, revision) for revision in ai["sourceRevisions"].values()))
    require(type(edge["repoDigest"]) is str
            and re.fullmatch(r"(?:docker\.io/library/)?caddy@sha256:[0-9a-f]{64}", edge["repoDigest"]))


def read_secrets(fd):
    require(type(fd) is int and fd > 2)
    info = os.fstat(fd)
    require(stat.S_ISFIFO(info.st_mode) or stat.S_ISREG(info.st_mode))
    if stat.S_ISREG(info.st_mode):
        require(info.st_uid == os.getuid() and not info.st_mode & 0o077 and info.st_size <= 16384)
    # The private descriptor is consumed and closed here, before any child.
    # Pipes must terminate promptly; regular descriptors also have a hard cap.
    data = bytearray()
    deadline = time.monotonic() + 3
    try:
        os.set_blocking(fd, False)
        with selectors.SelectSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                require(remaining > 0 and selector.select(remaining))
                chunk = os.read(fd, min(4096, 16385 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                require(len(data) <= 16384)
    finally:
        os.close(fd)
    value = parse_json(data)
    exact_keys(value, SECRETS)
    for name in SECRETS[:2]:
        token = value[name]
        require(type(token) is str and 32 <= len(token) <= 4096
                and all(33 <= ord(character) <= 126 for character in token))
    key = value[SECRETS[2]]
    require(type(key) is str and len(key) == 44)
    decoded = base64.b64decode(key, validate=True)
    require(len(decoded) == 32 and base64.b64encode(decoded).decode("ascii") == key)
    require(len(set(value.values())) == 3)
    # No values, digests or inferred compatibility are returned or persisted.


class Docker:
    def __init__(self, binary):
        self.binary = binary

    def command(self, args):
        limit = 1024 * 1024
        output = bytearray()
        counts = {"stdout": 0, "stderr": 0}
        # No inherited Docker contexts/endpoints, Compose selectors, provider
        # credentials, secret FD or shell. These are built-in read-only verbs.
        with subprocess.Popen([self.binary, "--host", "unix:///var/run/docker.sock", *args],
                              env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              close_fds=True, start_new_session=True) as process:
            deadline = time.monotonic() + 10
            succeeded = False
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
                            # Count and discard all diagnostics, never print them.
                    require(process.wait(timeout=max(0.001, deadline - time.monotonic())) == 0)
                    succeeded = True
            finally:
                if not succeeded:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait()
        return bytes(output)

    def ids(self, query):
        data = self.command(["ps", "-a", "--no-trunc", "--filter", query, "--format", "{{.ID}}"])
        values = data.decode("ascii").splitlines()
        require(all(matches(HEX64, value) for value in values) and len(values) == len(set(values)))
        return sorted(values)

    def inspect(self, kind, identity, projection):
        prefix = [] if kind == "container" else [kind]
        return parse_json(self.command([*prefix, "inspect", identity, "--format", projection]))


def validate_volume(value, role, created_at):
    name = PROJECT + "_" + role
    require(type(value) is dict and value.get("name") == name)
    require(value.get("driver") == "local" and value.get("scope") == "local")
    require(value.get("options") in (None, {}))
    require(value.get("project") == PROJECT and value.get("role") == role)
    require(value.get("createdAt") == created_at)
    mountpoint = value.get("mountpoint")
    require(type(mountpoint) is str and mountpoint.startswith("/")
            and ".." not in Path(mountpoint).parts and str(Path(mountpoint)) == mountpoint)


def snapshot(docker, admission):
    pin = admission["presentation"]
    pid = pin["containerId"]
    network_id = admission["privateNetwork"]["id"]
    require(docker.ids("label=com.docker.compose.project=" + PROJECT) == [pid])
    presentation = docker.inspect("container", pid, CONTAINER_FORMAT)
    require(type(presentation) is dict and presentation.get("id") == pid)
    require(presentation.get("image") == pin["imageId"] and presentation.get("status") == "running")
    require(presentation.get("health") == "healthy" and presentation.get("project") == PROJECT)
    require(presentation.get("service") == PRESENTATION and presentation.get("networkMode") == NETWORK)
    require(presentation.get("ports") in (None, {}))
    networks = presentation.get("networks")
    exact_keys(networks, {NETWORK})
    attachment = networks[NETWORK]
    require(type(attachment) is dict and attachment.get("NetworkID") == network_id)
    aliases = attachment.get("Aliases")
    require(type(aliases) is list and all(type(alias) is str for alias in aliases) and PRESENTATION in aliases)
    require(not set(aliases) & {"chummer-build-ghost-ai", "build-ghost-private-edge", "canary.chummer.run",
                                "presentation.canary.chummer.run", "build-ghost-cloudflare-access-edge"})
    network = docker.inspect("network", network_id, NETWORK_FORMAT)
    require(type(network) is dict and network.get("id") == network_id and network.get("name") == NETWORK)
    require(network.get("driver") == "bridge" and network.get("scope") == "local")
    require(network.get("internal") is True and network.get("ingress") is False)
    require(network.get("options") in (None, {}) and network.get("project") == PROJECT)
    require(network.get("role") == "build-ghost-private")
    exact_keys(network.get("containers"), {pid})
    require(docker.ids("network=" + network_id) == [pid])

    names = docker.command(["volume", "ls", "--format", "{{.Name}}"]).decode("ascii").splitlines()
    require(all(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name) for name in names))
    require(len(names) == len(set(names)) and PACKET in names and JOURNAL not in names)
    packet = docker.inspect("volume", PACKET, VOLUME_FORMAT)
    validate_volume(packet, "build-ghost-packet-access", pin["packetVolumeCreatedAt"])
    require(docker.ids("volume=" + PACKET) == [pid])
    mounts = presentation.get("mounts")
    require(type(mounts) is list and len(mounts) == 1 and type(mounts[0]) is dict)
    mount = mounts[0]
    require(mount.get("Type") == "volume" and mount.get("Name") == PACKET and mount.get("Driver") == "local")
    require(mount.get("Source") == packet["mountpoint"] and mount.get("Destination") == "/app/state")
    require(mount.get("RW") is True)
    volumes = {PACKET: packet}
    for role, volume_pin in admission["caddyVolumes"].items():
        name = PROJECT + "_" + role
        if volume_pin is None:
            require(name not in names)
        else:
            require(name in names)
            value = docker.inspect("volume", name, VOLUME_FORMAT)
            validate_volume(value, role, volume_pin["createdAt"])
            require(docker.ids("volume=" + name) == [])
            volumes[name] = value

    images = {}
    for role, image_pin in admission["images"].items():
        value = docker.inspect("image", image_pin["id"], IMAGE_FORMAT)
        require(type(value) is dict and value.get("id") == image_pin["id"])
        if role == "ai":
            require(value.get("profile") == "private-nonprod")
            require(all(value.get(key) == revision for key, revision in image_pin["sourceRevisions"].items()))
        else:
            require(type(value.get("digests")) is list and image_pin["repoDigest"] in value["digests"])
        images[role] = value
    return {"presentation": presentation, "network": network, "volumes": volumes, "images": images}


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid preflight arguments")


def main(argv=None, *, docker_binary="/usr/bin/docker"):
    # Dependency seam is for daemon-free tests only, never an operator CLI flag.
    report = {
        "schema": "chummer.build_ghost.partial_bootstrap_preflight.v1",
        "status": "preflight-blocked", "scope": "observation-only",
        "deploymentReady": False, "runtimeMutationPerformed": False,
        "providerActivationAuthorized": False, "historicalDeploymentAttested": False,
        "existingSecretCompatibilityChecked": False, "secretCustodyVerified": False,
        "authenticatedImageProvenanceChecked": False,
        "remainingOperations": ["operator-secret-compatibility-and-custody", "staged-image-provenance",
                                "bootstrap-transaction-and-rollback", "journal-initialization",
                                "runtime-readback-and-health", "grounded-local-canary",
                                "signed-in-ingress", "provider-and-team-truth"],
    }
    stage = "arguments"
    try:
        parser = SafeParser(description=__doc__, allow_abbrev=False)
        parser.add_argument("--admission", required=True)
        parser.add_argument("--secrets-fd", type=int, required=True)
        args = parser.parse_args(argv)
        stage = "operator-admission"
        data = stable_admission(args.admission)
        admission = parse_json(data)
        validate_admission(admission)
        stage = "secret-format-only"
        read_secrets(args.secrets_fd)
        stage = "partial-runtime-baseline"
        docker = Docker(docker_binary)
        first = snapshot(docker, admission)
        stage = "observation-drift"
        require(snapshot(docker, admission) == first)
        require(stable_admission(args.admission) == data)
        # Identify only the public admission and projected Docker metadata.
        # These are observation bindings, not secret hashes or deployment permits.
        report["admissionSha256"] = "sha256:" + hashlib.sha256(data).hexdigest()
        public_projection = json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        report["runtimeProjectionSha256"] = "sha256:" + hashlib.sha256(public_projection).hexdigest()
        report["checks"] = ["presentation-only-baseline", "private-network-and-packet-volume",
                            "caddy-volume-admission-and-journal-absence", "pinned-image-label-consistency",
                            "operator-secret-format-and-distinctness", "two-observations-agree"]
        report["limitations"] = ["not-a-deployment-permit", "not-an-atomic-runtime-lock",
                                 "volume-contents-unexamined", "provider-posture-not-evaluated",
                                 "installed-docker-and-local-daemon-trusted"]
        report["status"] = "preflight-passed"
    except (Exception, KeyboardInterrupt):
        # Never expose exception messages, tool output, operator values or paths.
        report["blockedStage"] = stage
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "preflight-passed" else 1


if __name__ == "__main__":
    sys.exit(main())
