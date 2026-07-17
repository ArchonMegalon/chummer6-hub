using System.Security.Cryptography;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkingService
{
    public const int MaxRequestBodyBytes = 16 * 1024;
    private const int MaxInstallationIdLength = 64;
    private const int MaxAccessTokenLength = 256;
    private const int MaxClaimCodeLength = 128;
    private const int MaxCallbackCodeLength = 256;
    private const int MaxVersionLength = 64;
    private const int MaxChannelIdLength = 64;
    private const int MaxHeadIdLength = 128;
    private const int MaxPlatformLength = 64;
    private const int MaxArchLength = 32;
    private const int MaxPublicKeyLength = 256;
    private const int MaxHostLabelLength = 256;
    private const int MaxPendingClaimTicketsPerPrincipal = 16;
    private const int MaxDownloadReceiptsPerPrincipalPerHour = 128;
    private const int MaxPendingBrowserCallbacksPerPrincipal = 8;
    private static readonly TimeSpan DefaultClaimTicketLifetime = TimeSpan.FromDays(1);
    private static readonly TimeSpan DefaultBrowserCallbackLifetime = TimeSpan.FromMinutes(15);
    private static readonly TimeSpan GrantLifetime = TimeSpan.FromDays(30);
    private readonly Func<InstallLinkingStore> _storeAccessor;
    private InstallLinkingStore _store => _storeAccessor();
    private readonly TimeSpan _claimTicketLifetime;
    private readonly TimeSpan _browserCallbackLifetime;
    private readonly int _maxPendingClaimTicketsPerPrincipal;
    private readonly int _maxDownloadReceiptsPerPrincipalPerHour;
    private readonly int _maxPendingBrowserCallbacksPerPrincipal;
    private readonly IInstallLinkingStoreReadinessProbe? _readinessProbe;

    public InstallLinkingService(
        InstallLinkingStore store,
        IConfiguration configuration,
        IInstallLinkingStoreReadinessProbe? readinessProbe = null)
        : this(
            () => store ?? throw new ArgumentNullException(nameof(store)),
            configuration,
            readinessProbe)
    {
    }

    public InstallLinkingService(
        InstallLinkingStoreAccess storeAccess,
        IConfiguration configuration,
        IInstallLinkingStoreReadinessProbe readinessProbe)
        : this(
            (storeAccess ?? throw new ArgumentNullException(nameof(storeAccess))).GetRequired,
            configuration,
            readinessProbe)
    {
    }

    private InstallLinkingService(
        Func<InstallLinkingStore> storeAccessor,
        IConfiguration configuration,
        IInstallLinkingStoreReadinessProbe? readinessProbe)
    {
        _storeAccessor = storeAccessor;
        ArgumentNullException.ThrowIfNull(configuration);
        _readinessProbe = readinessProbe;
        _claimTicketLifetime = ResolveClaimTicketLifetime(configuration);
        _browserCallbackLifetime = ResolveBrowserCallbackLifetime(configuration);
        _maxPendingClaimTicketsPerPrincipal = ResolveBoundedLimit(
            configuration["CHUMMER_INSTALL_LINKING_MAX_PENDING_CLAIM_TICKETS_PER_PRINCIPAL"],
            MaxPendingClaimTicketsPerPrincipal,
            64);
        _maxDownloadReceiptsPerPrincipalPerHour = ResolveBoundedLimit(
            configuration["CHUMMER_INSTALL_LINKING_MAX_DOWNLOAD_RECEIPTS_PER_PRINCIPAL_PER_HOUR"],
            MaxDownloadReceiptsPerPrincipalPerHour,
            512);
        _maxPendingBrowserCallbacksPerPrincipal = ResolveBoundedLimit(
            configuration["CHUMMER_INSTALL_LINKING_MAX_PENDING_BROWSER_CALLBACKS_PER_PRINCIPAL"],
            MaxPendingBrowserCallbacksPerPrincipal,
            32);
    }

    public DownloadDispatchResult IssueDownload(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto artifact,
        string? userId,
        string? subjectId,
        bool forceNewClaim = false)
    {
        var now = DateTimeOffset.UtcNow;
        var normalizedUserId = NormalizeOptional(userId);
        var normalizedSubjectId = NormalizeOptional(subjectId);
        string? generationId = NormalizeOptional(manifest.GenerationId);
        string? artifactSha256 = generationId is null
            ? null
            : NormalizeRequiredArtifactSha256(artifact.Sha256);
        string installAccessClass = NormalizeAccessClass(artifact.InstallAccessClass);
        if (normalizedUserId is null && normalizedSubjectId is null)
        {
            if (string.Equals(
                    installAccessClass,
                    InstallAccessClasses.AccountRequired,
                    StringComparison.Ordinal))
            {
                throw new InstallLinkingOperationException(
                    StatusCodes.Status401Unauthorized,
                    "Account sign-in is required for this download.");
            }

            // Anonymous guest-readable delivery (open-public or account-recommended) is already
            // covered by endpoint/global limiting and has no claim secret to recover. Return an
            // ephemeral correlation receipt instead of turning unauthenticated traffic into
            // synchronous protect + full-snapshot fsync work.
            return new DownloadDispatchResult(
                CreateDownloadReceipt(
                    manifest,
                    artifact,
                    normalizedUserId,
                    normalizedSubjectId,
                    claimTicket: null,
                    installAccessClass: installAccessClass,
                    now: now),
                ClaimTicket: null);
        }

        EnsureDurableStoreReady();
        lock (_store.Gate)
        {
            ExpireTicketsLocked(now);
            EnforceRecentReceiptLimitLocked(normalizedUserId, normalizedSubjectId, now);

            InstallClaimTicketDto? claimTicket = null;
            if (normalizedUserId is not null || normalizedSubjectId is not null)
            {
                claimTicket = forceNewClaim ? null : FindReusableTicketLocked(
                            artifact.Id,
                            generationId,
                            artifactSha256,
                            normalizedUserId,
                            normalizedSubjectId,
                            now);
                if (claimTicket is null)
                {
                    EnforcePendingTicketLimitLocked(normalizedUserId, normalizedSubjectId, now);
                    claimTicket = CreateClaimTicketLocked(manifest, artifact, normalizedUserId, normalizedSubjectId, now);
                }
                _store.ClaimTicketsById[claimTicket.TicketId] = claimTicket;
            }

            DownloadReceiptDto receipt = CreateDownloadReceipt(
                manifest,
                artifact,
                normalizedUserId,
                normalizedSubjectId,
                claimTicket,
                installAccessClass,
                now);

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
        if (!IsDurableStoreReady())
        {
            return new InstallLinkingSummaryDto([], [], [], [], []);
        }

        var normalizedUserId = NormalizeOptional(userId);
        var normalizedSubjectId = NormalizeOptional(subjectId);
        lock (_store.Gate)
        {
            var now = DateTimeOffset.UtcNow;
            ExpireTicketsLocked(now);
            ExpireBrowserCallbacksLocked(now);
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
            var callbacks = _store.BrowserCallbacksById.Values
                .Where(item => string.Equals(item.Status, InstallBrowserCallbackStates.Pending, StringComparison.OrdinalIgnoreCase))
                .Where(item => item.ExpiresAtUtc > now)
                .Where(item => MatchesIdentity(item.UserId, item.SubjectId, normalizedUserId, normalizedSubjectId))
                .OrderByDescending(static item => item.CreatedAtUtc)
                .Take(Math.Max(1, maxItems))
                .ToArray();
            return new InstallLinkingSummaryDto(receipts, tickets, installations, grants, callbacks);
        }
    }

    public RedeemInstallClaimResponseDto RedeemClaim(RedeemInstallClaimRequestDto request)
    {
        EnsureDurableStoreReady();
        ArgumentNullException.ThrowIfNull(request);

        var normalizedClaimCode = NormalizeClaimCode(request.ClaimCode)
            ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, "claim code is required.");
        var installationId = NormalizeRequired(request.InstallationId, nameof(request.InstallationId), MaxInstallationIdLength);
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
        EnsureDurableStoreReady();
        ArgumentNullException.ThrowIfNull(request);

        var installationId = NormalizeRequired(request.InstallationId, nameof(request.InstallationId), MaxInstallationIdLength);
        var accessToken = NormalizeRequired(request.AccessToken, nameof(request.AccessToken), MaxAccessTokenLength);
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

    public RevokeInstallationGrantResponseDto RevokeGrant(RevokeInstallationGrantRequestDto request)
    {
        EnsureDurableStoreReady();
        ArgumentNullException.ThrowIfNull(request);

        var installationId = NormalizeRequired(request.InstallationId, nameof(request.InstallationId), MaxInstallationIdLength);
        var accessToken = NormalizeRequired(request.AccessToken, nameof(request.AccessToken), MaxAccessTokenLength);
        var now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            ExpireGrantsLocked(now);

            if (!_store.InstallationsById.TryGetValue(installationId, out ClaimedInstallationDto? installation))
            {
                throw new InstallLinkingOperationException(StatusCodes.Status404NotFound, "installation was not found.");
            }

            InstallationGrantDto? presentedGrant = _store.GrantsById.Values
                .Where(item => string.Equals(item.InstallationId, installationId, StringComparison.OrdinalIgnoreCase))
                .Where(item => string.Equals(item.AccessToken, accessToken, StringComparison.Ordinal))
                .OrderByDescending(static item => item.IssuedAtUtc)
                .FirstOrDefault();
            if (presentedGrant is null)
            {
                throw new InstallLinkingOperationException(StatusCodes.Status401Unauthorized, "installation grant is unknown.");
            }

            if (!string.Equals(presentedGrant.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase)
                || presentedGrant.ExpiresAtUtc <= now)
            {
                throw new InstallLinkingOperationException(StatusCodes.Status401Unauthorized, "installation grant is no longer active.");
            }

            ClaimedInstallationDto revokedInstallation = installation with
            {
                Status = ClaimedInstallationStates.Revoked,
                GrantId = null,
                UpdatedAtUtc = now
            };
            _store.InstallationsById[revokedInstallation.InstallationId] = revokedInstallation;

            InstallationGrantDto[] revokedGrants = _store.GrantsById.Values
                .Where(item => string.Equals(item.InstallationId, installationId, StringComparison.OrdinalIgnoreCase))
                .Where(item => string.Equals(item.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase))
                .Select(item => item with { Status = InstallationGrantStates.Revoked })
                .ToArray();

            foreach (InstallationGrantDto revokedGrant in revokedGrants)
            {
                _store.GrantsById[revokedGrant.GrantId] = revokedGrant;
            }

            RevokeBrowserCallbacksForInstallationLocked(installationId);
            _store.PersistLocked();
            return new RevokeInstallationGrantResponseDto(revokedInstallation, revokedGrants);
        }
    }

    public IssueInstallBrowserCallbackResponseDto IssueBrowserCallback(
        IssueInstallBrowserCallbackRequestDto request,
        string? userId,
        string? subjectId)
    {
        EnsureDurableStoreReady();
        ArgumentNullException.ThrowIfNull(request);

        string? normalizedInstallationId = NormalizeOptional(request.InstallationId)
            ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, "installation id is required.");
        string? normalizedArtifactId = NormalizeOptional(request.ArtifactId)
            ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, "artifact id is required.");
        string? normalizedCallbackUri = NormalizeOptional(request.CallbackUri)
            ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, "callback uri is required.");
        string? normalizedUserId = NormalizeOptional(userId);
        string? normalizedSubjectId = NormalizeOptional(subjectId);
        DateTimeOffset now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            ExpireBrowserCallbacksLocked(now);
            ExpireGrantsLocked(now);

            _store.InstallationsById.TryGetValue(normalizedInstallationId, out ClaimedInstallationDto? existingInstallation);
            EnsureInstallationIdentityAvailable(existingInstallation, normalizedUserId, normalizedSubjectId);

            InstallBrowserCallbackDto? callback = FindReusableBrowserCallbackLocked(
                    normalizedInstallationId,
                    normalizedUserId,
                    normalizedSubjectId,
                    normalizedCallbackUri,
                    now);
            if (callback is null)
            {
                EnforcePendingCallbackLimitLocked(normalizedUserId, normalizedSubjectId, now);
                callback = CreateBrowserCallbackLocked(request with
                {
                    InstallationId = normalizedInstallationId,
                    ArtifactId = normalizedArtifactId,
                    CallbackUri = normalizedCallbackUri
                }, normalizedUserId, normalizedSubjectId, now);
            }

            _store.BrowserCallbacksById[callback.CallbackId] = callback;
            _store.PersistLocked();
            return new IssueInstallBrowserCallbackResponseDto(
                Callback: callback,
                AlreadyClaimed: existingInstallation is not null
                    && string.Equals(existingInstallation.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase),
                Installation: existingInstallation);
        }
    }

    public ExchangeInstallBrowserCallbackResponseDto ExchangeBrowserCallback(ExchangeInstallBrowserCallbackRequestDto request)
    {
        EnsureDurableStoreReady();
        ArgumentNullException.ThrowIfNull(request);

        string? normalizedCallbackCode = NormalizeBrowserCallbackCode(request.CallbackCode)
            ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, "callback code is required.");
        string normalizedInstallationId = NormalizeRequired(request.InstallationId, nameof(request.InstallationId), MaxInstallationIdLength);
        DateTimeOffset now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            ExpireBrowserCallbacksLocked(now);
            ExpireGrantsLocked(now);

            InstallBrowserCallbackDto? callback = FindBrowserCallbackByCodeLocked(normalizedCallbackCode);
            if (callback is null)
            {
                throw new InstallLinkingOperationException(StatusCodes.Status404NotFound, "browser callback was not found.");
            }

            if (string.Equals(callback.Status, InstallBrowserCallbackStates.Revoked, StringComparison.OrdinalIgnoreCase))
            {
                throw new InstallLinkingOperationException(StatusCodes.Status409Conflict, "browser callback was revoked.");
            }

            if (string.Equals(callback.Status, InstallBrowserCallbackStates.Expired, StringComparison.OrdinalIgnoreCase))
            {
                throw new InstallLinkingOperationException(StatusCodes.Status409Conflict, "browser callback expired before it could be completed.");
            }

            if (!string.Equals(callback.InstallationId, normalizedInstallationId, StringComparison.OrdinalIgnoreCase))
            {
                throw new InstallLinkingOperationException(StatusCodes.Status409Conflict, "browser callback is already bound to another installation.");
            }

            _store.InstallationsById.TryGetValue(normalizedInstallationId, out ClaimedInstallationDto? existingInstallation);
            EnsureInstallationIdentityAvailable(existingInstallation, callback.UserId, callback.SubjectId);

            if (string.Equals(callback.Status, InstallBrowserCallbackStates.Redeemed, StringComparison.OrdinalIgnoreCase))
            {
                if (existingInstallation is null
                    || !string.Equals(
                        existingInstallation.Status,
                        ClaimedInstallationStates.Active,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new InstallLinkingOperationException(
                        StatusCodes.Status409Conflict,
                        "browser callback no longer resolves to an active installation.");
                }

                string? originalGrantId = NormalizeOptional(callback.GrantId);
                if (originalGrantId is null
                    || !string.Equals(
                        existingInstallation.GrantId,
                        originalGrantId,
                        StringComparison.OrdinalIgnoreCase)
                    || !_store.GrantsById.TryGetValue(originalGrantId, out InstallationGrantDto? originalGrant)
                    || !string.Equals(
                        originalGrant.InstallationId,
                        existingInstallation.InstallationId,
                        StringComparison.OrdinalIgnoreCase)
                    || !string.Equals(
                        originalGrant.Status,
                        InstallationGrantStates.Active,
                        StringComparison.OrdinalIgnoreCase)
                    || originalGrant.ExpiresAtUtc <= now)
                {
                    throw new InstallLinkingOperationException(
                        StatusCodes.Status409Conflict,
                        "browser callback no longer resolves to its original active grant.");
                }

                return new ExchangeInstallBrowserCallbackResponseDto(
                    callback,
                    existingInstallation,
                    originalGrant,
                    AlreadyClaimed: true);
            }

            ClaimedInstallationDto installation = UpsertInstallationLocked(existingInstallation, callback, request, now);
            InstallationGrantDto issuedGrant = CreateGrantLocked(installation, now);
            installation = installation with
            {
                GrantId = issuedGrant.GrantId,
                UpdatedAtUtc = now
            };
            callback = callback with
            {
                Status = InstallBrowserCallbackStates.Redeemed,
                GrantId = issuedGrant.GrantId
            };

            _store.InstallationsById[installation.InstallationId] = installation;
            _store.BrowserCallbacksById[callback.CallbackId] = callback;
            _store.GrantsById[issuedGrant.GrantId] = issuedGrant;
            _store.PersistLocked();
            return new ExchangeInstallBrowserCallbackResponseDto(callback, installation, issuedGrant, AlreadyClaimed: false);
        }
    }

    public ClaimedInstallationDto? ResolveInstallationForGrant(string? installationId, string? accessToken)
    {
        if (!IsDurableStoreReady())
        {
            return null;
        }

        string? normalizedInstallationId;
        string? normalizedAccessToken;
        try
        {
            normalizedInstallationId = NormalizeOptional(installationId, nameof(installationId), MaxInstallationIdLength);
            normalizedAccessToken = NormalizeOptional(accessToken, nameof(accessToken), MaxAccessTokenLength);
        }
        catch (InstallLinkingOperationException)
        {
            return null;
        }

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

    public bool CanDownloadArtifactWithClaimCode(
        string? artifactId,
        string? generationId,
        string? artifactSha256,
        bool allowLegacyUnbound,
        string? claimCode)
    {
        return ResolveClaimTicketForDownload(
            artifactId,
            generationId,
            artifactSha256,
            allowLegacyUnbound,
            claimCode) is not null;
    }

    public InstallClaimTicketDto? ResolveClaimTicketForDownload(
        string? artifactId,
        string? generationId,
        string? artifactSha256,
        bool allowLegacyUnbound,
        string? claimCode)
    {
        if (!IsDurableStoreReady())
        {
            return null;
        }

        string? normalizedArtifactId = NormalizeOptional(artifactId);
        string? normalizedGenerationId = NormalizeOptional(generationId);
        string? normalizedArtifactSha256 = NormalizeArtifactSha256OrNull(artifactSha256);
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

            string? ticketGenerationId = NormalizeOptional(ticket.GenerationId);
            string? ticketArtifactSha256 = NormalizeArtifactSha256OrNull(ticket.ArtifactSha256);
            if ((ticketGenerationId is null) != (ticketArtifactSha256 is null))
            {
                return null;
            }

            if (ticketGenerationId is null)
            {
                if (!allowLegacyUnbound || normalizedGenerationId is not null)
                {
                    return null;
                }
            }
            else if (normalizedGenerationId is null
                     || normalizedArtifactSha256 is null
                     || !string.Equals(ticketGenerationId, normalizedGenerationId, StringComparison.Ordinal)
                     || !FixedTimeEquals(ticketArtifactSha256!, normalizedArtifactSha256))
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

    private InstallClaimTicketDto? FindReusableTicketLocked(
        string artifactId,
        string? generationId,
        string? artifactSha256,
        string? userId,
        string? subjectId,
        DateTimeOffset now)
        => _store.ClaimTicketsById.Values
            .Where(item => string.Equals(item.ArtifactId, artifactId, StringComparison.OrdinalIgnoreCase))
            .Where(item => ReleaseBindingMatches(item, generationId, artifactSha256))
            .Where(item => string.Equals(item.Status, InstallClaimTicketStates.Pending, StringComparison.OrdinalIgnoreCase))
            .Where(item => item.ExpiresAtUtc > now)
            .Where(item => MatchesIdentity(item.UserId, item.SubjectId, userId, subjectId))
            .OrderByDescending(static item => item.CreatedAtUtc)
            .FirstOrDefault();

    private InstallBrowserCallbackDto? FindReusableBrowserCallbackLocked(
        string installationId,
        string? userId,
        string? subjectId,
        string callbackUri,
        DateTimeOffset now)
        => _store.BrowserCallbacksById.Values
            .Where(item => string.Equals(item.InstallationId, installationId, StringComparison.OrdinalIgnoreCase))
            .Where(item => string.Equals(item.Status, InstallBrowserCallbackStates.Pending, StringComparison.OrdinalIgnoreCase))
            .Where(item => item.ExpiresAtUtc > now)
            .Where(item => MatchesIdentity(item.UserId, item.SubjectId, userId, subjectId))
            .Where(item => string.Equals(item.CallbackUri, callbackUri, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.CreatedAtUtc)
            .FirstOrDefault();

    private InstallClaimTicketDto? FindTicketByClaimCodeLocked(string normalizedClaimCode)
        => _store.ClaimTicketsById.Values
            .FirstOrDefault(item => string.Equals(NormalizeClaimCode(item.ClaimCode), normalizedClaimCode, StringComparison.Ordinal));

    private InstallBrowserCallbackDto? FindBrowserCallbackByCodeLocked(string normalizedCallbackCode)
        => _store.BrowserCallbacksById.Values
            .FirstOrDefault(item => string.Equals(NormalizeBrowserCallbackCode(item.CallbackCode), normalizedCallbackCode, StringComparison.Ordinal));

    private InstallClaimTicketDto CreateClaimTicketLocked(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto artifact,
        string? userId,
        string? subjectId,
        DateTimeOffset now)
    {
        var expiresAtUtc = now.Add(_claimTicketLifetime);
        string? generationId = NormalizeOptional(manifest.GenerationId);
        string? artifactSha256 = generationId is null
            ? null
            : NormalizeRequiredArtifactSha256(artifact.Sha256);
        return new InstallClaimTicketDto(
            TicketId: NewId("ict"),
            ClaimCode: NewClaimCode(),
            ArtifactId: artifact.Id,
            ArtifactLabel: artifact.PlatformLabel ?? artifact.Platform,
            Channel: manifest.Channel,
            Version: manifest.Version,
            InstallAccessClass: NormalizeAccessClass(artifact.InstallAccessClass),
            Status: InstallClaimTicketStates.Pending,
            CreatedAtUtc: now,
            ExpiresAtUtc: expiresAtUtc,
            UserId: userId,
            SubjectId: subjectId,
            GenerationId: generationId,
            ArtifactSha256: artifactSha256);
    }

    private static DownloadReceiptDto CreateDownloadReceipt(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto artifact,
        string? userId,
        string? subjectId,
        InstallClaimTicketDto? claimTicket,
        string installAccessClass,
        DateTimeOffset now)
        => new(
            ReceiptId: NewId("dlr"),
            ArtifactId: artifact.Id,
            ArtifactLabel: artifact.PlatformLabel ?? artifact.Platform,
            FileName: artifact.FileName ?? Path.GetFileName(artifact.Url),
            DownloadUrl: artifact.Url,
            Channel: manifest.Channel,
            Version: manifest.Version,
            Head: NormalizeOptional(artifact.Head) ?? "desktop",
            Platform: NormalizeOptional(artifact.PlatformId) ?? NormalizeOptional(artifact.Platform) ?? "unknown",
            Arch: NormalizeOptional(artifact.Arch) ?? "unknown",
            Kind: NormalizeOptional(artifact.Kind) ?? InferKind(artifact),
            InstallAccessClass: installAccessClass,
            IssuedAtUtc: now,
            UserId: userId,
            SubjectId: subjectId,
            ClaimTicketId: claimTicket?.TicketId,
            ClaimCode: claimTicket?.ClaimCode,
            ClaimTicketExpiresAtUtc: claimTicket?.ExpiresAtUtc);

    private static bool ReleaseBindingMatches(
        InstallClaimTicketDto ticket,
        string? generationId,
        string? artifactSha256)
    {
        string? ticketGenerationId = NormalizeOptional(ticket.GenerationId);
        string? ticketArtifactSha256 = NormalizeArtifactSha256OrNull(ticket.ArtifactSha256);
        string? normalizedGenerationId = NormalizeOptional(generationId);
        string? normalizedArtifactSha256 = NormalizeArtifactSha256OrNull(artifactSha256);
        if ((ticketGenerationId is null) != (ticketArtifactSha256 is null))
        {
            return false;
        }

        if (ticketGenerationId is null)
        {
            return normalizedGenerationId is null;
        }

        return normalizedGenerationId is not null
            && normalizedArtifactSha256 is not null
            && string.Equals(ticketGenerationId, normalizedGenerationId, StringComparison.Ordinal)
            && FixedTimeEquals(ticketArtifactSha256!, normalizedArtifactSha256);
    }

    private InstallBrowserCallbackDto CreateBrowserCallbackLocked(
        IssueInstallBrowserCallbackRequestDto request,
        string? userId,
        string? subjectId,
        DateTimeOffset now)
    {
        var expiresAtUtc = now.Add(_browserCallbackLifetime);
        return new InstallBrowserCallbackDto(
            CallbackId: NewId("ibc"),
            CallbackCode: NewCallbackCode(),
            InstallationId: NormalizeOptional(request.InstallationId) ?? string.Empty,
            ArtifactId: NormalizeOptional(request.ArtifactId) ?? string.Empty,
            Channel: NormalizeOptional(request.ChannelId) ?? "preview",
            Version: NormalizeOptional(request.ApplicationVersion) ?? "unknown",
            InstallAccessClass: NormalizeAccessClass(request.InstallAccessClass),
            Status: InstallBrowserCallbackStates.Pending,
            CreatedAtUtc: now,
            ExpiresAtUtc: expiresAtUtc,
            UserId: userId,
            SubjectId: subjectId,
            PublicKey: NormalizeOptional(request.PublicKey),
            HeadId: NormalizeOptional(request.HeadId),
            Platform: NormalizeOptional(request.Platform),
            Arch: NormalizeOptional(request.Arch),
            HostLabel: NormalizeOptional(request.HostLabel),
            CallbackUri: NormalizeOptional(request.CallbackUri));
    }

    private static void EnsureInstallationIdentityAvailable(ClaimedInstallationDto? existingInstallation, InstallClaimTicketDto ticket)
    {
        EnsureInstallationIdentityAvailable(existingInstallation, ticket.UserId, ticket.SubjectId);
    }

    private static void EnsureInstallationIdentityAvailable(ClaimedInstallationDto? existingInstallation, string? userId, string? subjectId)
    {
        if (existingInstallation is null)
        {
            return;
        }

        bool sameUser = string.IsNullOrWhiteSpace(existingInstallation.UserId)
            || string.IsNullOrWhiteSpace(userId)
            || string.Equals(existingInstallation.UserId, userId, StringComparison.OrdinalIgnoreCase);
        bool sameSubject = string.IsNullOrWhiteSpace(existingInstallation.SubjectId)
            || string.IsNullOrWhiteSpace(subjectId)
            || string.Equals(existingInstallation.SubjectId, subjectId, StringComparison.OrdinalIgnoreCase);
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
        string version = NormalizeOptional(request.ApplicationVersion, nameof(request.ApplicationVersion), MaxVersionLength) ?? ticket.Version;
        string channelId = NormalizeOptional(request.ChannelId, nameof(request.ChannelId), MaxChannelIdLength) ?? ticket.Channel;
        string headId = NormalizeOptional(request.HeadId, nameof(request.HeadId), MaxHeadIdLength) ?? existingInstallation?.HeadId ?? "desktop";
        string platform = NormalizeOptional(request.Platform, nameof(request.Platform), MaxPlatformLength) ?? existingInstallation?.Platform ?? "unknown";
        string arch = NormalizeOptional(request.Arch, nameof(request.Arch), MaxArchLength) ?? existingInstallation?.Arch ?? "unknown";
        string? publicKey = NormalizeOptional(request.PublicKey, nameof(request.PublicKey), MaxPublicKeyLength) ?? existingInstallation?.PublicKey;
        string? hostLabel = NormalizeOptional(request.HostLabel, nameof(request.HostLabel), MaxHostLabelLength) ?? existingInstallation?.HostLabel;

        return new ClaimedInstallationDto(
            InstallationId: NormalizeRequired(request.InstallationId, nameof(request.InstallationId), MaxInstallationIdLength),
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

    private ClaimedInstallationDto UpsertInstallationLocked(
        ClaimedInstallationDto? existingInstallation,
        InstallBrowserCallbackDto callback,
        ExchangeInstallBrowserCallbackRequestDto request,
        DateTimeOffset now)
    {
        string version = NormalizeOptional(request.ApplicationVersion, nameof(request.ApplicationVersion), MaxVersionLength) ?? callback.Version;
        string channelId = NormalizeOptional(request.ChannelId, nameof(request.ChannelId), MaxChannelIdLength) ?? callback.Channel;
        string headId = NormalizeOptional(request.HeadId, nameof(request.HeadId), MaxHeadIdLength) ?? callback.HeadId ?? existingInstallation?.HeadId ?? "desktop";
        string platform = NormalizeOptional(request.Platform, nameof(request.Platform), MaxPlatformLength) ?? callback.Platform ?? existingInstallation?.Platform ?? "unknown";
        string arch = NormalizeOptional(request.Arch, nameof(request.Arch), MaxArchLength) ?? callback.Arch ?? existingInstallation?.Arch ?? "unknown";
        string? publicKey = NormalizeOptional(request.PublicKey, nameof(request.PublicKey), MaxPublicKeyLength) ?? callback.PublicKey ?? existingInstallation?.PublicKey;
        string? hostLabel = NormalizeOptional(request.HostLabel, nameof(request.HostLabel), MaxHostLabelLength) ?? callback.HostLabel ?? existingInstallation?.HostLabel;

        return new ClaimedInstallationDto(
            InstallationId: NormalizeOptional(request.InstallationId, nameof(request.InstallationId), MaxInstallationIdLength)
                ?? existingInstallation?.InstallationId ?? callback.InstallationId,
            ArtifactId: callback.ArtifactId,
            Channel: channelId,
            Version: version,
            InstallAccessClass: NormalizeAccessClass(callback.InstallAccessClass),
            Status: ClaimedInstallationStates.Active,
            CreatedAtUtc: existingInstallation?.CreatedAtUtc ?? now,
            UpdatedAtUtc: now,
            UserId: callback.UserId,
            SubjectId: callback.SubjectId,
            PublicKey: publicKey,
            ClaimTicketId: existingInstallation?.ClaimTicketId,
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
            HeadId = NormalizeOptional(request.HeadId, nameof(request.HeadId), MaxHeadIdLength) ?? installation.HeadId,
            Version = NormalizeOptional(request.ApplicationVersion, nameof(request.ApplicationVersion), MaxVersionLength) ?? installation.Version,
            Channel = NormalizeOptional(request.ChannelId, nameof(request.ChannelId), MaxChannelIdLength) ?? installation.Channel,
            Platform = NormalizeOptional(request.Platform, nameof(request.Platform), MaxPlatformLength) ?? installation.Platform,
            Arch = NormalizeOptional(request.Arch, nameof(request.Arch), MaxArchLength) ?? installation.Arch,
            PublicKey = NormalizeOptional(request.PublicKey, nameof(request.PublicKey), MaxPublicKeyLength) ?? installation.PublicKey,
            HostLabel = NormalizeOptional(request.HostLabel, nameof(request.HostLabel), MaxHostLabelLength) ?? installation.HostLabel
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
        // Every new grant terminates every older browser bearer for this installation. The
        // callback-exchange path deliberately restores only the callback that created this exact
        // grant after this method returns, preserving lost-response retry without allowing an
        // older callback to reveal a subsequently rotated token.
        RevokeBrowserCallbacksForInstallationLocked(installation.InstallationId);
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

    private void ExpireBrowserCallbacksLocked(DateTimeOffset now)
    {
        var dirty = false;
        foreach (InstallBrowserCallbackDto callback in _store.BrowserCallbacksById.Values.ToArray())
        {
            if (callback.ExpiresAtUtc > now)
            {
                continue;
            }

            bool pending = string.Equals(
                callback.Status,
                InstallBrowserCallbackStates.Pending,
                StringComparison.OrdinalIgnoreCase);
            if (!pending
                && string.IsNullOrEmpty(callback.CallbackCode)
                && callback.CallbackUri is null)
            {
                continue;
            }

            _store.BrowserCallbacksById[callback.CallbackId] = callback with
            {
                Status = pending ? InstallBrowserCallbackStates.Expired : callback.Status,
                CallbackCode = string.Empty,
                CallbackUri = null
            };
            dirty = true;
        }

        if (dirty)
        {
            _store.PersistLocked();
        }
    }

    private void RevokeBrowserCallbacksForInstallationLocked(string installationId)
    {
        foreach (InstallBrowserCallbackDto callback in _store.BrowserCallbacksById.Values
                     .Where(item => string.Equals(
                         item.InstallationId,
                         installationId,
                         StringComparison.OrdinalIgnoreCase))
                     .ToArray())
        {
            _store.BrowserCallbacksById[callback.CallbackId] = callback with
            {
                Status = InstallBrowserCallbackStates.Revoked,
                CallbackCode = string.Empty,
                CallbackUri = null
            };
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

    private void EnforceRecentReceiptLimitLocked(string? userId, string? subjectId, DateTimeOffset now)
    {
        if (userId is null && subjectId is null)
        {
            return;
        }

        DateTimeOffset cutoff = now.AddHours(-1);
        int count = 0;
        foreach (DownloadReceiptDto receipt in _store.ReceiptsById.Values)
        {
            if (receipt.IssuedAtUtc >= cutoff
                && MatchesIdentity(receipt.UserId, receipt.SubjectId, userId, subjectId)
                && ++count >= _maxDownloadReceiptsPerPrincipalPerHour)
            {
                throw IssuanceLimitReached();
            }
        }
    }

    private void EnforcePendingTicketLimitLocked(string? userId, string? subjectId, DateTimeOffset now)
    {
        int count = 0;
        foreach (InstallClaimTicketDto ticket in _store.ClaimTicketsById.Values)
        {
            if (ticket.ExpiresAtUtc > now
                && string.Equals(ticket.Status, InstallClaimTicketStates.Pending, StringComparison.OrdinalIgnoreCase)
                && MatchesIdentity(ticket.UserId, ticket.SubjectId, userId, subjectId)
                && ++count >= _maxPendingClaimTicketsPerPrincipal)
            {
                throw IssuanceLimitReached();
            }
        }
    }

    private void EnforcePendingCallbackLimitLocked(string? userId, string? subjectId, DateTimeOffset now)
    {
        int count = 0;
        foreach (InstallBrowserCallbackDto callback in _store.BrowserCallbacksById.Values)
        {
            if (callback.ExpiresAtUtc > now
                && string.Equals(callback.Status, InstallBrowserCallbackStates.Pending, StringComparison.OrdinalIgnoreCase)
                && MatchesIdentity(callback.UserId, callback.SubjectId, userId, subjectId)
                && ++count >= _maxPendingBrowserCallbacksPerPrincipal)
            {
                throw IssuanceLimitReached();
            }
        }
    }

    private static InstallLinkingOperationException IssuanceLimitReached()
        => new(StatusCodes.Status429TooManyRequests, "install-link issuance limit reached.");

    private bool IsDurableStoreReady()
    {
        if (_readinessProbe is null)
        {
            return _store.IsHealthy;
        }

        try
        {
            return _readinessProbe.Evaluate().Ready && _store.IsHealthy;
        }
        catch
        {
            return false;
        }
    }

    private void EnsureDurableStoreReady()
    {
        if (!IsDurableStoreReady())
        {
            throw new InstallLinkingOperationException(
                StatusCodes.Status503ServiceUnavailable,
                "Install-linking is temporarily unavailable.");
        }
    }

    private static int ResolveBoundedLimit(string? configured, int fallback, int maximum)
        => int.TryParse(configured, out int parsed)
            ? Math.Clamp(parsed, 1, maximum)
            : fallback;

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

    private static TimeSpan ResolveBrowserCallbackLifetime(IConfiguration configuration)
    {
        string? configuredMinutes = configuration["CHUMMER_INSTALL_BROWSER_CALLBACK_LIFETIME_MINUTES"];
        if (int.TryParse(configuredMinutes, out int minutes))
        {
            minutes = Math.Clamp(minutes, 5, 24 * 60);
            return TimeSpan.FromMinutes(minutes);
        }

        return DefaultBrowserCallbackLifetime;
    }

    private static string NewId(string prefix)
        => $"{prefix}-{Guid.NewGuid():N}"[..Math.Min(prefix.Length + 13, prefix.Length + 1 + 12)];

    private static string NewClaimCode()
    {
        var bytes = RandomNumberGenerator.GetBytes(10);
        var hex = Convert.ToHexString(bytes);
        return $"{hex[..5]}-{hex[5..10]}-{hex[10..15]}-{hex[15..20]}";
    }

    private static string NewCallbackCode()
    {
        var bytes = RandomNumberGenerator.GetBytes(18);
        return Convert.ToBase64String(bytes)
            .TrimEnd('=')
            .Replace("+", "-", StringComparison.Ordinal)
            .Replace("/", "_", StringComparison.Ordinal);
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
        var normalized = NormalizeOptional(value, "claim code", MaxClaimCodeLength);
        if (normalized is null)
        {
            return null;
        }

        return string.Concat(normalized.Where(char.IsLetterOrDigit)).ToUpperInvariant();
    }

    private static string? NormalizeBrowserCallbackCode(string? value)
        => NormalizeOptional(value, "callback code", MaxCallbackCodeLength);

    private static string NormalizeRequiredArtifactSha256(string? value)
        => NormalizeArtifactSha256OrNull(value)
            ?? throw new InvalidOperationException("generation-bound install claims require an exact artifact SHA-256.");

    private static string? NormalizeArtifactSha256OrNull(string? value)
    {
        string? normalized = NormalizeOptional(value)?.ToLowerInvariant();
        return normalized is not null
               && normalized.Length == 64
               && normalized.All(static character => Uri.IsHexDigit(character))
            ? normalized
            : null;
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = System.Text.Encoding.ASCII.GetBytes(left);
        byte[] rightBytes = System.Text.Encoding.ASCII.GetBytes(right);
        return leftBytes.Length == rightBytes.Length
            && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string? NormalizeOptional(string? value, string label, int maxLength)
    {
        string? normalized = NormalizeOptional(value);
        if (normalized is null)
        {
            return null;
        }

        if (normalized.Length > maxLength)
        {
            throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, $"{label} exceeds the maximum length of {maxLength} characters.");
        }

        return normalized;
    }

    private static string NormalizeRequired(string value, string label, int maxLength)
        => NormalizeOptional(value, label, maxLength) ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, $"{label} is required.");
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
