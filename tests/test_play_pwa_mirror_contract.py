from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_PROJECT = ROOT / "Chummer.Run.Api"
CONTRACT_PATH = RUN_PROJECT / "play-pwa-mirrors.json"
INVENTORY_PATH = RUN_PROJECT / "play-pwa-required-inventory.json"


def test_declared_play_install_mirrors_are_byte_identical_and_digest_pinned() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    source_root = (ROOT / contract["sourceRepository"]).resolve()

    assert contract["contract"] == "play-install-mirror-v5"
    assert contract["inventoryContract"] == "play-install-mirror-required-inventory-v2"
    assert contract["policyId"] == "chummer.public-play-pwa-mirror.v1"
    assert inventory["policyId"] == "chummer.public-play-pwa-mirror.v1"
    assert contract["assetPolicyCount"] == len(inventory["assets"]) == 12
    assert contract["dependencyPolicyCount"] == len(inventory["generatorDependencies"]) == 4
    assert contract["inventoryPath"] == "Chummer.Run.Api/play-pwa-required-inventory.json"
    assert contract["inventorySha256"] == hashlib.sha256(INVENTORY_PATH.read_bytes()).hexdigest()
    assert contract["assets"]
    expected_exact = [item for item in inventory["assets"] if item["kind"] == "exact"]
    assert len(contract["assets"]) == len(expected_exact)
    assert {item["projection"] for item in contract["assets"]} == {
        item["projection"] for item in expected_exact
    }
    assert len({item["source"] for item in contract["assets"]}) == len(contract["assets"])
    assert len({item["projection"] for item in contract["assets"]}) == len(contract["assets"])
    assert len({item["role"] for item in contract["assets"]}) == len(contract["assets"])
    source_available = source_root.is_dir()

    for asset in contract["assets"]:
        source = source_root / asset["source"]
        projection = RUN_PROJECT / asset["projection"]
        projection_bytes = projection.read_bytes()

        assert hashlib.sha256(projection_bytes).hexdigest() == asset["sha256"]
        if source_available:
            assert source.read_bytes() == projection_bytes, asset["projection"]
        assert asset["contentType"]
        assert asset["kind"] == "exact"
        assert asset["role"]
        assert asset["cacheControl"] in {
            "public, max-age=300, must-revalidate",
            "no-cache, no-store, must-revalidate",
        }


def test_root_worker_transform_is_digest_closed_and_semantically_narrower() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    source_root = (ROOT / contract["sourceRepository"]).resolve()
    transforms = contract["executableTransforms"]

    assert len(transforms) == 1
    transform = transforms[0]
    required_transform = next(item for item in json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))["assets"] if item["kind"] == "transform")
    for field in ("source", "projection", "kind", "role", "contentType", "cacheControl"):
        assert transform[field] == required_transform[field]
    source = (source_root / transform["source"]).read_bytes()
    projection = (RUN_PROJECT / transform["projection"]).read_bytes()
    assert hashlib.sha256(source).hexdigest() == transform["sourceSha256"]
    assert hashlib.sha256(projection).hexdigest() == transform["projectionSha256"]

    source_text = source.decode("utf-8")
    projection_text = projection.decode("utf-8")
    assert 'const CACHE_CONTRACT = "play-source-v2";' in source_text
    assert 'const CACHE_CONTRACT = "run-api-projection-v2";' in projection_text
    assert '"/manifest.webmanifest"' in source_text
    assert '"/manifest.play.webmanifest"' in projection_text
    assert '"/mobile-turn-companion.js"' not in projection_text
    for worker in (source_text, projection_text):
        assert "self.skipWaiting()" not in worker
        assert "self.clients.claim()" not in worker
        assert "isExpectedPublicAssetResponse" in worker
        assert 'url.pathname.startsWith("/api/play/")' in worker


def test_root_worker_projection_has_digest_pinned_generator_config_and_template() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    generator = contract["generator"]

    assert generator["contract"] == "play-root-worker-projection-generator-v1"
    assert generator["command"] == "python3 scripts/generate_public_play_worker_projection.py"
    for name in ("script", "config", "template", "inventory"):
        path = ROOT / generator[name]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == generator[f"{name}Sha256"]
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert len(generator["dependencies"]) == len(inventory["generatorDependencies"])
    assert {item["role"] for item in generator["dependencies"]} == {
        item["role"] for item in inventory["generatorDependencies"]
    }
