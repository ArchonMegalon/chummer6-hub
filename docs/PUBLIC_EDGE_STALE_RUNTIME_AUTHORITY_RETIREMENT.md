# Stale public-edge runtime-authority retirement

`active-runtime-authority.json` prevents an ordinary deployment from silently treating a changed
Docker runtime as a new baseline. If that receipt says the prior portal existed but the exact
container was removed outside the deploy transaction, the normal deploy correctly stops with
`active runtime authority lost its portal container`.

`scripts/retire_stale_public_edge_runtime_authority.py` is the one narrow recovery operation for
that state. It is not general authority adoption and it does not weaken the existing deploy journal
or topology-B recovery lanes.

## Admission contract

The operation fails closed unless all of the following are simultaneously true:

- the canonical `active-runtime-authority.json` is a caller-owned, mode-`0600`, link-count-one,
  regular file read through a stable `O_NOFOLLOW` descriptor;
- its exact bytes match an independently supplied lowercase SHA-256;
- its strict v1 contract records one exact prior portal container and, when present, its bound
  InstallLinking readiness receipt still validates under the existing owner-only contract;
- the canonical deploy recovery journal is absent;
- the topology-B public-download active authority is absent;
- the canonical Docker context is `default` at `unix:///var/run/docker.sock` without TLS routing;
- Docker returns zero containers for the recorded container ID, the canonical
  `chummer6-hub` / `chummer-portal` Compose label pair, every project carrying the
  `chummer-portal` service label, and every container claiming published port `8091`; any live,
  stopped, recovery-overlay, malformed, duplicate, or ambiguous result is rejected;
- the shared public-edge mutation lock can be acquired.

The helper first writes a mode-`0600`, link-count-one, no-clobber archive beneath
`public-edge-deploy-receipts/retired-active-runtime-authorities/`. The archive binds the exact prior
authority digest and object, the fixed `recorded_portal_container_missing` reason, and the
canonical Docker absence evidence. It fsyncs the archive and directory, repeats the Docker absence
proof, revalidates the still-open authority descriptor against its pathname, and only then unlinks
the stale active authority and fsyncs its parent. A crash after archive commit is resumable with the
same operation ID and authority digest; archive bytes are never overwritten.

The successful disposition permits the next ordinary governed deploy to observe an unmanaged,
container-absent starting point and establish a fresh active-runtime baseline. The helper does not
start, stop, adopt, rename, or remove a container; alter an image tag; modify an overlay; start a
tunnel; or touch DNS/provider state.

## Exact operator sequence

Run from the reviewed clean, pushed Hub worktree that contains the helper. Record both the source
commit and helper digest in the operator packet. The active-authority digest is an external input;
do not compute it inside the retirement invocation.

```bash
SOURCE=/absolute/path/to/clean/chummer6-hub-worktree
EXPECTED_HEAD=<reviewed-40-hex-pushed-commit>
EXPECTED_HELPER_SHA256=<reviewed-lowercase-helper-sha256>
EXPECTED_ACTIVE_AUTHORITY_SHA256=<reviewed-lowercase-authority-sha256>
OPERATION_ID=missing-portal-YYYYMMDD-hhmmss

test "$(/usr/bin/git -C "$SOURCE" rev-parse --verify HEAD)" = "$EXPECTED_HEAD"
test -z "$(/usr/bin/git -C "$SOURCE" status --porcelain=v1 --untracked-files=all)"
test "$(/usr/bin/git -C "$SOURCE" rev-parse --verify '@{upstream}^{commit}')" = "$EXPECTED_HEAD"
test "$(/usr/bin/sha256sum "$SOURCE/scripts/retire_stale_public_edge_runtime_authority.py" | /usr/bin/awk '{print $1}')" = "$EXPECTED_HELPER_SHA256"

/usr/bin/env -i PATH=/usr/bin:/bin HOME=/nonexistent LANG=C LC_ALL=C \
  /usr/bin/python3 -I \
  "$SOURCE/scripts/retire_stale_public_edge_runtime_authority.py" \
  --operation-id "$OPERATION_ID" \
  --expected-authority-sha256 "$EXPECTED_ACTIVE_AUTHORITY_SHA256"
```

After a `status=pass` receipt, preserve the archive and its printed SHA-256 in the operator packet.
Then run the ordinary `scripts/deploy_public_edge_portal.sh deploy` transaction with all of its
existing commit, verifier, projection, release-channel, boundary, image, and source pins. Do not
start Cloudflare connectors until local `Host: chummer.run` `/api/ready` returns HTTP 200 and the
normal postdeploy gate passes. If the retirement helper reports a journal, topology-B authority,
container, Docker ambiguity, digest drift, unsafe file, or lock owner, stop and use the owning
recovery lane; do not delete the authority by hand.
