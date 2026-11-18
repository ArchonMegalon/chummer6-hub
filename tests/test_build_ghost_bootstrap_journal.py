"""Host-local journal tests: synthetic metadata/files only, never a Docker daemon."""

import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "ops/build-ghost-private-nonprod/rook_bootstrap_journal.py"
PROJECT = "chummer-build-ghost-private-nonprod"
ADMISSION = "sha256:" + "a" * 64
AI_IMAGE = "sha256:" + "b" * 64
NEW_ID = "4" * 64


@pytest.fixture
def journal_module():
    spec = importlib.util.spec_from_file_location("rook_bootstrap_journal", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def baseline():
    packet = PROJECT + "_build-ghost-packet-access"
    return {
        "presentation": {"containerId": "1" * 64, "imageId": "sha256:" + "2" * 64,
                         "name": PROJECT + "-chummer-build-ghost-presentation-1"},
        "packetVolume": {"name": packet, "createdAt": "2026-08-22T10:00:00Z",
                         "mountpoint": "/var/lib/docker/volumes/" + packet + "/_data"},
        "privateNetwork": {"id": "3" * 64, "name": PROJECT + "_build-ghost-private"},
        "admittedVolumes": {},
    }


def absent(kind, name):
    return {"kind": kind, "name": name, "querySucceeded": True, "present": False}


def create_intent(tx, kind="container", role="ai", image=AI_IMAGE):
    name = tx.resource_name(kind, role)
    return tx.intent(tx.checkpoint, kind=kind, role=role,
                     absence=absent(kind, name), image_id=image if kind == "container" else None)


def observed(intent, *, resource_id=NEW_ID):
    if intent["kind"] == "container":
        resource = {"kind": "container", "id": resource_id, "name": intent["name"],
                    "imageId": intent["imageId"], "labels": copy.deepcopy(intent["labels"])}
        consumers = None
    else:
        resource = {"kind": "volume", "name": intent["name"], "createdAt": "2026-09-09T10:00:00Z",
                    "driver": "local", "scope": "local", "options": None,
                    "mountpoint": "/var/lib/docker/volumes/" + intent["name"] + "/_data",
                    "labels": copy.deepcopy(intent["labels"])}
        consumers = []
    return {"querySucceeded": True, "present": True, "resource": resource, "consumers": consumers}


def add_container(tx, role="ai", resource_id=NEW_ID):
    intent = create_intent(tx, role=role)
    observation = observed(intent, resource_id=resource_id)
    tx.observe_created(tx.checkpoint, intent["intentId"], observation)
    return intent, observation


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def checkpoint(document):
    return {"transactionId": document["transactionId"], "revision": len(document["events"]),
            "sha256": "sha256:" + hashlib.sha256(encode(document)).hexdigest()}


def test_records_exact_baseline_and_unique_ownership_without_runtime_authority(journal_module, tmp_path, capsys):
    j = journal_module
    original = baseline()
    with j.Journal.create(tmp_path / "journal", ADMISSION, original) as tx:
        start = tx.checkpoint
        assert start["revision"] == 0
        intent, observation = add_container(tx)
        assert tx.checkpoint["revision"] == 2
        assert intent["labels"]["run.chummer.rook-bootstrap.transaction"] == start["transactionId"]
        assert intent["labels"]["run.chummer.rook-bootstrap.intent"] == intent["intentId"]
        assert intent["labels"]["run.chummer.rook-bootstrap.admission"] == ADMISSION
        state = tx.snapshot()
        assert state["phase"] == "recording"
        assert state["baseline"] == original
        assert state["resources"][intent["intentId"]]["resource"] == observation["resource"]
        assert state["deploymentReady"] is False
        saved = tx.checkpoint
    with j.Journal.open(tmp_path / "journal", saved, ADMISSION, original) as tx:
        assert tx.checkpoint == saved
    assert capsys.readouterr() == ("", "")


def test_exact_owned_container_rollback_plan_never_executes(journal_module, tmp_path):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        intent, observation = add_container(tx)
        tx.begin_rollback(tx.checkpoint)
        plan = tx.rollback_plan(tx.checkpoint, baseline(), {intent["intentId"]: observation})
        assert plan["status"] == "candidates-only"
        assert plan["executionAuthorized"] is False
        assert plan["requiresFreshRecheck"] is True
        assert len(plan["targets"]) == 1
        assert plan["targets"][0]["resource"] == observation["resource"]
        assert plan["targets"][0]["intentId"] == intent["intentId"]
        assert "command" not in plan["targets"][0]


@pytest.mark.parametrize("kind,role", (("container", "presentation"), ("network", "private"), ("image", "ai"),
                                      ("volume", "build-ghost-packet-access"), ("container", "other")))
def test_never_admits_retained_or_unbounded_resource_roles(journal_module, tmp_path, kind, role):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        with pytest.raises(journal_module.JournalError):
            create_intent(tx, kind, role)
        assert tx.checkpoint["revision"] == 0


def test_never_admits_existing_caddy_volume(journal_module, tmp_path):
    original = baseline()
    name = PROJECT + "_caddy-data"
    original["admittedVolumes"]["caddy-data"] = {
        "name": name, "createdAt": "2026-08-22T10:00:00Z",
        "mountpoint": "/var/lib/docker/volumes/" + name + "/_data"}
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, original) as tx:
        with pytest.raises(journal_module.JournalError):
            create_intent(tx, "volume", "caddy-data")


@pytest.mark.parametrize("field,value", (("present", True), ("querySucceeded", False), ("kind", "volume"),
                                         ("name", "other")))
def test_creation_intent_requires_explicit_successful_absence(journal_module, tmp_path, field, value):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        evidence = absent("container", tx.resource_name("container", "ai"))
        evidence[field] = value
        with pytest.raises(journal_module.JournalError):
            tx.intent(tx.checkpoint, kind="container", role="ai", absence=evidence, image_id=AI_IMAGE)


@pytest.mark.parametrize("mutation", ("retained-id", "wrong-label", "wrong-image", "wrong-name", "query-error", "not-present"))
def test_observation_rejects_ownership_or_identity_mismatch(journal_module, tmp_path, mutation):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        intent = create_intent(tx)
        observation = observed(intent)
        if mutation == "retained-id":
            observation["resource"]["id"] = baseline()["presentation"]["containerId"]
        elif mutation == "wrong-label":
            observation["resource"]["labels"]["run.chummer.rook-bootstrap.transaction"] = "f" * 32
        elif mutation == "wrong-image":
            observation["resource"]["imageId"] = "mutable:latest"
        elif mutation == "wrong-name":
            observation["resource"]["name"] = baseline()["presentation"]["name"]
        elif mutation == "query-error":
            observation["querySucceeded"] = False
        else:
            observation["present"] = False
        with pytest.raises(journal_module.JournalError):
            tx.observe_created(tx.checkpoint, intent["intentId"], observation)
        assert tx.checkpoint["revision"] == 1


def test_reopen_pending_create_quarantines_all_cleanup(journal_module, tmp_path):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        known, observation = add_container(tx)
        create_intent(tx, role="edge")
        saved = tx.checkpoint
    with journal_module.Journal.open(path, saved, ADMISSION, baseline()) as tx:
        assert tx.snapshot()["phase"] == "quarantined"
        assert tx.checkpoint["revision"] == saved["revision"] + 1
        plan = tx.rollback_plan(tx.checkpoint, baseline(), {known["intentId"]: observation})
        assert plan["status"] == "quarantined" and plan["targets"] == []
        with pytest.raises(journal_module.JournalError):
            create_intent(tx, role="ingress")


def test_rollback_with_unknown_create_never_guesses(journal_module, tmp_path):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        create_intent(tx)
        tx.begin_rollback(tx.checkpoint)
        assert tx.snapshot()["phase"] == "quarantined"
        assert tx.rollback_plan(tx.checkpoint, baseline(), {})["targets"] == []


def test_stale_cas_and_duplicate_observation_are_rejected(journal_module, tmp_path):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        old = tx.checkpoint
        intent, observation = add_container(tx)
        with pytest.raises(journal_module.JournalError):
            tx.begin_rollback(old)
        with pytest.raises(journal_module.JournalError):
            tx.observe_created(tx.checkpoint, intent["intentId"], observation)
        with pytest.raises(journal_module.JournalError):
            create_intent(tx)


def test_duplicate_created_id_is_rejected(journal_module, tmp_path):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        add_container(tx)
        other = create_intent(tx, role="edge")
        with pytest.raises(journal_module.JournalError):
            tx.observe_created(tx.checkpoint, other["intentId"], observed(other))


@pytest.mark.parametrize("mutation", ("missing", "query-error", "label", "id", "baseline"))
def test_rollback_requires_complete_fresh_matching_observations(journal_module, tmp_path, mutation):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        intent, observation = add_container(tx)
        tx.begin_rollback(tx.checkpoint)
        current = {intent["intentId"]: observation}
        original = baseline()
        if mutation == "missing":
            current = {}
        elif mutation == "query-error":
            observation["querySucceeded"] = False
        elif mutation == "label":
            observation["resource"]["labels"] = {}
        elif mutation == "id":
            observation["resource"]["id"] = "f" * 64
        else:
            original["privateNetwork"]["id"] = "f" * 64
        plan = tx.rollback_plan(tx.checkpoint, original, current)
        assert plan["status"] == "quarantined" and plan["targets"] == []


def test_volume_plan_requires_no_consumers_and_defers_until_owned_container_gone(journal_module, tmp_path):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        vol = create_intent(tx, "volume", "build-ghost-live-support")
        vol_observation = observed(vol)
        tx.observe_created(tx.checkpoint, vol["intentId"], vol_observation)
        container, container_observation = add_container(tx)
        tx.begin_rollback(tx.checkpoint)
        vol_observation["consumers"] = [NEW_ID]
        current = {container["intentId"]: container_observation, vol["intentId"]: vol_observation}
        plan = tx.rollback_plan(tx.checkpoint, baseline(), current)
        assert [item["resource"]["kind"] for item in plan["targets"]] == ["container"]
        assert plan["deferredVolumes"] == [vol["intentId"]]
        gone = copy.deepcopy(container_observation)
        gone["present"] = False
        tx.confirm_removed(tx.checkpoint, container["intentId"], gone)
        vol_observation["consumers"] = []
        plan = tx.rollback_plan(tx.checkpoint, baseline(), {vol["intentId"]: vol_observation})
        assert len(plan["targets"]) == 1
        assert plan["targets"][0]["resource"] == vol_observation["resource"]


@pytest.mark.parametrize("consumers", (None, ["f" * 64], ["bad-id"], False))
def test_unknown_or_foreign_volume_consumers_quarantine(journal_module, tmp_path, consumers):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        intent = create_intent(tx, "volume", "caddy-trust")
        observation = observed(intent)
        tx.observe_created(tx.checkpoint, intent["intentId"], observation)
        tx.begin_rollback(tx.checkpoint)
        observation["consumers"] = consumers
        plan = tx.rollback_plan(tx.checkpoint, baseline(), {intent["intentId"]: observation})
        assert plan["status"] == "quarantined" and plan["targets"] == []


def test_closed_and_sealed_are_monotonic_not_readiness(journal_module, tmp_path):
    with journal_module.Journal.create(tmp_path / "sealed", ADMISSION, baseline()) as tx:
        add_container(tx)
        tx.seal(tx.checkpoint)
        assert tx.snapshot()["phase"] == "sealed"
        assert tx.snapshot()["deploymentReady"] is False
        with pytest.raises(journal_module.JournalError):
            tx.begin_rollback(tx.checkpoint)
        with pytest.raises(journal_module.JournalError):
            create_intent(tx, role="edge")
    with journal_module.Journal.create(tmp_path / "closed", ADMISSION, baseline()) as tx:
        intent, observation = add_container(tx)
        tx.begin_rollback(tx.checkpoint)
        with pytest.raises(journal_module.JournalError):
            tx.finish_rollback(tx.checkpoint)
        observation["present"] = False
        tx.confirm_removed(tx.checkpoint, intent["intentId"], observation)
        tx.finish_rollback(tx.checkpoint)
        assert tx.snapshot()["phase"] == "closed"
        with pytest.raises(journal_module.JournalError):
            tx.confirm_removed(tx.checkpoint, intent["intentId"], observation)


@pytest.mark.parametrize("mismatch", ("checkpoint", "admission", "baseline"))
def test_external_binding_mismatch_is_never_self_healed(journal_module, tmp_path, mismatch):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        old = tx.checkpoint
        add_container(tx)
        saved = tx.checkpoint
    admission, original = ADMISSION, baseline()
    if mismatch == "checkpoint":
        saved = old
    elif mismatch == "admission":
        admission = "sha256:" + "f" * 64
    else:
        original["presentation"]["imageId"] = "sha256:" + "f" * 64
    with pytest.raises(journal_module.JournalError):
        journal_module.Journal.open(path, saved, admission, original)


def test_replayed_older_snapshot_rejected_by_external_checkpoint(journal_module, tmp_path):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        old_bytes = (path / "journal.json").read_bytes()
        add_container(tx)
        saved = tx.checkpoint
    (path / "journal.json").write_bytes(old_bytes)
    with pytest.raises(journal_module.JournalError):
        journal_module.Journal.open(path, saved, ADMISSION, baseline())


@pytest.mark.parametrize("mutation", ("unknown-key", "bad-sequence", "bad-previous", "observe-before-intent", "duplicate-key"))
def test_malformed_or_semantically_invalid_event_history_rejected(journal_module, tmp_path, mutation):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        add_container(tx)
        saved = tx.checkpoint
    document = json.loads((path / "journal.json").read_bytes())
    if mutation == "unknown-key":
        document["secret"] = "synthetic-do-not-print"
    elif mutation == "bad-sequence":
        document["events"][0]["seq"] = 99
    elif mutation == "bad-previous":
        document["events"][0]["previousSha256"] = "sha256:" + "f" * 64
    elif mutation == "observe-before-intent":
        document["events"][0]["type"] = "created"
    data = encode(document)
    if mutation == "duplicate-key":
        data = data[:-1] + b',"schema":"duplicate"}'
    else:
        saved = checkpoint(document)
    (path / "journal.json").write_bytes(data)
    with pytest.raises(journal_module.JournalError):
        journal_module.Journal.open(path, saved, ADMISSION, baseline())


@pytest.mark.parametrize("target", ("journal.json", ".lock"))
@pytest.mark.parametrize("mode", (0o644, 0o660))
def test_private_file_permissions_required(journal_module, tmp_path, target, mode):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
    (path / target).chmod(mode)
    with pytest.raises(journal_module.JournalError):
        journal_module.Journal.open(path, saved, ADMISSION, baseline())


def test_directory_and_lock_replacement_poison_existing_handle(journal_module, tmp_path):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
        (path / ".lock").rename(path / "old-lock")
        (path / ".lock").write_bytes(b"")
        (path / ".lock").chmod(0o600)
        with pytest.raises(journal_module.JournalError):
            tx.begin_rollback(saved)
        with pytest.raises(journal_module.JournalError):
            tx.snapshot()


def child_code():
    return """import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('journal',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
path,cp,admission,original=sys.argv[2],json.loads(sys.argv[3]),sys.argv[4],json.loads(sys.argv[5])
"""


def child_args(path, saved):
    return ["/usr/bin/python3", "-I", "-c", "", str(MODULE), str(path), json.dumps(saved), ADMISSION, json.dumps(baseline())]


def test_cross_process_exclusion_and_lock_inode_stability(journal_module, tmp_path):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
        inode = (path / ".lock").stat().st_ino
        args = child_args(path, saved)
        args[3] = child_code() + "\ntry: m.Journal.open(path,cp,admission,original)\nexcept m.JournalError: print('blocked')\nelse: raise SystemExit(91)\n"
        child = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
        assert child.returncode == 0 and child.stdout == "blocked\n", child.stderr
    with journal_module.Journal.open(path, saved, ADMISSION, baseline()):
        assert (path / ".lock").stat().st_ino == inode


def test_threaded_cas_has_exactly_one_winner(journal_module, tmp_path):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
        def change(role):
            try:
                tx.intent(saved, kind="container", role=role,
                          absence=absent("container", tx.resource_name("container", role)), image_id=AI_IMAGE)
                return True
            except journal_module.JournalError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(change, ("ai", "edge"))) == [False, True]
        assert tx.checkpoint["revision"] == 1


@pytest.mark.parametrize("failure", ("write", "file-fsync", "replace", "directory-fsync"))
def test_uncertain_persistence_poisons_handle(journal_module, tmp_path, monkeypatch, failure):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
        original_fsync = os.fsync
        def fsync(fd):
            is_directory = os.path.isdir("/proc/self/fd/" + str(fd))
            if (failure == "file-fsync" and not is_directory) or (failure == "directory-fsync" and is_directory):
                raise OSError("synthetic failure")
            return original_fsync(fd)
        with monkeypatch.context() as patch:
            if failure in ("file-fsync", "directory-fsync"):
                patch.setattr(journal_module.os, "fsync", fsync)
            elif failure == "write":
                patch.setattr(journal_module.os, "write", lambda *args: (_ for _ in ()).throw(OSError("synthetic")))
            else:
                patch.setattr(journal_module.os, "replace", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("synthetic")))
            with pytest.raises(journal_module.JournalError):
                create_intent(tx)
        with pytest.raises(journal_module.JournalError):
            tx.rollback_plan(saved, baseline(), {})
        assert isinstance(json.loads((tmp_path / "journal/journal.json").read_bytes()), dict)


def test_process_crash_after_replace_leaves_complete_snapshot_but_old_checkpoint_rejected(journal_module, tmp_path):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
    args = child_args(path, saved)
    args[3] = child_code() + """
import os
tx=m.Journal.open(path,cp,admission,original)
replace=os.replace
def crash(*args,**kwargs):
    replace(*args,**kwargs)
    os._exit(17)
os.replace=crash
name=tx.resource_name('container','ai')
tx.intent(cp,kind='container',role='ai',absence={'kind':'container','name':name,'querySucceeded':True,'present':False},image_id='sha256:'+'b'*64)
"""
    child = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
    assert child.returncode == 17, child.stderr
    assert len(json.loads((path / "journal.json").read_bytes())["events"]) == 1
    with pytest.raises(journal_module.JournalError):
        journal_module.Journal.open(path, saved, ADMISSION, baseline())


def test_nested_input_and_output_mutation_cannot_rewrite_journal(journal_module, tmp_path):
    path = tmp_path / "journal"
    original = baseline()
    with journal_module.Journal.create(path, ADMISSION, original) as tx:
        original["presentation"]["containerId"] = "f" * 64
        intent = create_intent(tx)
        original_intent = copy.deepcopy(intent)
        observation = observed(intent)
        tx.observe_created(tx.checkpoint, intent["intentId"], observation)
        intent["labels"].clear()
        observation["resource"]["id"] = "f" * 64
        tx.begin_rollback(tx.checkpoint)
        plan = tx.rollback_plan(tx.checkpoint, baseline(), {intent["intentId"]: observed(original_intent)})
        plan["targets"][0]["resource"]["labels"].clear()
        returned = tx.snapshot()
        returned["baseline"]["presentation"]["containerId"] = "f" * 64
        saved = tx.checkpoint
    with journal_module.Journal.open(path, saved, ADMISSION, baseline()) as tx:
        assert tx.snapshot()["resources"][intent["intentId"]]["resource"] == observed(original_intent)["resource"]


def test_module_has_no_subprocess_network_or_provider_execution(journal_module):
    source = MODULE.read_text()
    assert "import subprocess" not in source
    assert "import socket" not in source
    assert "Config.Env" not in source
    assert "docker compose" not in source


def test_concurrent_close_waits_for_persistence_and_never_falls_back_to_cwd(journal_module, tmp_path, monkeypatch):
    cwd = tmp_path / "unrelated-cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    tx = journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline())
    saved = tx.checkpoint
    writing, release, closed = threading.Event(), threading.Event(), threading.Event()
    original_write = os.write
    def pause_write(fd, data):
        writing.set()
        assert release.wait(3)
        return original_write(fd, data)
    def close():
        tx.close()
        closed.set()
    monkeypatch.setattr(journal_module.os, "write", pause_write)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(tx.begin_rollback, saved)
            assert writing.wait(2)
            closer = pool.submit(close)
            try:
                assert not closed.wait(0.1), "close released descriptors during an active write"
            finally:
                release.set()
            writer.result(timeout=3)
            closer.result(timeout=3)
        assert list(cwd.iterdir()) == []
        assert json.loads((tmp_path / "journal/journal.json").read_bytes())["events"][-1]["type"] == "rollback"
    finally:
        tx.close()


def test_copied_store_cannot_replay_same_transaction_under_a_second_lock(journal_module, tmp_path):
    original = tmp_path / "journal"
    with journal_module.Journal.create(original, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
    clone = tmp_path / "clone"
    shutil.copytree(original, clone)
    with pytest.raises(journal_module.JournalError):
        journal_module.Journal.open(clone, saved, ADMISSION, baseline())


@pytest.mark.parametrize("interrupt", (KeyboardInterrupt, SystemExit))
def test_interrupt_after_persistence_cannot_expose_new_state_under_old_checkpoint(journal_module, tmp_path, monkeypatch, interrupt):
    with journal_module.Journal.create(tmp_path / "journal", ADMISSION, baseline()) as tx:
        intent, observation = add_container(tx)
        old = tx.checkpoint
        original_checkpoint = journal_module.checkpoint
        def interrupted_checkpoint(document):
            if document["events"][-1]["type"] == "rollback":
                raise interrupt()
            return original_checkpoint(document)
        with monkeypatch.context() as patch:
            patch.setattr(journal_module, "checkpoint", interrupted_checkpoint)
            with pytest.raises(interrupt):
                tx.begin_rollback(old)
        assert tx._poisoned is True
        with pytest.raises(journal_module.JournalError):
            tx.rollback_plan(old, baseline(), {intent["intentId"]: observation})


def test_replaced_lock_cannot_open_second_handle_under_original_checkpoint(journal_module, tmp_path):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
        (path / ".lock").rename(path / "retained-old-lock")
        (path / ".lock").write_bytes(b"")
        (path / ".lock").chmod(0o600)
        with pytest.raises(journal_module.JournalError):
            with journal_module.Journal.open(path, saved, ADMISSION, baseline()):
                pass


def test_temp_name_collision_never_deletes_a_file_this_attempt_did_not_create(journal_module, tmp_path, monkeypatch):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
        pending = path / (".pending-" + "f" * 32 + ".json")
        pending.write_bytes(b"retained-synthetic-collision-evidence")
        pending.chmod(0o600)
        monkeypatch.setattr(journal_module.uuid, "uuid4", lambda: SimpleNamespace(hex="f" * 32))
        with pytest.raises(journal_module.JournalError):
            tx.begin_rollback(saved)
        assert pending.exists()
        assert pending.read_bytes() == b"retained-synthetic-collision-evidence"


def test_interrupted_open_releases_unreturned_handle_lock(journal_module, tmp_path, monkeypatch):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
    with monkeypatch.context() as patch:
        patch.setattr(journal_module.Journal, "_read", lambda self: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            journal_module.Journal.open(path, saved, ADMISSION, baseline())
    with journal_module.Journal.open(path, saved, ADMISSION, baseline()):
        pass


def test_interrupted_create_releases_unreturned_handle_lock(journal_module, tmp_path, monkeypatch):
    path = tmp_path / "journal"
    with monkeypatch.context() as patch:
        patch.setattr(journal_module, "replay", lambda document: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            journal_module.Journal.create(path, ADMISSION, baseline())
    with (path / ".lock").open("rb") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (path / "journal.json").exists()


@pytest.mark.parametrize("target", (".lock", "journal.json"))
@pytest.mark.parametrize("link_type", ("symlink", "hardlink"))
def test_linked_files_are_never_adopted(journal_module, tmp_path, target, link_type):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
    original = path / target
    retained = path / (target + ".retained")
    if link_type == "symlink":
        original.rename(retained)
        original.symlink_to(retained)
    else:
        os.link(original, retained)
    with pytest.raises(journal_module.JournalError):
        journal_module.Journal.open(path, saved, ADMISSION, baseline())
    assert retained.exists()


def test_relocated_live_directory_poisoned_without_cwd_fallback(journal_module, tmp_path):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
        path.rename(tmp_path / "retained-renamed-journal")
        with pytest.raises(journal_module.JournalError):
            tx.begin_rollback(saved)
        assert tx._poisoned


def test_create_refuses_existing_store_without_overwriting(journal_module, tmp_path):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
    data = (path / "journal.json").read_bytes()
    with pytest.raises(journal_module.JournalError):
        journal_module.Journal.create(path, ADMISSION, baseline())
    assert (path / "journal.json").read_bytes() == data
    with journal_module.Journal.open(path, saved, ADMISSION, baseline()):
        pass


def test_rehashed_terminal_event_replay_still_rejects_state_machine_violation(journal_module, tmp_path):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        add_container(tx)
        tx.seal(tx.checkpoint)
    document = json.loads((path / "journal.json").read_bytes())
    document["events"].append({"seq": len(document["events"]) + 1,
                                "previousSha256": checkpoint(document)["sha256"],
                                "type": "rollback", "data": {}})
    (path / "journal.json").write_bytes(encode(document))
    with pytest.raises(journal_module.JournalError):
        journal_module.Journal.open(path, checkpoint(document), ADMISSION, baseline())


def test_process_crash_before_replace_keeps_old_checkpoint_and_does_not_promote_pending_file(journal_module, tmp_path):
    path = tmp_path / "journal"
    with journal_module.Journal.create(path, ADMISSION, baseline()) as tx:
        saved = tx.checkpoint
    args = child_args(path, saved)
    args[3] = child_code() + """
import os
tx=m.Journal.open(path,cp,admission,original)
def crash(*args,**kwargs): os._exit(19)
os.replace=crash
tx.begin_rollback(cp)
"""
    child = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
    assert child.returncode == 19, child.stderr
    assert any(item.name.startswith(".pending-") for item in path.iterdir())
    with journal_module.Journal.open(path, saved, ADMISSION, baseline()) as tx:
        assert tx.snapshot()["phase"] == "recording"
        assert tx.checkpoint == saved
