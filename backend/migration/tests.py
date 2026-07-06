from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from migration.fhir_client import FhirClient, FhirClientError
from migration.models import MigrationRun, Observation, Patient
from migration.tasks import run_migration
from migration.transformers import transform_observation, transform_patient

SAMPLE_PATIENT = {
    "resourceType": "Patient",
    "id": "example-patient-1",
    "meta": {"lastUpdated": "2024-01-15T10:00:00Z"},
    "identifier": [{"value": "MRN-12345"}],
    "name": [{"given": ["Jane"], "family": "Doe"}],
    "gender": "female",
    "birthDate": "1990-05-20",
}

SAMPLE_OBSERVATION = {
    "resourceType": "Observation",
    "id": "obs-1",
    "status": "final",
    "code": {
        "coding": [{"code": "8867-4", "display": "Heart rate"}],
    },
    "subject": {"reference": "Patient/example-patient-1"},
    "effectiveDateTime": "2024-01-15T11:00:00Z",
    "valueQuantity": {"value": 72, "unit": "beats/min"},
}


@pytest.mark.django_db
class TestTransformers:
    def test_transform_patient_maps_fields(self):
        result = transform_patient(SAMPLE_PATIENT)
        assert result is not None
        assert result["fhir_id"] == "example-patient-1"
        assert result["given_name"] == "Jane"
        assert result["family_name"] == "Doe"
        assert result["birth_date"] == date(1990, 5, 20)
        assert result["gender"] == "female"
        assert result["mrn"] == "MRN-12345"

    def test_transform_patient_missing_id_returns_none(self):
        assert transform_patient({"resourceType": "Patient"}) is None

    def test_transform_patient_prefers_official_name_and_mrn_identifier(self):
        patient = {
            **SAMPLE_PATIENT,
            "name": [
                {"use": "nickname", "given": ["JJ"], "family": "D"},
                {"use": "official", "given": ["Jane"], "family": "Doe"},
            ],
            "identifier": [
                {"value": "SSN-999"},
                {
                    "type": {"coding": [{"code": "MR"}]},
                    "value": "MRN-12345",
                },
            ],
        }
        result = transform_patient(patient)
        assert result["given_name"] == "Jane"
        assert result["family_name"] == "Doe"
        assert result["mrn"] == "MRN-12345"

    def test_transform_observation_maps_quantity(self):
        result = transform_observation(SAMPLE_OBSERVATION)
        assert result is not None
        assert result["fhir_id"] == "obs-1"
        assert result["patient_fhir_id"] == "example-patient-1"
        assert result["code"] == "8867-4"
        assert result["display"] == "Heart rate"
        assert result["value_numeric"] == 72
        assert result["unit"] == "beats/min"
        assert result["status"] == "final"

    def test_transform_observation_missing_subject_returns_none(self):
        obs = {**SAMPLE_OBSERVATION, "subject": None}
        assert transform_observation(obs) is None

    def test_transform_observation_component_values(self):
        """Multi-part observations (e.g. blood pressure) store values in component[]."""
        obs = {
            "resourceType": "Observation",
            "id": "obs-bp",
            "status": "final",
            "code": {"coding": [{"code": "85354-9", "display": "Blood pressure"}]},
            "subject": {"reference": "Patient/example-patient-1"},
            "component": [
                {
                    "code": {"coding": [{"code": "8480-6", "display": "Systolic"}]},
                    "valueQuantity": {"value": 120, "unit": "mmHg"},
                },
                {
                    "code": {"coding": [{"code": "8462-4", "display": "Diastolic"}]},
                    "valueQuantity": {"value": 80, "unit": "mmHg"},
                },
            ],
        }
        result = transform_observation(obs)
        assert result["value_numeric"] is None
        assert result["value_text"] == "Systolic: 120 mmHg; Diastolic: 80 mmHg"

    def test_transform_observation_codeable_concept_value(self):
        obs = {
            "resourceType": "Observation",
            "id": "obs-cc",
            "status": "final",
            "code": {"coding": [{"code": "exam-finding"}]},
            "subject": {"reference": "Patient/example-patient-1"},
            "valueCodeableConcept": {"text": "Positive"},
        }
        result = transform_observation(obs)
        assert result["value_text"] == "Positive"
        # No display on the coding: fall back to the code so the UI isn't blank.
        assert result["display"] == "exam-finding"


@pytest.mark.django_db
class TestMigrationTasks:
    """Tasks run inline here because CELERY_TASK_ALWAYS_EAGER defaults to true."""

    @patch("migration.tasks.FhirClient")
    def test_run_migration_persists_patients_and_observations(self, mock_client_cls):
        mock_client = MagicMock(spec=FhirClient)
        mock_client.fetch_patients.return_value = [SAMPLE_PATIENT]
        mock_client.fetch_observations_for_patient.return_value = [SAMPLE_OBSERVATION]
        mock_client_cls.return_value = mock_client

        run = MigrationRun.objects.create(status=MigrationRun.Status.RUNNING)
        run_migration.delay(run.pk, 5)
        run.refresh_from_db()

        assert run.status == "completed"
        assert run.patients_migrated == 1
        assert run.observations_migrated == 1
        assert run.pending_batches == 0
        assert run.completed_at is not None
        assert Patient.objects.filter(fhir_id="example-patient-1").exists()
        assert Observation.objects.filter(fhir_id="obs-1").exists()

    @patch("migration.tasks.FhirClient")
    def test_run_migration_marks_failed_on_discovery_error(self, mock_client_cls):
        mock_client = MagicMock(spec=FhirClient)
        mock_client.fetch_patients.side_effect = FhirClientError("upstream down", 503)
        mock_client_cls.return_value = mock_client

        run = MigrationRun.objects.create(status=MigrationRun.Status.RUNNING)
        run_migration.delay(run.pk, 1)
        run.refresh_from_db()

        assert run.status == "failed"
        assert "upstream down" in run.error_message

    @patch("migration.tasks.FhirClient")
    def test_run_migration_marks_failed_on_observation_error(self, mock_client_cls):
        mock_client = MagicMock(spec=FhirClient)
        mock_client.fetch_patients.return_value = [SAMPLE_PATIENT]
        mock_client.fetch_observations_for_patient.side_effect = FhirClientError(
            "timeout", None
        )
        mock_client_cls.return_value = mock_client

        run = MigrationRun.objects.create(status=MigrationRun.Status.RUNNING)
        run_migration.delay(run.pk, 5)
        run.refresh_from_db()

        assert run.status == "failed"
        assert "timeout" in run.error_message
        # Patients migrated during discovery are kept (idempotent re-run overwrites).
        assert Patient.objects.filter(fhir_id="example-patient-1").exists()

    @patch("migration.tasks.FhirClient")
    def test_run_migration_batches_fan_out(self, mock_client_cls):
        patients = [
            {**SAMPLE_PATIENT, "id": f"patient-{i}"} for i in range(7)
        ]
        mock_client = MagicMock(spec=FhirClient)
        mock_client.fetch_patients.return_value = patients
        mock_client.fetch_observations_for_patient.return_value = []
        mock_client_cls.return_value = mock_client

        run = MigrationRun.objects.create(status=MigrationRun.Status.RUNNING)
        with patch("migration.tasks.migrate_observation_batch.delay") as mock_delay:
            run_migration.delay(run.pk, None)

        # 7 patients at batch size 5 -> 2 batches
        assert mock_delay.call_count == 2
        run.refresh_from_db()
        assert run.patients_migrated == 7
        assert run.pending_batches == 2


@pytest.mark.django_db
class TestPatientAPI:
    def setup_method(self):
        self.client = APIClient()
        self.patient = Patient.objects.create(
            fhir_id="p-1",
            given_name="Jane",
            family_name="Doe",
            birth_date=date(1990, 5, 20),
            gender="female",
        )
        Observation.objects.create(
            fhir_id="o-1",
            patient=self.patient,
            code="8867-4",
            display="Heart rate",
            value_numeric=72,
            unit="beats/min",
            status="final",
        )

    def test_list_patients(self):
        url = reverse("patient-list")
        response = self.client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["full_name"] == "Jane Doe"
        assert response.data[0]["observation_count"] == 1

    def test_get_patient_detail_with_observations(self):
        url = reverse("patient-detail", kwargs={"pk": self.patient.pk})
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["fhir_id"] == "p-1"
        assert len(response.data["observations"]) == 1
        assert response.data["observations"][0]["display"] == "Heart rate"

    def test_patient_not_found_returns_404(self):
        url = reverse("patient-detail", kwargs={"pk": 9999})
        response = self.client.get(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestMigrationAPI:
    @patch("migration.tasks.FhirClient")
    def test_migrate_endpoint_returns_502_on_fhir_failure(self, mock_client_cls):
        mock_client = MagicMock(spec=FhirClient)
        mock_client.fetch_patients.side_effect = FhirClientError(
            "Service unavailable", 503
        )
        mock_client_cls.return_value = mock_client

        client = APIClient()
        response = client.post(reverse("migrate") + "?limit=1")
        assert response.status_code == 502
        assert "FHIR API request failed" in response.data["detail"]

    @patch("migration.tasks.FhirClient")
    def test_migrate_endpoint_returns_201_when_run_completes(self, mock_client_cls):
        mock_client = MagicMock(spec=FhirClient)
        mock_client.fetch_patients.return_value = [SAMPLE_PATIENT]
        mock_client.fetch_observations_for_patient.return_value = [SAMPLE_OBSERVATION]
        mock_client_cls.return_value = mock_client

        client = APIClient()
        response = client.post(reverse("migrate") + "?limit=5")
        assert response.status_code == 201
        assert response.data["status"] == "completed"
        assert response.data["patients_migrated"] == 1

    @pytest.mark.parametrize("limit", ["abc", "0", "-5"])
    def test_migrate_endpoint_rejects_invalid_limit(self, limit):
        client = APIClient()
        response = client.post(reverse("migrate") + f"?limit={limit}")
        assert response.status_code == 400


def _mock_response(status_code, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    if status_code >= 400:
        from requests.exceptions import HTTPError

        response.raise_for_status.side_effect = HTTPError(response=response)
    return response


class TestFhirClientRetry:
    PATIENT_BUNDLE = {
        "resourceType": "Bundle",
        "entry": [{"resource": SAMPLE_PATIENT}],
    }

    def test_retries_transient_errors_then_succeeds(self):
        session = MagicMock()
        session.headers = {}
        session.get.side_effect = [
            _mock_response(503),
            _mock_response(429),
            _mock_response(200, self.PATIENT_BUNDLE),
        ]
        client = FhirClient(base_url="http://fhir.test", session=session)

        with patch("tenacity.nap.time.sleep"):  # skip real backoff delays
            patients = list(client.fetch_patients())

        assert len(patients) == 1
        assert patients[0]["id"] == "example-patient-1"
        assert session.get.call_count == 3

    def test_permanent_error_fails_without_retry(self):
        session = MagicMock()
        session.headers = {}
        session.get.return_value = _mock_response(404)
        client = FhirClient(base_url="http://fhir.test", session=session)

        with pytest.raises(FhirClientError) as exc_info:
            list(client.fetch_patients())

        assert exc_info.value.status_code == 404
        assert session.get.call_count == 1
