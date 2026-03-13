using System.Text.Json;
using System.Reflection;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.Contracts.Registry;
using Chummer.Run.Registry.Services;
using RegistryHubReviewRequest = Chummer.Run.Contracts.Registry.HubReviewRequest;

namespace RunServicesVerification;

internal static class StateStoreBackupVerification
{
    public static async Task RunAsync()
    {
        await VerifySessionLedgerBackupRestoreAsync();
        VerifyHubStoreBackupRestore();
        VerifyHubStoreRestoresLegacyV1Backups();
        VerifyStoreSignatureBoundary();
    }

    private static async Task VerifySessionLedgerBackupRestoreAsync()
    {
        var ledger = new SessionLedgerService();
        var timestamp = DateTimeOffset.Parse("2026-03-10T12:00:00+00:00");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session-backup",
                SceneId: "scene-1",
                EventType: "event-a",
                Payload: "{}",
                AtUtc: timestamp,
                EventId: "evt-1"),
            new SessionEventEnvelope(
                SessionId: "session-backup",
                SceneId: "scene-1",
                EventType: "event-b",
                Payload: "{}",
                AtUtc: timestamp.AddMinutes(1),
                EventId: "evt-2"),
            new SessionEventEnvelope(
                SessionId: "session-backup",
                SceneId: "scene-1",
                EventType: "event-dup",
                Payload: "{}",
                AtUtc: timestamp.AddMinutes(2),
                EventId: "evt-2"),
            new SessionEventEnvelope(
                SessionId: "session-backup",
                SceneId: "scene-other",
                EventType: "wrong-scene",
                Payload: "{}",
                AtUtc: timestamp,
                EventId: "evt-z")
        ]);

        var beforeProjection = ledger.GetProjection("session-backup", "scene-1");
        var beforePipeline = ledger.GetRelayPipelineProjection();
        var backup = ledger.ExportBackup();
        VerificationAssert.Equal("session_state_backup_v1", backup.ContractFamily, "Session ledger backups should use canonical family.");
        VerificationAssert.True(backup.Scenes.Count == 1, "Session ledger backup should retain only canonical merged scene state.");

        // Mutate the source after backup to verify restore is based on captured state.
        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session-backup",
                SceneId: "scene-1",
                EventType: "event-c",
                Payload: "{}",
                AtUtc: timestamp.AddMinutes(3),
                EventId: "evt-3")
        ]);

        var restored = new SessionLedgerService();
        restored.RestoreBackup(backup);

        var restoredProjection = restored.GetProjection("session-backup", "scene-1");
        var restoredPipeline = restored.GetRelayPipelineProjection();

        VerificationAssert.Equal(beforeProjection.ProjectionFingerprint, restoredProjection.ProjectionFingerprint, "Session ledger restore should preserve projection fingerprint.");
        VerificationAssert.Equal(beforeProjection.Events.Count, restoredProjection.Events.Count, "Session ledger restore should preserve event count.");
        VerificationAssert.Equal(beforePipeline.Observability.ProcessedCount, restoredPipeline.Observability.ProcessedCount, "Session ledger restore should preserve observability counters.");
        VerificationAssert.Equal(beforePipeline.Idempotency.ReplayCount, restoredPipeline.Idempotency.ReplayCount, "Session ledger restore should preserve replay counters.");
    }

    private static void VerifyHubStoreBackupRestore()
    {
        var store = new HubArtifactStore();
        var created = store.UpsertArtifact(new HubArtifactCreateRequest(
            Name: "Backup Artifact",
            Kind: HubArtifactKind.RulePack,
            Version: "1.0.0",
            RulesetId: "sr6",
            Visibility: ArtifactVisibilityModes.LocalOnly,
            TrustTier: ArtifactTrustTiers.LocalOnly,
            OwnerId: "ops.backup",
            PublisherId: null,
            Summary: "state backup drill",
            Description: null,
            RuntimeFingerprint: "runtime:v1"));

        store.RegisterInstall(created.Id, new HubInstallEvent(
            ArtifactId: created.Id,
            UserId: "runner-1",
            InstalledAtUtc: DateTimeOffset.Parse("2026-03-10T12:05:00+00:00"),
            ActiveRuntimeRef: true));
        store.AddReview(created.Id, new RegistryHubReviewRequest(created.Id, 8, "stable"));
        store.ChangeState(created.Id, new HubArtifactStateChangeRequest(
            RequestedBy: "ops.backup",
            TargetState: HubArtifactState.Deprecated,
            SupersededByArtifactId: null,
            Reason: "backup-drill"));

        var issueRequest = new RuntimeBundleIssueRequest(
            SessionId: "session-backup",
            SceneId: "scene-1",
            Head: RuntimeBundleHeadKind.Session,
            SourceBundleVersion: "bundle-v1",
            ProjectionFingerprint: "proj-fp-1",
            ProjectionVersion: 2,
            Ready: true,
            OfflineCapable: true,
            CollaborationMode: "portable",
            InvalidationSignals: ["ledger-update"],
            IncludedEventTypes: ["event-a"],
            SupportedExchangeFormats: ["session-ledger.v1"],
            RequestedBy: "ops.backup",
            OwnerId: "ops.backup",
            RulesetId: "sr6",
            Visibility: ArtifactVisibilityModes.CampaignShared,
            TrustTier: ArtifactTrustTiers.Official,
            PublisherId: "pub.backup",
            Description: "backup drill bundle description",
            Summary: "backup drill bundle");
        var issued = store.IssueRuntimeBundle(issueRequest);
        store.IssueRuntimeBundle(issueRequest); // idempotency replay
        store.AttemptDelete("missing-artifact");

        var beforePipeline = store.GetRegistryPipelineProjection();
        var backup = store.ExportBackup();
        VerificationAssert.Equal("hub_state_backup_v1", backup.ContractFamily, "Hub store backups should use canonical family.");
        VerificationAssert.True(backup.Artifacts.Count >= 2, "Hub store backup should include both authored and runtime bundle artifacts.");
        VerificationAssert.True(backup.RuntimeBundleHeads.Count >= 1, "Hub store backup should include runtime bundle heads.");

        // Mutate the source after backup to verify restore is based on captured state.
        store.UpsertArtifact(new HubArtifactCreateRequest(
            Name: "Post-backup drift",
            Kind: HubArtifactKind.BuildIdea,
            Version: "1.0.0",
            RulesetId: "sr6",
            Visibility: ArtifactVisibilityModes.LocalOnly,
            TrustTier: ArtifactTrustTiers.LocalOnly,
            OwnerId: "ops.backup",
            PublisherId: null,
            Summary: "should not appear in restored state",
            Description: null,
            RuntimeFingerprint: null));

        var restored = new HubArtifactStore();
        restored.RestoreBackup(backup);

        var restoredProjection = restored.GetProjection(created.Id);
        var restoredArtifact = restored.GetArtifact(created.Id);
        var restoredHead = restored.GetRuntimeBundleHead("session-backup", "scene-1", RuntimeBundleHeadKind.Session);
        var restoredPipeline = restored.GetRegistryPipelineProjection();

        VerificationAssert.NotNull(restoredProjection, "Hub store restore should preserve artifact projections.");
        VerificationAssert.Equal(HubArtifactState.Deprecated.ToString(), restoredProjection!.State, "Hub store restore should preserve artifact lifecycle state.");
        VerificationAssert.NotNull(restoredArtifact, "Hub store restore should preserve authored artifact metadata.");
        VerificationAssert.Equal("sr6", restoredArtifact!.RulesetId, "Hub store restore should preserve artifact ruleset metadata.");
        VerificationAssert.Equal(ArtifactVisibilityModes.LocalOnly, restoredArtifact.Visibility, "Hub store restore should preserve authored artifact visibility.");
        VerificationAssert.Equal(ArtifactTrustTiers.LocalOnly, restoredArtifact.TrustTier, "Hub store restore should preserve authored artifact trust tier.");
        VerificationAssert.NotNull(restoredHead, "Hub store restore should preserve runtime bundle heads.");
        VerificationAssert.Equal(issued.Head.CurrentArtifactId, restoredHead!.CurrentArtifactId, "Hub store restore should preserve runtime head ownership.");
        var restoredRuntimeArtifact = restored.GetArtifact(issued.Artifact.Id);
        VerificationAssert.NotNull(restoredRuntimeArtifact, "Hub store restore should preserve runtime-bundle artifact metadata.");
        VerificationAssert.Equal("sr6", restoredRuntimeArtifact!.RulesetId, "Hub store restore should preserve runtime-bundle ruleset metadata.");
        VerificationAssert.Equal(ArtifactVisibilityModes.CampaignShared, restoredRuntimeArtifact.Visibility, "Hub store restore should preserve runtime-bundle visibility.");
        VerificationAssert.Equal(ArtifactTrustTiers.Official, restoredRuntimeArtifact.TrustTier, "Hub store restore should preserve runtime-bundle trust tier.");
        VerificationAssert.True(string.Equals("pub.backup", restoredRuntimeArtifact.PublisherId, StringComparison.Ordinal), "Hub store restore should preserve runtime-bundle publisher metadata.");
        VerificationAssert.True(string.Equals("backup drill bundle description", restoredRuntimeArtifact.Description, StringComparison.Ordinal), "Hub store restore should preserve runtime-bundle description metadata.");
        VerificationAssert.Equal(beforePipeline.Observability.ProcessedCount, restoredPipeline.Observability.ProcessedCount, "Hub store restore should preserve observability counters.");
        VerificationAssert.Equal(beforePipeline.Idempotency.ReplayCount, restoredPipeline.Idempotency.ReplayCount, "Hub store restore should preserve replay counters.");
    }

    private static void VerifyStoreSignatureBoundary()
    {
        VerifyMethodSignatures(typeof(ISessionLedgerService));
        VerifyMethodSignatures(typeof(IHubArtifactStore));
    }

    private static void VerifyHubStoreRestoresLegacyV1Backups()
    {
        const string legacyBackupJson = """
            {
              "ExportedAtUtc": "2026-03-10T12:00:00+00:00",
              "Artifacts": [
                {
                  "Id": "artifact-legacy",
                  "Name": "Legacy Artifact",
                  "Kind": 0,
                  "Version": "1.0.0",
                  "State": 0,
                  "Owner": "ops.legacy",
                  "Summary": "legacy backup payload",
                  "RuntimeFingerprint": "legacy:fingerprint",
                  "StateReason": null,
                  "SupersededByArtifactId": null,
                  "CreatedAtUtc": "2026-03-10T12:00:00+00:00",
                  "UpdatedAtUtc": "2026-03-10T12:00:00+00:00",
                  "LifecycleChangedAtUtc": null,
                  "InstallCount": 1,
                  "ActiveRuntimeRefCount": 0,
                  "LastInstalledAtUtc": "2026-03-10T12:00:00+00:00",
                  "ReviewScores": [7]
                }
              ],
              "RuntimeBundleArtifacts": [],
              "RuntimeBundleHeads": [],
              "DeadLetters": [],
              "UpsertCount": 1,
              "RuntimeIssueCount": 0,
              "RuntimeIssueIdempotentCount": 0,
              "LastRuntimeIssueReplayAtUtc": null,
              "InstallCount": 1,
              "ReviewCount": 1,
              "ContractFamily": "hub_state_backup_v1"
            }
            """;

        var legacyBackup = JsonSerializer.Deserialize<HubArtifactStoreBackupPackage>(legacyBackupJson);
        VerificationAssert.NotNull(legacyBackup, "Legacy hub-store backups should deserialize into the current backup package.");

        var restored = new HubArtifactStore();
        restored.RestoreBackup(legacyBackup!);

        var restoredArtifact = restored.GetArtifact("artifact-legacy");
        VerificationAssert.NotNull(restoredArtifact, "Legacy hub-store backups should restore authored artifact metadata.");
        VerificationAssert.Equal("sr5", restoredArtifact!.RulesetId, "Legacy hub-store backups should default missing ruleset metadata.");
        VerificationAssert.Equal(ArtifactVisibilityModes.Shared, restoredArtifact.Visibility, "Legacy hub-store backups should default missing visibility metadata.");
        VerificationAssert.Equal(ArtifactTrustTiers.Curated, restoredArtifact.TrustTier, "Legacy hub-store backups should default missing trust tier metadata.");
        VerificationAssert.True(restoredArtifact.PublisherId is null, "Legacy hub-store backups should default missing publisher metadata.");
        VerificationAssert.True(restoredArtifact.Description is null, "Legacy hub-store backups should default missing description metadata.");
    }

    private static void VerifyMethodSignatures(Type type)
    {
        const string message = "Store public signatures must stay on hosted clean-room contract surfaces.";
        foreach (var method in type.GetMethods(BindingFlags.Instance | BindingFlags.Public))
        {
            var allTypes = new[] { method.ReturnType }.Concat(method.GetParameters().Select(parameter => parameter.ParameterType));
            foreach (var parameterType in allTypes.SelectMany(FlattenTypes))
            {
                if (IsAllowedSignatureType(parameterType))
                {
                    continue;
                }

                throw new InvalidOperationException($"{message} Offending type '{parameterType.FullName}' on {type.Name}.{method.Name}.");
            }
        }
    }

    private static IEnumerable<Type> FlattenTypes(Type type)
    {
        if (Nullable.GetUnderlyingType(type) is Type underlying)
        {
            yield return underlying;
            yield break;
        }

        if (type.IsArray)
        {
            var elementType = type.GetElementType();
            if (elementType is not null)
            {
                foreach (var nested in FlattenTypes(elementType))
                {
                    yield return nested;
                }
            }
            yield break;
        }

        if (type.IsGenericType)
        {
            foreach (var argument in type.GetGenericArguments())
            {
                foreach (var nested in FlattenTypes(argument))
                {
                    yield return nested;
                }
            }
        }

        yield return type;
    }

    private static bool IsAllowedSignatureType(Type type)
    {
        if (type.IsGenericParameter)
        {
            return true;
        }

        if (type.IsPrimitive || type == typeof(string) || type == typeof(decimal))
        {
            return true;
        }

        var ns = type.Namespace ?? string.Empty;
        return ns.StartsWith("System", StringComparison.Ordinal)
            || ns.StartsWith("Chummer.Run.Contracts", StringComparison.Ordinal)
            || ns.StartsWith("Chummer.Play.Contracts", StringComparison.Ordinal)
            || ns.StartsWith("Chummer.Media.Contracts", StringComparison.Ordinal);
    }
}
