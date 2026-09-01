import csv
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db.models import Sum, Count, Q
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, TemplateView, CreateView, UpdateView

from core.models import Provider, Transaction, TransactionStatus
from .filters import TransactionFilter, ProviderFilter


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