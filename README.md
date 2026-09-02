# edoctussd





Superuser (full Django admin + dashboard, sees every provider/transaction)

username: superadmin
password: SuperAdmin@2026

Admin (dashboard-only, scoped to providers they manage)

username: clinicadmin
password: ClinicAdmin@2026

I actually caught and fixed a real bug while verifying this: my first version gave clinicadmin is_staff=True, which — combined with the Admin group's model permissions — let it into the raw /admin/ site and defeated the "dashboard only" restriction. Fixed by setting is_staff=False for the Admin-group account; the custom dashboard checks group membership, not is_staff, so clinicadmin still gets full dashboard access while /admin/ correctly redirects it away (302). Confirmed with the test client:

superadmin → sees all 15 seeded providers, /admin/ → 200
clinicadmin → sees only 1 provider (auto-assigned to it by the seed command for testing scoping), /admin/ → 302, /transactions/ → 200

seed_users is idempotent and takes --reset-passwords if you ever change them locally and want to reset back to defaults. As with the other seed commands, these are dev/test credentials only — swap or remove them before deploying anywhere real.