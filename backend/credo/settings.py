import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load backend/.env if present (real env vars take precedence). Kept to a few
# lines of stdlib instead of pulling in python-dotenv for one file.
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _value = _line.partition("=")
            os.environ.setdefault(_key.strip(), _value.strip())

SECRET_KEY = "dev-only-key-not-for-production"

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "migration",
]

MIDDLEWARE = [
    "credo.cors_middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "credo.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "credo.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # Path override lets Docker containers share the DB on a volume.
        "NAME": os.environ.get("DJANGO_DB_PATH", BASE_DIR / "db.sqlite3"),
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# FHIR migration settings, overridable via environment variables.
FHIR_BASE_URL = os.environ.get("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4")
FHIR_REQUEST_TIMEOUT = int(os.environ.get("FHIR_REQUEST_TIMEOUT", 30))
FHIR_MAX_RETRIES = int(os.environ.get("FHIR_MAX_RETRIES", 5))
FHIR_PAGE_SIZE = int(os.environ.get("FHIR_PAGE_SIZE", 50))
# Default patient cap per migration run; keeps demo load on the sandbox small.
MIGRATION_DEFAULT_PATIENT_LIMIT = int(
    os.environ.get("MIGRATION_DEFAULT_PATIENT_LIMIT", 20)
)
# Patients per observation-fetch task when fanning out to Celery workers.
MIGRATION_BATCH_SIZE = int(os.environ.get("MIGRATION_BATCH_SIZE", 5))

# Celery. Eager mode (default) executes tasks inline so no broker is needed;
# set CELERY_TASK_ALWAYS_EAGER=false and run Redis + a worker for true async.
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = (
    os.environ.get("CELERY_TASK_ALWAYS_EAGER", "true").lower() == "true"
)
