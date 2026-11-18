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
        StringAssert.Contains(view, "provider-specific photorealistic-video canary");
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
        StringAssert.Contains(
            support,
            "href=\"/account/alice/@Uri.EscapeDataString(Model.HandoffId)\"");
        StringAssert.Contains(
            support,
            "action=\"/account/alice/@Uri.EscapeDataString(Model.HandoffId)/live-support\"");
        StringAssert.Contains(handoff, ">Live support options</a>");
        StringAssert.Contains(
            handoff,
            "href=\"/account/alice/@Uri.EscapeDataString(handoff.HandoffId)/live-support\"");
        Assert.IsFalse(support.Contains("href=\"/alice\"", StringComparison.Ordinal));
        Assert.IsFalse(handoff.Contains(">Request live support</a>", StringComparison.Ordinal));
    }

    [TestMethod]
    public void Rook_text_fallback_is_canonical_across_the_gateway_and_signed_in_page_model()
    {
        string gateway = ReadRepositoryFile(
            "Chummer.Run.Api",
            "Services",
            "KarmaForge",
            "BuildGhostLiveSupportGateway.cs");
        string controller = ReadRepositoryFileThree(
            "Chummer.Run.Api",
            "Controllers",
            "BuildGhostLiveSupportController.cs");

        StringAssert.Contains(
            gateway,
            "BuildGhostDefaultSupportContract.DeterministicRookTextFallback");
        StringAssert.Contains(
            controller,
            "BuildGhostDefaultSupportContract.DeterministicRookTextFallback");
        Assert.IsFalse(
            controller.Contains(
                "Rook is available with deterministic text while the VidBoard clip is unavailable or stale.",
                StringComparison.Ordinal));
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
        StringAssert.Contains(
            controller,
            "private const string PagePathTemplate = \"/account/alice/{handoffId}/live-support\";");
        StringAssert.Contains(controller, "[HttpGet(PagePathTemplate)]");
        StringAssert.Contains(controller, "[HttpPost(PagePathTemplate)]");
        StringAssert.Contains(
            controller,
            "[HttpGet(\"/account/alice/{handoffId}/live-support/{requestId}\")]");
        StringAssert.Contains(controller, "Redirect($\"/login?next={Uri.EscapeDataString(pagePath)}\")");
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
