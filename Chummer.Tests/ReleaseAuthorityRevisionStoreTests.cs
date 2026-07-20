using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.PublicSurface;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseAuthorityRevisionStoreTests
{
    [Fact]
    public void AdvanceRequestJsonRequiresExactCanonicalFieldsAndBoundedBase64()
    {
        var request = new ReleaseAuthorityRevisionAdvanceRequest(
            "generation-a",
            new string('a', 64),
            new string('b', 64),
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

    [Theory]
    [InlineData("legacy_contract")]
    [InlineData("unknown_top_field")]
    [InlineData("arbitrary_matrix")]
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
    [InlineData("blocked_source_status")]
    [InlineData("missing_generated_at")]
    [InlineData("stale_evidence_row")]
    [InlineData("future_evidence_row")]
    [InlineData("unresolved_source_verdict")]
    [InlineData("review_required_source_verdict")]
    [InlineData("nonportable_evidence_path")]
    [InlineData("nonportable_policy_path")]
    [InlineData("score_three_preview_state")]
    [InlineData("score_three_preview_failure")]
    public async Task ScorecardValidatorRejectsHandShapedOrContradictoryEvidence(string testCase)
    {
        bool stable = testCase.StartsWith("score_three_", StringComparison.Ordinal);
        using var fixture = new AuthorityFixture(
            previewScoreTwo: !stable,
            scorecardMutation: scorecard => MutateScorecard(scorecard, testCase));

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

    private static void MutateScorecard(JsonObject scorecard, string testCase)
    {
        JsonObject firstCell = scorecard["cells"]!.AsArray()[0]!.AsObject();
        JsonObject firstRow = firstCell["evidence"]!.AsArray()[0]!.AsObject();
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
            case "blocked_source_status":
                firstRow["source_status"] = "fail";
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
                firstRow["source_verdict"] = "unknown";
                break;
            case "review_required_source_verdict":
                firstRow["source_verdict"] = "PUBLIC_RELEASE_REVIEW_REQUIRED";
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
            Action<JsonObject>? scorecardMutation = null,
            Action<JsonObject>? convergenceMutation = null)
        {
            Shelf = new ReleaseShelfGenerationStoreTests.ReleaseShelfFixture();
            byte[] artifactBytes = Encoding.UTF8.GetBytes("artifact-a");
            _manifest = BuildManifest(artifactBytes);
            PublicReleaseTruthProjectionTests.AuthorityEnvelope? predecessor = null;
            Shelf.WriteGeneration(
                GenerationId,
                "run-a",
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
            Shelf.Activate(GenerationId, "run-a");
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
                duplicateEvidenceValues);
            if (scorecardMutation is not null)
            {
                JsonObject scorecard = JsonNode.Parse(_scorecardBytes)!.AsObject();
                scorecardMutation(scorecard);
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

        private static PublicReleaseManifestDto BuildManifest(byte[] artifactBytes)
            => new(
                Version: "run-a",
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

    private static byte[] BuildScorecard(
        bool handShapedScoreTwo,
        bool previewScoreTwo,
        bool duplicateEvidenceValues)
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
        int index = 0;
        bool preview = handShapedScoreTwo || previewScoreTwo || duplicateEvidenceValues;
        foreach (string surface in surfaces)
        {
            foreach (string dimension in dimensions)
            {
                bool malformedScoreTwo = handShapedScoreTwo && index == 0;
                int score = preview ? 2 : 3;
                string journeyId = $"journey_{index:00}";
                string evidenceId = $"evidence_{index:00}";
                string owner = $"owner_{surface}";
                string sharedAction = "Close the shared bounded preview action.";
                string sharedGap = "Shared evidence has not reached the stable bar";
                JsonObject Evidence(string id, bool receipt) => new()
                {
                    ["id"] = id,
                    ["path"] = $"proof/{id}.json",
                    ["source_status"] = "pass",
                    ["generated_at"] = "2026-07-20T20:00:00Z",
                    ["score"] = score,
                    ["status"] = score == 3 ? "pass" : "preview",
                    ["bounded_owner"] = score == 3 || malformedScoreTwo ? string.Empty : owner,
                    ["next_actions"] = score == 3 || malformedScoreTwo
                        ? new JsonArray()
                        : duplicateEvidenceValues
                            ? new JsonArray(sharedAction, sharedAction)
                            : new JsonArray($"Close the bounded preview action for {id}."),
                    ["failure"] = score == 3
                        ? string.Empty
                        : duplicateEvidenceValues
                            ? sharedGap
                            : $"{id} has not reached the stable bar",
                    ["preview_failure"] = string.Empty
                };
                JsonObject journey = Evidence(journeyId, receipt: false);
                JsonObject evidence = Evidence(evidenceId, receipt: true);
                evidence["source_verdict"] = "PASS";
                var stableGaps = score == 3
                    ? new JsonArray()
                    : new JsonArray(
                        journey["failure"]!.GetValue<string>(),
                        evidence["failure"]!.GetValue<string>());
                cells.Add(new JsonObject
                {
                    ["surface_id"] = surface,
                    ["dimension_id"] = dimension,
                    ["score"] = score,
                    ["preview_status"] = "pass",
                    ["stable_status"] = score == 3 ? "pass" : "fail",
                    ["owners"] = new JsonArray("release-operations"),
                    ["preview_owners"] = score == 3 || malformedScoreTwo
                        ? new JsonArray()
                        : new JsonArray(owner),
                    ["next_actions"] = score == 3 || malformedScoreTwo
                        ? new JsonArray()
                        : duplicateEvidenceValues
                            ? new JsonArray(sharedAction)
                            : new JsonArray(
                                $"Close the bounded preview action for {journeyId}.",
                                $"Close the bounded preview action for {evidenceId}."),
                    ["journey_ids"] = new JsonArray(journeyId),
                    ["evidence_ids"] = new JsonArray(evidenceId),
                    ["evidence"] = new JsonArray(journey, evidence),
                    ["preview_blockers"] = new JsonArray(),
                    ["flagship_gaps"] = stableGaps.DeepClone(),
                    ["failures"] = stableGaps
                });
                index++;
            }
        }
        int scoreTwoCount = preview ? 36 : 0;
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
