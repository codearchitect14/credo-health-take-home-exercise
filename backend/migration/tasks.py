"""Celery task pipeline mirroring the plan in Plan.md at demo scale.

run_migration performs sequential discovery (FHIR pagination cursors are
serial), upserts patients, then fans observation fetching out to
migrate_observation_batch tasks. Batch tasks complete out of order; the one
that drives pending_batches to zero marks the run completed. In eager mode
(the default) the whole pipeline executes inline, so no broker is required.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.db.models import F
from django.utils import timezone

from migration.fhir_client import FhirClient, FhirClientError
from migration.models import MigrationRun, Patient
from migration.services import migrate_observations_for_patient, upsert_patient

logger = logging.getLogger(__name__)


def _fail_run(run_id: int, error: str) -> None:
    MigrationRun.objects.filter(pk=run_id).exclude(
        status=MigrationRun.Status.FAILED
    ).update(
        status=MigrationRun.Status.FAILED,
        error_message=error,
        completed_at=timezone.now(),
    )


def _complete_run_if_done(run_id: int) -> None:
    MigrationRun.objects.filter(
        pk=run_id,
        pending_batches=0,
        status=MigrationRun.Status.RUNNING,
    ).update(
        status=MigrationRun.Status.COMPLETED,
        completed_at=timezone.now(),
    )


@shared_task
def run_migration(run_id: int, patient_limit: int | None = None) -> None:
    """Discovery phase: fetch and upsert patients, then fan out observation batches."""
    client = FhirClient()
    patient_fhir_ids: list[str] = []

    try:
        for fhir_patient in client.fetch_patients():
            if patient_limit is not None and len(patient_fhir_ids) >= patient_limit:
                break
            patient = upsert_patient(fhir_patient)
            if patient:
                patient_fhir_ids.append(patient.fhir_id)
    except FhirClientError as exc:
        logger.error("Migration run %s failed during discovery: %s", run_id, exc)
        _fail_run(run_id, str(exc))
        return

    batch_size = settings.MIGRATION_BATCH_SIZE
    batches = [
        patient_fhir_ids[i : i + batch_size]
        for i in range(0, len(patient_fhir_ids), batch_size)
    ]

    MigrationRun.objects.filter(pk=run_id).update(
        patients_migrated=len(patient_fhir_ids),
        pending_batches=len(batches),
    )

    if not batches:
        _complete_run_if_done(run_id)
        return

    for batch in batches:
        migrate_observation_batch.delay(run_id, batch)


@shared_task
def migrate_observation_batch(run_id: int, patient_fhir_ids: list[str]) -> None:
    """Fetch and upsert observations for a batch of already-migrated patients."""
    client = FhirClient()
    observation_count = 0

    try:
        for fhir_id in patient_fhir_ids:
            patient = Patient.objects.get(fhir_id=fhir_id)
            observation_count += migrate_observations_for_patient(client, patient)
    except FhirClientError as exc:
        logger.error("Migration run %s failed on batch %s: %s", run_id, patient_fhir_ids, exc)
        MigrationRun.objects.filter(pk=run_id).update(
            observations_migrated=F("observations_migrated") + observation_count,
            pending_batches=F("pending_batches") - 1,
        )
        _fail_run(run_id, str(exc))
        return

    MigrationRun.objects.filter(pk=run_id).update(
        observations_migrated=F("observations_migrated") + observation_count,
        pending_batches=F("pending_batches") - 1,
    )
    _complete_run_if_done(run_id)
