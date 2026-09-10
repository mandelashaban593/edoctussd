import django_filters as df
from dashboard.models import Transaction, Provider, Network, TransactionStatus, ProviderCategory


class TransactionFilter(df.FilterSet):
    date_from = df.DateFilter(field_name="created_at", lookup_expr="gte", label="From date")
    date_to = df.DateFilter(field_name="created_at", lookup_expr="lte", label="To date")
    provider = df.CharFilter(field_name="provider__name", lookup_expr="icontains", label="Provider name")
    merchant_code = df.CharFilter(field_name="provider__merchant_code", lookup_expr="iexact")
    network = df.ChoiceFilter(choices=Network.choices)
    status = df.ChoiceFilter(choices=TransactionStatus.choices)
    category = df.ChoiceFilter(field_name="provider__category", choices=ProviderCategory.choices)
    reference = df.CharFilter(field_name="payment_external_reference", lookup_expr="icontains")
    min_amount = df.NumberFilter(field_name="amount", lookup_expr="gte")
    max_amount = df.NumberFilter(field_name="amount", lookup_expr="lte")

    class Meta:
        model = Transaction
        fields = [
            "date_from", "date_to", "provider", "merchant_code", "network",
            "status", "category", "reference", "min_amount", "max_amount",
        ]


class ProviderFilter(df.FilterSet):
    name = df.CharFilter(field_name="name", lookup_expr="icontains")
    merchant_code = df.CharFilter(field_name="merchant_code", lookup_expr="icontains")
    category = df.ChoiceFilter(choices=ProviderCategory.choices)
    network = df.ChoiceFilter(choices=Network.choices)
    is_active = df.BooleanFilter()

    class Meta:
        model = Provider
        fields = ["name", "merchant_code", "category", "network", "is_active"]