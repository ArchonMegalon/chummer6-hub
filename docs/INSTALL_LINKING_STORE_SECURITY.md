# Install-linking durable-store production prerequisites

The install-linking store contains claim codes, callback codes, personalized installer content,
and installation grants. Production uses PostgreSQL as the transactional, cross-host authority and
keeps the protected local store only as a same-generation mirror and import source. PostgreSQL is
managed or externally operated; `docker-compose.public-edge.yml` intentionally does not create an
embedded database.

## Runtime and local-file boundary

- The production file-security contract is Linux x86-64. Store, floor, writer-lock, certificate,
  password, and PostgreSQL credential files are opened without following the leaf link and checked
  through the open descriptor for regular-file type, effective owner, one hard link, bounded size,
  and owner-only mode.
- `CHUMMER_INSTALL_LINKING_STORE_PATH` points beneath the durable `/app/state` volume. `/tmp` is not
  a production store path. The local floor detects plaintext downgrade, replacement of only the
  snapshot, and partial/crash rollback.
- PostgreSQL provides cross-host compare-and-swap authority, but a portal process still holds the
  local writer lease and treats an unexpected compare-and-swap conflict as terminal. Keep exactly
  one portal writer until reload/retry conflict handling is implemented.
- Production readiness fails closed when the PostgreSQL authority is absent, unreachable, invalid,
  behind the protected local floor, or contains an envelope that cannot be unprotected. A locally
  green mirror never substitutes for the authority and no boolean/operator attestation bypasses it.
- Quarantine files contain only bounded metadata (fixed reason, source byte count, SHA-256, and
  timestamp). They never duplicate ciphertext or legacy plaintext.

## Managed PostgreSQL and TLS contract

Provision an external PostgreSQL service with backups and point-in-time recovery. Runtime and
migration use distinct LOGIN roles and distinct passwords. The runtime role must already exist
before `prepare`; the tool creates/migrates the schema and grants the bounded runtime privileges,
but deliberately never creates a LOGIN role.

Each credential file contains exactly one non-empty UTF-8 connection-string line. Inline
connection-string environment values are rejected. Production files must be regular, owner-only,
single-link files owned by `CHUMMER_PORTAL_UID:CHUMMER_PORTAL_GID` (default `1654:1654`). Require
full server identity verification and a certificate that chains to the container system trust store:

```text
Host=db.example.net;Port=5432;Database=chummer;Username=chummer_install_linking_runtime;Password=...;SSL Mode=VerifyFull;Timeout=5;Command Timeout=15;Keepalive=30
```

Use the same TLS policy with the distinct migrator identity. If the provider uses a private CA,
install that CA into the image trust store through the governed image build; never weaken the file
to `SSL Mode=Require` or `Trust Server Certificate=true`.

Configure host paths, not secret contents:

- `CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_CONNECTION_FILE` is mounted only into the portal and
  explicit import job.
- `CHUMMER_INSTALL_LINKING_POSTGRES_MIGRATOR_CONNECTION_FILE` is mounted only into the profile-only
  prepare/validate job.
- Prepare/validate and import use the separate `install-linking-postgres-tool-final` image target.
  The long-running public API image does not contain the migration/import executable.
- Snapshot, envelope, digest, and compare-exchange request byte buffers are cleared after each
  persistence attempt. Some framework-owned managed strings (including Data Protection internals)
  cannot be deterministically cleared before garbage collection, so the portal and both operator
  jobs also drop all Linux capabilities, forbid privilege escalation, and disable core dumps.
- `CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE` names the pre-existing role granted by `prepare`.
- The governed runbook wraps every operator job in a fixed 180-second host-side deadline; the
  migration tool itself does not claim an unbounded process deadline is safe.

The portal and jobs run as the explicit numeric container identity. Prepare all secrets before use:

```sh
sudo chown 1654:1654 \
  /secure/path/data-protection-key-encryption.pfx \
  /secure/path/data-protection-key-encryption.password \
  /secure/path/install-linking-postgres-runtime.connection-string \
  /secure/path/install-linking-postgres-migrator.connection-string
sudo chmod 0400 \
  /secure/path/data-protection-key-encryption.pfx \
  /secure/path/data-protection-key-encryption.password \
  /secure/path/install-linking-postgres-runtime.connection-string \
  /secure/path/install-linking-postgres-migrator.connection-string
```

Use the configured numeric IDs when overridden. Never mount the migrator credential into the
long-running portal or the import job.

## Data Protection custody

ASP.NET Core Data Protection keys must be encrypted with the operator-provided PKCS#12 certificate.
Configure the certificate path and password-file path; a plaintext password environment variable is
rejected. Missing or invalid custody uses an ephemeral provider and keeps readiness failed without
writing a new unprotected production key. Activation requires an RSA private key of at least 2048
bits whose key-usage extension permits encryption (when present), a live protect/unprotect round
trip, and structurally valid certificate-encrypted key XML.

The PostgreSQL rows contain protected envelopes, not a substitute for the matching Data Protection
key ring and certificate. Back up and test-restore the database/PITR stream and encrypted key-ring
custody as separately protected assets. A database restore behind the local protected floor stays
failed closed; restore the matching/newer PITR point or follow a governed recovery procedure. Never
delete the floor or promote the local mirror to make readiness green.

For an existing `chummer-run-api-state` volume created by an older root-running image, migrate its
ownership only while the portal is stopped, then verify it as the runtime identity:

```sh
docker compose -f docker-compose.public-edge.yml stop chummer-portal
docker run --rm --user 0:0 \
  -v chummer6-hub_chummer-run-api-state:/state \
  alpine:3.20 chown -R 1654:1654 /state
docker run --rm --user 1654:1654 \
  -v chummer6-hub_chummer-run-api-state:/state:ro \
  alpine:3.20 test -r /state
```

The volume name follows `COMPOSE_PROJECT_NAME`; adjust it and the numeric IDs to the deployment.
