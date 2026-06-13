using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Xunit;

namespace Chummer.Tests;

public sealed class UserExperienceServiceTests
{
    [Fact]
    public void RecordWorkspacePrepLibrarySearch_tracks_workspace_scoped_deduplicated_history()
    {
        using Fixture fixture = new();
        fixture.Accounts.EnsureUser("subject.demo", "Runner Demo", "runner@example.invalid");

        fixture.Experience.RecordWorkspacePrepLibrarySearch("subject.demo", "ws-a", " Opposition ");
        fixture.Experience.RecordWorkspacePrepLibrarySearch("subject.demo", "ws-b", " scene ");
        fixture.Experience.RecordWorkspacePrepLibrarySearch("subject.demo", "ws-a", "opposition");

        for (int i = 0; i < 6; i++)
        {
            fixture.Experience.RecordWorkspacePrepLibrarySearch("subject.demo", "ws-a", $"a{i}");
            fixture.Experience.RecordWorkspacePrepLibrarySearch("subject.demo", "ws-b", $"b{i}");
        }

        HubUserExperienceDto experience = fixture.Experience.GetOrCreate("subject.demo");
        IReadOnlyList<WorkspacePrepLibrarySearchHistoryItem> history = experience.WorkspacePrepLibrarySearchHistory ?? [];
        IReadOnlyList<WorkspacePrepLibrarySearchHistoryItem> workspaceAHistory = history
            .Where(item => string.Equals(item.WorkspaceId, "ws-a", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        IReadOnlyList<WorkspacePrepLibrarySearchHistoryItem> workspaceBHistory = history
            .Where(item => string.Equals(item.WorkspaceId, "ws-b", StringComparison.OrdinalIgnoreCase))
            .ToArray();

        Assert.InRange(workspaceAHistory.Count, 1, 10);
        Assert.InRange(workspaceBHistory.Count, 1, 10);
        Assert.Single(workspaceAHistory, item => string.Equals(item.Query, "opposition", StringComparison.OrdinalIgnoreCase));
        Assert.All(workspaceAHistory, item => Assert.Equal("ws-a", item.WorkspaceId));
        Assert.All(workspaceBHistory, item => Assert.Equal("ws-b", item.WorkspaceId));
    }

    [Fact]
    public void RecordWorkspacePrepLibrarySearch_global_history_enforces_total_limit()
    {
        using Fixture fixture = new();
        fixture.Accounts.EnsureUser("subject.demo", "Runner Demo", "runner@example.invalid");

        for (int workspace = 1; workspace <= 4; workspace++)
        {
            string workspaceId = $"ws-{workspace}";
            for (int i = 0; i < 12; i++)
            {
                fixture.Experience.RecordWorkspacePrepLibrarySearch("subject.demo", workspaceId, $"q{i}");
            }
        }

        HubUserExperienceDto experience = fixture.Experience.GetOrCreate("subject.demo");
        IReadOnlyList<WorkspacePrepLibrarySearchHistoryItem> history = experience.WorkspacePrepLibrarySearchHistory ?? Array.Empty<WorkspacePrepLibrarySearchHistoryItem>();

        Assert.Equal(30, history.Count);
        for (int workspace = 1; workspace <= 4; workspace++)
        {
            string workspaceId = $"ws-{workspace}";
            int count = history.Count(item => string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase));
            Assert.InRange(count, 0, 10);
        }
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), $"chummer-tests-user-experience-{Guid.NewGuid():N}");

        public Fixture()
        {
            Directory.CreateDirectory(_root);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                })
                .Build();

            Store = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(Store, logger: NullLogger<AccountService>.Instance);
            Experience = new UserExperienceService(Store, Accounts);
        }

        public IConfiguration Configuration { get; }
        public CommunityStore Store { get; }
        public AccountService Accounts { get; }
        public UserExperienceService Experience { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
