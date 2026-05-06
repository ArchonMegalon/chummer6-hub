using System.Net;
using System.Net.Http.Headers;
using System.Net.Mail;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Contracts.Identity;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Identity.Services;

public interface IIdentityEmailDeliveryService
{
    IdentityEmailDeliveryResult DeliverMagicLink(string email, string displayName, string ticketId, string? nextPath, DateTimeOffset expiresAtUtc);
    IdentityEmailDeliveryStatusResponse GetStatus();
    IdentityEmailWebhookAckResponse RecordEmailitWebhook(JsonElement payload);
}

public sealed record IdentityEmailDeliveryResult(
    string DeliveryMode,
    string PreviewNote,
    bool Delivered,
    string? ProviderMessageId = null);

public sealed class IdentityEmailDeliveryService : IIdentityEmailDeliveryService
{
    private sealed record IdentityEmailMessage(
        string EmailKind,
        string RecipientEmail,
        string RecipientName,
        string FromEmail,
        string? FromName,
        string? ReplyTo,
        string Subject,
        string TextBody,
        string HtmlBody,
        string IdempotencyKey,
        IReadOnlyDictionary<string, string> Meta);

    private sealed record IdentityEmailTransportResult(
        string TransportKey,
        string DeliveryMode,
        bool Delivered,
        string PreviewNote,
        string Status,
        string? ProviderMessageId = null,
        string? FailureReason = null,
        bool Configured = false);

    private interface IIdentityEmailTransport
    {
        string TransportKey { get; }
        IdentityEmailTransportResult Send(IdentityEmailMessage message);
    }

    private sealed class EmailitApiIdentityEmailTransport : IIdentityEmailTransport
    {
        private readonly IConfiguration _configuration;
        private readonly ILogger _logger;
        private readonly HttpClient _httpClient;

        public EmailitApiIdentityEmailTransport(IConfiguration configuration, ILogger logger, HttpClient httpClient)
        {
            _configuration = configuration;
            _logger = logger;
            _httpClient = httpClient;
        }

        public string TransportKey => "emailit_api";

        public IdentityEmailTransportResult Send(IdentityEmailMessage message)
        {
            var apiKey = _configuration["IDENTITY_EMAILIT_API_KEY"]?.Trim();
            if (string.IsNullOrWhiteSpace(apiKey) || string.IsNullOrWhiteSpace(message.FromEmail))
            {
                return new IdentityEmailTransportResult(
                    TransportKey,
                    "emailit_api_unconfigured",
                    Delivered: false,
                    PreviewNote: "Emailit API is not configured on this host.",
                    Status: "not_configured",
                    Configured: false);
            }

            var payload = new EmailitSendEmailRequest(
                From: FormatMailbox(message.FromEmail, message.FromName),
                To: message.RecipientEmail,
                Subject: message.Subject,
                Text: message.TextBody,
                Html: message.HtmlBody,
                Tracking: false,
                ReplyTo: string.IsNullOrWhiteSpace(message.ReplyTo) ? null : message.ReplyTo.Trim(),
                Meta: new Dictionary<string, string>(message.Meta, StringComparer.Ordinal));

            try
            {
                var baseUrl = (_configuration["IDENTITY_EMAILIT_BASE_URL"] ?? "https://api.emailit.com/v2").Trim().TrimEnd('/');
                using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/emails");
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
                request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
                request.Headers.Add("Idempotency-Key", message.IdempotencyKey);
                request.Content = new StringContent(
                    JsonSerializer.Serialize(payload, JsonOptions),
                    Encoding.UTF8,
                    "application/json");

                using var response = _httpClient.SendAsync(request).GetAwaiter().GetResult();
                var body = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                if (!response.IsSuccessStatusCode)
                {
                    return new IdentityEmailTransportResult(
                        TransportKey,
                        "emailit_api_failed",
                        Delivered: false,
                        PreviewNote: "Emailit could not accept the message on this host.",
                        Status: "failed",
                        FailureReason: $"Emailit returned {(int)response.StatusCode}: {body}",
                        Configured: true);
                }

                var providerMessageId = ExtractProviderMessageId(body);
                _logger.LogInformation("Delivered Chummer sign-in link to {Email} via Emailit API.", message.RecipientEmail);
                return new IdentityEmailTransportResult(
                    TransportKey,
                    $"emailit_api_{message.EmailKind}",
                    Delivered: true,
                    PreviewNote: $"A sign-in link was sent to {message.RecipientEmail}.",
                    Status: "accepted",
                    ProviderMessageId: providerMessageId,
                    Configured: true);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to deliver Chummer sign-in link to {Email} via Emailit API.", message.RecipientEmail);
                return new IdentityEmailTransportResult(
                    TransportKey,
                    "emailit_api_failed",
                    Delivered: false,
                    PreviewNote: "Emailit delivery failed on this host.",
                    Status: "failed",
                    FailureReason: ex.Message,
                    Configured: true);
            }
        }
    }

    private sealed class SmtpIdentityEmailTransport : IIdentityEmailTransport
    {
        private readonly IConfiguration _configuration;
        private readonly ILogger _logger;

        public SmtpIdentityEmailTransport(IConfiguration configuration, ILogger logger)
        {
            _configuration = configuration;
            _logger = logger;
        }

        public string TransportKey => "smtp";

        public IdentityEmailTransportResult Send(IdentityEmailMessage message)
        {
            var host = _configuration["IDENTITY_SMTP_HOST"]?.Trim();
            if (string.IsNullOrWhiteSpace(host) || string.IsNullOrWhiteSpace(message.FromEmail))
            {
                return new IdentityEmailTransportResult(
                    TransportKey,
                    "smtp_unconfigured",
                    Delivered: false,
                    PreviewNote: "SMTP is not configured on this host.",
                    Status: "not_configured",
                    Configured: false);
            }

            var port = ResolvePort(_configuration["IDENTITY_SMTP_PORT"]);
            var username = _configuration["IDENTITY_SMTP_USERNAME"]?.Trim();
            var password = _configuration["IDENTITY_SMTP_PASSWORD"];
            var enableSsl = ResolveBool(_configuration["IDENTITY_SMTP_USE_SSL"], defaultValue: true);

            using var messageBody = new MailMessage
            {
                From = string.IsNullOrWhiteSpace(message.FromName)
                    ? new MailAddress(message.FromEmail)
                    : new MailAddress(message.FromEmail, message.FromName),
                Subject = message.Subject,
                Body = message.TextBody,
                IsBodyHtml = false
            };
            messageBody.To.Add(new MailAddress(message.RecipientEmail, message.RecipientName));
            if (!string.IsNullOrWhiteSpace(message.ReplyTo))
            {
                messageBody.ReplyToList.Add(new MailAddress(message.ReplyTo));
            }

            try
            {
                using var client = new SmtpClient(host, port)
                {
                    EnableSsl = enableSsl,
                    DeliveryMethod = SmtpDeliveryMethod.Network
                };

                if (!string.IsNullOrWhiteSpace(username))
                {
                    client.Credentials = new NetworkCredential(username, password ?? string.Empty);
                }
                else
                {
                    client.UseDefaultCredentials = false;
                }

                client.Send(messageBody);
                _logger.LogInformation("Delivered Chummer sign-in link to {Email} via SMTP host {Host}:{Port}.", message.RecipientEmail, host, port);
                return new IdentityEmailTransportResult(
                    TransportKey,
                    $"smtp_{message.EmailKind}",
                    Delivered: true,
                    PreviewNote: $"A sign-in link was sent to {message.RecipientEmail}.",
                    Status: "accepted",
                    Configured: true);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to deliver Chummer sign-in link to {Email} via SMTP host {Host}:{Port}.", message.RecipientEmail, host, port);
                return new IdentityEmailTransportResult(
                    TransportKey,
                    "smtp_failed",
                    Delivered: false,
                    PreviewNote: "SMTP delivery failed on this host.",
                    Status: "failed",
                    FailureReason: ex.Message,
                    Configured: true);
            }
        }
    }

    private sealed record EmailDeliveryEventState(
        string DeliveryId,
        string EmailKind,
        string TransportKey,
        string DeliveryMode,
        string Status,
        bool Delivered,
        string RecipientEmail,
        string? ProviderMessageId,
        string? FailureReason,
        DateTimeOffset OccurredAtUtc);

    private sealed record RecipientState(
        string Email,
        string State,
        string? LastEvent,
        DateTimeOffset? LastEventAtUtc,
        string? Provider,
        string? ProviderDetail);

    private sealed record DeliverySnapshot(
        IReadOnlyList<EmailDeliveryEventState> Deliveries,
        IReadOnlyList<RecipientState> Recipients,
        IReadOnlyDictionary<string, string> ProviderMessageRecipients);

    private readonly IConfiguration _configuration;
    private readonly ILogger<IdentityEmailDeliveryService> _logger;
    private readonly HttpClient _httpClient;
    private readonly object _mutate = new();
    private readonly string _storagePath;
    private readonly Dictionary<string, RecipientState> _recipientStates = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<EmailDeliveryEventState> _recentDeliveries = new();
    private readonly Dictionary<string, string> _providerMessageRecipients = new(StringComparer.OrdinalIgnoreCase);

    public IdentityEmailDeliveryService(IConfiguration configuration, ILogger<IdentityEmailDeliveryService> logger)
        : this(configuration, logger, new HttpClient())
    {
    }

    public IdentityEmailDeliveryService(IConfiguration configuration, ILogger<IdentityEmailDeliveryService> logger, HttpClient httpClient)
    {
        _configuration = configuration;
        _logger = logger ?? NullLogger<IdentityEmailDeliveryService>.Instance;
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
        _storagePath = ResolveStoragePath(configuration);
        LoadSnapshot();
    }

    public IdentityEmailDeliveryResult DeliverMagicLink(string email, string displayName, string ticketId, string? nextPath, DateTimeOffset expiresAtUtc)
    {
        var normalizedEmail = email.Trim().ToLowerInvariant();
        var message = BuildMagicLinkMessage(normalizedEmail, displayName, ticketId, nextPath, expiresAtUtc);
        foreach (var transport in CreateTransportOrder())
        {
            var result = transport.Send(message);
            if (!result.Configured)
            {
                continue;
            }

            RecordTransportResult(message, result);
            if (result.Delivered)
            {
                return new IdentityEmailDeliveryResult(
                    result.DeliveryMode,
                    result.PreviewNote,
                    Delivered: true,
                    ProviderMessageId: result.ProviderMessageId);
            }
        }

        var previewNote = AnyRealTransportConfigured()
            ? "Email delivery failed on this host, so the preview callback link is shown directly for recovery."
            : "Transactional email is not configured in this build, so the callback link is shown directly after submit.";
        RecordPreviewFallback(message, previewNote);
        return new IdentityEmailDeliveryResult(
            DeliveryMode: "preview_inline_link",
            PreviewNote: previewNote,
            Delivered: false);
    }

    public IdentityEmailDeliveryStatusResponse GetStatus()
    {
        lock (_mutate)
        {
            return new IdentityEmailDeliveryStatusResponse(
                RecentDeliveries: _recentDeliveries
                    .OrderByDescending(static item => item.OccurredAtUtc)
                    .Take(40)
                    .Select(static item => new IdentityEmailDeliveryEventResponse(
                        item.DeliveryId,
                        item.EmailKind,
                        item.TransportKey,
                        item.DeliveryMode,
                        item.Status,
                        item.Delivered,
                        item.RecipientEmail,
                        item.ProviderMessageId,
                        item.FailureReason,
                        item.OccurredAtUtc))
                    .ToList(),
                Recipients: _recipientStates.Values
                    .OrderBy(static item => item.Email, StringComparer.OrdinalIgnoreCase)
                    .Select(static item => new IdentityEmailRecipientStateResponse(
                        item.Email,
                        item.State,
                        item.LastEvent,
                        item.LastEventAtUtc,
                        item.Provider,
                        item.ProviderDetail))
                    .ToList(),
                GeneratedAtUtc: DateTimeOffset.UtcNow);
        }
    }

    public IdentityEmailWebhookAckResponse RecordEmailitWebhook(JsonElement payload)
    {
        var eventType = TryReadString(payload, "type")
            ?? TryReadString(payload, "event")
            ?? "unknown";
        var envelope = ExtractWebhookEnvelope(payload);
        var providerMessageId = TryReadString(envelope, "id") ?? TryReadString(payload, "id");
        var recipient = NormalizeWebhookRecipient(envelope) ?? NormalizeWebhookRecipient(payload);
        var receivedAtUtc = DateTimeOffset.UtcNow;
        var providerOccurredAtUtc = TryReadDateTimeOffset(envelope, "created_at")
            ?? TryReadDateTimeOffset(payload, "created_at");
        var status = NormalizeEventStatus(eventType);

        lock (_mutate)
        {
            if (!string.IsNullOrWhiteSpace(providerMessageId) && !string.IsNullOrWhiteSpace(recipient))
            {
                _providerMessageRecipients[providerMessageId] = recipient;
            }
            else if (!string.IsNullOrWhiteSpace(providerMessageId) && _providerMessageRecipients.TryGetValue(providerMessageId, out var knownRecipient))
            {
                recipient = knownRecipient;
            }

            if (!string.IsNullOrWhiteSpace(recipient))
            {
                _recipientStates[recipient] = new RecipientState(
                    Email: recipient,
                    State: status,
                    LastEvent: eventType,
                    LastEventAtUtc: receivedAtUtc,
                    Provider: "emailit_api",
                    ProviderDetail: providerMessageId);
            }

            _recentDeliveries.Add(new EmailDeliveryEventState(
                DeliveryId: $"evt_{Guid.NewGuid():N}",
                EmailKind: "webhook",
                TransportKey: "emailit_api",
                DeliveryMode: "emailit_webhook",
                Status: status,
                Delivered: string.Equals(status, "delivered", StringComparison.OrdinalIgnoreCase),
                RecipientEmail: recipient ?? "(unknown)",
                ProviderMessageId: providerMessageId,
                FailureReason: providerOccurredAtUtc is null ? null : $"provider_occurred_at={providerOccurredAtUtc.Value:O}",
                OccurredAtUtc: receivedAtUtc));
            TrimRecentDeliveries();
            PersistLocked();
        }

        return new IdentityEmailWebhookAckResponse(
            Provider: "emailit_api",
            Status: status,
            RecordedEvents: 1,
            ReceivedAtUtc: receivedAtUtc);
    }

    private IdentityEmailMessage BuildMagicLinkMessage(string email, string displayName, string ticketId, string? nextPath, DateTimeOffset expiresAtUtc)
    {
        var callbackUrl = BuildCallbackUrl(ticketId, nextPath);
        var fromEmail = ResolveFromEmail();
        if (string.IsNullOrWhiteSpace(fromEmail))
        {
            fromEmail = "concierge@chummer.run";
        }

        return new IdentityEmailMessage(
            EmailKind: "magic_link",
            RecipientEmail: email,
            RecipientName: displayName,
            FromEmail: fromEmail,
            FromName: ResolveFromName(),
            ReplyTo: _configuration["IDENTITY_EMAIL_REPLY_TO"]?.Trim(),
            Subject: "Your Chummer sign-in link",
            TextBody: BuildTextBody(displayName, callbackUrl, expiresAtUtc),
            HtmlBody: BuildHtmlBody(displayName, callbackUrl, expiresAtUtc),
            IdempotencyKey: BuildIdempotencyKey(ticketId),
            Meta: new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["purpose"] = "magic_link",
                ["ticket_id"] = ticketId,
                ["next_path"] = string.IsNullOrWhiteSpace(nextPath) ? "/home" : nextPath.Trim()
            });
    }

    private IEnumerable<IIdentityEmailTransport> CreateTransportOrder()
    {
        var orderRaw = (_configuration["IDENTITY_EMAIL_PROVIDER_ORDER"] ?? "emailit_api,smtp").Trim();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var raw in orderRaw.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            if (!seen.Add(raw))
            {
                continue;
            }

            if (string.Equals(raw, "emailit_api", StringComparison.OrdinalIgnoreCase))
            {
                yield return new EmailitApiIdentityEmailTransport(_configuration, _logger, _httpClient);
            }
            else if (string.Equals(raw, "smtp", StringComparison.OrdinalIgnoreCase))
            {
                yield return new SmtpIdentityEmailTransport(_configuration, _logger);
            }
        }
    }

    private bool AnyRealTransportConfigured()
        => !string.IsNullOrWhiteSpace(_configuration["IDENTITY_EMAILIT_API_KEY"]?.Trim())
           || !string.IsNullOrWhiteSpace(_configuration["IDENTITY_SMTP_HOST"]?.Trim());

    private void RecordTransportResult(IdentityEmailMessage message, IdentityEmailTransportResult result)
    {
        lock (_mutate)
        {
            if (!string.IsNullOrWhiteSpace(result.ProviderMessageId))
            {
                _providerMessageRecipients[result.ProviderMessageId] = message.RecipientEmail;
            }

            _recentDeliveries.Add(new EmailDeliveryEventState(
                DeliveryId: $"dly_{Guid.NewGuid():N}",
                EmailKind: message.EmailKind,
                TransportKey: result.TransportKey,
                DeliveryMode: result.DeliveryMode,
                Status: result.Status,
                Delivered: result.Delivered,
                RecipientEmail: message.RecipientEmail,
                ProviderMessageId: result.ProviderMessageId,
                FailureReason: result.FailureReason,
                OccurredAtUtc: DateTimeOffset.UtcNow));

            _recipientStates[message.RecipientEmail] = new RecipientState(
                Email: message.RecipientEmail,
                State: result.Delivered ? "active" : "failed",
                LastEvent: result.Status,
                LastEventAtUtc: DateTimeOffset.UtcNow,
                Provider: result.TransportKey,
                ProviderDetail: result.ProviderMessageId ?? result.FailureReason);

            TrimRecentDeliveries();
            PersistLocked();
        }
    }

    private void RecordPreviewFallback(IdentityEmailMessage message, string previewNote)
    {
        lock (_mutate)
        {
            _recentDeliveries.Add(new EmailDeliveryEventState(
                DeliveryId: $"dly_{Guid.NewGuid():N}",
                EmailKind: message.EmailKind,
                TransportKey: "preview",
                DeliveryMode: "preview_inline_link",
                Status: "preview",
                Delivered: false,
                RecipientEmail: message.RecipientEmail,
                ProviderMessageId: null,
                FailureReason: previewNote,
                OccurredAtUtc: DateTimeOffset.UtcNow));
            TrimRecentDeliveries();
            PersistLocked();
        }
    }

    private void TrimRecentDeliveries()
    {
        const int maxEvents = 100;
        if (_recentDeliveries.Count <= maxEvents)
        {
            return;
        }

        _recentDeliveries.RemoveRange(0, _recentDeliveries.Count - maxEvents);
    }

    private void LoadSnapshot()
    {
        try
        {
            if (!File.Exists(_storagePath))
            {
                return;
            }

            var raw = File.ReadAllText(_storagePath, Encoding.UTF8);
            if (string.IsNullOrWhiteSpace(raw))
            {
                return;
            }

            var snapshot = JsonSerializer.Deserialize<DeliverySnapshot>(raw, JsonOptions);
            if (snapshot is null)
            {
                return;
            }

            lock (_mutate)
            {
                _recentDeliveries.Clear();
                _recentDeliveries.AddRange(snapshot.Deliveries ?? Array.Empty<EmailDeliveryEventState>());
                _recipientStates.Clear();
                foreach (var state in snapshot.Recipients ?? Array.Empty<RecipientState>())
                {
                    _recipientStates[state.Email] = state;
                }

                _providerMessageRecipients.Clear();
                foreach (var pair in snapshot.ProviderMessageRecipients ?? new Dictionary<string, string>())
                {
                    _providerMessageRecipients[pair.Key] = pair.Value;
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to load identity email delivery snapshot from {Path}.", _storagePath);
        }
    }

    private void PersistLocked()
    {
        try
        {
            var directory = Path.GetDirectoryName(_storagePath);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            var snapshot = new DeliverySnapshot(
                Deliveries: _recentDeliveries.ToList(),
                Recipients: _recipientStates.Values.ToList(),
                ProviderMessageRecipients: new Dictionary<string, string>(_providerMessageRecipients, StringComparer.OrdinalIgnoreCase));
            File.WriteAllText(_storagePath, JsonSerializer.Serialize(snapshot, JsonOptions), Encoding.UTF8);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to persist identity email delivery snapshot to {Path}.", _storagePath);
        }
    }

    private string BuildCallbackUrl(string ticketId, string? nextPath)
    {
        var baseUrl = (_configuration["IDENTITY_PUBLIC_BASE_URL"] ?? "https://chummer.run").Trim().TrimEnd('/');
        var next = string.IsNullOrWhiteSpace(nextPath) ? "/home" : nextPath.Trim();
        return $"{baseUrl}/auth/email/callback?ticket={WebUtility.UrlEncode(ticketId)}&next={WebUtility.UrlEncode(next)}";
    }

    private string? ResolveFromEmail()
        => _configuration["IDENTITY_EMAILIT_FROM_EMAIL"]?.Trim()
           ?? _configuration["IDENTITY_SMTP_FROM_EMAIL"]?.Trim();

    private string? ResolveFromName()
        => _configuration["IDENTITY_EMAILIT_FROM_NAME"]?.Trim()
           ?? _configuration["IDENTITY_SMTP_FROM_NAME"]?.Trim();

    private static string BuildTextBody(string displayName, string callbackUrl, DateTimeOffset expiresAtUtc)
        => $"""
Hello {displayName},

Use this sign-in link to enter Chummer:
{callbackUrl}

This link expires at {expiresAtUtc:u}.

If you did not request this, you can ignore this email.
""";

    private static string BuildHtmlBody(string displayName, string callbackUrl, DateTimeOffset expiresAtUtc)
        => $"""
<!doctype html>
<html>
  <body style="font-family: Arial, sans-serif; color: #101828; line-height: 1.5;">
    <p>Hello {WebUtility.HtmlEncode(displayName)},</p>
    <p>Use this sign-in link to enter Chummer.</p>
    <p><a href="{WebUtility.HtmlEncode(callbackUrl)}" style="display: inline-block; background: #0f766e; color: #ffffff; padding: 12px 18px; text-decoration: none; border-radius: 8px;">Open Chummer</a></p>
    <p>If the button does not work, use this link directly:<br /><a href="{WebUtility.HtmlEncode(callbackUrl)}">{WebUtility.HtmlEncode(callbackUrl)}</a></p>
    <p>This link expires at {expiresAtUtc:u}.</p>
    <p>If you did not request this, you can ignore this email.</p>
  </body>
</html>
""";

    private static string BuildIdempotencyKey(string ticketId)
    {
        var sanitized = new string(ticketId.Where(static ch => char.IsLetterOrDigit(ch) || ch == '-' || ch == '_').ToArray());
        if (string.IsNullOrWhiteSpace(sanitized))
        {
            sanitized = Guid.NewGuid().ToString("N");
        }

        return $"email_magic_link_{sanitized[..Math.Min(sanitized.Length, 220)]}";
    }

    private static string? ExtractProviderMessageId(string responseBody)
    {
        if (string.IsNullOrWhiteSpace(responseBody))
        {
            return null;
        }

        try
        {
            using var json = JsonDocument.Parse(responseBody);
            if (json.RootElement.TryGetProperty("data", out var data) && data.ValueKind == JsonValueKind.Object)
            {
                return TryReadString(data, "id");
            }

            return TryReadString(json.RootElement, "id");
        }
        catch
        {
            return null;
        }
    }

    private static string NormalizeEventStatus(string eventType)
    {
        var lowered = (eventType ?? string.Empty).Trim().ToLowerInvariant();
        if (lowered.Contains("delivered", StringComparison.Ordinal))
        {
            return "delivered";
        }
        if (lowered.Contains("accepted", StringComparison.Ordinal))
        {
            return "accepted";
        }
        if (lowered.Contains("bounced", StringComparison.Ordinal))
        {
            return "bounced";
        }
        if (lowered.Contains("complained", StringComparison.Ordinal))
        {
            return "complained";
        }
        if (lowered.Contains("suppressed", StringComparison.Ordinal))
        {
            return "suppressed";
        }
        if (lowered.Contains("failed", StringComparison.Ordinal))
        {
            return "failed";
        }

        return string.IsNullOrWhiteSpace(lowered) ? "unknown" : lowered;
    }

    private static JsonElement ExtractWebhookEnvelope(JsonElement payload)
    {
        if (payload.TryGetProperty("data", out var dataElement) && dataElement.ValueKind == JsonValueKind.Object)
        {
            return dataElement;
        }

        if (payload.TryGetProperty("object", out var objectElement) && objectElement.ValueKind == JsonValueKind.Object)
        {
            return objectElement;
        }

        return payload;
    }

    private static string? NormalizeWebhookRecipient(JsonElement payload)
    {
        var recipient = TryReadString(payload, "to")
            ?? TryReadString(payload, "email")
            ?? TryReadString(payload, "recipient");
        if (!string.IsNullOrWhiteSpace(recipient))
        {
            return recipient.Trim().ToLowerInvariant();
        }

        if (payload.TryGetProperty("recipients", out var recipients) && recipients.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in recipients.EnumerateArray())
            {
                var value = item.ValueKind == JsonValueKind.String ? item.GetString() : TryReadString(item, "email");
                if (!string.IsNullOrWhiteSpace(value))
                {
                    return value.Trim().ToLowerInvariant();
                }
            }
        }

        if (payload.TryGetProperty("data", out var dataElement) && dataElement.ValueKind == JsonValueKind.Object)
        {
            return NormalizeWebhookRecipient(dataElement);
        }

        if (payload.TryGetProperty("object", out var objectElement) && objectElement.ValueKind == JsonValueKind.Object)
        {
            return NormalizeWebhookRecipient(objectElement);
        }

        return null;
    }

    private static string? TryReadString(JsonElement payload, string propertyName)
        => payload.TryGetProperty(propertyName, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static DateTimeOffset? TryReadDateTimeOffset(JsonElement payload, string propertyName)
    {
        if (!payload.TryGetProperty(propertyName, out var value))
        {
            return null;
        }

        if (value.ValueKind == JsonValueKind.String && DateTimeOffset.TryParse(value.GetString(), out var parsed))
        {
            return parsed;
        }

        return null;
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        var explicitPath = configuration["CHUMMER_IDENTITY_EMAIL_DELIVERY_STORE_PATH"]?.Trim();
        if (!string.IsNullOrWhiteSpace(explicitPath))
        {
            return Path.GetFullPath(explicitPath);
        }

        var identityStorePath = configuration["CHUMMER_IDENTITY_STORE_PATH"]?.Trim();
        if (!string.IsNullOrWhiteSpace(identityStorePath))
        {
            var fullIdentityStorePath = Path.GetFullPath(identityStorePath);
            var directory = Path.GetDirectoryName(fullIdentityStorePath) ?? AppContext.BaseDirectory;
            return Path.Combine(directory, "identity-email-delivery.json");
        }

        return Path.Combine(AppContext.BaseDirectory, "identity-email-delivery.json");
    }

    private static string FormatMailbox(string email, string? name)
        => string.IsNullOrWhiteSpace(name)
            ? email.Trim()
            : $"{name.Trim()} <{email.Trim()}>";

    private static int ResolvePort(string? configured)
        => int.TryParse(configured, out var port) && port > 0 ? port : 587;

    private static bool ResolveBool(string? configured, bool defaultValue)
        => bool.TryParse(configured, out var value) ? value : defaultValue;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true
    };

    private sealed record EmailitSendEmailRequest(
        string From,
        string To,
        string Subject,
        string Text,
        string Html,
        bool Tracking,
        string? ReplyTo,
        Dictionary<string, string> Meta);
}
