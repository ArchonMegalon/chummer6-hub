using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Xml.Linq;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.DataProtection.KeyManagement;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Chummer.Tests;

public sealed class DataProtectionKeyProtectionConfiguratorTests : IDisposable
{
    private const string Password = "data-protection-test-password";
    private readonly string _root = Path.Combine(
        Path.GetTempPath(),
        "data-protection-key-protection-tests",
        Guid.NewGuid().ToString("N"));

    public DataProtectionKeyProtectionConfiguratorTests() => Directory.CreateDirectory(_root);

    [Fact]
    public void Production_rsa_certificate_performs_round_trip_and_generates_encrypted_key_xml()
    {
        if (!IsSupportedProductionPlatform())
        {
            return;
        }

        using RSA rsa = RSA.Create(2048);
        var request = new CertificateRequest(
            "CN=Chummer Data Protection Test",
            rsa,
            HashAlgorithmName.SHA256,
            RSASignaturePadding.Pkcs1);
        request.CertificateExtensions.Add(new X509KeyUsageExtension(
            X509KeyUsageFlags.KeyEncipherment | X509KeyUsageFlags.DataEncipherment,
            critical: true));
        using X509Certificate2 certificate = request.CreateSelfSigned(
            DateTimeOffset.UtcNow.AddHours(-1),
            DateTimeOffset.UtcNow.AddDays(30));
        (IConfiguration configuration, string keyRingPath) = WriteConfiguration(certificate);
        var services = new ServiceCollection();

        DataProtectionKeyProtectionStatus status = DataProtectionKeyProtectionConfigurator.Configure(
            services,
            configuration,
            ProductionEnvironment(),
            keyRingPath);

        Assert.Equal(new DataProtectionKeyProtectionStatus(
            true,
            "certificate_key_encryptor_configured"), status);
        Assert.Null(DataProtectionKeyProtectionConfigurator.ValidateEncryptedKeyRing(
            keyRingPath,
            repairOwnerMode: false));
        using ServiceProvider provider = services.BuildServiceProvider();
        IDataProtector protector = provider
            .GetRequiredService<IDataProtectionProvider>()
            .CreateProtector("Chummer.Tests.DataProtectionKeyProtectionConfigurator");
        const string cleartext = "round-trip-marker";
        Assert.Equal(cleartext, protector.Unprotect(protector.Protect(cleartext)));
    }

    [Fact]
    public void Production_ecdsa_pfx_fails_closed_without_generating_a_key_ring()
    {
        if (!IsSupportedProductionPlatform())
        {
            return;
        }

        using ECDsa ecdsa = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var request = new CertificateRequest(
            "CN=Chummer Signing Only Test",
            ecdsa,
            HashAlgorithmName.SHA256);
        request.CertificateExtensions.Add(new X509KeyUsageExtension(
            X509KeyUsageFlags.DigitalSignature,
            critical: true));
        using X509Certificate2 certificate = request.CreateSelfSigned(
            DateTimeOffset.UtcNow.AddHours(-1),
            DateTimeOffset.UtcNow.AddDays(30));
        (IConfiguration configuration, string keyRingPath) = WriteConfiguration(certificate);
        var services = new ServiceCollection();

        DataProtectionKeyProtectionStatus status = DataProtectionKeyProtectionConfigurator.Configure(
            services,
            configuration,
            ProductionEnvironment(),
            keyRingPath);

        Assert.Equal(new DataProtectionKeyProtectionStatus(
            false,
            "data_protection_key_encryptor_invalid"), status);
        Assert.False(Directory.Exists(keyRingPath));
    }

    [Fact]
    public void Production_rotation_bundle_reads_existing_ring_and_uses_latest_expiry_primary()
    {
        if (!IsSupportedProductionPlatform())
        {
            return;
        }

        using RSA previousRsa = RSA.Create(2048);
        using RSA primaryRsa = RSA.Create(3072);
        using X509Certificate2 previousCertificate = CreateEncryptionCertificate(
            previousRsa,
            DateTimeOffset.UtcNow.AddDays(30));
        using X509Certificate2 primaryCertificate = CreateEncryptionCertificate(
            primaryRsa,
            DateTimeOffset.UtcNow.AddDays(365));
        string keyRingPath = Path.Combine(_root, $"keys-{Guid.NewGuid():N}");

        var previousServices = new ServiceCollection();
        DataProtectionKeyProtectionStatus previousStatus = DataProtectionKeyProtectionConfigurator.Configure(
            previousServices,
            WriteCertificateBundle([previousCertificate], "previous"),
            ProductionEnvironment(),
            keyRingPath);
        Assert.True(previousStatus.Ready, previousStatus.Code);
        using ServiceProvider previousProvider = previousServices.BuildServiceProvider();
        IDataProtector previousProtector = previousProvider
            .GetRequiredService<IDataProtectionProvider>()
            .CreateProtector("Chummer.Tests.DataProtectionRotation");
        string protectedPayload = previousProtector.Protect("previous-ring-marker");

        var rotationServices = new ServiceCollection();
        DataProtectionKeyProtectionStatus rotationStatus = DataProtectionKeyProtectionConfigurator.Configure(
            rotationServices,
            WriteCertificateBundle([previousCertificate, primaryCertificate], "rotation"),
            ProductionEnvironment(),
            keyRingPath);
        Assert.Equal(
            new DataProtectionKeyProtectionStatus(
                true,
                "certificate_rotation_key_encryptor_configured"),
            rotationStatus);
        using ServiceProvider rotationProvider = rotationServices.BuildServiceProvider();
        IDataProtector rotationProtector = rotationProvider
            .GetRequiredService<IDataProtectionProvider>()
            .CreateProtector("Chummer.Tests.DataProtectionRotation");
        Assert.Equal("previous-ring-marker", rotationProtector.Unprotect(protectedPayload));

        rotationProvider.GetRequiredService<IKeyManager>().CreateNewKey(
            DateTimeOffset.UtcNow,
            DateTimeOffset.UtcNow.AddDays(90));
        string[] embeddedFingerprints = Directory
            .EnumerateFiles(keyRingPath, "key-*.xml", SearchOption.TopDirectoryOnly)
            .Select(EmbeddedCertificateFingerprint)
            .ToArray();
        Assert.Contains(previousCertificate.GetCertHashString(HashAlgorithmName.SHA256), embeddedFingerprints);
        Assert.Contains(primaryCertificate.GetCertHashString(HashAlgorithmName.SHA256), embeddedFingerprints);
    }

    [Fact]
    public void Production_rotation_bundle_rejects_ambiguous_latest_expiry()
    {
        if (!IsSupportedProductionPlatform())
        {
            return;
        }

        DateTimeOffset sharedExpiry = DateTimeOffset.UtcNow.AddDays(365);
        using RSA firstRsa = RSA.Create(2048);
        using RSA secondRsa = RSA.Create(2048);
        using X509Certificate2 first = CreateEncryptionCertificate(firstRsa, sharedExpiry);
        using X509Certificate2 second = CreateEncryptionCertificate(secondRsa, sharedExpiry);
        string keyRingPath = Path.Combine(_root, $"keys-{Guid.NewGuid():N}");
        var services = new ServiceCollection();

        DataProtectionKeyProtectionStatus status = DataProtectionKeyProtectionConfigurator.Configure(
            services,
            WriteCertificateBundle([first, second], "ambiguous"),
            ProductionEnvironment(),
            keyRingPath);

        Assert.Equal(
            new DataProtectionKeyProtectionStatus(false, "data_protection_key_encryptor_invalid"),
            status);
        Assert.False(Directory.Exists(keyRingPath));
    }

    [Fact]
    public void Production_rotation_bundle_rejects_duplicate_certificate_identity()
    {
        if (!IsSupportedProductionPlatform())
        {
            return;
        }

        using RSA rsa = RSA.Create(2048);
        using X509Certificate2 certificate = CreateEncryptionCertificate(
            rsa,
            DateTimeOffset.UtcNow.AddDays(365));
        string keyRingPath = Path.Combine(_root, $"keys-{Guid.NewGuid():N}");
        var services = new ServiceCollection();

        DataProtectionKeyProtectionStatus status = DataProtectionKeyProtectionConfigurator.Configure(
            services,
            WriteCertificateBundle([certificate, certificate], "duplicate"),
            ProductionEnvironment(),
            keyRingPath);

        Assert.Equal(
            new DataProtectionKeyProtectionStatus(false, "data_protection_key_encryptor_invalid"),
            status);
        Assert.False(Directory.Exists(keyRingPath));
    }

    [Fact]
    public void Production_rotation_bundle_rejects_non_encryption_decryptor()
    {
        if (!IsSupportedProductionPlatform())
        {
            return;
        }

        using RSA priorRsa = RSA.Create(2048);
        using RSA primaryRsa = RSA.Create(2048);
        using X509Certificate2 prior = CreateCertificate(
            priorRsa,
            DateTimeOffset.UtcNow.AddDays(30),
            X509KeyUsageFlags.DigitalSignature);
        using X509Certificate2 primary = CreateEncryptionCertificate(
            primaryRsa,
            DateTimeOffset.UtcNow.AddDays(365));
        string keyRingPath = Path.Combine(_root, $"keys-{Guid.NewGuid():N}");
        var services = new ServiceCollection();

        DataProtectionKeyProtectionStatus status = DataProtectionKeyProtectionConfigurator.Configure(
            services,
            WriteCertificateBundle([prior, primary], "signing-only-prior"),
            ProductionEnvironment(),
            keyRingPath);

        Assert.Equal(
            new DataProtectionKeyProtectionStatus(false, "data_protection_key_encryptor_invalid"),
            status);
        Assert.False(Directory.Exists(keyRingPath));
    }

    [Fact]
    public void Production_near_expiry_primary_fails_closed_before_ring_creation()
    {
        if (!IsSupportedProductionPlatform())
        {
            return;
        }

        using RSA rsa = RSA.Create(2048);
        using X509Certificate2 certificate = CreateEncryptionCertificate(
            rsa,
            DateTimeOffset.UtcNow.AddDays(6));
        string keyRingPath = Path.Combine(_root, $"keys-{Guid.NewGuid():N}");
        var services = new ServiceCollection();

        DataProtectionKeyProtectionStatus status = DataProtectionKeyProtectionConfigurator.Configure(
            services,
            WriteCertificateBundle([certificate], "near-expiry"),
            ProductionEnvironment(),
            keyRingPath);

        Assert.Equal(
            new DataProtectionKeyProtectionStatus(false, "data_protection_key_encryptor_invalid"),
            status);
        Assert.False(Directory.Exists(keyRingPath));
    }

    private (IConfiguration Configuration, string KeyRingPath) WriteConfiguration(X509Certificate2 certificate)
    {
        string keyRingPath = Path.Combine(_root, $"keys-{Guid.NewGuid():N}");
        return (WriteCertificateBundle([certificate], Guid.NewGuid().ToString("N")), keyRingPath);
    }

    private IConfiguration WriteCertificateBundle(
        X509Certificate2Collection certificates,
        string label)
    {
        string certificatePath = Path.Combine(_root, $"certificate-{label}.pfx");
        string passwordPath = Path.Combine(_root, $"password-{label}.txt");
        byte[] pfx = certificates.Export(X509ContentType.Pfx, Password)
            ?? throw new InvalidOperationException("Test certificate bundle export failed.");
        try
        {
            File.WriteAllBytes(certificatePath, pfx);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(pfx);
        }

        File.WriteAllText(passwordPath, $"{Password}\n");
        if (OperatingSystem.IsLinux())
        {
            File.SetUnixFileMode(certificatePath, UnixFileMode.UserRead | UnixFileMode.UserWrite);
            File.SetUnixFileMode(passwordPath, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        }
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH"] = certificatePath,
                ["CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE"] = passwordPath
            })
            .Build();
        return configuration;
    }

    private static X509Certificate2 CreateEncryptionCertificate(
        RSA rsa,
        DateTimeOffset notAfter)
        => CreateCertificate(
            rsa,
            notAfter,
            X509KeyUsageFlags.KeyEncipherment | X509KeyUsageFlags.DataEncipherment);

    private static X509Certificate2 CreateCertificate(
        RSA rsa,
        DateTimeOffset notAfter,
        X509KeyUsageFlags keyUsage)
    {
        var request = new CertificateRequest(
            "CN=Chummer Data Protection Rotation Test",
            rsa,
            HashAlgorithmName.SHA256,
            RSASignaturePadding.Pkcs1);
        request.CertificateExtensions.Add(new X509KeyUsageExtension(keyUsage, critical: true));
        return request.CreateSelfSigned(DateTimeOffset.UtcNow.AddHours(-1), notAfter);
    }

    private static string EmbeddedCertificateFingerprint(string keyFile)
    {
        XDocument document = XDocument.Load(keyFile, LoadOptions.None);
        string encoded = document.Descendants()
            .Single(element => string.Equals(
                element.Name.LocalName,
                "X509Certificate",
                StringComparison.Ordinal))
            .Value;
        using X509Certificate2 certificate = X509CertificateLoader.LoadCertificate(
            Convert.FromBase64String(encoded));
        return certificate.GetCertHashString(HashAlgorithmName.SHA256);
    }

    private TestHostEnvironment ProductionEnvironment()
        => new()
        {
            EnvironmentName = Environments.Production,
            ContentRootPath = _root
        };

    private static bool IsSupportedProductionPlatform()
        => OperatingSystem.IsLinux()
            && RuntimeInformation.ProcessArchitecture == Architecture.X64;

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    private sealed class TestHostEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Production;
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string ContentRootPath { get; set; } = string.Empty;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
