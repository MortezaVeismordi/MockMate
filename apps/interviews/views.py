# apps/interviews/views.py
# =============================================================================
# Interview Views — REST Endpoints
# =============================================================================

import logging

from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.views import APIView

from apps.users.response import APIResponse
from .models import InterviewSession
from .selectors import SessionSelector, InterviewStatsSelector
from .serializers import (
    InterviewSessionCreateSerializer,
    InterviewSessionListSerializer,
    InterviewSessionDetailSerializer,
    InterviewReportSerializer,
    UserAnswerEvaluationSerializer,
)
from .services import InterviewSetupService

logger = logging.getLogger(__name__)


# =============================================================================
#  Session Views
# =============================================================================

class InterviewSessionCreateView(APIView):
    """
    POST /api/v1/interviews/
    ساختن session جدید + شروع مصاحبه
    response: uuid برای اتصال WebSocket
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = InterviewSessionCreateSerializer(data=request.data)

        if not serializer.is_valid():
            return APIResponse.error(
                message=_("اطلاعات وارد شده نامعتبر است."),
                errors=serializer.errors,
            )

        try:
            session = InterviewSetupService.create_session(
                user=request.user,
                **serializer.validated_data,
            )
        except ValueError as exc:
            return APIResponse.error(
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.error(
                "Session creation failed | user=%s | error=%s",
                request.user.pk, str(exc),
                exc_info=True,
            )
            return APIResponse.error(
                message=_("خطا در ایجاد مصاحبه."),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return APIResponse.created(
            data={
                "uuid"           : str(session.uuid),
                "status"         : session.status,
                "target_position": session.target_position,
                "total_questions": session.total_questions,
                "ws_url"         : f"/ws/interviews/{session.uuid}/",
            },
            message=_("مصاحبه با موفقیت ایجاد شد."),
        )


class InterviewSessionListView(APIView):
    """
    GET /api/v1/interviews/
    تاریخچه مصاحبه‌های کاربر
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_filter = request.query_params.get("status")

        sessions = SessionSelector.get_user_sessions(
            user=request.user,
            status=status_filter,
            limit=int(request.query_params.get("limit", 20)),
        )

        serializer = InterviewSessionListSerializer(sessions, many=True)

        return APIResponse.success(
            data={
                "results": serializer.data,
                "count"  : sessions.count() if hasattr(sessions, "count") else len(serializer.data),
            },
            message=_("لیست مصاحبه‌ها."),
        )


class InterviewSessionDetailView(APIView):
    """
    GET    /api/v1/interviews/<uuid>/  ← وضعیت فعلی
    DELETE /api/v1/interviews/<uuid>/  ← abandon کردن
    """
    permission_classes = [IsAuthenticated]

    def _get_session_or_403(self, uuid: str, user):
        session = SessionSelector.get_by_uuid(uuid)

        if not session:
            return None, APIResponse.error(
                message=_("مصاحبه یافت نشد."),
                status=status.HTTP_404_NOT_FOUND,
            )

        if session.user_id != user.pk:
            return None, APIResponse.error(
                message=_("دسترسی غیرمجاز."),
                status=status.HTTP_403_FORBIDDEN,
            )

        return session, None

    def get(self, request, uuid: str):
        session, error = self._get_session_or_403(uuid, request.user)
        if error:
            return error

        serializer = InterviewSessionDetailSerializer(session)
        return APIResponse.success(data=serializer.data)

    def delete(self, request, uuid: str):
        session, error = self._get_session_or_403(uuid, request.user)
        if error:
            return error

        if not session.is_active and session.status != InterviewSession.Status.SETUP:
            return APIResponse.error(
                message=_("فقط مصاحبه‌های فعال قابل لغو هستند."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.transition_to(InterviewSession.Status.ABANDONED)

        logger.info(
            "Session abandoned | uuid=%s | user=%s",
            uuid, request.user.pk,
        )

        return APIResponse.success(
            message=_("مصاحبه با موفقیت لغو شد."),
        )


# =============================================================================
#  Active Session View
# =============================================================================

class ActiveSessionView(APIView):
    """
    GET /api/v1/interviews/active/
    session فعال فعلی کاربر — برای resume کردن
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        session = SessionSelector.get_active_session(request.user)

        if not session:
            return APIResponse.success(
                data=None,
                message=_("مصاحبه فعالی وجود ندارد."),
            )

        serializer = InterviewSessionDetailSerializer(session)
        return APIResponse.success(
            data=serializer.data,
            message=_("مصاحبه فعال یافت شد."),
        )


# =============================================================================
#  Report View
# =============================================================================

class InterviewReportView(APIView):
    """
    GET /api/v1/interviews/<uuid>/report/
    گزارش کامل نهایی — فقط اگه COMPLETED باشه
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, uuid: str):
        session = SessionSelector.get_by_uuid(uuid)

        if not session:
            return APIResponse.error(
                message=_("مصاحبه یافت نشد."),
                status=status.HTTP_404_NOT_FOUND,
            )

        if session.user_id != request.user.pk:
            return APIResponse.error(
                message=_("دسترسی غیرمجاز."),
                status=status.HTTP_403_FORBIDDEN,
            )

        if session.status != InterviewSession.Status.COMPLETED:
            return APIResponse.error(
                message=_("گزارش مصاحبه هنوز آماده نشده است."),
                errors={"status": session.status},
                status=status.HTTP_202_ACCEPTED,
            )

        serializer = InterviewReportSerializer(session)
        return APIResponse.success(data=serializer.data)


# =============================================================================
#  User Stats View
# =============================================================================

class UserInterviewStatsView(APIView):
    """
    GET /api/v1/interviews/stats/
    آمار کلی کاربر از همه مصاحبه‌هاش — داشبورد
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stats = InterviewStatsSelector.get_user_overall_stats(request.user)
        trend = InterviewStatsSelector.get_score_trend(
            request.user,
            last_n=int(request.query_params.get("last_n", 10)),
        )

        return APIResponse.success(
            data={
                "overview": stats,
                "trend"   : trend,
            },
        )


# =============================================================================
#  Admin Views
# =============================================================================

class AdminSessionListView(APIView):
    """
    GET /api/v1/interviews/admin/sessions/
    لیست همه sessions با فیلتر — فقط ادمین
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        status_filter = request.query_params.get("status")
        user_id       = request.query_params.get("user_id")
        limit         = int(request.query_params.get("limit", 50))

        qs = InterviewSession.objects.select_related("user").order_by("-created_at")

        if status_filter:
            qs = qs.filter(status=status_filter)

        if user_id:
            qs = qs.filter(user_id=user_id)

        qs = qs[:limit]

        serializer = InterviewSessionListSerializer(qs, many=True)
        return APIResponse.success(
            data={
                "results": serializer.data,
                "count"  : len(serializer.data),
            },
        )


class AdminSessionDetailView(APIView):
    """
    GET /api/v1/interviews/admin/sessions/<uuid>/
    جزئیات کامل یه session — فقط ادمین
    """
    permission_classes = [IsAdminUser]

    def get(self, request, uuid: str):
        session = SessionSelector.get_by_uuid(uuid)

        if not session:
            return APIResponse.error(
                message=_("مصاحبه یافت نشد."),
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = InterviewReportSerializer(session)
        return APIResponse.success(data=serializer.data)


class AdminAnswerDetailView(APIView):
    """
    GET /api/v1/interviews/admin/answers/<pk>/
    جزئیات یه answer برای debug و بررسی ارزیابی
    """
    permission_classes = [IsAdminUser]

    def get(self, request, pk: int):
        from .models import UserAnswer

        try:
            answer = (
                UserAnswer.objects
                .select_related("question", "session", "user")
                .get(pk=pk)
            )
        except UserAnswer.DoesNotExist:
            return APIResponse.error(
                message=_("پاسخ یافت نشد."),
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UserAnswerEvaluationSerializer(answer)

        return APIResponse.success(
            data={
                **serializer.data,
                "raw_evaluation": answer.raw_evaluation,
                "error_log"     : answer.error_log,
                "session_uuid"  : str(answer.session.uuid),
            },
        )


class AdminRetriggerEvaluationView(APIView):
    """
    POST /api/v1/interviews/admin/answers/<pk>/retrigger/
    trigger مجدد ارزیابی یه answer — برای failed یا pending
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        from .models import UserAnswer
        from .tasks import evaluate_answer_task

        try:
            answer = UserAnswer.objects.get(pk=pk)
        except UserAnswer.DoesNotExist:
            return APIResponse.error(
                message=_("پاسخ یافت نشد."),
                status=status.HTTP_404_NOT_FOUND,
            )

        if answer.status == UserAnswer.Status.GRADED:
            return APIResponse.error(
                message=_("این پاسخ قبلاً ارزیابی شده است."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # reset و trigger
        answer.status    = UserAnswer.Status.PENDING
        answer.error_log = ""
        answer.save(update_fields=["status", "error_log"])

        evaluate_answer_task.delay(answer.pk)

        logger.info(
            "Evaluation retriggered | answer=%d | admin=%s",
            pk, request.user.pk,
        )

        return APIResponse.success(
            message=_("ارزیابی مجدداً در صف قرار گرفت."),
        )
        
        
class InterviewSessionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return InterviewSessionListView().get(request)

    def post(self, request):
        return InterviewSessionCreateView().post(request)