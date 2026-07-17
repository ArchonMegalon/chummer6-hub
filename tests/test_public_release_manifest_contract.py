from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "Chummer.Run.Contracts" / "PublicLandingContracts.cs"


def test_public_release_manifest_display_labels_require_published_gold_stable_posture() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "public string DisplayVersion => ResolveDisplayVersion(PublicVersion, Version, Channel, RolloutState, Status, SupportabilityState);" in source
    assert "public string DisplayBuildLabel => ResolveDisplayBuildLabel(Version, Channel, RolloutState, Status, SupportabilityState);" in source
    assert "public string DisplayChannelLabel => ResolveDisplayChannelLabel(Channel, RolloutState, Status, SupportabilityState);" in source
    assert "if (!string.IsNullOrWhiteSpace(publicVersion)\n            && IsPublicStable(channel, rolloutState, status, supportabilityState))" in source
    assert '&& string.Equals((supportabilityState ?? string.Empty).Trim(), "gold_supported", StringComparison.OrdinalIgnoreCase)' in source
    assert '&& string.Equals((status ?? string.Empty).Trim(), "published", StringComparison.OrdinalIgnoreCase);' in source
    assert '|| string.Equals(normalizedRolloutState, "promoted_preview", StringComparison.OrdinalIgnoreCase)' in source
    assert '? "Public release"' in source
    assert '? "Current release build"' in source
