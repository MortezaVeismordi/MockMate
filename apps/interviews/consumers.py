# apps/interviews/consumers.py
# =============================================================================
# Interview WebSocket Consumer
# =============================================================================

import json
import logging
from uuid import UUID

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


# =============================================================================
#  Interview Consumer
# =============================================================================


class InterviewConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer برای مصاحبه real-time.

    URL: ws/interviews/<uuid>/

    Event Types (client → server):
        start           ← شروع مصاحبه
        next_question   ← درخواست سوال بعدی
        submit_answer   ← ارسال پاسخ
        submit_follow_up← پاسخ سوال تعقیبی

    Event Types (server → client):
        connected       ← اتصال برقرار شد
        error           ← خطا
        greeting        ← پیام خوش‌آمدگویی
        question        ← سوال جدید
        follow_up       ← سوال تعقیبی
        answer_received ← پاسخ دریافت شد
        evaluating      ← در حال ارزیابی
        evaluation_done ← ارزیابی تموم شد
        wrap_up         ← جمع‌بندی
        report_ready    ← گزارش آماده‌ست
    """

    # ── Connect ───────────────────────────────────────────────────────────────

    async def connect(self):
        """
        اتصال WebSocket.
        احراز هویت + پیدا کردن session.
        """
        self.session_uuid = self.scope["url_route"]["kwargs"]["uuid"]
        self.room_group_name = f"interview_{self.session_uuid}"
        self.user = self.scope.get("user")

        # ── احراز هویت ───────────────────────────────────────────────────────
        if not self.user or isinstance(self.user, AnonymousUser):
            logger.warning(
                "Unauthenticated WebSocket connection | uuid=%s",
                self.session_uuid,
            )
            await self.close(code=4001)
            return

        # ── پیدا کردن session ────────────────────────────────────────────────
        self.session = await self._get_session(self.session_uuid)

        if not self.session:
            logger.warning(
                "Session not found | uuid=%s | user=%s",
                self.session_uuid,
                self.user.pk,
            )
            await self.close(code=4004)
            return

        # ── چک owner بودن ────────────────────────────────────────────────────
        if self.session.user_id != self.user.pk:
            logger.warning(
                "Unauthorized session access | uuid=%s | user=%s",
                self.session_uuid,
                self.user.pk,
            )
            await self.close(code=4003)
            return

        # ── Join channel group ────────────────────────────────────────────────
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        await self.accept()

        logger.info(
            "WebSocket connected | uuid=%s | user=%s",
            self.session_uuid,
            self.user.pk,
        )

        # ── ارسال وضعیت فعلی session ─────────────────────────────────────────
        await self._send_event(
            "connected",
            {
                "session_uuid": str(self.session.uuid),
                "status": self.session.status,
                "target_position": self.session.target_position,
                "total_questions": self.session.total_questions,
                "current_index": self.session.current_question_index,
            },
        )

    # ── Disconnect ────────────────────────────────────────────────────────────

    async def disconnect(self, close_code: int):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

        logger.info(
            "WebSocket disconnected | uuid=%s | code=%s",
            getattr(self, "session_uuid", "unknown"),
            close_code,
        )

    # ── Receive (client → server) ─────────────────────────────────────────────

    async def receive(self, text_data: str):
        """
        دریافت event از client و routing به handler مناسب.
        """
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_error("فرمت پیام نامعتبر است.")
            return

        event_type = data.get("type")
        payload = data.get("payload", {})

        logger.debug(
            "Event received | uuid=%s | type=%s",
            self.session_uuid,
            event_type,
        )

        # ── Router ───────────────────────────────────────────────────────────
        handlers = {
            "start": self._handle_start,
            "next_question": self._handle_next_question,
            "submit_answer": self._handle_submit_answer,
            "submit_follow_up": self._handle_submit_follow_up,
        }

        handler = handlers.get(event_type)

        if not handler:
            await self._send_error(f"نوع event ناشناخته: {event_type}")
            return

        # ── refresh session قبل از هر action ─────────────────────────────────
        self.session = await self._get_session(self.session_uuid)

        try:
            await handler(payload)
        except ValueError as exc:
            await self._send_error(str(exc))
        except Exception as exc:
            logger.error(
                "Handler error | uuid=%s | type=%s | error=%s",
                self.session_uuid,
                event_type,
                str(exc),
                exc_info=True,
            )
            await self._send_error("خطای داخلی سرور.")

    # ── Event Handlers ────────────────────────────────────────────────────────

    async def _handle_start(self, payload: dict):
        """
        شروع مصاحبه — SETUP → INTRO
        """
        from .models import InterviewSession

        if self.session.status != InterviewSession.Status.SETUP:
            await self._send_error("مصاحبه قبلاً شروع شده است.")
            return

        greeting_msg = await self._start_interview()

        await self._send_event(
            "greeting",
            {
                "content": greeting_msg.content,
                "turn_number": greeting_msg.turn_number,
            },
        )

    async def _handle_next_question(self, payload: dict):
        """
        درخواست سوال بعدی
        """
        from .models import InterviewSession

        if self.session.status not in (
            InterviewSession.Status.INTRO,
            InterviewSession.Status.QUESTIONING,
        ):
            await self._send_error("الان نوبت سوال بعدی نیست.")
            return

        result = await self._ask_next_question()

        if result is None:
            # سوالی نمونده
            wrap_up_msg = await self._wrap_up()
            await self._send_event(
                "wrap_up",
                {
                    "content": wrap_up_msg.content,
                },
            )
            return

        # نوع event رو بر اساس message_type تعیین کن
        await self._send_event(
            "question",
            {
                "content": result["content"],
                "turn_number": result["turn_number"],
                "question_order": result["question_order"],
                "estimated_time": result["estimated_time"],
                "question_type": result["question_type"],
                "code_template": result["code_template"],
            },
        )

    async def _handle_submit_answer(self, payload: dict):
        """
        دریافت پاسخ کاربر و trigger ارزیابی
        """
        from .models import InterviewSession

        if self.session.status != InterviewSession.Status.QUESTIONING:
            await self._send_error("الان نوبت پاسخ دادن نیست.")
            return

        answer_text = payload.get("answer_text", "").strip()
        answer_duration = payload.get("answer_duration")

        if len(answer_text) < 10:
            await self._send_error("پاسخ حداقل ۱۰ کاراکتر باید داشته باشد.")
            return

        answer = await self._submit_answer(answer_text, answer_duration)

        # اعلام دریافت پاسخ
        await self._send_event(
            "answer_received",
            {
                "answer_id": answer.pk,
                "status": answer.status,
            },
        )

        # اعلام شروع ارزیابی
        await self._send_event(
            "evaluating",
            {
                "message": "در حال ارزیابی پاسخ شما...",
            },
        )

    async def _handle_submit_follow_up(self, payload: dict):
        """
        دریافت پاسخ سوال تعقیبی
        """
        from .models import InterviewSession

        if self.session.status != InterviewSession.Status.DRILLING:
            await self._send_error("الان در فاز سوال تعقیبی نیستیم.")
            return

        answer_text = payload.get("answer_text", "").strip()

        if len(answer_text) < 5:
            await self._send_error("پاسخ خیلی کوتاه است.")
            return

        await self._submit_follow_up_answer(answer_text)

        await self._send_event(
            "answer_received",
            {
                "type": "follow_up",
                "message": "پاسخ تعقیبی دریافت شد.",
            },
        )

    # ── Channel Layer Handlers (server → client via group_send) ──────────────
    # این متدها توسط Celery tasks صدا زده میشن

    async def interview_evaluation_done(self, event: dict):
        """
        Celery task ارزیابی تموم کرده → به client بفرست
        """
        await self._send_event("evaluation_done", event["data"])

    async def interview_follow_up(self, event: dict):
        """
        LLM تصمیم گرفته follow-up بپرسه → به client بفرست
        """
        await self._send_event("follow_up", event["data"])

    async def interview_wrap_up(self, event: dict):
        await self._send_event("wrap_up", event["data"])

    async def interview_report_ready(self, event: dict):
        """
        گزارش نهایی آماده‌ست → به client بفرست
        """
        await self._send_event("report_ready", event["data"])

    async def interview_error(self, event: dict):
        await self._send_error(event["message"])

    # ── Database Sync Methods ─────────────────────────────────────────────────

    @database_sync_to_async
    def _get_session(self, uuid: str):
        from .selectors import SessionSelector

        try:
            return SessionSelector.get_by_uuid(UUID(uuid))
        except (ValueError, Exception):
            return None

    @database_sync_to_async
    def _start_interview(self):
        from .services import InterviewConductService

        return InterviewConductService.start_interview(self.session)

    @database_sync_to_async
    def _ask_next_question(self):
        from .services import InterviewConductService

        result = InterviewConductService.ask_next_question(self.session)

        # اگه wrap_up برگشت یعنی سوالی نمونده
        if result.message_type == "wrap_up":
            return None

        # اطلاعات سوال رو از metadata بگیر
        return {
            "content": result.content,
            "turn_number": result.turn_number,
            "question_order": result.metadata.get("question_order", 0),
            "estimated_time": result.metadata.get("estimated_time", 120),
            "question_type": (
                result.related_question.question.question_type
                if result.related_question
                else ""
            ),
            "code_template": (
                result.related_question.question.code_template
                if result.related_question
                else None
            ),
        }

    @database_sync_to_async
    def _submit_answer(self, answer_text: str, answer_duration):
        from .services import InterviewConductService

        return InterviewConductService.submit_answer(
            self.session, answer_text, answer_duration
        )

    @database_sync_to_async
    def _submit_follow_up_answer(self, answer_text: str):
        from .services import InterviewConductService

        InterviewConductService.submit_follow_up_answer(self.session, answer_text)

    @database_sync_to_async
    def _wrap_up(self):
        from .services import InterviewConductService

        return InterviewConductService.wrap_up(self.session)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _send_event(self, event_type: str, data: dict = None):
        await self.send(
            text_data=json.dumps(
                {
                    "type": event_type,
                    "payload": data or {},
                },
                ensure_ascii=False,
            )
        )

    async def _send_error(self, message: str):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "error",
                    "payload": {"message": message},
                },
                ensure_ascii=False,
            )
        )

    # ── Class Method برای notify از Celery ───────────────────────────────────

    @classmethod
    async def notify_evaluation_done(
        cls,
        channel_layer,
        session_uuid: str,
        evaluation_data: dict,
    ):
        """
        از Celery task صدا زده میشه تا نتیجه ارزیابی رو push کنه.
        """
        await channel_layer.group_send(
            f"interview_{session_uuid}",
            {
                "type": "interview.evaluation.done",
                "data": evaluation_data,
            },
        )

    @classmethod
    async def notify_report_ready(
        cls,
        channel_layer,
        session_uuid: str,
        report_data: dict,
    ):
        await channel_layer.group_send(
            f"interview_{session_uuid}",
            {
                "type": "interview.report.ready",
                "data": report_data,
            },
        )
