from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.interviews.models import InterviewSession, UserAnswer
from apps.interviews.tasks import evaluate_answer_task, generate_report_task
from apps.questions.models import Question
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


class TestInterviewTasks(TransactionTestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.session = InterviewSessionFactory.create(
            user=self.user,
            target_position="Backend",
            status=InterviewSession.Status.QUESTIONING,
        )
        self.question = QuestionFactory.create(
            title="Q1", body="B1", reference_answer="R1"
        )
        self.answer = UserAnswerFactory.create(
            session=self.session,
            user=self.user,
            question=self.question,
            answer_text="Test",
            status=UserAnswer.Status.PENDING,
        )

    @patch("apps.interviews.services.EvaluationService.evaluate_answer")
    def test_evaluate_answer_task(self, mock_evaluate):
        # مهم: channel_layer رو None برمیگردونیم تا branch مربوط به WebSocket
        # اجرا نشه. اگه MagicMock برگردونه، async_to_sync روی mock می‌ترکه.
        # مهم: autoretry_for=(Exception,) فعاله؛ اگه چیزی پرتاب بشه، رتری میشه.
        with patch("apps.interviews.tasks.get_channel_layer", return_value=None):
            # _check_all_evaluated.apply_async هم داخل task صدا زده میشه؛
            # اون رو هم mock میکنیم تا celery دیگه کاری انجام نده.
            with patch("apps.interviews.tasks._check_all_evaluated.apply_async"):
                evaluate_answer_task(self.answer.pk)

        mock_evaluate.assert_called_once()
        args, kwargs = mock_evaluate.call_args
        self.assertEqual(args[0].pk, self.answer.pk)

    @patch("apps.interviews.services.ReportService.generate_final_report")
    def test_generate_report_task(self, mock_generate):
        # ReportService.generate_final_report رو طوری mock کنیم که session رو
        # برگردونه چون task بعدش session.uuid و session.final_score رو میخونه.
        mock_generate.return_value = self.session

        with patch("apps.interviews.tasks.get_channel_layer", return_value=None):
            generate_report_task(self.session.pk)

        mock_generate.assert_called_once()
        args, kwargs = mock_generate.call_args
        self.assertEqual(args[0].pk, self.session.pk)
