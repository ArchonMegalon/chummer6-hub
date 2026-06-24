from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_origin_dossier_fallback_reel_generator_is_removed() -> None:
    assert not (ROOT / "scripts" / "build_origin_dossier_fallback_reel.py").exists()


def test_origin_dossier_fallback_media_tokens_do_not_return() -> None:
    forbidden = (
        "build_origin_dossier_fallback_reel",
        "origin_dossier_fallback_reel",
        "ORIGIN_DOSSIER_FALLBACK_REEL",
        "UNMIXR_ORIGIN_DOSSIER_FALLBACK_REEL",
        "chummer.origin_dossier_fallback_reel",
    )
    scanned_roots = (
        ROOT / "scripts",
        ROOT / "tests" / "public",
        ROOT / "Chummer.Run.Api",
        ROOT / "Chummer.Run.Contracts",
    )
    offenders: list[str] = []
    for scanned_root in scanned_roots:
        if not scanned_root.exists():
            continue
        for path in scanned_root.rglob("*"):
            if path.is_dir() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp3", ".mp4", ".webm"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.relative_to(ROOT)}:{token}")
    assert offenders == []
