from unittest.mock import Mock, patch

import requests

from django.conf import settings
from django.test import TestCase, override_settings

from apps.notifications.providers.email import ConsoleEmailProvider, SmtpEmailProvider
from apps.notifications.providers.sms import ConsoleSMSProvider, KavenegarSMSProvider


@override_settings(KAVENEGAR_API_KEY="test-api-key", KAVENEGAR_SENDER="10008663")
class KavenegarSMSProviderTests(TestCase):
    def setUp(self):
        self.provider = KavenegarSMSProvider()
        self.valid_recipient = "09123456789"
        self.valid_body = "Test message"
        self.valid_title = "Test Title"

    @patch("apps.notifications.providers.sms.requests.post")
    def test_send_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "return": {"status": 200, "message": "ok"},
            "entries": [{"messageid": "1234567890"}],
        }
        mock_post.return_value = mock_response

        success, provider_id, error = self.provider.send(
            recipient=self.valid_recipient,
            body=self.valid_body,
            title=self.valid_title,
        )

        self.assertTrue(success)
        self.assertEqual(provider_id, "1234567890")
        self.assertIsNone(error)
        mock_post.assert_called_once()

    @patch("apps.notifications.providers.sms.requests.post")
    def test_send_failure_api_error(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "return": {"status": 400, "message": "Invalid parameters"}
        }
        mock_post.return_value = mock_response

        success, provider_id, error = self.provider.send(
            recipient=self.valid_recipient,
            body=self.valid_body,
            title=self.valid_title,
        )

        self.assertFalse(success)
        self.assertIsNone(provider_id)
        self.assertIn("API Error Code 400", error)

    @patch("apps.notifications.providers.sms.requests.post")
    def test_send_failure_timeout(self, mock_post):
        # باید requests.exceptions.Timeout بده نه Exception عادی
        mock_post.side_effect = requests.exceptions.Timeout("Timeout")

        success, provider_id, error = self.provider.send(
            recipient=self.valid_recipient,
            body=self.valid_body,
            title=self.valid_title,
        )

        self.assertFalse(success)
        self.assertIsNone(provider_id)
        self.assertIn("Connection timed out", error)

    @patch("apps.notifications.providers.sms.requests.post")
    def test_send_failure_connection_error(self, mock_post):
        # باید requests.exceptions.ConnectionError بده
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection error")

        success, provider_id, error = self.provider.send(
            recipient=self.valid_recipient,
            body=self.valid_body,
            title=self.valid_title,
        )

        self.assertFalse(success)
        self.assertIsNone(provider_id)
        self.assertIn("Network connection failed", error)

    def test_send_missing_api_key(self):
        original_api_key = getattr(settings, "KAVENEGAR_API_KEY", None)
        settings.KAVENEGAR_API_KEY = ""

        try:
            success, provider_id, error = self.provider.send(
                recipient=self.valid_recipient,
                body=self.valid_body,
                title=self.valid_title,
            )
            self.assertFalse(success)
            self.assertIsNone(provider_id)
            self.assertIn("API key is missing or empty", error)
        finally:
            if original_api_key is not None:
                settings.KAVENEGAR_API_KEY = original_api_key


class SmtpEmailProviderTests(TestCase):
    def setUp(self):
        self.provider = SmtpEmailProvider()
        self.valid_recipient = "user@example.com"
        self.valid_body = "Test email body"
        self.valid_title = "Test Email Title"

    @patch("apps.notifications.providers.email.send_mail")
    def test_send_success(self, mock_send_mail):
        mock_send_mail.return_value = 1

        success, provider_id, error = self.provider.send(
            recipient=self.valid_recipient,
            body=self.valid_body,
            title=self.valid_title,
        )

        self.assertTrue(success)
        self.assertEqual(provider_id, "smtp_success_dispatched_id")
        self.assertIsNone(error)
        mock_send_mail.assert_called_once()

    @patch("apps.notifications.providers.email.send_mail")
    def test_send_failure_smtp_exception(self, mock_send_mail):
        from smtplib import SMTPException

        mock_send_mail.side_effect = SMTPException("SMTP error")

        success, provider_id, error = self.provider.send(
            recipient=self.valid_recipient,
            body=self.valid_body,
            title=self.valid_title,
        )

        self.assertFalse(success)
        self.assertIsNone(provider_id)
        self.assertIn("SMTP protocol error occurred", error)

    @patch("apps.notifications.providers.email.send_mail")
    def test_send_failure_general_exception(self, mock_send_mail):
        mock_send_mail.side_effect = Exception("General error")

        success, provider_id, error = self.provider.send(
            recipient=self.valid_recipient,
            body=self.valid_body,
            title=self.valid_title,
        )

        self.assertFalse(success)
        self.assertIsNone(provider_id)
        self.assertIn("Unexpected system error during email transport", error)


class ConsoleSMSProviderTests(TestCase):
    def setUp(self):
        # از sms.py import میکنیم نه base.py
        self.provider = ConsoleSMSProvider()

    def test_send_returns_success(self):
        success, provider_id, error = self.provider.send(
            recipient="09123456789",
            body="Test SMS message",
            title="Test SMS Title",
        )

        self.assertTrue(success)
        self.assertIsNotNone(provider_id)
        self.assertIsNone(error)
        self.assertIsInstance(provider_id, str)


class ConsoleEmailProviderTests(TestCase):
    def setUp(self):
        self.provider = ConsoleEmailProvider()

    def test_send_returns_success(self):
        success, provider_id, error = self.provider.send(
            recipient="user@example.com",
            body="Test email message",
            title="Test Email Title",
        )

        self.assertTrue(success)
        self.assertIsNotNone(provider_id)
        self.assertIsNone(error)
        self.assertIsInstance(provider_id, str)
