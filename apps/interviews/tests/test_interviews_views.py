from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from apps.interviews.models import (InterviewSession, SessionQuestion,
                                    UserAnswer)
from apps.questions.models import Question, QuestionCategory
from apps.users.tests.base import BaseAPITestCase as APITestCase
from apps.users.tests.factories import (InterviewMessageFactory,
                                        InterviewSessionFactory,
                                        NotificationFactory,
                                        QuestionCategoryFactory,
                                        QuestionFactory, QuestionOptionFactory,
                                        SessionQuestionFactory,
                                        UserAnswerFactory, UserFactory)


@pytest.mark.django_db
class TestInterviewSessionViews(APITestCase):

    def setUp(self):
        self.user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
            is_active=True,
        )
        self.category = QuestionCategoryFactory.create(title="Django", slug="django")
        for i in range(5):
            question = QuestionFactory.create(
                title=f"Question {i}",
                body=f"Description {i}",
                question_type=Question.QuestionType.TECHNICAL,
                seniority_level=Question.SeniorityLevel.SENIOR,
                reference_answer=f"Answer {i}",
            )
            question.categories.add(self.category)
        self.client.force_authenticate(user=self.user)
        self.session_list_url = "/api/v1/interviews/"

    def test_create_interview_session(self):
        data = {
            "target_position": "Senior Django Developer",
            "seniority_level": "senior",
            "total_questions": 5,
        }
        response = self.client.post(self.session_list_url, data, format="json")
        self.assertIn(
            response.status_code,
            [
                status.HTTP_201_CREATED,
                status.HTTP_200_OK,
            ],
        )

    def test_create_interview_session_unauthenticated(self):
        self.client.force_authenticate(user=None)
        data = {
            "target_position": "Senior Django Developer",
            "seniority_level": "senior",
        }
        response = self.client.post(self.session_list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_interview_sessions(self):
        InterviewSessionFactory.create(
            user=self.user,
            target_position="Senior Django Developer",
        )
        InterviewSessionFactory.create(
            user=self.user,
            target_position="DevOps Engineer",
        )
        response = self.client.get(self.session_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@pytest.mark.django_db
class TestUserAnswerModel:

    def test_create_user_answer(self):
        user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
        )
        category = QuestionCategoryFactory.create(title="Django", slug="django")
        question = QuestionFactory.create(
            title="What is Django?",
            body="Explain Django.",
            question_type=Question.QuestionType.TECHNICAL,
            seniority_level=Question.SeniorityLevel.SENIOR,
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
        assert answer.question == question
        assert answer.status == UserAnswer.Status.PENDING
