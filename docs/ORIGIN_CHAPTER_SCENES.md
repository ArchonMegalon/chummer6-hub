# Origin chapter scene bridge

`OriginChapterSceneRequestBridge` is a compose-only adapter to the existing
`origin-dossier-media` governed request lane. It reads the chapter under the
authenticated subject and requires explicit image-processing consent, the exact
reader-accepted prose digest and an excerpt that occurs in those exact bytes.
It rechecks authorization after reading and before returning the request.

It does not mutate the chapter, accept reading for a user, consume quota, choose
a provider, execute a render, persist image bytes or grant publication. The media
payload binds opaque owner, workspace, chapter, canonical chapter digest and
selected prose. Alt text is bounded and must be escaped by clients.

## Private delivery boundary

`AndroidLinkedOriginScenesController` now implements signed-install POST routes
under `/api/v2/android/linked/origin/scenes`: `request`, `read`, and `decide`.
The existing Android v2 proof middleware binds the exact route, body and install.
The request resolves a real Hub user for allowance accounting, composes from
accepted prose, checks the private worker, admits one exact governed request,
then dispatches it. Reconnection reuses that same charged receipt; a concurrent
Teable writer is reread, never blindly charged again. A changed scene request
cannot replace an admitted one, including after a weekly allowance reset.
Read/review identity is derived from the authenticated owner's accepted chapter,
not a phone-supplied asset ID. Authorization is rechecked after I/O.

`OriginSceneMediaClient` uses a private Unix-domain socket, no public TCP route,
no redirects/proxy/cookies, a dedicated file-mounted bearer token and bounded
streamed JSON. Media Factory owns provider execution, image retention and the
no-replay fence. The client never receives provider credentials or download URLs.
Hub does not start a second renderer or store image blobs in its application tree.

Local Docker configuration requires absolute `CHUMMER_ORIGIN_SCENE_MEDIA_SOCKET`
and `CHUMMER_ORIGIN_SCENE_MEDIA_TOKEN_FILE` paths in a private shared mount. The
token must be a separate owner-only file, 32–256 printable ASCII bytes, not an
account credential. Set `CHUMMER_ORIGIN_SCENE_MEDIA_REQUIRED=true` once enabled
and retain it even during outages: account erasure then fails closed if the media
worker is unavailable. Never-enabled installations may omit all three settings.
Partial configuration is not a silent erasure bypass. Account deletion removes
media before other auxiliary stores and retains an owner tombstone against
in-flight completion. Existing primary-store erasure restrictions still apply.

The capability remains disabled by default. This source change does not configure
or deploy the service. Android must still obtain explicit scene consent, call
these routes, review/download and adopt bytes into its existing immutable scene
store for offline reading and EPUB embedding. No automatic illustrated-book or
Play delivery claim follows from server tests.

Focused local verification: affected API build; Origin chapter, Horizon allowance,
scene signed-install and account-erasure tests. These cover accepted/unaccepted
text, literal excerpt, consent, owner/revocation, cold/concurrent admission,
bounded private transport and recovery-only dispatch refusal. No paid provider
calls are used by these tests. Reuse the unchanged Android EPUB checks; device
and complete actual narrative/illustration delivery remain separate work.
