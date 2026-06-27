# apps/users/tests/conftest.py
from contextlib import ExitStack
from unittest.mock import patch

import pytest

NOTIFICATION_PATHS = [
    "apps.notifications.services.NotificationService.send_notification",
    "apps.notifications.tasks.send_otp_notification_task.delay",
    "apps.notifications.tasks.send_welcome_sms.delay",
    "apps.notifications.tasks.send_welcome_notification.delay",
    "apps.notifications.tasks.send_profile_completed_notification.delay",
]


@pytest.fixture(autouse=True)
def mock_external_services_in_user_tests():
    with ExitStack() as stack:
        for path in NOTIFICATION_PATHS:
            stack.enter_context(patch(path))
        yield


@pytest.fixture(autouse=True)
def disable_throttling(settings):
    """
    در تست‌ها throttling رو کاملاً غیرفعال می‌کنیم
    تا rate limit باعث 429 نشه.
    """
    settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
    settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {}
