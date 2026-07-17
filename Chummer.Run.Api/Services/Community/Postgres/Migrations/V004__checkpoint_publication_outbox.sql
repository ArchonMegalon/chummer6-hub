CREATE TABLE play_auth.checkpoint_publications (
    audit_sequence bigint PRIMARY KEY
        REFERENCES play_auth.audit_log(sequence) ON DELETE RESTRICT,
    publication_id uuid NOT NULL UNIQUE
        CHECK (publication_id <> '00000000-0000-0000-0000-000000000000'::uuid),
    epoch bigint NOT NULL CHECK (epoch > 0),
    generation bigint NOT NULL CHECK (generation > 0),
    clock_high_water_utc timestamptz NOT NULL,
    audit_head_hmac bytea NOT NULL
        CHECK (octet_length(audit_head_hmac) = 32),
    external_checkpoint bytea NOT NULL
        CHECK (octet_length(external_checkpoint) BETWEEN 1 AND 4096),
    digest_algorithm text NOT NULL CHECK (digest_algorithm = 'SHA-256'),
    canonical_version integer NOT NULL CHECK (canonical_version = 1),
    payload_digest_sha256 bytea NOT NULL CHECK (octet_length(payload_digest_sha256) = 32),
    state text NOT NULL CHECK (state IN ('pending', 'published')),
    fencing_token bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    lease_owner uuid NULL,
    lease_expires_at_utc timestamptz NULL,
    last_attempt_at_utc timestamptz NULL,
    last_error_code text NULL
        CHECK (last_error_code IS NULL OR char_length(last_error_code) BETWEEN 1 AND 64),
    created_at_utc timestamptz NOT NULL,
    published_at_utc timestamptz NULL,
    CHECK ((lease_owner IS NULL) = (lease_expires_at_utc IS NULL)),
    CHECK ((attempt_count = 0) = (last_attempt_at_utc IS NULL)),
    CHECK (last_attempt_at_utc IS NULL OR last_attempt_at_utc >= created_at_utc),
    CHECK (lease_expires_at_utc IS NULL OR lease_expires_at_utc > last_attempt_at_utc),
    CHECK (published_at_utc IS NULL OR published_at_utc >= created_at_utc),
    CHECK (
        (state = 'pending' AND published_at_utc IS NULL)
        OR
        (state = 'published'
            AND published_at_utc IS NOT NULL
            AND lease_owner IS NULL
            AND lease_expires_at_utc IS NULL
            AND last_error_code IS NULL))
);

CREATE INDEX ix_play_auth_checkpoint_publications_pending
    ON play_auth.checkpoint_publications(state, audit_sequence);

-- V1-V3 did not durably bind individual publications. Preserve exactly one quarantined
-- current-head baseline instead of fabricating historical publication rows. Runtime readiness
-- and mutations remain blocked until the external authority verifies this exact baseline.
CREATE TABLE play_auth.checkpoint_baseline (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    baseline_id uuid NOT NULL UNIQUE
        CHECK (baseline_id <> '00000000-0000-0000-0000-000000000000'::uuid),
    epoch bigint NOT NULL CHECK (epoch >= 0),
    generation bigint NOT NULL CHECK (generation >= 0),
    clock_high_water_utc timestamptz NOT NULL,
    audit_head_sequence bigint NOT NULL CHECK (audit_head_sequence >= 0),
    audit_head_hmac bytea NOT NULL CHECK (octet_length(audit_head_hmac) = 32),
    external_checkpoint bytea NOT NULL CHECK (octet_length(external_checkpoint) <= 4096),
    digest_algorithm text NOT NULL CHECK (digest_algorithm = 'SHA-256'),
    canonical_version integer NOT NULL CHECK (canonical_version = 1),
    payload_digest_sha256 bytea NULL CHECK (
        payload_digest_sha256 IS NULL OR octet_length(payload_digest_sha256) = 32),
    state text NOT NULL CHECK (state IN ('quarantined', 'verified')),
    captured_at_utc timestamptz NOT NULL,
    verified_at_utc timestamptz NULL,
    CHECK ((state = 'verified') = (
        verified_at_utc IS NOT NULL AND payload_digest_sha256 IS NOT NULL))
);

INSERT INTO play_auth.checkpoint_baseline(
    singleton, baseline_id, epoch, generation, clock_high_water_utc,
    audit_head_sequence, audit_head_hmac, external_checkpoint,
    digest_algorithm, canonical_version, state, captured_at_utc)
SELECT true, gen_random_uuid(), epoch, generation, clock_high_water_utc,
       audit_head_sequence, audit_head_hmac, external_checkpoint,
       'SHA-256', 1, 'quarantined', clock_timestamp()
FROM play_auth.authority_state
WHERE singleton = true;

DROP TRIGGER idempotency_receipt_transition_guard
    ON play_auth.idempotency_receipts;

DO $migration$
DECLARE
    constraint_to_drop text;
BEGIN
    FOR constraint_to_drop IN
        SELECT constraint_row.conname
        FROM pg_constraint AS constraint_row
        WHERE constraint_row.conrelid = 'play_auth.idempotency_receipts'::regclass
          AND constraint_row.contype = 'c'
          AND pg_get_constraintdef(constraint_row.oid) LIKE '%state%'
    LOOP
        EXECUTE format(
            'ALTER TABLE play_auth.idempotency_receipts DROP CONSTRAINT %I',
            constraint_to_drop);
    END LOOP;
END;
$migration$;

ALTER TABLE play_auth.idempotency_receipts
    ADD COLUMN audit_sequence bigint NULL
        REFERENCES play_auth.audit_log(sequence) ON DELETE RESTRICT,
    ADD COLUMN audit_event_id uuid NULL,
    ADD COLUMN audit_payload_canonical_version integer NULL
        CHECK (audit_payload_canonical_version IS NULL OR audit_payload_canonical_version = 1),
    ADD COLUMN audited_payload_sha256 bytea NULL
        CHECK (audited_payload_sha256 IS NULL OR octet_length(audited_payload_sha256) = 32),
    ADD COLUMN pruned_at_utc timestamptz NULL,
    ADD COLUMN quarantine_until_utc timestamptz NULL;

-- Legacy audit payloads predate the versioned receipt/response commitment. Leave their version
-- NULL rather than pretending that their existing payload digest was produced by canonical v1.
ALTER TABLE play_auth.audit_log
    ADD COLUMN payload_canonical_version integer NULL
        CHECK (payload_canonical_version IS NULL OR payload_canonical_version = 1),
    ADD CONSTRAINT audit_log_payload_binding_v004_unique
        UNIQUE (sequence, event_id, payload_canonical_version, payload_sha256);

ALTER TABLE play_auth.idempotency_receipts
    ADD CONSTRAINT idempotency_receipts_audit_payload_v004_fk
        FOREIGN KEY (
            audit_sequence, audit_event_id,
            audit_payload_canonical_version, audited_payload_sha256)
        REFERENCES play_auth.audit_log(
            sequence, event_id,
            payload_canonical_version, payload_sha256)
        MATCH FULL
        ON DELETE RESTRICT;

-- A V1-V3 completed receipt cannot be bound reliably to its audit event. Scrub all legacy
-- receipts and quarantine their identity rather than risking a cross-operation replay.
DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM play_auth.authority_state
        WHERE singleton = true
          AND isfinite(clock_high_water_utc))
       OR EXISTS (
        SELECT 1
        FROM play_auth.idempotency_receipts
        WHERE NOT isfinite(created_at_utc)
           OR NOT isfinite(expires_at_utc)
           OR (completed_at_utc IS NOT NULL AND NOT isfinite(completed_at_utc))) THEN
        RAISE EXCEPTION 'legacy receipt quarantine requires finite authority and receipt clocks'
            USING ERRCODE = '23514';
    END IF;
END;
$migration$;

WITH migration_clock AS MATERIALIZED (
    SELECT GREATEST(clock_timestamp(), authority.clock_high_water_utc) AS effective_now_utc
    FROM play_auth.authority_state AS authority
    WHERE authority.singleton = true
)
UPDATE play_auth.idempotency_receipts AS receipt
SET state = 'pruned',
    response_type = NULL,
    response_status = NULL,
    response_ciphertext = NULL,
    response_plaintext_sha256 = NULL,
    audit_sequence = NULL,
    audit_event_id = NULL,
    audit_payload_canonical_version = NULL,
    audited_payload_sha256 = NULL,
    pruned_at_utc = GREATEST(migration_clock.effective_now_utc, receipt.expires_at_utc),
    quarantine_until_utc =
        GREATEST(migration_clock.effective_now_utc, receipt.expires_at_utc)
        + INTERVAL '365 days'
FROM migration_clock;

DO $migration$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM play_auth.idempotency_receipts AS receipt
        WHERE receipt.state <> 'pruned'
           OR receipt.response_type IS NOT NULL
           OR receipt.response_status IS NOT NULL
           OR receipt.response_ciphertext IS NOT NULL
           OR receipt.response_plaintext_sha256 IS NOT NULL
           OR receipt.audit_sequence IS NOT NULL
           OR receipt.audit_event_id IS NOT NULL
           OR receipt.audit_payload_canonical_version IS NOT NULL
           OR receipt.audited_payload_sha256 IS NOT NULL
           OR receipt.pruned_at_utc IS NULL
           OR receipt.pruned_at_utc < receipt.expires_at_utc
           OR receipt.quarantine_until_utc IS NULL
           OR receipt.quarantine_until_utc
                <> receipt.pruned_at_utc + INTERVAL '365 days') THEN
        RAISE EXCEPTION 'legacy receipt quarantine could not be established safely'
            USING ERRCODE = '23514';
    END IF;
END;
$migration$;

ALTER TABLE play_auth.idempotency_receipts
    ADD CONSTRAINT idempotency_receipts_finite_times_v004_check
        CHECK (
            isfinite(created_at_utc)
            AND isfinite(expires_at_utc)
            AND (completed_at_utc IS NULL OR isfinite(completed_at_utc))
            AND (pruned_at_utc IS NULL OR isfinite(pruned_at_utc))
            AND (quarantine_until_utc IS NULL OR isfinite(quarantine_until_utc))),
    ADD CONSTRAINT idempotency_receipts_state_v004_check
        CHECK (state IN ('in_progress', 'completed', 'pruned')),
    ADD CONSTRAINT idempotency_receipts_operation_v004_check
        CHECK (operation IN (
            'redeem_invite',
            'consume_exchange',
            'refresh_grant',
            'revoke_grant',
            'revoke_participant',
            'bump_session_version',
            'bump_participant_version',
            'close_session')),
    ADD CONSTRAINT idempotency_receipts_lifecycle_v004_check
        CHECK (
            (state = 'in_progress'
                AND response_type IS NULL
                AND response_status IS NULL
                AND response_ciphertext IS NULL
                AND response_plaintext_sha256 IS NULL
                AND completed_at_utc IS NULL
                AND audit_sequence IS NULL
                AND audit_event_id IS NULL
                AND audit_payload_canonical_version IS NULL
                AND audited_payload_sha256 IS NULL
                AND pruned_at_utc IS NULL
                AND quarantine_until_utc IS NULL)
            OR
            (state = 'completed'
                AND response_type IS NOT NULL
                AND response_status IS NOT NULL
                AND response_ciphertext IS NOT NULL
                AND response_plaintext_sha256 IS NOT NULL
                AND completed_at_utc IS NOT NULL
                AND audit_sequence IS NOT NULL
                AND audit_event_id IS NOT NULL
                AND audit_payload_canonical_version = 1
                AND audited_payload_sha256 IS NOT NULL
                AND pruned_at_utc IS NULL
                AND quarantine_until_utc IS NULL)
            OR
            (state = 'pruned'
                AND response_type IS NULL
                AND response_status IS NULL
                AND response_ciphertext IS NULL
                AND response_plaintext_sha256 IS NULL
                AND audit_sequence IS NULL
                AND audit_event_id IS NULL
                AND audit_payload_canonical_version IS NULL
                AND audited_payload_sha256 IS NULL
                AND pruned_at_utc IS NOT NULL
                AND pruned_at_utc >= expires_at_utc
                AND quarantine_until_utc IS NOT NULL
                AND quarantine_until_utc >= pruned_at_utc + INTERVAL '1 hour'
                AND quarantine_until_utc <= pruned_at_utc + INTERVAL '365 days'));

ALTER TABLE play_auth.authority_state
    ADD CONSTRAINT authority_state_finite_clock_v004_check
        CHECK (isfinite(clock_high_water_utc) AND isfinite(updated_at_utc));

ALTER TABLE play_auth.audit_log
    ADD CONSTRAINT audit_log_operation_v004_check
        CHECK (operation IN (
            'redeem_invite',
            'consume_exchange',
            'refresh_grant',
            'revoke_grant',
            'revoke_participant',
            'bump_session_version',
            'bump_participant_version',
            'close_session'));

DO $migration$
DECLARE
    constraint_to_drop text;
BEGIN
    IF EXISTS (
        SELECT 1 FROM play_auth.capability_verifiers
        WHERE octet_length(verifier_hmac) <> 32)
       OR EXISTS (
        SELECT 1 FROM play_auth.audit_log
        WHERE octet_length(entry_hmac) <> 32) THEN
        RAISE EXCEPTION 'legacy non-HMAC-SHA-256 rows cannot be upgraded safely'
            USING ERRCODE = '23514';
    END IF;

    FOR constraint_to_drop IN
        SELECT constraint_row.conname
        FROM pg_constraint AS constraint_row
        WHERE constraint_row.conrelid = 'play_auth.capability_verifiers'::regclass
          AND constraint_row.contype = 'c'
          AND pg_get_constraintdef(constraint_row.oid) LIKE '%verifier_hmac%'
    LOOP
        EXECUTE format(
            'ALTER TABLE play_auth.capability_verifiers DROP CONSTRAINT %I',
            constraint_to_drop);
    END LOOP;

    FOR constraint_to_drop IN
        SELECT constraint_row.conname
        FROM pg_constraint AS constraint_row
        WHERE constraint_row.conrelid = 'play_auth.audit_log'::regclass
          AND constraint_row.contype = 'c'
          AND pg_get_constraintdef(constraint_row.oid) LIKE '%entry_hmac%'
    LOOP
        EXECUTE format(
            'ALTER TABLE play_auth.audit_log DROP CONSTRAINT %I',
            constraint_to_drop);
    END LOOP;
END;
$migration$;

ALTER TABLE play_auth.capability_verifiers
    ADD CONSTRAINT capability_verifiers_hmac_sha256_v004_check
        CHECK (octet_length(verifier_hmac) = 32);

ALTER TABLE play_auth.audit_log
    ADD CONSTRAINT audit_log_hmac_sha256_v004_check
        CHECK (octet_length(entry_hmac) = 32);

CREATE INDEX ix_play_auth_idempotency_prune
    ON play_auth.idempotency_receipts(state, expires_at_utc, quarantine_until_utc);

CREATE OR REPLACE FUNCTION play_auth.guard_idempotency_update()
RETURNS trigger
LANGUAGE plpgsql
AS $guard$
BEGIN
    IF NEW.scope_sha256 IS DISTINCT FROM OLD.scope_sha256
       OR NEW.key_sha256 IS DISTINCT FROM OLD.key_sha256
       OR NEW.fingerprint_sha256 IS DISTINCT FROM OLD.fingerprint_sha256
       OR NEW.operation IS DISTINCT FROM OLD.operation
       OR NEW.epoch IS DISTINCT FROM OLD.epoch
       OR NEW.generation IS DISTINCT FROM OLD.generation
       OR NEW.created_at_utc IS DISTINCT FROM OLD.created_at_utc
       OR NEW.expires_at_utc IS DISTINCT FROM OLD.expires_at_utc
       OR (OLD.state = 'completed'
           AND NEW.state = 'pruned'
           AND OLD.expires_at_utc > (
               SELECT GREATEST(clock_timestamp(), clock_high_water_utc)
               FROM play_auth.authority_state
               WHERE singleton = true))
       OR NOT (
           (OLD.state = 'in_progress' AND NEW.state = 'completed')
           OR (OLD.state = 'completed' AND NEW.state = 'pruned')) THEN
        RAISE EXCEPTION 'play_auth idempotency receipt transition is invalid'
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$guard$;

CREATE TRIGGER idempotency_receipt_transition_guard
BEFORE UPDATE ON play_auth.idempotency_receipts
FOR EACH ROW EXECUTE FUNCTION play_auth.guard_idempotency_update();

CREATE OR REPLACE FUNCTION play_auth.guard_idempotency_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $guard$
BEGIN
    IF OLD.state <> 'pruned'
       OR OLD.quarantine_until_utc > (
           SELECT GREATEST(clock_timestamp(), clock_high_water_utc)
           FROM play_auth.authority_state
           WHERE singleton = true) THEN
        RAISE EXCEPTION 'play_auth idempotency receipt quarantine is still active'
            USING ERRCODE = '55000';
    END IF;

    RETURN OLD;
END;
$guard$;

CREATE TRIGGER idempotency_receipt_delete_guard
BEFORE DELETE ON play_auth.idempotency_receipts
FOR EACH ROW EXECUTE FUNCTION play_auth.guard_idempotency_delete();

CREATE OR REPLACE FUNCTION play_auth.guard_checkpoint_publication_update()
RETURNS trigger
LANGUAGE plpgsql
AS $guard$
BEGIN
    IF OLD.state = 'published'
       OR NEW.audit_sequence IS DISTINCT FROM OLD.audit_sequence
       OR NEW.publication_id IS DISTINCT FROM OLD.publication_id
       OR NEW.epoch IS DISTINCT FROM OLD.epoch
       OR NEW.generation IS DISTINCT FROM OLD.generation
       OR NEW.clock_high_water_utc IS DISTINCT FROM OLD.clock_high_water_utc
       OR NEW.audit_head_hmac IS DISTINCT FROM OLD.audit_head_hmac
       OR NEW.external_checkpoint IS DISTINCT FROM OLD.external_checkpoint
       OR NEW.digest_algorithm IS DISTINCT FROM OLD.digest_algorithm
       OR NEW.canonical_version IS DISTINCT FROM OLD.canonical_version
       OR NEW.payload_digest_sha256 IS DISTINCT FROM OLD.payload_digest_sha256
       OR NEW.created_at_utc IS DISTINCT FROM OLD.created_at_utc
       OR NEW.attempt_count < OLD.attempt_count
       OR NEW.fencing_token < OLD.fencing_token
       OR (NEW.state = 'published'
           AND (OLD.lease_owner IS NULL
               OR EXISTS (
                   SELECT 1
                   FROM play_auth.checkpoint_publications AS earlier
                   WHERE earlier.state = 'pending'
                     AND earlier.audit_sequence < OLD.audit_sequence)))
       OR NEW.state NOT IN ('pending', 'published') THEN
        RAISE EXCEPTION 'play_auth checkpoint publication transition is invalid'
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$guard$;

CREATE TRIGGER checkpoint_publication_transition_guard
BEFORE UPDATE ON play_auth.checkpoint_publications
FOR EACH ROW EXECUTE FUNCTION play_auth.guard_checkpoint_publication_update();

CREATE OR REPLACE FUNCTION play_auth.guard_checkpoint_baseline_update()
RETURNS trigger
LANGUAGE plpgsql
AS $guard$
BEGIN
    IF OLD.state = 'verified'
       OR NEW.singleton IS DISTINCT FROM OLD.singleton
       OR NEW.state NOT IN ('quarantined', 'verified') THEN
        RAISE EXCEPTION 'play_auth checkpoint baseline transition is invalid'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.state = 'verified' THEN
        IF NEW.baseline_id IS DISTINCT FROM OLD.baseline_id
           OR NEW.epoch IS DISTINCT FROM OLD.epoch
           OR NEW.generation IS DISTINCT FROM OLD.generation
           OR NEW.clock_high_water_utc IS DISTINCT FROM OLD.clock_high_water_utc
           OR NEW.audit_head_sequence IS DISTINCT FROM OLD.audit_head_sequence
           OR NEW.audit_head_hmac IS DISTINCT FROM OLD.audit_head_hmac
           OR NEW.external_checkpoint IS DISTINCT FROM OLD.external_checkpoint
           OR NEW.digest_algorithm IS DISTINCT FROM OLD.digest_algorithm
           OR NEW.canonical_version IS DISTINCT FROM OLD.canonical_version
           OR NEW.payload_digest_sha256 IS DISTINCT FROM OLD.payload_digest_sha256
           OR NEW.captured_at_utc IS DISTINCT FROM OLD.captured_at_utc
           OR OLD.payload_digest_sha256 IS NULL
           OR NEW.verified_at_utc IS NULL THEN
            RAISE EXCEPTION 'play_auth checkpoint baseline verification is invalid'
                USING ERRCODE = '55000';
        END IF;
    ELSIF OLD.payload_digest_sha256 IS NULL
          AND NEW.payload_digest_sha256 IS NOT NULL THEN
        IF NEW.baseline_id IS DISTINCT FROM OLD.baseline_id
           OR NEW.epoch IS DISTINCT FROM OLD.epoch
           OR NEW.generation IS DISTINCT FROM OLD.generation
           OR NEW.clock_high_water_utc IS DISTINCT FROM OLD.clock_high_water_utc
           OR NEW.audit_head_sequence IS DISTINCT FROM OLD.audit_head_sequence
           OR NEW.audit_head_hmac IS DISTINCT FROM OLD.audit_head_hmac
           OR NEW.external_checkpoint IS DISTINCT FROM OLD.external_checkpoint
           OR NEW.digest_algorithm IS DISTINCT FROM OLD.digest_algorithm
           OR NEW.canonical_version IS DISTINCT FROM OLD.canonical_version
           OR NEW.captured_at_utc IS DISTINCT FROM OLD.captured_at_utc
           OR NEW.verified_at_utc IS NOT NULL THEN
            RAISE EXCEPTION 'play_auth checkpoint baseline digest attachment is invalid'
                USING ERRCODE = '55000';
        END IF;
    ELSIF OLD.audit_head_sequence = 0
          AND NEW.audit_head_sequence = 0
          AND OLD.payload_digest_sha256 IS NULL
          AND NEW.payload_digest_sha256 IS NULL
          AND NEW.verified_at_utc IS NULL THEN
        IF NOT EXISTS (
               SELECT 1
               FROM play_auth.authority_state AS authority
               WHERE authority.singleton = true
                 AND authority.epoch = NEW.epoch
                 AND authority.generation = NEW.generation
                 AND authority.clock_high_water_utc = NEW.clock_high_water_utc
                 AND authority.audit_head_sequence = NEW.audit_head_sequence
                 AND authority.audit_head_hmac = NEW.audit_head_hmac
                 AND authority.external_checkpoint = NEW.external_checkpoint)
           OR EXISTS (SELECT 1 FROM play_auth.audit_log)
           OR EXISTS (SELECT 1 FROM play_auth.checkpoint_publications) THEN
            RAISE EXCEPTION 'play_auth checkpoint baseline refresh is invalid'
                USING ERRCODE = '55000';
        END IF;
    ELSE
        RAISE EXCEPTION 'play_auth checkpoint baseline transition is invalid'
            USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$guard$;

CREATE TRIGGER checkpoint_baseline_transition_guard
BEFORE UPDATE ON play_auth.checkpoint_baseline
FOR EACH ROW EXECUTE FUNCTION play_auth.guard_checkpoint_baseline_update();

REVOKE ALL ON play_auth.checkpoint_publications FROM PUBLIC;
REVOKE ALL ON play_auth.checkpoint_baseline FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA play_auth FROM PUBLIC;
