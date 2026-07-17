using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using Chummer.Run.Api.ViewModels;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Hosting;

namespace Chummer.Run.Api.Services;

public sealed class PublicParticipateSnapshotService
{
    private static readonly TimeSpan FetchTimeout = TimeSpan.FromMilliseconds(1250);
    private static readonly TimeSpan RefreshTargetAge = TimeSpan.FromMinutes(4);
    private static readonly TimeSpan RefreshRetryGap = TimeSpan.FromSeconds(30);

    private readonly PublicParticipateSnapshotStore _store;
    private readonly IConfiguration _configuration;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IWebHostEnvironment _webHostEnvironment;
    private readonly ILogger<PublicParticipateSnapshotService> _logger;
    private readonly object _gate = new();

    private PublicParticipateSnapshot _snapshot;
    private DateTimeOffset _lastRefreshAttemptUtc;
    private int _refreshInFlight;

    public PublicParticipateSnapshotService(
        PublicParticipateSnapshotStore store,
        IConfiguration configuration,
        IHttpClientFactory httpClientFactory,
        IWebHostEnvironment webHostEnvironment,
        ILogger<PublicParticipateSnapshotService> logger)
    {
        _store = store;
        _configuration = configuration;
        _httpClientFactory = httpClientFactory;
        _webHostEnvironment = webHostEnvironment;
        _logger = logger;

        lock (_store.Gate)
        {
            _snapshot = _store.Snapshot;
        }
    }

    public PublicParticipateSnapshot GetSnapshot()
    {
        PublicParticipateSnapshot snapshot = Snapshot;
        if (!ShouldShortCircuitHostedBoardUpstream(ResolveProductLiftHostedBoardUri()))
        {
            QueueRefreshIfDue(snapshot);
        }
        return snapshot;
    }

    public PublicParticipatePostSnapshot? TryGetPostDetail(string canonicalHref)
    {
        if (string.IsNullOrWhiteSpace(canonicalHref))
        {
            return null;
        }

        PublicParticipateSnapshot snapshot = GetSnapshot();
        return snapshot.Posts.FirstOrDefault(item =>
            string.Equals(item.CanonicalHref, canonicalHref, StringComparison.OrdinalIgnoreCase));
    }

    public async Task<PublicParticipateSnapshot> RefreshAsync(CancellationToken cancellationToken)
    {
        Uri? upstream = ResolveProductLiftHostedBoardUri();
        if (ShouldShortCircuitHostedBoardUpstream(upstream) || upstream is null)
        {
            return Snapshot;
        }

        MarkRefreshAttempt(DateTimeOffset.UtcNow);

        Uri upstreamOrigin = new($"{upstream.GetLeftPart(UriPartial.Authority).TrimEnd('/')}/");

        try
        {
            using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeoutCts.CancelAfter(FetchTimeout);

            PublicParticipateSnapshot? fetched = await FetchSnapshotFromUpstreamAsync(
                upstreamOrigin,
                DateTimeOffset.UtcNow,
                timeoutCts.Token).ConfigureAwait(false);
            if (fetched is null)
            {
                return Snapshot;
            }

            PersistSnapshot(fetched);
            return fetched;
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Participate snapshot refresh could not reach ProductLift.");
            return Snapshot;
        }
        catch (JsonException ex)
        {
            _logger.LogWarning(ex, "Participate snapshot refresh received invalid ProductLift JSON.");
            return Snapshot;
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Participate snapshot refresh timed out.");
            return Snapshot;
        }
    }

    public void QueueRefreshIfDue()
        => QueueRefreshIfDue(Snapshot);

    private PublicParticipateSnapshot Snapshot
    {
        get
        {
            lock (_gate)
            {
                return _snapshot;
            }
        }
    }

    private void PersistSnapshot(PublicParticipateSnapshot snapshot)
    {
        lock (_store.Gate)
        {
            _store.PersistLocked(snapshot);
        }

        lock (_gate)
        {
            _snapshot = snapshot;
        }
    }

    private void QueueRefreshIfDue(PublicParticipateSnapshot snapshot)
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        if (snapshot.SyncedAtUtc != DateTimeOffset.MinValue
            && now - snapshot.SyncedAtUtc < RefreshTargetAge)
        {
            return;
        }

        if (!TryBeginBackgroundRefresh(now))
        {
            return;
        }

        _ = Task.Run(async () =>
        {
            try
            {
                await RefreshAsync(CancellationToken.None).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                _logger.LogDebug(ex, "Participate background refresh failed.");
            }
            finally
            {
                Interlocked.Exchange(ref _refreshInFlight, 0);
            }
        });
    }

    private bool TryBeginBackgroundRefresh(DateTimeOffset now)
    {
        if (Interlocked.CompareExchange(ref _refreshInFlight, 1, 0) != 0)
        {
            return false;
        }

        lock (_gate)
        {
            if (now - _lastRefreshAttemptUtc < RefreshRetryGap)
            {
                Interlocked.Exchange(ref _refreshInFlight, 0);
                return false;
            }

            _lastRefreshAttemptUtc = now;
            return true;
        }
    }

    private void MarkRefreshAttempt(DateTimeOffset now)
    {
        lock (_gate)
        {
            _lastRefreshAttemptUtc = now;
        }
    }

    private Uri? ResolveProductLiftHostedBoardUri()
        => ProductLiftHostedUriResolver.TryResolve(_configuration["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"]?.Trim());

    private bool ShouldShortCircuitHostedBoardUpstream(Uri? upstream)
        => upstream is not null
            && _webHostEnvironment.IsDevelopment()
            && upstream.Host.EndsWith(".example.test", StringComparison.OrdinalIgnoreCase);

    private async Task<PublicParticipateSnapshot?> FetchSnapshotFromUpstreamAsync(
        Uri upstreamOrigin,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        Uri target = new(upstreamOrigin, "http_api/posts?tab=feedback");
        using HttpClient client = _httpClientFactory.CreateClient();
        using var outbound = new HttpRequestMessage(HttpMethod.Get, target);
        outbound.Headers.TryAddWithoutValidation("Accept", "application/json");
        outbound.Headers.TryAddWithoutValidation("User-Agent", "Chummer.Run.Api/participate-refresh");

        using HttpResponseMessage response = await client.SendAsync(outbound, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            return null;
        }

        string mediaType = response.Content.Headers.ContentType?.MediaType ?? string.Empty;
        if (!mediaType.Contains("json", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        await using Stream stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using JsonDocument document = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
        if (!document.RootElement.TryGetProperty("data", out JsonElement data) || data.ValueKind != JsonValueKind.Array)
        {
            return null;
        }

        List<PublicParticipatePostSnapshot> posts = [];
        foreach (JsonElement item in data.EnumerateArray())
        {
            PublicParticipatePostSnapshot? post = TryMapParticipatePost(item);
            if (post is null)
            {
                continue;
            }

            posts.Add(post);
            if (posts.Count >= 64)
            {
                break;
            }
        }

        int totalCount = ReadJsonInt(document.RootElement, "total");
        if (totalCount <= 0)
        {
            totalCount = posts.Count;
        }

        return new PublicParticipateSnapshot(posts, totalCount, now);
    }

    private static PublicParticipatePostSnapshot? TryMapParticipatePost(JsonElement item)
    {
        string title = ReadJsonString(item, "title");
        if (string.IsNullOrWhiteSpace(title))
        {
            return null;
        }

        string canonicalHref = RewriteParticipatePostHref(FirstNonEmptyParticipateValue(
            ReadJsonString(item, "proxy_url"),
            ReadJsonString(item, "url")))
            ?? BuildFallbackParticipatePostHref(title, ReadJsonString(item, "id"))
            ?? string.Empty;
        if (string.IsNullOrWhiteSpace(canonicalHref))
        {
            return null;
        }

        FirstPartyParticipatePostViewModel post = new(
            Id: ReadJsonString(item, "id"),
            Title: CleanParticipateCopy(title),
            Summary: CleanParticipateCopy(FirstNonEmptyParticipateValue(
                ReadJsonString(item, "description_short"),
                ReadJsonString(item, "excerpt"),
                StripHtml(ReadJsonString(item, "description")))),
            Score: ReadJsonInt(item, "votes_count"),
            CommentCount: ReadJsonInt(item, "comments_count"),
            Status: CleanParticipateStatus(ReadNestedJsonString(item, "status", "name")),
            Category: CleanParticipateCategory(ReadNestedJsonString(item, "category", "name")),
            UpdatedLabel: FormatParticipateUpdatedLabel(ReadJsonString(item, "updated_at")),
            Href: canonicalHref);

        IReadOnlyList<string> bodyParagraphs = BuildParticipateDetailParagraphs(item, post.Summary);
        return new PublicParticipatePostSnapshot(canonicalHref, post, bodyParagraphs);
    }

    private static string ReadJsonString(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out JsonElement value))
        {
            return string.Empty;
        }

        return value.ValueKind switch
        {
            JsonValueKind.String => value.GetString()?.Trim() ?? string.Empty,
            JsonValueKind.Number => value.GetRawText(),
            _ => string.Empty
        };
    }

    private static int ReadJsonInt(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out JsonElement value))
        {
            return 0;
        }

        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out int number))
        {
            return Math.Max(0, number);
        }

        return value.ValueKind == JsonValueKind.String && int.TryParse(value.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out number)
            ? Math.Max(0, number)
            : 0;
    }

    private static string ReadNestedJsonString(JsonElement element, string objectPropertyName, string nestedPropertyName)
    {
        if (!element.TryGetProperty(objectPropertyName, out JsonElement nested) || nested.ValueKind != JsonValueKind.Object)
        {
            return string.Empty;
        }

        return ReadJsonString(nested, nestedPropertyName);
    }

    private static string FirstNonEmptyParticipateValue(params string[] values)
        => values.FirstOrDefault(static value => !string.IsNullOrWhiteSpace(value))?.Trim() ?? string.Empty;

    private static string? RewriteParticipatePostHref(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string trimmed = value.Trim();
        if (Uri.TryCreate(trimmed, UriKind.Absolute, out Uri? absolute))
        {
            string pathAndQuery = string.IsNullOrWhiteSpace(absolute.PathAndQuery) ? "/" : absolute.PathAndQuery;
            return $"/participate/board{pathAndQuery}";
        }

        if (!Uri.TryCreate(trimmed, UriKind.Relative, out _))
        {
            return null;
        }

        string relative = trimmed.StartsWith("/", StringComparison.Ordinal) ? trimmed : $"/{trimmed}";
        if (relative.StartsWith("/participate/board", StringComparison.OrdinalIgnoreCase))
        {
            return relative;
        }

        return $"/participate/board{relative}";
    }

    private static string? BuildFallbackParticipatePostHref(string title, string id)
    {
        string normalizedId = id.Trim();
        if (string.IsNullOrWhiteSpace(title) || string.IsNullOrWhiteSpace(normalizedId))
        {
            return null;
        }

        string slug = Regex.Replace(title.Trim().ToLowerInvariant(), @"[^a-z0-9]+", "-", RegexOptions.None, TimeSpan.FromMilliseconds(250)).Trim('-');
        if (string.IsNullOrWhiteSpace(slug))
        {
            return null;
        }

        return $"/participate/board/p/{slug}-{normalizedId}";
    }

    private static string StripHtml(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        string withoutTags = Regex.Replace(value, "<.*?>", " ", RegexOptions.Singleline, TimeSpan.FromMilliseconds(250));
        return System.Net.WebUtility.HtmlDecode(withoutTags).Trim();
    }

    private static string CleanParticipateCopy(string value)
        => NormalizeParticipateCopy(value, maxLength: 220);

    private static string CleanParticipateLongCopy(string value)
        => NormalizeParticipateCopy(value, maxLength: null);

    private static string NormalizeParticipateCopy(string value, int? maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        string cleaned = value
            .Replace("AI-powered", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("AI powered", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("AI-generated", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("AI generated", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("Automatically generate", "Create", StringComparison.OrdinalIgnoreCase)
            .Replace("automatically generate", "create", StringComparison.Ordinal);

        cleaned = Regex.Replace(cleaned, @"\s{2,}", " ", RegexOptions.None, TimeSpan.FromMilliseconds(250)).Trim();
        if (maxLength is null || cleaned.Length <= maxLength.Value)
        {
            return cleaned;
        }

        int sliceLength = Math.Max(0, maxLength.Value - 3);
        return $"{cleaned[..sliceLength].TrimEnd()}...";
    }

    private static string CleanParticipateStatus(string value)
    {
        string cleaned = CleanParticipateCopy(value);
        return string.Equals(cleaned, "Gathering votes", StringComparison.OrdinalIgnoreCase)
            ? "Open"
            : (string.IsNullOrWhiteSpace(cleaned) ? "Open" : cleaned);
    }

    private static string CleanParticipateCategory(string value)
    {
        string cleaned = CleanParticipateCopy(value);
        return string.Equals(cleaned, "Feature", StringComparison.OrdinalIgnoreCase)
            ? "Idea"
            : (string.IsNullOrWhiteSpace(cleaned) ? "Request" : cleaned);
    }

    private static IReadOnlyList<string> BuildParticipateDetailParagraphs(JsonElement item, string fallbackSummary)
    {
        string body = CleanParticipateLongCopy(FirstNonEmptyParticipateValue(
            StripHtml(ReadJsonString(item, "description")),
            ReadJsonString(item, "clean_description_changelog"),
            ReadJsonString(item, "description_short"),
            fallbackSummary));
        if (string.IsNullOrWhiteSpace(body))
        {
            return Array.Empty<string>();
        }

        string[] paragraphs = body
            .Split(["\r\n\r\n", "\n\n"], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(paragraph => Regex.Replace(paragraph, @"\s+", " ", RegexOptions.None, TimeSpan.FromMilliseconds(250)).Trim())
            .Where(static paragraph => !string.IsNullOrWhiteSpace(paragraph))
            .ToArray();
        return paragraphs.Length == 0 ? new[] { body } : paragraphs;
    }

    private static string FormatParticipateUpdatedLabel(string raw)
    {
        if (!DateTimeOffset.TryParse(raw, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out DateTimeOffset updated))
        {
            return "Updated";
        }

        return $"Updated {updated.UtcDateTime:yyyy-MM-dd}";
    }
}

public sealed record PublicParticipateSnapshot(
    IReadOnlyList<PublicParticipatePostSnapshot> Posts,
    int TotalCount,
    DateTimeOffset SyncedAtUtc)
{
    public static PublicParticipateSnapshot Empty { get; } = new(Array.Empty<PublicParticipatePostSnapshot>(), 0, DateTimeOffset.MinValue);
}

public sealed record PublicParticipatePostSnapshot(
    string CanonicalHref,
    FirstPartyParticipatePostViewModel Post,
    IReadOnlyList<string> BodyParagraphs);

public sealed class PublicParticipateSnapshotWorker : BackgroundService
{
    private static readonly TimeSpan DefaultInitialDelay = TimeSpan.FromSeconds(15);
    private static readonly TimeSpan DefaultInterval = TimeSpan.FromMinutes(5);

    private readonly PublicParticipateSnapshotService _snapshots;
    private readonly IConfiguration _configuration;
    private readonly ILogger<PublicParticipateSnapshotWorker> _logger;

    public PublicParticipateSnapshotWorker(
        PublicParticipateSnapshotService snapshots,
        IConfiguration configuration,
        ILogger<PublicParticipateSnapshotWorker> logger)
    {
        _snapshots = snapshots;
        _configuration = configuration;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!IsEnabled())
        {
            return;
        }

        TimeSpan initialDelay = ResolveDurationSeconds("CHUMMER_PUBLIC_PARTICIPATE_REFRESH_INITIAL_DELAY_SECONDS", DefaultInitialDelay);
        TimeSpan interval = ResolveDurationMinutes("CHUMMER_PUBLIC_PARTICIPATE_REFRESH_INTERVAL_MINUTES", DefaultInterval);

        if (initialDelay > TimeSpan.Zero)
        {
            await Task.Delay(initialDelay, stoppingToken);
        }

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                PublicParticipateSnapshot snapshot = await _snapshots.RefreshAsync(stoppingToken).ConfigureAwait(false);
                if (snapshot.Posts.Count > 0)
                {
                    _logger.LogInformation(
                        "Participate snapshot refresh stored {PostCount} posts at {SyncedAtUtc:O}.",
                        snapshot.Posts.Count,
                        snapshot.SyncedAtUtc);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Participate snapshot worker loop failed.");
            }

            await Task.Delay(interval, stoppingToken);
        }
    }

    private bool IsEnabled()
        => ParseBool(_configuration["CHUMMER_PUBLIC_PARTICIPATE_REFRESH_ENABLED"], defaultValue: true);

    private TimeSpan ResolveDurationMinutes(string key, TimeSpan fallback)
    {
        string? raw = Normalize(_configuration[key]);
        return int.TryParse(raw, out int minutes) && minutes > 0 ? TimeSpan.FromMinutes(minutes) : fallback;
    }

    private TimeSpan ResolveDurationSeconds(string key, TimeSpan fallback)
    {
        string? raw = Normalize(_configuration[key]);
        return int.TryParse(raw, out int seconds) && seconds >= 0 ? TimeSpan.FromSeconds(seconds) : fallback;
    }

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static bool ParseBool(string? value, bool defaultValue)
    {
        string? normalized = Normalize(value);
        return normalized is null ? defaultValue : bool.TryParse(normalized, out bool parsed) ? parsed : defaultValue;
    }
}
