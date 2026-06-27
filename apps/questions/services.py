import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.llm.client import LLMClient
from apps.interviews.models import UserAnswer
from apps.questions.models import Question

logger = logging.getLogger(__name__)


def submit_and_grade_answer(
    *, user_id: int, session_id: int, question_id: int, user_answer_text: str
) -> UserAnswer:
    # ۱. اعتبارسنجی‌های اولیه بیزینس (Business Validation)
    if not user_answer_text.strip():
        raise ValidationError("پاسخ ارسال شده نمی‌تواند خالی باشد.")

    try:
        question = Question.objects.get(id=question_id, is_active=True)
    except Question.DoesNotExist:
        raise ValidationError("سوال مورد نظر یافت نشد یا در حال حاضر غیرفعال است.")

    # فقط عملیات ساخت رکورد که به دیتابیس مربوطه اتمیک میشه
    with transaction.atomic():
        user_answer_record = UserAnswer.objects.create(
            user_id=user_id,
            session_id=session_id,
            question=question,
            answer_text=user_answer_text,
            status=UserAnswer.Status.PENDING,
        )

    ai_prompt = _build_evaluation_prompt(
        question=question, user_answer=user_answer_text
    )

    try:
        ai_analysis = LLMClient.evaluate_default(ai_prompt)

        user_answer_record.score = ai_analysis.get("score", 0)
        user_answer_record.strengths = ai_analysis.get("strengths", [])
        user_answer_record.weaknesses = ai_analysis.get("weaknesses", [])
        user_answer_record.feedback = ai_analysis.get(
            "model_improvement_suggestion", ""
        )
        user_answer_record.status = UserAnswer.Status.GRADED
        user_answer_record.save()

        logger.info(
            f"Successfully graded answer {user_answer_record.id} for user {user_id} via AI."
        )

    except Exception as exc:
        logger.error(
            f"AI Grading failed for answer {user_answer_record.id}. Error: {str(exc)}",
            exc_info=True,
        )
        user_answer_record.status = UserAnswer.Status.FAILED
        user_answer_record.error_log = str(exc)
        user_answer_record.save()  # این Save حالا چون بیرون اتمیکه، Commit میشه و باقی میمونه

        # خط آخر مربوط به set_rollback هم از اینجا حذف شد چون دیگه تراکنش سراسری نداریم
        exc_clean = exc.__class__(
            f"در حال حاضر ارتباط با موتور هوش مصنوعی برقرار نشد. پاسخ شما ذخیره شد و بعداً تصحیح می‌شود. (Original: {str(exc)})"
        )
        raise exc_clean

    return user_answer_record


def _build_evaluation_prompt(*, question: Question, user_answer: str) -> str:
    """
    یک متد کمکی (Private) کاملاً کپسوله‌شده برای ساخت پرامپت ارزیابی تمیز و یکدست.
    """
    return f"""
    You are an expert, cynical Backend and DevOps Technical Interviewer.
    Evaluate the candidate's answer strictly based on the provided reference answer and professional standards.

    [Question Title]
    {question.title}

    [Question Context / Body]
    {question.body}

    [Official Reference Answer]
    {question.reference_answer}

    [Expected AI Evaluation Criteria]
    {question.ai_evaluation_criteria}

    [Candidate's Answer]
    {user_answer}

    Your response must be a single, valid JSON object. Do NOT wrap it in markdown blocks like ```json ... ```.
    Expected JSON Structure:
    {{
        "score": <int between 0 and 100>,
        "strengths": [<list of short strings highlighting what they got right>],
        "weaknesses": [<list of short strings highlighting what important concepts they missed or got wrong>],
        "model_improvement_suggestion": "<clear, constructive feedback in Persian or English on how they can improve>"
    }}
    """
