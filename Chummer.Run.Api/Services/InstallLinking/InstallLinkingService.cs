using System.Security.Cryptography;
using Chummer.Run.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkingService
{
    private static readonly TimeSpan ClaimTicketLifetime = TimeSpan.FromDays(3);
    private readonly InstallLinkingStore _store;

    public InstallLinkingService(InstallLinkingStore store)
    {
        _store = store;
    }

    public DownloadDispatchResult IssueDownload(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto artifact,
        string? userId,
        string? subjectId)
    {
        var now = DateTimeOffset.UtcNow;
        var normalizedUserId = NormalizeOptional(userId);
        var normalizedSubjectId = NormalizeOptional(subjectId);
        lock (_store.Gate)
        {
            ExpireTicketsLocked(now);

            InstallClaimTicketDto? claimTicket = null;
            if (normalizedUserId is not null || normalizedSubjectId is not null)
            {
                claimTicket = FindReusableTicketLocked(artifact.Id, normalizedUserId, normalizedSubjectId, now)
                    ?? CreateClaimTicketLocked(manifest, artifact, normalizedUserId, normalizedSubjectId, now);
                _store.ClaimTicketsById[claimTicket.TicketId] = claimTicket;
            }

            var receipt = new DownloadReceiptDto(
                ReceiptId: NewId("dlr"),
                ArtifactId: artifact.Id,
                ArtifactLabel: artifact.Platform,
                FileName: artifact.FileName ?? Path.GetFileName(artifact.Url),
                DownloadUrl: artifact.Url,
                Channel: manifest.Channel,
                Version: manifest.Version,
                Head: NormalizeOptional(artifact.Head) ?? "desktop",
                Platform: NormalizeOptional(artifact.PlatformId) ?? NormalizeOptional(artifact.Platform) ?? "unknown",
                Arch: NormalizeOptional(artifact.Arch) ?? "unknown",
                Kind: NormalizeOptional(artifact.Kind) ?? InferKind(artifact),
                InstallAccessClass: NormalizeAccessClass(artifact.InstallAccessClass),
                IssuedAtUtc: now,
                UserId: normalizedUserId,
                SubjectId: normalizedSubjectId,
                ClaimTicketId: claimTicket?.TicketId,
                ClaimCode: claimTicket?.ClaimCode,
                ClaimTicketExpiresAtUtc: claimTicket?.ExpiresAtUtc);

            _store.ReceiptsById[receipt.ReceiptId] = receipt;

            if (claimTicket is not null)
            {
                _store.ClaimTicketsById[claimTicket.TicketId] = claimTicket with { ReceiptId = receipt.ReceiptId };
                claimTicket = _store.ClaimTicketsById[claimTicket.TicketId];
            }

            _store.PersistLocked();
            return new DownloadDispatchResult(receipt, claimTicket);
        }
    }

    public InstallLinkingSummaryDto GetSummary(string? userId, string? subjectId, int maxItems = 8)
    {
        var normalizedUserId = NormalizeOptional(userId);
        var normalizedSubjectId = NormalizeOptional(subjectId);
        lock (_store.Gate)
        {
            ExpireTicketsLocked(DateTimeOffset.UtcNow);
            var receipts = _store.ReceiptsById.Values
                .Where(item => MatchesIdentity(item.UserId, item.SubjectId, normalizedUserId, normalizedSubjectId))
                .OrderByDescending(static item => item.IssuedAtUtc)
                .Take(Math.Max(1, maxItems))
                .ToArray();
            var tickets = _store.ClaimTicketsById.Values
                .Where(item => string.Equals(item.Status, InstallClaimTicketStates.Pending, StringComparison.OrdinalIgnoreCase))
                .Where(item => MatchesIdentity(item.UserId, item.SubjectId, normalizedUserId, normalizedSubjectId))
                .OrderByDescending(static item => item.CreatedAtUtc)
                .Take(Math.Max(1, maxItems))
                .ToArray();
            return new InstallLinkingSummaryDto(receipts, tickets);
        }
    }

    private InstallClaimTicketDto? FindReusableTicketLocked(string artifactId, string? userId, string? subjectId, DateTimeOffset now)
        => _store.ClaimTicketsById.Values
            .Where(item => string.Equals(item.ArtifactId, artifactId, StringComparison.OrdinalIgnoreCase))
            .Where(item => string.Equals(item.Status, InstallClaimTicketStates.Pending, StringComparison.OrdinalIgnoreCase))
            .Where(item => item.ExpiresAtUtc > now)
            .Where(item => MatchesIdentity(item.UserId, item.SubjectId, userId, subjectId))
            .OrderByDescending(static item => item.CreatedAtUtc)
            .FirstOrDefault();

    private InstallClaimTicketDto CreateClaimTicketLocked(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto artifact,
        string? userId,
        string? subjectId,
        DateTimeOffset now)
    {
        var expiresAtUtc = now.Add(ClaimTicketLifetime);
        return new InstallClaimTicketDto(
            TicketId: NewId("ict"),
            ClaimCode: NewClaimCode(),
            ArtifactId: artifact.Id,
            ArtifactLabel: artifact.Platform,
            Channel: manifest.Channel,
            Version: manifest.Version,
            InstallAccessClass: NormalizeAccessClass(artifact.InstallAccessClass),
            Status: InstallClaimTicketStates.Pending,
            CreatedAtUtc: now,
            ExpiresAtUtc: expiresAtUtc,
            UserId: userId,
            SubjectId: subjectId);
    }

    private void ExpireTicketsLocked(DateTimeOffset now)
    {
        var dirty = false;
        foreach (var ticket in _store.ClaimTicketsById.Values.ToArray())
        {
            if (!string.Equals(ticket.Status, InstallClaimTicketStates.Pending, StringComparison.OrdinalIgnoreCase)
                || ticket.ExpiresAtUtc > now)
            {
                continue;
            }

            _store.ClaimTicketsById[ticket.TicketId] = ticket with { Status = InstallClaimTicketStates.Expired };
            dirty = true;
        }

        if (dirty)
        {
            _store.PersistLocked();
        }
    }

    private static bool MatchesIdentity(string? rowUserId, string? rowSubjectId, string? userId, string? subjectId)
        => (!string.IsNullOrWhiteSpace(userId) && string.Equals(rowUserId, userId, StringComparison.OrdinalIgnoreCase))
            || (!string.IsNullOrWhiteSpace(subjectId) && string.Equals(rowSubjectId, subjectId, StringComparison.OrdinalIgnoreCase));

    private static string NormalizeAccessClass(string? value)
    {
        var normalized = NormalizeOptional(value);
        return normalized switch
        {
            InstallAccessClasses.AccountRecommended => InstallAccessClasses.AccountRecommended,
            InstallAccessClasses.AccountRequired => InstallAccessClasses.AccountRequired,
            _ => InstallAccessClasses.OpenPublic
        };
    }

    private static string InferKind(PublicReleaseArtifactDto artifact)
    {
        var fileName = (artifact.FileName ?? artifact.Url).ToLowerInvariant();
        if (fileName.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
            || fileName.EndsWith(".msi", StringComparison.OrdinalIgnoreCase)
            || fileName.EndsWith(".dmg", StringComparison.OrdinalIgnoreCase)
            || fileName.EndsWith(".pkg", StringComparison.OrdinalIgnoreCase))
        {
            return "installer";
        }

        return "archive";
    }

    private static string NewId(string prefix)
        => $"{prefix}-{Guid.NewGuid():N}"[..Math.Min(prefix.Length + 13, prefix.Length + 1 + 12)];

    private static string NewClaimCode()
    {
        var bytes = RandomNumberGenerator.GetBytes(4);
        var hex = Convert.ToHexString(bytes);
        return $"{hex[..4]}-{hex[4..]}";
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}

public sealed record DownloadDispatchResult(
    DownloadReceiptDto Receipt,
    InstallClaimTicketDto? ClaimTicket);
