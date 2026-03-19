using System.Net.Http.Headers;
using System.Net;
using System.Net.Mail;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Identity.Services;

public interface IIdentityEmailDeliveryService
{
    IdentityEmailDeliveryResult DeliverMagicLink(string email, string displayName, string ticketId, string? nextPath, DateTimeOffset expiresAtUtc);
}

public sealed record IdentityEmailDeliveryResult(
    string DeliveryMode,
    string PreviewNote,
    bool Delivered);

public sealed class IdentityEmailDeliveryService : IIdentityEmailDeliveryService
{
    private readonly IConfiguration _configuration;
    private readonly ILogger<IdentityEmailDeliveryService> _logger;
    private readonly HttpClient _httpClient;

    public IdentityEmailDeliveryService(IConfiguration configuration, ILogger<IdentityEmailDeliveryService> logger)
        : this(configuration, logger, new HttpClient())
    {
    }

    public IdentityEmailDeliveryService(IConfiguration configuration, ILogger<IdentityEmailDeliveryService> logger, HttpClient httpClient)
    {
        _configuration = configuration;
        _logger = logger ?? NullLogger<IdentityEmailDeliveryService>.Instance;
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
    }

    public IdentityEmailDeliveryResult DeliverMagicLink(string email, string displayName, string ticketId, string? nextPath, DateTimeOffset expiresAtUtc)
    {
        var callbackUrl = BuildCallbackUrl(ticketId, nextPath);
        var fromEmail = ResolveFromEmail();
        if (TryDeliverViaEmailit(email, displayName, callbackUrl, ticketId, nextPath, expiresAtUtc, fromEmail, out var emailitResult))
        {
            return emailitResult;
        }

        if (TryDeliverViaSmtp(email, displayName, callbackUrl, expiresAtUtc, fromEmail, out var smtpResult))
        {
            return smtpResult;
        }

        var emailitConfigured = !string.IsNullOrWhiteSpace(_configuration["IDENTITY_EMAILIT_API_KEY"]?.Trim());
        var smtpConfigured = !string.IsNullOrWhiteSpace(_configuration["IDENTITY_SMTP_HOST"]?.Trim()) && !string.IsNullOrWhiteSpace(fromEmail);
        if (!emailitConfigured && !smtpConfigured)
        {
            return new IdentityEmailDeliveryResult(
                DeliveryMode: "preview_inline_link",
                PreviewNote: "Transactional email is not configured in this build, so the callback link is shown directly after submit.",
                Delivered: false);
        }

        return new IdentityEmailDeliveryResult(
            DeliveryMode: "preview_inline_link",
            PreviewNote: "Email delivery failed on this host, so the preview callback link is shown directly for recovery.",
            Delivered: false);
    }

    private bool TryDeliverViaEmailit(
        string email,
        string displayName,
        string callbackUrl,
        string ticketId,
        string? nextPath,
        DateTimeOffset expiresAtUtc,
        string? fromEmail,
        out IdentityEmailDeliveryResult result)
    {
        var apiKey = _configuration["IDENTITY_EMAILIT_API_KEY"]?.Trim();
        if (string.IsNullOrWhiteSpace(apiKey) || string.IsNullOrWhiteSpace(fromEmail))
        {
            result = default!;
            return false;
        }

        var fromName = _configuration["IDENTITY_SMTP_FROM_NAME"]?.Trim();
        var emailitFromName = _configuration["IDENTITY_EMAILIT_FROM_NAME"]?.Trim();
        var sender = FormatMailbox(fromEmail, emailitFromName ?? fromName);
        var payload = new EmailitSendEmailRequest(
            sender,
            email,
            "Your Chummer sign-in link",
            BuildTextBody(displayName, callbackUrl, expiresAtUtc),
            BuildHtmlBody(displayName, callbackUrl, expiresAtUtc),
            false,
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["purpose"] = "magic_link",
                ["ticket_id"] = ticketId,
                ["next_path"] = string.IsNullOrWhiteSpace(nextPath) ? "/home" : nextPath.Trim()
            });

        try
        {
            var baseUrl = (_configuration["IDENTITY_EMAILIT_BASE_URL"] ?? "https://api.emailit.com/v2").Trim().TrimEnd('/');
            using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/emails");
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
            request.Headers.Add("Idempotency-Key", BuildIdempotencyKey(ticketId));
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            request.Content = new StringContent(
                JsonSerializer.Serialize(payload, JsonOptions),
                Encoding.UTF8,
                "application/json");

            using var response = _httpClient.SendAsync(request).GetAwaiter().GetResult();
            var body = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
            if (!response.IsSuccessStatusCode)
            {
                throw new InvalidOperationException($"Emailit returned {(int)response.StatusCode}: {body}");
            }

            _logger.LogInformation("Delivered Chummer sign-in link to {Email} via Emailit API.", email);
            result = new IdentityEmailDeliveryResult(
                DeliveryMode: "emailit_api_magic_link",
                PreviewNote: $"A sign-in link was sent to {email}.",
                Delivered: true);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to deliver Chummer sign-in link to {Email} via Emailit API.", email);
            result = default!;
            return false;
        }
    }

    private bool TryDeliverViaSmtp(
        string email,
        string displayName,
        string callbackUrl,
        DateTimeOffset expiresAtUtc,
        string? fromEmail,
        out IdentityEmailDeliveryResult result)
    {
        var host = _configuration["IDENTITY_SMTP_HOST"]?.Trim();
        if (string.IsNullOrWhiteSpace(host) || string.IsNullOrWhiteSpace(fromEmail))
        {
            result = default!;
            return false;
        }

        var fromName = _configuration["IDENTITY_SMTP_FROM_NAME"]?.Trim();
        var port = ResolvePort(_configuration["IDENTITY_SMTP_PORT"]);
        var username = _configuration["IDENTITY_SMTP_USERNAME"]?.Trim();
        var password = _configuration["IDENTITY_SMTP_PASSWORD"];
        var enableSsl = ResolveBool(_configuration["IDENTITY_SMTP_USE_SSL"], defaultValue: true);

        using var message = new MailMessage
        {
            From = string.IsNullOrWhiteSpace(fromName)
                ? new MailAddress(fromEmail)
                : new MailAddress(fromEmail, fromName),
            Subject = "Your Chummer sign-in link",
            Body = BuildTextBody(displayName, callbackUrl, expiresAtUtc),
            IsBodyHtml = false
        };
        message.To.Add(new MailAddress(email, displayName));

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

            client.Send(message);
            _logger.LogInformation("Delivered Chummer sign-in link to {Email} via SMTP host {Host}:{Port}.", email, host, port);
            result = new IdentityEmailDeliveryResult(
                DeliveryMode: "smtp_magic_link",
                PreviewNote: $"A sign-in link was sent to {email}.",
                Delivered: true);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to deliver Chummer sign-in link to {Email} via SMTP host {Host}:{Port}.", email, host, port);
            result = default!;
            return false;
        }
    }

    private string BuildCallbackUrl(string ticketId, string? nextPath)
    {
        var baseUrl = (_configuration["IDENTITY_PUBLIC_BASE_URL"] ?? "https://chummer.run").Trim().TrimEnd('/');
        var next = string.IsNullOrWhiteSpace(nextPath) ? "/home" : nextPath.Trim();
        return $"{baseUrl}/auth/email/callback?ticket={WebUtility.UrlEncode(ticketId)}&next={WebUtility.UrlEncode(next)}";
    }

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

    private string? ResolveFromEmail()
        => _configuration["IDENTITY_EMAILIT_FROM_EMAIL"]?.Trim()
           ?? _configuration["IDENTITY_SMTP_FROM_EMAIL"]?.Trim();

    private static string FormatMailbox(string email, string? name)
        => string.IsNullOrWhiteSpace(name)
            ? email.Trim()
            : $"{name.Trim()} <{email.Trim()}>";

    private static string BuildIdempotencyKey(string ticketId)
    {
        var sanitized = new string(ticketId.Where(static ch => char.IsLetterOrDigit(ch) || ch == '-' || ch == '_').ToArray());
        if (string.IsNullOrWhiteSpace(sanitized))
        {
            sanitized = Guid.NewGuid().ToString("N");
        }

        return $"magic-link-{sanitized[..Math.Min(sanitized.Length, 220)]}";
    }

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };

    private static int ResolvePort(string? configured)
        => int.TryParse(configured, out var port) && port > 0 ? port : 587;

    private static bool ResolveBool(string? configured, bool defaultValue)
        => bool.TryParse(configured, out var value) ? value : defaultValue;

    private sealed record EmailitSendEmailRequest(
        string From,
        string To,
        string Subject,
        string Text,
        string Html,
        bool Tracking,
        Dictionary<string, string> Meta);
}
