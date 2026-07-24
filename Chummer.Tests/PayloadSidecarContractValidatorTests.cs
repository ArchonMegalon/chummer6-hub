using System.Text.Json;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class PayloadSidecarContractValidatorTests
{
    private const string ArtifactId = "avalonia-win-x64-installer";
    private const string InstallerFileName =
        "chummer-avalonia-win-x64-installer.exe";
    private const string PayloadFileName =
        "chummer-avalonia-win-x64-payload.zip";
    private const string StablePayloadUrl =
        "https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip";
    private const string ProjectedPayloadUrl =
        "/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload";
    private const string PayloadSha256 =
        "22464a462bf72e0b24efd686ddb2a66114bccde0f98b82273e15f7335a35582e";
    private const long PayloadSizeBytes = 51231862;
    private const string ReleaseVersion = "run-20260723-230227";

    [Fact]
    public void ExactFailedProductionSidecarMatchesProjectedOpenPublicManifest()
    {
        bool valid = ValidateSealed(
            Sidecar(),
            ProjectedPayloadUrl,
            "open_public",
            ArtifactId,
            out string? failure);

        Assert.True(valid, failure);
    }

    [Theory]
    [InlineData("account_required")]
    [InlineData("account_recommended")]
    [InlineData("Open_Public")]
    [InlineData(" open_public ")]
    [InlineData(null)]
    public void StablePayloadUrlRequiresExactEffectiveOpenPublicAccess(
        string? installAccessClass)
    {
        bool valid = ValidateSealed(
            Sidecar(),
            ProjectedPayloadUrl,
            installAccessClass,
            ArtifactId,
            out string? failure);

        Assert.False(valid);
        Assert.Equal(
            "payload sidecar URL does not match its governed payload route",
            failure);
    }

    [Theory]
    [InlineData("/downloads/files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://evil.example/downloads/files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("http://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://www.chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://Chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://attacker@chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://chummer.run:443/downloads/files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://chummer.run:444/downloads/files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip?download=1")]
    [InlineData("https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip#payload")]
    [InlineData("https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload%2Ezip")]
    [InlineData("https://chummer.run/downloads/files%2Fchummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://chummer.run//downloads/files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://chummer.run/downloads//files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://chummer.run/downloads/files/../files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://chummer.run/downloads/files/./chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip/")]
    [InlineData("https://chummer.run/downloads/files\\chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://chummer.run/downloads/files/not-the-payload.zip")]
    [InlineData(" https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip")]
    [InlineData("https://chummer.run/downloads/files/chummer-avalonia-win-x64-payload.zip ")]
    public void SealedStablePayloadUrlRejectsEveryNoncanonicalVariant(
        string sidecarUrl)
    {
        bool valid = ValidateSealed(
            Sidecar(downloadUrl: sidecarUrl),
            ProjectedPayloadUrl,
            "open_public",
            ArtifactId,
            out _);

        Assert.False(valid);
    }

    [Theory]
    [InlineData("//downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload")]
    [InlineData("/downloads//g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload")]
    [InlineData("/downloads/g//install/avalonia-win-x64-installer/payload")]
    [InlineData("/downloads/g/g-20260724T111416Z-48dd860a787641a0//install/avalonia-win-x64-installer/payload")]
    [InlineData("/downloads/g/g-20260724T111416Z-48dd860a787641a0/install//payload")]
    [InlineData("/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload/")]
    [InlineData(" /downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload")]
    [InlineData("/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload ")]
    [InlineData("https://chummer.run/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload")]
    [InlineData("/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/other-artifact/payload")]
    [InlineData("/downloads/g/../install/avalonia-win-x64-installer/payload")]
    [InlineData("/downloads/g/./install/avalonia-win-x64-installer/payload")]
    [InlineData("/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/./payload")]
    [InlineData("/downloads/g/g%2D20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload")]
    [InlineData("/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload?download=1")]
    [InlineData("/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload#payload")]
    public void StablePayloadUrlRequiresExactProjectedSemanticManifestRoute(
        string manifestUrl)
    {
        bool valid = ValidateSealed(
            Sidecar(),
            manifestUrl,
            "open_public",
            ArtifactId,
            out _);

        Assert.False(valid);
    }

    [Theory]
    [InlineData(" avalonia-win-x64-installer")]
    [InlineData("avalonia-win-x64-installer ")]
    [InlineData("other-artifact")]
    [InlineData("")]
    [InlineData(null)]
    public void StablePayloadUrlRequiresExactProjectedArtifactIdentity(
        string? artifactId)
    {
        bool valid = ValidateSealed(
            Sidecar(),
            ProjectedPayloadUrl,
            "open_public",
            artifactId,
            out _);

        Assert.False(valid);
    }

    [Fact]
    public void StablePayloadUrlRejectsPayloadDigestDrift()
    {
        bool valid = ValidateSealed(
            Sidecar(sha256: new string('a', 64)),
            ProjectedPayloadUrl,
            "open_public",
            ArtifactId,
            out string? failure);

        Assert.False(valid);
        Assert.Equal(
            "payload sidecar identity does not match its manifests",
            failure);
    }

    [Fact]
    public void StablePayloadUrlRejectsPayloadSizeDrift()
    {
        bool valid = ValidateSealed(
            Sidecar(sizeBytes: PayloadSizeBytes + 1),
            ProjectedPayloadUrl,
            "open_public",
            ArtifactId,
            out string? failure);

        Assert.False(valid);
        Assert.Equal(
            "payload sidecar identity does not match its manifests",
            failure);
    }

    [Theory]
    [InlineData("open_public")]
    [InlineData("account_recommended")]
    [InlineData("account_required")]
    public void ExactRelativeSemanticRouteRemainsValidForEveryAccessClass(
        string installAccessClass)
    {
        bool valid = ValidateSealed(
            Sidecar(downloadUrl: ProjectedPayloadUrl),
            ProjectedPayloadUrl,
            installAccessClass,
            ArtifactId,
            out string? failure);

        Assert.True(valid, failure);
    }

    [Fact]
    public void ExactCanonicalAbsoluteSemanticRouteRemainsValid()
    {
        bool valid = ValidateSealed(
            Sidecar(downloadUrl: "https://chummer.run" + ProjectedPayloadUrl),
            ProjectedPayloadUrl,
            "account_required",
            ArtifactId,
            out string? failure);

        Assert.True(valid, failure);
    }

    [Theory]
    [InlineData("http://chummer.run")]
    [InlineData("https://www.chummer.run")]
    [InlineData("https://Chummer.run")]
    [InlineData("https://attacker@chummer.run")]
    [InlineData("https://chummer.run:443")]
    [InlineData("https://chummer.run:444")]
    public void AbsoluteSemanticRouteRejectsNoncanonicalOrigin(
        string origin)
    {
        bool valid = ValidateSealed(
            Sidecar(downloadUrl: origin + ProjectedPayloadUrl),
            ProjectedPayloadUrl,
            "account_required",
            ArtifactId,
            out _);

        Assert.False(valid);
    }

    [Theory]
    [InlineData("https://chummer.run/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload?download=1")]
    [InlineData("https://chummer.run/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload#payload")]
    [InlineData("https://chummer.run/downloads/g/g%2D20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload")]
    [InlineData("https://chummer.run/downloads/g/../g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload")]
    [InlineData("https://chummer.run/downloads/g/./g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload")]
    [InlineData("https://chummer.run/downloads//g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload")]
    [InlineData("https://chummer.run/downloads/g/g-20260724T111416Z-48dd860a787641a0/install/avalonia-win-x64-installer/payload/")]
    public void AbsoluteSemanticRouteRejectsNoncanonicalPath(
        string sidecarUrl)
    {
        bool valid = ValidateSealed(
            Sidecar(downloadUrl: sidecarUrl),
            ProjectedPayloadUrl,
            "account_required",
            ArtifactId,
            out _);

        Assert.False(valid);
    }

    [Theory]
    [InlineData(" arbitrary-equal-mutable-route ")]
    [InlineData("/downloads/files/chummer-avalonia-win-x64-payload.zip")]
    public void MutableIncomingEqualUrlRetainsLegacyTrimmingSemantics(
        string sharedUrl)
    {
        bool valid = Validate(
            Sidecar(downloadUrl: sharedUrl),
            sharedUrl,
            installAccessClass: null,
            artifactId: null,
            allowMutableIncomingUrl: true,
            out string? failure);

        Assert.True(valid, failure);
    }

    [Fact]
    public void MutableIncomingCanonicalAbsoluteStableUrlRemainsValid()
    {
        bool valid = Validate(
            Sidecar(),
            "/unrelated/incoming/manifest/route",
            installAccessClass: "account_required",
            artifactId: ArtifactId,
            allowMutableIncomingUrl: true,
            out string? failure);

        Assert.True(valid, failure);
    }

    private static byte[] Sidecar(
        string downloadUrl = StablePayloadUrl,
        string sha256 = PayloadSha256,
        long sizeBytes = PayloadSizeBytes)
        => JsonSerializer.SerializeToUtf8Bytes(new
        {
            contractName = "chummer6-ui.windows_bootstrap_payload",
            fileName = PayloadFileName,
            downloadUrl,
            sha256,
            sizeBytes,
            installerFileName = InstallerFileName,
            releaseVersion = ReleaseVersion
        });

    private static bool ValidateSealed(
        byte[] sidecar,
        string manifestUrl,
        string? installAccessClass,
        string? artifactId,
        out string? failure)
        => Validate(
            sidecar,
            manifestUrl,
            installAccessClass,
            artifactId,
            allowMutableIncomingUrl: false,
            out failure);

    private static bool Validate(
        byte[] sidecar,
        string manifestUrl,
        string? installAccessClass,
        string? artifactId,
        bool allowMutableIncomingUrl,
        out string? failure)
        => PayloadSidecarContractValidator.TryValidate(
            sidecar,
            InstallerFileName,
            PayloadFileName,
            manifestUrl,
            PayloadSha256,
            PayloadSizeBytes,
            ReleaseVersion,
            allowMutableIncomingUrl,
            out failure,
            installAccessClass,
            artifactId);
}
