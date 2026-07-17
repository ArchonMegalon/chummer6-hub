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
                "url": f"https://chummer.run/downloads/files/{artifact_path.name}",
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
        "/downloads/install/avalonia-linux-x64-installer",
        "/downloads/install/protected-installer",
    ]
    assert normalized["releaseProof"]["proofRoutes"] == normalized["proofRoutes"]
    MODULE.validate_manifest_routes(normalized, "generation-routes", "fixture")


@pytest.mark.parametrize(
    "url",
    (
        "/downloads/g/generation-routes/install/protected-installer/claim",
        "/downloads/g/generation-routes/install/protected-installer?ticket=x",
        "/downloads/g/generation-routes/install/protected-installer#claim",
        "/downloads/g/generation-routes/install/protected-installer%2Fclaim",
    ),
)
def test_manifest_validator_rejects_non_exact_generation_install_routes(url: str) -> None:
    with pytest.raises(MODULE.ReleaseShelfError, match="unsafe generation URL|plain site path"):
        MODULE.validate_manifest_routes(
            {"url": url},
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

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_aws = fake_bin / "aws"
    fake_aws.write_text(
        """#!/usr/bin/env python3
import json
import os
import shutil
import sys
from pathlib import Path

remote = Path(os.environ["FAKE_AWS_ROOT"])
public = Path(os.environ["FAKE_PUBLIC_ROOT"])
log = Path(os.environ["FAKE_AWS_LOG"])
args = sys.argv[1:]

def option(name):
    return args[args.index(name) + 1]

def s3_path(uri):
    raw = uri[len("s3://"):]
    bucket, _, key = raw.partition("/")
    return remote / bucket / key, bucket, key

def record(text):
    with log.open("a", encoding="utf-8") as handle:
        handle.write(text + "\\n")

if args[:2] == ["s3api", "head-object"]:
    bucket = option("--bucket")
    key = option("--key")
    path = remote / bucket / key
    record(f"HEAD {key}")
    if not path.is_file():
        raise SystemExit(255)
    metadata_path = Path(str(path) + ".metadata.json")
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    print(json.dumps({"ContentLength": path.stat().st_size, "Metadata": metadata}))
    raise SystemExit(0)

if args[:2] == ["s3", "ls"]:
    path, _, key = s3_path(args[2])
    record(f"LS {key}")
    if path.exists():
        for child in sorted(path.rglob("*")):
            if child.is_file() and not child.name.endswith(".metadata.json"):
                print(child)
    raise SystemExit(0)

if args[:2] == ["s3", "cp"]:
    source, destination = args[2], args[3]
    if source.startswith("s3://"):
        source_path, _, key = s3_path(source)
        record(f"GET {key}")
        if not source_path.is_file():
            raise SystemExit(1)
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        raise SystemExit(0)
    destination_path, _, key = s3_path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination_path)
    metadata = {}
    if "--metadata" in args:
        raw = option("--metadata")
        metadata = dict(item.split("=", 1) for item in raw.split(",") if "=" in item)
    Path(str(destination_path) + ".metadata.json").write_text(json.dumps(metadata))
    record(f"PUT {key}")
    prefix = "downloads/generations/"
    if key.startswith(prefix):
        relative = key[len(prefix):]
        generation_id, _, generation_relative = relative.partition("/")
        public_path = public / "g" / generation_id / generation_relative
        public_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, public_path)
    elif key == "downloads/current.json":
        public.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, public / "current.json")
    raise SystemExit(0)

raise SystemExit(f"unsupported fake aws invocation: {args}")
""",
        encoding="utf-8",
    )
    fake_aws.chmod(0o755)
    remote_root = tmp_path / "remote"
    public_root = tmp_path / "public"
    log_path = tmp_path / "aws.log"
    missing_existing = tmp_path / "missing-existing.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_AWS_ROOT": str(remote_root),
            "FAKE_PUBLIC_ROOT": str(public_root),
            "FAKE_AWS_LOG": str(log_path),
            "CHUMMER_PORTAL_DOWNLOADS_S3_URI": "s3://fixture/downloads",
            "CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL": str(missing_existing),
            "CHUMMER_PORTAL_DOWNLOADS_CURRENT_VERIFY_URL": (public_root / "current.json").as_uri(),
            "CHUMMER_PORTAL_DOWNLOADS_GENERATION_VERIFY_BASE_URL": (public_root / "g").as_uri(),
            "CHUMMER_RELEASE_SHELF_LAYOUT_V1_ENABLED": "true",
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
