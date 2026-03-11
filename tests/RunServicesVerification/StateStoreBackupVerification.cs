using System.Reflection;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.Contracts.Registry;
using Chummer.Run.Registry.Services;

namespace RunServicesVerification;

internal static class StateStoreBackupVerification
{
    public static async Task RunAsync()
    {
        await VerifySessionLedgerBackupRestoreAsync();
        VerifyHubStoreBackupRestore();
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
            Owner: "ops.backup",
            Summary: "state backup drill",
            RuntimeFingerprint: "runtime:v1"));

        store.RegisterInstall(created.Id, new HubInstallEvent(
            ArtifactId: created.Id,
            UserId: "runner-1",
            InstalledAtUtc: DateTimeOffset.Parse("2026-03-10T12:05:00+00:00"),
            ActiveRuntimeRef: true));
        store.AddReview(created.Id, new HubReviewRequest(created.Id, 8, "stable"));
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
            Owner: "ops.backup",
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
            Owner: "ops.backup",
            Summary: "should not appear in restored state",
            RuntimeFingerprint: null));

        var restored = new HubArtifactStore();
        restored.RestoreBackup(backup);

        var restoredProjection = restored.GetProjection(created.Id);
        var restoredHead = restored.GetRuntimeBundleHead("session-backup", "scene-1", RuntimeBundleHeadKind.Session);
        var restoredPipeline = restored.GetRegistryPipelineProjection();

        VerificationAssert.NotNull(restoredProjection, "Hub store restore should preserve artifact projections.");
        VerificationAssert.Equal(HubArtifactState.Deprecated.ToString(), restoredProjection!.State, "Hub store restore should preserve artifact lifecycle state.");
        VerificationAssert.NotNull(restoredHead, "Hub store restore should preserve runtime bundle heads.");
        VerificationAssert.Equal(issued.Head.CurrentArtifactId, restoredHead!.CurrentArtifactId, "Hub store restore should preserve runtime head ownership.");
        VerificationAssert.Equal(beforePipeline.Observability.ProcessedCount, restoredPipeline.Observability.ProcessedCount, "Hub store restore should preserve observability counters.");
        VerificationAssert.Equal(beforePipeline.Idempotency.ReplayCount, restoredPipeline.Idempotency.ReplayCount, "Hub store restore should preserve replay counters.");
    }

    private static void VerifyStoreSignatureBoundary()
    {
        VerifyMethodSignatures(typeof(ISessionLedgerService));
        VerifyMethodSignatures(typeof(IHubArtifactStore));
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
