from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_origin_edition_final_bundle.py"


def load_module():
    spec = importlib.util.spec_from_file_location("origin_edition_final_bundle", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_file(path: Path, payload: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8")
    return path


def receipt(path: Path, *, status: str = "pass", gold: bool = True, extra: dict | None = None) -> Path:
    payload = {
        "contractName": "test.receipt",
        "operation": path.stem,
        "provider": "test",
        "status": status,
        "goldEligible": gold,
        "createdAtUtc": "2026-06-25T00:00:00Z",
    }
    if extra:
        payload.update(extra)
    return write_json(path, payload)


def build_bundle(
    tmp_path: Path,
    *,
    namespace: str = "origin.chummer.run/Varga/Mira/Kestrel",
    runner: str = "Kestrel",
    m4b_name: str = "kestrel-origin.m4b",
) -> Path:
    root = tmp_path / "bundle"
    edition = root / namespace
    write_json(root / "approved-sample-runner-canon.json", {"runner": runner, "status": "approved"})
    write_file(root / "provider-manuscript-draft.md", "Rain made the clinic sign stutter.\nNobody gets sold.\n")
    receipt(root / "undetectable-humanizer.receipt.json")
    receipt(root / "undetectable-humanizer-quality-gate.receipt.json")
    write_file(edition / "cover.jpg", b"cover")
    write_file(edition / "dossier" / "ebook.epub", b"epub")
    write_file(edition / "dossier" / "book.pdf", b"%PDF-1.4\n")
    receipt(edition / "dossier" / "pdf-cover.receipt.json")
    receipt(edition / "dossier" / "audiobookshelf-dossier-import.receipt.json")
    write_file(edition / "audiobook" / m4b_name, b"m4b")
    receipt(edition / "audiobook" / "m4b-provider-import-gate.receipt.json")
    receipt(edition / "audiobook" / "audiobookshelf-import.receipt.json")
    receipt(edition / "cover-consistency-strict.receipt.json")
    write_file(edition / "movie" / "movie.mp4", b"mp4")
    receipt(edition / "movie" / "dossier-video.receipt.json")
    return root


def surface(result: dict, name: str) -> dict:
    return next(item for item in result["surfaces"] if item["name"] == name)


def test_final_bundle_audit_passes_complete_clean_bundle(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)

    result = module.audit(root)

    assert result["status"] == "pass"
    assert result["goldEligible"] is True
    assert result["blockedSurfaces"] == []
    assert surface(result, "real_m4b_artifact")["candidateCount"] == 1


def test_final_bundle_audit_uses_origin_edition_context_namespace(tmp_path: Path) -> None:
    module = load_module()
    namespace = "origin.chummer.run/Case/Ari/Ghost"
    root = build_bundle(tmp_path, namespace=namespace, runner="Ghost", m4b_name="ghost-origin.m4b")
    context = module.OriginEditionContext.from_env(
        project_id="case-ari-ghost",
        family_name="Case",
        given_name="Ari",
        runner_name="Ghost",
    )

    result = module.audit(root, context=context)

    assert result["status"] == "pass"
    assert result["namespace"] == namespace
    assert result["projectId"] == "case-ari-ghost"
    assert surface(result, "cover")["path"] == f"{namespace}/cover.jpg"
    assert surface(result, "real_m4b_artifact")["path"] == f"{namespace}/audiobook/*.m4b"


def test_final_bundle_audit_blocks_failed_humanizer_quality(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)
    receipt(root / "undetectable-humanizer-quality-gate.receipt.json", status="failed_quality_gate", gold=False)

    result = module.audit(root)

    assert result["status"] == "blocked"
    assert "humanizer_quality_receipt" in result["blockedSurfaces"]
    assert surface(result, "humanizer_quality_receipt")["status"] == "blocked_not_pass"


def test_final_bundle_audit_blocks_missing_m4b_and_audiobook_share_receipt(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)
    (root / "origin.chummer.run" / "Varga" / "Mira" / "Kestrel" / "audiobook" / "kestrel-origin.m4b").unlink()
    (root / "origin.chummer.run" / "Varga" / "Mira" / "Kestrel" / "audiobook" / "audiobookshelf-import.receipt.json").unlink()

    result = module.audit(root)

    assert result["status"] == "blocked"
    assert "real_m4b_artifact" in result["blockedSurfaces"]
    assert "audiobookshelf_audiobook_receipt" in result["blockedSurfaces"]


def test_final_bundle_audit_blocks_fallback_marker_in_manuscript(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)
    write_file(root / "provider-manuscript-draft.md", "fallback narration placeholder\n")

    result = module.audit(root)

    assert result["status"] == "blocked"
    assert "provider_manuscript" in result["blockedSurfaces"]
    assert surface(result, "provider_manuscript")["status"] == "blocked_rejected_marker"


def test_final_bundle_audit_writes_receipt(tmp_path: Path) -> None:
    module = load_module()
    root = build_bundle(tmp_path)
    output = tmp_path / "receipt.json"

    result = module.audit(root, output)

    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert sha256_file(output)
