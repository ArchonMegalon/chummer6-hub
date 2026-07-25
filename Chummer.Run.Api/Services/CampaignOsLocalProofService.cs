using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Services;

public sealed class CampaignOsLocalProofService
{
    private const string ContractName = "chummer6-hub.campaign_os_local_proof";
    private const int ContractVersion = 3;
    private const string PassedStatus = "passed";
    private const string ProofKind = "materializer_owned_executed_smoke_receipt";
    private const string InvocationId = "run_services_smoke";
    private const string InvocationOwner = "campaign_os_local_proof_materializer";
    private const string DependencyMode = "restore_free_with_locally_closed_package_inputs";
    private const string DotnetHostPath = "/usr/bin/dotnet";
    private const string AssemblyFileName = "RunServicesSmoke.dll";
    private const string DefaultLocalProofRelativePath = ".codex-studio/published/HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json";
    private const string PublicCanonRootKey = "CHUMMER_PUBLIC_CANON_ROOT";
    private const string LocalProofFileKey = "CHUMMER_HUB_CAMPAIGN_OS_LOCAL_PROOF_FILE";
    private const int MaximumProofBytes = 2 * 1024 * 1024;
    private const int MaximumInputBytes = 128 * 1024 * 1024;
    private const int MaximumCheckpointBytes = 64 * 1024;
    private const int MaximumTreeFiles = 200_000;
    private const long MaximumTreeBytes = 8L * 1024 * 1024 * 1024;
    private const int TreeFormatVersion = 1;
    private static readonly TimeSpan MaximumAge = TimeSpan.FromHours(24);
    private static readonly TimeSpan MaximumFutureSkew = TimeSpan.FromMinutes(5);
    private static readonly string[] RootProperties =
    [
        "contract_name", "contract_version", "status", "proof_kind", "run_id", "started_at", "completed_at",
        "generated_at", "expires_at", "invocation", "inputs", "execution", "journeys", "summary"
    ];
    private static readonly string[] InputProperties =
    [
        "source", "journey_spec", "runner", "prepare_helper", "environment_helper", "cleanroom_builder",
        "registry_global_usings", "materializer", "contract_module", "dotnet_host", "csc", "assembly"
    ];
    private static readonly (string Key, string Path)[] FileInputs =
    [
        ("source", "tests/RunServicesSmoke/Program.cs"),
        ("journey_spec", ".codex-design/product/GOLDEN_JOURNEY_RELEASE_GATES.yaml"),
        ("runner", "scripts/ai/run_services_smoke.sh"),
        ("prepare_helper", "scripts/ai/prepare_run_services_smoke.sh"),
        ("environment_helper", "scripts/ai/_env.sh"),
        ("cleanroom_builder", "scripts/ai/build_r1_cleanroom.sh"),
        ("registry_global_usings", "../chummer-hub-registry/Chummer.Run.Registry/GlobalUsings.RegistryContracts.cs"),
        ("materializer", "scripts/materialize_campaign_os_local_proof.py"),
        ("contract_module", "scripts/campaign_os_local_proof_v3.py")
    ];
    private static readonly string[] JourneyIds =
    [
        "install_claim_restore_continue",
        "build_explain_publish",
        "campaign_session_recover_recap",
        "recover_from_sync_conflict",
        "report_cluster_release_notify",
        "organize_community_and_close_loop"
    ];
    private static readonly string[] RuntimeManifestPaths =
    [
        "Chummer.Campaign.Contracts.dll",
        "Chummer.Control.Contracts.dll",
        "Chummer.Engine.Contracts.dll",
        "Chummer.Hub.Registry.Contracts.dll",
        "Chummer.Media.Contracts.dll",
        "Chummer.Media.Factory.Runtime.dll",
        "Chummer.Play.Contracts.dll",
        "Chummer.Run.AI.dll",
        "Chummer.Run.Api.dll",
        "Chummer.Run.Contracts.dll",
        "Chummer.Run.Identity.dll",
        "Chummer.Run.Registry.dll",
        "RunServicesSmoke.dll",
        "RunServicesSmoke.runtimeconfig.json",
        "YamlDotNet.dll",
        "toolchain/csc.dll",
        "toolchain/dotnet"
    ];
    private static readonly string[] ExecutionProperties =
    [
        "phase", "failure_reason",
        "candidate_source_build_inputs_before", "candidate_source_build_inputs_after",
        "staged_candidate_inputs_before", "staged_candidate_inputs_after",
        "managed_dotnet_closure_before", "managed_dotnet_closure_after",
        "runtime_manifest_before", "runtime_manifest_after", "checkpoint_log", "runtime_checkpoints",
        "candidate_source_build_inputs_stable", "staged_candidate_inputs_stable",
        "managed_dotnet_closure_stable", "runtime_closure_stable", "closure_stable"
    ];
    private static readonly string[] ProjectRoots =
    [
        "../chummer-core-engine/Chummer.Contracts",
        "../chummer-hub-registry/Chummer.Hub.Registry.Contracts",
        "../chummer-hub-registry/Chummer.Run.Registry",
        "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts",
        "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime",
        "Chummer.Play.Contracts",
        "Chummer.Campaign.Contracts",
        "Chummer.Control.Contracts",
        "Chummer.Run.Contracts",
        "Chummer.World.Contracts",
        "Chummer.Run.Api",
        "Chummer.Run.Identity",
        "Chummer.Run.AI"
    ];
    private static readonly (string Source, string Staged)[] RuntimeDataRoots =
    [
        (".codex-design/product", ".codex-design/product"),
        ("../chummer-design/products/chummer", "products/chummer")
    ];
    private static readonly string[] ManagedComponentRoots =
    [
        "hostfxr", "Microsoft.NETCore.App", "Microsoft.AspNetCore.App",
        "Microsoft.NETCore.App.Ref", "Microsoft.AspNetCore.App.Ref", "sdk"
    ];
    private static readonly Regex SpecVersionPattern = new(
        "^version:\\s*([0-9]+)\\s*$",
        RegexOptions.CultureInvariant);
    private static readonly Regex SpecJourneyPattern = new(
        "^  - id:\\s*([a-z0-9_]+)\\s*$",
        RegexOptions.CultureInvariant);
    private static readonly Regex SdkVersionPattern = new(
        "^[0-9A-Za-z._-]+$",
        RegexOptions.CultureInvariant);
    private readonly IConfiguration _configuration;
    private readonly TimeProvider _timeProvider;
    private readonly ICampaignOsClosureProvider _closureProvider;

    public CampaignOsLocalProofService(IConfiguration configuration)
        : this(configuration, TimeProvider.System)
    {
    }

    public CampaignOsLocalProofService(IConfiguration configuration, TimeProvider timeProvider)
        : this(configuration, timeProvider, FileSystemCampaignOsClosureProvider.Instance)
    {
    }

    internal CampaignOsLocalProofService(
        IConfiguration configuration,
        TimeProvider timeProvider,
        ICampaignOsClosureProvider closureProvider)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        _closureProvider = closureProvider ?? throw new ArgumentNullException(nameof(closureProvider));
    }

    public CampaignOsLocalProofSnapshot? LoadProof() => Evaluate().Snapshot;

    public CampaignOsLocalProofEvaluation Evaluate()
    {
        var resolution = ResolveLocalProofPath();
        if (resolution.Error is not null)
        {
            return Invalid(resolution.Error);
        }

        var read = ReadStableFile(resolution.Path!, MaximumProofBytes);
        if (read.Error is not null)
        {
            return Invalid(read.Error);
        }

        try
        {
            using var document = JsonDocument.Parse(
                read.Bytes!,
                new JsonDocumentOptions
                {
                    AllowTrailingCommas = false,
                    CommentHandling = JsonCommentHandling.Disallow,
                    MaxDepth = 16
                });

            if (HasDuplicateProperty(document.RootElement))
            {
                return Invalid("proof_duplicate_property");
            }

            return Validate(document.RootElement, resolution.CanonRoot!);
        }
        catch (JsonException)
        {
            return Invalid("proof_json_invalid");
        }
    }

    private CampaignOsLocalProofEvaluation Validate(JsonElement root, string canonRoot)
    {
        if (!HasExactProperties(root, RootProperties))
        {
            return Invalid("proof_schema_invalid");
        }

        if (!TryGetString(root, "contract_name", out var contractName)
            || !string.Equals(contractName, ContractName, StringComparison.Ordinal)
            || !TryGetInt32(root, "contract_version", out var contractVersion)
            || contractVersion != ContractVersion)
        {
            return Invalid("proof_contract_mismatch");
        }

        if (!TryGetString(root, "status", out var status)
            || !string.Equals(status, PassedStatus, StringComparison.Ordinal))
        {
            return Invalid("proof_status_not_passed");
        }

        if (!TryGetString(root, "proof_kind", out var proofKind)
            || !string.Equals(proofKind, ProofKind, StringComparison.Ordinal)
            || !TryGetString(root, "run_id", out var runId)
            || !IsCanonicalUuidV4(runId))
        {
            return Invalid("proof_identity_invalid");
        }

        if (!TryGetUtcTimestamp(root, "started_at", out var startedAt)
            || !TryGetUtcTimestamp(root, "completed_at", out var completedAt)
            || !TryGetUtcTimestamp(root, "generated_at", out var generatedAt)
            || !TryGetUtcTimestamp(root, "expires_at", out var expiresAt)
            || startedAt > completedAt
            || generatedAt != completedAt
            || !TryAdd(completedAt, MaximumAge, out var expectedExpiresAt)
            || expiresAt != expectedExpiresAt)
        {
            return Invalid("proof_timestamp_invalid");
        }

        var now = _timeProvider.GetUtcNow();
        if (!TryAdd(now, MaximumFutureSkew, out var latestAcceptedTime)
            || startedAt > latestAcceptedTime
            || completedAt > latestAcceptedTime
            || generatedAt > latestAcceptedTime)
        {
            return Invalid("proof_from_future");
        }

        if (now - generatedAt > MaximumAge)
        {
            return Invalid("proof_stale");
        }

        if (expiresAt <= now)
        {
            return Invalid("proof_expired");
        }

        if (!ValidateInvocation(root.GetProperty("invocation")))
        {
            return Invalid("proof_invocation_invalid");
        }

        if (!ValidateInputs(root.GetProperty("inputs"), canonRoot, out var inputs))
        {
            return Invalid("proof_inputs_invalid");
        }

        if (!ValidateExecution(root.GetProperty("execution"), canonRoot, runId, inputs, out var execution))
        {
            return Invalid("proof_execution_invalid");
        }

        if (!ValidateJourneys(root.GetProperty("journeys"), out var journeys))
        {
            return Invalid("proof_journeys_invalid");
        }

        if (!ValidateSummary(root.GetProperty("summary")))
        {
            return Invalid("proof_summary_invalid");
        }

        var snapshot = new CampaignOsLocalProofSnapshot(
            Status: status,
            ContractVersion: contractVersion,
            RunId: runId,
            StartedAt: startedAt,
            CompletedAt: completedAt,
            GeneratedAt: generatedAt,
            ExpiresAt: expiresAt,
            ProofKind: proofKind,
            SourceFile: inputs.Source.Path,
            JourneysPassed: Array.AsReadOnly(journeys),
            Inputs: inputs,
            Execution: execution);
        return new CampaignOsLocalProofEvaluation(true, "proof_valid", snapshot);
    }

    private static bool ValidateInvocation(JsonElement invocation)
    {
        return HasExactProperties(invocation, ["id", "owner", "dependency_mode", "prepare_exit_code", "runner_exit_code"])
               && TryGetString(invocation, "id", out var id)
               && string.Equals(id, InvocationId, StringComparison.Ordinal)
               && TryGetString(invocation, "owner", out var owner)
               && string.Equals(owner, InvocationOwner, StringComparison.Ordinal)
               && TryGetString(invocation, "dependency_mode", out var dependencyMode)
               && string.Equals(dependencyMode, DependencyMode, StringComparison.Ordinal)
               && TryGetInt32(invocation, "prepare_exit_code", out var prepareExitCode)
               && prepareExitCode == 0
               && TryGetInt32(invocation, "runner_exit_code", out var runnerExitCode)
               && runnerExitCode == 0;
    }

    private static bool ValidateInputs(
        JsonElement inputsElement,
        string canonRoot,
        out CampaignOsLocalProofInputs inputs)
    {
        inputs = default!;
        if (!HasExactProperties(inputsElement, InputProperties))
        {
            return false;
        }

        var identities = new Dictionary<string, CampaignOsFileIdentity>(StringComparer.Ordinal);
        foreach (var (key, expectedPath) in FileInputs)
        {
            if (!TryReadFileIdentity(
                    inputsElement.GetProperty(key),
                    canonRoot,
                    expectedPath,
                    key == "journey_spec",
                    out var identity,
                    out var currentBytes)
                || (key == "journey_spec" && !ValidateJourneySpec(currentBytes)))
            {
                return false;
            }

            identities.Add(key, identity);
        }

        if (!TryReadToolchainIdentities(
                inputsElement.GetProperty("dotnet_host"),
                inputsElement.GetProperty("csc"),
                out var dotnetHost,
                out var csc))
        {
            return false;
        }

        var assemblyElement = inputsElement.GetProperty("assembly");
        if (!HasExactProperties(assemblyElement, ["file_name", "sha256", "size_bytes"])
            || !TryGetString(assemblyElement, "file_name", out var assemblyFileName)
            || !string.Equals(assemblyFileName, AssemblyFileName, StringComparison.Ordinal)
            || !TryGetString(assemblyElement, "sha256", out var assemblySha256)
            || !IsLowerHexSha256(assemblySha256)
            || !TryGetInt64(assemblyElement, "size_bytes", out var assemblySize)
            || assemblySize <= 0
            || assemblySize > MaximumInputBytes)
        {
            return false;
        }

        inputs = new CampaignOsLocalProofInputs(
            identities["source"],
            identities["journey_spec"],
            identities["runner"],
            identities["prepare_helper"],
            identities["environment_helper"],
            identities["cleanroom_builder"],
            identities["registry_global_usings"],
            identities["materializer"],
            identities["contract_module"],
            dotnetHost,
            csc,
            new CampaignOsAssemblyIdentity(assemblyFileName, assemblySha256, assemblySize));
        return true;
    }

    private static bool TryReadFileIdentity(
        JsonElement element,
        string canonRoot,
        string expectedPath,
        bool includesVersion,
        out CampaignOsFileIdentity identity,
        out byte[] currentBytes)
    {
        identity = default!;
        currentBytes = [];
        var expectedProperties = includesVersion
            ? new[] { "path", "sha256", "size_bytes", "version" }
            : new[] { "path", "sha256", "size_bytes" };
        if (!HasExactProperties(element, expectedProperties)
            || !TryGetString(element, "path", out var path)
            || !string.Equals(path, expectedPath, StringComparison.Ordinal)
            || !TryGetString(element, "sha256", out var sha256)
            || !IsLowerHexSha256(sha256)
            || !TryGetInt64(element, "size_bytes", out var sizeBytes)
            || sizeBytes <= 0
            || (includesVersion && (!TryGetInt32(element, "version", out var version) || version != 1)))
        {
            return false;
        }

        identity = new CampaignOsFileIdentity(path, sha256, sizeBytes);
        var inputPath = Path.GetFullPath(Path.Combine(
            canonRoot,
            expectedPath.Replace('/', Path.DirectorySeparatorChar)));
        var currentInput = ReadStableFile(inputPath, MaximumInputBytes);
        if (currentInput.Error is not null
            || currentInput.Bytes is null
            || currentInput.Bytes.LongLength != sizeBytes)
        {
            return false;
        }

        var currentSha256 = Convert.ToHexString(SHA256.HashData(currentInput.Bytes)).ToLowerInvariant();
        if (!string.Equals(currentSha256, sha256, StringComparison.Ordinal))
        {
            return false;
        }

        currentBytes = currentInput.Bytes;
        return true;
    }

    private static bool TryReadToolchainIdentities(
        JsonElement dotnetElement,
        JsonElement cscElement,
        out CampaignOsDotnetIdentity dotnetIdentity,
        out CampaignOsFileIdentity cscIdentity)
    {
        dotnetIdentity = default!;
        cscIdentity = default!;
        if (!HasExactProperties(dotnetElement, ["path", "resolved_path", "sha256", "size_bytes"])
            || !TryGetString(dotnetElement, "path", out var dotnetPath)
            || !string.Equals(dotnetPath, DotnetHostPath, StringComparison.Ordinal)
            || !TryGetString(dotnetElement, "resolved_path", out var resolvedPath)
            || !Path.IsPathFullyQualified(resolvedPath)
            || !TryGetString(dotnetElement, "sha256", out var dotnetSha256)
            || !IsLowerHexSha256(dotnetSha256)
            || !TryGetInt64(dotnetElement, "size_bytes", out var dotnetSize)
            || dotnetSize <= 0
            || dotnetSize > MaximumInputBytes)
        {
            return false;
        }

        string currentResolvedPath;
        try
        {
            var dotnetFile = new FileInfo(DotnetHostPath);
            var resolved = dotnetFile.ResolveLinkTarget(returnFinalTarget: true);
            currentResolvedPath = Path.GetFullPath(resolved?.FullName ?? dotnetFile.FullName);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return false;
        }

        var currentDotnet = ReadStableFile(currentResolvedPath, MaximumInputBytes);
        if (!string.Equals(resolvedPath, currentResolvedPath, StringComparison.Ordinal)
            || currentDotnet.Error is not null
            || currentDotnet.Bytes is null
            || currentDotnet.Bytes.LongLength != dotnetSize
            || !string.Equals(Sha256(currentDotnet.Bytes), dotnetSha256, StringComparison.Ordinal))
        {
            return false;
        }

        if (!HasExactProperties(cscElement, ["path", "sha256", "size_bytes"])
            || !TryGetString(cscElement, "path", out var cscPath)
            || !Path.IsPathFullyQualified(cscPath)
            || !TryGetString(cscElement, "sha256", out var cscSha256)
            || !IsLowerHexSha256(cscSha256)
            || !TryGetInt64(cscElement, "size_bytes", out var cscSize)
            || cscSize <= 0
            || cscSize > MaximumInputBytes)
        {
            return false;
        }

        string currentCscPath;
        try
        {
            currentCscPath = Path.GetFullPath(cscPath);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return false;
        }

        var currentCsc = ReadStableFile(currentCscPath, MaximumInputBytes);
        if (currentCsc.Error is not null
            || currentCsc.Bytes is null
            || currentCsc.Bytes.LongLength != cscSize
            || !string.Equals(Sha256(currentCsc.Bytes), cscSha256, StringComparison.Ordinal))
        {
            return false;
        }

        dotnetIdentity = new CampaignOsDotnetIdentity(dotnetPath, resolvedPath, dotnetSha256, dotnetSize);
        cscIdentity = new CampaignOsFileIdentity(cscPath, cscSha256, cscSize);
        return true;
    }

    private static bool ValidateJourneySpec(byte[] bytes)
    {
        if (!TryDecodeUtf8(bytes, out var spec))
        {
            return false;
        }

        var versions = new List<int>();
        var journeys = new List<string>();
        var inJourneyGates = false;
        var sectionCount = 0;
        using var reader = new StringReader(spec);
        while (reader.ReadLine() is { } line)
        {
            var versionMatch = SpecVersionPattern.Match(line);
            if (versionMatch.Success && int.TryParse(versionMatch.Groups[1].Value, out var version))
            {
                versions.Add(version);
            }

            if (string.Equals(line, "journey_gates:", StringComparison.Ordinal))
            {
                sectionCount++;
                inJourneyGates = true;
                continue;
            }

            if (inJourneyGates)
            {
                var journeyMatch = SpecJourneyPattern.Match(line);
                if (journeyMatch.Success)
                {
                    journeys.Add(journeyMatch.Groups[1].Value);
                }
            }
        }

        return sectionCount == 1
               && versions.SequenceEqual([1])
               && journeys.SequenceEqual(JourneyIds, StringComparer.Ordinal);
    }

    private bool ValidateExecution(
        JsonElement executionElement,
        string canonRoot,
        string runId,
        CampaignOsLocalProofInputs inputs,
        out CampaignOsExecutionSnapshot execution)
    {
        execution = default!;
        if (!HasExactProperties(executionElement, ExecutionProperties)
            || !TryGetString(executionElement, "phase", out var phase)
            || !string.Equals(phase, "verified", StringComparison.Ordinal)
            || executionElement.GetProperty("failure_reason").ValueKind != JsonValueKind.Null
            || executionElement.GetProperty("candidate_source_build_inputs_stable").ValueKind is not JsonValueKind.True
            || executionElement.GetProperty("staged_candidate_inputs_stable").ValueKind is not JsonValueKind.True
            || executionElement.GetProperty("managed_dotnet_closure_stable").ValueKind is not JsonValueKind.True
            || executionElement.GetProperty("runtime_closure_stable").ValueKind is not JsonValueKind.True
            || executionElement.GetProperty("closure_stable").ValueKind is not JsonValueKind.True)
        {
            return false;
        }

        var candidateBefore = executionElement.GetProperty("candidate_source_build_inputs_before");
        var candidateAfter = executionElement.GetProperty("candidate_source_build_inputs_after");
        var stagedBefore = executionElement.GetProperty("staged_candidate_inputs_before");
        var stagedAfter = executionElement.GetProperty("staged_candidate_inputs_after");
        var managedBefore = executionElement.GetProperty("managed_dotnet_closure_before");
        var managedAfter = executionElement.GetProperty("managed_dotnet_closure_after");
        if (!ValidateCandidateClosure(candidateBefore)
            || !ValidateCandidateClosure(candidateAfter)
            || !ValidateStagedClosure(stagedBefore)
            || !ValidateStagedClosure(stagedAfter)
            || !ValidateManagedDotnetClosure(managedBefore)
            || !ValidateManagedDotnetClosure(managedAfter)
            || !JsonEquivalent(candidateBefore, candidateAfter)
            || !JsonEquivalent(stagedBefore, stagedAfter)
            || !JsonEquivalent(managedBefore, managedAfter)
            || !StageMatchesCandidate(candidateBefore, stagedBefore)
            || !StageMatchesCandidate(candidateAfter, stagedAfter)
            || !ToolchainMatchesManagedClosure(managedBefore, inputs))
        {
            return false;
        }

        try
        {
            using var currentCandidate = ParseNode(_closureProvider.CaptureCandidateSourceBuildInputs(canonRoot));
            using var currentManaged = ParseNode(_closureProvider.CaptureManagedDotnetClosure());
            if (!ValidateCandidateClosure(currentCandidate.RootElement)
                || !ValidateManagedDotnetClosure(currentManaged.RootElement)
                || !JsonEquivalent(currentCandidate.RootElement, candidateAfter)
                || !JsonEquivalent(currentManaged.RootElement, managedAfter)
                || !ToolchainMatchesManagedClosure(currentManaged.RootElement, inputs))
            {
                return false;
            }
        }
        catch (Exception exception) when (exception is CampaignOsClosureCaptureException
                                           or IOException
                                           or UnauthorizedAccessException
                                           or ArgumentException
                                           or NotSupportedException
                                           or JsonException)
        {
            return false;
        }

        if (!TryReadManifest(executionElement.GetProperty("runtime_manifest_before"), inputs, out var before)
            || !TryReadManifest(executionElement.GetProperty("runtime_manifest_after"), inputs, out var after)
            || !ManifestsEqual(before, after))
        {
            return false;
        }

        var checkpointsElement = executionElement.GetProperty("runtime_checkpoints");
        if (!TryReadRuntimeCheckpoints(checkpointsElement, runId, out var checkpoints))
        {
            return false;
        }

        var checkpointLogElement = executionElement.GetProperty("checkpoint_log");
        var canonicalLog = CanonicalCheckpointLog(checkpoints);
        if (!HasExactProperties(checkpointLogElement, ["file_name", "sha256", "size_bytes"])
            || !TryGetString(checkpointLogElement, "file_name", out var logFileName)
            || !string.Equals(logFileName, "campaign-os-checkpoints.jsonl", StringComparison.Ordinal)
            || !TryGetString(checkpointLogElement, "sha256", out var logSha256)
            || !IsLowerHexSha256(logSha256)
            || !TryGetInt64(checkpointLogElement, "size_bytes", out var logSize)
            || logSize > MaximumCheckpointBytes
            || logSize != canonicalLog.LongLength
            || !string.Equals(logSha256, Sha256(canonicalLog), StringComparison.Ordinal))
        {
            return false;
        }

        execution = new CampaignOsExecutionSnapshot(
            before,
            after,
            new CampaignOsCheckpointLogIdentity(logFileName, logSha256, logSize),
            Array.AsReadOnly(checkpoints));
        return true;
    }

    private static bool ValidateCandidateClosure(JsonElement closure)
    {
        string[] fields =
        [
            "kind", "tree_format_version", "project_roots", "smoke_source_tree", "runtime_data_roots",
            "runtime_data_files", "ancestor_build_controls", "project_assets", "generated_nuget_imports",
            "nuget_package_roots", "nuget_packages", "project_root_count", "runtime_data_root_count",
            "closure_sha256"
        ];
        if (!HasExactProperties(closure, fields)
            || !TryGetString(closure, "kind", out var kind)
            || !string.Equals(kind, "candidate_source_build_inputs", StringComparison.Ordinal)
            || !TryGetInt32(closure, "tree_format_version", out var formatVersion)
            || formatVersion != TreeFormatVersion
            || !TryGetInt32(closure, "project_root_count", out var projectRootCount)
            || projectRootCount != ProjectRoots.Length
            || !TryGetInt32(closure, "runtime_data_root_count", out var runtimeRootCount)
            || runtimeRootCount != RuntimeDataRoots.Length)
        {
            return false;
        }

        var projectRoots = closure.GetProperty("project_roots");
        if (projectRoots.ValueKind != JsonValueKind.Array || projectRoots.GetArrayLength() != ProjectRoots.Length)
        {
            return false;
        }

        var projectIndex = 0;
        foreach (var record in projectRoots.EnumerateArray())
        {
            if (!ValidateTreeRecord(record, ProjectRoots[projectIndex++], allowEmpty: false))
            {
                return false;
            }
        }

        if (!ValidateTreeRecord(closure.GetProperty("smoke_source_tree"), "tests/RunServicesSmoke", allowEmpty: false))
        {
            return false;
        }

        var runtimeRoots = closure.GetProperty("runtime_data_roots");
        if (runtimeRoots.ValueKind != JsonValueKind.Array || runtimeRoots.GetArrayLength() != RuntimeDataRoots.Length)
        {
            return false;
        }

        var runtimeIndex = 0;
        foreach (var record in runtimeRoots.EnumerateArray())
        {
            if (!ValidateTreeRecord(record, RuntimeDataRoots[runtimeIndex++].Source, allowEmpty: false))
            {
                return false;
            }
        }

        if (!ValidateTreeRecord(closure.GetProperty("runtime_data_files"), "runtime_data_files", allowEmpty: false)
            || !ValidateTreeRecord(closure.GetProperty("ancestor_build_controls"), "ancestor_build_controls", allowEmpty: true)
            || !ValidateTreeRecord(closure.GetProperty("project_assets"), "project_assets", allowEmpty: false)
            || !ValidateTreeRecord(closure.GetProperty("generated_nuget_imports"), "generated_nuget_imports", allowEmpty: false)
            || !ValidateTreeRecord(closure.GetProperty("nuget_packages"), "project_assets.packageFolders", allowEmpty: false)
            || closure.GetProperty("project_assets").GetProperty("file_count").GetInt64() != ProjectRoots.Length
            || closure.GetProperty("generated_nuget_imports").GetProperty("file_count").GetInt64() != ProjectRoots.Length * 2L)
        {
            return false;
        }

        var packageRoots = closure.GetProperty("nuget_package_roots");
        if (packageRoots.ValueKind != JsonValueKind.Array || packageRoots.GetArrayLength() == 0)
        {
            return false;
        }

        string? prior = null;
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in packageRoots.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.String
                || item.GetString() is not { } path
                || !Path.IsPathFullyQualified(path)
                || !seen.Add(path)
                || (prior is not null && string.CompareOrdinal(prior, path) >= 0))
            {
                return false;
            }

            prior = path;
        }

        return HasBoundClosureDigest(closure);
    }

    private static bool ValidateStagedClosure(JsonElement closure)
    {
        string[] fields = ["kind", "tree_format_version", "roots", "runtime_data_files", "root_count", "closure_sha256"];
        var expectedRoots = new[] { "Chummer.Run.Api" }.Concat(RuntimeDataRoots.Select(static item => item.Staged)).ToArray();
        if (!HasExactProperties(closure, fields)
            || !TryGetString(closure, "kind", out var kind)
            || !string.Equals(kind, "staged_candidate_inputs", StringComparison.Ordinal)
            || !TryGetInt32(closure, "tree_format_version", out var formatVersion)
            || formatVersion != TreeFormatVersion
            || !TryGetInt32(closure, "root_count", out var rootCount)
            || rootCount != expectedRoots.Length)
        {
            return false;
        }

        var roots = closure.GetProperty("roots");
        if (roots.ValueKind != JsonValueKind.Array || roots.GetArrayLength() != expectedRoots.Length)
        {
            return false;
        }

        var index = 0;
        foreach (var record in roots.EnumerateArray())
        {
            if (!ValidateTreeRecord(record, expectedRoots[index++], allowEmpty: false))
            {
                return false;
            }
        }

        return ValidateTreeRecord(closure.GetProperty("runtime_data_files"), "runtime_data_files", allowEmpty: false)
               && HasBoundClosureDigest(closure);
    }

    private static bool ValidateManagedDotnetClosure(JsonElement closure)
    {
        string[] fields = ["kind", "dotnet_host", "components", "component_count", "closure_sha256"];
        if (!HasExactProperties(closure, fields)
            || !TryGetString(closure, "kind", out var kind)
            || !string.Equals(kind, "managed_dotnet_closure", StringComparison.Ordinal)
            || !ValidateDotnetIdentityElement(closure.GetProperty("dotnet_host"))
            || !TryGetInt32(closure, "component_count", out var componentCount)
            || componentCount != ManagedComponentRoots.Length)
        {
            return false;
        }

        var components = closure.GetProperty("components");
        if (components.ValueKind != JsonValueKind.Array || components.GetArrayLength() != ManagedComponentRoots.Length)
        {
            return false;
        }

        var index = 0;
        foreach (var component in components.EnumerateArray())
        {
            var expectedRoot = ManagedComponentRoots[index++];
            if (!HasExactProperties(
                    component,
                    ["root", "version", "path", "file_count", "total_size_bytes", "tree_sha256"])
                || !TryGetString(component, "root", out var root)
                || !string.Equals(root, expectedRoot, StringComparison.Ordinal)
                || !TryGetString(component, "version", out var version)
                || !version.StartsWith("10.", StringComparison.Ordinal)
                || !SdkVersionPattern.IsMatch(version)
                || !TryGetString(component, "path", out var path)
                || !Path.IsPathFullyQualified(path)
                || !ValidateTreeValues(component, allowEmpty: false))
            {
                return false;
            }
        }

        return HasBoundClosureDigest(closure);
    }

    private static bool ValidateDotnetIdentityElement(JsonElement identity)
    {
        return HasExactProperties(identity, ["path", "resolved_path", "sha256", "size_bytes"])
               && TryGetString(identity, "path", out var path)
               && string.Equals(path, DotnetHostPath, StringComparison.Ordinal)
               && TryGetString(identity, "resolved_path", out var resolvedPath)
               && Path.IsPathFullyQualified(resolvedPath)
               && TryGetString(identity, "sha256", out var sha256)
               && IsLowerHexSha256(sha256)
               && TryGetInt64(identity, "size_bytes", out var sizeBytes)
               && sizeBytes is > 0 and <= MaximumInputBytes;
    }

    private static bool ValidateTreeRecord(JsonElement record, string root, bool allowEmpty)
    {
        return HasExactProperties(record, ["root", "file_count", "total_size_bytes", "tree_sha256"])
               && TryGetString(record, "root", out var actualRoot)
               && string.Equals(actualRoot, root, StringComparison.Ordinal)
               && ValidateTreeValues(record, allowEmpty);
    }

    private static bool ValidateTreeValues(JsonElement record, bool allowEmpty)
    {
        return TryGetInt64(record, "file_count", out var fileCount)
               && fileCount >= (allowEmpty ? 0 : 1)
               && fileCount <= MaximumTreeFiles
               && TryGetInt64(record, "total_size_bytes", out var totalSize)
               && totalSize >= 0
               && totalSize <= MaximumTreeBytes
               && TryGetString(record, "tree_sha256", out var treeSha256)
               && IsLowerHexSha256(treeSha256);
    }

    private static bool HasBoundClosureDigest(JsonElement closure)
    {
        return TryGetString(closure, "closure_sha256", out var claimed)
               && IsLowerHexSha256(claimed)
               && string.Equals(claimed, CanonicalObjectDigest(closure, "closure_sha256"), StringComparison.Ordinal);
    }

    private static bool StageMatchesCandidate(JsonElement candidate, JsonElement staged)
    {
        var projectRecords = candidate.GetProperty("project_roots").EnumerateArray()
            .ToDictionary(static item => item.GetProperty("root").GetString()!, StringComparer.Ordinal);
        var stagedRecords = staged.GetProperty("roots").EnumerateArray()
            .ToDictionary(static item => item.GetProperty("root").GetString()!, StringComparer.Ordinal);
        if (!TreeContentEqual(projectRecords["Chummer.Run.Api"], stagedRecords["Chummer.Run.Api"]))
        {
            return false;
        }

        var runtimeRecords = candidate.GetProperty("runtime_data_roots").EnumerateArray().ToArray();
        for (var index = 0; index < RuntimeDataRoots.Length; index++)
        {
            if (!string.Equals(
                    runtimeRecords[index].GetProperty("root").GetString(),
                    RuntimeDataRoots[index].Source,
                    StringComparison.Ordinal)
                || !TreeContentEqual(runtimeRecords[index], stagedRecords[RuntimeDataRoots[index].Staged]))
            {
                return false;
            }
        }

        return TreeContentEqual(candidate.GetProperty("runtime_data_files"), staged.GetProperty("runtime_data_files"));
    }

    private static bool TreeContentEqual(JsonElement left, JsonElement right)
    {
        return left.GetProperty("file_count").GetInt64() == right.GetProperty("file_count").GetInt64()
               && left.GetProperty("total_size_bytes").GetInt64() == right.GetProperty("total_size_bytes").GetInt64()
               && string.Equals(
                   left.GetProperty("tree_sha256").GetString(),
                   right.GetProperty("tree_sha256").GetString(),
                   StringComparison.Ordinal);
    }

    private static bool ToolchainMatchesManagedClosure(
        JsonElement managedClosure,
        CampaignOsLocalProofInputs inputs)
    {
        var dotnet = managedClosure.GetProperty("dotnet_host");
        if (!string.Equals(dotnet.GetProperty("path").GetString(), inputs.DotnetHost.Path, StringComparison.Ordinal)
            || !string.Equals(dotnet.GetProperty("resolved_path").GetString(), inputs.DotnetHost.ResolvedPath, StringComparison.Ordinal)
            || !string.Equals(dotnet.GetProperty("sha256").GetString(), inputs.DotnetHost.Sha256, StringComparison.Ordinal)
            || dotnet.GetProperty("size_bytes").GetInt64() != inputs.DotnetHost.SizeBytes)
        {
            return false;
        }

        var sdk = managedClosure.GetProperty("components")[ManagedComponentRoots.Length - 1];
        try
        {
            var expectedCsc = Path.GetFullPath(Path.Combine(
                sdk.GetProperty("path").GetString()!, "Roslyn", "bincore", "csc.dll"));
            return string.Equals(expectedCsc, Path.GetFullPath(inputs.Csc.Path), StringComparison.Ordinal);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return false;
        }
    }

    private static JsonDocument ParseNode(JsonObject value) => JsonDocument.Parse(
        value.ToJsonString(new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping }));

    private static bool TryReadManifest(
        JsonElement manifestElement,
        CampaignOsLocalProofInputs inputs,
        out CampaignOsRuntimeManifest manifest)
    {
        manifest = default!;
        if (!HasExactProperties(manifestElement, ["algorithm", "entries", "entry_count", "manifest_sha256"])
            || !TryGetString(manifestElement, "algorithm", out var algorithm)
            || !string.Equals(algorithm, "sha256", StringComparison.Ordinal)
            || !TryGetInt32(manifestElement, "entry_count", out var entryCount)
            || entryCount != RuntimeManifestPaths.Length
            || !TryGetString(manifestElement, "manifest_sha256", out var manifestSha256)
            || !IsLowerHexSha256(manifestSha256))
        {
            return false;
        }

        var entriesElement = manifestElement.GetProperty("entries");
        if (entriesElement.ValueKind != JsonValueKind.Array || entriesElement.GetArrayLength() != entryCount)
        {
            return false;
        }

        var entries = new CampaignOsManifestEntry[entryCount];
        string? priorPath = null;
        var index = 0;
        foreach (var entryElement in entriesElement.EnumerateArray())
        {
            if (!HasExactProperties(entryElement, ["path", "sha256", "size_bytes"])
                || !TryGetString(entryElement, "path", out var path)
                || !IsStableRuntimePath(path)
                || !string.Equals(path, RuntimeManifestPaths[index], StringComparison.Ordinal)
                || (priorPath is not null && string.CompareOrdinal(priorPath, path) >= 0)
                || !TryGetString(entryElement, "sha256", out var sha256)
                || !IsLowerHexSha256(sha256)
                || !TryGetInt64(entryElement, "size_bytes", out var sizeBytes)
                || sizeBytes <= 0
                || sizeBytes > MaximumInputBytes)
            {
                return false;
            }

            entries[index++] = new CampaignOsManifestEntry(path, sha256, sizeBytes);
            priorPath = path;
        }

        var canonical = CanonicalManifest(entries);
        if (!string.Equals(manifestSha256, Sha256(canonical), StringComparison.Ordinal)
            || !ManifestContainsIdentity(entries, AssemblyFileName, inputs.Assembly.Sha256, inputs.Assembly.SizeBytes)
            || !ManifestContainsIdentity(entries, "toolchain/dotnet", inputs.DotnetHost.Sha256, inputs.DotnetHost.SizeBytes)
            || !ManifestContainsIdentity(entries, "toolchain/csc.dll", inputs.Csc.Sha256, inputs.Csc.SizeBytes))
        {
            return false;
        }

        manifest = new CampaignOsRuntimeManifest(manifestSha256, Array.AsReadOnly(entries));
        return true;
    }

    private static bool TryReadRuntimeCheckpoints(
        JsonElement checkpointsElement,
        string runId,
        out CampaignOsRuntimeCheckpoint[] checkpoints)
    {
        checkpoints = [];
        if (checkpointsElement.ValueKind != JsonValueKind.Array
            || checkpointsElement.GetArrayLength() != JourneyIds.Length)
        {
            return false;
        }

        var parsed = new CampaignOsRuntimeCheckpoint[JourneyIds.Length];
        var index = 0;
        foreach (var checkpointElement in checkpointsElement.EnumerateArray())
        {
            var expectedCheckpointId = JourneyIds[index] + ".run_services_smoke_exit_zero";
            if (!HasExactProperties(checkpointElement, ["checkpoint_id", "run_id", "status"])
                || !TryGetString(checkpointElement, "checkpoint_id", out var checkpointId)
                || !string.Equals(checkpointId, expectedCheckpointId, StringComparison.Ordinal)
                || !TryGetString(checkpointElement, "run_id", out var checkpointRunId)
                || !string.Equals(checkpointRunId, runId, StringComparison.Ordinal)
                || !TryGetString(checkpointElement, "status", out var status)
                || !string.Equals(status, PassedStatus, StringComparison.Ordinal))
            {
                return false;
            }

            parsed[index++] = new CampaignOsRuntimeCheckpoint(checkpointId, checkpointRunId, status);
        }

        checkpoints = parsed;
        return true;
    }

    private static byte[] CanonicalManifest(IReadOnlyList<CampaignOsManifestEntry> entries)
    {
        var builder = new StringBuilder("[");
        for (var index = 0; index < entries.Count; index++)
        {
            if (index > 0)
            {
                builder.Append(',');
            }

            var entry = entries[index];
            builder.Append("{\"path\":\"")
                .Append(entry.Path)
                .Append("\",\"sha256\":\"")
                .Append(entry.Sha256)
                .Append("\",\"size_bytes\":")
                .Append(entry.SizeBytes.ToString(CultureInfo.InvariantCulture))
                .Append('}');
        }

        builder.Append(']');
        return Encoding.UTF8.GetBytes(builder.ToString());
    }

    private static byte[] CanonicalCheckpointLog(IReadOnlyList<CampaignOsRuntimeCheckpoint> checkpoints)
    {
        var builder = new StringBuilder();
        foreach (var checkpoint in checkpoints)
        {
            builder.Append("{\"checkpoint_id\":\"")
                .Append(checkpoint.CheckpointId)
                .Append("\",\"run_id\":\"")
                .Append(checkpoint.RunId)
                .Append("\",\"status\":\"")
                .Append(checkpoint.Status)
                .Append("\"}\n");
        }

        return Encoding.UTF8.GetBytes(builder.ToString());
    }

    private static bool JsonEquivalent(JsonElement left, JsonElement right) =>
        CanonicalJson(left).AsSpan().SequenceEqual(CanonicalJson(right));

    private static string CanonicalObjectDigest(JsonElement value, string excludedProperty)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(
                   stream,
                   new JsonWriterOptions
                   {
                       Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
                       Indented = false
                   }))
        {
            writer.WriteStartObject();
            foreach (var property in value.EnumerateObject()
                         .Where(property => !string.Equals(property.Name, excludedProperty, StringComparison.Ordinal))
                         .OrderBy(static property => property.Name, StringComparer.Ordinal))
            {
                writer.WritePropertyName(property.Name);
                WriteCanonicalJson(writer, property.Value);
            }

            writer.WriteEndObject();
        }

        return Sha256(stream.ToArray());
    }

    internal static byte[] CanonicalJson(JsonElement value)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(
                   stream,
                   new JsonWriterOptions
                   {
                       Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
                       Indented = false
                   }))
        {
            WriteCanonicalJson(writer, value);
        }

        return stream.ToArray();
    }

    private static void WriteCanonicalJson(Utf8JsonWriter writer, JsonElement value)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (var property in value.EnumerateObject().OrderBy(static property => property.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(property.Name);
                    WriteCanonicalJson(writer, property.Value);
                }

                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (var item in value.EnumerateArray())
                {
                    WriteCanonicalJson(writer, item);
                }

                writer.WriteEndArray();
                break;
            case JsonValueKind.String:
                writer.WriteStringValue(value.GetString());
                break;
            case JsonValueKind.Number:
                if (value.TryGetInt64(out var integer))
                {
                    writer.WriteNumberValue(integer);
                }
                else
                {
                    writer.WriteRawValue(value.GetRawText(), skipInputValidation: false);
                }

                break;
            case JsonValueKind.True:
                writer.WriteBooleanValue(true);
                break;
            case JsonValueKind.False:
                writer.WriteBooleanValue(false);
                break;
            case JsonValueKind.Null:
                writer.WriteNullValue();
                break;
            default:
                throw new JsonException("Unsupported JSON token in canonical proof data.");
        }
    }

    private static bool ManifestsEqual(CampaignOsRuntimeManifest left, CampaignOsRuntimeManifest right)
    {
        return string.Equals(left.ManifestSha256, right.ManifestSha256, StringComparison.Ordinal)
               && left.Entries.SequenceEqual(right.Entries);
    }

    private static bool ManifestContainsIdentity(
        IEnumerable<CampaignOsManifestEntry> entries,
        string path,
        string sha256,
        long sizeBytes)
    {
        return entries.Any(entry => string.Equals(entry.Path, path, StringComparison.Ordinal)
                                    && string.Equals(entry.Sha256, sha256, StringComparison.Ordinal)
                                    && entry.SizeBytes == sizeBytes);
    }

    private static bool IsStableRuntimePath(string path)
    {
        if (string.IsNullOrWhiteSpace(path)
            || path.Length > 512
            || path.StartsWith("/", StringComparison.Ordinal)
            || path.Contains('\\')
            || path.Any(character => character is not (>= 'a' and <= 'z'
                or >= 'A' and <= 'Z'
                or >= '0' and <= '9'
                or '.' or '_' or '-' or '/')))
        {
            return false;
        }

        return path.Split('/').All(segment => segment.Length > 0 && segment is not "." and not "..");
    }

    private static bool ValidateJourneys(JsonElement journeysElement, out string[] journeys)
    {
        journeys = [];
        if (journeysElement.ValueKind != JsonValueKind.Array || journeysElement.GetArrayLength() != JourneyIds.Length)
        {
            return false;
        }

        var validated = new string[JourneyIds.Length];
        var index = 0;
        foreach (var journey in journeysElement.EnumerateArray())
        {
            var expectedId = JourneyIds[index];
            var expectedCheckpoint = expectedId + ".run_services_smoke_exit_zero";
            if (!HasExactProperties(journey, ["id", "status", "checkpoint_ids"])
                || !TryGetString(journey, "id", out var id)
                || !string.Equals(id, expectedId, StringComparison.Ordinal)
                || !TryGetString(journey, "status", out var status)
                || !string.Equals(status, PassedStatus, StringComparison.Ordinal))
            {
                return false;
            }

            var checkpoints = journey.GetProperty("checkpoint_ids");
            if (checkpoints.ValueKind != JsonValueKind.Array
                || checkpoints.GetArrayLength() != 1
                || checkpoints[0].ValueKind != JsonValueKind.String
                || !string.Equals(checkpoints[0].GetString(), expectedCheckpoint, StringComparison.Ordinal))
            {
                return false;
            }

            validated[index++] = id;
        }

        journeys = validated;
        return true;
    }

    private static bool ValidateSummary(JsonElement summary)
    {
        return HasExactProperties(summary, ["journey_count", "passed_journey_count", "checkpoint_count", "passed_checkpoint_count"])
               && TryGetInt32(summary, "journey_count", out var journeyCount)
               && journeyCount == JourneyIds.Length
               && TryGetInt32(summary, "passed_journey_count", out var passedJourneyCount)
               && passedJourneyCount == JourneyIds.Length
               && TryGetInt32(summary, "checkpoint_count", out var checkpointCount)
               && checkpointCount == JourneyIds.Length
               && TryGetInt32(summary, "passed_checkpoint_count", out var passedCheckpointCount)
               && passedCheckpointCount == JourneyIds.Length;
    }

    private (string? Path, string? CanonRoot, string? Error) ResolveLocalProofPath()
    {
        try
        {
            var configuredCanonRoot = _configuration[PublicCanonRootKey]?.Trim();
            if (string.IsNullOrWhiteSpace(configuredCanonRoot))
            {
                return (null, null, "proof_not_configured");
            }

            if (!Path.IsPathFullyQualified(configuredCanonRoot))
            {
                return (null, null, "proof_path_not_absolute");
            }

            var canonRoot = Path.GetFullPath(configuredCanonRoot);
            var configuredProofPath = _configuration[LocalProofFileKey]?.Trim();
            if (!string.IsNullOrWhiteSpace(configuredProofPath))
            {
                return Path.IsPathFullyQualified(configuredProofPath)
                    ? (Path.GetFullPath(configuredProofPath), canonRoot, null)
                    : (null, null, "proof_path_not_absolute");
            }

            var relativePath = DefaultLocalProofRelativePath.Replace('/', Path.DirectorySeparatorChar);
            return (Path.GetFullPath(Path.Combine(canonRoot, relativePath)), canonRoot, null);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return (null, null, "proof_path_invalid");
        }
    }

    private static (byte[]? Bytes, string? Error) ReadStableFile(
        string path,
        int maximumBytes,
        bool allowEmpty = false)
    {
        try
        {
            if (HasLinkedAncestor(path))
            {
                return (null, "proof_link_disallowed");
            }

            var file = new FileInfo(path);
            if (file.LinkTarget is not null)
            {
                return (null, "proof_link_disallowed");
            }

            file.Refresh();
            if (!file.Exists)
            {
                return (null, "proof_not_found");
            }

            if ((file.Attributes & FileAttributes.ReparsePoint) != 0)
            {
                return (null, "proof_link_disallowed");
            }

            if ((file.Attributes & (FileAttributes.Directory | FileAttributes.Device)) != 0)
            {
                return (null, "proof_not_regular_file");
            }

            var beforeLength = file.Length;
            var beforeWrite = file.LastWriteTimeUtc;
            if (beforeLength < 0 || (!allowEmpty && beforeLength == 0))
            {
                return (null, "proof_read_failed");
            }

            if (beforeLength > maximumBytes)
            {
                return (null, "proof_too_large");
            }

            var bytes = new byte[checked((int)beforeLength)];
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 4096, FileOptions.SequentialScan))
            {
                if (stream.Length != beforeLength)
                {
                    return (null, "proof_unstable");
                }

                var offset = 0;
                while (offset < bytes.Length)
                {
                    var count = stream.Read(bytes, offset, bytes.Length - offset);
                    if (count == 0)
                    {
                        return (null, "proof_unstable");
                    }

                    offset += count;
                }

                if (stream.ReadByte() != -1)
                {
                    return (null, "proof_unstable");
                }
            }

            file.Refresh();
            if (!file.Exists || file.Length != beforeLength || file.LastWriteTimeUtc != beforeWrite)
            {
                return (null, "proof_unstable");
            }

            return (bytes, null);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return (null, "proof_read_failed");
        }
    }

    private static bool HasLinkedAncestor(string path)
    {
        var directory = Directory.GetParent(Path.GetFullPath(path));
        while (directory is not null)
        {
            directory.Refresh();
            if (directory.Exists
                && (directory.LinkTarget is not null
                    || (directory.Attributes & FileAttributes.ReparsePoint) != 0))
            {
                return true;
            }

            directory = directory.Parent;
        }

        return false;
    }

    private static bool TryDecodeUtf8(byte[] bytes, out string text)
    {
        try
        {
            text = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true).GetString(bytes);
            return true;
        }
        catch (DecoderFallbackException)
        {
            text = string.Empty;
            return false;
        }
    }

    private static string Sha256(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private static bool TryAdd(DateTimeOffset value, TimeSpan delta, out DateTimeOffset result)
    {
        try
        {
            result = value.Add(delta);
            return true;
        }
        catch (ArgumentOutOfRangeException)
        {
            result = default;
            return false;
        }
    }

    private static bool HasDuplicateProperty(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject())
            {
                if (!names.Add(property.Name) || HasDuplicateProperty(property.Value))
                {
                    return true;
                }
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in element.EnumerateArray())
            {
                if (HasDuplicateProperty(item))
                {
                    return true;
                }
            }
        }

        return false;
    }

    private static bool HasExactProperties(JsonElement element, IReadOnlyList<string> expected)
    {
        if (element.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        var index = 0;
        foreach (var property in element.EnumerateObject())
        {
            if (index >= expected.Count
                || !string.Equals(property.Name, expected[index], StringComparison.Ordinal))
            {
                return false;
            }

            index++;
        }

        return index == expected.Count;
    }

    private static bool TryGetString(JsonElement element, string propertyName, out string value)
    {
        value = string.Empty;
        return element.TryGetProperty(propertyName, out var property)
               && property.ValueKind == JsonValueKind.String
               && property.GetString() is { } parsed
               && (value = parsed) is not null;
    }

    private static bool TryGetInt32(JsonElement element, string propertyName, out int value)
    {
        value = default;
        return element.TryGetProperty(propertyName, out var property)
               && property.ValueKind == JsonValueKind.Number
               && property.TryGetInt32(out value);
    }

    private static bool TryGetInt64(JsonElement element, string propertyName, out long value)
    {
        value = default;
        return element.TryGetProperty(propertyName, out var property)
               && property.ValueKind == JsonValueKind.Number
               && property.TryGetInt64(out value);
    }

    private static bool TryGetUtcTimestamp(JsonElement element, string propertyName, out DateTimeOffset value)
    {
        value = default;
        return TryGetString(element, propertyName, out var text)
               && DateTimeOffset.TryParseExact(
                   text,
                   "yyyy-MM-dd'T'HH:mm:ss'Z'",
                   CultureInfo.InvariantCulture,
                   DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                   out value);
    }

    private static bool IsLowerHexSha256(string value)
    {
        return value.Length == 64 && value.All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');
    }

    private static bool IsCanonicalUuidV4(string value)
    {
        return Guid.TryParseExact(value, "D", out var parsed)
               && string.Equals(value, parsed.ToString("D"), StringComparison.Ordinal)
               && value[14] == '4'
               && value[19] is '8' or '9' or 'a' or 'b';
    }

    private sealed class FileSystemCampaignOsClosureProvider : ICampaignOsClosureProvider
    {
        private static readonly ProjectSpec[] Projects =
        [
            new("../chummer-core-engine/Chummer.Contracts", "Chummer.Contracts.csproj", "../chummer-core-engine/.tmp/nuget/packages"),
            new("../chummer-hub-registry/Chummer.Hub.Registry.Contracts", "Chummer.Hub.Registry.Contracts.csproj", "../chummer-hub-registry/.tmp/nuget/packages"),
            new("../chummer-hub-registry/Chummer.Run.Registry", "Chummer.Run.Registry.csproj", "../chummer-hub-registry/.tmp/nuget/packages"),
            new("../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts", "Chummer.Media.Contracts.csproj", "../../fleet/repos/chummer-media-factory/.tmp/nuget/packages"),
            new("../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime", "Chummer.Media.Factory.Runtime.csproj", "../../fleet/repos/chummer-media-factory/.tmp/nuget/packages"),
            new("Chummer.Play.Contracts", "Chummer.Play.Contracts.csproj", ".tmp/nuget/packages"),
            new("Chummer.Campaign.Contracts", "Chummer.Campaign.Contracts.csproj", ".tmp/nuget/packages"),
            new("Chummer.Control.Contracts", "Chummer.Control.Contracts.csproj", ".tmp/nuget/packages"),
            new("Chummer.Run.Contracts", "Chummer.Run.Contracts.csproj", ".tmp/nuget/packages"),
            new("Chummer.World.Contracts", "Chummer.World.Contracts.csproj", ".tmp/nuget/packages"),
            new("Chummer.Run.Api", "Chummer.Run.Api.csproj", ".tmp/nuget/packages"),
            new("Chummer.Run.Identity", "Chummer.Run.Identity.csproj", ".tmp/nuget/packages"),
            new("Chummer.Run.AI", "Chummer.Run.AI.csproj", ".tmp/nuget/packages")
        ];
        private static readonly HashSet<string> ExcludedTreeDirectories = new(
            ["bin", "obj", "TestResults", ".tmp"],
            StringComparer.Ordinal);
        private static readonly HashSet<string> NoExcludedDirectories = new(StringComparer.Ordinal);
        private static readonly string[] AncestorControlNames =
        [
            ".editorconfig", "Directory.Build.props", "Directory.Build.rsp", "Directory.Build.targets",
            "Directory.Packages.props", "Directory.Packages.targets", "MSBuild.rsp", "NuGet.Config",
            "global.json", "nuget.config", "packages.lock.json"
        ];

        public static FileSystemCampaignOsClosureProvider Instance { get; } = new();

        public JsonObject CaptureCandidateSourceBuildInputs(string canonRoot)
        {
            var root = Path.GetFullPath(canonRoot);
            var projectRecords = ToJsonArray(Projects.Select(project =>
                (JsonNode)TreeRecord(project.Root, Combine(root, project.Root), ExcludedTreeDirectories)));
            var runtimeRecords = ToJsonArray(RuntimeDataRoots.Select(item =>
                (JsonNode)TreeRecord(item.Source, Combine(root, item.Source), ExcludedTreeDirectories)));
            var assets = Projects.Select(project => (
                Logical: $"{project.Root}/obj/project.assets.json",
                Physical: Combine(root, project.Root, "obj", "project.assets.json"))).ToArray();
            var imports = Projects.SelectMany(project => new[]
            {
                (
                    Logical: $"{project.Root}/obj/{project.ProjectFile}.nuget.g.props",
                    Physical: Combine(root, project.Root, "obj", $"{project.ProjectFile}.nuget.g.props")),
                (
                    Logical: $"{project.Root}/obj/{project.ProjectFile}.nuget.g.targets",
                    Physical: Combine(root, project.Root, "obj", $"{project.ProjectFile}.nuget.g.targets"))
            }).ToArray();
            var (packageRoots, packageRecord) = CaptureNugetPackages(root);

            var closure = new JsonObject
            {
                ["kind"] = "candidate_source_build_inputs",
                ["tree_format_version"] = TreeFormatVersion,
                ["project_roots"] = projectRecords,
                ["smoke_source_tree"] = TreeRecord(
                    "tests/RunServicesSmoke",
                    Combine(root, "tests/RunServicesSmoke"),
                    ExcludedTreeDirectories),
                ["runtime_data_roots"] = runtimeRecords,
                ["runtime_data_files"] = ExplicitFilesRecord(
                    "runtime_data_files",
                    [("scripts/runbook.sh", Combine(root, "scripts/runbook.sh"))]),
                ["ancestor_build_controls"] = AncestorControlsRecord(root),
                ["project_assets"] = ExplicitFilesRecord("project_assets", assets),
                ["generated_nuget_imports"] = ExplicitFilesRecord("generated_nuget_imports", imports),
                ["nuget_package_roots"] = ToJsonArray(packageRoots.Select(static item => (JsonNode)JsonValue.Create(item)!)),
                ["nuget_packages"] = packageRecord,
                ["project_root_count"] = Projects.Length,
                ["runtime_data_root_count"] = RuntimeDataRoots.Length
            };
            closure["closure_sha256"] = DigestNode(closure);
            return closure;
        }

        public JsonObject CaptureManagedDotnetClosure()
        {
            var dotnetFile = new FileInfo(DotnetHostPath);
            string resolvedDotnet;
            try
            {
                if (HasLinkedAncestor(DotnetHostPath))
                {
                    throw new CampaignOsClosureCaptureException("dotnet_host_symlink_ancestor");
                }

                resolvedDotnet = Path.GetFullPath(
                    dotnetFile.ResolveLinkTarget(returnFinalTarget: true)?.FullName ?? dotnetFile.FullName);
            }
            catch (Exception exception) when (exception is IOException
                                               or UnauthorizedAccessException
                                               or ArgumentException
                                               or NotSupportedException)
            {
                throw new CampaignOsClosureCaptureException("dotnet_host_invalid", exception);
            }

            var dotnetBytes = RequiredFile(resolvedDotnet);
            var dotnetRoot = Path.GetDirectoryName(resolvedDotnet)
                             ?? throw new CampaignOsClosureCaptureException("dotnet_root_invalid");
            var selections = new[]
            {
                SelectManagedVersion(Combine(dotnetRoot, "host/fxr"), []),
                SelectManagedVersion(Combine(dotnetRoot, "shared/Microsoft.NETCore.App"), []),
                SelectManagedVersion(Combine(dotnetRoot, "shared/Microsoft.AspNetCore.App"), []),
                SelectManagedVersion(Combine(dotnetRoot, "packs/Microsoft.NETCore.App.Ref"), ["ref", "net10.0"]),
                SelectManagedVersion(Combine(dotnetRoot, "packs/Microsoft.AspNetCore.App.Ref"), ["ref", "net10.0"]),
                SelectManagedVersion(Combine(dotnetRoot, "sdk"), [])
            };
            RequiredFile(Combine(selections[^1].Path, "Roslyn/bincore/csc.dll"));

            var components = new JsonArray();
            for (var index = 0; index < selections.Length; index++)
            {
                var tree = TreeRecord(ManagedComponentRoots[index], selections[index].Path, NoExcludedDirectories);
                components.Add(new JsonObject
                {
                    ["root"] = ManagedComponentRoots[index],
                    ["version"] = selections[index].Version,
                    ["path"] = selections[index].Path,
                    ["file_count"] = tree["file_count"]!.DeepClone(),
                    ["total_size_bytes"] = tree["total_size_bytes"]!.DeepClone(),
                    ["tree_sha256"] = tree["tree_sha256"]!.DeepClone()
                });
            }

            var closure = new JsonObject
            {
                ["kind"] = "managed_dotnet_closure",
                ["dotnet_host"] = new JsonObject
                {
                    ["path"] = DotnetHostPath,
                    ["resolved_path"] = resolvedDotnet,
                    ["sha256"] = Sha256(dotnetBytes),
                    ["size_bytes"] = dotnetBytes.LongLength
                },
                ["components"] = components,
                ["component_count"] = components.Count
            };
            closure["closure_sha256"] = DigestNode(closure);
            return closure;
        }

        private static (string[] Roots, JsonObject Record) CaptureNugetPackages(string root)
        {
            var packageRoots = new SortedSet<string>(StringComparer.Ordinal);
            var packageDirectories = new SortedDictionary<string, string>(StringComparer.Ordinal);
            foreach (var project in Projects)
            {
                var assetPath = Combine(root, project.Root, "obj", "project.assets.json");
                var bytes = RequiredFile(assetPath);
                JsonDocument document;
                try
                {
                    document = JsonDocument.Parse(bytes, new JsonDocumentOptions
                    {
                        AllowTrailingCommas = false,
                        CommentHandling = JsonCommentHandling.Disallow,
                        MaxDepth = 64
                    });
                }
                catch (JsonException exception)
                {
                    throw new CampaignOsClosureCaptureException("project_assets_invalid", exception);
                }

                using (document)
                {
                    var asset = document.RootElement;
                    if (asset.ValueKind != JsonValueKind.Object
                        || HasDuplicateProperty(asset)
                        || !TryGetInt32(asset, "version", out var version)
                        || version != 3
                        || !asset.TryGetProperty("targets", out var targets)
                        || targets.ValueKind != JsonValueKind.Object
                        || !targets.EnumerateObject().Any(property =>
                            property.Name.Contains("net10.0", StringComparison.OrdinalIgnoreCase)
                            || property.Name.Contains("version=v10.0", StringComparison.OrdinalIgnoreCase)))
                    {
                        throw new CampaignOsClosureCaptureException("project_assets_invalid");
                    }

                    if (asset.TryGetProperty("logs", out var logs)
                        && (logs.ValueKind != JsonValueKind.Array
                            || logs.EnumerateArray().Any(item =>
                                item.ValueKind == JsonValueKind.Object
                                && TryGetString(item, "level", out var level)
                                && string.Equals(level, "error", StringComparison.OrdinalIgnoreCase))))
                    {
                        throw new CampaignOsClosureCaptureException("project_assets_restore_error");
                    }

                    if (!asset.TryGetProperty("packageFolders", out var folders)
                        || folders.ValueKind != JsonValueKind.Object
                        || folders.EnumerateObject().Count() != 1)
                    {
                        throw new CampaignOsClosureCaptureException("project_assets_package_root_mismatch");
                    }

                    var folder = folders.EnumerateObject().Single().Name;
                    var actualRoot = Path.GetFullPath(folder);
                    var expectedRoot = Combine(root, project.PackageRoot);
                    if (!string.Equals(actualRoot, expectedRoot, StringComparison.Ordinal)
                        || !IsSafeDirectory(expectedRoot))
                    {
                        throw new CampaignOsClosureCaptureException("project_assets_package_root_mismatch");
                    }

                    packageRoots.Add(expectedRoot);
                    if (!asset.TryGetProperty("libraries", out var libraries)
                        || libraries.ValueKind != JsonValueKind.Object)
                    {
                        throw new CampaignOsClosureCaptureException("project_assets_invalid");
                    }

                    foreach (var libraryProperty in libraries.EnumerateObject())
                    {
                        var library = libraryProperty.Value;
                        if (library.ValueKind != JsonValueKind.Object
                            || !TryGetString(library, "type", out var type)
                            || !string.Equals(type, "package", StringComparison.Ordinal))
                        {
                            continue;
                        }

                        var packagePath = TryGetString(library, "path", out var configuredPath)
                            ? configuredPath
                            : libraryProperty.Name.ToLowerInvariant();
                        if (!IsRelativeTreePath(packagePath))
                        {
                            throw new CampaignOsClosureCaptureException("nuget_package_path_invalid");
                        }

                        var directory = Combine(expectedRoot, packagePath);
                        if (!IsUnderRoot(directory, expectedRoot))
                        {
                            throw new CampaignOsClosureCaptureException("nuget_package_path_escape");
                        }

                        packageDirectories[$"{expectedRoot.Replace('\\', '/')}::{packagePath}"] = directory;
                    }
                }
            }

            var combined = new List<TreeEntry>();
            foreach (var (logicalRoot, directory) in packageDirectories)
            {
                foreach (var entry in StableTreeEntries(directory, NoExcludedDirectories))
                {
                    combined.Add(new TreeEntry(
                        $"{logicalRoot}/{entry.Path}",
                        entry.Sha256,
                        entry.SizeBytes));
                }
            }

            combined.Sort(static (left, right) => string.CompareOrdinal(left.Path, right.Path));
            EnsureTreeBounds(combined);
            if (combined.Select(static item => item.Path).Distinct(StringComparer.Ordinal).Count() != combined.Count)
            {
                throw new CampaignOsClosureCaptureException("nuget_package_duplicate_path");
            }

            return (
                packageRoots.ToArray(),
                new JsonObject
                {
                    ["root"] = "project_assets.packageFolders",
                    ["file_count"] = combined.Count,
                    ["total_size_bytes"] = combined.Sum(static item => item.SizeBytes),
                    ["tree_sha256"] = DigestEntries(combined)
                });
        }

        private static JsonObject AncestorControlsRecord(string root)
        {
            var first = ScanExplicitFiles(DiscoverAncestorControls(root));
            var second = ScanExplicitFiles(DiscoverAncestorControls(root));
            if (!first.SequenceEqual(second))
            {
                throw new CampaignOsClosureCaptureException("ancestor_build_controls_unstable");
            }

            return new JsonObject
            {
                ["root"] = "ancestor_build_controls",
                ["file_count"] = first.Count,
                ["total_size_bytes"] = first.Sum(static item => item.SizeBytes),
                ["tree_sha256"] = DigestEntries(first)
            };
        }

        private static (string Logical, string Physical)[] DiscoverAncestorControls(string root)
        {
            var controls = new SortedDictionary<string, string>(StringComparer.Ordinal);
            foreach (var logicalRoot in ProjectRoots.Append("tests/RunServicesSmoke"))
            {
                var current = Directory.GetParent(Combine(root, logicalRoot));
                while (current is not null)
                {
                    foreach (var name in AncestorControlNames)
                    {
                        var candidate = Combine(current.FullName, name);
                        var fileInfo = new FileInfo(candidate);
                        var directoryInfo = new DirectoryInfo(candidate);
                        fileInfo.Refresh();
                        directoryInfo.Refresh();
                        if (fileInfo.Exists
                            || directoryInfo.Exists
                            || fileInfo.LinkTarget is not null
                            || directoryInfo.LinkTarget is not null)
                        {
                            controls[candidate] = candidate;
                        }
                    }

                    current = current.Parent;
                }
            }

            return controls.Select(static item => (item.Key, item.Value)).ToArray();
        }

        private static JsonObject TreeRecord(
            string label,
            string root,
            IReadOnlySet<string> excludedDirectories)
        {
            var entries = StableTreeEntries(root, excludedDirectories);
            return new JsonObject
            {
                ["root"] = label,
                ["file_count"] = entries.Count,
                ["total_size_bytes"] = entries.Sum(static item => item.SizeBytes),
                ["tree_sha256"] = DigestEntries(entries)
            };
        }

        private static List<TreeEntry> StableTreeEntries(string root, IReadOnlySet<string> excludedDirectories)
        {
            var first = ScanTree(root, excludedDirectories);
            var second = ScanTree(root, excludedDirectories);
            if (!first.SequenceEqual(second))
            {
                throw new CampaignOsClosureCaptureException("tree_unstable");
            }

            return first;
        }

        private static List<TreeEntry> ScanTree(string root, IReadOnlySet<string> excludedDirectories)
        {
            var absoluteRoot = Path.GetFullPath(root);
            if (!IsSafeDirectory(absoluteRoot))
            {
                throw new CampaignOsClosureCaptureException("tree_root_invalid");
            }

            var entries = new List<TreeEntry>();
            long totalSize = 0;
            var pending = new Stack<string>();
            pending.Push(absoluteRoot);
            while (pending.Count > 0)
            {
                var directory = pending.Pop();
                if (!IsSafeDirectory(directory))
                {
                    throw new CampaignOsClosureCaptureException("tree_directory_invalid");
                }

                DirectoryInfo[] directories;
                FileInfo[] files;
                try
                {
                    var info = new DirectoryInfo(directory);
                    directories = info.EnumerateDirectories().OrderBy(static item => item.Name, StringComparer.Ordinal).ToArray();
                    files = info.EnumerateFiles().OrderBy(static item => item.Name, StringComparer.Ordinal).ToArray();
                }
                catch (Exception exception) when (exception is IOException
                                                   or UnauthorizedAccessException
                                                   or ArgumentException
                                                   or NotSupportedException)
                {
                    throw new CampaignOsClosureCaptureException("tree_scan_failed", exception);
                }

                for (var index = directories.Length - 1; index >= 0; index--)
                {
                    var child = directories[index];
                    child.Refresh();
                    if (child.LinkTarget is not null || (child.Attributes & FileAttributes.ReparsePoint) != 0)
                    {
                        throw new CampaignOsClosureCaptureException("tree_symlink");
                    }

                    if (!excludedDirectories.Contains(child.Name))
                    {
                        pending.Push(child.FullName);
                    }
                }

                foreach (var file in files)
                {
                    file.Refresh();
                    if (file.LinkTarget is not null
                        || (file.Attributes & (FileAttributes.ReparsePoint | FileAttributes.Directory | FileAttributes.Device)) != 0)
                    {
                        throw new CampaignOsClosureCaptureException("tree_non_regular");
                    }

                    var relative = Path.GetRelativePath(absoluteRoot, file.FullName).Replace('\\', '/');
                    if (!IsRelativeTreePath(relative))
                    {
                        throw new CampaignOsClosureCaptureException("tree_path_invalid");
                    }

                    var bytes = RequiredFile(file.FullName, allowEmpty: true);
                    entries.Add(new TreeEntry(relative, Sha256(bytes), bytes.LongLength));
                    totalSize = checked(totalSize + bytes.LongLength);
                    if (entries.Count > MaximumTreeFiles || totalSize > MaximumTreeBytes)
                    {
                        throw new CampaignOsClosureCaptureException("tree_bounds_exceeded");
                    }
                }
            }

            entries.Sort(static (left, right) => string.CompareOrdinal(left.Path, right.Path));
            if (entries.Select(static item => item.Path).Distinct(StringComparer.Ordinal).Count() != entries.Count)
            {
                throw new CampaignOsClosureCaptureException("tree_duplicate_path");
            }

            return entries;
        }

        private static JsonObject ExplicitFilesRecord(
            string label,
            IEnumerable<(string Logical, string Physical)> files)
        {
            var first = ScanExplicitFiles(files);
            var second = ScanExplicitFiles(files);
            if (!first.SequenceEqual(second))
            {
                throw new CampaignOsClosureCaptureException("explicit_files_unstable");
            }

            return new JsonObject
            {
                ["root"] = label,
                ["file_count"] = first.Count,
                ["total_size_bytes"] = first.Sum(static item => item.SizeBytes),
                ["tree_sha256"] = DigestEntries(first)
            };
        }

        private static List<TreeEntry> ScanExplicitFiles(IEnumerable<(string Logical, string Physical)> files)
        {
            var entries = new List<TreeEntry>();
            long totalSize = 0;
            var logicalPaths = new HashSet<string>(StringComparer.Ordinal);
            var physicalPaths = new HashSet<string>(StringComparer.Ordinal);
            foreach (var item in files.OrderBy(static item => item.Logical, StringComparer.Ordinal))
            {
                var physical = Path.GetFullPath(item.Physical);
                if (string.IsNullOrEmpty(item.Logical)
                    || !logicalPaths.Add(item.Logical)
                    || !physicalPaths.Add(physical))
                {
                    throw new CampaignOsClosureCaptureException("explicit_files_duplicate");
                }

                var bytes = RequiredFile(physical, allowEmpty: true);
                entries.Add(new TreeEntry(item.Logical, Sha256(bytes), bytes.LongLength));
                totalSize = checked(totalSize + bytes.LongLength);
                if (entries.Count > MaximumTreeFiles || totalSize > MaximumTreeBytes)
                {
                    throw new CampaignOsClosureCaptureException("tree_bounds_exceeded");
                }
            }

            return entries;
        }

        private static ManagedSelection SelectManagedVersion(string parent, string[] suffix)
        {
            if (!IsSafeDirectory(parent))
            {
                throw new CampaignOsClosureCaptureException("managed_dotnet_root_invalid");
            }

            var candidates = new List<ManagedSelection>();
            foreach (var entry in new DirectoryInfo(parent).EnumerateFileSystemInfos())
            {
                entry.Refresh();
                if (entry.LinkTarget is not null || (entry.Attributes & FileAttributes.ReparsePoint) != 0)
                {
                    throw new CampaignOsClosureCaptureException("managed_dotnet_symlink");
                }

                if (entry is not DirectoryInfo directory || !entry.Name.StartsWith("10.", StringComparison.Ordinal))
                {
                    continue;
                }

                if (!SdkVersionPattern.IsMatch(entry.Name))
                {
                    throw new CampaignOsClosureCaptureException("managed_dotnet_version_invalid");
                }

                var selected = suffix.Aggregate(directory.FullName, Path.Combine);
                if (IsSafeDirectory(selected))
                {
                    candidates.Add(new ManagedSelection(entry.Name, Path.GetFullPath(selected)));
                }
            }

            if (candidates.Count == 0)
            {
                throw new CampaignOsClosureCaptureException("managed_dotnet_version_missing");
            }

            candidates.Sort(static (left, right) => CompareManagedVersions(left.Version, right.Version));
            return candidates[^1];
        }

        private static int CompareManagedVersions(string left, string right)
        {
            var leftParts = Regex.Matches(left, "[0-9]+", RegexOptions.CultureInvariant)
                .Select(static match => NormalizeNumericVersionPart(match.Value)).ToArray();
            var rightParts = Regex.Matches(right, "[0-9]+", RegexOptions.CultureInvariant)
                .Select(static match => NormalizeNumericVersionPart(match.Value)).ToArray();
            var count = Math.Min(leftParts.Length, rightParts.Length);
            for (var index = 0; index < count; index++)
            {
                var comparison = leftParts[index].Length.CompareTo(rightParts[index].Length);
                if (comparison == 0)
                {
                    comparison = string.CompareOrdinal(leftParts[index], rightParts[index]);
                }

                if (comparison != 0)
                {
                    return comparison;
                }
            }

            var lengthComparison = leftParts.Length.CompareTo(rightParts.Length);
            return lengthComparison != 0 ? lengthComparison : string.CompareOrdinal(left, right);
        }

        private static string NormalizeNumericVersionPart(string value)
        {
            var normalized = value.TrimStart('0');
            return normalized.Length == 0 ? "0" : normalized;
        }

        private static bool IsSafeDirectory(string path)
        {
            try
            {
                var absolute = Path.GetFullPath(path);
                if (HasLinkedAncestor(absolute))
                {
                    return false;
                }

                var info = new DirectoryInfo(absolute);
                info.Refresh();
                return info.Exists
                       && info.LinkTarget is null
                       && (info.Attributes & (FileAttributes.ReparsePoint | FileAttributes.Device)) == 0;
            }
            catch (Exception exception) when (exception is IOException
                                               or UnauthorizedAccessException
                                               or ArgumentException
                                               or NotSupportedException)
            {
                return false;
            }
        }

        private static bool IsUnderRoot(string path, string root)
        {
            var relative = Path.GetRelativePath(root, path);
            return !Path.IsPathFullyQualified(relative)
                   && !relative.Equals("..", StringComparison.Ordinal)
                   && !relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal);
        }

        private static bool IsRelativeTreePath(string path)
        {
            return !string.IsNullOrEmpty(path)
                   && !Path.IsPathFullyQualified(path)
                   && !path.Contains('\\')
                   && path.Split('/').All(static part => part.Length > 0 && part is not "." and not "..");
        }

        private static byte[] RequiredFile(string path, bool allowEmpty = false)
        {
            var read = ReadStableFile(Path.GetFullPath(path), MaximumInputBytes, allowEmpty);
            if (read.Error is not null || read.Bytes is null)
            {
                throw new CampaignOsClosureCaptureException("closure_input_invalid");
            }

            return read.Bytes;
        }

        private static void EnsureTreeBounds(IReadOnlyCollection<TreeEntry> entries)
        {
            if (entries.Count > MaximumTreeFiles || entries.Sum(static item => item.SizeBytes) > MaximumTreeBytes)
            {
                throw new CampaignOsClosureCaptureException("tree_bounds_exceeded");
            }
        }

        private static string DigestEntries(IEnumerable<TreeEntry> entries)
        {
            var array = new JsonArray();
            foreach (var entry in entries)
            {
                array.Add(new JsonObject
                {
                    ["path"] = entry.Path,
                    ["sha256"] = entry.Sha256,
                    ["size_bytes"] = entry.SizeBytes
                });
            }

            return DigestNode(array);
        }

        private static string DigestNode(JsonNode node)
        {
            using var document = JsonDocument.Parse(
                node.ToJsonString(new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping }));
            return Sha256(CanonicalJson(document.RootElement));
        }

        private static JsonArray ToJsonArray(IEnumerable<JsonNode> values)
        {
            var result = new JsonArray();
            foreach (var value in values)
            {
                result.Add(value);
            }

            return result;
        }

        private static string Combine(string first, params string[] rest)
        {
            var result = first;
            foreach (var item in rest)
            {
                result = Path.Combine(result, item.Replace('/', Path.DirectorySeparatorChar));
            }

            return Path.GetFullPath(result);
        }

        private sealed record ProjectSpec(string Root, string ProjectFile, string PackageRoot);

        private sealed record TreeEntry(string Path, string Sha256, long SizeBytes);

        private sealed record ManagedSelection(string Version, string Path);
    }

    private static CampaignOsLocalProofEvaluation Invalid(string reasonCode) => new(false, reasonCode, null);
}

internal interface ICampaignOsClosureProvider
{
    JsonObject CaptureCandidateSourceBuildInputs(string canonRoot);

    JsonObject CaptureManagedDotnetClosure();
}

internal sealed class CampaignOsClosureCaptureException : Exception
{
    public CampaignOsClosureCaptureException(string message)
        : base(message)
    {
    }

    public CampaignOsClosureCaptureException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

public sealed record CampaignOsLocalProofEvaluation(
    bool IsValid,
    string ReasonCode,
    CampaignOsLocalProofSnapshot? Snapshot);

public sealed record CampaignOsLocalProofSnapshot(
    string Status,
    int ContractVersion,
    string RunId,
    DateTimeOffset StartedAt,
    DateTimeOffset CompletedAt,
    DateTimeOffset GeneratedAt,
    DateTimeOffset ExpiresAt,
    string ProofKind,
    string SourceFile,
    IReadOnlyList<string> JourneysPassed,
    CampaignOsLocalProofInputs Inputs,
    CampaignOsExecutionSnapshot Execution);

public sealed record CampaignOsLocalProofInputs(
    CampaignOsFileIdentity Source,
    CampaignOsFileIdentity JourneySpec,
    CampaignOsFileIdentity Runner,
    CampaignOsFileIdentity PrepareHelper,
    CampaignOsFileIdentity EnvironmentHelper,
    CampaignOsFileIdentity CleanroomBuilder,
    CampaignOsFileIdentity RegistryGlobalUsings,
    CampaignOsFileIdentity Materializer,
    CampaignOsFileIdentity ContractModule,
    CampaignOsDotnetIdentity DotnetHost,
    CampaignOsFileIdentity Csc,
    CampaignOsAssemblyIdentity Assembly);

public sealed record CampaignOsFileIdentity(string Path, string Sha256, long SizeBytes);

public sealed record CampaignOsDotnetIdentity(string Path, string ResolvedPath, string Sha256, long SizeBytes);

public sealed record CampaignOsAssemblyIdentity(string FileName, string Sha256, long SizeBytes);

public sealed record CampaignOsExecutionSnapshot(
    CampaignOsRuntimeManifest RuntimeManifestBefore,
    CampaignOsRuntimeManifest RuntimeManifestAfter,
    CampaignOsCheckpointLogIdentity CheckpointLog,
    IReadOnlyList<CampaignOsRuntimeCheckpoint> RuntimeCheckpoints);

public sealed record CampaignOsRuntimeManifest(
    string ManifestSha256,
    IReadOnlyList<CampaignOsManifestEntry> Entries);

public sealed record CampaignOsManifestEntry(string Path, string Sha256, long SizeBytes);

public sealed record CampaignOsCheckpointLogIdentity(string FileName, string Sha256, long SizeBytes);

public sealed record CampaignOsRuntimeCheckpoint(string CheckpointId, string RunId, string Status);
