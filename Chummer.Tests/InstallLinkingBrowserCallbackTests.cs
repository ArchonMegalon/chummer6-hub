using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingBrowserCallbackTests
{
    [Fact]
    public void Issue_and_exchange_browser_callback_links_install_without_claim_code()
    {
        using Fixture fixture = new();

        IssueInstallBrowserCallbackResponseDto issued = fixture.Service.IssueBrowserCallback(
            new IssueInstallBrowserCallbackRequestDto(
                InstallationId: "ins-browser-1",
                ArtifactId: "avalonia-win-x64-installer",
                ApplicationVersion: "6.0.1-preview",
                ChannelId: "preview",
                HeadId: "avalonia",
                Platform: "windows",
                Arch: "x64",
                CallbackUri: "chummer://install-link",
                PublicKey: "public-key",
                HostLabel: "Windows Workstation",
                InstallAccessClass: InstallAccessClasses.AccountRecommended),
            userId: "user-archon",
            subjectId: "subject-archon");

        Assert.False(issued.AlreadyClaimed);
        Assert.Equal(InstallBrowserCallbackStates.Pending, issued.Callback.Status);
        Assert.Equal("ins-browser-1", issued.Callback.InstallationId);
        Assert.Equal("avalonia-win-x64-installer", issued.Callback.ArtifactId);
        InstallLinkingSummaryDto summaryAfterIssue = fixture.Service.GetSummary("user-archon", "subject-archon");
        InstallBrowserCallbackDto pendingCallback = Assert.Single(summaryAfterIssue.PendingBrowserCallbacks!);
        Assert.Equal(issued.Callback.CallbackId, pendingCallback.CallbackId);

        ExchangeInstallBrowserCallbackResponseDto exchanged = fixture.Service.ExchangeBrowserCallback(
            new ExchangeInstallBrowserCallbackRequestDto(
                CallbackCode: issued.Callback.CallbackCode,
                InstallationId: "ins-browser-1",
                HeadId: "avalonia",
                ApplicationVersion: "6.0.1-preview",
                ChannelId: "preview",
                Platform: "windows",
                Arch: "x64",
                PublicKey: "public-key",
                HostLabel: "Windows Workstation"));

        Assert.False(exchanged.AlreadyClaimed);
        Assert.Equal(InstallBrowserCallbackStates.Redeemed, exchanged.Callback.Status);
        Assert.Equal(ClaimedInstallationStates.Active, exchanged.Installation.Status);
        Assert.Equal("avalonia-win-x64-installer", exchanged.Installation.ArtifactId);
        Assert.Equal("user-archon", exchanged.Installation.UserId);
        Assert.Equal("subject-archon", exchanged.Installation.SubjectId);
        Assert.Equal(InstallationGrantStates.Active, exchanged.Grant.Status);
        Assert.Equal("ins-browser-1", exchanged.Grant.InstallationId);

        ExchangeInstallBrowserCallbackResponseDto repeated = fixture.Service.ExchangeBrowserCallback(
            new ExchangeInstallBrowserCallbackRequestDto(
                CallbackCode: issued.Callback.CallbackCode,
                InstallationId: "ins-browser-1",
                HeadId: "avalonia",
                ApplicationVersion: "6.0.1-preview",
                ChannelId: "preview",
                Platform: "windows",
                Arch: "x64",
                PublicKey: "public-key",
                HostLabel: "Windows Workstation"));

        Assert.True(repeated.AlreadyClaimed);
        Assert.Equal(ClaimedInstallationStates.Active, repeated.Installation.Status);
        Assert.Equal(InstallationGrantStates.Active, repeated.Grant.Status);
        InstallLinkingSummaryDto summaryAfterExchange = fixture.Service.GetSummary("user-archon", "subject-archon");
        Assert.Empty(summaryAfterExchange.PendingBrowserCallbacks ?? Array.Empty<InstallBrowserCallbackDto>());
    }

    [Fact]
    public void Revoke_grant_unlinks_install_and_revokes_active_grants()
    {
        using Fixture fixture = new();

        IssueInstallBrowserCallbackResponseDto issued = fixture.Service.IssueBrowserCallback(
            new IssueInstallBrowserCallbackRequestDto(
                InstallationId: "ins-unlink-1",
                ArtifactId: "avalonia-linux-x64-installer",
                ApplicationVersion: "6.0.1-preview",
                ChannelId: "preview",
                HeadId: "avalonia",
                Platform: "linux",
                Arch: "x64",
                CallbackUri: "chummer://install-link",
                PublicKey: "public-key",
                HostLabel: "Linux Workstation",
                InstallAccessClass: InstallAccessClasses.AccountRecommended),
            userId: "user-archon",
            subjectId: "subject-archon");
        ExchangeInstallBrowserCallbackResponseDto exchanged = fixture.Service.ExchangeBrowserCallback(
            new ExchangeInstallBrowserCallbackRequestDto(
                CallbackCode: issued.Callback.CallbackCode,
                InstallationId: "ins-unlink-1",
                HeadId: "avalonia",
                ApplicationVersion: "6.0.1-preview",
                ChannelId: "preview",
                Platform: "linux",
                Arch: "x64",
                PublicKey: "public-key",
                HostLabel: "Linux Workstation"));

        RevokeInstallationGrantResponseDto revoked = fixture.Service.RevokeGrant(
            new RevokeInstallationGrantRequestDto(
                InstallationId: exchanged.Installation.InstallationId,
                AccessToken: exchanged.Grant.AccessToken));

        Assert.Equal(ClaimedInstallationStates.Revoked, revoked.Installation.Status);
        InstallationGrantDto revokedGrant = Assert.Single(revoked.RevokedGrants);
        Assert.Equal(exchanged.Grant.GrantId, revokedGrant.GrantId);
        Assert.Equal(InstallationGrantStates.Revoked, revokedGrant.Status);
        Assert.Null(fixture.Service.ResolveInstallationForGrant(
            exchanged.Installation.InstallationId,
            exchanged.Grant.AccessToken));
        InstallLinkingSummaryDto summary = fixture.Service.GetSummary("user-archon", "subject-archon");
        Assert.Contains(summary.ClaimedInstallations ?? Array.Empty<ClaimedInstallationDto>(),
            item => string.Equals(item.InstallationId, "ins-unlink-1", StringComparison.Ordinal)
                    && string.Equals(item.Status, ClaimedInstallationStates.Revoked, StringComparison.Ordinal));
        Assert.Empty(summary.ActiveGrants ?? Array.Empty<InstallationGrantDto>());
    }

    [Fact]
    public void Redeemed_callback_retry_survives_encrypted_reload_without_rotating_grant()
    {
        using Fixture fixture = new();
        (IssueInstallBrowserCallbackResponseDto issued, ExchangeInstallBrowserCallbackResponseDto exchanged) =
            CreateBrowserLink(fixture, "ins-reload-1");

        fixture.Reload();

        ExchangeInstallBrowserCallbackResponseDto repeated = RepeatExchange(
            fixture,
            issued.Callback.CallbackCode,
            issued.Callback.InstallationId);

        Assert.True(repeated.AlreadyClaimed);
        Assert.Equal(exchanged.Installation, repeated.Installation);
        Assert.Equal(exchanged.Grant.GrantId, repeated.Grant.GrantId);
        Assert.True(SecretsMatch(exchanged.Grant.AccessToken, repeated.Grant.AccessToken));
    }

    [Fact]
    public void Revocation_scrubs_redeemed_callback_and_replay_cannot_reactivate_installation()
    {
        using Fixture fixture = new();
        (IssueInstallBrowserCallbackResponseDto issued, ExchangeInstallBrowserCallbackResponseDto exchanged) =
            CreateBrowserLink(fixture, "ins-revoke-replay-1");

        fixture.Service.RevokeGrant(new RevokeInstallationGrantRequestDto(
            exchanged.Installation.InstallationId,
            exchanged.Grant.AccessToken));
        fixture.Reload();

        InstallLinkingOperationException replay = Assert.Throws<InstallLinkingOperationException>(() =>
            RepeatExchange(fixture, issued.Callback.CallbackCode, issued.Callback.InstallationId));
        Assert.Equal(StatusCodes.Status404NotFound, replay.StatusCode);
        InstallLinkingSummaryDto summary = fixture.Service.GetSummary("user-archon", "subject-archon");
        ClaimedInstallationDto installation = Assert.Single(
            summary.ClaimedInstallations!,
            item => string.Equals(item.InstallationId, issued.Callback.InstallationId, StringComparison.Ordinal));
        Assert.Equal(ClaimedInstallationStates.Revoked, installation.Status);
        Assert.Empty(summary.ActiveGrants ?? []);
    }

    [Fact]
    public void Grant_refresh_scrubs_redeemed_callback_and_old_code_cannot_read_rotated_grant()
    {
        using Fixture fixture = new();
        (IssueInstallBrowserCallbackResponseDto issued, ExchangeInstallBrowserCallbackResponseDto exchanged) =
            CreateBrowserLink(fixture, "ins-refresh-replay-1");

        RefreshInstallationGrantResponseDto refreshed = fixture.Service.RefreshGrant(
            new RefreshInstallationGrantRequestDto(
                exchanged.Installation.InstallationId,
                exchanged.Grant.AccessToken,
                ApplicationVersion: "6.0.2-preview"));
        fixture.Reload();

        InstallLinkingOperationException replay = Assert.Throws<InstallLinkingOperationException>(() =>
            RepeatExchange(fixture, issued.Callback.CallbackCode, issued.Callback.InstallationId));
        Assert.Equal(StatusCodes.Status404NotFound, replay.StatusCode);
        Assert.Null(fixture.Service.ResolveInstallationForGrant(
            exchanged.Installation.InstallationId,
            exchanged.Grant.AccessToken));
        Assert.NotNull(fixture.Service.ResolveInstallationForGrant(
            refreshed.Installation.InstallationId,
            refreshed.Grant.AccessToken));
        Assert.NotEqual(exchanged.Grant.GrantId, refreshed.Grant.GrantId);
    }

    [Fact]
    public void Second_callback_rotation_scrubs_first_callback_without_disclosing_new_grant()
    {
        using Fixture fixture = new();
        (IssueInstallBrowserCallbackResponseDto first, ExchangeInstallBrowserCallbackResponseDto firstExchange) =
            CreateBrowserLink(fixture, "ins-callback-rotation-1");
        IssueInstallBrowserCallbackResponseDto second = fixture.Service.IssueBrowserCallback(
            new IssueInstallBrowserCallbackRequestDto(
                first.Callback.InstallationId,
                "avalonia-linux-x64-installer",
                "6.0.2-preview",
                "preview",
                "avalonia",
                "linux",
                "x64",
                "chummer://install-link",
                "rotated-public-key",
                "Linux Workstation",
                InstallAccessClasses.AccountRecommended),
            "user-archon",
            "subject-archon");
        ExchangeInstallBrowserCallbackResponseDto secondExchange = RepeatExchange(
            fixture,
            second.Callback.CallbackCode,
            second.Callback.InstallationId);
        fixture.Reload();

        InstallLinkingOperationException firstReplay = Assert.Throws<InstallLinkingOperationException>(() =>
            RepeatExchange(fixture, first.Callback.CallbackCode, first.Callback.InstallationId));
        Assert.Equal(StatusCodes.Status404NotFound, firstReplay.StatusCode);
        ExchangeInstallBrowserCallbackResponseDto secondReplay = RepeatExchange(
            fixture,
            second.Callback.CallbackCode,
            second.Callback.InstallationId);
        Assert.True(secondReplay.AlreadyClaimed);
        Assert.NotEqual(firstExchange.Grant.GrantId, secondExchange.Grant.GrantId);
        Assert.Equal(secondExchange.Grant.GrantId, secondReplay.Grant.GrantId);
        Assert.True(SecretsMatch(secondExchange.Grant.AccessToken, secondReplay.Grant.AccessToken));
    }

    [Fact]
    public void Fresh_claim_rotation_scrubs_redeemed_callback_without_disclosing_claim_grant()
    {
        using Fixture fixture = new();
        (IssueInstallBrowserCallbackResponseDto issued, ExchangeInstallBrowserCallbackResponseDto exchanged) =
            CreateBrowserLink(fixture, "ins-claim-rotation-1");
        var artifact = new PublicReleaseArtifactDto(
            Id: "avalonia-linux-x64-installer",
            Platform: "linux",
            Url: "/downloads/files/avalonia-linux-x64-installer.tar.gz",
            Sha256: new string('a', 64),
            InstallAccessClass: InstallAccessClasses.AccountRecommended);
        var manifest = new PublicReleaseManifestDto(
            Version: "6.0.2-preview",
            Channel: "preview",
            PublishedAt: DateTimeOffset.UtcNow,
            Downloads: [artifact]);
        DownloadDispatchResult dispatch = fixture.Service.IssueDownload(
            manifest,
            artifact,
            "user-archon",
            "subject-archon",
            forceNewClaim: true);
        RedeemInstallClaimResponseDto claim = fixture.Service.RedeemClaim(
            new RedeemInstallClaimRequestDto(
                dispatch.ClaimTicket!.ClaimCode,
                issued.Callback.InstallationId,
                "avalonia",
                "6.0.2-preview",
                "preview",
                "linux",
                "x64",
                "claim-public-key",
                "Linux Workstation"));
        fixture.Reload();

        InstallLinkingOperationException replay = Assert.Throws<InstallLinkingOperationException>(() =>
            RepeatExchange(fixture, issued.Callback.CallbackCode, issued.Callback.InstallationId));
        Assert.Equal(StatusCodes.Status404NotFound, replay.StatusCode);
        Assert.NotEqual(exchanged.Grant.GrantId, claim.Grant.GrantId);
        Assert.NotNull(fixture.Service.ResolveInstallationForGrant(
            claim.Installation.InstallationId,
            claim.Grant.AccessToken));
    }

    [Fact]
    public void Expired_redeemed_callback_is_scrubbed_on_persisted_reload_and_cannot_replay()
    {
        using Fixture fixture = new();
        (IssueInstallBrowserCallbackResponseDto issued, _) = CreateBrowserLink(
            fixture,
            "ins-expired-replay-1");
        DateTimeOffset now = DateTimeOffset.UtcNow;
        lock (fixture.Store.Gate)
        {
            fixture.Store.BrowserCallbacksById[issued.Callback.CallbackId] = issued.Callback with
            {
                Status = InstallBrowserCallbackStates.Redeemed,
                CreatedAtUtc = now.AddMinutes(-10),
                ExpiresAtUtc = now.AddMinutes(-5),
                CallbackUri = null
            };
            fixture.Store.PersistLocked();
        }

        fixture.Reload();

        InstallBrowserCallbackDto retained = fixture.Store.BrowserCallbacksById[issued.Callback.CallbackId];
        Assert.True(string.IsNullOrEmpty(retained.CallbackCode));
        Assert.Null(retained.CallbackUri);
        InstallLinkingOperationException replay = Assert.Throws<InstallLinkingOperationException>(() =>
            RepeatExchange(fixture, issued.Callback.CallbackCode, issued.Callback.InstallationId));
        Assert.Equal(StatusCodes.Status404NotFound, replay.StatusCode);
    }

    [Fact]
    public void Protected_preupgrade_unbound_redeemed_callback_is_revoked_during_load_migration()
    {
        using Fixture fixture = new();
        (IssueInstallBrowserCallbackResponseDto issued, ExchangeInstallBrowserCallbackResponseDto exchanged) =
            CreateBrowserLink(fixture, "ins-unbound-upgrade-1");

        InstallBrowserCallbackDto callback = exchanged.Callback;
        byte[] preFixSnapshot = JsonSerializer.SerializeToUtf8Bytes(
            new
            {
                Receipts = Array.Empty<object>(),
                ClaimTickets = Array.Empty<object>(),
                BrowserCallbacks = new[]
                {
                    new
                    {
                        callback.CallbackId,
                        CallbackCode = issued.Callback.CallbackCode,
                        callback.InstallationId,
                        callback.ArtifactId,
                        callback.Channel,
                        callback.Version,
                        callback.InstallAccessClass,
                        Status = InstallBrowserCallbackStates.Redeemed,
                        callback.CreatedAtUtc,
                        ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(10),
                        callback.UserId,
                        callback.SubjectId,
                        callback.PublicKey,
                        callback.HeadId,
                        callback.Platform,
                        callback.Arch,
                        callback.HostLabel,
                        CallbackUri = (string?)null
                    }
                },
                Installations = new[] { exchanged.Installation },
                Grants = new[] { exchanged.Grant },
                PersonalizedInstallScripts = Array.Empty<object>()
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web));
        try
        {
            using (JsonDocument document = JsonDocument.Parse(preFixSnapshot))
            {
                JsonElement serializedCallback = document.RootElement
                    .GetProperty("browserCallbacks")[0];
                Assert.False(serializedCallback.TryGetProperty("grantId", out _));
            }

            fixture.LoadProtectedPreFixEnvelope(preFixSnapshot);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(preFixSnapshot);
        }

        fixture.Reload();
        InstallBrowserCallbackDto migrated = fixture.Store.BrowserCallbacksById[issued.Callback.CallbackId];
        Assert.Equal(InstallBrowserCallbackStates.Revoked, migrated.Status);
        Assert.True(string.IsNullOrEmpty(migrated.CallbackCode));
        Assert.Null(migrated.CallbackUri);
        InstallLinkingOperationException replay = Assert.Throws<InstallLinkingOperationException>(() =>
            RepeatExchange(fixture, issued.Callback.CallbackCode, issued.Callback.InstallationId));
        Assert.Equal(StatusCodes.Status404NotFound, replay.StatusCode);
    }

    private static (
        IssueInstallBrowserCallbackResponseDto Issued,
        ExchangeInstallBrowserCallbackResponseDto Exchanged) CreateBrowserLink(
        Fixture fixture,
        string installationId)
    {
        IssueInstallBrowserCallbackResponseDto issued = fixture.Service.IssueBrowserCallback(
            new IssueInstallBrowserCallbackRequestDto(
                installationId,
                "avalonia-linux-x64-installer",
                "6.0.1-preview",
                "preview",
                "avalonia",
                "linux",
                "x64",
                "chummer://install-link",
                "public-key",
                "Linux Workstation",
                InstallAccessClasses.AccountRecommended),
            "user-archon",
            "subject-archon");
        return (issued, RepeatExchange(
            fixture,
            issued.Callback.CallbackCode,
            issued.Callback.InstallationId));
    }

    private static ExchangeInstallBrowserCallbackResponseDto RepeatExchange(
        Fixture fixture,
        string callbackCode,
        string installationId)
        => fixture.Service.ExchangeBrowserCallback(
            new ExchangeInstallBrowserCallbackRequestDto(
                callbackCode,
                installationId,
                "avalonia",
                "6.0.1-preview",
                "preview",
                "linux",
                "x64",
                "public-key",
                "Linux Workstation"));

    private static bool SecretsMatch(string left, string right)
    {
        byte[] leftBytes = Encoding.ASCII.GetBytes(left);
        byte[] rightBytes = Encoding.ASCII.GetBytes(right);
        try
        {
            return leftBytes.Length == rightBytes.Length
                && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(leftBytes);
            CryptographicOperations.ZeroMemory(rightBytes);
        }
    }

    private sealed class Fixture : IDisposable
    {
        private const string SnapshotProtectionPurpose =
            "Chummer.Run.Api.InstallLinkingStore.snapshot.v2";
        private readonly string _tempRoot;
        private readonly string _storePath;
        private readonly IConfiguration _configuration;
        private readonly IDataProtectionProvider _dataProtectionProvider;

        public Fixture()
        {
            _tempRoot = Path.Combine(Path.GetTempPath(), "chummer-install-browser-callback-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_tempRoot);
            _storePath = Path.Combine(_tempRoot, "install-linking-store.json");
            _configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = _storePath,
                    ["CHUMMER_INSTALL_BROWSER_CALLBACK_LIFETIME_MINUTES"] = "15"
                })
                .Build();
            _dataProtectionProvider = DataProtectionProvider.Create(
                Path.Combine(_tempRoot, "install-linking-keys"));
            Store = CreateStore();
            Service = new InstallLinkingService(Store, _configuration);
        }

        public InstallLinkingStore Store { get; private set; }

        public InstallLinkingService Service { get; private set; }

        public void Reload()
        {
            Store.Dispose();
            Store = CreateStore();
            Service = new InstallLinkingService(Store, _configuration);
        }

        public void LoadProtectedPreFixEnvelope(ReadOnlySpan<byte> snapshotBytes)
        {
            Store.Dispose();
            File.Delete($"{_storePath}.floor");

            IDataProtector protector = _dataProtectionProvider.CreateProtector(SnapshotProtectionPurpose);
            string protectedPayload = protector.Protect(Convert.ToBase64String(snapshotBytes));
            byte[] envelopeBytes = JsonSerializer.SerializeToUtf8Bytes(
                new
                {
                    Format = "chummer.install-linking-store",
                    Version = 2,
                    Generation = 1,
                    ProtectedPayload = protectedPayload
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web));
            try
            {
                File.WriteAllBytes(_storePath, envelopeBytes);
                if (!OperatingSystem.IsWindows())
                {
                    File.SetUnixFileMode(
                        _storePath,
                        UnixFileMode.UserRead | UnixFileMode.UserWrite);
                }
            }
            finally
            {
                CryptographicOperations.ZeroMemory(envelopeBytes);
            }

            Store = CreateStore();
            Service = new InstallLinkingService(Store, _configuration);
        }

        private InstallLinkingStore CreateStore()
            => new(
                _configuration,
                _dataProtectionProvider,
                NullLogger<InstallLinkingStore>.Instance);

        public void Dispose()
        {
            Store.Dispose();
            (_dataProtectionProvider as IDisposable)?.Dispose();
            if (Directory.Exists(_tempRoot))
            {
                Directory.Delete(_tempRoot, recursive: true);
            }
        }
    }
}
