using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;

namespace Chummer.Run.Api.Services;

public sealed record AccountDesktopLaunchTicketClaims(
    string Kind,
    string ResourceId,
    string? UserId,
    string? SubjectId,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc);

public sealed record AccountDesktopLaunchTicketIssueResult(
    string Ticket,
    AccountDesktopLaunchTicketClaims Claims);

public sealed class AccountDesktopLaunchTicketService
{
    private const string Purpose = "chummer.run.account-desktop-launch-ticket.v1";
    private static readonly TimeSpan DefaultLifetime = TimeSpan.FromMinutes(10);
    private readonly IDataProtector _protector;
    private readonly TimeSpan _ticketLifetime;

    public AccountDesktopLaunchTicketService(
        IDataProtectionProvider dataProtectionProvider,
        IConfiguration configuration)
    {
        _protector = dataProtectionProvider.CreateProtector(Purpose);
        _ticketLifetime = ResolveTicketLifetime(configuration);
    }

    public AccountDesktopLaunchTicketIssueResult Issue(
        string kind,
        string resourceId,
        string? userId,
        string? subjectId)
    {
        string normalizedKind = NormalizeRequired(kind, nameof(kind));
        string normalizedResourceId = NormalizeRequired(resourceId, nameof(resourceId));
        string? normalizedUserId = NormalizeOptional(userId);
        string? normalizedSubjectId = NormalizeOptional(subjectId);
        if (normalizedUserId is null && normalizedSubjectId is null)
        {
            throw new ArgumentException("desktop launch ticket requires a user id or subject id.");
        }

        DateTimeOffset issuedAtUtc = DateTimeOffset.UtcNow;
        AccountDesktopLaunchTicketClaims claims = new(
            Kind: normalizedKind,
            ResourceId: normalizedResourceId,
            UserId: normalizedUserId,
            SubjectId: normalizedSubjectId,
            IssuedAtUtc: issuedAtUtc,
            ExpiresAtUtc: issuedAtUtc.Add(_ticketLifetime));

        AccountDesktopLaunchTicketPayload payload = new(
            Kind: claims.Kind,
            ResourceId: claims.ResourceId,
            UserId: claims.UserId,
            SubjectId: claims.SubjectId,
            IssuedAtUtc: claims.IssuedAtUtc,
            ExpiresAtUtc: claims.ExpiresAtUtc,
            Scope: "account_desktop_launch",
            Nonce: Guid.NewGuid().ToString("N"));

        string ticket = _protector.Protect(JsonSerializer.Serialize(payload));
        return new AccountDesktopLaunchTicketIssueResult(ticket, claims);
    }

    public bool TryValidate(string? ticket, out AccountDesktopLaunchTicketClaims? claims)
    {
        claims = null;
        if (string.IsNullOrWhiteSpace(ticket))
        {
            return false;
        }

        AccountDesktopLaunchTicketPayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<AccountDesktopLaunchTicketPayload>(_protector.Unprotect(ticket.Trim()));
        }
        catch
        {
            return false;
        }

        if (payload is null
            || !string.Equals(payload.Scope, "account_desktop_launch", StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(payload.Kind)
            || string.IsNullOrWhiteSpace(payload.ResourceId)
            || (string.IsNullOrWhiteSpace(payload.UserId) && string.IsNullOrWhiteSpace(payload.SubjectId))
            || payload.ExpiresAtUtc <= DateTimeOffset.UtcNow)
        {
            return false;
        }

        claims = new AccountDesktopLaunchTicketClaims(
            Kind: NormalizeRequired(payload.Kind, nameof(payload.Kind)),
            ResourceId: NormalizeRequired(payload.ResourceId, nameof(payload.ResourceId)),
            UserId: NormalizeOptional(payload.UserId),
            SubjectId: NormalizeOptional(payload.SubjectId),
            IssuedAtUtc: payload.IssuedAtUtc,
            ExpiresAtUtc: payload.ExpiresAtUtc);
        return true;
    }

    private static TimeSpan ResolveTicketLifetime(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_ACCOUNT_DESKTOP_LAUNCH_TICKET_LIFETIME_MINUTES"];
        if (int.TryParse(configured, out int minutes))
        {
            minutes = Math.Clamp(minutes, 2, 60);
            return TimeSpan.FromMinutes(minutes);
        }

        return DefaultLifetime;
    }

    private static string NormalizeRequired(string? value, string paramName)
        => string.IsNullOrWhiteSpace(value)
            ? throw new ArgumentException("required value missing", paramName)
            : value.Trim();

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private sealed record AccountDesktopLaunchTicketPayload(
        string Kind,
        string ResourceId,
        string? UserId,
        string? SubjectId,
        DateTimeOffset IssuedAtUtc,
        DateTimeOffset ExpiresAtUtc,
        string Scope,
        string Nonce);
}
