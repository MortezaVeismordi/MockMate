# config/settings/production.py
# =============================================================================
# Production Settings — AI Interviewer
# =============================================================================
import logging
import os
from datetime import timedelta

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from .base import *  # noqa: F401, F403
from .base import CACHES, CELERY_TASK_ROUTES, INSTALLED_APPS, LOGGING, MIDDLEWARE, REST_FRAMEWORK, SIMPLE_JWT

# ─── Core ─────────────────────────────────────────────────────────────────────
DEBUG = False
DJANGO_ENV = "production"

ALLOWED_HOSTS = os.environ["ALLOWED_HOSTS"].split(",")   # noqa: F405

# ─── Security ────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ["SECRET_KEY"]                    # noqa: F405

# HTTPS
SECURE_SSL_REDIRECT                  = True
SECURE_PROXY_SSL_HEADER              = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS                  = 31536000          # 1 سال
SECURE_HSTS_INCLUDE_SUBDOMAINS       = True
SECURE_HSTS_PRELOAD                  = True

# Cookies
SESSION_COOKIE_SECURE                = True
SESSION_COOKIE_HTTPONLY              = True
SESSION_COOKIE_SAMESITE              = "Strict"
CSRF_COOKIE_SECURE                   = True
CSRF_COOKIE_HTTPONLY                 = True
CSRF_COOKIE_SAMESITE                 = "Strict"
CSRF_TRUSTED_ORIGINS                 = os.environ.get(   # noqa: F405
    "CSRF_TRUSTED_ORIGINS", ""
).split(",")

# ─── Database — production tuning ─────────────────────────────────────────────
DATABASES["default"].update({                            # noqa: F405
    "CONN_MAX_AGE": 300,
    "CONN_HEALTH_CHECKS": True,
    "OPTIONS": {
        "connect_timeout": 10,
        "options": "-c statement_timeout=10000",         # 10s — سخت‌گیرانه‌تر
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
})

# ─── Cache — production tuning ────────────────────────────────────────────────
CACHES["default"]["OPTIONS"].update({
    "MAX_CONNECTIONS": 100,
    "SOCKET_CONNECT_TIMEOUT": 3,
    "SOCKET_TIMEOUT": 3,
})

# ─── NOTIFICATION ────────────────────────────────────────────────────────────────────
NOTIFICATION_PROVIDERS = {
    "sms": "apps.notifications.providers.sms.KavenegarSMSProvider",
    "email": "apps.notifications.providers.email.SmtpEmailProvider",
}

# کلیدهای اجباری کاوه‌نگار در پروداکشن
KAVENEGAR_API_KEY = os.environ["KAVENEGAR_API_KEY"]  # بدون دیفالت تا در صورت نبودن Fail Fast شود
KAVENEGAR_SENDER  = os.environ.get("KAVENEGAR_SENDER", "")

# ساختار SMTP واقعی شما بدون تغییر باقی می‌ماند
EMAIL_BACKEND       = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST          = os.environ["EMAIL_HOST"]
EMAIL_PORT          = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER     = os.environ["EMAIL_HOST_USER"]
EMAIL_HOST_PASSWORD = os.environ["EMAIL_HOST_PASSWORD"]
EMAIL_USE_TLS       = True
EMAIL_TIMEOUT       = 10
DEFAULT_FROM_EMAIL  = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "noreply@ai-interviewer.com"
)

# ─── Static Files — WhiteNoise ────────────────────────────────────────────────
INSTALLED_APPS = ["whitenoise.runserver_nostatic"] + INSTALLED_APPS

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ─── REST Framework — production ──────────────────────────────────────────────
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",             # فقط JSON
]

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon": "30/hour",
    "user": "500/hour",
    "otp":  "5/hour",                                    # سخت‌گیرانه
}

# ─── JWT — production ────────────────────────────────────────────────────────
SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]  = timedelta(minutes=15)   # کوتاه‌تر
SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] = timedelta(days=3)

# ─── CORS ─────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = os.environ["CORS_ALLOWED_ORIGINS"].split(",")  # noqa: F405
CORS_ALLOW_ALL_ORIGINS = False

# ─── Celery — production tuning ───────────────────────────────────────────────
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 3600,
    "max_retries": 3,
    "interval_start": 0,
    "interval_step": 0.2,
    "interval_max": 0.5,
}

CELERY_WORKER_PREFETCH_MULTIPLIER = 1        # جلوگیری از task انباشته شدن
CELERY_TASK_ACKS_LATE             = True     # task بعد از موفقیت ack میشه
CELERY_TASK_REJECT_ON_WORKER_LOST = True     # اگه worker crash کرد، retry

CELERY_TASK_ROUTES.update({
    "apps.notifications.tasks.send_notification_task": {"queue": "notifications", "priority": 9},
    "apps.interviews.tasks.evaluate":                  {"queue": "interviews",    "priority": 5},
})

# ─── Sentry ───────────────────────────────────────────────────────────────────
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")           # noqa: F405

if SENTRY_DSN:
    sentry_logging = LoggingIntegration(
        level=logging.INFO,
        event_level=logging.ERROR,        # فقط ERROR به بالا رو Sentry میگیره
    )

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(
                transaction_style="url",
                middleware_spans=True,
                signals_spans=True,
                cache_spans=True,
            ),
            CeleryIntegration(
                monitor_beat_tasks=True,
                propagate_traces=True,
            ),
            RedisIntegration(),
            sentry_logging,
        ],

        traces_sample_rate=float(
            os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")  # noqa: F405
        ),
        profiles_sample_rate=float(
            os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1")  # noqa: F405
        ),

        environment="production",
        release=os.environ.get("APP_VERSION", "unknown"),  # noqa: F405

        # اطلاعات حساس رو فیلتر میکنه
        send_default_pii=False,
        before_send=_filter_sensitive_data,  # noqa: F405
    )

# ─── Sentry sensitive data filter ────────────────────────────────────────────
def _filter_sensitive_data(event, hint):
    """
    قبل از ارسال به Sentry، داده‌های حساس رو پاک میکنه
    """
    sensitive_keys = {
        "password", "token", "secret", "otp",
        "authorization", "credit_card", "phone"
    }

    def _scrub(obj):
        if isinstance(obj, dict):
            return {
                k: "***FILTERED***" if k.lower() in sensitive_keys else _scrub(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_scrub(i) for i in obj]
        return obj

    if "request" in event:
        event["request"] = _scrub(event["request"])

    return event

# ─── Logging — production overrides ──────────────────────────────────────────
# همه appها رو INFO میکنیم (نه DEBUG)
for _app in ["apps.users", "apps.interviews", "apps.questions", "apps.notifications"]:
    LOGGING["loggers"][_app]["level"] = "INFO"           # noqa: F405

# file handler اضافه میکنیم به root
LOGGING["root"]["handlers"] = [                          # noqa: F405
    "console",
    "file_general",
    "file_error",
]

# ─── Performance ──────────────────────────────────────────────────────────────
# Data Upload
DATA_UPLOAD_MAX_MEMORY_SIZE     = 5242880    # 5MB
DATA_UPLOAD_MAX_NUMBER_FIELDS   = 100
FILE_UPLOAD_MAX_MEMORY_SIZE     = 5242880    # 5MB

# ─── API Docs — توی production خاموش ─────────────────────────────────────────
SPECTACULAR_SETTINGS = {                                 # noqa: F405
    **SPECTACULAR_SETTINGS,                              # noqa: F405
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
}

# ─── Health Check ────────────────────────────────────────────────────────────
HEALTH_CHECK = {
    "DISK_USAGE_MAX": 90,        # درصد
    "MEMORY_MIN": 100,           # MB
}
