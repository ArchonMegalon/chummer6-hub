using Chummer.Media.Contracts;
using Chummer.Run.Contracts.Media;
using Chummer.Run.AI.Services.Assets;
using System.Collections.Concurrent;
using System.Net;
using System.Text;

namespace Chummer.Run.AI.Services.Creative;

public interface IPortraitForgeService
{
    Task<PortraitForgeResult> ForgeAsync(PortraitForgeRequest request, CancellationToken cancellationToken = default);
    PortraitForgeResult? Get(string portraitDraftId);
    IReadOnlyList<PortraitForgeResult> ListForEntity(string entityId);
    Task<PortraitForgeResult?> ApproveAsync(string portraitDraftId, PortraitApprovalRequest request, CancellationToken cancellationToken = default);
}

public sealed class PortraitForgeService : IPortraitForgeService
{
    private readonly IAssetLifecycleService _assetLifecycle;
    private readonly IMediaRenderJobService _mediaRenderJobs;
    private readonly ConcurrentDictionary<string, HashSet<string>> _styleTokensByEntity = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, PortraitDraftState> _drafts = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, PortraitIdentityState> _identitiesByEntity = new(StringComparer.OrdinalIgnoreCase);
    private readonly object _sync = new();
    private static readonly string[] Variants = ["canonical", "undercover", "damaged", "dossier_headshot", "wanted_poster"];

    private sealed class PortraitVariantState
    {
        public required string Variant { get; init; }
        public required string JobId { get; init; }
        public required string PromptLineage { get; init; }
        public required string StyleToken { get; init; }
    }

    private sealed class PortraitDraftState
    {
        public required string PortraitDraftId { get; init; }
        public required string PortraitIdentityId { get; init; }
        public required string EntityId { get; init; }
        public required string Style { get; init; }
        public required string? Notes { get; init; }
        public required bool AllowUndercover { get; init; }
        public required string? RerollOfPortraitId { get; init; }
        public required string? RerollRootPortraitId { get; init; }
        public required int RerollDepth { get; init; }
        public required DateTimeOffset CreatedAtUtc { get; init; }
        public required TimeSpan CacheTtl { get; init; }
        public required double Confidence { get; init; }
        public required Dictionary<string, PortraitVariantState> Variants { get; init; }
        public required List<PortraitReviewRecord> ReviewHistory { get; init; }
        public string DraftState { get; set; } = "draft";
        public string? ApprovedVariant { get; set; }
        public string? ApprovedAssetId { get; set; }
    }

    private sealed class PortraitIdentityState
    {
        public required string PortraitIdentityId { get; init; }
        public required string EntityId { get; init; }
        public string? CanonicalPortraitId { get; set; }
        public string? CanonicalDraftId { get; set; }
        public string? CanonicalVariant { get; set; }
        public List<string> DraftIds { get; } = new();
        public List<PortraitReviewRecord> History { get; } = new();
    }

    public PortraitForgeService(IAssetLifecycleService assetLifecycle, IMediaRenderJobService mediaRenderJobs)
    {
        _assetLifecycle = assetLifecycle;
        _mediaRenderJobs = mediaRenderJobs;
    }

    public async Task<PortraitForgeResult> ForgeAsync(PortraitForgeRequest request, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(request.EntityId))
        {
            throw new ArgumentException("EntityId is required.");
        }

        if (string.IsNullOrWhiteSpace(request.Style))
        {
            throw new ArgumentException("Style is required.");
        }

        var entityId = request.EntityId.Trim();
        var style = request.Style.Trim();
        var notes = string.IsNullOrWhiteSpace(request.Notes) ? null : request.Notes.Trim();
        var styleTokens = _styleTokensByEntity.GetOrAdd(entityId, static _ => new HashSet<string>(StringComparer.OrdinalIgnoreCase));
        lock (styleTokens)
        {
            styleTokens.Add(style);
        }

        PortraitIdentityState identity;
        PortraitDraftState? rerollParent = null;
        lock (_sync)
        {
            identity = _identitiesByEntity.GetOrAdd(entityId, static key => new PortraitIdentityState
            {
                PortraitIdentityId = $"portrait_identity_{Guid.NewGuid():N}",
                EntityId = key
            });

            if (!string.IsNullOrWhiteSpace(request.RerollOfPortraitId))
            {
                if (!_drafts.TryGetValue(request.RerollOfPortraitId.Trim(), out rerollParent) ||
                    !string.Equals(rerollParent.EntityId, entityId, StringComparison.OrdinalIgnoreCase))
                {
                    throw new ArgumentException("RerollOfPortraitId must refer to an existing portrait draft for the same entity.");
                }
            }
        }

        var portraitDraftId = $"portrait_{Guid.NewGuid():N}";
        var cacheTtl = TimeSpan.FromDays(180);
        var variantStates = new Dictionary<string, PortraitVariantState>(StringComparer.OrdinalIgnoreCase);
        var policy = new AssetLifecyclePolicy(
            CacheTtl: cacheTtl,
            LongTermCache: false,
            MaxBytes: 2_000_000,
            RequiresApproval: true,
            PersistOnApproval: true,
            StorageClass: AssetStorageClass.ObjectStorage,
            AllowPersistentPinning: true);

        foreach (var variant in Variants)
        {
            var isUndercover = variant.Contains("undercover", StringComparison.OrdinalIgnoreCase) && request.AllowUnderscover;
            string styleLine;
            lock (styleTokens)
            {
                styleLine = $"{style}|{string.Join(',', styleTokens.OrderBy(static token => token, StringComparer.OrdinalIgnoreCase))}{(isUndercover ? "|undercover" : string.Empty)}";
            }

            var html = RenderVariantAsset(entityId, variant, styleLine, notes, portraitDraftId, rerollParent?.PortraitDraftId);
            var job = await _mediaRenderJobs.EnqueueAsync(
                new MediaRenderJobEnqueueRequest(
                    JobType: MediaRenderJobType.PortraitImageVariant,
                    DeduplicationKey: $"{portraitDraftId}:{variant}",
                    Category: $"portrait/{entityId}",
                    Payload: html,
                    Source: $"style={style}|draft={portraitDraftId}",
                    CacheTtl: cacheTtl,
                    MaxBytes: policy.MaxBytes,
                    RequiresApproval: true,
                    PersistOnApproval: true,
                    AllowPersistentPinning: true),
                cancellationToken: cancellationToken);

            variantStates[variant] = new PortraitVariantState
            {
                Variant = variant,
                JobId = job.JobId,
                PromptLineage = styleLine,
                StyleToken = style
            };
        }

        var createdAtUtc = DateTimeOffset.UtcNow;
        var draftState = new PortraitDraftState
        {
            PortraitDraftId = portraitDraftId,
            PortraitIdentityId = identity.PortraitIdentityId,
            EntityId = entityId,
            Style = style,
            Notes = notes,
            AllowUndercover = request.AllowUnderscover,
            RerollOfPortraitId = rerollParent?.PortraitDraftId,
            RerollRootPortraitId = rerollParent is null
                ? null
                : string.IsNullOrWhiteSpace(rerollParent.RerollRootPortraitId)
                    ? rerollParent.PortraitDraftId
                    : rerollParent.RerollRootPortraitId,
            RerollDepth = rerollParent is null ? 0 : rerollParent.RerollDepth + 1,
            CreatedAtUtc = createdAtUtc,
            CacheTtl = cacheTtl,
            Confidence = 0.82d,
            Variants = variantStates,
            ReviewHistory = new List<PortraitReviewRecord>()
        };

        lock (_sync)
        {
            _drafts[draftState.PortraitDraftId] = draftState;
            identity.DraftIds.Add(draftState.PortraitDraftId);
        }

        return BuildResult(draftState);
    }

    public PortraitForgeResult? Get(string portraitDraftId)
    {
        if (string.IsNullOrWhiteSpace(portraitDraftId) ||
            !_drafts.TryGetValue(portraitDraftId.Trim(), out var draft))
        {
            return null;
        }

        return BuildResult(draft);
    }

    public IReadOnlyList<PortraitForgeResult> ListForEntity(string entityId)
    {
        if (string.IsNullOrWhiteSpace(entityId) ||
            !_identitiesByEntity.TryGetValue(entityId.Trim(), out var identity))
        {
            return Array.Empty<PortraitForgeResult>();
        }

        lock (_sync)
        {
            return identity.DraftIds
                .Select(id => _drafts.TryGetValue(id, out var draft) ? BuildResult(draft) : null)
                .Where(static result => result is not null)
                .Cast<PortraitForgeResult>()
                .OrderByDescending(static result => result.CreatedAtUtc)
                .ToArray();
        }
    }

    public async Task<PortraitForgeResult?> ApproveAsync(string portraitDraftId, PortraitApprovalRequest request, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(portraitDraftId))
        {
            throw new ArgumentException("portraitDraftId is required.", nameof(portraitDraftId));
        }

        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.Variant) || string.IsNullOrWhiteSpace(request.ApprovedBy))
        {
            throw new ArgumentException("Variant and ApprovedBy are required.", nameof(request));
        }

        PortraitDraftState draft;
        PortraitIdentityState identity;
        lock (_sync)
        {
            if (!_drafts.TryGetValue(portraitDraftId.Trim(), out draft!))
            {
                return null;
            }

            identity = _identitiesByEntity[draft.EntityId];
        }

        if (!draft.Variants.TryGetValue(request.Variant.Trim(), out var selectedVariant))
        {
            throw new InvalidOperationException("Requested portrait variant does not exist on this draft.");
        }

        var selectedAsset = ResolveAsset(selectedVariant);
        if (selectedAsset is null)
        {
            throw new InvalidOperationException("Selected portrait variant is not ready for approval.");
        }

        string? previousCanonicalPortraitId;
        string? previousCanonicalDraftId;
        lock (_sync)
        {
            previousCanonicalPortraitId = identity.CanonicalPortraitId;
            previousCanonicalDraftId = identity.CanonicalDraftId;
        }

        if (!string.IsNullOrWhiteSpace(previousCanonicalPortraitId) &&
            !string.Equals(previousCanonicalPortraitId, selectedAsset.AssetId, StringComparison.OrdinalIgnoreCase))
        {
            await _assetLifecycle.ApplyLifecycleAsync(
                previousCanonicalPortraitId,
                new AssetLifecycleMutationRequest(
                    ApprovalState: AssetApprovalState.Approved,
                    Pin: false,
                    Persist: true,
                    Reason: "superseded by newer canonical portrait"),
                cancellationToken);
        }

        var canonicalAsset = await _assetLifecycle.ApplyLifecycleAsync(
            selectedAsset.AssetId,
            new AssetLifecycleMutationRequest(
                ApprovalState: AssetApprovalState.Approved,
                Pin: request.PinCanonical,
                Persist: true,
                Reason: request.Notes),
            cancellationToken);
        if (canonicalAsset is null)
        {
            throw new InvalidOperationException("Selected portrait asset expired before approval could complete.");
        }

        foreach (var variant in draft.Variants.Values)
        {
            if (string.Equals(variant.Variant, selectedVariant.Variant, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var alternativeAsset = ResolveAsset(variant);
            if (alternativeAsset is null ||
                alternativeAsset.ApprovalState == AssetApprovalState.Rejected)
            {
                continue;
            }

            await _assetLifecycle.ApplyLifecycleAsync(
                alternativeAsset.AssetId,
                new AssetLifecycleMutationRequest(
                    ApprovalState: AssetApprovalState.Rejected,
                    Pin: false,
                    Persist: false,
                    Reason: "not selected as canonical portrait"),
                cancellationToken);
        }

        var reviewRecord = new PortraitReviewRecord(
            Action: "approved",
            Variant: selectedVariant.Variant,
            AssetId: canonicalAsset.AssetId,
            Actor: request.ApprovedBy.Trim(),
            AtUtc: DateTimeOffset.UtcNow,
            Notes: request.Notes,
            PreviousCanonicalPortraitId: previousCanonicalPortraitId,
            ResultingCanonicalPortraitId: canonicalAsset.AssetId);

        lock (_sync)
        {
            if (!string.IsNullOrWhiteSpace(previousCanonicalDraftId) &&
                !string.Equals(previousCanonicalDraftId, draft.PortraitDraftId, StringComparison.OrdinalIgnoreCase) &&
                _drafts.TryGetValue(previousCanonicalDraftId, out var previousCanonicalDraft))
            {
                previousCanonicalDraft.DraftState = "superseded";
            }

            draft.DraftState = "approved";
            draft.ApprovedVariant = selectedVariant.Variant;
            draft.ApprovedAssetId = canonicalAsset.AssetId;
            draft.ReviewHistory.Add(reviewRecord);
            identity.CanonicalPortraitId = canonicalAsset.AssetId;
            identity.CanonicalDraftId = draft.PortraitDraftId;
            identity.CanonicalVariant = selectedVariant.Variant;
            identity.History.Add(reviewRecord);
        }

        return BuildResult(draft);
    }

    private PortraitForgeResult BuildResult(PortraitDraftState draft)
    {
        var variants = draft.Variants.Values
            .Select(variant =>
            {
                var asset = ResolveAsset(variant);
                var approvalState = asset?.ApprovalState ?? AssetApprovalState.Pending;
                var retentionState = asset?.RetentionState ?? ResolvePendingRetention(variant);
                return new PortraitVariant(
                    Variant: variant.Variant,
                    JobId: variant.JobId,
                    AssetId: asset?.AssetId,
                    PromptLineage: variant.PromptLineage,
                    StyleToken: variant.StyleToken,
                    ApprovalState: approvalState,
                    RetentionState: retentionState,
                    IsCanonical: IsCanonicalVariant(draft, variant.Variant, asset?.AssetId));
            })
            .OrderBy(static variant => Array.IndexOf(Variants, variant.Variant))
            .ToArray();

        lock (_sync)
        {
            if (_identitiesByEntity.TryGetValue(draft.EntityId, out var identity) &&
                draft.DraftState == "draft" &&
                variants.All(static variant => variant.RetentionState == AssetRetentionState.Expired))
            {
                draft.DraftState = identity.CanonicalDraftId == draft.PortraitDraftId ? "approved" : "expired";
            }

            return new PortraitForgeResult(
                PortraitDraftId: draft.PortraitDraftId,
                PortraitIdentityId: draft.PortraitIdentityId,
                EntityId: draft.EntityId,
                CanonicalPortraitId: identity?.CanonicalPortraitId,
                DraftState: draft.DraftState,
                Variants: variants,
                CacheTtl: draft.CacheTtl,
                Confidence: draft.Confidence,
                CreatedAtUtc: draft.CreatedAtUtc,
                RerollOfPortraitId: draft.RerollOfPortraitId,
                RerollRootPortraitId: draft.RerollRootPortraitId,
                RerollDepth: draft.RerollDepth,
                ReviewHistory: draft.ReviewHistory.ToArray());
        }
    }

    private AssetCatalogItem? ResolveAsset(PortraitVariantState variant)
    {
        var job = _mediaRenderJobs.Get(variant.JobId);
        if (string.IsNullOrWhiteSpace(job?.AssetId))
        {
            return null;
        }

        return _assetLifecycle.Resolve(job.AssetId);
    }

    private AssetRetentionState ResolvePendingRetention(PortraitVariantState variant)
    {
        var job = _mediaRenderJobs.Get(variant.JobId);
        return job?.State switch
        {
            MediaRenderJobState.Expired => AssetRetentionState.Expired,
            MediaRenderJobState.Failed => AssetRetentionState.Rejected,
            _ => AssetRetentionState.ApprovalPending
        };
    }

    private bool IsCanonicalVariant(PortraitDraftState draft, string variant, string? assetId)
    {
        lock (_sync)
        {
            if (!_identitiesByEntity.TryGetValue(draft.EntityId, out var identity))
            {
                return false;
            }

            return string.Equals(identity.CanonicalDraftId, draft.PortraitDraftId, StringComparison.OrdinalIgnoreCase) &&
                   string.Equals(identity.CanonicalVariant, variant, StringComparison.OrdinalIgnoreCase) &&
                   (!string.IsNullOrWhiteSpace(identity.CanonicalPortraitId) &&
                    string.Equals(identity.CanonicalPortraitId, assetId, StringComparison.OrdinalIgnoreCase));
        }
    }

    private static string RenderVariantAsset(
        string entityId,
        string variant,
        string styleLine,
        string? note,
        string portraitDraftId,
        string? rerollParentId)
    {
        var noteText = WebUtility.HtmlEncode(note ?? string.Empty);
        var style = WebUtility.HtmlEncode(styleLine);
        var payload = $"Entity:{WebUtility.HtmlEncode(entityId)} Draft:{WebUtility.HtmlEncode(portraitDraftId)} Variant:{variant} Style:{style} Note:{noteText} RerollOf:{WebUtility.HtmlEncode(rerollParentId ?? string.Empty)}";
        var encoded = Convert.ToBase64String(Encoding.UTF8.GetBytes(payload));
        return $"<div class=\"portrait-variant\"><h1>{variant}</h1><p>{WebUtility.HtmlEncode(payload)}</p><img src=\"data:text/plain;base64,{encoded}\" /></div>";
    }
}
