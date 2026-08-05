using System.IO.Compression;
using System.Security.Cryptography;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseUploadSnapshotAuthorityTests
{
    private const long UnsignedBundleInventoryCount = 344;
    private const string UnsignedBundleInventorySha256 =
        "0f26e227d658d3986bd54969d8b994fa89046807325f5367f1a5b23572eb6026";
    private static readonly string[] UnsignedRetainedPointerKeys =
    [
        "atomicallyRetained",
        "authority",
        "bundleInventoryCount",
        "bundleInventorySha256",
        "consumerCommit",
        "contractName",
        "contractVersion",
        "manifest",
        "manifestIsAuthoritative",
        "release",
        "status",
        "targetPath"
    ];

    [Fact]
    public void RawFleetCredentialCannotBypassMissingOrReviewOnlySnapshotPolicy()
    {
        using var fixture = new SnapshotFixture();
        Assert.Null(fixture.Evaluate());

        fixture.Publish("review_required");

        Assert.Null(fixture.Evaluate());
        ReleaseUploadSnapshotAuthority review = fixture.Authority.Load();
        Assert.True(review.IsValid, review.FailureReason);
        Assert.False(review.ReleaseUploadAuthority);
        Assert.False(review.CandidateImportAuthority);
    }

    [Fact]
    public void FullPassSnapshotAuthorizesFleetCredentialAndPrivilegedReconciliation()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("pass");

        ReleaseUploadAuthorizationContext authorization = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate());

        Assert.False(authorization.SingleUseAuthorization);
        Assert.True(authorization.AllowsPrivilegedReconciliation);
        Assert.Null(authorization.CandidateImportAuthority);
        Assert.Matches("^[0-9a-f]{64}$", authorization.AuthorizationBinding);
    }

    [Fact]
    public void CandidateSnapshotRequiresExactHeadersAndForcesSingleUseFleetAuthorization()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("candidate_import_ready");
        ReleaseUploadCandidateAuthority candidate = Assert.IsType<ReleaseUploadCandidateAuthority>(
            fixture.Authority.Load().Candidate);
        Assert.False(candidate.ExactIncomingDesktopScopeIsFreshDelta);
        Assert.False(candidate.SessionBinding.ExactIncomingDesktopScopeIsFreshDelta);
        Assert.Null(candidate.IncumbentBinding);

        Assert.Null(fixture.Evaluate());
        Assert.Null(fixture.Evaluate(candidate.Candidate, includeExactScope: false));
        ReleaseUploadAuthorizationContext exact = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate(candidate.Candidate));

        Assert.True(exact.SingleUseAuthorization);
        Assert.False(exact.AllowsPrivilegedReconciliation);
        Assert.Equal(candidate.SessionBinding, exact.CandidateImportAuthority?.SessionBinding);
        Assert.Equal(candidate.ExpiresAtUtc, exact.AuthorizationExpiresAtUtc);

        ReleaseUploadCandidateIdentity mismatch = candidate.Candidate with
        {
            InventorySha256 = new string('f', 64)
        };
        Assert.Null(fixture.Evaluate(mismatch));
    }

    [Fact]
    public void CandidateAuthorityIsGloballyOneShotAcrossFleetAndRotatedTickets()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("candidate_import_ready");
        ReleaseUploadCandidateAuthority candidate = Assert.IsType<ReleaseUploadCandidateAuthority>(
            fixture.Authority.Load().Candidate);
        ReleaseUploadAuthorizationContext fleet = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate(candidate.Candidate));
        ReleaseUploadTicketIssueResult firstTicket = fixture.IssueTicket("first-operator");
        ReleaseUploadTicketIssueResult secondTicket = fixture.IssueTicket("second-operator");
        ReleaseUploadAuthorizationContext first = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate(candidate.Candidate, firstTicket.Ticket));
        ReleaseUploadAuthorizationContext second = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate(candidate.Candidate, secondTicket.Ticket));

        Assert.Equal(fleet.AuthorizationBinding, first.AuthorizationBinding);
        Assert.Equal(fleet.AuthorizationBinding, second.AuthorizationBinding);
        ReleaseUploadSession created = fixture.UploadSessions.CreateSession(
            fleet.AuthorizationBinding,
            fleet.SingleUseAuthorization,
            fleet.AuthorizationExpiresAtUtc,
            fleet.CandidateImportAuthority?.SessionBinding);
        Assert.Equal(
            created.SessionId,
            fixture.UploadSessions.CreateSession(
                first.AuthorizationBinding,
                first.SingleUseAuthorization,
                first.AuthorizationExpiresAtUtc,
                first.CandidateImportAuthority?.SessionBinding).SessionId);
        Assert.Equal(
            created.SessionId,
            fixture.UploadSessions.CreateSession(
                second.AuthorizationBinding,
                second.SingleUseAuthorization,
                second.AuthorizationExpiresAtUtc,
                second.CandidateImportAuthority?.SessionBinding).SessionId);

        ReleaseBundlePromotionResult result = BuildPromotionResult();
        using (ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
               fixture.UploadSessions.BeginCompletion(created.SessionId, fleet.AuthorizationBinding))
        {
            completion.RecordActivationIntent(BuildActivationIntent(result));
            completion.MarkCompleted(result);
        }

        foreach (ReleaseUploadAuthorizationContext replay in new[] { fleet, first, second })
        {
            InvalidOperationException consumed = Assert.Throws<InvalidOperationException>(() =>
                fixture.UploadSessions.CreateSession(
                    replay.AuthorizationBinding,
                    replay.SingleUseAuthorization,
                    replay.AuthorizationExpiresAtUtc,
                    replay.CandidateImportAuthority?.SessionBinding));
            Assert.Contains("already been consumed", consumed.Message, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void CandidateBundleValidatorRejectsAnyExtraOrChangedStagedByte()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("candidate_import_ready");
        ReleaseUploadCandidateAuthority candidate = Assert.IsType<ReleaseUploadCandidateAuthority>(
            fixture.Authority.Load().Candidate);
        string bundle = fixture.CreateExactBundle(candidate);

        ReleaseUploadCandidateBundleValidator.Validate(bundle, candidate);
        File.WriteAllText(Path.Combine(bundle, "unexpected.bin"), "extra");

        InvalidDataException rejected = Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadCandidateBundleValidator.Validate(bundle, candidate));
        Assert.Contains("exact candidate authority inventory", rejected.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RuntimeLoadsUnsignedV3AndValidatesExactBundleWithRetainedAncillaryFile()
    {
        using var fixture = new SnapshotFixture();
        byte[] authorityBytes = LoadUnsignedCandidateAuthorityV3();

        fixture.Publish("candidate_import_ready", authorityBytes);

        ReleaseUploadSnapshotAuthority loaded = fixture.Authority.Load();
        Assert.True(loaded.IsValid, loaded.FailureReason);
        Assert.True(loaded.CandidateImportAuthority);
        Assert.False(loaded.ReleaseUploadAuthority);
        ReleaseUploadCandidateAuthority candidate =
            Assert.IsType<ReleaseUploadCandidateAuthority>(loaded.Candidate);
        Assert.True(candidate.ExactIncomingDesktopScopeIsFreshDelta);
        Assert.True(candidate.SessionBinding.ExactIncomingDesktopScopeIsFreshDelta);
        Assert.NotNull(candidate.IncumbentBinding);
        Assert.Equal(candidate.IncumbentBinding, candidate.SessionBinding.IncumbentBinding);
        Assert.Equal(6, candidate.Inventory.Count);
        Assert.Contains(
            candidate.Inventory,
            static row => string.Equals(
                row.Path,
                "operator-note.txt",
                StringComparison.Ordinal));

        string bundle = fixture.CreateUnsignedExactBundle(candidate, authorityBytes);
        ReleaseUploadCandidateBundleValidator.Validate(bundle, candidate);
        Assert.True(Directory.Exists(Path.Combine(bundle, "files")));
        Assert.Equal(
            "ancillary-retained",
            File.ReadAllText(Path.Combine(bundle, "operator-note.txt")));
    }

    [Fact]
    public void RuntimeAcceptsFrozenUnsignedNativeV4AlternateShape()
    {
        using JsonDocument fixture = LoadUnsignedNativeEvidenceV4Contract();
        JsonElement root = fixture.RootElement;
        Assert.Equal(
            "4400a3a95ad923d5615bfe93a58df9e24d5e5a76",
            root.GetProperty("uiCommit").GetString());
        Assert.Equal(
            "789c19a9bad5fb03cf9ca06a51deb62659afba5648008a4c8775c5ae3a93279d",
            root.GetProperty("nativeOuterFileSha256").GetString());
        Assert.Equal(
            "0494a20ad8820013601842d4aca5fec49c0ee205bd2707b11e5e6bdfa1942c41",
            root.GetProperty("nativeCompactSha256").GetString());
        Assert.Equal(
            "5eefb891104780388a3ef14f4ff2dd9011fb7a7365c225edfbdac7194f449d4c",
            root.GetProperty("visualProofSha256").GetString());
        Assert.Equal(
            "580b7b3c7e8d640fb6ec987ceac5443f75aa4eb0efaebf96c701ba316d52df4d",
            root.GetProperty("hubEvidenceBindingSha256").GetString());
        byte[] canonicalManifest = Convert.FromBase64String(
            root.GetProperty("canonicalManifestBase64").GetString()!);
        var inventory = root.GetProperty("inventory")
            .EnumerateArray()
            .Select(row => new ReleaseUploadCandidateInventoryRow(
                row.GetProperty("path").GetString()!,
                row.GetProperty("sizeBytes").GetInt64(),
                row.GetProperty("sha256").GetString()!))
            .ToArray();
        string inventorySha256 =
            ReleaseUploadSnapshotAuthorityService.ComputeInventoryDigest(inventory);
        var candidate = new ReleaseUploadCandidateIdentity(
            root.GetProperty("version").GetString()!,
            root.GetProperty("canonicalManifestSha256").GetString()!,
            inventorySha256,
            inventory.Length,
            inventory.Sum(static row => row.SizeBytes),
            string.Empty);
        candidate = candidate with
        {
            BundleIdentitySha256 =
                ReleaseUploadSnapshotAuthorityService.ComputeBundleIdentity(candidate)
        };
        byte[] nativeEvidence = JsonSerializer.SerializeToUtf8Bytes(
            root.GetProperty("nativeEvidence"));

        ReleaseUploadCandidateNativeEvidenceBinding binding =
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedNativeEvidenceContract(
                nativeEvidence,
                canonicalManifest,
                candidate,
                inventory,
                root.GetProperty("nowUtc").GetDateTimeOffset());

        Assert.Equal(
            "4400a3a95ad923d5615bfe93a58df9e24d5e5a76",
            binding.SourceCommit);
        Assert.Equal(candidate.BundleIdentitySha256, binding.BundleIdentitySha256);
        Assert.Equal(
            candidate.CanonicalManifestSha256,
            binding.CanonicalManifestSha256);
        Assert.Equal(candidate.InventorySha256, binding.InventorySha256);
        Assert.Equal(
            root.GetProperty("hubEvidenceBindingSha256").GetString(),
            binding.EvidenceSha256);
        Assert.Matches("^[0-9a-f]{64}$", binding.CaptureInventorySha256);
        JsonElement visualProof = root
            .GetProperty("nativeEvidence")
            .GetProperty("files")
            .EnumerateArray()
            .Single(static row => string.Equals(
                row.GetProperty("path").GetString(),
                "UNSIGNED_WINDOWS_PREVIEW_VISUAL_PROOF-avalonia-win-x64.generated.json",
                StringComparison.Ordinal));
        Assert.Equal(
            root.GetProperty("visualProofSha256").GetString(),
            visualProof.GetProperty("sha256").GetString());
    }

    [Fact]
    public void RuntimeAcceptsFullUnsignedNativeV4WithDistinctProducerAndCaptureSources()
    {
        byte[] authorityBytes = LoadUnsignedCandidateAuthorityV4DistinctSource();
        using JsonDocument document = JsonDocument.Parse(authorityBytes);
        JsonElement root = document.RootElement;
        JsonElement custody = root.GetProperty("custody");
        JsonElement publicationEvidence =
            custody.GetProperty("unsignedPublicationEvidence");
        JsonElement nativeEvidence =
            custody.GetProperty("nativeWindowsFinalizedEvidence");
        string producerSource =
            publicationEvidence.GetProperty("sourceSha").GetString()!;
        string captureSource =
            nativeEvidence.GetProperty("captureSource").GetProperty("sha").GetString()!;
        string finalizationSource =
            nativeEvidence.GetProperty("finalizationSource").GetProperty("sha").GetString()!;
        Assert.Equal(
            producerSource,
            nativeEvidence.GetProperty("candidateContentInventory")
                .GetProperty("sourceSha")
                .GetString());
        Assert.Equal(captureSource, finalizationSource);
        Assert.NotEqual(producerSource, captureSource);

        DateTimeOffset evaluatedAt =
            root.GetProperty("generatedAtUtc").GetDateTimeOffset().AddMinutes(1);
        ReleaseUploadCandidateAuthority authority =
            ReleaseUploadSnapshotAuthorityService.ParseCandidateAuthority(
                "distinct-source-v4",
                new string('1', 64),
                Convert.ToHexStringLower(SHA256.HashData(authorityBytes)),
                authorityBytes,
                evaluatedAt);

        Assert.True(authority.ExactIncomingDesktopScopeIsFreshDelta);
        ReleaseUploadCandidateNativeEvidenceBinding binding =
            Assert.IsType<ReleaseUploadCandidateNativeEvidenceBinding>(
                authority.NativeEvidenceBinding);
        Assert.Equal(captureSource, binding.SourceCommit);
        Assert.Equal(
            authority.Candidate.BundleIdentitySha256,
            binding.BundleIdentitySha256);

        JsonElement sourceCanonical = publicationEvidence.GetProperty("files")
            .EnumerateArray()
            .Single(static row => string.Equals(
                row.GetProperty("path").GetString(),
                "transport/source-publication/RELEASE_CHANNEL.generated.json",
                StringComparison.Ordinal));
        JsonElement nativeCanonical = nativeEvidence
            .GetProperty("candidateContentInventory")
            .GetProperty("files")
            .EnumerateArray()
            .Single(static row => string.Equals(
                row.GetProperty("path").GetString(),
                "publication/RELEASE_CHANNEL.generated.json",
                StringComparison.Ordinal));
        Assert.Equal(
            sourceCanonical.GetProperty("sha256").GetString(),
            nativeCanonical.GetProperty("sha256").GetString());
        Assert.Equal(
            sourceCanonical.GetProperty("sizeBytes").GetInt64(),
            nativeCanonical.GetProperty("sizeBytes").GetInt64());
        Assert.NotEqual(
            authority.Candidate.CanonicalManifestSha256,
            nativeCanonical.GetProperty("sha256").GetString());

        JsonElement nativeInstaller = nativeEvidence
            .GetProperty("candidateContentInventory")
            .GetProperty("files")
            .EnumerateArray()
            .Single(static row => string.Equals(
                row.GetProperty("path").GetString(),
                "publication/files/chummer-avalonia-win-x64-installer.exe",
                StringComparison.Ordinal));
        ReleaseUploadCandidateInventoryRow candidateInstaller =
            authority.Inventory.Single(static row => string.Equals(
                row.Path,
                "files/chummer-avalonia-win-x64-installer.exe",
                StringComparison.Ordinal));
        Assert.Equal(candidateInstaller.Sha256, nativeInstaller.GetProperty("sha256").GetString());
        Assert.Equal(candidateInstaller.SizeBytes, nativeInstaller.GetProperty("sizeBytes").GetInt64());
    }

    [Fact]
    public void RuntimeAcceptsExactGenerationProjectedUnsignedNativeV5Bridge()
    {
        byte[] authorityBytes = BuildGenerationProjectedUnsignedNativeV5();
        using JsonDocument document = JsonDocument.Parse(authorityBytes);
        DateTimeOffset evaluatedAt = document.RootElement
            .GetProperty("generatedAtUtc")
            .GetDateTimeOffset()
            .AddMinutes(1);

        ReleaseUploadCandidateAuthority authority =
            ReleaseUploadSnapshotAuthorityService.ParseCandidateAuthority(
                $"public-projection-{new string('a', 64)}",
                new string('b', 64),
                Convert.ToHexStringLower(SHA256.HashData(authorityBytes)),
                authorityBytes,
                evaluatedAt);

        Assert.True(authority.Inventory.Count > 3);
        Assert.Equal(
            "gen-native-stage-authority-seed-test",
            JsonNode.Parse(authority.CanonicalManifestBytes)!["generationId"]!
                .GetValue<string>());
        Assert.Contains(
            authority.Inventory,
            static row => string.Equals(
                row.Path,
                "release-evidence/CURRENT.json",
                StringComparison.Ordinal));
        Assert.NotNull(authority.NativeEvidenceBinding);
    }

    [Fact]
    public void RuntimeRejectsGenerationProjectedUnsignedNativeV5DigestDrift()
    {
        JsonObject authority = JsonNode.Parse(
                BuildGenerationProjectedUnsignedNativeV5())?.AsObject()
            ?? throw new InvalidDataException("unsigned v5 authority fixture is invalid");
        authority["custody"]!["generationProjection"]![
            "projectedCanonicalManifestSha256"] = new string('f', 64);
        byte[] authorityBytes = JsonSerializer.SerializeToUtf8Bytes(authority);
        DateTimeOffset evaluatedAt = DateTimeOffset.Parse(
            authority["generatedAtUtc"]!.GetValue<string>()).AddMinutes(1);

        InvalidDataException drift = Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ParseCandidateAuthority(
                $"public-projection-{new string('a', 64)}",
                new string('b', 64),
                Convert.ToHexStringLower(SHA256.HashData(authorityBytes)),
                authorityBytes,
                evaluatedAt));

        Assert.Contains(
            "projectedCanonicalManifestSha256",
            drift.Message,
            StringComparison.Ordinal);
    }

    [Fact]
    public void RuntimeAcceptsRegistryPinnedUnsignedWindowsFreshDeltaManifestPair()
    {
        (JsonObject canonical, JsonObject compatibility) =
            LoadUnsignedWindowsFreshDeltaManifestPair();

        bool profile =
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedWindowsFreshDeltaManifestPair(
                JsonSerializer.SerializeToElement(canonical),
                JsonSerializer.SerializeToElement(compatibility),
                "run-20260803-204603");

        Assert.True(profile);
        Assert.Equal(
            "25ff1437a1f1bb6b04c823fa3cb47c0976d0e141",
            canonical["registryCommit"]!.GetValue<string>());
    }

    [Fact]
    public void RuntimeAcceptsRegistryPinnedUnsignedWindowsOnlyFreshDeltaManifestPair()
    {
        (JsonObject canonical, JsonObject compatibility) =
            LoadUnsignedWindowsFreshDeltaManifestPair();
        ConvertUnsignedFreshDeltaManifestPairToWindowsOnly(
            canonical,
            compatibility);

        bool profile =
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedWindowsFreshDeltaManifestPair(
                JsonSerializer.SerializeToElement(canonical),
                JsonSerializer.SerializeToElement(compatibility),
                "run-20260803-204603");

        Assert.True(profile);
        Assert.Single(canonical["artifacts"]!.AsArray());
        Assert.Empty(
            canonical["retainedIncumbentProvenance"]!
                .AsObject()["retainedArtifactBindings"]!
                .AsArray());
    }

    [Fact]
    public void RuntimeRejectsRegistryPinnedUnsignedFreshDeltaMixedRetainedModes()
    {
        (JsonObject canonical, JsonObject compatibility) =
            LoadUnsignedWindowsFreshDeltaManifestPair();
        JsonObject retainedCompatibility = compatibility.DeepClone().AsObject();
        ConvertUnsignedFreshDeltaManifestPairToWindowsOnly(
            canonical,
            compatibility);
        compatibility["downloads"] =
            retainedCompatibility["downloads"]!.DeepClone();
        compatibility["retainedIncumbentProvenance"] =
            retainedCompatibility["retainedIncumbentProvenance"]!.DeepClone();

        Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedWindowsFreshDeltaManifestPair(
                JsonSerializer.SerializeToElement(canonical),
                JsonSerializer.SerializeToElement(compatibility),
                "run-20260803-204603"));
    }

    [Fact]
    public void RuntimeLoadsRegistryPinnedUnsignedWindowsFreshDeltaAuthority()
    {
        byte[] authorityBytes = LoadUnsignedWindowsFreshDeltaCandidateAuthorityV3();
        ReleaseUploadCandidateAuthority candidate =
            ReleaseUploadSnapshotAuthorityService.ParseCandidateAuthority(
                $"public-projection-{new string('a', 64)}",
                new string('a', 64),
                Convert.ToHexStringLower(SHA256.HashData(authorityBytes)),
                authorityBytes);
        Assert.True(candidate.ExactIncomingDesktopScopeIsFreshDelta);
        Assert.Equal(58, candidate.Inventory.Count);
        ReleaseUploadCandidateIncumbentBinding incumbent =
            Assert.IsType<ReleaseUploadCandidateIncumbentBinding>(
                candidate.IncumbentBinding);
        Assert.Equal(
            "5e4e68256f7e0cd423555cc8d7daaff3e98af9fec8faf20bec3b714db64d8037",
            incumbent.SnapshotSha256);
    }

    [Fact]
    public void RuntimeRejectsCoordinatedRehashedUnsignedWindowsFreshDeltaRegistryCommitDrift()
    {
        byte[] authorityBytes =
            TamperUnsignedWindowsFreshDeltaRegistryCommit();

        Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ParseCandidateAuthority(
                $"public-projection-{new string('a', 64)}",
                new string('a', 64),
                Convert.ToHexStringLower(SHA256.HashData(authorityBytes)),
                authorityBytes));
    }

    [Theory]
    [InlineData("boolean_code_deploy_review")]
    [InlineData("retained_compatibility_byte")]
    [InlineData("recursive_authority_true")]
    [InlineData("windows_public_identity")]
    [InlineData("windows_account_required")]
    [InlineData("profile_wrong_type")]
    [InlineData("windows_id_wrong_type")]
    [InlineData("root_review_posture")]
    [InlineData("root_generated_alias")]
    [InlineData("proof_timestamp")]
    [InlineData("review_timestamp")]
    [InlineData("extra_compatibility_artifact")]
    public void RuntimeRejectsUnsignedWindowsFreshDeltaManifestPolicyDrift(string tamper)
    {
        (JsonObject canonical, JsonObject compatibility) =
            LoadUnsignedWindowsFreshDeltaManifestPair();
        switch (tamper)
        {
            case "boolean_code_deploy_review":
                canonical["codeDeployCurrentShelfAuthority"] = false;
                break;
            case "retained_compatibility_byte":
                compatibility["downloads"]!.AsArray()
                    .Select(static node => node!.AsObject())
                    .Single(static row => string.Equals(
                        row["id"]?.GetValue<string>(),
                        "avalonia-linux-x64-installer",
                        StringComparison.Ordinal))["sha256"] = new string('f', 64);
                break;
            case "recursive_authority_true":
                canonical["smuggledPolicy"] = new JsonObject
                {
                    ["uploadAuthorized"] = true
                };
                break;
            case "windows_public_identity":
                canonical["artifacts"]!.AsArray()
                    .Select(static node => node!.AsObject())
                    .Single(static row => string.Equals(
                        row["artifactId"]?.GetValue<string>(),
                        "avalonia-win-x64-installer",
                        StringComparison.Ordinal))["artifactByteVisibility"] =
                        "account_required";
                break;
            case "windows_account_required":
                canonical["artifacts"]!.AsArray()
                    .Select(static node => node!.AsObject())
                    .Single(static row => string.Equals(
                        row["artifactId"]?.GetValue<string>(),
                        "avalonia-win-x64-installer",
                        StringComparison.Ordinal))["installAccessClass"] =
                            "account_required";
                compatibility["downloads"]!.AsArray()
                    .Select(static node => node!.AsObject())
                    .Single(static row => string.Equals(
                        row["id"]?.GetValue<string>(),
                        "avalonia-win-x64-installer",
                        StringComparison.Ordinal))["installAccessClass"] =
                            "account_required";
                break;
            case "profile_wrong_type":
                canonical["projectionProfile"] = false;
                break;
            case "windows_id_wrong_type":
                canonical["artifacts"]!.AsArray()
                    .Select(static node => node!.AsObject())
                    .Single(static row => string.Equals(
                        row["artifactId"]?.GetValue<string>(),
                        "avalonia-win-x64-installer",
                        StringComparison.Ordinal))["id"] = true;
                break;
            case "root_review_posture":
                foreach (JsonObject manifest in new[] { canonical, compatibility })
                {
                    manifest["status"] = "draft";
                    manifest["rolloutState"] = "blocked";
                }
                break;
            case "root_generated_alias":
                canonical["generated_at"] = "2026-07-22T16:59:00Z";
                break;
            case "proof_timestamp":
                foreach (JsonObject manifest in new[] { canonical, compatibility })
                {
                    manifest["releaseProof"]!.AsObject()["generatedAt"] =
                        "2026-07-22T16:59:00Z";
                }
                break;
            case "review_timestamp":
                foreach (JsonObject manifest in new[] { canonical, compatibility })
                {
                    manifest["codeDeployCurrentShelfAuthority"]!
                        .AsObject()["evaluatedAt"] = "2026-07-22T16:59:00Z";
                }
                break;
            case "extra_compatibility_artifact":
            {
                JsonArray downloads = compatibility["downloads"]!.AsArray();
                JsonObject extra = downloads[0]!.DeepClone().AsObject();
                extra["artifactId"] = null;
                extra["id"] = "smuggled-osx-arm64-installer";
                extra["fileName"] = "smuggled-osx-arm64-installer.dmg";
                downloads.Add(extra);
                break;
            }
            default:
                throw new ArgumentOutOfRangeException(nameof(tamper));
        }

        Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedWindowsFreshDeltaManifestPair(
                JsonSerializer.SerializeToElement(canonical),
                JsonSerializer.SerializeToElement(compatibility),
                "run-20260803-204603"));
    }

    [Theory]
    [InlineData("package_lock_path_traversal", "path drifted")]
    [InlineData("package_lock_property_smuggling", "lock binding property set drifted")]
    [InlineData("retained_manifest_path_traversal", "path drifted")]
    [InlineData("retained_manifest_property_smuggling", "manifest binding property set drifted")]
    [InlineData("target_path_traversal", "target path is not a canonical absolute path")]
    [InlineData("target_path_unit_separator", "target path is not a canonical absolute path")]
    [InlineData("target_path_del", "target path is not a canonical absolute path")]
    [InlineData("pointer_property_smuggling", "pointer property set drifted")]
    [InlineData("missing_bundle_inventory_count", "pointer property set drifted")]
    [InlineData("bundle_inventory_count_zero", "bundleInventoryCount is invalid")]
    [InlineData("bundle_inventory_count_bool", "bundleInventoryCount is invalid")]
    [InlineData("bundle_inventory_count_fractional", "bundleInventoryCount is invalid")]
    [InlineData("missing_bundle_inventory_sha256", "pointer property set drifted")]
    [InlineData("bundle_inventory_sha256_uppercase", "bundleInventorySha256 is invalid")]
    public void RuntimeBindingValidatorRejectsUnsignedProducerPathOrPropertySmuggling(
        string tamper,
        string expectedFailure)
    {
        (JsonObject receipt, JsonObject retained, byte[] packageLock, byte[] retainedBytes) =
            LoadUnsignedProducerDocuments();
        JsonObject pointer = receipt["retainedWindowsBundle"]!.AsObject();
        bool rebindManifest = false;

        switch (tamper)
        {
            case "package_lock_path_traversal":
                receipt["consumerPackagePlaneLock"]!.AsObject()["path"] =
                    "config/nested/../package-plane.lock.json";
                break;
            case "package_lock_property_smuggling":
                retained["packagePlaneLock"]!.AsObject()["unexpectedProperty"] = true;
                break;
            case "retained_manifest_path_traversal":
                pointer["manifest"]!.AsObject()["path"] =
                    $"{pointer["targetPath"]!.GetValue<string>()}/nested/../manifest.json";
                break;
            case "retained_manifest_property_smuggling":
                pointer["manifest"]!.AsObject()["unexpectedProperty"] = true;
                break;
            case "target_path_traversal":
            {
                const string target =
                    "/tmp/chummer-preview/nested/../retained-windows-bundle";
                pointer["targetPath"] = target;
                pointer["manifest"]!.AsObject()["path"] = $"{target}/manifest.json";
                retained["targetPath"] = target;
                rebindManifest = true;
                break;
            }
            case "target_path_unit_separator":
            {
                const string target =
                    "/tmp/chummer-preview/unit\u001fseparator/retained-windows-bundle";
                pointer["targetPath"] = target;
                pointer["manifest"]!.AsObject()["path"] = $"{target}/manifest.json";
                retained["targetPath"] = target;
                rebindManifest = true;
                break;
            }
            case "target_path_del":
            {
                const string target =
                    "/tmp/chummer-preview/del\u007fsegment/retained-windows-bundle";
                pointer["targetPath"] = target;
                pointer["manifest"]!.AsObject()["path"] = $"{target}/manifest.json";
                retained["targetPath"] = target;
                rebindManifest = true;
                break;
            }
            case "pointer_property_smuggling":
                pointer["publicationAuthorized"] = false;
                break;
            case "missing_bundle_inventory_count":
                pointer.Remove("bundleInventoryCount");
                break;
            case "bundle_inventory_count_zero":
                pointer["bundleInventoryCount"] = 0;
                break;
            case "bundle_inventory_count_bool":
                pointer["bundleInventoryCount"] = true;
                break;
            case "bundle_inventory_count_fractional":
                pointer["bundleInventoryCount"] = 1.0;
                break;
            case "missing_bundle_inventory_sha256":
                pointer.Remove("bundleInventorySha256");
                break;
            case "bundle_inventory_sha256_uppercase":
                pointer["bundleInventorySha256"] = pointer["bundleInventorySha256"]!
                    .GetValue<string>()
                    .ToUpperInvariant();
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(tamper));
        }

        if (rebindManifest)
        {
            retainedBytes = JsonSerializer.SerializeToUtf8Bytes(retained);
            JsonObject manifest = pointer["manifest"]!.AsObject();
            manifest["sha256"] = Convert.ToHexStringLower(
                SHA256.HashData(retainedBytes));
            manifest["sizeBytes"] = retainedBytes.LongLength;
        }

        JsonElement receiptElement = JsonSerializer.SerializeToElement(receipt);
        if (tamper == "bundle_inventory_count_fractional")
        {
            string fractionalReceipt = receiptElement.GetRawText().Replace(
                "\"bundleInventoryCount\":1",
                "\"bundleInventoryCount\":1.0",
                StringComparison.Ordinal);
            Assert.Contains(
                "\"bundleInventoryCount\":1.0",
                fractionalReceipt,
                StringComparison.Ordinal);
            receiptElement = JsonDocument.Parse(fractionalReceipt).RootElement.Clone();
        }
        InvalidDataException rejected = Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedProducerBindings(
                receiptElement,
                JsonSerializer.SerializeToElement(retained),
                packageLock,
                retainedBytes));

        Assert.Contains(expectedFailure, rejected.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RuntimeBindingValidatorAcceptsActualUnsignedProducerShape()
    {
        (JsonObject receipt, JsonObject retained, byte[] packageLock, byte[] retainedBytes) =
            LoadUnsignedProducerDocuments();
        JsonObject pointer = receipt["retainedWindowsBundle"]!.AsObject();

        Assert.Equal(
            UnsignedRetainedPointerKeys.OrderBy(static value => value, StringComparer.Ordinal),
            pointer.Select(static property => property.Key)
                .OrderBy(static value => value, StringComparer.Ordinal));
        Assert.Equal(
            UnsignedBundleInventoryCount,
            pointer["bundleInventoryCount"]!.GetValue<long>());
        Assert.Equal(
            UnsignedBundleInventorySha256,
            pointer["bundleInventorySha256"]!.GetValue<string>());

        ReleaseUploadSnapshotAuthorityService.ValidateUnsignedProducerBindings(
            JsonSerializer.SerializeToElement(receipt),
            JsonSerializer.SerializeToElement(retained),
            packageLock,
            retainedBytes);
    }

    [Fact]
    public void UnsignedCanonicalValidatorAcceptsRealRetainedCrossPlatformShelf()
    {
        (JsonObject canonical,
            Dictionary<string, ReleaseUploadCandidateInventoryRow> inventory,
            JsonArray fresh) = BuildUnsignedCrossPlatformShelf();

        IReadOnlySet<string> managedRetainedPaths =
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedCanonicalWindows(
                JsonSerializer.SerializeToElement(canonical),
                inventory,
                JsonSerializer.SerializeToElement(fresh));

        Assert.Equal(
            new[]
            {
                "files/chummer-avalonia-linux-x64-installer.deb",
                "files/chummer-avalonia-osx-arm64-installer.dmg",
                "files/chummer-avalonia-osx-arm64.zip",
                "files/chummer-blazor-desktop-osx-arm64-installer.dmg",
                "files/chummer-blazor-desktop-osx-arm64.zip"
            },
            managedRetainedPaths.OrderBy(static path => path, StringComparer.Ordinal));
    }

    [Theory]
    [InlineData("required_head_widen", "requiredDesktopHeads")]
    [InlineData("extra_windows_head", "outside requiredDesktopHeads")]
    [InlineData("retained_head", "artifact head is invalid")]
    [InlineData("retained_unknown_head", "artifact head is invalid")]
    [InlineData("retained_platform", "outside the exact desktop shelf scope")]
    [InlineData("retained_rid", "outside the exact desktop shelf scope")]
    [InlineData("retained_linux_rid", "outside the exact desktop shelf scope")]
    [InlineData("retained_kind", "outside the exact desktop shelf scope")]
    [InlineData("retained_linux_kind", "outside the exact desktop shelf scope")]
    [InlineData("retained_bytes", "artifact bytes drifted")]
    [InlineData("duplicate_primary_path", "artifact bytes drifted")]
    [InlineData("windows_archive", "outside the exact desktop shelf scope")]
    public void UnsignedCanonicalValidatorRejectsInvalidRetainedShelfOrWindowsWidening(
        string drift,
        string expectedFailure)
    {
        (JsonObject canonical,
            Dictionary<string, ReleaseUploadCandidateInventoryRow> inventory,
            JsonArray fresh) = BuildUnsignedCrossPlatformShelf();
        JsonArray artifacts = canonical["artifacts"]!.AsArray();
        JsonObject retained = artifacts
            .Select(static node => node!.AsObject())
            .Single(artifact =>
                string.Equals(
                    artifact["head"]!.GetValue<string>(),
                    "blazor-desktop",
                    StringComparison.Ordinal)
                && string.Equals(
                    artifact["kind"]!.GetValue<string>(),
                    "archive",
                    StringComparison.Ordinal));
        JsonObject linux = artifacts
            .Select(static node => node!.AsObject())
            .Single(artifact => string.Equals(
                artifact["platform"]!.GetValue<string>(),
                "linux",
                StringComparison.Ordinal));
        JsonObject windows = artifacts
            .Select(static node => node!.AsObject())
            .Single(artifact => string.Equals(
                artifact["platform"]!.GetValue<string>(),
                "windows",
                StringComparison.Ordinal));

        switch (drift)
        {
            case "required_head_widen":
                canonical["desktopTupleCoverage"]!
                    .AsObject()["requiredDesktopHeads"]!
                    .AsArray()
                    .Add("blazor-desktop");
                break;
            case "extra_windows_head":
            {
                byte[] raw = "undeclared-blazor-windows-installer"u8.ToArray();
                string digest = Convert.ToHexStringLower(SHA256.HashData(raw));
                const string fileName =
                    "chummer-blazor-desktop-win-x64-installer.exe";
                artifacts.Add(new JsonObject
                {
                    ["artifactId"] = "blazor-desktop-win-x64-installer",
                    ["head"] = "blazor-desktop",
                    ["platform"] = "windows",
                    ["rid"] = "win-x64",
                    ["kind"] = "installer",
                    ["installerMode"] = "bootstrap",
                    ["payloadAcquisitionMode"] = "download",
                    ["fileName"] = fileName,
                    ["sha256"] = digest,
                    ["sizeBytes"] = raw.LongLength,
                    ["payloadFileName"] =
                        "chummer-blazor-desktop-win-x64-payload.zip",
                    ["payloadSha256"] = new string('e', 64),
                    ["payloadSizeBytes"] = 1
                });
                inventory.Add(
                    $"files/{fileName}",
                    new ReleaseUploadCandidateInventoryRow(
                        $"files/{fileName}",
                        raw.LongLength,
                        digest));
                break;
            }
            case "retained_head":
                retained["head"] = "Blazor Desktop";
                break;
            case "retained_unknown_head":
                retained["head"] = "future-desktop";
                break;
            case "retained_platform":
                retained["platform"] = "android";
                break;
            case "retained_rid":
                retained["rid"] = "osx-ppc64";
                break;
            case "retained_linux_rid":
                linux["rid"] = "linux-arm64";
                break;
            case "retained_kind":
                retained["kind"] = "symbols";
                break;
            case "retained_linux_kind":
                linux["kind"] = "symbols";
                break;
            case "retained_bytes":
                retained["sha256"] = new string('f', 64);
                break;
            case "duplicate_primary_path":
            {
                JsonObject duplicate = artifacts
                    .Select(static node => node!.AsObject())
                    .Single(artifact =>
                        string.Equals(
                            artifact["head"]!.GetValue<string>(),
                            "avalonia",
                            StringComparison.Ordinal)
                        && string.Equals(
                            artifact["platform"]!.GetValue<string>(),
                            "macos",
                            StringComparison.Ordinal)
                        && string.Equals(
                            artifact["kind"]!.GetValue<string>(),
                            "archive",
                            StringComparison.Ordinal));
                retained["fileName"] = duplicate["fileName"]!.DeepClone();
                retained["sha256"] = duplicate["sha256"]!.DeepClone();
                retained["sizeBytes"] = duplicate["sizeBytes"]!.DeepClone();
                break;
            }
            case "windows_archive":
                windows["kind"] = "archive";
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(drift));
        }

        InvalidDataException rejected = Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedCanonicalWindows(
                JsonSerializer.SerializeToElement(canonical),
                inventory,
                JsonSerializer.SerializeToElement(fresh)));

        Assert.Contains(expectedFailure, rejected.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RuntimeRejectsRehashedUnsignedV3AuthorityPostureTamper()
    {
        using var fixture = new SnapshotFixture();
        JsonObject authority = JsonNode.Parse(LoadUnsignedCandidateAuthorityV3())?.AsObject()
            ?? throw new InvalidDataException("unsigned v3 authority fixture is invalid");
        authority["publicationAuthorized"] = true;

        fixture.Publish(
            "candidate_import_ready",
            JsonSerializer.SerializeToUtf8Bytes(authority));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();
        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Theory]
    [InlineData("full_inventory_digest")]
    [InlineData("release_property_set")]
    public void RuntimeRejectsCoordinatedRehashedUnsignedV3ScopeTamper(
        string tamper)
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish(
            "candidate_import_ready",
            TamperUnsignedCandidateAuthorityV3Scope(tamper));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();

        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Fact]
    public void RuntimeRejectsCoordinatedRehashedUnsignedV3CompositionReleasePropertySet()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish(
            "candidate_import_ready",
            TamperUnsignedCandidateAuthorityV3CompositionRelease());

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();

        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    internal static byte[] LoadUnsignedCandidateAuthorityV3()
    {
        string fixturePath = RepoPaths.FromRoot(
            "Chummer.Tests",
            "Fixtures",
            "unsigned_candidate_import_authority_v3.json.gz.b64");
        byte[] compressed = Convert.FromBase64String(
            string.Concat(File.ReadLines(fixturePath)));
        using var input = new MemoryStream(compressed, writable: false);
        using var gzip = new GZipStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream();
        gzip.CopyTo(output);
        JsonObject authority = JsonNode.Parse(output.ToArray())?.AsObject()
            ?? throw new InvalidDataException("unsigned v3 authority fixture is invalid");
        DateTimeOffset now = DateTimeOffset.UtcNow;
        authority["generatedAtUtc"] = now;
        authority["expiresAtUtc"] = now.AddHours(2);
        return JsonSerializer.SerializeToUtf8Bytes(authority);
    }

    private static JsonDocument LoadUnsignedNativeEvidenceV4Contract()
    {
        string fixturePath = RepoPaths.FromRoot(
            "Chummer.Tests",
            "Fixtures",
            "unsigned_native_evidence_v4_contract.json.gz.b64");
        byte[] compressed = Convert.FromBase64String(
            string.Concat(File.ReadLines(fixturePath)));
        using var input = new MemoryStream(compressed, writable: false);
        using var gzip = new GZipStream(input, CompressionMode.Decompress);
        return JsonDocument.Parse(gzip);
    }

    private static byte[] LoadUnsignedCandidateAuthorityV4DistinctSource()
    {
        string fixturePath = RepoPaths.FromRoot(
            "Chummer.Tests",
            "Fixtures",
            "unsigned_candidate_import_authority_v4_distinct_source.json.gz.b64");
        byte[] compressed = Convert.FromBase64String(
            string.Concat(File.ReadLines(fixturePath)));
        using var input = new MemoryStream(compressed, writable: false);
        using var gzip = new GZipStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream();
        gzip.CopyTo(output);
        return output.ToArray();
    }

    private static byte[] BuildGenerationProjectedUnsignedNativeV5()
    {
        JsonObject authority = JsonNode.Parse(
                LoadUnsignedCandidateAuthorityV4DistinctSource())?.AsObject()
            ?? throw new InvalidDataException("unsigned v4 authority fixture is invalid");
        JsonObject custody = authority["custody"]!.AsObject();
        JsonObject canonicalEntry = custody["canonicalManifest"]!.AsObject();
        JsonObject compatibilityEntry = custody["compatibilityManifest"]!.AsObject();
        byte[] sourceCanonicalBytes = Convert.FromBase64String(
            canonicalEntry["base64"]!.GetValue<string>());
        byte[] sourceCompatibilityBytes = Convert.FromBase64String(
            compatibilityEntry["base64"]!.GetValue<string>());
        JsonObject sourceCanonical = JsonNode.Parse(sourceCanonicalBytes)!.AsObject();
        JsonObject sourceCompatibility =
            JsonNode.Parse(sourceCompatibilityBytes)!.AsObject();
        PublicReleaseManifestDto publicManifest =
            JsonSerializer.Deserialize<PublicReleaseManifestDto>(
                sourceCompatibilityBytes,
                new JsonSerializerOptions(JsonSerializerDefaults.Web)
                {
                    PropertyNameCaseInsensitive = true
                })
            ?? throw new InvalidDataException(
                "unsigned v4 compatibility fixture is invalid");
        const string generationId = "gen-native-stage-authority-seed-test";
        byte[] projectedCanonical =
            ReleaseBundlePromotionService.ProjectRegistryManifestForGeneration(
                sourceCanonical,
                generationId,
                publicManifest);
        byte[] projectedCompatibility =
            ReleaseBundlePromotionService.ProjectRegistryManifestForGeneration(
                sourceCompatibility,
                generationId,
                publicManifest);
        RewriteUnsignedEmbedded(canonicalEntry, projectedCanonical);
        RewriteUnsignedEmbedded(compatibilityEntry, projectedCompatibility);

        JsonObject inventoryEntry = custody["inventory"]!.AsObject();
        JsonObject inventory = DecodeUnsignedEmbedded(inventoryEntry);
        JsonArray rows = inventory["files"]!.AsArray();
        JsonObject canonicalRow = rows
            .Select(static node => node!.AsObject())
            .Single(static row => string.Equals(
                row["path"]!.GetValue<string>(),
                "RELEASE_CHANNEL.generated.json",
                StringComparison.Ordinal));
        canonicalRow["sha256"] = Convert.ToHexStringLower(
            SHA256.HashData(projectedCanonical));
        canonicalRow["sizeBytes"] = projectedCanonical.LongLength;
        JsonObject compatibilityRow = rows
            .Select(static node => node!.AsObject())
            .Single(static row => string.Equals(
                row["path"]!.GetValue<string>(),
                "releases.json",
                StringComparison.Ordinal));
        compatibilityRow["sha256"] = Convert.ToHexStringLower(
            SHA256.HashData(projectedCompatibility));
        compatibilityRow["sizeBytes"] = projectedCompatibility.LongLength;

        var seedBytes = new Dictionary<string, byte[]>(StringComparer.Ordinal)
        {
            ["CURRENT.json"] = Encoding.UTF8.GetBytes("{\"status\":\"review_required\"}\n"),
            ["RELEASE_DECISION.json"] = Encoding.UTF8.GetBytes("{\"releaseDecisionStatus\":\"review_required\"}\n"),
            ["SNAPSHOT.json"] = Encoding.UTF8.GetBytes("{\"releaseDecisionStatus\":\"review_required\"}\n")
        };
        var authoritySeed = new JsonObject();
        foreach ((string name, byte[] bytes) in seedBytes)
        {
            string path = $"release-evidence/{name}";
            string sha256 = Convert.ToHexStringLower(SHA256.HashData(bytes));
            var row = new JsonObject
            {
                ["path"] = path,
                ["sha256"] = sha256,
                ["sizeBytes"] = bytes.LongLength
            };
            rows.Add(row);
            authoritySeed[name] = row.DeepClone();
        }
        JsonNode[] sortedRows = rows
            .OrderBy(
                static node => node!["path"]!.GetValue<string>(),
                StringComparer.Ordinal)
            .Select(static node => node!.DeepClone())
            .ToArray();
        inventory["files"] = new JsonArray(sortedRows);
        byte[] inventoryBytes = JsonSerializer.SerializeToUtf8Bytes(
            inventory,
            new JsonSerializerOptions { WriteIndented = false });
        inventoryBytes = [.. inventoryBytes, (byte)'\n'];
        RewriteUnsignedEmbedded(inventoryEntry, inventoryBytes);

        ReleaseUploadCandidateInventoryRow[] typedRows = inventory["files"]!
            .AsArray()
            .Select(static node => node!.AsObject())
            .Select(static row => new ReleaseUploadCandidateInventoryRow(
                row["path"]!.GetValue<string>(),
                row["sizeBytes"]!.GetValue<long>(),
                row["sha256"]!.GetValue<string>()))
            .ToArray();
        JsonObject candidateNode = authority["candidate"]!.AsObject();
        var candidate = new ReleaseUploadCandidateIdentity(
            candidateNode["version"]!.GetValue<string>(),
            Convert.ToHexStringLower(SHA256.HashData(projectedCanonical)),
            ReleaseUploadSnapshotAuthorityService.ComputeInventoryDigest(typedRows),
            typedRows.Length,
            typedRows.Sum(static row => row.SizeBytes),
            string.Empty);
        candidate = candidate with
        {
            BundleIdentitySha256 =
                ReleaseUploadSnapshotAuthorityService.ComputeBundleIdentity(candidate)
        };
        authority["candidate"] = JsonSerializer.SerializeToNode(
            candidate,
            new JsonSerializerOptions(JsonSerializerDefaults.Web));
        authority["contractName"] =
            "chummer.release-upload.candidate-import-authority/v5";
        authority["contractVersion"] = 5;
        authority["ownerNativeStageAuthoritySeedBridgeAuthority"] = true;
        custody["generationProjection"] = new JsonObject
        {
            ["contractName"] =
                "chummer.release-upload.native-stage-generation-projection/v1",
            ["contractVersion"] = 1,
            ["status"] = "passed",
            ["generationId"] = generationId,
            ["evaluatedAtUtc"] = authority["generatedAtUtc"]!.DeepClone(),
            ["sourceCanonicalManifestSha256"] = Convert.ToHexStringLower(
                SHA256.HashData(sourceCanonicalBytes)),
            ["sourceCompatibilityManifestSha256"] = Convert.ToHexStringLower(
                SHA256.HashData(sourceCompatibilityBytes)),
            ["projectedCanonicalManifestSha256"] = Convert.ToHexStringLower(
                SHA256.HashData(projectedCanonical)),
            ["projectedCompatibilityManifestSha256"] = Convert.ToHexStringLower(
                SHA256.HashData(projectedCompatibility)),
            ["authoritySeed"] = authoritySeed
        };
        return JsonSerializer.SerializeToUtf8Bytes(authority);
    }

    private static byte[] LoadUnsignedWindowsFreshDeltaCandidateAuthorityV3()
    {
        string fixturePath = RepoPaths.FromRoot(
            "Chummer.Tests",
            "Fixtures",
            "unsigned_windows_fresh_delta_candidate_import_authority_v3.json.gz.b64");
        byte[] compressed = Convert.FromBase64String(
            string.Concat(File.ReadLines(fixturePath)));
        using var input = new MemoryStream(compressed, writable: false);
        using var gzip = new GZipStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream();
        gzip.CopyTo(output);
        JsonObject authority = JsonNode.Parse(output.ToArray())?.AsObject()
            ?? throw new InvalidDataException(
                "unsigned fresh-delta authority fixture is invalid");
        DateTimeOffset now = DateTimeOffset.UtcNow;
        authority["generatedAtUtc"] = now;
        authority["expiresAtUtc"] = now.AddHours(2);
        return JsonSerializer.SerializeToUtf8Bytes(authority);
    }

    private static byte[] TamperUnsignedWindowsFreshDeltaRegistryCommit()
    {
        JsonObject authority = JsonNode.Parse(
                LoadUnsignedWindowsFreshDeltaCandidateAuthorityV3())?.AsObject()
            ?? throw new InvalidDataException(
                "unsigned fresh-delta authority fixture is invalid");
        JsonObject custody = authority["custody"]!.AsObject();
        const string driftedCommit =
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

        JsonObject candidateEntry =
            custody["registryPrepareCandidateReceipt"]!.AsObject();
        JsonObject candidate = DecodeUnsignedEmbedded(candidateEntry);
        candidate["registryCommit"] = driftedCommit;
        candidate["registry_commit"] = driftedCommit;
        RewriteUnsignedEmbedded(
            candidateEntry,
            Encoding.UTF8.GetBytes(candidate.ToJsonString() + "\n"));

        JsonObject registryAuthorityEntry =
            custody["registryFinalizeAuthority"]!.AsObject();
        JsonObject registryAuthority = DecodeUnsignedEmbedded(registryAuthorityEntry);
        registryAuthority["registryCommit"] = driftedCommit;
        registryAuthority["registry_commit"] = driftedCommit;
        RebindUnsignedReference(
            registryAuthority["candidateReceipt"]!.AsObject(),
            candidateEntry);
        RewriteUnsignedEmbedded(
            registryAuthorityEntry,
            Encoding.UTF8.GetBytes(registryAuthority.ToJsonString() + "\n"));

        JsonObject registryReceiptEntry =
            custody["registryFinalizeReceipt"]!.AsObject();
        JsonObject registryReceipt = DecodeUnsignedEmbedded(registryReceiptEntry);
        registryReceipt["registryCommit"] = driftedCommit;
        registryReceipt["registry_commit"] = driftedCommit;
        RebindUnsignedReference(
            registryReceipt["candidateReceipt"]!.AsObject(),
            candidateEntry);
        RebindUnsignedReference(
            registryReceipt["authority"]!.AsObject(),
            registryAuthorityEntry);
        RewriteUnsignedEmbedded(
            registryReceiptEntry,
            Encoding.UTF8.GetBytes(registryReceipt.ToJsonString() + "\n"));

        JsonObject finalization = custody["registryFinalization"]!.AsObject();
        finalization["candidateReceiptSha256"] =
            candidateEntry["sha256"]!.GetValue<string>();
        finalization["authoritySha256"] =
            registryAuthorityEntry["sha256"]!.GetValue<string>();
        finalization["finalizeReceiptSha256"] =
            registryReceiptEntry["sha256"]!.GetValue<string>();
        return JsonSerializer.SerializeToUtf8Bytes(authority);
    }

    private static (JsonObject Canonical, JsonObject Compatibility)
        LoadUnsignedWindowsFreshDeltaManifestPair()
    {
        string fixturePath = RepoPaths.FromRoot(
            "Chummer.Tests",
            "Fixtures",
            "unsigned_windows_fresh_delta_manifest_pair.json.gz.b64");
        byte[] compressed = Convert.FromBase64String(
            string.Concat(File.ReadLines(fixturePath)));
        using var input = new MemoryStream(compressed, writable: false);
        using var gzip = new GZipStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream();
        gzip.CopyTo(output);
        JsonObject pair = JsonNode.Parse(output.ToArray())?.AsObject()
            ?? throw new InvalidDataException(
                "unsigned fresh-delta manifest-pair fixture is invalid");
        return (
            pair["canonical"]?.AsObject()
                ?? throw new InvalidDataException(
                    "unsigned fresh-delta canonical fixture is invalid"),
            pair["compatibility"]?.AsObject()
                ?? throw new InvalidDataException(
                    "unsigned fresh-delta compatibility fixture is invalid"));
    }

    private static void ConvertUnsignedFreshDeltaManifestPairToWindowsOnly(
        JsonObject canonical,
        JsonObject compatibility)
    {
        canonical["artifacts"] = new JsonArray(
            canonical["artifacts"]!.AsArray()
                .Where(static node => string.Equals(
                    node!["platform"]!.GetValue<string>(),
                    "windows",
                    StringComparison.Ordinal))
                .Select(static node => node!.DeepClone())
                .ToArray());
        compatibility["downloads"] = new JsonArray(
            compatibility["downloads"]!.AsArray()
                .Where(static node => string.Equals(
                    node!["platform"]!.GetValue<string>(),
                    "windows",
                    StringComparison.Ordinal))
                .Select(static node => node!.DeepClone())
                .ToArray());

        string emptyArraySha256 =
            Convert.ToHexStringLower(SHA256.HashData("[]"u8));
        foreach (JsonObject manifest in new[] { canonical, compatibility })
        {
            JsonObject provenance =
                manifest["retainedIncumbentProvenance"]!.AsObject();
            provenance["retainedArtifactBindings"] = new JsonArray();
            provenance["retainedArtifactBindingsSha256"] = emptyArraySha256;
            provenance["retainedCompatibilityBindings"] = new JsonArray();
            provenance["retainedCompatibilityBindingsSha256"] = emptyArraySha256;

            JsonObject coverage = manifest["desktopTupleCoverage"]!.AsObject();
            coverage["requiredDesktopPlatforms"] =
                JsonSerializer.SerializeToNode(new[] { "windows" });
            coverage["requiredDesktopPlatformHeadRidTuples"] =
                JsonSerializer.SerializeToNode(
                    new[] { "avalonia:win-x64:windows" });
            coverage["missingRequiredHeads"] =
                JsonSerializer.SerializeToNode(new[] { "avalonia" });
            coverage["promotedInstallerTuples"] = new JsonArray();
            coverage["promotedPlatformHeadRidTuples"] = new JsonArray();
            coverage["promotedPlatformHeads"] = new JsonObject
            {
                ["windows"] = new JsonArray()
            };
            coverage["desktopRouteTruth"] = new JsonArray(
                coverage["desktopRouteTruth"]!.AsArray()
                    .Where(static node => string.Equals(
                        node!["platform"]!.GetValue<string>(),
                        "windows",
                        StringComparison.Ordinal))
                    .Select(static node => node!.DeepClone())
                    .ToArray());
        }

        JsonObject artifact = canonical["artifacts"]![0]!.AsObject();
        var inventory = new JsonArray
        {
            new JsonObject
            {
                ["arch"] = artifact["arch"]!.DeepClone(),
                ["artifactId"] = artifact["artifactId"]!.DeepClone(),
                ["fileName"] = artifact["fileName"]!.DeepClone(),
                ["head"] = artifact["head"]!.DeepClone(),
                ["kind"] = artifact["kind"]!.DeepClone(),
                ["payloadFileName"] = artifact["payloadFileName"]!.DeepClone(),
                ["payloadSha256"] = artifact["payloadSha256"]!.DeepClone(),
                ["payloadSizeBytes"] = artifact["payloadSizeBytes"]!.DeepClone(),
                ["platform"] = artifact["platform"]!.DeepClone(),
                ["rid"] = artifact["rid"]!.DeepClone(),
                ["sha256"] = artifact["sha256"]!.DeepClone(),
                ["sizeBytes"] = artifact["sizeBytes"]!.DeepClone()
            }
        };
        string projectedInventorySha256 = Convert.ToHexStringLower(
            SHA256.HashData(Encoding.UTF8.GetBytes(inventory.ToJsonString())));
        foreach (JsonObject manifest in new[] { canonical, compatibility })
        {
            JsonObject review =
                manifest["codeDeployCurrentShelfAuthority"]!.AsObject();
            review["projectedArtifactCount"] = 1;
            review["projectedArtifactInventorySha256"] =
                projectedInventorySha256;
        }
    }

    private static byte[] TamperUnsignedCandidateAuthorityV3Scope(string tamper)
    {
        JsonObject authority = JsonNode.Parse(LoadUnsignedCandidateAuthorityV3())?.AsObject()
            ?? throw new InvalidDataException("unsigned v3 authority fixture is invalid");
        JsonObject custody = authority["custody"]!.AsObject();
        JsonObject evidence = custody["unsignedPublicationEvidence"]!.AsObject();
        const string scopePath = "PREVIEW_NIGHTLY_UNSIGNED_SCOPE.proposed.json";
        JsonObject scopeEntry = evidence["files"]!.AsArray()
            .Select(static node => node!.AsObject())
            .Single(entry => string.Equals(
                entry["path"]!.GetValue<string>(),
                scopePath,
                StringComparison.Ordinal));
        JsonObject scope = DecodeUnsignedEmbedded(scopeEntry);

        switch (tamper)
        {
            case "full_inventory_digest":
                scope["fullShelfInventorySha256"] = new string('f', 64);
                evidence["fullShelfInventorySha256"] = new string('f', 64);
                break;
            case "release_property_set":
            {
                JsonObject release = scope["release"]!.AsObject();
                scope["release"] = new JsonObject
                {
                    ["channel"] = release["channel"]!.DeepClone(),
                    ["smuggled"] = true,
                    ["version"] = release["version"]!.DeepClone()
                };
                break;
            }
            default:
                throw new ArgumentOutOfRangeException(nameof(tamper));
        }

        byte[] scopeBytes = Encoding.UTF8.GetBytes(
            scope.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n");
        RewriteUnsignedEmbedded(scopeEntry, scopeBytes);
        evidence["publicationScopeSha256"] = scopeEntry["sha256"]!.GetValue<string>();

        JsonObject registryAuthorityEntry =
            custody["registryFinalizeAuthority"]!.AsObject();
        JsonObject registryAuthority = DecodeUnsignedEmbedded(registryAuthorityEntry);
        RebindUnsignedReference(
            registryAuthority["sourceScope"]!.AsObject(),
            scopeEntry);
        RewriteUnsignedEmbedded(
            registryAuthorityEntry,
            Encoding.UTF8.GetBytes(registryAuthority.ToJsonString() + "\n"));

        JsonObject registryReceiptEntry =
            custody["registryFinalizeReceipt"]!.AsObject();
        JsonObject registryReceipt = DecodeUnsignedEmbedded(registryReceiptEntry);
        RebindUnsignedReference(
            registryReceipt["sourceScope"]!.AsObject(),
            scopeEntry);
        RebindUnsignedReference(
            registryReceipt["authority"]!.AsObject(),
            registryAuthorityEntry);
        RewriteUnsignedEmbedded(
            registryReceiptEntry,
            Encoding.UTF8.GetBytes(registryReceipt.ToJsonString() + "\n"));

        JsonObject finalization = custody["registryFinalization"]!.AsObject();
        finalization["authoritySha256"] =
            registryAuthorityEntry["sha256"]!.GetValue<string>();
        finalization["finalizeReceiptSha256"] =
            registryReceiptEntry["sha256"]!.GetValue<string>();
        return JsonSerializer.SerializeToUtf8Bytes(authority);
    }

    private static (
        JsonObject Canonical,
        Dictionary<string, ReleaseUploadCandidateInventoryRow> Inventory,
        JsonArray Fresh) BuildUnsignedCrossPlatformShelf()
    {
        var artifacts = new JsonArray();
        var inventory = new Dictionary<string, ReleaseUploadCandidateInventoryRow>(
            StringComparer.Ordinal);

        JsonObject AddPrimary(
            string head,
            string platform,
            string rid,
            string kind,
            string fileName)
        {
            byte[] bytes = Encoding.UTF8.GetBytes(
                $"{head}:{platform}:{rid}:{kind}:{fileName}");
            string digest = Convert.ToHexStringLower(SHA256.HashData(bytes));
            var artifact = new JsonObject
            {
                ["artifactId"] = fileName,
                ["head"] = head,
                ["platform"] = platform,
                ["rid"] = rid,
                ["kind"] = kind,
                ["fileName"] = fileName,
                ["sha256"] = digest,
                ["sizeBytes"] = bytes.LongLength
            };
            artifacts.Add(artifact);
            string path = $"files/{fileName}";
            inventory.Add(
                path,
                new ReleaseUploadCandidateInventoryRow(path, bytes.LongLength, digest));
            return artifact;
        }

        foreach (string head in new[] { "blazor-desktop", "avalonia" })
        {
            AddPrimary(
                head,
                "macos",
                "osx-arm64",
                "installer",
                $"chummer-{head}-osx-arm64-installer.dmg");
            AddPrimary(
                head,
                "macos",
                "osx-arm64",
                "archive",
                $"chummer-{head}-osx-arm64.zip");
        }
        AddPrimary(
            "avalonia",
            "linux",
            "linux-x64",
            "installer",
            "chummer-avalonia-linux-x64-installer.deb");
        JsonObject windows = AddPrimary(
            "avalonia",
            "windows",
            "win-x64",
            "installer",
            "chummer-avalonia-win-x64-installer.exe");
        byte[] payload = "fresh-avalonia-windows-bootstrap-payload"u8.ToArray();
        string payloadDigest = Convert.ToHexStringLower(SHA256.HashData(payload));
        const string payloadFileName = "chummer-avalonia-win-x64-payload.zip";
        windows["installerMode"] = "bootstrap";
        windows["payloadAcquisitionMode"] = "download";
        windows["payloadFileName"] = payloadFileName;
        windows["payloadSha256"] = payloadDigest;
        windows["payloadSizeBytes"] = payload.LongLength;
        inventory.Add(
            $"files/{payloadFileName}",
            new ReleaseUploadCandidateInventoryRow(
                $"files/{payloadFileName}",
                payload.LongLength,
                payloadDigest));

        var canonical = new JsonObject
        {
            ["version"] = "run-cross-platform-shelf",
            ["releaseVersion"] = "run-cross-platform-shelf",
            ["channel"] = "preview",
            ["channelId"] = "preview",
            ["desktopTupleCoverage"] = new JsonObject
            {
                ["requiredDesktopHeads"] = new JsonArray("avalonia")
            },
            ["artifacts"] = artifacts
        };
        var fresh = new JsonArray
        {
            new JsonObject
            {
                ["artifactRole"] = "installer",
                ["head"] = "avalonia",
                ["platform"] = "windows",
                ["rid"] = "win-x64",
                ["path"] = "files/chummer-avalonia-win-x64-installer.exe"
            },
            new JsonObject
            {
                ["artifactRole"] = "bootstrap_payload",
                ["head"] = "avalonia",
                ["platform"] = "windows",
                ["rid"] = "win-x64",
                ["path"] = $"files/{payloadFileName}"
            }
        };
        return (canonical, inventory, fresh);
    }

    private static (
        JsonObject Receipt,
        JsonObject Retained,
        byte[] PackageLock,
        byte[] RetainedBytes) LoadUnsignedProducerDocuments()
    {
        JsonObject authority = JsonNode.Parse(LoadUnsignedCandidateAuthorityV3())?.AsObject()
            ?? throw new InvalidDataException("unsigned v3 authority fixture is invalid");
        JsonArray files = authority["custody"]!
            .AsObject()["unsignedPublicationEvidence"]!
            .AsObject()["files"]!
            .AsArray();
        JsonObject packageLock = UnsignedEvidenceEntry(
            files,
            "provenance/config/package-plane.lock.json");
        JsonObject receipt = UnsignedEvidenceEntry(
            files,
            "provenance/UI_FRESH_PACKAGE_PLANE.generated.json");
        JsonObject retained = UnsignedEvidenceEntry(
            files,
            "provenance/retained-windows-publish-closure/manifest.json");
        byte[] retainedBytes = Convert.FromBase64String(
            retained["base64"]!.GetValue<string>());
        return (
            DecodeUnsignedEmbedded(receipt),
            JsonNode.Parse(retainedBytes)?.AsObject()
                ?? throw new InvalidDataException("unsigned retained fixture is invalid"),
            Convert.FromBase64String(packageLock["base64"]!.GetValue<string>()),
            retainedBytes);
    }

    private static JsonObject UnsignedEvidenceEntry(JsonArray files, string path)
        => files
            .Select(static node => node!.AsObject())
            .Single(entry => string.Equals(
                entry["path"]!.GetValue<string>(),
                path,
                StringComparison.Ordinal));

    private static JsonObject DecodeUnsignedEmbedded(JsonObject entry)
    {
        byte[] bytes = Convert.FromBase64String(
            entry["base64"]!.GetValue<string>());
        return JsonNode.Parse(bytes)?.AsObject()
            ?? throw new InvalidDataException("unsigned embedded fixture is invalid");
    }

    private static void RewriteUnsignedEmbedded(JsonObject entry, byte[] bytes)
    {
        entry["base64"] = Convert.ToBase64String(bytes);
        entry["sha256"] = Convert.ToHexStringLower(SHA256.HashData(bytes));
        entry["sizeBytes"] = bytes.LongLength;
    }

    private static void RebindUnsignedReference(
        JsonObject reference,
        JsonObject entry)
    {
        reference["sha256"] = entry["sha256"]!.GetValue<string>();
        reference["sizeBytes"] = entry["sizeBytes"]!.GetValue<long>();
    }

    private static byte[] TamperUnsignedCandidateAuthorityV3CompositionRelease()
    {
        JsonObject authority = JsonNode.Parse(LoadUnsignedCandidateAuthorityV3())?.AsObject()
            ?? throw new InvalidDataException("unsigned v3 authority fixture is invalid");
        JsonObject custody = authority["custody"]!.AsObject();
        JsonObject candidateEntry =
            custody["registryPrepareCandidateReceipt"]!.AsObject();
        JsonObject candidate = DecodeUnsignedEmbedded(candidateEntry);
        JsonObject composition = candidate["compositionInputDocument"]!.AsObject();
        JsonObject release = composition["release"]!.AsObject();
        composition["release"] = new JsonObject
        {
            ["channel"] = release["channel"]!.DeepClone(),
            ["smuggled"] = true,
            ["version"] = release["version"]!.DeepClone()
        };
        byte[] compositionBytes = Encoding.UTF8.GetBytes(
            composition.ToJsonString(
                new JsonSerializerOptions { WriteIndented = true }) + "\n");
        JsonObject compositionReference = candidate["compositionInput"]!.AsObject();
        compositionReference["sha256"] =
            Convert.ToHexStringLower(SHA256.HashData(compositionBytes));
        compositionReference["sizeBytes"] = compositionBytes.LongLength;
        RewriteUnsignedEmbedded(
            candidateEntry,
            Encoding.UTF8.GetBytes(candidate.ToJsonString() + "\n"));

        JsonObject registryAuthorityEntry =
            custody["registryFinalizeAuthority"]!.AsObject();
        JsonObject registryAuthority = DecodeUnsignedEmbedded(registryAuthorityEntry);
        RebindUnsignedReference(
            registryAuthority["candidateReceipt"]!.AsObject(),
            candidateEntry);
        RebindUnsignedReference(
            registryAuthority["compositionRequest"]!.AsObject(),
            compositionReference);
        RewriteUnsignedEmbedded(
            registryAuthorityEntry,
            Encoding.UTF8.GetBytes(registryAuthority.ToJsonString() + "\n"));

        JsonObject registryReceiptEntry =
            custody["registryFinalizeReceipt"]!.AsObject();
        JsonObject registryReceipt = DecodeUnsignedEmbedded(registryReceiptEntry);
        RebindUnsignedReference(
            registryReceipt["candidateReceipt"]!.AsObject(),
            candidateEntry);
        RebindUnsignedReference(
            registryReceipt["compositionRequest"]!.AsObject(),
            compositionReference);
        RebindUnsignedReference(
            registryReceipt["authority"]!.AsObject(),
            registryAuthorityEntry);
        RewriteUnsignedEmbedded(
            registryReceiptEntry,
            Encoding.UTF8.GetBytes(registryReceipt.ToJsonString() + "\n"));

        JsonObject finalization = custody["registryFinalization"]!.AsObject();
        finalization["candidateReceiptSha256"] =
            candidateEntry["sha256"]!.GetValue<string>();
        finalization["authoritySha256"] =
            registryAuthorityEntry["sha256"]!.GetValue<string>();
        finalization["finalizeReceiptSha256"] =
            registryReceiptEntry["sha256"]!.GetValue<string>();
        return JsonSerializer.SerializeToUtf8Bytes(authority);
    }

    [Theory]
    [InlineData("empty_capture")]
    [InlineData("capture_actor")]
    [InlineData("capture_workflow")]
    [InlineData("capture_run_id_whitespace")]
    [InlineData("capture_artifact_identity")]
    [InlineData("stale_capture")]
    [InlineData("not_native")]
    [InlineData("wine_runner")]
    [InlineData("ready_checkpoint")]
    [InlineData("visual_contract_version")]
    [InlineData("visual_contract_type")]
    [InlineData("empty_runner")]
    [InlineData("blank_runner")]
    [InlineData("artifact_digest")]
    [InlineData("scope_widen")]
    [InlineData("scope_narrow")]
    [InlineData("candidate_artifact_name")]
    [InlineData("export_source")]
    [InlineData("export_heads")]
    [InlineData("capture_heads_empty")]
    [InlineData("capture_heads_extra")]
    [InlineData("capture_receipt_fields")]
    [InlineData("capture_progress_path")]
    [InlineData("capture_screenshot_extra")]
    [InlineData("capture_width_type")]
    [InlineData("finalization_contract_type")]
    [InlineData("capture_inventory_root_extra")]
    [InlineData("capture_inventory_empty")]
    [InlineData("finalized_inventory_extra_row")]
    [InlineData("authority_root_extra")]
    [InlineData("candidate_extra")]
    [InlineData("custody_extra")]
    [InlineData("canonical_manifest_path")]
    [InlineData("inventory_path")]
    [InlineData("inventory_root_extra")]
    [InlineData("inventory_row_extra")]
    [InlineData("embedded_entry_extra")]
    [InlineData("visual_screenshot_order")]
    [InlineData("visual_checks_extra")]
    [InlineData("visual_checks_numeric")]
    [InlineData("visual_review_extra")]
    public void RuntimeRejectsFreshlyRehashedSemanticEvidenceTamper(string tamper)
    {
        using var fixture = new SnapshotFixture();
        byte[] authority = TamperCandidateAuthority(
            SnapshotFixture.BuildCandidateAuthority(),
            tamper);

        fixture.Publish("candidate_import_ready", authority);

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();
        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Theory]
    [InlineData("candidateProducer")]
    [InlineData("nativeCapture")]
    public void RuntimeRequiresIndependentFinalReviewOwner(string actorField)
    {
        using var fixture = new SnapshotFixture();
        JsonObject authority = JsonNode.Parse(SnapshotFixture.BuildCandidateAuthority())?.AsObject()
            ?? throw new InvalidDataException("candidate fixture authority is invalid");
        JsonObject actors = authority["custody"]!["finalizedPublicationEvidence"]!["actors"]!
            .AsObject();
        actors[actorField] = actors["scopeApprover"]!.DeepClone();

        fixture.Publish(
            "candidate_import_ready",
            Encoding.UTF8.GetBytes(authority.ToJsonString()));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();
        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Fact]
    public void RuntimeRejectsLegacyCandidateImportAuthorityV1()
    {
        using var fixture = new SnapshotFixture();
        JsonObject authority = JsonNode.Parse(SnapshotFixture.BuildCandidateAuthority())?.AsObject()
            ?? throw new InvalidDataException("candidate fixture authority is invalid");
        authority["contractName"] = "chummer.release-upload.candidate-import-authority/v1";
        authority["contractVersion"] = 1;

        fixture.Publish(
            "candidate_import_ready",
            Encoding.UTF8.GetBytes(authority.ToJsonString()));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();
        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Theory]
    [InlineData("wrapper", "boolean_contract_version")]
    [InlineData("wrapper", "float_contract_version")]
    [InlineData("wrapper", "float_size")]
    [InlineData("nativeFinalization", "boolean_contract_version")]
    [InlineData("nativeFinalization", "float_contract_version")]
    [InlineData("nativeFinalization", "float_size")]
    [InlineData("visualProof", "boolean_contract_version")]
    [InlineData("visualProof", "float_contract_version")]
    [InlineData("visualProof", "float_size")]
    [InlineData("authenticodeVerification", "boolean_contract_version")]
    [InlineData("authenticodeVerification", "float_contract_version")]
    [InlineData("authenticodeVerification", "float_size")]
    public void RuntimeRejectsNativeCompositeNumericEqualityAliases(
        string referenceName,
        string drift)
    {
        using var fixture = new SnapshotFixture();
        JsonObject authority = JsonNode.Parse(SnapshotFixture.BuildCandidateAuthority())?.AsObject()
            ?? throw new InvalidDataException("candidate fixture authority is invalid");
        JsonObject finalized = authority["custody"]!["finalizedPublicationEvidence"]!.AsObject();
        JsonObject scopeEntry = finalized["files"]!.AsArray()
            .Select(static node => node!.AsObject())
            .Single(entry => string.Equals(
                entry["path"]!.GetValue<string>(),
                "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json",
                StringComparison.Ordinal));
        JsonObject scope = JsonNode.Parse(
            Convert.FromBase64String(scopeEntry["base64"]!.GetValue<string>()))!.AsObject();
        JsonObject reference = scope["nativeEvidenceComposite"]![referenceName]!.AsObject();
        reference[drift switch
        {
            "boolean_contract_version" => "contractVersion",
            "float_contract_version" => "contractVersion",
            "float_size" => "sizeBytes",
            _ => throw new ArgumentOutOfRangeException(nameof(drift))
        }] = drift switch
        {
            "boolean_contract_version" => JsonValue.Create(true),
            "float_contract_version" => JsonNode.Parse(
                reference["contractVersion"]!.GetValue<int>().ToString(
                    System.Globalization.CultureInfo.InvariantCulture) + ".0"),
            "float_size" => JsonNode.Parse(
                reference["sizeBytes"]!.GetValue<long>().ToString(
                    System.Globalization.CultureInfo.InvariantCulture) + ".0"),
            _ => throw new ArgumentOutOfRangeException(nameof(drift))
        };
        byte[] scopeBytes = JsonSerializer.SerializeToUtf8Bytes(scope);
        string scopeSha256 = Convert.ToHexStringLower(SHA256.HashData(scopeBytes));
        scopeEntry["base64"] = Convert.ToBase64String(scopeBytes);
        scopeEntry["sha256"] = scopeSha256;
        scopeEntry["sizeBytes"] = scopeBytes.LongLength;
        finalized["publicationScopeSha256"] = scopeSha256;

        fixture.Publish(
            "candidate_import_ready",
            JsonSerializer.SerializeToUtf8Bytes(authority));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();
        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Fact]
    public void MatchingAliasRejectsExplicitNullWhenCompatibilityAliasExists()
    {
        using JsonDocument document = JsonDocument.Parse(
            "{\"version\":null,\"releaseVersion\":\"run-candidate\"}");
        MethodInfo method = typeof(ReleaseUploadSnapshotAuthorityService).GetMethod(
            "RequireMatchingAlias",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("alias validator is unavailable");

        TargetInvocationException rejected = Assert.Throws<TargetInvocationException>(() =>
            method.Invoke(
                null,
                [
                    document.RootElement,
                    "version",
                    "releaseVersion",
                    "candidate release version"
                ]));

        Assert.IsType<InvalidDataException>(rejected.InnerException);
    }

    [Fact]
    public void RuntimeRejectsWidenedBlazorPromotedHeadScope()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish(
            "candidate_import_ready",
            SnapshotFixture.BuildCandidateAuthority(
                includeUndeclaredWindowsArtifacts: true));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();

        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Fact]
    public void RuntimeRejectsExtraRootLevelCandidateInventoryRow()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish(
            "candidate_import_ready",
            SnapshotFixture.BuildCandidateAuthority(
                includeExtraRootInventoryRow: true));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();

        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    [Theory]
    [InlineData("rid")]
    [InlineData("kind")]
    [InlineData("file")]
    public void RuntimeRejectsAllowedHeadWindowsScopeWidening(string drift)
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish(
            "candidate_import_ready",
            SnapshotFixture.BuildCandidateAuthority(
                allowedHeadScopeDrift: drift));

        ReleaseUploadSnapshotAuthority rejected = fixture.Authority.Load();

        Assert.False(rejected.IsValid);
        Assert.Null(rejected.Candidate);
    }

    private static byte[] TamperCandidateAuthority(byte[] payload, string tamper)
    {
        JsonObject authority = JsonNode.Parse(payload)?.AsObject()
            ?? throw new InvalidDataException("candidate fixture authority is invalid");
        JsonObject native = authority["custody"]!["nativeWindowsFinalizedEvidence"]!.AsObject();
        const string capturePath = "WINDOWS_NATIVE_CAPTURE.generated.json";
        const string finalizationPath = "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json";
        const string startupPath = "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json";
        const string visualPath =
            "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json";
        const string exportPath =
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json";

        switch (tamper)
        {
            case "empty_capture":
                RewriteEmbedded(authority, capturePath, new JsonObject());
                break;
            case "capture_actor":
            {
                JsonObject source = native["captureSource"]!.AsObject();
                source["actor"] = "untrusted-capture-actor";
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["source"] = source.DeepClone();
                RewriteEmbedded(authority, capturePath, capture);
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                finalization["captureSource"] = source.DeepClone();
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "capture_workflow":
            {
                JsonObject source = native["captureSource"]!.AsObject();
                source["workflow"] = ".github/workflows/untrusted.yml";
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["source"] = source.DeepClone();
                RewriteEmbedded(authority, capturePath, capture);
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                finalization["captureSource"] = source.DeepClone();
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "capture_run_id_whitespace":
            case "capture_artifact_identity":
            {
                JsonObject source = native["captureSource"]!.AsObject();
                if (tamper == "capture_run_id_whitespace")
                {
                    source["runId"] = "   ";
                }
                else
                {
                    source["artifactName"] = "unbound-capture-artifact";
                }
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["source"] = source.DeepClone();
                RewriteEmbedded(authority, capturePath, capture);
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                finalization["captureSource"] = source.DeepClone();
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "stale_capture":
            {
                string stale = DateTimeOffset.UtcNow.AddDays(-2).ToString("O");
                native["captureGeneratedAtUtc"] = stale;
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["generatedAt"] = stale;
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "not_native":
            {
                JsonObject startup = ReadEmbedded(authority, startupPath);
                startup["executionEnvironment"] = "compatibility_layer";
                startup["nativeHostEvidence"]!["isNativeWindows"] = false;
                RewriteEmbedded(authority, startupPath, startup);
                break;
            }
            case "wine_runner":
            {
                JsonObject startup = ReadEmbedded(authority, startupPath);
                startup["nativeHostEvidence"]!["runner"] = "wine64";
                RewriteEmbedded(authority, startupPath, startup);
                break;
            }
            case "ready_checkpoint":
            {
                JsonObject startup = ReadEmbedded(authority, startupPath);
                startup["readyCheckpoint"] = "post_ui_event_loop";
                RewriteEmbedded(authority, startupPath, startup);
                break;
            }
            case "visual_contract_version":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["contractVersion"] = 2;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "visual_contract_type":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["contractVersion"] = true;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "empty_runner":
            {
                JsonObject startup = ReadEmbedded(authority, startupPath);
                startup["nativeHostEvidence"]!["runner"] = "";
                RewriteEmbedded(authority, startupPath, startup);
                break;
            }
            case "blank_runner":
            {
                JsonObject startup = ReadEmbedded(authority, startupPath);
                startup["nativeHostEvidence"]!["runner"] = "   ";
                RewriteEmbedded(authority, startupPath, startup);
                break;
            }
            case "artifact_digest":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["artifactDigest"] = "sha256:" + new string('f', 64);
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "scope_widen":
            {
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                JsonObject existing = finalization["proofs"]![0]!.AsObject();
                finalization["proofs"]!.AsArray().Add(new JsonObject
                {
                    ["headId"] = "blazor-desktop",
                    ["path"] = existing["path"]!.GetValue<string>(),
                    ["sha256"] = existing["sha256"]!.GetValue<string>()
                });
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "scope_narrow":
            {
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                finalization["proofs"] = new JsonArray();
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "candidate_artifact_name":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["candidate"]!["artifactName"] =
                    "preview-nightly-candidate-99999-1";
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "export_source":
            {
                JsonObject export = ReadEmbedded(authority, exportPath);
                export["source"]!["actor"] = "different-producer";
                RewriteEmbedded(authority, exportPath, export);
                break;
            }
            case "export_heads":
            {
                JsonObject export = ReadEmbedded(authority, exportPath);
                export["heads"]![0]!["installer"]!["sha256"] = new string('f', 64);
                RewriteEmbedded(authority, exportPath, export);
                break;
            }
            case "capture_heads_empty":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["heads"] = new JsonArray();
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "capture_heads_extra":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                JsonArray heads = capture["heads"]!.AsArray();
                heads.Add(heads[0]!.DeepClone());
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "capture_receipt_fields":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["heads"]![0]!["receipt"]!["sizeBytes"] = 1;
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "capture_progress_path":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["heads"]![0]!["progressLog"]!["path"] = startupPath;
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "capture_screenshot_extra":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                JsonArray screenshots = capture["heads"]![0]!["screenshots"]!.AsArray();
                screenshots.Add(screenshots[0]!.DeepClone());
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "capture_width_type":
            {
                JsonObject capture = ReadEmbedded(authority, capturePath);
                capture["heads"]![0]!["screenshots"]![0]!["width"] = true;
                RewriteEmbedded(authority, capturePath, capture);
                break;
            }
            case "finalization_contract_type":
            {
                JsonObject finalization = ReadEmbedded(authority, finalizationPath);
                finalization["contractVersion"] = true;
                RewriteEmbedded(authority, finalizationPath, finalization);
                break;
            }
            case "capture_inventory_root_extra":
            case "capture_inventory_empty":
            {
                JsonObject captureInventory = ReadEmbedded(
                    authority,
                    "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json");
                if (tamper == "capture_inventory_root_extra")
                {
                    captureInventory["unexpected"] = true;
                }
                else
                {
                    captureInventory["files"] = new JsonArray();
                }
                RewriteEmbedded(
                    authority,
                    "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json",
                    captureInventory);
                break;
            }
            case "finalized_inventory_extra_row":
            {
                JsonObject finalizedInventory = ReadEmbedded(
                    authority,
                    "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json");
                finalizedInventory["files"]!.AsArray().Add(new JsonObject
                {
                    ["path"] = "zz-unexpected.bin",
                    ["sha256"] = new string('0', 64),
                    ["sizeBytes"] = 1
                });
                RewriteEmbedded(
                    authority,
                    "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json",
                    finalizedInventory);
                break;
            }
            case "authority_root_extra":
                authority["unexpected"] = true;
                break;
            case "candidate_extra":
                authority["candidate"]!["unexpected"] = true;
                break;
            case "custody_extra":
                authority["custody"]!["unexpected"] = true;
                break;
            case "canonical_manifest_path":
                authority["custody"]!["canonicalManifest"]!["path"] =
                    "renamed-release-channel.json";
                break;
            case "inventory_path":
                authority["custody"]!["inventory"]!["path"] =
                    "renamed-candidate-inventory.json";
                break;
            case "inventory_root_extra":
            {
                JsonObject inventory = ReadCustodyEmbedded(authority, "inventory");
                inventory["unexpected"] = true;
                RewriteCustodyEmbedded(authority, "inventory", inventory);
                break;
            }
            case "inventory_row_extra":
            {
                JsonObject inventory = ReadCustodyEmbedded(authority, "inventory");
                inventory["files"]![0]!["unexpected"] = true;
                RewriteCustodyEmbedded(authority, "inventory", inventory);
                break;
            }
            case "embedded_entry_extra":
                FindEmbedded(authority, capturePath)["unexpected"] = true;
                break;
            case "visual_screenshot_order":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                JsonArray screenshots = visual["screenshots"]!.AsArray();
                JsonNode first = screenshots[0]!.DeepClone();
                screenshots[0] = screenshots[1]!.DeepClone();
                screenshots[1] = first;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "visual_checks_extra":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["checks"]!["unexpected"] = true;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "visual_checks_numeric":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["checks"]!["human_review_confirmed"] = 1;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            case "visual_review_extra":
            {
                JsonObject visual = ReadEmbedded(authority, visualPath);
                visual["readabilityReview"]!["unexpected"] = true;
                RewriteEmbedded(authority, visualPath, visual);
                break;
            }
            default:
                throw new ArgumentOutOfRangeException(nameof(tamper));
        }

        RefreshEvidenceBindings(authority);
        return JsonSerializer.SerializeToUtf8Bytes(authority);
    }

    private static JsonObject ReadEmbedded(JsonObject authority, string path)
    {
        JsonObject entry = FindEmbedded(authority, path);
        byte[] bytes = Convert.FromBase64String(entry["base64"]!.GetValue<string>());
        return JsonNode.Parse(bytes)?.AsObject()
            ?? throw new InvalidDataException("embedded candidate fixture is invalid");
    }

    private static void RewriteEmbedded(JsonObject authority, string path, JsonObject document)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(document);
        JsonObject entry = FindEmbedded(authority, path);
        entry["base64"] = Convert.ToBase64String(bytes);
        entry["sha256"] = Convert.ToHexStringLower(SHA256.HashData(bytes));
        entry["sizeBytes"] = bytes.LongLength;
    }

    private static JsonObject ReadCustodyEmbedded(JsonObject authority, string name)
    {
        JsonObject entry = authority["custody"]![name]!.AsObject();
        byte[] bytes = Convert.FromBase64String(entry["base64"]!.GetValue<string>());
        return JsonNode.Parse(bytes)?.AsObject()
            ?? throw new InvalidDataException("embedded custody fixture is invalid");
    }

    private static void RewriteCustodyEmbedded(
        JsonObject authority,
        string name,
        JsonObject document)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(document);
        JsonObject entry = authority["custody"]![name]!.AsObject();
        entry["base64"] = Convert.ToBase64String(bytes);
        entry["sha256"] = Convert.ToHexStringLower(SHA256.HashData(bytes));
        entry["sizeBytes"] = bytes.LongLength;
    }

    private static JsonObject FindEmbedded(JsonObject authority, string path)
    {
        JsonArray files = authority["custody"]!["nativeWindowsFinalizedEvidence"]!["files"]!.AsArray();
        return files
            .Select(static node => node!.AsObject())
            .Single(entry => string.Equals(
                entry["path"]!.GetValue<string>(),
                path,
                StringComparison.Ordinal));
    }

    private static void RefreshEvidenceBindings(JsonObject authority)
    {
        const string capturePath = "WINDOWS_NATIVE_CAPTURE.generated.json";
        const string captureInventoryPath = "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json";
        const string finalizationPath = "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json";
        const string finalizedInventoryPath = "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json";
        JsonArray files = authority["custody"]!["nativeWindowsFinalizedEvidence"]!["files"]!.AsArray();
        var entries = files
            .Select(static node => node!.AsObject())
            .ToDictionary(
                static entry => entry["path"]!.GetValue<string>(),
                StringComparer.Ordinal);

        JsonObject capture = ReadEmbedded(authority, capturePath);
        if (capture["candidate"] is JsonObject captureCandidate)
        {
            foreach ((string property, string path) in new[]
                     {
                         (
                             "contentInventory",
                             "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json"),
                         (
                             "exportReceipt",
                             "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json")
                     })
            {
                JsonObject entry = entries[path];
                captureCandidate[property] = new JsonObject
                {
                    ["path"] = path,
                    ["sha256"] = entry["sha256"]!.GetValue<string>(),
                    ["sizeBytes"] = entry["sizeBytes"]!.GetValue<long>()
                };
                captureCandidate[$"{property}Sha256"] =
                    entry["sha256"]!.GetValue<string>();
            }
        }
        if (capture["heads"] is JsonArray captureHeads)
        {
            foreach (JsonNode? node in captureHeads)
            {
                JsonObject head = node!.AsObject();
                foreach (string property in new[] { "receipt", "progressLog" })
                {
                    if (head[property] is JsonObject reference
                        && reference["path"] is JsonValue pathValue
                        && entries.TryGetValue(
                            pathValue.GetValue<string>(),
                            out JsonObject? entry))
                    {
                        reference["sha256"] = entry["sha256"]!.GetValue<string>();
                    }
                }
                if (head["screenshots"] is JsonArray screenshots)
                {
                    foreach (JsonNode? screenshotNode in screenshots)
                    {
                        JsonObject screenshot = screenshotNode!.AsObject();
                        string path = screenshot["path"]!.GetValue<string>();
                        if (entries.TryGetValue(path, out JsonObject? entry))
                        {
                            screenshot["sha256"] = entry["sha256"]!.GetValue<string>();
                        }
                    }
                }
            }
        }
        RewriteEmbedded(authority, capturePath, capture);

        JsonObject captureInventory = ReadEmbedded(authority, captureInventoryPath);
        captureInventory["captureManifestSha256"] = entries[capturePath]["sha256"]!.GetValue<string>();
        foreach (JsonNode? node in captureInventory["files"]!.AsArray())
        {
            JsonObject row = node!.AsObject();
            string path = row["path"]!.GetValue<string>();
            if (entries.TryGetValue(path, out JsonObject? entry))
            {
                row["sha256"] = entry["sha256"]!.GetValue<string>();
                row["sizeBytes"] = entry["sizeBytes"]!.GetValue<long>();
            }
        }
        RewriteEmbedded(authority, captureInventoryPath, captureInventory);

        JsonObject finalization = ReadEmbedded(authority, finalizationPath);
        string captureInventorySha256 =
            entries[captureInventoryPath]["sha256"]!.GetValue<string>();
        finalization["captureInventorySha256"] = captureInventorySha256;
        foreach (JsonNode? node in finalization["proofs"]!.AsArray())
        {
            JsonObject proofBinding = node!.AsObject();
            string proofPath = proofBinding["path"]!.GetValue<string>();
            JsonObject proof = ReadEmbedded(authority, proofPath);
            if (capture["source"] is JsonObject refreshedCaptureSource)
            {
                proof["review"]!["captureActor"] =
                    refreshedCaptureSource["actor"]!.GetValue<string>();
                proof["captureBinding"] = new JsonObject
                {
                    ["repository"] = refreshedCaptureSource["repository"]!.GetValue<string>(),
                    ["workflow"] = refreshedCaptureSource["workflow"]!.GetValue<string>(),
                    ["runId"] = refreshedCaptureSource["runId"]!.GetValue<string>(),
                    ["runAttempt"] = refreshedCaptureSource["runAttempt"]!.GetValue<string>(),
                    ["ref"] = refreshedCaptureSource["ref"]!.GetValue<string>(),
                    ["sha"] = refreshedCaptureSource["sha"]!.GetValue<string>(),
                    ["artifactName"] = refreshedCaptureSource["artifactName"]!.GetValue<string>(),
                    ["inventorySha256"] = captureInventorySha256
                };
                RewriteEmbedded(authority, proofPath, proof);
            }
            proofBinding["sha256"] = entries[proofPath]["sha256"]!.GetValue<string>();
        }
        RewriteEmbedded(authority, finalizationPath, finalization);

        JsonObject finalizedInventory = ReadEmbedded(authority, finalizedInventoryPath);
        finalizedInventory["captureInventorySha256"] = captureInventorySha256;
        foreach (JsonNode? node in finalizedInventory["files"]!.AsArray())
        {
            JsonObject row = node!.AsObject();
            string path = row["path"]!.GetValue<string>();
            if (entries.TryGetValue(path, out JsonObject? entry))
            {
                row["sha256"] = entry["sha256"]!.GetValue<string>();
                row["sizeBytes"] = entry["sizeBytes"]!.GetValue<long>();
            }
        }
        RewriteEmbedded(authority, finalizedInventoryPath, finalizedInventory);
    }

    internal sealed class SnapshotFixture : IDisposable
    {
        private static readonly byte[] InstallerBytes = "MZ-avalonia-installer"u8.ToArray();
        private static readonly byte[] PayloadBytes = "PK-avalonia-payload"u8.ToArray();
        private static readonly byte[] BlazorInstallerBytes = "MZ-blazor-installer"u8.ToArray();
        private static readonly byte[] BlazorPayloadBytes = "PK-blazor-payload"u8.ToArray();
        private static readonly string[] BaseOutputNames =
        [
            "HUB_LOCAL_RELEASE_PROOF.generated.json",
            "HUB_SERVED_RELEASE_PROOF.generated.json",
            "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
            "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
            "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
            "RELEASE_CHANNEL.generated.json",
            "FLAGSHIP_PRODUCT_READINESS.generated.json"
        ];
        private readonly string _root;
        private readonly IDataProtectionProvider _protection;

        public SnapshotFixture()
        {
            _root = Path.Combine(
                Path.GetTempPath(),
                "release-upload-snapshot-authority-tests",
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    [PublicProjectionSnapshotService.SnapshotRootConfigurationKey] = _root,
                    [PublicProjectionSnapshotService.SnapshotRequiredConfigurationKey] = "true",
                    ["FLEET_INTERNAL_API_TOKEN"] = "fleet-test-token",
                    ["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(_root, "sessions"),
                    ["CHUMMER_RELEASE_UPLOAD_MIN_FREE_BYTES"] = "0",
                    ["CHUMMER_RELEASE_UPLOAD_MIN_FREE_FRACTION"] = "0"
                })
                .Build();
            _protection = DataProtectionProvider.Create(
                new DirectoryInfo(Path.Combine(_root, "keys")));
            Tickets = new ReleaseUploadTicketService(_protection, Configuration);
            Authority = new ReleaseUploadSnapshotAuthorityService(Configuration);
            Evaluator = new ReleaseUploadAuthorizationEvaluator(
                Configuration,
                Tickets,
                Authority);
            UploadSessions = new ReleaseBundleUploadSessionService(
                Configuration,
                NullLogger<ReleaseBundleUploadSessionService>.Instance);
        }

        public IConfiguration Configuration { get; }
        public ReleaseUploadTicketService Tickets { get; }
        public ReleaseUploadSnapshotAuthorityService Authority { get; }
        public ReleaseUploadAuthorizationEvaluator Evaluator { get; }
        public ReleaseBundleUploadSessionService UploadSessions { get; }

        public ReleaseUploadAuthorizationContext? Evaluate(
            ReleaseUploadCandidateIdentity? candidate = null,
            string bearer = "fleet-test-token",
            bool includeExactScope = true)
        {
            var context = new DefaultHttpContext();
            context.Request.Method = HttpMethods.Post;
            context.Request.Path = "/api/internal/releases/upload-sessions";
            context.Request.Headers.Authorization = $"Bearer {bearer}";
            if (candidate is not null)
            {
                context.Request.Headers[
                    ReleaseUploadAuthorizationEvaluator.CandidateManifestSha256Header] =
                    candidate.CanonicalManifestSha256;
                context.Request.Headers[
                    ReleaseUploadAuthorizationEvaluator.CandidateInventorySha256Header] =
                    candidate.InventorySha256;
                context.Request.Headers[
                    ReleaseUploadAuthorizationEvaluator.CandidateBundleIdentitySha256Header] =
                    candidate.BundleIdentitySha256;
                if (includeExactScope)
                {
                    context.Request.Headers[
                        "X-Chummer-Release-Exact-Incoming-Scope"] =
                        ReleaseUploadSnapshotAuthorityService.CandidateExactIncomingDesktopScope;
                }
            }
            return Evaluator.Evaluate(context.Request);
        }

        public ReleaseUploadTicketIssueResult IssueTicket(string subjectId)
            => Tickets.Issue(new AuthenticatedHubSubject(
                SubjectId: subjectId,
                DisplayName: subjectId,
                Email: $"{subjectId}@example.com",
                Roles: ["operator"],
                AccessToken: "identity-token"));

        public void Publish(string status, byte[]? candidateAuthority = null)
        {
            byte[] local = "{\"status\":\"projection\"}\n"u8.ToArray();
            var payloads = BaseOutputNames.ToDictionary(
                static name => name,
                _ => "{\"status\":\"test\"}\n"u8.ToArray(),
                StringComparer.Ordinal);
            payloads[BaseOutputNames[0]] = local;
            payloads[BaseOutputNames[1]] = local;
            if (status == "candidate_import_ready")
            {
                payloads[ReleaseUploadSnapshotAuthorityService.CandidateAuthorityFileName] =
                    candidateAuthority ?? BuildCandidateAuthority();
            }
            string[] outputNames = payloads.Keys.ToArray();
            var digests = payloads.ToDictionary(
                static pair => pair.Key,
                static pair => Sha256(pair.Value),
                StringComparer.Ordinal);
            string aggregate = SnapshotDigest(outputNames, digests);
            string snapshotId = $"public-projection-{aggregate}";
            string directory = Path.Combine(_root, snapshotId);
            Directory.CreateDirectory(directory);
            foreach ((string name, byte[] payload) in payloads)
            {
                File.WriteAllBytes(Path.Combine(directory, name), payload);
            }
            (string stage, bool code, bool release, bool candidate) = status switch
            {
                "pass" => ("release_upload_ready", true, true, false),
                "review_required" => ("code_deploy_review_required", true, false, false),
                "candidate_import_ready" => ("candidate_import_ready", false, false, true),
                _ => throw new ArgumentOutOfRangeException(nameof(status))
            };
            object[] findings = status switch
            {
                "pass" => [],
                "review_required" =>
                [
                    new
                    {
                        gate = "live public Windows installer",
                        status = "postdeploy_required",
                        reason = "live Windows installer proof must pass after code deployment"
                    }
                ],
                _ =>
                [
                    new
                    {
                        gate = "live release convergence after candidate import",
                        status = "postdeploy_required",
                        reason = "candidate bytes require live verification before release upload authority can be restored"
                    }
                ]
            };
            var common = new Dictionary<string, object?>
            {
                ["status"] = status,
                ["projectionStage"] = stage,
                ["codeDeploymentAuthority"] = code,
                ["releaseUploadAuthority"] = release,
                ["candidateImportAuthority"] = candidate,
                ["releaseGateFindings"] = findings,
                ["snapshotId"] = snapshotId,
                ["snapshotSha256"] = aggregate
            };
            var manifest = new Dictionary<string, object?>(common)
            {
                ["contractName"] = "chummer.public_projection_snapshot/v1",
                ["authorityInputs"] = new Dictionary<string, object?>(),
                ["outputs"] = outputNames.ToDictionary(
                    static name => name,
                    name => (object)new Dictionary<string, object?>
                    {
                        ["relativePath"] = name,
                        ["sha256"] = digests[name],
                        ["sizeBytes"] = payloads[name].LongLength
                    },
                    StringComparer.Ordinal)
            };
            byte[] manifestBytes = JsonSerializer.SerializeToUtf8Bytes(manifest);
            File.WriteAllBytes(
                Path.Combine(directory, "PUBLIC_PROJECTION_SNAPSHOT.generated.json"),
                manifestBytes);
            var pointer = new Dictionary<string, object?>(common)
            {
                ["contractName"] = "chummer.public_projection_current/v1",
                ["manifestRelativePath"] =
                    $"{snapshotId}/PUBLIC_PROJECTION_SNAPSHOT.generated.json",
                ["manifestSha256"] = Sha256(manifestBytes),
                ["outputs"] = outputNames.ToDictionary(
                    static name => name,
                    name => (object)$"{snapshotId}/{name}",
                    StringComparer.Ordinal)
            };
            File.WriteAllBytes(
                Path.Combine(_root, "CURRENT.json"),
                JsonSerializer.SerializeToUtf8Bytes(pointer));
        }

        public string CreateExactBundle(ReleaseUploadCandidateAuthority authority)
        {
            string root = Path.Combine(_root, "exact-bundle");
            Directory.CreateDirectory(root);
            JsonObject generatedAuthority = JsonNode.Parse(BuildCandidateAuthority())?.AsObject()
                ?? throw new InvalidDataException("candidate fixture authority is invalid");
            JsonObject fixtureCustody = generatedAuthority["custody"]!.AsObject();
            byte[] compatibilityBytes = Convert.FromBase64String(
                fixtureCustody["compatibilityManifest"]!["base64"]!.GetValue<string>());
            foreach (ReleaseUploadCandidateInventoryRow row in authority.Inventory)
            {
                string path = Path.Combine(root, row.Path.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                byte[] bytes = row.Path switch
                {
                    "RELEASE_CHANNEL.generated.json" => authority.CanonicalManifestBytes,
                    "releases.json" => compatibilityBytes,
                    "files/chummer-avalonia-win-x64-installer.exe" => InstallerBytes,
                    "files/chummer-avalonia-win-x64-payload.zip" => PayloadBytes,
                    _ => throw new InvalidDataException("unexpected candidate fixture path")
                };
                File.WriteAllBytes(path, bytes);
            }
            return root;
        }

        public string CreateUnsignedExactBundle(
            ReleaseUploadCandidateAuthority authority,
            byte[] authorityBytes)
        {
            string root = Path.Combine(_root, "unsigned-exact-bundle");
            Directory.CreateDirectory(root);
            JsonObject document = JsonNode.Parse(authorityBytes)?.AsObject()
                ?? throw new InvalidDataException("unsigned v3 authority fixture is invalid");
            JsonObject custody = document["custody"]!.AsObject();
            byte[] canonicalBytes = Convert.FromBase64String(
                custody["canonicalManifest"]!["base64"]!.GetValue<string>());
            byte[] compatibilityBytes = Convert.FromBase64String(
                custody["compatibilityManifest"]!["base64"]!.GetValue<string>());
            foreach (ReleaseUploadCandidateInventoryRow row in authority.Inventory)
            {
                string path = Path.Combine(
                    root,
                    row.Path.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                byte[] bytes = row.Path switch
                {
                    "RELEASE_CHANNEL.generated.json" => canonicalBytes,
                    "releases.json" => compatibilityBytes,
                    "files/chummer-avalonia-linux-x64-installer.deb" =>
                        Convert.FromBase64String("bGludXgtcmV0YWluZWQ="),
                    "files/chummer-avalonia-win-x64-installer.exe" =>
                        BuildUnsignedPreviewInstallerBytes(),
                    "files/chummer-avalonia-win-x64-payload.zip" =>
                        Convert.FromBase64String("ZnJlc2gtcGF5bG9hZA=="),
                    "operator-note.txt" =>
                        Convert.FromBase64String("YW5jaWxsYXJ5LXJldGFpbmVk"),
                    _ => throw new InvalidDataException(
                        $"unexpected unsigned candidate fixture path: {row.Path}")
                };
                File.WriteAllBytes(path, bytes);
            }
            return root;
        }

        private static byte[] BuildUnsignedPreviewInstallerBytes()
        {
            byte[] bytes = new byte[512];
            bytes[0] = (byte)'M';
            bytes[1] = (byte)'Z';
            bytes[60] = 0x80;
            bytes[128] = (byte)'P';
            bytes[129] = (byte)'E';
            bytes[148] = 0xe0;
            bytes[152] = 0x0b;
            bytes[153] = 0x01;
            return bytes;
        }

        public static byte[] BuildCandidateAuthority(
            bool includeUndeclaredWindowsArtifacts = false,
            string? allowedHeadScopeDrift = null,
            bool includeExtraRootInventoryRow = false)
        {
            string installerSha = Sha256(InstallerBytes);
            string payloadSha = Sha256(PayloadBytes);
            string blazorInstallerSha = Sha256(BlazorInstallerBytes);
            string blazorPayloadSha = Sha256(BlazorPayloadBytes);
            var manifestArtifacts = new List<object>
            {
                new
                {
                    artifactId = "avalonia-win-x64-installer",
                    head = "avalonia",
                    platform = "windows",
                    rid = "win-x64",
                    arch = "x64",
                    kind = "installer",
                    installerMode = "bootstrap",
                    payloadAcquisitionMode = "download",
                    fileName = "chummer-avalonia-win-x64-installer.exe",
                    sha256 = installerSha,
                    sizeBytes = InstallerBytes.LongLength,
                    payloadFileName = "chummer-avalonia-win-x64-payload.zip",
                    payloadSha256 = payloadSha,
                    payloadSizeBytes = PayloadBytes.LongLength
                }
            };
            if (includeUndeclaredWindowsArtifacts)
            {
                manifestArtifacts.Add(new
                {
                    artifactId = "blazor-desktop-win-x64-installer",
                    head = "blazor-desktop",
                    platform = "windows",
                    rid = "win-x64",
                    arch = "x64",
                    kind = "installer",
                    installerMode = "bootstrap",
                    payloadAcquisitionMode = "download",
                    fileName = "chummer-blazor-desktop-win-x64-installer.exe",
                    sha256 = blazorInstallerSha,
                    sizeBytes = BlazorInstallerBytes.LongLength,
                    payloadFileName = "chummer-blazor-desktop-win-x64-payload.zip",
                    payloadSha256 = blazorPayloadSha,
                    payloadSizeBytes = BlazorPayloadBytes.LongLength
                });
            }
            if (allowedHeadScopeDrift == "rid")
            {
                manifestArtifacts.Add(new
                {
                    artifactId = "avalonia-win-arm64-installer",
                    head = "avalonia",
                    platform = "windows",
                    rid = "win-arm64",
                    arch = "arm64",
                    kind = "installer",
                    installerMode = "bootstrap",
                    payloadAcquisitionMode = "download",
                    fileName = "chummer-avalonia-win-arm64-installer.exe",
                    sha256 = blazorInstallerSha,
                    sizeBytes = BlazorInstallerBytes.LongLength,
                    payloadFileName = "chummer-avalonia-win-arm64-payload.zip",
                    payloadSha256 = blazorPayloadSha,
                    payloadSizeBytes = BlazorPayloadBytes.LongLength
                });
            }
            else if (allowedHeadScopeDrift == "kind")
            {
                manifestArtifacts.Add(new
                {
                    artifactId = "avalonia-win-x64-symbols",
                    head = "avalonia",
                    platform = "windows",
                    rid = "win-x64",
                    arch = "x64",
                    kind = "archive",
                    fileName = "chummer-avalonia-win-x64-symbols.zip",
                    sha256 = blazorPayloadSha,
                    sizeBytes = BlazorPayloadBytes.LongLength
                });
            }
            else if (allowedHeadScopeDrift is not null and not "file")
            {
                throw new ArgumentOutOfRangeException(nameof(allowedHeadScopeDrift));
            }
            byte[] canonical = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "Chummer.Hub.Registry.Contracts",
                version = "run-candidate",
                releaseVersion = "run-candidate",
                channel = "preview",
                channelId = "preview",
                artifacts = manifestArtifacts,
                desktopTupleCoverage = new
                {
                    requiredDesktopHeads = includeUndeclaredWindowsArtifacts
                        ? new[] { "avalonia", "blazor-desktop" }
                        : new[] { "avalonia" }
                }
            });
            string canonicalSha = Sha256(canonical);
            byte[] compatibility = JsonSerializer.SerializeToUtf8Bytes(new
            {
                channel = "preview",
                releaseVersion = "run-candidate",
                artifacts = manifestArtifacts
            });
            var rows = new List<ReleaseUploadCandidateInventoryRow>
            {
                new ReleaseUploadCandidateInventoryRow(
                    "RELEASE_CHANNEL.generated.json",
                    canonical.LongLength,
                    canonicalSha),
                new ReleaseUploadCandidateInventoryRow(
                    "releases.json",
                    compatibility.LongLength,
                    Sha256(compatibility)),
                new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-x64-installer.exe",
                    InstallerBytes.LongLength,
                    installerSha),
                new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-x64-payload.zip",
                    PayloadBytes.LongLength,
                    payloadSha)
            };
            if (includeUndeclaredWindowsArtifacts)
            {
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-blazor-desktop-win-x64-installer.exe",
                    BlazorInstallerBytes.LongLength,
                    blazorInstallerSha));
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-blazor-desktop-win-x64-payload.zip",
                    BlazorPayloadBytes.LongLength,
                    blazorPayloadSha));
            }
            if (allowedHeadScopeDrift == "rid")
            {
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-arm64-installer.exe",
                    BlazorInstallerBytes.LongLength,
                    blazorInstallerSha));
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-arm64-payload.zip",
                    BlazorPayloadBytes.LongLength,
                    blazorPayloadSha));
            }
            else if (allowedHeadScopeDrift == "kind")
            {
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-x64-symbols.zip",
                    BlazorPayloadBytes.LongLength,
                    blazorPayloadSha));
            }
            else if (allowedHeadScopeDrift == "file")
            {
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "files/chummer-avalonia-win-x64-debug.zip",
                    BlazorPayloadBytes.LongLength,
                    blazorPayloadSha));
            }
            if (includeUndeclaredWindowsArtifacts || allowedHeadScopeDrift is not null)
            {
                rows.Sort(static (left, right) => string.CompareOrdinal(left.Path, right.Path));
            }
            string inventorySha =
                ReleaseUploadSnapshotAuthorityService.ComputeInventoryDigest(rows);
            var candidate = new ReleaseUploadCandidateIdentity(
                "run-candidate",
                canonicalSha,
                inventorySha,
                rows.Count,
                rows.Sum(static row => row.SizeBytes),
                string.Empty);
            candidate = candidate with
            {
                BundleIdentitySha256 =
                    ReleaseUploadSnapshotAuthorityService.ComputeBundleIdentity(candidate)
            };
            byte[] inventory = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer.release-upload.candidate-inventory/v1",
                contractVersion = 1,
                files = rows.Select(row => new
                {
                    path = row.Path,
                    sha256 = row.Sha256,
                    sizeBytes = row.SizeBytes
                })
            });
            DateTimeOffset now = DateTimeOffset.UtcNow;
            var captureSource = new Dictionary<string, object?>
            {
                ["repository"] = "ArchonMegalon/chummer6-ui",
                ["workflow"] = ".github/workflows/windows-native-evidence-capture.yml",
                ["runId"] = "12345",
                ["runAttempt"] = "1",
                ["ref"] = "refs/heads/main",
                ["sha"] = new string('a', 40),
                ["actor"] = "github-actions[bot]",
                ["artifactName"] = "windows-native-evidence-12345-1"
            };
            var finalizationSource = new Dictionary<string, object?>
            {
                ["repository"] = "ArchonMegalon/chummer6-ui",
                ["workflow"] = ".github/workflows/windows-native-evidence-finalize.yml",
                ["runId"] = "12345",
                ["runAttempt"] = "1",
                ["ref"] = "refs/heads/main",
                ["sha"] = new string('a', 40),
                ["actor"] = "scope-approver",
                ["artifactName"] = "windows-native-evidence-finalized-12345-1"
            };
            byte[] nativeAuthenticode = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.windows-authenticode-verification",
                contractVersion = 1,
                status = "verified"
            });
            var rawAuthenticodeBinding = new
            {
                path = "authenticode/"
                       + "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json",
                sha256 = Sha256(nativeAuthenticode),
                signerCertificateSha256 = new string('c', 64),
                signerSpkiSha256 = new string('d', 64),
                sizeBytes = nativeAuthenticode.LongLength,
                timestampUtc = now.ToString("O")
            };
            byte[] nativeApproval = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-windows-publication-approval",
                contractVersion = 2,
                status = "approved",
                approver = "scope-approver"
            });
            byte[] provenanceScopeProposal = JsonSerializer.SerializeToUtf8Bytes(new
            {
                registryPrepareSha256 = new string('f', 64),
                scopeDecisionSha256 = new string('d', 64)
            });
            byte[] provenanceSigning = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.desktop_artifact_signing",
                contractVersion = 2,
                signingStatus = "pass"
            });
            var provenanceRows = rows
                .Select(row => new
                {
                    path = row.Path,
                    sha256 = row.Sha256,
                    sizeBytes = row.SizeBytes
                })
                .Concat(
                new[]
                {
                    new
                    {
                        path = "publication-scope/"
                               + "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_PROPOSAL.generated.json",
                        sha256 = Sha256(provenanceScopeProposal),
                        sizeBytes = provenanceScopeProposal.LongLength
                    },
                    new
                    {
                        path = "signing/signing-avalonia-win-x64.receipt.json",
                        sha256 = Sha256(provenanceSigning),
                        sizeBytes = provenanceSigning.LongLength
                    }
                })
                .OrderBy(static row => row.path, StringComparer.Ordinal)
                .ToArray();
            byte[] provenance = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-candidate-content-inventory",
                contractVersion = 2,
                release = new { channel = "preview", version = "run-candidate" },
                manifest = new
                {
                    path = "RELEASE_CHANNEL.generated.json",
                    sha256 = canonicalSha
                },
                files = provenanceRows
            });
            byte[] startup = JsonSerializer.SerializeToUtf8Bytes(new
            {
                status = "pass",
                readyCheckpoint = "pre_ui_event_loop",
                headId = "avalonia",
                platform = "windows",
                rid = "win-x64",
                channelId = "preview",
                releaseVersion = "run-candidate",
                artifactFileName = "chummer-avalonia-win-x64-installer.exe",
                artifactDigest = $"sha256:{installerSha}",
                bootstrapPayloadAcquisitionMode = "download",
                bootstrapPayloadFileName = "chummer-avalonia-win-x64-payload.zip",
                bootstrapPayloadSha256 = payloadSha,
                bootstrapPayloadSizeBytes = PayloadBytes.LongLength,
                executionEnvironment = "native_windows",
                nativeHostEvidence = new
                {
                    contractName = "chummer6-ui.native_windows_host_evidence",
                    status = "verified",
                    isNativeWindows = true,
                    hostPlatform = "windows",
                    hostKernel = "Windows_NT",
                    runner = "powershell.exe",
                    evidenceSource = "GitHub-hosted windows-latest"
                }
            });
            byte[] progressScreenshot = "png-progress"u8.ToArray();
            byte[] completionScreenshot = "png-completion"u8.ToArray();
            byte[] progressLog = "Install complete\n"u8.ToArray();
            const string visualPath =
                "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json";
            byte[] visual = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.windows_installer_visual_proof",
                contractVersion = 1,
                status = "passed",
                generatedAt = now,
                version = "run-candidate",
                releaseVersion = "run-candidate",
                channel = "preview",
                channelId = "preview",
                platform = "windows",
                head = "avalonia",
                headId = "avalonia",
                rid = "win-x64",
                artifactFileName = "chummer-avalonia-win-x64-installer.exe",
                artifactDigest = $"sha256:{installerSha}",
                authenticodeVerification = rawAuthenticodeBinding,
                screenshots = new object[]
                {
                    new
                    {
                        role = "progress",
                        path = "screenshots/windows-installer-avalonia-win-x64-progress.png",
                        sha256 = Sha256(progressScreenshot)
                    },
                    new
                    {
                        role = "completion",
                        path = "screenshots/windows-installer-avalonia-win-x64-completion.png",
                        sha256 = Sha256(completionScreenshot)
                    }
                },
                checks = new
                {
                    capture_mode = "interactive",
                    human_review_confirmed = true
                },
                readabilityReview = new { status = "passed", reviewer = "scope-approver" },
                contrastReview = new { status = "passed", reviewer = "scope-approver" },
                clippingReview = new { status = "passed", reviewer = "scope-approver" },
                finalizationBinding = finalizationSource
            });
            var producerSource = new Dictionary<string, object?>
            {
                ["repository"] = "ArchonMegalon/chummer6-ui",
                ["workflow"] = ".github/workflows/preview-nightly-candidate-export.yml",
                ["runId"] = "900",
                ["runAttempt"] = "1",
                ["ref"] = "refs/heads/main",
                ["sha"] = new string('a', 40),
                ["actor"] = "candidate-producer",
                ["artifactName"] = "preview-nightly-candidate-900-1"
            };
            var exportHead = new
            {
                headId = "avalonia",
                rid = "win-x64",
                installer = new
                {
                    relativePath = "files/chummer-avalonia-win-x64-installer.exe",
                    fileName = "chummer-avalonia-win-x64-installer.exe",
                    sha256 = installerSha,
                    sizeBytes = InstallerBytes.LongLength
                },
                payload = new
                {
                    relativePath = "files/chummer-avalonia-win-x64-payload.zip",
                    fileName = "chummer-avalonia-win-x64-payload.zip",
                    sha256 = payloadSha,
                    sizeBytes = PayloadBytes.LongLength
                }
            };
            var exportSource = new Dictionary<string, object?>(producerSource)
            {
                ["runnerLabel"] = "chummer-preview-nightly-export-abcdefghijkl"
            };
            byte[] export = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-candidate-export",
                contractVersion = 2,
                status = "exported",
                release = new { channel = "preview", version = "run-candidate" },
                candidateManifest = new
                {
                    path = "RELEASE_CHANNEL.generated.json",
                    sha256 = canonicalSha
                },
                contentInventory = new
                {
                    path = "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json",
                    sha256 = Sha256(provenance)
                },
                source = exportSource,
                heads = new[] { exportHead },
                publicationScope = new { registryPrepareSha256 = new string('f', 64) },
                supplyChain = new { },
                supplyChainVerification = new
                {
                    mode = "release_authoritative",
                    releaseAuthoritative = true
                }
            });
            if (includeExtraRootInventoryRow)
            {
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    "UNEXPECTED.generated.json",
                    3,
                    Sha256("{}\n"u8.ToArray())));
            }
            rows.Sort(static (left, right) => string.CompareOrdinal(left.Path, right.Path));
            inventorySha = ReleaseUploadSnapshotAuthorityService.ComputeInventoryDigest(rows);
            candidate = new ReleaseUploadCandidateIdentity(
                "run-candidate",
                canonicalSha,
                inventorySha,
                rows.Count,
                rows.Sum(static row => row.SizeBytes),
                string.Empty);
            candidate = candidate with
            {
                BundleIdentitySha256 =
                    ReleaseUploadSnapshotAuthorityService.ComputeBundleIdentity(candidate)
            };
            inventory = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer.release-upload.candidate-inventory/v1",
                contractVersion = 1,
                files = rows.Select(row => new
                {
                    path = row.Path,
                    sha256 = row.Sha256,
                    sizeBytes = row.SizeBytes
                })
            });
            string artifactCreatedAt = now.AddMinutes(-1).ToString(
                "yyyy-MM-dd'T'HH:mm:ss'Z'",
                System.Globalization.CultureInfo.InvariantCulture);
            string artifactExpiresAt = now.AddDays(14).ToString(
                "yyyy-MM-dd'T'HH:mm:ss'Z'",
                System.Globalization.CultureInfo.InvariantCulture);
            const string artifactId = "503";
            string artifactSha = new('d', 64);
            var handoff = new Dictionary<string, object?>(producerSource)
            {
                ["contractName"] = "chummer6-ui.preview-nightly-candidate-handoff",
                ["contractVersion"] = 1,
                ["artifactId"] = artifactId,
                ["artifactSha256"] = artifactSha,
                ["contentInventorySha256"] = Sha256(provenance)
            };
            var authenticatedApi = new Dictionary<string, object?>(producerSource)
            {
                ["contractName"] = "chummer6-ui.preview-nightly-candidate-authenticated-api",
                ["contractVersion"] = 1,
                ["artifactId"] = artifactId,
                ["artifactSha256"] = artifactSha,
                ["artifactCreatedAt"] = artifactCreatedAt,
                ["artifactExpiresAt"] = artifactExpiresAt,
                ["event"] = "workflow_dispatch",
                ["status"] = "completed",
                ["conclusion"] = "success"
            };
            var captureCandidate = new Dictionary<string, object?>(producerSource)
            {
                ["artifactId"] = artifactId,
                ["artifactSha256"] = artifactSha,
                ["artifactCreatedAt"] = artifactCreatedAt,
                ["artifactExpiresAt"] = artifactExpiresAt,
                ["manifestPath"] = "RELEASE_CHANNEL.generated.json",
                ["manifestSha256"] = canonicalSha,
                ["contentInventorySha256"] = Sha256(provenance),
                ["exportReceiptSha256"] = Sha256(export),
                ["handoffSha256"] = Sha256(JsonSerializer.SerializeToUtf8Bytes(handoff)),
                ["authenticatedApiSha256"] = Sha256(
                    JsonSerializer.SerializeToUtf8Bytes(authenticatedApi)),
                ["contentInventory"] = new
                {
                    path = CandidateProvenanceInventoryPath,
                    sha256 = Sha256(provenance),
                    sizeBytes = provenance.LongLength
                },
                ["exportReceipt"] = new
                {
                    path = CandidateProvenanceExportPath,
                    sha256 = Sha256(export),
                    sizeBytes = export.LongLength
                },
                ["fullShelfManifest"] = new
                {
                    path = "candidate-provenance/RELEASE_CHANNEL.generated.json",
                    sha256 = canonicalSha,
                    sizeBytes = canonical.LongLength
                },
                ["fullShelfManifestPath"] = "RELEASE_CHANNEL.generated.json",
                ["fullShelfManifestSha256"] = canonicalSha,
                ["fullShelfCompatibilityManifest"] = new
                {
                    path = "candidate-provenance/releases.json",
                    sha256 = Sha256(compatibility),
                    sizeBytes = compatibility.LongLength
                },
                ["fullShelfCompatibilityManifestPath"] = "releases.json",
                ["fullShelfCompatibilityManifestSha256"] = Sha256(compatibility),
                ["publicationScope"] = new
                {
                    path = "candidate-provenance/publication-scope/"
                           + "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_PROPOSAL.generated.json",
                    sha256 = Sha256(provenanceScopeProposal),
                    sizeBytes = provenanceScopeProposal.LongLength
                },
                ["publicationScopePath"] = "publication-scope/"
                    + "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_PROPOSAL.generated.json",
                ["publicationScopeSha256"] = Sha256(provenanceScopeProposal),
                ["registryPrepareFiles"] = Array.Empty<object>(),
                ["registryPrepareSha256"] = new string('f', 64),
                ["scopeDecisionSha256"] = new string('d', 64),
                ["signingReceipt"] = new
                {
                    path = "candidate-provenance/signing/"
                           + "signing-avalonia-win-x64.receipt.json",
                    sha256 = Sha256(provenanceSigning),
                    sizeBytes = provenanceSigning.LongLength
                },
                ["signingReceiptPath"] = "signing/signing-avalonia-win-x64.receipt.json",
                ["signingReceiptSha256"] = Sha256(provenanceSigning),
                ["supplyChain"] = new { }
            };
            var captureHead = new
            {
                exportHead.headId,
                exportHead.rid,
                exportHead.installer,
                exportHead.payload,
                authenticodeVerification = rawAuthenticodeBinding,
                receipt = new
                {
                    path = "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
                    sha256 = Sha256(startup)
                },
                progressLog = new
                {
                    path = "startup-smoke/windows-installer-progress-avalonia-win-x64.log",
                    sha256 = Sha256(progressLog)
                },
                screenshots = new object[]
                {
                    new
                    {
                        role = "progress",
                        path = "screenshots/windows-installer-avalonia-win-x64-progress.png",
                        sha256 = Sha256(progressScreenshot),
                        width = 1280,
                        height = 720
                    },
                    new
                    {
                        role = "completion",
                        path = "screenshots/windows-installer-avalonia-win-x64-completion.png",
                        sha256 = Sha256(completionScreenshot),
                        width = 1280,
                        height = 720
                    }
                }
            };
            byte[] capture = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-native-windows-capture",
                contractVersion = 2,
                status = "captured",
                captureMode = "interactive",
                generatedAt = now,
                version = "run-candidate",
                channelId = "preview",
                source = captureSource,
                candidate = captureCandidate,
                authenticodeVerification = rawAuthenticodeBinding,
                heads = new[] { captureHead }
            });
            var captureSubjects = new (string Path, byte[] Bytes)[]
                {
                    ("WINDOWS_NATIVE_CAPTURE.generated.json", capture),
                    (
                        "authenticode/"
                        + "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json",
                        nativeAuthenticode),
                    (CandidateProvenanceInventoryPath, provenance),
                    (CandidateProvenanceExportPath, export),
                    ("candidate-provenance/RELEASE_CHANNEL.generated.json", canonical),
                    (
                        "candidate-provenance/files/"
                        + "chummer-avalonia-win-x64-installer.exe",
                        InstallerBytes),
                    (
                        "candidate-provenance/files/"
                        + "chummer-avalonia-win-x64-payload.zip",
                        PayloadBytes),
                    (
                        "candidate-provenance/publication-scope/"
                        + "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_PROPOSAL.generated.json",
                        provenanceScopeProposal),
                    ("candidate-provenance/releases.json", compatibility),
                    (
                        "candidate-provenance/signing/"
                        + "signing-avalonia-win-x64.receipt.json",
                        provenanceSigning),
                    (
                        "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
                        startup),
                    (
                        "startup-smoke/windows-installer-progress-avalonia-win-x64.log",
                        progressLog),
                    (
                        "screenshots/windows-installer-avalonia-win-x64-progress.png",
                        progressScreenshot),
                    (
                        "screenshots/windows-installer-avalonia-win-x64-completion.png",
                        completionScreenshot)
                };
            object[] captureInventoryRows = captureSubjects
                .OrderBy(static row => row.Path, StringComparer.Ordinal)
                .Select(row => (object)new
                {
                    path = row.Path,
                    sha256 = Sha256(row.Bytes),
                    sizeBytes = row.Bytes.LongLength
                })
                .ToArray();
            byte[] captureInventory = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-native-windows-capture-inventory",
                contractVersion = 2,
                captureContract = "chummer6-ui.preview-nightly-native-windows-capture",
                captureManifestSha256 = Sha256(capture),
                files = captureInventoryRows
            });
            JsonObject visualDocument = JsonNode.Parse(visual)!.AsObject();
            visualDocument["review"] = JsonSerializer.SerializeToNode(new
            {
                authenticatedReviewer = "scope-approver",
                captureActor = "github-actions[bot]",
                allowlistSource = "repository variable plus protected environment",
                explicitConfirmations = new
                {
                    readability = "passed",
                    contrast = "passed",
                    clipping = "passed"
                }
            });
            visualDocument["captureBinding"] = JsonSerializer.SerializeToNode(new
            {
                repository = captureSource["repository"],
                workflow = captureSource["workflow"],
                runId = captureSource["runId"],
                runAttempt = captureSource["runAttempt"],
                @ref = captureSource["ref"],
                sha = captureSource["sha"],
                artifactName = captureSource["artifactName"],
                inventorySha256 = Sha256(captureInventory)
            });
            visual = JsonSerializer.SerializeToUtf8Bytes(visualDocument);
            byte[] finalization = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-native-windows-finalization",
                contractVersion = 2,
                status = "passed",
                generatedAt = now,
                captureInventorySha256 = Sha256(captureInventory),
                captureSource,
                finalizationSource,
                reviewer = "scope-approver",
                reviewerWasCaptureActor = false,
                humanReviewConfirmed = true,
                authenticodeVerification = rawAuthenticodeBinding,
                proofs = new object[]
                {
                    new { headId = "avalonia", path = visualPath, sha256 = Sha256(visual) }
                },
                scopeApproval = new
                {
                    approver = "scope-approver",
                    path = "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json",
                    scopeDecisionSha256 = new string('d', 64),
                    sha256 = Sha256(nativeApproval)
                }
            });
            var evidence = new Dictionary<string, byte[]>(StringComparer.Ordinal)
            {
                ["WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json"] = captureInventory,
                ["WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json"] = finalization,
                ["PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json"] =
                    nativeApproval,
                [visualPath] = visual,
            };
            foreach ((string path, byte[] bytes) in captureSubjects)
            {
                evidence[path] = bytes;
            }
            object[] finalizedRows = captureSubjects
                .Concat(
                [
                    (Path: visualPath, Bytes: visual),
                    (
                        Path: "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json",
                        Bytes: nativeApproval),
                    (
                        Path: "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json",
                        Bytes: captureInventory),
                    (
                        Path: "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json",
                        Bytes: finalization)
                ])
                .OrderBy(static subject => subject.Path, StringComparer.Ordinal)
                .Select(subject => (object)new
                {
                    path = subject.Path,
                    sha256 = Sha256(subject.Bytes),
                    sizeBytes = subject.Bytes.LongLength
                })
                .ToArray();
            byte[] finalizedInventory = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer6-ui.preview-nightly-native-windows-finalized-inventory",
                contractVersion = 1,
                captureInventorySha256 = Sha256(captureInventory),
                files = finalizedRows
            });
            evidence["WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json"] = finalizedInventory;
            using JsonDocument provenanceDocument = JsonDocument.Parse(provenance);
            var sourceReceipt = new
            {
                contractName = "fixture.desktop-source",
                contractVersion = 1,
                path = "receipts/fixture.json",
                sha256 = new string('e', 64)
            };
            var installerTuple = new
            {
                artifactRole = "installer",
                consumerCommit = new string('a', 40),
                fileName = "chummer-avalonia-win-x64-installer.exe",
                head = "avalonia",
                manifestRowSha256 = new string('1', 64),
                path = "files/chummer-avalonia-win-x64-installer.exe",
                platform = "windows",
                rid = "win-x64",
                sha256 = installerSha,
                sizeBytes = InstallerBytes.LongLength,
                sourceReceipt
            };
            var payloadTuple = new
            {
                artifactRole = "payload",
                consumerCommit = new string('a', 40),
                fileName = "chummer-avalonia-win-x64-payload.zip",
                head = "avalonia",
                manifestRowSha256 = new string('2', 64),
                path = "files/chummer-avalonia-win-x64-payload.zip",
                platform = "windows",
                rid = "win-x64",
                sha256 = payloadSha,
                sizeBytes = PayloadBytes.LongLength,
                sourceReceipt
            };
            object[] deltaTuples = [installerTuple, payloadTuple];
            object[] fullShelfInventory = rows.Select(row => (object)new
            {
                mode = 420,
                path = row.Path,
                sha256 = row.Sha256,
                sizeBytes = row.SizeBytes
            }).ToArray();
            object[] registryInventory = rows.Select(row => (object)new
            {
                mode = "0644",
                path = row.Path,
                sha256 = row.Sha256,
                sizeBytes = row.SizeBytes
            }).ToArray();
            var projectionInputs = new
            {
                materializer = Reference(
                    "scripts/materialize_preview_publication_delta.py",
                    "materializer"u8.ToArray()),
                releaseChannelMaterializer = Reference(
                    "scripts/materialize_public_release_channel.py",
                    "release-channel"u8.ToArray()),
                schema = Reference(
                    "contracts/preview-publication-delta-v1.schema.json",
                    "schema"u8.ToArray()),
                verifier = Reference(
                    "scripts/verify_public_release_channel.py",
                    "verifier"u8.ToArray())
            };
            byte[] compositionBytes = "{\"scope\":\"windows_only\"}"u8.ToArray();
            byte[] registryCandidate = JsonSerializer.SerializeToUtf8Bytes(new
            {
                canonicalManifest = Reference("RELEASE_CHANNEL.generated.json", canonical),
                channel = "preview",
                compatibilityManifest = Reference("releases.json", compatibility),
                compositionInput = Reference("composition.json", compositionBytes),
                compositionInputDocument = new { scope = "windows_only" },
                contractName = "chummer.registry.preview-publication-delta-candidate",
                contractVersion = 1,
                deltaPlatforms = new[] { "windows" },
                deployAuthority = false,
                evidencePlatforms = new[] { "linux" },
                fullShelfInventory = registryInventory,
                fullShelfInventorySha256 = new string('3', 64),
                incumbentDesktopTupleSetSha256 = new string('4', 64),
                incumbentCanonicalManifestBytesBase64 = Convert.ToBase64String("incumbent"u8),
                incumbentSnapshotSha256 = new string('5', 64),
                nonPublishedEvidenceTupleSetSha256 = new string('6', 64),
                postPublicationTupleSetSha256 = new string('7', 64),
                publicationDeltaTupleSetSha256 = new string('8', 64),
                publicationEligible = false,
                publicationStatus = "review_required",
                registryProjectionInputs = projectionInputs,
                releaseUploadAuthority = false,
                routeAuthority = false,
                releaseVersion = "run-candidate",
                retainedPlatforms = Array.Empty<string>(),
                retainedTupleSetSha256 = new string('9', 64),
                shelfPlatforms = new[] { "windows" }
            });
            byte[] finalSigning = provenanceSigning;
            byte[] finalAuthenticode = nativeAuthenticode;
            byte[] finalApproval = nativeApproval;
            Dictionary<string, object?> finalCaptureSource = captureSource;
            Dictionary<string, object?> finalizationSourceV2 = finalizationSource;
            var finalAuthenticodeBinding = new
            {
                path = "proof/windows-native/authenticode/"
                       + "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json",
                rawAuthenticodeBinding.sha256,
                rawAuthenticodeBinding.signerCertificateSha256,
                rawAuthenticodeBinding.signerSpkiSha256,
                sizeBytes = finalAuthenticode.LongLength,
                rawAuthenticodeBinding.timestampUtc
            };
            byte[] finalVisual = JsonSerializer.SerializeToUtf8Bytes(new
            {
                artifactDigest = $"sha256:{installerSha}",
                artifactFileName = "chummer-avalonia-win-x64-installer.exe",
                authenticodeVerification = finalAuthenticodeBinding,
                captureBinding = new
                {
                    artifactName = finalCaptureSource["artifactName"],
                    inventorySha256 = Sha256(captureInventory),
                    @ref = finalCaptureSource["ref"],
                    repository = finalCaptureSource["repository"],
                    runAttempt = finalCaptureSource["runAttempt"],
                    runId = finalCaptureSource["runId"],
                    sha = finalCaptureSource["sha"],
                    workflow = finalCaptureSource["workflow"]
                },
                channel = "preview",
                channelId = "preview",
                checks = new
                {
                    capture_mode = "interactive",
                    human_review_confirmed = true
                },
                clippingReview = new { status = "passed", reviewer = "scope-approver" },
                contractName = "chummer6-ui.windows_installer_visual_proof",
                contractVersion = 1,
                contrastReview = new { status = "passed", reviewer = "scope-approver" },
                finalizationBinding = finalizationSourceV2,
                generatedAt = now,
                head = "avalonia",
                headId = "avalonia",
                platform = "windows",
                readabilityReview = new { status = "passed", reviewer = "scope-approver" },
                releaseVersion = "run-candidate",
                review = new
                {
                    allowlistSource = "repository variable plus protected environment",
                    authenticatedReviewer = "scope-approver",
                    captureActor = "github-actions[bot]",
                    explicitConfirmations = new
                    {
                        clipping = "passed",
                        contrast = "passed",
                        readability = "passed"
                    }
                },
                rid = "win-x64",
                screenshots = new object[]
                {
                    new
                    {
                        path = "proof/windows-native/screenshots/"
                               + "windows-installer-avalonia-win-x64-progress.png",
                        role = "progress",
                        sha256 = Sha256(progressScreenshot)
                    },
                    new
                    {
                        path = "proof/windows-native/screenshots/"
                               + "windows-installer-avalonia-win-x64-completion.png",
                        role = "completion",
                        sha256 = Sha256(completionScreenshot)
                    }
                },
                status = "passed",
                version = "run-candidate"
            });
            const string finalSigningPath = "signing/signing-avalonia-win-x64.receipt.json";
            const string finalNativePath = "NATIVE_WINDOWS_EVIDENCE.generated.json";
            const string finalNativeFinalizationPath =
                "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json";
            const string finalAuthenticodePath =
                "proof/windows-native/authenticode/"
                + "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json";
            const string finalApprovalPath =
                "proof/windows-native/"
                + "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json";
            const string finalVisualPath =
                "WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-win-x64.generated.json";
            byte[] finalNativeFinalization = finalization;
            byte[] finalNative = JsonSerializer.SerializeToUtf8Bytes(new
            {
                archivePath = "proof/windows-native/windows-native-evidence-finalized.zip",
                archiveSha256 = new string('1', 64),
                authenticodeVerification = finalAuthenticodeBinding,
                candidateProvenance = new { candidate = captureCandidate },
                captureInventorySha256 = Sha256(captureInventory),
                captureSource = finalCaptureSource,
                contractName = "chummer6-ui.preview-nightly-native-windows-evidence",
                contractVersion = 1,
                fileCount = 12,
                finalizationSha256 = Sha256(finalNativeFinalization),
                finalizationSource = finalizationSourceV2,
                finalizedInventorySha256 = new string('2', 64),
                githubActionsProvenance = new { },
                nativeFinalization = Reference(
                    finalNativeFinalizationPath,
                    finalNativeFinalization),
                progressLogSha256 = new { avalonia = new string('3', 64) },
                release = new { channel = "preview", version = "run-candidate" },
                scopeApproval = new
                {
                    approver = "scope-approver",
                    path = "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json",
                    payload = new { },
                    scopeDecisionSha256 = new string('d', 64),
                    sha256 = Sha256(finalApproval)
                },
                startupReceiptSha256 = new { avalonia = new string('4', 64) },
                status = "passed",
                treeSha256 = new string('5', 64),
                visualProof = Reference(finalVisualPath, finalVisual),
                visualProofSha256 = new { avalonia = Sha256(finalVisual) },
                visualReviewers = new { avalonia = "scope-approver" }
            });
            var registryPrepare = new
            {
                candidateReceiptSha256 = Sha256(registryCandidate),
                composition = Reference("composition.json", compositionBytes),
                contractName = "chummer6-ui.registry-preview-prepare-binding",
                contractVersion = 1,
                deployAuthority = false,
                finalizeAvailable = true,
                finalizeReceipt = (object?)null,
                inputRoots = new { },
                outputInventory = Array.Empty<object>(),
                outputInventorySha256 = new string('a', 64),
                projectionInputs,
                publicationEligible = false,
                registryCommit = new string('b', 40),
                releaseUploadAuthority = false,
                routeAuthority = false,
                status = "review_required",
                wholeDirectoryVerified = true
            };
            byte[] publicationScope = JsonSerializer.SerializeToUtf8Bytes(new
            {
                approval = new
                {
                    approver = "scope-approver",
                    path = finalApprovalPath,
                    sha256 = Sha256(finalApproval)
                },
                approvalIndependent = true,
                authenticodeRequired = true,
                authenticodeVerificationSha256 = Sha256(finalAuthenticode),
                buildEvidenceTuples = deltaTuples,
                contractName = "chummer6-ui.preview-nightly-windows-publication-scope",
                contractVersion = 2,
                deployAuthorized = false,
                fullShelfCompatibilityManifestSha256 = Sha256(compatibility),
                fullShelfInventory,
                fullShelfInventorySha256 = new string('c', 64),
                fullShelfManifestSha256 = canonicalSha,
                incumbentSnapshot = new { },
                incumbentSnapshotSha256 = new string('5', 64),
                macosSoak = new { required = false },
                nativeEvidenceComposite = new
                {
                    authenticodeVerification = new
                    {
                        contractName = "chummer6-ui.windows-authenticode-verification",
                        contractVersion = 1,
                        path = finalAuthenticodePath,
                        sha256 = Sha256(finalAuthenticode),
                        sizeBytes = finalAuthenticode.LongLength
                    },
                    nativeFinalization = new
                    {
                        contractName = "chummer6-ui.preview-nightly-native-windows-finalization",
                        contractVersion = 2,
                        path = finalNativeFinalizationPath,
                        sha256 = Sha256(finalNativeFinalization),
                        sizeBytes = finalNativeFinalization.LongLength
                    },
                    visualProof = new
                    {
                        contractName = "chummer6-ui.windows_installer_visual_proof",
                        contractVersion = 1,
                        path = finalVisualPath,
                        sha256 = Sha256(finalVisual),
                        sizeBytes = finalVisual.LongLength
                    },
                    wrapper = new
                    {
                        contractName = "chummer6-ui.preview-nightly-native-windows-evidence",
                        contractVersion = 1,
                        path = finalNativePath,
                        sha256 = Sha256(finalNative),
                        sizeBytes = finalNative.LongLength
                    }
                },
                nativeEvidenceSha256 = Sha256(finalNative),
                nonPublishedEvidenceTuples = Array.Empty<object>(),
                postPublicationShelfTuples = deltaTuples,
                publicationDeltaTuples = deltaTuples,
                publicationEligible = false,
                registryPrepare,
                registryFinalizeEligible = true,
                release = new { channel = "preview", version = "run-candidate" },
                retainedTuples = Array.Empty<object>(),
                scopeDecision = new { scope = "windows_only" },
                scopeDecisionSha256 = new string('d', 64),
                signingReceipt = new
                {
                    path = finalSigningPath,
                    sha256 = Sha256(finalSigning)
                },
                signingReceiptSha256 = Sha256(finalSigning),
                status = "validated",
                uploadAuthorized = false,
                visualApprovalSha256 = new[] { Sha256(finalVisual) }
            });
            byte[] registryAuthority = JsonSerializer.SerializeToUtf8Bytes(new
            {
                candidateImportAuthority = true,
                candidateReceipt = Reference(
                    "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json",
                    registryCandidate),
                candidateReviewAuthority = true,
                canonicalManifest = Reference("RELEASE_CHANNEL.generated.json", canonical),
                channel = "preview",
                compatibilityManifest = Reference("releases.json", compatibility),
                compositionInputSha256 = Sha256(compositionBytes),
                contractName = "chummer.registry.preview-publication-delta-authority",
                contractVersion = 1,
                deltaPlatforms = new[] { "windows" },
                deployAuthority = false,
                dispositions = new object[]
                {
                    new
                    {
                        artifactId = "avalonia-win-x64-installer",
                        disposition = "delta",
                        head = "avalonia",
                        platform = "windows",
                        rid = "win-x64",
                        sha256 = installerSha,
                        sizeBytes = InstallerBytes.LongLength,
                        sourceManifestSha256 = canonicalSha,
                        sourceReleaseVersion = "run-candidate",
                        sourceSnapshotSha256 = new string('3', 64)
                    }
                },
                evidence = new
                {
                    approval = Reference(finalApprovalPath, finalApproval),
                    nativeEvidence = Reference(finalNativePath, finalNative),
                    signingReceipt = Reference(finalSigningPath, finalSigning),
                    visualEvidence = new[] { Reference(finalVisualPath, finalVisual) }
                },
                evidencePlatforms = new[] { "linux" },
                fullShelfInventorySha256 = new string('3', 64),
                incumbentSnapshotSha256 = new string('5', 64),
                nonPublishedEvidenceTupleSetSha256 = new string('6', 64),
                postPublicationTupleSetSha256 = new string('7', 64),
                publicationDeltaTupleSetSha256 = new string('8', 64),
                publicationEligible = false,
                releaseUploadAuthority = false,
                releaseVersion = "run-candidate",
                retainedPlatforms = Array.Empty<string>(),
                retainedTupleSetSha256 = new string('9', 64),
                routeAuthority = false,
                scope = "windows_only",
                shelfPlatforms = new[] { "windows" },
                sourceScope = Reference(
                    "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json",
                    publicationScope)
            });
            byte[] registryFinalize = JsonSerializer.SerializeToUtf8Bytes(new
            {
                authority = Reference(
                    "PREVIEW_PUBLICATION_DELTA_AUTHORITY.json",
                    registryAuthority),
                candidateBytesMutated = false,
                candidateImportAuthority = true,
                candidateReceipt = Reference(
                    "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json",
                    registryCandidate),
                candidateReviewAuthority = true,
                canonicalManifest = Reference("RELEASE_CHANNEL.generated.json", canonical),
                channel = "preview",
                compatibilityManifest = Reference("releases.json", compatibility),
                contractName = "chummer.registry.preview-publication-delta-finalize",
                contractVersion = 1,
                deployAuthority = false,
                fullShelfInventorySha256 = new string('3', 64),
                publicationEligible = false,
                releaseUploadAuthority = false,
                releaseVersion = "run-candidate",
                routeAuthority = false,
                sourceScope = Reference(
                    "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json",
                    publicationScope),
                verificationStatus = "finalized"
            });
            return JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer.release-upload.candidate-import-authority/v2",
                contractVersion = 2,
                status = "candidate_import_ready",
                candidateImportAuthority = true,
                candidateReviewAuthority = true,
                publicationEligible = false,
                releaseUploadAuthority = false,
                deployAuthority = false,
                routeAuthority = false,
                exactIncomingDesktopScope = "avalonia:windows:win-x64",
                generatedAtUtc = now,
                expiresAtUtc = now.AddHours(2),
                candidate = new
                {
                    version = candidate.Version,
                    canonicalManifestSha256 = candidate.CanonicalManifestSha256,
                    inventorySha256 = candidate.InventorySha256,
                    fileCount = candidate.FileCount,
                    totalBytes = candidate.TotalBytes,
                    bundleIdentitySha256 = candidate.BundleIdentitySha256
                },
                custody = new
                {
                    canonicalManifest = Embedded("RELEASE_CHANNEL.generated.json", canonical),
                    compatibilityManifest = Embedded("releases.json", compatibility),
                    inventory = Embedded("CANDIDATE_UPLOAD_INVENTORY.generated.json", inventory),
                    nativeWindowsFinalizedEvidence = new
                    {
                        status = "passed",
                        captureGeneratedAtUtc = now,
                        finalizationGeneratedAtUtc = now,
                        reviewer = "scope-approver",
                        captureSource,
                        finalizationSource,
                        candidateContentInventorySha256 = Sha256(provenance),
                        candidateContentInventory = provenanceDocument.RootElement.Clone(),
                        files = evidence
                            .OrderBy(static pair => pair.Key, StringComparer.Ordinal)
                            .Select(pair => Embedded(pair.Key, pair.Value))
                    },
                    finalizedPublicationEvidence = new
                    {
                        status = "passed",
                        exactIncomingDesktopScope = "avalonia:windows:win-x64",
                        publicationScopeSha256 = Sha256(publicationScope),
                        scopeDecisionSha256 = new string('d', 64),
                        signingReceiptSha256 = Sha256(finalSigning),
                        nativeEvidenceSha256 = Sha256(finalNative),
                        authenticodeVerificationSha256 = Sha256(finalAuthenticode),
                        approvalSha256 = Sha256(finalApproval),
                        visualApprovalSha256 = new[] { Sha256(finalVisual) },
                        actors = new
                        {
                            candidateProducer = "candidate-producer",
                            nativeCapture = "github-actions[bot]",
                            visualReviewer = "scope-approver",
                            scopeApprover = "scope-approver"
                        },
                        files = new object[]
                        {
                            Embedded(
                                "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json",
                                publicationScope),
                            Embedded(finalSigningPath, finalSigning),
                            Embedded(finalNativePath, finalNative),
                            Embedded(finalNativeFinalizationPath, finalNativeFinalization),
                            Embedded(finalAuthenticodePath, finalAuthenticode),
                            Embedded(finalApprovalPath, finalApproval),
                            Embedded(finalVisualPath, finalVisual)
                        }
                    },
                    registryPrepareCandidateReceipt = Embedded(
                        "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json",
                        registryCandidate),
                    registryFinalizeAuthority = Embedded(
                        "PREVIEW_PUBLICATION_DELTA_AUTHORITY.json",
                        registryAuthority),
                    registryFinalizeReceipt = Embedded(
                        "PREVIEW_PUBLICATION_DELTA_FINALIZE.json",
                        registryFinalize),
                    registryFinalization = new
                    {
                        status = "finalized",
                        candidateImportAuthority = true,
                        candidateReviewAuthority = true,
                        publicationEligible = false,
                        releaseUploadAuthority = false,
                        deployAuthority = false,
                        routeAuthority = false,
                        scope = "windows_only",
                        exactIncomingDesktopScope = "avalonia:windows:win-x64",
                        candidateReceiptSha256 = Sha256(registryCandidate),
                        authoritySha256 = Sha256(registryAuthority),
                        finalizeReceiptSha256 = Sha256(registryFinalize)
                    }
                }
            });
        }

        private const string CandidateProvenanceInventoryPath =
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json";
        private const string CandidateProvenanceExportPath =
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json";

        private static object Embedded(string path, byte[] payload)
            => new
            {
                path,
                sha256 = Sha256(payload),
                sizeBytes = payload.LongLength,
                @base64 = Convert.ToBase64String(payload)
            };

        private static object Reference(string path, byte[] payload)
            => new
            {
                path,
                sha256 = Sha256(payload),
                sizeBytes = payload.LongLength
            };

        private static string SnapshotDigest(
            IEnumerable<string> names,
            IReadOnlyDictionary<string, string> digests)
        {
            using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            foreach (string name in names)
            {
                hash.AppendData(Encoding.UTF8.GetBytes(name));
                hash.AppendData([0]);
                hash.AppendData(Encoding.ASCII.GetBytes(digests[name]));
                hash.AppendData([(byte)'\n']);
            }
            return Convert.ToHexStringLower(hash.GetHashAndReset());
        }

        private static string Sha256(byte[] payload)
            => Convert.ToHexStringLower(SHA256.HashData(payload));

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private static ReleaseBundlePromotionResult BuildPromotionResult()
        => new(
            Version: "run-candidate",
            Channel: "preview",
            PublishedAt: DateTimeOffset.UtcNow,
            PromotedArtifactIds: [],
            DownloadsUrl: "https://chummer.run/downloads/",
            InstallDispatchUrls: [],
            DirectFileUrls: [],
            GenerationId: "candidate-generation",
            ActivationReceiptId: "candidate-activation",
            InventoryDigest: "sha256:" + new string('a', 64));

    private static ReleaseActivationIntent BuildActivationIntent(ReleaseBundlePromotionResult result)
    {
        byte[] pointer = "candidate-pointer"u8.ToArray();
        return new ReleaseActivationIntent(
            Operation: "promotion",
            PreviousGenerationId: null,
            PreviousPointerSha256: null,
            GenerationId: result.GenerationId!,
            ActivationReceiptId: result.ActivationReceiptId!,
            ReleaseVersion: result.Version,
            Channel: result.Channel,
            PublishedAt: result.PublishedAt,
            InventoryDigest: result.InventoryDigest!,
            PointerSha256: "sha256:" + Convert.ToHexStringLower(SHA256.HashData(pointer)),
            PreparedAtUtc: DateTimeOffset.UtcNow,
            PreviousPointerBase64: null,
            TargetPointerBase64: Convert.ToBase64String(pointer));
    }
}
