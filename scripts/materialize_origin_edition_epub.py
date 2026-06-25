#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import html
import json
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


CONTRACT_NAME = "chummer.origin_edition.epub_materialization.v1"
PREAMBLE_PREFIXES = (
    "introduction",
    "intro:",
    "non-story intro",
    "preamble",
    "author's note",
    "authors note",
    "about this book",
    "this origin dossier",
    "this story",
    "the following",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _runner_from_namespace(namespace: str) -> str:
    parts = [part for part in str(namespace or "").strip("/").split("/") if part]
    return parts[-1] if parts else "Runner"


def _first_story_heading(story: str) -> str:
    for line in story.splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            return text
    return "Origin Dossier"


def _starts_without_preamble(story: str) -> bool:
    first = _first_story_heading(story).lower()
    return bool(first) and not any(first.startswith(prefix) for prefix in PREAMBLE_PREFIXES)


def _paragraphs(story: str) -> str:
    parts = []
    for paragraph in story.splitlines():
        paragraph = paragraph.strip()
        if paragraph:
            parts.append(f"<p>{html.escape(paragraph)}</p>")
    return "\n".join(parts)


def _write_epub_tree(
    *,
    manuscript: Path,
    cover: Path,
    dossier_dir: Path,
    namespace: str,
    book_title: str,
    runner_name: str,
) -> dict[str, str]:
    story = manuscript.read_text(encoding="utf-8").strip()
    if not story:
        raise ValueError("manuscript is empty")
    story_title = _first_story_heading(story)
    book_identifier = f"urn:chummer:origin-edition:{_sha256_text(namespace)[:24]}"

    epub_root = dossier_dir / "EPUB"
    meta_inf = dossier_dir / "META-INF"
    images = epub_root / "images"
    images.mkdir(parents=True, exist_ok=True)
    meta_inf.mkdir(parents=True, exist_ok=True)

    (dossier_dir / "mimetype").write_text("application/epub+zip", encoding="ascii")
    (meta_inf / "container.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        encoding="utf-8",
    )
    (epub_root / "style.css").write_text(
        """body{font-family:serif;line-height:1.55;margin:8%;color:#17120d;background:#f7f0e3}h1{font-size:1.8em;margin-bottom:1.2em}p{margin:0 0 1em}img.cover{max-width:100%;height:auto;display:block;margin:0 auto 2em}""",
        encoding="utf-8",
    )
    (epub_root / "title.xhtml").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>{html.escape(book_title)}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body><img class="cover" src="images/cover.jpg" alt="{html.escape(runner_name)} origin scene cover"/><h1>{html.escape(book_title)}</h1></body>
</html>
""",
        encoding="utf-8",
    )
    (epub_root / "story.xhtml").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>{html.escape(story_title)}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body><h1>{html.escape(story_title)}</h1>
{_paragraphs(story)}
</body>
</html>
""",
        encoding="utf-8",
    )
    (epub_root / "nav.xhtml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en">
<head><title>Navigation</title></head>
<body><nav epub:type="toc"><ol><li><a href="title.xhtml">Cover</a></li><li><a href="story.xhtml">Story</a></li></ol></nav></body>
</html>
""",
        encoding="utf-8",
    )
    modified = _now_iso().replace("Z", "Z")
    (epub_root / "package.opf").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{book_identifier}</dc:identifier>
    <dc:title>{html.escape(book_title)}</dc:title>
    <dc:creator>Chummer Origin Studio</dc:creator>
    <dc:language>en-US</dc:language>
    <meta property="dcterms:modified">{modified}</meta>
    <meta name="cover" content="cover-image"/>
    <meta property="chummer:namespace">{html.escape(namespace)}</meta>
    <meta property="chummer:runner-name">{html.escape(runner_name)}</meta>
    <meta property="chummer:manuscript-sha256">{_sha256_file(manuscript)}</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="style" href="style.css" media-type="text/css"/>
    <item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>
    <item id="story" href="story.xhtml" media-type="application/xhtml+xml"/>
    <item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>
  </manifest>
  <spine>
    <itemref idref="title"/>
    <itemref idref="story"/>
  </spine>
</package>
""",
        encoding="utf-8",
    )
    (images / "cover.jpg").write_bytes(cover.read_bytes())
    return {"manuscriptSha256": _sha256_file(manuscript), "coverSha256": _sha256_file(cover)}


def _zip_epub(dossier_dir: Path, output_epub: Path) -> None:
    output_epub.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_epub, "w") as archive:
        archive.write(dossier_dir / "mimetype", "mimetype", compress_type=ZIP_STORED)
        for path in sorted(dossier_dir.rglob("*")):
            if path == output_epub or path.name == "mimetype" or not path.is_file():
                continue
            archive.write(path, path.relative_to(dossier_dir).as_posix(), compress_type=ZIP_DEFLATED)


def materialize(
    *,
    manuscript: Path,
    cover: Path,
    dossier_dir: Path,
    output_epub: Path,
    receipt: Path,
    namespace: str,
    book_title: str | None = None,
    runner_name: str | None = None,
) -> dict[str, Any]:
    resolved_runner_name = (runner_name or _runner_from_namespace(namespace)).strip() or "Runner"
    resolved_book_title = (book_title or f"{resolved_runner_name}: Origin Dossier").strip()
    hashes = _write_epub_tree(
        manuscript=manuscript,
        cover=cover,
        dossier_dir=dossier_dir,
        namespace=namespace,
        book_title=resolved_book_title,
        runner_name=resolved_runner_name,
    )
    _zip_epub(dossier_dir, output_epub)
    epub_sha = _sha256_file(output_epub)
    story_starts_without_preamble = _starts_without_preamble(manuscript.read_text(encoding="utf-8"))
    tokens = [
        namespace,
        epub_sha,
        hashes["coverSha256"],
        hashes["manuscriptSha256"],
        "ebook_cover_embedded",
        "accepted_humanized_manuscript_embedded",
    ]
    if story_starts_without_preamble:
        tokens.append("story_starts_without_preamble")
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "operation": "origin_edition_epub_materialization",
        "provider": "Chummer",
        "status": "verified",
        "completedAtUtc": _now_iso(),
        "namespace": namespace,
        "runnerName": resolved_runner_name,
        "bookTitle": resolved_book_title,
        "epubPath": (Path(namespace) / "dossier" / output_epub.name).as_posix(),
        "epubSha256": epub_sha,
        "coverSha256": hashes["coverSha256"],
        "manuscriptSha256": hashes["manuscriptSha256"],
        "storyStartsWithoutPreamble": story_starts_without_preamble,
        "coverEmbedded": True,
        "rawRuntimePathsExposed": False,
        "tokens": tokens,
    }
    _write_json(receipt, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize an Origin Edition EPUB from accepted manuscript text.")
    parser.add_argument("--manuscript", required=True, type=Path)
    parser.add_argument("--cover", required=True, type=Path)
    parser.add_argument("--dossier-dir", required=True, type=Path)
    parser.add_argument("--output-epub", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--book-title")
    parser.add_argument("--runner-name")
    args = parser.parse_args()
    payload = materialize(
        manuscript=args.manuscript,
        cover=args.cover,
        dossier_dir=args.dossier_dir,
        output_epub=args.output_epub,
        receipt=args.receipt,
        namespace=args.namespace,
        book_title=args.book_title,
        runner_name=args.runner_name,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
