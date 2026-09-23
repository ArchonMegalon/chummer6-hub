# Private Hub configuration recovery

This local Linux x64 operator tool stores **actual selected file bytes** in a
dedicated private Teable recovery table. It is not a projection, a whole-Hub
backup, a secret rotation service or a deployment controller. It never starts
Docker, executes recovered configuration, publishes a route or overwrites an
existing restore directory. Existing account/book streams remain separate.

The recovery table must have the `TeableRevisionStore` schema: `revision_key`
(`singleLineText`, UNIQUE and NOT NULL), `stream`/`kind` (`singleLineText`),
`revision` (`number`) and `payload` (`longText`). Use a restricted operator token;
do not grant this table to user-facing Hub runtime credentials or public shares.
The payload is not additionally encrypted. Teable access therefore grants access
to the selected secrets, as well as retained historical versions. There is no
history purge/credential revocation implementation here.

## Capture

Prepare an explicit, frozen directory containing only the reviewed configuration
and secret files needed for this Hub deployment. Mount it read-only for capture;
exclude parallel writers. Do not point this tool at a workspace, `.git`, the EA
secret store, signing material, an entire Docker volume or the original unreadable
account archive. The tool does not scan directories or follow references inside
configuration. Selection is a flat filename allowlist, not a glob.

Directories must be owned by the operator with mode `0700`, and input files must
be owner-only regular files. Symlink ancestry, symlinks, hard links and FIFOs are
rejected. Maximums: 64 files, 1 MiB per file, 8 MiB combined. Deployment names use
ASCII letters, digits, `_` and `-`; filenames may additionally contain `.` but
cannot be `.` or `..`.

Supply an owner-only `0600` options file inside a private `0700` directory:

```json
{
  "origin": "https://app.teable.ai/",
  "tableId": "<private recovery table>",
  "tokenFile": "/private/bootstrap/teable-token",
  "deployment": "fresh-hub",
  "sourceDirectory": "/private/prepared-config",
  "files": ["compose.yml", "hub.env", "identity-admin-key"]
}
```

Using the locally built executable:

```sh
dotnet Chummer.Teable.Recovery/bin/Release/net10.0/Chummer.Teable.Recovery.dll capture /private/capture.json
```

Only operation status and a receipt (deployment, revision, commit, bundle digest,
file count) go to stdout. Neither file contents nor token values are output.
Identical selected bytes reuse the current revision. Concurrent changes reject;
an uncertain write is **not** automatically replayed. Use `inspect` to reconcile
the current remote state after an uncertain capture.

## Restore onto a fresh host

The first Teable login/token, origin, table ID and deployment name must be
recoverable **outside this host and independently of the same Teable base**.
Storing the only bootstrap credential inside its own recovery table is circular.
Obtain a scoped token through the separately authorized account workflow; do not
install EA's broad token in a recovered Hub.

1. Make the trusted local tool/build inputs available on the new Linux x64 host.
2. Put the recovered bootstrap token and private options in owner-only files.
3. Run `inspect` with origin/table/token/deployment options. Retain and review its
   exact receipt; this is not a claim that the deployment is current or healthy.
4. Provide that receipt as `expected`, plus an existing private
   `destinationParent` and a **new** flat `directoryName`, then run `restore`.

```json
{
  "origin": "https://app.teable.ai/",
  "tableId": "<private recovery table>",
  "tokenFile": "/private/bootstrap/teable-token",
  "deployment": "fresh-hub",
  "destinationParent": "/private/recovered",
  "directoryName": "candidate",
  "expected": {
    "deployment": "fresh-hub",
    "revision": 1,
    "commit": "<exact GUID from inspect/capture>",
    "sha256": "<exact bundle digest>",
    "fileCount": 3
  }
}
```

```sh
dotnet Chummer.Teable.Recovery/bin/Release/net10.0/Chummer.Teable.Recovery.dll inspect /private/inspect.json
dotnet Chummer.Teable.Recovery/bin/Release/net10.0/Chummer.Teable.Recovery.dll restore /private/restore.json
```

Restore checks the exact receipt and all member names/digests before writing,
flushes and reads back the files with mode `0600`, then moves the private staging
directory to the new target. An interrupted run may leave a private `.recovery-*`
directory; it never marks it as a complete target or deletes an existing target.
Review such partial directories before removing them. This is not a filesystem
power-loss durability guarantee or an automatic service rollback.

Finally inspect the recovered config, rebind host-specific paths, verify the
actual account/book primary tables and key custody, and test the complete Hub in
isolation before an explicit cutover. Files being restored does **not** prove that
all required configuration was selected, that referenced images are available,
that credentials remain valid, or that the complete Hub is recoverable. Production
migration and historical erasure are still unfinished.
