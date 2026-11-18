using System.Text;
using System.Diagnostics.CodeAnalysis;

namespace Chummer.Run.Api.Services.InstallLinking;

/// <summary>
/// Internal, bounded consent for one exact Rook rule-read selection. This is persisted
/// consent state, not a credential or proof that its owner, grant, or selection is current.
/// </summary>
internal sealed record InstallLinkingRookReadConsent(
    string ConsentId,
    long Version,
    string UserId,
    string SubjectId,
    string InstallationId,
    string GrantId,
    string WorkspaceId,
    long RemoteRevision,
    string ServerToken,
    string ContinuationDigest,
    string Purpose,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    DateTimeOffset? RevokedAtUtc)
{
    internal const string RequiredPurpose = "rook-rule-read";
    internal static readonly TimeSpan MaximumLifetime = TimeSpan.FromMinutes(15);
    internal static readonly TimeSpan RetentionAfterExpiryOrRevocation = TimeSpan.FromHours(24);
    private static readonly UTF8Encoding StrictUtf8 = new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);

    internal static bool IsIdentifier(string? value, int maximumBytes)
    {
        if (string.IsNullOrEmpty(value)
            || value.Length > maximumBytes
            || value.Any(static character => char.IsWhiteSpace(character) || char.IsControl(character)))
        {
            return false;
        }

        try
        {
            return StrictUtf8.GetByteCount(value) <= maximumBytes;
        }
        catch (EncoderFallbackException)
        {
            return false;
        }
    }

    internal static bool IsSha256(string? value)
        => value is { Length: 64 }
           && value.All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    internal static bool ShapeIsValid([NotNullWhen(true)] InstallLinkingRookReadConsent? value)
        => value is not null
           && IsSha256(value.ConsentId)
           && (value.RevokedAtUtc is null ? value.Version == 1 : value.Version >= 2)
           && IsIdentifier(value.UserId, 128)
           && IsIdentifier(value.SubjectId, 128)
           && IsIdentifier(value.InstallationId, 64)
           && IsIdentifier(value.GrantId, 128)
           && IsIdentifier(value.WorkspaceId, 128)
           && value.RemoteRevision > 0
           && IsSha256(value.ServerToken)
           && IsSha256(value.ContinuationDigest)
           && string.Equals(value.Purpose, RequiredPurpose, StringComparison.Ordinal)
           && IsTimestamp(value.IssuedAtUtc)
           && IsTimestamp(value.ExpiresAtUtc)
           && value.ExpiresAtUtc > value.IssuedAtUtc
           && value.ExpiresAtUtc - value.IssuedAtUtc <= MaximumLifetime
           && (value.RevokedAtUtc is null
               || (IsTimestamp(value.RevokedAtUtc.Value) && value.RevokedAtUtc >= value.IssuedAtUtc));

    // Compare elapsed time rather than adding to hostile input timestamps. Callers must
    // validate shape and references before using retention to discard any persisted row.
    internal static bool ShouldRetain(InstallLinkingRookReadConsent value, DateTimeOffset now)
    {
        DateTimeOffset lastRelevantTime = value.RevokedAtUtc is { } revokedAtUtc
            && revokedAtUtc > value.ExpiresAtUtc
                ? revokedAtUtc
                : value.ExpiresAtUtc;
        return now - lastRelevantTime <= RetentionAfterExpiryOrRevocation;
    }

    private static bool IsTimestamp(DateTimeOffset value)
        => value != default && value.Offset == TimeSpan.Zero && value.Year is >= 2020 and <= 2200;
}
