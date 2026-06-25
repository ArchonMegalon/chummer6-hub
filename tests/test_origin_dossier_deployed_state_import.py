from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_origin_dossier_deployed_state_import.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_origin_dossier_deployed_state_import", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")
    return path


def test_state_import_copies_artifacts_and_writes_container_visible_index(tmp_path: Path) -> None:
    module = load_module()
    evidence = tmp_path / "evidence"
    host_state = tmp_path / "state"
    book = write(evidence / "origin.chummer.run/Case/Ari/Ghost/dossier/ebook.epub", b"epub bytes")
    cover = write(evidence / "origin.chummer.run/Case/Ari/Ghost/cover.jpg", b"cover bytes")
    video = write(evidence / "origin.chummer.run/Case/Ari/Ghost/movie/movie.mp4", b"video bytes")
    receipt = write(evidence / "provider.receipt.json", '{"operation":"provider_manuscript_import"}')
    live_import = evidence / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import.write_text(
        json.dumps(
            {
                "importRequest": {
                    "projectId": "case-ari-ghost",
                    "title": "Ghost Origin Dossier",
                    "runnerAlias": "Ghost",
                    "publicationState": "published_for_owner",
                    "originEditionNamespace": "origin.chummer.run/Case/Ari/Ghost",
                    "bookArtifactPath": str(book),
                    "ebookArtifactPath": str(book),
                    "storySceneCoverPath": str(cover),
                    "dossierVideoPath": str(video),
                    "providerManuscriptReceiptPath": str(receipt),
                    "audiobookshelfShareUrl": "https://audio.chummer.run/share/ghost-audio",
                    "audiobookshelfDossierShareUrl": "https://audio.chummer.run/share/ghost-dossier",
                    "audiobookshelfAudiobookShareUrl": "https://audio.chummer.run/share/ghost-audio",
                    "providerAuthoredManuscriptImported": True,
                    "undetectableHumanizerApplied": True,
                    "bookArtifactVerified": True,
                    "dossierVideoVerified": True,
                    "storySceneCoverUsesSelectedCharacterFace": True,
                    "audiobookshelfPlaybackVerified": True,
                    "telegramShareDelivered": True,
                }
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "state-import.receipt.json"
    result = module.materialize(
        live_import=live_import,
        host_state_root=host_state,
        container_state_root=Path("/app/state"),
        subject_id=None,
        owner_user_id=None,
        output_receipt=output,
    )

    index = json.loads((host_state / "origin-dossier-publications.json").read_text(encoding="utf-8"))
    entry = index["publications"][0]
    assert result["status"] == "verified"
    assert result["deploymentPerformed"] is False
    assert result["restartRequiredForExistingContainer"] is True
    assert entry["subjectId"] == "subject.origin-edition.51dc324fd03a0fb6"
    assert entry["ownerSubjectId"] == entry["subjectId"]
    assert entry["bookArtifactPath"].startswith("/app/state/origin-dossier-editions/")
    assert entry["storySceneCoverPath"].startswith("/app/state/origin-dossier-editions/")
    assert entry["dossierVideoPath"].startswith("/app/state/origin-dossier-editions/")
    assert Path(str(entry["bookArtifactPath"]).replace("/app/state", str(host_state))).is_file()
    assert output.is_file()


def test_state_import_rejects_missing_artifact(tmp_path: Path) -> None:
    module = load_module()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    live_import = evidence / "ORIGIN_DOSSIER_LIVE_IMPORT_REQUEST.generated.json"
    live_import.write_text(
        json.dumps(
            {
                "importRequest": {
                    "projectId": "case-ari-ghost",
                    "originEditionNamespace": "origin.chummer.run/Case/Ari/Ghost",
                    "bookArtifactPath": str(evidence / "missing.epub"),
                }
            }
        ),
        encoding="utf-8",
    )

    try:
        module.materialize(
            live_import=live_import,
            host_state_root=tmp_path / "state",
            container_state_root=Path("/app/state"),
            subject_id="subject.case",
            owner_user_id=None,
            output_receipt=None,
        )
    except module.StateImportError as exc:
        assert "missing or empty" in str(exc)
    else:
        raise AssertionError("expected missing artifact to be rejected")
