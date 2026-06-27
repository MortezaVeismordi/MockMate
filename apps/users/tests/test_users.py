import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.users.tests.base import BaseAPITestCase as APITestCase
from rest_framework import status
from unittest.mock import patch
from apps.users.models import OTPCode
from apps.users.services import OTPService

User = get_user_model()


# =============================================================================
#  User Model Tests
# =============================================================================

@pytest.mark.django_db
class TestUserModel:

    def test_create_user(self):
        user = User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
            first_name='Test',
            last_name='User',
            email='test@example.com',
        )
        assert user.phone_number == '09123456789'
        assert user.email == 'test@example.com'
        assert user.first_name == 'Test'
        assert user.last_name == 'User'
        assert user.is_active is False
        assert user.is_staff is False
        assert user.check_password('testpass123')

    def test_create_superuser(self):
        admin_user = User.objects.create_superuser(
            phone_number='09000000000',
            email='admin@example.com',
            password='adminpass123',
        )
        assert admin_user.is_active is True
        assert admin_user.is_staff is True
        assert admin_user.is_superuser is True

    def test_user_str_representation(self):
        user = User.objects.create_user(
            phone_number='09123456789',
            first_name='Ali',
            last_name='Rezaei',
            password='testpass123',
        )
        assert str(user) == 'Ali Rezaei'

    def test_user_str_no_name_falls_back_to_phone(self):
        user = User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
        )
        assert str(user) == '09123456789'


# =============================================================================
#  OTP Model Tests
# =============================================================================

@pytest.mark.django_db
class TestOTPModel:

    def test_create_otp(self):
        user = User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
        )
        otp = OTPCode.objects.create(
            user=user,
            code='123456',
            purpose='login',
        )
        assert otp.user == user
        assert otp.code == '123456'
        assert otp.purpose == 'login'
        assert otp.is_used is False

    def test_otp_str_representation(self):
        user = User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
        )
        otp = OTPCode.objects.create(
            user=user,
            code='123456',
            purpose='login',
        )
        assert '09123456789' in str(otp)
        assert 'login' in str(otp)

    def test_otp_is_expired(self):
        from django.utils import timezone
        from datetime import timedelta

        user = User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
        )
        otp = OTPCode.objects.create(
            user=user,
            code='123456',
            purpose='login',
        )
        OTPCode.objects.filter(pk=otp.pk).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )
        otp.refresh_from_db()
        assert otp.is_expired is True

    def test_otp_is_valid(self):
        user = User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
        )
        otp = OTPCode.objects.create(
            user=user,
            code='123456',
            purpose='login',
        )
        assert otp.is_valid is True


# =============================================================================
#  OTP Service Tests
# =============================================================================

@pytest.mark.django_db
class TestOTPService:

    @patch('django.db.transaction.on_commit', lambda f: f())
    @patch('apps.notifications.tasks.send_otp_notification_task.delay')
    def test_send_otp_login(self, mock_task):
        result = OTPService.send_otp(
            phone_number='09123456789',
            purpose='login',
            ip_address=None,
        )
        assert result['success'] is True
        assert result['is_new_user'] is True
        mock_task.assert_called_once()

    @patch('django.db.transaction.on_commit', lambda f: f())
    @patch('apps.notifications.tasks.send_otp_notification_task.delay')
    def test_send_otp_existing_user(self, mock_task):
        User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
        )
        result = OTPService.send_otp(
            phone_number='09123456789',
            purpose='login',
            ip_address=None,
        )
        assert result['success'] is True
        mock_task.assert_called_once()

    def test_verify_otp_success(self):
        user = User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
        )
        OTPCode.objects.create(
            user=user,
            code='123456',
            purpose='login',
        )
        result = OTPService.verify_otp(
            phone_number='09123456789',
            code='123456',
            purpose='login',
        )
        assert result['success'] is True
        assert result['user'] == user

    def test_verify_otp_invalid_code(self):
        user = User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
        )
        OTPCode.objects.create(
            user=user,
            code='123456',
            purpose='login',
        )
        result = OTPService.verify_otp(
            phone_number='09123456789',
            code='000000',
            purpose='login',
        )
        assert result['success'] is False

    def test_verify_otp_expired(self):
        from django.utils import timezone
        from datetime import timedelta

        user = User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
        )
        otp = OTPCode.objects.create(
            user=user,
            code='123456',
            purpose='login',
        )
        OTPCode.objects.filter(pk=otp.pk).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )
        result = OTPService.verify_otp(
            phone_number='09123456789',
            code='123456',
            purpose='login',
        )
        assert result['success'] is False

    def test_verify_otp_banned_user(self):
        User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
            is_banned=True,
        )
        result = OTPService.send_otp(
            phone_number='09123456789',
            purpose='login',
            ip_address=None,
        )
        assert result['success'] is False


# =============================================================================
#  Auth Views Tests
# =============================================================================

class TestAuthViews(APITestCase):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            phone_number='09123456789',
            password='testpass123',
            first_name='Test',
            last_name='User',
            email='test@example.com',
            is_active=True,
        )
        self.send_otp_url   = '/api/v1/auth/send-otp/'
        self.verify_otp_url = '/api/v1/auth/verify-otp/'
        self.login_url      = '/api/v1/auth/login-password/'
        self.logout_url     = '/api/v1/auth/logout/'

    @patch('django.db.transaction.on_commit', lambda f: f())
    @patch('apps.notifications.tasks.send_otp_notification_task.delay')
    def test_send_otp(self, mock_task):
        response = self.client.post(self.send_otp_url, {
            'phone_number': '09123456789',
            'purpose': 'login',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

    @patch('django.db.transaction.on_commit', lambda f: f())
    @patch('apps.notifications.tasks.send_otp_notification_task.delay')
    def test_send_otp_new_user(self, mock_task):
        response = self.client.post(self.send_otp_url, {
            'phone_number': '09199999999',
            'purpose': 'login',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

    @patch('django.db.transaction.on_commit', lambda f: f())
    @patch('apps.notifications.tasks.send_otp_notification_task.delay')
    def test_verify_otp_and_get_token(self, mock_task):
        OTPCode.objects.create(
            user=self.user,
            code='123456',
            purpose='login',
        )
        response = self.client.post(self.verify_otp_url, {
            'phone_number': '09123456789',
            'code': '123456',
            'purpose': 'login',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

    @patch('django.db.transaction.on_commit', lambda f: f())
    @patch('apps.notifications.tasks.send_otp_notification_task.delay')
    def test_verify_otp_invalid(self, mock_task):
        OTPCode.objects.create(
            user=self.user,
            code='123456',
            purpose='login',
        )
        response = self.client.post(self.verify_otp_url, {
            'phone_number': '09123456789',
            'code': '000000',
            'purpose': 'login',
        }, format='json')
        # سرویس success: false برمیگردونه با 200 یا 400
        if response.status_code == status.HTTP_200_OK:
            self.assertFalse(response.data['success'])
        else:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)