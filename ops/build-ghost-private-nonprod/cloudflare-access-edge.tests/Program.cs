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
    private const string TestToolContractDigest =
        "sha256:af7b643855bbc2220be40bfadc8cb1e89ecdc324a787c771a353d74e85f01104";

    public static async Task<int> Main()
    {
        List<(string Name, Func<Task> Run)> tests =
        [
            ("configuration is explicit and sentinel-blocked", TestConfigurationAsync),
            ("route surface is an exact user-facing allowlist", TestRouteAllowlistAsync),
            ("Access headers require canonical single values", TestHeaderCardinalityAsync),
            ("browser Access cookie is assertion-bound and hostile forms fail closed", TestAccessCookieCompatibilityAsync),
            ("upstream request overwrites identity and strips authority headers", TestUpstreamSanitizationAsync),
            ("JWT binds signature issuer audience type lifetime and email", TestJwtValidationAsync),
            ("signing-key retrieval is exact bounded and redirect closed", TestSigningKeyRetrievalAsync),
            ("signing-key cache refresh rotation failure and concurrency are closed", TestSigningKeyCacheAsync),
            ("real outbound handlers suppress all activity propagation", TestActivityHeaderIsolationAsync),
            ("proxy rejects bypasses before upstream", TestProxyBypassesAsync),
            ("proxy forwards one admitted request without security header leakage", TestProxyForwardingAsync),
            ("owner-bound registry caps lifetime cardinality and concurrent claims", TestOwnerBoundRegistryBoundsAsync),
            ("owner-bound grant errors are bounded before status forwarding", TestOwnerBoundGrantResponseBoundsAsync),
            ("owner-bound v2 broker issues dispatches once and returns deterministic packet", TestOwnerBoundProviderToolAsync),
            ("owner-bound v2 broker fails closed across owner replay expiry restart and revocation", TestOwnerBoundProviderTerminalBehaviorAsync),
            ("owner-bound v2 broker rejects hostile contract and body ambiguity before dispatch", TestOwnerBoundProviderHostileInputsAsync),
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
    Equal(TestToolContractDigest, configuration.ToolContractDigest);
    Equal(
        "https://example-team.cloudflareaccess.com/cdn-cgi/access/certs",
        configuration.CertificatesEndpoint.AbsoluteUri);

    Throws<InvalidOperationException>(() => AccessEdgeConfiguration.Create(
        "unconfigured.invalid",
        "example-team.cloudflareaccess.com",
        TestAudience,
        TestToolContractDigest));
    Throws<InvalidOperationException>(() => AccessEdgeConfiguration.Create(
        "ghost.chummer.run",
        "evil.example.com",
        TestAudience,
        TestToolContractDigest));
    Throws<InvalidOperationException>(() => AccessEdgeConfiguration.Create(
        "Ghost.chummer.run",
        "example-team.cloudflareaccess.com",
        TestAudience,
        TestToolContractDigest));
    Throws<InvalidOperationException>(() => AccessEdgeConfiguration.Create(
        "ghost.chummer.run",
        "example-team.cloudflareaccess.com",
        "",
        TestToolContractDigest));
    Throws<InvalidOperationException>(() => AccessEdgeConfiguration.Create(
        "ghost.chummer.run",
        "example-team.cloudflareaccess.com",
        TestAudience,
        "sha256:ABC"));
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
    True(BuildGhostAccessProxy.TryMatchRoute(
        "POST", BuildGhostProviderToolRequestContract.Path, out BuildGhostAccessRoute provider));
    Equal(BuildGhostAccessRouteKind.ProviderToolV2, provider.Kind);
    Equal((long)BuildGhostProviderToolRequestContract.MaximumBodyBytes, provider.MaximumBodyBytes);

    foreach ((string method, string path) in new[]
    {
        ("POST", "/api/internal/build-ghost/tool/resolve"),
        ("POST", "/api/v1/ai/build-ghost/tool"),
        ("POST", "/api/v2/ai/build-ghost/explain"),
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

    context.Request.Headers.Cookie =
        $"{BuildGhostAccessProxy.AccessAuthorizationCookieName}={assertion}";
    True(BuildGhostAccessProxy.TryReadAccessHeaders(context.Request, out _, out _));

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

static async Task TestAccessCookieCompatibilityAsync()
{
    const string assertion = "signed.assertion.value";
    AccessEdgeConfiguration configuration = TestConfiguration();
    CountingHandler handler = new();
    using HttpClient upstream = new(handler);
    BuildGhostAccessProxy proxy = new(configuration, new FixedValidator(true), upstream);

    foreach (string hostileCookie in new[]
    {
        "CF_Authorization=forged.assertion.value",
        $"cf_authorization={assertion}",
        $"CF-Authorization={assertion}",
        $"CF_Authorization=\"{assertion}\"",
        $"CF_Authorization={assertion};",
        $"CF_Authorization={assertion}; CF_Binding=unexpected",
        $"session=unexpected; CF_Authorization={assertion}",
        $"CF_Authorization={assertion}; CF_Authorization={assertion}",
        $"CF_Authorization={assertion},session=unexpected",
        $" CF_Authorization={assertion}",
        $"CF_Authorization ={assertion}",
        $"CF_Authorization={assertion} ",
        $"CF_Authorization={assertion}\t",
        $"CF_Authorization={assertion}\r\nX-Smuggled: yes",
        $"CF_Authorization={assertion}\0",
        $"CF_Authorization={new string('a', CloudflareAccessJwtValidator.MaximumAssertionBytes + 1)}",
    })
    {
        DefaultHttpContext rejected = AdmittedContext("/api/workspaces/runner-1", "GET");
        rejected.Request.Headers.Cookie = hostileCookie;
        rejected.Response.Body = new MemoryStream();
        await proxy.HandleAsync(rejected);
        Equal(StatusCodes.Status401Unauthorized, rejected.Response.StatusCode);
        Equal("{\"error\":\"cloudflare_access_required\"}", await ResponseBodyAsync(rejected));
    }

    DefaultHttpContext duplicateHeader = AdmittedContext("/api/workspaces/runner-1", "GET");
    duplicateHeader.Request.Headers.Cookie = new StringValues([
        $"CF_Authorization={assertion}",
        $"CF_Authorization={assertion}",
    ]);
    duplicateHeader.Response.Body = new MemoryStream();
    await proxy.HandleAsync(duplicateHeader);
    Equal(StatusCodes.Status401Unauthorized, duplicateHeader.Response.StatusCode);
    Equal("{\"error\":\"cloudflare_access_required\"}", await ResponseBodyAsync(duplicateHeader));
    Equal(0, handler.Calls);
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

    GatedResponseHandler sameUnknownHandler = new(
        _ => JwksResponse(Jwks("key-1", first)),
        gatedCall: 2);
    using HttpClient sameUnknownClient = new(sameUnknownHandler);
    MutableTimeProvider sameUnknownClock = new(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000));
    CloudflareAccessSigningKeyProvider sameUnknownProvider = new(
        configuration,
        sameUnknownClient,
        sameUnknownClock);
    True(await sameUnknownProvider.GetAsync("key-1", CancellationToken.None) is not null);
    CloudflareAccessSigningKey?[] sameUnknown = await GetConcurrentWaveAsync(
        sameUnknownProvider,
        sameUnknownHandler,
        _ => "unknown");
    True(sameUnknown.All(static key => key is null));
    Equal(2, sameUnknownHandler.Calls);
    sameUnknownClock.Advance(TimeSpan.FromSeconds(
        CloudflareAccessSigningKeyProvider.RefreshRetrySeconds - 1));
    True(await sameUnknownProvider.GetAsync("unknown", CancellationToken.None) is null);
    Equal(2, sameUnknownHandler.Calls);
    sameUnknownClock.Advance(TimeSpan.FromSeconds(2));
    True(await sameUnknownProvider.GetAsync("unknown", CancellationToken.None) is null);
    Equal(3, sameUnknownHandler.Calls);

    GatedResponseHandler differentUnknownHandler = new(
        _ => JwksResponse(Jwks("key-1", first)),
        gatedCall: 2);
    using HttpClient differentUnknownClient = new(differentUnknownHandler);
    CloudflareAccessSigningKeyProvider differentUnknownProvider = new(
        configuration,
        differentUnknownClient,
        new MutableTimeProvider(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000)));
    True(await differentUnknownProvider.GetAsync("key-1", CancellationToken.None) is not null);
    CloudflareAccessSigningKey?[] differentUnknown = await GetConcurrentWaveAsync(
        differentUnknownProvider,
        differentUnknownHandler,
        index => $"unknown-{index}");
    True(differentUnknown.All(static key => key is null));
    Equal(2, differentUnknownHandler.Calls);

    GatedResponseHandler failedInitialHandler = new(
        _ => new HttpResponseMessage(HttpStatusCode.ServiceUnavailable),
        gatedCall: 1);
    using HttpClient failedInitialClient = new(failedInitialHandler);
    MutableTimeProvider failedInitialClock = new(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000));
    CloudflareAccessSigningKeyProvider failedInitialProvider = new(
        configuration,
        failedInitialClient,
        failedInitialClock);
    CloudflareAccessSigningKey?[] failedInitial = await GetConcurrentWaveAsync(
        failedInitialProvider,
        failedInitialHandler,
        index => $"initial-{index}");
    True(failedInitial.All(static key => key is null));
    Equal(1, failedInitialHandler.Calls);
    failedInitialClock.Advance(TimeSpan.FromSeconds(
        CloudflareAccessSigningKeyProvider.RefreshRetrySeconds - 1));
    True(await failedInitialProvider.GetAsync("initial-retry", CancellationToken.None) is null);
    Equal(1, failedInitialHandler.Calls);
    failedInitialClock.Advance(TimeSpan.FromSeconds(2));
    True(await failedInitialProvider.GetAsync("initial-retry", CancellationToken.None) is null);
    Equal(2, failedInitialHandler.Calls);

    GatedResponseHandler failedWarmUnknownHandler = new(
        call => call == 1
            ? JwksResponse(Jwks("key-1", first))
            : new HttpResponseMessage(HttpStatusCode.ServiceUnavailable),
        gatedCall: 2);
    using HttpClient failedWarmUnknownClient = new(failedWarmUnknownHandler);
    CloudflareAccessSigningKeyProvider failedWarmUnknownProvider = new(
        configuration,
        failedWarmUnknownClient,
        new MutableTimeProvider(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000)));
    True(await failedWarmUnknownProvider.GetAsync("key-1", CancellationToken.None) is not null);
    CloudflareAccessSigningKey?[] failedWarmUnknown = await GetConcurrentWaveAsync(
        failedWarmUnknownProvider,
        failedWarmUnknownHandler,
        _ => "unknown");
    True(failedWarmUnknown.All(static key => key is null));
    True(await failedWarmUnknownProvider.GetAsync("key-1", CancellationToken.None) is not null);
    Equal(2, failedWarmUnknownHandler.Calls);

    GatedResponseHandler rotationHandler = new(call =>
        JwksResponse(call == 1
            ? Jwks("key-1", first)
            : Jwks("key-1", second)),
        gatedCall: 2);
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
    CloudflareAccessSigningKey?[] afterRotation = await GetConcurrentWaveAsync(
        rotationProvider,
        rotationHandler,
        _ => "key-1");
    True(beforeRotation is not null && afterRotation.All(static key => key is not null));
    True(beforeRotation!.Modulus.SequenceEqual(first.Modulus!));
    True(afterRotation.All(key => key!.Modulus.SequenceEqual(second.Modulus!)));
    Equal(2, rotationHandler.Calls);

    GatedResponseHandler failedRefreshHandler = new(call =>
        call == 1
            ? JwksResponse(Jwks("key-1", first))
            : new HttpResponseMessage(HttpStatusCode.ServiceUnavailable),
        gatedCall: 2);
    using HttpClient failedRefreshClient = new(failedRefreshHandler);
    MutableTimeProvider failedRefreshClock = new(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000));
    CloudflareAccessSigningKeyProvider failedRefreshProvider = new(
        configuration,
        failedRefreshClient,
        failedRefreshClock);
    True(await failedRefreshProvider.GetAsync("key-1", CancellationToken.None) is not null);
    failedRefreshClock.Advance(TimeSpan.FromMinutes(11));
    CloudflareAccessSigningKey?[] failedRefresh = await GetConcurrentWaveAsync(
        failedRefreshProvider,
        failedRefreshHandler,
        _ => "key-1");
    True(failedRefresh.All(static key => key is null));
    True(await failedRefreshProvider.GetAsync("key-1", CancellationToken.None) is null);
    Equal(2, failedRefreshHandler.Calls);

    GatedResponseHandler newKidHandler = new(call =>
        JwksResponse(call == 1
            ? Jwks("key-1", first)
            : Jwks("key-2", second)),
        gatedCall: 2);
    using HttpClient newKidClient = new(newKidHandler);
    CloudflareAccessSigningKeyProvider newKidProvider = new(
        configuration,
        newKidClient,
        new MutableTimeProvider(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000)));
    True(await newKidProvider.GetAsync("key-1", CancellationToken.None) is not null);
    CloudflareAccessSigningKey?[] newKid = await GetConcurrentWaveAsync(
        newKidProvider,
        newKidHandler,
        _ => "key-2");
    True(newKid.All(static key => key is not null));
    True(newKid.All(key => key!.Modulus.SequenceEqual(second.Modulus!)));
    Equal(2, newKidHandler.Calls);

    GatedResponseHandler concurrentHandler = new(
        _ => JwksResponse(Jwks("key-1", first)),
        gatedCall: 1);
    using HttpClient concurrentClient = new(concurrentHandler);
    CloudflareAccessSigningKeyProvider concurrentProvider = new(
        configuration,
        concurrentClient,
        new MutableTimeProvider(DateTimeOffset.FromUnixTimeSeconds(2_000_000_000)));
    CloudflareAccessSigningKey?[] concurrent = await GetConcurrentWaveAsync(
        concurrentProvider,
        concurrentHandler,
        _ => "key-1");
    True(concurrent.All(static key => key is not null));
    Equal(1, concurrentHandler.Calls);
}

static async Task<CloudflareAccessSigningKey?[]> GetConcurrentWaveAsync(
    CloudflareAccessSigningKeyProvider provider,
    GatedResponseHandler handler,
    Func<int, string> keyId)
{
    Task<CloudflareAccessSigningKey?> first = provider
        .GetAsync(keyId(0), CancellationToken.None)
        .AsTask();
    await handler.WaitForGateAsync();
    Task<CloudflareAccessSigningKey?>[] waiters = Enumerable.Range(1, 31)
        .Select(index => provider.GetAsync(keyId(index), CancellationToken.None).AsTask())
        .ToArray();
    handler.ReleaseGate();
    return await Task.WhenAll(waiters.Prepend(first));
}

static async Task TestActivityHeaderIsolationAsync()
{
    foreach (ActivityIdFormat format in new[]
    {
        ActivityIdFormat.W3C,
        ActivityIdFormat.Hierarchical,
    })
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
                await WithHostileActivityAsync(format, async () =>
                {
                    using HttpResponseMessage response = await client.SendAsync(request);
                    Equal(HttpStatusCode.OK, response.StatusCode);
                });
            },
            "{\"ok\":true}");
        AssertTraceHeadersAbsent(presentationHeaders);

        IReadOnlySet<string> aiHeaders = await CaptureLoopbackHeadersAsync(
            async endpoint =>
            {
                using SocketsHttpHandler handler = AccessEdgeHttpTransport.CreateAiHandler();
                True(handler.ActivityHeadersPropagator is null);
                using HttpClient client = new(handler);
                using HttpRequestMessage request = BuildGhostAccessProxy.CreateProviderToolUpstreamRequest(
                    incoming.Request,
                    "{}"u8.ToArray(),
                    TestToolContractDigest);
                request.RequestUri = endpoint;
                await WithHostileActivityAsync(format, async () =>
                {
                    using HttpResponseMessage response = await client.SendAsync(request);
                    Equal(HttpStatusCode.OK, response.StatusCode);
                });
            },
            "{\"ok\":true}");
        AssertTraceHeadersAbsent(aiHeaders);
    }

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
                    baseConfiguration.ToolContractDigest,
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
        (configuration.PublicHost, "POST", "/api/v2/ai/build-ghost/explain", null),
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
    context.Request.Headers.Cookie =
        $"{BuildGhostAccessProxy.AccessAuthorizationCookieName}=signed.assertion.value";
    context.Response.Body = new MemoryStream();

    await proxy.HandleAsync(context);

    Equal(StatusCodes.Status200OK, context.Response.StatusCode);
    Equal(1, handler.Calls);
    Equal("runner@example.com", handler.Owner);
    False(handler.SawJwt);
    False(handler.SawAuthenticatedEmail);
    False(handler.SawPortalOwner);
    False(handler.SawAuthorization);
    False(handler.SawCookie);
    Equal("no-store", context.Response.Headers.CacheControl.ToString());
    False(context.Response.Headers.ContainsKey("Set-Cookie"));
    Equal("\"rev-1\"", context.Response.Headers.ETag.ToString());
    context.Response.Body.Position = 0;
    using StreamReader reader = new(context.Response.Body, Encoding.UTF8);
    Equal("{\"ok\":true}", await reader.ReadToEndAsync());
}

static async Task TestOwnerBoundRegistryBoundsAsync()
{
    DateTimeOffset now = DateTimeOffset.Parse("2026-08-24T11:00:00Z");
    MutableTimeProvider clock = new(now);
    string digest = $"sha256:{new string('9', 64)}";
    const string owner = "runner@example.com";
    BuildGhostOwnerBoundGrantRegistry registry = new(clock);

    False(registry.TryRegister(
        CanonicalPacketKey(0),
        owner,
        digest,
        now));
    False(registry.TryRegister(
        CanonicalPacketKey(0),
        owner,
        digest,
        now.Add(BuildGhostOwnerBoundGrantRegistry.MaximumGrantLifetime).AddTicks(1)));
    True(registry.TryRegister(
        CanonicalPacketKey(0),
        owner,
        digest,
        now.Add(BuildGhostOwnerBoundGrantRegistry.MaximumGrantLifetime)));
    False(registry.TryRegister(
        CanonicalPacketKey(0),
        "other@example.com",
        digest,
        now.Add(BuildGhostOwnerBoundGrantRegistry.MaximumGrantLifetime)));

    for (int index = 1; index < BuildGhostOwnerBoundGrantRegistry.MaximumBindings; index++)
    {
        True(registry.TryRegister(
            CanonicalPacketKey(index),
            owner,
            digest,
            now.Add(BuildGhostOwnerBoundGrantRegistry.MaximumGrantLifetime)),
            $"binding {index} should fit exact registry capacity");
    }
    Equal(BuildGhostOwnerBoundGrantRegistry.MaximumBindings, registry.Count);
    False(registry.TryRegister(
        CanonicalPacketKey(BuildGhostOwnerBoundGrantRegistry.MaximumBindings),
        owner,
        digest,
        now.Add(BuildGhostOwnerBoundGrantRegistry.MaximumGrantLifetime)));

    clock.Advance(BuildGhostOwnerBoundGrantRegistry.MaximumGrantLifetime);
    True(registry.TryRegister(
        CanonicalPacketKey(BuildGhostOwnerBoundGrantRegistry.MaximumBindings),
        owner,
        digest,
        clock.GetUtcNow().Add(BuildGhostOwnerBoundGrantRegistry.MaximumGrantLifetime)));
    Equal(1, registry.Count);
    False(registry.TryClaim(CanonicalPacketKey(0), owner, digest));

    BuildGhostOwnerBoundGrantRegistry claimRegistry = new(clock);
    string claimKey = CanonicalPacketKey(BuildGhostOwnerBoundGrantRegistry.MaximumBindings + 1);
    True(claimRegistry.TryRegister(
        claimKey,
        owner,
        digest,
        clock.GetUtcNow().AddMinutes(1)));
    bool[] claimResults = await Task.WhenAll(
        Enumerable.Range(0, 64)
            .Select(_ => Task.Run(() => claimRegistry.TryClaim(claimKey, owner, digest))));
    Equal(1, claimResults.Count(static claimed => claimed));
    Equal(0, claimRegistry.Count);

    BuildGhostOwnerBoundGrantRegistry dispatchRegistry = new(clock);
    string dispatchKey = CanonicalPacketKey(BuildGhostOwnerBoundGrantRegistry.MaximumBindings + 2);
    True(dispatchRegistry.TryRegister(
        dispatchKey,
        owner,
        digest,
        clock.GetUtcNow().AddMinutes(1)));
    using HttpClient presentation = new(new CountingHandler());
    ConcurrentProviderToolHandler aiHandler = new(digest);
    using HttpClient ai = new(aiHandler);
    BuildGhostAccessProxy proxy = new(
        TestConfiguration(),
        new FixedValidator(true),
        presentation,
        ai,
        dispatchRegistry);
    DefaultHttpContext[] contexts = Enumerable.Range(0, 64)
        .Select(_ => ProviderRequestContext(dispatchKey, digest))
        .ToArray();
    Task[] dispatches = contexts.Select(proxy.HandleAsync).ToArray();
    await aiHandler.WaitForCallAsync();
    aiHandler.Release();
    await Task.WhenAll(dispatches);
    Equal(1, aiHandler.Calls);
    Equal(1, contexts.Count(static context => context.Response.StatusCode == StatusCodes.Status200OK));
    Equal(63, contexts.Count(static context => context.Response.StatusCode == StatusCodes.Status410Gone));
    Equal(0, dispatchRegistry.Count);
}

static async Task TestOwnerBoundGrantResponseBoundsAsync()
{
    DateTimeOffset now = DateTimeOffset.Parse("2026-08-24T11:30:00Z");
    MutableTimeProvider clock = new(now);
    const string leakedKey = "HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHc";
    byte[] hostileBody = Encoding.UTF8.GetBytes(
        $"{{\"packetAccessKey\":\"{leakedKey}\",\"padding\":\"{new string('x', 17 * 1024)}\"}}");
    bool responseHadNoDeclaredLength = false;
    FixedResponseHandler presentationHandler = new(_ =>
    {
        StreamContent content = new(new NonSeekableReadStream(hostileBody));
        content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/json");
        responseHadNoDeclaredLength = content.Headers.ContentLength is null;
        return new HttpResponseMessage(HttpStatusCode.Conflict)
        {
            Content = content,
        };
    });
    using HttpClient presentation = new(presentationHandler);
    using HttpClient ai = new(new CountingHandler());
    BuildGhostOwnerBoundGrantRegistry registry = new(clock);
    BuildGhostAccessProxy proxy = new(
        TestConfiguration(),
        new FixedValidator(true),
        presentation,
        ai,
        registry);
    DefaultHttpContext context = GrantRequestContext();

    await proxy.HandleAsync(context);

    True(responseHadNoDeclaredLength);
    Equal(StatusCodes.Status502BadGateway, context.Response.StatusCode);
    Equal(0, registry.Count);
    Equal(
        "{\"error\":\"private_tool_upstream_response_invalid\"}",
        await ResponseBodyAsync(context));
    False((await ResponseBodyAsync(context)).Contains(leakedKey, StringComparison.Ordinal));
    Equal("no-store", context.Response.Headers.CacheControl.ToString());
}

static async Task TestOwnerBoundProviderToolAsync()
{
    DateTimeOffset now = DateTimeOffset.Parse("2026-08-24T12:00:00Z");
    MutableTimeProvider clock = new(now);
    const string key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    string digest = $"sha256:{new string('a', 64)}";
    GrantIssuanceHandler presentationHandler = new();
    presentationHandler.Enqueue(new TestGrant(key, digest, now.AddMinutes(5)));
    ProviderToolHandler aiHandler = new();
    aiHandler.Enqueue(new TestProviderResponse(
        HttpStatusCode.OK,
        "{\"schema\":\"chummer.build_ghost_analysis.v1\",\"deterministicFallbackText\":\"grounded local answer\"}",
        digest));
    using HttpClient presentation = new(presentationHandler);
    using HttpClient ai = new(aiHandler);
    BuildGhostOwnerBoundGrantRegistry registry = new(clock);
    BuildGhostAccessProxy proxy = new(
        TestConfiguration(),
        new FixedValidator(true),
        presentation,
        ai,
        registry);

    DefaultHttpContext issue = GrantRequestContext();
    await proxy.HandleAsync(issue);
    Equal(StatusCodes.Status200OK, issue.Response.StatusCode);
    Equal(1, presentationHandler.Calls);
    Equal("runner@example.com", presentationHandler.Owner);
    False(presentationHandler.SawAccessAssertion);
    False(presentationHandler.SawAuthorization);
    Equal(1, registry.Count);
    string issueBody = await ResponseBodyAsync(issue);
    True(issueBody.Contains(key, StringComparison.Ordinal));
    Equal("no-store", issue.Response.Headers.CacheControl.ToString());

    DefaultHttpContext consume = ProviderRequestContext(key, digest);
    consume.Request.Headers.Cookie =
        $"{BuildGhostAccessProxy.AccessAuthorizationCookieName}=signed.assertion.value";
    consume.Request.Headers[BuildGhostAccessProxy.OwnerHeader] = "mallory@example.com";
    consume.Request.Headers["traceparent"] =
        "00-11111111111111111111111111111111-2222222222222222-01";
    consume.Request.Headers["Cf-Connecting-Ip"] = "203.0.113.9";
    await proxy.HandleAsync(consume);
    Equal(StatusCodes.Status200OK, consume.Response.StatusCode);
    Equal(1, aiHandler.Calls);
    Equal(0, registry.Count);
    False(aiHandler.SawOwner);
    False(aiHandler.SawAccessAssertion);
    False(aiHandler.SawAuthenticatedEmail);
    False(aiHandler.SawAuthorization);
    False(aiHandler.SawCookie);
    False(aiHandler.SawTrace);
    False(aiHandler.SawCloudflareHeaders);
    True(aiHandler.SawCanonicalPacketKeyInBody);
    Equal(TestToolContractDigest, aiHandler.ToolContracts.Single());
    True(aiHandler.CacheControlNoStore);
    Equal(BuildGhostProviderToolRequestContract.Path, aiHandler.Paths.Single());
    Equal("no-store", consume.Response.Headers.CacheControl.ToString());
    False(consume.Response.Headers.ContainsKey("Set-Cookie"));
    Equal(digest, consume.Response.Headers["X-Chummer-Build-Ghost-Packet-Digest"].ToString());
    True((await ResponseBodyAsync(consume)).Contains("grounded local answer", StringComparison.Ordinal));

    DefaultHttpContext replay = ProviderRequestContext(key, digest);
    await proxy.HandleAsync(replay);
    Equal(StatusCodes.Status410Gone, replay.Response.StatusCode);
    Equal("{\"error\":\"private-tool-authority-rejected\"}", await ResponseBodyAsync(replay));
    Equal(1, aiHandler.Calls);
}

static async Task TestOwnerBoundProviderTerminalBehaviorAsync()
{
    DateTimeOffset now = DateTimeOffset.Parse("2026-08-24T13:00:00Z");
    MutableTimeProvider clock = new(now);
    string digest = $"sha256:{new string('b', 64)}";
    string ownerKey = $"{new string('B', 42)}E";
    string restartKey = $"{new string('C', 42)}I";
    string expiredKey = $"{new string('D', 42)}M";
    string revokedKey = $"{new string('E', 42)}Q";
    GrantIssuanceHandler presentationHandler = new();
    presentationHandler.Enqueue(new TestGrant(ownerKey, digest, now.AddMinutes(5)));
    presentationHandler.Enqueue(new TestGrant(restartKey, digest, now.AddMinutes(5)));
    presentationHandler.Enqueue(new TestGrant(expiredKey, digest, now.AddMinutes(1)));
    presentationHandler.Enqueue(new TestGrant(revokedKey, digest, now.AddMinutes(5)));
    ProviderToolHandler aiHandler = new();
    aiHandler.Enqueue(new TestProviderResponse(HttpStatusCode.OK, "{\"ok\":true}", digest));
    const string terminalBody = "{\"error\":\"private-tool-authority-rejected\"}";
    aiHandler.Enqueue(new TestProviderResponse(HttpStatusCode.Gone, terminalBody, null));
    using HttpClient presentation = new(presentationHandler);
    using HttpClient ai = new(aiHandler);
    BuildGhostOwnerBoundGrantRegistry registry = new(clock);
    BuildGhostAccessProxy proxy = new(
        TestConfiguration(),
        new FixedValidator(true),
        presentation,
        ai,
        registry);

    await proxy.HandleAsync(GrantRequestContext());
    DefaultHttpContext crossOwner = ProviderRequestContext(ownerKey, digest, "attacker@example.com");
    await proxy.HandleAsync(crossOwner);
    Equal(StatusCodes.Status410Gone, crossOwner.Response.StatusCode);
    Equal(0, aiHandler.Calls);
    Equal(1, registry.Count);

    DefaultHttpContext wrongDigest = ProviderRequestContext(
        ownerKey,
        $"sha256:{new string('f', 64)}");
    await proxy.HandleAsync(wrongDigest);
    Equal(StatusCodes.Status410Gone, wrongDigest.Response.StatusCode);
    Equal(0, aiHandler.Calls);
    Equal(1, registry.Count);

    DefaultHttpContext rightfulOwner = ProviderRequestContext(ownerKey, digest);
    await proxy.HandleAsync(rightfulOwner);
    Equal(StatusCodes.Status200OK, rightfulOwner.Response.StatusCode);
    Equal(1, aiHandler.Calls);

    await proxy.HandleAsync(GrantRequestContext());
    BuildGhostAccessProxy restarted = new(
        TestConfiguration(),
        new FixedValidator(true),
        presentation,
        ai,
        new BuildGhostOwnerBoundGrantRegistry(clock));
    DefaultHttpContext afterRestart = ProviderRequestContext(restartKey, digest);
    await restarted.HandleAsync(afterRestart);
    Equal(StatusCodes.Status410Gone, afterRestart.Response.StatusCode);
    Equal(1, aiHandler.Calls);

    await proxy.HandleAsync(GrantRequestContext());
    clock.Advance(TimeSpan.FromMinutes(2));
    DefaultHttpContext expired = ProviderRequestContext(expiredKey, digest);
    await proxy.HandleAsync(expired);
    Equal(StatusCodes.Status410Gone, expired.Response.StatusCode);
    Equal(1, aiHandler.Calls);

    await proxy.HandleAsync(GrantRequestContext());
    DefaultHttpContext revoked = ProviderRequestContext(revokedKey, digest);
    await proxy.HandleAsync(revoked);
    Equal(StatusCodes.Status410Gone, revoked.Response.StatusCode);
    Equal(terminalBody, await ResponseBodyAsync(revoked));
    Equal("no-store", revoked.Response.Headers.CacheControl.ToString());
    Equal(2, aiHandler.Calls);

    DefaultHttpContext terminalReplay = ProviderRequestContext(revokedKey, digest);
    await proxy.HandleAsync(terminalReplay);
    Equal(revoked.Response.StatusCode, terminalReplay.Response.StatusCode);
    Equal(await ResponseBodyAsync(revoked), await ResponseBodyAsync(terminalReplay));
    Equal(revoked.Response.ContentType, terminalReplay.Response.ContentType);
    Equal(revoked.Response.Headers.CacheControl.ToString(), terminalReplay.Response.Headers.CacheControl.ToString());
    Equal(2, aiHandler.Calls);
}

static async Task TestOwnerBoundProviderHostileInputsAsync()
{
    DateTimeOffset now = DateTimeOffset.Parse("2026-08-24T14:00:00Z");
    MutableTimeProvider clock = new(now);
    const string key = "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFU";
    string digest = $"sha256:{new string('c', 64)}";
    GrantIssuanceHandler presentationHandler = new();
    presentationHandler.Enqueue(new TestGrant(key, digest, now.AddMinutes(5)));
    ProviderToolHandler aiHandler = new();
    aiHandler.Enqueue(new TestProviderResponse(HttpStatusCode.OK, "{\"ok\":true}", digest));
    using HttpClient presentation = new(presentationHandler);
    using HttpClient ai = new(aiHandler);
    BuildGhostOwnerBoundGrantRegistry registry = new(clock);
    BuildGhostAccessProxy proxy = new(
        TestConfiguration(),
        new FixedValidator(true),
        presentation,
        ai,
        registry);
    await proxy.HandleAsync(GrantRequestContext());
    Equal(1, registry.Count);

    async Task AssertRejectedAsync(DefaultHttpContext context, int expectedStatus)
    {
        await proxy.HandleAsync(context);
        Equal(expectedStatus, context.Response.StatusCode);
        Equal("no-store", context.Response.Headers.CacheControl.ToString());
        False((await ResponseBodyAsync(context)).Contains(key, StringComparison.Ordinal));
        Equal(0, aiHandler.Calls);
        Equal(1, registry.Count);
    }

    DefaultHttpContext missingCache = ProviderRequestContext(key, digest);
    missingCache.Request.Headers.Remove("Cache-Control");
    await AssertRejectedAsync(missingCache, StatusCodes.Status401Unauthorized);

    DefaultHttpContext authorization = ProviderRequestContext(key, digest);
    authorization.Request.Headers.Authorization = $"Bearer {key}";
    await AssertRejectedAsync(authorization, StatusCodes.Status401Unauthorized);

    DefaultHttpContext cookie = ProviderRequestContext(key, digest);
    cookie.Request.Headers.Cookie = $"packet_access_key={key}";
    await AssertRejectedAsync(cookie, StatusCodes.Status401Unauthorized);

    DefaultHttpContext wrongContract = ProviderRequestContext(key, digest);
    wrongContract.Request.Headers[BuildGhostAccessProxy.ToolContractHeader] = $"sha256:{new string('d', 64)}";
    await AssertRejectedAsync(wrongContract, StatusCodes.Status401Unauthorized);

    DefaultHttpContext duplicateContract = ProviderRequestContext(key, digest);
    duplicateContract.Request.Headers[BuildGhostAccessProxy.ToolContractHeader] =
        new StringValues([TestToolContractDigest, TestToolContractDigest]);
    await AssertRejectedAsync(duplicateContract, StatusCodes.Status401Unauthorized);

    DefaultHttpContext wrongMedia = ProviderRequestContext(key, digest);
    wrongMedia.Request.ContentType = "application/json; charset=iso-8859-1";
    await AssertRejectedAsync(wrongMedia, StatusCodes.Status415UnsupportedMediaType);

    DefaultHttpContext tooLarge = ProviderRequestContext(key, digest);
    tooLarge.Request.ContentLength = BuildGhostProviderToolRequestContract.MaximumBodyBytes + 1;
    await AssertRejectedAsync(tooLarge, StatusCodes.Status413PayloadTooLarge);

    string validBody = ProviderBody(key, digest);
    DefaultHttpContext unknownField = ProviderRequestContext(
        key,
        digest,
        bodyOverride: validBody[..^1] + ",\"authorization\":\"blocked\"}");
    await AssertRejectedAsync(unknownField, StatusCodes.Status400BadRequest);

    DefaultHttpContext duplicateKey = ProviderRequestContext(
        key,
        digest,
        bodyOverride: validBody.Replace(
            "\"packet_digest\"",
            $"\"packet_access_key\":\"{key}\",\"packet_digest\"",
            StringComparison.Ordinal));
    await AssertRejectedAsync(duplicateKey, StatusCodes.Status400BadRequest);

    DefaultHttpContext wrongSchema = ProviderRequestContext(
        key,
        digest,
        bodyOverride: validBody.Replace(
            BuildGhostProviderToolRequestContract.RequestSchema,
            "chummer.build_ghost.private_tool_request.v1",
            StringComparison.Ordinal));
    await AssertRejectedAsync(wrongSchema, StatusCodes.Status400BadRequest);

    DefaultHttpContext query = ProviderRequestContext(key, digest);
    query.Request.QueryString = new QueryString("?packet_access_key=blocked");
    query.Features.Get<IHttpRequestFeature>()!.RawTarget =
        BuildGhostProviderToolRequestContract.Path + query.Request.QueryString;
    await AssertRejectedAsync(query, StatusCodes.Status404NotFound);

    DefaultHttpContext valid = ProviderRequestContext(key, digest);
    valid.Request.Headers[BuildGhostAccessProxy.OwnerHeader] = "mallory@example.com";
    await proxy.HandleAsync(valid);
    Equal(StatusCodes.Status200OK, valid.Response.StatusCode);
    Equal(1, aiHandler.Calls);
    False(aiHandler.SawOwner);
    False(aiHandler.SawAuthorization);
    False(aiHandler.SawCookie);

    const string malformedGrantKey = "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGY";
    FixedResponseHandler malformedGrant = new(_ => new HttpResponseMessage(HttpStatusCode.OK)
    {
        Content = new StringContent(
            $"{{\"packetAccessKey\":\"{malformedGrantKey}\",\"packetDigest\":\"{digest}\",\"expiresAtUtc\":\"{now.AddMinutes(5):O}\",\"unexpected\":true}}",
            Encoding.UTF8,
            "application/json"),
    });
    using HttpClient malformedPresentation = new(malformedGrant);
    BuildGhostAccessProxy malformedProxy = new(
        TestConfiguration(),
        new FixedValidator(true),
        malformedPresentation,
        ai,
        new BuildGhostOwnerBoundGrantRegistry(clock));
    DefaultHttpContext malformedIssue = GrantRequestContext();
    await malformedProxy.HandleAsync(malformedIssue);
    Equal(StatusCodes.Status502BadGateway, malformedIssue.Response.StatusCode);
    False((await ResponseBodyAsync(malformedIssue)).Contains(malformedGrantKey, StringComparison.Ordinal));
}

static DefaultHttpContext GrantRequestContext(string owner = "runner@example.com")
{
    DefaultHttpContext context = AdmittedContext(
        "/api/workspaces/runner-1/build-ghost/tool-access",
        "POST");
    context.Request.Headers[BuildGhostAccessProxy.AuthenticatedEmailHeader] = owner;
    context.Request.ContentType = "application/json; charset=utf-8";
    byte[] body = "{\"locale\":\"en-US\",\"requestKind\":\"current-build\"}"u8.ToArray();
    context.Request.Body = new MemoryStream(body);
    context.Request.ContentLength = body.Length;
    context.Response.Body = new MemoryStream();
    return context;
}

static DefaultHttpContext ProviderRequestContext(
    string key,
    string digest,
    string owner = "runner@example.com",
    string? bodyOverride = null)
{
    DefaultHttpContext context = AdmittedContext(BuildGhostProviderToolRequestContract.Path, "POST");
    context.Request.Headers[BuildGhostAccessProxy.AuthenticatedEmailHeader] = owner;
    context.Request.Headers.CacheControl = "no-store";
    context.Request.Headers[BuildGhostAccessProxy.ToolContractHeader] = TestToolContractDigest;
    context.Request.ContentType = "application/json";
    byte[] body = Encoding.UTF8.GetBytes(bodyOverride ?? ProviderBody(key, digest));
    context.Request.Body = new MemoryStream(body);
    context.Request.ContentLength = body.Length;
    context.Response.Body = new MemoryStream();
    return context;
}

static string ProviderBody(string key, string digest)
    => JsonSerializer.Serialize(new Dictionary<string, object?>
    {
        ["schema"] = BuildGhostProviderToolRequestContract.RequestSchema,
        ["packet_access_key"] = key,
        ["packet_digest"] = digest,
        ["locale"] = "en-US",
        ["request_kind"] = "current-build",
        ["question"] = "What should I improve?",
    });

static string CanonicalPacketKey(int value)
{
    byte[] material = new byte[32];
    material[^4] = (byte)(value >> 24);
    material[^3] = (byte)(value >> 16);
    material[^2] = (byte)(value >> 8);
    material[^1] = (byte)value;
    return Base64Url(material);
}

static async Task<string> ResponseBodyAsync(DefaultHttpContext context)
{
    context.Response.Body.Position = 0;
    using StreamReader reader = new(context.Response.Body, Encoding.UTF8, leaveOpen: true);
    return await reader.ReadToEndAsync();
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
        TestAudience,
        TestToolContractDigest);

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
    public bool SawCookie { get; private set; }

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
        SawCookie = request.Headers.Contains("Cookie");
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

sealed record TestGrant(
    string PacketAccessKey,
    string PacketDigest,
    DateTimeOffset ExpiresAtUtc);

sealed class GrantIssuanceHandler : HttpMessageHandler
{
    private readonly Queue<TestGrant> _grants = new();

    public int Calls { get; private set; }
    public string? Owner { get; private set; }
    public bool SawAccessAssertion { get; private set; }
    public bool SawAuthorization { get; private set; }

    public void Enqueue(TestGrant grant) => _grants.Enqueue(grant);

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        Calls++;
        Equal(HttpMethod.Post, request.Method);
        True(request.RequestUri?.AbsolutePath.EndsWith(
            "/build-ghost/tool-access",
            StringComparison.Ordinal) == true);
        Owner = request.Headers.GetValues(BuildGhostAccessProxy.OwnerHeader).Single();
        SawAccessAssertion |= request.Headers.Contains(BuildGhostAccessProxy.JwtAssertionHeader);
        SawAuthorization |= request.Headers.Authorization is not null;
        True(request.Headers.CacheControl?.NoStore is true);
        string requestBody = await request.Content!.ReadAsStringAsync(cancellationToken);
        False(requestBody.Contains("packet_access_key", StringComparison.Ordinal));
        TestGrant grant = _grants.Dequeue();
        string body = JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["packetAccessKey"] = grant.PacketAccessKey,
            ["packetDigest"] = grant.PacketDigest,
            ["expiresAtUtc"] = grant.ExpiresAtUtc,
        });
        HttpResponseMessage response = new(HttpStatusCode.OK)
        {
            Content = new StringContent(body, Encoding.UTF8, "application/json"),
        };
        response.Headers.TryAddWithoutValidation("Set-Cookie", "presentation-cookie=blocked");
        return response;
    }
}

sealed record TestProviderResponse(
    HttpStatusCode StatusCode,
    string Body,
    string? PacketDigest);

sealed class ProviderToolHandler : HttpMessageHandler
{
    private readonly Queue<TestProviderResponse> _responses = new();

    public int Calls { get; private set; }
    public bool SawOwner { get; private set; }
    public bool SawAccessAssertion { get; private set; }
    public bool SawAuthenticatedEmail { get; private set; }
    public bool SawAuthorization { get; private set; }
    public bool SawCookie { get; private set; }
    public bool SawTrace { get; private set; }
    public bool SawCloudflareHeaders { get; private set; }
    public bool SawCanonicalPacketKeyInBody { get; private set; }
    public bool CacheControlNoStore { get; private set; }
    public List<string> ToolContracts { get; } = [];
    public List<string> Paths { get; } = [];

    public void Enqueue(TestProviderResponse response) => _responses.Enqueue(response);

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        Calls++;
        Equal(HttpMethod.Post, request.Method);
        Paths.Add(request.RequestUri?.AbsolutePath ?? string.Empty);
        SawOwner |= request.Headers.Contains(BuildGhostAccessProxy.OwnerHeader);
        SawAccessAssertion |= request.Headers.Contains(BuildGhostAccessProxy.JwtAssertionHeader);
        SawAuthenticatedEmail |= request.Headers.Contains(BuildGhostAccessProxy.AuthenticatedEmailHeader);
        SawAuthorization |= request.Headers.Authorization is not null;
        SawCookie |= request.Headers.Contains("Cookie");
        SawTrace |= request.Headers.Contains("traceparent")
            || request.Headers.Contains("tracestate")
            || request.Headers.Contains("baggage")
            || request.Headers.Contains("Request-Id")
            || request.Headers.Contains("Correlation-Context");
        SawCloudflareHeaders |= request.Headers.Any(
            static header => header.Key.StartsWith("Cf-", StringComparison.OrdinalIgnoreCase));
        CacheControlNoStore |= request.Headers.CacheControl?.NoStore is true;
        ToolContracts.Add(request.Headers.GetValues(BuildGhostAccessProxy.ToolContractHeader).Single());
        byte[] body = await request.Content!.ReadAsByteArrayAsync(cancellationToken);
        try
        {
            SawCanonicalPacketKeyInBody |= BuildGhostProviderToolRequestContract.TryParse(
                body,
                out _,
                out _);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(body);
        }

        TestProviderResponse configured = _responses.Dequeue();
        HttpResponseMessage response = new(configured.StatusCode)
        {
            Content = new StringContent(configured.Body, Encoding.UTF8, "application/json"),
        };
        if (configured.PacketDigest is not null)
        {
            response.Headers.TryAddWithoutValidation(
                "X-Chummer-Build-Ghost-Packet-Digest",
                configured.PacketDigest);
        }
        response.Headers.TryAddWithoutValidation("Set-Cookie", "ai-cookie=blocked");
        return response;
    }
}

sealed class ConcurrentProviderToolHandler(string packetDigest) : HttpMessageHandler
{
    private readonly TaskCompletionSource _callEntered = new(
        TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource _callReleased = new(
        TaskCreationOptions.RunContinuationsAsynchronously);
    private int _calls;

    public int Calls => Volatile.Read(ref _calls);

    public Task WaitForCallAsync() => _callEntered.Task.WaitAsync(TimeSpan.FromSeconds(10));

    public void Release() => _callReleased.TrySetResult();

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _calls);
        _callEntered.TrySetResult();
        await _callReleased.Task.WaitAsync(cancellationToken);
        HttpResponseMessage response = new(HttpStatusCode.OK)
        {
            Content = new StringContent("{\"ok\":true}", Encoding.UTF8, "application/json"),
        };
        response.Headers.TryAddWithoutValidation(
            "X-Chummer-Build-Ghost-Packet-Digest",
            packetDigest);
        return response;
    }
}

sealed class NonSeekableReadStream(byte[] body) : Stream
{
    private readonly MemoryStream _inner = new(body, writable: false);

    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => throw new NotSupportedException();
    public override long Position
    {
        get => throw new NotSupportedException();
        set => throw new NotSupportedException();
    }

    public override void Flush() => throw new NotSupportedException();
    public override int Read(byte[] buffer, int offset, int count)
        => _inner.Read(buffer, offset, count);
    public override ValueTask<int> ReadAsync(
        Memory<byte> buffer,
        CancellationToken cancellationToken = default)
        => _inner.ReadAsync(buffer, cancellationToken);
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _inner.Dispose();
        }
        base.Dispose(disposing);
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

sealed class GatedResponseHandler(
    Func<int, HttpResponseMessage> responseFactory,
    int gatedCall) : HttpMessageHandler
{
    private readonly TaskCompletionSource _gateEntered = new(
        TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource _gateReleased = new(
        TaskCreationOptions.RunContinuationsAsynchronously);
    private int _calls;

    public int Calls => Volatile.Read(ref _calls);

    public Task WaitForGateAsync() => _gateEntered.Task.WaitAsync(TimeSpan.FromSeconds(10));

    public void ReleaseGate() => _gateReleased.TrySetResult();

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        int call = Interlocked.Increment(ref _calls);
        if (call == gatedCall)
        {
            _gateEntered.TrySetResult();
            await _gateReleased.Task.WaitAsync(cancellationToken);
        }
        return responseFactory(call);
    }
}
}
