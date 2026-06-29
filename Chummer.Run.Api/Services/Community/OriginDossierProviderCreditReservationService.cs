using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class OriginDossierProviderCreditReservationService
{
    private const int DefaultMaxActiveReservationsPerUser = 5;
    private const string PremiumAuthoringCapability = "premium_authoring_credit";
    private static readonly IReadOnlySet<string> PremiumAuthoringProviderTokens = new HashSet<string>(
        ["first book", "firstbook", "my first book"],
        StringComparer.OrdinalIgnoreCase);

    private readonly OriginDossierProviderCreditReservationStore _store;
    private readonly HorizonArtifactQuotaService _quota;
    private readonly IConfiguration _configuration;

    public OriginDossierProviderCreditReservationService(
        OriginDossierProviderCreditReservationStore store,
        HorizonArtifactQuotaService quota,
        IConfiguration configuration)
    {
        _store = store;
        _quota = quota;
        _configuration = configuration;
    }

    public OriginDossierProviderCreditReservationResult Reserve(
        OriginDossierProviderCreditReservationRequest request,
        DateTimeOffset? now = null)
    {
        ArgumentNullException.ThrowIfNull(request);

        DateTimeOffset checkedAt = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();
        string userId = Clean(request.UserId);
        string projectId = Clean(request.ProjectId);
        string provider = Clean(request.Provider);
        string accountAlias = Clean(request.ProviderAccountAlias);
        List<string> blocked = ValidateRequest(request, userId, projectId, provider, accountAlias, checkedAt);

        if (blocked.Count > 0)
        {
            return BuildResult("blocked", false, null, userId, projectId, provider, accountAlias, 0, blocked, checkedAt, request.AuditOnly, providerBurnWouldBeAllowed: false);
        }

        string reservationId = BuildReservationId(userId, projectId, provider, accountAlias);
        lock (_store.Gate)
        {
            OriginDossierProviderCreditReservationLedgerEntry? existing = _store.Entries.FirstOrDefault(item =>
                string.Equals(item.ReservationId, reservationId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Status, "reserved", StringComparison.OrdinalIgnoreCase));
            if (existing is not null)
            {
                return request.AuditOnly
                    ? BuildResult("audit_passed", false, existing.ReservationId, userId, projectId, provider, accountAlias, existing.CreditsReserved, [], checkedAt, auditOnly: true, providerBurnWouldBeAllowed: true)
                    : BuildResult("reserved", true, existing.ReservationId, userId, projectId, provider, accountAlias, existing.CreditsReserved, [], checkedAt);
            }

            int activeReservations = _store.Entries.Count(item =>
                string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Status, "reserved", StringComparison.OrdinalIgnoreCase));
            if (activeReservations >= ResolveMaxActiveReservationsPerUser())
            {
                return BuildResult("blocked", false, null, userId, projectId, provider, accountAlias, 0, ["active provider credit reservation limit"], checkedAt, request.AuditOnly, providerBurnWouldBeAllowed: false);
            }

            if (request.AuditOnly)
            {
                return BuildResult("audit_passed", false, null, userId, projectId, provider, accountAlias, 0, [], checkedAt, auditOnly: true, providerBurnWouldBeAllowed: true);
            }

            _store.Entries.Add(new OriginDossierProviderCreditReservationLedgerEntry(
                reservationId,
                userId,
                projectId,
                provider,
                accountAlias,
                request.CreditsRequested,
                "reserved",
                checkedAt,
                checkedAt));
            _store.PersistLocked();
        }

        return BuildResult("reserved", true, reservationId, userId, projectId, provider, accountAlias, request.CreditsRequested, [], checkedAt);
    }

    private List<string> ValidateRequest(
        OriginDossierProviderCreditReservationRequest request,
        string userId,
        string projectId,
        string provider,
        string accountAlias,
        DateTimeOffset checkedAt)
    {
        List<string> blocked = [];
        AddIfMissing(blocked, !string.IsNullOrWhiteSpace(userId), "user id");
        AddIfMissing(blocked, !string.IsNullOrWhiteSpace(projectId), "project id");
        AddIfMissing(blocked, IsOriginBookKind(request.BookKind), "origin book kind");
        AddIfMissing(blocked, IsAllowedPrivacy(request.PrivacyClassification), "origin privacy classification");
        AddIfMissing(blocked, !string.IsNullOrWhiteSpace(provider), "assigned provider");
        AddIfMissing(blocked, !string.IsNullOrWhiteSpace(accountAlias), "assigned provider account alias");
        AddIfMissing(blocked, request.CreditsRequested > 0, "positive credit reservation");
        AddIfMissing(blocked, request.SourcePacketApproved, "approved source packet");
        AddIfMissing(blocked, request.ExternalProcessingConsent, "external processing consent");
        AddIfMissing(blocked, request.ChronologyValidated, "chronology validation");
        AddIfMissing(blocked, request.OutlineApproved, "outline approval");
        AddIfMissing(blocked, request.VoiceSampleApproved, "voice sample approval");
        AddIfMissing(blocked, request.CanonPreflightPassed, "canon preflight");
        AddIfMissing(blocked, request.HumanReviewAssigned, "human review assignment");
        AddIfMissing(blocked, AccountAliasAllowed(accountAlias), "configured provider account alias");

        if (IsPremiumAuthoringProvider(provider) && !string.IsNullOrWhiteSpace(userId) && request.CreditsRequested > 0)
        {
            HorizonArtifactQuotaSnapshot quota = _quota.GetQuota(
                new HorizonArtifactQuotaRequest(
                    UserId: userId,
                    HorizonId: "origin-dossier",
                    ArtifactKindOrCapabilityId: PremiumAuthoringCapability,
                    Email: request.Email,
                    UnitsRequested: request.CreditsRequested),
                checkedAt);
            AddIfMissing(blocked, quota.WindowRemaining >= request.CreditsRequested, "available premium authoring quota");
        }

        return blocked
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    private bool AccountAliasAllowed(string accountAlias)
    {
        IReadOnlyList<string> configured = ResolveAllowedAccountAliases();
        return configured.Count == 0
            ? !OriginDossierProviderAccountRegistry.HasConfiguredAliasSource(
                _configuration,
                "CHUMMER_ORIGIN_PROVIDER_ACCOUNT_ALIASES",
                "OriginDossier:ProviderAccountAliases")
            : configured.Any(alias => string.Equals(alias, accountAlias, StringComparison.OrdinalIgnoreCase));
    }

    private IReadOnlyList<string> ResolveAllowedAccountAliases()
        => OriginDossierProviderAccountRegistry.ResolveAllAliases(
            _configuration,
            "CHUMMER_ORIGIN_PROVIDER_ACCOUNT_ALIASES",
            "OriginDossier:ProviderAccountAliases");

    private int ResolveMaxActiveReservationsPerUser()
        => int.TryParse(
                _configuration["CHUMMER_ORIGIN_MAX_ACTIVE_PROVIDER_RESERVATIONS"]
                ?? _configuration["OriginDossier:MaxActiveProviderReservations"],
                out int configured)
            && configured > 0
            ? configured
            : DefaultMaxActiveReservationsPerUser;

    private static bool IsPremiumAuthoringProvider(string provider)
        => PremiumAuthoringProviderTokens.Any(token => provider.Contains(token, StringComparison.OrdinalIgnoreCase));

    private static bool IsOriginBookKind(string? value)
    {
        string text = Clean(value);
        return text.Equals("origin_dossier", StringComparison.OrdinalIgnoreCase)
            || text.Equals("narrative_origin", StringComparison.OrdinalIgnoreCase)
            || text.Equals("runner_memoir", StringComparison.OrdinalIgnoreCase)
            || text.Equals("intelligence_casefile", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsAllowedPrivacy(string? value)
    {
        string text = Clean(value);
        return text.Equals("runner_private", StringComparison.OrdinalIgnoreCase)
            || text.Equals("private", StringComparison.OrdinalIgnoreCase)
            || text.Equals("campaign_safe", StringComparison.OrdinalIgnoreCase)
            || text.Equals("public_safe", StringComparison.OrdinalIgnoreCase);
    }

    private static void AddIfMissing(List<string> blocked, bool condition, string requirement)
    {
        if (!condition)
        {
            blocked.Add(requirement);
        }
    }

    private static OriginDossierProviderCreditReservationResult BuildResult(
        string status,
        bool providerBurnAllowed,
        string? reservationId,
        string userId,
        string projectId,
        string provider,
        string accountAlias,
        int creditsReserved,
        IReadOnlyList<string> blocked,
        DateTimeOffset checkedAt,
        bool auditOnly = false,
        bool providerBurnWouldBeAllowed = false)
        => new(
            status,
            providerBurnAllowed,
            reservationId,
            string.IsNullOrWhiteSpace(userId) ? null : userId,
            string.IsNullOrWhiteSpace(projectId) ? null : projectId,
            string.IsNullOrWhiteSpace(provider) ? null : provider,
            string.IsNullOrWhiteSpace(accountAlias) ? null : accountAlias,
            creditsReserved,
            blocked,
            checkedAt,
            auditOnly,
            providerBurnWouldBeAllowed || providerBurnAllowed);

    private static string BuildReservationId(string userId, string projectId, string provider, string accountAlias)
    {
        string material = string.Join("\n", userId, projectId, provider, accountAlias);
        string digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(material))).ToLowerInvariant()[..16];
        return $"origin-provider-reservation-{digest}";
    }

    private static string Clean(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim();
}
