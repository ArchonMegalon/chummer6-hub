using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Services.Support;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class SupportStoreAccountErasureTests
{
    [Fact]
    public void EraseReporter_removes_private_cases_and_indexes_and_is_idempotent()
    {
        using Fixture fixture = new();
        fixture.Store.CasesById["case-delete"] = Case("case-delete", "user-delete", "subject-delete");
        fixture.Store.CasesById["case-keep"] = Case("case-keep", "user-keep", "subject-keep");
        fixture.Store.CaseIdByClusterKey["cluster-delete"] = "case-delete";
        fixture.Store.CaseIdByClusterKey["cluster-keep"] = "case-keep";
        fixture.Store.CrashCaseIdByWorkItemId["work-delete"] = "case-delete";
        fixture.Store.PersistLocked();

        SupportReporterErasureResult result = fixture.Store.EraseReporter("user-delete", "subject-delete");

        Assert.True(result.Erased);
        Assert.Equal(1, result.CasesRemoved);
        Assert.Equal(2, result.IndexRecordsRemoved);
        Assert.DoesNotContain("case-delete", fixture.Store.CasesById.Keys, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("case-keep", fixture.Store.CasesById.Keys, StringComparer.OrdinalIgnoreCase);
        SupportStore reloaded = fixture.Reload();
        Assert.Single(reloaded.CasesById);
        Assert.Single(reloaded.CaseIdByClusterKey);
        Assert.Empty(reloaded.CrashCaseIdByWorkItemId);

        SupportReporterErasureResult repeated = fixture.Store.EraseReporter("user-delete", "subject-delete");
        Assert.False(repeated.Erased);
        Assert.Equal(0, repeated.CasesRemoved);
    }

    [Fact]
    public void EraseReporter_rolls_back_if_durable_write_fails()
    {
        using Fixture fixture = new();
        fixture.Store.CasesById["case-delete"] = Case("case-delete", "user-delete", "subject-delete");
        fixture.Store.CaseIdByClusterKey["cluster-delete"] = "case-delete";
        fixture.Store.AccountErasurePersistenceFaultInjector =
            () => throw new IOException("simulated durable write failure");

        Assert.Throws<IOException>(() => fixture.Store.EraseReporter("user-delete", "subject-delete"));

        Assert.Contains("case-delete", fixture.Store.CasesById.Keys, StringComparer.OrdinalIgnoreCase);
        Assert.Equal("case-delete", fixture.Store.CaseIdByClusterKey["cluster-delete"]);
        Assert.Contains("case-delete", fixture.Reload().CasesById.Keys, StringComparer.OrdinalIgnoreCase);
    }

    private static SupportCaseProjection Case(string caseId, string userId, string subjectId)
        => new(
            CaseId: caseId,
            ClusterKey: $"cluster-{caseId}",
            Kind: "account",
            Status: "open",
            Title: "Private request",
            Summary: "Private summary",
            Detail: "Private detail",
            CandidateOwnerRepo: "chummer6-hub",
            DesignImpactSuspected: false,
            CreatedAtUtc: DateTimeOffset.UtcNow,
            UpdatedAtUtc: DateTimeOffset.UtcNow,
            Source: "account",
            ReporterUserId: userId,
            ReporterSubjectId: subjectId);

    private sealed class Fixture : IDisposable
    {
        private readonly string _directory = Path.Combine(
            Path.GetTempPath(),
            "chummer-support-erasure-tests",
            Guid.NewGuid().ToString("N"));

        public Fixture()
        {
            Directory.CreateDirectory(_directory);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_SUPPORT_STORE_PATH"] = StoragePath
                })
                .Build();
            Store = new SupportStore(Configuration, NullLogger<SupportStore>.Instance);
        }

        public IConfiguration Configuration { get; }
        public string StoragePath => Path.Combine(_directory, "support.json");
        public SupportStore Store { get; }

        public SupportStore Reload()
            => new(Configuration, NullLogger<SupportStore>.Instance);

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
