CREATE SCHEMA IF NOT EXISTS install_linking;
REVOKE ALL ON SCHEMA install_linking FROM PUBLIC;

CREATE TABLE install_linking.snapshot_commits (
    generation bigint PRIMARY KEY CHECK (generation > 0),
    commit_id uuid NOT NULL UNIQUE
        CHECK (commit_id <> '00000000-0000-0000-0000-000000000000'::uuid),
    parent_generation bigint NOT NULL CHECK (parent_generation >= 0),
    parent_commit_id uuid NULL,
    parent_envelope_sha256 bytea NULL
        CHECK (parent_envelope_sha256 IS NULL OR octet_length(parent_envelope_sha256) = 32),
    envelope_version integer NOT NULL CHECK (envelope_version = 2),
    snapshot_sha256 bytea NOT NULL CHECK (octet_length(snapshot_sha256) = 32),
    envelope_sha256 bytea NOT NULL CHECK (octet_length(envelope_sha256) = 32),
    committed_at_utc timestamptz NOT NULL,
    CHECK (generation = parent_generation + 1),
    CHECK (
        (parent_generation = 0
            AND parent_commit_id IS NULL
            AND parent_envelope_sha256 IS NULL)
        OR
        (parent_generation > 0
            AND parent_commit_id IS NOT NULL
            AND parent_envelope_sha256 IS NOT NULL))
);

CREATE TABLE install_linking.snapshot_head (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    generation bigint NOT NULL CHECK (generation >= 0),
    commit_id uuid NULL UNIQUE
        REFERENCES install_linking.snapshot_commits(commit_id) ON DELETE RESTRICT,
    envelope_version integer NULL CHECK (envelope_version IS NULL OR envelope_version = 2),
    snapshot_sha256 bytea NULL
        CHECK (snapshot_sha256 IS NULL OR octet_length(snapshot_sha256) = 32),
    envelope_sha256 bytea NULL
        CHECK (envelope_sha256 IS NULL OR octet_length(envelope_sha256) = 32),
    protected_envelope bytea NULL
        CHECK (protected_envelope IS NULL OR octet_length(protected_envelope) BETWEEN 1 AND 67108864),
    updated_at_utc timestamptz NOT NULL,
    CHECK (
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
            AND envelope_sha256 IS NOT NULL
            AND protected_envelope IS NOT NULL))
);

INSERT INTO install_linking.snapshot_head(
    singleton,
    generation,
    commit_id,
    envelope_version,
    snapshot_sha256,
    envelope_sha256,
    protected_envelope,
    updated_at_utc)
VALUES (
    true,
    0,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    TIMESTAMPTZ '1970-01-01 00:00:00+00')
ON CONFLICT (singleton) DO NOTHING;

CREATE FUNCTION install_linking.guard_snapshot_head_advance()
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

CREATE TRIGGER snapshot_head_monotonic_advance
BEFORE UPDATE ON install_linking.snapshot_head
FOR EACH ROW
EXECUTE FUNCTION install_linking.guard_snapshot_head_advance();

REVOKE ALL ON ALL TABLES IN SCHEMA install_linking FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA install_linking FROM PUBLIC;
REVOKE ALL ON FUNCTION install_linking.guard_snapshot_head_advance() FROM PUBLIC;
