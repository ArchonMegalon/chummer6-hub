using System.Security.Cryptography;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking.Postgres;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed partial class InstallLinkingService
{
    /// <summary>
    /// Persists explicit consent for one reviewed continuation. The trusted caller first
    /// authenticates the account and supplies a synchronous, read-only selection validator.
    /// Selection is validated under the local store gate before the existing durable CAS.
    /// This method does not infer consent from an installation link or grant.
    /// </summary>
    internal InstallLinkingRookReadConsent GrantRookReadConsent(
        string userId,
        string subjectId,
        string installationId,
        string grantId,
        string workspaceId,
        long remoteRevision,
        string serverToken,
        string continuationDigest,
        bool explicitConfirmation,
        DateTimeOffset expiresAtUtc,
        Action<ClaimedInstallationDto> validateSelection,
        CancellationToken ct = default)
    {
        ct.ThrowIfCancellationRequested();
        InstallLinkingReadFenceCallback.Validate(validateSelection);
        if (!RookPrincipalAndGrantIdsValid(userId, subjectId, installationId, grantId)
            || !InstallLinkingRookReadConsent.IsIdentifier(workspaceId, 128)
            || remoteRevision <= 0
            || !InstallLinkingRookReadConsent.IsSha256(serverToken)
            || !InstallLinkingRookReadConsent.IsSha256(continuationDigest)
            || !explicitConfirmation)
        {
            throw new ArgumentException("Explicit Rook read consent requires a valid selected continuation.");
        }

        EnsureDurableStoreReady();
        InstallLinkingStore store = _store;
        lock (store.Gate)
        {
            ct.ThrowIfCancellationRequested();
            DateTimeOffset now = DateTimeOffset.UtcNow;
            if (!TryResolveRookGrantLocked(store, userId, subjectId, installationId, grantId,
                    now, out ClaimedInstallationDto? installation, out InstallationGrantDto? grant))
            {
                throw RookConsentDenied();
            }

            ValidateRookConsentExpiry(expiresAtUtc, now, grant!.ExpiresAtUtc);
            validateSelection(installation!);
            ct.ThrowIfCancellationRequested();
            now = DateTimeOffset.UtcNow;
            if (!TryResolveRookGrantLocked(store, userId, subjectId, installationId, grantId,
                    now, out ClaimedInstallationDto? currentInstallation, out InstallationGrantDto? currentGrant)
                || currentInstallation != installation || currentGrant != grant)
            {
                throw RookConsentDenied();
            }

            ValidateRookConsentExpiry(expiresAtUtc, now, grant.ExpiresAtUtc);
            if (!store.CanRetainNewRookReadConsentLocked(now))
            {
                throw new InvalidOperationException("Rook read consent capacity is unavailable.");
            }

            string consentId;
            do
            {
                consentId = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
            }
            while (store.RookReadConsentsById.ContainsKey(consentId));

            var consent = new InstallLinkingRookReadConsent(
                consentId, 1, userId, subjectId, installationId, grantId, workspaceId,
                remoteRevision, serverToken, continuationDigest,
                InstallLinkingRookReadConsent.RequiredPurpose, now, expiresAtUtc.ToUniversalTime(), null);
            ct.ThrowIfCancellationRequested();
            store.RookReadConsentsById.Add(consent.ConsentId, consent);
            // PersistLocked owns rollback to the previous committed snapshot on write/CAS
            // failure. This is the commit boundary: cancellation cannot preempt synchronous
            // persistence, and a successful commit always returns its exact durable record,
            // even if cancellation or expiry happens during persistence. Capture revalidates.
            store.PersistLocked();
            return consent;
        }
    }

    /// <summary>
    /// Revocation remains available after the bound grant expires, rotates, or is revoked.
    /// A retry with the current already-revoked version is unchanged; an older version fails.
    /// </summary>
    internal InstallLinkingRookReadConsent RevokeRookReadConsent(
        string userId,
        string subjectId,
        string consentId,
        long expectedVersion,
        CancellationToken ct = default)
    {
        ct.ThrowIfCancellationRequested();
        if (!InstallLinkingRookReadConsent.IsIdentifier(userId, 128)
            || !InstallLinkingRookReadConsent.IsIdentifier(subjectId, 128)
            || !InstallLinkingRookReadConsent.IsSha256(consentId)
            || expectedVersion < 1)
        {
            throw new ArgumentException("The Rook read consent revocation request is invalid.");
        }

        EnsureDurableStoreReady();
        InstallLinkingStore store = _store;
        lock (store.Gate)
        {
            ct.ThrowIfCancellationRequested();
            if (!store.RookReadConsentsById.TryGetValue(consentId, out InstallLinkingRookReadConsent? consent)
                || !InstallLinkingRookReadConsent.ShapeIsValid(consent)
                || consent.Version != expectedVersion
                || !string.Equals(consent.UserId, userId, StringComparison.Ordinal)
                || !string.Equals(consent.SubjectId, subjectId, StringComparison.Ordinal))
            {
                throw RookConsentDenied();
            }

            if (consent.RevokedAtUtc is not null)
            {
                return consent;
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            if (now < consent.IssuedAtUtc)
            {
                throw RookConsentDenied();
            }

            InstallLinkingRookReadConsent revoked = consent with
            {
                Version = checked(consent.Version + 1),
                RevokedAtUtc = now
            };
            ct.ThrowIfCancellationRequested();
            store.RookReadConsentsById[consentId] = revoked;
            // The same commit boundary as grant: report a durable success even if the
            // cancellation token changes while synchronous persistence is in progress.
            store.PersistLocked();
            return revoked;
        }
    }

    /// <summary>
    /// Captures only under local store gate -> authoritative PostgreSQL row -> snapshot gate.
    /// The callback is trusted bounded synchronous read-only work, may run on another thread,
    /// and must not acquire the local store gate or perform async/HTTP work. The caller MUST
    /// discard every callback output unless this method returns true; cancellation or failed
    /// cleanup can reject a capture after its callback ran. No grant data or future lease is
    /// returned. Fresh session/account admission remains the caller's separate obligation.
    /// </summary>
    internal bool CaptureRookReadConsent(
        string userId,
        string subjectId,
        string installationId,
        string grantId,
        string consentId,
        long expectedVersion,
        Action<InstallLinkingRookReadConsent, ClaimedInstallationDto> capture,
        CancellationToken ct = default)
    {
        ct.ThrowIfCancellationRequested();
        InstallLinkingReadFenceCallback.Validate(capture);
        if (!RookPrincipalAndGrantIdsValid(userId, subjectId, installationId, grantId)
            || !InstallLinkingRookReadConsent.IsSha256(consentId)
            || expectedVersion < 1)
        {
            return false;
        }

        if (!IsDurableStoreReady())
        {
            return false;
        }

        InstallLinkingStore store = _store;
        if (!store.IsHealthy)
        {
            return false;
        }

        lock (store.Gate)
        {
            ct.ThrowIfCancellationRequested();
            bool captured = false;
            DateTimeOffset admittedExpiry = default;
            bool fenced = store.ReadRookConsentFencedLocked(() =>
            {
                // Do not reacquire Gate here: the calling thread already holds it while
                // the fence may invoke this callback on a different thread.
                ct.ThrowIfCancellationRequested();
                if (!TryResolveRookConsentLocked(store, userId, subjectId, installationId,
                        grantId, consentId, expectedVersion, DateTimeOffset.UtcNow,
                        out InstallLinkingRookReadConsent? consent,
                        out ClaimedInstallationDto? installation, out InstallationGrantDto? grant))
                {
                    return;
                }

                capture(consent!, installation!);
                ct.ThrowIfCancellationRequested();
                if (!TryResolveRookConsentLocked(store, userId, subjectId, installationId,
                        grantId, consentId, expectedVersion, DateTimeOffset.UtcNow,
                        out InstallLinkingRookReadConsent? afterConsent,
                        out ClaimedInstallationDto? afterInstallation, out InstallationGrantDto? afterGrant)
                    || afterConsent != consent || afterInstallation != installation || afterGrant != grant)
                {
                    return;
                }

                admittedExpiry = consent!.ExpiresAtUtc;
                captured = true;
            }, ct);
            ct.ThrowIfCancellationRequested();
            return fenced && captured && admittedExpiry > DateTimeOffset.UtcNow;
        }
    }

    private static bool RookPrincipalAndGrantIdsValid(
        string userId, string subjectId, string installationId, string grantId)
        => InstallLinkingRookReadConsent.IsIdentifier(userId, 128)
           && InstallLinkingRookReadConsent.IsIdentifier(subjectId, 128)
           && InstallLinkingRookReadConsent.IsIdentifier(installationId, MaxInstallationIdLength)
           && InstallLinkingRookReadConsent.IsIdentifier(grantId, MaxGrantIdLength);

    private static void ValidateRookConsentExpiry(
        DateTimeOffset expiresAtUtc, DateTimeOffset now, DateTimeOffset grantExpiry)
    {
        if (expiresAtUtc <= now
            || expiresAtUtc - now > InstallLinkingRookReadConsent.MaximumLifetime
            || expiresAtUtc > grantExpiry)
        {
            throw new ArgumentException("The Rook read consent expiry is invalid.");
        }
    }

    private static bool TryResolveRookGrantLocked(
        InstallLinkingStore store, string userId, string subjectId, string installationId,
        string grantId, DateTimeOffset now, out ClaimedInstallationDto? installation,
        out InstallationGrantDto? grant)
    {
        grant = null;
        if (!store.IsHealthy
            || !store.InstallationsById.TryGetValue(installationId, out installation)
            || installation is null
            || !string.Equals(installation.InstallationId, installationId, StringComparison.Ordinal)
            || !string.Equals(installation.GrantId, grantId, StringComparison.Ordinal)
            || !string.Equals(installation.Status, ClaimedInstallationStates.Active, StringComparison.Ordinal)
            || !string.Equals(installation.UserId, userId, StringComparison.Ordinal)
            || !string.Equals(installation.SubjectId, subjectId, StringComparison.Ordinal)
            || !store.GrantsById.TryGetValue(grantId, out grant)
            || grant is null
            || !string.Equals(grant.GrantId, grantId, StringComparison.Ordinal)
            || !string.Equals(grant.InstallationId, installationId, StringComparison.Ordinal)
            || !string.Equals(grant.UserId, userId, StringComparison.Ordinal)
            || !string.Equals(grant.SubjectId, subjectId, StringComparison.Ordinal)
            || !string.Equals(grant.Status, InstallationGrantStates.Active, StringComparison.Ordinal)
            || grant.IssuedAtUtc > now || grant.ExpiresAtUtc <= now
            || !store.GrantTransportAuthoritiesByGrantId.TryGetValue(grantId,
                out InstallationGrantTransportAuthority? transport)
            || transport is null
            || !string.Equals(transport.GrantId, grantId, StringComparison.Ordinal)
            || !string.Equals(transport.Transport, InstallationGrantTransports.AndroidLinkedV2,
                StringComparison.Ordinal))
        {
            installation = null;
            grant = null;
            return false;
        }

        return true;
    }

    private static bool TryResolveRookConsentLocked(
        InstallLinkingStore store, string userId, string subjectId, string installationId,
        string grantId, string consentId, long expectedVersion, DateTimeOffset now,
        out InstallLinkingRookReadConsent? consent, out ClaimedInstallationDto? installation,
        out InstallationGrantDto? grant)
    {
        installation = null;
        grant = null;
        if (!store.RookReadConsentsById.TryGetValue(consentId, out consent)
            || !InstallLinkingRookReadConsent.ShapeIsValid(consent)
            || !string.Equals(consent.ConsentId, consentId, StringComparison.Ordinal)
            || consent.Version != expectedVersion || consent.RevokedAtUtc is not null
            || consent.IssuedAtUtc > now || consent.ExpiresAtUtc <= now
            || !string.Equals(consent.UserId, userId, StringComparison.Ordinal)
            || !string.Equals(consent.SubjectId, subjectId, StringComparison.Ordinal)
            || !string.Equals(consent.InstallationId, installationId, StringComparison.Ordinal)
            || !string.Equals(consent.GrantId, grantId, StringComparison.Ordinal)
            || !TryResolveRookGrantLocked(store, userId, subjectId, installationId, grantId,
                now, out installation, out grant)
            || consent.ExpiresAtUtc > grant!.ExpiresAtUtc)
        {
            consent = null;
            return false;
        }

        return true;
    }

    private static InvalidOperationException RookConsentDenied()
        => new("Rook read consent is unavailable for the current owner and grant.");
}
