using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Services.Support;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class SupportProgressEmailWorkflowServiceTests
{
    [Fact]
    public void SendFixAvailable_AttachesLinkedInstallRailAndVersionMetadata()
    {
        var requests = new List<CapturedRequest>();
        using var http = new HttpClient(new CapturingHandler(requests));
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_API_TOKEN"] = "ea-token",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_PRINCIPAL_ID"] = "principal-1",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BINDING_ID"] = "binding-1",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_API_KEY"] = "emailit-token",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BASE_URL"] = "https://ea.test",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_BASE_URL"] = "https://emailit.test",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_PUBLIC_BASE_URL"] = "https://chummer.run"
            })
            .Build();
        var service = new SupportProgressEmailWorkflowService(http, configuration, NullLogger<SupportProgressEmailWorkflowService>.Instance);
        var supportCase = new SupportCaseProjection(
            CaseId: "case-install-rail",
            ClusterKey: "cluster-install",
            Kind: SupportCaseKinds.InstallHelp,
            Status: SupportCaseStatuses.ReleasedToReporterChannel,
            Title: "Linux update recovery",
            Summary: "Install update follow-through needs a reporter check.",
            Detail: "The affected linked install needs the fixed preview.",
            CandidateOwnerRepo: "chummer6-hub",
            DesignImpactSuspected: false,
            CreatedAtUtc: DateTimeOffset.Parse("2026-04-15T00:00:00Z"),
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-15T01:00:00Z"),
            Source: SupportCaseSourceKinds.HubAccount,
            ReporterEmail: "runner@example.invalid",
            ReporterUserId: "usr-1",
            ReporterSubjectId: "subject-1",
            InstallationId: "install-1",
            ApplicationVersion: "0.7.0-preview",
            ReleaseChannel: "preview",
            HeadId: "avalonia",
            Platform: "linux",
            Arch: "x64",
            FixedVersion: "0.7.1-preview",
            FixedChannel: "preview");

        SupportProgressEmailDispatchResult result = service.SendFixAvailable(
            supportCase,
            new SupportCaseNotificationRequest(
                Note: "Reporter-ready fix is available.",
                Actor: "hub",
                Channel: "account_history",
                DownloadUrl: "https://chummer.run/downloads"));

        Assert.Equal("sent", result.State);
        Assert.Equal("https://chummer.run/account/access", result.InstallRailUrl);
        string emailBody = Assert.Single(requests, static item => item.Url == "https://emailit.test/emails").Body;
        Assert.Contains("Open the affected claimed desktop install first", emailBody, StringComparison.Ordinal);
        Assert.Contains("Browser fallback for relink or recovery: https://chummer.run/account/access", emailBody, StringComparison.Ordinal);
        Assert.Contains("Affected install: install-1", emailBody, StringComparison.Ordinal);
        Assert.Contains("Target build: preview 0.7.1-preview", emailBody, StringComparison.Ordinal);

        string dispatchBody = Assert.Single(requests, static item => item.Url == "https://ea.test/v1/tools/execute").Body;
        using JsonDocument dispatchJson = JsonDocument.Parse(dispatchBody);
        JsonElement metadata = dispatchJson.RootElement
            .GetProperty("payload_json")
            .GetProperty("metadata");
        Assert.Equal("install-1", metadata.GetProperty("installation_id").GetString());
        Assert.Equal("0.7.0-preview", metadata.GetProperty("application_version").GetString());
        Assert.Equal("0.7.1-preview", metadata.GetProperty("fixed_version").GetString());
        Assert.Equal("preview", metadata.GetProperty("fixed_channel").GetString());
        Assert.Equal("https://chummer.run/account/access", metadata.GetProperty("install_rail_url").GetString());
    }

    [Fact]
    public void SendFixAvailable_KeepsInstallHelpOnInstallRailEvenBeforeDeviceMetadataExists()
    {
        var requests = new List<CapturedRequest>();
        using var http = new HttpClient(new CapturingHandler(requests));
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_API_TOKEN"] = "ea-token",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_PRINCIPAL_ID"] = "principal-1",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BINDING_ID"] = "binding-1",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_API_KEY"] = "emailit-token",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BASE_URL"] = "https://ea.test",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_BASE_URL"] = "https://emailit.test",
                ["CHUMMER_SUPPORT_PROGRESS_EMAIL_PUBLIC_BASE_URL"] = "https://chummer.run"
            })
            .Build();
        var service = new SupportProgressEmailWorkflowService(http, configuration, NullLogger<SupportProgressEmailWorkflowService>.Instance);
        var supportCase = new SupportCaseProjection(
            CaseId: "case-install-help",
            ClusterKey: "cluster-install",
            Kind: SupportCaseKinds.InstallHelp,
            Status: SupportCaseStatuses.ReleasedToReporterChannel,
            Title: "Installer needs recovery",
            Summary: "Install follow-through needs a reporter check.",
            Detail: "The affected install was not linked yet when support accepted the case.",
            CandidateOwnerRepo: "chummer6-hub",
            DesignImpactSuspected: false,
            CreatedAtUtc: DateTimeOffset.Parse("2026-04-15T00:00:00Z"),
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-15T01:00:00Z"),
            Source: SupportCaseSourceKinds.HubAccount,
            ReporterEmail: "runner@example.invalid",
            ReporterUserId: "usr-1",
            ReporterSubjectId: "subject-1",
            FixedVersion: "0.7.1-preview",
            FixedChannel: "preview");

        SupportProgressEmailDispatchResult result = service.SendFixAvailable(
            supportCase,
            new SupportCaseNotificationRequest(
                Note: "Reporter-ready fix is available.",
                Actor: "hub",
                Channel: "account_history",
                DownloadUrl: "https://chummer.run/downloads"));

        Assert.Equal("sent", result.State);
        Assert.Equal("https://chummer.run/account/access", result.InstallRailUrl);
        string emailBody = Assert.Single(requests, static item => item.Url == "https://emailit.test/emails").Body;
        Assert.Contains("Open the affected claimed desktop install first", emailBody, StringComparison.Ordinal);
        Assert.Contains("Browser fallback for relink or recovery: https://chummer.run/account/access", emailBody, StringComparison.Ordinal);
        Assert.DoesNotContain("Affected install:", emailBody, StringComparison.Ordinal);

        string dispatchBody = Assert.Single(requests, static item => item.Url == "https://ea.test/v1/tools/execute").Body;
        using JsonDocument dispatchJson = JsonDocument.Parse(dispatchBody);
        JsonElement metadata = dispatchJson.RootElement
            .GetProperty("payload_json")
            .GetProperty("metadata");
        Assert.Equal("https://chummer.run/account/access", metadata.GetProperty("install_rail_url").GetString());
        Assert.False(metadata.TryGetProperty("installation_id", out _));
    }

    private sealed record CapturedRequest(string Url, string Body);

    private sealed class CapturingHandler(List<CapturedRequest> requests) : HttpMessageHandler
    {
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string body = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            requests.Add(new CapturedRequest(request.RequestUri!.ToString(), body));

            object payload = request.RequestUri!.AbsolutePath switch
            {
                "/v1/tools/execute" => new { target_ref = "delivery-1" },
                "/emails" => new { id = "emailit-1" },
                _ => new { status = "ok" }
            };

            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = JsonContent.Create(payload)
            };
        }
    }
}
