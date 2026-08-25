using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Text;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class BuildGhostLiveSupportSessionStoreTests
{
    [TestMethod]
    public async Task Session_survives_store_restart_and_join_url_is_encrypted_at_rest()
    {
        using StoreDirectory directory = StoreDirectory.Create();
        IConfiguration configuration = directory.Configuration();
        StoredBuildGhostLiveSupportSession expected = Stored();

        using (EncryptedFileBuildGhostLiveSupportSessionStore first = new(configuration))
        {
            Assert.IsEmpty(first.BlockingReasons);
            Assert.IsTrue(await first.WriteAsync(expected, CancellationToken.None));
        }

        string raw = string.Join("", Directory.GetFiles(directory.Path).Select(File.ReadAllText));
        Assert.IsFalse(raw.Contains("zoom.us", StringComparison.OrdinalIgnoreCase));
        Assert.IsFalse(raw.Contains("pwd=secret", StringComparison.Ordinal));

        using EncryptedFileBuildGhostLiveSupportSessionStore restarted = new(configuration);
        StoredBuildGhostLiveSupportSession? actual = await restarted.ReadAsync(
            expected.OwnerScopeHash,
            expected.Session.RequestId,
            expected.WorkspaceId,
            expected.SourceDigest,
            CancellationToken.None);
        bool? reserved = await restarted.HasOpenReservationAsync(
            DateTimeOffset.Parse("2026-08-25T00:30:00Z"),
            CancellationToken.None);
        bool? releasedAfterExpiry = await restarted.HasOpenReservationAsync(
            DateTimeOffset.Parse("2026-08-25T01:00:01Z"),
            CancellationToken.None);
        Assert.IsNotNull(actual);
        Assert.AreEqual(expected.Schema, actual.Schema);
        Assert.AreEqual(expected.OwnerScopeHash, actual.OwnerScopeHash);
        Assert.AreEqual(expected.WorkspaceId, actual.WorkspaceId);
        Assert.AreEqual(expected.SourceDigest, actual.SourceDigest);
        Assert.AreEqual(expected.RequestFingerprint, actual.RequestFingerprint);
        Assert.AreEqual(expected.Session.RequestId, actual.Session.RequestId);
        Assert.AreEqual(expected.Session.JoinUrl, actual.Session.JoinUrl);
        Assert.AreEqual(expected.Session.MeetingBotReceiptDigest, actual.Session.MeetingBotReceiptDigest);
        Assert.IsTrue(reserved.HasValue && reserved.Value);
        Assert.IsTrue(releasedAfterExpiry.HasValue);
        Assert.IsFalse(releasedAfterExpiry.Value);
    }

    [TestMethod]
    public async Task Symlinked_session_entry_makes_capacity_indeterminate_and_fail_closed()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using StoreDirectory directory = StoreDirectory.Create();
        string target = System.IO.Path.Combine(directory.Path, "poison.payload");
        string link = System.IO.Path.Combine(directory.Path, "poison.session");
        File.WriteAllText(target, "not-a-session");
        File.CreateSymbolicLink(link, target);

        using EncryptedFileBuildGhostLiveSupportSessionStore store = new(directory.Configuration());
        bool? reserved = await store.HasOpenReservationAsync(
            DateTimeOffset.Parse("2026-08-25T00:30:00Z"),
            CancellationToken.None);

        Assert.IsFalse(reserved.HasValue);
    }

    [TestMethod]
    public async Task Same_owner_and_request_id_in_different_workspaces_cannot_overwrite_an_active_reservation()
    {
        using StoreDirectory directory = StoreDirectory.Create();
        using EncryptedFileBuildGhostLiveSupportSessionStore store = new(directory.Configuration());
        StoredBuildGhostLiveSupportSession active = Stored();
        StoredBuildGhostLiveSupportSession otherWorkspace = active with
        {
            WorkspaceId = "handoff-other",
            SourceDigest = Digest('d'),
            RequestFingerprint = Digest('e'),
            Session = active.Session with
            {
                Status = BuildGhostLiveSupportStatuses.Unavailable,
                JoinUrl = null,
                JoinUrlExpiresAtUtc = null,
                BlockingReasons = ["live-support-provider-capacity-reservation-open"]
            }
        };

        Assert.IsTrue(await store.WriteAsync(active, CancellationToken.None));
        Assert.IsTrue(await store.WriteAsync(otherWorkspace, CancellationToken.None));

        StoredBuildGhostLiveSupportSession? activeReadback = await store.ReadAsync(
            active.OwnerScopeHash,
            active.Session.RequestId,
            active.WorkspaceId,
            active.SourceDigest,
            CancellationToken.None);
        StoredBuildGhostLiveSupportSession? otherReadback = await store.ReadAsync(
            otherWorkspace.OwnerScopeHash,
            otherWorkspace.Session.RequestId,
            otherWorkspace.WorkspaceId,
            otherWorkspace.SourceDigest,
            CancellationToken.None);
        bool? reserved = await store.HasOpenReservationAsync(
            DateTimeOffset.Parse("2026-08-25T00:30:00Z"),
            CancellationToken.None);

        Assert.HasCount(2, Directory.GetFiles(directory.Path, "*.session"));
        Assert.IsNotNull(activeReadback);
        Assert.AreEqual(BuildGhostLiveSupportStatuses.Ready, activeReadback.Session.Status);
        Assert.AreEqual(active.Session.JoinUrl, activeReadback.Session.JoinUrl);
        Assert.IsNotNull(otherReadback);
        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, otherReadback.Session.Status);
        Assert.IsTrue(reserved.HasValue && reserved.Value);
    }

    [TestMethod]
    public void Provisioning_reserves_until_reconciliation_and_ready_reserves_until_exact_expiry()
    {
        BuildGhostLiveSupportSessionProjection ready = Stored().Session;
        BuildGhostLiveSupportSessionProjection uncertain = ready with
        {
            Status = BuildGhostLiveSupportStatuses.ProvisioningAvatar,
            JoinUrl = null,
            JoinUrlExpiresAtUtc = null,
            UpdatedAtUtc = DateTimeOffset.Parse("2026-08-20T00:00:00Z")
        };

        Assert.IsTrue(EncryptedFileBuildGhostLiveSupportSessionStore.ReservesProviderCapacity(
            uncertain,
            DateTimeOffset.Parse("2026-08-25T00:00:00Z")));
        Assert.IsTrue(EncryptedFileBuildGhostLiveSupportSessionStore.ReservesProviderCapacity(
            ready,
            DateTimeOffset.Parse("2026-08-25T00:59:59Z")));
        Assert.IsFalse(EncryptedFileBuildGhostLiveSupportSessionStore.ReservesProviderCapacity(
            ready,
            DateTimeOffset.Parse("2026-08-25T01:00:01Z")));
    }

    private static StoredBuildGhostLiveSupportSession Stored()
    {
        BuildGhostDefaultSupportProjection fallback = new(
            BuildGhostSupportChannelKinds.RookVidBoard,
            ToughTongueBuildGhostPersonaIds.Rook,
            ToughTongueBuildGhostPersonaIds.RookAvatar,
            ToughTongueBuildGhostPersonaIds.RookVidBoardSupport,
            "/media/support/rook.mp4",
            Digest('0'),
            true,
            "ready",
            "Rook remains available.",
            []);
        BuildGhostLiveSupportSessionProjection session = new(
            ToughTongueBuildGhostContractVersions.LiveSupportSessionV1,
            "live-request-1",
            BuildGhostSupportChannelKinds.LivePhotorealMeeting,
            BuildGhostLiveSupportStatuses.Ready,
            BuildGhostLiveMeetingProviders.Zoom,
            new Uri("https://chummer.zoom.us/j/123?pwd=secret"),
            DateTimeOffset.Parse("2026-08-25T01:00:00Z"),
            ToughTongueBuildGhostPersonaIds.StockDefaultAvatar,
            "photorealistic-provider-managed",
            true,
            true,
            BuildGhostLiveSupportDisclosureContract.CurrentVersion,
            BuildGhostLiveSupportDisclosureContract.ComputeDigest(),
            Digest('1'),
            Digest('2'),
            Digest('3'),
            Digest('4'),
            DateTimeOffset.Parse("2026-08-25T00:00:00Z"),
            DateTimeOffset.Parse("2026-08-25T00:01:00Z"),
            fallback,
            []);
        return new StoredBuildGhostLiveSupportSession(
            EncryptedFileBuildGhostLiveSupportSessionStore.StoredSchema,
            Digest('a'),
            "handoff-test",
            Digest('c'),
            Digest('b'),
            session);
    }

    private static string Digest(char value) => "sha256:" + new string(value, 64);

    private sealed class StoreDirectory : IDisposable
    {
        private StoreDirectory(string path)
        {
            Path = path;
        }

        public string Path { get; }

        public static StoreDirectory Create()
        {
            string path = System.IO.Path.Combine(
                System.IO.Path.GetTempPath(),
                $"chummer-live-support-store-{Guid.NewGuid():N}");
            Directory.CreateDirectory(path);
            if (!OperatingSystem.IsWindows())
            {
                File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
            }
            return new StoreDirectory(path);
        }

        public IConfiguration Configuration()
            => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            {
                [EncryptedFileBuildGhostLiveSupportSessionStore.DirectoryConfigurationKey] = Path,
                [EncryptedFileBuildGhostLiveSupportSessionStore.EncryptionKeyConfigurationKey] =
                    Convert.ToBase64String(Enumerable.Range(1, 32).Select(static value => (byte)value).ToArray()),
                [EncryptedFileBuildGhostLiveSupportSessionStore.SingleInstanceConfigurationKey] = "true"
            }).Build();

        public void Dispose()
        {
            if (Directory.Exists(Path))
            {
                Directory.Delete(Path, recursive: true);
            }
        }
    }
}
