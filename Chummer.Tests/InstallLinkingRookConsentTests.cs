using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingRookConsentTests
{
    private const string UserId = "user-rook-owner";
    private const string SubjectId = "subject-Rook-owner";
    private const string InstallationId = "install-rook-owner";
    private const string GrantId = "grant-rook-owner";
    private const string WorkspaceId = "workspace-rook-selected";
    private static readonly string ServerToken = new('a', 64);
    private static readonly string ContinuationDigest = new('b', 64);

    [Fact]
    public void Explicit_consent_validates_the_actual_selection_under_gate_and_survives_encrypted_restart()
    {
        using Fixture fixture = new();
        int validations = 0;
        DateTimeOffset before = DateTimeOffset.UtcNow;
        GrantArguments request = new();

        InstallLinkingRookReadConsent consent = fixture.Grant(request, installation =>
        {
            validations++;
            Assert.True(Monitor.IsEntered(fixture.Store.Gate));
            Assert.Same(fixture.Store.InstallationsById[InstallationId], installation);
            Assert.Equal(GrantId, installation.GrantId);
            Assert.Empty(fixture.Store.RookReadConsentsById);
        });

        Assert.Equal(1, validations);
        Assert.Matches("^[0-9a-f]{64}$", consent.ConsentId);
        Assert.Equal(1, consent.Version);
        Assert.Equal(UserId, consent.UserId);
        Assert.Equal(SubjectId, consent.SubjectId);
        Assert.Equal(InstallationId, consent.InstallationId);
        Assert.Equal(GrantId, consent.GrantId);
        Assert.Equal(WorkspaceId, consent.WorkspaceId);
        Assert.Equal(17, consent.RemoteRevision);
        Assert.Equal(ServerToken, consent.ServerToken);
        Assert.Equal(ContinuationDigest, consent.ContinuationDigest);
        Assert.Equal("rook-rule-read", consent.Purpose);
        Assert.InRange(consent.IssuedAtUtc, before, DateTimeOffset.UtcNow);
        Assert.Equal(request.ExpiresAtUtc, consent.ExpiresAtUtc);
        Assert.Null(consent.RevokedAtUtc);
        Assert.Same(StringComparer.Ordinal, fixture.Store.RookReadConsentsById.Comparer);
        string envelope = File.ReadAllText(fixture.Store.StoragePath);
        Assert.DoesNotContain(consent.ConsentId, envelope, StringComparison.Ordinal);
        Assert.DoesNotContain(WorkspaceId, envelope, StringComparison.Ordinal);
        Assert.DoesNotContain(ContinuationDigest, envelope, StringComparison.Ordinal);

        fixture.Restart();

        Assert.Equal(consent, Assert.Single(fixture.Store.RookReadConsentsById.Values));
    }

    [Fact]
    public void Owner_can_revoke_after_grant_revocation_and_the_incremented_version_survives_restart()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = fixture.Grant();
        fixture.Service.RevokeGrantForOwner(InstallationId, UserId, SubjectId);
        DateTimeOffset before = DateTimeOffset.UtcNow;

        InstallLinkingRookReadConsent revoked = fixture.Service.RevokeRookReadConsent(
            UserId, SubjectId, consent.ConsentId, consent.Version);

        Assert.Equal(consent with { Version = 2, RevokedAtUtc = revoked.RevokedAtUtc }, revoked);
        Assert.NotNull(revoked.RevokedAtUtc);
        Assert.InRange(revoked.RevokedAtUtc!.Value, before, DateTimeOffset.UtcNow);
        fixture.Restart();
        Assert.Equal(revoked, Assert.Single(fixture.Store.RookReadConsentsById.Values));
        Assert.Equal(InstallationGrantStates.Revoked, fixture.Store.GrantsById[GrantId].Status);
    }

    [Fact]
    public void Regrant_uses_a_new_random_id_and_cannot_restore_an_old_version()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent original = fixture.Grant();
        InstallLinkingRookReadConsent revoked = fixture.Service.RevokeRookReadConsent(
            UserId, SubjectId, original.ConsentId, original.Version);
        InstallLinkingRookReadConsent replacement = fixture.Grant();

        Assert.NotEqual(original.ConsentId, replacement.ConsentId);
        Assert.Matches("^[0-9a-f]{64}$", replacement.ConsentId);
        Assert.Equal(1, replacement.Version);
        Assert.Null(replacement.RevokedAtUtc);
        DurableState before = fixture.Observe();
        Assert.Throws<InvalidOperationException>(() => fixture.Service.RevokeRookReadConsent(
            UserId, SubjectId, original.ConsentId, original.Version));
        fixture.AssertUnchanged(before);
        fixture.Restart();
        Assert.Equal(revoked, fixture.Store.RookReadConsentsById[original.ConsentId]);
        Assert.Equal(replacement, fixture.Store.RookReadConsentsById[replacement.ConsentId]);
    }

    [Theory]
    [InlineData("another-user", SubjectId)]
    [InlineData(UserId, "SUBJECT-ROOK-OWNER")]
    public void Both_exact_owner_components_are_required_without_any_write(string userId, string subjectId)
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = fixture.Grant();
        DurableState before = fixture.Observe();
        int validations = 0;

        Assert.Throws<InvalidOperationException>(() => fixture.Grant(
            new GrantArguments { UserId = userId, SubjectId = subjectId }, _ => validations++));
        Assert.Throws<InvalidOperationException>(() => fixture.Service.RevokeRookReadConsent(
            userId, subjectId, consent.ConsentId, consent.Version));

        Assert.Equal(0, validations);
        fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData("noncurrent")]
    [InlineData("revoked-installation")]
    [InlineData("revoked-grant")]
    [InlineData("expired-grant")]
    [InlineData("legacy-grant")]
    [InlineData("grant-owner-mismatch")]
    [InlineData("null-installation")]
    [InlineData("null-grant")]
    [InlineData("null-transport")]
    public void Only_the_current_active_v2_owned_grant_can_issue_consent(string state)
    {
        using Fixture fixture = new();
        lock (fixture.Store.Gate)
        {
            ClaimedInstallationDto installation = fixture.Store.InstallationsById[InstallationId];
            InstallationGrantDto grant = fixture.Store.GrantsById[GrantId];
            switch (state)
            {
                case "noncurrent":
                    fixture.Store.InstallationsById[InstallationId] = installation with { GrantId = "grant-other" };
                    break;
                case "revoked-installation":
                    fixture.Store.InstallationsById[InstallationId] = installation with { Status = ClaimedInstallationStates.Revoked };
                    break;
                case "revoked-grant":
                    fixture.Store.GrantsById[GrantId] = grant with { Status = InstallationGrantStates.Revoked };
                    break;
                case "expired-grant":
                    fixture.Store.GrantsById[GrantId] = grant with { ExpiresAtUtc = DateTimeOffset.UtcNow.AddSeconds(-5) };
                    break;
                case "legacy-grant":
                    fixture.Store.GrantTransportAuthoritiesByGrantId[GrantId] = new(
                        GrantId, InstallationGrantTransports.LegacyV1);
                    break;
                case "grant-owner-mismatch":
                    fixture.Store.GrantsById[GrantId] = grant with { SubjectId = "another-subject" };
                    break;
                case "null-installation":
                    fixture.Store.InstallationsById[InstallationId] = null!;
                    break;
                case "null-grant":
                    fixture.Store.GrantsById[GrantId] = null!;
                    break;
                case "null-transport":
                    fixture.Store.GrantTransportAuthoritiesByGrantId[GrantId] = null!;
                    break;
                default:
                    throw new InvalidOperationException("Unknown test state.");
            }
            // Null rows deliberately model hostile internal state, not a valid snapshot.
            if (!state.StartsWith("null-", StringComparison.Ordinal))
            {
                fixture.Store.PersistLocked();
            }
        }
        DurableState before = fixture.Observe();
        int validations = 0;

        Assert.Throws<InvalidOperationException>(() => fixture.Grant(validateSelection: _ => validations++));

        Assert.Equal(0, validations);
        fixture.AssertUnchanged(before);
        Assert.Empty(fixture.Store.RookReadConsentsById);
    }

    [Fact]
    public void Malformed_inputs_and_missing_validator_are_rejected_before_writes_or_selection()
    {
        using Fixture fixture = new();
        GrantArguments valid = new();
        GrantArguments[] invalid =
        [
            valid with { UserId = " " },
            valid with { UserId = "user-\ud800" },
            valid with { SubjectId = "subject\nowner" },
            valid with { SubjectId = "subject-\udfff" },
            valid with { InstallationId = new string('i', 1025) },
            valid with { GrantId = " grant-rook-owner" },
            valid with { WorkspaceId = "workspace\tother" },
            valid with { RemoteRevision = 0 },
            valid with { RemoteRevision = -1 },
            valid with { ServerToken = new string('A', 64) },
            valid with { ServerToken = new string('a', 63) },
            valid with { ContinuationDigest = new string('z', 64) },
            valid with { ContinuationDigest = new string('b', 65) }
        ];
        DurableState before = fixture.Observe();
        int validations = 0;
        foreach (GrantArguments request in invalid)
        {
            Assert.ThrowsAny<ArgumentException>(() => fixture.Grant(request, _ => validations++));
            fixture.AssertUnchanged(before);
        }
        Assert.ThrowsAny<ArgumentException>(() => fixture.Service.GrantRookReadConsent(
            UserId, SubjectId, InstallationId, GrantId, WorkspaceId, 17, ServerToken,
            ContinuationDigest, true, valid.ExpiresAtUtc, null!));
        Assert.Equal(0, validations);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public void Explicit_confirmation_is_not_inferred_from_a_valid_installation_or_grant()
    {
        using Fixture fixture = new();
        DurableState before = fixture.Observe();
        int validations = 0;

        Assert.ThrowsAny<ArgumentException>(() => fixture.Grant(
            new GrantArguments { ExplicitConfirmation = false }, _ => validations++));

        Assert.Equal(0, validations);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public void Consent_expiry_must_be_future_within_fifteen_minutes_and_no_later_than_the_grant()
    {
        using Fixture fixture = new();
        DurableState before = fixture.Observe();
        foreach (DateTimeOffset expiry in new[]
                 { DateTimeOffset.UtcNow.AddSeconds(-5), DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(16) })
        {
            Assert.ThrowsAny<ArgumentException>(() => fixture.Grant(new GrantArguments { ExpiresAtUtc = expiry }));
            fixture.AssertUnchanged(before);
        }
        lock (fixture.Store.Gate)
        {
            fixture.Store.GrantsById[GrantId] = fixture.Store.GrantsById[GrantId] with
            {
                ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(2)
            };
            fixture.Store.PersistLocked();
        }
        before = fixture.Observe();

        Assert.ThrowsAny<ArgumentException>(() => fixture.Grant(
            new GrantArguments { ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(3) }));

        fixture.AssertUnchanged(before);
    }

    [Fact]
    public void A_throwing_selection_validator_cannot_leave_a_consent_in_memory_or_on_disk()
    {
        using Fixture fixture = new();
        DurableState before = fixture.Observe();
        InvalidOperationException rejection = new("selection rejected by test");

        Assert.Same(rejection, Assert.Throws<InvalidOperationException>(() => fixture.Grant(
            validateSelection: _ => throw rejection)));

        fixture.AssertUnchanged(before);
        fixture.Restart();
        Assert.Empty(fixture.Store.RookReadConsentsById);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Async_void_selection_validators_are_rejected_including_multicast_members(bool multicast)
    {
        using Fixture fixture = new();
        int validations = 0;
        Action<ClaimedInstallationDto> asynchronous = async _ =>
        {
            validations++;
            await Task.CompletedTask;
        };
        Action<ClaimedInstallationDto> validator = asynchronous;
        if (multicast)
        {
            validator = _ => validations++;
            validator += asynchronous;
        }
        DurableState before = fixture.Observe();

        Assert.ThrowsAny<ArgumentException>(() => fixture.Grant(validateSelection: validator));

        Assert.Equal(0, validations);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public void Cancellation_before_entry_or_inside_selection_cannot_commit_a_consent_change()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = fixture.Grant();
        DurableState before = fixture.Observe();
        using CancellationTokenSource cancelled = new();
        cancelled.Cancel();
        int callbacks = 0;
        Assert.ThrowsAny<OperationCanceledException>(() => fixture.Grant(
            validateSelection: _ => callbacks++, cancellationToken: cancelled.Token));
        Assert.ThrowsAny<OperationCanceledException>(() => fixture.Service.RevokeRookReadConsent(
            UserId, SubjectId, consent.ConsentId, consent.Version, cancelled.Token));
        Assert.ThrowsAny<OperationCanceledException>(() => fixture.Service.CaptureRookReadConsent(
            UserId, SubjectId, InstallationId, GrantId, consent.ConsentId, consent.Version,
            (_, _) => callbacks++, cancelled.Token));
        Assert.Equal(0, callbacks);
        fixture.AssertUnchanged(before);

        using CancellationTokenSource duringSelection = new();
        Assert.ThrowsAny<OperationCanceledException>(() => fixture.Grant(
            validateSelection: _ => duringSelection.Cancel(), cancellationToken: duringSelection.Token));
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public void A_local_durable_consent_is_not_a_postgres_fence_and_never_invokes_capture()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = fixture.Grant();
        fixture.Restart();
        DurableState before = fixture.Observe();
        int captures = 0;

        Assert.False(fixture.Service.CaptureRookReadConsent(
            UserId, SubjectId, InstallationId, GrantId, consent.ConsentId, consent.Version,
            (_, _) => captures++));

        Assert.Equal(0, captures);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task An_unready_fixed_store_denies_before_waiting_for_its_local_gate()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = fixture.Grant();
        fixture.UseReadinessProbe(new UnavailableReadinessProbe());
        DurableState before = fixture.Observe();
        int callbacks = 0;
        using ManualResetEventSlim checksFinished = new();
        Task checks;
        bool completedWhileGateHeld;
        lock (fixture.Store.Gate)
        {
            checks = Task.Run(() =>
            {
                try
                {
                    InstallLinkingOperationException grantFailure = Assert.Throws<InstallLinkingOperationException>(
                        () => fixture.Grant(validateSelection: _ => callbacks++));
                    InstallLinkingOperationException revokeFailure = Assert.Throws<InstallLinkingOperationException>(
                        () => fixture.Service.RevokeRookReadConsent(
                            UserId, SubjectId, consent.ConsentId, consent.Version));
                    Assert.Equal(503, grantFailure.StatusCode);
                    Assert.Equal(503, revokeFailure.StatusCode);
                    Assert.False(fixture.Service.CaptureRookReadConsent(
                        UserId, SubjectId, InstallationId, GrantId, consent.ConsentId, consent.Version,
                        (_, _) => callbacks++));
                }
                finally
                {
                    checksFinished.Set();
                }
            });
            completedWhileGateHeld = checksFinished.Wait(TimeSpan.FromSeconds(5));
        }
        await checks.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.True(completedWhileGateHeld, "Readiness denial must not acquire the unavailable store's gate.");
        Assert.Equal(0, callbacks);
        fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Cancellation_during_real_data_protection_returns_the_successfully_committed_record(bool revoke)
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent? existing = revoke ? fixture.Grant() : null;
        using CancellationTokenSource cancellation = new();
        fixture.AfterNextProtect = cancellation.Cancel;

        InstallLinkingRookReadConsent committed = revoke
            ? fixture.Service.RevokeRookReadConsent(
                UserId, SubjectId, existing!.ConsentId, existing.Version, cancellation.Token)
            : fixture.Grant(cancellationToken: cancellation.Token);

        Assert.True(cancellation.IsCancellationRequested);
        Assert.Equal(revoke ? 2 : 1, committed.Version);
        Assert.Equal(revoke, committed.RevokedAtUtc.HasValue);
        Assert.Equal(committed, Assert.Single(fixture.Store.RookReadConsentsById.Values));
        fixture.Restart();
        Assert.Equal(committed, Assert.Single(fixture.Store.RookReadConsentsById.Values));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Corrupt_consent_fields_or_references_fail_closed_and_restore_the_committed_snapshot(bool badReference)
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent committed = fixture.Grant();
        DurableState before = fixture.Observe();
        lock (fixture.Store.Gate)
        {
            fixture.Store.RookReadConsentsById[committed.ConsentId] = badReference
                ? committed with { GrantId = "missing-grant" }
                : committed with { Purpose = "provider-write" };

            Assert.Throws<InvalidDataException>(() => fixture.Store.PersistLocked());
        }

        Assert.False(fixture.Store.IsHealthy);
        Assert.Equal(committed, Assert.Single(fixture.Store.RookReadConsentsById.Values));
        Assert.Equal(before.Envelope, File.ReadAllBytes(fixture.Store.StoragePath));
        Assert.Equal(before.Floor, File.ReadAllBytes(fixture.Store.StoragePath + ".floor"));
        fixture.Restart();
        Assert.True(fixture.Store.IsHealthy);
        Assert.Equal(committed, Assert.Single(fixture.Store.RookReadConsentsById.Values));
    }

    [Fact]
    public void Legacy_snapshot_without_the_optional_collection_loads_as_no_consent()
    {
        using Fixture fixture = new(legacyEmptySnapshot: true);

        Assert.Empty(fixture.Store.RookReadConsentsById);
        Assert.Empty(fixture.Snapshot().RookReadConsents ?? []);
        Assert.Contains("chummer.install-linking-store", File.ReadAllText(fixture.Store.StoragePath), StringComparison.Ordinal);
        fixture.Restart();
        Assert.Empty(fixture.Store.RookReadConsentsById);
    }

    [Fact]
    public void Retention_keeps_the_consent_and_its_references_until_the_audit_window_has_ended()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent consent = fixture.Grant();
        fixture.Service.RevokeRookReadConsent(UserId, SubjectId, consent.ConsentId, consent.Version);
        InstallLinkingStoreSnapshot source = fixture.Snapshot();

        InstallLinkingStoreSnapshot retained = InstallLinkingStore.BuildRetainedSnapshot(
            source, consent.ExpiresAtUtc.AddHours(23));

        Assert.Equal(consent.ConsentId, Assert.Single(retained.RookReadConsents!).ConsentId);
        Assert.Contains(retained.Grants, grant => grant.GrantId == GrantId);
        Assert.Contains(retained.Installations, installation => installation.InstallationId == InstallationId);
        InstallLinkingStore.ValidateSnapshot(retained);
        InstallLinkingStoreSnapshot expired = InstallLinkingStore.BuildRetainedSnapshot(
            source, consent.ExpiresAtUtc.AddHours(25));
        Assert.Empty(expired.RookReadConsents ?? []);
        InstallLinkingStore.ValidateSnapshot(expired);
    }

    [Fact]
    public void Principal_erasure_removes_owned_consents_durably_without_removing_another_owners_consent()
    {
        using Fixture fixture = new();
        fixture.Grant();
        fixture.Seed("user-other", "subject-other", "install-other", "grant-other");
        InstallLinkingRookReadConsent other = fixture.Grant(new GrantArguments
        {
            UserId = "user-other", SubjectId = "subject-other",
            InstallationId = "install-other", GrantId = "grant-other"
        });

        InstallLinkingPrincipalErasureResult erased = fixture.Store.ErasePrincipal(UserId, SubjectId);

        Assert.True(erased.Erased);
        Assert.Equal(1, erased.InstallationsRemoved);
        Assert.Equal(other, Assert.Single(fixture.Store.RookReadConsentsById.Values));
        fixture.Restart();
        Assert.Equal(other, Assert.Single(fixture.Store.RookReadConsentsById.Values));
        Assert.False(fixture.Store.InstallationsById.ContainsKey(InstallationId));
        Assert.False(fixture.Store.GrantsById.ContainsKey(GrantId));
    }

    [Fact]
    public void Full_live_consent_capacity_denies_without_evicting_existing_evidence()
    {
        using Fixture fixture = new();
        InstallLinkingRookReadConsent template = fixture.Grant();
        lock (fixture.Store.Gate)
        {
            for (int index = 1; index < InstallLinkingStore.MaxRookReadConsents; index++)
            {
                string consentId = index.ToString("x64", System.Globalization.CultureInfo.InvariantCulture);
                fixture.Store.RookReadConsentsById.Add(consentId, template with { ConsentId = consentId });
            }
            fixture.Store.PersistLocked();
        }
        DurableState before = fixture.Observe();
        int validations = 0;

        Assert.Throws<InvalidOperationException>(() => fixture.Grant(validateSelection: _ => validations++));

        Assert.Equal(1, validations);
        Assert.Equal(InstallLinkingStore.MaxRookReadConsents, fixture.Store.RookReadConsentsById.Count);
        fixture.AssertUnchanged(before);
    }

    private sealed record GrantArguments
    {
        public string UserId { get; init; } = InstallLinkingRookConsentTests.UserId;
        public string SubjectId { get; init; } = InstallLinkingRookConsentTests.SubjectId;
        public string InstallationId { get; init; } = InstallLinkingRookConsentTests.InstallationId;
        public string GrantId { get; init; } = InstallLinkingRookConsentTests.GrantId;
        public string WorkspaceId { get; init; } = InstallLinkingRookConsentTests.WorkspaceId;
        public long RemoteRevision { get; init; } = 17;
        public string ServerToken { get; init; } = InstallLinkingRookConsentTests.ServerToken;
        public string ContinuationDigest { get; init; } = InstallLinkingRookConsentTests.ContinuationDigest;
        public bool ExplicitConfirmation { get; init; } = true;
        public DateTimeOffset ExpiresAtUtc { get; init; } = DateTimeOffset.UtcNow.AddMinutes(10);
    }

    private sealed record DurableState(
        long PersistenceAttempts,
        byte[] Envelope,
        byte[] Floor,
        InstallLinkingRookReadConsent[] Consents);

    private sealed class Fixture : IDisposable
    {
        private readonly string _root = Path.Combine(
            Path.GetTempPath(), "chummer-rook-consent-tests", Guid.NewGuid().ToString("N"));
        private readonly string _keyPath;
        private readonly IConfiguration _configuration;

        public Fixture(bool legacyEmptySnapshot = false)
        {
            Directory.CreateDirectory(_root);
            _keyPath = Path.Combine(_root, "keys");
            string storagePath = Path.Combine(_root, "install-linking-store.json");
            if (legacyEmptySnapshot)
            {
                File.WriteAllText(storagePath,
                    "{\"receipts\":[],\"claimTickets\":[],\"browserCallbacks\":[],\"installations\":[],\"grants\":[],\"personalizedInstallScripts\":[]}");
            }
            _configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = storagePath
            }).Build();
            Store = CreateStore();
            Service = new InstallLinkingService(Store, _configuration);
            if (!legacyEmptySnapshot)
            {
                Seed(UserId, SubjectId, InstallationId, GrantId);
            }
        }

        public InstallLinkingStore Store { get; private set; }
        public InstallLinkingService Service { get; private set; }
        public Action? AfterNextProtect { get; set; }

        public void UseReadinessProbe(IInstallLinkingStoreReadinessProbe readinessProbe)
            => Service = new InstallLinkingService(Store, _configuration, readinessProbe);

        public InstallLinkingRookReadConsent Grant(
            GrantArguments? arguments = null,
            Action<ClaimedInstallationDto>? validateSelection = null,
            CancellationToken cancellationToken = default)
        {
            GrantArguments request = arguments ?? new();
            return Service.GrantRookReadConsent(
                request.UserId, request.SubjectId, request.InstallationId, request.GrantId,
                request.WorkspaceId, request.RemoteRevision, request.ServerToken,
                request.ContinuationDigest, request.ExplicitConfirmation, request.ExpiresAtUtc,
                validateSelection ?? (_ => { }), cancellationToken);
        }

        public void Seed(string userId, string subjectId, string installationId, string grantId)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            lock (Store.Gate)
            {
                Store.InstallationsById[installationId] = new ClaimedInstallationDto(
                    InstallationId: installationId,
                    ArtifactId: "artifact-rook-test",
                    Channel: "preview",
                    Version: "6.0.1",
                    InstallAccessClass: InstallAccessClasses.AccountRequired,
                    Status: ClaimedInstallationStates.Active,
                    CreatedAtUtc: now.AddMinutes(-5),
                    UpdatedAtUtc: now,
                    UserId: userId,
                    SubjectId: subjectId,
                    PublicKey: "fixture-public-key",
                    ClaimTicketId: null,
                    HeadId: "desktop",
                    Platform: "linux",
                    Arch: "x64",
                    HostLabel: "Rook consent fixture",
                    GrantId: grantId);
                Store.GrantsById[grantId] = new InstallationGrantDto(
                    GrantId: grantId,
                    InstallationId: installationId,
                    Status: InstallationGrantStates.Active,
                    AccessToken: "fixture-grant-token",
                    IssuedAtUtc: now.AddMinutes(-1),
                    ExpiresAtUtc: now.AddHours(1),
                    UserId: userId,
                    SubjectId: subjectId);
                Store.GrantTransportAuthoritiesByGrantId[grantId] = new(
                    grantId, InstallationGrantTransports.AndroidLinkedV2);
                Store.PersistLocked();
            }
        }

        public DurableState Observe() => new(
            Store.PersistenceAttempts,
            File.ReadAllBytes(Store.StoragePath),
            File.ReadAllBytes(Store.StoragePath + ".floor"),
            Store.RookReadConsentsById.Values.OrderBy(item => item.ConsentId, StringComparer.Ordinal).ToArray());

        public void AssertUnchanged(DurableState before)
        {
            Assert.Equal(before.PersistenceAttempts, Store.PersistenceAttempts);
            Assert.Equal(before.Envelope, File.ReadAllBytes(Store.StoragePath));
            Assert.Equal(before.Floor, File.ReadAllBytes(Store.StoragePath + ".floor"));
            Assert.Equal(before.Consents,
                Store.RookReadConsentsById.Values.OrderBy(item => item.ConsentId, StringComparer.Ordinal).ToArray());
        }

        public InstallLinkingStoreSnapshot Snapshot()
        {
            using JsonDocument envelope = JsonDocument.Parse(File.ReadAllBytes(Store.StoragePath));
            IDataProtector protector = DataProtectionProvider.Create(new DirectoryInfo(_keyPath))
                .CreateProtector(InstallLinkingStore.DataProtectionPurpose);
            string payload = protector.Unprotect(envelope.RootElement.GetProperty("protectedPayload").GetString()!);
            return JsonSerializer.Deserialize<InstallLinkingStoreSnapshot>(
                Convert.FromBase64String(payload), new JsonSerializerOptions(JsonSerializerDefaults.Web))
                ?? throw new InvalidDataException("Fixture snapshot could not be decoded.");
        }

        public void Restart()
        {
            Store.Dispose();
            Store = CreateStore();
            Service = new InstallLinkingService(Store, _configuration);
        }

        private InstallLinkingStore CreateStore() => new(
            _configuration,
            new ForwardingProtectionProvider(DataProtectionProvider.Create(new DirectoryInfo(_keyPath)), () =>
            {
                Action? afterProtect = AfterNextProtect;
                AfterNextProtect = null;
                afterProtect?.Invoke();
            }),
            NullLogger<InstallLinkingStore>.Instance);

        public void Dispose()
        {
            Store.Dispose();
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class UnavailableReadinessProbe : IInstallLinkingStoreReadinessProbe
    {
        public InstallLinkingStoreReadiness Evaluate() => new(false, "fixture-unavailable");
    }

    // The hook observes actual successful DataProtection work; it does not emulate encryption
    // or persistence success. Every Protect/Unprotect delegates to the real persisted key ring.
    private sealed class ForwardingProtectionProvider(IDataProtectionProvider inner, Action afterProtect)
        : IDataProtectionProvider
    {
        public IDataProtector CreateProtector(string purpose)
            => new ForwardingProtector(inner.CreateProtector(purpose), afterProtect);
    }

    private sealed class ForwardingProtector(IDataProtector inner, Action afterProtect) : IDataProtector
    {
        public IDataProtector CreateProtector(string purpose)
            => new ForwardingProtector(inner.CreateProtector(purpose), afterProtect);

        public byte[] Protect(byte[] plaintext)
        {
            byte[] protectedData = inner.Protect(plaintext);
            afterProtect();
            return protectedData;
        }

        public byte[] Unprotect(byte[] protectedData) => inner.Unprotect(protectedData);
    }
}
