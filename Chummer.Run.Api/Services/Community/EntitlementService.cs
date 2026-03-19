using Chummer.Run.Contracts.Entitlements;
using Chummer.Run.Contracts.Ledger;

namespace Chummer.Run.Api.Services.Community;

public sealed class EntitlementService
{
    private readonly CommunityStore _store;

    public EntitlementService(CommunityStore store)
    {
        _store = store;
    }

    public IReadOnlyList<string> ApplyReceipt(ContributionReceiptDto receipt, int mintedPoints)
    {
        if (string.IsNullOrWhiteSpace(receipt.UserId))
        {
            return Array.Empty<string>();
        }

        var grantedKeys = new List<string>();
        lock (_store.Gate)
        {
            if (string.Equals(receipt.EventKind, "slice_landed", StringComparison.OrdinalIgnoreCase)
                && receipt.Verified)
            {
                GrantIfMissingLocked("user", receipt.UserId!, "supporter-flair", receipt.ReceiptId, "verified landed slice", grantedKeys);
            }

            var userTotal = _store.RewardEntries
                .Where(entry => string.Equals(entry.UserId, receipt.UserId, StringComparison.OrdinalIgnoreCase))
                .Sum(entry => entry.Points);
            if (userTotal + mintedPoints >= 25)
            {
                GrantIfMissingLocked("user", receipt.UserId!, "gm-tools-waitlist-priority", receipt.ReceiptId, "community contribution threshold", grantedKeys);
            }

            if (!string.IsNullOrWhiteSpace(receipt.GroupId))
            {
                var groupTotal = _store.RewardEntries
                    .Where(entry => string.Equals(entry.GroupId, receipt.GroupId, StringComparison.OrdinalIgnoreCase))
                    .Sum(entry => entry.Points);
                if (groupTotal + mintedPoints >= 50)
                {
                    GrantIfMissingLocked("group", receipt.GroupId!, "private-leaderboard", receipt.ReceiptId, "group contribution threshold", grantedKeys);
                }
            }
        }

        return grantedKeys;
    }

    public IReadOnlyList<EntitlementDto> ListForUser(string userId)
    {
        lock (_store.Gate)
        {
            return _store.EntitlementEntries
                .Where(entry => string.Equals(entry.Scope, "user", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(entry.ScopeId, userId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(entry => entry.GrantedAtUtc)
                .Select(entry => new EntitlementDto(
                    entry.GrantId,
                    entry.Scope,
                    entry.ScopeId,
                    entry.Key,
                    "active",
                    entry.Reason,
                    null,
                    entry.GrantedAtUtc,
                    entry.ExpiresAtUtc))
                .ToArray();
        }
    }

    private void GrantIfMissingLocked(string scope, string scopeId, string key, string sourceReceiptId, string reason, ICollection<string> grantedKeys)
    {
        if (_store.EntitlementEntries.Any(entry =>
                string.Equals(entry.Scope, scope, StringComparison.OrdinalIgnoreCase)
                && string.Equals(entry.ScopeId, scopeId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(entry.Key, key, StringComparison.OrdinalIgnoreCase)))
        {
            return;
        }

        _store.EntitlementEntries.Add(
            new EntitlementGrantDto(
                GrantId: AccountService.NewId("ent"),
                Scope: scope,
                ScopeId: scopeId,
                Key: key,
                SourceReceiptId: sourceReceiptId,
                Reason: reason,
                GrantedAtUtc: DateTimeOffset.UtcNow,
                ExpiresAtUtc: null));
        grantedKeys.Add(key);
    }
}
