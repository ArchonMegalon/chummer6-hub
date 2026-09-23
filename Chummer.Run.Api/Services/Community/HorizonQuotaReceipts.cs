namespace Chummer.Run.Api.Services.Community;

// A charge and its user-visible request receipt share the usage-store commit.
// This is Hub allowance custody, never provider-dispatch or execution authority.
internal static class HorizonQuotaReceipts
{
    internal static void Validate(IReadOnlyList<HorizonArtifactRequestReceipt>? receipts,
        string userId, DateTimeOffset start, DateTimeOffset end, int used, string windowKind,
        HashSet<string> ids, string? horizonId = null, string? capabilityId = null, string? artifactKind = null)
    {
        if (receipts is null) return; // Legacy rows have no historical request attribution.
        HorizonArtifactRequestReceiptStore.ValidatePrimary(receipts);
        var counts = new HashSet<int>();
        foreach (var receipt in receipts)
        {
            if (!ids.Add(receipt.RequestId) || receipt.Status != "accepted" || !receipt.QuotaTracked
                || !string.Equals(receipt.RequestedByUserId, userId, StringComparison.OrdinalIgnoreCase)
                || receipt.CreatedAtUtc < start || receipt.CreatedAtUtc >= end
                || receipt.Quota is not { } quota || quota.WindowStartUtc != start || quota.WindowEndUtc != end
                || quota.WindowKind != windowKind || quota.WindowUsed <= 0 || quota.WindowUsed > used
                || quota.WindowUsed > quota.WindowLimit || !counts.Add(quota.WindowUsed)
                || (horizonId is not null && receipt.HorizonId != horizonId)
                || (capabilityId is not null && receipt.CapabilityId != capabilityId)
                || (artifactKind is not null && receipt.ArtifactKind != artifactKind))
                throw new InvalidDataException("Charged request receipt is not bound to its usage row.");
        }
        if (receipts.Count > used) throw new InvalidDataException("Charged request count exceeds usage.");
    }

    internal static IReadOnlyList<HorizonArtifactRequestReceipt> Append(
        IReadOnlyList<HorizonArtifactRequestReceipt>? existing, HorizonArtifactRequestReceipt receipt)
        => [.. existing ?? [], receipt];

    internal static void RejectDuplicate(IEnumerable<HorizonArtifactRequestReceipt> receipts, string requestId)
    {
        if (receipts.Any(row => string.Equals(row.RequestId, requestId, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException("This request was already recorded; read its receipt instead of charging again.");
    }

    internal static HorizonArtifactRequestReceipt[] Merge(IEnumerable<HorizonArtifactRequestReceipt> left,
        IEnumerable<HorizonArtifactRequestReceipt> right)
    {
        var rows = left.Concat(right).ToArray();
        if (rows.Select(row => row.RequestId).Distinct(StringComparer.OrdinalIgnoreCase).Count() != rows.Length)
            throw new InvalidDataException("Request receipt identity is ambiguous across stores.");
        return rows;
    }
}
