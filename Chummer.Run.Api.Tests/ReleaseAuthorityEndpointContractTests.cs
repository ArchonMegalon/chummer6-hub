using Chummer.Run.Api.Controllers;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Xunit;

namespace Chummer.Run.Api.Tests;

public sealed class ReleaseAuthorityEndpointContractTests
{
    [Fact]
    public void AuthorityAdvanceAllowsBase64ExpansionAndDeclaresInfrastructureFailure()
    {
        System.Reflection.MethodInfo method = typeof(InternalReleaseBundlesController)
            .GetMethod(nameof(InternalReleaseBundlesController.AdvanceReleaseAuthority))
            ?? throw new InvalidOperationException("authority advance action is missing.");
        RequestSizeLimitAttribute requestSize = method
            .GetCustomAttributes(typeof(RequestSizeLimitAttribute), inherit: true)
            .Cast<RequestSizeLimitAttribute>()
            .Single();
        long? maximumBodyBytes =
            ((Microsoft.AspNetCore.Http.Metadata.IRequestSizeLimitMetadata)requestSize)
            .MaxRequestBodySize;

        Assert.Equal(64L * 1024L * 1024L, maximumBodyBytes);
        int[] responseCodes = method
            .GetCustomAttributes(typeof(ProducesResponseTypeAttribute), inherit: true)
            .Cast<ProducesResponseTypeAttribute>()
            .Select(attribute => attribute.StatusCode)
            .ToArray();
        Assert.Contains(StatusCodes.Status409Conflict, responseCodes);
        Assert.Contains(StatusCodes.Status503ServiceUnavailable, responseCodes);
    }
}
