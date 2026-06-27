import pytest
from django.test import TestCase

from apps.questions.models import (
    Question,
    QuestionAttachment,
    QuestionCategory,
    QuestionOption,
)
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


class TestQuestionModels(TestCase):
    def test_question_category_creation_and_str(self):
        parent_cat = QuestionCategory.objects.create(title="Backend", slug="backend")
        child_cat = QuestionCategory.objects.create(
            title="Python", slug="python", parent=parent_cat
        )
        self.assertEqual(str(parent_cat), "Backend")
        self.assertEqual(str(child_cat), "Backend -> Python")

    def test_question_creation_and_str(self):
        question = QuestionFactory.create(
            title="What is GIL?",
            body="Explain the Global Interpreter Lock.",
            seniority_level=Question.SeniorityLevel.SENIOR,
            question_type=Question.QuestionType.TECHNICAL,
            reference_answer="GIL allows only one thread.",
            source=Question.SourceType.MANUAL,
        )
        self.assertEqual(str(question), "[Senior] What is GIL?")
        self.assertTrue(question.is_active)
        self.assertDictEqual(question.ai_evaluation_criteria, {})

    def test_question_with_categories_and_options(self):
        cat = QuestionCategory.objects.create(title="DevOps", slug="devops")
        question = QuestionFactory.create(
            title="Docker CMD vs ENTRYPOINT",
            body="Difference?",
            reference_answer="CMD can be overridden, ENTRYPOINT cannot easily be.",
        )
        question.categories.add(cat)

        opt1 = QuestionOption.objects.create(
            question=question, text="Option 1", is_correct=True
        )
        opt2 = QuestionOption.objects.create(
            question=question, text="Option 2", is_correct=False
        )

        self.assertEqual(question.categories.count(), 1)
        self.assertEqual(question.options.count(), 2)
        self.assertTrue(opt1.is_correct)
        self.assertFalse(opt2.is_correct)

    def test_question_attachment(self):
        question = QuestionFactory.create(
            title="System Design",
            body="Design Whatsapp",
            reference_answer="Use WebSockets",
        )
        attachment = QuestionAttachment.objects.create(
            question=question,
            file="questions/attachments/architecture.png",
            attachment_type=QuestionAttachment.AttachmentType.IMAGE,
        )
        self.assertEqual(attachment.question, question)
        self.assertEqual(
            attachment.attachment_type, QuestionAttachment.AttachmentType.IMAGE
        )
