using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.Privacy;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class AccountErasureJournalStoreTests
{
    private static readonly DateTimeOffset Baseline = new(2026, 8, 12, 12, 0, 0, TimeSpan.Zero);

    [Fact]
    public void Completed_entry_carries_restore_fence_and_prunes_after_audit_retention()
    {
        using Fixture fixture = new();
        AccountErasureJournalStore store = fixture.CreateStore();
        string subjectKey = new('a', 64);
        store.Begin(subjectKey, new string('b', 64), Baseline);
        store.RecordComponent(subjectKey, Component("community", 4, 'c'), Baseline);
        store.MarkIdentityPending(subjectKey, "subject-private", Baseline);

        AccountErasureJournalEntry completed = store.Complete(
            subjectKey,
            Component("identity", 2, 'd'),
            Baseline,
            new string('e', 64));

        Assert.Equal(Baseline.AddDays(35), completed.RestoreFenceUntilUtc);
        Assert.Equal(Baseline.AddDays(365), completed.RetainUntilUtc);
        Assert.Equal(0, store.PruneExpired(Baseline.AddDays(365).AddTicks(-1)));
        Assert.Equal(1, store.PruneExpired(Baseline.AddDays(365)));
        Assert.Null(store.Find(subjectKey));
    }

    [Fact]
    public void Authenticated_journal_rejects_local_tampering()
    {
        using Fixture fixture = new();
        AccountErasureJournalStore store = fixture.CreateStore();
        store.Begin(new string('a', 64), null, Baseline);
        string payload = File.ReadAllText(store.StoragePath);
        File.WriteAllText(store.StoragePath, payload.Replace(new string('a', 64), new string('f', 64), StringComparison.Ordinal));

        Assert.Throws<InvalidDataException>(() => fixture.CreateStore());
    }

    [Fact]
    public void Production_requires_explicit_journal_path_separate_from_mutable_stores()
    {
        IConfiguration missing = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ASPNETCORE_ENVIRONMENT"] = "Production",
                ["CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY"] = Fixture.HmacKey
            })
            .Build();
        Assert.Throws<InvalidOperationException>(() => new AccountErasureJournalStore(
            missing,
            new EphemeralDataProtectionProvider(),
            NullLogger<AccountErasureJournalStore>.Instance));

        string sharedPath = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"), "shared.json");
        IConfiguration shared = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ASPNETCORE_ENVIRONMENT"] = "Production",
                ["CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY"] = Fixture.HmacKey,
                ["CHUMMER_ACCOUNT_ERASURE_JOURNAL_PATH"] = sharedPath,
                ["CHUMMER_COMMUNITY_STORE_PATH"] = sharedPath
            })
            .Build();
        Assert.Throws<InvalidOperationException>(() => new AccountErasureJournalStore(
            shared,
            new EphemeralDataProtectionProvider(),
            NullLogger<AccountErasureJournalStore>.Instance));
    }

    private static AccountErasureComponentReceipt Component(string name, int count, char digest)
        => new(name, true, count, new string(digest, 64));

    private sealed class Fixture : IDisposable
    {
        internal static readonly string HmacKey = Convert.ToBase64String(
            Enumerable.Repeat((byte)0x5a, 32).ToArray());
        private readonly string _directory = Path.Combine(
            Path.GetTempPath(),
            "chummer-account-erasure-journal-tests",
            Guid.NewGuid().ToString("N"));
        private readonly IDataProtectionProvider _dataProtection = new EphemeralDataProtectionProvider();

        public Fixture()
        {
            Directory.CreateDirectory(_directory);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_ACCOUNT_ERASURE_JOURNAL_PATH"] = Path.Combine(_directory, "journal.json"),
                    ["CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY"] = HmacKey
                })
                .Build();
        }

        public IConfiguration Configuration { get; }

        public AccountErasureJournalStore CreateStore()
            => new(Configuration, _dataProtection, NullLogger<AccountErasureJournalStore>.Instance);

        public void Dispose()
        {
            try
            {
                Directory.Delete(_directory, recursive: true);
            }
            catch
            {
                // Best-effort cleanup for test temp files.
            }
        }
    }
}
