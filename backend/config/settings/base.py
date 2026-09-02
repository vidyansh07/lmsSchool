"""Base settings shared by every environment.

Environment-specific modules (``local``, ``development``, ``staging``,
``production``, ``test``) import from here and only override what genuinely
differs. Defaults in this file are the *secure* ones; relaxations live in the
development-oriented modules so that a missing override can never silently
weaken a deployed environment.
"""

from __future__ import annotations

from pathlib import Path

import environ

from apps.common.storage import LOCAL_BACKEND, storage_settings

from .guards import forbid_sqlite

# --- Paths -----------------------------------------------------------------
# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BASE_DIR.parent

env = environ.Env()

# Load a local .env when present (developer convenience). Deployed environments
# inject real variables into the process environment instead.
for candidate in (BASE_DIR / ".env", REPO_ROOT / ".env"):
    if candidate.is_file():
        env.read_env(str(candidate))
        break

# --- Core ------------------------------------------------------------------
# Substring that marks a key as a development placeholder. Not a credential:
# deployed environments refuse to boot with any key containing it.
DEV_SECRET_KEY_MARKER = "insecure-development-key"  # nosec B105  # noqa: S105

SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
ROOT_URLCONF = "config.urls"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# --- Applications ----------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    # Registers PostgreSQL-specific lookups used by ArrayField queries.
    "django.contrib.postgres",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.students",
    "apps.trainers",
    "apps.courses",
    "apps.batches",
    "apps.sessions",
    "apps.attendance",
    "apps.assignments",
    "apps.assessments",
    "apps.academics",
    "apps.projects",
    "apps.progress",
    "apps.certificates",
    "apps.notifications",
    "apps.announcements",
    "apps.discussions",
    "apps.learning",
    "apps.reporting",
    "apps.questions",
    "apps.exams",
    "apps.enrollments",
    "apps.dashboards",
    "apps.audit",
    "apps.health",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    # RequestID first so every downstream log line and error envelope can be
    # correlated, including responses produced by the security middleware.
    "apps.common.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.SecurityHeadersMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

# --- Database --------------------------------------------------------------
# A single DATABASE_URL is the source of truth so that every environment is
# configured the same way and credentials never live in source control.
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://grras:grras@localhost:5432/grras_lms",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["ATOMIC_REQUESTS"] = True  # transaction-safe by default
DATABASES["default"].setdefault("OPTIONS", {})
if env.bool("DATABASE_SSL_REQUIRE", default=False):
    DATABASES["default"]["OPTIONS"]["sslmode"] = "require"
forbid_sqlite(DATABASES)

# --- Cache -----------------------------------------------------------------
# Throttling counters and sessions live here. Local memory is fine for a single
# process; staging/production require a shared backend (see those modules).
CACHE_URL = env.str("CACHE_URL", default="")
CACHES = {
    "default": env.cache_url_config(CACHE_URL)
    if CACHE_URL
    else {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "grras-lms-local",
    }
}

# --- Authentication --------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Session strategy: first-party browser clients authenticate with Django's
# session cookie (HttpOnly + CSRF protected + server-side revocation).
# See docs/architecture.md "Authentication strategy" for the rationale and the
# planned token path for non-browser clients.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "grras_sessionid"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=12 * 60 * 60)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True  # sliding expiry for active users

CSRF_COOKIE_NAME = "grras_csrftoken"
CSRF_COOKIE_HTTPONLY = False  # the SPA must read it to echo it back in a header
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
CSRF_FAILURE_VIEW = "apps.common.views.csrf_failure"

# --- CORS ------------------------------------------------------------------
# Credentials are sent cross-origin, so a wildcard origin is never allowed.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (
    "accept",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-request-id",
    "x-requested-with",
)
CORS_EXPOSE_HEADERS = ("x-request-id",)

# --- Security headers ------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = False  # enabled per-environment; TLS terminates upstream
# X-Forwarded-Proto is only trustworthy behind a proxy that overwrites it.
# Trusting it here would let a client reaching the app directly claim HTTPS,
# so it is enabled in `hardened.py` only, and only when NUM_PROXIES > 0.
SECURE_PROXY_SSL_HEADER = None
SECURE_HSTS_SECONDS = 0  # enabled in staging/production only
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
# Applied by apps.common.middleware.SecurityHeadersMiddleware. The API returns
# JSON and the admin/docs pages are the only HTML surfaces, so the policy is
# restrictive by default and relaxed for the docs route only.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self'; object-src 'none'; img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; script-src 'self'"
)
PERMISSIONS_POLICY = "geolocation=(), microphone=(), camera=(), interest-cohort=()"

DATA_UPLOAD_MAX_MEMORY_SIZE = env.int("DATA_UPLOAD_MAX_MEMORY_SIZE", default=5 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000
# Uploads land outside the web root and are served through the application, so
# a future LMS upload feature cannot become an arbitrary file-serving hole.
FILE_UPLOAD_PERMISSIONS = 0o640

# --- Static & media --------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Where uploaded files live. Local disk in development, S3 in a deployed
# environment — chosen by configuration so no application code knows which.
# `apps.common.storage` documents why student files are private in both, and
# `config.settings.hardened` refuses to boot a configuration that would expose
# them.
# --- Background work -------------------------------------------------------
# Redis is already the cache; it is also the broker. Defaulting the broker to
# CACHE_URL means one running Redis serves both in development, while a
# deployment can point them at separate instances (a full cache eviction must
# not take the queue with it).
CELERY_BROKER_URL = env.str("CELERY_BROKER_URL", default=CACHE_URL)
# No result backend: every task here is fire-and-forget, and storing results
# would keep a copy of task arguments — recipient addresses among them — in
# Redis for no reader.
CELERY_TASK_IGNORE_RESULT = True
CELERY_RESULT_BACKEND = None
# Acknowledge after the work is done, one task at a time: a worker that dies
# mid-task has it redelivered rather than dropped. See `config/celery.py`.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=300)
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=240)
CELERY_TASK_DEFAULT_QUEUE = "grras"
CELERY_TIMEZONE = env.str("DJANGO_TIME_ZONE", default="Asia/Kolkata")
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# Without a broker there is nowhere to queue, so tasks run inline. Correct for
# a laptop, refused in a deployed environment by `config.settings.hardened`.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=not CELERY_BROKER_URL)
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BEAT_SCHEDULE = {
    # The outbox sweep. Individual sends are queued as they happen; this catches
    # the ones that failed and are due for another attempt, which is the only
    # path by which a message sent during a provider outage ever arrives.
    "retry-pending-email": {
        "task": "notifications.retry_pending_email",
        "schedule": env.int("EMAIL_RETRY_INTERVAL_SECONDS", default=300),
        "options": {"expires": 240},
    },
}

# Malware scanning for uploads. `disabled` until a scanner is provisioned;
# `apps.common.scanning` documents why the unavailable case fails closed.
UPLOAD_SCANNER = env.str("UPLOAD_SCANNER", default="disabled")
UPLOAD_SCAN_FAIL_OPEN = env.bool("UPLOAD_SCAN_FAIL_OPEN", default=False)

FILE_STORAGE_BACKEND = env.str("FILE_STORAGE_BACKEND", default=LOCAL_BACKEND)
AWS_STORAGE_BUCKET_NAME = env.str("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = env.str("AWS_S3_REGION_NAME", default="")
AWS_S3_ENDPOINT_URL = env.str("AWS_S3_ENDPOINT_URL", default="") or None
#: Signature lifetime for object URLs. Short: a signed URL is a bearer token.
AWS_QUERYSTRING_EXPIRE = env.int("AWS_QUERYSTRING_EXPIRE", default=300)
#: Credentials are read by boto3 from the environment or the instance role.
#: They are deliberately not named here so they cannot be written into a
#: settings file by accident.
S3_OPTIONS = {
    "bucket_name": AWS_STORAGE_BUCKET_NAME,
    "querystring_expire": AWS_QUERYSTRING_EXPIRE,
    "location": env.str("AWS_LOCATION", default="media"),
}
if AWS_S3_REGION_NAME:
    S3_OPTIONS["region_name"] = AWS_S3_REGION_NAME
if AWS_S3_ENDPOINT_URL:
    S3_OPTIONS["endpoint_url"] = AWS_S3_ENDPOINT_URL

STORAGES = {
    "default": storage_settings(FILE_STORAGE_BACKEND, S3_OPTIONS),
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

# --- I18N ------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env.str("DJANGO_TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# --- REST framework --------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework.authentication.SessionAuthentication",),
    # Deny by default: an endpoint must opt in to being public.
    "DEFAULT_PERMISSION_CLASSES": ("apps.common.permissions.IsActiveUser",),
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env.str("THROTTLE_RATE_ANON", default="60/min"),
        "user": env.str("THROTTLE_RATE_USER", default="600/min"),
        "auth": env.str("THROTTLE_RATE_AUTH", default="10/min"),
        "burst": env.str("THROTTLE_RATE_BURST", default="20/min"),
        # Public certificate verification. A 160-bit code is not
        # brute-forceable, so this bounds bulk checking of a leaked list
        # rather than guessing.
        "certificate_verification": env.str("THROTTLE_RATE_VERIFY", default="30/min"),
    },
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
}

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=False)

# Fake demo/seed data may only be created in environments that opt in.
ALLOW_DEMO_SEED = False

# --- Course content access -------------------------------------------------
# Non-preview lesson content, resources and video require a live enrolment.
# On by default from Phase 3, now that enrolment records exist to check against.
# It stays configurable so a demo or an open-catalogue deployment can drop the
# gate deliberately, rather than by editing the access layer.
COURSE_CONTENT_REQUIRES_ENROLMENT = env.bool("COURSE_CONTENT_REQUIRES_ENROLMENT", default=True)

SPECTACULAR_SETTINGS = {
    "TITLE": "Grras LMS API",
    "DESCRIPTION": (
        "Learning Management System API. Phase 0 exposes the platform "
        "foundation only: health, authentication and user administration."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v[0-9]+",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "ENUM_NAME_OVERRIDES": {
        "UserRoleEnum": "apps.accounts.roles.UserRole.choices",
        "FeeStatusEnum": "apps.students.models.FeeStatus.choices",
        "QualificationEnum": "apps.students.models.Qualification.choices",
        "PublishStatusEnum": "apps.courses.models.PublishStatus.choices",
        "CourseVisibilityEnum": "apps.courses.models.CourseVisibility.choices",
        "CourseDifficultyEnum": "apps.courses.models.CourseDifficulty.choices",
        "LessonContentTypeEnum": "apps.courses.models.LessonContentType.choices",
        "ContentStatusEnum": "apps.courses.models.CONTENT_STATUS_CHOICES",
        "CourseAuthorRoleEnum": "apps.courses.models.CourseAuthorRole.choices",
        "ResourceKindEnum": "apps.courses.models.ResourceKind.choices",
        "VideoProviderEnum": "apps.courses.models.VideoProvider.choices",
        "VideoStatusEnum": "apps.courses.models.VideoStatus.choices",
        "BatchStatusEnum": "apps.batches.models.BatchStatus.choices",
        "WeekdayEnum": "apps.batches.models.Weekday.choices",
        "EnrollmentStatusEnum": "apps.enrollments.models.EnrollmentStatus.choices",
        "SessionStatusEnum": "apps.sessions.models.SessionStatus.choices",
        "AttendanceStatusEnum": "apps.attendance.models.AttendanceStatus.choices",
        # Assignments and assessments share one lifecycle vocabulary, so they
        # share one schema enum. Two names for an identical choice set is a
        # drf-spectacular error, and would also be a lie about the API.
        "AcademicLifecycleEnum": "apps.assignments.models.AssignmentStatus.choices",
        "SubmissionKindEnum": "apps.assignments.models.SubmissionKind.choices",
        "SubmissionStatusEnum": "apps.assignments.models.SubmissionStatus.choices",
        "AssessmentCategoryEnum": "apps.assessments.models.AssessmentCategory.choices",
        "AssessmentDeliveryEnum": "apps.assessments.models.AssessmentDelivery.choices",
        "ResultSourceEnum": "apps.assessments.models.ResultSource.choices",
        "ImportStatusEnum": "apps.assessments.models.ImportStatus.choices",
        "ProjectKindEnum": "apps.projects.models.ProjectKind.choices",
        "ProjectWorkStatusEnum": "apps.projects.models.WorkStatus.choices",
        "QuestionTypeEnum": "apps.questions.models.QuestionType.choices",
        "DifficultyEnum": "apps.questions.models.Difficulty.choices",
        "AttemptStatusEnum": "apps.exams.models.AttemptStatus.choices",
        "DeliveryModeEnum": "apps.batches.models.DeliveryMode.choices",
        "CompletionStatusEnum": "apps.progress.models.CompletionStatus.choices",
        "CertificateStatusEnum": "apps.certificates.models.CertificateStatus.choices",
        "NotificationKindEnum": "apps.notifications.models.NotificationKind.choices",
        "NotificationCategoryEnum": "apps.notifications.models.NotificationCategory.choices",
        "AudienceEnum": "apps.announcements.models.Audience.choices",
        "AnnouncementStatusEnum": "apps.announcements.models.AnnouncementStatus.choices",
        "AcademicEventKindEnum": "apps.academics.models.AcademicEventKind.choices",
        "ImportKindEnum": "apps.reporting.models.ImportKind.choices",
        "BulkImportStatusEnum": "apps.reporting.models.BulkImportStatus.choices",
        "LessonProgressStatusEnum": "apps.enrollments.models.LessonProgressStatus.choices",
    },
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": False},
}

# --- Logging ---------------------------------------------------------------
LOG_LEVEL = env.str("DJANGO_LOG_LEVEL", default="INFO")
LOG_FORMAT = env.str("DJANGO_LOG_FORMAT", default="console")  # console | json

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.common.logging.RequestIDFilter"},
        "redact_secrets": {"()": "apps.common.logging.RedactSecretsFilter"},
    },
    "formatters": {
        "console": {
            "format": "%(asctime)s %(levelname)-8s %(name)s [%(request_id)s] %(message)s",
        },
        "json": {"()": "apps.common.logging.JSONFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT if LOG_FORMAT in ("console", "json") else "console",
            "filters": ["request_id", "redact_secrets"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Dedicated channels so security/audit events can be shipped separately.
        "grras.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "grras.audit": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "grras.calendar": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# --- Error reporting -------------------------------------------------------
SENTRY_DSN = env.str("SENTRY_DSN", default="")
SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0)

# --- Project metadata ------------------------------------------------------
PROJECT_NAME = "Grras LMS"
APP_VERSION = env.str("APP_VERSION", default="0.1.0")

# --- Email -----------------------------------------------------------------
# Password reset and email verification are the only mail this phase sends.
# The console backend is the default so a misconfigured environment prints mail
# instead of silently failing; deployed environments switch to SMTP.
EMAIL_BACKEND = env.str("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env.str("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
EMAIL_SUBJECT_PREFIX = env.str("EMAIL_SUBJECT_PREFIX", default="[Grras LMS] ")
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="no-reply@grras.local")

# Base URL used to build links inside emails. It must point at the frontend,
# not the API, because the user clicks it in a browser.
FRONTEND_BASE_URL = env.str("FRONTEND_BASE_URL", default="http://localhost:3000").rstrip("/")
FRONTEND_PASSWORD_RESET_PATH = "/reset-password"  # nosec B105  # noqa: S105 - a URL path
FRONTEND_EMAIL_VERIFY_PATH = "/verify-email"

# Token lifetimes, surfaced here so the values in emails and in the model stay
# in step. Reset tokens are short-lived because they grant account takeover;
# verification links are weaker and may live longer.
AUTH_TOKEN_RESET_TTL_HOURS = env.int("AUTH_TOKEN_RESET_TTL_HOURS", default=1)
AUTH_TOKEN_VERIFICATION_TTL_DAYS = env.int("AUTH_TOKEN_VERIFICATION_TTL_DAYS", default=3)
