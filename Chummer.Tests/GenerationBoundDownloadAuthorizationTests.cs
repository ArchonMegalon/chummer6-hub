using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class GenerationBoundDownloadAuthorizationTests
{
    [Fact]
    public void CredentialedArtifactHrefUsesImmutableGenerationRoute()
    {
        var artifact = new PublicReleaseArtifactDto(
            Id: GenerationFixture.ArtifactId,
            Platform: "macos",
            Url: "/downloads/files/chummer-shared-installer.dmg",
            Sha256: new string('a', 64),
            FileName: GenerationFixture.FileName,
            InstallAccessClass: "account_required");
        var manifest = new PublicReleaseManifestDto(
            Version: "run-a",
            Channel: "preview",
            PublishedAt: DateTimeOffset.UnixEpoch,
            Downloads: [artifact])
        {
            GenerationId = "generation-a"
        };

        string href = PublicLandingController.BuildCredentialBoundArtifactHref(
            manifest,
            artifact,
            $"/downloads/file/{artifact.Id}");

        Assert.Equal(
            "/downloads/g/generation-a/install/shared-account-required-installer",
            href);
    }

    [Fact]
    public void ExplicitlyPublicArtifactHrefUsesImmutableGenerationFileRoute()
    {
        var artifact = new PublicReleaseArtifactDto(
            Id: GenerationFixture.ArtifactId,
            Platform: "macos",
            Url: "/downloads/files/chummer-shared-installer.dmg",
            Sha256: new string('a', 64),
            FileName: GenerationFixture.FileName,
            InstallAccessClass: "open_public");
        var manifest = new PublicReleaseManifestDto(
            Version: "run-a",
            Channel: "preview",
            PublishedAt: DateTimeOffset.UnixEpoch,
            Downloads: [artifact])
        {
            GenerationId = "generation-a"
        };

        string href = PublicLandingController.BuildCredentialBoundArtifactHref(
            manifest,
            artifact,
            $"/downloads/file/{artifact.Id}");

        Assert.Equal(
            "/downloads/g/generation-a/files/chummer-shared-installer.dmg",
            href);
    }

    [Fact]
    public async Task ProtectedGenerationFileFailsClosedWithoutGenerationCredential()
    {
        using GenerationFixture fixture = new();
        fixture.SetConfiguration("CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS", "true");
        fixture.SetQuery(null, null);

        IActionResult result = await fixture.Controller.DownloadGenerationFile(
            "generation-a",
            GenerationFixture.FileName,
            CancellationToken.None);

        ObjectResult blocked = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status409Conflict, blocked.StatusCode);
    }

    [Fact]
    public async Task GenerationInstallRouteValidatesExactGenerationAndDigestBeforeVerifiedServe()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifestA, PublicReleaseArtifactDto artifactA) = fixture.LoadArtifact("generation-a");
        DownloadDispatchResult dispatchA = fixture.InstallLinking.IssueDownload(
            manifestA,
            artifactA,
            "user-generation-a",
            "subject-generation-a");
        Assert.NotNull(dispatchA.ClaimTicket);
        string claimA = dispatchA.ClaimTicket!.ClaimCode;

        fixture.Activate(GenerationFixture.ProtectedGenerationId);
        fixture.SetQuery("claimCode", claimA);
        IActionResult generationB = await fixture.Controller.DownloadGenerationArtifact(
            GenerationFixture.ProtectedGenerationId,
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.IsType<UnauthorizedObjectResult>(generationB);

        fixture.SetQuery("claimCode", claimA);
        IActionResult retainedA = await fixture.Controller.DownloadGenerationArtifact(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.Equal("artifact-a", await ReadFileResultAsync(retainedA));
    }

    [Fact]
    public async Task GenerationAClaimCannotReadCurrentBButCanReadRetainedA()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifestA, PublicReleaseArtifactDto artifactA) = fixture.LoadArtifact("generation-a");
        DownloadDispatchResult dispatchA = fixture.InstallLinking.IssueDownload(
            manifestA,
            artifactA,
            "user-generation-a",
            "subject-generation-a");
        Assert.NotNull(dispatchA.ClaimTicket);
        string claimA = dispatchA.ClaimTicket!.ClaimCode;

        fixture.Activate(GenerationFixture.ProtectedGenerationId);
        fixture.SetQuery("claimCode", claimA);
        IActionResult currentB = await fixture.Controller.DownloadFile(GenerationFixture.FileName, CancellationToken.None);
        Assert.IsType<UnauthorizedObjectResult>(currentB);

        fixture.SetQuery("claimCode", claimA);
        IActionResult retainedA = await fixture.Controller.DownloadGenerationFile(
            "generation-a",
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal("artifact-a", await ReadFileResultAsync(retainedA));

        (PublicReleaseManifestDto manifestB, PublicReleaseArtifactDto artifactB) = fixture.LoadArtifact(
            GenerationFixture.ProtectedGenerationId);
        DownloadDispatchResult dispatchB = fixture.InstallLinking.IssueDownload(
            manifestB,
            artifactB,
            "user-generation-b",
            "subject-generation-b");
        Assert.NotNull(dispatchB.ClaimTicket);
        fixture.SetQuery("claimCode", dispatchB.ClaimTicket!.ClaimCode);
        IActionResult correctlyBoundCurrentB = await fixture.Controller.DownloadFile(
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal("artifact-protected-b", await ReadFileResultAsync(correctlyBoundCurrentB));
    }

    [Fact]
    public async Task GenerationABootstrapTicketCannotReadBButCanReadRetainedA()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifestA, PublicReleaseArtifactDto artifactA) = fixture.LoadArtifact("generation-a");
        InstallBootstrapTicketIssueResult ticketA = fixture.InstallBootstrapTickets.IssueBound(
            artifactA.Id,
            [new InstallBootstrapArtifactBinding(artifactA.Id, artifactA.Sha256)],
            manifestA.GenerationId!,
            "user-generation-a",
            "subject-generation-a");

        fixture.Activate("generation-b");
        fixture.SetQuery("ticket", ticketA.Ticket);
        IActionResult currentB = await fixture.Controller.DownloadFile(GenerationFixture.FileName, CancellationToken.None);
        Assert.IsType<UnauthorizedObjectResult>(currentB);

        fixture.SetQuery("ticket", ticketA.Ticket);
        IActionResult retainedA = await fixture.Controller.DownloadGenerationFile(
            "generation-a",
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal("artifact-a", await ReadFileResultAsync(retainedA));
    }

    [Fact]
    public async Task RoleBoundTicketCannotCollapsePrimaryBindingIntoPayloadOrMetadata()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) = fixture.LoadArtifact("generation-a");
        InstallBootstrapTicketIssueResult primaryOnly = fixture.InstallBootstrapTickets.IssueBound(
            artifact.Id,
            [new InstallBootstrapArtifactBinding(artifact.Id, artifact.Sha256)],
            manifest.GenerationId!,
            "user-generation-a",
            "subject-generation-a");

        fixture.SetCompanionRequest(
            $"/downloads/g/generation-a/install/{GenerationFixture.ArtifactId}/payload",
            "ticket",
            primaryOnly.Ticket);
        IActionResult payloadDenied = await fixture.Controller.DownloadGenerationArtifactPayload(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.IsType<UnauthorizedObjectResult>(payloadDenied);

        ReleaseShelfSnapshot snapshot = fixture.ManifestService.CaptureShelfGeneration("generation-a");
        IReadOnlyList<InstallBootstrapArtifactBinding> bindings = fixture.DeliveryPolicy.BuildCredentialBindings(
            snapshot,
            [artifact]);
        InstallBootstrapTicketIssueResult roleBound = fixture.InstallBootstrapTickets.IssueBound(
            artifact.Id,
            bindings,
            manifest.GenerationId!,
            "user-generation-a",
            "subject-generation-a");

        fixture.SetCompanionRequest(
            $"/downloads/g/generation-a/install/{GenerationFixture.ArtifactId}/payload",
            "ticket",
            roleBound.Ticket);
        IActionResult payload = await fixture.Controller.DownloadGenerationArtifactPayload(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.Equal("payload-a", await ReadFileResultAsync(payload));

        fixture.SetCompanionRequest(
            $"/downloads/g/generation-a/install/{GenerationFixture.ArtifactId}/metadata",
            "ticket",
            roleBound.Ticket);
        IActionResult metadata = await fixture.Controller.DownloadGenerationArtifactPayloadMetadata(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        FileStreamResult metadataFile = Assert.IsType<FileStreamResult>(metadata);
        Assert.Equal("application/json; charset=utf-8", metadataFile.ContentType);
        await metadataFile.FileStream.DisposeAsync();
    }

    [Fact]
    public async Task GlobalRevocationInvalidatesOpenCurrentAndRetainedClaimAndTicketPaths()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifestA, PublicReleaseArtifactDto artifactA) = fixture.LoadArtifact("generation-a");
        DownloadDispatchResult dispatchA = fixture.InstallLinking.IssueDownload(
            manifestA,
            artifactA,
            "user-generation-a",
            "subject-generation-a");
        InstallBootstrapTicketIssueResult ticketA = fixture.InstallBootstrapTickets.IssueBound(
            artifactA.Id,
            fixture.DeliveryPolicy.BuildCredentialBindings(
                fixture.ManifestService.CaptureShelfGeneration("generation-a"),
                [artifactA]),
            manifestA.GenerationId!,
            "user-generation-a",
            "subject-generation-a");
        fixture.Activate("generation-b");
        fixture.RevokeArtifact(GenerationFixture.ArtifactId);

        fixture.SetQuery(null, null);
        IActionResult openCurrent = await fixture.Controller.DownloadFile(
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(openCurrent).StatusCode);

        fixture.SetQuery("claimCode", dispatchA.ClaimTicket!.ClaimCode);
        IActionResult retainedClaim = await fixture.Controller.DownloadGenerationArtifact(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(retainedClaim).StatusCode);

        fixture.SetCompanionRequest(
            $"/downloads/g/generation-a/install/{GenerationFixture.ArtifactId}/payload",
            "ticket",
            ticketA.Ticket);
        IActionResult retainedTicket = await fixture.Controller.DownloadGenerationArtifactPayload(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(retainedTicket).StatusCode);
    }

    [Fact]
    public void GlobalRevocationBlocksCurrentAndRetainedWindowsSupplementalRoutes()
    {
        using GenerationFixture fixture = new();
        fixture.Activate("generation-b");
        fixture.RevokeArtifact(GenerationFixture.WindowsProofArtifactId);

        fixture.SetQuery(null, null);
        IActionResult current = fixture.Controller.DownloadWindowsProofInstaller(
            GenerationFixture.WindowsProofFileName);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(current).StatusCode);

        fixture.SetQuery(null, null);
        IActionResult retained = fixture.Controller.DownloadGenerationWindowsProofInstallerByArtifactId(
            "generation-a",
            GenerationFixture.WindowsProofArtifactId);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(retained).StatusCode);
    }

    [Fact]
    public async Task UpstreamDigestRevocationBlocksCurrentAndRetainedAurSidecars()
    {
        using GenerationFixture fixture = new();
        fixture.Activate("generation-b");
        (_, PublicReleaseArtifactDto artifactB) = fixture.LoadArtifact("generation-b");
        fixture.RevokeDigest(artifactB.Sha256);
        fixture.SetQuery(null, null);
        IActionResult current = await fixture.Controller.DownloadFile(
            GenerationFixture.AurPkgbuildFileName,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(current).StatusCode);

        (_, PublicReleaseArtifactDto artifactA) = fixture.LoadArtifact("generation-a");
        fixture.RevokeDigest(artifactA.Sha256);
        fixture.SetQuery(null, null);
        IActionResult retained = await fixture.Controller.DownloadGenerationFile(
            "generation-a",
            GenerationFixture.AurPkgbuildFileName,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(retained).StatusCode);
    }

    [Fact]
    public async Task EstablishedKillSwitchAndForcedAccountPolicyApplyToLayoutV1CurrentAndRetainedRoutes()
    {
        using GenerationFixture fixture = new();
        fixture.Activate("generation-b");
        fixture.SetConfiguration("CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS", GenerationFixture.ArtifactId);
        fixture.SetQuery(null, null);
        ReleaseShelfSnapshot disabledSnapshot = fixture.ManifestService.CaptureShelfSnapshot();
        ArtifactDeliveryResolution disabledResolution = fixture.DeliveryPolicy.ResolveByPath(
            disabledSnapshot,
            GenerationFixture.FileName);
        Assert.Equal(ArtifactDeliveryFailure.Revoked, disabledResolution.Failure);
        IActionResult disabled = await fixture.Controller.DownloadFile(
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(disabled).StatusCode);

        fixture.SetConfiguration("CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS", null);
        fixture.SetConfiguration("CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS", "true");
        fixture.SetQuery(null, null);
        IActionResult forcedCurrent = await fixture.Controller.DownloadFile(
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.IsType<RedirectResult>(forcedCurrent);

        fixture.SetQuery(null, null);
        IActionResult forcedRetained = await fixture.Controller.DownloadGenerationFile(
            "generation-b",
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status409Conflict, Assert.IsType<ObjectResult>(forcedRetained).StatusCode);
    }

    [Fact]
    public void ForcedAccountPolicyCannotUseOpenPublicStableSidecarException()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.StableOpenGenerationId);
        ReleaseShelfSnapshot snapshot = fixture.ManifestService.CaptureShelfSnapshot();

        ArtifactDeliveryResolution openPublic = fixture.DeliveryPolicy.ResolveByArtifactId(
            snapshot,
            GenerationFixture.ArtifactId,
            ArtifactDeliveryRoles.PayloadMetadata);
        Assert.True(openPublic.Allowed);

        fixture.SetConfiguration(
            "CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS",
            "true");
        ArtifactDeliveryResolution forcedAccount =
            fixture.DeliveryPolicy.ResolveByArtifactId(
                snapshot,
                GenerationFixture.ArtifactId,
                ArtifactDeliveryRoles.PayloadMetadata);

        Assert.False(forcedAccount.Allowed);
        Assert.Equal(ArtifactDeliveryFailure.InvalidContract, forcedAccount.Failure);
        Assert.Equal("artifact_delivery_contract_invalid", forcedAccount.Code);
    }

    [Fact]
    public async Task ChannelWideCurrentRevocationBlocksArtifactOnlyPresentInRetainedGeneration()
    {
        using GenerationFixture fixture = new();
        fixture.WriteAndActivateChannelWideRevokedGeneration();
        fixture.SetQuery(null, null);

        ReleaseShelfSnapshot retainedSnapshot = fixture.ManifestService.CaptureShelfGeneration(
            "generation-a");
        PublicReleaseManifestDto retainedManifest = fixture.ManifestService.LoadManifest(retainedSnapshot);
        Assert.Single(retainedManifest.Downloads, item => item.Id == GenerationFixture.ArtifactId);
        ArtifactDeliveryResolution retainedResolution = fixture.DeliveryPolicy.ResolveByArtifactId(
            retainedSnapshot,
            GenerationFixture.ArtifactId);
        Assert.False(retainedResolution.Allowed);
        Assert.Equal(ArtifactDeliveryFailure.Revoked, retainedResolution.Failure);

        IActionResult retained = await fixture.Controller.DownloadGenerationArtifact(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);

        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(retained).StatusCode);
        Assert.Equal(
            "generation-a",
            fixture.ManifestService.CaptureShelfSnapshot().GenerationId);
        Assert.Equal(
            "generation-revoked",
            fixture.ManifestService.CaptureUnpinnedActiveShelfSnapshot().GenerationId);
    }

    [Fact]
    public async Task ReviewRequiredPublicByteHandoffServesOnlyBoundRawArtifactRoles()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) =
            fixture.LoadArtifact(GenerationFixture.PublicWindowsGenerationId);
        fixture.SetReleaseTruth(BuildReviewRequiredPublicByteHandoff(manifest, artifact));

        IActionResult installer = await fixture.Controller.DownloadFile(
            GenerationFixture.PublicWindowsFileName,
            CancellationToken.None);
        Assert.Equal("artifact-windows-public", await ReadFileResultAsync(installer));

        IActionResult payload = await fixture.Controller.DownloadGenerationFile(
            GenerationFixture.PublicWindowsGenerationId,
            GenerationFixture.PayloadFileName,
            CancellationToken.None);
        Assert.Equal("payload-windows-public", await ReadFileResultAsync(payload));

        IActionResult metadata = await fixture.Controller.DownloadGenerationFile(
            GenerationFixture.PublicWindowsGenerationId,
            GenerationFixture.PayloadFileName + ".json",
            CancellationToken.None);
        Assert.IsType<FileStreamResult>(metadata).FileStream.Dispose();

        IActionResult unrelated = await fixture.Controller.DownloadFile(
            GenerationFixture.AurPkgbuildFileName,
            CancellationToken.None);
        Assert.IsType<NotFoundResult>(unrelated);
    }

    [Theory]
    [InlineData("payload", "payload-windows-public")]
    [InlineData("metadata", null)]
    public async Task ReviewRequiredPublicByteHandoffServesOnlyBoundGenerationCompanionsAsImmutable(
        string role,
        string? expectedBody)
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) =
            fixture.LoadArtifact(GenerationFixture.PublicWindowsGenerationId);
        PublicReleaseTruthProjectionDto projection =
            BuildReviewRequiredPublicByteHandoff(manifest, artifact);
        string path =
            $"/downloads/g/{GenerationFixture.PublicWindowsGenerationId}/install/{GenerationFixture.ArtifactId}/{role}";
        fixture.SetCompanionRequest(path);
        fixture.SetReleaseTruth(projection);

        IActionResult result = role == "payload"
            ? await fixture.Controller.DownloadGenerationArtifactPayload(
                GenerationFixture.PublicWindowsGenerationId,
                GenerationFixture.ArtifactId,
                CancellationToken.None)
            : await fixture.Controller.DownloadGenerationArtifactPayloadMetadata(
                GenerationFixture.PublicWindowsGenerationId,
                GenerationFixture.ArtifactId,
                CancellationToken.None);

        if (expectedBody is not null)
        {
            Assert.Equal(expectedBody, await ReadFileResultAsync(result));
        }
        else
        {
            await Assert.IsType<FileStreamResult>(result).FileStream.DisposeAsync();
        }
        Assert.Equal(
            "public, max-age=31536000, immutable",
            fixture.Controller.Response.Headers.CacheControl.ToString());
        Assert.Equal(
            GenerationFixture.PublicWindowsGenerationId,
            fixture.Controller.Response.Headers[
                "X-Chummer-Release-Generation"].ToString());
    }

    [Fact]
    public async Task ReviewRequiredGenerationCompanionFailsClosedOnArtifactHandoffBindingDrift()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) =
            fixture.LoadArtifact(GenerationFixture.PublicWindowsGenerationId);
        PublicReleaseTruthProjectionDto projection =
            BuildReviewRequiredPublicByteHandoff(manifest, artifact);
        string path =
            $"/downloads/g/{GenerationFixture.PublicWindowsGenerationId}/install/{GenerationFixture.ArtifactId}/payload";
        fixture.SetCompanionRequest(path);
        fixture.SetReleaseTruth(projection with
        {
            ArtifactHandoff = projection.ArtifactHandoff! with
            {
                Sha256 = new string('f', 64)
            }
        });

        ObjectResult blocked = Assert.IsType<ObjectResult>(
            await fixture.Controller.DownloadGenerationArtifactPayload(
                GenerationFixture.PublicWindowsGenerationId,
                GenerationFixture.ArtifactId,
                CancellationToken.None));

        Assert.Equal(StatusCodes.Status503ServiceUnavailable, blocked.StatusCode);
        Assert.Equal(
            "private, no-store, max-age=0",
            fixture.Controller.Response.Headers.CacheControl.ToString());
        AssertPrivateNoStoreHeaders(fixture.Controller.Response.Headers);
        Assert.DoesNotContain(
            "immutable",
            fixture.Controller.Response.Headers.CacheControl.ToString(),
            StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("payload")]
    [InlineData("metadata")]
    public async Task GenerationCompanionVerificationFailureIsNeverImmutable(
        string role)
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        _ = fixture.LoadArtifact(
            GenerationFixture.PublicWindowsGenerationId);
        fixture.CorruptGenerationCompanion(
            GenerationFixture.PublicWindowsGenerationId,
            role);
        string path =
            $"/downloads/g/{GenerationFixture.PublicWindowsGenerationId}/install/{GenerationFixture.ArtifactId}/{role}";
        fixture.SetCompanionRequest(path);

        IActionResult result = role == "payload"
            ? await fixture.Controller.DownloadGenerationArtifactPayload(
                GenerationFixture.PublicWindowsGenerationId,
                GenerationFixture.ArtifactId,
                CancellationToken.None)
            : await fixture.Controller.DownloadGenerationArtifactPayloadMetadata(
                GenerationFixture.PublicWindowsGenerationId,
                GenerationFixture.ArtifactId,
                CancellationToken.None);

        ObjectResult failure = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, failure.StatusCode);
        AssertPrivateNoStoreHeaders(fixture.Controller.Response.Headers);
        Assert.DoesNotContain(
            "immutable",
            fixture.Controller.Response.Headers.CacheControl.ToString(),
            StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(
        "GET",
        "/downloads/g/generation-windows-public/files/chummer-windows-public-installer.exe",
        "application/octet-stream")]
    [InlineData(
        "HEAD",
        "/downloads/g/generation-windows-public/files/chummer-windows-public-installer.exe",
        "application/octet-stream")]
    [InlineData(
        "GET",
        "/downloads/g/generation-windows-public/install/shared-account-required-installer/payload",
        "application/octet-stream")]
    [InlineData(
        "HEAD",
        "/downloads/g/generation-windows-public/install/shared-account-required-installer/payload",
        "application/octet-stream")]
    [InlineData(
        "GET",
        "/downloads/g/generation-windows-public/install/shared-account-required-installer/metadata",
        "application/json; charset=utf-8")]
    [InlineData(
        "HEAD",
        "/downloads/g/generation-windows-public/install/shared-account-required-installer/metadata",
        "application/json; charset=utf-8")]
    public async Task ProductionNoStoreBoundaryPreservesVerifiedCanonicalGenerationBytes(
        string method,
        string target,
        string expectedContentType)
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        await using GenerationHttpApp app = await fixture.StartHttpAppAsync();
        using HttpClient client = app.CreateClient();
        using var request = new HttpRequestMessage(new HttpMethod(method), target);

        using HttpResponseMessage response = await client.SendAsync(request);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(
            PublicReleaseResponseCachePolicy.ImmutableCacheControl,
            response.Headers.CacheControl?.ToString());
        Assert.Equal(
            GenerationFixture.PublicWindowsGenerationId,
            Assert.Single(response.Headers.GetValues(
                "X-Chummer-Release-Generation")));
        Assert.Equal(
            expectedContentType,
            response.Content.Headers.ContentType?.ToString());
        Assert.Null(response.Content.Headers.ContentDisposition);
        Assert.True(response.Content.Headers.ContentLength > 0);
        Assert.False(response.Headers.Contains("CDN-Cache-Control"));
        Assert.False(response.Headers.Contains("Cloudflare-CDN-Cache-Control"));
        Assert.False(response.Headers.Contains("Surrogate-Control"));
        Assert.False(response.Headers.Contains("Pragma"));
        Assert.Null(response.Content.Headers.Expires);

        byte[] body = await response.Content.ReadAsByteArrayAsync();
        if (method == HttpMethods.Head)
        {
            Assert.Empty(body);
        }
        else
        {
            Assert.Equal(response.Content.Headers.ContentLength, body.LongLength);
        }
    }

    [Theory]
    [InlineData(
        "/downloads/g/generation-windows-public/install/shared-account-required-installer",
        HttpStatusCode.OK)]
    [InlineData(
        "/downloads/g/generation-windows-public/releases.json",
        HttpStatusCode.OK)]
    [InlineData(
        "/downloads/install/shared-account-required-installer/payload",
        HttpStatusCode.OK)]
    [InlineData(
        "/downloads/g/generation-windows-public/files/chummer-windows-public-installer.exe?unknown=value",
        HttpStatusCode.OK)]
    [InlineData(
        "/downloads/g/generation-windows-public/install/shared-account-required-installer/PAYLOAD",
        HttpStatusCode.NotFound)]
    [InlineData(
        "/downloads/g/generation-windows-public/install/shared-account-required-installer/payload?unknown=value",
        HttpStatusCode.NotFound)]
    [InlineData(
        "/downloads/g/generation-windows-public/install/shared-account-required-installer/payload?ticket=invalid",
        HttpStatusCode.Unauthorized)]
    [InlineData(
        "/downloads/g/generation-windows-public/install/shared-account-required-installer/payload?claimCode=invalid",
        HttpStatusCode.Unauthorized)]
    [InlineData(
        "/downloads/g/generation-windows-public/install/shared-account-required-installer/payload/",
        HttpStatusCode.NotFound)]
    [InlineData(
        "/downloads/g/generation-windows-public/files/missing.exe",
        HttpStatusCode.NotFound)]
    public async Task ProductionNoStoreBoundaryRejectsUnmarkedCredentialAndNoncanonicalVariants(
        string target,
        HttpStatusCode expectedStatus)
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        await using GenerationHttpApp app = await fixture.StartHttpAppAsync();
        using HttpClient client = app.CreateClient();

        using HttpResponseMessage response = await client.GetAsync(target);

        Assert.Equal(expectedStatus, response.StatusCode);
        AssertPrivateNoStoreHeaders(response);
    }

    [Fact]
    public async Task ProductionNoStoreBoundaryRejectsCredentialHeadersAndRanges()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        await using GenerationHttpApp app = await fixture.StartHttpAppAsync();
        using HttpClient client = app.CreateClient();
        string target =
            $"/downloads/g/{GenerationFixture.PublicWindowsGenerationId}/files/{GenerationFixture.PublicWindowsFileName}";

        (string Name, string Value)[] privateRequestHeaders =
        [
            ("Authorization", "Bearer test-credential"),
            ("Cookie", "session=test-credential"),
            ("Proxy-Authorization", "Bearer test-credential"),
            ("If-None-Match", "\"test-etag\""),
            ("If-Modified-Since", "Wed, 21 Oct 2015 07:28:00 GMT")
        ];
        foreach ((string name, string value) in privateRequestHeaders)
        {
            using var privateRequest =
                new HttpRequestMessage(HttpMethod.Get, target);
            Assert.True(
                privateRequest.Headers.TryAddWithoutValidation(name, value));
            using HttpResponseMessage privateResponse =
                await client.SendAsync(privateRequest);
            Assert.Equal(HttpStatusCode.OK, privateResponse.StatusCode);
            AssertPrivateNoStoreHeaders(privateResponse);
        }

        using var rangeRequest = new HttpRequestMessage(HttpMethod.Get, target);
        rangeRequest.Headers.Range =
            new System.Net.Http.Headers.RangeHeaderValue(0, 3);
        using HttpResponseMessage range = await client.SendAsync(rangeRequest);
        Assert.Equal(HttpStatusCode.PartialContent, range.StatusCode);
        AssertPrivateNoStoreHeaders(range);

        using var unsatisfiedRangeRequest =
            new HttpRequestMessage(HttpMethod.Get, target);
        unsatisfiedRangeRequest.Headers.Range =
            new System.Net.Http.Headers.RangeHeaderValue(
                long.MaxValue - 1,
                long.MaxValue);
        using HttpResponseMessage unsatisfiedRange =
            await client.SendAsync(unsatisfiedRangeRequest);
        Assert.Equal(
            HttpStatusCode.RequestedRangeNotSatisfiable,
            unsatisfiedRange.StatusCode);
        AssertPrivateNoStoreHeaders(unsatisfiedRange);
    }

    [Fact]
    public async Task ProductionNoStoreBoundaryKeepsValidCredentialDownloadsPrivate()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) =
            fixture.LoadArtifact("generation-a");
        ReleaseShelfSnapshot snapshot =
            fixture.ManifestService.CaptureShelfGeneration("generation-a");
        InstallBootstrapTicketIssueResult ticket =
            fixture.InstallBootstrapTickets.IssueBound(
                artifact.Id,
                fixture.DeliveryPolicy.BuildCredentialBindings(
                    snapshot,
                    [artifact]),
                "generation-a",
                "user-generation-a",
                "subject-generation-a");
        DownloadDispatchResult dispatch = fixture.InstallLinking.IssueDownload(
            manifest,
            artifact,
            "user-generation-a",
            "subject-generation-a");
        Assert.NotNull(dispatch.ClaimTicket);

        await using GenerationHttpApp app = await fixture.StartHttpAppAsync();
        using HttpClient client = app.CreateClient();
        string[] targets =
        [
            $"/downloads/g/generation-a/install/{GenerationFixture.ArtifactId}/payload?ticket={Uri.EscapeDataString(ticket.Ticket)}",
            $"/downloads/g/generation-a/files/{GenerationFixture.FileName}?claimCode={Uri.EscapeDataString(dispatch.ClaimTicket!.ClaimCode)}"
        ];
        foreach (string target in targets)
        {
            using HttpResponseMessage response = await client.GetAsync(target);
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            Assert.NotEmpty(await response.Content.ReadAsByteArrayAsync());
            AssertPrivateNoStoreHeaders(response);
        }
    }

    [Fact]
    public async Task ProductionNoStoreBoundaryKeepsVerificationErrorsPrivate()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        _ = fixture.LoadArtifact(
            GenerationFixture.PublicWindowsGenerationId);
        fixture.CorruptGenerationCompanion(
            GenerationFixture.PublicWindowsGenerationId,
            "payload");
        await using GenerationHttpApp app = await fixture.StartHttpAppAsync();
        using HttpClient client = app.CreateClient();
        string target =
            $"/downloads/g/{GenerationFixture.PublicWindowsGenerationId}/install/{GenerationFixture.ArtifactId}/payload";

        using HttpResponseMessage response = await client.GetAsync(target);

        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        AssertPrivateNoStoreHeaders(response);
    }

    [Theory]
    [InlineData("GET", "payload")]
    [InlineData("HEAD", "payload")]
    [InlineData("GET", "metadata")]
    [InlineData("HEAD", "metadata")]
    public async Task ComposedReviewPipelineServesGenerationCompanionsButDeniesCurrentAliases(
        string method,
        string role)
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) =
            fixture.LoadArtifact(GenerationFixture.PublicWindowsGenerationId);
        PublicReleaseTruthProjectionDto projection =
            BuildReviewRequiredPublicByteHandoff(manifest, artifact);
        string generationPath =
            $"/downloads/g/{GenerationFixture.PublicWindowsGenerationId}/install/{GenerationFixture.ArtifactId}/{role}";
        var generation = await fixture.InvokeComposedCompanionAsync(
            projection,
            generationPath,
            method,
            role == "payload"
                ? controller => controller.DownloadGenerationArtifactPayload(
                    GenerationFixture.PublicWindowsGenerationId,
                    GenerationFixture.ArtifactId,
                    CancellationToken.None)
                : controller => controller.DownloadGenerationArtifactPayloadMetadata(
                    GenerationFixture.PublicWindowsGenerationId,
                    GenerationFixture.ArtifactId,
                    CancellationToken.None));

        Assert.True(generation.ControllerInvoked);
        Assert.IsType<FileStreamResult>(generation.Result);
        Assert.Equal(
            "public, max-age=31536000, immutable",
            generation.Context.Response.Headers.CacheControl.ToString());
        if (method == HttpMethods.Head)
        {
            Assert.Equal(0, generation.Context.Response.Body.Length);
        }
        else
        {
            Assert.True(generation.Context.Response.Body.Length > 0);
        }

        string currentPath =
            $"/downloads/install/{GenerationFixture.ArtifactId}/{role}";
        var current = await fixture.InvokeComposedCompanionAsync(
            projection,
            currentPath,
            method,
            role == "payload"
                ? controller => controller.DownloadCurrentArtifactPayload(
                    GenerationFixture.ArtifactId,
                    CancellationToken.None)
                : controller => controller.DownloadCurrentArtifactPayloadMetadata(
                    GenerationFixture.ArtifactId,
                    CancellationToken.None));

        Assert.False(current.ControllerInvoked);
        Assert.Null(current.Result);
        Assert.Equal(StatusCodes.Status409Conflict, current.Context.Response.StatusCode);
        Assert.Equal(
            "private, no-store, max-age=0",
            current.Context.Response.Headers.CacheControl.ToString());
        AssertPrivateNoStoreHeaders(current.Context.Response.Headers);
        Assert.DoesNotContain(
            "immutable",
            current.Context.Response.Headers.CacheControl.ToString(),
            StringComparison.Ordinal);
        if (method == HttpMethods.Head)
        {
            Assert.Equal(0, current.Context.Response.Body.Length);
        }
        else
        {
            current.Context.Response.Body.Position = 0;
            using JsonDocument denial = await JsonDocument.ParseAsync(
                current.Context.Response.Body);
            Assert.Equal(
                "review_required",
                denial.RootElement.GetProperty("status").GetString());
            Assert.Equal(
                projection.ReleaseDecisionSha256,
                denial.RootElement.GetProperty("releaseTruth")
                    .GetProperty("releaseDecisionSha256")
                    .GetString());
        }
    }

    [Theory]
    [InlineData("GET", "payload")]
    [InlineData("HEAD", "payload")]
    [InlineData("GET", "metadata")]
    [InlineData("HEAD", "metadata")]
    public async Task ComposedStableCurrentCompanionBypassesUnreadyAdmissionWithoutImmutableCaching(
        string method,
        string role)
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        (PublicReleaseManifestDto manifest, _) =
            fixture.LoadArtifact(GenerationFixture.PublicWindowsGenerationId);
        PublicReleaseTruthProjectionDto projection =
            BuildStableReleaseTruth(manifest);
        string path = $"/downloads/install/{GenerationFixture.ArtifactId}/{role}";

        var invocation = await fixture.InvokeComposedCompanionAsync(
            projection,
            path,
            method,
            role == "payload"
                ? controller => controller.DownloadCurrentArtifactPayload(
                    GenerationFixture.ArtifactId,
                    CancellationToken.None)
                : controller => controller.DownloadCurrentArtifactPayloadMetadata(
                    GenerationFixture.ArtifactId,
                    CancellationToken.None));

        Assert.True(invocation.ControllerInvoked);
        Assert.IsType<FileStreamResult>(invocation.Result);
        Assert.Equal(
            "private, no-store, max-age=0",
            invocation.Context.Response.Headers.CacheControl.ToString());
        AssertPrivateNoStoreHeaders(invocation.Context.Response.Headers);
        Assert.DoesNotContain(
            "immutable",
            invocation.Context.Response.Headers.CacheControl.ToString(),
            StringComparison.Ordinal);
        if (method == HttpMethods.Head)
        {
            Assert.Equal(0, invocation.Context.Response.Body.Length);
        }
        else
        {
            Assert.True(invocation.Context.Response.Body.Length > 0);
        }
    }

    [Theory]
    [InlineData("/downloads/g/generation-windows-public/install/shared-account-required-installer/PAYLOAD", "")]
    [InlineData("/downloads/g/generation-windows-public/install/shared-account-required-installer/payload", "?unknown=value")]
    [InlineData("/downloads/g/generation-windows-public/install/shared-account-required-installer/payload", "?ticket=one&ticket=two")]
    [InlineData("/downloads/g/generation-windows-public/install/shared-account-required-installer/payload", "?ticket=one&")]
    [InlineData("/downloads/g/generation-windows-public/install/shared-account-required-installer/payload", "?%74icket=one")]
    [InlineData("/downloads/g/generation-windows-public/install/shared-account-required-installer/payload", "?claimCode=one&claimCode=two")]
    [InlineData("/downloads/g/generation-windows-public/install/shared-account-required-installer/payload", "?ticket=one&claimCode=two")]
    [InlineData("/downloads/g/generation-windows-public/install/shared-account-required-installer/payload", "?ticket=")]
    [InlineData("/downloads/g/generation-windows-public/install/shared-account-required-installer/payload", "?claimCode=")]
    public async Task CompanionControllerRejectsCaseAndNoncanonicalQueryVariants(
        string path,
        string query)
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        fixture.SetCompanionRequestTarget(path, query, path + query);

        IActionResult result =
            await fixture.Controller.DownloadGenerationArtifactPayload(
                GenerationFixture.PublicWindowsGenerationId,
                GenerationFixture.ArtifactId,
                CancellationToken.None);

        Assert.IsType<NotFoundResult>(result);
        Assert.DoesNotContain(
            "immutable",
            fixture.Controller.Response.Headers.CacheControl.ToString(),
            StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("/downloads/g/generation-windows-public/install/shared-account-required-installer/%70ayload")]
    [InlineData("/downloads/g/generation-windows-public/install/ignored/../shared-account-required-installer/payload")]
    public async Task CompanionControllerRejectsEncodedAndTraversalRawTargets(
        string rawTarget)
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        string path =
            $"/downloads/g/{GenerationFixture.PublicWindowsGenerationId}/install/{GenerationFixture.ArtifactId}/payload";
        fixture.SetCompanionRequestTarget(path, string.Empty, rawTarget);

        IActionResult result =
            await fixture.Controller.DownloadGenerationArtifactPayload(
                GenerationFixture.PublicWindowsGenerationId,
                GenerationFixture.ArtifactId,
                CancellationToken.None);

        Assert.IsType<NotFoundResult>(result);
    }

    [Fact]
    public async Task CompanionControllerPreservesCanonicalClaimCodeRequestContract()
    {
        using GenerationFixture fixture = new();
        string path =
            $"/downloads/g/generation-a/install/{GenerationFixture.ArtifactId}/payload";
        fixture.SetCompanionRequest(
            path,
            queryName: "claimCode",
            queryValue: "unknown-but-canonical");

        IActionResult result =
            await fixture.Controller.DownloadGenerationArtifactPayload(
                "generation-a",
                GenerationFixture.ArtifactId,
                CancellationToken.None);

        Assert.IsType<UnauthorizedObjectResult>(result);
        AssertPrivateNoStoreHeaders(fixture.Controller.Response.Headers);
    }

    [Theory]
    [InlineData(
        "/downloads/install/shared-account-required-installer/payload",
        "?unknown=value",
        "/downloads/install/shared-account-required-installer/payload?unknown=value")]
    [InlineData(
        "/downloads/install/shared-account-required-installer/payload",
        "",
        "/downloads/install/shared-account-required-installer/%70ayload")]
    [InlineData(
        "/downloads/install/SHARED-account-required-installer/payload",
        "",
        "/downloads/install/SHARED-account-required-installer/payload")]
    public async Task CurrentCompanionControllerRejectsNoncanonicalTargetsWithNoStore(
        string path,
        string query,
        string rawTarget)
    {
        using GenerationFixture fixture = new();
        fixture.SetCompanionRequestTarget(path, query, rawTarget);

        IActionResult result =
            await fixture.Controller.DownloadCurrentArtifactPayload(
                GenerationFixture.ArtifactId,
                CancellationToken.None);

        Assert.IsType<NotFoundResult>(result);
        AssertPrivateNoStoreHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task ReviewRequiredPublicByteHandoffFailsClosedOnShelfBindingDrift()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) =
            fixture.LoadArtifact(GenerationFixture.PublicWindowsGenerationId);
        PublicReleaseTruthProjectionDto projection =
            BuildReviewRequiredPublicByteHandoff(manifest, artifact);
        fixture.SetReleaseTruth(projection with
        {
            ArtifactHandoff = projection.ArtifactHandoff! with
            {
                Sha256 = new string('f', 64)
            }
        });

        IActionResult result = await fixture.Controller.DownloadFile(
            GenerationFixture.PublicWindowsFileName,
            CancellationToken.None);

        ObjectResult blocked = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, blocked.StatusCode);
    }

    [Fact]
    public async Task ReviewRequiredPublicByteHandoffStillHonorsGlobalRevocation()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) =
            fixture.LoadArtifact(GenerationFixture.PublicWindowsGenerationId);
        fixture.SetReleaseTruth(BuildReviewRequiredPublicByteHandoff(manifest, artifact));
        fixture.RevokeArtifact(GenerationFixture.ArtifactId);

        IActionResult result = await fixture.Controller.DownloadFile(
            GenerationFixture.PublicWindowsFileName,
            CancellationToken.None);

        ObjectResult blocked = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status410Gone, blocked.StatusCode);
    }

    [Fact]
    public void InvalidCandidateImportProjectionCannotMutateSealedReviewAuthority()
    {
        using GenerationFixture fixture = new();
        PublicReleaseManifestDto sealedManifest =
            fixture.SealReviewRequiredPublicByteAuthority();
        string candidateProjectionLeaf =
            fixture.ConfigureInvalidCandidateImportProjectionLeaf();

        PublicProjectionOutputSnapshot publicProjection =
            new PublicProjectionSnapshotService(fixture.Configuration)
                .LoadHubLocalReleaseProof();
        PublicReleaseManifestDto guardedManifest =
            fixture.ManifestService.LoadManifest();
        PublicReleaseTruthCapture capture =
            fixture.CreateReleaseTruthProjectionService().CaptureWithAuthority();

        Assert.Equal(candidateProjectionLeaf, fixture.Configuration[
            PublicProjectionSnapshotService.SnapshotRootConfigurationKey]);
        Assert.True(publicProjection.IsConfigured);
        Assert.False(publicProjection.IsValid);
        Assert.Equal(sealedManifest.KnownIssueSummary, guardedManifest.KnownIssueSummary);
        Assert.Equal("review_required", guardedManifest.ProofStatus);
        Assert.Contains(
            "public projection",
            guardedManifest.SupportabilitySummary,
            StringComparison.OrdinalIgnoreCase);
        Assert.NotEqual(
            PublicReleaseTruthProjectionDto.Missing,
            capture.AuthoritySnapshotSha256);
        Assert.True(capture.Projection.AuthorityBound);
        Assert.True(capture.Projection.ReviewRequiredPublicByteHandoffsAllowed);
        Assert.False(capture.Projection.AvailabilityClaimsAllowed);
    }

    [Fact]
    public async Task StableCompatibilityManifestAddsOnlyAuthorityTruthToSealedLayoutV1Bytes()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) =
            fixture.LoadArtifact(GenerationFixture.PublicWindowsGenerationId);
        PublicReleaseTruthProjectionDto releaseTruth =
            BuildReviewRequiredPublicByteHandoff(manifest, artifact);
        byte[] sealedCompatibility = fixture.ReadCompatibilityManifestBytes(
            GenerationFixture.PublicWindowsGenerationId);

        FileContentResult result =
            Assert.IsType<FileContentResult>(
                await fixture.InvokeReleaseManifestWithAuthenticatedTruthAsync(
                    releaseTruth));
        JsonObject served = JsonNode.Parse(result.FileContents)!.AsObject();
        JsonNode? embeddedReleaseTruth = served["releaseTruth"];
        Assert.NotNull(embeddedReleaseTruth);
        Assert.True(served.Remove("releaseTruth"));
        JsonNode sealedBody = JsonNode.Parse(sealedCompatibility)!;

        Assert.True(JsonNode.DeepEquals(sealedBody, served));
        Assert.Equal("application/json; charset=utf-8", result.ContentType);
        Assert.Equal(
            GenerationFixture.PublicWindowsGenerationId,
            fixture.Controller.Response.Headers["X-Chummer-Release-Generation"].ToString());
        Assert.Equal(
            "private, no-store, max-age=0",
            fixture.Controller.Response.Headers.CacheControl.ToString());
        Assert.Equal(
            "no-store, max-age=0",
            fixture.Controller.Response.Headers["CDN-Cache-Control"].ToString());
        Assert.Equal(
            "no-store, max-age=0",
            fixture.Controller.Response.Headers["Cloudflare-CDN-Cache-Control"].ToString());
    }

    [Fact]
    public void StableCompatibilityManifestWithUnauthenticatedTruthKeepsGuardedFallback()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.PublicWindowsGenerationId);
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) =
            fixture.LoadArtifact(GenerationFixture.PublicWindowsGenerationId);
        fixture.SetReleaseTruth(BuildReviewRequiredPublicByteHandoff(manifest, artifact));
        fixture.RevokeArtifact(GenerationFixture.ArtifactId);

        IActionResult result = fixture.Controller.ReleaseManifest();

        OkObjectResult guarded = Assert.IsType<OkObjectResult>(result);
        PublicReleaseManifestDto payload =
            Assert.IsType<PublicReleaseManifestDto>(guarded.Value);
        Assert.Empty(payload.Downloads);
        Assert.Null(
            PublicReleaseTruthProjectionMiddleware.TryGetAuthoritySnapshotSha256(
                fixture.Controller.HttpContext));
    }

    [Fact]
    public async Task CompletionClaimsStayBoundToPromotedGenerationWhenCurrentShelfAdvances()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.ProtectedGenerationId);
        var resultA = new ReleaseBundlePromotionResult(
            Version: "run-a",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-07-15T12:00:00Z"),
            PromotedArtifactIds: [GenerationFixture.ArtifactId],
            DownloadsUrl: "/downloads",
            InstallDispatchUrls:
            [
                $"/downloads/g/generation-a/install/{GenerationFixture.ArtifactId}"
            ],
            DirectFileUrls: [],
            GenerationId: "generation-a",
            ActivationReceiptId: "activation-generation-a");
        var claims = new ReleaseUploadTicketClaims(
            SubjectId: "subject-release-operator",
            DisplayName: "Release operator",
            Email: "operator@example.test",
            IssuedAtUtc: DateTimeOffset.UtcNow,
            ExpiresAtUtc: DateTimeOffset.UtcNow.AddHours(1),
            TicketId: "ticket-generation-a");

        ReleaseBundlePromotionResult attached = fixture.InternalController.AttachSignedInInstallClaims(
            resultA,
            claims);

        ReleasePromotionInstallClaim claimA = Assert.Single(attached.SignedInInstallClaims!);
        Assert.StartsWith(
            $"/downloads/g/generation-a/install/{GenerationFixture.ArtifactId}",
            claimA.InstallDispatchUrl,
            StringComparison.Ordinal);
        Assert.Contains("claimCode=", claimA.InstallDispatchUrl, StringComparison.Ordinal);

        fixture.SetQuery("claimCode", claimA.ClaimCode);
        IActionResult currentB = await fixture.Controller.DownloadGenerationArtifact(
            GenerationFixture.ProtectedGenerationId,
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.IsType<UnauthorizedObjectResult>(currentB);

        fixture.SetQuery("claimCode", claimA.ClaimCode);
        IActionResult retainedA = await fixture.Controller.DownloadGenerationArtifact(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.Equal("artifact-a", await ReadFileResultAsync(retainedA));
    }

    private static PublicReleaseTruthProjectionDto BuildReviewRequiredPublicByteHandoff(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto artifact)
    {
        const string scopeSha256 =
            "d24e00334e53c8ca159d5dac93275374b6ac8d7798d13ec9548abcf53a6bc8cb";
        return new(
            ContractName: PublicReleaseTruthProjectionDto.Schema,
            ReleaseVersion: manifest.Version,
            Channel: "preview",
            ReleaseStatus: "published",
            RolloutState: "public_release_review_required",
            SupportabilityState: "review_required",
            AvailablePlatforms: ["windows"],
            PrimaryHeadByPlatform: new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["windows"] = "avalonia"
            },
            ArtifactCount: 1,
            DownloadAccessPosture: "open_public",
            KnownIssueSummary: "Preview remains review-required.",
            ManifestSha256: new string('a', 64),
            RegistryCommit: new string('b', 40),
            ReleaseDecisionStatus: "review_required",
            ReleaseDecisionSha256: new string('c', 64))
        {
            ReleaseScopeDecisionSha256 = scopeSha256,
            ArtifactHandoff = new PublicPreviewByteHandoffDto(
                ContractName: "chummer.public-preview-byte-handoff/v1",
                Status: "approved_public_preview_bytes",
                SourcePublicationState: "preview",
                ReleaseScopeDecisionSha256: scopeSha256,
                ReleaseVersion: manifest.Version,
                Channel: "preview",
                ArtifactId: artifact.Id,
                Head: artifact.Head!,
                Platform: artifact.PlatformId!,
                Rid: artifact.Rid!,
                Arch: artifact.Arch!,
                Sha256: artifact.Sha256,
                SizeBytes: artifact.SizeBytes!.Value,
                ArtifactAccessClass: artifact.InstallAccessClass!,
                SigningRequirement: "preview_unsigned_allowed",
                DownloadUrl: artifact.Url,
                PublicInstallRoute: $"/downloads/install/{artifact.Id}")
        };
    }

    private static PublicReleaseTruthProjectionDto BuildStableReleaseTruth(
        PublicReleaseManifestDto manifest)
        => new(
            ContractName: PublicReleaseTruthProjectionDto.Schema,
            ReleaseVersion: manifest.Version,
            Channel: "stable",
            ReleaseStatus: "published",
            RolloutState: "public_stable",
            SupportabilityState: "gold_supported",
            AvailablePlatforms: ["windows"],
            PrimaryHeadByPlatform: new Dictionary<string, string>(
                StringComparer.Ordinal)
            {
                ["windows"] = "avalonia"
            },
            ArtifactCount: 1,
            DownloadAccessPosture: "open_public",
            KnownIssueSummary: string.Empty,
            ManifestSha256: new string('a', 64),
            RegistryCommit: new string('b', 40),
            ReleaseDecisionStatus: "stable_ready",
            ReleaseDecisionSha256: new string('c', 64));

    private static async Task<string> ReadFileResultAsync(IActionResult result)
    {
        FileStreamResult file = Assert.IsType<FileStreamResult>(result);
        await using Stream stream = file.FileStream;
        using StreamReader reader = new(stream, Encoding.UTF8);
        return await reader.ReadToEndAsync();
    }

    private static void AssertPrivateNoStoreHeaders(IHeaderDictionary headers)
    {
        Assert.Equal(
            "private, no-store, max-age=0",
            headers.CacheControl.ToString());
        Assert.Equal(
            "no-store, max-age=0",
            headers["CDN-Cache-Control"].ToString());
        Assert.Equal(
            "no-store, max-age=0",
            headers["Cloudflare-CDN-Cache-Control"].ToString());
        Assert.Equal("no-store", headers["Surrogate-Control"].ToString());
        Assert.Equal("no-cache", headers.Pragma.ToString());
        Assert.Equal("0", headers.Expires.ToString());
    }

    private static void AssertPrivateNoStoreHeaders(
        HttpResponseMessage response)
    {
        Assert.True(response.Headers.CacheControl?.Private);
        Assert.True(response.Headers.CacheControl?.NoStore);
        Assert.Equal(TimeSpan.Zero, response.Headers.CacheControl?.MaxAge);
        Assert.Equal(
            "no-store, max-age=0",
            Assert.Single(response.Headers.GetValues("CDN-Cache-Control")));
        Assert.Equal(
            "no-store, max-age=0",
            Assert.Single(response.Headers.GetValues(
                "Cloudflare-CDN-Cache-Control")));
        Assert.Equal(
            "no-store",
            Assert.Single(response.Headers.GetValues("Surrogate-Control")));
        Assert.Equal(
            "no-cache",
            Assert.Single(response.Headers.GetValues("Pragma")));
        Assert.DoesNotContain(
            "immutable",
            response.Headers.CacheControl?.ToString() ?? string.Empty,
            StringComparison.Ordinal);
    }

    private sealed class GenerationHttpApp(
        WebApplication application) : IAsyncDisposable
    {
        public HttpClient CreateClient()
        {
            IServer server =
                application.Services.GetRequiredService<IServer>();
            IServerAddressesFeature addresses = server.Features
                .Get<IServerAddressesFeature>()
                ?? throw new InvalidOperationException(
                    "Kestrel did not expose a bound address.");
            return new HttpClient
            {
                BaseAddress = new Uri(addresses.Addresses.Single())
            };
        }

        public async ValueTask DisposeAsync()
        {
            await application.StopAsync();
            await application.DisposeAsync();
        }
    }

    private sealed class GenerationFixture : IDisposable
    {
        public const string ArtifactId = "shared-account-required-installer";
        public const string FileName = "chummer-shared-installer.dmg";
        public const string PayloadFileName = "chummer-shared-payload.zip";
        public const string ProtectedGenerationId = "generation-protected-b";
        public const string StableOpenGenerationId = "generation-stable-open";
        public const string PublicWindowsGenerationId = "generation-windows-public";
        public const string PublicWindowsFileName = "chummer-windows-public-installer.exe";
        public const string WindowsProofArtifactId = "avalonia-win-x64-installer";
        public const string WindowsProofFileName = "chummer-avalonia-win-x64-installer.exe";
        public const string AurPkgbuildFileName = "chummer6-bin.PKGBUILD";
        private const string PublishedAt = "2026-07-15T12:00:00Z";

        private readonly string _root = Path.Combine(
            Path.GetTempPath(),
            "generation-bound-download-auth-tests",
            Guid.NewGuid().ToString("N"));
        private readonly string _downloadsRoot;
        private readonly Dictionary<string, GenerationMetadata> _generations = new(StringComparer.Ordinal);
        private readonly ServiceProvider _serviceProvider;
        private readonly IHttpContextAccessor _httpContextAccessor;

        public GenerationFixture()
        {
            _downloadsRoot = Path.Combine(_root, "downloads");
            Directory.CreateDirectory(_downloadsRoot);
            WriteGeneration("generation-a", "run-a", "artifact-a", "payload-a", "account_required");
            WriteGeneration("generation-b", "run-b", "artifact-b", "payload-b", "open_public");
            WriteGeneration(
                ProtectedGenerationId,
                "run-protected-b",
                "artifact-protected-b",
                "payload-protected-b",
                "account_required");
            WriteGeneration(
                StableOpenGenerationId,
                "run-stable-open",
                "artifact-stable-open",
                "payload-stable-open",
                "open_public",
                stableSidecarWithSemanticManifest: true);
            WriteGeneration(
                PublicWindowsGenerationId,
                "run-windows-public",
                "artifact-windows-public",
                "payload-windows-public",
                "open_public",
                platform: "windows",
                rid: "win-x64",
                arch: "x64",
                kind: "installer",
                artifactFileName: PublicWindowsFileName,
                useRawDownloadUrl: true);
            Activate("generation-a");

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = _downloadsRoot,
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking.json"),
                    ["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(_root, "upload-sessions"),
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
                    ["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = string.Empty,
                    ["CHUMMER_HUB_REGISTRY_BASE_URL"] = string.Empty,
                    ["CHUMMER_WINDOWS_PROOF_LEGACY_SHELF_FALLBACK"] = "true",
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://127.0.0.1:9"
                })
                .Build();

            IConfiguration configuration = Configuration;

            var services = new ServiceCollection();
            services.AddSingleton<IConfiguration>(configuration);
            services.AddLogging();
            services.AddControllers();
            services.AddHubPublicGuideContext();
            _serviceProvider = services.BuildServiceProvider();
            _httpContextAccessor = _serviceProvider.GetRequiredService<IHttpContextAccessor>();
            ManifestService = _serviceProvider.GetRequiredService<PublicReleaseManifestService>();
            IDataProtectionProvider dataProtection = DataProtectionProvider.Create(
                new DirectoryInfo(Path.Combine(_root, "keys")));
            InstallLinking = new InstallLinkingService(
                new InstallLinkingStore(
                    configuration,
                    dataProtection,
                    NullLogger<InstallLinkingStore>.Instance),
                configuration);
            InstallBootstrapTickets = new InstallBootstrapTicketService(dataProtection, configuration);
            DeliveryPolicy = _serviceProvider.GetRequiredService<ArtifactDeliveryPolicy>();
            var accounts = new AccountService(
                new CommunityStore(configuration, NullLogger<CommunityStore>.Instance));
            InternalController = new InternalReleaseBundlesController(
                new ReleaseBundlePromotionService(
                    configuration,
                    NullLogger<ReleaseBundlePromotionService>.Instance),
                new ReleaseBundleUploadSessionService(
                    configuration,
                    NullLogger<ReleaseBundleUploadSessionService>.Instance),
                configuration,
                new ReleaseUploadTicketService(dataProtection, configuration),
                ManifestService,
                accounts,
                InstallLinking);
            var releaseSelection = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
            Controller = new DownloadsCompatibilityController(
                ManifestService,
                new WindowsProofInstallerService(configuration),
                new AurPackageCatalogService(configuration),
                releaseSelection,
                InstallLinking,
                InstallBootstrapTickets,
                new HubIdentityClient(new HttpClient(), configuration, NullLogger<HubIdentityClient>.Instance),
                configuration,
                NullLogger<DownloadsCompatibilityController>.Instance,
                DeliveryPolicy);
            SetQuery(null, null);
        }

        public PublicReleaseManifestService ManifestService { get; }
        public InstallLinkingService InstallLinking { get; }
        public InstallBootstrapTicketService InstallBootstrapTickets { get; }
        public IConfigurationRoot Configuration { get; }
        public ArtifactDeliveryPolicy DeliveryPolicy { get; }
        public DownloadsCompatibilityController Controller { get; }
        public InternalReleaseBundlesController InternalController { get; }

        public (PublicReleaseManifestDto Manifest, PublicReleaseArtifactDto Artifact) LoadArtifact(string generationId)
        {
            SetQuery(null, null);
            ReleaseShelfSnapshot snapshot = ManifestService.CaptureShelfGeneration(generationId);
            PublicReleaseManifestDto manifest = ManifestService.LoadManifest(snapshot);
            return (manifest, Assert.Single(manifest.Downloads, item => item.Id == ArtifactId));
        }

        public void SetQuery(string? name, string? value)
        {
            var context = new DefaultHttpContext();
            if (!string.IsNullOrWhiteSpace(name) && value is not null)
            {
                context.Request.QueryString = QueryString.Create(name, value);
            }

            Controller.ControllerContext = new ControllerContext { HttpContext = context };
            _httpContextAccessor.HttpContext = context;
        }

        public void SetCompanionRequest(
            string path,
            string? queryName = null,
            string? queryValue = null,
            string? rawTarget = null,
            string method = "GET")
        {
            var context = new DefaultHttpContext();
            context.Request.Method = method;
            context.Request.Path = path;
            if (!string.IsNullOrWhiteSpace(queryName) && queryValue is not null)
            {
                context.Request.QueryString = QueryString.Create(
                    queryName,
                    queryValue);
            }
            context.Features.Get<IHttpRequestFeature>()!.RawTarget =
                rawTarget ?? path + context.Request.QueryString.Value;
            Controller.ControllerContext =
                new ControllerContext { HttpContext = context };
            _httpContextAccessor.HttpContext = context;
        }

        public void SetCompanionRequestTarget(
            string path,
            string query,
            string rawTarget,
            string method = "GET")
        {
            var context = new DefaultHttpContext();
            context.Request.Method = method;
            context.Request.Path = path;
            context.Request.QueryString = new QueryString(query);
            context.Features.Get<IHttpRequestFeature>()!.RawTarget = rawTarget;
            Controller.ControllerContext =
                new ControllerContext { HttpContext = context };
            _httpContextAccessor.HttpContext = context;
        }

        public async Task<(
            IActionResult? Result,
            HttpContext Context,
            bool ControllerInvoked)> InvokeComposedCompanionAsync(
            PublicReleaseTruthProjectionDto projection,
            string path,
            string method,
            Func<DownloadsCompatibilityController, Task<IActionResult>> action)
        {
            var context = new DefaultHttpContext();
            context.Request.Method = method;
            context.Request.Path = path;
            context.Features.Get<IHttpRequestFeature>()!.RawTarget = path;
            context.Response.Body = new MemoryStream();
            context.RequestServices = _serviceProvider;
            IActionResult? result = null;
            bool controllerInvoked = false;
            var admission = new InstallLinkingRequestAdmissionMiddleware(
                async controllerContext =>
                {
                    controllerInvoked = true;
                    Controller.ControllerContext =
                        new ControllerContext { HttpContext = controllerContext };
                    _httpContextAccessor.HttpContext = controllerContext;
                    result = await action(Controller);
                    await result.ExecuteResultAsync(
                        Controller.ControllerContext);
                });
            var releaseTruth = new PublicReleaseTruthProjectionMiddleware(
                admissionContext => admission.InvokeAsync(
                    admissionContext,
                    new UnavailableCompanionReadinessProbe()));
            var promotions = new ReleaseBundlePromotionService(
                Configuration,
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint: null);

            await releaseTruth.InvokeAsync(
                context,
                new FixedReleaseTruthProjection(
                    projection,
                    new string('d', 64)),
                promotions,
                new ReleaseShelfGenerationStore(Configuration),
                NullLogger<PublicReleaseTruthProjectionMiddleware>.Instance);
            return (result, context, controllerInvoked);
        }

        public void SetReleaseTruth(PublicReleaseTruthProjectionDto projection)
            => Controller.HttpContext.Items[
                PublicReleaseTruthProjectionMiddleware.HttpContextItemKey] = projection;

        public async Task<IActionResult> InvokeReleaseManifestWithAuthenticatedTruthAsync(
            PublicReleaseTruthProjectionDto projection)
        {
            IActionResult? result = null;
            var middleware = new PublicReleaseTruthProjectionMiddleware(context =>
            {
                Controller.ControllerContext =
                    new ControllerContext { HttpContext = context };
                _httpContextAccessor.HttpContext = context;
                result = Controller.ReleaseManifest();
                return Task.CompletedTask;
            });
            var context = new DefaultHttpContext();
            context.Request.Method = HttpMethods.Get;
            context.Request.Path = "/downloads/releases.json";
            var promotions = new ReleaseBundlePromotionService(
                Configuration,
                NullLogger<ReleaseBundlePromotionService>.Instance,
                promotionCheckpoint: null);
            await middleware.InvokeAsync(
                context,
                new FixedReleaseTruthProjection(projection, new string('d', 64)),
                promotions,
                new ReleaseShelfGenerationStore(Configuration),
                NullLogger<PublicReleaseTruthProjectionMiddleware>.Instance);
            return result
                ?? throw new InvalidOperationException(
                    "Authenticated release manifest middleware did not invoke the controller.");
        }

        public void RevokeArtifact(string artifactId)
            => Configuration["CHUMMER_RELEASE_REVOKED_ARTIFACT_IDS"] = artifactId;

        public void RevokeDigest(string sha256)
            => Configuration["CHUMMER_RELEASE_REVOKED_SHA256"] = sha256;

        public void CorruptGenerationCompanion(
            string generationId,
            string role)
        {
            string fileName = role switch
            {
                "payload" => PayloadFileName,
                "metadata" => PayloadFileName + ".json",
                _ => throw new ArgumentOutOfRangeException(
                    nameof(role),
                    role,
                    "Unknown companion role.")
            };
            File.WriteAllText(
                Path.Combine(
                    _downloadsRoot,
                    ReleaseShelfGenerationStore.GenerationsDirectoryName,
                    generationId,
                    "files",
                    fileName),
                "tampered-companion-bytes");
        }

        public void SetConfiguration(string key, string? value)
            => Configuration[key] = value;

        public async Task<GenerationHttpApp> StartHttpAppAsync()
        {
            _httpContextAccessor.HttpContext = null;
            WebApplicationBuilder builder = WebApplication.CreateBuilder();
            builder.WebHost.ConfigureKestrel(
                options => options.Listen(IPAddress.Loopback, 0));
            builder.Services
                .AddControllers()
                .AddApplicationPart(
                    typeof(DownloadsCompatibilityController).Assembly)
                .AddControllersAsServices();
            builder.Services.AddSingleton(Controller);

            WebApplication app = builder.Build();
            app.Use((context, next) =>
                PublicReleaseResponseCachePolicy.InvokeNoStoreBoundaryAsync(
                    context,
                    next,
                    requiresNoStore: true));
            app.UseRouting();
            app.MapControllers();
            try
            {
                await app.StartAsync();
                return new GenerationHttpApp(app);
            }
            catch
            {
                await app.DisposeAsync();
                throw;
            }
        }

        public PublicReleaseTruthProjectionService CreateReleaseTruthProjectionService()
            => new(
                ManifestService,
                new ReleaseSelectionService(new PublicCanonFileLoader(Configuration)),
                DeliveryPolicy);

        public byte[] ReadCompatibilityManifestBytes(string generationId)
            => ManifestService.LoadGenerationCompatibilityManifestBytes(
                ManifestService.CaptureShelfGeneration(generationId))
                ?? throw new InvalidDataException(
                    $"Generation '{generationId}' has no compatibility manifest.");

        public string ConfigureInvalidCandidateImportProjectionLeaf()
        {
            string leaf = Path.Combine(_root, "candidate-import-projection-leaf");
            Directory.CreateDirectory(leaf);
            File.WriteAllText(
                Path.Combine(
                    leaf,
                    "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json"),
                "{\"status\":\"candidate_import_ready\"}\n");
            Configuration[PublicProjectionSnapshotService.SnapshotRootConfigurationKey] =
                leaf;
            Configuration[PublicProjectionSnapshotService.SnapshotRequiredConfigurationKey] =
                "true";
            return leaf;
        }

        public PublicReleaseManifestDto SealReviewRequiredPublicByteAuthority()
        {
            Activate(PublicWindowsGenerationId);
            ReleaseShelfSnapshot snapshot = ManifestService.CaptureShelfSnapshot();
            var releaseSelection =
                new ReleaseSelectionService(new PublicCanonFileLoader(Configuration));
            PublicReleaseManifestDto manifest = DeliveryPolicy.FilterRevokedArtifacts(
                snapshot,
                releaseSelection.ApplyAccessPolicy(ManifestService.LoadManifest(snapshot)));
            byte[] canonicalBytes =
                ManifestService.LoadGenerationCanonicalManifestBytes(snapshot)
                ?? throw new InvalidDataException(
                    "Review-required authority source is missing its canonical manifest.");
            PublicReleaseTruthProjectionTests.AuthorityEnvelope authority =
                PublicReleaseTruthProjectionTests.BuildAuthorityEnvelope(
                    manifest,
                    "review_required",
                    manifestBytesOverride: canonicalBytes,
                    publicByteHandoff: true);
            string generationRoot = Path.Combine(
                _downloadsRoot,
                ReleaseShelfGenerationStore.GenerationsDirectoryName,
                PublicWindowsGenerationId);
            WriteAuthorityFile(
                generationRoot,
                PublicReleaseAuthorityEnvelopeProjection.CurrentInventoryPath,
                authority.CurrentBytes);
            WriteAuthorityFile(
                generationRoot,
                PublicReleaseAuthorityEnvelopeProjection.SnapshotInventoryPath,
                authority.SnapshotBytes);
            WriteAuthorityFile(
                generationRoot,
                "release-evidence/" + PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath,
                authority.DecisionBytes);

            string canonicalPath = Path.Combine(
                generationRoot,
                ReleaseShelfGenerationStore.CanonicalManifestFileName);
            string compatibilityPath = Path.Combine(
                generationRoot,
                ReleaseShelfGenerationStore.CompatibilityManifestFileName);
            var metadata = new GenerationMetadata(
                Version: manifest.Version,
                CanonicalSha256: Sha256(canonicalPath),
                CompatibilitySha256: Sha256(compatibilityPath),
                InventoryDigest:
                    ReleaseShelfGenerationStore.ComputeInventoryDigest(generationRoot));
            _generations[PublicWindowsGenerationId] = metadata;
            Dictionary<string, object?> candidate = BuildPointer(
                PublicWindowsGenerationId,
                metadata,
                "chummer.release-shelf.activation-candidate/v1");
            candidate["contractName"] = "chummer.release-shelf-activation-candidate";
            candidate["inventory"] =
                ReleaseShelfGenerationStore.BuildInventory(generationRoot);
            File.WriteAllText(
                Path.Combine(generationRoot, "activation-candidate.json"),
                JsonSerializer.Serialize(candidate));
            Activate(PublicWindowsGenerationId);
            SetQuery(null, null);
            return manifest;
        }

        public void WriteAndActivateChannelWideRevokedGeneration()
        {
            const string generationId = "generation-revoked";
            const string version = "run-revoked";
            string generationRoot = Path.Combine(_downloadsRoot, "generations", generationId);
            string filesRoot = Path.Combine(generationRoot, "files");
            Directory.CreateDirectory(filesRoot);
            File.WriteAllText(
                Path.Combine(filesRoot, "channel-revocation.json"),
                JsonSerializer.Serialize(new { status = "revoked" }));
            string canonicalPath = Path.Combine(
                generationRoot,
                ReleaseShelfGenerationStore.CanonicalManifestFileName);
            string compatibilityPath = Path.Combine(
                generationRoot,
                ReleaseShelfGenerationStore.CompatibilityManifestFileName);
            File.WriteAllText(
                canonicalPath,
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["generationId"] = generationId,
                    ["product"] = "chummer",
                    ["channelId"] = "preview",
                    ["version"] = version,
                    ["publishedAt"] = PublishedAt,
                    ["status"] = "revoked",
                    ["effectiveRolloutState"] = "revoked",
                    ["artifacts"] = Array.Empty<object>()
                }));
            File.WriteAllText(
                compatibilityPath,
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["generationId"] = generationId,
                    ["version"] = version,
                    ["channel"] = "preview",
                    ["publishedAt"] = PublishedAt,
                    ["status"] = "revoked",
                    ["downloads"] = Array.Empty<object>()
                }));
            var metadata = new GenerationMetadata(
                Version: version,
                CanonicalSha256: Sha256(canonicalPath),
                CompatibilitySha256: Sha256(compatibilityPath),
                InventoryDigest: ReleaseShelfGenerationStore.ComputeInventoryDigest(generationRoot));
            _generations[generationId] = metadata;
            Dictionary<string, object?> candidate = BuildPointer(
                generationId,
                metadata,
                "chummer.release-shelf.activation-candidate/v1");
            candidate["contractName"] = "chummer.release-shelf-activation-candidate";
            candidate["inventory"] = ReleaseShelfGenerationStore.BuildInventory(generationRoot);
            File.WriteAllText(
                Path.Combine(generationRoot, "activation-candidate.json"),
                JsonSerializer.Serialize(candidate));
            Activate(generationId);
        }

        public void Activate(string generationId)
        {
            string pointerPath = Path.Combine(
                _downloadsRoot,
                ReleaseShelfGenerationStore.CurrentPointerFileName);
            byte[]? previousPointerBytes = File.Exists(pointerPath)
                ? File.ReadAllBytes(pointerPath)
                : null;
            File.WriteAllText(
                Path.Combine(_downloadsRoot, ReleaseShelfGenerationStore.LayoutMarkerFileName),
                "release-shelf-layout-v1\n");
            GenerationMetadata metadata = _generations[generationId];
            byte[] targetPointerBytes = JsonSerializer.SerializeToUtf8Bytes(
                BuildPointer(generationId, metadata, "chummer.release-shelf.current/v1"));
            File.WriteAllBytes(pointerPath, targetPointerBytes);
            WriteCommittedActivationJournal(
                _downloadsRoot,
                targetPointerBytes,
                previousPointerBytes);
        }

        public void Dispose()
        {
            _httpContextAccessor.HttpContext = null;
            _serviceProvider.Dispose();
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }

        private void WriteGeneration(
            string generationId,
            string version,
            string artifactText,
            string payloadText,
            string installAccessClass,
            bool stableSidecarWithSemanticManifest = false,
            string platform = "macos",
            string rid = "osx-arm64",
            string arch = "arm64",
            string kind = "dmg",
            string artifactFileName = FileName,
            bool useRawDownloadUrl = false)
        {
            string generationRoot = Path.Combine(_downloadsRoot, "generations", generationId);
            string filesRoot = Path.Combine(generationRoot, "files");
            Directory.CreateDirectory(filesRoot);
            byte[] artifactBytes = Encoding.UTF8.GetBytes(artifactText);
            string artifactPath = Path.Combine(filesRoot, artifactFileName);
            File.WriteAllBytes(artifactPath, artifactBytes);
            string artifactSha256 = Convert.ToHexStringLower(SHA256.HashData(artifactBytes));
            byte[] payloadBytes = Encoding.UTF8.GetBytes(payloadText);
            string payloadPath = Path.Combine(filesRoot, PayloadFileName);
            File.WriteAllBytes(payloadPath, payloadBytes);
            string payloadSha256 = Convert.ToHexStringLower(SHA256.HashData(payloadBytes));
            string payloadUrl = stableSidecarWithSemanticManifest
                ? $"/downloads/g/{generationId}/install/{ArtifactId}/payload"
                : $"/downloads/g/{generationId}/files/{PayloadFileName}";
            string sidecarPayloadUrl = stableSidecarWithSemanticManifest
                ? $"https://chummer.run/downloads/files/{PayloadFileName}"
                : payloadUrl;
            string artifactDownloadUrl = useRawDownloadUrl
                ? $"/downloads/g/{generationId}/files/{artifactFileName}"
                : $"/downloads/g/{generationId}/install/{ArtifactId}";
            var payloadSidecar = new Dictionary<string, object?>
            {
                ["contractName"] = "chummer6-ui.windows_bootstrap_payload",
                ["fileName"] = PayloadFileName,
                ["downloadUrl"] = sidecarPayloadUrl,
                ["sha256"] = payloadSha256,
                ["sizeBytes"] = payloadBytes.Length,
                ["installerFileName"] = artifactFileName,
                ["releaseVersion"] = version
            };
            if (stableSidecarWithSemanticManifest)
            {
                payloadSidecar["payloadAcquisitionMode"] = "download";
            }

            File.WriteAllText(
                Path.Combine(filesRoot, PayloadFileName + ".json"),
                JsonSerializer.Serialize(payloadSidecar));
            WriteWindowsProofInstaller(generationRoot, version);
            WriteAurCatalog(
                generationRoot,
                generationId,
                artifactSha256,
                artifactBytes.LongLength,
                artifactFileName);

            var canonical = new Dictionary<string, object?>
            {
                ["generationId"] = generationId,
                ["product"] = "chummer",
                ["channelId"] = "preview",
                ["version"] = version,
                ["publishedAt"] = PublishedAt,
                ["status"] = "published",
                ["artifacts"] = new object[]
                {
                    new Dictionary<string, object?>
                    {
                        ["artifactId"] = ArtifactId,
                        ["head"] = "avalonia",
                        ["platform"] = platform,
                        ["rid"] = rid,
                        ["arch"] = arch,
                        ["kind"] = kind,
                        ["compatibilityState"] =
                            generationId == PublicWindowsGenerationId
                                ? "compatible"
                                : null,
                        ["platformLabel"] = "Shared account-required installer",
                        ["fileName"] = artifactFileName,
                        ["downloadUrl"] = artifactDownloadUrl,
                        ["payloadFileName"] = PayloadFileName,
                        ["payloadDownloadUrl"] = payloadUrl,
                        ["payloadSha256"] = payloadSha256,
                        ["payloadSizeBytes"] = payloadBytes.Length,
                        ["sha256"] = artifactSha256,
                        ["sizeBytes"] = artifactBytes.Length,
                        ["installAccessClass"] = installAccessClass
                    }
                }
            };
            var compatibility = new Dictionary<string, object?>
            {
                ["generationId"] = generationId,
                ["version"] = version,
                ["channel"] = "preview",
                ["publishedAt"] = PublishedAt,
                ["status"] = "published",
                ["downloads"] = new object[]
                {
                    new Dictionary<string, object?>
                    {
                        ["id"] = ArtifactId,
                        ["platform"] = platform,
                        ["url"] = artifactDownloadUrl,
                        ["payloadFileName"] = PayloadFileName,
                        ["payloadDownloadUrl"] = payloadUrl,
                        ["payloadSha256"] = payloadSha256,
                        ["payloadSizeBytes"] = payloadBytes.Length,
                        ["sha256"] = artifactSha256,
                        ["sizeBytes"] = artifactBytes.Length,
                        ["head"] = "avalonia",
                        ["platformId"] = platform,
                        ["rid"] = rid,
                        ["arch"] = arch,
                        ["kind"] = kind,
                        ["fileName"] = artifactFileName,
                        ["installAccessClass"] = installAccessClass
                    }
                }
            };

            string canonicalPath = Path.Combine(generationRoot, ReleaseShelfGenerationStore.CanonicalManifestFileName);
            string compatibilityPath = Path.Combine(generationRoot, ReleaseShelfGenerationStore.CompatibilityManifestFileName);
            File.WriteAllText(canonicalPath, JsonSerializer.Serialize(canonical));
            File.WriteAllText(compatibilityPath, JsonSerializer.Serialize(compatibility));
            var metadata = new GenerationMetadata(
                Version: version,
                CanonicalSha256: Sha256(canonicalPath),
                CompatibilitySha256: Sha256(compatibilityPath),
                InventoryDigest: ReleaseShelfGenerationStore.ComputeInventoryDigest(generationRoot));
            _generations[generationId] = metadata;

            Dictionary<string, object?> candidate = BuildPointer(
                generationId,
                metadata,
                "chummer.release-shelf.activation-candidate/v1");
            candidate["contractName"] = "chummer.release-shelf-activation-candidate";
            candidate["inventory"] = ReleaseShelfGenerationStore.BuildInventory(generationRoot);
            File.WriteAllText(
                Path.Combine(generationRoot, "activation-candidate.json"),
                JsonSerializer.Serialize(candidate));
        }

        private static void WriteWindowsProofInstaller(string generationRoot, string releaseVersion)
        {
            string proofRoot = Path.Combine(generationRoot, "proof", "windows");
            string signingRoot = Path.Combine(generationRoot, "signing");
            Directory.CreateDirectory(proofRoot);
            Directory.CreateDirectory(signingRoot);
            byte[] installerBytes = Encoding.UTF8.GetBytes(
                "proof-installer\0ChummerInstaller.Payload.zip\0Samples/Legacy/Soma-Career.chum5\0tail");
            File.WriteAllBytes(Path.Combine(proofRoot, WindowsProofFileName), installerBytes);
            string sha256 = Convert.ToHexStringLower(SHA256.HashData(installerBytes));
            File.WriteAllText(
                Path.Combine(signingRoot, "signing-avalonia-win-x64.receipt.json"),
                JsonSerializer.Serialize(new
                {
                    contractName = "chummer6-ui.desktop_artifact_signing",
                    generatedAt = "2026-06-19T12:01:00Z",
                    platform = "windows",
                    app = "avalonia",
                    rid = "win-x64",
                    releaseChannel = "preview",
                    releaseVersion,
                    signingStatus = "pass",
                    notarizationStatus = (string?)null,
                    artifacts = new[]
                    {
                        new
                        {
                            fileName = WindowsProofFileName,
                            sha256,
                            kind = "installer",
                            signingStatus = "pass",
                            notarizationStatus = (string?)null
                        }
                    }
                }));
        }

        private static void WriteAurCatalog(
            string generationRoot,
            string generationId,
            string upstreamSha256,
            long upstreamSizeBytes,
            string upstreamFileName)
        {
            string filesRoot = Path.Combine(generationRoot, "files");
            string sourceArchivePath = Path.Combine(filesRoot, "chummer6-bin-aur-source.tar.gz");
            string pkgbuildPath = Path.Combine(filesRoot, AurPkgbuildFileName);
            string srcinfoPath = Path.Combine(filesRoot, "chummer6-bin.SRCINFO");
            File.WriteAllText(sourceArchivePath, "aur-source-" + generationId);
            File.WriteAllText(pkgbuildPath, "pkgbuild-" + generationId);
            File.WriteAllText(srcinfoPath, "srcinfo-" + generationId);
            string prefix = $"/downloads/g/{generationId}/files/";
            File.WriteAllText(
                Path.Combine(generationRoot, "aur-packages.json"),
                JsonSerializer.Serialize(new
                {
                    generationId,
                    packages = new[]
                    {
                        new
                        {
                            id = "chummer6-bin",
                            packageName = "chummer6-bin",
                            packageVersion = "20260715.120000",
                            title = "Arch / CachyOS",
                            summary = "Generation-bound AUR package.",
                            platformLabel = "Arch / CachyOS",
                            installCommand = "makepkg -si",
                            sourceArchiveFileName = Path.GetFileName(sourceArchivePath),
                            sourceArchiveUrl = prefix + Path.GetFileName(sourceArchivePath),
                            sourceArchiveSha256 = Sha256(sourceArchivePath),
                            sourceArchiveSizeBytes = new FileInfo(sourceArchivePath).Length,
                            pkgbuildFileName = Path.GetFileName(pkgbuildPath),
                            pkgbuildUrl = prefix + Path.GetFileName(pkgbuildPath),
                            pkgbuildSha256 = Sha256(pkgbuildPath),
                            srcinfoFileName = Path.GetFileName(srcinfoPath),
                            srcinfoUrl = prefix + Path.GetFileName(srcinfoPath),
                            srcinfoSha256 = Sha256(srcinfoPath),
                            upstreamArtifactId = ArtifactId,
                            upstreamArtifactFileName = upstreamFileName,
                            upstreamArtifactUrl = prefix + upstreamFileName,
                            upstreamArtifactSha256 = upstreamSha256,
                            upstreamArtifactSizeBytes = upstreamSizeBytes
                        }
                    }
                }));
        }

        private static Dictionary<string, object?> BuildPointer(
            string generationId,
            GenerationMetadata metadata,
            string schemaVersion)
            => new()
            {
                ["schemaVersion"] = schemaVersion,
                ["generationId"] = generationId,
                ["releaseVersion"] = metadata.Version,
                ["channel"] = "preview",
                ["publishedAt"] = PublishedAt,
                ["manifests"] = new Dictionary<string, object?>
                {
                    ["canonical"] = new Dictionary<string, object?>
                    {
                        ["path"] = $"/downloads/g/{generationId}/{ReleaseShelfGenerationStore.CanonicalManifestFileName}",
                        ["sha256"] = metadata.CanonicalSha256
                    },
                    ["compatibility"] = new Dictionary<string, object?>
                    {
                        ["path"] = $"/downloads/g/{generationId}/{ReleaseShelfGenerationStore.CompatibilityManifestFileName}",
                        ["sha256"] = metadata.CompatibilitySha256
                    }
                },
                ["inventoryDigest"] = $"sha256:{metadata.InventoryDigest}",
                ["activatedAt"] = PublishedAt,
                ["activationReceiptId"] = $"activation-{generationId}"
            };

        private static string Sha256(string path)
        {
            using FileStream stream = File.OpenRead(path);
            return Convert.ToHexStringLower(SHA256.HashData(stream));
        }

        private static void WriteAuthorityFile(
            string generationRoot,
            string relativePath,
            ReadOnlyMemory<byte> bytes)
        {
            string path = Path.Combine(
                generationRoot,
                relativePath.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllBytes(path, bytes.ToArray());
        }

        private static void WriteCommittedActivationJournal(
            string downloadsRoot,
            byte[] targetPointerBytes,
            byte[]? previousPointerBytes)
        {
            using JsonDocument targetDocument = JsonDocument.Parse(targetPointerBytes);
            JsonElement target = targetDocument.RootElement;
            string receiptId = target.GetProperty("activationReceiptId").GetString()!;
            string generationId = target.GetProperty("generationId").GetString()!;
            string? previousGenerationId = null;
            if (previousPointerBytes is not null)
            {
                using JsonDocument previousDocument = JsonDocument.Parse(previousPointerBytes);
                previousGenerationId = previousDocument.RootElement
                    .GetProperty("generationId")
                    .GetString();
            }

            DateTimeOffset publishedAt = DateTimeOffset.Parse(
                    target.GetProperty("publishedAt").GetString()!)
                .ToUniversalTime();
            DateTimeOffset activatedAt = DateTimeOffset.Parse(
                    target.GetProperty("activatedAt").GetString()!)
                .ToUniversalTime();
            string ShaBinding(byte[] bytes)
                => $"sha256:{Convert.ToHexStringLower(SHA256.HashData(bytes))}";
            var intent = new TestActivationIntent(
                Operation: "promotion",
                PreviousGenerationId: previousGenerationId,
                PreviousPointerSha256: previousPointerBytes is null
                    ? null
                    : ShaBinding(previousPointerBytes),
                GenerationId: generationId,
                ActivationReceiptId: receiptId,
                ReleaseVersion: target.GetProperty("releaseVersion").GetString()!,
                Channel: target.GetProperty("channel").GetString()!,
                PublishedAt: publishedAt,
                InventoryDigest: target.GetProperty("inventoryDigest").GetString()!,
                PointerSha256: ShaBinding(targetPointerBytes),
                PreparedAtUtc: activatedAt,
                PreviousPointerBase64: previousPointerBytes is null
                    ? null
                    : Convert.ToBase64String(previousPointerBytes),
                TargetPointerBase64: Convert.ToBase64String(targetPointerBytes));
            var journal = new TestActivationJournal(
                SchemaVersion: "chummer.release-shelf.activation-intent/v1",
                State: "prepared",
                Intent: intent,
                PreviousPointerBase64: previousPointerBytes is null
                    ? null
                    : Convert.ToBase64String(previousPointerBytes),
                TargetPointerBase64: Convert.ToBase64String(targetPointerBytes));
            var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
            {
                PropertyNameCaseInsensitive = true,
                WriteIndented = true
            };
            string receiptRoot = Path.Combine(
                downloadsRoot,
                ".release-shelf-activation-journal",
                receiptId);
            Directory.CreateDirectory(receiptRoot);
            byte[] intentBytes = JsonSerializer.SerializeToUtf8Bytes(journal, options);
            File.WriteAllBytes(Path.Combine(receiptRoot, "intent.json"), intentBytes);
            var outcome = new TestActivationOutcome(
                SchemaVersion: "chummer.release-shelf.activation-outcome/v1",
                State: "committed",
                ActivationReceiptId: receiptId,
                IntentSha256: ShaBinding(intentBytes),
                ResolvedAtUtc: activatedAt);
            File.WriteAllBytes(
                Path.Combine(receiptRoot, "outcome.json"),
                JsonSerializer.SerializeToUtf8Bytes(outcome, options));
        }

        private sealed record TestActivationJournal(
            string SchemaVersion,
            string State,
            TestActivationIntent Intent,
            string? PreviousPointerBase64,
            string TargetPointerBase64);

        private sealed record TestActivationIntent(
            string Operation,
            string? PreviousGenerationId,
            string? PreviousPointerSha256,
            string GenerationId,
            string ActivationReceiptId,
            string ReleaseVersion,
            string Channel,
            DateTimeOffset PublishedAt,
            string InventoryDigest,
            string PointerSha256,
            DateTimeOffset PreparedAtUtc,
            string? PreviousPointerBase64,
            string? TargetPointerBase64);

        private sealed record TestActivationOutcome(
            string SchemaVersion,
            string State,
            string ActivationReceiptId,
            string IntentSha256,
            DateTimeOffset ResolvedAtUtc);

        private sealed class FixedReleaseTruthProjection(
            PublicReleaseTruthProjectionDto projection,
            string authoritySnapshotSha256)
            : IReleaseTruthProjection
        {
            public PublicReleaseTruthCapture CaptureWithAuthority()
                => new(projection, authoritySnapshotSha256);

            public PublicReleaseTruthCapture CaptureGenerationWithAuthority(
                string generationId)
                => new(projection, authoritySnapshotSha256);

            public PublicReleaseTruthProjectionDto Capture() => projection;

            public PublicReleaseTruthProjectionDto CaptureGeneration(
                string generationId)
                => projection;

            public PublicReleaseTruthProjectionDto Project(
                PublicReleaseManifestDto manifest,
                string? immutableManifestSha256,
                ReadOnlyMemory<byte>? immutableAuthorityManifestBytes)
                => projection;
        }

        private sealed class UnavailableCompanionReadinessProbe
            : IInstallLinkingStoreReadinessProbe
        {
            public InstallLinkingStoreReadiness Evaluate()
                => new(false, "store_unready");
        }

        private sealed record GenerationMetadata(
            string Version,
            string CanonicalSha256,
            string CompatibilitySha256,
            string InventoryDigest);
    }
}
