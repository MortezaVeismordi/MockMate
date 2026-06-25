# config/settings/testing.py
# =============================================================================
# Testing Settings — AI Interviewer
# =============================================================================

from .base import *  # noqa: F401, F403
from .base import (
    INSTALLED_APPS, MIDDLEWARE, REST_FRAMEWORK,
    CACHES, SIMPLE_JWT, LOGGING
)
from datetime import timedelta

# ─── Core ─────────────────────────────────────────────────────────────────────
DEBUG = False                      # production رفتار رو شبیه‌سازی میکنیم
DJANGO_ENV = "testing"

ALLOWED_HOSTS = ["*"]

# ─── Security — توی test نیازی نیست ──────────────────────────────────────────
SECRET_KEY = "test-secret-key-not-for-production-use-only-testing"  # noqa: S106

# ─── Database — سریع‌ترین حالت ممکن ──────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME":     os.environ.get("TEST_DB_NAME", "test_ai_interviewer"),  # noqa: F405
        "USER":     os.environ.get("DB_USER", "postgres"),                  # noqa: F405
        "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),              # noqa: F405
        "HOST":     os.environ.get("DB_HOST", "db"),                        # noqa: F405
        "PORT":     os.environ.get("DB_PORT", "5432"),                      # noqa: F405
        "TEST": {
            "NAME": "test_ai_interviewer",
            # هر test run یه دیتابیس تازه میسازه
            "CREATE_DB": True,
        },
        "OPTIONS": {
            "connect_timeout": 5,
            # توی test statement_timeout نمیخوایم
            # بعضی تست‌های پیچیده ممکنه بیشتر طول بکشه
        },
        # connection pooling توی test خاموش
        "CONN_MAX_AGE": 0,
    }
}

# ─── Cache — فقط LocMem برای سرعت ────────────────────────────────────────────
# توی test نیازی به Redis نداریم مگه integration test
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-default",
    },
    "otp": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-otp",
    },
    "rate_limit": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-rate-limit",
    },
}

# ─── Password Hashing — سریع‌ترین hasher ─────────────────────────────────────
# MD5 فقط برای test — production هرگز
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ─── Email — هیچی ارسال نمیشه ─────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ─── Media — tmp directory ───────────────────────────────────────────────────
import tempfile                                          # noqa: E402
MEDIA_ROOT = tempfile.mkdtemp()

# ─── Celery — همه چیز sync ───────────────────────────────────────────────────
CELERY_TASK_ALWAYS_EAGER    = True     # بدون worker اجرا میشه
CELERY_TASK_EAGER_PROPAGATES = True    # exception ها bubble up میشن

# ─── REST Framework — testing ─────────────────────────────────────────────────
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
    "apps.users.authentication.CustomJWTAuthentication",
]
# throttle رو خاموش میکنیم — تست‌ها throttle نمیخوان
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon": "1000/minute",
    "user": "1000/minute",
    "otp": "1000/minute",
    "login": "1000/minute",
}

# ─── JWT — توی test token ها خیلی بیشتر دوام میارن ──────────────────────────
SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]  = timedelta(days=7)
SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] = timedelta(days=30)

# ─── OTP ─────────────────────────────────────────────────────────────────────
OTP_DEV_BYPASS  = True
OTP_DEV_CODE    = "123456"
OTP_EXPIRY_SECONDS  = 300          # توی test بیشتر وقت داریم
OTP_MAX_ATTEMPTS    = 10           # توی test سخت‌گیری نمیکنیم

# ─── Middleware — حذف موارد غیرضروری برای سرعت ───────────────────────────────
MIDDLEWARE = [
    m for m in MIDDLEWARE
    if m not in [
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        "django.middleware.security.SecurityMiddleware",
    ]
]

# ─── Logging — توی test فقط error ─────────────────────────────────────────────
# نمیخوایم test output با لاگ پر بشه
LOGGING["root"]["level"] = "ERROR"                      # noqa: F405

for _logger in LOGGING["loggers"].values():             # noqa: F405
    _logger["level"] = "ERROR"

# ─── Test Runner ──────────────────────────────────────────────────────────────
TEST_RUNNER = "django.test.runner.DiscoverTestRunner"

# parallel test برای سرعت بیشتر
# تعداد CPU core رو میگیره
import multiprocessing                                   # noqa: E402
TEST_RUNNER_PARALLEL = multiprocessing.cpu_count()

# ─── Fixtures ────────────────────────────────────────────────────────────────
FIXTURE_DIRS = [
    BASE_DIR / "tests" / "fixtures",                    # noqa: F405
]

# ─── Factory Boy — برای test data ─────────────────────────────────────────────
# اگه از factory_boy استفاده میکنی
FACTORY_BOY_RESET_SEQUENCES = True

# ─── Coverage ────────────────────────────────────────────────────────────────
# این تنظیمات رو .coveragerc هم میخونه
COVERAGE_CONFIG = {
    "run": {
        "source": ["apps"],
        "omit": [
            "*/migrations/*",
            "*/tests/*",
            "*/admin.py",
            "manage.py",
        ],
    },
    "report": {
        "fail_under": 80,          # زیر ۸۰٪ coverage = fail
        "show_missing": True,
    },
}