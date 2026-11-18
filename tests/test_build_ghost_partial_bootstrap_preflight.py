"""Executable, daemon-free contract for the observational partial-stack preflight."""

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "ops/build-ghost-private-nonprod/preflight-provider-disabled-rook-bootstrap.py"
PROJECT = "chummer-build-ghost-private-nonprod"
PRESENTATION = "chummer-build-ghost-presentation"
PID = "1" * 64
NID = "2" * 64
PIMAGE = "sha256:" + "3" * 64
AIIMAGE = "sha256:" + "4" * 64
EDGEIMAGE = "sha256:" + "5" * 64
PACKET = PROJECT + "_build-ghost-packet-access"
NETWORK = PROJECT + "_build-ghost-private"
JOURNAL = PROJECT + "_build-ghost-live-support"
CADDY = ("caddy-data", "caddy-config", "caddy-trust")
SENTINEL = "synthetic-secret-do-not-disclose-1234567890"
SECRET_NAMES = (
    "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN",
    "CHUMMER_AI_INTERNAL_API_TOKEN",
    "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY",
)

# The fake accepts these projections only. Full inspect, Config.Env, exec,
# Compose, pulls and mutations are rejected before they can do any work.
CONTAINER_FORMAT = '{"id":{{json .Id}},"image":{{json .Image}},"status":{{json .State.Status}},"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}},"mounts":{{json .Mounts}},"networks":{{json .NetworkSettings.Networks}},"networkMode":{{json .HostConfig.NetworkMode}},"ports":{{json .HostConfig.PortBindings}}}'
NETWORK_FORMAT = '{"id":{{json .Id}},"name":{{json .Name}},"driver":{{json .Driver}},"scope":{{json .Scope}},"internal":{{json .Internal}},"ingress":{{json .Ingress}},"options":{{json .Options}},"containers":{{json .Containers}},"project":{{json (index .Labels "com.docker.compose.project")}},"role":{{json (index .Labels "com.docker.compose.network")}}}'
VOLUME_FORMAT = '{"name":{{json .Name}},"driver":{{json .Driver}},"scope":{{json .Scope}},"options":{{json .Options}},"mountpoint":{{json .Mountpoint}},"createdAt":{{json .CreatedAt}},"project":{{json (index .Labels "com.docker.compose.project")}},"role":{{json (index .Labels "com.docker.compose.volume")}}}'
IMAGE_FORMAT = '{"id":{{json .Id}},"digests":{{json .RepoDigests}},"hub":{{json (index .Config.Labels "org.opencontainers.image.revision")}},"core":{{json (index .Config.Labels "run.chummer.build-ghost.core-revision")}},"hubRegistry":{{json (index .Config.Labels "run.chummer.build-ghost.hub-registry-revision")}},"mediaFactory":{{json (index .Config.Labels "run.chummer.build-ghost.media-factory-revision")}},"profile":{{json (index .Config.Labels "run.chummer.build-ghost.profile")}}}'


def volume(role):
    name = PROJECT + "_" + role
    return {"name": name, "driver": "local", "scope": "local", "options": None,
            "mountpoint": "/var/lib/docker/volumes/" + name + "/_data",
            "createdAt": "2026-08-22T10:00:00Z", "project": PROJECT, "role": role}


def fixture(tmp_path):
    revisions = {"hub": "a" * 40, "core": "b" * 40,
                 "hubRegistry": "c" * 40, "mediaFactory": "d" * 40}
    edge_digest = "caddy@sha256:" + "e" * 64
    admission = {
        "schema": "chummer.build_ghost.partial_bootstrap_admission.v1",
        "project": PROJECT,
        "presentation": {"containerId": PID, "imageId": PIMAGE, "packetVolume": PACKET,
                         "packetVolumeCreatedAt": volume("build-ghost-packet-access")["createdAt"]},
        "privateNetwork": {"id": NID, "name": NETWORK},
        "caddyVolumes": {role: None for role in CADDY},
        "images": {"ai": {"id": AIIMAGE, "sourceRevisions": revisions},
                   "edge": {"id": EDGEIMAGE, "repoDigest": edge_digest}},
    }
    state = {
        "projectContainers": [PID],
        "container": {"id": PID, "image": PIMAGE, "status": "running", "health": "healthy",
                      "project": PROJECT, "service": PRESENTATION,
                      "mounts": [{"Type": "volume", "Name": PACKET, "Driver": "local",
                                  "Source": volume("build-ghost-packet-access")["mountpoint"],
                                  "Destination": "/app/state", "RW": True}],
                      "networks": {NETWORK: {"NetworkID": NID, "Aliases": [PRESENTATION, "old-presentation"]}},
                      "networkMode": NETWORK, "ports": {}},
        "network": {"id": NID, "name": NETWORK, "driver": "bridge", "scope": "local",
                    "internal": True, "ingress": False, "options": {},
                    "containers": {PID: {"Name": "old-presentation"}},
                    "project": PROJECT, "role": "build-ghost-private"},
        "volumes": {PACKET: volume("build-ghost-packet-access")},
        "consumers": {PACKET: [PID]}, "networkConsumers": [PID],
        "images": {AIIMAGE: {"id": AIIMAGE, "digests": [], "profile": "private-nonprod", **revisions},
                   EDGEIMAGE: {"id": EDGEIMAGE, "digests": [edge_digest], "profile": None,
                               **{key: None for key in revisions}}},
    }
    secrets = {SECRET_NAMES[0]: SENTINEL, SECRET_NAMES[1]: SENTINEL + "-distinct",
               SECRET_NAMES[2]: base64.b64encode(bytes(range(32))).decode()}
    state_path = tmp_path / "state.json"
    admission_path = tmp_path / "admission.json"
    log = tmp_path / "calls.jsonl"
    fake = tmp_path / "docker"
    # Only the trusted fake reads this nonsecret fixture file. It is not a
    # supported production environment override or alternate daemon endpoint.
    fake.write_text("#!/usr/bin/python3 -I\n" +
                    "import json, os, sys\nfrom pathlib import Path\n" +
                    "base=Path(__file__).parent\nstate=json.loads((base/'state.json').read_text())\n" +
                    "assert sys.argv[1:3]==['--host','unix:///var/run/docker.sock']\n" +
                    "a=sys.argv[3:]\nlog=base/'calls.jsonl'\n" +
                    "with log.open('a') as stream: stream.write(json.dumps(a)+'\\n')\n" +
                    "assert not any(k.startswith('CHUMMER_') or k.startswith('COMPOSE_') or k.startswith('DOCKER_') for k in os.environ)\n" +
                    "try: os.fstat(int((base/'secret-fd').read_text()))\n" +
                    "except OSError: pass\nelse: raise SystemExit(88)\n" +
                    "if state.get('fail'): print('" + SENTINEL + "', file=sys.stderr); raise SystemExit(42)\n" +
                    "if state.get('oversize'): print('x'*2200000); raise SystemExit(0)\n" +
                    "if state.get('oversizeStderr'): print('x'*2200000, file=sys.stderr); raise SystemExit(0)\n" +
                    "if state.get('malformed'): print('{}'); raise SystemExit(0)\n" +
                    "if a[:2]==state.get('failPrefix') or (state.get('secondPassFail') and len(log.read_text().splitlines())>10): print('" + SENTINEL + "', file=sys.stderr); raise SystemExit(42)\n" +
                    "if a==['ps','-a','--no-trunc','--filter','label=com.docker.compose.project=" + PROJECT + "','--format','{{.ID}}']:\n" +
                    " ids=state['projectContainers']\n" +
                    " if state.get('drift') and len(log.read_text().splitlines())>2: ids=ids+['9'*64]\n" +
                    " print('\\n'.join(ids))\n" +
                    "elif a==['volume','ls','--format','{{.Name}}']: print('\\n'.join(state['volumes']))\n" +
                    "elif len(a)==7 and a[:4]==['ps','-a','--no-trunc','--filter'] and a[4].startswith('volume=') and a[5:]==['--format','{{.ID}}']:\n" +
                    " sys.stdout.write(''.join(value+'\\n' for value in state['consumers'].get(a[4][7:],[])))\n" +
                    "elif a==['ps','-a','--no-trunc','--filter','network=" + NID + "','--format','{{.ID}}']: print('\\n'.join(state['networkConsumers']))\n" +
                    f"elif a==['inspect','{PID}','--format',{CONTAINER_FORMAT!r}]: print(json.dumps(state['container']))\n" +
                    f"elif a==['network','inspect','{NID}','--format',{NETWORK_FORMAT!r}]: print(json.dumps(state['network']))\n" +
                    f"elif len(a)==5 and a[:2]==['volume','inspect'] and a[3:]==['--format',{VOLUME_FORMAT!r}]: print(json.dumps(state['volumes'][a[2]]))\n" +
                    f"elif len(a)==5 and a[:2]==['image','inspect'] and a[3:]==['--format',{IMAGE_FORMAT!r}]: print(json.dumps(state['images'][a[2]]))\n" +
                    "else: raise SystemExit(87)\n", encoding="utf-8")
    fake.chmod(0o700)
    launcher = tmp_path / "launch.py"
    launcher.write_text(
        "import importlib.util, sys\n"
        f"spec=importlib.util.spec_from_file_location('preflight', {str(HELPER)!r})\n"
        "module=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\n"
        f"raise SystemExit(module.main(sys.argv[1:], docker_binary={str(fake)!r}))\n")
    admission_path.write_text(json.dumps(admission))
    admission_path.chmod(0o600)
    state_path.write_text(json.dumps(state))
    return {"dir": tmp_path, "state": state, "admission": admission, "secrets": secrets,
            "admission_path": admission_path, "state_path": state_path, "log": log}


def run_preflight(fx, *, admission_bytes=None, secret_bytes=None, extra=(), secret_file_mode=None,
                  keep_writer_open=False):
    fx["state_path"].write_text(json.dumps(fx["state"]))
    fx["admission_path"].write_bytes(admission_bytes if admission_bytes is not None
                                     else json.dumps(fx["admission"]).encode())
    secret_bytes = json.dumps(fx["secrets"]).encode() if secret_bytes is None else secret_bytes
    if secret_file_mode is None:
        read_fd, write_fd = os.pipe()
    else:
        secret_path = fx["dir"] / "private-test-secrets.json"
        secret_path.write_bytes(secret_bytes)
        secret_path.chmod(secret_file_mode)
        read_fd, write_fd = os.open(secret_path, os.O_RDONLY), None
    try:
        # Test input fits into the pipe without a concurrent writer.
        if write_fd is not None:
            os.write(write_fd, secret_bytes)
            if not keep_writer_open:
                os.close(write_fd)
                write_fd = None
        (fx["dir"] / "secret-fd").write_text(str(read_fd))
        result = subprocess.run(
            ["/usr/bin/python3", "-I", str(fx["dir"] / "launch.py"), "--admission", str(fx["admission_path"]),
             "--secrets-fd", str(read_fd), *extra],
            env={"PATH": str(fx["dir"]) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
                 "CHUMMER_SECRET_POISON": SENTINEL, "COMPOSE_FILE": SENTINEL,
                 "DOCKER_HOST": "tcp://untrusted.invalid:2375"},
            pass_fds=(read_fd,), capture_output=True, text=True, timeout=20, check=False)
    finally:
        os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)
    assert SENTINEL not in result.stdout + result.stderr
    calls = [json.loads(line) for line in fx["log"].read_text().splitlines()] if fx["log"].exists() else []
    assert SENTINEL not in json.dumps(calls)
    assert all(call[0] in ("ps", "inspect", "network", "volume", "image") for call in calls)
    assert all(".Config.Env" not in " ".join(call) for call in calls)
    allowed = [
        ["ps", "-a", "--no-trunc", "--filter", "label=com.docker.compose.project=" + PROJECT, "--format", "{{.ID}}"],
        ["ps", "-a", "--no-trunc", "--filter", "network=" + NID, "--format", "{{.ID}}"],
        ["volume", "ls", "--format", "{{.Name}}"],
        ["inspect", PID, "--format", CONTAINER_FORMAT],
        ["network", "inspect", NID, "--format", NETWORK_FORMAT],
        *[["ps", "-a", "--no-trunc", "--filter", "volume=" + name, "--format", "{{.ID}}"]
          for name in [PACKET, *(PROJECT + "_" + role for role in CADDY)]],
        *[["volume", "inspect", name, "--format", VOLUME_FORMAT]
          for name in [PACKET, *(PROJECT + "_" + role for role in CADDY)]],
        *[["image", "inspect", name, "--format", IMAGE_FORMAT] for name in (AIIMAGE, EDGEIMAGE)],
    ]
    assert all(call in allowed for call in calls), calls
    return result, calls


def assert_blocked(result):
    assert result.returncode != 0
    report = json.loads(result.stdout)
    assert report["status"] == "preflight-blocked"
    assert report["deploymentReady"] is False
    assert report["runtimeMutationPerformed"] is False
    assert report["providerActivationAuthorized"] is False


def test_admits_exact_partial_baseline_without_claiming_readiness_or_historical_authority(tmp_path):
    fx = fixture(tmp_path)
    result, calls = run_preflight(fx)
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["status"] == "preflight-passed"
    for field in ("deploymentReady", "runtimeMutationPerformed", "providerActivationAuthorized",
                  "historicalDeploymentAttested", "existingSecretCompatibilityChecked",
                  "authenticatedImageProvenanceChecked", "secretCustodyVerified"):
        assert report[field] is False
    assert set(report["remainingOperations"]) >= {
        "grounded-local-canary", "signed-in-ingress", "provider-and-team-truth",
        "operator-secret-compatibility-and-custody", "staged-image-provenance",
        "bootstrap-transaction-and-rollback", "journal-initialization", "runtime-readback-and-health"}
    assert len([call for call in calls if call[0] == "inspect"]) == 2
    assert all("config_files" not in " ".join(call) for call in calls)


@pytest.mark.parametrize("role", ("ai-running", "ai-exited", "edge-created", "trust-export-exited", "foreign-role"))
def test_rejects_any_extra_project_container_in_all_states(tmp_path, role):
    fx = fixture(tmp_path)
    fx["state"]["projectContainers"].append("9" * 64)
    result, _ = run_preflight(fx)
    assert_blocked(result)


@pytest.mark.parametrize("field,value", (("id", "9" * 64), ("image", EDGEIMAGE), ("status", "exited"),
                                         ("health", "starting"), ("project", "foreign"), ("service", "other"),
                                         ("networkMode", "host"), ("ports", {"8080/tcp": [{"HostPort": "8080"}]})))
def test_rejects_changed_presentation_identity_or_posture(tmp_path, field, value):
    fx = fixture(tmp_path)
    fx["state"]["container"][field] = value
    result, _ = run_preflight(fx)
    assert_blocked(result)


@pytest.mark.parametrize("field,value", (("Type", "bind"), ("Name", "other"), ("Destination", "/other"),
                                         ("Source", "/other"), ("RW", False), ("Driver", "nfs")))
def test_rejects_wrong_packet_mount(tmp_path, field, value):
    fx = fixture(tmp_path)
    fx["state"]["container"]["mounts"][0][field] = value
    result, _ = run_preflight(fx)
    assert_blocked(result)


@pytest.mark.parametrize("mutation", ("extra-mount", "extra-network", "wrong-network-id", "reserved-alias",
                                      "extra-network-endpoint", "stopped-network-consumer", "packet-other-consumer", "journal-present"))
def test_rejects_ownership_or_isolation_conflict(tmp_path, mutation):
    fx = fixture(tmp_path)
    state = fx["state"]
    if mutation == "extra-mount":
        state["container"]["mounts"].append(copy.deepcopy(state["container"]["mounts"][0]))
    elif mutation == "extra-network":
        state["container"]["networks"]["public"] = {}
    elif mutation == "wrong-network-id":
        state["container"]["networks"][NETWORK]["NetworkID"] = "9" * 64
    elif mutation == "reserved-alias":
        state["container"]["networks"][NETWORK]["Aliases"].append("chummer-build-ghost-ai")
    elif mutation == "extra-network-endpoint":
        state["network"]["containers"]["9" * 64] = {}
    elif mutation == "stopped-network-consumer":
        state["networkConsumers"].append("9" * 64)
    elif mutation == "packet-other-consumer":
        state["consumers"][PACKET].append("9" * 64)
    else:
        state["volumes"][JOURNAL] = volume("build-ghost-live-support")
    result, _ = run_preflight(fx)
    assert_blocked(result)


@pytest.mark.parametrize("field,value", (("internal", False), ("ingress", True), ("driver", "overlay"),
                                         ("scope", "swarm"), ("options", {"opaque": "yes"}),
                                         ("id", "9" * 64), ("name", "other"), ("project", "other"), ("role", "other")))
def test_rejects_unadmitted_network(tmp_path, field, value):
    fx = fixture(tmp_path)
    fx["state"]["network"][field] = value
    result, _ = run_preflight(fx)
    assert_blocked(result)


@pytest.mark.parametrize("role", ("build-ghost-packet-access", *CADDY))
@pytest.mark.parametrize("field,value", (("driver", "nfs"), ("scope", "swarm"), ("options", {"device": "/other"}),
                                         ("project", "other"), ("role", "other"), ("mountpoint", "relative")))
def test_rejects_unsafe_volume_metadata(tmp_path, role, field, value):
    fx = fixture(tmp_path)
    name = PROJECT + "_" + role
    fx["state"]["volumes"][name] = volume(role)
    if role in CADDY:
        fx["admission"]["caddyVolumes"][role] = {"name": name, "createdAt": volume(role)["createdAt"]}
    fx["state"]["volumes"][name][field] = value
    result, _ = run_preflight(fx)
    assert_blocked(result)


def test_admits_only_explicitly_pinned_unused_caddy_volumes(tmp_path):
    fx = fixture(tmp_path)
    for role in CADDY:
        name = PROJECT + "_" + role
        fx["state"]["volumes"][name] = volume(role)
        fx["admission"]["caddyVolumes"][role] = {"name": name, "createdAt": volume(role)["createdAt"]}
    result, _ = run_preflight(fx)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("mutation", ("unadmitted", "missing", "timestamp", "consumer"))
def test_rejects_caddy_admission_drift(tmp_path, mutation):
    fx = fixture(tmp_path)
    role = "caddy-data"
    name = PROJECT + "_" + role
    fx["state"]["volumes"][name] = volume(role)
    if mutation != "unadmitted":
        fx["admission"]["caddyVolumes"][role] = {"name": name, "createdAt": volume(role)["createdAt"]}
    if mutation == "missing":
        del fx["state"]["volumes"][name]
    elif mutation == "timestamp":
        fx["state"]["volumes"][name]["createdAt"] = "different"
    elif mutation == "consumer":
        fx["state"]["consumers"][name] = ["9" * 64]
    result, _ = run_preflight(fx)
    assert_blocked(result)


@pytest.mark.parametrize("field", ("id", "hub", "core", "hubRegistry", "mediaFactory", "profile"))
def test_rejects_ai_image_identity_or_label_mismatch(tmp_path, field):
    fx = fixture(tmp_path)
    fx["state"]["images"][AIIMAGE][field] = "wrong"
    result, _ = run_preflight(fx)
    assert_blocked(result)


def test_rejects_edge_digest_mismatch(tmp_path):
    fx = fixture(tmp_path)
    fx["state"]["images"][EDGEIMAGE]["digests"] = ["caddy:latest"]
    result, _ = run_preflight(fx)
    assert_blocked(result)


@pytest.mark.parametrize("mutation", ("mutable-ai", "mutable-edge", "project", "unknown-key", "missing-key",
                                      "relative-network", "malformed-revision"))
def test_rejects_invalid_public_admission_before_docker(tmp_path, mutation):
    fx = fixture(tmp_path)
    admission = fx["admission"]
    if mutation in ("mutable-ai", "mutable-edge"):
        admission["images"][mutation[8:]]["id"] = "image:latest"
    elif mutation == "project":
        admission["project"] = "other"
    elif mutation == "unknown-key":
        admission["compose"] = "/untrusted/compose.yml"
    elif mutation == "missing-key":
        del admission["presentation"]
    elif mutation == "relative-network":
        admission["privateNetwork"]["name"] = "other"
    else:
        admission["images"]["ai"]["sourceRevisions"]["hub"] = "main"
    result, calls = run_preflight(fx)
    assert_blocked(result)
    assert not calls


@pytest.mark.parametrize("payload", (b'{"schema":"one","schema":"two"}', b'{}', b'[]', b'null', b'NaN', b'not json'))
def test_rejects_malformed_or_duplicate_admission_before_docker(tmp_path, payload):
    fx = fixture(tmp_path)
    result, calls = run_preflight(fx, admission_bytes=payload)
    assert_blocked(result)
    assert not calls


@pytest.mark.parametrize("mutation", ("short", "equal", "newline", "missing", "extra", "key-short", "key-noncanonical"))
def test_rejects_invalid_operator_secrets_without_output_or_docker(tmp_path, mutation):
    fx = fixture(tmp_path)
    secrets = fx["secrets"]
    if mutation == "short":
        secrets[SECRET_NAMES[0]] = "short"
    elif mutation == "equal":
        secrets[SECRET_NAMES[1]] = secrets[SECRET_NAMES[0]]
    elif mutation == "newline":
        secrets[SECRET_NAMES[0]] += "\n"
    elif mutation == "missing":
        del secrets[SECRET_NAMES[2]]
    elif mutation == "extra":
        secrets["PROVIDER_KEY"] = SENTINEL
    elif mutation == "key-short":
        secrets[SECRET_NAMES[2]] = base64.b64encode(b"short").decode()
    else:
        secrets[SECRET_NAMES[2]] += "="
    result, calls = run_preflight(fx)
    assert_blocked(result)
    assert not calls


def test_rejects_duplicate_secret_keys(tmp_path):
    fx = fixture(tmp_path)
    result, calls = run_preflight(fx, secret_bytes=b'{"key":"one","key":"two"}')
    assert_blocked(result)
    assert not calls


@pytest.mark.parametrize("mode", ("fail", "malformed", "oversize", "oversizeStderr", "drift"))
def test_fails_closed_on_docker_error_malformed_or_drifting_output(tmp_path, mode):
    fx = fixture(tmp_path)
    fx["state"][mode] = True
    result, _ = run_preflight(fx)
    assert_blocked(result)


def test_rejects_group_writable_admission(tmp_path):
    fx = fixture(tmp_path)
    fx["admission_path"].chmod(0o620)
    result, calls = run_preflight(fx)
    assert_blocked(result)
    assert not calls


@pytest.mark.parametrize("prefix", (["volume", "ls"], ["volume", "inspect"], ["image", "inspect"], ["network", "inspect"]))
def test_later_docker_failure_is_not_absence(tmp_path, prefix):
    fx = fixture(tmp_path)
    fx["state"]["failPrefix"] = prefix
    result, _ = run_preflight(fx)
    assert_blocked(result)


def test_second_pass_error_blocks_preflight(tmp_path):
    fx = fixture(tmp_path)
    fx["state"]["secondPassFail"] = True
    result, _ = run_preflight(fx)
    assert_blocked(result)


def test_accepts_operator_owned_private_regular_secret_fd(tmp_path):
    fx = fixture(tmp_path)
    result, _ = run_preflight(fx, secret_file_mode=0o600)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("mode", (0o604, 0o640, 0o660))
def test_rejects_shared_regular_secret_fd_before_docker(tmp_path, mode):
    fx = fixture(tmp_path)
    result, calls = run_preflight(fx, secret_file_mode=mode)
    assert_blocked(result)
    assert not calls


def test_rejects_oversized_secret_fd_before_docker(tmp_path):
    fx = fixture(tmp_path)
    result, calls = run_preflight(fx, secret_file_mode=0o600, secret_bytes=b"x" * 20000)
    assert_blocked(result)
    assert not calls


def test_does_not_wait_forever_for_private_pipe_eof(tmp_path):
    fx = fixture(tmp_path)
    result, calls = run_preflight(fx, keep_writer_open=True)
    assert_blocked(result)
    assert not calls


@pytest.mark.parametrize("flag", ("--docker-bin", "--docker-host", "--project", "--compose-file"))
def test_cli_cannot_override_observation_authority(tmp_path, flag):
    fx = fixture(tmp_path)
    result, calls = run_preflight(fx, extra=(flag, SENTINEL))
    assert_blocked(result)
    assert not calls


def test_rejects_symlink_admission(tmp_path):
    fx = fixture(tmp_path)
    original = fx["admission_path"]
    linked = tmp_path / "linked-admission.json"
    linked.symlink_to(original)
    fx["admission_path"] = linked
    result, calls = run_preflight(fx)
    assert_blocked(result)
    assert not calls


def test_rejects_oversized_admission_before_docker(tmp_path):
    fx = fixture(tmp_path)
    result, calls = run_preflight(fx, admission_bytes=b" " * 32769)
    assert_blocked(result)
    assert not calls


def test_packet_creation_time_is_an_exact_admission_pin(tmp_path):
    fx = fixture(tmp_path)
    fx["state"]["volumes"][PACKET]["createdAt"] = "2026-09-01T00:00:00Z"
    result, _ = run_preflight(fx)
    assert_blocked(result)


def test_public_observation_bindings_identify_inputs_without_secret_fingerprints(tmp_path):
    fx = fixture(tmp_path)
    result, _ = run_preflight(fx)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["admissionSha256"] == "sha256:" + hashlib.sha256(fx["admission_path"].read_bytes()).hexdigest()
    projection = {"presentation": fx["state"]["container"], "network": fx["state"]["network"],
                  "volumes": fx["state"]["volumes"],
                  "images": {"ai": fx["state"]["images"][AIIMAGE], "edge": fx["state"]["images"][EDGEIMAGE]}}
    public_bytes = json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    assert report["runtimeProjectionSha256"] == "sha256:" + hashlib.sha256(public_bytes).hexdigest()
    fx["secrets"] = {SECRET_NAMES[0]: "another-synthetic-token-1111111111111111",
                     SECRET_NAMES[1]: "another-synthetic-token-2222222222222222",
                     SECRET_NAMES[2]: base64.b64encode(bytes(reversed(range(32)))).decode()}
    other, _ = run_preflight(fx)
    assert other.returncode == 0
    assert json.loads(other.stdout) == report
