using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Services.KarmaForge;

public sealed record AliceDraftTraitValue(string Key, int Value);

public sealed record AliceDraftCreateRequest(
    string RunnerId,
    long ExpectedRunnerRevision,
    string Objective,
    IReadOnlyList<AliceDraftTraitValue>? CurrentTraits,
    string IdempotencyKey);

public sealed record AliceDraftCompareRequest(
    long ExpectedVersion,
    string DraftFingerprint,
    string IdempotencyKey);

public sealed record AliceDraftApplyRequest(
    long ExpectedVersion,
    string ComparisonSha256,
    string CompareReceiptId,
    string IdempotencyKey);

public sealed record AliceDraftDiscardRequest(
    long ExpectedVersion,
    string IdempotencyKey);

public sealed record AliceDraftProposedChange(
    string TraitKey,
    int Before,
    int After,
    int Delta,
    string ReasonCode);

public sealed record AliceDraftAuditReceipt(
    string Contract,
    string ReceiptId,
    string DraftId,
    long Sequence,
    string Action,
    string FromState,
    string ToState,
    long ResultVersion,
    string ActorSubjectSha256,
    string MutationScope,
    string Authority,
    string BeforeSha256,
    string AfterSha256,
    DateTimeOffset RecordedAtUtc);

public sealed record AliceDraftProjection(
    string Contract,
    string DraftId,
    string RunnerId,
    long RunnerRevision,
    string Objective,
    string State,
    long Version,
    string DraftFingerprint,
    string? ComparisonSha256,
    IReadOnlyList<AliceDraftTraitValue> BaselineTraits,
    IReadOnlyList<AliceDraftProposedChange> ProposedChanges,
    IReadOnlyList<AliceDraftTraitValue>? AppliedTraits,
    IReadOnlyList<AliceDraftAuditReceipt> AuditReceipts,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    string MutationScope,
    string Authority,
    string PersistencePosture,
    string ProviderPosture);

public sealed class AliceDraftConflictException : Exception
{
    public AliceDraftConflictException(string message)
        : base(message)
    {
    }
}

/// <summary>
/// Owns the bounded first-party ALICE mutation lane. The service accepts only an
/// allowlisted numeric runner snapshot, computes changes locally, and never sends
/// character state or mutation authority to a provider.
/// </summary>
public sealed class AliceDraftWorkflowService
{
    public const string ProjectionContract = "chummer.alice-draft-workflow/v1";
    public const string ReceiptContract = "chummer.alice-draft-audit-receipt/v1";

    private const int MaxIdentifierLength = 128;
    private const int MaxIdempotencyKeyLength = 128;
    private const int MaxTraits = 32;
    private const int MaxTraitValue = 20;
    private const int DefaultMaxDraftsPerSubject = 32;
    private const int DefaultMaxDraftsGlobal = 2048;

    private static readonly IReadOnlyDictionary<string, (string TraitKey, string ReasonCode)> ObjectiveRules
        = new Dictionary<string, (string TraitKey, string ReasonCode)>(StringComparer.Ordinal)
        {
            ["initiative"] = ("reaction", "alice.initiative.reaction_plus_one"),
            ["matrix"] = ("logic", "alice.matrix.logic_plus_one"),
            ["resilience"] = ("willpower", "alice.resilience.willpower_plus_one"),
            ["social"] = ("charisma", "alice.social.charisma_plus_one"),
            ["stealth"] = ("agility", "alice.stealth.agility_plus_one"),
            ["survivability"] = ("body", "alice.survivability.body_plus_one")
        };

    private static readonly HashSet<string> AllowedTraits = new(StringComparer.Ordinal)
    {
        "agility",
        "armor",
        "body",
        "charisma",
        "edge",
        "initiative",
        "intuition",
        "logic",
        "reaction",
        "resources",
        "willpower"
    };

    private readonly object _gate = new();
    private readonly Dictionary<(string SubjectHash, string DraftId), DraftState> _drafts = new();
    private readonly Dictionary<(string SubjectHash, string IdempotencyKey), CreateReplay> _createReplays = new();
    private readonly int _maxDraftsPerSubject;
    private readonly int _maxDraftsGlobal;

    public AliceDraftWorkflowService()
        : this(DefaultMaxDraftsPerSubject, DefaultMaxDraftsGlobal)
    {
    }

    public AliceDraftWorkflowService(int maxDraftsPerSubject, int maxDraftsGlobal)
    {
        if (maxDraftsPerSubject <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxDraftsPerSubject));
        }

        if (maxDraftsGlobal < maxDraftsPerSubject)
        {
            throw new ArgumentOutOfRangeException(
                nameof(maxDraftsGlobal),
                "global draft capacity must be at least the per-subject capacity.");
        }

        _maxDraftsPerSubject = maxDraftsPerSubject;
        _maxDraftsGlobal = maxDraftsGlobal;
    }

    public AliceDraftProjection Create(string authenticatedSubjectId, AliceDraftCreateRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        string subjectHash = HashSubject(authenticatedSubjectId);
        string runnerId = NormalizeIdentifier(request.RunnerId, nameof(request.RunnerId));
        string objective = NormalizeObjective(request.Objective);
        string idempotencyKey = NormalizeIdempotencyKey(request.IdempotencyKey);
        if (request.ExpectedRunnerRevision < 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(request.ExpectedRunnerRevision),
                "expected runner revision cannot be negative.");
        }

        AliceDraftTraitValue[] traits = NormalizeTraits(request.CurrentTraits);
        (string targetTrait, string reasonCode) = ObjectiveRules[objective];
        AliceDraftTraitValue currentTarget = traits.FirstOrDefault(item => string.Equals(item.Key, targetTrait, StringComparison.Ordinal))
            ?? throw new ArgumentException(
                $"objective {objective} requires the allowlisted {targetTrait} trait.",
                nameof(request.CurrentTraits));
        if (currentTarget.Value >= MaxTraitValue)
        {
            throw new ArgumentException(
                $"objective {objective} cannot propose a value above the bounded trait maximum.",
                nameof(request.CurrentTraits));
        }

        AliceDraftProposedChange[] proposedChanges =
        [
            new(
                TraitKey: targetTrait,
                Before: currentTarget.Value,
                After: currentTarget.Value + 1,
                Delta: 1,
                ReasonCode: reasonCode)
        ];
        string requestFingerprint = HashLines(
            "create",
            runnerId,
            request.ExpectedRunnerRevision.ToString(System.Globalization.CultureInfo.InvariantCulture),
            objective,
            TraitsCanonicalForm(traits));

        lock (_gate)
        {
            var replayKey = (subjectHash, idempotencyKey);
            if (_createReplays.TryGetValue(replayKey, out CreateReplay? replay))
            {
                if (!string.Equals(replay.RequestFingerprint, requestFingerprint, StringComparison.Ordinal))
                {
                    throw new AliceDraftConflictException(
                        "create idempotency key was already used with a different normalized request.");
                }

                return Snapshot(_drafts[(subjectHash, replay.DraftId)]);
            }

            PruneTerminalDraftsForCapacity(subjectHash);
            if (_drafts.Count >= _maxDraftsGlobal)
            {
                throw new AliceDraftConflictException(
                    "ALICE draft capacity is reached; no new draft was created.");
            }

            int subjectDraftCount = _drafts.Keys.Count(key => string.Equals(key.SubjectHash, subjectHash, StringComparison.Ordinal));
            if (subjectDraftCount >= _maxDraftsPerSubject)
            {
                throw new AliceDraftConflictException(
                    "ALICE subject draft capacity is reached; no new draft was created.");
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            string draftFingerprint = HashLines(
                "draft",
                runnerId,
                request.ExpectedRunnerRevision.ToString(System.Globalization.CultureInfo.InvariantCulture),
                objective,
                TraitsCanonicalForm(traits),
                ChangesCanonicalForm(proposedChanges));
            string draftId = "alice-draft-" + HashLines(subjectHash, idempotencyKey)[..24];
            var state = new DraftState(
                draftId,
                runnerId,
                request.ExpectedRunnerRevision,
                objective,
                draftFingerprint,
                traits,
                proposedChanges,
                now);
            AddReceipt(state, subjectHash, "created", "none", "draft", beforeHash: draftFingerprint, afterHash: StateFingerprint(state));
            _drafts.Add((subjectHash, draftId), state);
            _createReplays.Add(replayKey, new CreateReplay(requestFingerprint, draftId));
            return Snapshot(state);
        }
    }

    public AliceDraftProjection Get(string authenticatedSubjectId, string draftId)
    {
        string subjectHash = HashSubject(authenticatedSubjectId);
        string normalizedDraftId = NormalizeIdentifier(draftId, nameof(draftId));
        lock (_gate)
        {
            return Snapshot(RequireOwnedDraft(subjectHash, normalizedDraftId));
        }
    }

    public AliceDraftProjection Compare(
        string authenticatedSubjectId,
        string draftId,
        AliceDraftCompareRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        string subjectHash = HashSubject(authenticatedSubjectId);
        string normalizedDraftId = NormalizeIdentifier(draftId, nameof(draftId));
        string idempotencyKey = NormalizeIdempotencyKey(request.IdempotencyKey);
        string expectedFingerprint = NormalizeSha256(request.DraftFingerprint, nameof(request.DraftFingerprint));
        string payloadFingerprint = HashLines(
            "compare",
            request.ExpectedVersion.ToString(System.Globalization.CultureInfo.InvariantCulture),
            expectedFingerprint);

        lock (_gate)
        {
            DraftState state = RequireOwnedDraft(subjectHash, normalizedDraftId);
            if (TryReplay(state, "compare", idempotencyKey, payloadFingerprint, out AliceDraftProjection? replay))
            {
                return replay!;
            }

            RequireVersion(state, request.ExpectedVersion);
            RequireState(state, "draft", "only a draft can enter comparison.");
            if (!string.Equals(state.DraftFingerprint, expectedFingerprint, StringComparison.Ordinal))
            {
                throw new AliceDraftConflictException("draft fingerprint does not match the reviewed draft.");
            }

            string beforeHash = StateFingerprint(state);
            state.State = "compared";
            state.Version++;
            state.ComparisonSha256 = HashLines(
                "comparison",
                state.DraftFingerprint,
                ChangesCanonicalForm(state.ProposedChanges));
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            AddReceipt(state, subjectHash, "compared", "draft", "compared", beforeHash, StateFingerprint(state));
            AliceDraftProjection result = Snapshot(state);
            StoreReplay(state, "compare", idempotencyKey, payloadFingerprint, result);
            return result;
        }
    }

    public AliceDraftProjection Apply(
        string authenticatedSubjectId,
        string draftId,
        AliceDraftApplyRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        string subjectHash = HashSubject(authenticatedSubjectId);
        string normalizedDraftId = NormalizeIdentifier(draftId, nameof(draftId));
        string idempotencyKey = NormalizeIdempotencyKey(request.IdempotencyKey);
        string comparisonSha256 = NormalizeSha256(request.ComparisonSha256, nameof(request.ComparisonSha256));
        string compareReceiptId = NormalizeReceiptId(request.CompareReceiptId);
        string payloadFingerprint = HashLines(
            "apply",
            request.ExpectedVersion.ToString(System.Globalization.CultureInfo.InvariantCulture),
            comparisonSha256,
            compareReceiptId);

        lock (_gate)
        {
            DraftState state = RequireOwnedDraft(subjectHash, normalizedDraftId);
            if (TryReplay(state, "apply", idempotencyKey, payloadFingerprint, out AliceDraftProjection? replay))
            {
                return replay!;
            }

            RequireVersion(state, request.ExpectedVersion);
            RequireState(state, "compared", "apply requires a completed compare step.");
            if (!string.Equals(state.ComparisonSha256, comparisonSha256, StringComparison.Ordinal))
            {
                throw new AliceDraftConflictException("comparison digest does not match the reviewed comparison.");
            }

            AliceDraftAuditReceipt compareReceipt = state.AuditReceipts.LastOrDefault(item => string.Equals(item.Action, "compared", StringComparison.Ordinal))
                ?? throw new AliceDraftConflictException("comparison receipt is missing; apply fails closed.");
            if (!string.Equals(compareReceipt.ReceiptId, compareReceiptId, StringComparison.Ordinal))
            {
                throw new AliceDraftConflictException("comparison receipt does not match the reviewed comparison.");
            }

            string beforeHash = StateFingerprint(state);
            Dictionary<string, int> applied = state.BaselineTraits.ToDictionary(static item => item.Key, static item => item.Value, StringComparer.Ordinal);
            foreach (AliceDraftProposedChange change in state.ProposedChanges)
            {
                if (!applied.TryGetValue(change.TraitKey, out int current) || current != change.Before)
                {
                    throw new AliceDraftConflictException("baseline changed after compare; apply fails closed.");
                }

                applied[change.TraitKey] = change.After;
            }

            state.AppliedTraits = applied
                .OrderBy(static item => item.Key, StringComparer.Ordinal)
                .Select(static item => new AliceDraftTraitValue(item.Key, item.Value))
                .ToArray();
            state.State = "applied";
            state.Version++;
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            AddReceipt(state, subjectHash, "applied", "compared", "applied", beforeHash, StateFingerprint(state));
            AliceDraftProjection result = Snapshot(state);
            StoreReplay(state, "apply", idempotencyKey, payloadFingerprint, result);
            return result;
        }
    }

    public AliceDraftProjection Discard(
        string authenticatedSubjectId,
        string draftId,
        AliceDraftDiscardRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        string subjectHash = HashSubject(authenticatedSubjectId);
        string normalizedDraftId = NormalizeIdentifier(draftId, nameof(draftId));
        string idempotencyKey = NormalizeIdempotencyKey(request.IdempotencyKey);
        string payloadFingerprint = HashLines(
            "discard",
            request.ExpectedVersion.ToString(System.Globalization.CultureInfo.InvariantCulture));

        lock (_gate)
        {
            DraftState state = RequireOwnedDraft(subjectHash, normalizedDraftId);
            if (TryReplay(state, "discard", idempotencyKey, payloadFingerprint, out AliceDraftProjection? replay))
            {
                return replay!;
            }

            RequireVersion(state, request.ExpectedVersion);
            if (state.State is not ("draft" or "compared"))
            {
                throw new AliceDraftConflictException("only a draft or compared variant can be discarded.");
            }

            string fromState = state.State;
            string beforeHash = StateFingerprint(state);
            state.State = "discarded";
            state.Version++;
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            AddReceipt(state, subjectHash, "discarded", fromState, "discarded", beforeHash, StateFingerprint(state));
            AliceDraftProjection result = Snapshot(state);
            StoreReplay(state, "discard", idempotencyKey, payloadFingerprint, result);
            return result;
        }
    }

    private static AliceDraftTraitValue[] NormalizeTraits(IReadOnlyList<AliceDraftTraitValue>? input)
    {
        if (input is null || input.Count == 0)
        {
            throw new ArgumentException("current traits are required.", nameof(input));
        }

        if (input.Count > MaxTraits)
        {
            throw new ArgumentException($"current traits cannot exceed {MaxTraits} entries.", nameof(input));
        }

        var normalized = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (AliceDraftTraitValue trait in input)
        {
            if (trait is null)
            {
                throw new ArgumentException("current traits cannot contain null entries.", nameof(input));
            }

            string key = (trait.Key ?? string.Empty).Trim().ToLowerInvariant();
            if (!AllowedTraits.Contains(key))
            {
                throw new ArgumentException("current traits contain an unsupported trait key.", nameof(input));
            }

            if (trait.Value is < 0 or > MaxTraitValue)
            {
                throw new ArgumentException(
                    $"trait values must be between 0 and {MaxTraitValue}.",
                    nameof(input));
            }

            if (!normalized.TryAdd(key, trait.Value))
            {
                throw new ArgumentException("current traits contain a duplicate trait key.", nameof(input));
            }
        }

        return normalized
            .OrderBy(static item => item.Key, StringComparer.Ordinal)
            .Select(static item => new AliceDraftTraitValue(item.Key, item.Value))
            .ToArray();
    }

    private static string NormalizeObjective(string value)
    {
        string normalized = (value ?? string.Empty).Trim().ToLowerInvariant();
        if (!ObjectiveRules.ContainsKey(normalized))
        {
            throw new ArgumentException(
                "objective must be one of: initiative, matrix, resilience, social, stealth, survivability.",
                nameof(value));
        }

        return normalized;
    }

    private static string NormalizeIdentifier(string value, string parameterName)
    {
        string normalized = (value ?? string.Empty).Trim();
        if (normalized.Length is 0 or > MaxIdentifierLength
            || normalized.Any(static character => !char.IsLetterOrDigit(character) && character is not ('-' or '_' or '.' or ':')))
        {
            throw new ArgumentException(
                $"{parameterName} must be 1-{MaxIdentifierLength} safe identifier characters.",
                parameterName);
        }

        return normalized;
    }

    private static string NormalizeIdempotencyKey(string value)
    {
        string normalized = (value ?? string.Empty).Trim();
        if (normalized.Length < 8 || normalized.Length > MaxIdempotencyKeyLength
            || normalized.Any(char.IsControl))
        {
            throw new ArgumentException(
                $"idempotency key must be 8-{MaxIdempotencyKeyLength} printable characters.",
                nameof(value));
        }

        return normalized;
    }

    private static string NormalizeSha256(string value, string parameterName)
    {
        string normalized = (value ?? string.Empty).Trim().ToLowerInvariant();
        if (normalized.Length != 64 || normalized.Any(static character => !Uri.IsHexDigit(character)))
        {
            throw new ArgumentException($"{parameterName} must be a 64-character SHA-256 digest.", parameterName);
        }

        return normalized;
    }

    private static string NormalizeReceiptId(string value)
    {
        string normalized = (value ?? string.Empty).Trim().ToLowerInvariant();
        const string prefix = "alice-receipt-";
        if (!normalized.StartsWith(prefix, StringComparison.Ordinal)
            || normalized.Length != prefix.Length + 32
            || normalized[prefix.Length..].Any(static character => !Uri.IsHexDigit(character)))
        {
            throw new ArgumentException("compare receipt id is malformed.", nameof(value));
        }

        return normalized;
    }

    private static string HashSubject(string subjectId)
    {
        string normalized = (subjectId ?? string.Empty).Trim();
        if (normalized.Length is 0 or > 512 || normalized.Any(char.IsControl))
        {
            throw new ArgumentException("authenticated subject is invalid.", nameof(subjectId));
        }

        return HashLines("subject", normalized);
    }

    private static string HashLines(params string[] values)
    {
        string canonical = string.Join('\n', values.Select(static value => value.Normalize(NormalizationForm.FormC)));
        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(canonical)));
    }

    private static string TraitsCanonicalForm(IEnumerable<AliceDraftTraitValue> traits)
        => string.Join(';', traits.Select(static item => $"{item.Key}={item.Value.ToString(System.Globalization.CultureInfo.InvariantCulture)}"));

    private static string ChangesCanonicalForm(IEnumerable<AliceDraftProposedChange> changes)
        => string.Join(
            ';',
            changes.Select(static item =>
                $"{item.TraitKey}:{item.Before.ToString(System.Globalization.CultureInfo.InvariantCulture)}>{item.After.ToString(System.Globalization.CultureInfo.InvariantCulture)}:{item.ReasonCode}"));

    private static string StateFingerprint(DraftState state)
        => HashLines(
            "state",
            state.DraftFingerprint,
            state.State,
            state.Version.ToString(System.Globalization.CultureInfo.InvariantCulture),
            state.ComparisonSha256 ?? string.Empty,
            state.AppliedTraits is null ? string.Empty : TraitsCanonicalForm(state.AppliedTraits));

    private static void RequireVersion(DraftState state, long expectedVersion)
    {
        if (expectedVersion != state.Version)
        {
            throw new AliceDraftConflictException(
                $"draft version mismatch; expected {expectedVersion}, current {state.Version}.");
        }
    }

    private static void RequireState(DraftState state, string expected, string message)
    {
        if (!string.Equals(state.State, expected, StringComparison.Ordinal))
        {
            throw new AliceDraftConflictException(message);
        }
    }

    private DraftState RequireOwnedDraft(string subjectHash, string draftId)
        => _drafts.TryGetValue((subjectHash, draftId), out DraftState? state)
            ? state
            : throw new KeyNotFoundException("ALICE draft was not found for the authenticated subject.");

    private void PruneTerminalDraftsForCapacity(string subjectHash)
    {
        while (_drafts.Keys.Count(key => string.Equals(key.SubjectHash, subjectHash, StringComparison.Ordinal))
               >= _maxDraftsPerSubject
               && TryPruneOldestTerminalDraft(subjectHash))
        {
        }

        while (_drafts.Count >= _maxDraftsGlobal && TryPruneOldestTerminalDraft(subjectHash: null))
        {
        }
    }

    private bool TryPruneOldestTerminalDraft(string? subjectHash)
    {
        (string SubjectHash, string DraftId) candidate = _drafts
            .Where(pair => (subjectHash is null
                    || string.Equals(pair.Key.SubjectHash, subjectHash, StringComparison.Ordinal))
                && pair.Value.State is "applied" or "discarded")
            .OrderBy(static pair => pair.Value.UpdatedAtUtc)
            .ThenBy(static pair => pair.Key.DraftId, StringComparer.Ordinal)
            .Select(static pair => pair.Key)
            .FirstOrDefault();
        if (string.IsNullOrEmpty(candidate.SubjectHash))
        {
            return false;
        }

        _drafts.Remove(candidate);
        foreach ((string SubjectHash, string IdempotencyKey) replayKey in _createReplays
                     .Where(pair => string.Equals(pair.Key.SubjectHash, candidate.SubjectHash, StringComparison.Ordinal)
                         && string.Equals(pair.Value.DraftId, candidate.DraftId, StringComparison.Ordinal))
                     .Select(static pair => pair.Key)
                     .ToArray())
        {
            _createReplays.Remove(replayKey);
        }

        return true;
    }

    private static void AddReceipt(
        DraftState state,
        string actorSubjectHash,
        string action,
        string fromState,
        string toState,
        string beforeHash,
        string afterHash)
    {
        long sequence = state.AuditReceipts.Count + 1L;
        string receiptId = "alice-receipt-" + HashLines(
            state.DraftId,
            sequence.ToString(System.Globalization.CultureInfo.InvariantCulture),
            action,
            beforeHash,
            afterHash)[..32];
        state.AuditReceipts.Add(new AliceDraftAuditReceipt(
            ReceiptContract,
            receiptId,
            state.DraftId,
            sequence,
            action,
            fromState,
            toState,
            state.Version,
            "sha256:" + actorSubjectHash,
            "draft_snapshot_only",
            "bounded_first_party_draft_not_character_authority",
            beforeHash,
            afterHash,
            state.UpdatedAtUtc));
    }

    private static bool TryReplay(
        DraftState state,
        string action,
        string idempotencyKey,
        string payloadFingerprint,
        out AliceDraftProjection? projection)
    {
        projection = null;
        if (!state.Replays.TryGetValue(action + ":" + idempotencyKey, out MutationReplay? replay))
        {
            return false;
        }

        if (!string.Equals(replay.PayloadFingerprint, payloadFingerprint, StringComparison.Ordinal))
        {
            throw new AliceDraftConflictException(
                $"{action} idempotency key was already used with a different normalized request.");
        }

        projection = replay.Projection;
        return true;
    }

    private static void StoreReplay(
        DraftState state,
        string action,
        string idempotencyKey,
        string payloadFingerprint,
        AliceDraftProjection projection)
        => state.Replays.Add(action + ":" + idempotencyKey, new MutationReplay(payloadFingerprint, projection));

    private static AliceDraftProjection Snapshot(DraftState state)
        => new(
            ProjectionContract,
            state.DraftId,
            state.RunnerId,
            state.RunnerRevision,
            state.Objective,
            state.State,
            state.Version,
            state.DraftFingerprint,
            state.ComparisonSha256,
            state.BaselineTraits.ToArray(),
            state.ProposedChanges.ToArray(),
            state.AppliedTraits?.ToArray(),
            state.AuditReceipts.ToArray(),
            state.CreatedAtUtc,
            state.UpdatedAtUtc,
            MutationScope: "draft_snapshot_only",
            Authority: "bounded_first_party_draft_not_character_authority",
            PersistencePosture: "process_local_non_durable",
            ProviderPosture: "none; provider execution and provider mutation authority are forbidden");

    private sealed record CreateReplay(string RequestFingerprint, string DraftId);

    private sealed record MutationReplay(string PayloadFingerprint, AliceDraftProjection Projection);

    private sealed class DraftState
    {
        public DraftState(
            string draftId,
            string runnerId,
            long runnerRevision,
            string objective,
            string draftFingerprint,
            AliceDraftTraitValue[] baselineTraits,
            AliceDraftProposedChange[] proposedChanges,
            DateTimeOffset createdAtUtc)
        {
            DraftId = draftId;
            RunnerId = runnerId;
            RunnerRevision = runnerRevision;
            Objective = objective;
            DraftFingerprint = draftFingerprint;
            BaselineTraits = baselineTraits;
            ProposedChanges = proposedChanges;
            CreatedAtUtc = createdAtUtc;
            UpdatedAtUtc = createdAtUtc;
        }

        public string DraftId { get; }
        public string RunnerId { get; }
        public long RunnerRevision { get; }
        public string Objective { get; }
        public string DraftFingerprint { get; }
        public AliceDraftTraitValue[] BaselineTraits { get; }
        public AliceDraftProposedChange[] ProposedChanges { get; }
        public string State { get; set; } = "draft";
        public long Version { get; set; } = 1;
        public string? ComparisonSha256 { get; set; }
        public AliceDraftTraitValue[]? AppliedTraits { get; set; }
        public DateTimeOffset CreatedAtUtc { get; }
        public DateTimeOffset UpdatedAtUtc { get; set; }
        public List<AliceDraftAuditReceipt> AuditReceipts { get; } = [];
        public Dictionary<string, MutationReplay> Replays { get; } = new(StringComparer.Ordinal);
    }
}
