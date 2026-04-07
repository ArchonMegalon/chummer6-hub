using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallBootstrapTicketServiceTests
{
    [Fact]
    public void IssueAndValidateRoundTripsClaims()
    {
        using TicketFixture fixture = new();
        InstallBootstrapTicketIssueResult issued = fixture.Service.Issue(
            "avalonia-osx-arm64-installer",
            ["avalonia-osx-arm64-installer", "blazor-desktop-osx-arm64-installer"],
            "user-archon",
            "subject-archon");

        bool valid = fixture.Service.TryValidate(issued.Ticket, out InstallBootstrapTicketClaims? claims);

        Assert.True(valid);
        Assert.NotNull(claims);
        Assert.Equal("avalonia-osx-arm64-installer", claims!.ArtifactId);
        Assert.Equal(
            ["avalonia-osx-arm64-installer", "blazor-desktop-osx-arm64-installer"],
            claims.AllowedArtifactIds);
        Assert.Equal("user-archon", claims.UserId);
        Assert.Equal("subject-archon", claims.SubjectId);
        Assert.True(claims.ExpiresAtUtc > claims.IssuedAtUtc);
    }

    [Fact]
    public void TryValidateRejectsTamperedTicket()
    {
        using TicketFixture fixture = new();
        InstallBootstrapTicketIssueResult issued = fixture.Service.Issue(
            "avalonia-osx-arm64-installer",
            "user-archon",
            "subject-archon");

        bool valid = fixture.Service.TryValidate($"{issued.Ticket}tampered", out InstallBootstrapTicketClaims? claims);

        Assert.False(valid);
        Assert.Null(claims);
    }

    [Fact]
    public void TryValidateForArtifactRequiresArtifactMembership()
    {
        using TicketFixture fixture = new();
        InstallBootstrapTicketIssueResult issued = fixture.Service.Issue(
            "avalonia-osx-arm64-installer",
            ["avalonia-osx-arm64-installer", "blazor-desktop-osx-arm64-installer"],
            "user-archon",
            "subject-archon");

        bool validAllowed = fixture.Service.TryValidateForArtifact(issued.Ticket, "blazor-desktop-osx-arm64-installer", out InstallBootstrapTicketClaims? allowedClaims);
        bool validDenied = fixture.Service.TryValidateForArtifact(issued.Ticket, "avalonia-win-x64-installer", out InstallBootstrapTicketClaims? deniedClaims);

        Assert.True(validAllowed);
        Assert.NotNull(allowedClaims);
        Assert.False(validDenied);
        Assert.Null(deniedClaims);
    }

    private sealed class TicketFixture : IDisposable
    {
        private readonly string _root;

        public TicketFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "install-bootstrap-ticket-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_BOOTSTRAP_TICKET_LIFETIME_MINUTES"] = "15"
                })
                .Build();
            IDataProtectionProvider provider = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            Service = new InstallBootstrapTicketService(provider, configuration);
        }

        public InstallBootstrapTicketService Service { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
