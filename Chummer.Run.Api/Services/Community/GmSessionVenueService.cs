using System.Security.Cryptography;
using System.Text;
using Chummer.Campaign.Contracts;
using Chummer.Contracts.Receipts;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed record GmSessionVenueSurfaceProjection(
    string CampaignId,
    string CampaignName,
    string SessionId,
    string SessionTitle,
    string VenueStatus,
    string Provider,
    string Mode,
    string Visibility,
    string ScheduledTimeSummary,
    string PrivacyStatus,
    string ConsentStatus,
    string AttendeeSyncStatus,
    string NonverbiaDebriefStatus,
    string NonverbiaPlayerSafeSummaryStatus,
    string? LatestRecapStatus,
    string? ProviderRoomUrl,
    string InvitePageUrl,
    string FallbackMessage,
    bool CanManage,
    bool ProviderCreateAvailable,
    string? ProviderCreateDisabledReason);

public sealed record NonverbiaDebriefRequest(
    bool ConsentToAnalyzeSessionDynamics,
    bool ConsentToGeneratePlayerSafeSummary,
    bool ReviewedForPlayerSafeProjection,
    string? ConsentScope,
    string? GmPrivateDebrief,
    string? PlayerSafeSummary);

public sealed record NonverbiaDebriefReceiptProjection(
    string ReceiptId,
    string VenueId,
    string SessionIdHash,
    string Provider,
    string DebriefStatus,
    string PlayerSafeSummaryStatus,
    string ConsentScope,
    string GmPrivateDebrief,
    string? PlayerSafeSummary,
    DateTimeOffset CreatedAtUtc);

public sealed record NonverbiaPlayerSafeSummaryProjection(
    string VenueId,
    string SessionIdHash,
    string Provider,
    string Summary,
    string ReviewStatus,
    DateTimeOffset CreatedAtUtc);

public sealed class GmSessionVenueService
{
    private readonly GmSessionVenueStore _store;
    private readonly BeHumanEventAdapterPostureService _beHumanPosture;
    private readonly IGmSessionVenueAdapter _adapter;
    private readonly IConfiguration _configuration;
    private readonly CommunityStore _communityStore;

    public GmSessionVenueService(
        GmSessionVenueStore store,
        BeHumanEventAdapterPostureService beHumanPosture,
        IGmSessionVenueAdapter adapter,
        IConfiguration configuration,
        CommunityStore communityStore)
    {
        _store = store;
        _beHumanPosture = beHumanPosture;
        _adapter = adapter;
        _configuration = configuration;
        _communityStore = communityStore;
    }

    public GmSessionVenueProjection GetVenue(string ownerAccountId, string campaignId, string sessionId)
    {
        EnsureCampaignAccess(ownerAccountId, campaignId, requireManage: false);

        lock (_store.Gate)
        {
            if (_store.VenuesBySessionKey.TryGetValue(GmSessionVenueStore.BuildSessionKey(ownerAccountId, campaignId, sessionId), out GmSessionVenueProjection? existing))
            {
                return existing;
            }
        }

        DateTimeOffset now = DateTimeOffset.UtcNow;
        return new GmSessionVenueProjection(
            VenueId: StableId("gm-session-venue", campaignId, sessionId),
            CampaignId: campaignId,
            SessionId: sessionId,
            OwnerAccountId: ownerAccountId,
            Provider: "none",
            Mode: "manual_link_mode",
            Visibility: "private_campaign",
            ProviderEventId: null,
            ProviderEventUrl: null,
            ProviderRoomUrl: null,
            VenueStatus: "not_configured",
            ScheduledStartUtc: now,
            ScheduledEndUtc: null,
            PrivacyStatus: "pending",
            ConsentStatus: "not_required",
            CreatedAtUtc: now,
            UpdatedAtUtc: now);
    }

    public VenueLinkReceiptProjection AddManualVenueLink(string ownerAccountId, string campaignId, string sessionId, ManualVenueLinkRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        EnsureCampaignAccess(ownerAccountId, campaignId, requireManage: true);

        ValidateProvider(request.Provider);
        string validatedUrl = _adapter.ValidateVenueUrlAsync(request.VenueUrl).GetAwaiter().GetResult();
        string visibility = NormalizeVisibility(request.Visibility);
        ValidateSchedule(request.ScheduledStartUtc, request.ScheduledEndUtc);
        if (request.ProviderDirectEmailInvites && !request.ConsentToShareAttendeeEmails)
        {
            throw new ArgumentException("provider_direct_email_invites require explicit consent to share attendee emails.", nameof(request));
        }

        DateTimeOffset now = DateTimeOffset.UtcNow;
        string privacyStatus = "pass";
        string consentStatus = request.ProviderDirectEmailInvites || request.ConsentToShareAttendeeEmails
            ? (request.ConsentToShareAttendeeEmails ? "complete" : "missing")
            : "not_required";

        lock (_store.Gate)
        {
            GmSessionVenueProjection current = GetVenue(ownerAccountId, campaignId, sessionId);
            GmSessionVenueProjection updated = current with
            {
                OwnerAccountId = ownerAccountId,
                Provider = "behuman",
                Mode = "manual_link_mode",
                Visibility = visibility,
                ProviderEventUrl = validatedUrl,
                ProviderRoomUrl = validatedUrl,
                VenueStatus = "manual_link_added",
                ScheduledStartUtc = request.ScheduledStartUtc ?? current.ScheduledStartUtc,
                ScheduledEndUtc = request.ScheduledEndUtc ?? current.ScheduledEndUtc,
                PrivacyStatus = privacyStatus,
                ConsentStatus = consentStatus,
                UpdatedAtUtc = now
            };
            _store.VenuesBySessionKey[GmSessionVenueStore.BuildSessionKey(ownerAccountId, campaignId, sessionId)] = updated;

            VenueLinkReceiptProjection receipt = new(
                ReceiptId: StableId("venue-link-receipt", updated.VenueId, now.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture)),
                VenueId: updated.VenueId,
                CampaignIdHash: HashId(campaignId),
                SessionIdHash: HashId(sessionId),
                Provider: "behuman",
                Mode: "manual_link_mode",
                LinkValidated: true,
                PrivacyStatus: privacyStatus,
                CreatedAtUtc: now,
                Envelope: BuildVenueReceiptEnvelope("venue_link", updated.VenueId, "manual_link_added"));
            _store.VenueLinkReceipts.Add(receipt);
            _store.PersistLocked();
            return receipt;
        }
    }

    public VenueCreatedReceiptProjection CreateBeHumanVenue(string ownerAccountId, string campaignId, string sessionId, CreateBeHumanVenueRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        EnsureCampaignAccess(ownerAccountId, campaignId, requireManage: true);
        ValidateSchedule(request.ScheduledStartUtc, request.ScheduledEndUtc);

        if (string.IsNullOrWhiteSpace(request.PublicSafeSessionTitle))
        {
            throw new ArgumentException("public_safe_session_title is required.", nameof(request));
        }

        BeHumanEventAdapterPosture posture = _beHumanPosture.Build();
        GmSessionVenueAdapterAvailability availability = _adapter.GetAvailability();
        if (!availability.CreateModeAvailable)
        {
            throw new InvalidOperationException(availability.FailureReason ?? "Create BeHuman venue is unavailable.");
        }

        GmSessionVenueAdapterCreateResult created = _adapter.CreateSessionVenueAsync(new GmSessionVenuePlan(
            CampaignId: campaignId,
            SessionId: sessionId,
            PublicSafeSessionTitle: request.PublicSafeSessionTitle.Trim(),
            ScheduledStartUtc: request.ScheduledStartUtc,
            ScheduledEndUtc: request.ScheduledEndUtc,
            Visibility: NormalizeVisibility(request.Visibility),
            RegistrationCapacity: request.RegistrationCapacity,
            ConsentToShareAttendeeEmails: request.ConsentToShareAttendeeEmails)).GetAwaiter().GetResult();

        DateTimeOffset now = DateTimeOffset.UtcNow;
        lock (_store.Gate)
        {
            GmSessionVenueProjection current = GetVenue(ownerAccountId, campaignId, sessionId);
            GmSessionVenueProjection updated = current with
            {
                OwnerAccountId = ownerAccountId,
                Provider = "behuman",
                Mode = "adapter_create_mode",
                Visibility = NormalizeVisibility(request.Visibility),
                ProviderEventId = created.ProviderEventId,
                ProviderEventUrl = created.ProviderEventUrl,
                ProviderRoomUrl = created.ProviderRoomUrl,
                VenueStatus = "provider_created",
                ScheduledStartUtc = request.ScheduledStartUtc,
                ScheduledEndUtc = request.ScheduledEndUtc,
                PrivacyStatus = created.PrivacyStatus,
                ConsentStatus = request.ConsentToShareAttendeeEmails ? "complete" : "not_required",
                UpdatedAtUtc = now
            };
            _store.VenuesBySessionKey[GmSessionVenueStore.BuildSessionKey(ownerAccountId, campaignId, sessionId)] = updated;

            VenueCreatedReceiptProjection receipt = new(
                ReceiptId: StableId("venue-created-receipt", updated.VenueId, now.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture)),
                VenueId: updated.VenueId,
                ProviderEventId: created.ProviderEventId,
                ProviderEventUrlHash: HashId(created.ProviderEventUrl),
                AdapterMode: "adapter_create_mode",
                Capacity: created.Capacity,
                PrivacyStatus: created.PrivacyStatus,
                CreatedAtUtc: now,
                Envelope: BuildVenueReceiptEnvelope("venue_created", updated.VenueId, "provider_created"));
            _store.VenueCreatedReceipts.Add(receipt);
            _store.PersistLocked();
            return receipt;
        }
    }

    public SessionVenueCloseoutReceiptProjection CloseVenue(string ownerAccountId, string campaignId, string sessionId, SessionVenueCloseoutRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        EnsureCampaignAccess(ownerAccountId, campaignId, requireManage: true);

        DateTimeOffset now = DateTimeOffset.UtcNow;
        lock (_store.Gate)
        {
            string sessionKey = GmSessionVenueStore.BuildSessionKey(ownerAccountId, campaignId, sessionId);
            if (!_store.VenuesBySessionKey.TryGetValue(sessionKey, out GmSessionVenueProjection? current))
            {
                throw new InvalidOperationException("Session venue is not configured yet.");
            }

            string attendanceStatus = "not_requested";
            int? attendeeCount = null;
            if (request.SyncAttendance)
            {
                if (!request.ConsentToImportAttendance)
                {
                    attendanceStatus = "missing";
                }
                else if (string.IsNullOrWhiteSpace(current.ProviderEventId))
                {
                    attendanceStatus = "unavailable";
                }
                else
                {
                    GmSessionVenueAttendanceSyncResult sync = _adapter.SyncAttendanceAsync(current.ProviderEventId).GetAwaiter().GetResult();
                    attendanceStatus = sync.AttendanceSyncStatus;
                    attendeeCount = sync.AttendeeCount;
                }
            }

            GmSessionVenueProjection updated = current with
            {
                VenueStatus = "closed",
                ConsentStatus = request.ConsentToImportAttendance ? "complete" : current.ConsentStatus,
                UpdatedAtUtc = now
            };
            _store.VenuesBySessionKey[sessionKey] = updated;

            SessionVenueCloseoutReceiptProjection receipt = new(
                ReceiptId: StableId("session-venue-closeout", updated.VenueId, now.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture)),
                VenueId: updated.VenueId,
                SessionIdHash: HashId(sessionId),
                AttendanceSyncStatus: attendanceStatus,
                AttendeeCount: attendeeCount,
                RecapStatus: NormalizeRecapStatus(request.RecapStatus),
                BlackLedgerImpactReceiptId: NormalizeOptional(request.LinkedBlackLedgerReceiptId),
                CreatedAtUtc: now,
                Envelope: BuildVenueReceiptEnvelope("venue_closeout", updated.VenueId, "closed"));
            _store.CloseoutReceipts.Add(receipt);
            _store.PersistLocked();
            return receipt;
        }
    }

    public NonverbiaDebriefReceiptProjection SubmitNonverbiaDebrief(string ownerAccountId, string campaignId, string sessionId, NonverbiaDebriefRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        EnsureCampaignAccess(ownerAccountId, campaignId, requireManage: true);
        GmSessionVenueProjection venue = GetVenue(ownerAccountId, campaignId, sessionId);
        EnsureNonverbiaEligibleVenue(venue);

        if (!request.ConsentToAnalyzeSessionDynamics)
        {
            throw new ArgumentException("nonverbia debrief requires explicit consent to analyze session dynamics.", nameof(request));
        }

        string gmPrivateDebrief = NormalizeOptional(request.GmPrivateDebrief)
            ?? throw new ArgumentException("gm_private_debrief is required.", nameof(request));
        string consentScope = NormalizeOptional(request.ConsentScope) ?? "gm_private_only";
        string? playerSafeSummary = NormalizeOptional(request.PlayerSafeSummary);
        string playerSafeSummaryStatus = "not_requested";
        if (playerSafeSummary is not null)
        {
            if (!request.ConsentToGeneratePlayerSafeSummary)
            {
                throw new ArgumentException("player_safe_summary requires consent to generate a player-safe summary.", nameof(request));
            }

            if (!request.ReviewedForPlayerSafeProjection)
            {
                throw new ArgumentException("player_safe_summary requires GM review before player-safe projection.", nameof(request));
            }

            playerSafeSummaryStatus = "reviewed_player_safe";
        }
        else if (request.ConsentToGeneratePlayerSafeSummary)
        {
            playerSafeSummaryStatus = request.ReviewedForPlayerSafeProjection ? "reviewed_empty" : "awaiting_review";
        }

        DateTimeOffset now = DateTimeOffset.UtcNow;
        NonverbiaDebriefReceiptProjection receipt = new(
            ReceiptId: StableId("nonverbia-debrief", venue.VenueId, now.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture)),
            VenueId: venue.VenueId,
            SessionIdHash: HashId(sessionId),
            Provider: "nonverbia",
            DebriefStatus: "gm_private_complete",
            PlayerSafeSummaryStatus: playerSafeSummaryStatus,
            ConsentScope: consentScope,
            GmPrivateDebrief: gmPrivateDebrief,
            PlayerSafeSummary: playerSafeSummary,
            CreatedAtUtc: now);

        lock (_store.Gate)
        {
            _store.NonverbiaDebriefReceipts.Add(receipt);
            _store.PersistLocked();
        }

        return receipt;
    }

    public NonverbiaDebriefReceiptProjection GetLatestNonverbiaDebrief(string ownerAccountId, string campaignId, string sessionId)
    {
        EnsureCampaignAccess(ownerAccountId, campaignId, requireManage: true);
        GmSessionVenueProjection venue = GetVenue(ownerAccountId, campaignId, sessionId);
        EnsureNonverbiaEligibleVenue(venue);

        lock (_store.Gate)
        {
            return _store.NonverbiaDebriefReceipts
                .Where(item => string.Equals(item.VenueId, venue.VenueId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(item => item.CreatedAtUtc)
                .FirstOrDefault()
                ?? throw new InvalidOperationException("No Nonverbia debrief receipt exists for this session venue yet.");
        }
    }

    public NonverbiaPlayerSafeSummaryProjection GetPlayerSafeNonverbiaSummary(string ownerAccountId, string campaignId, string sessionId)
    {
        EnsureCampaignAccess(ownerAccountId, campaignId, requireManage: false);
        GmSessionVenueProjection venue = GetVenue(ownerAccountId, campaignId, sessionId);
        EnsureNonverbiaEligibleVenue(venue);

        lock (_store.Gate)
        {
            NonverbiaDebriefReceiptProjection receipt = _store.NonverbiaDebriefReceipts
                .Where(item => string.Equals(item.VenueId, venue.VenueId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.PlayerSafeSummaryStatus, "reviewed_player_safe", StringComparison.OrdinalIgnoreCase)
                    && !string.IsNullOrWhiteSpace(item.PlayerSafeSummary))
                .OrderByDescending(item => item.CreatedAtUtc)
                .FirstOrDefault()
                ?? throw new InvalidOperationException("No reviewed player-safe Nonverbia summary exists for this session venue yet.");

            return new NonverbiaPlayerSafeSummaryProjection(
                VenueId: receipt.VenueId,
                SessionIdHash: receipt.SessionIdHash,
                Provider: receipt.Provider,
                Summary: receipt.PlayerSafeSummary!,
                ReviewStatus: receipt.PlayerSafeSummaryStatus,
                CreatedAtUtc: receipt.CreatedAtUtc);
        }
    }

    public GmSessionVenueSurfaceProjection DescribeVenue(string ownerAccountId, string campaignId, string sessionId, bool requireManage)
    {
        VenueAccessContext access = EnsureCampaignAccess(ownerAccountId, campaignId, requireManage);
        GmSessionVenueProjection venue = GetVenue(ownerAccountId, campaignId, sessionId);
        SessionVenueCloseoutReceiptProjection? closeout;
        NonverbiaDebriefReceiptProjection? debrief;
        BeHumanEventAdapterPosture posture = _beHumanPosture.Build();

        lock (_store.Gate)
        {
            closeout = _store.CloseoutReceipts
                .Where(item => string.Equals(item.VenueId, venue.VenueId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(item => item.CreatedAtUtc)
                .FirstOrDefault();
            debrief = _store.NonverbiaDebriefReceipts
                .Where(item => string.Equals(item.VenueId, venue.VenueId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(item => item.CreatedAtUtc)
                .FirstOrDefault();
        }

        string scheduledTimeSummary = venue.VenueStatus == "not_configured"
            ? "Not scheduled yet"
            : venue.ScheduledEndUtc is { } end
                ? $"{venue.ScheduledStartUtc:yyyy-MM-dd HH:mm} UTC to {end:yyyy-MM-dd HH:mm} UTC"
                : $"{venue.ScheduledStartUtc:yyyy-MM-dd HH:mm} UTC";
        GmSessionVenueAdapterAvailability availability = _adapter.GetAvailability();
        string fallbackMessage = availability.CreateModeAvailable
            ? "Manual room links remain valid if provider automation is unavailable."
            : "Live room integration unavailable. Paste your external room link manually or use another provider.";

        return new GmSessionVenueSurfaceProjection(
            CampaignId: campaignId,
            CampaignName: access.Campaign.Title,
            SessionId: sessionId,
            SessionTitle: $"Session {sessionId}",
            VenueStatus: venue.VenueStatus,
            Provider: venue.Provider,
            Mode: venue.Mode,
            Visibility: venue.Visibility,
            ScheduledTimeSummary: scheduledTimeSummary,
            PrivacyStatus: venue.PrivacyStatus,
            ConsentStatus: venue.ConsentStatus,
            AttendeeSyncStatus: closeout?.AttendanceSyncStatus ?? "not_requested",
            NonverbiaDebriefStatus: debrief?.DebriefStatus ?? "not_started",
            NonverbiaPlayerSafeSummaryStatus: debrief?.PlayerSafeSummaryStatus ?? "not_started",
            LatestRecapStatus: closeout?.RecapStatus,
            ProviderRoomUrl: venue.ProviderRoomUrl,
            InvitePageUrl: $"/account/campaigns/{campaignId}/sessions/{sessionId}/venue",
            FallbackMessage: fallbackMessage,
            CanManage: access.CanManage,
            ProviderCreateAvailable: availability.CreateModeAvailable,
            ProviderCreateDisabledReason: availability.FailureReason);
    }

    private static void EnsureNonverbiaEligibleVenue(GmSessionVenueProjection venue)
    {
        if (!string.Equals(venue.Provider, "behuman", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Nonverbia debrief is currently bounded to BeHuman-backed GM session venues.");
        }
    }

    private static void ValidateProvider(string? provider)
    {
        string normalized = NormalizeOptional(provider) ?? "behuman";
        if (!string.Equals(normalized, "behuman", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("manual venue mode currently accepts only the BeHuman provider boundary.", nameof(provider));
        }
    }

    private static void ValidateSchedule(DateTimeOffset? scheduledStartUtc, DateTimeOffset? scheduledEndUtc)
    {
        if (scheduledStartUtc is not null && scheduledEndUtc is not null && scheduledEndUtc < scheduledStartUtc)
        {
            throw new ArgumentException("scheduled_end_utc must be greater than or equal to scheduled_start_utc.");
        }
    }

    private static string NormalizeVisibility(string? visibility)
        => NormalizeOptional(visibility) switch
        {
            "registered_open_run" => "registered_open_run",
            "public_event" => "public_event",
            _ => "private_campaign"
        };

    private static string NormalizeRecapStatus(string? recapStatus)
        => NormalizeOptional(recapStatus) switch
        {
            "public_safe" => "public_safe",
            "not_created" => "not_created",
            _ => "private_only"
        };

    private static ReceiptEnvelope BuildVenueReceiptEnvelope(string receiptKind, string venueId, string reviewState)
        => ReceiptEnvelopeFactory.Runtime(
            receiptKind: receiptKind,
            ownerScope: "community.gm_session_venue",
            exposureClass: ReceiptExposureClasses.SignedIn,
            evidenceRef: venueId,
            reviewState: reviewState);

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private VenueAccessContext EnsureCampaignAccess(string ownerAccountId, string campaignId, bool requireManage)
    {
        string normalizedCampaignId = NormalizeOptional(campaignId)
            ?? throw new ArgumentException("campaignId is required.", nameof(campaignId));
        string normalizedOwnerUserId = NormalizeOptional(ownerAccountId)
            ?? throw new ArgumentException("ownerAccountId is required.", nameof(ownerAccountId));

        lock (_communityStore.Gate)
        {
            if (!_communityStore.CampaignsById.TryGetValue(normalizedCampaignId, out BoostCampaignDto? campaign))
            {
                throw new KeyNotFoundException($"Unknown campaign: {normalizedCampaignId}");
            }

            if (!_communityStore.GroupsById.TryGetValue(campaign.GroupId, out GroupDto? group))
            {
                throw new KeyNotFoundException($"Unknown group for campaign: {normalizedCampaignId}");
            }

            GroupMembershipDto? membership = group.Memberships.FirstOrDefault(member =>
                string.Equals(member.UserId, normalizedOwnerUserId, StringComparison.OrdinalIgnoreCase));
            if (membership is null)
            {
                throw new CommunityAccessDeniedException("Current account is not a member of this campaign group.");
            }

            bool canManage = CanManageVenue(membership.Role);
            if (requireManage && !canManage)
            {
                throw new CommunityAccessDeniedException("Current account must be an owner, organizer, admin, manager, or gm to manage this venue.");
            }

            return new VenueAccessContext(campaign, group, membership, canManage);
        }
    }

    private static bool CanManageVenue(string role)
        => role.Equals("owner", StringComparison.OrdinalIgnoreCase)
            || role.Equals("organizer", StringComparison.OrdinalIgnoreCase)
            || role.Equals("admin", StringComparison.OrdinalIgnoreCase)
            || role.Equals("manager", StringComparison.OrdinalIgnoreCase)
            || role.Equals("gm", StringComparison.OrdinalIgnoreCase);

    private sealed record VenueAccessContext(
        BoostCampaignDto Campaign,
        GroupDto Group,
        GroupMembershipDto Membership,
        bool CanManage);

    private static string StableId(string prefix, params string[] parts)
        => $"{prefix}-{string.Join('-', parts.Select(static part => part.Trim().Replace(' ', '-').ToLowerInvariant()))}";

    private static string HashId(string value)
    {
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes(value));
        return Convert.ToHexString(hash[..8]).ToLowerInvariant();
    }
}
