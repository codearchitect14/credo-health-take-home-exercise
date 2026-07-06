from django.db import models


class Patient(models.Model):
    fhir_id = models.CharField(max_length=64, unique=True, db_index=True)
    given_name = models.CharField(max_length=128, blank=True)
    family_name = models.CharField(max_length=128, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=16, default="unknown")
    mrn = models.CharField(max_length=64, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    migrated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["family_name", "given_name"]

    def __str__(self) -> str:
        return f"{self.given_name} {self.family_name} ({self.fhir_id})"

    @property
    def full_name(self) -> str:
        return f"{self.given_name} {self.family_name}".strip()


class Observation(models.Model):
    fhir_id = models.CharField(max_length=64, unique=True, db_index=True)
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="observations"
    )
    code = models.CharField(max_length=64, blank=True)
    display = models.CharField(max_length=256, blank=True)
    value_numeric = models.FloatField(null=True, blank=True)
    value_text = models.CharField(max_length=256, blank=True)
    unit = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, default="unknown")
    effective_at = models.DateTimeField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    migrated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_at", "display"]

    def __str__(self) -> str:
        return f"{self.display or self.code} ({self.fhir_id})"


class MigrationRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.RUNNING
    )
    patients_migrated = models.PositiveIntegerField(default=0)
    observations_migrated = models.PositiveIntegerField(default=0)
    # Observation-fetch tasks still in flight; the task that drives this to
    # zero marks the run completed.
    pending_batches = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"MigrationRun #{self.pk} ({self.status})"
