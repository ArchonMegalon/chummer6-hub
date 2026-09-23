using System.Security.Cryptography;
using System.Xml;
using System.Xml.Linq;
using Microsoft.AspNetCore.DataProtection.Repositories;

namespace Chummer.Run.Api.Services.InstallLinking;

// Data Protection still encrypts/authenticates application payloads. Only the
// additional certificate wrapping of its persisted master keys is omitted.
// Backups of this directory are secrets and must include the actual key bytes.
internal sealed class OwnerOnlyDataProtectionKeyRepository : IXmlRepository
{
    private readonly string _path;

    public OwnerOnlyDataProtectionKeyRepository(string path)
    {
        if (!LinuxSecureFile.IsSupportedPlatform || !Path.IsPathFullyQualified(path))
            throw new InvalidOperationException("Owner-only key storage requires an absolute Linux path.");
        _path = Path.GetFullPath(path);
        if (!Directory.Exists(_path))
            LinuxSecureFile.PrepareOwnerOnlyDirectory(_path);
        ValidateDirectory();
    }

    public IReadOnlyCollection<XElement> GetAllElements()
    {
        ValidateDirectory();
        string[] files = Directory.EnumerateFiles(_path, "*.xml").Take(257).ToArray();
        if (files.Length > 256)
            throw new InvalidDataException("Key repository inventory is unbounded.");
        List<XElement> elements = [];
        foreach (string file in files)
        {
            byte[] bytes = LinuxSecureFile.ReadOwnerOnlyRegularFile(file, 1024 * 1024, repairOwnerMode: false);
            try
            {
                using var stream = new MemoryStream(bytes, writable: false);
                using XmlReader reader = XmlReader.Create(stream, new XmlReaderSettings
                {
                    DtdProcessing = DtdProcessing.Prohibit,
                    XmlResolver = null,
                    MaxCharactersInDocument = 1024 * 1024
                });
                XElement element = XElement.Load(reader, LoadOptions.None);
                ValidateElement(element);
                elements.Add(element);
            }
            finally { CryptographicOperations.ZeroMemory(bytes); }
        }
        return elements;
    }

    public void StoreElement(XElement element, string friendlyName)
    {
        if (!OperatingSystem.IsLinux())
            throw new PlatformNotSupportedException();
        ValidateDirectory();
        ValidateElement(element);
        // Do not accept a path from friendlyName. Create private bytes from the
        // first write and atomically expose a new file; never overwrite a key.
        string name = element.Name == "key"
            ? $"key-{Guid.Parse(element.Attribute("id")!.Value):D}"
            : $"revocation-{Guid.NewGuid():N}";
        string temporary = Path.Combine(_path, $".{Guid.NewGuid():N}.tmp");
        try
        {
            using (var stream = new FileStream(temporary, new FileStreamOptions
            {
                Mode = FileMode.CreateNew,
                Access = FileAccess.Write,
                Share = FileShare.None,
                Options = FileOptions.WriteThrough,
                UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite
            }))
            {
                element.Save(stream);
                stream.Flush(flushToDisk: true);
            }
            File.Move(temporary, Path.Combine(_path, name + ".xml"), overwrite: false);
        }
        finally { File.Delete(temporary); }
    }

    private void ValidateDirectory()
        => LinuxSecureFile.ValidateExistingDirectory(_path, ownerOnly: true, readOnlyFileSystem: false);

    internal static void ValidateElement(XElement element)
    {
        if (element.Attribute("version")?.Value != "1"
            || element.Descendants().Any(node => node.Name.LocalName is "encryptedSecret" or "EncryptedData"))
            throw new InvalidDataException("Encrypted or invalid key history cannot be adopted by owner-only storage.");
        if (element.Name == "revocation") return;
        if (element.Name != "key" || !Guid.TryParse(element.Attribute("id")?.Value, out _)
            || element.Elements("descriptor").Count() != 1
            || element.Descendants("masterKey").Count() != 1
            || element.Descendants("masterKey").Single().Elements("value").Count() != 1)
            throw new InvalidDataException("Invalid owner-only key record.");
    }
}
