namespace Chummer.Run.Api.Services.InstallLinking;

/// <summary>
/// Defers the production InstallLinking authority activation until an operation
/// actually needs the store. Unrelated public routes may stay available while
/// readiness and every InstallLinking mutation continue to fail closed.
/// </summary>
public sealed class InstallLinkingStoreAccess
{
    private readonly InstallLinkingStoreActivation _activation;

    public InstallLinkingStoreAccess(InstallLinkingStoreActivation activation)
    {
        _activation = activation ?? throw new ArgumentNullException(nameof(activation));
    }

    public bool TryGet(out InstallLinkingStore store)
    {
        store = null!;
        try
        {
            if (!_activation.Evaluate().Ready)
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
        => _activation.GetRequiredStore();
}
