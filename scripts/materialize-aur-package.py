#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKAGE_NAME = "chummer6-bin"
CONTRACT_NAME = "chummer.downloads.aur_packages.v1"
SOURCE_ARCHIVE_NAME = f"{PACKAGE_NAME}-aur-source.tar.gz"
PKGBUILD_NAME = f"{PACKAGE_NAME}.PKGBUILD"
SRCINFO_NAME = f"{PACKAGE_NAME}.SRCINFO"


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iter_artifacts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("artifacts")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    rows = payload.get("downloads")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def clean_token(value: object) -> str:
    return str(value or "").strip().lower()


def find_linux_deb(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exact = [
        row for row in rows
        if clean_token(row.get("artifactId") or row.get("id")) == "avalonia-linux-x64-installer"
    ]
    if exact:
        return exact[0]

    candidates: list[dict[str, Any]] = []
    for row in rows:
        file_name = str(row.get("fileName") or Path(str(row.get("downloadUrl") or row.get("url") or "")).name).strip()
        platform = clean_token(row.get("platform") or row.get("platformId"))
        arch = clean_token(row.get("arch"))
        kind = clean_token(row.get("kind") or row.get("flavor"))
        if file_name.endswith(".deb") and "linux" in platform and (not arch or arch == "x64") and kind in {"", "installer"}:
            candidates.append(row)
    if not candidates:
        raise SystemExit("No Linux x64 .deb artifact was found in the release manifest.")
    return candidates[0]


def package_version(release_version: str) -> str:
    match = re.fullmatch(r"run-(\d{8})-(\d{6})", release_version.strip())
    if match:
        return f"{match.group(1)}.{match.group(2)}"

    normalized = re.sub(r"[^A-Za-z0-9._+]+", "_", release_version.strip())
    normalized = normalized.strip("._+")
    return normalized or "0"


def render_pkgbuild(*, pkgver: str, deb_file_name: str, deb_url: str, deb_sha256: str) -> str:
    return f"""# Maintainer: Chummer release automation <release@chummer.run>
pkgname={PACKAGE_NAME}
pkgver={pkgver}
pkgrel=1
pkgdesc='Shadowrun character and campaign companion desktop build'
arch=('x86_64')
url='https://chummer.run'
license=('custom')
depends=('fontconfig' 'gtk3' 'libx11' 'libxcursor' 'libxext' 'libxfixes' 'libxi' 'libxinerama' 'libxrandr' 'libxrender' 'libglvnd' 'zlib')
source_x86_64=('{deb_file_name}::{deb_url}')
sha256sums_x86_64=('{deb_sha256}')
options=('!strip')

package() {{
  bsdtar -xf "$srcdir/{deb_file_name}" -C "$srcdir"
  local data_tar
  data_tar="$(find "$srcdir" -maxdepth 1 -type f -name 'data.tar*' | sort | head -n 1)"
  if [[ -z "$data_tar" ]]; then
    echo "Chummer .deb payload is missing data.tar.*" >&2
    return 1
  fi

  bsdtar -xf "$data_tar" -C "$pkgdir"
}}
"""


def render_srcinfo(*, pkgver: str, deb_file_name: str, deb_url: str, deb_sha256: str) -> str:
    depends = [
        "fontconfig",
        "gtk3",
        "libx11",
        "libxcursor",
        "libxext",
        "libxfixes",
        "libxi",
        "libxinerama",
        "libxrandr",
        "libxrender",
        "libglvnd",
        "zlib",
    ]
    lines = [
        f"pkgbase = {PACKAGE_NAME}",
        "\tpkgdesc = Shadowrun character and campaign companion desktop build",
        f"\tpkgver = {pkgver}",
        "\tpkgrel = 1",
        "\turl = https://chummer.run",
        "\tarch = x86_64",
        "\tlicense = custom",
    ]
    lines.extend(f"\tdepends = {item}" for item in depends)
    lines.extend([
        f"\tsource_x86_64 = {deb_file_name}::{deb_url}",
        f"\tsha256sums_x86_64 = {deb_sha256}",
        "",
        f"pkgname = {PACKAGE_NAME}",
        "",
    ])
    return "\n".join(lines)


def render_readme(*, release_version: str, deb_file_name: str, deb_sha256: str) -> str:
    return f"""# {PACKAGE_NAME}

This AUR-compatible source package installs the same Chummer Linux desktop build
published on chummer.run.

- Release: `{release_version}`
- Source package: `{deb_file_name}`
- Source SHA-256: `{deb_sha256}`

Install from this directory with:

```sh
makepkg -si
```
"""


def tar_bytes(files: dict[str, str]) -> bytes:
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0) as gzip_file:
        with tarfile.open(fileobj=gzip_file, mode="w") as archive:
            for relative_name, content in files.items():
                data = content.encode("utf-8")
                info = tarfile.TarInfo(f"{PACKAGE_NAME}/{relative_name}")
                info.size = len(data)
                info.mode = 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(data))
    return compressed.getvalue()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def file_url(prefix: str, file_name: str) -> str:
    return f"{prefix.rstrip('/')}/{file_name}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize the Chummer Arch/AUR sidecar package.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--files-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--downloads-prefix", default="https://chummer.run/downloads/files")
    parser.add_argument("--optional", action="store_true", help="Remove stale AUR sidecars and exit when no Linux .deb is published.")
    args = parser.parse_args()

    manifest_path = args.manifest
    files_root = args.files_root
    output_root = args.output_root
    output_files = output_root / "files"

    payload = read_json(manifest_path)
    try:
        linux_deb = find_linux_deb(iter_artifacts(payload))
    except SystemExit:
        if not args.optional:
            raise
        for stale_path in (
            output_root / "aur-packages.json",
            output_files / SOURCE_ARCHIVE_NAME,
            output_files / PKGBUILD_NAME,
            output_files / SRCINFO_NAME,
        ):
            stale_path.unlink(missing_ok=True)
        print(f"no linux deb in {manifest_path}; removed stale AUR sidecars")
        return
    release_version = str(linux_deb.get("version") or linux_deb.get("releaseVersion") or payload.get("version") or "unpublished").strip()
    channel = str(linux_deb.get("channelId") or linux_deb.get("channel") or payload.get("channelId") or payload.get("channel") or "stable").strip()
    deb_file_name = str(linux_deb.get("fileName") or Path(str(linux_deb.get("downloadUrl") or linux_deb.get("url") or "")).name).strip()
    if not deb_file_name:
        raise SystemExit("Linux .deb artifact is missing fileName/downloadUrl.")
    deb_path = files_root / deb_file_name
    if not deb_path.is_file():
        raise SystemExit(f"Linux .deb artifact is missing from files root: {deb_path}")

    actual_deb_sha = sha256(deb_path)
    expected_deb_sha = str(linux_deb.get("sha256") or "").strip().lower()
    if expected_deb_sha and actual_deb_sha != expected_deb_sha:
        raise SystemExit(f"{deb_file_name}: sha256 {actual_deb_sha} != manifest {expected_deb_sha}")

    deb_url = str(linux_deb.get("downloadUrl") or linux_deb.get("url") or "").strip()
    if not deb_url:
        deb_url = file_url(args.downloads_prefix, deb_file_name)
    pkgver = package_version(release_version)

    pkgbuild = render_pkgbuild(pkgver=pkgver, deb_file_name=deb_file_name, deb_url=deb_url, deb_sha256=actual_deb_sha)
    srcinfo = render_srcinfo(pkgver=pkgver, deb_file_name=deb_file_name, deb_url=deb_url, deb_sha256=actual_deb_sha)
    readme = render_readme(release_version=release_version, deb_file_name=deb_file_name, deb_sha256=actual_deb_sha)

    output_files.mkdir(parents=True, exist_ok=True)
    pkgbuild_path = output_files / PKGBUILD_NAME
    srcinfo_path = output_files / SRCINFO_NAME
    source_archive_path = output_files / SOURCE_ARCHIVE_NAME
    write_text(pkgbuild_path, pkgbuild)
    write_text(srcinfo_path, srcinfo)
    source_archive_path.write_bytes(tar_bytes({"PKGBUILD": pkgbuild, ".SRCINFO": srcinfo, "README.md": readme}))

    pkgbuild_sha = sha256(pkgbuild_path)
    srcinfo_sha = sha256(srcinfo_path)
    source_archive_sha = sha256(source_archive_path)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    catalog = {
        "contractName": CONTRACT_NAME,
        "contract_name": CONTRACT_NAME,
        "generatedAt": now,
        "generated_at": now,
        "version": release_version,
        "channel": channel,
        "packages": [
            {
                "id": PACKAGE_NAME,
                "packageName": PACKAGE_NAME,
                "packageVersion": pkgver,
                "title": "Arch / CachyOS",
                "summary": "AUR-compatible source package for the same Linux build published as the .deb.",
                "platformLabel": "Arch / CachyOS",
                "installCommand": "Download the AUR source, extract it, then run makepkg -si.",
                "sourceArchiveFileName": SOURCE_ARCHIVE_NAME,
                "sourceArchiveUrl": file_url(args.downloads_prefix, SOURCE_ARCHIVE_NAME),
                "sourceArchiveSha256": source_archive_sha,
                "sourceArchiveSizeBytes": source_archive_path.stat().st_size,
                "pkgbuildFileName": PKGBUILD_NAME,
                "pkgbuildUrl": file_url(args.downloads_prefix, PKGBUILD_NAME),
                "pkgbuildSha256": pkgbuild_sha,
                "srcinfoFileName": SRCINFO_NAME,
                "srcinfoUrl": file_url(args.downloads_prefix, SRCINFO_NAME),
                "srcinfoSha256": srcinfo_sha,
                "upstreamArtifactId": str(linux_deb.get("artifactId") or linux_deb.get("id") or "").strip(),
                "upstreamArtifactFileName": deb_file_name,
                "upstreamArtifactUrl": deb_url,
                "upstreamArtifactSha256": actual_deb_sha,
                "upstreamArtifactSizeBytes": deb_path.stat().st_size,
            }
        ],
    }
    write_text(output_root / "aur-packages.json", json.dumps(catalog, indent=2) + "\n")
    print(output_root / "aur-packages.json")


if __name__ == "__main__":
    main()
