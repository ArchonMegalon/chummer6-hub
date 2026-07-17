from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path("/docker/chummercomplete/chummer.run-services")
CLOSURE_PATH = ROOT / "scripts" / "check_absolute_audit_closure.py"
SUBSTANCE_PATH = ROOT / "scripts" / "check_absolute_audit_substance.py"


def load_module(name: str, path: Path):
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_closure_status_is_pass_rejects_pass_shaped_receipt_with_failures() -> None:
    module = load_module("absolute_audit_closure_semantics", CLOSURE_PATH)

    assert module.status_is_pass(
        {
            "status": "pass",
            "failures": ["canonical domain proof contradicted by live receipt"],
        }
    ) is False


def test_closure_canonical_domain_rejects_pass_shaped_receipt_with_failed_gates() -> None:
    module = load_module("absolute_audit_closure_semantics_canonical", CLOSURE_PATH)

    ok, detail = module.validate_canonical_domain(
        {
            "status": "pass",
            "canonical_public_domain": "chummer.run",
            "domain_status": {"chummer6.run": "not_used"},
            "failed_gates": ["verify_canonical_domain_live"],
        }
    )

    assert ok is False
    assert "status=pass" in detail


def test_substance_status_is_pass_rejects_pass_shaped_receipt_with_failed_gates() -> None:
    module = load_module("absolute_audit_substance_semantics", SUBSTANCE_PATH)

    assert module.status_is_pass(
        {
            "status": "pass",
            "failed_gates": ["scan_public_claims"],
        }
    ) is False


def test_substance_canonical_domain_rejects_pass_shaped_receipt_with_failures() -> None:
    module = load_module("absolute_audit_substance_semantics_canonical", SUBSTANCE_PATH)

    with (
        patch.object(
            module,
            "load_json",
            return_value={
                "status": "pass",
                "canonical_public_domain": "chummer.run",
                "domain_status": {"chummer6.run": "not_used"},
                "failures": ["canonical domain proof contradicted by live alias check"],
            },
        ),
        patch.object(module, "find_manifest_route", return_value={"path": "/participate/codex", "must_exist": True}),
    ):
        check = module.validate_canonical_domain()

    assert check["ok"] is False
    assert "status=pass" in check["detail"]
