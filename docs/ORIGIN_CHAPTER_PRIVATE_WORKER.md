# Private Origin chapter worker connection

This is a local execution seam, not provider enablement, automatic spending,
publication, a Core rules endpoint or a completed app/provider deployment.
The public signed-install request/read route remains unchanged.

## Listener and credentials

Worker routes are `/api/internal/origin/chapters/*`. They return 404 on the
ordinary Hub listener, even with a correct worker token. The gate runs before
forwarded-header processing and MVC body binding; forwarded port/address headers
cannot select the private listener. The controller also requires the gate's
non-forgeable in-process admission marker.

To enable locally, explicitly configure a **separate** Kestrel listener and:

- `CHUMMER_ORIGIN_CHAPTER_WORKER_PORT`: that listener's actual container-side
  port, e.g. `5089`, never the public/tunnel listener's port;
- `CHUMMER_ORIGIN_CHAPTER_WORKER_TOKEN`: a dedicated random service token
  (32–256 characters) injected by the existing private deployment secret facility;
- `CHUMMER_RUNTIME_STATE_ROOT`: the existing private persistent Hub state root.

Keep the worker port out of Cloudflare ingress. If the host worker needs access,
publish only `127.0.0.1:5089:5089` in the existing local Docker deployment. Do not
publish it on all host interfaces. No Compose service is enabled by this change.
No fallback to the EA webhook token, install grant, browser cookie or provider
credential is accepted. The private port denies non-worker routes. All worker
responses use the existing no-store private-response headers.

## Job flow

1. The signed Android caller creates a consent-bound, source-bound private job.
2. The trusted worker GETs `pending?limit=20` (maximum 20) or `/{workId}`.
   `workId` is an opaque owner/request-scoped reference, not an identity subject
   or install credential. Source facts remain private.
3. After separately obtaining execution/quota admission and preparing the exact
   provider mapping, POST `/{workId}/admit` with `sourceDigest` and
   `executionAdmission` (opaque admission reference, not a secret).
4. The first admitted transition is durably fenced and returns
   `mayStartGeneration: true`. Every repeat of that exact admission returns false;
   another admission or changed source is rejected. A lost first response is
   reconciliation-only, never automatic permission to resend a paid operation.
5. POST `/{workId}/complete` with the exact source/admission, bounded `draftText`
   and `providerReceiptDigest`. Only the admitted worker result can complete it.
   Repeating the identical completion is safe; replacement prose is rejected.
6. The existing Android read route returns `review_required`. The app still owns
   explicit reader adoption; no Core or character mutation occurs here.

Admission does **not** reserve or assert provider credits. Hub does not receive
provider account IDs, login material, browser cookies or execution credentials.
The worker retains those private operational bindings outside public contracts.
Existing jobs without a worker admission remain readable. Already-fenced legacy
jobs cannot be silently adopted into a new worker dispatch.

Account erasure deletes the Hub job/admission and rejects late worker results;
completion never recreates a missing job. External provider and worker-journal
retention/deletion is a separate execution obligation, not claimed by this route.

## Local connector

EA's trusted-local `scripts/origin_chapter_worker.py` consumes this API. It accepts
only an explicit literal loopback HTTP origin, a private token file, an exact
prepared provider mapping and the complete approved source projection. It checks
the server's source, locale, owner-scoped work identity and review/no-mutation
flags before invoking the existing non-replaying chapter writer.

It is deliberately not a public/generic EA tool or a background daemon. Automatic
book creation, book-level mapping, future-chapter preparation and deployment
remain required before claiming unattended app generation. Never spend a new
book credit per chapter implicitly, or attach an old test draft to a new source.

## Verification

Focused `OriginChapterWorkerTests` cover separate actual Kestrel listeners,
private bearer admission, public-port rejection, forwarded-header spoofing,
duplicate/missing credentials, result/source conflicts, cold recovery, immutable
completion and erasure fencing. The normal signed Android request/read tests
still apply. These are local integration checks, not hosted or Play authority.
