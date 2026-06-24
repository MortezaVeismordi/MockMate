import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.questions.models import Question
from apps.interviews.models import UserAnswer
from apps.core.llm.client import LLMClient

logger = logging.getLogger(__name__)

@transaction.atomic
def submit_and_grade_answer(
    *, 
    user_id: int, 
    question_id: int, 
    user_answer_text: str
) -> UserAnswer:
    """
    سرویس انترپرایز و اتمیک برای ثبت پاسخ کاربر و ارزیابی آن توسط هوش مصنوعی.
    
    * Database Atomicity: با decorator اتمیک تضمین می‌کنیم که اگر هر کجای فرآیند 
      (مثل ذخیره دیتابیس) شکست خورد، هیچ دیتای ناقصی ثبت نشود.
    * Presentation Agnostic: ورودی‌ها کاملاً دیتاهای خام پایتون هستند و ربطی به HTTP Request ندارند.
    """
    # ۱. اعتبارسنجی‌های اولیه بیزینس (Business Validation)
    if not user_answer_text.strip():
        raise ValidationError("پاسخ ارسال شده نمی‌تواند خالی باشد.")

    try:
        question = Question.objects.get(id=question_id, is_active=True)
    except Question.DoesNotExist:
        raise ValidationError("سوال مورد نظر یافت نشد یا در حال حاضر غیرفعال است.")

    # ۲. ایجاد رکورد اولیه در دیتابیس (حالت Pending)
    # این کار باعث می‌شود اگر API هوش مصنوعی طول کشید یا تایم‌اوت شد، پاسخ کاربر گم نشود.
    user_answer_record = UserAnswer.objects.create(
        user_id=user_id,
        question=question,
        answer_text=user_answer_text,
        status=UserAnswer.Status.PENDING  # فرض بر داشتن فیلد وضعیت (Pending, Graded, Failed)
    )

    # ۳. آماده‌سازی پرامپت مهندسی‌شده (Prompt Engineering) برای هوش مصنوعی
    ai_prompt = _build_evaluation_prompt(question=question, user_answer=user_answer_text)

    # ۴. صدا زدن کلاینت هوش مصنوعی با مدیریت خطا (Fault Tolerance)
    try:
        ai_analysis = LLMClient.evaluate_default(ai_prompt)
        
        # ۵. به‌روزرسانی رکورد با فیدبک و نمره نهایی هوش مصنوعی
        user_answer_record.score = ai_analysis.get("score", 0)
        user_answer_record.strengths = ai_analysis.get("strengths", [])
        user_answer_record.weaknesses = ai_analysis.get("weaknesses", [])
        user_answer_record.feedback = ai_analysis.get("model_improvement_suggestion", "")
        user_answer_record.status = UserAnswer.Status.GRADED
        user_answer_record.save()

        logger.info(f"Successfully graded answer {user_answer_record.id} for user {user_id} via AI.")
        
    except Exception as exc:
        # در صورت خطای شبکه یا API هوش مصنوعی، تراکنش دیتابیس را خراب نمی‌کنیم
        # بلکه رکورد را در وضعیت FAILED می‌گذاریم تا بعداً قابل Retry یا لاگ‌گیری باشد.
        logger.error(f"AI Grading failed for answer {user_answer_record.id}. Error: {str(exc)}", exc_info=True)
        user_answer_record.status = UserAnswer.Status.FAILED
        user_answer_record.error_log = str(exc)
        user_answer_record.save()
        
        # بر حسب سیاست بیزینس، می‌توانید خطا را بالا ببرید یا یک فیدبک پیش‌فرض برگردانید
        raise ValidationError("در حال حاضر ارتباط با موتور هوش مصنوعی برقرار نشد. پاسخ شما ذخیره شد و بعداً تصحیح می‌شود.")

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