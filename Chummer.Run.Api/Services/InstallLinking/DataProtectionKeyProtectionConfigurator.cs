using Microsoft.AspNetCore.DataProtection;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Xml;
using System.Xml.Linq;

namespace Chummer.Run.Api.Services.InstallLinking;

public static class DataProtectionKeyProtectionConfigurator
{
    private const int MaximumCertificatesInBundle = 16;
    private const int MaximumPrivateKeyCertificates = 8;

    public static DataProtectionKeyProtectionStatus Configure(
        IServiceCollection services,
        IConfiguration configuration,
        IHostEnvironment environment,
        string keyRingPath)
    {
        IDataProtectionBuilder builder = services.AddDataProtection()
            .SetApplicationName("Chummer.Run.Api");
        bool production = environment.IsProduction();
        string? certificatePath = Normalize(configuration["CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH"]);
        string? passwordFile = Normalize(configuration["CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE"]);
        if (!string.IsNullOrWhiteSpace(configuration["CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD"]))
        {
            builder.UseEphemeralDataProtectionProvider();
            return new(false, "plaintext_certificate_password_rejected");
        }

        if (certificatePath is null || passwordFile is null)
        {
            if (production)
            {
                builder.UseEphemeralDataProtectionProvider();
                return new(false, "data_protection_key_encryptor_missing");
            }

            Directory.CreateDirectory(keyRingPath);
            builder.PersistKeysToFileSystem(new DirectoryInfo(Path.GetFullPath(keyRingPath)));
            return new(true, "development_key_ring");
        }

        try
        {
            if (!LinuxSecureFile.IsSupportedPlatform && production)
            {
                builder.UseEphemeralDataProtectionProvider();
                return new(false, "data_protection_secure_file_platform_unsupported");
            }

            byte[] certificateBytes = ReadSecretFile(certificatePath, 2 * 1024 * 1024, production);
            byte[] passwordBytes = [];
            X509Certificate2Collection? certificates = null;
            bool certificatesRegistered = false;
            try
            {
                passwordBytes = ReadSecretFile(passwordFile, 16 * 1024, production);
                string password = Encoding.UTF8.GetString(passwordBytes).TrimEnd('\r', '\n');
                if (password.Length is < 1 or > 4096 || password.Any(char.IsControl))
                {
                    throw new InvalidDataException("Certificate password file is invalid.");
                }

                certificates = X509CertificateLoader.LoadPkcs12Collection(
                    certificateBytes,
                    password,
                    X509KeyStorageFlags.EphemeralKeySet);
                if (certificates.Count is < 1 or > MaximumCertificatesInBundle)
                {
                    throw new InvalidDataException(
                        "Data-protection certificate bundle inventory is unbounded.");
                }

                X509Certificate2[] privateKeyCertificates = certificates
                    .Where(static candidate => candidate.HasPrivateKey)
                    .ToArray();
                if (privateKeyCertificates.Length is < 1 or > MaximumPrivateKeyCertificates
                    || privateKeyCertificates
                        .Select(static candidate => candidate.Thumbprint)
                        .Any(static thumbprint => string.IsNullOrWhiteSpace(thumbprint))
                    || privateKeyCertificates
                        .Select(static candidate => candidate.Thumbprint)
                        .Distinct(StringComparer.OrdinalIgnoreCase)
                        .Count() != privateKeyCertificates.Length)
                {
                    throw new InvalidDataException(
                        "Data-protection certificate bundle is not bounded and unique.");
                }

                foreach (X509Certificate2 candidate in privateKeyCertificates)
                {
                    ValidateEncryptionCertificate(candidate);
                }

                DateTime latestExpiry = privateKeyCertificates
                    .Max(static candidate => candidate.NotAfter.ToUniversalTime());
                X509Certificate2[] primaryCandidates = privateKeyCertificates
                    .Where(candidate => candidate.NotAfter.ToUniversalTime() == latestExpiry)
                    .ToArray();
                DateTime utcNow = DateTime.UtcNow;
                if (primaryCandidates.Length != 1
                    || primaryCandidates[0].NotBefore.ToUniversalTime() > utcNow
                    || latestExpiry <= utcNow.AddDays(7))
                {
                    throw new InvalidDataException(
                        "Data-protection primary certificate is not uniquely usable.");
                }

                X509Certificate2 primaryCertificate = primaryCandidates[0];
                X509Certificate2[] decryptionCertificates = privateKeyCertificates
                    .OrderByDescending(static candidate => candidate.NotAfter.ToUniversalTime())
                    .ThenBy(static candidate => candidate.Thumbprint, StringComparer.OrdinalIgnoreCase)
                    .ToArray();

                if (LinuxSecureFile.IsSupportedPlatform)
                {
                    LinuxSecureFile.PrepareOwnerOnlyDirectory(Path.GetFullPath(keyRingPath));
                }
                else
                {
                    Directory.CreateDirectory(keyRingPath);
                }

                VerifyDataProtectionRoundTrip(
                    primaryCertificate,
                    decryptionCertificates,
                    Path.GetFullPath(keyRingPath));
                string? keyRingFailure = ValidateEncryptedKeyRing(
                    Path.GetFullPath(keyRingPath),
                    repairOwnerMode: true);
                if (keyRingFailure is not null)
                {
                    throw new InvalidDataException("Data-protection generated key XML is invalid.");
                }

                builder
                    .PersistKeysToFileSystem(new DirectoryInfo(Path.GetFullPath(keyRingPath)))
                    .ProtectKeysWithCertificate(primaryCertificate)
                    .UnprotectKeysWithAnyCertificate(decryptionCertificates);
                foreach (X509Certificate2 certificate in certificates
                             .Where(static candidate => !candidate.HasPrivateKey))
                {
                    certificate.Dispose();
                }

                certificatesRegistered = true;
                return new(
                    true,
                    decryptionCertificates.Length == 1
                        ? "certificate_key_encryptor_configured"
                        : "certificate_rotation_key_encryptor_configured");
            }
            finally
            {
                if (!certificatesRegistered && certificates is not null)
                {
                    foreach (X509Certificate2 certificate in certificates)
                    {
                        certificate.Dispose();
                    }
                }

                CryptographicOperations.ZeroMemory(certificateBytes);
                CryptographicOperations.ZeroMemory(passwordBytes);
            }
        }
        catch
        {
            builder.UseEphemeralDataProtectionProvider();
            return new(false, "data_protection_key_encryptor_invalid");
        }
    }

    private static byte[] ReadSecretFile(string path, int maximumBytes, bool strict)
    {
        string fullPath = Path.GetFullPath(path);
        if (strict || LinuxSecureFile.IsSupportedPlatform)
        {
            return LinuxSecureFile.ReadOwnerOnlyRegularFile(fullPath, maximumBytes, repairOwnerMode: false);
        }

        FileInfo file = new(fullPath);
        if (!file.Exists || file.Length is <= 0 || file.Length > maximumBytes)
        {
            throw new InvalidDataException("Secret file is invalid.");
        }

        return File.ReadAllBytes(fullPath);
    }

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : Path.GetFullPath(value.Trim());

    private static void ValidateEncryptionCertificate(X509Certificate2 certificate)
    {
        using RSA? rsa = certificate.GetRSAPrivateKey();
        X509KeyUsageExtension? keyUsage = certificate.Extensions
            .OfType<X509KeyUsageExtension>()
            .SingleOrDefault();
        if (rsa is null
            || rsa.KeySize < 2048
            || (keyUsage is not null
                && (keyUsage.KeyUsages
                    & (X509KeyUsageFlags.KeyEncipherment | X509KeyUsageFlags.DataEncipherment)) == 0))
        {
            throw new InvalidDataException(
                "Data-protection certificate must have an RSA encryption-capable private key.");
        }
    }

    private static void VerifyDataProtectionRoundTrip(
        X509Certificate2 primaryCertificate,
        X509Certificate2[] decryptionCertificates,
        string keyRingPath)
    {
        IDataProtectionProvider provider = DataProtectionProvider.Create(
            new DirectoryInfo(keyRingPath),
            verification => verification
                .SetApplicationName("Chummer.Run.Api")
                .ProtectKeysWithCertificate(primaryCertificate)
                .UnprotectKeysWithAnyCertificate(decryptionCertificates));
        byte[] cleartext = RandomNumberGenerator.GetBytes(32);
        byte[]? protectedPayload = null;
        byte[]? recovered = null;
        try
        {
            IDataProtector protector = provider.CreateProtector(
                "Chummer.Run.Api.DataProtectionKeyProtectionConfigurator.readiness.v1");
            protectedPayload = protector.Protect(cleartext);
            recovered = protector.Unprotect(protectedPayload);
            if (!CryptographicOperations.FixedTimeEquals(cleartext, recovered))
            {
                throw new CryptographicException("Data-protection certificate round trip failed.");
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(cleartext);
            if (protectedPayload is not null)
            {
                CryptographicOperations.ZeroMemory(protectedPayload);
            }

            if (recovered is not null)
            {
                CryptographicOperations.ZeroMemory(recovered);
            }

            (provider as IDisposable)?.Dispose();
        }
    }

    internal static string? ValidateEncryptedKeyRing(string keyRingPath, bool repairOwnerMode)
    {
        string[] keyFiles = Directory.EnumerateFiles(keyRingPath, "key-*.xml", SearchOption.TopDirectoryOnly)
            .Take(129)
            .ToArray();
        if (keyFiles.Length == 0)
        {
            return "key_ring_empty";
        }

        if (keyFiles.Length > 128)
        {
            return "key_ring_inventory_unbounded";
        }

        foreach (string keyFile in keyFiles)
        {
            byte[] keyBytes = ReadKeyFile(keyFile, repairOwnerMode);
            try
            {
                if (!HasEncryptedKeyStructure(keyBytes))
                {
                    return "unprotected_key_material_detected";
                }
            }
            finally
            {
                CryptographicOperations.ZeroMemory(keyBytes);
            }
        }

        return null;
    }

    private static byte[] ReadKeyFile(string path, bool repairOwnerMode)
    {
        if (LinuxSecureFile.IsSupportedPlatform)
        {
            return LinuxSecureFile.ReadOwnerOnlyRegularFile(
                path,
                maximumBytes: 1024 * 1024,
                repairOwnerMode);
        }

        FileInfo file = new(path);
        if (!file.Exists || file.Length is <= 0 or > 1024 * 1024)
        {
            throw new InvalidDataException("Data-protection key file is invalid.");
        }

        if (repairOwnerMode && !OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        }

        return File.ReadAllBytes(path);
    }

    private static bool HasEncryptedKeyStructure(byte[] keyBytes)
    {
        try
        {
            using var stream = new MemoryStream(keyBytes, writable: false);
            using XmlReader reader = XmlReader.Create(
                stream,
                new XmlReaderSettings
                {
                    DtdProcessing = DtdProcessing.Prohibit,
                    MaxCharactersInDocument = 1024 * 1024,
                    XmlResolver = null
                });
            XDocument document = XDocument.Load(reader, LoadOptions.None);
            XElement? root = document.Root;
            if (root is null
                || !string.Equals(root.Name.LocalName, "key", StringComparison.Ordinal)
                || !Guid.TryParse(root.Attribute("id")?.Value, out _)
                || !string.Equals(root.Attribute("version")?.Value, "1", StringComparison.Ordinal))
            {
                return false;
            }

            XElement[] descriptors = root.Elements()
                .Where(static element => string.Equals(element.Name.LocalName, "descriptor", StringComparison.Ordinal))
                .ToArray();
            XElement[] encryptedSecrets = root.Descendants()
                .Where(static element => string.Equals(element.Name.LocalName, "encryptedSecret", StringComparison.Ordinal))
                .ToArray();
            if (descriptors.Length != 1
                || encryptedSecrets.Length != 1
                || string.IsNullOrWhiteSpace(encryptedSecrets[0].Attribute("decryptorType")?.Value)
                || root.Descendants().Any(static element =>
                    string.Equals(element.Name.LocalName, "masterKey", StringComparison.Ordinal)
                    || string.Equals(element.Name.LocalName, "secret", StringComparison.Ordinal)))
            {
                return false;
            }

            XElement encryptedSecret = encryptedSecrets[0];
            XElement[] encryptedData = encryptedSecret.Descendants()
                .Where(static element => string.Equals(element.Name.LocalName, "EncryptedData", StringComparison.Ordinal))
                .ToArray();
            XElement[] encryptedKeys = encryptedSecret.Descendants()
                .Where(static element => string.Equals(element.Name.LocalName, "EncryptedKey", StringComparison.Ordinal))
                .ToArray();
            XElement[] cipherValues = encryptedSecret.Descendants()
                .Where(static element => string.Equals(element.Name.LocalName, "CipherValue", StringComparison.Ordinal))
                .ToArray();
            XElement[] certificateValues = encryptedSecret.Descendants()
                .Where(static element => string.Equals(element.Name.LocalName, "X509Certificate", StringComparison.Ordinal))
                .ToArray();
            return encryptedData.Length == 1
                && encryptedKeys.Length == 1
                && cipherValues.Length >= 2
                && cipherValues.All(static value => !string.IsNullOrWhiteSpace(value.Value))
                && certificateValues.Length == 1
                && !string.IsNullOrWhiteSpace(certificateValues[0].Value);
        }
        catch (Exception exception) when (exception is XmlException
            or InvalidOperationException
            or InvalidDataException)
        {
            return false;
        }
    }
}
