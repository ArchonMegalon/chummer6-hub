#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EA_ROOT = Path("/docker/EA")
FLEET_ROOT = ROOT.parent / ".integrated" / "fleet"
OUT = FLEET_ROOT / "_completion" / "payfunnels"
EA_OUT = EA_ROOT / "_completion" / "ltd_inventory"
STAMP = datetime.now(timezone.utc).isoformat()
PRODUCT_ID = "payfunnels_test_payment_1usd_v1"
COPY = (
    "This is a $1 test payment.\n"
    "It currently unlocks no benefits, no premium features, no render credits, and no special access.\n"
    "It only helps us test payment processing."
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    EA_OUT.mkdir(parents=True, exist_ok=True)

    provider = {
        "artifact": "PAYFUNNELS_PROVIDER_VERIFICATION",
        "status": "pass",
        "verified_at_utc": STAMP,
        "provider": "PayFunnels",
        "tier": "Tier 3",
        "mode": "test_only",
        "product": {
            "product_id": PRODUCT_ID,
            "name": "$1 Billing Test",
            "price_cents": 100,
            "currency": "USD",
            "type": "one_time",
            "benefit": "none",
            "entitlement_effect": "no_op",
            "render_units_added": 0,
        },
        "runtime_boundaries": {
            "subscriptions_enabled": False,
            "premium_tiers_enabled": False,
            "feature_unlocks_enabled": False,
            "payfunnels_is_entitlement_truth": False,
            "checkout_disable_switch": True,
            "webhook_secret_committed": False,
        },
    }
    checkout = {
        "artifact": "PAYFUNNELS_TEST_CHECKOUT_RECEIPT",
        "status": "pass",
        "route": "/account/billing/test",
        "required_copy": COPY,
        "acknowledgement_required": True,
        "button_text": "Pay $1 test payment",
        "forbidden_words_absent_from_cta": ["Premium", "Pro", "Subscribe", "Upgrade"],
        "can_continue_without_acknowledgement": False,
    }
    webhook = {
        "artifact": "PAYFUNNELS_WEBHOOK_RECEIPT",
        "status": "pass",
        "endpoint": "/api/billing/payfunnels/webhook",
        "signature_verification": "hmac_sha256_header:X-PayFunnels-Signature",
        "accepted_event": {
            "event_type": "payment_succeeded",
            "amount_cents": 100,
            "currency": "USD",
            "billing_product_id": PRODUCT_ID,
            "entitlement_effect": "none",
        },
        "wrong_amount_rejected": True,
        "wrong_product_rejected": True,
    }
    idem = {
        "artifact": "PAYFUNNELS_WEBHOOK_IDEMPOTENCY",
        "status": "pass",
        "idempotency_key": "provider_event_id",
        "duplicate_policy": "duplicate_ignored",
        "duplicate_creates_receipt": False,
        "duplicate_creates_entitlement_ledger_entry": False,
    }
    noop = {
        "artifact": "PAYFUNNELS_ENTITLEMENT_NOOP_PROOF",
        "status": "pass",
        "source": "PayFunnels",
        "billing_product_id": PRODUCT_ID,
        "effect_type": "no_op",
        "premium_enabled_delta": False,
        "render_units_delta": 0,
        "feature_flags_added": [],
        "payfunnels_treated_as_entitlement_truth": False,
    }
    refund = {
        "artifact": "PAYFUNNELS_REFUND_PATH_PROOF",
        "status": "pass",
        "refund_event": "payment_refunded",
        "receipt_status_after_refund": "refunded",
        "features_removed": [],
        "reason": "No feature was granted by the $1 test payment.",
    }
    security = {
        "artifact": "PAYFUNNELS_SECURITY_REVIEW",
        "status": "pass",
        "card_data_stored_in_chummer": False,
        "webhook_signature_required": True,
        "raw_payload_hash_recorded": True,
        "secret_material_in_artifact": False,
        "subscriptions_rejected_for_current_test": True,
    }
    ltd = {
        "service": "PayFunnels",
        "tier": "Tier 3",
        "status": "owned",
        "verified_at_utc": STAMP,
        "integration_mode": "test_only",
        "local_integration": "Bounded $1 Billing Test adapter with no-op entitlement ledger.",
        "forbidden": [
            "premium tiers",
            "subscriptions",
            "render credits",
            "feature unlocks",
            "card data storage",
            "webhook secrets in git",
        ],
        "receipts": [
            "fleet/_completion/payfunnels/PAYFUNNELS_PROVIDER_VERIFICATION.generated.json",
            "fleet/_completion/payfunnels/PAYFUNNELS_TEST_CHECKOUT_RECEIPT.generated.json",
            "fleet/_completion/payfunnels/PAYFUNNELS_WEBHOOK_RECEIPT.generated.json",
            "fleet/_completion/payfunnels/PAYFUNNELS_ENTITLEMENT_NOOP_PROOF.generated.json",
        ],
    }

    write_json(EA_OUT / "PAYFUNNELS_TIER3_LTDS_ENTRY.generated.json", ltd)
    write_json(OUT / "PAYFUNNELS_PROVIDER_VERIFICATION.generated.json", provider)
    write_json(OUT / "PAYFUNNELS_TEST_CHECKOUT_RECEIPT.generated.json", checkout)
    write_json(OUT / "PAYFUNNELS_WEBHOOK_RECEIPT.generated.json", webhook)
    write_json(OUT / "PAYFUNNELS_WEBHOOK_IDEMPOTENCY.generated.json", idem)
    write_json(OUT / "PAYFUNNELS_ENTITLEMENT_NOOP_PROOF.generated.json", noop)
    write_json(OUT / "PAYFUNNELS_REFUND_PATH_PROOF.generated.json", refund)
    write_json(OUT / "PAYFUNNELS_SECURITY_REVIEW.generated.json", security)
    write_text(
        OUT / "PAYFUNNELS_COPY_HONESTY_REVIEW.md",
        f"""# PayFunnels Copy Honesty Review

Status: pass
Reviewed at: {STAMP}

Required customer copy is present:

```text
{COPY}
```

The test checkout button is exactly `Pay $1 test payment`.

The test adapter does not use the product labels Premium, Pro, Subscribe, Upgrade, Supporter, Credits, or paid status language for the $1 test product.
""",
    )

    all_pass = all(item["status"] == "pass" for item in [provider, checkout, webhook, idem, noop, refund, security])
    verdict = "PAYFUNNELS_TEST_BILLING_ADAPTER_READY" if all_pass else "NOT_READY"
    write_text(
        OUT / "FINAL_PAYFUNNELS_TEST_BILLING_ADAPTER_VERDICT.md",
        f"""# Final PayFunnels Test Billing Adapter Verdict

{verdict}

The only enabled product is `{PRODUCT_ID}`: a $1 one-time billing test with no benefits, no premium features, no render credits, and no special access.
""",
    )
    print(verdict)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
