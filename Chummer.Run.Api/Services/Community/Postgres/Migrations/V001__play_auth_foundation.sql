CREATE SCHEMA IF NOT EXISTS play_auth;
REVOKE ALL ON SCHEMA play_auth FROM PUBLIC;

CREATE TABLE play_auth.authority_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    epoch bigint NOT NULL CHECK (epoch >= 0),
    generation bigint NOT NULL CHECK (generation >= 0),
    clock_high_water_utc timestamptz NOT NULL,
    audit_head_sequence bigint NOT NULL CHECK (audit_head_sequence >= 0),
    audit_head_hmac bytea NOT NULL CHECK (octet_length(audit_head_hmac) = 32),
    audit_hmac_key_id text NOT NULL CHECK (char_length(audit_hmac_key_id) BETWEEN 1 AND 128),
    external_checkpoint bytea NOT NULL CHECK (octet_length(external_checkpoint) <= 4096),
    updated_at_utc timestamptz NOT NULL
);

INSERT INTO play_auth.authority_state (
    singleton,
    epoch,
    generation,
    clock_high_water_utc,
    audit_head_sequence,
    audit_head_hmac,
    audit_hmac_key_id,
    external_checkpoint,
    updated_at_utc)
VALUES (
    true,
    0,
    0,
    TIMESTAMPTZ '1970-01-01 00:00:00+00',
    0,
    decode(repeat('00', 32), 'hex'),
    'unprovisioned',
    ''::bytea,
    TIMESTAMPTZ '1970-01-01 00:00:00+00')
ON CONFLICT (singleton) DO NOTHING;

CREATE TABLE play_auth.capability_verifiers (
    capability_kind text NOT NULL CHECK (capability_kind IN ('invite', 'exchange', 'grant')),
    capability_id text NOT NULL CHECK (char_length(capability_id) BETWEEN 1 AND 128),
    epoch bigint NOT NULL CHECK (epoch > 0),
    generation bigint NOT NULL CHECK (generation > 0),
    key_id text NOT NULL CHECK (char_length(key_id) BETWEEN 1 AND 128),
    verifier_hmac bytea NOT NULL CHECK (octet_length(verifier_hmac) BETWEEN 32 AND 64),
    created_at_utc timestamptz NOT NULL,
    expires_at_utc timestamptz NOT NULL,
    consumed_at_utc timestamptz NULL,
    revoked_at_utc timestamptz NULL,
    PRIMARY KEY (capability_kind, capability_id),
    CHECK (expires_at_utc > created_at_utc),
    CHECK (consumed_at_utc IS NULL OR consumed_at_utc >= created_at_utc),
    CHECK (revoked_at_utc IS NULL OR revoked_at_utc >= created_at_utc)
);

CREATE TABLE play_auth.sessions (
    session_id text PRIMARY KEY CHECK (char_length(session_id) BETWEEN 1 AND 128),
    campaign_id text NOT NULL CHECK (char_length(campaign_id) BETWEEN 1 AND 128),
    run_id text NOT NULL CHECK (char_length(run_id) BETWEEN 1 AND 128),
    group_id text NOT NULL CHECK (char_length(group_id) BETWEEN 1 AND 128),
    status text NOT NULL CHECK (status IN ('active', 'closed', 'revoked')),
    authorization_version bigint NOT NULL CHECK (authorization_version > 0),
    epoch bigint NOT NULL CHECK (epoch > 0),
    generation bigint NOT NULL CHECK (generation > 0),
    created_by_user_id text NOT NULL CHECK (char_length(created_by_user_id) BETWEEN 1 AND 128),
    created_at_utc timestamptz NOT NULL,
    updated_at_utc timestamptz NOT NULL,
    closed_at_utc timestamptz NULL,
    revoked_at_utc timestamptz NULL,
    CHECK (updated_at_utc >= created_at_utc),
    CHECK ((status = 'closed') = (closed_at_utc IS NOT NULL)),
    CHECK ((status = 'revoked') = (revoked_at_utc IS NOT NULL))
);

CREATE TABLE play_auth.participants (
    participant_id text PRIMARY KEY CHECK (char_length(participant_id) BETWEEN 1 AND 128),
    session_id text NOT NULL REFERENCES play_auth.sessions(session_id) ON DELETE RESTRICT,
    user_id text NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    role text NOT NULL CHECK (role IN ('game_master', 'player', 'observer')),
    source_kind text NOT NULL CHECK (source_kind IN ('group_operator', 'crew_assignment', 'accepted_open_run_roster', 'explicit_participant')),
    source_id text NOT NULL CHECK (char_length(source_id) BETWEEN 1 AND 128),
    status text NOT NULL CHECK (status IN ('active', 'revoked')),
    authorization_version bigint NOT NULL CHECK (authorization_version > 0),
    epoch bigint NOT NULL CHECK (epoch > 0),
    generation bigint NOT NULL CHECK (generation > 0),
    added_by_user_id text NOT NULL CHECK (char_length(added_by_user_id) BETWEEN 1 AND 128),
    created_at_utc timestamptz NOT NULL,
    updated_at_utc timestamptz NOT NULL,
    revoked_at_utc timestamptz NULL,
    UNIQUE (session_id, user_id, role),
    UNIQUE (participant_id, session_id),
    CHECK (updated_at_utc >= created_at_utc),
    CHECK ((status = 'revoked') = (revoked_at_utc IS NOT NULL))
);

CREATE TABLE play_auth.invites (
    invite_id text PRIMARY KEY CHECK (char_length(invite_id) BETWEEN 1 AND 128),
    session_id text NOT NULL REFERENCES play_auth.sessions(session_id) ON DELETE RESTRICT,
    participant_id text NOT NULL,
    target_user_id text NOT NULL CHECK (char_length(target_user_id) BETWEEN 1 AND 128),
    requested_role text NOT NULL CHECK (requested_role IN ('game_master', 'player', 'observer')),
    status text NOT NULL CHECK (status IN ('pending', 'consumed', 'revoked', 'expired')),
    session_authorization_version bigint NOT NULL CHECK (session_authorization_version > 0),
    participant_authorization_version bigint NOT NULL CHECK (participant_authorization_version > 0),
    epoch bigint NOT NULL CHECK (epoch > 0),
    generation bigint NOT NULL CHECK (generation > 0),
    created_by_user_id text NOT NULL CHECK (char_length(created_by_user_id) BETWEEN 1 AND 128),
    created_at_utc timestamptz NOT NULL,
    updated_at_utc timestamptz NOT NULL,
    expires_at_utc timestamptz NOT NULL,
    consumed_by_user_id text NULL,
    consumed_at_utc timestamptz NULL,
    revoked_at_utc timestamptz NULL,
    FOREIGN KEY (participant_id, session_id)
        REFERENCES play_auth.participants(participant_id, session_id) ON DELETE RESTRICT,
    CHECK (expires_at_utc > created_at_utc),
    CHECK (updated_at_utc >= created_at_utc),
    CHECK ((status = 'consumed') = (consumed_at_utc IS NOT NULL AND consumed_by_user_id IS NOT NULL)),
    CHECK ((status = 'revoked') = (revoked_at_utc IS NOT NULL))
);

CREATE TABLE play_auth.exchanges (
    exchange_id text PRIMARY KEY CHECK (char_length(exchange_id) BETWEEN 1 AND 128),
    invite_id text NOT NULL UNIQUE REFERENCES play_auth.invites(invite_id) ON DELETE RESTRICT,
    session_id text NOT NULL REFERENCES play_auth.sessions(session_id) ON DELETE RESTRICT,
    participant_id text NOT NULL,
    user_id text NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    role text NOT NULL CHECK (role IN ('game_master', 'player', 'observer')),
    device_thumbprint text NOT NULL CHECK (device_thumbprint ~ '^[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('active', 'consumed', 'revoked', 'expired')),
    session_authorization_version bigint NOT NULL CHECK (session_authorization_version > 0),
    participant_authorization_version bigint NOT NULL CHECK (participant_authorization_version > 0),
    epoch bigint NOT NULL CHECK (epoch > 0),
    generation bigint NOT NULL CHECK (generation > 0),
    created_at_utc timestamptz NOT NULL,
    updated_at_utc timestamptz NOT NULL,
    expires_at_utc timestamptz NOT NULL,
    consumed_at_utc timestamptz NULL,
    revoked_at_utc timestamptz NULL,
    FOREIGN KEY (participant_id, session_id)
        REFERENCES play_auth.participants(participant_id, session_id) ON DELETE RESTRICT,
    CHECK (expires_at_utc > created_at_utc),
    CHECK (updated_at_utc >= created_at_utc),
    CHECK ((status = 'consumed') = (consumed_at_utc IS NOT NULL)),
    CHECK ((status = 'revoked') = (revoked_at_utc IS NOT NULL))
);

CREATE TABLE play_auth.grants (
    grant_id text PRIMARY KEY CHECK (char_length(grant_id) BETWEEN 1 AND 128),
    exchange_id text NOT NULL UNIQUE REFERENCES play_auth.exchanges(exchange_id) ON DELETE RESTRICT,
    session_id text NOT NULL REFERENCES play_auth.sessions(session_id) ON DELETE RESTRICT,
    participant_id text NOT NULL,
    user_id text NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    role text NOT NULL CHECK (role IN ('game_master', 'player', 'observer')),
    device_thumbprint text NOT NULL CHECK (device_thumbprint ~ '^[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('active', 'revoked', 'expired')),
    session_authorization_version bigint NOT NULL CHECK (session_authorization_version > 0),
    participant_authorization_version bigint NOT NULL CHECK (participant_authorization_version > 0),
    secret_generation bigint NOT NULL DEFAULT 1 CHECK (secret_generation > 0),
    epoch bigint NOT NULL CHECK (epoch > 0),
    generation bigint NOT NULL CHECK (generation > 0),
    issued_at_utc timestamptz NOT NULL,
    updated_at_utc timestamptz NOT NULL,
    expires_at_utc timestamptz NOT NULL,
    refresh_until_utc timestamptz NOT NULL,
    revoked_at_utc timestamptz NULL,
    FOREIGN KEY (participant_id, session_id)
        REFERENCES play_auth.participants(participant_id, session_id) ON DELETE RESTRICT,
    CHECK (expires_at_utc > issued_at_utc),
    CHECK (refresh_until_utc >= expires_at_utc),
    CHECK (updated_at_utc >= issued_at_utc),
    CHECK ((status = 'revoked') = (revoked_at_utc IS NOT NULL))
);

CREATE TABLE play_auth.audit_log (
    sequence bigint PRIMARY KEY CHECK (sequence > 0),
    event_id uuid NOT NULL UNIQUE,
    epoch bigint NOT NULL CHECK (epoch > 0),
    generation bigint NOT NULL CHECK (generation > 0),
    operation text NOT NULL CHECK (char_length(operation) BETWEEN 1 AND 64),
    aggregate_kind text NOT NULL CHECK (aggregate_kind IN ('session', 'participant', 'invite', 'exchange', 'grant')),
    aggregate_id text NOT NULL CHECK (char_length(aggregate_id) BETWEEN 1 AND 128),
    actor_digest_sha256 text NOT NULL CHECK (actor_digest_sha256 ~ '^[0-9a-f]{64}$'),
    payload_sha256 bytea NOT NULL CHECK (octet_length(payload_sha256) = 32),
    previous_hmac bytea NOT NULL CHECK (octet_length(previous_hmac) = 32),
    entry_hmac bytea NOT NULL CHECK (octet_length(entry_hmac) BETWEEN 32 AND 64),
    hmac_key_id text NOT NULL CHECK (char_length(hmac_key_id) BETWEEN 1 AND 128),
    occurred_at_utc timestamptz NOT NULL
);

CREATE INDEX ix_play_auth_participants_session_user
    ON play_auth.participants(session_id, user_id);
CREATE INDEX ix_play_auth_invites_session_status
    ON play_auth.invites(session_id, status, expires_at_utc);
CREATE INDEX ix_play_auth_exchanges_session_status
    ON play_auth.exchanges(session_id, status, expires_at_utc);
CREATE INDEX ix_play_auth_grants_session_user_status
    ON play_auth.grants(session_id, user_id, status, expires_at_utc);
CREATE INDEX ix_play_auth_capability_expiry
    ON play_auth.capability_verifiers(expires_at_utc);

REVOKE ALL ON ALL TABLES IN SCHEMA play_auth FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA play_auth FROM PUBLIC;
