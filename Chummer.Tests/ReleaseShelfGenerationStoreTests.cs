using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseShelfGenerationStoreTests
{
    [Fact]
    public void InventoryDigestMatchesCrossLanguageGoldenFixture()
    {
        string fixturePath = Path.Combine(
            Directory.GetParent(ResolveSharedFixtureRoot())!.FullName,
            "atomic_release_shelf_inventory_digest_v1.json");
        using JsonDocument fixture = JsonDocument.Parse(File.ReadAllText(fixturePath));
        JsonElement root = fixture.RootElement;
        ReleaseShelfInventoryEntry[] inventory = root
            .GetProperty("inventory")
            .EnumerateArray()
            .Select(static row => new ReleaseShelfInventoryEntry(
                row.GetProperty("path").GetString()!,
                row.GetProperty("sha256").GetString()!,
                SizeBytes: 0))
            .ToArray();

        string digest = ReleaseShelfGenerationStore.ComputeInventoryDigest(inventory);

        Assert.Equal(root.GetProperty("sha256").GetString(), digest);
    }

    [Fact]
    public void BuildInventoryRejectsNonportableUnicodePaths()
    {
        string generationRoot = Path.Combine(
            Path.GetTempPath(),
            "release-shelf-portable-inventory-tests",
            Guid.NewGuid().ToString("N"));
        try
        {
            string filesRoot = Path.Combine(generationRoot, "files");
            Directory.CreateDirectory(filesRoot);
            File.WriteAllText(Path.Combine(filesRoot, "über.bin"), "fixture");

            InvalidDataException exception = Assert.Throws<InvalidDataException>(
                () => ReleaseShelfGenerationStore.BuildInventory(generationRoot));
            Assert.Contains("not portable ASCII", exception.Message, StringComparison.Ordinal);
        }
        finally
        {
            if (Directory.Exists(generationRoot))
            {
                Directory.Delete(generationRoot, recursive: true);
            }
        }
    }

    [Fact]
    public void ReaderConsumesSharedPythonPublisherContractFixture()
    {
        string fixtureRoot = ResolveSharedFixtureRoot();
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = fixtureRoot
            })
            .Build();

        ReleaseShelfSnapshot snapshot = new ReleaseShelfGenerationStore(configuration).Capture();

        Assert.False(snapshot.IsLegacy);
        Assert.Equal("gen-20260715T160912Z-0123456789ab", snapshot.GenerationId);
        Assert.Equal("run-fixture-20260715-160912", snapshot.ReleaseVersion);
        Assert.Equal("47c07b4a56faf5213f2bcab7707b0330d74821311bfa30683bcddca54c795a83", snapshot.InventoryDigest);
        using ReleaseShelfVerifiedFile? fixtureArtifact = snapshot.OpenVerifiedFile("files/chummer-fixture.dmg");
        using ReleaseShelfVerifiedFile? fixtureProof = snapshot.OpenVerifiedFile("proof/mac/release-proof.json");
        using ReleaseShelfVerifiedFile? fixtureEvidence = snapshot.OpenVerifiedFile("release-evidence/public-promotion.json");
        Assert.NotNull(fixtureArtifact);
        Assert.NotNull(fixtureProof);
        Assert.NotNull(fixtureEvidence);
    }

    [Fact]
    public void RetainedSharedFixtureGenerationReopensFromBoundCandidateAfterAnotherActivation()
    {
        string sourceRoot = ResolveSharedFixtureRoot();
        string tempRoot = Path.Combine(
            Path.GetTempPath(),
            "release-shelf-shared-retained-tests",
            Guid.NewGuid().ToString("N"));
        try
        {
            CopyDirectory(sourceRoot, tempRoot);
            const string retainedId = "gen-20260715T160912Z-0123456789ab";
            const string activeId = "gen-20260715T170000Z-fedcba987654";
            const string retainedVersion = "run-fixture-20260715-160912";
            const string activeVersion = "run-fixture-20260715-170000";
            string retainedRoot = Path.Combine(tempRoot, "generations", retainedId);
            string activeRoot = Path.Combine(tempRoot, "generations", activeId);
            CopyDirectory(retainedRoot, activeRoot);

            foreach (string manifestName in new[]
                     {
                         ReleaseShelfGenerationStore.CanonicalManifestFileName,
                         ReleaseShelfGenerationStore.CompatibilityManifestFileName
                     })
            {
                string path = Path.Combine(activeRoot, manifestName);
                string json = File.ReadAllText(path)
                    .Replace(retainedId, activeId, StringComparison.Ordinal)
                    .Replace(retainedVersion, activeVersion, StringComparison.Ordinal);
                File.WriteAllText(path, json);
            }

            using JsonDocument originalPointer = JsonDocument.Parse(File.ReadAllText(
                Path.Combine(tempRoot, ReleaseShelfGenerationStore.CurrentPointerFileName)));
            WriteCommittedActivationJournal(
                tempRoot,
                File.ReadAllBytes(Path.Combine(tempRoot, ReleaseShelfGenerationStore.CurrentPointerFileName)),
                previousPointerBytes: null);
            string candidatePath = Path.Combine(activeRoot, "activation-candidate.json");
            using (JsonDocument candidate = JsonDocument.Parse(File.ReadAllText(candidatePath)))
            {
                JsonElement inventory = candidate.RootElement.GetProperty("inventory").Clone();
                File.WriteAllText(
                    candidatePath,
                    JsonSerializer.Serialize(new
                    {
                        schemaVersion = "chummer.release-shelf.activation-candidate/v1",
                        generationId = activeId,
                        releaseVersion = activeVersion,
                        channel = "preview",
                        publishedAt = "2026-07-15T16:09:12Z",
                        manifests = BuildManifestBindings(
                            activeId,
                            Sha256File(Path.Combine(activeRoot, ReleaseShelfGenerationStore.CanonicalManifestFileName)),
                            Sha256File(Path.Combine(activeRoot, ReleaseShelfGenerationStore.CompatibilityManifestFileName))),
                        inventoryDigest = originalPointer.RootElement
                            .GetProperty("inventoryDigest")
                            .GetString(),
                        inventory
                    }));
            }

            string inventoryDigest = originalPointer.RootElement
                .GetProperty("inventoryDigest")
                .GetString()!["sha256:".Length..];
            File.WriteAllText(
                Path.Combine(tempRoot, ReleaseShelfGenerationStore.CurrentPointerFileName),
                JsonSerializer.Serialize(new
                {
                    schemaVersion = "chummer.release-shelf.current/v1",
                    generationId = activeId,
                    releaseVersion = activeVersion,
                    channel = "preview",
                    publishedAt = "2026-07-15T16:09:12Z",
                    manifests = BuildManifestBindings(
                        activeId,
                        Sha256File(Path.Combine(activeRoot, ReleaseShelfGenerationStore.CanonicalManifestFileName)),
                        Sha256File(Path.Combine(activeRoot, ReleaseShelfGenerationStore.CompatibilityManifestFileName))),
                    inventoryDigest = $"sha256:{inventoryDigest}",
                    activatedAt = "2026-07-15T17:00:00Z",
                    activationReceiptId = "activation-fixture-second"
                }));

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = tempRoot
                })
                .Build();
            var store = new ReleaseShelfGenerationStore(configuration);

            Assert.Equal(activeId, store.Capture().GenerationId);
            ReleaseShelfSnapshot retained = store.CaptureGeneration(retainedId);
            Assert.Equal(retainedId, retained.GenerationId);
            Assert.Equal(retainedVersion, retained.ReleaseVersion);
            Assert.True(retained.IsExplicitGeneration);
            Assert.Equal(
                DateTimeOffset.Parse("2026-07-15T16:09:15Z"),
                retained.ActivatedAt);
            Assert.Equal("activation-fixture-20260715-160915", retained.ActivationReceiptId);
            using ReleaseShelfVerifiedFile? retainedArtifact = retained.OpenVerifiedFile("files/chummer-fixture.dmg");
            Assert.NotNull(retainedArtifact);
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    [Fact]
    public void CaptureUsesLegacyRootOnlyWhenMarkerAndPointerAreBothAbsent()
    {
        using var fixture = new ReleaseShelfFixture();

        ReleaseShelfSnapshot snapshot = fixture.CreateStore().Capture();

        Assert.True(snapshot.IsLegacy);
        Assert.Equal(Path.GetFullPath(fixture.DownloadsRoot), snapshot.PhysicalRoot);

        File.WriteAllText(Path.Combine(fixture.DownloadsRoot, ReleaseShelfGenerationStore.LayoutMarkerFileName), "v1\n");
        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());

        File.Delete(Path.Combine(fixture.DownloadsRoot, ReleaseShelfGenerationStore.LayoutMarkerFileName));
        File.WriteAllText(Path.Combine(fixture.DownloadsRoot, ReleaseShelfGenerationStore.CurrentPointerFileName), "{}");
        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());
    }

    [Fact]
    public void EmptyGenerationDirectoryStillAllowsControlledInitialLegacyMigration()
    {
        using var fixture = new ReleaseShelfFixture();
        Directory.CreateDirectory(Path.Combine(
            fixture.DownloadsRoot,
            ReleaseShelfGenerationStore.GenerationsDirectoryName));

        ReleaseShelfSnapshot snapshot = fixture.CreateStore().Capture();

        Assert.True(snapshot.IsLegacy);
    }

    [Fact]
    public void CaptureAllowsOnlyTopLevelReleaseProofRoutesToRemainCanonical()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration(
            "generation-a",
            "run-a",
            "artifact-a",
            topLevelProofRoutes: ["/downloads/install/test-installer"]);
        fixture.Activate("generation-a", "run-a");

        ReleaseShelfSnapshot snapshot = fixture.CreateStore().Capture();

        Assert.Equal("generation-a", snapshot.GenerationId);
    }

    [Fact]
    public void CaptureRejectsNestedReleaseProofLookalikeEvenWithGenerationBoundRoute()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration(
            "generation-a",
            "run-a",
            "artifact-a",
            topLevelProofRoutes: ["/downloads/install/test-installer"],
            nestedProofRoutes: ["/downloads/g/generation-a/install/test-installer"]);
        fixture.Activate("generation-a", "run-a");

        InvalidDataException error = Assert.Throws<InvalidDataException>(
            () => fixture.CreateStore().Capture());

        Assert.Contains("lookalike", error.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void CaptureRejectsManifestMissingGenerationId(bool canonical)
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration(
            "generation-a",
            "run-a",
            "artifact-a",
            omitCanonicalGenerationId: canonical,
            omitCompatibilityGenerationId: !canonical);
        fixture.Activate("generation-a", "run-a");

        InvalidDataException error = Assert.Throws<InvalidDataException>(
            () => fixture.CreateStore().Capture());

        Assert.Contains("generationId", error.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void CaptureRejectsManifestGenerationIdThatDoesNotMatchActiveGeneration(bool canonical)
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration(
            "generation-a",
            "run-a",
            "artifact-a",
            canonicalGenerationIdOverride: canonical ? "generation-b" : null,
            compatibilityGenerationIdOverride: canonical ? null : "generation-b");
        fixture.Activate("generation-a", "run-a");

        InvalidDataException error = Assert.Throws<InvalidDataException>(
            () => fixture.CreateStore().Capture());

        Assert.Contains("does not match the active generation", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void PreparedGenerationKeepsLegacyServingOnlyDuringExplicitInitialMigration()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        IConfiguration migrationConfiguration = new ConfigurationBuilder()
            .AddConfiguration(fixture.Configuration)
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"] = "true"
            })
            .Build();

        ReleaseShelfSnapshot snapshot = new ReleaseShelfGenerationStore(migrationConfiguration).Capture();

        Assert.True(snapshot.IsLegacy);
        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());
    }

    [Fact]
    public void RetainedGenerationRejectsLegacyFallbackAfterPointerAndMarkerDeletion()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.Activate("generation-a", "run-a");
        File.Delete(Path.Combine(
            fixture.DownloadsRoot,
            ReleaseShelfGenerationStore.LayoutMarkerFileName));
        File.Delete(Path.Combine(
            fixture.DownloadsRoot,
            ReleaseShelfGenerationStore.CurrentPointerFileName));

        InvalidDataException exception = Assert.Throws<InvalidDataException>(
            () => fixture.CreateStore().Capture());

        Assert.Contains(
            "committed activation history",
            exception.Message,
            StringComparison.Ordinal);
    }

    [Fact]
    public void CaseVariantGenerationFootprintsCannotMaskEachOtherOnCaseSensitiveFileSystems()
    {
        if (OperatingSystem.IsWindows() || OperatingSystem.IsMacOS())
        {
            return;
        }

        using var fixture = new ReleaseShelfFixture();
        Directory.CreateDirectory(Path.Combine(
            fixture.DownloadsRoot,
            ReleaseShelfGenerationStore.GenerationsDirectoryName));
        string caseVariant = Path.Combine(fixture.DownloadsRoot, "GENERATIONS");
        Directory.CreateDirectory(caseVariant);
        File.WriteAllText(Path.Combine(caseVariant, "retained-generation"), "fixture");

        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());
    }

    [Theory]
    [InlineData(ReleaseShelfGenerationStore.LayoutMarkerFileName)]
    [InlineData(ReleaseShelfGenerationStore.CurrentPointerFileName)]
    public void MalformedControlDirectoriesNeverCountAsAbsent(string controlName)
    {
        using var fixture = new ReleaseShelfFixture();
        Directory.CreateDirectory(Path.Combine(fixture.DownloadsRoot, controlName));

        InvalidDataException exception = Assert.Throws<InvalidDataException>(
            () => fixture.CreateStore().Capture());

        Assert.Contains("must be a regular file", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void BrokenControlSymlinkNeverCountsAsAbsent()
    {
        if (!(OperatingSystem.IsLinux() || OperatingSystem.IsFreeBSD()))
        {
            return;
        }

        using var fixture = new ReleaseShelfFixture();
        string pointerPath = Path.Combine(
            fixture.DownloadsRoot,
            ReleaseShelfGenerationStore.CurrentPointerFileName);
        File.CreateSymbolicLink(pointerPath, Path.Combine(fixture.DownloadsRoot, "missing-pointer-target"));

        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());
    }

    [Fact]
    public void RequiredLayoutSentinelRejectsMarkerAndPointerDeletionDowngrade()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.Activate("generation-a", "run-a");
        IConfiguration requiredConfiguration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = fixture.DownloadsRoot,
                ["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"] = "true"
            })
            .Build();
        var store = new ReleaseShelfGenerationStore(requiredConfiguration);
        Assert.Equal("generation-a", store.Capture().GenerationId);

        File.Delete(Path.Combine(fixture.DownloadsRoot, ReleaseShelfGenerationStore.LayoutMarkerFileName));
        File.Delete(Path.Combine(fixture.DownloadsRoot, ReleaseShelfGenerationStore.CurrentPointerFileName));

        Assert.Throws<InvalidDataException>(() => new ReleaseShelfGenerationStore(requiredConfiguration).Capture());
    }

    [Fact]
    public void ValidPointerIsAuthoritativeBeforePostCommitMarkerExists()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.Activate("generation-a", "run-a");
        File.Delete(Path.Combine(
            fixture.DownloadsRoot,
            ReleaseShelfGenerationStore.LayoutMarkerFileName));

        ReleaseShelfSnapshot snapshot = fixture.CreateStore().Capture();

        Assert.False(snapshot.IsLegacy);
        Assert.Equal("generation-a", snapshot.GenerationId);
    }

    [Theory]
    [InlineData("../escape")]
    [InlineData("/absolute")]
    [InlineData("..")]
    [InlineData("generation/child")]
    [InlineData("bad..generation")]
    public void CaptureRejectsTraversalUnsafeGenerationIds(string generationId)
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteLayoutMarker();
        fixture.WritePointer(new Dictionary<string, object?>
        {
            ["schemaVersion"] = "chummer.release-shelf.current/v1",
            ["generationId"] = generationId,
            ["releaseVersion"] = "run-bad",
            ["channel"] = "preview",
            ["publishedAt"] = ReleaseShelfFixture.PublishedAt,
            ["manifests"] = BuildManifestBindings(generationId, new string('a', 64), new string('b', 64)),
            ["inventoryDigest"] = $"sha256:{new string('c', 64)}",
            ["activatedAt"] = ReleaseShelfFixture.PublishedAt,
            ["activationReceiptId"] = "receipt-bad"
        });

        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());
    }

    [Fact]
    public void CaptureRejectsMalformedPointerMissingGenerationAndDigestMismatch()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteLayoutMarker();
        File.WriteAllText(fixture.PointerPath, "not-json");
        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());

        fixture.WritePointer(new Dictionary<string, object?>
        {
            ["schemaVersion"] = "chummer.release-shelf.current/v1",
            ["generationId"] = "missing-generation",
            ["releaseVersion"] = "run-missing",
            ["channel"] = "preview",
            ["publishedAt"] = ReleaseShelfFixture.PublishedAt,
            ["manifests"] = BuildManifestBindings("missing-generation", new string('a', 64), new string('b', 64)),
            ["inventoryDigest"] = $"sha256:{new string('c', 64)}",
            ["activatedAt"] = ReleaseShelfFixture.PublishedAt,
            ["activationReceiptId"] = "receipt-missing"
        });
        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());

        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.Activate("generation-a", "run-a", canonicalShaOverride: new string('0', 64));
        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());
    }

    [Fact]
    public void RequestKeepsItsFirstGenerationAfterCurrentPointerChanges()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.WriteGeneration("generation-b", "run-b", "artifact-b");
        fixture.Activate("generation-a", "run-a");
        var accessor = new HttpContextAccessor { HttpContext = new DefaultHttpContext() };
        var store = new ReleaseShelfGenerationStore(fixture.Configuration, accessor);

        ReleaseShelfSnapshot first = store.CaptureForCurrentRequest();
        fixture.Activate("generation-b", "run-b");
        ReleaseShelfSnapshot sameRequest = store.CaptureForCurrentRequest();

        Assert.Same(first, sameRequest);
        Assert.Equal("generation-a", sameRequest.GenerationId);
        using ReleaseShelfVerifiedFile? sameRequestArtifact = sameRequest.OpenVerifiedFile("files/chummer-test.bin");
        Assert.NotNull(sameRequestArtifact);
        Assert.EndsWith(
            Path.Combine("generations", "generation-a", "files", "chummer-test.bin"),
            sameRequestArtifact!.PhysicalPath,
            StringComparison.Ordinal);

        accessor.HttpContext = new DefaultHttpContext();
        ReleaseShelfSnapshot nextRequest = store.CaptureForCurrentRequest();
        Assert.Equal("generation-b", nextRequest.GenerationId);
        using ReleaseShelfVerifiedFile? nextRequestArtifact = nextRequest.OpenVerifiedFile("files/chummer-test.bin");
        Assert.NotNull(nextRequestArtifact);
        Assert.EndsWith(
            Path.Combine("generations", "generation-b", "files", "chummer-test.bin"),
            nextRequestArtifact!.PhysicalPath,
            StringComparison.Ordinal);
    }

    [Fact]
    public void RequestSnapshotRejectsSwitchingToAnotherExplicitGeneration()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.WriteGeneration("generation-b", "run-b", "artifact-b");
        fixture.Activate("generation-a", "run-a");
        var accessor = new HttpContextAccessor { HttpContext = new DefaultHttpContext() };
        var store = new ReleaseShelfGenerationStore(fixture.Configuration, accessor);

        ReleaseShelfSnapshot first = store.CaptureGenerationForCurrentRequest("generation-a");
        Assert.Throws<InvalidOperationException>(
            () => store.CaptureGenerationForCurrentRequest("generation-b"));
        Assert.Same(first, store.CaptureForCurrentRequest());
    }

    [Fact]
    public void CapturedInventoryRejectsMutatedAndAddedFilesAtEveryOpenBoundary()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.Activate("generation-a", "run-a");
        ReleaseShelfSnapshot snapshot = fixture.CreateStore().Capture();
        string generationRoot = Path.Combine(fixture.DownloadsRoot, "generations", "generation-a");
        string artifactPath = Path.Combine(generationRoot, "files", "chummer-test.bin");

        using (ReleaseShelfVerifiedFile? verified = snapshot.OpenVerifiedFile("files/chummer-test.bin"))
        {
            Assert.NotNull(verified);
            Assert.Equal("artifact-a", new StreamReader(verified!.Stream).ReadToEnd());
        }

        File.WriteAllText(artifactPath, "artifact-z");
        Assert.Null(snapshot.OpenVerifiedFile("files/chummer-test.bin"));

        File.WriteAllText(Path.Combine(generationRoot, "files", "added.bin"), "added");
        Assert.Null(snapshot.OpenVerifiedFile("files/added.bin"));
    }

    [Fact]
    public void ActivationInventoryExcludesManifestsThenSnapshotBindsTheirPointerDigestsSeparately()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        string generationRoot = Path.Combine(fixture.DownloadsRoot, "generations", "generation-a");

        IReadOnlyList<ReleaseShelfInventoryEntry> activationInventory =
            ReleaseShelfGenerationStore.BuildInventory(generationRoot);
        Assert.DoesNotContain(
            activationInventory,
            row => row.Path is ReleaseShelfGenerationStore.CanonicalManifestFileName
                or ReleaseShelfGenerationStore.CompatibilityManifestFileName);

        fixture.Activate("generation-a", "run-a");
        ReleaseShelfSnapshot snapshot = fixture.CreateStore().Capture();
        Assert.True(snapshot.Inventory.ContainsKey(ReleaseShelfGenerationStore.CanonicalManifestFileName));
        Assert.True(snapshot.Inventory.ContainsKey(ReleaseShelfGenerationStore.CompatibilityManifestFileName));
        Assert.Equal(
            snapshot.CanonicalManifestSha256,
            snapshot.Inventory[ReleaseShelfGenerationStore.CanonicalManifestFileName].Sha256);
        Assert.Equal(
            snapshot.CompatibilityManifestSha256,
            snapshot.Inventory[ReleaseShelfGenerationStore.CompatibilityManifestFileName].Sha256);
    }

    [Fact]
    public void BuildInventoryExcludesOnlyRootMetadataAndIncludesNestedMatchingBasenames()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        string generationRoot = Path.Combine(fixture.DownloadsRoot, "generations", "generation-a");
        foreach (string name in new[]
                 {
                     "activation-candidate.json",
                     ReleaseShelfGenerationStore.CanonicalManifestFileName,
                     ReleaseShelfGenerationStore.CompatibilityManifestFileName
                 })
        {
            File.WriteAllText(Path.Combine(generationRoot, "files", name), name);
        }

        IReadOnlyList<ReleaseShelfInventoryEntry> inventory =
            ReleaseShelfGenerationStore.BuildInventory(generationRoot);

        Assert.DoesNotContain(inventory, row => row.Path is "activation-candidate.json"
            or ReleaseShelfGenerationStore.CanonicalManifestFileName
            or ReleaseShelfGenerationStore.CompatibilityManifestFileName);
        Assert.Contains(inventory, row => row.Path == "files/activation-candidate.json");
        Assert.Contains(
            inventory,
            row => row.Path == $"files/{ReleaseShelfGenerationStore.CanonicalManifestFileName}");
        Assert.Contains(
            inventory,
            row => row.Path == $"files/{ReleaseShelfGenerationStore.CompatibilityManifestFileName}");
    }

    [Fact]
    public void CaptureRejectsCandidateInventoryThatAddsPointerBoundManifestMetadata()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.AddExcludedMetadataToCandidateInventoryAndActivate(
            "generation-a",
            "run-a",
            ReleaseShelfGenerationStore.CanonicalManifestFileName);

        InvalidDataException exception = Assert.Throws<InvalidDataException>(
            () => fixture.CreateStore().Capture());
        Assert.Contains("excluded metadata or an unexpected path", exception.Message);
    }

    [Fact]
    public void CaptureAcceptsExactGenerationInstallRouteForProtectedArtifact()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration(
            "generation-a",
            "run-a",
            "artifact-a",
            installAccessClass: "account_required");
        fixture.Activate("generation-a", "run-a");

        ReleaseShelfSnapshot snapshot = fixture.CreateStore().Capture();

        Assert.Equal("generation-a", snapshot.GenerationId);
    }

    [Theory]
    [InlineData("/downloads/g/generation-a/install/test-installer/claim")]
    [InlineData("/downloads/g/generation-a/install/test-installer?ticket=x")]
    [InlineData("/downloads/g/generation-a/install/test-installer#claim")]
    [InlineData("/downloads/g/generation-a/install/test-installer%2Fclaim")]
    [InlineData("/downloads/g/generation-a/files/nested/chummer-test.bin")]
    [InlineData("/downloads/g/generation-a/proof")]
    [InlineData("https://chummer.run/downloads/g/generation-a/install/test-installer")]
    [InlineData("//chummer.run/downloads/g/generation-a/install/test-installer")]
    [InlineData("/downloads/g/generation-a/files\\chummer-test.bin")]
    public void CaptureRejectsMalformedOrNoncanonicalGenerationRoute(string route)
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration(
            "generation-a",
            "run-a",
            "artifact-a",
            installAccessClass: "account_required",
            artifactDownloadUrlOverride: route);
        fixture.Activate("generation-a", "run-a");

        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());
    }

    [Fact]
    public void ArtifactOpenRequiresExactManifestPathDigestAndCase()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration(
            "generation-a",
            "run-a",
            "artifact-a",
            extraFiles: new Dictionary<string, string>
            {
                ["files/nested/chummer-test.bin"] = "shadow"
            });
        fixture.Activate("generation-a", "run-a");
        var store = fixture.CreateStore();
        ReleaseShelfSnapshot snapshot = store.Capture();
        var service = new PublicReleaseManifestService(fixture.Configuration, store);
        PublicReleaseArtifactDto artifact = Assert.Single(service.LoadManifest(snapshot).Downloads);

        using ReleaseShelfVerifiedFile? exact = service.OpenVerifiedArtifactFile(
            snapshot,
            artifact,
            "chummer-test.bin");
        Assert.NotNull(exact);
        Assert.Null(service.OpenVerifiedArtifactFile(
            snapshot,
            artifact,
            "nested/chummer-test.bin"));
        Assert.Null(service.OpenVerifiedArtifactFile(
            snapshot,
            artifact,
            "CHUMMER-TEST.BIN"));
        Assert.Null(service.OpenVerifiedArtifactFile(
            snapshot,
            artifact with { Sha256 = new string('a', 64) },
            "chummer-test.bin"));
    }

    [Fact]
    public void WindowsProofGenerationNeverFallsBackToProtectedFilesAndReverifiesBeforeServing()
    {
        const string proofFileName = "chummer-avalonia-win-x64-installer.exe";
        const string proofBytes = "prefix ChummerInstaller.Payload.zip middle Samples/Legacy/Soma-Career.chum5 suffix";
        string proofSha256 = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(proofBytes)));
        string signingReceipt = JsonSerializer.Serialize(new
        {
            contractName = "chummer6-ui.desktop_artifact_signing",
            generatedAt = "2026-06-19T12:01:00Z",
            platform = "windows",
            app = "avalonia",
            rid = "win-x64",
            releaseChannel = "preview",
            releaseVersion = "run-b",
            signingStatus = "pass",
            notarizationStatus = (string?)null,
            artifacts = new[]
            {
                new
                {
                    fileName = proofFileName,
                    sha256 = proofSha256,
                    kind = "installer",
                    signingStatus = "pass",
                    notarizationStatus = (string?)null
                }
            }
        });
        using var fallbackFixture = new ReleaseShelfFixture();
        fallbackFixture.WriteGeneration(
            "generation-a",
            "run-a",
            "artifact-a",
            extraFiles: new Dictionary<string, string>
            {
                [$"files/{proofFileName}"] = proofBytes
            });
        fallbackFixture.Activate("generation-a", "run-a");
        ReleaseShelfSnapshot fallbackSnapshot = fallbackFixture.CreateStore().Capture();
        var fallbackService = new WindowsProofInstallerService(
            fallbackFixture.Configuration,
            fallbackFixture.CreateStore());
        Assert.Null(fallbackService.FindByFileName(fallbackSnapshot, proofFileName));

        using var proofFixture = new ReleaseShelfFixture();
        proofFixture.WriteGeneration(
            "generation-b",
            "run-b",
            "artifact-b",
            extraFiles: new Dictionary<string, string>
            {
                [$"proof/windows/{proofFileName}"] = proofBytes,
                ["signing/signing-avalonia-win-x64.receipt.json"] = signingReceipt
            });
        proofFixture.Activate("generation-b", "run-b");
        ReleaseShelfSnapshot proofSnapshot = proofFixture.CreateStore().Capture();
        var proofService = new WindowsProofInstallerService(
            proofFixture.Configuration,
            proofFixture.CreateStore());
        WindowsProofInstallerRecord record = Assert.IsType<WindowsProofInstallerRecord>(
            proofService.FindByFileName(proofSnapshot, proofFileName));
        File.WriteAllText(
            Path.Combine(proofSnapshot.PhysicalRoot, record.RelativePath),
            "tampered after catalog lookup");

        Assert.Null(proofService.OpenVerifiedInstaller(proofSnapshot, record));
    }

    [Fact]
    public void BuildInventoryRejectsCaseCollidingPaths()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        string filesRoot = Path.Combine(
            fixture.DownloadsRoot,
            "generations",
            "generation-a",
            "files");
        File.WriteAllText(Path.Combine(filesRoot, "CASE.bin"), "upper");
        File.WriteAllText(Path.Combine(filesRoot, "case.bin"), "lower");

        Assert.Throws<InvalidDataException>(() => ReleaseShelfGenerationStore.BuildInventory(
            Path.GetDirectoryName(filesRoot)!));
    }

    [Fact]
    public void CaptureRejectsManifestBeyondStrictByteCapBeforeParsing()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        string canonicalPath = Path.Combine(
            fixture.DownloadsRoot,
            "generations",
            "generation-a",
            ReleaseShelfGenerationStore.CanonicalManifestFileName);
        File.AppendAllText(canonicalPath, new string(' ', ReleaseShelfGenerationStore.MaximumManifestBytes));
        fixture.Activate("generation-a", "run-a");

        Assert.Throws<InvalidDataException>(() => fixture.CreateStore().Capture());
    }

    [Fact]
    public void ManifestCacheIsGenerationKeyed()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.WriteGeneration("generation-b", "run-b", "artifact-b");
        fixture.Activate("generation-a", "run-a");
        var store = fixture.CreateStore();
        var service = new PublicReleaseManifestService(fixture.Configuration, store);

        ReleaseShelfSnapshot generationA = store.Capture();
        Assert.Equal("run-a", service.LoadManifest(generationA).Version);

        fixture.Activate("generation-b", "run-b");
        ReleaseShelfSnapshot generationB = store.Capture();
        Assert.Equal("run-b", service.LoadManifest(generationB).Version);
        Assert.Equal("run-a", service.LoadManifest(generationA).Version);
    }

    [Fact]
    public void GenerationManifestReadsReturnExactPointerBoundBytes()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.Activate("generation-a", "run-a");
        var store = fixture.CreateStore();
        var service = new PublicReleaseManifestService(fixture.Configuration, store);
        ReleaseShelfSnapshot snapshot = store.CaptureGeneration("generation-a");

        byte[] canonical = Assert.IsType<byte[]>(service.LoadGenerationCanonicalManifestBytes(snapshot));
        byte[] compatibility = Assert.IsType<byte[]>(service.LoadGenerationCompatibilityManifestBytes(snapshot));

        Assert.Equal(snapshot.CanonicalManifestSha256, Convert.ToHexStringLower(SHA256.HashData(canonical)));
        Assert.Equal(snapshot.CompatibilityManifestSha256, Convert.ToHexStringLower(SHA256.HashData(compatibility)));
        Assert.Equal(
            File.ReadAllBytes(Path.Combine(snapshot.PhysicalRoot, ReleaseShelfGenerationStore.CanonicalManifestFileName)),
            canonical);
        Assert.Equal(
            File.ReadAllBytes(Path.Combine(snapshot.PhysicalRoot, ReleaseShelfGenerationStore.CompatibilityManifestFileName)),
            compatibility);
        byte[] canonicalBeforeProjection = canonical.ToArray();
        using JsonDocument projected = JsonDocument.Parse(
            Assert.IsType<string>(service.LoadCanonicalManifestJson(snapshot)));
        Assert.Equal("run-a", projected.RootElement.GetProperty("version").GetString());
        Assert.Equal(
            "review_required",
            projected.RootElement.GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "missing",
            projected.RootElement
                .GetProperty("publicTrustMetrics")
                .GetProperty("proofFreshness")
                .GetProperty("status")
                .GetString());
        Assert.Equal(
            canonicalBeforeProjection,
            service.LoadGenerationCanonicalManifestBytes(snapshot));
    }

    [Fact]
    public void LayoutV1CurrentManifestAndCompatibilityProjectionLowerMissingProofWithoutMutatingGeneration()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.Activate("generation-a", "run-a");
        var store = fixture.CreateStore();
        var service = new PublicReleaseManifestService(fixture.Configuration, store);
        ReleaseShelfSnapshot snapshot = store.Capture();
        byte[] canonicalBefore = Assert.IsType<byte[]>(
            service.LoadGenerationCanonicalManifestBytes(snapshot));
        byte[] compatibilityBefore = Assert.IsType<byte[]>(
            service.LoadGenerationCompatibilityManifestBytes(snapshot));

        PublicReleaseManifestDto compatibility = service.LoadManifest(snapshot);
        using JsonDocument canonical = JsonDocument.Parse(
            Assert.IsType<string>(service.LoadCanonicalManifestJson(snapshot)));

        Assert.Equal("review_required", compatibility.SupportabilityState);
        Assert.Equal(
            "review_required",
            canonical.RootElement.GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "blocked",
            canonical.RootElement
                .GetProperty("publicTrustMetrics")
                .GetProperty("releaseChannel")
                .GetProperty("posture")
                .GetString());
        Assert.Equal(
            canonicalBefore,
            service.LoadGenerationCanonicalManifestBytes(snapshot));
        Assert.Equal(
            compatibilityBefore,
            service.LoadGenerationCompatibilityManifestBytes(snapshot));
    }

    [Fact]
    public void GenerationAurCatalogIsInventoryValidatedAndUrlBound()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a", includeAur: true);
        fixture.Activate("generation-a", "run-a");
        ReleaseShelfSnapshot snapshot = fixture.CreateStore().CaptureGeneration("generation-a");
        var service = new AurPackageCatalogService(fixture.Configuration, fixture.CreateStore());

        AurPackageEntry package = Assert.Single(service.LoadCatalog(snapshot).Packages);
        Assert.Equal(
            "/downloads/g/generation-a/files/chummer6-bin-aur-source.tar.gz",
            package.SourceArchiveUrl);
        Assert.Equal(
            "/downloads/g/generation-a/files/chummer6-bin.PKGBUILD",
            package.PkgbuildUrl);
        Assert.Equal(
            "/downloads/g/generation-a/files/chummer6-bin.SRCINFO",
            package.SrcinfoUrl);
        Assert.Equal(
            "/downloads/g/generation-a/files/chummer-test.bin",
            package.UpstreamArtifactUrl);

        string pkgbuild = Path.Combine(snapshot.PhysicalRoot, "files", "chummer6-bin.PKGBUILD");
        File.WriteAllText(pkgbuild, "tampered");
        Assert.Null(snapshot.OpenVerifiedFile("files/chummer6-bin.PKGBUILD"));
    }

    [Fact]
    public void CaptureGenerationRejectsAValidButNeverCommittedActivationCandidate()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.WriteGeneration("generation-b", "run-b", "artifact-b");
        fixture.Activate("generation-b", "run-b");
        var store = fixture.CreateStore();

        InvalidDataException exception = Assert.Throws<InvalidDataException>(
            () => store.CaptureGeneration("generation-a"));

        Assert.Contains("not bound to a committed activation receipt", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void CaptureGenerationRejectsPreparedAndAbortedHistoricalGenerations()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.WriteGeneration("generation-b", "run-b", "artifact-b");
        fixture.Activate("generation-a", "run-a");
        fixture.Activate("generation-b", "run-b");
        string outcomePath = Path.Combine(
            fixture.DownloadsRoot,
            ".release-shelf-activation-journal",
            "activation-generation-a",
            "outcome.json");
        string committedOutcome = File.ReadAllText(outcomePath);

        File.Delete(outcomePath);
        Assert.Throws<InvalidDataException>(
            () => fixture.CreateStore().CaptureGeneration("generation-a"));

        File.WriteAllText(
            outcomePath,
            committedOutcome.Replace(
                "\"state\": \"committed\"",
                "\"state\": \"aborted\"",
                StringComparison.Ordinal));
        Assert.Throws<InvalidDataException>(
            () => fixture.CreateStore().CaptureGeneration("generation-a"));
    }

    [Fact]
    public void CaptureGenerationRejectsNestedPointerBytesThatDisagreeWithJournalEnvelope()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.WriteGeneration("generation-b", "run-b", "artifact-b");
        fixture.Activate("generation-a", "run-a");
        fixture.Activate("generation-b", "run-b");
        string intentPath = Path.Combine(
            fixture.DownloadsRoot,
            ".release-shelf-activation-journal",
            "activation-generation-a",
            "intent.json");
        JsonObject journal = JsonNode.Parse(File.ReadAllText(intentPath))!.AsObject();
        journal["intent"]!.AsObject()["targetPointerBase64"] = Convert.ToBase64String("{}"u8.ToArray());
        File.WriteAllText(
            intentPath,
            journal.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));

        InvalidDataException exception = Assert.Throws<InvalidDataException>(
            () => fixture.CreateStore().CaptureGeneration("generation-a"));

        Assert.Contains("identity is invalid", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void CaptureGenerationRejectsRetainedManifestMutationAgainstCandidateBinding()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.WriteGeneration("generation-b", "run-b", "artifact-b");
        fixture.Activate("generation-a", "run-a");
        fixture.Activate("generation-b", "run-b");
        string retainedCanonical = Path.Combine(
            fixture.DownloadsRoot,
            "generations",
            "generation-a",
            ReleaseShelfGenerationStore.CanonicalManifestFileName);
        File.AppendAllText(retainedCanonical, " ");

        Assert.Throws<InvalidDataException>(
            () => fixture.CreateStore().CaptureGeneration("generation-a"));
    }

    [Fact]
    public void ExplicitGenerationManifestNeverReadsMutableRemoteRegistryTruth()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.WriteGeneration("generation-b", "run-b", "artifact-b");
        fixture.Activate("generation-a", "run-a");
        fixture.Activate("generation-b", "run-b");
        IConfiguration configuration = new ConfigurationBuilder()
            .AddConfiguration(fixture.Configuration)
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = "https://registry.invalid/current"
            })
            .Build();
        var handler = new CountingJsonHandler(
            "{\"version\":\"mutable-remote\",\"channel\":\"preview\",\"artifacts\":[]}");
        var service = new PublicReleaseManifestService(
            configuration,
            new HttpClient(handler),
            TimeProvider.System);
        ReleaseShelfSnapshot retained = service.CaptureShelfGeneration("generation-a");

        var manifest = service.LoadManifest(retained);

        Assert.Equal("run-a", manifest.Version);
        Assert.Equal(0, handler.CallCount);
    }

    [Fact]
    public void CurrentGenerationManifestNeverOverlaysSameIdentityMutableRemoteArtifactTruth()
    {
        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-a", "run-a", "artifact-a");
        fixture.Activate("generation-a", "run-a");
        IConfiguration configuration = new ConfigurationBuilder()
            .AddConfiguration(fixture.Configuration)
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = "https://registry.invalid/current"
            })
            .Build();
        var handler = new CountingJsonHandler(
            """
            {"version":"run-a","channelId":"preview","publishedAt":"2026-07-15T12:00:00Z","artifacts":[{"artifactId":"test-installer","fileName":"relaxed.bin","downloadUrl":"/downloads/g/generation-a/files/relaxed.bin","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","sizeBytes":1,"installAccessClass":"account_required"}]}
            """);
        var store = new ReleaseShelfGenerationStore(configuration);
        var service = new PublicReleaseManifestService(
            configuration,
            new HttpClient(handler),
            TimeProvider.System);

        PublicReleaseManifestDto manifest = service.LoadManifest(store.Capture());
        PublicReleaseArtifactDto artifact = Assert.Single(manifest.Downloads);

        Assert.Equal(0, handler.CallCount);
        Assert.Equal("chummer-test.bin", artifact.FileName);
        Assert.Equal("open_public", artifact.InstallAccessClass);
        Assert.Equal("/downloads/g/generation-a/files/chummer-test.bin", artifact.Url);
        Assert.NotEqual(new string('a', 64), artifact.Sha256);
    }

    [Fact]
    public void CaptureGenerationRejectsASymlinkedInactiveGenerationBeforeOpeningItsCandidate()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using var fixture = new ReleaseShelfFixture();
        fixture.WriteGeneration("generation-current", "run-current", "artifact-current");
        fixture.Activate("generation-current", "run-current");
        string outside = Path.Combine(Path.GetTempPath(), $"release-shelf-outside-{Guid.NewGuid():N}");
        Directory.CreateDirectory(outside);
        try
        {
            File.WriteAllText(Path.Combine(outside, "activation-candidate.json"), "{}");
            Directory.CreateSymbolicLink(
                Path.Combine(fixture.DownloadsRoot, "generations", "generation-linked"),
                outside);

            Assert.Throws<InvalidDataException>(
                () => fixture.CreateStore().CaptureGeneration("generation-linked"));
        }
        finally
        {
            Directory.Delete(outside, recursive: true);
        }
    }

    [Fact]
    public async Task HttpRequestUsesOneSnapshotForManifestArtifactAndEvidenceReads()
    {
        await using var fixture = new ReleaseShelfHttpFixture();
        await fixture.StartAsync();
        using HttpClient client = fixture.CreateClient();

        using HttpResponseMessage firstResponse = await client.GetAsync("/snapshot-and-activate");
        firstResponse.EnsureSuccessStatusCode();
        using JsonDocument first = JsonDocument.Parse(await firstResponse.Content.ReadAsStringAsync());
        Assert.Equal("generation-a", first.RootElement.GetProperty("generationId").GetString());
        Assert.Equal("run-a", first.RootElement.GetProperty("version").GetString());
        Assert.Equal("artifact-a", first.RootElement.GetProperty("artifactBytes").GetString());
        Assert.Equal("evidence-a", first.RootElement.GetProperty("evidence").GetString());

        using HttpResponseMessage secondResponse = await client.GetAsync("/current");
        secondResponse.EnsureSuccessStatusCode();
        using JsonDocument second = JsonDocument.Parse(await secondResponse.Content.ReadAsStringAsync());
        Assert.Equal("generation-b", second.RootElement.GetProperty("generationId").GetString());
        Assert.Equal("run-b", second.RootElement.GetProperty("version").GetString());
        Assert.Equal("artifact-b", second.RootElement.GetProperty("artifactBytes").GetString());
    }

    private sealed class ReleaseShelfHttpFixture : IAsyncDisposable
    {
        private readonly ReleaseShelfFixture _shelf = new();
        private WebApplication? _app;

        public async Task StartAsync()
        {
            _shelf.WriteGeneration("generation-a", "run-a", "artifact-a", "evidence-a");
            _shelf.WriteGeneration("generation-b", "run-b", "artifact-b", "evidence-b");
            _shelf.Activate("generation-a", "run-a");

            WebApplicationBuilder builder = WebApplication.CreateBuilder();
            builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0));
            builder.Configuration.AddConfiguration(_shelf.Configuration);
            builder.Services.AddHttpContextAccessor();
            builder.Services.AddSingleton<ReleaseShelfGenerationStore>();
            builder.Services.AddSingleton(static provider => new PublicReleaseManifestService(
                provider.GetRequiredService<IConfiguration>(),
                provider.GetRequiredService<ReleaseShelfGenerationStore>()));

            _app = builder.Build();
            _app.MapGet("/snapshot-and-activate", (PublicReleaseManifestService releases) =>
            {
                ReleaseShelfSnapshot snapshot = releases.CaptureShelfSnapshot();
                var manifest = releases.LoadManifest(snapshot);
                _shelf.Activate("generation-b", "run-b");
                using ReleaseShelfVerifiedFile artifact = snapshot.OpenVerifiedFile("files/chummer-test.bin")
                    ?? throw new InvalidDataException("captured artifact disappeared");
                using ReleaseShelfVerifiedFile evidence = snapshot.OpenVerifiedFile("release-evidence/public-promotion.json")
                    ?? throw new InvalidDataException("captured evidence disappeared");
                using var artifactReader = new StreamReader(artifact.Stream, Encoding.UTF8);
                using JsonDocument evidenceDocument = JsonDocument.Parse(evidence.Stream);
                return Results.Json(new
                {
                    snapshot.GenerationId,
                    manifest.Version,
                    ArtifactBytes = artifactReader.ReadToEnd(),
                    Evidence = evidenceDocument.RootElement.GetProperty("value").GetString()
                });
            });
            _app.MapGet("/current", (PublicReleaseManifestService releases) =>
            {
                ReleaseShelfSnapshot snapshot = releases.CaptureShelfSnapshot();
                var manifest = releases.LoadManifest(snapshot);
                using ReleaseShelfVerifiedFile artifact = snapshot.OpenVerifiedFile("files/chummer-test.bin")
                    ?? throw new InvalidDataException("current artifact disappeared");
                using var artifactReader = new StreamReader(artifact.Stream, Encoding.UTF8);
                return Results.Json(new
                {
                    snapshot.GenerationId,
                    manifest.Version,
                    ArtifactBytes = artifactReader.ReadToEnd()
                });
            });
            await _app.StartAsync();
        }

        public HttpClient CreateClient()
        {
            IServer server = (_app ?? throw new InvalidOperationException()).Services.GetRequiredService<IServer>();
            IServerAddressesFeature addresses = server.Features.Get<IServerAddressesFeature>()
                ?? throw new InvalidOperationException("Kestrel did not publish its address.");
            return new HttpClient { BaseAddress = new Uri(addresses.Addresses.Single()) };
        }

        public async ValueTask DisposeAsync()
        {
            if (_app is not null)
            {
                await _app.StopAsync();
                await _app.DisposeAsync();
            }

            _shelf.Dispose();
        }
    }

    private sealed class CountingJsonHandler(string payload) : HttpMessageHandler
    {
        public int CallCount { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            CallCount++;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(payload, Encoding.UTF8, "application/json")
            });
        }
    }

    private static string ResolveSharedFixtureRoot()
    {
        string? cursor = Path.GetFullPath(Directory.GetCurrentDirectory());
        for (int depth = 0; depth < 8 && cursor is not null; depth++)
        {
            string candidate = Path.Combine(cursor, "tests", "fixtures", "atomic_release_shelf_v1");
            if (File.Exists(Path.Combine(candidate, "current.json")))
            {
                return candidate;
            }

            cursor = Directory.GetParent(cursor)?.FullName;
        }

        throw new DirectoryNotFoundException("Shared atomic release shelf fixture was not found.");
    }

    private static void CopyDirectory(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (string directory in Directory.EnumerateDirectories(source, "*", SearchOption.AllDirectories))
        {
            Directory.CreateDirectory(Path.Combine(destination, Path.GetRelativePath(source, directory)));
        }

        foreach (string file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            string target = Path.Combine(destination, Path.GetRelativePath(source, file));
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }

    private static string Sha256File(string path)
    {
        using FileStream stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }

    private static Dictionary<string, object?> BuildManifestBindings(
        string generationId,
        string canonicalSha256,
        string compatibilitySha256)
        => new()
        {
            ["canonical"] = new Dictionary<string, object?>
            {
                ["path"] = $"/downloads/g/{generationId}/RELEASE_CHANNEL.generated.json",
                ["sha256"] = canonicalSha256
            },
            ["compatibility"] = new Dictionary<string, object?>
            {
                ["path"] = $"/downloads/g/{generationId}/releases.json",
                ["sha256"] = compatibilitySha256
            }
        };

    private static void WriteCommittedActivationJournal(
        string downloadsRoot,
        byte[] targetPointerBytes,
        byte[]? previousPointerBytes)
    {
        using JsonDocument targetDocument = JsonDocument.Parse(targetPointerBytes);
        JsonElement target = targetDocument.RootElement;
        string receiptId = target.GetProperty("activationReceiptId").GetString()!;
        string generationId = target.GetProperty("generationId").GetString()!;
        string? previousGenerationId = null;
        if (previousPointerBytes is not null)
        {
            using JsonDocument previousDocument = JsonDocument.Parse(previousPointerBytes);
            previousGenerationId = previousDocument.RootElement.GetProperty("generationId").GetString();
        }

        DateTimeOffset publishedAt = DateTimeOffset.Parse(target.GetProperty("publishedAt").GetString()!).ToUniversalTime();
        DateTimeOffset activatedAt = DateTimeOffset.Parse(target.GetProperty("activatedAt").GetString()!).ToUniversalTime();
        string ShaBinding(byte[] bytes)
            => $"sha256:{Convert.ToHexStringLower(SHA256.HashData(bytes))}";
        var intent = new TestActivationIntent(
            Operation: "promotion",
            PreviousGenerationId: previousGenerationId,
            PreviousPointerSha256: previousPointerBytes is null ? null : ShaBinding(previousPointerBytes),
            GenerationId: generationId,
            ActivationReceiptId: receiptId,
            ReleaseVersion: target.GetProperty("releaseVersion").GetString()!,
            Channel: target.GetProperty("channel").GetString()!,
            PublishedAt: publishedAt,
            InventoryDigest: target.GetProperty("inventoryDigest").GetString()!,
            PointerSha256: ShaBinding(targetPointerBytes),
            PreparedAtUtc: activatedAt,
            PreviousPointerBase64: previousPointerBytes is null
                ? null
                : Convert.ToBase64String(previousPointerBytes),
            TargetPointerBase64: Convert.ToBase64String(targetPointerBytes));
        var journal = new TestActivationJournal(
            SchemaVersion: "chummer.release-shelf.activation-intent/v1",
            State: "prepared",
            Intent: intent,
            PreviousPointerBase64: previousPointerBytes is null
                ? null
                : Convert.ToBase64String(previousPointerBytes),
            TargetPointerBase64: Convert.ToBase64String(targetPointerBytes));
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = true,
            WriteIndented = true
        };
        string receiptRoot = Path.Combine(
            downloadsRoot,
            ".release-shelf-activation-journal",
            receiptId);
        Directory.CreateDirectory(receiptRoot);
        File.WriteAllBytes(
            Path.Combine(receiptRoot, "intent.json"),
            JsonSerializer.SerializeToUtf8Bytes(journal, options));
        string intentSha = $"sha256:{Convert.ToHexStringLower(SHA256.HashData(
            JsonSerializer.SerializeToUtf8Bytes(journal, options)))}";
        var outcome = new TestActivationOutcome(
            SchemaVersion: "chummer.release-shelf.activation-outcome/v1",
            State: "committed",
            ActivationReceiptId: receiptId,
            IntentSha256: intentSha,
            ResolvedAtUtc: activatedAt);
        File.WriteAllBytes(
            Path.Combine(receiptRoot, "outcome.json"),
            JsonSerializer.SerializeToUtf8Bytes(outcome, options));
    }

    private sealed record TestActivationJournal(
        string SchemaVersion,
        string State,
        TestActivationIntent Intent,
        string? PreviousPointerBase64,
        string TargetPointerBase64);

    private sealed record TestActivationIntent(
        string Operation,
        string? PreviousGenerationId,
        string? PreviousPointerSha256,
        string GenerationId,
        string ActivationReceiptId,
        string ReleaseVersion,
        string Channel,
        DateTimeOffset PublishedAt,
        string InventoryDigest,
        string PointerSha256,
        DateTimeOffset PreparedAtUtc,
        string? PreviousPointerBase64,
        string? TargetPointerBase64);

    private sealed record TestActivationOutcome(
        string SchemaVersion,
        string State,
        string ActivationReceiptId,
        string IntentSha256,
        DateTimeOffset ResolvedAtUtc);

    private sealed class ReleaseShelfFixture : IDisposable
    {
        public const string PublishedAt = "2026-07-15T12:00:00Z";
        private readonly string _root = Path.Combine(
            Path.GetTempPath(),
            "release-shelf-generation-store-tests",
            Guid.NewGuid().ToString("N"));
        private readonly Dictionary<string, GenerationMetadata> _generations = new(StringComparer.Ordinal);

        public ReleaseShelfFixture()
        {
            DownloadsRoot = Path.Combine(_root, "downloads");
            Directory.CreateDirectory(DownloadsRoot);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = DownloadsRoot,
                    ["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = string.Empty,
                    ["CHUMMER_HUB_REGISTRY_BASE_URL"] = string.Empty,
                    ["CHUMMER_PUBLIC_FLAGSHIP_READINESS_FILE"] = Path.Combine(_root, "missing-flagship.json"),
                    ["CHUMMER_PUBLIC_FINAL_GOLD_JANITOR_FILE"] = Path.Combine(_root, "missing-gold.json"),
                    ["CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE"] = Path.Combine(_root, "mutable-local-proof.json")
                })
                .Build();
        }

        public string DownloadsRoot { get; }
        public string PointerPath => Path.Combine(DownloadsRoot, ReleaseShelfGenerationStore.CurrentPointerFileName);
        public IConfiguration Configuration { get; }

        public ReleaseShelfGenerationStore CreateStore() => new(Configuration);

        public void WriteLayoutMarker()
            => File.WriteAllText(
                Path.Combine(DownloadsRoot, ReleaseShelfGenerationStore.LayoutMarkerFileName),
                "release-shelf-layout-v1\n");

        public void WriteGeneration(
            string generationId,
            string version,
            string artifactBytes,
            string evidence = "evidence",
            bool includeAur = false,
            string installAccessClass = "open_public",
            string? artifactDownloadUrlOverride = null,
            IReadOnlyDictionary<string, string>? extraFiles = null,
            IReadOnlyList<string>? topLevelProofRoutes = null,
            IReadOnlyList<string>? nestedProofRoutes = null,
            bool omitCanonicalGenerationId = false,
            bool omitCompatibilityGenerationId = false,
            string? canonicalGenerationIdOverride = null,
            string? compatibilityGenerationIdOverride = null)
        {
            string generationRoot = Path.Combine(DownloadsRoot, "generations", generationId);
            Directory.CreateDirectory(Path.Combine(generationRoot, "files"));
            Directory.CreateDirectory(Path.Combine(generationRoot, "release-evidence"));
            File.WriteAllText(Path.Combine(generationRoot, "files", "chummer-test.bin"), artifactBytes);
            File.WriteAllText(
                Path.Combine(generationRoot, "release-evidence", "public-promotion.json"),
                JsonSerializer.Serialize(new { value = evidence }));
            foreach ((string relativePath, string contents) in extraFiles
                         ?? new Dictionary<string, string>())
            {
                string path = Path.Combine(
                    generationRoot,
                    relativePath.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                File.WriteAllText(path, contents);
            }
            if (includeAur)
            {
                WriteAurCatalog(generationRoot, generationId);
            }
            byte[] artifact = Encoding.UTF8.GetBytes(artifactBytes);
            string artifactSha = Convert.ToHexStringLower(SHA256.HashData(artifact));
            string artifactDownloadUrl = artifactDownloadUrlOverride
                ?? (string.Equals(installAccessClass, "open_public", StringComparison.Ordinal)
                    ? $"/downloads/g/{generationId}/files/chummer-test.bin"
                    : $"/downloads/g/{generationId}/install/test-installer");
            var canonical = new Dictionary<string, object?>
            {
                ["generationId"] = generationId,
                ["product"] = "chummer",
                ["channelId"] = "preview",
                ["version"] = version,
                ["publishedAt"] = PublishedAt,
                ["status"] = "published",
                ["artifacts"] = new object[]
                {
                    new Dictionary<string, object?>
                    {
                        ["artifactId"] = "test-installer",
                        ["head"] = "avalonia",
                        ["platform"] = "linux",
                        ["rid"] = "linux-x64",
                        ["arch"] = "x64",
                        ["kind"] = "installer",
                        ["platformLabel"] = "Test installer",
                        ["fileName"] = "chummer-test.bin",
                        ["downloadUrl"] = artifactDownloadUrl,
                        ["sha256"] = artifactSha,
                        ["sizeBytes"] = artifact.Length,
                        ["installAccessClass"] = installAccessClass
                    }
                }
            };
            var compatibility = new Dictionary<string, object?>
            {
                ["generationId"] = generationId,
                ["version"] = version,
                ["channel"] = "preview",
                ["publishedAt"] = PublishedAt,
                ["status"] = "published",
                ["downloads"] = new object[]
                {
                    new Dictionary<string, object?>
                    {
                        ["id"] = "test-installer",
                        ["platform"] = "linux",
                        ["url"] = artifactDownloadUrl,
                        ["sha256"] = artifactSha,
                        ["sizeBytes"] = artifact.Length,
                        ["fileName"] = "chummer-test.bin",
                        ["installAccessClass"] = installAccessClass
                    }
                }
            };
            if (omitCanonicalGenerationId)
            {
                canonical.Remove("generationId");
            }
            else if (!string.IsNullOrWhiteSpace(canonicalGenerationIdOverride))
            {
                canonical["generationId"] = canonicalGenerationIdOverride;
            }

            if (omitCompatibilityGenerationId)
            {
                compatibility.Remove("generationId");
            }
            else if (!string.IsNullOrWhiteSpace(compatibilityGenerationIdOverride))
            {
                compatibility["generationId"] = compatibilityGenerationIdOverride;
            }
            if (topLevelProofRoutes is not null)
            {
                canonical["releaseProof"] = new Dictionary<string, object?>
                {
                    ["proofRoutes"] = topLevelProofRoutes
                };
                compatibility["releaseProof"] = new Dictionary<string, object?>
                {
                    ["proofRoutes"] = topLevelProofRoutes
                };
            }

            if (nestedProofRoutes is not null)
            {
                canonical["extension"] = new Dictionary<string, object?>
                {
                    ["releaseProof"] = new Dictionary<string, object?>
                    {
                        ["proofRoutes"] = nestedProofRoutes
                    }
                };
            }

            string canonicalPath = Path.Combine(generationRoot, ReleaseShelfGenerationStore.CanonicalManifestFileName);
            string compatibilityPath = Path.Combine(generationRoot, ReleaseShelfGenerationStore.CompatibilityManifestFileName);
            File.WriteAllText(canonicalPath, JsonSerializer.Serialize(canonical));
            File.WriteAllText(compatibilityPath, JsonSerializer.Serialize(compatibility));
            var metadata = new GenerationMetadata(
                version,
                Sha256(canonicalPath),
                Sha256(compatibilityPath),
                ReleaseShelfGenerationStore.ComputeInventoryDigest(generationRoot));
            _generations[generationId] = metadata;
            Dictionary<string, object?> activationCandidate = BuildPointer(
                generationId,
                version,
                metadata,
                canonicalShaOverride: null);
            activationCandidate["schemaVersion"] = "chummer.release-shelf.activation-candidate/v1";
            activationCandidate["contractName"] = "chummer.release-shelf-activation-candidate";
            activationCandidate["inventory"] = ReleaseShelfGenerationStore.BuildInventory(generationRoot);
            File.WriteAllText(
                Path.Combine(generationRoot, "activation-candidate.json"),
                JsonSerializer.Serialize(activationCandidate));
        }

        public void Activate(
            string generationId,
            string version,
            string? canonicalShaOverride = null)
        {
            byte[]? previousPointerBytes = File.Exists(PointerPath)
                ? File.ReadAllBytes(PointerPath)
                : null;
            WriteLayoutMarker();
            GenerationMetadata metadata = _generations[generationId];
            WritePointer(BuildPointer(generationId, version, metadata, canonicalShaOverride));
            WriteCommittedActivationJournal(
                DownloadsRoot,
                File.ReadAllBytes(PointerPath),
                previousPointerBytes);
        }

        public void AddExcludedMetadataToCandidateInventoryAndActivate(
            string generationId,
            string version,
            string relativePath)
        {
            string generationRoot = Path.Combine(DownloadsRoot, "generations", generationId);
            string metadataPath = Path.Combine(generationRoot, relativePath);
            var inventory = ReleaseShelfGenerationStore.BuildInventory(generationRoot).ToList();
            inventory.Add(new ReleaseShelfInventoryEntry(
                relativePath,
                Sha256(metadataPath),
                new FileInfo(metadataPath).Length));
            inventory = inventory.OrderBy(static row => row.Path, StringComparer.Ordinal).ToList();
            string inventoryDigest = ReleaseShelfGenerationStore.ComputeInventoryDigest(inventory);
            GenerationMetadata original = _generations[generationId];
            var rebound = new GenerationMetadata(
                original.Version,
                original.CanonicalSha256,
                original.CompatibilitySha256,
                inventoryDigest);
            Dictionary<string, object?> candidate = BuildPointer(
                generationId,
                version,
                rebound,
                canonicalShaOverride: null);
            candidate["schemaVersion"] = "chummer.release-shelf.activation-candidate/v1";
            candidate["contractName"] = "chummer.release-shelf-activation-candidate";
            candidate["inventory"] = inventory;
            File.WriteAllText(
                Path.Combine(generationRoot, "activation-candidate.json"),
                JsonSerializer.Serialize(candidate));
            WriteLayoutMarker();
            WritePointer(BuildPointer(generationId, version, rebound, canonicalShaOverride: null));
        }

        public void WritePointer(IReadOnlyDictionary<string, object?> pointer)
            => File.WriteAllText(PointerPath, JsonSerializer.Serialize(pointer));

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }

        private static string Sha256(string path)
        {
            using FileStream stream = File.OpenRead(path);
            return Convert.ToHexStringLower(SHA256.HashData(stream));
        }

        private static void WriteAurCatalog(string generationRoot, string generationId)
        {
            string filesRoot = Path.Combine(generationRoot, "files");
            string sourceArchivePath = Path.Combine(filesRoot, "chummer6-bin-aur-source.tar.gz");
            string pkgbuildPath = Path.Combine(filesRoot, "chummer6-bin.PKGBUILD");
            string srcinfoPath = Path.Combine(filesRoot, "chummer6-bin.SRCINFO");
            File.WriteAllText(sourceArchivePath, "aur-source");
            File.WriteAllText(pkgbuildPath, "pkgbuild");
            File.WriteAllText(srcinfoPath, "srcinfo");
            string upstreamPath = Path.Combine(filesRoot, "chummer-test.bin");
            string legacyPrefix = "https://chummer.run/downloads/files/";
            File.WriteAllText(
                Path.Combine(generationRoot, "aur-packages.json"),
                JsonSerializer.Serialize(new
                {
                    generationId,
                    packages = new[]
                    {
                        new
                        {
                            id = "chummer6-bin",
                            packageName = "chummer6-bin",
                            packageVersion = "20260715.120000",
                            title = "Arch / CachyOS",
                            summary = "Generation-bound AUR package.",
                            platformLabel = "Arch / CachyOS",
                            installCommand = "makepkg -si",
                            sourceArchiveFileName = Path.GetFileName(sourceArchivePath),
                            sourceArchiveUrl = legacyPrefix + Path.GetFileName(sourceArchivePath),
                            sourceArchiveSha256 = Sha256(sourceArchivePath),
                            sourceArchiveSizeBytes = new FileInfo(sourceArchivePath).Length,
                            pkgbuildFileName = Path.GetFileName(pkgbuildPath),
                            pkgbuildUrl = legacyPrefix + Path.GetFileName(pkgbuildPath),
                            pkgbuildSha256 = Sha256(pkgbuildPath),
                            srcinfoFileName = Path.GetFileName(srcinfoPath),
                            srcinfoUrl = legacyPrefix + Path.GetFileName(srcinfoPath),
                            srcinfoSha256 = Sha256(srcinfoPath),
                            upstreamArtifactId = "test-installer",
                            upstreamArtifactFileName = Path.GetFileName(upstreamPath),
                            upstreamArtifactUrl = legacyPrefix + Path.GetFileName(upstreamPath),
                            upstreamArtifactSha256 = Sha256(upstreamPath),
                            upstreamArtifactSizeBytes = new FileInfo(upstreamPath).Length
                        }
                    }
                }));
        }

        private static Dictionary<string, object?> BuildPointer(
            string generationId,
            string version,
            GenerationMetadata metadata,
            string? canonicalShaOverride)
            => new()
            {
                ["schemaVersion"] = "chummer.release-shelf.current/v1",
                ["generationId"] = generationId,
                ["releaseVersion"] = version,
                ["channel"] = "preview",
                ["publishedAt"] = PublishedAt,
                ["manifests"] = BuildManifestBindings(
                    generationId,
                    canonicalShaOverride ?? metadata.CanonicalSha256,
                    metadata.CompatibilitySha256),
                ["inventoryDigest"] = $"sha256:{metadata.InventoryDigest}",
                ["activatedAt"] = PublishedAt,
                ["activationReceiptId"] = $"activation-{generationId}"
            };

        private sealed record GenerationMetadata(
            string Version,
            string CanonicalSha256,
            string CompatibilitySha256,
            string InventoryDigest);
    }
}
