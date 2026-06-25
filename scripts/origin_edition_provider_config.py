from __future__ import annotations

import os
from urllib.parse import urlparse


DEFAULT_TRUSTED_AUDIOBOOKSHELF_HOSTS = (
    "audio.chummer.run",
    "audiobookshelf.chummer.run",
    "audiobookshelf.girschele.com",
)


def trusted_audiobookshelf_hosts() -> tuple[str, ...]:
    raw = os.environ.get("CHUMMER_ORIGIN_AUDIOBOOKSHELF_TRUSTED_HOSTS", "")
    hosts = [host.strip().lower() for host in raw.split(",") if host.strip()]
    return tuple(dict.fromkeys(hosts or DEFAULT_TRUSTED_AUDIOBOOKSHELF_HOSTS))


def is_trusted_audiobookshelf_share(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    return (
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").lower() in trusted_audiobookshelf_hosts()
        and (parsed.path.startswith("/share/") or parsed.path.startswith("/audiobookshelf/share/"))
    )


def origin_owner_url(base_url: str, project_id: str, suffix: str = "") -> str:
    base = str(base_url or "").strip().rstrip("/")
    project = str(project_id or "").strip()
    clean_suffix = str(suffix or "").strip()
    if clean_suffix and not clean_suffix.startswith("/"):
        clean_suffix = "/" + clean_suffix
    return f"{base}/account/work/origin-dossiers/{project}{clean_suffix}"
