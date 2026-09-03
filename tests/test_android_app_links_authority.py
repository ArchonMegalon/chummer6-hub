from __future__ import annotations

import json
import re
import stat
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_LINKS = (
    REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / ".well-known" / "assetlinks.json"
)
PROGRAM = REPO_ROOT / "Chummer.Run.Api" / "Program.cs"
PROJECT = REPO_ROOT / "Chummer.Run.Api" / "Chummer.Run.Api.csproj"
DOCKERFILE = REPO_ROOT / "Chummer.Run.Api" / "Dockerfile"

PLAY_APP_SIGNING_CERTIFICATE_SHA256 = (
    "03:5D:F3:7B:31:C5:99:D3:22:1A:AB:FD:A7:D9:E3:CD:FE:65:75:2B:D6:E6:0E:70:C6:40:78:0C:51:DD:90:8F"
)
EXPECTED_ASSET_LINKS = [
    {
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "com.myexternalbrain.chummer",
            "sha256_cert_fingerprints": [PLAY_APP_SIGNING_CERTIFICATE_SHA256],
        },
    }
]


def test_android_asset_links_is_exact_strict_play_signing_authority() -> None:
    file_status = ASSET_LINKS.lstat()
    assert stat.S_ISREG(file_status.st_mode)
    assert not ASSET_LINKS.is_symlink()

    source = ASSET_LINKS.read_bytes()
    expected_source = (json.dumps(EXPECTED_ASSET_LINKS, indent=2) + "\n").encode("utf-8")
    assert source == expected_source

    payload = json.loads(source)
    assert payload == EXPECTED_ASSET_LINKS
    assert re.fullmatch(
        r"[0-9A-F]{2}(?::[0-9A-F]{2}){31}",
        payload[0]["target"]["sha256_cert_fingerprints"][0],
    )


def test_android_asset_links_is_in_the_public_edge_publish_path() -> None:
    project = PROJECT.read_text(encoding="utf-8")
    program = PROGRAM.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert '<Project Sdk="Microsoft.NET.Sdk.Web">' in project
    assert "FileExtensionContentTypeProvider contentTypeProvider = new();" in program
    assert "staticFiles.UseStaticFiles(new StaticFileOptions" in program
    assert (
        "COPY --from=run-services-source Chummer.Run.Api/ chummer.run-services/Chummer.Run.Api/"
        in dockerfile
    )
    assert "COPY --from=build /app/publish ." in dockerfile
