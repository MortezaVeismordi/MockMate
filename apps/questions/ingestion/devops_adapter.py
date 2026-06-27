import logging
import os
import re
from typing import Any, Dict, List

from apps.questions.models import Question

from .base_adapter import BaseQuestionAdapter

logger = logging.getLogger(__name__)


class DevOpsExercisesAdapter(BaseQuestionAdapter):
    """
    آداپتور انترپرایز و هوشمند اختصاصی برای ریپوزیوری devops-exercises.
    این کلاس فایل‌های README.md را کالبدشکافی کرده و سوالات، پاسخ‌ها و کدهای کانتینر/یامل را استخراج می‌کند.
    """

    def extract(self) -> List[Dict[str, Any]]:
        raw_files_data = []

        if not os.path.exists(self.target_dir):
            logger.error(f"Target directory does not exist: {self.target_dir}")
            return raw_files_data

        # لیست فایل‌های مستندات که باید کاملاً نادیده گرفته شوند
        EXCLUDED_FILES = {
            "readme.md",
            "contributing.md",
            "license.md",
            "code_of_conduct.md",
            "contributing-pt-br.md",
            "readme-fa.md",
            "faq.md",
            "faq-he.md",
        }

        for root, dirs, files in os.walk(self.target_dir):
            for file in files:
                if file.endswith(".md"):
                    # ۱. فیلتر کردن فایل‌های مستندات عمومی و غیر فنی
                    if file.lower() in EXCLUDED_FILES:
                        continue

                    file_path = os.path.join(root, file)
                    category_name = os.path.basename(root)

                    if category_name.startswith(".") or category_name == self.repo_path:
                        continue

                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            raw_files_data.append(
                                {
                                    "content": content,
                                    "category": category_name,
                                    "file_path": file_path,
                                }
                            )
                    except Exception as e:
                        logger.error(f"Error reading file {file_path}: {str(e)}")

        return raw_files_data

    def transform(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        فاز Transform: پارس کردن متن مارک‌داون با Regex و استخراج ساختار سوال و جواب.
        """
        transformed_questions = []

        # الگوی ریجکس برای پیدا کردن سوالاتی که با هدر یا علامت Q شروع می‌شوند
        # این الگو سوالاتی که پاسخشان داخل تگ <details> هست را هم شکار می‌کند
        question_block_pattern = re.compile(
            r"(?:^|\n)(?P<header>#{2,4})\s+(?:Q\d*:\s*)?(?P<title>.+?)(?=\n)(?P<body>.+?)(?=(?:\n#{2,4}\s+Q\d*:|\n#{2,4}\s+[^Q]|\Z))",
            re.DOTALL | re.IGNORECASE,
        )

        for file_item in raw_data:
            content = file_item["content"]
            category = file_item["category"]

            # پیدا کردن تمام بلوک‌های سوال در فایل
            matches = question_block_pattern.finditer(content)

            for match in matches:
                title = match.group("title").strip()
                raw_body = match.group("body").strip()

                # فیلتر اموجی‌ها یا کاراکترهای اضافه از عنوان
                title = re.sub(r"[\d\.\-\:]", "", title).strip()

                # تفکیک پاسخ مرجع (Reference Answer) از بدنه سوال
                # در این ریپو پاسخ‌ها معمولاً بین تگ‌های <details> و <summary> هستند
                reference_answer = ""
                body_clean = raw_body

                if "<details>" in raw_body:
                    details_match = re.search(
                        r"<details>.*?</summary>(?P<ans>.*?)</details>",
                        raw_body,
                        re.DOTALL | re.IGNORECASE,
                    )
                    if details_match:
                        reference_answer = details_match.group("ans").strip()
                        # پاک کردن تگ دتیلز از بدنه سوال اصلی
                        body_clean = re.sub(
                            r"<details>.*?</details>",
                            "",
                            raw_body,
                            flags=re.DOTALL | re.IGNORECASE,
                        ).strip()
                else:
                    # اگر تگ details نبود، بخش دوم متن را به عنوان پاسخ در نظر می‌گیریم (بر اساس جداکننده رایج)
                    parts = raw_body.split("\n**Answer:**\n", 1)
                    if len(parts) == 2:
                        body_clean = parts[0].strip()
                        reference_answer = parts[1].strip()
                    else:
                        reference_answer = "پاسخ مرجع در گیت‌هاب ثبت نشده است. نیاز به بررسی هوش مصنوعی."

                # تشخیص هوشمند نوع سوال (اگر کلمات کلیدی تستی داشت)
                q_type = Question.QuestionType.DEVOPS
                options_metadata = []

                if any(
                    indicator in body_clean for indicator in ["a)", "b)", "1)", "- [ ]"]
                ):
                    q_type = Question.QuestionType.MULTIPLE_CHOICE
                    options_metadata = self._parse_options(body_clean, reference_answer)

                # تخمین زمان داینامیک بر اساس طول محتوا و کدهای موجود
                estimated_time = 90  # پیش‌فرض ۹۰ ثانیه برای سوالات کوتاه لینوکس
                if "```" in body_clean or "```" in reference_answer:
                    estimated_time = 240  # ۴ دقیقه برای سناریوهای شامل کد یا یامل
                if q_type == Question.QuestionType.MULTIPLE_CHOICE:
                    estimated_time = 60  # ۱ دقیقه برای تست‌های سریع

                # اعمال فیلتر سطح ارشدیت (سطح‌بندی بر اساس کلمات کلیدی یا فولدر)
                seniority = Question.SeniorityLevel.MID_LEVEL
                if any(
                    k in body_clean.lower() or k in title.lower()
                    for k in ["advanced", "architecture", "production", "optimize"]
                ):
                    seniority = Question.SeniorityLevel.SENIOR
                elif any(
                    k in body_clean.lower() for k in ["basic", "what is", "junior"]
                ):
                    seniority = Question.SeniorityLevel.JUNIOR

                # ساخت داکیومنت نهایی طبق ساختار مورد انتظار کلاس پایه
                question_document = {
                    "title": title,
                    "body": body_clean if body_clean else title,
                    "question_type": q_type,
                    "seniority_level": seniority,
                    "reference_answer": reference_answer,
                    "estimated_time": estimated_time,
                    "categories_metadata": [
                        category,
                        "DevOps",
                    ],  # تگ داینامیک پوشه + تگ کلان DevOps
                    "options_metadata": options_metadata,
                    "source_url": f"https://github.com/devops-exercises (File: {os.path.basename(file_item['file_path'])})",
                }

                # فیلترهای اختیاری کاربر زمان اجرای دستور (خروج زودهنگام در صورت عدم انطباق)
                if (
                    self.category_filter
                    and self.category_filter.lower() != category.lower()
                ):
                    continue
                if self.level_filter and self.level_filter.lower() != seniority.value:
                    continue

                transformed_questions.append(question_document)

        logger.info(
            f"DevOps Adapter transformed {len(transformed_questions)} potential questions."
        )
        return transformed_questions

    def _parse_options(self, body_text: str, answer_text: str) -> List[Dict[str, Any]]:
        """
        متد کمکی داخلی برای استخراج گزینه‌های تستی و تشخیص گزینه صحیح.
        """
        options = []
        # پیدا کردن خطوطی که با حروف الفبا یا عدد به عنوان گزینه شروع می‌شوند
        raw_options = re.findall(
            r"(?P<label>[a-d1-4])[\)\.]\s*(?P<text>.+)", body_text, re.IGNORECASE
        )

        for label, text in raw_options:
            clean_text = text.strip()
            # تشخیص هوشمند اینکه آیا این گزینه پاسخ صحیح است یا خیر
            # بررسی اینکه آیا علامت تایید یا متن پاسخ در بخش جواب آمده است
            is_correct = (
                label.lower() in answer_text.lower()
                or clean_text.lower() in answer_text.lower()
            )

            options.append({"text": clean_text, "is_correct": is_correct})
        return options
