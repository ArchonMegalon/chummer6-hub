using System.Reflection;
using System.IO;
using System.Text.Json;
using Chummer.Play.Core.Application;
using Chummer.Play.Core.Offline;
using Chummer.Play.Core.PlayApi;
using Chummer.Play.Core.Sync;
using MediaAssetApprovalState = Chummer.Media.Contracts.AssetApprovalState;
using MediaAssetLifecyclePolicy = Chummer.Media.Contracts.AssetLifecyclePolicy;
using MediaMediaRenderJobState = Chummer.Media.Contracts.MediaRenderJobState;
using MediaMediaRenderJobStatus = Chummer.Media.Contracts.MediaRenderJobStatus;
using MediaNewsBriefResult = Chummer.Run.Contracts.Media.NewsBriefResult;
using MediaNpcVideoMessageResult = Chummer.Run.Contracts.Media.NpcVideoMessageResult;
using MediaPacketArtifactHandle = Chummer.Media.Contracts.PacketArtifactHandle;
using MediaPacketArtifactRole = Chummer.Media.Contracts.PacketArtifactRole;
using MediaPacketFactoryResult = Chummer.Media.Contracts.PacketFactoryResult;
using MediaPortraitForgeRequest = Chummer.Run.Contracts.Media.PortraitForgeRequest;
using MediaPortraitVariant = Chummer.Run.Contracts.Media.PortraitVariant;
using MediaRouteCinemaArtifactHandle = Chummer.Media.Contracts.RouteCinemaArtifactHandle;
using MediaRouteCinemaArtifactRole = Chummer.Media.Contracts.RouteCinemaArtifactRole;
using RegistryArtifactInstallProjection = Chummer.Run.Contracts.Registry.HubArtifactInstallProjection;
using RegistryArtifactKind = Chummer.Run.Contracts.Registry.HubArtifactKind;
using RegistryArtifactMetadata = Chummer.Run.Contracts.Registry.HubArtifactMetadata;
using RegistryArtifactState = Chummer.Run.Contracts.Registry.HubArtifactState;
using RegistryArtifactCreateRequest = Chummer.Run.Contracts.Registry.HubArtifactCreateRequest;
using RegistryRuntimeBundleHeadKind = Chummer.Run.Contracts.Registry.RuntimeBundleHeadKind;
using RegistryRuntimeBundleIssueRequest = Chummer.Run.Contracts.Registry.RuntimeBundleIssueRequest;
using RunGatewayContracts = Chummer.Run.Contracts.Gateway;
using RunMemoryContracts = Chummer.Run.Contracts.Memory;
using RunAiContracts = Chummer.Run.AI.Compatibility;

namespace RunServicesVerification;

internal static class CompatibilityVerification
{
    private static readonly string RepoRoot = ResolveRepoRoot();

    public static void Run()
    {
        VerifyRelayCompatibilityDefaults();
        VerifyHostedCanonicalShapes();
        VerifyLegacyAiCompatibilityShapes();
        VerifyMediaCompatibilityShapes();
        VerifyRegistryRequestBackCompat();
        VerifyHubRegistryPublicationBoundary();
        VerifySessionOverlayWrapperIsServerOnly();
        VerifyHostedBoundary();
    }

    private static void VerifyRelayCompatibilityDefaults()
    {
        var bundle = new RunAiContracts.SessionRuntimeBundleResponse(
            SessionId: "session-1",
            SceneId: "scene-1",
            BundleVersion: "bundle-1",
            Ready: true,
            ProjectionVersion: 3,
            ProjectionFingerprint: "fingerprint",
            GeneratedAtUtc: DateTimeOffset.Parse("2026-03-09T12:00:00+00:00"),
            InvalidationSignals: ["ledger-update"],
            IncludedEventTypes: ["alarm-tripped"],
            OfflineCapable: true,
            CollaborationMode: "portable",
            SupportedExchangeFormats: ["foundry-json", "portable-cache"]);
        var delta = new RunAiContracts.SessionDeltaProjection(
            SessionId: "session-1",
            SceneId: "scene-1",
            Version: 3,
            ProjectionFingerprint: "fingerprint",
            GeneratedAtUtc: DateTimeOffset.Parse("2026-03-09T12:00:00+00:00"),
            Events:
            [
                new RunAiContracts.SessionEventEnvelope(
                    SessionId: "session-1",
                    SceneId: "scene-1",
                    EventType: "alarm-tripped",
                    Payload: "{}",
                    AtUtc: DateTimeOffset.Parse("2026-03-09T12:00:00+00:00"),
                    EventId: "evt-1")
            ]);

        VerificationAssert.Equal("runtime_dtos_vnext", bundle.ContractFamily, "Legacy runtime bundle shims should preserve the runtime contract family.");
        VerificationAssert.Equal("session-runtime-bundle", bundle.RuntimeDtoKind, "Legacy runtime bundle shims should preserve the DTO kind.");
        VerificationAssert.Equal("session_events_vnext", delta.ContractFamily, "Legacy relay projections should preserve the canonical relay family.");
    }

    private static void VerifyHostedCanonicalShapes()
    {
        var playContractsAssembly = typeof(SessionEventEnvelope).Assembly;
        var runContractsAssembly = typeof(RunGatewayContracts.ProviderRouteRequest).Assembly;

        AssertEquivalentShape(typeof(SubmitObservationRequest), typeof(RunGatewayContracts.SubmitObservationRequest));
        AssertEquivalentShape(typeof(ProviderRouteRequest), typeof(RunGatewayContracts.ProviderRouteRequest));
        AssertEquivalentShape(typeof(PromptTemplate), typeof(RunGatewayContracts.PromptTemplate));
        AssertEquivalentShape(typeof(GatewayStatus), typeof(RunGatewayContracts.GatewayStatus));

        VerificationAssert.True(
            typeof(PlaySurfaceRole).Assembly == playContractsAssembly,
            "Play surface roles must live in Chummer.Play.Contracts.");
        VerificationAssert.True(
            typeof(PlayBootstrapRequest).Assembly == playContractsAssembly,
            "Play bootstrap requests must live in Chummer.Play.Contracts.");
        VerificationAssert.True(
            typeof(EngineSessionEnvelope).Assembly == playContractsAssembly,
            "Play session envelopes must live in Chummer.Play.Contracts.");
        VerificationAssert.True(
            typeof(SyncCheckpoint).Assembly == playContractsAssembly,
            "Play sync checkpoints must live in Chummer.Play.Contracts.");
        VerificationAssert.True(
            typeof(OfflineLedgerEnvelope).Assembly == playContractsAssembly,
            "Offline ledger envelopes must live in Chummer.Play.Contracts.");

        VerificationAssert.True(
            runContractsAssembly.GetType("Chummer.Run.Contracts.Relay.SessionEventEnvelope") is null,
            "Chummer.Run.Contracts must not shadow relay event DTOs.");
        VerificationAssert.True(
            runContractsAssembly.GetType("Chummer.Run.Contracts.Spider.SpiderObservation") is null,
            "Chummer.Run.Contracts must not shadow spider DTOs.");
        VerificationAssert.True(
            runContractsAssembly.GetType("Chummer.Run.Contracts.Docs.RuntimeDocQuery") is null,
            "Chummer.Run.Contracts must not shadow docs DTOs.");
        VerificationAssert.True(
            runContractsAssembly.GetType("Chummer.Run.Contracts.Interop.InteropExportPackage") is null,
            "Chummer.Run.Contracts must not shadow interop DTOs.");
        VerificationAssert.True(
            runContractsAssembly.GetType("Chummer.Run.Contracts.Memory.SessionMemoryDraftRequest") is null,
            "Chummer.Run.Contracts must not shadow shared memory DTOs.");
        VerificationAssert.True(
            runContractsAssembly.GetType("Chummer.Run.Contracts.Registry.HubArtifactCreateRequest") is null,
            "Chummer.Run.Contracts must not shadow extracted registry DTOs.");
        VerificationAssert.True(
            runContractsAssembly.GetType("Chummer.Run.Contracts.Publication.PublicationRecordResponse") is null,
            "Chummer.Run.Contracts must not shadow extracted publication DTOs.");
        VerificationAssert.True(
            typeof(RunMemoryContracts.SessionMemoryIngestionResult).GetProperty(nameof(RunMemoryContracts.SessionMemoryIngestionResult.Draft))?.PropertyType == typeof(SessionMemoryDraftResult),
            "Run-specific memory ingestion should point back to canonical play-memory draft results.");

        VerificationAssert.True(
            Enum.GetNames(typeof(AiProvider)).SequenceEqual(Enum.GetNames(typeof(RunGatewayContracts.AiProvider)), StringComparer.Ordinal),
            "Gateway provider enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(PromptGroundingKind)).SequenceEqual(Enum.GetNames(typeof(RunGatewayContracts.PromptGroundingKind)), StringComparer.Ordinal),
            "Gateway grounding enums should remain aligned.");
    }

    private static void VerifyLegacyAiCompatibilityShapes()
    {
        AssertEquivalentShape(typeof(RunGatewayContracts.SubmitObservationRequest), typeof(RunAiContracts.SubmitObservationRequest));
        AssertEquivalentShape(typeof(RunGatewayContracts.ProviderRouteRequest), typeof(RunAiContracts.ProviderRouteRequest));
        AssertEquivalentShape(typeof(RunGatewayContracts.PromptTemplate), typeof(RunAiContracts.PromptTemplate));
        AssertEquivalentShape(typeof(RunGatewayContracts.GatewayStatus), typeof(RunAiContracts.GatewayStatus));
        AssertEquivalentShape(typeof(SessionEventEnvelope), typeof(RunAiContracts.SessionEventEnvelope));
        AssertEquivalentShape(typeof(SessionRuntimeBundleDto), typeof(RunAiContracts.SessionRuntimeBundleDto));
        AssertEquivalentShape(typeof(OfflineSyncSnapshotPackage), typeof(RunAiContracts.OfflineSyncSnapshotPackage));
        AssertEquivalentShape(typeof(OfflineSyncReconcileResult), typeof(RunAiContracts.OfflineSyncReconcileResult));
        AssertEquivalentShape(typeof(SessionMemoryDraftRequest), typeof(RunAiContracts.SessionMemoryDraftRequest));
        AssertEquivalentShape(typeof(PersonaMemoryResult), typeof(RunAiContracts.PersonaMemoryResult));
        AssertEquivalentShape(typeof(SpiderObservation), typeof(RunAiContracts.SpiderObservation));
        AssertEquivalentShape(typeof(PolicyDecision), typeof(RunAiContracts.PolicyDecision));
        AssertEquivalentShape(typeof(SpiderTacticalPayload), typeof(RunAiContracts.SpiderTacticalPayload));
        AssertEquivalentShape(typeof(RuntimeDocQuery), typeof(RunAiContracts.RuntimeDocQuery));

        VerificationAssert.True(
            Enum.GetNames(typeof(RunGatewayContracts.AiProvider)).SequenceEqual(Enum.GetNames(typeof(RunAiContracts.AiProvider)), StringComparer.Ordinal),
            "Gateway provider compatibility enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(RunGatewayContracts.PromptGroundingKind)).SequenceEqual(Enum.GetNames(typeof(RunAiContracts.PromptGroundingKind)), StringComparer.Ordinal),
            "Gateway grounding compatibility enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(InterruptionLevel)).SequenceEqual(Enum.GetNames(typeof(RunAiContracts.InterruptionLevel)), StringComparer.Ordinal),
            "Spider interruption compatibility enums should remain aligned.");
    }

    private static void VerifyMediaCompatibilityShapes()
    {
        AssertEquivalentShape(typeof(MediaPortraitForgeRequest), typeof(RunAiContracts.PortraitForgeRequest));
        AssertEquivalentShape(typeof(MediaPortraitVariant), typeof(RunAiContracts.PortraitVariant));
        AssertEquivalentShape(typeof(MediaAssetLifecyclePolicy), typeof(RunAiContracts.AssetLifecyclePolicy));
        AssertEquivalentShape(typeof(MediaMediaRenderJobStatus), typeof(RunAiContracts.MediaRenderJobStatus));
        AssertEquivalentShape(typeof(MediaPacketArtifactHandle), typeof(RunAiContracts.PacketArtifactHandle));
        AssertEquivalentShape(typeof(MediaPacketFactoryResult), typeof(RunAiContracts.PacketFactoryResult));
        AssertEquivalentShape(typeof(MediaRouteCinemaArtifactHandle), typeof(RunAiContracts.RouteCinemaArtifactHandle));
        AssertEquivalentShape(typeof(MediaNewsBriefResult), typeof(RunAiContracts.NewsBriefResult));
        AssertEquivalentShape(typeof(MediaNpcVideoMessageResult), typeof(RunAiContracts.NpcVideoMessageResult));

        VerificationAssert.True(
            Enum.GetNames(typeof(MediaAssetApprovalState)).SequenceEqual(Enum.GetNames(typeof(RunAiContracts.AssetApprovalState)), StringComparer.Ordinal),
            "Approval state compatibility enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(MediaMediaRenderJobState)).SequenceEqual(Enum.GetNames(typeof(RunAiContracts.MediaRenderJobState)), StringComparer.Ordinal),
            "Media job compatibility enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(MediaPacketArtifactRole)).SequenceEqual(Enum.GetNames(typeof(RunAiContracts.PacketArtifactRole)), StringComparer.Ordinal),
            "Packet artifact role compatibility enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(MediaRouteCinemaArtifactRole)).SequenceEqual(Enum.GetNames(typeof(RunAiContracts.RouteCinemaArtifactRole)), StringComparer.Ordinal),
            "Route cinema artifact role compatibility enums should remain aligned.");
    }

    private static void VerifyRegistryRequestBackCompat()
    {
        var legacyCreate = new RegistryArtifactCreateRequest(
            Name: "Legacy pack",
            Kind: RegistryArtifactKind.RulePack,
            Version: "1.0.0",
            Owner: "ops.legacy",
            Summary: "Legacy summary",
            RuntimeFingerprint: "fp-1");
        VerificationAssert.Equal("sr5", legacyCreate.RulesetId, "Legacy create ctor should default missing ruleset id.");
        VerificationAssert.Equal("ops.legacy", legacyCreate.ResolveOwnerId() ?? string.Empty, "Legacy create ctor should preserve Owner as the effective owner id.");

        var legacyRuntimeIssue = new RegistryRuntimeBundleIssueRequest(
            SessionId: "session-1",
            SceneId: "scene-1",
            Head: RegistryRuntimeBundleHeadKind.Session,
            SourceBundleVersion: "bundle-1",
            ProjectionFingerprint: "fingerprint-1",
            ProjectionVersion: 3,
            Ready: true,
            OfflineCapable: true,
            CollaborationMode: "portable",
            InvalidationSignals: ["sig-1"],
            IncludedEventTypes: ["alarm"],
            SupportedExchangeFormats: ["portable-cache"],
            RequestedBy: "ops",
            Owner: "ops.legacy",
            Summary: "Legacy summary");
        VerificationAssert.Equal("sr5", legacyRuntimeIssue.RulesetId, "Legacy runtime issue ctor should default missing ruleset id.");
        VerificationAssert.Equal("ops.legacy", legacyRuntimeIssue.ResolveOwnerId() ?? string.Empty, "Legacy runtime issue ctor should preserve Owner as the effective owner id.");

        var legacyJsonRequest = JsonSerializer.Deserialize<RegistryArtifactCreateRequest>(
            """
            {
              "Name": "JSON legacy pack",
              "Kind": 0,
              "Version": "2.0.0",
              "Owner": "ops.json",
              "Summary": "JSON legacy summary"
            }
            """);
        VerificationAssert.True(legacyJsonRequest is not null, "Legacy create payload should deserialize.");
        VerificationAssert.Equal("sr5", legacyJsonRequest!.RulesetId, "Legacy create payload should default the ruleset id when absent.");
        VerificationAssert.Equal("ops.json", legacyJsonRequest.ResolveOwnerId() ?? string.Empty, "Legacy create payload should map Owner onto the effective owner id.");

        var legacyMetadata = new RegistryArtifactMetadata(
            Id: "artifact-1",
            Name: "Legacy pack",
            Kind: RegistryArtifactKind.RulePack,
            Version: "1.0.0",
            State: RegistryArtifactState.Active,
            Owner: "ops.legacy",
            Summary: "Legacy summary",
            RuntimeFingerprint: "fp-1",
            StateReason: null,
            SupersededByArtifactId: null,
            ImmutableRetentionRequired: true,
            InstallCount: 0,
            ActiveRuntimeRefCount: 0,
            ReviewCount: 0,
            AverageReviewScore: 0,
            CreatedAtUtc: DateTimeOffset.Parse("2026-03-13T00:00:00+00:00"),
            UpdatedAtUtc: DateTimeOffset.Parse("2026-03-13T00:00:00+00:00"),
            LifecycleChangedAtUtc: null);
        var metadataJson = JsonSerializer.Serialize(legacyMetadata);
        VerificationAssert.True(metadataJson.Contains("\"Owner\":\"ops.legacy\"", StringComparison.Ordinal), "Registry metadata should still emit the legacy Owner field.");

        var legacyInstallProjection = new RegistryArtifactInstallProjection(
            ArtifactId: "artifact-1",
            Kind: RegistryArtifactKind.RulePack,
            Version: "1.0.0",
            State: RegistryArtifactState.Active,
            SupersededByArtifactId: null,
            ImmutableRetentionRequired: true,
            AcceptingNewInstalls: true,
            InstallCount: 1,
            ActiveRuntimeRefCount: 0,
            HasInstallReferences: true,
            HasRuntimeReferences: false,
            LastInstalledAtUtc: DateTimeOffset.Parse("2026-03-13T00:00:00+00:00"));
        VerificationAssert.Equal("sr5", legacyInstallProjection.RulesetId, "Legacy install projection ctor should default the ruleset id.");
    }

    private static void VerifyHubRegistryPublicationBoundary()
    {
        var registryAssembly = typeof(Chummer.Run.Registry.Services.HubArtifactStore).Assembly;

        VerificationAssert.True(
            registryAssembly.GetType("Chummer.Run.Registry.Controllers.PublicationsController") is not null,
            "Chummer.Run.Registry must expose PublicationsController.");
        VerificationAssert.True(
            registryAssembly.GetType("Chummer.Run.Registry.Services.PublicationWorkflowService") is not null,
            "Chummer.Run.Registry must expose PublicationWorkflowService.");

        // Load the run-api assembly by name if it exists in the current output set.
        var loadedRunApi = AppDomain.CurrentDomain.GetAssemblies()
            .FirstOrDefault(static assembly => string.Equals(assembly.GetName().Name, "Chummer.Run.Api", StringComparison.Ordinal))
            ?? TryLoadAssembly("Chummer.Run.Api");
        if (loadedRunApi is not null)
        {
            VerificationAssert.True(
                loadedRunApi.GetType("Chummer.Run.Api.Controllers.PublicationsController") is null,
                "Chummer.Run.Api must not own PublicationsController after hub-registry boundary extraction.");
            VerificationAssert.True(
                loadedRunApi.GetType("Chummer.Run.Api.Services.PublicationWorkflowService") is null,
                "Chummer.Run.Api must not own PublicationWorkflowService after hub-registry boundary extraction.");
        }
    }

    private static void VerifySessionOverlayWrapperIsServerOnly()
    {
        var runContractsAssembly = typeof(RunGatewayContracts.ProviderRouteRequest).Assembly;

        VerificationAssert.True(
            runContractsAssembly.GetType("Chummer.Run.Contracts.Relay.SessionOverlayEventDto") is null,
            "Chummer.Run.Contracts must not expose legacy session overlay wrappers.");
        VerificationAssert.True(
            runContractsAssembly.GetType("Chummer.Run.Contracts.Relay.SessionEventEnvelope") is null,
            "Chummer.Run.Contracts must not expose duplicate relay DTO families.");
        VerificationAssert.True(
            typeof(SessionEventEnvelope).Assembly.GetType("Chummer.Play.Contracts.Relay.SessionOverlayEventDto") is null,
            "Chummer.Play.Contracts must not expose legacy session overlay wrappers.");
    }

    private static void VerifyHostedBoundary()
    {
        var manifestPath = Path.Combine(RepoRoot, "docs", "hosted-boundary.manifest");
        VerificationAssert.True(File.Exists(manifestPath), "Hosted boundary manifest must exist.");

        var values = File.ReadAllLines(manifestPath)
            .Where(static line => !string.IsNullOrWhiteSpace(line) && !line.TrimStart().StartsWith('#'))
            .Select(static line => line.Split('=', 2))
            .ToDictionary(
                static parts => parts[0].Trim(),
                static parts => parts.Length > 1 ? parts[1].Trim() : string.Empty,
                StringComparer.Ordinal);

        if (!values.TryGetValue("ACTIVE_HOSTED_PROJECTS", out var hostedProjects))
        {
            throw new InvalidOperationException("Boundary manifest must declare ACTIVE_HOSTED_PROJECTS.");
        }

        if (!values.TryGetValue("EXTERNAL_OWNER_PACKAGES", out var externalOwnerPackagesValue))
        {
            throw new InvalidOperationException("Boundary manifest must declare EXTERNAL_OWNER_PACKAGES.");
        }

        if (!values.TryGetValue("ORACLE_ROOTS", out var oracleRootsValue))
        {
            throw new InvalidOperationException("Boundary manifest must declare ORACLE_ROOTS.");
        }

        if (!values.TryGetValue("RETIRED_ROOTS", out var retiredRootsValue))
        {
            throw new InvalidOperationException("Boundary manifest must declare RETIRED_ROOTS.");
        }

        var expectedHostedProjects = SplitManifestList(hostedProjects);
        var externalOwnerPackages = SplitManifestList(externalOwnerPackagesValue);
        var oracleRoots = SplitManifestList(oracleRootsValue);
        var retiredRoots = SplitManifestList(retiredRootsValue);

        var canonicalHostedProjects = new[]
            {
                "Chummer.Play.Contracts",
                "Chummer.Run.AI",
                "Chummer.Run.Api",
                "Chummer.Run.Contracts",
                "Chummer.Run.Identity"
            }
            .OrderBy(static entry => entry, StringComparer.Ordinal)
            .ToArray();
        var canonicalExternalOwnerPackages = new[]
            {
                "Chummer.Hub.Registry.Contracts",
                "Chummer.Media.Contracts",
                "Chummer.Media.Factory.Runtime",
                "Chummer.Run.Registry"
            }
            .OrderBy(static entry => entry, StringComparer.Ordinal)
            .ToArray();
        var canonicalOracleRoots = Array.Empty<string>();
        var canonicalRetiredRoots = new[]
            {
                "Chummer",
                "Chummer.Api",
                "ChummerDataViewer",
                "ChummerHub",
                "Plugins",
                "TextblockConverter",
                "Translator"
            }
            .OrderBy(static entry => entry, StringComparer.Ordinal)
            .ToArray();

        VerificationAssert.True(
            expectedHostedProjects.SequenceEqual(canonicalHostedProjects, StringComparer.Ordinal),
            "Boundary manifest must keep the canonical hosted project set for identity, relay/Spider/media orchestration, and hosted APIs.");
        VerificationAssert.True(
            externalOwnerPackages.SequenceEqual(canonicalExternalOwnerPackages, StringComparer.Ordinal),
            "Boundary manifest must declare the canonical external owner packages for media-factory and hub-registry seams.");
        VerificationAssert.True(
            oracleRoots.SequenceEqual(canonicalOracleRoots, StringComparer.Ordinal),
            "Boundary manifest must keep the canonical oracle root set.");
        VerificationAssert.True(
            retiredRoots.SequenceEqual(canonicalRetiredRoots, StringComparer.Ordinal),
            "Boundary manifest must keep the canonical retired hosted-clutter set.");

        var solutionPath = Path.Combine(RepoRoot, "Chummer.Run.sln");
        var solutionText = File.ReadAllText(solutionPath);
        var solutionProjectPaths = solutionText
            .Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(static line => line.StartsWith("Project(", StringComparison.Ordinal) && line.Contains(".csproj", StringComparison.Ordinal))
            .Select(static line => line.Split('"'))
            .Where(static parts => parts.Length >= 6)
            .Select(static parts => parts[5].Replace('/', '\\'))
            .ToArray();

        foreach (var projectName in expectedHostedProjects)
        {
            VerificationAssert.True(solutionText.Contains($" = \"{projectName}\", ", StringComparison.Ordinal), $"Hosted solution must include '{projectName}'.");
        }

        foreach (var externalOwnerPackage in externalOwnerPackages)
        {
            VerificationAssert.True(
                !solutionText.Contains($" = \"{externalOwnerPackage}\", ", StringComparison.Ordinal),
                $"Hosted solution must not include external owner package '{externalOwnerPackage}'.");
        }

        foreach (var oracleRoot in oracleRoots)
        {
            var normalizedRoot = oracleRoot.Replace('/', '\\');
            VerificationAssert.True(Directory.Exists(Path.Combine(RepoRoot, oracleRoot)), $"Oracle root '{oracleRoot}' must exist.");
            VerificationAssert.True(
                !solutionProjectPaths.Any(projectPath => projectPath.StartsWith(normalizedRoot + "\\", StringComparison.Ordinal)),
                $"Hosted solution must not include oracle root '{oracleRoot}'.");
        }

        foreach (var retiredRoot in retiredRoots)
        {
            var normalizedRoot = retiredRoot.Replace('/', '\\');
            VerificationAssert.True(
                !Directory.Exists(Path.Combine(RepoRoot, retiredRoot)),
                $"Retired hosted-clutter root '{retiredRoot}' must stay absent.");
            VerificationAssert.True(
                !solutionProjectPaths.Any(projectPath => projectPath.StartsWith(normalizedRoot + "\\", StringComparison.Ordinal)),
                $"Hosted solution must not include retired hosted-clutter root '{retiredRoot}'.");
        }

        var buildScriptPath = Path.Combine(RepoRoot, "scripts", "ai", "build_r1_cleanroom.sh");
        var buildScript = File.ReadAllText(buildScriptPath);

        foreach (var projectName in expectedHostedProjects)
        {
            VerificationAssert.True(
                buildScript.Contains($"dotnet build {projectName}/{projectName}.csproj --nologo", StringComparison.Ordinal),
                $"Clean-room build script must build hosted project '{projectName}'.");
        }

        foreach (var oracleRoot in oracleRoots)
        {
            var oracleBuildPrefix = $"dotnet build {oracleRoot}/";
            VerificationAssert.True(
                !buildScript.Contains(oracleBuildPrefix, StringComparison.Ordinal),
                $"Clean-room build script must not target oracle root '{oracleRoot}'.");
        }

        foreach (var retiredRoot in retiredRoots)
        {
            var retiredBuildPrefix = $"dotnet build {retiredRoot}/";
            VerificationAssert.True(
                !buildScript.Contains(retiredBuildPrefix, StringComparison.Ordinal),
                $"Clean-room build script must not target retired hosted-clutter root '{retiredRoot}'.");
        }

        var compatibilityAssembly = typeof(RunAiContracts.GatewayStatus).Assembly;
        VerificationAssert.True(
            compatibilityAssembly.GetType("Chummer.Run.AI.Compatibility.HubInstallEvent") is null,
            "Run AI compatibility shims must not source-own registry install events after extraction.");
        VerificationAssert.True(
            compatibilityAssembly.GetType("Chummer.Run.AI.Compatibility.HubReviewRequest") is null,
            "Run AI compatibility shims must not source-own registry review requests after extraction.");
        VerificationAssert.True(
            compatibilityAssembly.GetType("Chummer.Run.AI.Compatibility.HubReviewResponse") is null,
            "Run AI compatibility shims must not source-own registry review responses after extraction.");
    }

    private static string[] SplitManifestList(string value)
    {
        return value
            .Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .OrderBy(static entry => entry, StringComparer.Ordinal)
            .ToArray();
    }

    private static string ResolveRepoRoot()
    {
        var candidates = new[]
        {
            Directory.GetCurrentDirectory(),
            AppContext.BaseDirectory
        };

        foreach (var seed in candidates)
        {
            var directory = new DirectoryInfo(seed);
            while (directory is not null)
            {
                if (File.Exists(Path.Combine(directory.FullName, "Chummer.Run.sln")))
                {
                    return directory.FullName;
                }

                directory = directory.Parent;
            }
        }

        throw new InvalidOperationException("Unable to locate repository root containing Chummer.Run.sln.");
    }

    private static void AssertEquivalentShape(Type canonicalType, Type compatibilityType)
    {
        var canonicalMembers = canonicalType
            .GetProperties(BindingFlags.Instance | BindingFlags.Public)
            .Select(static property => $"{property.Name}:{property.PropertyType.Name}")
            .OrderBy(static member => member, StringComparer.Ordinal)
            .ToArray();
        var compatibilityMembers = compatibilityType
            .GetProperties(BindingFlags.Instance | BindingFlags.Public)
            .Select(static property => $"{property.Name}:{property.PropertyType.Name}")
            .OrderBy(static member => member, StringComparer.Ordinal)
            .ToArray();

        VerificationAssert.True(
            canonicalMembers.SequenceEqual(compatibilityMembers, StringComparer.Ordinal),
            $"Compatibility contract '{compatibilityType.Name}' must stay shape-compatible with '{canonicalType.Name}'.");
    }

    private static Assembly? TryLoadAssembly(string assemblyName)
    {
        try
        {
            return Assembly.Load(assemblyName);
        }
        catch
        {
            return null;
        }
    }
}
