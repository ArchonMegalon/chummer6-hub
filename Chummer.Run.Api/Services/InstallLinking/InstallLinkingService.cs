using System.Security.Cryptography;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkingService
{
    private static readonly TimeSpan DefaultClaimTicketLifetime = TimeSpan.FromDays(1);
    private static readonly TimeSpan GrantLifetime = TimeSpan.FromDays(30);
    private readonly InstallLinkingStore _store;
    private readonly TimeSpan _claimTicketLifetime;

    public InstallLinkingService(InstallLinkingStore store, IConfiguration configuration)
    {
        _store = store;
        _claimTicketLifetime = ResolveClaimTicketLifetime(configuration);
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
            var now = DateTimeOffset.UtcNow;
            ExpireTicketsLocked(now);
            ExpireGrantsLocked(now);
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
            var installations = _store.InstallationsById.Values
                .Where(item => MatchesIdentity(item.UserId, item.SubjectId, normalizedUserId, normalizedSubjectId))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .Take(Math.Max(1, maxItems))
                .ToArray();
            var grants = _store.GrantsById.Values
                .Where(item => string.Equals(item.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase))
                .Where(item => item.ExpiresAtUtc > now)
                .Where(item => MatchesIdentity(item.UserId, item.SubjectId, normalizedUserId, normalizedSubjectId))
                .OrderByDescending(static item => item.IssuedAtUtc)
                .Take(Math.Max(1, maxItems))
                .ToArray();
            return new InstallLinkingSummaryDto(receipts, tickets, installations, grants);
        }
    }

    public RedeemInstallClaimResponseDto RedeemClaim(RedeemInstallClaimRequestDto request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var normalizedClaimCode = NormalizeClaimCode(request.ClaimCode)
            ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, "claim code is required.");
        var installationId = NormalizeOptional(request.InstallationId)
            ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, "installation id is required.");
        var now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            ExpireTicketsLocked(now);
            ExpireGrantsLocked(now);

            var ticket = FindTicketByClaimCodeLocked(normalizedClaimCode);
            if (ticket is null)
            {
                throw new InstallLinkingOperationException(StatusCodes.Status404NotFound, "claim ticket was not found.");
            }

            if (string.Equals(ticket.Status, InstallClaimTicketStates.Revoked, StringComparison.OrdinalIgnoreCase))
            {
                throw new InstallLinkingOperationException(StatusCodes.Status409Conflict, "claim ticket was revoked.");
            }

            if (string.Equals(ticket.Status, InstallClaimTicketStates.Expired, StringComparison.OrdinalIgnoreCase))
            {
                throw new InstallLinkingOperationException(StatusCodes.Status409Conflict, "claim ticket expired before it could be redeemed.");
            }

            _store.InstallationsById.TryGetValue(installationId, out ClaimedInstallationDto? existingInstallation);
            if (string.Equals(ticket.Status, InstallClaimTicketStates.Redeemed, StringComparison.OrdinalIgnoreCase))
            {
                if (!string.Equals(ticket.InstallationId, installationId, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InstallLinkingOperationException(StatusCodes.Status409Conflict, "claim ticket is already bound to another installation.");
                }

                if (existingInstallation is null)
                {
                    throw new InstallLinkingOperationException(StatusCodes.Status409Conflict, "claim ticket was redeemed but the installation record is missing.");
                }

                ClaimedInstallationDto refreshedInstallation = UpsertInstallationLocked(existingInstallation, ticket, request, now);
                InstallationGrantDto grant = FindReusableGrantLocked(refreshedInstallation.InstallationId, now)
                    ?? CreateGrantLocked(refreshedInstallation, now);
                refreshedInstallation = refreshedInstallation with
                {
                    GrantId = grant.GrantId,
                    UpdatedAtUtc = now
                };
                _store.InstallationsById[refreshedInstallation.InstallationId] = refreshedInstallation;
                _store.GrantsById[grant.GrantId] = grant;
                _store.PersistLocked();
                return new RedeemInstallClaimResponseDto(ticket, refreshedInstallation, grant, AlreadyClaimed: true);
            }

            EnsureInstallationIdentityAvailable(existingInstallation, ticket);

            ClaimedInstallationDto installation = UpsertInstallationLocked(
                existingInstallation,
                ticket with
                {
                    InstallationId = installationId
                },
                request,
                now);
            InstallationGrantDto issuedGrant = CreateGrantLocked(installation, now);
            installation = installation with
            {
                GrantId = issuedGrant.GrantId,
                UpdatedAtUtc = now
            };
            ticket = ticket with
            {
                Status = InstallClaimTicketStates.Redeemed,
                InstallationId = installation.InstallationId
            };

            _store.InstallationsById[installation.InstallationId] = installation;
            _store.ClaimTicketsById[ticket.TicketId] = ticket;
            _store.GrantsById[issuedGrant.GrantId] = issuedGrant;
            _store.PersistLocked();
            return new RedeemInstallClaimResponseDto(ticket, installation, issuedGrant, AlreadyClaimed: false);
        }
    }

    public RefreshInstallationGrantResponseDto RefreshGrant(RefreshInstallationGrantRequestDto request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var installationId = NormalizeOptional(request.InstallationId)
            ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, "installation id is required.");
        var accessToken = NormalizeOptional(request.AccessToken)
            ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, "access token is required.");
        var now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            ExpireTicketsLocked(now);
            ExpireGrantsLocked(now);

            if (!_store.InstallationsById.TryGetValue(installationId, out ClaimedInstallationDto? installation))
            {
                throw new InstallLinkingOperationException(StatusCodes.Status404NotFound, "installation was not found.");
            }

            if (!string.Equals(installation.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase))
            {
                throw new InstallLinkingOperationException(StatusCodes.Status409Conflict, "installation is not active.");
            }

            InstallationGrantDto? currentGrant = _store.GrantsById.Values
                .Where(item => string.Equals(item.InstallationId, installationId, StringComparison.OrdinalIgnoreCase))
                .Where(item => string.Equals(item.AccessToken, accessToken, StringComparison.Ordinal))
                .OrderByDescending(static item => item.IssuedAtUtc)
                .FirstOrDefault();
            if (currentGrant is null)
            {
                throw new InstallLinkingOperationException(StatusCodes.Status401Unauthorized, "installation grant is unknown.");
            }

            if (!string.Equals(currentGrant.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase)
                || currentGrant.ExpiresAtUtc <= now)
            {
                throw new InstallLinkingOperationException(StatusCodes.Status401Unauthorized, "installation grant is no longer active.");
            }

            ClaimedInstallationDto refreshedInstallation = ApplyInstallationRefreshLocked(installation, request, now);
            InstallationGrantDto nextGrant = CreateGrantLocked(refreshedInstallation, now);
            refreshedInstallation = refreshedInstallation with
            {
                GrantId = nextGrant.GrantId,
                UpdatedAtUtc = now
            };

            _store.InstallationsById[refreshedInstallation.InstallationId] = refreshedInstallation;
            _store.GrantsById[currentGrant.GrantId] = currentGrant with
            {
                Status = InstallationGrantStates.Revoked
            };
            _store.GrantsById[nextGrant.GrantId] = nextGrant;
            _store.PersistLocked();
            return new RefreshInstallationGrantResponseDto(refreshedInstallation, nextGrant, Rotated: true);
        }
    }

    public ClaimedInstallationDto? ResolveInstallationForGrant(string? installationId, string? accessToken)
    {
        string? normalizedInstallationId = NormalizeOptional(installationId);
        string? normalizedAccessToken = NormalizeOptional(accessToken);
        if (normalizedInstallationId is null || normalizedAccessToken is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            ExpireGrantsLocked(now);

            if (!_store.InstallationsById.TryGetValue(normalizedInstallationId, out ClaimedInstallationDto? installation))
            {
                return null;
            }

            if (!string.Equals(installation.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase))
            {
                return null;
            }

            InstallationGrantDto? grant = _store.GrantsById.Values
                .Where(item => string.Equals(item.InstallationId, normalizedInstallationId, StringComparison.OrdinalIgnoreCase))
                .Where(item => string.Equals(item.AccessToken, normalizedAccessToken, StringComparison.Ordinal))
                .Where(item => string.Equals(item.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase))
                .Where(item => item.ExpiresAtUtc > now)
                .OrderByDescending(static item => item.IssuedAtUtc)
                .FirstOrDefault();
            return grant is null ? null : installation;
        }
    }

    public bool CanDownloadArtifactWithClaimCode(string? artifactId, string? claimCode)
    {
        return ResolveClaimTicketForDownload(artifactId, claimCode) is not null;
    }

    public InstallClaimTicketDto? ResolveClaimTicketForDownload(string? artifactId, string? claimCode)
    {
        string? normalizedArtifactId = NormalizeOptional(artifactId);
        string? normalizedClaimCode = NormalizeClaimCode(claimCode);
        if (normalizedArtifactId is null || normalizedClaimCode is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            ExpireTicketsLocked(now);

            InstallClaimTicketDto? ticket = FindTicketByClaimCodeLocked(normalizedClaimCode);
            if (ticket is null)
            {
                return null;
            }

            if (!string.Equals(ticket.ArtifactId, normalizedArtifactId, StringComparison.OrdinalIgnoreCase))
            {
                return null;
            }

            if (ticket.ExpiresAtUtc <= now)
            {
                return null;
            }

            return string.Equals(ticket.Status, InstallClaimTicketStates.Revoked, StringComparison.OrdinalIgnoreCase)
                   || string.Equals(ticket.Status, InstallClaimTicketStates.Expired, StringComparison.OrdinalIgnoreCase)
                ? null
                : ticket;
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

    private InstallClaimTicketDto? FindTicketByClaimCodeLocked(string normalizedClaimCode)
        => _store.ClaimTicketsById.Values
            .FirstOrDefault(item => string.Equals(NormalizeClaimCode(item.ClaimCode), normalizedClaimCode, StringComparison.Ordinal));

    private InstallClaimTicketDto CreateClaimTicketLocked(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto artifact,
        string? userId,
        string? subjectId,
        DateTimeOffset now)
    {
        var expiresAtUtc = now.Add(_claimTicketLifetime);
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

    private static void EnsureInstallationIdentityAvailable(ClaimedInstallationDto? existingInstallation, InstallClaimTicketDto ticket)
    {
        if (existingInstallation is null)
        {
            return;
        }

        bool sameUser = string.IsNullOrWhiteSpace(existingInstallation.UserId)
            || string.IsNullOrWhiteSpace(ticket.UserId)
            || string.Equals(existingInstallation.UserId, ticket.UserId, StringComparison.OrdinalIgnoreCase);
        bool sameSubject = string.IsNullOrWhiteSpace(existingInstallation.SubjectId)
            || string.IsNullOrWhiteSpace(ticket.SubjectId)
            || string.Equals(existingInstallation.SubjectId, ticket.SubjectId, StringComparison.OrdinalIgnoreCase);
        if (!sameUser || !sameSubject)
        {
            throw new InstallLinkingOperationException(StatusCodes.Status409Conflict, "installation is already linked to another account.");
        }
    }

    private ClaimedInstallationDto UpsertInstallationLocked(
        ClaimedInstallationDto? existingInstallation,
        InstallClaimTicketDto ticket,
        RedeemInstallClaimRequestDto request,
        DateTimeOffset now)
    {
        string version = NormalizeOptional(request.ApplicationVersion) ?? ticket.Version;
        string channelId = NormalizeOptional(request.ChannelId) ?? ticket.Channel;
        string headId = NormalizeOptional(request.HeadId) ?? existingInstallation?.HeadId ?? "desktop";
        string platform = NormalizeOptional(request.Platform) ?? existingInstallation?.Platform ?? "unknown";
        string arch = NormalizeOptional(request.Arch) ?? existingInstallation?.Arch ?? "unknown";
        string? publicKey = NormalizeOptional(request.PublicKey) ?? existingInstallation?.PublicKey;
        string? hostLabel = NormalizeOptional(request.HostLabel) ?? existingInstallation?.HostLabel;

        return new ClaimedInstallationDto(
            InstallationId: NormalizeOptional(request.InstallationId) ?? existingInstallation?.InstallationId ?? string.Empty,
            ArtifactId: ticket.ArtifactId,
            Channel: channelId,
            Version: version,
            InstallAccessClass: ticket.InstallAccessClass,
            Status: ClaimedInstallationStates.Active,
            CreatedAtUtc: existingInstallation?.CreatedAtUtc ?? now,
            UpdatedAtUtc: now,
            UserId: ticket.UserId,
            SubjectId: ticket.SubjectId,
            PublicKey: publicKey,
            ClaimTicketId: ticket.TicketId,
            HeadId: headId,
            Platform: platform,
            Arch: arch,
            HostLabel: hostLabel,
            GrantId: existingInstallation?.GrantId);
    }

    private ClaimedInstallationDto ApplyInstallationRefreshLocked(
        ClaimedInstallationDto installation,
        RefreshInstallationGrantRequestDto request,
        DateTimeOffset now)
        => installation with
        {
            UpdatedAtUtc = now,
            HeadId = NormalizeOptional(request.HeadId) ?? installation.HeadId,
            Version = NormalizeOptional(request.ApplicationVersion) ?? installation.Version,
            Channel = NormalizeOptional(request.ChannelId) ?? installation.Channel,
            Platform = NormalizeOptional(request.Platform) ?? installation.Platform,
            Arch = NormalizeOptional(request.Arch) ?? installation.Arch,
            PublicKey = NormalizeOptional(request.PublicKey) ?? installation.PublicKey,
            HostLabel = NormalizeOptional(request.HostLabel) ?? installation.HostLabel
        };

    private InstallationGrantDto? FindReusableGrantLocked(string installationId, DateTimeOffset now)
        => _store.GrantsById.Values
            .Where(item => string.Equals(item.InstallationId, installationId, StringComparison.OrdinalIgnoreCase))
            .Where(item => string.Equals(item.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase))
            .Where(item => item.ExpiresAtUtc > now)
            .OrderByDescending(static item => item.IssuedAtUtc)
            .FirstOrDefault();

    private InstallationGrantDto CreateGrantLocked(ClaimedInstallationDto installation, DateTimeOffset now)
    {
        foreach (InstallationGrantDto activeGrant in _store.GrantsById.Values
                     .Where(item => string.Equals(item.InstallationId, installation.InstallationId, StringComparison.OrdinalIgnoreCase))
                     .Where(item => string.Equals(item.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase))
                     .ToArray())
        {
            _store.GrantsById[activeGrant.GrantId] = activeGrant with
            {
                Status = InstallationGrantStates.Revoked
            };
        }

        return new InstallationGrantDto(
            GrantId: NewId("igr"),
            InstallationId: installation.InstallationId,
            Status: InstallationGrantStates.Active,
            AccessToken: NewAccessToken(),
            IssuedAtUtc: now,
            ExpiresAtUtc: now.Add(GrantLifetime),
            UserId: installation.UserId,
            SubjectId: installation.SubjectId);
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

    private void ExpireGrantsLocked(DateTimeOffset now)
    {
        var dirty = false;
        foreach (InstallationGrantDto grant in _store.GrantsById.Values.ToArray())
        {
            if (!string.Equals(grant.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase)
                || grant.ExpiresAtUtc > now)
            {
                continue;
            }

            _store.GrantsById[grant.GrantId] = grant with
            {
                Status = InstallationGrantStates.Expired
            };
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

    private static TimeSpan ResolveClaimTicketLifetime(IConfiguration configuration)
    {
        string? configuredHours = configuration["CHUMMER_INSTALL_CLAIM_TICKET_LIFETIME_HOURS"];
        if (int.TryParse(configuredHours, out int hours))
        {
            hours = Math.Clamp(hours, 1, 7 * 24);
            return TimeSpan.FromHours(hours);
        }

        string? configuredMinutes = configuration["CHUMMER_INSTALL_CLAIM_TICKET_LIFETIME_MINUTES"];
        if (int.TryParse(configuredMinutes, out int minutes))
        {
            minutes = Math.Clamp(minutes, 30, 7 * 24 * 60);
            return TimeSpan.FromMinutes(minutes);
        }

        return DefaultClaimTicketLifetime;
    }

    private static string NewId(string prefix)
        => $"{prefix}-{Guid.NewGuid():N}"[..Math.Min(prefix.Length + 13, prefix.Length + 1 + 12)];

    private static string NewClaimCode()
    {
        var bytes = RandomNumberGenerator.GetBytes(10);
        var hex = Convert.ToHexString(bytes);
        return $"{hex[..5]}-{hex[5..10]}-{hex[10..15]}-{hex[15..20]}";
    }

    private static string NewAccessToken()
    {
        var bytes = RandomNumberGenerator.GetBytes(24);
        return Convert.ToBase64String(bytes)
            .TrimEnd('=')
            .Replace("+", "-", StringComparison.Ordinal)
            .Replace("/", "_", StringComparison.Ordinal);
    }

    private static string? NormalizeClaimCode(string? value)
    {
        var normalized = NormalizeOptional(value);
        if (normalized is null)
        {
            return null;
        }

        return string.Concat(normalized.Where(char.IsLetterOrDigit)).ToUpperInvariant();
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}

public sealed record DownloadDispatchResult(
    DownloadReceiptDto Receipt,
    InstallClaimTicketDto? ClaimTicket);

public sealed class InstallLinkingOperationException : Exception
{
    public InstallLinkingOperationException(int statusCode, string message)
        : base(message)
    {
        StatusCode = statusCode;
    }

    public int StatusCode { get; }
}
