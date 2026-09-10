"""
Management command: seed_sample_data

Populates 15 sample records in each of:
  - Provider
  - FeeRule
  - Transaction
  - IPNLog

Usage:
    python manage.py seed_sample_data
    python manage.py seed_sample_data --flush   # wipe these 4 tables first, then reseed

Safe to re-run: providers/fee-rules use get_or_create on their natural
keys, and transactions/IPN logs are only created if they don't already
exist for this seed batch (tagged with a "SEED-" reference prefix), so
running it twice will not double the counts.
"""
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.utils import timezone

from dashboard.models import (
    Provider,
    FeeRule,
    Transaction,
    IPNLog,
    Network,
    MerchantType,
    ProviderCategory,
    CommissionType,
    TransactionStatus,
    SettlementStatus,
)

SEED_PREFIX = "SEED-"


# ---------------------------------------------------------------------------
# Fixed sample data (15 of each) - deterministic, so re-running is idempotent.
# ---------------------------------------------------------------------------

PROVIDER_SEED = [
    # merchant_code, name, category, network, merchant_type, commission_type, commission_value
    ("2001", "Doctors Clinic Sseguku", ProviderCategory.CLINIC, Network.MTN, MerchantType.INDIVIDUAL, CommissionType.PERCENT, Decimal("10.00")),
    ("2002", "Kampala Pharmacy Plus", ProviderCategory.PHARMACY, Network.AIRTEL, MerchantType.INDIVIDUAL, CommissionType.FIXED, Decimal("1000.00")),
    ("2003", "Mulago Wellness Hospital", ProviderCategory.HOSPITAL, Network.MTN, MerchantType.BUSINESS, CommissionType.PERCENT, Decimal("8.00")),
    ("2004", "Nakawa Family Clinic", ProviderCategory.CLINIC, Network.AIRTEL, MerchantType.INDIVIDUAL, CommissionType.PERCENT, Decimal("9.50")),
    ("2005", "Entebbe Road Pharmacy", ProviderCategory.PHARMACY, Network.MTN, MerchantType.INDIVIDUAL, CommissionType.FIXED, Decimal("800.00")),
    ("2006", "Jinja Referral Hospital", ProviderCategory.HOSPITAL, Network.AIRTEL, MerchantType.INDIVIDUAL, CommissionType.PERCENT, Decimal("7.00")),
    ("2007", "Ntinda Health Point Clinic", ProviderCategory.CLINIC, Network.MTN, MerchantType.INDIVIDUAL, CommissionType.PERCENT, Decimal("10.00")),
    ("2008", "Bugolobi Care Pharmacy", ProviderCategory.PHARMACY, Network.AIRTEL, MerchantType.INDIVIDUAL, CommissionType.FIXED, Decimal("1200.00")),
    ("2009", "Mbarara Community Hospital", ProviderCategory.HOSPITAL, Network.MTN, MerchantType.BUSINESS, CommissionType.PERCENT, Decimal("8.50")),
    ("2010", "Kira Road Medical Clinic", ProviderCategory.CLINIC, Network.AIRTEL, MerchantType.INDIVIDUAL, CommissionType.PERCENT, Decimal("9.00")),
    ("2011", "Wandegeya Pharmacy", ProviderCategory.PHARMACY, Network.MTN, MerchantType.INDIVIDUAL, CommissionType.FIXED, Decimal("700.00")),
    ("2012", "Gulu Regional Hospital", ProviderCategory.HOSPITAL, Network.AIRTEL, MerchantType.INDIVIDUAL, CommissionType.PERCENT, Decimal("7.50")),
    ("2013", "Bukoto Diagnostic Clinic", ProviderCategory.CLINIC, Network.MTN, MerchantType.INDIVIDUAL, CommissionType.PERCENT, Decimal("10.00")),
    ("2014", "Mbale Health Pharmacy", ProviderCategory.PHARMACY, Network.AIRTEL, MerchantType.INDIVIDUAL, CommissionType.FIXED, Decimal("950.00")),
    ("2015", "Other Care Home Services", ProviderCategory.OTHER, Network.MTN, MerchantType.BUSINESS, CommissionType.PERCENT, Decimal("6.00")),
]

FEE_RULE_SEED = [
    # network, merchant_type, min_amount, max_amount, fee_type, fee_value
    (Network.AIRTEL, None, Decimal("0"), Decimal("30000"), CommissionType.FIXED, Decimal("900")),
    (Network.AIRTEL, None, Decimal("30001"), Decimal("60000"), CommissionType.FIXED, Decimal("1800")),
    (Network.AIRTEL, None, Decimal("60001"), Decimal("125000"), CommissionType.FIXED, Decimal("3500")),
    (Network.AIRTEL, None, Decimal("125001"), Decimal("250000"), CommissionType.FIXED, Decimal("6500")),
    (Network.AIRTEL, None, Decimal("250001"), Decimal("500000"), CommissionType.FIXED, Decimal("12000")),
    (Network.MTN, MerchantType.INDIVIDUAL, Decimal("0"), Decimal("50000"), CommissionType.PERCENT, Decimal("1.00")),
    (Network.MTN, MerchantType.INDIVIDUAL, Decimal("50001"), Decimal("150000"), CommissionType.PERCENT, Decimal("0.90")),
    (Network.MTN, MerchantType.INDIVIDUAL, Decimal("150001"), Decimal("500000"), CommissionType.PERCENT, Decimal("0.80")),
    (Network.MTN, MerchantType.INDIVIDUAL, Decimal("500001"), Decimal("1000000"), CommissionType.PERCENT, Decimal("0.70")),
    (Network.MTN, MerchantType.INDIVIDUAL, Decimal("1000001"), None, CommissionType.PERCENT, Decimal("0.60")),
    (Network.MTN, MerchantType.BUSINESS, Decimal("0"), Decimal("50000"), CommissionType.PERCENT, Decimal("2.00")),
    (Network.MTN, MerchantType.BUSINESS, Decimal("50001"), Decimal("150000"), CommissionType.PERCENT, Decimal("1.80")),
    (Network.MTN, MerchantType.BUSINESS, Decimal("150001"), Decimal("500000"), CommissionType.PERCENT, Decimal("1.60")),
    (Network.MTN, MerchantType.BUSINESS, Decimal("500001"), Decimal("1000000"), CommissionType.PERCENT, Decimal("1.40")),
    (Network.MTN, MerchantType.BUSINESS, Decimal("1000001"), None, CommissionType.PERCENT, Decimal("1.20")),
]

# 15 sample transaction amounts (medicine/item amount before fees), one per provider above.
TRANSACTION_AMOUNTS = [
    10000, 45000, 250000, 18000, 60000,
    500000, 12000, 90000, 175000, 35000,
    8000, 300000, 15000, 70000, 620000,
]

# Status distribution across the 15 transactions - deliberately varied so the
# dashboard KPIs/reporting have something interesting to filter on.
TRANSACTION_STATUSES = [
    TransactionStatus.SUCCESS, TransactionStatus.SUCCESS, TransactionStatus.SUCCESS,
    TransactionStatus.PENDING, TransactionStatus.SUCCESS, TransactionStatus.FAILED,
    TransactionStatus.SUCCESS, TransactionStatus.SUCCESS, TransactionStatus.CANCELLED,
    TransactionStatus.SUCCESS, TransactionStatus.PENDING, TransactionStatus.SUCCESS,
    TransactionStatus.FAILED, TransactionStatus.SUCCESS, TransactionStatus.SUCCESS,
]

SAMPLE_MSISDNS = [f"25677{2000000 + i:07d}"[:12] for i in range(15)]


class Command(BaseCommand):
    help = "Seed 15 sample records into Provider, FeeRule, Transaction and IPNLog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing IPNLog/Transaction/FeeRule/Provider rows before reseeding.",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write(self.style.WARNING("Flushing existing IPNLog, Transaction, FeeRule and Provider rows..."))
            IPNLog.objects.all().delete()
            Transaction.objects.all().delete()
            FeeRule.objects.all().delete()
            Provider.objects.all().delete()

        with db_transaction.atomic():
            providers = self._seed_providers()
            self._seed_fee_rules()
            transactions = self._seed_transactions(providers)
            self._seed_ipn_logs(transactions)

        self.stdout.write(self.style.SUCCESS(
            f"Done. Provider={Provider.objects.count()}, FeeRule={FeeRule.objects.count()}, "
            f"Transaction={Transaction.objects.count()}, IPNLog={IPNLog.objects.count()}."
        ))

    # ------------------------------------------------------------------
    def _seed_providers(self):
        providers = []
        for code, name, category, network, merchant_type, commission_type, commission_value in PROVIDER_SEED:
            provider, _ = Provider.objects.get_or_create(
                merchant_code=code,
                defaults=dict(
                    name=name,
                    category=category,
                    mobile_number=f"25677{2000000 + int(code):07d}"[:12],
                    network=network,
                    merchant_type=merchant_type,
                    commission_type=commission_type,
                    commission_value=commission_value,
                    is_active=True,
                ),
            )
            providers.append(provider)
        self.stdout.write(self.style.SUCCESS(f"Providers ready: {len(providers)}"))
        return providers

    def _seed_fee_rules(self):
        created = 0
        for network, merchant_type, min_amount, max_amount, fee_type, fee_value in FEE_RULE_SEED:
            _, was_created = FeeRule.objects.get_or_create(
                network=network,
                merchant_type=merchant_type,
                min_amount=min_amount,
                max_amount=max_amount,
                defaults=dict(fee_type=fee_type, fee_value=fee_value, is_active=True),
            )
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Fee rules ready: {FeeRule.objects.count()} ({created} newly created)"))

    def _seed_transactions(self, providers):
        transactions = []
        for i, provider in enumerate(providers):
            ref = f"{SEED_PREFIX}{i + 1:04d}"
            if Transaction.objects.filter(payment_external_reference=ref).exists():
                transactions.append(Transaction.objects.get(payment_external_reference=ref))
                continue

            amount = Decimal(str(TRANSACTION_AMOUNTS[i]))
            status = TRANSACTION_STATUSES[i]

            mm_fee = self._lookup_mm_fee(provider.network, provider.merchant_type, amount)
            edoctor_commission = provider.calculate_commission(amount)
            total_payable = amount + mm_fee + edoctor_commission

            settlement_status = (
                SettlementStatus.SETTLED if status == TransactionStatus.SUCCESS else SettlementStatus.PENDING
            )

            txn = Transaction.objects.create(
                payment_external_reference=ref,
                provider=provider,
                msisdn=SAMPLE_MSISDNS[i],
                network=provider.network,
                amount=amount,
                mm_fee=mm_fee,
                edoctor_commission=edoctor_commission,
                total_payable=total_payable,
                status=status,
                settlement_status=settlement_status,
                payment_confirmation_reference=f"MM-CONF-{i + 1:04d}" if status == TransactionStatus.SUCCESS else None,
                raw_callout_request={
                    "datetime": timezone.now().strftime("%Y%m%d%H%M"),
                    "anumbermsisdn": SAMPLE_MSISDNS[i],
                    "amount": str(amount),
                    "clinic_code": provider.merchant_code,
                    "seeded": True,
                },
            )
            transactions.append(txn)
        self.stdout.write(self.style.SUCCESS(f"Transactions ready: {len(transactions)}"))
        return transactions

    def _seed_ipn_logs(self, transactions):
        created = 0
        for i, txn in enumerate(transactions):
            if IPNLog.objects.filter(transaction=txn).exists():
                continue

            if txn.status == TransactionStatus.SUCCESS:
                direction = "SUCCESS"
                payload = {
                    "payment_external_reference": txn.payment_external_reference,
                    "confirmation_reference": txn.payment_confirmation_reference,
                    "status": "SUCCESS",
                    "amount_paid": str(txn.total_payable),
                    "network": txn.network,
                    "msisdn": txn.msisdn,
                    "seeded": True,
                }
            else:
                direction = "FAILURE"
                reason = {
                    TransactionStatus.PENDING: "Customer has not yet confirmed the mobile money prompt.",
                    TransactionStatus.FAILED: "Mobile money payment declined by network.",
                    TransactionStatus.CANCELLED: "Customer cancelled the USSD session.",
                }.get(txn.status, "Unknown failure reason.")
                payload = {
                    "payment_external_reference": txn.payment_external_reference,
                    "status": txn.status,
                    "reason": reason,
                    "network": txn.network,
                    "msisdn": txn.msisdn,
                    "seeded": True,
                }

            IPNLog.objects.create(transaction=txn, direction=direction, payload=payload)
            created += 1
        self.stdout.write(self.style.SUCCESS(f"IPN logs ready: {created} newly created (total {IPNLog.objects.count()})"))

    @staticmethod
    def _lookup_mm_fee(network, merchant_type, amount: Decimal) -> Decimal:
        for rule in FeeRule.objects.filter(network=network, is_active=True).order_by("min_amount"):
            if rule.matches(network, merchant_type, amount):
                return rule.compute_fee(amount)
        return Decimal("0.00")