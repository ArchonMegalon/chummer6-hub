using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseSelectionServiceTests
{
    [Fact]
    public void BuildExperienceLoadsCurrentPublicReleaseCanon()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
        var manifest = new PublicReleaseManifestDto(
            Version: "run-20260401-065126",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-04-01T06:51:26Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-linux-x64-installer",
                    Platform: "Avalonia Desktop Linux X64 Installer",
                    Url: "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                    Sha256: "6b0a63c39850a257e66d142c0bad196a7cc4fcbaf027635965f138f534bb13ea",
                    SizeBytes: 34297862,
                    Head: "avalonia",
                    PlatformId: "linux",
                    Arch: "x64",
                    Kind: "installer",
                    FileName: "chummer-avalonia-linux-x64-installer.deb",
                    InstallAccessClass: "open_public")
            ]);

        var experience = service.BuildExperience(manifest, userAgent: "Mozilla/5.0 (X11; Linux x86_64)", authenticated: false);

        Assert.Equal("Preview channel", experience.Display.ChannelLabel);
        Assert.Equal("Need install help?", experience.InstallHelpLabel);
        Assert.NotNull(experience.Recommended);
        Assert.Equal("Avalonia Desktop Linux X64 Installer", experience.Recommended!.Artifact.Platform);
    }
}
