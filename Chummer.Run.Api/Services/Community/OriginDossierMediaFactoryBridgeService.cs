using Chummer.Media.Contracts;
using System.Text;
using System.Text.Json;

namespace Chummer.Run.Api.Services.Community;

public sealed class OriginDossierMediaRequestOutboxService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };
    private static readonly Encoding Utf8NoBom = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);

    private readonly IConfiguration _configuration;
    private readonly ILogger<OriginDossierMediaRequestOutboxService> _logger;

    public OriginDossierMediaRequestOutboxService(
        IConfiguration configuration,
        ILogger<OriginDossierMediaRequestOutboxService> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public OriginDossierMediaEnqueueResult Enqueue(
        OriginDossierMediaDispatchKind kind,
        OriginDossierMediaDispatchSource source,
        string locale = "en-US")
    {
        ArgumentNullException.ThrowIfNull(source);
        string? inboxRoot = ResolveRoot(
            "CHUMMER_MEDIA_FACTORY_ORIGIN_INBOX",
            "OriginDossier:MediaFactoryInboxRoot");
        if (string.IsNullOrWhiteSpace(inboxRoot))
        {
            return new(false, "disabled", string.Empty, string.Empty);
        }

        string requestId = BuildRequestId(kind, source);
        var request = new OriginDossierMediaDispatchRequest(
            ContractVersion: OriginDossierMediaDispatchContract.Version,
            RequestId: requestId,
            Kind: kind,
            ProjectId: source.ProjectId,
            OwnerRefHash: source.OwnerRefHash,
            ApprovedOriginPacketId: source.ApprovedOriginPacketId,
            OriginRevisionId: source.OriginRevisionId,
            Source: "chummer6-hub",
            RequestedAtUtc: DateTimeOffset.UtcNow,
            Locale: string.IsNullOrWhiteSpace(locale) ? "en-US" : locale.Trim(),
            SelectionId: source.SelectionId,
            SelectionLabel: source.SelectionLabel,
            SelectionSummary: source.SelectionSummary,
            ManuscriptPath: source.ManuscriptPath,
            SourcePacketPath: source.SourcePacketPath,
            CoverPath: source.CoverPath,
            StoryboardPath: source.StoryboardPath,
            DurationTargetSeconds: kind == OriginDossierMediaDispatchKind.CinematicScene ? 10 : 1);

        try
        {
            Directory.CreateDirectory(inboxRoot);
            string requestPath = Path.Combine(inboxRoot, requestId + ".request.json");
            if (File.Exists(requestPath))
            {
                return new(true, "already_queued", requestId, requestPath);
            }

            string temporaryPath = requestPath + $".{Guid.NewGuid():N}.tmp";
            File.WriteAllText(
                temporaryPath,
                JsonSerializer.Serialize(request, JsonOptions) + Environment.NewLine,
                Utf8NoBom);
            try
            {
                File.Move(temporaryPath, requestPath);
            }
            catch (IOException) when (File.Exists(requestPath))
            {
                File.Delete(temporaryPath);
                return new(true, "already_queued", requestId, requestPath);
            }

            return new(true, "queued", requestId, requestPath);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _logger.LogError(
                ex,
                "Origin Dossier media request {RequestId} could not be written to the media-factory inbox.",
                requestId);
            return new(false, "outbox_write_failed", requestId, string.Empty);
        }
    }

    private string? ResolveRoot(string environmentKey, string configurationKey)
    {
        string? configured = _configuration[environmentKey] ?? _configuration[configurationKey];
        return string.IsNullOrWhiteSpace(configured)
            ? null
            : Path.GetFullPath(configured.Trim());
    }

    private static string BuildRequestId(
        OriginDossierMediaDispatchKind kind,
        OriginDossierMediaDispatchSource source)
        => OriginDossierMediaDispatchContract.BuildRequestId(
            kind,
            source.ProjectId,
            source.OwnerRefHash,
            source.SelectionId,
            source.OriginRevisionId);
}

public sealed record OriginDossierMediaEnqueueResult(
    bool Queued,
    string Status,
    string RequestId,
    string RequestPath);

public sealed class OriginDossierMediaReceiptIngestService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };
    private static readonly Encoding Utf8NoBom = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);

    private readonly IConfiguration _configuration;
    private readonly OriginDossierPublicationService _publications;
    private readonly ILogger<OriginDossierMediaReceiptIngestService> _logger;

    public OriginDossierMediaReceiptIngestService(
        IConfiguration configuration,
        OriginDossierPublicationService publications,
        ILogger<OriginDossierMediaReceiptIngestService> logger)
    {
        _configuration = configuration;
        _publications = publications;
        _logger = logger;
    }

    public IReadOnlyList<OriginDossierMediaReceiptIngestResult> IngestPending(int limit = 25)
    {
        string? receiptRoot = ResolveReceiptRoot();
        if (string.IsNullOrWhiteSpace(receiptRoot) || !Directory.Exists(receiptRoot))
        {
            return Array.Empty<OriginDossierMediaReceiptIngestResult>();
        }

        var results = new List<OriginDossierMediaReceiptIngestResult>();
        foreach (string receiptPath in Directory
                     .EnumerateFiles(receiptRoot, "*.receipt.json", SearchOption.TopDirectoryOnly)
                     .Order(StringComparer.Ordinal)
                     .Take(Math.Clamp(limit, 1, 100)))
        {
            string markerPath = receiptPath + ".ingested.json";
            if (File.Exists(markerPath))
            {
                continue;
            }

            OriginDossierMediaReceiptIngestResult result;
            try
            {
                OriginDossierMediaDispatchReceipt receipt =
                    JsonSerializer.Deserialize<OriginDossierMediaDispatchReceipt>(
                        File.ReadAllText(receiptPath, Encoding.UTF8),
                        JsonOptions)
                    ?? throw new JsonException("Origin Dossier media receipt is empty.");
                OriginDossierMediaCompletionApplyResult applied =
                    _publications.ApplyMediaDispatchReceipt(receipt, receiptPath);
                result = new(
                    ReceiptPath: receiptPath,
                    RequestId: receipt.RequestId,
                    Applied: applied.Applied,
                    Status: string.Equals(receipt.Status, "failed", StringComparison.Ordinal)
                        ? receipt.ErrorCode
                        : applied.Status);
            }
            catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
            {
                _logger.LogWarning(ex, "Origin Dossier media receipt could not be ingested from {ReceiptPath}.", receiptPath);
                result = new(receiptPath, string.Empty, false, "receipt_read_failed");
            }

            WriteMarker(markerPath, result);
            results.Add(result);
        }

        return results;
    }

    private string? ResolveReceiptRoot()
    {
        string? configured = _configuration["CHUMMER_MEDIA_FACTORY_ORIGIN_RECEIPTS"]
            ?? _configuration["OriginDossier:MediaFactoryReceiptRoot"];
        return string.IsNullOrWhiteSpace(configured)
            ? null
            : Path.GetFullPath(configured.Trim());
    }

    private static void WriteMarker(
        string markerPath,
        OriginDossierMediaReceiptIngestResult result)
    {
        string temporaryPath = markerPath + $".{Guid.NewGuid():N}.tmp";
        File.WriteAllText(
            temporaryPath,
            JsonSerializer.Serialize(
                new
                {
                    contractVersion = "chummer.origin_dossier_media_ingest.v1",
                    result.ReceiptPath,
                    result.RequestId,
                    result.Applied,
                    result.Status,
                    observedAtUtc = DateTimeOffset.UtcNow
                },
                JsonOptions) + Environment.NewLine,
            Utf8NoBom);
        File.Move(temporaryPath, markerPath, true);
    }
}

public sealed record OriginDossierMediaReceiptIngestResult(
    string ReceiptPath,
    string RequestId,
    bool Applied,
    string Status);

public sealed class OriginDossierMediaReceiptIngestWorker : BackgroundService
{
    private readonly OriginDossierMediaReceiptIngestService _ingest;
    private readonly ILogger<OriginDossierMediaReceiptIngestWorker> _logger;

    public OriginDossierMediaReceiptIngestWorker(
        OriginDossierMediaReceiptIngestService ingest,
        ILogger<OriginDossierMediaReceiptIngestWorker> logger)
    {
        _ingest = ingest;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                _ingest.IngestPending();
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                _logger.LogError(ex, "Origin Dossier media receipt ingest iteration failed.");
            }

            await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
        }
    }
}
