from decimal import Decimal
from django.core.management.base import BaseCommand
from core.models import FeeRule, Network, MerchantType, CommissionType


class Command(BaseCommand):
    help = "Seed sample MTN/Airtel fee rules described in the eDoctorUG integration spec."

    def handle(self, *args, **options):
        rules = [
            # Airtel: flat fee bands (sample - replace with the full attached charge table)
            dict(network=Network.AIRTEL, merchant_type=None, min_amount=Decimal("0"),
                 max_amount=Decimal("30000"), fee_type=CommissionType.FIXED, fee_value=Decimal("900")),
            dict(network=Network.AIRTEL, merchant_type=None, min_amount=Decimal("30001"),
                 max_amount=Decimal("60000"), fee_type=CommissionType.FIXED, fee_value=Decimal("1800")),
            dict(network=Network.AIRTEL, merchant_type=None, min_amount=Decimal("60001"),
                 max_amount=Decimal("125000"), fee_type=CommissionType.FIXED, fee_value=Decimal("3500")),
            # MTN: percentage based on merchant type
            dict(network=Network.MTN, merchant_type=MerchantType.INDIVIDUAL, min_amount=Decimal("0"),
                 max_amount=None, fee_type=CommissionType.PERCENT, fee_value=Decimal("1.00")),
            dict(network=Network.MTN, merchant_type=MerchantType.BUSINESS, min_amount=Decimal("0"),
                 max_amount=None, fee_type=CommissionType.PERCENT, fee_value=Decimal("2.00")),
        ]
        created = 0
        for r in rules:
            obj, was_created = FeeRule.objects.get_or_create(
                network=r["network"], merchant_type=r["merchant_type"],
                min_amount=r["min_amount"], max_amount=r["max_amount"],
                defaults={"fee_type": r["fee_type"], "fee_value": r["fee_value"]},
            )
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Seeded fee rules. {created} new rows created."))