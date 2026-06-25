from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "Chummer.Run.Api" / "Services" / "Community" / "OriginDossierPublicationService.cs"


def test_origin_publication_service_uses_exact_chummer_host_guard() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "private static bool IsTrustedChummerHost(Uri uri)" in source
    assert 'string.Equals(host, "chummer.run", StringComparison.OrdinalIgnoreCase)' in source
    assert 'host.EndsWith(".chummer.run", StringComparison.OrdinalIgnoreCase)' in source
    assert 'uri.Host.Contains("chummer.run", StringComparison.OrdinalIgnoreCase)' not in source


def test_origin_publication_service_limits_http_to_loopback() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "string.Equals(uri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)" in source
    assert "&& uri.IsLoopback" in source


def test_origin_publication_service_requires_audiobookshelf_share_prefix() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert 'uri.AbsolutePath.StartsWith("/share/", StringComparison.OrdinalIgnoreCase)' in source
    assert 'uri.AbsolutePath.StartsWith("/audiobookshelf/share/", StringComparison.OrdinalIgnoreCase)' in source
    assert 'uri.AbsolutePath.Contains("/share/", StringComparison.OrdinalIgnoreCase)' not in source


def test_origin_publication_service_provider_tokens_are_configurable() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "CHUMMER_ORIGIN_MANUSCRIPT_PROVIDER_TOKENS" in source
    assert "OriginDossier:ManuscriptProviderTokens" in source
    assert "CHUMMER_ORIGIN_AUDIO_PROVIDER_TOKENS" in source
    assert "OriginDossier:AudioProviderTokens" in source
    assert "ResolveApprovedProviderTokens" in source
    assert "ContainsTokenWithBoundary" in source
    assert "ReceiptProviderMatchesAnyToken" in source
    assert "provider.Contains(token, StringComparison.OrdinalIgnoreCase)" not in source


def test_origin_publication_service_requires_canonical_watch_telegram_link() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert 'BuildOwnerPath(entry, "watch")' in source
    assert 'BuildOwnerPath(entry, "video")' not in source
    assert "Sha256Text(BuildOwnerPath(entry, null))" in source
    assert 'Sha256Text(BuildOwnerPath(entry, "read"))' in source
    assert 'Sha256Text(BuildOwnerPath(entry, "listen"))' in source
    assert 'Sha256Text(BuildOwnerPath(entry, "watch"))' in source
    assert "Sha256Text(BuildOriginEditionNamespace(entry))" in source


def test_origin_publication_service_requires_specialized_movie_poster_artifact() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "MoviePosterPath" in source
    assert "HasArchivedArtifact(entry.MoviePosterPath)" in source
    assert '"movie poster artifact path"' in source
    assert 'ReceiptSurfacePassed(root, "movie_poster")' in source
