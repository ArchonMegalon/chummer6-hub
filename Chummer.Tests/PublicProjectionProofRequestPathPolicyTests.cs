using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicProjectionProofRequestPathPolicyTests
{
    [Theory]
    [InlineData(PublicProjectionProofRequestPathPolicy.CurrentProofPath)]
    [InlineData(PublicProjectionProofRequestPathPolicy.LegacyCompatibilityProofPath)]
    public void ExactControllerRoutesAreCanonical(string path)
    {
        HttpRequest request = Request(path, path);

        Assert.Equal(
            PublicProjectionProofRequestPathDisposition.Canonical,
            PublicProjectionProofRequestPathPolicy.Evaluate(request));
        Assert.True(PublicProjectionProofRequestPathPolicy.IsCanonical(request.Path));
    }

    [Theory]
    [InlineData("/proofs//mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")]
    [InlineData("/proofs/mac-codex-release//HUB_LOCAL_RELEASE_PROOF.generated.json")]
    [InlineData("/proofs/./mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")]
    [InlineData("/proofs/ignored/../mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")]
    [InlineData("/proofs%2fmac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")]
    [InlineData("/proofs/%2e/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")]
    [InlineData("/proofs%252fmac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")]
    [InlineData("/proofs\\mac-codex-release\\HUB_LOCAL_RELEASE_PROOF.generated.json")]
    [InlineData("/proofs%5cmac-codex-release%5cHUB_LOCAL_RELEASE_PROOF.generated.json")]
    [InlineData("/proofs/mac-codex-release/%48UB_LOCAL_RELEASE_PROOF.generated.json")]
    [InlineData("/PROOFS/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")]
    public void EquivalentNonCanonicalRoutesAreRejected(string rawTarget)
    {
        HttpRequest request = Request(rawTarget, rawTarget);

        Assert.Equal(
            PublicProjectionProofRequestPathDisposition.RejectVariant,
            PublicProjectionProofRequestPathPolicy.Evaluate(request));
    }

    [Fact]
    public void ServerDecodedPathStillUsesRawTargetForVariantDetection()
    {
        HttpRequest request = Request(
            "/proofs%2fmac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json",
            PublicProjectionProofRequestPathPolicy.LegacyCompatibilityProofPath);

        Assert.Equal(
            PublicProjectionProofRequestPathDisposition.RejectVariant,
            PublicProjectionProofRequestPathPolicy.Evaluate(request));
    }

    [Fact]
    public void QueryDoesNotChangeCanonicalRoute()
    {
        HttpRequest request = Request(
            PublicProjectionProofRequestPathPolicy.CurrentProofPath + "?cache=no",
            PublicProjectionProofRequestPathPolicy.CurrentProofPath);

        Assert.Equal(
            PublicProjectionProofRequestPathDisposition.Canonical,
            PublicProjectionProofRequestPathPolicy.Evaluate(request));
    }

    [Fact]
    public void UnrelatedProofPathIsNotGovernedByThisPolicy()
    {
        HttpRequest request = Request("/proofs/other.json", "/proofs/other.json");

        Assert.Equal(
            PublicProjectionProofRequestPathDisposition.NotGoverned,
            PublicProjectionProofRequestPathPolicy.Evaluate(request));
    }

    private static HttpRequest Request(string rawTarget, string path)
    {
        var context = new DefaultHttpContext();
        context.Request.Path = path;
        context.Features.Get<IHttpRequestFeature>()!.RawTarget = rawTarget;
        return context.Request;
    }
}
