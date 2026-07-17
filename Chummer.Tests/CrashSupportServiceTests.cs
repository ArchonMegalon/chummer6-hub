using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class CrashSupportServiceTests
{
    [Fact]
    public void SubmitCapsRequestBodySize()
    {
        MethodInfo method = typeof(SupportCrashesController).GetMethod(nameof(SupportCrashesController.Submit))
            ?? throw new InvalidOperationException("Missing Submit method.");
        RequestSizeLimitAttribute requestSize = method.GetCustomAttribute<RequestSizeLimitAttribute>()
            ?? throw new InvalidOperationException("Submit is missing RequestSizeLimitAttribute.");

        Assert.Equal(CrashSupportService.MaxRequestBodyBytes, ((IRequestSizeLimitMetadata)requestSize).MaxRequestBodySize);
    }

    [Fact]
    public void SubmitReturnsBadRequestForOversizedExceptionDetail()
    {
        using var fixture = new CrashSupportFixture();
        CrashEnvelope envelope = fixture.CreateEnvelope(ExceptionDetail: new string('d', CrashSupportService.MaxExceptionDetailLength + 1));

        ActionResult<CrashIntakeAcceptedResponse> result = fixture.Controller.Submit(envelope);

        BadRequestObjectResult badRequest = Assert.IsType<BadRequestObjectResult>(result.Result);
        Assert.Contains(nameof(CrashEnvelope.ExceptionDetail), badRequest.Value?.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void ServiceRejectsOversizedLogTailEntry()
    {
        using var fixture = new CrashSupportFixture();
        CrashEnvelope envelope = fixture.CreateEnvelope(LogTail: [new string('l', CrashSupportService.MaxLogTailLineLength + 1)]);

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.Submit(envelope));

        Assert.Equal(nameof(CrashEnvelope.LogTail), error.ParamName);
    }

    private sealed class CrashSupportFixture : IDisposable
    {
        private readonly string _root;

        public CrashSupportFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-crash-support-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(_root, "support-store.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking-store.json"),
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                    ["CHUMMER_SUPPORT_ATTACHMENT_ROOT"] = Path.Combine(_root, "attachments")
                })
                .Build();

            InstallLinkingStore installLinkingStore = new(
                configuration,
                DataProtectionProvider.Create(Path.Combine(_root, "install-linking-keys")),
                NullLogger<InstallLinkingStore>.Instance);
            InstallLinkingService installLinking = new(installLinkingStore, configuration);
            CommunityStore communityStore = new(configuration, NullLogger<CommunityStore>.Instance);
            RewardService rewards = new(communityStore);
            SupportStore supportStore = new(configuration, NullLogger<SupportStore>.Instance);
            SupportAttachmentStorageService attachments = new(configuration);
            SupportProgressEmailWorkflowService progressEmails = new(
                new HttpClient(new StubHandler()),
                configuration,
                NullLogger<SupportProgressEmailWorkflowService>.Instance);
            SupportCaseService supportCases = new(
                supportStore,
                attachments,
                rewards,
                progressEmails,
                NullLogger<SupportCaseService>.Instance);

            Service = new CrashSupportService(
                supportStore,
                supportCases,
                installLinking,
                NullLogger<CrashSupportService>.Instance);
            Controller = new SupportCrashesController(Service, configuration)
            {
                ControllerContext = new ControllerContext
                {
                    HttpContext = new DefaultHttpContext()
                }
            };
        }

        public CrashSupportService Service { get; }
        public SupportCrashesController Controller { get; }

        public CrashEnvelope CreateEnvelope(
            string? ExceptionDetail = null,
            IReadOnlyList<string>? LogTail = null)
            => new(
                CrashId: "crash-001",
                HeadId: "avalonia",
                ApplicationVersion: "0.9.4",
                RuntimeVersion: ".NET 10",
                OperatingSystem: "Linux",
                ProcessArchitecture: "X64",
                CrashFingerprint: "fingerprint-001",
                ExceptionType: "System.Exception",
                ExceptionMessage: "boom",
                ExceptionDetail: ExceptionDetail ?? "System.Exception: boom",
                CapturedAtUtc: DateTimeOffset.UtcNow,
                ReleaseChannel: "stable",
                Platform: "linux",
                DesktopHead: "avalonia",
                RuntimeHead: "desktop-runtime",
                LastActionCategory: "startup",
                LogTail: LogTail ?? ["line one", "line two"]);

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class StubHandler : HttpMessageHandler
    {
        protected override HttpResponseMessage Send(HttpRequestMessage request, CancellationToken cancellationToken)
            => new(HttpStatusCode.OK)
            {
                Content = new StringContent("{\"status\":\"disabled\"}", Encoding.UTF8, "application/json")
            };

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(Send(request, cancellationToken));
    }
}
