using Chummer.Contracts.BuildGhost;
using Chummer.Run.Api.Services.InstallLinking;

namespace Chummer.Run.Api.Controllers;

// API-local selections, never owner stamps, restored carriers or alternate credentials.
internal interface IRookWorkspaceToolRequest
{
    bool IsValid();
}

internal sealed record RookWorkspaceConsentGrantRequestDto : IRookWorkspaceToolRequest
{
    public required string InstallationId { get; init; }
    public required string GrantId { get; init; }
    public required string WorkspaceId { get; init; }
    public required long RemoteRevision { get; init; }
    public required string ServerToken { get; init; }
    public required string ContinuationDigest { get; init; }
    public required bool ExplicitConfirmation { get; init; }
    public required DateTimeOffset ExpiresAtUtc { get; init; }

    public bool IsValid()
        => InstallLinkingRookReadConsent.IsIdentifier(InstallationId, 64)
           && InstallLinkingRookReadConsent.IsIdentifier(GrantId, 128)
           && InstallLinkingRookReadConsent.IsIdentifier(WorkspaceId, 128)
           && RemoteRevision > 0
           && InstallLinkingRookReadConsent.IsSha256(ServerToken)
           && InstallLinkingRookReadConsent.IsSha256(ContinuationDigest)
           && ExpiresAtUtc.Offset == TimeSpan.Zero && ExpiresAtUtc.Year is >= 2020 and <= 2200;
}

internal sealed record RookWorkspaceConsentRevokeRequestDto : IRookWorkspaceToolRequest
{
    public required string ConsentId { get; init; }
    public required long ExpectedVersion { get; init; }

    public bool IsValid()
        => InstallLinkingRookReadConsent.IsSha256(ConsentId) && ExpectedVersion > 0;
}

internal sealed record RookWorkspaceRuleReadRequestDto : IRookWorkspaceToolRequest
{
    public required string InstallationId { get; init; }
    public required string GrantId { get; init; }
    public required string ConsentId { get; init; }
    public required long ExpectedVersion { get; init; }
    public required string Intent { get; init; }
    public required string SavedSubjectId { get; init; }
    public required string Locale { get; init; }

    public bool IsValid()
        => InstallLinkingRookReadConsent.IsIdentifier(InstallationId, 64)
           && InstallLinkingRookReadConsent.IsIdentifier(GrantId, 128)
           && InstallLinkingRookReadConsent.IsSha256(ConsentId)
           && ExpectedVersion > 0
           // Only shape is bounded here. Core, not this adapter, owns supported intents.
           && InstallLinkingRookReadConsent.IsIdentifier(Intent, 128)
           && InstallLinkingRookReadConsent.IsIdentifier(SavedSubjectId, 128)
           && InstallLinkingRookReadConsent.IsIdentifier(Locale, 32);
}

internal sealed record RookWorkspaceConsentResponseDto(
    string ConsentId, long Version, string WorkspaceId, string Purpose,
    DateTimeOffset IssuedAtUtc, DateTimeOffset ExpiresAtUtc, DateTimeOffset? RevokedAtUtc)
{
    internal static RookWorkspaceConsentResponseDto FromConsent(InstallLinkingRookReadConsent consent)
        => new(consent.ConsentId, consent.Version, consent.WorkspaceId, consent.Purpose,
            consent.IssuedAtUtc, consent.ExpiresAtUtc, consent.RevokedAtUtc);
}

/// <summary>
/// Private owner-facing observation only. This projection is not the raw Core result,
/// a provider packet, a continuing authorization token or a package-approval receipt.
/// Core's original digest covers owner authority fields which are intentionally not
/// exported here; do not relabel that digest as integrity for these different bytes.
/// </summary>
internal sealed record RookWorkspaceRuleReadResponseDto(
    string Status, BuildGhostRuleExplanation Explanation,
    IReadOnlyList<WorkspaceRuleSourceAnchor> SourceAnchors,
    int? Level, int? MaximumLevel, string? FailureReason,
    RookWorkspaceRuleContextDto? RuleContext)
{
    internal static RookWorkspaceRuleReadResponseDto FromResult(WorkspaceRuleQuestionResult result)
        => new(result.Status, result.Explanation, result.SourceAnchors, result.Level,
            result.MaximumLevel, result.FailureReason,
            result.Binding is { } binding ? RookWorkspaceRuleContextDto.FromBinding(binding) : null);
}

// Explicit safe fields retain the calculation's runtime/source/revision context
// without exposing the owner issuer, authority instance or full stored document.
internal sealed record RookWorkspaceRuleContextDto(
    string WorkspaceId, string RulesetId, long ContentRevision, long SavedRevision,
    string WorkspaceDocumentDigest, string SettingsProfileId, string SourceProfileDigest,
    string SourceNodeDigest, string EngineIdentityKind, string EngineFingerprint,
    IReadOnlyList<WorkspaceRuleExecutingModule> ExecutingModules,
    string Intent, string SubjectId, string Locale)
{
    internal static RookWorkspaceRuleContextDto FromBinding(WorkspaceRuleQuestionBinding binding)
        => new(binding.WorkspaceId.Value, binding.RulesetId, binding.ContentRevision,
            binding.SavedRevision, binding.WorkspaceDocumentDigest, binding.SettingsProfileId,
            binding.SourceProfileDigest, binding.SourceNodeDigest, binding.EngineIdentityKind,
            binding.EngineFingerprint, binding.ExecutingModules, binding.Intent,
            binding.SubjectId, binding.Locale);
}
