"""
tests/test_profile.py

Integration tests for user profile flows.

Coverage:
  - UserMeView         → GET/PATCH /api/v1/me/
  - CompleteProfileView → POST /api/v1/me/complete-profile/
  - AvatarView         → PUT/DELETE /api/v1/me/avatar/
  - DeleteAccountView  → DELETE /api/v1/me/delete/

Philosophy:
  - دیتابیس واقعی
  - فایل‌های avatar با SimpleUploadedFile mock می‌شن
  - هر تست یه سناریوی کاربری واقعی رو cover می‌کنه
"""

import io
from unittest.mock import MagicMock, patch

from PIL import Image
from rest_framework_simplejwt.tokens import RefreshToken

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from apps.users.models import CustomUser, OTPCode
from apps.users.tests.base import BaseAPITestCase as APITestCase

# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────


def create_active_user(
    phone_number: str = "09170000001",
    password: str = None,
    **kwargs,
) -> CustomUser:
    user = CustomUser.objects.create_user(
        phone_number=phone_number,
        password=password,
        **kwargs,
    )
    user.is_active = True
    user.is_phone_verified = True
    user.save(update_fields=["is_active", "is_phone_verified"])
    return user


def auth_header(user: CustomUser) -> str:
    refresh = RefreshToken.for_user(user)
    return f"Bearer {str(refresh.access_token)}"


def fake_image(name: str = "avatar.jpg") -> SimpleUploadedFile:
    """یه فایل تصویر ساختگی برای تست آپلود."""
    return SimpleUploadedFile(
        name=name,
        content=b"\xff\xd8\xff\xe0" + b"\x00" * 100,  # minimal JPEG header
        content_type="image/jpeg",
    )


def generate_image(name: str = "avatar.jpg", fmt: str = "JPEG") -> SimpleUploadedFile:
    """Generate a real, valid in-memory image using PIL."""
    buffer = io.BytesIO()
    img = Image.new("RGB", (200, 200), color="red")
    img.save(buffer, format=fmt)
    buffer.seek(0)
    return SimpleUploadedFile(
        name=name,
        content=buffer.read(),
        content_type=f"image/{fmt.lower()}",
    )


# ─────────────────────────────────────────────────────────────
#  1. GET /me/ — دریافت پروفایل
# ─────────────────────────────────────────────────────────────


class UserMeGetTests(APITestCase):
    """
    GET /api/v1/me/

    Tests:
      - بدون token → 401
      - با token → 200 + فیلدهای اصلی
      - phone_number در response هست
      - is_profile_complete درسته
    """

    URL = reverse("users:me")

    def setUp(self):
        super().setUp()
        self.user = create_active_user(
            phone_number="09170000001",
            first_name="علی",
            last_name="رضایی",
        )
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.user))

    def test_unauthenticated_returns_401(self):
        self.client.credentials()
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_returns_200(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_response_contains_phone_number(self):
        response = self.client.get(self.URL)
        self.assertEqual(
            response.json()["data"]["phone_number"],
            "09170000001",
        )

    def test_response_contains_full_name(self):
        response = self.client.get(self.URL)
        data = response.json()["data"]
        self.assertIn("full_name", data)
        self.assertEqual(data["full_name"], "علی رضایی")

    def test_incomplete_profile_returns_is_profile_complete_false(self):
        """کاربری که job_title نداره باید is_profile_complete=False داشته باشه."""
        response = self.client.get(self.URL)
        self.assertFalse(response.json()["data"]["is_profile_complete"])

    def test_complete_profile_returns_is_profile_complete_true(self):
        self.user.job_title = "Backend Developer"
        self.user.experience_level = "mid_level"
        self.user.save(update_fields=["job_title", "experience_level"])

        response = self.client.get(self.URL)
        self.assertTrue(response.json()["data"]["is_profile_complete"])


# ─────────────────────────────────────────────────────────────
#  2. PATCH /me/ — ویرایش پروفایل
# ─────────────────────────────────────────────────────────────


class UserMePatchTests(APITestCase):
    """
    PATCH /api/v1/me/

    Tests:
      - بدون token → 401
      - ویرایش partial یه فیلد
      - ویرایش چند فیلد همزمان
      - فیلد phone_number نباید قابل تغییر باشه
      - skills (JSONField) درست ذخیره می‌شه
      - مقدار خالی bio قابل ذخیره‌ست
    """

    URL = reverse("users:me")

    def setUp(self):
        super().setUp()
        self.user = create_active_user(phone_number="09170000002")
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.user))

    def test_unauthenticated_returns_401(self):
        self.client.credentials()
        response = self.client.patch(self.URL, {"first_name": "تست"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_single_field_persists(self):
        response = self.client.patch(self.URL, {"first_name": "محمد"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "محمد")

    def test_patch_multiple_fields_at_once(self):
        response = self.client.patch(
            self.URL,
            {
                "first_name": "سارا",
                "last_name": "احمدی",
                "bio": "توسعه‌دهنده بکند",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "سارا")
        self.assertEqual(self.user.last_name, "احمدی")
        self.assertEqual(self.user.bio, "توسعه‌دهنده بکند")

    def test_phone_number_cannot_be_changed_via_patch(self):
        """
        phone_number فیلد اصلی auth هست — نباید از /me/ قابل تغییر باشه.
        """
        original_phone = self.user.phone_number
        self.client.patch(self.URL, {"phone_number": "09199999999"})

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, original_phone)

    def test_skills_json_field_saved_correctly(self):
        skills = ["Python", "Django", "Docker"]
        response = self.client.patch(self.URL, {"skills": skills}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertCountEqual(self.user.skills, skills)

    def test_empty_bio_is_accepted(self):
        response = self.client.patch(self.URL, {"bio": ""}, format="json")
        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT],
        )


# ─────────────────────────────────────────────────────────────
#  3. Complete Profile
# ─────────────────────────────────────────────────────────────


class CompleteProfileTests(APITestCase):
    """
    POST /api/v1/me/complete-profile/

    Tests:
      - بدون token → 401
      - تکمیل موفق → is_profile_complete=True
      - فیلدهای اجباری: first_name, last_name, job_title, experience_level
      - experience_level نامعتبر → 400
      - skills لیست درستی هست
    """

    URL = reverse("users:complete-profile")

    VALID_PAYLOAD = {
        "first_name": "رضا",
        "last_name": "محمدی",
        "job_title": "Backend Developer",
        "experience_level": "mid_level",
        "years_of_experience": 3,
        "skills": ["Python", "Django", "Redis"],
    }

    def setUp(self):
        super().setUp()
        self.user = create_active_user(phone_number="09170000003")
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.user))

    def test_unauthenticated_returns_401(self):
        self.client.credentials()
        response = self.client.post(self.URL, self.VALID_PAYLOAD, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_valid_payload_completes_profile(self):
        response = self.client.post(self.URL, self.VALID_PAYLOAD, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_profile_complete)

    def test_all_fields_are_persisted(self):
        self.client.post(self.URL, self.VALID_PAYLOAD, format="json")

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "رضا")
        self.assertEqual(self.user.last_name, "محمدی")
        self.assertEqual(self.user.job_title, "Backend Developer")
        self.assertEqual(self.user.experience_level, "mid_level")
        self.assertEqual(self.user.years_of_experience, 3)
        self.assertCountEqual(self.user.skills, ["Python", "Django", "Redis"])

    def test_invalid_experience_level_is_rejected(self):
        payload = {**self.VALID_PAYLOAD, "experience_level": "god_level"}
        response = self.client.post(self.URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_required_fields_returns_400(self):
        for field in ["first_name", "last_name", "job_title", "experience_level"]:
            payload = {k: v for k, v in self.VALID_PAYLOAD.items() if k != field}
            response = self.client.post(self.URL, payload, format="json")
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                msg=f"Expected 400 when '{field}' is missing",
            )

    def test_response_contains_full_profile_data(self):
        response = self.client.post(self.URL, self.VALID_PAYLOAD, format="json")
        data = response.json()["data"]

        self.assertIn("phone_number", data)
        self.assertIn("is_profile_complete", data)
        self.assertTrue(data["is_profile_complete"])


# ─────────────────────────────────────────────────────────────
#  4. Avatar Upload & Delete
# ─────────────────────────────────────────────────────────────


class AvatarTests(APITestCase):
    """
    PUT    /api/v1/me/avatar/
    DELETE /api/v1/me/avatar/

    Tests:
      - بدون token → 401
      - آپلود موفق → avatar_url در response
      - آپلود غیر تصویر → 400
      - حذف وقتی avatar ندارد → 404
      - حذف وقتی avatar دارد → 204
      - بعد از حذف، avatar=None در DB
    """

    PUT_URL = reverse("users:avatar")
    DELETE_URL = reverse("users:avatar")

    def setUp(self):
        super().setUp()
        self.user = create_active_user(phone_number="09170000004")
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.user))

    def test_unauthenticated_upload_returns_401(self):
        self.client.credentials()
        response = self.client.put(
            self.PUT_URL, {"avatar": generate_image()}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_valid_image_upload_returns_avatar_url(self):
        with patch(
            "django.core.files.storage.default_storage.save",
            return_value="avatars/test.jpg",
        ):
            response = self.client.put(
                self.PUT_URL,
                {"avatar": generate_image()},
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("avatar_url", response.json()["data"])

    def test_non_image_file_is_rejected(self):
        fake_pdf = SimpleUploadedFile(
            "resume.pdf",
            b"%PDF-1.4 content",
            content_type="application/pdf",
        )
        response = self.client.put(
            self.PUT_URL,
            {"avatar": fake_pdf},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_avatar_when_none_returns_404(self):
        """کاربری که avatar ندارد نباید بتواند delete کند."""
        response = self.client.delete(self.DELETE_URL)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("django.core.files.storage.default_storage.exists", return_value=True)
    @patch("django.core.files.storage.default_storage.delete")
    def test_delete_avatar_clears_field_in_db(self, mock_delete, mock_exists):
        # اول آپلود کن
        with patch(
            "django.core.files.storage.default_storage.save",
            return_value="avatars/test.jpg",
        ):
            response = self.client.put(
                self.PUT_URL,
                {"avatar": generate_image()},
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # بعد حذف کن
        response = self.client.delete(self.DELETE_URL)

        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT],
        )
        self.user.refresh_from_db()
        self.assertFalse(bool(self.user.avatar))

    def test_unauthenticated_delete_returns_401(self):
        self.client.credentials()
        response = self.client.delete(self.DELETE_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ─────────────────────────────────────────────────────────────
#  5. Delete Account
# ─────────────────────────────────────────────────────────────


class DeleteAccountTests(APITestCase):
    """
    DELETE /api/v1/me/delete/

    طبق کد، این یه soft delete هست که OTP با purpose=reset لازم داره.

    Tests:
      - بدون token → 401
      - بدون OTP → 400
      - با OTP درست → 204 + کاربر غیرفعال می‌شه
      - با OTP اشتباه → 400
      - با OTP منقضی → 400
      - بعد از delete، login ممکن نیست
    """

    URL = reverse("users:delete-account")
    LOGIN_URL = reverse("users:login-password")

    def setUp(self):
        super().setUp()
        self.user = create_active_user(
            phone_number="09170000005",
            password="Pass#12345",
        )
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.user))

    def _create_reset_otp(self, expired=False):
        from tests.test_otp import create_otp  # import local helper

        return create_otp(self.user, purpose="reset", expired=expired)

    def test_unauthenticated_returns_401(self):
        self.client.credentials()
        response = self.client.delete(self.URL, {"code": "123456"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_code_returns_400(self):
        response = self.client.delete(self.URL, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_otp_returns_error(self):
        OTPCode.objects.create(
            user=self.user,
            code="123456",
            purpose="reset",
        )

        response = self.client.delete(self.URL, {"code": "000000"})
        self.assertNotEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_expired_otp_returns_error(self):
        from datetime import timedelta

        from django.utils import timezone

        otp = OTPCode.objects.create(
            user=self.user,
            code="123456",
            purpose="reset",
        )
        OTPCode.objects.filter(pk=otp.pk).update(
            created_at=timezone.now() - timedelta(minutes=OTPCode.EXPIRE_MINUTES + 1)
        )

        response = self.client.delete(self.URL, {"code": "123456"})
        self.assertNotEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_correct_otp_soft_deletes_account(self):
        """
        بعد از delete موفق، کاربر باید غیرفعال بشه (soft delete).
        نه اینکه از DB پاک بشه.
        """
        OTPCode.objects.create(
            user=self.user,
            code="123456",
            purpose="reset",
        )

        response = self.client.delete(self.URL, {"code": "123456"})

        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT],
        )
        self.user.refresh_from_db()
        # soft delete = غیرفعال شدن، نه پاک شدن
        self.assertFalse(self.user.is_active)
        self.assertTrue(CustomUser.objects.filter(pk=self.user.pk).exists())

    def test_deleted_user_cannot_login(self):
        """
        بعد از delete، حتی با رمز درست نباید login کرد.
        این loop رو می‌بنده.
        """
        OTPCode.objects.create(
            user=self.user,
            code="123456",
            purpose="reset",
        )
        self.client.delete(self.URL, {"code": "123456"})

        login_response = self.client.post(
            self.LOGIN_URL,
            {
                "phone_number": "09170000005",
                "password": "Pass#12345",
            },
        )
        self.assertNotEqual(login_response.status_code, status.HTTP_200_OK)
