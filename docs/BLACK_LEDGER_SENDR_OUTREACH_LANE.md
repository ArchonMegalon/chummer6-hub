# Black Ledger Sendr Outreach Lane

Sendr Tier 4 is the governed outbound-growth lane for Black Ledger and Chummer relationship building. It is a distribution and relationship tool, not a source of truth.

## Role

Sendr may help with:

- Sponsor outreach.
- Guest and interview outreach.
- Creator and GM community collaboration outreach.
- Newsletter and episode launch outreach to lawful warm lists.
- Convention, event, and partner follow-up.
- Pilot-user recruitment and warm reactivation.
- Personalized Black Ledger landing pages.
- Personalized video or audio introductions.

Sendr must not own:

- Chummer rules truth.
- Black Ledger editorial truth.
- Sourcebook interpretation.
- Release, support, or moderation truth.
- Sponsor contract truth.
- Private campaign material.
- Memorial or private family material.
- Automatic publishing.
- Automatic commitments.

## Flow

```text
Black Ledger source packet
-> Sendr campaign draft
-> human/legal/brand review
-> Sendr sends approved outreach
-> replies and engagement return to EA / Black Ledger Signal Inbox
-> human review
-> sponsor, guest, creator, draft-reply, evidence, suppression, or commitment candidate
```

No Sendr event may directly create a commitment, booking, sponsor deal, public announcement, publication, or auto-reply.

## Campaign Packets

The canonical packet contract is `black_ledger.sendr_campaign_packet.v1`. Build and verify it with:

```bash
python3 scripts/build_black_ledger_sendr_campaign_packet.py \
  --type SPONSOR_OUTREACH \
  --packet black-ledger-sponsor-pilot-001 \
  --source-note "Approved public media-kit and pilot wording have been reviewed."

python3 scripts/verify_black_ledger_sendr_campaign_packet.py \
  --packet .codex-studio/published/black_ledger_sendr_campaign_packet.generated.json
```

Allowed campaign types:

- `SPONSOR_OUTREACH`
- `GUEST_INVITE`
- `CREATOR_COLLAB`
- `EPISODE_LAUNCH`
- `CHUMMER_ACADEMY_OUTREACH`

Every recipient row must carry:

- `recipient_basis`
- `source_url_or_source_note`
- `jurisdiction`
- `allowed_channel`
- `suppression_status`
- `last_verified_at`

Forbidden recipient bases include private scraped profiles, private Discord member exports, raw inbox data, purchased personal lists without lawful basis, and minors.

## Defaults

These remain disabled by default:

```env
BLACK_LEDGER_SENDR_ENABLED=0
BLACK_LEDGER_SENDR_API_ENABLED=0
BLACK_LEDGER_SENDR_WEBHOOKS_ENABLED=0
BLACK_LEDGER_SENDR_WHATSAPP_ENABLED=0
BLACK_LEDGER_SENDR_DIRECT_SEND_ENABLED=0
BLACK_LEDGER_SENDR_AUTO_REPLY_ENABLED=0
```

Runtime secrets stay local in `.env` only. Do not commit populated `SENDR_API_TOKEN`, `SENDR_WEBHOOK_SECRET`, workspace IDs, passwords, or raw contact exports.

## Hard Compliance Boundary

Allowed lead bases:

- Public business contact.
- Public creator contact.
- Prior relationship.
- Event attendee where outreach is allowed.
- Opt-in newsletter or contact list.
- Manual partner shortlist.
- Inbound inquiry.
- Explicit introduction.

Forbidden:

- Scraped private contacts.
- Private Discord member exports.
- Raw EA inbox data.
- Private campaign data.
- Sourcebook-piracy-adjacent targeting.
- Outreach to minors.
- Misleading audience, sponsor, or endorsement claims.
- Platform-rule bypass.

## Integration Modes

Mode 1 is manual-first: create the Sendr campaign in the provider UI from an approved packet, then store the packet and receipts in this repo. Use this for the first sponsor, guest, and Chummer Academy pilots.

Mode 2 is semi-automated: EA materializes reviewed packets and sanitized contact exports, the operator imports them into Sendr, and EA stores contact hashes, message/page/video hashes, approval receipts, and engagement receipts.

Mode 3 is API/webhook integration. It stays disabled until Mode 1 and Mode 2 receipts prove clean suppression, recipient basis, copy review, preview review, and human approval. Direct send, WhatsApp, and auto-reply remain disabled even when API access exists.

Planned API/webhook scope, once governance receipts are green:

- Campaign creation.
- Contact enrollment.
- Event ingestion.
- Reply ingestion.
- Unsubscribe and suppression sync.
- Receipt generation.

## Copy Rules

Use:

- "I am building a small editorial/newsroom project around Chummer and Shadowrun tooling."
- "I thought your audience might care because ..."
- "I recorded a short personalized note here."
- "Would it be worth a 15-minute fit call?"
- "No pressure - if this is not relevant, I will not follow up."

Avoid:

- "official Shadowrun"
- "guaranteed reach"
- "massive audience"
- "sponsor now before it is too late"
- "we already selected you"
- "you need to reply today"
- "automated personalized surveillance"

Sponsor-safe wording:

- "We are testing sponsor fit for a pilot run."
- "Audience and distribution claims are limited to what we can currently prove."

Guest-safe wording:

- "This is an invitation, not an assumption that you are participating."
- "Recording and publication would only happen after explicit approval."

## Data Retention

Store in EA / Black Ledger:

- `contact_hash`
- `source_note`
- `recipient_basis`
- `campaign_membership`
- `send_approval`
- `reply_event`
- `suppression_status`

Do not store raw Sendr payloads, raw reply bodies, raw emails, raw inbox data, private chats, sourcebook PDFs, copied rulebook prose, private campaign data, unpublished sponsor terms, pricing negotiations, or unreviewed claims.

Suppression is fail-closed. A recipient with `suppression_status` of `pending_review` or `suppressed` is not setup-ready. `allowed_channel=whatsapp` is rejected while WhatsApp is disabled.

## Related Tools

- `Subscribr`: writes approved script and episode assets. Sendr distributes approved outreach only.
- `Poppy` and `Syllabbles`: draft variants only. No direct send.
- `Teable`: shows campaign status and reply-review queues. It is not the source of truth.
- `Emailit`: owned transactional and review notifications only; do not mirror Sendr campaign sends unless intentionally separate.
- `ProductLift` and `MetaSurvey`: structured feedback after approved outreach.
- `FlipLink`: approved media-kit or sponsor-deck hosting when controlled access is needed.

## First Pilots

Start with the sponsor pilot:

- Audience: 50 public B2B TTRPG-adjacent tool, accessory, software, publisher, event, or AI-workflow contacts.
- Goal: 3-5 sponsor conversations.
- Channels: email first, LinkedIn only for manually verified contacts, WhatsApp disabled.
- Asset: personalized page, 30-45 second video, approved media-kit link, short episode concept.
- CTA: "Worth a 15-minute sponsor fit call?"
- Required proof: recipient basis, media-kit hash, pilot audience wording, no fake audience numbers, suppression checked.

Then run guest/interview outreach and Chummer Academy cross-promo only after the sponsor packet, preview, reply queue, and suppression sync prove clean.

## Receipts

Materialize a dry-run campaign receipt:

```bash
python3 scripts/materialize_sendr_campaign_receipt.py \
  --packet .codex-studio/published/black_ledger_sendr_campaign_packet.generated.json \
  --dry-run
```

Materialize and verify a sanitized engagement batch:

```bash
python3 scripts/materialize_sendr_engagement_batch_receipt.py \
  --campaign-id sendr-campaign-001 \
  --campaign-type SPONSOR_OUTREACH \
  --event-batch batch-001 \
  --events .codex-studio/published/sendr-events.sanitized.json \
  --dry-run

python3 scripts/verify_sendr_suppression_sync.py \
  --batch .codex-studio/published/black_ledger_sendr_engagement_batch-001.generated.json
```

Materialize a single sanitized reply review receipt:

```bash
python3 scripts/materialize_sendr_reply_receipt.py \
  --campaign-id sendr-campaign-001 \
  --campaign-type SPONSOR_OUTREACH \
  --event-batch reply-batch-001 \
  --contact-hash <contact-hash> \
  --occurred-at 2026-06-30T12:00:00Z \
  --preview "Interested, please send details." \
  --dry-run
```

Engagement receipts store contact hashes and sanitized previews only. Raw reply bodies, raw Sendr payloads, raw emails, raw inbox data, private chats, sourcebook PDFs, and unreviewed claims are forbidden.

## Pilot Gates

Before more than 50 contacts:

- One campaign packet is approved.
- One Sendr preview is reviewed.
- All contacts have lawful basis.
- Suppression check passes fail-closed.
- Message, page, and video hashes are recorded.
- Operator approval is recorded.
- First 10 sends are manually inspected.

Before more than 250 contacts:

- Bounce rate is acceptable.
- Negative reply rate is acceptable.
- Unsubscribe path is verified.
- Reply triage works.
- Suppression sync works.
- No misleading-claim complaints exist.

## Live Smoke Gate

```bash
python3 scripts/build_black_ledger_sendr_campaign_packet.py \
  --type SPONSOR_OUTREACH \
  --packet black-ledger-sponsor-pilot-001

python3 scripts/verify_black_ledger_sendr_campaign_packet.py \
  --packet .codex-studio/published/black_ledger_sendr_campaign_packet.generated.json

python3 scripts/materialize_sendr_campaign_receipt.py \
  --packet .codex-studio/published/black_ledger_sendr_campaign_packet.generated.json \
  --dry-run

python3 -m pytest \
  tests/test_black_ledger_sendr_campaign_packet.py \
  tests/test_sendr_outreach_policy.py \
  tests/test_sendr_receipts.py \
  tests/test_sendr_engagement_receipts.py -q
```
