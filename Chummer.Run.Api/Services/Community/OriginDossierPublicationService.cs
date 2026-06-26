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
    private static readonly IReadOnlyList<string> DefaultApprovedManuscriptProviderTokens = ["Inkfluence", "Youbooks", "First Book", "FirstBook", "Chummer OriginBookEngine"];
    private static readonly IReadOnlyList<string> DefaultApprovedAudiobookProviderTokens = ["Inkfluence", "Unmixr"];
    private static readonly IReadOnlyList<string> DefaultTrustedAudiobookshelfHosts = ["audio.chummer.run", "audiobookshelf.chummer.run", "audiobookshelf.girschele.com"];
    private const string SelectedCharacterFaceProofToken = "selected_character_face";
    private const string ApprovedSourcePacketToken = "approved_source_packet";
    private const string ExternalProcessingConsentToken = "external_processing_consent";
    private const string CanonAuditPassedToken = "canon_audit_passed";
    private const string HardConflictsZeroToken = "hard_conflicts:0";
    private const string PrivacyFindingsZeroToken = "privacy_findings:0";
    private const string OperatorVerifiedLiveRunToken = "operator_verified_live_run";
    private const string ProviderReceiptReferenceToken = "provider_receipt_reference";
    private readonly IConfiguration _configuration;
    private readonly HorizonCapabilityService? _capabilities;
    private readonly ILogger<OriginDossierPublicationService> _logger;

    public OriginDossierPublicationService(
        IConfiguration configuration,
        HorizonCapabilityService? capabilities,
        ILogger<OriginDossierPublicationService> logger)
    {
        _configuration = configuration;
        _capabilities = capabilities;
        _logger = logger;
    }

    public OriginDossierPublicationService(
        IConfiguration configuration,
        ILogger<OriginDossierPublicationService> logger)
        : this(configuration, null, logger)
    {
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
                : null,
            SharedArtifacts: BuildSharedArtifacts(),
            ArtifactCapability: BuildPublicArtifactCapability(projectId));
    }

    private SharedArtifactSurfaceRoutesViewModel? BuildSharedArtifacts()
        => _capabilities?.BuildSharedArtifactSurfaceRoutesViewModel("origin-dossier", "dossier_media");

    private PublicHorizonCapabilityViewModel? BuildPublicArtifactCapability(string projectId)
    {
        if (_capabilities is null)
        {
            return null;
        }

        return _capabilities.BuildPublicCapabilityViewModel(
            "origin-dossier",
            "dossier_media",
            $"origin-dossier:{projectId}:media",
            visibility: "private") with
        {
            PublicVisible = true
        };
    }

    private IReadOnlyList<string> ResolveMissingRequirements(OriginDossierPublicationIndexEntry entry)
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
        AddIfMissing(missing, HasProviderAccountAliasReceipt(entry.ProviderManuscriptAccountAlias, entry.ProviderManuscriptReceiptPath, "CHUMMER_ORIGIN_MANUSCRIPT_ACCOUNT_ALIASES", "OriginDossier:ManuscriptAccountAliases"), "provider manuscript account alias");
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
        AddIfMissing(missing, HasAudiobookshelfDossierImportReceipt(entry), "Audiobookshelf dossier ebook import receipt path");
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
        AddIfMissing(missing, HasAudiobookshelfImportReceipt(entry), "Audiobookshelf import receipt path");
        AddIfMissing(missing, HasProviderAccountAliasReceipt(entry.AudiobookProviderAccountAlias, entry.AudiobookshelfImportReceiptPath, "CHUMMER_ORIGIN_AUDIO_ACCOUNT_ALIASES", "OriginDossier:AudioAccountAliases"), "audiobook provider account alias");
        AddIfMissing(missing, HasArchivedArtifact(entry.DossierVideoPath), "dossier video artifact path");
        AddIfMissing(missing, HasArchivedArtifact(entry.MoviePosterPath), "movie poster artifact path");
        AddIfMissing(missing, HasArtifactReceipt(entry.DossierVideoPath, entry.DossierVideoReceiptPath, "dossier_video_import", null, ExternalProviderReceiptTokens()), "dossier video receipt path");
        AddIfMissing(missing, entry.TelegramShareDelivered, "Telegram share delivery");
        AddIfMissing(
            missing,
            HasTelegramShareDeliveryReceipt(entry),
            "Telegram share delivery receipt path");
        AddIfMissing(missing, HasFinalNoFallbackNoSentinelReceipt(entry), "final no-fallback/no-sentinel audit receipt path");
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
            && IsTrustedChummerHost(uri)
            && string.Equals(uri.AbsolutePath, BuildOwnerPath(entry, null), StringComparison.OrdinalIgnoreCase);

    private static bool IsChummerRunArtifactUrl(
        OriginDossierPublicationIndexEntry entry,
        string? url,
        string artifactKind)
        => IsHttpUrl(url)
            && Uri.TryCreate(url, UriKind.Absolute, out Uri? uri)
            && IsTrustedChummerHost(uri)
            && string.Equals(uri.AbsolutePath, BuildOwnerPath(entry, artifactKind), StringComparison.OrdinalIgnoreCase);

    private static bool IsHttpUrl(string? url)
        => Uri.TryCreate(url, UriKind.Absolute, out Uri? uri)
            && ((string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
                    && IsTrustedChummerHost(uri))
                || (string.Equals(uri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
                    && uri.IsLoopback));

    private static bool IsTrustedChummerHost(Uri uri)
    {
        if (uri.IsLoopback)
        {
            return true;
        }

        string host = uri.Host.TrimEnd('.');
        return string.Equals(host, "chummer.run", StringComparison.OrdinalIgnoreCase)
            || host.EndsWith(".chummer.run", StringComparison.OrdinalIgnoreCase);
    }

    private bool IsTrustedAudiobookshelfShareUrl(string? url)
        => Uri.TryCreate(url, UriKind.Absolute, out Uri? uri)
            && string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            && ResolveTrustedAudiobookshelfHosts().Contains(uri.Host, StringComparer.OrdinalIgnoreCase)
            && (uri.AbsolutePath.StartsWith("/share/", StringComparison.OrdinalIgnoreCase)
                || uri.AbsolutePath.StartsWith("/audiobookshelf/share/", StringComparison.OrdinalIgnoreCase));

    private IReadOnlySet<string> ResolveTrustedAudiobookshelfHosts()
    {
        IReadOnlyList<string> configuredHosts = OriginDossierProviderAccountRegistry.ResolveHosts(
            _configuration,
            "CHUMMER_ORIGIN_AUDIOBOOKSHELF_TRUSTED_HOSTS",
            "OriginDossier:AudiobookshelfTrustedHosts",
            "audiobookshelf");
        IEnumerable<string> hosts = configuredHosts.Count > 0
            ? configuredHosts
            : OriginDossierProviderAccountRegistry.HasConfiguredHostSource(
                _configuration,
                "CHUMMER_ORIGIN_AUDIOBOOKSHELF_TRUSTED_HOSTS",
                "OriginDossier:AudiobookshelfTrustedHosts",
                "audiobookshelf")
                ? Array.Empty<string>()
                : DefaultTrustedAudiobookshelfHosts;
        return hosts
            .Select(static host => host.Trim().ToLowerInvariant())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
    }

    private IReadOnlyList<string> ResolveApprovedProviderTokens(
        string envKey,
        string configKey,
        IReadOnlyList<string> defaultTokens)
    {
        string? configured = _configuration[envKey] ?? _configuration[configKey];
        if (string.IsNullOrWhiteSpace(configured))
        {
            return defaultTokens;
        }

        string[] tokens = configured
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(static token => !string.IsNullOrWhiteSpace(token))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        return tokens.Length == 0 ? defaultTokens : tokens;
    }

    private IReadOnlyList<string> ResolveConfiguredProviderAccountAliases(string envKey, string configKey)
        => OriginDossierProviderAccountRegistry.ResolveAliases(
            _configuration,
            envKey,
            configKey,
            ProviderAccountRegistryRole(envKey));

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

    private bool HasProviderManuscriptReceipt(string? artifactPath, string? receiptPath)
    {
        if (!HasArtifactReceipt(artifactPath, receiptPath, "provider_manuscript_import", null, ExternalProviderReceiptTokens()))
        {
            return false;
        }

        return ReceiptProviderMatchesAnyToken(receiptPath, ResolveApprovedProviderTokens("CHUMMER_ORIGIN_MANUSCRIPT_PROVIDER_TOKENS", "OriginDossier:ManuscriptProviderTokens", DefaultApprovedManuscriptProviderTokens));
    }

    private bool HasProviderAccountAliasReceipt(string? accountAlias, string? receiptPath, string envKey, string configKey)
    {
        IReadOnlyList<string> configuredAliases = ResolveConfiguredProviderAccountAliases(envKey, configKey);
        if (configuredAliases.Count == 0)
        {
            return !OriginDossierProviderAccountRegistry.HasConfiguredAliasSource(_configuration, envKey, configKey, ProviderAccountRegistryRole(envKey));
        }

        string? cleanAlias = CleanNullable(accountAlias);
        return cleanAlias is not null
            && configuredAliases.Any(alias => Matches(alias, cleanAlias))
            && ReceiptContainsAccountAlias(receiptPath, cleanAlias);
    }

    private static string ProviderAccountRegistryRole(string envKey)
        => envKey.Contains("AUDIO", StringComparison.OrdinalIgnoreCase) ? "audio" : "manuscript";

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

    private bool HasAudiobookshelfImportReceipt(OriginDossierPublicationIndexEntry entry)
    {
        if (!HasArtifactReceipt(entry.AudiobookPath, entry.AudiobookshelfImportReceiptPath, "audiobookshelf_import", "Audiobookshelf", ExternalProviderReceiptTokens()))
        {
            return false;
        }

        return ReceiptContainsAnyToken(entry.AudiobookshelfImportReceiptPath, ResolveApprovedProviderTokens("CHUMMER_ORIGIN_AUDIO_PROVIDER_TOKENS", "OriginDossier:AudioProviderTokens", DefaultApprovedAudiobookProviderTokens))
            && ReceiptContainsOriginTaxonomy(entry.AudiobookshelfImportReceiptPath, BuildOriginEditionNamespace(entry), "audiobook");
    }

    private static bool HasAudiobookshelfDossierImportReceipt(OriginDossierPublicationIndexEntry entry)
        => HasArtifactReceipt(entry.EbookArtifactPath, entry.EbookAudiobookshelfImportReceiptPath, "audiobookshelf_dossier_import", "Audiobookshelf", ExternalProviderReceiptTokens())
            && ReceiptContainsOriginTaxonomy(entry.EbookAudiobookshelfImportReceiptPath, BuildOriginEditionNamespace(entry), "dossier");

    private static bool HasCoverConsistencyReceipt(OriginDossierPublicationIndexEntry entry)
    {
        string? coverHash = TryComputeSha256(entry.StorySceneCoverPath);
        if (string.IsNullOrWhiteSpace(coverHash))
        {
            return false;
        }

        if (!HasArchivedArtifact(entry.CoverConsistencyReceiptPath))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(entry.CoverConsistencyReceiptPath!, Encoding.UTF8));
            JsonElement root = document.RootElement;
            return root.ValueKind == JsonValueKind.Object
                && !ContainsFakeMarker(root)
                && ReceiptHasExpectedOperation(root, "origin_edition_cover_consistency")
                && ReceiptHasExpectedProvider(root, "Chummer")
                && TryGetString(root, "status", out string? status)
                && string.Equals(status, "pass", StringComparison.OrdinalIgnoreCase)
                && TryGetString(root, "expectedCoverSha256", out string? expectedCoverHash)
                && string.Equals(expectedCoverHash, coverHash, StringComparison.OrdinalIgnoreCase)
                && TryGetString(root, "namespace", out string? namespaceValue)
                && string.Equals(namespaceValue, BuildOriginEditionNamespace(entry), StringComparison.OrdinalIgnoreCase)
                && TryGetBoolean(root, "goldEligible", out bool goldEligible)
                && goldEligible
                && ReceiptArrayIsEmpty(root, "blockedSurfaces")
                && ReceiptHasCompletionTime(root)
                && ReceiptSurfacePassed(root, "chummer_hero_cover")
                && ReceiptSurfacePassed(root, "dossier_cover_asset")
                && ReceiptSurfacePassed(root, "ebook_embedded_cover")
                && ReceiptSurfacePassed(root, "pdf_cover_embedding")
                && ReceiptSurfacePassed(root, "audiobook_cover_asset")
                && ReceiptSurfacePassed(root, "m4b_cover_embedding")
                && ReceiptSurfacePassed(root, "audiobookshelf_dossier_cover")
                && ReceiptSurfacePassed(root, "audiobookshelf_audiobook_cover")
                && ReceiptSurfacePassed(root, "movie_poster");
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

    private static bool HasFinalNoFallbackNoSentinelReceipt(OriginDossierPublicationIndexEntry entry)
    {
        if (!HasArchivedArtifact(entry.FinalNoFallbackNoSentinelAuditReceiptPath))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(entry.FinalNoFallbackNoSentinelAuditReceiptPath!, Encoding.UTF8));
            JsonElement root = document.RootElement;
            return root.ValueKind == JsonValueKind.Object
                && !ContainsFakeMarker(root)
                && TryGetString(root, "contractName", out string? contractName)
                && string.Equals(contractName, "chummer.origin_edition.final_no_fallback_bundle_audit.v1", StringComparison.OrdinalIgnoreCase)
                && ReceiptHasExpectedOperation(root, "origin_edition_final_no_fallback_bundle_audit")
                && ReceiptHasExpectedProvider(root, "Chummer")
                && TryGetString(root, "status", out string? status)
                && string.Equals(status, "pass", StringComparison.OrdinalIgnoreCase)
                && TryGetString(root, "namespace", out string? namespaceValue)
                && string.Equals(namespaceValue, BuildOriginEditionNamespace(entry), StringComparison.OrdinalIgnoreCase)
                && TryGetBoolean(root, "goldEligible", out bool goldEligible)
                && goldEligible
                && ReceiptArrayIsEmpty(root, "blockedSurfaces")
                && ReceiptHasCompletionTime(root)
                && ReceiptSurfacePassed(root, "approved_canon_packet")
                && ReceiptSurfacePassed(root, "provider_manuscript")
                && ReceiptSurfacePassed(root, "humanizer_receipt")
                && ReceiptSurfacePassed(root, "humanizer_quality_receipt")
                && ReceiptSurfacePassed(root, "cover")
                && ReceiptSurfacePassed(root, "ebook")
                && ReceiptSurfacePassed(root, "pdf")
                && ReceiptSurfacePassed(root, "pdf_cover_receipt")
                && ReceiptSurfacePassed(root, "dossier_audiobookshelf_receipt")
                && ReceiptSurfacePassed(root, "m4b_provider_gate")
                && ReceiptSurfacePassed(root, "cover_consistency")
                && ReceiptSurfacePassed(root, "movie")
                && ReceiptSurfacePassed(root, "movie_receipt")
                && ReceiptSurfacePassed(root, "real_m4b_artifact")
                && ReceiptSurfacePassed(root, "audiobookshelf_audiobook_receipt");
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

    private bool HasTelegramShareDeliveryReceipt(OriginDossierPublicationIndexEntry entry)
    {
        if (!HasReceiptFile(
                entry.TelegramShareDeliveryReceiptPath,
                "telegram_share_delivery",
                "Telegram",
                RequiredTelegramDeliveryTokens(entry)))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(entry.TelegramShareDeliveryReceiptPath!, Encoding.UTF8));
            JsonElement root = document.RootElement;
            return root.ValueKind == JsonValueKind.Object
                && ReceiptHasEaTelegramAdapterProof(root, entry)
                && TelegramDeliveryAliasAllowed(entry.TelegramShareDeliveryReceiptPath);
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

    private bool TelegramDeliveryAliasAllowed(string? receiptPath)
    {
        IReadOnlyList<string> configuredAliases = OriginDossierProviderAccountRegistry.ResolveAliases(
            _configuration,
            "CHUMMER_ORIGIN_TELEGRAM_ACCOUNT_ALIASES",
            "OriginDossier:TelegramAccountAliases",
            "telegram");
        if (configuredAliases.Count == 0)
        {
            return !OriginDossierProviderAccountRegistry.HasConfiguredAliasSource(
                _configuration,
                "CHUMMER_ORIGIN_TELEGRAM_ACCOUNT_ALIASES",
                "OriginDossier:TelegramAccountAliases",
                "telegram");
        }

        return configuredAliases.Any(alias => ReceiptContainsAccountAlias(receiptPath, alias));
    }

    private static bool ReceiptHasEaTelegramAdapterProof(JsonElement root, OriginDossierPublicationIndexEntry entry)
    {
        string projectId = Clean(entry.ProjectId, "origin-dossier");
        string originNamespace = BuildOriginEditionNamespace(entry);
        JsonElement linkBundle = ResolveTelegramLinkBundle(root);
        return ReceiptHasEaTelegramContract(root)
            && TryGetString(root, "adapter", out string? adapter)
            && string.Equals(adapter, "ExecutiveAssistantChannelMessagingService", StringComparison.OrdinalIgnoreCase)
            && TryGetBoolean(root, "telegramMessageIdHashedByEa", out bool messageIdHashed)
            && messageIdHashed
            && TryGetBoolean(root, "rawTelegramChatIdIncluded", out bool rawChatIncluded)
            && !rawChatIncluded
            && TryGetString(linkBundle, "project_id", out string? bundleProjectId)
            && string.Equals(bundleProjectId, projectId, StringComparison.OrdinalIgnoreCase)
            && TryGetString(linkBundle, "origin_namespace_sha256", out string? namespaceHash)
            && string.Equals(namespaceHash, Sha256Text(originNamespace), StringComparison.OrdinalIgnoreCase)
            && TryGetString(linkBundle, "open_in_chummer_url_sha256", out string? ownerHash)
            && string.Equals(ownerHash, Sha256Text(BuildOwnerPath(entry, null)), StringComparison.OrdinalIgnoreCase)
            && TryGetString(linkBundle, "read_url_sha256", out string? readHash)
            && string.Equals(readHash, Sha256Text(BuildOwnerPath(entry, "read")), StringComparison.OrdinalIgnoreCase)
            && TryGetString(linkBundle, "listen_url_sha256", out string? listenHash)
            && string.Equals(listenHash, Sha256Text(BuildOwnerPath(entry, "listen")), StringComparison.OrdinalIgnoreCase)
            && TryGetString(linkBundle, "watch_url_sha256", out string? watchHash)
            && string.Equals(watchHash, Sha256Text(BuildOwnerPath(entry, "watch")), StringComparison.OrdinalIgnoreCase)
            && TryGetBoolean(linkBundle, "all_required_links_present", out bool allRequiredLinksPresent)
            && allRequiredLinksPresent
            && TryGetBoolean(linkBundle, "raw_urls_exposed", out bool rawUrlsExposed)
            && !rawUrlsExposed
            && TryGetString(linkBundle, "telegram_delivery_status", out string? deliveryStatus)
            && string.Equals(deliveryStatus, "sent", StringComparison.OrdinalIgnoreCase)
            && TryGetBoolean(linkBundle, "telegram_message_id_present", out bool messagePresent)
            && messagePresent;
    }

    private static bool ReceiptHasEaTelegramContract(JsonElement root)
        => (TryGetString(root, "contractName", out string? contractName)
                && string.Equals(contractName, "ea.telegram_audiobook_live_delivery_receipt.v1", StringComparison.OrdinalIgnoreCase))
            || (TryGetString(root, "contract_name", out string? snakeContractName)
                && string.Equals(snakeContractName, "ea.telegram_audiobook_live_delivery_receipt.v1", StringComparison.OrdinalIgnoreCase));

    private static JsonElement ResolveTelegramLinkBundle(JsonElement root)
    {
        if (root.TryGetProperty("selected_delivery", out JsonElement selected)
            && selected.ValueKind == JsonValueKind.Object
            && selected.TryGetProperty("origin_edition_link_bundle", out JsonElement selectedBundle)
            && selectedBundle.ValueKind == JsonValueKind.Object)
        {
            return selectedBundle;
        }

        if (root.TryGetProperty("origin_edition_link_bundle", out JsonElement bundle)
            && bundle.ValueKind == JsonValueKind.Object)
        {
            return bundle;
        }

        if (root.TryGetProperty("linkBundle", out JsonElement camelBundle)
            && camelBundle.ValueKind == JsonValueKind.Object)
        {
            return camelBundle;
        }

        return root;
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

    private static bool ReceiptContainsToken(string? receiptPath, string token)
    {
        if (!HasArchivedArtifact(receiptPath) || string.IsNullOrWhiteSpace(token))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(receiptPath!, Encoding.UTF8));
            return ReceiptContainsToken(document.RootElement, token);
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

    private static bool ReceiptContainsAccountAlias(string? receiptPath, string accountAlias)
    {
        if (!HasArchivedArtifact(receiptPath) || string.IsNullOrWhiteSpace(accountAlias))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(receiptPath!, Encoding.UTF8));
            return ReceiptContainsAccountAlias(document.RootElement, accountAlias.Trim());
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

    private static bool ReceiptContainsAccountAlias(JsonElement element, string accountAlias)
    {
        return element.ValueKind switch
        {
            JsonValueKind.String => StringIsAccountAliasToken(element.GetString(), accountAlias),
            JsonValueKind.Object => element.EnumerateObject().Any(property =>
                (PropertyIsAccountAlias(property.Name) && StringIsExact(property.Value, accountAlias))
                || ReceiptContainsAccountAlias(property.Value, accountAlias)),
            JsonValueKind.Array => element.EnumerateArray().Any(item => ReceiptContainsAccountAlias(item, accountAlias)),
            _ => false
        };
    }

    private static bool PropertyIsAccountAlias(string propertyName)
        => string.Equals(propertyName, "accountAlias", StringComparison.OrdinalIgnoreCase)
            || string.Equals(propertyName, "account_alias", StringComparison.OrdinalIgnoreCase)
            || string.Equals(propertyName, "assignedAccountAlias", StringComparison.OrdinalIgnoreCase)
            || string.Equals(propertyName, "providerAccountAlias", StringComparison.OrdinalIgnoreCase);

    private static bool StringIsExact(JsonElement element, string expected)
        => element.ValueKind == JsonValueKind.String
            && string.Equals(element.GetString()?.Trim(), expected, StringComparison.OrdinalIgnoreCase);

    private static bool StringIsAccountAliasToken(string? value, string accountAlias)
    {
        string text = value?.Trim() ?? string.Empty;
        return string.Equals(text, accountAlias, StringComparison.OrdinalIgnoreCase)
            || string.Equals(text, $"accountAlias: {accountAlias}", StringComparison.OrdinalIgnoreCase)
            || string.Equals(text, $"account_alias: {accountAlias}", StringComparison.OrdinalIgnoreCase)
            || string.Equals(text, $"assignedAccountAlias: {accountAlias}", StringComparison.OrdinalIgnoreCase)
            || string.Equals(text, $"providerAccountAlias: {accountAlias}", StringComparison.OrdinalIgnoreCase);
    }

    private static bool ReceiptContainsOriginTaxonomy(string? receiptPath, string originNamespace, string shelfKind)
    {
        if (!HasArchivedArtifact(receiptPath) || string.IsNullOrWhiteSpace(originNamespace) || string.IsNullOrWhiteSpace(shelfKind))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(receiptPath!, Encoding.UTF8));
            string taxonomy = $"{originNamespace.Trim().TrimEnd('/')}/{shelfKind.Trim().Trim('/')}";
            return ReceiptContainsExactNamespace(document.RootElement, originNamespace.Trim())
                && ReceiptContainsExactTaxonomy(document.RootElement, taxonomy);
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

    private static bool ReceiptContainsExactNamespace(JsonElement element, string originNamespace)
    {
        return element.ValueKind switch
        {
            JsonValueKind.String => string.Equals(element.GetString()?.Trim(), originNamespace, StringComparison.OrdinalIgnoreCase)
                || string.Equals(element.GetString()?.Trim(), $"originEditionNamespace: {originNamespace}", StringComparison.OrdinalIgnoreCase),
            JsonValueKind.Object => element.EnumerateObject().Any(property =>
                (PropertyIsOriginNamespace(property.Name) && StringIsExact(property.Value, originNamespace))
                || ReceiptContainsExactNamespace(property.Value, originNamespace)),
            JsonValueKind.Array => element.EnumerateArray().Any(item => ReceiptContainsExactNamespace(item, originNamespace)),
            _ => false
        };
    }

    private static bool ReceiptContainsExactTaxonomy(JsonElement element, string taxonomy)
    {
        return element.ValueKind switch
        {
            JsonValueKind.String => string.Equals(element.GetString()?.Trim(), taxonomy, StringComparison.OrdinalIgnoreCase)
                || string.Equals(element.GetString()?.Trim(), $"originTaxonomy: {taxonomy}", StringComparison.OrdinalIgnoreCase)
                || string.Equals(element.GetString()?.Trim(), $"libraryPath: {taxonomy}", StringComparison.OrdinalIgnoreCase),
            JsonValueKind.Object => element.EnumerateObject().Any(property =>
                (PropertyIsOriginTaxonomy(property.Name) && StringIsExact(property.Value, taxonomy))
                || ReceiptContainsExactTaxonomy(property.Value, taxonomy)),
            JsonValueKind.Array => element.EnumerateArray().Any(item => ReceiptContainsExactTaxonomy(item, taxonomy)),
            _ => false
        };
    }

    private static bool PropertyIsOriginNamespace(string propertyName)
        => string.Equals(propertyName, "originEditionNamespace", StringComparison.OrdinalIgnoreCase)
            || string.Equals(propertyName, "origin_edition_namespace", StringComparison.OrdinalIgnoreCase)
            || string.Equals(propertyName, "namespace", StringComparison.OrdinalIgnoreCase);

    private static bool PropertyIsOriginTaxonomy(string propertyName)
        => string.Equals(propertyName, "originTaxonomy", StringComparison.OrdinalIgnoreCase)
            || string.Equals(propertyName, "origin_taxonomy", StringComparison.OrdinalIgnoreCase)
            || string.Equals(propertyName, "libraryPath", StringComparison.OrdinalIgnoreCase)
            || string.Equals(propertyName, "library_path", StringComparison.OrdinalIgnoreCase)
            || string.Equals(propertyName, "relativePath", StringComparison.OrdinalIgnoreCase)
            || string.Equals(propertyName, "relative_path", StringComparison.OrdinalIgnoreCase);

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
            && ContainsTokenWithBoundary(provider, token);
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
            .Any(token => ReceiptContainsProviderToken(element, token));

    private static bool ReceiptProviderMatchesAnyToken(string? receiptPath, IReadOnlyList<string> tokens)
    {
        if (!HasArchivedArtifact(receiptPath))
        {
            return false;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(receiptPath!, Encoding.UTF8));
            return TryGetString(document.RootElement, "provider", out string? provider)
                && provider is not null
                && tokens
                    .Where(static token => !string.IsNullOrWhiteSpace(token))
                    .Any(token => ContainsTokenWithBoundary(provider, token));
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

    private static bool ReceiptContainsProviderToken(JsonElement element, string token)
    {
        return element.ValueKind switch
        {
            JsonValueKind.String => ContainsTokenWithBoundary(element.GetString(), token),
            JsonValueKind.Object => element.EnumerateObject().Any(property =>
                ContainsTokenWithBoundary(property.Name, token)
                || ReceiptContainsProviderToken(property.Value, token)),
            JsonValueKind.Array => element.EnumerateArray().Any(item => ReceiptContainsProviderToken(item, token)),
            _ => false
        };
    }

    private static bool ContainsTokenWithBoundary(string? value, string token)
    {
        if (string.IsNullOrWhiteSpace(value) || string.IsNullOrWhiteSpace(token))
        {
            return false;
        }

        ReadOnlySpan<char> haystack = value.AsSpan();
        ReadOnlySpan<char> needle = token.AsSpan().Trim();
        int start = 0;
        while (start <= haystack.Length - needle.Length)
        {
            int index = haystack[start..].IndexOf(needle, StringComparison.OrdinalIgnoreCase);
            if (index < 0)
            {
                return false;
            }

            int absoluteIndex = start + index;
            int afterIndex = absoluteIndex + needle.Length;
            bool beforeBoundary = absoluteIndex == 0 || !char.IsLetterOrDigit(haystack[absoluteIndex - 1]);
            bool afterBoundary = afterIndex >= haystack.Length || !char.IsLetterOrDigit(haystack[afterIndex]);
            if (beforeBoundary && afterBoundary)
            {
                return true;
            }

            start = absoluteIndex + 1;
        }

        return false;
    }

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

    private static bool TryGetBoolean(JsonElement root, string propertyName, out bool value)
    {
        value = false;
        if (!root.TryGetProperty(propertyName, out JsonElement property)
            || property.ValueKind is not JsonValueKind.True and not JsonValueKind.False)
        {
            return false;
        }

        value = property.GetBoolean();
        return true;
    }

    private static bool ReceiptArrayIsEmpty(JsonElement root, string propertyName)
        => root.TryGetProperty(propertyName, out JsonElement property)
            && property.ValueKind == JsonValueKind.Array
            && !property.EnumerateArray().Any();

    private static bool ReceiptSurfacePassed(JsonElement root, string surfaceName)
    {
        if (!root.TryGetProperty("surfaces", out JsonElement surfaces)
            || surfaces.ValueKind != JsonValueKind.Array)
        {
            return false;
        }

        foreach (JsonElement surface in surfaces.EnumerateArray())
        {
            if (surface.ValueKind == JsonValueKind.Object
                && TryGetString(surface, "name", out string? name)
                && string.Equals(name, surfaceName, StringComparison.OrdinalIgnoreCase)
                && TryGetString(surface, "status", out string? status)
                && string.Equals(status, "pass", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
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
            entry.TelegramShareDeliveryReceiptPath,
            entry.FinalNoFallbackNoSentinelAuditReceiptPath
        ];

        return values.Any(HasFakeMarker);
    }

    private static bool HasFakeMarker(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        string normalized = value
            .Replace("no-fallback", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("no_fallback", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("no fallback", string.Empty, StringComparison.OrdinalIgnoreCase);
        return normalized.Contains("stub", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("fallback", StringComparison.OrdinalIgnoreCase);
    }

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
            ProviderManuscriptAccountAlias = CleanNullable(request.ProviderManuscriptAccountAlias),
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
            AudiobookProviderAccountAlias = CleanNullable(request.AudiobookProviderAccountAlias),
            DossierVideoPath = CleanNullable(request.DossierVideoPath),
            DossierVideoReceiptPath = CleanNullable(request.DossierVideoReceiptPath),
            MoviePosterPath = CleanNullable(request.MoviePosterPath),
            MovieSubtitlesPath = CleanNullable(request.MovieSubtitlesPath),
            MovieStoryboardPath = CleanNullable(request.MovieStoryboardPath),
            TelegramShareDeliveryReceiptPath = CleanNullable(request.TelegramShareDeliveryReceiptPath),
            FinalNoFallbackNoSentinelAuditReceiptPath = CleanNullable(request.FinalNoFallbackNoSentinelAuditReceiptPath),
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
            Sha256Text(BuildOwnerPath(entry, null)),
            Sha256Text(BuildOwnerPath(entry, "read")),
            Sha256Text(BuildOwnerPath(entry, "listen")),
            Sha256Text(BuildOwnerPath(entry, "watch")),
            BuildOriginEditionNamespace(entry),
            Sha256Text(BuildOriginEditionNamespace(entry)),
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

    private static string Sha256Text(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

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
    public string? ProviderManuscriptAccountAlias { get; init; }
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
    public string? AudiobookProviderAccountAlias { get; init; }
    public string? DossierVideoPath { get; init; }
    public string? DossierVideoReceiptPath { get; init; }
    public string? MoviePosterPath { get; init; }
    public string? MovieSubtitlesPath { get; init; }
    public string? MovieStoryboardPath { get; init; }
    public string? TelegramShareDeliveryReceiptPath { get; init; }
    public string? FinalNoFallbackNoSentinelAuditReceiptPath { get; init; }
    public IReadOnlyList<string>? MissingGoldRequirements { get; init; }
}
