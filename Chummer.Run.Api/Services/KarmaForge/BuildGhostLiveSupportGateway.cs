using Chummer.Run.Contracts.BuildGhost;
using Microsoft.AspNetCore.Hosting;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;

namespace Chummer.Run.Api.Services.KarmaForge;

public interface IBuildGhostLiveSupportGateway
{
    Task<BuildGhostSupportExperienceProjection> GetExperienceAsync(CancellationToken cancellationToken);

    Task<BuildGhostLiveSupportSessionProjection> RequestAsync(
        BuildGhostLiveSupportRequest request,
        CancellationToken cancellationToken);

    Task<BuildGhostLiveSupportSessionProjection?> GetSessionAsync(
        BuildGhostLiveSupportStatusRequest request,
        CancellationToken cancellationToken);
}

public sealed class BuildGhostLiveSupportGateway : IBuildGhostLiveSupportGateway
{
    public const string HttpClientName = "BuildGhostLiveSupportAi";
    public const string BaseUrlConfigurationKey = "CHUMMER_BUILD_GHOST_AI_BASE_URL";
    public const string PrimaryTokenConfigurationKey = "CHUMMER_AI_INTERNAL_API_TOKEN";
    public const string FallbackTokenConfigurationKey = "FLEET_INTERNAL_API_TOKEN";
    public const int MaximumResponseBytes = 256 * 1024;

    private static readonly JsonSerializerOptions StrictJson = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow
    };

    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IConfiguration _configuration;
    private readonly string _webRootPath;

    public BuildGhostLiveSupportGateway(
        IHttpClientFactory httpClientFactory,
        IConfiguration configuration,
        IWebHostEnvironment environment)
    {
        _httpClientFactory = httpClientFactory ?? throw new ArgumentNullException(nameof(httpClientFactory));
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        ArgumentNullException.ThrowIfNull(environment);
        _webRootPath = ResolveWebRoot(environment.WebRootPath);
    }

    public async Task<BuildGhostSupportExperienceProjection> GetExperienceAsync(
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!TryResolveConfiguration(out Uri? baseAddress, out string token))
        {
            return UnavailableExperience("live-support-ai-gateway-unconfigured");
        }

        try
        {
            using HttpRequestMessage request = CreateRequest(
                HttpMethod.Get,
                new Uri(baseAddress, "api/v1/ai/build-ghost/support-experience"),
                token);
            using HttpResponseMessage response = await SendAsync(request, cancellationToken).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                return UnavailableExperience($"live-support-ai-http-{(int)response.StatusCode}");
            }

            BuildGhostSupportExperienceProjection? experience =
                await ReadBoundedJsonAsync<BuildGhostSupportExperienceProjection>(response.Content, cancellationToken)
                    .ConfigureAwait(false);
            return NormalizeExperience(experience)
                ?? UnavailableExperience("live-support-ai-experience-invalid");
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception) when (exception is HttpRequestException
            or IOException
            or JsonException
            or InvalidOperationException)
        {
            return UnavailableExperience("live-support-ai-unreachable");
        }
    }

    public async Task<BuildGhostLiveSupportSessionProjection> RequestAsync(
        BuildGhostLiveSupportRequest request,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        if (!TryResolveConfiguration(out Uri? baseAddress, out string token))
        {
            return UnavailableSession(request, "live-support-ai-gateway-unconfigured");
        }

        try
        {
            using HttpRequestMessage message = CreateRequest(
                HttpMethod.Post,
                new Uri(baseAddress, "api/v1/ai/build-ghost/live-support"),
                token);
            message.Content = JsonContent.Create(request, options: StrictJson);
            using HttpResponseMessage response = await SendAsync(message, cancellationToken).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                return UnavailableSession(request, $"live-support-ai-http-{(int)response.StatusCode}");
            }

            BuildGhostLiveSupportSessionProjection? session =
                await ReadBoundedJsonAsync<BuildGhostLiveSupportSessionProjection>(response.Content, cancellationToken)
                    .ConfigureAwait(false);
            return IsValidSession(session, request)
                ? session!
                : UnavailableSession(request, "live-support-ai-session-invalid");
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception) when (exception is HttpRequestException
            or IOException
            or JsonException
            or InvalidOperationException)
        {
            return UnavailableSession(request, "live-support-ai-unreachable");
        }
    }

    public async Task<BuildGhostLiveSupportSessionProjection?> GetSessionAsync(
        BuildGhostLiveSupportStatusRequest request,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        if (!TryResolveConfiguration(out Uri? baseAddress, out string token))
        {
            return null;
        }

        try
        {
            using HttpRequestMessage message = CreateRequest(
                HttpMethod.Post,
                new Uri(baseAddress, "api/v1/ai/build-ghost/live-support/status"),
                token);
            message.Content = JsonContent.Create(request, options: StrictJson);
            using HttpResponseMessage response = await SendAsync(message, cancellationToken).ConfigureAwait(false);
            if (response.StatusCode == System.Net.HttpStatusCode.NotFound || !response.IsSuccessStatusCode)
            {
                return null;
            }

            BuildGhostLiveSupportSessionProjection? session =
                await ReadBoundedJsonAsync<BuildGhostLiveSupportSessionProjection>(response.Content, cancellationToken)
                    .ConfigureAwait(false);
            return IsValidStatusSession(session, request) ? session : null;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception) when (exception is HttpRequestException
            or IOException
            or JsonException
            or InvalidOperationException)
        {
            return null;
        }
    }

    private async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        HttpClient client = _httpClientFactory.CreateClient(HttpClientName);
        return await client.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken).ConfigureAwait(false);
    }

    private bool TryResolveConfiguration(out Uri baseAddress, out string token)
    {
        baseAddress = null!;
        token = (_configuration[PrimaryTokenConfigurationKey]
            ?? _configuration[FallbackTokenConfigurationKey]
            ?? string.Empty).Trim();
        string configuredBase = (_configuration[BaseUrlConfigurationKey] ?? string.Empty).Trim();
        if (token.Length < 32
            || token.IndexOfAny(['\r', '\n', '\0']) >= 0
            || !Uri.TryCreate(configuredBase, UriKind.Absolute, out Uri? parsed)
            || !IsAllowedInternalBase(parsed))
        {
            token = string.Empty;
            return false;
        }

        baseAddress = parsed.AbsoluteUri.EndsWith("/", StringComparison.Ordinal)
            ? parsed
            : new Uri(parsed.AbsoluteUri + "/", UriKind.Absolute);
        return true;
    }

    private static bool IsAllowedInternalBase(Uri uri)
    {
        if (!uri.IsAbsoluteUri
            || !string.IsNullOrEmpty(uri.UserInfo)
            || !string.IsNullOrEmpty(uri.Query)
            || !string.IsNullOrEmpty(uri.Fragment)
            || uri.AbsolutePath is not ("" or "/"))
        {
            return false;
        }

        if (string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return string.Equals(uri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
            && (uri.IsLoopback
                || uri.Host.EndsWith(".internal", StringComparison.OrdinalIgnoreCase)
                || (!uri.Host.Contains('.', StringComparison.Ordinal) && uri.Host.Length > 0));
    }

    private static HttpRequestMessage CreateRequest(HttpMethod method, Uri endpoint, string token)
    {
        HttpRequestMessage request = new(method, endpoint);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.CacheControl = new CacheControlHeaderValue { NoStore = true };
        return request;
    }

    private static async Task<T?> ReadBoundedJsonAsync<T>(
        HttpContent content,
        CancellationToken cancellationToken)
    {
        await using Stream stream = await content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using MemoryStream buffer = new();
        byte[] chunk = new byte[16 * 1024];
        int total = 0;
        while (true)
        {
            int read = await stream.ReadAsync(chunk.AsMemory(), cancellationToken).ConfigureAwait(false);
            if (read == 0)
            {
                return JsonSerializer.Deserialize<T>(buffer.ToArray(), StrictJson);
            }

            total += read;
            if (total > MaximumResponseBytes)
            {
                throw new IOException("live-support-ai-response-too-large");
            }
            buffer.Write(chunk, 0, read);
        }
    }

    private BuildGhostSupportExperienceProjection? NormalizeExperience(
        BuildGhostSupportExperienceProjection? experience)
    {
        if (experience is null
            || experience.DefaultSupport is null
            || experience.LiveSupport is null
            || experience.LiveSupport.MeetingProviders is null
            || !string.Equals(
                experience.Schema,
                ToughTongueBuildGhostContractVersions.SupportExperienceV1,
                StringComparison.Ordinal)
            || !string.Equals(
                experience.DefaultSupport.ChannelKind,
                BuildGhostSupportChannelKinds.RookVidBoard,
                StringComparison.Ordinal)
            || !string.Equals(
                experience.DefaultSupport.PersonaId,
                ToughTongueBuildGhostPersonaIds.Rook,
                StringComparison.Ordinal)
            || !experience.LiveSupport.MeetingProviders.All(provider =>
                provider is BuildGhostLiveMeetingProviders.Zoom or BuildGhostLiveMeetingProviders.Teams))
        {
            return null;
        }

        BuildGhostDefaultSupportProjection defaultSupport = experience.DefaultSupport;
        if (defaultSupport.PreRenderedVideoReady
            && (!IsSafeSameOriginMediaHref(defaultSupport.PreRenderedVideoHref)
                || !IsSha256(defaultSupport.MediaContentDigest)
                || !HasApprovedMediaBytes(
                    defaultSupport.PreRenderedVideoHref!,
                    defaultSupport.MediaContentDigest)))
        {
            defaultSupport = defaultSupport with
            {
                PreRenderedVideoHref = null,
                MediaContentDigest = string.Empty,
                PreRenderedVideoReady = false,
                AvailabilityStatus = "text-fallback",
                BlockingReasons = (defaultSupport.BlockingReasons ?? [])
                    .Append("rook-vidboard-hub-media-bytes-unverified")
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(static reason => reason, StringComparer.Ordinal)
                    .ToArray()
            };
        }
        else if (!defaultSupport.PreRenderedVideoReady)
        {
            defaultSupport = defaultSupport with
            {
                PreRenderedVideoHref = null,
                MediaContentDigest = string.Empty
            };
        }

        return experience with { DefaultSupport = defaultSupport };
    }

    private bool HasApprovedMediaBytes(string href, string expectedDigest)
    {
        if (string.IsNullOrEmpty(_webRootPath))
        {
            return false;
        }

        try
        {
            string relative = href[1..].Replace('/', Path.DirectorySeparatorChar);
            string path = Path.GetFullPath(Path.Combine(_webRootPath, relative));
            string requiredPrefix = _webRootPath.EndsWith(Path.DirectorySeparatorChar)
                ? _webRootPath
                : _webRootPath + Path.DirectorySeparatorChar;
            if (!path.StartsWith(requiredPrefix, StringComparison.Ordinal)
                || !HasNoSymlinkSegments(path))
            {
                return false;
            }

            FileInfo file = new(path);
            if (!file.Exists || file.Length <= 0 || file.Length > 512L * 1024 * 1024 || file.LinkTarget is not null)
            {
                return false;
            }

            using FileStream stream = file.Open(FileMode.Open, FileAccess.Read, FileShare.Read);
            string observedDigest = $"sha256:{Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant()}";
            return CryptographicOperations.FixedTimeEquals(
                System.Text.Encoding.ASCII.GetBytes(observedDigest),
                System.Text.Encoding.ASCII.GetBytes(expectedDigest));
        }
        catch (Exception exception) when (exception is IOException
            or UnauthorizedAccessException
            or NotSupportedException
            or ArgumentException)
        {
            return false;
        }
    }

    private bool HasNoSymlinkSegments(string filePath)
    {
        DirectoryInfo? current = new FileInfo(filePath).Directory;
        while (current is not null
            && !string.Equals(current.FullName, _webRootPath, StringComparison.Ordinal))
        {
            if (current.LinkTarget is not null)
            {
                return false;
            }
            current = current.Parent;
        }
        return current is not null;
    }

    private static string ResolveWebRoot(string? candidate)
    {
        if (string.IsNullOrWhiteSpace(candidate) || !Path.IsPathFullyQualified(candidate))
        {
            return string.Empty;
        }
        try
        {
            DirectoryInfo directory = new(Path.GetFullPath(candidate));
            return directory.Exists && directory.LinkTarget is null ? directory.FullName : string.Empty;
        }
        catch (Exception exception) when (exception is IOException
            or UnauthorizedAccessException
            or NotSupportedException
            or ArgumentException)
        {
            return string.Empty;
        }
    }

    private static bool IsValidSession(
        BuildGhostLiveSupportSessionProjection? session,
        BuildGhostLiveSupportRequest request)
    {
        if (session is null
            || !string.Equals(session.Schema, ToughTongueBuildGhostContractVersions.LiveSupportSessionV1, StringComparison.Ordinal)
            || !string.Equals(session.RequestId, request.RequestId, StringComparison.Ordinal)
            || !string.Equals(session.MeetingProvider, request.MeetingProvider, StringComparison.Ordinal)
            || !string.Equals(session.DisclosureVersion, request.DisclosureVersion, StringComparison.Ordinal)
            || !string.Equals(session.DisclosureDigest, request.DisclosureDigest, StringComparison.Ordinal))
        {
            return false;
        }

        if (!string.Equals(session.Status, BuildGhostLiveSupportStatuses.Ready, StringComparison.Ordinal))
        {
            return session.JoinUrl is null;
        }

        return session.JoinUrl is not null && IsAllowedJoinUrl(session.JoinUrl, session.MeetingProvider);
    }

    private static bool IsValidStatusSession(
        BuildGhostLiveSupportSessionProjection? session,
        BuildGhostLiveSupportStatusRequest request)
        => session is not null
            && string.Equals(
                session.Schema,
                ToughTongueBuildGhostContractVersions.LiveSupportSessionV1,
                StringComparison.Ordinal)
            && string.Equals(session.RequestId, request.RequestId, StringComparison.Ordinal)
            && string.Equals(
                session.DisclosureVersion,
                BuildGhostLiveSupportDisclosureContract.CurrentVersion,
                StringComparison.Ordinal)
            && string.Equals(
                session.DisclosureDigest,
                BuildGhostLiveSupportDisclosureContract.ComputeDigest(),
                StringComparison.Ordinal)
            && (session.JoinUrl is null
                || (string.Equals(session.Status, BuildGhostLiveSupportStatuses.Ready, StringComparison.Ordinal)
                    && IsAllowedJoinUrl(session.JoinUrl, session.MeetingProvider)));

    private static bool IsAllowedJoinUrl(Uri uri, string provider)
    {
        if (!uri.IsAbsoluteUri
            || !string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            || !string.IsNullOrEmpty(uri.UserInfo)
            || !string.IsNullOrEmpty(uri.Fragment)
            || !uri.IsDefaultPort)
        {
            return false;
        }

        string host = uri.IdnHost.TrimEnd('.').ToLowerInvariant();
        return provider switch
        {
            BuildGhostLiveMeetingProviders.Zoom => host == "zoom.us"
                || host.EndsWith(".zoom.us", StringComparison.Ordinal),
            BuildGhostLiveMeetingProviders.Teams => (host == "teams.microsoft.com" || host == "teams.live.com")
                && (uri.AbsolutePath.StartsWith("/l/meetup-join/", StringComparison.OrdinalIgnoreCase)
                    || uri.AbsolutePath.StartsWith("/meet/", StringComparison.OrdinalIgnoreCase)),
            _ => false
        };
    }

    private static bool IsSafeSameOriginMediaHref(string? href)
        => href is { Length: > 1 and <= 512 }
            && href[0] == '/'
            && href[1] != '/'
            && !href.Contains('\\')
            && !href.Contains('?')
            && !href.Contains('#')
            && !href.Contains("%2f", StringComparison.OrdinalIgnoreCase)
            && !href.Contains("%5c", StringComparison.OrdinalIgnoreCase)
            && !href.Contains("%2e", StringComparison.OrdinalIgnoreCase)
            && !href.Contains("//", StringComparison.Ordinal)
            && !href.Split('/').Any(static segment => segment is "." or "..")
            && href.EndsWith(".mp4", StringComparison.OrdinalIgnoreCase);

    private static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).IndexOfAnyExcept("0123456789abcdef") < 0;

    private static BuildGhostSupportExperienceProjection UnavailableExperience(string reason)
        => new(
            ToughTongueBuildGhostContractVersions.SupportExperienceV1,
            new BuildGhostDefaultSupportProjection(
                BuildGhostSupportChannelKinds.RookVidBoard,
                ToughTongueBuildGhostPersonaIds.Rook,
                ToughTongueBuildGhostPersonaIds.RookAvatar,
                ToughTongueBuildGhostPersonaIds.RookVidBoardSupport,
                null,
                string.Empty,
                false,
                "text-fallback",
                "Rook can continue in the grounded Chummer help flow.",
                ["rook-vidboard-runtime-unverified"]),
            new BuildGhostLiveSupportCapabilityProjection(
                BuildGhostSupportChannelKinds.LivePhotorealMeeting,
                false,
                [],
                "unavailable",
                true,
                [reason]));

    private static BuildGhostLiveSupportSessionProjection UnavailableSession(
        BuildGhostLiveSupportRequest request,
        string reason)
        => new(
            ToughTongueBuildGhostContractVersions.LiveSupportSessionV1,
            request.RequestId,
            BuildGhostSupportChannelKinds.LivePhotorealMeeting,
            BuildGhostLiveSupportStatuses.Unavailable,
            request.MeetingProvider,
            null,
            null,
            string.Empty,
            "unavailable",
            request.RecordingConsentGranted,
            request.ExternalProviderProcessingConsentGranted,
            request.DisclosureVersion,
            request.DisclosureDigest,
            string.Empty,
            string.Empty,
            string.Empty,
            string.Empty,
            request.RequestedAtUtc,
            DateTimeOffset.UtcNow,
            UnavailableExperience(reason).DefaultSupport,
            [reason]);
}
