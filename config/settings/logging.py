# config/settings/logging.py
# =============================================================================
# Logging Configuration — AI Interviewer
# =============================================================================

import os
from pathlib import Path

# Derive logs directory relative to the project root (config/settings/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = _PROJECT_ROOT / "logs"
try:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

DJANGO_ENV = os.environ.get("DJANGO_ENV", "development")

# ─── Custom Formatter با رنگ برای development ─────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    # ─── Filters ─────────────────────────────────────────────────────────────
    "filters": {
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    # ─── Formatters ──────────────────────────────────────────────────────────
    "formatters": {
        # توی development — خوانا و رنگی
        "verbose_dev": {
            "format": (
                "\033[36m{asctime}\033[0m | "  # cyan — زمان
                "\033[1m{levelname:<8}\033[0m | "  # bold — level
                "\033[35m{name}\033[0m | "  # magenta — logger name
                "\033[33m{module}:{lineno}\033[0m"  # yellow — فایل:خط
                " | {message}"
            ),
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        # توی production — JSON برای log aggregator ها (Datadog, ELK, ...)
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": (
                "%(asctime)s %(levelname)s %(name)s "
                "%(module)s %(lineno)d %(message)s "
                "%(exc_info)s %(stack_info)s"
            ),
            "datefmt": "%Y-%m-%dT%H:%M:%SZ",
        },
        # ساده — برای فایل‌های لاگ
        "standard": {
            "format": "{asctime} | {levelname:<8} | {name} | {module}:{lineno} | {message}",
            "style": "{",
            "datefmt": "%Y-%m-%dT%H:%M:%SZ",
        },
        # خیلی ساده — برای django.server
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    # ─── Handlers ────────────────────────────────────────────────────────────
    "handlers": {
        # stdout — همیشه هست (Docker این رو میخونه)
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "verbose_dev" if DJANGO_ENV == "development" else "json",
        },
        # stderr — فقط برای error و بالاتر
        "console_error": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "level": "ERROR",
            "formatter": "json",
        },
        # فایل — همه لاگ‌ها با rotation
        "file_general": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": LOGS_DIR / "general.log",
            "when": "midnight",
            "backupCount": 30,  # ۳۰ روز نگه میداره
            "encoding": "utf-8",
            "formatter": "standard",
        },
        # فایل — فقط errorها
        "file_error": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": LOGS_DIR / "error.log",
            "when": "midnight",
            "backupCount": 90,  # errorها رو ۹۰ روز نگه میداره
            "encoding": "utf-8",
            "level": "ERROR",
            "formatter": "standard",
        },
        # فایل — فقط security events (login، OTP، ...)
        "file_security": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": LOGS_DIR / "security.log",
            "when": "midnight",
            "backupCount": 180,  # security لاگ‌ها رو ۶ ماه نگه میداره
            "encoding": "utf-8",
            "formatter": "standard",
        },
        # فایل — Celery tasks
        "file_celery": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": LOGS_DIR / "celery.log",
            "when": "midnight",
            "backupCount": 30,
            "encoding": "utf-8",
            "formatter": "standard",
        },
        # null handler — برای خاموش کردن لاگرهای پرسروصدا
        "null": {
            "class": "logging.NullHandler",
        },
    },
    # ─── Loggers ─────────────────────────────────────────────────────────────
    "loggers": {
        # ─── Django core ─────────────────────────────────────────────────────
        "django": {
            "handlers": ["console", "file_general"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file_error"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "file_security", "file_error"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.db.backends": {
            # توی development query ها رو لاگ میکنه
            # توی production خاموشه (پرسروصداست)
            "handlers": ["console"] if DJANGO_ENV == "development" else ["null"],
            "level": "DEBUG" if DJANGO_ENV == "development" else "CRITICAL",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # ─── Apps ────────────────────────────────────────────────────────────
        "apps.users": {
            "handlers": ["console", "file_general", "file_security"],
            "level": "DEBUG" if DJANGO_ENV == "development" else "INFO",
            "propagate": False,
        },
        "apps.interviews": {
            "handlers": ["console", "file_general"],
            "level": "DEBUG" if DJANGO_ENV == "development" else "INFO",
            "propagate": False,
        },
        "apps.questions": {
            "handlers": ["console", "file_general"],
            "level": "DEBUG" if DJANGO_ENV == "development" else "INFO",
            "propagate": False,
        },
        "apps.notifications": {
            "handlers": ["console", "file_general", "file_security"],
            "level": "DEBUG" if DJANGO_ENV == "development" else "INFO",
            "propagate": False,
        },
        # ─── Celery ──────────────────────────────────────────────────────────
        "celery": {
            "handlers": ["console", "file_celery"],
            "level": "INFO",
            "propagate": False,
        },
        "celery.task": {
            "handlers": ["console", "file_celery"],
            "level": "DEBUG" if DJANGO_ENV == "development" else "INFO",
            "propagate": False,
        },
        # ─── Third party های پرسروصدا ─────────────────────────────────────────
        "urllib3": {"handlers": ["null"], "propagate": False},
        "asyncio": {"handlers": ["null"], "propagate": False},
    },
    # ─── Root Logger ─────────────────────────────────────────────────────────
    # هر چیزی که logger مشخص نداشته باشه اینجا میاد
    "root": {
        "handlers": ["console", "file_general", "file_error"],
        "level": "WARNING",
    },
}
