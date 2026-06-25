#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import io
import json
from pathlib import Path
import textwrap
from typing import Any

from PIL import Image


CONTRACT_NAME = "chummer.origin_edition.pdf_materialization.v1"
PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN = 54
FONT_SIZE = 11
LEADING = 15
LINES_PER_PAGE = 43
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


def _pdf_string(value: str) -> str:
    return "(" + value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def _jpeg_bytes(path: Path) -> tuple[bytes, int, int]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        output = io.BytesIO()
        rgb.save(output, format="JPEG", quality=92)
        return output.getvalue(), rgb.width, rgb.height


def _wrap_story(text: str) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(paragraph, width=88, break_long_words=False, replace_whitespace=False))
    return lines


def _first_story_line(story: str) -> str:
    for line in story.splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            return text
    return ""


def _starts_without_preamble(story: str) -> bool:
    first = _first_story_line(story).lower()
    return bool(first) and not any(first.startswith(prefix) for prefix in PREAMBLE_PREFIXES)


def _text_pages(story: str) -> list[list[str]]:
    lines = _wrap_story(story)
    pages: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        current.append(line)
        if len(current) >= LINES_PER_PAGE:
            pages.append(current)
            current = []
    if current:
        pages.append(current)
    return pages


def _build_text_stream(lines: list[str]) -> bytes:
    parts = [
        "BT",
        f"/F1 {FONT_SIZE} Tf",
        f"{LEADING} TL",
        f"{MARGIN} {PAGE_HEIGHT - MARGIN} Td",
    ]
    for line in lines:
        if line:
            parts.append(f"{_pdf_string(line)} Tj")
        parts.append("T*")
    parts.append("ET")
    return ("\n".join(parts) + "\n").encode("latin-1", errors="replace")


def _build_pdf(cover_path: Path, story: str) -> bytes:
    image_bytes, image_width, image_height = _jpeg_bytes(cover_path)
    image_fit_width = PAGE_WIDTH
    image_fit_height = PAGE_WIDTH * image_height / image_width
    if image_fit_height > PAGE_HEIGHT:
        image_fit_height = PAGE_HEIGHT
        image_fit_width = PAGE_HEIGHT * image_width / image_height
    image_x = (PAGE_WIDTH - image_fit_width) / 2
    image_y = (PAGE_HEIGHT - image_fit_height) / 2
    cover_stream = (
        f"q\n{image_fit_width:.3f} 0 0 {image_fit_height:.3f} {image_x:.3f} {image_y:.3f} cm\n/Im0 Do\nQ\n"
    ).encode("ascii")

    objects: list[bytes] = []

    def add(body: bytes | str) -> int:
        if isinstance(body, str):
            body = body.encode("latin-1", errors="replace")
        objects.append(body)
        return len(objects)

    catalog_id = add("<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add(b"")
    image_id = add(
        b"<< /Type /XObject /Subtype /Image /Width "
        + str(image_width).encode("ascii")
        + b" /Height "
        + str(image_height).encode("ascii")
        + b" /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length "
        + str(len(image_bytes)).encode("ascii")
        + b" >>\nstream\n"
        + image_bytes
        + b"\nendstream"
    )
    font_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>")
    cover_content_id = add(
        b"<< /Length " + str(len(cover_stream)).encode("ascii") + b" >>\nstream\n" + cover_stream + b"endstream"
    )
    page_ids: list[int] = []
    cover_page_id = add(
        f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
        f"/Resources << /XObject << /Im0 {image_id} 0 R >> >> /Contents {cover_content_id} 0 R >>"
    )
    page_ids.append(cover_page_id)

    for page_lines in _text_pages(story):
        stream = _build_text_stream(page_lines)
        content_id = add(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream")
        page_id = add(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        page_ids.append(page_id)

    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(page_ids)} >>"
    ).encode("ascii")
    assert catalog_id == 1

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def materialize(
    *,
    manuscript: Path,
    cover: Path,
    output_pdf: Path,
    receipt: Path,
    namespace: str,
) -> dict[str, Any]:
    story = manuscript.read_text(encoding="utf-8").strip()
    if not story:
        raise ValueError("manuscript is empty")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.write_bytes(_build_pdf(cover, story))
    pdf_sha = _sha256_file(output_pdf)
    cover_sha = _sha256_file(cover)
    manuscript_sha = _sha256_file(manuscript)
    story_starts_without_preamble = _starts_without_preamble(story)
    tokens = [
        namespace,
        pdf_sha,
        cover_sha,
        manuscript_sha,
        "pdf_cover_embedded",
    ]
    if story_starts_without_preamble:
        tokens.append("story_starts_without_preamble")
    payload: dict[str, Any] = {
        "contractName": CONTRACT_NAME,
        "operation": "origin_edition_pdf_materialization",
        "provider": "Chummer",
        "status": "verified",
        "completedAtUtc": _now_iso(),
        "namespace": namespace,
        "pdfPath": (Path(namespace) / "dossier" / output_pdf.name).as_posix(),
        "pdfSha256": pdf_sha,
        "coverSha256": cover_sha,
        "manuscriptSha256": manuscript_sha,
        "storyStartsWithoutPreamble": story_starts_without_preamble,
        "coverEmbeddedOnFirstPage": True,
        "rawRuntimePathsExposed": False,
        "tokens": tokens,
    }
    _write_json(receipt, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize a covered Origin Edition PDF from approved manuscript text.")
    parser.add_argument("--manuscript", required=True, type=Path)
    parser.add_argument("--cover", required=True, type=Path)
    parser.add_argument("--output-pdf", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--namespace", required=True)
    args = parser.parse_args()
    payload = materialize(
        manuscript=args.manuscript,
        cover=args.cover,
        output_pdf=args.output_pdf,
        receipt=args.receipt,
        namespace=args.namespace,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
