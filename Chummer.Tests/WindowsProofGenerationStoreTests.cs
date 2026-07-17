using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services.WindowsProof;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class WindowsProofGenerationStoreTests
{
    [Fact]
    public async Task PreparedGenerationIsNotDeliverableUntilAtomicActivationCommits()
    {
        using var fixture = new Fixture();
        SourceBundle source = fixture.CreateSource("run-proof-0001", "installer-one");

        WindowsProofPreparedGeneration prepared = await fixture.Store.PrepareAsync(
            new WindowsProofPrepareRequest("prepare-0001", source.Root, source.ManifestSha256));

        Assert.StartsWith("sha256-", prepared.GenerationId, StringComparison.Ordinal);
        Assert.Null(fixture.Store.CaptureCurrent());
        Assert.Null(fixture.Store.CaptureGeneration(prepared.GenerationId));
        Assert.Null(fixture.Store.CaptureCandidate(prepared.CandidateVersion));

        WindowsProofActivationReceipt activation = await fixture.Store.ActivateAsync(
            new WindowsProofActivationRequest(
                "activate-0001",
                prepared.GenerationId,
                prepared.InventoryDigest,
                ExpectedCurrentGenerationId: null));

        WindowsProofGenerationSnapshot current = Assert.IsType<WindowsProofGenerationSnapshot>(
            fixture.Store.CaptureCurrent());
        WindowsProofGenerationSnapshot retained = Assert.IsType<WindowsProofGenerationSnapshot>(
            fixture.Store.CaptureCandidate("run-proof-0001"));
        Assert.Equal(activation.ActivatedAt, current.ActivatedAt);
        Assert.Equal(prepared.GenerationId, retained.GenerationId);
        WindowsProofInventoryEntry installer = Assert.Single(
            current.Inventory,
            row => row.Kind == WindowsProofArtifactKind.Installer);
        using Stream stream = current.OpenVerifiedArtifact(installer);
        using var reader = new StreamReader(stream, Encoding.UTF8);
        string installerBytes = reader.ReadToEnd();
        Assert.StartsWith("installer-one\nCHUMMER6_BOOTSTRAP_METADATA\n", installerBytes, StringComparison.Ordinal);
        Assert.EndsWith("payloadAcquisitionMode=embedded\n", installerBytes, StringComparison.Ordinal);

        Assert.Equal("canonical-sentinel", File.ReadAllText(fixture.CanonicalSentinel));
        Assert.False(File.Exists(Path.Combine(fixture.CanonicalRoot, "current.json")));
    }

    [Fact]
    public async Task PrepareIsIdempotentOnlyForTheSameRequestAndManifestDigest()
    {
        using var fixture = new Fixture();
        SourceBundle source = fixture.CreateSource("run-proof-0002", "installer-two");
        var request = new WindowsProofPrepareRequest(
            "prepare-0002",
            source.Root,
            source.ManifestSha256);

        WindowsProofPreparedGeneration first = await fixture.Store.PrepareAsync(request);
        WindowsProofPreparedGeneration second = await fixture.Store.PrepareAsync(request);

        Assert.Equal(first, second);
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Store.PrepareAsync(
            request with { ExpectedManifestSha256 = new string('0', 64) }));
    }

    [Fact]
    public async Task CandidateVersionCannotBeReboundToDifferentBytes()
    {
        using var fixture = new Fixture();
        SourceBundle first = fixture.CreateSource("run-proof-0003", "installer-three-a");
        SourceBundle second = fixture.CreateSource("run-proof-0003", "installer-three-b");
        await fixture.Store.PrepareAsync(
            new WindowsProofPrepareRequest("prepare-0003a", first.Root, first.ManifestSha256));

        InvalidDataException error = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.Store.PrepareAsync(
                new WindowsProofPrepareRequest("prepare-0003b", second.Root, second.ManifestSha256)));

        Assert.Contains("already bound", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task ActivationRejectsReplayAndCompareAndSwapMismatch()
    {
        using var fixture = new Fixture();
        SourceBundle source = fixture.CreateSource("run-proof-0004", "installer-four");
        WindowsProofPreparedGeneration prepared = await fixture.Store.PrepareAsync(
            new WindowsProofPrepareRequest("prepare-0004", source.Root, source.ManifestSha256));
        var activation = new WindowsProofActivationRequest(
            "activate-0004",
            prepared.GenerationId,
            prepared.InventoryDigest,
            ExpectedCurrentGenerationId: null);

        WindowsProofActivationReceipt first = await fixture.Store.ActivateAsync(activation);
        WindowsProofActivationReceipt retry = await fixture.Store.ActivateAsync(activation);
        Assert.Equal(first, retry);
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Store.ActivateAsync(
            activation with { InventoryDigest = new string('0', 64) }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.Store.ActivateAsync(
            activation with { RequestId = "activate-0004-replay" }));
    }

    [Fact]
    public async Task CaptureAndOpenFailClosedAfterGenerationTamperOrRevocationChange()
    {
        using var fixture = new Fixture();
        SourceBundle source = fixture.CreateSource("run-proof-0005", "installer-five");
        WindowsProofPreparedGeneration prepared = await fixture.Store.PrepareAsync(
            new WindowsProofPrepareRequest("prepare-0005", source.Root, source.ManifestSha256));
        await fixture.Store.ActivateAsync(new WindowsProofActivationRequest(
            "activate-0005",
            prepared.GenerationId,
            prepared.InventoryDigest,
            ExpectedCurrentGenerationId: null));
        WindowsProofGenerationSnapshot snapshot = Assert.IsType<WindowsProofGenerationSnapshot>(
            fixture.Store.CaptureCurrent());
        WindowsProofInventoryEntry installer = Assert.Single(
            snapshot.Inventory,
            row => row.Kind == WindowsProofArtifactKind.Installer);

        File.WriteAllText(
            Path.Combine(fixture.StoreRoot, "delivery-state.json"),
            JsonSerializer.Serialize(new
            {
                schemaVersion = "chummer.windows-proof.delivery-state/v1",
                revoked = true,
                revocationGeneration = 1,
                reason = "operator_test",
                updatedAt = DateTimeOffset.UtcNow
            }));
        Assert.Throws<InvalidOperationException>(() => snapshot.OpenVerifiedArtifact(installer));

        File.WriteAllText(
            Path.Combine(fixture.StoreRoot, "delivery-state.json"),
            JsonSerializer.Serialize(new
            {
                schemaVersion = "chummer.windows-proof.delivery-state/v1",
                revoked = false,
                revocationGeneration = 2,
                reason = (string?)null,
                updatedAt = DateTimeOffset.UtcNow
            }));
        string installerPath = Path.Combine(
            fixture.StoreRoot,
            "generations",
            prepared.GenerationId,
            installer.RelativePath.Replace('/', Path.DirectorySeparatorChar));
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(installerPath, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        }
        else
        {
            File.SetAttributes(installerPath, FileAttributes.Normal);
        }

        File.AppendAllText(installerPath, "tampered");
        Assert.Throws<InvalidDataException>(() => fixture.Store.CaptureCurrent());
    }

    [Fact]
    public async Task PrepareRejectsOptimisticPostureAndSourceSymlinks()
    {
        using var fixture = new Fixture();
        SourceBundle source = fixture.CreateSource("run-proof-0006", "installer-six");
        string manifestPath = Path.Combine(
            source.Root,
            WindowsProofManifestValidator.ManifestFileName);
        string optimistic = File.ReadAllText(manifestPath)
            .Replace("review_required", "preview_supported", StringComparison.Ordinal);
        File.WriteAllText(manifestPath, optimistic);
        string optimisticDigest = Sha256(manifestPath);

        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Store.PrepareAsync(
            new WindowsProofPrepareRequest("prepare-0006", source.Root, optimisticDigest)));

        if (OperatingSystem.IsLinux() || OperatingSystem.IsFreeBSD())
        {
            SourceBundle linked = fixture.CreateSource("run-proof-0007", "installer-seven");
            File.CreateSymbolicLink(
                Path.Combine(linked.Root, "proof", "case-link.json"),
                Path.Combine(linked.Root, "proof", "windows-visual-handoff.json"));
            await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Store.PrepareAsync(
                new WindowsProofPrepareRequest("prepare-0007", linked.Root, linked.ManifestSha256)));
        }
    }

    [Fact]
    public async Task PrepareRejectsNonEmbeddedPayloadAcquisitionMode()
    {
        using var fixture = new Fixture();
        SourceBundle source = fixture.CreateSource("run-proof-download-mode", "installer-download-mode");
        string manifestPath = Path.Combine(
            source.Root,
            WindowsProofManifestValidator.ManifestFileName);
        string original = File.ReadAllText(manifestPath);
        string legacyDownloadMode = original.Replace(
            "\"payloadAcquisitionMode\":\"embedded\"",
            "\"payloadAcquisitionMode\":\"download\"",
            StringComparison.Ordinal);
        Assert.NotEqual(original, legacyDownloadMode);
        File.WriteAllText(manifestPath, legacyDownloadMode);

        InvalidDataException error = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.Store.PrepareAsync(new WindowsProofPrepareRequest(
                "prepare-download-mode",
                source.Root,
                Sha256(manifestPath))));

        Assert.Contains("payloadAcquisitionMode=embedded", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task PrepareRejectsInstallerWithoutEmbeddedMetadataTrailer()
    {
        using var fixture = new Fixture();
        SourceBundle source = fixture.CreateSource(
            "run-proof-no-embedded-trailer",
            "installer-no-embedded-trailer",
            includeEmbeddedInstallerMetadata: false);

        InvalidDataException error = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.Store.PrepareAsync(new WindowsProofPrepareRequest(
                "prepare-no-embedded-trailer",
                source.Root,
                source.ManifestSha256)));

        Assert.Contains("embedded-payload metadata trailer", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task PrepareAcceptsCleanPublicKeyPemBootstrapEntry()
    {
        Assert.Equal(
            "chummer6.windows-bootstrap-zip-admission.v1",
            WindowsProofManifestValidator.BootstrapPayloadPolicyVersion);
        using var fixture = new Fixture();
        SourceBundle source = fixture.CreateSource(
            "run-proof-public-pem",
            "installer-public-pem",
            payloadWriter: archive =>
            {
                WriteZipEntry(archive, "app/Chummer.Avalonia.exe", "payload");
                WriteZipEntry(
                    archive,
                    "app/public-key.pem",
                    "-----BEGIN PUBLIC KEY-----\nPUBLIC-MATERIAL\n-----END PUBLIC KEY-----\n");
                WriteZipEntry(
                    archive,
                    "app/empty-sensitive-values.json",
                    """{"client_secret":"","authorization":null,"ConnectionStrings":{}}""");
            });

        WindowsProofPreparedGeneration prepared = await fixture.Store.PrepareAsync(
            new WindowsProofPrepareRequest(
                "prepare-public-pem",
                source.Root,
                source.ManifestSha256));

        Assert.Equal("run-proof-public-pem", prepared.CandidateVersion);
    }

    [Fact]
    public async Task PrepareRejectsUnsafeBootstrapPayloadArchivesWithoutLeakingValues()
    {
        const string canary = "WINDOWS_PROOF_SECRET_CANARY_64f76aa9";
        string rsaPrivateKeyMarker = string.Concat("-----BEGIN RSA ", "PRIVATE KEY-----");
        string encryptedPrivateKeyMarker = string.Concat("-----BEGIN ENCRYPTED ", "PRIVATE KEY-----");
        string pgpPrivateKeyMarker = string.Concat("-----BEGIN PGP ", "PRIVATE KEY BLOCK-----");
        using var fixture = new Fixture();
        var cases = new (string Name, Action<ZipArchive>? Writer, Action<string>? Mutator, string Rule)[]
        {
            (
                "invalid-zip",
                null,
                path => File.WriteAllBytes(path, Encoding.UTF8.GetBytes("not a ZIP " + canary)),
                "rule=archive.format"),
            ("traversal", archive => WriteZipEntry(archive, "../escape.txt", "safe"), null, "rule=path.relative"),
            ("absolute", archive => WriteZipEntry(archive, "/escape.txt", "safe"), null, "rule=path.relative"),
            ("drive-absolute", archive => WriteZipEntry(archive, "C:/escape.txt", "safe"), null, "rule=path.relative"),
            ("ads", archive => WriteZipEntry(archive, "app/file.txt:stream", "safe"), null, "rule=path.windows_invalid_segment"),
            ("control", archive => WriteZipEntry(archive, "app/bad\u0001name.txt", "safe"), null, "rule=path.ascii_printable"),
            ("wildcard", archive => WriteZipEntry(archive, "app/bad?.txt", "safe"), null, "rule=path.windows_invalid_segment"),
            ("trailing-dot", archive => WriteZipEntry(archive, "app/name.", "safe"), null, "rule=path.windows_invalid_segment"),
            ("trailing-space", archive => WriteZipEntry(archive, "app/name ", "safe"), null, "rule=path.windows_invalid_segment"),
            ("reserved-con", archive => WriteZipEntry(archive, "app/CON.txt", "safe"), null, "rule=path.windows_reserved_device"),
            ("reserved-lpt", archive => WriteZipEntry(archive, "app/lpt9.log", "safe"), null, "rule=path.windows_reserved_device"),
            (
                "duplicate",
                archive =>
                {
                    WriteZipEntry(archive, "app/config.txt", "one");
                    WriteZipEntry(archive, "app/config.txt", "two");
                },
                null,
                "rule=path.duplicate"),
            (
                "case-collision",
                archive =>
                {
                    WriteZipEntry(archive, "app/config.txt", "one");
                    WriteZipEntry(archive, "APP/CONFIG.TXT", "two");
                },
                null,
                "rule=path.portable_collision"),
            (
                "non-ascii-name",
                archive => WriteZipEntry(archive, "app/café.txt", "one"),
                null,
                "rule=path.ascii_printable"),
            (
                "symlink",
                archive =>
                {
                    ZipArchiveEntry entry = archive.CreateEntry("app/link");
                    entry.ExternalAttributes = unchecked((int)0xA1FF0000);
                    using var writer = new StreamWriter(entry.Open(), Encoding.UTF8);
                    writer.Write("target");
                },
                null,
                "rule=entry.symlink"),
            ("encrypted", archive => WriteZipEntry(archive, "app/config.txt", "safe"), MarkFirstZipEntryEncrypted, "rule=entry.encrypted"),
            (
                "corrupt-stored",
                archive => WriteZipEntry(
                    archive,
                    "app/corrupt.bin",
                    "stored-content",
                    CompressionLevel.NoCompression),
                CorruptFirstStoredEntry,
                "rule=entry.crc32"),
            ("dotenv", archive => WriteZipEntry(archive, "app/.env.production", canary), null, "rule=name.sensitive"),
            ("key-container-redacted-name", archive => WriteZipEntry(archive, $"app/{canary}.p12", "safe"), null, "rule=name.sensitive"),
            ("service-account-name", archive => WriteZipEntry(archive, "app/service-account.json", canary), null, "rule=name.sensitive"),
            ("classic-private-key", archive => WriteZipEntry(archive, "app/note.txt", $"{rsaPrivateKeyMarker}\n{canary}"), null, "rule=content.private_key_marker"),
            ("encrypted-private-key", archive => WriteZipEntry(archive, "app/note.txt", $"{encryptedPrivateKeyMarker}\n{canary}"), null, "rule=content.private_key_marker"),
            ("pgp-private-key", archive => WriteZipEntry(archive, "app/note.txt", $"{pgpPrivateKeyMarker}\n{canary}"), null, "rule=content.private_key_marker"),
            ("bearer", archive => WriteZipEntry(archive, "app/config.txt", $"Authorization: Bearer {canary}"), null, "rule=content.bearer_assignment"),
            ("refresh-token", archive => WriteZipEntry(archive, "app/config.txt", $"refresh_token={canary}"), null, "rule=content.credential_assignment"),
            ("access-token", archive => WriteZipEntry(archive, "app/config.txt", $"access_token={canary}"), null, "rule=content.credential_assignment"),
            ("short-client-secret", archive => WriteZipEntry(archive, "app/config.txt", "client_secret=x"), null, "rule=content.credential_assignment"),
            ("symbolic-client-secret", archive => WriteZipEntry(archive, "app/config.txt", "client_secret=${CLIENT_SECRET}"), null, "rule=content.credential_assignment"),
            (
                "binary-client-secret",
                archive => WriteZipEntry(
                    archive,
                    "app/native.dll",
                    "MZ\0\u0001client_secret=" + canary + "\0ÿ\u0010"),
                null,
                "rule=content.credential_assignment"),
            ("connection-string", archive => WriteZipEntry(archive, "app/config.txt", $"connection_string=Server=localhost;Password={canary}"), null, "rule=content.connection_string_assignment"),
            (
                "service-account-structure",
                archive => WriteZipEntry(
                    archive,
                    "app/data.dat",
                    JsonSerializer.Serialize(new
                    {
                        type = "service_account",
                        project_id = "project",
                        private_key_id = string.Empty,
                        private_key = string.Empty,
                        client_email = "test@example.invalid",
                        token_uri = "https://oauth2.googleapis.com/token"
                    })),
                null,
                "rule=content.google_service_account_json"),
            (
                "nested-sensitive-json-key",
                archive => WriteZipEntry(
                    archive,
                    "app/innocent.json",
                    """{"outer":[{"client.secret":{"source":"provider"}}]}"""),
                null,
                "rule=content.sensitive_json_value")
        };

        for (int index = 0; index < cases.Length; index++)
        {
            (string name, Action<ZipArchive>? writer, Action<string>? mutator, string rule) = cases[index];
            SourceBundle source = fixture.CreateSource(
                $"run-proof-unsafe-{index:D2}",
                $"installer-unsafe-{index:D2}",
                payloadWriter: writer,
                payloadMutator: mutator);

            Exception? observed = await Record.ExceptionAsync(
                () => fixture.Store.PrepareAsync(new WindowsProofPrepareRequest(
                    $"prepare-unsafe-{index:D2}",
                    source.Root,
                    source.ManifestSha256)));
            Assert.True(
                observed is InvalidDataException,
                $"Unsafe ZIP case '{name}' was not rejected as InvalidDataException; observed: {observed?.GetType().Name ?? "none"}.");
            var error = (InvalidDataException)observed!;

            Assert.Contains(rule, error.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Contains(
                $"policy={WindowsProofManifestValidator.BootstrapPayloadPolicyVersion}",
                error.Message,
                StringComparison.Ordinal);
            if (name != "invalid-zip")
            {
                Assert.Contains("entry_ordinal=", error.Message, StringComparison.Ordinal);
                Assert.Contains("entry_name_sha256=", error.Message, StringComparison.Ordinal);
            }
            Assert.DoesNotContain(canary, error.Message, StringComparison.Ordinal);
            Assert.Contains("chummer-avalonia-win-x64-payload.zip", error.Message, StringComparison.Ordinal);
        }
    }

    [Fact]
    public void BootstrapPayloadPolicyEnforcesEveryResourceBound()
    {
        using var fixture = new Fixture();
        var cases = new (
            string Name,
            Action<ZipArchive> Writer,
            WindowsProofManifestValidator.BootstrapPayloadPolicy Policy,
            string Rule)[]
        {
            (
                "archive",
                archive => WriteZipEntry(archive, "app/a.txt", "safe"),
                new(1, 8, 1024, 4096, 100, 1024, 1024),
                "rule=archive.size"),
            (
                "entries",
                archive =>
                {
                    WriteZipEntry(archive, "app/a.txt", "a");
                    WriteZipEntry(archive, "app/b.txt", "b");
                },
                new(1024 * 1024, 1, 1024, 4096, 100, 1024, 1024),
                "rule=archive.entry_count"),
            (
                "entry-size",
                archive => WriteZipEntry(archive, "app/a.txt", "12345"),
                new(1024 * 1024, 8, 4, 4096, 100, 1024, 1024),
                "rule=entry.decompressed_size"),
            (
                "total-size",
                archive =>
                {
                    WriteZipEntry(archive, "app/a.txt", "1234");
                    WriteZipEntry(archive, "app/b.txt", "5678");
                },
                new(1024 * 1024, 8, 1024, 7, 100, 1024, 1024),
                "rule=archive.decompressed_size"),
            (
                "ratio",
                archive => WriteZipEntry(archive, "app/a.txt", new string('A', 4096)),
                new(1024 * 1024, 8, 8192, 8192, 1, 8192, 8192),
                "rule=entry.compression_ratio"),
            (
                "central-directory",
                archive => WriteZipEntry(archive, "app/a.txt", "safe"),
                new(1024 * 1024, 8, 1024, 4096, 100, 1, 1024),
                "rule=archive.central_directory_size"),
            (
                "inspectable-text",
                archive => WriteZipEntry(archive, "app/a.txt", "abcdef"),
                new(1024 * 1024, 8, 1024, 4096, 100, 1024, 4),
                "rule=content.text_inspection_size"),
            (
                "inspectable-json",
                archive => WriteZipEntry(archive, "app/a.json", """{"a":"b"}"""),
                new(1024 * 1024, 8, 1024, 4096, 100, 1024, 4),
                "rule=content.json_inspection_size")
        };

        foreach ((string name, Action<ZipArchive> writer, WindowsProofManifestValidator.BootstrapPayloadPolicy policy, string rule) in cases)
        {
            string path = Path.Combine(fixture.Root, $"bound-{name}.zip");
            WritePayloadArchive(path, writer);

            InvalidDataException error = Assert.Throws<InvalidDataException>(
                () => WindowsProofManifestValidator.ValidateBootstrapPayloadArchive(
                    path,
                    $"files/{name}.zip",
                    policy));

            Assert.Contains(rule, error.Message, StringComparison.Ordinal);
            Assert.Contains(
                WindowsProofManifestValidator.BootstrapPayloadPolicyVersion,
                error.Message,
                StringComparison.Ordinal);
        }
    }

    [Fact]
    public void BootstrapPayloadPolicyStreamsKnownBinaryPastInspectionLimit()
    {
        using var fixture = new Fixture();
        string path = Path.Combine(fixture.Root, "streamed-known-binary.zip");
        WritePayloadArchive(
            path,
            archive => WriteZipEntry(
                archive,
                "app/native.dll",
                "MZ\0\u0001ÿ\u0010",
                CompressionLevel.NoCompression));
        var policy = new WindowsProofManifestValidator.BootstrapPayloadPolicy(
            1024 * 1024,
            8,
            1024,
            4096,
            100,
            1024,
            4);

        WindowsProofManifestValidator.ValidateBootstrapPayloadArchive(
            path,
            "files/streamed-known-binary.zip",
            policy);
    }

    [Fact]
    public async Task NewAdmissionRejectsLegacyV1AndIncompleteProvenanceSets()
    {
        using var fixture = new Fixture();
        SourceBundle legacy = fixture.CreateSource("run-proof-legacy", "installer-legacy");
        string legacyManifest = Path.Combine(
            legacy.Root,
            WindowsProofManifestValidator.ManifestFileName);
        File.WriteAllText(
            legacyManifest,
            File.ReadAllText(legacyManifest).Replace(
                WindowsProofManifestValidator.ManifestSchemaVersion,
                WindowsProofManifestValidator.LegacyManifestSchemaVersion,
                StringComparison.Ordinal));
        await Assert.ThrowsAsync<InvalidDataException>(() => fixture.Store.PrepareAsync(
            new WindowsProofPrepareRequest(
                "prepare-legacy",
                legacy.Root,
                Sha256(legacyManifest))));

        SourceBundle missingMaterial = fixture.CreateSource(
            "run-proof-missing-material",
            "installer-missing-material",
            omitSourceMaterial: true);
        InvalidDataException materialError = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.Store.PrepareAsync(new WindowsProofPrepareRequest(
                "prepare-missing-material",
                missingMaterial.Root,
                missingMaterial.ManifestSha256)));
        Assert.Contains("source-material set is incomplete", materialError.Message, StringComparison.Ordinal);

        SourceBundle missingInput = fixture.CreateSource(
            "run-proof-missing-input",
            "installer-missing-input",
            omitBuildInput: true);
        InvalidDataException inputError = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.Store.PrepareAsync(new WindowsProofPrepareRequest(
                "prepare-missing-input",
                missingInput.Root,
                missingInput.ManifestSha256)));
        Assert.Contains("input set is incomplete", inputError.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task DeliveryRevalidatesV2ExpiryWhileLegacyParsingRequiresExplicitMode()
    {
        using var fixture = new Fixture();
        SourceBundle source = fixture.CreateSource("run-proof-expiry", "installer-expiry");
        WindowsProofPreparedGeneration prepared = await fixture.Store.PrepareAsync(
            new WindowsProofPrepareRequest("prepare-expiry", source.Root, source.ManifestSha256));
        await fixture.Store.ActivateAsync(new WindowsProofActivationRequest(
            "activate-expiry",
            prepared.GenerationId,
            prepared.InventoryDigest,
            ExpectedCurrentGenerationId: null));
        WindowsProofGenerationSnapshot preExpiry = Assert.IsType<WindowsProofGenerationSnapshot>(
            fixture.Store.CaptureCurrent());
        WindowsProofInventoryEntry installer = Assert.Single(
            preExpiry.Inventory,
            row => row.Kind == WindowsProofArtifactKind.Installer);

        fixture.Clock.Advance(TimeSpan.FromHours(24));
        InvalidDataException expired = Assert.Throws<InvalidDataException>(
            () => fixture.Store.CaptureCurrent());
        Assert.Contains("expired", expired.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Throws<InvalidDataException>(() => preExpiry.OpenVerifiedArtifact(installer));

        JsonObject legacy = JsonNode.Parse(File.ReadAllText(Path.Combine(
            source.Root,
            WindowsProofManifestValidator.ManifestFileName)))!.AsObject();
        legacy["schemaVersion"] = WindowsProofManifestValidator.LegacyManifestSchemaVersion;
        legacy.Remove("generatedAt");
        legacy.Remove("expiresAt");
        JsonArray artifacts = legacy["artifacts"]!.AsArray();
        for (int index = artifacts.Count - 1; index >= 0; index--)
        {
            string? kind = artifacts[index]?["kind"]?.GetValue<string>();
            if (kind is "build_provenance_receipt" or "sbom")
            {
                artifacts.RemoveAt(index);
            }
        }
        byte[] legacyBytes = Encoding.UTF8.GetBytes(legacy.ToJsonString());
        var validator = new WindowsProofManifestValidator(fixture.Clock);
        Assert.Throws<InvalidDataException>(() => validator.ParseAndValidate(legacyBytes));
        WindowsProofManifest parsed = validator.ParseAndValidate(
            legacyBytes,
            allowLegacyV1Delivery: true);
        Assert.Equal(WindowsProofManifestValidator.LegacyManifestSchemaVersion, parsed.SchemaVersion);
    }

    [Fact]
    public async Task StoreRootMayNotOverlapCanonicalReleaseShelf()
    {
        string root = Path.Combine(Path.GetTempPath(), "windows-proof-overlap-tests", Guid.NewGuid().ToString("N"));
        try
        {
            string canonical = Path.Combine(root, "canonical");
            Directory.CreateDirectory(canonical);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    [WindowsProofGenerationStore.RootConfigurationKey] = Path.Combine(canonical, "proof"),
                    [WindowsProofGenerationStore.CfAccessGatedConfigurationKey] = "true",
                    [WindowsProofGenerationStore.CanonicalDownloadsRootConfigurationKey] = canonical
                })
                .Build();
            var store = new WindowsProofGenerationStore(configuration);

            await Assert.ThrowsAsync<InvalidOperationException>(() => store.PrepareAsync(
                new WindowsProofPrepareRequest("prepare-overlap", root, new string('0', 64))));
        }
        finally
        {
            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }

    private sealed class Fixture : IDisposable
    {
        private int _sourceNumber;

        public Fixture()
        {
            Clock = new AdjustableTimeProvider(DateTimeOffset.UtcNow);
            Root = Path.Combine(
                Path.GetTempPath(),
                "windows-proof-generation-store-tests",
                Guid.NewGuid().ToString("N"));
            StoreRoot = Path.Combine(Root, "windows-proof-store");
            CanonicalRoot = Path.Combine(Root, "canonical-downloads");
            Directory.CreateDirectory(CanonicalRoot);
            CanonicalSentinel = Path.Combine(CanonicalRoot, "sentinel.txt");
            File.WriteAllText(CanonicalSentinel, "canonical-sentinel");
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    [WindowsProofGenerationStore.RootConfigurationKey] = StoreRoot,
                    [WindowsProofGenerationStore.CfAccessGatedConfigurationKey] = "true",
                    [WindowsProofGenerationStore.CanonicalDownloadsRootConfigurationKey] = CanonicalRoot
                })
                .Build();
            Store = new WindowsProofGenerationStore(configuration, Clock);
        }

        public string Root { get; }

        public string StoreRoot { get; }

        public string CanonicalRoot { get; }

        public string CanonicalSentinel { get; }

        public WindowsProofGenerationStore Store { get; }

        public AdjustableTimeProvider Clock { get; }

        public SourceBundle CreateSource(
            string version,
            string installerContents,
            bool includeEmbeddedInstallerMetadata = true,
            bool omitSourceMaterial = false,
            bool omitBuildInput = false,
            Action<ZipArchive>? payloadWriter = null,
            Action<string>? payloadMutator = null)
        {
            string source = Path.Combine(Root, $"source-{++_sourceNumber}");
            string files = Path.Combine(source, "files");
            string signing = Path.Combine(source, "signing");
            string smoke = Path.Combine(source, "startup-smoke");
            string proof = Path.Combine(source, "proof");
            Directory.CreateDirectory(files);
            Directory.CreateDirectory(signing);
            Directory.CreateDirectory(smoke);
            Directory.CreateDirectory(proof);
            const string artifactId = "avalonia-win-x64-installer";
            const string installerName = "chummer-avalonia-win-x64-installer.exe";
            const string payloadName = "chummer-avalonia-win-x64-payload.zip";
            string payloadPath = Path.Combine(files, payloadName);
            WritePayloadArchive(
                payloadPath,
                payloadWriter ?? (archive =>
                {
                    WriteZipEntry(archive, "app/Chummer.Avalonia.exe", "payload-" + installerContents);
                    WriteZipEntry(archive, "app/Chummer.Avalonia.runtimeconfig.json", "{\"runtimeOptions\":{}}");
                }));
            payloadMutator?.Invoke(payloadPath);
            string payloadSha = Sha256(payloadPath);
            long payloadSize = new FileInfo(payloadPath).Length;
            string payloadUrl =
                $"https://chummer.run/downloads/proof/windows/candidates/{version}/files/{payloadName}";
            string installerPath = Path.Combine(files, installerName);
            string embeddedMetadata =
                "\nCHUMMER6_BOOTSTRAP_METADATA\n"
                + $"payloadFileName={payloadName}\n"
                + $"payloadDownloadUrl={payloadUrl}\n"
                + $"payloadSha256={payloadSha}\n"
                + $"payloadSizeBytes={payloadSize}\n"
                + "payloadAcquisitionMode=embedded\n";
            File.WriteAllText(
                installerPath,
                includeEmbeddedInstallerMetadata
                    ? installerContents + embeddedMetadata
                    : installerContents);
            string installerSha = Sha256(installerPath);
            long installerSize = new FileInfo(installerPath).Length;
            IReadOnlyDictionary<string, byte[]> provenanceFiles =
                WindowsBuildProvenanceTestFixture.CreateFiles(
                    version,
                    artifactId,
                    installerName,
                    File.ReadAllBytes(installerPath),
                    omitSourceMaterial,
                    omitBuildInput);
            foreach ((string relativePath, byte[] bytes) in provenanceFiles)
            {
                string path = Path.Combine(
                    source,
                    relativePath.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                File.WriteAllBytes(path, bytes);
            }
            string provenancePath = Path.Combine(
                source,
                provenanceFiles.Keys.Single(path => path.Contains("/invocations/", StringComparison.Ordinal))
                    .Replace('/', Path.DirectorySeparatorChar));
            string sbomPath = Path.Combine(
                source,
                provenanceFiles.Keys.Single(path => path.Contains("/sbom/", StringComparison.Ordinal))
                    .Replace('/', Path.DirectorySeparatorChar));
            const string metadataName = "chummer-avalonia-win-x64-payload.zip.json";
            string metadataPath = Path.Combine(files, metadataName);
            WriteJson(metadataPath, new
            {
                contractName = "chummer6-ui.windows_bootstrap_payload",
                fileName = payloadName,
                downloadUrl = payloadUrl,
                sha256 = payloadSha,
                sizeBytes = payloadSize,
                payloadAcquisitionMode = "embedded",
                installerFileName = installerName,
                releaseVersion = version
            });

            const string signingName = "signing-avalonia-win-x64.receipt.json";
            string signingPath = Path.Combine(signing, signingName);
            WriteJson(signingPath, new
            {
                contractName = "chummer6-ui.desktop_artifact_signing",
                platform = "windows",
                app = "avalonia",
                rid = "win-x64",
                releaseChannel = "preview",
                releaseVersion = version,
                signingStatus = "skipped_preview",
                artifacts = new[]
                {
                    new
                    {
                        fileName = installerName,
                        sha256 = installerSha,
                        kind = "installer",
                        signingStatus = "skipped_preview"
                    }
                }
            });

            const string smokeName = "startup-smoke-avalonia-win-x64.receipt.json";
            string smokePath = Path.Combine(smoke, smokeName);
            WriteJson(smokePath, new
            {
                status = "pass",
                headId = "avalonia",
                version,
                releaseVersion = version,
                channelId = "preview",
                platform = "windows",
                rid = "win-x64",
                artifactId,
                artifactFileName = installerName,
                artifactRelativePath = $"files/{installerName}",
                artifactDigest = $"sha256:{installerSha}",
                artifactSha256 = installerSha,
                executionEnvironment = "wine_compatibility",
                bootstrapPayloadAcquisitionMode = "embedded",
                bootstrapPayloadFileName = payloadName,
                bootstrapPayloadSha256 = payloadSha,
                bootstrapPayloadSizeBytes = payloadSize,
                verificationScope = "windows_compatibility_startup",
                nativeHostEvidence = new
                {
                    contractName = "chummer6-ui.native_windows_host_evidence",
                    status = "not_native",
                    isNativeWindows = false,
                    hostPlatform = "linux",
                    runner = "wine"
                }
            });
            string smokeSha = Sha256(smokePath);

            const string handoffName = "windows-visual-handoff.json";
            string handoffPath = Path.Combine(proof, handoffName);
            WriteJson(handoffPath, new
            {
                contract_name = "chummer6-ui.windows_installer_visual_proof_handoff",
                handoff_only = true,
                handoff_scope = "staged_nightly_windows_visual_proof",
                stable_release_unchanged = true,
                requires_separate_publish_lane = true,
                status = "ready_for_windows_host",
                only_blocker = "visual_proof",
                only_blocker_is_visual_proof = true,
                blockers = Array.Empty<string>(),
                release = new
                {
                    channel_id = "preview",
                    version,
                    release_version = version,
                    release_scope = "proof_only",
                    supportability_state = "review_required",
                    public_trust_posture = "blocked",
                    cf_access_gated = true
                },
                windows_installer = new
                {
                    artifact_id = artifactId,
                    file_name = installerName,
                    sha256 = installerSha
                },
                startup_smoke_path = $"startup-smoke/{smokeName}",
                startup_smoke = new
                {
                    status = "pass",
                    version,
                    release_version = version,
                    artifact_id = artifactId,
                    artifact_file_name = installerName,
                    artifact_digest = installerSha,
                    receipt_file_name = smokeName,
                    receipt_sha256 = smokeSha,
                    bootstrap_payload_acquisition_mode = "embedded",
                    matches_release_version = true,
                    matches_artifact_file_name = true,
                    matches_artifact_digest = true
                }
            });

            object[] artifacts =
            {
                Row("installer", installerName, $"files/{installerName}", "application/vnd.microsoft.portable-executable", installerPath),
                Row("bootstrap_payload", artifactId, payloadName, $"files/{payloadName}", "application/zip", payloadPath),
                Row("bootstrap_metadata", artifactId, metadataName, $"files/{metadataName}", "application/json", metadataPath),
                Row("signing_receipt", artifactId, signingName, $"signing/{signingName}", "application/json", signingPath),
                Row("startup_smoke_receipt", artifactId, smokeName, $"startup-smoke/{smokeName}", "application/json", smokePath),
                Row("build_provenance_receipt", artifactId, Path.GetFileName(provenancePath), Path.GetRelativePath(source, provenancePath).Replace(Path.DirectorySeparatorChar, '/'), "application/json", provenancePath),
                Row("sbom", artifactId, Path.GetFileName(sbomPath), Path.GetRelativePath(source, sbomPath).Replace(Path.DirectorySeparatorChar, '/'), "application/vnd.cyclonedx+json", sbomPath),
                Row("visual_handoff", artifactId, handoffName, $"proof/{handoffName}", "application/json", handoffPath)
            };
            string manifestPath = Path.Combine(source, WindowsProofManifestValidator.ManifestFileName);
            WriteJson(manifestPath, new
            {
                schemaVersion = WindowsProofManifestValidator.ManifestSchemaVersion,
                candidateVersion = version,
                channel = "preview",
                releaseScope = "proof_only",
                supportabilityState = "review_required",
                publicTrustPosture = "blocked",
                cfAccessGated = true,
                revoked = false,
                generatedAt = Clock.GetUtcNow().ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'"),
                expiresAt = Clock.GetUtcNow().AddHours(23).ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'"),
                proofOnlyPolicy = new
                {
                    enabled = true,
                    unsignedPreviewAllowed = true,
                    nativeWindowsValidationRequired = true
                },
                signing = new
                {
                    status = "skipped_preview",
                    proofOnlyPolicyRecorded = true,
                    receiptArtifactId = artifactId
                },
                compatibilitySmoke = new
                {
                    status = "pass",
                    executionEnvironment = "wine_compatibility",
                    nativeWindows = false,
                    receiptArtifactId = artifactId,
                    payloadAcquisitionMode = "embedded"
                },
                visualExitGate = new
                {
                    status = "external_only",
                    evidenceArtifactId = (string?)null
                },
                nativeHostHandoff = new
                {
                    status = "ready_for_windows_host",
                    onlyBlocker = "visual_proof",
                    onlyBlockerIsVisualProof = true,
                    handoffArtifactId = artifactId
                },
                artifacts
            });
            return new SourceBundle(source, Sha256(manifestPath));
        }

        public void Dispose()
        {
            if (!Directory.Exists(Root))
            {
                return;
            }

            if (!OperatingSystem.IsWindows())
            {
                foreach (string file in Directory.EnumerateFiles(Root, "*", SearchOption.AllDirectories))
                {
                    File.SetUnixFileMode(file, UnixFileMode.UserRead | UnixFileMode.UserWrite);
                }

                foreach (string directory in Directory.EnumerateDirectories(Root, "*", SearchOption.AllDirectories))
                {
                    File.SetUnixFileMode(
                        directory,
                        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
                }
            }

            Directory.Delete(Root, recursive: true);
        }

        private static object Row(
            string kind,
            string fileName,
            string relativePath,
            string contentType,
            string path)
            => Row(kind, "avalonia-win-x64-installer", fileName, relativePath, contentType, path);

        private static object Row(
            string kind,
            string artifactId,
            string fileName,
            string relativePath,
            string contentType,
            string path)
            => new
            {
                kind,
                artifactId,
                head = "avalonia",
                rid = "win-x64",
                fileName,
                relativePath,
                contentType,
                size = new FileInfo(path).Length,
                sha256 = Sha256(path)
            };

        private static void WriteJson(string path, object value)
            => File.WriteAllText(path, JsonSerializer.Serialize(value));
    }

    private sealed class AdjustableTimeProvider(DateTimeOffset utcNow) : TimeProvider
    {
        private DateTimeOffset _utcNow = utcNow;

        public override DateTimeOffset GetUtcNow() => _utcNow;

        public void Advance(TimeSpan duration) => _utcNow = _utcNow.Add(duration);
    }

    private sealed record SourceBundle(string Root, string ManifestSha256);

    private static void WritePayloadArchive(string path, Action<ZipArchive> writer)
    {
        using FileStream stream = new(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None);
        using var archive = new ZipArchive(stream, ZipArchiveMode.Create, leaveOpen: false);
        writer(archive);
    }

    private static void WriteZipEntry(
        ZipArchive archive,
        string path,
        string contents,
        CompressionLevel compressionLevel = CompressionLevel.Optimal)
    {
        ZipArchiveEntry entry = archive.CreateEntry(path, compressionLevel);
        using var writer = new StreamWriter(entry.Open(), new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        writer.Write(contents);
    }

    private static void CorruptFirstStoredEntry(string path)
    {
        byte[] bytes = File.ReadAllBytes(path);
        int local = FindZipSignature(bytes, 0x03, 0x04);
        Assert.True(local >= 0, "Stored ZIP fixture local header was not found.");
        ushort compressionMethod = BitConverter.ToUInt16(bytes, local + 8);
        Assert.Equal((ushort)0, compressionMethod);
        ushort nameLength = BitConverter.ToUInt16(bytes, local + 26);
        ushort extraLength = BitConverter.ToUInt16(bytes, local + 28);
        int dataOffset = checked(local + 30 + nameLength + extraLength);
        Assert.InRange(dataOffset, 0, bytes.Length - 1);
        bytes[dataOffset] ^= 0x01;
        File.WriteAllBytes(path, bytes);
    }

    private static int FindZipSignature(byte[] bytes, byte third, byte fourth)
    {
        for (int index = 0; index <= bytes.Length - 4; index++)
        {
            if (bytes[index] == 0x50
                && bytes[index + 1] == 0x4b
                && bytes[index + 2] == third
                && bytes[index + 3] == fourth)
            {
                return index;
            }
        }
        return -1;
    }

    private static void MarkFirstZipEntryEncrypted(string path)
    {
        byte[] bytes = File.ReadAllBytes(path);
        bool patchedLocalHeader = false;
        bool patchedCentralHeader = false;
        for (int index = 0; index <= bytes.Length - 10; index++)
        {
            if (bytes[index] == 0x50
                && bytes[index + 1] == 0x4b
                && bytes[index + 2] == 0x03
                && bytes[index + 3] == 0x04)
            {
                bytes[index + 6] |= 0x01;
                patchedLocalHeader = true;
            }
            else if (bytes[index] == 0x50
                     && bytes[index + 1] == 0x4b
                     && bytes[index + 2] == 0x01
                     && bytes[index + 3] == 0x02)
            {
                bytes[index + 8] |= 0x01;
                patchedCentralHeader = true;
            }
        }
        Assert.True(patchedLocalHeader && patchedCentralHeader, "ZIP encryption fixture headers were not found.");
        File.WriteAllBytes(path, bytes);
    }

    private static string Sha256(string path)
        => Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));
}
