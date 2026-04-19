using Chummer.Campaign.Contracts;
using Microsoft.Extensions.Configuration;
using System.Text.Json;

namespace Chummer.Run.Api.Services.Community;

public sealed record WorkspaceLifecyclePolicyOptions
{
    public TimeSpan RestoreSummaryRetention { get; init; } = TimeSpan.FromDays(30);

    public static WorkspaceLifecyclePolicyOptions FromConfiguration(IConfiguration configuration)
    {
        string? rawRetentionDays = configuration["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"];
        if (int.TryParse(rawRetentionDays, out int parsedDays) && parsedDays > 0)
        {
            return new WorkspaceLifecyclePolicyOptions
            {
                RestoreSummaryRetention = TimeSpan.FromDays(parsedDays)
            };
        }

        return new WorkspaceLifecyclePolicyOptions();
    }
}

public sealed record WorkspaceLifecycleCleanupResult(
    int PrunedRestoreSummaries,
    int PrunedOrphanRestoreSummaries)
{
    public bool Changed => PrunedRestoreSummaries > 0 || PrunedOrphanRestoreSummaries > 0;
}

public sealed class WorkspaceLifecyclePolicyService
{
    private static readonly JsonSerializerOptions ComparisonJsonOptions = new(JsonSerializerDefaults.Web);
    private readonly WorkspaceLifecyclePolicyOptions _options;

    public WorkspaceLifecyclePolicyService(IConfiguration configuration)
    {
        _options = WorkspaceLifecyclePolicyOptions.FromConfiguration(configuration);
    }

    public WorkspaceLifecyclePolicyOptions Options => _options;

    public WorkspaceLifecycleCleanupResult ApplyLocked(CommunityStore store, DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(store);

        int prunedExpired = 0;
        int prunedOrphaned = 0;
        DateTimeOffset restoreCutoff = now - _options.RestoreSummaryRetention;
        string[] restoreKeys = store.RestoreByUserId.Keys.ToArray();
        foreach (string userId in restoreKeys)
        {
            if (!store.RestoreByUserId.TryGetValue(userId, out WorkspaceRestoreProjection? restore))
            {
                continue;
            }

            if (!store.UsersById.ContainsKey(userId))
            {
                store.RestoreByUserId.Remove(userId);
                prunedOrphaned++;
                continue;
            }

            if (restore.GeneratedAtUtc < restoreCutoff)
            {
                store.RestoreByUserId.Remove(userId);
                prunedExpired++;
            }
        }

        return new WorkspaceLifecycleCleanupResult(prunedExpired, prunedOrphaned);
    }

    public WorkspaceRestoreProjection FinalizeRestoreProjection(
        WorkspaceRestoreProjection? existing,
        WorkspaceRestoreProjection candidate,
        DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(candidate);

        if (existing is null)
        {
            return candidate with { GeneratedAtUtc = now };
        }

        WorkspaceRestoreProjection stableCandidate = candidate with
        {
            GeneratedAtUtc = existing.GeneratedAtUtc,
            ProvenanceReceipts = NormalizeReceiptObservations(candidate.ProvenanceReceipts, existing.ProvenanceReceipts),
            ConflictReceipts = NormalizeConflictObservations(candidate.ConflictReceipts, existing.ConflictReceipts)
        };
        return ContentEquals(existing, stableCandidate)
            ? existing
            : stableCandidate with { GeneratedAtUtc = now };
    }

    private static IReadOnlyList<WorkspaceRestoreProvenanceReceipt>? NormalizeReceiptObservations(
        IReadOnlyList<WorkspaceRestoreProvenanceReceipt>? candidate,
        IReadOnlyList<WorkspaceRestoreProvenanceReceipt>? existing)
    {
        if (candidate is null)
        {
            return null;
        }

        Dictionary<string, DateTimeOffset> existingObservedById = BuildProvenanceObservationMap(existing);

        return candidate
            .Select(item => TryResolveExistingObservation(existingObservedById, ResolveProvenanceReceiptObservationKeys(item), out DateTimeOffset observedAtUtc)
                ? item with { ObservedAtUtc = observedAtUtc }
                : item)
            .ToArray();
    }

    private static IReadOnlyList<WorkspaceRestoreConflictReceipt>? NormalizeConflictObservations(
        IReadOnlyList<WorkspaceRestoreConflictReceipt>? candidate,
        IReadOnlyList<WorkspaceRestoreConflictReceipt>? existing)
    {
        if (candidate is null)
        {
            return null;
        }

        Dictionary<string, DateTimeOffset> existingObservedById = BuildConflictObservationMap(existing);

        return candidate
            .Select(item => TryResolveExistingObservation(existingObservedById, ResolveConflictReceiptObservationKeys(item), out DateTimeOffset observedAtUtc)
                ? item with { ObservedAtUtc = observedAtUtc }
                : item)
            .ToArray();
    }

    private static Dictionary<string, DateTimeOffset> BuildProvenanceObservationMap(
        IReadOnlyList<WorkspaceRestoreProvenanceReceipt>? existing)
    {
        Dictionary<string, DateTimeOffset> observedByKey = new(StringComparer.OrdinalIgnoreCase);
        foreach (WorkspaceRestoreProvenanceReceipt receipt in existing ?? Array.Empty<WorkspaceRestoreProvenanceReceipt>())
        {
            AddObservationKeys(observedByKey, ResolveProvenanceReceiptObservationKeys(receipt), receipt.ObservedAtUtc);
        }

        return observedByKey;
    }

    private static Dictionary<string, DateTimeOffset> BuildConflictObservationMap(
        IReadOnlyList<WorkspaceRestoreConflictReceipt>? existing)
    {
        Dictionary<string, DateTimeOffset> observedByKey = new(StringComparer.OrdinalIgnoreCase);
        foreach (WorkspaceRestoreConflictReceipt receipt in existing ?? Array.Empty<WorkspaceRestoreConflictReceipt>())
        {
            AddObservationKeys(observedByKey, ResolveConflictReceiptObservationKeys(receipt), receipt.ObservedAtUtc);
        }

        return observedByKey;
    }

    private static void AddObservationKeys(
        Dictionary<string, DateTimeOffset> observedByKey,
        IEnumerable<string> keys,
        DateTimeOffset observedAtUtc)
    {
        foreach (string key in keys)
        {
            if (observedByKey.TryGetValue(key, out DateTimeOffset existingObservedAtUtc))
            {
                if (observedAtUtc < existingObservedAtUtc)
                {
                    observedByKey[key] = observedAtUtc;
                }

                continue;
            }

            observedByKey[key] = observedAtUtc;
        }
    }

    private static bool TryResolveExistingObservation(
        IReadOnlyDictionary<string, DateTimeOffset> observedByKey,
        IEnumerable<string> keys,
        out DateTimeOffset observedAtUtc)
    {
        foreach (string key in keys)
        {
            if (observedByKey.TryGetValue(key, out observedAtUtc))
            {
                return true;
            }
        }

        observedAtUtc = default;
        return false;
    }

    private static IEnumerable<string> ResolveProvenanceReceiptObservationKeys(WorkspaceRestoreProvenanceReceipt receipt)
        => ResolveReceiptObservationKeys(
            receipt.ReceiptId,
            receipt.Surface,
            receipt.Kind,
            receipt.SubjectId,
            workspaceDefaultKind: "workspace_restore_provenance",
            entitlementDefaultKind: "entitlement_restore_provenance",
            suffix: "provenance");

    private static IEnumerable<string> ResolveConflictReceiptObservationKeys(WorkspaceRestoreConflictReceipt receipt)
        => ResolveReceiptObservationKeys(
            receipt.ReceiptId,
            receipt.Surface,
            receipt.Kind,
            receipt.SubjectId,
            workspaceDefaultKind: "workspace_restore_conflict",
            entitlementDefaultKind: "entitlement_restore_conflict",
            suffix: "conflict");

    private static IEnumerable<string> ResolveReceiptObservationKeys(
        string? receiptId,
        string? surface,
        string? kind,
        string? subjectId,
        string workspaceDefaultKind,
        string entitlementDefaultKind,
        string suffix)
    {
        string? normalizedReceiptId = NormalizeOptional(receiptId);
        if (normalizedReceiptId is not null)
        {
            yield return $"id:{normalizedReceiptId}";
        }

        string normalizedSurface = ResolveReceiptSurface(surface, kind);
        string normalizedKind = NormalizeReceiptToken(NormalizeOptional(kind)
            ?? (string.Equals(normalizedSurface, "entitlement_sync", StringComparison.Ordinal)
                ? entitlementDefaultKind
                : workspaceDefaultKind));
        string normalizedSubject = NormalizeReceiptToken(NormalizeOptional(subjectId) ?? "unknown restore subject");
        yield return $"{normalizedSurface}:{normalizedKind}:{normalizedSubject}:{suffix}";
    }

    private static string ResolveReceiptSurface(string? surface, string? kind)
    {
        string? normalizedSurface = NormalizeOptional(surface);
        if (normalizedSurface is not null)
        {
            return NormalizeReceiptToken(normalizedSurface);
        }

        string normalizedKind = NormalizeOptional(kind) ?? string.Empty;
        return normalizedKind.Contains("entitlement", StringComparison.OrdinalIgnoreCase)
            ? "entitlement_sync"
            : "workspace_restore";
    }

    private static string NormalizeReceiptToken(string value)
        => string.Join(
            "_",
            value.Trim()
                .ToLowerInvariant()
                .Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static bool ContentEquals<T>(T left, T right)
        => string.Equals(
            JsonSerializer.Serialize(left, ComparisonJsonOptions),
            JsonSerializer.Serialize(right, ComparisonJsonOptions),
            StringComparison.Ordinal);
}
