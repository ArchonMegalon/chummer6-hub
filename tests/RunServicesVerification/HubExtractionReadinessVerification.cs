using System.IO;
using System.Reflection;
using System.Xml.Linq;

namespace RunServicesVerification;

internal static class HubExtractionReadinessVerification
{
    private static readonly string RepoRoot = ResolveRepoRoot();

    public static void Run()
    {
        VerifyRegistryBoundaryReadiness();
        VerifyMediaBoundaryReadiness();
        VerifyDesignMirrorReadiness();
        VerifyAcceptanceDocument();
        VerifyLegacyRootBoundaryMoves();
        VerifyMilestoneMapping();
    }

    private static void VerifyRegistryBoundaryReadiness()
    {
        VerificationAssert.True(
            !Directory.Exists(Path.Combine(RepoRoot, "Chummer.Run.Registry")),
            "Run-services must not keep the registry service source-owned after owner transfer to chummer6-hub-registry.");

        foreach (var retiredFile in new[]
                 {
                     Path.Combine(RepoRoot, "Chummer.Run.Contracts", "HubRegistryContracts.cs"),
                     Path.Combine(RepoRoot, "Chummer.Run.Contracts", "RegistryContracts.cs"),
                     Path.Combine(RepoRoot, "Chummer.Run.Contracts", "PublicationContracts.cs")
                 })
        {
            VerificationAssert.True(
                !File.Exists(retiredFile),
                $"Run-services must not keep retired local registry/publication contract shadows: {Path.GetFileName(retiredFile)}");
        }

        var registryProject = XDocument.Load(Path.Combine(RepoRoot, "..", "chummer-hub-registry", "Chummer.Run.Registry", "Chummer.Run.Registry.csproj"));
        var projectReferences = registryProject
            .Descendants("ProjectReference")
            .Select(static element => (string?)element.Attribute("Include"))
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Select(static value => value!)
            .ToArray();

        VerificationAssert.Equal(0, projectReferences.Length, "Chummer.Run.Registry should stop source-owning registry/publication DTOs through project references.");
        var assemblyReferences = registryProject
            .Descendants("Reference")
            .Select(static element => new
            {
                Include = (string?)element.Attribute("Include"),
                HintPath = (string?)element.Element("HintPath")
            })
            .Where(static entry => !string.IsNullOrWhiteSpace(entry.Include))
            .ToArray();

        VerificationAssert.True(
            assemblyReferences.Any(static entry =>
                string.Equals(entry.Include, "Chummer.Hub.Registry.Contracts", StringComparison.Ordinal)
                && string.Equals(entry.HintPath, @"..\Chummer.Hub.Registry.Contracts\bin\$(Configuration)\net10.0\Chummer.Hub.Registry.Contracts.dll", StringComparison.Ordinal)),
            "Chummer.Run.Registry should consume registry/publication DTOs through the sibling hub-registry owner package.");
        VerificationAssert.True(
            assemblyReferences.All(static entry => !string.Equals(entry.Include, "Chummer.Run.Contracts", StringComparison.Ordinal)),
            "Chummer.Run.Registry must not keep a local Chummer.Run.Contracts assembly seam for registry/publication ownership.");

        var runContractsAssembly = AppDomain.CurrentDomain.GetAssemblies()
            .FirstOrDefault(static assembly => string.Equals(assembly.GetName().Name, "Chummer.Run.Contracts", StringComparison.Ordinal))
            ?? TryLoadAssembly("Chummer.Run.Contracts");
        VerificationAssert.NotNull(runContractsAssembly, "RunServicesVerification should be able to load Chummer.Run.Contracts for boundary checks.");

        VerificationAssert.True(
            runContractsAssembly!.GetType("Chummer.Run.Contracts.Registry.HubArtifactCreateRequest") is null,
            "Chummer.Run.Contracts must not ship registry contract types after hub-registry owner transfer.");
        VerificationAssert.True(
            runContractsAssembly.GetType("Chummer.Run.Contracts.Publication.PublicationRecordResponse") is null,
            "Chummer.Run.Contracts must not ship publication contract types after hub-registry owner transfer.");

        var runApiAssembly = AppDomain.CurrentDomain.GetAssemblies()
            .FirstOrDefault(static assembly => string.Equals(assembly.GetName().Name, "Chummer.Run.Api", StringComparison.Ordinal))
            ?? TryLoadAssembly("Chummer.Run.Api");
        VerificationAssert.NotNull(runApiAssembly, "RunServicesVerification should be able to load Chummer.Run.Api for Hub readiness checks.");

        VerificationAssert.True(
            runApiAssembly!.GetType("Chummer.Run.Api.Controllers.PublicationsController") is null,
            "Chummer.Run.Api must stay free of publication controllers for hub-registry extraction readiness.");
        VerificationAssert.True(
            runApiAssembly.GetType("Chummer.Run.Api.Services.PublicationWorkflowService") is null,
            "Chummer.Run.Api must stay free of publication workflow ownership for hub-registry extraction readiness.");
    }

    private static void VerifyMediaBoundaryReadiness()
    {
        VerificationAssert.True(
            !Directory.Exists(Path.Combine(RepoRoot, "Chummer.Media.Contracts")),
            "Run-services must not keep a repo-local Chummer.Media.Contracts source project after media-factory owner transfer.");

        var mediaContractsAssembly = typeof(Chummer.Media.Contracts.AssetLifecyclePolicy).Assembly;
        var mediaContractsTypeNames = mediaContractsAssembly.GetTypes().Select(static type => type.Name).ToHashSet(StringComparer.Ordinal);

        foreach (var forbiddenMediaType in new[]
                 {
                     "PortraitForgeRequest",
                     "PortraitForgeResult",
                     "NewsBriefRequest",
                     "NewsBriefResult",
                     "ShadowfeedRequest",
                     "ShadowfeedResult",
                     "NpcVideoMessageRequest",
                     "NpcVideoMessageResult"
                 })
        {
            VerificationAssert.True(
                !mediaContractsTypeNames.Contains(forbiddenMediaType),
                $"Chummer.Media.Contracts must remain render-only and must not expose orchestration type '{forbiddenMediaType}'.");
        }

        var runContractsAssembly = typeof(Chummer.Run.Contracts.Media.NewsBriefRequest).Assembly;
        var runContractsTypeNames = runContractsAssembly.GetTypes().Select(static type => type.FullName ?? type.Name).ToHashSet(StringComparer.Ordinal);

        foreach (var forbiddenRunType in new[]
                 {
                     "Chummer.Run.Contracts.Media.AssetLifecyclePolicy",
                     "Chummer.Run.Contracts.Media.AssetLifecycleMutationRequest",
                     "Chummer.Run.Contracts.Media.AssetRenderResult",
                     "Chummer.Run.Contracts.Media.MediaRenderJobEnqueueRequest",
                     "Chummer.Run.Contracts.Media.MediaRenderJobStatus",
                     "Chummer.Run.Contracts.Media.PacketFactoryRequest",
                     "Chummer.Run.Contracts.Media.RouteCinemaRequest"
                 })
        {
            VerificationAssert.True(
                !runContractsTypeNames.Contains(forbiddenRunType),
                $"Chummer.Run.Contracts.Media must not regrow render-only ownership via '{forbiddenRunType}'.");
        }

        var mediaContractsProjectPath = Path.GetFullPath(Path.Combine(RepoRoot, "..", "..", "fleet", "repos", "chummer-media-factory", "src", "Chummer.Media.Contracts", "Chummer.Media.Contracts.csproj"));
        VerificationAssert.True(File.Exists(mediaContractsProjectPath), "Media-factory owner contracts project must exist.");
        var mediaContractsProject = XDocument.Load(mediaContractsProjectPath);
        VerificationAssert.True(
            !mediaContractsProject.Descendants("ProjectReference").Any(),
            "Chummer.Media.Contracts must remain dependency-light with no project references.");
        VerificationAssert.True(
            !mediaContractsProject.Descendants("PackageReference").Any(),
            "Chummer.Media.Contracts must remain dependency-light with no package references.");

        var runAiProject = XDocument.Load(Path.Combine(RepoRoot, "Chummer.Run.AI", "Chummer.Run.AI.csproj"));
        var mediaReference = runAiProject
            .Descendants("Reference")
            .Select(static element => new
            {
                Include = (string?)element.Attribute("Include"),
                HintPath = (string?)element.Element("HintPath")
            })
            .FirstOrDefault(static entry => string.Equals(entry.Include, "Chummer.Media.Contracts", StringComparison.Ordinal));
        VerificationAssert.NotNull(mediaReference, "Chummer.Run.AI must reference the media-factory owner contract assembly.");
        VerificationAssert.True(
            string.Equals(mediaReference!.HintPath, @"..\..\..\fleet\repos\chummer-media-factory\src\Chummer.Media.Contracts\bin\$(Configuration)\net10.0\Chummer.Media.Contracts.dll", StringComparison.Ordinal),
            "Chummer.Run.AI must consume Chummer.Media.Contracts through the sibling media-factory owner package.");

        var mediaRuntimeReference = runAiProject
            .Descendants("Reference")
            .Select(static element => new
            {
                Include = (string?)element.Attribute("Include"),
                HintPath = (string?)element.Element("HintPath")
            })
            .FirstOrDefault(static entry => string.Equals(entry.Include, "Chummer.Media.Factory.Runtime", StringComparison.Ordinal));
        VerificationAssert.NotNull(mediaRuntimeReference, "Chummer.Run.AI must reference the media-factory runtime assembly.");
        VerificationAssert.True(
            string.Equals(mediaRuntimeReference!.HintPath, @"..\..\..\fleet\repos\chummer-media-factory\src\Chummer.Media.Factory.Runtime\bin\$(Configuration)\net10.0\Chummer.Media.Factory.Runtime.dll", StringComparison.Ordinal),
            "Chummer.Run.AI must consume media execution through the sibling media-factory runtime assembly.");

        foreach (var retiredMediaService in new[]
                 {
                     Path.Combine(RepoRoot, "Chummer.Run.AI", "Services", "Assets", "AssetLifecycleService.cs"),
                     Path.Combine(RepoRoot, "Chummer.Run.AI", "Services", "Assets", "MediaRenderJobService.cs")
                 })
        {
            VerificationAssert.True(
                !File.Exists(retiredMediaService),
                $"Run-services must not keep retired local media execution ownership: {Path.GetFileName(retiredMediaService)}");
        }
    }

    private static void VerifyDesignMirrorReadiness()
    {
        VerifyMirrorFile(
            Path.Combine(RepoRoot, ".codex-design", "product", "README.md"),
            "Project Chummer");
        VerifyMirrorFile(
            Path.Combine(RepoRoot, ".codex-design", "repo", "IMPLEMENTATION_SCOPE.md"),
            "Hub implementation scope");
        VerifyMirrorFile(
            Path.Combine(RepoRoot, ".codex-design", "review", "REVIEW_CONTEXT.md"),
            "Review guidelines");
    }

    private static void VerifyAcceptanceDocument()
    {
        var acceptancePath = Path.Combine(RepoRoot, "docs", "HUB_EXTRACTION_ACCEPTANCE.md");
        VerificationAssert.True(File.Exists(acceptancePath), "Hub extraction acceptance document must exist.");

        var acceptanceText = File.ReadAllText(acceptancePath);
        foreach (var requiredToken in new[]
                 {
                     "WL-089",
                     "WL-207",
                     "WL-216",
                     "WL-217",
                     "WL-218",
                     "WL-219",
                     "WL-220",
                     "WL-228",
                     "WL-209",
                     "WL-210",
                     "WL-211",
                     "WL-212",
                     "A2",
                     "A3",
                     "C1b",
                     "D1",
                     "E2b",
                     "F1",
                     "WL-148",
                     "WL-149",
                     "WL-150",
                     "WL-151",
                     "WL-153",
                     "WL-155",
                     "WL-086",
                     "WL-118",
                     "WL-120",
                     "WL-145",
                     "WL-088",
                     "WL-095",
                     "WL-098",
                     "WL-102",
                     "WL-104",
                     "WL-111",
                     "WL-125",
                     "WL-137",
                     "WL-140",
                     "WL-085",
                     "4333",
                     "4338",
                     "4334",
                     "4339",
                     "11709",
                     "1926",
                     "2367",
                     "3948",
                     "4367",
                     "8667",
                     "21817",
                     "21818",
                     "53652",
                     "53653",
                     "53654",
                     "53655",
                     "8668",
                     "8697",
                     "8698",
                     "21924",
                     "2369",
                     "C2",
                     "R0",
                     "Chummer.Run.Registry",
                     "Chummer.Play.Contracts",
                     "Chummer.Media.Contracts",
                     "LEGACY_ROOT_SURFACE_INVENTORY.md",
                     "PublicationVerification.cs",
                     "CompatibilityVerification.cs",
                     "PipelineProjectionVerification.cs",
                     "StateStoreBackupVerification.cs",
                     "RuntimeBundleVerification.cs",
                     "HOSTED_BOUNDARY.md",
                     "hosted-boundary.manifest",
                     ".codex-design/product/README.md",
                     ".codex-design/repo/IMPLEMENTATION_SCOPE.md",
                     ".codex-design/review/REVIEW_CONTEXT.md",
                     "scripts/ai/run_services_smoke.sh",
                     "scripts/ai/run_services_verification.sh",
                     "PROGRAM_MILESTONES.yaml",
                     "scripts/ai/verify.sh"
                 })
        {
            VerificationAssert.True(
                acceptanceText.Contains(requiredToken, StringComparison.Ordinal),
                $"Hub extraction acceptance document must mention '{requiredToken}'.");
        }
    }

    private static void VerifyLegacyRootBoundaryMoves()
    {
        var legacyDcprojPath = Path.Combine(RepoRoot, "legacy", "tooling", "vs-compose", "docker-compose.dcproj");
        var legacySettingsPath = Path.Combine(RepoRoot, "legacy", "interoperability", "settings", "README.txt");
        var legacyArchitecturePath = Path.Combine(RepoRoot, "legacy", "architecture-archive", "chummer-run-services.design.v2.md");
        var rootDcprojPath = Path.Combine(RepoRoot, "docker-compose.dcproj");
        var rootSettingsPath = Path.Combine(RepoRoot, "settings");
        var rootArchitecturePath = Path.Combine(RepoRoot, "chummer-run-services.design.v2.md");

        VerificationAssert.True(
            File.Exists(legacyDcprojPath),
            "Legacy tooling boundary must keep docker-compose.dcproj under legacy/tooling/vs-compose.");
        VerificationAssert.True(
            File.Exists(legacySettingsPath),
            "Legacy interoperability boundary must keep settings assets under legacy/interoperability/settings.");
        VerificationAssert.True(
            !File.Exists(rootDcprojPath),
            "Root hosted topology must not keep docker-compose.dcproj at repo root.");
        VerificationAssert.True(
            !Directory.Exists(rootSettingsPath),
            "Root hosted topology must not keep settings/ at repo root.");
        VerificationAssert.True(
            File.Exists(legacyArchitecturePath),
            "Legacy architecture boundary must keep chummer-run-services.design.v2.md under legacy/architecture-archive.");
        VerificationAssert.True(
            !File.Exists(rootArchitecturePath),
            "Root hosted topology must not keep chummer-run-services.design.v2.md at repo root.");

        var dcprojText = File.ReadAllText(legacyDcprojPath);
        VerificationAssert.True(
            dcprojText.Contains(@"..\docker\docker-compose.yml", StringComparison.Ordinal),
            "Legacy docker-compose.dcproj must bridge to legacy/tooling/docker/docker-compose.yml.");
        VerificationAssert.True(
            dcprojText.Contains(@"..\..\..\.dockerignore", StringComparison.Ordinal),
            "Legacy docker-compose.dcproj must bridge to the root .dockerignore path.");
    }

    private static void VerifyMilestoneMapping()
    {
        var milestonePath = Path.Combine(RepoRoot, ".codex-design", "product", "PROGRAM_MILESTONES.yaml");
        VerificationAssert.True(File.Exists(milestonePath), "Program milestones mirror must exist for Hub acceptance mapping.");

        var milestoneText = File.ReadAllText(milestonePath);
        var hasRepoExecutionTracks = milestoneText.Contains("repo_execution_tracks:", StringComparison.Ordinal);
        var hasExecutableQueue = milestoneText.Contains("executable_queue:", StringComparison.Ordinal);
        VerificationAssert.True(
            hasRepoExecutionTracks || hasExecutableQueue,
            "Program milestones must retain either repo execution tracks or an executable queue.");

        if (hasExecutableQueue)
        {
            VerifyExecutableQueueMapping(milestoneText);
            return;
        }

        var milestoneLines = File.ReadAllLines(milestonePath);
        var p0Section = ExtractHubMilestoneTrack(milestoneLines, "P0");
        var p1Section = ExtractHubMilestoneTrack(milestoneLines, "P1");
        var p3Section = ExtractHubMilestoneTrack(milestoneLines, "P3");

        AssertSectionContainsTokens(
            p0Section,
            "P0",
            "parent_milestone: C0",
            "play_api_vnext",
            "WL-085",
            "WL-089",
            "WL-121",
            "WL-131",
            "WL-148",
            "WL-149",
            "WL-150",
            "WL-151",
            "WL-152",
            "WL-153",
            "WL-155",
            "WL-161",
            "WL-086",
            "WL-118",
            "WL-120",
            "WL-145",
            "WL-088",
            "WL-095",
            "WL-098",
            "WL-102",
            "WL-104",
            "WL-111",
            "WL-125",
            "WL-137",
            "WL-140",
            ".codex-design/product/README.md",
            ".codex-design/repo/IMPLEMENTATION_SCOPE.md",
            ".codex-design/review/REVIEW_CONTEXT.md");
        AssertSectionContainsCandidate(p0Section, "P0", 25, "project.uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 11709, "project.design_mirror_missing_or_stale");
        AssertSectionContainsCandidate(p0Section, "P0", 4333, "project.uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 4338, "project.queue_exhausted_with_uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 4334, "project.uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 4339, "project.queue_exhausted_with_uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 28, "project.milestone_coverage_incomplete");
        AssertSectionContainsCandidate(p0Section, "P0", 1926, "project.ai_platform_contract_catchall");
        AssertSectionContainsCandidate(p0Section, "P0", 3948, "project.session_overlay_compat_shim_present");
        AssertSectionContainsCandidate(p0Section, "P0", 4367, "project.hub_legacy_host_clutter_present");
        AssertSectionContainsCandidate(p0Section, "P0", 21818, "project.uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 53655, "project.queue_exhausted_with_uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 8667, "project.uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 21817, "project.uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 53652, "project.queue_exhausted_with_uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 53653, "project.queue_exhausted_with_uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 53654, "project.queue_exhausted_with_uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 8668, "project.uncovered_scope");
        AssertSectionContainsCandidate(p0Section, "P0", 8697, "project.media_contracts_mix_render_and_narrative");
        AssertSectionContainsCandidate(p0Section, "P0", 8698, "project.media_contracts_mix_render_and_narrative");
        AssertSectionContainsCandidate(p0Section, "P0", 21924, "project.media_contracts_mix_render_and_narrative");

        AssertSectionContainsTokens(
            p1Section,
            "P1",
            "parent_milestone: C0",
            "WL-090",
            "WL-152");
        AssertSectionContainsCandidate(p1Section, "P1", 2367, "project.queue_exhausted_with_uncovered_scope");

        AssertSectionContainsTokens(
            p3Section,
            "P3",
            "parent_milestone: C0",
            "WL-092",
            "2369");
        AssertSectionContainsCandidate(p3Section, "P3", 2369, "project.queue_exhausted_with_uncovered_scope");
    }

    private static void VerifyExecutableQueueMapping(string milestoneText)
    {
        AssertExecutableQueueItem(
            milestoneText,
            "WL-D007",
            "status: done",
            "backlog: products/chummer/sync/REVIEW_TEMPLATE_MIRROR_BACKLOG.md");
        AssertExecutableQueueItem(
            milestoneText,
            "WL-D008",
            "status: done",
            "backlog: products/chummer/sync/LOCAL_MIRROR_PUBLISH_BACKLOG.md");
        AssertExecutableQueueItem(
            milestoneText,
            "WL-D009",
            "status: done",
            "backlog: products/chummer/sync/TRUTH_MAINTENANCE_BACKLOG.md");
        AssertExecutableQueueItem(
            milestoneText,
            "WL-D010",
            "status: done",
            "backlog: products/chummer/sync/REVIEW_TEMPLATE_MIRROR_UNBLOCK_BACKLOG.md");
        AssertExecutableQueueItem(
            milestoneText,
            "WL-D011",
            "status: done",
            "backlog: products/chummer/sync/REVIEW_TEMPLATE_ACCESS_UNBLOCK_BACKLOG.md");
    }

    private static void AssertExecutableQueueItem(string text, string itemId, params string[] requiredTokens)
    {
        var section = ExtractExecutableQueueItemSection(text, itemId);

        foreach (var token in requiredTokens)
        {
            VerificationAssert.True(
                section.Contains(token, StringComparison.Ordinal),
                $"Program milestones executable queue item '{itemId}' must retain token '{token}'.");
        }
    }

    private static string ExtractExecutableQueueItemSection(string text, string itemId)
    {
        var itemStart = text.IndexOf($"- id: {itemId}", StringComparison.Ordinal);
        VerificationAssert.True(itemStart >= 0, $"Program milestones executable queue must contain '{itemId}'.");

        var nextItem = text.IndexOf(Environment.NewLine + "- id: ", itemStart + 1, StringComparison.Ordinal);
        return nextItem >= 0 ? text[itemStart..nextItem] : text[itemStart..];
    }

    private static void AssertSectionContainsTokens(string sectionText, string trackId, params string[] requiredTokens)
    {
        foreach (var requiredToken in requiredTokens)
        {
            VerificationAssert.True(
                sectionText.Contains(requiredToken, StringComparison.Ordinal),
                $"Program milestones Hub track '{trackId}' must retain token '{requiredToken}'.");
        }
    }

    private static void AssertSectionContainsCandidate(string sectionText, string trackId, int candidateId, string findingKey)
    {
        VerificationAssert.True(
            sectionText.Contains($"candidate_id: {candidateId}", StringComparison.Ordinal),
            $"Program milestones Hub track '{trackId}' must map auditor candidate '{candidateId}'.");
        VerificationAssert.True(
            sectionText.Contains($"finding_key: {findingKey}", StringComparison.Ordinal),
            $"Program milestones Hub track '{trackId}' must retain finding key '{findingKey}' for candidate '{candidateId}'.");
    }

    private static string ExtractHubMilestoneTrack(IReadOnlyList<string> lines, string trackId)
    {
        var hubProjectIndex = -1;
        for (var index = 0; index < lines.Count; index++)
        {
            if (string.Equals(lines[index].Trim(), "- project: hub", StringComparison.Ordinal))
            {
                hubProjectIndex = index;
                break;
            }
        }

        VerificationAssert.True(hubProjectIndex >= 0, "Program milestones must define the Hub execution track.");

        var startIndex = -1;
        for (var index = hubProjectIndex + 1; index < lines.Count; index++)
        {
            if (lines[index].StartsWith("- project: ", StringComparison.Ordinal))
            {
                break;
            }

            if (string.Equals(lines[index].Trim(), $"- id: {trackId}", StringComparison.Ordinal))
            {
                startIndex = index;
                break;
            }
        }

        VerificationAssert.True(startIndex >= 0, $"Program milestones must define Hub track '{trackId}'.");

        var sectionLines = new List<string>();
        for (var index = startIndex; index < lines.Count; index++)
        {
            if (index > startIndex && lines[index].StartsWith("  - id: ", StringComparison.Ordinal))
            {
                break;
            }

            if (lines[index].StartsWith("- project: ", StringComparison.Ordinal))
            {
                break;
            }

            sectionLines.Add(lines[index]);
        }

        return string.Join(Environment.NewLine, sectionLines);
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

    private static void VerifyMirrorFile(string path, string requiredToken)
    {
        VerificationAssert.True(File.Exists(path), $"Required design mirror file '{path}' must exist.");

        var text = File.ReadAllText(path);
        VerificationAssert.True(
            text.Contains(requiredToken, StringComparison.Ordinal),
            $"Design mirror file '{path}' must retain token '{requiredToken}'.");
    }

    private static string ResolveRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "Chummer.Run.sln")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new InvalidOperationException("Unable to locate repository root from test host.");
    }
}
