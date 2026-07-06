from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from migration.models import MigrationRun
from migration.tasks import run_migration


class Command(BaseCommand):
    help = "Fetch patients and observations from the FHIR sandbox and persist locally."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=settings.MIGRATION_DEFAULT_PATIENT_LIMIT,
            help=(
                "Maximum number of patients to migrate "
                f"(default: {settings.MIGRATION_DEFAULT_PATIENT_LIMIT})."
            ),
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        self.stdout.write(f"Starting FHIR migration (limit={limit})...")

        run = MigrationRun.objects.create(status=MigrationRun.Status.RUNNING)
        run_migration.delay(run.pk, limit)
        run.refresh_from_db()

        if run.status == MigrationRun.Status.COMPLETED:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Migration {run.status}: "
                    f"{run.patients_migrated} patients, "
                    f"{run.observations_migrated} observations."
                )
            )
        elif run.status == MigrationRun.Status.FAILED:
            raise CommandError(f"Migration failed: {run.error_message}")
        else:
            self.stdout.write(
                f"Migration run #{run.pk} dispatched to Celery workers; "
                "track progress at /api/migrate/status/."
            )
