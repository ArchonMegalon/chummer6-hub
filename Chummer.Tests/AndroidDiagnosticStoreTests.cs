using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class AndroidDiagnosticStoreTests
{
    [Fact]
    public async Task DisabledByDefaultDoesNotCreateFilesOrExposeReadback()
    {
        using var fixture = new Fixture(enabled: false);
        Assert.False(fixture.Store.Enabled);
        Assert.False(Directory.Exists(fixture.DirectoryPath));
        Assert.False(fixture.Store.AuthorizeReader("Bearer " + Fixture.ReaderToken));
        Assert.Equal(503, Assert.IsType<StatusCodeResult>((await fixture.Controller.Read(default)).Result).StatusCode);
        Assert.Equal(503, Assert.IsType<StatusCodeResult>((await fixture.Controller.Submit(fixture.Report(), default)).Result).StatusCode);
        await fixture.Store.PruneAsync(default);
        Assert.False(Directory.Exists(fixture.DirectoryPath));
    }

    [Fact]
    public async Task AdmissionIsDurableAndExactRetriesReturnTheSameReceipt()
    {
        using var fixture = new Fixture();
        var report = fixture.Report();
        var receipt = await fixture.Store.SubmitAsync(report, default);
        fixture.Store.Dispose();
        fixture.Clock.Now += TimeSpan.FromMinutes(5);
        fixture.Store = new(fixture.Configuration, fixture.Clock);
        Assert.Equal(receipt, await fixture.Store.SubmitAsync(report, default));
        Assert.Equal(report, Assert.Single((await fixture.Store.ReadAsync(default)).Items).Report);
        await Assert.ThrowsAsync<AndroidDiagnosticConflictException>(() =>
            fixture.Store.SubmitAsync(report with { Error = AndroidDiagnosticError.Network }, default));
        Assert.DoesNotContain(Fixture.ReaderToken, await File.ReadAllTextAsync(fixture.Snapshot));
    }

    [Fact]
    public async Task ReadbackNeedsItsOwnScopedCredential()
    {
        using var fixture = new Fixture();
        await fixture.Store.SubmitAsync(fixture.Report(), default);
        var controller = fixture.Controller;
        Assert.IsType<UnauthorizedResult>((await controller.Read(default)).Result);
        foreach (string header in new[] { "Bearer wrong", "Basic " + Fixture.ReaderToken, "Bearer " + new string('x', 300) })
        {
            controller.Request.Headers.Authorization = header;
            Assert.IsType<UnauthorizedResult>((await controller.Read(default)).Result);
        }
        controller.Request.Headers.Authorization = "Bearer " + Fixture.ReaderToken;
        var result = Assert.IsType<OkObjectResult>((await controller.Read(default)).Result);
        Assert.Single(Assert.IsType<AndroidDiagnosticReadback>(result.Value).Items);
        Assert.Equal("no-store", controller.Response.Headers.CacheControl.ToString());
    }

    [Fact]
    public async Task HourlyLimitIsDurableButDoesNotRejectAnExactRetry()
    {
        using var fixture = new Fixture();
        var first = fixture.Report();
        var receipt = await fixture.Store.SubmitAsync(first, default);
        for (int i = 1; i < AndroidDiagnosticStore.MaximumHourlyReports; i++)
            await fixture.Store.SubmitAsync(fixture.Report(), default);
        fixture.Store.Dispose();
        fixture.Store = new(fixture.Configuration, fixture.Clock);
        Assert.Equal(receipt, await fixture.Store.SubmitAsync(first, default));
        var controller = fixture.Controller;
        Assert.Equal(429, Assert.IsType<StatusCodeResult>((await controller.Submit(fixture.Report(), default)).Result).StatusCode);
        Assert.Equal("3600", controller.Response.Headers.RetryAfter.ToString());
        fixture.Clock.Now += TimeSpan.FromHours(1) + TimeSpan.FromSeconds(1);
        await fixture.Store.SubmitAsync(fixture.Report(), default);
        Assert.Equal(65, (await fixture.Store.ReadAsync(default)).Items.Count);
    }

    [Fact]
    public async Task TotalCountAndBytesStayBounded()
    {
        using var fixture = new Fixture();
        for (int i = 0; i < AndroidDiagnosticStore.MaximumReports; i++)
        {
            if (i > 0 && i % AndroidDiagnosticStore.MaximumHourlyReports == 0)
                fixture.Clock.Now += TimeSpan.FromHours(1) + TimeSpan.FromSeconds(1);
            await fixture.Store.SubmitAsync(fixture.Report(), default);
        }
        fixture.Clock.Now += TimeSpan.FromHours(1) + TimeSpan.FromSeconds(1);
        await Assert.ThrowsAsync<AndroidDiagnosticCapacityException>(() => fixture.Store.SubmitAsync(fixture.Report(), default));
        Assert.Equal(AndroidDiagnosticStore.MaximumReports, (await fixture.Store.ReadAsync(default)).Items.Count);
        Assert.InRange(new FileInfo(fixture.Snapshot).Length, 1, AndroidDiagnosticStore.MaximumSnapshotBytes);
    }

    [Fact]
    public async Task ExpiryRemovesReportsOnReadAndIdleMaintenance()
    {
        using var fixture = new Fixture();
        await fixture.Store.SubmitAsync(fixture.Report(), default);
        fixture.Clock.Now += TimeSpan.FromDays(2) + TimeSpan.FromSeconds(1);
        Assert.Empty((await fixture.Store.ReadAsync(default)).Items);
        Assert.Equal("[]", await File.ReadAllTextAsync(fixture.Snapshot));
        await fixture.Store.SubmitAsync(fixture.Report(), default);
        fixture.Clock.Now += TimeSpan.FromDays(2) + TimeSpan.FromSeconds(1);
        await fixture.Store.PruneAsync(default);
        Assert.Equal("[]", await File.ReadAllTextAsync(fixture.Snapshot));
    }

    [Theory]
    [InlineData("version")]
    [InlineData("id")]
    [InlineData("old")]
    [InlineData("future")]
    [InlineData("area")]
    [InlineData("operation")]
    [InlineData("outcome")]
    [InlineData("error")]
    [InlineData("duration")]
    public async Task RejectsInvalidMetadataWithoutWriting(string field)
    {
        using var fixture = new Fixture();
        var report = fixture.Report();
        report = field switch
        {
            "version" => report with { VersionCode = 0 },
            "id" => report with { ReportId = Guid.Empty },
            "old" => report with { ObservedAtUtc = fixture.Clock.Now.AddDays(-3) },
            "future" => report with { ObservedAtUtc = fixture.Clock.Now.AddMinutes(6) },
            "area" => report with { Area = (AndroidDiagnosticArea)100 },
            "operation" => report with { Operation = (AndroidDiagnosticOperation)100 },
            "outcome" => report with { Outcome = (AndroidDiagnosticOutcome)100 },
            "error" => report with { Error = (AndroidDiagnosticError)100 },
            _ => report with { ElapsedMilliseconds = 86400001 }
        };
        Assert.IsType<BadRequestResult>((await fixture.Controller.Submit(report, default)).Result);
        Assert.False(File.Exists(fixture.Snapshot));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task InvalidStorageFailsClosedWithoutReplacingIt(bool oversized)
    {
        using var fixture = new Fixture();
        string corrupt = oversized ? new string('x', AndroidDiagnosticStore.MaximumSnapshotBytes + 1) : "not-json";
        await File.WriteAllTextAsync(fixture.Snapshot, corrupt);
        Assert.Equal(503, Assert.IsType<StatusCodeResult>((await fixture.Controller.Submit(fixture.Report(), default)).Result).StatusCode);
        Assert.Equal(corrupt, await File.ReadAllTextAsync(fixture.Snapshot));
    }

    [Fact]
    public async Task ConcurrentExactRetriesProduceOneObservation()
    {
        using var fixture = new Fixture();
        var report = fixture.Report();
        var receipts = await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => fixture.Store.SubmitAsync(report, default)));
        Assert.All(receipts, receipt => Assert.Equal(receipts[0], receipt));
        Assert.Single((await fixture.Store.ReadAsync(default)).Items);
    }

    [Fact]
    public async Task CorruptStorageDoesNotCrashTheRetentionWorkerOrHost()
    {
        using var fixture = new Fixture();
        await File.WriteAllTextAsync(fixture.Snapshot, new string('x', AndroidDiagnosticStore.MaximumSnapshotBytes + 1));
        using var worker = new AndroidDiagnosticRetentionWorker(fixture.Store,
            NullLogger<AndroidDiagnosticRetentionWorker>.Instance);
        await worker.StartAsync(default);
        Assert.False(worker.ExecuteTask!.IsFaulted);
        await worker.StopAsync(default);
        Assert.Equal(AndroidDiagnosticStore.MaximumSnapshotBytes + 1, new FileInfo(fixture.Snapshot).Length);
    }

    [Fact]
    public async Task RealHttpRouteRejectsExtraFieldsMissingFieldsAndOversizedChunkedBody()
    {
        using var fixture = new Fixture();
        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.WebHost.UseKestrel().UseUrls("http://127.0.0.1:0");
        builder.Services.AddSingleton(fixture.Store);
        builder.Services.AddSingleton(HubApiGuardrailOptions.FromConfiguration(builder.Configuration));
        builder.Services.AddControllers().AddApplicationPart(typeof(AndroidDiagnosticsController).Assembly);
        await using var app = builder.Build();
        app.UseRouting();
        app.UseMiddleware<HubApiRequestGuardrailMiddleware>();
        app.MapControllers();
        await app.StartAsync();
        try
        {
            var address = app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
            using var client = new HttpClient { BaseAddress = new Uri(address), Timeout = TimeSpan.FromSeconds(10) };
            const string route = "/api/v1/support/android-diagnostics";
            var report = fixture.Report();
            using var accepted = await client.PostAsJsonAsync(route, report);
            Assert.Equal(HttpStatusCode.Accepted, accepted.StatusCode);
            var receipt = await accepted.Content.ReadFromJsonAsync<AndroidDiagnosticReceipt>();
            Assert.Equal(report.ReportId, receipt!.ReportId);
            Assert.Equal(HttpStatusCode.Unauthorized, (await client.GetAsync(route)).StatusCode);
            string json = JsonSerializer.Serialize(report, new JsonSerializerOptions(JsonSerializerDefaults.Web));
            using var extra = await client.PostAsync(route, new StringContent(json[..^1] + ",\"story\":\"must not be stored\"}", Encoding.UTF8, "application/json"));
            Assert.Equal(HttpStatusCode.BadRequest, extra.StatusCode);
            using var missing = await client.PostAsync(route, new StringContent("{}", Encoding.UTF8, "application/json"));
            Assert.Equal(HttpStatusCode.BadRequest, missing.StatusCode);
            using var request = new HttpRequestMessage(HttpMethod.Post, route)
            {
                Content = new StringContent(json + new string(' ', 4096), Encoding.UTF8, "application/json")
            };
            request.Headers.TransferEncodingChunked = true;
            using var oversized = await client.SendAsync(request);
            Assert.Equal(HttpStatusCode.RequestEntityTooLarge, oversized.StatusCode);
            using var oversizedKnownLength = await client.PostAsync(route,
                new StringContent(json + new string(' ', 4096), Encoding.UTF8, "application/json"));
            Assert.Equal(HttpStatusCode.RequestEntityTooLarge, oversizedKnownLength.StatusCode);
            Assert.Single((await fixture.Store.ReadAsync(default)).Items);
        }
        finally { await app.StopAsync(); }
    }

    private sealed class Clock : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = new(2026, 10, 9, 10, 0, 0, TimeSpan.Zero);
        public override DateTimeOffset GetUtcNow() => Now;
    }

    private sealed class Fixture : IDisposable
    {
        public const string ReaderToken = "synthetic-scoped-reader-token-for-unit-tests-only";
        public string DirectoryPath { get; } = Path.Combine(Path.GetTempPath(), "chummer-android-diagnostics-" + Guid.NewGuid().ToString("N"));
        public string Snapshot => Path.Combine(DirectoryPath, "observations.json");
        public Clock Clock { get; } = new();
        public IConfiguration Configuration { get; }
        public AndroidDiagnosticStore Store { get; set; }
        public Fixture(bool enabled = true)
        {
            Configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ANDROID_DIAGNOSTICS_ENABLED"] = enabled ? "true" : "false",
                ["CHUMMER_ANDROID_DIAGNOSTICS_DIRECTORY"] = DirectoryPath,
                ["CHUMMER_ANDROID_DIAGNOSTICS_READER_TOKEN"] = ReaderToken
            }).Build();
            Store = new(Configuration, Clock);
        }
        public AndroidDiagnosticsController Controller => new(Store)
        {
            ControllerContext = new() { HttpContext = new DefaultHttpContext() }
        };
        public AndroidDiagnosticReport Report() => new(Guid.NewGuid(), 165, Clock.Now,
            AndroidDiagnosticArea.LifeModules, AndroidDiagnosticOperation.Refresh,
            AndroidDiagnosticOutcome.Slow, 31000, AndroidDiagnosticError.None);
        public void Dispose()
        {
            Store.Dispose();
            if (Directory.Exists(DirectoryPath)) Directory.Delete(DirectoryPath, recursive: true);
        }
    }
}
