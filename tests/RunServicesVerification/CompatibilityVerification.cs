using System.Reflection;
using System.IO;
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
using RegistryHubInstallEvent = Chummer.Run.Contracts.Registry.HubInstallEvent;
using RegistryHubReviewRequest = Chummer.Run.Contracts.Registry.HubReviewRequest;
using RegistryHubReviewResponse = Chummer.Run.Contracts.Registry.HubReviewResponse;
using RunDocsContracts = Chummer.Run.Contracts.Docs;
using RunGatewayContracts = Chummer.Run.Contracts.Gateway;
using RunInteropContracts = Chummer.Run.Contracts.Interop;
using RunMemoryContracts = Chummer.Run.Contracts.Memory;
using RunRelayContracts = Chummer.Run.Contracts.Relay;
using RunSpiderContracts = Chummer.Run.Contracts.Spider;
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
        VerifyRegistryCompatibilityShapes();
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
        AssertEquivalentShape(typeof(SubmitObservationRequest), typeof(RunGatewayContracts.SubmitObservationRequest));
        AssertEquivalentShape(typeof(ProviderRouteRequest), typeof(RunGatewayContracts.ProviderRouteRequest));
        AssertEquivalentShape(typeof(PromptTemplate), typeof(RunGatewayContracts.PromptTemplate));
        AssertEquivalentShape(typeof(GatewayStatus), typeof(RunGatewayContracts.GatewayStatus));
        AssertEquivalentShape(typeof(SessionEventEnvelope), typeof(RunRelayContracts.SessionEventEnvelope));
        AssertEquivalentShape(typeof(SessionRuntimeBundleDto), typeof(RunRelayContracts.SessionRuntimeBundleDto));
        AssertEquivalentShape(typeof(OfflineSyncSnapshotPackage), typeof(RunRelayContracts.OfflineSyncSnapshotPackage));
        AssertEquivalentShape(typeof(OfflineSyncReconcileResult), typeof(RunRelayContracts.OfflineSyncReconcileResult));
        AssertEquivalentShape(typeof(Chummer.Play.Contracts.Interop.InteropExportPackage), typeof(RunInteropContracts.InteropExportPackage));
        AssertEquivalentShape(typeof(Chummer.Play.Contracts.Interop.InteropImportResult), typeof(RunInteropContracts.InteropImportResult));
        AssertEquivalentShape(typeof(SessionMemoryDraftRequest), typeof(RunMemoryContracts.SessionMemoryDraftRequest));
        AssertEquivalentShape(typeof(PersonaMemoryResult), typeof(RunMemoryContracts.PersonaMemoryResult));
        AssertEquivalentShape(typeof(SpiderObservation), typeof(RunSpiderContracts.SpiderObservation));
        AssertEquivalentShape(typeof(PolicyDecision), typeof(RunSpiderContracts.PolicyDecision));
        AssertEquivalentShape(typeof(SpiderTacticalPayload), typeof(RunSpiderContracts.SpiderTacticalPayload));
        AssertEquivalentShape(typeof(RuntimeDocQuery), typeof(RunDocsContracts.RuntimeDocQuery));

        VerificationAssert.True(
            Enum.GetNames(typeof(AiProvider)).SequenceEqual(Enum.GetNames(typeof(RunGatewayContracts.AiProvider)), StringComparer.Ordinal),
            "Gateway provider enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(PromptGroundingKind)).SequenceEqual(Enum.GetNames(typeof(RunGatewayContracts.PromptGroundingKind)), StringComparer.Ordinal),
            "Gateway grounding enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(InterruptionLevel)).SequenceEqual(Enum.GetNames(typeof(RunSpiderContracts.InterruptionLevel)), StringComparer.Ordinal),
            "Spider interruption enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(Chummer.Play.Contracts.Interop.InteropAssetKind)).SequenceEqual(Enum.GetNames(typeof(RunInteropContracts.InteropAssetKind)), StringComparer.Ordinal),
            "Interop asset-kind enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(Chummer.Play.Contracts.Interop.InteropImportMode)).SequenceEqual(Enum.GetNames(typeof(RunInteropContracts.InteropImportMode)), StringComparer.Ordinal),
            "Interop import-mode enums should remain aligned.");
    }

    private static void VerifyLegacyAiCompatibilityShapes()
    {
        AssertEquivalentShape(typeof(RunGatewayContracts.SubmitObservationRequest), typeof(RunAiContracts.SubmitObservationRequest));
        AssertEquivalentShape(typeof(RunGatewayContracts.ProviderRouteRequest), typeof(RunAiContracts.ProviderRouteRequest));
        AssertEquivalentShape(typeof(RunGatewayContracts.PromptTemplate), typeof(RunAiContracts.PromptTemplate));
        AssertEquivalentShape(typeof(RunGatewayContracts.GatewayStatus), typeof(RunAiContracts.GatewayStatus));
        AssertEquivalentShape(typeof(RunRelayContracts.SessionEventEnvelope), typeof(RunAiContracts.SessionEventEnvelope));
        AssertEquivalentShape(typeof(RunRelayContracts.SessionRuntimeBundleDto), typeof(RunAiContracts.SessionRuntimeBundleDto));
        AssertEquivalentShape(typeof(RunRelayContracts.OfflineSyncSnapshotPackage), typeof(RunAiContracts.OfflineSyncSnapshotPackage));
        AssertEquivalentShape(typeof(RunRelayContracts.OfflineSyncReconcileResult), typeof(RunAiContracts.OfflineSyncReconcileResult));
        AssertEquivalentShape(typeof(RunMemoryContracts.SessionMemoryDraftRequest), typeof(RunAiContracts.SessionMemoryDraftRequest));
        AssertEquivalentShape(typeof(RunMemoryContracts.PersonaMemoryResult), typeof(RunAiContracts.PersonaMemoryResult));
        AssertEquivalentShape(typeof(RunSpiderContracts.SpiderObservation), typeof(RunAiContracts.SpiderObservation));
        AssertEquivalentShape(typeof(RunSpiderContracts.PolicyDecision), typeof(RunAiContracts.PolicyDecision));
        AssertEquivalentShape(typeof(RunSpiderContracts.SpiderTacticalPayload), typeof(RunAiContracts.SpiderTacticalPayload));
        AssertEquivalentShape(typeof(RunDocsContracts.RuntimeDocQuery), typeof(RunAiContracts.RuntimeDocQuery));

        VerificationAssert.True(
            Enum.GetNames(typeof(RunGatewayContracts.AiProvider)).SequenceEqual(Enum.GetNames(typeof(RunAiContracts.AiProvider)), StringComparer.Ordinal),
            "Gateway provider compatibility enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(RunGatewayContracts.PromptGroundingKind)).SequenceEqual(Enum.GetNames(typeof(RunAiContracts.PromptGroundingKind)), StringComparer.Ordinal),
            "Gateway grounding compatibility enums should remain aligned.");
        VerificationAssert.True(
            Enum.GetNames(typeof(RunSpiderContracts.InterruptionLevel)).SequenceEqual(Enum.GetNames(typeof(RunAiContracts.InterruptionLevel)), StringComparer.Ordinal),
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

    private static void VerifyRegistryCompatibilityShapes()
    {
        AssertEquivalentShape(typeof(RegistryHubInstallEvent), typeof(RunAiContracts.HubInstallEvent));
        AssertEquivalentShape(typeof(RegistryHubReviewRequest), typeof(RunAiContracts.HubReviewRequest));
        AssertEquivalentShape(typeof(RegistryHubReviewResponse), typeof(RunAiContracts.HubReviewResponse));
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
        VerificationAssert.True(
            typeof(RunRelayContracts.SessionEventEnvelope).Assembly.GetType("Chummer.Run.Contracts.Relay.SessionOverlayEventDto") is null,
            "Chummer.Run.Contracts must not expose legacy session overlay wrappers.");
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

        if (!values.TryGetValue("ORACLE_ROOTS", out var oracleRootsValue))
        {
            throw new InvalidOperationException("Boundary manifest must declare ORACLE_ROOTS.");
        }

        if (!values.TryGetValue("RETIRED_ROOTS", out var retiredRootsValue))
        {
            throw new InvalidOperationException("Boundary manifest must declare RETIRED_ROOTS.");
        }

        var expectedHostedProjects = SplitManifestList(hostedProjects);
        var oracleRoots = SplitManifestList(oracleRootsValue);
        var retiredRoots = SplitManifestList(retiredRootsValue);

        var canonicalHostedProjects = new[]
            {
                "Chummer.Media.Contracts",
                "Chummer.Play.Contracts",
                "Chummer.Run.AI",
                "Chummer.Run.Api",
                "Chummer.Run.Contracts",
                "Chummer.Run.Identity",
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
                "Plugins/ChummerHub.Client",
                "Plugins/SamplePlugin",
                "TextblockConverter",
                "Translator"
            }
            .OrderBy(static entry => entry, StringComparer.Ordinal)
            .ToArray();

        VerificationAssert.True(
            expectedHostedProjects.SequenceEqual(canonicalHostedProjects, StringComparer.Ordinal),
            "Boundary manifest must keep the canonical hosted project set for identity, registry, relay/Spider/media orchestration, and hosted APIs.");
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
