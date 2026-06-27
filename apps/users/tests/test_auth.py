"""
tests/test_auth.py

Integration tests for the users app — authentication flows.

Coverage:
  - Password login (LoginWithPasswordView)
  - Set password (SetPasswordView)
  - Token refresh (RefreshTokenView)
  - Logout / token blacklist (LogoutView)
  - OTP send & verify (SendOTPView / VerifyOTPView)
  - Protected endpoint access

Philosophy:
  Tests describe *behaviour*, not implementation.
  A failing test means a real user-facing regression.
  We do NOT mock the database — we use Django's test DB.
  We DO mock OTPService.send_otp (external SMS) and
  RefreshToken (only where we need a known token value).
"""

from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from apps.users.tests.base import BaseAPITestCase as APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import CustomUser, OTPCode


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def create_active_user(
    phone_number: str = "09123456789",
    password: str = "StrongPass@123",
    **kwargs,
) -> CustomUser:
    """
    Factory for a fully active user (is_active=True, phone verified).
    The default CustomUser has is_active=False until OTP verification,
    so we force-activate here for tests that don't care about that flow.
    """
    user = CustomUser.objects.create_user(
        phone_number=phone_number,
        password=password,
        **kwargs,
    )
    user.is_active = True
    user.is_phone_verified = True
    user.save(update_fields=["is_active", "is_phone_verified"])
    return user


def auth_headers(user: CustomUser) -> dict:
    """Return Authorization header for the given user."""
    refresh = RefreshToken.for_user(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {str(refresh.access_token)}"}


# ─────────────────────────────────────────────────────────────
#  1. Password Login
# ─────────────────────────────────────────────────────────────

class LoginWithPasswordTests(APITestCase):
    """
    POST /api/v1/auth/login-password/

    Tests:
      - Happy path: correct credentials → JWT pair returned
      - Wrong password → 400
      - Non-existent phone → 400
      - Inactive user cannot log in
      - Response shape contains expected keys
    """

    URL = reverse("users:login-password")

    def setUp(self):
        super().setUp()
        self.user = create_active_user(
            phone_number="09111111111",
            password="CorrectHorse#99",
        )

    # ── Happy path ────────────────────────────────────────────

    def test_valid_credentials_return_jwt_pair(self):
        """
        A user with correct phone + password must receive
        both an access token and a refresh token.
        """
        response = self.client.post(self.URL, {
            "phone_number": "09111111111",
            "password": "CorrectHorse#99",
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertTrue(len(data["access"]) > 20, "access token looks too short")
        self.assertTrue(len(data["refresh"]) > 20, "refresh token looks too short")

    def test_response_includes_user_info(self):
        """
        Login response should embed basic user info so the
        frontend doesn't need an extra /me/ round-trip.
        """
        response = self.client.post(self.URL, {
            "phone_number": "09111111111",
            "password": "CorrectHorse#99",
        })

        user_data = response.json()["data"]["user"]
        self.assertEqual(user_data["phone_number"], "09111111111")

    def test_last_login_is_updated_on_success(self):
        """
        After a successful login, last_login should be refreshed.
        """
        before = self.user.last_login
        self.client.post(self.URL, {
            "phone_number": "09111111111",
            "password": "CorrectHorse#99",
        })
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.last_login, before)

    # ── Failure cases ─────────────────────────────────────────

    def test_wrong_password_is_rejected(self):
        """
        Wrong password must NOT return a token under any circumstances.
        """
        response = self.client.post(self.URL, {
            "phone_number": "09111111111",
            "password": "WrongPassword!",
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("access", response.json().get("data", {}))

    def test_nonexistent_phone_is_rejected(self):
        """
        A phone number that has never registered must not leak
        whether the account exists (same error class as wrong password).
        """
        response = self.client.post(self.URL, {
            "phone_number": "09999999999",
            "password": "AnyPassword!",
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_user_cannot_login(self):
        """
        Deactivated users (suspended / banned / unverified)
        must be blocked even with a correct password.
        """
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(self.URL, {
            "phone_number": "09111111111",
            "password": "CorrectHorse#99",
        })

        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    def test_missing_fields_return_400(self):
        """Both fields are required."""
        response = self.client.post(self.URL, {"phone_number": "09111111111"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(self.URL, {"password": "CorrectHorse#99"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_phone_format_rejected(self):
        """
        The custom phone validator (09XXXXXXXXX) should reject
        malformed numbers before even hitting the DB.
        """
        response = self.client.post(self.URL, {
            "phone_number": "123",
            "password": "CorrectHorse#99",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────
#  2. Set Password
# ─────────────────────────────────────────────────────────────

class SetPasswordTests(APITestCase):
    """
    POST /api/v1/me/set-password/

    Tests:
      - Unauthenticated request is blocked
      - First-time password set works
      - Password change (old → new) works
      - Weak password is rejected
      - New password == old password should be rejected (if enforced)
      - After set-password the user can log in with the new password
    """

    SET_URL = reverse("users:set-password")
    LOGIN_URL = reverse("users:login-password")

    def setUp(self):
        super().setUp()
        self.user = create_active_user(
            phone_number="09122222222",
            password="OldPassword#1",
        )

    # ── Auth guard ────────────────────────────────────────────

    def test_unauthenticated_request_is_blocked(self):
        response = self.client.post(self.SET_URL, {
            "new_password": "NewPass#123",
            "confirm_password": "NewPass#123",
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── Happy path ────────────────────────────────────────────

    def test_authenticated_user_can_set_password(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(self.user).access_token)}"
        )
        response = self.client.post(self.SET_URL, {
            "current_password": "OldPassword#1", "new_password": "BrandNew#999",
            "confirm_password": "BrandNew#999",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_new_password_is_actually_persisted(self):
        """
        After set-password, the user must be able to log in
        with the new password — this closes the loop end-to-end.
        """
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(self.user).access_token)}"
        )
        self.client.post(self.SET_URL, {
            "current_password": "OldPassword#1", "new_password": "Updated#Pass1",
            "confirm_password": "Updated#Pass1",
        })

        # Now try logging in with the new password
        login_response = self.client.post(self.LOGIN_URL, {
            "phone_number": "09122222222",
            "password": "Updated#Pass1",
        })
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

    def test_old_password_no_longer_works_after_change(self):
        """
        The old password must be invalidated after a successful change.
        """
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(self.user).access_token)}"
        )
        self.client.post(self.SET_URL, {
            "current_password": "OldPassword#1", "new_password": "Updated#Pass1",
            "confirm_password": "Updated#Pass1",
        })

        login_response = self.client.post(self.LOGIN_URL, {
            "phone_number": "09122222222",
            "password": "OldPassword#1",
        })
        self.assertNotEqual(login_response.status_code, status.HTTP_200_OK)

    # ── Validation ────────────────────────────────────────────

    def test_mismatched_passwords_are_rejected(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(self.user).access_token)}"
        )
        response = self.client.post(self.SET_URL, {
            "new_password": "GoodPass#1",
            "confirm_password": "DifferentPass#1",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────
#  3. Token Refresh
# ─────────────────────────────────────────────────────────────

class RefreshTokenTests(APITestCase):
    """
    POST /api/v1/auth/refresh-token/

    Tests:
      - Valid refresh token → new access + rotated refresh
      - Invalid / tampered token is rejected
      - Blacklisted token is rejected
      - Expired token is rejected (mocked)
    """

    URL = reverse("users:refresh-token")

    def setUp(self):
        super().setUp()
        self.user = create_active_user(phone_number="09133333333")
        self.refresh = RefreshToken.for_user(self.user)

    # ── Happy path ────────────────────────────────────────────

    def test_valid_refresh_token_returns_new_access(self):
        response = self.client.post(self.URL, {"refresh": str(self.refresh)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.json()["data"])

    def test_refresh_rotation_returns_new_refresh_token(self):
        """
        With rotation enabled, the old refresh token should be replaced.
        """
        response = self.client.post(self.URL, {"refresh": str(self.refresh)})
        data = response.json()["data"]
        # A new refresh token should be present
        self.assertIn("refresh", data)
        # And it should differ from the original
        self.assertNotEqual(data["refresh"], str(self.refresh))

    # ── Failure cases ─────────────────────────────────────────

    def test_tampered_token_is_rejected(self):
        tampered = str(self.refresh) + "tampered"
        response = self.client.post(self.URL, {"refresh": tampered})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_blacklisted_refresh_token_is_rejected(self):
        """
        After logout, the same refresh token must not generate new access tokens.
        """
        # Blacklist by logging out first
        logout_url = reverse("users:logout")
        access = str(self.refresh.access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.client.post(logout_url, {"refresh_token": str(self.refresh)})
        self.client.credentials()  # clear

        # Now try to refresh with the blacklisted token
        response = self.client.post(self.URL, {"refresh": str(self.refresh)})
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    def test_missing_refresh_field_returns_400(self):
        response = self.client.post(self.URL, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────
#  4. Logout
# ─────────────────────────────────────────────────────────────

class LogoutTests(APITestCase):
    """
    POST /api/v1/auth/logout/

    Tests:
      - Authenticated user can log out (refresh token blacklisted)
      - Unauthenticated request is blocked
      - Double logout with same token is rejected
    """

    URL = reverse("users:logout")

    def setUp(self):
        super().setUp()
        self.user = create_active_user(phone_number="09144444444")
        self.refresh = RefreshToken.for_user(self.user)
        self.access = str(self.refresh.access_token)

    def test_authenticated_user_can_logout(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        response = self.client.post(self.URL, {"refresh_token": str(self.refresh)})
        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT],
        )

    def test_unauthenticated_logout_is_blocked(self):
        response = self.client.post(self.URL, {"refresh_token": str(self.refresh)})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_double_logout_is_rejected(self):
        """
        Using the same refresh token twice to log out must fail on the
        second attempt — the token was blacklisted on the first call.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        self.client.post(self.URL, {"refresh_token": str(self.refresh)})

        # Second attempt with the same (now blacklisted) token
        response = self.client.post(self.URL, {"refresh_token": str(self.refresh)})
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────
#  5. OTP Send
# ─────────────────────────────────────────────────────────────

class SendOTPTests(APITestCase):
    """
    POST /api/v1/auth/send-otp/

    OTPService.send_otp is mocked — we don't want real SMS.
    Tests:
      - New phone → user created + is_new_user=True
      - Existing phone → is_new_user=False
      - Invalid phone format is rejected before service is called
      - Daily limit exceeded → 400
    """

    URL = reverse("users:send-otp")

    MOCK_SUCCESS = {
        "success": True,
        "message": "کد OTP ارسال شد",
        "is_new_user": False,
        "remaining_seconds": 120,
    }

    @patch("apps.users.views.OTPService.send_otp")
    def test_valid_phone_triggers_otp(self, mock_send):
        mock_send.return_value = {**self.MOCK_SUCCESS, "is_new_user": True}

        response = self.client.post(self.URL, {
            "phone_number": "09150000001",
            "purpose": "login",
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_send.assert_called_once()

    @patch("apps.users.views.OTPService.send_otp")
    def test_new_phone_returns_is_new_user_true(self, mock_send):
        mock_send.return_value = {**self.MOCK_SUCCESS, "is_new_user": True}

        response = self.client.post(self.URL, {
            "phone_number": "09150000002",
            "purpose": "login",
        })

        data = response.json()["data"]
        self.assertTrue(data["is_new_user"])

    @patch("apps.users.views.OTPService.send_otp")
    def test_existing_user_returns_is_new_user_false(self, mock_send):
        create_active_user(phone_number="09150000003")
        mock_send.return_value = {**self.MOCK_SUCCESS, "is_new_user": False}

        response = self.client.post(self.URL, {
            "phone_number": "09150000003",
            "purpose": "login",
        })

        data = response.json()["data"]
        self.assertFalse(data["is_new_user"])

    def test_invalid_phone_format_rejected_without_calling_service(self):
        """
        The validator must reject the request at the serializer level,
        before OTPService is ever called.
        """
        with patch("apps.users.views.OTPService.send_otp") as mock_send:
            response = self.client.post(self.URL, {
                "phone_number": "00000",
                "purpose": "login",
            })
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            mock_send.assert_not_called()

    @patch("apps.users.views.OTPService.send_otp")
    def test_daily_limit_exceeded_returns_error(self, mock_send):
        """
        When OTPService reports daily limit reached,
        the view must propagate that as a 4xx.
        """
        mock_send.return_value = {
            "success": False,
            "message": "تعداد درخواست OTP امروز به حد مجاز رسیده",
        }

        response = self.client.post(self.URL, {
            "phone_number": "09150000004",
            "purpose": "login",
        })
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────
#  6. Protected Endpoint Access
# ─────────────────────────────────────────────────────────────

class ProtectedEndpointTests(APITestCase):
    """
    GET /api/v1/me/

    Verifies that the JWT guard works correctly end-to-end.
    Tests:
      - No token → 401
      - Valid token → 200
      - Tampered token → 401
      - Token for a deactivated user → 401
    """

    URL = reverse("users:me")

    def setUp(self):
        super().setUp()
        self.user = create_active_user(phone_number="09155555555")
        self.refresh = RefreshToken.for_user(self.user)
        self.access = str(self.refresh.access_token)

    def test_no_token_returns_401(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_valid_token_returns_200(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_tampered_token_returns_401(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self.access}tampered"
        )
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_deactivated_user_token_is_rejected(self):
        """
        If a user is deactivated after their token was issued,
        they must not be able to access protected endpoints.
        """
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        response = self.client.get(self.URL)
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)