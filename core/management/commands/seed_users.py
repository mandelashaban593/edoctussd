"""
Management command: seed_users

Creates two fixed, ready-to-use dashboard accounts for local testing:

  - superadmin  -> is_superuser=True, is_staff=True (full Django admin + dashboard, sees all providers)
  - clinicadmin -> is_staff=False, in the "Admin" group (dashboard only, scoped to providers they manage)

Usage:
    python manage.py setup_roles     # creates the "Admin" group + permissions (run this first)
    python manage.py seed_users
    python manage.py seed_users --reset-passwords   # reset both to their default passwords if changed

These are DEV/TEST credentials only. Change or remove them before any
staging/production deployment.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from core.models import Provider

User = get_user_model()

SUPERUSER_USERNAME = "superadmin"
SUPERUSER_PASSWORD = "SuperAdmin@2026"
SUPERUSER_EMAIL = "superadmin@edoctorug.test"

ADMIN_USERNAME = "clinicadmin"
ADMIN_PASSWORD = "ClinicAdmin@2026"
ADMIN_EMAIL = "clinicadmin@edoctorug.test"


class Command(BaseCommand):
    help = "Create a test superuser and a test Admin-group user for dashboard login."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Force both accounts' passwords back to their defaults even if they already exist.",
        )

    def handle(self, *args, **options):
        superuser = self._seed_superuser(options["reset_passwords"])
        admin_user = self._seed_admin_user(options["reset_passwords"])
        self._scope_sample_provider_to_admin(admin_user)

        self.stdout.write(self.style.SUCCESS("\nTest accounts ready:\n"))
        self.stdout.write(f"  Superuser   username: {SUPERUSER_USERNAME}   password: {SUPERUSER_PASSWORD}")
        self.stdout.write(f"  Admin       username: {ADMIN_USERNAME}   password: {ADMIN_PASSWORD}")
        self.stdout.write(self.style.WARNING(
            "\nThese are fixed dev/test credentials — change or remove them before staging/production."
        ))

    def _seed_superuser(self, reset_passwords):
        user, created = User.objects.get_or_create(
            username=SUPERUSER_USERNAME,
            defaults=dict(email=SUPERUSER_EMAIL, is_staff=True, is_superuser=True, is_active=True),
        )
        if created or reset_passwords:
            user.set_password(SUPERUSER_PASSWORD)
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save()
        self.stdout.write(self.style.SUCCESS(f"Superuser '{SUPERUSER_USERNAME}' {'created' if created else 'already existed'}."))
        return user

    def _seed_admin_user(self, reset_passwords):
        user, created = User.objects.get_or_create(
            username=ADMIN_USERNAME,
            defaults=dict(email=ADMIN_EMAIL, is_staff=False, is_superuser=False, is_active=True),
        )
        if created or reset_passwords:
            user.set_password(ADMIN_PASSWORD)
            # Deliberately is_staff=False: is_staff would let this account
            # into the raw /admin/ site (and, combined with the group's
            # model permissions, let them edit things outside the
            # dashboard's role-scoping). The custom dashboard's
            # StaffRequiredMixin checks group membership / is_superuser,
            # not is_staff, so this account still gets full dashboard access.
            user.is_staff = False
            user.is_superuser = False
            user.is_active = True
            user.save()

        try:
            admin_group = Group.objects.get(name="Admin")
            user.groups.add(admin_group)
        except Group.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                "'Admin' group not found — run `python manage.py setup_roles` first, "
                "otherwise this user can log in but the dashboard access check will reject them."
            ))

        self.stdout.write(self.style.SUCCESS(f"Admin user '{ADMIN_USERNAME}' {'created' if created else 'already existed'}."))
        return user

    def _scope_sample_provider_to_admin(self, admin_user):
        """
        If seed_sample_data has already been run, hand the admin user one
        provider to manage so role-scoping (Admin sees only their own
        providers/transactions) is visible immediately after login.
        """
        provider = Provider.objects.filter(merchant_code="2001").first()
        if provider and provider.managed_by_id is None:
            provider.managed_by = admin_user
            provider.save(update_fields=["managed_by"])
            self.stdout.write(self.style.SUCCESS(
                f"Assigned provider '{provider.name}' (2001) to '{ADMIN_USERNAME}' for scoped testing."
            ))