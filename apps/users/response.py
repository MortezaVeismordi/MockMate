from rest_framework.response import Response
from rest_framework import status as http_status


class APIResponse:
    """
    فرمت یکسان برای تمام Responseهای API.

    Success:
        {
            "success": true,
            "message": "عملیات موفق",
            "data": { ... }
        }

    Error:
        {
            "success": false,
            "message": "خطا",
            "errors": { ... }
        }
    """

    @staticmethod
    def success(
        data=None,
        message: str = "",
        status: int = http_status.HTTP_200_OK,
    ) -> Response:
        body = {
            "success": True,
            "message": message,
        }
        if data is not None:
            body["data"] = data

        return Response(body, status=status)

    @staticmethod
    def created(
        data=None,
        message: str = "",
    ) -> Response:
        return APIResponse.success(
            data=data,
            message=message,
            status=http_status.HTTP_201_CREATED,
        )

    @staticmethod
    def no_content(message: str = "") -> Response:
        return Response(
            {"success": True, "message": message},
            status=http_status.HTTP_204_NO_CONTENT,
        )

    @staticmethod
    def error(
        message: str = "",
        errors=None,
        status: int = http_status.HTTP_400_BAD_REQUEST,
    ) -> Response:
        body = {
            "success": False,
            "message": message,
        }
        if errors is not None:
            body["errors"] = errors

        return Response(body, status=status)

    @staticmethod
    def not_found(message: str = "یافت نشد") -> Response:
        return APIResponse.error(
            message=message,
            status=http_status.HTTP_404_NOT_FOUND,
        )

    @staticmethod
    def forbidden(message: str = "دسترسی ندارید") -> Response:
        return APIResponse.error(
            message=message,
            status=http_status.HTTP_403_FORBIDDEN,
        )

    @staticmethod
    def unauthorized(message: str = "احراز هویت نشده‌اید") -> Response:
        return APIResponse.error(
            message=message,
            status=http_status.HTTP_401_UNAUTHORIZED,
        )

    @staticmethod
    def throttled(message: str = "تعداد درخواست بیش از حد مجاز") -> Response:
        return APIResponse.error(
            message=message,
            status=http_status.HTTP_429_TOO_MANY_REQUESTS,
        )