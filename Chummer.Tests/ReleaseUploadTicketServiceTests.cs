using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseUploadTicketServiceTests
{
    [Fact]
    public void IssueUsesExtendedDefaultLifetime()
    {
        using TicketFixture fixture = new(configureLifetime: false);
        ReleaseUploadTicketIssueResult issued = fixture.Service.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));

        TimeSpan lifetime = issued.Claims.ExpiresAtUtc - issued.Claims.IssuedAtUtc;

        Assert.Equal(TimeSpan.FromHours(12), lifetime);
    }

    [Fact]
    public void IssueAndValidateRoundTripsClaims()
    {
        using TicketFixture fixture = new();
        ReleaseUploadTicketIssueResult issued = fixture.Service.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));

        bool valid = fixture.Service.TryValidate(issued.Ticket, out ReleaseUploadTicketClaims? claims);

        Assert.True(valid);
        Assert.NotNull(claims);
        Assert.Equal("subject-archon", claims!.SubjectId);
        Assert.Equal("Archon", claims.DisplayName);
        Assert.Equal("archon@example.com", claims.Email);
        Assert.True(claims.ExpiresAtUtc > claims.IssuedAtUtc);
        Assert.True(Guid.TryParseExact(claims.TicketId, "N", out _));
    }

    [Fact]
    public void TryValidateRejectsTamperedTicket()
    {
        using TicketFixture fixture = new();
        ReleaseUploadTicketIssueResult issued = fixture.Service.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: [],
            AccessToken: "token"));

        bool valid = fixture.Service.TryValidate($"{issued.Ticket}tampered", out ReleaseUploadTicketClaims? claims);

        Assert.False(valid);
        Assert.Null(claims);
    }

    [Fact]
    public void ChangingRevocationEpochInvalidatesEveryPreviouslyIssuedTicket()
    {
        using TicketFixture fixture = new(revocationEpoch: "release-epoch-a");
        ReleaseUploadTicketIssueResult issued = fixture.Service.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));

        ReleaseUploadTicketService rotatedService = fixture.CreateService("release-epoch-b");

        Assert.True(fixture.Service.TryValidate(issued.Ticket, out _));
        Assert.False(rotatedService.TryValidate(issued.Ticket, out ReleaseUploadTicketClaims? claims));
        Assert.Null(claims);
    }

    [Fact]
    public void MatchingRevocationEpochAndSharedKeyRingPreserveTicketValidationAcrossIndependentProviders()
    {
        using TicketFixture fixture = new(revocationEpoch: "release-epoch-a");
        ReleaseUploadTicketIssueResult issued = fixture.Service.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));

        ReleaseUploadTicketService restartedService = fixture.CreateServiceWithIndependentProvider("release-epoch-a");

        Assert.True(restartedService.TryValidate(issued.Ticket, out ReleaseUploadTicketClaims? claims));
        Assert.NotNull(claims);
        Assert.Equal("subject-archon", claims.SubjectId);
    }

    [Fact]
    public void MatchingRevocationEpochWithoutSharedKeyRingRejectsTicket()
    {
        using TicketFixture issuer = new(revocationEpoch: "release-epoch-a");
        using TicketFixture validator = new(revocationEpoch: "release-epoch-a");
        ReleaseUploadTicketIssueResult issued = issuer.Service.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));

        Assert.False(validator.Service.TryValidate(issued.Ticket, out ReleaseUploadTicketClaims? claims));
        Assert.Null(claims);
    }

    [Fact]
    public void ImplicitDefaultEpochMatchesExplicitEpochOneAcrossIndependentProviders()
    {
        using TicketFixture fixture = new();
        ReleaseUploadTicketIssueResult issued = fixture.Service.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));

        ReleaseUploadTicketService restartedService = fixture.CreateServiceWithIndependentProvider("1");

        Assert.True(restartedService.TryValidate(issued.Ticket, out ReleaseUploadTicketClaims? claims));
        Assert.NotNull(claims);
        Assert.Equal("subject-archon", claims.SubjectId);
    }

    private sealed class TicketFixture : IDisposable
    {
        private readonly string _root;
        private readonly IDataProtectionProvider _provider;
        private readonly bool _configureLifetime;

        public TicketFixture(bool configureLifetime = true, string? revocationEpoch = null)
        {
            _root = Path.Combine(Path.GetTempPath(), "release-upload-ticket-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            _configureLifetime = configureLifetime;
            _provider = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            Service = CreateService(revocationEpoch);
        }

        public ReleaseUploadTicketService Service { get; }

        public ReleaseUploadTicketService CreateService(string? revocationEpoch)
            => CreateService(_provider, revocationEpoch);

        public ReleaseUploadTicketService CreateServiceWithIndependentProvider(string? revocationEpoch)
            => CreateService(
                DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys"))),
                revocationEpoch);

        private ReleaseUploadTicketService CreateService(
            IDataProtectionProvider provider,
            string? revocationEpoch)
        {
            var settings = new Dictionary<string, string?>();
            if (_configureLifetime)
            {
                settings["CHUMMER_RELEASE_UPLOAD_TICKET_LIFETIME_MINUTES"] = "45";
            }
            if (!string.IsNullOrWhiteSpace(revocationEpoch))
            {
                settings["CHUMMER_RELEASE_UPLOAD_TICKET_REVOCATION_EPOCH"] = revocationEpoch;
            }

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(settings)
                .Build();
            return new ReleaseUploadTicketService(provider, configuration);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
