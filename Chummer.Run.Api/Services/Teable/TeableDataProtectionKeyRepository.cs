using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Xml;
using System.Xml.Linq;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection.Repositories;

namespace Chummer.Run.Api.Services.Teable;

/// <summary>
/// Private remote custody of the actual new key bytes, not paths or an extra
/// certificate that would be lost with the host. Never adopts encrypted history.
/// Requires a restricted Teable table/token; this is not public book content.
/// </summary>
internal sealed class TeableDataProtectionKeyRepository(TeableRevisionStore store) : IXmlRepository
{
    private const string Stream = "data-protection-keys";
    private const int MaximumKeySetBytes = 4 * 1024 * 1024;
    private static readonly JsonSerializerOptions Json = new() { MaxDepth = 4 };

    public IReadOnlyCollection<XElement> GetAllElements()
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        var head = store.ReadAsync(Stream, deadline.Token).GetAwaiter().GetResult();
        try { return Decode(head).Values.ToArray(); }
        finally { if (head is not null) CryptographicOperations.ZeroMemory(head.Bytes); }
    }

    public void StoreElement(XElement element, string friendlyName)
    {
        OwnerOnlyDataProtectionKeyRepository.ValidateElement(element);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        var head = store.ReadAsync(Stream, deadline.Token).GetAwaiter().GetResult();
        byte[]? bytes = null;
        TeableRevisionStore.Head? committed = null;
        try
        {
            Dictionary<string, XElement> keys = Decode(head);
            string identity = Identity(element);
            if (keys.TryGetValue(identity, out var existing))
            {
                if (!XNode.DeepEquals(existing, element)) throw new InvalidDataException("An existing key cannot be replaced.");
                return;
            }
            if (keys.Count >= 256) throw new InvalidDataException("The key inventory is full.");
            keys.Add(identity, element);
            bytes = JsonSerializer.SerializeToUtf8Bytes(keys.OrderBy(pair => pair.Key, StringComparer.Ordinal)
                .Select(pair => pair.Value.ToString(SaveOptions.DisableFormatting)).ToArray(), Json);
            if (bytes.Length > MaximumKeySetBytes) throw new InvalidDataException("The key inventory is oversized.");
            // A racing generator fails; it must reread the winning keyring. Never
            // overwrite another key/revocation or return an unacknowledged key.
            committed = store.CompareExchangeAsync(Stream, head, Guid.NewGuid(), bytes, deadline.Token).GetAwaiter().GetResult();
        }
        finally
        {
            if (bytes is not null) CryptographicOperations.ZeroMemory(bytes);
            if (head is not null) CryptographicOperations.ZeroMemory(head.Bytes);
            if (committed is not null) CryptographicOperations.ZeroMemory(committed.Bytes);
        }
    }

    private static Dictionary<string, XElement> Decode(TeableRevisionStore.Head? head)
    {
        var result = new Dictionary<string, XElement>(StringComparer.Ordinal);
        if (head is null) return result;
        if (head.Bytes.Length > MaximumKeySetBytes) throw new InvalidDataException("The key inventory is oversized.");
        string[] values = JsonSerializer.Deserialize<string[]>(head.Bytes, Json) ?? throw new InvalidDataException("Invalid key inventory.");
        if (values.Length is < 1 or > 256) throw new InvalidDataException("Invalid key inventory size.");
        foreach (string xml in values)
        {
            if (xml is null || xml.Length > 1024 * 1024) throw new InvalidDataException("Invalid key record size.");
            using var text = new StringReader(xml);
            using var reader = XmlReader.Create(text, new XmlReaderSettings
                { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null, MaxCharactersInDocument = 1024 * 1024 });
            XElement element = XElement.Load(reader);
            OwnerOnlyDataProtectionKeyRepository.ValidateElement(element);
            if (!result.TryAdd(Identity(element), element)) throw new InvalidDataException("Duplicate key identity.");
        }
        return result;
    }

    private static string Identity(XElement element)
        => element.Name == "key" ? "key-" + Guid.Parse(element.Attribute("id")!.Value).ToString("D")
            : "revocation-" + Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(element.ToString(SaveOptions.DisableFormatting))));
}
