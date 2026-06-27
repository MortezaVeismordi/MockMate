import logging
from typing import Optional, Tuple

import requests

from django.conf import settings

from .base import BaseNotificationProvider

logger = logging.getLogger(__name__)


class ConsoleSMSProvider(BaseNotificationProvider):
    """
    پرووایدر محیط توسعه (Development)
    پیامک‌ها را با ساختار بصری واضح در ترمینال کانتینر داکر چاپ می‌کند.
    """

    def send(
        self, recipient: str, body: str, title: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        # لاگ استاندارد برای سیستم‌های مانیتورینگ داخلی داکر
        logger.info(f"[Console-SMS] Simulating SMS delivery to {recipient}")

        # شبیه‌سازی بصری خروجی پیامک برای دولوپر
        print("\n" + "═" * 60)
        print(" 📱 [SMS CONSOLE PROVIDER] — DEV MODE")
        print(f" 👤 گیرنده: {recipient}")
        if title:
            print(f" 📌 عنوان/الگو: {title}")
        print(f" ✉️  متن پیام:\n\n {body}\n")
        print("═" * 60 + "\n")

        # بازگرداندن وضعیت موفقیت، شناسه فرضی پیگیری و خطای خالی
        return True, "mock_sms_id_dev_only", None


class KavenegarSMSProvider(BaseNotificationProvider):
    """
    پرووایدر محیط عملیاتی (Production)
    اتصال مستقیم و پایدار به وب‌سرویس REST API پنل کاوه‌نگار با مدیریت استثناها.
    """

    def send(
        self, recipient: str, body: str, title: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        api_key = getattr(settings, "KAVENEGAR_API_KEY", "")
        sender = getattr(settings, "KAVENEGAR_SENDER", "")

        # ۱. مکانیزم Fail-Fast در صورتی که کلید در پروداکشن مقداردهی نشده باشد
        if not api_key:
            error_msg = "Kavenegar API key is missing or empty in Django settings."
            logger.critical(f"[Kavenegar-SMS] Environment Error: {error_msg}")
            return False, None, error_msg

        # آماده‌سازی مستندات و پارامترهای ارسالی به کاوه‌نگار
        url = f"https://api.kavenegar.com/v1/{api_key}/sms/send.json"
        payload = {"receptor": recipient, "sender": sender, "message": body}

        logger.info(f"[Kavenegar-SMS] Sending actual SMS to {recipient} via API.")

        try:
            # ۲. ست کردن تهاجمی Timeout (اتصال در ۵ ثانیه، خواندن داده در ۱۰ ثانیه) برای جلوگیری از فریز شدن کانتینر سلری
            response = requests.post(url, data=payload, timeout=(5.0, 10.0))

            # ۳. پارس کردن امن فرمت JSON خروجی
            try:
                result = response.json()
            except ValueError:
                error_msg = f"Kavenegar returned invalid JSON. HTTP Status: {response.status_code}"
                logger.error(f"[Kavenegar-SMS] Response Parsing Error: {error_msg}")
                return False, None, error_msg

            # ۴. بررسی لایه وضعیت خروجی کاوه‌نگار بر اساس مستندات رسمی
            return_meta = result.get("return", {})
            status_code = return_meta.get("status")
            response_msg = return_meta.get("message", "No message provided")

            if response.status_code == 200 and status_code == 200:
                entries = result.get("entries", [])
                # دریافت شناسه پیامک برای پیگیری‌های قانونی یا مانیتورینگ دلیوری
                message_id = (
                    str(entries[0].get("messageid"))
                    if entries
                    else "kavenegar_fallback_id"
                )

                logger.info(
                    f"[Kavenegar-SMS] SMS delivered successfully to {recipient}. Provider ID: {message_id}"
                )
                return True, message_id, None

            else:
                # خطای منطقی از سمت سرورهای کاوه‌نگار (مثل کمبود اعتبار، مسدود بودن خط گیرنده و...)
                error_msg = f"API Error Code {status_code}: {response_msg}"
                logger.error(f"[Kavenegar-SMS] Business Logic Refusal: {error_msg}")
                return False, None, error_msg

        # ۵. مدیریت تخصصی تمام استثناهای احتمالی لایه شبکه (Network I/O)
        except requests.exceptions.Timeout:
            error_msg = "Connection timed out while reaching Kavenegar API."
            logger.error(f"[Kavenegar-SMS] Timeout Exception: {error_msg}")
            return False, None, error_msg

        except requests.exceptions.ConnectionError:
            error_msg = "Network connection failed or DNS resolution error."
            logger.error(f"[Kavenegar-SMS] Connection Exception: {error_msg}")
            return False, None, error_msg

        except requests.exceptions.RequestException as e:
            error_msg = f"Unexpected requests transport error: {str(e)}"
            logger.error(f"[Kavenegar-SMS] Request General Exception: {error_msg}")
            return False, None, error_msg
