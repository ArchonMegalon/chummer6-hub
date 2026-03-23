using System.Net;
using System.Net.Http.Json;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services;

public sealed record AuthenticatedHubSubject(
    string SubjectId,
    string? DisplayName,
    string? Email,
    IReadOnlyList<string> Roles,
    string AccessToken);

public sealed class HubRequestAuthException : Exception
{
    public HubRequestAuthException(int statusCode, string message)
        : base(message)
    {
        StatusCode = statusCode;
    }

    public int StatusCode { get; }
}

public sealed class HubIdentityClient
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;

    public HubIdentityClient(HttpClient httpClient, IConfiguration configuration)
    {
        _httpClient = httpClient;
        _configuration = configuration;
    }

    private string BaseUrl =>
        (_configuration["IDENTITY_SERVICE_BASE_URL"] ?? "http://chummer-run-identity:8080").TrimEnd('/');

    public async Task<AuthenticatedHubSubject> RequireSubjectAsync(HttpRequest request, CancellationToken cancellationToken)
    {
        var accessToken = ExtractBearerToken(request);
        var introspection = await IntrospectAsync(accessToken, cancellationToken);
        if (!introspection.Active || string.IsNullOrWhiteSpace(introspection.SubjectId))
        {
            throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "active identity session required.");
        }

        var profile = await TryGetSubjectAsync(introspection.SubjectId!, cancellationToken);
        return new AuthenticatedHubSubject(
            introspection.SubjectId!,
            profile?.DisplayName,
            profile?.Email,
            introspection.Roles ?? Array.Empty<string>(),
            accessToken);
    }

    public async Task<AuthenticatedHubSubject> RequireMatchingSubjectAsync(
        HttpRequest request,
        string? claimedSubjectId,
        CancellationToken cancellationToken)
    {
        var subject = await RequireSubjectAsync(request, cancellationToken);
        var claimed = string.IsNullOrWhiteSpace(claimedSubjectId) ? null : claimedSubjectId.Trim();
        if (claimed is not null && !string.Equals(claimed, subject.SubjectId, StringComparison.OrdinalIgnoreCase))
        {
            throw new HubRequestAuthException(StatusCodes.Status403Forbidden, "subject mismatch for authenticated session.");
        }

        return subject;
    }

    private async Task<IdentityIntrospectionResponse> IntrospectAsync(string accessToken, CancellationToken cancellationToken)
    {
        using var response = await _httpClient.PostAsJsonAsync(
            $"{BaseUrl}/api/v1/identity/introspect",
            new IdentityIntrospectionRequest(accessToken),
            cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "identity introspection failed.");
        }

        var payload = await response.Content.ReadFromJsonAsync<IdentityIntrospectionResponse>(cancellationToken: cancellationToken);
        return payload ?? new IdentityIntrospectionResponse(false, null, null, null, null);
    }

    private async Task<IdentitySubjectResponse?> TryGetSubjectAsync(string subjectId, CancellationToken cancellationToken)
    {
        using var response = await _httpClient.GetAsync(
            $"{BaseUrl}/api/v1/identity/subjects/{Uri.EscapeDataString(subjectId)}",
            cancellationToken);
        if (response.StatusCode == HttpStatusCode.NotFound || !response.IsSuccessStatusCode)
        {
            return null;
        }

        return await response.Content.ReadFromJsonAsync<IdentitySubjectResponse>(cancellationToken: cancellationToken);
    }

    private static string ExtractBearerToken(HttpRequest request)
    {
        if (request is null)
        {
            throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "bearer access token required.");
        }

        var header = request.Headers.Authorization.ToString();
        if (!string.IsNullOrWhiteSpace(header)
            && header.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
        {
            var token = header["Bearer ".Length..].Trim();
            if (!string.IsNullOrWhiteSpace(token))
            {
                return token;
            }
        }

        if (request.Cookies.TryGetValue(HubBrowserAuthConstants.AccessTokenCookieName, out var cookieToken)
            && !string.IsNullOrWhiteSpace(cookieToken))
        {
            return cookieToken.Trim();
        }

        throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "bearer access token required.");
    }
}
