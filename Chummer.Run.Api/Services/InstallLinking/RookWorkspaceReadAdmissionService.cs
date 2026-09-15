using Chummer.Run.Api.Services.Community;

namespace Chummer.Run.Api.Services.InstallLinking;

/// <summary>
/// Server-local custody of one explicitly selected, consented continuation.
/// This is neither a Core restore receipt nor continuing authorization. No
/// provider or public endpoint may serialize this full character carrier.
/// </summary>
internal sealed record RookWorkspaceReadCapture(
    HubSessionAccountObservation Account,
    InstallLinkingRookReadConsent Consent,
    InstallLinkedWorkspaceSnapshotRecord Snapshot,
    DateTimeOffset CapturedAtUtc);

/// <summary>
/// Composes fresh Identity introspection with canonical account, installation,
/// persisted consent and selected-workspace custody. Identity I/O occurs before
/// the account -> install store -> PostgreSQL fence -> snapshot lock sequence.
/// No provider activation, character mutation or public route is introduced.
/// </summary>
internal sealed class RookWorkspaceReadAdmissionService(
    HubSessionAccountAdmissionService sessions,
    AccountService accounts,
    InstallLinkingService installations,
    InstallLinkedWorkspaceSnapshotService snapshots,
    TimeProvider time)
{
    internal async Task<InstallLinkingRookReadConsent> GrantAsync(
        HttpRequest request,
        string installationId,
        string grantId,
        string workspaceId,
        long remoteRevision,
        string serverToken,
        string continuationDigest,
        bool explicitConfirmation,
        DateTimeOffset expiresAtUtc,
        CancellationToken ct = default)
    {
        if (!explicitConfirmation) throw Denied();
        HubSessionAccountObservation account = await sessions.RequireAccountAsync(request, ct).ConfigureAwait(false);
        InstallLinkingRookReadConsent? consent = null;
        bool captured = accounts.CaptureExistingCanonicalAccount(account.SubjectId, account.UserId, () =>
        {
            RequireFresh(account, ct);
            consent = installations.GrantRookReadConsent(
                account.UserId, account.SubjectId, installationId, grantId, workspaceId,
                remoteRevision, serverToken, continuationDigest, explicitConfirmation,
                expiresAtUtc <= account.ExpiresAtUtc ? expiresAtUtc : account.ExpiresAtUtc,
                installation =>
                {
                    RequireFresh(account, ct);
                    // Validation only: consent issuance must not return the
                    // selected continuation or enumerate other workspaces.
                    _ = snapshots.CaptureSelectedContinuation(installation, workspaceId,
                        remoteRevision, serverToken, continuationDigest);
                    RequireFresh(account, ct);
                }, ct);
        });
        if (!captured || consent is null) throw Denied();
        return consent;
    }

    internal async Task<InstallLinkingRookReadConsent> RevokeAsync(
        HttpRequest request, string consentId, long expectedVersion, CancellationToken ct = default)
    {
        HubSessionAccountObservation account = await sessions.RequireAccountAsync(request, ct).ConfigureAwait(false);
        InstallLinkingRookReadConsent? revoked = null;
        bool captured = accounts.CaptureExistingCanonicalAccount(account.SubjectId, account.UserId, () =>
        {
            RequireFresh(account, ct);
            // Revocation needs the consent owner, not a still-active device grant.
            revoked = installations.RevokeRookReadConsent(
                account.UserId, account.SubjectId, consentId, expectedVersion, ct);
        });
        if (!captured || revoked is null) throw Denied();
        return revoked;
    }

    internal async Task<RookWorkspaceReadCapture> CaptureAsync(
        HttpRequest request,
        string installationId,
        string grantId,
        string consentId,
        long expectedVersion,
        CancellationToken ct = default)
    {
        HubSessionAccountObservation account = await sessions.RequireAccountAsync(request, ct).ConfigureAwait(false);
        RookWorkspaceReadCapture? candidate = null;
        bool fenced = false;
        bool mapped = accounts.CaptureExistingCanonicalAccount(account.SubjectId, account.UserId, () =>
        {
            RequireFresh(account, ct);
            fenced = installations.CaptureRookReadConsent(
                account.UserId, account.SubjectId, installationId, grantId, consentId, expectedVersion,
                (consent, installation) =>
                {
                    // This callback may execute on another thread. In particular,
                    // it must not reacquire the caller-held account/install gates.
                    RequireFresh(account, ct);
                    InstallLinkedWorkspaceSnapshotRecord snapshot = snapshots.CaptureSelectedContinuation(
                        installation, consent.WorkspaceId, consent.RemoteRevision,
                        consent.ServerToken, consent.ContinuationDigest);
                    RequireFresh(account, ct);
                    candidate = new(account, consent, snapshot, time.GetUtcNow());
                }, ct);
        });

        // A callback can run before rollback/cleanup fails. Never release its
        // captured bytes merely because the callback happened to populate them.
        if (!mapped || !fenced || candidate is null) throw Denied();
        RequireFresh(account, ct);
        if (candidate.Consent.ExpiresAtUtc <= time.GetUtcNow()) throw Denied();
        return candidate;
    }

    /// <summary>
    /// Must be called after asynchronous Core/provider work and before releasing
    /// derived output. It performs fresh introspection and fenced recapture; the
    /// earlier capture is not accepted as a bearer credential or cached approval.
    /// The result remains a point-in-time observation, not a lifetime lease.
    /// </summary>
    internal async Task RevalidateAsync(
        HttpRequest request, RookWorkspaceReadCapture previous, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(previous);
        RookWorkspaceReadCapture current = await CaptureAsync(request,
            previous.Consent.InstallationId, previous.Consent.GrantId,
            previous.Consent.ConsentId, previous.Consent.Version, ct).ConfigureAwait(false);
        if (!string.Equals(current.Account.UserId, previous.Account.UserId, StringComparison.Ordinal)
            || !string.Equals(current.Account.SubjectId, previous.Account.SubjectId, StringComparison.Ordinal)
            || !string.Equals(current.Account.SessionId, previous.Account.SessionId, StringComparison.Ordinal)
            || current.Consent != previous.Consent
            || current.Snapshot.RemoteRevision != previous.Snapshot.RemoteRevision
            || !string.Equals(current.Snapshot.ServerToken, previous.Snapshot.ServerToken, StringComparison.Ordinal)
            || !string.Equals(current.Snapshot.WorkspaceContinuationDigest,
                previous.Snapshot.WorkspaceContinuationDigest, StringComparison.Ordinal))
            throw Denied();
    }

    private void RequireFresh(HubSessionAccountObservation account, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (account.ExpiresAtUtc <= time.GetUtcNow()) throw Denied();
    }

    private static InstallLinkingOperationException Denied()
        => new(StatusCodes.Status403Forbidden, "The selected workspace is not authorized for this Rook read.");
}
