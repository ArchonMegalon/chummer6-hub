using Chummer.Hub.Registry.Contracts.InstallLinking;
using System.Security.Cryptography;
using System.Text.Json;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkedWorkspaceSnapshotService
{
    public const int MaxUpsertRequestBodyBytes = 768 * 1024;
    public const int MaxUpsertPayloadCharacters = 512 * 1024;
    private const int MaxWorkspaceIdLength = 128;
    private const int MaxRulesetIdLength = 64;
    private const int MaxFormatLength = 64;
    private const int MaxPayloadKindLength = 64;
    private const int MaxOriginInstallationIdLength = 64;
    private const int MaxDisplayNameLength = 160;
    private const int MaxTraitLength = 64;
    private readonly InstallLinkedWorkspaceSnapshotStore _store;

    public InstallLinkedWorkspaceSnapshotService(InstallLinkedWorkspaceSnapshotStore store)
    {
        _store = store;
    }

    public IReadOnlyList<InstallLinkedWorkspaceSnapshotRecord> ListForInstallation(ClaimedInstallationDto installation)
    {
        ArgumentNullException.ThrowIfNull(installation);

        string ownerKey = ResolveOwnerKey(installation);
        lock (_store.Gate)
        {
            return _store.SnapshotsByKey.Values
                .Where(item => string.Equals(item.OwnerKey, ownerKey, StringComparison.Ordinal))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .Select(item => WithAuthority(item, installation))
                .ToArray();
        }
    }

    public InstallLinkedWorkspaceSnapshotRecord UpsertForInstallation(
        ClaimedInstallationDto installation,
        InstallLinkedWorkspaceSnapshotRecord snapshot,
        long? expectedRemoteRevision = null,
        string? expectedServerToken = null)
    {
        ArgumentNullException.ThrowIfNull(installation);
        ArgumentNullException.ThrowIfNull(snapshot);
        if (expectedRemoteRevision is < 0
            || (expectedRemoteRevision is null && expectedServerToken is not null)
            || (expectedRemoteRevision == 0 && expectedServerToken is not null && !IsServerToken(expectedServerToken))
            || (expectedRemoteRevision is > 0 && !IsServerToken(expectedServerToken)))
        {
            throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest,
                "The expected remote revision and server token are invalid.");
        }

        string ownerKey = ResolveOwnerKey(installation);
        InstallLinkedWorkspaceSnapshotRecord normalized = snapshot with
        {
            OwnerKey = ownerKey,
            WorkspaceId = NormalizeRequired(snapshot.WorkspaceId, "workspace id", MaxWorkspaceIdLength),
            RulesetId = NormalizeRequired(snapshot.RulesetId, "ruleset id", MaxRulesetIdLength),
            Format = NormalizeRequired(snapshot.Format, "format", MaxFormatLength),
            PayloadKind = NormalizeRequired(snapshot.PayloadKind, "payload kind", MaxPayloadKindLength),
            Payload = NormalizePayload(snapshot.Payload),
            OriginInstallationId = NormalizeOptional(snapshot.OriginInstallationId, "origin installation id", MaxOriginInstallationIdLength) ?? installation.InstallationId,
            Name = NormalizeOptional(snapshot.Name, "name", MaxDisplayNameLength),
            Alias = NormalizeOptional(snapshot.Alias, "alias", MaxDisplayNameLength),
            Metatype = NormalizeOptional(snapshot.Metatype, "metatype", MaxTraitLength),
            BuildMethod = NormalizeOptional(snapshot.BuildMethod, "build method", MaxTraitLength),
            CreatedVersion = NormalizeOptional(snapshot.CreatedVersion, "created version", MaxTraitLength),
            AppVersion = NormalizeOptional(snapshot.AppVersion, "app version", MaxTraitLength)
        };
        normalized = InstallLinkedWorkspaceSnapshotTransfer.Validate(normalized,
            expectedContinuationOwnerId: ResolveContinuationOwnerId(installation, normalized));

        lock (_store.Gate)
        {
            string key = InstallLinkedWorkspaceSnapshotStore.ComposeKey(ownerKey, normalized.WorkspaceId);
            _store.SnapshotsByKey.TryGetValue(key, out InstallLinkedWorkspaceSnapshotRecord? existing);
            InstallLinkedWorkspaceSnapshotRecord? observed = existing is null ? null : WithAuthority(existing, installation);
            if (expectedRemoteRevision is { } expected
                && (expected != (observed?.RemoteRevision ?? 0)
                    || !string.Equals(expectedServerToken, observed?.ServerToken, StringComparison.Ordinal)))
            {
                throw new InstallLinkingOperationException(StatusCodes.Status409Conflict,
                    "The remote workspace changed. Read and review its current snapshot before updating it.");
            }

            if (existing is not null)
            {
                if (existing.WorkspaceContinuation is not null && normalized.WorkspaceContinuation is null)
                    throw new InstallLinkingOperationException(StatusCodes.Status409Conflict,
                        "A complete workspace continuation cannot be replaced by a projection-only or payload-only client.");
                if (existing.WorkspaceSnapshot is not null && normalized.WorkspaceSnapshot is null
                    && normalized.WorkspaceContinuation is null)
                    throw new InstallLinkingOperationException(StatusCodes.Status409Conflict,
                        "A complete workspace snapshot cannot be replaced by a payload-only client.");
                // An exact no-op is safe for older clients, but a newer clock is
                // never permission to overwrite. A supplied stale precondition
                // was already rejected above, including byte-identical ABA.
                if ((normalized with { RemoteRevision = existing.RemoteRevision, ServerToken = existing.ServerToken,
                        WorkspaceSnapshot = null, WorkspaceContinuation = null })
                    == (existing with { WorkspaceSnapshot = null, WorkspaceContinuation = null }))
                    return observed!;
                if (expectedRemoteRevision is null)
                    throw new InstallLinkingOperationException(StatusCodes.Status428PreconditionRequired,
                        "Updating a remote workspace requires its reviewed remote revision and server token.");
            }
            if (existing?.RemoteRevision is < 0 or long.MaxValue)
                throw new InstallLinkingOperationException(StatusCodes.Status409Conflict,
                    "The stored remote workspace revision cannot be advanced safely.");

            InstallLinkedWorkspaceSnapshotRecord committed = normalized with
            {
                RemoteRevision = checked((existing?.RemoteRevision ?? 0) + 1),
                // Opaque optimistic-concurrency value, never an access credential.
                ServerToken = Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(32))
            };
            _store.SnapshotsByKey[key] = committed;
            try
            {
                _store.PersistLocked();
            }
            catch
            {
                // Persistence failure must not publish an uncommitted snapshot
                // to later readers in this process.
                if (existing is null) _store.SnapshotsByKey.Remove(key);
                else _store.SnapshotsByKey[key] = existing;
                throw;
            }
            return committed;
        }
    }

    private static bool IsServerToken(string? token)
        => token is { Length: 64 } && token.All(static c => c is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static InstallLinkedWorkspaceSnapshotRecord WithAuthority(InstallLinkedWorkspaceSnapshotRecord record,
        ClaimedInstallationDto installation)
    {
        record = InstallLinkedWorkspaceSnapshotTransfer.Validate(record, stored: true,
            expectedContinuationOwnerId: ResolveContinuationOwnerId(installation, record, stored: true));
        if (record.RemoteRevision == 0 && record.ServerToken is null)
        {
            // An older persisted row still needs an exact read-before-write
            // token. Revision zero with NO token means missing-only creation;
            // it must never overwrite an unseen legacy row. This read projection
            // is deterministic across restarts and does not rewrite the store.
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(new
            { Contract = "chummer.legacy-workspace-snapshot-etag/v1", Snapshot = record });
            return record with { ServerToken = Convert.ToHexStringLower(SHA256.HashData(bytes)) };
        }
        if (record.RemoteRevision <= 0 || !IsServerToken(record.ServerToken))
            throw new InstallLinkingOperationException(StatusCodes.Status503ServiceUnavailable,
                "The stored remote workspace authority is invalid.");
        return record;
    }

    private static string ResolveOwnerKey(ClaimedInstallationDto installation)
    {
        string? subjectId = installation.SubjectId;
        if (!string.IsNullOrEmpty(subjectId))
        {
            // Opaque authenticated subjects retain exact case and whitespace.
            // Ambiguous historically trimmed rows are never guessed/remapped.
            return $"subject:{subjectId}";
        }

        string? userId = string.IsNullOrWhiteSpace(installation.UserId) ? null : installation.UserId.Trim();
        if (!string.IsNullOrWhiteSpace(userId))
        {
            return $"user:{userId}";
        }

        throw new InvalidOperationException("claimed installation has no user or subject identity.");
    }

    private static string? ResolveContinuationOwnerId(ClaimedInstallationDto installation,
        InstallLinkedWorkspaceSnapshotRecord record, bool stored = false)
    {
        if (record.WorkspaceContinuation is null && record.WorkspaceContinuationDigest is null)
            return null;
        try
        {
            return InstallLinkedWorkspaceSnapshotTransfer.ComputeContinuationOwnerId(installation.SubjectId!);
        }
        catch (ArgumentException)
        {
            throw new InstallLinkingOperationException(
                stored ? StatusCodes.Status503ServiceUnavailable : StatusCodes.Status400BadRequest,
                "Full workspace continuation requires a valid exact authenticated subject identity.");
        }
    }

    private static string NormalizeRequired(string? value, string label, int maxLength)
        => NormalizeOptional(value, label, maxLength) ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, $"{label} is required.");

    private static string? NormalizeOptional(string? value, string label, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string normalized = value.Trim();
        if (normalized.Length > maxLength)
        {
            throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, $"{label} exceeds the maximum length of {maxLength} characters.");
        }

        return normalized;
    }

    private static string NormalizePayload(string? payload)
    {
        string normalized = payload ?? string.Empty;
        if (normalized.Length > MaxUpsertPayloadCharacters)
        {
            throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, $"payload exceeds the maximum length of {MaxUpsertPayloadCharacters} characters.");
        }

        return normalized;
    }
}
