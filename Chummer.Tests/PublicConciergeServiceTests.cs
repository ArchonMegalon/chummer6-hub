using Chummer.Run.Api.Services;
using Chummer.Run.Api.ViewModels;
using Chummer.Contracts.Receipts;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicConciergeServiceTests
{
    [Fact]
    public void PublicConciergeController_UsesPlainPublicCopy()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicConciergeController.cs"));

        Assert.Contains("Guided setup without extra noise.", controller, StringComparison.Ordinal);
        Assert.Contains("Short answers about the current release and what changed.", controller, StringComparison.Ordinal);
        Assert.Contains("Continue the invite, review the primer, or ask for onboarding help without losing your place.", controller, StringComparison.Ordinal);
        Assert.Contains("Primer and join stay in Chummer", controller, StringComparison.Ordinal);
        Assert.Contains("Open written view", controller, StringComparison.Ordinal);
        Assert.Contains("Open video view", controller, StringComparison.Ordinal);

        foreach (string forbidden in new[]
                 {
                     "bounded first-party wrapper",
                     "first-party truth",
                     "first-party lane",
                     "first-party page",
                     "governed invite",
                     "first-party account rails",
                     "Join rail",
                     "packet posture",
                     "video posture",
                     "recovery posture",
                     "install truth",
                     "download truth",
                     "creator consult"
                 })
        {
            Assert.DoesNotContain(forbidden, controller, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void BuildPage_UsesConfiguredWidgetAndKeepsFirstPartyFallbackVisible()
    {
        using TempRoot temp = new("public-concierge-widget");
        IConfiguration configuration = BuildConfiguration(temp.Root, new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_CONCIERGE_DOWNLOADS_WIDGET_URL"] = "https://widget.example.invalid/downloads"
        });

        PublicConciergeService service = CreateService(configuration);

        PublicConciergePageViewModel page = service.BuildPage(
            "downloads",
            CreateChrome(authenticated: false),
            requestedLocale: "de-AT",
            acceptLanguage: null);

        Assert.Equal("downloads_concierge", page.FlowId);
        Assert.Equal("de-AT", page.Locale);
        Assert.False(page.LocaleFallbackUsed);
        Assert.Equal("Optional guided widget live", page.Widget.StatusLabel);
        Assert.Equal("widget.example.invalid", page.Widget.HostLabel);
        Assert.Contains("Chummer path stays visible", page.ProofPoints, StringComparer.OrdinalIgnoreCase);
        Assert.Equal(4, page.Branches.Count);
        Assert.Contains(page.Branches, branch => branch.BranchId == "download_now" && branch.ActionHref.Contains("/downloads/concierge/download_now", StringComparison.Ordinal));
        Assert.Contains(page.Branches, branch => branch.BranchId == "unresolved_setup_issue" && branch.DestinationLabel.Contains("Support follow-up", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ResolveBranchRedirect_UsesConfiguredExternalHandoffAndPersistsReceipt()
    {
        using TempRoot temp = new("public-concierge-redirect");
        IConfiguration configuration = BuildConfiguration(temp.Root, new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_CONCIERGE_DOWNLOADS_BRANCH_UNRESOLVED_SETUP_ISSUE_URL"] = "https://support.example.invalid/setup"
        });

        PublicConciergeStore store = new(configuration, NullLogger<PublicConciergeStore>.Instance);
        PublicConciergeService service = CreateService(configuration, store);

        ConciergeRedirectResolution resolution = service.ResolveBranchRedirect(
            surfaceKey: "downloads",
            branchId: "unresolved_setup_issue",
            authenticated: false,
            requestedLocale: "en-US",
            acceptLanguage: null);

        Assert.StartsWith("https://support.example.invalid/setup", resolution.RedirectHref, StringComparison.Ordinal);
        Assert.Contains("concierge_flow_id=downloads_concierge", resolution.RedirectHref, StringComparison.Ordinal);
        Assert.Contains("locale=en-US", resolution.RedirectHref, StringComparison.Ordinal);
        Assert.Equal("Support follow-up", resolution.DestinationLabel);

        PublicConciergeBranchReceipt receipt = Assert.Single(store.BranchReceiptsById.Values);
        Assert.Equal(resolution.ReceiptId, receipt.ReceiptId);
        Assert.Equal("downloads", receipt.SurfaceKey);
        Assert.Equal("unresolved_setup_issue", receipt.BranchId);
        Assert.Equal("external_redirect", receipt.TargetKind);
        Assert.NotNull(receipt.Envelope);
        Assert.Equal("public_concierge_branch", receipt.Envelope!.ReceiptKind);
        Assert.Equal("public.concierge", receipt.Envelope.OwnerScope);
        Assert.Equal(ReceiptExposureClasses.PublicSafe, receipt.Envelope.ExposureClass);
        Assert.Equal("external_redirect", receipt.Envelope.ReviewState);
    }

    [Fact]
    public void RecordWebhook_DeduplicatesReceiptsAndCreatesModerationItemsForTestimonialCapture()
    {
        using TempRoot temp = new("public-concierge-webhook");
        IConfiguration configuration = BuildConfiguration(temp.Root, new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_CONCIERGE_PROVIDER_FACEPOP_WEBHOOK_SECRET"] = "top-secret"
        });

        PublicConciergeStore store = new(configuration, NullLogger<PublicConciergeStore>.Instance);
        PublicConciergeService service = CreateService(configuration, store);
        HeaderDictionary headers = new()
        {
            ["X-Chummer-Concierge-Webhook-Secret"] = "top-secret"
        };

        string payload = """
            {
              "flow_id": "testimonial_capture",
              "branch_id": "video_review",
              "correlation_id": "corr-1",
              "locale": "en-US",
              "event_type": "submitted",
              "status": "received",
              "provider_receipt_id": "provider-1",
              "summary": "Video testimonial captured",
              "media_kind": "video_review",
              "publication_ref": "pub-1"
            }
            """;

        ConciergeWebhookResult first = service.RecordWebhook(
            "facepop",
            System.Text.Json.JsonDocument.Parse(payload).RootElement,
            headers,
            "127.0.0.1");
        ConciergeWebhookResult second = service.RecordWebhook(
            "facepop",
            System.Text.Json.JsonDocument.Parse(payload).RootElement,
            headers,
            "127.0.0.1");

        Assert.Equal("verified", first.VerificationState);
        Assert.Equal(first.ReceiptId, second.ReceiptId);
        Assert.Single(store.WebhookReceiptsById);
        PublicConciergeWebhookReceipt receipt = Assert.Single(store.WebhookReceiptsById.Values);
        Assert.Equal("testimonial_capture", receipt.FlowId);
        Assert.Equal("video_review", receipt.BranchId);
        Assert.Equal("provider-1", receipt.ProviderReceiptId);
        Assert.NotNull(receipt.Envelope);
        Assert.Equal("public_concierge_webhook", receipt.Envelope!.ReceiptKind);
        Assert.Equal("public.concierge", receipt.Envelope.OwnerScope);
        Assert.Equal(ReceiptExposureClasses.Internal, receipt.Envelope.ExposureClass);
        Assert.Equal("verified", receipt.Envelope.ReviewState);
        PublicConciergeModerationItem moderation = Assert.Single(store.ModerationItemsById.Values);
        Assert.Equal(receipt.ReceiptId, moderation.SourceReceiptId);
        Assert.Equal("pending_moderation", moderation.Status);
    }

    private static PublicConciergeService CreateService(IConfiguration configuration, PublicConciergeStore? store = null)
    {
        PublicCanonFileLoader canon = new(configuration);
        PublicRouteCatalogService routes = new(canon);
        return new PublicConciergeService(
            canon,
            routes,
            store ?? new PublicConciergeStore(configuration, NullLogger<PublicConciergeStore>.Instance),
            configuration,
            NullLogger<PublicConciergeService>.Instance);
    }

    private static IConfiguration BuildConfiguration(string tempRoot, IReadOnlyDictionary<string, string?> overrides)
    {
        Dictionary<string, string?> settings = new(StringComparer.OrdinalIgnoreCase)
        {
            ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
            ["CHUMMER_PUBLIC_CONCIERGE_STORE_PATH"] = Path.Combine(tempRoot, "public-concierge-store.json")
        };

        foreach ((string key, string? value) in overrides)
        {
            settings[key] = value;
        }

        return new ConfigurationBuilder()
            .AddInMemoryCollection(settings)
            .Build();
    }

    private static SiteChromeViewModel CreateChrome(bool authenticated)
        => new(
            Title: "Concierge",
            Description: "Bounded concierge test chrome",
            CurrentPath: "/downloads/concierge",
            PrimaryNavigation: Array.Empty<PublicNavigationLink>(),
            SecondaryNavigation: Array.Empty<PublicNavigationLink>(),
            UtilityNavigation: Array.Empty<PublicNavigationLink>(),
            HeaderActions: Array.Empty<SiteChromeActionViewModel>(),
            PublicPrimaryCta: null,
            Authenticated: authenticated,
            SignedInLabel: authenticated ? "Runner" : null,
            FooterCanonicalSource: "test",
            FooterGeneratedNote: "test");

    private sealed class TempRoot : IDisposable
    {
        public TempRoot(string prefix)
        {
            Root = Path.Combine(Path.GetTempPath(), $"{prefix}-{Guid.NewGuid():N}");
            Directory.CreateDirectory(Root);
        }

        public string Root { get; }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(Root))
                {
                    Directory.Delete(Root, recursive: true);
                }
            }
            catch
            {
            }
        }
    }
}
