using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.KarmaForge;

namespace Chummer.Run.Api.Services;

public sealed record AccountAuxiliaryDataErasureResult(
    int RecordsRemoved,
    IReadOnlyDictionary<string, int> RecordsRemovedByComponent);

public interface IAccountAuxiliaryDataErasureService
{
    AccountAuxiliaryDataErasureResult Erase(string? userId, string subjectId);
}

/// <summary>
/// Erases account-keyed data from first-party stores that sit outside the community snapshot.
/// Each store commits independently and idempotently; Identity is retained until all stores pass,
/// so a caller can retry safely after any storage failure.
/// </summary>
public sealed class AccountAuxiliaryDataErasureService : IAccountAuxiliaryDataErasureService
{
    private readonly BrilliantDirectoriesBillingStore _brilliantDirectories;
    private readonly MyFirstBookUsageStore _myFirstBookUsage;
    private readonly HorizonArtifactUsageStore _horizonUsage;
    private readonly OriginDossierProviderCreditReservationStore _originReservations;
    private readonly HorizonArtifactRequestReceiptStore _artifactRequests;
    private readonly PayFunnelsBillingStore _payFunnels;
    private readonly InstallLinkedWorkspaceSnapshotStore _installSnapshots;
    private readonly InstallLinkingStoreAccess _installLinking;
    private readonly GmSessionVenueStore _venues;
    private readonly GmSessionVideoFoundryStore _videoFoundry;
    private readonly PromptFoundryStore _promptFoundry;
    private readonly KarmaForgeStore _karmaForge;
    private readonly OriginDossierPublicationService _originDossiers;

    public AccountAuxiliaryDataErasureService(
        BrilliantDirectoriesBillingStore brilliantDirectories,
        MyFirstBookUsageStore myFirstBookUsage,
        HorizonArtifactUsageStore horizonUsage,
        OriginDossierProviderCreditReservationStore originReservations,
        HorizonArtifactRequestReceiptStore artifactRequests,
        PayFunnelsBillingStore payFunnels,
        InstallLinkedWorkspaceSnapshotStore installSnapshots,
        InstallLinkingStoreAccess installLinking,
        GmSessionVenueStore venues,
        GmSessionVideoFoundryStore videoFoundry,
        PromptFoundryStore promptFoundry,
        KarmaForgeStore karmaForge,
        OriginDossierPublicationService originDossiers)
    {
        _brilliantDirectories = brilliantDirectories;
        _myFirstBookUsage = myFirstBookUsage;
        _horizonUsage = horizonUsage;
        _originReservations = originReservations;
        _artifactRequests = artifactRequests;
        _payFunnels = payFunnels;
        _installSnapshots = installSnapshots;
        _installLinking = installLinking;
        _venues = venues;
        _videoFoundry = videoFoundry;
        _promptFoundry = promptFoundry;
        _karmaForge = karmaForge;
        _originDossiers = originDossiers;
    }

    public AccountAuxiliaryDataErasureResult Erase(string? userId, string subjectId)
    {
        string normalizedSubject = string.IsNullOrWhiteSpace(subjectId)
            ? throw new ArgumentException("subjectId is required.", nameof(subjectId))
            : subjectId.Trim();
        string? normalizedUser = string.IsNullOrWhiteSpace(userId) ? null : userId.Trim();
        var removed = new Dictionary<string, int>(StringComparer.Ordinal)
        {
            ["brilliant_directories_projection"] = EraseSingleList(
                _brilliantDirectories.Gate,
                _brilliantDirectories.Members,
                item => IdEquals(item.UserId, normalizedUser),
                _brilliantDirectories.PersistLocked),
            ["myfirstbook_usage"] = EraseSingleList(
                _myFirstBookUsage.Gate,
                _myFirstBookUsage.Entries,
                item => IdEquals(item.UserId, normalizedUser),
                _myFirstBookUsage.PersistLocked),
            ["horizon_usage"] = EraseSingleList(
                _horizonUsage.Gate,
                _horizonUsage.Entries,
                item => IdEquals(item.UserId, normalizedUser),
                _horizonUsage.PersistLocked),
            ["origin_provider_reservations"] = EraseSingleList(
                _originReservations.Gate,
                _originReservations.Entries,
                item => IdEquals(item.UserId, normalizedUser),
                _originReservations.PersistLocked),
            ["horizon_request_receipts"] = EraseSingleList(
                _artifactRequests.Gate,
                _artifactRequests.Receipts,
                item => IdEquals(item.RequestedByUserId, normalizedUser),
                _artifactRequests.PersistLocked),
            ["payfunnels_billing"] = ErasePayFunnels(normalizedUser),
            ["install_workspace_snapshots"] = EraseInstallSnapshots(normalizedUser, normalizedSubject),
            ["install_linking"] = _installLinking.GetRequired()
                .ErasePrincipal(normalizedUser, normalizedSubject)
                .RecordsRemoved,
            ["gm_session_venues"] = EraseVenues(normalizedUser, normalizedSubject),
            ["gm_session_video_foundry"] = EraseVideoFoundry(normalizedUser),
            ["prompt_foundry"] = ErasePromptFoundry(normalizedUser),
            ["karma_forge"] = EraseKarmaForge(normalizedSubject),
            ["origin_dossier_publications"] = _originDossiers.EraseForAccount(normalizedUser, normalizedSubject)
        };

        return new AccountAuxiliaryDataErasureResult(removed.Values.Sum(), removed);
    }

    private int ErasePayFunnels(string? userId)
    {
        if (userId is null)
        {
            return 0;
        }

        lock (_payFunnels.Gate)
        {
            var intents = _payFunnels.Intents.ToArray();
            var events = _payFunnels.Events.ToArray();
            var receipts = _payFunnels.Receipts.ToArray();
            var entitlements = _payFunnels.EntitlementLedger.ToArray();
            try
            {
                HashSet<string> providerEventIds = _payFunnels.Receipts
                    .Where(item => IdEquals(item.UserId, userId))
                    .Select(static item => item.ProviderEventId)
                    .ToHashSet(StringComparer.OrdinalIgnoreCase);
                int removed = _payFunnels.Intents.RemoveAll(item => IdEquals(item.UserId, userId));
                removed += _payFunnels.Receipts.RemoveAll(item => IdEquals(item.UserId, userId));
                removed += _payFunnels.EntitlementLedger.RemoveAll(item => IdEquals(item.UserId, userId));
                removed += _payFunnels.Events.RemoveAll(item => providerEventIds.Contains(item.ProviderEventId));
                PersistIfChanged(removed, _payFunnels.PersistLocked);
                return removed;
            }
            catch
            {
                Restore(_payFunnels.Intents, intents);
                Restore(_payFunnels.Events, events);
                Restore(_payFunnels.Receipts, receipts);
                Restore(_payFunnels.EntitlementLedger, entitlements);
                throw;
            }
        }
    }

    private int EraseInstallSnapshots(string? userId, string subjectId)
    {
        string subjectOwner = $"subject:{subjectId}";
        string? userOwner = userId is null ? null : $"user:{userId}";
        lock (_installSnapshots.Gate)
        {
            KeyValuePair<string, InstallLinkedWorkspaceSnapshotRecord>[] before =
                _installSnapshots.SnapshotsByKey.ToArray();
            try
            {
                int removed = RemoveDictionaryWhere(
                    _installSnapshots.SnapshotsByKey,
                    pair => IdEquals(pair.Value.OwnerKey, subjectOwner)
                            || IdEquals(pair.Value.OwnerKey, userOwner));
                PersistIfChanged(removed, _installSnapshots.PersistLocked);
                return removed;
            }
            catch
            {
                Restore(_installSnapshots.SnapshotsByKey, before);
                throw;
            }
        }
    }

    private int EraseVenues(string? userId, string subjectId)
    {
        lock (_venues.Gate)
        {
            KeyValuePair<string, GmSessionVenueProjection>[] venues = _venues.VenuesBySessionKey.ToArray();
            VenueLinkReceiptProjection[] linkReceipts = _venues.VenueLinkReceipts.ToArray();
            VenueCreatedReceiptProjection[] createdReceipts = _venues.VenueCreatedReceipts.ToArray();
            SessionVenueCloseoutReceiptProjection[] closeouts = _venues.CloseoutReceipts.ToArray();
            NonverbiaDebriefReceiptProjection[] debriefs = _venues.NonverbiaDebriefReceipts.ToArray();
            try
            {
                HashSet<string> venueIds = _venues.VenuesBySessionKey.Values
                    .Where(venue => IdEquals(venue.OwnerAccountId, userId)
                                    || IdEquals(venue.OwnerAccountId, subjectId))
                    .Select(static venue => venue.VenueId)
                    .ToHashSet(StringComparer.OrdinalIgnoreCase);
                int removed = RemoveDictionaryWhere(
                    _venues.VenuesBySessionKey,
                    pair => venueIds.Contains(pair.Value.VenueId));
                removed += _venues.VenueLinkReceipts.RemoveAll(item => venueIds.Contains(item.VenueId));
                removed += _venues.VenueCreatedReceipts.RemoveAll(item => venueIds.Contains(item.VenueId));
                removed += _venues.CloseoutReceipts.RemoveAll(item => venueIds.Contains(item.VenueId));
                removed += _venues.NonverbiaDebriefReceipts.RemoveAll(item => venueIds.Contains(item.VenueId));
                PersistIfChanged(removed, _venues.PersistLocked);
                return removed;
            }
            catch
            {
                Restore(_venues.VenuesBySessionKey, venues);
                Restore(_venues.VenueLinkReceipts, linkReceipts);
                Restore(_venues.VenueCreatedReceipts, createdReceipts);
                Restore(_venues.CloseoutReceipts, closeouts);
                Restore(_venues.NonverbiaDebriefReceipts, debriefs);
                throw;
            }
        }
    }

    private int EraseVideoFoundry(string? userId)
    {
        if (userId is null)
        {
            return 0;
        }

        lock (_videoFoundry.Gate)
        {
            KeyValuePair<string, FaceAssetProjection>[] faces = _videoFoundry.FacesById.ToArray();
            KeyValuePair<string, PromptDraftProjection>[] drafts = _videoFoundry.PromptDraftsById.ToArray();
            PromptVersionProjection[] versions = _videoFoundry.PromptVersions.ToArray();
            KeyValuePair<string, SessionVideoRenderJobProjection>[] jobs = _videoFoundry.JobsById.ToArray();
            RenderUsageLedgerEntryProjection[] usage = _videoFoundry.UsageLedger.ToArray();
            TablePulseMediaPacketProjection[] packets = _videoFoundry.TablePulsePackets.ToArray();
            try
            {
                HashSet<string> faceIds = _videoFoundry.FacesById.Values
                    .Where(face => IdEquals(face.OwnerGmUserId, userId))
                    .Select(static face => face.Id)
                    .ToHashSet(StringComparer.OrdinalIgnoreCase);
                foreach ((string faceId, FaceAssetProjection face) in _videoFoundry.FacesById.ToArray())
                {
                    if (!faceIds.Contains(faceId) && face.AllowedUserIds.Any(id => IdEquals(id, userId)))
                    {
                        _videoFoundry.FacesById[faceId] = face with
                        {
                            AllowedUserIds = face.AllowedUserIds.Where(id => !IdEquals(id, userId)).ToArray()
                        };
                    }
                }

                HashSet<string> draftIds = _videoFoundry.PromptDraftsById.Values
                    .Where(draft => IdEquals(draft.GmUserId, userId)
                                    || draft.SelectedFaceAssetIds.Any(faceIds.Contains))
                    .Select(static draft => draft.Id)
                    .ToHashSet(StringComparer.OrdinalIgnoreCase);
                HashSet<string> jobIds = _videoFoundry.JobsById.Values
                    .Where(job => IdEquals(job.GmUserId, userId)
                                  || draftIds.Contains(job.PromptDraftId)
                                  || job.AssetIds.Any(faceIds.Contains))
                    .Select(static job => job.Id)
                    .ToHashSet(StringComparer.OrdinalIgnoreCase);
                int removed = RemoveDictionaryWhere(_videoFoundry.FacesById, pair => faceIds.Contains(pair.Key));
                removed += RemoveDictionaryWhere(_videoFoundry.PromptDraftsById, pair => draftIds.Contains(pair.Key));
                removed += _videoFoundry.PromptVersions.RemoveAll(item => draftIds.Contains(item.PromptDraftId)
                                                                        || IdEquals(item.EditorUserId, userId));
                removed += RemoveDictionaryWhere(_videoFoundry.JobsById, pair => jobIds.Contains(pair.Key));
                removed += _videoFoundry.UsageLedger.RemoveAll(item => IdEquals(item.GmUserId, userId)
                                                                       || (item.RenderJobId is not null && jobIds.Contains(item.RenderJobId)));
                removed += _videoFoundry.TablePulsePackets.RemoveAll(item => IdEquals(item.GmUserId, userId)
                                                                             || item.CastAssetIds.Any(faceIds.Contains));
                PersistIfChanged(removed, _videoFoundry.PersistLocked);
                return removed;
            }
            catch
            {
                Restore(_videoFoundry.FacesById, faces);
                Restore(_videoFoundry.PromptDraftsById, drafts);
                Restore(_videoFoundry.PromptVersions, versions);
                Restore(_videoFoundry.JobsById, jobs);
                Restore(_videoFoundry.UsageLedger, usage);
                Restore(_videoFoundry.TablePulsePackets, packets);
                throw;
            }
        }
    }

    private int ErasePromptFoundry(string? userId)
    {
        if (userId is null)
        {
            return 0;
        }

        lock (_promptFoundry.Gate)
        {
            KeyValuePair<string, PromptFoundryDraftProjection>[] drafts = _promptFoundry.DraftsById.ToArray();
            PromptFoundryVersionProjection[] versions = _promptFoundry.Versions.ToArray();
            PromptUsageLedgerEntryProjection[] usage = _promptFoundry.UsageLedger.ToArray();
            try
            {
                HashSet<string> draftIds = _promptFoundry.DraftsById.Values
                    .Where(draft => IdEquals(draft.GmUserId, userId)
                                    || IdEquals(draft.OperatorUserId, userId))
                    .Select(static draft => draft.Id)
                    .ToHashSet(StringComparer.OrdinalIgnoreCase);
                int removed = RemoveDictionaryWhere(_promptFoundry.DraftsById, pair => draftIds.Contains(pair.Key));
                removed += _promptFoundry.Versions.RemoveAll(item => draftIds.Contains(item.PromptDraftId)
                                                                    || IdEquals(item.EditorUserId, userId));
                removed += _promptFoundry.UsageLedger.RemoveAll(item => IdEquals(item.UserId, userId)
                                                                       || draftIds.Contains(item.PromptDraftId));
                PersistIfChanged(removed, _promptFoundry.PersistLocked);
                return removed;
            }
            catch
            {
                Restore(_promptFoundry.DraftsById, drafts);
                Restore(_promptFoundry.Versions, versions);
                Restore(_promptFoundry.UsageLedger, usage);
                throw;
            }
        }
    }

    private int EraseKarmaForge(string subjectId)
    {
        lock (_karmaForge.Gate)
        {
            KeyValuePair<string, KarmaForgeSubmissionProjection>[] before =
                _karmaForge.SubmissionsById.ToArray();
            try
            {
                int removed = RemoveDictionaryWhere(
                    _karmaForge.SubmissionsById,
                    pair => IdEquals(pair.Value.SubjectId, subjectId));
                PersistIfChanged(removed, _karmaForge.PersistLocked);
                return removed;
            }
            catch
            {
                Restore(_karmaForge.SubmissionsById, before);
                throw;
            }
        }
    }

    private static int EraseSingleList<T>(
        object gate,
        List<T> list,
        Predicate<T> predicate,
        Action persist)
    {
        lock (gate)
        {
            T[] before = list.ToArray();
            try
            {
                int removed = list.RemoveAll(predicate);
                PersistIfChanged(removed, persist);
                return removed;
            }
            catch
            {
                Restore(list, before);
                throw;
            }
        }
    }

    private static void PersistIfChanged(int removed, Action persist)
    {
        if (removed > 0)
        {
            persist();
        }
    }

    private static int RemoveDictionaryWhere<TKey, TValue>(
        Dictionary<TKey, TValue> dictionary,
        Func<KeyValuePair<TKey, TValue>, bool> predicate)
        where TKey : notnull
    {
        TKey[] keys = dictionary.Where(predicate).Select(static pair => pair.Key).ToArray();
        foreach (TKey key in keys)
        {
            dictionary.Remove(key);
        }

        return keys.Length;
    }

    private static void Restore<T>(List<T> target, IEnumerable<T> values)
    {
        target.Clear();
        target.AddRange(values);
    }

    private static void Restore<TKey, TValue>(
        Dictionary<TKey, TValue> target,
        IEnumerable<KeyValuePair<TKey, TValue>> values)
        where TKey : notnull
    {
        target.Clear();
        foreach ((TKey key, TValue value) in values)
        {
            target[key] = value;
        }
    }

    private static bool IdEquals(string? left, string? right)
        => !string.IsNullOrWhiteSpace(left)
           && !string.IsNullOrWhiteSpace(right)
           && string.Equals(left.Trim(), right.Trim(), StringComparison.OrdinalIgnoreCase);
}
