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
        Assert.False(ReleaseUploadAccessPolicy.CanAccess(null));
        Assert.False(ReleaseUploadAccessPolicy.CanAccess(string.Empty));
    }
}
