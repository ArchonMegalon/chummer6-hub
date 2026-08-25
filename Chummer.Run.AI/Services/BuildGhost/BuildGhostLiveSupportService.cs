using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Chummer.Run.AI.Services.BuildGhost;

public interface IBuildGhostMeetingLinkBroker
{
    Task<BuildGhostMeetingLinkProvisioningResult> CreateAsync(
        BuildGhostMeetingLinkProvisioningCommand command,
        CancellationToken cancellationToken);

    Task<BuildGhostMeetingLinkCancellationResult> CancelAsync(
        BuildGhostMeetingLinkCancellationCommand command,
        CancellationToken cancellationToken);
}

public interface IToughTongueLiveSupportMeetingClient
{
    Task<BuildGhostToughTongueMeetingBotResult> ScheduleAsync(
        BuildGhostToughTongueMeetingBotCommand command,
        CancellationToken cancellationToken);
}

public interface IToughTongueLiveSupportAuthorityBinding
{
    string ScenarioRefDigest { get; }
}

public interface IBuildGhostLiveSupportDependencyReadiness
{
    IReadOnlyList<string> BlockingReasons { get; }
}

public interface IBuildGhostLiveSupportService
{
    BuildGhostSupportExperienceProjection BuildExperience();

    Task<BuildGhostLiveSupportSessionProjection> RequestAsync(
        BuildGhostLiveSupportRequest request,
        CancellationToken cancellationToken);

    Task<BuildGhostLiveSupportSessionProjection?> GetAsync(
        BuildGhostLiveSupportStatusRequest request,
        CancellationToken cancellationToken);
}

public sealed class DisabledBuildGhostMeetingLinkBroker : IBuildGhostMeetingLinkBroker, IBuildGhostLiveSupportDependencyReadiness
{
    public IReadOnlyList<string> BlockingReasons => ["meeting-link-broker-disabled"];

    public Task<BuildGhostMeetingLinkProvisioningResult> CreateAsync(
        BuildGhostMeetingLinkProvisioningCommand command,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(new BuildGhostMeetingLinkProvisioningResult(
            false,
            false,
            "meeting-link-broker-disabled",
            command.MeetingProvider,
            null,
            string.Empty,
            string.Empty,
            string.Empty,
            null,
            null));
    }

    public Task<BuildGhostMeetingLinkCancellationResult> CancelAsync(
        BuildGhostMeetingLinkCancellationCommand command,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(new BuildGhostMeetingLinkCancellationResult(
            false,
            "meeting-link-broker-disabled",
            string.Empty));
    }
}

public sealed class DisabledToughTongueLiveSupportMeetingClient : IToughTongueLiveSupportMeetingClient, IBuildGhostLiveSupportDependencyReadiness
{
    public IReadOnlyList<string> BlockingReasons => ["tough-tongue-meeting-bot-disabled"];

    public Task<BuildGhostToughTongueMeetingBotResult> ScheduleAsync(
        BuildGhostToughTongueMeetingBotCommand command,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(new BuildGhostToughTongueMeetingBotResult(
            false,
            false,
            "tough-tongue-meeting-bot-disabled",
            string.Empty,
            string.Empty,
            string.Empty));
    }
}

public sealed class BuildGhostLiveSupportService : IBuildGhostLiveSupportService
{
    public const string RemoteExecutionEnabledKey = "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_REMOTE_EXECUTION_ENABLED";
    public const string CapabilityReceiptPathKey = "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_CAPABILITY_RECEIPT_PATH";
    public const string CapabilityReceiptHmacKey = "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_CAPABILITY_HMAC_KEY";
    public const string ExpectedAccountScopeDigestKey = "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_ACCOUNT_SCOPE_REF_DIGEST";
    public const string ExpectedScenarioDigestKey = "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SCENARIO_REF_DIGEST";
    public const string ExpectedAvatarBindingDigestKey = "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_AVATAR_BINDING_DIGEST";
    public const string RookVidBoardMediaHrefKey = "CHUMMER_BUILD_GHOST_ROOK_VIDBOARD_MEDIA_HREF";
    public const string RookVidBoardMediaDigestKey = "CHUMMER_BUILD_GHOST_ROOK_VIDBOARD_MEDIA_DIGEST";

    private const string DeterministicFallback =
        "Rook can continue in the grounded Chummer help flow while live support is unavailable.";
    private const int MaximumReceiptBytes = 64 * 1024;
    private static readonly Regex SafeIdentifier = new(
        "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex SafeLocale = new(
        "^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2}$",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);

    private readonly IConfiguration _configuration;
    private readonly IBuildGhostPersonaReleaseRegistry _personaReleases;
    private readonly IBuildGhostMeetingLinkBroker _meetingLinks;
    private readonly IToughTongueLiveSupportMeetingClient _meetingBots;
    private readonly IBuildGhostLiveSupportSessionStore _sessionStore;
    private readonly IBuildGhostClock _clock;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public BuildGhostLiveSupportService(
        IConfiguration configuration,
        IBuildGhostPersonaReleaseRegistry personaReleases,
        IBuildGhostMeetingLinkBroker meetingLinks,
        IToughTongueLiveSupportMeetingClient meetingBots,
        IBuildGhostClock clock,
        IBuildGhostLiveSupportSessionStore? sessionStore = null)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _personaReleases = personaReleases ?? throw new ArgumentNullException(nameof(personaReleases));
        _meetingLinks = meetingLinks ?? throw new ArgumentNullException(nameof(meetingLinks));
        _meetingBots = meetingBots ?? throw new ArgumentNullException(nameof(meetingBots));
        _clock = clock ?? throw new ArgumentNullException(nameof(clock));
        _sessionStore = sessionStore ?? new DisabledBuildGhostLiveSupportSessionStore();
    }

    public BuildGhostSupportExperienceProjection BuildExperience()
    {
        BuildGhostDefaultSupportProjection defaultSupport = BuildDefaultSupport();
        (BuildGhostLiveSupportCapabilityReceipt? receipt, IReadOnlyList<string> receiptFailures) =
            LoadCapabilityReceipt();
        List<string> blockers = [.. receiptFailures];
        blockers.AddRange(DependencyBlockers());
        if (!RemoteExecutionEnabled())
        {
            blockers.Add("live-support-remote-execution-disabled-by-default");
        }

        string[] providers = receipt is null
            ? []
            : receipt.MeetingProviders
                .Where(provider => IsMeetingProvider(provider))
                .Distinct(StringComparer.Ordinal)
                .OrderBy(static provider => provider, StringComparer.Ordinal)
                .ToArray();
        bool available = blockers.Count == 0 && providers.Length != 0;
        return new BuildGhostSupportExperienceProjection(
            ToughTongueBuildGhostContractVersions.SupportExperienceV1,
            defaultSupport,
            new BuildGhostLiveSupportCapabilityProjection(
                BuildGhostSupportChannelKinds.LivePhotorealMeeting,
                available,
                providers,
                available ? "photorealistic-provider-managed" : "unavailable",
                receipt?.RecordingDisclosureRequired ?? true,
                blockers.Distinct(StringComparer.Ordinal).OrderBy(static reason => reason, StringComparer.Ordinal).ToArray()));
    }

    public async Task<BuildGhostLiveSupportSessionProjection> RequestAsync(
        BuildGhostLiveSupportRequest request,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        DateTimeOffset now = _clock.UtcNow;
        BuildGhostDefaultSupportProjection fallback = BuildDefaultSupport();
        List<string> validationFailures = ValidateRequest(request, now);
        if (validationFailures.Count != 0)
        {
            return Failed(request, now, fallback, validationFailures);
        }

        string requestFingerprint = RequestFingerprint(request);

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            StoredBuildGhostLiveSupportSession? stored;
            try
            {
                stored = await _sessionStore.ReadAsync(
                    request.OwnerScopeHash,
                    request.RequestId,
                    request.WorkspaceId,
                    request.SourceDigest,
                    cancellationToken).ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or InvalidDataException)
            {
                return Failed(request, now, fallback, ["live-support-session-store-read-failed"]);
            }

            if (stored is not null)
            {
                return FixedTimeDigestEquals(stored.RequestFingerprint, requestFingerprint)
                    ? stored.Session
                    : Failed(request, now, fallback, ["live-support-idempotency-conflict"]);
            }

            List<string> blockers = [];
            blockers.AddRange(DependencyBlockers());
            if (!RemoteExecutionEnabled())
            {
                blockers.Add("live-support-remote-execution-disabled-by-default");
            }

            (BuildGhostLiveSupportCapabilityReceipt? receipt, IReadOnlyList<string> receiptFailures) =
                LoadCapabilityReceipt();
            blockers.AddRange(receiptFailures);
            if (receipt is not null
                && !receipt.MeetingProviders.Contains(request.MeetingProvider, StringComparer.Ordinal))
            {
                blockers.Add($"{request.MeetingProvider}-live-support-capability-unverified");
            }
            if (receipt is not null
                && request.RequestedDurationMinutes * receipt.LiveAvatarMinutesMultiplier + receipt.ReservedMinutes
                    > receipt.AvailableMinutesAtObservation)
            {
                blockers.Add("live-support-provider-minute-reserve-insufficient");
            }
            bool? hasOpenReservation;
            try
            {
                hasOpenReservation = await _sessionStore.HasOpenReservationAsync(now, cancellationToken)
                    .ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is IOException
                or UnauthorizedAccessException
                or InvalidDataException)
            {
                hasOpenReservation = null;
            }
            if (hasOpenReservation is null)
            {
                blockers.Add("live-support-provider-capacity-reservation-unverified");
            }
            else if (hasOpenReservation.Value)
            {
                blockers.Add("live-support-provider-capacity-reservation-open");
            }

            if (blockers.Count != 0 || receipt is null)
            {
                return await PersistFailureAsync(
                    request,
                    requestFingerprint,
                    Failed(request, now, fallback, blockers),
                    cancellationToken).ConfigureAwait(false);
            }

            BuildGhostLiveSupportSessionProjection meetingJournal = Provisioning(
                request,
                BuildGhostLiveSupportStatuses.ProvisioningMeeting,
                receipt.ReceiptDigest,
                string.Empty,
                fallback,
                []);
            if (!await PersistAsync(
                    request,
                    requestFingerprint,
                    meetingJournal,
                    cancellationToken).ConfigureAwait(false))
            {
                return Failed(
                    request,
                    _clock.UtcNow,
                    fallback,
                    ["live-support-provisioning-journal-write-failed"]);
            }

            BuildGhostMeetingLinkProvisioningResult meeting;
            try
            {
                meeting = await _meetingLinks.CreateAsync(
                    new BuildGhostMeetingLinkProvisioningCommand(
                        request.RequestId,
                        request.OwnerScopeHash,
                        request.MeetingProvider,
                        request.Locale,
                        request.RequestedDurationMinutes,
                        request.IdempotencyKey),
                    cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch
            {
                BuildGhostLiveSupportSessionProjection uncertain = meetingJournal with
                {
                    UpdatedAtUtc = _clock.UtcNow,
                    BlockingReasons = ["meeting-link-provisioning-reconciliation-required"]
                };
                await PersistAsync(
                    request,
                    requestFingerprint,
                    uncertain,
                    cancellationToken).ConfigureAwait(false);
                return uncertain;
            }

            if (meeting.ReconciliationRequired)
            {
                BuildGhostLiveSupportSessionProjection uncertain = meetingJournal with
                {
                    UpdatedAtUtc = _clock.UtcNow,
                    BlockingReasons = [
                        NormalizeOutcome(meeting.OutcomeCode, "meeting-link-provisioning-reconciliation-required"),
                        "meeting-link-provisioning-reconciliation-required"
                    ]
                };
                await PersistAsync(
                    request,
                    requestFingerprint,
                    uncertain,
                    cancellationToken).ConfigureAwait(false);
                return uncertain;
            }

            IReadOnlyList<string> meetingFailures = ValidateMeeting(meeting, request.MeetingProvider, _clock.UtcNow);
            if (meetingFailures.Count != 0 || meeting.JoinUrl is null)
            {
                List<string> compensatedFailures = [.. meetingFailures];
                if (meeting.Success && IsSafeIdentifier(meeting.CancellationHandle))
                {
                    await TryCompensateMeetingAsync(request, meeting, compensatedFailures)
                        .ConfigureAwait(false);
                }
                else if (meeting.Success)
                {
                    compensatedFailures.Add("meeting-link-compensation-unverified");
                }
                BuildGhostLiveSupportSessionProjection meetingFailure = compensatedFailures.Contains(
                    "meeting-link-compensation-unverified",
                    StringComparer.Ordinal)
                    ? meetingJournal with
                    {
                        UpdatedAtUtc = _clock.UtcNow,
                        BlockingReasons = compensatedFailures
                            .Append("meeting-link-provisioning-reconciliation-required")
                            .Distinct(StringComparer.Ordinal)
                            .OrderBy(static reason => reason, StringComparer.Ordinal)
                            .ToArray()
                    }
                    : Failed(request, _clock.UtcNow, fallback, compensatedFailures);
                return await PersistFailureAsync(
                    request,
                    requestFingerprint,
                    meetingFailure,
                    cancellationToken).ConfigureAwait(false);
            }

            BuildGhostLiveSupportSessionProjection avatarJournal = Provisioning(
                request,
                BuildGhostLiveSupportStatuses.ProvisioningAvatar,
                receipt.ReceiptDigest,
                DigestMeetingReceipt(meeting),
                fallback,
                []);
            if (!await PersistAsync(
                    request,
                    requestFingerprint,
                    avatarJournal,
                    cancellationToken).ConfigureAwait(false))
            {
                List<string> journalFailures = ["live-support-provisioning-journal-write-failed"];
                await TryCompensateMeetingAsync(request, meeting, journalFailures).ConfigureAwait(false);
                return meetingJournal with
                {
                    UpdatedAtUtc = _clock.UtcNow,
                    BlockingReasons = journalFailures
                        .Append("meeting-link-provisioning-reconciliation-required")
                        .Distinct(StringComparer.Ordinal)
                        .OrderBy(static reason => reason, StringComparer.Ordinal)
                        .ToArray()
                };
            }

            BuildGhostToughTongueMeetingBotResult bot;
            try
            {
                bot = await _meetingBots.ScheduleAsync(
                    new BuildGhostToughTongueMeetingBotCommand(
                        request.RequestId,
                        request.MeetingProvider,
                        meeting.JoinUrl,
                        request.IdempotencyKey),
                    cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                List<string> cancellationFailures = [];
                await TryCompensateMeetingAsync(request, meeting, cancellationFailures).ConfigureAwait(false);
                throw;
            }
            catch
            {
                List<string> uncertainFailures = ["tough-tongue-meeting-bot-reconciliation-required"];
                await TryCompensateMeetingAsync(request, meeting, uncertainFailures).ConfigureAwait(false);
                BuildGhostLiveSupportSessionProjection uncertain = avatarJournal with
                {
                    UpdatedAtUtc = _clock.UtcNow,
                    BlockingReasons = uncertainFailures
                        .Distinct(StringComparer.Ordinal)
                        .OrderBy(static reason => reason, StringComparer.Ordinal)
                        .ToArray()
                };
                await PersistAsync(
                    request,
                    requestFingerprint,
                    uncertain,
                    cancellationToken).ConfigureAwait(false);
                return uncertain;
            }

            if (bot.ReconciliationRequired)
            {
                List<string> uncertainFailures = [
                    NormalizeOutcome(bot.OutcomeCode, "tough-tongue-meeting-bot-reconciliation-required"),
                    "tough-tongue-meeting-bot-reconciliation-required"
                ];
                await TryCompensateMeetingAsync(request, meeting, uncertainFailures).ConfigureAwait(false);
                BuildGhostLiveSupportSessionProjection uncertain = avatarJournal with
                {
                    UpdatedAtUtc = _clock.UtcNow,
                    BlockingReasons = uncertainFailures
                        .Distinct(StringComparer.Ordinal)
                        .OrderBy(static reason => reason, StringComparer.Ordinal)
                        .ToArray()
                };
                await PersistAsync(
                    request,
                    requestFingerprint,
                    uncertain,
                    cancellationToken).ConfigureAwait(false);
                return uncertain;
            }

            IReadOnlyList<string> botFailures = ValidateBot(bot);
            if (botFailures.Count != 0)
            {
                List<string> compensatedFailures = [.. botFailures];
                await TryCompensateMeetingAsync(request, meeting, compensatedFailures)
                    .ConfigureAwait(false);
                BuildGhostLiveSupportSessionProjection botFailure = compensatedFailures.Contains(
                    "meeting-link-compensation-unverified",
                    StringComparer.Ordinal)
                    ? avatarJournal with
                    {
                        UpdatedAtUtc = _clock.UtcNow,
                        BlockingReasons = compensatedFailures
                            .Append("tough-tongue-meeting-bot-reconciliation-required")
                            .Distinct(StringComparer.Ordinal)
                            .OrderBy(static reason => reason, StringComparer.Ordinal)
                            .ToArray()
                    }
                    : Failed(request, _clock.UtcNow, fallback, compensatedFailures);
                return await PersistFailureAsync(
                    request,
                    requestFingerprint,
                    botFailure,
                    cancellationToken).ConfigureAwait(false);
            }

            DateTimeOffset completedAt = _clock.UtcNow;
            BuildGhostLiveSupportSessionProjection ready = new(
                ToughTongueBuildGhostContractVersions.LiveSupportSessionV1,
                request.RequestId,
                BuildGhostSupportChannelKinds.LivePhotorealMeeting,
                BuildGhostLiveSupportStatuses.Ready,
                request.MeetingProvider,
                meeting.JoinUrl,
                meeting.ExpiresAtUtc,
                receipt.AvatarAlias,
                "photorealistic-provider-managed",
                request.RecordingConsentGranted,
                request.ExternalProviderProcessingConsentGranted,
                request.DisclosureVersion,
                request.DisclosureDigest,
                DigestText(meeting.JoinUrl.AbsoluteUri),
                DigestMeetingReceipt(meeting),
                DigestBotReceipt(bot),
                receipt.ReceiptDigest,
                request.RequestedAtUtc,
                completedAt,
                fallback,
                []);
            if (!await PersistAsync(request, requestFingerprint, ready, cancellationToken).ConfigureAwait(false))
            {
                List<string> persistenceFailures = ["live-support-session-store-write-failed"];
                await TryCompensateMeetingAsync(request, meeting, persistenceFailures).ConfigureAwait(false);
                return avatarJournal with
                {
                    UpdatedAtUtc = _clock.UtcNow,
                    BlockingReasons = persistenceFailures
                        .Append("tough-tongue-meeting-bot-reconciliation-required")
                        .Distinct(StringComparer.Ordinal)
                        .OrderBy(static reason => reason, StringComparer.Ordinal)
                        .ToArray()
                };
            }
            return ready;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<BuildGhostLiveSupportSessionProjection?> GetAsync(
        BuildGhostLiveSupportStatusRequest request,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        if (!string.Equals(
                request.Schema,
                ToughTongueBuildGhostContractVersions.LiveSupportStatusRequestV1,
                StringComparison.Ordinal)
            || !IsSha256(request.OwnerScopeHash)
            || !IsSafeIdentifier(request.RequestId)
            || !IsSafeIdentifier(request.WorkspaceId)
            || !IsSha256(request.SourceDigest)
            || _sessionStore.BlockingReasons.Count != 0)
        {
            return null;
        }

        StoredBuildGhostLiveSupportSession? stored;
        try
        {
            stored = await _sessionStore.ReadAsync(
                request.OwnerScopeHash,
                request.RequestId,
                request.WorkspaceId,
                request.SourceDigest,
                cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or InvalidDataException)
        {
            return null;
        }

        if (stored is null)
        {
            return null;
        }

        BuildGhostLiveSupportSessionProjection session = stored.Session;
        bool contextChanged = !FixedTimeDigestEquals(stored.SourceDigest, request.SourceDigest);
        if (session.JoinUrl is not null
            && session.JoinUrlExpiresAtUtc is DateTimeOffset expiresAt
            && expiresAt <= _clock.UtcNow)
        {
            BuildGhostLiveSupportSessionProjection persistedExpired = session with
            {
                Status = BuildGhostLiveSupportStatuses.Expired,
                JoinUrl = null,
                UpdatedAtUtc = _clock.UtcNow,
                BlockingReasons = ["live-support-meeting-link-expired"]
            };
            await _sessionStore.WriteAsync(
                stored with { Session = persistedExpired },
                cancellationToken).ConfigureAwait(false);
            return contextChanged
                ? persistedExpired with
                {
                    BlockingReasons = [
                        "live-support-handoff-context-changed-after-request",
                        "live-support-meeting-link-expired"
                    ]
                }
                : persistedExpired;
        }

        return contextChanged
            ? session with
            {
                BlockingReasons = (session.BlockingReasons ?? [])
                    .Append("live-support-handoff-context-changed-after-request")
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(static reason => reason, StringComparer.Ordinal)
                    .ToArray()
            }
            : session;
    }

    public static string DigestCapabilityReceipt(BuildGhostLiveSupportCapabilityReceipt receipt)
    {
        ArgumentNullException.ThrowIfNull(receipt);
        JsonArray providers = [];
        foreach (string provider in receipt.MeetingProviders ?? [])
        {
            providers.Add(provider);
        }

        JsonObject authority = new()
        {
            ["schema"] = receipt.Schema,
            ["meetingProviders"] = providers,
            ["accountScopeRefDigest"] = receipt.AccountScopeRefDigest,
            ["scenarioRefDigest"] = receipt.ScenarioRefDigest,
            ["avatarAlias"] = receipt.AvatarAlias,
            ["avatarBindingDigest"] = receipt.AvatarBindingDigest,
            ["photorealisticVideoInMeetingVerified"] = receipt.PhotorealisticVideoInMeetingVerified,
            ["recordingDisclosureRequired"] = receipt.RecordingDisclosureRequired,
            ["availableMinutesAtObservation"] = receipt.AvailableMinutesAtObservation,
            ["reservedMinutes"] = receipt.ReservedMinutes,
            ["liveAvatarMinutesMultiplier"] = receipt.LiveAvatarMinutesMultiplier,
            ["evidenceSource"] = receipt.EvidenceSource,
            ["observedAtUtc"] = receipt.ObservedAtUtc.ToUniversalTime().ToString("O"),
            ["maximumAgeSeconds"] = receipt.MaximumAgeSeconds
        };
        return DigestText(authority.ToJsonString(new JsonSerializerOptions { WriteIndented = false }));
    }

    public static string ComputeCapabilityReceiptAuthorityMac(
        BuildGhostLiveSupportCapabilityReceipt receipt,
        ReadOnlySpan<byte> key)
    {
        ArgumentNullException.ThrowIfNull(receipt);
        if (key.Length != 32)
        {
            throw new ArgumentException("Capability receipt authority key must contain exactly 32 bytes.", nameof(key));
        }

        string receiptDigest = DigestCapabilityReceipt(receipt);
        byte[] mac = HMACSHA256.HashData(key, Encoding.UTF8.GetBytes(receiptDigest));
        return $"hmac-sha256:{Convert.ToHexString(mac).ToLowerInvariant()}";
    }

    private BuildGhostDefaultSupportProjection BuildDefaultSupport()
    {
        BuildGhostPersonaReleaseProjection release = _personaReleases.ResolveRookVidBoard();
        BuildGhostPersonaMediaRelease? media = _personaReleases.ResolveRookVidBoardMedia();
        List<string> blockers = [.. release.BlockingReasons];
        string configuredHref = (_configuration[RookVidBoardMediaHrefKey] ?? string.Empty).Trim();
        string configuredDigest = (_configuration[RookVidBoardMediaDigestKey] ?? string.Empty).Trim();
        string? mediaHref = IsSafeSameOriginMediaHref(configuredHref) ? configuredHref : null;
        bool digestBound = media is not null
            && IsSha256(configuredDigest)
            && FixedTimeDigestEquals(media.ContentDigest, configuredDigest);
        bool videoReady = release.AvatarReady && mediaHref is not null && digestBound;
        if (!release.AvatarReady)
        {
            blockers.Add("rook-vidboard-support-video-unavailable");
        }
        if (mediaHref is null)
        {
            blockers.Add("rook-vidboard-support-video-href-missing-or-invalid");
        }
        if (!digestBound)
        {
            blockers.Add("rook-vidboard-support-video-digest-binding-invalid");
        }

        return new BuildGhostDefaultSupportProjection(
            BuildGhostSupportChannelKinds.RookVidBoard,
            ToughTongueBuildGhostPersonaIds.Rook,
            ToughTongueBuildGhostPersonaIds.RookAvatar,
            ToughTongueBuildGhostPersonaIds.RookVidBoardSupport,
            videoReady ? mediaHref : null,
            videoReady ? configuredDigest : string.Empty,
            videoReady,
            videoReady ? "ready" : "text-fallback",
            DeterministicFallback,
            blockers.Distinct(StringComparer.Ordinal).OrderBy(static reason => reason, StringComparer.Ordinal).ToArray());
    }

    private (BuildGhostLiveSupportCapabilityReceipt? Receipt, IReadOnlyList<string> Failures) LoadCapabilityReceipt()
    {
        List<string> failures = [];
        string configuredPath = _configuration[CapabilityReceiptPathKey]?.Trim() ?? string.Empty;
        if (string.IsNullOrEmpty(configuredPath) || !Path.IsPathFullyQualified(configuredPath))
        {
            failures.Add("live-support-capability-receipt-path-missing-or-invalid");
            return (null, failures);
        }

        FileInfo file = new(Path.GetFullPath(configuredPath));
        if (!file.Exists || file.Length <= 0 || file.Length > MaximumReceiptBytes || file.LinkTarget is not null)
        {
            failures.Add("live-support-capability-receipt-file-missing-or-invalid");
            return (null, failures);
        }

        if (!OperatingSystem.IsWindows())
        {
            try
            {
                UnixFileMode mode = File.GetUnixFileMode(file.FullName);
                if ((mode & (UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute
                    | UnixFileMode.OtherRead | UnixFileMode.OtherWrite | UnixFileMode.OtherExecute)) != 0)
                {
                    failures.Add("live-support-capability-receipt-permissions-not-private");
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or PlatformNotSupportedException)
            {
                failures.Add("live-support-capability-receipt-permissions-unverified");
            }
        }

        BuildGhostLiveSupportCapabilityReceipt? receipt;
        try
        {
            receipt = JsonSerializer.Deserialize<BuildGhostLiveSupportCapabilityReceipt>(
                File.ReadAllText(file.FullName),
                new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = false,
                    UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow
                });
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            failures.Add("live-support-capability-receipt-json-invalid");
            return (null, failures);
        }

        if (receipt is null)
        {
            failures.Add("live-support-capability-receipt-json-invalid");
            return (null, failures);
        }

        failures.AddRange(ValidateCapabilityReceipt(receipt, _clock.UtcNow));
        return failures.Count == 0 ? (receipt, []) : (null, failures);
    }

    private IReadOnlyList<string> ValidateCapabilityReceipt(
        BuildGhostLiveSupportCapabilityReceipt receipt,
        DateTimeOffset now)
    {
        List<string> failures = [];
        if (!string.Equals(receipt.Schema, ToughTongueBuildGhostContractVersions.LiveSupportCapabilityReceiptV1, StringComparison.Ordinal))
            failures.Add("live-support-capability-receipt-schema-invalid");
        if (receipt.MeetingProviders is null
            || receipt.MeetingProviders.Count == 0
            || receipt.MeetingProviders.Any(provider => !IsMeetingProvider(provider))
            || receipt.MeetingProviders.Distinct(StringComparer.Ordinal).Count() != receipt.MeetingProviders.Count
            || !receipt.MeetingProviders.SequenceEqual(receipt.MeetingProviders.OrderBy(static value => value, StringComparer.Ordinal), StringComparer.Ordinal))
            failures.Add("live-support-capability-meeting-providers-invalid");
        if (!IsSha256(receipt.AccountScopeRefDigest)) failures.Add("live-support-capability-account-scope-digest-invalid");
        if (!IsSha256(receipt.ScenarioRefDigest)) failures.Add("live-support-capability-scenario-digest-invalid");
        if (!string.Equals(receipt.AvatarAlias, ToughTongueBuildGhostPersonaIds.StockDefaultAvatar, StringComparison.Ordinal))
            failures.Add("live-support-capability-avatar-alias-invalid");
        if (!IsSha256(receipt.AvatarBindingDigest)) failures.Add("live-support-capability-avatar-binding-digest-invalid");
        if (!receipt.PhotorealisticVideoInMeetingVerified)
            failures.Add("live-support-photorealistic-video-in-meeting-unverified");
        if (!receipt.RecordingDisclosureRequired)
            failures.Add("live-support-recording-disclosure-not-required");
        if (receipt.AvailableMinutesAtObservation is < 0 or > 1_000_000)
            failures.Add("live-support-capability-available-minutes-invalid");
        if (receipt.ReservedMinutes is < 0 or > 1_000_000)
            failures.Add("live-support-capability-reserved-minutes-invalid");
        if (receipt.LiveAvatarMinutesMultiplier is < 1 or > 10)
            failures.Add("live-support-capability-avatar-minute-multiplier-invalid");
        if (receipt.AvailableMinutesAtObservation < receipt.ReservedMinutes)
            failures.Add("live-support-capability-minute-reserve-insufficient");
        if (string.IsNullOrWhiteSpace(receipt.EvidenceSource) || receipt.EvidenceSource.Length > 160)
            failures.Add("live-support-capability-evidence-source-invalid");
        if (receipt.MaximumAgeSeconds is < 60 or > 86_400)
            failures.Add("live-support-capability-maximum-age-invalid");
        if (receipt.ObservedAtUtc > now.AddMinutes(5)
            || now - receipt.ObservedAtUtc > TimeSpan.FromSeconds(Math.Max(receipt.MaximumAgeSeconds, 0)))
            failures.Add("live-support-capability-receipt-stale-or-future");
        if (!IsSha256(receipt.ReceiptDigest)
            || !string.Equals(receipt.ReceiptDigest, DigestCapabilityReceipt(receipt), StringComparison.Ordinal))
            failures.Add("live-support-capability-receipt-digest-invalid");
        string expectedAccountScope = (_configuration[ExpectedAccountScopeDigestKey] ?? string.Empty).Trim();
        string expectedScenario = (_configuration[ExpectedScenarioDigestKey] ?? string.Empty).Trim();
        string expectedAvatarBinding = (_configuration[ExpectedAvatarBindingDigestKey] ?? string.Empty).Trim();
        if (!IsSha256(expectedAccountScope)
            || !FixedTimeDigestEquals(receipt.AccountScopeRefDigest, expectedAccountScope))
            failures.Add("live-support-capability-account-scope-authority-mismatch");
        if (!IsSha256(expectedScenario)
            || !FixedTimeDigestEquals(receipt.ScenarioRefDigest, expectedScenario))
            failures.Add("live-support-capability-scenario-authority-mismatch");
        if (_meetingBots is not IToughTongueLiveSupportAuthorityBinding meetingBotAuthority
            || !FixedTimeDigestEquals(
                receipt.ScenarioRefDigest,
                meetingBotAuthority.ScenarioRefDigest))
            failures.Add("live-support-meeting-bot-scenario-authority-mismatch");
        if (!IsSha256(expectedAvatarBinding)
            || !FixedTimeDigestEquals(receipt.AvatarBindingDigest, expectedAvatarBinding))
            failures.Add("live-support-capability-avatar-binding-authority-mismatch");

        byte[] authorityKey = ResolveCapabilityAuthorityKey(_configuration[CapabilityReceiptHmacKey]);
        if (authorityKey.Length != 32
            || !FixedTimeMacEquals(
                receipt.AuthorityMac,
                authorityKey.Length == 32
                    ? ComputeCapabilityReceiptAuthorityMac(receipt, authorityKey)
                    : string.Empty))
        {
            failures.Add("live-support-capability-authority-mac-invalid");
        }
        CryptographicOperations.ZeroMemory(authorityKey);
        return failures;
    }

    private static List<string> ValidateRequest(BuildGhostLiveSupportRequest request, DateTimeOffset now)
    {
        List<string> failures = [];
        if (!string.Equals(request.Schema, ToughTongueBuildGhostContractVersions.LiveSupportRequestV1, StringComparison.Ordinal))
            failures.Add("live-support-request-schema-invalid");
        if (!IsSafeIdentifier(request.RequestId)) failures.Add("live-support-request-id-invalid");
        if (!IsSha256(request.OwnerScopeHash)) failures.Add("live-support-owner-scope-invalid");
        if (!IsSafeIdentifier(request.WorkspaceId)) failures.Add("live-support-workspace-id-invalid");
        if (request.WorkspaceRevision < 0) failures.Add("live-support-workspace-revision-invalid");
        if (!IsSha256(request.SourceDigest)) failures.Add("live-support-source-digest-invalid");
        if (!SafeLocale.IsMatch(request.Locale ?? string.Empty)) failures.Add("live-support-locale-invalid");
        if (!IsMeetingProvider(request.MeetingProvider)) failures.Add("live-support-meeting-provider-invalid");
        if (!request.RecordingConsentGranted) failures.Add("live-support-recording-consent-required");
        if (!request.ExternalProviderProcessingConsentGranted) failures.Add("live-support-provider-processing-consent-required");
        if (!string.Equals(
                request.DisclosureVersion,
                BuildGhostLiveSupportDisclosureContract.CurrentVersion,
                StringComparison.Ordinal))
            failures.Add("live-support-disclosure-version-invalid");
        if (!IsSha256(request.DisclosureDigest)
            || !FixedTimeDigestEquals(
                request.DisclosureDigest,
                BuildGhostLiveSupportDisclosureContract.ComputeDigest()))
            failures.Add("live-support-disclosure-digest-invalid");
        if (request.RequestedDurationMinutes is < 5 or > 60) failures.Add("live-support-duration-invalid");
        if (!IsSafeIdentifier(request.IdempotencyKey)) failures.Add("live-support-idempotency-key-invalid");
        if (request.RequestedAtUtc > now.AddMinutes(5) || now - request.RequestedAtUtc > TimeSpan.FromMinutes(15))
            failures.Add("live-support-request-stale-or-future");
        return failures;
    }

    private static IReadOnlyList<string> ValidateMeeting(
        BuildGhostMeetingLinkProvisioningResult meeting,
        string expectedProvider,
        DateTimeOffset now)
    {
        List<string> failures = [];
        if (!meeting.Success) failures.Add(NormalizeOutcome(meeting.OutcomeCode, "meeting-link-provisioning-failed"));
        if (!string.Equals(meeting.MeetingProvider, expectedProvider, StringComparison.Ordinal))
            failures.Add("meeting-link-provider-mismatch");
        if (meeting.JoinUrl is null || !IsAllowedJoinUrl(meeting.JoinUrl, expectedProvider))
            failures.Add("meeting-link-url-invalid");
        if (!IsSafeIdentifier(meeting.CancellationHandle)) failures.Add("meeting-link-cancellation-handle-invalid");
        if (!IsSha256(meeting.ProviderMeetingRefDigest)) failures.Add("meeting-link-provider-ref-digest-invalid");
        if (!IsSha256(meeting.ProviderResponseDigest)) failures.Add("meeting-link-provider-response-digest-invalid");
        if (meeting.ExpiresAtUtc is null
            || meeting.ExpiresAtUtc <= now
            || meeting.ExpiresAtUtc > now.AddHours(24))
            failures.Add("meeting-link-expiry-invalid");
        return failures.Distinct(StringComparer.Ordinal).ToArray();
    }

    private static IReadOnlyList<string> ValidateBot(BuildGhostToughTongueMeetingBotResult bot)
    {
        List<string> failures = [];
        if (!bot.Success) failures.Add(NormalizeOutcome(bot.OutcomeCode, "tough-tongue-meeting-bot-provisioning-failed"));
        if (!IsSha256(bot.BotRefDigest)) failures.Add("tough-tongue-meeting-bot-ref-digest-invalid");
        if (!IsSha256(bot.SessionRefDigest)) failures.Add("tough-tongue-meeting-session-ref-digest-invalid");
        if (!IsSha256(bot.ProviderResponseDigest)) failures.Add("tough-tongue-meeting-response-digest-invalid");
        return failures.Distinct(StringComparer.Ordinal).ToArray();
    }

    private async Task TryCompensateMeetingAsync(
        BuildGhostLiveSupportRequest request,
        BuildGhostMeetingLinkProvisioningResult meeting,
        List<string> failures)
    {
        using CancellationTokenSource cleanup = new(TimeSpan.FromSeconds(10));
        try
        {
            BuildGhostMeetingLinkCancellationResult cancellation = await _meetingLinks.CancelAsync(
                new BuildGhostMeetingLinkCancellationCommand(
                    request.RequestId,
                    request.MeetingProvider,
                    meeting.CancellationHandle,
                    request.IdempotencyKey),
                cleanup.Token).ConfigureAwait(false);
            if (!cancellation.Success || !IsSha256(cancellation.ProviderResponseDigest))
            {
                failures.Add("meeting-link-compensation-unverified");
            }
        }
        catch
        {
            failures.Add("meeting-link-compensation-unverified");
        }
    }

    private static bool IsAllowedJoinUrl(Uri uri, string provider)
    {
        if (!uri.IsAbsoluteUri
            || !string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            || !string.IsNullOrEmpty(uri.UserInfo)
            || !string.IsNullOrEmpty(uri.Fragment)
            || !uri.IsDefaultPort)
        {
            return false;
        }

        string host = uri.IdnHost.TrimEnd('.').ToLowerInvariant();
        if (provider == BuildGhostLiveMeetingProviders.Zoom)
        {
            return host == "zoom.us" || host.EndsWith(".zoom.us", StringComparison.Ordinal);
        }

        return provider == BuildGhostLiveMeetingProviders.Teams
            && (host == "teams.microsoft.com" || host == "teams.live.com")
            && (uri.AbsolutePath.StartsWith("/l/meetup-join/", StringComparison.OrdinalIgnoreCase)
                || uri.AbsolutePath.StartsWith("/meet/", StringComparison.OrdinalIgnoreCase));
    }

    private BuildGhostLiveSupportSessionProjection Failed(
        BuildGhostLiveSupportRequest request,
        DateTimeOffset now,
        BuildGhostDefaultSupportProjection fallback,
        IEnumerable<string> reasons)
    {
        string[] normalized = reasons
            .Where(static reason => !string.IsNullOrWhiteSpace(reason))
            .Select(static reason => NormalizeOutcome(reason, "live-support-unavailable"))
            .Distinct(StringComparer.Ordinal)
            .OrderBy(static reason => reason, StringComparer.Ordinal)
            .ToArray();
        return new BuildGhostLiveSupportSessionProjection(
            ToughTongueBuildGhostContractVersions.LiveSupportSessionV1,
            request.RequestId,
            BuildGhostSupportChannelKinds.LivePhotorealMeeting,
            BuildGhostLiveSupportStatuses.Unavailable,
            request.MeetingProvider,
            null,
            null,
            string.Empty,
            "unavailable",
            request.RecordingConsentGranted,
            request.ExternalProviderProcessingConsentGranted,
            request.DisclosureVersion,
            request.DisclosureDigest,
            string.Empty,
            string.Empty,
            string.Empty,
            string.Empty,
            request.RequestedAtUtc,
            now,
            fallback,
            normalized.Length == 0 ? ["live-support-unavailable"] : normalized);
    }

    private static BuildGhostLiveSupportSessionProjection Provisioning(
        BuildGhostLiveSupportRequest request,
        string status,
        string capabilityReceiptDigest,
        string meetingReceiptDigest,
        BuildGhostDefaultSupportProjection fallback,
        IReadOnlyList<string> blockers)
        => new(
            ToughTongueBuildGhostContractVersions.LiveSupportSessionV1,
            request.RequestId,
            BuildGhostSupportChannelKinds.LivePhotorealMeeting,
            status,
            request.MeetingProvider,
            null,
            null,
            string.Empty,
            "photorealistic-provider-managed",
            request.RecordingConsentGranted,
            request.ExternalProviderProcessingConsentGranted,
            request.DisclosureVersion,
            request.DisclosureDigest,
            string.Empty,
            meetingReceiptDigest,
            string.Empty,
            capabilityReceiptDigest,
            request.RequestedAtUtc,
            request.RequestedAtUtc,
            fallback,
            blockers);

    private async Task<BuildGhostLiveSupportSessionProjection> PersistFailureAsync(
        BuildGhostLiveSupportRequest request,
        string requestFingerprint,
        BuildGhostLiveSupportSessionProjection projection,
        CancellationToken cancellationToken)
    {
        await PersistAsync(request, requestFingerprint, projection, cancellationToken).ConfigureAwait(false);
        return projection;
    }

    private Task<bool> PersistAsync(
        BuildGhostLiveSupportRequest request,
        string requestFingerprint,
        BuildGhostLiveSupportSessionProjection projection,
        CancellationToken cancellationToken)
        => _sessionStore.WriteAsync(
            new StoredBuildGhostLiveSupportSession(
                EncryptedFileBuildGhostLiveSupportSessionStore.StoredSchema,
                request.OwnerScopeHash,
                request.WorkspaceId,
                request.SourceDigest,
                requestFingerprint,
                projection),
            cancellationToken);

    private bool RemoteExecutionEnabled()
        => bool.TryParse(_configuration[RemoteExecutionEnabledKey], out bool enabled) && enabled;

    private IReadOnlyList<string> DependencyBlockers()
    {
        List<string> blockers = [];
        if (_meetingLinks is IBuildGhostLiveSupportDependencyReadiness meetingReadiness)
        {
            blockers.AddRange(meetingReadiness.BlockingReasons);
        }
        else
        {
            blockers.Add("meeting-link-broker-readiness-unverified");
        }

        if (_meetingBots is IBuildGhostLiveSupportDependencyReadiness botReadiness)
        {
            blockers.AddRange(botReadiness.BlockingReasons);
        }
        else
        {
            blockers.Add("tough-tongue-meeting-bot-readiness-unverified");
        }

        blockers.AddRange(_sessionStore.BlockingReasons);

        return blockers
            .Where(static blocker => !string.IsNullOrWhiteSpace(blocker))
            .Distinct(StringComparer.Ordinal)
            .OrderBy(static blocker => blocker, StringComparer.Ordinal)
            .ToArray();
    }

    private static bool IsMeetingProvider(string? provider)
        => string.Equals(provider, BuildGhostLiveMeetingProviders.Zoom, StringComparison.Ordinal)
            || string.Equals(provider, BuildGhostLiveMeetingProviders.Teams, StringComparison.Ordinal);

    private static bool IsSafeSameOriginMediaHref(string? href)
        => href is { Length: > 1 and <= 512 }
            && href[0] == '/'
            && href[1] != '/'
            && !href.Contains('\\')
            && !href.Contains('?')
            && !href.Contains('#')
            && !href.Contains("%2f", StringComparison.OrdinalIgnoreCase)
            && !href.Contains("%5c", StringComparison.OrdinalIgnoreCase)
            && href.EndsWith(".mp4", StringComparison.OrdinalIgnoreCase);

    private static bool IsSafeIdentifier(string? value)
        => !string.IsNullOrWhiteSpace(value) && SafeIdentifier.IsMatch(value);

    private static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).IndexOfAnyExcept("0123456789abcdef") < 0;

    private static byte[] ResolveCapabilityAuthorityKey(string? configured)
    {
        try
        {
            byte[] decoded = Convert.FromBase64String(configured?.Trim() ?? string.Empty);
            if (decoded.Length == 32)
            {
                return decoded;
            }
            CryptographicOperations.ZeroMemory(decoded);
        }
        catch (FormatException)
        {
        }
        return [];
    }

    private static bool FixedTimeDigestEquals(string? left, string? right)
    {
        if (!IsSha256(left) || !IsSha256(right))
        {
            return false;
        }

        return CryptographicOperations.FixedTimeEquals(
            Encoding.ASCII.GetBytes(left!),
            Encoding.ASCII.GetBytes(right!));
    }

    private static string RequestFingerprint(BuildGhostLiveSupportRequest request)
        => DigestText(string.Join(
            '\n',
            request.Schema,
            request.RequestId,
            request.OwnerScopeHash,
            request.WorkspaceId,
            request.WorkspaceRevision.ToString(System.Globalization.CultureInfo.InvariantCulture),
            request.SourceDigest,
            request.Locale,
            request.MeetingProvider,
            request.RecordingConsentGranted ? "recording-consent:yes" : "recording-consent:no",
            request.ExternalProviderProcessingConsentGranted ? "external-processing-consent:yes" : "external-processing-consent:no",
            request.DisclosureVersion,
            request.DisclosureDigest,
            request.RequestedDurationMinutes.ToString(System.Globalization.CultureInfo.InvariantCulture),
            request.IdempotencyKey));

    private static bool FixedTimeMacEquals(string? left, string? right)
    {
        if (left is not { Length: 76 }
            || right is not { Length: 76 }
            || !left.StartsWith("hmac-sha256:", StringComparison.Ordinal)
            || !right.StartsWith("hmac-sha256:", StringComparison.Ordinal))
        {
            return false;
        }

        return CryptographicOperations.FixedTimeEquals(
            Encoding.ASCII.GetBytes(left),
            Encoding.ASCII.GetBytes(right));
    }

    private static string DigestMeetingReceipt(BuildGhostMeetingLinkProvisioningResult meeting)
        => DigestText(string.Join(
            '\n',
            meeting.MeetingProvider,
            meeting.ProviderMeetingRefDigest,
            meeting.ProviderResponseDigest,
            meeting.StartsAtUtc?.ToUniversalTime().ToString("O") ?? string.Empty,
            meeting.ExpiresAtUtc?.ToUniversalTime().ToString("O") ?? string.Empty));

    private static string DigestBotReceipt(BuildGhostToughTongueMeetingBotResult bot)
        => DigestText(string.Join(
            '\n',
            bot.BotRefDigest,
            bot.SessionRefDigest,
            bot.ProviderResponseDigest));

    private static string DigestText(string value)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()}";

    private static string NormalizeOutcome(string? value, string fallback)
    {
        string normalized = string.IsNullOrWhiteSpace(value)
            ? fallback
            : new string(value.Trim().ToLowerInvariant()
                .Select(static character => char.IsAsciiLetterOrDigit(character) || character == '-' ? character : '-')
                .Take(96)
                .ToArray()).Trim('-');
        return string.IsNullOrEmpty(normalized) ? fallback : normalized;
    }
}
