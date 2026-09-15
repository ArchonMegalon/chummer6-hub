using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Contracts.BuildGhost;
using Chummer.Contracts.Workspaces;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Infrastructure.Workspaces;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

/// <summary>
/// Real loopback HTTP, fresh session admission and encrypted consent persistence.
/// The stores use their explicit Testing configuration, not Production activation.
/// No PostgreSQL coordinator is supplied: every read must fail before private Core
/// work. Successful Core reads remain covered by the PostgreSQL integration suite.
/// </summary>
public sealed class RookWorkspaceToolEndpointTests
{
    private const string Route = "/api/internal/rook/workspace/";
    private const string Subject = "subject.rook.http";
    private const string Session = "session.rook.http";
    private const string Token = "rook-http-synthetic-bearer";
    private const string InstallationId = "ins-rook-http";
    private const string GrantId = "grant-rook-http";
    private const string PrivateMarker = "PRIVATE-ROOK-HTTP-CHARACTER-SENTINEL";
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private static readonly string[] Actions = ["consents", "consents/revoke", "read"];

    [Theory]
    [InlineData(null, "Production", null, true)]
    [InlineData("false", "Production", null, true)]
    [InlineData("TRUE", "Production", null, true)]
    [InlineData(" true ", "Production", null, true)]
    [InlineData("true", "Development", null, true)]
    [InlineData("true", "Testing", null, true)]
    [InlineData("true", "Production", "true", true)]
    [InlineData("true", "Production", "FALSE", true)]
    [InlineData("true", "Production", null, false)]
    public async Task Disabled_gate_hides_all_actions_before_body_or_service_resolution(
        string? enabled, string environment, string? publicOnly, bool registerRead)
    {
        await using TestApp app = await TestApp.StartAsync(enabled, environment, publicOnly, registerRead);
        StoreImage before = app.Fixture.Image();
        foreach (string action in Actions)
        {
            foreach (string mediaType in new[] { "application/json", "application/x-www-form-urlencoded", "multipart/form-data" })
            {
                // Both malformed and over-limit: neither MVC's form value provider
                // nor this controller may consume a hidden feature's request body.
                using HttpResponseMessage response = await app.SendAsync(action, new string('x', 8193), mediaType: mediaType);
                Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
                await AssertSafeResponse(response);
            }
        }
        Assert.Equal(0, app.Fixture.ReadResolutions);
        Assert.Equal(0, app.Fixture.Identity.Calls);
        app.Fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData("unknown")]
    [InlineData("owner-stamp")]
    [InlineData("carrier")]
    [InlineData("duplicate")]
    [InlineData("wrong-case")]
    [InlineData("missing")]
    [InlineData("wrong-type")]
    [InlineData("null")]
    [InlineData("array")]
    [InlineData("trailing")]
    public async Task Strict_json_rejects_ambiguous_or_caller_authority_fields_before_admission(string damage)
    {
        await using TestApp app = await TestApp.StartAsync();
        StoreImage before = app.Fixture.Image();
        foreach (string action in Actions)
        {
            Dictionary<string, object?> body = app.Fixture.Body(action);
            string first = body.Keys.First();
            string wire;
            switch (damage)
            {
                case "unknown": body["unexpected"] = PrivateMarker; break;
                case "owner-stamp": body["ownerAuthorityInstanceId"] = PrivateMarker; break;
                case "carrier": body["workspaceContinuation"] = new { notes = PrivateMarker }; break;
                case "wrong-case": body[char.ToUpperInvariant(first[0]) + first[1..]] = body[first]; body.Remove(first); break;
                case "missing": body.Remove(first); break;
                case "wrong-type": body[first] = 123; break;
                case "null": body[first] = null; break;
            }
            wire = JsonSerializer.Serialize(body, Json);
            wire = damage switch
            {
                "duplicate" => wire[..^1] + "," + JsonSerializer.Serialize(first) + ":" + JsonSerializer.Serialize(body[first]) + "}",
                "array" => "[" + wire + "]",
                "trailing" => wire + "{}",
                _ => wire
            };
            using HttpResponseMessage response = await app.SendAsync(action, wire);
            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
            await AssertSafeResponse(response);
        }
        Assert.Equal(0, app.Fixture.Identity.Calls);
        app.Fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData("text/plain", null, null, 415)]
    [InlineData("application/x-www-form-urlencoded", null, null, 415)]
    [InlineData("multipart/form-data", null, null, 415)]
    [InlineData("application/problem+json", null, null, 415)]
    [InlineData("application/json", "gzip", null, 415)]
    [InlineData("application/json", null, "?ownerId=untrusted", 400)]
    public async Task Media_encoding_and_query_cannot_add_an_alternate_input_channel(
        string mediaType, string? encoding, string? query, int status)
    {
        await using TestApp app = await TestApp.StartAsync();
        StoreImage before = app.Fixture.Image();
        foreach (string action in Actions)
        {
            using HttpResponseMessage response = await app.SendAsync(action + query,
                JsonSerializer.Serialize(app.Fixture.Body(action), Json), mediaType: mediaType, encoding: encoding);
            Assert.Equal((HttpStatusCode)status, response.StatusCode);
            await AssertSafeResponse(response);
        }
        Assert.Equal(0, app.Fixture.Identity.Calls);
        app.Fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Body_limit_is_enforced_with_content_length_or_chunked_transfer(bool chunked)
    {
        await using TestApp app = await TestApp.StartAsync();
        StoreImage before = app.Fixture.Image();
        foreach (string action in Actions)
        {
            string wire = JsonSerializer.Serialize(app.Fixture.Body(action), Json);
            // Valid JSON with trailing whitespace, so this proves the byte limit, not syntax rejection.
            wire += new string(' ', 8193 - Encoding.UTF8.GetByteCount(wire));
            using HttpResponseMessage response = await app.SendAsync(action, wire, chunked: chunked);
            Assert.Equal(HttpStatusCode.RequestEntityTooLarge, response.StatusCode);
            await AssertSafeResponse(response);
        }
        Assert.Equal(0, app.Fixture.Identity.Calls);
        app.Fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData("missing")]
    [InlineData("cookie-only")]
    [InlineData("malformed")]
    public async Task Every_action_requires_the_original_explicit_bearer_not_a_cookie(string credential)
    {
        await using TestApp app = await TestApp.StartAsync();
        StoreImage before = app.Fixture.Image();
        foreach (string action in Actions)
        {
            using HttpResponseMessage response = await app.SendAsync(action,
                JsonSerializer.Serialize(app.Fixture.Body(action), Json),
                authorization: credential == "malformed" ? "Bearer not a valid token" : null,
                cookie: credential == "cookie-only" ? "chummer.session=" + Token : null);
            // An unsupported host rejects the actual Linux-only factory before
            // ResolveAsync; do not claim that branch reached bearer admission.
            Assert.Equal(action == "read" && !OperatingSystem.IsLinux()
                ? HttpStatusCode.ServiceUnavailable : HttpStatusCode.Unauthorized, response.StatusCode);
            await AssertSafeResponse(response);
        }
        Assert.Equal(0, app.Fixture.Identity.Calls);
        app.Fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData("inactive", 401)]
    [InlineData("expired", 401)]
    [InlineData("missing-account", 403)]
    [InlineData("foreign-account", 503)]
    [InlineData("identity-failure", 503)]
    public async Task Consent_requires_fresh_identity_and_the_existing_exact_owner(string change, int status)
    {
        await using TestApp app = await TestApp.StartAsync();
        Fixture fixture = app.Fixture;
        switch (change)
        {
            case "inactive": fixture.Identity.Active = false; break;
            case "expired": fixture.Identity.ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(-1); break;
            case "missing-account": fixture.Identity.SubjectId = "subject.no-canonical-account"; break;
            case "foreign-account":
                fixture.Accounts.EnsureUser("subject.foreign-owner", "Synthetic other owner", "foreign@example.invalid");
                fixture.Identity.SubjectId = "subject.foreign-owner";
                break;
            case "identity-failure": fixture.Identity.ThrowPrivateFailure = true; break;
        }
        StoreImage before = fixture.Image();
        using HttpResponseMessage response = await app.SendAsync("consents", JsonSerializer.Serialize(fixture.GrantBody(), Json));
        Assert.Equal((HttpStatusCode)status, response.StatusCode);
        await AssertSafeResponse(response);
        Assert.Equal(1, fixture.Identity.Calls);
        Assert.Empty(fixture.InstallStore.RookReadConsentsById);
        fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData("confirmation", 403)]
    [InlineData("revision", 409)]
    [InlineData("server-token", 409)]
    [InlineData("digest", 409)]
    [InlineData("workspace", 404)]
    [InlineData("expiry", 400)]
    [InlineData("revoked-grant", 503)]
    public async Task Grant_validates_explicit_confirmation_and_exact_current_selection(string change, int status)
    {
        await using TestApp app = await TestApp.StartAsync();
        Fixture fixture = app.Fixture;
        Dictionary<string, object?> body = fixture.GrantBody();
        switch (change)
        {
            case "confirmation": body["explicitConfirmation"] = false; break;
            case "revision": body["remoteRevision"] = fixture.Selected.RemoteRevision + 1; break;
            case "server-token": body["serverToken"] = DifferentDigest(fixture.Selected.ServerToken!); break;
            case "digest": body["continuationDigest"] = DifferentDigest(fixture.Selected.WorkspaceContinuationDigest!); break;
            case "workspace": body["workspaceId"] = "ws-other-selection"; break;
            case "expiry": body["expiresAtUtc"] = DateTimeOffset.UtcNow.AddMinutes(-1); break;
            case "revoked-grant": fixture.Installations.RevokeGrantForOwner(InstallationId, fixture.User.UserId, Subject); break;
        }
        StoreImage before = fixture.Image();
        using HttpResponseMessage response = await app.SendAsync("consents", JsonSerializer.Serialize(body, Json));
        Assert.Equal((HttpStatusCode)status, response.StatusCode);
        await AssertSafeResponse(response);
        Assert.Equal(change == "confirmation" ? 0 : 1, fixture.Identity.Calls);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task Owner_grants_and_revokes_persisted_consent_without_mutating_character_or_account()
    {
        await using TestApp app = await TestApp.StartAsync();
        Fixture fixture = app.Fixture;
        fixture.Identity.ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(2);
        string stableBefore = fixture.StableState();

        InstallLinkingRookReadConsent consent = await Grant(app);
        Assert.Equal(1, consent.Version);
        Assert.Null(consent.RevokedAtUtc);
        Assert.Equal(fixture.Identity.ExpiresAtUtc, consent.ExpiresAtUtc);
        Assert.Equal(fixture.Selected.ServerToken, consent.ServerToken);
        Assert.Equal(fixture.Selected.WorkspaceContinuationDigest, consent.ContinuationDigest);
        Assert.Equal(stableBefore, fixture.StableState());

        // Revoking the installation cannot prevent its owner from revoking prior consent.
        fixture.Installations.RevokeGrantForOwner(InstallationId, fixture.User.UserId, Subject);
        using HttpResponseMessage revoke = await app.SendAsync("consents/revoke",
            JsonSerializer.Serialize(fixture.RevokeBody(consent), Json));
        Assert.Equal(HttpStatusCode.OK, revoke.StatusCode);
        await AssertConsentProjection(revoke, fixture);
        InstallLinkingRookReadConsent revoked = fixture.InstallStore.RookReadConsentsById[consent.ConsentId];
        Assert.Equal(2, revoked.Version);
        Assert.NotNull(revoked.RevokedAtUtc);
        Assert.Equal(stableBefore, fixture.StableState());
        Assert.Equal(2, fixture.Identity.Calls);

        StoreImage beforeRetry = fixture.Image();
        using HttpResponseMessage retry = await app.SendAsync("consents/revoke",
            JsonSerializer.Serialize(fixture.RevokeBody(revoked), Json));
        Assert.Equal(HttpStatusCode.OK, retry.StatusCode);
        await AssertConsentProjection(retry, fixture);
        fixture.AssertUnchanged(beforeRetry);
        Assert.Equal(3, fixture.Identity.Calls);
        Assert.DoesNotContain(Token, File.ReadAllText(fixture.InstallStore.StoragePath), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("stale-version", 503)]
    [InlineData("foreign-owner", 503)]
    [InlineData("expired-session", 401)]
    public async Task Revocation_rejects_stale_version_or_noncurrent_owner_without_a_write(string change, int status)
    {
        await using TestApp app = await TestApp.StartAsync();
        InstallLinkingRookReadConsent consent = await Grant(app);
        Fixture fixture = app.Fixture;
        Dictionary<string, object?> body = fixture.RevokeBody(consent);
        switch (change)
        {
            case "stale-version": body["expectedVersion"] = consent.Version + 1; break;
            case "foreign-owner":
                fixture.Accounts.EnsureUser("subject.foreign-owner", "Synthetic other owner", "foreign@example.invalid");
                fixture.Identity.SubjectId = "subject.foreign-owner";
                break;
            case "expired-session": fixture.Identity.ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(-1); break;
        }
        StoreImage before = fixture.Image();
        using HttpResponseMessage response = await app.SendAsync("consents/revoke", JsonSerializer.Serialize(body, Json));
        Assert.Equal((HttpStatusCode)status, response.StatusCode);
        await AssertSafeResponse(response);
        Assert.Null(fixture.InstallStore.RookReadConsentsById[consent.ConsentId].RevokedAtUtc);
        Assert.Equal(2, fixture.Identity.Calls);
        fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData("intact-but-no-postgres", 403)]
    [InlineData("stale-version", 403)]
    [InlineData("revoked-consent", 403)]
    [InlineData("revoked-grant", 403)]
    [InlineData("expired-consent", 403)]
    [InlineData("foreign-owner", 403)]
    [InlineData("expired-session", 401)]
    public async Task Read_cannot_release_a_carrier_or_enter_Core_without_real_fenced_admission(string change, int status)
    {
        await using TestApp app = await TestApp.StartAsync();
        InstallLinkingRookReadConsent consent = await Grant(app);
        Fixture fixture = app.Fixture;
        Dictionary<string, object?> body = fixture.ReadBody(consent);
        switch (change)
        {
            case "stale-version": body["expectedVersion"] = consent.Version + 1; break;
            case "revoked-consent":
                using (HttpResponseMessage revoke = await app.SendAsync("consents/revoke",
                    JsonSerializer.Serialize(fixture.RevokeBody(consent), Json)))
                    Assert.Equal(HttpStatusCode.OK, revoke.StatusCode);
                break;
            case "revoked-grant": fixture.Installations.RevokeGrantForOwner(InstallationId, fixture.User.UserId, Subject); break;
            case "expired-consent":
                // Test setup persists an actually expired record while Identity
                // remains active. No clock wait or alternate read authority.
                DateTimeOffset issuedAt = fixture.InstallStore.GrantsById[GrantId].IssuedAtUtc;
                InstallLinkingRookReadConsent expired = consent with
                {
                    IssuedAtUtc = issuedAt,
                    ExpiresAtUtc = issuedAt.AddSeconds(30)
                };
                Assert.True(InstallLinkingRookReadConsent.ShapeIsValid(expired));
                Assert.True(expired.ExpiresAtUtc < DateTimeOffset.UtcNow);
                lock (fixture.InstallStore.Gate)
                {
                    fixture.InstallStore.RookReadConsentsById[consent.ConsentId] = expired;
                    fixture.InstallStore.PersistLocked();
                }
                break;
            case "foreign-owner":
                fixture.Accounts.EnsureUser("subject.foreign-owner", "Synthetic other owner", "foreign@example.invalid");
                fixture.Identity.SubjectId = "subject.foreign-owner";
                break;
            case "expired-session": fixture.Identity.ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(-1); break;
        }
        StoreImage before = fixture.Image();
        int callsBefore = fixture.Identity.Calls;
        using HttpResponseMessage response = await app.SendAsync("read", JsonSerializer.Serialize(body, Json));
        Assert.Equal(OperatingSystem.IsLinux() ? (HttpStatusCode)status : HttpStatusCode.ServiceUnavailable, response.StatusCode);
        await AssertSafeResponse(response);
        Assert.Equal(callsBefore + (OperatingSystem.IsLinux() ? 1 : 0), fixture.Identity.Calls);
        Assert.Equal(1, fixture.ReadResolutions);
        fixture.AssertUnchanged(before);
        Assert.Empty(Directory.GetDirectories(fixture.Scratch));
    }

    [Fact]
    public async Task Disconnect_during_fresh_identity_admission_cancels_without_consent_or_private_work()
    {
        await using TestApp app = await TestApp.StartAsync();
        Fixture fixture = app.Fixture;
        fixture.Identity.Block = true;
        StoreImage before = fixture.Image();
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        Task<HttpResponseMessage> pending = app.SendAsync("consents",
            JsonSerializer.Serialize(fixture.GrantBody(), Json), cancellationToken: cancellation.Token);
        await fixture.Identity.Entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
        {
            using HttpResponseMessage unexpected = await pending;
        });
        await fixture.Identity.Canceled.Task.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(1, fixture.Identity.Calls);
        Assert.Empty(fixture.InstallStore.RookReadConsentsById);
        fixture.AssertUnchanged(before);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Rule_projection_preserves_Core_observations_but_not_owner_authority_or_result_digest(bool resolved)
    {
        // Serialization-only proof, not a fabricated successful HTTP/Core admission.
        var modules = new[] { new WorkspaceRuleExecutingModule("rules", "Fixture.Query", "Fixture.Core", Guid.NewGuid()) };
        var binding = new WorkspaceRuleQuestionBinding(WorkspaceRuleQuestionSchemas.BindingV1,
            PrivateMarker + "-owner", true, PrivateMarker + "-authority", 987654321,
            new CharacterWorkspaceId("ws-projection-fixture"), "sr5", 4, 3,
            new string('a', 64), "settings-fixture", new string('b', 64), new string('c', 64),
            "executing-modules", new string('d', 64), modules, WorkspaceRuleQuestionIntents.QualityLevel,
            "saved-quality-fixture", "en");
        var anchor = new WorkspaceRuleSourceAnchor("fixture-anchor", "sr5", "FIXTURE", 12,
            "fixture-quality", binding.SourceNodeDigest, binding.SettingsProfileId, binding.SourceProfileDigest,
            ["fixture quality level: 2"]);
        var explanation = new BuildGhostRuleExplanation("fixture-explanation/v1", "fixture-explanation",
            WorkspaceRuleQuestionIntents.QualityLevelRuleId, "Fixture question", resolved ? "resolved" : "unresolved",
            "Fixture-only explanation", resolved ? [anchor.AnchorId] : [], resolved ? null : "fixture uncertainty", null);
        var result = new WorkspaceRuleQuestionResult(WorkspaceRuleQuestionSchemas.ResultV1,
            resolved ? WorkspaceRuleQuestionStatuses.Resolved : WorkspaceRuleQuestionStatuses.Unresolved,
            explanation, resolved ? [anchor] : [], binding, resolved ? 2 : null, resolved ? 4 : null,
            PrivateMarker + "-raw-result-digest", resolved ? null : "fixture unresolved");

        RookWorkspaceRuleReadResponseDto projection = RookWorkspaceRuleReadResponseDto.FromResult(result);
        using JsonDocument document = JsonDocument.Parse(JsonSerializer.Serialize(projection, Json));
        JsonElement wire = document.RootElement;
        Assert.Equal(new[] { "explanation", "failureReason", "level", "maximumLevel", "ruleContext", "sourceAnchors", "status" },
            wire.EnumerateObject().Select(property => property.Name).Order(StringComparer.Ordinal).ToArray());
        Assert.Equal(result.Status, wire.GetProperty("status").GetString());
        Assert.Equal(JsonSerializer.Serialize(result.Explanation, Json), wire.GetProperty("explanation").GetRawText());
        Assert.Equal(JsonSerializer.Serialize(result.SourceAnchors, Json), wire.GetProperty("sourceAnchors").GetRawText());
        Assert.Equal(result.FailureReason, wire.GetProperty("failureReason").GetString());
        Assert.Equal(result.Level, wire.GetProperty("level").ValueKind == JsonValueKind.Null
            ? (int?)null : wire.GetProperty("level").GetInt32());
        Assert.Equal(result.MaximumLevel, wire.GetProperty("maximumLevel").ValueKind == JsonValueKind.Null
            ? (int?)null : wire.GetProperty("maximumLevel").GetInt32());
        JsonElement context = wire.GetProperty("ruleContext");
        Assert.Equal(new[] { "contentRevision", "engineFingerprint", "engineIdentityKind", "executingModules", "intent",
            "locale", "rulesetId", "savedRevision", "settingsProfileId", "sourceNodeDigest", "sourceProfileDigest",
            "subjectId", "workspaceDocumentDigest", "workspaceId" },
            context.EnumerateObject().Select(property => property.Name).Order(StringComparer.Ordinal).ToArray());
        using JsonDocument fullBinding = JsonDocument.Parse(JsonSerializer.Serialize(binding, Json));
        Assert.Equal(binding.WorkspaceId.Value, context.GetProperty("workspaceId").GetString());
        foreach (JsonProperty property in context.EnumerateObject())
            if (property.Name != "workspaceId")
                Assert.Equal(fullBinding.RootElement.GetProperty(property.Name).GetRawText(), property.Value.GetRawText());
        string serialized = wire.GetRawText();
        foreach (string forbidden in new[] { PrivateMarker, "ownerId", "trustedLocalOwner", "ownerAuthorityInstanceId",
            "ownerTransitionRevision", "rawBinding", "resultDigest", "rawResultDigest", "carrier" })
            Assert.DoesNotContain(forbidden, serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Unbound_unresolved_projection_does_not_invent_rule_context_or_levels()
    {
        var result = new WorkspaceRuleQuestionResult(WorkspaceRuleQuestionSchemas.ResultV1,
            WorkspaceRuleQuestionStatuses.Unresolved,
            new BuildGhostRuleExplanation("fixture-explanation/v1", "fixture", "unsupported", "Fixture question",
                "unresolved", "No supported rule intent.", [], "unsupported", null),
            [], null, null, null, PrivateMarker, "unsupported");
        RookWorkspaceRuleReadResponseDto projection = RookWorkspaceRuleReadResponseDto.FromResult(result);
        Assert.Null(projection.RuleContext);
        Assert.Null(projection.Level);
        Assert.Null(projection.MaximumLevel);
        Assert.Empty(projection.SourceAnchors);
        Assert.Equal(WorkspaceRuleQuestionStatuses.Unresolved, projection.Status);
        Assert.DoesNotContain(PrivateMarker, JsonSerializer.Serialize(projection, Json), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Response_buffer_returns_complete_JSON_at_normal_size_and_the_exact_byte_limit(bool atLimit)
    {
        using ServiceProvider services = new ServiceCollection().BuildServiceProvider();
        using var output = new MemoryStream();
        RookWorkspaceToolController controller = SerializationController(services, output);
        RookWorkspaceRuleReadResponseDto projection = SerializationFixture();
        int overhead = JsonSerializer.SerializeToUtf8Bytes(projection, Json).Length;
        projection = projection with
        {
            Explanation = projection.Explanation with
            {
                Explanation = new string('x', atLimit ? RookWorkspaceToolController.MaxResponseBytes - overhead : 16)
            }
        };

        FileContentResult result = controller.SerializeBoundedResponse(projection);

        Assert.Equal("application/json; charset=utf-8", result.ContentType);
        Assert.Equal(JsonSerializer.SerializeToUtf8Bytes(projection, Json), result.FileContents);
        if (atLimit) Assert.Equal(RookWorkspaceToolController.MaxResponseBytes, result.FileContents.Length);
        using JsonDocument complete = JsonDocument.Parse(result.FileContents);
        Assert.Equal(projection.Explanation.Explanation,
            complete.RootElement.GetProperty("explanation").GetProperty("explanation").GetString());
        Assert.False(controller.Response.HasStarted);
        Assert.Equal(0, output.Length);
    }

    [Theory]
    [InlineData("string")]
    [InlineData("collection")]
    public void Oversized_response_is_rejected_before_any_body_bytes_are_written(string oversized)
    {
        using ServiceProvider services = new ServiceCollection().BuildServiceProvider();
        using var output = new MemoryStream();
        RookWorkspaceToolController controller = SerializationController(services, output);
        RookWorkspaceRuleReadResponseDto projection = SerializationFixture();
        projection = oversized == "string"
            ? projection with { Explanation = projection.Explanation with
                { Explanation = PrivateMarker + new string('x', RookWorkspaceToolController.MaxResponseBytes) } }
            : projection with { SourceAnchors = Enumerable.Repeat(new WorkspaceRuleSourceAnchor(
                "fixture-anchor", "sr5", "FIXTURE", 12, "fixture-quality", new string('a', 64),
                "fixture-settings", new string('b', 64), ["fixture-only trace"]), 1024).ToArray() };
        Assert.True(JsonSerializer.SerializeToUtf8Bytes(projection, Json).Length > RookWorkspaceToolController.MaxResponseBytes);

        InstallLinkingOperationException error = Assert.Throws<InstallLinkingOperationException>(
            () => controller.SerializeBoundedResponse(projection));

        Assert.Equal(StatusCodes.Status503ServiceUnavailable, error.StatusCode);
        Assert.DoesNotContain(PrivateMarker, error.Message, StringComparison.Ordinal);
        Assert.Null(error.InnerException);
        Assert.False(controller.Response.HasStarted);
        Assert.Equal(0, output.Length);
    }

    private static RookWorkspaceRuleReadResponseDto SerializationFixture()
        => new("unresolved", new BuildGhostRuleExplanation("fixture-explanation/v1", "fixture", "unsupported",
            "Fixture question", "unresolved", "", [], "unsupported", null), [], null, null, "unsupported", null);

    private static RookWorkspaceToolController SerializationController(IServiceProvider services, Stream body)
    {
        var context = new DefaultHttpContext();
        context.Response.Body = body;
        return new(new ConfigurationBuilder().Build(), new TestEnvironment(), services)
        {
            ControllerContext = new ControllerContext { HttpContext = context }
        };
    }

    private sealed class TestEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Production;
        public string ApplicationName { get; set; } = nameof(RookWorkspaceToolEndpointTests);
        public string ContentRootPath { get; set; } = Path.GetTempPath();
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }

    private static string DifferentDigest(string digest) => new(digest[0] == 'a' ? 'b' : 'a', 64);

    private static async Task<InstallLinkingRookReadConsent> Grant(TestApp app)
    {
        using HttpResponseMessage response = await app.SendAsync("consents", JsonSerializer.Serialize(app.Fixture.GrantBody(), Json));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        await AssertConsentProjection(response, app.Fixture);
        return Assert.Single(app.Fixture.InstallStore.RookReadConsentsById).Value;
    }

    private static async Task AssertConsentProjection(HttpResponseMessage response, Fixture fixture)
    {
        string wire = await AssertSafeResponse(response);
        using JsonDocument document = JsonDocument.Parse(wire);
        JsonElement root = document.RootElement;
        Assert.Equal(new[] { "consentId", "expiresAtUtc", "issuedAtUtc", "purpose", "revokedAtUtc", "version", "workspaceId" },
            root.EnumerateObject().Select(property => property.Name).Order(StringComparer.Ordinal).ToArray());
        InstallLinkingRookReadConsent consent = fixture.InstallStore.RookReadConsentsById[root.GetProperty("consentId").GetString()!];
        Assert.Equal(consent.Version, root.GetProperty("version").GetInt64());
        Assert.Equal(consent.WorkspaceId, root.GetProperty("workspaceId").GetString());
        Assert.Equal(consent.Purpose, root.GetProperty("purpose").GetString());
        Assert.Equal(consent.IssuedAtUtc, root.GetProperty("issuedAtUtc").GetDateTimeOffset());
        Assert.Equal(consent.ExpiresAtUtc, root.GetProperty("expiresAtUtc").GetDateTimeOffset());
        Assert.Equal(consent.RevokedAtUtc, root.GetProperty("revokedAtUtc").ValueKind == JsonValueKind.Null
            ? (DateTimeOffset?)null : root.GetProperty("revokedAtUtc").GetDateTimeOffset());
        Assert.DoesNotContain(fixture.User.UserId, wire, StringComparison.Ordinal);
        Assert.DoesNotContain(fixture.Selected.ServerToken!, wire, StringComparison.Ordinal);
        Assert.DoesNotContain(fixture.Selected.WorkspaceContinuationDigest!, wire, StringComparison.Ordinal);
    }

    private static async Task<string> AssertSafeResponse(HttpResponseMessage response)
    {
        Assert.True(response.Headers.CacheControl?.NoStore);
        Assert.True(response.Headers.CacheControl?.Private);
        string wire = await response.Content.ReadAsStringAsync();
        Assert.InRange(Encoding.UTF8.GetByteCount(wire), 0, 64 * 1024);
        foreach (string secret in new[] { PrivateMarker, Token, Subject, Session, InstallationId, GrantId,
            "ownerAuthorityInstanceId", "ownerTransitionRevision", "trustedLocalOwner", "rawBinding", "rawResultDigest",
            "workspaceContinuation", "continuationDigest", "serverToken", "stackTrace", "innerException" })
            Assert.DoesNotContain(secret, wire, StringComparison.OrdinalIgnoreCase);
        return wire;
    }

    private sealed record StoreImage(string[] Paths, string[] Digests, long[] Modified, string Consents);

    private sealed class Fixture : IDisposable
    {
        private readonly IDataProtectionProvider _protection;
        private readonly HttpClient _identityClient;
        private readonly string _character;
        public string Root { get; }
        public string Scratch { get; }
        public string Sources { get; }
        public string SnapshotPath { get; }
        public CommunityStore AccountsStore { get; }
        public AccountService Accounts { get; }
        public HubUserDto User { get; }
        public InstallLinkingStore InstallStore { get; }
        public InstallLinkingService Installations { get; }
        public InstallLinkedWorkspaceSnapshotRecord Selected { get; }
        public RookWorkspaceReadAdmissionService Admission { get; }
        public IdentityHandler Identity { get; }
        public int ReadResolutions;

        public Fixture()
        {
            Root = Path.Combine(Path.GetTempPath(), "chummer-rook-http-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Root);
            try
            {
                Scratch = Path.Combine(Root, "private-core-scratch");
                if (OperatingSystem.IsWindows()) Directory.CreateDirectory(Scratch);
                else Directory.CreateDirectory(Scratch, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
                Sources = Path.Combine(Root, "synthetic-core-sources");
                Directory.CreateDirectory(Sources);
                _character = Path.Combine(Root, "private-character.xml");
                File.WriteAllText(_character, "<character><notes>" + PrivateMarker + "</notes></character>");
                SnapshotPath = Path.Combine(Root, "snapshots.json");
                IConfiguration storeConfiguration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["ASPNETCORE_ENVIRONMENT"] = "Testing",
                    ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.invalid",
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(Root, "community.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(Root, "install.json"),
                    ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] = SnapshotPath
                }).Build();
                _protection = DataProtectionProvider.Create(Path.Combine(Root, "keys"));
                InstallStore = new(storeConfiguration, _protection, NullLogger<InstallLinkingStore>.Instance);
                AccountsStore = new(storeConfiguration, NullLogger<CommunityStore>.Instance);
                Accounts = new(AccountsStore);
                User = Accounts.EnsureUser(Subject, "Synthetic HTTP owner", "rook-http@example.invalid");
                Identity = new();
                _identityClient = new(Identity) { Timeout = TimeSpan.FromSeconds(10) };
                Installations = new(InstallStore, storeConfiguration);
                DateTimeOffset now = DateTimeOffset.UtcNow;
                using RSA key = RSA.Create(2048);
                var installation = new ClaimedInstallationDto(InstallationId, "android-play-app", "internal",
                    "0.1.0-preview.12", InstallAccessClasses.AccountRequired, ClaimedInstallationStates.Active,
                    now.AddMinutes(-2), now.AddMinutes(-1), UserId: User.UserId, SubjectId: Subject,
                    PublicKey: Convert.ToBase64String(key.ExportSubjectPublicKeyInfo()), HeadId: "android",
                    Platform: "android", Arch: "arm64", GrantId: GrantId);
                lock (InstallStore.Gate)
                {
                    InstallStore.InstallationsById[InstallationId] = installation;
                    InstallStore.GrantsById[GrantId] = new(GrantId, InstallationId, InstallationGrantStates.Active,
                        "synthetic-installation-token", now.AddMinutes(-1), now.AddHours(1), User.UserId, Subject);
                    InstallStore.GrantTransportAuthoritiesByGrantId[GrantId] = new(GrantId, InstallationGrantTransports.AndroidLinkedV2);
                    InstallStore.PersistLocked();
                }
                var snapshots = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(storeConfiguration));
                WorkspaceContinuationSnapshot full = InstallLinkedWorkspaceSnapshotTransferTests.SampleContinuation(Subject);
                Selected = snapshots.UpsertForInstallation(installation,
                    InstallLinkedWorkspaceSnapshotTransferTests.ToContinuationRecord(full), 0);
                var sessions = new HubSessionAccountAdmissionService(_identityClient, storeConfiguration, Accounts, TimeProvider.System);
                Admission = new(sessions, Accounts, Installations, snapshots, TimeProvider.System);
                Assert.True(InstallStore.IsHealthy);
                Assert.Empty(InstallStore.RookReadConsentsById);
            }
            catch
            {
                InstallStore?.Dispose();
                _identityClient?.Dispose();
                (_protection as IDisposable)?.Dispose();
                if (Directory.Exists(Root)) Directory.Delete(Root, recursive: true);
                throw;
            }
        }

        public Dictionary<string, object?> Body(string action) => action switch
        {
            "consents" => GrantBody(),
            "consents/revoke" => RevokeBody(),
            "read" => ReadBody(),
            _ => throw new ArgumentOutOfRangeException(nameof(action))
        };

        public Dictionary<string, object?> GrantBody() => new()
        {
            ["installationId"] = InstallationId, ["grantId"] = GrantId, ["workspaceId"] = Selected.WorkspaceId,
            ["remoteRevision"] = Selected.RemoteRevision, ["serverToken"] = Selected.ServerToken,
            ["continuationDigest"] = Selected.WorkspaceContinuationDigest, ["explicitConfirmation"] = true,
            ["expiresAtUtc"] = DateTimeOffset.UtcNow.AddMinutes(5)
        };

        public Dictionary<string, object?> RevokeBody(InstallLinkingRookReadConsent? consent = null) => new()
        {
            ["consentId"] = consent?.ConsentId ?? new string('a', 64), ["expectedVersion"] = consent?.Version ?? 1
        };

        public Dictionary<string, object?> ReadBody(InstallLinkingRookReadConsent? consent = null) => new()
        {
            ["installationId"] = InstallationId, ["grantId"] = GrantId,
            ["consentId"] = consent?.ConsentId ?? new string('a', 64), ["expectedVersion"] = consent?.Version ?? 1,
            ["intent"] = WorkspaceRuleQuestionIntents.QualityLevel, ["savedSubjectId"] = "saved-quality-http-fixture", ["locale"] = "en"
        };

        public string StableState() => string.Join("|", new[] { AccountsStore.StoragePath, SnapshotPath, _character }
            .Select(path => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))) + ":" + File.GetLastWriteTimeUtc(path).Ticks));

        public StoreImage Image()
        {
            string[] paths = Directory.GetFiles(Root, "*", SearchOption.AllDirectories).Order(StringComparer.Ordinal).ToArray();
            Assert.InRange(paths.Length, 1, 20);
            Assert.All(paths, path => Assert.InRange(new FileInfo(path).Length, 0, 1024 * 1024));
            return new(paths, paths.Select(path => path == InstallStore.StoragePath + ".writer.lock"
                ? "exclusive-lease:" + new FileInfo(path).Length
                : Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)))).ToArray(),
                paths.Select(path => File.GetLastWriteTimeUtc(path).Ticks).ToArray(),
                JsonSerializer.Serialize(InstallStore.RookReadConsentsById, Json));
        }

        public void AssertUnchanged(StoreImage before)
        {
            StoreImage after = Image();
            Assert.Equal(before.Paths, after.Paths);
            Assert.Equal(before.Digests, after.Digests);
            Assert.Equal(before.Modified, after.Modified);
            Assert.Equal(before.Consents, after.Consents);
            Assert.All(Identity.Tokens, token => Assert.Equal(Token, token));
        }

        public void Dispose()
        {
            try { InstallStore.Dispose(); }
            finally
            {
                _identityClient.Dispose();
                (_protection as IDisposable)?.Dispose();
                if (Directory.Exists(Root)) Directory.Delete(Root, recursive: true);
            }
        }
    }

    private sealed class TestApp(WebApplication application, Fixture fixture, HttpClient client) : IAsyncDisposable
    {
        public Fixture Fixture => fixture;

        public static async Task<TestApp> StartAsync(string? enabled = "true", string environment = "Production",
            string? publicOnly = null, bool registerRead = true)
        {
            Fixture fixture = new();
            WebApplication? app = null;
            try
            {
                WebApplicationBuilder builder = WebApplication.CreateBuilder(new WebApplicationOptions
                {
                    EnvironmentName = environment, ContentRootPath = fixture.Root
                });
                builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_ROOK_PRIVATE_RUNTIME_ENABLED"] = enabled,
                    ["CHUMMER_PUBLIC_DOWNLOAD_ONLY"] = publicOnly
                });
                builder.Logging.ClearProviders();
                builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0));
                builder.Services.AddControllers().AddApplicationPart(typeof(RookWorkspaceToolController).Assembly);
                builder.Services.AddSingleton(fixture.Admission);
                if (registerRead)
                    builder.Services.AddTransient<RookWorkspaceRuleReadService>(_ =>
                    {
                        Interlocked.Increment(ref fixture.ReadResolutions);
                        return new(fixture.Admission,
                            new PrivateWorkspaceRuleRuntimeFactory(fixture.Scratch, fixture.Sources, fixture.Sources, null));
                    });
                app = builder.Build();
                app.MapControllers();
                using var startup = new CancellationTokenSource(TimeSpan.FromSeconds(10));
                await app.StartAsync(startup.Token);
                IServerAddressesFeature addresses = app.Services.GetRequiredService<IServer>().Features
                    .Get<IServerAddressesFeature>() ?? throw new InvalidOperationException("No loopback test listener.");
                HttpClient client = new(new HttpClientHandler { UseCookies = false, AllowAutoRedirect = false, UseProxy = false })
                {
                    BaseAddress = new Uri(Assert.Single(addresses.Addresses)), Timeout = TimeSpan.FromSeconds(10)
                };
                return new(app, fixture, client);
            }
            catch
            {
                try { if (app is not null) await app.DisposeAsync(); }
                finally { fixture.Dispose(); }
                throw;
            }
        }

        public async Task<HttpResponseMessage> SendAsync(string action, string body,
            string? authorization = "Bearer " + Token, string? cookie = null,
            string mediaType = "application/json", string? encoding = null, bool chunked = false,
            CancellationToken cancellationToken = default)
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, Route + action);
            request.Content = chunked ? new ChunkedContent(Encoding.UTF8.GetBytes(body)) : new StringContent(body, Encoding.UTF8);
            request.Content.Headers.ContentType = new MediaTypeHeaderValue(mediaType);
            if (authorization is not null) request.Headers.TryAddWithoutValidation("Authorization", authorization);
            if (cookie is not null) request.Headers.TryAddWithoutValidation("Cookie", cookie);
            if (encoding is not null) request.Content.Headers.ContentEncoding.Add(encoding);
            if (chunked) request.Headers.TransferEncodingChunked = true;
            return await client.SendAsync(request, cancellationToken);
        }

        public async ValueTask DisposeAsync()
        {
            client.Dispose();
            try
            {
                using var shutdown = new CancellationTokenSource(TimeSpan.FromSeconds(10));
                await application.StopAsync(shutdown.Token);
            }
            finally
            {
                try { await application.DisposeAsync(); }
                finally { fixture.Dispose(); }
            }
        }
    }

    private sealed class ChunkedContent(byte[] bytes) : HttpContent
    {
        protected override bool TryComputeLength(out long length) { length = 0; return false; }
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context)
            => stream.WriteAsync(bytes).AsTask();
    }

    private sealed class IdentityHandler : HttpMessageHandler
    {
        public bool Active { get; set; } = true;
        public string SubjectId { get; set; } = Subject;
        public DateTimeOffset ExpiresAtUtc { get; set; } = DateTimeOffset.UtcNow.AddMinutes(10);
        public bool ThrowPrivateFailure { get; set; }
        public bool Block { get; set; }
        public TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Canceled { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public int Calls { get; private set; }
        public List<string> Tokens { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Calls++;
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://identity.example.invalid/api/v1/identity/introspect", request.RequestUri?.AbsoluteUri);
            IdentityIntrospectionRequest? input = JsonSerializer.Deserialize<IdentityIntrospectionRequest>(
                await request.Content!.ReadAsStringAsync(cancellationToken), Json);
            Tokens.Add(Assert.IsType<IdentityIntrospectionRequest>(input).AccessToken);
            Entered.TrySetResult();
            if (Block)
            {
                try { await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken); }
                catch (OperationCanceledException) { Canceled.TrySetResult(); throw; }
            }
            if (ThrowPrivateFailure) throw new IOException(PrivateMarker);
            return new(HttpStatusCode.OK)
            {
                Content = new StringContent(JsonSerializer.Serialize(new IdentityIntrospectionResponse(
                    Active, Session, SubjectId, ["player"], ExpiresAtUtc), Json), Encoding.UTF8, "application/json")
            };
        }
    }
}
