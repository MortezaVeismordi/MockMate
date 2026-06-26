import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class UsersConfig(AppConfig):
    """
    تنظیمات اپلیکیشن Users.

    مسئولیت‌ها:
        - مدیریت Custom User Model
        - احراز هویت با OTP
        - مدیریت پروفایل کاربران
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    verbose_name = _("مدیریت کاربران")
    verbose_name_plural = _("مدیریت کاربران")

    def ready(self):
        """
        هنگام آماده شدن اپلیکیشن اجرا میشه.

        کارها:
            1. ثبت سیگنال‌ها
            2. ثبت System Checks سفارشی
        """
        self._register_signals()
        self._register_checks()

        logger.debug("Users app ready.")

    # ── Private Methods ────────────────────────────

    @staticmethod
    def _register_signals():
        """ایمپورت و ثبت سیگنال‌های مربوط به User و OTP."""
        try:
            import apps.users.signals  # noqa: F401
        except ImportError as exc:
            logger.error("Failed to import users signals: %s", exc)

    @staticmethod
    def _register_checks():
        """
        ثبت بررسی‌های سفارشی جنگو.
        موقع اجرای `python manage.py check` اجرا میشن.
        """
        from django.core.checks import Tags, register

        @register(Tags.models)
        def check_auth_user_model(app_configs, **kwargs):
            """
            چک میکنه AUTH_USER_MODEL درست تنظیم شده باشه.
            """
            from django.conf import settings
            errors = []

            expected = "users.CustomUser"
            actual = getattr(settings, "AUTH_USER_MODEL", None)

            if actual != expected:
                from django.core.checks import Error
                errors.append(
                    Error(
                        f"AUTH_USER_MODEL باید '{expected}' باشد، "
                        f"ولی '{actual}' تنظیم شده.",
                        hint=f'AUTH_USER_MODEL = "{expected}" را در settings قرار دهید.',
                        obj=settings,
                        id="users.E001",
                    )
                )

            return errors

        @register(Tags.security)
        def check_otp_settings(app_configs, **kwargs):
            """
            چک میکنه تنظیمات OTP معقول باشن.
            """
            from django.conf import settings
            from django.core.checks import Warning

            warnings = []

            # ── OTP_EXPIRE_MINUTES ─────────────────
            expire = getattr(settings, "OTP_EXPIRE_MINUTES", 2)
            if expire > 5:
                warnings.append(
                    Warning(
                        f"OTP_EXPIRE_MINUTES = {expire} خیلی زیاده (پیشنهاد: ≤ 5).",
                        hint="مدت اعتبار OTP رو کم کنید.",
                        id="users.W001",
                    )
                )
            if expire < 1:
                warnings.append(
                    Warning(
                        f"OTP_EXPIRE_MINUTES = {expire} خیلی کمه (حداقل: 1).",
                        hint="مدت اعتبار OTP رو افزایش بدید.",
                        id="users.W002",
                    )
                )

            # ── OTP_MAX_ATTEMPTS ───────────────────
            attempts = getattr(settings, "OTP_MAX_ATTEMPTS", 3)
            if attempts > 10:
                warnings.append(
                    Warning(
                        f"OTP_MAX_ATTEMPTS = {attempts} خیلی زیاده (پیشنهاد: ≤ 5).",
                        hint="تعداد تلاش مجاز رو کم کنید.",
                        id="users.W003",
                    )
                )

            # ── OTP_MAX_RESEND_PER_DAY ─────────────
            resend = getattr(settings, "OTP_MAX_RESEND_PER_DAY", 5)
            if resend > 20:
                warnings.append(
                    Warning(
                        f"OTP_MAX_RESEND_PER_DAY = {resend} خیلی زیاده (پیشنهاد: ≤ 10).",
                        hint="سقف ارسال روزانه رو کم کنید.",
                        id="users.W004",
                    )
                )

            # ── OTP_CODE_LENGTH ────────────────────
            length = getattr(settings, "OTP_CODE_LENGTH", 6)
            if length < 4:
                warnings.append(
                    Warning(
                        f"OTP_CODE_LENGTH = {length} خیلی کمه (حداقل: 4).",
                        hint="طول کد OTP رو افزایش بدید.",
                        id="users.W005",
                    )
                )

            return warnings

        @register(Tags.security)
        def check_jwt_settings(app_configs, **kwargs):
            """
            چک میکنه تنظیمات JWT درست باشن.
            """
            from django.conf import settings
            from django.core.checks import Error, Warning

            issues = []

            # چک وجود SIMPLE_JWT
            jwt_settings = getattr(settings, "SIMPLE_JWT", None)
            if jwt_settings is None:
                issues.append(
                    Error(
                        "SIMPLE_JWT در settings تعریف نشده.",
                        hint=(
                            "pip install djangorestframework-simplejwt\n"
                            "و SIMPLE_JWT را در settings تنظیم کنید."
                        ),
                        id="users.E002",
                    )
                )
                return issues

            # چک ROTATE_REFRESH_TOKENS
            if not jwt_settings.get("ROTATE_REFRESH_TOKENS", False):
                issues.append(
                    Warning(
                        "ROTATE_REFRESH_TOKENS فعال نیست.",
                        hint="برای امنیت بیشتر فعالش کنید.",
                        id="users.W006",
                    )
                )

            # چک BLACKLIST_AFTER_ROTATION
            if not jwt_settings.get("BLACKLIST_AFTER_ROTATION", False):
                issues.append(
                    Warning(
                        "BLACKLIST_AFTER_ROTATION فعال نیست.",
                        hint="برای جلوگیری از استفاده مجدد توکن‌های قدیمی فعالش کنید.",
                        id="users.W007",
                    )
                )

            return issues
