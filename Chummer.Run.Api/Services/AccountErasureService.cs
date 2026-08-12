using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Contracts.Privacy;

namespace Chummer.Run.Api.Services;

public interface IAccountErasureService
{
    Task<CurrentAccountErasureResponse> EraseAsync(
        string subjectId,
        CancellationToken cancellationToken);
}

public sealed class AccountErasureService : IAccountErasureService
{
    private const string ReceiptKeyConfig = "CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY";
    private readonly AccountService _accounts;
    private readonly CommunityAccountErasureService _community;
    private readonly SupportStore _support;
    private readonly IAccountAuxiliaryDataErasureService _auxiliary;
    private readonly IHostedBuildAccountErasureClient _hostedBuild;
    private readonly HubIdentityClient _identity;
    private readonly AccountErasureJournalStore _journal;
    private readonly IConfiguration _configuration;
    private readonly TimeProvider _timeProvider;

    public AccountErasureService(
        AccountService accounts,
        CommunityAccountErasureService community,
        SupportStore support,
        IAccountAuxiliaryDataErasureService auxiliary,
        IHostedBuildAccountErasureClient hostedBuild,
        HubIdentityClient identity,
        AccountErasureJournalStore journal,
        IConfiguration configuration,
        TimeProvider? timeProvider = null)
    {
        _accounts = accounts;
        _community = community;
        _support = support;
        _auxiliary = auxiliary;
        _hostedBuild = hostedBuild;
        _identity = identity;
        _journal = journal;
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
            DateTimeOffset startedAtUtc = _timeProvider.GetUtcNow();
            string subjectKey = Hash(hmacKey, "subject", normalizedSubject);
            string? userKey = userId is null ? null : Hash(hmacKey, "user", userId);
            AccountErasureJournalEntry journalEntry = _journal.Begin(
                subjectKey,
                userKey,
                startedAtUtc);
            if (journalEntry.Stage == AccountErasureJournalStage.Completed)
            {
                return ToResponse(journalEntry);
            }
            // Identity is deliberately last. If any first-party data plane fails, the caller
            // retains an authenticated session and can safely retry the idempotent sequence.
            HostedBuildAccountErasureResult hosted =
                await _hostedBuild.EraseOwnerWorkspacesAsync(normalizedSubject, cancellationToken);
            RequireReceipt(hosted.ReceiptSha256, "Hosted Build");
            journalEntry = _journal.RecordComponent(
                subjectKey,
                new AccountErasureComponentReceipt(
                    Component: "hosted_build_workspaces",
                    Completed: true,
                    RecordsRemoved: hosted.WorkspaceRowsRemoved,
                    ReceiptSha256: hosted.ReceiptSha256.ToLowerInvariant()),
                _timeProvider.GetUtcNow());

            SupportReporterErasureResult support = _support.EraseReporter(userId, normalizedSubject);
            journalEntry = _journal.RecordComponent(
                subjectKey,
                new AccountErasureComponentReceipt(
                    Component: "support",
                    Completed: true,
                    RecordsRemoved: support.CasesRemoved + support.IndexRecordsRemoved,
                    ReceiptSha256: Hash(
                        hmacKey,
                        "support",
                        support.CasesRemoved.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        support.IndexRecordsRemoved.ToString(System.Globalization.CultureInfo.InvariantCulture))),
                _timeProvider.GetUtcNow());

            AccountAuxiliaryDataErasureResult auxiliary = _auxiliary.Erase(userId, normalizedSubject);
            journalEntry = _journal.RecordComponent(
                subjectKey,
                new AccountErasureComponentReceipt(
                    Component: "first_party_auxiliary_stores",
                    Completed: true,
                    RecordsRemoved: auxiliary.RecordsRemoved,
                    ReceiptSha256: Hash(
                        hmacKey,
                        "auxiliary",
                        string.Join('|', auxiliary.RecordsRemovedByComponent
                            .OrderBy(static pair => pair.Key, StringComparer.Ordinal)
                            .Select(static pair => $"{pair.Key}:{pair.Value}")))),
                _timeProvider.GetUtcNow());

            CommunityAccountErasureResult community = _community.Erase(normalizedSubject, userId);
            journalEntry = _journal.RecordComponent(
                subjectKey,
                new AccountErasureComponentReceipt(
                    Component: "community",
                    Completed: true,
                    RecordsRemoved: community.RecordsRemoved,
                    ReceiptSha256: Hash(
                        hmacKey,
                        "community",
                        community.RecordsRemoved.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        community.OwnedGroupsRemoved.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        community.PlayAuthorizationRecordsRemoved.ToString(System.Globalization.CultureInfo.InvariantCulture))),
                _timeProvider.GetUtcNow());

            journalEntry = _journal.MarkIdentityPending(
                subjectKey,
                normalizedSubject,
                _timeProvider.GetUtcNow());
            IdentitySubjectErasureResponse identity =
                await _identity.EraseSubjectAsync(normalizedSubject, cancellationToken);
            return CompleteIdentity(journalEntry, identity, hmacKey);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(hmacKey);
        }
    }

    internal async Task RecoverPendingIdentityAsync(
        PendingIdentityAccountErasure pending,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(pending);
        byte[] hmacKey = ResolveReceiptKey();
        try
        {
            string subjectKey = Hash(hmacKey, "subject", pending.SubjectId);
            if (!FixedDigestEquals(subjectKey, pending.Entry.SubjectKeySha256))
            {
                throw new CryptographicException("Pending Identity erasure subject binding is invalid.");
            }

            AccountErasureJournalEntry? current = _journal.Find(subjectKey);
            if (current?.Stage == AccountErasureJournalStage.Completed)
            {
                return;
            }

            IdentitySubjectErasureResponse identity =
                await _identity.EraseSubjectAsync(pending.SubjectId, cancellationToken);
            CompleteIdentity(current ?? pending.Entry, identity, hmacKey);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(hmacKey);
        }
    }

    private CurrentAccountErasureResponse CompleteIdentity(
        AccountErasureJournalEntry journalEntry,
        IdentitySubjectErasureResponse identity,
        byte[] hmacKey)
    {
        DateTimeOffset erasedAtUtc = _timeProvider.GetUtcNow();
        var identityComponent = new AccountErasureComponentReceipt(
            Component: "identity",
            Completed: true,
            RecordsRemoved: identity.RevokedSessionCount + identity.DeletedEmailTicketCount + (identity.Erased ? 1 : 0),
            ReceiptSha256: Hash(
                hmacKey,
                "identity",
                identity.SubjectKeySha256,
                identity.RevokedSessionCount.ToString(System.Globalization.CultureInfo.InvariantCulture),
                identity.DeletedEmailTicketCount.ToString(System.Globalization.CultureInfo.InvariantCulture)));
        AccountErasureComponentReceipt[] components = [.. journalEntry.Components, identityComponent];
        string receiptSha256 = Hash(
            hmacKey,
            "account-erasure",
            journalEntry.SubjectKeySha256,
            journalEntry.UserKeySha256 ?? "none",
            erasedAtUtc.ToString("O", System.Globalization.CultureInfo.InvariantCulture),
            string.Join('|', components.Select(static component =>
                $"{component.Component}:{component.RecordsRemoved}:{component.ReceiptSha256}")));
        AccountErasureJournalEntry completed = _journal.Complete(
            journalEntry.SubjectKeySha256,
            identityComponent,
            erasedAtUtc,
            receiptSha256);
        return ToResponse(completed);
    }

    private static CurrentAccountErasureResponse ToResponse(AccountErasureJournalEntry entry)
    {
        if (entry.Stage != AccountErasureJournalStage.Completed
            || entry.CompletedAtUtc is null
            || entry.ReceiptSha256 is null)
        {
            throw new InvalidOperationException("Account-erasure journal entry is not complete.");
        }

        return new CurrentAccountErasureResponse(
            Erased: true,
            SubjectKeySha256: entry.SubjectKeySha256,
            UserKeySha256: entry.UserKeySha256,
            Components: entry.Components,
            ErasedAtUtc: entry.CompletedAtUtc.Value,
            ReceiptSha256: entry.ReceiptSha256);
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

    private static bool FixedDigestEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.ASCII.GetBytes(left);
        byte[] rightBytes = Encoding.ASCII.GetBytes(right);
        try
        {
            return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(leftBytes);
            CryptographicOperations.ZeroMemory(rightBytes);
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
