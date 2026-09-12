from __future__ import annotations

import importlib.util
import json
import re
import shutil
import stat
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_LINKS = (
    REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / ".well-known" / "assetlinks.json"
)
PROGRAM = REPO_ROOT / "Chummer.Run.Api" / "Program.cs"
PROJECT = REPO_ROOT / "Chummer.Run.Api" / "Chummer.Run.Api.csproj"
DOCKERFILE = REPO_ROOT / "Chummer.Run.Api" / "Dockerfile"
PACKAGE_PLANE_VERIFIER = (
    REPO_ROOT / "scripts" / "ai" / "verify-hub-package-plane.py"
)

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


def load_package_plane_verifier():
    spec = importlib.util.spec_from_file_location(
        "android_app_links_package_plane_verifier", PACKAGE_PLANE_VERIFIER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def test_package_plane_publishes_release_api_and_matches_asset_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = load_package_plane_verifier()
    consumer = tmp_path / "consumer"
    source = consumer / "Chummer.Run.Api" / verifier.ANDROID_APP_LINKS_RELATIVE_PATH
    publish_root = tmp_path / "publish"
    source.parent.mkdir(parents=True)
    source.write_bytes(ASSET_LINKS.read_bytes())
    calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []

    def fake_run(command, *, cwd=None, env=None):
        calls.append((tuple(command), cwd, dict(env)))
        published = publish_root / verifier.ANDROID_APP_LINKS_RELATIVE_PATH
        published.parent.mkdir(parents=True)
        shutil.copyfile(source, published)
        return ""

    monkeypatch.setattr(verifier, "_run", fake_run)
    result = verifier._publish_and_audit_android_app_links(
        consumer,
        publish_root,
        "/locked/dotnet",
        ("-p:RestorePackagesPath=/isolated/packages",),
        {"DOTNET_MULTILEVEL_LOOKUP": "0"},
    )

    assert calls == [
        (
            (
                "/locked/dotnet",
                "publish",
                str(consumer / "Chummer.Run.Api/Chummer.Run.Api.csproj"),
                "--configuration",
                "Release",
                "--no-restore",
                "--nologo",
                "-m:1",
                "-p:RestorePackagesPath=/isolated/packages",
                "--output",
                str(publish_root),
            ),
            consumer,
            {"DOTNET_MULTILEVEL_LOOKUP": "0"},
        )
    ]
    assert result == {
        "relative_path": "wwwroot/.well-known/assetlinks.json",
        "sha256": "d73ff1c9ac3fa55f0f3232b1128b2abee2d2ac4a51c06654221b3be34eca7c32",
        "size_bytes": 347,
    }


def test_package_plane_rejects_changed_published_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = load_package_plane_verifier()
    consumer = tmp_path / "consumer"
    source = consumer / "Chummer.Run.Api" / verifier.ANDROID_APP_LINKS_RELATIVE_PATH
    publish_root = tmp_path / "publish"
    source.parent.mkdir(parents=True)
    source.write_bytes(ASSET_LINKS.read_bytes())

    def fake_run(_command, **_kwargs):
        published = publish_root / verifier.ANDROID_APP_LINKS_RELATIVE_PATH
        published.parent.mkdir(parents=True)
        published.write_bytes(source.read_bytes() + b" ")
        return ""

    monkeypatch.setattr(verifier, "_run", fake_run)
    with pytest.raises(
        verifier.VerificationError,
        match="differs byte-for-byte from tracked source",
    ):
        verifier._publish_and_audit_android_app_links(
            consumer, publish_root, "dotnet", (), {}
        )


def test_package_plane_rejects_symlinked_published_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = load_package_plane_verifier()
    consumer = tmp_path / "consumer"
    source = consumer / "Chummer.Run.Api" / verifier.ANDROID_APP_LINKS_RELATIVE_PATH
    publish_root = tmp_path / "publish"
    source.parent.mkdir(parents=True)
    source.write_bytes(ASSET_LINKS.read_bytes())

    def fake_run(_command, **_kwargs):
        published = publish_root / verifier.ANDROID_APP_LINKS_RELATIVE_PATH
        published.parent.mkdir(parents=True)
        published.symlink_to(source)
        return ""

    monkeypatch.setattr(verifier, "_run", fake_run)
    with pytest.raises(
        verifier.VerificationError,
        match="published Android App Links asset is not a regular file",
    ):
        verifier._publish_and_audit_android_app_links(
            consumer, publish_root, "dotnet", (), {}
        )
