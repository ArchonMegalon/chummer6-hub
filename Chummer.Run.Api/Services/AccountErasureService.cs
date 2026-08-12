using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Contracts.Privacy;

namespace Chummer.Run.Api.Services;

public sealed class AccountErasureService
{
    private const string ReceiptKeyConfig = "CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY";
    private readonly AccountService _accounts;
    private readonly CommunityAccountErasureService _community;
    private readonly SupportStore _support;
    private readonly IAccountAuxiliaryDataErasureService _auxiliary;
    private readonly IHostedBuildAccountErasureClient _hostedBuild;
    private readonly HubIdentityClient _identity;
    private readonly IConfiguration _configuration;
    private readonly TimeProvider _timeProvider;

    public AccountErasureService(
        AccountService accounts,
        CommunityAccountErasureService community,
        SupportStore support,
        IAccountAuxiliaryDataErasureService auxiliary,
        IHostedBuildAccountErasureClient hostedBuild,
        HubIdentityClient identity,
        IConfiguration configuration,
        TimeProvider? timeProvider = null)
    {
        _accounts = accounts;
        _community = community;
        _support = support;
        _auxiliary = auxiliary;
        _hostedBuild = hostedBuild;
        _identity = identity;
        _configuration = configuration;
        _timeProvider = timeProvider ?? TimeProvider.System;
    }

    public async Task<CurrentAccountErasureResponse> EraseAsync(
        string subjectId,
        CancellationToken cancellationToken)
    {
        string normalizedSubject = string.IsNullOrWhiteSpace(subjectId)
            ? throw new ArgumentException("subjectId is required.", nameof(subjectId))
            : subjectId.Trim();
        string? userId = _accounts.GetBySubject(normalizedSubject)?.UserId;
        byte[] hmacKey = ResolveReceiptKey();
        try
        {
            // Identity is deliberately last. If any first-party data plane fails, the caller
            // retains an authenticated session and can safely retry the idempotent sequence.
            HostedBuildAccountErasureResult hosted =
                await _hostedBuild.EraseOwnerWorkspacesAsync(normalizedSubject, cancellationToken);
            RequireReceipt(hosted.ReceiptSha256, "Hosted Build");

            SupportReporterErasureResult support = _support.EraseReporter(userId, normalizedSubject);
            AccountAuxiliaryDataErasureResult auxiliary = _auxiliary.Erase(userId, normalizedSubject);
            CommunityAccountErasureResult community = _community.Erase(normalizedSubject, userId);
            IdentitySubjectErasureResponse identity =
                await _identity.EraseSubjectAsync(normalizedSubject, cancellationToken);

            DateTimeOffset erasedAtUtc = _timeProvider.GetUtcNow();
            string subjectKey = Hash(hmacKey, "subject", normalizedSubject);
            string? userKey = userId is null ? null : Hash(hmacKey, "user", userId);
            AccountErasureComponentReceipt[] components =
            [
                new(
                    Component: "hosted_build_workspaces",
                    Completed: true,
                    RecordsRemoved: hosted.WorkspaceRowsRemoved,
                    ReceiptSha256: hosted.ReceiptSha256.ToLowerInvariant()),
                new(
                    Component: "support",
                    Completed: true,
                    RecordsRemoved: support.CasesRemoved + support.IndexRecordsRemoved,
                    ReceiptSha256: Hash(
                        hmacKey,
                        "support",
                        support.CasesRemoved.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        support.IndexRecordsRemoved.ToString(System.Globalization.CultureInfo.InvariantCulture))),
                new(
                    Component: "first_party_auxiliary_stores",
                    Completed: true,
                    RecordsRemoved: auxiliary.RecordsRemoved,
                    ReceiptSha256: Hash(
                        hmacKey,
                        "auxiliary",
                        string.Join('|', auxiliary.RecordsRemovedByComponent
                            .OrderBy(static pair => pair.Key, StringComparer.Ordinal)
                            .Select(static pair => $"{pair.Key}:{pair.Value}")))),
                new(
                    Component: "community",
                    Completed: true,
                    RecordsRemoved: community.RecordsRemoved,
                    ReceiptSha256: Hash(
                        hmacKey,
                        "community",
                        community.RecordsRemoved.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        community.OwnedGroupsRemoved.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        community.PlayAuthorizationRecordsRemoved.ToString(System.Globalization.CultureInfo.InvariantCulture))),
                new(
                    Component: "identity",
                    Completed: true,
                    RecordsRemoved: identity.RevokedSessionCount + identity.DeletedEmailTicketCount + (identity.Erased ? 1 : 0),
                    ReceiptSha256: Hash(
                        hmacKey,
                        "identity",
                        identity.SubjectKeySha256,
                        identity.RevokedSessionCount.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        identity.DeletedEmailTicketCount.ToString(System.Globalization.CultureInfo.InvariantCulture)))
            ];

            string receiptSha256 = Hash(
                hmacKey,
                "account-erasure",
                subjectKey,
                userKey ?? "none",
                erasedAtUtc.ToString("O", System.Globalization.CultureInfo.InvariantCulture),
                string.Join('|', components.Select(static component =>
                    $"{component.Component}:{component.RecordsRemoved}:{component.ReceiptSha256}")));

            return new CurrentAccountErasureResponse(
                Erased: true,
                SubjectKeySha256: subjectKey,
                UserKeySha256: userKey,
                Components: components,
                ErasedAtUtc: erasedAtUtc,
                ReceiptSha256: receiptSha256);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(hmacKey);
        }
    }

    private byte[] ResolveReceiptKey()
    {
        string? configured = _configuration[ReceiptKeyConfig];
        if (string.IsNullOrWhiteSpace(configured))
        {
            throw new HubRequestAuthException(
                StatusCodes.Status503ServiceUnavailable,
                "Account erasure is unavailable right now. Try again later.");
        }

        string normalized = configured.Trim();
        byte[] key;
        try
        {
            key = Convert.FromBase64String(normalized);
        }
        catch (FormatException)
        {
            key = Encoding.UTF8.GetBytes(normalized);
        }

        if (key.Length < 32)
        {
            CryptographicOperations.ZeroMemory(key);
            throw new HubRequestAuthException(
                StatusCodes.Status503ServiceUnavailable,
                "Account erasure is unavailable right now. Try again later.");
        }

        return key;
    }

    private static string Hash(byte[] key, params string[] parts)
    {
        string value = "chummer.account-erasure.v1\0" + string.Join('\0', parts);
        byte[] bytes = Encoding.UTF8.GetBytes(value);
        byte[] digest = HMACSHA256.HashData(key, bytes);
        try
        {
            return Convert.ToHexString(digest).ToLowerInvariant();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(bytes);
            CryptographicOperations.ZeroMemory(digest);
        }
    }

    private static void RequireReceipt(string receiptSha256, string component)
    {
        if (receiptSha256.Length != 64 || receiptSha256.Any(static value => !Uri.IsHexDigit(value)))
        {
            throw new HubRequestAuthException(
                StatusCodes.Status503ServiceUnavailable,
                $"{component} account erasure returned an invalid receipt.");
        }
    }
}
