import logging
import uuid

from decimal import Decimal
from django.conf import settings
from django.db import transaction as db_transaction
from django.utils.timezone import now
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from core.models import Provider, Transaction, TransactionStatus, IPNLog
from .utils import verify_signature, parse_amount, calculate_mm_fee, format_ugx

logger = logging.getLogger("ussd")


class CalloutView(APIView):
    """
    POST /api/ussd/callout/

    Called by Yo! Payments / the USSD aggregator once the customer has
    entered amount + merchant code. See README section 4 for the full flow.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        payload = request.data

        required = ["datetime", "anumbermsisdn", "signature", "amount", "clinic_code"]
        missing = [f for f in required if f not in payload]
        if missing:
            return Response(
                {"validated": False, "message": f"Missing required field(s): {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not verify_signature(payload):
            logger.warning("Signature verification failed for callout payload: %s", payload)
            return Response(
                {"validated": False, "message": "Invalid signature."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            amount = parse_amount(payload["amount"])
        except ValueError:
            return Response({"validated": False, "message": "Invalid amount."}, status=400)

        clinic_code = str(payload["clinic_code"]).strip()
        try:
            provider = Provider.objects.get(merchant_code=clinic_code, is_active=True)
        except Provider.DoesNotExist:
            return Response(
                {"validated": False, "message": "Merchant code not recognised or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )

        mm_fee = calculate_mm_fee(provider.network, provider.merchant_type, amount)
        edoctor_commission = provider.calculate_commission(amount)
        total_fees = mm_fee + edoctor_commission
        total_payable = amount + total_fees

        payment_external_reference = str(uuid.uuid4().int)[:9]

        with db_transaction.atomic():
            txn = Transaction.objects.create(
                payment_external_reference=payment_external_reference,
                provider=provider,
                msisdn=payload["anumbermsisdn"],
                network=provider.network,
                amount=amount,
                mm_fee=mm_fee,
                edoctor_commission=edoctor_commission,
                total_payable=total_payable,
                status=TransactionStatus.PENDING,
                raw_callout_request=payload,
            )

        message = (
            f"Name: {provider.name}\n"
            f"Medicine Amount: {format_ugx(amount)}\n"
            f"Fees: {format_ugx(total_fees)}\n"
            f"Total Amount Payable: {format_ugx(total_payable)}"
        )

        base_url = settings.PUBLIC_BASE_URL.rstrip("/")
        response_body = {
            "validated": True,
            "message": message,
            "ussd_processor_params": {
                "amount_payable": str(int(total_payable)),
                "amount_payable_formatted": format_ugx(total_payable),
                "payment_external_reference": txn.payment_external_reference,
            },
            "success_ipn_url": f"{base_url}/api/ussd/ipn/success/",
            "failure_ipn_url": f"{base_url}/api/ussd/ipn/failure/",
        }
        return Response(response_body, status=status.HTTP_200_OK)


class BaseIPNView(APIView):
    authentication_classes = []
    permission_classes = []
    result_status = None  # overridden by subclasses
    direction = None

    def post(self, request, *args, **kwargs):
        payload = request.data

        provided_secret = request.headers.get("X-IPN-Secret", "")
        if settings.IPN_SHARED_SECRET and provided_secret != settings.IPN_SHARED_SECRET:
            logger.warning("IPN rejected: bad/missing X-IPN-Secret header.")
            return Response({"received": False, "message": "Unauthorized."}, status=401)

        ref = payload.get("payment_external_reference") or payload.get("reference")
        if not ref:
            return Response({"received": False, "message": "payment_external_reference is required."}, status=400)

        with db_transaction.atomic():
            try:
                txn = Transaction.objects.select_for_update().get(payment_external_reference=ref)
            except Transaction.DoesNotExist:
                return Response({"received": False, "message": "Unknown transaction reference."}, status=404)

            txn.status = self.result_status
            txn.raw_ipn_payload = payload
            txn.payment_confirmation_reference = payload.get("confirmation_reference", "")
            if self.result_status == TransactionStatus.SUCCESS:
                txn.settlement_status = "SETTLED"
            txn.save(update_fields=[
                "status", "raw_ipn_payload", "payment_confirmation_reference",
                "settlement_status", "updated_at",
            ])
            IPNLog.objects.create(transaction=txn, direction=self.direction, payload=payload)

        logger.info("Processed %s IPN for %s at %s", self.direction, ref, now())
        return Response({"received": True}, status=200)


class SuccessIPNView(BaseIPNView):
    result_status = TransactionStatus.SUCCESS
    direction = "SUCCESS"


class FailureIPNView(BaseIPNView):
    result_status = TransactionStatus.FAILED
    direction = "FAILURE"