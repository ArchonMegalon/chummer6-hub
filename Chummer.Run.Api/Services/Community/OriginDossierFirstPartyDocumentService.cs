using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class OriginDossierFirstPartyDocumentService
{
    public const int MaxRequestBodyBytes = 128 * 1024;

    private const string DocumentContract = "chummer.origin-dossier.first-party-document/v1";
    private const string ReceiptContract = "chummer.origin-dossier.first-party-receipt/v2";
    private const string CanonStatus = "non_canon_private_draft";
    private const string ProviderExecution = "not_requested";
    private const string PremiumMediaState = "blocked_by_existing_governance";
    private const string ReleaseScope = "unchanged";
    private const int MaximumInputs = 64;
    private const int DefaultMaxRevisionsPerOwner = 64;
    private const int DefaultMaxRevisionsGlobal = 2048;
    private const int AbsoluteMaxRevisions = 16_384;
    private const int MaxTemporaryDirectoriesInspectedPerPreview = 64;
    private const int MaxTemporaryDirectoriesScavengedPerPreview = 16;
    private const int MaxTemporaryRevisionEntries = 5;
    private static readonly TimeSpan TemporaryRevisionStaleAfter = TimeSpan.FromHours(1);
    private static readonly Regex SafeIdentifier = new(
        "\\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}\\z",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);
    private static readonly Regex TemporaryRevisionName = new(
        "\\Aodfp-[a-f0-9]{24}\\.tmp-[a-f0-9]{32}\\z",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);
    private static readonly Regex Sha256Digest = new(
        "\\A[a-f0-9]{64}\\z",
        RegexOptions.CultureInvariant | RegexOptions.Compiled);
    private static readonly HashSet<string> TemporaryRevisionFiles = new(StringComparer.Ordinal)
    {
        ".active",
        "document.json",
        "document.md",
        "metadata.json",
        "preview-receipt.json"
    };
    private static readonly HashSet<string> ApprovedSourceKinds = new(StringComparer.Ordinal)
    {
        "campaign_record",
        "character_sheet",
        "chummer_import",
        "gm_note",
        "player_note"
    };
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    private readonly object _gate = new();
    private readonly string _root;
    private readonly string _storagePosture;
    private readonly int _maxRevisionsPerOwner;
    private readonly int _maxRevisionsGlobal;

    public OriginDossierFirstPartyDocumentService(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        string? configured = configuration["CHUMMER_ORIGIN_DOSSIER_FIRST_PARTY_ROOT"]
            ?? configuration["OriginDossier:FirstPartyDocumentRoot"];
        string? runtimeStateRoot = configuration["CHUMMER_RUNTIME_STATE_ROOT"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            _root = Path.GetFullPath(configured.Trim());
            _storagePosture = "configured_private_storage_root";
        }
        else if (!string.IsNullOrWhiteSpace(runtimeStateRoot))
        {
            _root = Path.GetFullPath(Path.Combine(runtimeStateRoot.Trim(), "origin-dossier-first-party"));
            _storagePosture = "configured_private_storage_root";
        }
        else
        {
            _root = Path.GetFullPath(Path.Combine(Path.GetTempPath(), "chummer6-hub", "origin-dossier-first-party"));
            _storagePosture = "process_local_temp_non_durable";
        }

        _maxRevisionsPerOwner = ReadBoundedLimit(
            configuration,
            "CHUMMER_ORIGIN_DOSSIER_FIRST_PARTY_MAX_REVISIONS_PER_OWNER",
            "OriginDossier:MaxFirstPartyRevisionsPerOwner",
            DefaultMaxRevisionsPerOwner);
        _maxRevisionsGlobal = ReadBoundedLimit(
            configuration,
            "CHUMMER_ORIGIN_DOSSIER_FIRST_PARTY_MAX_REVISIONS_GLOBAL",
            "OriginDossier:MaxFirstPartyRevisionsGlobal",
            DefaultMaxRevisionsGlobal);
        if (_maxRevisionsGlobal < _maxRevisionsPerOwner)
        {
            throw new InvalidOperationException(
                "Origin Dossier global first-party revision capacity must be at least the per-owner capacity.");
        }
    }

    public OriginDossierFirstPartyDocumentProjection Preview(
        string ownerUserId,
        string ownerSubjectId,
        string projectId,
        OriginDossierFirstPartyDocumentRequest request)
    {
        string ownerScopeSha256 = ResolveOwnerScope(ownerUserId, ownerSubjectId);
        string normalizedProjectId = RequireIdentifier(projectId, nameof(projectId));
        NormalizedOriginDossierRequest normalized = NormalizeRequest(request);
        string canonicalInputJson = Serialize(new CanonicalOriginDossierInput(
            DocumentContract,
            normalizedProjectId,
            normalized.Title,
            normalized.RunnerAlias,
            normalized.Inputs));
        string revisionId = $"odfp-{Sha256(canonicalInputJson)[..24]}";
        string revisionRoot = ResolveRevisionRoot(ownerScopeSha256, normalizedProjectId, revisionId);

        lock (_gate)
        {
            ScavengeStaleTemporaryRevisions(Path.GetDirectoryName(revisionRoot)!);
            if (Directory.Exists(revisionRoot))
            {
                return LoadProjection(revisionRoot, ownerScopeSha256, normalizedProjectId, revisionId);
            }

            EnsureRevisionCapacity(ownerScopeSha256);
            string markdown = RenderMarkdown(normalizedProjectId, revisionId, normalized, _storagePosture);
            string documentJson = RenderDocumentJson(
                ownerScopeSha256,
                normalizedProjectId,
                revisionId,
                normalized,
                _storagePosture);
            string markdownSha256 = Sha256(markdown);
            string jsonSha256 = Sha256(documentJson);
            FirstPartyDocumentMetadata metadata = new(
                DocumentContract,
                ownerScopeSha256,
                normalizedProjectId,
                revisionId,
                normalized.Title,
                normalized.RunnerAlias,
                normalized.Inputs,
                _storagePosture,
                Sha256(canonicalInputJson),
                markdownSha256,
                jsonSha256);
            string metadataJson = Serialize(metadata);
            string previewReceipt = RenderReceipt(
                "preview",
                metadata,
                Sha256(metadataJson),
                markdown.Length,
                documentJson.Length,
                previewReceiptSha256: null);

            PersistNewRevision(
                revisionRoot,
                metadataJson,
                markdown,
                documentJson,
                previewReceipt);
            return LoadProjection(revisionRoot, ownerScopeSha256, normalizedProjectId, revisionId);
        }
    }

    public OriginDossierFirstPartyDocumentProjection? GetForOwner(
        string ownerUserId,
        string ownerSubjectId,
        string projectId,
        string revisionId)
    {
        string ownerScopeSha256 = ResolveOwnerScope(ownerUserId, ownerSubjectId);
        string normalizedProjectId = RequireIdentifier(projectId, nameof(projectId));
        string normalizedRevisionId = RequireIdentifier(revisionId, nameof(revisionId));
        string revisionRoot = ResolveRevisionRoot(ownerScopeSha256, normalizedProjectId, normalizedRevisionId);
        lock (_gate)
        {
            return Directory.Exists(revisionRoot)
                ? LoadProjection(revisionRoot, ownerScopeSha256, normalizedProjectId, normalizedRevisionId)
                : null;
        }
    }

    public bool DeleteForOwner(
        string ownerUserId,
        string ownerSubjectId,
        string projectId,
        string revisionId)
    {
        string ownerScopeSha256 = ResolveOwnerScope(ownerUserId, ownerSubjectId);
        string normalizedProjectId = RequireIdentifier(projectId, nameof(projectId));
        string normalizedRevisionId = RequireIdentifier(revisionId, nameof(revisionId));
        string revisionRoot = ResolveRevisionRoot(ownerScopeSha256, normalizedProjectId, normalizedRevisionId);

        lock (_gate)
        {
            if (!Directory.Exists(revisionRoot))
            {
                return false;
            }

            string projectRoot = Path.GetDirectoryName(revisionRoot)!;
            string ownerRoot = Path.GetDirectoryName(projectRoot)!;
            EnsureDirectoryIsNotLinked(_root);
            EnsureDirectoryIsNotLinked(ownerRoot);
            EnsureDirectoryIsNotLinked(projectRoot);
            EnsureDirectoryTreeContainsNoLinks(revisionRoot);
            Directory.Delete(revisionRoot, recursive: true);
            DeleteIfEmpty(projectRoot);
            DeleteIfEmpty(ownerRoot);
            return true;
        }
    }

    public OriginDossierFirstPartyDocumentProjection Export(
        string ownerUserId,
        string ownerSubjectId,
        string projectId,
        string revisionId)
    {
        string ownerScopeSha256 = ResolveOwnerScope(ownerUserId, ownerSubjectId);
        string normalizedProjectId = RequireIdentifier(projectId, nameof(projectId));
        string normalizedRevisionId = RequireIdentifier(revisionId, nameof(revisionId));
        string revisionRoot = ResolveRevisionRoot(ownerScopeSha256, normalizedProjectId, normalizedRevisionId);

        lock (_gate)
        {
            if (!Directory.Exists(revisionRoot))
            {
                throw new KeyNotFoundException("Origin Dossier first-party preview was not found for this owner.");
            }

            ValidatedFirstPartyDocument preview = LoadValidatedRevision(
                revisionRoot,
                ownerScopeSha256,
                normalizedProjectId,
                normalizedRevisionId);
            string exportReceiptPath = Path.Combine(revisionRoot, "export-receipt.json");
            if (!File.Exists(exportReceiptPath))
            {
                string exportReceipt = RenderReceipt(
                    "exported",
                    preview.Metadata,
                    preview.MetadataSha256,
                    preview.Markdown.Length,
                    preview.DocumentJson.Length,
                    preview.PreviewReceiptSha256);
                WriteImmutable(exportReceiptPath, exportReceipt);
            }

            return LoadProjection(revisionRoot, ownerScopeSha256, normalizedProjectId, normalizedRevisionId);
        }
    }

    public OriginDossierFirstPartyExportArtifact GetExportArtifactForOwner(
        string ownerUserId,
        string ownerSubjectId,
        string projectId,
        string revisionId,
        string format)
    {
        OriginDossierFirstPartyDocumentProjection projection = GetForOwner(
            ownerUserId,
            ownerSubjectId,
            projectId,
            revisionId)
            ?? throw new KeyNotFoundException("Origin Dossier first-party export was not found for this owner.");
        if (!string.Equals(projection.State, "exported", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Origin Dossier first-party preview must be exported before its files can be downloaded.");
        }

        return format.Trim().ToLowerInvariant() switch
        {
            "json" => new(
                projection.Json,
                "application/json; charset=utf-8",
                $"{projection.ProjectId}-{projection.RevisionId}.json",
                projection.JsonSha256),
            "markdown" or "md" => new(
                projection.Markdown,
                "text/markdown; charset=utf-8",
                $"{projection.ProjectId}-{projection.RevisionId}.md",
                projection.MarkdownSha256),
            "receipt" => new(
                projection.ReceiptJson,
                "application/json; charset=utf-8",
                $"{projection.ProjectId}-{projection.RevisionId}.receipt.json",
                projection.ReceiptSha256),
            _ => throw new ArgumentException("Origin Dossier first-party export format must be json, markdown, or receipt.", nameof(format))
        };
    }

    private static NormalizedOriginDossierRequest NormalizeRequest(OriginDossierFirstPartyDocumentRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (!request.OwnerApproved)
        {
            throw new InvalidOperationException("The owner must approve all first-party inputs before preview generation.");
        }

        string title = RequireText(request.Title, nameof(request.Title), 160);
        string runnerAlias = RequireText(request.RunnerAlias, nameof(request.RunnerAlias), 120);
        OriginDossierFirstPartyInput[] supplied = request.Inputs?.ToArray() ?? [];
        if (supplied.Length is < 1 or > MaximumInputs)
        {
            throw new ArgumentException($"Origin Dossier requires between 1 and {MaximumInputs} approved first-party inputs.", nameof(request));
        }

        NormalizedOriginDossierInput[] normalized = supplied
            .Select(input =>
            {
                ArgumentNullException.ThrowIfNull(input);
                if (!input.OwnerApproved)
                {
                    throw new InvalidOperationException("Every Origin Dossier first-party input must be owner-approved.");
                }

                string sourceKind = RequireText(input.SourceKind, nameof(input.SourceKind), 40).ToLowerInvariant();
                if (!ApprovedSourceKinds.Contains(sourceKind))
                {
                    throw new InvalidOperationException($"Origin Dossier source kind '{sourceKind}' is not an approved first-party source.");
                }

                return new NormalizedOriginDossierInput(
                    RequireText(input.Field, nameof(input.Field), 80).ToLowerInvariant(),
                    RequireText(input.Value, nameof(input.Value), 4_000),
                    sourceKind,
                    RequireIdentifier(input.SourceReference, nameof(input.SourceReference)));
            })
            .OrderBy(static input => input.Field, StringComparer.Ordinal)
            .ThenBy(static input => input.SourceKind, StringComparer.Ordinal)
            .ThenBy(static input => input.SourceReference, StringComparer.Ordinal)
            .ThenBy(static input => input.Value, StringComparer.Ordinal)
            .ToArray();
        if (normalized
            .GroupBy(static input => $"{input.Field}\0{input.SourceKind}\0{input.SourceReference}", StringComparer.Ordinal)
            .Any(static group => group.Count() > 1))
        {
            throw new ArgumentException("Origin Dossier first-party input identities must be unique.", nameof(request));
        }

        return new NormalizedOriginDossierRequest(title, runnerAlias, normalized);
    }

    private void EnsureRevisionCapacity(string ownerScopeSha256)
    {
        string ownerRoot = Path.Combine(_root, ownerScopeSha256);
        if (CountRevisionDirectories(ownerRoot, ownerScoped: true) >= _maxRevisionsPerOwner)
        {
            throw new InvalidOperationException(
                "Origin Dossier first-party owner revision capacity is reached; delete an existing private draft before retrying.");
        }

        if (CountRevisionDirectories(_root, ownerScoped: false) >= _maxRevisionsGlobal)
        {
            throw new InvalidOperationException(
                "Origin Dossier first-party global revision capacity is reached; no new private draft was written.");
        }
    }

    private static int CountRevisionDirectories(string root, bool ownerScoped)
    {
        if (!Directory.Exists(root))
        {
            return 0;
        }

        EnsureDirectoryIsNotLinked(root);
        int count = 0;
        IEnumerable<string> ownerRoots = ownerScoped ? [root] : EnumerateSafeDirectories(root);
        foreach (string ownerRoot in ownerRoots)
        {
            foreach (string projectRoot in EnumerateSafeDirectories(ownerRoot))
            {
                foreach (string revisionRoot in EnumerateSafeDirectories(projectRoot))
                {
                    if (TemporaryRevisionName.IsMatch(Path.GetFileName(revisionRoot)))
                    {
                        continue;
                    }

                    count++;
                    if (count >= AbsoluteMaxRevisions)
                    {
                        return count;
                    }
                }
            }
        }

        return count;
    }

    private static IEnumerable<string> EnumerateSafeDirectories(string root)
    {
        foreach (string directory in Directory.EnumerateDirectories(root))
        {
            if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException(
                    "Origin Dossier first-party storage contains a linked directory and fails closed.");
            }

            yield return directory;
        }
    }

    private static int ReadBoundedLimit(
        IConfiguration configuration,
        string environmentKey,
        string configurationKey,
        int fallback)
    {
        string? raw = configuration[environmentKey] ?? configuration[configurationKey];
        if (string.IsNullOrWhiteSpace(raw))
        {
            return fallback;
        }

        if (!int.TryParse(raw.Trim(), out int value) || value is < 1 or > AbsoluteMaxRevisions)
        {
            throw new InvalidOperationException(
                $"{configurationKey} must be an integer between 1 and {AbsoluteMaxRevisions}.");
        }

        return value;
    }

    private static void DeleteIfEmpty(string directory)
    {
        if (!Directory.Exists(directory))
        {
            return;
        }

        EnsureDirectoryIsNotLinked(directory);
        if (!Directory.EnumerateFileSystemEntries(directory).Any())
        {
            Directory.Delete(directory);
        }
    }

    private static void EnsureDirectoryIsNotLinked(string directory)
    {
        if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException(
                "Origin Dossier first-party storage contains a linked directory and fails closed.");
        }
    }

    private static void EnsureDirectoryTreeContainsNoLinks(string root)
    {
        EnsureDirectoryIsNotLinked(root);
        foreach (string entry in Directory.EnumerateFileSystemEntries(root))
        {
            FileAttributes attributes = File.GetAttributes(entry);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException(
                    "Origin Dossier first-party storage contains a linked entry and fails closed.");
            }

            if ((attributes & FileAttributes.Directory) != 0)
            {
                EnsureDirectoryTreeContainsNoLinks(entry);
            }
        }
    }

    private static void ScavengeStaleTemporaryRevisions(string projectRoot)
    {
        if (!Directory.Exists(projectRoot))
        {
            return;
        }

        EnsureDirectoryIsNotLinked(projectRoot);
        DateTime staleBeforeUtc = DateTime.UtcNow.Subtract(TemporaryRevisionStaleAfter);
        int directoriesInspected = 0;
        int scavenged = 0;
        foreach (string candidate in Directory.EnumerateDirectories(projectRoot))
        {
            if (directoriesInspected >= MaxTemporaryDirectoriesInspectedPerPreview
                || scavenged >= MaxTemporaryDirectoriesScavengedPerPreview)
            {
                break;
            }

            directoriesInspected++;
            string candidateName = Path.GetFileName(candidate);
            if (!TemporaryRevisionName.IsMatch(candidateName))
            {
                continue;
            }

            FileAttributes candidateAttributes = File.GetAttributes(candidate);
            if ((candidateAttributes & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException(
                    "Origin Dossier first-party temporary storage contains a linked directory and fails closed.");
            }

            if (!IsStaleInactiveTemporaryRevision(candidate, staleBeforeUtc))
            {
                continue;
            }

            EnsureDirectoryTreeContainsNoLinks(candidate);
            Directory.Delete(candidate, recursive: true);
            scavenged++;
        }
    }

    private static bool IsStaleInactiveTemporaryRevision(string temporaryRoot, DateTime staleBeforeUtc)
    {
        string[] entries = Directory.EnumerateFileSystemEntries(temporaryRoot)
            .Take(MaxTemporaryRevisionEntries + 1)
            .ToArray();
        if (entries.Length > MaxTemporaryRevisionEntries)
        {
            return false;
        }

        DateTime latestWriteUtc = Directory.GetLastWriteTimeUtc(temporaryRoot);
        foreach (string entry in entries)
        {
            FileAttributes attributes = File.GetAttributes(entry);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException(
                    "Origin Dossier first-party temporary storage contains a linked entry and fails closed.");
            }

            if ((attributes & FileAttributes.Directory) != 0
                || !TemporaryRevisionFiles.Contains(Path.GetFileName(entry)))
            {
                return false;
            }

            latestWriteUtc = DateTime.SpecifyKind(
                latestWriteUtc > File.GetLastWriteTimeUtc(entry)
                    ? latestWriteUtc
                    : File.GetLastWriteTimeUtc(entry),
                DateTimeKind.Utc);
        }

        if (latestWriteUtc > staleBeforeUtc)
        {
            return false;
        }

        string activeMarker = Path.Combine(temporaryRoot, ".active");
        if (!File.Exists(activeMarker))
        {
            return true;
        }

        try
        {
            using var lease = new FileStream(
                activeMarker,
                FileMode.Open,
                FileAccess.ReadWrite,
                FileShare.None);
            return true;
        }
        catch (IOException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static string RenderMarkdown(
        string projectId,
        string revisionId,
        NormalizedOriginDossierRequest request,
        string storagePosture)
    {
        var builder = new StringBuilder();
        builder.AppendLine("# Origin Dossier — First-Party Preview");
        builder.AppendLine();
        builder.AppendLine("> PRIVATE OWNER-SCOPED ARTIFACT. NON-CANON DRAFT. No provider execution or quota use occurred.");
        builder.AppendLine();
        builder.AppendLine($"- Project: `{projectId}`");
        builder.AppendLine($"- Revision: `{revisionId}`");
        builder.AppendLine("- Canon status: `non_canon_private_draft`");
        builder.AppendLine("- Visibility: `private_owner_scoped`");
        builder.AppendLine("- Governed premium media: `blocked_by_existing_governance`");
        builder.AppendLine("- Release scope: `unchanged`");
        builder.AppendLine($"- Storage posture: `{storagePosture}`");
        builder.AppendLine();
        builder.AppendLine($"## {EscapeMarkdown(request.Title)}");
        builder.AppendLine();
        builder.AppendLine($"**Runner alias:** {EscapeMarkdown(request.RunnerAlias)}");
        builder.AppendLine();
        builder.AppendLine("## Approved first-party inputs");
        builder.AppendLine();
        foreach (NormalizedOriginDossierInput input in request.Inputs)
        {
            builder.AppendLine($"### {EscapeMarkdown(input.Field)}");
            builder.AppendLine();
            builder.AppendLine(EscapeMarkdown(input.Value));
            builder.AppendLine();
            builder.AppendLine($"Source: `{input.SourceKind}/{input.SourceReference}` (owner approved)");
            builder.AppendLine();
        }

        return builder.ToString().Replace("\r\n", "\n", StringComparison.Ordinal);
    }

    private static string RenderDocumentJson(
        string ownerScopeSha256,
        string projectId,
        string revisionId,
        NormalizedOriginDossierRequest request,
        string storagePosture)
        => Serialize(new FirstPartyDocumentArtifact(
            DocumentContract,
            projectId,
            revisionId,
            request.Title,
            request.RunnerAlias,
            new FirstPartyDocumentBoundaries(
                PrivateOwnerScoped: true,
                CanonStatus,
                ProviderExecution,
                ProviderCalls: 0,
                QuotaUnitsClaimed: 0,
                PremiumMediaState,
                ReleaseScope,
                storagePosture),
            ownerScopeSha256,
            request.Inputs));

    private static string RenderReceipt(
        string operation,
        FirstPartyDocumentMetadata metadata,
        string metadataSha256,
        int markdownLength,
        int jsonLength,
        string? previewReceiptSha256)
        => Serialize(new FirstPartyDocumentReceipt(
            ReceiptContract,
            operation,
            metadata.ProjectId,
            metadata.RevisionId,
            metadata.OwnerScopeSha256,
            metadata.CanonicalInputSha256,
            metadataSha256,
            new FirstPartyDocumentBoundaries(
                PrivateOwnerScoped: true,
                CanonStatus,
                ProviderExecution,
                ProviderCalls: 0,
                QuotaUnitsClaimed: 0,
                PremiumMediaState,
                ReleaseScope,
                metadata.StoragePosture),
            [
                new("document.md", metadata.MarkdownSha256, markdownLength),
                new("document.json", metadata.JsonSha256, jsonLength)
            ],
            previewReceiptSha256));

    private void PersistNewRevision(
        string revisionRoot,
        string metadataJson,
        string markdown,
        string documentJson,
        string previewReceipt)
    {
        string parent = Path.GetDirectoryName(revisionRoot)!;
        EnsurePrivateDirectory(_root);
        EnsurePrivateDirectory(Path.GetDirectoryName(parent)!);
        EnsurePrivateDirectory(parent);
        string temporaryRoot = $"{revisionRoot}.tmp-{Guid.NewGuid():N}";
        EnsurePrivateDirectory(temporaryRoot);
        try
        {
            string activeMarker = Path.Combine(temporaryRoot, ".active");
            using (var activeLease = new FileStream(
                       activeMarker,
                       FileMode.CreateNew,
                       FileAccess.ReadWrite,
                       FileShare.None))
            {
                if (!OperatingSystem.IsWindows())
                {
                    File.SetUnixFileMode(activeMarker, UnixFileMode.UserRead | UnixFileMode.UserWrite);
                }

                WriteImmutable(Path.Combine(temporaryRoot, "metadata.json"), metadataJson);
                WriteImmutable(Path.Combine(temporaryRoot, "document.md"), markdown);
                WriteImmutable(Path.Combine(temporaryRoot, "document.json"), documentJson);
                WriteImmutable(Path.Combine(temporaryRoot, "preview-receipt.json"), previewReceipt);
                activeLease.Flush(flushToDisk: true);
            }

            File.Delete(activeMarker);
            try
            {
                Directory.Move(temporaryRoot, revisionRoot);
            }
            catch (IOException) when (Directory.Exists(revisionRoot))
            {
                Directory.Delete(temporaryRoot, recursive: true);
            }
        }
        catch
        {
            if (Directory.Exists(temporaryRoot))
            {
                Directory.Delete(temporaryRoot, recursive: true);
            }

            throw;
        }
    }

    private OriginDossierFirstPartyDocumentProjection LoadProjection(
        string revisionRoot,
        string expectedOwnerScopeSha256,
        string expectedProjectId,
        string expectedRevisionId)
        => LoadValidatedRevision(
            revisionRoot,
            expectedOwnerScopeSha256,
            expectedProjectId,
            expectedRevisionId).Projection;

    private ValidatedFirstPartyDocument LoadValidatedRevision(
        string revisionRoot,
        string expectedOwnerScopeSha256,
        string expectedProjectId,
        string expectedRevisionId)
    {
        string projectRoot = Path.GetDirectoryName(revisionRoot)!;
        string ownerRoot = Path.GetDirectoryName(projectRoot)!;
        EnsureDirectoryIsNotLinked(_root);
        EnsureDirectoryIsNotLinked(ownerRoot);
        EnsureDirectoryIsNotLinked(projectRoot);
        EnsureDirectoryTreeContainsNoLinks(revisionRoot);
        string metadataJson = File.ReadAllText(Path.Combine(revisionRoot, "metadata.json"), Encoding.UTF8);
        FirstPartyDocumentMetadata metadata = DeserializeMetadata(metadataJson);
        if (!FixedEquals(metadata.OwnerScopeSha256, expectedOwnerScopeSha256)
            || !string.Equals(metadata.ProjectId, expectedProjectId, StringComparison.Ordinal)
            || !string.Equals(metadata.RevisionId, expectedRevisionId, StringComparison.Ordinal)
            || !string.Equals(metadata.ContractName, DocumentContract, StringComparison.Ordinal)
            || !string.Equals(metadata.StoragePosture, _storagePosture, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Origin Dossier first-party ownership or revision metadata does not match its storage scope.");
        }

        NormalizedOriginDossierRequest normalized = ValidateStoredRequest(metadata);
        string canonicalInputJson = Serialize(new CanonicalOriginDossierInput(
            DocumentContract,
            metadata.ProjectId,
            normalized.Title,
            normalized.RunnerAlias,
            normalized.Inputs));
        string canonicalInputSha256 = Sha256(canonicalInputJson);
        string derivedRevisionId = $"odfp-{canonicalInputSha256[..24]}";
        if (!IsSha256(metadata.CanonicalInputSha256)
            || !IsSha256(metadata.MarkdownSha256)
            || !IsSha256(metadata.JsonSha256)
            || !FixedEquals(metadata.CanonicalInputSha256, canonicalInputSha256)
            || !string.Equals(metadata.RevisionId, derivedRevisionId, StringComparison.Ordinal)
            || !string.Equals(metadataJson, Serialize(metadata), StringComparison.Ordinal))
        {
            throw new InvalidDataException("Origin Dossier first-party metadata integrity validation failed.");
        }

        string markdown = File.ReadAllText(Path.Combine(revisionRoot, "document.md"), Encoding.UTF8);
        string documentJson = File.ReadAllText(Path.Combine(revisionRoot, "document.json"), Encoding.UTF8);
        string expectedMarkdown = RenderMarkdown(
            metadata.ProjectId,
            metadata.RevisionId,
            normalized,
            metadata.StoragePosture);
        string expectedDocumentJson = RenderDocumentJson(
            metadata.OwnerScopeSha256,
            metadata.ProjectId,
            metadata.RevisionId,
            normalized,
            metadata.StoragePosture);
        if (!string.Equals(markdown, expectedMarkdown, StringComparison.Ordinal)
            || !string.Equals(documentJson, expectedDocumentJson, StringComparison.Ordinal)
            || !FixedEquals(Sha256(markdown), metadata.MarkdownSha256)
            || !FixedEquals(Sha256(documentJson), metadata.JsonSha256))
        {
            throw new InvalidDataException("Origin Dossier first-party artifact digest validation failed.");
        }

        string metadataSha256 = Sha256(metadataJson);
        string previewReceiptPath = Path.Combine(revisionRoot, "preview-receipt.json");
        string previewReceiptJson = File.ReadAllText(previewReceiptPath, Encoding.UTF8);
        string expectedPreviewReceiptJson = RenderReceipt(
            "preview",
            metadata,
            metadataSha256,
            markdown.Length,
            documentJson.Length,
            previewReceiptSha256: null);
        if (!string.Equals(previewReceiptJson, expectedPreviewReceiptJson, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Origin Dossier first-party preview receipt integrity validation failed.");
        }

        string previewReceiptSha256 = Sha256(previewReceiptJson);
        string exportReceiptPath = Path.Combine(revisionRoot, "export-receipt.json");
        string state = File.Exists(exportReceiptPath) ? "exported" : "preview";
        string receiptJson = previewReceiptJson;
        if (string.Equals(state, "exported", StringComparison.Ordinal))
        {
            receiptJson = File.ReadAllText(exportReceiptPath, Encoding.UTF8);
            string expectedExportReceiptJson = RenderReceipt(
                "exported",
                metadata,
                metadataSha256,
                markdown.Length,
                documentJson.Length,
                previewReceiptSha256);
            if (!string.Equals(receiptJson, expectedExportReceiptJson, StringComparison.Ordinal))
            {
                throw new InvalidDataException("Origin Dossier first-party export receipt integrity validation failed.");
            }
        }

        var projection = new OriginDossierFirstPartyDocumentProjection(
            DocumentContract,
            metadata.ProjectId,
            metadata.RevisionId,
            state,
            metadata.Title,
            metadata.RunnerAlias,
            PrivateOwnerScoped: true,
            CanonStatus,
            ProviderExecution,
            ProviderCalls: 0,
            QuotaUnitsClaimed: 0,
            PremiumMediaState,
            ReleaseScope,
            metadata.StoragePosture,
            metadata.CanonicalInputSha256,
            metadata.MarkdownSha256,
            metadata.JsonSha256,
            Sha256(receiptJson),
            markdown,
            documentJson,
            receiptJson);
        return new ValidatedFirstPartyDocument(
            metadata,
            metadataSha256,
            markdown,
            documentJson,
            previewReceiptSha256,
            projection);
    }

    private static FirstPartyDocumentMetadata DeserializeMetadata(string metadataJson)
    {
        try
        {
            return JsonSerializer.Deserialize<FirstPartyDocumentMetadata>(metadataJson, JsonOptions)
                ?? throw new InvalidDataException("Origin Dossier first-party metadata is invalid.");
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException("Origin Dossier first-party metadata is invalid.", ex);
        }
    }

    private static NormalizedOriginDossierRequest ValidateStoredRequest(FirstPartyDocumentMetadata metadata)
    {
        try
        {
            if (metadata.Inputs is null)
            {
                throw new InvalidDataException("Origin Dossier first-party metadata inputs are missing.");
            }

            NormalizedOriginDossierRequest normalized = NormalizeRequest(new OriginDossierFirstPartyDocumentRequest(
                metadata.Title,
                metadata.RunnerAlias,
                metadata.Inputs.Select(static input => new OriginDossierFirstPartyInput(
                    input.Field,
                    input.Value,
                    input.SourceKind,
                    input.SourceReference,
                    OwnerApproved: true)).ToArray(),
                OwnerApproved: true));
            if (!string.Equals(metadata.Title, normalized.Title, StringComparison.Ordinal)
                || !string.Equals(metadata.RunnerAlias, normalized.RunnerAlias, StringComparison.Ordinal)
                || !metadata.Inputs.SequenceEqual(normalized.Inputs))
            {
                throw new InvalidDataException("Origin Dossier first-party metadata is not in canonical form.");
            }

            return normalized;
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or NullReferenceException)
        {
            throw new InvalidDataException("Origin Dossier first-party metadata is not valid canonical input.", ex);
        }
    }

    private string ResolveRevisionRoot(string ownerScopeSha256, string projectId, string revisionId)
        => Path.Combine(_root, ownerScopeSha256, projectId, revisionId);

    private static string ResolveOwnerScope(string ownerUserId, string ownerSubjectId)
    {
        string userId = RequireText(ownerUserId, nameof(ownerUserId), 256);
        string subjectId = RequireText(ownerSubjectId, nameof(ownerSubjectId), 512);
        return Sha256($"chummer-origin-dossier-owner-v1\0{userId}\0{subjectId}");
    }

    private static string RequireIdentifier(string? value, string parameterName)
    {
        string normalized = RequireText(value, parameterName, 96);
        return SafeIdentifier.IsMatch(normalized)
            ? normalized
            : throw new ArgumentException($"{parameterName} must be an ASCII identifier without path separators.", parameterName);
    }

    private static string RequireText(string? value, string parameterName, int maximumLength)
    {
        string normalized = string.Join(
            " ",
            (value ?? string.Empty).Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
        if (string.IsNullOrWhiteSpace(normalized) || normalized.Length > maximumLength)
        {
            throw new ArgumentException($"{parameterName} is required and must be at most {maximumLength} characters.", parameterName);
        }

        return normalized;
    }

    private static string EscapeMarkdown(string value)
        => value.Replace("\\", "\\\\", StringComparison.Ordinal)
            .Replace("`", "\\`", StringComparison.Ordinal)
            .Replace("#", "\\#", StringComparison.Ordinal)
            .Replace("*", "\\*", StringComparison.Ordinal)
            .Replace("_", "\\_", StringComparison.Ordinal)
            .Replace("<", "&lt;", StringComparison.Ordinal)
            .Replace(">", "&gt;", StringComparison.Ordinal)
            .Replace("[", "\\[", StringComparison.Ordinal)
            .Replace("]", "\\]", StringComparison.Ordinal);

    private static string Serialize<T>(T value)
        => JsonSerializer.Serialize(value, JsonOptions).Replace("\r\n", "\n", StringComparison.Ordinal) + "\n";

    private static void WriteImmutable(string path, string content)
    {
        using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        using var writer = new StreamWriter(stream, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        writer.Write(content);
        writer.Flush();
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        }
    }

    private static void EnsurePrivateDirectory(string path)
    {
        Directory.CreateDirectory(path);
        EnsureDirectoryIsNotLinked(path);
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(
                path,
                UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        }
    }

    private static string Sha256(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static bool IsSha256(string? value)
        => value is not null && Sha256Digest.IsMatch(value);

    private static bool FixedEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.ASCII.GetBytes(left);
        byte[] rightBytes = Encoding.ASCII.GetBytes(right);
        return leftBytes.Length == rightBytes.Length
            && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private sealed record NormalizedOriginDossierRequest(
        string Title,
        string RunnerAlias,
        IReadOnlyList<NormalizedOriginDossierInput> Inputs);

    private sealed record CanonicalOriginDossierInput(
        string ContractName,
        string ProjectId,
        string Title,
        string RunnerAlias,
        IReadOnlyList<NormalizedOriginDossierInput> Inputs);

    private sealed record FirstPartyDocumentMetadata(
        string ContractName,
        string OwnerScopeSha256,
        string ProjectId,
        string RevisionId,
        string Title,
        string RunnerAlias,
        IReadOnlyList<NormalizedOriginDossierInput> Inputs,
        string StoragePosture,
        string CanonicalInputSha256,
        string MarkdownSha256,
        string JsonSha256);

    private sealed record FirstPartyDocumentArtifact(
        string ContractName,
        string ProjectId,
        string RevisionId,
        string Title,
        string RunnerAlias,
        FirstPartyDocumentBoundaries Boundaries,
        string OwnerScopeSha256,
        IReadOnlyList<NormalizedOriginDossierInput> ApprovedFirstPartyInputs);

    private sealed record FirstPartyDocumentReceipt(
        string ContractName,
        string Operation,
        string ProjectId,
        string RevisionId,
        string OwnerScopeSha256,
        string CanonicalInputSha256,
        string MetadataSha256,
        FirstPartyDocumentBoundaries Boundaries,
        IReadOnlyList<FirstPartyDocumentReceiptArtifact> Artifacts,
        string? PreviewReceiptSha256);

    private sealed record ValidatedFirstPartyDocument(
        FirstPartyDocumentMetadata Metadata,
        string MetadataSha256,
        string Markdown,
        string DocumentJson,
        string PreviewReceiptSha256,
        OriginDossierFirstPartyDocumentProjection Projection);

    private sealed record FirstPartyDocumentReceiptArtifact(string Name, string Sha256, int Utf16Length);
}

public sealed record OriginDossierFirstPartyDocumentRequest(
    string Title,
    string RunnerAlias,
    IReadOnlyList<OriginDossierFirstPartyInput>? Inputs,
    bool OwnerApproved);

public sealed record OriginDossierFirstPartyInput(
    string Field,
    string Value,
    string SourceKind,
    string SourceReference,
    bool OwnerApproved);

public sealed record NormalizedOriginDossierInput(
    string Field,
    string Value,
    string SourceKind,
    string SourceReference);

public sealed record FirstPartyDocumentBoundaries(
    bool PrivateOwnerScoped,
    string CanonStatus,
    string ProviderExecution,
    int ProviderCalls,
    int QuotaUnitsClaimed,
    string PremiumMediaState,
    string ReleaseScope,
    string StoragePosture);

public sealed record OriginDossierFirstPartyDocumentProjection(
    string ContractName,
    string ProjectId,
    string RevisionId,
    string State,
    string Title,
    string RunnerAlias,
    bool PrivateOwnerScoped,
    string CanonStatus,
    string ProviderExecution,
    int ProviderCalls,
    int QuotaUnitsClaimed,
    string PremiumMediaState,
    string ReleaseScope,
    string StoragePosture,
    string CanonicalInputSha256,
    string MarkdownSha256,
    string JsonSha256,
    string ReceiptSha256,
    string Markdown,
    string Json,
    string ReceiptJson);

public sealed record OriginDossierFirstPartyExportArtifact(
    string Content,
    string ContentType,
    string FileName,
    string Sha256);
