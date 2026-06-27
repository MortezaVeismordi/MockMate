from unittest.mock import MagicMock, patch

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken


class NoThrottle:
    """Throttle ای که همیشه allow می‌کنه — فقط برای تست."""

    def allow_request(self, request, view):
        return True

    def wait(self):
        return None


class BaseAPITestCase(APITestCase):
    """
    Base class برای همه تست‌های users app.

    استفاده:
        from apps.users.tests.base import BaseAPITestCase

        class MyTest(BaseAPITestCase):
            def test_something(self):
                ...
    """

    # مسیرهایی که باید mock بشن تا SMS/Email واقعی نره
    NOTIFICATION_PATHS = [
        "apps.notifications.services.NotificationService.send_notification",
        "apps.notifications.tasks.send_otp_notification_task.delay",
        "apps.notifications.tasks.send_welcome_sms.delay",
        "apps.notifications.tasks.send_welcome_notification.delay",
        "apps.notifications.tasks.send_profile_completed_notification.delay",
    ]

    # view-level throttle هایی که باید patch بشن
    THROTTLE_PATHS = [
        "apps.users.views.OTPSendThrottle",
        "apps.users.views.OTPVerifyThrottle",
        "apps.users.views.AuthThrottle",
    ]

    def setUp(self):
        super().setUp()
        self._patchers = []

        # ── غیرفعال کردن SimpleRateThrottle (پایه همه throttle ها) ──────────
        # این کافیه چون OTPSendThrottle از AnonRateThrottle ارث میبره
        # که خودش از SimpleRateThrottle ارث میبره
        p = patch(
            "rest_framework.throttling.SimpleRateThrottle.allow_request",
            return_value=True,
        )
        p.start()
        self._patchers.append(p)

        # ── mock کردن notification ها ─────────────────────────────────────────
        for path in self.NOTIFICATION_PATHS:
            try:
                p = patch(path)
                p.start()
                self._patchers.append(p)
            except ModuleNotFoundError:
                # اگه مسیر وجود نداشت، skip کن
                pass

    def tearDown(self):
        for p in getattr(self, "_patchers", []):  # ← اگه نبود، [] برمیگردونه
            try:
                p.stop()
            except RuntimeError:
                pass
        super().tearDown()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def authenticate(self, user):
        """
        کاربر رو با JWT authenticate می‌کنه.

        استفاده:
            self.authenticate(self.user)
            response = self.client.get(url)
        """
        refresh = RefreshToken.for_user(user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}"
        )

    def deauthenticate(self):
        """credentials رو پاک می‌کنه."""
        self.client.credentials()
