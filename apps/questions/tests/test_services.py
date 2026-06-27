from unittest.mock import patch
from django.test import TransactionTestCase
from django.core.exceptions import ValidationError
from apps.questions.models import Question
from apps.interviews.models import UserAnswer
from apps.questions.services import submit_and_grade_answer, _build_evaluation_prompt
from apps.users.tests.factories import (
    UserFactory, QuestionCategoryFactory, QuestionFactory, QuestionOptionFactory,
    InterviewSessionFactory, SessionQuestionFactory, InterviewMessageFactory, UserAnswerFactory,
    NotificationFactory
)

class TestQuestionsServices(TransactionTestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.session = InterviewSessionFactory.create(user=self.user)
        self.question = QuestionFactory.create(
            title="What is Docker?",
            body="Explain containerization.",
            reference_answer="Docker is a containerization platform.",
            is_active=True,
        )
        
    @patch("apps.questions.services.LLMClient.evaluate_default")
    def test_submit_and_grade_answer_success(self, mock_evaluate_default):
        # LLMClient.evaluate_default یک classmethod هست که مستقیماً توسط سرویس
        # با LLMClient.evaluate_default(ai_prompt) صدا زده میشه و یک dict برمیگردونه.
        # پس return_value خود mock باید dict باشه، نه زنجیره mock.return_value.*.
        mock_evaluate_default.return_value = {
            "score": 85,
            "strengths": ["Good explanation"],
            "weaknesses": ["Missed isolated networking aspect"],
            "model_improvement_suggestion": "Try mentioning namespaces."
        }

        user_answer_text = "Docker runs apps in isolated environments."
        record = submit_and_grade_answer(
            user_id=self.user.id,
            session_id=self.session.id,
            question_id=self.question.id,
            user_answer_text=user_answer_text
        )

        self.assertEqual(record.status, UserAnswer.Status.GRADED)
        self.assertEqual(record.score, 85)
        self.assertEqual(record.strengths, ["Good explanation"])

        # Ensure it actually saved in the DB
        db_record = UserAnswer.objects.get(id=record.id)
        self.assertEqual(db_record.status, UserAnswer.Status.GRADED)

    def test_submit_empty_answer(self):
        with self.assertRaises(ValidationError) as context:
            submit_and_grade_answer(
                user_id=self.user.id,
            session_id=self.session.id,
                question_id=self.question.id,
                user_answer_text="   "
            )
        self.assertIn("خالی باشد", str(context.exception))

    def test_submit_to_invalid_question(self):
        with self.assertRaises(ValidationError) as context:
            submit_and_grade_answer(
                user_id=self.user.id,
            session_id=self.session.id,
                question_id=9999,
                user_answer_text="Answer"
            )
        self.assertIn("یافت نشد", str(context.exception))

    @patch("apps.questions.services.LLMClient.evaluate_default")
    def test_submit_and_grade_ai_failure(self, mock_evaluate_default):
        # شبیه‌سازی خطای تایم‌اوت هوش مصنوعی
        mock_evaluate_default.side_effect = Exception("API Timeout")

        # چک می‌کنیم که اکسپشن به درستی بالا بیاد
        with self.assertRaises(Exception) as context:
            submit_and_grade_answer(
                user_id=self.user.id,
                session_id=self.session.id,
                question_id=self.question.id,
                user_answer_text="Answer"
            )

        # چک می‌کنیم که پیام خطای سفارشی‌شده درست باشد
        self.assertIn("برقرار نشد", str(context.exception))

        # حالا بررسی می‌کنیم که رکورد با وضعیت FAILED و لاگ خطا حتماً توی دیتابیس موندگار شده باشه
        record = UserAnswer.objects.filter(
            user_id=self.user.id,
            session_id=self.session.id, 
            question_id=self.question.id
        ).first()
        
        self.assertIsNotNone(record, "رکورد باید در دیتابیس ذخیره شده باشد")
        self.assertEqual(record.status, UserAnswer.Status.FAILED)
        self.assertIn("API Timeout", record.error_log)

    def test_build_evaluation_prompt(self):
        prompt = _build_evaluation_prompt(question=self.question, user_answer="My answer")
        self.assertIn("What is Docker?", prompt)
        self.assertIn("Docker is a containerization platform.", prompt)
        self.assertIn("My answer", prompt)
