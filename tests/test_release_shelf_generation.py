from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_shelf_generation.py"
SPEC = importlib.util.spec_from_file_location("release_shelf_generation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_project_manifest_pair_binds_exact_generation_without_copying_artifacts(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    compatibility_path = tmp_path / "releases.json"
    source = {
        "version": "run-20260720-nightly",
        "channel": "preview",
        "publishedAt": "2026-07-20T20:00:00Z",
        "downloads": [
            {
                "id": "avalonia-osx-arm64",
                "fileName": "chummer.dmg",
                "url": "/downloads/files/chummer.dmg",
                "installAccessClass": "open_public",
            }
        ],
    }
    canonical_path.write_text(json.dumps(source), encoding="utf-8")
    compatibility_path.write_text(json.dumps(source), encoding="utf-8")

    receipt = MODULE.project_manifest_pair(
        canonical_path,
        compatibility_path,
        "gen-run-20260720-nightly-abcdef0123456789",
    )

    expected_route = (
        "/downloads/g/gen-run-20260720-nightly-abcdef0123456789/"
        "files/chummer.dmg"
    )
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
    assert canonical == compatibility
    assert canonical["generationId"] == receipt["generationId"]
    assert canonical["downloads"][0]["url"] == expected_route
    assert receipt["canonicalManifestSha256"] == MODULE.sha256_file(canonical_path)
    assert receipt["compatibilityManifestSha256"] == MODULE.sha256_file(
        compatibility_path
    )
    assert not list(tmp_path.glob(".*.generation-*"))


def test_project_manifest_pair_rejects_release_identity_drift_without_mutation(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    compatibility_path = tmp_path / "releases.json"
    canonical_path.write_text(
        json.dumps(
            {
                "version": "run-one",
                "channel": "preview",
                "publishedAt": "2026-07-20T20:00:00Z",
                "downloads": [],
            }
        ),
        encoding="utf-8",
    )
    compatibility_path.write_text(
        json.dumps(
            {
                "version": "run-two",
                "channel": "preview",
                "publishedAt": "2026-07-20T20:00:00Z",
                "downloads": [],
            }
        ),
        encoding="utf-8",
    )
    before = (canonical_path.read_bytes(), compatibility_path.read_bytes())

    with pytest.raises(MODULE.ReleaseShelfError, match="same release identity"):
        MODULE.project_manifest_pair(
            canonical_path,
            compatibility_path,
            "gen-release-identity-drift",
        )

    assert (canonical_path.read_bytes(), compatibility_path.read_bytes()) == before


def install_fake_conditional_s3_cli(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_aws = fake_bin / "aws"
    fake_aws.write_text(
        """#!/usr/bin/env python3
import fcntl
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

remote = Path(os.environ["FAKE_AWS_ROOT"])
public = Path(os.environ["FAKE_PUBLIC_ROOT"])
latest_public = Path(os.environ["FAKE_LATEST_PUBLIC_ROOT"])
log = Path(os.environ["FAKE_AWS_LOG"])
args = sys.argv[1:]
remote.mkdir(parents=True, exist_ok=True)

def option(name):
    return args[args.index(name) + 1]

def s3_path(uri):
    raw = uri[len("s3://"):]
    bucket, _, key = raw.partition("/")
    return remote / bucket / key, bucket, key

def etag(path):
    return '"' + hashlib.sha256(path.read_bytes()).hexdigest() + '"'

def record(text):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(text + "\\n")
        handle.flush()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

def mirror_public(source, key):
    target = None
    if "/generations/" in key:
        prefix, relative = key.split("/generations/", 1)
        generation_id, _, generation_relative = relative.partition("/")
        if prefix == "downloads":
            target = public / "g" / generation_id / generation_relative
        elif prefix == "latest":
            target = latest_public / "g" / generation_id / generation_relative
    elif key == "downloads/current.json":
        target = public / "current.json"
    elif key == "latest/current.json":
        target = latest_public / "current.json"
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + f".tmp-{os.getpid()}")
        shutil.copy2(source, temp)
        os.replace(temp, target)

if args[:2] == ["s3api", "head-object"]:
    bucket = option("--bucket")
    key = option("--key")
    path = remote / bucket / key
    record(f"HEAD {key}")
    if not path.is_file():
        raise SystemExit(255)
    metadata_path = Path(str(path) + ".metadata.json")
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    print(json.dumps({"ContentLength": path.stat().st_size, "Metadata": metadata, "ETag": etag(path)}))
    raise SystemExit(0)

if args[:2] == ["s3api", "list-objects-v2"]:
    bucket = option("--bucket")
    prefix = option("--prefix")
    max_keys = int(option("--max-keys"))
    bucket_root = remote / bucket
    inject_key = os.environ.get("FAKE_AWS_INJECT_ON_SECOND_ROOT_LIST", "")
    inject_prefix = os.environ.get("FAKE_AWS_ROOT_INVENTORY_PREFIX", "downloads")
    if inject_key and prefix == inject_prefix:
        counter_path = remote / ".root-inventory-count"
        with counter_path.open("a+b") as counter:
            fcntl.flock(counter.fileno(), fcntl.LOCK_EX)
            counter.seek(0)
            raw_count = counter.read().decode("ascii")
            count = int(raw_count or "0") + 1
            counter.seek(0)
            counter.truncate()
            counter.write(str(count).encode("ascii"))
            counter.flush()
            if count == 2:
                injected = remote / bucket / inject_key
                injected.parent.mkdir(parents=True, exist_ok=True)
                injected.write_bytes(b"concurrent legacy object")
            fcntl.flock(counter.fileno(), fcntl.LOCK_UN)
    contents = []
    if bucket_root.is_dir():
        for child in sorted(bucket_root.rglob("*")):
            if not child.is_file() or child.name.endswith(".metadata.json") or ".tmp-" in child.name:
                continue
            key = child.relative_to(bucket_root).as_posix()
            if key.startswith(prefix):
                contents.append({"Key": key})
    record(f"LIST {prefix}")
    selected = contents[:max_keys]
    print(json.dumps({
        "Contents": selected,
        "IsTruncated": len(contents) > len(selected),
        "KeyCount": len(selected),
    }))
    raise SystemExit(0)

if args[:2] == ["s3api", "put-object"]:
    bucket = option("--bucket")
    key = option("--key")
    source = Path(option("--body"))
    destination = remote / bucket / key
    fail_prefix = os.environ.get("FAKE_AWS_FAIL_PUT_PREFIX", "")
    if fail_prefix and key.startswith(fail_prefix):
        record(f"PUT_FAIL {key}")
        raise SystemExit(42)
    delay_ms = int(os.environ.get("FAKE_AWS_PUT_DELAY_MS", "0"))
    if delay_ms:
        time.sleep(delay_ms / 1000)
    lock_path = remote / ".conditional-put.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if "--if-none-match" in args and destination.exists():
            record(f"PUT_CONDITION_FAILED {key}")
            raise SystemExit(255)
        if "--if-match" in args:
            expected = option("--if-match")
            if not destination.is_file() or etag(destination) != expected:
                record(f"PUT_CONDITION_FAILED {key}")
                raise SystemExit(255)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_name(destination.name + f".tmp-{os.getpid()}")
        shutil.copy2(source, temp)
        os.replace(temp, destination)
        metadata = {}
        if "--metadata" in args:
            raw = option("--metadata")
            metadata = dict(item.split("=", 1) for item in raw.split(",") if "=" in item)
        metadata_path = Path(str(destination) + ".metadata.json")
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        record(f"PUT {key}")
        mirror_public(destination, key)
        response_etag = etag(destination)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    print(json.dumps({"ETag": response_etag}))
    raise SystemExit(0)

if args[:2] == ["s3", "cp"]:
    source, destination = args[2], args[3]
    if not source.startswith("s3://"):
        raise SystemExit(f"legacy upload is forbidden in fake conditional S3: {args}")
    source_path, _, key = s3_path(source)
    if key == os.environ.get("FAKE_AWS_FAIL_GET_KEY", ""):
        record(f"GET_FAIL {key}")
        raise SystemExit(43)
    record(f"GET {key}")
    if not source_path.is_file():
        raise SystemExit(1)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    raise SystemExit(0)

raise SystemExit(f"unsupported fake aws invocation: {args}")
""",
        encoding="utf-8",
    )
    fake_aws.chmod(0o755)
    remote_root = tmp_path / "remote"
    public_root = tmp_path / "public"
    latest_public_root = tmp_path / "latest-public"
    log_path = tmp_path / "aws.log"
    return fake_bin, remote_root, public_root, latest_public_root, log_path


def write_s3_publish_bundle(
    root: Path,
    *,
    version: str,
    published_at: str,
    payload: bytes,
) -> Path:
    files = root / "files"
    files.mkdir(parents=True)
    artifact = files / "chummer-avalonia-osx-arm64-installer.dmg"
    artifact.write_bytes(payload)
    digest = MODULE.sha256_file(artifact)
    canonical = {
        "version": version,
        "releaseVersion": version,
        "channel": "preview",
        "publishedAt": published_at,
        "artifacts": [
            {
                "artifactId": "avalonia-osx-arm64-installer",
                "head": "avalonia",
                "platform": "macos",
                "rid": "osx-arm64",
                "kind": "dmg",
                "fileName": artifact.name,
                "downloadUrl": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
            }
        ],
    }
    compatibility = {
        "version": version,
        "channel": "preview",
        "publishedAt": published_at,
        "downloads": [
            {
                "id": "avalonia-osx-arm64-installer",
                "head": "avalonia",
                "platformId": "macos",
                "rid": "osx-arm64",
                "kind": "dmg",
                "fileName": artifact.name,
                "url": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
            }
        ],
    }
    (root / MODULE.CANONICAL_MANIFEST).write_text(
        json.dumps(canonical, indent=2) + "\n", encoding="utf-8"
    )
    (root / MODULE.COMPATIBILITY_MANIFEST).write_text(
        json.dumps(compatibility, indent=2) + "\n", encoding="utf-8"
    )
    return root


def test_inventory_digest_matches_cross_language_golden_fixture() -> None:
    fixture = json.loads(
        (
            ROOT
            / "tests"
            / "fixtures"
            / "atomic_release_shelf_inventory_digest_v1.json"
        ).read_text(encoding="utf-8")
    )

    canonical = MODULE.canonical_json_bytes(fixture["inventory"])

    assert canonical == fixture["canonicalJson"].encode("utf-8")
    assert MODULE.inventory_digest(fixture["inventory"]) == fixture["sha256"]


def test_inventory_rejects_nonportable_unicode_paths_before_activation(tmp_path: Path) -> None:
    generation = tmp_path / "generation"
    files = generation / "files"
    files.mkdir(parents=True)
    (files / "über.bin").write_bytes(b"fixture")

    with pytest.raises(MODULE.ReleaseShelfError, match="not portable ASCII"):
        MODULE.build_inventory(generation)


def write_candidate(root: Path, version: str = "release-1", artifact: bytes = b"artifact-a") -> Path:
    files = root / "files"
    proof = root / "proof"
    smoke = root / "startup-smoke"
    evidence = root / "release-evidence"
    files.mkdir(parents=True)
    proof.mkdir()
    smoke.mkdir()
    evidence.mkdir()
    artifact_path = files / "chummer-test-installer.exe"
    artifact_path.write_bytes(artifact)
    digest = MODULE.sha256_file(artifact_path)
    published_at = "2026-07-15T12:00:00Z"
    canonical = {
        "version": version,
        "releaseVersion": version,
        "channel": "preview",
        "publishedAt": published_at,
        "artifacts": [
            {
                "artifactId": "test-installer",
                "fileName": artifact_path.name,
                "downloadUrl": f"/downloads/files/{artifact_path.name}",
                "sha256": digest,
                "sizeBytes": len(artifact),
                "installAccessClass": "open_public",
            }
        ],
        "proofUrl": "/downloads/proof/local.json",
        "smokeUrl": "/downloads/startup-smoke/test.json",
        "evidenceUrl": "/downloads/release-evidence/test.json",
    }
    compatibility = {
        "version": version,
        "channel": "preview",
        "publishedAt": "2026-07-15T12:00:00+00:00",
        "downloads": [
            {
                "id": "test-installer",
                "fileName": artifact_path.name,
                "url": f"/downloads/files/{artifact_path.name}",
                "sha256": digest,
                "sizeBytes": len(artifact),
                "installAccessClass": "open_public",
            }
        ],
    }
    (root / MODULE.CANONICAL_MANIFEST).write_text(
        json.dumps(canonical, indent=2) + "\n", encoding="utf-8"
    )
    (root / MODULE.COMPATIBILITY_MANIFEST).write_text(
        json.dumps(compatibility, indent=2) + "\n", encoding="utf-8"
    )
    (proof / "local.json").write_text('{"status":"passed"}\n', encoding="utf-8")
    (smoke / "test.json").write_text('{"status":"passed"}\n', encoding="utf-8")
    (evidence / "test.json").write_text('{"status":"passed"}\n', encoding="utf-8")
    return root


def test_prepare_binds_every_shelf_url_and_records_complete_inventory(tmp_path: Path) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    prepared = tmp_path / "prepared"

    pointer = MODULE.prepare_layout(
        candidate,
        prepared,
        generation_id="generation-a",
        activated_at="2026-07-15T13:00:00Z",
        activation_receipt_id="receipt-a",
    )

    generation = prepared / "generations" / "generation-a"
    canonical = json.loads((generation / MODULE.CANONICAL_MANIFEST).read_text(encoding="utf-8"))
    compatibility = json.loads(
        (generation / MODULE.COMPATIBILITY_MANIFEST).read_text(encoding="utf-8")
    )
    candidate_record = json.loads(
        (generation / MODULE.ACTIVATION_CANDIDATE).read_text(encoding="utf-8")
    )
    assert canonical["generationId"] == "generation-a"
    assert compatibility["generationId"] == "generation-a"
    assert canonical["artifacts"][0]["downloadUrl"].startswith(
        "/downloads/g/generation-a/files/"
    )
    assert compatibility["downloads"][0]["url"].startswith(
        "/downloads/g/generation-a/files/"
    )
    assert canonical["proofUrl"] == "/downloads/g/generation-a/proof/local.json"
    assert canonical["smokeUrl"] == "/downloads/g/generation-a/startup-smoke/test.json"
    assert canonical["evidenceUrl"] == "/downloads/g/generation-a/release-evidence/test.json"
    assert pointer["manifests"] == {
        "canonical": {
            "path": "/downloads/g/generation-a/RELEASE_CHANNEL.generated.json",
            "sha256": MODULE.sha256_file(generation / MODULE.CANONICAL_MANIFEST),
        },
        "compatibility": {
            "path": "/downloads/g/generation-a/releases.json",
            "sha256": MODULE.sha256_file(generation / MODULE.COMPATIBILITY_MANIFEST),
        },
    }
    assert candidate_record["releaseVersion"] == pointer["releaseVersion"]
    assert candidate_record["channel"] == pointer["channel"]
    assert candidate_record["publishedAt"] == pointer["publishedAt"]
    assert candidate_record["manifests"] == pointer["manifests"]
    assert candidate_record["inventoryDigest"] == pointer["inventoryDigest"]
    assert pointer["inventoryDigest"] == f"sha256:{MODULE.inventory_digest(candidate_record['inventory'])}"
    assert {row["path"] for row in candidate_record["inventory"]} >= {
        "files/chummer-test-installer.exe",
        "proof/local.json",
        "startup-smoke/test.json",
        "release-evidence/test.json",
    }
    MODULE.verify_generation(generation, pointer)


def test_filesystem_writer_refuses_server_journal_policy_before_staging(tmp_path: Path) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    shelf = tmp_path / "downloads"
    shelf.mkdir()
    (shelf / MODULE.WRITER_POLICY).write_text(
        json.dumps(
            {
                "schemaVersion": MODULE.SERVER_WRITER_POLICY_SCHEMA,
                "mode": MODULE.SERVER_WRITER_POLICY_MODE,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="staged HTTP server journal"):
        MODULE.activate_filesystem(candidate, shelf, initialize_layout=True)

    assert not (shelf / MODULE.CURRENT_POINTER).exists()
    assert not (shelf / MODULE.GENERATIONS_DIRECTORY).exists()
    assert not list(shelf.glob(".release-shelf-stage-*"))


def test_prepared_filesystem_writer_refuses_server_journal_policy_before_rename(
    tmp_path: Path,
) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    prepared = tmp_path / "prepared"
    MODULE.prepare_layout(candidate, prepared, generation_id="generation-policy")
    shelf = tmp_path / "downloads"
    shelf.mkdir()
    (shelf / MODULE.WRITER_POLICY).write_text(
        json.dumps(
            {
                "schemaVersion": MODULE.SERVER_WRITER_POLICY_SCHEMA,
                "mode": MODULE.SERVER_WRITER_POLICY_MODE,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="staged HTTP server journal"):
        MODULE.activate_prepared_filesystem(prepared, shelf, initialize_layout=True)

    assert (prepared / MODULE.GENERATIONS_DIRECTORY / "generation-policy").is_dir()
    assert not (shelf / MODULE.CURRENT_POINTER).exists()
    assert not (shelf / MODULE.GENERATIONS_DIRECTORY).exists()


def test_manifest_normalizer_projects_artifact_routes_by_access_and_omits_mutable_facts(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / MODULE.CANONICAL_MANIFEST
    manifest_path.write_text(
        json.dumps(
            {
                "version": "release-routes",
                "channel": "preview",
                "publishedAt": "2026-07-15T12:00:00Z",
                "artifacts": [
                    {
                        "artifactId": "open-installer",
                        "fileName": "open.bin",
                        "installAccessClass": "open_public",
                        "downloadUrl": "/downloads/files/open.bin",
                    },
                    {
                        "artifactId": "protected-installer",
                        "fileName": "protected.bin",
                        "installAccessClass": "account_required",
                        "downloadUrl": "/downloads/install/protected-installer",
                    },
                ],
                "openFact": "/downloads/get/open-installer",
                "protectedFact": "/downloads/file/protected-installer",
                "absentFact": "/downloads/install/missing-installer",
                "mutableContinuation": "/downloads/install/protected-installer/claim",
                "proofRoutes": [
                    "/downloads/install/avalonia-linux-x64-installer",
                    "/downloads/install/protected-installer",
                ],
                "releaseProof": {
                    "proofRoutes": [
                        "/downloads/install/avalonia-linux-x64-installer",
                        "/downloads/install/protected-installer",
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    normalized = MODULE.normalize_manifest(manifest_path, "generation-routes")

    assert normalized["artifacts"][0]["downloadUrl"] == (
        "/downloads/g/generation-routes/files/open.bin"
    )
    assert normalized["artifacts"][1]["downloadUrl"] == (
        "/downloads/g/generation-routes/install/protected-installer"
    )
    assert normalized["openFact"] == "/downloads/g/generation-routes/files/open.bin"
    assert normalized["protectedFact"] == (
        "/downloads/g/generation-routes/install/protected-installer"
    )
    assert "absentFact" not in normalized
    assert "mutableContinuation" not in normalized
    assert normalized["proofRoutes"] == [
        "/downloads/g/generation-routes/install/protected-installer",
    ]
    assert normalized["releaseProof"]["proofRoutes"] == [
        "/downloads/install/avalonia-linux-x64-installer",
        "/downloads/install/protected-installer",
    ]
    MODULE.validate_manifest_routes(normalized, "generation-routes", "fixture")


def test_registry_generation_projection_matches_cross_language_golden_bytes(
    tmp_path: Path,
) -> None:
    source = {
        "version": "release-parity",
        "channel": "preview",
        "publishedAt": "2026-07-17T20:00:00Z",
        "downloads": [
            {
                "id": "open",
                "fileName": "open.bin",
                "url": "/downloads/files/open.bin",
                "installAccessClass": "open_public",
            },
            {
                "id": "protected",
                "fileName": "protected.bin",
                "url": "/downloads/files/protected.bin",
                "installAccessClass": "account_required",
                "payloadFileName": "protected.zip",
                "payloadDownloadUrl": "/downloads/files/protected.zip",
            },
        ],
        "releaseProof": {"proofRoutes": ["/downloads/install/protected"]},
    }
    manifest_path = tmp_path / MODULE.COMPATIBILITY_MANIFEST
    manifest_path.write_text(json.dumps(source), encoding="utf-8")

    MODULE.normalize_manifest(manifest_path, "generation-parity")

    expected = (
        b'{"channel":"preview","downloads":[{"fileName":"open.bin","id":"open",'
        b'"installAccessClass":"open_public","url":"/downloads/g/generation-parity/files/open.bin"},'
        b'{"fileName":"protected.bin","id":"protected","installAccessClass":"account_required",'
        b'"payloadDownloadUrl":"/downloads/g/generation-parity/install/protected/payload",'
        b'"payloadFileName":"protected.zip","url":"/downloads/g/generation-parity/install/protected"}],'
        b'"generationId":"generation-parity","publishedAt":"2026-07-17T20:00:00Z",'
        b'"releaseProof":{"proofRoutes":["/downloads/install/protected"]},'
        b'"version":"release-parity"}\n'
    )
    assert manifest_path.read_bytes() == expected


@pytest.mark.parametrize(
    "route",
    (
        "/downloads/files/open.bin?ticket=secret",
        "/downloads/files/open.bin#fragment",
        "/downloads/files%2Fopen.bin",
        "/downloads/files/nested/open.bin",
        "https://chummer.run/downloads/files/open.bin",
        "//chummer.run/downloads/files/open.bin",
    ),
)
def test_registry_generation_projection_rejects_noncanonical_source_routes(
    tmp_path: Path,
    route: str,
) -> None:
    manifest_path = tmp_path / MODULE.COMPATIBILITY_MANIFEST
    manifest_path.write_text(
        json.dumps(
            {
                "version": "release-invalid-route",
                "channel": "preview",
                "publishedAt": "2026-07-17T20:00:00Z",
                "downloads": [
                    {
                        "id": "open",
                        "fileName": "open.bin",
                        "url": route,
                        "installAccessClass": "open_public",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="canonical|plain"):
        MODULE.normalize_manifest(manifest_path, "generation-invalid-route")


def test_registry_generation_projection_rejects_nested_release_proof_lookalike(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / MODULE.COMPATIBILITY_MANIFEST
    manifest_path.write_text(
        json.dumps(
            {
                "version": "release-lookalike",
                "channel": "preview",
                "publishedAt": "2026-07-17T20:00:00Z",
                "downloads": [],
                "extension": {
                    "releaseProof": {
                        "proofRoutes": ["/downloads/install/shadow"]
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="nested"):
        MODULE.normalize_manifest(manifest_path, "generation-lookalike")


@pytest.mark.parametrize(
    "url",
    (
        "/downloads/g/generation-routes/",
        "/downloads/g/generation-routes/files/nested/open.bin",
        "/downloads/g/generation-routes/install/protected-installer/claim",
        "/downloads/g/generation-routes/install/protected-installer?ticket=x",
        "/downloads/g/generation-routes/install/protected-installer#claim",
        "/downloads/g/generation-routes/install/protected-installer%2Fclaim",
    ),
)
def test_manifest_validator_rejects_non_exact_generation_install_routes(url: str) -> None:
    with pytest.raises(
        MODULE.ReleaseShelfError,
        match="unsafe generation URL|noncanonical route shape|canonical unencoded site path",
    ):
        MODULE.validate_manifest_routes(
            {"generationId": "generation-routes", "url": url},
            "generation-routes",
            "fixture",
        )


def test_shared_helper_accepts_cross_language_contract_fixture() -> None:
    fixture = ROOT / "tests" / "fixtures" / "atomic_release_shelf_v1"

    state, generation_root, pointer = MODULE.resolve_shelf_root(fixture)

    assert state == "generation"
    assert pointer is not None
    assert generation_root.name == pointer["generationId"]
    MODULE.verify_generation(generation_root, pointer)


@pytest.mark.parametrize(
    "generation_id",
    ("../escape", "/absolute", "with/slash", "", ".", "bad generation", "bad..generation"),
)
def test_generation_id_must_be_opaque_and_traversal_safe(generation_id: str) -> None:
    with pytest.raises(MODULE.ReleaseShelfError, match="traversal-safe opaque token"):
        MODULE.validate_generation_id(generation_id)


def test_filesystem_activation_requires_explicit_initialization_and_preserves_generations(
    tmp_path: Path,
) -> None:
    shelf = tmp_path / "shelf"
    first = write_candidate(tmp_path / "first")

    with pytest.raises(MODULE.ReleaseShelfError, match="explicit layout initialization"):
        MODULE.activate_filesystem(
            first,
            shelf,
            initialize_layout=False,
            generation_id="generation-a",
        )
    assert not (shelf / MODULE.LAYOUT_MARKER).exists()
    assert not (shelf / MODULE.CURRENT_POINTER).exists()

    pointer_a = MODULE.activate_filesystem(
        first,
        shelf,
        initialize_layout=True,
        generation_id="generation-a",
        activated_at="2026-07-15T13:00:00Z",
        activation_receipt_id="receipt-a",
    )
    first_bytes = (shelf / "generations" / "generation-a" / "files" / "chummer-test-installer.exe").read_bytes()
    second = write_candidate(tmp_path / "second", version="release-2", artifact=b"artifact-b")
    pointer_b = MODULE.activate_filesystem(
        second,
        shelf,
        initialize_layout=False,
        generation_id="generation-b",
        activated_at="2026-07-15T14:00:00Z",
        activation_receipt_id="receipt-b",
    )

    current = MODULE.load_pointer(shelf / MODULE.CURRENT_POINTER)
    assert pointer_a["generationId"] == "generation-a"
    assert pointer_b["generationId"] == current["generationId"] == "generation-b"
    assert (
        shelf / "generations" / "generation-a" / "files" / "chummer-test-installer.exe"
    ).read_bytes() == first_bytes
    state, resolved, _ = MODULE.resolve_shelf_root(shelf)
    assert state == "generation"
    assert resolved == shelf / "generations" / "generation-b"


def test_marker_or_pointer_inconsistency_fails_closed_without_legacy_fallback(tmp_path: Path) -> None:
    shelf = tmp_path / "shelf"
    shelf.mkdir()
    legacy_manifest = shelf / MODULE.CANONICAL_MANIFEST
    legacy_manifest.write_text('{"version":"legacy"}\n', encoding="utf-8")
    (shelf / MODULE.LAYOUT_MARKER).write_text("1\n", encoding="utf-8")

    with pytest.raises(MODULE.ReleaseShelfError, match="refusing legacy fallback"):
        MODULE.resolve_shelf_root(shelf)
    assert legacy_manifest.read_text(encoding="utf-8") == '{"version":"legacy"}\n'



def test_valid_pointer_is_authoritative_before_postcommit_marker_exists(tmp_path: Path) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-a",
    )
    (shelf / MODULE.LAYOUT_MARKER).unlink()

    state, generation_root, pointer = MODULE.resolve_shelf_root(shelf)

    assert state == "generation"
    assert generation_root.name == "generation-a"
    assert pointer is not None and pointer["generationId"] == "generation-a"


def test_manifest_mutation_is_rejected_by_pointer_and_candidate_bindings(tmp_path: Path) -> None:
    candidate = write_candidate(tmp_path / "candidate")
    prepared = tmp_path / "prepared"
    pointer = MODULE.prepare_layout(candidate, prepared, generation_id="generation-a")
    generation = prepared / MODULE.GENERATIONS_DIRECTORY / "generation-a"
    (generation / MODULE.CANONICAL_MANIFEST).write_text("{}\n", encoding="utf-8")

    with pytest.raises(MODULE.ReleaseShelfError, match="SHA-256|identity|generationId mismatch"):
        MODULE.verify_generation(generation, pointer)


def test_materializer_rejects_unreferenced_nested_and_case_colliding_files(tmp_path: Path) -> None:
    nested_candidate = write_candidate(tmp_path / "nested")
    nested = nested_candidate / "files" / "nested"
    nested.mkdir()
    (nested / "chummer-test-installer.exe").write_bytes(b"shadow")
    with pytest.raises(MODULE.ReleaseShelfError, match="unreferenced bytes"):
        MODULE.prepare_layout(
            nested_candidate,
            tmp_path / "nested-prepared",
            generation_id="generation-nested",
        )

    case_candidate = write_candidate(tmp_path / "case")
    (case_candidate / "files" / "CHUMMER-TEST-INSTALLER.EXE").write_bytes(b"shadow")
    with pytest.raises(MODULE.ReleaseShelfError, match="unreferenced bytes|case-colliding"):
        MODULE.prepare_layout(
            case_candidate,
            tmp_path / "case-prepared",
            generation_id="generation-case",
        )


def test_missing_or_corrupt_generation_fails_closed(tmp_path: Path) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-a",
    )
    artifact = shelf / "generations" / "generation-a" / "files" / "chummer-test-installer.exe"
    artifact.write_bytes(b"tampered")

    with pytest.raises(MODULE.ReleaseShelfError, match="mismatch"):
        MODULE.resolve_shelf_root(shelf)


def test_generation_id_cannot_be_reused_even_with_identical_bytes(tmp_path: Path) -> None:
    shelf = tmp_path / "shelf"
    candidate = write_candidate(tmp_path / "candidate")
    MODULE.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-a",
    )

    with pytest.raises(MODULE.ReleaseShelfError, match="already been used"):
        MODULE.activate_filesystem(
            candidate,
            shelf,
            initialize_layout=False,
            generation_id="generation-a",
        )


def test_concurrent_pointer_readers_observe_only_complete_generation_a_or_b(
    tmp_path: Path,
) -> None:
    shelf = tmp_path / "shelf"
    first = write_candidate(tmp_path / "first", version="release-a", artifact=b"artifact-a")
    MODULE.activate_filesystem(
        first,
        shelf,
        initialize_layout=True,
        generation_id="generation-a",
    )
    second = write_candidate(tmp_path / "second", version="release-b", artifact=b"artifact-b")
    stop = threading.Event()
    observed_b = threading.Event()
    failures: list[str] = []
    observed: set[str] = set()

    def read_current() -> None:
        while not stop.is_set():
            try:
                pointer_bytes = (shelf / MODULE.CURRENT_POINTER).read_bytes()
                pointer = json.loads(pointer_bytes)
                generation_id = pointer["generationId"]
                observed.add(generation_id)
                generation = shelf / MODULE.GENERATIONS_DIRECTORY / generation_id
                manifest = generation / MODULE.CANONICAL_MANIFEST
                expected = pointer["manifests"]["canonical"]["sha256"]
                if not manifest.is_file() or MODULE.sha256_file(manifest) != expected:
                    failures.append(f"mixed or incomplete generation observed: {generation_id}")
                    return
                if generation_id == "generation-b":
                    observed_b.set()
            except Exception as exc:  # pragma: no cover - failure detail for stress loop
                failures.append(str(exc))
                return

    reader = threading.Thread(target=read_current, daemon=True)
    reader.start()
    MODULE.activate_filesystem(
        second,
        shelf,
        initialize_layout=False,
        generation_id="generation-b",
    )
    assert observed_b.wait(timeout=2)
    time.sleep(0.01)
    stop.set()
    reader.join(timeout=2)

    assert not failures
    assert observed <= {"generation-a", "generation-b"}
    assert "generation-b" in observed


def test_publishers_use_one_shared_generation_primitive_and_keep_legacy_guard() -> None:
    filesystem = (ROOT / "scripts" / "publish-download-bundle.sh").read_text(encoding="utf-8")
    object_storage = (ROOT / "scripts" / "publish-download-bundle-s3.sh").read_text(
        encoding="utf-8"
    )
    # These assertions become effective alongside the publisher migration patch and
    # prevent either lane from drifting back to top-level activation.
    for script in (filesystem, object_storage):
        assert "release_shelf_generation.py" in script
        assert ".release-shelf-layout-v1" in script
        assert "current.json" in script
    assert "activate-filesystem" in filesystem
    assert "generations/" in object_storage


def test_manifest_generator_refuses_direct_output_to_activated_shelf(tmp_path: Path) -> None:
    shelf = tmp_path / "shelf"
    shelf.mkdir()
    (shelf / MODULE.LAYOUT_MARKER).write_text("v1\n", encoding="utf-8")
    registry = tmp_path / "registry"
    materializer = registry / "scripts" / "materialize_public_release_channel.py"
    materializer.parent.mkdir(parents=True)
    materializer.write_text("# guard test placeholder\n", encoding="utf-8")
    portal = tmp_path / "portal"
    authoritative = tmp_path / "published"
    env = os.environ.copy()
    env.update(
        {
            "CHUMMER_HUB_REGISTRY_ROOT": str(registry),
            "CHUMMER_PUBLIC_AUTHORITATIVE_PUBLISHED_ROOT": str(authoritative),
            "DOWNLOADS_DIR": str(shelf / "files"),
            "MANIFEST_PATH": str(shelf / MODULE.COMPATIBILITY_MANIFEST),
            "CANONICAL_MANIFEST_PATH": str(shelf / MODULE.CANONICAL_MANIFEST),
            "PORTAL_MANIFEST_PATH": str(portal / MODULE.COMPATIBILITY_MANIFEST),
            "PORTAL_CANONICAL_MANIFEST_PATH": str(portal / MODULE.CANONICAL_MANIFEST),
            "PORTAL_DOWNLOADS_DIR": str(portal),
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "generate-releases-manifest.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "direct manifest generation is forbidden" in result.stderr
    assert not (shelf / MODULE.COMPATIBILITY_MANIFEST).exists()
    assert not portal.exists()


def test_s3_publisher_uploads_immutable_objects_before_single_pointer_put_without_network(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    files = bundle / "files"
    files.mkdir(parents=True)
    artifact = files / "chummer-avalonia-osx-arm64-installer.dmg"
    artifact.write_bytes(b"fixture installer")
    digest = MODULE.sha256_file(artifact)
    published_at = "2026-07-15T12:00:00Z"
    canonical = {
        "version": "release-s3",
        "releaseVersion": "release-s3",
        "channel": "preview",
        "publishedAt": published_at,
        "artifacts": [
            {
                "artifactId": "avalonia-osx-arm64-installer",
                "head": "avalonia",
                "platform": "macos",
                "rid": "osx-arm64",
                "kind": "dmg",
                "fileName": artifact.name,
                "downloadUrl": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
            }
        ],
    }
    compatibility = {
        "version": "release-s3",
        "channel": "preview",
        "publishedAt": published_at,
        "downloads": [
            {
                "id": "avalonia-osx-arm64-installer",
                "head": "avalonia",
                "platformId": "macos",
                "rid": "osx-arm64",
                "kind": "dmg",
                "fileName": artifact.name,
                "url": f"/downloads/files/{artifact.name}",
                "sha256": digest,
                "sizeBytes": artifact.stat().st_size,
            }
        ],
    }
    (bundle / MODULE.CANONICAL_MANIFEST).write_text(
        json.dumps(canonical, indent=2) + "\n", encoding="utf-8"
    )
    (bundle / MODULE.COMPATIBILITY_MANIFEST).write_text(
        json.dumps(compatibility, indent=2) + "\n", encoding="utf-8"
    )

    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (public_root / "current.json").as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (public_root / "g").as_uri(),
            "CHUMMER_RELEASE_GENERATION_ID": "generation-s3",
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh"), str(bundle)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    operations = log_path.read_text(encoding="utf-8").splitlines()
    puts = [row for row in operations if row.startswith("PUT ")]
    assert puts[-2:] == ["PUT downloads/current.json", "PUT downloads/.release-shelf-layout-v1"]
    assert "PUT downloads/.release-shelf-layout-v1" in puts
    assert all(
        row.startswith("PUT downloads/generations/generation-s3/")
        for row in puts[: puts.index("PUT downloads/current.json")]
    )
    assert not any(
        row in {
            "PUT downloads/releases.json",
            "PUT downloads/RELEASE_CHANNEL.generated.json",
        }
        or row.startswith("PUT downloads/files/")
        for row in puts
    )
    pointer = json.loads((public_root / "current.json").read_text(encoding="utf-8"))
    assert pointer["generationId"] == "generation-s3"


@pytest.mark.parametrize(
    "existing_keys",
    (
        ("downloads",),
        ("downloads/releases.json",),
        ("downloads/files/legacy-installer.exe",),
        ("downloads/generations/orphan/activation-candidate.json",),
        ("downloads/.partial-upload",),
        ("downloads-a", "downloads-b", "downloads-c"),
    ),
    ids=(
        "root-object",
        "legacy-manifest",
        "legacy-file",
        "orphan-generation",
        "partial-object",
        "truncated-ambiguous-prefix",
    ),
)
def test_s3_first_generation_requires_bounded_empty_root_inventory(
    tmp_path: Path,
    existing_keys: tuple[str, ...],
) -> None:
    bundle = write_s3_publish_bundle(
        tmp_path / "bundle",
        version="release-nonempty-root",
        published_at="2026-07-15T12:30:00Z",
        payload=b"nonempty root artifact",
    )
    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    for key in existing_keys:
        path = remote_root / "fixture" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"preexisting object")
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (
                public_root / "current.json"
            ).as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (
                public_root / "g"
            ).as_uri(),
            "CHUMMER_RELEASE_GENERATION_ID": "generation-nonempty-root",
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh"), str(bundle)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "non-empty or ambiguous" in result.stderr
    assert "PRIMARY_RELEASE_NOT_COMMITTED" in result.stderr
    operations = log_path.read_text(encoding="utf-8").splitlines()
    assert not any(row.startswith("PUT ") for row in operations)


def test_s3_first_generation_rechecks_empty_root_before_first_upload(
    tmp_path: Path,
) -> None:
    bundle = write_s3_publish_bundle(
        tmp_path / "bundle",
        version="release-root-race",
        published_at="2026-07-15T12:45:00Z",
        payload=b"root race artifact",
    )
    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "FAKE_AWS_INJECT_ON_SECOND_ROOT_LIST": "downloads/releases.json",
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (
                public_root / "current.json"
            ).as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (
                public_root / "g"
            ).as_uri(),
            "CHUMMER_RELEASE_GENERATION_ID": "generation-root-race",
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh"), str(bundle)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert "non-empty or ambiguous" in result.stderr
    assert (remote_root / "fixture" / "downloads" / "releases.json").is_file()
    operations = log_path.read_text(encoding="utf-8").splitlines()
    assert operations.count("LIST downloads") == 2
    assert not any(row.startswith("PUT ") for row in operations)


def test_s3_concurrent_publishers_cannot_overwrite_current_pointer(
    tmp_path: Path,
) -> None:
    published_at = "2026-07-15T13:00:00Z"
    bundle_a = write_s3_publish_bundle(
        tmp_path / "bundle-a",
        version="release-concurrent-a",
        published_at=published_at,
        payload=b"concurrent artifact a",
    )
    bundle_b = write_s3_publish_bundle(
        tmp_path / "bundle-b",
        version="release-concurrent-b",
        published_at=published_at,
        payload=b"concurrent artifact b",
    )
    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    missing_existing = tmp_path / "missing-existing.json"
    common_env = os.environ.copy()
    common_env.update(
        {
            "PATH": f"{fake_bin}:{common_env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "FAKE_AWS_PUT_DELAY_MS": "15",
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (
                public_root / "current.json"
            ).as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (
                public_root / "g"
            ).as_uri(),
        }
    )
    env_a = common_env | {"CHUMMER_RELEASE_GENERATION_ID": "generation-concurrent-a"}
    env_b = common_env | {"CHUMMER_RELEASE_GENERATION_ID": "generation-concurrent-b"}
    command = ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh")]
    process_a = subprocess.Popen(
        command + [str(bundle_a)],
        cwd=ROOT,
        env=env_a,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    process_b = subprocess.Popen(
        command + [str(bundle_b)],
        cwd=ROOT,
        env=env_b,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout_a, stderr_a = process_a.communicate(timeout=60)
    stdout_b, stderr_b = process_b.communicate(timeout=60)

    outcomes = [process_a.returncode, process_b.returncode]
    assert outcomes.count(0) == 1, (
        f"publisher A status={process_a.returncode}\n{stdout_a}{stderr_a}\n"
        f"publisher B status={process_b.returncode}\n{stdout_b}{stderr_b}"
    )
    assert sum(status != 0 for status in outcomes) == 1
    pointer_bytes = (remote_root / "fixture" / "downloads" / "current.json").read_bytes()
    assert pointer_bytes == (public_root / "current.json").read_bytes()
    pointer = json.loads(pointer_bytes)
    assert pointer["generationId"] in {
        "generation-concurrent-a",
        "generation-concurrent-b",
    }
    operations = log_path.read_text(encoding="utf-8").splitlines()
    assert operations.count("PUT downloads/current.json") == 1


def test_s3_latest_failure_reports_primary_pointer_as_committed(
    tmp_path: Path,
) -> None:
    bundle = write_s3_publish_bundle(
        tmp_path / "bundle",
        version="release-latest-failure",
        published_at="2026-07-15T14:00:00Z",
        payload=b"latest failure artifact",
    )
    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "FAKE_AWS_FAIL_PUT_PREFIX": "latest/generations/",
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_S3_LATEST_URI": "s3://fixture/latest",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (
                public_root / "current.json"
            ).as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (
                public_root / "g"
            ).as_uri(),
            "CHUMMER_RELEASE_GENERATION_ID": "generation-latest-failure",
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh"), str(bundle)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "PRIMARY_RELEASE_COMMITTED generation=generation-latest-failure" in result.stderr
    )
    assert "PRIMARY_RELEASE_NOT_COMMITTED" not in result.stderr
    pointer = json.loads((public_root / "current.json").read_text(encoding="utf-8"))
    assert pointer["generationId"] == "generation-latest-failure"
    assert not (latest_public_root / "current.json").exists()


def test_s3_pointer_readback_failure_reports_primary_pointer_as_committed(
    tmp_path: Path,
) -> None:
    bundle = write_s3_publish_bundle(
        tmp_path / "bundle",
        version="release-readback-failure",
        published_at="2026-07-15T15:00:00Z",
        payload=b"readback failure artifact",
    )
    fake_bin, remote_root, public_root, latest_public_root, log_path = (
        install_fake_conditional_s3_cli(tmp_path)
    )
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_LATEST_PUBLIC_ROOT": str(latest_public_root),
            "FAKE_AWS_LOG": str(log_path),
            "FAKE_AWS_FAIL_GET_KEY": "downloads/current.json",
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (
                public_root / "current.json"
            ).as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (
                public_root / "g"
            ).as_uri(),
            "CHUMMER_RELEASE_GENERATION_ID": "generation-readback-failure",
        }
    )

    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "publish-download-bundle-s3.sh"), str(bundle)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "PRIMARY_RELEASE_COMMITTED generation=generation-readback-failure"
        in result.stderr
    )
    assert "PRIMARY_RELEASE_NOT_COMMITTED" not in result.stderr
    pointer = json.loads(
        (remote_root / "fixture" / "downloads" / "current.json").read_text(
            encoding="utf-8"
        )
    )
    assert pointer["generationId"] == "generation-readback-failure"


def test_runtime_generation_routes_and_production_downgrade_sentinel_are_wired() -> None:
    controller = (ROOT / "Chummer.Run.Api" / "Controllers" / "DownloadsCompatibilityController.cs").read_text(
        encoding="utf-8"
    )
    program = (ROOT / "Chummer.Run.Api" / "Program.cs").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.public-edge.yml").read_text(encoding="utf-8")
    appsettings = json.loads((ROOT / "Chummer.Run.Api" / "appsettings.json").read_text(encoding="utf-8"))
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md").read_text(encoding="utf-8")

    assert "LoadGenerationCompatibilityManifestBytes(snapshot)" in controller
    assert "LoadGenerationCanonicalManifestBytes(snapshot)" in controller
    assert 'HttpGet("/downloads/g/{generationId}/aur-packages.json")' in controller
    assert 'snapshot.OpenVerifiedFile($"release-evidence/{path}")' in program
    assert 'snapshot.OpenVerifiedFile($"proof/{path}")' in program
    assert 'snapshot.OpenVerifiedFile($"startup-smoke/{path}")' in program
    assert "static context => !IsGovernedReleaseStaticPath(context.Request.Path)" in program
    governed_gate = program[program.index("static bool IsGovernedReleaseStaticPath(") :]
    for governed_path in (
        "/downloads/RELEASE_CHANNEL.generated.json",
        "/downloads/releases.json",
        "/downloads/g",
        "/downloads/files",
        "/downloads/file",
        "/downloads/install",
        "/downloads/proof",
        "/downloads/startup-smoke",
        "/downloads/release-evidence",
    ):
        assert governed_path in governed_gate
    assert "/downloads/release-upload" not in governed_gate
    assert 'CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED: "${CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED:?' in compose
    assert 'CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED: "${CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED:?' in compose
    assert appsettings["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"] is False
    assert "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED=false" in env_example
    assert "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED=false" in env_example
    assert "downgrade sentinel" in runbook
    assert "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED=true" in runbook
    assert "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED=false" in runbook
    assert "matching committed activation receipt" in runbook


def test_runtime_bounded_reader_uses_one_descriptor_and_checks_for_growth() -> None:
    source = (ROOT / "Chummer.Run.Api" / "Services" / "ReleaseShelfGenerationStore.cs").read_text(
        encoding="utf-8"
    )
    start = source.index("private static byte[] ReadBoundedFile(")
    end = source.index("private static JsonElement ParseJsonObject", start)
    body = source[start:end]

    assert "new FileStream(" in body
    assert "stream.Length" in body
    assert "stream.ReadExactly(bytes)" in body
    assert "stream.ReadByte() != -1" in body
    assert "File.ReadAllBytes" not in body


def test_layout_v1_reader_exposes_no_verify_then_reopen_path_api() -> None:
    offenders = []
    for source_path in (ROOT / "Chummer.Run.Api").rglob("*.cs"):
        source = source_path.read_text(encoding="utf-8")
        if ".ResolveExistingFile(" in source:
            offenders.append(source_path.relative_to(ROOT).as_posix())

    assert offenders == []
