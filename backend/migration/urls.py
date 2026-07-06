from django.urls import path

from migration import views

urlpatterns = [
    path("patients/", views.PatientListView.as_view(), name="patient-list"),
    path("patients/<int:pk>/", views.PatientDetailView.as_view(), name="patient-detail"),
    path("migrate/", views.MigrationTriggerView.as_view(), name="migrate"),
    path("migrate/status/", views.MigrationStatusView.as_view(), name="migrate-status"),
]
