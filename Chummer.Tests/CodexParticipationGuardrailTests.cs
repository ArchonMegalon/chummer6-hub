using System.Reflection;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class CodexParticipationGuardrailTests
{
    [Theory]
    [InlineData(typeof(CodexParticipationController), nameof(CodexParticipationController.CreateIntent))]
    [InlineData(typeof(BoostSessionsController), nameof(BoostSessionsController.Create))]
    public void SponsorSessionCreateRoutesCapRequestBodySize(Type controllerType, string methodName)
    {
        MethodInfo method = controllerType.GetMethod(methodName)
            ?? throw new InvalidOperationException($"{controllerType.Name}.{methodName} was not found.");
        RequestSizeLimitAttribute requestSize = method.GetCustomAttribute<RequestSizeLimitAttribute>()
            ?? throw new InvalidOperationException($"{controllerType.Name}.{methodName} is missing RequestSizeLimitAttribute.");

        Assert.Equal(BoostSessionService.MaxCreateRequestBodyBytes, ((IRequestSizeLimitMetadata)requestSize).MaxRequestBodySize);
    }

    [Fact]
    public void BoostSessionCreateRejectsOversizedSubjectLabel()
    {
        using var fixture = new Fixture();

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.Create(new CreateSponsorSessionRequest(
            SubjectId: "subject-a",
            ProjectId: "project-a",
            SubjectLabel: new string('s', 161))));

        Assert.Equal(nameof(CreateSponsorSessionRequest.SubjectLabel), error.ParamName);
    }

    [Fact]
    public void BoostSessionCreateRejectsOversizedLaneRole()
    {
        using var fixture = new Fixture();

        ArgumentException error = Assert.Throws<ArgumentException>(() => fixture.Service.Create(new CreateSponsorSessionRequest(
            SubjectId: "subject-a",
            ProjectId: "project-a",
            RequestedLaneRole: new string('r', 65))));

        Assert.Equal(nameof(CreateSponsorSessionRequest.RequestedLaneRole), error.ParamName);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-codex-participation-guardrail-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json")
                })
                .Build();

            CommunityStore store = new(Configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            GroupService groups = new(store, accounts);
            RewardService rewards = new(store);
            FleetBridgeService fleet = new(new HttpClient(), Configuration, NullLogger<FleetBridgeService>.Instance);
            Service = new BoostSessionService(store, accounts, groups, fleet, rewards);
        }

        public IConfiguration Configuration { get; }
        public BoostSessionService Service { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
