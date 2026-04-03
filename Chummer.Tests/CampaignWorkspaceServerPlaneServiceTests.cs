using System.Reflection;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignWorkspaceServerPlaneServiceTests
{
    [Fact]
    public void PrepLibraryQueryTokensSplitAndNormalizePunctuation()
    {
        IReadOnlyList<string> tokens = InvokeBuildTokens("  Opposition, season-control / audit  ");

        Assert.Contains("opposition", tokens);
        Assert.Contains("season", tokens);
        Assert.Contains("control", tokens);
        Assert.Contains("audit", tokens);
    }

    [Fact]
    public void PrepLibraryQueryMatchingRequiresAllTokensAcrossSearchSurfaces()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "opposition:demo",
            Kind: "opposition_packet",
            Title: "Neon Cradle opposition packet",
            Summary: "Active pressure stays tied to the current season lane.",
            BindingSummary: "Bound to the return lane and audit receipts.",
            Reusable: true,
            SearchTerms: ["opposition", "season", "roster"],
            EvidenceLines: ["GM audit line: roster movement receipt captured."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        IReadOnlyList<string> positiveTokens = InvokeBuildTokens("opposition audit");
        IReadOnlyList<string> negativeTokens = InvokeBuildTokens("opposition matrix");

        Assert.True(InvokeMatches(packet, positiveTokens));
        Assert.False(InvokeMatches(packet, negativeTokens));
    }

    private static IReadOnlyList<string> InvokeBuildTokens(string? queryText)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildPrepLibraryQueryTokens", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildPrepLibraryQueryTokens was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<string>>(method.Invoke(null, [queryText]));
    }

    private static bool InvokeMatches(GovernedPrepPacketSummary packet, IReadOnlyList<string> queryTokens)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("MatchesPrepLibraryQuery", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("MatchesPrepLibraryQuery was not found.");

        return Assert.IsType<bool>(method.Invoke(null, [packet, queryTokens]));
    }
}
