using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseUploadAccessPolicyTests
{
    [Fact]
    public void CanAccessAllowsOnlyConfiguredOwnerEmail()
    {
        Assert.True(ReleaseUploadAccessPolicy.CanAccess("tibor.girschele@gmail.com"));
        Assert.True(ReleaseUploadAccessPolicy.CanAccess("  TIBOR.GIRSCHELE@GMAIL.COM  "));
        Assert.False(ReleaseUploadAccessPolicy.CanAccess("archon.megalon@gmail.com"));
        Assert.False(ReleaseUploadAccessPolicy.CanAccess((string?)null));
        Assert.False(ReleaseUploadAccessPolicy.CanAccess(string.Empty));
    }

    [Theory]
    [InlineData("operator")]
    [InlineData(" OPERATOR ")]
    [InlineData("admin")]
    [InlineData("ADMIN")]
    public void CanAccessAllowsTrustedPrivilegedIdentityRoles(string role)
    {
        var subject = new AuthenticatedHubSubject(
            SubjectId: "subject-operator",
            DisplayName: "Release operator",
            Email: "operator@example.invalid",
            Roles: [role],
            AccessToken: "test-token");

        Assert.True(ReleaseUploadAccessPolicy.CanAccess(subject));
    }

    [Fact]
    public void CanAccessRejectsOrdinarySignedInIdentity()
    {
        var subject = new AuthenticatedHubSubject(
            SubjectId: "subject-player",
            DisplayName: "Player",
            Email: "player@example.invalid",
            Roles: ["player"],
            AccessToken: "test-token");

        Assert.False(ReleaseUploadAccessPolicy.CanAccess(subject));
        Assert.False(ReleaseUploadAccessPolicy.CanAccess((AuthenticatedHubSubject?)null));
    }

    [Fact]
    public void CanAccessSubjectPreservesConfiguredOwnerAccessWithoutRoleEscalation()
    {
        var subject = new AuthenticatedHubSubject(
            SubjectId: "subject-owner",
            DisplayName: "Configured owner",
            Email: ReleaseUploadAccessPolicy.AllowedEmail,
            Roles: ["player"],
            AccessToken: "test-token");

        Assert.True(ReleaseUploadAccessPolicy.CanAccess(subject));
    }
}
