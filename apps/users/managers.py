import re

from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):

    def create_user(self, phone_number: str, password=None, **extra_fields):
        if not phone_number:
            raise ValueError(_("شماره تلفن الزامی است"))

        phone_number = self._normalize_phone(phone_number)
        user = self.model(phone_number=phone_number, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.full_clean()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if not extra_fields.get("is_staff"):
            raise ValueError(_("Superuser باید is_staff=True داشته باشد"))
        if not extra_fields.get("is_superuser"):
            raise ValueError(_("Superuser باید is_superuser=True داشته باشد"))

        return self.create_user(phone_number, password, **extra_fields)

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        phone = phone.strip().replace(" ", "").replace("-", "")
        phone = re.sub(r"^\+98", "0", phone)
        phone = re.sub(r"^98(?=9)", "0", phone)
        return phone
