from unittest.mock import patch

import pytest
from django.test import TestCase

from apps.questions.ingestion.base_adapter import BaseQuestionAdapter
from apps.questions.ingestion.pipeline import QuestionIngestionPipeline
from apps.questions.models import Question, QuestionCategory, QuestionOption


# Dummy implementation for testing abstract methods
class DummyAdapter(BaseQuestionAdapter):
    def extract(self):
        return []

    def transform(self, raw_data):
        return raw_data


class TestBaseQuestionAdapter(TestCase):
    def setUp(self):
        self.adapter = DummyAdapter(repo_path="/fake/repo", limit=5)

    def test_clean_text(self):
        raw_text = " \n  Line 1   \n\n Line 2 \n  "
        self.assertEqual(self.adapter.clean_text(raw_text), "Line 1\n\nLine 2")
        self.assertEqual(self.adapter.clean_text(""), "")

    def test_validate_and_truncate_invalid(self):
        self.assertIsNone(
            self.adapter.validate_and_truncate({"title": "", "body": "Body"})
        )
        self.assertIsNone(
            self.adapter.validate_and_truncate({"title": "Title", "body": ""})
        )
        self.assertIsNone(self.adapter.validate_and_truncate(dict()))

    def test_validate_and_truncate_long_title(self):
        long_title = "X" * 300
        data = {"title": long_title, "body": "Body", "reference_answer": "Reference"}
        validated = self.adapter.validate_and_truncate(data)
        self.assertTrue(validated["title"].endswith("..."))
        self.assertEqual(len(validated["title"]), 253)

    def test_get_or_create_category(self):
        cat1 = self.adapter.get_or_create_category("  Cloud Native  ")
        self.assertEqual(cat1.title, "Cloud Native")
        self.assertEqual(cat1.slug, "cloud-native")

        # Second call should fetch the exact same object
        cat2 = self.adapter.get_or_create_category("CLOUD NATIVE")
        self.assertEqual(cat1.id, cat2.id)

    def test_load_saving_logic(self):
        questions_chunk = [
            {
                "title": "Ingested One",
                "body": "Body 1",
                "reference_answer": "Ref 1",
                "categories_metadata": ["Cat A", "Cat B"],
                "options_metadata": [
                    {"text": "A", "is_correct": True},
                    {"text": "B", "is_correct": False},
                ],
                "question_type": Question.QuestionType.TECHNICAL,
                "seniority_level": Question.SeniorityLevel.JUNIOR,
            }
        ]

        saved = self.adapter.load(questions_chunk)
        self.assertEqual(saved, 1)

        question = Question.objects.get(title="Ingested One")
        self.assertEqual(question.body, "Body 1")
        self.assertEqual(question.categories.count(), 2)
        self.assertEqual(question.options.count(), 2)
        self.assertEqual(question.source, Question.SourceType.GITHUB_IMPORT)

    def test_load_honors_limit(self):
        self.adapter.limit = 1
        data = [
            {"title": "Q1", "body": "B1", "reference_answer": "R1"},
            {"title": "Q2", "body": "B2", "reference_answer": "R2"},
        ]
        saved = self.adapter.load(data)
        self.assertEqual(saved, 1)
        self.assertEqual(Question.objects.count(), 1)


class TestQuestionIngestionPipeline(TestCase):
    def test_invalid_adapter_raises_error(self):
        with self.assertRaises(ValueError) as context:
            QuestionIngestionPipeline(adapter_name="unknown")
        self.assertIn("not registered", str(context.exception))

    @patch(
        "apps.questions.ingestion.pipeline.QuestionIngestionPipeline._setup_repository"
    )
    def test_pipeline_instantiates_adapter(self, mock_setup):
        from apps.questions.ingestion.devops_adapter import DevOpsExercisesAdapter

        pipeline = QuestionIngestionPipeline(adapter_name="devops")
        self.assertEqual(pipeline.repo_config["adapter_class"], DevOpsExercisesAdapter)
        self.assertTrue(pipeline.local_repo_path.endswith("devops-exercises"))

    @patch("subprocess.run")
    def test_pipeline_setup_repository(self, mock_subprocess):
        pipeline = QuestionIngestionPipeline(adapter_name="devops")

        # We can't mock os.path.exists fully dynamically easily without patch,
        # but mocking subprocess ensures no real shell commands map to github.
        with patch("os.path.exists", return_value=False), patch("os.makedirs"):
            pipeline._setup_repository()
            mock_subprocess.assert_called()
