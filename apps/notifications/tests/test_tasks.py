from unittest.mock import patch, Mock

from django.test import TestCase

from apps.notifications.models import Notification
from apps.notifications.tasks import send_otp_notification_task


class NotificationTaskTests(TestCase):
    def setUp(self):
        self.notification = Notification.objects.create(
            recipient="09123456789",
            body="Test message",
            notification_type=Notification.Type.SMS,
            status=Notification.Status.PENDING,
        )

    @patch('apps.notifications.services.NotificationService.send_notification')
    def test_task_success(self, mock_send_notification):
        mock_send_notification.return_value = None

        result = send_otp_notification_task.apply(args=[self.notification.id])

        # EagerResult از .result استفاده میکنه نه .return_value
        self.assertIsNone(result.result)
        mock_send_notification.assert_called_once_with(notification_id=self.notification.id)

    @patch('apps.notifications.services.NotificationService.send_notification')
    def test_task_notification_not_found(self, mock_send_notification):
        notification_id = self.notification.id
        self.notification.delete()

        result = send_otp_notification_task.apply(args=[notification_id])

        self.assertIsNone(result.result)
        mock_send_notification.assert_not_called()

    @patch('apps.notifications.services.NotificationService.send_notification')
    def test_task_notification_already_sent(self, mock_send_notification):
        self.notification.status = Notification.Status.SENT
        self.notification.save()

        result = send_otp_notification_task.apply(args=[self.notification.id])

        self.assertIsNone(result.result)
        mock_send_notification.assert_not_called()

    @patch('apps.notifications.services.NotificationService.send_notification')
    def test_task_provider_failure_retries(self, mock_send_notification):
        mock_send_notification.side_effect = Exception("Provider failed")

        # با CELERY_TASK_ALWAYS_EAGER=True، task بعد از max_retries raise میکنه
        # exception توسط Celery wrap میشه — فقط چک میکنیم raise شد
        with self.assertRaises(Exception):
            send_otp_notification_task.apply(args=[self.notification.id])

        mock_send_notification.assert_called_once_with(notification_id=self.notification.id)

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.retry_count, 1)

    @patch('apps.notifications.services.NotificationService.send_notification')
    def test_task_provider_failure_max_retries_exceeded(self, mock_send_notification):
        mock_send_notification.side_effect = Exception("Provider failed")

        self.notification.retry_count = 3
        self.notification.save()

        with self.assertRaises(Exception):
            send_otp_notification_task.apply(args=[self.notification.id])

        mock_send_notification.assert_called_once_with(notification_id=self.notification.id)

        self.notification.refresh_from_db()
        self.assertGreaterEqual(self.notification.retry_count, 1)

    @patch('apps.notifications.services.NotificationService.send_notification')
    def test_task_database_error_when_updating_retry_count(self, mock_send_notification):
        mock_send_notification.side_effect = Exception("Provider failed")

        with patch('apps.notifications.models.Notification.objects') as mock_objects:
            mock_objects.select_for_update.return_value.get.side_effect = Exception("Database error")

            with self.assertRaises(Exception):
                send_otp_notification_task.apply(args=[self.notification.id])

            mock_send_notification.assert_called_once_with(notification_id=self.notification.id)