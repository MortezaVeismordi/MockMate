import logging
import os
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils.text import slugify

from apps.questions.models import Question, QuestionCategory, QuestionOption

logger = logging.getLogger(__name__)


class BaseQuestionAdapter:
    """
    کلاس پایه‌ی انترپرایز برای خط لوله ETL استخراج سوالات از گیت‌هاب.
    این کلاس قوانین کلی، پاک‌سازی داده‌ها، مدیریت خطا و تراکنش‌های امن دیتابیس را تضمین می‌کند.
    """

    def __init__(
        self,
        repo_path: str,
        limit: Optional[int] = None,
        sub_path: Optional[str] = None,
        category: Optional[str] = None,
        level: Optional[str] = None,
    ):
        self.repo_path = repo_path
        self.limit = limit
        self.sub_path = sub_path
        self.category_filter = category
        self.level_filter = level

        # ترکیب مسیر اصلی ریپو با ساب‌پات درخواستی کاربر
        self.target_dir = os.path.join(repo_path, sub_path) if sub_path else repo_path

    def run_pipeline(self) -> int:
        """
        متد ارکستراتور اصلی که چرخه کامل ETL را اجرا می‌کند.
        خروجی: تعداد سوالاتی که با موفقیت ذخیره شده‌اند.
        """
        logger.info(f"Starting ETL pipeline for target directory: {self.target_dir}")

        try:
            # ۱. فاز Extract
            raw_data = self.extract()
            if not raw_data:
                logger.warning("No raw data extracted from the source.")
                return 0

            # ۲. فاز Transform
            transformed_questions = self.transform(raw_data)
            if not transformed_questions:
                logger.warning(
                    "No questions remained after transformation and filtering."
                )
                return 0

            # ۳. فاز Load
            saved_count = self.load(transformed_questions)
            return saved_count

        except Exception as e:
            logger.critical(
                f"Pipeline crashed catastrophically: {str(e)}", exc_info=True
            )
            return 0

    def extract(self) -> List[Any]:
        """
        باید در کلاس فرزند اورراید شود.
        وظیفه: اسکن دایرکتوری و خواندن فایل‌های خام (متن مارک‌داون یا جیسون).
        """
        raise NotImplementedError(
            "Each adapter must implement its own 'extract' method."
        )

    def transform(self, raw_data: List[Any]) -> List[Dict[str, Any]]:
        """
        باید در کلاس فرزند اورراید شود.
        وظیفه: پارس کردن متون خام و تبدیل آن‌ها به دیکشنری‌های استاندارد شده.
        """
        raise NotImplementedError(
            "Each adapter must implement its own 'transform' method."
        )

    def clean_text(self, text: str) -> str:
        """
        متد کمکی برای پاک‌سازی زواید متنی، فضاهای خالی اضافه و کاراکترهای مخرب.
        """
        if not text:
            return ""
        # حذف فاصله‌های اضافه در ابتدا و انتها و یکپارچه‌سازی اینترها
        cleaned = "\n".join([line.strip() for line in text.strip().splitlines()])
        return cleaned

    def validate_and_truncate(
        self, question_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        لایه دفاعی اعتبارسنجی داده‌ها قبل از ورود به دیتابیس.
        تضمین می‌کند که فیلدهای حیاتی پر هستند و طول فیلد تایتل از حد مجاز دیتابیس بیشتر نیست.
        """
        title = question_data.get("title", "").strip()
        body = question_data.get("body", "").strip()
        reference_answer = question_data.get("reference_answer", "").strip()

        if not title or not body:
            logger.warning(
                "Validation failed: Question skipped due to empty title or body."
            )
            return None

        # خلاصه کردن عنوان در صورت فراتر رفتن از حد مجاز VARCHAR(255) دیتابیس
        if len(title) > 255:
            question_data["title"] = title[:250] + "..."

        question_data["body"] = self.clean_text(body)
        question_data["reference_answer"] = self.clean_text(reference_answer)

        return question_data

    def get_or_create_category(self, category_name: str) -> QuestionCategory:
        """
        متد کمکی برای ساخت داینامیک و امن دسته‌بندی‌ها بر اساس فولدربندی گیت‌هاب.
        """
        clean_name = category_name.strip().title()
        slug = slugify(clean_name) or clean_name.lower().replace(" ", "-")

        category, created = QuestionCategory.objects.get_or_create(
            slug=slug, defaults={"title": clean_name}
        )
        return category

    def load(self, questions_data: List[Dict[str, Any]]) -> int:
        """
        فاز نهایی: بارگذاری داده‌ها به صورت تراکنش اتمیک و امن.
        روابط چند‌به‌چند (Categories) و گزینه‌ها (Options) را مدیریت می‌کند.
        """
        success_count = 0

        # اجرای کل فرآیند در یک تراکنش دیتابیسی برای جلوگیری از دیتای ناقص
        with transaction.atomic():
            for q_data in questions_data:
                try:
                    with transaction.atomic():  # ← هر سوال transaction مجزا
                        validated_data = self.validate_and_truncate(q_data)
                        if not validated_data:
                            continue

                        categories_list = validated_data.pop("categories_metadata", [])
                        options_list = validated_data.pop("options_metadata", [])

                        question, created = Question.objects.update_or_create(
                            title=validated_data["title"],
                            source_url=validated_data.get("source_url"),
                            defaults={
                                "body": validated_data["body"],
                                "question_type": validated_data.get(
                                    "question_type", Question.QuestionType.TECHNICAL
                                ),
                                "seniority_level": validated_data.get(
                                    "seniority_level", Question.SeniorityLevel.MID_LEVEL
                                ),
                                "reference_answer": validated_data["reference_answer"],
                                "ai_evaluation_criteria": validated_data.get(
                                    "ai_evaluation_criteria", {}
                                ),
                                "estimated_time": validated_data.get(
                                    "estimated_time", 120
                                ),
                                "code_template": validated_data.get("code_template"),
                                "source": Question.SourceType.GITHUB_IMPORT,
                                "is_active": True,
                            },
                        )

                        for cat_name in categories_list:
                            category_obj = self.get_or_create_category(cat_name)
                            question.categories.add(category_obj)

                        if options_list:
                            question.options.all().delete()
                            QuestionOption.objects.bulk_create(
                                [
                                    QuestionOption(
                                        question=question,
                                        text=opt["text"],
                                        is_correct=opt.get("is_correct", False),
                                    )
                                    for opt in options_list
                                ]
                            )

                        success_count += 1

                        if self.limit and success_count >= self.limit:
                            logger.info(f"Reached limit of {self.limit}. Stopping.")
                            break

                except Exception as item_error:
                    logger.error(
                        f"Failed to load question: {str(item_error)}", exc_info=True
                    )
                    continue

        logger.info(f"Successfully loaded {success_count} questions into the database.")
        return success_count
