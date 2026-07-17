# Public PWA proof authority

`Chummer.Run.Api/public-pwa-proof-authority.json` is the single reviewed SHA-256
authority for the public Play PWA static proof. It binds the verifier, deterministic
worker generator, and exact required-inventory policy. The policy remains closed at
12 projected assets plus 4 generator dependencies.

The authority file is deliberately not generated from the files it approves at
preflight runtime. A legitimate verifier, generator, or inventory change must update
its corresponding digest in this file in the same review. No verifier or Dockerfile
literal is a second SHA authority.

The host preflight opens and retains no-follow descriptors for the workspace,
`chummer.run-services`, and the exact sibling `chummer-play` root. It independently
enumerates a closed 35-file input set: 23 run-services inputs and the 12 required Play
source assets. Every component is opened relative to the retained root descriptor,
read with a path-specific bound, and checked for stable inode, size, mtime, and ctime.
The aggregate input payload is capped at 64 MiB.

Each input is copied into its own fully sealed Linux memfd. A separate canonical,
duplicate-rejecting manifest binds the exact root paths, root identities, path traces,
file identities, sizes, digests, and inherited descriptor numbers; that manifest is
also sealed. Verifier and generator program bytes are independently copied into
content-addressed, read-only snapshots and fully sealed memfds. Python executes the
verifier from its inherited descriptor. The verifier accepts the sealed manifest only
when its root path matches the invocation, requires the exact duplicated 35-file
policy, reads every input from the declared sealed descriptor, and supplies those
captured bytes to the in-process generator. Repository input pathnames are logical
labels, not byte authorities.

The child runs after descriptor-bound `fchdir` with hard address-space, CPU, output,
open-file, timeout, and receipt-size limits. It writes JSON only to an inherited memfd,
which the parent seals and parses with duplicate rejection. The parent requires the
receipt to echo the exact manifest digest and exact identity/digest rows it issued.
Snapshot paths, substituted file descriptors, a replaced `--source-root`, and a forged
`receipt.json` pathname therefore cannot produce a passing proof.

After the child exits (including timeout and error paths), the parent revalidates the
retained root descriptors, every original absolute path trace, every intermediate
directory trace, every input file identity and digest, the reviewed authority, and the
program snapshots. Whole-root, sibling-root, subdirectory, and file swap-and-restore
attempts change one of those identities and fail closed. A same-UID attacker can still
cause denial of service by perturbing the checkout; it cannot make replacement bytes
pass as the captured proof inputs.

The Docker build has no sibling `chummer-play` checkout and does not claim to execute
the full host-side source proof. Instead, its first stage is a closed validation stage
that receives only the validator, the seven reviewed validator inputs, and the 12
projected assets required to verify the closed mirror policy. The validator parses all
JSON inputs with duplicate rejection and canonical UTF-8 enforcement, checks every
digest binding and the exact ordered 12-asset plus 4-dependency policy, and verifies
the projected bytes. The full sibling-source proof remains a host-preflight
responsibility.

The stage uses the official multi-architecture OCI index
`python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28`.
That index digest was resolved read-only from Docker's authoritative Registry v2 on
2026-07-14. The exact lookup was:

```sh
token="$(curl -fsSL \
  'https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
curl -fsSI \
  -H "Authorization: Bearer ${token}" \
  -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
  'https://registry-1.docker.io/v2/library/python/manifests/3.12-slim'
```

The response's `Docker-Content-Digest` was the pinned digest above. A GET with the
same `Accept` header returned `application/vnd.oci.image.index.v1+json`, 16 manifest
entries, and Linux variants for 386, amd64, arm, arm64, ppc64le, riscv64, and s390x.

The proof stage permits one literal digest-pinned `FROM` alias, one `WORKDIR`, the
exact closed `COPY` sequence, and one JSON exec-form `RUN`. That RUN invokes
`/usr/local/bin/python3 -I -S` with the exact validator and seven-input argument vector.
On success only, `--receipt` atomically publishes canonical, duplicate-free JSON that
records the receipt contract/version, isolated interpreter identity, SHA-256 and stable
filesystem identity of all seven inputs, and the closed 12+4 policy. The build stage
must copy that exact receipt path; a failed validator therefore leaves no source for
the build-stage dependency.

The deploy preflight compares the first stage against that exact instruction whitelist.
It rejects any global instruction before it, any parser directive after the exact
header, heredocs, shell-form or additional `RUN`, `ARG`, `ENV`, `SHELL`, `ONBUILD`,
derived/redefined proof stages, altered copies, JSON indirection, interpreter changes,
and receipt substitution. It parses Docker backslash continuations into logical
instructions before inspecting later stages, so a physical line that resembles the
receipt `COPY` cannot be hidden inside a preceding `RUN`. The only permitted stage
headers are the exact `public-pwa-proof`, .NET SDK `build`, and ASP.NET `final` headers,
in that order, with `final` last and therefore the default target. The exact receipt
copy must occur once as the first build instruction, and the final stage must copy the
exact `/app/publish` artifact from `build` once.

Every leading `COPY --from` option is classified as an allowed earlier stage or as one
of the stage-specific named contexts (`run-services-source`,
`fleet-media-factory-contracts`, or `design-product`). Positional lookalikes, numeric
stage references, external image references, forward references, and named contexts in
the wrong stage fail closed. The resulting graph must be exactly
`final -> build -> public-pwa-proof`; consequently every selectable named or numeric
stage target executes the proof gate. No shell tokenizer or optimistic command-flow
inference is part of this boundary.

The digest pin removes tag drift but does not, by itself, prove a publisher signature,
SBOM, or the platform-specific child-manifest digest selected by BuildKit. The named
build-context bytes also remain checkout inputs rather than signed source provenance.
A Buildx caller can [override stage or image references with colliding named-context
bindings](https://docs.docker.com/reference/cli/docker/buildx/build/#build-context);
the governed build invocation must therefore record its context bindings and forbid
reserved stage, base-image, and frontend names. The deploy preflight parses the
checked-in `chummer-portal` Compose build mapping without interpolation, requires its
exact build root and Dockerfile, and records the exact three accepted non-colliding
bindings. Missing, additional, changed, or reserved bindings fail closed. An arbitrary
direct Buildx CLI invocation remains outside what the Dockerfile or Compose source can
attest and must be constrained separately by CI policy.
A passing stage graph proves proof-gate execution, not complete provenance of every
later runtime-layer byte; downstream mounts, ordinary context copies, and runtime image
content remain build-invocation and source-review responsibilities.
A floating `docker/dockerfile:1.4` frontend and the separate .NET SDK/runtime base
tags remain outside this proof-stage pin and need their own provenance policy.
A clean no-cache Docker build is still required in CI to prove that the selected
platform image contains the expected absolute interpreter and executes the validator;
that build was deliberately outside this audit's allowed command set.

This is a release gate, not a substitute for repository review or source provenance.
A legitimate policy, verifier, generator, authority, or Docker validator change still
requires review in one change set. The host proof establishes exact current-checkout
bytes and the expected sibling topology; it does not attest who authored those bytes,
the cleanliness of unrelated files, or a remote commit identity.
