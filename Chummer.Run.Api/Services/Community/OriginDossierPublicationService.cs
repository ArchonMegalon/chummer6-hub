using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace Chummer.Run.Api.Services.Community;

public sealed class OriginDossierPublicationService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private static readonly IReadOnlyList<string> ApprovedManuscriptProviderTokens = ["Inkfluence", "Youbooks", "First Book", "FirstBook"];
    private static readonly IReadOnlyList<string> ApprovedAudiobookProviderTokens = ["Inkfluence", "Unmixr"];
    private const string SelectedCharacterFaceProofToken = "selected_character_face";
    private const string ApprovedSourcePacketToken = "approved_source_packet";
    private const string ExternalProcessingConsentToken = "external_processing_consent";
    private const string CanonAuditPassedToken = "canon_audit_passed";
    private const string HardConflictsZeroToken = "hard_conflicts:0";
    private const string PrivacyFindingsZeroToken = "privacy_findings:0";
    private const string OperatorVerifiedLiveRunToken = "operator_verified_live_run";
    private const string ProviderReceiptReferenceToken = "provider_receipt_reference";
    private readonly IConfiguration _configuration;
    private readonly ILogger<OriginDossierPublicationService> _logger;

    public OriginDossierPublicationService(
        IConfiguration configuration,
        ILogger<OriginDossierPublicationService> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public IReadOnlyList<OriginDossierPublicationViewModel> ListForAccount(string userId, string subjectId)
    {
        string? indexPath = ResolveIndexPath();
        if (string.IsNullOrWhiteSpace(indexPath) || !File.Exists(indexPath))
        {
            return Array.Empty<OriginDossierPublicationViewModel>();
        }

        try
        {
            IReadOnlyList<OriginDossierPublicationIndexEntry> entries = LoadEntries(indexPath);
            return entries
                .Where(entry => IsOwnedBy(entry, userId, subjectId))
                .Select(BuildViewModel)
                .OrderByDescending(static publication => publication.GoldReady)
                .ThenBy(static publication => publication.Title, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
        {
            _logger.LogWarning(ex, "Origin Dossier publication index could not be loaded from {IndexPath}.", indexPath);
            return Array.Empty<OriginDossierPublicationViewModel>();
        }
    }

    public OriginDossierPublicationViewModel? GetForAccount(string userId, string subjectId, string projectId)
        => string.IsNullOrWhiteSpace(projectId)
            ? null
            : ListForAccount(userId, subjectId)
                .FirstOrDefault(publication => Matches(publication.ProjectId, projectId));

    public OriginDossierPublicationArtifact? GetArtifactForAccount(
        string userId,
        string subjectId,
        string projectId,
        string artifactKind)
    {
        if (string.IsNullOrWhiteSpace(projectId) || string.IsNullOrWhiteSpace(artifactKind))
        {
            return null;
        }

        string? indexPath = ResolveIndexPath();
        if (string.IsNullOrWhiteSpace(indexPath) || !File.Exists(indexPath))
        {
            return null;
        }

        try
        {
            OriginDossierPublicationIndexEntry? entry = LoadEntries(indexPath)
                .FirstOrDefault(candidate =>
                    IsOwnedBy(candidate, userId, subjectId)
                    && Matches(candidate.ProjectId, projectId));
            if (entry is null || !BuildViewModel(entry).GoldReady)
            {
                return null;
            }

            string? path = artifactKind.Trim().ToLowerInvariant() switch
            {
                "book" => entry.BookArtifactPath,
                "cover" => entry.StorySceneCoverPath,
                "video" => entry.DossierVideoPath,
                _ => null
            };

            return HasArchivedArtifact(path)
                ? new OriginDossierPublicationArtifact(path!, ResolveContentType(path!, artifactKind))
                : null;
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
        {
            _logger.LogWarning(ex, "Origin Dossier publication artifact could not be loaded from {IndexPath}.", indexPath);
            return null;
        }
    }

    public string? GetAudiobookshelfShareForAccount(
        string userId,
        string subjectId,
        string projectId,
        string shareKind = "audiobook")
    {
        if (string.IsNullOrWhiteSpace(projectId))
        {
            return null;
        }

        string? indexPath = ResolveIndexPath();
        if (string.IsNullOrWhiteSpace(indexPath) || !File.Exists(indexPath))
        {
            return null;
        }

        try
        {
            OriginDossierPublicationIndexEntry? entry = LoadEntries(indexPath)
                .FirstOrDefault(candidate =>
                    IsOwnedBy(candidate, userId, subjectId)
                    && Matches(candidate.ProjectId, projectId));
            if (entry is null || !BuildViewModel(entry).GoldReady)
            {
                return null;
            }

            string? shareUrl = shareKind.Trim().ToLowerInvariant() switch
            {
                "dossier" or "read" or "ebook" => entry.AudiobookshelfDossierShareUrl,
                "audiobook" or "listen" => entry.AudiobookshelfAudiobookShareUrl ?? entry.AudiobookshelfShareUrl,
                _ => null
            };
            return IsTrustedAudiobookshelfShareUrl(shareUrl)
                ? shareUrl
                : null;
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
        {
            _logger.LogWarning(ex, "Origin Dossier Audiobookshelf share could not be loaded from {IndexPath}.", indexPath);
            return null;
        }
    }

    public OriginDossierPublicationViewModel UpsertForAccount(
        HubUserDto user,
        string subjectId,
        OriginDossierPublicationImportRequest request)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        string projectId = Clean(request.ProjectId, string.Empty);
        if (string.IsNullOrWhiteSpace(projectId))
        {
            throw new InvalidOperationException("Origin Dossier projectId is required.");
        }

        string? indexPath = ResolveIndexPath();
        if (string.IsNullOrWhiteSpace(indexPath))
        {
            throw new InvalidOperationException("Origin Dossier publication index path is not configured.");
        }

        OriginDossierPublicationIndexEntry entry = BuildOwnedEntry(user, subjectId, request, projectId);
        lock (_writeGate)
        {
            List<OriginDossierPublicationIndexEntry> entries = File.Exists(indexPath)
                ? LoadEntries(indexPath).ToList()
                : new List<OriginDossierPublicationIndexEntry>();
            int existingIndex = entries.FindIndex(candidate =>
                Matches(candidate.OwnerUserId, user.UserId)
                && Matches(candidate.ProjectId, projectId));
            if (existingIndex >= 0)
            {
                entries[existingIndex] = entry;
            }
            else
            {
                entries.Add(entry);
            }

            PersistEntries(indexPath, entries);
        }

        return BuildViewModel(entry);
    }

    public static OriginDossierPublicationImportResultDto ToImportResult(OriginDossierPublicationViewModel publication)
        => new(
            ProjectId: publication.ProjectId,
            Title: publication.Title,
            RunnerAlias: publication.RunnerAlias,
            PublicationState: publication.PublicationState,
            ChummerRunOwnerUrl: publication.ChummerRunOwnerUrl,
            BookArtifactUrl: publication.BookArtifactUrl,
            AudiobookshelfShareUrl: publication.AudiobookshelfShareUrl,
            DossierVideoUrl: publication.DossierVideoUrl,
            StorySceneCoverUrl: publication.StorySceneCoverUrl,
            ProviderAuthoredManuscriptImported: publication.ProviderAuthoredManuscriptImported,
            UndetectableHumanizerApplied: publication.UndetectableHumanizerApplied,
            BookArtifactVerified: publication.BookArtifactVerified,
            DossierVideoVerified: publication.DossierVideoVerified,
            StorySceneCoverUsesSelectedCharacterFace: publication.StorySceneCoverUsesSelectedCharacterFace,
            AudiobookshelfPlaybackVerified: publication.AudiobookshelfPlaybackVerified,
            TelegramShareDelivered: publication.TelegramShareDelivered,
            RequiresAuthenticatedChummerRunUser: publication.RequiresAuthenticatedChummerRunUser,
            GoldReady: publication.GoldReady,
            MissingGoldRequirements: publication.MissingGoldRequirements,
            FamilyName: publication.FamilyName,
            GivenName: publication.GivenName,
            RunnerName: publication.RunnerName,
            OriginEditionNamespace: publication.OriginEditionNamespace,
            AudiobookshelfDossierShareUrl: publication.AudiobookshelfDossierShareUrl,
            AudiobookshelfAudiobookShareUrl: publication.AudiobookshelfAudiobookShareUrl);

    private string? ResolveIndexPath()
    {
        string? configured = _configuration["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"]
            ?? _configuration["OriginDossier:PublicationIndexPath"];
        return string.IsNullOrWhiteSpace(configured)
            ? null
            : Path.GetFullPath(configured.Trim());
    }

    private string ResolvePublicBaseUrl()
        => (_configuration["CHUMMER_PUBLIC_BASE_URL"]
            ?? _configuration["OriginDossier:PublicBaseUrl"]
            ?? "https://chummer.run").Trim().TrimEnd('/');

    private static readonly object _writeGate = new();

    private static IReadOnlyList<OriginDossierPublicationIndexEntry> LoadEntries(string indexPath)
    {
        using JsonDocument document = JsonDocument.Parse(File.ReadAllText(indexPath, Encoding.UTF8));
        JsonElement source = document.RootElement;
        if (source.ValueKind == JsonValueKind.Object)
        {
            if (source.TryGetProperty("publications", out JsonElement publications))
            {
                source = publications;
            }
            else if (source.TryGetProperty("originDossierPublications", out JsonElement originDossierPublications))
            {
                source = originDossierPublications;
            }
        }

        if (source.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<OriginDossierPublicationIndexEntry>();
        }

        return source.Deserialize<OriginDossierPublicationIndexEntry[]>(JsonOptions)
            ?? Array.Empty<OriginDossierPublicationIndexEntry>();
    }

    private static void PersistEntries(string indexPath, IReadOnlyList<OriginDossierPublicationIndexEntry> entries)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(indexPath)!);
        var snapshot = new OriginDossierPublicationIndexSnapshot(
            entries
                .OrderBy(static item => item.OwnerUserId, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static item => item.ProjectId, StringComparer.OrdinalIgnoreCase)
                .ToArray());
        string tempPath = $"{indexPath}.tmp";
        File.WriteAllText(
            tempPath,
            JsonSerializer.Serialize(snapshot, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }),
            Encoding.UTF8);
        File.Move(tempPath, indexPath, true);
    }

    private static bool IsOwnedBy(OriginDossierPublicationIndexEntry entry, string userId, string subjectId)
        => Matches(entry.OwnerUserId, userId)
            || Matches(entry.SubjectId, subjectId)
            || Matches(entry.OwnerSubjectId, subjectId);

    private OriginDossierPublicationViewModel BuildViewModel(OriginDossierPublicationIndexEntry entry)
    {
        IReadOnlyList<string> missing = ResolveMissingRequirements(entry);
        string projectId = Clean(entry.ProjectId, "origin-dossier");
        return new OriginDossierPublicationViewModel(
            ProjectId: projectId,
            Title: Clean(entry.Title, "Origin Dossier"),
            RunnerAlias: Clean(entry.RunnerAlias, "Runner"),
            PublicationState: Clean(entry.PublicationState, "awaiting_provider_manuscript"),
            ChummerRunOwnerUrl: IsChummerRunOwnerUrl(entry)
                ? BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, null)
                : null,
            BookArtifactUrl: IsChummerRunArtifactUrl(entry, entry.BookArtifactUrl, "book")
                ? BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, "book")
                : null,
            AudiobookshelfShareUrl: IsTrustedAudiobookshelfShareUrl(entry.AudiobookshelfShareUrl)
                ? BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, "listen")
                : null,
            DossierVideoUrl: IsChummerRunArtifactUrl(entry, entry.DossierVideoUrl, "video")
                ? BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, "video")
                : null,
            StorySceneCoverUrl: IsChummerRunArtifactUrl(entry, entry.StorySceneCoverUrl, "cover")
                ? BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, "cover")
                : null,
            ProviderAuthoredManuscriptImported: entry.ProviderAuthoredManuscriptImported,
            UndetectableHumanizerApplied: entry.UndetectableHumanizerApplied,
            BookArtifactVerified: entry.BookArtifactVerified,
            DossierVideoVerified: entry.DossierVideoVerified,
            StorySceneCoverUsesSelectedCharacterFace: entry.StorySceneCoverUsesSelectedCharacterFace,
            AudiobookshelfPlaybackVerified: entry.AudiobookshelfPlaybackVerified,
            TelegramShareDelivered: entry.TelegramShareDelivered,
            RequiresAuthenticatedChummerRunUser: entry.RequiresAuthenticatedChummerRunUser,
            GoldReady: missing.Count == 0,
            MissingGoldRequirements: missing,
            FamilyName: Clean(entry.FamilyName, string.Empty),
            GivenName: Clean(entry.GivenName, string.Empty),
            RunnerName: Clean(entry.RunnerName, Clean(entry.RunnerAlias, "Runner")),
            OriginEditionNamespace: Clean(entry.OriginEditionNamespace, BuildOriginEditionNamespace(entry)),
            AudiobookshelfDossierShareUrl: IsTrustedAudiobookshelfShareUrl(entry.AudiobookshelfDossierShareUrl)
                ? BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, "read")
                : null,
            AudiobookshelfAudiobookShareUrl: IsTrustedAudiobookshelfShareUrl(entry.AudiobookshelfAudiobookShareUrl ?? entry.AudiobookshelfShareUrl)
                ? BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, "listen")
                : null);
    }

    private static IReadOnlyList<string> ResolveMissingRequirements(OriginDossierPublicationIndexEntry entry)
    {
        List<string> missing = new(entry.MissingGoldRequirements ?? Array.Empty<string>());
        AddIfMissing(missing, IsPublishedForOwner(entry.PublicationState), "published_for_owner publication state");
        AddIfMissing(missing, entry.ProviderAuthoredManuscriptImported, "provider-authored manuscript import");
        AddIfMissing(missing, entry.UndetectableHumanizerApplied, "Undetectable Humanizer receipt");
        AddIfMissing(missing, entry.StorySceneCoverUsesSelectedCharacterFace, "rendered story scene cover with selected character face");
        AddIfMissing(missing, entry.AudiobookshelfPlaybackVerified, "Audiobookshelf playback verification");
        AddIfMissing(missing, IsChummerRunOwnerUrl(entry), "authenticated chummer.run owner URL");
        AddIfMissing(missing, entry.BookArtifactVerified, "book artifact verification");
        AddIfMissing(missing, IsChummerRunArtifactUrl(entry, entry.BookArtifactUrl, "book"), "book artifact URL");
        AddIfMissing(missing, IsTrustedAudiobookshelfShareUrl(entry.AudiobookshelfShareUrl), "trusted Audiobookshelf share URL");
        AddIfMissing(missing, HasOriginEditionNamespace(entry), "canonical origin.chummer.run family/given/runner namespace");
        AddIfMissing(missing, IsTrustedAudiobookshelfShareUrl(entry.AudiobookshelfDossierShareUrl), "trusted Audiobookshelf dossier ebook share URL");
        AddIfMissing(missing, IsTrustedAudiobookshelfShareUrl(entry.AudiobookshelfAudiobookShareUrl ?? entry.AudiobookshelfShareUrl), "trusted Audiobookshelf audiobook share URL");
        AddIfMissing(missing, entry.DossierVideoVerified, "dossier video verification");
        AddIfMissing(missing, IsChummerRunArtifactUrl(entry, entry.DossierVideoUrl, "video"), "dossier video URL");
        AddIfMissing(missing, IsChummerRunArtifactUrl(entry, entry.StorySceneCoverUrl, "cover"), "rendered story scene cover URL");
        AddIfMissing(missing, HasArchivedArtifact(entry.SourcePacketPath), "approved source packet artifact path");
        AddIfMissing(missing, HasSourcePacketReceipt(entry.SourcePacketPath, entry.SourcePacketReceiptPath), "approved source packet receipt path");
        AddIfMissing(missing, HasArchivedArtifact(entry.ProviderManuscriptPath), "provider manuscript artifact path");
        AddIfMissing(missing, HasProviderManuscriptReceipt(entry.ProviderManuscriptPath, entry.ProviderManuscriptReceiptPath), "provider manuscript receipt path");
        AddIfMissing(
            missing,
            HasArtifactReceipt(
                entry.ProviderManuscriptPath,
                entry.HumanizerReceiptPath,
                "undetectable_humanizer_postprocess",
                "Undetectable",
                ExternalProviderReceiptTokens()),
            "Undetectable Humanizer receipt path");
        AddIfMissing(missing, HasCanonAuditReceipt(entry.SourcePacketPath, entry.ProviderManuscriptPath, entry.CanonAuditReceiptPath), "Chummer canon audit receipt path");
        AddIfMissing(missing, HasArchivedArtifact(entry.BookArtifactPath), "book artifact path");
        AddIfMissing(missing, HasArtifactReceipt(entry.BookArtifactPath, entry.BookArtifactReceiptPath, "book_artifact_import", null, ExternalProviderReceiptTokens()), "book artifact receipt path");
        AddIfMissing(missing, HasArchivedArtifact(entry.EbookArtifactPath), "ebook artifact path");
        AddIfMissing(missing, HasAudiobookshelfDossierImportReceipt(entry.EbookArtifactPath, entry.EbookAudiobookshelfImportReceiptPath), "Audiobookshelf dossier ebook import receipt path");
        AddIfMissing(missing, HasArchivedArtifact(entry.StorySceneCoverPath), "story scene cover artifact path");
        AddIfMissing(
            missing,
            HasArtifactReceipt(
                entry.StorySceneCoverPath,
                entry.StorySceneCoverReceiptPath,
                "selected_face_scene_render",
                null,
                RequiredStorySceneCoverTokens(entry)),
            "story scene cover receipt path");
        AddIfMissing(missing, HasCoverConsistencyReceipt(entry), "cover consistency receipt path");
        AddIfMissing(missing, HasArchivedArtifact(entry.AudiobookPath), "audiobook artifact path");
        AddIfMissing(missing, HasAudiobookshelfImportReceipt(entry.AudiobookPath, entry.AudiobookshelfImportReceiptPath), "Audiobookshelf import receipt path");
        AddIfMissing(missing, HasArchivedArtifact(entry.DossierVideoPath), "dossier video artifact path");
        AddIfMissing(missing, HasArtifactReceipt(entry.DossierVideoPath, entry.DossierVideoReceiptPath, "dossier_video_import", null, ExternalProviderReceiptTokens()), "dossier video receipt path");
        AddIfMissing(missing, entry.TelegramShareDelivered, "Telegram share delivery");
        AddIfMissing(
            missing,
            HasReceiptFile(
                entry.TelegramShareDeliveryReceiptPath,
                "telegram_share_delivery",
                "Telegram",
                RequiredTelegramDeliveryTokens(entry)),
            "Telegram share delivery receipt path");
        AddIfMissing(missing, !ContainsFakeMarker(entry), "no generated placeholder artifact markers");
        return missing
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Select(static item => item.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static void AddIfMissing(List<string> missing, bool condition, string requirement)
    {
        if (!condition)
        {
            missing.Add(requirement);
        }
    }

    private static bool IsPublishedForOwner(string? state)
        => Matches(state, "published_for_owner");

    private static bool IsChummerRunOwnerUrl(OriginDossierPublicationIndexEntry entry)
        => IsHttpUrl(entry.ChummerRunOwnerUrl)
            && Uri.TryCreate(entry.ChummerRunOwnerUrl, UriKind.Absolute, out Uri? uri)
            && uri.Host.Contains("chummer.run", StringComparison.OrdinalIgnoreCase)
            && string.Equals(uri.AbsolutePath, BuildOwnerPath(entry, null), StringComparison.OrdinalIgnoreCase);

    private static bool IsChummerRunArtifactUrl(
        OriginDossierPublicationIndexEntry entry,
        string? url,
        string artifactKind)
        => IsHttpUrl(url)
            && Uri.TryCreate(url, UriKind.Absolute, out Uri? uri)
            && uri.Host.Contains("chummer.run", StringComparison.OrdinalIgnoreCase)
            && string.Equals(uri.AbsolutePath, BuildOwnerPath(entry, artifactKind), StringComparison.OrdinalIgnoreCase);

    private static bool IsHttpUrl(string? url)
        => Uri.TryCreate(url, UriKind.Absolute, out Uri? uri)
            && (string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
                || string.Equals(uri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase));

    private static bool IsTrustedAudiobookshelfShareUrl(string? url)
        => Uri.TryCreate(url, UriKind.Absolute, out Uri? uri)
            && string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            && (string.Equals(uri.Host, "audio.chummer.run", StringComparison.OrdinalIgnoreCase)
                || string.Equals(uri.Host, "audiobookshelf.chummer.run", StringComparison.OrdinalIgnoreCase))
            && uri.AbsolutePath.Contains("/share/", StringComparison.OrdinalIgnoreCase);

    private static bool HasRealPath(string? path)
        => !string.IsNullOrWhiteSpace(path)
            && !HasFakeMarker(path);

    private static bool HasArchivedArtifact(string? path)
    {
        if (!HasRealPath(path))
        {
            return false;
        }

        try
        {
            var file = new FileInfo(path!);
            return file.Exists && file.Length > 0;
        }
        catch (ArgumentException)
        {
            return false;
        }
        catch (PathTooLongException)
        {
            return false;
        }
        catch (NotSupportedException)
        {
            return false;
        }
    }

    private static bool HasReceiptFile(
        string? path,
        string expectedOperation,
        string? expectedProviderToken = null,
        IReadOnlyList<string>? requiredTokens = null)
    {
        if (!HasArchivedArtifact(path))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(path!, Encoding.UTF8));
            return document.RootElement.ValueKind == JsonValueKind.Object
                && !ContainsFakeMarker(document.RootElement)
                && ReceiptHasExpectedOperation(document.RootElement, expectedOperation)
                && ReceiptHasExpectedProvider(document.RootElement, expectedProviderToken)
                && ReceiptHasVerifiedStatus(document.RootElement)
                && ReceiptHasCompletionTime(document.RootElement)
                && ReceiptContainsRequiredTokens(document.RootElement, requiredTokens);
        }
        catch (IOException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static bool HasArtifactReceipt(
        string? artifactPath,
        string? receiptPath,
        string expectedOperation,
        string? expectedProviderToken = null,
        IReadOnlyList<string>? requiredTokens = null)
    {
        string? artifactHash = TryComputeSha256(artifactPath);
        if (string.IsNullOrWhiteSpace(artifactHash))
        {
            return false;
        }

        List<string> tokens = new(requiredTokens ?? Array.Empty<string>())
        {
            artifactHash
        };
        return HasReceiptFile(receiptPath, expectedOperation, expectedProviderToken, tokens);
    }

    private static bool HasProviderManuscriptReceipt(string? artifactPath, string? receiptPath)
    {
        if (!HasArtifactReceipt(artifactPath, receiptPath, "provider_manuscript_import", null, ExternalProviderReceiptTokens()))
        {
            return false;
        }

        return ReceiptContainsAnyToken(receiptPath, ApprovedManuscriptProviderTokens);
    }

    private static bool HasSourcePacketReceipt(string? sourcePacketPath, string? receiptPath)
        => HasArtifactReceipt(
            sourcePacketPath,
            receiptPath,
            "origin_source_packet_approval",
            "Chummer",
            [ApprovedSourcePacketToken, ExternalProcessingConsentToken]);

    private static bool HasCanonAuditReceipt(string? sourcePacketPath, string? manuscriptPath, string? receiptPath)
    {
        string? sourcePacketHash = TryComputeSha256(sourcePacketPath);
        string? manuscriptHash = TryComputeSha256(manuscriptPath);
        if (string.IsNullOrWhiteSpace(sourcePacketHash) || string.IsNullOrWhiteSpace(manuscriptHash))
        {
            return false;
        }

        return HasReceiptFile(
            receiptPath,
            "chummer_canon_audit",
            "Chummer",
            [
                sourcePacketHash,
                manuscriptHash,
                CanonAuditPassedToken,
                HardConflictsZeroToken,
                PrivacyFindingsZeroToken
            ]);
    }

    private static bool HasAudiobookshelfImportReceipt(string? audiobookPath, string? receiptPath)
    {
        if (!HasArtifactReceipt(audiobookPath, receiptPath, "audiobookshelf_import", "Audiobookshelf", ExternalProviderReceiptTokens()))
        {
            return false;
        }

        return ReceiptContainsAnyToken(receiptPath, ApprovedAudiobookProviderTokens);
    }

    private static bool HasAudiobookshelfDossierImportReceipt(string? ebookPath, string? receiptPath)
        => HasArtifactReceipt(ebookPath, receiptPath, "audiobookshelf_dossier_import", "Audiobookshelf", ExternalProviderReceiptTokens());

    private static bool HasCoverConsistencyReceipt(OriginDossierPublicationIndexEntry entry)
    {
        string? coverHash = TryComputeSha256(entry.StorySceneCoverPath);
        if (string.IsNullOrWhiteSpace(coverHash))
        {
            return false;
        }

        return HasReceiptFile(
            entry.CoverConsistencyReceiptPath,
            "origin_edition_cover_consistency",
            "Chummer",
            [
                coverHash,
                BuildOriginEditionNamespace(entry),
                "ebook_cover_embedded",
                "m4b_cover_embedded",
                "movie_poster_matches_cover"
            ]);
    }

    private static bool ReceiptContainsAnyToken(string? receiptPath, IReadOnlyList<string> tokens)
    {
        if (!HasArchivedArtifact(receiptPath))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(receiptPath!, Encoding.UTF8));
            return ReceiptContainsAnyToken(document.RootElement, tokens);
        }
        catch (IOException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static string? TryComputeSha256(string? path)
    {
        if (!HasArchivedArtifact(path))
        {
            return null;
        }

        try
        {
            using FileStream stream = File.OpenRead(path!);
            return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
        catch (ArgumentException)
        {
            return null;
        }
        catch (NotSupportedException)
        {
            return null;
        }
    }

    private static bool ContainsFakeMarker(JsonElement element)
    {
        return element.ValueKind switch
        {
            JsonValueKind.String => HasFakeMarker(element.GetString()),
            JsonValueKind.Object => element.EnumerateObject().Any(property =>
                HasFakeMarker(property.Name) || ContainsFakeMarker(property.Value)),
            JsonValueKind.Array => element.EnumerateArray().Any(ContainsFakeMarker),
            _ => false
        };
    }

    private static bool ReceiptHasExpectedOperation(JsonElement root, string expectedOperation)
        => TryGetString(root, "operation", out string? operation)
            && string.Equals(operation, expectedOperation, StringComparison.OrdinalIgnoreCase);

    private static bool ReceiptHasExpectedProvider(JsonElement root, string? expectedProviderToken)
    {
        if (string.IsNullOrWhiteSpace(expectedProviderToken))
        {
            return true;
        }

        string token = expectedProviderToken;
        return TryGetString(root, "provider", out string? provider)
            && provider is not null
            && provider.Contains(token, StringComparison.OrdinalIgnoreCase);
    }

    private static bool ReceiptHasVerifiedStatus(JsonElement root)
        => !TryGetString(root, "status", out string? status)
            || string.Equals(status, "verified", StringComparison.OrdinalIgnoreCase)
            || string.Equals(status, "delivered", StringComparison.OrdinalIgnoreCase)
            || string.Equals(status, "ok", StringComparison.OrdinalIgnoreCase)
            || string.Equals(status, "success", StringComparison.OrdinalIgnoreCase);

    private static bool ReceiptHasCompletionTime(JsonElement root)
    {
        string[] fields = ["completedAtUtc", "completed_at_utc", "deliveredAtUtc", "delivered_at_utc", "createdAtUtc", "created_at_utc"];
        return fields.Any(field =>
            TryGetString(root, field, out string? value)
            && DateTimeOffset.TryParse(value, out _));
    }

    private static bool ReceiptContainsRequiredTokens(JsonElement root, IReadOnlyList<string>? requiredTokens)
        => requiredTokens is null
            || requiredTokens.Count == 0
            || requiredTokens
                .Where(static token => !string.IsNullOrWhiteSpace(token))
                .All(token => ReceiptContainsToken(root, token));

    private static bool ReceiptContainsToken(JsonElement element, string token)
    {
        return element.ValueKind switch
        {
            JsonValueKind.String => element.GetString()?.Contains(token, StringComparison.OrdinalIgnoreCase) == true,
            JsonValueKind.Object => element.EnumerateObject().Any(property =>
                property.Name.Contains(token, StringComparison.OrdinalIgnoreCase)
                || ReceiptContainsToken(property.Value, token)),
            JsonValueKind.Array => element.EnumerateArray().Any(item => ReceiptContainsToken(item, token)),
            _ => false
        };
    }

    private static bool ReceiptContainsAnyToken(JsonElement element, IReadOnlyList<string> tokens)
        => tokens
            .Where(static token => !string.IsNullOrWhiteSpace(token))
            .Any(token => ReceiptContainsToken(element, token));

    private static bool TryGetString(JsonElement root, string propertyName, out string? value)
    {
        value = null;
        if (!root.TryGetProperty(propertyName, out JsonElement property)
            || property.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        value = property.GetString();
        return !string.IsNullOrWhiteSpace(value);
    }

    private static bool ContainsFakeMarker(OriginDossierPublicationIndexEntry entry)
    {
        string?[] values =
        [
            entry.ChummerRunOwnerUrl,
            entry.BookArtifactUrl,
            entry.AudiobookshelfShareUrl,
            entry.DossierVideoUrl,
            entry.StorySceneCoverUrl,
            entry.SourcePacketPath,
            entry.SourcePacketReceiptPath,
            entry.CanonAuditReceiptPath,
            entry.ProviderManuscriptPath,
            entry.ProviderManuscriptReceiptPath,
            entry.HumanizerReceiptPath,
            entry.BookArtifactPath,
            entry.BookArtifactReceiptPath,
            entry.StorySceneCoverPath,
            entry.StorySceneCoverReceiptPath,
            entry.EbookArtifactPath,
            entry.EbookAudiobookshelfImportReceiptPath,
            entry.CoverConsistencyReceiptPath,
            entry.AudiobookPath,
            entry.AudiobookshelfImportReceiptPath,
            entry.DossierVideoPath,
            entry.DossierVideoReceiptPath,
            entry.MoviePosterPath,
            entry.MovieSubtitlesPath,
            entry.MovieStoryboardPath,
            entry.TelegramShareDeliveryReceiptPath
        ];

        return values.Any(HasFakeMarker);
    }

    private static bool HasFakeMarker(string? value)
        => !string.IsNullOrWhiteSpace(value)
            && (value.Contains("stub", StringComparison.OrdinalIgnoreCase)
                || value.Contains("fallback", StringComparison.OrdinalIgnoreCase));

    private static bool Matches(string? left, string right)
        => string.Equals(left?.Trim(), right.Trim(), StringComparison.OrdinalIgnoreCase);

    private static string Clean(string? value, string fallback)
        => string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();

    private static string? CleanNullable(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private OriginDossierPublicationIndexEntry BuildOwnedEntry(
        HubUserDto user,
        string subjectId,
        OriginDossierPublicationImportRequest request,
        string projectId)
    {
        string ownerUrl = BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, null);
        return new()
        {
            OwnerUserId = user.UserId,
            SubjectId = subjectId,
            OwnerSubjectId = subjectId,
            ProjectId = projectId,
            Title = Clean(request.Title, "Origin Dossier"),
            RunnerAlias = Clean(request.RunnerAlias, "Runner"),
            FamilyName = CleanNullable(request.FamilyName),
            GivenName = CleanNullable(request.GivenName),
            RunnerName = Clean(request.RunnerName, Clean(request.RunnerAlias, "Runner")),
            PublicationState = Clean(request.PublicationState, "awaiting_provider_manuscript"),
            OriginEditionNamespace = CleanNullable(request.OriginEditionNamespace)
                ?? BuildOriginEditionNamespace(
                    CleanNullable(request.FamilyName),
                    CleanNullable(request.GivenName),
                    Clean(request.RunnerName, Clean(request.RunnerAlias, "Runner"))),
            ChummerRunOwnerUrl = ownerUrl,
            BookArtifactUrl = BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, "book"),
            AudiobookshelfShareUrl = CleanNullable(request.AudiobookshelfShareUrl),
            AudiobookshelfDossierShareUrl = CleanNullable(request.AudiobookshelfDossierShareUrl),
            AudiobookshelfAudiobookShareUrl = CleanNullable(request.AudiobookshelfAudiobookShareUrl) ?? CleanNullable(request.AudiobookshelfShareUrl),
            DossierVideoUrl = BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, "video"),
            StorySceneCoverUrl = BuildOwnerUrl(ResolvePublicBaseUrl(), projectId, "cover"),
            ProviderAuthoredManuscriptImported = request.ProviderAuthoredManuscriptImported,
            UndetectableHumanizerApplied = request.UndetectableHumanizerApplied,
            BookArtifactVerified = request.BookArtifactVerified,
            DossierVideoVerified = request.DossierVideoVerified,
            StorySceneCoverUsesSelectedCharacterFace = request.StorySceneCoverUsesSelectedCharacterFace,
            AudiobookshelfPlaybackVerified = request.AudiobookshelfPlaybackVerified,
            TelegramShareDelivered = request.TelegramShareDelivered,
            RequiresAuthenticatedChummerRunUser = true,
            SourcePacketPath = CleanNullable(request.SourcePacketPath),
            SourcePacketReceiptPath = CleanNullable(request.SourcePacketReceiptPath),
            CanonAuditReceiptPath = CleanNullable(request.CanonAuditReceiptPath),
            ProviderManuscriptPath = CleanNullable(request.ProviderManuscriptPath),
            ProviderManuscriptReceiptPath = CleanNullable(request.ProviderManuscriptReceiptPath),
            HumanizerReceiptPath = CleanNullable(request.HumanizerReceiptPath),
            BookArtifactPath = CleanNullable(request.BookArtifactPath),
            BookArtifactReceiptPath = CleanNullable(request.BookArtifactReceiptPath),
            StorySceneCoverPath = CleanNullable(request.StorySceneCoverPath),
            StorySceneCoverReceiptPath = CleanNullable(request.StorySceneCoverReceiptPath),
            EbookArtifactPath = CleanNullable(request.EbookArtifactPath),
            EbookAudiobookshelfImportReceiptPath = CleanNullable(request.EbookAudiobookshelfImportReceiptPath),
            CoverConsistencyReceiptPath = CleanNullable(request.CoverConsistencyReceiptPath),
            AudiobookPath = CleanNullable(request.AudiobookPath),
            AudiobookshelfImportReceiptPath = CleanNullable(request.AudiobookshelfImportReceiptPath),
            DossierVideoPath = CleanNullable(request.DossierVideoPath),
            DossierVideoReceiptPath = CleanNullable(request.DossierVideoReceiptPath),
            MoviePosterPath = CleanNullable(request.MoviePosterPath),
            MovieSubtitlesPath = CleanNullable(request.MovieSubtitlesPath),
            MovieStoryboardPath = CleanNullable(request.MovieStoryboardPath),
            TelegramShareDeliveryReceiptPath = CleanNullable(request.TelegramShareDeliveryReceiptPath),
            MissingGoldRequirements = request.MissingGoldRequirements ?? Array.Empty<string>()
        };
    }

    private static string BuildOwnerUrl(string publicBaseUrl, string projectId, string? artifactKind)
        => $"{publicBaseUrl}{BuildOwnerPath(projectId, artifactKind)}";

    private static string BuildOwnerPath(OriginDossierPublicationIndexEntry entry, string? artifactKind)
        => BuildOwnerPath(Clean(entry.ProjectId, "origin-dossier"), artifactKind);

    private static IReadOnlyList<string> RequiredTelegramDeliveryTokens(OriginDossierPublicationIndexEntry entry)
        =>
        [
            BuildOwnerPath(entry, null),
            BuildOwnerPath(entry, "read"),
            BuildOwnerPath(entry, "listen"),
            BuildOwnerPath(entry, "watch"),
            BuildOriginEditionNamespace(entry),
            OperatorVerifiedLiveRunToken,
            ProviderReceiptReferenceToken
        ];

    private static IReadOnlyList<string> RequiredStorySceneCoverTokens(OriginDossierPublicationIndexEntry entry)
        =>
        [
            BuildOwnerPath(entry, null),
            BuildOwnerPath(entry, "cover"),
            BuildOriginEditionNamespace(entry),
            SelectedCharacterFaceProofToken,
            OperatorVerifiedLiveRunToken,
            ProviderReceiptReferenceToken
        ];

    private static IReadOnlyList<string> ExternalProviderReceiptTokens()
        =>
        [
            OperatorVerifiedLiveRunToken,
            ProviderReceiptReferenceToken
        ];

    private static string BuildOwnerPath(string projectId, string? artifactKind)
    {
        string path = $"/account/work/origin-dossiers/{Uri.EscapeDataString(projectId)}";
        return string.IsNullOrWhiteSpace(artifactKind)
            ? path
            : $"{path}/{Uri.EscapeDataString(artifactKind.Trim().ToLowerInvariant())}";
    }

    private static bool HasOriginEditionNamespace(OriginDossierPublicationIndexEntry entry)
    {
        string value = Clean(entry.OriginEditionNamespace, BuildOriginEditionNamespace(entry));
        return value.StartsWith("origin.chummer.run/", StringComparison.OrdinalIgnoreCase)
            && value.Split('/', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Length >= 4;
    }

    private static string BuildOriginEditionNamespace(OriginDossierPublicationIndexEntry entry)
        => BuildOriginEditionNamespace(entry.FamilyName, entry.GivenName, entry.RunnerName ?? entry.RunnerAlias);

    private static string BuildOriginEditionNamespace(string? familyName, string? givenName, string? runnerName)
        => $"origin.chummer.run/{NamespaceSegment(familyName, "Family")}/{NamespaceSegment(givenName, "Given")}/{NamespaceSegment(runnerName, "Runner")}";

    private static string NamespaceSegment(string? value, string fallback)
    {
        string clean = Clean(value, fallback);
        Span<char> buffer = stackalloc char[clean.Length];
        int written = 0;
        foreach (char c in clean)
        {
            if (char.IsLetterOrDigit(c))
            {
                buffer[written++] = c;
            }
            else if ((c is '-' or '_' || char.IsWhiteSpace(c)) && written > 0 && buffer[written - 1] != '-')
            {
                buffer[written++] = '-';
            }
        }

        string segment = new string(buffer[..written]).Trim('-');
        return string.IsNullOrWhiteSpace(segment) ? fallback : segment;
    }

    private static string ResolveContentType(string path, string artifactKind)
        => artifactKind.Trim().ToLowerInvariant() switch
        {
            "cover" when path.EndsWith(".jpg", StringComparison.OrdinalIgnoreCase)
                || path.EndsWith(".jpeg", StringComparison.OrdinalIgnoreCase) => "image/jpeg",
            "cover" when path.EndsWith(".webp", StringComparison.OrdinalIgnoreCase) => "image/webp",
            "cover" => "image/png",
            "video" when path.EndsWith(".webm", StringComparison.OrdinalIgnoreCase) => "video/webm",
            "video" => "video/mp4",
            "book" when path.EndsWith(".epub", StringComparison.OrdinalIgnoreCase) => "application/epub+zip",
            "book" when path.EndsWith(".docx", StringComparison.OrdinalIgnoreCase) => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "book" when path.EndsWith(".md", StringComparison.OrdinalIgnoreCase) => "text/markdown; charset=utf-8",
            "book" => "application/pdf",
            _ => "application/octet-stream"
        };
}

public sealed record OriginDossierPublicationArtifact(
    string Path,
    string ContentType);

internal sealed record OriginDossierPublicationIndexSnapshot(
    IReadOnlyList<OriginDossierPublicationIndexEntry>? Publications);

internal sealed class OriginDossierPublicationIndexEntry
{
    public string? OwnerUserId { get; init; }
    public string? SubjectId { get; init; }
    public string? OwnerSubjectId { get; init; }
    public string? ProjectId { get; init; }
    public string? Title { get; init; }
    public string? RunnerAlias { get; init; }
    public string? PublicationState { get; init; }
    public string? FamilyName { get; init; }
    public string? GivenName { get; init; }
    public string? RunnerName { get; init; }
    public string? OriginEditionNamespace { get; init; }
    public string? ChummerRunOwnerUrl { get; init; }
    public string? BookArtifactUrl { get; init; }
    public string? AudiobookshelfShareUrl { get; init; }
    public string? AudiobookshelfDossierShareUrl { get; init; }
    public string? AudiobookshelfAudiobookShareUrl { get; init; }
    public string? DossierVideoUrl { get; init; }
    public string? StorySceneCoverUrl { get; init; }
    public string? SourcePacketPath { get; init; }
    public string? SourcePacketReceiptPath { get; init; }
    public string? CanonAuditReceiptPath { get; init; }
    public bool ProviderAuthoredManuscriptImported { get; init; }
    public bool UndetectableHumanizerApplied { get; init; }
    public bool BookArtifactVerified { get; init; }
    public bool DossierVideoVerified { get; init; }
    public bool StorySceneCoverUsesSelectedCharacterFace { get; init; }
    public bool AudiobookshelfPlaybackVerified { get; init; }
    public bool TelegramShareDelivered { get; init; }
    public bool RequiresAuthenticatedChummerRunUser { get; init; } = true;
    public string? ProviderManuscriptPath { get; init; }
    public string? ProviderManuscriptReceiptPath { get; init; }
    public string? HumanizerReceiptPath { get; init; }
    public string? BookArtifactPath { get; init; }
    public string? BookArtifactReceiptPath { get; init; }
    public string? StorySceneCoverPath { get; init; }
    public string? StorySceneCoverReceiptPath { get; init; }
    public string? EbookArtifactPath { get; init; }
    public string? EbookAudiobookshelfImportReceiptPath { get; init; }
    public string? CoverConsistencyReceiptPath { get; init; }
    public string? AudiobookPath { get; init; }
    public string? AudiobookshelfImportReceiptPath { get; init; }
    public string? DossierVideoPath { get; init; }
    public string? DossierVideoReceiptPath { get; init; }
    public string? MoviePosterPath { get; init; }
    public string? MovieSubtitlesPath { get; init; }
    public string? MovieStoryboardPath { get; init; }
    public string? TelegramShareDeliveryReceiptPath { get; init; }
    public IReadOnlyList<string>? MissingGoldRequirements { get; init; }
}
