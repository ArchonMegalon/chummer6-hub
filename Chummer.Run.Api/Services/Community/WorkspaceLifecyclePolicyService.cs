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
            : candidate with { GeneratedAtUtc = now };
    }

    private static IReadOnlyList<WorkspaceRestoreProvenanceReceipt>? NormalizeReceiptObservations(
        IReadOnlyList<WorkspaceRestoreProvenanceReceipt>? candidate,
        IReadOnlyList<WorkspaceRestoreProvenanceReceipt>? existing)
    {
        if (candidate is null)
        {
            return null;
        }

        Dictionary<string, DateTimeOffset> existingObservedById = (existing ?? Array.Empty<WorkspaceRestoreProvenanceReceipt>())
            .Where(static item => !string.IsNullOrWhiteSpace(item.ReceiptId))
            .GroupBy(static item => item.ReceiptId, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group.First().ObservedAtUtc,
                StringComparer.OrdinalIgnoreCase);

        return candidate
            .Select(item => existingObservedById.TryGetValue(item.ReceiptId, out DateTimeOffset observedAtUtc)
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

        Dictionary<string, DateTimeOffset> existingObservedById = (existing ?? Array.Empty<WorkspaceRestoreConflictReceipt>())
            .Where(static item => !string.IsNullOrWhiteSpace(item.ReceiptId))
            .GroupBy(static item => item.ReceiptId, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group.First().ObservedAtUtc,
                StringComparer.OrdinalIgnoreCase);

        return candidate
            .Select(item => existingObservedById.TryGetValue(item.ReceiptId, out DateTimeOffset observedAtUtc)
                ? item with { ObservedAtUtc = observedAtUtc }
                : item)
            .ToArray();
    }

    private static bool ContentEquals<T>(T left, T right)
        => string.Equals(
            JsonSerializer.Serialize(left, ComparisonJsonOptions),
            JsonSerializer.Serialize(right, ComparisonJsonOptions),
            StringComparison.Ordinal);
}
