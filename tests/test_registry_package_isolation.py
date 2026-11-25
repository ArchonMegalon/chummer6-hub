"""Negative checks for candidate selection and package-to-runtime byte binding."""
import base64
import dataclasses
import hashlib
import importlib.util
import json
import sys
import types
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / f"scripts/ai/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path):
    module = load("verify-registry-package-isolation")
    feed, cache = tmp_path / "feed", tmp_path / "cache"
    feed.mkdir()
    cache.mkdir()
    rows = {}
    libraries = {}
    for package_id in module.REGISTRY_IDS:
        row = types.SimpleNamespace(package_id=package_id, version="1.2.3-test", commit="b" * 40)
        rows[package_id] = row
        package = feed / f"{package_id}.{row.version}.nupkg"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(f"lib/net10.0/{package_id}.dll", b"synthetic-dll-bytes")
        libraries[f"{package_id}/{row.version}"] = {
            "type": "package", "sha512": base64.b64encode(hashlib.sha512(package.read_bytes()).digest()).decode()
        }
        for project in ("Chummer.Run.Api", module.PROJECT):
            dll = tmp_path / project / "bin/Release/net10.0" / f"{package_id}.dll"
            dll.parent.mkdir(parents=True, exist_ok=True)
            dll.write_bytes(b"synthetic-dll-bytes")
    for project in ("Chummer.Run.Api", module.PROJECT):
        assets = tmp_path / project / "obj/project.assets.json"
        assets.parent.mkdir()
        assets.write_text(json.dumps({"packageFolders": {str(cache): {}}, "libraries": libraries}))
    return module, feed, cache, rows


def test_baseline_source_is_rejected_before_runtime():
    module = load("verify-registry-package-isolation")
    rows = tuple(types.SimpleNamespace(package_id=x, commit=module.BASELINE_REGISTRY_COMMIT) for x in module.REGISTRY_IDS)
    with pytest.raises(ValueError, match="old vulnerable"):
        module.selected_registry(types.SimpleNamespace(packages=rows), module.BASELINE_REGISTRY_COMMIT)


def test_mixed_registry_source_selection_is_rejected():
    module = load("verify-registry-package-isolation")
    rows = tuple(types.SimpleNamespace(package_id=x, commit=str(i) * 40) for i, x in enumerate(module.REGISTRY_IDS))
    with pytest.raises(ValueError, match="Both Registry packages"):
        module.selected_registry(types.SimpleNamespace(packages=rows), "1" * 40)


def test_actual_package_and_runtime_bytes_match(tmp_path):
    module, feed, cache, rows = fixture(tmp_path)
    module.audit_assets(tmp_path, cache, rows, feed)
    assert len(module.audit_loaded_files(tmp_path, rows, feed)) == 2


@pytest.mark.parametrize("change", ["cache", "source-project", "hash", "second-project"])
def test_restore_escape_or_substitution_is_rejected(tmp_path, change):
    module, feed, cache, rows = fixture(tmp_path)
    path = tmp_path / "Chummer.Run.Api/obj/project.assets.json"
    payload = json.loads(path.read_text())
    library = next(iter(payload["libraries"].values()))
    if change == "cache":
        payload["packageFolders"][str(tmp_path / "ambient")] = {}
    elif change == "source-project":
        library["type"] = "project"
    elif change == "hash":
        library["sha512"] = "different"
    else:
        payload["libraries"]["Chummer.Run.Registry/9.9.9"] = {"type": "project"}
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        module.audit_assets(tmp_path, cache, rows, feed)


@pytest.mark.parametrize("project", ["Chummer.Run.Api", "Chummer.Run.Registry.PackageTests"])
def test_runtime_dll_substitution_is_rejected(tmp_path, project):
    module, feed, _, rows = fixture(tmp_path)
    (tmp_path / project / "bin/Release/net10.0/Chummer.Run.Registry.dll").write_bytes(b"substituted")
    with pytest.raises(ValueError, match="runtime DLL differs"):
        module.audit_loaded_files(tmp_path, rows, feed)


def test_candidate_selection_preserves_core_and_feed_authorities():
    candidate = load("prepare-registry-package-candidate")
    bootstrap = candidate.load_bootstrap(ROOT)
    lock = bootstrap.load_lock(ROOT / "eng/package-plane.lock.json")
    selected = candidate.select(bootstrap, lock, "b" * 40, "c" * 40, "1.2.3-synthetic")
    assert selected.core_runtime == lock.core_runtime
    assert selected.approved_remote_source == lock.approved_remote_source
    assert selected.build_recipe_sha256 == lock.build_recipe_sha256
    for old, new in zip(lock.packages, selected.packages, strict=True):
        assert dataclasses.replace(new, version=old.version, commit=old.commit) == old
    with pytest.raises(ValueError, match="existing locked"):
        candidate.select(bootstrap, lock, "b" * 40, "c" * 40, lock.package_version)
    with pytest.raises(ValueError, match="accepted correction"):
        candidate.select(bootstrap, lock, lock.packages[0].commit, "c" * 40, "1.2.3-synthetic")
