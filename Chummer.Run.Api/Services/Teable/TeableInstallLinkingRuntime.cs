using Chummer.Storage.Teable;

namespace Chummer.Run.Api.Services.Teable;

internal sealed class TeableInstallLinkingRuntime : IDisposable
{
    private readonly TeableRevisionStore _store;
    internal TeableInstallLinkingSnapshotAuthority Authority { get; }

    public TeableInstallLinkingRuntime(IConfiguration configuration)
        : this(Open(configuration)) { }

    internal TeableInstallLinkingRuntime(TeableRevisionStore store)
    {
        _store = store;
        Authority = new(_store);
    }

    internal static TeableRevisionStore Open(IConfiguration configuration) => TeableRevisionStore.OpenFromPrivateTokenFile(
        new Uri(configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
        configuration["CHUMMER_INSTALL_LINKING_TEABLE_TABLE_ID"] ?? string.Empty,
        configuration["CHUMMER_INSTALL_LINKING_TEABLE_TOKEN_FILE"] ?? string.Empty);

    public void Dispose() => _store.Dispose();
}
