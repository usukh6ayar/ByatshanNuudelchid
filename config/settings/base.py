"""
Base settings. Every value comes from the environment — RFP §14, §690.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

# ---------------------------------------------------------------- Apps

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "simple_history",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.tenants",
    "apps.children",
    "apps.portfolio",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

# ---------------------------------------------------------------- Database
# RFP §14 — SQLite is not permitted in production

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- Auth

AUTH_USER_MODEL = "accounts.User"

# RFP §3.1 — teachers log in by username or email, guardians by phone or email
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.MultiIdentifierBackend",
]

# The approved design states the rules on screen (8+ characters, upper case,
# lower case, digit), so RFP §21.15 makes them part of the acceptance surface.
# The shorter minimum is offset by the character-class requirement and the
# §3.1 lockout below.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "apps.accounts.validators.PasswordComplexityValidator"},
]

LOGIN_URL = "accounts:login"
# "/" is the role-based landing view, which forwards to the right screen.
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "accounts:login"

# RFP §3.1 — throttle repeated failed logins
LOGIN_MAX_ATTEMPTS = env.int("LOGIN_MAX_ATTEMPTS", default=5)
LOGIN_LOCKOUT_MINUTES = env.int("LOGIN_LOCKOUT_MINUTES", default=15)

# ---------------------------------------------------------------- Locale

LANGUAGE_CODE = "mn"          # RFP §611 — the interface is in Mongolian
TIME_ZONE = "Asia/Ulaanbaatar"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- Static & media

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# ⚠ MEDIA_URL is deliberately unset.
# Child photos are NEVER served by Django's static file handling.
# Every file goes through /media/<uuid>/<variant>/ → permission check → signed URL.
# RFP §4.4, §15, §21.10

MEDIA_SIGNED_URL_TTL = env.int("MEDIA_SIGNED_URL_TTL", default=300)
MAX_UPLOAD_SIZE_MB = env.int("MAX_UPLOAD_SIZE_MB", default=25)
REPORT_RETENTION_DAYS = env.int("REPORT_RETENTION_DAYS", default=30)

# ---------------------------------------------------------------- Celery
# RFP §549 — slow work never happens inside a request

CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# ---------------------------------------------------------------- Security
# RFP §15

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False        # read by JS for the HTMX header
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# ---------------------------------------------------------------- Logging
# RFP §656

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"],
                               "propagate": False},
        # These two set their own loggers to DEBUG and emit several hundred
        # lines per PDF render, burying everything else.
        "fontTools": {"level": "WARNING", "handlers": ["console"],
                      "propagate": False},
        "weasyprint": {"level": "WARNING", "handlers": ["console"],
                       "propagate": False},
        "apps": {"level": "DEBUG" if DEBUG else "INFO", "handlers": ["console"],
                 "propagate": False},
    },
}
