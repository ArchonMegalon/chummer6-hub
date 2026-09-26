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

This is not registered as a live endpoint. The authenticated admission/readback
flow and atomic quota decision must be connected before dispatch. Media Factory
owns execution/retention, including the no-replay fence and private provider
receipt. Android must download through a private owner-authorized route and use
its existing immutable scene store for in-app display and EPUB embedding. No
provider URL, API key or raw credential belongs in the phone response.

Focused local verification: affected API build, then `OriginChapter` tests,
including the new bridge's accepted, unaccepted, stale-text, invented-excerpt,
wrong-owner, missing-consent and post-read revocation cases. This does not prove
an automatic illustrated book or a Play-installed app.
