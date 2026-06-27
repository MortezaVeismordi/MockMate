"""
tests/test_otp.py

Integration tests for OTP flows.

Coverage:
  - SendOTPView       → POST /api/v1/auth/send-otp/
  - ResendOTPView     → POST /api/v1/auth/resend-otp/
  - VerifyOTPView     → POST /api/v1/auth/verify-otp/
  - OTPCode model     → business logic (expiry, attempts, daily limit)

Philosophy:
  - OTPService.send_otp  مشکت می‌شه (SMS واقعی نمی‌زنیم)
  - دیتابیس واقعی — OTPCode رو مستقیم در DB می‌سازیم
  - هر تست یه سناریوی کاربری واقعی رو cover می‌کنه
"""

from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import CustomUser, OTPCode
from apps.users.tests.base import BaseAPITestCase as APITestCase

# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────


def create_inactive_user(phone_number: str = "09120000001") -> CustomUser:
    """
    کاربری که تازه ثبت‌نام کرده ولی OTP رو هنوز verify نکرده.
    is_active=False است — دقیقاً همون default مدل.
    """
    return CustomUser.objects.create_user(
        phone_number=phone_number,
        password=None,
    )


def create_active_user(phone_number: str = "09120000002") -> CustomUser:
    """کاربر کاملاً فعال و تایید شده."""
    user = CustomUser.objects.create_user(
        phone_number=phone_number,
        password=None,
    )
    user.is_active = True
    user.is_phone_verified = True
    user.save(update_fields=["is_active", "is_phone_verified"])
    return user


def create_otp(
    user: CustomUser,
    purpose: str = "login",
    expired: bool = False,
    used: bool = False,
    failed_attempts: int = 0,
) -> OTPCode:
    """
    OTP مستقیم در DB می‌سازیم — بدون نیاز به OTPService.
    این بهمون کنترل کامل روی state رو می‌ده.
    """
    otp = OTPCode.objects.create(
        user=user,
        code="123456",
        purpose=purpose,
        is_used=used,
        failed_attempts=failed_attempts,
    )
    if expired:
        # زمان ساخت رو به گذشته می‌بریم تا منقضی بشه
        OTPCode.objects.filter(pk=otp.pk).update(
            created_at=timezone.now() - timedelta(minutes=OTPCode.EXPIRE_MINUTES + 1)
        )
        otp.refresh_from_db()
    return otp


MOCK_SEND_SUCCESS = {
    "success": True,
    "message": "کد OTP ارسال شد",
    "is_new_user": False,
    "remaining_seconds": 120,
}


# ─────────────────────────────────────────────────────────────
#  1. Send OTP
# ─────────────────────────────────────────────────────────────


class SendOTPTests(APITestCase):
    """
    POST /api/v1/auth/send-otp/

    Tests:
      - شماره جدید → کاربر ساخته می‌شه، is_new_user=True
      - شماره موجود → is_new_user=False
      - فرمت نامعتبر → بدون صدا زدن service رد می‌شه
      - daily limit رسیده → 4xx
      - purpose نامعتبر → 400
      - remaining_seconds در response هست
    """

    URL = reverse("users:send-otp")

    @patch("apps.users.views.OTPService.send_otp")
    def test_new_phone_creates_user_and_returns_is_new_user_true(self, mock_send):
        mock_send.return_value = {**MOCK_SEND_SUCCESS, "is_new_user": True}

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09130000001",
                "purpose": "login",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertTrue(data["is_new_user"])
        mock_send.assert_called_once()

    @patch("apps.users.views.OTPService.send_otp")
    def test_existing_phone_returns_is_new_user_false(self, mock_send):
        create_active_user(phone_number="09130000002")
        mock_send.return_value = {**MOCK_SEND_SUCCESS, "is_new_user": False}

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09130000002",
                "purpose": "login",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.json()["data"]["is_new_user"])

    @patch("apps.users.views.OTPService.send_otp")
    def test_response_includes_remaining_seconds(self, mock_send):
        mock_send.return_value = {**MOCK_SEND_SUCCESS, "remaining_seconds": 115}

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09130000003",
                "purpose": "login",
            },
        )

        self.assertIn("remaining_seconds", response.json()["data"])

    def test_invalid_phone_format_blocked_before_service_is_called(self):
        """
        Validator باید قبل از OTPService رد کنه.
        اگه mock صدا زده بشه یعنی validation کار نکرده.
        """
        with patch("apps.users.views.OTPService.send_otp") as mock_send:
            response = self.client.post(
                self.URL,
                {
                    "phone_number": "0912",  # فرمت نادرست
                    "purpose": "login",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            mock_send.assert_not_called()

    def test_non_09_phone_is_rejected(self):
        """شماره‌ای که با 09 شروع نمی‌شه باید رد بشه."""
        with patch("apps.users.views.OTPService.send_otp") as mock_send:
            response = self.client.post(
                self.URL,
                {
                    "phone_number": "08123456789",
                    "purpose": "login",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            mock_send.assert_not_called()

    def test_invalid_purpose_is_rejected(self):
        with patch("apps.users.views.OTPService.send_otp") as mock_send:
            response = self.client.post(
                self.URL,
                {
                    "phone_number": "09130000004",
                    "purpose": "hack",  # مقدار نامعتبر
                },
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            mock_send.assert_not_called()

    @patch("apps.users.views.OTPService.send_otp")
    def test_daily_limit_exceeded_returns_error(self, mock_send):
        """
        وقتی service می‌گه limit رسیده، view باید error برگردونه —
        نه 200 با success=False.
        """
        mock_send.return_value = {
            "success": False,
            "message": "تعداد درخواست OTP امروز به حد مجاز رسیده",
        }

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09130000005",
                "purpose": "login",
            },
        )

        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    def test_missing_phone_number_returns_400(self):
        response = self.client.post(self.URL, {"purpose": "login"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_purpose_returns_400(self):
        response = self.client.post(self.URL, {"phone_number": "09130000006"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────
#  2. Resend OTP
# ─────────────────────────────────────────────────────────────


class ResendOTPTests(APITestCase):
    """
    POST /api/v1/auth/resend-otp/

    Tests:
      - resend موفق → remaining_seconds و daily_remaining در response
      - daily limit → error
      - شماره نامعتبر → بدون صدا زدن service رد می‌شه
    """

    URL = reverse("users:resend-otp")

    def setUp(self):
        super().setUp()
        # کاربر و OTP قبلی باید وجود داشته باشن
        self.user = create_active_user(phone_number="09140000001")
        # OTP قبلی بساز که cooldown چک بشه — ولی قدیمی باشه (بیشتر از 60 ثانیه)
        otp = create_otp(self.user, purpose="login")
        OTPCode.objects.filter(pk=otp.pk).update(
            created_at=timezone.now() - timedelta(seconds=90)
        )

    @patch("apps.users.views.OTPService.send_otp")
    def test_successful_resend_returns_countdown(self, mock_send):
        mock_send.return_value = {
            **MOCK_SEND_SUCCESS,
            "remaining_seconds": 110,
        }

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09140000001",
                "purpose": "login",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("remaining_seconds", response.json()["data"])

    @patch("apps.users.views.OTPService.send_otp")
    def test_resend_daily_limit_returns_error(self, mock_send):
        mock_send.return_value = {
            "success": False,
            "message": "تعداد درخواست OTP امروز به حد مجاز رسیده",
        }

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09140000002",
                "purpose": "login",
            },
        )

        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    def test_invalid_phone_blocked_before_service(self):
        with patch("apps.users.views.OTPService.send_otp") as mock_send:
            response = self.client.post(
                self.URL,
                {
                    "phone_number": "123",
                    "purpose": "login",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            mock_send.assert_not_called()


# ─────────────────────────────────────────────────────────────
#  3. Verify OTP
# ─────────────────────────────────────────────────────────────


class VerifyOTPTests(APITestCase):
    """
    POST /api/v1/auth/verify-otp/

    Tests:
      - کد درست → JWT pair + user + is_profile_complete
      - کد اشتباه → failed_attempts بالا می‌ره
      - کد منقضی شده → رد می‌شه
      - کد قبلاً استفاده شده → رد می‌شه
      - بعد از MAX_ATTEMPTS تلاش اشتباه → قفل می‌شه
      - verify موفق → is_active=True و last_login_ip ست می‌شه
      - کاربر جدید → is_new_user=True در response
    """

    URL = reverse("users:verify-otp")

    def setUp(self):
        super().setUp()
        self.user = create_inactive_user(phone_number="09150000001")

    # ── Happy path ────────────────────────────────────────────

    def test_correct_code_returns_jwt_pair(self):
        create_otp(self.user, purpose="login")

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "123456",
                "purpose": "login",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tokens = response.json()["data"]["tokens"]
        self.assertIn("access", tokens)
        self.assertIn("refresh", tokens)

    def test_correct_code_activates_user(self):
        """
        بعد از verify موفق، کاربر باید is_active=True بشه.
        این مهم‌ترین side-effect verify هست.
        """
        create_otp(self.user, purpose="login")

        self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "123456",
                "purpose": "login",
            },
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.is_phone_verified)

    def test_correct_code_saves_last_login_ip(self):
        """IP کاربر باید بعد از verify ذخیره بشه."""
        create_otp(self.user, purpose="login")

        self.client.post(
            self.URL,
            {"phone_number": "09150000001", "code": "123456", "purpose": "login"},
            REMOTE_ADDR="1.2.3.4",
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.last_login_ip, "1.2.3.4")

    def test_response_includes_is_profile_complete(self):
        create_otp(self.user, purpose="login")

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "123456",
                "purpose": "login",
            },
        )

        self.assertIn("is_profile_complete", response.json()["data"])

    def test_used_otp_is_marked_as_used_in_db(self):
        """بعد از verify، کد باید is_used=True بشه."""
        otp = create_otp(self.user, purpose="login")

        self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "123456",
                "purpose": "login",
            },
        )

        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

    # ── Wrong code ────────────────────────────────────────────

    def test_wrong_code_is_rejected(self):
        create_otp(self.user, purpose="login")

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "000000",
                "purpose": "login",
            },
        )

        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    def test_wrong_code_increments_failed_attempts(self):
        """
        هر بار کد اشتباه وارد می‌شه، failed_attempts باید بره بالا.
        این جلوی brute force رو می‌گیره.
        """
        otp = create_otp(self.user, purpose="login")

        self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "000000",
                "purpose": "login",
            },
        )

        otp.refresh_from_db()
        self.assertEqual(otp.failed_attempts, 1)

    def test_wrong_code_does_not_activate_user(self):
        create_otp(self.user, purpose="login")

        self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "000000",
                "purpose": "login",
            },
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    # ── Expired OTP ───────────────────────────────────────────

    def test_expired_code_is_rejected(self):
        create_otp(self.user, purpose="login", expired=True)

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "123456",
                "purpose": "login",
            },
        )

        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    def test_expired_code_does_not_activate_user(self):
        create_otp(self.user, purpose="login", expired=True)

        self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "123456",
                "purpose": "login",
            },
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    # ── Already used OTP ──────────────────────────────────────

    def test_already_used_code_is_rejected(self):
        """
        یه کد که یه بار استفاده شده نباید دوباره قبول بشه.
        حتی اگه کد درست باشه.
        """
        create_otp(self.user, purpose="login", used=True)

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "123456",
                "purpose": "login",
            },
        )

        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    # ── Max attempts ──────────────────────────────────────────

    def test_locked_otp_is_rejected_even_with_correct_code(self):
        """
        بعد از MAX_ATTEMPTS تلاش اشتباه، حتی کد درست هم نباید کار کنه.
        این مهم‌ترین تست امنیتی OTP هست.
        """
        create_otp(
            self.user,
            purpose="login",
            failed_attempts=OTPCode.MAX_ATTEMPTS,
        )

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "123456",
                "purpose": "login",
            },
        )

        self.assertNotEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    # ── Purpose mismatch ──────────────────────────────────────

    def test_wrong_purpose_is_rejected(self):
        """
        کد login نباید برای reset قبول بشه و برعکس.
        """
        create_otp(self.user, purpose="login")

        response = self.client.post(
            self.URL,
            {
                "phone_number": "09150000001",
                "code": "123456",
                "purpose": "reset",  # purpose اشتباه
            },
        )

        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    # ── Nonexistent phone ─────────────────────────────────────

    def test_nonexistent_phone_returns_error(self):
        response = self.client.post(
            self.URL,
            {
                "phone_number": "09199999999",
                "code": "123456",
                "purpose": "login",
            },
        )

        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    # ── New OTP invalidates old one ───────────────────────────

    def test_new_otp_invalidates_previous_same_purpose(self):
        """
        وقتی OTP جدید می‌فرستیم، کد قبلی باید غیرمعتبر بشه.
        این جلوی replay attack رو می‌گیره.
        """
        old_otp = create_otp(self.user, purpose="login")

        # OTP جدید بساز برای همون purpose
        OTPCode.invalidate_previous(self.user, "login")

        old_otp.refresh_from_db()
        self.assertTrue(old_otp.is_used)


# ─────────────────────────────────────────────────────────────
#  4. OTPCode Model Logic
# ─────────────────────────────────────────────────────────────


class OTPCodeModelTests(APITestCase):
    """
    تست مستقیم business logic مدل OTPCode.
    این تست‌ها به HTTP layer وابسته نیستن.

    Tests:
      - is_expired property
      - is_valid property
      - remaining_seconds
      - daily limit در create_otp
      - invalidate_previous
      - generate_code فقط عدد تولید می‌کنه
    """

    def setUp(self):
        super().setUp()
        self.user = create_active_user(phone_number="09160000001")

    def test_fresh_otp_is_not_expired(self):
        otp = create_otp(self.user)
        self.assertFalse(otp.is_expired)

    def test_old_otp_is_expired(self):
        otp = create_otp(self.user, expired=True)
        self.assertTrue(otp.is_expired)

    def test_valid_otp_passes_all_checks(self):
        otp = create_otp(self.user)
        self.assertTrue(otp.is_valid)

    def test_used_otp_is_not_valid(self):
        otp = create_otp(self.user, used=True)
        self.assertFalse(otp.is_valid)

    def test_expired_otp_is_not_valid(self):
        otp = create_otp(self.user, expired=True)
        self.assertFalse(otp.is_valid)

    def test_max_attempts_reached_otp_is_not_valid(self):
        otp = create_otp(self.user, failed_attempts=OTPCode.MAX_ATTEMPTS)
        self.assertFalse(otp.is_valid)

    def test_remaining_seconds_positive_for_fresh_otp(self):
        otp = create_otp(self.user)
        self.assertGreater(otp.remaining_seconds, 0)

    def test_remaining_seconds_zero_for_expired_otp(self):
        otp = create_otp(self.user, expired=True)
        self.assertEqual(otp.remaining_seconds, 0)

    def test_generate_code_is_numeric_and_correct_length(self):
        code = OTPCode.generate_code(6)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_generate_code_different_each_time(self):
        """کد باید random باشه — نه ثابت."""
        codes = {OTPCode.generate_code(6) for _ in range(20)}
        # در ۲۰ بار تولید، باید حداقل ۲ مقدار مختلف داشته باشیم
        self.assertGreater(len(codes), 1)

    def test_daily_limit_raises_after_max_resend(self):
        """
        بعد از MAX_RESEND_PER_DAY درخواست،
        create_otp باید ValueError بده.
        """
        # به تعداد max مجاز OTP بساز
        for _ in range(OTPCode.MAX_RESEND_PER_DAY):
            OTPCode.objects.create(
                user=self.user,
                code="123456",
                purpose="login",
            )

        with self.assertRaises(ValueError):
            OTPCode.create_otp(user=self.user, purpose="login")

    def test_invalidate_previous_marks_old_codes_as_used(self):
        otp1 = create_otp(self.user, purpose="login")
        otp2 = create_otp(self.user, purpose="login")

        OTPCode.invalidate_previous(self.user, "login")

        otp1.refresh_from_db()
        otp2.refresh_from_db()
        self.assertTrue(otp1.is_used)
        self.assertTrue(otp2.is_used)

    def test_invalidate_previous_does_not_affect_other_purpose(self):
        """
        invalidate_previous فقط باید همون purpose رو invalidate کنه.
        """
        login_otp = create_otp(self.user, purpose="login")
        reset_otp = create_otp(self.user, purpose="reset")

        OTPCode.invalidate_previous(self.user, "login")

        reset_otp.refresh_from_db()
        self.assertFalse(reset_otp.is_used)

    def test_verify_otp_returns_false_for_wrong_code(self):
        create_otp(self.user, purpose="login")
        success, message = OTPCode.verify_otp(self.user, "000000", "login")
        self.assertFalse(success)

    def test_verify_otp_returns_true_for_correct_code(self):
        create_otp(self.user, purpose="login")
        success, message = OTPCode.verify_otp(self.user, "123456", "login")
        self.assertTrue(success)

    def test_verify_otp_returns_false_when_no_otp_exists(self):
        success, message = OTPCode.verify_otp(self.user, "123456", "login")
        self.assertFalse(success)
