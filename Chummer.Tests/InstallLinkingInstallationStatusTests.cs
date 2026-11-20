using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingInstallationStatusTests
{
    [Fact]
    public void Recovery_returns_only_current_legacy_grant_without_issuing_another()
    {
        using Fixture fixture = new();
        InstallationGrantDto orphan = fixture.Grant with
        {
            GrantId = "newer-orphan",
            AccessToken = "different-orphan-token",
            IssuedAtUtc = DateTimeOffset.UtcNow
        };
        fixture.Store.GrantsById[orphan.GrantId] = orphan;
        int callbackCount = fixture.Store.BrowserCallbacksById.Count;
        AndroidInstallLinkProofPollRequest request = fixture.Request();

        InstallLinkingInstallationStatusDto result = fixture.Service.ResolveInstallationStatus(request);
        InstallLinkingInstallationStatusDto repeated = fixture.Service.ResolveInstallationStatus(request);

        Assert.True(result.Linked);
        Assert.Equal(fixture.Installation, result.Installation);
        Assert.Equal(fixture.Grant, result.Grant);
        Assert.Equal(result, repeated);
        Assert.Equal(2, fixture.Store.GrantsById.Count);
        Assert.Equal(callbackCount, fixture.Store.BrowserCallbacksById.Count);
    }

    [Theory]
    [InlineData("head")]
    [InlineData("version")]
    [InlineData("channel")]
    [InlineData("platform")]
    [InlineData("arch")]
    public void Valid_signature_for_another_target_does_not_recover_credentials(string field)
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollRequest request = fixture.Request();
        request = field switch
        {
            "head" => request with { HeadId = "another-head" },
            "version" => request with { ApplicationVersion = "another-version" },
            "channel" => request with { ChannelId = "another-channel" },
            "platform" => request with { Platform = "another-platform" },
            "arch" => request with { Arch = "another-arch" },
            _ => throw new ArgumentOutOfRangeException(nameof(field))
        };

        AssertNotLinked(fixture.Service.ResolveInstallationStatus(fixture.Sign(request)));
    }

    [Fact]
    public void Public_key_comparison_preserves_base64_case()
    {
        using Fixture fixture = new();
        string publicKey = fixture.Installation.PublicKey!;
        char first = publicKey[0];
        Assert.True(char.IsAsciiLetter(first));
        string differentKey = (char.IsUpper(first) ? char.ToLowerInvariant(first) : char.ToUpperInvariant(first))
            + publicKey[1..];
        fixture.Store.InstallationsById[Fixture.InstallationId] = fixture.Installation with { PublicKey = differentKey };

        AssertNotLinked(fixture.Service.ResolveInstallationStatus(fixture.Request()));
    }

    [Theory]
    [InlineData("missing-current")]
    [InlineData("missing-grant")]
    [InlineData("other-installation")]
    [InlineData("other-user")]
    [InlineData("other-subject")]
    [InlineData("missing-user")]
    [InlineData("missing-subject")]
    [InlineData("revoked-installation")]
    [InlineData("revoked-grant")]
    [InlineData("expired-grant")]
    [InlineData("empty-token")]
    [InlineData("future-grant")]
    [InlineData("android-v2")]
    public void Recovery_refuses_unusable_or_unbound_grant_with_neutral_response(string defect)
    {
        using Fixture fixture = new();
        ClaimedInstallationDto installation = fixture.Installation;
        InstallationGrantDto grant = fixture.Grant;
        switch (defect)
        {
            case "missing-current": installation = installation with { GrantId = null }; break;
            case "missing-grant": installation = installation with { GrantId = "missing" }; break;
            case "other-installation": grant = grant with { InstallationId = "another-installation" }; break;
            case "other-user": grant = grant with { UserId = "another-user" }; break;
            case "other-subject": grant = grant with { SubjectId = "another-subject" }; break;
            case "missing-user":
                installation = installation with { UserId = string.Empty };
                grant = grant with { UserId = string.Empty };
                break;
            case "missing-subject":
                installation = installation with { SubjectId = string.Empty };
                grant = grant with { SubjectId = string.Empty };
                break;
            case "revoked-installation": installation = installation with { Status = ClaimedInstallationStates.Revoked }; break;
            case "revoked-grant": grant = grant with { Status = InstallationGrantStates.Revoked }; break;
            case "expired-grant":
                grant = grant with
                {
                    IssuedAtUtc = DateTimeOffset.UtcNow.AddMinutes(-2),
                    ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(-1)
                };
                break;
            case "empty-token": grant = grant with { AccessToken = string.Empty }; break;
            case "future-grant": grant = grant with { IssuedAtUtc = DateTimeOffset.UtcNow.AddMinutes(1) }; break;
            case "android-v2":
                fixture.Store.GrantTransportAuthoritiesByGrantId[grant.GrantId] =
                    new InstallationGrantTransportAuthority(grant.GrantId, InstallationGrantTransports.AndroidLinkedV2);
                break;
            default: throw new ArgumentOutOfRangeException(nameof(defect));
        }
        fixture.Store.InstallationsById[Fixture.InstallationId] = installation;
        fixture.Store.GrantsById[grant.GrantId] = grant;

        AssertNotLinked(fixture.Service.ResolveInstallationStatus(fixture.Request()));
    }

    [Fact]
    public void Altered_signed_target_is_rejected()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollRequest request = fixture.Request() with { HeadId = "tampered" };

        InstallLinkingOperationException exception = Assert.Throws<InstallLinkingOperationException>(
            () => fixture.Service.ResolveInstallationStatus(request));

        Assert.Equal(StatusCodes.Status409Conflict, exception.StatusCode);
    }

    [Fact]
    public void Nonce_bound_operation_id_recovers_current_grant()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollRequest request = fixture.Sign(fixture.Request() with
        {
            Nonce = "status-recovery-proof-001",
            OperationId = "I8A-OY5Hh6zcqHRIY7I60QW-8YrI_rux"
        });

        InstallLinkingInstallationStatusDto result = fixture.Service.ResolveInstallationStatus(request);

        Assert.True(result.Linked);
        Assert.Equal(fixture.Grant, result.Grant);
    }

    [Theory]
    [InlineData("unbound-operation-id")]
    [InlineData("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")]
    public void Unbound_operation_id_is_rejected(string operationId)
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollRequest request = fixture.Request() with { OperationId = operationId };

        InstallLinkingOperationException exception = Assert.Throws<InstallLinkingOperationException>(
            () => fixture.Service.ResolveInstallationStatus(request));

        Assert.Equal(StatusCodes.Status400BadRequest, exception.StatusCode);
    }

    [Theory]
    [InlineData(-86400)]
    [InlineData(86400)]
    public void Expired_or_future_proof_is_rejected(long offset)
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollRequest request = fixture.Sign(fixture.Request() with
        {
            IssuedAtUnixSeconds = DateTimeOffset.UtcNow.ToUnixTimeSeconds() + offset
        });

        InstallLinkingOperationException exception = Assert.Throws<InstallLinkingOperationException>(
            () => fixture.Service.ResolveInstallationStatus(request));

        Assert.Equal(StatusCodes.Status400BadRequest, exception.StatusCode);
    }

    private static void AssertNotLinked(InstallLinkingInstallationStatusDto result)
    {
        Assert.False(result.Linked);
        Assert.Null(result.Installation);
        Assert.Null(result.Grant);
    }

    private sealed class Fixture : IDisposable
    {
        public const string InstallationId = "installation-status-test";
        private readonly string _root = Path.Combine(Path.GetTempPath(), "chummer-install-status", Guid.NewGuid().ToString("N"));
        private readonly RSA _key = RSA.Create(2048);
        private readonly IDataProtectionProvider _protection;

        public Fixture()
        {
            Directory.CreateDirectory(_root);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "store.json")
                })
                .Build();
            _protection = DataProtectionProvider.Create(Path.Combine(_root, "keys"));
            Store = new InstallLinkingStore(configuration, _protection, NullLogger<InstallLinkingStore>.Instance);
            Service = new InstallLinkingService(Store, configuration);
            string publicKey = Convert.ToBase64String(_key.ExportSubjectPublicKeyInfo());
            IssueInstallBrowserCallbackResponseDto issued = Service.IssueBrowserCallback(
                new IssueInstallBrowserCallbackRequestDto(InstallationId, "avalonia-win-x64-installer", "6.0.1-preview",
                    "preview", "avalonia", "windows", "x64", "chummer://install-link", publicKey, "Test workstation",
                    InstallAccessClasses.AccountRecommended), "status-test-user", "status-test-subject");
            ExchangeInstallBrowserCallbackResponseDto exchange = Service.ExchangeBrowserCallback(
                new ExchangeInstallBrowserCallbackRequestDto(issued.Callback.CallbackCode, InstallationId,
                    "avalonia", "6.0.1-preview", "preview", "windows", "x64", publicKey, "Test workstation"));
            Installation = exchange.Installation;
            Grant = exchange.Grant;
        }

        public InstallLinkingStore Store { get; }
        public InstallLinkingService Service { get; }
        public ClaimedInstallationDto Installation { get; }
        public InstallationGrantDto Grant { get; }

        public AndroidInstallLinkProofPollRequest Request() => Sign(new AndroidInstallLinkProofPollRequest(
            InstallationId, "avalonia", "6.0.1-preview", "preview", "windows", "x64",
            Convert.ToBase64String(_key.ExportSubjectPublicKeyInfo()), DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Guid.NewGuid().ToString("N"), "unsigned"));

        public AndroidInstallLinkProofPollRequest Sign(AndroidInstallLinkProofPollRequest request)
        {
            byte[] proof = Encoding.UTF8.GetBytes(string.Join('\n', "chummer.install-link.install-status.v1",
                request.InstallationId, request.HeadId, request.ApplicationVersion, request.ChannelId, request.Platform,
                request.Arch, request.IssuedAtUnixSeconds.ToString(CultureInfo.InvariantCulture), request.Nonce));
            return request with
            {
                Signature = Convert.ToBase64String(_key.SignData(proof, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1))
            };
        }

        public void Dispose()
        {
            Store.Dispose();
            _key.Dispose();
            (_protection as IDisposable)?.Dispose();
            Directory.Delete(_root, recursive: true);
        }
    }
}
