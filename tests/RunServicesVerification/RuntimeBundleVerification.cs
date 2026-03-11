using Chummer.Run.Contracts.Registry;
using Chummer.Run.Registry.Services;

namespace RunServicesVerification;

internal static class RuntimeBundleVerification
{
    public static void Run()
    {
        var store = new HubArtifactStore();

        var sessionIssued = store.IssueRuntimeBundle(new RuntimeBundleIssueRequest(
            SessionId: "session_alpha",
            SceneId: "scene_redmond",
            Head: RuntimeBundleHeadKind.Session,
            SourceBundleVersion: "bundle-2-abcd1234",
            ProjectionFingerprint: "abcd1234efgh5678",
            ProjectionVersion: 2,
            Ready: true,
            OfflineCapable: true,
            CollaborationMode: "local-first",
            InvalidationSignals: new[] { "event-stream:session_alpha:scene_redmond" },
            IncludedEventTypes: new[] { "objective.unresolved", "relationship.shift" },
            SupportedExchangeFormats: new[] { "session-ledger.v1", "foundry-vtt.scene-ledger.v1" },
            RequestedBy: "ops.publisher",
            Owner: "hub.ops",
            Summary: "Session head bundle"));

        VerificationAssert.True(sessionIssued.CreatedNewArtifact, "First runtime-bundle issue should create a new immutable artifact.");
        VerificationAssert.Equal(HubArtifactKind.RuntimeBundle, sessionIssued.Artifact.Kind, "Issued runtime bundles should land in the runtime-bundle registry kind.");
        VerificationAssert.Equal(RuntimeBundleHeadKind.Session, sessionIssued.Projection.Head, "Runtime-bundle projections should preserve the head kind.");
        VerificationAssert.Equal(sessionIssued.Artifact.Id, sessionIssued.Head.CurrentArtifactId, "Head projections should point at the issued artifact.");

        var repeated = store.IssueRuntimeBundle(new RuntimeBundleIssueRequest(
            SessionId: "session_alpha",
            SceneId: "scene_redmond",
            Head: RuntimeBundleHeadKind.Session,
            SourceBundleVersion: "bundle-2-abcd1234",
            ProjectionFingerprint: "abcd1234efgh5678",
            ProjectionVersion: 2,
            Ready: true,
            OfflineCapable: true,
            CollaborationMode: "local-first",
            InvalidationSignals: new[] { "event-stream:session_alpha:scene_redmond" },
            IncludedEventTypes: new[] { "objective.unresolved", "relationship.shift" },
            SupportedExchangeFormats: new[] { "session-ledger.v1", "foundry-vtt.scene-ledger.v1" },
            RequestedBy: "ops.publisher",
            Owner: "hub.ops",
            Summary: "Session head bundle"));

        VerificationAssert.True(!repeated.CreatedNewArtifact, "Issuing the same runtime bundle head twice should be idempotent.");
        VerificationAssert.Equal(sessionIssued.Artifact.Id, repeated.Artifact.Id, "Idempotent runtime-bundle issue should preserve the original artifact id.");

        var mobileIssued = store.IssueRuntimeBundle(new RuntimeBundleIssueRequest(
            SessionId: "session_alpha",
            SceneId: "scene_redmond",
            Head: RuntimeBundleHeadKind.Mobile,
            SourceBundleVersion: "bundle-2-abcd1234",
            ProjectionFingerprint: "abcd1234efgh5678",
            ProjectionVersion: 2,
            Ready: true,
            OfflineCapable: true,
            CollaborationMode: "local-first",
            InvalidationSignals: new[] { "event-stream:session_alpha:scene_redmond", "projection-version:2" },
            IncludedEventTypes: new[] { "objective.unresolved", "relationship.shift" },
            SupportedExchangeFormats: new[] { "session-ledger.v1", "mobile-bootstrap.v1" },
            RequestedBy: "ops.publisher",
            Owner: "hub.ops",
            Summary: "Mobile head bundle"));

        VerificationAssert.True(mobileIssued.CreatedNewArtifact, "Different runtime-bundle heads should issue distinct immutable artifacts.");
        VerificationAssert.Equal(RuntimeBundleHeadKind.Mobile, mobileIssued.Head.Head, "Mobile issue should populate the mobile head projection.");

        var sessionUpdated = store.IssueRuntimeBundle(new RuntimeBundleIssueRequest(
            SessionId: "session_alpha",
            SceneId: "scene_redmond",
            Head: RuntimeBundleHeadKind.Session,
            SourceBundleVersion: "bundle-3-ffff9999",
            ProjectionFingerprint: "ffff9999bbbb0000",
            ProjectionVersion: 3,
            Ready: true,
            OfflineCapable: true,
            CollaborationMode: "local-first",
            InvalidationSignals: new[] { "event-stream:session_alpha:scene_redmond", "projection-version:3" },
            IncludedEventTypes: new[] { "objective.unresolved", "relationship.shift", "heat.alert" },
            SupportedExchangeFormats: new[] { "session-ledger.v1", "foundry-vtt.scene-ledger.v1" },
            RequestedBy: "ops.publisher",
            Owner: "hub.ops",
            Summary: "Session head bundle v3"));

        VerificationAssert.True(sessionUpdated.CreatedNewArtifact, "A new projection fingerprint should issue a new immutable artifact.");
        VerificationAssert.Equal(sessionIssued.Artifact.Id, sessionUpdated.Projection.PreviousArtifactId!, "Runtime-bundle projections should preserve the superseded artifact id.");
        VerificationAssert.Equal(sessionIssued.Artifact.Id, sessionUpdated.Head.PreviousArtifactId!, "Head projections should preserve the prior artifact id for lineage.");

        var supersededArtifact = store.GetArtifact(sessionIssued.Artifact.Id);
        VerificationAssert.Equal(HubArtifactState.Superseded, supersededArtifact!.State, "Previous runtime-bundle artifacts should be superseded when a head is reissued.");
        VerificationAssert.Equal(sessionUpdated.Artifact.Id, supersededArtifact.SupersededByArtifactId!, "Superseded runtime bundles should point at the replacement artifact id.");

        var familyHeads = store.GetRuntimeBundleHeads("session_alpha", "scene_redmond");
        VerificationAssert.Equal(2, familyHeads.Heads.Count, "Runtime-bundle head listings should return the issued session and mobile heads.");
        VerificationAssert.True(familyHeads.Heads.Any(head => head.Head == RuntimeBundleHeadKind.Session && head.CurrentArtifactId == sessionUpdated.Artifact.Id), "Head listing should expose the latest session head pointer.");
        VerificationAssert.True(familyHeads.Heads.Any(head => head.Head == RuntimeBundleHeadKind.Mobile && head.CurrentArtifactId == mobileIssued.Artifact.Id), "Head listing should expose the mobile head pointer.");

        var artifactProjection = store.GetRuntimeBundleArtifact(sessionUpdated.Artifact.Id);
        VerificationAssert.Equal("bundle-3-ffff9999", artifactProjection!.SourceBundleVersion, "Runtime-bundle artifact projections should preserve the source session bundle version.");
        VerificationAssert.True(artifactProjection.SupportedExchangeFormats.Contains("foundry-vtt.scene-ledger.v1"), "Runtime-bundle artifact projections should preserve exchange-format seams.");
    }
}
