using System.Security.Cryptography;
using System.Runtime.CompilerServices;
using Npgsql;
using NpgsqlTypes;

namespace Chummer.Run.Api.Services.Community.Postgres;

/// <summary>
/// Process-local provider-call registry. Lanes are keyed by provider object identity so
/// separately constructed reconcilers cannot multiply a non-cooperative provider call. Runtime
/// activation must satisfy <see cref="PlayAuthorizationCheckpointProviderActivationContract"/>;
/// transient or scoped provider wrappers would create distinct identities and are forbidden.
/// </summary>
public sealed class PlayAuthorizationCheckpointProviderCallRegistry
{
    private static readonly ConditionalWeakTable<
        IPlayAuthorizationCheckpointAuthority,
        ProviderCallLanes> _providers = new();

    internal ProviderCallLanes For(IPlayAuthorizationCheckpointAuthority provider)
        => _providers.GetValue(provider, static _ => new ProviderCallLanes());

    internal sealed class ProviderCallLanes
    {
        public ProviderCallLane Validation { get; } = new();
        public ProviderCallLane Baseline { get; } = new();
        public ProviderCallLane Publication { get; } = new();
    }

    internal sealed class ProviderCallLane
    {
        private readonly object _gate = new();
        private object? _active;

        public int ActiveCount
        {
            get
            {
                lock (_gate)
                {
                    return _active is null ? 0 : 1;
                }
            }
        }

        public ProviderCallReservation<T>? TryReserve<T>()
        {
            lock (_gate)
            {
                if (_active is not null)
                {
                    return null;
                }

                var reservation = new ProviderCallReservation<T>(this);
                _active = reservation;
                return reservation;
            }
        }

        internal void Complete(object reservation)
        {
            lock (_gate)
            {
                if (ReferenceEquals(_active, reservation))
                {
                    _active = null;
                }
            }
        }
    }

    internal sealed class ProviderCallReservation<T>
    {
        private readonly ProviderCallLane _lane;
        private readonly TaskCompletionSource<T> _completion = new(
            TaskCreationOptions.RunContinuationsAsynchronously);
        private Func<Task<T>>? _start;
        private int _scheduled;

        public ProviderCallReservation(ProviderCallLane lane)
        {
            _lane = lane;
        }

        public Task<T> Task => _completion.Task;

        public bool Schedule(Func<Task<T>> start)
        {
            ArgumentNullException.ThrowIfNull(start);
            if (Interlocked.CompareExchange(ref _scheduled, 1, 0) != 0)
            {
                throw new InvalidOperationException(
                    "The provider-call reservation is no longer available for scheduling.");
            }

            _start = start;
            try
            {
                if (ThreadPool.QueueUserWorkItem(
                        static (ProviderCallReservation<T> reservation) =>
                            reservation.Execute(),
                        this,
                        preferLocal: false))
                {
                    return true;
                }

                FailScheduling(new InvalidOperationException(
                    "The provider-call reservation could not be scheduled."));
                return false;
            }
            catch (Exception exception)
            {
                FailScheduling(exception);
                return false;
            }
        }

        public void Abort()
        {
            if (Interlocked.CompareExchange(ref _scheduled, -1, 0) != 0)
            {
                throw new InvalidOperationException(
                    "A scheduled provider-call reservation cannot be aborted.");
            }

            _start = null;
            _lane.Complete(this);
            _completion.TrySetCanceled();
        }

        private void Execute() => _ = ExecuteAsync();

        private async Task ExecuteAsync()
        {
            try
            {
                Func<Task<T>> start = Interlocked.Exchange(ref _start, null)
                    ?? throw new InvalidOperationException(
                        "The provider-call reservation has no scheduled invocation.");
                T result = await start();
                _lane.Complete(this);
                _completion.TrySetResult(result);
            }
            catch (OperationCanceledException exception)
            {
                _lane.Complete(this);
                _completion.TrySetCanceled(exception.CancellationToken);
            }
            catch (Exception exception)
            {
                _lane.Complete(this);
                _completion.TrySetException(exception);
            }
        }

        private void FailScheduling(Exception exception)
        {
            _start = null;
            _lane.Complete(this);
            _completion.TrySetException(exception);
        }
    }
}

/// <summary>
/// Reconciles the quarantined upgrade baseline and checkpoint publications. All database scopes
/// end before an external authority call starts; claims and acknowledgements are finalized in
/// separate, bounded transactions.
/// </summary>
public sealed class NpgsqlPlayAuthorizationCheckpointPublicationReconciler :
    IPlayAuthorizationCheckpointPublicationReconciler
{
    private const long ClaimLockKey = 0x504C415943484B50;
    private readonly NpgsqlDataSource _dataSource;
    private readonly PlayAuthorizationCheckpointProviderActivation _checkpointProvider;
    private readonly PlayAuthorizationCheckpointProviderCapabilities _providerCapabilities;
    private readonly IPlayAuthorizationEpochAuthority _epochAuthority;
    private readonly PlayAuthorizationCheckpointPublicationPolicy _policy;
    private readonly TimeProvider _timeProvider;
    private NpgsqlPlayAuthorizationCheckpointPublicationReconciler(
        NpgsqlDataSource dataSource,
        PlayAuthorizationCheckpointProviderActivation checkpointProvider,
        IPlayAuthorizationEpochAuthority epochAuthority,
        PlayAuthorizationCheckpointPublicationPolicy policy,
        TimeProvider timeProvider)
    {
        _dataSource = dataSource ?? throw new ArgumentNullException(nameof(dataSource));
        _checkpointProvider = checkpointProvider
            ?? throw new ArgumentNullException(nameof(checkpointProvider));
        _providerCapabilities = _checkpointProvider.Capabilities;
        _epochAuthority = epochAuthority ?? throw new ArgumentNullException(nameof(epochAuthority));
        _policy = policy ?? throw new ArgumentNullException(nameof(policy));
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        PlayAuthorizationCheckpointProviderDeadline.Validate(_providerCapabilities);
        TimeSpan requiredLease = _providerCapabilities.HardDeadline
            + _policy.DatabaseFinalizationDeadline
            + _policy.ClockSkew;
        if (_policy.ClaimLease < requiredLease)
        {
            throw new InvalidOperationException(
                "The checkpoint claim lease is shorter than the provider deadline, finalization deadline, and skew.");
        }
    }

    internal static NpgsqlPlayAuthorizationCheckpointPublicationReconciler Create(
        object factoryLease,
        PlayAuthorizationCheckpointProviderActivation checkpointProvider,
        NpgsqlDataSource dataSource,
        IPlayAuthorizationEpochAuthority epochAuthority,
        PlayAuthorizationCheckpointPublicationPolicy policy,
        TimeProvider timeProvider)
    {
        PlayAuthorizationPostgresDormantFactory.DemandConstructionLease(
            factoryLease,
            checkpointProvider);
        return new(
            dataSource,
            checkpointProvider,
            epochAuthority,
            policy,
            timeProvider);
    }

    public PlayAuthorizationCheckpointProviderCallDiagnostics ProviderCallDiagnostics
    {
        get
        {
            _checkpointProvider.DemandOpen();
            return _checkpointProvider.Diagnostics;
        }
    }

    public async Task<PlayAuthorizationCheckpointReconciliationResult> ReconcileAsync(
        int maximumPublications,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        if (maximumPublications is < 1 or > 256)
        {
            throw new ArgumentOutOfRangeException(nameof(maximumPublications));
        }

        BaselineResult baseline = await EnsureBaselineVerifiedAsync(cancellationToken);
        if (!baseline.Verified)
        {
            return new(0, 1, null, baseline.Code);
        }

        int publishedCount = 0;
        string code = "complete";
        for (int attempt = 0; attempt < maximumPublications; attempt++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (_checkpointProvider.Diagnostics.PublicationCallsInFlight != 0)
            {
                PendingSnapshot retainedPending = await ReadPendingSnapshotAsync(cancellationToken);
                return new(
                    publishedCount,
                    retainedPending.Count,
                    retainedPending.OldestSequence,
                    "publication_provider_call_in_flight");
            }

            PublicationClaimResult claimResult = await ClaimOldestPendingAsync(cancellationToken);
            if (claimResult.Claim is null)
            {
                code = claimResult.Code;
                break;
            }

            using PublicationClaim claim = claimResult.Claim!;
            byte[] canonicalDigest = PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
                claim.Envelope.PublicationId,
                claim.Envelope.State,
                claim.Envelope.DigestAlgorithm,
                claim.Envelope.CanonicalVersion);
            bool storedPayloadIsCanonical;
            try
            {
                storedPayloadIsCanonical = CryptographicOperations.FixedTimeEquals(
                    canonicalDigest,
                    claim.Envelope.PayloadDigestSha256);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(canonicalDigest);
            }

            if (!storedPayloadIsCanonical)
            {
                await ReleaseFailedClaimAsync(claim, "payload_digest_mismatch", cancellationToken);
                code = "payload_digest_mismatch";
                break;
            }

            PlayAuthorizationCheckpointPublicationProviderResult providerResult;
            try
            {
                providerResult = await _checkpointProvider.PublishAsync(
                    claim.Envelope,
                    _timeProvider,
                    cancellationToken);
            }
            catch (PlayAuthorizationCheckpointProviderCallInFlightException exception)
                when (exception.Lane
                    == PlayAuthorizationCheckpointProviderLaneKind.Publication)
            {
                await ReleaseFailedClaimAsync(
                    claim,
                    "provider_call_in_flight",
                    cancellationToken);
                code = "publication_provider_call_in_flight";
                break;
            }
            catch (PlayAuthorizationProviderDeadlineExceededException)
            {
                // The provider may still be running despite cancellation. Keep the lease intact;
                // no database scope is opened while that late call may complete.
                return new(publishedCount, 1, claim.Envelope.State.AuditHeadSequence,
                    "provider_deadline_exceeded");
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception exception) when (!IsFatal(exception))
            {
                await ReleaseFailedClaimAsync(claim, "authority_failure", cancellationToken);
                code = "authority_failure";
                break;
            }

            if (!providerResult.Exact || !providerResult.Accepted)
            {
                code = !providerResult.Exact
                    ? "acknowledgement_mismatch"
                    : providerResult.Disposition switch
                    {
                        PlayAuthorizationCheckpointPublicationDisposition.RejectedOutOfOrder =>
                            "rejected_out_of_order",
                        PlayAuthorizationCheckpointPublicationDisposition.RejectedAuthority =>
                            "rejected_authority",
                        _ => "rejected"
                    };
                await ReleaseFailedClaimAsync(claim, code, cancellationToken);
                break;
            }

            if (!await FinalizePublishedClaimAsync(claim, cancellationToken))
            {
                code = "finalize_conflict";
                break;
            }

            publishedCount++;
        }

        PendingSnapshot pending = await ReadPendingSnapshotAsync(cancellationToken);
        string finalCode = pending.Count == 0
            ? "complete"
            : string.Equals(code, "complete", StringComparison.Ordinal)
                ? "batch_limit"
                : code;
        return new(publishedCount, pending.Count, pending.OldestSequence, finalCode);
    }

    public async Task<bool> IsPublishedAsync(
        long auditSequence,
        long epoch,
        long generation,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        if (auditSequence <= 0 || epoch <= 0 || generation <= 0)
        {
            return false;
        }

        using CancellationTokenSource timeout =
            new(_policy.DatabaseFinalizationDeadline, _timeProvider);
        using CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            timeout.Token);
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(deadline.Token);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            SELECT EXISTS (
                SELECT 1
                FROM play_auth.checkpoint_publications
                WHERE audit_sequence = @sequence
                  AND epoch = @epoch
                  AND generation = @generation
                  AND state = 'published')
            """;
        command.Parameters.AddWithValue("sequence", auditSequence);
        command.Parameters.AddWithValue("epoch", epoch);
        command.Parameters.AddWithValue("generation", generation);
        return Convert.ToBoolean(await command.ExecuteScalarAsync(deadline.Token));
    }

    private async Task<BaselineResult> EnsureBaselineVerifiedAsync(CancellationToken cancellationToken)
    {
        if (_checkpointProvider.Diagnostics.BaselineCallsInFlight != 0)
        {
            return new(false, "baseline_provider_call_in_flight");
        }

        for (int attempt = 0; attempt < 4; attempt++)
        {
            using BaselineSnapshot snapshot = await ReadBaselineSnapshotAsync(cancellationToken);
            if (snapshot.State == "verified")
            {
                return BaselineAnchorsAuthority(snapshot)
                    ? new(true, "baseline_verified")
                    : new(false, "baseline_state_mismatch");
            }

            if (!StatesEqual(snapshot.BaselineState, snapshot.AuthorityState))
            {
                if (!await RefreshUnprovisionedBaselineAsync(snapshot, cancellationToken))
                {
                    return new(false, "baseline_state_mismatch");
                }

                continue;
            }

            if (snapshot.AuthorityState.Epoch <= 0
                || snapshot.AuthorityState.Generation <= 0
                || snapshot.AuthorityState.ExternalCheckpoint.Length == 0)
            {
                return new(false, "baseline_unprovisioned");
            }

            byte[] expectedDigest = PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
                snapshot.BaselineId,
                snapshot.BaselineState,
                snapshot.DigestAlgorithm,
                snapshot.CanonicalVersion);
            try
            {
                if (snapshot.PayloadDigestSha256 is null)
                {
                    bool stored = await StoreBaselineDigestAsync(
                        snapshot,
                        expectedDigest,
                        cancellationToken);
                    if (!stored)
                    {
                        continue;
                    }

                    continue;
                }

                if (!CryptographicOperations.FixedTimeEquals(
                        expectedDigest,
                        snapshot.PayloadDigestSha256))
                {
                    return new(false, "baseline_digest_mismatch");
                }
            }
            finally
            {
                CryptographicOperations.ZeroMemory(expectedDigest);
            }

            PlayAuthorizationExternalEpoch external =
                await _epochAuthority.ReadCurrentAsync(cancellationToken);
            if (external.Epoch != snapshot.BaselineState.Epoch
                || external.Generation != snapshot.BaselineState.Generation
                || !CryptographicOperations.FixedTimeEquals(
                    external.Checkpoint,
                    snapshot.BaselineState.ExternalCheckpoint))
            {
                return new(false, "baseline_authority_mismatch");
            }

            var verification = new PlayAuthorizationCheckpointBaselineVerification(
                snapshot.BaselineId,
                snapshot.BaselineState,
                snapshot.DigestAlgorithm,
                snapshot.CanonicalVersion,
                snapshot.PayloadDigestSha256
                    ?? throw new InvalidOperationException(
                        "The stored baseline payload digest disappeared during verification."));
            PlayAuthorizationCheckpointBaselineProviderResult providerResult;
            try
            {
                providerResult = await _checkpointProvider.VerifyBaselineAsync(
                    verification,
                    external,
                    _timeProvider,
                    cancellationToken);
            }
            catch (PlayAuthorizationCheckpointProviderCallInFlightException exception)
                when (exception.Lane == PlayAuthorizationCheckpointProviderLaneKind.Baseline)
            {
                return new(false, "baseline_provider_call_in_flight");
            }
            catch (PlayAuthorizationProviderDeadlineExceededException)
            {
                return new(false, "baseline_provider_deadline_exceeded");
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception exception) when (!IsFatal(exception))
            {
                return new(false, "baseline_authority_failure");
            }

            if (!providerResult.Exact || !providerResult.Accepted)
            {
                return new(false, "baseline_acknowledgement_mismatch");
            }

            if (await FinalizeBaselineAsync(snapshot, cancellationToken))
            {
                return new(true, "baseline_verified");
            }
        }

        return new(false, "baseline_retry_exhausted");
    }

    private async Task<BaselineSnapshot> ReadBaselineSnapshotAsync(CancellationToken cancellationToken)
    {
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            SELECT baseline.baseline_id, baseline.epoch, baseline.generation,
                   baseline.clock_high_water_utc, baseline.audit_head_sequence,
                   baseline.audit_head_hmac, baseline.external_checkpoint,
                   baseline.digest_algorithm, baseline.canonical_version,
                   baseline.payload_digest_sha256, baseline.state,
                   authority.epoch, authority.generation, authority.clock_high_water_utc,
                   authority.audit_head_sequence, authority.audit_head_hmac,
                   authority.external_checkpoint,
                   baseline.epoch = authority.epoch
                     AND baseline.generation = authority.generation
                     AND baseline.audit_head_sequence <= authority.audit_head_sequence
                     AND baseline.clock_high_water_utc <= authority.clock_high_water_utc
                     AND baseline.external_checkpoint = authority.external_checkpoint
                     AND (
                       (baseline.audit_head_sequence = authority.audit_head_sequence
                         AND baseline.clock_high_water_utc = authority.clock_high_water_utc
                         AND baseline.audit_head_hmac = authority.audit_head_hmac)
                       OR
                       (baseline.audit_head_sequence < authority.audit_head_sequence
                         AND EXISTS (
                           SELECT 1
                           FROM play_auth.audit_log AS audit
                           JOIN play_auth.checkpoint_publications AS publication
                             ON publication.audit_sequence = audit.sequence
                           WHERE audit.sequence = authority.audit_head_sequence
                             AND audit.epoch = authority.epoch
                             AND audit.generation = authority.generation
                             AND audit.entry_hmac = authority.audit_head_hmac
                             AND publication.epoch = authority.epoch
                             AND publication.generation = authority.generation
                             AND publication.clock_high_water_utc = authority.clock_high_water_utc
                             AND publication.audit_head_hmac = authority.audit_head_hmac
                             AND publication.external_checkpoint = authority.external_checkpoint)))
                     AS lineage_valid
            FROM play_auth.checkpoint_baseline AS baseline
            CROSS JOIN play_auth.authority_state AS authority
            WHERE baseline.singleton = true AND authority.singleton = true
            """;
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException("The checkpoint baseline is missing.");
        }

        PlayAuthorizationPostgresState? baselineState = null;
        PlayAuthorizationPostgresState? authorityState = null;
        bool transferred = false;
        try
        {
            baselineState = ReadState(reader, 1);
            authorityState = ReadState(reader, 11);
            var snapshot = new BaselineSnapshot(
                reader.GetGuid(0),
                baselineState!,
                reader.GetString(7),
                reader.GetInt32(8),
                reader.IsDBNull(9) ? null : (byte[])reader[9],
                reader.GetString(10),
                authorityState!,
                reader.GetBoolean(17));
            transferred = true;
            return snapshot;
        }
        finally
        {
            if (!transferred)
            {
                if (baselineState is not null)
                {
                    ZeroState(baselineState);
                }

                if (authorityState is not null)
                {
                    ZeroState(authorityState);
                }
            }
        }
    }

    private async Task<bool> RefreshUnprovisionedBaselineAsync(
        BaselineSnapshot snapshot,
        CancellationToken cancellationToken)
    {
        if (!string.Equals(snapshot.State, "quarantined", StringComparison.Ordinal)
            || snapshot.BaselineState.AuditHeadSequence != 0
            || snapshot.AuthorityState.AuditHeadSequence != 0)
        {
            return false;
        }

        Guid replacementId = Guid.NewGuid();
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlTransaction transaction = await connection.BeginTransactionAsync(cancellationToken);
        PlayAuthorizationPostgresState locked = await PlayAuthorizationPostgresReadinessProbe.ReadStateAsync(
            connection,
            cancellationToken,
            transaction,
            forUpdate: true);
        try
        {
            if (!StatesEqual(locked, snapshot.AuthorityState))
            {
                await transaction.RollbackAsync(cancellationToken);
                return false;
            }

            await using NpgsqlCommand command = connection.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = """
                UPDATE play_auth.checkpoint_baseline
                SET baseline_id = @baseline_id,
                    epoch = @epoch,
                    generation = @generation,
                    clock_high_water_utc = @clock,
                    audit_head_sequence = @sequence,
                    audit_head_hmac = @hmac,
                    external_checkpoint = @checkpoint,
                    payload_digest_sha256 = NULL,
                    captured_at_utc = GREATEST(clock_timestamp(), @clock)
                WHERE singleton = true
                  AND state = 'quarantined'
                  AND audit_head_sequence = 0
                  AND NOT EXISTS (SELECT 1 FROM play_auth.audit_log)
                  AND NOT EXISTS (SELECT 1 FROM play_auth.checkpoint_publications)
                """;
            command.Parameters.AddWithValue("baseline_id", replacementId);
            BindState(command, locked);
            bool changed = await command.ExecuteNonQueryAsync(cancellationToken) == 1;
            if (changed)
            {
                await transaction.CommitAsync(cancellationToken);
            }
            else
            {
                await transaction.RollbackAsync(cancellationToken);
            }

            return changed;
        }
        finally
        {
            ZeroState(locked);
        }
    }

    private async Task<bool> StoreBaselineDigestAsync(
        BaselineSnapshot snapshot,
        byte[] digest,
        CancellationToken cancellationToken)
    {
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            UPDATE play_auth.checkpoint_baseline
            SET payload_digest_sha256 = @digest
            WHERE singleton = true
              AND state = 'quarantined'
              AND baseline_id = @baseline_id
              AND epoch = @epoch
              AND generation = @generation
              AND clock_high_water_utc = @clock
              AND audit_head_sequence = @sequence
              AND audit_head_hmac = @hmac
              AND external_checkpoint = @checkpoint
              AND digest_algorithm = @digest_algorithm
              AND canonical_version = @canonical_version
              AND payload_digest_sha256 IS NULL
            """;
        AddBytea(command, "digest", digest);
        command.Parameters.AddWithValue("baseline_id", snapshot.BaselineId);
        BindState(command, snapshot.BaselineState);
        command.Parameters.AddWithValue("digest_algorithm", snapshot.DigestAlgorithm);
        command.Parameters.AddWithValue("canonical_version", snapshot.CanonicalVersion);
        return await command.ExecuteNonQueryAsync(cancellationToken) == 1;
    }

    private async Task<bool> FinalizeBaselineAsync(
        BaselineSnapshot snapshot,
        CancellationToken cancellationToken)
    {
        using CancellationTokenSource timeout =
            new(_policy.DatabaseFinalizationDeadline, _timeProvider);
        using CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            timeout.Token);
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(deadline.Token);
        await using NpgsqlTransaction transaction = await connection.BeginTransactionAsync(deadline.Token);
        PlayAuthorizationPostgresState locked = await PlayAuthorizationPostgresReadinessProbe.ReadStateAsync(
            connection,
            deadline.Token,
            transaction,
            forUpdate: true);
        try
        {
            if (!StatesEqual(locked, snapshot.BaselineState))
            {
                await transaction.RollbackAsync(deadline.Token);
                return false;
            }

            await using NpgsqlCommand command = connection.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = """
                UPDATE play_auth.checkpoint_baseline
                SET state = 'verified',
                    verified_at_utc = GREATEST(clock_timestamp(), @clock)
                WHERE singleton = true
                  AND state = 'quarantined'
                  AND baseline_id = @baseline_id
                  AND epoch = @epoch
                  AND generation = @generation
                  AND clock_high_water_utc = @clock
                  AND audit_head_sequence = @sequence
                  AND audit_head_hmac = @hmac
                  AND external_checkpoint = @checkpoint
                  AND digest_algorithm = @digest_algorithm
                  AND canonical_version = @canonical_version
                  AND payload_digest_sha256 = @digest
                  AND NOT EXISTS (
                      SELECT 1 FROM play_auth.checkpoint_publications WHERE state = 'pending')
                """;
            command.Parameters.AddWithValue("baseline_id", snapshot.BaselineId);
            BindState(command, snapshot.BaselineState);
            command.Parameters.AddWithValue("digest_algorithm", snapshot.DigestAlgorithm);
            command.Parameters.AddWithValue("canonical_version", snapshot.CanonicalVersion);
            AddBytea(command, "digest", snapshot.PayloadDigestSha256!);
            bool changed = await command.ExecuteNonQueryAsync(deadline.Token) == 1;
            if (changed)
            {
                await transaction.CommitAsync(deadline.Token);
            }
            else
            {
                await transaction.RollbackAsync(deadline.Token);
            }

            return changed;
        }
        finally
        {
            ZeroState(locked);
        }
    }

    private async Task<PublicationClaimResult> ClaimOldestPendingAsync(
        CancellationToken cancellationToken)
    {
        using CancellationTokenSource timeout =
            new(_policy.DatabaseFinalizationDeadline, _timeProvider);
        using CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            timeout.Token);
        Guid owner = Guid.NewGuid();
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(deadline.Token);
        await using NpgsqlTransaction transaction = await connection.BeginTransactionAsync(deadline.Token);
        await using (NpgsqlCommand advisoryLock = connection.CreateCommand())
        {
            advisoryLock.Transaction = transaction;
            advisoryLock.CommandText = "SELECT pg_advisory_xact_lock(@key)";
            advisoryLock.Parameters.AddWithValue("key", ClaimLockKey);
            await advisoryLock.ExecuteNonQueryAsync(deadline.Token);
        }

        PublicationClaim? candidate = null;
        bool transferCandidate = false;
        bool candidateMatchesAuthority = false;
        DateTimeOffset effectiveNow = default;
        DateTimeOffset? leaseExpiresAt = null;
        try
        {
            await using (NpgsqlCommand select = connection.CreateCommand())
            {
                select.Transaction = transaction;
                select.CommandText = """
                SELECT publication.audit_sequence, publication.publication_id,
                       publication.epoch, publication.generation,
                       publication.clock_high_water_utc, publication.audit_head_hmac,
                       publication.external_checkpoint, publication.digest_algorithm,
                       publication.canonical_version, publication.payload_digest_sha256,
                       publication.fencing_token, publication.lease_expires_at_utc,
                       GREATEST(clock_timestamp(), authority.clock_high_water_utc),
                       publication.epoch = authority.epoch
                         AND publication.generation = authority.generation
                         AND publication.clock_high_water_utc = authority.clock_high_water_utc
                         AND publication.audit_sequence = authority.audit_head_sequence
                         AND publication.audit_head_hmac = authority.audit_head_hmac
                         AND publication.external_checkpoint = authority.external_checkpoint
                FROM play_auth.checkpoint_publications AS publication
                CROSS JOIN play_auth.authority_state AS authority
                CROSS JOIN play_auth.checkpoint_baseline AS baseline
                WHERE publication.state = 'pending'
                  AND authority.singleton = true
                  AND baseline.singleton = true
                  AND baseline.state = 'verified'
                ORDER BY publication.audit_sequence
                LIMIT 1
                FOR UPDATE OF publication
                """;
                await using NpgsqlDataReader reader = await select.ExecuteReaderAsync(deadline.Token);
                if (await reader.ReadAsync(deadline.Token))
                {
                    effectiveNow = reader.GetFieldValue<DateTimeOffset>(12);
                    leaseExpiresAt = reader.IsDBNull(11)
                        ? null
                        : reader.GetFieldValue<DateTimeOffset>(11);
                    candidateMatchesAuthority = reader.GetBoolean(13);
                    long nextFence = checked(reader.GetInt64(10) + 1);
                    candidate = new PublicationClaim(
                        owner,
                        reader.GetGuid(1),
                        nextFence,
                        reader.GetInt64(2),
                        reader.GetInt64(3),
                        reader.GetFieldValue<DateTimeOffset>(4),
                        reader.GetInt64(0),
                        (byte[])reader[5],
                        (byte[])reader[6],
                        reader.GetString(7),
                        reader.GetInt32(8),
                        (byte[])reader[9]);
                }
            }

            if (candidate is null)
            {
                await transaction.CommitAsync(deadline.Token);
                return new(null, "complete");
            }

            if (!candidateMatchesAuthority)
            {
                await transaction.CommitAsync(deadline.Token);
                return new(null, "publication_head_mismatch");
            }

            if (leaseExpiresAt is not null && leaseExpiresAt > effectiveNow)
            {
                await transaction.CommitAsync(deadline.Token);
                return new(null, "lease_active");
            }

            await using (NpgsqlCommand claim = connection.CreateCommand())
            {
                claim.Transaction = transaction;
                claim.CommandText = """
                UPDATE play_auth.checkpoint_publications
                SET lease_owner = @owner,
                    lease_expires_at_utc = @lease_expires,
                    fencing_token = @fence,
                    attempt_count = attempt_count + 1,
                    last_attempt_at_utc = @now,
                    last_error_code = NULL
                WHERE audit_sequence = @sequence
                  AND publication_id = @publication_id
                  AND epoch = @epoch
                  AND generation = @generation
                  AND clock_high_water_utc = @clock
                  AND audit_head_hmac = @hmac
                  AND external_checkpoint = @checkpoint
                  AND digest_algorithm = @digest_algorithm
                  AND canonical_version = @canonical_version
                  AND payload_digest_sha256 = @digest
                  AND fencing_token = @previous_fence
                  AND state = 'pending'
                """;
                claim.Parameters.AddWithValue("owner", owner);
                claim.Parameters.AddWithValue("lease_expires", effectiveNow.Add(_policy.ClaimLease));
                claim.Parameters.AddWithValue("fence", candidate.Envelope.FencingToken);
                claim.Parameters.AddWithValue("previous_fence", candidate.Envelope.FencingToken - 1);
                claim.Parameters.AddWithValue("now", effectiveNow);
                claim.Parameters.AddWithValue("sequence", candidate.Envelope.State.AuditHeadSequence);
                claim.Parameters.AddWithValue("publication_id", candidate.Envelope.PublicationId);
                BindEnvelope(claim, candidate.Envelope);
                if (await claim.ExecuteNonQueryAsync(deadline.Token) != 1)
                {
                    await transaction.RollbackAsync(deadline.Token);
                    return new(null, "claim_conflict");
                }
            }

            await transaction.CommitAsync(deadline.Token);
            transferCandidate = true;
            return new(candidate, "claimed");
        }
        finally
        {
            if (!transferCandidate)
            {
                candidate?.Dispose();
            }
        }
    }

    private async Task<bool> FinalizePublishedClaimAsync(
        PublicationClaim claim,
        CancellationToken cancellationToken)
    {
        using CancellationTokenSource timeout =
            new(_policy.DatabaseFinalizationDeadline, _timeProvider);
        using CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            timeout.Token);
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(deadline.Token);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            UPDATE play_auth.checkpoint_publications AS publication
            SET state = 'published',
                lease_owner = NULL,
                lease_expires_at_utc = NULL,
                last_error_code = NULL,
                published_at_utc = GREATEST(
                    clock_timestamp(),
                    (SELECT clock_high_water_utc
                     FROM play_auth.authority_state
                     WHERE singleton = true))
            WHERE publication.audit_sequence = @sequence
              AND publication.publication_id = @publication_id
              AND publication.epoch = @epoch
              AND publication.generation = @generation
              AND publication.clock_high_water_utc = @clock
              AND publication.audit_head_hmac = @hmac
              AND publication.external_checkpoint = @checkpoint
              AND publication.digest_algorithm = @digest_algorithm
              AND publication.canonical_version = @canonical_version
              AND publication.fencing_token = @fence
              AND publication.payload_digest_sha256 = @digest
              AND publication.state = 'pending'
              AND publication.lease_owner = @owner
            """;
        command.Parameters.AddWithValue("sequence", claim.Envelope.State.AuditHeadSequence);
        command.Parameters.AddWithValue("publication_id", claim.Envelope.PublicationId);
        command.Parameters.AddWithValue("epoch", claim.Envelope.State.Epoch);
        command.Parameters.AddWithValue("generation", claim.Envelope.State.Generation);
        command.Parameters.AddWithValue("clock", claim.Envelope.State.ClockHighWaterUtc);
        AddBytea(command, "hmac", claim.Envelope.State.AuditHeadHmac);
        AddBytea(command, "checkpoint", claim.Envelope.State.ExternalCheckpoint);
        command.Parameters.AddWithValue("digest_algorithm", claim.Envelope.DigestAlgorithm);
        command.Parameters.AddWithValue("canonical_version", claim.Envelope.CanonicalVersion);
        command.Parameters.AddWithValue("fence", claim.Envelope.FencingToken);
        AddBytea(command, "digest", claim.Envelope.PayloadDigestSha256);
        command.Parameters.AddWithValue("owner", claim.Owner);
        return await command.ExecuteNonQueryAsync(deadline.Token) == 1;
    }

    private async Task ReleaseFailedClaimAsync(
        PublicationClaim claim,
        string errorCode,
        CancellationToken cancellationToken)
    {
        using CancellationTokenSource timeout =
            new(_policy.DatabaseFinalizationDeadline, _timeProvider);
        using CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            timeout.Token);
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(deadline.Token);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            UPDATE play_auth.checkpoint_publications
            SET lease_owner = NULL,
                lease_expires_at_utc = NULL,
                last_error_code = @error
            WHERE audit_sequence = @sequence
              AND publication_id = @publication_id
              AND epoch = @epoch
              AND generation = @generation
              AND clock_high_water_utc = @clock
              AND audit_head_hmac = @hmac
              AND external_checkpoint = @checkpoint
              AND digest_algorithm = @digest_algorithm
              AND canonical_version = @canonical_version
              AND payload_digest_sha256 = @digest
              AND fencing_token = @fence
              AND state = 'pending'
              AND lease_owner = @owner
            """;
        command.Parameters.AddWithValue("error", errorCode);
        command.Parameters.AddWithValue("sequence", claim.Envelope.State.AuditHeadSequence);
        command.Parameters.AddWithValue("publication_id", claim.Envelope.PublicationId);
        BindEnvelope(command, claim.Envelope);
        command.Parameters.AddWithValue("fence", claim.Envelope.FencingToken);
        command.Parameters.AddWithValue("owner", claim.Owner);
        await command.ExecuteNonQueryAsync(deadline.Token);
    }

    private async Task<PendingSnapshot> ReadPendingSnapshotAsync(CancellationToken cancellationToken)
    {
        using CancellationTokenSource timeout =
            new(_policy.DatabaseFinalizationDeadline, _timeProvider);
        using CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            timeout.Token);
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(deadline.Token);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            SELECT COUNT(*), MIN(audit_sequence)
            FROM play_auth.checkpoint_publications
            WHERE state = 'pending'
            """;
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(deadline.Token);
        if (!await reader.ReadAsync(deadline.Token))
        {
            throw new InvalidOperationException("PostgreSQL did not return checkpoint publication state.");
        }

        return new(reader.GetInt64(0), reader.IsDBNull(1) ? null : reader.GetInt64(1));
    }

    private static PlayAuthorizationPostgresState ReadState(NpgsqlDataReader reader, int start)
        => CopyState(new PlayAuthorizationPostgresState(
            reader.GetInt64(start),
            reader.GetInt64(start + 1),
            reader.GetFieldValue<DateTimeOffset>(start + 2),
            reader.GetInt64(start + 3),
            (byte[])reader[start + 4],
            (byte[])reader[start + 5]));

    private static PlayAuthorizationPostgresState CopyState(PlayAuthorizationPostgresState state)
    {
        byte[] auditHeadHmac = state.AuditHeadHmac.ToArray();
        byte[]? externalCheckpoint = null;
        try
        {
            externalCheckpoint = state.ExternalCheckpoint.ToArray();
            return new PlayAuthorizationPostgresState(
                state.Epoch,
                state.Generation,
                state.ClockHighWaterUtc,
                state.AuditHeadSequence,
                auditHeadHmac,
                externalCheckpoint);
        }
        catch
        {
            CryptographicOperations.ZeroMemory(auditHeadHmac);
            if (externalCheckpoint is not null)
            {
                CryptographicOperations.ZeroMemory(externalCheckpoint);
            }

            throw;
        }
    }

    private static void ZeroState(PlayAuthorizationPostgresState state)
    {
        CryptographicOperations.ZeroMemory(state.AuditHeadHmac);
        CryptographicOperations.ZeroMemory(state.ExternalCheckpoint);
    }

    private static void BindState(NpgsqlCommand command, PlayAuthorizationPostgresState state)
    {
        command.Parameters.AddWithValue("epoch", state.Epoch);
        command.Parameters.AddWithValue("generation", state.Generation);
        command.Parameters.AddWithValue("clock", state.ClockHighWaterUtc);
        command.Parameters.AddWithValue("sequence", state.AuditHeadSequence);
        AddBytea(command, "hmac", state.AuditHeadHmac);
        AddBytea(command, "checkpoint", state.ExternalCheckpoint);
    }

    private static void BindEnvelope(
        NpgsqlCommand command,
        PlayAuthorizationCheckpointPublicationEnvelope envelope)
    {
        command.Parameters.AddWithValue("epoch", envelope.State.Epoch);
        command.Parameters.AddWithValue("generation", envelope.State.Generation);
        command.Parameters.AddWithValue("clock", envelope.State.ClockHighWaterUtc);
        AddBytea(command, "hmac", envelope.State.AuditHeadHmac);
        AddBytea(command, "checkpoint", envelope.State.ExternalCheckpoint);
        command.Parameters.AddWithValue("digest_algorithm", envelope.DigestAlgorithm);
        command.Parameters.AddWithValue("canonical_version", envelope.CanonicalVersion);
        AddBytea(command, "digest", envelope.PayloadDigestSha256);
    }

    internal static bool StatesEqual(
        PlayAuthorizationPostgresState left,
        PlayAuthorizationPostgresState right)
        => left.Epoch == right.Epoch
           && left.Generation == right.Generation
           && left.ClockHighWaterUtc == right.ClockHighWaterUtc
           && left.AuditHeadSequence == right.AuditHeadSequence
           && left.AuditHeadHmac.Length == right.AuditHeadHmac.Length
           && CryptographicOperations.FixedTimeEquals(left.AuditHeadHmac, right.AuditHeadHmac)
           && left.ExternalCheckpoint.Length == right.ExternalCheckpoint.Length
           && CryptographicOperations.FixedTimeEquals(
               left.ExternalCheckpoint,
               right.ExternalCheckpoint);

    private static bool BaselineAnchorsAuthority(BaselineSnapshot snapshot)
        => snapshot.LineageValid
           && snapshot.BaselineState.Epoch == snapshot.AuthorityState.Epoch
           && snapshot.BaselineState.Generation == snapshot.AuthorityState.Generation
           && snapshot.BaselineState.AuditHeadSequence <= snapshot.AuthorityState.AuditHeadSequence
           && snapshot.BaselineState.ClockHighWaterUtc <= snapshot.AuthorityState.ClockHighWaterUtc
           && CryptographicOperations.FixedTimeEquals(
               snapshot.BaselineState.ExternalCheckpoint,
               snapshot.AuthorityState.ExternalCheckpoint)
           && (snapshot.BaselineState.AuditHeadSequence < snapshot.AuthorityState.AuditHeadSequence
               || StatesEqual(snapshot.BaselineState, snapshot.AuthorityState));

    private static bool IsFatal(Exception exception)
        => exception is OutOfMemoryException or StackOverflowException or AccessViolationException;

    private static void AddBytea(NpgsqlCommand command, string name, byte[] value)
        => command.Parameters.AddWithValue(name, NpgsqlDbType.Bytea, value);

    private sealed record BaselineResult(bool Verified, string Code);
    private sealed class BaselineSnapshot : IDisposable
    {
        private int _disposed;

        public BaselineSnapshot(
            Guid baselineId,
            PlayAuthorizationPostgresState baselineState,
            string digestAlgorithm,
            int canonicalVersion,
            byte[]? payloadDigestSha256,
            string state,
            PlayAuthorizationPostgresState authorityState,
            bool lineageValid)
        {
            byte[]? ownedPayloadDigest = null;
            try
            {
                ownedPayloadDigest = payloadDigestSha256?.ToArray();
                BaselineId = baselineId;
                BaselineState = baselineState;
                DigestAlgorithm = digestAlgorithm;
                CanonicalVersion = canonicalVersion;
                PayloadDigestSha256 = ownedPayloadDigest;
                State = state;
                AuthorityState = authorityState;
                LineageValid = lineageValid;
            }
            catch
            {
                ZeroState(baselineState);
                ZeroState(authorityState);
                if (ownedPayloadDigest is not null)
                {
                    CryptographicOperations.ZeroMemory(ownedPayloadDigest);
                }

                throw;
            }
        }

        public Guid BaselineId { get; }
        public PlayAuthorizationPostgresState BaselineState { get; }
        public string DigestAlgorithm { get; }
        public int CanonicalVersion { get; }
        public byte[]? PayloadDigestSha256 { get; }
        public string State { get; }
        public PlayAuthorizationPostgresState AuthorityState { get; }
        public bool LineageValid { get; }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0)
            {
                return;
            }

            ZeroState(BaselineState);
            ZeroState(AuthorityState);
            if (PayloadDigestSha256 is not null)
            {
                CryptographicOperations.ZeroMemory(PayloadDigestSha256);
            }
        }
    }

    private sealed class PublicationClaim : IDisposable
    {
        private int _disposed;

        public PublicationClaim(
            Guid owner,
            Guid publicationId,
            long fencingToken,
            long epoch,
            long generation,
            DateTimeOffset clockHighWaterUtc,
            long auditHeadSequence,
            byte[] auditHeadHmac,
            byte[] externalCheckpoint,
            string digestAlgorithm,
            int canonicalVersion,
            byte[] payloadDigestSha256)
        {
            PlayAuthorizationPostgresState? ownedState = null;
            byte[]? ownedPayloadDigest = null;
            try
            {
                ownedState = CopyState(new PlayAuthorizationPostgresState(
                    epoch,
                    generation,
                    clockHighWaterUtc,
                    auditHeadSequence,
                    auditHeadHmac,
                    externalCheckpoint));
                ownedPayloadDigest = payloadDigestSha256.ToArray();
                Owner = owner;
                Envelope = new PlayAuthorizationCheckpointPublicationEnvelope(
                    publicationId,
                    fencingToken,
                    ownedState!,
                    digestAlgorithm,
                    canonicalVersion,
                    ownedPayloadDigest!);
            }
            catch
            {
                if (ownedState is not null)
                {
                    ZeroState(ownedState);
                }

                if (ownedPayloadDigest is not null)
                {
                    CryptographicOperations.ZeroMemory(ownedPayloadDigest);
                }

                throw;
            }
        }

        public Guid Owner { get; }
        public PlayAuthorizationCheckpointPublicationEnvelope Envelope { get; }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0)
            {
                return;
            }

            ZeroState(Envelope.State);
            CryptographicOperations.ZeroMemory(Envelope.PayloadDigestSha256);
        }
    }

    private sealed record PublicationClaimResult(PublicationClaim? Claim, string Code);
    private sealed record PendingSnapshot(long Count, long? OldestSequence);
}

/// <summary>
/// Maintenance-identity operation. Ciphertext is scrubbed at expiry, identity is retained for at
/// least the configured replay/capability safety window plus skew, and the key becomes a new
/// idempotency identity only after bounded quarantine deletion.
/// </summary>
public sealed class NpgsqlPlayAuthorizationIdempotencyReceiptPruner :
    IPlayAuthorizationIdempotencyReceiptPruner
{
    private static readonly TimeSpan MaintenanceDeadline = TimeSpan.FromSeconds(10);
    private readonly NpgsqlDataSource _maintenanceDataSource;
    private readonly TimeSpan _quarantineRetention;
    private readonly TimeProvider _timeProvider;

    public NpgsqlPlayAuthorizationIdempotencyReceiptPruner(
        NpgsqlDataSource maintenanceDataSource,
        TimeSpan quarantineRetention,
        PlayAuthorizationReplaySafetyPolicy replaySafetyPolicy,
        TimeProvider timeProvider)
    {
        _maintenanceDataSource = maintenanceDataSource
            ?? throw new ArgumentNullException(nameof(maintenanceDataSource));
        ArgumentNullException.ThrowIfNull(replaySafetyPolicy);
        if (quarantineRetention < replaySafetyPolicy.MinimumQuarantine
            || quarantineRetention > TimeSpan.FromDays(365))
        {
            throw new ArgumentOutOfRangeException(nameof(quarantineRetention));
        }

        _quarantineRetention = quarantineRetention;
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
    }

    public async Task<PlayAuthorizationReceiptPruneResult> PruneExpiredAsync(
        int maximumReceipts,
        CancellationToken cancellationToken = default)
    {
        if (maximumReceipts is < 1 or > 1000)
        {
            throw new ArgumentOutOfRangeException(nameof(maximumReceipts));
        }

        using CancellationTokenSource timeout = new(MaintenanceDeadline, _timeProvider);
        using CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            timeout.Token);
        await using NpgsqlConnection connection =
            await _maintenanceDataSource.OpenConnectionAsync(deadline.Token);
        await using NpgsqlTransaction transaction = await connection.BeginTransactionAsync(deadline.Token);
        DateTimeOffset effectiveNow;
        await using (NpgsqlCommand clock = connection.CreateCommand())
        {
            clock.Transaction = transaction;
            clock.CommandText = """
                SELECT GREATEST(clock_timestamp(), clock_high_water_utc)
                FROM play_auth.authority_state
                WHERE singleton = true
                """;
            effectiveNow = ConvertDatabaseTime(await clock.ExecuteScalarAsync(deadline.Token));
        }

        int scrubbed = await ExecuteCountAsync(connection, transaction, """
            WITH target AS (
                SELECT receipt.scope_sha256, receipt.key_sha256
                FROM play_auth.idempotency_receipts AS receipt
                WHERE receipt.state = 'completed' AND receipt.expires_at_utc <= @now
                ORDER BY receipt.expires_at_utc, receipt.scope_sha256, receipt.key_sha256
                LIMIT @maximum
                FOR UPDATE OF receipt SKIP LOCKED
            ), changed AS (
                UPDATE play_auth.idempotency_receipts AS receipt
                SET state = 'pruned', response_type = NULL, response_status = NULL,
                    response_ciphertext = NULL, response_plaintext_sha256 = NULL,
                    audit_sequence = NULL, audit_event_id = NULL,
                    audit_payload_canonical_version = NULL,
                    audited_payload_sha256 = NULL,
                    pruned_at_utc = @now, quarantine_until_utc = @now + @quarantine
                FROM target
                WHERE receipt.scope_sha256 = target.scope_sha256
                  AND receipt.key_sha256 = target.key_sha256
                RETURNING 1)
            SELECT COUNT(*) FROM changed
            """, maximumReceipts, effectiveNow, includeQuarantine: true, deadline.Token);

        int deleted = await ExecuteCountAsync(connection, transaction, """
            WITH target AS (
                SELECT receipt.scope_sha256, receipt.key_sha256
                FROM play_auth.idempotency_receipts AS receipt
                WHERE receipt.state = 'pruned' AND receipt.quarantine_until_utc <= @now
                ORDER BY receipt.quarantine_until_utc, receipt.scope_sha256, receipt.key_sha256
                LIMIT @maximum
                FOR UPDATE OF receipt SKIP LOCKED
            ), changed AS (
                DELETE FROM play_auth.idempotency_receipts AS receipt USING target
                WHERE receipt.scope_sha256 = target.scope_sha256
                  AND receipt.key_sha256 = target.key_sha256
                RETURNING 1)
            SELECT COUNT(*) FROM changed
            """, maximumReceipts, effectiveNow, includeQuarantine: false, deadline.Token);

        await transaction.CommitAsync(deadline.Token);
        return new(scrubbed, deleted, effectiveNow);
    }

    private async Task<int> ExecuteCountAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        string sql,
        int maximum,
        DateTimeOffset now,
        bool includeQuarantine,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = sql;
        command.Parameters.AddWithValue("maximum", maximum);
        command.Parameters.AddWithValue("now", now);
        if (includeQuarantine)
        {
            command.Parameters.AddWithValue("quarantine", NpgsqlDbType.Interval, _quarantineRetention);
        }

        return Convert.ToInt32(await command.ExecuteScalarAsync(cancellationToken));
    }

    private static DateTimeOffset ConvertDatabaseTime(object? value)
        => value switch
        {
            DateTime dateTime => new DateTimeOffset(DateTime.SpecifyKind(dateTime, DateTimeKind.Utc)),
            DateTimeOffset dateTimeOffset => dateTimeOffset.ToUniversalTime(),
            _ => throw new InvalidOperationException("PostgreSQL did not return its effective clock.")
        };
}
