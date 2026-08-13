using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Services;

public enum PlayReviewAuthenticationStatus
{
    Disabled,
    Rejected,
    Throttled,
    Succeeded
}

public sealed record PlayReviewAccessPrincipal(
    string SubjectId,
    string DisplayName,
    IReadOnlyList<string> Roles);

public sealed record PlayReviewAuthenticationResult(
    PlayReviewAuthenticationStatus Status,
    PlayReviewAccessPrincipal? Principal = null,
    TimeSpan? RetryAfter = null);

/// <summary>
/// Verifies the dedicated, operator-configured credential used by Google Play reviewers.
/// The service is disabled by default and never accepts or stores a plaintext configured password.
/// </summary>
public sealed class PlayReviewAccessService
{
    private const int MaximumFailuresPerWindow = 5;
    private const int MaximumTrackedClients = 4096;
    private static readonly TimeSpan FailureWindow = TimeSpan.FromMinutes(15);
    private static readonly byte[] DisabledComparisonValue = SHA256.HashData(Encoding.UTF8.GetBytes("play-review-disabled"));

    private sealed record FailureState(DateTimeOffset WindowStartedAtUtc, int Count);

    private readonly object _gate = new();
    private readonly Dictionary<string, FailureState> _failures = new(StringComparer.Ordinal);
    private readonly byte[] _usernameDigest = DisabledComparisonValue;
    private readonly byte[] _passwordDigest = DisabledComparisonValue;

    public PlayReviewAccessService(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);

        Enabled = configuration.GetValue<bool>("CHUMMER_PLAY_REVIEW_ACCESS_ENABLED");
        if (!Enabled)
        {
            SubjectId = string.Empty;
            DisplayName = "Play Reviewer";
            return;
        }

        string username = RequireBounded(configuration["CHUMMER_PLAY_REVIEW_ACCESS_USERNAME"], "username", 8, 128);
        SubjectId = RequireBounded(configuration["CHUMMER_PLAY_REVIEW_ACCESS_SUBJECT_ID"], "subject ID", 8, 160);
        DisplayName = OptionalBounded(configuration["CHUMMER_PLAY_REVIEW_ACCESS_DISPLAY_NAME"], "display name", 96)
            ?? "Play Reviewer";

        string passwordSha256 = configuration["CHUMMER_PLAY_REVIEW_ACCESS_PASSWORD_SHA256"]?.Trim() ?? string.Empty;
        if (!TryDecodeSha256(passwordSha256, out byte[]? decodedPasswordDigest))
        {
            throw new InvalidOperationException(
                "CHUMMER_PLAY_REVIEW_ACCESS_PASSWORD_SHA256 must be exactly 64 hexadecimal characters when Play review access is enabled.");
        }

        _usernameDigest = SHA256.HashData(Encoding.UTF8.GetBytes(username));
        _passwordDigest = decodedPasswordDigest;
    }

    public bool Enabled { get; }

    public string SubjectId { get; }

    public string DisplayName { get; }

    public PlayReviewAuthenticationResult Authenticate(
        string? username,
        string? password,
        string? clientKey,
        DateTimeOffset nowUtc)
    {
        if (!Enabled)
        {
            return new PlayReviewAuthenticationResult(PlayReviewAuthenticationStatus.Disabled);
        }

        string boundedClientKey = NormalizeClientKey(clientKey);
        lock (_gate)
        {
            PruneExpiredFailures(nowUtc);
            if (_failures.TryGetValue(boundedClientKey, out FailureState? blocked)
                && blocked.Count >= MaximumFailuresPerWindow)
            {
                TimeSpan retryAfter = FailureWindow - (nowUtc - blocked.WindowStartedAtUtc);
                return new PlayReviewAuthenticationResult(
                    PlayReviewAuthenticationStatus.Throttled,
                    RetryAfter: retryAfter > TimeSpan.Zero ? retryAfter : TimeSpan.FromSeconds(1));
            }
        }

        byte[] suppliedUsernameDigest = SHA256.HashData(Encoding.UTF8.GetBytes(BoundCredentialValue(username)));
        byte[] suppliedPasswordDigest = SHA256.HashData(Encoding.UTF8.GetBytes(BoundCredentialValue(password)));
        bool usernameMatches = CryptographicOperations.FixedTimeEquals(suppliedUsernameDigest, _usernameDigest);
        bool passwordMatches = CryptographicOperations.FixedTimeEquals(suppliedPasswordDigest, _passwordDigest);

        if (usernameMatches && passwordMatches)
        {
            lock (_gate)
            {
                _failures.Remove(boundedClientKey);
            }

            return new PlayReviewAuthenticationResult(
                PlayReviewAuthenticationStatus.Succeeded,
                new PlayReviewAccessPrincipal(SubjectId, DisplayName, ["player"]));
        }

        lock (_gate)
        {
            if (_failures.Count >= MaximumTrackedClients && !_failures.ContainsKey(boundedClientKey))
            {
                RemoveOldestFailure();
            }

            _failures[boundedClientKey] = _failures.TryGetValue(boundedClientKey, out FailureState? current)
                ? current with { Count = current.Count + 1 }
                : new FailureState(nowUtc, 1);
        }

        return new PlayReviewAuthenticationResult(PlayReviewAuthenticationStatus.Rejected);
    }

    private void PruneExpiredFailures(DateTimeOffset nowUtc)
    {
        string[] expired = _failures
            .Where(pair => nowUtc - pair.Value.WindowStartedAtUtc >= FailureWindow)
            .Select(static pair => pair.Key)
            .ToArray();
        foreach (string key in expired)
        {
            _failures.Remove(key);
        }
    }

    private void RemoveOldestFailure()
    {
        string? oldest = _failures
            .OrderBy(static pair => pair.Value.WindowStartedAtUtc)
            .Select(static pair => pair.Key)
            .FirstOrDefault();
        if (oldest is not null)
        {
            _failures.Remove(oldest);
        }
    }

    private static string NormalizeClientKey(string? clientKey)
    {
        string value = string.IsNullOrWhiteSpace(clientKey) ? "remote-ip-unavailable" : clientKey.Trim();
        return value.Length <= 128 ? value : value[..128];
    }

    private static string BoundCredentialValue(string? value)
        => string.IsNullOrEmpty(value)
            ? string.Empty
            : value.Length <= 512
                ? value
                : value[..512];

    private static string RequireBounded(string? value, string label, int minimumLength, int maximumLength)
    {
        string normalized = value?.Trim() ?? string.Empty;
        if (normalized.Length < minimumLength || normalized.Length > maximumLength)
        {
            throw new InvalidOperationException(
                $"Play review access {label} must contain between {minimumLength} and {maximumLength} characters when access is enabled.");
        }

        return normalized;
    }

    private static string? OptionalBounded(string? value, string label, int maximumLength)
    {
        string? normalized = string.IsNullOrWhiteSpace(value) ? null : value.Trim();
        if (normalized?.Length > maximumLength)
        {
            throw new InvalidOperationException(
                $"Play review access {label} must not exceed {maximumLength} characters.");
        }

        return normalized;
    }

    private static bool TryDecodeSha256(string value, out byte[] digest)
    {
        digest = Array.Empty<byte>();
        if (value.Length != 64)
        {
            return false;
        }

        try
        {
            digest = Convert.FromHexString(value);
            return digest.Length == 32;
        }
        catch (FormatException)
        {
            return false;
        }
    }
}
