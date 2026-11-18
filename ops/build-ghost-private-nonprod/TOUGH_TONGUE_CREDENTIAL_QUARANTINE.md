# Tough Tongue credential-compromise quarantine

This runbook removes Tough Tongue credentials and opaque provider bindings from
the local Build Ghost AI container while preserving the private lane's
deterministic fallback. It keeps all four provider gates literal `false`, pins
the deliberately unconfigured read-only-contract sentinel, recreates only AI,
and retains the existing rollback image.

This is **local quarantine, not provider-side revocation**. A credential exposed
outside this host remains usable at the provider until the provider revokes it.
The current repository authority and EA live-ops adapter do not authorize or
implement six-account key creation/revocation. Do not claim rotation complete
from this procedure.

## Known clean deployment baseline

The deployed Hub source at the time this runbook was prepared is the clean
worktree
`/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer.run-services`,
HEAD `b7f21f50ddd324648549649753a37e39958555dd`, tree
`b260bccca60ac8095095eab78d2358830e9b5dcd`. It does not contain this quarantine
mode; use it only as the independently verified base for the reviewed patch.

The other clean source authorities are:

| Source | Path | Revision |
| --- | --- | --- |
| Core | `/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer-core-engine` | `c75d68d2233af980dd8b1ef6116dcbdeefcf3c71` |
| Hub Registry | `/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer-hub-registry` | `7b54afec574a9327616c4ad7566da3a7b6b906a5` |
| Media Factory | `/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer-media-factory` | `415c8163d3d90b1211e4014fef332bdec6d75f73` |
| Presentation | `/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer-presentation-1c4922` | `1c492202ac708f302b59f47c2bb1e4c67e352328` |
| UI Kit | `/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer-ui-kit` | `d51ecd99cf72098d4adc8db0192bff7bf9fd8e61` |

Credential authority remains outside Git. Without reading or printing values,
the known local sources are `/docker/EA/.env`,
`/docker/EA/.ea-runtime-secrets/ea_runtime.env`, and
`/docker/EA/.ea-runtime-secrets/ea_runtime.local.env`, plus protected Teable
recovery and the active Docker container configuration. The deployment-time
operator JSON and credential-bearing `runtime.env` were already destroyed; the
retained contract and receipt are secret-free evidence.

## Review and test gate

Deployment is a separate mutation and requires a new independent approval. The
review must bind the exact quarantine commit and tree. From the reviewed clean
quarantine worktree, run:

```sh
bash -n ops/build-ghost-private-nonprod/deploy-ai-with-rollback.sh
python3 -m pytest -q \
  tests/test_build_ghost_private_nonprod_ai_deploy.py \
  tests/test_build_ghost_tough_tongue_runtime_deploy_plumbing.py \
  tests/test_build_ghost_tough_tongue_runtime_config.py \
  tests/test_build_ghost_private_nonprod_compose.py
git status --short
git rev-parse HEAD HEAD^{tree}
```

Do not continue unless the tests pass, the worktree is clean, and the two Git
objects exactly match the independently approved review receipt.

## Read-only live preflight

The following check emits only health and gate posture, never environment
values:

```sh
project=chummer-build-ghost-private-nonprod
cid="$(docker ps \
  --filter "label=com.docker.compose.project=$project" \
  --filter 'label=com.docker.compose.service=chummer-build-ghost-ai' \
  --filter status=running --format '{{.ID}}')"
test -n "$cid"
docker inspect "$cid" | jq -e '
  .[0] as $c
  | $c.State.Health.Status == "healthy"
    and ([
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED=false",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED=false",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED=false",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED=false"
    ] | map(. as $expected | [$c.Config.Env[] | select(. == $expected)] | length == 1) | all)'
```

## Reviewed local quarantine execution

Set the Hub path to the exact independently reviewed clean quarantine worktree.
The remaining sources stay on the deployed clean revisions listed above:

```sh
export CHUMMER_RUN_SERVICES_SOURCE=/absolute/path/to/reviewed-clean-quarantine-worktree
export CHUMMER_RUN_SERVICES_REVISION="$(git -C "$CHUMMER_RUN_SERVICES_SOURCE" rev-parse HEAD)"
export CHUMMER_CORE_ENGINE_SOURCE=/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer-core-engine
export CHUMMER_CORE_ENGINE_REVISION=c75d68d2233af980dd8b1ef6116dcbdeefcf3c71
export CHUMMER_HUB_REGISTRY_SOURCE=/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer-hub-registry
export CHUMMER_HUB_REGISTRY_REVISION=7b54afec574a9327616c4ad7566da3a7b6b906a5
export CHUMMER_MEDIA_FACTORY_SOURCE=/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer-media-factory
export CHUMMER_MEDIA_FACTORY_REVISION=415c8163d3d90b1211e4014fef332bdec6d75f73
export CHUMMER_PRESENTATION_SOURCE=/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer-presentation-1c4922
export CHUMMER_PRESENTATION_REVISION=1c492202ac708f302b59f47c2bb1e4c67e352328
export CHUMMER_UI_KIT_SOURCE=/docker/chummercomplete/.state/build-ghost-presentation-deploy-20260822/chummer-ui-kit
export CHUMMER_UI_KIT_REVISION=d51ecd99cf72098d4adc8db0192bff7bf9fd8e61
unset CHUMMER_BUILD_GHOST_TOUGH_TONGUE_OPERATOR_CONFIG_FILE
unset CHUMMER_BUILD_GHOST_TOUGH_TONGUE_RUNTIME_EVIDENCE_ROOT
export CHUMMER_BUILD_GHOST_TOUGH_TONGUE_QUARANTINE=1
"$CHUMMER_RUN_SERVICES_SOURCE/ops/build-ghost-private-nonprod/deploy-ai-with-rollback.sh"
```

The helper obtains only the two internal service tokens from the running AI. In
quarantine mode it never reads the old provider variables. Before activation it
requires the rendered credential/account/candidate/contract fields to be empty,
the sentinel secret source to be exact, and all gates to remain false. After
activation it requires health, deterministic fallback, public `404`, unchanged
neighbors, empty provider fields, the sentinel mount, removal of the superseded
credential-bearing container metadata, and all gates false.

If activation or a postcheck fails, rollback restores the preserved image but
still recreates it with empty provider fields and the unconfigured sentinel.
A failure before activation leaves the existing container unchanged. The helper
does not delete rollback tags or provider credentials from external authorities.

## Secret-safe postcheck

After a reported pass, use the same `project` lookup and verify only exact empty
fields and literal-false gates:

```sh
cid="$(docker ps \
  --filter 'label=com.docker.compose.project=chummer-build-ghost-private-nonprod' \
  --filter 'label=com.docker.compose.service=chummer-build-ghost-ai' \
  --filter status=running --format '{{.ID}}')"
docker inspect "$cid" | jq -e '
  .[0] as $c
  | [
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID",
      "EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST"
    ] as $empty
  | [
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED=false",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED=false",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED=false",
      "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED=false"
    ] as $false
  | $c.State.Health.Status == "healthy"
    and ($empty | map(. as $name | [$c.Config.Env[] | select(. == ($name + "="))] | length == 1) | all)
    and ($false | map(. as $expected | [$c.Config.Env[] | select(. == $expected)] | length == 1) | all)'
```

## Provider-side rotation boundary

True remediation still requires revoking every exposed key at Tough Tongue and
creating replacements. Stop here unless a new explicit authority covers all six
accounts and an independently reviewed provider workflow proves create,
readback, revoke, and recovery behavior. The existing EA adapter is deliberately
GET-only; do not improvise undocumented `POST` or `DELETE` calls.

After separately authorized replacement credentials have been written directly
to all governed secret authorities without chat/log output, prepare a fresh
complete mode-`0600` operator config and use the existing materializer/deployer
path with quarantine disabled:

```sh
unset CHUMMER_BUILD_GHOST_TOUGH_TONGUE_QUARANTINE
export CHUMMER_BUILD_GHOST_TOUGH_TONGUE_OPERATOR_CONFIG_FILE=/absolute/private/operator-runtime-config.json
export CHUMMER_BUILD_GHOST_TOUGH_TONGUE_RUNTIME_EVIDENCE_ROOT=/absolute/private/build-ghost-runtime-evidence
"$CHUMMER_RUN_SERVICES_SOURCE/ops/build-ghost-private-nonprod/deploy-ai-with-rollback.sh"
```

That path still hard-codes all provider gates false and performs no provider
probe or mutation. A separate fresh EA v2 six-slot GET-only receipt may verify
the replacements after local-ledger preflight, but it is not revocation proof.
