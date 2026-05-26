using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class WorkspaceNoticeSafetyTests
{
    [Theory]
    [InlineData("Closed workspace uuid 7b0d6ecf-5fd8-4d87-9a8b-b9aa3cc6d130 needs review.")]
    [InlineData("workspace closed pending manual resolution")]
    [InlineData("workspace decision is blocked until review")]
    [InlineData("7b0d6ecf-5fd8-4d87-9a8b-b9aa3cc6d130")]
    [InlineData("portable exchange for uuid 7b0d6ecf-5fd8-4d87-9a8b-b9aa3cc6d130")]
    public void LooksLikeInternalWorkspaceLeakReturnsTrueForUnsafeSummaries(string summary)
    {
        Assert.True(WorkspaceNoticeSafety.LooksLikeInternalWorkspaceLeak(summary));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("Portable exchange is ready for inspect-only or merge across 3 dossier(s) and 2 packet(s).")]
    [InlineData("GM operations still need governed receipts.")]
    [InlineData("Stage a new travel prefetch receipt before departure so offline continuity stays bounded and explicit.")]
    public void LooksLikeInternalWorkspaceLeakReturnsFalseForSafeSummaries(string? summary)
    {
        Assert.False(WorkspaceNoticeSafety.LooksLikeInternalWorkspaceLeak(summary));
    }
}
