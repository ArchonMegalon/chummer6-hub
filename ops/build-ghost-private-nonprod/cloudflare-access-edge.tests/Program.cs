using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.BuildGhost.CloudflareAccessEdge;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.Primitives;

internal static class Program
{
    private const string TestAudience =
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    public static async Task<int> Main()
    {
        List<(string Name, Func<Task> Run)> tests =
        [
            ("configuration is explicit and sentinel-blocked", TestConfigurationAsync),
            ("route surface is an exact user-facing allowlist", TestRouteAllowlistAsync),
            ("Access headers require canonical single values", TestHeaderCardinalityAsync),
            ("upstream request overwrites identity and strips authority headers", TestUpstreamSanitizationAsync),
            ("JWT binds signature issuer audience type lifetime and email", TestJwtValidationAsync),
            ("signing-key retrieval is exact bounded and redirect closed", TestSigningKeyRetrievalAsync),
            ("signing-key cache refresh rotation failure and concurrency are closed", TestSigningKeyCacheAsync),
            ("real outbound handlers suppress all activity propagation", TestActivityHeaderIsolationAsync),
            ("proxy rejects bypasses before upstream", TestProxyBypassesAsync),
            ("proxy forwards one admitted request without security header leakage", TestProxyForwardingAsync),
        ];

        int failures = 0;
        foreach ((string name, Func<Task> run) in tests)
        {
            try
            {
                await run().ConfigureAwait(false);
                Console.WriteLine($"PASS {name}");
            }
            catch (Exception exception)
            {
                failures++;
                Console.Error.WriteLine($"FAIL {name}: {exception.Message}");
            }
        }

        Console.WriteLine($"cloudflare_access_edge_tests={tests.Count - failures}/{tests.Count}");
        return failures == 0 ? 0 : 1;
    }

static Task TestConfigurationAsync()
{
    AccessEdgeConfiguration configuration = TestConfiguration();
    Equal("ghost.chummer.run", configuration.PublicHost);
    Equal("example-team.cloudflareaccess.com", configuration.TeamDomain);
    Equal("https://example-team.cloudflareaccess.com/", configuration.Issuer.AbsoluteUri);
    Equal(
        "https://example-team.cloudflareaccess.com/cdn-cgi/access/certs",
        configuration.CertificatesEndpoint.AbsoluteUri);

    Throws<InvalidOperationException>(() => AccessEdgeConfiguration.Create(
        "unconfigured.invalid",
        "example-team.cloudflareaccess.com",
        TestAudience));
    Throws<InvalidOperationException>(() => AccessEdgeConfiguration.Create(
        "ghost.chummer.run",
        "evil.example.com",
        TestAudience));
    Throws<InvalidOperationException>(() => AccessEdgeConfiguration.Create(
        "Ghost.chummer.run",
        "example-team.cloudflareaccess.com",
        TestAudience));
    Throws<InvalidOperationException>(() => AccessEdgeConfiguration.Create(
        "ghost.chummer.run",
        "example-team.cloudflareaccess.com",
        ""));
    return Task.CompletedTask;
}

static Task TestRouteAllowlistAsync()
{
    True(BuildGhostAccessProxy.TryMatchRoute(
        "POST", "/api/workspaces/import", out BuildGhostAccessRoute import));
    Equal(BuildGhostAccessRouteKind.WorkspaceImport, import.Kind);
    True(BuildGhostAccessProxy.TryMatchRoute(
        "GET", "/api/workspaces/abc-123", out BuildGhostAccessRoute get));
    Equal(BuildGhostAccessRouteKind.WorkspaceLifecycle, get.Kind);
    True(BuildGhostAccessProxy.TryMatchRoute(
        "DELETE", "/api/workspaces/abc-123", out BuildGhostAccessRoute delete));
    Equal(BuildGhostAccessRouteKind.WorkspaceLifecycle, delete.Kind);
    True(BuildGhostAccessProxy.TryMatchRoute(
        "POST", "/api/workspaces/abc-123/build-ghost/tool-access", out BuildGhostAccessRoute grant));
    Equal(BuildGhostAccessRouteKind.ToolAccess, grant.Kind);

    foreach ((string method, string path) in new[]
    {
        ("POST", "/api/internal/build-ghost/tool/resolve"),
        ("POST", "/api/v1/ai/build-ghost/tool"),
        ("POST", "/api/v2/ai/build-ghost/tool"),
        ("POST", "/api/v1/ai/build-ghost/explain"),
        ("PUT", "/api/workspaces/abc-123"),
        ("GET", "/api/workspaces"),
        ("GET", "/api/workspaces/abc-123/summary"),
        ("POST", "/api/workspaces/../build-ghost/tool-access"),
        ("GET", "/api/workspaces/abc/def"),
        ("get", "/api/workspaces/abc-123"),
    })
    {
        False(BuildGhostAccessProxy.TryMatchRoute(method, path, out _), $"unexpected route {method} {path}");
    }
    return Task.CompletedTask;
}

static Task TestHeaderCardinalityAsync()
{
    DefaultHttpContext context = AdmittedContext("/api/workspaces/runner-1", "GET");
    True(BuildGhostAccessProxy.TryReadAccessHeaders(
        context.Request,
        out string email,
        out string assertion));
    Equal("runner@example.com", email);
    Equal("signed.assertion.value", assertion);

    context.Request.Headers[BuildGhostAccessProxy.AuthenticatedEmailHeader] =
        new StringValues(["runner@example.com", "attacker@example.com"]);
    False(BuildGhostAccessProxy.TryReadAccessHeaders(context.Request, out _, out _));

    context = AdmittedContext("/api/workspaces/runner-1", "GET");
    context.Request.Headers[BuildGhostAccessProxy.JwtAssertionHeader] =
        new StringValues(["signed.assertion.value", "forged.assertion.value"]);
    False(BuildGhostAccessProxy.TryReadAccessHeaders(context.Request, out _, out _));

    foreach (string badEmail in new[]
    {
        string.Empty,
        " Runner@example.com",
        "Runner@example.com",
        "runner@example.com,attacker@example.com",
        "runner@localhost",
    })
    {
        context = AdmittedContext("/api/workspaces/runner-1", "GET");
        context.Request.Headers[BuildGhostAccessProxy.AuthenticatedEmailHeader] = badEmail;
        False(BuildGhostAccessProxy.TryReadAccessHeaders(context.Request, out _, out _));
    }

    context = AdmittedContext("/api/workspaces/runner-1", "GET");
    context.Request.Headers.Remove(BuildGhostAccessProxy.JwtAssertionHeader);
    context.Request.Headers.Cookie = "CF_Authorization=cookie-only";
    False(BuildGhostAccessProxy.TryReadAccessHeaders(context.Request, out _, out _));
    return Task.CompletedTask;
}

static Task TestUpstreamSanitizationAsync()
{
    DefaultHttpContext context = AdmittedContext("/api/workspaces/import", "POST");
    context.Request.ContentType = "application/json";
    context.Request.Body = new MemoryStream("{}"u8.ToArray());
    context.Request.Headers.Authorization = "Bearer attacker";
    context.Request.Headers.Cookie = "session=attacker";
    context.Request.Headers[BuildGhostAccessProxy.OwnerHeader] = "attacker@example.com";
    context.Request.Headers[BuildGhostAccessProxy.PortalOwnerHeader] = "attacker@example.com";
    context.Request.Headers[BuildGhostAccessProxy.PortalOwnerTimestampHeader] = "1";
    context.Request.Headers[BuildGhostAccessProxy.PortalOwnerSignatureHeader] = "forged";
    context.Request.Headers[BuildGhostAccessProxy.PortalModeratorSignatureHeader] = "forged";
    context.Request.Headers["X-Forwarded-Host"] = "attacker.example";
    context.Request.Headers["Cf-Connecting-Ip"] = "203.0.113.4";

    True(BuildGhostAccessProxy.TryMatchRoute(
        context.Request.Method,
        context.Request.Path,
        out BuildGhostAccessRoute route));
    using HttpRequestMessage outgoing = BuildGhostAccessProxy.CreateUpstreamRequest(
        context.Request,
        "runner@example.com",
        route);

    Equal("http://chummer-build-ghost-presentation:8080/api/workspaces/import", outgoing.RequestUri!.AbsoluteUri);
    Equal("runner@example.com", outgoing.Headers.GetValues(BuildGhostAccessProxy.OwnerHeader).Single());
    True(outgoing.Headers.CacheControl?.NoStore is true);
    foreach (string name in new[]
    {
        BuildGhostAccessProxy.AuthenticatedEmailHeader,
        BuildGhostAccessProxy.JwtAssertionHeader,
        BuildGhostAccessProxy.PortalOwnerHeader,
        BuildGhostAccessProxy.PortalOwnerTimestampHeader,
        BuildGhostAccessProxy.PortalOwnerSignatureHeader,
        BuildGhostAccessProxy.PortalModeratorSignatureHeader,
        "Authorization",
        "Cookie",
        "X-Forwarded-Host",
        "Cf-Connecting-Ip",
    })
    {
        False(outgoing.Headers.Contains(name), $"leaked upstream header {name}");
        True(BuildGhostAccessProxy.IsForbiddenUpstreamHeader(name));
    }
    return Task.CompletedTask;
}

static async Task TestJwtValidationAsync()
{
    using RSA rsa = RSA.Create(2048);
    RSAParameters publicKey = rsa.ExportParameters(false);
    AccessEdgeConfiguration configuration = TestConfiguration();
    FixedTimeProvider clock = new(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000));
    CloudflareAccessJwtValidator validator = new(
        configuration,
        new StaticKeyProvider(new CloudflareAccessSigningKey(
            "key-1",
            publicKey.Modulus!,
            publicKey.Exponent!)),
        clock);

    string valid = Token(rsa, "key-1", configuration, "runner@example.com", 1_999_999_900, 2_000_000_300);
    True(await validator.ValidateAsync(valid, "runner@example.com", CancellationToken.None));
    True(await validator.ValidateAsync(
        Token(
            rsa,
            "key-1",
            configuration,
            "runner@example.com",
            1_999_999_900,
            1_999_999_900 + CloudflareAccessJwtValidator.MaximumTokenLifetimeSeconds),
        "runner@example.com",
        CancellationToken.None));
    False(await validator.ValidateAsync(
        Token(
            rsa,
            "key-1",
            configuration,
            "runner@example.com",
            1_999_999_900,
            1_999_999_901 + CloudflareAccessJwtValidator.MaximumTokenLifetimeSeconds),
        "runner@example.com",
        CancellationToken.None));
    False(await validator.ValidateAsync(
        Token(
            rsa,
            "key-1",
            configuration,
            "runner@example.com",
            long.MinValue,
            long.MaxValue),
        "runner@example.com",
        CancellationToken.None));
    False(await validator.ValidateAsync(
        Token(
            rsa,
            "key-1",
            configuration,
            "runner@example.com",
            1_999_999_900,
            2_000_000_300,
            tokenType: "org"),
        "runner@example.com",
        CancellationToken.None));
    False(await validator.ValidateAsync(valid, "attacker@example.com", CancellationToken.None));
    False(await validator.ValidateAsync(
        Token(rsa, "key-1", configuration, "runner@example.com", 1_999_999_900, 2_000_000_300, audience: "other-audience-value"),
        "runner@example.com",
        CancellationToken.None));
    False(await validator.ValidateAsync(
        Token(rsa, "key-1", configuration, "runner@example.com", 1_999_999_900, 2_000_000_300, issuer: "https://evil.cloudflareaccess.com"),
        "runner@example.com",
        CancellationToken.None));
    False(await validator.ValidateAsync(
        Token(rsa, "key-1", configuration, "runner@example.com", 1_999_999_000, 1_999_999_100),
        "runner@example.com",
        CancellationToken.None));
    False(await validator.ValidateAsync(
        Token(rsa, "key-1", configuration, "runner@example.com", 1_999_999_900, 2_000_000_300, notBefore: 2_000_000_100),
        "runner@example.com",
        CancellationToken.None));

    string[] tamperedSegments = valid.Split('.');
    int tamperedIndex = tamperedSegments[1].Length / 2;
    char replacement = tamperedSegments[1][tamperedIndex] == 'A' ? 'B' : 'A';
    tamperedSegments[1] = tamperedSegments[1][..tamperedIndex]
        + replacement
        + tamperedSegments[1][(tamperedIndex + 1)..];
    string tampered = string.Join('.', tamperedSegments);
    False(await validator.ValidateAsync(tampered, "runner@example.com", CancellationToken.None));
    False(await validator.ValidateAsync(
        Token(rsa, "unknown", configuration, "runner@example.com", 1_999_999_900, 2_000_000_300),
        "runner@example.com",
        CancellationToken.None));

    string duplicatePayload =
        $"{{\"iss\":\"{configuration.Issuer.AbsoluteUri.TrimEnd('/')}\",\"aud\":[\"{configuration.Audience}\"],\"type\":\"app\",\"email\":\"runner@example.com\",\"email\":\"attacker@example.com\",\"iat\":1999999900,\"exp\":2000000300}}";
    False(await validator.ValidateAsync(
        TokenFromRawPayload(rsa, "key-1", duplicatePayload),
        "runner@example.com",
        CancellationToken.None));

    string serviceTokenPayload =
        $"{{\"iss\":\"{configuration.Issuer.AbsoluteUri.TrimEnd('/')}\",\"aud\":[\"{configuration.Audience}\"],\"type\":\"app\",\"common_name\":\"service.access\",\"sub\":\"\",\"iat\":1999999900,\"exp\":2000000300}}";
    False(await validator.ValidateAsync(
        TokenFromRawPayload(rsa, "key-1", serviceTokenPayload),
        "runner@example.com",
        CancellationToken.None));
}

static async Task TestSigningKeyRetrievalAsync()
{
    using RSA rsa = RSA.Create(2048);
    RSAParameters publicKey = rsa.ExportParameters(false);
    AccessEdgeConfiguration configuration = TestConfiguration();
    string keyJson = JsonSerializer.Serialize(new
    {
        kty = "RSA",
        kid = "key-1",
        use = "sig",
        alg = "RS256",
        n = Base64Url(publicKey.Modulus!),
        e = Base64Url(publicKey.Exponent!),
    });
    FixedResponseHandler validHandler = new(_ => new HttpResponseMessage(HttpStatusCode.OK)
    {
        Content = new StringContent($"{{\"keys\":[{keyJson}]}}", Encoding.UTF8, "application/json"),
    });
    using HttpClient validClient = new(validHandler);
    CloudflareAccessSigningKeyProvider validProvider = new(
        configuration,
        validClient,
        new FixedTimeProvider(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000)));
    CloudflareAccessSigningKey? key = await validProvider.GetAsync("key-1", CancellationToken.None);
    True(key is not null);
    Equal("key-1", key!.KeyId);
    True(key.Modulus.SequenceEqual(publicKey.Modulus!));
    Equal(configuration.CertificatesEndpoint, validHandler.RequestedUris.Single());
    Equal(HttpMethod.Get, validHandler.Methods.Single());

    FixedResponseHandler redirectHandler = new(_ =>
    {
        HttpResponseMessage response = new(HttpStatusCode.Redirect);
        response.Headers.Location = new Uri("https://evil.example/certs");
        return response;
    });
    using HttpClient redirectClient = new(redirectHandler);
    CloudflareAccessSigningKeyProvider redirectProvider = new(configuration, redirectClient);
    True(await redirectProvider.GetAsync("key-1", CancellationToken.None) is null);
    Equal(1, redirectHandler.RequestedUris.Count);

    string duplicateKids = $"{{\"keys\":[{keyJson},{keyJson}]}}";
    FixedResponseHandler duplicateHandler = new(_ => new HttpResponseMessage(HttpStatusCode.OK)
    {
        Content = new StringContent(duplicateKids, Encoding.UTF8, "application/json"),
    });
    using HttpClient duplicateClient = new(duplicateHandler);
    CloudflareAccessSigningKeyProvider duplicateProvider = new(configuration, duplicateClient);
    True(await duplicateProvider.GetAsync("key-1", CancellationToken.None) is null);

    string duplicateRoot = $"{{\"keys\":[{keyJson}],\"keys\":[]}}";
    FixedResponseHandler duplicateRootHandler = new(_ => new HttpResponseMessage(HttpStatusCode.OK)
    {
        Content = new StringContent(duplicateRoot, Encoding.UTF8, "application/json"),
    });
    using HttpClient duplicateRootClient = new(duplicateRootHandler);
    CloudflareAccessSigningKeyProvider duplicateRootProvider = new(configuration, duplicateRootClient);
    True(await duplicateRootProvider.GetAsync("key-1", CancellationToken.None) is null);

    string encryptionKey = keyJson.Replace("\"use\":\"sig\"", "\"use\":\"enc\"", StringComparison.Ordinal);
    FixedResponseHandler encryptionHandler = new(_ => new HttpResponseMessage(HttpStatusCode.OK)
    {
        Content = new StringContent($"{{\"keys\":[{encryptionKey}]}}", Encoding.UTF8, "application/json"),
    });
    using HttpClient encryptionClient = new(encryptionHandler);
    CloudflareAccessSigningKeyProvider encryptionProvider = new(configuration, encryptionClient);
    True(await encryptionProvider.GetAsync("key-1", CancellationToken.None) is null);
}

static async Task TestSigningKeyCacheAsync()
{
    using RSA firstRsa = RSA.Create(2048);
    using RSA secondRsa = RSA.Create(2048);
    RSAParameters first = firstRsa.ExportParameters(false);
    RSAParameters second = secondRsa.ExportParameters(false);
    AccessEdgeConfiguration configuration = TestConfiguration();

    FixedResponseHandler cachedHandler = new(_ => JwksResponse(Jwks("key-1", first)));
    using HttpClient cachedClient = new(cachedHandler);
    MutableTimeProvider cachedClock = new(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000));
    CloudflareAccessSigningKeyProvider cachedProvider = new(
        configuration,
        cachedClient,
        cachedClock);
    CloudflareAccessSigningKey? cachedFirst = await cachedProvider.GetAsync(
        "key-1",
        CancellationToken.None);
    CloudflareAccessSigningKey? cachedSecond = await cachedProvider.GetAsync(
        "key-1",
        CancellationToken.None);
    True(cachedFirst is not null && cachedSecond is not null);
    Equal(1, cachedHandler.RequestedUris.Count);

    int unknownRefreshCall = 0;
    FixedResponseHandler unknownRefreshHandler = new(_ =>
        JwksResponse(Interlocked.Increment(ref unknownRefreshCall) == 1
            ? Jwks("key-1", first)
            : Jwks("key-2", second)));
    using HttpClient unknownRefreshClient = new(unknownRefreshHandler);
    CloudflareAccessSigningKeyProvider unknownRefreshProvider = new(
        configuration,
        unknownRefreshClient,
        new MutableTimeProvider(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000)));
    True(await unknownRefreshProvider.GetAsync("key-1", CancellationToken.None) is not null);
    True(await unknownRefreshProvider.GetAsync("key-2", CancellationToken.None) is not null);
    Equal(2, unknownRefreshHandler.RequestedUris.Count);

    int rotationCall = 0;
    FixedResponseHandler rotationHandler = new(_ =>
        JwksResponse(Interlocked.Increment(ref rotationCall) == 1
            ? Jwks("key-1", first)
            : Jwks("key-1", second)));
    using HttpClient rotationClient = new(rotationHandler);
    MutableTimeProvider rotationClock = new(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000));
    CloudflareAccessSigningKeyProvider rotationProvider = new(
        configuration,
        rotationClient,
        rotationClock);
    CloudflareAccessSigningKey? beforeRotation = await rotationProvider.GetAsync(
        "key-1",
        CancellationToken.None);
    rotationClock.Advance(TimeSpan.FromMinutes(11));
    CloudflareAccessSigningKey? afterRotation = await rotationProvider.GetAsync(
        "key-1",
        CancellationToken.None);
    True(beforeRotation is not null && afterRotation is not null);
    True(beforeRotation!.Modulus.SequenceEqual(first.Modulus!));
    True(afterRotation!.Modulus.SequenceEqual(second.Modulus!));
    Equal(2, rotationHandler.RequestedUris.Count);

    int failedRefreshCall = 0;
    FixedResponseHandler failedRefreshHandler = new(_ =>
        Interlocked.Increment(ref failedRefreshCall) == 1
            ? JwksResponse(Jwks("key-1", first))
            : new HttpResponseMessage(HttpStatusCode.ServiceUnavailable));
    using HttpClient failedRefreshClient = new(failedRefreshHandler);
    MutableTimeProvider failedRefreshClock = new(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000));
    CloudflareAccessSigningKeyProvider failedRefreshProvider = new(
        configuration,
        failedRefreshClient,
        failedRefreshClock);
    True(await failedRefreshProvider.GetAsync("key-1", CancellationToken.None) is not null);
    failedRefreshClock.Advance(TimeSpan.FromMinutes(11));
    True(await failedRefreshProvider.GetAsync("key-1", CancellationToken.None) is null);
    Equal(2, failedRefreshHandler.RequestedUris.Count);

    FixedResponseHandler concurrentHandler = new(_ => JwksResponse(Jwks("key-1", first)));
    using HttpClient concurrentClient = new(concurrentHandler);
    CloudflareAccessSigningKeyProvider concurrentProvider = new(
        configuration,
        concurrentClient,
        new MutableTimeProvider(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000)));
    CloudflareAccessSigningKey?[] concurrent = await Task.WhenAll(
        Enumerable.Range(0, 32).Select(_ =>
            concurrentProvider.GetAsync("key-1", CancellationToken.None).AsTask()));
    True(concurrent.All(static key => key is not null));
    Equal(1, concurrentHandler.RequestedUris.Count);
}

static async Task TestActivityHeaderIsolationAsync()
{
    DefaultHttpContext incoming = AdmittedContext("/api/workspaces/import", "POST");
    incoming.Request.ContentType = "application/json";
    incoming.Request.Body = new MemoryStream("{}"u8.ToArray());
    incoming.Request.Headers["traceparent"] =
        "00-11111111111111111111111111111111-2222222222222222-01";
    incoming.Request.Headers["tracestate"] = "vendor=hostile";
    incoming.Request.Headers["baggage"] = "owner=hostile";
    incoming.Request.Headers["Request-Id"] = "|hostile.request.";
    incoming.Request.Headers["Correlation-Context"] = "owner=hostile";
    True(BuildGhostAccessProxy.TryMatchRoute(
        incoming.Request.Method,
        incoming.Request.Path,
        out BuildGhostAccessRoute route));

    IReadOnlySet<string> presentationHeaders = await CaptureLoopbackHeadersAsync(
        async endpoint =>
        {
            using SocketsHttpHandler handler = AccessEdgeHttpTransport.CreatePresentationHandler();
            True(handler.ActivityHeadersPropagator is null);
            using HttpClient client = new(handler);
            using HttpRequestMessage request = BuildGhostAccessProxy.CreateUpstreamRequest(
                incoming.Request,
                "runner@example.com",
                route);
            request.RequestUri = endpoint;
            await WithHostileActivityAsync(ActivityIdFormat.W3C, async () =>
            {
                using HttpResponseMessage response = await client.SendAsync(request);
                Equal(HttpStatusCode.OK, response.StatusCode);
            });
        },
        "{\"ok\":true}");
    AssertTraceHeadersAbsent(presentationHeaders);

    using RSA rsa = RSA.Create(2048);
    RSAParameters key = rsa.ExportParameters(false);
    foreach (ActivityIdFormat format in new[]
    {
        ActivityIdFormat.W3C,
        ActivityIdFormat.Hierarchical,
    })
    {
        IReadOnlySet<string> certificateHeaders = await CaptureLoopbackHeadersAsync(
            async endpoint =>
            {
                AccessEdgeConfiguration baseConfiguration = TestConfiguration();
                AccessEdgeConfiguration loopbackConfiguration = new(
                    baseConfiguration.PublicHost,
                    baseConfiguration.TeamDomain,
                    baseConfiguration.Audience,
                    baseConfiguration.Issuer,
                    endpoint);
                using SocketsHttpHandler handler = AccessEdgeHttpTransport.CreateCertificateHandler();
                True(handler.ActivityHeadersPropagator is null);
                using HttpClient client = new(handler);
                CloudflareAccessSigningKeyProvider provider = new(
                    loopbackConfiguration,
                    client,
                    new MutableTimeProvider(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000)));
                await WithHostileActivityAsync(format, async () =>
                {
                    True(await provider.GetAsync("key-1", CancellationToken.None) is not null);
                });
            },
            Jwks("key-1", key));
        AssertTraceHeadersAbsent(certificateHeaders);
    }
}

static async Task TestProxyBypassesAsync()
{
    AccessEdgeConfiguration configuration = TestConfiguration();
    CountingHandler handler = new();
    using HttpClient upstream = new(handler);
    BuildGhostAccessProxy proxy = new(configuration, new FixedValidator(true), upstream);

    foreach ((string host, string method, string path, Action<DefaultHttpContext>? mutate) in new[]
    {
        ("wrong.chummer.run", "GET", "/api/workspaces/runner-1", (Action<DefaultHttpContext>?)null),
        (configuration.PublicHost, "POST", "/api/internal/build-ghost/tool/resolve", null),
        (configuration.PublicHost, "POST", "/api/v2/ai/build-ghost/tool", null),
        (configuration.PublicHost, "PUT", "/api/workspaces/runner-1", null),
        (configuration.PublicHost, "GET", "/api/workspaces/runner-1", context => context.Request.QueryString = new QueryString("?bypass=1")),
        (configuration.PublicHost, "GET", "/api/workspaces/runner-1", context => context.Request.Headers.Remove(BuildGhostAccessProxy.JwtAssertionHeader)),
        (configuration.PublicHost, "GET", "/api/workspaces/runner-1", context => context.Request.Headers[BuildGhostAccessProxy.AuthenticatedEmailHeader] = new StringValues(["runner@example.com", "attacker@example.com"])),
    })
    {
        DefaultHttpContext context = AdmittedContext(path, method);
        context.Request.Headers.Host = host;
        mutate?.Invoke(context);
        await proxy.HandleAsync(context);
        True(context.Response.StatusCode is StatusCodes.Status404NotFound or StatusCodes.Status401Unauthorized);
        Equal("no-store", context.Response.Headers.CacheControl.ToString());
    }
    Equal(0, handler.Calls);

    DefaultHttpContext rejected = AdmittedContext("/api/workspaces/runner-1", "GET");
    BuildGhostAccessProxy rejecting = new(configuration, new FixedValidator(false), upstream);
    await rejecting.HandleAsync(rejected);
    Equal(StatusCodes.Status401Unauthorized, rejected.Response.StatusCode);
    Equal(0, handler.Calls);
}

static async Task TestProxyForwardingAsync()
{
    AccessEdgeConfiguration configuration = TestConfiguration();
    CapturingHandler handler = new();
    using HttpClient upstream = new(handler);
    BuildGhostAccessProxy proxy = new(configuration, new FixedValidator(true), upstream);
    DefaultHttpContext context = AdmittedContext("/api/workspaces/import", "POST");
    context.Request.ContentType = "application/json";
    byte[] body = "{\"payload\":true}"u8.ToArray();
    context.Request.Body = new MemoryStream(body);
    context.Request.ContentLength = body.Length;
    context.Request.Headers[BuildGhostAccessProxy.OwnerHeader] = "attacker@example.com";
    context.Request.Headers[BuildGhostAccessProxy.PortalOwnerSignatureHeader] = "forged";
    context.Response.Body = new MemoryStream();

    await proxy.HandleAsync(context);

    Equal(StatusCodes.Status200OK, context.Response.StatusCode);
    Equal(1, handler.Calls);
    Equal("runner@example.com", handler.Owner);
    False(handler.SawJwt);
    False(handler.SawAuthenticatedEmail);
    False(handler.SawPortalOwner);
    False(handler.SawAuthorization);
    Equal("no-store", context.Response.Headers.CacheControl.ToString());
    False(context.Response.Headers.ContainsKey("Set-Cookie"));
    Equal("\"rev-1\"", context.Response.Headers.ETag.ToString());
    context.Response.Body.Position = 0;
    using StreamReader reader = new(context.Response.Body, Encoding.UTF8);
    Equal("{\"ok\":true}", await reader.ReadToEndAsync());
}

static DefaultHttpContext AdmittedContext(string path, string method)
{
    DefaultHttpContext context = new();
    context.Request.Method = method;
    context.Request.Path = path;
    context.Request.Headers.Host = "ghost.chummer.run";
    context.Request.Headers[BuildGhostAccessProxy.AuthenticatedEmailHeader] = "runner@example.com";
    context.Request.Headers[BuildGhostAccessProxy.JwtAssertionHeader] = "signed.assertion.value";
    context.Features.Get<IHttpRequestFeature>()!.RawTarget = path;
    return context;
}

static AccessEdgeConfiguration TestConfiguration()
    => AccessEdgeConfiguration.Create(
        "ghost.chummer.run",
        "example-team.cloudflareaccess.com",
        TestAudience);

static string Token(
    RSA rsa,
    string keyId,
    AccessEdgeConfiguration configuration,
    string email,
    long issuedAt,
    long expiresAt,
    string? issuer = null,
    string? audience = null,
    long? notBefore = null,
    string tokenType = "app")
{
    Dictionary<string, object> payload = new(StringComparer.Ordinal)
    {
        ["iss"] = issuer ?? configuration.Issuer.AbsoluteUri.TrimEnd('/'),
        ["aud"] = new[] { audience ?? configuration.Audience },
        ["type"] = tokenType,
        ["email"] = email,
        ["iat"] = issuedAt,
        ["exp"] = expiresAt,
    };
    if (notBefore is not null)
    {
        payload["nbf"] = notBefore.Value;
    }
    return TokenFromRawPayload(rsa, keyId, JsonSerializer.Serialize(payload));
}

static string TokenFromRawPayload(RSA rsa, string keyId, string payload)
{
    string header = JsonSerializer.Serialize(new Dictionary<string, string>
    {
        ["alg"] = "RS256",
        ["kid"] = keyId,
        ["typ"] = "JWT",
    });
    string encodedHeader = Base64Url(Encoding.UTF8.GetBytes(header));
    string encodedPayload = Base64Url(Encoding.UTF8.GetBytes(payload));
    byte[] signed = Encoding.ASCII.GetBytes($"{encodedHeader}.{encodedPayload}");
    byte[] signature = rsa.SignData(
        signed,
        HashAlgorithmName.SHA256,
        RSASignaturePadding.Pkcs1);
    return $"{encodedHeader}.{encodedPayload}.{Base64Url(signature)}";
}

static string Base64Url(byte[] bytes)
    => Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');

static string Jwks(string keyId, RSAParameters parameters)
    => JsonSerializer.Serialize(new
    {
        keys = new[]
        {
            new
            {
                kty = "RSA",
                kid = keyId,
                use = "sig",
                alg = "RS256",
                n = Base64Url(parameters.Modulus!),
                e = Base64Url(parameters.Exponent!),
            },
        },
    });

static HttpResponseMessage JwksResponse(string json)
    => new(HttpStatusCode.OK)
    {
        Content = new StringContent(json, Encoding.UTF8, "application/json"),
    };

static async Task<IReadOnlySet<string>> CaptureLoopbackHeadersAsync(
    Func<Uri, Task> send,
    string responseBody)
{
    TcpListener listener = new(IPAddress.Loopback, 0);
    listener.Start(1);
    try
    {
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        Uri endpoint = new($"http://127.0.0.1:{port}/capture", UriKind.Absolute);
        Task<IReadOnlySet<string>> capture = CaptureOneRequestAsync(listener, responseBody);
        await send(endpoint);
        return await capture;
    }
    finally
    {
        listener.Stop();
    }
}

static async Task<IReadOnlySet<string>> CaptureOneRequestAsync(
    TcpListener listener,
    string responseBody)
{
    using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));
    using TcpClient connection = await listener.AcceptTcpClientAsync(timeout.Token);
    await using NetworkStream stream = connection.GetStream();
    byte[] buffer = new byte[64 * 1024];
    int total = 0;
    int headerEnd = -1;
    while (total < buffer.Length)
    {
        int read = await stream.ReadAsync(
            buffer.AsMemory(total, buffer.Length - total),
            timeout.Token);
        if (read == 0)
        {
            break;
        }
        total += read;
        headerEnd = Encoding.ASCII.GetString(buffer, 0, total)
            .IndexOf("\r\n\r\n", StringComparison.Ordinal);
        if (headerEnd >= 0)
        {
            break;
        }
    }
    True(headerEnd >= 0, "loopback request headers were incomplete");
    string headerBlock = Encoding.ASCII.GetString(buffer, 0, headerEnd);
    HashSet<string> names = headerBlock.Split("\r\n", StringSplitOptions.None)
        .Skip(1)
        .Select(static line => line.Split(':', 2)[0])
        .ToHashSet(StringComparer.OrdinalIgnoreCase);

    byte[] body = Encoding.UTF8.GetBytes(responseBody);
    string responseHeaders =
        $"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {body.Length}\r\nConnection: close\r\n\r\n";
    await stream.WriteAsync(Encoding.ASCII.GetBytes(responseHeaders), timeout.Token);
    await stream.WriteAsync(body, timeout.Token);
    await stream.FlushAsync(timeout.Token);
    return names;
}

static async Task WithHostileActivityAsync(
    ActivityIdFormat format,
    Func<Task> action)
{
    using Activity activity = new Activity("hostile-edge-context").SetIdFormat(format);
    if (format == ActivityIdFormat.W3C)
    {
        activity.SetParentId(
            "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01");
        activity.TraceStateString = "vendor=hostile";
    }
    else
    {
        activity.SetParentId("|hostile.root.");
    }
    activity.AddBaggage("owner", "hostile");
    activity.Start();
    try
    {
        await action();
    }
    finally
    {
        activity.Stop();
    }
}

static void AssertTraceHeadersAbsent(IReadOnlySet<string> headerNames)
{
    foreach (string forbidden in new[]
    {
        "traceparent",
        "tracestate",
        "baggage",
        "Request-Id",
        "Correlation-Context",
    })
    {
        False(headerNames.Contains(forbidden), $"activity header crossed boundary: {forbidden}");
    }
}

static void True(bool condition, string? message = null)
{
    if (!condition)
    {
        throw new InvalidOperationException(message ?? "expected true");
    }
}

static void False(bool condition, string? message = null) => True(!condition, message ?? "expected false");

static void Equal<T>(T expected, T actual)
{
    if (!EqualityComparer<T>.Default.Equals(expected, actual))
    {
        throw new InvalidOperationException($"expected={expected} actual={actual}");
    }
}

static void Throws<T>(Action action) where T : Exception
{
    try
    {
        action();
    }
    catch (T)
    {
        return;
    }
    throw new InvalidOperationException($"expected exception {typeof(T).Name}");
}

sealed class StaticKeyProvider(CloudflareAccessSigningKey key) : ICloudflareAccessSigningKeyProvider
{
    public ValueTask<CloudflareAccessSigningKey?> GetAsync(
        string keyId,
        CancellationToken cancellationToken)
        => ValueTask.FromResult<CloudflareAccessSigningKey?>(
            string.Equals(keyId, key.KeyId, StringComparison.Ordinal) ? key : null);
}

sealed class FixedTimeProvider(DateTimeOffset now) : TimeProvider
{
    public override DateTimeOffset GetUtcNow() => now;
}

sealed class MutableTimeProvider(DateTimeOffset now) : TimeProvider
{
    private DateTimeOffset _now = now;

    public override DateTimeOffset GetUtcNow() => _now;

    public void Advance(TimeSpan duration) => _now = _now.Add(duration);
}

sealed class FixedValidator(bool result) : ICloudflareAccessTokenValidator
{
    public ValueTask<bool> ValidateAsync(
        string assertion,
        string authenticatedEmail,
        CancellationToken cancellationToken)
        => ValueTask.FromResult(result);
}

sealed class CountingHandler : HttpMessageHandler
{
    public int Calls { get; private set; }

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        Calls++;
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
    }
}

sealed class CapturingHandler : HttpMessageHandler
{
    public int Calls { get; private set; }
    public string? Owner { get; private set; }
    public bool SawJwt { get; private set; }
    public bool SawAuthenticatedEmail { get; private set; }
    public bool SawPortalOwner { get; private set; }
    public bool SawAuthorization { get; private set; }

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        Calls++;
        Owner = request.Headers.GetValues(BuildGhostAccessProxy.OwnerHeader).Single();
        SawJwt = request.Headers.Contains(BuildGhostAccessProxy.JwtAssertionHeader);
        SawAuthenticatedEmail = request.Headers.Contains(BuildGhostAccessProxy.AuthenticatedEmailHeader);
        SawPortalOwner = request.Headers.Contains(BuildGhostAccessProxy.PortalOwnerHeader);
        SawAuthorization = request.Headers.Authorization is not null;
        Equal("{\"payload\":true}", await request.Content!.ReadAsStringAsync(cancellationToken));
        HttpResponseMessage response = new(HttpStatusCode.OK)
        {
            Content = new StringContent("{\"ok\":true}", Encoding.UTF8, "application/json"),
        };
        response.Headers.ETag = new System.Net.Http.Headers.EntityTagHeaderValue("\"rev-1\"");
        response.Headers.TryAddWithoutValidation("Set-Cookie", "should-not-cross=1");
        return response;
    }
}

sealed class FixedResponseHandler(Func<HttpRequestMessage, HttpResponseMessage> responseFactory)
    : HttpMessageHandler
{
    public List<Uri> RequestedUris { get; } = [];
    public List<HttpMethod> Methods { get; } = [];

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        RequestedUris.Add(request.RequestUri!);
        Methods.Add(request.Method);
        return Task.FromResult(responseFactory(request));
    }
}
}
