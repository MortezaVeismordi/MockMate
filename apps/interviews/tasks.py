# apps/interviews/tasks.py
from asgiref.sync import async_to_sync
from celery import shared_task
from celery.utils.log import get_task_logger
from channels.layers import get_channel_layer
from django.utils import timezone

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    name="apps.interviews.tasks.evaluate_answer",
    queue="interviews",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    time_limit=120,
    soft_time_limit=90,
    acks_late=True,
    reject_on_worker_lost=True,
)
def evaluate_answer_task(self, answer_id: int) -> dict:
    logger.info("Starting evaluation | answer_id=%d", answer_id)

    from .models import UserAnswer
    from .services import EvaluationService

    try:
        answer = UserAnswer.objects.select_related("question", "session", "user").get(pk=answer_id)
    except UserAnswer.DoesNotExist:
        logger.error("Answer not found | answer_id=%d", answer_id)
        return {"status": "not_found", "answer_id": answer_id}

    if answer.status == UserAnswer.Status.GRADED:
        logger.info("Answer already graded | answer_id=%d", answer_id)
        return {"status": "already_graded", "answer_id": answer_id}

    try:
        EvaluationService.evaluate_answer(answer)

        # ── Push نتیجه به WebSocket ────────────────────────────────────────
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"interview_{answer.session.uuid}",
                {
                    "type": "interview.evaluation.done",
                    "data": {
                        "answer_id": answer.pk,
                        "score": answer.score,
                        "feedback": answer.feedback,
                        "strengths": answer.strengths,
                        "weaknesses": answer.weaknesses,
                        "passed": answer.passed,
                        "status": answer.status,
                    },
                },
            )

        logger.info(
            "Evaluation complete | answer_id=%d | score=%s",
            answer_id,
            answer.score,
        )

        # چک همه پاسخ‌های session
        _check_all_evaluated.apply_async(
            args=[answer.session_id],
            countdown=2,
        )

        return {
            "status": "success",
            "answer_id": answer_id,
            "score": answer.score,
        }

    except Exception as exc:
        logger.error(
            "Evaluation failed | answer_id=%d | error=%s",
            answer_id,
            str(exc),
            exc_info=True,
        )

        # ── Push خطا به WebSocket ──────────────────────────────────────────
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"interview_{answer.session.uuid}",
                    {
                        "type": "interview.error",
                        "message": "خطا در ارزیابی پاسخ. مجدداً تلاش می‌شود.",
                    },
                )
        except Exception:
            pass

        raise


@shared_task(
    name="apps.interviews.tasks.check_all_evaluated",
    queue="interviews",
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=30,
    acks_late=True,
)
def _check_all_evaluated(session_id: int) -> dict:
    from .models import InterviewSession, UserAnswer

    try:
        session = InterviewSession.objects.get(pk=session_id)
    except InterviewSession.DoesNotExist:
        return {"status": "not_found"}

    if session.status not in (
        InterviewSession.Status.WRAP_UP,
        InterviewSession.Status.QUESTIONING,
    ):
        return {"status": "skipped"}

    pending_count = UserAnswer.objects.filter(
        session=session,
        status=UserAnswer.Status.PENDING,
    ).count()

    if pending_count > 0:
        return {"status": "pending", "remaining": pending_count}

    if session.status == InterviewSession.Status.WRAP_UP:
        generate_report_task.delay(session_id)
        return {"status": "report_triggered"}

    return {"status": "ok"}


@shared_task(
    bind=True,
    name="apps.interviews.tasks.generate_report",
    queue="interviews",
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    time_limit=180,
    soft_time_limit=150,
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_report_task(self, session_id: int) -> dict:
    logger.info("Generating report | session_id=%d", session_id)

    from .models import InterviewSession
    from .services import ReportService

    try:
        session = InterviewSession.objects.select_related("user").get(pk=session_id)
    except InterviewSession.DoesNotExist:
        return {"status": "not_found"}

    if session.status == InterviewSession.Status.COMPLETED:
        return {"status": "already_completed"}

    session = ReportService.generate_final_report(session)

    # ── Push گزارش آماده به WebSocket ─────────────────────────────────────
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"interview_{session.uuid}",
            {
                "type": "interview.report.ready",
                "data": {
                    "session_uuid": str(session.uuid),
                    "final_score": session.final_score,
                    "message": "گزارش مصاحبه آماده است.",
                },
            },
        )

    logger.info(
        "Report generated | session=%s | score=%.1f",
        session.uuid,
        session.final_score or 0,
    )

    return {
        "status": "success",
        "session_id": session_id,
        "score": session.final_score,
    }


@shared_task(
    name="apps.interviews.tasks.cleanup_abandoned_sessions",
    queue="interviews",
    ignore_result=True,
)
def cleanup_abandoned_sessions() -> dict:
    from .models import InterviewSession

    threshold = timezone.now() - timezone.timedelta(hours=2)

    abandoned = InterviewSession.objects.filter(
        status__in=[
            InterviewSession.Status.INTRO,
            InterviewSession.Status.QUESTIONING,
            InterviewSession.Status.DRILLING,
            InterviewSession.Status.WRAP_UP,
        ],
        started_at__lt=threshold,
    )

    count = abandoned.count()
    if count > 0:
        abandoned.update(status=InterviewSession.Status.ABANDONED)
        logger.info("Abandoned sessions cleaned up | count=%d", count)

    return {"abandoned_count": count}


@shared_task(
    name="apps.interviews.tasks.retry_failed_evaluations",
    queue="interviews",
    ignore_result=True,
)
def retry_failed_evaluations() -> dict:
    from .models import UserAnswer
    from .selectors import AnswerSelector

    failed_answers = AnswerSelector.get_failed_evaluations(limit=10)
    count = 0

    for answer in failed_answers:
        answer.status = UserAnswer.Status.PENDING
        answer.error_log = ""
        answer.save(update_fields=["status", "error_log"])
        evaluate_answer_task.delay(answer.pk)
        count += 1

    if count > 0:
        logger.info("Failed evaluations queued for retry | count=%d", count)

    return {"retried_count": count}
