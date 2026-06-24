# config/settings/development.py
# =============================================================================
# Development Settings — AI Interviewer
# =============================================================================

from .base import *  # noqa: F401, F403
from .base import INSTALLED_APPS, MIDDLEWARE, REST_FRAMEWORK, CACHES, SIMPLE_JWT
from datetime import timedelta

# ─── Core ─────────────────────────────────────────────────────────────────────
DEBUG = True
ALLOWED_HOSTS = ["*"]
DJANGO_ENV = "development"

# ─── Apps & Middleware (فقط development) ─────────────────────────────────────
INSTALLED_APPS += [
    # "debug_toolbar",
    "django_extensions",        # shell_plus، graph_models، ...
]

# MIDDLEWARE += [
#     "debug_toolbar.middleware.DebugToolbarMiddleware",
# ]

# ─── Database ────────────────────────────────────────────────────────────────
# همون base ولی با logging کامل query ها
DATABASES["default"]["OPTIONS"]["options"] = (   # noqa: F405
    "-c statement_timeout=60000"                 # توی dev بیشتر صبر میکنیم
)

# ─── Cache ────────────────────────────────────────────────────────────────────
# توی development میتونیم dummy cache هم بذاریم
# ولی Redis رو نگه میداریم که رفتار production رو شبیه‌سازی کنیم
CACHES["default"]["OPTIONS"]["SOCKET_TIMEOUT"] = 10    # کمی relaxed‌تر

# ─── Email — فقط console ──────────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ─── REST Framework — development overrides ───────────────────────────────────
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",   # ← فقط dev
]

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon": "1000/hour",       # توی dev محدودیت نمیخوایم
    "user": "10000/hour",
    "otp":  "100/hour",
}

# ─── JWT — توی dev token ها بیشتر دوام میارن ──────────────────────────────────
SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]  = timedelta(days=1)
SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] = timedelta(days=30)

# ─── CORS — توی dev همه رو قبول میکنیم ───────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True

# ─── Debug Toolbar ────────────────────────────────────────────────────────────
INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
]

DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
    "SHOW_COLLAPSED": True,
    "SQL_WARNING_THRESHOLD": 100,    # query های بالای 100ms رو highlight میکنه
    "IS_RUNNING_TESTS": False,
}

DEBUG_TOOLBAR_PANELS = [
    "debug_toolbar.panels.history.HistoryPanel",
    "debug_toolbar.panels.versions.VersionsPanel",
    "debug_toolbar.panels.timer.TimerPanel",
    "debug_toolbar.panels.settings.SettingsPanel",
    "debug_toolbar.panels.headers.HeadersPanel",
    "debug_toolbar.panels.request.RequestPanel",
    "debug_toolbar.panels.sql.SQLPanel",            # ← مهم‌ترین
    "debug_toolbar.panels.staticfiles.StaticFilesPanel",
    "debug_toolbar.panels.templates.TemplatesPanel",
    "debug_toolbar.panels.cache.CachePanel",        # ← Redis hits/misses
    "debug_toolbar.panels.signals.SignalsPanel",
    "debug_toolbar.panels.logging.LoggingPanel",
    "debug_toolbar.panels.redirects.RedirectsPanel",
    "debug_toolbar.panels.profiling.ProfilingPanel",
]

# ─── Django Extensions ────────────────────────────────────────────────────────
SHELL_PLUS = "ipython"
SHELL_PLUS_PRINT_SQL = True                  # هر query رو print میکنه

SHELL_PLUS_IMPORTS = [
    "from apps.users.models import User",
    "from apps.interviews.models import InterviewSession",
    "from apps.questions.models import Question",
    "from django.core.cache import cache",
    "from django.utils import timezone",
    "import json",
]

# graph_models برای دیدن ERD دیتابیس
GRAPH_MODELS = {
    "all_applications": True,
    "group_models": True,
    "output": "docs/erd.png",
}

# ─── Celery — توی dev همه چیز sync اجرا میشه (اختیاری) ───────────────────────
# اگه بخوای task ها رو بدون worker تست کنی uncomment کن:
# CELERY_TASK_ALWAYS_EAGER = True
# CELERY_TASK_EAGER_PROPAGATES = True

# ─── OTP — توی dev همیشه یه کد ثابت ─────────────────────────────────────────
OTP_DEV_BYPASS = True              # توی کد چک میشه: if settings.OTP_DEV_BYPASS
OTP_DEV_CODE   = "123456"          # کد ثابت برای تست

# ─── Logging overrides ────────────────────────────────────────────────────────
# query های دیتابیس رو هم لاگ میکنیم
LOGGING["loggers"]["django.db.backends"] = {    # noqa: F405
    "handlers": ["console"],
    "level": "DEBUG",
    "propagate": False,
}

# تمام app ها رو DEBUG میکنیم
for app in ["apps.users", "apps.interviews", "apps.questions", "apps.notifications"]:
    LOGGING["loggers"][app]["level"] = "DEBUG"  # noqa: F405