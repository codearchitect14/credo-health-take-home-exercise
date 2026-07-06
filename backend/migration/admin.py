from django.contrib import admin

from migration.models import MigrationRun, Observation, Patient

admin.site.register(Patient)
admin.site.register(Observation)
admin.site.register(MigrationRun)
