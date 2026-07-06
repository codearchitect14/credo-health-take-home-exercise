from rest_framework import serializers

from migration.models import MigrationRun, Observation, Patient


class ObservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Observation
        fields = [
            "id",
            "fhir_id",
            "code",
            "display",
            "value_numeric",
            "value_text",
            "unit",
            "status",
            "effective_at",
        ]


class PatientListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    observation_count = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = [
            "id",
            "fhir_id",
            "given_name",
            "family_name",
            "full_name",
            "birth_date",
            "gender",
            "mrn",
            "observation_count",
        ]

    def get_observation_count(self, obj: Patient) -> int:
        if hasattr(obj, "observation_count"):
            return obj.observation_count
        return obj.observations.count()


class PatientDetailSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    observations = ObservationSerializer(many=True, read_only=True)

    class Meta:
        model = Patient
        fields = [
            "id",
            "fhir_id",
            "given_name",
            "family_name",
            "full_name",
            "birth_date",
            "gender",
            "mrn",
            "source_updated_at",
            "migrated_at",
            "observations",
        ]


class MigrationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = MigrationRun
        fields = [
            "id",
            "status",
            "started_at",
            "completed_at",
            "patients_migrated",
            "observations_migrated",
            "pending_batches",
            "error_message",
        ]
