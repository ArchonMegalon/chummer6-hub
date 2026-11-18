using System.Text;
using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingRookConsentJsonTests
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private static readonly JsonSerializerOptions PrettyJson = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };
    private static readonly DateTimeOffset IssuedAt = new(2026, 9, 15, 10, 0, 0, TimeSpan.Zero);

    [Fact]
    public void Canonical_consent_roundtrips_through_real_import_and_snapshot_validation()
    {
        InstallLinkingStoreSnapshot source = ValidSnapshot();
        InstallLinkingStore.ValidateSnapshot(source);
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(source, Json);

        InstallLinkingStoreSnapshot parsed = InstallLinkingStore.DeserializeImportSnapshot(bytes, Json);
        InstallLinkingStore.ValidateSnapshot(parsed);

        Assert.Equal(Assert.Single(source.RookReadConsents!), Assert.Single(parsed.RookReadConsents!));
        Assert.Equal(bytes, JsonSerializer.SerializeToUtf8Bytes(parsed, Json));
    }

    [Theory]
    [InlineData("duplicate-collection")]
    [InlineData("case-duplicate-collection")]
    [InlineData("case-alias-collection")]
    [InlineData("duplicate-field")]
    [InlineData("unknown-field")]
    [InlineData("omitted-field")]
    [InlineData("quoted-number")]
    [InlineData("non-array-collection")]
    [InlineData("null-row")]
    [InlineData("null-identity-field")]
    [InlineData("wrong-field-type")]
    public void Ambiguous_or_wrong_typed_consent_json_is_rejected_by_real_import(string corruption)
    {
        InstallLinkingStoreSnapshot source = ValidSnapshot();
        InstallLinkingStore.ValidateSnapshot(source);
        string json = JsonSerializer.Serialize(source, Json);
        string consent = JsonSerializer.Serialize(Assert.Single(source.RookReadConsents!), Json);
        string changed = corruption switch
        {
            // A trailing null must not hide an earlier populated consent collection.
            "duplicate-collection" => json[..^1] + ",\"rookReadConsents\":null}",
            "case-duplicate-collection" => json[..^1] + ",\"RookReadConsents\":null}",
            "case-alias-collection" => ReplaceOnce(json, "\"rookReadConsents\":", "\"RookReadConsents\":"),
            "duplicate-field" => ReplaceOnce(json, consent,
                consent[..^1] + ",\"version\":2}"),
            "unknown-field" => ReplaceOnce(json, consent,
                consent[..^1] + ",\"providerAuthority\":\"not-authority\"}"),
            "omitted-field" => ReplaceOnce(json, consent,
                ReplaceOnce(consent, "\"purpose\":\"rook-rule-read\",", string.Empty)),
            "quoted-number" => ReplaceOnce(json, consent,
                ReplaceOnce(consent, "\"remoteRevision\":17", "\"remoteRevision\":\"17\"")),
            "non-array-collection" => ReplaceOnce(json, "[" + consent + "]", "{}"),
            "null-row" => ReplaceOnce(json, "[" + consent + "]", "[null]"),
            "null-identity-field" => ReplaceOnce(json, consent,
                ReplaceOnce(consent, "\"subjectId\":\"subject-Json-owner\"", "\"subjectId\":null")),
            "wrong-field-type" => ReplaceOnce(json, consent,
                ReplaceOnce(consent, "\"revokedAtUtc\":null", "\"revokedAtUtc\":false")),
            _ => throw new InvalidOperationException("Unknown fixture corruption.")
        };

        Assert.Throws<InvalidDataException>(() => InstallLinkingStore.DeserializeImportSnapshot(
            Encoding.UTF8.GetBytes(changed), Json));
    }

    [Fact]
    public void Escaped_unpaired_surrogate_identity_is_not_admitted_by_real_import()
    {
        InstallLinkingStoreSnapshot source = ValidSnapshot();
        string json = JsonSerializer.Serialize(source, Json);
        string consent = JsonSerializer.Serialize(Assert.Single(source.RookReadConsents!), Json);
        string changed = ReplaceOnce(json, consent, ReplaceOnce(consent,
            "\"subjectId\":\"subject-Json-owner\"", "\"subjectId\":\"\\uD800\""));

        Assert.Throws<JsonException>(() =>
        {
            InstallLinkingStoreSnapshot parsed = InstallLinkingStore.DeserializeImportSnapshot(
                Encoding.UTF8.GetBytes(changed), Json);
            InstallLinkingStore.ValidateSnapshot(parsed);
        });
    }

    [Fact]
    public void Legacy_absent_consent_collection_preserves_exact_canonical_snapshot_bytes()
    {
        byte[] legacyBytes = LegacyEmptyBytes();

        InstallLinkingStoreSnapshot parsed = InstallLinkingStore.DeserializeImportSnapshot(legacyBytes, PrettyJson);
        InstallLinkingStore.ValidateSnapshot(parsed);

        Assert.Null(parsed.RookReadConsents);
        Assert.Equal(legacyBytes, JsonSerializer.SerializeToUtf8Bytes(parsed, PrettyJson));
    }

    [Theory]
    [InlineData("null")]
    [InlineData("[]")]
    public void Empty_optional_collection_is_no_consent_and_retains_the_legacy_byte_layout(string emptyValue)
    {
        byte[] legacyBytes = LegacyEmptyBytes();
        string legacy = Encoding.UTF8.GetString(legacyBytes);
        string withEmpty = legacy[..^1] + ",\"rookReadConsents\":" + emptyValue + "}";

        InstallLinkingStoreSnapshot parsed = InstallLinkingStore.DeserializeImportSnapshot(
            Encoding.UTF8.GetBytes(withEmpty), PrettyJson);
        InstallLinkingStore.ValidateSnapshot(parsed);
        InstallLinkingStoreSnapshot retained = InstallLinkingStore.BuildRetainedSnapshot(parsed, IssuedAt);
        InstallLinkingStore.ValidateSnapshot(retained);

        Assert.Empty(parsed.RookReadConsents ?? []);
        Assert.Null(retained.RookReadConsents);
        Assert.Equal(legacyBytes, JsonSerializer.SerializeToUtf8Bytes(retained, PrettyJson));
    }

    [Fact]
    public void Expired_malformed_consent_cannot_be_laundered_by_retention()
    {
        InstallLinkingStoreSnapshot source = ValidSnapshot();
        InstallLinkingRookReadConsent valid = Assert.Single(source.RookReadConsents!);
        InstallLinkingStoreSnapshot corrupted = source with
        {
            RookReadConsents = [valid with { Purpose = "provider-write" }]
        };
        // Exercise the actual JSON import before the actual retention validation.
        InstallLinkingStoreSnapshot parsed = InstallLinkingStore.DeserializeImportSnapshot(
            JsonSerializer.SerializeToUtf8Bytes(corrupted, Json), Json);

        Assert.Throws<InvalidDataException>(() => InstallLinkingStore.ValidateSnapshot(parsed));
        Assert.Throws<InvalidDataException>(() => InstallLinkingStore.BuildRetainedSnapshot(
            parsed, valid.ExpiresAtUtc.AddDays(2)));
    }

    private static string ReplaceOnce(string input, string expected, string replacement)
    {
        int first = input.IndexOf(expected, StringComparison.Ordinal);
        Assert.True(first >= 0, "The fixture mutation target must exist.");
        Assert.Equal(-1, input.IndexOf(expected, first + expected.Length, StringComparison.Ordinal));
        return input[..first] + replacement + input[(first + expected.Length)..];
    }

    private static byte[] LegacyEmptyBytes()
        => Encoding.UTF8.GetBytes("""
            {
              "receipts": [],
              "claimTickets": [],
              "browserCallbacks": [],
              "installations": [],
              "grants": [],
              "personalizedInstallScripts": [],
              "androidLinkedV2ReplayReceipts": [],
              "grantTransportAuthorities": [],
              "browserCallbackRedemptionReceipts": [],
              "androidLinkedV2RefreshReceipts": [],
              "browserCallbackTransportIntents": []
            }
            """);

    private static InstallLinkingStoreSnapshot ValidSnapshot()
    {
        const string installationId = "install-json-owner";
        const string grantId = "grant-json-owner";
        const string userId = "user-json-owner";
        const string subjectId = "subject-Json-owner";
        var installation = new ClaimedInstallationDto(
            InstallationId: installationId, ArtifactId: "artifact-json", Channel: "preview",
            Version: "6.0.1", InstallAccessClass: InstallAccessClasses.AccountRequired,
            Status: ClaimedInstallationStates.Active, CreatedAtUtc: IssuedAt.AddMinutes(-5),
            UpdatedAtUtc: IssuedAt, UserId: userId, SubjectId: subjectId,
            PublicKey: "fixture-public-key", ClaimTicketId: null, HeadId: "desktop",
            Platform: "linux", Arch: "x64", HostLabel: "Consent JSON fixture", GrantId: grantId);
        var grant = new InstallationGrantDto(
            GrantId: grantId, InstallationId: installationId, Status: InstallationGrantStates.Active,
            AccessToken: "fixture-json-grant-token", IssuedAtUtc: IssuedAt.AddMinutes(-1),
            ExpiresAtUtc: IssuedAt.AddHours(1), UserId: userId, SubjectId: subjectId);
        var consent = new InstallLinkingRookReadConsent(
            new string('c', 64), 1, userId, subjectId, installationId, grantId, "workspace-json",
            17, new string('a', 64), new string('b', 64), "rook-rule-read",
            IssuedAt, IssuedAt.AddMinutes(10), null);
        return new InstallLinkingStoreSnapshot(
            [], [], [], [installation], [grant],
            GrantTransportAuthorities: [new(grantId, InstallationGrantTransports.AndroidLinkedV2)],
            RookReadConsents: [consent]);
    }
}
