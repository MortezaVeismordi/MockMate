from unittest.mock import patch

from django.test import TestCase

from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.notifications.providers.base import BaseNotificationProvider


# ── Concrete test providers (جایگزین Mock(spec=...) که abstract class رو instantiate نمیکنه) ──

class SuccessProvider(BaseNotificationProvider):
    """Provider که همیشه موفق میشه."""
    def send(self, recipient: str, body: str, title: str = None):
        return (True, "mock_provider_id_123", None)


class FailingProvider(BaseNotificationProvider):
    """Provider که همیشه fail میشه."""
    def send(self, recipient: str, body: str, title: str = None):
        return (False, None, "Provider error")


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.notification = Notification.objects.create(
            recipient="09123456789",
            body="Test message",
            notification_type=Notification.Type.EMAIL,
            status=Notification.Status.PENDING,
        )

    def test_send_notification_no_provider_marks_as_failed(self):
        """When no provider class is found, notification should be marked as failed."""
        # توی testing چون DEBUG=False هست، _resolve_provider یه provider برمیگردونه
        # پس باید in_app بفرستیم که هیچ provider ای نداره
        self.notification.notification_type = Notification.Type.IN_APP
        self.notification.save()

        NotificationService.send_notification(notification_id=self.notification.id)

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, Notification.Status.FAILED)
        self.assertIn(
            "No valid provider class found for notification type: in_app",
            self.notification.error_message,
        )
        self.assertIsNone(self.notification.sent_at)

    def test_send_notification_no_provider_in_app_marks_as_failed(self):
        """IN_APP notifications should also be marked as failed when no provider."""
        self.notification.notification_type = Notification.Type.IN_APP
        self.notification.save()

        NotificationService.send_notification(notification_id=self.notification.id)

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, Notification.Status.FAILED)
        self.assertIn(
            "No valid provider class found for notification type: in_app",
            self.notification.error_message,
        )

    def test_send_notification_with_failing_provider_marks_as_failed_and_raises(self):
        """If provider.send returns failure, notification should be marked as failed and exception raised."""
        with self.assertRaises(RuntimeError) as context:
            NotificationService.send_notification(
                notification_id=self.notification.id,
                provider_class=FailingProvider,
            )

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, Notification.Status.FAILED)
        self.assertEqual(self.notification.error_message, "Provider error")
        self.assertIn("Provider failed to deliver message: Provider error", str(context.exception))

    def test_send_notification_with_successful_provider_marks_as_sent(self):
        """If provider.send returns success, notification should be marked as sent."""
        NotificationService.send_notification(
            notification_id=self.notification.id,
            provider_class=SuccessProvider,
        )

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, Notification.Status.SENT)
        self.assertEqual(self.notification.provider_message_id, "mock_provider_id_123")
        self.assertIsNotNone(self.notification.sent_at)
        self.assertIsNone(self.notification.error_message)

    @patch("apps.notifications.tasks.send_otp_notification_task")
    def test_create_notification(self, mock_task):
        """Test creating a notification via the service."""
        mock_task.delay.return_value = None

        notification = NotificationService.create_notification(
            recipient="09123456789",
            body="Test message",
            notification_type=Notification.Type.SMS,
            user=None,
            title="Test Title",
        )

        self.assertIsInstance(notification, Notification)
        self.assertEqual(notification.recipient, "09123456789")
        self.assertEqual(notification.body, "Test message")
        self.assertEqual(notification.notification_type, Notification.Type.SMS)
        self.assertEqual(notification.status, Notification.Status.PENDING)
        self.assertEqual(notification.title, "Test Title")
        self.assertIsNone(notification.provider_message_id)
        self.assertIsNone(notification.error_message)
        self.assertIsNone(notification.sent_at)
        mock_task.delay.assert_called_once_with(notification_id=notification.id)