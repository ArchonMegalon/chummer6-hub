using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingControllerBrowserCallbackTests
{
    [Fact]
    public async Task Android_proof_poll_links_the_exact_approved_install_without_exposing_callback_code()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer android-review-access-token";
        using RSA rsa = RSA.Create(2048);
        string publicKey = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());
        const string callbackUri = "https://chummer.run/app/install-link?state=android-review-state";

        IActionResult approval = await fixture.Controller.BrowserInstallLink(
            installationId: "android-review-install",
            headId: "android",
            applicationVersion: "0.1.0-preview.7",
            releaseChannel: "preview",
            platform: "android",
            arch: "arm64",
            installLinkCallbackUri: callbackUri,
            cancellationToken: CancellationToken.None,
            installLinkTransport: "proof_poll",
            publicKey: publicKey);

        ContentResult page = Assert.IsType<ContentResult>(approval);
        Assert.Equal(StatusCodes.Status200OK, page.StatusCode);
        Assert.Contains("Account linked", page.Content, StringComparison.Ordinal);
        Assert.Contains("Return to Chummer", page.Content, StringComparison.Ordinal);
        Assert.Contains(callbackUri.Replace("&", "&amp;", StringComparison.Ordinal), page.Content, StringComparison.Ordinal);
        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal(publicKey, callback.PublicKey);
        Assert.Equal("android-play-app", callback.ArtifactId);
        Assert.Equal(
            InstallLinkingService.LegacyProofPollTransport,
            fixture.Store.BrowserCallbackTransportIntentsByCallbackId[callback.CallbackId].Transport);
        Assert.DoesNotContain(callback.CallbackCode, page.Content, StringComparison.Ordinal);

        long issuedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        const string nonce = "0123456789abcdef0123456789abcdef0123456789abcdef";
        byte[] proof = Encoding.UTF8.GetBytes(string.Join(
            '\n',
            "chummer.install-link.remote-callback.v1",
            "android-review-install",
            "android",
            "0.1.0-preview.7",
            "preview",
            "android",
            "arm64",
            issuedAt.ToString(System.Globalization.CultureInfo.InvariantCulture),
            nonce));
        string signature;
        try
        {
            signature = Convert.ToBase64String(rsa.SignData(
                proof,
                HashAlgorithmName.SHA256,
                RSASignaturePadding.Pkcs1));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(proof);
        }

        AndroidInstallLinkProofPollRequest poll = new(
            "android-review-install",
            "android",
            "0.1.0-preview.7",
            "preview",
            "android",
            "arm64",
            publicKey,
            issuedAt,
            nonce,
            signature,
            "Play review device");
        ActionResult<ExchangeInstallBrowserCallbackResponseDto> pollResult =
            fixture.Controller.PollBrowserCallback(poll);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(pollResult.Result);
        ExchangeInstallBrowserCallbackResponseDto exchanged =
            Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(ok.Value);
        Assert.Equal(InstallationGrantStates.Active, exchanged.Grant.Status);
        Assert.Equal("android-review-install", exchanged.Grant.InstallationId);
        Assert.Equal("subject.install.browser", exchanged.Installation.SubjectId);

        ActionResult<ExchangeInstallBrowserCallbackResponseDto> replay =
            fixture.Controller.PollBrowserCallback(poll);
        OkObjectResult replayOk = Assert.IsType<OkObjectResult>(replay.Result);
        ExchangeInstallBrowserCallbackResponseDto replayExchange =
            Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(replayOk.Value);
        Assert.Equal(InstallationGrantStates.Active, replayExchange.Grant.Status);
        Assert.Equal(exchanged.Grant.GrantId, replayExchange.Grant.GrantId);
        Assert.True(replayExchange.AlreadyClaimed);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Desktop_proof_poll_links_the_exact_approved_install_without_exposing_callback_code()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";
        using RSA rsa = RSA.Create(2048);
        string publicKey = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());
        const string callbackUri = "chummer://install-link";

        IActionResult approval = await fixture.Controller.BrowserInstallLink(
            installationId: "desktop-proof-install",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: callbackUri,
            cancellationToken: CancellationToken.None,
            installLinkTransport: "proof_poll",
            publicKey: publicKey);

        ContentResult page = Assert.IsType<ContentResult>(approval);
        Assert.Equal(StatusCodes.Status200OK, page.StatusCode);
        Assert.Contains("Account linked", page.Content, StringComparison.Ordinal);
        Assert.Contains("Return to Chummer", page.Content, StringComparison.Ordinal);
        Assert.Contains(callbackUri.Replace("&", "&amp;", StringComparison.Ordinal), page.Content, StringComparison.Ordinal);
        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal(publicKey, callback.PublicKey);
        Assert.Equal("avalonia-win-x64-installer", callback.ArtifactId);
        Assert.Equal(
            InstallLinkingService.LegacyProofPollTransport,
            fixture.Store.BrowserCallbackTransportIntentsByCallbackId[callback.CallbackId].Transport);
        Assert.DoesNotContain(callback.CallbackCode, page.Content, StringComparison.Ordinal);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Desktop_client_url_journey_login_approval_poll_grant_end_to_end()
    {
        using RSA rsa = RSA.Create(2048);
        string spkiBase64 = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());

        // Step 0: build the exact client URL (DesktopInstallLinkingRuntime contract).
        string clientPath = HubBrowserAuthService.BuildInstallLinkingNextPath(
            "cross-repo-desktop",
            "avalonia",
            "6.0.1-preview",
            "preview",
            "windows",
            "x64",
            "chummer://install-link",
            "proof_poll",
            spkiBase64);
        Assert.Equal(
            "/account/access/install-link",
            new Uri("https://chummer.run" + clientPath).AbsolutePath);

        // Step 1: unauthenticated GET -> login redirect carrying the next path.
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";

        IActionResult redirectResult = await fixture.Controller.BrowserInstallLink(
            installationId: "cross-repo-desktop",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None,
            installLinkTransport: "proof_poll",
            publicKey: spkiBase64);

        RedirectResult redirect = Assert.IsType<RedirectResult>(redirectResult);
        Assert.StartsWith("/login?next=", redirect.Url, StringComparison.Ordinal);

        // Step 2: login return sanitization preserves the proof-poll parameters exactly.
        string nextPath = Uri.UnescapeDataString(redirect.Url!["/login?next=".Length..]);
        string sanitized = HubBrowserAuthService.SanitizeNextPath(nextPath, "/safe");
        IReadOnlyDictionary<string, Microsoft.Extensions.Primitives.StringValues> query =
            Microsoft.AspNetCore.WebUtilities.QueryHelpers.ParseQuery(new Uri("https://chummer.run" + sanitized).Query);
        Assert.Equal("proof_poll", Assert.Single(query["installLinkTransport"]));
        Assert.Equal(spkiBase64, Assert.Single(query["publicKey"]));
        Assert.Equal("cross-repo-desktop", Assert.Single(query["installationId"]));
        Assert.Equal("chummer://install-link/", Assert.Single(query["installLinkCallbackUri"]));

        // Step 3: authenticated approval with the same parameters -> 200 approval page.
        // The browser session changes at login, so the authenticated call runs against
        // a fresh fixture (the identity handler is constructed per-fixture).
        using Fixture authedFixture = new(authenticated: true);
        authedFixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        authedFixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        authedFixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";
        IActionResult approval = await authedFixture.Controller.BrowserInstallLink(
            installationId: "cross-repo-desktop",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None,
            installLinkTransport: "proof_poll",
            publicKey: spkiBase64);

        ContentResult page = Assert.IsType<ContentResult>(approval);
        Assert.Equal(StatusCodes.Status200OK, page.StatusCode);
        Assert.Contains("Account linked", page.Content!, StringComparison.Ordinal);
        InstallBrowserCallbackDto callback = Assert.Single(authedFixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("cross-repo-desktop", callback.InstallationId);
        Assert.Equal(spkiBase64, callback.PublicKey);

        // Step 4: the desktop app polls with a signed proof -> active grant.
        long issuedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        const string nonce = "0123456789abcdef0123456789abcdef0123456789abcdef";
        byte[] proof = Encoding.UTF8.GetBytes(string.Join(
            '\n',
            "chummer.install-link.remote-callback.v1",
            "cross-repo-desktop",
            "avalonia",
            "6.0.1-preview",
            "preview",
            "windows",
            "x64",
            issuedAt.ToString(System.Globalization.CultureInfo.InvariantCulture),
            nonce));
        string signature;
        try
        {
            signature = Convert.ToBase64String(rsa.SignData(
                proof,
                HashAlgorithmName.SHA256,
                RSASignaturePadding.Pkcs1));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(proof);
        }

        AndroidInstallLinkProofPollRequest poll = new(
            "cross-repo-desktop",
            "avalonia",
            "6.0.1-preview",
            "preview",
            "windows",
            "x64",
            spkiBase64,
            issuedAt,
            nonce,
            signature,
            "Desktop proof-poll journey");
        ActionResult<ExchangeInstallBrowserCallbackResponseDto> pollResult =
            authedFixture.Controller.PollBrowserCallback(poll);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(pollResult.Result);
        ExchangeInstallBrowserCallbackResponseDto exchanged =
            Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(ok.Value);
        Assert.Equal(InstallationGrantStates.Active, exchanged.Grant.Status);
        Assert.Equal("cross-repo-desktop", exchanged.Grant.InstallationId);

        // Step 5: replay -> AlreadyClaimed recovery (identical retry).
        ActionResult<ExchangeInstallBrowserCallbackResponseDto> replay =
            authedFixture.Controller.PollBrowserCallback(poll);
        OkObjectResult replayOk = Assert.IsType<OkObjectResult>(replay.Result);
        ExchangeInstallBrowserCallbackResponseDto replayExchange =
            Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(replayOk.Value);
        Assert.Equal(exchanged.Grant.GrantId, replayExchange.Grant.GrantId);
        Assert.True(replayExchange.AlreadyClaimed);
        AssertSensitiveResponseHeaders(authedFixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Desktop_proof_poll_for_new_operation_stays_pending_despite_older_version_history()
    {
        // R69 audit regression: a terminal callback recorded for application version A
        // must not terminate a fresh, authenticated operation from version B on the
        // same installation. The operation-bound poll has to keep waiting for its own
        // approval instead of being rejected through the historical-target fallback.
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        const string installationId = "desktop-version-history-install";

        // Version A: issue and complete an approval so terminal history exists.
        AndroidInstallLinkProofPollRequest versionA = CreateSignedPoll(key, installationId, bound: true, nonce: "0123456789abcdef0123456789abcdef0123456789abcdef");
        await ApproveAttempt(fixture, versionA);
        InstallBrowserCallbackDto historyCallback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        // The browser completes version A: the poll itself exchanges the callback and
        // records terminal history for this installation.
        ExchangeInstallBrowserCallbackResponseDto historyExchange =
            AssertExchange(fixture.Controller.PollBrowserCallback(versionA));
        Assert.False(historyExchange.AlreadyClaimed);

        // Version B: a fresh, authenticated operation signs its own proof with a NEW
        // application version. Its approval has not been recorded yet when the first
        // poll arrives.
        const string versionBNonce = "fedcba9876543210fedcba9876543210fedcba9876543210";
        long versionBIssuedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        byte[] versionBProof = Encoding.UTF8.GetBytes(string.Join(
            '\n',
            "chummer.install-link.remote-callback.v1",
            installationId,
            "avalonia",
            "6.0.2-preview",
            "preview",
            "windows",
            "x64",
            versionBIssuedAt.ToString(System.Globalization.CultureInfo.InvariantCulture),
            versionBNonce));
        AndroidInstallLinkProofPollRequest versionB;
        try
        {
            versionB = new AndroidInstallLinkProofPollRequest(
                installationId, "avalonia", "6.0.2-preview", "preview", "windows", "x64",
                versionA.PublicKey,
                versionBIssuedAt,
                versionBNonce,
                Convert.ToBase64String(key.SignData(versionBProof, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1)),
                "Desktop version-B attempt",
                OperationId: ProofOperationId(versionBNonce));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(versionBProof);
        }

        // The new operation must stay pending (202) rather than being terminated by
        // version A's terminal history (409).
        AssertPending(fixture.Controller.PollBrowserCallback(versionB));

        // The browser then approves version B's attempt; the poll consumes it and
        // links against the exact new approval.
        await ApproveAttempt(fixture, versionB);
        InstallBrowserCallbackDto versionBCallback = Assert.Single(fixture.Store.BrowserCallbacksById.Values,
            item => !string.Equals(item.CallbackId, historyCallback.CallbackId, StringComparison.Ordinal));
        Assert.NotNull(versionBCallback);

        ExchangeInstallBrowserCallbackResponseDto exchanged =
            AssertExchange(fixture.Controller.PollBrowserCallback(versionB));
        Assert.Equal(InstallationGrantStates.Active, exchanged.Grant.Status);
        Assert.False(exchanged.AlreadyClaimed);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Desktop_proof_poll_retry_after_lost_response_recovers_original_grant()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";
        using RSA rsa = RSA.Create(2048);
        string publicKey = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());
        const string callbackUri = "chummer://install-link";

        await fixture.Controller.BrowserInstallLink(
            installationId: "desktop-recovery-install",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: callbackUri,
            cancellationToken: CancellationToken.None,
            installLinkTransport: "proof_poll",
            publicKey: publicKey);

        long issuedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        const string nonce = "0123456789abcdef0123456789abcdef0123456789abcdef";
        byte[] proof = Encoding.UTF8.GetBytes(string.Join(
            '\n',
            "chummer.install-link.remote-callback.v1",
            "desktop-recovery-install",
            "avalonia",
            "6.0.1-preview",
            "preview",
            "windows",
            "x64",
            issuedAt.ToString(System.Globalization.CultureInfo.InvariantCulture),
            nonce));
        string signature;
        try
        {
            signature = Convert.ToBase64String(rsa.SignData(
                proof,
                HashAlgorithmName.SHA256,
                RSASignaturePadding.Pkcs1));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(proof);
        }

        AndroidInstallLinkProofPollRequest poll = new(
            "desktop-recovery-install",
            "avalonia",
            "6.0.1-preview",
            "preview",
            "windows",
            "x64",
            publicKey,
            issuedAt,
            nonce,
            signature,
            "Desktop recovery journey");

        // First poll succeeds (its response is "lost" on the way back).
        ActionResult<ExchangeInstallBrowserCallbackResponseDto> first =
            fixture.Controller.PollBrowserCallback(poll);
        OkObjectResult firstOk = Assert.IsType<OkObjectResult>(first.Result);
        ExchangeInstallBrowserCallbackResponseDto firstExchange =
            Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(firstOk.Value);
        Assert.Equal(InstallationGrantStates.Active, firstExchange.Grant.Status);
        string firstGrantId = firstExchange.Grant.GrantId;

        fixture.ReloadInstallLinking();

        // Retry with the IDENTICAL proof reaches the recovery path and returns
        // the original grant instead of failing with "already completed".
        ActionResult<ExchangeInstallBrowserCallbackResponseDto> retry =
            fixture.Controller.PollBrowserCallback(poll);
        OkObjectResult retryOk = Assert.IsType<OkObjectResult>(retry.Result);
        ExchangeInstallBrowserCallbackResponseDto retryExchange =
            Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(retryOk.Value);
        Assert.Equal(InstallationGrantStates.Active, retryExchange.Grant.Status);
        Assert.Equal(firstGrantId, retryExchange.Grant.GrantId);
        Assert.Equal(firstExchange.Grant.AccessToken, retryExchange.Grant.AccessToken);
        Assert.True(retryExchange.AlreadyClaimed);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Desktop_proof_poll_retry_with_different_nonce_is_isolated_after_redemption()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";
        using RSA rsa = RSA.Create(2048);
        string publicKey = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());
        const string callbackUri = "chummer://install-link";

        await fixture.Controller.BrowserInstallLink(
            installationId: "desktop-isolation-install",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: callbackUri,
            cancellationToken: CancellationToken.None,
            installLinkTransport: "proof_poll",
            publicKey: publicKey);

        static string SignProof(RSA key, long issuedAt, string nonce)
        {
            byte[] proof = System.Text.Encoding.UTF8.GetBytes(string.Join(
                '\n',
                "chummer.install-link.remote-callback.v1",
                "desktop-isolation-install",
                "avalonia",
                "6.0.1-preview",
                "preview",
                "windows",
                "x64",
                issuedAt.ToString(System.Globalization.CultureInfo.InvariantCulture),
                nonce));
            try
            {
                return Convert.ToBase64String(key.SignData(
                    proof,
                    HashAlgorithmName.SHA256,
                    RSASignaturePadding.Pkcs1));
            }
            finally
            {
                System.Security.Cryptography.CryptographicOperations.ZeroMemory(proof);
            }
        }

        long issuedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        const string originalNonce = "0123456789abcdef0123456789abcdef0123456789abcdef";
        const string attackerNonce = "fedcba9876543210fedcba9876543210fedcba9876543210";
        string originalSignature = SignProof(rsa, issuedAt, originalNonce);
        string attackerSignature = SignProof(rsa, issuedAt, attackerNonce);

        AndroidInstallLinkProofPollRequest originalPoll = new(
            "desktop-isolation-install",
            "avalonia",
            "6.0.1-preview",
            "preview",
            "windows",
            "x64",
            publicKey,
            issuedAt,
            originalNonce,
            originalSignature,
            "Desktop isolation original");
        AndroidInstallLinkProofPollRequest attackerPoll = originalPoll with
        {
            Nonce = attackerNonce,
            Signature = attackerSignature,
            HostLabel = "Desktop isolation attacker"
        };

        // Original poll redeems the callback.
        ActionResult<ExchangeInstallBrowserCallbackResponseDto> first =
            fixture.Controller.PollBrowserCallback(originalPoll);
        OkObjectResult firstOk = Assert.IsType<OkObjectResult>(first.Result);
        ExchangeInstallBrowserCallbackResponseDto firstExchange =
            Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(firstOk.Value);
        string firstGrantId = firstExchange.Grant.GrantId;

        // A DIFFERENT attempt (fresh nonce) after redemption must NOT recover the
        // grant: attempt isolation keeps terminal callbacks terminal.
        ActionResult<ExchangeInstallBrowserCallbackResponseDto> attacker =
            fixture.Controller.PollBrowserCallback(attackerPoll);
        ObjectResult conflict = Assert.IsType<ObjectResult>(attacker.Result);
        Assert.Equal(StatusCodes.Status409Conflict, conflict.StatusCode);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Proof_poll_persisted_pre_upgrade_receipt_cannot_recover_with_identical_or_fresh_proof(bool preTransportAuthority)
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        using RSA key = RSA.Create(2048);
        IssueInstallBrowserCallbackRequestDto approval = CreateProofApproval(key);
        InstallBrowserCallbackDto callback = fixture.InstallLinking.IssueBrowserCallback(
            approval, fixture.User.UserId, fixture.SubjectId, InstallLinkingService.LegacyProofPollTransport).Callback;
        AndroidInstallLinkProofPollRequest original = SignProofPoll(key, approval);
        ExchangeInstallBrowserCallbackResponseDto first = Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(
            fixture.InstallLinking.PollBrowserCallback(original).Exchange);

        // Persist the pre-upgrade shape, including the older pre-transport-authority form.
        // Loading it must remain supported, but its exchange digest cannot identify a proof retry.
        lock (fixture.Store.Gate)
        {
            InstallBrowserCallbackRedemptionReceipt receipt = fixture.Store.BrowserCallbackRedemptionReceiptsByCallbackId[callback.CallbackId];
            fixture.Store.BrowserCallbackRedemptionReceiptsByCallbackId[callback.CallbackId] = receipt with
            {
                OperationId = null,
                OperationSha256 = null,
                CallbackTransport = preTransportAuthority ? null : receipt.CallbackTransport
            };
            if (preTransportAuthority)
            {
                fixture.Store.BrowserCallbackTransportIntentsByCallbackId.Remove(callback.CallbackId);
            }
            fixture.Store.PersistLocked();
        }
        fixture.ReloadInstallLinking();
        InstallBrowserCallbackRedemptionReceipt loaded = Assert.Single(fixture.Store.BrowserCallbackRedemptionReceiptsByCallbackId.Values);
        Assert.Null(loaded.OperationId);
        Assert.Null(loaded.OperationSha256);
        Assert.Equal(first.Grant.GrantId, loaded.GrantId);

        AndroidInstallLinkProofPollRequest fresh = SignProofPoll(key, approval, "fedcba9876543210fedcba9876543210");
        foreach (AndroidInstallLinkProofPollRequest poll in new[] { original, fresh })
        {
            ObjectResult rejected = Assert.IsType<ObjectResult>(fixture.Controller.PollBrowserCallback(poll).Result);
            Assert.Equal(StatusCodes.Status409Conflict, rejected.StatusCode);
        }
        Assert.Equal(first.Grant, Assert.Single(fixture.Store.GrantsById.Values));
        Assert.Equal(InstallBrowserCallbackStates.Redeemed, Assert.Single(fixture.Store.BrowserCallbacksById.Values).Status);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Theory]
    [InlineData("unknown-head", "windows", "x64", StatusCodes.Status404NotFound)]
    [InlineData("avalonia", "unknown-platform", "x64", StatusCodes.Status404NotFound)]
    [InlineData("avalonia", "windows", "arm64", StatusCodes.Status404NotFound)]
    [InlineData("avalonia", "windows", "unknown-arch", StatusCodes.Status404NotFound)]
    [InlineData("android", "windows", "x64", StatusCodes.Status404NotFound)]
    [InlineData("avalonia", "android", "arm64", StatusCodes.Status404NotFound)]
    [InlineData("Android", "android", "arm64", StatusCodes.Status404NotFound)]
    [InlineData("android", "Android", "arm64", StatusCodes.Status404NotFound)]
    [InlineData(null, "windows", "x64", StatusCodes.Status400BadRequest)]
    [InlineData("avalonia", null, "x64", StatusCodes.Status400BadRequest)]
    [InlineData("avalonia", "windows", null, StatusCodes.Status400BadRequest)]
    [InlineData("avalonia", "windows", " ", StatusCodes.Status400BadRequest)]
    public async Task Desktop_proof_poll_requires_complete_catalog_target(
        string? headId, string? platform, string? arch, int expectedStatus)
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        fixture.Controller.Request.Headers.Authorization = "Bearer desktop-access-token";
        using RSA key = RSA.Create(2048);
        IActionResult result = await fixture.Controller.BrowserInstallLink(
            "desktop-invalid-target", headId, "6.0.1-preview", "preview", platform, arch,
            "chummer://install-link", CancellationToken.None, "proof_poll",
            Convert.ToBase64String(key.ExportSubjectPublicKeyInfo()));

        if (expectedStatus == StatusCodes.Status400BadRequest)
        {
            Assert.Equal(expectedStatus, Assert.IsType<ObjectResult>(result).StatusCode);
        }
        else
        {
            ContentResult page = Assert.IsType<ContentResult>(result);
            Assert.Equal(expectedStatus, page.StatusCode);
            Assert.Contains("This install needs a current desktop package", page.Content, StringComparison.Ordinal);
        }
        Assert.Empty(fixture.Store.BrowserCallbacksById);
        Assert.Empty(fixture.Store.InstallationsById);
        Assert.Empty(fixture.Store.GrantsById);
    }

    [Theory]
    [InlineData("avalonia", "linux", "avalonia-linux-x64-installer")]
    [InlineData("blazor-desktop", "windows", "blazor-desktop-win-x64-installer")]
    public async Task Desktop_proof_poll_uses_existing_catalog_platform_matching(string headId, string platform, string artifactId)
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        fixture.Controller.Request.Headers.Authorization = "Bearer desktop-access-token";
        using RSA key = RSA.Create(2048);
        IssueInstallBrowserCallbackRequestDto request = CreateProofApproval(key) with { HeadId = headId, Platform = platform };
        IActionResult result = await fixture.Controller.BrowserInstallLink(
            request.InstallationId, request.HeadId, request.ApplicationVersion, request.ChannelId, request.Platform, request.Arch,
            request.CallbackUri, CancellationToken.None, "proof_poll", request.PublicKey);

        Assert.Equal(StatusCodes.Status200OK, Assert.IsType<ContentResult>(result).StatusCode);
        Assert.Equal(artifactId, Assert.Single(fixture.Store.BrowserCallbacksById.Values).ArtifactId);
        OkObjectResult exchange = Assert.IsType<OkObjectResult>(fixture.Controller.PollBrowserCallback(SignProofPoll(key, request)).Result);
        Assert.Equal(artifactId, Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(exchange.Value).Installation.ArtifactId);
    }

    [Theory]
    [InlineData("chummer://install-link")]
    [InlineData("http://127.0.0.1:47761/install-link/callback")]
    public async Task Desktop_proof_poll_browser_approval_rejects_duplicate_state_and_strips_credentials(string callbackBase)
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        fixture.Controller.Request.Headers.Authorization = "Bearer desktop-access-token";
        using RSA key = RSA.Create(2048);
        string publicKey = Convert.ToBase64String(key.ExportSubjectPublicKeyInfo());
        string callbackUri = callbackBase + "?state=safe&nonce=safe-nonce&accessToken=prior-access&callbackCode=foreign-code";
        IActionResult rejected = await fixture.Controller.BrowserInstallLink(
            "desktop-query-install", "avalonia", "6.0.1-preview", "preview", "windows", "x64",
            callbackUri + "&state=duplicate", CancellationToken.None, "proof_poll", publicKey);
        Assert.Equal(StatusCodes.Status400BadRequest, Assert.IsType<ObjectResult>(rejected).StatusCode);
        Assert.Empty(fixture.Store.BrowserCallbacksById);

        IActionResult approved = await fixture.Controller.BrowserInstallLink(
            "desktop-query-install", "avalonia", "6.0.1-preview", "preview", "windows", "x64",
            callbackUri, CancellationToken.None, "proof_poll", publicKey);
        ContentResult page = Assert.IsType<ContentResult>(approved);
        Assert.Equal(StatusCodes.Status200OK, page.StatusCode);
        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        var query = Microsoft.AspNetCore.WebUtilities.QueryHelpers.ParseQuery(new Uri(callback.CallbackUri!).Query);
        Assert.Equal(2, query.Count);
        Assert.Equal("safe", Assert.Single(query["state"]));
        Assert.Equal("safe-nonce", Assert.Single(query["nonce"]));
        Assert.DoesNotContain("prior-access", callback.CallbackUri, StringComparison.Ordinal);
        Assert.DoesNotContain("foreign-code", callback.CallbackUri, StringComparison.Ordinal);
        Assert.DoesNotContain("prior-access", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("foreign-code", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain(callback.CallbackCode, page.Content, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("key")]
    [InlineData("head")]
    [InlineData("version")]
    [InlineData("channel")]
    [InlineData("platform")]
    [InlineData("arch")]
    [InlineData("artifact")]
    [InlineData("host")]
    [InlineData("access")]
    [InlineData("state")]
    public void Pending_proof_poll_approval_reuses_only_exact_identity(string changedField)
    {
        using Fixture fixture = new(authenticated: true);
        using RSA key = RSA.Create(2048);
        using RSA otherKey = RSA.Create(2048);
        IssueInstallBrowserCallbackRequestDto request = CreateProofApproval(key) with { CallbackUri = "chummer://install-link?state=case-sensitive" };
        InstallBrowserCallbackDto first = fixture.InstallLinking.IssueBrowserCallback(
            request, fixture.User.UserId, fixture.SubjectId, InstallLinkingService.LegacyProofPollTransport).Callback;
        InstallBrowserCallbackDto repeated = fixture.InstallLinking.IssueBrowserCallback(
            request, fixture.User.UserId, fixture.SubjectId, InstallLinkingService.LegacyProofPollTransport).Callback;
        Assert.Equal(first.CallbackId, repeated.CallbackId);

        IssueInstallBrowserCallbackRequestDto changed = changedField switch
        {
            "key" => request with { PublicKey = Convert.ToBase64String(otherKey.ExportSubjectPublicKeyInfo()) },
            "head" => request with { HeadId = "blazor-desktop" },
            "version" => request with { ApplicationVersion = "6.0.2-preview" },
            "channel" => request with { ChannelId = "stable" },
            "platform" => request with { Platform = "linux" },
            "arch" => request with { Arch = "arm64" },
            "artifact" => request with { ArtifactId = "replacement-installer" },
            "host" => request with { HostLabel = "other-host" },
            "access" => request with { InstallAccessClass = InstallAccessClasses.AccountRecommended },
            "state" => request with { CallbackUri = "chummer://install-link?state=CASE-SENSITIVE" },
            _ => throw new ArgumentOutOfRangeException(nameof(changedField))
        };
        InstallBrowserCallbackDto next = fixture.InstallLinking.IssueBrowserCallback(
            changed, fixture.User.UserId, fixture.SubjectId, InstallLinkingService.LegacyProofPollTransport).Callback;
        Assert.NotEqual(first.CallbackId, next.CallbackId);
        Assert.Equal(changed.PublicKey, next.PublicKey);
        Assert.Equal(changed.ApplicationVersion, next.Version);
        Assert.Equal(changed.ArtifactId, next.ArtifactId);
        Assert.Equal(changed.CallbackUri, next.CallbackUri);
        Assert.Equal(2, fixture.Store.BrowserCallbacksById.Count);
        Assert.Empty(fixture.Store.GrantsById);
    }

    [Fact]
    public void New_browser_approval_cannot_move_a_linked_install_to_another_account()
    {
        using Fixture fixture = new(authenticated: true);
        using RSA key = RSA.Create(2048);
        IssueInstallBrowserCallbackRequestDto request = CreateProofApproval(key);
        fixture.InstallLinking.IssueBrowserCallback(
            request, fixture.User.UserId, fixture.SubjectId, InstallLinkingService.LegacyProofPollTransport);
        AndroidInstallLinkProofPollRequest proof = SignProofPoll(key, request);
        ExchangeInstallBrowserCallbackResponseDto original = Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(
            fixture.InstallLinking.PollBrowserCallback(proof).Exchange);

        InstallLinkingOperationException conflict = Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.InstallLinking.IssueBrowserCallback(request, "other-user", "other-subject", InstallLinkingService.LegacyProofPollTransport));
        Assert.Equal(StatusCodes.Status409Conflict, conflict.StatusCode);
        ExchangeInstallBrowserCallbackResponseDto retry = Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(
            fixture.InstallLinking.PollBrowserCallback(proof).Exchange);
        Assert.True(retry.AlreadyClaimed);
        Assert.Equal(original.Grant, retry.Grant);
        Assert.Equal(fixture.User.UserId, retry.Installation.UserId);
        Assert.Equal(fixture.SubjectId, retry.Installation.SubjectId);
        Assert.Single(fixture.Store.BrowserCallbacksById);
    }

    [Fact]
    public async Task Android_v2_browser_approval_persists_distinct_proof_poll_intent()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer android-v2-access-token";
        using RSA rsa = RSA.Create(2048);
        string publicKey = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());

        IActionResult approval = await fixture.Controller.BrowserInstallLink(
            installationId: "android-v2-browser-intent",
            headId: "android",
            applicationVersion: "0.1.0-preview.11",
            releaseChannel: "preview",
            platform: "android",
            arch: "arm64",
            installLinkCallbackUri: "https://chummer.run/app/install-link?state=android-v2-state",
            cancellationToken: CancellationToken.None,
            installLinkTransport: InstallLinkingService.AndroidLinkedV2ProofPollTransport,
            publicKey: publicKey);

        Assert.Equal(StatusCodes.Status200OK, Assert.IsType<ContentResult>(approval).StatusCode);
        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal(
            InstallLinkingService.AndroidLinkedV2ProofPollTransport,
            fixture.Store.BrowserCallbackTransportIntentsByCallbackId[callback.CallbackId].Transport);
    }

    [Fact]
    public async Task Browser_install_link_redirects_unauthenticated_requests_to_login_with_return_path()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString(
            "?installationId=ins-unauth&headId=avalonia&platform=windows&arch=x64&installLinkCallbackUri=chummer%3A%2F%2Finstall-link");

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-unauth",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.StartsWith("/login?next=", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("%2Faccount%2Faccess%2Finstall-link%3FinstallationId%3Dins-unauth", redirect.Url, StringComparison.Ordinal);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Browser_install_link_login_return_path_does_not_relay_hostile_credentials()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString(
            "?accessToken=top-secret&ticket=top-ticket&claimCode=top-claim&apiKey=top-key");

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-safe",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "http://127.0.0.1:47761/install-link/callback?state=desktop&nonce=callback-proof&accessToken=nested-secret&unknown=nested-unknown#ticket=fragment-ticket",
            cancellationToken: CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        string decoded = redirect.Url!;
        for (int pass = 0; pass < 8; pass++)
        {
            decoded = Uri.UnescapeDataString(decoded);
        }

        Assert.Contains("installationId=ins-safe", decoded, StringComparison.Ordinal);
        Assert.Contains("state=desktop", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("top-secret", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("top-ticket", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("top-claim", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("top-key", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("nested-secret", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("nested-unknown", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("fragment-ticket", decoded, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("https://evil.example/install-link")]
    [InlineData("chummer://downloads")]
    [InlineData("http://127.0.0.1:47761/browser-only/claim?state=desktop")]
    [InlineData("https://localhost:47762/account/access/install-link")]
    public async Task Browser_install_link_rejects_invalid_callback_uris(string callbackUri)
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-invalid",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: callbackUri,
            cancellationToken: CancellationToken.None);

        ObjectResult problem = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status400BadRequest, problem.StatusCode);
        ProblemDetails details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("install-link callback uri is invalid.", details.Detail);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Browser_install_link_renders_authenticated_handoff_page_with_callback_code()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-browser-route",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.Equal(StatusCodes.Status200OK, page.StatusCode);
        Assert.Contains("Claim this copy in Chummer", page.Content, StringComparison.Ordinal);
        Assert.Contains("Claim this copy", page.Content, StringComparison.Ordinal);
        Assert.Contains("Installer:", page.Content, StringComparison.Ordinal);
        Assert.Contains("id=\"install-link-open\"", page.Content, StringComparison.Ordinal);
        Assert.Contains("Claim link", page.Content, StringComparison.Ordinal);
        Assert.Contains("Copy claim link", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Manual launch link", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Open Chummer to finish linking this install", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Package:", page.Content, StringComparison.Ordinal);
        Assert.Contains("window.location.assign(href)", page.Content, StringComparison.Ordinal);
        Assert.Contains("iframe", page.Content, StringComparison.Ordinal);
        Assert.True(TryExtractPrimaryHref(page.Content!, out string callbackHref), "The controller should render a manual callback link.");
        Assert.True(Uri.TryCreate(WebUtility.HtmlDecode(callbackHref), UriKind.Absolute, out Uri? callbackUri), "The controller should emit a valid callback URI.");
        Assert.Equal("chummer", callbackUri.Scheme);
        Assert.Equal("install-link", callbackUri.Host);
        Assert.Contains("code=", callbackHref, StringComparison.Ordinal);
        Assert.Contains("installationId=ins-browser-route", callbackHref, StringComparison.Ordinal);
        Assert.Contains("headId=avalonia", callbackHref, StringComparison.Ordinal);
        Assert.Contains("installLinkMode=browser_callback", callbackHref, StringComparison.Ordinal);
        Assert.Contains("installLinkTransport=grant_callback", callbackHref, StringComparison.Ordinal);

        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("ins-browser-route", callback.InstallationId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
        Assert.Contains($"code={Uri.EscapeDataString(callback.CallbackCode)}", callbackHref, StringComparison.Ordinal);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Install_linking_api_success_applies_private_no_store_response_headers()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/api/v1/install-linking/me";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        ActionResult<InstallLinkingSummaryDto> result = await fixture.Controller.GetSummary(CancellationToken.None);

        Assert.IsType<OkObjectResult>(result.Result);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Install_linking_summary_redacts_all_legacy_and_v2_bearers()
    {
        using Fixture fixture = new(authenticated: true);
        InstallationGrantDto legacy = fixture.SeedClaimedInstall(
            "preview10-summary",
            fixture.User.UserId,
            fixture.SubjectId);
        InstallationGrantDto v2 = fixture.SeedClaimedInstall(
            "preview11-summary",
            fixture.User.UserId,
            fixture.SubjectId,
            explicitV2: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.Request.Headers.Authorization = "Bearer account-owner-session";

        ActionResult<InstallLinkingSummaryDto> action =
            await fixture.Controller.GetSummary(CancellationToken.None);

        InstallLinkingSummaryDto summary = Assert.IsType<InstallLinkingSummaryDto>(
            Assert.IsType<OkObjectResult>(action.Result).Value);
        IReadOnlyList<InstallationGrantDto> grants = summary.ActiveGrants
            ?? throw new Xunit.Sdk.XunitException("active grants were missing");
        Assert.Equal(2, grants.Count);
        Assert.All(grants, static grant => Assert.Equal(string.Empty, grant.AccessToken));
        string json = JsonSerializer.Serialize(summary, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        Assert.DoesNotContain(legacy.AccessToken, json, StringComparison.Ordinal);
        Assert.DoesNotContain(v2.AccessToken, json, StringComparison.Ordinal);

        // The owner-authorized Preview10/v2 UI flow uses grant metadata only.
        Assert.All(grants, static grant => Assert.False(string.IsNullOrWhiteSpace(grant.GrantId)));
    }

    [Fact]
    public void Install_linking_api_error_applies_private_no_store_response_headers()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/api/v1/install-linking/redeem";

        ActionResult<RedeemInstallClaimResponseDto> result = fixture.Controller.Redeem(request: null);

        Assert.IsType<BadRequestObjectResult>(result.Result);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Theory]
    [InlineData("http://127.0.0.1:47761/install-link/callback?state=desktop&nonce=callback-proof", "127.0.0.1", "/install-link/callback", true)]
    [InlineData("http://[::1]:47763/install-link/callback?state=desktop", "[::1]", "/install-link/callback", true)]
    [InlineData("http://127.0.0.1:47761/install-link/callback/?state=desktop", "127.0.0.1", "/install-link/callback/", true)]
    [InlineData("https://localhost:47762/install-link/callback", "localhost", "/install-link/callback", false)]
    public async Task Browser_install_link_preserves_app_local_callback_targets(
        string callbackUri,
        string expectedHost,
        string expectedPath,
        bool expectDesktopState)
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-local-callback",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: callbackUri,
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.Equal(StatusCodes.Status200OK, page.StatusCode);
        Assert.Contains("Claim this copy", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Open Chummer to finish linking this install", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Manual callback link", page.Content, StringComparison.Ordinal);
        Assert.Contains("Claim link", page.Content, StringComparison.Ordinal);
        Assert.Contains("Copy claim link", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("iframe", page.Content, StringComparison.Ordinal);
        Assert.True(TryExtractPrimaryHref(page.Content!, out string callbackHref), "The controller should render a manual callback link.");
        string decodedCallbackHref = WebUtility.HtmlDecode(callbackHref);
        Assert.True(Uri.TryCreate(decodedCallbackHref, UriKind.Absolute, out Uri? redirectUri), "The controller should emit a valid app-local callback URI.");
        Assert.Equal(expectedHost, redirectUri.Host);
        Assert.Equal(expectedPath, redirectUri.AbsolutePath);
        Assert.Contains("code=", decodedCallbackHref, StringComparison.Ordinal);
        if (expectDesktopState)
        {
            Assert.Contains("state=desktop", decodedCallbackHref, StringComparison.Ordinal);
            if (callbackUri.Contains("nonce=callback-proof", StringComparison.Ordinal))
            {
                Assert.Contains("nonce=callback-proof", decodedCallbackHref, StringComparison.Ordinal);
            }
        }

        Assert.Contains("installationId=ins-local-callback", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("installLinkMode=browser_callback", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("installLinkTransport=grant_callback", decodedCallbackHref, StringComparison.Ordinal);

        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("ins-local-callback", callback.InstallationId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
    }

    [Fact]
    public async Task Browser_install_link_matches_linux_callback_platform_to_rid_backed_manifest_artifact()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-linux-route",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "linux",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.Contains("installationId=ins-linux-route", page.Content, StringComparison.Ordinal);

        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("avalonia-linux-x64-installer", callback.ArtifactId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
    }

    [Fact]
    public async Task Browser_install_link_matches_windows_callback_platform_to_rid_backed_manifest_artifact()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-windows-rid-route",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.Contains("installationId=ins-windows-rid-route", page.Content, StringComparison.Ordinal);

        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("avalonia-win-x64-installer", callback.ArtifactId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
    }

    [Fact]
    public async Task Browser_install_link_preserves_only_bounded_state_from_app_local_callback()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-authoritative",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "http://127.0.0.1:47761/install-link/callback?state=desktop&accessToken=stale-access&grantId=stale-grant&claimCode=stale-claim&claimTicketId=stale-ticket&ticketId=stale-ticket-id&receiptId=stale-receipt&installedBuildReceiptId=stale-installed-receipt&callbackCode=stale-callback&code=stale-code&unknown=unknown-query-secret#state=desktop-fragment&nonce=fragment-proof&accessToken=fragment-access&unknown=unknown-fragment-secret",
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.True(TryExtractPrimaryHref(page.Content!, out string callbackHref), "The controller should render a manual callback link.");
        string decodedCallbackHref = WebUtility.HtmlDecode(callbackHref);
        Assert.Contains("state=desktop", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("#state=desktop-fragment", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("nonce=fragment-proof", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("code=", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("installationId=ins-authoritative", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-access", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-grant", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-claim", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-ticket", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-ticket-id", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-receipt", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-installed-receipt", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-callback", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-code", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("fragment-access", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("unknown-query-secret", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("unknown-fragment-secret", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("installLinkTransport=grant_callback", decodedCallbackHref, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Browser_install_link_renders_visible_recovery_page_when_artifact_is_missing()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-missing-artifact",
            headId: "unknown-head",
            applicationVersion: "run-20260612-121055",
            releaseChannel: "docker",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.Equal(StatusCodes.Status404NotFound, page.StatusCode);
        Assert.Contains("This install needs a current desktop package", page.Content, StringComparison.Ordinal);
        Assert.Contains("could not match this copy to a current desktop installer", page.Content, StringComparison.Ordinal);
        Assert.Contains("Open downloads", page.Content, StringComparison.Ordinal);
        Assert.Contains("ins-missing-artifact", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("published desktop artifact", page.Content, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("app handoff", page.Content, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Desktop_launch_exchange_accepts_valid_ticket_for_matching_claimed_install()
    {
        using Fixture fixture = new(authenticated: true);
        InstallationGrantDto grant = fixture.SeedClaimedInstall("ins-launch-valid", fixture.User.UserId, fixture.SubjectId);
        AccountDesktopLaunchTicketIssueResult issued = fixture.DesktopLaunchTickets.Issue("character", "dossier-7", fixture.User.UserId, fixture.SubjectId);

        ActionResult<DesktopAccountLaunchExchangeResponseDto> result = fixture.Controller.ExchangeDesktopLaunch(
            new DesktopAccountLaunchExchangeRequestDto(
                InstallationId: "ins-launch-valid",
                AccessToken: grant.AccessToken,
                Ticket: issued.Ticket));

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        DesktopAccountLaunchExchangeResponseDto payload = Assert.IsType<DesktopAccountLaunchExchangeResponseDto>(ok.Value);
        Assert.Equal("character", payload.Kind);
        Assert.Equal("dossier-7", payload.ResourceId);
    }

    [Fact]
    public void Desktop_launch_exchange_rejects_ticket_for_another_identity()
    {
        using Fixture fixture = new(authenticated: true);
        InstallationGrantDto grant = fixture.SeedClaimedInstall("ins-launch-mismatch", fixture.User.UserId, fixture.SubjectId);
        AccountDesktopLaunchTicketIssueResult issued = fixture.DesktopLaunchTickets.Issue("group", "group-4", userId: "someone-else", subjectId: "subject.someone-else");

        ActionResult<DesktopAccountLaunchExchangeResponseDto> result = fixture.Controller.ExchangeDesktopLaunch(
            new DesktopAccountLaunchExchangeRequestDto(
                InstallationId: "ins-launch-mismatch",
                AccessToken: grant.AccessToken,
                Ticket: issued.Ticket));

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status403Forbidden, problem.StatusCode);
        ProblemDetails details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("desktop launch ticket does not belong to this linked install.", details.Detail);
    }

    [Fact]
    public void Desktop_launch_exchange_rejects_invalid_ticket()
    {
        using Fixture fixture = new(authenticated: true);
        InstallationGrantDto grant = fixture.SeedClaimedInstall("ins-launch-invalid", fixture.User.UserId, fixture.SubjectId);

        ActionResult<DesktopAccountLaunchExchangeResponseDto> result = fixture.Controller.ExchangeDesktopLaunch(
            new DesktopAccountLaunchExchangeRequestDto(
                InstallationId: "ins-launch-invalid",
                AccessToken: grant.AccessToken,
                Ticket: "not-a-real-ticket"));

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status400BadRequest, problem.StatusCode);
        ProblemDetails details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("desktop launch ticket is invalid.", details.Detail);
    }

    [Fact]
    public async Task Account_owner_unlink_revokes_explicit_v2_grant_without_legacy_bearer_downgrade()
    {
        using Fixture fixture = new(authenticated: true);
        InstallationGrantDto grant = fixture.SeedClaimedInstall(
            "android-owner-unlink",
            fixture.User.UserId,
            fixture.SubjectId,
            explicitV2: true);
        Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.InstallLinking.RevokeGrant(new RevokeInstallationGrantRequestDto(
                grant.InstallationId,
                grant.AccessToken)));
        AccountsController controller = fixture.CreateAccountsController();
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        controller.Request.Headers.Authorization = "Bearer account-owner-session";

        IActionResult result = await controller.UnlinkInstall(
            grant.InstallationId,
            CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/account/access?accessNotice=unlinked", redirect.Url);
        Assert.Equal(
            ClaimedInstallationStates.Revoked,
            fixture.Store.InstallationsById[grant.InstallationId].Status);
        Assert.Equal(
            InstallationGrantStates.Revoked,
            fixture.Store.GrantsById[grant.GrantId].Status);
    }

    [Fact]
    public async Task Preview10_account_unlink_uses_redacted_grant_metadata_without_page_bearer()
    {
        using Fixture fixture = new(authenticated: true);
        InstallationGrantDto grant = fixture.SeedClaimedInstall(
            "preview10-owner-unlink",
            fixture.User.UserId,
            fixture.SubjectId);
        InstallLinkingSummaryDto summary = fixture.InstallLinking.GetSummary(
            fixture.User.UserId,
            fixture.SubjectId);
        InstallationGrantDto pageGrant = Assert.Single(summary.ActiveGrants!);
        Assert.Equal(string.Empty, pageGrant.AccessToken);
        AccountsController controller = fixture.CreateAccountsController();
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        controller.Request.Headers.Authorization = "Bearer account-owner-session";

        IActionResult result = await controller.UnlinkInstall(
            grant.InstallationId,
            CancellationToken.None);

        Assert.Equal(
            "/account/access?accessNotice=unlinked",
            Assert.IsType<RedirectResult>(result).Url);
        Assert.Equal(
            InstallationGrantStates.Revoked,
            fixture.Store.GrantsById[grant.GrantId].Status);
    }

    [Fact]
    public async Task Account_owner_unlink_cannot_revoke_another_owners_explicit_v2_grant()
    {
        using Fixture fixture = new(authenticated: true);
        InstallationGrantDto grant = fixture.SeedClaimedInstall(
            "android-other-owner",
            "different-user",
            "different-subject",
            explicitV2: true);
        AccountsController controller = fixture.CreateAccountsController();
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        controller.Request.Headers.Authorization = "Bearer account-owner-session";

        IActionResult result = await controller.UnlinkInstall(
            grant.InstallationId,
            CancellationToken.None);

        Assert.IsType<RedirectResult>(result);
        Assert.Equal(
            ClaimedInstallationStates.Active,
            fixture.Store.InstallationsById[grant.InstallationId].Status);
        Assert.Equal(
            InstallationGrantStates.Active,
            fixture.Store.GrantsById[grant.GrantId].Status);
    }

    private static bool TryExtractPrimaryHref(string content, out string href)
    {
        const string classMarker = "class=\"button-like button-like--primary\"";
        int anchorStart = content.IndexOf(classMarker, StringComparison.Ordinal);
        if (anchorStart < 0)
        {
            href = string.Empty;
            return false;
        }

        int hrefMarker = content.IndexOf("href=\"", anchorStart, StringComparison.Ordinal);
        if (hrefMarker < 0)
        {
            href = string.Empty;
            return false;
        }

        int start = hrefMarker + "href=\"".Length;
        int end = content.IndexOf('"', start);
        if (end < 0)
        {
            href = string.Empty;
            return false;
        }

        href = content[start..end];
        return true;
    }

    private static void AssertSensitiveResponseHeaders(IHeaderDictionary headers)
    {
        Assert.Equal("private, no-store, max-age=0", headers.CacheControl.ToString());
        Assert.Equal("no-store, max-age=0", headers["CDN-Cache-Control"].ToString());
        Assert.Equal("no-store, max-age=0", headers["Cloudflare-CDN-Cache-Control"].ToString());
        Assert.Equal("no-store", headers["Surrogate-Control"].ToString());
        Assert.Equal("no-cache", headers.Pragma.ToString());
        Assert.Equal("0", headers.Expires.ToString());
        Assert.Equal("no-referrer", headers["Referrer-Policy"].ToString());
    }

    [Theory]
    [InlineData("revoked")]
    [InlineData("expired")]
    [InlineData("redeemed")]
    [InlineData("redeemed-expired")]
    public async Task Bound_attempt_immediate_retry_uses_distinct_nonce_without_aging_history(string history)
    {
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        AndroidInstallLinkProofPollRequest first = CreateSignedPoll(key, "attempt-immediate", bound: true);
        AssertPending(fixture.Controller.PollBrowserCallback(first));
        await ApproveAttempt(fixture, first);
        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        ExchangeInstallBrowserCallbackResponseDto? accepted = null;
        if (history != "expired")
        {
            accepted = AssertExchange(fixture.Controller.PollBrowserCallback(first));
        }
        if (history == "revoked")
        {
            fixture.InstallLinking.RevokeGrant(new RevokeInstallationGrantRequestDto(
                first.InstallationId, accepted!.Grant.AccessToken));
        }
        if (history is "expired" or "redeemed-expired")
        {
            ExpireAttempt(fixture, callback.CallbackId);
        }
        fixture.ReloadInstallLinking();
        Assert.Equal(callback.CreatedAtUtc, fixture.Store.BrowserCallbacksById[callback.CallbackId].CreatedAtUtc);
        if (history == "redeemed-expired")
        {
            Assert.Equal(InstallBrowserCallbackStates.Redeemed, fixture.Store.BrowserCallbacksById[callback.CallbackId].Status);
        }

        AndroidInstallLinkProofPollRequest second = CreateSignedPoll(key, first.InstallationId, bound: true);
        Assert.NotEqual(first.Nonce, second.Nonce);
        Assert.NotEqual(first.OperationId, second.OperationId);
        AssertPending(fixture.Controller.PollBrowserCallback(second));
        if (history == "redeemed")
        {
            Assert.Equal(accepted!.Grant, AssertExchange(fixture.Controller.PollBrowserCallback(first)).Grant);
        }
        else
        {
            int expected = history == "revoked" ? StatusCodes.Status409Conflict : StatusCodes.Status410Gone;
            AssertPollProblem(fixture.Controller.PollBrowserCallback(first with { AttemptStartedAtUnixSeconds = long.MaxValue }), expected);
            ObjectResult repeatedApproval = Assert.IsType<ObjectResult>(await ApproveAttempt(fixture, first, expectSuccess: false));
            Assert.Equal(expected, repeatedApproval.StatusCode);
        }

        await ApproveAttempt(fixture, second);
        fixture.ReloadInstallLinking();
        ExchangeInstallBrowserCallbackResponseDto linked = AssertExchange(fixture.Controller.PollBrowserCallback(second));
        Assert.False(linked.AlreadyClaimed);
        Assert.NotEqual(callback.CallbackId, linked.Callback.CallbackId);
        Assert.NotEqual(accepted?.Grant.GrantId, linked.Grant.GrantId);
        Assert.Equal(2, fixture.Store.BrowserCallbacksById.Count);
        Assert.Equal(second.OperationId, fixture.Store.BrowserCallbackRedemptionReceiptsByCallbackId[linked.Callback.CallbackId].OperationId);
        AssertPollProblem(fixture.Controller.PollBrowserCallback(first),
            history is "expired" or "redeemed-expired" ? StatusCodes.Status410Gone : StatusCodes.Status409Conflict);
        Assert.Equal(linked.Grant.GrantId, fixture.Store.InstallationsById[first.InstallationId].GrantId);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Theory]
    [InlineData(false, 0L)]
    [InlineData(false, long.MaxValue)]
    [InlineData(false, long.MinValue)]
    [InlineData(true, 0L)]
    [InlineData(true, long.MaxValue)]
    [InlineData(true, long.MinValue)]
    public async Task Advisory_attempt_timestamp_cannot_hide_current_revocation(bool bound, long advisory)
    {
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        AndroidInstallLinkProofPollRequest poll = CreateSignedPoll(key, "attempt-advisory", bound);
        await ApproveAttempt(fixture, poll);
        ExchangeInstallBrowserCallbackResponseDto accepted = AssertExchange(fixture.Controller.PollBrowserCallback(poll));
        fixture.InstallLinking.RevokeGrant(new RevokeInstallationGrantRequestDto(poll.InstallationId, accepted.Grant.AccessToken));
        fixture.ReloadInstallLinking();

        AssertPollProblem(fixture.Controller.PollBrowserCallback(poll with { AttemptStartedAtUnixSeconds = advisory }),
            StatusCodes.Status409Conflict);
        // Omitting the new field cannot turn the same signed operation into a new attempt.
        AssertPollProblem(fixture.Controller.PollBrowserCallback(poll with { OperationId = null, AttemptStartedAtUnixSeconds = advisory }),
            StatusCodes.Status409Conflict);
        Assert.Single(fixture.Store.GrantsById);
        Assert.Equal(InstallationGrantStates.Revoked, fixture.Store.GrantsById[accepted.Grant.GrantId].Status);
    }

    [Theory]
    [InlineData("key")]
    [InlineData("signature")]
    [InlineData("transport")]
    [InlineData("operation")]
    [InlineData("nonce")]
    public async Task Fresh_bound_poll_authenticates_before_returning_pending(string attack)
    {
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        using RSA otherKey = RSA.Create(2048);
        AndroidInstallLinkProofPollRequest first = CreateSignedPoll(key, "attempt-auth", bound: attack != "transport");
        if (attack == "transport")
        {
            // Use the real service boundary to record a different transport.
            fixture.InstallLinking.IssueBrowserCallback(
                CreateProofApproval(key) with { InstallationId = first.InstallationId },
                "user.transport", "subject.install.browser", InstallLinkingService.AndroidLinkedV2ProofPollTransport);
        }
        else
        {
            await ApproveAttempt(fixture, first);
            ExchangeInstallBrowserCallbackResponseDto accepted = AssertExchange(fixture.Controller.PollBrowserCallback(first));
            fixture.InstallLinking.RevokeGrant(new RevokeInstallationGrantRequestDto(first.InstallationId, accepted.Grant.AccessToken));
        }
        AndroidInstallLinkProofPollRequest fresh = CreateSignedPoll(
            attack == "key" ? otherKey : key, first.InstallationId, bound: true);
        if (attack == "signature")
        {
            fresh = fresh with { Signature = CreateSignedPoll(otherKey, first.InstallationId, bound: true).Signature };
        }
        if (attack == "operation")
        {
            fresh = fresh with { OperationId = first.OperationId };
        }
        if (attack == "nonce")
        {
            fresh = fresh with { Nonce = first.Nonce, OperationId = first.OperationId };
        }
        int grantCount = fixture.Store.GrantsById.Count;
        if (attack is "key" or "transport")
        {
            // R69: a fresh, authenticated operation is not terminated by another
            // operation's history. The signature is valid (authentication happened
            // above); a historical callback with a different key or transport
            // describes a different operation and must not answer this poll.
            AssertPending(fixture.Controller.PollBrowserCallback(fresh with { AttemptStartedAtUnixSeconds = long.MaxValue }));
        }
        else
        {
            AssertPollProblem(fixture.Controller.PollBrowserCallback(fresh with { AttemptStartedAtUnixSeconds = long.MaxValue }),
                attack == "operation" ? StatusCodes.Status400BadRequest : StatusCodes.Status409Conflict);
        }
        Assert.Equal(grantCount, fixture.Store.GrantsById.Count);
    }

    [Fact]
    public void Bound_poll_with_no_history_still_requires_valid_signature()
    {
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        using RSA otherKey = RSA.Create(2048);
        AndroidInstallLinkProofPollRequest poll = CreateSignedPoll(key, "attempt-no-history", bound: true);
        poll = poll with { Signature = CreateSignedPoll(otherKey, poll.InstallationId, bound: true).Signature };
        AssertPollProblem(fixture.Controller.PollBrowserCallback(poll), StatusCodes.Status409Conflict);
        Assert.Empty(fixture.Store.GrantsById);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Uncertain_original_completion_reconciles_its_receipt_across_new_approval_and_reload(bool originalBound)
    {
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        AndroidInstallLinkProofPollRequest first = CreateSignedPoll(key, "attempt-uncertain", originalBound);
        await ApproveAttempt(fixture, first);
        ExchangeInstallBrowserCallbackResponseDto original = AssertExchange(fixture.Controller.PollBrowserCallback(first));
        AndroidInstallLinkProofPollRequest second = CreateSignedPoll(key, first.InstallationId, bound: true);
        Assert.NotEqual(first.Nonce, second.Nonce);
        Assert.NotEqual(ProofOperationId(first.Nonce), second.OperationId);
        await ApproveAttempt(fixture, second);
        fixture.ReloadInstallLinking();

        ExchangeInstallBrowserCallbackResponseDto recovered = AssertExchange(fixture.Controller.PollBrowserCallback(first));
        Assert.True(recovered.AlreadyClaimed);
        Assert.Equal(original.Callback.CallbackId, recovered.Callback.CallbackId);
        Assert.Equal(original.Grant, recovered.Grant);
        Assert.Single(fixture.Store.GrantsById);
        // Retention clears a redeemed callback URI. Reopening cannot substitute a
        // new URI or approval; recovery is the authenticated poll above.
        ObjectResult reopen = Assert.IsType<ObjectResult>(await ApproveAttempt(
            fixture, first with { OperationId = ProofOperationId(first.Nonce) }, expectSuccess: false));
        Assert.Equal(StatusCodes.Status409Conflict, reopen.StatusCode);
        Assert.Equal(2, fixture.Store.BrowserCallbacksById.Count);
        // A valid re-sign with a changed timestamp is not the immutable accepted operation.
        AndroidInstallLinkProofPollRequest rewritten = CreateSignedPoll(
            key, first.InstallationId, originalBound, first.Nonce, first.IssuedAtUnixSeconds + 1);
        AssertPollProblem(fixture.Controller.PollBrowserCallback(rewritten), StatusCodes.Status409Conflict);

        ExchangeInstallBrowserCallbackResponseDto replacement = AssertExchange(fixture.Controller.PollBrowserCallback(second));
        Assert.NotEqual(original.Grant.GrantId, replacement.Grant.GrantId);
        fixture.ReloadInstallLinking();
        AssertPollProblem(fixture.Controller.PollBrowserCallback(first), StatusCodes.Status409Conflict);
        Assert.Equal(replacement.Grant.GrantId, fixture.Store.InstallationsById[first.InstallationId].GrantId);
        Assert.Equal(2, fixture.Store.GrantsById.Count);
    }

    [Fact]
    public async Task Bound_approval_is_idempotent_and_rejects_changes_to_account_target_key_or_callback()
    {
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        using RSA otherKey = RSA.Create(2048);
        AndroidInstallLinkProofPollRequest poll = CreateSignedPoll(key, "attempt-binding", bound: true);
        await ApproveAttempt(fixture, poll);
        await ApproveAttempt(fixture, poll);
        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        IssueInstallBrowserCallbackRequestDto request = CreateProofApproval(key) with { InstallationId = poll.InstallationId };
        foreach (var changed in new[]
        {
            request with { PublicKey = Convert.ToBase64String(otherKey.ExportSubjectPublicKeyInfo()) },
            request with { Arch = "arm64" },
            request with { CallbackUri = "chummer://install-link?state=other" }
        })
        {
            Assert.Equal(StatusCodes.Status409Conflict, Assert.Throws<InstallLinkingOperationException>(() =>
                fixture.InstallLinking.IssueBrowserCallback(changed, callback.UserId, callback.SubjectId,
                    InstallLinkingService.LegacyProofPollTransport, poll.OperationId)).StatusCode);
        }
        foreach (var identity in new[] { ("other-user", callback.SubjectId), (callback.UserId, "other-subject") })
        {
            Assert.Equal(StatusCodes.Status409Conflict, Assert.Throws<InstallLinkingOperationException>(() =>
                fixture.InstallLinking.IssueBrowserCallback(request, identity.Item1, identity.Item2,
                    InstallLinkingService.LegacyProofPollTransport, poll.OperationId)).StatusCode);
        }
        Assert.Single(fixture.Store.BrowserCallbacksById);
        Assert.Empty(fixture.Store.GrantsById);
    }

    [Fact]
    public async Task Omitted_operation_cannot_consume_another_bound_approval()
    {
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        AndroidInstallLinkProofPollRequest bound = CreateSignedPoll(key, "attempt-omitted", bound: true);
        await ApproveAttempt(fixture, bound);
        AndroidInstallLinkProofPollRequest other = CreateSignedPoll(key, bound.InstallationId, bound: false);
        AssertPollProblem(fixture.Controller.PollBrowserCallback(other), StatusCodes.Status409Conflict);
        Assert.Empty(fixture.Store.GrantsById);
        AssertExchange(fixture.Controller.PollBrowserCallback(bound));
    }

    [Fact]
    public async Task Definitive_pending_allows_fresh_proof_with_stable_attempt_nonce_but_receipt_stays_immutable()
    {
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        AndroidInstallLinkProofPollRequest pending = CreateSignedPoll(key, "attempt-refresh", bound: true);
        AssertPending(fixture.Controller.PollBrowserCallback(pending));
        AndroidInstallLinkProofPollRequest refreshed = CreateSignedPoll(
            key, pending.InstallationId, bound: true, pending.Nonce, pending.IssuedAtUnixSeconds + 1);
        Assert.Equal(pending.Nonce, refreshed.Nonce);
        Assert.Equal(pending.OperationId, refreshed.OperationId);
        Assert.NotEqual(pending.Signature, refreshed.Signature);
        AssertPending(fixture.Controller.PollBrowserCallback(refreshed));
        await ApproveAttempt(fixture, pending);
        ExchangeInstallBrowserCallbackResponseDto accepted = AssertExchange(fixture.Controller.PollBrowserCallback(refreshed));
        fixture.ReloadInstallLinking();
        Assert.Equal(accepted.Grant, AssertExchange(fixture.Controller.PollBrowserCallback(refreshed)).Grant);
        AssertPollProblem(fixture.Controller.PollBrowserCallback(pending), StatusCodes.Status409Conflict);
        Assert.Single(fixture.Store.GrantsById);
    }

    [Theory]
    [InlineData("", "proof_poll")]
    [InlineData("short", "proof_poll")]
    [InlineData("0123456789abcdef0123456789abcdef", "proof_poll_v2")]
    [InlineData("0123456789abcdef0123456789abcdef", null)]
    public async Task Browser_approval_rejects_invalid_operation_binding(string operationId, string? transport)
    {
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        ObjectResult result = Assert.IsType<ObjectResult>(await fixture.Controller.BrowserInstallLink(
            "attempt-invalid", "avalonia", "6.0.1-preview", "preview", "windows", "x64",
            "chummer://install-link", CancellationToken.None, transport,
            Convert.ToBase64String(key.ExportSubjectPublicKeyInfo()), operationId));
        Assert.Equal(StatusCodes.Status400BadRequest, result.StatusCode);
        Assert.Empty(fixture.Store.BrowserCallbacksById);
    }

    [Fact]
    public async Task Browser_approval_rejects_empty_or_duplicate_query_before_issuing_legacy_approval()
    {
        using Fixture fixture = new(authenticated: true);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        AndroidInstallLinkProofPollRequest poll = CreateSignedPoll(key, "attempt-query", bound: true);
        foreach (string query in new[]
        {
            "?installLinkOperationId=",
            $"?installLinkOperationId={poll.OperationId}&installLinkOperationId={poll.OperationId}"
        })
        {
            fixture.Controller.Request.QueryString = new QueryString(query);
            ObjectResult result = Assert.IsType<ObjectResult>(await ApproveAttempt(
                fixture, poll with { OperationId = null }, expectSuccess: false));
            Assert.Equal(StatusCodes.Status400BadRequest, result.StatusCode);
        }
        Assert.Empty(fixture.Store.BrowserCallbacksById);
    }

    [Fact]
    public async Task Bound_browser_login_return_preserves_operation_and_state()
    {
        using Fixture fixture = new(authenticated: false);
        ConfigureAttemptController(fixture);
        using RSA key = RSA.Create(2048);
        AndroidInstallLinkProofPollRequest poll = CreateSignedPoll(key, "attempt-login", bound: true);
        RedirectResult redirect = Assert.IsType<RedirectResult>(
            await ApproveAttempt(fixture, poll, expectSuccess: false, callbackUri: "chummer://install-link?state=attempt-state"));
        var login = Microsoft.AspNetCore.WebUtilities.QueryHelpers.ParseQuery(new Uri("https://chummer.run" + redirect.Url).Query);
        string next = HubBrowserAuthService.SanitizeNextPath(Assert.Single(login["next"]), "/safe");
        var query = Microsoft.AspNetCore.WebUtilities.QueryHelpers.ParseQuery(new Uri("https://chummer.run" + next).Query);
        Assert.Equal(poll.OperationId, Assert.Single(query["installLinkOperationId"]));
        Assert.Equal(new Uri("chummer://install-link?state=attempt-state").AbsoluteUri, Assert.Single(query["installLinkCallbackUri"]));
        Assert.Empty(fixture.Store.BrowserCallbacksById);
    }

    private static void ConfigureAttemptController(Fixture fixture)
    {
        fixture.Controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        fixture.Controller.Request.Path = "/account/access/install-link";
        fixture.Controller.Request.Headers.Authorization = "Bearer desktop-access-token";
    }

    private static async Task<IActionResult> ApproveAttempt(
        Fixture fixture, AndroidInstallLinkProofPollRequest poll, bool expectSuccess = true,
        string callbackUri = "chummer://install-link")
    {
        IActionResult result = await fixture.Controller.BrowserInstallLink(
            poll.InstallationId, poll.HeadId, poll.ApplicationVersion, poll.ChannelId, poll.Platform, poll.Arch,
            callbackUri, CancellationToken.None, InstallLinkingService.LegacyProofPollTransport, poll.PublicKey, poll.OperationId);
        if (expectSuccess)
        {
            Assert.Equal(StatusCodes.Status200OK, Assert.IsType<ContentResult>(result).StatusCode);
        }
        return result;
    }

    private static void ExpireAttempt(Fixture fixture, string callbackId)
    {
        lock (fixture.Store.Gate)
        {
            InstallBrowserCallbackDto callback = fixture.Store.BrowserCallbacksById[callbackId];
            // Exercise expiry itself; never age CreatedAt to manufacture attempt separation.
            fixture.Store.BrowserCallbacksById[callbackId] = callback with { ExpiresAtUtc = callback.CreatedAtUtc };
            fixture.Store.PersistLocked();
        }
    }

    private static void AssertPending(ActionResult<ExchangeInstallBrowserCallbackResponseDto> result)
    {
        AcceptedResult accepted = Assert.IsType<AcceptedResult>(result.Result);
        AndroidInstallLinkProofPollStatus status = Assert.IsType<AndroidInstallLinkProofPollStatus>(accepted.Value);
        Assert.Equal(InstallBrowserCallbackStates.Pending, status.State);
        Assert.False(status.Terminal);
        Assert.False(status.Completed);
    }

    private static void AssertPollProblem(ActionResult<ExchangeInstallBrowserCallbackResponseDto> result, int expected)
        => Assert.Equal(expected, Assert.IsType<ObjectResult>(result.Result).StatusCode);

    private static ExchangeInstallBrowserCallbackResponseDto AssertExchange(
        ActionResult<ExchangeInstallBrowserCallbackResponseDto> result)
        => Assert.IsType<ExchangeInstallBrowserCallbackResponseDto>(Assert.IsType<OkObjectResult>(result.Result).Value);

    private static string ProofOperationId(string nonce)
        => Convert.ToBase64String(SHA256.HashData(Encoding.UTF8.GetBytes(nonce)).AsSpan(0, 24))
            .TrimEnd('=').Replace('+', '-').Replace('/', '_');

    private static AndroidInstallLinkProofPollRequest CreateSignedPoll(
        RSA key, string installationId, bool bound, string? nonce = null, long? issuedAtUnixSeconds = null)
    {
        long issuedAt = issuedAtUnixSeconds ?? DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        nonce ??= Guid.NewGuid().ToString("N");
        byte[] proof = Encoding.UTF8.GetBytes(string.Join('\n',
            "chummer.install-link.remote-callback.v1", installationId, "avalonia",
            "6.0.1-preview", "preview", "windows", "x64",
            issuedAt.ToString(System.Globalization.CultureInfo.InvariantCulture), nonce));
        try
        {
            return new AndroidInstallLinkProofPollRequest(
                installationId, "avalonia", "6.0.1-preview", "preview", "windows", "x64",
                Convert.ToBase64String(key.ExportSubjectPublicKeyInfo()), issuedAt, nonce,
                Convert.ToBase64String(key.SignData(proof, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1)),
                OperationId: bound ? ProofOperationId(nonce) : null);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(proof);
        }
    }

    private static IssueInstallBrowserCallbackRequestDto CreateProofApproval(RSA key)
        => new(
            InstallationId: "desktop-proof-repair-install",
            ArtifactId: "avalonia-win-x64-installer",
            ApplicationVersion: "6.0.1-preview",
            ChannelId: "preview",
            HeadId: "avalonia",
            Platform: "windows",
            Arch: "x64",
            CallbackUri: "chummer://install-link",
            PublicKey: Convert.ToBase64String(key.ExportSubjectPublicKeyInfo()),
            HostLabel: null,
            InstallAccessClass: InstallAccessClasses.AccountRequired);

    private static AndroidInstallLinkProofPollRequest SignProofPoll(
        RSA key, IssueInstallBrowserCallbackRequestDto approval, string nonce = "0123456789abcdef0123456789abcdef")
    {
        long issuedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        byte[] proof = Encoding.UTF8.GetBytes(string.Join('\n',
            "chummer.install-link.remote-callback.v1", approval.InstallationId, approval.HeadId,
            approval.ApplicationVersion, approval.ChannelId, approval.Platform, approval.Arch,
            issuedAt.ToString(System.Globalization.CultureInfo.InvariantCulture), nonce));
        try
        {
            return new AndroidInstallLinkProofPollRequest(
                approval.InstallationId, approval.HeadId!, approval.ApplicationVersion!, approval.ChannelId!,
                approval.Platform!, approval.Arch!, approval.PublicKey!, issuedAt, nonce,
                Convert.ToBase64String(key.SignData(proof, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1)), approval.HostLabel);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(proof);
        }
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;
        private readonly IConfiguration _configuration;
        private readonly IDataProtectionProvider _dataProtection;

        public Fixture(bool authenticated)
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-install-link-controller-tests", Guid.NewGuid().ToString("N"));
            string downloadsRoot = Path.Combine(_root, "downloads");
            Directory.CreateDirectory(downloadsRoot);
            File.WriteAllText(
                Path.Combine(downloadsRoot, "releases.json"),
                """
                {
                  "version": "6.0.1-preview",
                  "channel": "preview",
                  "publishedAt": "2026-04-15T08:00:00Z",
                  "downloads": [
                    {
                      "id": "avalonia-linux-x64-installer",
                      "platform": "Avalonia Desktop Linux x64 Installer",
                      "url": "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                      "sha256": "c3",
                      "sizeBytes": 303,
                      "head": "avalonia",
                      "platformId": "linux-x64",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-avalonia-linux-x64-installer.deb",
                      "installAccessClass": "open_public"
                    },
                    {
                      "id": "avalonia-win-x64-installer",
                      "platform": "Avalonia Desktop Windows x64 Installer",
                      "url": "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                      "sha256": "d4",
                      "sizeBytes": 404,
                      "head": "avalonia",
                      "platformId": "win-x64",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-avalonia-win-x64-installer.exe",
                      "installAccessClass": "account_required"
                    },
                    {
                      "id": "blazor-desktop-win-x64-installer",
                      "platform": "Blazor Desktop Windows x64 Installer",
                      "url": "/downloads/files/chummer-blazor-desktop-win-x64-installer.exe",
                      "sha256": "e5",
                      "sizeBytes": 505,
                      "head": "blazor-desktop",
                      "platformId": "windows",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-blazor-desktop-win-x64-installer.exe",
                      "installAccessClass": "account_required"
                    }
                  ]
                }
                """);

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot,
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking-store.json"),
                    ["CHUMMER_INSTALL_BROWSER_CALLBACK_LIFETIME_MINUTES"] = "15",
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.example"
                })
                .Build();

            HubIdentityClient identity = new(
                new HttpClient(new IdentityHandler(authenticated))
                {
                    BaseAddress = new Uri("http://identity.example")
                },
                configuration,
                NullLogger<HubIdentityClient>.Instance);
            CommunityStore communityStore = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(communityStore);
            IDataProtectionProvider dataProtection = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            _configuration = configuration;
            _dataProtection = dataProtection;
            InstallLinkingStore installLinkingStore = new(
                configuration,
                dataProtection,
                NullLogger<InstallLinkingStore>.Instance);
            AccountDesktopLaunchTicketService desktopLaunchTickets = new(dataProtection, configuration);

            Identity = identity;
            Accounts = accounts;
            Store = installLinkingStore;
            InstallLinking = new InstallLinkingService(installLinkingStore, configuration);
            Releases = new PublicReleaseManifestService(configuration);
            DesktopLaunchTickets = desktopLaunchTickets;
            Controller = new InstallLinkingController(
                identity,
                accounts,
                InstallLinking,
                desktopLaunchTickets,
                Releases,
                supportCases: null!,
                supportPresentation: new SupportCasePresentationService(),
                configuration);

            if (authenticated)
            {
                User = accounts.EnsureUser(SubjectId, "Archon", "archon@example.com");
            }
        }

        public string SubjectId { get; } = "subject.install.browser";

        public HubIdentityClient Identity { get; }

        public AccountService Accounts { get; }

        public InstallLinkingStore Store { get; private set; }

        public InstallLinkingService InstallLinking { get; private set; }

        public PublicReleaseManifestService Releases { get; }

        public AccountDesktopLaunchTicketService DesktopLaunchTickets { get; }

        public InstallLinkingController Controller { get; private set; }

        public void ReloadInstallLinking()
        {
            ControllerContext context = Controller.ControllerContext;
            Store.Dispose();
            Store = new InstallLinkingStore(_configuration, _dataProtection, NullLogger<InstallLinkingStore>.Instance);
            InstallLinking = new InstallLinkingService(Store, _configuration);
            Controller = new InstallLinkingController(
                Identity, Accounts, InstallLinking, DesktopLaunchTickets, Releases,
                supportCases: null!, supportPresentation: new SupportCasePresentationService(), _configuration)
            {
                ControllerContext = context
            };
        }

        public Chummer.Run.Contracts.Community.HubUserDto User { get; private set; } = null!;

        public AccountsController CreateAccountsController()
        {
            System.Reflection.ConstructorInfo constructor = Assert.Single(
                typeof(AccountsController).GetConstructors());
            object?[] arguments = constructor.GetParameters()
                .Select(parameter =>
                {
                    if (parameter.ParameterType == typeof(AccountService))
                    {
                        return (object?)Accounts;
                    }
                    if (parameter.ParameterType == typeof(HubIdentityClient))
                    {
                        return Identity;
                    }
                    if (parameter.ParameterType == typeof(InstallLinkingService))
                    {
                        return InstallLinking;
                    }
                    return parameter.ParameterType == typeof(ILogger<AccountsController>)
                        ? NullLogger<AccountsController>.Instance
                        : null;
                })
                .ToArray();
            return Assert.IsType<AccountsController>(constructor.Invoke(arguments));
        }

        public InstallationGrantDto SeedClaimedInstall(
            string installationId,
            string userId,
            string? subjectId,
            bool explicitV2 = false)
        {
            lock (Store.Gate)
            {
                DateTimeOffset now = DateTimeOffset.UtcNow;
                InstallationGrantDto grant = new(
                    GrantId: $"grant-{installationId}",
                    InstallationId: installationId,
                    Status: InstallationGrantStates.Active,
                    AccessToken: $"access-{installationId}",
                    IssuedAtUtc: now.AddMinutes(-5),
                    ExpiresAtUtc: now.AddHours(8),
                    UserId: userId,
                    SubjectId: subjectId);
                ClaimedInstallationDto installation = new(
                    InstallationId: installationId,
                    ArtifactId: "avalonia-win-x64-installer",
                    Channel: "preview",
                    Version: "6.0.1-preview",
                    InstallAccessClass: InstallAccessClasses.AccountRequired,
                    Status: ClaimedInstallationStates.Active,
                    CreatedAtUtc: now.AddHours(-1),
                    UpdatedAtUtc: now,
                    UserId: userId,
                    SubjectId: subjectId,
                    PublicKey: "public-key",
                    ClaimTicketId: $"ticket-{installationId}",
                    HeadId: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    HostLabel: "Test host",
                    GrantId: grant.GrantId);
                Store.InstallationsById[installationId] = installation;
                Store.GrantsById[grant.GrantId] = grant;
                if (explicitV2)
                {
                    Store.GrantTransportAuthoritiesByGrantId[grant.GrantId] =
                        new InstallationGrantTransportAuthority(
                            grant.GrantId,
                            InstallationGrantTransports.AndroidLinkedV2);
                }
                Store.PersistLocked();
                return grant;
            }
        }

        public void Dispose()
        {
            // Release the writer lease before deleting the store directory; the
            // store holds an exclusive lock for its lifetime on Windows.
            Store.Dispose();
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class IdentityHandler : HttpMessageHandler
    {
        private readonly bool _authenticated;

        public IdentityHandler(bool authenticated)
        {
            _authenticated = authenticated;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (!_authenticated)
            {
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.Unauthorized)
                {
                    Content = new StringContent(string.Empty, Encoding.UTF8, "application/json")
                });
            }

            if (request.RequestUri?.AbsolutePath.EndsWith("/api/v1/identity/introspect", StringComparison.Ordinal) == true)
            {
                return Task.FromResult(JsonResponse(new IdentityIntrospectionResponse(
                    Active: true,
                    SessionId: "session-123",
                    SubjectId: "subject.install.browser",
                    Roles: ["user"],
                    ExpiresAtUtc: DateTimeOffset.UtcNow.AddHours(1))));
            }

            if (request.RequestUri?.AbsolutePath.EndsWith("/api/v1/identity/subjects/subject.install.browser", StringComparison.Ordinal) == true)
            {
                return Task.FromResult(JsonResponse(new IdentitySubjectResponse(
                    SubjectId: "subject.install.browser",
                    DisplayName: "Archon",
                    Email: "archon@example.com",
                    Roles: ["user"],
                    UpdatedAtUtc: DateTimeOffset.UtcNow)));
            }

            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
        }

        private static HttpResponseMessage JsonResponse<T>(T payload)
            => new(HttpStatusCode.OK)
            {
                Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json")
            };
    }
}
