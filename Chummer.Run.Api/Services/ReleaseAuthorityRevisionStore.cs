using System.Buffers.Binary;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

[JsonConverter(typeof(ReleaseAuthorityRevisionAdvanceRequestJsonConverter))]
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ReleaseAuthorityRevisionAdvanceRequest(
    string GenerationId,
    string ExpectedShelfPointerSha256,
    string ExpectedShelfInventoryDigest,
    byte[] PredecessorCurrentBytes,
    byte[] PredecessorSnapshotBytes,
    byte[] PredecessorDecisionBytes,
    byte[] SuccessorCurrentBytes,
    byte[] SuccessorSnapshotBytes,
    byte[] SuccessorDecisionBytes,
    byte[] ScorecardBytes,
    byte[] ConvergenceBytes);

public sealed class ReleaseAuthorityRevisionAdvanceRequestJsonConverter
    : JsonConverter<ReleaseAuthorityRevisionAdvanceRequest>
{
    private static readonly string[] ExactFields =
    [
        "generationId", "expectedShelfPointerSha256", "expectedShelfInventoryDigest",
        "predecessorCurrentBytes", "predecessorSnapshotBytes", "predecessorDecisionBytes",
        "successorCurrentBytes", "successorSnapshotBytes", "successorDecisionBytes",
        "scorecardBytes", "convergenceBytes"
    ];

    public override ReleaseAuthorityRevisionAdvanceRequest Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        using JsonDocument document = JsonDocument.ParseValue(ref reader);
        JsonElement root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object)
        {
            throw new JsonException("Release authority advance body must be a JSON object.");
        }

        var observed = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (JsonProperty property in root.EnumerateObject())
        {
            if (!observed.Add(property.Name))
            {
                throw new JsonException(
                    $"Release authority advance body contains duplicate or case-shadowed field '{property.Name}'.");
            }
        }
        if (observed.Count != ExactFields.Length
            || ExactFields.Any(field => !root.TryGetProperty(field, out _)))
        {
            throw new JsonException(
                "Release authority advance body contains unexpected, missing, or noncanonical fields.");
        }

        return new ReleaseAuthorityRevisionAdvanceRequest(
            RequiredString(root, "generationId"),
            RequiredString(root, "expectedShelfPointerSha256"),
            RequiredString(root, "expectedShelfInventoryDigest"),
            CanonicalBytes(root, "predecessorCurrentBytes", ReleaseAuthorityRevisionStore.MaximumCurrentBytes),
            CanonicalBytes(root, "predecessorSnapshotBytes", ReleaseAuthorityRevisionStore.MaximumSnapshotBytes),
            CanonicalBytes(root, "predecessorDecisionBytes", ReleaseAuthorityRevisionStore.MaximumDecisionBytes),
            CanonicalBytes(root, "successorCurrentBytes", ReleaseAuthorityRevisionStore.MaximumCurrentBytes),
            CanonicalBytes(root, "successorSnapshotBytes", ReleaseAuthorityRevisionStore.MaximumSnapshotBytes),
            CanonicalBytes(root, "successorDecisionBytes", ReleaseAuthorityRevisionStore.MaximumDecisionBytes),
            CanonicalBytes(root, "scorecardBytes", ReleaseAuthorityRevisionStore.MaximumProofBytes),
            CanonicalBytes(root, "convergenceBytes", ReleaseAuthorityRevisionStore.MaximumProofBytes));
    }

    public override void Write(
        Utf8JsonWriter writer,
        ReleaseAuthorityRevisionAdvanceRequest value,
        JsonSerializerOptions options)
    {
        writer.WriteStartObject();
        writer.WriteString("generationId", value.GenerationId);
        writer.WriteString("expectedShelfPointerSha256", value.ExpectedShelfPointerSha256);
        writer.WriteString("expectedShelfInventoryDigest", value.ExpectedShelfInventoryDigest);
        WriteBytes(writer, "predecessorCurrentBytes", value.PredecessorCurrentBytes);
        WriteBytes(writer, "predecessorSnapshotBytes", value.PredecessorSnapshotBytes);
        WriteBytes(writer, "predecessorDecisionBytes", value.PredecessorDecisionBytes);
        WriteBytes(writer, "successorCurrentBytes", value.SuccessorCurrentBytes);
        WriteBytes(writer, "successorSnapshotBytes", value.SuccessorSnapshotBytes);
        WriteBytes(writer, "successorDecisionBytes", value.SuccessorDecisionBytes);
        WriteBytes(writer, "scorecardBytes", value.ScorecardBytes);
        WriteBytes(writer, "convergenceBytes", value.ConvergenceBytes);
        writer.WriteEndObject();
    }

    private static string RequiredString(JsonElement root, string name)
    {
        JsonElement value = root.GetProperty(name);
        if (value.ValueKind != JsonValueKind.String)
        {
            throw new JsonException($"Release authority advance field '{name}' must be a string.");
        }
        return value.GetString() ?? string.Empty;
    }

    private static byte[] CanonicalBytes(JsonElement root, string name, int maximumBytes)
    {
        string encoded = RequiredString(root, name);
        int maximumEncodedLength = checked(((maximumBytes + 2) / 3) * 4);
        if (encoded.Length is < 4 || encoded.Length > maximumEncodedLength)
        {
            throw new JsonException($"Release authority advance field '{name}' has an invalid byte length.");
        }
        byte[] decoded;
        try
        {
            decoded = Convert.FromBase64String(encoded);
        }
        catch (FormatException exception)
        {
            throw new JsonException(
                $"Release authority advance field '{name}' must be canonical base64.",
                exception);
        }
        if (decoded.Length is < 1
            || decoded.Length > maximumBytes
            || !string.Equals(Convert.ToBase64String(decoded), encoded, StringComparison.Ordinal))
        {
            throw new JsonException(
                $"Release authority advance field '{name}' must be canonical bounded base64.");
        }
        return decoded;
    }

    private static void WriteBytes(Utf8JsonWriter writer, string name, byte[] bytes)
    {
        writer.WritePropertyName(name);
        writer.WriteBase64StringValue(bytes);
    }
}

public sealed record ReleaseAuthorityRevisionAdvanceResult(
    string GenerationId,
    string ReleaseVersion,
    string RevisionId,
    string PreviousDecisionStatus,
    string DecisionStatus,
    string SnapshotSha256,
    string DecisionSha256,
    string ScorecardSha256,
    string ConvergenceSha256,
    string JournalReceiptId,
    DateTimeOffset CommittedAtUtc,
    bool Recovered);

public sealed class ReleaseAuthorityRevisionConcurrencyException : InvalidOperationException
{
    public ReleaseAuthorityRevisionConcurrencyException(string message)
        : base(message)
    {
    }
}

internal enum ReleaseAuthorityRevisionCheckpoint
{
    IntentPersisted,
    RevisionPersisted,
    PointerReplaced
}

internal sealed class ReleaseAuthorityRevisionProcessTerminationSimulationException : IOException
{
    internal ReleaseAuthorityRevisionProcessTerminationSimulationException(string message)
        : base(message)
    {
    }
}

internal sealed record ReleaseAuthorityEnvelopeBytes(
    byte[] CurrentBytes,
    byte[] SnapshotBytes,
    byte[] DecisionBytes,
    string Source,
    string? RevisionId,
    string? JournalReceiptId,
    DateTimeOffset? CommittedAtUtc,
    string? ScorecardSha256,
    string? ConvergenceSha256);

/// <summary>
/// Persists a validated authority successor for an already sealed release shelf
/// generation. Authority revisions live beside, never inside, immutable generation
/// bytes. The compare-and-swap shares the exact promotion lock with shelf activation.
/// </summary>
public sealed class ReleaseAuthorityRevisionStore
{
    internal const string AuthorityRootDirectoryName = ".release-shelf-authority";
    internal const string AuthorityGenerationsDirectoryName = "generations";
    internal const string AuthorityJournalDirectoryName = "journal";
    internal const string AuthorityActiveIntentFileName = "active.json";
    internal const string AuthorityCurrentPointerFileName = "current.json";
    internal const string AuthorityRevisionsDirectoryName = "revisions";
    internal const string AuthorityRevisionDescriptorFileName = "revision.json";
    internal const string AuthorityScorecardFileName = "CAMPAIGN_OPERABILITY_SCORECARD.json";
    internal const string AuthorityConvergenceFileName = "LIVE_RELEASE_CONVERGENCE.json";

    private const string AuthorityPointerSchema = "chummer.release-shelf.authority-current/v1";
    private const string AuthorityRevisionSchema = "chummer.release-shelf.authority-revision/v1";
    private const string AuthorityIntentSchema = "chummer.release-shelf.authority-intent/v1";
    private const string AuthorityOutcomeSchema = "chummer.release-shelf.authority-outcome/v1";
    private const string AuthorityIntentFileName = "intent.json";
    private const string AuthorityOutcomeFileName = "outcome.json";
    private const int MaximumPointerBytes = 128 * 1024;
    internal const int MaximumCurrentBytes = 64 * 1024;
    internal const int MaximumSnapshotBytes = 4 * 1024 * 1024;
    internal const int MaximumDecisionBytes = 4 * 1024 * 1024;
    internal const int MaximumProofBytes = 8 * 1024 * 1024;
    internal const long MaximumAdvanceRequestBodyBytes = 64L * 1024L * 1024L;
    private const int MaximumDescriptorBytes = 256 * 1024;
    private const int MaximumJournalBytes = 512 * 1024;

    private static readonly Regex SafeGenerationId = new(
        "\\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex SafeArtifactId = new(
        "\\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex SafeRevisionId = new(
        "\\Aauth-[0-9a-f]{64}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex SafeReceiptId = new(
        "\\Aauthority-[0-9a-f]{32}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex LowerSha256 = new(
        "\\A[0-9a-f]{64}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex CanonicalToken = new(
        "\\A[a-z0-9][a-z0-9._-]{0,127}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex WindowsDrivePrefix = new(
        "\\A[a-zA-Z]:",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex TokenComponent = new(
        "[a-z0-9]+",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex CanonicalUtcSeconds = new(
        "\\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly string[] ScorecardSurfaces =
    [
        "desktop_workbench",
        "public_front_door_and_support",
        "install_claim_restore_continue",
        "build_explain_publish",
        "run_and_rejoin",
        "improve_and_close_the_loop"
    ];
    private static readonly string[] ScorecardDimensions =
    [
        "route_clarity",
        "rules_and_continuity_truth",
        "recovery_confidence",
        "closure_honesty",
        "responsiveness",
        "design_authorship"
    ];
    private static readonly string[] LocalPathMarkers =
    [
        "/tmp/", "/var/tmp/", "/docker/", "/workspace/", "/Users/", "/home/"
    ];
    private static readonly string[] CurrentReleaseConvergenceRoutes =
    [
        "/", "/now", "/changelog", "/downloads", "/downloads/concierge",
        "/status", "/artifacts", "/progress", "/help", "/now/concierge",
        "/now/concierge/read_notes", "/api/v1/public/progress-report",
        "/api/public/progress-report", "/api/v1/public/progress-poster.svg",
        "/api/public/progress-poster.svg", "/api/v1/public/weekly-pulse",
        "/api/public/weekly-pulse", "/api/public/release-truth",
        "/api/v1/install-linking/continuation",
        "/api/v1/install-linking/continuation/support",
        "/api/v1/install-linking/continuation/update",
        "/api/v1/install-linking/continuation/rollback",
        "/downloads/releases.json", "/downloads/RELEASE_CHANNEL.generated.json",
        "/Now/", "/Help/", "/Downloads/Concierge/", "/Now/Concierge/",
        "/Now/Concierge/read_notes/"
    ];
    private static readonly TimeSpan SuccessorProofMaximumAge = TimeSpan.FromHours(24);
    private static readonly TimeSpan SuccessorProofFutureSkew = TimeSpan.FromMinutes(5);

    private static readonly JsonDocumentOptions StrictDocumentOptions = new()
    {
        AllowTrailingCommas = false,
        CommentHandling = JsonCommentHandling.Disallow,
        MaxDepth = 64
    };
    private static readonly JsonSerializerOptions WriterOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        WriteIndented = true
    };

    private readonly IConfiguration _configuration;
    private readonly ReleaseShelfGenerationStore _shelfStore;
    private readonly Func<ReleaseShelfSnapshot, PublicReleaseManifestDto> _manifestLoader;
    private readonly TimeProvider _timeProvider;
    private readonly Action<ReleaseAuthorityRevisionCheckpoint>? _checkpoint;

    public ReleaseAuthorityRevisionStore(
        IConfiguration configuration,
        ReleaseShelfGenerationStore shelfStore,
        PublicReleaseManifestService releases,
        ReleaseSelectionService releaseSelection,
        ArtifactDeliveryPolicy artifactDelivery,
        TimeProvider? timeProvider = null)
        : this(
            configuration,
            shelfStore,
            snapshot => artifactDelivery.FilterRevokedArtifacts(
                snapshot,
                releaseSelection.ApplyAccessPolicy(releases.LoadManifest(snapshot))),
            timeProvider ?? TimeProvider.System,
            checkpoint: null)
    {
    }

    internal ReleaseAuthorityRevisionStore(
        IConfiguration configuration,
        ReleaseShelfGenerationStore shelfStore,
        Func<ReleaseShelfSnapshot, PublicReleaseManifestDto> manifestLoader,
        TimeProvider timeProvider,
        Action<ReleaseAuthorityRevisionCheckpoint>? checkpoint = null)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _shelfStore = shelfStore ?? throw new ArgumentNullException(nameof(shelfStore));
        _manifestLoader = manifestLoader ?? throw new ArgumentNullException(nameof(manifestLoader));
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        _checkpoint = checkpoint;
    }

    public Task<ReleaseAuthorityRevisionAdvanceResult> AdvancePreviewReadyAsync(
        ReleaseAuthorityRevisionAdvanceRequest request,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        ValidateRequestShape(request);

        string downloadsRoot = Path.GetFullPath(_shelfStore.ResolveDownloadsRoot());
        Directory.CreateDirectory(downloadsRoot);
        using FileStream mutationLock = ReleaseShelfPromotionLock.Acquire(downloadsRoot);
        cancellationToken.ThrowIfCancellationRequested();

        ReleaseShelfSnapshot shelf = _shelfStore.Capture();
        bool recovered = RecoverPendingTransactionUnderLock(downloadsRoot, shelf);
        shelf = _shelfStore.Capture();
        ValidateActiveShelfExpectation(shelf, request);
        cancellationToken.ThrowIfCancellationRequested();

        PublicReleaseManifestDto manifest = _manifestLoader(shelf);
        byte[] immutableManifestBytes = shelf.ReadVerifiedFileBytes(
                ReleaseShelfGenerationStore.CanonicalManifestFileName,
                ReleaseShelfGenerationStore.MaximumManifestBytes)
            ?? throw new InvalidDataException(
                "The active shelf canonical manifest no longer matches its immutable inventory binding.");

        PublicReleaseTruthProjectionDto predecessorProjection =
            PublicReleaseAuthorityEnvelopeProjection.Project(
                request.PredecessorCurrentBytes,
                request.PredecessorSnapshotBytes,
                request.PredecessorDecisionBytes,
                manifest,
                shelf.CanonicalManifestSha256,
                immutableManifestBytes);
        PublicReleaseTruthProjectionDto successorProjection =
            PublicReleaseAuthorityEnvelopeProjection.Project(
                request.SuccessorCurrentBytes,
                request.SuccessorSnapshotBytes,
                request.SuccessorDecisionBytes,
                manifest,
                shelf.CanonicalManifestSha256,
                immutableManifestBytes);

        ReleaseAuthorityEnvelopeBytes current = ResolveEffectiveEnvelope(shelf)
            ?? throw new InvalidDataException(
                "The active release shelf has no complete review-required authority seed.");
        bool exactCommittedSuccessor = EnvelopeEqualsSuccessor(current, request)
            && current.RevisionId is not null
            && current.JournalReceiptId is not null
            && current.CommittedAtUtc is not null
            && current.ScorecardSha256 is not null
            && current.ConvergenceSha256 is not null;

        ValidateSuccessorProofClosure(
            request,
            predecessorProjection,
            successorProjection,
            manifest,
            _timeProvider.GetUtcNow().ToUniversalTime(),
            enforceObservedFreshness: !exactCommittedSuccessor);

        if (EnvelopeEqualsSuccessor(current, request))
        {
            if (current.RevisionId is null
                || current.JournalReceiptId is null
                || current.CommittedAtUtc is null
                || current.ScorecardSha256 is null
                || current.ConvergenceSha256 is null)
            {
                throw new InvalidDataException(
                    "The effective successor authority lacks committed revision metadata.");
            }

            return Task.FromResult(new ReleaseAuthorityRevisionAdvanceResult(
                shelf.GenerationId!,
                shelf.ReleaseVersion!,
                current.RevisionId,
                predecessorProjection.ReleaseDecisionStatus,
                successorProjection.ReleaseDecisionStatus,
                Sha256(request.SuccessorSnapshotBytes),
                Sha256(request.SuccessorDecisionBytes),
                current.ScorecardSha256,
                current.ConvergenceSha256,
                current.JournalReceiptId,
                current.CommittedAtUtc.Value,
                recovered));
        }

        if (!EnvelopeEqualsPredecessor(current, request))
        {
            throw new ReleaseAuthorityRevisionConcurrencyException(
                "The supplied predecessor is not the current committed authority revision for this generation.");
        }

        ReleaseAuthorityRevisionAdvanceResult result = PersistSuccessorUnderLock(
            shelf,
            request,
            predecessorProjection,
            successorProjection,
            cancellationToken);
        return Task.FromResult(result with { Recovered = recovered });
    }

    /// <summary>
    /// Resolves only a fully committed authority overlay. Absence permits the sealed
    /// generation envelope; any present-but-invalid overlay fails closed.
    /// </summary>
    internal static ReleaseAuthorityEnvelopeBytes? TryResolveCommittedRevision(
        ReleaseShelfSnapshot shelf)
    {
        ArgumentNullException.ThrowIfNull(shelf);
        if (shelf.IsLegacy)
        {
            return null;
        }

        string authorityRoot = ResolveExactDirectoryOrMissing(
            shelf.DownloadsRoot,
            AuthorityRootDirectoryName,
            "release authority root");
        if (authorityRoot.Length == 0)
        {
            return null;
        }

        string generationsRoot = ResolveExactDirectory(
            authorityRoot,
            AuthorityGenerationsDirectoryName,
            "release authority generations root");
        string generationRoot = ResolveExactDirectoryOrMissing(
            generationsRoot,
            shelf.GenerationId!,
            "release authority generation");
        if (generationRoot.Length == 0)
        {
            return null;
        }

        string pointerPath = ResolveExactFile(
            generationRoot,
            AuthorityCurrentPointerFileName,
            "release authority generation pointer");
        byte[] pointerBytes = ReadBoundedRegularFile(
            pointerPath,
            MaximumPointerBytes,
            "release authority generation pointer");
        AuthorityPointerDocument pointer = ParseAuthorityPointer(pointerBytes);
        ValidatePointerShelfBinding(pointer, shelf);

        string revisionsRoot = ResolveExactDirectory(
            generationRoot,
            AuthorityRevisionsDirectoryName,
            "release authority revisions root");
        string revisionRoot = ResolveExactDirectory(
            revisionsRoot,
            pointer.RevisionId,
            "release authority revision");
        RequireExactDirectoryEntries(
            revisionRoot,
            [
                PublicReleaseAuthorityEnvelopeProjection.CurrentInventoryPath.Split('/')[^1],
                PublicReleaseAuthorityEnvelopeProjection.SnapshotInventoryPath.Split('/')[^1],
                PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath,
                AuthorityScorecardFileName,
                AuthorityConvergenceFileName,
                AuthorityRevisionDescriptorFileName
            ],
            "release authority revision");

        byte[] currentBytes = ReadRevisionFile(
            revisionRoot,
            "CURRENT.json",
            MaximumCurrentBytes);
        byte[] snapshotBytes = ReadRevisionFile(
            revisionRoot,
            "SNAPSHOT.json",
            MaximumSnapshotBytes);
        byte[] decisionBytes = ReadRevisionFile(
            revisionRoot,
            PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath,
            MaximumDecisionBytes);
        byte[] scorecardBytes = ReadRevisionFile(
            revisionRoot,
            AuthorityScorecardFileName,
            MaximumProofBytes);
        byte[] convergenceBytes = ReadRevisionFile(
            revisionRoot,
            AuthorityConvergenceFileName,
            MaximumProofBytes);
        byte[] descriptorBytes = ReadRevisionFile(
            revisionRoot,
            AuthorityRevisionDescriptorFileName,
            MaximumDescriptorBytes);

        RequireDigest(pointer.CurrentSha256, currentBytes, "authority pointer currentSha256");
        RequireDigest(pointer.SnapshotSha256, snapshotBytes, "authority pointer snapshotSha256");
        RequireDigest(pointer.DecisionSha256, decisionBytes, "authority pointer decisionSha256");
        RequireDigest(pointer.ScorecardSha256, scorecardBytes, "authority pointer scorecardSha256");
        RequireDigest(pointer.ConvergenceSha256, convergenceBytes, "authority pointer convergenceSha256");
        RequireDigest(pointer.RevisionSha256, descriptorBytes, "authority pointer revisionSha256");

        AuthorityRevisionDocument descriptor = ParseRevisionDescriptor(descriptorBytes);
        ValidateDescriptorMatchesPointer(descriptor, pointer);
        ValidateCommittedJournal(shelf.DownloadsRoot, pointer, pointerBytes);

        return new ReleaseAuthorityEnvelopeBytes(
            currentBytes,
            snapshotBytes,
            decisionBytes,
            "authority_revision",
            pointer.RevisionId,
            pointer.JournalReceiptId,
            ParseUtc(pointer.CommittedAtUtc, "authority pointer committedAtUtc"),
            pointer.ScorecardSha256,
            pointer.ConvergenceSha256);
    }

    internal static void EnsureNoUnresolvedAuthorityMutation(string downloadsRoot)
    {
        string authorityRoot = ResolveExactDirectoryOrMissing(
            downloadsRoot,
            AuthorityRootDirectoryName,
            "release authority root");
        if (authorityRoot.Length == 0)
        {
            return;
        }

        string active = ResolveExactFileOrMissing(
            authorityRoot,
            AuthorityActiveIntentFileName,
            "active release authority intent");
        if (active.Length > 0)
        {
            throw new ReleaseShelfMutationConcurrencyException(
                "a release authority compare-and-swap requires recovery before shelf mutation.");
        }

        string journalRoot = ResolveExactDirectoryOrMissing(
            authorityRoot,
            AuthorityJournalDirectoryName,
            "release authority journal root");
        if (journalRoot.Length == 0)
        {
            return;
        }

        string[] receiptRoots = Directory.EnumerateFileSystemEntries(journalRoot).ToArray();
        if (receiptRoots.Length > 10_000)
        {
            throw new InvalidDataException(
                "Release authority journal contains an unreasonable number of receipts.");
        }
        foreach (string receiptRoot in receiptRoots)
        {
            string receiptId = Path.GetFileName(receiptRoot);
            if (!SafeReceiptId.IsMatch(receiptId))
            {
                throw new InvalidDataException(
                    "Release authority journal contains a noncanonical receipt entry.");
            }
            EnsureRegularDirectory(receiptRoot, "release authority journal receipt");
            string[] entries = Directory.EnumerateFileSystemEntries(receiptRoot)
                .Select(static path => Path.GetFileName(path))
                .OrderBy(static name => name, StringComparer.Ordinal)
                .ToArray();
            if (!entries.SequenceEqual(
                    [AuthorityIntentFileName, AuthorityOutcomeFileName],
                    StringComparer.Ordinal))
            {
                if (entries.SequenceEqual([AuthorityIntentFileName], StringComparer.Ordinal))
                {
                    throw new ReleaseShelfMutationConcurrencyException(
                        "a release authority journal intent requires recovery before shelf mutation.");
                }
                throw new InvalidDataException(
                    "Release authority journal receipt contains unexpected or missing entries.");
            }
            string intent = ResolveExactFile(
                receiptRoot,
                AuthorityIntentFileName,
                "release authority journal intent");
            AuthorityIntentDocument intentDocument = ParseAuthorityIntent(
                ReadBoundedRegularFile(
                    intent,
                    MaximumJournalBytes,
                    "release authority journal intent"));
            string outcome = ResolveExactFile(
                receiptRoot,
                AuthorityOutcomeFileName,
                "release authority journal outcome");
            AuthorityOutcomeDocument outcomeDocument = ParseAuthorityOutcome(
                ReadBoundedRegularFile(
                    outcome,
                    MaximumJournalBytes,
                    "release authority journal outcome"));
            ValidateOutcome(outcomeDocument, intentDocument);
        }
    }

    private ReleaseAuthorityEnvelopeBytes? ResolveEffectiveEnvelope(ReleaseShelfSnapshot shelf)
        => TryResolveCommittedRevision(shelf) ?? ReadSealedEnvelope(shelf);

    private static ReleaseAuthorityEnvelopeBytes? ReadSealedEnvelope(ReleaseShelfSnapshot shelf)
    {
        bool hasCurrent = shelf.Inventory.ContainsKey(
            PublicReleaseAuthorityEnvelopeProjection.CurrentInventoryPath);
        bool hasSnapshot = shelf.Inventory.ContainsKey(
            PublicReleaseAuthorityEnvelopeProjection.SnapshotInventoryPath);
        if (!hasCurrent && !hasSnapshot)
        {
            return null;
        }

        if (!hasCurrent || !hasSnapshot)
        {
            throw new InvalidDataException(
                "The sealed release generation contains a partial authority envelope.");
        }

        string decisionPath = "release-evidence/" +
            PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath;
        if (!shelf.Inventory.ContainsKey(decisionPath))
        {
            throw new InvalidDataException(
                "The sealed release generation omits its release decision sibling.");
        }

        return new ReleaseAuthorityEnvelopeBytes(
            shelf.ReadVerifiedFileBytes(
                    PublicReleaseAuthorityEnvelopeProjection.CurrentInventoryPath,
                    MaximumCurrentBytes)
                ?? throw new InvalidDataException("Sealed CURRENT.json failed inventory verification."),
            shelf.ReadVerifiedFileBytes(
                    PublicReleaseAuthorityEnvelopeProjection.SnapshotInventoryPath,
                    MaximumSnapshotBytes)
                ?? throw new InvalidDataException("Sealed SNAPSHOT.json failed inventory verification."),
            shelf.ReadVerifiedFileBytes(decisionPath, MaximumDecisionBytes)
                ?? throw new InvalidDataException("Sealed RELEASE_DECISION.json failed inventory verification."),
            "sealed_generation",
            RevisionId: null,
            JournalReceiptId: null,
            CommittedAtUtc: null,
            ScorecardSha256: null,
            ConvergenceSha256: null);
    }

    private ReleaseAuthorityRevisionAdvanceResult PersistSuccessorUnderLock(
        ReleaseShelfSnapshot shelf,
        ReleaseAuthorityRevisionAdvanceRequest request,
        PublicReleaseTruthProjectionDto predecessorProjection,
        PublicReleaseTruthProjectionDto successorProjection,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        string generationId = shelf.GenerationId!;
        string releaseVersion = shelf.ReleaseVersion!;
        string currentSha256 = Sha256(request.SuccessorCurrentBytes);
        string snapshotSha256 = Sha256(request.SuccessorSnapshotBytes);
        string decisionSha256 = Sha256(request.SuccessorDecisionBytes);
        string scorecardSha256 = Sha256(request.ScorecardBytes);
        string convergenceSha256 = Sha256(request.ConvergenceBytes);
        string predecessorSnapshotSha256 = Sha256(request.PredecessorSnapshotBytes);
        string predecessorDecisionSha256 = Sha256(request.PredecessorDecisionBytes);
        string revisionId = BuildRevisionId(shelf, request);
        string receiptId = $"authority-{Guid.NewGuid():N}";
        DateTimeOffset committedAtUtc = _timeProvider.GetUtcNow().ToUniversalTime();
        string committedAt = FormatUtc(committedAtUtc);

        var descriptor = new AuthorityRevisionDocument(
            AuthorityRevisionSchema,
            generationId,
            releaseVersion,
            shelf.PointerDigest!,
            "sha256:" + shelf.InventoryDigest,
            revisionId,
            predecessorSnapshotSha256,
            predecessorDecisionSha256,
            currentSha256,
            snapshotSha256,
            decisionSha256,
            scorecardSha256,
            convergenceSha256,
            receiptId,
            committedAt);
        byte[] descriptorBytes = SerializeDocument(descriptor);
        var pointer = new AuthorityPointerDocument(
            AuthorityPointerSchema,
            generationId,
            releaseVersion,
            shelf.PointerDigest!,
            "sha256:" + shelf.InventoryDigest,
            revisionId,
            Sha256(descriptorBytes),
            predecessorSnapshotSha256,
            predecessorDecisionSha256,
            currentSha256,
            snapshotSha256,
            decisionSha256,
            scorecardSha256,
            convergenceSha256,
            receiptId,
            committedAt);
        byte[] targetPointerBytes = SerializeDocument(pointer);

        string authorityRoot = EnsureOwnerOnlyDirectory(
            Path.Combine(shelf.DownloadsRoot, AuthorityRootDirectoryName));
        string generationsRoot = EnsureOwnerOnlyDirectory(
            Path.Combine(authorityRoot, AuthorityGenerationsDirectoryName));
        string journalRoot = EnsureOwnerOnlyDirectory(
            Path.Combine(authorityRoot, AuthorityJournalDirectoryName));
        string generationRoot = Path.Combine(generationsRoot, generationId);
        string pointerPath = Path.Combine(generationRoot, AuthorityCurrentPointerFileName);
        byte[]? previousPointerBytes = File.Exists(pointerPath)
            ? ReadBoundedRegularFile(pointerPath, MaximumPointerBytes, "previous authority pointer")
            : null;
        string? previousPointerSha256 = previousPointerBytes is null
            ? null
            : Sha256(previousPointerBytes);

        var intent = new AuthorityIntentDocument(
            AuthorityIntentSchema,
            "prepared",
            generationId,
            releaseVersion,
            revisionId,
            receiptId,
            shelf.PointerDigest!,
            "sha256:" + shelf.InventoryDigest,
            previousPointerSha256,
            previousPointerBytes is null ? null : Convert.ToBase64String(previousPointerBytes),
            Sha256(targetPointerBytes),
            Convert.ToBase64String(targetPointerBytes),
            committedAt);
        byte[] intentBytes = SerializeDocument(intent);
        string activePath = Path.Combine(authorityRoot, AuthorityActiveIntentFileName);

        try
        {
            WriteOwnerOnlyFileAtomically(activePath, intentBytes, overwrite: false);
            PersistJournalIntent(journalRoot, receiptId, intentBytes);
            _checkpoint?.Invoke(ReleaseAuthorityRevisionCheckpoint.IntentPersisted);

            cancellationToken.ThrowIfCancellationRequested();
            string revisionRoot = PersistRevision(
                generationsRoot,
                generationId,
                revisionId,
                descriptorBytes,
                request);
            _ = revisionRoot;
            _checkpoint?.Invoke(ReleaseAuthorityRevisionCheckpoint.RevisionPersisted);

            cancellationToken.ThrowIfCancellationRequested();
            Directory.CreateDirectory(generationRoot);
            SetOwnerOnlyDirectoryMode(generationRoot);
            WriteOwnerOnlyFileAtomically(pointerPath, targetPointerBytes, overwrite: true);
            _checkpoint?.Invoke(ReleaseAuthorityRevisionCheckpoint.PointerReplaced);

            WriteJournalOutcome(
                journalRoot,
                intent,
                state: "committed",
                _timeProvider.GetUtcNow().ToUniversalTime());
            DeleteFileDurably(activePath);
        }
        catch (ReleaseAuthorityRevisionProcessTerminationSimulationException)
        {
            throw;
        }
        catch
        {
            try
            {
                RecoverPendingTransactionUnderLock(shelf.DownloadsRoot, shelf);
            }
            catch
            {
                // The original failure remains actionable. A later retry will run
                // the same deterministic recovery while holding the shared lock.
            }

            throw;
        }

        return new ReleaseAuthorityRevisionAdvanceResult(
            generationId,
            releaseVersion,
            revisionId,
            predecessorProjection.ReleaseDecisionStatus,
            successorProjection.ReleaseDecisionStatus,
            snapshotSha256,
            decisionSha256,
            scorecardSha256,
            convergenceSha256,
            receiptId,
            committedAtUtc,
            Recovered: false);
    }

    private bool RecoverPendingTransactionUnderLock(
        string downloadsRoot,
        ReleaseShelfSnapshot shelf)
    {
        string authorityRoot = ResolveExactDirectoryOrMissing(
            downloadsRoot,
            AuthorityRootDirectoryName,
            "release authority root");
        if (authorityRoot.Length == 0)
        {
            return false;
        }

        string activePath = ResolveExactFileOrMissing(
            authorityRoot,
            AuthorityActiveIntentFileName,
            "active release authority intent");
        if (activePath.Length == 0)
        {
            return false;
        }

        byte[] activeBytes = ReadBoundedRegularFile(
            activePath,
            MaximumJournalBytes,
            "active release authority intent");
        AuthorityIntentDocument intent = ParseAuthorityIntent(activeBytes);
        if (shelf.IsLegacy
            || !string.Equals(shelf.GenerationId, intent.GenerationId, StringComparison.Ordinal)
            || !FixedDigestEquals(shelf.PointerDigest!, intent.ShelfPointerSha256)
            || !string.Equals(
                "sha256:" + shelf.InventoryDigest,
                intent.ShelfInventoryDigest,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Pending release authority intent no longer binds the active release shelf.");
        }

        string journalRoot = EnsureOwnerOnlyDirectory(
            Path.Combine(authorityRoot, AuthorityJournalDirectoryName));
        PersistJournalIntent(journalRoot, intent.JournalReceiptId, activeBytes);
        AuthorityOutcomeDocument? existingOutcome = TryReadJournalOutcome(
            journalRoot,
            intent.JournalReceiptId);
        string generationsRoot = EnsureOwnerOnlyDirectory(
            Path.Combine(authorityRoot, AuthorityGenerationsDirectoryName));
        string generationRoot = Path.Combine(generationsRoot, intent.GenerationId);
        string pointerPath = Path.Combine(generationRoot, AuthorityCurrentPointerFileName);
        byte[] targetPointerBytes = DecodeCanonicalBase64(
            intent.TargetPointerBase64,
            MaximumPointerBytes,
            "authority intent target pointer");
        RequireDigest(
            intent.TargetPointerSha256,
            targetPointerBytes,
            "authority intent targetPointerSha256");
        byte[]? previousPointerBytes = intent.PreviousPointerBase64 is null
            ? null
            : DecodeCanonicalBase64(
                intent.PreviousPointerBase64,
                MaximumPointerBytes,
                "authority intent previous pointer");
        if (previousPointerBytes is null != (intent.PreviousPointerSha256 is null))
        {
            throw new InvalidDataException(
                "Authority intent previous pointer closure is partial.");
        }
        if (previousPointerBytes is not null)
        {
            RequireDigest(
                intent.PreviousPointerSha256!,
                previousPointerBytes,
                "authority intent previousPointerSha256");
        }

        byte[]? actualPointerBytes = File.Exists(pointerPath)
            ? ReadBoundedRegularFile(pointerPath, MaximumPointerBytes, "authority pointer during recovery")
            : null;
        bool targetVisible = ByteExact(actualPointerBytes, targetPointerBytes);
        bool previousVisible = previousPointerBytes is null
            ? actualPointerBytes is null
            : ByteExact(actualPointerBytes, previousPointerBytes);

        if (existingOutcome is not null)
        {
            ValidateOutcome(existingOutcome, intent);
            if (existingOutcome.State == "committed" && !targetVisible
                || existingOutcome.State == "aborted" && !previousVisible)
            {
                throw new InvalidDataException(
                    "Release authority journal outcome contradicts its visible pointer.");
            }

            DeleteFileDurably(activePath);
            return true;
        }

        if (targetVisible)
        {
            AuthorityPointerDocument pointer = ParseAuthorityPointer(targetPointerBytes);
            ValidatePointerShelfBinding(pointer, shelf);
            ValidatePersistedRevisionWithoutJournal(downloadsRoot, pointer);
            WriteJournalOutcome(
                journalRoot,
                intent,
                "committed",
                _timeProvider.GetUtcNow().ToUniversalTime());
        }
        else if (previousVisible)
        {
            RemoveAbortedRevision(generationsRoot, intent);
            WriteJournalOutcome(
                journalRoot,
                intent,
                "aborted",
                _timeProvider.GetUtcNow().ToUniversalTime());
        }
        else
        {
            throw new InvalidDataException(
                "Release authority recovery found neither the previous nor target pointer bytes.");
        }

        DeleteFileDurably(activePath);
        return true;
    }

    private static void ValidateActiveShelfExpectation(
        ReleaseShelfSnapshot shelf,
        ReleaseAuthorityRevisionAdvanceRequest request)
    {
        if (shelf.IsLegacy || shelf.IsExplicitGeneration)
        {
            throw new InvalidOperationException(
                "Release authority advancement requires the active layout-v1 shelf generation.");
        }

        if (!string.Equals(shelf.GenerationId, request.GenerationId, StringComparison.Ordinal))
        {
            throw new ReleaseAuthorityRevisionConcurrencyException(
                "The active shelf generation changed before authority advancement.");
        }

        string pointerPath = Path.Combine(
            shelf.DownloadsRoot,
            ReleaseShelfGenerationStore.CurrentPointerFileName);
        byte[] actualPointerBytes = ReadBoundedRegularFile(
            pointerPath,
            MaximumPointerBytes,
            "active release shelf pointer");
        string actualPointerSha256 = Sha256(actualPointerBytes);
        if (!FixedDigestEquals(actualPointerSha256, shelf.PointerDigest!)
            || !FixedDigestEquals(actualPointerSha256, request.ExpectedShelfPointerSha256))
        {
            throw new ReleaseAuthorityRevisionConcurrencyException(
                "The active shelf pointer bytes changed before authority advancement.");
        }

        string actualInventoryDigest = ReleaseShelfGenerationStore.ComputeInventoryDigest(
            shelf.PhysicalRoot);
        string expectedInventoryDigest = "sha256:" + actualInventoryDigest;
        if (!FixedDigestEquals(actualInventoryDigest, shelf.InventoryDigest!)
            || !string.Equals(
                expectedInventoryDigest,
                request.ExpectedShelfInventoryDigest,
                StringComparison.Ordinal))
        {
            throw new ReleaseAuthorityRevisionConcurrencyException(
                "The active shelf inventory changed before authority advancement.");
        }
    }

    private static void ValidateRequestShape(ReleaseAuthorityRevisionAdvanceRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.GenerationId)
            || !SafeGenerationId.IsMatch(request.GenerationId))
        {
            throw new InvalidDataException(
                "Authority advance generationId is not a traversal-safe opaque token.");
        }

        RequireSha256(request.ExpectedShelfPointerSha256, "expected shelf pointer digest");
        if (request.ExpectedShelfInventoryDigest is null
            || !request.ExpectedShelfInventoryDigest.StartsWith("sha256:", StringComparison.Ordinal)
            || request.ExpectedShelfInventoryDigest.Length != 71)
        {
            throw new InvalidDataException(
                "Expected shelf inventory digest must use exact sha256:<lower-hex> form.");
        }
        RequireSha256(
            request.ExpectedShelfInventoryDigest[7..],
            "expected shelf inventory digest");

        RequireInputBytes(request.PredecessorCurrentBytes, MaximumCurrentBytes, "predecessor CURRENT.json");
        RequireInputBytes(request.PredecessorSnapshotBytes, MaximumSnapshotBytes, "predecessor SNAPSHOT.json");
        RequireInputBytes(request.PredecessorDecisionBytes, MaximumDecisionBytes, "predecessor RELEASE_DECISION.json");
        RequireInputBytes(request.SuccessorCurrentBytes, MaximumCurrentBytes, "successor CURRENT.json");
        RequireInputBytes(request.SuccessorSnapshotBytes, MaximumSnapshotBytes, "successor SNAPSHOT.json");
        RequireInputBytes(request.SuccessorDecisionBytes, MaximumDecisionBytes, "successor RELEASE_DECISION.json");
        RequireInputBytes(request.ScorecardBytes, MaximumProofBytes, "campaign-operability scorecard");
        RequireInputBytes(request.ConvergenceBytes, MaximumProofBytes, "live convergence receipt");
    }

    private static void RequireInputBytes(byte[]? bytes, int maximumBytes, string label)
    {
        if (bytes is null || bytes.Length is < 1 || bytes.Length > maximumBytes)
        {
            throw new InvalidDataException($"{label} has an invalid byte length.");
        }
    }

    private static bool EnvelopeEqualsPredecessor(
        ReleaseAuthorityEnvelopeBytes envelope,
        ReleaseAuthorityRevisionAdvanceRequest request)
        => ByteExact(envelope.CurrentBytes, request.PredecessorCurrentBytes)
           && ByteExact(envelope.SnapshotBytes, request.PredecessorSnapshotBytes)
           && ByteExact(envelope.DecisionBytes, request.PredecessorDecisionBytes);

    private static bool EnvelopeEqualsSuccessor(
        ReleaseAuthorityEnvelopeBytes envelope,
        ReleaseAuthorityRevisionAdvanceRequest request)
        => ByteExact(envelope.CurrentBytes, request.SuccessorCurrentBytes)
           && ByteExact(envelope.SnapshotBytes, request.SuccessorSnapshotBytes)
           && ByteExact(envelope.DecisionBytes, request.SuccessorDecisionBytes);

    private static string BuildRevisionId(
        ReleaseShelfSnapshot shelf,
        ReleaseAuthorityRevisionAdvanceRequest request)
    {
        using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        AppendHashPart(hash, "generation", Encoding.UTF8.GetBytes(shelf.GenerationId!));
        AppendHashPart(hash, "shelf-pointer", Encoding.ASCII.GetBytes(shelf.PointerDigest!));
        AppendHashPart(hash, "shelf-inventory", Encoding.ASCII.GetBytes(shelf.InventoryDigest!));
        AppendHashPart(hash, "predecessor-current", request.PredecessorCurrentBytes);
        AppendHashPart(hash, "predecessor-snapshot", request.PredecessorSnapshotBytes);
        AppendHashPart(hash, "predecessor-decision", request.PredecessorDecisionBytes);
        AppendHashPart(hash, "successor-current", request.SuccessorCurrentBytes);
        AppendHashPart(hash, "successor-snapshot", request.SuccessorSnapshotBytes);
        AppendHashPart(hash, "successor-decision", request.SuccessorDecisionBytes);
        AppendHashPart(hash, "scorecard", request.ScorecardBytes);
        AppendHashPart(hash, "convergence", request.ConvergenceBytes);
        return "auth-" + Convert.ToHexStringLower(hash.GetHashAndReset());
    }

    private static void AppendHashPart(IncrementalHash hash, string label, ReadOnlySpan<byte> bytes)
    {
        byte[] labelBytes = Encoding.UTF8.GetBytes(label);
        Span<byte> length = stackalloc byte[8];
        BinaryPrimitives.WriteInt32BigEndian(length[..4], labelBytes.Length);
        BinaryPrimitives.WriteInt32BigEndian(length[4..], bytes.Length);
        hash.AppendData(length);
        hash.AppendData(labelBytes);
        hash.AppendData(bytes);
    }

    private static void ValidateSuccessorProofClosure(
        ReleaseAuthorityRevisionAdvanceRequest request,
        PublicReleaseTruthProjectionDto predecessor,
        PublicReleaseTruthProjectionDto successor,
        PublicReleaseManifestDto manifest,
        DateTimeOffset observedAtUtc,
        bool enforceObservedFreshness)
    {
        if (!string.Equals(
                predecessor.ReleaseDecisionStatus,
                "review_required",
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Release authority predecessor must be the review-required seed.");
        }
        if (!string.Equals(
                successor.ReleaseDecisionStatus,
                "preview_ready",
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Release authority successor must be preview_ready.");
        }

        DateTimeOffset predecessorGeneratedAt;
        DateTimeOffset manifestGeneratedAt;
        using (JsonDocument predecessorDecisionDocument = ParseStrictJson(
                   request.PredecessorDecisionBytes,
                   "predecessor RELEASE_DECISION.json"))
        {
            JsonElement predecessorDecision = predecessorDecisionDocument.RootElement;
            foreach (string propertyName in new[]
                     {
                         "authoritySnapshotSha256", "candidateDecisionStatus",
                         "candidateDecisionSha256", "scorecardSha256", "convergenceSha256"
                     })
            {
                if (RequireString(
                        predecessorDecision,
                        propertyName,
                        128,
                        allowEmpty: true).Length != 0)
                {
                    throw new InvalidDataException(
                        "Review-required predecessor must be an unadvanced authority seed with empty proof closure.");
                }
            }
            predecessorGeneratedAt = ParseCanonicalUtcSeconds(
                RequireString(predecessorDecision, "generatedAt", 128),
                "review predecessor generatedAt");
            manifestGeneratedAt = ParseCanonicalUtcSeconds(
                RequireString(predecessorDecision, "manifestGeneratedAt", 128),
                "review predecessor manifestGeneratedAt");
        }

        using JsonDocument decisionDocument = ParseStrictJson(
            request.SuccessorDecisionBytes,
            "successor RELEASE_DECISION.json");
        JsonElement decision = decisionDocument.RootElement;
        DateTimeOffset successorGeneratedAt = ParseCanonicalUtcSeconds(
            RequireString(decision, "generatedAt", 128),
            "preview successor generatedAt");
        DateTimeOffset successorManifestGeneratedAt = ParseCanonicalUtcSeconds(
            RequireString(decision, "manifestGeneratedAt", 128),
            "preview successor manifestGeneratedAt");
        string predecessorSnapshotSha256 = Sha256(request.PredecessorSnapshotBytes);
        string predecessorDecisionSha256 = Sha256(request.PredecessorDecisionBytes);
        string scorecardSha256 = Sha256(request.ScorecardBytes);
        string convergenceSha256 = Sha256(request.ConvergenceBytes);
        if (!string.Equals(
                RequireString(decision, "candidateDecisionStatus", 128),
                "review_required",
                StringComparison.Ordinal)
            || !FixedDigestEquals(
                RequireSha256Property(decision, "authoritySnapshotSha256"),
                predecessorSnapshotSha256)
            || !FixedDigestEquals(
                RequireSha256Property(decision, "candidateDecisionSha256"),
                predecessorDecisionSha256)
            || !FixedDigestEquals(
                RequireSha256Property(decision, "scorecardSha256"),
                scorecardSha256)
            || !FixedDigestEquals(
                RequireSha256Property(decision, "convergenceSha256"),
                convergenceSha256))
        {
            throw new InvalidDataException(
                "Preview-ready authority does not bind the exact predecessor and proof bytes.");
        }

        if (successorManifestGeneratedAt != manifestGeneratedAt)
        {
            throw new InvalidDataException(
                "Review predecessor and preview successor disagree on manifest chronology.");
        }

        DateTimeOffset scorecardGeneratedAt = ValidateScorecardBytes(request.ScorecardBytes);
        DateTimeOffset convergenceGeneratedAt = ValidateConvergenceBytes(
            request.ConvergenceBytes,
            predecessor,
            predecessorSnapshotSha256,
            predecessorDecisionSha256,
            manifest.Downloads.Select(static artifact => artifact.Id).ToArray());
        ValidateSuccessorProofChronology(
            successorGeneratedAt,
            manifestGeneratedAt,
            predecessorGeneratedAt,
            scorecardGeneratedAt,
            convergenceGeneratedAt,
            observedAtUtc,
            enforceObservedFreshness);
    }

    private static DateTimeOffset ValidateScorecardBytes(ReadOnlyMemory<byte> bytes)
    {
        using JsonDocument document = ParseStrictJson(bytes, "campaign-operability scorecard");
        JsonElement scorecard = document.RootElement;
        RequireExactObject(
            scorecard,
            [
                "contract_name", "contract_version", "generated_at_utc", "status", "verdict",
                "preview_status", "preview_verdict", "stable_status", "stable_verdict",
                "rubric_path", "journey_gate_path", "required_surfaces", "required_dimensions",
                "summary", "cells", "preview_failures", "flagship_gaps", "failures"
            ],
            "campaign-operability scorecard");
        if (!string.Equals(
                RequireString(scorecard, "contract_name", 128),
                "chummer.campaign_operability_scorecard",
                StringComparison.Ordinal)
            || RequireBoundedInt(scorecard, "contract_version", 0, 4096) != 2
            || !string.Equals(RequireString(scorecard, "preview_status", 128), "pass", StringComparison.Ordinal)
            || !string.Equals(
                RequireString(scorecard, "preview_verdict", 128),
                "CAMPAIGN_OPERABILITY_PREVIEW_READY",
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Campaign-operability scorecard must be the preview-ready version-2 contract.");
        }
        DateTimeOffset generatedAtUtc = ParseCanonicalUtcSeconds(
            RequireString(scorecard, "generated_at_utc", 128),
            "scorecard generated_at_utc");
        ValidatePortableEvidencePath(
            RequireString(scorecard, "rubric_path", 2048),
            "scorecard rubric_path");
        ValidatePortableEvidencePath(
            RequireString(scorecard, "journey_gate_path", 2048),
            "scorecard journey_gate_path");
        RequireEmptyArray(scorecard, "preview_failures", "campaign-operability scorecard");

        string[] surfaces = RequireCanonicalTokenArray(
            scorecard,
            "required_surfaces",
            allowEmpty: false,
            maximumCount: 32);
        string[] dimensions = RequireCanonicalTokenArray(
            scorecard,
            "required_dimensions",
            allowEmpty: false,
            maximumCount: 32);
        if (!surfaces.SequenceEqual(ScorecardSurfaces, StringComparer.Ordinal)
            || !dimensions.SequenceEqual(ScorecardDimensions, StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                "Campaign-operability scorecard does not declare the exact ordered v2 matrix.");
        }
        JsonElement cells = RequireArray(scorecard, "cells", "campaign-operability scorecard");
        if (cells.GetArrayLength() != 36)
        {
            throw new InvalidDataException(
                "Campaign-operability scorecard must contain exactly 36 cells.");
        }

        var observed = new HashSet<string>(StringComparer.Ordinal);
        var scores = new List<int>(36);
        var expectedTopGaps = new List<string>(36);
        foreach (JsonElement cell in cells.EnumerateArray())
        {
            if (cell.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidDataException("Campaign-operability scorecard cells must be objects.");
            }
            RequireExactObject(
                cell,
                [
                    "surface_id", "dimension_id", "score", "preview_status", "stable_status",
                    "owners", "preview_owners", "next_actions", "journey_ids", "evidence_ids",
                    "evidence", "preview_blockers", "flagship_gaps", "failures"
                ],
                "campaign-operability scorecard cell");
            string surface = RequireCanonicalToken(cell, "surface_id");
            string dimension = RequireCanonicalToken(cell, "dimension_id");
            int score = RequireBoundedInt(cell, "score", 0, 3);
            if (score < 2
                || !surfaces.Contains(surface, StringComparer.Ordinal)
                || !dimensions.Contains(dimension, StringComparer.Ordinal)
                || !observed.Add(surface + "\0" + dimension))
            {
                throw new InvalidDataException(
                    "Every scorecard cell must uniquely cover the declared 6x6 matrix at score 2 or 3.");
            }
            if (RequireString(cell, "preview_status", 128) != "pass"
                || RequireString(cell, "stable_status", 128) != (score == 3 ? "pass" : "fail"))
            {
                throw new InvalidDataException(
                    "Campaign-operability cell preview/stable posture contradicts its score.");
            }
            _ = RequireCanonicalTokenArray(
                cell,
                "owners",
                allowEmpty: false,
                maximumCount: 32);
            RequireEmptyArray(cell, "preview_blockers", "campaign-operability cell");

            string[] journeyIds = RequireCanonicalTokenArray(
                cell,
                "journey_ids",
                allowEmpty: false,
                maximumCount: 32);
            string[] evidenceIds = RequireCanonicalTokenArray(
                cell,
                "evidence_ids",
                allowEmpty: false,
                maximumCount: 32);
            if (journeyIds.Intersect(evidenceIds, StringComparer.Ordinal).Any())
            {
                throw new InvalidDataException(
                    "Campaign-operability journey and evidence IDs must be disjoint.");
            }
            JsonElement evidenceRows = RequireArray(cell, "evidence", "campaign-operability cell");
            if (evidenceRows.GetArrayLength() == 0
                || evidenceRows.GetArrayLength() > 64
                || evidenceRows.GetArrayLength() != journeyIds.Length + evidenceIds.Length)
            {
                throw new InvalidDataException(
                    "Campaign-operability cell evidence inventory contradicts its declared IDs.");
            }
            var scoreTwoOwners = new SortedSet<string>(StringComparer.Ordinal);
            var scoreTwoActions = new List<string>();
            var stableGaps = new List<string>();
            var observedEvidenceIds = new List<string>();
            int minimumEvidenceScore = 3;
            foreach (JsonElement evidence in evidenceRows.EnumerateArray())
            {
                if (evidence.ValueKind != JsonValueKind.Object)
                {
                    throw new InvalidDataException("Campaign-operability evidence rows must be objects.");
                }
                string[] fieldNames = evidence.EnumerateObject()
                    .Select(static property => property.Name)
                    .OrderBy(static value => value, StringComparer.Ordinal)
                    .ToArray();
                string[] journeyFields =
                [
                    "bounded_owner", "failure", "generated_at", "id", "next_actions",
                    "path", "preview_failure", "score", "source_status", "status"
                ];
                string[] receiptFields =
                [
                    "bounded_owner", "failure", "generated_at", "id", "next_actions",
                    "path", "preview_failure", "score", "source_status", "source_verdict", "status"
                ];
                if (!fieldNames.SequenceEqual(journeyFields, StringComparer.Ordinal)
                    && !fieldNames.SequenceEqual(receiptFields, StringComparer.Ordinal))
                {
                    throw new InvalidDataException(
                        "Campaign-operability evidence row has unexpected or missing fields.");
                }
                string evidenceId = RequireCanonicalToken(evidence, "id");
                observedEvidenceIds.Add(evidenceId);
                ValidatePortableEvidencePath(
                    RequireString(evidence, "path", 2048),
                    "campaign-operability evidence path");
                string sourceStatus = RequireCanonicalToken(evidence, "source_status");
                if (IsUnresolvedToken(sourceStatus)
                    || TokenComponent.Matches(sourceStatus)
                        .Select(static match => match.Value)
                        .Any(IsSentinelToken))
                {
                    throw new InvalidDataException(
                        "Campaign-operability evidence source_status is unresolved.");
                }
                if (evidence.TryGetProperty("source_verdict", out _))
                {
                    string sourceVerdict = RequireString(
                        evidence,
                        "source_verdict",
                        256,
                        allowEmpty: true);
                    if (sourceVerdict.Length != 0 && IsUnresolvedToken(sourceVerdict))
                    {
                        throw new InvalidDataException(
                            "Campaign-operability evidence source_verdict is unresolved.");
                    }
                }
                _ = ParseUtc(
                    RequireString(evidence, "generated_at", 128),
                    "campaign-operability evidence generated_at");
                int evidenceScore = RequireBoundedInt(evidence, "score", 0, 3);
                if (evidenceScore is not (2 or 3))
                {
                    throw new InvalidDataException(
                        "Preview-ready scorecard evidence must be at score 2 or 3.");
                }
                minimumEvidenceScore = Math.Min(minimumEvidenceScore, evidenceScore);
                string evidenceStatus = RequireString(evidence, "status", 128);
                string owner = RequireString(evidence, "bounded_owner", 128, allowEmpty: true);
                string[] actions = RequireConcreteTextArray(
                    evidence,
                    "next_actions",
                    allowEmpty: true,
                    maximumCount: 32);
                string failure = RequireString(evidence, "failure", 512, allowEmpty: true);
                string previewFailure = RequireString(evidence, "preview_failure", 512, allowEmpty: true);
                if (previewFailure.Length != 0
                    || evidenceScore == 2
                       && (evidenceStatus != "preview"
                           || !CanonicalToken.IsMatch(owner)
                           || IsUnresolvedToken(owner)
                           || actions.Length == 0
                           || failure.Length == 0
                           || IsUnresolvedToken(failure))
                    || evidenceScore == 3
                       && (evidenceStatus != "pass"
                           || owner.Length != 0
                           || actions.Length != 0
                           || failure.Length != 0))
                {
                    throw new InvalidDataException(
                        "Campaign-operability evidence score lacks its required owner/action or stable binding.");
                }
                if (evidenceScore == 2)
                {
                    scoreTwoOwners.Add(owner);
                    foreach (string action in actions)
                    {
                        if (!scoreTwoActions.Contains(action, StringComparer.Ordinal))
                        {
                            scoreTwoActions.Add(action);
                        }
                    }
                    stableGaps.Add(failure);
                }
            }
            string[] expectedEvidenceIds = journeyIds.Concat(evidenceIds).ToArray();
            if (!observedEvidenceIds.SequenceEqual(expectedEvidenceIds, StringComparer.Ordinal)
                || minimumEvidenceScore != score
                || !RequireCanonicalTokenArray(
                        cell,
                        "preview_owners",
                        allowEmpty: true,
                        maximumCount: 32)
                    .SequenceEqual(scoreTwoOwners, StringComparer.Ordinal)
                || !RequireConcreteTextArray(
                        cell,
                        "next_actions",
                        allowEmpty: true,
                        maximumCount: 32)
                    .SequenceEqual(scoreTwoActions, StringComparer.Ordinal))
            {
                throw new InvalidDataException(
                    "Campaign-operability cell aggregates contradict their evidence rows.");
            }
            string[] flagshipGaps = RequireOrderedTextArray(
                cell,
                "flagship_gaps",
                allowEmpty: true,
                maximumCount: 64);
            string[] failures = RequireOrderedTextArray(
                cell,
                "failures",
                allowEmpty: true,
                maximumCount: 64);
            if (!flagshipGaps.SequenceEqual(stableGaps, StringComparer.Ordinal)
                || !failures.SequenceEqual(stableGaps, StringComparer.Ordinal))
            {
                throw new InvalidDataException(
                    "Campaign-operability cell stable gaps contradict its evidence.");
            }
            if (score == 2
                && (scoreTwoOwners.Count == 0
                    || scoreTwoActions.Count == 0
                    || stableGaps.Count == 0)
                || score == 3
                   && (scoreTwoOwners.Count != 0
                       || scoreTwoActions.Count != 0
                       || stableGaps.Count != 0))
            {
                throw new InvalidDataException(
                    "Campaign-operability cell preview-only state contradicts its score.");
            }
            if (stableGaps.Count > 0)
            {
                expectedTopGaps.Add(
                    $"{surface}.{dimension}: {string.Join(", ", stableGaps)}");
            }
            scores.Add(score);
        }
        if (observed.Count != surfaces.Length * dimensions.Length)
        {
            throw new InvalidDataException(
                "Campaign-operability scorecard does not cover the exact 6x6 matrix.");
        }

        JsonElement summary = RequireObject(scorecard, "summary", "campaign-operability scorecard");
        RequireExactObject(
            summary,
            [
                "surface_count", "dimension_count", "cell_count", "score_0_count",
                "score_1_count", "score_2_count", "score_3_count", "at_least_2_count",
                "below_2_count", "below_3_count", "minimum_score"
            ],
            "campaign-operability scorecard summary");
        if (RequireBoundedInt(summary, "surface_count", 0, 4096) != 6
            || RequireBoundedInt(summary, "dimension_count", 0, 4096) != 6
            || RequireBoundedInt(summary, "cell_count", 0, 4096) != 36
            || RequireBoundedInt(summary, "score_0_count", 0, 4096) != 0
            || RequireBoundedInt(summary, "score_1_count", 0, 4096) != 0
            || RequireBoundedInt(summary, "score_2_count", 0, 4096) != scores.Count(static score => score == 2)
            || RequireBoundedInt(summary, "score_3_count", 0, 4096) != scores.Count(static score => score == 3)
            || RequireBoundedInt(summary, "at_least_2_count", 0, 4096) != 36
            || RequireBoundedInt(summary, "below_2_count", 0, 4096) != 0
            || RequireBoundedInt(summary, "below_3_count", 0, 4096) != scores.Count(static score => score < 3)
            || RequireBoundedInt(summary, "minimum_score", 0, 4096) != scores.Min())
        {
            throw new InvalidDataException(
                "Campaign-operability scorecard summary contradicts its 36 cells.");
        }
        bool stableReady = scores.All(static score => score == 3);
        string expectedStableStatus = stableReady ? "pass" : "fail";
        string expectedStableVerdict = stableReady
            ? "CAMPAIGN_OPERABILITY_READY"
            : "CAMPAIGN_OPERABILITY_NOT_READY";
        if (RequireString(scorecard, "stable_status", 128) != expectedStableStatus
            || RequireString(scorecard, "stable_verdict", 128) != expectedStableVerdict
            || RequireString(scorecard, "status", 128) != expectedStableStatus
            || RequireString(scorecard, "verdict", 128) != expectedStableVerdict)
        {
            throw new InvalidDataException(
                "Campaign-operability stable posture contradicts its 36 cells.");
        }
        string[] topFlagshipGaps = RequireUniqueTextArray(
            scorecard,
            "flagship_gaps",
            allowEmpty: true,
            maximumCount: 64);
        string[] topFailures = RequireUniqueTextArray(
            scorecard,
            "failures",
            allowEmpty: true,
            maximumCount: 64);
        if (!topFlagshipGaps.SequenceEqual(expectedTopGaps, StringComparer.Ordinal)
            || !topFailures.SequenceEqual(expectedTopGaps, StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                "Campaign-operability whole-product stable gaps contradict its cells.");
        }
        return generatedAtUtc;
    }

    private static DateTimeOffset ValidateConvergenceBytes(
        ReadOnlyMemory<byte> bytes,
        PublicReleaseTruthProjectionDto predecessor,
        string predecessorSnapshotSha256,
        string predecessorDecisionSha256,
        IReadOnlyList<string> artifactIds)
    {
        using JsonDocument document = ParseStrictJson(bytes, "live release convergence receipt");
        JsonElement receipt = document.RootElement;
        RequireExactObject(
            receipt,
            [
                "contractName", "contractVersion", "generatedAtUtc", "status", "mismatchCount",
                "failureCount", "mismatches", "failures", "authorityRoute", "checkedRouteCount",
                "checkedRoutes", "comparedFields", "releaseTruth", "manifestSha256",
                "releaseDecisionStatus", "releaseDecisionSha256", "authoritySnapshotSha256"
            ],
            "live release convergence receipt");
        if (!string.Equals(
                RequireString(receipt, "contractName", 128),
                "chummer.live-release-convergence/v1",
                StringComparison.Ordinal)
            || RequireBoundedInt(receipt, "contractVersion", 0, 4096) != 1
            || !string.Equals(RequireString(receipt, "status", 128), "pass", StringComparison.Ordinal)
            || RequireBoundedInt(receipt, "mismatchCount", 0, 4096) != 0
            || RequireBoundedInt(receipt, "failureCount", 0, 4096) != 0)
        {
            throw new InvalidDataException(
                "Live release convergence receipt must be a version-1 zero-failure pass.");
        }
        DateTimeOffset generatedAtUtc = ParseCanonicalUtcSeconds(
            RequireString(receipt, "generatedAtUtc", 128),
            "convergence generatedAtUtc");
        RequireEmptyArray(receipt, "mismatches", "live release convergence receipt");
        RequireEmptyArray(receipt, "failures", "live release convergence receipt");

        string authorityRoute = RequireSafePublicRoute(
            receipt,
            "authorityRoute",
            "convergence authority route");
        if (authorityRoute != "/api/v1/public/release-truth")
        {
            throw new InvalidDataException(
                "Convergence authority route must be the exact CURRENT release-truth route.");
        }
        string[] checkedRoutes = RequireSafeRouteArray(receipt, "checkedRoutes");
        if (checkedRoutes.Length == 0
            || RequireBoundedInt(receipt, "checkedRouteCount", 0, 4096) != checkedRoutes.Length
            || !checkedRoutes.SequenceEqual(
                checkedRoutes.Distinct(StringComparer.Ordinal).OrderBy(static route => route, StringComparer.Ordinal),
                StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                "Convergence checked routes must be non-empty, unique, and ordinally sorted.");
        }
        var requiredRoutes = new HashSet<string>(
            CurrentReleaseConvergenceRoutes,
            StringComparer.Ordinal);
        var checkedRouteSet = new HashSet<string>(checkedRoutes, StringComparer.Ordinal);
        string[] missingRoutes = requiredRoutes.Except(checkedRouteSet, StringComparer.Ordinal)
            .OrderBy(static route => route, StringComparer.Ordinal)
            .ToArray();
        if (missingRoutes.Length != 0)
        {
            throw new InvalidDataException(
                $"Convergence checked routes omit canonical CURRENT routes: {string.Join(", ", missingRoutes)}.");
        }
        var canonicalArtifactIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (string artifactId in artifactIds)
        {
            if (string.IsNullOrWhiteSpace(artifactId)
                || !SafeArtifactId.IsMatch(artifactId)
                || !canonicalArtifactIds.Add(artifactId))
            {
                throw new InvalidDataException(
                    "Release manifest artifact IDs are not unique route-safe opaque tokens.");
            }
        }
        string[] extraRoutes = checkedRouteSet.Except(requiredRoutes, StringComparer.Ordinal)
            .OrderBy(static route => route, StringComparer.Ordinal)
            .ToArray();
        if (canonicalArtifactIds.Count == 0)
        {
            if (extraRoutes.Length != 0)
            {
                throw new InvalidDataException(
                    "Convergence checked routes exceed the artifact-free CURRENT denominator.");
            }
        }
        else if (extraRoutes.Length != 1
                 || !canonicalArtifactIds.Contains(
                     extraRoutes[0].StartsWith("/downloads/install/", StringComparison.Ordinal)
                         ? extraRoutes[0]["/downloads/install/".Length..]
                         : string.Empty))
        {
            throw new InvalidDataException(
                "Convergence checked routes must add exactly one artifact-bound CURRENT install route.");
        }
        int expectedRouteCount = requiredRoutes.Count + (canonicalArtifactIds.Count == 0 ? 0 : 1);
        if (checkedRouteSet.Count != expectedRouteCount)
        {
            throw new InvalidDataException(
                "Convergence checked routes do not exactly match the CURRENT route denominator.");
        }

        string[] comparedFields = RequireStringArray(receipt, "comparedFields", maximumCount: 32);
        string[] expectedComparedFields =
        [
            "releaseVersion", "channel", "releaseStatus", "rolloutState", "supportabilityState",
            "availablePlatforms", "primaryHeadByPlatform", "artifactCount", "downloadAccessPosture",
            "knownIssueSummary", "manifestSha256", "registryCommit", "releaseDecisionStatus",
            "releaseDecisionSha256"
        ];
        if (!comparedFields.SequenceEqual(expectedComparedFields, StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                "Convergence comparedFields is not the exact release-truth field set.");
        }

        JsonElement truth = RequireObject(receipt, "releaseTruth", "convergence receipt");
        RequireExactObject(
            truth,
            [
                "contractName", "releaseVersion", "channel", "releaseStatus", "rolloutState",
                "supportabilityState", "availablePlatforms", "primaryHeadByPlatform", "artifactCount",
                "downloadAccessPosture", "knownIssueSummary", "manifestSha256", "registryCommit",
                "releaseDecisionStatus", "releaseDecisionSha256"
            ],
            "convergence releaseTruth");
        if (!string.Equals(
                RequireString(truth, "contractName", 128),
                PublicReleaseTruthProjectionDto.Schema,
                StringComparison.Ordinal)
            || !string.Equals(RequireString(truth, "releaseVersion", 128), predecessor.ReleaseVersion, StringComparison.Ordinal)
            || !string.Equals(RequireString(truth, "channel", 128), predecessor.Channel, StringComparison.Ordinal)
            || !string.Equals(RequireString(truth, "releaseStatus", 128), predecessor.ReleaseStatus, StringComparison.Ordinal)
            || !string.Equals(RequireString(truth, "rolloutState", 128), predecessor.RolloutState, StringComparison.Ordinal)
            || !string.Equals(RequireString(truth, "supportabilityState", 128), predecessor.SupportabilityState, StringComparison.Ordinal)
            || !string.Equals(RequireString(truth, "downloadAccessPosture", 128), predecessor.DownloadAccessPosture, StringComparison.Ordinal)
            || !string.Equals(RequireString(truth, "knownIssueSummary", 512, allowEmpty: true), predecessor.KnownIssueSummary, StringComparison.Ordinal)
            || !FixedDigestEquals(RequireSha256Property(truth, "manifestSha256"), predecessor.ManifestSha256)
            || !string.Equals(RequireString(truth, "registryCommit", 128), predecessor.RegistryCommit, StringComparison.Ordinal)
            || !string.Equals(RequireString(truth, "releaseDecisionStatus", 128), "review_required", StringComparison.Ordinal)
            || !FixedDigestEquals(RequireSha256Property(truth, "releaseDecisionSha256"), predecessorDecisionSha256)
            || RequireBoundedInt(truth, "artifactCount", 0, 4096) != predecessor.ArtifactCount
            || !JsonStringArrayEquals(truth.GetProperty("availablePlatforms"), predecessor.AvailablePlatforms)
            || !JsonStringMapEquals(truth.GetProperty("primaryHeadByPlatform"), predecessor.PrimaryHeadByPlatform))
        {
            throw new InvalidDataException(
                "Convergence releaseTruth does not bind the exact review-required predecessor projection.");
        }

        if (!FixedDigestEquals(
                RequireSha256Property(receipt, "manifestSha256"),
                predecessor.ManifestSha256)
            || !string.Equals(
                RequireString(receipt, "releaseDecisionStatus", 128),
                "review_required",
                StringComparison.Ordinal)
            || !FixedDigestEquals(
                RequireSha256Property(receipt, "releaseDecisionSha256"),
                predecessorDecisionSha256)
            || !FixedDigestEquals(
                RequireSha256Property(receipt, "authoritySnapshotSha256"),
                predecessorSnapshotSha256))
        {
            throw new InvalidDataException(
                "Convergence top-level authority bindings contradict the review predecessor.");
        }
        return generatedAtUtc;
    }

    private static void ValidateSuccessorProofChronology(
        DateTimeOffset successorGeneratedAt,
        DateTimeOffset manifestGeneratedAt,
        DateTimeOffset predecessorGeneratedAt,
        DateTimeOffset scorecardGeneratedAt,
        DateTimeOffset convergenceGeneratedAt,
        DateTimeOffset observedAtUtc,
        bool enforceObservedFreshness)
    {
        if (predecessorGeneratedAt < manifestGeneratedAt)
        {
            throw new InvalidDataException(
                "Review predecessor generatedAt must not predate the manifest.");
        }
        DateTimeOffset proofFloor = predecessorGeneratedAt > manifestGeneratedAt
            ? predecessorGeneratedAt
            : manifestGeneratedAt;
        if (successorGeneratedAt < proofFloor)
        {
            throw new InvalidDataException(
                "Preview successor generatedAt must not predate its manifest or review predecessor.");
        }
        if (enforceObservedFreshness
            && (successorGeneratedAt > observedAtUtc + SuccessorProofFutureSkew
                || observedAtUtc - successorGeneratedAt > SuccessorProofMaximumAge))
        {
            throw new InvalidDataException(
                "Preview successor generatedAt is outside the live 24-hour authority window.");
        }
        foreach ((string Label, DateTimeOffset GeneratedAt) proof in new[]
                 {
                     ("scorecard generated_at_utc", scorecardGeneratedAt),
                     ("convergence generatedAtUtc", convergenceGeneratedAt)
                 })
        {
            if (proof.GeneratedAt < proofFloor)
            {
                throw new InvalidDataException(
                    $"{proof.Label} must not predate the manifest or review predecessor.");
            }
            if (proof.GeneratedAt > successorGeneratedAt + SuccessorProofFutureSkew)
            {
                throw new InvalidDataException(
                    $"{proof.Label} exceeds the fixed five-minute successor clock-skew allowance.");
            }
            if (successorGeneratedAt - proof.GeneratedAt > SuccessorProofMaximumAge
                || enforceObservedFreshness
                   && observedAtUtc - proof.GeneratedAt > SuccessorProofMaximumAge)
            {
                throw new InvalidDataException(
                    $"{proof.Label} exceeds the fixed 24-hour proof age budget.");
            }
        }
        if (scorecardGeneratedAt < convergenceGeneratedAt)
        {
            throw new InvalidDataException(
                "Campaign-operability scorecard must be generated after CURRENT convergence.");
        }
    }

    private static DateTimeOffset ParseCanonicalUtcSeconds(string value, string label)
    {
        if (!CanonicalUtcSeconds.IsMatch(value))
        {
            throw new InvalidDataException(
                $"{label} must use canonical UTC seconds (YYYY-MM-DDTHH:mm:ssZ).");
        }
        DateTimeOffset parsed = ParseUtc(value, label);
        if (parsed.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture) != value)
        {
            throw new InvalidDataException($"{label} is not a valid canonical UTC timestamp.");
        }
        return parsed;
    }

    private static JsonDocument ParseStrictJson(ReadOnlyMemory<byte> bytes, string label)
    {
        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(bytes, StrictDocumentOptions);
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException($"{label} is not strict JSON.", ex);
        }
        try
        {
            RejectDuplicateProperties(document.RootElement, label, depth: 0);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidDataException($"{label} must be a JSON object.");
            }
            return document;
        }
        catch
        {
            document.Dispose();
            throw;
        }
    }

    private static void RejectDuplicateProperties(JsonElement element, string label, int depth)
    {
        if (depth > StrictDocumentOptions.MaxDepth)
        {
            throw new InvalidDataException($"{label} exceeds the JSON nesting limit.");
        }
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (!names.Add(property.Name))
                {
                    throw new InvalidDataException(
                        $"{label} contains duplicate or case-shadowed property '{property.Name}'.");
                }
                RejectDuplicateProperties(property.Value, label, depth + 1);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in element.EnumerateArray())
            {
                RejectDuplicateProperties(item, label, depth + 1);
            }
        }
    }

    private static void RequireExactObject(
        JsonElement source,
        IReadOnlyCollection<string> expected,
        string label)
    {
        if (source.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException($"{label} must be an object.");
        }
        string[] actual = source.EnumerateObject()
            .Select(static property => property.Name)
            .OrderBy(static name => name, StringComparer.Ordinal)
            .ToArray();
        string[] required = expected.OrderBy(static name => name, StringComparer.Ordinal).ToArray();
        if (!actual.SequenceEqual(required, StringComparer.Ordinal))
        {
            throw new InvalidDataException($"{label} has unexpected or missing properties.");
        }
    }

    private static string RequireString(
        JsonElement source,
        string propertyName,
        int maximumLength,
        bool allowEmpty = false)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement value)
            || value.ValueKind != JsonValueKind.String)
        {
            throw new InvalidDataException($"{propertyName} must be a string.");
        }
        string text = value.GetString() ?? string.Empty;
        if (!string.Equals(text, text.Trim(), StringComparison.Ordinal)
            || text.Length > maximumLength
            || !allowEmpty && text.Length == 0)
        {
            throw new InvalidDataException($"{propertyName} must be a canonical bounded string.");
        }
        return text;
    }

    private static string RequireCanonicalToken(JsonElement source, string propertyName)
    {
        string value = RequireString(source, propertyName, 128);
        if (!CanonicalToken.IsMatch(value) || value is "unknown" or "missing" or "invalid")
        {
            throw new InvalidDataException($"{propertyName} must be a canonical lower-case token.");
        }
        return value;
    }

    private static string RequireSha256Property(JsonElement source, string propertyName)
    {
        string value = RequireString(source, propertyName, 64);
        RequireSha256(value, propertyName);
        return value;
    }

    private static int RequireBoundedInt(
        JsonElement source,
        string propertyName,
        int minimum,
        int maximum)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement value)
            || value.ValueKind != JsonValueKind.Number
            || !value.TryGetInt32(out int result)
            || result < minimum
            || result > maximum)
        {
            throw new InvalidDataException($"{propertyName} must be a bounded integer.");
        }
        return result;
    }

    private static JsonElement RequireArray(JsonElement source, string propertyName, string label)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement value)
            || value.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException($"{label} {propertyName} must be an array.");
        }
        return value;
    }

    private static JsonElement RequireObject(JsonElement source, string propertyName, string label)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement value)
            || value.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException($"{label} {propertyName} must be an object.");
        }
        return value;
    }

    private static void RequireEmptyArray(JsonElement source, string propertyName, string label)
    {
        JsonElement value = RequireArray(source, propertyName, label);
        if (value.GetArrayLength() != 0)
        {
            throw new InvalidDataException($"{label} {propertyName} must be empty.");
        }
    }

    private static string[] RequireCanonicalTokenArray(
        JsonElement source,
        string propertyName,
        bool allowEmpty,
        int maximumCount)
    {
        JsonElement array = RequireArray(source, propertyName, "scorecard");
        if (array.GetArrayLength() > maximumCount
            || !allowEmpty && array.GetArrayLength() == 0)
        {
            throw new InvalidDataException($"{propertyName} must be a bounded token array.");
        }
        string[] values = array.EnumerateArray().Select(item =>
        {
            if (item.ValueKind != JsonValueKind.String)
            {
                throw new InvalidDataException($"{propertyName} entries must be strings.");
            }
            string token = item.GetString() ?? string.Empty;
            if (!CanonicalToken.IsMatch(token) || IsUnresolvedToken(token))
            {
                throw new InvalidDataException(
                    $"{propertyName} entries must be resolved canonical tokens.");
            }
            return token;
        }).ToArray();
        if (values.Distinct(StringComparer.Ordinal).Count() != values.Length)
        {
            throw new InvalidDataException($"{propertyName} entries must be unique.");
        }
        return values;
    }

    private static string[] RequireStringArray(
        JsonElement source,
        string propertyName,
        int maximumCount)
    {
        JsonElement array = RequireArray(source, propertyName, "JSON document");
        if (array.GetArrayLength() > maximumCount)
        {
            throw new InvalidDataException($"{propertyName} exceeds the entry limit.");
        }
        return array.EnumerateArray().Select(item =>
        {
            if (item.ValueKind != JsonValueKind.String)
            {
                throw new InvalidDataException($"{propertyName} entries must be strings.");
            }
            string value = item.GetString() ?? string.Empty;
            if (value.Length == 0 || value.Length > 512 || value != value.Trim())
            {
                throw new InvalidDataException($"{propertyName} entries must be canonical bounded strings.");
            }
            return value;
        }).ToArray();
    }

    private static string[] RequireConcreteTextArray(
        JsonElement source,
        string propertyName,
        bool allowEmpty,
        int maximumCount)
    {
        string[] values = RequireStringArray(source, propertyName, maximumCount);
        if (!allowEmpty && values.Length == 0)
        {
            throw new InvalidDataException($"{propertyName} must not be empty.");
        }
        if (values.Any(IsUnresolvedToken))
        {
            throw new InvalidDataException($"{propertyName} contains an unresolved value.");
        }
        return values;
    }

    private static string[] RequireOrderedTextArray(
        JsonElement source,
        string propertyName,
        bool allowEmpty,
        int maximumCount)
    {
        string[] values = RequireStringArray(source, propertyName, maximumCount);
        if (!allowEmpty && values.Length == 0)
        {
            throw new InvalidDataException($"{propertyName} must not be empty.");
        }
        return values;
    }

    private static string[] RequireUniqueTextArray(
        JsonElement source,
        string propertyName,
        bool allowEmpty,
        int maximumCount)
    {
        string[] values = RequireOrderedTextArray(
            source,
            propertyName,
            allowEmpty,
            maximumCount);
        if (values.Distinct(StringComparer.Ordinal).Count() != values.Length)
        {
            throw new InvalidDataException($"{propertyName} entries must be unique.");
        }
        return values;
    }

    private static bool IsUnresolvedToken(string value)
        => value.Trim().ToLowerInvariant()
            is "" or "none" or "null" or "tbd" or "todo" or "unknown" or "unassigned" or "missing" or "invalid";

    private static bool IsSentinelToken(string value)
        => value is "unknown" or "missing" or "invalid";

    private static void ValidatePortableEvidencePath(string path, string label)
    {
        if (path.StartsWith("/", StringComparison.Ordinal)
            || path.Contains('\\')
            || WindowsDrivePrefix.IsMatch(path)
            || LocalPathMarkers.Any(marker => path.Contains(marker, StringComparison.Ordinal))
            || path.Split('/').Any(static segment => segment is "." or ".."))
        {
            throw new InvalidDataException(
                $"{label} must be a portable non-traversing path without machine-local roots.");
        }
    }

    private static string[] RequireSafeRouteArray(JsonElement source, string propertyName)
    {
        JsonElement array = RequireArray(source, propertyName, "convergence receipt");
        if (array.GetArrayLength() > 256)
        {
            throw new InvalidDataException("Convergence checked route count exceeds the limit.");
        }
        return array.EnumerateArray().Select(item =>
        {
            if (item.ValueKind != JsonValueKind.String)
            {
                throw new InvalidDataException("Convergence checked routes must be strings.");
            }
            return ValidateSafePublicRoute(item.GetString() ?? string.Empty, "convergence checked route");
        }).ToArray();
    }

    private static string RequireSafePublicRoute(
        JsonElement source,
        string propertyName,
        string label)
        => ValidateSafePublicRoute(RequireString(source, propertyName, 2048), label);

    private static string ValidateSafePublicRoute(string route, string label)
    {
        if (!route.StartsWith("/", StringComparison.Ordinal)
            || route.StartsWith("//", StringComparison.Ordinal)
            || route.Contains("//", StringComparison.Ordinal)
            || route.Contains('?')
            || route.Contains('#')
            || route.Contains('\\')
            || route.Any(static character => char.IsWhiteSpace(character) || char.IsControl(character)))
        {
            throw new InvalidDataException($"{label} must be a safe root-relative route.");
        }
        foreach (string segment in route.Split('/'))
        {
            string decoded;
            try
            {
                decoded = Uri.UnescapeDataString(segment);
            }
            catch (UriFormatException ex)
            {
                throw new InvalidDataException($"{label} contains invalid escaping.", ex);
            }
            if (decoded is "." or ".." || decoded.Contains('/') || decoded.Contains('\\'))
            {
                throw new InvalidDataException($"{label} contains traversal.");
            }
        }
        return route;
    }

    private static bool JsonStringArrayEquals(JsonElement source, IReadOnlyList<string> expected)
    {
        if (source.ValueKind != JsonValueKind.Array)
        {
            return false;
        }
        string?[] actual = source.EnumerateArray()
            .Select(static item => item.ValueKind == JsonValueKind.String ? item.GetString() : null)
            .ToArray();
        return actual.Length == expected.Count
               && actual.Select(static value => value ?? string.Empty)
                   .SequenceEqual(expected, StringComparer.Ordinal);
    }

    private static bool JsonStringMapEquals(
        JsonElement source,
        IReadOnlyDictionary<string, string> expected)
    {
        if (source.ValueKind != JsonValueKind.Object || source.EnumerateObject().Count() != expected.Count)
        {
            return false;
        }
        foreach (JsonProperty property in source.EnumerateObject())
        {
            if (property.Value.ValueKind != JsonValueKind.String
                || !expected.TryGetValue(property.Name, out string? expectedValue)
                || !string.Equals(property.Value.GetString(), expectedValue, StringComparison.Ordinal))
            {
                return false;
            }
        }
        return true;
    }

    private static string PersistRevision(
        string generationsRoot,
        string generationId,
        string revisionId,
        byte[] descriptorBytes,
        ReleaseAuthorityRevisionAdvanceRequest request)
    {
        string generationRoot = EnsureOwnerOnlyDirectory(
            Path.Combine(generationsRoot, generationId));
        string revisionsRoot = EnsureOwnerOnlyDirectory(
            Path.Combine(generationRoot, AuthorityRevisionsDirectoryName));
        string revisionRoot = Path.Combine(revisionsRoot, revisionId);
        if (Directory.Exists(revisionRoot) || File.Exists(revisionRoot))
        {
            EnsureRegularDirectory(revisionRoot, "existing release authority revision");
            ValidateRevisionExactBytes(revisionRoot, descriptorBytes, request);
            return revisionRoot;
        }

        string stagedRoot = Path.Combine(revisionsRoot, $".{revisionId}.{Guid.NewGuid():N}.tmp");
        try
        {
            EnsureOwnerOnlyDirectory(stagedRoot);
            WriteOwnerOnlyFileDirect(
                Path.Combine(stagedRoot, "CURRENT.json"),
                request.SuccessorCurrentBytes);
            WriteOwnerOnlyFileDirect(
                Path.Combine(stagedRoot, "SNAPSHOT.json"),
                request.SuccessorSnapshotBytes);
            WriteOwnerOnlyFileDirect(
                Path.Combine(stagedRoot, PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath),
                request.SuccessorDecisionBytes);
            WriteOwnerOnlyFileDirect(
                Path.Combine(stagedRoot, AuthorityScorecardFileName),
                request.ScorecardBytes);
            WriteOwnerOnlyFileDirect(
                Path.Combine(stagedRoot, AuthorityConvergenceFileName),
                request.ConvergenceBytes);
            WriteOwnerOnlyFileDirect(
                Path.Combine(stagedRoot, AuthorityRevisionDescriptorFileName),
                descriptorBytes);
            FlushDirectoryDurably(stagedRoot);
            Directory.Move(stagedRoot, revisionRoot);
            FlushDirectoryDurably(revisionsRoot);
            return revisionRoot;
        }
        finally
        {
            if (Directory.Exists(stagedRoot))
            {
                Directory.Delete(stagedRoot, recursive: true);
            }
        }
    }

    private static void ValidateRevisionExactBytes(
        string revisionRoot,
        byte[] descriptorBytes,
        ReleaseAuthorityRevisionAdvanceRequest request)
    {
        RequireExactDirectoryEntries(
            revisionRoot,
            [
                "CURRENT.json", "SNAPSHOT.json",
                PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath,
                AuthorityScorecardFileName, AuthorityConvergenceFileName,
                AuthorityRevisionDescriptorFileName
            ],
            "existing release authority revision");
        (string Name, byte[] Expected, int Maximum)[] files =
        [
            ("CURRENT.json", request.SuccessorCurrentBytes, MaximumCurrentBytes),
            ("SNAPSHOT.json", request.SuccessorSnapshotBytes, MaximumSnapshotBytes),
            (PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath, request.SuccessorDecisionBytes, MaximumDecisionBytes),
            (AuthorityScorecardFileName, request.ScorecardBytes, MaximumProofBytes),
            (AuthorityConvergenceFileName, request.ConvergenceBytes, MaximumProofBytes),
            (AuthorityRevisionDescriptorFileName, descriptorBytes, MaximumDescriptorBytes)
        ];
        foreach ((string name, byte[] expected, int maximum) in files)
        {
            byte[] actual = ReadRevisionFile(revisionRoot, name, maximum);
            if (!ByteExact(actual, expected))
            {
                throw new InvalidDataException(
                    "An existing release authority revision ID resolves different immutable bytes.");
            }
        }
    }

    private static void ValidatePersistedRevisionWithoutJournal(
        string downloadsRoot,
        AuthorityPointerDocument pointer)
    {
        string authorityRoot = ResolveExactDirectory(
            downloadsRoot,
            AuthorityRootDirectoryName,
            "release authority root");
        string generationsRoot = ResolveExactDirectory(
            authorityRoot,
            AuthorityGenerationsDirectoryName,
            "release authority generations root");
        string generationRoot = ResolveExactDirectory(
            generationsRoot,
            pointer.GenerationId,
            "release authority generation");
        string revisionsRoot = ResolveExactDirectory(
            generationRoot,
            AuthorityRevisionsDirectoryName,
            "release authority revisions root");
        string revisionRoot = ResolveExactDirectory(
            revisionsRoot,
            pointer.RevisionId,
            "release authority revision");
        RequireExactDirectoryEntries(
            revisionRoot,
            [
                "CURRENT.json", "SNAPSHOT.json",
                PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath,
                AuthorityScorecardFileName, AuthorityConvergenceFileName,
                AuthorityRevisionDescriptorFileName
            ],
            "release authority revision");
        (string Name, string Digest, int Maximum)[] files =
        [
            ("CURRENT.json", pointer.CurrentSha256, MaximumCurrentBytes),
            ("SNAPSHOT.json", pointer.SnapshotSha256, MaximumSnapshotBytes),
            (PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath, pointer.DecisionSha256, MaximumDecisionBytes),
            (AuthorityScorecardFileName, pointer.ScorecardSha256, MaximumProofBytes),
            (AuthorityConvergenceFileName, pointer.ConvergenceSha256, MaximumProofBytes),
            (AuthorityRevisionDescriptorFileName, pointer.RevisionSha256, MaximumDescriptorBytes)
        ];
        foreach ((string name, string digest, int maximum) in files)
        {
            RequireDigest(digest, ReadRevisionFile(revisionRoot, name, maximum), $"authority revision {name}");
        }
        AuthorityRevisionDocument descriptor = ParseRevisionDescriptor(
            ReadRevisionFile(
                revisionRoot,
                AuthorityRevisionDescriptorFileName,
                MaximumDescriptorBytes));
        ValidateDescriptorMatchesPointer(descriptor, pointer);
    }

    private static void RemoveAbortedRevision(
        string generationsRoot,
        AuthorityIntentDocument intent)
    {
        string generationRoot = Path.Combine(generationsRoot, intent.GenerationId);
        string revisionsRoot = Path.Combine(generationRoot, AuthorityRevisionsDirectoryName);
        string revisionRoot = Path.Combine(revisionsRoot, intent.RevisionId);
        if (Directory.Exists(revisionRoot))
        {
            EnsureRegularDirectory(revisionRoot, "aborted release authority revision");
            Directory.Delete(revisionRoot, recursive: true);
            FlushDirectoryDurably(revisionsRoot);
        }
        else if (File.Exists(revisionRoot))
        {
            throw new InvalidDataException(
                "Aborted release authority revision path is not a directory.");
        }

        if (Directory.Exists(revisionsRoot)
            && !Directory.EnumerateFileSystemEntries(revisionsRoot).Any())
        {
            Directory.Delete(revisionsRoot);
            FlushDirectoryDurably(generationRoot);
        }
        if (Directory.Exists(generationRoot)
            && !Directory.EnumerateFileSystemEntries(generationRoot).Any())
        {
            Directory.Delete(generationRoot);
            FlushDirectoryDurably(generationsRoot);
        }
    }

    private static void PersistJournalIntent(
        string journalRoot,
        string receiptId,
        byte[] intentBytes)
    {
        if (!SafeReceiptId.IsMatch(receiptId))
        {
            throw new InvalidDataException("Release authority receipt ID is unsafe.");
        }
        string receiptRoot = Path.Combine(journalRoot, receiptId);
        if (Directory.Exists(receiptRoot) || File.Exists(receiptRoot))
        {
            EnsureRegularDirectory(receiptRoot, "release authority journal receipt");
            string intentPath = ResolveExactFile(
                receiptRoot,
                AuthorityIntentFileName,
                "release authority journal intent");
            byte[] existing = ReadBoundedRegularFile(
                intentPath,
                MaximumJournalBytes,
                "release authority journal intent");
            if (!ByteExact(existing, intentBytes))
            {
                throw new InvalidDataException(
                    "Existing release authority journal receipt has different intent bytes.");
            }
            return;
        }

        string staged = Path.Combine(journalRoot, $".{receiptId}.{Guid.NewGuid():N}.tmp");
        try
        {
            EnsureOwnerOnlyDirectory(staged);
            WriteOwnerOnlyFileDirect(Path.Combine(staged, AuthorityIntentFileName), intentBytes);
            FlushDirectoryDurably(staged);
            Directory.Move(staged, receiptRoot);
            FlushDirectoryDurably(journalRoot);
        }
        finally
        {
            if (Directory.Exists(staged))
            {
                Directory.Delete(staged, recursive: true);
            }
        }
    }

    private static void WriteJournalOutcome(
        string journalRoot,
        AuthorityIntentDocument intent,
        string state,
        DateTimeOffset resolvedAtUtc)
    {
        if (state is not ("committed" or "aborted"))
        {
            throw new ArgumentOutOfRangeException(nameof(state));
        }
        string receiptRoot = ResolveExactDirectory(
            journalRoot,
            intent.JournalReceiptId,
            "release authority journal receipt");
        var outcome = new AuthorityOutcomeDocument(
            AuthorityOutcomeSchema,
            state,
            intent.GenerationId,
            intent.RevisionId,
            intent.JournalReceiptId,
            intent.TargetPointerSha256,
            FormatUtc(resolvedAtUtc));
        string path = Path.Combine(receiptRoot, AuthorityOutcomeFileName);
        byte[] bytes = SerializeDocument(outcome);
        if (File.Exists(path))
        {
            AuthorityOutcomeDocument existing = ParseAuthorityOutcome(
                ReadBoundedRegularFile(path, MaximumJournalBytes, "release authority journal outcome"));
            if (existing != outcome)
            {
                throw new InvalidDataException(
                    "Release authority journal outcome is already bound to different bytes.");
            }
            return;
        }
        WriteOwnerOnlyFileAtomically(path, bytes, overwrite: false);
    }

    private static AuthorityOutcomeDocument? TryReadJournalOutcome(
        string journalRoot,
        string receiptId)
    {
        string receiptRoot = ResolveExactDirectory(
            journalRoot,
            receiptId,
            "release authority journal receipt");
        string outcomePath = ResolveExactFileOrMissing(
            receiptRoot,
            AuthorityOutcomeFileName,
            "release authority journal outcome");
        return outcomePath.Length == 0
            ? null
            : ParseAuthorityOutcome(ReadBoundedRegularFile(
                outcomePath,
                MaximumJournalBytes,
                "release authority journal outcome"));
    }

    private static void ValidateCommittedJournal(
        string downloadsRoot,
        AuthorityPointerDocument pointer,
        byte[] pointerBytes)
    {
        string authorityRoot = ResolveExactDirectory(
            downloadsRoot,
            AuthorityRootDirectoryName,
            "release authority root");
        string journalRoot = ResolveExactDirectory(
            authorityRoot,
            AuthorityJournalDirectoryName,
            "release authority journal root");
        string receiptRoot = ResolveExactDirectory(
            journalRoot,
            pointer.JournalReceiptId,
            "release authority journal receipt");
        RequireExactDirectoryEntries(
            receiptRoot,
            [AuthorityIntentFileName, AuthorityOutcomeFileName],
            "committed release authority journal receipt");
        AuthorityIntentDocument intent = ParseAuthorityIntent(
            ReadBoundedRegularFile(
                Path.Combine(receiptRoot, AuthorityIntentFileName),
                MaximumJournalBytes,
                "release authority journal intent"));
        ValidateIntentMatchesPointer(intent, pointer, pointerBytes);
        AuthorityOutcomeDocument outcome = ParseAuthorityOutcome(
            ReadBoundedRegularFile(
                Path.Combine(receiptRoot, AuthorityOutcomeFileName),
                MaximumJournalBytes,
                "release authority journal outcome"));
        ValidateOutcome(outcome, intent);
        if (!string.Equals(outcome.State, "committed", StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Release authority pointer is not backed by a committed journal outcome.");
        }
    }

    private static void ValidateIntentMatchesPointer(
        AuthorityIntentDocument intent,
        AuthorityPointerDocument pointer,
        byte[] pointerBytes)
    {
        byte[] declaredPointer = DecodeCanonicalBase64(
            intent.TargetPointerBase64,
            MaximumPointerBytes,
            "authority journal target pointer");
        if (!ByteExact(declaredPointer, pointerBytes)
            || !FixedDigestEquals(intent.TargetPointerSha256, Sha256(pointerBytes))
            || !string.Equals(intent.GenerationId, pointer.GenerationId, StringComparison.Ordinal)
            || !string.Equals(intent.ReleaseVersion, pointer.ReleaseVersion, StringComparison.Ordinal)
            || !string.Equals(intent.RevisionId, pointer.RevisionId, StringComparison.Ordinal)
            || !string.Equals(intent.JournalReceiptId, pointer.JournalReceiptId, StringComparison.Ordinal)
            || !FixedDigestEquals(intent.ShelfPointerSha256, pointer.ShelfPointerSha256)
            || !string.Equals(intent.ShelfInventoryDigest, pointer.ShelfInventoryDigest, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Release authority journal intent does not bind its exact pointer bytes.");
        }
    }

    private static void ValidateOutcome(
        AuthorityOutcomeDocument outcome,
        AuthorityIntentDocument intent)
    {
        if (outcome.SchemaVersion != AuthorityOutcomeSchema
            || outcome.State is not ("committed" or "aborted")
            || !string.Equals(outcome.GenerationId, intent.GenerationId, StringComparison.Ordinal)
            || !string.Equals(outcome.RevisionId, intent.RevisionId, StringComparison.Ordinal)
            || !string.Equals(outcome.JournalReceiptId, intent.JournalReceiptId, StringComparison.Ordinal)
            || !FixedDigestEquals(outcome.TargetPointerSha256, intent.TargetPointerSha256))
        {
            throw new InvalidDataException("Release authority journal outcome is contradictory.");
        }
        _ = ParseUtc(outcome.ResolvedAtUtc, "authority outcome resolvedAtUtc");
    }

    private static AuthorityPointerDocument ParseAuthorityPointer(byte[] bytes)
    {
        using JsonDocument document = ParseStrictJson(bytes, "release authority pointer");
        RequireExactObject(
            document.RootElement,
            [
                "schemaVersion", "generationId", "releaseVersion", "shelfPointerSha256",
                "shelfInventoryDigest", "revisionId", "revisionSha256",
                "predecessorSnapshotSha256", "predecessorDecisionSha256", "currentSha256",
                "snapshotSha256", "decisionSha256", "scorecardSha256", "convergenceSha256",
                "journalReceiptId", "committedAtUtc"
            ],
            "release authority pointer");
        AuthorityPointerDocument pointer = JsonSerializer.Deserialize<AuthorityPointerDocument>(
                bytes,
                WriterOptions)
            ?? throw new InvalidDataException("Release authority pointer is malformed.");
        ValidatePointerShape(pointer);
        return pointer;
    }

    private static void ValidatePointerShape(AuthorityPointerDocument pointer)
    {
        if (pointer.SchemaVersion != AuthorityPointerSchema
            || !SafeGenerationId.IsMatch(pointer.GenerationId ?? string.Empty)
            || !SafeRevisionId.IsMatch(pointer.RevisionId ?? string.Empty)
            || !SafeReceiptId.IsMatch(pointer.JournalReceiptId ?? string.Empty)
            || string.IsNullOrWhiteSpace(pointer.ReleaseVersion))
        {
            throw new InvalidDataException("Release authority pointer identity is invalid.");
        }
        RequireSha256(pointer.ShelfPointerSha256, "authority pointer shelfPointerSha256");
        RequirePrefixedSha256(pointer.ShelfInventoryDigest, "authority pointer shelfInventoryDigest");
        RequireSha256(pointer.RevisionSha256, "authority pointer revisionSha256");
        RequireSha256(pointer.PredecessorSnapshotSha256, "authority pointer predecessorSnapshotSha256");
        RequireSha256(pointer.PredecessorDecisionSha256, "authority pointer predecessorDecisionSha256");
        RequireSha256(pointer.CurrentSha256, "authority pointer currentSha256");
        RequireSha256(pointer.SnapshotSha256, "authority pointer snapshotSha256");
        RequireSha256(pointer.DecisionSha256, "authority pointer decisionSha256");
        RequireSha256(pointer.ScorecardSha256, "authority pointer scorecardSha256");
        RequireSha256(pointer.ConvergenceSha256, "authority pointer convergenceSha256");
        _ = ParseUtc(pointer.CommittedAtUtc, "authority pointer committedAtUtc");
    }

    private static AuthorityRevisionDocument ParseRevisionDescriptor(byte[] bytes)
    {
        using JsonDocument document = ParseStrictJson(bytes, "release authority revision descriptor");
        RequireExactObject(
            document.RootElement,
            [
                "schemaVersion", "generationId", "releaseVersion", "shelfPointerSha256",
                "shelfInventoryDigest", "revisionId", "predecessorSnapshotSha256",
                "predecessorDecisionSha256", "currentSha256", "snapshotSha256", "decisionSha256",
                "scorecardSha256", "convergenceSha256", "journalReceiptId", "committedAtUtc"
            ],
            "release authority revision descriptor");
        AuthorityRevisionDocument descriptor = JsonSerializer.Deserialize<AuthorityRevisionDocument>(
                bytes,
                WriterOptions)
            ?? throw new InvalidDataException("Release authority revision descriptor is malformed.");
        if (descriptor.SchemaVersion != AuthorityRevisionSchema)
        {
            throw new InvalidDataException("Release authority revision descriptor schema is invalid.");
        }
        return descriptor;
    }

    private static AuthorityIntentDocument ParseAuthorityIntent(byte[] bytes)
    {
        using JsonDocument document = ParseStrictJson(bytes, "release authority journal intent");
        RequireExactObject(
            document.RootElement,
            [
                "schemaVersion", "state", "generationId", "releaseVersion", "revisionId",
                "journalReceiptId", "shelfPointerSha256", "shelfInventoryDigest",
                "previousPointerSha256", "previousPointerBase64", "targetPointerSha256",
                "targetPointerBase64", "preparedAtUtc"
            ],
            "release authority journal intent");
        AuthorityIntentDocument intent = JsonSerializer.Deserialize<AuthorityIntentDocument>(bytes, WriterOptions)
            ?? throw new InvalidDataException("Release authority journal intent is malformed.");
        if (intent.SchemaVersion != AuthorityIntentSchema
            || intent.State != "prepared"
            || !SafeGenerationId.IsMatch(intent.GenerationId ?? string.Empty)
            || !SafeRevisionId.IsMatch(intent.RevisionId ?? string.Empty)
            || !SafeReceiptId.IsMatch(intent.JournalReceiptId ?? string.Empty))
        {
            throw new InvalidDataException("Release authority journal intent identity is invalid.");
        }
        RequireSha256(intent.ShelfPointerSha256, "authority intent shelfPointerSha256");
        RequirePrefixedSha256(intent.ShelfInventoryDigest, "authority intent shelfInventoryDigest");
        RequireSha256(intent.TargetPointerSha256, "authority intent targetPointerSha256");
        if (intent.PreviousPointerSha256 is not null)
        {
            RequireSha256(intent.PreviousPointerSha256, "authority intent previousPointerSha256");
        }
        _ = ParseUtc(intent.PreparedAtUtc, "authority intent preparedAtUtc");
        return intent;
    }

    private static AuthorityOutcomeDocument ParseAuthorityOutcome(byte[] bytes)
    {
        using JsonDocument document = ParseStrictJson(bytes, "release authority journal outcome");
        RequireExactObject(
            document.RootElement,
            [
                "schemaVersion", "state", "generationId", "revisionId", "journalReceiptId",
                "targetPointerSha256", "resolvedAtUtc"
            ],
            "release authority journal outcome");
        return JsonSerializer.Deserialize<AuthorityOutcomeDocument>(bytes, WriterOptions)
            ?? throw new InvalidDataException("Release authority journal outcome is malformed.");
    }

    private static void ValidatePointerShelfBinding(
        AuthorityPointerDocument pointer,
        ReleaseShelfSnapshot shelf)
    {
        ValidatePointerShape(pointer);
        if (shelf.IsLegacy
            || !string.Equals(pointer.GenerationId, shelf.GenerationId, StringComparison.Ordinal)
            || !string.Equals(pointer.ReleaseVersion, shelf.ReleaseVersion, StringComparison.Ordinal)
            || !FixedDigestEquals(pointer.ShelfPointerSha256, shelf.PointerDigest!)
            || !string.Equals(
                pointer.ShelfInventoryDigest,
                "sha256:" + shelf.InventoryDigest,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Release authority pointer does not bind this exact release shelf generation.");
        }
    }

    private static void ValidateDescriptorMatchesPointer(
        AuthorityRevisionDocument descriptor,
        AuthorityPointerDocument pointer)
    {
        if (descriptor.SchemaVersion != AuthorityRevisionSchema
            || descriptor.GenerationId != pointer.GenerationId
            || descriptor.ReleaseVersion != pointer.ReleaseVersion
            || !FixedDigestEquals(descriptor.ShelfPointerSha256, pointer.ShelfPointerSha256)
            || descriptor.ShelfInventoryDigest != pointer.ShelfInventoryDigest
            || descriptor.RevisionId != pointer.RevisionId
            || !FixedDigestEquals(descriptor.PredecessorSnapshotSha256, pointer.PredecessorSnapshotSha256)
            || !FixedDigestEquals(descriptor.PredecessorDecisionSha256, pointer.PredecessorDecisionSha256)
            || !FixedDigestEquals(descriptor.CurrentSha256, pointer.CurrentSha256)
            || !FixedDigestEquals(descriptor.SnapshotSha256, pointer.SnapshotSha256)
            || !FixedDigestEquals(descriptor.DecisionSha256, pointer.DecisionSha256)
            || !FixedDigestEquals(descriptor.ScorecardSha256, pointer.ScorecardSha256)
            || !FixedDigestEquals(descriptor.ConvergenceSha256, pointer.ConvergenceSha256)
            || descriptor.JournalReceiptId != pointer.JournalReceiptId
            || descriptor.CommittedAtUtc != pointer.CommittedAtUtc)
        {
            throw new InvalidDataException(
                "Release authority revision descriptor contradicts its pointer.");
        }
    }

    private static byte[] ReadRevisionFile(string revisionRoot, string fileName, int maximumBytes)
        => ReadBoundedRegularFile(
            ResolveExactFile(revisionRoot, fileName, $"release authority revision {fileName}"),
            maximumBytes,
            $"release authority revision {fileName}");

    private static byte[] ReadBoundedRegularFile(string path, int maximumBytes, string label)
    {
        EnsureRegularFile(path, label);
        try
        {
            using var stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                64 * 1024,
                FileOptions.SequentialScan);
            if (stream.Length is < 1 || stream.Length > maximumBytes)
            {
                throw new InvalidDataException($"{label} has an invalid byte length.");
            }
            byte[] bytes = new byte[checked((int)stream.Length)];
            stream.ReadExactly(bytes);
            if (stream.Position != stream.Length)
            {
                throw new InvalidDataException($"{label} changed while it was read.");
            }
            return bytes;
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            throw new InvalidDataException($"{label} could not be read safely.", ex);
        }
    }

    private static string ResolveExactDirectory(string parent, string name, string label)
    {
        string result = ResolveExactDirectoryOrMissing(parent, name, label);
        return result.Length == 0
            ? throw new InvalidDataException($"{label} is missing.")
            : result;
    }

    private static string ResolveExactDirectoryOrMissing(string parent, string name, string label)
    {
        if (!Directory.Exists(parent))
        {
            return string.Empty;
        }
        EnsureRegularDirectory(parent, $"{label} parent");
        string[] matches = Directory.EnumerateFileSystemEntries(parent)
            .Where(path => string.Equals(Path.GetFileName(path), name, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (matches.Length == 0)
        {
            return string.Empty;
        }
        if (matches.Length != 1
            || !string.Equals(Path.GetFileName(matches[0]), name, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} has ambiguous or noncanonical casing.");
        }
        EnsureRegularDirectory(matches[0], label);
        return matches[0];
    }

    private static string ResolveExactFile(string parent, string name, string label)
    {
        string result = ResolveExactFileOrMissing(parent, name, label);
        return result.Length == 0
            ? throw new InvalidDataException($"{label} is missing.")
            : result;
    }

    private static string ResolveExactFileOrMissing(string parent, string name, string label)
    {
        if (!Directory.Exists(parent))
        {
            return string.Empty;
        }
        EnsureRegularDirectory(parent, $"{label} parent");
        string[] matches = Directory.EnumerateFileSystemEntries(parent)
            .Where(path => string.Equals(Path.GetFileName(path), name, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (matches.Length == 0)
        {
            return string.Empty;
        }
        if (matches.Length != 1
            || !string.Equals(Path.GetFileName(matches[0]), name, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} has ambiguous or noncanonical casing.");
        }
        EnsureRegularFile(matches[0], label);
        return matches[0];
    }

    private static void RequireExactDirectoryEntries(
        string directory,
        IReadOnlyCollection<string> expected,
        string label)
    {
        EnsureRegularDirectory(directory, label);
        string[] actual = Directory.EnumerateFileSystemEntries(directory)
            .Select(static path => Path.GetFileName(path))
            .OrderBy(static name => name, StringComparer.Ordinal)
            .ToArray();
        string[] required = expected.OrderBy(static name => name, StringComparer.Ordinal).ToArray();
        if (!actual.SequenceEqual(required, StringComparer.Ordinal))
        {
            throw new InvalidDataException($"{label} contains unexpected or missing entries.");
        }
        foreach (string name in required)
        {
            EnsureRegularFile(Path.Combine(directory, name), $"{label} entry");
        }
    }

    private static void EnsureRegularFile(string path, string label)
    {
        if (!File.Exists(path))
        {
            throw new InvalidDataException($"{label} is not a regular file.");
        }
        FileAttributes attributes = File.GetAttributes(path);
        if ((attributes & (FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0)
        {
            throw new InvalidDataException($"{label} cannot be a directory or link.");
        }
    }

    private static void EnsureRegularDirectory(string path, string label)
    {
        if (!Directory.Exists(path))
        {
            throw new InvalidDataException($"{label} is not a directory.");
        }
        FileAttributes attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.Directory) == 0
            || (attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException($"{label} cannot be a file or link.");
        }
    }

    private static string EnsureOwnerOnlyDirectory(string path)
    {
        if (Directory.Exists(path))
        {
            EnsureRegularDirectory(path, "release authority directory");
        }
        else if (File.Exists(path))
        {
            throw new InvalidDataException("Release authority directory path is occupied by a file.");
        }
        else
        {
            string parent = Path.GetDirectoryName(path)
                ?? throw new InvalidDataException("Release authority directory has no parent.");
            Directory.CreateDirectory(path);
            SetOwnerOnlyDirectoryMode(path);
            FlushDirectoryDurably(parent);
        }
        SetOwnerOnlyDirectoryMode(path);
        return path;
    }

    private static void SetOwnerOnlyDirectoryMode(string path)
    {
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(
                path,
                UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        }
    }

    private static void WriteOwnerOnlyFileDirect(string path, ReadOnlySpan<byte> bytes)
    {
        var options = new FileStreamOptions
        {
            Mode = FileMode.CreateNew,
            Access = FileAccess.Write,
            Share = FileShare.None,
            Options = FileOptions.WriteThrough
        };
        if (!OperatingSystem.IsWindows())
        {
            options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
        }
        using (var stream = new FileStream(path, options))
        {
            stream.Write(bytes);
            stream.Flush(flushToDisk: true);
        }
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        }
    }

    private static void WriteOwnerOnlyFileAtomically(
        string path,
        byte[] bytes,
        bool overwrite)
    {
        string directory = EnsureOwnerOnlyDirectory(
            Path.GetDirectoryName(path)
            ?? throw new InvalidDataException("Release authority file has no parent."));
        if (File.Exists(path))
        {
            EnsureRegularFile(path, "existing release authority file");
        }
        else if (Directory.Exists(path))
        {
            throw new InvalidDataException("Release authority file path is occupied by a directory.");
        }
        string tempPath = Path.Combine(directory, $".{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
        try
        {
            WriteOwnerOnlyFileDirect(tempPath, bytes);
            File.Move(tempPath, path, overwrite);
            if (!OperatingSystem.IsWindows())
            {
                File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
            }
            FlushDirectoryDurably(directory);
        }
        finally
        {
            if (File.Exists(tempPath))
            {
                File.Delete(tempPath);
            }
        }
    }

    private static void DeleteFileDurably(string path)
    {
        if (!File.Exists(path))
        {
            return;
        }
        EnsureRegularFile(path, "release authority active intent");
        File.Delete(path);
        FlushDirectoryDurably(
            Path.GetDirectoryName(path)
            ?? throw new InvalidDataException("Release authority file has no parent."));
    }

    private static byte[] SerializeDocument<T>(T document)
    {
        byte[] payload = JsonSerializer.SerializeToUtf8Bytes(document, WriterOptions);
        byte[] result = new byte[payload.Length + 1];
        payload.CopyTo(result, 0);
        result[^1] = (byte)'\n';
        return result;
    }

    private static byte[] DecodeCanonicalBase64(string value, int maximumBytes, string label)
    {
        byte[] bytes;
        try
        {
            bytes = Convert.FromBase64String(value);
        }
        catch (FormatException ex)
        {
            throw new InvalidDataException($"{label} is not base64.", ex);
        }
        if (bytes.Length is < 1 || bytes.Length > maximumBytes
            || !string.Equals(Convert.ToBase64String(bytes), value, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} is not canonical bounded base64.");
        }
        return bytes;
    }

    private static void RequireDigest(string expected, ReadOnlySpan<byte> bytes, string label)
    {
        RequireSha256(expected, label);
        string actual = Sha256(bytes);
        if (!FixedDigestEquals(expected, actual))
        {
            throw new InvalidDataException($"{label} does not match the exact bytes.");
        }
    }

    private static void RequirePrefixedSha256(string value, string label)
    {
        if (value is null || value.Length != 71 || !value.StartsWith("sha256:", StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} must use sha256:<lower-hex> form.");
        }
        RequireSha256(value[7..], label);
    }

    private static void RequireSha256(string value, string label)
    {
        if (value is null || !LowerSha256.IsMatch(value))
        {
            throw new InvalidDataException($"{label} must be a lower-case SHA-256 digest.");
        }
    }

    private static string Sha256(ReadOnlySpan<byte> bytes)
        => Convert.ToHexStringLower(SHA256.HashData(bytes));

    private static bool FixedDigestEquals(string left, string right)
    {
        try
        {
            byte[] leftBytes = Convert.FromHexString(left);
            byte[] rightBytes = Convert.FromHexString(right);
            return leftBytes.Length == 32
                   && rightBytes.Length == 32
                   && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private static bool ByteExact(byte[]? left, byte[]? right)
    {
        if (left is null || right is null)
        {
            return left is null && right is null;
        }
        return left.Length == right.Length
               && CryptographicOperations.FixedTimeEquals(left, right);
    }

    private static DateTimeOffset ParseUtc(string value, string label)
    {
        bool hasOffset = value.EndsWith('Z')
                         || value.Length > 10
                         && (value[10..].Contains('+') || value[10..].Contains('-'));
        if (!hasOffset
            || !DateTimeOffset.TryParse(
                value,
                CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind,
                out DateTimeOffset instant))
        {
            throw new InvalidDataException($"{label} must be an ISO-8601 timestamp with an explicit offset.");
        }
        return instant.ToUniversalTime();
    }

    private static string FormatUtc(DateTimeOffset value)
        => value.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);

    private static void FlushDirectoryDurably(string path)
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }
        int descriptor = NativeOpen(path, 0);
        if (descriptor < 0)
        {
            throw new IOException(
                $"Could not open release authority directory for fsync: {path}.");
        }
        try
        {
            if (NativeFsync(descriptor) != 0)
            {
                throw new IOException(
                    $"Could not fsync release authority directory: {path}.");
            }
        }
        finally
        {
            _ = NativeClose(descriptor);
        }
    }

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int NativeOpen(string path, int flags);

    [DllImport("libc", EntryPoint = "fsync", SetLastError = true)]
    private static extern int NativeFsync(int descriptor);

    [DllImport("libc", EntryPoint = "close", SetLastError = true)]
    private static extern int NativeClose(int descriptor);

    private sealed record AuthorityPointerDocument(
        string SchemaVersion,
        string GenerationId,
        string ReleaseVersion,
        string ShelfPointerSha256,
        string ShelfInventoryDigest,
        string RevisionId,
        string RevisionSha256,
        string PredecessorSnapshotSha256,
        string PredecessorDecisionSha256,
        string CurrentSha256,
        string SnapshotSha256,
        string DecisionSha256,
        string ScorecardSha256,
        string ConvergenceSha256,
        string JournalReceiptId,
        string CommittedAtUtc);

    private sealed record AuthorityRevisionDocument(
        string SchemaVersion,
        string GenerationId,
        string ReleaseVersion,
        string ShelfPointerSha256,
        string ShelfInventoryDigest,
        string RevisionId,
        string PredecessorSnapshotSha256,
        string PredecessorDecisionSha256,
        string CurrentSha256,
        string SnapshotSha256,
        string DecisionSha256,
        string ScorecardSha256,
        string ConvergenceSha256,
        string JournalReceiptId,
        string CommittedAtUtc);

    private sealed record AuthorityIntentDocument(
        string SchemaVersion,
        string State,
        string GenerationId,
        string ReleaseVersion,
        string RevisionId,
        string JournalReceiptId,
        string ShelfPointerSha256,
        string ShelfInventoryDigest,
        string? PreviousPointerSha256,
        string? PreviousPointerBase64,
        string TargetPointerSha256,
        string TargetPointerBase64,
        string PreparedAtUtc);

    private sealed record AuthorityOutcomeDocument(
        string SchemaVersion,
        string State,
        string GenerationId,
        string RevisionId,
        string JournalReceiptId,
        string TargetPointerSha256,
        string ResolvedAtUtc);
}
