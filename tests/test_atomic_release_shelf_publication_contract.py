from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterator
from urllib.parse import unquote, urlsplit

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "atomic_release_shelf_v1"
ATOMIC_CONTRACT_DOC = REPO_ROOT / "docs" / "ATOMIC_RELEASE_SHELF_PUBLICATION.md"
DOWNLOADS_RUNBOOK = REPO_ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md"
GENERATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
POINTER_SCHEMA = "chummer.release-shelf.current/v1"
ALLOWED_GENERATION_ROUTE_ROOTS = {
    "RELEASE_CHANNEL.generated.json",
    "releases.json",
    "files",
    "proof",
    "startup-smoke",
    "release-evidence",
}


class ShelfContractError(ValueError):
    pass


def read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ShelfContractError(f"invalid JSON object: {path}") from error
    if not isinstance(payload, dict):
        raise ShelfContractError(f"JSON root must be an object: {path}")
    return payload


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_inventory_digest(inventory: list[dict[str, Any]]) -> str:
    encoded = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_safe_generation_id(value: Any) -> str:
    generation_id = str(value or "")
    if (
        not GENERATION_ID_PATTERN.fullmatch(generation_id)
        or generation_id in {".", ".."}
        or ".." in generation_id
    ):
        raise ShelfContractError("current pointer generationId is not traversal-safe")
    return generation_id


def generation_url_to_path(url: str, generation_root: Path, generation_id: str) -> Path:
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ShelfContractError(f"authoritative manifest URL must be a plain site path: {url}")
    decoded_path = unquote(parsed.path)
    prefix = f"/downloads/g/{generation_id}/"
    if not decoded_path.startswith(prefix):
        raise ShelfContractError(f"authoritative manifest URL is not generation-bound: {url}")

    relative_text = decoded_path[len(prefix) :]
    relative = PurePosixPath(relative_text)
    if (
        not relative_text
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.parts[0] not in ALLOWED_GENERATION_ROUTE_ROOTS
    ):
        raise ShelfContractError(f"authoritative manifest URL has an unsafe generation path: {url}")

    candidate = generation_root.joinpath(*relative.parts)
    try:
        candidate.resolve().relative_to(generation_root.resolve())
    except (OSError, ValueError) as error:
        raise ShelfContractError(f"authoritative manifest URL escapes its generation: {url}") from error
    return candidate


def iter_download_urls(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_download_urls(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_download_urls(child)
    elif isinstance(value, str) and value.startswith("/downloads/"):
        yield value


def validate_generation_inventory(generation_root: Path, pointer: dict[str, Any]) -> None:
    candidate = read_object(generation_root / "activation-candidate.json")
    inventory = candidate.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        raise ShelfContractError("activation candidate inventory must be a non-empty list")

    for row in inventory:
        if not isinstance(row, dict):
            raise ShelfContractError("activation candidate inventory row must be an object")
        relative = PurePosixPath(str(row.get("path") or ""))
        digest = str(row.get("sha256") or "")
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ShelfContractError("activation candidate inventory path is unsafe")
        if not SHA256_PATTERN.fullmatch(digest):
            raise ShelfContractError("activation candidate inventory SHA-256 is malformed")
        artifact = generation_root.joinpath(*relative.parts)
        if not artifact.is_file() or sha256_file(artifact) != digest:
            raise ShelfContractError(f"generation inventory digest mismatch: {relative}")

    expected = str(pointer.get("inventoryDigest") or "")
    actual = f"sha256:{canonical_inventory_digest(inventory)}"
    if expected != actual:
        raise ShelfContractError("current pointer inventoryDigest does not bind activation inventory")


def resolve_release_shelf(root: Path) -> tuple[str, Path, dict[str, Any] | None]:
    marker = root / ".release-shelf-layout-v1"
    pointer_path = root / "current.json"
    marker_exists = marker.is_file()
    pointer_exists = pointer_path.is_file()

    if not marker_exists and not pointer_exists:
        for manifest_name in ("RELEASE_CHANNEL.generated.json", "releases.json"):
            if not (root / manifest_name).is_file():
                raise ShelfContractError(f"legacy shelf is missing {manifest_name}")
        return "legacy", root, None

    if not marker_exists or not pointer_exists:
        raise ShelfContractError("layout marker and current pointer must either both exist or both be absent")

    pointer = read_object(pointer_path)
    if pointer.get("schemaVersion") != POINTER_SCHEMA:
        raise ShelfContractError("current pointer schemaVersion is unsupported")
    generation_id = require_safe_generation_id(pointer.get("generationId"))
    for field in (
        "releaseVersion",
        "channel",
        "publishedAt",
        "inventoryDigest",
        "activatedAt",
        "activationReceiptId",
    ):
        if not isinstance(pointer.get(field), str) or not pointer[field].strip():
            raise ShelfContractError(f"current pointer is missing {field}")

    generation_root = root / "generations" / generation_id
    if not generation_root.is_dir() or generation_root.is_symlink():
        raise ShelfContractError("current pointer generation is missing or not an immutable directory")

    manifests = pointer.get("manifests")
    if not isinstance(manifests, dict) or set(manifests) != {"canonical", "compatibility"}:
        raise ShelfContractError("current pointer must bind canonical and compatibility manifests")
    expected_names = {
        "canonical": "RELEASE_CHANNEL.generated.json",
        "compatibility": "releases.json",
    }
    for key, expected_name in expected_names.items():
        binding = manifests.get(key)
        if not isinstance(binding, dict):
            raise ShelfContractError(f"current pointer {key} manifest binding is malformed")
        expected_url = f"/downloads/g/{generation_id}/{expected_name}"
        if binding.get("path") != expected_url:
            raise ShelfContractError(f"current pointer {key} path is not generation-bound")
        digest = str(binding.get("sha256") or "")
        if not SHA256_PATTERN.fullmatch(digest):
            raise ShelfContractError(f"current pointer {key} SHA-256 is malformed")
        manifest_path = generation_url_to_path(expected_url, generation_root, generation_id)
        if not manifest_path.is_file() or sha256_file(manifest_path) != digest:
            raise ShelfContractError(f"current pointer {key} manifest digest mismatch")
        manifest = read_object(manifest_path)
        if manifest.get("generationId") != generation_id:
            raise ShelfContractError(f"{key} manifest generationId disagrees with current pointer")
        if manifest.get("version") != pointer["releaseVersion"]:
            raise ShelfContractError(f"{key} manifest release version disagrees with current pointer")

    validate_generation_inventory(generation_root, pointer)
    return "generation", generation_root, pointer


def executable_source_lines(source: str) -> str:
    return "\n".join(
        line for line in source.splitlines() if line.strip() and not line.lstrip().startswith("#")
    )


def writer_protocol(source: str, contract: dict[str, Any]) -> str | None:
    executable = executable_source_lines(source)
    protocols = contract["writerProtocols"]
    marker_and_pointer = all(token in executable for token in (".release-shelf-layout-v1", "current.json"))
    if not marker_and_pointer:
        return None

    call_source = "\n".join(
        line
        for line in executable.splitlines()
        if not re.match(r"^\s*def\s+assert_legacy_release_shelf_target\s*\(.*:\s*$", line)
        and not re.match(r"^\s*assert_legacy_release_shelf_target\s*\(\)\s*\{", line)
    )
    legacy_call = re.search(
        r"(?m)^\s*assert_legacy_release_shelf_target(?:\s|\(|$)",
        call_source,
    )
    if legacy_call and all(token in executable for token in protocols["legacyFailClosed"]):
        return "legacyFailClosed"

    if all(token in executable for token in protocols["generationAware"]):
        stage_calls = len(re.findall(r"stage_release_shelf_generation(?:\s|\()", executable))
        activate_calls = len(re.findall(r"activate_release_shelf_generation(?:\s|\()", executable))
        if stage_calls >= 2 and activate_calls >= 2:
            return "generationAware"
    return None


def load_contract() -> dict[str, Any]:
    return read_object(FIXTURE_ROOT / "contract.json")


def copy_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / "downloads"
    shutil.copytree(FIXTURE_ROOT, destination)
    return destination


def test_release_publication_docs_describe_the_implemented_authority() -> None:
    contract_doc = ATOMIC_CONTRACT_DOC.read_text(encoding="utf-8")
    runbook = DOWNLOADS_RUNBOOK.read_text(encoding="utf-8")

    for implemented_truth in (
        "Status: **Implemented production contract**",
        "## Closed deterministic gap",
        "`server-journal-v1` stages and validates one immutable generation",
        "atomically commits `current.json` as the sole publication",
        "production local publication uses the staged HTTP lane",
        "Any regression closes the gate",
    ):
        assert implemented_truth in contract_doc

    for retired_claim in (
        "Status: **P1 launch blocker**",
        "## Current deterministic gap",
        "currently reads `proof/windows`",
        "currently reads `aur-packages.json`",
        "currently treat top-level paths as authoritative",
        "currently mutates deploy and mirror roots",
        "must call the shared stage/validate/activate primitive",
        "must route release mode",
        "must move in the same contract change",
        "Do not claim atomic release publication",
    ):
        assert retired_claim not in contract_doc

    topology = runbook[
        runbook.index("## Recommended Production Topology") :
        runbook.index("## Install-linking PostgreSQL authority cutover")
    ]
    filesystem_lane = runbook[
        runbook.index("## Mode A: Legacy/dev filesystem source candidate") :
        runbook.index("## Mode B: Object Storage Deploy")
    ]
    assert "canonical local-production lane is Mode C" in topology
    assert "server-journal-v1" in topology
    assert "limited to legacy development or source-candidate trees" in topology
    assert "never production" in filesystem_lane.splitlines()[0]
    assert "must not be the live production shelf" in filesystem_lane
    assert "production uses\nMode C staged HTTP publication" in filesystem_lane


def test_layout_v1_fixture_pointer_binds_complete_generation() -> None:
    mode, generation_root, pointer = resolve_release_shelf(FIXTURE_ROOT)

    assert mode == "generation"
    assert pointer is not None
    assert generation_root.name == pointer["generationId"]


def test_authoritative_fixture_urls_are_generation_bound_and_resolvable() -> None:
    contract = load_contract()
    mode, generation_root, pointer = resolve_release_shelf(FIXTURE_ROOT)
    assert mode == "generation"
    assert pointer is not None
    generation_id = pointer["generationId"]

    urls: set[str] = set()
    identities: set[tuple[str, str]] = set()
    for manifest_name in contract["authoritativeManifestNames"]:
        manifest = read_object(generation_root / manifest_name)
        identities.add((manifest["generationId"], manifest["version"]))
        for url in iter_download_urls(manifest):
            urls.add(url)
            assert not any(
                url.startswith(prefix)
                for prefix in contract["forbiddenAuthoritativeRoutePrefixes"]
            )
            assert generation_url_to_path(url, generation_root, generation_id).is_file()

    assert identities == {(generation_id, pointer["releaseVersion"])}
    assert urls == {
        f"/downloads/g/{generation_id}/RELEASE_CHANNEL.generated.json",
        f"/downloads/g/{generation_id}/files/chummer-fixture.dmg",
        f"/downloads/g/{generation_id}/proof/mac/release-proof.json",
        f"/downloads/g/{generation_id}/release-evidence/public-promotion.json",
        f"/downloads/g/{generation_id}/startup-smoke/startup-smoke-avalonia-osx-arm64.receipt.json",
    }


@pytest.mark.parametrize(
    ("marker_exists", "pointer_exists", "expected_mode"),
    (
        (False, False, "legacy"),
        (True, False, None),
        (False, True, None),
    ),
)
def test_legacy_fallback_requires_marker_and_pointer_to_both_be_absent(
    tmp_path: Path,
    marker_exists: bool,
    pointer_exists: bool,
    expected_mode: str | None,
) -> None:
    root = tmp_path / "downloads"
    root.mkdir()
    for name in ("RELEASE_CHANNEL.generated.json", "releases.json"):
        (root / name).write_text("{}\n", encoding="utf-8")
    if marker_exists:
        (root / ".release-shelf-layout-v1").write_text("v1\n", encoding="utf-8")
    if pointer_exists:
        shutil.copy2(FIXTURE_ROOT / "current.json", root / "current.json")

    if expected_mode is None:
        with pytest.raises(ShelfContractError, match="must either both exist or both be absent"):
            resolve_release_shelf(root)
    else:
        assert resolve_release_shelf(root)[0] == expected_mode


@pytest.mark.parametrize("generation_id", ("../escape", "/absolute", "gen/child", ".."))
def test_invalid_pointer_never_falls_back_to_stale_top_level_bytes(
    tmp_path: Path,
    generation_id: str,
) -> None:
    root = tmp_path / "downloads"
    root.mkdir()
    (root / ".release-shelf-layout-v1").write_text("v1\n", encoding="utf-8")
    pointer = read_object(FIXTURE_ROOT / "current.json")
    pointer["generationId"] = generation_id
    (root / "current.json").write_text(json.dumps(pointer), encoding="utf-8")
    for name in ("RELEASE_CHANNEL.generated.json", "releases.json"):
        (root / name).write_text('{"version":"stale-but-present"}\n', encoding="utf-8")

    with pytest.raises(ShelfContractError, match="traversal-safe"):
        resolve_release_shelf(root)


def test_manifest_digest_mismatch_never_falls_back_to_top_level_bytes(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    generation_id = read_object(root / "current.json")["generationId"]
    canonical = root / "generations" / generation_id / "RELEASE_CHANNEL.generated.json"
    canonical.write_text(canonical.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    for name in ("RELEASE_CHANNEL.generated.json", "releases.json"):
        (root / name).write_text('{"version":"stale-but-present"}\n', encoding="utf-8")

    with pytest.raises(ShelfContractError, match="canonical manifest digest mismatch"):
        resolve_release_shelf(root)


def test_authoritative_manifest_rejects_friendly_or_top_level_routes() -> None:
    pointer = read_object(FIXTURE_ROOT / "current.json")
    generation_id = pointer["generationId"]
    generation_root = FIXTURE_ROOT / "generations" / generation_id
    manifest = copy.deepcopy(read_object(generation_root / "RELEASE_CHANNEL.generated.json"))
    manifest["artifacts"][0]["downloadUrl"] = "/downloads/files/chummer-fixture.dmg"

    with pytest.raises(ShelfContractError, match="not generation-bound"):
        for url in iter_download_urls(manifest):
            generation_url_to_path(url, generation_root, generation_id)


def test_writer_protocol_classifier_rejects_comments_and_uninvoked_helpers() -> None:
    contract = load_contract()
    comment_only = """
# .release-shelf-layout-v1 current.json assert_legacy_release_shelf_target
cp bundle/RELEASE_CHANNEL.generated.json "$DEPLOY_DIR/RELEASE_CHANNEL.generated.json"
"""
    definition_only = """
assert_legacy_release_shelf_target() { return 1; }
layout_marker=.release-shelf-layout-v1
current_pointer=current.json
cp bundle/RELEASE_CHANNEL.generated.json "$DEPLOY_DIR/RELEASE_CHANNEL.generated.json"
"""

    assert writer_protocol(comment_only, contract) is None
    assert writer_protocol(definition_only, contract) is None


def test_writer_protocol_classifier_accepts_executable_fail_closed_guard() -> None:
    contract = load_contract()
    guarded = """
assert_legacy_release_shelf_target() {
  test ! -e "$1/.release-shelf-layout-v1" || return 1
  test ! -e "$1/current.json" || return 1
}
assert_legacy_release_shelf_target "$DEPLOY_DIR"
cp bundle/RELEASE_CHANNEL.generated.json "$DEPLOY_DIR/RELEASE_CHANNEL.generated.json"
"""

    assert writer_protocol(guarded, contract) == "legacyFailClosed"


def test_writer_protocol_classifier_accepts_stage_then_single_pointer_activation() -> None:
    contract = load_contract()
    generation_aware = """
layout_marker=.release-shelf-layout-v1
current_pointer=current.json
stage_release_shelf_generation() { return 0; }
activate_release_shelf_generation() { return 0; }
stage_release_shelf_generation "$CANDIDATE_ROOT"
activate_release_shelf_generation "$CANDIDATE_ROOT"
"""

    assert writer_protocol(generation_aware, contract) == "generationAware"


def test_release_writer_inventory_discovers_known_cross_repository_entrypoints() -> None:
    contract = load_contract()
    inventoried = {
        WORKSPACE_ROOT / row["repository"] / row["path"]
        for row in contract["releaseModeWriters"]
    }
    missing = sorted(str(path.relative_to(WORKSPACE_ROOT)) for path in inventoried if not path.is_file())
    assert not missing, "release writer inventory names missing files:\n" + "\n".join(missing)

    discovered: set[Path] = set()
    for repository_name in contract["releaseRepositories"]:
        repository = WORKSPACE_ROOT / repository_name
        if not repository.is_dir():
            continue
        for name in contract["releaseModeWriterNames"]:
            candidate = repository / "scripts" / name
            if candidate.is_file():
                discovered.add(candidate)
    unregistered = sorted(
        str(path.relative_to(WORKSPACE_ROOT)) for path in discovered - inventoried
    )
    assert not unregistered, "unregistered release-mode writers:\n" + "\n".join(unregistered)


def test_every_release_mode_writer_is_generation_aware_or_fails_closed_on_layout_v1() -> None:
    contract = load_contract()
    violations: list[str] = []
    for row in contract["releaseModeWriters"]:
        relative = Path(row["repository"]) / row["path"]
        source_path = WORKSPACE_ROOT / relative
        if not source_path.is_file():
            violations.append(f"{relative}: missing inventoried writer")
            continue
        protocol = writer_protocol(source_path.read_text(encoding="utf-8"), contract)
        if protocol is None:
            violations.append(
                f"{relative}: neither generation-aware nor guarded legacy protocol is executable"
            )

    assert not violations, (
        "layout-v1 publication contract violations; a release-mode writer could mutate "
        "top-level active shelf paths after marker/pointer activation:\n" + "\n".join(violations)
    )
