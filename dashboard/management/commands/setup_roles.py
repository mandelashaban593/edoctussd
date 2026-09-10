from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from dashboard.models import Provider, Transaction, FeeRule


class Command(BaseCommand):
    help = "Create the 'Admin' group used for dashboard-only (non-superuser) staff access."

    def handle(self, *args, **options):
        group, created = Group.objects.get_or_create(name="Admin")

        models_and_perms = [
            (Provider, ["view", "add", "change"]),
            (Transaction, ["view", "change"]),  # admins can update settlement notes, not delete
            (FeeRule, ["view"]),
        ]
        perms = []
        for model, actions in models_and_perms:
            ct = ContentType.objects.get_for_model(model)
            for action in actions:
                codename = f"{action}_{model._meta.model_name}"
                try:
                    perms.append(Permission.objects.get(content_type=ct, codename=codename))
                except Permission.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Missing permission {codename}, run migrate first."))

        group.permissions.set(perms)
        self.stdout.write(self.style.SUCCESS(
            f"'Admin' group {'created' if created else 'updated'} with {len(perms)} permissions. "
            "Add staff users to this group and set is_staff=True (but NOT is_superuser) "
            "so they see the dashboard but not the full Django admin/user management."
        ))