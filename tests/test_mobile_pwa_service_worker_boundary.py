from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_mobile_pwa_service_worker_boundary.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_mobile_pwa_service_worker_boundary", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_worker_classifier_distinguishes_portal_and_play_root_workers() -> None:
    module = load_module()

    assert module.classify_worker('const CACHE_NAME = "chummer-public-v4"; function handlePush() {}') == "portal_public_root_worker"
    assert module.classify_worker('const CACHE_VERSION = "play-shell-v14"; const SHELL_ASSETS = [];') == "play_root_worker"
    assert module.classify_worker("const CACHE_NAME = \"unknown\";") == "unknown"


def test_registration_boundary_accepts_shared_portal_or_scoped_mobile_worker() -> None:
    module = load_module()
    shared = module.extract_service_worker_registrations('navigator.serviceWorker.register("/service-worker.js", { scope: "/" });')
    scoped = module.extract_service_worker_registrations('navigator.serviceWorker.register("/mobile-sw.js", { scope: "/mobile" });')

    assert module.classify_registration_boundary(shared, "portal_public_root_worker") == "shared_portal_root_worker"
    assert module.classify_registration_boundary(shared, "play_root_worker") == "unknown"
    assert module.classify_registration_boundary(scoped, "play_root_worker") == "scoped_mobile_worker"
