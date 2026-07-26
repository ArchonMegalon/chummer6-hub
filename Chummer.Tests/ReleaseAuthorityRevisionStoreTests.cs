using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseAuthorityRevisionStoreTests
{
    private const string CandidateReleaseVersion = "run-20260728-050000";
    private static readonly byte[] ReleaseScopeDecisionBytes = BuildReleaseScopeDecision();
    private static readonly string ReleaseScopeDecisionSha256 = Digest(ReleaseScopeDecisionBytes);

    [Fact]
    public void AdvanceRequestJsonRequiresExactCanonicalFieldsAndBoundedBase64()
    {
        var request = new ReleaseAuthorityRevisionAdvanceRequest(
            "generation-a",
            new string('a', 64),
            new string('b', 64),
            new string('c', 64),
            [9],
            [1],
            [2],
            [3],
            [4],
            [5],
            [6],
            [7],
            [8]);
        string canonical = JsonSerializer.Serialize(request);

        ReleaseAuthorityRevisionAdvanceRequest parsed = Assert.IsType<ReleaseAuthorityRevisionAdvanceRequest>(
            JsonSerializer.Deserialize<ReleaseAuthorityRevisionAdvanceRequest>(canonical));
        Assert.Equal(request.GenerationId, parsed.GenerationId);
        Assert.Equal(request.ConvergenceBytes, parsed.ConvergenceBytes);

        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ReleaseAuthorityRevisionAdvanceRequest>(
            canonical.Insert(canonical.Length - 1, ",\"unexpected\":true")));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ReleaseAuthorityRevisionAdvanceRequest>(
            canonical.Insert(canonical.Length - 1, ",\"generationId\":\"duplicate\"")));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ReleaseAuthorityRevisionAdvanceRequest>(
            canonical.Insert(canonical.Length - 1, ",\"GenerationId\":\"case-shadow\"")));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ReleaseAuthorityRevisionAdvanceRequest>(
            canonical.Replace(
                "\"predecessorCurrentBytes\":\"AQ==\"",
                "\"predecessorCurrentBytes\":\"AQ== \"",
                StringComparison.Ordinal)));
    }

    [Fact]
    public void RollbackRequestJsonRequiresExactCanonicalFields()
    {
        var request = new ReleaseGenerationRollbackRequest(
            "generation-b",
            "generation-a",
            new string('a', 64),
            "auth-" + new string('b', 64),
            "rollback-test-0001");
        string canonical = JsonSerializer.Serialize(request);

        Assert.Equal(
            request,
            JsonSerializer.Deserialize<ReleaseGenerationRollbackRequest>(canonical));
        Assert.Throws<JsonException>(() =>
            JsonSerializer.Deserialize<ReleaseGenerationRollbackRequest>(
                canonical.Insert(canonical.Length - 1, ",\"unexpected\":true")));
        Assert.Throws<JsonException>(() =>
            JsonSerializer.Deserialize<ReleaseGenerationRollbackRequest>(
                canonical.Insert(
                    canonical.Length - 1,
                    ",\"TargetGenerationId\":\"case-shadow\"")));
    }

    [Fact]
    public async Task PrivilegedRollbackRestoresExactRetainedPointerAndIsCasIdempotent()
    {
        using var fixture = new AuthorityFixture();
        fixture.Shelf.WriteGeneration("generation-b", "run-b", "artifact-b");
        fixture.Shelf.Activate("generation-b", "run-b");
        byte[] retainedPointer = File.ReadAllBytes(fixture.Shelf.PointerPath);
        fixture.Shelf.Activate(
            AuthorityFixture.GenerationId,
            CandidateReleaseVersion);

        ReleaseShelfSnapshot active = fixture.ShelfStore.Capture();
        ReleaseAuthorityRevisionAdvanceRequest rebound = fixture.Request with
        {
            ExpectedShelfPointerSha256 =
                Digest(File.ReadAllBytes(fixture.Shelf.PointerPath)),
            ExpectedShelfInventoryDigest = "sha256:" + active.InventoryDigest
        };
        ReleaseAuthorityRevisionAdvanceResult authority =
            await fixture.CreateStore().AdvancePreviewReadyAsync(
                rebound,
                CancellationToken.None);
        var service = new ReleaseBundlePromotionService(
            fixture.Shelf.Configuration,
            NullLogger<ReleaseBundlePromotionService>.Instance,
            promotionCheckpoint: null,
            TimeProvider.System,
            PrivacyLaunchGate.ClearForTests);
        var request = new ReleaseGenerationRollbackRequest(
            "generation-b",
            AuthorityFixture.GenerationId,
            authority.SnapshotSha256,
            authority.RevisionId,
            "rollback-authority-test-0001");

        await Assert.ThrowsAsync<ReleaseShelfMutationConcurrencyException>(() =>
            service.RollbackToGenerationAsync(
                request with
                {
                    ExpectedCurrentSnapshotSha256 = new string('f', 64)
                },
                CancellationToken.None));
        Assert.Equal(
            AuthorityFixture.GenerationId,
            fixture.ShelfStore.Capture().GenerationId);

        ReleaseBundlePromotionResult committed =
            await service.RollbackToGenerationAsync(
                request,
                CancellationToken.None);

        Assert.Equal("generation-b", committed.GenerationId);
        Assert.Equal(retainedPointer, File.ReadAllBytes(fixture.Shelf.PointerPath));
        Assert.Equal("generation-b", fixture.ShelfStore.Capture().GenerationId);

        ReleaseBundlePromotionResult retried =
            await service.RollbackToGenerationAsync(
                request,
                CancellationToken.None);
        Assert.Equal(committed.ActivationReceiptId, retried.ActivationReceiptId);
        Assert.Equal(retainedPointer, File.ReadAllBytes(fixture.Shelf.PointerPath));

        await Assert.ThrowsAsync<ReleaseShelfMutationConcurrencyException>(() =>
            service.RollbackToGenerationAsync(
                request with
                {
                    ExpectedCurrentRevisionId =
                        "auth-" + new string('e', 64)
                },
                CancellationToken.None));
    }

    [Fact]
    public async Task PreviewAdvancePersistsOverlayWithoutChangingSealedGenerationAndResolvesRetainedGeneration()
    {
        using var fixture = new AuthorityFixture();
        Dictionary<string, string> sealedBefore = HashGeneration(fixture.GenerationRoot);

        ReleaseAuthorityRevisionAdvanceResult result = await fixture.CreateStore()
            .AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None);

        Assert.Equal("preview_ready", result.DecisionStatus);
        Assert.False(result.Recovered);
        Assert.Equal(sealedBefore, HashGeneration(fixture.GenerationRoot));
        Assert.StartsWith("auth-", result.RevisionId, StringComparison.Ordinal);

        PublicReleaseTruthProjectionDto current = fixture.Project(fixture.ShelfStore.Capture());
        Assert.Equal("preview_ready", current.ReleaseDecisionStatus);

        fixture.Shelf.WriteGeneration("generation-b", "run-b", "artifact-b");
        fixture.Shelf.Activate("generation-b", "run-b");
        ReleaseShelfSnapshot retained = fixture.ShelfStore.CaptureGeneration(AuthorityFixture.GenerationId);
        PublicReleaseTruthProjectionDto retainedProjection = fixture.Project(retained);
        Assert.Equal("preview_ready", retainedProjection.ReleaseDecisionStatus);
        Assert.Equal(result.SnapshotSha256, retainedProjection.AuthorityBound
            ? Digest(fixture.Successor.SnapshotBytes)
            : string.Empty);
    }

    [Fact]
    public async Task PointerVisibleProcessDeathFailsClosedAndRetryRecoversIdempotently()
    {
        using var fixture = new AuthorityFixture();
        ReleaseAuthorityRevisionStore crashing = fixture.CreateStore(checkpoint =>
        {
            if (checkpoint == ReleaseAuthorityRevisionCheckpoint.PointerReplaced)
            {
                throw new ReleaseAuthorityRevisionProcessTerminationSimulationException(
                    "synthetic process death after authority pointer replacement");
            }
        });

        await Assert.ThrowsAsync<ReleaseAuthorityRevisionProcessTerminationSimulationException>(
            () => crashing.AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None));
        Assert.Throws<InvalidDataException>(() => fixture.Project(fixture.ShelfStore.Capture()));

        DateTimeOffset afterFreshnessWindow = DateTimeOffset.Parse(
            "2026-07-22T20:09:00Z",
            CultureInfo.InvariantCulture);
        ReleaseAuthorityRevisionAdvanceResult recovered = await fixture.CreateStore(
                observedAtUtc: afterFreshnessWindow)
            .AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None);

        Assert.True(recovered.Recovered);
        Assert.Equal("preview_ready", fixture.Project(fixture.ShelfStore.Capture()).ReleaseDecisionStatus);
        ReleaseAuthorityRevisionAdvanceResult repeated = await fixture.CreateStore(
                observedAtUtc: afterFreshnessWindow)
            .AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None);
        Assert.Equal(recovered.RevisionId, repeated.RevisionId);
        Assert.Equal(recovered.JournalReceiptId, repeated.JournalReceiptId);
    }

    [Fact]
    public async Task UncommittedSuccessorCannotFirstCommitAfterFreshnessWindowExpires()
    {
        using var fixture = new AuthorityFixture();

        await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.CreateStore(
                    observedAtUtc: DateTimeOffset.Parse(
                        "2026-07-22T20:09:00Z",
                        CultureInfo.InvariantCulture))
                .AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None));
        Assert.Null(ReleaseAuthorityRevisionStore.TryResolveCommittedRevision(
            fixture.ShelfStore.Capture()));
    }

    [Fact]
    public async Task RevisionVisibleBeforePointerProcessDeathAbortsAndRetryCommits()
    {
        using var fixture = new AuthorityFixture();
        ReleaseAuthorityRevisionStore crashing = fixture.CreateStore(checkpoint =>
        {
            if (checkpoint == ReleaseAuthorityRevisionCheckpoint.RevisionPersisted)
            {
                throw new ReleaseAuthorityRevisionProcessTerminationSimulationException(
                    "synthetic process death before authority pointer replacement");
            }
        });

        await Assert.ThrowsAsync<ReleaseAuthorityRevisionProcessTerminationSimulationException>(
            () => crashing.AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None));
        Assert.Throws<InvalidDataException>(() => fixture.Project(fixture.ShelfStore.Capture()));

        ReleaseAuthorityRevisionAdvanceResult recovered = await fixture.CreateStore()
            .AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None);

        Assert.True(recovered.Recovered);
        Assert.Equal(
            "preview_ready",
            fixture.Project(fixture.ShelfStore.Capture()).ReleaseDecisionStatus);
    }

    [Fact]
    public async Task OrphanJournalIntentBlocksShelfMutationEvenIfActiveBarrierIsRemoved()
    {
        using var fixture = new AuthorityFixture();
        ReleaseAuthorityRevisionStore crashing = fixture.CreateStore(checkpoint =>
        {
            if (checkpoint == ReleaseAuthorityRevisionCheckpoint.IntentPersisted)
            {
                throw new ReleaseAuthorityRevisionProcessTerminationSimulationException(
                    "synthetic process death after journal intent");
            }
        });
        await Assert.ThrowsAsync<ReleaseAuthorityRevisionProcessTerminationSimulationException>(
            () => crashing.AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None));
        string activePath = Path.Combine(
            fixture.Shelf.DownloadsRoot,
            ReleaseAuthorityRevisionStore.AuthorityRootDirectoryName,
            ReleaseAuthorityRevisionStore.AuthorityActiveIntentFileName);
        File.Delete(activePath);

        Assert.Throws<ReleaseShelfMutationConcurrencyException>(
            () => ReleaseAuthorityRevisionStore.EnsureNoUnresolvedAuthorityMutation(
                fixture.Shelf.DownloadsRoot));
    }

    [Fact]
    public async Task PresentButCorruptAuthorityPointerNeverFallsBackToSealedReviewSeed()
    {
        using var fixture = new AuthorityFixture();
        await fixture.CreateStore().AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None);
        string pointerPath = Path.Combine(
            fixture.Shelf.DownloadsRoot,
            ReleaseAuthorityRevisionStore.AuthorityRootDirectoryName,
            ReleaseAuthorityRevisionStore.AuthorityGenerationsDirectoryName,
            AuthorityFixture.GenerationId,
            ReleaseAuthorityRevisionStore.AuthorityCurrentPointerFileName);
        File.WriteAllText(pointerPath, "{}\n");

        Assert.Throws<InvalidDataException>(() => fixture.Project(fixture.ShelfStore.Capture()));
    }

    [Fact]
    public async Task PresentButCorruptAuthorityRevisionNeverFallsBackToSealedReviewSeed()
    {
        using var fixture = new AuthorityFixture();
        ReleaseAuthorityRevisionAdvanceResult result = await fixture.CreateStore()
            .AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None);
        string decisionPath = Path.Combine(
            fixture.Shelf.DownloadsRoot,
            ReleaseAuthorityRevisionStore.AuthorityRootDirectoryName,
            ReleaseAuthorityRevisionStore.AuthorityGenerationsDirectoryName,
            AuthorityFixture.GenerationId,
            ReleaseAuthorityRevisionStore.AuthorityRevisionsDirectoryName,
            result.RevisionId,
            PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath);
        File.WriteAllText(decisionPath, "{}\n");

        Assert.Throws<InvalidDataException>(() => fixture.Project(fixture.ShelfStore.Capture()));
    }

    [Fact]
    public async Task ShelfPointerExpectationMismatchIsReportedAsConcurrency()
    {
        using var fixture = new AuthorityFixture();
        ReleaseAuthorityRevisionAdvanceRequest stale = fixture.Request with
        {
            ExpectedShelfPointerSha256 = new string('0', 64)
        };

        await Assert.ThrowsAsync<ReleaseAuthorityRevisionConcurrencyException>(
            () => fixture.CreateStore().AdvancePreviewReadyAsync(stale, CancellationToken.None));
    }

    [Fact]
    public async Task HandShapedScoreTwoWithoutBoundedOwnerAndActionIsRejected()
    {
        using var fixture = new AuthorityFixture(handShapedScoreTwo: true);

        InvalidDataException error = await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.CreateStore().AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None));

        Assert.Contains("owner/action", error.Message, StringComparison.Ordinal);
        Assert.Null(ReleaseAuthorityRevisionStore.TryResolveCommittedRevision(
            fixture.ShelfStore.Capture()));
    }

    [Fact]
    public async Task DesignGeneratedDuplicateEvidenceActionsAndStableGapsAreAccepted()
    {
        using var fixture = new AuthorityFixture(
            previewScoreTwo: true,
            duplicateEvidenceValues: true);

        ReleaseAuthorityRevisionAdvanceResult result = await fixture.CreateStore()
            .AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None);

        Assert.Equal("preview_ready", result.DecisionStatus);
        Assert.Equal(
            "preview_ready",
            fixture.Project(fixture.ShelfStore.Capture()).ReleaseDecisionStatus);
    }

    [Fact]
    public async Task DesignGeneratedNegativeRawScoreTwoFixtureIsAcceptedUnderExactPreviewProof()
    {
        byte[] fixtureBytes = File.ReadAllBytes(Path.Combine(
            AppContext.BaseDirectory,
            "Fixtures",
            "campaign_operability_score_two_evidence.json"));
        Assert.Equal(
            "a59ee3fa555d9c25c1efbafd189ffa39dc1ad31b63f4b31960421be435143230",
            Digest(fixtureBytes));
        using var fixture = new AuthorityFixture(designGeneratedScoreTwo: true);

        ReleaseAuthorityRevisionAdvanceResult result = await fixture.CreateStore()
            .AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None);

        Assert.Equal("preview_ready", result.DecisionStatus);
        Assert.Equal(
            "preview_ready",
            fixture.Project(fixture.ShelfStore.Capture()).ReleaseDecisionStatus);
    }

    [Fact]
    public async Task DesignFrozenGenericCandidateFixtureIsByteExactAndAcceptedAtAuthority()
    {
        byte[] fixtureBytes = File.ReadAllBytes(Path.Combine(
            AppContext.BaseDirectory,
            "Fixtures",
            "campaign_operability_candidate_evidence.json"));
        Assert.Equal(
            "223fbacac6521dc56ea1a750a835bd865a3dbed6b9181ba5688ed889bf666334",
            Digest(fixtureBytes));
        using var fixture = new AuthorityFixture();

        ReleaseAuthorityRevisionAdvanceResult result = await fixture.CreateStore()
            .AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None);

        Assert.Equal("preview_ready", result.DecisionStatus);
    }

    [Fact]
    public void DesignFrozenCellInventoryIsByteExactAndMatchesAuthorityMap()
    {
        byte[] fixtureBytes = File.ReadAllBytes(Path.Combine(
            AppContext.BaseDirectory,
            "Fixtures",
            "campaign_operability_cell_inventory.json"));
        Assert.Equal(
            "f9efeea2b70f120f9a9ad132c1f16b365acc8257e29c71d676606f7ed617d882",
            Digest(fixtureBytes));
        using JsonDocument fixture = JsonDocument.Parse(fixtureBytes);
        JsonElement root = fixture.RootElement;
        Assert.Equal(
            "chummer.campaign-operability-cell-inventory/v1",
            root.GetProperty("contract_name").GetString());
        Assert.Equal(1, root.GetProperty("contract_version").GetInt32());
        string[] surfaces = root.GetProperty("surface_order").EnumerateArray()
            .Select(static node => node.GetString()!)
            .ToArray();
        string[] dimensions = root.GetProperty("dimension_order").EnumerateArray()
            .Select(static node => node.GetString()!)
            .ToArray();
        JsonElement[] cells = root.GetProperty("cells").EnumerateArray().ToArray();
        Assert.Equal(36, cells.Length);
        int cellIndex = 0;
        foreach (string surface in surfaces)
        {
            foreach (string dimension in dimensions)
            {
                JsonElement cell = cells[cellIndex++];
                Assert.Equal(surface, cell.GetProperty("surface_id").GetString());
                Assert.Equal(dimension, cell.GetProperty("dimension_id").GetString());
                Assert.Equal(
                    ReleaseAuthorityRevisionStore.CampaignOperabilityOwners(surface),
                    cell.GetProperty("owners").EnumerateArray()
                        .Select(static node => node.GetString()!)
                        .ToArray());
                Assert.Equal(
                    ReleaseAuthorityRevisionStore.CampaignOperabilityJourneyIds(surface),
                    cell.GetProperty("journey_ids").EnumerateArray()
                        .Select(static node => node.GetString()!)
                        .ToArray());
                Assert.Equal(
                    ReleaseAuthorityRevisionStore.CampaignOperabilityEvidenceIds(
                        surface,
                        dimension),
                    cell.GetProperty("evidence_ids").EnumerateArray()
                        .Select(static node => node.GetString()!)
                        .ToArray());
            }
        }
    }

    [Theory]
    [InlineData("registry_review_seed")]
    [InlineData("approved_scope_exclusion")]
    public async Task CandidateBoundSpecialScoreTwoProofIsAccepted(string provenanceKind)
    {
        using var fixture = new AuthorityFixture(
            previewScoreTwo: true,
            scorecardMutation: (scorecard, predecessorSnapshotSha256) => ReplaceFirstPreviewProof(
                scorecard,
                provenanceKind,
                predecessorSnapshotSha256));

        ReleaseAuthorityRevisionAdvanceResult result = await fixture.CreateStore()
            .AdvancePreviewReadyAsync(fixture.Request, CancellationToken.None);

        Assert.Equal("preview_ready", result.DecisionStatus);
    }

    [Fact]
    public async Task ScorecardReleaseVersionMustMatchSealedManifest()
    {
        using var fixture = new AuthorityFixture(
            previewScoreTwo: true,
            manifestVersion: "run-20260712-050000");

        await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.CreateStore().AdvancePreviewReadyAsync(
                fixture.Request,
                CancellationToken.None));
    }

    [Fact]
    public async Task ApprovedScopeMustMatchExactCanonicalBytesAndExpectedDigest()
    {
        using var fixture = new AuthorityFixture();
        byte[] noncanonical = [.. fixture.Request.ReleaseScopeDecisionBytes, (byte)' '];
        ReleaseAuthorityRevisionAdvanceRequest request = fixture.Request with
        {
            ReleaseScopeDecisionBytes = noncanonical,
            ExpectedReleaseScopeDecisionSha256 = Digest(noncanonical)
        };

        await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.CreateStore().AdvancePreviewReadyAsync(request, CancellationToken.None));

        request = fixture.Request with
        {
            ExpectedReleaseScopeDecisionSha256 = new string('0', 64)
        };
        await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.CreateStore().AdvancePreviewReadyAsync(request, CancellationToken.None));
    }

    [Theory]
    [InlineData("legacy_contract")]
    [InlineData("unknown_top_field")]
    [InlineData("arbitrary_matrix")]
    [InlineData("cell_sequence")]
    [InlineData("owner_map")]
    [InlineData("journey_map")]
    [InlineData("evidence_map")]
    [InlineData("row_sequence")]
    [InlineData("repeated_row_drift")]
    [InlineData("journey_source_drift")]
    [InlineData("receipt_source_reuse")]
    [InlineData("cell_score_drift")]
    [InlineData("unknown_evidence_field")]
    [InlineData("unresolved_bounded_owner")]
    [InlineData("noncanonical_bounded_owner")]
    [InlineData("missing_next_action")]
    [InlineData("unresolved_next_action")]
    [InlineData("preview_failure")]
    [InlineData("missing_stable_failure")]
    [InlineData("evidence_id_drift")]
    [InlineData("overlapping_declared_ids")]
    [InlineData("preview_owner_drift")]
    [InlineData("cell_gap_drift")]
    [InlineData("summary_drift")]
    [InlineData("stable_alias_lie")]
    [InlineData("top_gap_drift")]
    [InlineData("unresolved_source_status")]
    [InlineData("invented_source_status")]
    [InlineData("blocked_source_status")]
    [InlineData("preview_proof_contract")]
    [InlineData("preview_proof_legacy_v1")]
    [InlineData("preview_proof_release_version")]
    [InlineData("preview_proof_scope")]
    [InlineData("preview_proof_owner")]
    [InlineData("preview_proof_action")]
    [InlineData("preview_proof_digest")]
    [InlineData("preview_source_digest")]
    [InlineData("root_scope_binding_drift")]
    [InlineData("registry_preview_ready")]
    [InlineData("registry_authority_digest")]
    [InlineData("scope_exclusion_platform")]
    [InlineData("missing_generated_at")]
    [InlineData("stale_evidence_row")]
    [InlineData("future_evidence_row")]
    [InlineData("unresolved_source_verdict")]
    [InlineData("review_required_source_verdict")]
    [InlineData("nonportable_evidence_path")]
    [InlineData("nonportable_policy_path")]
    [InlineData("score_three_preview_state")]
    [InlineData("score_three_preview_failure")]
    [InlineData("score_three_candidate_missing")]
    [InlineData("score_three_receipt_candidate_missing")]
    [InlineData("score_three_candidate_source_digest")]
    [InlineData("score_three_candidate_registry_commit")]
    [InlineData("score_three_source_release_version")]
    public async Task ScorecardValidatorRejectsHandShapedOrContradictoryEvidence(string testCase)
    {
        bool stable = testCase.StartsWith("score_three_", StringComparison.Ordinal)
            || testCase is "journey_source_drift" or "receipt_source_reuse"
            || testCase is "blocked_source_status" or "review_required_source_verdict";
        using var fixture = new AuthorityFixture(
            previewScoreTwo: !stable,
            scorecardMutation: (scorecard, predecessorSnapshotSha256) => MutateScorecard(
                scorecard,
                testCase,
                predecessorSnapshotSha256));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.CreateStore().AdvancePreviewReadyAsync(
                fixture.Request,
                CancellationToken.None));
        Assert.Null(ReleaseAuthorityRevisionStore.TryResolveCommittedRevision(
            fixture.ShelfStore.Capture()));
    }

    [Theory]
    [InlineData("missing_current_route")]
    [InlineData("generation_authority_route")]
    [InlineData("stale_convergence")]
    [InlineData("future_convergence")]
    public async Task ConvergenceValidatorRejectsPartialOrStaleProof(string testCase)
    {
        using var fixture = new AuthorityFixture(
            convergenceMutation: convergence => MutateConvergence(convergence, testCase));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => fixture.CreateStore().AdvancePreviewReadyAsync(
                fixture.Request,
                CancellationToken.None));
        Assert.Null(ReleaseAuthorityRevisionStore.TryResolveCommittedRevision(
            fixture.ShelfStore.Capture()));
    }

    private static void MutateConvergence(JsonObject convergence, string testCase)
    {
        switch (testCase)
        {
            case "missing_current_route":
                JsonArray routes = convergence["checkedRoutes"]!.AsArray();
                JsonNode statusRoute = routes.Single(route => route!.GetValue<string>() == "/status")!;
                routes.Remove(statusRoute);
                convergence["checkedRouteCount"] = routes.Count;
                break;
            case "generation_authority_route":
                convergence["authorityRoute"] =
                    "/api/v1/public/release-truth/g/generation-a";
                break;
            case "stale_convergence":
                convergence["generatedAtUtc"] = "2026-07-19T19:00:00Z";
                break;
            case "future_convergence":
                convergence["generatedAtUtc"] = "2026-07-20T20:13:00Z";
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(testCase));
        }
    }

    private static void MutateScorecard(
        JsonObject scorecard,
        string testCase,
        string predecessorSnapshotSha256)
    {
        JsonObject firstCell = scorecard["cells"]!.AsArray()[0]!.AsObject();
        JsonObject firstRow = firstCell["evidence"]!.AsArray()[0]!.AsObject();
        int journeyCount = firstCell["journey_ids"]!.AsArray().Count;
        JsonObject firstReceipt = firstCell["evidence"]!.AsArray()[journeyCount]!.AsObject();
        switch (testCase)
        {
            case "legacy_contract":
                scorecard["contract_version"] = 1;
                break;
            case "unknown_top_field":
                scorecard["claimed_ready"] = true;
                break;
            case "arbitrary_matrix":
                scorecard["required_surfaces"]!.AsArray()[0] = "invented_surface";
                break;
            case "cell_sequence":
                JsonArray cells = scorecard["cells"]!.AsArray();
                JsonNode firstCellClone = cells[0]!.DeepClone();
                cells[0] = cells[1]!.DeepClone();
                cells[1] = firstCellClone;
                break;
            case "owner_map":
                firstCell["owners"]!.AsArray()[0] = "chummer6-hub";
                break;
            case "journey_map":
                firstCell["journey_ids"]!.AsArray()[0] =
                    "report_cluster_release_notify";
                break;
            case "evidence_map":
                firstCell["evidence_ids"]!.AsArray()[0] = "public_route";
                break;
            case "row_sequence":
                JsonArray evidenceRows = firstCell["evidence"]!.AsArray();
                JsonNode firstRowClone = evidenceRows[0]!.DeepClone();
                evidenceRows[0] = evidenceRows[1]!.DeepClone();
                evidenceRows[1] = firstRowClone;
                break;
            case "repeated_row_drift":
                JsonObject repeatedJourney = scorecard["cells"]!.AsArray()[1]!["evidence"]!
                    .AsArray()[0]!.AsObject();
                repeatedJourney["path"] =
                    "products/chummer/evidence/alternate-install-journey.json";
                break;
            case "journey_source_drift":
                JsonObject[] journeyRows = scorecard["cells"]!.AsArray()
                    .SelectMany(static cell => cell!["evidence"]!.AsArray())
                    .Select(static row => row!.AsObject())
                    .Where(static row => row["id"]!.GetValue<string>() ==
                        "install_claim_restore_continue")
                    .ToArray();
                string alternateJourneySha = new string('a', 64);
                foreach (JsonObject row in journeyRows)
                {
                    row["source_sha256"] = alternateJourneySha;
                    row["candidate_evidence"]!["source_receipt_sha256"] =
                        alternateJourneySha;
                }
                break;
            case "receipt_source_reuse":
                JsonObject visualReceipt = scorecard["cells"]!.AsArray()
                    .SelectMany(static cell => cell!["evidence"]!.AsArray())
                    .Select(static row => row!.AsObject())
                    .First(static row => row["id"]!.GetValue<string>() == "desktop_visual");
                string reusedReceiptSha = visualReceipt["source_sha256"]!.GetValue<string>();
                foreach (JsonObject row in scorecard["cells"]!.AsArray()
                             .SelectMany(static cell => cell!["evidence"]!.AsArray())
                             .Select(static row => row!.AsObject())
                             .Where(static row => row["id"]!.GetValue<string>() ==
                                 "desktop_workflow"))
                {
                    row["source_sha256"] = reusedReceiptSha;
                    row["candidate_evidence"]!["source_receipt_sha256"] = reusedReceiptSha;
                }
                break;
            case "cell_score_drift":
                firstCell["score"] = 3;
                break;
            case "unknown_evidence_field":
                firstRow["claimed_valid"] = true;
                break;
            case "unresolved_bounded_owner":
                firstRow["bounded_owner"] = "todo";
                break;
            case "noncanonical_bounded_owner":
                firstRow["bounded_owner"] = "Release-Operations";
                break;
            case "missing_next_action":
                firstRow["next_actions"] = new JsonArray();
                break;
            case "unresolved_next_action":
                firstRow["next_actions"] = new JsonArray("todo");
                break;
            case "preview_failure":
                firstRow["preview_failure"] = "Preview proof is still blocked.";
                break;
            case "missing_stable_failure":
                firstRow["failure"] = string.Empty;
                break;
            case "evidence_id_drift":
                firstRow["id"] = "unbound_evidence";
                break;
            case "overlapping_declared_ids":
                firstCell["evidence_ids"]!.AsArray()[0] =
                    firstCell["journey_ids"]!.AsArray()[0]!.GetValue<string>();
                break;
            case "preview_owner_drift":
                firstCell["preview_owners"] = new JsonArray("different_owner");
                break;
            case "cell_gap_drift":
                firstCell["flagship_gaps"] = new JsonArray("Invented stable gap.");
                firstCell["failures"] = new JsonArray("Invented stable gap.");
                break;
            case "summary_drift":
                scorecard["summary"]!.AsObject()["score_2_count"] = 35;
                break;
            case "stable_alias_lie":
                scorecard["status"] = "pass";
                scorecard["stable_status"] = "pass";
                scorecard["verdict"] = "CAMPAIGN_OPERABILITY_READY";
                scorecard["stable_verdict"] = "CAMPAIGN_OPERABILITY_READY";
                break;
            case "top_gap_drift":
                scorecard["flagship_gaps"] = new JsonArray();
                scorecard["failures"] = new JsonArray();
                break;
            case "unresolved_source_status":
                firstRow["source_status"] = "missing_or_blocked";
                break;
            case "invented_source_status":
                firstRow["source_status"] = "invented";
                break;
            case "blocked_source_status":
                firstRow["source_status"] = "fail";
                break;
            case "preview_proof_contract":
                firstRow["preview_evidence"]!["proof"]!["contract_name"] =
                    "invented.preview_evidence";
                RebindPreviewProofDigest(firstRow);
                break;
            case "preview_proof_legacy_v1":
                firstRow["preview_evidence"]!["proof"]!["contract_version"] = 1;
                firstRow["preview_evidence"]!["proof"]!.AsObject().Remove("release_version");
                firstRow["preview_evidence"]!["proof"]!.AsObject()
                    .Remove("release_scope_decision_sha256");
                RebindPreviewProofDigest(firstRow);
                break;
            case "preview_proof_release_version":
                firstRow["preview_evidence"]!["proof"]!["release_version"] =
                    "run-20260712-050000";
                RebindPreviewProofDigest(firstRow);
                break;
            case "preview_proof_scope":
                firstRow["preview_evidence"]!["proof"]!["release_scope_decision_sha256"] =
                    new string('b', 64);
                RebindPreviewProofDigest(firstRow);
                break;
            case "preview_proof_owner":
                firstRow["bounded_owner"] = "todo";
                firstRow["preview_evidence"]!["proof"]!["bounded_owner"] = "todo";
                RebindPreviewProofDigest(firstRow);
                break;
            case "preview_proof_action":
                firstRow["next_actions"] = new JsonArray("todo");
                firstRow["preview_evidence"]!["proof"]!["next_actions"] =
                    new JsonArray("todo");
                RebindPreviewProofDigest(firstRow);
                break;
            case "preview_proof_digest":
                firstRow["preview_evidence"]!["proof_sha256"] = new string('0', 64);
                break;
            case "preview_source_digest":
                firstRow["preview_evidence"]!["source_receipt_sha256"] =
                    new string('0', 64);
                break;
            case "root_scope_binding_drift":
                scorecard["release_scope_decision_sha256"] = new string('b', 64);
                break;
            case "registry_preview_ready":
                JsonObject registryStatusRow = ReplaceFirstPreviewProof(
                    scorecard,
                    "registry_review_seed",
                    predecessorSnapshotSha256);
                registryStatusRow["preview_evidence"]!["proof"]!["release_decision_status"] =
                    "preview_ready";
                RebindPreviewProofDigest(registryStatusRow);
                break;
            case "registry_authority_digest":
                JsonObject registryDigestRow = ReplaceFirstPreviewProof(
                    scorecard,
                    "registry_review_seed",
                    predecessorSnapshotSha256);
                registryDigestRow["preview_evidence"]!["proof"]!["authority_snapshot_sha256"] =
                    "not-a-digest";
                RebindPreviewProofDigest(registryDigestRow);
                break;
            case "scope_exclusion_platform":
                JsonObject exclusionRow = ReplaceFirstPreviewProof(
                    scorecard,
                    "approved_scope_exclusion",
                    predecessorSnapshotSha256);
                exclusionRow["preview_evidence"]!["proof"]!["excluded_platform"] = "linux";
                RebindPreviewProofDigest(exclusionRow);
                break;
            case "missing_generated_at":
                firstRow["generated_at"] = string.Empty;
                break;
            case "stale_evidence_row":
                firstRow["generated_at"] = "2026-07-19T19:00:00Z";
                break;
            case "future_evidence_row":
                firstRow["generated_at"] = "2026-07-20T20:14:00Z";
                break;
            case "unresolved_source_verdict":
                firstReceipt["source_verdict"] = "unknown";
                break;
            case "review_required_source_verdict":
                firstReceipt["source_verdict"] = "PUBLIC_RELEASE_REVIEW_REQUIRED";
                break;
            case "nonportable_evidence_path":
                firstRow["path"] = "/tmp/hand-shaped.json";
                break;
            case "nonportable_policy_path":
                scorecard["rubric_path"] = "../CAMPAIGN_OPERABILITY_SCORING_RUBRIC.yaml";
                break;
            case "score_three_preview_state":
                firstRow["bounded_owner"] = "invented_owner";
                break;
            case "score_three_preview_failure":
                firstRow["preview_failure"] = "Preview proof is still blocked.";
                break;
            case "score_three_candidate_missing":
                firstRow.Remove("candidate_evidence");
                break;
            case "score_three_receipt_candidate_missing":
                firstReceipt.Remove("candidate_evidence");
                break;
            case "score_three_candidate_source_digest":
                firstRow["candidate_evidence"]!["source_receipt_sha256"] =
                    new string('0', 64);
                break;
            case "score_three_candidate_registry_commit":
                firstRow["candidate_evidence"]!["registry_commit"] =
                    new string('0', 40);
                break;
            case "score_three_source_release_version":
                firstRow["source_release_version"] = "run-20260712-050000";
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(testCase), testCase, null);
        }
    }

    private static Dictionary<string, string> HashGeneration(string root)
        => Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
            .ToDictionary(
                path => Path.GetRelativePath(root, path).Replace(Path.DirectorySeparatorChar, '/'),
                path => Digest(File.ReadAllBytes(path)),
                StringComparer.Ordinal);

    private static string Digest(ReadOnlyMemory<byte> bytes)
        => Convert.ToHexStringLower(SHA256.HashData(bytes.Span));

    private static void RebindPreviewProofDigest(JsonObject evidenceRow)
    {
        JsonNode proof = evidenceRow["preview_evidence"]!["proof"]!;
        evidenceRow["preview_evidence"]!["proof_sha256"] = CanonicalJsonDigest(proof);
    }

    private static JsonObject ReplaceFirstPreviewProof(
        JsonObject scorecard,
        string provenanceKind,
        string predecessorSnapshotSha256)
    {
        string evidenceId = provenanceKind switch
        {
            "registry_review_seed" => "release_channel",
            "approved_scope_exclusion" => "windows_visual",
            _ => throw new ArgumentOutOfRangeException(
                nameof(provenanceKind), provenanceKind, null)
        };
        const string owner = "release-operations";
        string action = provenanceKind == "registry_review_seed"
            ? "Verify live route convergence."
            : "Close the bounded approved-scope visual exclusion.";
        JsonObject? firstRow = null;
        foreach (JsonObject cell in scorecard["cells"]!.AsArray()
                     .Select(static node => node!.AsObject()))
        {
            JsonObject? row = cell["evidence"]!.AsArray()
                .Select(static node => node!.AsObject())
                .SingleOrDefault(candidate => string.Equals(
                    candidate["id"]!.GetValue<string>(),
                    evidenceId,
                    StringComparison.Ordinal));
            if (row is null)
            {
                continue;
            }
            row["bounded_owner"] = owner;
            row["next_actions"] = new JsonArray(action);
            JsonObject proof;
            if (provenanceKind == "registry_review_seed")
            {
                row["source_sha256"] = predecessorSnapshotSha256;
                row["source_status"] = "published";
                proof = new JsonObject
                {
                    ["contract_name"] = "chummer.campaign_operability_registry_review_seed",
                    ["contract_version"] = 1,
                    ["status"] = "published",
                    ["channel"] = "preview",
                    ["rollout_state"] = "promoted_preview",
                    ["supportability_state"] = "preview_supported",
                    ["release_decision_status"] = "review_required",
                    ["release_version"] = CandidateReleaseVersion,
                    ["release_scope_decision_sha256"] = ReleaseScopeDecisionSha256,
                    ["authority_snapshot_sha256"] = predecessorSnapshotSha256,
                    ["bounded_owner"] = owner,
                    ["next_actions"] = new JsonArray(action)
                };
            }
            else
            {
                proof = new JsonObject
                {
                    ["contract_name"] =
                        "chummer.campaign_operability_approved_scope_exclusion",
                    ["contract_version"] = 1,
                    ["status"] = "approved",
                    ["release_version"] = CandidateReleaseVersion,
                    ["release_scope_decision_sha256"] = ReleaseScopeDecisionSha256,
                    ["excluded_platform"] = "windows",
                    ["evidence_id"] = "windows_visual",
                    ["bounded_owner"] = owner,
                    ["next_actions"] = new JsonArray(action)
                };
            }
            row["preview_evidence"]!["provenance_kind"] = provenanceKind;
            row["preview_evidence"]!["source_receipt_sha256"] =
                row["source_sha256"]!.DeepClone();
            row["preview_evidence"]!["proof"] = proof;
            RebindPreviewProofDigest(row);
            firstRow ??= row;

            JsonObject[] scoreTwoRows = cell["evidence"]!.AsArray()
                .Select(static node => node!.AsObject())
                .Where(static candidate => candidate["score"]!.GetValue<int>() == 2)
                .ToArray();
            string[] owners = scoreTwoRows
                .Select(static candidate => candidate["bounded_owner"]!.GetValue<string>())
                .Distinct(StringComparer.Ordinal)
                .OrderBy(static value => value, StringComparer.Ordinal)
                .ToArray();
            cell["preview_owners"] = JsonSerializer.SerializeToNode(owners);
            var aggregateActions = new JsonArray();
            foreach (string nextAction in scoreTwoRows
                         .SelectMany(static candidate => candidate["next_actions"]!.AsArray())
                         .Select(static node => node!.GetValue<string>())
                         .Distinct(StringComparer.Ordinal))
            {
                aggregateActions.Add(nextAction);
            }
            cell["next_actions"] = aggregateActions;
        }
        return firstRow ?? throw new InvalidDataException(
            $"The canonical scorecard does not contain {evidenceId}.");
    }

    private static string CanonicalJsonDigest(JsonNode node)
    {
        using JsonDocument document = JsonDocument.Parse(node.ToJsonString());
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream, new JsonWriterOptions
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            Indented = false
        }))
        {
            WriteCanonicalJson(writer, document.RootElement);
        }
        return Digest(stream.ToArray());
    }

    private static byte[] BuildReleaseScopeDecision()
    {
        var decision = new JsonObject
        {
            ["contractName"] = "chummer.release-scope-decision/v1",
            ["contractVersion"] = 1,
            ["decisionId"] = "scope-run-20260728-050000",
            ["status"] = "approved",
            ["approvedAtUtc"] = "2026-07-20T19:55:00Z",
            ["approvedBy"] = "Release authority",
            ["releaseVersion"] = CandidateReleaseVersion,
            ["channel"] = "preview",
            ["releaseTarget"] = "preview",
            ["supportOwner"] = "release-operations",
            ["platforms"] = new JsonArray
            {
                new JsonObject
                {
                    ["platform"] = "linux",
                    ["rid"] = "linux-x64",
                    ["primaryHead"] = "avalonia",
                    ["fallbackHeads"] = new JsonArray(),
                    ["artifactAccessClass"] = "open_public",
                    ["signingRequirement"] = "not_applicable"
                }
            }
        };
        using JsonDocument document = JsonDocument.Parse(decision.ToJsonString());
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream, new JsonWriterOptions
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            Indented = false
        }))
        {
            WriteCanonicalJson(writer, document.RootElement);
        }
        stream.WriteByte((byte)'\n');
        return stream.ToArray();
    }

    private static void WriteCanonicalJson(Utf8JsonWriter writer, JsonElement element)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (JsonProperty property in element.EnumerateObject()
                             .OrderBy(static property => property.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(property.Name);
                    WriteCanonicalJson(writer, property.Value);
                }
                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (JsonElement item in element.EnumerateArray())
                {
                    WriteCanonicalJson(writer, item);
                }
                writer.WriteEndArray();
                break;
            case JsonValueKind.String:
                writer.WriteStringValue(element.GetString());
                break;
            case JsonValueKind.Number:
                writer.WriteRawValue(element.GetRawText(), skipInputValidation: false);
                break;
            case JsonValueKind.True:
                writer.WriteBooleanValue(true);
                break;
            case JsonValueKind.False:
                writer.WriteBooleanValue(false);
                break;
            case JsonValueKind.Null:
                writer.WriteNullValue();
                break;
            default:
                throw new InvalidOperationException("Fixture proof contains an unsupported JSON token.");
        }
    }

    private sealed class AuthorityFixture : IDisposable
    {
        public const string GenerationId = "generation-a";
        private readonly PublicReleaseManifestDto _manifest;
        private readonly byte[] _scorecardBytes;
        private readonly byte[] _convergenceBytes;

        public AuthorityFixture(
            bool handShapedScoreTwo = false,
            bool previewScoreTwo = false,
            bool duplicateEvidenceValues = false,
            bool designGeneratedScoreTwo = false,
            Action<JsonObject, string>? scorecardMutation = null,
            Action<JsonObject>? convergenceMutation = null,
            string? manifestVersion = null)
        {
            Shelf = new ReleaseShelfGenerationStoreTests.ReleaseShelfFixture();
            byte[] artifactBytes = Encoding.UTF8.GetBytes("artifact-a");
            string sealedReleaseVersion = manifestVersion ?? CandidateReleaseVersion;
            _manifest = BuildManifest(artifactBytes, sealedReleaseVersion);
            PublicReleaseTruthProjectionTests.AuthorityEnvelope? predecessor = null;
            Shelf.WriteGeneration(
                GenerationId,
                sealedReleaseVersion,
                "artifact-a",
                generationBoundFilesFactory: canonicalBytes =>
                {
                    predecessor = PublicReleaseTruthProjectionTests.BuildAuthorityEnvelope(
                        _manifest,
                        "review_required",
                        manifestBytesOverride: canonicalBytes);
                    return new Dictionary<string, byte[]>(StringComparer.Ordinal)
                    {
                        [PublicReleaseAuthorityEnvelopeProjection.CurrentInventoryPath] = predecessor.CurrentBytes.ToArray(),
                        [PublicReleaseAuthorityEnvelopeProjection.SnapshotInventoryPath] = predecessor.SnapshotBytes.ToArray(),
                        ["release-evidence/" + PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath] = predecessor.DecisionBytes.ToArray()
                    };
                });
            Shelf.Activate(GenerationId, sealedReleaseVersion);
            ShelfStore = Shelf.CreateStore();
            Predecessor = predecessor
                ?? throw new InvalidOperationException("Authority predecessor fixture was not materialized.");
            ReleaseShelfSnapshot snapshot = ShelfStore.Capture();
            PublicReleaseTruthProjectionDto predecessorProjection =
                PublicReleaseAuthorityEnvelopeProjection.Project(
                    Predecessor.CurrentBytes,
                    Predecessor.SnapshotBytes,
                    Predecessor.DecisionBytes,
                    _manifest,
                    snapshot.CanonicalManifestSha256,
                    Predecessor.ManifestBytes);
            _scorecardBytes = BuildScorecard(
                handShapedScoreTwo,
                previewScoreTwo,
                duplicateEvidenceValues,
                designGeneratedScoreTwo,
                predecessorProjection.ManifestSha256,
                Digest(Predecessor.SnapshotBytes),
                Digest(Predecessor.DecisionBytes),
                predecessorProjection.RegistryCommit);
            if (scorecardMutation is not null)
            {
                JsonObject scorecard = JsonNode.Parse(_scorecardBytes)!.AsObject();
                scorecardMutation(scorecard, Digest(Predecessor.SnapshotBytes));
                _scorecardBytes = Encoding.UTF8.GetBytes(scorecard.ToJsonString());
            }
            _convergenceBytes = BuildConvergence(
                predecessorProjection,
                Digest(Predecessor.SnapshotBytes),
                Digest(Predecessor.DecisionBytes));
            if (convergenceMutation is not null)
            {
                JsonObject convergence = JsonNode.Parse(_convergenceBytes)!.AsObject();
                convergenceMutation(convergence);
                _convergenceBytes = Encoding.UTF8.GetBytes(convergence.ToJsonString());
            }
            Successor = BuildSuccessor(
                _manifest,
                Predecessor,
                _scorecardBytes,
                _convergenceBytes);
            Request = new ReleaseAuthorityRevisionAdvanceRequest(
                GenerationId,
                Digest(File.ReadAllBytes(Shelf.PointerPath)),
                "sha256:" + snapshot.InventoryDigest,
                ReleaseScopeDecisionSha256,
                ReleaseScopeDecisionBytes.ToArray(),
                Predecessor.CurrentBytes.ToArray(),
                Predecessor.SnapshotBytes.ToArray(),
                Predecessor.DecisionBytes.ToArray(),
                Successor.CurrentBytes.ToArray(),
                Successor.SnapshotBytes.ToArray(),
                Successor.DecisionBytes.ToArray(),
                _scorecardBytes,
                _convergenceBytes);
        }

        public ReleaseShelfGenerationStoreTests.ReleaseShelfFixture Shelf { get; }
        public ReleaseShelfGenerationStore ShelfStore { get; }
        public PublicReleaseTruthProjectionTests.AuthorityEnvelope Predecessor { get; }
        public PublicReleaseTruthProjectionTests.AuthorityEnvelope Successor { get; }
        public ReleaseAuthorityRevisionAdvanceRequest Request { get; }
        public string GenerationRoot => Path.Combine(
            Shelf.DownloadsRoot,
            ReleaseShelfGenerationStore.GenerationsDirectoryName,
            GenerationId);

        public ReleaseAuthorityRevisionStore CreateStore(
            Action<ReleaseAuthorityRevisionCheckpoint>? checkpoint = null,
            DateTimeOffset? observedAtUtc = null)
            => new(
                Shelf.Configuration,
                ShelfStore,
                _ => _manifest,
                new FixedTimeProvider(
                    observedAtUtc ?? DateTimeOffset.Parse(
                        "2026-07-20T20:08:00Z",
                        CultureInfo.InvariantCulture)),
                checkpoint);

        public PublicReleaseTruthProjectionDto Project(ReleaseShelfSnapshot snapshot)
        {
            PublicReleaseTruthProjectionDto? projection =
                PublicReleaseAuthorityEnvelopeProjection.TryProject(
                    snapshot,
                    _manifest,
                    snapshot.CanonicalManifestSha256,
                    Predecessor.ManifestBytes,
                    out _);
            return projection ?? throw new InvalidOperationException("Authority projection was absent.");
        }

        public void Dispose() => Shelf.Dispose();

        private sealed class FixedTimeProvider(DateTimeOffset utcNow) : TimeProvider
        {
            public override DateTimeOffset GetUtcNow() => utcNow;
        }

        private static PublicReleaseManifestDto BuildManifest(
            byte[] artifactBytes,
            string releaseVersion)
            => new(
                Version: releaseVersion,
                Channel: "preview",
                PublishedAt: DateTimeOffset.Parse(ReleaseShelfGenerationStoreTests.ReleaseShelfFixture.PublishedAt),
                Downloads:
                [
                    new PublicReleaseArtifactDto(
                        Id: "test-installer",
                        Platform: "Test installer",
                        Url: "/downloads/g/generation-a/files/chummer-test.bin",
                        Sha256: Digest(artifactBytes),
                        Head: "avalonia",
                        PlatformId: "linux",
                        Rid: "linux-x64",
                        Arch: "x64",
                        Kind: "installer",
                        SizeBytes: artifactBytes.Length,
                        CompatibilityState: "compatible",
                        InstallAccessClass: "open_public")
                ],
                Status: "published",
                RolloutState: "promoted_preview",
                SupportabilityState: "preview_supported",
                KnownIssueSummary: "No known preview blocker.");
    }

    private static PublicReleaseTruthProjectionTests.AuthorityEnvelope BuildSuccessor(
        PublicReleaseManifestDto manifest,
        PublicReleaseTruthProjectionTests.AuthorityEnvelope predecessor,
        byte[] scorecardBytes,
        byte[] convergenceBytes)
    {
        PublicReleaseTruthProjectionTests.AuthorityEnvelope successor =
            PublicReleaseTruthProjectionTests.BuildAuthorityEnvelope(
                manifest,
                "preview_ready",
                manifestBytesOverride: predecessor.ManifestBytes);
        JsonObject decision = JsonNode.Parse(successor.DecisionBytes.Span)!.AsObject();
        decision["authoritySnapshotSha256"] = Digest(predecessor.SnapshotBytes);
        decision["candidateDecisionStatus"] = "review_required";
        decision["candidateDecisionSha256"] = Digest(predecessor.DecisionBytes);
        decision["scorecardSha256"] = Digest(scorecardBytes);
        decision["convergenceSha256"] = Digest(convergenceBytes);
        decision["generatedAt"] = "2026-07-20T20:07:00Z";
        return PublicReleaseTruthProjectionTests.RebindDecision(
            successor,
            Encoding.UTF8.GetBytes(decision.ToJsonString()));
    }

    private static JsonObject LoadDesignScoreTwoFixtureRow()
    {
        JsonObject fixture = JsonNode.Parse(File.ReadAllBytes(Path.Combine(
            AppContext.BaseDirectory,
            "Fixtures",
            "campaign_operability_score_two_evidence.json")))!.AsObject();
        if (fixture["fixture_contract"]?.GetValue<string>()
                != "chummer.design.campaign_operability_score_two_fixture/v1"
            || fixture["scorecard_row"] is not JsonObject row)
        {
            throw new InvalidDataException("Design score-two fixture is malformed.");
        }
        return row.DeepClone().AsObject();
    }

    private static JsonObject LoadDesignCandidateEvidenceFixture()
    {
        JsonObject fixture = JsonNode.Parse(File.ReadAllBytes(Path.Combine(
            AppContext.BaseDirectory,
            "Fixtures",
            "campaign_operability_candidate_evidence.json")))!.AsObject();
        if (fixture["fixture_contract"]?.GetValue<string>()
                != "chummer.design.campaign_operability_candidate_evidence_fixture/v1"
            || fixture["scorecard_row"]?["candidate_evidence"] is not JsonObject binding)
        {
            throw new InvalidDataException("Design candidate-evidence fixture is malformed.");
        }
        return binding.DeepClone().AsObject();
    }

    private static byte[] BuildScorecard(
        bool handShapedScoreTwo,
        bool previewScoreTwo,
        bool duplicateEvidenceValues,
        bool designGeneratedScoreTwo,
        string manifestSha256,
        string predecessorSnapshotSha256,
        string predecessorDecisionSha256,
        string registryCommit)
    {
        string[] surfaces =
        [
            "desktop_workbench",
            "public_front_door_and_support",
            "install_claim_restore_continue",
            "build_explain_publish",
            "run_and_rejoin",
            "improve_and_close_the_loop"
        ];
        string[] dimensions =
        [
            "route_clarity",
            "rules_and_continuity_truth",
            "recovery_confidence",
            "closure_honesty",
            "responsiveness",
            "design_authorship"
        ];
        var cells = new JsonArray();
        bool preview = handShapedScoreTwo
            || previewScoreTwo
            || duplicateEvidenceValues
            || designGeneratedScoreTwo;
        string sharedAction = "Close the shared bounded preview action.";
        string sharedGap = "Shared evidence has not reached the stable bar";
        var journeyCatalog = new Dictionary<string, JsonObject>(StringComparer.Ordinal);
        var evidenceCatalog = new Dictionary<string, JsonObject>(StringComparer.Ordinal);

        JsonObject BuildEvidenceRow(string id, bool receipt)
        {
            bool scoreThree = !preview || receipt && id == "ui_frame";
            bool malformedScoreTwo = handShapedScoreTwo
                && id == "install_claim_restore_continue";
            int rowScore = scoreThree ? 3 : 2;
            string sourceSha256 = receipt
                ? Digest(Encoding.UTF8.GetBytes($"source receipt {id}"))
                : Digest(Encoding.UTF8.GetBytes("canonical journey gate receipt"));
            string[] proofActions = duplicateEvidenceValues
                ? [sharedAction, sharedAction]
                : [$"Close the bounded preview action for {id}."];
            string owner = $"owner_{id}";
            string rowOwner = rowScore == 3 || malformedScoreTwo ? string.Empty : owner;
            string[] rowActions = rowScore == 3 || malformedScoreTwo ? [] : proofActions;
            JsonNode? previewEvidence = null;
            if (rowScore == 2)
            {
                JsonObject proof = new()
                {
                    ["contract_name"] = "chummer.campaign_operability_preview_evidence",
                    ["contract_version"] = 2,
                    ["status"] = "pass",
                    ["release_version"] = CandidateReleaseVersion,
                    ["release_scope_decision_sha256"] = ReleaseScopeDecisionSha256,
                    ["bounded_owner"] = owner,
                    ["next_actions"] = JsonSerializer.SerializeToNode(proofActions)
                };
                previewEvidence = new JsonObject
                {
                    ["provenance_kind"] = "nested_declaration",
                    ["source_receipt_sha256"] = sourceSha256,
                    ["proof_sha256"] = CanonicalJsonDigest(proof),
                    ["proof"] = proof
                };
            }
            var row = new JsonObject
            {
                ["id"] = id,
                ["path"] = receipt
                    ? $"proof/{id}.json"
                    : "$FLEET_WORKSPACE/.codex-studio/published/JOURNEY_GATES.generated.json",
                ["source_status"] = rowScore == 3 ? "pass" : "fail",
                ["source_sha256"] = sourceSha256,
                ["generated_at"] = "2026-07-20T20:00:00Z",
                ["score"] = rowScore,
                ["status"] = rowScore == 3 ? "pass" : "preview",
                ["bounded_owner"] = rowOwner,
                ["next_actions"] = JsonSerializer.SerializeToNode(rowActions),
                ["failure"] = rowScore == 3
                    ? string.Empty
                    : duplicateEvidenceValues
                        ? sharedGap
                        : $"{id} has not reached the stable bar",
                ["preview_failure"] = string.Empty,
                ["preview_evidence"] = previewEvidence
            };
            if (rowScore == 3)
            {
                row["source_release_version"] = CandidateReleaseVersion;
                JsonObject candidateEvidence = LoadDesignCandidateEvidenceFixture();
                candidateEvidence["release_version"] = CandidateReleaseVersion;
                candidateEvidence["release_scope_decision_sha256"] =
                    ReleaseScopeDecisionSha256;
                candidateEvidence["manifest_sha256"] = manifestSha256;
                candidateEvidence["authority_snapshot_sha256"] =
                    predecessorSnapshotSha256;
                candidateEvidence["release_decision_sha256"] =
                    predecessorDecisionSha256;
                candidateEvidence["registry_commit"] = registryCommit;
                candidateEvidence["source_receipt_sha256"] = sourceSha256;
                row["candidate_evidence"] = candidateEvidence;
            }
            if (receipt)
            {
                row["source_verdict"] = rowScore == 3 ? "PASS" : "NOT_RELEASE_READY";
            }
            return row;
        }

        foreach (string surface in surfaces)
        {
            foreach (string journeyId in ReleaseAuthorityRevisionStore
                         .CampaignOperabilityJourneyIds(surface))
            {
                journeyCatalog.TryAdd(journeyId, BuildEvidenceRow(journeyId, receipt: false));
            }
            foreach (string dimension in dimensions)
            {
                foreach (string evidenceId in ReleaseAuthorityRevisionStore
                             .CampaignOperabilityEvidenceIds(surface, dimension))
                {
                    evidenceCatalog.TryAdd(evidenceId, BuildEvidenceRow(evidenceId, receipt: true));
                }
            }
        }

        foreach (string surface in surfaces)
        {
            foreach (string dimension in dimensions)
            {
                string[] journeyIds = ReleaseAuthorityRevisionStore
                    .CampaignOperabilityJourneyIds(surface);
                string[] evidenceIds = ReleaseAuthorityRevisionStore
                    .CampaignOperabilityEvidenceIds(surface, dimension);
                JsonObject[] rows = journeyIds.Select(id =>
                        journeyCatalog[id].DeepClone().AsObject())
                    .Concat(evidenceIds.Select(id =>
                        evidenceCatalog[id].DeepClone().AsObject()))
                    .ToArray();
                int score = rows.Min(row => row["score"]!.GetValue<int>());
                var scoreTwoOwners = new SortedSet<string>(StringComparer.Ordinal);
                var actions = new List<string>();
                var stableGaps = new JsonArray();
                foreach (JsonObject row in rows.Where(row => row["score"]!.GetValue<int>() == 2))
                {
                    string rowOwner = row["bounded_owner"]!.GetValue<string>();
                    if (rowOwner.Length > 0)
                    {
                        scoreTwoOwners.Add(rowOwner);
                    }
                    foreach (string action in row["next_actions"]!.AsArray()
                                 .Select(node => node!.GetValue<string>()))
                    {
                        if (!actions.Contains(action, StringComparer.Ordinal))
                        {
                            actions.Add(action);
                        }
                    }
                    stableGaps.Add(row["failure"]!.GetValue<string>());
                }
                cells.Add(new JsonObject
                {
                    ["surface_id"] = surface,
                    ["dimension_id"] = dimension,
                    ["score"] = score,
                    ["preview_status"] = "pass",
                    ["stable_status"] = score == 3 ? "pass" : "fail",
                    ["owners"] = JsonSerializer.SerializeToNode(
                        ReleaseAuthorityRevisionStore.CampaignOperabilityOwners(surface)),
                    ["preview_owners"] = JsonSerializer.SerializeToNode(scoreTwoOwners),
                    ["next_actions"] = JsonSerializer.SerializeToNode(actions),
                    ["journey_ids"] = JsonSerializer.SerializeToNode(journeyIds),
                    ["evidence_ids"] = JsonSerializer.SerializeToNode(evidenceIds),
                    ["evidence"] = new JsonArray(rows.Select(row => (JsonNode)row).ToArray()),
                    ["preview_blockers"] = new JsonArray(),
                    ["flagship_gaps"] = stableGaps.DeepClone(),
                    ["failures"] = stableGaps
                });
            }
        }
        int scoreTwoCount = cells.Count(node => node!["score"]!.GetValue<int>() == 2);
        var topGaps = new JsonArray();
        foreach (JsonNode? node in cells)
        {
            JsonObject cell = node!.AsObject();
            JsonArray gaps = cell["failures"]!.AsArray();
            if (gaps.Count > 0)
            {
                topGaps.Add(
                    $"{cell["surface_id"]!.GetValue<string>()}.{cell["dimension_id"]!.GetValue<string>()}: " +
                    string.Join(", ", gaps.Select(static gap => gap!.GetValue<string>())));
            }
        }
        JsonObject payload = new()
        {
            ["contract_name"] = "chummer.campaign_operability_scorecard",
            ["contract_version"] = 2,
            ["generated_at_utc"] = "2026-07-20T20:06:00Z",
            ["release_version"] = CandidateReleaseVersion,
            ["release_scope_decision_sha256"] = ReleaseScopeDecisionSha256,
            ["releaseVersion"] = CandidateReleaseVersion,
            ["releaseScopeDecisionSha256"] = ReleaseScopeDecisionSha256,
            ["snapshotSha256"] = predecessorSnapshotSha256,
            ["manifestSha256"] = manifestSha256,
            ["releaseDecisionSha256"] = predecessorDecisionSha256,
            ["status"] = scoreTwoCount == 0 ? "pass" : "fail",
            ["verdict"] = scoreTwoCount == 0 ? "CAMPAIGN_OPERABILITY_READY" : "CAMPAIGN_OPERABILITY_NOT_READY",
            ["preview_status"] = "pass",
            ["preview_verdict"] = "CAMPAIGN_OPERABILITY_PREVIEW_READY",
            ["stable_status"] = scoreTwoCount == 0 ? "pass" : "fail",
            ["stable_verdict"] = scoreTwoCount == 0 ? "CAMPAIGN_OPERABILITY_READY" : "CAMPAIGN_OPERABILITY_NOT_READY",
            ["rubric_path"] = "products/chummer/CAMPAIGN_OPERABILITY_SCORING_RUBRIC.yaml",
            ["journey_gate_path"] = "$FLEET_WORKSPACE/.codex-studio/published/JOURNEY_GATES.generated.json",
            ["required_surfaces"] = JsonSerializer.SerializeToNode(surfaces),
            ["required_dimensions"] = JsonSerializer.SerializeToNode(dimensions),
            ["summary"] = new JsonObject
            {
                ["surface_count"] = 6,
                ["dimension_count"] = 6,
                ["cell_count"] = 36,
                ["score_0_count"] = 0,
                ["score_1_count"] = 0,
                ["score_2_count"] = scoreTwoCount,
                ["score_3_count"] = 36 - scoreTwoCount,
                ["at_least_2_count"] = 36,
                ["below_2_count"] = 0,
                ["below_3_count"] = scoreTwoCount,
                ["minimum_score"] = scoreTwoCount == 0 ? 3 : 2
            },
            ["cells"] = cells,
            ["preview_failures"] = new JsonArray(),
            ["flagship_gaps"] = topGaps.DeepClone(),
            ["failures"] = topGaps
        };
        return Encoding.UTF8.GetBytes(payload.ToJsonString());
    }

    private static byte[] BuildConvergence(
        PublicReleaseTruthProjectionDto predecessor,
        string predecessorSnapshotSha256,
        string predecessorDecisionSha256)
    {
        string[] comparedFields =
        [
            "releaseVersion", "channel", "releaseStatus", "rolloutState", "supportabilityState",
            "availablePlatforms", "primaryHeadByPlatform", "artifactCount", "downloadAccessPosture",
            "knownIssueSummary", "manifestSha256", "registryCommit", "releaseDecisionStatus",
            "releaseDecisionSha256"
        ];
        string[] checkedRoutes = new[]
        {
            "/", "/now", "/changelog", "/downloads", "/downloads/concierge",
            "/status", "/artifacts", "/progress", "/help", "/now/concierge",
            "/now/concierge/read_notes", "/api/v1/public/progress-report",
            "/api/public/progress-report", "/api/v1/public/progress-poster.svg",
            "/api/public/progress-poster.svg", "/api/v1/public/weekly-pulse",
            "/api/public/weekly-pulse", "/api/public/release-truth",
            "/api/v1/install-linking/continuation",
            "/api/v1/install-linking/continuation/support",
            "/api/v1/install-linking/continuation/update",
            "/api/v1/install-linking/continuation/rollback",
            "/downloads/releases.json", "/downloads/RELEASE_CHANNEL.generated.json",
            "/Now/", "/Help/", "/Downloads/Concierge/", "/Now/Concierge/",
            "/Now/Concierge/read_notes/", "/downloads/install/test-installer"
        }.OrderBy(static route => route, StringComparer.Ordinal).ToArray();
        var payload = new
        {
            contractName = "chummer.live-release-convergence/v1",
            contractVersion = 1,
            generatedAtUtc = "2026-07-20T20:05:00Z",
            status = "pass",
            mismatchCount = 0,
            failureCount = 0,
            mismatches = Array.Empty<object>(),
            failures = Array.Empty<object>(),
            authorityRoute = "/api/v1/public/release-truth",
            checkedRouteCount = checkedRoutes.Length,
            checkedRoutes,
            comparedFields,
            releaseTruth = new
            {
                contractName = PublicReleaseTruthProjectionDto.Schema,
                releaseVersion = predecessor.ReleaseVersion,
                channel = predecessor.Channel,
                releaseStatus = predecessor.ReleaseStatus,
                rolloutState = predecessor.RolloutState,
                supportabilityState = predecessor.SupportabilityState,
                availablePlatforms = predecessor.AvailablePlatforms,
                primaryHeadByPlatform = predecessor.PrimaryHeadByPlatform,
                artifactCount = predecessor.ArtifactCount,
                downloadAccessPosture = predecessor.DownloadAccessPosture,
                knownIssueSummary = predecessor.KnownIssueSummary,
                manifestSha256 = predecessor.ManifestSha256,
                registryCommit = predecessor.RegistryCommit,
                releaseDecisionStatus = "review_required",
                releaseDecisionSha256 = predecessorDecisionSha256
            },
            manifestSha256 = predecessor.ManifestSha256,
            releaseDecisionStatus = "review_required",
            releaseDecisionSha256 = predecessorDecisionSha256,
            authoritySnapshotSha256 = predecessorSnapshotSha256
        };
        return JsonSerializer.SerializeToUtf8Bytes(payload);
    }
}
