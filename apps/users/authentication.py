# apps/users/authentication.py
import logging
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import exceptions
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)


class CustomJWTAuthentication(JWTAuthentication):
    """
    کلاس سفارشی احراز هویت برای رفع باگ 403 در نسخه‌های جدید SimpleJWT.
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except (InvalidToken, TokenError) as exc:
            logger.warning(
                "Invalid or expired token provided. Error: %s | Path: %s",
                str(exc),
                request.path,
            )
            raise exceptions.AuthenticationFailed(str(exc)) from exc
        except Exception as exc:
            logger.error(
                "Unexpected authentication error: %s | Path: %s",
                str(exc),
                request.path,
                exc_info=True,
            )
            raise exceptions.AuthenticationFailed("خطا در پردازش توکن.") from exc

    def authenticate_header(self, request):
        """
        تصمیم‌گیری بین کد 401 یا 403.
        """
        header = self.get_header(request)
        
        if header is None:
            return ''  # یعنی 401 بده
            
        raw_token = super().get_raw_token(header)
        if raw_token is None:
            return ''
            
        return super().authenticate_header(request)