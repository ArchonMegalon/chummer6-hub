using System.Security.Cryptography;
using System.Text;
using Npgsql;
using NpgsqlTypes;

namespace Chummer.Run.Api.Services.Community.Postgres;

/// <summary>
/// Dormant PostgreSQL implementation. Every successful lifecycle mutation, encrypted response
/// receipt, audit append, audit-head advance, and pending checkpoint publication commits in one
/// database transaction. Commit ambiguity is resolved through independent bounded publication
/// recovery and the operation/epoch-bound durable receipt on a new connection.
/// </summary>
public sealed class NpgsqlPlayAuthorizationRepository : IPlayAuthorizationPostgresRepository
{
    private static readonly TimeSpan PostCommitObserverDeadline = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan PostCommitRecoveryDeadline = TimeSpan.FromSeconds(8);
    private static readonly TimeSpan RecoveryRetryDelay = TimeSpan.FromMilliseconds(25);
    private const int MaximumRecoveryPublications = 32;
    private const int MaximumRecoveryPasses = 8;
    private const int MaximumOptimisticAttempts = 4;
    private readonly NpgsqlDataSource _dataSource;
    private readonly IPlayAuthorizationPostgresUnitOfWorkFactory _unitOfWorkFactory;
    private readonly IPlayAuthorizationEpochAuthority _epochAuthority;
    private readonly IPlayAuthorizationHmacAuthority _hmacAuthority;
    private readonly PlayAuthorizationCheckpointProviderActivation _checkpointProvider;
    private readonly PlayAuthorizationCheckpointProviderCapabilities _checkpointCapabilities;
    private readonly IPlayAuthorizationCheckpointPublicationReconciler _checkpointReconciler;
    private readonly IPlayAuthorizationReceiptCipher _receiptCipher;
    private readonly IPlayAuthorizationCommitObserver _commitObserver;
    private readonly TimeProvider _timeProvider;

    private NpgsqlPlayAuthorizationRepository(
        NpgsqlDataSource dataSource,
        IPlayAuthorizationPostgresUnitOfWorkFactory unitOfWorkFactory,
        IPlayAuthorizationEpochAuthority epochAuthority,
        IPlayAuthorizationHmacAuthority hmacAuthority,
        PlayAuthorizationCheckpointProviderActivation checkpointProvider,
        IPlayAuthorizationCheckpointPublicationReconciler checkpointReconciler,
        IPlayAuthorizationReceiptCipher receiptCipher,
        IPlayAuthorizationCommitObserver commitObserver,
        TimeProvider timeProvider)
    {
        _dataSource = dataSource ?? throw new ArgumentNullException(nameof(dataSource));
        _unitOfWorkFactory = unitOfWorkFactory ?? throw new ArgumentNullException(nameof(unitOfWorkFactory));
        _epochAuthority = epochAuthority ?? throw new ArgumentNullException(nameof(epochAuthority));
        _hmacAuthority = hmacAuthority ?? throw new ArgumentNullException(nameof(hmacAuthority));
        _checkpointProvider = checkpointProvider
            ?? throw new ArgumentNullException(nameof(checkpointProvider));
        _checkpointCapabilities = _checkpointProvider.Capabilities;
        _checkpointReconciler = checkpointReconciler
            ?? throw new ArgumentNullException(nameof(checkpointReconciler));
        _receiptCipher = receiptCipher ?? throw new ArgumentNullException(nameof(receiptCipher));
        _commitObserver = commitObserver ?? throw new ArgumentNullException(nameof(commitObserver));
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        PlayAuthorizationCheckpointProviderDeadline.Validate(_checkpointCapabilities);
    }

    internal static NpgsqlPlayAuthorizationRepository Create(
        object factoryLease,
        PlayAuthorizationCheckpointProviderActivation checkpointProvider,
        NpgsqlDataSource dataSource,
        IPlayAuthorizationPostgresUnitOfWorkFactory unitOfWorkFactory,
        IPlayAuthorizationEpochAuthority epochAuthority,
        IPlayAuthorizationHmacAuthority hmacAuthority,
        NpgsqlPlayAuthorizationCheckpointPublicationReconciler checkpointReconciler,
        IPlayAuthorizationReceiptCipher receiptCipher,
        IPlayAuthorizationCommitObserver commitObserver,
        TimeProvider timeProvider)
    {
        PlayAuthorizationPostgresDormantFactory.DemandOwnedReconciler(
            factoryLease,
            checkpointProvider,
            checkpointReconciler);
        return new(
            dataSource,
            unitOfWorkFactory,
            epochAuthority,
            hmacAuthority,
            checkpointProvider,
            checkpointReconciler,
            receiptCipher,
            commitObserver,
            timeProvider);
    }

    public Task<PlayAuthorizationPostgresMutationResult> RedeemInviteAsync(
        PlayAuthorizationRedeemMutation mutation,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        ArgumentNullException.ThrowIfNull(mutation);
        return ExecuteAtomicAsync(
            mutation.DurableRequest,
            PlayAuthorizationOperation.RedeemInvite,
            "invite",
            mutation.InviteId,
            mutation.ActorDigestSha256,
            (state, token) => PrepareCapabilityMutationAsync(
                state,
                PlayAuthorizationCapabilityKind.Invite,
                mutation.InviteId,
                mutation.PresentedInviteSecret,
                PlayAuthorizationCapabilityKind.Exchange,
                mutation.ExchangeId,
                mutation.NewExchangeSecret,
                token),
            (unitOfWork, state, now, prepared, token) =>
                RedeemInviteCoreAsync(unitOfWork, state, now, mutation, prepared, token),
            cancellationToken);
    }

    public Task<PlayAuthorizationPostgresMutationResult> ConsumeExchangeAsync(
        PlayAuthorizationConsumeMutation mutation,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        ArgumentNullException.ThrowIfNull(mutation);
        return ExecuteAtomicAsync(
            mutation.DurableRequest,
            PlayAuthorizationOperation.ConsumeExchange,
            "exchange",
            mutation.ExchangeId,
            mutation.ActorDigestSha256,
            (state, token) => PrepareCapabilityMutationAsync(
                state,
                PlayAuthorizationCapabilityKind.Exchange,
                mutation.ExchangeId,
                mutation.PresentedExchangeSecret,
                PlayAuthorizationCapabilityKind.Grant,
                mutation.GrantId,
                mutation.NewGrantSecret,
                token),
            (unitOfWork, state, now, prepared, token) =>
                ConsumeExchangeCoreAsync(unitOfWork, state, now, mutation, prepared, token),
            cancellationToken);
    }

    public Task<PlayAuthorizationPostgresMutationResult> RefreshGrantAsync(
        PlayAuthorizationRefreshMutation mutation,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        ArgumentNullException.ThrowIfNull(mutation);
        return ExecuteAtomicAsync(
            mutation.DurableRequest,
            PlayAuthorizationOperation.RefreshGrant,
            "grant",
            mutation.GrantId,
            mutation.ActorDigestSha256,
            (state, token) => PrepareCapabilityMutationAsync(
                state,
                PlayAuthorizationCapabilityKind.Grant,
                mutation.GrantId,
                mutation.PresentedGrantSecret,
                PlayAuthorizationCapabilityKind.Grant,
                mutation.GrantId,
                mutation.NewGrantSecret,
                token),
            (unitOfWork, state, now, prepared, token) =>
                RefreshGrantCoreAsync(unitOfWork, state, now, mutation, prepared, token),
            cancellationToken);
    }

    public Task<PlayAuthorizationPostgresMutationResult> RevokeGrantAsync(
        PlayAuthorizationGrantMutation mutation,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        ArgumentNullException.ThrowIfNull(mutation);
        return ExecuteAtomicAsync(
            mutation.DurableRequest,
            PlayAuthorizationOperation.RevokeGrant,
            "grant",
            mutation.GrantId,
            mutation.ActorDigestSha256,
            static (_, _) => Task.FromResult(PreparedCapabilityMutation.None),
            (unitOfWork, state, now, _, token) => RevokeGrantCoreAsync(unitOfWork, state, now, mutation, token),
            cancellationToken);
    }

    public Task<PlayAuthorizationPostgresMutationResult> RevokeParticipantAsync(
        PlayAuthorizationParticipantMutation mutation,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        ArgumentNullException.ThrowIfNull(mutation);
        return ExecuteAtomicAsync(
            mutation.DurableRequest,
            PlayAuthorizationOperation.RevokeParticipant,
            "participant",
            mutation.ParticipantId,
            mutation.ActorDigestSha256,
            static (_, _) => Task.FromResult(PreparedCapabilityMutation.None),
            (unitOfWork, state, now, _, token) => RevokeParticipantCoreAsync(unitOfWork, state, now, mutation, token),
            cancellationToken);
    }

    public Task<PlayAuthorizationPostgresMutationResult> BumpSessionAuthorizationVersionAsync(
        PlayAuthorizationSessionMutation mutation,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        ArgumentNullException.ThrowIfNull(mutation);
        return ExecuteAtomicAsync(
            mutation.DurableRequest,
            PlayAuthorizationOperation.BumpSessionAuthorizationVersion,
            "session",
            mutation.SessionId,
            mutation.ActorDigestSha256,
            static (_, _) => Task.FromResult(PreparedCapabilityMutation.None),
            (unitOfWork, state, now, _, token) => BumpSessionCoreAsync(unitOfWork, state, now, mutation, token),
            cancellationToken);
    }

    public Task<PlayAuthorizationPostgresMutationResult> BumpParticipantAuthorizationVersionAsync(
        PlayAuthorizationParticipantMutation mutation,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        ArgumentNullException.ThrowIfNull(mutation);
        return ExecuteAtomicAsync(
            mutation.DurableRequest,
            PlayAuthorizationOperation.BumpParticipantAuthorizationVersion,
            "participant",
            mutation.ParticipantId,
            mutation.ActorDigestSha256,
            static (_, _) => Task.FromResult(PreparedCapabilityMutation.None),
            (unitOfWork, state, now, _, token) => BumpParticipantCoreAsync(unitOfWork, state, now, mutation, token),
            cancellationToken);
    }

    public Task<PlayAuthorizationPostgresMutationResult> CloseSessionAsync(
        PlayAuthorizationSessionMutation mutation,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        ArgumentNullException.ThrowIfNull(mutation);
        return ExecuteAtomicAsync(
            mutation.DurableRequest,
            PlayAuthorizationOperation.CloseSession,
            "session",
            mutation.SessionId,
            mutation.ActorDigestSha256,
            static (_, _) => Task.FromResult(PreparedCapabilityMutation.None),
            (unitOfWork, state, now, _, token) => CloseSessionCoreAsync(unitOfWork, state, now, mutation, token),
            cancellationToken);
    }

    public async Task<PlayAuthorizationPostgresMutationResult?> LookupIdempotencyReceiptAsync(
        PlayAuthorizationDurableRequest request,
        CancellationToken cancellationToken = default)
    {
        _checkpointProvider.DemandOpen();
        return await LookupIdempotencyReceiptCoreAsync(request, cancellationToken);
    }

    private async Task<PlayAuthorizationPostgresMutationResult?> LookupIdempotencyReceiptCoreAsync(
        PlayAuthorizationDurableRequest request,
        CancellationToken cancellationToken)
    {
        ValidateDurableRequest(request);
        byte[] scopeHash = HashUtf8(request.Scope);
        byte[] keyHash = HashUtf8(request.IdempotencyKey);
        byte[] fingerprint = ParseSha256(request.FingerprintSha256, nameof(request.FingerprintSha256));
        try
        {
            for (int attempt = 0; attempt < MaximumOptimisticAttempts; attempt++)
            {
                ReceiptSnapshotRead initial = await ReadReceiptSnapshotAsync(
                    request,
                    scopeHash,
                    keyHash,
                    fingerprint,
                    cancellationToken);
                if (initial.Resolution is not null || initial.Snapshot is null)
                {
                    return initial.Resolution;
                }

                using ReceiptSnapshot snapshot = initial.Snapshot;
                PlayAuthorizationExternalEpoch external =
                    await _epochAuthority.ReadCurrentAsync(cancellationToken);
                if (!ExternalMatchesState(external, snapshot.AuthorityState))
                {
                    return new(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable);
                }

                await _checkpointProvider.ValidateAsync(
                    external,
                    snapshot.AuthorityState,
                    _timeProvider,
                    cancellationToken);

                ReceiptSnapshotRead final = await ReadReceiptSnapshotAsync(
                    request,
                    scopeHash,
                    keyHash,
                    fingerprint,
                    cancellationToken);
                if (final.Resolution is not null)
                {
                    return final.Resolution;
                }

                if (final.Snapshot is null)
                {
                    continue;
                }

                using ReceiptSnapshot finalSnapshot = final.Snapshot;
                if (!ReceiptSnapshotsEqual(snapshot, finalSnapshot))
                {
                    continue;
                }

                byte[] ciphertext = finalSnapshot.ResponseCiphertext.ToArray();
                byte[] plaintextHash = finalSnapshot.ResponsePlaintextSha256.ToArray();
                try
                {
                    PlayAuthorizationReceiptEnvelope response = _receiptCipher.Unprotect(
                        ciphertext,
                        plaintextHash,
                        finalSnapshot.ResponseType);
                    return new(PlayAuthorizationPostgresOutcomeCode.Replayed, response);
                }
                finally
                {
                    CryptographicOperations.ZeroMemory(ciphertext);
                    CryptographicOperations.ZeroMemory(plaintextHash);
                }
            }

            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }
        catch (PlayAuthorizationExternalAuthorityUnavailableException)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable);
        }
        catch (PlayAuthorizationProviderDeadlineExceededException)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable);
        }
        catch (PlayAuthorizationCheckpointProviderCallInFlightException exception)
            when (exception.Lane == PlayAuthorizationCheckpointProviderLaneKind.Validation)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable);
        }
        catch (CryptographicException)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }
        catch (Exception exception) when (exception is NpgsqlException or IOException or TimeoutException)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(scopeHash);
            CryptographicOperations.ZeroMemory(keyHash);
            CryptographicOperations.ZeroMemory(fingerprint);
        }
    }

    private async Task<PlayAuthorizationPostgresMutationResult> ExecuteAtomicAsync(
        PlayAuthorizationDurableRequest request,
        PlayAuthorizationOperation operationKind,
        string aggregateKind,
        string aggregateId,
        string actorDigestSha256,
        Func<PlayAuthorizationPostgresState, CancellationToken, Task<PreparedCapabilityMutation>> prepareMutation,
        Func<IPlayAuthorizationPostgresUnitOfWork, PlayAuthorizationPostgresState, DateTimeOffset,
            PreparedCapabilityMutation, CancellationToken, Task<PlayAuthorizationPostgresOutcomeCode>> mutation,
        CancellationToken cancellationToken)
    {
        ValidateDurableRequest(request);
        string operation = operationKind.ToDatabaseValue();
        RequireIdentifier(operation, nameof(operation), 64);
        RequireIdentifier(aggregateId, nameof(aggregateId));
        ValidateSha256(actorDigestSha256, nameof(actorDigestSha256));
        if (request.Operation != operationKind)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
        }

        try
        {
            PlayAuthorizationCheckpointReconciliationResult preflight =
                await _checkpointReconciler.ReconcileAsync(
                    MaximumRecoveryPublications,
                    cancellationToken);
            if (!preflight.Complete)
            {
                return new(PlayAuthorizationPostgresOutcomeCode.CheckpointPending);
            }
        }
        catch (PlayAuthorizationExternalAuthorityUnavailableException)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable);
        }
        catch (Exception exception) when (
            exception is NpgsqlException or IOException or TimeoutException)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }

        byte[] scopeHash = HashUtf8(request.Scope);
        byte[] keyHash = HashUtf8(request.IdempotencyKey);
        byte[] fingerprint = ParseSha256(request.FingerprintSha256, nameof(request.FingerprintSha256));
        bool commitAttempted = false;
        try
        {
            for (int attempt = 0; attempt < MaximumOptimisticAttempts; attempt++)
            {
                commitAttempted = false;
                using OptimisticAuthoritySnapshot optimistic =
                    await ReadOptimisticAuthoritySnapshotAsync(cancellationToken);
                PlayAuthorizationPostgresState state = optimistic.State;
                PlayAuthorizationExternalEpoch external =
                    await _epochAuthority.ReadCurrentAsync(cancellationToken);
                if (!ExternalMatchesState(external, state))
                {
                    return new(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable);
                }

                await _checkpointProvider.ValidateAsync(
                    external,
                    state,
                    _timeProvider,
                    cancellationToken);

                using PreparedCapabilityMutation prepared =
                    await prepareMutation(state, cancellationToken);
                if (!prepared.CanAttempt)
                {
                    return new(PlayAuthorizationPostgresOutcomeCode.NotFound);
                }

                PlayAuthorizationProtectedReceipt protectedReceipt =
                    _receiptCipher.Protect(request.Response);
                try
                {
                    using PreparedAuditMutation preparedAudit = await PrepareAuditMutationAsync(
                        state,
                        external,
                        operation,
                        aggregateKind,
                        aggregateId,
                        actorDigestSha256,
                        scopeHash,
                        keyHash,
                        fingerprint,
                        protectedReceipt.PlaintextSha256,
                        cancellationToken);
                    PlayAuthorizationPostgresMutationResult? existing = null;
                    PlayAuthorizationPostgresOutcomeCode? mutationFailure = null;
                    bool retry = false;
                    await using (IPlayAuthorizationPostgresUnitOfWork unitOfWork =
                                 await _unitOfWorkFactory.BeginAsync(cancellationToken))
                    {
                        PlayAuthorizationPostgresState? locked =
                            await ReadLockedMutationStateAsync(unitOfWork, cancellationToken);
                        bool exactLockedState = locked is not null && StatesEqual(locked, state);
                        if (locked is not null)
                        {
                            CryptographicOperations.ZeroMemory(locked.AuditHeadHmac);
                            CryptographicOperations.ZeroMemory(locked.ExternalCheckpoint);
                        }

                        if (!exactLockedState)
                        {
                            await unitOfWork.RollbackAsync(cancellationToken);
                            retry = true;
                        }
                        else
                        {
                            DateTimeOffset transactionNow = await ReadEffectiveDatabaseTimeAsync(
                                unitOfWork,
                                state,
                                cancellationToken);
                            existing = await BeginIdempotencyAsync(
                                unitOfWork,
                                request,
                                operation,
                                scopeHash,
                                keyHash,
                                fingerprint,
                                state,
                                transactionNow,
                                cancellationToken);
                            if (existing is not null)
                            {
                                await unitOfWork.RollbackAsync(cancellationToken);
                            }
                            else
                            {
                                PlayAuthorizationPostgresOutcomeCode mutationCode;
                                try
                                {
                                    mutationCode = await mutation(
                                        unitOfWork,
                                        state,
                                        transactionNow,
                                        prepared,
                                        cancellationToken);
                                }
                                catch (OptimisticRetryRequiredException)
                                {
                                    await unitOfWork.RollbackAsync(cancellationToken);
                                    retry = true;
                                    mutationCode = PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable;
                                }

                                if (retry)
                                {
                                    // A verifier or lifecycle row changed after external preparation.
                                }
                                else if (mutationCode != PlayAuthorizationPostgresOutcomeCode.Applied)
                                {
                                    await unitOfWork.RollbackAsync(cancellationToken);
                                    mutationFailure = mutationCode;
                                }
                                else
                                {
                                    preparedAudit.Materialize(state, transactionNow);
                                    await AppendAuditAndAdvanceStateAsync(
                                        unitOfWork,
                                        state,
                                        preparedAudit,
                                        operation,
                                        aggregateKind,
                                        aggregateId,
                                        actorDigestSha256,
                                        transactionNow,
                                        cancellationToken);
                                    await CompleteIdempotencyAsync(
                                        unitOfWork,
                                        scopeHash,
                                        keyHash,
                                        protectedReceipt,
                                        request.Response.StatusCode,
                                        preparedAudit.CommittedState.AuditHeadSequence,
                                        preparedAudit.EventId,
                                        preparedAudit.PayloadCanonicalVersion,
                                        preparedAudit.PayloadSha256,
                                        state,
                                        transactionNow,
                                        cancellationToken);
                                    commitAttempted = true;
                                    await unitOfWork.CommitAsync(cancellationToken);
                                }
                            }
                        }
                    }

                    if (retry)
                    {
                        await TryReconcileBeforeRetryAsync(cancellationToken);
                        continue;
                    }

                    if (existing is not null)
                    {
                        if (existing.Code == PlayAuthorizationPostgresOutcomeCode.CheckpointPending)
                        {
                            return await ReconcileAndLookupReceiptAsync(request);
                        }

                        if (existing.Code == PlayAuthorizationPostgresOutcomeCode.Replayed)
                        {
                            return await LookupIdempotencyReceiptCoreAsync(request, cancellationToken)
                                ?? new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
                        }

                        return existing;
                    }

                    if (mutationFailure is not null)
                    {
                        return new(mutationFailure.Value);
                    }

                    await NotifyCommitObserverAsync();

                    using CancellationTokenSource recoveryDeadline =
                        new(PostCommitRecoveryDeadline, _timeProvider);
                    if (!await RecoverCommittedCheckpointAsync(
                            preparedAudit.CommittedState,
                            recoveryDeadline.Token))
                    {
                        return new(PlayAuthorizationPostgresOutcomeCode.CheckpointPending);
                    }

                    return new(PlayAuthorizationPostgresOutcomeCode.Applied, request.Response);
                }
                finally
                {
                    CryptographicOperations.ZeroMemory(protectedReceipt.Ciphertext);
                    CryptographicOperations.ZeroMemory(protectedReceipt.PlaintextSha256);
                }
            }

            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }
        catch (PostgresException exception) when (exception.SqlState.StartsWith("23", StringComparison.Ordinal))
        {
            return new(PlayAuthorizationPostgresOutcomeCode.InvalidLifecycle);
        }
        catch (PlayAuthorizationExternalAuthorityUnavailableException)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable);
        }
        catch (PlayAuthorizationProviderDeadlineExceededException)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable);
        }
        catch (PlayAuthorizationCheckpointProviderCallInFlightException exception)
            when (exception.Lane == PlayAuthorizationCheckpointProviderLaneKind.Validation)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable);
        }
        catch (CryptographicException)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }
        catch (Exception exception) when (commitAttempted && IsAmbiguousPersistenceFailure(exception))
        {
            return await ReconcileAndLookupReceiptAsync(request);
        }
        catch (Exception exception) when (
            exception is not OperationCanceledException
            && IsAmbiguousPersistenceFailure(exception))
        {
            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(scopeHash);
            CryptographicOperations.ZeroMemory(keyHash);
            CryptographicOperations.ZeroMemory(fingerprint);
        }
    }

    private async Task<PlayAuthorizationPostgresMutationResult?> BeginIdempotencyAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationDurableRequest request,
        string operation,
        byte[] scopeHash,
        byte[] keyHash,
        byte[] fingerprint,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await using (NpgsqlCommand insert = Command(unitOfWork, """
            INSERT INTO play_auth.idempotency_receipts(
                scope_sha256, key_sha256, fingerprint_sha256, operation, state,
                epoch, generation, created_at_utc, expires_at_utc)
            VALUES (@scope, @key, @fingerprint, @operation, 'in_progress',
                    @epoch, @generation, @now, @expires)
            ON CONFLICT (scope_sha256, key_sha256) DO NOTHING
            """))
        {
            AddBytea(insert, "scope", scopeHash);
            AddBytea(insert, "key", keyHash);
            AddBytea(insert, "fingerprint", fingerprint);
            insert.Parameters.AddWithValue("operation", operation);
            insert.Parameters.AddWithValue("epoch", state.Epoch);
            insert.Parameters.AddWithValue("generation", state.Generation);
            insert.Parameters.AddWithValue("now", now);
            insert.Parameters.AddWithValue(
                "expires",
                now.Add(PlayAuthorizationPostgresDurabilityInvariants.ReceiptLifetime));
            if (await insert.ExecuteNonQueryAsync(cancellationToken) == 1)
            {
                return null;
            }
        }

        await using NpgsqlCommand select = Command(unitOfWork, """
            SELECT receipt.fingerprint_sha256, receipt.operation, receipt.state,
                   receipt.epoch, receipt.generation, receipt.expires_at_utc,
                   receipt.response_type, receipt.response_ciphertext,
                   receipt.response_plaintext_sha256, receipt.audit_sequence,
                   audit.operation, audit.epoch, audit.generation,
                   publication.state,
                   receipt.audit_event_id, receipt.audit_payload_canonical_version,
                   receipt.audited_payload_sha256, audit.event_id,
                   audit.payload_canonical_version, audit.payload_sha256,
                   audit.aggregate_kind, audit.aggregate_id, audit.actor_digest_sha256
            FROM play_auth.idempotency_receipts AS receipt
            LEFT JOIN play_auth.audit_log AS audit
              ON audit.sequence = receipt.audit_sequence
             AND audit.operation = receipt.operation
             AND audit.epoch = receipt.epoch
             AND audit.generation = receipt.generation
            LEFT JOIN play_auth.checkpoint_publications AS publication
              ON publication.audit_sequence = receipt.audit_sequence
             AND publication.epoch = receipt.epoch
             AND publication.generation = receipt.generation
            WHERE receipt.scope_sha256 = @scope AND receipt.key_sha256 = @key
            FOR UPDATE OF receipt
            """);
        AddBytea(select, "scope", scopeHash);
        AddBytea(select, "key", keyHash);
        await using NpgsqlDataReader reader = await select.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }

        string receiptState = reader.GetString(2);
        if (string.Equals(receiptState, "pruned", StringComparison.Ordinal)
            || ReadDateTimeOffset(reader, 5) <= now)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.Expired);
        }

        byte[] storedFingerprint = (byte[])reader[0];
        if (!CryptographicOperations.FixedTimeEquals(storedFingerprint, fingerprint))
        {
            return new(PlayAuthorizationPostgresOutcomeCode.FingerprintConflict);
        }

        if (!string.Equals(reader.GetString(1), operation, StringComparison.Ordinal)
            || reader.GetInt64(3) != state.Epoch
            || reader.GetInt64(4) != state.Generation)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
        }

        if (!string.Equals(receiptState, "completed", StringComparison.Ordinal))
        {
            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }

        if (reader.IsDBNull(9)
            || reader.IsDBNull(10)
            || reader.IsDBNull(11)
            || reader.IsDBNull(12)
            || !string.Equals(reader.GetString(10), operation, StringComparison.Ordinal)
            || reader.GetInt64(11) != state.Epoch
            || reader.GetInt64(12) != state.Generation)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
        }

        if (reader.IsDBNull(13)
            || !string.Equals(reader.GetString(13), "published", StringComparison.Ordinal))
        {
            return new(PlayAuthorizationPostgresOutcomeCode.CheckpointPending);
        }

        if (reader.IsDBNull(6)
            || reader.IsDBNull(7)
            || reader.IsDBNull(8))
        {
            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }

        if (reader.IsDBNull(14)
            || reader.IsDBNull(15)
            || reader.IsDBNull(16)
            || reader.IsDBNull(17)
            || reader.IsDBNull(18)
            || reader.IsDBNull(19)
            || reader.IsDBNull(20)
            || reader.IsDBNull(21)
            || reader.IsDBNull(22)
            || reader.GetGuid(14) != reader.GetGuid(17)
            || reader.GetInt32(15)
                != PlayAuthorizationPostgresDurabilityInvariants.AuditPayloadCanonicalVersion
            || reader.GetInt32(18) != reader.GetInt32(15)
            || !CryptographicOperations.FixedTimeEquals((byte[])reader[16], (byte[])reader[19]))
        {
            return new(PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
        }

        byte[] expectedPayload = PlayAuthorizationAuditPayloadCanonicalizer.ComputePayloadDigest(
            reader.GetGuid(17),
            reader.GetInt64(11),
            reader.GetInt64(12),
            reader.GetInt64(9),
            reader.GetString(10),
            reader.GetString(20),
            reader.GetString(21),
            reader.GetString(22),
            scopeHash,
            keyHash,
            fingerprint,
            (byte[])reader[8],
            reader.GetInt32(18));
        try
        {
            if (!CryptographicOperations.FixedTimeEquals(expectedPayload, (byte[])reader[19]))
            {
                return new(PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(expectedPayload);
        }

        return new(PlayAuthorizationPostgresOutcomeCode.Replayed);
    }

    private async Task<OptimisticAuthoritySnapshot> ReadOptimisticAuthoritySnapshotAsync(
        CancellationToken cancellationToken)
    {
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            SELECT epoch, generation, clock_high_water_utc, audit_head_sequence,
                   audit_head_hmac, external_checkpoint
            FROM play_auth.authority_state
            WHERE singleton = true
            """;
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException("The Play authorization authority state is missing.");
        }

        PlayAuthorizationPostgresState state = new(
            reader.GetInt64(0),
            reader.GetInt64(1),
            ReadDateTimeOffset(reader, 2),
            reader.GetInt64(3),
            ((byte[])reader[4]).ToArray(),
            ((byte[])reader[5]).ToArray());
        return new OptimisticAuthoritySnapshot(state);
    }

    private static async Task<PlayAuthorizationPostgresState?> ReadLockedMutationStateAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = Command(unitOfWork, """
            SELECT authority.epoch, authority.generation, authority.clock_high_water_utc,
                   authority.audit_head_sequence, authority.audit_head_hmac,
                   authority.external_checkpoint
            FROM play_auth.authority_state AS authority
            JOIN play_auth.checkpoint_baseline AS baseline
              ON baseline.singleton = authority.singleton
            WHERE authority.singleton = true
              AND baseline.state = 'verified'
              AND baseline.epoch = authority.epoch
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
                        FROM play_auth.audit_log AS head_audit
                        JOIN play_auth.checkpoint_publications AS head_publication
                          ON head_publication.audit_sequence = head_audit.sequence
                        WHERE head_audit.sequence = authority.audit_head_sequence
                          AND head_audit.epoch = authority.epoch
                          AND head_audit.generation = authority.generation
                          AND head_audit.entry_hmac = authority.audit_head_hmac
                          AND head_publication.state = 'published'
                          AND head_publication.epoch = authority.epoch
                          AND head_publication.generation = authority.generation
                          AND head_publication.clock_high_water_utc = authority.clock_high_water_utc
                          AND head_publication.audit_head_hmac = authority.audit_head_hmac
                          AND head_publication.external_checkpoint = authority.external_checkpoint)))
              AND NOT EXISTS (
                  SELECT 1
                  FROM play_auth.checkpoint_publications AS pending
                  WHERE pending.state = 'pending')
            FOR UPDATE OF authority
            """);
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            return null;
        }

        return new PlayAuthorizationPostgresState(
            reader.GetInt64(0),
            reader.GetInt64(1),
            ReadDateTimeOffset(reader, 2),
            reader.GetInt64(3),
            ((byte[])reader[4]).ToArray(),
            ((byte[])reader[5]).ToArray());
    }

    private async Task<PreparedCapabilityMutation> PrepareCapabilityMutationAsync(
        PlayAuthorizationPostgresState state,
        PlayAuthorizationCapabilityKind presentedKind,
        string presentedId,
        byte[] presentedSecret,
        PlayAuthorizationCapabilityKind replacementKind,
        string replacementId,
        byte[] replacementSecret,
        CancellationToken cancellationToken)
    {
        CapabilityVerifierSnapshot? snapshot;
        await using (NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken))
        await using (NpgsqlCommand command = connection.CreateCommand())
        {
            command.CommandText = """
                SELECT key_id, verifier_hmac, epoch, generation
                FROM play_auth.capability_verifiers
                WHERE capability_kind = @kind
                  AND capability_id = @id
                  AND epoch = @epoch
                  AND generation = @generation
                """;
            command.Parameters.AddWithValue("kind", presentedKind.ToDatabaseValue());
            command.Parameters.AddWithValue("id", presentedId);
            command.Parameters.AddWithValue("epoch", state.Epoch);
            command.Parameters.AddWithValue("generation", state.Generation);
            await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken);
            snapshot = await reader.ReadAsync(cancellationToken)
                ? new CapabilityVerifierSnapshot(
                    presentedKind,
                    presentedId,
                    reader.GetString(0),
                    ((byte[])reader[1]).ToArray(),
                    reader.GetInt64(2),
                    reader.GetInt64(3))
                : null;
        }

        if (snapshot is null)
        {
            return PreparedCapabilityMutation.Missing;
        }

        try
        {
            if (snapshot.VerifierHmac.Length
                != PlayAuthorizationPostgresDurabilityInvariants.HmacSizeInBytes)
            {
                throw new CryptographicException(
                    "The stored capability HMAC-SHA-256 verifier is malformed.");
            }

            PlayAuthorizationKeyedDigest? actual = await _hmacAuthority.ComputeCapabilityAsync(
                presentedKind,
                presentedId,
                presentedSecret,
                snapshot.KeyId,
                cancellationToken);
            bool matches;
            try
            {
                ValidateHmacDigest(actual, "capability");
                matches = string.Equals(actual!.KeyId, snapshot.KeyId, StringComparison.Ordinal)
                    && CryptographicOperations.FixedTimeEquals(actual.Digest, snapshot.VerifierHmac);
            }
            finally
            {
                if (actual?.Digest is not null)
                {
                    CryptographicOperations.ZeroMemory(actual.Digest);
                }
            }

            if (!matches)
            {
                return new PreparedCapabilityMutation(snapshot, null, presentedMatches: false);
            }

            PlayAuthorizationKeyedDigest? replacement = await _hmacAuthority.ComputeCapabilityAsync(
                replacementKind,
                replacementId,
                replacementSecret,
                requiredKeyId: null,
                cancellationToken);
            try
            {
                ValidateHmacDigest(replacement, "replacement capability");
            }
            catch
            {
                if (replacement?.Digest is not null)
                {
                    CryptographicOperations.ZeroMemory(replacement.Digest);
                }

                throw;
            }

            return new PreparedCapabilityMutation(snapshot, replacement, presentedMatches: true);
        }
        catch
        {
            snapshot.Dispose();
            throw;
        }
    }

    private async Task<PreparedAuditMutation> PrepareAuditMutationAsync(
        PlayAuthorizationPostgresState state,
        PlayAuthorizationExternalEpoch external,
        string operation,
        string aggregateKind,
        string aggregateId,
        string actorDigestSha256,
        byte[] scopeHash,
        byte[] keyHash,
        byte[] fingerprint,
        byte[] responsePlaintextSha256,
        CancellationToken cancellationToken)
    {
        long sequence = checked(state.AuditHeadSequence + 1);
        Guid eventId = Guid.NewGuid();
        byte[] payload = PlayAuthorizationAuditPayloadCanonicalizer.ComputePayloadDigest(
            eventId,
            state.Epoch,
            state.Generation,
            sequence,
            operation,
            aggregateKind,
            aggregateId,
            actorDigestSha256,
            scopeHash,
            keyHash,
            fingerprint,
            responsePlaintextSha256,
            PlayAuthorizationPostgresDurabilityInvariants.AuditPayloadCanonicalVersion);
        PlayAuthorizationKeyedDigest? audit = null;
        byte[]? externalCheckpoint = null;
        try
        {
            audit = await _hmacAuthority.ComputeAuditAsync(
                new(state.Epoch, state.Generation, sequence, state.AuditHeadHmac, payload),
                cancellationToken);
            ValidateHmacDigest(audit, "audit");

            Guid publicationId = Guid.NewGuid();
            externalCheckpoint = external.Checkpoint.ToArray();
            return new PreparedAuditMutation(
                payload,
                audit!,
                eventId,
                publicationId,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion,
                externalCheckpoint);
        }
        catch
        {
            CryptographicOperations.ZeroMemory(payload);
            if (audit?.Digest is not null)
            {
                CryptographicOperations.ZeroMemory(audit.Digest);
            }

            if (externalCheckpoint is not null)
            {
                CryptographicOperations.ZeroMemory(externalCheckpoint);
            }

            throw;
        }
    }

    private async Task<ReceiptSnapshotRead> ReadReceiptSnapshotAsync(
        PlayAuthorizationDurableRequest request,
        byte[] scopeHash,
        byte[] keyHash,
        byte[] fingerprint,
        CancellationToken cancellationToken)
    {
        ReceiptSnapshotRead result;
        await using (NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken))
        await using (NpgsqlTransaction transaction = await connection.BeginTransactionAsync(cancellationToken))
        await using (NpgsqlCommand command = connection.CreateCommand())
        {
            command.Transaction = transaction;
            command.CommandText = """
                SELECT receipt.fingerprint_sha256, receipt.operation, receipt.state,
                       receipt.epoch, receipt.generation, receipt.expires_at_utc,
                       receipt.response_type, receipt.response_ciphertext,
                       receipt.response_plaintext_sha256, receipt.audit_sequence,
                       audit.operation, audit.epoch, audit.generation, audit.entry_hmac,
                       publication.state, publication.publication_id,
                       publication.epoch, publication.generation,
                       publication.clock_high_water_utc, publication.audit_head_hmac,
                       publication.external_checkpoint, publication.digest_algorithm,
                       publication.canonical_version, publication.payload_digest_sha256,
                       authority.epoch, authority.generation, authority.clock_high_water_utc,
                       authority.audit_head_sequence, authority.audit_head_hmac,
                       authority.external_checkpoint,
                       GREATEST(clock_timestamp(), authority.clock_high_water_utc),
                       EXISTS (
                           SELECT 1
                           FROM play_auth.checkpoint_baseline AS baseline
                           WHERE baseline.singleton = true
                             AND baseline.state = 'verified'
                             AND baseline.epoch = authority.epoch
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
                                   FROM play_auth.audit_log AS head_audit
                                   JOIN play_auth.checkpoint_publications AS head_publication
                                     ON head_publication.audit_sequence = head_audit.sequence
                                   WHERE head_audit.sequence = authority.audit_head_sequence
                                     AND head_audit.epoch = authority.epoch
                                     AND head_audit.generation = authority.generation
                                     AND head_audit.entry_hmac = authority.audit_head_hmac
                                     AND head_publication.state = 'published'
                                     AND head_publication.epoch = authority.epoch
                                     AND head_publication.generation = authority.generation
                                     AND head_publication.clock_high_water_utc = authority.clock_high_water_utc
                                     AND head_publication.audit_head_hmac = authority.audit_head_hmac
                                     AND head_publication.external_checkpoint = authority.external_checkpoint)))),
                       receipt.audit_event_id, receipt.audit_payload_canonical_version,
                       receipt.audited_payload_sha256, audit.event_id,
                       audit.payload_canonical_version, audit.payload_sha256,
                       audit.aggregate_kind, audit.aggregate_id, audit.actor_digest_sha256
                FROM play_auth.idempotency_receipts AS receipt
                CROSS JOIN play_auth.authority_state AS authority
                LEFT JOIN play_auth.audit_log AS audit
                  ON audit.sequence = receipt.audit_sequence
                LEFT JOIN play_auth.checkpoint_publications AS publication
                  ON publication.audit_sequence = receipt.audit_sequence
                WHERE receipt.scope_sha256 = @scope
                  AND receipt.key_sha256 = @key
                  AND authority.singleton = true
                FOR SHARE OF receipt, authority
                """;
            AddBytea(command, "scope", scopeHash);
            AddBytea(command, "key", keyHash);
            await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
            {
                result = new ReceiptSnapshotRead(null, null);
            }
            else
            {
                DateTimeOffset effectiveNow = ReadDateTimeOffset(reader, 30);
                string receiptState = reader.GetString(2);
                if (string.Equals(receiptState, "pruned", StringComparison.Ordinal)
                    || ReadDateTimeOffset(reader, 5) <= effectiveNow)
                {
                    result = ReceiptSnapshotRead.Resolved(PlayAuthorizationPostgresOutcomeCode.Expired);
                }
                else if (!CryptographicOperations.FixedTimeEquals((byte[])reader[0], fingerprint))
                {
                    result = ReceiptSnapshotRead.Resolved(
                        PlayAuthorizationPostgresOutcomeCode.FingerprintConflict);
                }
                else if (!string.Equals(
                             reader.GetString(1),
                             request.Operation.ToDatabaseValue(),
                             StringComparison.Ordinal)
                         || reader.GetInt64(3) != reader.GetInt64(24)
                         || reader.GetInt64(4) != reader.GetInt64(25))
                {
                    result = ReceiptSnapshotRead.Resolved(
                        PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
                }
                else if (!string.Equals(receiptState, "completed", StringComparison.Ordinal))
                {
                    result = ReceiptSnapshotRead.Resolved(
                        PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
                }
                else if (reader.IsDBNull(9)
                         || reader.IsDBNull(10)
                         || reader.IsDBNull(11)
                         || reader.IsDBNull(12)
                         || reader.IsDBNull(13)
                         || !string.Equals(reader.GetString(10), reader.GetString(1), StringComparison.Ordinal)
                         || reader.GetInt64(11) != reader.GetInt64(3)
                         || reader.GetInt64(12) != reader.GetInt64(4))
                {
                    result = ReceiptSnapshotRead.Resolved(
                        PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
                }
                else if (reader.IsDBNull(14)
                         || !string.Equals(reader.GetString(14), "published", StringComparison.Ordinal))
                {
                    result = ReceiptSnapshotRead.Resolved(
                        PlayAuthorizationPostgresOutcomeCode.CheckpointPending);
                }
                else if (reader.IsDBNull(15)
                         || reader.IsDBNull(16)
                         || reader.IsDBNull(17)
                         || reader.IsDBNull(18)
                         || reader.IsDBNull(19)
                         || reader.IsDBNull(20)
                         || reader.IsDBNull(21)
                         || reader.IsDBNull(22)
                         || reader.IsDBNull(23)
                         || reader.GetInt64(16) != reader.GetInt64(3)
                         || reader.GetInt64(17) != reader.GetInt64(4)
                         || !CryptographicOperations.FixedTimeEquals(
                             (byte[])reader[19],
                             (byte[])reader[13])
                         || reader.GetInt64(27) < reader.GetInt64(9))
                {
                    result = ReceiptSnapshotRead.Resolved(
                        PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
                }
                else if (!reader.GetBoolean(31))
                {
                    result = ReceiptSnapshotRead.Resolved(
                        PlayAuthorizationPostgresOutcomeCode.CheckpointPending);
                }
                else if (reader.IsDBNull(6) || reader.IsDBNull(7) || reader.IsDBNull(8))
                {
                    result = ReceiptSnapshotRead.Resolved(
                        PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
                }
                else if (reader.IsDBNull(32)
                         || reader.IsDBNull(33)
                         || reader.IsDBNull(34)
                         || reader.IsDBNull(35)
                         || reader.IsDBNull(36)
                         || reader.IsDBNull(37)
                         || reader.IsDBNull(38)
                         || reader.IsDBNull(39)
                         || reader.IsDBNull(40))
                {
                    result = ReceiptSnapshotRead.Resolved(
                        PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
                }
                else
                {
                    PlayAuthorizationPostgresState authorityState = new(
                        reader.GetInt64(24),
                        reader.GetInt64(25),
                        ReadDateTimeOffset(reader, 26),
                        reader.GetInt64(27),
                        ((byte[])reader[28]).ToArray(),
                        ((byte[])reader[29]).ToArray());
                    PlayAuthorizationPostgresState publicationState = new(
                        reader.GetInt64(16),
                        reader.GetInt64(17),
                        ReadDateTimeOffset(reader, 18),
                        reader.GetInt64(9),
                        ((byte[])reader[19]).ToArray(),
                        ((byte[])reader[20]).ToArray());
                    result = new ReceiptSnapshotRead(
                        new ReceiptSnapshot(
                            scopeHash.ToArray(),
                            keyHash.ToArray(),
                            ((byte[])reader[0]).ToArray(),
                            reader.GetString(1),
                            reader.GetInt64(3),
                            reader.GetInt64(4),
                            ReadDateTimeOffset(reader, 5),
                            reader.GetString(6),
                            ((byte[])reader[7]).ToArray(),
                            ((byte[])reader[8]).ToArray(),
                            reader.GetInt64(9),
                            reader.GetGuid(32),
                            reader.GetInt32(33),
                            ((byte[])reader[34]).ToArray(),
                            reader.GetGuid(35),
                            reader.GetInt32(36),
                            ((byte[])reader[37]).ToArray(),
                            reader.GetString(38),
                            reader.GetString(39),
                            reader.GetString(40),
                            ((byte[])reader[13]).ToArray(),
                            reader.GetGuid(15),
                            publicationState,
                            reader.GetString(21),
                            reader.GetInt32(22),
                            ((byte[])reader[23]).ToArray(),
                            authorityState),
                        null);
                }
            }

            await reader.DisposeAsync();
            await transaction.CommitAsync(cancellationToken);
        }

        if (result.Snapshot is not null)
        {
            bool validAuditBinding;
            bool validPublicationDigest;
            try
            {
                validAuditBinding = result.Snapshot.HasValidAuditBinding();
                validPublicationDigest = result.Snapshot.HasValidPublicationDigest();
            }
            catch (Exception exception) when (exception is ArgumentException
                                                   or InvalidOperationException
                                                   or CryptographicException)
            {
                result.Snapshot.Dispose();
                return ReceiptSnapshotRead.Resolved(
                    PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
            }

            if (!validAuditBinding || !validPublicationDigest)
            {
                result.Snapshot.Dispose();
                return ReceiptSnapshotRead.Resolved(
                    PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict);
            }
        }

        return result;
    }

    private async Task TryReconcileBeforeRetryAsync(CancellationToken cancellationToken)
    {
        try
        {
            await _checkpointReconciler.ReconcileAsync(MaximumRecoveryPublications, cancellationToken);
        }
        catch (Exception exception) when (!IsFatal(exception) && exception is not OperationCanceledException)
        {
            // The bounded optimistic loop will retry from current durable truth.
        }
    }

    private async Task<PlayAuthorizationPostgresOutcomeCode> RedeemInviteCoreAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        PlayAuthorizationRedeemMutation mutation,
        PreparedCapabilityMutation prepared,
        CancellationToken cancellationToken)
    {
        RequireCommonBinding(mutation.SessionId, mutation.ParticipantId, mutation.UserId, mutation.Role);
        RequireIdentifier(mutation.InviteId, nameof(mutation.InviteId));
        RequireIdentifier(mutation.ExchangeId, nameof(mutation.ExchangeId));
        RequireDeviceThumbprint(mutation.DeviceThumbprint);
        if (mutation.ExchangeExpiresAtUtc <= now)
        {
            return PlayAuthorizationPostgresOutcomeCode.InvalidLifecycle;
        }

        await using NpgsqlCommand command = Command(unitOfWork, """
            SELECT i.status, i.expires_at_utc, i.session_authorization_version,
                   i.participant_authorization_version, i.target_user_id, i.requested_role,
                   s.status, s.authorization_version,
                   p.status, p.authorization_version, p.user_id, p.role,
                   v.key_id, v.verifier_hmac, v.epoch, v.generation
            FROM play_auth.invites i
            JOIN play_auth.sessions s ON s.session_id = i.session_id
            JOIN play_auth.participants p
              ON p.participant_id = i.participant_id AND p.session_id = i.session_id
            JOIN play_auth.capability_verifiers v
              ON v.capability_kind = 'invite' AND v.capability_id = i.invite_id
            WHERE i.invite_id = @invite
              AND i.session_id = @session
              AND i.participant_id = @participant
              AND i.epoch = @epoch AND i.generation = @generation
              AND s.epoch = @epoch AND s.generation = @generation
              AND p.epoch = @epoch AND p.generation = @generation
              AND v.epoch = @epoch AND v.generation = @generation
            FOR UPDATE OF i, s, p, v
            """);
        command.Parameters.AddWithValue("invite", mutation.InviteId);
        command.Parameters.AddWithValue("session", mutation.SessionId);
        command.Parameters.AddWithValue("participant", mutation.ParticipantId);
        command.Parameters.AddWithValue("epoch", state.Epoch);
        command.Parameters.AddWithValue("generation", state.Generation);
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new OptimisticRetryRequiredException();
        }

        if (!string.Equals(reader.GetString(0), "pending", StringComparison.Ordinal))
        {
            return PlayAuthorizationPostgresOutcomeCode.AlreadyConsumed;
        }

        if (reader.GetFieldValue<DateTimeOffset>(1) <= now)
        {
            return PlayAuthorizationPostgresOutcomeCode.Expired;
        }

        if (reader.GetInt64(2) != mutation.ExpectedSessionAuthorizationVersion
            || reader.GetInt64(3) != mutation.ExpectedParticipantAuthorizationVersion
            || !Same(reader.GetString(4), mutation.UserId)
            || !string.Equals(reader.GetString(5), mutation.Role, StringComparison.Ordinal)
            || !string.Equals(reader.GetString(6), "active", StringComparison.Ordinal)
            || reader.GetInt64(7) != mutation.ExpectedSessionAuthorizationVersion
            || !string.Equals(reader.GetString(8), "active", StringComparison.Ordinal)
            || reader.GetInt64(9) != mutation.ExpectedParticipantAuthorizationVersion
            || !Same(reader.GetString(10), mutation.UserId)
            || !string.Equals(reader.GetString(11), mutation.Role, StringComparison.Ordinal))
        {
            return PlayAuthorizationPostgresOutcomeCode.VersionMismatch;
        }

        if (!prepared.Matches(
                PlayAuthorizationCapabilityKind.Invite,
                mutation.InviteId,
                reader.GetString(12),
                (byte[])reader[13],
                reader.GetInt64(14),
                reader.GetInt64(15)))
        {
            throw new OptimisticRetryRequiredException();
        }

        await reader.DisposeAsync();
        await using NpgsqlCommand mutate = Command(unitOfWork, """
                UPDATE play_auth.invites
                SET status = 'consumed', consumed_by_user_id = @user,
                    consumed_at_utc = @now, updated_at_utc = @now
                WHERE invite_id = @invite AND status = 'pending'
                  AND epoch = @epoch AND generation = @generation;

                INSERT INTO play_auth.exchanges(
                    exchange_id, invite_id, session_id, participant_id, user_id, role,
                    device_thumbprint, status, session_authorization_version,
                    participant_authorization_version, epoch, generation,
                    created_at_utc, updated_at_utc, expires_at_utc)
                VALUES (@exchange, @invite, @session, @participant, @user, @role,
                    @device, 'active', @session_version, @participant_version,
                    @epoch, @generation, @now, @now, @expires);

                INSERT INTO play_auth.capability_verifiers(
                    capability_kind, capability_id, epoch, generation, key_id,
                    verifier_hmac, created_at_utc, expires_at_utc)
                VALUES ('exchange', @exchange, @epoch, @generation, @key_id,
                    @verifier, @now, @expires)
                """);
        BindCommon(mutate, state, now, mutation.SessionId, mutation.ParticipantId,
            mutation.UserId, mutation.Role, mutation.ExpectedSessionAuthorizationVersion,
            mutation.ExpectedParticipantAuthorizationVersion);
        mutate.Parameters.AddWithValue("invite", mutation.InviteId);
        mutate.Parameters.AddWithValue("exchange", mutation.ExchangeId);
        mutate.Parameters.AddWithValue("device", mutation.DeviceThumbprint);
        mutate.Parameters.AddWithValue("expires", mutation.ExchangeExpiresAtUtc);
        mutate.Parameters.AddWithValue("key_id", prepared.Replacement!.KeyId);
        AddBytea(mutate, "verifier", prepared.Replacement.Digest);
        if (await mutate.ExecuteNonQueryAsync(cancellationToken) != 3)
        {
            throw new OptimisticRetryRequiredException();
        }

        return PlayAuthorizationPostgresOutcomeCode.Applied;
    }

    private async Task<PlayAuthorizationPostgresOutcomeCode> ConsumeExchangeCoreAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        PlayAuthorizationConsumeMutation mutation,
        PreparedCapabilityMutation prepared,
        CancellationToken cancellationToken)
    {
        RequireCommonBinding(mutation.SessionId, mutation.ParticipantId, mutation.UserId, mutation.Role);
        RequireIdentifier(mutation.ExchangeId, nameof(mutation.ExchangeId));
        RequireIdentifier(mutation.GrantId, nameof(mutation.GrantId));
        RequireDeviceThumbprint(mutation.DeviceThumbprint);
        if (mutation.GrantExpiresAtUtc <= now || mutation.RefreshUntilUtc < mutation.GrantExpiresAtUtc)
        {
            return PlayAuthorizationPostgresOutcomeCode.InvalidLifecycle;
        }

        await using NpgsqlCommand command = Command(unitOfWork, """
            SELECT e.status, e.expires_at_utc, e.session_authorization_version,
                   e.participant_authorization_version, e.user_id, e.role, e.device_thumbprint,
                   s.status, s.authorization_version,
                   p.status, p.authorization_version, p.user_id, p.role,
                   v.key_id, v.verifier_hmac, v.epoch, v.generation
            FROM play_auth.exchanges e
            JOIN play_auth.sessions s ON s.session_id = e.session_id
            JOIN play_auth.participants p
              ON p.participant_id = e.participant_id AND p.session_id = e.session_id
            JOIN play_auth.capability_verifiers v
              ON v.capability_kind = 'exchange' AND v.capability_id = e.exchange_id
            WHERE e.exchange_id = @exchange
              AND e.session_id = @session
              AND e.participant_id = @participant
              AND e.epoch = @epoch AND e.generation = @generation
              AND s.epoch = @epoch AND s.generation = @generation
              AND p.epoch = @epoch AND p.generation = @generation
              AND v.epoch = @epoch AND v.generation = @generation
            FOR UPDATE OF e, s, p, v
            """);
        command.Parameters.AddWithValue("exchange", mutation.ExchangeId);
        command.Parameters.AddWithValue("session", mutation.SessionId);
        command.Parameters.AddWithValue("participant", mutation.ParticipantId);
        command.Parameters.AddWithValue("epoch", state.Epoch);
        command.Parameters.AddWithValue("generation", state.Generation);
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new OptimisticRetryRequiredException();
        }

        if (!string.Equals(reader.GetString(0), "active", StringComparison.Ordinal))
        {
            return PlayAuthorizationPostgresOutcomeCode.AlreadyConsumed;
        }

        if (reader.GetFieldValue<DateTimeOffset>(1) <= now)
        {
            return PlayAuthorizationPostgresOutcomeCode.Expired;
        }

        if (reader.GetInt64(2) != mutation.ExpectedSessionAuthorizationVersion
            || reader.GetInt64(3) != mutation.ExpectedParticipantAuthorizationVersion
            || !Same(reader.GetString(4), mutation.UserId)
            || !string.Equals(reader.GetString(5), mutation.Role, StringComparison.Ordinal)
            || !string.Equals(reader.GetString(6), mutation.DeviceThumbprint, StringComparison.Ordinal)
            || !string.Equals(reader.GetString(7), "active", StringComparison.Ordinal)
            || reader.GetInt64(8) != mutation.ExpectedSessionAuthorizationVersion
            || !string.Equals(reader.GetString(9), "active", StringComparison.Ordinal)
            || reader.GetInt64(10) != mutation.ExpectedParticipantAuthorizationVersion
            || !Same(reader.GetString(11), mutation.UserId)
            || !string.Equals(reader.GetString(12), mutation.Role, StringComparison.Ordinal))
        {
            return PlayAuthorizationPostgresOutcomeCode.VersionMismatch;
        }

        if (!prepared.Matches(
                PlayAuthorizationCapabilityKind.Exchange,
                mutation.ExchangeId,
                reader.GetString(13),
                (byte[])reader[14],
                reader.GetInt64(15),
                reader.GetInt64(16)))
        {
            throw new OptimisticRetryRequiredException();
        }

        await reader.DisposeAsync();
        await using NpgsqlCommand mutate = Command(unitOfWork, """
                UPDATE play_auth.exchanges
                SET status = 'consumed', consumed_at_utc = @now, updated_at_utc = @now
                WHERE exchange_id = @exchange AND status = 'active'
                  AND epoch = @epoch AND generation = @generation;

                UPDATE play_auth.capability_verifiers
                SET consumed_at_utc = @now
                WHERE capability_kind = 'exchange' AND capability_id = @exchange
                  AND epoch = @epoch AND generation = @generation;

                INSERT INTO play_auth.grants(
                    grant_id, exchange_id, session_id, participant_id, user_id, role,
                    device_thumbprint, status, session_authorization_version,
                    participant_authorization_version, epoch, generation,
                    issued_at_utc, updated_at_utc, expires_at_utc, refresh_until_utc)
                VALUES (@grant, @exchange, @session, @participant, @user, @role,
                    @device, 'active', @session_version, @participant_version,
                    @epoch, @generation, @now, @now, @expires, @refresh_until);

                INSERT INTO play_auth.capability_verifiers(
                    capability_kind, capability_id, epoch, generation, key_id,
                    verifier_hmac, created_at_utc, expires_at_utc)
                VALUES ('grant', @grant, @epoch, @generation, @key_id,
                    @verifier, @now, @expires)
                """);
        BindCommon(mutate, state, now, mutation.SessionId, mutation.ParticipantId,
            mutation.UserId, mutation.Role, mutation.ExpectedSessionAuthorizationVersion,
            mutation.ExpectedParticipantAuthorizationVersion);
        mutate.Parameters.AddWithValue("exchange", mutation.ExchangeId);
        mutate.Parameters.AddWithValue("grant", mutation.GrantId);
        mutate.Parameters.AddWithValue("device", mutation.DeviceThumbprint);
        mutate.Parameters.AddWithValue("expires", mutation.GrantExpiresAtUtc);
        mutate.Parameters.AddWithValue("refresh_until", mutation.RefreshUntilUtc);
        mutate.Parameters.AddWithValue("key_id", prepared.Replacement!.KeyId);
        AddBytea(mutate, "verifier", prepared.Replacement.Digest);
        if (await mutate.ExecuteNonQueryAsync(cancellationToken) != 4)
        {
            throw new OptimisticRetryRequiredException();
        }

        return PlayAuthorizationPostgresOutcomeCode.Applied;
    }

    private async Task<PlayAuthorizationPostgresOutcomeCode> RefreshGrantCoreAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        PlayAuthorizationRefreshMutation mutation,
        PreparedCapabilityMutation prepared,
        CancellationToken cancellationToken)
    {
        RequireCommonBinding(mutation.SessionId, mutation.ParticipantId, mutation.UserId, mutation.Role);
        RequireIdentifier(mutation.GrantId, nameof(mutation.GrantId));
        RequireDeviceThumbprint(mutation.DeviceThumbprint);

        await using NpgsqlCommand command = Command(unitOfWork, """
            SELECT g.status, g.expires_at_utc, g.refresh_until_utc,
                   g.session_authorization_version, g.participant_authorization_version,
                   g.user_id, g.role, g.device_thumbprint,
                   s.status, s.authorization_version,
                   p.status, p.authorization_version, p.user_id, p.role,
                   v.key_id, v.verifier_hmac, v.epoch, v.generation
            FROM play_auth.grants g
            JOIN play_auth.sessions s ON s.session_id = g.session_id
            JOIN play_auth.participants p
              ON p.participant_id = g.participant_id AND p.session_id = g.session_id
            JOIN play_auth.capability_verifiers v
              ON v.capability_kind = 'grant' AND v.capability_id = g.grant_id
            WHERE g.grant_id = @grant
              AND g.session_id = @session
              AND g.participant_id = @participant
              AND g.epoch = @epoch AND g.generation = @generation
              AND s.epoch = @epoch AND s.generation = @generation
              AND p.epoch = @epoch AND p.generation = @generation
              AND v.epoch = @epoch AND v.generation = @generation
            FOR UPDATE OF g, s, p, v
            """);
        command.Parameters.AddWithValue("grant", mutation.GrantId);
        command.Parameters.AddWithValue("session", mutation.SessionId);
        command.Parameters.AddWithValue("participant", mutation.ParticipantId);
        command.Parameters.AddWithValue("epoch", state.Epoch);
        command.Parameters.AddWithValue("generation", state.Generation);
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new OptimisticRetryRequiredException();
        }

        DateTimeOffset refreshUntil = reader.GetFieldValue<DateTimeOffset>(2);
        if (!string.Equals(reader.GetString(0), "active", StringComparison.Ordinal))
        {
            return PlayAuthorizationPostgresOutcomeCode.NotFound;
        }

        if (reader.GetFieldValue<DateTimeOffset>(1) <= now || refreshUntil <= now)
        {
            return PlayAuthorizationPostgresOutcomeCode.Expired;
        }

        if (mutation.GrantExpiresAtUtc <= now || mutation.GrantExpiresAtUtc > refreshUntil)
        {
            return PlayAuthorizationPostgresOutcomeCode.InvalidLifecycle;
        }

        if (reader.GetInt64(3) != mutation.ExpectedSessionAuthorizationVersion
            || reader.GetInt64(4) != mutation.ExpectedParticipantAuthorizationVersion
            || !Same(reader.GetString(5), mutation.UserId)
            || !string.Equals(reader.GetString(6), mutation.Role, StringComparison.Ordinal)
            || !string.Equals(reader.GetString(7), mutation.DeviceThumbprint, StringComparison.Ordinal)
            || !string.Equals(reader.GetString(8), "active", StringComparison.Ordinal)
            || reader.GetInt64(9) != mutation.ExpectedSessionAuthorizationVersion
            || !string.Equals(reader.GetString(10), "active", StringComparison.Ordinal)
            || reader.GetInt64(11) != mutation.ExpectedParticipantAuthorizationVersion
            || !Same(reader.GetString(12), mutation.UserId)
            || !string.Equals(reader.GetString(13), mutation.Role, StringComparison.Ordinal))
        {
            return PlayAuthorizationPostgresOutcomeCode.VersionMismatch;
        }

        if (!prepared.Matches(
                PlayAuthorizationCapabilityKind.Grant,
                mutation.GrantId,
                reader.GetString(14),
                (byte[])reader[15],
                reader.GetInt64(16),
                reader.GetInt64(17)))
        {
            throw new OptimisticRetryRequiredException();
        }

        await reader.DisposeAsync();
        await using NpgsqlCommand mutate = Command(unitOfWork, """
                UPDATE play_auth.grants
                SET secret_generation = secret_generation + 1,
                    expires_at_utc = @expires,
                    updated_at_utc = @now
                WHERE grant_id = @grant AND status = 'active'
                  AND epoch = @epoch AND generation = @generation;

                UPDATE play_auth.capability_verifiers
                SET key_id = @key_id, verifier_hmac = @verifier,
                    expires_at_utc = @expires
                WHERE capability_kind = 'grant' AND capability_id = @grant
                  AND epoch = @epoch AND generation = @generation
                """);
        mutate.Parameters.AddWithValue("grant", mutation.GrantId);
        mutate.Parameters.AddWithValue("expires", mutation.GrantExpiresAtUtc);
        mutate.Parameters.AddWithValue("now", now);
        mutate.Parameters.AddWithValue("epoch", state.Epoch);
        mutate.Parameters.AddWithValue("generation", state.Generation);
        mutate.Parameters.AddWithValue("key_id", prepared.Replacement!.KeyId);
        AddBytea(mutate, "verifier", prepared.Replacement.Digest);
        if (await mutate.ExecuteNonQueryAsync(cancellationToken) != 2)
        {
            throw new OptimisticRetryRequiredException();
        }

        return PlayAuthorizationPostgresOutcomeCode.Applied;
    }

    private static async Task<PlayAuthorizationPostgresOutcomeCode> RevokeGrantCoreAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        PlayAuthorizationGrantMutation mutation,
        CancellationToken cancellationToken)
    {
        RequireIdentifier(mutation.GrantId, nameof(mutation.GrantId));
        RequireIdentifier(mutation.SessionId, nameof(mutation.SessionId));
        await using NpgsqlCommand command = Command(unitOfWork, """
            WITH revoked AS (
                UPDATE play_auth.grants g
                SET status = 'revoked', revoked_at_utc = @now, updated_at_utc = @now
                FROM play_auth.sessions s
                WHERE g.grant_id = @grant
                  AND g.session_id = @session
                  AND g.status = 'active'
                  AND g.epoch = @epoch
                  AND g.generation = @generation
                  AND s.session_id = g.session_id
                  AND s.status = 'active'
                  AND s.epoch = @epoch
                  AND s.generation = @generation
                  AND s.authorization_version = @session_version
                RETURNING g.grant_id
            )
            UPDATE play_auth.capability_verifiers verifier
            SET revoked_at_utc = @now
            FROM revoked
            WHERE verifier.capability_kind = 'grant'
              AND verifier.capability_id = revoked.grant_id
              AND verifier.epoch = @epoch
              AND verifier.generation = @generation
            RETURNING verifier.capability_id
            """);
        command.Parameters.AddWithValue("grant", mutation.GrantId);
        command.Parameters.AddWithValue("session", mutation.SessionId);
        command.Parameters.AddWithValue("session_version", mutation.ExpectedSessionAuthorizationVersion);
        command.Parameters.AddWithValue("epoch", state.Epoch);
        command.Parameters.AddWithValue("generation", state.Generation);
        command.Parameters.AddWithValue("now", now);
        object? changed = await command.ExecuteScalarAsync(cancellationToken);
        return changed is null
            ? PlayAuthorizationPostgresOutcomeCode.NotFound
            : PlayAuthorizationPostgresOutcomeCode.Applied;
    }

    private static async Task<PlayAuthorizationPostgresOutcomeCode> RevokeParticipantCoreAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        PlayAuthorizationParticipantMutation mutation,
        CancellationToken cancellationToken)
    {
        RequireIdentifier(mutation.ParticipantId, nameof(mutation.ParticipantId));
        RequireIdentifier(mutation.SessionId, nameof(mutation.SessionId));
        await using NpgsqlCommand command = Command(unitOfWork, """
            WITH changed_participant AS (
                UPDATE play_auth.participants p
                SET status = 'revoked', revoked_at_utc = @now,
                    updated_at_utc = @now,
                    authorization_version = authorization_version + 1
                FROM play_auth.sessions s
                WHERE p.participant_id = @participant
                  AND p.session_id = @session
                  AND p.status = 'active'
                  AND p.epoch = @epoch
                  AND p.generation = @generation
                  AND p.authorization_version = @participant_version
                  AND s.session_id = p.session_id
                  AND s.status = 'active'
                  AND s.epoch = @epoch
                  AND s.generation = @generation
                  AND s.authorization_version = @session_version
                RETURNING p.participant_id
            ), revoked_grants AS (
                UPDATE play_auth.grants g
                SET status = 'revoked', revoked_at_utc = @now, updated_at_utc = @now
                FROM changed_participant changed
                WHERE g.participant_id = changed.participant_id
                  AND g.status = 'active'
                  AND g.epoch = @epoch
                  AND g.generation = @generation
                RETURNING g.grant_id
            ), revoked_verifiers AS (
                UPDATE play_auth.capability_verifiers verifier
                SET revoked_at_utc = @now
                FROM revoked_grants grants
                WHERE verifier.capability_kind = 'grant'
                  AND verifier.capability_id = grants.grant_id
                  AND verifier.epoch = @epoch
                  AND verifier.generation = @generation
            )
            SELECT participant_id FROM changed_participant
            """);
        command.Parameters.AddWithValue("participant", mutation.ParticipantId);
        command.Parameters.AddWithValue("session", mutation.SessionId);
        command.Parameters.AddWithValue("participant_version", mutation.ExpectedParticipantAuthorizationVersion);
        command.Parameters.AddWithValue("session_version", mutation.ExpectedSessionAuthorizationVersion);
        command.Parameters.AddWithValue("epoch", state.Epoch);
        command.Parameters.AddWithValue("generation", state.Generation);
        command.Parameters.AddWithValue("now", now);
        object? changed = await command.ExecuteScalarAsync(cancellationToken);
        return changed is null
            ? PlayAuthorizationPostgresOutcomeCode.NotFound
            : PlayAuthorizationPostgresOutcomeCode.Applied;
    }

    private static Task<PlayAuthorizationPostgresOutcomeCode> BumpSessionCoreAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        PlayAuthorizationSessionMutation mutation,
        CancellationToken cancellationToken)
        => ConditionalMutationAsync(
            unitOfWork,
            """
            UPDATE play_auth.sessions
            SET authorization_version = authorization_version + 1, updated_at_utc = @now
            WHERE session_id = @session
              AND status = 'active'
              AND epoch = @epoch
              AND generation = @generation
              AND authorization_version = @session_version
            RETURNING session_id
            """,
            command =>
            {
                command.Parameters.AddWithValue("session", mutation.SessionId);
                command.Parameters.AddWithValue("session_version", mutation.ExpectedSessionAuthorizationVersion);
                command.Parameters.AddWithValue("epoch", state.Epoch);
                command.Parameters.AddWithValue("generation", state.Generation);
                command.Parameters.AddWithValue("now", now);
            },
            cancellationToken);

    private static Task<PlayAuthorizationPostgresOutcomeCode> BumpParticipantCoreAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        PlayAuthorizationParticipantMutation mutation,
        CancellationToken cancellationToken)
        => ConditionalMutationAsync(
            unitOfWork,
            """
            UPDATE play_auth.participants p
            SET authorization_version = p.authorization_version + 1, updated_at_utc = @now
            FROM play_auth.sessions s
            WHERE p.participant_id = @participant
              AND p.session_id = @session
              AND p.status = 'active'
              AND p.epoch = @epoch
              AND p.generation = @generation
              AND p.authorization_version = @participant_version
              AND s.session_id = p.session_id
              AND s.status = 'active'
              AND s.epoch = @epoch
              AND s.generation = @generation
              AND s.authorization_version = @session_version
            RETURNING p.participant_id
            """,
            command =>
            {
                command.Parameters.AddWithValue("participant", mutation.ParticipantId);
                command.Parameters.AddWithValue("session", mutation.SessionId);
                command.Parameters.AddWithValue("participant_version", mutation.ExpectedParticipantAuthorizationVersion);
                command.Parameters.AddWithValue("session_version", mutation.ExpectedSessionAuthorizationVersion);
                command.Parameters.AddWithValue("epoch", state.Epoch);
                command.Parameters.AddWithValue("generation", state.Generation);
                command.Parameters.AddWithValue("now", now);
            },
            cancellationToken);

    private static Task<PlayAuthorizationPostgresOutcomeCode> CloseSessionCoreAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        PlayAuthorizationSessionMutation mutation,
        CancellationToken cancellationToken)
        => ConditionalMutationAsync(
            unitOfWork,
            """
            UPDATE play_auth.sessions
            SET status = 'closed', closed_at_utc = @now, updated_at_utc = @now,
                authorization_version = authorization_version + 1
            WHERE session_id = @session
              AND status = 'active'
              AND epoch = @epoch
              AND generation = @generation
              AND authorization_version = @session_version
            RETURNING session_id
            """,
            command =>
            {
                command.Parameters.AddWithValue("session", mutation.SessionId);
                command.Parameters.AddWithValue("session_version", mutation.ExpectedSessionAuthorizationVersion);
                command.Parameters.AddWithValue("epoch", state.Epoch);
                command.Parameters.AddWithValue("generation", state.Generation);
                command.Parameters.AddWithValue("now", now);
            },
            cancellationToken);

    private static async Task<PlayAuthorizationPostgresOutcomeCode> ConditionalMutationAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        string sql,
        Action<NpgsqlCommand> bind,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = Command(unitOfWork, sql);
        bind(command);
        return await command.ExecuteScalarAsync(cancellationToken) is null
            ? PlayAuthorizationPostgresOutcomeCode.NotFound
            : PlayAuthorizationPostgresOutcomeCode.Applied;
    }

    private static async Task AppendAuditAndAdvanceStateAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationPostgresState state,
        PreparedAuditMutation prepared,
        string operation,
        string aggregateKind,
        string aggregateId,
        string actorDigestSha256,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = Command(unitOfWork, """
                INSERT INTO play_auth.audit_log(
                    sequence, event_id, epoch, generation, operation, aggregate_kind,
                    aggregate_id, actor_digest_sha256, payload_sha256, previous_hmac,
                    entry_hmac, hmac_key_id, occurred_at_utc, payload_canonical_version)
                VALUES (@sequence, @event_id, @epoch, @generation, @operation, @aggregate_kind,
                    @aggregate_id, @actor, @payload, @previous, @entry, @key_id, @now,
                    @payload_canonical_version);

                UPDATE play_auth.authority_state
                SET clock_high_water_utc = @now,
                    audit_head_sequence = @sequence,
                    audit_head_hmac = @entry,
                    audit_hmac_key_id = @key_id,
                    external_checkpoint = @checkpoint,
                    updated_at_utc = @now
                WHERE singleton = true
                  AND epoch = @epoch
                  AND generation = @generation
                  AND audit_head_sequence = @previous_sequence
                  AND audit_head_hmac = @previous
                  AND external_checkpoint = @checkpoint;

                INSERT INTO play_auth.checkpoint_publications(
                    audit_sequence, publication_id, epoch, generation, clock_high_water_utc,
                    audit_head_hmac, external_checkpoint, digest_algorithm,
                    canonical_version, payload_digest_sha256, state, created_at_utc)
                VALUES (
                    @sequence, @publication_id, @epoch, @generation, @now,
                    @entry, @checkpoint, @digest_algorithm,
                    @canonical_version, @payload_digest, 'pending', @now)
                """);
        command.Parameters.AddWithValue("sequence", prepared.CommittedState.AuditHeadSequence);
        command.Parameters.AddWithValue("event_id", prepared.EventId);
        command.Parameters.AddWithValue("epoch", state.Epoch);
        command.Parameters.AddWithValue("generation", state.Generation);
        command.Parameters.AddWithValue("operation", operation);
        command.Parameters.AddWithValue("aggregate_kind", aggregateKind);
        command.Parameters.AddWithValue("aggregate_id", aggregateId);
        command.Parameters.AddWithValue("actor", actorDigestSha256);
        AddBytea(command, "payload", prepared.PayloadSha256);
        command.Parameters.AddWithValue(
            "payload_canonical_version",
            prepared.PayloadCanonicalVersion);
        AddBytea(command, "previous", state.AuditHeadHmac);
        AddBytea(command, "entry", prepared.AuditDigest.Digest);
        command.Parameters.AddWithValue("key_id", prepared.AuditDigest.KeyId);
        command.Parameters.AddWithValue("now", now);
        AddBytea(command, "checkpoint", prepared.CommittedState.ExternalCheckpoint);
        command.Parameters.AddWithValue("previous_sequence", state.AuditHeadSequence);
        command.Parameters.AddWithValue("publication_id", prepared.PublicationId);
        command.Parameters.AddWithValue("digest_algorithm", prepared.DigestAlgorithm);
        command.Parameters.AddWithValue("canonical_version", prepared.CanonicalVersion);
        AddBytea(command, "payload_digest", prepared.PayloadDigestSha256);
        if (await command.ExecuteNonQueryAsync(cancellationToken) != 3)
        {
            throw new OptimisticRetryRequiredException();
        }
    }

    private static async Task CompleteIdempotencyAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        byte[] scopeHash,
        byte[] keyHash,
        PlayAuthorizationProtectedReceipt receipt,
        int responseStatus,
        long auditSequence,
        Guid auditEventId,
        int auditPayloadCanonicalVersion,
        byte[] auditedPayloadSha256,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = Command(unitOfWork, """
            UPDATE play_auth.idempotency_receipts
            SET state = 'completed', response_type = @response_type,
                response_status = @response_status, response_ciphertext = @ciphertext,
                response_plaintext_sha256 = @plaintext_hash, completed_at_utc = @now,
                audit_sequence = @audit_sequence, audit_event_id = @audit_event_id,
                audit_payload_canonical_version = @audit_payload_canonical_version,
                audited_payload_sha256 = @audited_payload_sha256
            WHERE scope_sha256 = @scope AND key_sha256 = @key AND state = 'in_progress'
              AND epoch = @epoch AND generation = @generation
            """);
        command.Parameters.AddWithValue("response_type", receipt.ResponseType);
        command.Parameters.AddWithValue("response_status", responseStatus);
        command.Parameters.AddWithValue("audit_sequence", auditSequence);
        command.Parameters.AddWithValue("audit_event_id", auditEventId);
        command.Parameters.AddWithValue(
            "audit_payload_canonical_version",
            auditPayloadCanonicalVersion);
        AddBytea(command, "audited_payload_sha256", auditedPayloadSha256);
        AddBytea(command, "ciphertext", receipt.Ciphertext);
        AddBytea(command, "plaintext_hash", receipt.PlaintextSha256);
        command.Parameters.AddWithValue("now", now);
        command.Parameters.AddWithValue("epoch", state.Epoch);
        command.Parameters.AddWithValue("generation", state.Generation);
        AddBytea(command, "scope", scopeHash);
        AddBytea(command, "key", keyHash);
        if (await command.ExecuteNonQueryAsync(cancellationToken) != 1)
        {
            throw new InvalidOperationException("The Play authorization idempotency receipt did not complete atomically.");
        }
    }

    private async Task<bool> RecoverCommittedCheckpointAsync(
        PlayAuthorizationPostgresState committedState,
        CancellationToken cancellationToken)
    {
        try
        {
            for (int pass = 0; pass < MaximumRecoveryPasses; pass++)
            {
                await _checkpointReconciler.ReconcileAsync(
                    MaximumRecoveryPublications,
                    cancellationToken);
                if (await _checkpointReconciler.IsPublishedAsync(
                        committedState.AuditHeadSequence,
                        committedState.Epoch,
                        committedState.Generation,
                        cancellationToken))
                {
                    return true;
                }

                await Task.Delay(RecoveryRetryDelay, _timeProvider, cancellationToken);
            }

            return false;
        }
        catch (Exception exception) when (
            exception is PlayAuthorizationExternalAuthorityUnavailableException
                or NpgsqlException
                or IOException
                or TimeoutException
                or OperationCanceledException)
        {
            return false;
        }
    }

    private async Task NotifyCommitObserverAsync()
    {
        using CancellationTokenSource deadline =
            new(PostCommitObserverDeadline, _timeProvider);
        Task? observerTask = null;
        try
        {
            observerTask = _commitObserver.AfterCommitAsync(deadline.Token).AsTask();
            await observerTask.WaitAsync(
                PostCommitObserverDeadline,
                _timeProvider,
                CancellationToken.None);
        }
        catch (Exception exception) when (!IsFatal(exception))
        {
            if (observerTask is not null)
            {
                _ = observerTask.ContinueWith(
                    static completed => _ = completed.Exception,
                    CancellationToken.None,
                    TaskContinuationOptions.ExecuteSynchronously
                    | TaskContinuationOptions.OnlyOnFaulted,
                    TaskScheduler.Default);
            }

            // The observer is diagnostic only. Recovery receives its own fresh deadline.
        }
    }

    private async Task<PlayAuthorizationPostgresMutationResult> ReconcileAndLookupReceiptAsync(
        PlayAuthorizationDurableRequest request)
    {
        using CancellationTokenSource recoveryDeadline =
            new(PostCommitRecoveryDeadline, _timeProvider);
        try
        {
            for (int pass = 0; pass < MaximumRecoveryPasses; pass++)
            {
                await _checkpointReconciler.ReconcileAsync(
                    MaximumRecoveryPublications,
                    recoveryDeadline.Token);
                PlayAuthorizationPostgresMutationResult? resolved =
                    await LookupIdempotencyReceiptCoreAsync(request, recoveryDeadline.Token);
                if (resolved is not null
                    && resolved.Code != PlayAuthorizationPostgresOutcomeCode.CheckpointPending)
                {
                    return resolved;
                }

                await Task.Delay(RecoveryRetryDelay, _timeProvider, recoveryDeadline.Token);
            }

            return new(PlayAuthorizationPostgresOutcomeCode.CheckpointPending);
        }
        catch (Exception exception) when (
            exception is PlayAuthorizationExternalAuthorityUnavailableException
                or NpgsqlException
                or IOException
                or TimeoutException
                or OperationCanceledException)
        {
            return new(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable);
        }
    }

    private static async Task<DateTimeOffset> ReadEffectiveDatabaseTimeAsync(
        IPlayAuthorizationPostgresUnitOfWork unitOfWork,
        PlayAuthorizationPostgresState state,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = Command(unitOfWork, "SELECT clock_timestamp()");
        object databaseClock = await command.ExecuteScalarAsync(cancellationToken)
            ?? throw new InvalidOperationException("PostgreSQL did not return its clock.");
        DateTimeOffset databaseNow = databaseClock switch
        {
            DateTime value => new DateTimeOffset(DateTime.SpecifyKind(value, DateTimeKind.Utc)),
            DateTimeOffset value => value.ToUniversalTime(),
            _ => throw new InvalidOperationException(
                "PostgreSQL returned an unsupported clock representation.")
        };
        return databaseNow > state.ClockHighWaterUtc ? databaseNow : state.ClockHighWaterUtc;
    }

    private static byte[] HashUtf8(string value)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(value);
        try
        {
            return SHA256.HashData(bytes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(bytes);
        }
    }

    private static byte[] ParseSha256(string value, string parameterName)
    {
        ValidateSha256(value, parameterName);
        return Convert.FromHexString(value);
    }

    private static void ValidateDurableRequest(PlayAuthorizationDurableRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        RequireIdentifier(request.Scope, nameof(request.Scope), 256);
        if (!PlayAuthorizationIdempotencyCoordinator.ValidKey(request.IdempotencyKey))
        {
            throw new ArgumentException("The idempotency key is invalid.", nameof(request));
        }

        ValidateSha256(request.FingerprintSha256, nameof(request.FingerprintSha256));
        if (!Enum.IsDefined(request.Operation))
        {
            throw new ArgumentException("The durable Play authorization operation is invalid.", nameof(request));
        }

        RequireIdentifier(request.Operation.ToDatabaseValue(), nameof(request.Operation), 64);
        ArgumentNullException.ThrowIfNull(request.Response);
    }

    private static DateTimeOffset ReadDateTimeOffset(NpgsqlDataReader reader, int ordinal)
    {
        object value = reader.GetValue(ordinal);
        return value switch
        {
            DateTime dateTime => new DateTimeOffset(DateTime.SpecifyKind(dateTime, DateTimeKind.Utc)),
            DateTimeOffset dateTimeOffset => dateTimeOffset.ToUniversalTime(),
            _ => throw new InvalidOperationException("PostgreSQL returned an unsupported clock representation.")
        };
    }

    private static void RequireCommonBinding(
        string sessionId,
        string participantId,
        string userId,
        string role)
    {
        RequireIdentifier(sessionId, nameof(sessionId));
        RequireIdentifier(participantId, nameof(participantId));
        RequireIdentifier(userId, nameof(userId));
        if (role is not (PlaySessionRoles.GameMaster or PlaySessionRoles.Player or PlaySessionRoles.Observer))
        {
            throw new ArgumentException("The Play authorization role is invalid.", nameof(role));
        }
    }

    private static void RequireIdentifier(string value, string parameterName, int maximumLength = 128)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > maximumLength)
        {
            throw new ArgumentException("The Play authorization identifier is invalid.", parameterName);
        }
    }

    private static void RequireDeviceThumbprint(string value)
        => ValidateSha256(value, nameof(value));

    private static void ValidateSha256(string value, string parameterName)
    {
        if (value is null
            || value.Length != 64
            || value.Any(character => character is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))
        {
            throw new ArgumentException("A lowercase SHA-256 digest is required.", parameterName);
        }
    }

    private static void ValidateHmacDigest(PlayAuthorizationKeyedDigest? digest, string purpose)
    {
        if (digest is null
            || string.IsNullOrWhiteSpace(digest.KeyId)
            || digest.KeyId.Length > 128
            || digest.Digest is null
            || digest.Digest.Length != PlayAuthorizationPostgresDurabilityInvariants.HmacSizeInBytes)
        {
            throw new CryptographicException(
                $"The Play authorization {purpose} HMAC-SHA-256 digest is malformed.");
        }
    }

    private static bool Same(string left, string right)
        => string.Equals(left, right, StringComparison.Ordinal);

    private static void BindCommon(
        NpgsqlCommand command,
        PlayAuthorizationPostgresState state,
        DateTimeOffset now,
        string sessionId,
        string participantId,
        string userId,
        string role,
        long sessionVersion,
        long participantVersion)
    {
        command.Parameters.AddWithValue("session", sessionId);
        command.Parameters.AddWithValue("participant", participantId);
        command.Parameters.AddWithValue("user", userId);
        command.Parameters.AddWithValue("role", role);
        command.Parameters.AddWithValue("session_version", sessionVersion);
        command.Parameters.AddWithValue("participant_version", participantVersion);
        command.Parameters.AddWithValue("epoch", state.Epoch);
        command.Parameters.AddWithValue("generation", state.Generation);
        command.Parameters.AddWithValue("now", now);
    }

    private static NpgsqlCommand Command(IPlayAuthorizationPostgresUnitOfWork unitOfWork, string sql)
    {
        NpgsqlCommand command = unitOfWork.Connection.CreateCommand();
        command.Transaction = unitOfWork.Transaction;
        command.CommandText = sql;
        return command;
    }

    private static void AddBytea(NpgsqlCommand command, string name, byte[] value)
        => command.Parameters.AddWithValue(name, NpgsqlDbType.Bytea, value);

    private static bool IsAmbiguousPersistenceFailure(Exception exception)
        => exception is NpgsqlException or IOException or TimeoutException or OperationCanceledException;

    private static bool ExternalMatchesState(
        PlayAuthorizationExternalEpoch external,
        PlayAuthorizationPostgresState state)
        => state.Epoch > 0
           && state.Generation > 0
           && external.Epoch == state.Epoch
           && external.Generation == state.Generation
           && CryptographicOperations.FixedTimeEquals(
               external.Checkpoint,
               state.ExternalCheckpoint);

    private static bool StatesEqual(
        PlayAuthorizationPostgresState left,
        PlayAuthorizationPostgresState right)
        => left.Epoch == right.Epoch
           && left.Generation == right.Generation
           && left.ClockHighWaterUtc.ToUniversalTime() == right.ClockHighWaterUtc.ToUniversalTime()
           && left.AuditHeadSequence == right.AuditHeadSequence
           && CryptographicOperations.FixedTimeEquals(left.AuditHeadHmac, right.AuditHeadHmac)
           && CryptographicOperations.FixedTimeEquals(
               left.ExternalCheckpoint,
               right.ExternalCheckpoint);

    private static bool ReceiptSnapshotsEqual(ReceiptSnapshot left, ReceiptSnapshot right)
        => string.Equals(left.Operation, right.Operation, StringComparison.Ordinal)
           && left.Epoch == right.Epoch
           && left.Generation == right.Generation
           && left.ExpiresAtUtc.ToUniversalTime() == right.ExpiresAtUtc.ToUniversalTime()
           && string.Equals(left.ResponseType, right.ResponseType, StringComparison.Ordinal)
           && left.AuditSequence == right.AuditSequence
           && left.ReceiptAuditEventId == right.ReceiptAuditEventId
           && left.ReceiptAuditPayloadCanonicalVersion == right.ReceiptAuditPayloadCanonicalVersion
           && left.AuditEventId == right.AuditEventId
           && left.AuditPayloadCanonicalVersion == right.AuditPayloadCanonicalVersion
           && string.Equals(left.AuditAggregateKind, right.AuditAggregateKind, StringComparison.Ordinal)
           && string.Equals(left.AuditAggregateId, right.AuditAggregateId, StringComparison.Ordinal)
           && string.Equals(left.AuditActorDigestSha256, right.AuditActorDigestSha256, StringComparison.Ordinal)
           && left.PublicationId == right.PublicationId
           && string.Equals(left.DigestAlgorithm, right.DigestAlgorithm, StringComparison.Ordinal)
           && left.CanonicalVersion == right.CanonicalVersion
           && CryptographicOperations.FixedTimeEquals(left.FingerprintSha256, right.FingerprintSha256)
           && CryptographicOperations.FixedTimeEquals(left.ScopeSha256, right.ScopeSha256)
           && CryptographicOperations.FixedTimeEquals(
               left.IdempotencyKeySha256,
               right.IdempotencyKeySha256)
           && CryptographicOperations.FixedTimeEquals(
               left.ReceiptAuditedPayloadSha256,
               right.ReceiptAuditedPayloadSha256)
           && CryptographicOperations.FixedTimeEquals(
               left.AuditPayloadSha256,
               right.AuditPayloadSha256)
           && CryptographicOperations.FixedTimeEquals(
               left.ResponseCiphertext,
               right.ResponseCiphertext)
           && CryptographicOperations.FixedTimeEquals(
               left.ResponsePlaintextSha256,
               right.ResponsePlaintextSha256)
           && CryptographicOperations.FixedTimeEquals(left.AuditEntryHmac, right.AuditEntryHmac)
           && CryptographicOperations.FixedTimeEquals(
               left.PayloadDigestSha256,
               right.PayloadDigestSha256)
           && StatesEqual(left.PublicationState, right.PublicationState)
           && StatesEqual(left.AuthorityState, right.AuthorityState);

    private static bool IsFatal(Exception exception)
        => exception is OutOfMemoryException
            or StackOverflowException
            or AccessViolationException;

    private sealed class OptimisticAuthoritySnapshot : IDisposable
    {
        public OptimisticAuthoritySnapshot(PlayAuthorizationPostgresState state)
        {
            State = state;
        }

        public PlayAuthorizationPostgresState State { get; }

        public void Dispose()
        {
            CryptographicOperations.ZeroMemory(State.AuditHeadHmac);
            CryptographicOperations.ZeroMemory(State.ExternalCheckpoint);
        }
    }

    private sealed class CapabilityVerifierSnapshot : IDisposable
    {
        public CapabilityVerifierSnapshot(
            PlayAuthorizationCapabilityKind kind,
            string capabilityId,
            string keyId,
            byte[] verifierHmac,
            long epoch,
            long generation)
        {
            Kind = kind;
            CapabilityId = capabilityId;
            KeyId = keyId;
            VerifierHmac = verifierHmac;
            Epoch = epoch;
            Generation = generation;
        }

        public PlayAuthorizationCapabilityKind Kind { get; }
        public string CapabilityId { get; }
        public string KeyId { get; }
        public byte[] VerifierHmac { get; }
        public long Epoch { get; }
        public long Generation { get; }

        public void Dispose() => CryptographicOperations.ZeroMemory(VerifierHmac);
    }

    private sealed class PreparedCapabilityMutation : IDisposable
    {
        private readonly bool _doesNotRequireCapability;

        private PreparedCapabilityMutation(bool doesNotRequireCapability)
        {
            _doesNotRequireCapability = doesNotRequireCapability;
            PresentedMatches = doesNotRequireCapability;
        }

        public PreparedCapabilityMutation(
            CapabilityVerifierSnapshot snapshot,
            PlayAuthorizationKeyedDigest? replacement,
            bool presentedMatches)
        {
            Snapshot = snapshot;
            Replacement = replacement;
            PresentedMatches = presentedMatches;
        }

        public static PreparedCapabilityMutation None => new(doesNotRequireCapability: true);
        public static PreparedCapabilityMutation Missing => new(doesNotRequireCapability: false);
        public CapabilityVerifierSnapshot? Snapshot { get; }
        public PlayAuthorizationKeyedDigest? Replacement { get; }
        public bool PresentedMatches { get; }
        public bool CanAttempt => _doesNotRequireCapability
            || Snapshot is not null && PresentedMatches && Replacement is not null;

        public bool Matches(
            PlayAuthorizationCapabilityKind kind,
            string capabilityId,
            string keyId,
            byte[] verifierHmac,
            long epoch,
            long generation)
            => Snapshot is not null
               && Snapshot.Kind == kind
               && string.Equals(Snapshot.CapabilityId, capabilityId, StringComparison.Ordinal)
               && string.Equals(Snapshot.KeyId, keyId, StringComparison.Ordinal)
               && Snapshot.Epoch == epoch
               && Snapshot.Generation == generation
               && CryptographicOperations.FixedTimeEquals(Snapshot.VerifierHmac, verifierHmac);

        public void Dispose()
        {
            Snapshot?.Dispose();
            if (Replacement is not null)
            {
                CryptographicOperations.ZeroMemory(Replacement.Digest);
            }
        }
    }

    private sealed class PreparedAuditMutation : IDisposable
    {
        private PlayAuthorizationPostgresState? _committedState;
        public PreparedAuditMutation(
            byte[] payloadSha256,
            PlayAuthorizationKeyedDigest auditDigest,
            Guid eventId,
            Guid publicationId,
            string digestAlgorithm,
            int canonicalVersion,
            byte[] externalCheckpoint)
        {
            PayloadSha256 = payloadSha256;
            AuditDigest = auditDigest;
            EventId = eventId;
            PublicationId = publicationId;
            DigestAlgorithm = digestAlgorithm;
            CanonicalVersion = canonicalVersion;
            ExternalCheckpoint = externalCheckpoint;
        }

        public byte[] PayloadSha256 { get; }
        public PlayAuthorizationKeyedDigest AuditDigest { get; }
        public Guid EventId { get; }
        public int PayloadCanonicalVersion =>
            PlayAuthorizationPostgresDurabilityInvariants.AuditPayloadCanonicalVersion;
        public Guid PublicationId { get; }
        public string DigestAlgorithm { get; }
        public int CanonicalVersion { get; }
        public byte[] ExternalCheckpoint { get; }
        public byte[] PayloadDigestSha256 { get; private set; } = [];
        public PlayAuthorizationPostgresState CommittedState => _committedState
            ?? throw new InvalidOperationException(
                "The checkpoint publication envelope has not been materialized.");

        public void Materialize(PlayAuthorizationPostgresState previousState, DateTimeOffset now)
        {
            if (_committedState is not null || PayloadDigestSha256.Length != 0)
            {
                throw new InvalidOperationException(
                    "The checkpoint publication envelope is already materialized.");
            }

            byte[] committedHmac = AuditDigest.Digest.ToArray();
            PlayAuthorizationPostgresState committedState = new(
                previousState.Epoch,
                previousState.Generation,
                now,
                checked(previousState.AuditHeadSequence + 1),
                committedHmac,
                ExternalCheckpoint.ToArray());
            byte[]? payloadDigest = null;
            try
            {
                payloadDigest = PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
                    PublicationId,
                    committedState,
                    DigestAlgorithm,
                    CanonicalVersion);
                _committedState = committedState;
                PayloadDigestSha256 = payloadDigest;
            }
            catch
            {
                CryptographicOperations.ZeroMemory(committedState.AuditHeadHmac);
                CryptographicOperations.ZeroMemory(committedState.ExternalCheckpoint);
                if (payloadDigest is not null)
                {
                    CryptographicOperations.ZeroMemory(payloadDigest);
                }

                throw;
            }
        }

        public void Dispose()
        {
            CryptographicOperations.ZeroMemory(PayloadSha256);
            CryptographicOperations.ZeroMemory(AuditDigest.Digest);
            CryptographicOperations.ZeroMemory(ExternalCheckpoint);
            if (PayloadDigestSha256.Length != 0)
            {
                CryptographicOperations.ZeroMemory(PayloadDigestSha256);
            }

            if (_committedState is not null)
            {
                CryptographicOperations.ZeroMemory(_committedState.AuditHeadHmac);
                CryptographicOperations.ZeroMemory(_committedState.ExternalCheckpoint);
            }
        }
    }

    private sealed record ReceiptSnapshotRead(
        ReceiptSnapshot? Snapshot,
        PlayAuthorizationPostgresMutationResult? Resolution)
    {
        public static ReceiptSnapshotRead Resolved(PlayAuthorizationPostgresOutcomeCode code)
            => new(null, new PlayAuthorizationPostgresMutationResult(code));
    }

    private sealed class ReceiptSnapshot : IDisposable
    {
        public ReceiptSnapshot(
            byte[] scopeSha256,
            byte[] idempotencyKeySha256,
            byte[] fingerprintSha256,
            string operation,
            long epoch,
            long generation,
            DateTimeOffset expiresAtUtc,
            string responseType,
            byte[] responseCiphertext,
            byte[] responsePlaintextSha256,
            long auditSequence,
            Guid receiptAuditEventId,
            int receiptAuditPayloadCanonicalVersion,
            byte[] receiptAuditedPayloadSha256,
            Guid auditEventId,
            int auditPayloadCanonicalVersion,
            byte[] auditPayloadSha256,
            string auditAggregateKind,
            string auditAggregateId,
            string auditActorDigestSha256,
            byte[] auditEntryHmac,
            Guid publicationId,
            PlayAuthorizationPostgresState publicationState,
            string digestAlgorithm,
            int canonicalVersion,
            byte[] payloadDigestSha256,
            PlayAuthorizationPostgresState authorityState)
        {
            ScopeSha256 = scopeSha256;
            IdempotencyKeySha256 = idempotencyKeySha256;
            FingerprintSha256 = fingerprintSha256;
            Operation = operation;
            Epoch = epoch;
            Generation = generation;
            ExpiresAtUtc = expiresAtUtc;
            ResponseType = responseType;
            ResponseCiphertext = responseCiphertext;
            ResponsePlaintextSha256 = responsePlaintextSha256;
            AuditSequence = auditSequence;
            ReceiptAuditEventId = receiptAuditEventId;
            ReceiptAuditPayloadCanonicalVersion = receiptAuditPayloadCanonicalVersion;
            ReceiptAuditedPayloadSha256 = receiptAuditedPayloadSha256;
            AuditEventId = auditEventId;
            AuditPayloadCanonicalVersion = auditPayloadCanonicalVersion;
            AuditPayloadSha256 = auditPayloadSha256;
            AuditAggregateKind = auditAggregateKind;
            AuditAggregateId = auditAggregateId;
            AuditActorDigestSha256 = auditActorDigestSha256;
            AuditEntryHmac = auditEntryHmac;
            PublicationId = publicationId;
            PublicationState = publicationState;
            DigestAlgorithm = digestAlgorithm;
            CanonicalVersion = canonicalVersion;
            PayloadDigestSha256 = payloadDigestSha256;
            AuthorityState = authorityState;
        }

        public byte[] ScopeSha256 { get; }
        public byte[] IdempotencyKeySha256 { get; }
        public byte[] FingerprintSha256 { get; }
        public string Operation { get; }
        public long Epoch { get; }
        public long Generation { get; }
        public DateTimeOffset ExpiresAtUtc { get; }
        public string ResponseType { get; }
        public byte[] ResponseCiphertext { get; }
        public byte[] ResponsePlaintextSha256 { get; }
        public long AuditSequence { get; }
        public Guid ReceiptAuditEventId { get; }
        public int ReceiptAuditPayloadCanonicalVersion { get; }
        public byte[] ReceiptAuditedPayloadSha256 { get; }
        public Guid AuditEventId { get; }
        public int AuditPayloadCanonicalVersion { get; }
        public byte[] AuditPayloadSha256 { get; }
        public string AuditAggregateKind { get; }
        public string AuditAggregateId { get; }
        public string AuditActorDigestSha256 { get; }
        public byte[] AuditEntryHmac { get; }
        public Guid PublicationId { get; }
        public PlayAuthorizationPostgresState PublicationState { get; }
        public string DigestAlgorithm { get; }
        public int CanonicalVersion { get; }
        public byte[] PayloadDigestSha256 { get; }
        public PlayAuthorizationPostgresState AuthorityState { get; }

        public bool HasValidAuditBinding()
        {
            if (ReceiptAuditEventId != AuditEventId
                || ReceiptAuditPayloadCanonicalVersion
                    != PlayAuthorizationPostgresDurabilityInvariants.AuditPayloadCanonicalVersion
                || AuditPayloadCanonicalVersion != ReceiptAuditPayloadCanonicalVersion
                || !CryptographicOperations.FixedTimeEquals(
                    ReceiptAuditedPayloadSha256,
                    AuditPayloadSha256))
            {
                return false;
            }

            byte[] actual = PlayAuthorizationAuditPayloadCanonicalizer.ComputePayloadDigest(
                AuditEventId,
                Epoch,
                Generation,
                AuditSequence,
                Operation,
                AuditAggregateKind,
                AuditAggregateId,
                AuditActorDigestSha256,
                ScopeSha256,
                IdempotencyKeySha256,
                FingerprintSha256,
                ResponsePlaintextSha256,
                AuditPayloadCanonicalVersion);
            try
            {
                return CryptographicOperations.FixedTimeEquals(actual, AuditPayloadSha256);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(actual);
            }
        }

        public bool HasValidPublicationDigest()
        {
            byte[] actual = PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
                PublicationId,
                PublicationState,
                DigestAlgorithm,
                CanonicalVersion);
            try
            {
                return CryptographicOperations.FixedTimeEquals(actual, PayloadDigestSha256);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(actual);
            }
        }

        public void Dispose()
        {
            CryptographicOperations.ZeroMemory(ScopeSha256);
            CryptographicOperations.ZeroMemory(IdempotencyKeySha256);
            CryptographicOperations.ZeroMemory(FingerprintSha256);
            CryptographicOperations.ZeroMemory(ResponseCiphertext);
            CryptographicOperations.ZeroMemory(ResponsePlaintextSha256);
            CryptographicOperations.ZeroMemory(ReceiptAuditedPayloadSha256);
            CryptographicOperations.ZeroMemory(AuditPayloadSha256);
            CryptographicOperations.ZeroMemory(AuditEntryHmac);
            CryptographicOperations.ZeroMemory(PayloadDigestSha256);
            CryptographicOperations.ZeroMemory(PublicationState.AuditHeadHmac);
            CryptographicOperations.ZeroMemory(PublicationState.ExternalCheckpoint);
            CryptographicOperations.ZeroMemory(AuthorityState.AuditHeadHmac);
            CryptographicOperations.ZeroMemory(AuthorityState.ExternalCheckpoint);
        }
    }

    private sealed class OptimisticRetryRequiredException : Exception
    {
    }
}
