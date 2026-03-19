using System.Net;
using System.Net.Mail;
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

    public IdentityEmailDeliveryService(IConfiguration configuration, ILogger<IdentityEmailDeliveryService> logger)
    {
        _configuration = configuration;
        _logger = logger ?? NullLogger<IdentityEmailDeliveryService>.Instance;
    }

    public IdentityEmailDeliveryResult DeliverMagicLink(string email, string displayName, string ticketId, string? nextPath, DateTimeOffset expiresAtUtc)
    {
        var host = _configuration["IDENTITY_SMTP_HOST"]?.Trim();
        var fromEmail = _configuration["IDENTITY_SMTP_FROM_EMAIL"]?.Trim();
        if (string.IsNullOrWhiteSpace(host) || string.IsNullOrWhiteSpace(fromEmail))
        {
            return new IdentityEmailDeliveryResult(
                DeliveryMode: "preview_inline_link",
                PreviewNote: "Transactional email is not configured in this build, so the callback link is shown directly after submit.",
                Delivered: false);
        }

        var callbackUrl = BuildCallbackUrl(ticketId, nextPath);
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
            return new IdentityEmailDeliveryResult(
                DeliveryMode: "smtp_magic_link",
                PreviewNote: $"A sign-in link was sent to {email}.",
                Delivered: true);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to deliver Chummer sign-in link to {Email} via SMTP host {Host}:{Port}.", email, host, port);
            return new IdentityEmailDeliveryResult(
                DeliveryMode: "preview_inline_link",
                PreviewNote: "Email delivery failed on this host, so the preview callback link is shown directly for recovery.",
                Delivered: false);
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

    private static int ResolvePort(string? configured)
        => int.TryParse(configured, out var port) && port > 0 ? port : 587;

    private static bool ResolveBool(string? configured, bool defaultValue)
        => bool.TryParse(configured, out var value) ? value : defaultValue;
}
