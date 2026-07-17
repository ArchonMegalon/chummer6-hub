CREATE TABLE play_auth.idempotency_receipts (
    scope_sha256 bytea NOT NULL CHECK (octet_length(scope_sha256) = 32),
    key_sha256 bytea NOT NULL CHECK (octet_length(key_sha256) = 32),
    fingerprint_sha256 bytea NOT NULL CHECK (octet_length(fingerprint_sha256) = 32),
    operation text NOT NULL CHECK (char_length(operation) BETWEEN 1 AND 64),
    state text NOT NULL CHECK (state IN ('in_progress', 'completed')),
    epoch bigint NOT NULL CHECK (epoch > 0),
    generation bigint NOT NULL CHECK (generation > 0),
    response_type text NULL CHECK (response_type IS NULL OR char_length(response_type) BETWEEN 1 AND 64),
    response_status integer NULL CHECK (response_status IS NULL OR response_status BETWEEN 100 AND 599),
    response_ciphertext bytea NULL CHECK (response_ciphertext IS NULL OR octet_length(response_ciphertext) BETWEEN 1 AND 131072),
    response_plaintext_sha256 bytea NULL CHECK (response_plaintext_sha256 IS NULL OR octet_length(response_plaintext_sha256) = 32),
    created_at_utc timestamptz NOT NULL,
    completed_at_utc timestamptz NULL,
    expires_at_utc timestamptz NOT NULL,
    PRIMARY KEY (scope_sha256, key_sha256),
    CHECK (expires_at_utc > created_at_utc),
    CHECK (
        (state = 'in_progress'
            AND response_type IS NULL
            AND response_status IS NULL
            AND response_ciphertext IS NULL
            AND response_plaintext_sha256 IS NULL
            AND completed_at_utc IS NULL)
        OR
        (state = 'completed'
            AND response_type IS NOT NULL
            AND response_status IS NOT NULL
            AND response_ciphertext IS NOT NULL
            AND response_plaintext_sha256 IS NOT NULL
            AND completed_at_utc IS NOT NULL))
);

CREATE INDEX ix_play_auth_idempotency_expiry
    ON play_auth.idempotency_receipts(expires_at_utc);

REVOKE ALL ON play_auth.idempotency_receipts FROM PUBLIC;
