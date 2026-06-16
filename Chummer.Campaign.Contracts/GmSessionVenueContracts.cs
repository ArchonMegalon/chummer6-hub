using Chummer.Contracts.Receipts;

namespace Chummer.Campaign.Contracts;

public sealed record GmSessionVenueProjection(
    string VenueId,
    string CampaignId,
    string SessionId,
    string OwnerAccountId,
    string Provider,
    string Mode,
    string Visibility,
    string? ProviderEventId,
    string? ProviderEventUrl,
    string? ProviderRoomUrl,
    string VenueStatus,
    DateTimeOffset ScheduledStartUtc,
    DateTimeOffset? ScheduledEndUtc,
    string PrivacyStatus,
    string ConsentStatus,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record ManualVenueLinkRequest(
    string VenueUrl,
    string Provider = "behuman",
    string Visibility = "private_campaign",
    bool ProviderDirectEmailInvites = false,
    bool ConsentToShareAttendeeEmails = false,
    DateTimeOffset? ScheduledStartUtc = null,
    DateTimeOffset? ScheduledEndUtc = null);

public sealed record CreateBeHumanVenueRequest(
    string PublicSafeSessionTitle,
    DateTimeOffset ScheduledStartUtc,
    DateTimeOffset? ScheduledEndUtc = null,
    string Visibility = "private_campaign",
    int? RegistrationCapacity = null,
    bool ConsentToShareAttendeeEmails = false);

public sealed record SessionVenueCloseoutRequest(
    bool SyncAttendance = false,
    bool ConsentToImportAttendance = false,
    string RecapStatus = "private_only",
    string? LinkedBlackLedgerReceiptId = null);

public sealed record VenueLinkReceiptProjection(
    string ReceiptId,
    string VenueId,
    string CampaignIdHash,
    string SessionIdHash,
    string Provider,
    string Mode,
    bool LinkValidated,
    string PrivacyStatus,
    DateTimeOffset CreatedAtUtc,
    ReceiptEnvelope? Envelope = null);

public sealed record VenueCreatedReceiptProjection(
    string ReceiptId,
    string VenueId,
    string ProviderEventId,
    string ProviderEventUrlHash,
    string AdapterMode,
    int? Capacity,
    string PrivacyStatus,
    DateTimeOffset CreatedAtUtc,
    ReceiptEnvelope? Envelope = null);

public sealed record SessionVenueCloseoutReceiptProjection(
    string ReceiptId,
    string VenueId,
    string SessionIdHash,
    string AttendanceSyncStatus,
    int? AttendeeCount,
    string RecapStatus,
    string? BlackLedgerImpactReceiptId,
    DateTimeOffset CreatedAtUtc,
    ReceiptEnvelope? Envelope = null);
