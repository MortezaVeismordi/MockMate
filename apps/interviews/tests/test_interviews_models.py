from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.interviews.models import (InterviewMessage, InterviewSession,
                                    SessionQuestion, UserAnswer)
from apps.questions.models import Question, QuestionCategory
from apps.users.tests.factories import (InterviewMessageFactory,
                                        InterviewSessionFactory,
                                        NotificationFactory,
                                        QuestionCategoryFactory,
                                        QuestionFactory, QuestionOptionFactory,
                                        SessionQuestionFactory,
                                        UserAnswerFactory, UserFactory)


@pytest.mark.django_db
class TestInterviewSessionModel:
    """Test cases for InterviewSession model"""

    def test_create_interview_session(self):
        """Test creating an interview session"""
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        session = InterviewSessionFactory.create(
            user=user,
            target_position="Senior Django Developer",
            seniority_level=InterviewSession.SeniorityLevel.SENIOR,
        )
        assert session.user == user
        assert session.target_position == "Senior Django Developer"
        assert session.seniority_level == InterviewSession.SeniorityLevel.SENIOR
        assert session.status == InterviewSession.Status.SETUP
        assert session.created_at is not None

    def test_interview_session_str_representation(self):
        """Test string representation of interview session"""
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        session = InterviewSessionFactory.create(
            user=user,
            target_position="Senior Django Developer",
        )
        expected_str = (
            f"{user} | Senior Django Developer | {session.get_status_display()}"
        )
        assert str(session) == expected_str

    def test_interview_session_duration(self):
        """Test interview session duration calculation"""
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        start_time = timezone.now() - timedelta(minutes=30)
        end_time = timezone.now() - timedelta(minutes=5)
        session = InterviewSessionFactory.create(
            user=user,
            target_position="Senior Django Developer",
            started_at=start_time,
            completed_at=end_time,
            status=InterviewSession.Status.COMPLETED,
        )
        assert session.duration_minutes == 25

    def test_interview_session_duration_not_ended(self):
        """Test duration when session hasn't ended"""
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        session = InterviewSessionFactory.create(
            user=user,
            target_position="Senior Django Developer",
            status=InterviewSession.Status.QUESTIONING,
        )
        assert session.duration_minutes is None

    def test_transition_to(self):
        """Test status transition"""
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        session = InterviewSessionFactory.create(
            user=user,
            target_position="Senior Django Developer",
        )
        assert session.status == InterviewSession.Status.SETUP
        assert session.started_at is None

        session.transition_to(InterviewSession.Status.INTRO)
        session.refresh_from_db()
        assert session.status == InterviewSession.Status.INTRO
        assert session.started_at is not None

        # ✅ INTRO → QUESTIONING → WRAP_UP → COMPLETED (مسیر واقعی)
        session.transition_to(InterviewSession.Status.QUESTIONING)
        session.refresh_from_db()
        assert session.status == InterviewSession.Status.QUESTIONING

        session.transition_to(InterviewSession.Status.WRAP_UP)
        session.refresh_from_db()
        assert session.status == InterviewSession.Status.WRAP_UP

        session.transition_to(InterviewSession.Status.COMPLETED)
        session.refresh_from_db()
        assert session.status == InterviewSession.Status.COMPLETED
        assert session.completed_at is not None


@pytest.mark.django_db
class TestSessionQuestionModel:
    """Test cases for SessionQuestion model"""

    def test_create_session_question(self):
        """Test creating a session question"""
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        category = QuestionCategory.objects.create(title="Django", slug="django")
        question = QuestionFactory.create(
            title="What is Django?",
            body="Explain Django framework.",
            question_type=Question.QuestionType.TECHNICAL,
            seniority_level=Question.SeniorityLevel.MID_LEVEL,
            reference_answer="Django is a high-level Python web framework.",
        )
        question.categories.add(category)

        session = InterviewSessionFactory.create(
            user=user,
            target_position="Senior Django Developer",
        )
        session_question = SessionQuestionFactory.create(
            session=session,
            question=question,
            order=1,
            status=SessionQuestion.QuestionStatus.PENDING,
        )
        assert session_question.session == session
        assert session_question.question == question
        assert session_question.order == 1
        assert session_question.status == SessionQuestion.QuestionStatus.PENDING


@pytest.mark.django_db
class TestUserAnswerModel:
    """Test cases for UserAnswer model"""

    def test_create_user_answer(self):
        """Test creating a user answer"""
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        category = QuestionCategory.objects.create(title="Django", slug="django")
        question = QuestionFactory.create(
            title="What is Django?",
            body="Explain Django framework.",
            question_type=Question.QuestionType.TECHNICAL,
            seniority_level=Question.SeniorityLevel.MID_LEVEL,
            reference_answer="Django is a high-level Python web framework.",
        )
        question.categories.add(category)

        session = InterviewSessionFactory.create(
            user=user,
            target_position="Senior Django Developer",
        )
        answer = UserAnswerFactory.create(
            session=session,
            user=user,
            question=question,
            answer_text="Django is a high-level Python web framework.",
        )
        assert answer.session == session
        assert answer.user == user
        assert answer.question == question
        assert answer.answer_text == "Django is a high-level Python web framework."
        assert answer.score is None
        assert answer.feedback == ""
        assert answer.status == UserAnswer.Status.PENDING

    def test_user_answer_str_representation(self):
        """Test string representation of user answer"""
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        category = QuestionCategory.objects.create(title="Django", slug="django")
        question = QuestionFactory.create(
            title="What is Django?",
            body="Explain Django framework.",
            question_type=Question.QuestionType.TECHNICAL,
            seniority_level=Question.SeniorityLevel.MID_LEVEL,
            reference_answer="Django is a high-level Python web framework.",
        )
        question.categories.add(category)

        session = InterviewSessionFactory.create(
            user=user,
            target_position="Senior Django Developer",
        )
        answer = UserAnswerFactory.create(
            session=session,
            user=user,
            question=question,
            answer_text="Django is a high-level Python web framework.",
        )
        assert (
            str(answer) == f"{user} | Q#{question.id} | {answer.get_status_display()}"
        )

    def test_user_answer_with_evaluation(self):
        """Test user answer with evaluation scores"""
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        category = QuestionCategory.objects.create(title="Django", slug="django")
        question = QuestionFactory.create(
            title="What is Django?",
            body="Explain Django framework.",
            question_type=Question.QuestionType.TECHNICAL,
            seniority_level=Question.SeniorityLevel.MID_LEVEL,
            reference_answer="Django is a high-level Python web framework.",
        )
        question.categories.add(category)

        session = InterviewSessionFactory.create(
            user=user,
            target_position="Senior Django Developer",
        )
        answer = UserAnswerFactory.create(
            session=session,
            user=user,
            question=question,
            answer_text="Django is a high-level Python web framework.",
            score=85,
            feedback="Good explanation but could mention MTV pattern.",
            status=UserAnswer.Status.GRADED,
        )
        assert answer.score == 85
        assert answer.feedback == "Good explanation but could mention MTV pattern."
        assert answer.status == UserAnswer.Status.GRADED
        assert answer.is_evaluated is True
        assert answer.passed is True


@pytest.mark.django_db
class TestInterviewMessageModel:
    """Test cases for InterviewMessage model"""

    def test_create_interview_message(self):
        """Test creating an interview message"""
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        session = InterviewSessionFactory.create(
            user=user,
            target_position="Senior Django Developer",
        )
        message = InterviewMessage.objects.create(
            session=session,
            role=InterviewMessage.Role.ASSISTANT,
            message_type=InterviewMessage.MessageType.QUESTION,
            content="Welcome to the interview!",
            turn_number=1,
        )
        assert message.session == session
        assert message.role == InterviewMessage.Role.ASSISTANT
        assert message.message_type == InterviewMessage.MessageType.QUESTION
        assert message.content == "Welcome to the interview!"
        assert message.turn_number == 1
