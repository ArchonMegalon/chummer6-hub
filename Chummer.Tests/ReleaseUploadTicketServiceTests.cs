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

    private sealed class TicketFixture : IDisposable
    {
        private readonly string _root;

        public TicketFixture(bool configureLifetime = true)
        {
            _root = Path.Combine(Path.GetTempPath(), "release-upload-ticket-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            var settings = new Dictionary<string, string?>();
            if (configureLifetime)
            {
                settings["CHUMMER_RELEASE_UPLOAD_TICKET_LIFETIME_MINUTES"] = "45";
            }

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(settings)
                .Build();
            IDataProtectionProvider provider = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            Service = new ReleaseUploadTicketService(provider, configuration);
        }

        public ReleaseUploadTicketService Service { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
