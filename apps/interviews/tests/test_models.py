import pytest

from django.test import TestCase
from django.utils import timezone

from apps.interviews.models import (
    InterviewMessage,
    InterviewSession,
    SessionQuestion,
    UserAnswer,
)
from apps.questions.models import Question
from apps.users.tests.factories import (
    InterviewSessionFactory,
    QuestionFactory,
    SessionQuestionFactory,
    UserAnswerFactory,
    UserFactory,
)


class InterviewSessionModelTest(TestCase):
    def setUp(self):
        self.user = UserFactory.create(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        self.session = InterviewSessionFactory.create(
            user=self.user,
            target_position="Senior Django Developer",
            seniority_level="senior",
            job_description="Develop Django applications",
            focus_topics=["Django", "PostgreSQL"],
            total_questions=5,
            status=InterviewSession.Status.SETUP,
        )

    def test_interview_session_creation(self):
        self.session.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(self.session.user, self.user)
        self.assertEqual(self.session.target_position, "Senior Django Developer")
        self.assertEqual(self.session.seniority_level, "senior")
        self.assertEqual(self.session.job_description, "Develop Django applications")
        self.assertEqual(self.session.focus_topics, ["Django", "PostgreSQL"])
        self.assertEqual(self.session.total_questions, 5)
        self.assertEqual(self.session.status, InterviewSession.Status.SETUP)
        self.assertIsNotNone(self.session.uuid)
        self.assertIsNotNone(self.session.created_at)
        self.assertIsNotNone(self.session.updated_at)

    def test_interview_session_str(self):
        expected_str = f"{self.user} | {self.session.target_position} | {self.session.get_status_display()}"
        self.assertEqual(str(self.session), expected_str)

    def test_interview_session_status_choices(self):
        self.assertIn(
            self.session.status,
            [choice[0] for choice in InterviewSession.Status.choices],
        )

    def test_interview_session_transition_to(self):
        self.session.transition_to(InterviewSession.Status.INTRO)
        self.assertEqual(self.session.status, InterviewSession.Status.INTRO)
        self.assertIsNotNone(self.session.started_at)

        self.session.transition_to(InterviewSession.Status.QUESTIONING)
        self.assertEqual(self.session.status, InterviewSession.Status.QUESTIONING)

        self.session.transition_to(InterviewSession.Status.DRILLING)
        self.assertEqual(self.session.status, InterviewSession.Status.DRILLING)

        self.session.transition_to(InterviewSession.Status.WRAP_UP)
        self.assertEqual(self.session.status, InterviewSession.Status.WRAP_UP)

        self.session.transition_to(InterviewSession.Status.COMPLETED)
        self.assertEqual(self.session.status, InterviewSession.Status.COMPLETED)
        self.assertIsNotNone(self.session.completed_at)

    def test_interview_session_invalid_transition(self):
        with self.assertRaises(ValueError):
            self.session.transition_to(InterviewSession.Status.DRILLING)

    def test_interview_session_properties(self):
        # Test duration_minutes when not started
        self.assertIsNone(self.session.duration_minutes)

        # Set started_at and completed_at
        self.session.started_at = timezone.now()
        self.session.completed_at = self.session.started_at + timezone.timedelta(
            minutes=30
        )
        self.session.save()
        self.session.refresh_from_db()  # برای همگام سازی حافظه و دیتابیس
        self.assertEqual(self.session.duration_minutes, 30)

        # Test is_active
        self.session.status = InterviewSession.Status.SETUP
        self.session.save()
        self.session.refresh_from_db()
        self.assertFalse(self.session.is_active)

        self.session.status = InterviewSession.Status.INTRO
        self.session.save()
        self.session.refresh_from_db()
        self.assertTrue(self.session.is_active)

        self.session.status = InterviewSession.Status.QUESTIONING
        self.session.save()
        self.session.refresh_from_db()
        self.assertTrue(self.session.is_active)

        self.session.status = InterviewSession.Status.DRILLING
        self.session.save()
        self.session.refresh_from_db()
        self.assertTrue(self.session.is_active)

        self.session.status = InterviewSession.Status.WRAP_UP
        self.session.save()
        self.session.refresh_from_db()
        self.assertTrue(self.session.is_active)

        self.session.status = InterviewSession.Status.COMPLETED
        self.session.save()
        self.session.refresh_from_db()
        self.assertFalse(self.session.is_active)

        # Test progress_percentage
        self.session.current_question_index = 0
        self.session.total_questions = 10
        self.session.save()
        self.session.refresh_from_db()
        self.assertEqual(self.session.progress_percentage, 0.0)

        self.session.current_question_index = 5
        self.session.save()
        self.session.refresh_from_db()
        self.assertEqual(self.session.progress_percentage, 50.0)

        self.session.current_question_index = 10
        self.session.save()
        self.session.refresh_from_db()
        self.assertEqual(self.session.progress_percentage, 100.0)

        self.session.total_questions = 0
        self.session.save()
        self.session.refresh_from_db()
        self.assertEqual(self.session.progress_percentage, 0.0)


class SessionQuestionModelTest(TestCase):
    def setUp(self):
        self.user = UserFactory.create(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        self.session = InterviewSessionFactory.create(
            user=self.user,
            target_position="Senior Django Developer",
            seniority_level="senior",
            total_questions=2,
        )
        # ✅ فیلد difficulty حذف شد
        self.question = QuestionFactory.create(
            title="What is Django?",
            body="Explain Django.",
            question_type="technical",
            estimated_time=120,
            is_active=True,
        )
        self.session_question = SessionQuestionFactory.create(
            session=self.session,
            question=self.question,
            order=1,
            status=SessionQuestion.QuestionStatus.PENDING,
        )

    def test_session_question_creation(self):
        self.assertEqual(self.session_question.session, self.session)
        self.assertEqual(self.session_question.question, self.question)
        self.assertEqual(self.session_question.order, 1)
        self.assertEqual(
            self.session_question.status, SessionQuestion.QuestionStatus.PENDING
        )
        self.assertIsNotNone(self.session_question.id)

    def test_session_question_str(self):
        expected_str = f"Session {self.session.id} | Q{self.session_question.order}: {self.session_question.question}"
        self.assertEqual(str(self.session_question), expected_str)

    def test_session_question_unique_together(self):
        with self.assertRaises(Exception):
            SessionQuestionFactory.create(
                session=self.session,
                # ✅ فیلد difficulty حذف شد
                question=QuestionFactory.create(
                    title="Another question",
                    body="Another body",
                    question_type="technical",
                    estimated_time=120,
                    is_active=True,
                ),
                order=1,
            )


class InterviewMessageModelTest(TestCase):
    def setUp(self):
        self.user = UserFactory.create(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        self.session = InterviewSessionFactory.create(
            user=self.user,
            target_position="Senior Django Developer",
            seniority_level="senior",
            total_questions=2,
        )
        # ✅ فیلد difficulty حذف شد
        self.question = QuestionFactory.create(
            title="What is Django?",
            body="Explain Django.",
            question_type="technical",
            estimated_time=120,
            is_active=True,
        )
        self.session_question = SessionQuestionFactory.create(
            session=self.session,
            question=self.question,
            order=1,
            status=SessionQuestion.QuestionStatus.PENDING,
        )
        self.message = InterviewMessage.objects.create(
            session=self.session,
            role=InterviewMessage.Role.ASSISTANT,
            message_type=InterviewMessage.MessageType.QUESTION,
            content="What is Django?",
            turn_number=1,
            related_question=self.session_question,
            metadata={"estimated_time": 120},
        )

    def test_interview_message_creation(self):
        self.assertEqual(self.message.session, self.session)
        self.assertEqual(self.message.role, InterviewMessage.Role.ASSISTANT)
        self.assertEqual(
            self.message.message_type, InterviewMessage.MessageType.QUESTION
        )
        self.assertEqual(self.message.content, "What is Django?")
        self.assertEqual(self.message.turn_number, 1)
        self.assertEqual(self.message.related_question, self.session_question)
        self.assertEqual(self.message.metadata, {"estimated_time": 120})
        self.assertIsNotNone(self.message.created_at)

    def test_interview_message_str(self):
        expected_str = f"[{self.message.get_role_display()}] Turn {self.message.turn_number} | {self.message.content[:50]}"
        self.assertEqual(str(self.message), expected_str)


class UserAnswerModelTest(TestCase):
    def setUp(self):
        self.user = UserFactory.create(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        self.session = InterviewSessionFactory.create(
            user=self.user,
            target_position="Senior Django Developer",
            seniority_level="senior",
            total_questions=2,
        )
        # ✅ فیلد difficulty حذف شد
        self.question = QuestionFactory.create(
            title="What is Django?",
            body="Explain Django.",
            question_type="technical",
            estimated_time=120,
            is_active=True,
            reference_answer="Django is a high-level Python web framework.",
            ai_evaluation_criteria="Clarity, depth, correctness",
        )
        self.user_answer = UserAnswerFactory.create(
            session=self.session,
            user=self.user,
            question=self.question,
            answer_text="Django is a high-level Python web framework that encourages rapid development.",
            answer_duration=30,
            status=UserAnswer.Status.PENDING,
        )

    def test_user_answer_creation(self):
        self.assertEqual(self.user_answer.session, self.session)
        self.assertEqual(self.user_answer.user, self.user)
        self.assertEqual(self.user_answer.question, self.question)
        self.assertEqual(
            self.user_answer.answer_text,
            "Django is a high-level Python web framework that encourages rapid development.",
        )
        self.assertEqual(self.user_answer.answer_duration, 30)
        self.assertEqual(self.user_answer.status, UserAnswer.Status.PENDING)
        self.assertIsNotNone(self.user_answer.created_at)
        self.assertIsNotNone(self.user_answer.updated_at)

    def test_user_answer_str(self):
        expected_str = f"{self.user} | Q#{self.user_answer.question_id} | {self.user_answer.get_status_display()}"
        self.assertEqual(str(self.user_answer), expected_str)

    def test_user_answer_is_evaluated(self):
        self.assertFalse(self.user_answer.is_evaluated)
        self.user_answer.status = UserAnswer.Status.GRADED
        self.user_answer.save()
        self.assertTrue(self.user_answer.is_evaluated)

    def test_user_answer_passed(self):
        self.user_answer.score = 50
        self.user_answer.save()
        self.assertFalse(self.user_answer.passed)

        self.user_answer.score = 70
        self.user_answer.save()
        self.assertTrue(self.user_answer.passed)

        self.user_answer.score = None
        self.user_answer.save()
        self.assertFalse(self.user_answer.passed)

    def test_user_answer_unique_together(self):
        with self.assertRaises(Exception):
            UserAnswerFactory.create(
                session=self.session,
                user=self.user,
                question=self.question,
                answer_text="Another answer",
                status=UserAnswer.Status.PENDING,
            )
