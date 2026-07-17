DROP TRIGGER snapshot_head_monotonic_advance
    ON install_linking.snapshot_head;
DROP FUNCTION install_linking.guard_snapshot_head_advance();

DO $drop_checks$
DECLARE
    constraint_name name;
BEGIN
    FOR constraint_name IN
        SELECT conname
        FROM pg_catalog.pg_constraint
        WHERE conrelid IN (
                'install_linking.snapshot_commits'::regclass,
                'install_linking.snapshot_head'::regclass)
          AND contype = 'c'
    LOOP
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.pg_constraint
            WHERE conname = constraint_name
              AND conrelid = 'install_linking.snapshot_commits'::regclass)
        THEN
            EXECUTE format(
                'ALTER TABLE install_linking.snapshot_commits DROP CONSTRAINT %I',
                constraint_name);
        ELSE
            EXECUTE format(
                'ALTER TABLE install_linking.snapshot_head DROP CONSTRAINT %I',
                constraint_name);
        END IF;
    END LOOP;
END;
$drop_checks$;

ALTER TABLE install_linking.snapshot_commits
    RENAME CONSTRAINT snapshot_commits_pkey
    TO pk_snapshot_commits_v2;
ALTER TABLE install_linking.snapshot_commits
    RENAME CONSTRAINT snapshot_commits_commit_id_key
    TO uq_snapshot_commits_commit_id_v2;
ALTER TABLE install_linking.snapshot_head
    RENAME CONSTRAINT snapshot_head_pkey
    TO pk_snapshot_head_v2;
ALTER TABLE install_linking.snapshot_head
    RENAME CONSTRAINT snapshot_head_commit_id_key
    TO uq_snapshot_head_commit_id_v2;
ALTER TABLE install_linking.snapshot_head
    RENAME CONSTRAINT snapshot_head_commit_id_fkey
    TO fk_snapshot_head_commit_v2;

ALTER TABLE install_linking.snapshot_commits
    ADD CONSTRAINT ck_snapshot_commits_contract_v2 CHECK (
        generation > 0
        AND commit_id <> '00000000-0000-0000-0000-000000000000'::uuid
        AND parent_generation >= 0
        AND envelope_version = 2
        AND octet_length(snapshot_sha256) = 32
        AND octet_length(envelope_sha256) = 32
        AND generation = parent_generation + 1
        AND (
            (parent_generation = 0
                AND parent_commit_id IS NULL
                AND parent_envelope_sha256 IS NULL)
            OR
            (parent_generation > 0
                AND parent_commit_id IS NOT NULL
                AND parent_envelope_sha256 IS NOT NULL
                AND octet_length(parent_envelope_sha256) = 32)
        )
    );

ALTER TABLE install_linking.snapshot_head
    ADD CONSTRAINT ck_snapshot_head_contract_v2 CHECK (
        singleton
        AND generation >= 0
        AND (
            (generation = 0
                AND commit_id IS NULL
                AND envelope_version IS NULL
                AND snapshot_sha256 IS NULL
                AND envelope_sha256 IS NULL
                AND protected_envelope IS NULL)
            OR
            (generation > 0
                AND commit_id IS NOT NULL
                AND envelope_version = 2
                AND snapshot_sha256 IS NOT NULL
                AND octet_length(snapshot_sha256) = 32
                AND envelope_sha256 IS NOT NULL
                AND octet_length(envelope_sha256) = 32
                AND protected_envelope IS NOT NULL
                AND octet_length(protected_envelope) BETWEEN 1 AND 67108864)
        )
    );

CREATE FUNCTION install_linking.guard_snapshot_commit_append_v2()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, install_linking
AS $guard$
DECLARE
    current_head install_linking.snapshot_head%ROWTYPE;
BEGIN
    SELECT * INTO current_head
    FROM install_linking.snapshot_head
    WHERE singleton = true
    FOR UPDATE;

    IF NOT FOUND
       OR NEW.generation <> current_head.generation + 1
       OR NEW.parent_generation <> current_head.generation
       OR NEW.parent_commit_id IS DISTINCT FROM current_head.commit_id
       OR NEW.parent_envelope_sha256 IS DISTINCT FROM current_head.envelope_sha256 THEN
        RAISE EXCEPTION 'install-linking authority commit must append to the current head'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$guard$;

CREATE FUNCTION install_linking.guard_snapshot_head_advance_v2()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, install_linking
AS $guard$
DECLARE
    committed install_linking.snapshot_commits%ROWTYPE;
BEGIN
    IF NEW.singleton IS DISTINCT FROM OLD.singleton
       OR NEW.generation <> OLD.generation + 1 THEN
        RAISE EXCEPTION 'install-linking authority head must advance exactly one generation'
            USING ERRCODE = '23514';
    END IF;

    SELECT * INTO committed
    FROM install_linking.snapshot_commits
    WHERE commit_id = NEW.commit_id;

    IF NOT FOUND
       OR committed.generation <> NEW.generation
       OR committed.parent_generation <> OLD.generation
       OR committed.parent_commit_id IS DISTINCT FROM OLD.commit_id
       OR committed.parent_envelope_sha256 IS DISTINCT FROM OLD.envelope_sha256
       OR committed.envelope_version <> NEW.envelope_version
       OR committed.snapshot_sha256 <> NEW.snapshot_sha256
       OR committed.envelope_sha256 <> NEW.envelope_sha256 THEN
        RAISE EXCEPTION 'install-linking authority head does not match its append-only commit'
            USING ERRCODE = '23514';
    END IF;

    IF sha256(NEW.protected_envelope) <> NEW.envelope_sha256 THEN
        RAISE EXCEPTION 'install-linking protected envelope digest does not match'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$guard$;

CREATE TRIGGER snapshot_commit_monotonic_append_v2
BEFORE INSERT ON install_linking.snapshot_commits
FOR EACH ROW
EXECUTE FUNCTION install_linking.guard_snapshot_commit_append_v2();

CREATE TRIGGER snapshot_head_monotonic_advance_v2
BEFORE UPDATE ON install_linking.snapshot_head
FOR EACH ROW
EXECUTE FUNCTION install_linking.guard_snapshot_head_advance_v2();

REVOKE ALL ON ALL TABLES IN SCHEMA install_linking FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA install_linking FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA install_linking FROM PUBLIC;
