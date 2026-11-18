"""Host-local bootstrap ownership bookkeeping, not deployment authority.

Standard library only. No runtime adapter or command-line entry point exists.
Callers supply public observations; plans never authorize or execute deletion.
An independently retained checkpoint is mandatory on reopen and every mutation.
"""

import copy
import fcntl
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid


PROJECT = "chummer-build-ghost-private-nonprod"
SCHEMA = "chummer.rook.bootstrap_ownership_journal.v1"
MAX_BYTES = 256 * 1024
MAX_EVENTS = 128
CONTAINERS = {"ai": "chummer-build-ghost-ai", "edge": "build-ghost-private-edge",
              "ingress": "build-ghost-cloudflare-access-edge",
              "trust-export": "build-ghost-private-trust-export",
              "journal-init": "build-ghost-live-support-store-init"}
VOLUMES = {"caddy-data", "caddy-config", "caddy-trust", "build-ghost-live-support"}
LABEL = "run.chummer.rook-bootstrap."


class JournalError(ValueError):
    """Fixed, public-safe failure code; never embeds supplied values or paths."""


def require(condition, code="invalid-journal-data"):
    if not condition:
        raise JournalError(code)


def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected))


def match(pattern, value):
    return type(value) is str and re.fullmatch(pattern, value) is not None


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def parse(data):
    def invalid(_):
        raise JournalError("invalid-journal-data")
    return json.loads(data, object_pairs_hook=unique_pairs, parse_constant=invalid)


def checkpoint(document):
    return {"transactionId": document["transactionId"], "revision": len(document["events"]),
            "sha256": digest(document)}


def validate_checkpoint(value):
    keys(value, {"transactionId", "revision", "sha256"})
    require(match(r"[0-9a-f]{32}", value["transactionId"]))
    require(type(value["revision"]) is int and 0 <= value["revision"] <= MAX_EVENTS)
    require(match(r"sha256:[0-9a-f]{64}", value["sha256"]))


def absolute(value):
    return (type(value) is str and 0 < len(value) <= 4096 and "\0" not in value
            and value.startswith("/") and ".." not in Path(value).parts and str(Path(value)) == value)


def volume_pin(value, role):
    keys(value, {"name", "createdAt", "mountpoint"})
    require(value["name"] == PROJECT + "_" + role)
    require(match(r"[0-9T:.+Z-]{10,64}", value["createdAt"]))
    require(absolute(value["mountpoint"]))


def validate_baseline(value):
    # Identity binding only. The separate preflight owns structural/runtime
    # checks; this module never substitutes an authority or readiness verdict.
    keys(value, {"presentation", "packetVolume", "privateNetwork", "admittedVolumes"})
    presentation = value["presentation"]
    keys(presentation, {"containerId", "imageId", "name"})
    require(match(r"[0-9a-f]{64}", presentation["containerId"]))
    require(match(r"sha256:[0-9a-f]{64}", presentation["imageId"]))
    require(presentation["name"] == PROJECT + "-chummer-build-ghost-presentation-1")
    volume_pin(value["packetVolume"], "build-ghost-packet-access")
    network = value["privateNetwork"]
    keys(network, {"id", "name"})
    require(match(r"[0-9a-f]{64}", network["id"]) and network["name"] == PROJECT + "_build-ghost-private")
    admitted = value["admittedVolumes"]
    require(type(admitted) is dict and set(admitted) <= {"caddy-data", "caddy-config", "caddy-trust"})
    for role, pin in admitted.items():
        volume_pin(pin, role)


def resource_name(kind, role):
    if kind == "container":
        require(type(role) is str and role in CONTAINERS)
        return PROJECT + "-" + CONTAINERS[role] + "-1"
    require(kind == "volume" and type(role) is str and role in VOLUMES)
    return PROJECT + "_" + role


def ownership(document, intent_id, role):
    return {LABEL + "transaction": document["transactionId"], LABEL + "intent": intent_id,
            LABEL + "admission": document["admissionSha256"], LABEL + "role": role}


def validate_intent(document, state, value):
    keys(value, {"intentId", "kind", "role", "name", "imageId", "labels", "absence"})
    require(match(r"[0-9a-f]{32}", value["intentId"]))
    require(value["name"] == resource_name(value["kind"], value["role"]))
    require(value["labels"] == ownership(document, value["intentId"], value["role"]))
    require(value["intentId"] not in state["resources"])
    require(not any(item["intent"]["name"] == value["name"] for item in state["resources"].values()))
    if value["kind"] == "container":
        require(match(r"sha256:[0-9a-f]{64}", value["imageId"]))
        require(value["imageId"] != document["baseline"]["presentation"]["imageId"])
    else:
        require(value["imageId"] is None and value["role"] not in document["baseline"]["admittedVolumes"])
    keys(value["absence"], {"kind", "name", "querySucceeded", "present"})
    require(value["absence"] == {"kind": value["kind"], "name": value["name"],
                                  "querySucceeded": True, "present": False})
    require(value["absence"]["querySucceeded"] is True and value["absence"]["present"] is False)


def validate_resource(document, intent, value):
    if intent["kind"] == "container":
        keys(value, {"kind", "id", "name", "imageId", "labels"})
        require(match(r"[0-9a-f]{64}", value["id"]))
        require(value["id"] != document["baseline"]["presentation"]["containerId"])
        require(value["imageId"] == intent["imageId"])
    else:
        keys(value, {"kind", "name", "createdAt", "driver", "scope", "options", "mountpoint", "labels"})
        volume_pin({key: value[key] for key in ("name", "createdAt", "mountpoint")}, intent["role"])
        require(value["driver"] == "local" and value["scope"] == "local" and value["options"] in (None, {}))
    require(value["kind"] == intent["kind"] and value["name"] == intent["name"])
    require(value["labels"] == intent["labels"])


def validate_observation(document, intent, observation):
    keys(observation, {"querySucceeded", "present", "resource", "consumers"})
    require(observation["querySucceeded"] is True and type(observation["present"]) is bool)
    validate_resource(document, intent, observation["resource"])
    consumers = observation["consumers"]
    if intent["kind"] == "container":
        require(consumers is None)
    else:
        require(type(consumers) is list and all(match(r"[0-9a-f]{64}", value) for value in consumers))
        require(len(consumers) == len(set(consumers)))


def apply_event(document, state, event):
    kind, data = event["type"], event["data"]
    resources = state["resources"]
    if kind == "intent":
        require(state["phase"] == "recording")
        validate_intent(document, state, data)
        resources[data["intentId"]] = {"intent": copy.deepcopy(data), "state": "intent", "resource": None}
    elif kind == "created":
        require(state["phase"] == "recording")
        keys(data, {"intentId", "observation"})
        require(type(data["intentId"]) is str and data["intentId"] in resources)
        item = resources[data["intentId"]]
        require(item["state"] == "intent")
        observation = data["observation"]
        validate_observation(document, item["intent"], observation)
        require(observation["present"] is True)
        if item["intent"]["kind"] == "volume":
            require(observation["consumers"] == [])
        else:
            require(not any(other["resource"] is not None and other["intent"]["kind"] == "container"
                            and other["resource"]["id"] == observation["resource"]["id"]
                            for other in resources.values()))
        item["resource"] = copy.deepcopy(observation["resource"])
        item["state"] = "created"
    elif kind == "rollback":
        keys(data, {})
        require(state["phase"] == "recording" and all(item["state"] == "created" for item in resources.values()))
        state["phase"] = "rollback"
    elif kind == "removed":
        require(state["phase"] == "rollback")
        keys(data, {"intentId", "observation"})
        require(type(data["intentId"]) is str and data["intentId"] in resources)
        item = resources[data["intentId"]]
        require(item["state"] == "created")
        validate_observation(document, item["intent"], data["observation"])
        require(data["observation"]["present"] is False and data["observation"]["resource"] == item["resource"])
        require(data["observation"]["consumers"] in (None, []))
        item["state"] = "removed"
    elif kind in ("seal", "finish"):
        keys(data, {})
        expected_phase, expected_resource = ("recording", "created") if kind == "seal" else ("rollback", "removed")
        require(state["phase"] == expected_phase and all(item["state"] == expected_resource for item in resources.values()))
        state["phase"] = "sealed" if kind == "seal" else "closed"
    elif kind == "quarantine":
        keys(data, {"reason"})
        require(state["phase"] in ("recording", "rollback") and data["reason"] == "unknown-create-outcome")
        require(any(item["state"] == "intent" for item in resources.values()))
        state["phase"] = "quarantined"
    else:
        raise JournalError("invalid-journal-event")


def replay(document):
    keys(document, {"schema", "transactionId", "admissionSha256", "baseline", "store", "events"})
    require(document["schema"] == SCHEMA and match(r"[0-9a-f]{32}", document["transactionId"]))
    require(match(r"sha256:[0-9a-f]{64}", document["admissionSha256"]))
    validate_baseline(document["baseline"])
    keys(document["store"], {"device", "inode", "lockDevice", "lockInode", "pathSha256"})
    require(all(type(document["store"][key]) is int and document["store"][key] >= 0
                for key in ("device", "inode", "lockDevice", "lockInode")))
    require(match(r"sha256:[0-9a-f]{64}", document["store"]["pathSha256"]))
    require(type(document["events"]) is list and len(document["events"]) <= MAX_EVENTS)
    require(len(canonical(document)) <= MAX_BYTES)
    state = {"phase": "recording", "resources": {}}
    prefix = {**document, "events": []}
    for number, event in enumerate(document["events"], 1):
        keys(event, {"seq", "previousSha256", "type", "data"})
        require(type(event["seq"]) is int and event["seq"] == number)
        require(event["previousSha256"] == digest(prefix))
        apply_event(document, state, event)
        prefix["events"].append(event)
    return state


def guarded(method):
    @functools.wraps(method)
    def call(self, *args, **kwargs):
        require(self._pid == os.getpid(), "inherited-handle-refused")
        with self._mutex:
            require(not self._closed and not self._poisoned, "journal-handle-unavailable")
            return method(self, *args, **kwargs)
    return call


class Journal:
    """Keep this context open across a transaction; do not share across fork.

    The filesystem must support local flock, atomic replace and fsync semantics.
    External checkpoint custody and fresh runtime observations belong to the
    eventual coordinator. This ledger is neither a character journal nor a
    live-support MAC store, provider receipt, or historical deployment attester.
    """

    resource_name = staticmethod(resource_name)

    def __init__(self):
        self._pid = os.getpid()
        self._mutex = threading.RLock()
        self._closed = False
        self._poisoned = False
        self._directory = self._lock = None
        self._document = self._state = self._token = None

    @staticmethod
    def _path(value):
        value = os.fspath(value)
        require(absolute(value), "untrusted-journal-path")
        path = Path(value)
        for item in [*reversed(path.parents), path]:
            require(not stat.S_ISLNK(item.lstat().st_mode), "untrusted-journal-path")
        return path

    @staticmethod
    def _private(info, directory=False):
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600),
                "untrusted-journal-permissions")
        require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), "untrusted-journal-type")
        if not directory:
            require(info.st_nlink == 1, "linked-journal-file")

    def _attach(self, path, create=False):
        self._path_value = self._path(path)
        self._directory = os.open(self._path_value, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self._private(os.fstat(self._directory), True)
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        self._lock = os.open(".lock", flags, 0o600, dir_fd=self._directory)
        self._private(os.fstat(self._lock))
        fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if create:
            os.fsync(self._lock)
        self._paths()

    def _paths(self):
        self._path(self._path_value)
        for fd, info, directory in (
                (self._directory, self._path_value.lstat(), True),
                (self._lock, os.stat(".lock", dir_fd=self._directory, follow_symlinks=False), False)):
            original = os.fstat(fd)
            self._private(info, directory)
            self._private(original, directory)
            require((info.st_dev, info.st_ino) == (original.st_dev, original.st_ino), "journal-path-replaced")

    def _store_binding(self):
        directory, lock = os.fstat(self._directory), os.fstat(self._lock)
        return {"device": directory.st_dev, "inode": directory.st_ino,
                "lockDevice": lock.st_dev, "lockInode": lock.st_ino,
                "pathSha256": digest(str(self._path_value))}

    def _read(self):
        self._paths()
        fd = os.open("journal.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=self._directory)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            self._private(before)
            require(0 < before.st_size <= MAX_BYTES)
            data = stream.read(before.st_size + 1)
            after = os.fstat(stream.fileno())
            signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            require(len(data) == before.st_size and signature(before) == signature(after), "journal-changed")
            current = os.stat("journal.json", dir_fd=self._directory, follow_symlinks=False)
            self._private(current)
            require(signature(current) == signature(after), "journal-changed")
        document = parse(data)
        require(data == canonical(document), "noncanonical-journal")
        state = replay(document)
        self._paths()
        return document, state

    def _check(self, expected):
        validate_checkpoint(expected)
        require(expected == self._token, "stale-checkpoint")
        try:
            document, _ = self._read()
            require(document == self._document, "journal-changed")
            require(checkpoint(document) == self._token, "journal-checkpoint-inconsistent")
        except BaseException as error:
            self._poisoned = True
            if not isinstance(error, Exception):
                raise
            raise JournalError("journal-integrity-uncertain") from None

    def _persist(self, document, state):
        temporary = ".pending-" + uuid.uuid4().hex + ".json"
        fd = None
        created_identity = None
        renamed = False
        try:
            self._paths()
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=self._directory)
            created_info = os.fstat(fd)
            created_identity = (created_info.st_dev, created_info.st_ino)
            data = canonical(document)
            offset = 0
            while offset < len(data):
                count = os.write(fd, data[offset:])
                require(count > 0, "journal-write-incomplete")
                offset += count
            os.fsync(fd)
            os.close(fd)
            fd = None
            os.replace(temporary, "journal.json", src_dir_fd=self._directory, dst_dir_fd=self._directory)
            renamed = True
            os.fsync(self._directory)
            self._paths()
            next_token = checkpoint(document)
            self._document, self._state, self._token = copy.deepcopy(document), copy.deepcopy(state), next_token
        except BaseException as error:
            self._poisoned = True
            if not isinstance(error, Exception):
                raise
            raise JournalError("journal-persistence-uncertain") from None
        finally:
            if fd is not None:
                os.close(fd)
            if created_identity is not None and not renamed:
                try:
                    current = os.stat(temporary, dir_fd=self._directory, follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == created_identity:
                        os.unlink(temporary, dir_fd=self._directory)
                except OSError:
                    pass

    @classmethod
    def create(cls, path, admission_sha256, baseline):
        tx = cls()
        try:
            validate_baseline(baseline)
            require(match(r"sha256:[0-9a-f]{64}", admission_sha256))
            path = Path(path)
            require(absolute(str(path)), "untrusted-journal-path")
            parent = cls._path(path.parent)
            os.mkdir(path, 0o700)  # Existing stores are never overwritten/adopted.
            parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            tx._attach(path, create=True)
            document = {"schema": SCHEMA, "transactionId": uuid.uuid4().hex,
                        "admissionSha256": admission_sha256, "baseline": copy.deepcopy(baseline),
                        "store": tx._store_binding(), "events": []}
            tx._persist(document, replay(document))
            return tx
        except BaseException as error:
            tx.close()
            if not isinstance(error, Exception):
                raise
            raise JournalError("journal-create-refused") from None

    @classmethod
    def open(cls, path, expected_checkpoint, admission_sha256, baseline):
        tx = cls()
        try:
            validate_checkpoint(expected_checkpoint)
            validate_baseline(baseline)
            tx._attach(path)
            document, state = tx._read()
            require(checkpoint(document) == expected_checkpoint, "checkpoint-mismatch-quarantined")
            require(document["store"] == tx._store_binding(), "journal-store-mismatch")
            require(document["admissionSha256"] == admission_sha256 and document["baseline"] == baseline,
                    "binding-mismatch-quarantined")
            tx._document, tx._state, tx._token = document, state, checkpoint(document)
            if any(item["state"] == "intent" for item in state["resources"].values()) and state["phase"] != "quarantined":
                tx._append(tx._token, "quarantine", {"reason": "unknown-create-outcome"})
            return tx
        except BaseException as error:
            tx.close()
            if not isinstance(error, Exception):
                raise
            raise JournalError("journal-open-quarantined") from None

    def _append(self, expected, kind, data):
        self._check(expected)
        candidate = copy.deepcopy(self._document)
        candidate["events"].append({"seq": expected["revision"] + 1,
                                    "previousSha256": expected["sha256"], "type": kind, "data": copy.deepcopy(data)})
        state = replay(candidate)  # Validate the entire state machine before writing.
        self._persist(candidate, state)
        return copy.deepcopy(self._token)

    @property
    @guarded
    def checkpoint(self):
        self._check(self._token)
        return copy.deepcopy(self._token)

    @guarded
    def snapshot(self):
        self._check(self._token)
        return copy.deepcopy({**self._state, "baseline": self._document["baseline"], "checkpoint": self._token,
                              "admissionSha256": self._document["admissionSha256"], "deploymentReady": False})

    @guarded
    def intent(self, expected, *, kind, role, absence, image_id=None):
        intent_id = uuid.uuid4().hex
        value = {"intentId": intent_id, "kind": kind, "role": role, "name": resource_name(kind, role),
                 "imageId": image_id, "labels": ownership(self._document, intent_id, role), "absence": copy.deepcopy(absence)}
        self._append(expected, "intent", value)
        return copy.deepcopy(value)

    @guarded
    def observe_created(self, expected, intent_id, observation):
        return self._append(expected, "created", {"intentId": intent_id, "observation": observation})

    @guarded
    def begin_rollback(self, expected):
        if any(item["state"] == "intent" for item in self._state["resources"].values()):
            return self._append(expected, "quarantine", {"reason": "unknown-create-outcome"})
        return self._append(expected, "rollback", {})

    @guarded
    def confirm_removed(self, expected, intent_id, observation):
        return self._append(expected, "removed", {"intentId": intent_id, "observation": observation})

    @guarded
    def seal(self, expected):
        return self._append(expected, "seal", {})

    @guarded
    def finish_rollback(self, expected):
        return self._append(expected, "finish", {})

    @guarded
    def rollback_plan(self, expected, current_baseline, observations):
        self._check(expected)
        plan = {"status": "quarantined", "checkpoint": copy.deepcopy(self._token), "targets": [],
                "deferredVolumes": [], "absentOwnedResources": [], "executionAuthorized": False,
                "requiresFreshRecheck": True, "deploymentReady": False}
        try:
            require(self._state["phase"] == "rollback")
            validate_baseline(current_baseline)
            require(current_baseline == self._document["baseline"])
            resources = {key: item for key, item in self._state["resources"].items() if item["state"] == "created"}
            keys(observations, resources)
            for intent_id, item in resources.items():
                validate_observation(self._document, item["intent"], observations[intent_id])
                require(observations[intent_id]["resource"] == item["resource"])
            live_containers = {item["resource"]["id"] for intent_id, item in resources.items()
                               if item["intent"]["kind"] == "container" and observations[intent_id]["present"]}
            targets, deferred, absent_ids = [], [], []
            for intent_id, item in reversed(list(resources.items())):
                observation = observations[intent_id]
                if not observation["present"]:
                    require(observation["consumers"] in (None, []))
                    absent_ids.append(intent_id)
                    continue
                if item["intent"]["kind"] == "volume":
                    require(set(observation["consumers"]) <= live_containers)
                    if observation["consumers"]:
                        deferred.append(intent_id)
                        continue
                targets.append({"intentId": intent_id, "resource": copy.deepcopy(item["resource"]),
                                "identitySha256": digest(item["resource"])})
            plan.update(status="candidates-only", targets=targets, deferredVolumes=deferred, absentOwnedResources=absent_ids)
        except Exception:
            # Unknown observations never produce a partial destructive plan.
            pass
        return copy.deepcopy(plan)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._pid == os.getpid():
            # Serialize descriptor lifetime with every owner-process operation.
            # A dir_fd must never become None or get reused during persistence.
            with self._mutex:
                self._close_descriptors()
        else:
            # A fork child must not acquire a possibly inherited locked mutex.
            self._close_descriptors()

    def _close_descriptors(self):
        # Never unlink/recreate the lock inode. Closing (not LOCK_UN) also avoids
        # releasing a parent's shared flock if a forked child closes its copy.
        for attribute in ("_lock", "_directory"):
            fd = getattr(self, attribute, None)
            if fd is not None:
                os.close(fd)
                setattr(self, attribute, None)
        self._closed = True
