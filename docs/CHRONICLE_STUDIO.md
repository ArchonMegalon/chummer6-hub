# Chronicle Studio

Chronicle Studio is a group-owned book workflow at `/groups`. A GM can turn a consented, spoiler-reviewed, redaction-reviewed campaign brief into a versioned Markdown source packet, carry it through an operator-run AIWriteBook session, and import a finished PDF, EPUB, or DOCX with its SHA-256 digest.

The requirement-by-requirement evidence and remaining blockers are recorded in `docs/CHRONICLE_STUDIO_COMPLETION_AUDIT.md`.

Chummer remains the system of record. AIWriteBook never owns group membership, consent, project state, publication approval, rules truth, or artifact provenance. The current provider binding is deliberately non-executable: there is no verified public AIWriteBook API, and unattended browser automation is not authorized.

## Workflow

1. A group owner, manager, admin, or GM creates a draft.
2. While it remains a draft, the GM may revise it. Each save creates a new packet version and SHA-256 history entry.
3. The GM separately confirms external processing, participant consent, redaction review, spoiler review, and rights to use the source.
4. `approve_source` freezes the current reviewed source version.
5. `approve_upload` separately permits packet download and operator upload. It does not upload anything.
6. The operator creates the provider project and returns its opaque reference. `approve_generation` then records the separate generation and credit-spend decision; it does not invoke the provider.
7. `approve_outline` records the GM's reviewed-outline decision.
8. `import_artifact` accepts only HTTPS URLs or traversal-safe `/artifacts/...` paths, a 64-character SHA-256 digest, and `pdf`, `epub`, or `docx`.
9. `approve_publication` records a separate publication decision. It does not publish anything.
10. `approve_external_send` records permission to share the approved artifact. It does not send anything.

The states are `draft`, `source_approved`, `upload_approved`, `generation_approved`, `outline_approved`, `artifact_ready`, `publication_approved`, `external_send_approved`, and `archived`. Out-of-order transitions fail closed. The service accepts legacy `handoff_ready` records only as input to the new explicit generation approval; it never treats them as already generation-approved.

Player accounts only see `player_safe` projects after the GM records publication approval. Importing an artifact is not enough. Their response is an artifact-only projection: it keeps the title, book kind, status, URL, digest, format, and artifact/publication dates while removing the source brief, roster, creator ID, provider reference, packet digest/history, production settings, approval details, and credit estimate. GM-private projects and every source-packet route remain manager-only. Runner handles are snapshotted into the versioned packet only when roster inclusion was selected and participant consent was confirmed.

Revision history stores version, digest, and creation time—not historical packet contents. Only the current, approved version can be downloaded. This prevents an older packet that predates a redaction or consent correction from becoming an export path.

## HTTP surface

- `GET /api/v1/groups/{groupId}/chronicles`
- `POST /api/v1/groups/{groupId}/chronicles`
- `PUT /api/v1/groups/{groupId}/chronicles/{chronicleProjectId}/draft`
- `POST /api/v1/groups/{groupId}/chronicles/{chronicleProjectId}/actions`
- `GET /api/v1/groups/{groupId}/chronicles/{chronicleProjectId}/packet`

The server-rendered equivalents live below `/groups/{groupId}/chronicles`. Android uses native Campaign and Chronicle pages backed by linked-install endpoints; it does not open the PWA or a `WebView`. Windows-compatible clients use the authenticated hosted surface and shared contracts.

## Credit estimate

The draft shows an estimate, not a reservation or provider balance:

- outline: 3 credits per chapter
- writing: 15 Gemini, 20 Grok, or 30 Claude credits per chapter
- cover: 30 credits
- translation: 15 credits per chapter plus 30
- audiobook: estimated characters divided by 25, using six characters per target word

Provider prices may change. The operator must confirm the live provider total before spending credits.

## Provider evidence

EA records the authenticated AppSumo Tier 4 account as an operator lane. A read-only review on 2026-08-11 captured the current 5,000-credit monthly allowance, the credit costs used by the estimate above, and provider-declared PDF/EPUB/DOCX support. The current privacy policy declares that book content is not used for model training, is retained until deletion or account closure, and is deleted or anonymized within 90 days after account deletion. The terms declare user content ownership, human review responsibility, and a prohibition on unauthorized automated access.

The provider declarations remain distinct from runtime proof. The approved synthetic canary subsequently verified the account-specific credit deduction, private-project posture during the run, deletion/inaccessibility after cleanup, operator review, and PDF/EPUB/DOCX round trips. It did not and cannot prove every backend retention or deletion implementation detail beyond the observed UI and deleted-project result. Chummer therefore keeps the provider non-executable and operator-only.

EA now includes a deterministic synthetic canary packet and a strict offline
round-trip verifier; see `EA/docs/AIWRITEBOOK_EXPORT_CANARY.md`. The approval is
digest-bound and separately names project creation, upload, generation, an
18-credit ceiling, export download, and deletion. It never includes publication
or external send. A status-only receipt cannot satisfy governance. The operator
completed the authorized run with synthetic CC0 text. The provider deducted 13
credits from 5,100 to 5,087, all three exports passed structural and
content-marker verification, no publication or external send occurred, and the
synthetic provider project was deleted and confirmed inaccessible.

The durable sanitized round-trip receipt is
`EA/config/provider_evidence/AIWRITEBOOK_EXPORT_ROUNDTRIP.source.json`. EA
governance validates the complete receipt schema and accepts that tracked source
on a fresh checkout. The run was human-operated; unattended browser automation
remains prohibited and the runtime provider binding remains disabled.

The durable sanitized evidence source is `EA/config/provider_evidence/AIWRITEBOOK_ACCOUNT_REVIEW.source.json`. EA regenerates the ignored runtime receipt with `python3 scripts/materialize_aiwritebook_account_review.py`; governance can fall back to the tracked source on a fresh checkout, so the proof does not depend on an untracked local artifact.
