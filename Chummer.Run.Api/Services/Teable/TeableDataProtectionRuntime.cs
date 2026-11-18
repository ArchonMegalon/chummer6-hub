using System.Security.Cryptography;
using System.Xml.Linq;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Storage.Teable;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.DataProtection.KeyManagement;
using Microsoft.AspNetCore.DataProtection.Repositories;

namespace Chummer.Run.Api.Services.Teable;

/// <summary>Actual private remote key custody. No local key directory or certificate fallback.</summary>
internal sealed class TeableDataProtectionRuntime(TeableRevisionStore store, bool ownsStore)
    : IXmlRepository, IDataProtectionPrimaryReadinessProbe, IDisposable
{
    private readonly TeableDataProtectionKeyRepository _repository = new(store);
    internal const string Mode = "teable_primary";
    internal const string ReadyCode = "teable_primary_key_ring";

    public IReadOnlyCollection<XElement> GetAllElements() => _repository.GetAllElements();
    public void StoreElement(XElement element, string friendlyName) => _repository.StoreElement(element, friendlyName);
    public void Dispose() { if (ownsStore) store.Dispose(); }

    public DataProtectionKeyProtectionStatus Evaluate()
    {
        try
        {
            return GetAllElements().Any(element => element.Name == "key")
                ? new(true, ReadyCode) : new(false, "teable_key_ring_empty");
        }
        catch { return new(false, "teable_key_ring_unavailable"); }
    }

    internal void VerifyColdRoundTrip()
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        store.VerifySchemaAsync(deadline.Token).GetAwaiter().GetResult();
        _ = GetAllElements(); // Reject corrupt/encrypted history before creating a key.
        using ServiceProvider producer = NewProvider();
        byte[] clear = RandomNumberGenerator.GetBytes(32);
        byte[]? encrypted = null, restored = null;
        try
        {
            const string purpose = "Chummer.Run.Api.TeableKeyCustody.readiness.v1";
            encrypted = producer.GetRequiredService<IDataProtectionProvider>().CreateProtector(purpose).Protect(clear);
            using ServiceProvider consumer = NewProvider();
            restored = consumer.GetRequiredService<IDataProtectionProvider>().CreateProtector(purpose).Unprotect(encrypted);
            if (!CryptographicOperations.FixedTimeEquals(clear, restored))
                throw new CryptographicException("Remote key custody cold restoration failed.");
        }
        finally
        {
            CryptographicOperations.ZeroMemory(clear);
            if (encrypted is not null) CryptographicOperations.ZeroMemory(encrypted);
            if (restored is not null) CryptographicOperations.ZeroMemory(restored);
        }
    }

    private ServiceProvider NewProvider()
    {
        var services = new ServiceCollection();
        services.AddDataProtection().SetApplicationName("Chummer.Run.Api");
        services.Configure<KeyManagementOptions>(options =>
        {
            options.XmlRepository = this;
            options.XmlEncryptor = null;
        });
        return services.BuildServiceProvider();
    }
}
