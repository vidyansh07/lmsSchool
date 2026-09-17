"""Base settings shared by every environment.

Environment-specific modules (``local``, ``development``, ``staging``,
``production``, ``test``) import from here and only override what genuinely
differs. Defaults in this file are the *secure* ones; relaxations live in the
development-oriented modules so that a missing override can never silently
weaken a deployed environment.
"""

from __future__ import annotations

import os
from pathlib import Path

import environ
from celery.schedules import crontab

from apps.common.storage import LOCAL_BACKEND, storage_settings

from .guards import forbid_sqlite

# --- Paths -----------------------------------------------------------------
# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BASE_DIR.parent

env = environ.Env()

# Load a local .env when present (developer convenience) -- but only when the
# caller hasn't already told us which environment to boot as. A deployed
# environment (staging/production) and a test run always export DJANGO_ENV
# explicitly before settings are imported; in that case a dev-only `.env`
# left over in the repo/worktree root (which itself hardcodes
# DJANGO_ENV=local, e.g. for a docker-compose stack) must never leak into
# the already-chosen environment. env.read_env() fills gaps via
# os.environ.setdefault(), so any key it also happens to set -- an empty
# MFA_ENCRYPTION_KEY, SECURE_HSTS_SECONDS=0 -- would silently win over
# config/settings/test.py's or hardened.py's own env.str()/env.int()
# defaults, since those only apply when the variable is entirely absent.
# Checking DJANGO_ENV as the runtime supplied it (before this file touches
# os.environ at all) keeps single-command local usage working -- it's
# normally unset or "local" there -- while a deployed/test process's own
# DJANGO_ENV is left completely alone.
_runtime_django_env = os.environ.get("DJANGO_ENV")
if _runtime_django_env in (None, "", "local"):
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
    "apps.organisation",
    "apps.authorization",
    "apps.configuration",
    "apps.policies",
    "apps.forms",
    "apps.students",
    "apps.trainers",
    "apps.courses",
    "apps.batches",
    "apps.sessions",
    "apps.attendance",
    "apps.dsr",
    "apps.assignments",
    "apps.assessments",
    "apps.academics",
    "apps.branding",
    "apps.projects",
    "apps.progress",
    "apps.performance",
    "apps.certificates",
    "apps.notifications",
    "apps.announcements",
    "apps.discussions",
    "apps.learning",
    "apps.reporting",
    "apps.questions",
    "apps.exams",
    "apps.enrollments",
    "apps.fees",
    "apps.work",
    "apps.automation",
    "apps.communication",
    "apps.activity",
    "apps.warnings",
    "apps.requirements",
    "apps.dashboards",
    "apps.search",
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
    # After authentication (ERP Phase 6, ADR-06): needs request.user and
    # request.session already resolved. See the middleware's own docstring.
    "apps.accounts.middleware.TouchSessionActivityMiddleware",
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
# A statement that runs longer than this is cancelled by PostgreSQL rather
# than holding a worker (22a: 15 s). Set per connection through libpq's
# `options`, so it applies to every query without touching the server config.
DATABASE_STATEMENT_TIMEOUT_MS = env.int("DATABASE_STATEMENT_TIMEOUT_MS", default=15_000)
if DATABASE_STATEMENT_TIMEOUT_MS > 0:
    DATABASES["default"]["OPTIONS"]["options"] = (
        f"-c statement_timeout={DATABASE_STATEMENT_TIMEOUT_MS}"
    )
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
    # Monday 08:00 local: every staff member's open warnings, once a week.
    "weekly-warnings-digest": {
        "task": "warnings.weekly_digest",
        "schedule": crontab(hour=8, minute=0, day_of_week="mon"),
        "options": {"expires": 3600},
    },
    # Activity engine (ERP Phase 9): OVERDUE/MISSED are system-only
    # transitions, so something has to notice the clock — this is that
    # something. Every ten minutes is frequent enough that "overdue" means
    # roughly what it says without sweeping the whole table every request.
    "work-mark-overdue": {
        "task": "work.mark_overdue",
        "schedule": env.int("WORK_OVERDUE_INTERVAL_SECONDS", default=600),
        "options": {"expires": 540},
    },
    "work-reminders": {
        "task": "work.reminders",
        "schedule": env.int("WORK_REMINDER_INTERVAL_SECONDS", default=600),
        "options": {"expires": 540},
    },
    # Announcements scheduling (ERP Phase 19): every minute, so a scheduled
    # notice reaches the board within roughly a minute of its `publish_at`
    # rather than on the next hourly-or-slower sweep.
    "announcements-publish-due": {
        "task": "announcements.publish_due",
        "schedule": 60,
        "options": {"expires": 50},
    },
    # Exports (ERP Phase 20): once a night, well outside business hours, so a
    # file's `SystemSetting.export_retention_days` lifetime is enforced daily
    # rather than left to accumulate in storage indefinitely.
    "reporting-expire-exports": {
        "task": "reporting.expire_exports",
        "schedule": crontab(hour=2, minute=30),
        "options": {"expires": 3600},
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
        # Per-IP request throttle on the OTP endpoints (SECURITY_DECISIONS
        # "Rate limiting"). Separate from — and cheaper to evaluate than —
        # the per-user/per-IP hourly send caps `apps.accounts.otp` itself
        # enforces; this one just bounds raw request volume at the endpoint.
        "otp": env.str("THROTTLE_RATE_OTP", default="5/min"),
        # Public certificate verification. A 160-bit code is not
        # brute-forceable, so this bounds bulk checking of a leaked list
        # rather than guessing.
        "certificate_verification": env.str("THROTTLE_RATE_VERIFY", default="30/min"),
        # Global search (ERP Phase 11): every authenticated caller holds the
        # capability, so the rate limit is what keeps a command palette's
        # keystrokes from turning into unbounded query volume across ten
        # scoped sources.
        "search": env.str("THROTTLE_RATE_SEARCH", default="30/min"),
        # Communication centre (ERP Phase 19): manual send and a template's
        # test-send. Both are per-account, low-frequency, deliberate acts
        # (never a keystroke-driven UI), so the rate stays modest.
        "communication": env.str("THROTTLE_RATE_COMMUNICATION", default="20/min"),
    },
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
}

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=False)

# Fake demo/seed data may only be created in environments that opt in.
ALLOW_DEMO_SEED = False

#: ERP Phase 1 (ADR-01): read role → permission grants from the database. Off
#: means the code matrix alone decides, which is the rollback switch.
DYNAMIC_ROLES_ENABLED = env.bool("DYNAMIC_ROLES_ENABLED", default=True)

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
        "PermissionScopeEnum": "apps.authorization.models.PermissionScope.choices",
        "RoleStatusEnum": "apps.authorization.models.RoleStatus.choices",
        # `Permission.category` was the only field named `category` with no
        # override before ERP Phase 9 added a second (`ActivityType.category`,
        # below) — one unresolved choice set of a given name never collides
        # with anything, so this one had gone unnoticed until it had company.
        "PermissionCategoryEnum": "apps.authorization.models.PermissionCategory.choices",
        "PolicyScopeEnum": "apps.policies.models.PolicyScope.choices",
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
        # The fourth choice set on a field named `kind`. Without the override
        # drf-spectacular resolves the collision to something like `Kind8d2Enum`
        # — a name derived from a hash, which would reach a generated client and
        # mean nothing to whoever read it.
        "BatchKindEnum": "apps.batches.models.BatchKind.choices",
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
        # Two fields named `method` (StepUpSerializer, MfaVerifySerializer)
        # share this one choice set (ERP Phase 5, ADR-05); without the
        # override drf-spectacular sees two divergent auto-generated names
        # for what is the same enum.
        "MfaMethodEnum": "apps.accounts.mfa.MfaMethod.choices",
        # `FeePayment.method` was the only field named `method` before the
        # override above; adding a second, differently-shaped `method` enum
        # to the schema exposed a pre-existing ambiguity — `method` is used
        # by more than one fee-related component — that happened to resolve
        # cleanly by luck while it was the only choice set of that name.
        "PaymentMethodEnum": "apps.fees.models.PaymentMethod.choices",
        # ERP Phase 9: the third choice set on a field named `category`
        # (`Permission.category` and `AssessmentCategory`/`NotificationCategory`
        # already have their own overrides above).
        "ActivityCategoryEnum": "apps.work.models.ActivityCategory.choices",
        # ERP Phase 12: `PerformanceReview.status` is the second choice set on
        # a field named literally `status` with no other context to
        # disambiguate it (unlike `BatchStatus`/`EnrollmentStatus`/etc, whose
        # fields are not simply called `status`) — the same "second one
        # exposes a pre-existing ambiguity" shape as `PaymentMethodEnum` above.
        "ReviewStatusEnum": "apps.performance.models.ReviewStatus.choices",
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

# MFA (ERP Phase 5, ADR-05). Fernet key encrypting a TOTP device's secret at
# rest (apps.accounts.mfa). No usable default here — an empty string fails
# closed the moment a TOTP call is actually made (apps.accounts.mfa._fernet)
# — and no default at all in a deployed environment (see
# config/settings/hardened.py's require_setting call), matching the
# "no defaults for secrets" rule in docs/environments.md. local/test each set
# a fixed, clearly-labelled placeholder key of their own.
MFA_ENCRYPTION_KEY = env.str("MFA_ENCRYPTION_KEY", default="")

# --- WhatsApp (ERP Phase 19, ADR-12) ----------------------------------------
# Optional integration, gated on presence exactly like `SENTRY_DSN` above:
# `apps.communication.providers.get_provider` returns the Null provider
# (always "not configured, skipped") until an access token and phone number
# id are both set, and never fails at import time either way.
WHATSAPP_ACCESS_TOKEN = env.str("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = env.str("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_API_BASE_URL = env.str("WHATSAPP_API_BASE_URL", default="https://graph.facebook.com/v19.0")
# The webhook's own authentication (it is deliberately not session-based —
# see `apps.communication.webhooks`): `WHATSAPP_APP_SECRET` signs the POST
# body (`X-Hub-Signature-256`, the Meta Cloud API's own convention);
# `WHATSAPP_WEBHOOK_VERIFY_TOKEN` answers the provider's one-time GET
# handshake. An empty value fails every verification closed — there is no
# "accept anything" fallback for either.
WHATSAPP_APP_SECRET = env.str("WHATSAPP_APP_SECRET", default="")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = env.str("WHATSAPP_WEBHOOK_VERIFY_TOKEN", default="")
