using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
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

    private (IConfiguration Configuration, string KeyRingPath) WriteConfiguration(X509Certificate2 certificate)
    {
        string certificatePath = Path.Combine(_root, $"certificate-{Guid.NewGuid():N}.pfx");
        string passwordPath = Path.Combine(_root, $"password-{Guid.NewGuid():N}.txt");
        string keyRingPath = Path.Combine(_root, $"keys-{Guid.NewGuid():N}");
        byte[] pfx = certificate.Export(X509ContentType.Pfx, Password);
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
        return (configuration, keyRingPath);
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
