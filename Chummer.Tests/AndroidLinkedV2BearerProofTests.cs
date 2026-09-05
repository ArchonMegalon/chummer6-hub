using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class AndroidLinkedV2BearerProofTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("Basic token-android-v2")]
    [InlineData("Bearer")]
    [InlineData("Bearer token-android-v2 extra")]
    public async Task V2_rejects_absent_or_malformed_bearer(string? authorization)
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");
        DefaultHttpContext context = signed.CreateContext();
        if (authorization is null)
        {
            context.Request.Headers.Remove("Authorization");
        }
        else
        {
            context.Request.Headers["Authorization"] = authorization;
        }
        bool dispatched = false;

        await fixture.InvokeAsync(context, _ => dispatched = true);

        Assert.False(dispatched);
        Assert.Equal(StatusCodes.Status401Unauthorized, context.Response.StatusCode);
        Assert.DoesNotContain(Fixture.AccessToken, await ReadResponseAsync(context), StringComparison.Ordinal);
    }

    [Fact]
    public async Task V2_rejects_access_token_anywhere_in_body_and_redacts_logs_and_response()
    {
        using Fixture fixture = new();
        const string leakedSecret = "body-secret-that-must-never-be-logged";
        SignedRequest signed = fixture.Sign(
            "/api/v2/android/linked/groups",
            $"{{\"installationId\":\"android-v2\",\"nested\":{{\"accessToken\":\"{leakedSecret}\"}}}}");
        DefaultHttpContext context = signed.CreateContext();
        bool dispatched = false;

        await fixture.InvokeAsync(context, _ => dispatched = true);

        Assert.False(dispatched);
        Assert.Equal(StatusCodes.Status400BadRequest, context.Response.StatusCode);
        string observed = string.Join('\n', fixture.Logger.Messages.Append(await ReadResponseAsync(context)));
        Assert.DoesNotContain(leakedSecret, observed, StringComparison.Ordinal);
        Assert.DoesNotContain(Fixture.AccessToken, observed, StringComparison.Ordinal);
        Assert.DoesNotContain(signed.Signature, observed, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("{\"installationId\":\"android-v2\",\"installationId\":\"android-v2\"}")]
    [InlineData("{\"InstallationId\":\"android-v2\"}")]
    [InlineData("{\"installationId\":\"android-v2\",\"INSTALLATIONID\":\"android-v2\"}")]
    public async Task V2_rejects_duplicate_or_case_variant_installation_identity(string body)
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign("/api/v2/android/linked/groups", body);
        DefaultHttpContext context = signed.CreateContext();
        bool dispatched = false;

        await fixture.InvokeAsync(context, _ => dispatched = true);

        Assert.False(dispatched);
        Assert.Equal(StatusCodes.Status400BadRequest, context.Response.StatusCode);
    }

    [Fact]
    public async Task V2_proof_rejects_endpoint_and_grant_substitution_and_replay_after_store_restart()
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");
        int dispatches = 0;

        DefaultHttpContext accepted = signed.CreateContext();
        await fixture.InvokeAsync(accepted, _ => dispatches++);
        Assert.Equal(StatusCodes.Status204NoContent, accepted.Response.StatusCode);

        fixture.Reload();
        DefaultHttpContext replay = signed.CreateContext();
        await fixture.InvokeAsync(replay, _ => dispatches++);
        Assert.Equal(StatusCodes.Status409Conflict, replay.Response.StatusCode);

        DefaultHttpContext endpointSubstitution = signed.CreateContext();
        endpointSubstitution.Request.Path = "/api/v2/android/linked/groups/create";
        await fixture.InvokeAsync(endpointSubstitution, _ => dispatches++);
        Assert.Equal(StatusCodes.Status401Unauthorized, endpointSubstitution.Response.StatusCode);

        SignedRequest fresh = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");
        DefaultHttpContext grantSubstitution = fresh.CreateContext();
        grantSubstitution.Request.Headers[AndroidLinkedV2RequestProof.GrantHeader] = "grant-another-install";
        await fixture.InvokeAsync(grantSubstitution, _ => dispatches++);
        Assert.Equal(StatusCodes.Status401Unauthorized, grantSubstitution.Response.StatusCode);

        Assert.Equal(1, dispatches);
    }

    [Fact]
    public async Task V2_proof_binds_exact_body_and_rejects_query_substitution()
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");

        DefaultHttpContext bodySubstitution = signed.CreateContext();
        bodySubstitution.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(
            "{\"installationId\":\"android-v2\",\"extra\":true}"));
        await fixture.InvokeAsync(bodySubstitution, _ => throw new InvalidOperationException("dispatch must not occur"));
        Assert.Equal(StatusCodes.Status401Unauthorized, bodySubstitution.Response.StatusCode);

        SignedRequest fresh = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");
        DefaultHttpContext querySubstitution = fresh.CreateContext();
        querySubstitution.Request.QueryString = new QueryString("?grant=another");
        await fixture.InvokeAsync(querySubstitution, _ => throw new InvalidOperationException("dispatch must not occur"));
        Assert.Equal(StatusCodes.Status400BadRequest, querySubstitution.Response.StatusCode);
    }

    [Fact]
    public async Task V1_is_bypassed_but_v1_proof_cannot_authorize_v2()
    {
        using Fixture fixture = new();
        DefaultHttpContext legacy = new();
        legacy.Request.Method = HttpMethods.Post;
        legacy.Request.Path = "/api/v1/android/linked/groups";
        legacy.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(
            $"{{\"installationId\":\"android-v2\",\"accessToken\":\"{Fixture.AccessToken}\"}}"));
        legacy.Response.Body = new MemoryStream();
        bool legacyDispatched = false;

        await fixture.InvokeAsync(legacy, _ => legacyDispatched = true);

        Assert.True(legacyDispatched);
        Assert.Equal(StatusCodes.Status204NoContent, legacy.Response.StatusCode);

        SignedRequest v2 = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");
        DefaultHttpContext confused = v2.CreateContext();
        confused.Request.Headers[AndroidLinkedV2RequestProof.SchemeHeader] = "chummer.android.packet.v1";
        bool v2Dispatched = false;

        await fixture.InvokeAsync(confused, _ => v2Dispatched = true);

        Assert.False(v2Dispatched);
        Assert.Equal(StatusCodes.Status401Unauthorized, confused.Response.StatusCode);
    }

    [Fact]
    public async Task Refresh_rotates_bearer_in_authorization_header_without_serializing_it()
    {
        using Fixture fixture = new();
        const string body = "{\"installationId\":\"android-v2\",\"headId\":\"android\",\"applicationVersion\":\"0.1.0-preview.11\",\"channelId\":\"internal\",\"platform\":\"android\",\"architecture\":\"arm64\"}";
        SignedRequest signed = fixture.Sign("/api/v2/install-linking/grants/refresh", body);
        DefaultHttpContext context = signed.CreateContext();
        AndroidLinkedV2GrantRefreshResponse? response = null;

        await fixture.InvokeAsync(context, httpContext =>
        {
            var controller = new InstallLinkingV2Controller(
                fixture.Service,
                fixture.WorkspaceSnapshots,
                fixture.TimeProvider)
            {
                ControllerContext = new ControllerContext { HttpContext = httpContext }
            };
            ActionResult<AndroidLinkedV2GrantRefreshResponse> action = controller.RefreshGrant(
                new AndroidLinkedV2GrantRefreshRequest(
                    "android-v2",
                    "android",
                    "0.1.0-preview.11",
                    "internal",
                    "android",
                    "arm64",
                    OperationId: Fixture.OperationId));
            response = Assert.IsType<AndroidLinkedV2GrantRefreshResponse>(
                Assert.IsType<OkObjectResult>(action.Result).Value);
        });

        string rotatedAuthorization = context.Response.Headers["Authorization"].ToString();
        Assert.StartsWith("Bearer ", rotatedAuthorization, StringComparison.Ordinal);
        string rotatedToken = rotatedAuthorization["Bearer ".Length..];
        Assert.NotEqual(Fixture.AccessToken, rotatedToken);
        Assert.Equal(response!.Grant.GrantId, context.Response.Headers[AndroidLinkedV2RequestProof.GrantHeader]);
        string responseJson = JsonSerializer.Serialize(response, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        Assert.DoesNotContain(Fixture.AccessToken, responseJson, StringComparison.Ordinal);
        Assert.DoesNotContain(rotatedToken, responseJson, StringComparison.Ordinal);
        Assert.DoesNotContain("accessToken", responseJson, StringComparison.OrdinalIgnoreCase);
        Assert.Null(fixture.Service.ResolveAndroidLinkedV2Grant("android-v2", Fixture.GrantId, Fixture.AccessToken));
        Assert.Null(fixture.Service.ResolveInstallationForGrant("android-v2", Fixture.AccessToken));
        Assert.NotNull(fixture.Service.ResolveAndroidLinkedV2Grant("android-v2", response.Grant.GrantId, rotatedToken));
    }

    [Fact]
    public async Task Refresh_revokes_old_bearer_for_legacy_v1_resolver()
    {
        using Fixture fixture = new();
        const string body = "{\"installationId\":\"android-v2\"}";
        SignedRequest signed = fixture.Sign("/api/v2/install-linking/grants/refresh", body);
        DefaultHttpContext context = signed.CreateContext();

        await fixture.InvokeAsync(context, httpContext =>
        {
            var controller = new InstallLinkingV2Controller(
                fixture.Service,
                fixture.WorkspaceSnapshots,
                fixture.TimeProvider)
            {
                ControllerContext = new ControllerContext { HttpContext = httpContext }
            };
            Assert.IsType<OkObjectResult>(controller.RefreshGrant(
                new AndroidLinkedV2GrantRefreshRequest(
                    "android-v2",
                    OperationId: Fixture.OperationId)).Result);
        });

        Assert.Null(fixture.Service.ResolveInstallationForGrant(
            "android-v2",
            Fixture.AccessToken));
    }

    [Fact]
    public async Task Device_v2_unlink_still_requires_and_accepts_signed_grant_proof()
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign(
            "/api/v2/install-linking/grants/revoke",
            "{\"installationId\":\"android-v2\"}");
        AndroidLinkedV2GrantRevokeResponse? response = null;

        await fixture.InvokeAsync(signed.CreateContext(), httpContext =>
        {
            var controller = new InstallLinkingV2Controller(
                fixture.Service,
                fixture.WorkspaceSnapshots,
                fixture.TimeProvider)
            {
                ControllerContext = new ControllerContext { HttpContext = httpContext }
            };
            ActionResult<AndroidLinkedV2GrantRevokeResponse> action = controller.RevokeGrant(
                new AndroidLinkedV2GrantRequest("android-v2"));
            response = Assert.IsType<AndroidLinkedV2GrantRevokeResponse>(
                Assert.IsType<OkObjectResult>(action.Result).Value);
        });

        Assert.Equal(ClaimedInstallationStates.Revoked, response!.Installation.Status);
        Assert.Contains(response.Grants, item => item.GrantId == Fixture.GrantId);
        Assert.Null(fixture.Service.ResolveAndroidLinkedV2Grant(
            "android-v2",
            Fixture.GrantId,
            Fixture.AccessToken));
    }

    [Fact]
    public async Task Refresh_response_loss_fresh_proof_recovers_exact_replacement_after_restart()
    {
        using Fixture fixture = new();
        const string body = "{\"installationId\":\"android-v2\",\"applicationVersion\":\"0.1.0-preview.12\"}";
        SignedRequest signed = fixture.Sign("/api/v2/install-linking/grants/refresh", body);

        (DefaultHttpContext firstContext, AndroidLinkedV2GrantRefreshResponse first) =
            await InvokeRefreshAsync(fixture, signed);
        string firstAuthorization = firstContext.Response.Headers.Authorization.ToString();
        fixture.Reload();
        SignedRequest freshRetry = fixture.Sign(
            signed.Path,
            Encoding.UTF8.GetString(signed.Body),
            issuedAtUnixSeconds: signed.IssuedAtUnixSeconds + 1);

        (DefaultHttpContext retryContext, AndroidLinkedV2GrantRefreshResponse retry) =
            await InvokeRefreshAsync(fixture, freshRetry);

        Assert.Equal(first, retry);
        Assert.Equal(firstAuthorization, retryContext.Response.Headers.Authorization.ToString());
        Assert.Equal(first.Grant.GrantId, retryContext.Response.Headers[AndroidLinkedV2RequestProof.GrantHeader]);
        Assert.Equal(Fixture.OperationId, retry.OperationId);
        Assert.Equal(InstallLinkingService.AndroidLinkedV2GrantTransport, retry.GrantTransport);
        Assert.Equal(2, fixture.Store.GrantsById.Values.Count(item => item.InstallationId == "android-v2"));
        Assert.Single(fixture.Store.GrantsById.Values, item =>
            item.InstallationId == "android-v2"
            && item.Status == InstallationGrantStates.Active);
        string replacementToken = retryContext.Response.Headers.Authorization.ToString()["Bearer ".Length..];
        Assert.Null(fixture.Service.ResolveInstallationForGrant("android-v2", replacementToken));
        Assert.NotNull(fixture.Service.ResolveAndroidLinkedV2Grant(
            "android-v2",
            retry.Grant.GrantId,
            replacementToken));
    }

    [Fact]
    public async Task Refresh_response_loss_rejects_reused_proof_envelope_without_minting_again()
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign(
            "/api/v2/install-linking/grants/refresh",
            "{\"installationId\":\"android-v2\"}");
        await InvokeRefreshAsync(fixture, signed);

        DefaultHttpContext replay = signed.CreateContext();
        bool dispatched = false;
        await fixture.InvokeAsync(replay, _ => dispatched = true);

        Assert.False(dispatched);
        Assert.Equal(StatusCodes.Status409Conflict, replay.Response.StatusCode);
        Assert.Equal(2, fixture.Store.GrantsById.Values.Count(item => item.InstallationId == "android-v2"));
    }

    [Fact]
    public async Task Refresh_response_loss_at_full_grant_capacity_pins_source_and_replacement()
    {
        using Fixture fixture = new();
        lock (fixture.Store.Gate)
        {
            DateTimeOffset now = fixture.TimeProvider.GetUtcNow();
            for (int index = 0; index < InstallLinkingStore.MaxGrants - 1; index++)
            {
                string grantId = $"capacity-grant-{index:D4}";
                fixture.Store.GrantsById[grantId] = new InstallationGrantDto(
                    grantId,
                    "capacity-install",
                    InstallationGrantStates.Revoked,
                    $"capacity-token-{index:D4}",
                    now.AddSeconds(index),
                    now.AddDays(20),
                    "capacity-user",
                    "capacity-subject");
                fixture.Store.GrantTransportAuthoritiesByGrantId[grantId] =
                    new InstallationGrantTransportAuthority(
                        grantId,
                        InstallationGrantTransports.AndroidLinkedV2);
            }
            fixture.Store.PersistLocked();
        }

        SignedRequest signed = fixture.Sign(
            "/api/v2/install-linking/grants/refresh",
            "{\"installationId\":\"android-v2\"}");
        (DefaultHttpContext firstContext, AndroidLinkedV2GrantRefreshResponse first) =
            await InvokeRefreshAsync(fixture, signed);
        string firstAuthorization = firstContext.Response.Headers.Authorization.ToString();
        fixture.Reload();

        Assert.Equal(InstallLinkingStore.MaxGrants, fixture.Store.GrantsById.Count);
        Assert.True(fixture.Store.GrantsById.ContainsKey(Fixture.GrantId));
        Assert.True(fixture.Store.GrantsById.ContainsKey(first.Grant.GrantId));
        Assert.True(fixture.Store.AndroidLinkedV2RefreshReceiptsBySourceGrantId.ContainsKey(Fixture.GrantId));

        SignedRequest fresh = fixture.Sign(signed.Path, Encoding.UTF8.GetString(signed.Body));
        (DefaultHttpContext retryContext, AndroidLinkedV2GrantRefreshResponse retry) =
            await InvokeRefreshAsync(fixture, fresh);

        Assert.Equal(first, retry);
        Assert.Equal(firstAuthorization, retryContext.Response.Headers.Authorization.ToString());
        Assert.Equal(InstallLinkingStore.MaxGrants, fixture.Store.GrantsById.Count);
    }

    [Theory]
    [InlineData("body")]
    [InlineData("key")]
    [InlineData("bearer")]
    [InlineData("replacement-bearer")]
    [InlineData("operation")]
    [InlineData("installation")]
    [InlineData("owner")]
    public async Task Refresh_response_loss_rejects_changed_authority_or_request(string hostileChange)
    {
        using Fixture fixture = new();
        const string body = "{\"installationId\":\"android-v2\",\"hostLabel\":\"Pixel\"}";
        SignedRequest signed = fixture.Sign("/api/v2/install-linking/grants/refresh", body);
        (DefaultHttpContext firstContext, _) = await InvokeRefreshAsync(fixture, signed);

        SignedRequest fresh = fixture.Sign(signed.Path, Encoding.UTF8.GetString(signed.Body));
        DefaultHttpContext retry;
        if (hostileChange == "body")
        {
            fresh = fixture.Sign(
                signed.Path,
                "{\"installationId\":\"android-v2\",\"hostLabel\":\"Other\"}");
            retry = fresh.CreateContext();
        }
        else if (hostileChange == "key")
        {
            using RSA otherKey = RSA.Create(2048);
            fresh = fixture.SignWithKey(
                otherKey,
                signed.Path,
                Encoding.UTF8.GetString(signed.Body));
            retry = fresh.CreateContext();
        }
        else if (hostileChange == "bearer")
        {
            retry = fresh.CreateContext();
            retry.Request.Headers.Authorization = "Bearer changed-source-token";
        }
        else if (hostileChange == "replacement-bearer")
        {
            retry = fresh.CreateContext(firstContext.Response.Headers.Authorization.ToString());
        }
        else if (hostileChange == "operation")
        {
            const string changedOperationId = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB";
            string changedBody = Encoding.UTF8.GetString(signed.Body)
                .Replace(Fixture.OperationId, changedOperationId, StringComparison.Ordinal);
            fresh = fixture.Sign(signed.Path, changedBody, changedOperationId);
            retry = fresh.CreateContext();
        }
        else if (hostileChange == "installation")
        {
            retry = fresh.CreateContext();
            retry.Request.Headers[AndroidLinkedV2RequestProof.InstallationHeader] = "other-installation";
        }
        else
        {
            retry = fresh.CreateContext();
            lock (fixture.Store.Gate)
            {
                ClaimedInstallationDto installation = fixture.Store.InstallationsById["android-v2"];
                fixture.Store.InstallationsById["android-v2"] = installation with { UserId = "other-owner" };
            }
        }

        bool dispatched = false;
        await fixture.InvokeAsync(retry, _ => dispatched = true);

        Assert.False(dispatched);
        Assert.Equal(StatusCodes.Status401Unauthorized, retry.Response.StatusCode);
        Assert.Equal(2, fixture.Store.GrantsById.Values.Count(item => item.InstallationId == "android-v2"));
    }

    [Fact]
    public async Task Refresh_response_loss_rejects_case_mutated_source_grant_identity()
    {
        using Fixture fixture = new();
        const string body = "{\"installationId\":\"android-v2\"}";
        SignedRequest signed = fixture.Sign("/api/v2/install-linking/grants/refresh", body);
        await InvokeRefreshAsync(fixture, signed);
        SignedRequest caseMutated = fixture.SignForGrantId(
            signed.Path,
            Encoding.UTF8.GetString(signed.Body),
            Fixture.GrantId.ToUpperInvariant());
        DefaultHttpContext retry = caseMutated.CreateContext();
        bool dispatched = false;

        await fixture.InvokeAsync(retry, _ => dispatched = true);

        Assert.False(dispatched);
        Assert.Equal(StatusCodes.Status401Unauthorized, retry.Response.StatusCode);
        Assert.Equal(2, fixture.Store.GrantsById.Values.Count(item => item.InstallationId == "android-v2"));
    }

    [Fact]
    public async Task Refresh_response_loss_rejects_expired_operation_receipt()
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign(
            "/api/v2/install-linking/grants/refresh",
            "{\"installationId\":\"android-v2\"}");
        await InvokeRefreshAsync(fixture, signed);
        lock (fixture.Store.Gate)
        {
            AndroidLinkedV2GrantRefreshReceipt receipt =
                fixture.Store.AndroidLinkedV2RefreshReceiptsBySourceGrantId[Fixture.GrantId];
            fixture.Store.AndroidLinkedV2RefreshReceiptsBySourceGrantId[Fixture.GrantId] = receipt with
            {
                RetryExpiresAtUtc = fixture.TimeProvider.GetUtcNow().AddSeconds(-1)
            };
        }

        SignedRequest fresh = fixture.Sign(signed.Path, Encoding.UTF8.GetString(signed.Body));
        DefaultHttpContext retry = fresh.CreateContext();
        bool dispatched = false;
        await fixture.InvokeAsync(retry, _ => dispatched = true);

        Assert.False(dispatched);
        Assert.Equal(StatusCodes.Status401Unauthorized, retry.Response.StatusCode);
        Assert.Equal(2, fixture.Store.GrantsById.Values.Count(item => item.InstallationId == "android-v2"));
    }

    [Theory]
    [InlineData(InstallationGrantStates.Expired)]
    [InlineData(InstallationGrantStates.Revoked)]
    public async Task Refresh_response_loss_rejects_non_active_replacement(string replacementStatus)
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign(
            "/api/v2/install-linking/grants/refresh",
            "{\"installationId\":\"android-v2\"}");
        (_, AndroidLinkedV2GrantRefreshResponse first) = await InvokeRefreshAsync(fixture, signed);
        lock (fixture.Store.Gate)
        {
            InstallationGrantDto grant = fixture.Store.GrantsById[first.Grant.GrantId];
            fixture.Store.GrantsById[first.Grant.GrantId] = grant with
            {
                Status = replacementStatus,
                ExpiresAtUtc = replacementStatus == InstallationGrantStates.Expired
                    ? DateTimeOffset.UtcNow.AddMinutes(-1)
                    : grant.ExpiresAtUtc
            };
        }

        SignedRequest fresh = fixture.Sign(signed.Path, Encoding.UTF8.GetString(signed.Body));
        DefaultHttpContext retry = fresh.CreateContext();
        bool dispatched = false;
        await fixture.InvokeAsync(retry, _ => dispatched = true);

        Assert.False(dispatched);
        Assert.Equal(StatusCodes.Status401Unauthorized, retry.Response.StatusCode);
        Assert.Equal(2, fixture.Store.GrantsById.Values.Count(item => item.InstallationId == "android-v2"));
    }

    [Fact]
    public void Grant_transport_authority_blocks_cross_route_downgrade_and_preserves_legacy_grants()
    {
        using Fixture fixture = new();

        Assert.Null(fixture.Service.ResolveInstallationForGrant("android-v2", Fixture.AccessToken));
        InstallLinkingOperationException downgrade = Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.RefreshGrant(new RefreshInstallationGrantRequestDto(
                "android-v2",
                Fixture.AccessToken)));
        Assert.Equal(StatusCodes.Status401Unauthorized, downgrade.StatusCode);

        InstallationGrantDto legacy = fixture.SeedLegacyGrant("preview10-install");
        Assert.NotNull(fixture.Service.ResolveInstallationForGrant(
            legacy.InstallationId,
            legacy.AccessToken));
        Assert.Null(fixture.Service.ResolveAndroidLinkedV2Grant(
            legacy.InstallationId,
            legacy.GrantId,
            legacy.AccessToken));
    }

    [Fact]
    public void V2_request_DTOs_have_no_access_token_member()
    {
        Type[] requestTypes =
        [
            typeof(AndroidLinkedV2GrantRequest),
            typeof(AndroidLinkedV2GroupCreateRequest),
            typeof(AndroidLinkedV2GroupUpdateRequest),
            typeof(AndroidLinkedV2ChronicleDraftRequest),
            typeof(AndroidLinkedV2ChronicleActionRequest),
            typeof(AndroidLinkedV2AccountErasureRequest),
            typeof(AndroidLinkedV2GrantRefreshRequest),
            typeof(AndroidLinkedV2WorkspaceSnapshotUpsertRequest)
        ];

        Assert.All(requestTypes, static type => Assert.DoesNotContain(
            type.GetProperties(),
            static property => property.Name.Contains("AccessToken", StringComparison.OrdinalIgnoreCase)));
    }

    [Fact]
    public void Canonical_payload_is_version_endpoint_grant_and_body_bound_without_a_secret()
    {
        byte[] body = Encoding.UTF8.GetBytes("{\"installationId\":\"android-v2\"}");
        string packetKey = ToBase64Url(Enumerable.Repeat((byte)0x5a, 32).ToArray());
        byte[] canonical = AndroidLinkedV2RequestProof.CreateCanonicalPayload(
            "post",
            "/api/v2/android/linked/groups/Group-A/chronicles",
            "android-v2",
            "grant-android-v2",
            1_788_544_000,
            packetKey,
            body);
        string expectedBodyDigest = Convert.ToHexString(SHA256.HashData(body)).ToLowerInvariant();

        Assert.Equal(
            string.Join('\n',
                "chummer.android.packet.v2",
                "POST",
                "/api/v2/android/linked/groups/Group-A/chronicles",
                "android-v2",
                "grant-android-v2",
                "1788544000",
                packetKey,
                $"sha256:{expectedBodyDigest}"),
            Encoding.UTF8.GetString(canonical));
        Assert.DoesNotContain("grant-secret", Encoding.UTF8.GetString(canonical), StringComparison.Ordinal);
    }

    [Fact]
    public void V2_bootstrap_returns_secret_only_in_response_headers()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-v2",
            useLegacyCanonical: false);
        DefaultHttpContext context = CreateControllerContext(AndroidInstallLinkV2BootstrapProof.Path);
        var controller = new InstallLinkingV2Controller(
            fixture.Service,
            fixture.WorkspaceSnapshots,
            fixture.TimeProvider)
        {
            ControllerContext = new ControllerContext { HttpContext = context }
        };

        ActionResult<AndroidInstallLinkV2ExchangeResponse> action = controller.PollBrowserCallback(request);

        AndroidInstallLinkV2ExchangeResponse response = Assert.IsType<AndroidInstallLinkV2ExchangeResponse>(
            Assert.IsType<OkObjectResult>(action.Result).Value);
        Assert.Single(context.Response.Headers.Authorization);
        string authorization = context.Response.Headers.Authorization.ToString();
        Assert.StartsWith("Bearer ", authorization, StringComparison.Ordinal);
        string issuedToken = authorization["Bearer ".Length..];
        Assert.NotEmpty(issuedToken);
        Assert.Equal(response.Grant.GrantId, Assert.Single(context.Response.Headers[AndroidLinkedV2RequestProof.GrantHeader]));
        string json = JsonSerializer.Serialize(response, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        Assert.DoesNotContain(issuedToken, json, StringComparison.Ordinal);
        Assert.DoesNotContain("accessToken", json, StringComparison.OrdinalIgnoreCase);
        Assert.NotNull(fixture.Service.ResolveAndroidLinkedV2Grant(
            response.Installation.InstallationId,
            response.Grant.GrantId,
            issuedToken));
        Assert.Equal(Fixture.OperationId, response.OperationId);
        Assert.Equal(InstallLinkingService.AndroidLinkedV2GrantTransport, response.GrantTransport);
    }

    [Fact]
    public void V2_bootstrap_response_loss_fresh_proof_recovers_original_grant_after_restart()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-retry",
            useLegacyCanonical: false);

        (DefaultHttpContext firstContext, AndroidInstallLinkV2ExchangeResponse first) =
            PollBootstrap(fixture, request);
        string firstAuthorization = firstContext.Response.Headers.Authorization.ToString();
        fixture.Reload();
        InstallLinkingService sharedService = fixture.CreateSharedService();
        AndroidInstallLinkProofPollV2Request freshRetry = fixture.SignBootstrap(request with
        {
            IssuedAtUnixSeconds = request.IssuedAtUnixSeconds + 1,
            Nonce = ToBase64Url(RandomNumberGenerator.GetBytes(24)),
            Signature = string.Empty
        });

        (DefaultHttpContext retryContext, AndroidInstallLinkV2ExchangeResponse retry) =
            PollBootstrap(fixture, freshRetry, sharedService);

        Assert.False(first.AlreadyClaimed);
        Assert.True(retry.AlreadyClaimed);
        Assert.Equal(first.Installation, retry.Installation);
        Assert.Equal(first.Grant, retry.Grant);
        Assert.Equal(first.OperationId, retry.OperationId);
        Assert.Equal(firstAuthorization, retryContext.Response.Headers.Authorization.ToString());
        Assert.Equal(first.Grant.GrantId, retryContext.Response.Headers[AndroidLinkedV2RequestProof.GrantHeader]);
        Assert.Single(fixture.Store.GrantsById.Values, item =>
            item.InstallationId == request.InstallationId);
    }

    [Fact]
    public void V2_bootstrap_recovery_grant_is_pinned_against_newer_grant_eviction()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-eviction-window",
            useLegacyCanonical: false);
        (DefaultHttpContext firstContext, AndroidInstallLinkV2ExchangeResponse first) =
            PollBootstrap(fixture, request);
        string firstAuthorization = firstContext.Response.Headers.Authorization.ToString();

        lock (fixture.Store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            for (int index = 0; index < InstallLinkingStore.MaxGrants; index++)
            {
                string grantId = $"newer-grant-{index:D4}";
                fixture.Store.GrantsById[grantId] = new InstallationGrantDto(
                    grantId,
                    "newer-install",
                    InstallationGrantStates.Revoked,
                    string.Empty,
                    now.AddSeconds(index + 1),
                    now.AddDays(30),
                    "newer-user",
                    "newer-subject");
                fixture.Store.GrantTransportAuthoritiesByGrantId[grantId] =
                    new InstallationGrantTransportAuthority(
                        grantId,
                        InstallationGrantTransports.AndroidLinkedV2);
            }
            fixture.Store.PersistLocked();
        }

        fixture.Reload();
        Assert.Equal(InstallLinkingStore.MaxGrants, fixture.Store.GrantsById.Count);
        Assert.Contains(first.Grant.GrantId, fixture.Store.GrantsById.Keys);
        Assert.Contains(
            fixture.Store.BrowserCallbackRedemptionReceiptsByCallbackId.Values,
            item => item.GrantId == first.Grant.GrantId);
        AndroidInstallLinkProofPollV2Request freshRetry = fixture.SignBootstrap(request with
        {
            IssuedAtUnixSeconds = request.IssuedAtUnixSeconds + 1,
            Nonce = ToBase64Url(RandomNumberGenerator.GetBytes(24)),
            Signature = string.Empty
        });

        (DefaultHttpContext retryContext, AndroidInstallLinkV2ExchangeResponse retry) =
            PollBootstrap(fixture, freshRetry);

        Assert.Equal(first.Grant, retry.Grant);
        Assert.Equal(firstAuthorization, retryContext.Response.Headers.Authorization.ToString());
        Assert.Equal(InstallLinkingStore.MaxGrants, fixture.Store.GrantsById.Count);
    }

    [Fact]
    public void V2_bootstrap_full_recovery_capacity_fails_before_consuming_callback_across_restart()
    {
        using Fixture fixture = new();
        fixture.SeedFullyPinnedGrantCapacity();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-capacity",
            useLegacyCanonical: false);

        ObjectResult firstDenied = Assert.IsType<ObjectResult>(
            PollBootstrapAction(fixture, request).Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, firstDenied.StatusCode);
        InstallBrowserCallbackDto callback = Assert.Single(
            fixture.Store.BrowserCallbacksById.Values,
            item => item.InstallationId == request.InstallationId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
        Assert.Null(callback.GrantId);
        Assert.DoesNotContain(
            fixture.Store.GrantsById.Values,
            item => item.InstallationId == request.InstallationId);

        fixture.Reload();
        AndroidInstallLinkProofPollV2Request freshRetry = fixture.SignBootstrap(request with
        {
            IssuedAtUnixSeconds = request.IssuedAtUnixSeconds + 1,
            Nonce = ToBase64Url(RandomNumberGenerator.GetBytes(24)),
            Signature = string.Empty
        });
        ObjectResult retryDenied = Assert.IsType<ObjectResult>(
            PollBootstrapAction(fixture, freshRetry).Result);

        Assert.Equal(StatusCodes.Status503ServiceUnavailable, retryDenied.StatusCode);
        callback = Assert.Single(
            fixture.Store.BrowserCallbacksById.Values,
            item => item.InstallationId == request.InstallationId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
        Assert.Null(callback.GrantId);
        Assert.Equal(InstallLinkingStore.MaxGrants, fixture.Store.GrantsById.Count);
    }

    [Fact]
    public void V2_bootstrap_retry_rejects_reused_proof_envelope()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-replay",
            useLegacyCanonical: false);
        PollBootstrap(fixture, request);

        ObjectResult denied = Assert.IsType<ObjectResult>(PollBootstrapAction(fixture, request).Result);

        Assert.Equal(StatusCodes.Status409Conflict, denied.StatusCode);
        Assert.Single(fixture.Store.GrantsById.Values, item =>
            item.InstallationId == request.InstallationId);
    }

    [Fact]
    public void V2_bootstrap_retry_rejects_changed_identity_key_and_signed_body()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-hostile",
            useLegacyCanonical: false);
        PollBootstrap(fixture, request);

        AndroidInstallLinkProofPollV2Request changedBody = fixture.SignBootstrap(
            request with
            {
                HostLabel = "Different device",
                IssuedAtUnixSeconds = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
                Nonce = ToBase64Url(RandomNumberGenerator.GetBytes(24)),
                Signature = string.Empty
            });
        ObjectResult bodyDenied = Assert.IsType<ObjectResult>(
            PollBootstrapAction(fixture, changedBody).Result);
        Assert.Equal(StatusCodes.Status409Conflict, bodyDenied.StatusCode);

        const string changedOperationId = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB";
        AndroidInstallLinkProofPollV2Request changedOperation = fixture.SignBootstrap(request with
        {
            OperationId = changedOperationId,
            IssuedAtUnixSeconds = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Nonce = ToBase64Url(RandomNumberGenerator.GetBytes(24)),
            Signature = string.Empty
        });
        ObjectResult operationDenied = Assert.IsType<ObjectResult>(
            PollBootstrapAction(fixture, changedOperation).Result);
        Assert.Equal(StatusCodes.Status409Conflict, operationDenied.StatusCode);

        using RSA otherKey = RSA.Create(2048);
        AndroidInstallLinkProofPollV2Request changedKey = request with
        {
            PublicKey = Convert.ToBase64String(otherKey.ExportSubjectPublicKeyInfo())
        };
        ObjectResult keyDenied = Assert.IsType<ObjectResult>(
            PollBootstrapAction(fixture, changedKey).Result);
        Assert.Equal(StatusCodes.Status409Conflict, keyDenied.StatusCode);

        ActionResult<AndroidInstallLinkV2ExchangeResponse> identityResult = PollBootstrapAction(
            fixture,
            request with { InstallationId = "other-installation" });
        Assert.IsType<AcceptedResult>(identityResult.Result);
        Assert.Single(fixture.Store.GrantsById.Values, item =>
            item.InstallationId == request.InstallationId);
    }

    [Fact]
    public void V2_bootstrap_rejects_resigned_transport_substitution()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-transport-substitution",
            useLegacyCanonical: false);
        AndroidInstallLinkProofPollV2Request substituted = fixture.SignBootstrap(request with
        {
            InstallLinkTransport = InstallLinkingService.LegacyProofPollTransport,
            Signature = string.Empty
        });

        ObjectResult denied = Assert.IsType<ObjectResult>(
            PollBootstrapAction(fixture, substituted).Result);

        Assert.Equal(StatusCodes.Status400BadRequest, denied.StatusCode);
        Assert.DoesNotContain(
            fixture.Store.GrantsById.Values,
            item => item.InstallationId == request.InstallationId);
    }

    [Theory]
    [InlineData("owner")]
    [InlineData("grant-expired")]
    [InlineData("grant-revoked")]
    [InlineData("callback-expired")]
    [InlineData("callback-revoked")]
    public void V2_bootstrap_retry_rejects_changed_owner_or_terminal_authority(string hostileChange)
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-terminal",
            useLegacyCanonical: false);
        (_, AndroidInstallLinkV2ExchangeResponse first) = PollBootstrap(fixture, request);

        lock (fixture.Store.Gate)
        {
            InstallBrowserCallbackDto callback = Assert.Single(
                fixture.Store.BrowserCallbacksById.Values,
                item => item.InstallationId == request.InstallationId);
            InstallationGrantDto grant = fixture.Store.GrantsById[first.Grant.GrantId];
            ClaimedInstallationDto installation = fixture.Store.InstallationsById[request.InstallationId];
            if (hostileChange == "owner")
            {
                fixture.Store.InstallationsById[request.InstallationId] = installation with
                {
                    SubjectId = "other-subject"
                };
            }
            else if (hostileChange == "grant-expired")
            {
                fixture.Store.GrantsById[grant.GrantId] = grant with
                {
                    IssuedAtUtc = DateTimeOffset.UtcNow.AddMinutes(-2),
                    ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(-1)
                };
            }
            else if (hostileChange == "grant-revoked")
            {
                fixture.Store.GrantsById[grant.GrantId] = grant with { Status = InstallationGrantStates.Revoked };
            }
            else if (hostileChange == "callback-expired")
            {
                fixture.Store.BrowserCallbacksById[callback.CallbackId] = callback with
                {
                    CreatedAtUtc = DateTimeOffset.UtcNow.AddMinutes(-2),
                    ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(-1)
                };
            }
            else
            {
                fixture.Store.BrowserCallbacksById[callback.CallbackId] = callback with
                {
                    Status = InstallBrowserCallbackStates.Revoked
                };
            }
        }

        ObjectResult denied = Assert.IsType<ObjectResult>(PollBootstrapAction(fixture, request).Result);
        Assert.True(denied.StatusCode is StatusCodes.Status409Conflict or StatusCodes.Status410Gone);
        Assert.Single(fixture.Store.GrantsById.Values, item => item.InstallationId == request.InstallationId);
    }

    [Fact]
    public void V2_callback_intent_survives_restart_and_rejects_legacy_poll_before_redemption()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-v2-intent",
            useLegacyCanonical: false);
        InstallBrowserCallbackDto callback = Assert.Single(
            fixture.Store.BrowserCallbacksById.Values,
            item => item.InstallationId == request.InstallationId);

        fixture.Reload();

        Assert.Equal(
            InstallLinkingService.AndroidLinkedV2ProofPollTransport,
            fixture.Store.BrowserCallbackTransportIntentsByCallbackId[callback.CallbackId].Transport);
        InstallLinkingOperationException downgrade = Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.PollBrowserCallback(fixture.SignLegacyBootstrap(request)));
        Assert.Equal(StatusCodes.Status409Conflict, downgrade.StatusCode);
        Assert.DoesNotContain(
            fixture.Store.GrantsById.Values,
            item => item.InstallationId == request.InstallationId);

        (_, AndroidInstallLinkV2ExchangeResponse response) = PollBootstrap(fixture, request);
        Assert.Equal(
            InstallationGrantTransports.AndroidLinkedV2,
            fixture.Store.GrantTransportAuthoritiesByGrantId[response.Grant.GrantId].Transport);
    }

    [Fact]
    public void Legacy_callback_intent_rejects_v2_poll_and_still_allows_preview10_poll()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-legacy-intent",
            useLegacyCanonical: false,
            approvedTransport: InstallLinkingService.LegacyProofPollTransport);

        ObjectResult downgrade = Assert.IsType<ObjectResult>(
            PollBootstrapAction(fixture, request).Result);
        Assert.Equal(StatusCodes.Status409Conflict, downgrade.StatusCode);
        Assert.DoesNotContain(
            fixture.Store.GrantsById.Values,
            item => item.InstallationId == request.InstallationId);

        PollInstallBrowserCallbackResult legacy = fixture.Service.PollBrowserCallback(
            fixture.SignLegacyBootstrap(request));
        ExchangeInstallBrowserCallbackResponseDto exchange = Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(
            legacy.Exchange);
        Assert.Equal(
            InstallationGrantTransports.LegacyV1,
            fixture.Store.GrantTransportAuthoritiesByGrantId[exchange.Grant.GrantId].Transport);
    }

    [Fact]
    public async Task V2_callback_intent_closes_cross_route_redemption_race()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-v2-race",
            useLegacyCanonical: false);
        AndroidInstallLinkProofPollRequest legacyRequest = fixture.SignLegacyBootstrap(request);
        using var start = new ManualResetEventSlim(false);

        Task<ActionResult<AndroidInstallLinkV2ExchangeResponse>> v2 = Task.Run(() =>
        {
            start.Wait();
            return PollBootstrapAction(fixture, request);
        });
        Task<InstallLinkingOperationException> v1 = Task.Run(() =>
        {
            start.Wait();
            return Assert.Throws<InstallLinkingOperationException>(() =>
                fixture.Service.PollBrowserCallback(legacyRequest));
        });
        start.Set();
        ActionResult<AndroidInstallLinkV2ExchangeResponse> v2Result = await v2;
        InstallLinkingOperationException v1Error = await v1;

        Assert.Equal(StatusCodes.Status409Conflict, v1Error.StatusCode);
        AndroidInstallLinkV2ExchangeResponse exchange = Assert.IsType<AndroidInstallLinkV2ExchangeResponse>(
            Assert.IsType<OkObjectResult>(v2Result.Result).Value);
        Assert.Single(
            fixture.Store.GrantsById.Values,
            item => item.InstallationId == request.InstallationId);
        Assert.Equal(
            InstallationGrantTransports.AndroidLinkedV2,
            fixture.Store.GrantTransportAuthoritiesByGrantId[exchange.Grant.GrantId].Transport);
    }

    [Fact]
    public void Legacy_bootstrap_signature_cannot_authorize_v2_callback_poll()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-confusion",
            useLegacyCanonical: true);
        DefaultHttpContext context = CreateControllerContext(AndroidInstallLinkV2BootstrapProof.Path);
        var controller = new InstallLinkingV2Controller(
            fixture.Service,
            fixture.WorkspaceSnapshots,
            fixture.TimeProvider)
        {
            ControllerContext = new ControllerContext { HttpContext = context }
        };

        ActionResult<AndroidInstallLinkV2ExchangeResponse> action = controller.PollBrowserCallback(request);

        ObjectResult denied = Assert.IsType<ObjectResult>(action.Result);
        Assert.Equal(StatusCodes.Status409Conflict, denied.StatusCode);
        Assert.False(context.Response.Headers.ContainsKey("Authorization"));
        Assert.False(context.Response.Headers.ContainsKey(AndroidLinkedV2RequestProof.GrantHeader));
        Assert.DoesNotContain(request.Signature, JsonSerializer.Serialize(denied.Value), StringComparison.Ordinal);
    }

    [Fact]
    public void Bootstrap_canonical_payload_is_version_and_endpoint_bound()
    {
        var request = new AndroidInstallLinkProofPollV2Request(
            "android-bootstrap-v2",
            "android",
            "0.1.0-preview.11",
            "internal",
            "android",
            "arm64",
            "spki",
            1_788_544_000,
            "0123456789abcdef0123456789abcdef",
            "signature",
            "Pixel",
            Fixture.OperationId,
            InstallLinkingService.AndroidLinkedV2ProofPollTransport);

        Assert.Equal(
            string.Join('\n',
                "chummer.install-link.remote-callback.v2",
                "POST",
                "/api/v2/install-linking/callbacks/poll",
                InstallLinkingService.AndroidLinkedV2ProofPollTransport,
                Fixture.OperationId,
                "android-bootstrap-v2",
                "android",
                "0.1.0-preview.11",
                "internal",
                "android",
                "arm64",
                "1788544000",
                "0123456789abcdef0123456789abcdef",
                "Pixel"),
            Encoding.UTF8.GetString(AndroidInstallLinkV2BootstrapProof.CreateCanonicalPayload(request)));
    }

    private static async Task<(DefaultHttpContext Context, AndroidLinkedV2GrantRefreshResponse Response)>
        InvokeRefreshAsync(Fixture fixture, SignedRequest signed)
    {
        DefaultHttpContext context = signed.CreateContext();
        AndroidLinkedV2GrantRefreshResponse? response = null;
        await fixture.InvokeAsync(context, httpContext =>
        {
            var controller = new InstallLinkingV2Controller(
                fixture.Service,
                fixture.WorkspaceSnapshots,
                fixture.TimeProvider)
            {
                ControllerContext = new ControllerContext { HttpContext = httpContext }
            };
            AndroidLinkedV2GrantRefreshRequest request = JsonSerializer.Deserialize<AndroidLinkedV2GrantRefreshRequest>(
                signed.Body,
                new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
            ActionResult<AndroidLinkedV2GrantRefreshResponse> action = controller.RefreshGrant(request);
            response = Assert.IsType<AndroidLinkedV2GrantRefreshResponse>(
                Assert.IsType<OkObjectResult>(action.Result).Value);
        });
        return (context, Assert.IsType<AndroidLinkedV2GrantRefreshResponse>(response));
    }

    private static (
        DefaultHttpContext Context,
        AndroidInstallLinkV2ExchangeResponse Response) PollBootstrap(
        Fixture fixture,
        AndroidInstallLinkProofPollV2Request request,
        InstallLinkingService? service = null)
    {
        DefaultHttpContext context = CreateControllerContext(AndroidInstallLinkV2BootstrapProof.Path);
        ActionResult<AndroidInstallLinkV2ExchangeResponse> action = PollBootstrapAction(
            fixture,
            request,
            service,
            context);
        AndroidInstallLinkV2ExchangeResponse response = Assert.IsType<AndroidInstallLinkV2ExchangeResponse>(
            Assert.IsType<OkObjectResult>(action.Result).Value);
        return (context, response);
    }

    private static ActionResult<AndroidInstallLinkV2ExchangeResponse> PollBootstrapAction(
        Fixture fixture,
        AndroidInstallLinkProofPollV2Request request,
        InstallLinkingService? service = null,
        DefaultHttpContext? context = null)
    {
        var controller = new InstallLinkingV2Controller(
            service ?? fixture.Service,
            fixture.WorkspaceSnapshots,
            fixture.TimeProvider)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = context ?? CreateControllerContext(AndroidInstallLinkV2BootstrapProof.Path)
            }
        };
        return controller.PollBrowserCallback(request);
    }

    private static DefaultHttpContext CreateControllerContext(string path)
    {
        DefaultHttpContext context = new();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path = path;
        context.Response.Body = new MemoryStream();
        return context;
    }

    private static async Task<string> ReadResponseAsync(DefaultHttpContext context)
    {
        context.Response.Body.Position = 0;
        using StreamReader reader = new(context.Response.Body, Encoding.UTF8, leaveOpen: true);
        string content = await reader.ReadToEndAsync();
        context.Response.Body.Position = 0;
        return content;
    }

    private static string ToBase64Url(byte[] bytes)
        => Convert.ToBase64String(bytes)
            .TrimEnd('=')
            .Replace('+', '-')
            .Replace('/', '_');

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;
        private readonly RSA _key = RSA.Create(2048);
        private readonly IConfiguration _configuration;
        private readonly IDataProtectionProvider _protection;
        private InstallLinkingStore _store;

        public Fixture()
        {
            _root = Path.Combine(
                Path.GetTempPath(),
                "chummer-android-linked-v2-tests",
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            _configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking-store.json"),
                    ["CHUMMER_INSTALL_LINKED_WORKSPACE_STORE_PATH"] = Path.Combine(_root, "workspace-store.json")
                })
                .Build();
            _protection = DataProtectionProvider.Create(Path.Combine(_root, "keys"));
            _store = CreateStore();
            Service = new InstallLinkingService(_store, _configuration);
            WorkspaceSnapshots = new InstallLinkedWorkspaceSnapshotService(
                new InstallLinkedWorkspaceSnapshotStore(_configuration));
            TimeProvider = new FixedTimeProvider(DateTimeOffset.UtcNow);

            lock (_store.Gate)
            {
                InstallationGrantDto grant = new(
                    GrantId,
                    "android-v2",
                    InstallationGrantStates.Active,
                    AccessToken,
                    TimeProvider.GetUtcNow().AddMinutes(-1),
                    TimeProvider.GetUtcNow().AddDays(30),
                    "user-v2",
                    "subject-v2");
                _store.InstallationsById["android-v2"] = new ClaimedInstallationDto(
                    InstallationId: "android-v2",
                    ArtifactId: "android-play-app",
                    Channel: "internal",
                    Version: "0.1.0-preview.11",
                    InstallAccessClass: InstallAccessClasses.AccountRequired,
                    Status: ClaimedInstallationStates.Active,
                    CreatedAtUtc: TimeProvider.GetUtcNow().AddDays(-1),
                    UpdatedAtUtc: TimeProvider.GetUtcNow(),
                    UserId: "user-v2",
                    SubjectId: "subject-v2",
                    PublicKey: Convert.ToBase64String(_key.ExportSubjectPublicKeyInfo()),
                    ClaimTicketId: "ticket-android-v2",
                    HeadId: "android",
                    Platform: "android",
                    Arch: "arm64",
                    HostLabel: "Android test",
                    GrantId: GrantId);
                _store.GrantsById[GrantId] = grant;
                _store.GrantTransportAuthoritiesByGrantId[GrantId] =
                    new InstallationGrantTransportAuthority(
                        GrantId,
                        InstallationGrantTransports.AndroidLinkedV2);
                _store.PersistLocked();
            }
        }

        public const string GrantId = "grant-android-v2";
        public const string AccessToken = "token-android-v2";
        public const string OperationId = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
        public InstallLinkingStore Store => _store;
        public InstallLinkingService Service { get; private set; }
        public InstallLinkedWorkspaceSnapshotService WorkspaceSnapshots { get; }
        public TimeProvider TimeProvider { get; }
        public CapturingLogger Logger { get; } = new();

        public void Reload()
        {
            _store.Dispose();
            _store = CreateStore();
            Service = new InstallLinkingService(_store, _configuration);
        }

        public InstallLinkingService CreateSharedService()
            => new(_store, _configuration);

        public SignedRequest Sign(
            string path,
            string body,
            string operationId = OperationId,
            long? issuedAtUnixSeconds = null)
            => SignWithKey(_key, path, body, operationId, issuedAtUnixSeconds);

        public SignedRequest SignForGrantId(
            string path,
            string body,
            string grantId,
            string operationId = OperationId,
            long? issuedAtUnixSeconds = null)
            => SignWithKey(
                _key,
                path,
                body,
                operationId,
                issuedAtUnixSeconds,
                grantId);

        public SignedRequest SignWithKey(
            RSA signingKey,
            string path,
            string body,
            string operationId = OperationId,
            long? issuedAtUnixSeconds = null,
            string grantId = GrantId)
        {
            if (string.Equals(
                    path,
                    "/api/v2/install-linking/grants/refresh",
                    StringComparison.OrdinalIgnoreCase)
                && !body.Contains("\"operationId\"", StringComparison.Ordinal))
            {
                body = body.Insert(1, $"\"operationId\":\"{operationId}\",");
            }
            string packetKey = ToBase64Url(RandomNumberGenerator.GetBytes(
                AndroidLinkedV2RequestProof.PacketKeyBytes));
            long issued = issuedAtUnixSeconds ?? TimeProvider.GetUtcNow().ToUnixTimeSeconds();
            byte[] bodyBytes = Encoding.UTF8.GetBytes(body);
            byte[] canonical = AndroidLinkedV2RequestProof.CreateCanonicalPayload(
                HttpMethods.Post,
                path,
                "android-v2",
                grantId,
                issued,
                packetKey,
                bodyBytes);
            byte[] signature = signingKey.SignData(
                canonical,
                HashAlgorithmName.SHA256,
                RSASignaturePadding.Pkcs1);
            try
            {
                return new SignedRequest(
                    path,
                    bodyBytes,
                    grantId,
                    AccessToken,
                    packetKey,
                    issued,
                    Convert.ToBase64String(signature));
            }
            finally
            {
                CryptographicOperations.ZeroMemory(canonical);
                CryptographicOperations.ZeroMemory(signature);
            }
        }

        public AndroidInstallLinkProofPollV2Request IssueBootstrapRequest(
            string installationId,
            bool useLegacyCanonical,
            string approvedTransport = InstallLinkingService.AndroidLinkedV2ProofPollTransport)
        {
            const string headId = "android";
            const string applicationVersion = "0.1.0-preview.11";
            const string channelId = "internal";
            const string platform = "android";
            const string architecture = "arm64";
            const string hostLabel = "Android test";
            string publicKey = Convert.ToBase64String(_key.ExportSubjectPublicKeyInfo());
            Service.IssueBrowserCallback(
                new IssueInstallBrowserCallbackRequestDto(
                    installationId,
                    "android-play-app",
                    applicationVersion,
                    channelId,
                    headId,
                    platform,
                    architecture,
                    "chummer://install-link",
                    publicKey,
                    HostLabel: null,
                    InstallAccessClass: InstallAccessClasses.AccountRequired),
                "user-v2",
                "subject-v2",
                approvedTransport);

            long issued = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            string nonce = ToBase64Url(RandomNumberGenerator.GetBytes(24));
            var unsigned = new AndroidInstallLinkProofPollV2Request(
                installationId,
                headId,
                applicationVersion,
                channelId,
                platform,
                architecture,
                publicKey,
                issued,
                nonce,
                Signature: string.Empty,
                hostLabel,
                OperationId,
                InstallLinkingService.AndroidLinkedV2ProofPollTransport);
            if (!useLegacyCanonical)
            {
                return SignBootstrap(unsigned);
            }

            byte[] canonical = Encoding.UTF8.GetBytes(string.Join(
                    '\n',
                    "chummer.install-link.remote-callback.v1",
                    installationId,
                    headId,
                    applicationVersion,
                    channelId,
                    platform,
                    architecture,
                    issued.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    nonce));
            byte[] signature = _key.SignData(
                canonical,
                HashAlgorithmName.SHA256,
                RSASignaturePadding.Pkcs1);
            try
            {
                return unsigned with { Signature = Convert.ToBase64String(signature) };
            }
            finally
            {
                CryptographicOperations.ZeroMemory(canonical);
                CryptographicOperations.ZeroMemory(signature);
            }
        }

        public AndroidInstallLinkProofPollV2Request SignBootstrap(
            AndroidInstallLinkProofPollV2Request unsigned)
        {
            byte[] canonical = AndroidInstallLinkV2BootstrapProof.CreateCanonicalPayload(unsigned);
            byte[] signature = _key.SignData(
                canonical,
                HashAlgorithmName.SHA256,
                RSASignaturePadding.Pkcs1);
            try
            {
                return unsigned with { Signature = Convert.ToBase64String(signature) };
            }
            finally
            {
                CryptographicOperations.ZeroMemory(canonical);
                CryptographicOperations.ZeroMemory(signature);
            }
        }

        public AndroidInstallLinkProofPollRequest SignLegacyBootstrap(
            AndroidInstallLinkProofPollV2Request source)
        {
            string nonce = ToBase64Url(RandomNumberGenerator.GetBytes(24));
            long issued = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            byte[] canonical = Encoding.UTF8.GetBytes(string.Join(
                '\n',
                "chummer.install-link.remote-callback.v1",
                source.InstallationId,
                source.HeadId,
                source.ApplicationVersion,
                source.ChannelId,
                source.Platform,
                source.Architecture,
                issued.ToString(System.Globalization.CultureInfo.InvariantCulture),
                nonce));
            byte[] signature = _key.SignData(
                canonical,
                HashAlgorithmName.SHA256,
                RSASignaturePadding.Pkcs1);
            try
            {
                return new AndroidInstallLinkProofPollRequest(
                    source.InstallationId,
                    source.HeadId,
                    source.ApplicationVersion,
                    source.ChannelId,
                    source.Platform,
                    source.Architecture,
                    source.PublicKey,
                    issued,
                    nonce,
                    Convert.ToBase64String(signature),
                    source.HostLabel);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(canonical);
                CryptographicOperations.ZeroMemory(signature);
            }
        }

        public InstallationGrantDto SeedLegacyGrant(string installationId)
        {
            lock (_store.Gate)
            {
                DateTimeOffset now = DateTimeOffset.UtcNow;
                InstallationGrantDto grant = new(
                    $"legacy-{installationId}",
                    installationId,
                    InstallationGrantStates.Active,
                    $"legacy-token-{installationId}",
                    now.AddMinutes(-1),
                    now.AddDays(30),
                    "legacy-user",
                    "legacy-subject");
                _store.InstallationsById[installationId] = new ClaimedInstallationDto(
                    installationId,
                    "preview10-artifact",
                    "preview",
                    "0.1.0-preview.10",
                    InstallAccessClasses.AccountRequired,
                    ClaimedInstallationStates.Active,
                    now.AddDays(-1),
                    now,
                    "legacy-user",
                    "legacy-subject",
                    Convert.ToBase64String(_key.ExportSubjectPublicKeyInfo()),
                    "legacy-ticket",
                    "android",
                    "android",
                    "arm64",
                    "Legacy device",
                    grant.GrantId);
                _store.GrantsById[grant.GrantId] = grant;
                // Deliberately unmarked: pre-authority Preview10 grants migrate as legacy-v1.
                _store.PersistLocked();
                return grant;
            }
        }

        public void SeedFullyPinnedGrantCapacity()
        {
            lock (_store.Gate)
            {
                _store.GrantsById.Clear();
                _store.GrantTransportAuthoritiesByGrantId.Clear();
                _store.AndroidLinkedV2RefreshReceiptsBySourceGrantId.Clear();
                DateTimeOffset now = DateTimeOffset.UtcNow;
                for (int index = 0; index < InstallLinkingStore.MaxGrants; index++)
                {
                    string grantId = $"pinned-grant-{index:D4}";
                    _store.GrantsById[grantId] = new InstallationGrantDto(
                        grantId,
                        "pinned-install",
                        InstallationGrantStates.Revoked,
                        string.Empty,
                        now.AddMinutes(-10).AddMilliseconds(index),
                        now.AddDays(30),
                        "pinned-user",
                        "pinned-subject");
                    _store.GrantTransportAuthoritiesByGrantId[grantId] =
                        new InstallationGrantTransportAuthority(
                            grantId,
                            InstallationGrantTransports.AndroidLinkedV2);
                }

                for (int index = 0; index < InstallLinkingStore.MaxGrants / 2; index++)
                {
                    string sourceGrantId = $"pinned-grant-{index * 2:D4}";
                    string replacementGrantId = $"pinned-grant-{index * 2 + 1:D4}";
                    _store.AndroidLinkedV2RefreshReceiptsBySourceGrantId[sourceGrantId] =
                        new AndroidLinkedV2GrantRefreshReceipt(
                            sourceGrantId,
                            replacementGrantId,
                            "pinned-install",
                            new string('a', 64),
                            new string('b', 64),
                            now.AddMinutes(5),
                            "pinned-user",
                            "pinned-subject");
                }
                _store.PersistLocked();
            }
        }

        public async Task InvokeAsync(DefaultHttpContext context, Action<HttpContext> onDispatch)
        {
            var middleware = new AndroidLinkedV2RequestProofMiddleware(
                dispatched =>
                {
                    onDispatch(dispatched);
                    dispatched.Response.StatusCode = StatusCodes.Status204NoContent;
                    return Task.CompletedTask;
                },
                Logger);
            await middleware.InvokeAsync(
                context,
                Service,
                new AndroidLinkedV2RequestProofVerifier(),
                TimeProvider);
        }

        private InstallLinkingStore CreateStore()
            => new(
                _configuration,
                _protection,
                NullLogger<InstallLinkingStore>.Instance);

        public void Dispose()
        {
            _key.Dispose();
            _store.Dispose();
            (_protection as IDisposable)?.Dispose();
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed record SignedRequest(
        string Path,
        byte[] Body,
        string GrantId,
        string AccessToken,
        string PacketKey,
        long IssuedAtUnixSeconds,
        string Signature)
    {
        public DefaultHttpContext CreateContext(string? authorization = null)
        {
            DefaultHttpContext context = new();
            context.Request.Method = HttpMethods.Post;
            context.Request.Path = Path;
            context.Request.ContentType = "application/json; charset=utf-8";
            context.Request.ContentLength = Body.Length;
            context.Request.Body = new MemoryStream(Body, writable: false);
            context.Request.Headers["Authorization"] = authorization ?? $"Bearer {AccessToken}";
            context.Request.Headers[AndroidLinkedV2RequestProof.SchemeHeader] = AndroidLinkedV2RequestProof.Scheme;
            context.Request.Headers[AndroidLinkedV2RequestProof.InstallationHeader] = "android-v2";
            context.Request.Headers[AndroidLinkedV2RequestProof.GrantHeader] = GrantId;
            context.Request.Headers[AndroidLinkedV2RequestProof.PacketKeyHeader] = PacketKey;
            context.Request.Headers[AndroidLinkedV2RequestProof.IssuedHeader] =
                IssuedAtUnixSeconds.ToString(System.Globalization.CultureInfo.InvariantCulture);
            context.Request.Headers[AndroidLinkedV2RequestProof.SignatureHeader] = Signature;
            context.Response.Body = new MemoryStream();
            return context;
        }
    }

    private sealed class FixedTimeProvider(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }

    public sealed class CapturingLogger : ILogger<AndroidLinkedV2RequestProofMiddleware>
    {
        public List<string> Messages { get; } = [];

        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(
            LogLevel logLevel,
            EventId eventId,
            TState state,
            Exception? exception,
            Func<TState, Exception?, string> formatter)
            => Messages.Add(formatter(state, exception));
    }
}
