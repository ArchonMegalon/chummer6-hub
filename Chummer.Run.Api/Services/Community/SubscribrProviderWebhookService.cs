using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class SubscribrProviderWebhookService
{
    private static readonly StringComparison PathComparison =
        OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;

    private static readonly HashSet<string> SupportedEventTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "script.export_ready",
        "script.completed",
        "script.ready"
    };

    private static readonly TimeSpan AcceptedTimestampSkew = TimeSpan.FromMinutes(15);

    private readonly SubscribrWebhookStore _store;
    private readonly IConfiguration _configuration;
    private readonly string[] _allowedSourceRoots;

    public SubscribrProviderWebhookService(SubscribrWebhookStore store, IConfiguration configuration)
    {
        _store = store;
        _configuration = configuration;
        _allowedSourceRoots = ResolveAllowedSourceRoots(configuration);
    }

    public string ComputeSignature(string rawPayload, string timestamp)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(rawPayload);

        string material = SignatureMaterial(rawPayload, timestamp);
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(GetWebhookSecret()));
        return $"sha256={Convert.ToHexString(hmac.ComputeHash(Encoding.UTF8.GetBytes(material))).ToLowerInvariant()}";
    }

    public string ComputeSignature(SubscribrWebhookRequest request, string timestamp)
        => ComputeSignature(CanonicalPayload(request), timestamp);

    public SubscribrWebhookResult ProcessWebhook(
        string rawPayload,
        SubscribrWebhookRequest request,
        string? signature,
        string? timestamp,
        DateTimeOffset? now = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(rawPayload);
        return ProcessWebhookCore(rawPayload, request, signature, timestamp, now);
    }

    public SubscribrWebhookResult ProcessWebhook(
        SubscribrWebhookRequest request,
        string? signature,
        string? timestamp,
        DateTimeOffset? now = null)
        => ProcessWebhookCore(CanonicalPayload(request), request, signature, timestamp, now);

    private SubscribrWebhookResult ProcessWebhookCore(
        string rawPayload,
        SubscribrWebhookRequest request,
        string? signature,
        string? timestamp,
        DateTimeOffset? now)
    {
        ArgumentNullException.ThrowIfNull(request);

        if (!IsWebhookLaneEnabled())
        {
            throw new InvalidOperationException("Subscribr webhook lane is disabled.");
        }

        DateTimeOffset processedAtUtc = (now ?? DateTimeOffset.UtcNow).ToUniversalTime();
        string eventId = Clean(request.EventId);
        string eventType = Clean(request.EventType);

        if (!VerifySignature(rawPayload, signature, timestamp))
        {
            return RecordRejected(eventId, eventType, "failed", "first_seen", "blocked", "signature verification failed", processedAtUtc);
        }

        if (!TryParseTimestamp(timestamp, out DateTimeOffset webhookTimestampUtc))
        {
            return RecordRejected(eventId, eventType, "verified", "first_seen", "blocked", "timestamp header is required", processedAtUtc);
        }

        if ((processedAtUtc - webhookTimestampUtc).Duration() > AcceptedTimestampSkew)
        {
            return RecordRejected(eventId, eventType, "verified", "first_seen", "blocked", "timestamp outside accepted window", processedAtUtc);
        }

        if (string.IsNullOrWhiteSpace(eventId))
        {
            return RecordRejected(eventId, eventType, "verified", "first_seen", "blocked", "event id is required", processedAtUtc);
        }

        if (eventId.Length > 256)
        {
            return RecordRejected(eventId, eventType, "verified", "first_seen", "blocked", "event id exceeds the 256 character limit", processedAtUtc);
        }

        lock (_store.Gate)
        {
            SubscribrWebhookLedgerEntry? existing = _store.Entries.FirstOrDefault(entry =>
                string.Equals(entry.EventId, eventId, StringComparison.OrdinalIgnoreCase));
            if (existing is not null)
            {
                return new SubscribrWebhookResult(
                    EventId: existing.EventId,
                    Status: existing.Status,
                    SignatureStatus: existing.SignatureStatus,
                    ReplayStatus: "duplicate_ignored",
                    ValidationStatus: existing.ValidationStatus,
                    PacketId: existing.PacketId,
                    ReceiptPath: existing.ReceiptPath,
                    RejectionReason: existing.RejectionReason,
                    ProcessedAtUtc: existing.ProcessedAtUtc);
            }

            if (!SupportedEventTypes.Contains(eventType))
            {
                return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", "unsupported Subscribr event type", processedAtUtc);
            }

            if (string.IsNullOrWhiteSpace(Clean(request.ProviderScriptId)))
            {
                return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", "provider script id is required", processedAtUtc);
            }

            string packetPath;
            string markdownExportPath;
            JsonObject packet;
            string packetId;
            string mode;
            string sourcePacketSha256;
            string scriptMarkdownSha256;
            try
            {
                packetPath = ResolveAllowedSourcePath(request.PacketPath, "packet path");
                markdownExportPath = ResolveAllowedSourcePath(request.MarkdownExportPath, "markdown export path");
                packet = LoadPacket(packetPath);
                if (!string.Equals(packet["contract_name"]?.GetValue<string>(), "chummer.content_source_packet.v1", StringComparison.Ordinal))
                {
                    return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", "packet contract is not chummer.content_source_packet.v1", processedAtUtc);
                }

                if (!string.Equals(packet["target_provider"]?.GetValue<string>(), "subscribr", StringComparison.OrdinalIgnoreCase))
                {
                    return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", "packet target provider must be subscribr", processedAtUtc);
                }

                if (packet["approval"]?["publication_allowed"]?.GetValue<bool>() is true)
                {
                    return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", "packet must keep publication disabled before review", processedAtUtc);
                }

                packetId = Clean(packet["packet_id"]?.GetValue<string>());
                if (string.IsNullOrWhiteSpace(packetId))
                {
                    return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", "packet_id is required", processedAtUtc);
                }

                mode = Clean(packet["mode"]?.GetValue<string>());
                if (string.IsNullOrWhiteSpace(mode))
                {
                    return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", "packet mode is required", processedAtUtc);
                }

                sourcePacketSha256 = Sha256File(packetPath);
                scriptMarkdownSha256 = Sha256File(markdownExportPath);
            }
            catch (InvalidDataException ex)
            {
                return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", ex.Message, processedAtUtc);
            }
            catch (JsonException)
            {
                return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", "packet JSON is invalid", processedAtUtc);
            }
            catch (IOException ex)
            {
                return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", $"provider source files are unreadable: {ex.Message}", processedAtUtc);
            }
            catch (UnauthorizedAccessException ex)
            {
                return RecordRejectedLocked(eventId, eventType, "verified", "first_seen", "blocked", $"provider source files are unreadable: {ex.Message}", processedAtUtc);
            }

            string receiptPath = BuildReceiptPath(eventId);
            bool originMode = mode.StartsWith("ORIGIN_DOSSIER", StringComparison.Ordinal);
            var receipt = new JsonObject
            {
                ["contract_name"] = "chummer.subscribr_script_receipt.v1",
                ["status"] = "review_required",
                ["provider"] = "subscribr",
                ["provider_event_id"] = eventId,
                ["mode"] = mode,
                ["packet_id"] = packetId,
                ["source_packet_path"] = packetPath,
                ["script_markdown_path"] = markdownExportPath,
                ["channel_key"] = packet["subscribr_channel_key"]?.GetValue<string>(),
                ["provider_channel_id"] = Clean(request.ProviderChannelId),
                ["provider_idea_id"] = Clean(request.ProviderIdeaId),
                ["provider_script_id"] = Clean(request.ProviderScriptId),
                ["source_packet_sha256"] = sourcePacketSha256,
                ["script_markdown_sha256"] = scriptMarkdownSha256,
                ["source_heads"] = packet["source_heads"]?.DeepClone(),
                ["validation"] = new JsonObject
                {
                    ["source_binding"] = "pass",
                    ["private_data"] = "pending",
                    ["copyright"] = "pending",
                    ["mechanics_unchanged"] = "pending",
                    ["release_claims"] = "pending",
                    ["origin_canon"] = originMode ? "pending" : "not_applicable",
                    ["approval"] = "pending"
                },
                ["publication_allowed"] = false,
                ["media_factory_allowed"] = false
            };
            File.WriteAllText(receiptPath, receipt.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n", Encoding.UTF8);

            _store.Entries.Add(new SubscribrWebhookLedgerEntry(
                EventId: eventId,
                EventType: eventType,
                Status: "accepted",
                SignatureStatus: "verified",
                ReplayStatus: "first_seen",
                ValidationStatus: "review_required",
                PacketId: packetId,
                ReceiptPath: receiptPath,
                RejectionReason: null,
                ProcessedAtUtc: processedAtUtc));
            _store.PersistLocked();

            return new SubscribrWebhookResult(
                EventId: eventId,
                Status: "accepted",
                SignatureStatus: "verified",
                ReplayStatus: "first_seen",
                ValidationStatus: "review_required",
                PacketId: packetId,
                ReceiptPath: receiptPath,
                RejectionReason: null,
                ProcessedAtUtc: processedAtUtc);
        }
    }

    public static string CanonicalPayload(SubscribrWebhookRequest request)
        => JsonSerializer.Serialize(request, new JsonSerializerOptions(JsonSerializerDefaults.Web));

    private SubscribrWebhookResult RecordRejected(
        string eventId,
        string eventType,
        string signatureStatus,
        string replayStatus,
        string validationStatus,
        string reason,
        DateTimeOffset processedAtUtc)
    {
        lock (_store.Gate)
        {
            return RecordRejectedLocked(eventId, eventType, signatureStatus, replayStatus, validationStatus, reason, processedAtUtc);
        }
    }

    private SubscribrWebhookResult RecordRejectedLocked(
        string eventId,
        string eventType,
        string signatureStatus,
        string replayStatus,
        string validationStatus,
        string reason,
        DateTimeOffset processedAtUtc)
    {
        if (!string.IsNullOrWhiteSpace(eventId)
            && _store.Entries.All(entry => !string.Equals(entry.EventId, eventId, StringComparison.OrdinalIgnoreCase)))
        {
            _store.Entries.Add(new SubscribrWebhookLedgerEntry(
                EventId: eventId,
                EventType: eventType,
                Status: "rejected",
                SignatureStatus: signatureStatus,
                ReplayStatus: replayStatus,
                ValidationStatus: validationStatus,
                PacketId: null,
                ReceiptPath: null,
                RejectionReason: reason,
                ProcessedAtUtc: processedAtUtc));
            _store.PersistLocked();
        }

        return new SubscribrWebhookResult(
            EventId: eventId,
            Status: "rejected",
            SignatureStatus: signatureStatus,
            ReplayStatus: replayStatus,
            ValidationStatus: validationStatus,
            PacketId: null,
            ReceiptPath: null,
            RejectionReason: reason,
            ProcessedAtUtc: processedAtUtc);
    }

    private string BuildReceiptPath(string eventId)
    {
        string token = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(eventId))).ToLowerInvariant();
        return Path.Combine(_store.ReceiptRoot, $"{token}.generated.json");
    }

    private string ResolveAllowedSourcePath(string? rawPath, string fieldName)
    {
        string candidate = Clean(rawPath);
        if (string.IsNullOrWhiteSpace(candidate))
        {
            throw new InvalidDataException($"{fieldName} is required");
        }

        if (!Path.IsPathFullyQualified(candidate))
        {
            throw new InvalidDataException($"{fieldName} must be an absolute path");
        }

        string fullPath = Path.GetFullPath(candidate);
        if (!_allowedSourceRoots.Any(root => IsPathWithinRoot(fullPath, root)))
        {
            throw new InvalidDataException($"{fieldName} must stay within configured allowed source roots");
        }

        if (!File.Exists(fullPath))
        {
            throw new InvalidDataException($"{fieldName} must exist");
        }

        return fullPath;
    }

    private static bool IsPathWithinRoot(string candidatePath, string rootPath)
    {
        string normalizedRoot = Path.TrimEndingDirectorySeparator(rootPath);
        if (string.Equals(candidatePath, normalizedRoot, PathComparison))
        {
            return true;
        }

        return candidatePath.StartsWith(normalizedRoot + Path.DirectorySeparatorChar, PathComparison);
    }

    private bool VerifySignature(string canonicalPayload, string? signature, string? timestamp)
    {
        if (string.IsNullOrWhiteSpace(signature) || string.IsNullOrWhiteSpace(timestamp))
        {
            return false;
        }

        string material = SignatureMaterial(canonicalPayload, timestamp);
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(GetWebhookSecret()));
        string expected = $"sha256={Convert.ToHexString(hmac.ComputeHash(Encoding.UTF8.GetBytes(material))).ToLowerInvariant()}";
        byte[] expectedBytes = Encoding.UTF8.GetBytes(expected);
        byte[] providedBytes = Encoding.UTF8.GetBytes(signature.Trim());
        return expectedBytes.Length == providedBytes.Length
            && CryptographicOperations.FixedTimeEquals(expectedBytes, providedBytes);
    }

    private static bool TryParseTimestamp(string? timestamp, out DateTimeOffset parsed)
    {
        string cleaned = Clean(timestamp);
        if (DateTimeOffset.TryParse(cleaned, out parsed))
        {
            parsed = parsed.ToUniversalTime();
            return true;
        }

        parsed = default;
        return false;
    }

    private string GetWebhookSecret()
        => _configuration["SUBSCRIBR_WEBHOOK_SECRET"]
            ?? _configuration["Subscribr:WebhookSecret"]
            ?? throw new InvalidOperationException("SUBSCRIBR_WEBHOOK_SECRET must be configured; webhook secrets are not committed.");

    private static string[] ResolveAllowedSourceRoots(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_SUBSCRIBR_WEBHOOK_ALLOWED_SOURCE_ROOTS"]
            ?? configuration["Subscribr:WebhookAllowedSourceRoots"];
        if (string.IsNullOrWhiteSpace(configured))
        {
            throw new InvalidOperationException(
                "CHUMMER_SUBSCRIBR_WEBHOOK_ALLOWED_SOURCE_ROOTS must be configured; webhook source paths may not read arbitrary files.");
        }

        var comparer = OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal;
        string[] roots = configured
            .Split([',', ';', '\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(Path.GetFullPath)
            .Distinct(comparer)
            .ToArray();
        if (roots.Length == 0)
        {
            throw new InvalidOperationException(
                "CHUMMER_SUBSCRIBR_WEBHOOK_ALLOWED_SOURCE_ROOTS must include at least one readable root.");
        }

        return roots;
    }

    private bool IsWebhookLaneEnabled()
        => ReadBoolean("CHUMMER_SUBSCRIBR_ENABLED", "Subscribr:Enabled", defaultValue: false)
           && ReadBoolean("CHUMMER_SUBSCRIBR_WEBHOOKS_ENABLED", "Subscribr:WebhooksEnabled", defaultValue: false);

    private bool ReadBoolean(string envKey, string configKey, bool defaultValue)
    {
        string? configured = _configuration[envKey] ?? _configuration[configKey];
        return bool.TryParse(configured, out bool parsed) ? parsed : defaultValue;
    }

    private static string SignatureMaterial(string canonicalPayload, string timestamp)
        => $"{timestamp.Trim()}\n{canonicalPayload}";

    private static string Clean(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim();

    private static string Sha256File(string path)
    {
        using FileStream stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static JsonObject LoadPacket(string path)
        => JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8))?.AsObject()
            ?? throw new InvalidOperationException($"Unable to parse packet JSON: {path}");
}
