import pytest

from django.contrib.auth import get_user_model
from rest_framework import status

from apps.questions.models import Question, QuestionCategory
from apps.users.tests.base import BaseAPITestCase as APITestCase
from apps.users.tests.factories import (
    InterviewMessageFactory,
    InterviewSessionFactory,
    NotificationFactory,
    QuestionCategoryFactory,
    QuestionFactory,
    QuestionOptionFactory,
    SessionQuestionFactory,
    UserAnswerFactory,
    UserFactory,
)

User = get_user_model()


@pytest.mark.django_db
class TestQuestionModel:

    def test_create_question(self):
        category = QuestionCategory.objects.create(title="Django", slug="django")
        question = QuestionFactory.create(
            title="What is Django?",
            body="Explain what Django is and its main features.",
            question_type=Question.QuestionType.TECHNICAL,
            seniority_level=Question.SeniorityLevel.MID_LEVEL,
            reference_answer="Django is a high-level Python web framework.",
            estimated_time=300,
        )
        question.categories.add(category)
        assert question.title == "What is Django?"
        assert question.question_type == Question.QuestionType.TECHNICAL
        assert question.seniority_level == Question.SeniorityLevel.MID_LEVEL
        assert question.is_active is True

    def test_question_str_representation(self):
        category = QuestionCategory.objects.create(title="Django", slug="django")
        question = QuestionFactory.create(
            title="What is Django?",
            body="Explain what Django is.",
            question_type=Question.QuestionType.TECHNICAL,
            seniority_level=Question.SeniorityLevel.MID_LEVEL,
            reference_answer="Django is a high-level Python web framework.",
        )
        question.categories.add(category)
        assert (
            str(question)
            == f"[{question.get_seniority_level_display()}] {question.title}"
        )

    def test_question_type_choices(self):
        category = QuestionCategory.objects.create(title="Django", slug="django")
        for question_type in [choice[0] for choice in Question.QuestionType.choices]:
            question = QuestionFactory.create(
                title=f"Question {question_type}",
                body="Description",
                question_type=question_type,
                seniority_level=Question.SeniorityLevel.MID_LEVEL,
                reference_answer="Test answer",
            )
            question.categories.add(category)
            assert question.question_type == question_type

    def test_question_seniority_level_choices(self):
        category = QuestionCategory.objects.create(title="Django", slug="django")
        for level in [choice[0] for choice in Question.SeniorityLevel.choices]:
            question = QuestionFactory.create(
                title=f"Question {level}",
                body="Description",
                question_type=Question.QuestionType.TECHNICAL,
                seniority_level=level,
                reference_answer="Test answer",
            )
            question.categories.add(category)
            assert question.seniority_level == level


@pytest.mark.django_db
class TestQuestionCategoryModel:

    def test_create_category(self):
        category = QuestionCategory.objects.create(title="Python", slug="python")
        assert category.title == "Python"
        assert str(category) == "Python"

    def test_category_unique_slug(self):
        QuestionCategory.objects.create(title="Python", slug="python")
        with pytest.raises(Exception):
            QuestionCategory.objects.create(title="Python2", slug="python")

    def test_category_hierarchy(self):
        parent = QuestionCategory.objects.create(
            title="Programming", slug="programming"
        )
        child = QuestionCategory.objects.create(
            title="Python",
            slug="python",
            parent=parent,
        )
        assert child.parent == parent
        assert parent.children.count() == 1
        assert parent.children.first() == child


@pytest.mark.django_db
class TestQuestionViews(APITestCase):

    def setUp(self):
        self.user = UserFactory.create(
            phone_number="09123456789",
            password="testpass123",
            email="test@example.com",
            is_active=True,
        )
        self.category = QuestionCategory.objects.create(title="Django", slug="django")
        self.question = QuestionFactory.create(
            title="What is Django?",
            body="Explain what Django is and its main features.",
            question_type=Question.QuestionType.TECHNICAL,
            seniority_level=Question.SeniorityLevel.MID_LEVEL,
            reference_answer="Django is a high-level Python web framework.",
            estimated_time=300,
        )
        self.question.categories.add(self.category)
        self.client.force_authenticate(user=self.user)
        self.list_url = "/api/v1/questions/"

    def test_list_questions(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_questions_unauthenticated(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_question(self):
        response = self.client.get(f"{self.list_url}{self.question.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "What is Django?")

    def test_filter_questions_by_category(self):
        python_category = QuestionCategory.objects.create(title="Python", slug="python")
        python_question = QuestionFactory.create(
            title="What is Python?",
            body="Explain Python.",
            question_type=Question.QuestionType.TECHNICAL,
            seniority_level=Question.SeniorityLevel.MID_LEVEL,
            reference_answer="Python is a programming language.",
        )
        python_question.categories.add(python_category)

        response = self.client.get(f"{self.list_url}?category={self.category.slug}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
