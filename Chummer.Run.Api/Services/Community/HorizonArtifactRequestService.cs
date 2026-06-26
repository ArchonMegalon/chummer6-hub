using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Services.Community;

public sealed class HorizonArtifactRequestService
{
    private readonly HorizonCapabilityService _capabilities;
    private readonly HorizonArtifactQuotaService? _quota;
    private readonly HorizonArtifactRequestReceiptStore? _receipts;

    public HorizonArtifactRequestService(
        HorizonCapabilityService capabilities,
        HorizonArtifactQuotaService? quota = null,
        HorizonArtifactRequestReceiptStore? receipts = null)
    {
        _capabilities = capabilities;
        _quota = quota;
        _receipts = receipts;
    }

    public HorizonArtifactRequestReceipt BuildRequest(
        HorizonArtifactRequestCreateRequest request,
        DateTimeOffset? now = null,
        bool consumeQuota = false,
        bool requireEnabledCapability = true,
        bool requireRequestingUser = true)
    {
        ArgumentNullException.ThrowIfNull(request);

        DateTimeOffset createdAtUtc = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();
        HorizonCapabilityDefinition capability = _capabilities.GetCapability(request.HorizonId, request.ArtifactKindOrCapabilityId);
        string requestId = BuildRequestId(request, capability, createdAtUtc);
        List<string> blocked = [.. Validate(request, capability, requireEnabledCapability, requireRequestingUser)];
        HorizonArtifactQuotaSnapshot? quota = null;
        bool quotaTracked = capability.QuotaTracked;
        if (consumeQuota && quotaTracked && blocked.Count == 0)
        {
            if (_quota is null)
            {
                blocked.Add("quota enforcement");
            }
            else
            {
                try
                {
                    quota = _quota.Consume(
                        new HorizonArtifactQuotaRequest(
                            UserId: request.UserId,
                            HorizonId: capability.HorizonId,
                            ArtifactKindOrCapabilityId: capability.CapabilityId,
                            Email: request.Email),
                        createdAtUtc);
                }
                catch (InvalidOperationException ex) when (ex.Message.Contains("allowance", StringComparison.OrdinalIgnoreCase))
                {
                    blocked.Add("artifact allowance");
                }
            }
        }

        string status = blocked.Count == 0 ? "accepted" : "blocked";

        var receipt = new HorizonArtifactRequestReceipt(
            RequestId: requestId,
            Status: status,
            HorizonId: capability.HorizonId,
            CapabilityId: capability.CapabilityId,
            ArtifactKind: capability.ArtifactKind,
            PublicLabel: capability.PublicLabel,
            CapabilitySlot: capability.CapabilitySlot,
            SourceRef: Clean(request.SourceRef),
            RequestedByUserId: Clean(request.UserId),
            Visibility: Clean(request.Visibility),
            ExternalProcessingConsent: request.ExternalProcessingConsent,
            BlockedReasons: blocked,
            CreatedAtUtc: createdAtUtc,
            QuotaTracked: quotaTracked,
            Quota: quota);
        _receipts?.Append(receipt);
        return receipt;
    }

    public IReadOnlyList<HorizonArtifactRequestReceipt> ListRecentReceipts(
        string? horizonId = null,
        string? userId = null,
        int limit = 50)
        => _receipts?.ListRecent(horizonId, userId, limit) ?? Array.Empty<HorizonArtifactRequestReceipt>();

    public HorizonArtifactRequestReceipt? FindReceipt(string requestId)
        => _receipts?.FindByRequestId(requestId);

    public HorizonArtifactRequestReceipt? FindReceiptForUser(string requestId, string userId)
    {
        HorizonArtifactRequestReceipt? receipt = FindReceipt(requestId);
        string normalizedUserId = Clean(userId);
        return receipt is not null
            && !string.IsNullOrWhiteSpace(normalizedUserId)
            && string.Equals(receipt.RequestedByUserId, normalizedUserId, StringComparison.OrdinalIgnoreCase)
            ? receipt
            : null;
    }

    public HorizonArtifactRequestReceipt? FindAcceptedPublicSafeReceipt(string requestId)
    {
        HorizonArtifactRequestReceipt? receipt = FindReceipt(requestId);
        if (receipt is null
            || !string.Equals(receipt.Status, "accepted", StringComparison.OrdinalIgnoreCase)
            || !IsPublicSafeVisibility(receipt.Visibility))
        {
            return null;
        }

        try
        {
            HorizonCapabilityDefinition capability = _capabilities.GetCapability(receipt.HorizonId, receipt.CapabilityId);
            return IsPublicReceiptEligible(capability)
                ? receipt
                : null;
        }
        catch (KeyNotFoundException)
        {
            return null;
        }
    }

    private static IReadOnlyList<string> Validate(
        HorizonArtifactRequestCreateRequest request,
        HorizonCapabilityDefinition capability,
        bool requireEnabledCapability,
        bool requireRequestingUser)
    {
        List<string> blocked = [];
        if (requireEnabledCapability)
        {
            AddIfMissing(blocked, capability.Enabled, "capability enabled");
        }
        if (requireRequestingUser)
        {
            AddIfMissing(blocked, !string.IsNullOrWhiteSpace(request.UserId), "requesting user");
        }
        AddIfMissing(blocked, !string.IsNullOrWhiteSpace(request.SourceRef), "source reference");
        AddIfMissing(blocked, IsHorizonOwnedSourceRef(request.SourceRef, capability.HorizonId), "horizon source reference");
        AddIfMissing(blocked, IsAllowedVisibility(request.Visibility), "allowed visibility");
        AddIfMissing(blocked, request.ExternalProcessingConsent, "external processing consent");
        return blocked;
    }

    private static bool IsHorizonOwnedSourceRef(string? sourceRef, string horizonId)
    {
        string normalizedSourceRef = Clean(sourceRef);
        string normalizedHorizonId = Clean(horizonId);
        return !string.IsNullOrWhiteSpace(normalizedSourceRef)
            && !string.IsNullOrWhiteSpace(normalizedHorizonId)
            && normalizedSourceRef.StartsWith($"{normalizedHorizonId}:", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsAllowedVisibility(string? value)
    {
        string normalized = Clean(value);
        return normalized.Equals("private", StringComparison.OrdinalIgnoreCase)
            || normalized.Equals("campaign_safe", StringComparison.OrdinalIgnoreCase)
            || normalized.Equals("public_safe", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsPublicSafeVisibility(string? value)
        => Clean(value).Equals("public_safe", StringComparison.OrdinalIgnoreCase);

    private static bool IsPublicReceiptEligible(HorizonCapabilityDefinition capability)
        => capability.PublicVisible
            && !capability.RequiresAuthentication;

    private static void AddIfMissing(List<string> blocked, bool condition, string requirement)
    {
        if (!condition)
        {
            blocked.Add(requirement);
        }
    }

    private static string BuildRequestId(
        HorizonArtifactRequestCreateRequest request,
        HorizonCapabilityDefinition capability,
        DateTimeOffset createdAtUtc)
    {
        string material = string.Join(
            "\n",
            capability.HorizonId,
            capability.CapabilityId,
            Clean(request.UserId),
            Clean(request.SourceRef),
            createdAtUtc.ToUnixTimeMilliseconds().ToString(System.Globalization.CultureInfo.InvariantCulture));
        string digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(material))).ToLowerInvariant()[..16];
        return $"horizon-artifact-{digest}";
    }

    private static string Clean(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim();
}

public sealed record HorizonArtifactRequestCreateRequest(
    string HorizonId,
    string ArtifactKindOrCapabilityId,
    string UserId,
    string SourceRef,
    string Visibility,
    bool ExternalProcessingConsent,
    string? Email = null);

public sealed record HorizonArtifactRequestReceipt(
    string RequestId,
    string Status,
    string HorizonId,
    string CapabilityId,
    string ArtifactKind,
    string PublicLabel,
    string CapabilitySlot,
    string SourceRef,
    string RequestedByUserId,
    string Visibility,
    bool ExternalProcessingConsent,
    IReadOnlyList<string> BlockedReasons,
    DateTimeOffset CreatedAtUtc,
    bool QuotaTracked,
    HorizonArtifactQuotaSnapshot? Quota = null);
