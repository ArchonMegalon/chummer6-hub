from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sanitize_portable_startup_smoke_receipts.py"
SPEC = importlib.util.spec_from_file_location("sanitize_portable_startup_smoke_receipts", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_receipt(path: Path, process_path: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "pass",
                "artifactSha256": "a" * 64,
                "processPath": process_path,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_sanitizes_linux_macos_and_windows_process_paths_without_changing_truth(tmp_path: Path) -> None:
    root = tmp_path / "published"
    smoke = root / "portal" / "startup-smoke"
    paths = {
        "linux": smoke / "startup-smoke-avalonia-linux-x64.receipt.json",
        "macos": smoke / "startup-smoke-avalonia-osx-arm64.receipt.json",
        "windows": smoke / "startup-smoke-avalonia-win-x64.receipt.json",
    }
    write_receipt(paths["linux"], "/home/runner/work/chummer")
    write_receipt(paths["macos"], "/Users/runner/work/Chummer.app")
    write_receipt(paths["windows"], r"C:\Users\runner\work\Chummer.exe")

    result = MODULE.sanitize_roots([root])

    assert result["status"] == "pass"
    assert result["sanitized_receipt_count"] == 3
    for path in paths.values():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["status"] == "pass"
        assert payload["artifactSha256"] == "a" * 64
        assert "/" not in payload["processPath"]
        assert "\\" not in payload["processPath"]
        assert payload["processPathDisclosure"] == "file_name_only"


def test_leaves_already_portable_receipt_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "published"
    path = root / "startup-smoke" / "startup-smoke-avalonia-linux-x64.receipt.json"
    write_receipt(path, "Chummer")
    before = path.read_bytes()

    result = MODULE.sanitize_roots([root])

    assert result["status"] == "pass"
    assert result["sanitized_receipt_count"] == 0
    assert path.read_bytes() == before


def test_operation_receipt_uses_root_aliases_and_never_records_host_roots(tmp_path: Path) -> None:
    root = tmp_path / "private-host-root"
    path = root / "startup-smoke" / "startup-smoke-avalonia-linux-x64.receipt.json"
    write_receipt(path, "/home/private-user/Chummer")

    result = MODULE.sanitize_roots([root])
    serialized = json.dumps(result)

    assert str(root) not in serialized
    assert "/home/private-user" not in serialized
    assert result["sanitized_receipts"] == [
        "root-1/startup-smoke/startup-smoke-avalonia-linux-x64.receipt.json"
    ]
