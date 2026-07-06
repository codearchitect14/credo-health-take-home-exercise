from django.conf import settings
from django.db.models import Count
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from migration.models import MigrationRun, Patient
from migration.serializers import (
    MigrationRunSerializer,
    PatientDetailSerializer,
    PatientListSerializer,
)
from migration.tasks import run_migration


class PatientListView(APIView):
    def get(self, request):
        patients = Patient.objects.annotate(
            observation_count=Count("observations")
        ).order_by("family_name", "given_name")
        serializer = PatientListSerializer(patients, many=True)
        return Response(serializer.data)


class PatientDetailView(APIView):
    def get(self, request, pk: int):
        try:
            patient = Patient.objects.prefetch_related("observations").get(pk=pk)
        except Patient.DoesNotExist:
            return Response(
                {"detail": "Patient not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = PatientDetailSerializer(patient)
        return Response(serializer.data)


class MigrationTriggerView(APIView):
    """Trigger a FHIR migration. Optional ?limit=N to cap patients fetched."""

    def post(self, request):
        limit_param = request.query_params.get("limit")
        try:
            limit = (
                int(limit_param)
                if limit_param
                else settings.MIGRATION_DEFAULT_PATIENT_LIMIT
            )
        except ValueError:
            limit = -1
        if limit < 1:
            return Response(
                {"detail": "limit must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        run = MigrationRun.objects.create(status=MigrationRun.Status.RUNNING)
        run_migration.delay(run.pk, limit)

        # Eager mode executes inline, so the run may already be resolved;
        # with a real broker it stays "running" and the client polls status.
        run.refresh_from_db()
        if run.status == MigrationRun.Status.FAILED:
            return Response(
                {
                    "detail": "FHIR API request failed after retries.",
                    "error": run.error_message,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        response_status = (
            status.HTTP_201_CREATED
            if run.status == MigrationRun.Status.COMPLETED
            else status.HTTP_202_ACCEPTED
        )
        return Response(MigrationRunSerializer(run).data, status=response_status)


class MigrationStatusView(APIView):
    def get(self, request):
        runs = MigrationRun.objects.order_by("-started_at")[:10]
        return Response(MigrationRunSerializer(runs, many=True).data)
