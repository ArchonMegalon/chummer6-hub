using System.Net;
using System.Net.Http.Json;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Chummer.Tests;

public sealed class OriginChapterWorkerTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "origin-worker-tests-" + Guid.NewGuid().ToString("N"));
    private const string Token = "synthetic-worker-token-no-production-authority";
    private IConfiguration Configuration(params (string Key, string? Value)[] changes)
    {
        var values = new Dictionary<string, string?>
        {
            ["CHUMMER_RUNTIME_STATE_ROOT"] = _root,
            ["CHUMMER_ORIGIN_CHAPTER_WORKER_PORT"] = "5089",
            ["CHUMMER_ORIGIN_CHAPTER_WORKER_TOKEN"] = Token
        };
        foreach (var (key, value) in changes) values[key] = value;
        return new ConfigurationBuilder().AddInMemoryCollection(values).Build();
    }
    private OriginChapterAuthoringService Service() => new(Configuration());
    private static OriginChapterAuthoringRequest Request() => new("same-local-request",
        new("runner", "chapter", new string('a', 64), "decision", "de", "Nera",
            [new("fact", "decision", "Nera is an elf.")]), true);
    private static DefaultHttpContext Context(int port = 5089, string? token = Token, string? path = null)
    {
        var context = new DefaultHttpContext();
        context.Connection.LocalPort = port;
        context.Connection.LocalIpAddress = IPAddress.Loopback;
        context.Request.Path = path ?? OriginChapterWorkerGateMiddleware.Prefix + "/pending";
        if (token is not null) context.Request.Headers.Authorization = "Bearer " + token;
        return context;
    }

    [Fact]
    public void Worker_admission_is_durable_one_shot_and_owner_isolated()
    {
        var service = Service();
        var a = service.Create("subject-a", Request(), () => true);
        service.Create("subject-b", Request(), () => true);
        var pending = service.PendingForWorker(20);
        Assert.Equal(2, pending.Count);
        Assert.NotEqual(pending[0].WorkId, pending[1].WorkId);
        var work = pending[0];
        var first = service.AdmitForWorker(work.WorkId, a.SourceDigest, "admission-1");
        Assert.True(first.MayStartGeneration);
        Assert.Equal(OriginChapterAuthoringStates.ReconciliationRequired, first.Work.Job.State);
        var cold = Service().AdmitForWorker(work.WorkId, a.SourceDigest, "admission-1");
        Assert.False(cold.MayStartGeneration);
        Assert.Equal("admission-1", cold.Work.ExecutionAdmission);
        Assert.Throws<InvalidOperationException>(() => service.AdmitForWorker(work.WorkId, a.SourceDigest, "admission-2"));
        Assert.Throws<InvalidOperationException>(() => service.AdmitForWorker(work.WorkId, new string('b', 64), "admission-1"));
        Assert.Equal(OriginChapterAuthoringStates.AwaitingAuthoring,
            Service().GetForWorker(pending[1].WorkId).Job.State);
    }

    [Fact]
    public void Only_the_exact_admitted_result_can_be_returned_to_the_app()
    {
        var service = Service();
        var job = service.Create("subject", Request(), () => true);
        var work = Assert.Single(service.PendingForWorker(20));
        Assert.Throws<InvalidOperationException>(() => service.CompleteForWorker(work.WorkId, job.SourceDigest,
            "admission", "Premature", new string('d', 64)));
        service.AdmitForWorker(work.WorkId, job.SourceDigest, "admission");
        Assert.Throws<InvalidOperationException>(() => service.CompleteForWorker(work.WorkId, job.SourceDigest,
            "wrong-admission", "Wrong", new string('d', 64)));
        Assert.Throws<InvalidOperationException>(() => service.CompleteForWorker(work.WorkId, new string('d', 64),
            "admission", "Wrong", new string('d', 64)));
        Assert.Throws<InvalidOperationException>(() => service.Complete("subject", job.RequestId, job.SourceDigest,
            "Cannot bypass admission", new string('d', 64)));
        var result = service.CompleteForWorker(work.WorkId, job.SourceDigest, "admission", "Actual draft", new string('d', 64));
        Assert.Equal("Actual draft", Service().Get("subject", job.RequestId)!.DraftText);
        Assert.True(result.Job.RequiresReaderReview);
        Assert.False(result.Job.AffectsMechanics);
        Assert.False(result.Job.PublicationAuthorized);
        Assert.Empty(service.PendingForWorker(20));
        Assert.Equal(result.Job.SourceDigest, Service().CompleteForWorker(work.WorkId, job.SourceDigest,
            "admission", "Actual draft", new string('d', 64)).Job.SourceDigest);
        Assert.Throws<InvalidOperationException>(() => service.CompleteForWorker(work.WorkId, job.SourceDigest,
            "admission", "Replacement", new string('d', 64)));
    }

    [Fact]
    public void Account_erasure_fences_late_worker_results_and_does_not_delete_other_owners()
    {
        var service = Service();
        var job = service.Create("subject", Request(), () => true);
        var work = Assert.Single(service.PendingForWorker(20));
        service.AdmitForWorker(work.WorkId, job.SourceDigest, "admission");
        service.Create("other-subject", Request(), () => true);
        service.EraseForSubject("subject");
        Assert.Throws<KeyNotFoundException>(() => service.GetForWorker(work.WorkId));
        Assert.Throws<KeyNotFoundException>(() => service.CompleteForWorker(work.WorkId, job.SourceDigest,
            "admission", "Late", new string('a', 64)));
        Assert.Single(service.PendingForWorker(20));
        Assert.NotNull(service.Get("other-subject", job.RequestId));
    }

    [Fact]
    public void Invalid_worker_identity_bounds_or_corrupt_admission_fail_closed()
    {
        var service = Service();
        var job = service.Create("subject", Request(), () => true);
        var work = Assert.Single(service.PendingForWorker(20));
        Assert.Throws<ArgumentException>(() => service.GetForWorker("../../credential"));
        Assert.Throws<ArgumentException>(() => service.PendingForWorker(21));
        Assert.Throws<ArgumentException>(() => service.PendingForWorker(0));
        Assert.Throws<ArgumentException>(() => service.AdmitForWorker(work.WorkId, job.SourceDigest, "\n"));
        service.AdmitForWorker(work.WorkId, job.SourceDigest, "admission");
        Assert.Throws<ArgumentException>(() => service.CompleteForWorker(work.WorkId, job.SourceDigest,
            "admission", new string('a', 65537), new string('d', 64)));
        string path = Directory.GetFiles(Path.Combine(_root, "origin-chapter-jobs"), "*.json").Single();
        File.WriteAllText(path, File.ReadAllText(path).Replace("\"executionAdmission\":\"admission\"", "\"executionAdmission\":\"other\"", StringComparison.Ordinal));
        Assert.Throws<InvalidDataException>(() => service.GetForWorker(work.WorkId));
    }

    [Theory]
    [InlineData(8080, Token, 404)]
    [InlineData(5089, null, 401)]
    [InlineData(5089, "wrong", 401)]
    public async Task Public_listener_and_unauthenticated_requests_cannot_reach_worker(int port, string? token, int status)
    {
        var context = Context(port, token);
        context.Request.Headers["X-Forwarded-Port"] = "5089";
        context.Request.Headers["X-Forwarded-For"] = "127.0.0.1";
        await new OriginChapterWorkerGateMiddleware(_ => throw new InvalidOperationException("must not dispatch"), Configuration()).InvokeAsync(context);
        Assert.Equal(status, context.Response.StatusCode);
        Assert.Contains("no-store", context.Response.Headers.CacheControl.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Disabled_missing_secrets_duplicates_and_other_listener_routes_are_rejected()
    {
        var disabled = Context();
        await new OriginChapterWorkerGateMiddleware(_ => throw new InvalidOperationException(),
            Configuration(("CHUMMER_ORIGIN_CHAPTER_WORKER_PORT", null))).InvokeAsync(disabled);
        Assert.Equal(404, disabled.Response.StatusCode);
        var missing = Context();
        await new OriginChapterWorkerGateMiddleware(_ => throw new InvalidOperationException(),
            Configuration(("CHUMMER_ORIGIN_CHAPTER_WORKER_TOKEN", null), ("CHUMMER_EA_WEBHOOK_TOKEN", Token))).InvokeAsync(missing);
        Assert.Equal(503, missing.Response.StatusCode);
        var otherRoute = Context(path: "/api/account");
        await new OriginChapterWorkerGateMiddleware(_ => throw new InvalidOperationException(), Configuration()).InvokeAsync(otherRoute);
        Assert.Equal(404, otherRoute.Response.StatusCode);
        var duplicate = Context();
        duplicate.Request.Headers.Append("Authorization", "Bearer " + Token);
        await new OriginChapterWorkerGateMiddleware(_ => throw new InvalidOperationException(), Configuration()).InvokeAsync(duplicate);
        Assert.Equal(401, duplicate.Response.StatusCode);
        var oversized = Context();
        oversized.Request.ContentLength = 131073;
        await new OriginChapterWorkerGateMiddleware(_ => throw new InvalidOperationException(), Configuration()).InvokeAsync(oversized);
        Assert.Equal(413, oversized.Response.StatusCode);
    }

    [Fact]
    public async Task Middleware_admitted_worker_completes_a_real_stored_app_request()
    {
        var service = Service();
        var job = service.Create("subject", Request(), () => true);
        var work = Assert.Single(service.PendingForWorker(20));
        var outside = new InternalOriginChaptersController(service) { ControllerContext = new() { HttpContext = Context() } };
        Assert.IsType<NotFoundResult>(outside.Pending());
        var context = Context();
        await new OriginChapterWorkerGateMiddleware(http =>
        {
            var controller = new InternalOriginChaptersController(service) { ControllerContext = new() { HttpContext = http } };
            var pending = Assert.IsType<OkObjectResult>(controller.Pending());
            Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<OriginChapterWorkerItem>>(pending.Value));
            Assert.IsType<BadRequestObjectResult>(controller.Pending(21));
            var admitted = Assert.IsType<OkObjectResult>(controller.Admit(work.WorkId, new(job.SourceDigest, "admission")));
            Assert.True(Assert.IsType<OriginChapterWorkerAdmission>(admitted.Value).MayStartGeneration);
            Assert.IsType<ConflictObjectResult>(controller.Complete(work.WorkId, new(job.SourceDigest, "wrong", "text", new string('c', 64))));
            Assert.IsType<OkObjectResult>(controller.Complete(work.WorkId, new(job.SourceDigest, "admission", "Returned chapter", new string('c', 64))));
            return Task.CompletedTask;
        }, Configuration()).InvokeAsync(context);
        Assert.Equal("Returned chapter", Service().Get("subject", job.RequestId)!.DraftText);
    }

    [Fact]
    public async Task Ordinary_public_routes_remain_unchanged()
    {
        var context = Context(port: 8080, token: null, path: "/health");
        bool called = false;
        await new OriginChapterWorkerGateMiddleware(_ => { called = true; return Task.CompletedTask; }, Configuration()).InvokeAsync(context);
        Assert.True(called);
    }

    [Fact]
    public async Task Actual_http_worker_listener_returns_the_result_and_public_listener_denies_it()
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.ConfigureKestrel(options =>
        {
            options.Listen(IPAddress.Loopback, 0);
            options.Listen(IPAddress.Loopback, 0);
        });
        builder.Configuration.AddConfiguration(Configuration());
        var service = Service();
        var job = service.Create("subject", Request(), () => true);
        builder.Services.AddSingleton(service);
        builder.Services.AddControllers().AddApplicationPart(typeof(InternalOriginChaptersController).Assembly);
        await using var app = builder.Build();
        app.UseOriginChapterWorkerLane();
        app.Use((context, next) =>
        {
            Assert.False(OriginChapterWorkerGateMiddleware.IsAdmitted(context));
            return next(context);
        });
        app.MapControllers();
        await app.StartAsync();
        string[] addresses = app.Services.GetRequiredService<IServer>().Features
            .Get<IServerAddressesFeature>()!.Addresses.ToArray();
        Assert.Equal(2, addresses.Length);
        builder.Configuration["CHUMMER_ORIGIN_CHAPTER_WORKER_PORT"] = new Uri(addresses[0]).Port.ToString();
        using var client = new HttpClient { BaseAddress = new Uri(addresses[0]) };
        string route = OriginChapterWorkerGateMiddleware.Prefix;
        using var unauthenticated = await client.GetAsync(route + "/pending");
        Assert.Equal(HttpStatusCode.Unauthorized, unauthenticated.StatusCode);
        client.DefaultRequestHeaders.Authorization = new("Bearer", Token);
        var list = await client.GetFromJsonAsync<OriginChapterWorkerItem[]>(route + "/pending");
        var work = Assert.Single(list!);
        using var admitted = await client.PostAsJsonAsync(route + "/" + work.WorkId + "/admit",
            new OriginChapterWorkerAdmissionRequest(job.SourceDigest, "socket-admission"));
        admitted.EnsureSuccessStatusCode();
        Assert.True((await admitted.Content.ReadFromJsonAsync<OriginChapterWorkerAdmission>())!.MayStartGeneration);
        using var completed = await client.PostAsJsonAsync(route + "/" + work.WorkId + "/complete",
            new OriginChapterWorkerCompletionRequest(job.SourceDigest, "socket-admission", "Socket result", new string('e', 64)));
        completed.EnsureSuccessStatusCode();
        Assert.Equal("Socket result", Service().Get("subject", job.RequestId)!.DraftText);
        using var publicResponse = await client.GetAsync(addresses[1] + route + "/pending");
        Assert.Equal(HttpStatusCode.NotFound, publicResponse.StatusCode);
        await app.StopAsync();
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, true); }
}
