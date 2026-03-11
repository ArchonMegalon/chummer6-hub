#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-${CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL:-}}"

if [[ -z "${TARGET}" ]]; then
  echo "Provide a portal base URL or manifest path as the first argument (or set CHUMMER_PORTAL_DOWNLOADS_VERIFY_URL)." >&2
  exit 1
fi

python3 - "$TARGET" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

raw_target = (sys.argv[1] or "").strip()
if not raw_target:
    raise SystemExit("Manifest verification target was empty.")

require_published_version = os.environ.get("CHUMMER_PORTAL_DOWNLOADS_REQUIRE_PUBLISHED_VERSION", "").strip().lower() == "true"
verify_links = os.environ.get("CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS", "").strip().lower() == "true"
verify_timeout = float(os.environ.get("CHUMMER_PORTAL_DOWNLOADS_VERIFY_TIMEOUT", "30").strip() or "30")
manifest_url = None

if raw_target.startswith(("http://", "https://")):
    manifest_url = raw_target.rstrip("/")
    if not manifest_url.endswith("/downloads/releases.json"):
        manifest_url = f"{manifest_url}/downloads/releases.json"

    with urllib.request.urlopen(manifest_url, timeout=30) as response:
        manifest = json.load(response)

    source = manifest_url
else:
    manifest_path = Path(raw_target).expanduser()
    if manifest_path.is_dir():
        manifest_path = manifest_path / "releases.json"

    if not manifest_path.exists():
        raise SystemExit(f"Manifest file not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = str(manifest_path)

downloads = manifest.get("downloads") or []
if not isinstance(downloads, list) or not downloads:
    raise SystemExit(f"Manifest at {source} has no downloads.")

version = str(manifest.get("version") or "").strip()
if require_published_version and (not version or version.lower() == "unpublished"):
    raise SystemExit(
        f"Manifest at {source} has unpublished version '{version or '<missing>'}' while CHUMMER_PORTAL_DOWNLOADS_REQUIRE_PUBLISHED_VERSION=true."
    )

verified_links = 0
if verify_links:
    if verify_timeout <= 0:
        raise SystemExit("CHUMMER_PORTAL_DOWNLOADS_VERIFY_TIMEOUT must be greater than 0 when CHUMMER_PORTAL_DOWNLOADS_VERIFY_LINKS=true.")

    errors = []
    for index, artifact in enumerate(downloads):
        if not isinstance(artifact, dict):
            errors.append(f"downloads[{index}] is not an object.")
            continue

        raw_url = str(artifact.get("url") or "").strip()
        if not raw_url:
            errors.append(f"downloads[{index}] is missing url.")
            continue

        if raw_url.startswith(("http://", "https://")):
            resolved_url = raw_url
        elif manifest_url is not None:
            resolved_url = urllib.parse.urljoin(manifest_url, raw_url)
        else:
            parsed = urllib.parse.urlparse(raw_url)
            path_value = urllib.parse.unquote(parsed.path or "")
            if not path_value:
                errors.append(f"downloads[{index}] has invalid local url '{raw_url}'.")
                continue

            if path_value.startswith("/downloads/"):
                relative_path = path_value[len("/downloads/"):]
            else:
                relative_path = path_value.lstrip("/")
            if not relative_path:
                errors.append(f"downloads[{index}] resolves to empty local path from '{raw_url}'.")
                continue

            candidate = manifest_path.parent / relative_path
            if not candidate.exists() or not candidate.is_file():
                errors.append(f"downloads[{index}] file not found at '{candidate}'.")
                continue
            verified_links += 1
            continue

        try:
            request = urllib.request.Request(resolved_url, method="HEAD")
            with urllib.request.urlopen(request, timeout=verify_timeout) as response:
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as ex:
            if ex.code in (405, 501):
                try:
                    request = urllib.request.Request(resolved_url, method="GET")
                    with urllib.request.urlopen(request, timeout=verify_timeout) as response:
                        status = getattr(response, "status", 200)
                except Exception as fallback_ex:
                    errors.append(f"downloads[{index}] failed GET '{resolved_url}': {fallback_ex}")
                    continue
            else:
                errors.append(f"downloads[{index}] failed HEAD '{resolved_url}': HTTP {ex.code}")
                continue
        except Exception as ex:
            errors.append(f"downloads[{index}] failed HEAD '{resolved_url}': {ex}")
            continue

        if int(status) >= 400:
            errors.append(f"downloads[{index}] returned HTTP {status} for '{resolved_url}'.")
            continue

        verified_links += 1

    if errors:
        preview = "\n".join(errors[:10])
        suffix = "\n..." if len(errors) > 10 else ""
        raise SystemExit(
            f"Manifest at {source} failed artifact verification ({len(errors)} issue(s)):\n{preview}{suffix}"
        )

message = f"Verified manifest at {source} with {len(downloads)} artifact(s)."
if verify_links:
    message += f" Verified artifact links/files: {verified_links}."
print(message)
PY
