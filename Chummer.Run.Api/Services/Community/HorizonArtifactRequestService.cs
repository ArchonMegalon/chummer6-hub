using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Chummer.Run.Api.Services.Community;

public sealed class HorizonArtifactRequestService
{
    private readonly HorizonCapabilityService _capabilities;
    private readonly HorizonArtifactQuotaService? _quota;
    private readonly HorizonArtifactRequestReceiptStore? _receipts;
    private readonly HorizonGovernedRenderRequestComposerService _governedRenderRequests;

    public HorizonArtifactRequestService(
        HorizonCapabilityService capabilities,
        HorizonArtifactQuotaService? quota = null,
        HorizonArtifactRequestReceiptStore? receipts = null,
        HorizonGovernedRenderRequestComposerService? governedRenderRequests = null)
    {
        _capabilities = capabilities;
        _quota = quota;
        _receipts = receipts;
        _governedRenderRequests = governedRenderRequests ?? new HorizonGovernedRenderRequestComposerService();
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
        HorizonGovernedRenderRequestContract? governedRenderRequest = null;
        if (request.GovernedRenderRequest is not null)
        {
            HorizonGovernedRenderRequestCompositionResult governedRender = _governedRenderRequests.Compose(
                capability,
                request.SourceRef,
                request.GovernedRenderRequest);
            if (governedRender.Accepted)
            {
                governedRenderRequest = governedRender.Contract;
            }
            else
            {
                blocked.AddRange(governedRender.BlockedReasons);
            }
        }

        HorizonArtifactQuotaSnapshot? quota = null;
        bool quotaTracked = capability.QuotaTracked;
        var preparedReceipt = new HorizonArtifactRequestReceipt(
            requestId, blocked.Count == 0 ? "accepted" : "blocked", capability.HorizonId,
            capability.CapabilityId, capability.ArtifactKind, capability.PublicLabel, capability.CapabilitySlot,
            Clean(request.SourceRef), Clean(request.UserId), Clean(request.Visibility), request.ExternalProcessingConsent,
            blocked.ToArray(), createdAtUtc, quotaTracked, GovernedRenderRequest: governedRenderRequest);
        HorizonArtifactQuotaRequest quotaRequest = new(
            UserId: request.UserId,
            HorizonId: capability.HorizonId,
            ArtifactKindOrCapabilityId: capability.CapabilityId,
            Email: request.Email);
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
                    if (FindReceipt(requestId) is not null)
                        throw new InvalidOperationException("This request already has a receipt; read it instead of resubmitting.");
                    quota = _quota.Consume(quotaRequest, createdAtUtc, preparedReceipt);
                    // The usage commit includes this exact receipt. No second
                    // write can fail after consuming the user's allowance.
                    return preparedReceipt with { Quota = quota };
                }
                catch (InvalidOperationException ex) when (ex.Message.Contains("allowance", StringComparison.OrdinalIgnoreCase))
                {
                    blocked.Add("artifact allowance");
                    quota = TryReadQuotaSnapshot(_quota, quotaRequest, createdAtUtc);
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
            Quota: quota,
            GovernedRenderRequest: governedRenderRequest);
        _receipts?.Append(receipt);
        return receipt;
    }

    public HorizonArtifactRequestReceipt AdmitPrivateOriginScene(HorizonArtifactRequestCreateRequest request)
    {
        // Called only after composing from current reader-accepted prose and
        // resolving a real Hub user. The charged receipt is the durable key;
        // this is not a new Hub-owned render queue or provider-spend ledger.
        if (request.HorizonId != "origin-dossier" || request.ArtifactKindOrCapabilityId != "origin-dossier-media"
            || request.Visibility != "private" || request.GovernedRenderRequest is not { } render
            || render.WorkItemId is not { Length: 64 } || request.SourceRef != "origin-dossier:scene:" + render.WorkItemId)
            throw new ArgumentException("An exact private Origin scene is required.");
        var capability = _capabilities.GetCapability(request.HorizonId, request.ArtifactKindOrCapabilityId);
        var composed = _governedRenderRequests.Compose(capability, request.SourceRef, render);
        if (Validate(request, capability, true, true).Count != 0 || !composed.Accepted)
            throw new InvalidOperationException("Private scene admission is unavailable or lacks consent.");

        HorizonArtifactRequestReceipt? Existing()
        {
            var rows = (_quota?.ListChargedRequests() ?? []).Where(row => row.CapabilityId == capability.CapabilityId
                && row.SourceRef == request.SourceRef && row.RequestedByUserId == request.UserId).ToArray();
            if (rows.Length == 0) return null;
            if (rows.Length != 1 || rows[0].Status != "accepted" || rows[0].Quota is null
                || JsonSerializer.Serialize(rows[0].GovernedRenderRequest) != JsonSerializer.Serialize(composed.Contract))
                throw new InvalidOperationException("Reopen the already-admitted scene; its exact request cannot be replaced.");
            return rows[0];
        }

        if (Existing() is { } previous) return previous;
        try
        {
            var admitted = BuildRequest(request, consumeQuota: true);
            if (admitted.Status != "accepted" || admitted.Quota is null)
                throw new InvalidOperationException("No scene allowance is available.");
            return admitted;
        }
        catch (Exception error) when (error is InvalidOperationException or Chummer.Storage.Teable.TeableRevisionConflictException)
        {
            // A concurrent caller may have committed the one allowance first.
            // Return only the identical admitted request; never blind reconsume.
            if (Existing() is { } concurrent) return concurrent;
            throw;
        }
    }

    public IReadOnlyList<HorizonArtifactRequestReceipt> ListRecentReceipts(
        string? horizonId = null,
        string? userId = null,
        string? artifactKindOrCapabilityId = null,
        int limit = 50)
    {
        var charged = (_quota?.ListChargedRequests() ?? [])
            .Where(row => string.IsNullOrWhiteSpace(horizonId) || string.Equals(row.HorizonId, Clean(horizonId), StringComparison.OrdinalIgnoreCase))
            .Where(row => string.IsNullOrWhiteSpace(userId) || string.Equals(row.RequestedByUserId, Clean(userId), StringComparison.OrdinalIgnoreCase))
            .Where(row => string.IsNullOrWhiteSpace(artifactKindOrCapabilityId)
                || string.Equals(row.ArtifactKind, Clean(artifactKindOrCapabilityId), StringComparison.OrdinalIgnoreCase)
                || string.Equals(row.CapabilityId, Clean(artifactKindOrCapabilityId), StringComparison.OrdinalIgnoreCase));
        return HorizonQuotaReceipts.Merge(charged, _receipts?.ListRecent(horizonId, userId, artifactKindOrCapabilityId, limit) ?? [])
            .OrderByDescending(row => row.CreatedAtUtc)
            .ThenBy(row => row.RequestId, StringComparer.OrdinalIgnoreCase)
            .Take(Math.Clamp(limit, 1, 200)).ToArray();
    }

    public HorizonArtifactRequestReceipt? FindReceipt(string requestId)
    {
        if (string.IsNullOrWhiteSpace(requestId)) return null;
        var charged = (_quota?.ListChargedRequests() ?? [])
            .Where(row => string.Equals(row.RequestId, requestId.Trim(), StringComparison.OrdinalIgnoreCase));
        var legacy = _receipts?.FindByRequestId(requestId);
        return HorizonQuotaReceipts.Merge(charged, legacy is null ? [] : [legacy]).SingleOrDefault();
    }

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

    private static HorizonArtifactQuotaSnapshot? TryReadQuotaSnapshot(
        HorizonArtifactQuotaService quota,
        HorizonArtifactQuotaRequest request,
        DateTimeOffset createdAtUtc)
    {
        try
        {
            return quota.GetQuota(request, createdAtUtc);
        }
        catch (InvalidOperationException)
        {
            return null;
        }
    }

    private static string BuildRequestId(
        HorizonArtifactRequestCreateRequest request,
        HorizonCapabilityDefinition capability,
        DateTimeOffset createdAtUtc)
        => BuildRequestId(capability.HorizonId, capability.CapabilityId, Clean(request.UserId), Clean(request.SourceRef), createdAtUtc);

    internal static string BuildRequestId(string horizonId, string capabilityId, string userId, string sourceRef, DateTimeOffset createdAtUtc)
    {
        string material = string.Join(
            "\n",
            horizonId,
            capabilityId,
            userId,
            sourceRef,
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
    string? Email = null,
    HorizonGovernedRenderRequestCreateRequest? GovernedRenderRequest = null);

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
    HorizonArtifactQuotaSnapshot? Quota = null,
    HorizonGovernedRenderRequestContract? GovernedRenderRequest = null);
