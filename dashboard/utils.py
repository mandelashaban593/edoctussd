import hashlib
import hmac
from decimal import Decimal, InvalidOperation

from django.conf import settings

from dashboard.models import FeeRule


def build_signature_base_string(payload: dict) -> str:
    """
    Concatenation used to verify the inbound signature.
    Adjust field order to match exactly what Yo! Payments (or your aggregator)
    signs on their side - this is the #1 source of signature mismatches.
    """
    return "{datetime}{anumbermsisdn}{amount}{clinic_code}".format(
        datetime=payload.get("datetime", ""),
        anumbermsisdn=payload.get("anumbermsisdn", ""),
        amount=payload.get("amount", ""),
        clinic_code=payload.get("clinic_code", ""),
    )


def verify_signature(payload: dict) -> bool:
    provided = payload.get("signature", "")
    base_string = build_signature_base_string(payload)
    expected = hmac.new(
        key=settings.USSD_SHARED_SECRET.encode("utf-8"),
        msg=base_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, provided)


def parse_amount(raw_amount) -> Decimal:
    try:
        return Decimal(str(raw_amount))
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid amount")


def calculate_mm_fee(network: str, merchant_type: str, amount: Decimal) -> Decimal:
    """Look up the matching FeeRule band and compute the mobile-money charge."""
    rule = (
        FeeRule.objects.filter(network=network, is_active=True)
        .order_by("min_amount")
    )
    for r in rule:
        if r.matches(network, merchant_type, amount):
            return r.compute_fee(amount)
    return Decimal("0.00")


def format_ugx(amount: Decimal) -> str:
    return f"UGX {amount:,.0f}"