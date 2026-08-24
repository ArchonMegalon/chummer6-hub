namespace Chummer.BuildGhost.CloudflareAccessEdge;

public static class AccessEdgeHttpTransport
{
    public static SocketsHttpHandler CreateCertificateHandler()
        => new()
        {
            ActivityHeadersPropagator = null,
            AllowAutoRedirect = false,
            AutomaticDecompression = System.Net.DecompressionMethods.None,
            ConnectTimeout = TimeSpan.FromSeconds(5),
            PooledConnectionLifetime = TimeSpan.FromMinutes(10),
            UseCookies = false,
            UseProxy = false,
        };

    public static SocketsHttpHandler CreatePresentationHandler()
        => new()
        {
            ActivityHeadersPropagator = null,
            AllowAutoRedirect = false,
            AutomaticDecompression = System.Net.DecompressionMethods.None,
            ConnectTimeout = TimeSpan.FromSeconds(3),
            PooledConnectionLifetime = TimeSpan.FromMinutes(5),
            UseCookies = false,
            UseProxy = false,
        };
}
