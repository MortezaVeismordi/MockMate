import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

# ── نقشه status code → پیام فارسی ──────────────
STATUS_MESSAGES = {
    status.HTTP_400_BAD_REQUEST:            "خطا در اعتبارسنجی",
    status.HTTP_401_UNAUTHORIZED:           "احراز هویت نشده‌اید",
    status.HTTP_403_FORBIDDEN:              "دسترسی ندارید",
    status.HTTP_404_NOT_FOUND:              "یافت نشد",
    status.HTTP_405_METHOD_NOT_ALLOWED:     "متد مجاز نیست",
    status.HTTP_429_TOO_MANY_REQUESTS:      "تعداد درخواست بیش از حد مجاز",
}


def custom_exception_handler(exc, context):
    """
    تمام خطاهای DRF رو به فرمت یکسان تبدیل میکنه:
    {
        "success": false,
        "message": "...",
        "errors": { ... }   ← فقط در صورت وجود
    }
    """
    response = drf_exception_handler(exc, context)

    # اگه DRF هندل نکرد → None برگردون (500 پیش‌فرض جنگو)
    if response is None:
        logger.exception(
            "Unhandled exception in %s",
            context.get("view", "unknown"),
        )
        return Response(
            {
                "success": False,
                "message": "خطای داخلی سرور",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # ── 403 → 401 وقتی کاربر احراز هویت نشده ─────────
    # وقتی هدر Authorization غیبه، JWT authenticator silently
    # None برمیگردونه و IsAuthenticated یه PermissionDenied (403)
    # پرتاب میکنه. ما اینجا تبدیلش میکنیم به 401.
    request = context.get("request")
    if (
        response.status_code == status.HTTP_403_FORBIDDEN
        and request is not None
        and not getattr(request.user, "is_authenticated", False)
    ):
        response.status_code = status.HTTP_401_UNAUTHORIZED

    # ── پیام مناسب بر اساس status code ─────────
    message = STATUS_MESSAGES.get(
        response.status_code,
        "خطایی رخ داد",
    )

    # ── ساخت body یکسان ─────────────────────────
    body = {
        "success": False,
        "message": message,
    }

    # اگه DRF خطای validation برگردونده → داخل errors بذار
    if response.data:
        # DRF گاهی لیست میده، گاهی دیکشنری
        if isinstance(response.data, dict):
            body["errors"] = response.data
        elif isinstance(response.data, list):
            body["errors"] = {"detail": response.data}
        else:
            body["errors"] = {"detail": str(response.data)}

    response.data = body
    return response
