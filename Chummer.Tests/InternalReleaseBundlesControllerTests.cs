using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InternalReleaseBundlesControllerTests
{
    [Fact]
    public async Task UploadBundleAcceptsSignedInReleaseUploadTicket()
    {
        using ControllerFixture fixture = new();
        ReleaseUploadTicketIssueResult issued = fixture.ReleaseUploadTickets.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = $"Bearer {issued.Ticket}";

        ActionResult<ReleaseBundlePromotionResult> result = await fixture.Controller.UploadBundle(bundle: null, CancellationToken.None);

        BadRequestObjectResult badRequest = Assert.IsType<BadRequestObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
    }

    private sealed class ControllerFixture : IDisposable
    {
        private readonly string _root;

        public ControllerFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "internal-release-bundles-controller-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = Path.Combine(_root, "downloads"),
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://chummer.run/auth/google/callback",
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = Path.Combine(_root, "canon"),
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking.json")
                })
                .Build();

            IDataProtectionProvider dataProtectionProvider = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            ReleaseUploadTickets = new ReleaseUploadTicketService(dataProtectionProvider, Configuration);
            var releasePromotion = new ReleaseBundlePromotionService(Configuration, NullLogger<ReleaseBundlePromotionService>.Instance);
            var manifestService = new PublicReleaseManifestService(Configuration);
            var accounts = new AccountService(new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance));
            var installLinking = new InstallLinkingService(new InstallLinkingStore(Configuration, NullLogger<InstallLinkingStore>.Instance));
            Controller = new InternalReleaseBundlesController(
                releasePromotion,
                Configuration,
                ReleaseUploadTickets,
                manifestService,
                accounts,
                installLinking);
        }

        public IConfiguration Configuration { get; }

        public ReleaseUploadTicketService ReleaseUploadTickets { get; }

        public InternalReleaseBundlesController Controller { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
