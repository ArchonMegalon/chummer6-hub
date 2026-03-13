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
        VerifyMilestoneMapping();
    }

    private static void VerifyRegistryBoundaryReadiness()
    {
        var registryProject = XDocument.Load(Path.Combine(RepoRoot, "Chummer.Run.Registry", "Chummer.Run.Registry.csproj"));
        var projectReferences = registryProject
            .Descendants("ProjectReference")
            .Select(static element => (string?)element.Attribute("Include"))
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Select(static value => value!)
            .ToArray();

        VerificationAssert.Equal(1, projectReferences.Length, "Chummer.Run.Registry should keep a single project-reference seam while Hub extraction is in progress.");
        VerificationAssert.True(
            projectReferences[0].EndsWith(@"Chummer.Run.Contracts\Chummer.Run.Contracts.csproj", StringComparison.Ordinal),
            "Chummer.Run.Registry should consume registry/publication DTOs only through Chummer.Run.Contracts.");

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

        var mediaContractsProject = XDocument.Load(Path.Combine(RepoRoot, "Chummer.Media.Contracts", "Chummer.Media.Contracts.csproj"));
        VerificationAssert.True(
            !mediaContractsProject.Descendants("ProjectReference").Any(),
            "Chummer.Media.Contracts must remain dependency-light with no project references.");
        VerificationAssert.True(
            !mediaContractsProject.Descendants("PackageReference").Any(),
            "Chummer.Media.Contracts must remain dependency-light with no package references.");
    }

    private static void VerifyDesignMirrorReadiness()
    {
        VerifyMirrorFile(
            Path.Combine(RepoRoot, ".codex-design", "product", "README.md"),
            "Project Chummer");
        VerifyMirrorFile(
            Path.Combine(RepoRoot, ".codex-design", "repo", "IMPLEMENTATION_SCOPE.md"),
            "Run-services implementation scope");
        VerifyMirrorFile(
            Path.Combine(RepoRoot, ".codex-design", "review", "REVIEW_CONTEXT.md"),
            "Generic review checklist");
    }

    private static void VerifyAcceptanceDocument()
    {
        var acceptancePath = Path.Combine(RepoRoot, "docs", "HUB_EXTRACTION_ACCEPTANCE.md");
        VerificationAssert.True(File.Exists(acceptancePath), "Hub extraction acceptance document must exist.");

        var acceptanceText = File.ReadAllText(acceptancePath);
        foreach (var requiredToken in new[]
                 {
                     "WL-089",
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
                     "3948",
                     "4367",
                     "8667",
                     "21817",
                     "53652",
                     "53653",
                     "53654",
                     "8668",
                     "8697",
                     "8698",
                     "21924",
                     "2369",
                     "Chummer.Run.Registry",
                     "Chummer.Play.Contracts",
                     "Chummer.Media.Contracts",
                     "PublicationVerification.cs",
                     "CompatibilityVerification.cs",
                     "HOSTED_BOUNDARY.md",
                     "hosted-boundary.manifest",
                     ".codex-design/product/README.md",
                     ".codex-design/repo/IMPLEMENTATION_SCOPE.md",
                     ".codex-design/review/REVIEW_CONTEXT.md",
                     "PROGRAM_MILESTONES.yaml",
                     "scripts/ai/verify.sh"
                 })
        {
            VerificationAssert.True(
                acceptanceText.Contains(requiredToken, StringComparison.Ordinal),
                $"Hub extraction acceptance document must mention '{requiredToken}'.");
        }
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
            "status: in_progress",
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
