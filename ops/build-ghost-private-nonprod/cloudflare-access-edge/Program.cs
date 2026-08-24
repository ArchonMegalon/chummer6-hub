using Chummer.BuildGhost.CloudflareAccessEdge;

WebApplicationBuilder builder = WebApplication.CreateSlimBuilder(args);
builder.Logging.ClearProviders();
builder.WebHost.ConfigureKestrel(options =>
{
    options.AddServerHeader = false;
    options.Limits.MaxRequestBodySize = 64L * 1024 * 1024;
    options.Limits.RequestHeadersTimeout = TimeSpan.FromSeconds(10);
    options.Limits.KeepAliveTimeout = TimeSpan.FromSeconds(30);
});

AccessEdgeConfiguration configuration = AccessEdgeConfiguration.FromEnvironment();

SocketsHttpHandler certificateHandler = new()
{
    AllowAutoRedirect = false,
    AutomaticDecompression = System.Net.DecompressionMethods.None,
    ConnectTimeout = TimeSpan.FromSeconds(5),
    PooledConnectionLifetime = TimeSpan.FromMinutes(10),
    UseCookies = false,
    UseProxy = false,
};
HttpClient certificateClient = new(certificateHandler)
{
    Timeout = TimeSpan.FromSeconds(10),
};

SocketsHttpHandler upstreamHandler = new()
{
    AllowAutoRedirect = false,
    AutomaticDecompression = System.Net.DecompressionMethods.None,
    ConnectTimeout = TimeSpan.FromSeconds(3),
    PooledConnectionLifetime = TimeSpan.FromMinutes(5),
    UseCookies = false,
    UseProxy = false,
};
HttpClient upstreamClient = new(upstreamHandler)
{
    Timeout = TimeSpan.FromSeconds(30),
};

CloudflareAccessSigningKeyProvider signingKeys = new(
    configuration,
    certificateClient);
CloudflareAccessJwtValidator tokenValidator = new(
    configuration,
    signingKeys);
BuildGhostAccessProxy proxy = new(
    configuration,
    tokenValidator,
    upstreamClient);

WebApplication app = builder.Build();
app.Lifetime.ApplicationStopping.Register(certificateClient.Dispose);
app.Lifetime.ApplicationStopping.Register(upstreamClient.Dispose);
app.Run(proxy.HandleAsync);
await app.RunAsync().ConfigureAwait(false);
