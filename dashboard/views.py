import csv
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db.models import Sum, Count, Q
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, TemplateView, CreateView, UpdateView

from dashboard.models import Provider, Transaction, TransactionStatus
from .filters import TransactionFilter, ProviderFilter



import logging
import uuid

from decimal import Decimal
from django.conf import settings
from django.db import transaction as db_transaction
from django.utils.timezone import now
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from dashboard.models import IPNLog
from dashboard.utils import verify_signature, parse_amount, calculate_mm_fee, format_ugx

logger = logging.getLogger("dashboard")


class DashboardLoginView(LoginView):
    template_name = "dashboard/login.html"


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only staff (superuser OR member of 'Admin' group) may access the dashboard."""

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.groups.filter(name="Admin").exists()


class RoleScopedQuerysetMixin:
    """
    Superusers see everything.
    Admin-group users only see providers they manage (and transactions under those providers).
    """

    def scoped_providers(self):
        user = self.request.user
        if user.is_superuser:
            return Provider.objects.all()
        return Provider.objects.filter(managed_by=user)

    def scoped_transactions(self):
        user = self.request.user
        if user.is_superuser:
            return Transaction.objects.select_related("provider")
        return Transaction.objects.select_related("provider").filter(provider__managed_by=user)


class DashboardHomeView(StaffRequiredMixin, RoleScopedQuerysetMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        txns = self.scoped_transactions()
        today = timezone.localdate()

        successful = txns.filter(status=TransactionStatus.SUCCESS)

        ctx["kpi"] = {
            "total_transactions": txns.count(),
            "successful_transactions": successful.count(),
            "pending_transactions": txns.filter(status=TransactionStatus.PENDING).count(),
            "failed_transactions": txns.filter(status=TransactionStatus.FAILED).count(),
            "gross_volume": successful.aggregate(v=Sum("amount"))["v"] or Decimal("0"),
            "mm_fees": successful.aggregate(v=Sum("mm_fee"))["v"] or Decimal("0"),
            "edoctor_commission": successful.aggregate(v=Sum("edoctor_commission"))["v"] or Decimal("0"),
            "total_collected": successful.aggregate(v=Sum("total_payable"))["v"] or Decimal("0"),
            "today_transactions": txns.filter(created_at__date=today).count(),
            "active_providers": self.scoped_providers().filter(is_active=True).count(),
        }

        ctx["by_network"] = list(
            successful.values("network").annotate(count=Count("id"), volume=Sum("total_payable"))
        )
        ctx["by_provider"] = list(
            successful.values("provider__name").annotate(count=Count("id"), volume=Sum("total_payable"))
            .order_by("-volume")[:8]
        )
        ctx["recent_transactions"] = txns.order_by("-created_at")[:10]
        return ctx


class TransactionListView(StaffRequiredMixin, RoleScopedQuerysetMixin, ListView):
    template_name = "dashboard/transaction_list.html"
    context_object_name = "transactions"
    paginate_by = 25

    def get_queryset(self):
        qs = self.scoped_transactions().order_by("-created_at")
        self.filterset = TransactionFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter"] = self.filterset
        totals = self.filterset.qs.aggregate(
            total_amount=Sum("amount"), total_fees=Sum("mm_fee"), total_commission=Sum("edoctor_commission"),
            total_payable=Sum("total_payable"),
        )
        ctx["totals"] = totals
        return ctx


class TransactionExportCSVView(StaffRequiredMixin, RoleScopedQuerysetMixin, ListView):
    """Reconciliation-ready CSV export honouring the same filters as the list view."""

    def get(self, request, *args, **kwargs):
        qs = self.scoped_transactions().order_by("-created_at")
        filterset = TransactionFilter(request.GET, queryset=qs)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="edoctor_transactions.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Reference ID", "External Reference", "Provider", "Merchant Code", "Category",
            "Amount", "MM Fee", "eDoctor Commission", "Total Payable", "Network",
            "MSISDN", "Status", "Settlement Status", "Confirmation Reference", "Created At",
        ])
        for t in filterset.qs.select_related("provider"):
            writer.writerow([
                t.reference_id, t.payment_external_reference, t.provider.name, t.provider.merchant_code,
                t.provider.category, t.amount, t.mm_fee, t.edoctor_commission, t.total_payable,
                t.network, t.msisdn, t.status, t.settlement_status,
                t.payment_confirmation_reference or "", t.created_at.isoformat(),
            ])
        return response


class ProviderListView(StaffRequiredMixin, RoleScopedQuerysetMixin, ListView):
    template_name = "dashboard/provider_list.html"
    context_object_name = "providers"
    paginate_by = 25

    def get_queryset(self):
        qs = self.scoped_providers().order_by("name")
        self.filterset = ProviderFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter"] = self.filterset
        return ctx


class ProviderCreateView(StaffRequiredMixin, CreateView):
    model = Provider
    template_name = "dashboard/provider_form.html"
    fields = ["merchant_code", "name", "category", "mobile_number", "network",
              "merchant_type", "commission_type", "commission_value", "is_active"]
    success_url = reverse_lazy("dashboard:providers")

    def form_valid(self, form):
        if not self.request.user.is_superuser:
            form.instance.managed_by = self.request.user
        return super().form_valid(form)


class ProviderUpdateView(StaffRequiredMixin, RoleScopedQuerysetMixin, UpdateView):
    model = Provider
    template_name = "dashboard/provider_form.html"
    fields = ["merchant_code", "name", "category", "mobile_number", "network",
              "merchant_type", "commission_type", "commission_value", "is_active"]
    success_url = reverse_lazy("dashboard:providers")

    def get_queryset(self):
        return self.scoped_providers()




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