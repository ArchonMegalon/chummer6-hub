from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_public_canon_loader_caches_paths_and_documents() -> None:
    source = read("Chummer.Run.Api/Services/PublicCanonFileLoader.cs")

    assert "private readonly Dictionary<string, string> _resolvedPathCache" in source
    assert "private readonly Dictionary<string, CachedTextDocument> _textCache" in source
    assert "private readonly Dictionary<string, CachedYamlDocument> _yamlCache" in source
    assert "info.LastWriteTimeUtc" in source
    assert "info.Length" in source


def test_public_trust_and_privacy_documents_are_cached() -> None:
    trust = read("Chummer.Run.Api/Services/PublicTrustContentService.cs")
    privacy = read("Chummer.Run.Api/Services/PublicPrivacyBoundaryService.cs")

    assert "private PublicTrustContentDocument? _cachedDocument;" in trust
    assert "private void ValidateDocument(PublicTrustContentDocument document)" in trust
    assert "_cachedDocument ??= document;" in trust
    assert "private PublicPrivacyBoundariesDocument? _cachedDocument;" in privacy
    assert "_cachedDocument ??= document;" in privacy


def test_public_copy_humanizer_uses_bounded_cache_and_compiled_phrase_rules() -> None:
    source = read("Chummer.Run.Api/Services/PublicFacingCopyHumanizer.cs")

    assert "ConcurrentDictionary<string, string> CleanCache" in source
    assert "MaxCachedInputLength" in source
    assert "MaxCleanCacheEntries" in source
    assert "ReplacementRules" in source
    assert "RegexTimeout" in source
