# Brilliant Directories billing lane

This lane is Hub-owned account/community billing projection only. It opens a configured Brilliant Directories checkout/portal URL and accepts a signed membership snapshot back into Hub.

It does not store Brilliant Directories tenant credentials, API keys, payment methods, raw provider payloads, provider-credit accounting, premium feature flags, render credits, or registry/update-feed truth.

## Supported behavior

- `/account/billing` renders Free and Supporter membership choices.
- `/api/billing` returns the same billing projection with provider capabilities.
- `/account/billing/supporter` and `/api/billing/brilliant-directories/supporter` create a redirect URL for the configured Supporter checkout.
- `/api/billing/brilliant-directories/sync` accepts a signed membership snapshot through `X-Chummer-Billing-Secret`.
- `/api/billing/brilliant-directories/accounts/{userId}` returns Hub's latest normalized snapshot for that user, but only when `X-Chummer-Billing-Secret` matches the configured Hub-side billing webhook secret.

Only these plans are accepted:

- `free`
- `supporter`

Only configured membership statuses are accepted. Defaults are `active`, `inactive`, `pending`, `canceled`, `expired`, and `suspended`; only `active` marks Supporter as active by default.

If Brilliant Directories emits a different lifecycle, plan key, checkout requirement, or ambiguous Supporter state, stop and configure or implement that behavior explicitly before accepting it.

## Configuration

Required:

- `BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL`
- `BRILLIANT_DIRECTORIES_SYNC_SECRET`

Optional:

- `BRILLIANT_DIRECTORIES_FREE_PLAN_URL`
- `BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL`
- `BRILLIANT_DIRECTORIES_CHECKOUT_USER_ID_PARAMETER`
- `BRILLIANT_DIRECTORIES_CHECKOUT_EMAIL_PARAMETER`
- `BRILLIANT_DIRECTORIES_CHECKOUT_PLAN_PARAMETER`
- `BRILLIANT_DIRECTORIES_SUPPORTED_MEMBERSHIP_STATUSES`
- `BRILLIANT_DIRECTORIES_ACTIVE_MEMBERSHIP_STATUSES`
- `CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH`

Nested configuration keys under `BrilliantDirectories:*` are also supported for the same values.

The sync secret is a Hub webhook secret, not a Brilliant Directories tenant credential. Do not commit real values.

## Release gate

The public page may stay online without provider configuration, but that state is only a placeholder handoff:

```text
Supporter checkout is not open yet.
```

A publish that claims live Brilliant Directories billing must run the public billing E2E with:

```bash
CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT=1
```

That gate fails if `/account/billing` still shows the placeholder copy. Do not describe billing as live until `BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL`, `BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL` when available, and `BRILLIANT_DIRECTORIES_SYNC_SECRET` are configured in the public deployment environment.

## Production boundary

Production callers must bind `UserId` from the signed-in Hub account/session or a verified account-linking job. Do not let arbitrary browser form input decide which Hub account receives a membership snapshot.

The current entitlement effect is `supporter_membership_marker`. It intentionally grants no premium features and no render units.
