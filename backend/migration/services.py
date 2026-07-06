"""Persistence helpers shared by the Celery tasks in tasks.py."""

from django.db import transaction

from migration.fhir_client import FhirClient
from migration.models import Observation, Patient
from migration.transformers import transform_observation, transform_patient


def upsert_patient(fhir_patient: dict) -> Patient | None:
    """Transform and upsert a single FHIR Patient. Returns None if unmappable."""
    data = transform_patient(fhir_patient)
    if not data:
        return None

    patient, _ = Patient.objects.update_or_create(
        fhir_id=data["fhir_id"],
        defaults={
            "given_name": data["given_name"],
            "family_name": data["family_name"],
            "birth_date": data["birth_date"],
            "gender": data["gender"],
            "mrn": data["mrn"],
            "source_updated_at": data["source_updated_at"],
        },
    )
    return patient


def migrate_observations_for_patient(client: FhirClient, patient: Patient) -> int:
    """Fetch, transform, and upsert all observations for one patient.

    Runs in a single transaction so a mid-write failure never leaves a
    partially-written patient.
    """
    count = 0
    with transaction.atomic():
        for fhir_obs in client.fetch_observations_for_patient(patient.fhir_id):
            data = transform_observation(fhir_obs)
            if not data or data["patient_fhir_id"] != patient.fhir_id:
                continue

            Observation.objects.update_or_create(
                fhir_id=data["fhir_id"],
                defaults={
                    "patient": patient,
                    "code": data["code"],
                    "display": data["display"],
                    "value_numeric": data["value_numeric"],
                    "value_text": data["value_text"],
                    "unit": data["unit"],
                    "status": data["status"],
                    "effective_at": data["effective_at"],
                    "source_updated_at": data["source_updated_at"],
                },
            )
            count += 1
    return count
