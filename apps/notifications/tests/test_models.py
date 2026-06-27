from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import Notification


class NotificationModelTests(TestCase):
    def test_create_notification_with_defaults(self):
        """Test creating a notification with default values."""
        notification = Notification.objects.create(
            recipient="09123456789", body="Test message"
        )

        self.assertEqual(notification.recipient, "09123456789")
        self.assertEqual(notification.body, "Test message")
        self.assertEqual(notification.notification_type, Notification.Type.SMS)
        self.assertEqual(notification.status, Notification.Status.PENDING)
        self.assertIsNotNone(notification.created_at)
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)
        self.assertEqual(notification.retry_count, 0)
        self.assertIsNone(notification.provider_message_id)
        self.assertIsNone(notification.error_message)
        self.assertIsNone(notification.sent_at)
        self.assertIsNone(notification.title)

    def test_notification_type_choices(self):
        """Test that notification type choices are correct."""
        self.assertEqual(Notification.Type.SMS, "sms")
        self.assertEqual(Notification.Type.EMAIL, "email")
        self.assertEqual(Notification.Type.IN_APP, "in_app")

        # Test that the choices are available in the model
        choices = dict(Notification.Type.choices)
        self.assertIn("sms", choices)
        self.assertIn("email", choices)
        self.assertIn("in_app", choices)

    def test_notification_status_choices(self):
        """Test that notification status choices are correct."""
        self.assertEqual(Notification.Status.PENDING, "pending")
        self.assertEqual(Notification.Status.SENT, "sent")
        self.assertEqual(Notification.Status.FAILED, "failed")

        choices = dict(Notification.Status.choices)
        self.assertIn("pending", choices)
        self.assertIn("sent", choices)
        self.assertIn("failed", choices)

    def test_mark_as_sent(self):
        """Test marking a notification as sent."""
        notification = Notification.objects.create(
            recipient="09123456789",
            body="Test message",
            status=Notification.Status.PENDING,
        )

        notification.mark_as_sent(provider_id="provider_123")

        self.assertEqual(notification.status, Notification.Status.SENT)
        self.assertEqual(notification.provider_message_id, "provider_123")
        self.assertIsNotNone(notification.sent_at)
        # Check that only the specified fields were updated
        # We can't directly check update_fields, but we can check that other fields didn't change
        self.assertEqual(notification.recipient, "09123456789")
        self.assertEqual(notification.body, "Test message")

    def test_mark_as_failed(self):
        """Test marking a notification as failed."""
        notification = Notification.objects.create(
            recipient="09123456789",
            body="Test message",
            status=Notification.Status.PENDING,
        )

        notification.mark_as_failed(error="Something went wrong")

        self.assertEqual(notification.status, Notification.Status.FAILED)
        self.assertEqual(notification.error_message, "Something went wrong")
        self.assertIsNone(notification.provider_message_id)
        self.assertIsNone(notification.sent_at)

    def test_mark_as_read(self):
        """Test marking an in-app notification as read."""
        notification = Notification.objects.create(
            recipient="user@example.com",
            body="Test in-app message",
            notification_type=Notification.Type.IN_APP,
            status=Notification.Status.SENT,
        )

        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

        notification.mark_as_read()

        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

        # Calling again should not change read_at
        first_read_at = notification.read_at
        notification.mark_as_read()
        self.assertEqual(notification.read_at, first_read_at)

    def test_str_representation(self):
        """Test the string representation of the notification."""
        notification = Notification.objects.create(
            recipient="09123456789",
            body="Test message",
            notification_type=Notification.Type.SMS,
            status=Notification.Status.SENT,
        )

        expected_str = "پیامک | 09123456789 | ارسال شده"
        self.assertEqual(str(notification), expected_str)
