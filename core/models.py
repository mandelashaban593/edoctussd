import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator


class Network(models.TextChoices):
    MTN = "MTN", "MTN"
    AIRTEL = "AIRTEL", "Airtel"


class MerchantType(models.TextChoices):
    INDIVIDUAL = "INDIVIDUAL", "Individual Merchant"
    BUSINESS = "BUSINESS", "Business Merchant"


class ProviderCategory(models.TextChoices):
    CLINIC = "CLINIC", "Clinic"
    PHARMACY = "PHARMACY", "Pharmacy"
    HOSPITAL = "HOSPITAL", "Hospital"
    OTHER = "OTHER", "Other Healthcare Provider"


class CommissionType(models.TextChoices):
    FIXED = "FIXED", "Fixed amount (UGX)"
    PERCENT = "PERCENT", "Percentage of amount"


class Provider(models.Model):
    """A clinic / pharmacy / hospital registered on the eDoctorUG dashboard."""

    merchant_code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=ProviderCategory.choices)
    mobile_number = models.CharField(
        max_length=15, help_text="Registered mobile-money number, e.g. 256772123456"
    )
    network = models.CharField(max_length=10, choices=Network.choices)
    merchant_type = models.CharField(
        max_length=15,
        choices=MerchantType.choices,
        default=MerchantType.INDIVIDUAL,
        help_text="Only relevant for MTN fee-band lookup.",
    )
    commission_type = models.CharField(
        max_length=10, choices=CommissionType.choices, default=CommissionType.PERCENT
    )
    commission_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="eDoctorUG's own commission: either UGX flat amount or percent, per commission_type.",
    )
    is_active = models.BooleanField(default=True)
    managed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="providers",
        help_text="Admin user who manages this provider in the dashboard (for scoping non-superuser access).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.merchant_code} - {self.name}"

    def calculate_commission(self, amount: Decimal) -> Decimal:
        if self.commission_type == CommissionType.FIXED:
            return self.commission_value
        return (amount * self.commission_value / Decimal("100")).quantize(Decimal("1"))


class FeeRule(models.Model):
    """
    Mobile-money transaction charge bands, e.g.:
      AIRTEL  any        60,001-125,000  FIXED  3500
      MTN     INDIVIDUAL  any            PERCENT 1.0
      MTN     BUSINESS    any            PERCENT 2.0
    """

    network = models.CharField(max_length=10, choices=Network.choices)
    merchant_type = models.CharField(
        max_length=15,
        choices=MerchantType.choices,
        blank=True,
        null=True,
        help_text="Leave blank for Airtel (band-based, merchant-type independent).",
    )
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    max_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Leave blank for 'and above'."
    )
    fee_type = models.CharField(max_length=10, choices=CommissionType.choices)
    fee_value = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="UGX amount if FIXED, percentage points if PERCENT (e.g. 1.00 = 1%)."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["network", "min_amount"]

    def __str__(self):
        band = f"{self.min_amount}-{self.max_amount or '∞'}"
        mt = f" [{self.merchant_type}]" if self.merchant_type else ""
        return f"{self.network}{mt} {band} -> {self.fee_type} {self.fee_value}"

    def matches(self, network, merchant_type, amount: Decimal) -> bool:
        if self.network != network:
            return False
        if self.merchant_type and self.merchant_type != merchant_type:
            return False
        if amount < self.min_amount:
            return False
        if self.max_amount is not None and amount > self.max_amount:
            return False
        return True

    def compute_fee(self, amount: Decimal) -> Decimal:
        if self.fee_type == CommissionType.FIXED:
            return self.fee_value
        return (amount * self.fee_value / Decimal("100")).quantize(Decimal("1"))


class TransactionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class Transaction(models.Model):
    reference_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    payment_external_reference = models.CharField(max_length=64, unique=True)

    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name="transactions")
    msisdn = models.CharField(max_length=15)
    network = models.CharField(max_length=10, choices=Network.choices)

    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("1"))],
        help_text="Medicine/item amount entered by customer, before fees."
    )
    mm_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    edoctor_commission = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_payable = models.DecimalField(max_digits=12, decimal_places=2)

    currency = models.CharField(max_length=3, default="UGX")
    status = models.CharField(max_length=10, choices=TransactionStatus.choices, default=TransactionStatus.PENDING)

    payment_confirmation_reference = models.CharField(max_length=64, blank=True, null=True)
    settlement_status = models.CharField(
        max_length=15,
        choices=[("PENDING", "Pending"), ("SETTLED", "Settled"), ("FAILED", "Failed")],
        default="PENDING",
    )

    raw_callout_request = models.JSONField(blank=True, null=True)
    raw_ipn_payload = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["network"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.payment_external_reference} - {self.provider.name} - {self.status}"

    @property
    def net_provider_amount(self) -> Decimal:
        """Amount the provider actually receives = medicine amount only."""
        return self.amount


class IPNLog(models.Model):
    """Raw audit trail of every IPN callback received from Yo! Payments."""

    DIRECTION_CHOICES = [("SUCCESS", "Success"), ("FAILURE", "Failure")]

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="ipn_logs")
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.direction} IPN for {self.transaction.payment_external_reference}"