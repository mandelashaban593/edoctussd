from django.contrib import admin
from .models import Provider, FeeRule, Transaction, IPNLog


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("merchant_code", "name", "category", "network", "merchant_type",
                     "commission_type", "commission_value", "is_active", "managed_by")
    list_filter = ("category", "network", "merchant_type", "is_active")
    search_fields = ("merchant_code", "name", "mobile_number")
    autocomplete_fields = ("managed_by",)


@admin.register(FeeRule)
class FeeRuleAdmin(admin.ModelAdmin):
    list_display = ("network", "merchant_type", "min_amount", "max_amount", "fee_type", "fee_value", "is_active")
    list_filter = ("network", "merchant_type", "fee_type", "is_active")
    ordering = ("network", "min_amount")


class IPNLogInline(admin.TabularInline):
    model = IPNLog
    extra = 0
    readonly_fields = ("direction", "payload", "received_at")
    can_delete = False


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("payment_external_reference", "provider", "amount", "mm_fee",
                     "edoctor_commission", "total_payable", "network", "status",
                     "settlement_status", "created_at")
    list_filter = ("status", "network", "settlement_status", "provider__category", "created_at")
    search_fields = ("payment_external_reference", "reference_id", "msisdn", "provider__name",
                      "provider__merchant_code")
    date_hierarchy = "created_at"
    readonly_fields = ("reference_id", "raw_callout_request", "raw_ipn_payload", "created_at", "updated_at")
    inlines = [IPNLogInline]


@admin.register(IPNLog)
class IPNLogAdmin(admin.ModelAdmin):
    list_display = ("transaction", "direction", "received_at")
    list_filter = ("direction",)