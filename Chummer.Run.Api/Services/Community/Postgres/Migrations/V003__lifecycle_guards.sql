CREATE OR REPLACE FUNCTION play_auth.reject_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $guard$
BEGIN
    RAISE EXCEPTION 'play_auth.audit_log is append-only' USING ERRCODE = '55000';
END;
$guard$;

CREATE TRIGGER audit_log_append_only
BEFORE UPDATE OR DELETE ON play_auth.audit_log
FOR EACH ROW EXECUTE FUNCTION play_auth.reject_audit_mutation();

CREATE OR REPLACE FUNCTION play_auth.validate_audit_append()
RETURNS trigger
LANGUAGE plpgsql
AS $guard$
DECLARE
    current_head play_auth.authority_state%ROWTYPE;
BEGIN
    SELECT * INTO STRICT current_head
    FROM play_auth.authority_state
    WHERE singleton = true
    FOR UPDATE;

    IF NEW.sequence <> current_head.audit_head_sequence + 1
       OR NEW.previous_hmac <> current_head.audit_head_hmac
       OR NEW.epoch <> current_head.epoch
       OR NEW.generation <> current_head.generation THEN
        RAISE EXCEPTION 'play_auth audit head mismatch' USING ERRCODE = '40001';
    END IF;

    RETURN NEW;
END;
$guard$;

CREATE TRIGGER audit_log_head_guard
BEFORE INSERT ON play_auth.audit_log
FOR EACH ROW EXECUTE FUNCTION play_auth.validate_audit_append();

CREATE OR REPLACE FUNCTION play_auth.guard_idempotency_update()
RETURNS trigger
LANGUAGE plpgsql
AS $guard$
BEGIN
    IF OLD.state = 'completed'
       OR NEW.scope_sha256 <> OLD.scope_sha256
       OR NEW.key_sha256 <> OLD.key_sha256
       OR NEW.fingerprint_sha256 <> OLD.fingerprint_sha256
       OR NEW.operation <> OLD.operation
       OR NEW.epoch <> OLD.epoch
       OR NEW.generation <> OLD.generation
       OR NEW.created_at_utc <> OLD.created_at_utc THEN
        RAISE EXCEPTION 'play_auth idempotency receipts are immutable after completion' USING ERRCODE = '55000';
    END IF;

    RETURN NEW;
END;
$guard$;

CREATE TRIGGER idempotency_receipt_transition_guard
BEFORE UPDATE ON play_auth.idempotency_receipts
FOR EACH ROW EXECUTE FUNCTION play_auth.guard_idempotency_update();

CREATE OR REPLACE FUNCTION play_auth.require_capability_verifier()
RETURNS trigger
LANGUAGE plpgsql
AS $guard$
DECLARE
    expected_kind text;
    expected_id text;
BEGIN
    expected_kind := CASE TG_TABLE_NAME
        WHEN 'invites' THEN 'invite'
        WHEN 'exchanges' THEN 'exchange'
        WHEN 'grants' THEN 'grant'
        ELSE NULL
    END;
    expected_id := CASE TG_TABLE_NAME
        WHEN 'invites' THEN to_jsonb(NEW) ->> 'invite_id'
        WHEN 'exchanges' THEN to_jsonb(NEW) ->> 'exchange_id'
        WHEN 'grants' THEN to_jsonb(NEW) ->> 'grant_id'
        ELSE NULL
    END;

    IF expected_kind IS NULL OR NOT EXISTS (
        SELECT 1
        FROM play_auth.capability_verifiers verifier
        WHERE verifier.capability_kind = expected_kind
          AND verifier.capability_id = expected_id) THEN
        RAISE EXCEPTION 'play_auth lifecycle row is missing its capability verifier' USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$guard$;

CREATE CONSTRAINT TRIGGER invite_requires_verifier
AFTER INSERT OR UPDATE ON play_auth.invites
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION play_auth.require_capability_verifier();

CREATE CONSTRAINT TRIGGER exchange_requires_verifier
AFTER INSERT OR UPDATE ON play_auth.exchanges
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION play_auth.require_capability_verifier();

CREATE CONSTRAINT TRIGGER grant_requires_verifier
AFTER INSERT OR UPDATE ON play_auth.grants
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION play_auth.require_capability_verifier();

CREATE OR REPLACE FUNCTION play_auth.require_capability_owner()
RETURNS trigger
LANGUAGE plpgsql
AS $guard$
DECLARE
    owner_exists boolean;
BEGIN
    owner_exists := CASE NEW.capability_kind
        WHEN 'invite' THEN EXISTS (SELECT 1 FROM play_auth.invites WHERE invite_id = NEW.capability_id)
        WHEN 'exchange' THEN EXISTS (SELECT 1 FROM play_auth.exchanges WHERE exchange_id = NEW.capability_id)
        WHEN 'grant' THEN EXISTS (SELECT 1 FROM play_auth.grants WHERE grant_id = NEW.capability_id)
        ELSE false
    END;

    IF NOT owner_exists THEN
        RAISE EXCEPTION 'play_auth capability verifier is orphaned' USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$guard$;

CREATE CONSTRAINT TRIGGER capability_verifier_requires_owner
AFTER INSERT OR UPDATE ON play_auth.capability_verifiers
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION play_auth.require_capability_owner();

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA play_auth FROM PUBLIC;
