using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Runtime.CompilerServices;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class BuildGhostLiveSupportPresentationPolicyTests
{
    [TestMethod]
    public void Live_support_view_keeps_terminal_statuses_safe_and_prevents_duplicate_meetings()
    {
        string view = ReadRepositoryFile("Chummer.Run.Api", "Views", "Accounts", "BuildGhostLiveSupport.cshtml");

        StringAssert.Contains(view, "BuildGhostLiveSupportStatuses.Ready");
        StringAssert.Contains(view, "BuildGhostLiveSupportStatuses.Expired");
        StringAssert.Contains(view, "BuildGhostLiveSupportStatuses.Unavailable");
        StringAssert.Contains(view, "suppressMeetingCreation");
        StringAssert.Contains(view, "No second meeting will be created.");
        StringAssert.Contains(view, "Selected provider:");
        StringAssert.Contains(view, "Link available until:");
        StringAssert.Contains(view, "BuildGhostLiveSupportDisclosureContract.RecordingDisclosure");
        StringAssert.Contains(view, "BuildGhostLiveSupportDisclosureContract.ExternalProviderProcessingDisclosure");
        Assert.IsFalse(view.Contains("session.BlockingReasons", StringComparison.Ordinal));
    }

    [TestMethod]
    public void VidBoard_and_handoff_views_keep_accessible_fallback_and_options_copy()
    {
        string support = ReadRepositoryFile("Chummer.Run.Api", "Views", "Accounts", "BuildGhostLiveSupport.cshtml");
        string handoff = ReadRepositoryFile("Chummer.Run.Api", "Views", "Accounts", "BuildHandoff.cshtml");

        StringAssert.Contains(support, "aria-describedby=\"rook-vidboard-text-alternative\"");
        StringAssert.Contains(support, "Text alternative and transcript status");
        StringAssert.Contains(support, "No separate transcript or captions are claimed on this page.");
        StringAssert.Contains(support, "Continue with Rook's text help");
        StringAssert.Contains(handoff, ">Live support options</a>");
        Assert.IsFalse(handoff.Contains(">Request live support</a>", StringComparison.Ordinal));
    }

    [TestMethod]
    public void Signed_in_controller_keeps_antiforgery_and_server_derived_handoff_authority()
    {
        string controller = ReadRepositoryFileThree(
            "Chummer.Run.Api",
            "Controllers",
            "BuildGhostLiveSupportController.cs");

        StringAssert.Contains(controller, "[AutoValidateAntiforgeryToken]");
        StringAssert.Contains(controller, "[RequestSizeLimit(16 * 1024)]");
        StringAssert.Contains(controller, "identity.RequireSubjectAsync");
        StringAssert.Contains(controller, "ResolveHandoff(subject, handoffId)");
        StringAssert.Contains(controller, "BuildWorkspaceId(handoff)");
        StringAssert.Contains(controller, "$\"{ownerScopeHash}\\n{workspaceId}\\n{form.IdempotencyKey}\"");
        StringAssert.Contains(controller, "BuildSourceDigest(handoff)");
        StringAssert.Contains(controller, "BuildGhostLiveSupportDisclosureContract.ComputeDigest()");
        StringAssert.Contains(controller, "BuildGhostLiveSupportGateway");
        StringAssert.Contains(controller, "ShouldRedirectToDurableStatus(session)");
        StringAssert.Contains(controller, "BuildGhostLiveSupportStatuses.ProvisioningMeeting");
        StringAssert.Contains(controller, "BuildGhostLiveSupportStatuses.ProvisioningAvatar");
        Assert.IsFalse(controller.Contains("form.OwnerScopeHash", StringComparison.Ordinal));
        Assert.IsFalse(controller.Contains("form.WorkspaceId", StringComparison.Ordinal));
        Assert.IsFalse(controller.Contains("form.SourceDigest", StringComparison.Ordinal));
    }

    private static string ReadRepositoryFile(
        string first,
        string second,
        string third,
        string fourth,
        [CallerFilePath] string testSourcePath = "")
    {
        string projectDirectory = Path.GetDirectoryName(testSourcePath)
            ?? throw new InvalidOperationException("The test source directory is unavailable.");
        string repositoryRoot = Directory.GetParent(projectDirectory)?.FullName
            ?? throw new InvalidOperationException("The repository root is unavailable.");
        return File.ReadAllText(Path.Combine(repositoryRoot, first, second, third, fourth));
    }

    private static string ReadRepositoryFileThree(
        string first,
        string second,
        string third,
        [CallerFilePath] string testSourcePath = "")
    {
        string projectDirectory = Path.GetDirectoryName(testSourcePath)
            ?? throw new InvalidOperationException("The test source directory is unavailable.");
        string repositoryRoot = Directory.GetParent(projectDirectory)?.FullName
            ?? throw new InvalidOperationException("The repository root is unavailable.");
        return File.ReadAllText(Path.Combine(repositoryRoot, first, second, third));
    }
}
