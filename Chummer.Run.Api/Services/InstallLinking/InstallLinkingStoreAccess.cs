namespace Chummer.Run.Api.Services.InstallLinking;

/// <summary>
/// Defers the production InstallLinking authority activation until an operation
/// actually needs the store. Unrelated public routes may stay available while
/// readiness and every InstallLinking mutation continue to fail closed.
/// </summary>
public sealed class InstallLinkingStoreAccess
{
    private readonly InstallLinkingStoreActivation? _activation;
    private readonly InstallLinkingStore? _fixedStore;

    public InstallLinkingStoreAccess(InstallLinkingStoreActivation activation)
    {
        _activation = activation ?? throw new ArgumentNullException(nameof(activation));
    }

    internal InstallLinkingStoreAccess(InstallLinkingStore store)
    {
        _fixedStore = store ?? throw new ArgumentNullException(nameof(store));
    }

    public bool TryGet(out InstallLinkingStore store)
    {
        store = null!;
        try
        {
            if (_fixedStore is not null)
            {
                store = _fixedStore;
                return store.IsHealthy;
            }

            if (_activation is null || !_activation.Evaluate().Ready)
            {
                return false;
            }

            store = _activation.GetRequiredStore();
            return store.IsHealthy;
        }
        catch
        {
            store = null!;
            return false;
        }
    }

    public InstallLinkingStore GetRequired()
        => _fixedStore ?? _activation?.GetRequiredStore()
            ?? throw new InvalidOperationException("Install-linking durable store access is unavailable.");
}
